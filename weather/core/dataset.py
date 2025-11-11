from abc import ABC, abstractmethod
from typing import Any

import pandas as pd
import xarray as xr
from pydantic import BaseModel, Field, ValidationInfo, field_validator

from weather.utils.constants import ERA_VARIABLES, ERA5_VARIABLE_MAPPING
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


class DatasetSchema(BaseModel):
    """Schema definition for dataset validation"""

    required_columns: list[str] = Field(default_factory=list)
    optional_columns: list[str] = Field(default_factory=list)
    required_datatypes: dict[str, str] = Field(default_factory=dict)
    date_columns: list[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


# Schema definitions for different dataset types
DATASET_SCHEMAS = {
    "plant_data": DatasetSchema(
        required_columns=["plant_id", "latitude", "longitude", "technology", "capacity"],
        required_datatypes={
            "plant_id": "object",
            "latitude": "float64",
            "longitude": "float64",
            "technology": "object",
            "capacity": "float64",
        },
    ),
    "generation": DatasetSchema(
        required_columns=["plant_id", "time", "quantity"],
        required_datatypes={"plant_id": "object", "quantity": "float64"},
        date_columns=["time"],
    ),
    "era5": DatasetSchema(
        required_columns=[],  # ERA5 variables vary, so we'll check for time dimension
        optional_columns=ERA_VARIABLES
        + ["ssrd", "t2m", "sp", "tp"],  # Include standard ERA variables
        required_datatypes={},
        date_columns=["time"],
    ),
}


class PandasDataset(BaseDataset):
    """Pandas DataFrame wrapper with validation"""

    logger.info("Initialising PandasDataset")

    data: pd.DataFrame = Field(..., description="Pandas DataFrame")

    @field_validator("data")
    @classmethod
    def validate_data_structure(cls, v: pd.DataFrame, info: ValidationInfo) -> pd.DataFrame:
        """Validate required columns based on data type"""
        data_type = info.data.get("data_type")
        if not data_type or data_type not in DATASET_SCHEMAS:
            return v

        schema = DATASET_SCHEMAS[data_type]

        # Check required columns
        missing_cols = set(schema.required_columns) - set(v.columns)
        additional_cols = set(v.columns) - set(schema.required_columns)
        if missing_cols:
            raise ValueError(f"Missing required columns for {data_type} data: {missing_cols}")

        if additional_cols:
            logger.warning(
                f"Dropping additional columns found in {data_type} data not defined in schema: {additional_cols}"
            )
            v = v.drop(columns=list(additional_cols))

        # Validate datatypes for required columns
        for col, expected_dtype in schema.required_datatypes.items():
            if col in v.columns and str(v[col].dtype) != expected_dtype:
                raise ValueError(
                    f"Column '{col}' has dtype {v[col].dtype}, expected {expected_dtype}. "
                    f"No automatic conversion will be performed."
                )

        # Special validation for ERA5 data
        if data_type == "era5":
            time_cols = [col for col in schema.date_columns if col in v.columns]
            if not time_cols:
                raise ValueError("ERA5 data must contain a time dimension ('time')")

        return v

    def get_columns(self) -> list[str]:
        """Return list of column names"""
        return list(self.data.columns)

    def get_datatypes(self) -> dict[str, str]:
        """Return mapping of column names to their datatypes"""
        return {col: str(dtype) for col, dtype in self.data.dtypes.items()}

    def get_shape(self) -> tuple[int, ...]:
        """Return shape of the DataFrame"""
        return self.data.shape

    def filter_by_date_range(
        self, start_date: str, end_date: str, date_col: str | None = None
    ) -> "PandasDataset":
        """Filter dataset by date range"""
        df = self.data.copy()

        # Auto-detect date column if not specified
        if date_col is None:
            schema = DATASET_SCHEMAS.get(self.data_type)
            if schema:
                date_cols = [col for col in schema.date_columns if col in df.columns]
                date_col = date_cols[0] if date_cols else None

            if date_col is None:
                raise ValueError("No date column found in dataset")

        df[date_col] = pd.to_datetime(df[date_col])
        mask = (df[date_col] >= start_date) & (df[date_col] <= end_date)
        filtered_data = df[mask].copy()
        assert isinstance(filtered_data, pd.DataFrame), "Filtered data must be a DataFrame"

        new_metadata = self.metadata.copy()
        new_metadata["filtered_date_range"] = {"start": start_date, "end": end_date}

        return PandasDataset(data=filtered_data, data_type=self.data_type, metadata=new_metadata)

    def to_pandas(self) -> pd.DataFrame:
        """Return the pandas DataFrame"""
        return self.data.copy()

    def to_xarray(self) -> xr.Dataset:
        """Convert to xarray Dataset"""
        return xr.Dataset.from_dataframe(self.data)


class XarrayDataset(BaseDataset):
    """Xarray Dataset wrapper with validation"""

    data: xr.Dataset = Field(..., description="Xarray Dataset")

    @field_validator("data")
    @classmethod
    def validate_data_structure(cls, v: xr.Dataset, info: ValidationInfo) -> xr.Dataset:
        """Validate required variables based on data type"""
        data_type = info.data.get("data_type")
        if not data_type or data_type not in DATASET_SCHEMAS:
            return v

        schema = DATASET_SCHEMAS[data_type]

        # For xarray, check data variables and coordinates
        all_vars = {str(k) for k in v.data_vars.keys()} | {str(k) for k in v.coords.keys()}

        # Check required variables (treat as data variables or coordinates)
        missing_vars = set(schema.required_columns) - all_vars
        if missing_vars and data_type != "era5":  # ERA5 is more flexible
            raise ValueError(f"Missing required variables for {data_type} data: {missing_vars}")

        # Special validation for ERA5 data
        if data_type == "era5":
            time_dims = [dim for dim in schema.date_columns if dim in v.dims]
            if not time_dims:
                raise ValueError("ERA5 data must contain a time dimension ('time')")

            # Validate that requested variables are known ERA5 variables
            data_vars = set(v.data_vars.keys())
            
            # Create set of all valid ERA5 variable names (both API names and NetCDF names)
            all_valid_era5_names = set()
            for api_name, netcdf_names in ERA5_VARIABLE_MAPPING.items():
                all_valid_era5_names.add(api_name)
                all_valid_era5_names.update(netcdf_names)
            
            non_standard_vars = data_vars - all_valid_era5_names
            if non_standard_vars:
                logger.warning(
                    f"Variables {list(non_standard_vars)} are not in the standard ERA5 variable mapping. "
                    f"Expected variables include: {sorted(all_valid_era5_names)}"
                )

        return v

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
    ) -> "XarrayDataset":
        """Filter dataset by date range"""
        ds = self.data.copy()

        # Auto-detect date dimension if not specified
        if date_col is None:
            schema = DATASET_SCHEMAS.get(self.data_type)
            if schema:
                date_dims = [dim for dim in schema.date_columns if dim in ds.dims]
                date_col = date_dims[0] if date_dims else None

            if date_col is None:
                raise ValueError("No date dimension found in dataset")

        # Filter by date range
        filtered_data = ds.sel({date_col: slice(start_date, end_date)})

        new_metadata = self.metadata.copy()
        new_metadata["filtered_date_range"] = {"start": start_date, "end": end_date}

        return XarrayDataset(data=filtered_data, data_type=self.data_type, metadata=new_metadata)

    def to_pandas(self) -> pd.DataFrame:
        """Convert to pandas DataFrame"""
        return self.data.to_dataframe()

    def to_xarray(self) -> xr.Dataset:
        """Return the xarray Dataset"""
        return self.data.copy()


