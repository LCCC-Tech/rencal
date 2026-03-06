# The purpose of the BucketedData class is to serve as a container
# for all shared functionality between input modules that use the Bucketer
# as the main generation machanism.

# It is the parent class of the WeatherData, and DemandData classes.

# It has no state of its own, it relies on the fields of other classes to be named accordingly:
# (historical_start/end_date, mask, new_cdf, duplicate_histogram_positions/canonical_streams, historical_data).
# It is ready for the deployment of multiple types of streams in that regard,
# since it can repurpose those optimisation functions abstracted away from WeatherData.

# There is no main output, as the class functions more like a template of shared logic.

import datetime
import numpy as np
import pandas as pd
from typing import Sequence, Union
from numpy.typing import NDArray
import warnings


class VersionedColumnsNDArray:
    """
    This class serves as a wrapper around the final output data array of shape
    (n_hours, n_raw_features + n_transformed_features).
    
    We build it incrementally in the sampling loop for additional column versions,
    to keep track of the mapping between canonical columns and their
    transformed versions in the output array.

    If no additional versions are needed, it provides a passthrough of the access
    index to view canonical columns in the original sample, without any copy:
    version = 0 -> canonical column in the original sample;
    or
    no version specified -> use canonical column to index directly into full output;

    Otherwise:
    version >= 1 -> appended version generated in the sampling loop, in order of creation
    """
    def __init__(self, n_raw_features: int):
        self.n_raw_features = int(n_raw_features)
        self._canonical_to_absolute: dict[int, list[int]] = {}
        self._data: NDArray[np.floating] | None = None

    def update_mapping(self, canonical_col: int, j: int) -> int:
        """
        Record the creation of another version of the canonical_col,
        in the output matrix at loop index j through the list of all versions.

        j is 0-based loop index (from enumerate(self.duplicate_columns)) and
        we store that transformed column at absolute column index = n_raw_features + j.

        Args:
            canonical_col (int): The canonical column index in the original sample 
                that is being transformed this iteration.
            j (int): The 0-based current iteration index.
        
        Returns:
            abs_idx (int): The absolute column index in the output matrix where 
                the new version of the canonical column is stored.
        """
        abs_idx = self.n_raw_features + j
        self._canonical_to_absolute.setdefault(int(canonical_col), []).append(abs_idx)

        return abs_idx

    def attach_data(self, data: NDArray[np.floating]) -> "VersionedColumnsNDArray":
        """
        Attach the final output matrix exactly once, saving a reference to it internally.

        Args:
            data (NDArray[np.floating]): The final output matrix to attach,
            which should have shape (n_hours, n_raw_features + n_transformed_features).

        Returns:
            self (VersionedColumnsNDArray): The instance with the data attached, ready for column access.

        """
        # We ensure we don't ever attach data more than once:
        if self._data is not None:
            raise RuntimeError("Data already attached")
        # Sanity checks:
        if data.ndim != 2:
            raise ValueError("Data must be 2D: (hours, streams)")
        if data.shape[1] < self.n_raw_features:
            raise ValueError(f"Data has fewer columns than n_raw_features ({self.n_raw_features}): {data.shape[1]} columns provided")
        
        self._data = data
        return self

    def access_col(self, canonical_col: int, version: int = 0) -> NDArray[np.floating]:
        # Deal fast with unattached data or canonical version:
        if self._data is None:
            raise RuntimeError("Data not attached yet")
        if version == 0:
            # Only a view of the column requested, no copy:
            return self._data[:, int(canonical_col)]
        
        # Otherwise use the mapping to find the absolute column index of the requested version:
        absolute_col_indices = self._canonical_to_absolute.get(canonical_col) # no KeyError yet
        if not absolute_col_indices or version < 1 or version > len(absolute_col_indices):
            raise IndexError(f"No version {version} for canonical col {canonical_col}")
        # Version is 1-based for non-canonical columns, so we subtract 1 to get the correct index in the mapping for those:
        abs_idx = absolute_col_indices[version - 1]
        # Only a view of the canonical column, no copy:
        return self._data[:, abs_idx]
    
    def __getitem__(self, key) -> NDArray[np.floating]:
        # Deal fast with unattached data or canonical version:
        if self._data is None:
            raise RuntimeError("Data not attached yet")
        # Pass through direct indexing to the full output data:
        else:
            return self._data[key]


