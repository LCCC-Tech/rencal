"""Sphinx configuration for the generated RenCal API documentation."""

import sys
from pathlib import Path

project = "RenCal"
copyright = "Low Carbon Contracts Company Ltd"

sys.path.insert(0, str(Path("../../").resolve()))

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "autoapi.extension",
    "sphinx_markdown_builder",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "build"]
html_theme = "sphinx_rtd_theme"

autoapi_dirs = ["../../rencal"]
autoapi_root = "autoapi"
autoapi_options = [
    "members",
    "undoc-members",
    "show-inheritance",
    "show-module-summary",
    "imported-members",
]
autoapi_add_toctree_entry = False
autoapi_keep_files = False
autoapi_python_use_implicit_namespaces = True
