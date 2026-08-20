"""Extracts data from input files and calibreates solar power curves."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import xarray as xr
from matplotlib import pyplot as plt
from scipy.integrate import quad
from scipy.optimize import curve_fit

from ...utils.constants import (
    DEFAULT_SOLAR_CURVE_NOCT,
    SOLAR_IRRADIANCE_LBOUND,
    SOLAR_IRRADIANCE_HBOUND,
    DEFAULT_SOLAR_CURVE_GAMMA,
    SOLAR_CURVE_GAMMA_LBOUND,
    SOLAR_CURVE_GAMMA_HBOUND,
    SOLAR_CURVE_NOCT_LBOUND,
    SOLAR_CURVE_NOCT_HBOUND,
    ERA5_VARIABLE_MAPPING,
    INTERNAL_PLANT_ID,
    PLANT_ID_COLUMN,
    PLANT_ID_OUTPUT,
    SOLAR_TECHNOLOGY_TYPES,
)

from ...utils.logger import get_logger
from ..calibrator import Calibrator

logger = get_logger(__name__)

class SolarCalibrator(Calibrator):
    """Calibrates solar power curves for a set of timestamps and CFD IDs."""

    def __init__(
            self,
            data_path: str = None,
            plant_id_col: str = None,
            output_path: str | Path = Path.cwd(),
            visual_output: bool = False,
            stream_npy_output: bool = False,
    ) -> None:
        """
        Constructor for the SolarCalibrator class.

        Args:
            data_path (str): Path to the folder containing plant information, generation, and resource data.
            plant_id_col (str): Name of the plant identifier column.
            output_path (str | Path): Location to write the output files to.
            visual_output (bool): If True, each calibrated plant's power curve is plotted to the output folder.
            stream_npy_output (bool): If True, solar streams are written in NPY format alongside PARQUET.

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
            self.plants.data["technology"].isin(SOLAR_TECHNOLOGY_TYPES)
        ]
        self.calibration_plant_ids = self.generation.data[INTERNAL_PLANT_ID].unique()
        self.output_path = output_path if isinstance(output_path, Path) else Path(output_path)
        self.visual_output = visual_output
        self.stream_npy_output = stream_npy_output
        self.plant_irradiance: pd.DataFrame
        self.historical_load_factors: pd.DataFrame
        self.historical_load_factor_distributions: pd.DataFrame

    def solar_regression_model(x_data, gamma, noct):
        T = x_data[:, 0]          # temperature
        G = x_data[:, 1]          # irradiance
        T_cell = T + (noct - 20) * G / 800
        return (1 - gamma * (T_cell - 25)) * G / 1000
    

    def calibrate(self) -> None:
        """Triggers calibration workflow."""
        logger.info("Starting calibration process...")
        self.plant_irradiance = self.extract_resource_timeseries_for_plants()
        self.output_path.mkdir(parents=True, exists_ok=True)
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
        self.solar_streams = self.generate_resource_streams()
        self.output_resource_streams()
        logger.info("Calibration finished!")

    def extract_resource_timeseries_for_plants(self):
        """Extracts resource data for plants into a dataframe."""
        if "expver" in self.resource.data.coords:
            logger.info("Combining final and initial release data for resource...")
            self.resource.data = self.resource.data.set(expver=1).combine_first(
                self.resource.data.sel(expver=5)
            )
        
        # Convert SSRD from J/m to W/m
        ssrd_var = ERA5_VARIABLE_MAPPING["surface_solar_radiation_downwards"]
        self.resource.data["irradiance"] = (
            self.resource.data[ssrd_var] / 3600
        )

        if "2m_temperature" in ERA5_VARIABLE_MAPPING:
            t2m_var = ERA5_VARIABLE_MAPPING["2m_temperature"]
            self.resource.data["temperature"] = self.resource.data[t2m_var]
        logger.info("Extracting solar irradiance for plants...")
        unique_plant_locations = self.plants.data.drop_duplicates(INTERNAL_PLANT_ID)
        unique_plant_dim = xr.DataArray(
            unique_plant_locations[INTERNAL_PLANT_ID], DIMS=INTERNAL_PLANT_ID
        )

        plant_irradiance = self.resource.data.sel(
            longitude=xr.DataArray(unique_plant_locations["longitude"], dims=INTERNAL_PLANT_ID),
            latitude=xr.DataArray(unique_plant_locations["latitude"], dims=INTERNAL_PLANT_ID),
            method="nearest",
        )
        plant_irradiance[INTERNAL_PLANT_ID] = unique_plant_dim

        plant_irradiance_res = plant_irradiance.to_dataframe().reset_index(drop=False)

        keep_cols = ["time", INTERNAL_PLANT_ID, "irradiance"]
        if "temperature" in plant_irradiance:
            keep_cols.append("temperature")

        plant_irradiance_res = plant_irradiance_res[keep_cols]
        plant_irradiance_res["time"] = pd.to_datetime(plant_irradiance_res["time"], utc=True)

        plant_irradiance_res["irradiance"] = plant_irradiance_res["irradiance"].clip(
            lower=SOLAR_IRRADIANCE_LBOUND,
            upper=SOLAR_IRRADIANCE_HBOUND,
        )

        return plant_irradiance_res

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
        """Calculates historical load factors based on irradiance and generation data for each plant."""
        logger.info("Calculating historical load factors...")

        self.plant_irradiance[INTERNAL_PLANT_ID] = self.plant_irradiance[
        INTERNAL_PLANT_ID
        ].astype(str)
        self.generation.data[INTERNAL_PLANT_ID] = self.generation.data[INTERNAL_PLANT_ID].astype(
            str
        )
        self.generation.data = self._remove_duplicate_plant_time_from_generation(
            self.generation.data
        )
        coverage = self._get_plant_generation_temporal_bounds(self.generation.data)
        calibration_plant_irradiance = self.plant_irradiance[
            self.plant_irradiance[INTERNAL_PLANT_ID].isin(self.calibration_plant_ids)
        ]
        calibration_plant_irradiance = calibration_plant_irradiance.merge(
            coverage, on=INTERNAL_PLANT_ID, how="left"
        )
        mask = calibration_plant_irradiance["time"].between(
            calibration_plant_irradiance["hourly_start"],
            calibration_plant_irradiance["hourly_end"],
        )
        calibration_plant_irradiance = calibration_plant_irradiance.loc[
            mask, ["time", INTERNAL_PLANT_ID, "irradiance"]
        ]
        solar_irradiance_generation_merged = calibration_plant_irradiance.merge(
            self.generation.data, on=["time", INTERNAL_PLANT_ID], how="left"
        ).merge(self.plants.data, on=INTERNAL_PLANT_ID, how="left")
        solar_irradiance_generation_merged["load_factor"] = (
            solar_irradiance_generation_merged["quantity"].fillna(0)
            / solar_irradiance_generation_merged["capacity"]
        )    
        numeric_cols = solar_irradiance_generation_merged.select_dtypes(include=["number"]).columns
        solar_irradiance_generation_merged[numeric_cols] = solar_irradiance_generation_merged[
            numeric_cols
        ].round(2)

        solar_irradiance_generation_merged = self._drop_invalid_rows(solar_irradiance_generation_merged)

        return solar_irradiance_generation_merged
        
    @staticmethod
    def _fit_irradiance_histogram_to_plant(
        item: tuple[str, np.ndarray],
        bins: int,
    ) -> tuple[str, float | None, float | None]:
        """Fits an empirical histogram distribution to a plant's irradiance values.
        Args:
            item (tuple[str, np.ndarray]): (plant_id, irradiance_array)
            bins (int): Number of histogram bins.

        Returns:
            tuple[str, np.ndarray, np.ndarray]:
            plant_id, histogram probabilities, bin edges"""
        
        plant_id, irradiance = item

        if len(irradiance) < 3:
            return plant_id, np.array([]), np.array([])
        
        hist, bin_edges = np.histogram(
            irradiance,
            bins=bins,
            range=(SOLAR_IRRADIANCE_LBOUND, SOLAR_IRRADIANCE_HBOUND),
            density=True,
        )

        return plant_id, hist, bin_edges
    
    def fit_historical_load_factor_distribution(self) -> pd.DataFrame:
        """Fits an empirical irradiance histogram for each plant."""

        logger.info("Fitting irradiance histograms for historical load factors...")

        irradiance_groups = self.historical_load_factors.groupby(
            INTERNAL_PLANT_ID, sort=False
        )["irradiance"]

        irradiance_statistics = irradiance_groups.agg(
            irradiance_mean="mean",
            irradiance_stdev="std"
        )
        irradiance_arrays = [
            (plant_id, irr.dropna().to_numpy())
            for plant_id, irr in irradiance_groups
        ]
        with ThreadPoolExecutor(max_workers=8) as ex:
            fits = list(
                ex.map(
                    lambda item: self._fit_irradiance_histogram_to_plant(item),
                    irradiance_arrays
                )
            )
        hist_df = pd.DataFrame(
            fits,
            columns=[INTERNAL_PLANT_ID, "hisogram", "bin_edges"]
        )
        result = irradiance_statistics.reset_index().merge(
            hist_df, on=INTERNAL_PLANT_ID, sort=False
        )

        return result
    
    def estimate_load_factors_for_resource(self) -> pd.DataFrame:
        """Estimates long term load factors for plants using the NOCT-based solar model."""

        logger.info("Estimating long term solar load factors for plants...")

        summary = pd.DataFrame(
            columns=[INTERNAL_PLANT_ID, "gamma", "NOCT", "estimated_load_factor"]
        )

        for plant_id in self.calibration_plant_ids:

            lf_data = self.historical_load_factors.loc[
                self.historical_load_factors[INTERNAL_PLANT_ID] == plant_id
            ]

            if lf_data.empty:
                logger.warning("Skipping %s (no valid irradiance data).", plant_id)
                continue

            x_data = np.vstack([
                lf_data["temperature"].values,
                lf_data["irradiance"].values
            ])

            try:
                (gamma, noct), _ = curve_fit(
                    self.solar_regression_model,
                    x_data,
                    lf_data["load_factor"].values,
                    p0=[DEFAULT_SOLAR_CURVE_GAMMA, DEFAULT_SOLAR_CURVE_NOCT],
                    bounds=(
                        [SOLAR_CURVE_GAMMA_LBOUND, SOLAR_CURVE_NOCT_LBOUND],
                        [SOLAR_CURVE_GAMMA_HBOUND, SOLAR_CURVE_NOCT_HBOUND],
                    ),
                    maxfev=2000
                )
            except Exception as e:
                logger.warning("Skipping %s (solar curve fit failed: %s)", plant_id, e)
                continue

            estimated_lf = float(np.mean(
                self.solar_regression_model(x_data, gamma, noct)
            ))

            self.output_estimated_load_factors_visual(
                pv_params=np.array([gamma, noct]),
                load_factors=lf_data
            )

            summary.loc[len(summary)] = [
                plant_id,
                gamma,
                noct,
                round(estimated_lf, 4),
            ]

        return summary

    
    def _create_generic_solar_curve(self) -> None:
        """Generates a generic solar curve using median fitted parameters."""

        median_gamma = self.summary["gamma"].median()
        median_noct = self.summary["NOCT"].median()

        self.summary.loc[len(self.summary)] = [
            "Generic Solar",
            median_gamma,
            median_noct,
        ]

    def generate_solar_resource_streams(self) -> pd.DataFrame: 
        logger.info("Generating solar streams for plants...")

        plant_solar_irradiance_and_params = self.plant_irradiance.merge(
            self.summary[[PLANT_ID_OUTPUT, "gamma", "NOCT"]],
            left_on=INTERNAL_PLANT_ID,
            right_on=PLANT_ID_OUTPUT,
            how="left"
        ).drop(columns=PLANT_ID_OUTPUT)

        missing_mask = (
            plant_solar_irradiance_and_params["gamma"].isna() |
            plant_solar_irradiance_and_params["NOCT"].isna()
        )
        if missing_mask.any():
            generic = self.summary[self.summary[PLANT_ID_OUTPUT] == "Generic Solar"].iloc[0]
            plant_solar_irradiance_and_params.loc[missing_mask, "gamma"] = generic["gamma"]
            plant_solar_irradiance_and_params.loc[missing_mask, "NOCT"] = generic["NOCT"]

        T = plant_solar_irradiance_and_params["temperature"]
        G = plant_solar_irradiance_and_params["irradiance"]
        gamma = plant_solar_irradiance_and_params["gamma"]
        noct = plant_solar_irradiance_and_params["NOCT"]

        T_cell = T + (noct - 20) * G / 800

        plant_solar_irradiance_and_params["load_factor"] = (
            (1 - gamma * (T_cell - 25)) * G / 1000
        )
        plant_solar_irradiance_and_params = (
            plant_solar_irradiance_and_params[["time", INTERNAL_PLANT_ID, "load_factor"]]
            .pivot(index="time", columns=INTERNAL_PLANT_ID, values="load_factor")
            .sort_index()
            .reset_index()
            .rename(columns={"time": "Times"})
        )

        return plant_solar_irradiance_and_params

    
    def _rename_output_summary_columns(self) -> None:
        """Renames solar calibration summary columns to readable output names."""
        self.summary = self.summary.rename(
            columns={
                INTERNAL_PLANT_ID: PLANT_ID_OUTPUT,
                "estimated_load_factor": "Estimated Load Factor",
                "gamma": "Gamma",
                "NOCT": "NOCT",
            }
        )

    def output_historical_load_factor_distribution_parameters(self) -> None:
        """Writes irradiance distribution parameters to a CSV file."""
        output_path = self.output_path / "Solar Distribution Params.csv"
        self.historical_load_factor_distributions.to_csv(output_path, index=False)
        logger.info("Written solar irradiance distribution parameters to %s", output_path)


    def output_resource_per_plant(self) -> None:
        """Writes solar irradiance and temperature time series for each plant to a CSV file."""
        output_path = self.output_path / "Solar Resource.csv"
        self.plant_irradiance.to_csv(output_path, index=False)
        logger.info("Written plant‑wise solar resource dataset to %s", output_path)

    def output_resource_streams(self) -> None:
        """Writes solar load‑factor streams to a parquet file."""
        stream_path = self.output_path / "Solar Streams.parquet"
        self.solar_streams.to_parquet(stream_path, index=False)
        logger.info("Written solar streams to %s", stream_path)

        if self.stream_npy_output:
            with open(stream_path.with_suffix(".npy"), "wb") as stream_npy:
                np.save(
                    stream_npy,
                    self.solar_streams.drop(columns="Times").to_numpy(dtype=np.float32)
                )
            logger.info("Written solar streams to %s", stream_path.with_suffix(".npy"))

    def output_estimated_load_factors_tabular(self) -> None:
        """Outputs table of estimated solar load factors for the full history."""
        summary_path = self.output_path / "Solar Calibration Summary.csv"
        self.summary.to_csv(summary_path, index=False)
        logger.info("Written solar load factor summary to %s", summary_path)

    def output_estimated_load_factors_visual(
        self, pv_params: np.ndarray, load_factors: pd.DataFrame
    ) -> None:
        """Outputs a plot of observed solar load factors and the fitted NOCT PV curve."""

        gamma, noct = pv_params

        x_vals = np.linspace(0, 1200, 300)
        T_mean = load_factors["temperature"].mean()
        T_cell = T_mean + (noct - 20) * x_vals / 800
        y_vals = (1 - gamma * (T_cell - 25)) * x_vals / 1000

        plt.figure(figsize=(10, 6))
        plt.scatter(
            load_factors["irradiance"],
            load_factors["load_factor"],
            s=10,
            color="blue",
            alpha=0.6,
            label="Observed Data",
        )
        plt.plot(
            x_vals,
            y_vals,
            color="orange",
            lw=3,
            label="Fitted NOCT PV Curve",
        )
        mean_irr = load_factors["irradiance"].mean()
        plt.axvline(
            mean_irr,
            color="green",
            linestyle="--",
            lw=2,
            label=f"Mean Irradiance = {mean_irr:.1f} W/m²",
        )
        plant_id = load_factors[INTERNAL_PLANT_ID].iloc[0]
        plt.title(f"PV Curve Fit – {plant_id}")
        plt.xlabel("Irradiance (W/m²)")
        plt.ylabel("Load Factor")
        plt.legend()
        plt.grid(True)

        out_path = self.output_path / f"PV_Curve_Fit_{plant_id}.png"
        plt.savefig(out_path)
        plt.close()
        logger.info("Written PV curve fit plot to %s", out_path)
