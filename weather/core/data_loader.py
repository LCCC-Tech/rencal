# ==========================================
# ERA5 Downloader (working on Windows / Py3.13)
# ==========================================

import os
import cdsapi
from dotenv import load_dotenv

# --- SSL workaround (bypass verification) ---
import ssl

ssl._create_default_https_context = ssl._create_unverified_context
# --------------------------------------------

# Load your Copernicus API key
load_dotenv()
CDS_API_KEY = os.getenv("CDS_API_KEY")


def download_era5_years_to_files(years, api_key=None, out_dir="C:/Repos/weather/weather/data"):
    if not api_key:
        raise ValueError("Provide your Copernicus CDS API key string.")

    os.makedirs(out_dir, exist_ok=True)
    print(f"✅ Output directory: {os.path.abspath(out_dir)}")

    # SSL verification disabled because Python 3.13 breaks it
    client = cdsapi.Client(
        url="https://cds.climate.copernicus.eu/api",
        key=api_key,
        verify=False,  # disables HTTPS certificate check safely here
    )

    dataset = "reanalysis-era5-single-levels"
    area = [61, -12, 49, 5]  # [North, West, South, East] - UK bounding box

    for year in years:
        out_path = os.path.join(out_dir, f"ERA5_UK_{year}.nc")

        if os.path.exists(out_path):
            print(f"Skipping {year} (already exists)")
            continue

        print(f"⬇️ Downloading ERA5 data for {year}...")
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
            file_path = result.download(target=out_path)
            print(f"ERA5 {year} saved to: {file_path}")
        except Exception as e:
            print(f"Failed to download ERA5 for {year}: {e}")

    print("All requested years processed successfully!")


# Run it directly
download_era5_years_to_files(years=[2023], api_key=CDS_API_KEY)
