# astroquery-mcp

astroquery-mcp is an MCP server that lets your AI assistants, like Claude and Codex, search
astronomy data for you. Ask a question in
plain language, and the assistant can look up objects, find telescope observations, pull catalog
data and search the research literature from the following archives:

```{include} reference/archive_list.md
```

## Installation

```bash
git clone https://github.com/NASA-IMPACT/astroquery-mcp.git
cd astroquery-mcp
uv sync
```

### Run locally

You can run this MCP server locally from the code you just cloned. This starts it at
`http://127.0.0.1:8000/mcp`:

```bash
uv run fastmcp run server.py --transport http --port 8000
```

To use a different port (for example, when 8000 is already in use), change `--port`. The URL
changes to match, e.g. `--port 9000` gives `http://127.0.0.1:9000/mcp`.

Point any MCP client that supports HTTP servers at that URL. For example, in Claude Code:

```bash
claude mcp add --transport http astroquery http://127.0.0.1:8000/mcp
```

### Authentication

| Service | Environment variable | Needed for |
|---|---|---|
| NASA ADS | `API_DEV_KEY` | All ADS queries |
| MAST | `MAST_TOKEN` | Proprietary MAST data only |

Set them in your shell before starting the server:

```bash
export API_DEV_KEY="your-ads-token"
export MAST_TOKEN="your-mast-token"
```

Use the `astroquery_check_auth` tool to see which tokens the server picked up.

## Typical workflow

```python
astroquery_list_modules()                              # which archives exist
astroquery_list_functions("simbad")                    # which functions SIMBAD has
astroquery_get_function_info("simbad", "query_object") # parameters of one function
astroquery_execute("simbad", "query_object", {"object_name": "M31"})
```

Special parameter handling in `astroquery_execute`:

- **Coordinates** can be an object name (`"M31"`) or `{"ra": 10.68, "dec": 41.27}` (degrees).
- **Radius** can be a number (arcmin) or `{"value": 5, "unit": "arcmin"}`.

## Links

- Source: [github.com/NASA-IMPACT/astroquery-mcp](https://github.com/NASA-IMPACT/astroquery-mcp)
- Issues: [github.com/NASA-IMPACT/astroquery-mcp/issues](https://github.com/NASA-IMPACT/astroquery-mcp/issues)

```{toctree}
:hidden:
:maxdepth: 2

Home <self>
reference/tools
reference/archives/index
```
