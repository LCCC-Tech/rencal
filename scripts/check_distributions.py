"""Validate the contents of RenCal wheel and source distributions."""

from __future__ import annotations

import argparse
import email
import tarfile
import zipfile
from pathlib import Path


def archive_names(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    with tarfile.open(path, "r:gz") as archive:
        return archive.getnames()


def metadata(artifact: Path) -> email.message.Message:
    if artifact.suffix == ".whl":
        with zipfile.ZipFile(artifact) as archive:
            metadata_name = next(
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            )
            return email.message_from_bytes(archive.read(metadata_name))
    with tarfile.open(artifact, "r:gz") as archive:
        metadata_member = next(
            member for member in archive.getmembers() if member.name.endswith("/PKG-INFO")
        )
        extracted = archive.extractfile(metadata_member)
        assert extracted is not None
        return email.message_from_binary_file(extracted)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version")
    args = parser.parse_args()
    artifacts = list(Path("dist").glob("rencal-*"))
    assert len(artifacts) == 2, artifacts
    assert sum(path.suffix == ".whl" for path in artifacts) == 1
    assert sum(path.name.endswith(".tar.gz") for path in artifacts) == 1

    for artifact in artifacts:
        names = archive_names(artifact)
        assert any(name.endswith("LICENSE") for name in names), artifact
        assert not any("tests/data" in name for name in names), artifact
        artifact_metadata = metadata(artifact)
        assert artifact_metadata["Name"] == "rencal", artifact
        if args.version:
            assert artifact_metadata["Version"] == args.version, artifact


if __name__ == "__main__":
    main()
