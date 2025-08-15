# The SolarData module aims to encapsulate all the information and logic needed to generate solar hourly loadfactors for each plant in the future.

# It is a child of the BucketedData class that encapsulates all functionality used between the input types that bucket as a sampling mechanism.
# It has a slightly modified Bucketer child, the IntermittentBucketer, to sample random solar loadfactors in a way that preserves calendar patterns of solar.

# The sampling loop can run after the object is initialized, and it will return a numpy array of chronologically arranged hour-by-hour loadfactor datapoints filling the date range specified by 2 pd.Timestamp(s) or datetime.datetime(s).
# The sampling loop also makes use of the inverse sampling algorithm if ir requires this transformation. It turns data from the original historical distribution into a new distribution that was optimized for the purpose of changing the natural average.

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime
import random

from ..weather.IntermittentBucketer import IntermittentBucketer
from ..weather.BucketedData import BucketedData
from ..database.Database import Database

class SolarData(BucketedData):
    def __init__(self, connection, historical_start_date = datetime.datetime(2006, 7, 1), historical_end_date  = datetime.datetime(2023, 1, 1), desired_averages = [], solarstreams = []):

        if len(desired_averages) != len(solarstreams):
            raise ValueError("You need to specify as many desired averages as solarstreams. " +
                "Check there are None placeholders for the solarstreams that have no overridden average.")
        self.data = connection.get_Solar_Streams(historical_start_date, historical_end_date, solarstreams)

        self.desired_Averages = desired_averages
        # Save which solarstreams require this transformation in the mask (starting with 0):
        self.mask = np.array([i for i in range(len(self.desired_Averages)) if (self.desired_Averages[i] != None and not (np.isnan(self.desired_Averages[i])))])

        self.historical_Start_Datetime, self.historical_Start_Date, self.historical_End_Datetime, self.historical_End_Date = BucketedData.compute_Time_Margins(self.data)

        self.intermittent_Bucketer = IntermittentBucketer(historical_start_date = self.historical_Start_Date, historical_end_date = self.historical_End_Date, draw_period = 7)

        self.data = self.data.to_numpy()


        if (len(self.mask) != 0):
            # Get only the cropped-to-full-year data while keeping the most recent historical datapoints; only the start date can change:
            statistical_start_date = self.crop_Time_Margins_To_Full_Years()
            historical_data = self.data[:, self.mask + 1][self.data[:, 0] >= statistical_start_date] # TO DO: This code will have to change once the cloud version of solar is online (and once solar gets more plants), because selecting the magic number column 1 is not a good solution if the data is prefaced by 3/4 columns of datetime stamps like the case may be for WindData;

            # Getting the expected ratio of daytime hours to total hours in a year:
            total_hours = len(historical_data)

            all_non_zero_sorted_historical_data = []
            bin_width = []
            new_cdf = []

            for plant_no in range(len(self.mask)):

                plant_data = historical_data[:, plant_no]
                plant_data = plant_data[plant_data != 0]

                # One manual override plant at a time, the historical_Data field gets updated (we need this for the way get_Historical_PDF() works):
                self.historical_Data = np.sort(plant_data)
                # We keep the references to this data for later access when we random_Sample():
                all_non_zero_sorted_historical_data.append(self.historical_Data)

                total_Daytime = len(plant_data)
                expected_daytime = total_hours / total_Daytime
                # Updating the desired average for daytime only hours:
                self.desired_Averages[self.mask[plant_no]] *= expected_daytime

                if(self.desired_Averages[self.mask[plant_no]] >= 0.999):
                    raise ValueError("The desired average cannot be attained while keeping the nighttime periods at 0 generation. " +
                        "Update your requirement with a smaller manually overriden value.")

                # The method should work each time with a different array saved in self.historical_Data:
                previous_distribution, bins = self.get_Historical_PDF()
                bin_width.append(bins[1] - bins[0])
                new_distribution = BucketedData.compute_Optimized_Distribution(previous_distribution, bins, self.desired_Averages[self.mask[plant_no]])
                new_cdf.append(np.asarray(np.cumsum(new_distribution)))

            self.bin_Width = bin_width
            self.historical_Data = all_non_zero_sorted_historical_data
            self.new_CDF = new_cdf



    @property
    def draw_Period(self):
        return self.intermittent_Bucketer.draw_Period


    def random_Sample(self, future_start_date, future_end_date, python_rng=random.Random(0), numpy_rng=np.random.default_rng(0)):

        future_end_date, hours_needed = self.adjust_Forecasted_Horizon(future_start_date, future_end_date)

        sample = []
        sampled_dates = self.intermittent_Bucketer.random_Sample(future_start_date, future_end_date, python_rng)

        # initial_bucket = self.intermittent_Bucketer.bucket_of(future_start_date)
        # slice_start = 0
        # slice_end = 0

        for date in sampled_dates:
            # bucket = self.intermittent_Bucketer.bucket_of(date)

            # if not bucket == initial_bucket:
            #     scaling_factor = max(0, np.random.normal(self.averages[initial_bucket], self.standard_Deviations[initial_bucket]))
            #     sample[slice_start : slice_end] = np.multiply(sample[slice_start : slice_end], scaling_factor / np.mean(sample[slice_start : slice_end]))

            #     slice_start = slice_end
            #     initial_bucket = bucket

            first_index, last_index = self.get_Index_of_Date(date)
            last_index = first_index + self.intermittent_Bucketer.draw_Period * 24

            sample.append(self.data[:, 1:][first_index : last_index])# sample.append(self.historical_Demand[first_historical_index : last_historical_index,1]*self.forecast_Demand[first_forecast_index : last_forecast_index,1] / np.array(self.averages[category][bucket]))
            # slice_end += 1

        sample = np.asarray(np.concatenate(sample))

        for plant_no in range(len(self.mask)):
            plant_sample = sample[:, self.mask[plant_no]]
            plant_sample[plant_sample != 0] = np.searchsorted(self.new_CDF[plant_no], np.searchsorted(self.historical_Data[plant_no], plant_sample[plant_sample != 0]) / len(self.historical_Data[plant_no])) * self.bin_Width[plant_no] + numpy_rng.uniform(high = self.bin_Width[plant_no], size = plant_sample[plant_sample != 0].size)
            sample[:, self.mask[plant_no]] = plant_sample

        return sample[:hours_needed]

def main():
    connection = Database.Database()

    sd = SolarData(connection, historical_start_date = datetime.datetime(2006, 7, 1), historical_end_date = datetime.datetime(2021, 7, 1), desired_averages = [0.2, None, 0.5], solarstreams = ["solar_loadfactor", "solar_loadfactor", "solar_loadfactor"])
    for i in range(1):
        forecast = sd.random_Sample(datetime.datetime(2023, 7, 1), datetime.datetime(2025, 7, 1))

    for i in range(len(forecast[0])):
        plt.figure(figsize=(12, 8))
        plt.plot(pd.date_range(datetime.datetime(2023, 7, 1), datetime.datetime(2025, 7, 1) + datetime.timedelta(hours = 23), freq='H'), forecast[:, i], color = "orange")
        plt.savefig(f'/dbfs/mnt/gold/elfo/Dev/plots/SolarLoadFactors.png')



if __name__ == '__main__':
    main()
