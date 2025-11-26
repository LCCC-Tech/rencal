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
        self.plant_wind_speeds = None

    def calibrate(self) -> None:
        """Triggers calibration workflow."""
        logger.info("Starting calibration process...")
        self.plant_wind_speeds = self.extract_resource_timeseries_for_plants()
        self.calculate_historical_load_factors()
        self.fit_historical_load_factor_distribution()
        self.estimate_load_factors_for_resource()
        self.output_estimated_load_factors_tabular(self.output_path)
        if self.visual_output:
            self.output_estimated_load_factors_visual(self.output_path)
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
    def _get_unique_plant_ids_from_generation(generation_data: pd.DataFrame) -> pd.Series:
        """Extracts a series of all the unique plant ids featured in the generation data."""
        return generation_data[INTERNAL_PLANT_ID].unique()

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

    def calculate_historical_load_factors(self) -> None:
        """Calculates historical load factors based on resource availability and generation data for each plant."""
        self.plant_wind_speeds[INTERNAL_PLANT_ID] = self.plant_wind_speeds[INTERNAL_PLANT_ID].astype(str)
        self.generation.data[INTERNAL_PLANT_ID] = self.generation.data[INTERNAL_PLANT_ID].astype(str)
        self.generation.data = self._remove_duplicate_plant_time_from_generation(self.generation.data)
        coverage = self._get_plant_generation_temporal_bounds(self.generation.data)
        valid_cfds = self._get_unique_plant_ids_from_generation(self.generation.data)
        self.plant_wind_speeds = self.plant_wind_speeds[self.plant_wind_speeds[INTERNAL_PLANT_ID].isin(valid_cfds)].copy()
        self.plant_wind_speeds = self.plant_wind_speeds.merge(coverage, on=INTERNAL_PLANT_ID, how="left")
        mask = self.plant_wind_speeds["time"].between(
            self.plant_wind_speeds["hourly_start"], self.plant_wind_speeds["hourly_end"]
        )
        self.plant_wind_speeds = self.plant_wind_speeds.loc[mask, ["time", INTERNAL_PLANT_ID, "wind_speed"]].copy()
        self.wind_speed_generation_merged = pd.merge(
            self.plant_wind_speeds,
            self.generation.data,
            on=["time", INTERNAL_PLANT_ID],
            how="left"
        )
        self.wind_speed_generation_merged["load_factor"] = (
            self.wind_speed_generation_merged["quantity"].fillna(0)
            / self.wind_speed_generation_merged.groupby(INTERNAL_PLANT_ID)["quantity"].transform("max")
        )
        numeric_cols = self.wind_speed_generation_merged.select_dtypes(include=["float", "int"]).columns
        self.wind_speed_generation_merged[numeric_cols] = self.wind_speed_generation_merged[numeric_cols].round(2)

    @staticmethod
    def fit_weibull_dist_to_plant(item):
        cfd_id, speeds = item
        clean_speeds = speeds.dropna().values
        if len(clean_speeds) < 3:  # skip if not enough points
            return cfd_id, np.nan, np.nan
        k, _, lamb = weibull_min.fit(clean_speeds, floc=0)
        return cfd_id, k, lamb

    def fit_historical_load_factor_distribution(self) -> None:
        """Fits probability distribution to historical load factors and resource availability."""
        wind_speeds = self.generation.data.groupby("CFD_Id", sort=False)["Wind Speed"]
        wind_speed_stats = wind_speeds.agg(mean_wind_speed="mean", wind_speed_stdev="std")
        with ThreadPoolExecutor(max_workers=8)as ex:
            fits = list(ex.map(self.fit_weibull_dist_to_plant, wind_speeds))
        fitted_distributions = pd.DataFrame(fits, columns=["CFD_Id", "k", "Lambda"])
        self.weibull_params = wind_speed_stats.reset_index().merge(
            fitted_distributions, on="CFD_Id", sort=False
        )

    def estimate_load_factors_for_resource(self) -> None:
        """Estimates load factors based on the historical distribution and the whole resource availability history."""
        self.summary = pd.DataFrame(columns=[
            "CFD_Id", "a", "b", "c", "d", "g", "Estimated Load Factor"
        ])
        for cfd_id in self.all_plant_ids:
            merged_cfd_data = self.era5_generation_merged[self.era5_generation_merged["CFD_Id"] == cfd_id].copy()
            cfd_weibull_params = self.weibull_params[self.weibull_params["CFD_Id"] == cfd_id]
            if merged_cfd_data.empty():
                print(f"Skipping {cfd_id} (no data or Weibull params).")
                continue
            merged_cfd_data = self.drop_invalid_rows(merged_cfd_data)
            if merged_cfd_data.empty():
                print(f"Skipping {cfd_id} (no valid numeric data).")
            merged_cfd_data = self.clip_extreme_wind_speeds(merged_cfd_data)
            lambda_val = cfd_weibull_params["Lambda"].iloc[0]
            k_val = cfd_weibull_params["k"].iloc[0]

            try:
                logistic_params, _ = curve_fit(
                    self.logistic_function,
                    merged_cfd_data["Wind Speed"],
                    merged_cfd_data["Load Factor"],
                    p0=[
                        DEFAULT_LOGISTIC_FN_STEEPNESS,
                        DEFAULT_LOGISTIC_FN_XLOC,
                        DEFAULT_LOGISTIC_FN_ASYMMETRY
                    ],  # Initial guess for params -> default generic wind turbine power curve params
                    bounds=[
                        [
                            LOGISTIC_FN_STEEPNESS_LBOUND,
                            LOGISTIC_FN_XLOC_LBOUND,
                            LOGISTIC_FN_ASYMMETRY_LBOUND
                        ],
                        [
                            LOGISTIC_FN_STEEPNESS_HBOUND,
                            LOGISTIC_FN_XLOC_HBOUND,
                            LOGISTIC_FN_ASYMMETRY_HBOUND
                        ]
                    ], # change upper bound to 500 to coincide with currently used scripts
                    maxfev=LOGISTIC_FN_MAXEVAL
                )
            except Exception as e:
                print(f"Skipping {cfd_id} (curve fit failed: {e})")
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
                print(f"Integration failed for {cfd_id}: {e}")
                continue

            self.summary.loc[len(self.summary)] = [
                cfd_id,
                0,
                logistic_params[0],
                logistic_params[1],
                1,
                logistic_params[2],
                estimated_load_factor
            ]
            self.summary["Estimated Load Factor"] = self.summary["Estimated Load Factor"].round(4)

    @staticmethod
    def logistic_function(x, b, c, g):
        """Defines a generalised logistic function."""
        a = 0
        d = 1
        return d + (a - d) / ((1 + (x / c)**b)**g)

    @staticmethod
    def drop_invalid_rows(cfd_data: pd.DataFrame) -> pd.DataFrame:
        """Drops rows with no valid data."""
        return cfd_data.replace([np.inf, -np.inf], np.nan).dropna(subset=["Wind Speed", "Load Factor"])

    @staticmethod
    def clip_extreme_wind_speeds(cfd_wind_data: pd.DataFrame) -> pd.DataFrame:
        """Clips wind speeds above and below sensible thresholds to avoid overflow in power."""
        return cfd_wind_data[cfd_wind_data["Wind Speed"].between(WIND_SPEED_LBOUND, WIND_SPEED_HBOUND)]

    def output_estimated_load_factors_tabular(self, out_path: str | Path) -> None:
        """Outputs table of estimated load factors for whole resource availability history."""
        self.summary.to_csv(out_path / f"PowerCurveFitSummary_{datetime.now()}.csv", index=False)

    def output_estimated_load_factors_visual(self, summary_data: pd.DataFrame, cfd_data: pd.DataFrame) -> None:
        """Outputs a series of plots of estimated load and fitted curves per CfD plant."""
        for row in self.summary.iterrows():
            x_vals = np.linspace(0, 25, 300)
            y_vals = self.logistic_function(x_vals, row["b"], row["c"], row["g"])
            mean_wind_speed = cfd_data["Wind Speed"].mean()
            plt.figure(figsize=(10, 6))
            plt.scatter(cfd_data["Wind Speed"], cfd_data["Load Factor"], s=10, color="blue", alpha=0.6, label="Observed Data")
            plt.plot(x_vals, y_vals, color="orange", lw=3, label="Fitted Curve")
            plt.axvline(mean_wind_speed, color="green", linestyle="--", lw=2, label=f"Mean Wind Speed = {mean_wind_speed:.2f} m/s")
            plt.title(f"Power Curve Fit - {summary_data["CFD_Id"]}")
            plt.xlabel("Wind Speed (m/s)")
            plt.ylabel("Load Factor")
            plt.legend()
            plt.grid(True)
            plt.savefig(self.output_path / f"PowerCurveFit_{summary_data["CFD_Id"]}.png")
