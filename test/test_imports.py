"""Every first-party module must import with only the declared dependencies installed."""

import importlib

import pytest

MODULES = [
    "ads_tools",
    "auth",
    "config",
    "errors",
    "executor",
    "http_client",
    "introspection",
    "main",
    "retry",
    "server",
    "models",
    "models.errors",
    "models.results",
    "utils",
    "utils.async_utils",
    "utils.coord_utils",
    "utils.table_utils",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    importlib.import_module(name)
