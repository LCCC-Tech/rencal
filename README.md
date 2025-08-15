# Weather Forecasting and Modelling

An open-source repository for weather-related forecasting and modelling at LCCC (Low Carbon Contracts Company).

## Overview

This project provides tools and models for weather forecasting with a focus on renewable energy applications, including wind and solar power generation forecasting, demand prediction, and calibration utilities. It leverages ERA5 weather data and statistical sampling techniques to provide calibrated load factor predictions for wind and solar plants to support financial modelling and grid planning.

## Features

- **Wind Power Forecasting**: Advanced models for wind speed and power generation prediction
- **Solar Power Forecasting**: Solar radiation and power output forecasting tools
- **Demand Forecasting**: Energy demand prediction models
- **Calibration Tools**: Comprehensive calibration utilities for renewable energy models
- **Data Processing**: Robust data handling and preprocessing pipelines

## Installation

### Prerequisites

- Python 3.8 or higher
- pip or conda package manager

### Basic Installation

```bash
# Clone the repository
git clone https://github.com/LCCC/weather.git
cd weather

# Install dependencies
pip install -r requirements.txt

# Install the package in development mode
pip install -e .
```

### Conda Installation

```bash
# Create conda environment
conda env create -f environment.yml
conda activate weather-lccc

# Install the package
pip install -e .
```

## Quick Start

```python
from weather.models import WindForecast, SolarForecast
from weather.data import WindData, SolarData

# Load wind data
wind_data = WindData()
wind_data.load('path/to/wind/data')

# Create and train wind forecast model
wind_model = WindForecast()
wind_model.fit(wind_data)

# Make predictions
predictions = wind_model.predict(horizon=24)
```

## Project Structure

```
weather/
├── calibration/      # Calibration scripts for renewable models
│   ├── wind/        # Wind calibration utilities
│   └── solar/       # Solar calibration utilities
├── data/            # Data processing and handling
├── models/          # Forecasting models
├── scripts/         # Utility scripts
└── tests/           # Test suite
```

## Documentation

Comprehensive documentation is available in the [docs/](docs/) directory.

## Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details on how to submit pull requests, report issues, and contribute to the project.

## Testing

Run the test suite with:

```bash
pytest tests/
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

This project builds upon research and methodologies developed at LCCC for renewable energy forecasting and grid management.

## Contact

For questions and support, please open an issue on GitHub or contact the LCCC technical team.

## Citation

If you use this software in your research, please cite:

```bibtex
@software{lccc_weather_2025,
  title = {Weather Forecasting and Modelling for Renewable Energy},
  author = {LCCC Technical Team},
  year = {2025},
  url = {https://github.com/LCCC/weather}
}
```
