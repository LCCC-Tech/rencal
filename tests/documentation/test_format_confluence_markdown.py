from pathlib import Path

import pytest

from scripts.documentation.format_confluence_markdown import (
    _module_name,
    _output_path,
    convert,
)


def test_module_name_and_output_path() -> None:
    root = Path("/tmp/autoapi")
    page = root / "rencal" / "core" / "index.md"

    assert _module_name(root, page) == "rencal.core"
    assert _output_path("rencal.core") == Path("rencal.core.md")


def test_convert_cleans_headings_anchors_and_rewrites_links(tmp_path: Path) -> None:
    source = tmp_path / "autoapi"
    output = tmp_path / "confluence"
    package = source / "rencal"
    package.mkdir(parents=True)
    (package / "index.md").write_text(
        '# rencal\n\n<a id="rencal"></a>\n\nSee [core](core/index.md).\n',
        encoding="utf-8",
    )
    core = package / "core"
    core.mkdir()
    (core / "index.md").write_text("# core\n\n## API {#api}\n", encoding="utf-8")

    assert convert(source, output, clean=True) == 2
    root_page = (output / "rencal.md").read_text(encoding="utf-8")
    core_page = (output / "rencal.core.md").read_text(encoding="utf-8")

    assert "# rencal" in root_page
    assert "<a id=" not in root_page
    assert "[core](rencal.core.md)" in root_page
    assert "{#api}" not in core_page
    assert "generated from RenCal Python source" in core_page


def test_convert_processes_nested_pages(tmp_path: Path) -> None:
    source = tmp_path / "autoapi" / "rencal" / "models"
    source.mkdir(parents=True)
    (source / "plant_model.md").write_text("Plant model\n", encoding="utf-8")
    output = tmp_path / "confluence"

    assert convert(tmp_path / "autoapi", output) == 1
    assert (output / "rencal.models.plant_model.md").exists()


def test_convert_fails_when_no_autoapi_pages_exist(tmp_path: Path) -> None:
    source = tmp_path / "empty"
    source.mkdir()

    with pytest.raises(FileNotFoundError, match="No AutoAPI Markdown"):
        convert(source, tmp_path / "output")
