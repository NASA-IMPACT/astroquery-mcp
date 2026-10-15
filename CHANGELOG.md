# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Security
- Auth diagnostics no longer log any part of a secret. Previously `get_token()` logged the
  first 10 characters of every `API*`/`ADS*` environment variable when a token was missing, and
  `configure_astroquery_auth()` logged the first 10 characters of `ADS.TOKEN` and `API_DEV_KEY`.
  Logs now show variable names and whether a token is set, never the value.

### Added
- Science products are returned as artifacts instead of being put into the model context.
  FITS images and spectra, downloaded files, binary payloads and large arrays are saved in an
  artifact store (per-user cache dir; `ASTROQUERY_MCP_ARTIFACT_DIR` or config `artifacts.dir`
  to override) and described by archive, product ID, filename, content type, size, sha256,
  original download URL, local path, MCP resource URI, and a FITS header summary.
  Previously FITS results serialized as unusable `"<PrimaryHDU object at 0x...>"` strings and
  binary bytes were decoded into the response as text.
- `astroquery://artifacts/{artifact_id}` MCP resource serving an artifact's bytes to the
  client, outside the model context.
- Every function is labeled `kind: "metadata"` or `kind: "retrieval"` in
  `astroquery_list_functions`, `astroquery_get_function_info` and `astroquery_execute`
  responses, separating discovery from product retrieval.
- Retrieval calls run in their own folder in the artifact store, so archives that write to the
  current directory (XMM-Newton, ESA JWST, Gaia) no longer drop files wherever the server runs.
- Offline test suite (`uv run pytest`, no network) covering auth, configuration, argument
  conversion and result serialization, table/coordinate helpers, ADS result filtering, the MCP
  tool registry, and an import check for every module. Includes a regression test that secrets
  never appear in logs.
- `Tests` GitHub Actions workflow: offline tests on every pull request into `main` and on `main`
  after merge, on Python 3.10–3.13 plus the minimum dependency versions. Live-service tests run
  only on manual trigger. `main` requires the **Offline tests** check to pass before merging.
- `scripts/check_api_compat.py`: static check that every third-party name, attribute and
  keyword argument used by the code exists in the installed dependency versions.
- `CHANGELOG.md`.

### Changed
- Supported Python lowered from 3.13+ to **3.10+**. On Python 3.10 the resolver selects
  astropy 6.1.x and numpy 2.2.x, since astropy 7.x and numpy 2.3+ need Python 3.11.
- Packages the code imports directly are now declared as direct dependencies instead of being
  installed only as dependencies of other packages: `numpy`, `httpx`, `pydantic`, `pyyaml`,
  `tenacity`.
- Minimum versions: `astropy>=6.1` (was 7.2), `astroquery>=0.4.10` (was 0.4),
  `httpx>=0.28.1` and `pydantic>=2.11.7` (the floors fastmcp 2.14.2 already requires).
- The `docs` dependency group is limited to Python 3.12+ (Sphinx 9 needs it); docs are only
  built on 3.13.
- The existing live-service test scripts are marked `network` and skipped by default
  (`uv run pytest -m network` runs them).

### Fixed
- `retry.py` and `http_client.py` could not be imported because `tenacity` was never installed.
- Serializing array-valued Quantities and numpy arrays no longer fails (`float()`/`.item()` on
  arrays raised an error).

## [0.1.0] - 2026-09-28

Initial public release under NASA IMPACT: dynamic astroquery MCP server, ADS compact tools,
Sphinx documentation site and GitHub wiki generated from tool docstrings.

[Unreleased]: https://github.com/NASA-IMPACT/astroquery-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/NASA-IMPACT/astroquery-mcp/releases/tag/v0.1.0
