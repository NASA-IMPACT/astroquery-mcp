# astroquery-mcp

An [MCP](https://modelcontextprotocol.io/) server that gives AI assistants access to
astronomical archives through [astroquery](https://astroquery.readthedocs.io/).

The server does not hand-write a tool for every archive function. It uses **introspection**
(Python looking at its own code at runtime) to discover functions from astroquery classes such as
`Simbad`, `Ned` and `Observations`, and exposes them through a small set of generic MCP tools.

## How to read these docs

- **[MCP Tools](reference/tools.md)**: the tools an AI client actually sees and calls.
- **[Archives](reference/archives/index.md)**: every archive (SIMBAD, NED, MAST, ...) and every
  function you can call through `astroquery_execute`, with parameters from the upstream docstrings.

Both reference sections are generated from the source code on every release, so they always match
the server.

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

## Installation

```bash
git clone https://github.com/NASA-IMPACT/astroquery-mcp.git
cd astroquery-mcp
uv sync
uv run python3 server.py
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "astroquery": {
      "command": "uv",
      "args": ["--directory", "/path/to/astroquery-mcp", "run", "python3", "server.py"],
      "env": { "API_DEV_KEY": "your-ads-token", "MAST_TOKEN": "your-mast-token" }
    }
  }
}
```

### Authentication

| Service | Environment variable | Needed for |
|---|---|---|
| NASA ADS | `API_DEV_KEY` | All ADS queries |
| MAST | `MAST_TOKEN` | Proprietary MAST data only |

Use the `astroquery_check_auth` tool to see which tokens the server picked up.

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
