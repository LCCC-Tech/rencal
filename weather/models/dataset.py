from abc import ABC, abstractmethod
from typing import Any

import pandas as pd
import xarray as xr
from pydantic import BaseModel, Field, field_validator

from weather.utils.constants import ERA5_VARIABLE_MAPPING
from weather.utils.logger import get_logger

logger = get_logger(__name__)


class BaseDataset(BaseModel, ABC):
    """Abstract base class for weather/energy datasets"""

    metadata: dict[str, Any] = Field(default_factory=dict)
    data_type: str = Field(
        ..., description="Type: 'cfd_register', 'bmu_mapping', 'generation', 'era5'"
    )

    class Config:
        arbitrary_types_allowed = True

    @abstractmethod
    def get_columns(self) -> list[str]:
        """Return list of column/variable names"""
        pass

    @abstractmethod
    def get_datatypes(self) -> dict[str, str]:
        """Return mapping of column/variable names to their datatypes"""
        pass

    @abstractmethod
    def get_shape(self) -> tuple[int, ...]:
        """Return shape of the dataset"""
        pass

    @abstractmethod
    def filter_by_date_range(
        self, start_date: str, end_date: str, date_col: str | None = None
    ) -> "BaseDataset":
        """Filter dataset by date range"""
        pass

    @abstractmethod
    def to_pandas(self) -> pd.DataFrame:
        """Convert to pandas DataFrame"""
        pass

    @abstractmethod
    def to_xarray(self) -> xr.Dataset:
        """Convert to xarray Dataset"""
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(type='{self.data_type}', shape={self.get_shape()}, columns={len(self.get_columns())})"


class PlantDataset(BaseDataset):
    """Dataset for CfD plant/facility data with location and capacity information"""

    data: pd.DataFrame = Field(..., description="Plant data with location and capacity")
    data_type: str = Field(default="plant_data", description="Dataset type")

    @field_validator("data")
    @classmethod
    def validate_plant_data(cls, v: pd.DataFrame) -> pd.DataFrame:
        """Validate plant data structure
        Args:
            v (pd.DataFrame): Input DataFrame containing plant data
        Returns:
            pd.DataFrame: Validated DataFrame
        """
        logger.info("Validating PlantDataset structure...")
        required_columns = ["plant_id", "latitude", "longitude", "technology", "capacity"]

        # Check required columns
        missing_cols = set(required_columns) - set(v.columns)
        if missing_cols:
            raise ValueError(f"Missing required columns for plant data: {missing_cols}")

        # Validate datatypes
        expected_dtypes = {"latitude": "float64", "longitude": "float64", "capacity": "float64"}

        for col, _ in expected_dtypes.items():
            if col in v.columns and not pd.api.types.is_numeric_dtype(v[col]):
                raise ValueError(f"Column '{col}' must be numeric, got {v[col].dtype}")

        return v

    def filter_by_technology(self, technology: str) -> "PlantDataset":
        """Filter plants by technology type"""
        filtered_data = self.data[self.data["technology"] == technology].copy()
        assert isinstance(filtered_data, pd.DataFrame), "Filtered data must be a DataFrame"
        new_metadata = self.metadata.copy()
        new_metadata["filtered_technology"] = technology

        return PlantDataset(data=filtered_data, metadata=new_metadata)

    def get_geographic_bounds(self) -> dict[str, float]:
        """Get geographic bounds of all plants"""
        return {
            "lat_min": float(self.data["latitude"].min()),
            "lat_max": float(self.data["latitude"].max()),
            "lon_min": float(self.data["longitude"].min()),
            "lon_max": float(self.data["longitude"].max()),
        }

    def get_capacity_summary(self) -> dict[str, float]:
        """Get capacity statistics"""
        return {
            "total_capacity": float(self.data["capacity"].sum()),
            "mean_capacity": float(self.data["capacity"].mean()),
            "median_capacity": float(self.data["capacity"].median()),
            "capacity_count": len(self.data),
        }

    def get_columns(self) -> list[str]:
        return list(self.data.columns)

    def get_datatypes(self) -> dict[str, str]:
        return {col: str(dtype) for col, dtype in self.data.dtypes.items()}

    def get_shape(self) -> tuple[int, ...]:
        return self.data.shape

    def filter_by_date_range(
        self, start_date: str, end_date: str, date_col: str | None = None
    ) -> "PlantDataset":
        """Plants don't typically have date filtering, return self"""
        logger.warning(
            "Plant data typically doesn't have date filtering. Returning original dataset."
        )
        return self

    def to_pandas(self) -> pd.DataFrame:
        return self.data.copy()

    def to_xarray(self) -> xr.Dataset:
        return xr.Dataset.from_dataframe(self.data)


