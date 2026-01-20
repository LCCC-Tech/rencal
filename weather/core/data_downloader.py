import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

import cdsapi
import certifi
import numpy as np
import pandas as pd
import requests
import xarray as xr
from tqdm import tqdm

from weather.utils.constants import (
    AREA_BOUNDING_BOX_COORDINATES,
    CALIBRATION_END_DATE,
    CALIBRATION_START_DATE,
    CDS_API_KEY,
    CDS_API_URL,
    CFD_BMU_CSV_URL,
    CFD_REGISTER_API_URL,
    DEFAULT_SOLAR_VARIABLES,
    DEFAULT_WIND_VARIABLES,
    DOWNLOAD_DATA_DIR,
    ELEXON_API_URL,
    ERA5_DATASET,
    ERA5_PRODUCT_TYPE,
    GENERATION_DATA_FILE_NAME,
    MARCH_FORWARD_MINUTES,
    NORMAL_DAY_MINUTES,
    OCTOBER_BACK_MINUTES,
    PLANT_DATA_FILE_NAME,
)
from weather.utils.logger import get_logger
from weather.utils.types import ParsedURL

logger = get_logger(__name__)


class DataDownloader(ABC):
    """Abstract base class for data downloaders.

    This class provides a common interface and shared functionality for downloading
    various types of weather and energy data. Concrete implementations should inherit
    from this class and implement the abstract download method.

    Attributes:
        output_dir (Path): Directory where downloaded data will be saved.
        logger: Logger instance for the specific downloader class.
    """

    def __init__(self):
        """Initialize the DataDownloader with output directory and logger."""
        self.output_dir = Path(DOWNLOAD_DATA_DIR)
        self.logger = get_logger(self.__class__.__name__)

    def _update_output_directory(self, stem: str | None = None) -> None:
        """Create and update the output directory path.

        Creates a subdirectory within the main output directory if a stem is provided.
        The directory is created if it doesn't exist, including parent directories.

        Args:
            stem: Optional subdirectory name to append to the output path.
                 If None, uses the current output directory unchanged.
        """
        self.output_dir = self.output_dir / stem if stem else self.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger.debug(f"Data will be saved to: {self.output_dir}")

    @abstractmethod
    def download(self, *args: Any, **kwargs: Any) -> None:
        """Abstract method for downloading data.

        This method must be implemented by subclasses to define specific
        data downloading behavior.

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        pass


class ERA5DataDownloader(DataDownloader):
    """Downloader for ERA5 reanalysis data from Copernicus Climate Data Store.

    Downloads ERA5 weather data for specified years and variables within a defined
    geographical bounding box. The data is retrieved from the Copernicus Climate
    Data Store (CDS) API and saved as NetCDF files.


    Attributes:
        _api_key (str): CDS API key for authentication.
        _api (ParsedURL): Parsed CDS API URL.
        _client (cdsapi.Client): Lazy-initialized CDS API client.
    """

    def __init__(self):
        """Initialize ERA5 data downloader with API configuration."""
        super().__init__()
        self._api_key = CDS_API_KEY
        self._api = ParsedURL(CDS_API_URL)
        self._client = None

        self._update_output_directory(stem="era5")

    def _extract_calibration_years(self) -> list[int]:
        """Extract years from calibration start and end dates.

        Parses the calibration start and end dates from constants and generates
        a list of years covering the entire calibration period (inclusive).

        Returns:
            List of years (integers) from calibration start to end date.

        Raises:
            Exception: If date parsing fails or dates are invalid.
        """
        try:
            start_date = datetime.fromisoformat(CALIBRATION_START_DATE.replace("Z", "+00:00"))
            end_date = datetime.fromisoformat(CALIBRATION_END_DATE.replace("Z", "+00:00"))

            start_year = start_date.year
            end_year = end_date.year

            # Generate list of years from start to end (inclusive)
            years = list(range(start_year, end_year + 1))
            self.logger.debug(f"Extracted calibration years from date range: {years}")
            return years
        except Exception as e:
            self.logger.error(f"Error extracting calibration years: {e}")
            raise

    @property
    def client(self) -> cdsapi.Client:
        """Lazy initialization of CDS API client.

        Creates and returns a CDS API client instance with proper authentication
        and SSL verification. The client is cached after first initialization.

        Returns:
            Authenticated CDS API client instance.

        Raises:
            ValueError: If CDS API key is not provided.
            Exception: If client initialization fails.
        """
        try:
            self.logger.debug(f"Initializing CDS API client for {self._api.domain}...")
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
        """Download ERA5 data for a specific year.

        Downloads hourly ERA5 data for all days and months of the specified year
        within the configured geographical bounding box. Data includes all
        standard wind and solar variables. Due to request size constraints,
        the data is downloaded as two, half yearly requests.

        Args:
            year: Year to download data for.
            file_path: Local file path where the NetCDF data will be saved.

        Raises:
            Exception: If download fails or API request is unsuccessful.
        """
        self.logger.info("Downloading ERA5 data for %s...", year)

        path_filepath = Path(file_path)
        file_path_wind = str(path_filepath.parent / (path_filepath.stem + "_wind" + path_filepath.suffix))
        file_path_solar = str(path_filepath.parent / (path_filepath.stem + "_solar" + path_filepath.suffix))

        request_wind = {
            "product_type": ERA5_PRODUCT_TYPE,
            "variable": DEFAULT_WIND_VARIABLES,
            "year": str(year),
            "month": [f"{m:02d}" for m in range(1, 13)],
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(24)],
            "format": "netcdf_legacy",
            "area": AREA_BOUNDING_BOX_COORDINATES,
        }

        request_solar = {
            "product_type": ERA5_PRODUCT_TYPE,
            "variable": DEFAULT_SOLAR_VARIABLES,
            "year": str(year),
            "month": [f"{m:02d}" for m in range(1, 13)],
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(24)],
            "format": "netcdf_legacy",
            "area": AREA_BOUNDING_BOX_COORDINATES,
        }

        try:
            result_wind = self.client.retrieve(ERA5_DATASET, request_wind)
            result_wind.download(target=file_path_wind)
            self.logger.info("Download complete: %s", file_path_wind)
            result_solar = self.client.retrieve(ERA5_DATASET, request_solar)
            result_solar.download(target=file_path_solar)
            self.logger.info("Download complete: %s", file_path_solar)
        except Exception as e:
            self.logger.error("Error downloading %s: %s", year, e)
            raise

        with xr.open_dataset(file_path_wind) as ds_wind, \
             xr.open_dataset(file_path_solar) as ds_solar:
            merged_vars = xr.merge([ds_wind, ds_solar])
            merged_vars.to_netcdf(path_filepath)
            self.logger.info("Files %s and %s combined into %s", file_path_wind, file_path_solar, file_path)

        for fpath in [file_path_wind, file_path_solar]:
            try:
                os.remove(fpath)
                self.logger.info("Auxiliary file deleted: %s", fpath)
            except Exception as e:
                self.logger.error("Error deleting download artefacts for %s: %s", year, e)
                raise

    def _verify_and_update_metadata(self, year: int, file_path: str) -> None:
        """Verify downloaded file and update metadata.

        Opens the downloaded NetCDF file to verify its contents, checks for
        valid datetime coordinates, logs the date range, and adds metadata
        about timezone information. The file is then re-saved with updated
        metadata.

        Args:
            year: Year of the data file being verified.
            file_path: Path to the NetCDF file to verify and update.

        Raises:
            KeyError: If no datetime-like coordinate is found in the dataset.
            Exception: If file verification or metadata update fails.
        """
        # Progress bar shows which year is being processed
        try:
            ds = xr.open_dataset(file_path)

            datetime_coord = self._find_datetime_coordinate(ds)
            if not datetime_coord:
                self.logger.error(f"No datetime-like coordinate found in {file_path}.")
                raise KeyError("No datetime-like coordinate found (expected 'time' or similar).")

            self.logger.debug(
                f"{year}.nc date range: {ds[datetime_coord].values[0]}  →  {ds[datetime_coord].values[-1]}"
            )

            # Add metadata note
            ds.attrs["time_reference"] = f"Coordinate '{datetime_coord}' is already in UTC (GMT)."

            # Overwrite file safely
            ds.load()
            ds.close()
            ds.to_netcdf(file_path, mode="w")
            self.logger.debug(f"File verified and metadata updated: {file_path}")

        except Exception as e:
            self.logger.error(f"Error verifying {year}: {e}")
            raise

    def _find_datetime_coordinate(self, ds: xr.Dataset) -> str | None:
        """Find the datetime coordinate in the dataset.

        Searches through dataset coordinates to find one that likely represents
        time/date information based on coordinate name patterns.

        Args:
            ds: xarray Dataset to search for datetime coordinates.

        Returns:
            Name of the datetime coordinate if found, None otherwise.
        """
        for coord in ds.coords:
            coord_str = str(coord)
            if "time" in coord_str.lower() or "date" in coord_str.lower():
                return coord_str
        return None

    def download(self) -> None:
        """Download ERA5 data for calibration years.

        Downloads ERA5 reanalysis data for all years within the calibration period.
        If files already exist, they are verified for consistency. Each year's data
        is saved as a separate NetCDF file in the era5 subdirectory.
        """
        years = self._extract_calibration_years()
        existing_files = 0
        downloaded_files = 0

        # Create logger-styled progress bar format
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with tqdm(
            years,
            desc="Processing ERA5 data",
            unit="year",
            bar_format="[INFO] - {desc}: {percentage:3.0f}%|{bar:20}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}] {postfix} - [data_downloader] - "
            + current_time,
        ) as pbar:
            for year in pbar:
                file_path = self.output_dir / f"{year}.nc"
                current_date = datetime.now()
                is_current_year = True if current_date.year == year else False

                if not is_current_year and file_path.exists():
                    pbar.set_postfix_str(f"verifying file for {year}")
                    self.logger.debug(f"File already exist for {year}, verifying timestamps...")
                    existing_files += 1
                else:
                    pbar.set_postfix_str(f"downloading file for {year}")
                    self._download_year(year, str(file_path))
                    downloaded_files += 1

                pbar.set_postfix_str(f"verifying {year}.nc")
                self._verify_and_update_metadata(year, str(file_path))

        total_files = len(years)
        if downloaded_files > 0:
            self.logger.info(
                f"ERA5 data complete: {downloaded_files} downloaded, {existing_files} verified ({total_files} total files)"
            )
        else:
            self.logger.info(f"ERA5 data verified: {total_files} files ({min(years)}-{max(years)})")


class CfDDataDownloader(DataDownloader):
    """Downloader for Contract for Difference (CfD) data from LCCC.

    Downloads CfD register data and BMU (Balancing Mechanism Unit) mapping
    from The Low Carbon Contracts Company (LCCC) data portal. Combines the
    register data with BMU identifiers to create a merged dataset for wind
    technology analysis.

    Attributes:
        _cfd_register_api (ParsedURL): Parsed URL for CfD register API.
        _cfd_to_bmu_api (ParsedURL): Parsed URL for CfD to BMU CSV mapping.
    """

    def __init__(self):
        """Initialize CfD data downloader with API endpoints."""
        super().__init__()
        self._cfd_register_api = ParsedURL(CFD_REGISTER_API_URL)
        self._cfd_to_bmu_api = ParsedURL(CFD_BMU_CSV_URL)

        self._update_output_directory(stem="plant")

    def _download_cfd_bmu_csv(self) -> pd.DataFrame:
        """Download the CfD to BMU mapping CSV from the LCCC data portal.

        Downloads a CSV file containing the mapping between CfD contract IDs
        and BMU (Balancing Mechanism Unit) identifiers. This mapping is
        essential for linking CfD contracts to their operational units.

        Returns:
            DataFrame containing CFD_Id and BMU_Id columns.

        Raises:
            Exception: If CSV download or parsing fails.
        """
        try:
            self.logger.info(
                f"Reading CfD to BMU mapping CSV from {self._cfd_to_bmu_api.domain}..."
            )
            bmu_mapping = pd.read_csv(self._cfd_to_bmu_api.url)
            bmu_mapping.rename(columns={"CFD_Id": "cfd_id", "BMU_Id": "bmu_id"}, inplace=True)
            bmu_mapping = bmu_mapping.filter(["cfd_id", "bmu_id"])
            self.logger.info("Loaded CSV into dataframe memory.")
            return bmu_mapping
        except Exception as e:
            self.logger.error(
                f"Error downloading CfD to BMU CSV from {self._cfd_to_bmu_api.domain}: {e}"
            )
            raise

    def _download_cfd_register(self) -> pd.DataFrame:
        """Download CfD register data from the LCCC API.

        Downloads the complete CfD register from LCCC's REST API and filters
        it for wind technologies only. The returned data includes location
        coordinates, technology type, and capacity information.

        Returns:
            DataFrame with columns: CFD_Id, Latitude, Longitude, Technology,
            Maximum Capacity, filtered for wind technologies.

        Raises:
            Exception: If API request fails or returns invalid data.
        """
        try:
            self.logger.info(f"Fetching CfD register data from {self._cfd_register_api.url}...")
            res = requests.get(self._cfd_register_api.url)
            if res.status_code != 200:
                raise Exception(f"Failed to fetch data: {res.status_code}: {res.text}")

            data = res.json()
            df = pd.DataFrame(data)
            self.logger.info(f"Loaded {len(df)} records into dataframe memory.")

            cfd_df = df.loc[
                :,
                [
                    "contract_id",
                    "latitude",
                    "longitude",
                    "technology_type",
                    "current_installed_capacity",
                ],
            ].rename(
                columns={
                    "contract_id": "cfd_id",
                    "technology_type": "technology",
                    "current_installed_capacity": "capacity",
                }
            )

            return cfd_df

        except Exception as e:
            self.logger.error(f"Error downloading CfD register data: {e}")
            raise

    def download(self) -> None:
        """Download and merge CfD register and BMU mapping data.

        Downloads both the CfD register and BMU mapping datasets, merges them
        on cfd_id, and saves the combined dataset as a CSV file. If the output
        file already exists, the download is skipped.
        """
        if (self.output_dir / PLANT_DATA_FILE_NAME).exists():
            self.logger.debug("Skipping downloading existing CfD data with BMU mapping...")

        else:
            self.logger.info("Downloading CfD data with BMU mapping...")
            bmu_mapping = self._download_cfd_bmu_csv()
            cfd_register = self._download_cfd_register()
            cfd_df = cfd_register.merge(bmu_mapping, on="cfd_id", how="inner")
            cfd_df.to_csv(self.output_dir / PLANT_DATA_FILE_NAME, index=False)
            self.logger.info(
                f"CfD data with BMU mapping saved to {self.output_dir / PLANT_DATA_FILE_NAME}"
            )


class GenerationDataDownloader(DataDownloader):
    """Downloader for electricity generation data from Elexon API.

    Downloads settled generation data from the Elexon Balancing Mechanism
    Reporting Service (BMRS) for BMU units associated with CfD contracts.
    The data covers the calibration period and provides actual generation
    volumes for model validation.

    Attributes:
        _api (ParsedURL): Parsed URL for Elexon API endpoint.
    """

    def __init__(self):
        """Initialize generation data downloader with Elexon API configuration."""
        super().__init__()
        self._api = ParsedURL(ELEXON_API_URL)

    def _get_cfd_plants(self) -> pd.DataFrame:
        """Load CfD plant data with BMU mapping from local CSV file.

        Reads the previously downloaded CfD dataset containing plant
        information and BMU identifiers. This data is used to identify
        which BMU units to download generation data for.

        Returns:
            DataFrame containing CfD plant data with BMU mapping.
        """
        self.logger.info("Loading CfD plant data with BMU mapping...")
        cfd_data_path = self.output_dir / "plant" / PLANT_DATA_FILE_NAME
        if not cfd_data_path.exists():
            self.logger.error(
                f"CfD data file not found at {cfd_data_path}. Please download CfD data first."
            )
            raise FileNotFoundError(f"CfD data file not found at {cfd_data_path}.")

        cfd_df = pd.read_csv(cfd_data_path)
        self.bmu_ids: list[str] = cfd_df["bmu_id"].unique().tolist()
        self.logger.info(f"Found {len(self.bmu_ids)} unique BMU IDs.")

        return cfd_df

    def _download_generation_data(self) -> pd.DataFrame:
        """Download generation data from Elexon API for specified BMU units.

        Retrieves settled generation data for all provided BMU IDs within
        the calibration date range. The API returns settlement periods and
        generation quantities for each BMU unit.

        Args:
            bmu_ids: List of BMU ID strings to download data for.

        Returns:
            DataFrame with columns: settlementDate, settlementPeriod,
            bmUnit, quantity.

        Raises:
            Exception: If API request fails or returns invalid data.
        """
        self.logger.info("Downloading generation data for CfD-associated BMUs...")
        try:
            self.logger.info(f"Fetching settled Elexon generation data from {self._api.url}...")

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

    def _get_day_type_from_period_counts(self, generation_df: pd.DataFrame) -> pd.Series:
        """Determine day type by counting settlement periods per date.

        - 48 periods = Normal day ('n')
        - 46 periods = Short day/March forward ('s')
        - 50 periods = Long day/October back ('l')

        Returns 'n', 's', or 'l' for each row.
        """
        period_counts = generation_df.groupby("settlement_date")["settlement_period"].nunique()

        # Create day type lookup per date using explicit mapping
        date_to_day_type = pd.Series(index=period_counts.index, dtype=str)
        date_to_day_type[period_counts == 48] = "n"
        date_to_day_type[period_counts == 46] = "s"
        date_to_day_type[period_counts == 50] = "l"

        # We shouldn't have any other counts, log unexpected cases
        unexpected_mask = date_to_day_type.isna()
        if unexpected_mask.any():
            unexpected_counts = period_counts[unexpected_mask]
            self.logger.warning(f"Unexpected settlement period counts: {dict(unexpected_counts)}")
            date_to_day_type = date_to_day_type.fillna("n")

        day_type_series = generation_df["settlement_date"].map(
            lambda x: date_to_day_type.get(x, "n")
        )

        return pd.Series(day_type_series, index=generation_df.index, dtype="category")

    def _create_hourly_utc_datetime(self, generation_df: pd.DataFrame) -> pd.Series:
        """Create hourly UTC datetimes from UK settlement periods using Elexon rules.

        Converts UK settlement periods to UTC using official Elexon settlement period
        bmu_mapping. This accounts for daylight saving time changes and ensures
        correct hour alignment.

        Reference: https://www.elexon.co.uk/bsc/settlement/

        Expected outputs based on period counts:
        - 48 periods ('n'): → 24 UTC hours
        - 46 periods ('s'): → 23 UTC hours (periods 3&4 missing)
        - 50 periods ('l'): → 25 UTC hours (periods 3&4 duplicated)

        Args:
            generation_df: DataFrame with settlement_date and settlement_period columns.

        Returns:
            Series of UTC datetime objects floored to hour boundaries.
        """

        # Create working copy with day type from period counts
        df = generation_df.copy()
        df["day_type"] = self._get_day_type_from_period_counts(df)

        # Log day type distribution for debugging
        day_type_counts = df["day_type"].value_counts()
        self.logger.debug(f"Day type distribution: {day_type_counts.to_dict()}")

        # Convert to numpy arrays for vectorized operations
        normal_minuates_array = np.array(NORMAL_DAY_MINUTES)
        short_minutes_array = np.array(MARCH_FORWARD_MINUTES)
        long_minutes_array = np.array(OCTOBER_BACK_MINUTES)

        # Vectorized lookup with proper array bounds for each day type
        minutes_from_midnight = np.zeros(len(df), dtype=int)
        periods_idx = df["settlement_period"] - 1  # Convert to 0-based indexing

        # Apply correct array for each day type
        normal_day_mask = df["day_type"] == "n"
        short_day_mask = df["day_type"] == "s"
        long_day_mask = df["day_type"] == "l"

        minutes_from_midnight[normal_day_mask] = normal_minuates_array[periods_idx[normal_day_mask]]
        minutes_from_midnight[short_day_mask] = short_minutes_array[periods_idx[short_day_mask]]
        minutes_from_midnight[long_day_mask] = long_minutes_array[periods_idx[long_day_mask]]

        df["minutes_from_midnight"] = minutes_from_midnight

        # Build UK local datetimes
        base_datetime = pd.to_datetime(df["settlement_date"])
        settlement_datetime_naive = base_datetime + pd.to_timedelta(
            df["minutes_from_midnight"].values,
            unit="min",
        )

        # Localize to UK timezone
        uk_timezone = settlement_datetime_naive.dt.tz_localize(
            "Europe/London",
            ambiguous="infer",  # Handle fall back duplicates
            nonexistent="raise",  # Should never occur with proper Elexon mapping
        )

        # Convert to UTC and floor to hours
        utc_datetime = uk_timezone.dt.tz_convert("UTC")
        return utc_datetime.dt.floor("h")

    @staticmethod
    def _divide_shared_bmu_generation(generation_df: pd.DataFrame) -> pd.DataFrame:
        "Divides generation for shared BMUs by the number of plants sharing it."
        bmu_cfd_groups = (generation_df
                          .groupby(["bmu_id", "settlement_date", "settlement_period"])
                          .agg({"cfd_id": "count", "capacity": "sum"})
                          .reset_index()
                          .rename(columns={"cfd_id": "cfd_count", "capacity": "capacity_sum"}))
        generation_df = generation_df.merge(bmu_cfd_groups, on=["bmu_id", "settlement_date", "settlement_period"])
        generation_df["quantity"].where(
            generation_df["cfd_count"] == 1,
            generation_df["quantity"] * (generation_df["capacity"] / generation_df["capacity_sum"]),
            inplace=True
        )
        generation_df = generation_df.drop(columns=["capacity_sum", "cfd_count", "capacity"])
        return generation_df

    def _aggregate_bmu_generation_to_cfd(
        self, cfd_df: pd.DataFrame, generation_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Process and aggregate generation data by CFD ID.

        Merges the CFD plant data with the raw generation data on BMU ID,
        then aggregates the generation quantities by CFD ID and hourly UTC datetime.
        This accounts for cases where multiple BMUs are associated with a single
        CFD contract.

        Args:
            cfd_df: DataFrame containing CFD plant data with BMU mapping.
            generation_df: DataFrame containing raw generation data from Elexon.
        Returns:
            DataFrame with aggregated generation data by CFD ID and hourly UTC datetime.
        """
        generation_df = generation_df.copy()
        generation_df = generation_df.rename(
            columns={
                "bmUnit": "bmu_id",
                "settlementDate": "settlement_date",
                "settlementPeriod": "settlement_period",
            }
        )

        # Merge with CFD data first
        generation_df = generation_df.merge(cfd_df[["cfd_id", "bmu_id", "capacity"]], on="bmu_id", how="left")

        # Divide generation of shared bmus between plants
        generation_df = self._divide_shared_bmu_generation(generation_df)

        # Aggregate BMU data by CFD and settlement period first
        aggregated_df = (
            generation_df.groupby(
                ["cfd_id", "settlement_date", "settlement_period"], as_index=False
            )
            .agg({"quantity": "sum"})
            .round(2)
        )

        # Now create datetimes for the aggregated data
        aggregated_df["time"] = self._create_hourly_utc_datetime(aggregated_df)

        # Final aggregation to hourly by summing periods within each UTC hour
        result = (
            aggregated_df.groupby(["cfd_id", "time"], as_index=False)
            .agg({"quantity": "sum"})
            .round(2)
        )

        return result  # type: ignore[return-value]

    def download(self) -> None:
        """Download generation data for all CfD-associated BMU units.

        Downloads settled generation data from Elexon for all BMU units
        found in the CfD dataset. The data is saved as a CSV file in the
        generation subdirectory. If the file already exists, download
        is skipped.
        """
        cfd_df = self._get_cfd_plants()

        self._update_output_directory(stem="generation")
        output_file = self.output_dir / GENERATION_DATA_FILE_NAME
        if output_file.exists():
            self.logger.debug("Generation data already exists, skipping download...")
            return

        bmu_generation_df = self._download_generation_data()
        generation_df = self._aggregate_bmu_generation_to_cfd(cfd_df, bmu_generation_df)
        generation_df.to_parquet(output_file, index=False)
        self.logger.info(f"Generation data saved to {output_file}")


