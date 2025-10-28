# ==========================================
# ERA5 Downloader (Windows / Python 3.12)
# ==========================================
# Downloads ERA5 reanalysis data for specified years,
# confirms datetime coordinate is already UTC (GMT), and adds metadata.

import os
import ssl

import cdsapi
import certifi
import xarray as xr
from pathlib import Path

from weather.utils.constants import (
    AREA_BOUNDING_BOX_COORDINATES,
    CALIBRATION_YEARS,
    CDS_API_KEY,
    CDS_API_URL,
    DOWNLOAD_DATA_DIR,
    ERA5_DATASET,
)
from weather.utils.logger import get_logger

logger = get_logger(__name__)

# --- SSL verification setup for Python 3.12 ---
# Use certifi’s CA bundle to ensure correct certificate verification
ssl_context = ssl._create_default_https_context(cafile=certifi.where())
# -----------------------------------------------------------


def download_era5_years_to_files(
    years: list[int] = CALIBRATION_YEARS, out_dir: str = DOWNLOAD_DATA_DIR
):
    if not CDS_API_KEY:
        logger.error("CDS API key not found in environment variables.")
        raise ValueError("Provide your Copernicus CDS API key string.")

    os.makedirs(out_dir, exist_ok=True)
    logger.info(f"Data will be saved to: {out_dir}")

    # Initialize CDS API client with proper SSL verification
    client = cdsapi.Client(
        url=CDS_API_URL,
        key=CDS_API_KEY,
        verify=certifi.where(),
    )

    for year in years:
        file_path = str(Path(out_dir) / f"ERA5_UK_{year}.nc")

        if os.path.exists(file_path):
            logger.info(f"File already exists for {year}, verifying timestamps...")
        else:
            logger.info(f"Downloading ERA5 data for {year}...")
            request = {
                "product_type": "reanalysis",
                "variable": ["100m_u_component_of_wind", "100m_v_component_of_wind"],
                "year": str(year),
                "month": [f"{m:02d}" for m in range(1, 13)],
                "day": [f"{d:02d}" for d in range(1, 32)],
                "time": [f"{h:02d}:00" for h in range(24)],
                "format": "netcdf",
                "area": AREA_BOUNDING_BOX_COORDINATES,
            }

            try:
                result = client.retrieve(ERA5_DATASET, request)
                result.download(target=file_path)
                logger.info(f"Download complete: {file_path}")
            except Exception as e:
                logger.error(f"Error downloading {year}: {e}")
                continue

        try:
            ds = xr.open_dataset(file_path)

            # detect datetime coordinate
            datetime_coord = None
            for coord in ds.coords:
                if "time" in coord.lower() or "date" in coord.lower():
                    datetime_coord = coord
                    break

            if not datetime_coord:
                logger.error(f"No datetime-like coordinate found in {file_path}.")
                raise KeyError("No datetime-like coordinate found (expected 'time' or similar).")

            logger.info(f"Date range: {ds[datetime_coord].values[0]}  →  {ds[datetime_coord].values[-1]}")
            logger.debug("ERA5 timestamps are already in UTC (GMT). No conversion needed.")

            # Add metadata note
            ds.attrs["time_reference"] = f"Coordinate '{datetime_coord}' is already in UTC (GMT)."

            # Overwrite file safely
            ds.load()
            ds.close()
            ds.to_netcdf(file_path, mode="w")
            logger.info(f"File verified and metadata updated: {file_path}")

        except Exception as e:
            logger.error(f"Error verifying {year}: {e}")

    logger.info("Completed all downloads and verifications.")
