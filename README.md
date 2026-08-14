# RenCal

RenCal (Renewable Calibration) is a Python library for calibrating renewable
energy power curves and generating probabilistic load-factor time series for
wind and solar plants.

It supports Monte Carlo-based forecasting using weather, generation, and plant
characteristic data. RenCal is intended for energy analysts, researchers, and
developers working on renewable-energy modelling.

## Status

RenCal is an experimental pre-1.0 public package. The API and modelling
approach may change as the project develops. It is not currently a guarantee of
production suitability or a substitute for independent validation.

## Installation

The first public release will be installed from PyPI with:

```bash
python -m pip install rencal
```

Until that release is published, clone the repository and follow the
[development setup](CONTRIBUTING.md#development-setup) instead.

## Quick start

The primary workflow uses data supplied by the user. RenCal does not distribute
operational ERA5, generation, or plant datasets.

```python
from pathlib import Path

from rencal.core.data_loader import LocalDataLoader

loader = LocalDataLoader(data_path=Path("data"))
plants = loader.load_plant_data()
generation = loader.load_generation_data()

print(f"Loaded {len(plants.data)} plants")
print(f"Loaded {len(generation.data)} generation records")
```

For the full wind-calibration workflow, provide the expected input structure:

```text
data/
├── plant/plant_data.csv
├── generation/generation_data.parquet
└── era5/*.nc
```

The ERA5 loader expects suitable NetCDF weather data. Users are responsible for
obtaining data, checking its provenance and licence, and preparing it for the
documented schema.

## Main capabilities

- Wind and solar power-curve calibration foundations
- Probabilistic load-factor forecasting
- Weather and generation data loading and validation
- Time-bucketed sampling with geographical correlation support
- Extensible interfaces for local and external data sources

## Documentation

- [Wind calibration tutorial](docs/tutorials/wind_calibration_tutorial.ipynb)
- [Contributing](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Issue tracker](https://github.com/LCCC-Tech/rencal/issues)

Hosted documentation and versioned examples will be linked here once the public
documentation site is verified.

## Support

Use [GitHub Issues](https://github.com/LCCC-Tech/rencal/issues) for public,
reproducible bugs and feature requests. Please do not include credentials,
internal data, or confidential information in issues.

## Licence

RenCal is released under the [MIT Licence](LICENSE).
