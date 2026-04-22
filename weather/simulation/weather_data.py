# The weather_data module aims to encapsulate all the information and logic needed to simulate
# future hourly load for intermittent generators (i.e. unified platform for wind and solar).

# It is a child of the BucketedData class that provides shared basic functionality
# between this and other input types that bucket historical data as a sampling mechanism.
# It has a slightly modified Bucketer child, the IntermittentBucketer, to sample random
# loadfactors in a way that preserves calendar patterns defined through the buckets.

# The sampling loop makes use of the inverse sampling algorithm for the columns that require
# such a transformation. It turns data from the original historical distribution into a new distribution
# that was optimized for the purpose of changing the natural average to a user-specified target.

# Each WeatherData instance uses a JSON-parsed HistoricalMetadata descriptor and helper and
# a shared class-level dict (_HIST_CACHE) keyed by the name of the respective historical data files
# so that distributed workloads can perform lazy-loading without conflicts.
# It supports two resampling modes via the `ignore_zeros` flag:
# - ignore_zeros = False (wind): all loadfactor values participate in histogram building and resampling.
# - ignore_zeros = True (solar): zero-valued hours (nighttime) are preserved as-is;
#       histograms and inverse-CDF resampling operate only on non-zero loadfactors.
# Desired averages are automatically adjusted from "all-hours" to "daytime-only" averages.

# Samples use the same historical periods for all streams to preserve geographical correlations.
# The sampling loop will return a custom view into a 2D NDArray of chronologically arranged
# hour-by-hour rows of loadfactors filling the date range needed for all streams,
# keeping track of the average-changed streams through the access_col method.

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Union

from numpy.typing import NDArray

if TYPE_CHECKING:
    import pandas as pd

import datetime
import random

import numpy as np

from ..core.bucketed_data import BucketedData
from .intermittent_bucketer import IntermittentBucketer

DateTimeLike = Union[datetime.datetime, "pd.Timestamp"]


@dataclass(frozen=True)
class HistoricalMetadata:
    """
    Lightweight descriptor and path resolver for the NPY-backed historical data.

    Attributes:
        npy_basename: Filename of the .npy artifact (also serves as _HIST_CACHE key).
        path_resolver: Callable mapping npy_basename to the on-executor filesystem path.
        data_limit_left: Earliest datetime in the NPY file.
        data_limit_right: Latest datetime in the NPY file.
        columns: Column names/identifiers in the NPY file.
        hours_per_block: Block size used when building prefix histograms (None if unavailable).
    """

    npy_basename: str
    path_resolver: Callable[[str], str]
    data_limit_left: DateTimeLike
    data_limit_right: DateTimeLike
    columns: Sequence[str]
    hours_per_block: int | None = None

    @staticmethod
    def _parse_horizon(horizon_utc: dict[str, str]) -> tuple[datetime.datetime, datetime.datetime]:
        return (
            datetime.datetime.fromisoformat(horizon_utc["start"]),
            datetime.datetime.fromisoformat(horizon_utc["end"]),
        )

    @classmethod
    def from_manifest(
        cls, manifest: dict[str, Any], path_resolver: Callable[[str], str]
    ) -> HistoricalMetadata:
        start_utc, end_utc = cls._parse_horizon(manifest["horizon_utc"])

        return cls(
            npy_basename=manifest["basename"],
            path_resolver=path_resolver,
            data_limit_left=start_utc,
            data_limit_right=end_utc,
            columns=manifest["artifact"]["columns"],
            hours_per_block=manifest["artifact_histogram"]["rows_per_block"],
        )


