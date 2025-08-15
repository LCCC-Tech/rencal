# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Code Style Guidelines

- NEVER add emojis to code files, documentation, or README files
- Keep documentation clean and professional without decorative elements

## Project Overview

This is an open-source weather forecasting and modelling repository for renewable energy applications at The Low Carbon Contracts Company. The project provides tools for wind and solar power generation forecasting using ERA5 weather data and statistical sampling techniques.

## Development Commands

### Installation and Setup
```bash
# Development installation
pip install -e .

# Install development dependencies
pip install -r requirements-dev.txt

# Install with optional dependencies
pip install -e .[dev,azure,databricks]
```

### Code Quality and Testing
```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=weather --cov-report=html

# Run specific test
pytest tests/test_specific.py::test_function

# Code formatting
black weather/
isort weather/

# Linting
flake8 weather/
mypy weather/

# Pre-commit hooks
pre-commit run --all-files
```

### Package Building
```bash
# Build package
python -m build

# Check package
twine check dist/*
```

## Architecture Overview

### Core Components

**Data Layer (`weather.data`)**:
- `ERA5DataLoader`: Stub implementation for loading ERA5 weather data from user-specified directories
- Users must download ERA5 data locally and implement the loading methods

**Model Layer (`weather.models`)**:
- `WindData` / `SolarData`: Monte Carlo/ensemble forecast generators (not data loaders despite names)
- `BucketedData`: Base class for time-bucketed data sampling
- `IntermittentBucketer`: Specialized bucketing for intermittent renewables
- Uses inverse distribution sampling to transform historical distributions

**Calibration Layer (`weather.calibration`)**:
- `wind/`: Contains numbered scripts (01-05) for wind turbine calibration workflows
- `solar/`: Contains numbered scripts (01-03) for solar panel calibration workflows
- Scripts copied directly from The Low Carbon Contracts Company's internal "lego" project with original naming
- Includes Databricks/Azure dependencies and SQL queries

**Common Utilities (`weather.common`)**:
- `constants.py`: Shared constants across calibration and model modules

### Key Architectural Patterns

**Statistical Sampling Framework**:
- Historical weather data is bucketed by time periods
- Monte Carlo sampling preserves geographical correlations
- Inverse CDF transformation adjusts load factor distributions
- PyTorch used for vectorized operations on large datasets

**Calibration Workflow**:
- Scripts follow numbered sequence (01, 02, 03...)
- Process: ERA5 data → Weibull parameters → Power curves → Load factor calibration
- Integration with The Low Carbon Contracts Company's Synapse database and Azure storage

**Legacy Integration**:
- Models inherit from QuantLib architecture (BucketedData, Bucketer classes)
- Calibration scripts use Databricks notebook format with !pip installs
- Database connections expect The Low Carbon Contracts Company-specific infrastructure

## Important Development Notes

### File Naming Conventions
- Calibration scripts maintain original The Low Carbon Contracts Company naming with spaces (e.g., "01 Weibull Parameters.py")
- Model files use PascalCase (e.g., WindData.py, SolarData.py)
- Common utilities use lowercase (e.g., constants.py)

### Dependencies and Environment
- Core package supports Python 3.8+
- Optional dependencies for Azure (`azure`), Databricks (`databricks`), and notebooks (`notebook`)
- Calibration scripts expect Databricks environment with specific database access
- ERA5DataLoader is intentionally stubbed - users provide own implementation

### Data Expectations
- ERA5 NetCDF files with variables: u100, v100 (wind), ssrd, t2m (solar)
- Time series data with hourly resolution
- Location data as DataFrames with lat/lon coordinates
- Load factor calibration against actual CfD settlement data

### Model Usage Pattern
```python
# Models are forecast generators, not data loaders
from weather.models import WindData, SolarData

wind_model = WindData(connection, windstreams=["farm1", "farm2"], 
                     desired_averages=[None, 0.35])
forecast = wind_model.random_Sample(start_date, end_date)
```