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

def weibull(x, k, lamb):
    return (k / lamb) * (x / lamb)**(k-1) * np.exp(-(x / lamb)**k)

# COMMAND ----------

CONTAINER_NAME = "dw-bronze"
file_path = "01-cfd"
directory = f'/dbfs/mnt/{CONTAINER_NAME}/{file_path}'

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

import pandas as pd
!pip install scipy
from scipy.stats import weibull_min
from scipy.optimize import curve_fit

# COMMAND ----------

# Create a DataFrame to hold the results
weibull_parameters_df = pd.DataFrame(columns=['CFD ID', 'Mean', 'Std Dev', 'Lambda', 'k'])

# COMMAND ----------

for cfd_id in final_results['CFD ID'].unique():
    subset = final_results[final_results['CFD ID'] == cfd_id]['Wind Speed']

    # Calculate mean and standard deviation
    mean_val = subset.mean()
    std_dev = subset.std()

    # Fit Weibull distribution
    params, _ = curve_fit(weibull, subset, weibull_min.pdf(subset, *weibull_min.fit(subset, floc=0)), p0=[1, 2])
    k, lamb = params[0], params[1]

    # Prepare new data for DataFrame
    new_data = pd.DataFrame({'CFD ID': [cfd_id], 'Mean Wind Speed': [mean_val], 'Wind Speed Standard Deviation': [std_dev], 'Lambda': [lamb], 'k': [k]})

    # Append the results to the DataFrame
    weibull_parameters_df = pd.concat([weibull_parameters_df, new_data], ignore_index=True)

# COMMAND ----------

os.makedirs('/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Yearly Load Factors/', exist_ok=True)
weibull_parameters_df.to_csv(f'/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Yearly Load Factors/Weibull Parameters.csv', index=False)