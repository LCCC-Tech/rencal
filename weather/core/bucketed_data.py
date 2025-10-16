# The purpose of the BucketedData class is to serve as a container for all shared functionality between input modules that use the Bucketer as the main generation machanism.

# It is the parent class of the SolarData, WindData, and DemandData classes.

# It has no state of its own, it relies on the fields of other classes to be named accordingly (historical_Start/End_Date, new_CDF, historical_Data, bin_Width).
# It is ready for the deployment of multiple solar streams in that regard, since it can repurpose those optimisation functions abstracted away from WindData.

# There is no main output, as the class functions more like an abstract class template of shared logic.

import datetime
import numpy as np

from scipy.optimize import minimize
from scipy.special import rel_entr
from bisect import bisect_left

class BucketedData:
    """
    The purpose of this class is to serve as a container for all shared functionality between input modules that use the :class:`Bucketer` as the main path-generation mechanism.

    It is the parent class of the :class:`SolarData`, :class:`WindData`, and :class:`DemandData` classes.

    It has no state of its own, it relies on the fields of other classes to be named accordingly.

    There is no main output, as the class functions more like an abstract class template of shared logic.
    """
    def __init__(self):
        pass


    def crop_Time_Margins_To_Full_Years(self):
        """
        Used to crop the training data at the far (left) end, such that no calendar interval is overrepresented.
        It disregards the most distant dates to return a date from which, if historical data were to start, no calendar date would repeat itself more than any other.

        Returns:
            start_date (datetime.datetime): The date from which to start the historical data for no bias in the yearly distribution.
        """
        month = self.historical_End_Date.month
        day = self.historical_End_Date.day
        year = self.historical_Start_Date.year

        start_date = datetime.datetime(year, month, day)

        while start_date < self.historical_Start_Date:
            year += 1
            start_date = datetime.datetime(year, month, day)

        # We need at least a year's worth of data to create unbiased yearly distributions:
        if (self.historical_End_Date - start_date) < datetime.timedelta(365.2425):
            raise ValueError("There is insufficient historical data to have a full picture of the yearly distribution")

        return start_date

    # Function returns a summary of the discrete PDF of the historical (cropped) data:
    def get_Historical_PDF(self, plant_no = None):
        """
        Function returns a summary of the discrete PDF of the historical (cropped) data.

        Args:
            plant_no (int): The plant number to get the historical PDF for. Defaults to None.
        """
        if plant_no != None:
            historical_data = self.historical_Data[:, plant_no]
        else:
            historical_data = self.historical_Data
            
        weights = np.ones_like(historical_data) / len(historical_data) # Used these weights for the histogram such that the sum of all of the columns it yields is 1
        auto_bins = np.histogram_bin_edges(historical_data, bins = 100) # Use "auto" for the best of both worlds (both small and large samples) in terms of minimizing the differences in area between the histogram and the theoretical continuous PDF

        # np.histogram returns us the histogram column values as well as the bins in the second variable:
        hist1, hist2 = np.histogram(historical_data, weights = weights, bins = auto_bins)

        return hist1.astype(np.float64), hist2.astype(np.float64)

    # Returns an index of that particular date in the historical data (non-cropped):
    def get_Index_of_Date(self, date):
        first_index = int((date - self.historical_Start_Datetime).total_seconds() // 3600)
        last_index = first_index + 24

        return first_index, last_index

    def adjust_Forecasted_Horizon(self, future_start_date, future_end_date):
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
        return future_end_date + datetime.timedelta(days = self.draw_Period), int((future_end_date - future_start_date).total_seconds() // 3600 + 24)


    @staticmethod
    def compute_Time_Margins(dataframe):
        """
        Utility method used to compute the start and end point of timeseries data dynamically at runtime, in case we asked for more than we have available.

        Args:
            dataframe (pandas.DataFrame): The dataframe containing the timeseries data, whose first column is the datetime index, either in :class:`pandas.Timestamp` or :class:`datetime.datetime` format.

        Returns:
            start_datetime (pandas.Timestamp): The datetime of the first entry in the dataframe.
            start_date (pandas.Timestamp): The datetime of the first entry in the dataframe, rounded forward to the next midnight, unless already a midnight itself.
            end_datetime (pandas.Timestamp): The datetime of the last entry in the dataframe.
            end_date (pandas.Timestamp): The datetime of the last entry in the dataframe, rounded backward 2 previous midnights, unless already 11PM, in which case we round to just the previous midnight.
        """
        start_datetime = dataframe.iloc[0, 0]
        start_date = start_datetime + datetime.timedelta(hours = 24 - (24 if start_datetime.hour == 0 else start_datetime.hour))
        end_datetime = dataframe.iloc[len(dataframe.iloc[:, 0]) - 1, 0]
        end_date = end_datetime - datetime.timedelta(hours = (24 if end_datetime.hour != 23 else 0) + end_datetime.hour)

        return start_datetime, start_date, end_datetime, end_date

    # Main goal of the optimisation algorithm:
    @staticmethod
    def KL_Divergence(previous_distribution, new_distribution):
        return np.sum(rel_entr(previous_distribution, new_distribution))

    # Returns a distribution promised to be "just like" the previous_distribution in terms of information content, but with a different desired_average:
    @staticmethod
    def compute_Optimized_Distribution(previous_distribution, bins, desired_average):
        avg = bins[:len(bins) - 1] + ((bins[1:] - bins[:len(bins) - 1]) / 2) # This computes the midpoints of each bin in the histogram

        cons=({'type': 'eq',
               'fun': lambda x: sum(x) - 1},
              {'type': 'eq',
               'fun': lambda x: np.sum(avg * x) - desired_average})

        x0 = previous_distribution # The initial guess matches our initial probability distribution
        bnds = [(0, 1) for _ in range(len(x0))]
        
        res = minimize(lambda new_distribution: BucketedData.KL_Divergence(previous_distribution, new_distribution), x0, constraints = cons, bounds = bnds, options = {"maxiter": 5000})

        if res.success == True:
            return res.x
        else:
            raise ValueError("Optimization is not working properly")

