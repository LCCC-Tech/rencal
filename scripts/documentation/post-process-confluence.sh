#!/usr/bin/env bash
set -euo pipefail

uv run python scripts/documentation/format_confluence_markdown.py \
  docs/build/markdown/autoapi \
  docs/build/confluence \
  --clean
