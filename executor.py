"""Execute astroquery functions dynamically and serialize results."""

import importlib
import inspect
import io
import logging
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy.coordinates import SkyCoord
from astropy import units as u

from artifacts import COMPRESSION_EXTENSIONS, ArtifactCall, filename_from_url, get_store, working_directory
from introspection import ASTROQUERY_MODULES, discover_all_functions, function_kind
from utils.table_utils import table_to_dict
from models.errors import MCPError, ErrorCode

logger = logging.getLogger(__name__)

# Output-folder parameters of retrieval functions; pointed at the per-call artifact directory
DOWNLOAD_DIR_PARAMS = ("download_dir", "savedir", "folder", "location")
# Table columns that pair a downloaded file with its source URL (e.g. MAST download_products)
LOCAL_PATH_COLUMNS = ("Local Path", "local_path", "LocalPath")
URL_COLUMNS = ("URL", "url", "access_url")
# Results this small stay inline; anything bigger is stored as an artifact
MAX_INLINE_BYTES = 4096
MAX_INLINE_ARRAY_SIZE = 1000

# Cache for loaded classes
_class_cache: dict[str, Any] = {}


def get_class_instance(module_name: str) -> Any:
    """Get or create an instance/class for a module.

    Args:
        module_name: Short module name (e.g., 'simbad')

    Returns:
        The class or instance to call methods on.
    """
    if module_name in _class_cache:
        return _class_cache[module_name]

    if module_name not in ASTROQUERY_MODULES:
        raise MCPError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Unknown module: {module_name}",
            service="executor",
            recoverable=False,
            suggestion=f"Available modules: {', '.join(ASTROQUERY_MODULES.keys())}",
        )

    class_path = ASTROQUERY_MODULES[module_name]

    try:
        parts = class_path.rsplit(".", 1)
        if len(parts) == 2:
            module_path, class_name = parts
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
        else:
            cls = importlib.import_module(class_path)

        _class_cache[module_name] = cls
        return cls

    except ImportError as e:
        raise MCPError(
            code=ErrorCode.SERVICE_ERROR,
            message=f"Could not import {module_name}: {e}",
            service="executor",
            recoverable=False,
            suggestion="Check that astroquery is installed with required extras",
        )


def prepare_argument(value: Any, param_name: str) -> Any:
    """Convert argument values to appropriate types for astroquery.

    Handles special cases like coordinates, units, etc.
    """
    if value is None:
        return None

    # Handle coordinate-like parameters
    coord_params = {"coordinates", "coord", "coords", "position", "pos", "target"}
    if param_name.lower() in coord_params or "coord" in param_name.lower():
        if isinstance(value, dict):
            # Convert dict with ra/dec to SkyCoord
            if "ra" in value and "dec" in value:
                return SkyCoord(
                    ra=value["ra"] * u.deg,
                    dec=value["dec"] * u.deg,
                    frame=value.get("frame", "icrs"),
                )
        elif isinstance(value, str):
            # Try to parse as object name or coordinate string
            try:
                return SkyCoord.from_name(value)
            except Exception:
                try:
                    return SkyCoord(value)
                except Exception:
                    return value

    # Handle radius parameters
    radius_params = {"radius", "rad", "search_radius", "cone_radius"}
    if param_name.lower() in radius_params or "radius" in param_name.lower():
        if isinstance(value, dict):
            # {"value": 5, "unit": "arcmin"}
            val = value.get("value", value.get("v", 1))
            unit_str = value.get("unit", value.get("u", "arcmin"))
            unit = getattr(u, unit_str, u.arcmin)
            return val * unit
        elif isinstance(value, (int, float)):
            # Assume arcmin by default
            return value * u.arcmin

    # Handle width/height for box searches
    if param_name.lower() in {"width", "height"}:
        if isinstance(value, (int, float)):
            return value * u.arcmin
        elif isinstance(value, dict):
            val = value.get("value", 1)
            unit_str = value.get("unit", "arcmin")
            unit = getattr(u, unit_str, u.arcmin)
            return val * unit

    return value


def _is_file_container(value: Any) -> bool:
    return type(value).__name__ == "FileContainer" and hasattr(value, "get_string")


