# Databricks notebook source
from azure.storage.blob import BlobServiceClient, BlobClient
from datetime import datetime, timedelta
from io import StringIO
!pip install netCDF4
from netCDF4 import Dataset, num2date
import io
import numpy as np
import pandas as pd
import os
import tempfile

from Constants import CONTAINER_NAME

# COMMAND ----------

import pandas as pd
import numpy as np
import os
from netCDF4 import Dataset

os.makedirs('/dbfs/mnt/dw-manual-mapping/01-cfd/Renewables Calibration/Wind/Non-CfD Calibration/', exist_ok=True)
os.makedirs('/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Non-CfD Calibration/', exist_ok=True)
# Function to process wind streams for both offshore and onshore
def process_wind_streams(wind_farm_file, output_load_factor_file, stream_type):

    # Read in wind farm locations file
    wind_farms = pd.read_csv(wind_farm_file)

    # Get a list of all files in the directory
    CONTAINER_NAME = 'dw-bronze'
    file_path = "01-cfd/Weather Data/ERA5/Wind"
    directory = f'/dbfs/mnt/{CONTAINER_NAME}/{file_path}'
    file_list = os.listdir(directory)
    file_count = len(file_list)

    # Initialize wind speed dataframe
    wind_speed = pd.DataFrame()

    # Loop through files
    for j in range(file_count):

        # Correctly construct the full path for the current file
        current_file_path = os.path.join(directory, file_list[j])

        # Open file
        with Dataset(current_file_path, 'r') as dataset:

            # Extract dimensions: longitude, latitude, and time
            longitude_values = dataset.variables['longitude'][:]
            latitude_values = dataset.variables['latitude'][:]
            time_units = dataset.variables['time'].units
            time_values = dataset.variables['time'][:]

            # Calculate timestamps
            start_time_str = time_units.split('since ')[1]
            start_time = pd.to_datetime(start_time_str)
            timestamps = [start_time + pd.Timedelta(hours=int(t)) for t in time_values]
            wind_speed_temp = pd.DataFrame({'datetime_gmt': timestamps})

            # Extract 100m high wind speeds
            U100m = dataset.variables['u100'][:]
            V100m = dataset.variables['v100'][:]

            # Extract wind speeds for all locations at once and store in a temporary dictionary
            wind_speed_columns = {}

            for k in range(len(wind_farms)):
                x = np.abs(longitude_values - wind_farms.loc[k, 'Longitude']).argmin()
                y = np.abs(latitude_values - wind_farms.loc[k, 'Latitude']).argmin()
                wind_speed_columns[wind_farms.loc[k, 'Wind_Stream']] = np.sqrt(U100m[:, y, x]**2 + V100m[:, y, x]**2)

            # Convert the dictionary to a DataFrame
            wind_speed_df = pd.DataFrame(wind_speed_columns)

            # Combine it with the timestamps DataFrame
            wind_speed_temp = pd.concat([wind_speed_temp, wind_speed_df], axis=1)

            # If it's the first file, initialize the data frame; else, append it
            if wind_speed.empty:
                wind_speed = wind_speed_temp
            else:
                wind_speed = pd.concat([wind_speed, wind_speed_temp], ignore_index=True)

    # Order by datetime and convert datetime to string
    wind_speed = wind_speed.sort_values(by='datetime_gmt')
    wind_speed['datetime_gmt'] = wind_speed['datetime_gmt'].dt.strftime('%d-%b-%Y %H:%M:%S')

    # Calculate the average wind speed weighted by installed capacity
    for i in range(1, wind_speed.shape[1]):
        wind_speed.iloc[:, i] = wind_speed.iloc[:, i] * wind_farms.iloc[i-1, 3]

    wind_speed['average_speed'] = wind_speed.iloc[:, 1:].sum(axis=1) / wind_farms.iloc[:, 3].sum()

    # Read in wind power curve
    power_curve = pd.read_csv('/dbfs/mnt/dw-manual-mapping/01-cfd/Renewables Calibration/Wind/Non-CfD Calibration/power_curve_aggregated.csv')

    # Convert wind speeds to load factors using interpolation
    load_factors = wind_speed[['datetime_gmt', 'average_speed']].copy()
    load_factors['Load Factors'] = np.interp(load_factors['average_speed'], power_curve['wind_speed'], power_curve['load_factor'])
    load_factors['Load Factors'] = np.clip(load_factors['Load Factors'], 0, 1)

    # Rename columns
    load_factor_column_name = f'{stream_type} Generic Load Factor'
    load_factors = load_factors.rename(columns={'datetime_gmt': 'Times', 'Load Factors': load_factor_column_name})[['Times', load_factor_column_name]]

    # Export final load factor stream to .csv
    load_factors.to_csv(output_load_factor_file, index=False)


# Process offshore wind streams
process_wind_streams(
    wind_farm_file="/dbfs/mnt/dw-manual-mapping/01-cfd/Renewables Calibration/Wind/Non-CfD Calibration/wind_location_offshore_capacity.csv",
    output_load_factor_file='/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Non-CfD Calibration/Offshore_generic_stream.csv',
    stream_type='Offshore'
)

# Process onshore wind streams
process_wind_streams(
    wind_farm_file="/dbfs/mnt/dw-manual-mapping/01-cfd/Renewables Calibration/Wind/Non-CfD Calibration/wind_location_onshore_capacity.csv",
    output_load_factor_file='/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Non-CfD Calibration/Onshore_generic_stream.csv',
    stream_type='Onshore'
)
