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

### Calibrate wind power curves

With the plant, generation, and ERA5 inputs in place, run the wind calibration
workflow and write its outputs to a separate directory:

```python
from pathlib import Path

from rencal.calibration.wind.wind_calibrator import WindCalibrator

calibrator = WindCalibrator(
    data_path="data",
    output_path=Path("outputs/wind-calibration"),
    visual_output=True,
    stream_npy_output=True,
)
calibrator.calibrate()
```

The workflow writes the calibration summary, Weibull parameters, extracted wind
speeds, calibrated wind streams, and optional power-curve plots to the output
directory. With `stream_npy_output=True`, the generated `Wind Streams.npy` can
also be used by the weather sampler after its manifest and optional histogram
artefacts have been prepared.

### Sample calibrated wind streams

`WeatherData` samples future hourly paths from calibrated historical streams
while preserving the configured time-bucket structure. The local loader expects
the calibrated NPY file and its manifest under `data/calibrated/`.

```python
import datetime
import random

import numpy as np

from rencal.core.data_loader import LocalDataLoader
from rencal.simulation.weather_data import HistoricalMetadata, WeatherData

loader = LocalDataLoader(data_path="data")
manifest = loader.check_historical_weather()
metadata = HistoricalMetadata.from_manifest(
    manifest,
    loader.path_resolver_weather_data,
)

wind_sampler = WeatherData(
    metadata=metadata,
    prefix_histograms=loader.get_prefix_histograms(),
    historical_data=loader.get_historical_weather(),
)

sample = wind_sampler.random_sample(
    datetime.datetime(2027, 1, 1),
    datetime.datetime(2027, 1, 7),
    python_rng=random.Random(4),
    numpy_rng=np.random.default_rng(32),
)
```

Pass `desired_averages` to `WeatherData` when inverse-distribution resampling is
required; this also requires historical data or precomputed prefix histograms.

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
