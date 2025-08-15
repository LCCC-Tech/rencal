"""
Weather Forecasting and Modelling for Renewable Energy

A Python library for forecasting renewable energy generation using ERA5 weather data 
and statistical sampling techniques. Provides calibrated load factor predictions for 
wind and solar plants to support financial modelling and grid planning.
"""

__version__ = "0.1.0"
__author__ = "LCCC Technical Team"
__email__ = "tech@lccc.gov.uk"

# Import main classes for easy access
from .data.loader import ERA5DataLoader
from .models.wind_forecast import WindData
from .models.solar_forecast import SolarData

__all__ = [
    "ERA5DataLoader",
    "WindData", 
    "SolarData",
]