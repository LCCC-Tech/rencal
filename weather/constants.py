import os
import pytz
import os
import yaml
import datetime

# Load confiuration from YAML file
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'config.yml')

try:
    with open(CONFIG_FILE_PATH, 'r') as f:
        run_config = yaml.safe_load(f)
except FileNotFoundError:
    print(f"Error: {CONFIG_FILE_PATH} not found. Using default constants.")
    run_config = {}
except yaml.YAMLError as e:
    print(f"Error parsing {CONFIG_FILE_PATH}: {e}. Using default constants.")
    run_config = {}

SIMULATION_START_DATE = run_config.get('START_DATE', '2025-04-01T00:00:00')
SIMULATION_END_DATE = run_config.get('END_DATE', '2025-06-30T00:00:00')

# Runtime timestamp
RUNTIME_DATE = datetime.datetime.today()
TIMEZONE = pytz.timezone('Europe/London')

# ERA5 CDS API Credentials
CDS_API_URL = "https://cds.climate.copernicus.eu/api"
CDS_API_KEY = os.environ.get("CDS_API_KEY", None)


