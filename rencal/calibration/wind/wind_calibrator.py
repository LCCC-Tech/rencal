"""Extracts data from input files and calibreates wind power curves."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast

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

    def __init__(
        self,
        data_path: str = None,
        plant_id_col: str = None,
        output_path: str | Path = Path.cwd(),
        visual_output: bool = False,
        stream_npy_output: bool = False,
    ) -> None:
        """
        Constructor for the WindCalibrator class.

        Args:
            data_path (str): Path to the folder containing plant information, generation, and resource data.
            plant_id_col (str): Name of the plant identifier column.
            output_path (str | Path): Location to write the output files to.
            visual_output (bool): If True, each calibrated plant's power curve is plotted to the output folder.
            stream_npy_output (bool): If True, wind streams are written in NPY format alongside PARQUET.

        """
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
        self.plants.data = self.plants.data.loc[
            self.plants.data["technology"].isin(WIND_TECHNOLOGY_TYPES)
        ]
        self.calibration_plant_ids = self.generation.data[INTERNAL_PLANT_ID].unique()
        self.output_path = output_path if isinstance(output_path, Path) else Path(output_path)
        self.visual_output = visual_output
        self.stream_npy_output = stream_npy_output
        self.plant_wind_speeds: pd.DataFrame
        self.historical_load_factors: pd.DataFrame
        self.historical_load_factor_distributions: pd.DataFrame

    def calibrate(self) -> None:
        """Triggers calibration workflow."""
        logger.info("Starting calibration process...")
        self.plant_wind_speeds = self.extract_resource_timeseries_for_plants()
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.output_resource_per_plant()
        del self.resource
        self.generation.data = self._clip_generation_to_plant_capacity()
        self.historical_load_factors = self.calculate_historical_load_factors()
        self.historical_load_factor_distributions = self.fit_historical_load_factor_distribution()
        self.output_historical_load_factor_distribution_parameters()
        self.summary = self.estimate_load_factors_for_resource()
        del self.historical_load_factors
        del self.historical_load_factor_distributions
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
            self.resource.data = self.resource.data.sel(expver=1).combine_first(
                self.resource.data.sel(expver=5)
            )
        self.resource.data["wind_speed"] = np.sqrt(
            self.resource.data[ERA5_VARIABLE_MAPPING[DEFAULT_WIND_VARIABLES[0]]] ** 2
            + self.resource.data[ERA5_VARIABLE_MAPPING[DEFAULT_WIND_VARIABLES[1]]] ** 2
        )
        logger.info("Extracting resource data for plants...")
        unique_plant_locations = self.plants.data.drop_duplicates(INTERNAL_PLANT_ID)
        unique_plant_dim = xr.DataArray(
            unique_plant_locations[INTERNAL_PLANT_ID], dims=INTERNAL_PLANT_ID
        )
        plant_wind_speeds = self.resource.data.sel(
            longitude=xr.DataArray(unique_plant_locations["longitude"], dims=INTERNAL_PLANT_ID),
            latitude=xr.DataArray(unique_plant_locations["latitude"], dims=INTERNAL_PLANT_ID),
            method="nearest",
        )
        plant_wind_speeds[INTERNAL_PLANT_ID] = unique_plant_dim
        plant_wind_speed_res = plant_wind_speeds.to_dataframe().reset_index(drop=False)[
            ["time", INTERNAL_PLANT_ID, "wind_speed"]
        ]
        plant_wind_speed_res["time"] = pd.to_datetime(plant_wind_speed_res["time"], utc=True)
        plant_wind_speed_res = self._replace_extreme_wind_speeds(plant_wind_speed_res)
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
        gen_with_capacity = self.generation.data.merge(
            self.plants.data, how="left", on=INTERNAL_PLANT_ID
        ).drop_duplicates([INTERNAL_PLANT_ID, "time"])
        over_gen_mask = gen_with_capacity["quantity"] > gen_with_capacity["capacity"]
        gen_with_capacity.loc[over_gen_mask, "quantity"] = cast(
            pd.DataFrame, gen_with_capacity.loc[over_gen_mask, "capacity"]
        )
        return cast(pd.DataFrame, gen_with_capacity[self.generation.data.columns])

    @staticmethod
    def _remove_duplicate_plant_time_from_generation(generation_data: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregates generation quantities for potentialy rows where plant id and timestamp are equal.

        Args:
            generation_data (pd.DataFrame): Generation dataset.

        Returns:
            pd.DataFrame: Generation dataset with potentially duplicated plant-time combinations removed and their quantities summed.

        """
        return cast(
            pd.DataFrame,
            generation_data.groupby([INTERNAL_PLANT_ID, "time"], as_index=False, sort=False).agg(
                {"quantity": "sum"}
            ),
        )

    def calculate_historical_load_factors(self) -> pd.DataFrame:
        """Calculates historical load factors based on resource availability and generation data for each plant."""
        logger.info("Clculating historical load factors...")
        self.plant_wind_speeds[INTERNAL_PLANT_ID] = self.plant_wind_speeds[
            INTERNAL_PLANT_ID
        ].astype(str)
        self.generation.data[INTERNAL_PLANT_ID] = self.generation.data[INTERNAL_PLANT_ID].astype(
            str
        )
        self.generation.data = self._remove_duplicate_plant_time_from_generation(
            self.generation.data
        )
        coverage = self._get_plant_generation_temporal_bounds(self.generation.data)
        calibration_plant_wind_speeds = self.plant_wind_speeds[
            self.plant_wind_speeds[INTERNAL_PLANT_ID].isin(self.calibration_plant_ids)
        ]
        calibration_plant_wind_speeds = calibration_plant_wind_speeds.merge(
            coverage, on=INTERNAL_PLANT_ID, how="left"
        )
        mask = calibration_plant_wind_speeds["time"].between(
            calibration_plant_wind_speeds["hourly_start"],
            calibration_plant_wind_speeds["hourly_end"],
        )
        calibration_plant_wind_speeds = calibration_plant_wind_speeds.loc[
            mask, ["time", INTERNAL_PLANT_ID, "wind_speed"]
        ]
        wind_speed_generation_merged = calibration_plant_wind_speeds.merge(
            self.generation.data, on=["time", INTERNAL_PLANT_ID], how="left"
        ).merge(self.plants.data, on=INTERNAL_PLANT_ID, how="left")
        wind_speed_generation_merged["load_factor"] = (
            wind_speed_generation_merged["quantity"].fillna(0)
            / wind_speed_generation_merged["capacity"]
        )
        numeric_cols = wind_speed_generation_merged.select_dtypes(include=["number"]).columns
        wind_speed_generation_merged[numeric_cols] = wind_speed_generation_merged[
            numeric_cols
        ].round(2)
        wind_speed_generation_merged = self._drop_invalid_rows(wind_speed_generation_merged)
        return wind_speed_generation_merged

    @staticmethod
    def _fit_weibull_dist_to_plant(
        item: tuple[str, np.ndarray],
    ) -> tuple[str, float | None, float | None]:
        """
        Fits a Weibull distribution to an array of wind speeds.

        Args:
            item (tuple[str, np.ndarray]): Contains the ID and wind speeds connected to the plant to fit Weibull distribution to.

        Returns:
            tuple[str, float, float]: Tuple of plant ID, k and λ parameters of the fitted Weibull distribution.

        """
        cfd_id, speeds = item
        if len(speeds) < 3:  # skip if not enough points
            return cfd_id, np.nan, np.nan
        k, _, lamb = weibull_min.fit(speeds, floc=0)
        return cfd_id, k, lamb

    def fit_historical_load_factor_distribution(self) -> pd.DataFrame:
        """Fits probability distribution to historical load factors and resource availability."""
        logger.info("Fitting probability distribution to historical load factors...")
        wind_speeds = self.historical_load_factors.groupby(INTERNAL_PLANT_ID, sort=False)[
            "wind_speed"
        ]
        wind_speed_stats = wind_speeds.agg(wind_speed_mean="mean", wind_speed_stdev="std")
        wind_speeds = [
            (plant_id, wind_speed.dropna().to_numpy()) for plant_id, wind_speed in wind_speeds
        ]
        with ThreadPoolExecutor(max_workers=8) as ex:
            fits = list(ex.map(self._fit_weibull_dist_to_plant, wind_speeds))
        fitted_distributions = pd.DataFrame(fits, columns=[INTERNAL_PLANT_ID, "k", "lambda"])
        weibull_params = wind_speed_stats.reset_index().merge(
            fitted_distributions, on=INTERNAL_PLANT_ID, sort=False
        )
        return weibull_params

    def estimate_load_factors_for_resource(self) -> pd.DataFrame:
        """Estimates load factors based on the historical distribution and the whole resource availability history."""
        logger.info("Estimating long-term load factors for plants...")
        summary = pd.DataFrame(
            columns=[INTERNAL_PLANT_ID, "a", "b", "c", "d", "g", "estimated_load_factor"]
        )
        for plant_id in self.calibration_plant_ids:
            single_plant_load_factors = self.historical_load_factors.loc[
                self.historical_load_factors[INTERNAL_PLANT_ID] == plant_id
            ]
            single_plant_load_factor_dist_params = self.historical_load_factor_distributions.loc[
                self.historical_load_factor_distributions[INTERNAL_PLANT_ID] == plant_id
            ]
            if single_plant_load_factors.empty or single_plant_load_factor_dist_params.empty:
                logger.warning("Skipping %s (no valid data or Weibull params).", plant_id)
                continue
            lambda_val = single_plant_load_factor_dist_params["lambda"].iloc[0]
            k_val = single_plant_load_factor_dist_params["k"].iloc[0]

            try:
                logistic_params, _ = curve_fit(
                    self.logistic_function,
                    single_plant_load_factors["wind_speed"].to_numpy(),
                    single_plant_load_factors["load_factor"].to_numpy(),
                    p0=[
                        DEFAULT_LOGISTIC_FN_STEEPNESS,
                        DEFAULT_LOGISTIC_FN_XLOC,
                        DEFAULT_LOGISTIC_FN_ASYMMETRY,
                    ],
                    bounds=[
                        [
                            LOGISTIC_FN_STEEPNESS_LBOUND,
                            LOGISTIC_FN_XLOC_LBOUND,
                            LOGISTIC_FN_ASYMMETRY_LBOUND,
                        ],
                        [
                            LOGISTIC_FN_STEEPNESS_HBOUND,
                            LOGISTIC_FN_XLOC_HBOUND,
                            LOGISTIC_FN_ASYMMETRY_HBOUND,
                        ],
                    ],
                    maxfev=LOGISTIC_FN_MAXEVAL,
                )
            except Exception as e:
                logger.warning("Skipping %s (curve fit failed: %s)", plant_id, e)
                continue

            try:
                # Integrates the product of the logistic function for x (estimated load factor) and the weibull fuction of x (relative likelihood of x's occurrence)
                estimated_load_factor = quad(
                    lambda x, logistic_params, k_val, lambda_val: self.logistic_function(
                        x, *logistic_params
                    )
                    * self.weibull_function(x, k_val, lambda_val),
                    0,
                    np.inf,
                    (logistic_params, k_val, lambda_val),
                )[0]
            except Exception as e:
                logger.warning("Integration failed for %s: %s", plant_id, e)
                continue

            if self.visual_output:
                self.output_estimated_load_factors_visual(
                    logistic_params, single_plant_load_factors
                )

            summary.loc[len(summary)] = [
                plant_id,
                0,
                logistic_params[0],
                logistic_params[1],
                1,
                logistic_params[2],
                estimated_load_factor,
            ]
            summary_num_cols = summary.select_dtypes(include="number").columns
            summary[summary_num_cols] = summary[summary_num_cols].astype(np.float32)
            summary["estimated_load_factor"] = summary["estimated_load_factor"].round(4)
            if len(summary) < 1:
                raise ValueError("No calibration summary rows were produced.")
        return summary

    @staticmethod
    def logistic_function(
        x: int | float | np.ndarray, b: float, c: float, g: float
    ) -> float | np.ndarray:
        """
        Defines a generalised logistic function in the log domain for stability and calculates its
        value for any numeric input `x`.

        The generalised logistic function has 5 parameters defining its shape;
        however, this implementation forces the minimum and maximum values
        the function can take to 0 and 1, respectively, as load factors can vary between those two.

        The non-log-domain logistic function looks like this:

        f(x) = d + (a - d) / ((1 + (x / c) ** b) ** g)

        where `a` is the minimum bound, `b` is the steepness, `c` is the inflection point location,
        `d` is the maximum bound, and `g` is the asymmetry.

        Args:
            x (int | float | np.ndarray): Input variable(s), i. e.: wind speed.
            b (float): Steepness parameter of the generalised logistic function.
            c (float): X-axis inflection point location parameter of the generalised logistic function.
            g (float): Asymmetry parameter of the generalised logistic function.

        Returns:
            float | np.ndarray: The outputs of the generalised logistic function for each x value with the specified shape parameters.

        """
        x_arr = np.asarray(x)
        x_mask = x_arr != 0
        output = np.zeros_like(x_arr)
        output[x_mask] = 1.0 - np.exp(
            -g * np.logaddexp(0.0, b * (np.log(x_arr[x_mask]) - np.log(c)))
        )
        return output.item() if output.ndim == 0 else output

    @staticmethod
    def weibull_function(
        x: int | float | np.ndarray, k_val: float, lambda_val: float
    ) -> float | np.ndarray:
        """
        Calculates the value of a specified Weibull distribution for any numeric input `x`.

        The equation of the Weibull distribution is as follows:

        f(x) = k / λ * ((x / λ) ** (k - 1)) * (e ** -(x / λ) ** k)

        where `k` is the shape parameter, `λ` is the scale parameter, and `e` is Euler's number.

        Args:
            x (int | float | np.ndarray): Input variable(s), i. e.: wind speed.
            k_val (float): Shape parameter of the Weibull distribution.
            lambda_val (float): Scale parameter of the Weibull distribution.

        Returns:
            float | np.ndarray: Value of Weibull function at the specified x value(s).

        """
        return (
            k_val
            / lambda_val
            * (x / lambda_val) ** (k_val - 1)
            * np.exp(-((x / lambda_val) ** k_val))
        )

    @staticmethod
    def _drop_invalid_rows(cfd_data: pd.DataFrame) -> pd.DataFrame:
        """
        Drops rows with no valid data, eliminating positive and negative infinity values.

        Args:
            cfd_data (pd.DataFrame): DataFrame containing potentially invalid rows.

        Returns:
            pd.DataFrame: DataFrame without invalid rows.

        """
        return cfd_data.replace([np.inf, -np.inf], np.nan).dropna(
            subset=["wind_speed", "load_factor"]
        )

    @staticmethod
    def _replace_extreme_wind_speeds(cfd_wind_data: pd.DataFrame) -> pd.DataFrame:
        """
        Replaces wind speeds above and below sensible thresholds with threshold values.

        Args:
            cfd_wind_data (pd.DataFrame): DataFrame containing wind speed data.

        Returns:
            pd.DataFrame: DataFrame with too low or high wind speeds replaced.

        """
        cfd_wind_data["wind_speed"] = cfd_wind_data["wind_speed"].clip(
            lower=WIND_SPEED_LBOUND, upper=WIND_SPEED_HBOUND
        )
        return cfd_wind_data

    def _create_generic_power_curve(self) -> None:
        """Generates generic power curve parameters from the median of available fitted data."""
        summary_with_tech = self.summary.merge(
            self.plants.data[[INTERNAL_PLANT_ID, "technology"]], how="left", on=INTERNAL_PLANT_ID
        )
        unique_summary_tech = summary_with_tech["technology"].unique()
        if all(wind_tech in unique_summary_tech for wind_tech in WIND_TECHNOLOGY_TYPES):
            tech_medians = (
                summary_with_tech.groupby("technology")
                .agg({"a": "first", "b": "median", "c": "median", "d": "first", "g": "median"})
                .reset_index()
                .rename(columns={"technology": INTERNAL_PLANT_ID})
            )
            tech_medians["estimated_load_factor"] = 0
            tech_medians[INTERNAL_PLANT_ID] = "Generic " + tech_medians[INTERNAL_PLANT_ID]
            self.summary = pd.concat([self.summary, tech_medians])
        else:
            self.summary.loc[len(self.summary)] = [
                "Generic",
                0,
                self.summary["b"].median(),
                self.summary["c"].median(),
                1,
                self.summary["g"].median(),
                0,
            ]

    def generate_resource_streams(self) -> pd.DataFrame:
        """Generates wind streams from fitted and/or generalised power curve parameters and long-term wind data."""
        logger.info("Generating wind streams for plants...")
        summary_used_cols = [PLANT_ID_OUTPUT, "b", "c", "g"]
        plant_wind_speed_and_params = self.plant_wind_speeds.merge(
            self.summary[summary_used_cols],
            left_on=INTERNAL_PLANT_ID,
            right_on=PLANT_ID_OUTPUT,
            how="left",
            indicator=True,
        ).drop(columns=PLANT_ID_OUTPUT)
        if "Generic" in self.summary[PLANT_ID_OUTPUT]:
            plant_wind_speed_and_params.loc[
                plant_wind_speed_and_params["_merge"] == "left_only", summary_used_cols[1:]
            ] = self.summary.loc[self.summary.index[-1], summary_used_cols[1:]].values
        else:
            left_only_mask = plant_wind_speed_and_params["_merge"] == "left_only"
            plant_wind_speed_and_params[left_only_mask] = (
                plant_wind_speed_and_params[left_only_mask]
                .assign(__idx=lambda x: x.index)
                .drop(columns=summary_used_cols[1:])
                .merge(
                    cast(
                        pd.DataFrame, self.plants.data[[INTERNAL_PLANT_ID, "technology"]]
                    ).drop_duplicates(INTERNAL_PLANT_ID),
                    on=INTERNAL_PLANT_ID,
                    how="left",
                )
                .assign(technology=lambda df: "Generic " + df["technology"])
                .merge(
                    self.summary[summary_used_cols],
                    left_on="technology",
                    right_on=PLANT_ID_OUTPUT,
                    how="left",
                )
                .drop(columns=[PLANT_ID_OUTPUT, "technology"])
                .set_index("__idx")[plant_wind_speed_and_params.columns]
            )
        plant_wind_speed_and_params.drop(columns="_merge")
        plant_wind_speed_and_params["load_factor"] = self.logistic_function(
            plant_wind_speed_and_params["wind_speed"],
            plant_wind_speed_and_params["b"],
            plant_wind_speed_and_params["c"],
            plant_wind_speed_and_params["g"],
        )
        plant_wind_speed_and_params = (
            plant_wind_speed_and_params[["time", INTERNAL_PLANT_ID, "load_factor"]]
            .pivot(index="time", columns=INTERNAL_PLANT_ID, values="load_factor")
            .sort_index()
            .reset_index()
            .rename(columns={"time": "Times"})
        )
        return plant_wind_speed_and_params

    def _rename_output_summary_columns(self) -> None:
        """Renames output table columns to expected and/or more human-readable values."""
        self.summary = self.summary.rename(
            columns={
                INTERNAL_PLANT_ID: PLANT_ID_OUTPUT,
                "estimated_load_factor": "Estimated Load Factor",
            }
        )

    def output_historical_load_factor_distribution_parameters(self) -> None:
        """Writes historical load factor parameters to a CSV file."""
        weibull_path = self.output_path / "Weibull Params.csv"
        self.historical_load_factor_distributions.to_csv(weibull_path, index=False)
        logger.info("Written historical load factor parameters to %s", weibull_path)

    def output_resource_per_plant(self) -> None:
        """Writes resource time series for each plant to a CSV file."""
        resource_output_path = self.output_path / "Wind Speeds.csv"
        self.plant_wind_speeds.to_csv(resource_output_path, index=False)
        logger.info("Written plant-wise resource dataset to %s", resource_output_path)

    def output_resource_streams(self) -> None:
        """Writes resource streams to a parquet file."""
        stream_path = self.output_path / "Wind Streams.parquet"
        self.wind_streams.to_parquet(stream_path, index=False)
        logger.info("Written wind streams to %s", stream_path)
        if self.stream_npy_output:
            with open(stream_path.with_suffix(".npy"), "wb") as stream_npy:
                np.save(
                    stream_npy, self.wind_streams.drop(columns="Times").to_numpy(dtype=np.float32)
                )
            logger.info("Written wind streams to %s", stream_path.with_suffix(".npy"))

    def output_estimated_load_factors_tabular(self) -> None:
        """Outputs table of estimated load factors for whole resource availability history."""
        summary_path = self.output_path / "Calibration Summary.csv"
        self.summary.to_csv(summary_path, index=False)
        logger.info("Written estimated load factor summary to %s", summary_path)

    def output_estimated_load_factors_visual(
        self, logistic_params: np.ndarray, load_factors: pd.DataFrame
    ) -> None:
        """Outputs a series of plots of estimated load and fitted curves per plant."""
        x_vals = np.linspace(0, 25, 300)
        y_vals = self.logistic_function(
            x_vals, b=logistic_params[0], c=logistic_params[1], g=logistic_params[2]
        )
        mean_wind_speed = load_factors["wind_speed"].mean()
        plt.figure(figsize=(10, 6))
        plt.scatter(
            load_factors["wind_speed"],
            load_factors["load_factor"],
            s=10,
            color="blue",
            alpha=0.6,
            label="Observed Data",
        )
        plt.plot(x_vals, y_vals, color="orange", lw=3, label="Fitted Curve")
        plt.axvline(
            mean_wind_speed,
            color="green",
            linestyle="--",
            lw=2,
            label=f"Mean Wind Speed = {mean_wind_speed:.2f} m/s",
        )
        logger.info(load_factors[INTERNAL_PLANT_ID].iloc[0])
        plt.title(f"Power Curve Fit - {load_factors[INTERNAL_PLANT_ID].iloc[0]}")
        plt.xlabel("Wind Speed (m/s)")
        plt.ylabel("Load Factor")
        plt.legend()
        plt.grid(True)
        plt.savefig(
            self.output_path / f"PowerCurveFit_{load_factors[INTERNAL_PLANT_ID].iloc[0]}.png"
        )
        plt.close()
