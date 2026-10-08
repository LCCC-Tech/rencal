"""Generate deterministic, non-production fixtures for the test suite.

The committed files under ``tests/data`` deliberately contain no operational
plant, generation, or weather data. This script is the source of truth for
regenerating them. The original fixtures are kept locally under
``data/source-fixtures`` (which is gitignored) for comparison during the
public-release migration.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

SEED = 20260813
PLANT_COUNT = 10
GENERATION_PLANT_COUNT = 35
GENERATION_HOURS = 24 * 31


def generate_plant_data() -> pd.DataFrame:
    """Create synthetic plant metadata with the production schema."""
    capacities = np.array(
        [120.0, 135.5, 148.25, 160.0, 172.75, 185.0, 197.4, 165.0, 130.0, 220.389]
    )
    return pd.DataFrame(
        {
            "cfd_id": [f"SYN-WIND-{index:03d}" for index in range(1, PLANT_COUNT + 1)],
            "latitude": np.linspace(50.5, 58.5, PLANT_COUNT),
            "longitude": np.linspace(-5.5, 1.5, PLANT_COUNT),
            "technology": ["Onshore Wind"] * 5 + ["Offshore Wind"] * 5,
            "capacity": capacities,
            "bmu_id": [f"SYN-BMU-{index:03d}" for index in range(1, PLANT_COUNT + 1)],
        }
    )


def generate_generation_and_bov_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create synthetic metered generation and sparse negative curtailment volumes."""
    plant_ids = [f"SYN-WIND-{index:03d}" for index in range(1, PLANT_COUNT + 1)]
    plant_ids.extend(
        f"SYN-GENERATOR-{index:03d}" for index in range(PLANT_COUNT + 1, GENERATION_PLANT_COUNT + 1)
    )
    times = pd.date_range("2023-01-01", periods=GENERATION_HOURS, freq="h", tz="UTC")
    rows = []
    for plant_index, plant_id in enumerate(plant_ids):
        phase = plant_index / 3.0
        hourly_pattern = 0.45 + 0.3 * np.sin(np.arange(GENERATION_HOURS) / 18.0 + phase)
        deterministic_variation = 0.05 * np.cos(np.arange(GENERATION_HOURS) / 7.0 + phase)
        quantity = np.clip(
            (hourly_pattern + deterministic_variation) * (80 + plant_index * 4), 0, None
        )
        rows.extend(
            {"cfd_id": plant_id, "time": time, "quantity": quantity}
            for time, quantity in zip(times, quantity, strict=True)
        )

    generation_df = pd.DataFrame(rows)

    bov_df = generate_bov_data(generation_df)
    generation_df.loc[bov_df.index, "quantity"] += bov_df["volume"]

    return generation_df, bov_df


def generate_bov_data(generation_df: pd.DataFrame) -> pd.DataFrame:
    """Create sparse deterministic negative BOV capped at available generation."""

    hour_indices = np.tile(np.arange(GENERATION_HOURS), GENERATION_PLANT_COUNT)
    plant_indices = np.repeat(np.arange(GENERATION_PLANT_COUNT), GENERATION_HOURS)

    event_mask = ((hour_indices + plant_indices * 7) % 37 < 3) & (
        generation_df["quantity"].to_numpy() > 0
    )

    bov_df = generation_df.loc[event_mask, ["cfd_id", "time"]].copy()

    event_hours = hour_indices[event_mask]
    event_plants = plant_indices[event_mask]
    volumes = 2.0 + ((event_hours * 3 + event_plants * 5) % 19)

    bov_df["volume"] = -np.minimum(
        volumes.astype(float), generation_df.loc[event_mask, "quantity"].to_numpy()
    )

    return bov_df


def generate_era5_data() -> xr.Dataset:
    """Create a small synthetic wind-component dataset with ERA5-like schema."""
    rng = np.random.default_rng(SEED)
    time = pd.date_range("2023-01-01", periods=24, freq="h")
    latitude = np.linspace(49.0, 61.0, 49, dtype=np.float32)
    longitude = np.linspace(-12.0, 5.0, 69, dtype=np.float32)
    time_phase = np.arange(len(time), dtype=np.float32)[:, None, None]
    lat_phase = latitude[None, :, None] / 8
    lon_phase = longitude[None, None, :] / 6
    noise = rng.normal(0, 0.05, size=(len(time), len(latitude), len(longitude)))
    return xr.Dataset(
        {
            "u100": (
                ("time", "latitude", "longitude"),
                8 + np.sin(time_phase / 4 + lat_phase) + noise,
            ),
            "v100": (
                ("time", "latitude", "longitude"),
                1 + np.cos(time_phase / 5 + lon_phase) + noise,
            ),
        },
        coords={"time": time, "latitude": latitude, "longitude": longitude},
        attrs={
            "synthetic_data": "true",
            "description": "Deterministic synthetic fixture for RenCal tests; not operational weather data.",
        },
    )


def write_fixtures(output_dir: Path) -> None:
    """Write all synthetic fixtures below ``output_dir``."""
    (output_dir / "plant").mkdir(parents=True, exist_ok=True)
    (output_dir / "generation").mkdir(parents=True, exist_ok=True)
    (output_dir / "bov").mkdir(parents=True, exist_ok=True)
    (output_dir / "era5").mkdir(parents=True, exist_ok=True)

    generate_plant_data().to_csv(output_dir / "plant" / "plant_data.csv", index=False)

    generation_df, bov_df = generate_generation_and_bov_data()
    generation_df.to_parquet(output_dir / "generation" / "generation_data.parquet", index=False)
    bov_df.to_parquet(output_dir / "bov" / "bov_data.parquet", index=False)
    generate_era5_data().to_netcdf(output_dir / "era5" / "era5_data.nc", engine="scipy")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/data"),
        help="Directory receiving plant/, generation/, and era5/ fixtures.",
    )
    args = parser.parse_args()
    write_fixtures(args.output)


if __name__ == "__main__":
    main()
