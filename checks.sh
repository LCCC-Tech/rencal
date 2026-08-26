#!/bin/bash

# Format and linting
echo "Running formatter..."
uv run ruff format --check rencal/ tests/ scripts/
echo ""

echo "Running linter with auto fix..."
uv run ruff check rencal/ tests/ scripts/
echo ""

# Type checking
echo "Running type checker..."
uv run basedpyright --warnings
echo ""

# Tests
echo "Running tests verbose output..."
uv run pytest tests/ -v
