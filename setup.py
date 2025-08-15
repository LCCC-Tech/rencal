"""
Setup script for weather-lccc package.
"""

from setuptools import setup, find_packages

# This setup.py is kept for compatibility with older tools
# The main configuration is in pyproject.toml

setup(
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
)