class GenerationDataset(BaseDataset):
    """Dataset for generation/settlement time series data"""

    data: pd.DataFrame = Field(..., description="Generation time series data")
    data_type: str = Field(default="generation", description="Dataset type")

    @field_validator("data")
    @classmethod
    def validate_generation_data(cls, v: pd.DataFrame) -> pd.DataFrame:
        """Validate generation data structure

        Args:
            v (pd.DataFrame): Input DataFrame containing generation data
        Returns:
            pd.DataFrame: Validated DataFrame
        """
        logger.info("Validating GenerationDataset structure...")
        required_columns = ["plant_id", "time", "quantity"]

        # Check required columns
        missing_cols = set(required_columns) - set(v.columns)
        if missing_cols:
            raise ValueError(f"Missing required columns for generation data: {missing_cols}")

        # Validate quantity is numeric
        if not pd.api.types.is_numeric_dtype(v["quantity"]):
            raise ValueError(f"Column 'quantity' must be numeric, got {v['quantity'].dtype}")

        # Ensure time column exists (will be converted to datetime in filter methods)
        if "time" not in v.columns:
            raise ValueError("Generation data must contain a 'time' column")

        logger.info("GenerationDataset validation completed successfully!")
        return v

    def get_plant_ids(self) -> list[str]:
        """Get list of unique plant IDs in the dataset"""
        return list(self.data["plant_id"].unique())

    def filter_by_plant_id(self, plant_id: str) -> "GenerationDataset":
        """Filter generation data for a specific plant"""
        filtered_data = self.data[self.data["plant_id"] == plant_id].copy()
        assert isinstance(filtered_data, pd.DataFrame), "Filtered data must be a DataFrame"
        new_metadata = self.metadata.copy()
        new_metadata["filtered_plant_id"] = plant_id

        return GenerationDataset(data=filtered_data, metadata=new_metadata)

    def get_generation_summary(self) -> dict[str, Any]:
        """Get generation statistics"""
        return {
            "total_generation": float(self.data["quantity"].sum()),
            "mean_generation": float(self.data["quantity"].mean()),
            "max_generation": float(self.data["quantity"].max()),
            "min_generation": float(self.data["quantity"].min()),
            "plant_count": self.data["plant_id"].nunique(),
            "time_periods": len(self.data),
        }

    def get_time_range(self) -> dict[str, Any] | None:
        time_col = pd.to_datetime(self.data["time"])
        return {
            "start": str(time_col.min()),
            "end": str(time_col.max()),
            "periods": len(time_col.unique()),
        }

    def get_columns(self) -> list[str]:
        return list(self.data.columns)

    def get_datatypes(self) -> dict[str, str]:
        return {col: str(dtype) for col, dtype in self.data.dtypes.items()}

    def get_shape(self) -> tuple[int, ...]:
        return self.data.shape

    def filter_by_date_range(
        self, start_date: str, end_date: str, date_col: str | None = None
    ) -> "GenerationDataset":
        """Filter generation data by date range"""
        df = self.data.copy()

        # Use 'time' as default date column for generation data
        if date_col is None:
            date_col = "time"

        if date_col not in df.columns:
            raise ValueError(f"Date column '{date_col}' not found in generation data")

        # Convert to datetime and filter
        df[date_col] = pd.to_datetime(df[date_col])
        mask = (df[date_col] >= start_date) & (df[date_col] <= end_date)
        filtered_data = df[mask].copy()
        assert isinstance(filtered_data, pd.DataFrame), "Filtered data must be a DataFrame"

        new_metadata = self.metadata.copy()
        new_metadata["filtered_date_range"] = {"start": start_date, "end": end_date}

        return GenerationDataset(data=filtered_data, metadata=new_metadata)

    def to_pandas(self) -> pd.DataFrame:
        return self.data.copy()

    def to_xarray(self) -> xr.Dataset:
        return xr.Dataset.from_dataframe(self.data)


