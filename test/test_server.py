"""Offline tests for the MCP tool registry and tool-level behavior."""

import asyncio

import pytest

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


def test_mast_query_region_is_truncated(monkeypatch):
    rows = [{"obsid": i} for i in range(50)]

    def fake_execute(module_name, function_name, params):
        return {
            "success": True,
            "module": module_name,
            "function": function_name,
            "params": params,
            "result": {"columns": [], "data": rows, "meta": {}, "row_count": 50},
        }

    monkeypatch.setattr(server, "execute_function", fake_execute)
    result = server.astroquery_execute.fn("mast", "query_region", {}, max_rows=5)["result"]
    assert len(result["data"]) == 5
    assert result["total_rows"] == 50
    assert result["truncated"] is True
