from typing import Any

import pandas as pd
import xarray as xr
from pydantic import Field, field_validator

from rencal.models.base import XArrayDatasetModel
from rencal.utils.logger import get_logger

logger = get_logger(__name__)


class ERA5DatasetModel(XArrayDatasetModel):
    """Dataset for ERA5 weather data with specialized weather variable handling"""

    # Class-level schema definition - ERA5 variables vary depending on use case
    required_columns = ["u100", "v100"]
    required_datatypes = {
        "u100": "float32",
        "v100": "float32",
    }
    date_column = "time"

    data: xr.Dataset = Field(..., description="ERA5 weather data as xarray Dataset")

    @field_validator("data")
    @classmethod
    def validate_data(cls, data: xr.Dataset) -> xr.Dataset:
        """Validate ERA5 data structure using class-level schema with additional quality checks.

        Args:
            data (xr.Dataset): Input xarray Dataset containing ERA5 data
        Returns:
            xr.Dataset: Validated xarray dataset
        """
        logger.debug("Validating ERA5DatasetModel structure...")

        data = cls._validate_required_columns(data)
        data = cls._validate_datatypes(data)
        data = cls._validate_time_column(data)

        logger.debug("Validation completed successfully!")
        return data

    def get_wind_components(self) -> xr.Dataset:
        """Get wind speed components (u100, v100)"""
        return self.data[["u100", "v100"]]

    def get_solar_variables(self) -> xr.Dataset:
        """Get solar radiation variable (ssrd) if available"""
        return self.data[["ssrd", "t2m"]]

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

    def select_variables(self, variables: list[str]) -> "ERA5DatasetModel":
        """Select specific variables from the ERA5 dataset"""
        # Check if all requested variables exist
        missing_vars = set(variables) - set(self.data.data_vars.keys())
        if missing_vars:
            raise ValueError(f"Variables not found in dataset: {missing_vars}")

        selected_data = self.data[variables]
        new_metadata = self.metadata.copy()
        new_metadata["selected_variables"] = variables

        return ERA5DatasetModel(data=selected_data, metadata=new_metadata)

    def filter_by_date_range(
        self, start_date: str, end_date: str, date_col: str | None = None
    ) -> "ERA5DatasetModel":
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

        return ERA5DatasetModel(data=filtered_data, metadata=new_metadata)

    def to_pandas(self) -> pd.DataFrame:
        """Convert to pandas DataFrame"""
        return self.data.to_dataframe()

    def to_xarray(self) -> xr.Dataset:
        """Return the xarray Dataset"""
        return self.data.copy()

    def __repr__(self) -> str:
        """String representation of ERA5DatasetModel"""
        # Get basic info
        variables = list(self.data.data_vars.keys())
        dims = dict(self.data.sizes)

        # Get time range if available
        time_info = self.get_time_range()
        time_str = ""
        if time_info:
            time_str = (
                f", {time_info['start']} to {time_info['end']} ({time_info['periods']} periods)"
            )

        # Get spatial bounds if available
        spatial_info = self.get_spatial_bounds()
        spatial_str = ""
        if spatial_info:
            spatial_str = f", lat: {spatial_info['lat_min']:.2f}°-{spatial_info['lat_max']:.2f}°, lon: {spatial_info['lon_min']:.2f}°-{spatial_info['lon_max']:.2f}°"

        return f"ERA5DatasetModel(variables={variables}, dims={dims}{time_str}{spatial_str})"

    def __str__(self) -> str:
        """Overrides PyDantic default str representation"""
        return self.__repr__()
