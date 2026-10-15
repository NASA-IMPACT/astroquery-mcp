"""Introspect astroquery modules and generate MCP tools dynamically."""

import inspect
import importlib
import logging
import re
from typing import Any, Callable, get_type_hints
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Astroquery modules to expose
ASTROQUERY_MODULES = {
    "simbad": "astroquery.simbad.Simbad",
    "ned": "astroquery.ipac.ned.Ned",
    "vizier": "astroquery.vizier.Vizier",
    "ads": "astroquery.nasa_ads.ADS",
    "mast": "astroquery.mast.Observations",
    "mast_catalogs": "astroquery.mast.Catalogs",
    "heasarc": "astroquery.heasarc.Heasarc",
    "irsa": "astroquery.ipac.irsa.Irsa",
    "nea": "astroquery.ipac.nexsci.nasa_exoplanet_archive.NasaExoplanetArchive",
    "gaia": "astroquery.gaia.Gaia",
    "sdss": "astroquery.sdss.SDSS",
    "alma": "astroquery.alma.Alma",
    "esa_hubble": "astroquery.esa.hubble.ESAHubble",
    "esa_jwst": "astroquery.esa.jwst.Jwst",
    "xmm_newton": "astroquery.esa.xmm_newton.XMMNewton",
    # Astropy coordinates (commonly used with astroquery)
    "coordinates": "astropy.coordinates.SkyCoord",
}

# Methods to skip (internal/private)
SKIP_METHODS = {
    "__init__", "__class__", "__repr__", "__str__",
    "_request", "_parse_result", "_args_to_payload",
}

# Special methods to always include (authentication, help, etc.)
ALWAYS_INCLUDE_METHODS = {
    "login", "logout", "login_gui", "authenticated", "auth",
    "help", "help_tap",
}

# Methods that are typically useful query methods
QUERY_METHOD_PREFIXES = (
    # Core query methods
    "query_", "get_", "list_", "search_", "download_",
    "fetch_", "resolve_", "cone_search", "locate_",

    # Configuration & cache management (10 modules)
    "clear_", "reset_",

    # GAIA TAP/async workflows
    "launch_", "load_", "save_", "upload_",

    # Advanced analysis & filtering
    "cross_", "filter_",

    # Feature toggling & resource management
    "enable_", "disable_", "delete_", "remove_", "rename_",

    # Collaboration
    "share_",

    # Discovery & configuration
    "add_", "find_",
)

# Methods that fetch science products (files) rather than metadata. Their results are stored as
# artifacts and returned as descriptors; see executor.py and artifacts.py.
RETRIEVAL_METHOD_RE = re.compile(
    r"^(download_|get_images|get_spectra|get_spectral_template|get_product$|"
    r"get_files_from_tarballs$|load_data$|save_results$)"
)


def function_kind(method_name: str) -> str:
    """'retrieval' for methods that fetch science products, else 'metadata'."""
    return "retrieval" if RETRIEVAL_METHOD_RE.match(method_name) else "metadata"


@dataclass
class ParameterInfo:
    """Information about a function parameter."""
    name: str
    type_hint: str
    default: Any = None
    has_default: bool = False
    description: str = ""


@dataclass
class FunctionInfo:
    """Information about an astroquery function."""
    module_name: str
    class_name: str
    method_name: str
    full_name: str
    description: str
    parameters: list[ParameterInfo] = field(default_factory=list)
    callable: Callable | None = None
    kind: str = "metadata"


def get_type_hint_str(hint: Any) -> str:
    """Convert a type hint to a string representation."""
    if hint is inspect.Parameter.empty:
        return "Any"
    if hasattr(hint, "__name__"):
        return hint.__name__
    return str(hint).replace("typing.", "")


