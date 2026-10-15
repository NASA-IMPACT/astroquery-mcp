"""Shared fixtures."""

import pytest

import artifacts


@pytest.fixture(autouse=True)
def artifact_store(tmp_path, monkeypatch):
    """Point the artifact store at a temp dir so tests never write to the user cache."""
    root = tmp_path / "artifact-store"
    monkeypatch.setenv("ASTROQUERY_MCP_ARTIFACT_DIR", str(root))
    monkeypatch.setattr(artifacts, "_store", None)
    return root