# Specific Dataset Classes
# These provide type-safe, domain-specific interfaces for different data types


class PlantDataset(BaseDataset):
    """Dataset for CfD plant/facility data with location and capacity information"""

    data: pd.DataFrame = Field(..., description="Plant data with location and capacity")
    data_type: str = Field(default="plant_data", description="Dataset type")

    @field_validator("data")
    @classmethod
    def validate_plant_data(cls, v: pd.DataFrame) -> pd.DataFrame:
        """Validate plant data structure"""
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
        """Validate generation data structure"""
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
        """Validate ERA5 data structure with gap detection and quality analysis"""
        # Check for time dimension
        if "time" not in v.dims:
            raise ValueError("ERA5 data must contain a time dimension ('time')")
        
        time_dim = "time"

        # Validate that requested variables are known ERA5 variables
        data_vars = set(v.data_vars.keys())
        
        # Create set of all valid ERA5 variable names (both API names and NetCDF names)
        all_valid_era5_names = set()
        for api_name, netcdf_names in ERA5_VARIABLE_MAPPING.items():
            all_valid_era5_names.add(api_name)
            all_valid_era5_names.update(netcdf_names)
        
        non_standard_vars = data_vars - all_valid_era5_names
        if non_standard_vars:
            logger.warning(
                f"Variables {list(non_standard_vars)} are not in the standard ERA5 variable mapping. "
                f"Expected variables include: {sorted(all_valid_era5_names)}"
            )

        # Time continuity validation - basic checks
        if time_dim in v.coords:
            time_coord = v.coords[time_dim]
            
            if len(time_coord) > 1:
                # Convert to pandas for easier time analysis
                try:
                    time_series = pd.to_datetime(time_coord.values)
                    time_series_sorted = time_series.sort_values()
                    
                    # Check for duplicate timestamps
                    duplicate_times = time_series_sorted.duplicated()
                    if duplicate_times.any():
                        num_duplicates = duplicate_times.sum()
                        logger.warning(
                            f"ERA5 data quality warning: Found {num_duplicates} duplicate timestamps. "
                            f"This may indicate overlapping data files or processing errors."
                        )
                    
                    # Check if time series is sorted
                    if not time_series.equals(time_series_sorted):
                        logger.warning(
                            f"ERA5 data quality warning: Time series is not sorted. "
                            f"This may indicate data loading issues."
                        )
                    
                    # Basic time coverage summary
                    logger.info(
                        f"ERA5 data coverage: {len(time_series)} time periods "
                        f"from {time_series_sorted.min()} to {time_series_sorted.max()}"
                    )
                    
                except Exception as e:
                    logger.warning(f"Could not perform time series validation: {e}")
            else:
                logger.info("ERA5 data contains only a single time period")

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

    def get_data_quality_report(self) -> dict[str, Any]:
        """Generate a basic data quality report for ERA5 data"""
        report = {
            "variables": list(self.data.data_vars.keys()),
            "spatial_bounds": self.get_spatial_bounds(),
            "time_analysis": {},
            "data_completeness": {},
            "warnings": [],
        }

        # Find time dimension
        time_dim = "time" if "time" in self.data.dims else None

        if time_dim:
            try:
                time_coord = self.data.coords[time_dim]
                time_series = pd.to_datetime(time_coord.values)
                time_series_sorted = time_series.sort_values()

                # Basic time analysis
                report["time_analysis"] = {
                    "start": str(time_series_sorted.min()),
                    "end": str(time_series_sorted.max()),
                    "total_periods": len(time_series),
                    "is_sorted": time_series.equals(time_series_sorted),
                }

                # Duplicate check
                duplicate_times = time_series_sorted.duplicated()
                if duplicate_times.any():
                    num_duplicates = duplicate_times.sum()
                    report["time_analysis"]["duplicate_timestamps"] = int(num_duplicates)
                    report["warnings"].append(f"Found {num_duplicates} duplicate timestamps")

            except Exception as e:
                report["time_analysis"]["error"] = f"Could not analyze time dimension: {e}"
                report["warnings"].append("Time analysis failed")

        # Data completeness analysis
        for var in self.data.data_vars:
            try:
                data_array = self.data[var]
                total_values = data_array.size
                null_values = int(data_array.isnull().sum())
                
                report["data_completeness"][var] = {
                    "total_values": total_values,
                    "null_values": null_values,
                    "completeness_percent": round((total_values - null_values) / total_values * 100, 2) if total_values > 0 else 0,
                }
                
                if null_values > 0:
                    completion_pct = (total_values - null_values) / total_values * 100
                    report["warnings"].append(f"Variable '{var}' has {null_values} null values ({completion_pct:.1f}% complete)")
            except Exception as e:
                report["data_completeness"][var] = {"error": str(e)}
                report["warnings"].append(f"Could not analyze completeness for variable '{var}'")

        return report

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
