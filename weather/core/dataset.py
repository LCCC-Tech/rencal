from abc import ABC, abstractmethod
from typing import Any

import pandas as pd
import xarray as xr
from pydantic import BaseModel, Field, field_validator
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
            "capcaity": "float64",
        },
    ),
    "bmu_mapping": DatasetSchema(
        required_columns=["CFD_Id", "BMU_Id"],
        optional_columns=["mapping_date", "status"],
        required_datatypes={"CFD_Id": "object", "BMU_Id": "object"},
        date_columns=["mapping_date"],
    ),
    "generation": DatasetSchema(
        required_columns=["CFD_Id", "settlementDate", "quantity"],
        optional_columns=["forecast", "actual"],
        required_datatypes={"CFD_Id": "object", "quantity": "float64"},
        date_columns=["settlementDate"],
    ),
    "era5": DatasetSchema(
        required_columns=[],  # ERA5 variables vary, so we'll check for time dimension
        optional_columns=["u100", "v100", "ssrd", "t2m", "sp", "tp"],
        required_datatypes={},
        date_columns=["time", "Times"],
    ),
}


class PandasDataset(BaseDataset):
    """Pandas DataFrame wrapper with validation"""

    data: pd.DataFrame = Field(..., description="Pandas DataFrame")

    @field_validator("data")
    @classmethod
    def validate_data_structure(cls, v, info):
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
                f"Additional columns found in {data_type} data not defined in schema: {additional_cols}"
            )

        # Validate datatypes for required columns
        for col, expected_dtype in schema.required_datatypes.items():
            if col in v.columns and str(v[col].dtype) != expected_dtype:
                # Try to convert if possible
                try:
                    if expected_dtype == "float64":
                        v.loc[:, col] = pd.to_numeric(v[col], errors="coerce")
                    elif expected_dtype == "object":
                        v.loc[:, col] = v[col].astype(str)
                except:
                    raise ValueError(
                        f"Column '{col}' has dtype {v[col].dtype}, expected {expected_dtype}"
                    )

        # Special validation for ERA5 data
        if data_type == "era5":
            time_cols = [col for col in schema.date_columns if col in v.columns]
            if not time_cols:
                raise ValueError("ERA5 data must contain a time dimension ('time' or 'Times')")

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
    def validate_data_structure(cls, v, info):
        """Validate required variables based on data type"""
        data_type = info.data.get("data_type")
        if not data_type or data_type not in DATASET_SCHEMAS:
            return v

        schema = DATASET_SCHEMAS[data_type]

        # For xarray, check data variables and coordinates
        all_vars = set(v.data_vars.keys()) | set(v.coords.keys())

        # Check required variables (treat as data variables or coordinates)
        missing_vars = set(schema.required_columns) - all_vars
        if missing_vars and data_type != "era5":  # ERA5 is more flexible
            raise ValueError(f"Missing required variables for {data_type} data: {missing_vars}")

        # Special validation for ERA5 data
        if data_type == "era5":
            time_dims = [dim for dim in schema.date_columns if dim in v.dims]
            if not time_dims:
                raise ValueError("ERA5 data must contain a time dimension ('time' or 'Times')")

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


# Factory function for creating datasets
def create_dataset(
    data: pd.DataFrame | xr.Dataset, data_type: str, metadata: dict[str, Any] | None = None
) -> BaseDataset:
    """Factory function to create appropriate dataset wrapper"""
    if metadata is None:
        metadata = {}

    if isinstance(data, pd.DataFrame):
        return PandasDataset(data=data, data_type=data_type, metadata=metadata)
    elif isinstance(data, xr.Dataset):
        return XarrayDataset(data=data, data_type=data_type, metadata=metadata)
    else:
        raise ValueError(f"Unsupported data type: {type(data)}")
