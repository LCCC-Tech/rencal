import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_release_please_manifest_is_ready_for_initial_release() -> None:
    with (ROOT / "pyproject.toml").open("rb") as file:
        project_version = tomllib.load(file)["project"]["version"]
    with (ROOT / ".release-please-manifest.json").open(encoding="utf-8") as file:
        manifest = json.load(file)

    assert project_version == "0.0.0"
    assert manifest == {}


def test_uv_lock_marks_project_version_for_release_please() -> None:
    lockfile = (ROOT / "uv.lock").read_text(encoding="utf-8")
    with (ROOT / "pyproject.toml").open("rb") as file:
        project_version = tomllib.load(file)["project"]["version"]
    match = re.search(
        r'\[\[package\]\]\nname = "rencal"\n'
        r'version = "([^"]+)" # x-release-please-version',
        lockfile,
    )

    assert match is not None
    assert match.group(1) == project_version


def test_release_please_is_configured_for_python_package() -> None:
    with (ROOT / "release-please-config.json").open(encoding="utf-8") as file:
        config = json.load(file)

    package = config["packages"]["."]
    assert config["release-type"] == "python"
    assert config["include-component-in-tag"] is False
    assert config["include-v-in-tag"] is True
    assert package["package-name"] == "rencal"
    assert package["initial-version"] == "0.1.0"
    assert "uv.lock" in package["extra-files"]
    assert len(config["bootstrap-sha"]) == 40