class DownloadManager:
    """Main weather data downloader with support for multiple data sources.

    Provides a unified interface for downloading all required data sources
    for weather forecasting and renewable energy analysis. Manages instances
    of specialized downloaders for different data types and coordinates
    the overall download process.

    The manager handles:
    - ERA5 weather reanalysis data
    - CfD contract and BMU mapping data
    - Electricity generation data from Elexon
    - Coordinated download of all data sources

    Attributes:
        cfd (CfDDataDownloader): Downloader for CfD register and mapping data.
        generation (GenerationDataDownloader): Downloader for generation data.
        era5 (ERA5DataDownloader): Downloader for ERA5 weather data.
    """

    def __init__(self):
        """Initialize download manager with all data source downloaders."""
        self.cfd = CfDDataDownloader()
        self.generation = GenerationDataDownloader()
        self.era5 = ERA5DataDownloader()

    def download_cfd(self) -> None:
        """Download CfD register and BMU mapping data.

        Initiates download of Contract for Difference register data and
        BMU mapping information from LCCC data sources.
        """
        self.cfd.download()

    def download_generation_data(self) -> None:
        """Download electricity generation data from Elexon.

        Initiates download of settled generation data for CfD-associated
        BMU units from the Elexon BMRS API.
        """
        self.generation.download()

    def download_era5(self) -> None:
        """Download ERA5 weather reanalysis data.

        Initiates download of ERA5 weather data from the Copernicus
        Climate Data Store for the calibration period.
        """
        self.era5.download()

    def download_all(self) -> None:
        """Download all data sources in sequence.

        This method ensures proper dependency handling between data sources.
        """
        self.download_cfd()
        self.download_generation_data()
        self.download_era5()
