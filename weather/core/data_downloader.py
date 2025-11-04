from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

import cdsapi
import certifi
import pandas as pd
import requests
import xarray as xr

from weather.utils.constants import (
    AREA_BOUNDING_BOX_COORDINATES,
    CALIBRATION_END_DATE,
    CALIBRATION_START_YEAR,
    CALIBRATION_START_DATE,
    CDS_API_KEY,
    CDS_API_URL,
    CFD_BMU_CSV_URL,
    CFD_DATA_FILE_NAME,
    CFD_REGISTER_API_URL,
    CFD_WIND_TECHNOLOGIES,
    DOWNLOAD_DATA_DIR,
    ELEXON_API_URL,
    ERA5_DATASET,
    ERA5_PRODUCT_TYPE,
    ERA_VARIABLES,
)
from weather.utils.logger import get_logger
from weather.utils.types import ParsedURL

logger = get_logger(__name__)


class DataDownloader(ABC):
    """Abstract base class for data downloaders."""

    def __init__(self):
        self.output_dir = Path(DOWNLOAD_DATA_DIR)
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

    def __init__(self):
        super().__init__()
        self._api_key = CDS_API_KEY
        self._api = ParsedURL(CDS_API_URL)
        self._client = None

        self._update_output_directory(stem="era5")

    def _extract_calibration_years(self) -> list[int]:
        """Extract years from calibration start and end dates."""
        try:
            start_date = datetime.fromisoformat(CALIBRATION_START_DATE_UTC.replace("Z", "+00:00"))
            end_date = datetime.fromisoformat(CALIBRATION_END_DATE_UTC.replace("Z", "+00:00"))

            start_year = start_date.year
            end_year = end_date.year

            # Generate list of years from start to end (inclusive)
            years = list(range(start_year, end_year + 1))
            self.logger.info(f"Extracted calibration years from date range: {years}")
            return years
        except Exception as e:
            self.logger.error(f"Error extracting calibration years: {e}")
            raise

    @property
    def client(self) -> cdsapi.Client:
        """Lazy initialization of CDS API client."""
        try:
            self.logger.info(f"Initializing CDS API client for {self._api.domain}...")
            if self._client is None:
                if not self._api_key:
                    self.logger.error("CDS API key not found in environment variables.")
                    raise ValueError("Provide your Copernicus CDS API key string.")

                self._client = cdsapi.Client(
                    url=self._api.url,
                    key=self._api_key,
                    verify=certifi.where(),
                )
            return self._client
        except Exception as e:
            self.logger.error(f"Error initializing CDS API client: {e}")
            raise

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

    def download(self) -> None:
        """Download ERA5 data for specified years.

        Args:
            years: List of years to download data for. If None, extracts from calibration dates.
        """
        years = self._extract_calibration_years()

        for year in years:
            file_path = self.output_dir / f"{year}.nc"

            if file_path.exists():
                self.logger.info(f"File already exists for {year}, verifying timestamps...")
            else:
                self._download_year(year, str(file_path))

            self._verify_and_update_metadata(year, str(file_path))

        self.logger.info("ERA5 data saved and verified.")


