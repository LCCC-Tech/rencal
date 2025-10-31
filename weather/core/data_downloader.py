from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import cdsapi
import certifi
import xarray as xr

from weather.utils.types import ParsedURL
from weather.utils.constants import (
    AREA_BOUNDING_BOX_COORDINATES,
    CALIBRATION_YEARS,
    CDS_API_KEY,
    CDS_API_URL,
    CFD_BMU_CSV_URL,
    CFD_DATA_FILE_NAME,
    CFD_REGISTER_API_URL,
    CFD_WIND_TECHNOLOGIES,
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

    def _update_output_directory(self, stem: str | None = None) -> None:
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

        self._update_output_directory(stem="era5")

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
        """Download ERA5 data for specified years.

        Args:
            years: List of years to download data for
        """
        for year in years:
            file_path = self.output_dir / f"{year}.nc"

            if file_path.exists():
                self.logger.info(f"File already exists for {year}, verifying timestamps...")
            else:
                self._download_year(year, str(file_path))

            self._verify_and_update_metadata(year, str(file_path))

        self.logger.info("ERA5 data saved and verified.")

class CfDDataDownloader(DataDownloader):
    def __init__(self, output_dir: str = DOWNLOAD_DATA_DIR):
        super().__init__(output_dir)
        self._cfd_register_api_url = ParsedURL(CFD_REGISTER_API_URL)
        self._cfd_to_bmu_csv_url = ParsedURL(CFD_BMU_CSV_URL)

        self._update_output_directory(stem="cfd")

    def _download_cfd_bmu_csv(self) -> pd.DataFrame:
        """Download the CfD to BMU mapping CSV from the LCCC data portal."""
        try:
            self.logger.info(f"Reading CfD to BMU mapping CSV from {self._cfd_to_bmu_csv_url.domain}...")
            bmu_mapping = pd.read_csv(self._cfd_to_bmu_csv_url.url)
            bmu_mapping = bmu_mapping.filter(["CFD_Id", "BMU_Id"])
            self.logger.info("Loaded CSV into dataframe memory.")
            return bmu_mapping
        except Exception as e:
            self.logger.error(f"Error downloading CfD to BMU CSV from {self._cfd_to_bmu_csv_url.domain}: {e}")
            raise

    def _download_cfd_register(self) -> pd.DataFrame:
        """Download CfD register data from the LCCC API."""
        try:
            self.logger.info(f"Fetching CfD register data from {self._cfd_register_api_url.url}...")
            res = requests.get(CFD_REGISTER_API_URL)
            if res.status_code != 200:
                raise Exception(f"Failed to fetch data: {res.status_code}: {res.text}")

            data = res.json()
            df = pd.DataFrame(data)
            self.logger.info(f"Loaded {len(df)} records into dataframe memory.")

            # Filter for wind technologies and transform - no copy needed
            tech_mask = df["technology_type"].isin(CFD_WIND_TECHNOLOGIES)
            cfd_df = df.loc[tech_mask, ["contract_id", "latitude", "longitude", "technology_type", "current_installed_capacity"]].rename(columns= {
                "contract_id": "CFD_Id",
                "latitude": "Latitude",
                "longitude": "Longitude",
                "technology_type": "Technology",
                "current_installed_capacity": "Maximum Capacity"
            })

            return cfd_df

        except Exception as e:
            self.logger.error(f"Error downloading CfD register data: {e}")
            raise

    def download(self) -> None:
        """Download CfD data"""
        if (self.output_dir / "cfd_with_bmu.csv").exists():
            self.logger.info("CfD data with BMU mapping already exists, skipping download.")

        else:
            self.logger.info("Downloading CfD data with BMU mapping...")
            bmu_mapping = self._download_cfd_bmu_csv()
            cfd_register = self._download_cfd_register()
            cfd_df = cfd_register.merge(bmu_mapping, on="CFD_Id", how="inner")
            cfd_df.to_csv(self.output_dir / CFD_DATA_FILE_NAME, index=False)
            self.logger.info(f"CfD data with BMU mapping saved to {self.output_dir / CFD_DATA_FILE_NAME}")


class DownloadManager:
    """Main weather data downloader with support for multiple data sources."""

    def __init__(self, output_dir: str = DOWNLOAD_DATA_DIR):
        self.era5 = ERA5DataDownloader(output_dir)
        self.cfd = CfDDataDownloader(output_dir)

    def download_era5(self, years: list[int] = CALIBRATION_YEARS) -> None:
        """Download ERA5 data."""
        self.era5.download(years)

    def download_cfd(self) -> None:
        """Download CfD data."""
        self.cfd.download()
