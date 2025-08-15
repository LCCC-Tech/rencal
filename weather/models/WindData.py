# The WindData module aims to encapsulate all the information and logic needed to generate wind hourly loadfactors for each plant in the future.
# It works in a vectorized way, such that all plants are sampled at once using only one output of the Bucketer.

# It is a child of the BucketedData class that encapsulates all functionality used between the input types that bucket as a sampling mechanism.
# It has a slightly modified Bucketer child, the IntermittentBucketer, to sample random wind loadfactors in a way that preserves calendar patterns of wind:
# - it uses the same sampled historical period for all of the plants involved, keeping geographical correlations.

# In initializing it, we pull plant data to get the windstreams and their desired_average in the order of the plants we use.
# We would also perform the optimization of the yearly distributions to follow their historical distribution as close as possible of loadfactors to perform inverse distribution sampling in random_Sample() for those windstreams that require it.

# The sampling loop can run after the object is initialized, and it will return a numpy array of chronologically arranged hour-by-hour loadfactor datapoints filling the date range specified by 2 pd.Timestamp(s) or datetime.datetime(s).
# The sampling loop also makes use of the inverse sampling algorithm for the columns/windstreams that require this transformation. It turns data from the original historical distribution into a new distribution that was optimized for the purpose of changing the natural average.


import pandas as pd
import numpy as np
import datetime
import torch
import matplotlib.pyplot as plt
import random

from ..weather.IntermittentBucketer import IntermittentBucketer
from ..weather.BucketedData import BucketedData
from ..database.Database import Database

class WindData(BucketedData):
    def __init__(self, connection, historical_start_date = pd.Timestamp(1980, 1, 1), historical_end_date = pd.Timestamp(2023, 1, 1), desired_averages = [], windstreams = []):

        if len(desired_averages) != len(windstreams):
            raise ValueError("You need to specify as many desired averages as windstreams. " +
                "Check there are None placeholders for the windstreams that have no overridden average.")
        self.data = connection.get_Wind_Streams(historical_start_date, historical_end_date, windstreams)

        self.desired_Averages = desired_averages
        # Save which windstreams require this transformation in the mask (starting with 0):
        self.mask = np.array([i for i in range(len(self.desired_Averages)) if (self.desired_Averages[i] != None and not (np.isnan(self.desired_Averages[i])))])

        # Computes the margins of the time intervals for which we have data:
        self.historical_Start_Datetime, self.historical_Start_Date, self.historical_End_Datetime, self.historical_End_Date = BucketedData.compute_Time_Margins(self.data)

        self.intermittent_Bucketer = IntermittentBucketer(historical_start_date = self.historical_Start_Date, historical_end_date = self.historical_End_Date, draw_period = 7)

        self.data = self.data.to_numpy()

        if (len(self.mask) != 0):
            # Get only the cropped-to-full-year data while keeping the most recent historical datapoints; only the start date can change:
            statistical_start_date = self.crop_Time_Margins_To_Full_Years()
            historical_data = np.asarray(self.data[:, self.mask + 1][self.data[:, 0] >= statistical_start_date], dtype = float) # Gets the rows that need average transforming starting with the 2nd column onwards (only windstreams) that fit inside our cropped data (from the statistical_start_date onwards)
            self.historical_Data = np.sort(historical_data, axis = 0) # Sorts for faster searching in the inverse CDF

            # Needing one of those for each windstream:
            bin_width = []
            new_cdf = []

            for plant_no in range(len(self.mask)):
                previous_distribution, bins = self.get_Historical_PDF(plant_no)
                bin_width.append(bins[1] - bins[0])
                new_distribution = BucketedData.compute_Optimized_Distribution(previous_distribution, bins, self.desired_Averages[self.mask[plant_no]])
                new_cdf.append(np.cumsum(new_distribution))

            self.bin_Width = torch.from_numpy(np.asarray(bin_width).reshape(len(self.historical_Data[0]), 1))
            self.historical_Data = torch.t(torch.from_numpy(np.asarray(self.historical_Data, dtype=np.float64)))
            self.new_CDF = torch.from_numpy(np.asarray(np.vstack(new_cdf), dtype=np.float64))


    @property
    def draw_Period(self):
        return self.intermittent_Bucketer.draw_Period


    def random_Sample(self, future_start_date, future_end_date, python_rng=random.Random(40), numpy_rng=np.random.default_rng(22)):

        future_end_date, hours_needed = self.adjust_Forecasted_Horizon(future_start_date, future_end_date)

        sample = []
        sampled_dates = self.intermittent_Bucketer.random_Sample(future_start_date, future_end_date, python_rng)

        for date in sampled_dates:
            first_index, last_index = self.get_Index_of_Date(date)
            last_index = first_index + self.intermittent_Bucketer.draw_Period * 24
            # print(first_index, last_index)

            sample.append(self.data[:, 1:][first_index : last_index])

        sample = np.asarray(np.concatenate(sample), dtype = np.float64)

        if (len(self.mask) != 0):

            # Only get the windstreams that require inverse transformation sampling:
            sample_to_modify = torch.from_numpy(sample[:, self.mask])

            self.historical_Data = torch.from_numpy(np.asarray(self.historical_Data, dtype=np.float64)).contiguous()

            # The inverse sampling transformation:
            sample_to_modify = torch.t(torch.searchsorted(self.new_CDF, torch.searchsorted(self.historical_Data, torch.t(sample_to_modify).contiguous()) / self.historical_Data.shape[1]) * self.bin_Width + torch.t(torch.from_numpy(numpy_rng.uniform(size = sample_to_modify.shape))) * self.bin_Width)

            # Replace those newly sampled windstreams back into the main sample:
            sample[:, self.mask] = sample_to_modify

        return np.asarray(sample[:hours_needed, :])


def main():
    sd = WindData(Database.Database(), datetime.datetime(1979, 1, 1), datetime.datetime(2020, 12, 31), desired_averages = [None, None, None], windstreams = ["Beatrice1", "Walney1", "Burbo"])

    for i in range(1):
        forecast = sd.random_Sample(datetime.datetime(2021, 1, 1), datetime.datetime(2021, 12, 31))
        print(forecast[1])
        print(forecast[2])
        print(forecast[3])
        print(forecast[4])
        print(forecast[5])
        print(forecast[6])
        print(forecast[7])
        print(forecast[8])
        print(forecast[9])
        print(forecast[10])
        print(forecast[11])
        print(forecast[12])
        print(forecast[13])
        print(forecast[14])
        print(forecast[15])
        print(forecast[16])
        print(forecast[17])
        print(forecast[18])
        print(forecast[19])
        print(forecast[20])
        print(forecast[21])
        print(forecast[22])
        print(forecast[23])
        print(forecast[24])
        print(forecast[25])

    # for i in range(len(forecast[0])):
    #     plt.figure(figsize=(12, 8))
    #     plt.plot(pd.date_range(datetime.datetime(2023, 3, 1), datetime.datetime(2023, 7, 1) + datetime.timedelta(hours = 23), freq='H'), forecast[:, i], color = "powderblue")
    #     plt.savefig(f'/dbfs/mnt/gold/elfo/Dev/plots/HighConstellationWindStream.png')


if __name__ == '__main__':
    main()