class CfDDataDownloader(DataDownloader):
    def __init__(self):
        super().__init__()
        self._cfd_register_api = ParsedURL(CFD_REGISTER_API_URL)
        self._cfd_to_bmu_api = ParsedURL(CFD_BMU_CSV_URL)

        self._update_output_directory(stem="cfd")

    def _download_cfd_bmu_csv(self) -> pd.DataFrame:
        """Download the CfD to BMU mapping CSV from the LCCC data portal."""
        try:
            self.logger.info(
                f"Reading CfD to BMU mapping CSV from {self._cfd_to_bmu_api.domain}..."
            )
            bmu_mapping = pd.read_csv(self._cfd_to_bmu_api.url)
            bmu_mapping = bmu_mapping.filter(["CFD_Id", "BMU_Id"])
            self.logger.info("Loaded CSV into dataframe memory.")
            return bmu_mapping
        except Exception as e:
            self.logger.error(
                f"Error downloading CfD to BMU CSV from {self._cfd_to_bmu_api.domain}: {e}"
            )
            raise

    def _download_cfd_register(self) -> pd.DataFrame:
        """Download CfD register data from the LCCC API."""
        try:
            self.logger.info(f"Fetching CfD register data from {self._cfd_register_api.url}...")
            res = requests.get(self._cfd_register_api.url)
            if res.status_code != 200:
                raise Exception(f"Failed to fetch data: {res.status_code}: {res.text}")

            data = res.json()
            df = pd.DataFrame(data)
            self.logger.info(f"Loaded {len(df)} records into dataframe memory.")

            # Filter for wind technologies and transform - no copy needed
            tech_mask = df["technology_type"].isin(CFD_WIND_TECHNOLOGIES)
            cfd_df = df.loc[
                tech_mask,
                [
                    "contract_id",
                    "latitude",
                    "longitude",
                    "technology_type",
                    "current_installed_capacity",
                ],
            ].rename(
                columns={
                    "contract_id": "CFD_Id",
                    "latitude": "Latitude",
                    "longitude": "Longitude",
                    "technology_type": "Technology",
                    "current_installed_capacity": "Maximum Capacity",
                }
            )

            return cfd_df

        except Exception as e:
            self.logger.error(f"Error downloading CfD register data: {e}")
            raise

    def download(self) -> None:
        """Download CfD data"""
        if (self.output_dir / "cfd_with_bmu.csv").exists():
            self.logger.info("Skipping downloading existing CfD data with BMU mapping...")

        else:
            self.logger.info("Downloading CfD data with BMU mapping...")
            bmu_mapping = self._download_cfd_bmu_csv()
            cfd_register = self._download_cfd_register()
            cfd_df = cfd_register.merge(bmu_mapping, on="CFD_Id", how="inner")
            cfd_df.to_csv(self.output_dir / CFD_DATA_FILE_NAME, index=False)
            self.logger.info(
                f"CfD data with BMU mapping saved to {self.output_dir / CFD_DATA_FILE_NAME}"
            )


class GenerationDataDownloader(DataDownloader):
    def __init__(self):
        super().__init__()
        self._api = ParsedURL(ELEXON_API_URL)
        self.bmu_ids: list[str] = self._get_bmu_ids()

        self._update_output_directory(stem="generation")

    def _get_bmu_ids(self) -> list[str]:
        """Get BMU IDs from CfD data."""
        cfd_data_path = self.output_dir / "cfd" / CFD_DATA_FILE_NAME
        if not cfd_data_path.exists():
            self.logger.error(
                f"CfD data file not found at {cfd_data_path}. Please download CfD data first."
            )
            raise FileNotFoundError(f"CfD data file not found at {cfd_data_path}.")

        cfd_df = pd.read_csv(cfd_data_path)
        bmu_ids = cfd_df["BMU_Id"].unique().tolist()
        return bmu_ids

    def _download_generation_data(self) -> pd.DataFrame:
        """Download CfD register data from the LCCC API."""
        try:
            self.logger.info(
                f"Fetching settled Elexon generation data from {self._api.url}..."
            )

            params = {
                "from": CALIBRATION_START_DATE,
                "to": CALIBRATION_END_DATE,
                "bmUnit": self.bmu_ids,
                "format": "json",
            }

            res = requests.get(self._api.url, params=params, timeout=60)
            if res.status_code != 200:
                raise Exception(f"Failed to fetch data: {res.status_code}: {res.text}")

            data = res.json()
            data = data if isinstance(data, list) else data.get("data", [])
            df = pd.DataFrame(data).loc[
                :, ["settlementDate", "settlementPeriod", "bmUnit", "quantity"]
            ]
            self.logger.info(f"Loaded {len(df)} records into dataframe memory.")
            return df

        except Exception as e:
            self.logger.error(f"Error downloading generation data: {e}")
            raise

    def download(self) -> None:
        """Download generation data."""
        output_file = self.output_dir / "generation_data.csv"
        if output_file.exists():
            self.logger.info("Generation data already exists, skipping download...")
            return

        self.logger.info("Downloading generation data...")
        df = self._download_generation_data()
        df.to_csv(output_file, index=False)
        self.logger.info(f"Generation data saved to {output_file}")


class DownloadManager:
    """Main weather data downloader with support for multiple data sources."""

    def __init__(self):
        self.cfd = CfDDataDownloader()
        self.generation = GenerationDataDownloader()
        self.era5 = ERA5DataDownloader()

    def download_cfd(self) -> None:
        """Download CfD data."""
        self.cfd.download()

    def download_generation_data(self) -> None:
        """Download generation data."""
        self.generation.download()

    def download_era5(self) -> None:
        """Download ERA5 data."""
        self.era5.download()

