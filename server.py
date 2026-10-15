"""MCP server for astroquery - dynamically exposes all astroquery functions."""

import logging
from typing import Any, Literal

from fastmcp import FastMCP

from artifacts import RESOURCE_URI, get_store
from auth import configure_astroquery_auth
from executor import (
    execute_function,
    list_modules,
    list_functions,
    get_function_info,
)
from models.errors import MCPError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastMCP server
mcp = FastMCP(
    "astroquery-mcp",
    instructions="""MCP server for astronomical data queries via astroquery.

## Coordinates (COMMONLY USED)
Astronomical coordinate operations via SkyCoord:
- Resolve names: astroquery_execute("coordinates", "from_name", {"name": "M31"})
- Get constellation: astroquery_execute("coordinates", "get_constellation", ...)
- Search nearby: astroquery_execute("coordinates", "search_around_sky", ...)

Returns rich coordinate data: RA/Dec (deg + HMS/DMS), Galactic, multiple frames

## ADS Queries (RECOMMENDED)
Literature search tools that return only the fields you need:
- `ads_query_compact()` - Search ADS and get a short list of papers
- `ads_get_paper()` - Get full details for a specific bibcode

Example ADS workflow:
1. ads_query_compact("NGC 3783", fields="minimal", max_results=10)
2. Pick interesting paper from results
3. ads_get_paper(bibcode, include_abstract=True)

## Generic Queries
Use these for other services or advanced queries:
- `astroquery_list_modules()` - See available services (SIMBAD, ADS, MAST, etc.)
- `astroquery_list_functions()` - See what functions a module provides
- `astroquery_get_function_info()` - Get detailed parameter info for a function
- `astroquery_execute()` - Call any astroquery function (returns ALL fields)

Example generic workflow:
1. astroquery_list_modules() -> see available modules
2. astroquery_list_functions("simbad") -> see SIMBAD functions
3. astroquery_get_function_info("simbad", "query_object") -> see parameters
4. astroquery_execute("simbad", "query_object", {"object_name": "M31"}) -> run query

Note: Generic astroquery_execute() for ADS returns every field ADS has for each paper.
Use ads_query_compact() instead for shorter results.

## Science products (FITS images, spectra, tarballs)
Functions are either kind="metadata" (catalog rows, product lists: returned inline) or
kind="retrieval" (download_*, get_images, get_spectra, get_product, ...: fetch files).
Retrieval results never contain file contents. Each file is saved on the server and described
in the response's "artifacts" list: archive, product_id, filename, content_type, size_bytes,
sha256, download_url (archive URL when known), local_path, resource_uri, and for FITS a short
header summary. Discover with metadata functions first (e.g. mast get_product_list), then
retrieve only what is needed. The file bytes are available via the resource_uri
(astroquery://artifacts/{artifact_id}) for the client, not for the model context.
""",
)

# Configure authentication at module import time (for fastmcp cloud compatibility)
logger.info("Configuring astroquery authentication...")
auth_status = configure_astroquery_auth()
logger.info(f"Auth configured: {auth_status}")

# NOTE: Do NOT call list_modules() here. It eagerly imports every astroquery
# submodule (gaia, heasarc, jwst, xmm_newton, alma, ...) which takes ~60s and
# exceeds fastmcp.app's Lambda cold-start timeout, causing the server to exit
# before it can respond to `initialize`. Module imports are done lazily on
# first use via executor._class_cache.


def handle_error(e: Exception) -> dict[str, Any]:
    """Convert exception to error response."""
    if isinstance(e, MCPError):
        return e.to_dict()
    return {
        "error": True,
        "code": "INTERNAL_ERROR",
        "message": str(e),
        "service": "unknown",
        "recoverable": False,
        "suggestion": "Check server logs for details",
    }


@mcp.tool()
def astroquery_list_modules() -> dict[str, Any]:
    """List all available astroquery modules/services.

    Returns a list of modules like simbad, mast, ads, vizier, etc.
    with availability status.

    Returns:
        Dict with module_count and list of modules with name, class_path, available.
    """
    try:
        return list_modules()
    except Exception as e:
        return handle_error(e)