class BucketedData:
    """
    The purpose of this class is to serve as a container for all shared functionality between input modules that use the :class:`Bucketer` as the main path-generation mechanism.

    It is the parent class of the :class:`WeatherData`, and :class:`DemandData` classes.

    It has no state of its own, it relies on the fields of other classes to be named accordingly.

    There is no main output, as the class functions more like an abstract class template of shared logic.
    """
    def __init__(self):
        pass


    def crop_time_margins_to_full_years(self):
        """
        Used to crop the training data at the far (left) end, such that no calendar interval is overrepresented.
        It disregards the most distant dates to return a date from which, if historical data were to start, no calendar date would repeat itself more than any other.

        Returns:
            start_date (datetime.datetime): The date from which to start the historical data for no bias in the yearly distribution.
        """
        month = self.historical_end_date.month
        day = self.historical_end_date.day
        year = self.historical_start_date.year

        start_date = datetime.datetime(year, month, day)

        while start_date < self.historical_start_date:
            year += 1
            start_date = datetime.datetime(year, month, day)

        # We need at least a year's worth of data to create unbiased yearly distributions:
        if (self.historical_end_date - start_date) < datetime.timedelta(365.2425):
            raise ValueError("There is insufficient historical data to have a full picture of the yearly distribution.")

        return start_date
    
    def get_histogram(self,
        statistical_start_index: int,
        statistical_end_index: int,
        historical_data: NDArray[np.floating] | None,
        number_of_bins: int,
        ignore_zeros: bool = False,
    ) -> NDArray[np.uint32]:
        """
        Return uint32 histogram matrix shaped (len(self.mask), number_of_bins)
        for rows [statistical_start_index, statistical_end_index) and selected columns self.mask.

        Can only be used with MAX_UINT16 = 65536 bins or less.

        Args:
            statistical_start_index (int): The start index of the data to consider for the histogram (inclusive).
            statistical_end_index (int): The end index of the data to consider for the histogram (exclusive).
            number_of_bins (int): The number of bins to use for the histogram.
            historical_data (NDArray[np.floating]): The historical data array, loadfactors between 0 and 1.
            ignore_zeros (bool): If True, zero-valued observations are excluded from
                the histogram (useful for solar data where nighttime hours are 0).
                Defaults to False.

        Returns:
            histogram (NDArray[np.uint32]): The histogram matrix for the specified data and columns.

        """
        # Pre-allocate the memory for the histogram:
        histogram = np.zeros((len(self.mask), number_of_bins), dtype=np.uint32)

        if statistical_end_index <= statistical_start_index or historical_data is None:
            # Warning the user that there is no data to compute the histogram on:
            warnings.warn(f"No data to compute histogram between indices start: {statistical_start_index} " + 
                          f"and end: {statistical_end_index}. Returning empty histogram.")
            return histogram

        # Not a view! Actual hard copy:
        selected_data = historical_data[statistical_start_index:statistical_end_index, self.mask]

        # Floor function applied as a result of casting, should work as long as we have less than 65536 bins:
        matrix_bin_index = (selected_data * number_of_bins).astype(np.uint16)
        # Clip any occurance of 1 into previous bucket:
        matrix_bin_index[matrix_bin_index == number_of_bins] = number_of_bins - 1
        
        for column in range(len(self.mask)):
            if ignore_zeros:
                non_zero_mask = selected_data[:, column] > 0
                column_bin_index = matrix_bin_index[non_zero_mask, column]
            else:
                column_bin_index = matrix_bin_index[:, column]

            histogram[column] = np.bincount(column_bin_index, minlength=number_of_bins).astype(np.uint32)
        
        return histogram

    def get_fast_histogram(self, 
        first_statistical_index: int, 
        last_statistical_index: int, 
        historical_data: NDArray[np.floating], 
        hours_per_block: int, 
        prefix_histograms: NDArray[np.uint32],
        ignore_zeros: bool = False):
        """
        Function returns the histogram matrix shaped (len(self.mask), number_of_bins) of the historical data,
        for rows [statistical_start_index, statistical_end_index) and selected columns self.mask,
        using the pre-computed prefix histograms for the historical data to speed up the computation.

        Args:
            first_statistical_index (int): The start index of the historical data to consider for the PDF (inclusive).
            last_statistical_index (int): The end index of the historical data to consider for the PDF (exclusive).
            historical_data (NDArray[np.floating]): The historical data array.
            hours_per_block (int): The number of hours per block in the prefix histograms.
            prefix_histograms (NDArray[np.uint32]): The pre-computed prefix histograms for the historical data.

        Returns:
            histogram (NDArray[np.uint32]): The histogram matrix for the specified data and columns.
        """

        # 1-indexed blocks with the 0th block's prefix histogram filled with zeros:
        first_full_block = (first_statistical_index + hours_per_block - 1) // hours_per_block + 1
        last_full_block = last_statistical_index // hours_per_block

        # Compute the full-block part of the histogram:
        if last_full_block >= first_full_block:
            # first_full_block - 1 always a valid index because of 1-indexation:
            historical_distributions = \
                prefix_histograms[last_full_block, self.mask, :] - prefix_histograms[first_full_block - 1, self.mask, :]
        else:
            # Zero histograms from the first slice:
            historical_distributions = prefix_histograms[0, self.mask, :]

        number_of_bins = prefix_histograms.shape[2]

        # Partial start: [first_statistical_index, start_of_first_full_block):
        start_of_first_full = (first_full_block - 1) * hours_per_block
        partial_start = self.get_histogram(      
            first_statistical_index,
            min(last_statistical_index, start_of_first_full),
            historical_data,
            number_of_bins,
            ignore_zeros=ignore_zeros,
        )

        # Partial end: [end_of_last_full_block, last_statistical_index):
        end_of_last_full = last_full_block * hours_per_block
        partial_end = self.get_histogram(
            max(first_statistical_index, end_of_last_full),
            last_statistical_index,
            historical_data,
            number_of_bins,
            ignore_zeros=ignore_zeros,
        )

        return historical_distributions + partial_start + partial_end
    
    def get_absolute_index_of_date(self, date):
        """
        Returns an index of that particular date in the full historical data available, using the manifest file edges.

        Args:
            date (datetime.datetime): The date to get the index of.
        """
        first_index = int((date - self.data_limit_left).total_seconds() // 3600)
        last_index = first_index + 24

        return first_index, last_index

    def adjust_forecasted_horizon(self, future_start_date, future_end_date):
        """
        As the simulated horizon length is not always divisible by the ``draw_period``, we add simulation dates at the rightmost edge of the future horizon to cover for inconsistent patching.
        We also keep track of the number of hours actually needed to return after the simulation fills the data for the adjusted right-hand horizon.

        Args:
            future_start_date (datetime.datetime): The user-defined start date of the future horizon.
            future_end_date (datetime.datetime): The user-defined end date of the future horizon.

        Returns:
            future_end_date (datetime.datetime): The adjusted end date of the future horizon.
            hours_needed (int): The actual number of hours we need to return on a ``random_Sample()`` call to make sure we fill only the user-requested horizon and nothing more.
        """
        return future_end_date + datetime.timedelta(days = self.draw_period), int((future_end_date - future_start_date).total_seconds() // 3600 + 24)
    
    def append_resampled_columns(self,
        sample: NDArray[np.floating],
        rng: np.random.Generator,
    ) -> VersionedColumnsNDArray:
        """
        Appends len(self.duplicate_canonical_streams) new columns to the original sample,
        one per masked feature,
        by mapping quantiles under the old (empirical) distribution to the new distribution.

        Uses old_pdf/old_cdf (one row per unique masked column) via self.duplicate_histogram_positions indirection,
        so duplicate columns sharing the same historical histogram do not duplicate storage.

        new_cdf rows correspond to duplicated_columns order (row j -> duplicated_columns[j]).

        When ``self.ignore_zeros`` is True (solar mode), zero-valued hours in each
        sampled stream are preserved as-is and only positive loadfactors participate
        in the inverse-CDF resampling, consistent with the histogram building in
        ``get_Histogram`` and ``get_Fast_Histogram``.

        Args:
            sample (NDArray[np.floating]): The sampled data to append resampled columns to.
            rng (np.random.Generator): The random number generator to use for jittering.

        """
        if len(self.mask) == 0:
            return VersionedColumnsNDArray(n_raw_features=sample.shape[1]).attach_data(sample)

        n_unique_features_to_modify, n_bins = self.old_pdf.shape
        n_features_to_modify = len(self.duplicate_canonical_streams)
        
        if self.new_cdf.shape != (n_features_to_modify, n_bins):
            raise ValueError(f"new_cdf must have shape ({n_features_to_modify}, {n_bins}), but has shape {self.new_cdf.shape}")
        if len(self.duplicate_histogram_positions) != n_features_to_modify:
            raise ValueError("duplicate_histogram_positions must have one entry per duplicated feature. "+
                "Otherwise we don't know which row of the old_pdf/old_cdf to use for each duplicated feature.")

        n_hours, n_raw_features = sample.shape

        # Output: copy originals + appended transformed columns
        # View: keep track of multiple versions and their order in transforming original columns:
        output = np.empty((n_hours, n_raw_features + n_features_to_modify), dtype=np.float32)
        view = VersionedColumnsNDArray(n_raw_features=n_raw_features)
        output[:, :n_raw_features] = sample

        bin_width = 1.0 / n_bins
        old_total = self.old_cdf[:, -1] # (n_unique_features_to_modify,)

        for j, col in enumerate(self.duplicate_canonical_streams):
            sampled_stream = sample[:, col]
            absolute_index = view.update_mapping(canonical_col=col, j=j)
            # The indirection to reuse old_pdf/cdf:
            prev_hist_j = self.duplicate_histogram_positions[j]

            # Identify which hours to resample vs. keep as zero, if needed:
            if self.ignore_zeros:
                nz = sampled_stream > 0
                n_active = int(nz.sum())
                # Skip everything if the entire sample is 0:
                if n_active == 0:
                    output[:, absolute_index] = 0.0
                    continue
                active = sampled_stream[nz]
            else:
                nz = None
                n_active = n_hours
                active = sampled_stream

            # Finding the percentile along the old distribution of our sample's elements:
            position_proxy = active * n_bins

            # Firstly, the binclasses:
            bin_classes = position_proxy.astype(np.int32) # Cannot use unsigned as we need to access bin_classes - 1 un-lazily in computing observations_before;
            # Clip to [0, n_bins-1] in-place so any loadfactor at 1.0 doesn't overflow into bin number n_bins;
            np.clip(bin_classes, 0, n_bins - 1, out=bin_classes)

            fractional_part = position_proxy - bin_classes
            # Crop fractional_part to [0,1) in-place (so an hour with a loadfactor of 1.0 doesn't produce frac of 1.0):
            np.minimum(fractional_part, np.nextafter(1.0, 0.0), out=fractional_part)

            # Approximate the position of the sample in the old distribution with a linear interpolation within the bin:
            observations_before = np.where(bin_classes > 0, self.old_cdf[prev_hist_j, bin_classes - 1], 0)
            observations_within = self.old_pdf[prev_hist_j, bin_classes]
            percentile_aprox = (observations_before + fractional_part * observations_within) / old_total[prev_hist_j]

            # Invert percentile_aprox through new CDF to get new bin index:
            new_bin_classes = np.searchsorted(self.new_cdf[j], percentile_aprox, side="left")
            new_bin_classes = np.clip(new_bin_classes, 0, n_bins - 1)

            # Jitter within new bin:
            resampled = ((new_bin_classes + rng.random(n_active)) * bin_width).astype(np.float32, copy=False)

            # Replace only the non-zero elements of the sampled stream with their resampled version, if needed:
            if nz is not None:
                out_col = np.zeros(n_hours, dtype=np.float32)
                out_col[nz] = resampled
                output[:, absolute_index] = out_col
            else:
                output[:, absolute_index] = resampled
        
        return view.attach_data(output)


    @staticmethod
    def compute_time_margins(historical_start, historical_end, data_limit_left, data_limit_right):
        """
        Utility method used to compute the start and end point of stric hour-mark timeseries data dynamically at runtime in both full hours and full days, 
        cropping in case we asked for more than what we have available.

        In full days, we return the midnight start of the first and last day for which we have that entire day's data available.

        Args:
            historical_start (datetime.datetime): The datetime the user requested as the start of the historical data (inclusive).
            historical_end (datetime.datetime): The datetime the user requested as the end of the historical data (inclusive).
            data_limit_left (datetime.datetime): The leftmost datetime that we can use to index our historical data.
            data_limit_right (datetime.datetime): The rightmost datetime that we can use to index our historical data.

        Returns:
            start_datetime (pandas.Timestamp): The datetime of the first valid entry in the user horizon.
            start_date (pandas.Timestamp): The datetime of the first valid entry in the user horizon, rounded forward to the next midnight, unless already a midnight itself.
            end_datetime (pandas.Timestamp): The datetime of the last valid entry in the user horizon.
            end_date (pandas.Timestamp): The datetime of the last valid entry in the user horizon, rounded backward 2 previous midnights, unless already at or past 11PM, in which case we round to just the previous midnight.
        """

        historical_start = pd.Timestamp(historical_start)
        historical_end = pd.Timestamp(historical_end)
        
        # Enforcing strict hour marks while keeping logical behaviour inclusive of the user input
        # If already on an hour mark, leaves them unchanged:
        historical_start = historical_start.ceil("H") 
        historical_end = historical_end.floor("H")
        
        start_datetime = max(historical_start, data_limit_left)
        start_date = start_datetime + datetime.timedelta(hours = 24 - (24 if start_datetime.hour == 0 else start_datetime.hour))
        end_datetime = min(historical_end, data_limit_right)
        end_date = end_datetime - datetime.timedelta(hours = (24 if end_datetime.hour != 23 else 0) + end_datetime.hour)

        return start_datetime, start_date, end_datetime, end_date

    @staticmethod    
    def rowwise_logsumexp(a: NDArray[np.float64]) -> NDArray[np.float64]:
        """
        Compute log(sum(exp(a))) per row. Returns shape (n_rows,).
        """
        
        row_max = np.max(a, axis=1) # (n_rows,)
        exp_sum = np.sum(np.exp(a - row_max[:, None]), axis=1)  # (n_rows,)
        return row_max + np.log(exp_sum)

    @staticmethod
    def data_mean_and_var_under_logweights_probability(
        logw: NDArray[np.float64],
        mid_bins: NDArray[np.float64],
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """
        Given log-weights logw[j,i] (unnormalized), compute mean and var of the data if
        it were distributed under the normalized weights for each row j.

        Args:
            logw (NDArray[np.float64]): shape (n_distributions, n_bins) of unnormalized log-weights.
            mid_bins (NDArray[np.float64]): shape (n_bins,) of the midpoints of the bins corresponding to the weights.

        Returns:
            mean (NDArray[np.float64]): shape (n_distributions,) of the means under the normalized weights.
            var (NDArray[np.float64]): shape (n_distributions,) of the variances under the normalized weights.
        """
        # Avoiding exp(large_weight) in a stable way:
        maxs = np.max(logw, axis=1, keepdims=True)
        stable_weights = np.exp(logw - maxs)
        sumw = np.sum(stable_weights, axis=1) # (n_distributions,)

        first_moment = (stable_weights @ mid_bins) / sumw
        second_moment = (stable_weights @ (mid_bins * mid_bins)) / sumw
        mean = first_moment
        var = np.maximum(second_moment - first_moment * first_moment, 0.0)

        return mean, var

    @staticmethod
    def compute_optimized_distributions(
        previous_distribution_not_normalized: NDArray[np.uint32],
        desired_averages: Sequence[float],
        observations_per_column: Union[int, Sequence[int], NDArray],
        tol: float = 1e-12,
        max_iter: int = 60,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """
        Exponential-tilt each column-histogram (with frequency counts proportional to p_i) to match a desired mean, minimizing KL(q_i||p_i).

        Relies on the fact that the mean of the tilted distribution q_i is monotone in the tilt parameter lambda,
        so we can solve for lambda with a safely bounded Newton method.

        Also relies on the fact that the KL divergence is separable by column, so we can solve for each column independently and in parallel,
        with the caveat that we need to duplicate certain streams' historical distributions that have more than a single desired average.

        Args:
            previous_distribution_not_normalized (NDArray[np.uint32]):
                uint32 array shape (n_streams, n_bins) with the frequency counts of the historical data.
            desired_averages (Sequence[float]):
                Sequence of length n_streams. Desired E_q[X] per column.
            observations_per_column (Union[int, Sequence[int], NDArray]):
                Number of observations per column in previous_distribution_not_normalized, used to normalize.
                If scalar, the same count is used for all columns. If array-like, must have
                length n_streams, giving per-column observation counts (useful when columns
                have different amounts of valid data, e.g. after zero-filtering for solar).
            tol (float):
                Absolute tolerance on mean matching per column.
            max_iter (int):
                Maximum allowed iterations for the bracketed Newton solve.

        Returns:
            q (NDArray[np.float64]):
                float64 array shape (n_streams, n_bins) with the tilted probabilities per column.
            lambdas (NDArray[np.float64]):
                float64 array shape (n_streams,) with the solved tilt parameter per column.
        """
        # Basic shape/consistency checks:
        observations_per_column = np.asarray(observations_per_column, dtype = np.int32)
        if np.any(observations_per_column <= 0):
            raise ValueError("observations_per_column must be >= 0")

        if previous_distribution_not_normalized.ndim != 2:
            raise ValueError(
                "previous_distribution_not_normalized must be 2D with shape (n_cols, n_bins)"
            )

        n_streams, n_bins = previous_distribution_not_normalized.shape
        averages = np.asarray(desired_averages, dtype=np.float64)

        if averages.shape[0] != n_streams:
            raise ValueError(
                f"averages length must match number of columns in previous_distribution_not_normalized: "
                f"{averages.shape[0]} != {n_streams}"
            )

        if observations_per_column.ndim == 0:
            observations_per_column = np.full((n_streams,), observations_per_column.item(), dtype=np.int32)
        
        if observations_per_column.shape != (n_streams,):
            raise ValueError(
                "observations_per_column must be a scalar or a 1D array with length n_streams"
            )


        # Build the log previous PDF: log(each bin's count) - log(observations_per_column);
        log_total = np.log(observations_per_column)

        actual_observations = previous_distribution_not_normalized > 0
        # Making sure we don't fail on computing log(0):
        with np.errstate(divide="ignore"):
            log_counts = np.log(previous_distribution_not_normalized)
        # Fill 0 count bins with -inf:
        logp = np.where(actual_observations, log_counts - log_total[:, None], -np.inf)

        # Bin centers in [0, 1]:
        mid_bins = (np.arange(n_bins, dtype=np.float64) + 0.5) / n_bins

        # Compute achievable mean range per column (given support p_i: bins where counts>0)
        # mid_bins[None, :] broadcasts to shape (1, n_bins) to align with logp shape (n_streams, n_bins) that data has:
        min_possible_avg = np.where(actual_observations, mid_bins[None, :], np.inf).min(axis=1)
        max_possible_avg = np.where(actual_observations, mid_bins[None, :], -np.inf).max(axis=1)

        # If target average is outside achievable range,
        # we clip to the achievable range, with warning:
        averages_clipped = averages.copy()
        averages_clipped = np.clip(averages_clipped, min_possible_avg, max_possible_avg)
        if not np.array_equal(averages, averages_clipped):
            warnings.warn(
                "Some desired averages were outside the achievable range given the support of the previous distribution. "
                "They have been clipped to the nearest achievable value. "
            )

        # Solve for unique lambda per column with bracketed Newton.
        # Choose symmetric initial bracket magnitude based on x-range.
        support_range = (max_possible_avg - min_possible_avg)
        lambda_guess = np.zeros((n_streams,), dtype=np.float64) # start at zero, replicating initial distribution
        # One lower mean and one higher mean guesses for lambda, trimmed by Newtonian convergence:
        L = 50.0 / np.maximum(support_range, 1e-12)
        lo = -L
        hi = +L

        for _ in range(max_iter):
            # Evaluate mean/var at current lam for active columns
            logw = logp + lambda_guess[:, None] * mid_bins[None, :]
            mean, var = BucketedData.data_mean_and_var_under_logweights_probability(logw, mid_bins)
            # Error in mean matching at current guess:
            diff = mean - averages_clipped

            # Convergence if goal met for all columns:
            if np.max(np.abs(diff)) <= tol:
                break

            # Update brackets based on monotonicity: mean increases with lambda
            # If mean < target -> need larger lambda, and vice versa:
            need_up = diff < 0
            lo[need_up] = lambda_guess[need_up]
            hi[~need_up] = lambda_guess[~need_up]

            # Newton step: lambdas_new = lambdas_guess - (mean-target)/var
            lambdas_new = lambda_guess.copy()
            good = var > 1e-18 # avoid divide by near-zero for low-variance columns, will take bisection step instead for those
            # Newton update step makes use of the linearization of the objective function around the current guess: f(λ) ≈ f(λ_t​) + f′(λ_t​)*(λ_(t+1)−λ_t​).
            # For us, f(λ) = mean(λ) − desired_average = 0, for each row.
            # Hence f′(λ) = mean′(λ) = Var_q(λ)​[X], we get the update below:
            lambdas_new[good] = lambdas_new[good] - diff[good] / var[good]

            # If Newton overshoots to nan/inf or var too small, take bisection step;
            # We can only do this becuse the objective function is continuous and monotone in lambda, so the root is guaranteed to be in the bracket:
            mid = 0.5 * (lo + hi)
            bad = ~good | ~np.isfinite(lambdas_new)
            lambdas_new[bad] = mid[bad]

            # Clip to bracket
            lambdas_new = np.minimum(np.maximum(lambdas_new, lo), hi)

            # Update lambda
            lambda_guess = lambdas_new

        # Build final q (rowwise probabilities)
        logw = logp + lambda_guess[:, None] * mid_bins[None, :]
        logZ = BucketedData.rowwise_logsumexp(logw)
        q = np.exp(logw - logZ[:, None])

        return q, lambda_guess