def _existing_file(value: str, artifacts: ArtifactCall) -> Path | None:
    """Return the file a returned string points at (absolute, or relative to the call dir)."""
    if not artifacts.accept_paths or not value or len(value) > 1024 or "\n" in value or "\x00" in value:
        return None
    candidates = [Path(value)]
    if artifacts.has_dir and not Path(value).is_absolute():
        candidates.insert(0, artifacts.dir / value)
    for path in candidates:
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def _note_table_urls(result: Any, artifacts: ArtifactCall) -> None:
    """Remember source URLs listed next to local paths in result tables."""
    tables = result if isinstance(result, list) else [result]
    for table in tables:
        if not isinstance(table, Table):
            continue
        path_col = next((c for c in LOCAL_PATH_COLUMNS if c in table.colnames), None)
        url_col = next((c for c in URL_COLUMNS if c in table.colnames), None)
        if not (path_col and url_col):
            continue
        for row in table:
            path, url = row[path_col], row[url_col]
            if isinstance(path, str) and isinstance(url, str) and path and url:
                artifacts.note_url(path, url)


def _artifact_ref(descriptor: dict[str, Any]) -> dict[str, Any]:
    return {"artifact_id": descriptor["artifact_id"], "filename": descriptor["filename"]}


def _store_product(result: Any, artifacts: ArtifactCall) -> dict[str, Any] | None:
    """Store a science product as an artifact; return a reference, or None if not a product."""
    archive = artifacts.archive
    if _is_file_container(result):
        url = str(result._target)
        data = result.get_string()
        filename = filename_from_url(url, f"{archive}_product")
        # get_readable_fileobj decompresses, so the stored file is not compressed
        for ext in COMPRESSION_EXTENSIONS:
            if filename.lower().endswith(ext):
                filename = filename[: -len(ext)]
        data = data if isinstance(data, bytes) else data.encode()
        return _artifact_ref(artifacts.add_bytes(data, filename, url))
    if isinstance(result, fits.HDUList):
        return _artifact_ref(artifacts.add_hdulist(result, f"{archive}_product.fits"))
    if isinstance(result, fits.PrimaryHDU):
        return _artifact_ref(artifacts.add_hdulist(fits.HDUList([result]), f"{archive}_product.fits"))
    if isinstance(result, fits.hdu.base.ExtensionHDU):
        return _artifact_ref(artifacts.add_hdulist(fits.HDUList([fits.PrimaryHDU(), result]), f"{archive}_product.fits"))
    if isinstance(result, (bytes, bytearray)):
        data = bytes(result)
        filename = f"{archive}_product" if data[:9] == b"SIMPLE  =" else f"{archive}_product.bin"
        return _artifact_ref(artifacts.add_bytes(data, filename))
    if isinstance(result, np.ndarray) and result.size > MAX_INLINE_ARRAY_SIZE:
        buffer = io.BytesIO()
        np.save(buffer, result, allow_pickle=False)
        descriptor = artifacts.add_bytes(buffer.getvalue(), f"{archive}_array.npy")
        return {**_artifact_ref(descriptor), "shape": list(result.shape), "dtype": str(result.dtype)}
    return None


