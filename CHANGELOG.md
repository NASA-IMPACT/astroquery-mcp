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

## [0.1.0] - 2026-09-28

Initial public release under NASA IMPACT: dynamic astroquery MCP server, ADS compact tools,
Sphinx documentation site and GitHub wiki generated from tool docstrings.

[Unreleased]: https://github.com/NASA-IMPACT/astroquery-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/NASA-IMPACT/astroquery-mcp/releases/tag/v0.1.0
