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
DOWNLOAD_DATA_DIR: str = run_config.get("DOWNLOAD_DATA_DIR", str(Path(__file__).parent / "data"))

# Dates
CALIBRATION_YEARS: list[int] = run_config.get("CALIBRATION_YEARS", [2023])
SIMULATION_START_DATE: str = run_config.get("START_DATE", "2025-04-01T00:00:00")
SIMULATION_END_DATE: str = run_config.get("END_DATE", "2025-06-30T00:00:00")

# Runtime timestamp
RUNTIME_DATE = datetime.datetime.today()
TIMEZONE = pytz.timezone("Europe/London")

# ERA5 CDS API Credentials
ERA5_DATASET = "reanalysis-era5-single-levels"
CDS_API_URL: str = "https://cds.climate.copernicus.eu/api"
CDS_API_KEY: str | None = os.environ.get("CDS_API_KEY", None)

AREA_BOUNDING_BOX_COORDINATES = [61, -12, 49, 5]  # [North, West, South, East] - UK bounding box
