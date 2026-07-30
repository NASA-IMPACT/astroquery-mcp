# Astroquery MCP Server

A Model Context Protocol (MCP) server that dynamically exposes all astroquery functionality to AI assistants. This server uses introspection to discover and expose Python package functionality through MCP tools, making it a reusable template for creating MCP servers for any Python library.

> Part of **AI Agents for Science** (Accelerated Knowledge Discovery — AKD). This MCP server is the
> data-access backend for the [**AKD Astro Data Search Agent**](https://huggingface.co/spaces/ai-agents-for-science/astro-data-search-agent),
> a natural-language astrophysics dataset-discovery system, also packaged as a
> [Claude Code plugin](https://github.com/NASA-IMPACT/akd-plugins/tree/main/plugins/astro-data-search-assistant).

## What is This?

This is an MCP server that:
- **Dynamically discovers** all functions from astroquery modules using Python introspection
- **Exposes them as MCP tools** that AI assistants can call
- **Handles parameter conversion** (e.g., coordinates, units) automatically
- **Serializes results** (Astropy Tables → JSON) for AI consumption
- Provides a **reusable pattern** for wrapping any Python package as an MCP server

## Available Astroquery Modules

This server provides access to **14 astronomical data services** with **141 functions** total:

| Module | Functions | Description |
|--------|-----------|-------------|
| **SIMBAD** | 18 | Astronomical database for object resolution and crossmatch |
| **NED** | 15 | NASA/IPAC Extragalactic Database for galaxies and extragalactic objects |
| **VizieR** | 9 | Access to astronomical catalogs and data tables |
| **ADS** | 1 | NASA Astrophysics Data System for literature search |
| **MAST** | 19 | Mikulski Archive for Space Telescopes (HST, JWST, etc.) |
| **MAST Catalogs** | 12 | Query catalogs in MAST (HSC, PanSTARRS, etc.) |
| **HEASARC** | 9 | High Energy Astrophysics archive (X-ray, gamma-ray) |
| **IRSA** | 7 | NASA/IPAC Infrared Science Archive |
| **NASA Exoplanet Archive** | 7 | Exoplanet data and confirmed planets |
| **Gaia** | 13 | ESA Gaia mission astrometric catalog |
| **SDSS** | 16 | Sloan Digital Sky Survey optical imaging and spectroscopy |
| **ALMA** | 16 | Atacama Large Millimeter/submillimeter Array data |
| **ESA Hubble** | 21 | ESA Hubble Space Telescope Archive |
| **ESA JWST** | 16 | ESA James Webb Space Telescope Archive |

**Example queries:**
- Query SIMBAD for object data: `execute("simbad", "query_object", {"object_name": "M31"})`
- Search MAST for observations: `execute("mast", "query_region", {"coordinates": "M31", "radius": 0.1})`
- Get exoplanet data: `execute("nea", "query_object", {"object_name": "Kepler-22 b"})`
- Run TAP/ADQL queries: `execute("simbad", "query_tap", {"query": "SELECT TOP 10 * FROM basic"})`

For a complete list of all 141 functions with detailed signatures and parameters, see the [Scope Documentation](https://github.com/yourusername/astroquery-mcp/blob/main/SCOPE.md) (if included in your repository).

## How It Works

### Architecture Overview

```
┌─────────────────┐
│  AI Assistant   │
└────────┬────────┘
         │ MCP Protocol
┌────────▼────────────────────────────────────────┐
│  FastMCP Server (server.py)                     │
│  ┌────────────────────────────────────────┐     │
│  │ MCP Tools:                             │     │
│  │ - astroquery_list_modules()            │     │
│  │ - astroquery_list_functions(module)    │     │
│  │ - astroquery_get_function_info(...)    │     │
│  │ - astroquery_execute(module, func, params) │ │
│  └─────────┬──────────────────────────────┘     │
└────────────┼──────────────────────────────────┘
             │
┌────────────▼──────────────────────────────────┐
│  Introspection Layer (introspection.py)       │
│  - Discovers Python classes/modules           │
│  - Extracts method signatures                 │
│  - Parses docstrings                          │
└────────────┬──────────────────────────────────┘
             │
┌────────────▼──────────────────────────────────┐
│  Executor (executor.py)                       │
│  - Dynamically imports and calls functions    │
│  - Converts parameters (dict → SkyCoord, etc) │
│  - Serializes results (Table → dict)          │
└────────────┬──────────────────────────────────┘
             │
┌────────────▼──────────────────────────────────┐
│  Python Package (astroquery)                  │
│  - SIMBAD, MAST, ADS, Vizier, etc.           │
└───────────────────────────────────────────────┘
```

### Key Components

1. **server.py** - FastMCP server with 4 core tools
2. **introspection.py** - Discovers functions from Python modules
3. **executor.py** - Dynamically executes discovered functions
4. **config.py** - Configuration management
5. **auth.py** - Authentication handling
6. **utils/** - Serialization helpers (Table → dict, etc.)
7. **models/** - Type definitions and error handling

## Using This as a Template

This codebase can be adapted for **any Python package** with a similar structure. Here's how:

### Step 1: Define Your Modules

Edit `introspection.py` to define which classes/modules to expose:

```python
# introspection.py
YOUR_PACKAGE_MODULES = {
    "service1": "your_package.service1.ServiceClass",
    "service2": "your_package.service2.AnotherClass",
    # Add more modules here
}
```

**Examples for different packages:**

```python
# For scikit-learn
SKLEARN_MODULES = {
    "linear_model": "sklearn.linear_model",
    "tree": "sklearn.tree",
    "ensemble": "sklearn.ensemble",
}

# For requests
REQUESTS_MODULES = {
    "requests": "requests",
}

# For pandas
PANDAS_MODULES = {
    "dataframe": "pandas.DataFrame",
    "series": "pandas.Series",
    "io": "pandas",  # For read_csv, etc.
}
```

### Step 2: Customize Parameter Handling

Edit `executor.py`'s `prepare_argument()` function to handle package-specific types:

```python
def prepare_argument(value: Any, param_name: str) -> Any:
    """Convert argument values to appropriate types."""

    # Example: Handle file paths
    if param_name.lower() in {"filepath", "path", "filename"}:
        return Path(value)

    # Example: Handle dataframes from dicts
    if param_name.lower() in {"data", "df"}:
        if isinstance(value, dict):
            import pandas as pd
            return pd.DataFrame(value)

    # Add your package-specific conversions here
    return value
```

For astroquery, we handle:
- **Coordinates**: `dict → SkyCoord`
- **Radius**: `number → Quantity`
- **Units**: `string → astropy.units`

### Step 3: Customize Result Serialization

Edit `executor.py`'s `serialize_result()` to convert package-specific types to JSON:

```python
def serialize_result(result: Any) -> Any:
    """Serialize results to JSON-compatible format."""

    # Example: Handle pandas DataFrames
    if isinstance(result, pd.DataFrame):
        return result.to_dict(orient="records")

    # Example: Handle numpy arrays
    if isinstance(result, np.ndarray):
        return result.tolist()

    # Add your package-specific serialization here
    return result
```

For astroquery, we serialize:
- `astropy.Table → dict`
- `SkyCoord → {ra_deg, dec_deg, frame}`
- `Quantity → {value, unit}`

### Step 4: Update Server Metadata

Edit `server.py` to customize server name and instructions:

```python
mcp = FastMCP(
    "your-package-mcp",  # Change this
    instructions="""MCP server for [your package].

    Use `list_modules` to see available modules
    Use `list_functions` to see available functions
    Use `get_function_info` to get parameter details
    Use `execute` to call any function

    Example workflow:
    1. list_modules()
    2. list_functions("module_name")
    3. get_function_info("module_name", "function_name")
    4. execute("module_name", "function_name", {"param": "value"})
    """,
)

# Update tool names
@mcp.tool()
def your_package_execute(...):
    ...
```

### Step 5: Handle Authentication (if needed)

If your package requires API keys:

1. Edit `config.py` to define auth requirements:
```python
"auth": {
    "your_service": {"token_env": "YOUR_SERVICE_TOKEN"},
}
```

2. Edit `auth.py` to configure the package:
```python
def configure_your_package_auth():
    token = get_token("your_service")
    if token:
        import your_package
        your_package.api_key = token
```

### Step 6: Update pyproject.toml

```toml
[project]
name = "your-package-mcp"
version = "0.1.0"
description = "MCP server for your package"
dependencies = [
    "your-package>=1.0.0",
    "fastmcp>=2.14.2",
    "mcp>=1.25.0",
]

[project.scripts]
your-package-mcp = "server:main"

[tool.fastmcp]
name = "your-package-mcp"
```

## Installation & Usage

### Install Dependencies

```bash
# Using uv (recommended)
uv pip install -e .

# Or using pip
pip install -e .
```

### Run the Server

```bash
# Run directly
python server.py

# Or using fastmcp deploy (for MCP client integration)
fastmcp deploy server.py
```

### Configure Authentication (Optional)

For services requiring authentication:

```bash
export API_DEV_KEY="your-ads-token"
export MAST_TOKEN="your-mast-token"
```

### Use with Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "astroquery": {
      "command": "python",
      "args": ["/path/to/server.py"],
      "env": {
        "API_DEV_KEY": "your-token-here"
      }
    }
  }
}
```

## Example: Creating an MCP Server for Pandas

Here's a complete minimal example for pandas:

```python
# introspection.py
PANDAS_MODULES = {
    "io": "pandas",  # read_csv, read_json, etc.
    "dataframe": "pandas.DataFrame",
}

# executor.py - parameter handling
def prepare_argument(value: Any, param_name: str) -> Any:
    if param_name == "filepath_or_buffer":
        return value  # Already a string path
    return value

# executor.py - result serialization
def serialize_result(result: Any) -> Any:
    if isinstance(result, pd.DataFrame):
        return {
            "columns": result.columns.tolist(),
            "data": result.to_dict(orient="records"),
            "shape": result.shape,
        }
    return result

# server.py
mcp = FastMCP(
    "pandas-mcp",
    instructions="MCP server for pandas data operations"
)
```

Now AI assistants can call:
```python
execute("io", "read_csv", {"filepath_or_buffer": "data.csv"})
execute("dataframe", "describe", {})
```

## Advanced Features

### Method Filtering

By default, introspection looks for methods starting with common patterns:

```python
QUERY_METHOD_PREFIXES = (
    "query_", "get_", "list_", "search_", "download_",
    "fetch_", "resolve_", "cone_search",
)
```

Customize this in `introspection.py` for your package:

```python
# For a REST API wrapper
API_METHOD_PREFIXES = (
    "get_", "post_", "put_", "delete_", "fetch_",
)

# For a data processing library
PROCESSING_METHOD_PREFIXES = (
    "transform_", "process_", "compute_", "analyze_",
)
```

### Error Handling

The template includes structured error handling in `models/errors.py`:

```python
class MCPError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        service: str,
        recoverable: bool = True,
        suggestion: str = "",
        details: dict = None,
    ):
        ...
```

Use it in your code:

```python
raise MCPError(
    code=ErrorCode.VALIDATION_ERROR,
    message="Invalid parameter",
    service="your_module",
    recoverable=False,
    suggestion="Check the function signature",
)
```

### Retry Logic

The template includes configurable retry logic in `retry.py` for handling:
- Network errors
- Rate limiting
- Temporary service failures

Customize in `config.py`:

```python
defaults:
  timeout: 60
  max_retries: 3
  backoff_factor: 2.0
```

## Project Structure

```
astroquery_mcp/
├── server.py              # Main MCP server (FastMCP)
├── introspection.py       # Function discovery via reflection
├── executor.py            # Dynamic function execution
├── config.py             # Configuration management
├── auth.py               # Authentication handling
├── http_client.py        # HTTP client with retry logic
├── retry.py              # Retry decorators
├── models/
│   ├── errors.py         # Error types
│   └── results.py        # Result types
├── utils/
│   ├── table_utils.py    # Table serialization
│   └── param_utils.py    # Parameter conversion
└── tools/
    ├── discovery.py      # Service discovery
    ├── simbad.py         # Service-specific helpers
    └── ...
```

## Key Design Patterns

### 1. Dynamic Discovery
Uses Python's `inspect` and `importlib` to discover functions at runtime:

```python
def introspect_class(module_name: str, class_path: str):
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)

    for method_name in dir(cls):
        method = getattr(cls, method_name)
        sig = inspect.signature(method)
        # Extract parameters, docstrings, etc.
```

### 2. Generic Execution
Single `execute()` function handles all discovered functions:

```python
def execute_function(module_name, function_name, params):
    cls = get_class_instance(module_name)
    method = getattr(cls, function_name)
    prepared_params = {k: prepare_argument(v, k) for k, v in params.items()}
    result = method(**prepared_params)
    return serialize_result(result)
```

### 3. Type Conversion
Bidirectional conversion between JSON and package-specific types:

```
JSON dict → Python objects → Function call → Result → JSON dict
  ↓             ↓               ↓            ↓         ↓
{ra: 10,     SkyCoord(...)   method()    Table     {columns: [],
 dec: 41}                                           data: [...]}
```

## Benefits of This Approach

1. **Zero boilerplate** - No need to manually write MCP tools for each function
2. **Automatic updates** - New package functions are automatically exposed
3. **Type safety** - Introspection captures parameter types and defaults
4. **Discoverable** - AI can explore available functions via `list_functions`
5. **Reusable** - Same pattern works for any Python package
6. **Maintainable** - Changes to the package are automatically reflected

## When to Use This Pattern

This pattern works well for packages that:
- ✅ Have class-based or module-based APIs
- ✅ Use standard Python types or have serializable custom types
- ✅ Have functions with clear parameters (not *args/**kwargs heavy)
- ✅ Have docstrings for parameters

May need customization for:
- ⚠️ Packages with heavy use of callbacks/generators
- ⚠️ Packages requiring complex state management
- ⚠️ Packages with binary data (images, audio, etc.)
- ⚠️ Packages with streaming APIs

## Contributing

To add support for a new astroquery module:

1. Add to `ASTROQUERY_MODULES` in `introspection.py`
2. Add type conversions if needed in `executor.py`
3. Add auth config if needed in `config.py`

## License

MIT License - feel free to use this template for your own MCP servers!

## Related Projects

- [FastMCP](https://github.com/jlowin/fastmcp) - FastAPI-like framework for MCP servers
- [Astroquery](https://astroquery.readthedocs.io/) - Python package for astronomical data queries
- [MCP](https://modelcontextprotocol.io/) - Model Context Protocol specification

## Questions?

This README explains the architecture and how to adapt it. Key files to study:
- `server.py:1-171` - MCP server setup and tool definitions
- `introspection.py:109-198` - How function discovery works
- `executor.py:66-118` - Parameter conversion examples
- `executor.py:121-165` - Result serialization examples

---

# Complete Function Reference

Below is a comprehensive list of all available modules and functions with their complete signatures.

## Summary

- **Total Modules**: 14
- **Total Functions**: 141

## Module List

1. [SIMBAD](#1-simbad) - 18 functions
2. [NED](#2-ned) - 15 functions
3. [VizieR](#3-vizier) - 9 functions
4. [ADS](#4-ads) - 1 function
5. [MAST](#5-mast) - 19 functions
6. [MAST Catalogs](#6-mast-catalogs) - 12 functions
7. [HEASARC](#7-heasarc) - 9 functions
8. [IRSA](#8-irsa) - 7 functions
9. [NASA Exoplanet Archive](#9-nasa-exoplanet-archive) - 7 functions
10. [Gaia](#10-gaia) - 13 functions
11. [SDSS](#11-sdss) - 16 functions
12. [ALMA](#12-alma) - 16 functions
13. [ESA Hubble](#13-esa-hubble) - 21 functions
14. [ESA JWST](#14-esa-jwst) - 16 functions

## Module Details

### 1. SIMBAD

**Class**: `astroquery.simbad.Simbad`

SIMBAD is an astronomical database providing basic data, cross-identifications, bibliography, and measurements for astronomical objects outside the solar system.

#### Functions (18):

##### 1.1 `simbad_query_object(object_name, wildcard=False, criteria=None, get_query_payload=False, async_job=False, verbose=False)`
Query SIMBAD for the given object.

**Parameters**:
- `object_name` (Any, required): Name of object to be queried
- `wildcard` (Any, optional, default=False): When True, object specified with wildcards
- `criteria` (Any, optional): Criteria in ADQL syntax
- `get_query_payload` (Any, optional, default=False): When True, returns HTTP request parameters
- `async_job` (Any, optional, default=False): Execute in asynchronous mode
- `verbose` (Any, optional, default=False): Verbose output flag

##### 1.2 `simbad_query_region(coordinates, radius='2.0 arcmin', criteria=None, get_query_payload=False, async_job=False, equinox=None, epoch=None, cache=None)`
Query SIMBAD in a cone around the specified coordinates.

**Parameters**:
- `coordinates` (Any, required): Identifier or coordinates to query around
- `radius` (Any, optional, default='2.0 arcmin'): Radius of the region
- `criteria` (Any, optional): Criteria in ADQL syntax
- `get_query_payload` (Any, optional, default=False): When True, returns HTTP request parameters
- `async_job` (Any, optional, default=False): Execute in asynchronous mode
- `equinox` (Any, optional): Equinox for coordinates
- `epoch` (Any, optional): Epoch for coordinates
- `cache` (Any, optional): Cache results flag

##### 1.3 `simbad_query_tap(query, maxrec=10000, async_job=False, get_query_payload=False, *uploads)`
Query SIMBAD TAP service.

**Parameters**:
- `query` (str, required): ADQL query string
- `maxrec` (Any, optional, default=10000): Maximum number of records to return
- `async_job` (Any, optional, default=False): Execute in asynchronous mode
- `get_query_payload` (Any, optional, default=False): When True, returns HTTP request parameters
- `uploads` (Any, required): Local tables to be used in query

*For the complete list of all 141 functions across all 14 modules, see the full scope documentation or use the `list_functions()` MCP tool.*

### Key Function Patterns

Most modules support these common query patterns:
- **Object queries**: `query_object(object_name, ...)`
- **Region queries**: `query_region(coordinates, radius, ...)`
- **TAP/ADQL queries**: `query_tap(query, ...)` for advanced SQL-like queries
- **Criteria queries**: `query_criteria(**filters)` for filtering by attributes
- **Download functions**: `download_*()` for retrieving data products
- **List functions**: `list_*()` for discovering available catalogs, tables, columns

### Using the Functions

All functions are called through the `astroquery_execute` MCP tool:

```python
# Basic syntax
execute(module_name, function_name, params)

# Examples
execute("simbad", "query_object", {"object_name": "M31"})
execute("mast", "query_region", {"coordinates": "M31", "radius": 0.1})
execute("heasarc", "query_tap", {"query": "SELECT * FROM chandra_observation"})
```

### Discovery Workflow

1. **List modules**: `list_modules()` - See all 14 available modules
2. **List functions**: `list_functions("simbad")` - See all functions for SIMBAD
3. **Get function info**: `get_function_info("simbad", "query_object")` - See detailed parameters
4. **Execute**: `execute("simbad", "query_object", {"object_name": "M31"})` - Run the query

## Citation

If you use this software in your research, please cite it as:

```
Astroquery MCP Server. NASA IMPACT.
https://github.com/NASA-IMPACT/astroquery-mcp
```

## Contributors

- **Gaurab Panthee** ([@igaurab](https://github.com/igaurab)) — original author
- **Ashkbiz Danehkar** ([@danehkar](https://github.com/danehkar)) — astrophysics domain expertise; Universities Space Research Association
- **Nish** ([@NISH1001](https://github.com/NISH1001)) — NASA IMPACT / UAH
- **Muthukumaran R** ([@muthukumaranR](https://github.com/muthukumaranR)) — NASA IMPACT

## Acknowledgments

Originally developed by [Gaurab Panthee](https://github.com/igaurab) in collaboration with
astrophysicist [Ashkbiz Danehkar](https://github.com/danehkar) (Universities Space Research
Association). This repository is the canonical home for continued development under NASA IMPACT.

Built on [astroquery](https://astroquery.readthedocs.io/), an
[Astropy](https://www.astropy.org/)-affiliated package, and served over MCP with
[FastMCP](https://gofastmcp.com/).

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.
