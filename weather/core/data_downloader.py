from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import cdsapi
import certifi
import xarray as xr

from weather.utils.constants import (
    AREA_BOUNDING_BOX_COORDINATES,
    CALIBRATION_YEARS,
    CDS_API_KEY,
    CDS_API_URL,
    DOWNLOAD_DATA_DIR,
    ERA5_DATASET,
    ERA5_PRODUCT_TYPE,
    ERA_VARIABLES,
)
from weather.utils.logger import get_logger

logger = get_logger(__name__)


class DataDownloader(ABC):
    """Abstract base class for data downloaders."""

    def __init__(self, output_dir: str = DOWNLOAD_DATA_DIR):
        self.output_dir = Path(output_dir)
        self.logger = get_logger(self.__class__.__name__)

    def _setup_output_directory(self, stem: str | None = None) -> None:
        """Create output directory if it doesn't exist."""
        self.output_dir = self.output_dir / stem if stem else self.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Data will be saved to: {self.output_dir}")

    @abstractmethod
    def download(self, *args: Any, **kwargs: Any) -> None:
        """Abstract method for downloading data."""
        pass


class ERA5DataDownloader(DataDownloader):
    """Downloader for ERA5 reanalysis data from Copernicus Climate Data Store."""

    def __init__(
        self,
        output_dir: str = DOWNLOAD_DATA_DIR,
        api_key: str | None = None,
    ):
        super().__init__(output_dir)
        self.api_key = api_key or CDS_API_KEY
        self.api_url = CDS_API_URL
        self._client = None

    @property
    def client(self) -> cdsapi.Client:
        """Lazy initialization of CDS API client."""
        if self._client is None:
            if not self.api_key:
                self.logger.error("CDS API key not found in environment variables.")
                raise ValueError("Provide your Copernicus CDS API key string.")

            self._client = cdsapi.Client(
                url=self.api_url,
                key=self.api_key,
                verify=certifi.where(),
            )
        return self._client

    def download_era5(self, years: list[int] = CALIBRATION_YEARS) -> None:
        """Download ERA5 data for specified years.

        Args:
            years: List of years to download data for
        """
        self._setup_output_directory(stem="era5")

        for year in years:
            file_path = self.output_dir / f"{year}.nc"

            if file_path.exists():
                self.logger.info(f"File already exists for {year}, verifying timestamps...")
            else:
                self._download_year(year, str(file_path))

            self._verify_and_update_metadata(year, str(file_path))

        self.logger.info("Completed all downloads and verifications.")

    def _download_year(self, year: int, file_path: str) -> None:
        """Download ERA5 data for a specific year."""
        self.logger.info(f"Downloading ERA5 data for {year}...")

        request = {
            "product_type": ERA5_PRODUCT_TYPE,
            "variable": ERA_VARIABLES,
            "year": str(year),
            "month": [f"{m:02d}" for m in range(1, 13)],
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(24)],
            "format": "netcdf",
            "area": AREA_BOUNDING_BOX_COORDINATES,
        }

        try:
            result = self.client.retrieve(ERA5_DATASET, request)
            result.download(target=file_path)
            self.logger.info(f"Download complete: {file_path}")
        except Exception as e:
            self.logger.error(f"Error downloading {year}: {e}")
            raise

    def _verify_and_update_metadata(self, year: int, file_path: str) -> None:
        """Verify downloaded file and update metadata."""
        try:
            ds = xr.open_dataset(file_path)

            datetime_coord = self._find_datetime_coordinate(ds)
            if not datetime_coord:
                self.logger.error(f"No datetime-like coordinate found in {file_path}.")
                raise KeyError("No datetime-like coordinate found (expected 'time' or similar).")

            self.logger.info(
                f"{year}.nc date range: {ds[datetime_coord].values[0]}  →  {ds[datetime_coord].values[-1]}"
            )

            # Add metadata note
            ds.attrs["time_reference"] = f"Coordinate '{datetime_coord}' is already in UTC (GMT)."

            # Overwrite file safely
            ds.load()
            ds.close()
            ds.to_netcdf(file_path, mode="w")
            self.logger.info(f"File verified and metadata updated: {file_path}")

        except Exception as e:
            self.logger.error(f"Error verifying {year}: {e}")
            raise

    def _find_datetime_coordinate(self, ds: xr.Dataset) -> str | None:
        """Find the datetime coordinate in the dataset."""
        for coord in ds.coords:
            coord_str = str(coord)
            if "time" in coord_str.lower() or "date" in coord_str.lower():
                return coord_str
        return None

    def download(self, years: list[int] = CALIBRATION_YEARS) -> None:
        """Download ERA5 data (implementation of abstract method)."""
        self.download_era5(years)


class DownloadManager:
    """Main weather data downloader with support for multiple data sources."""

    def __init__(self, output_dir: str = DOWNLOAD_DATA_DIR):
        self.era5 = ERA5DataDownloader(output_dir)

    def download_era5(self, years: list[int] = CALIBRATION_YEARS) -> None:
        """Download ERA5 data."""
        self.era5.download(years)
