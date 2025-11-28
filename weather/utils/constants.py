import datetime
import os
from pathlib import Path
from typing import Any

import pytz
import yaml
from dotenv import load_dotenv

from .logger import get_logger

# Load environment variables from .env file
load_dotenv()

# Create logger for this module
logger = get_logger(__name__)

# Load confiuration from YAML file
CONFIG_FILE_PATH = Path(__file__).parent / "config.yml"

run_config: dict[str, Any]
try:
    with CONFIG_FILE_PATH.open("r") as f:
        run_config = yaml.safe_load(f) or {}
    logger.info(f"Successfully loaded configuration from {CONFIG_FILE_PATH}")
except FileNotFoundError:
    logger.warning(f"Configuration file {CONFIG_FILE_PATH} not found. Using default constants.")
    run_config = {}
except yaml.YAMLError as e:
    logger.error(f"Error parsing {CONFIG_FILE_PATH}: {e}. Using default constants.")
    run_config = {}

# Absolute path to download data directory
DOWNLOAD_DATA_DIR = run_config.get(
    "DOWNLOAD_DATA_DIR", str(Path(__file__).parent.parent.parent / "data")
)

# Dates
ERA5_START_YEAR: int = run_config.get("ERA5_START_YEAR", 2023)
CALIBRATION_START_YEAR: int = run_config.get("CALIBRATION_START_YEAR", 2023)
CALIBRATION_START_DATE: str = f"{CALIBRATION_START_YEAR}-01-01T00:00:00Z"
CALIBRATION_END_DATE: str = (
    datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=5)
).strftime("%Y-%m-%dT%H:%M:%SZ")

SIMULATION_START_DATE = run_config.get("START_DATE", "2025-04-01T00:00:00Z")
SIMULATION_END_DATE = run_config.get("END_DATE", "2025-06-30T00:00:00Z")

# Data
PLANT_ID_COLUMN: str = run_config.get("PLANT_ID_COLUMN", "cfd_id")

# Runtime timestamp
RUNTIME_DATE = datetime.datetime.today()
TIMEZONE = pytz.timezone("Europe/London")
DAYS_IN_YEAR: int = 365

# ERA5 API
CDS_API_URL: str = "https://cds.climate.copernicus.eu/api"
CDS_API_KEY: str | None = os.environ.get("CDS_API_KEY", None)
ERA5_PRODUCT_TYPE = "reanalysis"
ERA5_DATASET = "reanalysis-era5-single-levels"
AREA_BOUNDING_BOX_COORDINATES = [61, -12, 49, 5]  # [North, West, South, East] - UK bounding box

# Default ERA5 variables for different use cases
DEFAULT_WIND_VARIABLES = ["100m_u_component_of_wind", "100m_v_component_of_wind"]
DEFAULT_SOLAR_VARIABLES = ["surface_solar_radiation_downwards", "2m_temperature"]

# ERA5 Variable Name Mapping
# Maps ERA5 API names to possible NetCDF variable names (handles both naming conventions)
ERA5_VARIABLE_MAPPING = {
    "100m_u_component_of_wind": "u100",
    "100m_v_component_of_wind": "v100",
    "surface_solar_radiation_downwards": "ssrd",
    "2m_temperature": "t2m",
}

# CFD API
CFD_REGISTER_API_URL = "https://register.lowcarboncontracts.uk/api/v1/contracts?format=json"
CFD_BMU_CSV_URL = "https://dp.lowcarboncontracts.uk/dataset/be8c542a-c66c-4a06-a3df-bc46db7416c0/resource/9316f493-365c-4abc-a40e-3a5e67119a0a/download/cfd_to_bm_unit_mapping.csv"
PLANT_DATA_FILE_NAME = "plant_data.csv"
WIND_TECHNOLOGY_TYPES = {"Onshore Wind", "Offshore Wind"}

# Elexon API
ELEXON_API_URL = "https://data.elexon.co.uk/bmrs/api/v1/datasets/B1610/stream"
GENERATION_DATE_FILE_NAME = "generation_data.csv"

# Normal Day (n): 48 periods, continuous 30-minute intervals
NORMAL_DAY_MINUTES = [i * 30 for i in range(50)]  # [0, 30, 60, 90, ...] up to period 50

# March Forward Day (s): 46 periods, skip 01:00-02:00 UK time
# Periods 1-2: normal timing, Periods 3-46: add 60-minute offset for missing hour
MARCH_FORWARD_MINUTES = (
    [0, 30]  # Periods 1-2: 00:00, 00:30
    + [(i * 30) + 60 for i in range(2, 46)]  # Periods 3-46: skip missing hour
)

# October Back Day (l): 50 periods, duplicate 01:00-02:00 UK time
# Periods 1-4: normal, 5-6: duplicate hour, 7+: continue normally
OCTOBER_BACK_MINUTES = (
    [i * 30 for i in range(4)]  # Periods 1-4: [0, 30, 60, 90]
    + [60, 90]  # Periods 5-6: duplicate 01:00-02:00
    + [(i * 30) for i in range(4, 48)]  # Periods 7-50: [120, 150, ..., 1410]
)

# Logging Configuration
QUIET_MODE: bool = run_config.get("QUIET_MODE", False)  # Only show warnings/errors
VERBOSE_MODE: bool = run_config.get("VERBOSE_MODE", False)  # Show all DEBUG logs

# Wind calibrator constants
DEFAULT_LOGISTIC_FN_XLOC = 9
DEFAULT_LOGISTIC_FN_ASYMMETRY = 1
DEFAULT_LOGISTIC_FN_STEEPNESS = 4.5

LOGISTIC_FN_STEEPNESS_LBOUND = 0
LOGISTIC_FN_STEEPNESS_HBOUND = 500
LOGISTIC_FN_XLOC_LBOUND = 0
LOGISTIC_FN_XLOC_HBOUND = 500
LOGISTIC_FN_ASYMMETRY_LBOUND = 0
LOGISTIC_FN_ASYMMETRY_HBOUND = 500

LOGISTIC_FN_MAXEVAL = 10000

WIND_SPEED_LBOUND = 0
WIND_SPEED_HBOUND = 40

NOT_IMPLEMENTED_ERROR_DESC = "This method must be implemented by child classes."
INTERNAL_PLANT_ID = "plant_id" # for easier maintenance of internal calculations

PLANT_ID_OUTPUT = run_config.get("PLANT_ID_OUTPUT", "CFD ID")
