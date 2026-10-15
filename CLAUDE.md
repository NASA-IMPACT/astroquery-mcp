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
- `artifacts.py` - Artifact store: science products (FITS, downloads, binary) are saved to disk and returned as descriptors, never inlined. Served via the `astroquery://artifacts/{id}` MCP resource
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
- `test/` - Tests. `uv run pytest` runs offline tests only; live-service tests are marked `network` (`uv run pytest -m network`)
- `.github/workflows/tests.yml` - Offline tests on every PR into main and on main after merge (required check), on Python 3.10-3.13 plus minimum dependency versions; live tests on manual trigger
- `scripts/check_api_compat.py` - Static check that every third-party name/kwarg the code uses exists in the installed versions; CI runs it against the minimum versions

## Compatibility
- Supports Python 3.10+. Floors in `pyproject.toml` are tested in CI, so don't use APIs newer than them (e.g. astropy 7.x-only features) without raising the floor and updating README + CHANGELOG
- Record user-visible changes in `CHANGELOG.md` under `[Unreleased]`

**Docs** (generated, never hand-edit the reference pages):
- `scripts/gen_docs.py` - Builds reference pages from the FastMCP tool registry + `discover_all_functions()`
- `docs/` - Sphinx source (`conf.py` runs the generator); `docs/reference/` is generated and gitignored
- `.github/workflows/docs.yml` - On release: deploys site to GitHub Pages and syncs `build/wiki` to the GitHub wiki
- Tool docstrings in `server.py` ARE the docs: keep Args/Returns/Examples sections accurate

**Metadata vs retrieval**: `introspection.function_kind()` labels methods (regex `RETRIEVAL_METHOD_RE`). Retrieval calls run in a fresh per-call store folder; results go through `serialize_result()`, which turns products into artifact references. New product types → extend `_store_product()` in executor.py, not new tools

**Key Pattern**: Server uses introspection to auto-expose Python packages as MCP tools. Changes to add functionality usually go in executor/introspection, not new tool files.

## Maintenance
- Update this file when making architectural changes or adding new core modules
