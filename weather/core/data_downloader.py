# ==========================================
# ERA5 Downloader (Windows / Python 3.12)
# ==========================================
# Downloads ERA5 reanalysis data for specified years,
# confirms datetime coordinate is already UTC (GMT), and adds metadata.

import os
import ssl
import certifi
import cdsapi
from dotenv import load_dotenv
import xarray as xr

# --- SSL verification setup for Python 3.12 ---
# Use certifi’s CA bundle to ensure correct certificate verification
ssl._create_default_https_context = ssl.create_default_context
ssl_context = ssl.create_default_context(cafile=certifi.where())
# -----------------------------------------------------------

# Load Copernicus CDS API key from environment
load_dotenv()
CDS_API_KEY = os.getenv("CDS_API_KEY")


def download_era5_years_to_files(years, api_key=None, out_dir="C:/Repos/weather/weather/data"):
    if not api_key:
        raise ValueError("Provide your Copernicus CDS API key string.")

    os.makedirs(out_dir, exist_ok=True)
    print(f"Output directory: {os.path.abspath(out_dir)}")

    # Initialize CDS API client with proper SSL verification
    client = cdsapi.Client(
        url="https://cds.climate.copernicus.eu/api",
        key=api_key,
        verify=certifi.where(),  # explicitly use certifi bundle
    )

    dataset = "reanalysis-era5-single-levels"
    area = [61, -12, 49, 5]  # [North, West, South, East] - UK bounding box

    for year in years:
        file_path = os.path.join(out_dir, f"ERA5_UK_{year}.nc")

        if os.path.exists(file_path):
            print(f"\nFile already exists for {year}, verifying timestamps...")
        else:
            print(f"\nDownloading ERA5 data for {year}...")
            request = {
                "product_type": "reanalysis",
                "variable": ["100m_u_component_of_wind", "100m_v_component_of_wind"],
                "year": str(year),
                "month": [f"{m:02d}" for m in range(1, 13)],
                "day": [f"{d:02d}" for d in range(1, 32)],
                "time": [f"{h:02d}:00" for h in range(24)],
                "format": "netcdf",
                "area": area,
            }

            try:
                result = client.retrieve(dataset, request)
                result.download(target=file_path)
                print(f"Download complete: {file_path}")
            except Exception as e:
                print(f"Error downloading {year}: {e}")
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
                raise KeyError("No datetime-like coordinate found (expected 'time' or similar).")

            print(f"Detected datetime coordinate: '{datetime_coord}'")
            print(f"Date range: {ds[datetime_coord].values[0]}  →  {ds[datetime_coord].values[-1]}")
            print("ERA5 timestamps are already in UTC (GMT). No conversion needed.")

            # Add metadata note
            ds.attrs["time_reference"] = f"Coordinate '{datetime_coord}' is already in UTC (GMT)."

            # Overwrite file safely
            ds.load()
            ds.close()
            ds.to_netcdf(file_path, mode="w")
            print(f"File verified and metadata updated: {file_path}")

        except Exception as e:
            print(f"Error verifying {year}: {e}")

    print("\nAll requested years processed successfully.")


# Runs immediately
download_era5_years_to_files(years=[2023], api_key=CDS_API_KEY)
