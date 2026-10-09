from typing import Any

import pandas as pd
import xarray as xr
from pydantic import Field, field_validator

from rencal.models.base import PandasDatasetModel
from rencal.utils.logger import get_logger

logger = get_logger(__name__)


class BOVDatasetModel(PandasDatasetModel):
    """Dataset for bov/settlement time series data"""

    # Class-level schema definition
    required_columns = ["plant_id", "time", "volume"]
    required_datatypes = {"plant_id": "object", "volume": "float64"}
    date_column = "time"

    data: pd.DataFrame = Field(..., description="bov time series data")

    @field_validator("data")
    @classmethod
    def validate_data(cls, data: pd.DataFrame) -> pd.DataFrame:
        """Validate bov data structure using class-level schema

        Args:
            data (pd.DataFrame): Input DataFrame containing bov data
        Returns:
            pd.DataFrame: Validated DataFrame
        """
        logger.debug("Validating BOVDatasetModel structure...")

        data = cls._validate_required_columns(data)
        data = cls._validate_datatypes(data)
        data = cls._validate_time_column(data)

        logger.debug("Validation completed successfully!")
        return data

    def get_plant_ids(self) -> list[str]:
        """Get list of unique plant IDs in the dataset"""
        return list(self.data["plant_id"].unique())

    def get_time_range(self) -> dict[str, Any] | None:
        time_col = pd.to_datetime(self.data["time"])
        return {
            "start": str(time_col.min()),
            "end": str(time_col.max()),
            "periods": len(time_col.unique()),
        }

    def filter_by_plant_id(self, plant_id: str) -> "BOVDatasetModel":
        """Filter bov data for a specific plant"""
        filtered_data = self.data[self.data["plant_id"] == plant_id].copy()
        assert isinstance(filtered_data, pd.DataFrame), "Filtered data must be a DataFrame"
        new_metadata = self.metadata.copy()
        new_metadata["filtered_plant_id"] = plant_id

        return BOVDatasetModel(data=filtered_data, metadata=new_metadata)

    def filter_by_date_range(
        self, start_date: str, end_date: str, date_col: str | None = None
    ) -> "BOVDatasetModel":
        """Filter bov data by date range"""
        df = self.data.copy()

        # Use 'time' as default date column for generation data
        if date_col is None:
            date_col = "time"

        if date_col not in df.columns:
            raise ValueError(f"Date column '{date_col}' not found in bov data")

        # Convert to datetime and filter
        df[date_col] = pd.to_datetime(df[date_col])
        mask = (df[date_col] >= start_date) & (df[date_col] <= end_date)
        filtered_data = df[mask].copy()
        assert isinstance(filtered_data, pd.DataFrame), "Filtered data must be a DataFrame"

        new_metadata = self.metadata.copy()
        new_metadata["filtered_date_range"] = {"start": start_date, "end": end_date}

        return BOVDatasetModel(data=filtered_data, metadata=new_metadata)

    def to_pandas(self) -> pd.DataFrame:
        return self.data.copy()

    def to_xarray(self) -> xr.Dataset:
        return xr.Dataset.from_dataframe(self.data)

    def __repr__(self) -> str:
        """String representation of BOVDatasetModel"""
        # Get basic info
        plant_count = len(self.get_plant_ids())
        total_records = len(self.data)

        # Get time range if available
        time_info = self.get_time_range()
        time_str = ""
        if time_info:
            time_str = f", {time_info['start']} to {time_info['end']} ({time_info['periods']} unique times)"

        # Get sample of plant IDs for display with total count
        plant_ids = self.get_plant_ids()
        plant_display = ", ".join(plant_ids[:3]) + (
            f" ({len(plant_ids)} total)" if len(plant_ids) > 3 else ""
        )

        return f"BOVDatasetModel({plant_count} plants, {total_records} records{time_str}, plants={plant_display})"

    def __str__(self) -> str:
        """Override Pydantic's default str() to use __repr__"""
        return self.__repr__()