def serialize_result(
    result: Any,
    artifacts: ArtifactCall | None = None,
    max_rows: int | None = None,
) -> Any:
    """Serialize astroquery results to JSON-compatible format.

    Handles Astropy Tables, SkyCoords, Quantities, etc. Science products (FITS HDULists, lazy
    FileContainers, binary blobs, large arrays, paths to downloaded files) are never inlined:
    they are stored in the artifact store and replaced by {"artifact_id", "filename"} references.
    Every table, at any nesting level, is cut to max_rows rows (None = no limit).
    """
    if result is None:
        return None

    if artifacts is None:
        artifacts = ArtifactCall(get_store(), "unknown")

    # Short text responses stay inline; binary or large payloads become artifacts
    if isinstance(result, (bytes, bytearray)) and len(result) <= MAX_INLINE_BYTES and b"\x00" not in result:
        try:
            return bytes(result).decode("utf-8")
        except UnicodeDecodeError:
            pass

    product = _store_product(result, artifacts)
    if product is not None:
        return product

    # Path to a file the library downloaded
    if isinstance(result, str) and (path := _existing_file(result, artifacts)):
        return _artifact_ref(artifacts.add_file(path))

    # Astropy Table
    if isinstance(result, Table):
        return table_to_dict(result, max_rows)

    # List of Tables
    if isinstance(result, list) and result and all(isinstance(t, Table) for t in result):
        return [table_to_dict(t, max_rows) for t in result]

    # SkyCoord - provide rich output with multiple formats
    if isinstance(result, SkyCoord):
        # Handle both single coordinates and arrays
        if result.isscalar:
            return {
                "ra_deg": float(result.ra.deg),
                "dec_deg": float(result.dec.deg),
                "ra_hms": result.ra.to_string(unit=u.hour, sep="hms", precision=2),
                "dec_dms": result.dec.to_string(unit=u.deg, sep="dms", precision=1),
                "frame": result.frame.name,
                "galactic": {
                    "l": float(result.galactic.l.deg),
                    "b": float(result.galactic.b.deg),
                },
                "hmsdms": result.to_string("hmsdms"),
                "decimal": result.to_string("decimal", precision=4),
            }
        else:
            # Array of coordinates
            return {
                "count": len(result),
                "ra_deg": result.ra.deg.tolist(),
                "dec_deg": result.dec.deg.tolist(),
                "frame": result.frame.name,
            }

    # Astropy Quantity
    if hasattr(result, "value") and hasattr(result, "unit"):
        if np.ndim(result.value) == 0:
            return {"value": float(result.value), "unit": str(result.unit)}
        return {"value": serialize_result(np.asarray(result.value), artifacts, max_rows), "unit": str(result.unit)}

    # Small numpy arrays inline (large ones were stored above)
    if isinstance(result, np.ndarray):
        return result.tolist()

    # Dict - recursively serialize
    if isinstance(result, dict):
        return {k: serialize_result(v, artifacts, max_rows) for k, v in result.items()}

    # List/tuple - recursively serialize
    if isinstance(result, (list, tuple)):
        return [serialize_result(item, artifacts, max_rows) for item in result]

    # Numpy types
    if hasattr(result, "item"):
        return result.item()

    return result


def _resolve_method(cls: Any, function_name: str, kind: str) -> Any:
    """For retrieval functions with an `_async` twin (NED/SDSS get_images, get_spectra, ...),
    call the twin: it returns lazy FileContainers that keep the source URL, instead of parsed
    HDULists that have lost it."""
    if kind == "retrieval" and not function_name.endswith("_async"):
        twin = getattr(cls, f"{function_name}_async", None)
        if twin is not None:
            return twin
    return getattr(cls, function_name, None)


def _call(method: Any, params: dict[str, Any], kind: str, artifacts: ArtifactCall) -> Any:
    """Run the method; retrieval runs inside the per-call artifact directory."""
    if kind != "retrieval":
        return method(**params)
    try:
        accepted = inspect.signature(method).parameters
    except (TypeError, ValueError):
        accepted = {}
    for name in DOWNLOAD_DIR_PARAMS:
        if name in accepted and params.get(name) is None:
            params[name] = str(artifacts.dir)
    # Functions without an output-folder parameter write to the current directory
    with working_directory(artifacts.dir):
        return method(**params)


