from abc import ABC, abstractmethod
from typing import Any, ClassVar

import pandas as pd
import xarray as xr
from pydantic import BaseModel, Field

from rencal.utils.logger import get_logger

logger = get_logger(__name__)


class DatasetModel(BaseModel, ABC):
    """Abstract base class for datasets with common validation and methods

    Attributes:
        metadata (dict[str, Any]): Optional metadata about the datasets
    """

    metadata: dict[str, Any] = Field(default_factory=dict)

    # Default schema attributes (to be overridden by subclasses)
    required_columns: ClassVar[list[str]] = []
    required_datatypes: ClassVar[dict[str, str]] = {}
    date_column: ClassVar[str | None] = None

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    @abstractmethod
    def _validate_required_columns(cls, data: Any) -> Any:
        """Check that all required columns/variables are present in data"""
        pass

    @classmethod
    @abstractmethod
    def _validate_datatypes(cls, data: Any) -> Any:
        """Validate data column/variable datatypes"""
        pass

    @classmethod
    @abstractmethod
    def _validate_time_column(cls, data: Any) -> Any:
        """Validate that required time column/dimension exist in data"""
        pass

    @abstractmethod
    def to_pandas(self) -> pd.DataFrame:
        """Convert to pandas DataFrame"""
        pass

    @abstractmethod
    def to_xarray(self) -> xr.Dataset:
        """Convert to xarray Dataset"""
        pass


class PandasDatasetModel(DatasetModel):
    """Concrete base class for pandas DataFrame-based datasets"""

    @classmethod
    def _validate_required_columns(cls, data: pd.DataFrame) -> pd.DataFrame:
        """Check that all required columns are present in DataFrame"""
        missing_cols = set(cls.required_columns) - set(data.columns)
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        return data

    @classmethod
    def _validate_datatypes(cls, data: pd.DataFrame) -> pd.DataFrame:
        """Validate DataFrame column datatypes"""
        for col, expected_dtype in cls.required_datatypes.items():
            if col in data.columns:
                if expected_dtype in ["float64", "float32"] and not pd.api.types.is_numeric_dtype(
                    data[col]
                ):
                    raise ValueError(f"Column '{col}' must be numeric, got {data[col].dtype}")
                elif expected_dtype == "object" and not pd.api.types.is_object_dtype(data[col]):
                    # Allow string-like types for object columns
                    if not pd.api.types.is_string_dtype(data[col]):
                        logger.warning(
                            "Column '%s' expected object dtype, got %s", col, data[col].dtype
                        )
        return data

    @classmethod
    def _validate_time_column(cls, data: pd.DataFrame) -> pd.DataFrame:
        """Validate that required time columns exist in DataFrame"""
        if cls.date_column:
            # Check for presence of date dimension and coordinate
            if cls.date_column not in data.columns:
                raise ValueError(f"Missing required time column: '{cls.date_column}'")
            if not pd.api.types.is_datetime64_any_dtype(data[cls.date_column]):
                raise ValueError(
                    f"Time column '{cls.date_column}' must be datetime64, got {data[cls.date_column].dtype}"
                )

            # Check for non-empty and non-null time values
            if data[cls.date_column].empty is True:
                raise ValueError(f"Time column '{cls.date_column}' contains no data")
            if data[cls.date_column].isnull().any() is True:
                raise ValueError(f"Time column '{cls.date_column}' contains null values")

        return data


class XArrayDatasetModel(DatasetModel):
    """Concrete base class for xarray Dataset-based datasets"""

    @classmethod
    def _validate_required_columns(cls, data: xr.Dataset) -> xr.Dataset:
        """Check that all required variables are present in xarray Dataset

        Args:
            data (xr.Dataset): Input xarray Dataset
        Returns:
            xr.Dataset: xarray Dataset with validated variables
        """
        if cls.required_columns:  # For xarray, required_columns means required variables
            data_vars = set(data.data_vars.keys())
            missing_vars = set(cls.required_columns) - data_vars
            if missing_vars:
                raise ValueError(f"Missing required variables: {missing_vars}")
        return data

    @classmethod
    def _validate_datatypes(cls, data: xr.Dataset) -> xr.Dataset:
        """Validate xarray Dataset variable datatypes

        Args:
            data (xr.Dataset): Input xarray Dataset
        Returns:
            xr.Dataset: xarray Dataset with validated variable datatypes
        """
        for var, required_dtype in cls.required_datatypes.items():
            if var in data.data_vars:
                actual_dtype = str(data[var].dtype)
                if actual_dtype != required_dtype:
                    raise ValueError(
                        f"Variable '{var}' has incorrect dtype: expected '{required_dtype}', got '{actual_dtype}'"
                    )
        return data

    @classmethod
    def _validate_time_column(cls, data: xr.Dataset) -> xr.Dataset:
        """Validate that required date dimensions exist in xarray Dataset

        Args:
            data (xr.Dataset): Input xarray Dataset
        Returns:
            xr.Dataset: xarray Dataset with validated date dimensions
        """
        if cls.date_column:
            # Check for presence of date dimension and coordinate
            if cls.date_column not in data.dims:
                raise ValueError(f"Missing required time dimension: '{cls.date_column}'")
            if cls.date_column not in data.coords:
                raise ValueError(f"Missing required time coordinate: '{cls.date_column}'")

            # Check for non-empty and non-null time values
            if data[cls.date_column].size == 0:
                raise ValueError(f"Time coordinate '{cls.date_column}' contains no data")
            if data[cls.date_column].isnull().any():
                raise ValueError(f"Time coordinate '{cls.date_column}' contains null values")

            time_values = data[cls.date_column].values

            if not pd.api.types.is_datetime64_any_dtype(time_values):
                raise ValueError(
                    f"Time series '{cls.date_column}' must be datetime64, got {data[cls.date_column].dtype}"
                )

            # Check for strictly increasing time values and duplicates
            time_values = pd.to_datetime(time_values)
            duplicate_mask = time_values.duplicated()

            if duplicate_mask.any():
                duplicate_count = duplicate_mask.sum()
                raise ValueError(
                    f"Time series '{cls.date_column}' contains {duplicate_count} duplicate timestamps"
                )
            if not (time_values.to_series().is_monotonic_increasing):
                raise ValueError(
                    f"Time series '{cls.date_column}' must be sorted in ascending order"
                )

        return data