@mcp.tool()
def astroquery_list_functions(module_name: str | None = None) -> dict[str, Any]:
    """List available functions for a module.

    Args:
        module_name: Module to list functions for (e.g., 'simbad').
                    If None, lists all functions from all modules.

    Returns:
        Dict with function_count and list of functions with name, kind, description,
        parameters. kind is "metadata" (results returned inline) or "retrieval" (fetches
        files, which are returned as artifact descriptors).
    """
    try:
        return list_functions(module_name)
    except Exception as e:
        return handle_error(e)


@mcp.tool()
def astroquery_get_function_info(module_name: str, function_name: str) -> dict[str, Any]:
    """Get detailed information about a specific function.

    Args:
        module_name: Module name (e.g., 'simbad')
        function_name: Function name (e.g., 'query_object')

    Returns:
        Detailed function info including all parameters with types and descriptions.
    """
    try:
        return get_function_info(module_name, function_name)
    except Exception as e:
        return handle_error(e)


@mcp.tool()
def astroquery_check_auth() -> dict[str, Any]:
    """Check authentication status for all services.

    Returns diagnostic information about which services are authenticated,
    which environment variables are set, and any issues detected.

    Returns:
        Dict with authentication status for each service.
    """
    import os
    from auth import check_auth_status, configure_astroquery_auth

    try:
        # Re-configure auth to pick up any new environment variables
        auth_config = configure_astroquery_auth()

        # Get current status
        status = check_auth_status()

        # Add diagnostic info
        result = {
            "status": status,
            "configured": auth_config,
            "diagnostics": {
                "API_DEV_KEY": "set" if os.environ.get("API_DEV_KEY") else "not set",
                "MAST_TOKEN": "set" if os.environ.get("MAST_TOKEN") else "not set",
            }
        }

        # Check if ADS token is accessible
        if os.environ.get("API_DEV_KEY"):
            result["diagnostics"]["API_DEV_KEY_length"] = len(os.environ.get("API_DEV_KEY", ""))

        return result
    except Exception as e:
        return handle_error(e)


@mcp.tool()
def astroquery_execute(
    module_name: str,
    function_name: str,
    params: dict[str, Any] | None = None,
    max_rows: int = 20,
) -> dict[str, Any]:
    """Execute any astroquery function.

    Args:
        module_name: Module name (e.g., 'simbad', 'mast', 'ads', 'vizier')
        function_name: Function name (e.g., 'query_object', 'query_region')
        params: Parameters to pass to the function. Special handling:
            - Coordinates: Pass as {"ra": 10.68, "dec": 41.27} or object name string
            - Radius: Pass as {"value": 5, "unit": "arcmin"} or just a number (arcmin)
        max_rows: Maximum rows kept per result table, for every module and function
            (default: 20). Each table reports row_count (rows returned), total_rows and
            truncated so callers can tell rows were dropped. Raise it, or narrow the query
            (smaller radius, filters, TOP in ADQL), when more rows are needed.

    Returns:
        Dict with success status, kind ("metadata" or "retrieval") and serialized result
        (tables converted to dicts). Science products (FITS images and spectra, downloaded
        files, binary data, large arrays) are never inlined: in "result" they appear as
        {"artifact_id", "filename"} references, and the response's "artifacts" list describes
        each file with archive, product_id, filename, content_type, content_encoding,
        size_bytes, sha256, download_url, local_path, resource_uri and, for FITS files,
        fits_summary (HDU names/shapes and key header cards). Retrieval functions save files
        in a fresh folder of the server's artifact store unless you pass an output folder.

    Examples:
        # SIMBAD object query
        astroquery_execute("simbad", "query_object", {"object_name": "M31"})

        # SIMBAD region query
        astroquery_execute("simbad", "query_region", {
            "coordinates": {"ra": 10.68, "dec": 41.27},
            "radius": {"value": 5, "unit": "arcmin"}
        })

        # MAST observations query
        astroquery_execute("mast", "query_region", {
            "coordinates": "M31",
            "radius": 0.1
        })

        # Vizier catalog query
        astroquery_execute("vizier", "query_object", {
            "object_name": "M31",
            "catalog": "II/246"
        })

        # Retrieval: SDSS images come back as artifact descriptors, not pixel data
        astroquery_execute("sdss", "get_images", {
            "coordinates": {"ra": 179.689, "dec": -0.454},
            "band": "r"
        })
    """
    try:
        return execute_function(module_name, function_name, params, max_rows=max_rows)

    except Exception as e:
        return handle_error(e)