def extract_param_description(docstring: str, param_name: str) -> str:
    """Extract parameter description from docstring."""
    if not docstring:
        return ""

    # Look for numpy-style or Google-style param docs
    lines = docstring.split("\n")
    in_params = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower() in ("parameters", "parameters:", "args:", "arguments:"):
            in_params = True
            continue
        if in_params:
            if stripped.startswith(param_name):
                # Found the parameter
                desc_parts = []
                # Get rest of line after param name
                rest = stripped[len(param_name):].lstrip(": ")
                if rest:
                    desc_parts.append(rest)
                # Check following lines for continuation
                for j in range(i + 1, min(i + 5, len(lines))):
                    next_line = lines[j].strip()
                    if not next_line or next_line[0].isalpha() and ":" in next_line[:30]:
                        break
                    desc_parts.append(next_line)
                return " ".join(desc_parts)[:200]
            elif stripped and not stripped[0].isspace() and ":" in stripped[:30]:
                # Another parameter, stop looking
                continue
            elif stripped.lower() in ("returns", "returns:", "raises", "raises:", "examples", "examples:"):
                break
    return ""


def introspect_class(module_name: str, class_path: str) -> list[FunctionInfo]:
    """Introspect a class and extract callable methods.

    Args:
        module_name: Short name for the module (e.g., 'simbad')
        class_path: Full import path (e.g., 'astroquery.simbad.Simbad')

    Returns:
        List of FunctionInfo for exposed methods.
    """
    functions = []

    try:
        # Import the module and get the class
        parts = class_path.rsplit(".", 1)
        if len(parts) == 2:
            module_path, class_name = parts
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
        else:
            module = importlib.import_module(class_path)
            cls = module
            class_name = class_path.split(".")[-1]

        # Get all methods
        for method_name in dir(cls):
            # Skip private/internal methods
            if method_name.startswith("_") or method_name in SKIP_METHODS:
                continue

            method = getattr(cls, method_name, None)
            if method is None or not callable(method):
                continue

            # Focus on query-like methods and special methods
            matches_prefix = any(method_name.startswith(p) or method_name == p.rstrip("_")
                               for p in QUERY_METHOD_PREFIXES)
            is_special_method = method_name in ALWAYS_INCLUDE_METHODS
            is_useful_classmethod = isinstance(inspect.getattr_static(cls, method_name), (classmethod, staticmethod))

            if not (matches_prefix or is_special_method or is_useful_classmethod):
                continue

            # Extract function info
            try:
                sig = inspect.signature(method)
                docstring = inspect.getdoc(method) or ""

                # Get type hints if available
                try:
                    hints = get_type_hints(method)
                except Exception:
                    hints = {}

                # Extract parameters
                params = []
                for param_name, param in sig.parameters.items():
                    if param_name in ("self", "cls"):
                        continue

                    param_info = ParameterInfo(
                        name=param_name,
                        type_hint=get_type_hint_str(hints.get(param_name, param.annotation)),
                        default=param.default if param.default is not inspect.Parameter.empty else None,
                        has_default=param.default is not inspect.Parameter.empty,
                        description=extract_param_description(docstring, param_name),
                    )
                    params.append(param_info)

                # Create function info
                full_name = f"{module_name}_{method_name}"
                func_info = FunctionInfo(
                    module_name=module_name,
                    class_name=class_name,
                    method_name=method_name,
                    full_name=full_name,
                    description=docstring.split("\n")[0] if docstring else f"{class_name}.{method_name}",
                    parameters=params,
                    callable=method,
                    kind=function_kind(method_name),
                )
                functions.append(func_info)

            except Exception as e:
                logger.debug(f"Could not introspect {class_name}.{method_name}: {e}")
                continue

    except ImportError as e:
        logger.warning(f"Could not import {class_path}: {e}")
    except Exception as e:
        logger.warning(f"Error introspecting {class_path}: {e}")

    return functions


def discover_all_functions() -> dict[str, list[FunctionInfo]]:
    """Discover all available functions from configured modules.

    Returns:
        Dict mapping module names to lists of FunctionInfo.
    """
    all_functions = {}

    for module_name, class_path in ASTROQUERY_MODULES.items():
        functions = introspect_class(module_name, class_path)
        if functions:
            all_functions[module_name] = functions
            logger.info(f"Discovered {len(functions)} functions from {module_name}")

    return all_functions


def get_function_by_name(full_name: str) -> FunctionInfo | None:
    """Get a function by its full name (e.g., 'simbad_query_object')."""
    all_funcs = discover_all_functions()
    for module_funcs in all_funcs.values():
        for func in module_funcs:
            if func.full_name == full_name:
                return func
    return None
