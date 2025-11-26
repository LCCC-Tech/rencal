from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd
import xarray as xr
from numpy import float32, float64

from weather.models import ERA5DatasetModel, GenerationDatasetModel, PlantDatasetModel
from weather.utils.constants import (
    DEFAULT_SOLAR_VARIABLES,
    DEFAULT_WIND_VARIABLES,
    DOWNLOAD_DATA_DIR,
    ERA5_VARIABLE_MAPPING,
    GENERATION_DATE_FILE_NAME,
    INTERNAL_PLANT_ID,
    PLANT_DATA_FILE_NAME,
    PLANT_ID_COLUMN,
)
from weather.utils.logger import get_logger

logger = get_logger(__name__)


class DataLoader(ABC):
    """Abstract base class for loading different data sources"""

    @abstractmethod
    def load_plant_data(self) -> PlantDatasetModel:
        """Load CfD register with location/capacity data"""
        pass

    @abstractmethod
    def load_generation_data(self) -> GenerationDatasetModel:
        """Load settlement/generation time series"""
        pass

    @abstractmethod
    def load_era5_data(self) -> ERA5DatasetModel:
        """Load ERA5 weather data using standard wind and solar variables"""
        pass


class LocalDataLoader(DataLoader):
    def __init__(self, data_path: str = DOWNLOAD_DATA_DIR) -> None:
        self._base_path = Path(data_path)

    def load_plant_data(self, id_column: str = PLANT_ID_COLUMN) -> PlantDatasetModel:
        """Load CfD register with location/capacity data from Excel file"""
        file_path = self._base_path / "plant" / PLANT_DATA_FILE_NAME
        if not file_path.exists():
            raise FileNotFoundError(f"Plant data file not found at {file_path}")

        df = pd.read_csv(file_path)
        df = df.rename(columns={id_column: INTERNAL_PLANT_ID})

        # Log summary info
        total_plants = len(df)
        total_capacity = df["capacity"].sum() if "capacity" in df.columns else 0

        logger.info(
            f"Plant data loaded: {total_plants} plants, {total_capacity:.1f}MW total capacity"
        )

        return PlantDatasetModel(
            data=df,
            metadata={
                "source": "local_excel",
                "file_path": str(file_path),
            },
        )

    def load_generation_data(self, id_column: str = PLANT_ID_COLUMN) -> GenerationDatasetModel:
        """Load settlement/generation time series from CSV file

        Args:
            id_column (str): Column name for plant ID in the generation dataset
        Returns:
            GenerationDataset: Dataset containing generation time series
        """
        file_path = self._base_path / "generation" / GENERATION_DATE_FILE_NAME
        if not file_path.exists():
            raise FileNotFoundError(f"Generation data file not found at {file_path}")

        df = pd.read_csv(file_path, parse_dates=["time"])
        df = df.rename(columns={id_column: INTERNAL_PLANT_ID})

        # Log summary info
        total_records = len(df)
        unique_plants = df[INTERNAL_PLANT_ID].nunique() if INTERNAL_PLANT_ID in df.columns else 0

        logger.info(f"Generation data loaded: {total_records} records, {unique_plants} plants")

        return GenerationDatasetModel(
            data=df,
            metadata={
                "source": "elexon_api",
                "aggregated": True,
            },
        )

    def _get_time_dimension(self, ds: xr.Dataset) -> None:
        """Check if the dataset has a valid time dimension"""
        if "time" in ds.dims:
            return "time"
        if "valid_time" in ds.dims:
            return "valid_time"
        raise ValueError(
            "Dataset does not contain a valid time dimension ('valid_time' or 'time')"
        )

    def _combine_datasets_on_time_dimension(self, datasets: list[xr.Dataset]) -> xr.Dataset:
        """Combine multiple xarray Datasets on the time dimension"""
        combined_ds: xr.Dataset
        if len(datasets) > 1:
            # Assume files are split by time and concatenate along time dimension
            try:
                combined_ds = xr.concat(datasets, dim="time")
                # Sort by time to ensure chronological order
                combined_ds = combined_ds.sortby("time")
                logger.debug(f"Successfully concatenated and sorted {len(datasets)} NetCDF files")
            except Exception as e:
                logger.error(f"Failed to concatenate datasets on time dimension: {e}")
                raise ValueError(f"Failed to concatenate NetCDF files: {e}") from e
        else:
            combined_ds = datasets[0]
            logger.debug("Using single NetCDF file")
        return combined_ds

    def _filter_dataset_variables(self, ds: xr.Dataset) -> xr.Dataset:
        # Find available ERA5 variables in the dataset (checking both naming conventions)
        available_vars = list(ds.data_vars.keys())
        requested_vars: list[str] = []
        logger.debug(f"Available variables in dataset: {available_vars}")

        # Check for standard wind and solar variables
        standard_variables = DEFAULT_WIND_VARIABLES + DEFAULT_SOLAR_VARIABLES
        for era5_var in standard_variables:
            name = ERA5_VARIABLE_MAPPING.get(era5_var)
            if name is not None and name in available_vars:
                requested_vars.append(name)

        if not requested_vars:
            raise ValueError(
                f"No standard ERA5 variables found in data. Available variables: {available_vars}"
            )

        ds = ds[requested_vars]
        logger.debug(f"Filtered dataset to ERA5 variables: {requested_vars}")
        return ds

    def _cast_data_variables_to_float32(self, ds: xr.Dataset) -> xr.Dataset:
        """Casts all data variables to np.float32 if they are in np.float64.

        Args:
            ds (xr.Dataset): Dataset to convert data variables of.

        Returns:
            xr.Dataset: Dataset with float64 data variables converted to float32.
        """
        for data_var in ds.data_vars:
            if ds[data_var].dtype == float64:
                ds[data_var] = ds[data_var].astype(float32, casting="same_kind")
        return ds

    def load_era5_data(self) -> ERA5DatasetModel:
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
        directory_path = self._base_path / "era5"
        era5_files = list(directory_path.glob("*.nc"))
        if not era5_files:
            raise FileNotFoundError(f"No ERA5 NetCDF files found in {directory_path}")

        # Load all NetCDF files and concatenate if multiple files exist
        datasets: list[xr.Dataset] = []
        for file_path in era5_files:
            try:
                ds = xr.open_dataset(file_path)
                time_dim = self._get_time_dimension(ds)
                ds.rename({time_dim: "time"})
                ds = self._cast_data_variables_to_float32(ds)
                datasets.append(ds)
                logger.debug(f"Successfully loaded {file_path}")
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")
                continue

        if not datasets:
            raise ValueError("Failed to load any NetCDF files successfully")

        combined_ds = self._combine_datasets_on_time_dimension(datasets)
        combined_ds = self._filter_dataset_variables(combined_ds)

        # Summary log
        logger.info(
            f"ERA5 data loaded: {len(era5_files)} files, {combined_ds.sizes['time']} time periods"
        )

        return ERA5DatasetModel(
            data=combined_ds,
            metadata={
                "source": "local_netcdf",
                "total_files_found": len(era5_files),
                "dimensions": dict(combined_ds.sizes),
            },
        )
