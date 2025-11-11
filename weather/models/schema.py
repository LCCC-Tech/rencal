from pydantic import BaseModel, Field

from weather.utils.constants import ERA5_VARIABLE_MAPPING


class DatasetSchema(BaseModel):
    """Schema definition for dataset validation"""

    required_columns: list[str] = Field(default_factory=list)
    optional_columns: list[str] = Field(default_factory=list)
    required_datatypes: dict[str, str] = Field(default_factory=dict)
    date_columns: list[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


# Plant data schema
PLANT_DATA_SCHEMA = DatasetSchema(
    required_columns=["plant_id", "latitude", "longitude", "technology", "capacity"],
    required_datatypes={
        "plant_id": "object",
        "latitude": "float64",
        "longitude": "float64",
        "technology": "object",
        "capacity": "float64",
    },
)

# Generation data schema
GENERATION_DATA_SCHEMA = DatasetSchema(
    required_columns=["plant_id", "time", "quantity"],
    required_datatypes={"plant_id": "object", "quantity": "float64"},
    date_columns=["time"],
)

# ERA5 data schema - flexible for various ERA5 variables
ERA5_DATA_SCHEMA = DatasetSchema(
    required_columns=[],  # ERA5 variables vary depending on use case
    optional_columns=list(ERA5_VARIABLE_MAPPING.keys()),  # All known ERA5 API names
    required_datatypes={},
    date_columns=["time"],
)

