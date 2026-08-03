"""Unit tests for ERA5DataDownloader authentication behavior."""

import pytest

from rencal.core.data_downloader import ERA5DataDownloader


def test_era5_client_requires_api_key_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ERA5 client initialization fails without an API key."""
    monkeypatch.delenv("CDS_API_KEY", raising=False)

    downloader = ERA5DataDownloader(api_key=None)

    with pytest.raises(ValueError, match="CDS API key missing"):
        _ = downloader.client
