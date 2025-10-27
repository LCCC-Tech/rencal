# Weather Forecasting and Modelling

An open-source Python library for renewable energy forecasting using ERA5 weather data and statistical sampling techniques.

## Overview

This project provides Monte Carlo-based load factor forecasting for wind and solar plants to support financial modelling and grid planning. It uses statistical sampling of historical weather patterns with geographical correlation preservation.

## Status

**Early Development**: Significant refactoring needed for production use. The codebase contains calibration scripts from The Low Carbon Contracts Company's internal systems that require adaptation.

## Key Components

- **Wind/Solar Models**: Monte Carlo generators using inverse distribution sampling (`WindData`, `SolarData`)
- **Calibration Scripts**: The Low Carbon Contracts Company workflow scripts for wind/solar parameter calibration (requires Azure/Databricks)
- **Data Loading**: Stub implementation for ERA5 NetCDF data (user must implement)
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
from weather.models import WindData, SolarData

# Monte Carlo wind forecast (not a data loader despite the name)
wind_model = WindData(connection, windstreams=["farm1", "farm2"], 
                     desired_averages=[None, 0.35])
forecast = wind_model.random_Sample(start_date, end_date)
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