class ERA5Dataset(BaseDataset):
    """Dataset for ERA5 weather data with specialized weather variable handling"""

    data: xr.Dataset = Field(..., description="ERA5 weather data as xarray Dataset")
    data_type: str = Field(default="era5", description="Dataset type")

    @field_validator("data")
    @classmethod
    def validate_era5_data(cls, v: xr.Dataset) -> xr.Dataset:
        """Validate ERA5 data structure with gap detection and quality analysis.

        Args:
            v (xr.Dataset): Input xarray Dataset containing ERA5 data
        Returns:
            xr.Dataset: Validated xarray dataset
        """
        logger.info("Validating ERA5Dataset structure...")
        data_vars = set(v.data_vars.keys())
        valid_netcdf_names = set(ERA5_VARIABLE_MAPPING.values())
        invalid_vars = set(data_vars) - valid_netcdf_names
        if invalid_vars:
            logger.warning(f"Dropping invalid ERA5 variables: {list(invalid_vars)}")
            v = v.drop_vars(list(invalid_vars))
            logger.info(f"Should be an expected NetCDF variable from: {sorted(valid_netcdf_names)}")

        # Time continuity validation - basic checks
        time_dim = "time"
        if time_dim not in v.dims:
            raise ValueError("ERA5 data must contain a time dimension ('time')")

        if time_dim not in v.coords:
            raise ValueError("ERA5 data must contain a time coordinate ('time')")

        time_coord = v.coords[time_dim]

        if len(time_coord) > 1:
            # Convert to pandas for easier time analysis
            try:
                # Get the raw datetime values (may already be datetime64)
                time_values = time_coord.values
                if not pd.api.types.is_datetime64_any_dtype(time_values):
                    time_values = pd.to_datetime(time_values)

                # Create pandas series for analysis
                time_series = pd.Series(time_values)

                # Check for duplicate timestamps
                duplicate_mask = time_series.duplicated()
                if duplicate_mask.any():
                    num_duplicates = duplicate_mask.sum()
                    logger.warning(
                        f"ERA5 data quality warning: Found {num_duplicates} duplicate timestamps. "
                        f"This may indicate overlapping data files or processing errors."
                    )

                # Check if time series is sorted by comparing values directly
                sorted_series = time_series.sort_values()
                is_sorted = time_series.equals(sorted_series)
                if not is_sorted:
                    logger.warning("ERA5 data quality warning: Time series is not sorted.")

                # Basic time coverage summary
                logger.info(
                    f"ERA5 data coverage: {len(time_series)} time periods "
                    f"from {time_series.min()} to {time_series.max()}"
                )

            except Exception as e:
                logger.warning(f"Could not perform time series validation: {e}")
        else:
            logger.info("ERA5 data contains only a single time period")

        logger.info("ERA5Dataset validation completed successfully!")
        return v

    def get_wind_components(self) -> dict[str, xr.DataArray] | None:
        """Get wind speed components (u100, v100) if available"""
        wind_vars = {}
        if "u100" in self.data.data_vars:
            wind_vars["u100"] = self.data["u100"]
        if "v100" in self.data.data_vars:
            wind_vars["v100"] = self.data["v100"]

        return wind_vars if wind_vars else None

    def get_solar_variables(self) -> dict[str, xr.DataArray] | None:
        """Get solar radiation variables if available"""
        solar_vars = {}
        if "ssrd" in self.data.data_vars:
            solar_vars["ssrd"] = self.data["ssrd"]  # Surface solar radiation downwards
        if "t2m" in self.data.data_vars:
            solar_vars["t2m"] = self.data["t2m"]  # 2m temperature

        return solar_vars if solar_vars else None

    def get_available_variables(self) -> list[str]:
        """Get list of available weather variables"""
        return list(self.data.data_vars.keys())

    def get_spatial_bounds(self) -> dict[str, float] | None:
        """Get spatial bounds of the ERA5 data"""
        bounds = {}

        # Check for latitude/longitude coordinates
        if "latitude" in self.data.coords:
            lat_vals = self.data.coords["latitude"].values
            bounds.update({"lat_min": float(lat_vals.min()), "lat_max": float(lat_vals.max())})

        if "longitude" in self.data.coords:
            lon_vals = self.data.coords["longitude"].values
            bounds.update({"lon_min": float(lon_vals.min()), "lon_max": float(lon_vals.max())})

        return bounds if bounds else None

    def get_time_range(self) -> dict[str, Any] | None:
        """Get the time range of the ERA5 data"""
        if "time" not in self.data.dims:
            return None

        time_dim = "time"

        time_coord = self.data.coords[time_dim]
        return {
            "start": str(time_coord.values.min()),
            "end": str(time_coord.values.max()),
            "periods": len(time_coord),
        }

    def select_variables(self, variables: list[str]) -> "ERA5Dataset":
        """Select specific variables from the ERA5 dataset"""
        # Check if all requested variables exist
        missing_vars = set(variables) - set(self.data.data_vars.keys())
        if missing_vars:
            raise ValueError(f"Variables not found in dataset: {missing_vars}")

        selected_data = self.data[variables]
        new_metadata = self.metadata.copy()
        new_metadata["selected_variables"] = variables

        return ERA5Dataset(data=selected_data, metadata=new_metadata)

    def get_columns(self) -> list[str]:
        """Return list of variable and coordinate names"""
        return list(self.data.data_vars.keys()) + list(self.data.coords.keys())

    def get_datatypes(self) -> dict[str, str]:
        """Return mapping of variable names to their datatypes"""
        dtypes = {}
        for var in self.data.data_vars:
            dtypes[var] = str(self.data[var].dtype)
        for coord in self.data.coords:
            dtypes[coord] = str(self.data[coord].dtype)
        return dtypes

    def get_shape(self) -> tuple[int, ...]:
        """Return shape of the Dataset"""
        if self.data.data_vars:
            # Return shape of first data variable
            first_var = list(self.data.data_vars.keys())[0]
            return self.data[first_var].shape
        return tuple(self.data.sizes.values())

    def filter_by_date_range(
        self, start_date: str, end_date: str, date_col: str | None = None
    ) -> "ERA5Dataset":
        """Filter ERA5 data by date range"""
        ds = self.data.copy()

        # Auto-detect time dimension if not specified
        if date_col is None:
            if "time" not in ds.dims:
                raise ValueError("No time dimension found in ERA5 dataset")
            date_col = "time"

        # Filter by date range using xarray's slice selection
        filtered_data = ds.sel({date_col: slice(start_date, end_date)})

        new_metadata = self.metadata.copy()
        new_metadata["filtered_date_range"] = {"start": start_date, "end": end_date}

        return ERA5Dataset(data=filtered_data, metadata=new_metadata)

    def to_pandas(self) -> pd.DataFrame:
        """Convert to pandas DataFrame"""
        return self.data.to_dataframe()

    def to_xarray(self) -> xr.Dataset:
        """Return the xarray Dataset"""
        return self.data.copy()
