import pandas as pd
import numpy as np
import datetime
import random

from ..database.Database import Database
from ..constants import Constants
from ..weather.BucketedData import BucketedData
from ..weather.DemandBucketer import DemandBucketer

class DemandData(BucketedData):
    """
    The DemandData module aims to encapsulate all the information and logic needed to generate national demand hourly samples for future time intervals.

    It is a child of the :class:`BucketedData` class that encapsulates all functionality of the input types that use buckets as a resampling mechanism.
    It creates instances of its own special :class:`Bucketer` child, the :class:`DemandBucketer`, to sample random historical demand in a way that not only preserves calendar patterns of demand, but the business day patterns as well.

    The sampling loop can run after the object is initialized, and it will return a numpy array of chronologically arranged hour-by-hour demand datapoints filling the date range specified by 2 :class:`pandas.Timestamp` or :class:`datetime.datetime`.

    Attributes:
        forecast_Demand (numpy.ndarray): Hourly :class:`numpy.float64` values of the LCCC internal national demand forecasting model, for the entire forecast horizon.
        historical_Demand (numpy.ndarray): Hourly :class:`numpy.float64` values of historical national demand for the entire historical horizon.
        bank_Holidays (pandas.DataFrame): DataFrame of bank holidays in the UK as :class:`pandas.Timestamp` objects.
        historical_Start_Datetime (pandas.Timestamp): The chronologically first datetime in the historical_Demand. Never less than ``2012-01-01 00-00-00``.
        historical_Start_Date (pandas.Timestamp): The start of the first historical_Demand day with full data available (with 24 datapoints).
        historical_End_Datetime (pandas.Timestamp): The chronologically last datetime in the historical_Demand. Never more than ``2023-12-02 23-00-00``.
        historical_End_Date (pandas.Timestamp): The start of the last historical_Demand day that still has full data available (24 datapoints).
        forecast_Start_Datetime (pandas.Timestamp): The chronologically first datetime in the historical_Demand. Never less than ``2012-01-01 00-00-00``.
        forecast_Start_Date (pandas.Timestamp): The start of the first historical_Demand day with full data available (with 24 datapoints).
        forecast_End_Datetime (pandas.Timestamp): The chronologically last datetime in the historical_Demand. Never more than ``2023-12-02 23-00-00``.
        forecast_End_Date (pandas.Timestamp): The start of the last historical_Demand day that still has full data available (24 datapoints).
        scaling_Bucketer (DemandBucketer): The Bucketer object used to compute the hourly averages in advance (before the main sampling loop) where every day is treated individually.
        demand_Bucketer (DemandBucketer): The Bucketer object used in the main sampling logic, pulling the ``draw_period`` amount of days required by the sampling mechanism.
        averages (dict): A nested dictionary of per bucket and category hourly averages across the historical data, with the special, "bank holiday" category, represented as the category at key ``7``.
    """
    def __init__(self, connection, historical_start_date = None, historical_end_date = None,
                forecast_start_date = None, forecast_end_date = None):
        """
        In initializing the class, we pull an internal linear regression future demand forecast in ``forecast_Demand``, and historical demand datapoints as percentages of their particular year's ACS peak value in ``historical_Demand``, both :class:`numpy.float64` arrays.
        We also pull the ``bank_Holidays`` as an array of :class:`pandas.Timestamps` to pass to the :class:`DemandBucketers`, of which there are two

        - The scaling_Bucketer is used in computing historic hourly averages where every day is treated individually, using a draw_period of ``1`` (such that bank holidays are found in the bucket you would actually expect them to be);
        - The demand_Bucketer is used in the main sampling logic, pulling the draw_period amount of days required by the sampling mechanism (and hence those draw_period intervals get assigned to either bucket at a boundary via where the majority of days in that interval fall);
        
        We also save the timestamps where the historical and the forecast data start and end to use them to compute array positions in the main sampling logic ``random_Sample()``.
        """
        peaks = connection.get_ACS_Peaks() # Each year's max demand value.
        historical_demand = connection.get_Historical_Demand(historical_start_date = historical_start_date, historical_end_date = historical_end_date)
        self.forecast_Demand = connection.get_Forecast_Demand(forecast_start_date = forecast_start_date, forecast_end_date = forecast_end_date) # Nostradamus outputs.

        # The reason why the BucketedData method compute_Time_Margins is static is because we need to apply it on another dataframe within this class apart from the usual "self.historical_Data"-like:
        self.historical_Start_Datetime, self.historical_Start_Date, self.historical_End_Datetime, self.historical_End_Date = BucketedData.compute_Time_Margins(historical_demand)
        self.forecast_Start_Datetime, self.forecast_Start_Date, self.forecast_End_Datetime, self.forecast_End_Date = BucketedData.compute_Time_Margins(self.forecast_Demand)

        self.bank_Holidays = connection.get_Bank_Holidays(historical_start_date = self.historical_Start_Date, forecast_end_date = self.forecast_End_Date)

        # In-place scaling of the historical demand to remove yearly trends: historical_Demand is expressed in percentages (how much of their year's max demand each hour represents).
        self.ACS_Scaling(historical_demand, peaks)
        self.historical_Demand = historical_demand

        # Using another object here to compute per bucket and category averages in compute_Hourly_Averages():

        # Pass in a random seed to the scaling and demand bucketers to ensure that the same buckets are sampled for the same time interval:
        self.scaling_Bucketer = DemandBucketer(draw_period = 1, bucket_definition = Constants.WEEKLY_BUCKET_DEFINITION,
            historical_start_date = self.historical_Start_Date, historical_end_date = self.historical_End_Date, bank_holidays = list(self.bank_Holidays))
        self.demand_Bucketer = DemandBucketer(draw_period = 7, bucket_definition = Constants.WEEKLY_BUCKET_DEFINITION,
            historical_start_date = self.historical_Start_Date, historical_end_date = self.historical_End_Date, bank_holidays = list(self.bank_Holidays))


        self.averages = self.compute_Hourly_Averages()

        self.historical_Demand = self.historical_Demand.to_numpy()
        self.forecast_Demand = self.forecast_Demand.to_numpy()


    @property
    def draw_Period(self):
        return self.demand_Bucketer.draw_Period


    # Method scales the historical demand in-place, replacing values in MWh with percentages that represent how large was demand that particular hour compared to the year's maximum hourly demand:
    def ACS_Scaling(self, historical_demand, peaks):
        """
        Replaces the historical demand data in place with the scaled version of it, where each hour's demand is expressed as a percentage of the ACS peak demand for that year.
        
        Args:
            historical_demand (pandas.DataFrame): The historical demand data extracted from the database, with the **gmt_datetime** (pandas.Timestamp) and **national_demand** (float) columns.
            peaks (pandas.DataFrame): ACS Demand Peaks with a **Year** (int) index and **Value** (float) column.
        """
        peak_scaled_demand = []
        # Gets a pd.Series with the first/last element in the historical demand, converts it to a numpy array to perform type manipulations that extract the year with the default epoch of 1970-01-01T00:00
        first_historical_year = (historical_demand.head(1)["gmt_datetime"].values.astype('datetime64[Y]').astype(int) + 1970)[0]
        last_historical_year = (historical_demand.tail(1)["gmt_datetime"].values.astype('datetime64[Y]').astype(int) + 1970)[0]

        for year in range(first_historical_year, last_historical_year + 1):
            # Get each year of historical demand:
            spliced_data = historical_demand[(historical_demand["gmt_datetime"] >= np.datetime64(str(year) + '-01-01')) & (historical_demand["gmt_datetime"] < np.datetime64(str(year + 1) + '-01-01'))]
            # Retrieve the peak demand for that year by parsing the tabulated json from the SQL:
            peak = peaks.loc[year, 'Value']

            peak_scaled_demand += (spliced_data["national_demand"] / int(peak)).tolist() # Concatenate peak scaled data in the same order into a list

        scaled_demand = pd.DataFrame(peak_scaled_demand)
        scaled_demand.columns = ["national_demand"]

        historical_demand["national_demand"] = scaled_demand["national_demand"] # Replace the data, now scaled to ACS peaks

    
    def compute_Hourly_Averages(self):
        """
        Makes use of the ``scaling_Bucketer`` to compute per bucket and category hourly averages, with the special, "bank holiday" category, represented as the category at key ``7``.

        Returns:
            averages (dict): A nested dictionary of per bucket and category hourly averages across the historical data, mirroring the ``bucket_Structure`` data structure from the :class:`Bucketer` with the extra category for bank holidays.
        """
        # Getting averages needs a differentiation between bank and non-bank holidays, so the scaling structure has an additional category for them:
        scaling_structure = self.scaling_Bucketer.get_Scaling_Structure()

        # Mirroring the bucket_Structure data structure from the Bucketer, we save those averages in a nested dictionary per "category" and "bucket"
        averages = {category: {n: [] for n in range(0, len(Constants.WEEKLY_BUCKET_DEFINITION))} for category in range(7 + 1)}

        for category in scaling_structure:
            for bucket in scaling_structure[category]:
                # This usually happens for the "bank holiday" since there are weeks ("buckets") in the year where there are no bank holidays:
                if (len(scaling_structure[category][bucket]) == 0):
                    continue
                else:
                    for hour in range(24):
                        average = 0
                        hist = []

                        for date in scaling_structure[category][bucket]:
                            average += self.historical_Demand["national_demand"][int((date + datetime.timedelta(hours = hour) - self.historical_Start_Datetime).total_seconds() // 3600)]

                        average /= len(scaling_structure[category][bucket])
                        averages[category][bucket].append(average)

        return averages


    def random_Sample(self, future_start_date, future_end_date, python_rng=random.Random(0)):
        """
        The main sampling method that generates scenarios for national demand for a future horizon.
        It will replace every bank holiday in the future horizon with the nearest bank holiday found next to where the draw period was sampled from in the historical data.
        It will also replace every non-bank holiday in the future horizon with the nearest business day that preserves the weekday of the input date.

        Args:
            future_start_date (datetime.datetime): The start of the future horizon for which to generate demand scenarios.
            future_end_date (datetime.datetime): The end of the future horizon (inclusive) for which to generate demand scenarios.
            python_rng (random.Random): The random number generator to use for sampling.

        Returns:
            sample (numpy.ndarray): A :class:`numpy.ndarray` of :class:`numpy.float64` values representing the national demand for each consecutive hour in the future horizon.
        """
        # This asks for more data, retroactively moving the right edge of the simulation horizon further have enough demand to crop out:
        future_end_date, hours_needed = self.adjust_Forecasted_Horizon(future_start_date, future_end_date)

        if future_start_date < self.forecast_Start_Date or future_end_date > self.forecast_End_Date:
            raise ValueError("The sampled interval has no Nostradamus equivalent. Try a shorter interval close to the present date.")

        dates = self.demand_Bucketer.random_Sample(future_start_date, future_end_date, python_rng)

        sample = []
        test = []

        for index, date in enumerate(dates):
            for no_in_draw in range(self.draw_Period):
                first_historical_index = int((date + datetime.timedelta(no_in_draw) - self.historical_Start_Datetime).total_seconds() // 3600)
                last_historical_index = first_historical_index + 24

                first_forecast_index = int((future_start_date + datetime.timedelta(self.draw_Period * index + no_in_draw) - self.forecast_Start_Datetime).total_seconds() // 3600)
                last_forecast_index = first_forecast_index + 24

                category = self.demand_Bucketer.assign_Category(date + datetime.timedelta(no_in_draw))

                if self.demand_Bucketer.is_Bank_Holiday(date + datetime.timedelta(no_in_draw)) and not self.demand_Bucketer.is_Bank_Holiday(self.forecast_Demand[first_forecast_index, 0]):
                    non_BH_date = self.demand_Bucketer.nearest_Preserving_Weekday_Business_Day(date + datetime.timedelta(no_in_draw), python_rng)

                    first_historical_index = int((non_BH_date - self.historical_Start_Datetime).total_seconds() // 3600)
                    last_historical_index = first_historical_index + 24

                elif not self.demand_Bucketer.is_Bank_Holiday(date + datetime.timedelta(no_in_draw)) and self.demand_Bucketer.is_Bank_Holiday(self.forecast_Demand[first_forecast_index, 0]):
                    BH_date = self.demand_Bucketer.get_Nearest_Bank_Holiday(date + datetime.timedelta(no_in_draw))

                    first_historical_index = int((BH_date - self.historical_Start_Datetime).total_seconds() // 3600)
                    last_historical_index = first_historical_index + 24

                    category = self.demand_Bucketer.categories

                # Under whose bucket do we scale? What if this is the first future date that is a bank holiday in a certain week where there have never been bank holidays before?
                # Problem solved by scaling to the average computed from the actual bucket in which the historical date would be found (regardless if that bucket is different from the future one)
                bucket = self.scaling_Bucketer.bucket_of(self.historical_Demand[first_historical_index, 0])

                sample.append(self.historical_Demand[first_historical_index : last_historical_index, 1] * self.forecast_Demand[first_forecast_index : last_forecast_index, 1] / np.array(self.averages[category][bucket]))

        sample = np.concatenate(sample)

        return np.asarray(sample[:hours_needed], dtype = np.float64)


def main():
    dd = DemandData(Database.Database())

    # Generate future national demand for a certain future horizon:
    forecast = dd.random_Sample(future_start_date = datetime.datetime(2020, 3, 9),
    future_end_date = datetime.datetime(2025, 9, 7))

if __name__ == '__main__':
    main()
