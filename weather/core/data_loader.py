import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr
from numpy import float32, float64
from numpy.typing import NDArray

from weather.models import ERA5DatasetModel, GenerationDatasetModel, PlantDatasetModel
from weather.utils.constants import (
    DEFAULT_SOLAR_VARIABLES,
    DEFAULT_WIND_VARIABLES,
    DOWNLOAD_DATA_DIR,
    ERA5_VARIABLE_MAPPING,
    GENERATION_DATA_FILE_NAME,
    INTERNAL_PLANT_ID,
    PLANT_DATA_FILE_NAME,
    PLANT_ID_COLUMN,
    WIND_NPY_BASEPATH,
    WIND_NPY_HISTOGRAMS_BASEPATH,
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
            "Plant data loaded: %s plants, %.1f MW total capacity", total_plants, total_capacity
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
        file_path = self._base_path / "generation" / GENERATION_DATA_FILE_NAME
        if not file_path.exists():
            raise FileNotFoundError(f"Generation data file not found at {file_path}")

        df = pd.read_parquet(file_path)
        df = df.rename(columns={id_column: INTERNAL_PLANT_ID})

        # Log summary info
        total_records = len(df)
        unique_plants = df[INTERNAL_PLANT_ID].nunique() if INTERNAL_PLANT_ID in df.columns else 0

        logger.info("Generation data loaded: %s records, %s plants", total_records, unique_plants)

        return GenerationDatasetModel(
            data=df,
            metadata={
                "source": "elexon_api",
                "aggregated": True,
            },
        )

    def path_resolver_weather_data(self, basename: str) -> str | Path:
        return self._base_path / "calibrated" / basename

    def check_historical_weather(self):
        """
        This function is used to return the NPY historical calibrated weather metadata.
        It is also responsible for validating this data against its manifest file.

        Returns:
            manifest (dict): The dict representing the validation JSON along with file metadata,
                for fast federation across Simulations in models.

        """
        wind_path = self._base_path / "calibrated" / WIND_NPY_BASEPATH
        if not wind_path.exists():
            raise FileNotFoundError(f"Historical wind file not found at {wind_path}")

        basepath_wind = wind_path.name

        manifest_wind = self.verify_npy_against_manifest(
            npy_path=wind_path, manifest_path=f"{wind_path}.manifest.json"
        )

        # Add basepath to the manifest for later use in the executors:
        manifest_wind["basename"] = basepath_wind

        return manifest_wind

    def get_prefix_histograms(self) -> NDArray | None:
        histograms_wind_path = self._base_path / "calibrated" / WIND_NPY_HISTOGRAMS_BASEPATH

        if not histograms_wind_path.exists():
            return None

        try:
            histogram_memmap_ref_wind = np.load(
                histograms_wind_path, mmap_mode="r", allow_pickle=False
            )
        except Exception:
            histogram_memmap_ref_wind = None

        return histogram_memmap_ref_wind

    def get_historical_weather(self) -> NDArray | None:
        wind_path = self._base_path / "calibrated" / WIND_NPY_BASEPATH

        if not wind_path.exists():
            return None

        try:
            wind_npy = np.load(wind_path, mmap_mode="r", allow_pickle=False)
        except Exception:
            wind_npy = None

        return wind_npy

    @staticmethod
    def verify_npy_against_manifest(
        npy_path: str | Path, manifest_path: str | Path
    ) -> dict[str, Any]:
        """
        Raises ValueError on mismatch; returns None on success.
        Checks hash + basic header sanity (shape second dim vs columns length).

        Returns:
            manifest (dict): The dict representing the validation JSON,
                for later use in database -> models.

        """
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        # Checking the recorded hash from RenCal against the runtime hash of the NPY file:
        expected_hash = manifest["artifact"]["sha256"]
        actual_hash = hashlib.sha256()
        with open(npy_path, "rb") as f:
            for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
                actual_hash.update(chunk)

        if actual_hash.hexdigest() != expected_hash:
            raise ValueError(
                f"SHA-256 mismatch for {npy_path}\nexpected={expected_hash}\nactual={actual_hash.hexdigest()}"
            )

        # Sanity checks:
        actual_data = np.load(npy_path, mmap_mode="r")
        expected_cols = manifest.get("artifact", {}).get("columns", [])
        if expected_cols and actual_data.ndim != 2 and actual_data.shape[1] != len(expected_cols):
            raise ValueError(
                f"Column count mismatch: npy second dim={actual_data.shape[1]} vs manifest columns={len(expected_cols)}"
            )

        size_bytes = Path(npy_path).stat().st_size
        if size_bytes != manifest["artifact"]["size_bytes"]:
            raise ValueError(
                f"Size mismatch: file={size_bytes} vs manifest={manifest['artifact']['size_bytes']}"
            )

        return manifest

    @staticmethod
    def _get_time_dimension(ds: xr.Dataset) -> str:
        """
        Check if the dataset has a valid time dimension.

        Args:
            ds (xr.Dataset): Xarray dataset to get the name of the temporal dimension of.

        Returns:
            str: The name of the tempora dimension.

        Raises:
            ValueError: When there is no expected time dimension name in the dataset.

        """
        if "time" in ds.dims:
            return "time"
        if "valid_time" in ds.dims:
            return "valid_time"
        raise ValueError("Dataset does not contain a valid time dimension ('valid_time' or 'time')")

    def _combine_datasets_on_time_dimension(self, datasets: list[xr.Dataset]) -> xr.Dataset:
        """Combine multiple xarray Datasets on the time dimension"""
        combined_ds: xr.Dataset
        if len(datasets) > 1:
            # Assume files are split by time and concatenate along time dimension
            try:
                combined_ds = xr.concat(datasets, dim="time")
                # Sort by time to ensure chronological order
                combined_ds = combined_ds.sortby("time")
                logger.debug("Successfully concatenated and sorted %s NetCDF files", len(datasets))
            except Exception as e:
                logger.error("Failed to concatenate datasets on time dimension: %s", e)
                raise ValueError(f"Failed to concatenate NetCDF files: {e}") from e
        else:
            combined_ds = datasets[0]
            logger.debug("Using single NetCDF file")
        return combined_ds

    def _filter_dataset_variables(self, ds: xr.Dataset) -> xr.Dataset:
        # Find available ERA5 variables in the dataset (checking both naming conventions)
        available_vars = list(ds.data_vars.keys())
        requested_vars: list[str] = []
        logger.debug("Available variables in dataset: %s", available_vars)

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
        logger.debug("Filtered dataset to ERA5 variables: %s", requested_vars)
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
                with xr.open_dataset(file_path) as ds:
                    time_dim = self._get_time_dimension(ds)
                    ds = ds.rename({time_dim: "time"})
                    ds = self._cast_data_variables_to_float32(ds)
                    datasets.append(ds)
                logger.debug("Successfully loaded %s", file_path)
            except Exception as e:
                logger.warning("Failed to load %s: %s", file_path, e)
                continue

        if not datasets:
            raise ValueError("Failed to load any NetCDF files successfully")

        combined_ds = self._combine_datasets_on_time_dimension(datasets)
        combined_ds = self._filter_dataset_variables(combined_ds)

        # Summary log
        logger.info(
            "ERA5 data loaded: %s files, %s time periods",
            len(era5_files),
            combined_ds.sizes["time"],
        )

        return ERA5DatasetModel(
            data=combined_ds,
            metadata={
                "source": "local_netcdf",
                "total_files_found": len(era5_files),
                "dimensions": dict(combined_ds.sizes),
            },
        )
