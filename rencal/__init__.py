"""
Renewable Calibration (rencal) for renwable energy forecasting.

A Python library for calibrating renewable plant power curves using generalised logistic function
modules for generating probabilistic load factor time series forecasts using resampling from
historical ERA5 weather data.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("rencal")
except PackageNotFoundError:
    __version__ = "0+unknown"
__author__ = "Low Carbon Contracts Company Ltd"
__email__ = "analytics@lowcarboncontracts.uk"
