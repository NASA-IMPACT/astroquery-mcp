"""Offline tests for configuration loading."""

from config import load_config


def test_defaults_without_file(monkeypatch):
    monkeypatch.delenv("ASTROQUERY_MCP_CONFIG", raising=False)
    config = load_config()
    assert config.auth["ads"].token_env == "API_DEV_KEY"
    assert config.defaults.timeout == 60


def test_yaml_file_deep_merges_into_defaults(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("defaults:\n  timeout: 5\n  pagination:\n    max_rows: 50\n")
    config = load_config(path)
    assert config.defaults.timeout == 5
    assert config.defaults.pagination.max_rows == 50
    # Untouched siblings keep their defaults
    assert config.defaults.max_retries == 3
    assert config.defaults.pagination.ads_rows_per_page == 100


def test_env_var_selects_config_file(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("simbad:\n  row_limit: 7\n")
    monkeypatch.setenv("ASTROQUERY_MCP_CONFIG", str(path))
    assert load_config().simbad.row_limit == 7


def test_missing_file_falls_back_to_defaults(tmp_path):
    assert load_config(tmp_path / "nope.yaml").simbad.row_limit == 100