class WeatherData(BucketedData):
    """
    Unified intermittent weather sampler for intermittent loadfactors.

    Produces hourly loadfactor time-series for a future horizon by randomly stitching
    historical periods and (optionally) inverse-CDF resampling to hit target averages.

    For solar (ignore_zeros=True), nighttime zeros are preserved and only positive
    loadfactor hours participate in histogram building & resampling. Desired averages
    are automatically re-scaled from all-hours to daytime-only averages.

    The class-level _HIST_CACHE dict is keyed by npy_basename so that separate
    intermittent loadfactor instances never collide during PySpark lazy-loading on executors.
    """

    # Process-scope cache keyed by npy_basename.
    # Kept as a class variable (not instance) to prevent inadvertent serialization
    # poisoning: calling random_sample() on the driver would otherwise prevent
    # serializing the Engine.
    _HIST_CACHE: dict[str, NDArray] = {}

    def __init__(
        self,
        metadata: HistoricalMetadata,
        historical_start_date: DateTimeLike = datetime.datetime(1980, 1, 1),
        historical_end_date: DateTimeLike = datetime.datetime(2026, 1, 1),
        desired_averages: dict[int, list[float]] | None = None,
        prefix_histograms: NDArray[np.uint32] | None = None,
        historical_data: NDArray[np.floating] | None = None,
        ignore_zeros: bool = False,
    ):
        """
        Args:
            metadata: JSON-backed descriptor (basename, path resolver, time limits, columns).
            historical_start_date: Earliest date to consider for bucketed sampling.
            historical_end_date: Latest date to consider for bucketed sampling.
            desired_averages: ``{column_index: [avg_1, avg_2, ...]}`` mapping each column
                that needs inverse-CDF resampling to its target average(s).
                Multiple averages per column produce multiple output columns.
            prefix_histograms: Pre-computed prefix histograms for fast histogram queries.
            historical_data: Raw historical data array (needed only when desired_averages
                is non-empty and prefix_histograms is None, or when ignore_zeros is True
                for the zero-count adjustment).
            ignore_zeros: If True, zero-valued loadfactors are excluded from histogram
                building and inverse-CDF resampling (solar mode). Desired averages are
                automatically adjusted from all-hours to daytime-only averages.
        """

        if desired_averages is None:
            desired_averages = {}

        if len(desired_averages) != 0 and (historical_data is None and prefix_histograms is None):
            raise ValueError(
                "You need to pass a reference to some form of historical data upon WeatherData construction. "
                "Either remove the desired averages or provide the historical data and/or prefix histograms "
                "so that the optimization can be performed."
            )

        self.npy_basename = metadata.npy_basename
        self.path_resolver = metadata.path_resolver
        self.data_limit_left = metadata.data_limit_left
        self.data_limit_right = metadata.data_limit_right
        self.ignore_zeros = ignore_zeros

        # Save non-duplicate columns that require an average transformation in the mask (starting with 0):
        self.mask = np.array(list(desired_averages.keys()))

        # Computes the margins of the time intervals for which we have data:
        (
            self.historical_start_datetime,
            self.historical_start_date,
            self.historical_end_datetime,
            self.historical_end_date,
        ) = BucketedData.compute_time_margins(
            historical_start_date, historical_end_date, self.data_limit_left, self.data_limit_right
        )

        self.intermittent_bucketer = IntermittentBucketer(
            historical_start_date=self.historical_start_date,
            historical_end_date=self.historical_end_date,
            draw_period=7,
        )

        if len(self.mask) != 0:
            # Get only the cropped-to-full-year data while keeping the most recent historical datapoints; only the start date can change:
            statistical_start_date = self.crop_time_margins_to_full_years()
            first_statistical_index, _ = self.get_absolute_index_of_date(
                statistical_start_date
            )  # Inclusive
            _, last_statistical_index = self.get_absolute_index_of_date(
                self.historical_end_date
            )  # Non-inclusive

            # Compute the histogram matrix for the historical data for each masked col:
            if prefix_histograms is not None and metadata.hours_per_block is not None:
                prev_hist = self.get_fast_histogram(
                    first_statistical_index,
                    last_statistical_index,
                    historical_data,
                    metadata.hours_per_block,
                    prefix_histograms,
                    ignore_zeros=ignore_zeros,
                )
            else:
                prev_hist = self.get_histogram(
                    first_statistical_index,
                    last_statistical_index,
                    historical_data,
                    number_of_bins=500,
                    ignore_zeros=ignore_zeros,
                )

            # Store histogram once per unique masked column, not once per duplicate:
            self.old_pdf = prev_hist  # (n_unique_mask, n_bins)
            self.old_cdf = np.cumsum(prev_hist, axis=1)  # (n_unique_mask, n_bins)

            # When ignore_zeros is True, the histograms represent daytime-only distributions.
            # We must rescale the user-provided all-hours desired averages to daytime-only averages,
            # since the optimizer will target the average of the non-zero distribution.
            observations_per_col = self.old_cdf[:, -1].astype(np.int32, copy=False)
            # Inverse daytime ratio will be 1 for (ignore_zeros=False) and >1 for (ignore_zeros=True)
            # for each unique feature that needs average transformations:
            inverse_daytime_ratio = (
                last_statistical_index - first_statistical_index
            ) / observations_per_col

            # Build duplicate handling structures (same column may have multiple target averages):
            self.duplicate_histogram_positions = []
            self.duplicate_canonical_streams = []
            duplicate_averages = []
            i = 0
            for column, col_avgs in desired_averages.items():
                # Make sure optimizer gets rescaled averages when ignore_zeros is True:
                adjusted_averages = [avg * inverse_daytime_ratio[i] for avg in col_avgs]
                self.duplicate_histogram_positions.extend([i] * len(col_avgs))
                i += 1
                self.duplicate_canonical_streams.extend([column] * len(col_avgs))
                duplicate_averages.extend(adjusted_averages)

            # Optimization still needs potentially duplicated prev_hist rows
            # (temporary — does not persist):
            old_pdf_for_opt = prev_hist[self.duplicate_histogram_positions, :]

            # Optimization also needs observation counts per column for normalization:
            # if ignore_zeros is False, scalar of total number of hours;
            # else array of non-zero counts per duplicated feature:
            obs_for_opt = (
                observations_per_col[self.duplicate_histogram_positions]
                if self.ignore_zeros
                else last_statistical_index - first_statistical_index
            )

            new_pdf, _ = BucketedData.compute_optimized_distributions(
                previous_distribution_not_normalized=old_pdf_for_opt,
                desired_averages=duplicate_averages,
                observations_per_column=obs_for_opt,
            )
            self.new_cdf = np.cumsum(new_pdf, axis=1)

    @property
    def draw_period(self):
        return self.intermittent_bucketer.draw_period

    def get_or_mmap_historical(self) -> NDArray[np.floating]:
        """
        Lazy-load the NPY file into the process-level cache, keyed by basename.

        Using a dict keyed by npy_basename means each intermittent sampler gets
        their own cache slot, even though they share the same class.

        Returns:
            memmap_array: NDArray[np.floating] that is loaded from disk into mode "r" (read-only, memory-mapped)
        """
        cls = type(self)
        if self.npy_basename not in cls._HIST_CACHE:
            path_on_executor = self.path_resolver(self.npy_basename)
            # Protect against loading binary data from the NPY file:
            cls._HIST_CACHE[self.npy_basename] = np.load(
                path_on_executor, mmap_mode="r", allow_pickle=False
            )
        return cls._HIST_CACHE[self.npy_basename]

    def random_sample(
        self,
        future_start_date,
        future_end_date,
        python_rng=random.Random(40),
        numpy_rng=np.random.default_rng(22),
    ):
        """
        Generate a random sample of weather data for the specified future period.

        Args:
            future_start_date: Earliest datetime to include in the sample. Inclusive from 00:00 of that day.
            future_end_date: Latest date to include in the sample. Inclusive until 23:00 of that day.
            python_rng: Instance of Python's random.Random for reproducible sampling of historical periods.
            numpy_rng: Instance of NumPy's Generator for reproducible sampling in the inverse-CDF.

        Returns:
            sample: NDArray of shape (n_hours_in_horizon, n_output_columns) containing
                the generated sample of weather data for the future period.
        """

        historical = self.get_or_mmap_historical()

        future_end_date, hours_needed = self.adjust_forecasted_horizon(
            future_start_date, future_end_date
        )

        sample = []
        sampled_dates = self.intermittent_bucketer.random_sample(
            future_start_date, future_end_date, python_rng
        )

        for date in sampled_dates:
            first_index, _ = self.get_absolute_index_of_date(date)
            last_index = first_index + self.intermittent_bucketer.draw_period * 24

            sample.append(historical[first_index:last_index])

        sample = np.asarray(np.concatenate(sample), dtype=np.float32)

        sample = self.append_resampled_columns(sample[:hours_needed], numpy_rng)

        return sample
