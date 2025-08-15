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

def process_file(file_path, wind_farm_df):
    data_rows = []

    with Dataset(file_path, mode='r') as nc:
        longitude_values = nc.variables['longitude'][:]
        latitude_values = nc.variables['latitude'][:]
        time_units = nc.variables['time'].units
        time_values = nc.variables['time'][:]

        start_time_str = time_units.split('since ')[1]
        start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S.%f")
        timestamps = [start_time + timedelta(hours=int(t)) for t in time_values]

        U100m = nc.variables['u100'][:]
        V100m = nc.variables['v100'][:]

        for _, row in wind_farm_df.iterrows():
            lon_idx = np.argmin(np.abs(longitude_values - row['Longitude']))
            lat_idx = np.argmin(np.abs(latitude_values - row['Latitude']))

            # Calculate wind speed
            wind_speed_data = np.sqrt(U100m[:, lat_idx, lon_idx]**2 + V100m[:, lat_idx, lon_idx]**2)

            for time, wind_speed_val in zip(timestamps, wind_speed_data):
                data_rows.append({'Times': time, 'CFD ID': row['CFD ID'], 'Wind Speed': wind_speed_val})

    # Convert list of data rows to DataFrame
    return pd.DataFrame(data_rows)

# COMMAND ----------

container_name = CONTAINER_NAME
file_path = "01-cfd"
directory = f'/dbfs/mnt/{container_name}/{file_path}'

# COMMAND ----------

cfd_master_list = pd.read_csv("/dbfs/mnt/dw-silver/01-cfd/master_data/CfD_Master_Data.csv")
cfd_master_list = cfd_master_list.rename(columns={
    "CFD_Id": "CFD ID",
    "Name": "Name",
    "Maximum_Contract_Capacity_MW": "Maximum Contract Capacity (MW)",
    "Start_Date_Live_Generators": "Start Date - Live Generators",
    "Start_Date_High_Case": "Start Date - High Case",
    "Start_Date_Best_Estimate": "Start Date - Best Estimate",
    "Start_Date_Low_Case": "Start Date - Low Case",
    "Expected_Start_Date": "Expected Start Date",
    "Allocation_Round": "Allocation Round",
    "Latitude": "Latitude",
    "Longitude": "Longitude",
    "Strike_Price_2012_£_MWh": "Strike Price (2012 £/MWh)",
    "Strike_Price_Current_£_MWh": "Strike Price (Current £/MWh)",
    "Technology": "Technology",
    "Region": "Region",
    "GSP_Group": "GSP Group",
    "MDD": "MDD",
    "TCD": "TCD",
    "TCW_start_date": "TCW start date",
    "TCW_end_date": "TCW end date",
    "Longstop_Date": "Longstop Date",
    "Contract_End_Date": "Contract End Date",
    "ICE_MW": "ICE (MW)",
    "Termination_Date": "Termination Date",
    "Reference_Price_Type": "Reference Price Type",
    "Negative_Pricing_Provision": "Negative Pricing Provision",
    "Network_Type": "Network Type",
    "BMU_Id": "BMU Id"
})

wind_farm_df = cfd_master_list[cfd_master_list['Technology'].str.contains('Wind')]


# COMMAND ----------


# Get a list of all files in the directory
file_path = "01-cfd/Weather Data/ERA5/Wind"
directory = f'/dbfs/mnt/{CONTAINER_NAME}/{file_path}'
files = os.listdir(f'/dbfs/mnt/{CONTAINER_NAME}/{file_path}')

# COMMAND ----------

results = []

# Loop through the files, filter for .nc files, and append data to the list
for file in files:
    if file.endswith('.nc'):
        file_path = os.path.join(directory, file)
        data = process_file(file_path, wind_farm_df)
        results.append(data)

final_results = pd.concat(results, ignore_index=True)

# COMMAND ----------

# Convert datetime to the specified format
final_results['Times'] = pd.to_datetime(final_results['Times']).dt.tz_localize('UTC').dt.tz_convert('GMT')

# COMMAND ----------

os.makedirs(f'/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Yearly Load Factors/', exist_ok=True)
final_results.to_csv(f'/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Yearly Load Factors/Wind Speed.csv', index=False)
