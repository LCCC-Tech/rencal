# RenCal Re(newable)Cal(ibration)

An open-source Python library for renewable energy forecasting using ERA5 weather data and statistical sampling techniques.

## Overview

This project provides Monte Carlo-based load factor forecasting for wind and solar plants to support financial modelling and grid planning. It uses statistical sampling of historical weather patterns with geographical correlation preservation.

## Status

**Pre-release / Internal Integration Testing**: The core package is stable and currently being validated through end-to-end integration testing via TestPyPI distribution. Development is now focused primarily on infrastructure, packaging, and operational readiness, with incremental improvements still ongoing in the codebase.

## Key Components

- **Wind/Solar Models**: Monte Carlo paths for energy generators using bucketing and optional inverse distribution sampling (`WeatherData`)
- **Calibration Scripts**: The Low Carbon Contracts Company workflow scripts for wind/solar parameter calibration
- **Data Loading**: Stub implementation for ERA5 NetCDF data
- **Statistical Framework**: Time-bucketed sampling with correlation preservation

## Installation

```bash
# Install the package in development mode
uv sync

# Or install specific dependency groups
uv sync --group dev          # Development dependencies
uv sync --group docs         # Documentation dependencies
uv sync --group azure        # Azure integration dependencies
uv sync --group notebook     # Jupyter notebook dependencies
```

## Quick Start

```python
from weather.simulation.weather_data import WeatherData, HistoricalMetadata
from weather.core.data_loader import LocalDataLoader

loader = LocalDataLoader()

manifest_wind = loader.check_historical_weather()
metadata_wind = HistoricalMetadata.from_manifest(
    manifest_wind,
    loader.path_resolver_weather_data
)

wind_sampler = WeatherData(metadata = metadata_wind)

one_path = wind_sampler.random_sample(future_start_date,
    future_end_date)
```

**Note**: ERA5 data loading must be implemented by users. See `weather.data.ERA5DataLoader` stub.

## Development

```bash
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=weather --cov-report=html

# Code formatting and linting
uv run ruff format weather/     # Format code
uv run ruff check weather/      # Lint code
uv run basedpyright weather/    # Type checking

# Run pre-commit hooks
uv run pre-commit run --all-files
```

See [CLAUDE.md](CLAUDE.md) for detailed development guidelines.