def execute_function(
    module_name: str,
    function_name: str,
    params: dict[str, Any] | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Execute an astroquery function dynamically.

    Args:
        module_name: Short module name (e.g., 'simbad')
        function_name: Method name (e.g., 'query_object')
        params: Parameters to pass to the function
        max_rows: Maximum rows kept per result table (None = no limit)

    Returns:
        Serialized result with metadata.
    """
    params = params or {}
    if max_rows is not None and max_rows < 1:
        raise MCPError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"max_rows must be at least 1, got {max_rows}",
            service="executor",
            recoverable=False,
            suggestion="Pass a positive max_rows, or narrow the query",
        )

    try:
        # Configure authentication on-demand for services that need it
        if module_name in ("ads", "mast", "mast_catalogs"):
            import os
            from auth import configure_astroquery_auth

            logger.info(f"=== AUTH DEBUG for {module_name} ===")
            logger.info(f"API_DEV_KEY env var present: {bool(os.environ.get('API_DEV_KEY'))}")
            if os.environ.get('API_DEV_KEY'):
                logger.info(f"API_DEV_KEY length: {len(os.environ.get('API_DEV_KEY'))}")

            auth_status = configure_astroquery_auth()
            logger.info(f"Auth configuration result: {auth_status}")
            logger.info(f"=== END AUTH DEBUG ===")

        # Get the class/instance
        cls = get_class_instance(module_name)

        # Get the method
        kind = function_kind(function_name)
        method = _resolve_method(cls, function_name, kind)
        if method is None:
            raise MCPError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Function not found: {module_name}.{function_name}",
                service="executor",
                recoverable=False,
                suggestion=f"Use list_functions to see available functions",
            )

        # Prepare arguments
        prepared_params = {}
        for key, value in params.items():
            prepared_params[key] = prepare_argument(value, key)

        logger.info(f"Executing {module_name}.{function_name} ({kind}) with {list(prepared_params.keys())}")

        artifacts = ArtifactCall(get_store(), module_name, accept_paths=kind == "retrieval")
        try:
            # Execute the function
            result = _call(method, prepared_params, kind, artifacts)

            # Serialize the result; products become artifacts, files written to the call dir too
            _note_table_urls(result, artifacts)
            serialized = serialize_result(result, artifacts, max_rows)
            artifacts.collect_dir()
        finally:
            artifacts.cleanup_if_empty()

        response = {
            "success": True,
            "module": module_name,
            "function": function_name,
            "kind": kind,
            "params": {k: str(v)[:100] for k, v in params.items()},  # Truncate for logging
            "result": serialized,
        }
        if artifacts.descriptors:
            response["artifacts"] = artifacts.descriptors
        return response

    except MCPError:
        raise
    except TypeError as e:
        # Usually means wrong parameters
        raise MCPError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Invalid parameters for {module_name}.{function_name}: {e}",
            service="executor",
            recoverable=False,
            suggestion="Check parameter names and types using get_function_info",
            details={"params": list(params.keys())},
        )
    except Exception as e:
        raise MCPError(
            code=ErrorCode.SERVICE_ERROR,
            message=f"Execution failed: {e}",
            service=module_name,
            recoverable=True,
            suggestion="Check parameters and try again",
            details={"function": function_name, "error": str(e)},
        )


def list_modules() -> dict[str, Any]:
    """List available astroquery modules.

    Availability is checked via `importlib.util.find_spec` on the parent
    module, which is cheap (no heavy import side-effects). Actually loading
    a module happens lazily on first use in `get_class_instance`.

    Returns:
        Dict with module information.
    """
    import importlib.util

    modules = []
    for name, path in ASTROQUERY_MODULES.items():
        # Already cached → definitely available
        if name in _class_cache:
            available = True
        else:
            # Check the parent module can be located without importing it
            parent_path = path.rsplit(".", 1)[0] if "." in path else path
            try:
                available = importlib.util.find_spec(parent_path) is not None
            except (ImportError, ValueError):
                available = False

        modules.append({
            "name": name,
            "class_path": path,
            "available": available,
        })

    return {
        "module_count": len(modules),
        "modules": modules,
    }


def list_functions(module_name: str | None = None) -> dict[str, Any]:
    """List available functions.

    Args:
        module_name: Optional module to filter by

    Returns:
        Dict with function information.
    """
    all_funcs = discover_all_functions()

    if module_name:
        if module_name not in all_funcs:
            return {"functions": [], "error": f"Module not found: {module_name}"}
        funcs = all_funcs[module_name]
    else:
        funcs = []
        for module_funcs in all_funcs.values():
            funcs.extend(module_funcs)

    # Convert to serializable format
    function_list = []
    for f in funcs:
        function_list.append({
            "name": f.full_name,
            "module": f.module_name,
            "method": f.method_name,
            "kind": f.kind,
            "description": f.description[:200] if f.description else "",
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type_hint,
                    "required": not p.has_default,
                    "default": str(p.default)[:50] if p.has_default else None,
                    "description": p.description,
                }
                for p in f.parameters
            ],
        })

    return {
        "function_count": len(function_list),
        "functions": function_list,
    }


def get_function_info(module_name: str, function_name: str) -> dict[str, Any]:
    """Get detailed info about a specific function.

    Args:
        module_name: Module name
        function_name: Function name

    Returns:
        Detailed function information.
    """
    all_funcs = discover_all_functions()

    if module_name not in all_funcs:
        return {"error": f"Module not found: {module_name}"}

    for f in all_funcs[module_name]:
        if f.method_name == function_name:
            return {
                "name": f.full_name,
                "module": f.module_name,
                "class": f.class_name,
                "method": f.method_name,
                "kind": f.kind,
                "description": f.description,
                "parameters": [
                    {
                        "name": p.name,
                        "type": p.type_hint,
                        "required": not p.has_default,
                        "default": str(p.default) if p.has_default else None,
                        "description": p.description,
                    }
                    for p in f.parameters
                ],
            }

    return {"error": f"Function not found: {module_name}.{function_name}"}
