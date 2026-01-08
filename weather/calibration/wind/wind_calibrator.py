"""Extracts data from input files and calibreates wind power curves."""

from concurrent.futures import ThreadPoolExecutor
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

    def __init__(self, data_path: str = None, plant_id_col: str = None, output_path: str | Path = Path.cwd(), visual_output: bool = False) -> None:
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
        self.calibration_plant_ids = self.generation.data[INTERNAL_PLANT_ID].unique()
        self.output_path = output_path if isinstance(output_path, Path) else Path(output_path)
        self.visual_output = visual_output
        self.plant_wind_speeds: pd.DataFrame
        self.historical_load_factors: pd.DataFrame
        self.historical_load_factor_distributions: pd.DataFrame
        self.historical_combined: pd.DataFrame

    def calibrate(self) -> None:
        """Triggers calibration workflow."""
        logger.info("Starting calibration process...")
        self.plant_wind_speeds = self.extract_resource_timeseries_for_plants()
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.output_resource_per_plant()
        self.generation.data = self._clip_generation_to_plant_capacity()
        self.historical_load_factors = self.calculate_historical_load_factors()
        self.historical_load_factor_distributions = self.fit_historical_load_factor_distribution()
        self.output_historical_load_factor_distribution_parameters()
        self.summary = self.estimate_load_factors_for_resource()
        self._create_generic_power_curve()
        self._rename_output_summary_columns()
        self.output_estimated_load_factors_tabular()
        self.wind_streams = self.generate_resource_streams()
        self.output_resource_streams()
        logger.info("Calibration finished!")

    def extract_resource_timeseries_for_plants(self) -> pd.DataFrame:
        """Extracts resource data for plants into a DataFrame."""
        # If there is initial release data (expver=5) downloaded, it gets used to fill NaNs in the verified ERA5 data
        if "expver" in self.resource.data.coords:
            logger.info("Combining final and initial release data for resource...")
            self.resource.data = self.resource.data.sel(expver=1).combine_first(self.resource.data.sel(expver=5))
        self.resource.data["wind_speed"] = np.sqrt(
            self.resource.data[ERA5_VARIABLE_MAPPING[DEFAULT_WIND_VARIABLES[0]]] ** 2
            + self.resource.data[ERA5_VARIABLE_MAPPING[DEFAULT_WIND_VARIABLES[1]]] ** 2
        )
        unique_plant_locations = self.plants.data.drop_duplicates([INTERNAL_PLANT_ID, "latitude", "longitude"])
        unique_plant_dim = xr.DataArray(unique_plant_locations[INTERNAL_PLANT_ID], dims=INTERNAL_PLANT_ID)
        plant_wind_speeds = self.resource.data.sel(
            longitude=xr.DataArray(unique_plant_locations["longitude"], dims=INTERNAL_PLANT_ID),
            latitude=xr.DataArray(unique_plant_locations["latitude"], dims=INTERNAL_PLANT_ID),
            method="nearest"
        )
        plant_wind_speeds[INTERNAL_PLANT_ID] = unique_plant_dim
        plant_wind_speed_res = plant_wind_speeds.to_dataframe().reset_index(drop=False)[["time", INTERNAL_PLANT_ID, "wind_speed"]]
        plant_wind_speed_res["time"] = pd.to_datetime(plant_wind_speed_res["time"], utc=True)
        return plant_wind_speed_res

    @staticmethod
    def _get_plant_generation_temporal_bounds(generation_data: pd.DataFrame) -> pd.DataFrame:
        """
        Gets the first and last timestamp a plant has generation data for.
        
        Args:
            generation_data (pd.DataFrame): Generation dataset.

        Returns:
            pd.DataFrame: DataFrame containing the temporal bounds of generation availability for each plant.
        
        """
        return (
            generation_data.groupby(INTERNAL_PLANT_ID)["time"]
            .agg(hourly_start="min", hourly_end="max")
            .reset_index()
        )

    def _clip_generation_to_plant_capacity(self) -> pd.DataFrame:
        """Clips maximum generation to the capacity of the plant."""
        gen_with_capacity = self.generation.data.merge(self.plants.data, how="left", on=INTERNAL_PLANT_ID).drop_duplicates([INTERNAL_PLANT_ID, "time"])
        over_gen_mask = gen_with_capacity["quantity"] > gen_with_capacity["capacity"]
        gen_with_capacity.loc[over_gen_mask, "quantity"] = gen_with_capacity.loc[over_gen_mask, "capacity"]
        return gen_with_capacity[self.generation.data.columns]

    @staticmethod
    def _remove_duplicate_plant_time_from_generation(generation_data: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregates generation quantities for potentialy rows where plant id and timestamp are equal.
        
        Args:
            generation_data (pd.DataFrame): Generation dataset.

        Returns:
            pd.DataFrame: Generation dataset with potentially duplicated plant-time combinations removed and their quantities summed.
        
        """
        return generation_data.groupby(
            [INTERNAL_PLANT_ID, "time"], as_index=False, sort=False
        ).agg({"quantity": "sum"})

    def calculate_historical_load_factors(self) -> pd.DataFrame:
        """Calculates historical load factors based on resource availability and generation data for each plant."""
        self.plant_wind_speeds[INTERNAL_PLANT_ID] = self.plant_wind_speeds[INTERNAL_PLANT_ID].astype(str)
        self.generation.data[INTERNAL_PLANT_ID] = self.generation.data[INTERNAL_PLANT_ID].astype(str)
        self.generation.data = self._remove_duplicate_plant_time_from_generation(self.generation.data)
        coverage = self._get_plant_generation_temporal_bounds(self.generation.data)
        calibration_plant_wind_speeds = self.plant_wind_speeds[self.plant_wind_speeds[INTERNAL_PLANT_ID].isin(self.calibration_plant_ids)]
        calibration_plant_wind_speeds = calibration_plant_wind_speeds.merge(coverage, on=INTERNAL_PLANT_ID, how="left")
        mask = calibration_plant_wind_speeds["time"].between(
            calibration_plant_wind_speeds["hourly_start"], calibration_plant_wind_speeds["hourly_end"]
        )
        calibration_plant_wind_speeds = calibration_plant_wind_speeds.loc[mask, ["time", INTERNAL_PLANT_ID, "wind_speed"]]
        wind_speed_generation_merged = pd.merge(
            calibration_plant_wind_speeds,
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
    def _fit_weibull_dist_to_plant(item):
        """Fits a Weibull distribution to an array of wind speeds."""
        cfd_id, speeds = item
        if len(speeds) < 3:  # skip if not enough points
            return cfd_id, np.nan, np.nan
        k, _, lamb = weibull_min.fit(speeds, floc=0)
        return cfd_id, k, lamb

    def fit_historical_load_factor_distribution(self) -> pd.DataFrame:
        """Fits probability distribution to historical load factors and resource availability."""
        wind_speeds = self.historical_load_factors.groupby(INTERNAL_PLANT_ID, sort=False)["wind_speed"]
        wind_speed_stats = wind_speeds.agg(wind_speed_mean="mean", wind_speed_stdev="std")
        wind_speeds = [(plant_id, wind_speed.dropna().to_numpy()) for plant_id, wind_speed in wind_speeds]
        with ThreadPoolExecutor(max_workers=8)as ex:
            fits = list(ex.map(self._fit_weibull_dist_to_plant, wind_speeds))
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
        self.historical_load_factors = self._clip_extreme_wind_speeds(self.historical_load_factors)
        self.historical_load_factors = self._drop_invalid_rows(self.historical_load_factors)
        for plant_id in self.calibration_plant_ids:
            single_plant_load_factors = self.historical_load_factors[self.historical_load_factors[INTERNAL_PLANT_ID] == plant_id]
            single_plant_load_factor_dist_params = self.historical_load_factor_distributions[
                self.historical_load_factor_distributions[INTERNAL_PLANT_ID] == plant_id
            ]
            if single_plant_load_factors.empty or single_plant_load_factor_dist_params.empty:
                logger.warning(f"Skipping {plant_id} (no valid data or Weibull params).")
                continue
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
                    lambda x, logistic_params, k_val, lambda_val: self.logistic_function(x, *logistic_params)
                        * (k_val / lambda_val * (x / lambda_val)**(k_val - 1) * np.exp(-((x / lambda_val)**k_val))),
                    0, np.inf, (logistic_params, k_val, lambda_val)
                )[0]
            except Exception as e:
                logger.warning(f"Integration failed for {plant_id}: {e}")
                continue

            if self.visual_output:
                self.output_estimated_load_factors_visual(logistic_params, single_plant_load_factors)

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
            if len(summary) < 1:
                raise ValueError("No calibration summary rows were produced.")
        return summary

    @staticmethod
    def logistic_function(x, b, c, g):
        """
        Defines a generalised logistic function in the log domain for stability.
        
        Args:
            x (int | float | np.ndarray): Input variable(s), i. e.: wind speed.
            b (float): Steepness parameter of the generalised logistic function.
            c (float): X-axis inflection point location parameter of the generalised logistic function.
            g (float): Asymmetry parameter of the generalised logistic function.

        Returns:
            int | float | np.ndarray: The outputs of the generalised logistic function for each x value with the specified shape parameters.
        
        """
        x_arr = np.asarray(x)
        x_mask = x_arr != 0
        output = np.zeros_like(x_arr)
        output[x_mask] = 1.0 - np.exp(-g * np.logaddexp(0.0, b * (np.log(x_arr[x_mask]) - np.log(c))))
        return output.item() if output.ndim == 0 else output

    @staticmethod
    def _drop_invalid_rows(cfd_data: pd.DataFrame) -> pd.DataFrame:
        """
        Drops rows with no valid data, eliminating positive and negative infinity values.
        
        Args:
            cfd_data (pd.DataFrame): DataFrame containing potentially invalid rows.

        Returns:
            pd.DataFrame: DataFrame without invalid rows.
        
        """
        return cfd_data.replace([np.inf, -np.inf], np.nan).dropna(subset=["wind_speed", "load_factor"])

    @staticmethod
    def _clip_extreme_wind_speeds(cfd_wind_data: pd.DataFrame) -> pd.DataFrame:
        """
        Clips wind speeds above and below sensible thresholds to avoid overflow in power.
        
        Args:
            cfd_wind_data (pd.DataFrame): DataFrame containing wind speed data.

        Returns:
            pd.DataFrame: DataFrame with too low or high wind speeds removed.
        
        """
        return cfd_wind_data[cfd_wind_data["wind_speed"].between(WIND_SPEED_LBOUND, WIND_SPEED_HBOUND)]

    def _create_generic_power_curve(self) -> None:
        """Generates generic power curve parameters from available fitted data."""
        self.summary.loc[len(self.summary)] = ["GEN", 0, self.summary["b"].mean(), self.summary["c"].mean(), 1, self.summary["g"].mean(), 0]

    def generate_resource_streams(self) -> None:
        """Generates wind streams from fitted and/or generalised power curve parameters and long-term wind data."""
        plant_wind_speed_and_params = self.plant_wind_speeds.merge(self.summary, left_on=INTERNAL_PLANT_ID, right_on=PLANT_ID_OUTPUT, how="left", indicator=True)
        plant_wind_speed_and_params.loc[plant_wind_speed_and_params["_merge"] == "left_only", self.summary.columns] = self.summary.iloc[-1].values
        plant_wind_speed_and_params.drop(columns="_merge")
        plant_wind_speed_and_params["load_factor"] = self.logistic_function(
            plant_wind_speed_and_params["wind_speed"],
            plant_wind_speed_and_params["b"],
            plant_wind_speed_and_params["c"],
            plant_wind_speed_and_params["g"]
        )
        plant_wind_speed_and_params = plant_wind_speed_and_params.drop(columns=list(self.summary.columns) + ["_merge", "wind_speed"])
        plant_wind_speed_and_params = (
            plant_wind_speed_and_params
                .pivot(index="time", columns=INTERNAL_PLANT_ID, values="load_factor")
                .sort_index()
                .reset_index()
                .rename(columns={"time": "Times"})
        )
        return plant_wind_speed_and_params

    def _rename_output_summary_columns(self) -> None:
        """Renames output table columns to expected and/or more human-readable values."""
        self.summary = self.summary.rename(columns={
            INTERNAL_PLANT_ID: PLANT_ID_OUTPUT,
            "estimated_load_factor": "Estimated Load Factor",
        })

    def output_historical_load_factor_distribution_parameters(self) -> None:
        """Writes historical load factor parameters to a CSV file."""
        self.historical_load_factor_distributions.to_csv(self.output_path / "Weibull Params.csv", index=False)

    def output_resource_per_plant(self) -> None:
        """Writes resource time series for each plant to a CSV file."""
        self.plant_wind_speeds.to_csv(self.output_path / "Wind Speeds.csv", index=False)

    def output_resource_streams(self) -> None:
        """Writes resource streams to a parquet file."""
        self.wind_streams.to_parquet(self.output_path / "Wind Streams.parquet", index=False)

    def output_estimated_load_factors_tabular(self) -> None:
        """Outputs table of estimated load factors for whole resource availability history."""
        self.summary.to_csv(self.output_path / "Calibration Summary.csv", index=False)

    def output_estimated_load_factors_visual(self, logistic_params: np.ndarray, load_factors: pd.DataFrame) -> None:
        """Outputs a series of plots of estimated load and fitted curves per plant."""
        x_vals = np.linspace(0, 25, 300)
        y_vals = self.logistic_function(x_vals, b=logistic_params[0], c=logistic_params[1], g=logistic_params[2])
        mean_wind_speed = load_factors["wind_speed"].mean()
        plt.figure(figsize=(10, 6))
        plt.scatter(load_factors["wind_speed"], load_factors["load_factor"], s=10, color="blue", alpha=0.6, label="Observed Data")
        plt.plot(x_vals, y_vals, color="orange", lw=3, label="Fitted Curve")
        plt.axvline(mean_wind_speed, color="green", linestyle="--", lw=2, label=f"Mean Wind Speed = {mean_wind_speed:.2f} m/s")
        logger.info(load_factors[INTERNAL_PLANT_ID].iloc[0])
        plt.title(f"Power Curve Fit - {load_factors[INTERNAL_PLANT_ID].iloc[0]}")
        plt.xlabel("Wind Speed (m/s)")
        plt.ylabel("Load Factor")
        plt.legend()
        plt.grid(True)
        plt.savefig(self.output_path / f"PowerCurveFit_{load_factors[INTERNAL_PLANT_ID].iloc[0]}.png")
        plt.close()
