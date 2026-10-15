"""Offline tests for token lookup and auth diagnostics."""

import logging

import pytest

import auth
from models.errors import ErrorCode, MCPError

TOKEN_VARS = ("API_DEV_KEY", "ADS_API_KEY", "MAST_TOKEN")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in TOKEN_VARS:
        monkeypatch.delenv(var, raising=False)


def test_get_token_reads_configured_env_var(monkeypatch):
    monkeypatch.setenv("API_DEV_KEY", "ads-token")
    assert auth.get_token("ads") == "ads-token"


def test_get_token_falls_back_to_ads_api_key(monkeypatch):
    monkeypatch.setenv("ADS_API_KEY", "fallback-token")
    assert auth.get_token("ads") == "fallback-token"


def test_get_token_unknown_service_returns_none():
    assert auth.get_token("not-a-service") is None


def test_require_token_raises_when_missing():
    with pytest.raises(MCPError) as exc:
        auth.require_token("ads")
    assert exc.value.code == ErrorCode.AUTHENTICATION_ERROR
    assert exc.value.details["env_var"] == "API_DEV_KEY"


def test_check_auth_status_reports_without_values(monkeypatch):
    monkeypatch.setenv("API_DEV_KEY", "ads-token")
    status = auth.check_auth_status()
    assert status["ads"] == {"configured": True, "env_var": "API_DEV_KEY", "required": True}
    assert status["mast"]["configured"] is False
    assert "ads-token" not in repr(status)


def test_logs_never_contain_secret_values(monkeypatch, caplog):
    other_secret = "zq9xk2-other-secret"
    ads_secret = "wv7jm4-ads-secret"
    monkeypatch.setenv("API_OTHER_SECRET", other_secret)

    with caplog.at_level(logging.DEBUG):
        auth.get_token("ads")  # missing-token path lists API*/ADS* env vars
        monkeypatch.setenv("API_DEV_KEY", ads_secret)
        auth.configure_astroquery_auth()

    assert "API_OTHER_SECRET" in caplog.text
    for secret in (other_secret, ads_secret):
        assert secret[:4] not in caplog.text
