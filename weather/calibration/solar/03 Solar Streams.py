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

container_name = "dw-silver"
file_path = "Renewables Calibration"
directory = f'/dbfs/mnt/{container_name}/{file_path}'

# COMMAND ----------

solar_temperature_radiation = pd.read_csv("/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Solar/Yearly Load Factors/Solar Temperatures and Radiation.csv")
solar_calibration_summary = pd.read_csv("/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Solar/Yearly Load Factors/Calibration Summary.csv")

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
solar_farm_df = cfd_master_list[cfd_master_list['Technology'].str.contains('Solar PV')]

# COMMAND ----------

# Set default parameters for non-calibrated solar farms
ncpar = [0.0034, 45]

# COMMAND ----------

# Add a new column for load factors
solar_temperature_radiation['Load Factor'] = np.nan

# COMMAND ----------

for index, row in solar_farm_df.iterrows():
    cfd_id = row['CFD ID']
    
    # Find the corresponding row in power_curve_parameters based on CFD ID
    param_row = solar_calibration_summary[solar_calibration_summary['CFD ID'] == cfd_id]
    
    if param_row.empty or param_row['Estimated Load Factor'].iloc[0] == -1:
        gamma = ncpar[0]
        noct = ncpar[1]
    else:
        gamma = param_row['gamma'].iloc[0]
        noct = param_row['NOCT'].iloc[0]
    
    mask = solar_temperature_radiation['CFD ID'] == cfd_id
    temp_adjust = (noct - 20) * solar_temperature_radiation.loc[mask, 'Solar Radiation'] / 800
    solar_temperature_radiation.loc[mask, 'Load Factor'] = (1 - gamma * ((solar_temperature_radiation.loc[mask, 'Temperature'] + temp_adjust) - 25)) * solar_temperature_radiation.loc[mask, 'Solar Radiation'] / 1000

# COMMAND ----------

# Sort the DataFrame by the 'Times' column
solar_temperature_radiation = solar_temperature_radiation.sort_values(by='Times')

# COMMAND ----------

# Create a pivot table
import pandas as pd
solar_temperature_radiation_pivot = pd.pivot_table(solar_temperature_radiation, values='Load Factor', index='Times', columns='CFD ID', aggfunc='first')

# COMMAND ----------

# Adding generic stream
solar_temperature_radiation_pivot['Solar_Generic_Stream'] = solar_temperature_radiation_pivot.mean(axis=1)

# COMMAND ----------

# Write to local disk
solar_temperature_radiation_pivot.to_csv('/tmp/solar_streams.csv', index=False)

os.makedirs('/dbfs/mnt/dw-silver/01-cfd/ELFO/inputs/Solar/Yearly Load Factors/', exist_ok=True)
# Then move to mounted blob storage
dbutils.fs.cp('file:/tmp/solar_streams.csv', '/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Solar/Yearly Load Factors/Solar Streams.csv')

# COMMAND ----------

# Write to local disk
solar_temperature_radiation_pivot.to_parquet('/tmp/solar_streams_rad.parquet', index=False)

os.makedirs('/dbfs/mnt/dw-silver/01-cfd/ELFO/inputs/Solar/Yearly Load Factors/', exist_ok=True)
# Then move to mounted blob storage
dbutils.fs.cp('file:/tmp/solar_streams_rad.parquet', '/dbfs/mnt/dw-silver/01-cfd/ELFO/inputs/Solar/Yearly Load Factors/Solar Streams.parquet')
