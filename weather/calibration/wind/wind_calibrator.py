"""Extracts data from input files and calibreates wind power curves."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from matplotlib import pyplot as plt
from scipy.integrate import quad
from scipy.optimize import curve_fit
from scipy.stats import weibull_min

from ...utils.constants import (
    DEFAULT_LOGISTIC_FN_ASYMMETRY,
    DEFAULT_LOGISTIC_FN_STEEPNESS,
    DEFAULT_LOGISTIC_FN_XLOC,
    DEFAULT_WIND_VARIABLES,
    ERA5_VARIABLE_MAPPING,
    INTERNAL_PLANT_ID,
    LOGISTIC_FN_ASYMMETRY_HBOUND,
    LOGISTIC_FN_ASYMMETRY_LBOUND,
    LOGISTIC_FN_MAXEVAL,
    LOGISTIC_FN_STEEPNESS_HBOUND,
    LOGISTIC_FN_STEEPNESS_LBOUND,
    LOGISTIC_FN_XLOC_HBOUND,
    LOGISTIC_FN_XLOC_LBOUND,
    PLANT_ID_COLUMN,
    PLANT_ID_OUTPUT,
    WIND_SPEED_HBOUND,
    WIND_SPEED_LBOUND,
    WIND_TECHNOLOGY_TYPES,
)
from ...utils.logger import get_logger
from ..calibrator import Calibrator

logger = get_logger(__name__)


class WindCalibrator(Calibrator):
    """Calibrates wind power curves for a set of timestamps and CFD IDs."""

    def __init__(self, data_path: str = None, plant_id_col: str = None, output_path: str = Path.cwd(), visual_output: bool = False) -> None:
        """Constructor for the WindCalibrator class."""
        super_args = {}
        if data_path:
            super_args["data_path"] = data_path
        if plant_id_col:
            super_args["plant_id_col"] = plant_id_col
            logger.debug("Runtime-specified plant id column: %s", plant_id_col)
        else:
            plant_id_col = PLANT_ID_COLUMN
            logger.debug("Config-specified plant id column: %s", PLANT_ID_COLUMN)
        super().__init__(**super_args)
        self.plants.data = self.plants.data[self.plants.data["technology"].isin(WIND_TECHNOLOGY_TYPES)]
        self.all_plant_ids = self.generation.data[INTERNAL_PLANT_ID].unique()
        self.output_path = output_path
        self.visual_output = visual_output
        self.plant_wind_speeds: pd.DataFrame
        self.historical_load_factors: pd.DataFrame
        self.historical_load_factor_distributions: pd.DataFrame

    def calibrate(self) -> None:
        """Triggers calibration workflow."""
        logger.info("Starting calibration process...")
        self.plant_wind_speeds = self.extract_resource_timeseries_for_plants()
        self.historical_load_factors = self.calculate_historical_load_factors()
        self.historical_load_factor_distributions = self.fit_historical_load_factor_distribution()
        self.summary = self.estimate_load_factors_for_resource()
        if self.visual_output:
            self.output_estimated_load_factors_visual()
        self._rename_output_summary_columns()
        self.output_estimated_load_factors_tabular()
        logger.info("Calibration finished!")

    def extract_resource_timeseries_for_plants(self) -> pd.DataFrame:
        """Extracts resource data for plants into a DataFrame."""
        self.resource.data["wind_speed"] = np.sqrt(
            self.resource.data[ERA5_VARIABLE_MAPPING[DEFAULT_WIND_VARIABLES[0]]] ** 2
            + self.resource.data[ERA5_VARIABLE_MAPPING[DEFAULT_WIND_VARIABLES[1]]] ** 2
        )
        unique_plant_locations = self.plants.data[
            self.plants.data[INTERNAL_PLANT_ID].isin(self.all_plant_ids)
        ].drop_duplicates(INTERNAL_PLANT_ID)[[INTERNAL_PLANT_ID, "latitude", "longitude"]]
        unique_plant_dim = xr.DataArray(unique_plant_locations[INTERNAL_PLANT_ID].to_numpy(), dims=INTERNAL_PLANT_ID)
        plant_wind_speeds = self.resource.data.sel(
            longitude=xr.DataArray(unique_plant_locations["longitude"].to_numpy(), dims=INTERNAL_PLANT_ID),
            latitude=xr.DataArray(unique_plant_locations["latitude"].to_numpy(), dims=INTERNAL_PLANT_ID),
            method="nearest"
        )
        plant_wind_speeds[INTERNAL_PLANT_ID] = unique_plant_dim
        plant_wind_speed_res = plant_wind_speeds.to_dataframe().reset_index(drop=False)[["time", INTERNAL_PLANT_ID, "wind_speed"]]
        plant_wind_speed_res["time"] = pd.to_datetime(plant_wind_speed_res["time"], utc=True)
        return plant_wind_speed_res

    @staticmethod
    def _get_plant_generation_temporal_bounds(generation_data:pd.DataFrame) -> pd.DataFrame:
        """Gets the first and last timestamp a plant has generation data for."""
        return (
            generation_data.groupby(INTERNAL_PLANT_ID)["time"]
            .agg(hourly_start="min", hourly_end="max")
            .reset_index()
        )

    @staticmethod
    def _remove_duplicate_plant_time_from_generation(generation_data: pd.DataFrame) -> pd.DataFrame:
        """Aggregates generation quantities for potentialy rows where plant id and timestamp are equal."""
        return generation_data.groupby(
            [INTERNAL_PLANT_ID, "time"], as_index=False, sort=False
        ).agg({"quantity": "sum"})

    def calculate_historical_load_factors(self) -> pd.DataFrame:
        """Calculates historical load factors based on resource availability and generation data for each plant."""
        self.plant_wind_speeds[INTERNAL_PLANT_ID] = self.plant_wind_speeds[INTERNAL_PLANT_ID].astype(str)
        self.generation.data[INTERNAL_PLANT_ID] = self.generation.data[INTERNAL_PLANT_ID].astype(str)
        self.generation.data = self._remove_duplicate_plant_time_from_generation(self.generation.data)
        coverage = self._get_plant_generation_temporal_bounds(self.generation.data)
        self.plant_wind_speeds = self.plant_wind_speeds[self.plant_wind_speeds[INTERNAL_PLANT_ID].isin(self.all_plant_ids)].copy()
        self.plant_wind_speeds = self.plant_wind_speeds.merge(coverage, on=INTERNAL_PLANT_ID, how="left")
        mask = self.plant_wind_speeds["time"].between(
            self.plant_wind_speeds["hourly_start"], self.plant_wind_speeds["hourly_end"]
        )
        self.plant_wind_speeds = self.plant_wind_speeds.loc[mask, ["time", INTERNAL_PLANT_ID, "wind_speed"]].copy()
        wind_speed_generation_merged = pd.merge(
            self.plant_wind_speeds,
            self.generation.data,
            on=["time", INTERNAL_PLANT_ID],
            how="left"
        )
        wind_speed_generation_merged["load_factor"] = (
            wind_speed_generation_merged["quantity"].fillna(0)
            / wind_speed_generation_merged.groupby(INTERNAL_PLANT_ID)["quantity"].transform("max")
        )
        numeric_cols = wind_speed_generation_merged.select_dtypes(include=["number"]).columns
        wind_speed_generation_merged[numeric_cols] = wind_speed_generation_merged[numeric_cols].round(2)
        return wind_speed_generation_merged

    @staticmethod
    def fit_weibull_dist_to_plant(item):
        cfd_id, speeds = item
        clean_speeds = speeds.dropna().values
        if len(clean_speeds) < 3:  # skip if not enough points
            return cfd_id, np.nan, np.nan
        k, _, lamb = weibull_min.fit(clean_speeds, floc=0)
        return cfd_id, k, lamb

    def fit_historical_load_factor_distribution(self) -> pd.DataFrame:
        """Fits probability distribution to historical load factors and resource availability."""
        wind_speeds = self.historical_load_factors.groupby(INTERNAL_PLANT_ID, sort=False)["wind_speed"]
        wind_speed_stats = wind_speeds.agg(wind_speed_mean="mean", wind_speed_stdev="std")
        with ThreadPoolExecutor(max_workers=8)as ex:
            fits = list(ex.map(self.fit_weibull_dist_to_plant, wind_speeds))
        fitted_distributions = pd.DataFrame(fits, columns=[INTERNAL_PLANT_ID, "k", "lambda"])
        weibull_params = wind_speed_stats.reset_index().merge(
            fitted_distributions, on=INTERNAL_PLANT_ID, sort=False
        )
        return weibull_params

    def estimate_load_factors_for_resource(self) -> pd.DataFrame:
        """Estimates load factors based on the historical distribution and the whole resource availability history."""
        summary = pd.DataFrame(columns=[
            INTERNAL_PLANT_ID, "a", "b", "c", "d", "g", "estimated_load_factor"
        ])
        for plant_id in self.all_plant_ids:
            single_plant_load_factors = self.historical_load_factors[self.historical_load_factors[INTERNAL_PLANT_ID] == plant_id].copy()
            single_plant_load_factor_dist_params = self.historical_load_factor_distributions[
                self.historical_load_factor_distributions[INTERNAL_PLANT_ID] == plant_id
            ]
            if single_plant_load_factors.empty or single_plant_load_factor_dist_params.empty:
                logger.warning(f"Skipping {plant_id} (no data or Weibull params).")
                continue
            single_plant_load_factors = self.drop_invalid_rows(single_plant_load_factors)
            if single_plant_load_factors.empty:
                logger.warning(f"Skipping {plant_id} (no valid numeric data).")
                continue
            single_plant_load_factors = self.clip_extreme_wind_speeds(single_plant_load_factors)
            lambda_val = single_plant_load_factor_dist_params["lambda"].iloc[0]
            k_val = single_plant_load_factor_dist_params["k"].iloc[0]

            try:
                logistic_params, _ = curve_fit(
                    self.logistic_function,
                    single_plant_load_factors["wind_speed"].to_numpy(),
                    single_plant_load_factors["load_factor"].to_numpy(),
                    p0=[DEFAULT_LOGISTIC_FN_STEEPNESS, DEFAULT_LOGISTIC_FN_XLOC, DEFAULT_LOGISTIC_FN_ASYMMETRY],
                    bounds=[
                        [LOGISTIC_FN_STEEPNESS_LBOUND, LOGISTIC_FN_XLOC_LBOUND, LOGISTIC_FN_ASYMMETRY_LBOUND],
                        [LOGISTIC_FN_STEEPNESS_HBOUND, LOGISTIC_FN_XLOC_HBOUND, LOGISTIC_FN_ASYMMETRY_HBOUND]
                    ],
                    maxfev=LOGISTIC_FN_MAXEVAL
                )
            except Exception as e:
                logger.warning(f"Skipping {plant_id} (curve fit failed: {e})")
                continue

            try:
                estimated_load_factor = quad(
                    lambda x: self.logistic_function(x, *logistic_params)
                              * (k_val / lambda_val)
                              * (x / lambda_val)**(k_val - 1)
                              * np.exp(-((x / lambda_val)**k_val)),
                    0, np.inf
                )[0]
            except Exception as e:
                logger.warning(f"Integration failed for {plant_id}: {e}")
                continue

            summary.loc[len(summary)] = [
                plant_id,
                0,
                logistic_params[0],
                logistic_params[1],
                1,
                logistic_params[2],
                estimated_load_factor
            ]
            summary["estimated_load_factor"] = summary["estimated_load_factor"].round(4)
        return summary

    @staticmethod
    def logistic_function(x, b, c, g):
        """Defines a generalised logistic function."""
        a = 0
        d = 1
        return d + (a - d) / ((1 + (x / c)**b)**g)

    @staticmethod
    def drop_invalid_rows(cfd_data: pd.DataFrame) -> pd.DataFrame:
        """Drops rows with no valid data."""
        return cfd_data.replace([np.inf, -np.inf], np.nan).dropna(subset=["wind_speed", "load_factor"])

    @staticmethod
    def clip_extreme_wind_speeds(cfd_wind_data: pd.DataFrame) -> pd.DataFrame:
        """Clips wind speeds above and below sensible thresholds to avoid overflow in power."""
        return cfd_wind_data[cfd_wind_data["wind_speed"].between(WIND_SPEED_LBOUND, WIND_SPEED_HBOUND)]

    def _rename_output_summary_columns(self) -> None:
        """Renames output table columns to expected and/or more human-readable values."""
        self.summary.columns.rename({
            INTERNAL_PLANT_ID: PLANT_ID_OUTPUT,
            "estimated_load_factor": "Estimated Load Factor",
        })

    def output_estimated_load_factors_tabular(self) -> None:
        """Outputs table of estimated load factors for whole resource availability history."""
        self.summary.to_csv(self.output_path / f"PowerCurveFitSummary_{datetime.now()}.csv", index=False)

    def output_estimated_load_factors_visual(self) -> None:
        """Outputs a series of plots of estimated load and fitted curves per CfD plant."""
        for row in self.summary.iterrows():
            x_vals = np.linspace(0, 25, 300)
            y_vals = self.logistic_function(x_vals, row["b"], row["c"], row["g"])
            mean_wind_speed = cfd_data["wind_speed"].mean()
            plt.figure(figsize=(10, 6))
            plt.scatter(cfd_data["wind_speed"], cfd_data["load_factor"], s=10, color="blue", alpha=0.6, label="Observed Data")
            plt.plot(x_vals, y_vals, color="orange", lw=3, label="Fitted Curve")
            plt.axvline(mean_wind_speed, color="green", linestyle="--", lw=2, label=f"Mean Wind Speed = {mean_wind_speed:.2f} m/s")
            plt.title(f"Power Curve Fit - {self.summary[PLANT_ID_COLUMN]}")
            plt.xlabel("Wind Speed (m/s)")
            plt.ylabel("Load Factor")
            plt.legend()
            plt.grid(True)
            plt.savefig(self.output_path / f"PowerCurveFit_{self.summary[PLANT_ID_OUTPUT]}.png")
