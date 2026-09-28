"""Sphinx configuration. Reference pages are generated from source on every build."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Set by the release workflow (tag name); Read the Docs sets READTHEDOCS_VERSION_NAME.
version = release = os.environ.get("DOCS_VERSION") or os.environ.get("READTHEDOCS_VERSION_NAME") or "dev"

subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_docs.py"), "--version", release], check=True)

project = "astroquery-mcp"
author = "NASA IMPACT"
copyright = "NASA IMPACT"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
]

source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
exclude_patterns = ["_build"]

# Upstream docstrings use `single backticks` for objects (astropy convention), e.g. `~astropy.table.Table`.
default_role = "py:obj"

myst_heading_anchors = 3
# GitHub-style slugs (keep underscores) so generated anchors like #query_region work on the site and the wiki.
myst_heading_slug_func = "scripts.gen_docs.github_slug"

autodoc_member_order = "bysource"
napoleon_numpy_docstring = True
napoleon_google_docstring = True
napoleon_preprocess_types = True  # link types like ~astropy.table.Table via intersphinx

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "astropy": ("https://docs.astropy.org/en/stable/", None),
    "astroquery": ("https://astroquery.readthedocs.io/en/latest/", None),
}

# Upstream astroquery docstrings reference labels that only exist in astroquery's own docs.
suppress_warnings = ["ref.ref", "ref.doc", "docutils"]

html_theme = "sphinx_rtd_theme"
html_title = f"astroquery-mcp {release}"
html_theme_options = {"navigation_depth": 3, "collapse_navigation": False, "style_nav_header_background": "#0032A0"}
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_context = {
    "display_github": True,
    "github_user": "NASA-IMPACT",
    "github_repo": "astroquery-mcp",
    "github_version": "main",
    "conf_py_path": "/docs/",
}
