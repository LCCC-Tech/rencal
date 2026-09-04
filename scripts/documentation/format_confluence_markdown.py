#!/usr/bin/env python3
"""Convert Sphinx AutoAPI Markdown into stable Confluence-ready pages."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

GENERATED_NOTICE = "<!-- This page is generated from RenCal Python source. -->"
ANCHOR_RE = re.compile(r"<a\s+(?:id|name)=[\"'][^\"']+[\"']\s*></a>", re.IGNORECASE)
LINK_RE = re.compile(r"(]\()([^)#]+)(#[^)]*)?(\))")


def _module_name(root: Path, page: Path) -> str:
    """Return the dotted module represented by an AutoAPI page."""
    relative = page.relative_to(root)
    parts = list(relative.parts)
    if parts[-1] == "index.md":
        parts = parts[:-1]
    else:
        parts[-1] = Path(parts[-1]).stem
    return ".".join(parts)


def _output_path(module: str) -> Path:
    """Return the flat, stable filename for a dotted module."""
    return Path(f"{module}.md")


def _title(module: str) -> str:
    return module


def _clean_markdown(content: str, title: str) -> str:
    content = ANCHOR_RE.sub("", content)
    content = re.sub(r"\s*{#[-\w]+}", "", content)
    lines = content.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and re.match(r"^#\s+", lines[0]):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    body = "\n".join(lines).rstrip()
    return f"{GENERATED_NOTICE}\n\n# {title}\n\n{body}\n"


def _rewrite_links(content: str, source: Path, mapping: dict[Path, Path]) -> str:
    def replace(match: re.Match[str]) -> str:
        target = match.group(2)
        if target.startswith(("http://", "https://", "mailto:", "#")):
            return match.group(0)
        resolved = (source.parent / target).resolve()
        destination = mapping.get(resolved)
        if destination is None:
            return match.group(0)
        return f"]({destination.name})"

    return LINK_RE.sub(replace, content)


def convert(
    input_dir: Path, output_dir: Path, *, clean: bool = False, verbose: bool = False
) -> int:
    """Convert all AutoAPI Markdown pages and return the number processed."""
    if not input_dir.is_dir():
        raise FileNotFoundError(f"AutoAPI directory does not exist: {input_dir}")
    pages = sorted(input_dir.rglob("*.md"))
    if not pages:
        raise FileNotFoundError(f"No AutoAPI Markdown pages found in {input_dir}")
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        page.resolve(): (output_dir / _output_path(_module_name(input_dir, page))).resolve()
        for page in pages
    }
    for page in pages:
        module = _module_name(input_dir, page)
        output = mapping[page.resolve()]
        content = _rewrite_links(page.read_text(encoding="utf-8"), page, mapping)
        output.write_text(_clean_markdown(content, _title(module)), encoding="utf-8")
        if verbose:
            print(f"{page} -> {output}")
    return len(pages)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    count = convert(args.input_dir, args.output_dir, clean=args.clean, verbose=args.verbose)
    print(f"Converted {count} AutoAPI Markdown page(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
