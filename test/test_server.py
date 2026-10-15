"""Offline tests for the MCP tool registry and tool-level behavior."""

import asyncio

import pytest
from astropy.table import Table

import executor
import server

EXPECTED_TOOLS = {
    "astroquery_list_modules",
    "astroquery_list_functions",
    "astroquery_get_function_info",
    "astroquery_check_auth",
    "astroquery_execute",
    "ads_query_compact",
    "ads_get_paper",
}


@pytest.fixture(scope="module")
def registry():
    return asyncio.run(server.mcp.get_tools())


def test_all_tools_registered(registry):
    assert EXPECTED_TOOLS <= set(registry)


def test_tools_are_documented(registry):
    for name in EXPECTED_TOOLS:
        assert registry[name].description, f"{name} has no docstring"


def test_execute_returns_error_dict_instead_of_raising():
    result = server.astroquery_execute.fn("not_a_module", "query_object")
    assert result["error"] is True
    assert result["code"] == "VALIDATION_ERROR"


def test_check_auth_does_not_return_token_values(monkeypatch):
    monkeypatch.setenv("API_DEV_KEY", "SECRET-TOKEN-VALUE")
    result = server.astroquery_check_auth.fn()
    assert result["diagnostics"]["API_DEV_KEY"] == "set"
    assert "SECRET" not in repr(result)


class FakeCatalog:
    @staticmethod
    def query_tap(query):
        return Table({"obsid": list(range(50))})


@pytest.mark.parametrize("module_name", ["mast", "simbad", "vizier"])
def test_every_module_is_truncated_to_max_rows(monkeypatch, module_name):
    monkeypatch.setattr(executor, "get_class_instance", lambda name: FakeCatalog)
    result = server.astroquery_execute.fn(module_name, "query_tap", {"query": "q"}, max_rows=5)["result"]
    assert [row["obsid"] for row in result["data"]] == [0, 1, 2, 3, 4]
    assert result["row_count"] == 5
    assert result["total_rows"] == 50
    assert result["truncated"] is True


def test_default_max_rows_is_20(monkeypatch):
    monkeypatch.setattr(executor, "get_class_instance", lambda name: FakeCatalog)
    result = server.astroquery_execute.fn("simbad", "query_tap", {"query": "q"})["result"]
    assert result["row_count"] == 20


def test_invalid_max_rows_is_a_validation_error():
    result = server.astroquery_execute.fn("simbad", "query_tap", {"query": "q"}, max_rows=0)
    assert result["code"] == "VALIDATION_ERROR"
