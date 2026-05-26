#!/bin/bash

# Format and linting
echo "Running formatter..."
uv run ruff format rencal/ tests/
echo ""

echo "Running linter with auto fix..."
uv run ruff check --fix rencal/ tests/
echo ""

# Type checking
echo "Running type checker..."
uv run basedpyright --warnings
echo ""

# Tests
echo "Running tests verbose output..."
uv run pytest tests/ -v
