from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd
import xarray as xr

from weather.utils.constants import (
    DOWNLOAD_DATA_DIR,
    ERA5_VARIABLE_MAPPING,
    DEFAULT_WIND_VARIABLES,
    DEFAULT_SOLAR_VARIABLES,
    GENERATION_DATE_FILE_NAME,
    PLANT_DATA_FILE_NAME,
    PLANT_ID_COLUMN,
    WIND_TECHNOLOGY_TYPES,
)
from weather.utils.logger import get_logger

from weather.models.dataset import (
    ERA5Dataset,
    GenerationDataset,
    PlantDataset,
)

logger = get_logger(__name__)


class DataLoader(ABC):
    """Abstract base class for loading different data sources"""

    @abstractmethod
    def load_wind_plant_data(self) -> PlantDataset:
        """Load CfD register with location/capacity data"""
        pass

    @abstractmethod
    def load_generation_data(self) -> GenerationDataset:
        """Load settlement/generation time series"""
        pass

    @abstractmethod
    def load_era5_data(self) -> ERA5Dataset:
        """Load ERA5 weather data using standard wind and solar variables"""
        pass


class LocalDataLoader(DataLoader):
    def __init__(self, data_path: str = DOWNLOAD_DATA_DIR) -> None:
        self._base_path = Path(data_path)

    def load_wind_plant_data(self, id_column: str = PLANT_ID_COLUMN) -> PlantDataset:
        """Load CfD register with location/capacity data from Excel file"""
        file_path = self._base_path / "plant" / PLANT_DATA_FILE_NAME
        if not file_path.exists():
            raise FileNotFoundError(f"Plant data file not found at {file_path}")

        df = pd.read_csv(file_path)

        # Filter for wind technologies
        mask = df["technology"].isin(list(WIND_TECHNOLOGY_TYPES))
        wind_df = df.loc[mask].copy()

        wind_df = wind_df.rename(columns={id_column: "plant_id"})

        return PlantDataset(
            data=wind_df,
            metadata={
                "source": "local_excel",
                "file_path": str(file_path),
                "filtered": True,
                "filter_criteria": "Onshore Wind, Offshore Wind only",
            },
        )

    def load_generation_data(self, id_column: str = PLANT_ID_COLUMN) -> GenerationDataset:
        """Load settlement/generation time series from CSV file

        Args:
            id_column (str): Column name for plant ID in the generation dataset
        Returns:
            GenerationDataset: Dataset containing generation time series
        """
        file_path = self._base_path / "generation" / GENERATION_DATE_FILE_NAME
        if not file_path.exists():
            raise FileNotFoundError(f"Generation data file not found at {file_path}")

        df = pd.read_csv(file_path)
        df = df.rename(columns={id_column: "plant_id"})

        return GenerationDataset(
            data=df,
            metadata={
                "source": "elexon_api",
                "aggregated": True,
            },
        )

    def load_era5_data(self) -> ERA5Dataset:
        """Load ERA5 weather data from NetCDF files using standard variables

        Automatically discovers and loads all available NetCDF files, filtering for
        standard ERA5 variables defined in DEFAULT_WIND_VARIABLES and DEFAULT_SOLAR_VARIABLES. 
        No date filtering is applied - users can filter post-load using the dataset's filter methods.

        Returns:
            ERA5Dataset: Dataset containing all available ERA5 weather data

        Raises:
            FileNotFoundError: If no NetCDF files found in the data path
            ValueError: If no standard ERA5 variables are found in the data
        """
        era5_files = list(self._base_path.glob("*.nc"))
        if not era5_files:
            raise FileNotFoundError(f"No ERA5 NetCDF files found in {self._base_path}")

        # Load all NetCDF files and concatenate if multiple files exist
        datasets: list[xr.Dataset] = []
        for file_path in era5_files:
            try:
                ds = xr.open_dataset(file_path)
                datasets.append(ds)
                logger.debug(f"Successfully loaded {file_path}")
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")
                continue

        if not datasets:
            raise ValueError("Failed to load any NetCDF files successfully")

        # Concatenate datasets if multiple files, otherwise use single dataset
        combined_ds: xr.Dataset
        if len(datasets) > 1:
            # Assume files are split by time and concatenate along time dimension
            try:
                combined_ds = xr.concat(datasets, dim="time")
                logger.info(f"Successfully concatenated {len(datasets)} NetCDF files")
            except Exception as e:
                logger.error(f"Failed to concatenate datasets: {e}")
                raise ValueError(f"Failed to concatenate NetCDF files: {e}") from e
        else:
            combined_ds = datasets[0]
            logger.info("Using single NetCDF file")

        # Use the centralized ERA5 variable mapping from constants
        era5_var_mapping = ERA5_VARIABLE_MAPPING

        # Find available ERA5 variables in the dataset (checking both naming conventions)
        available_vars = list(combined_ds.data_vars.keys())
        requested_vars: list[str] = []

        # Check for standard wind and solar variables
        standard_variables = DEFAULT_WIND_VARIABLES + DEFAULT_SOLAR_VARIABLES
        for era5_var in standard_variables:
            possible_names = era5_var_mapping.get(era5_var, [era5_var])
            for name in possible_names:
                if name in available_vars:
                    requested_vars.append(name)
                    break

        # Check for any other ERA5 variables that might be present but aren't in our standard set
        all_era5_api_names = list(era5_var_mapping.keys())
        for era5_var in all_era5_api_names:
            if era5_var not in standard_variables:
                possible_names = era5_var_mapping.get(era5_var, [era5_var])
                for name in possible_names:
                    if name in available_vars and name not in requested_vars:
                        requested_vars.append(name)
                        break

        if not requested_vars:
            # Create a readable list of expected variable names
            expected_names: list[str] = []
            for era5_var in standard_variables:
                possible_names = era5_var_mapping.get(era5_var, [era5_var])
                expected_names.extend(possible_names)

            raise ValueError(
                f"No standard ERA5 variables found in data. "
                f"Expected variables (any of): {expected_names}, "
                f"Available variables: {available_vars}"
            )

        # Select available ERA5 variables
        combined_ds = combined_ds[requested_vars]
        logger.info(f"Loaded ERA5 variables: {requested_vars}")

        return ERA5Dataset(
            data=combined_ds,
            metadata={
                "source": "local_netcdf",
                "data_path": str(self._base_path),
                "files_loaded": len(datasets),
                "total_files_found": len(era5_files),
                "dimensions": dict(combined_ds.sizes),  # Use .sizes instead of .dims to avoid FutureWarning
            },
        )