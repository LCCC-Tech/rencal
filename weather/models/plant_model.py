import pandas as pd
import xarray as xr
from pydantic import Field, field_validator

from weather.models.base import PandasDatasetModel
from weather.utils.constants import WIND_TECHNOLOGY_TYPES
from weather.utils.logger import get_logger

logger = get_logger(__name__)


class PlantDatasetModel(PandasDatasetModel):
    """Dataset for CfD plant/facility data with location and capacity information"""

    # Class-level schema definition
    required_columns = ["plant_id", "latitude", "longitude", "technology", "capacity"]
    required_datatypes = {
        "plant_id": "object",
        "latitude": "float64",
        "longitude": "float64",
        "technology": "object",
        "capacity": "float64",
    }
    date_column = None

    data: pd.DataFrame = Field(..., description="Plant data with location and capacity")

    @field_validator("data")
    @classmethod
    def validate_data(cls, data: pd.DataFrame) -> pd.DataFrame:
        """Validate plant data structure using PLANT_DATA_SCHEMA

        Args:
            data (pd.DataFrame): Input DataFrame containing plant data
        Returns:
            pd.DataFrame: Validated DataFrame
        """
        logger.debug("Validating PlantDataset structure...")

        data = cls._validate_required_columns(data)
        data = cls._validate_datatypes(data)

        logger.debug("PlantDatasetModel validation completed successfully!")
        return data

    def get_geographic_bounds(self) -> dict[str, float]:
        """Get geographic bounds of all plants"""
        return {
            "lat_min": float(self.data["latitude"].min()),
            "lat_max": float(self.data["latitude"].max()),
            "lon_min": float(self.data["longitude"].min()),
            "lon_max": float(self.data["longitude"].max()),
        }

    def filter_by_technology(self, technologies: list[str]) -> "PlantDatasetModel":
        """Filter plants by user specified technology types.

        Args:
            technologies (list[str]): List of technology types to filter by
        Returns:
            PlantDatasetModel: New PlantDatasetModel with filtered data
        Raises:
            ValueError: If no plants found with specified technology types
        """
        mask = self.data["technology"].isin(technologies)
        if mask.any() is False:
            raise ValueError(f"No plants found with technology types '{technologies}'")
        filtered_data = self.data[mask].copy()
        assert isinstance(filtered_data, pd.DataFrame), "Filtered data must be a DataFrame"

        new_metadata = self.metadata.copy()
        new_metadata["filtered_technologies"] = technologies

        return PlantDatasetModel(data=filtered_data, metadata=new_metadata)

    def get_wind_plants(self) -> "PlantDatasetModel":
        """Get only wind plants from the dataset"""
        return self.filter_by_technology(list(WIND_TECHNOLOGY_TYPES))

    def to_pandas(self) -> pd.DataFrame:
        return self.data.copy()

    def to_xarray(self) -> xr.Dataset:
        return xr.Dataset.from_dataframe(self.data)

    def __repr__(self) -> str:
        """String representation of PlantDatasetModel"""
        # Get basic info
        plant_count = len(self.data)
        technologies = list(self.data["technology"].unique())
        total_capacity = self.data["capacity"].sum()

        # Get geographic bounds
        bounds = self.get_geographic_bounds()
        geo_str = f"lat: {bounds['lat_min']:.2f}°-{bounds['lat_max']:.2f}°, lon: {bounds['lon_min']:.2f}°-{bounds['lon_max']:.2f}°"

        # Show sample technologies
        tech_display = f"{technologies[:3]}{'...' if len(technologies) > 3 else ''}"

        return f"PlantDatasetModel({plant_count} plants, {total_capacity:.1f}MW total, technologies={tech_display}, {geo_str})"