@mcp.tool()
def ads_query_compact(
    query_string: str,
    fields: Literal["minimal", "standard", "extended", "full"] = "standard",
    max_results: int = 10,
    sort: str = "citation_count desc",
) -> dict[str, Any]:
    """Search NASA ADS and return a compact list of papers.

    Returns only the chosen set of fields for each paper, so results stay
    short and easy to scan. Use this instead of astroquery_execute for
    most ADS queries.

    Args:
        query_string: ADS query string (e.g., "black hole X-ray", "author:Smith")
        fields: Which fields to return for each paper:
            - "minimal": bibcode, title, first_author, year, citation_count.
              Best for browsing many results.
            - "standard" (default): minimal + author, pubdate, doi, pub (journal),
              abstract. Good for most queries.
            - "extended": standard + volume, page, keyword.
            - "full": every field ADS returns. Rarely needed.
            All presets list at most 10 authors and shorten abstracts to 200 characters.
        max_results: Maximum number of papers to return (default: 10)
        sort: Sort order (default: "citation_count desc")

    Returns:
        Dict with success status, count, results list, and metadata.

    Examples:
        # Browse many papers quickly
        ads_query_compact("NGC 3783", fields="minimal", max_results=20)

        # Authors, journal and short abstracts
        ads_query_compact("black hole X-ray variability", fields="standard")

        # Add keywords and publication details
        ads_query_compact("AGN feedback", fields="extended", max_results=5)
    """
    from ads_tools import query_ads_compact
    from auth import configure_astroquery_auth

    # Configure auth on-demand
    configure_astroquery_auth()

    try:
        return query_ads_compact(query_string, fields, max_results, sort)
    except Exception as e:
        return handle_error(e)


@mcp.tool()
def ads_get_paper(
    bibcode: str,
    include_abstract: bool = True,
) -> dict[str, Any]:
    """Get details for a specific paper by bibcode.

    Use this after ads_query_compact to get full details about a specific
    paper of interest. Returns all metadata including full author list.

    Args:
        bibcode: ADS bibcode (e.g., "2023ApJ...123..456S")
        include_abstract: Include the full abstract (default: True)

    Returns:
        Dict with success status and full paper details, including all authors.

    Examples:
        # 1. Find papers with compact query
        results = ads_query_compact("NGC 3783", fields="minimal", max_results=10)

        # 2. Get bibcode of interesting paper
        bibcode = results["results"][0]["bibcode"]

        # 3. Get full details
        paper = ads_get_paper(bibcode, include_abstract=True)
    """
    from ads_tools import get_paper_details
    from auth import configure_astroquery_auth

    configure_astroquery_auth()

    fields = None if include_abstract else [
        "bibcode", "title", "author", "year", "pubdate",
        "citation_count", "doi", "pub", "volume", "page"
    ]

    try:
        return get_paper_details(bibcode, fields)
    except Exception as e:
        return handle_error(e)


@mcp.resource(
    RESOURCE_URI,
    name="artifact",
    mime_type="application/octet-stream",
    description="Raw bytes of a science product saved by a retrieval call. The artifact's "
    "descriptor (content_type, sha256, size_bytes) is in the astroquery_execute response.",
)
def read_artifact(artifact_id: str) -> bytes:
    """Return the stored file for an artifact ID from an astroquery_execute response."""
    return get_store().read_bytes(artifact_id)


def main():
    """Main entry point for the MCP server."""
    # Auth is configured at module import time (see above)
    # Run the server (uses stdio by default for fastmcp deploy compatibility)
    mcp.run()



if __name__ == "__main__":
    main()
