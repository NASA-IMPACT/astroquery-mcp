## Environment
- Always use `uv run python3` for running Python scripts

## Development Philosophy
- **Dynamic first**: When user requests changes, prefer dynamic/runtime solutions over creating new tools unless explicitly asked
- Example: Adding new parameter handling → modify executor.py, not create new tool
- Example: Supporting new data format → enhance introspection.py, not hardcode

## Project Structure
**Core MCP Server** (dynamic introspection-based):
- `server.py` - MCP server, tool registry, request handling
- `introspection.py` - Discovers Python package functions dynamically
- `executor.py` - Executes discovered functions, handles parameter conversion
- `main.py` - Entry point

**Specialized Tools**:
- `ads_tools.py` - ADS-specific tools (auth, search)

**Infrastructure**:
- `config.py` - Configuration
- `auth.py` - Authentication (tokens, credentials)
- `http_client.py` - HTTP client with retry
- `retry.py` - Retry logic
- `models/` - Data models (errors, results)
- `utils/` - Helpers (async, coordinates, table serialization)
- `test/` - Tests

**Docs** (generated, never hand-edit the reference pages):
- `scripts/gen_docs.py` - Builds reference pages from the FastMCP tool registry + `discover_all_functions()`
- `docs/` - Sphinx source (`conf.py` runs the generator); `docs/reference/` is generated and gitignored
- `.github/workflows/docs.yml` - On release: deploys site to GitHub Pages and syncs `build/wiki` to the GitHub wiki
- Tool docstrings in `server.py` ARE the docs: keep Args/Returns/Examples sections accurate

**Key Pattern**: Server uses introspection to auto-expose Python packages as MCP tools. Changes to add functionality usually go in executor/introspection, not new tool files.

## Maintenance
- Update this file when making architectural changes or adding new core modules
