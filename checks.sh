#!/bin/bash

# Format and linting
echo "Running formatter..."
uv run ruff format weather/ tests/
echo ""

echo "Running linter with auto fix..."
uv run ruff check --fix weather/ tests/
echo ""

# Type checking
echo "Running type checker..."
uv run basedpyright --warnings
echo ""

# Tests
echo "Running tests verbose output..."
uv run pytest tests/ -v
