# Databricks notebook source
from azure.storage.blob import BlobServiceClient, BlobClient
from datetime import datetime, timedelta
from io import StringIO
!pip install netCDF4
from netCDF4 import Dataset, num2date
!pip install scipy
from scipy.interpolate import InterpolatedUnivariateSpline

import io
import numpy as np
import pandas as pd
import os
import tempfile

# COMMAND ----------

wind_speed = pd.read_csv("/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Yearly Load Factors/Wind Speed.csv")
wind_calibration_summary = pd.read_csv("/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Yearly Load Factors/Calibration Summary.csv")
generic_power_curve = pd.read_csv("/dbfs/mnt/dw-manual-mapping/01-cfd/Renewables Calibration/Wind/Yearly Load Factors/Generic_power_curve.csv")

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

load_factor = InterpolatedUnivariateSpline(generic_power_curve['wind_speed'], generic_power_curve['load_factor'])

# COMMAND ----------

for col in wind_speed.columns[2:]:
    wind_speed[col] = pd.to_numeric(wind_speed[col], errors='coerce')

# COMMAND ----------

# Iterate through each location (column) in wind_speed
for col in wind_speed.columns[2:]:
    i = wind_speed.columns.get_loc(col)
    if pd.isna(wind_calibration_summary['Estimated Load Factor'][i-1]) or wind_calibration_summary['Estimated Load Factor'][i-1] == -1:
        # For Non-calibrated, use the spline function
        wind_speed[col] = wind_speed[col].apply(load_factor)
        # Apply constraints
        wind_speed[col] = wind_speed[col].clip(lower=0, upper=1)
    else:
        # For Calibrated, use the 5-parameter logistic function
        a = wind_calibration_summary['a'][i-1]
        b = wind_calibration_summary['b'][i-1]
        c = wind_calibration_summary['c'][i-1]
        d = wind_calibration_summary['d'][i-1]
        g = wind_calibration_summary['g'][i-1]
        
        wind_speed[col] = d + (a - d) / (1 + (wind_speed[col] / c) ** b) ** g

# COMMAND ----------

# Sort the DataFrame by the 'Times' column
wind_speed = wind_speed.sort_values(by='Times')

# COMMAND ----------

print(wind_speed.head())

# COMMAND ----------

# Create a pivot table
wind_speed_pivot = pd.pivot_table(wind_speed, values='Wind Speed', index='Times', columns='CFD ID', aggfunc='first')

# COMMAND ----------

wind_speed_pivot.reset_index(inplace=True)

print(wind_speed_pivot.head())

wind_speed_pivot['Times'] = pd.to_datetime(wind_speed_pivot['Times'])

wind_speed_pivot['Times'] = wind_speed_pivot['Times'].dt.tz_localize(None)

# COMMAND ----------

offshore_generic_wind_streams = pd.read_csv('/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Non-CfD Calibration/Offshore_generic_stream.csv')
onshore_generic_wind_streams = pd.read_csv('/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Non-CfD Calibration/Onshore_generic_stream.csv')

combined_generic = pd.merge(offshore_generic_wind_streams, onshore_generic_wind_streams, on ='Times' )

combined_generic.reset_index(drop=True, inplace=True)
combined_generic['Times'] = pd.to_datetime(combined_generic['Times'])

# COMMAND ----------

combined_generic.head()

# COMMAND ----------

wind_speed_pivot_new = pd.merge(wind_speed_pivot, combined_generic, on='Times')

# COMMAND ----------

os.makedirs('/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Yearly Load Factors/', exist_ok=True)
wind_speed_pivot_new.to_csv(f'/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Yearly Load Factors/Wind Streams.csv', index=False)


# COMMAND ----------

os.makedirs('/dbfs/mnt/dw-silver/01-cfd/ELFO/inputs/Wind/Yearly Load Factors/', exist_ok=True)
wind_speed_pivot_new.to_parquet('/dbfs/mnt/dw-silver/01-cfd/ELFO/inputs/Wind/Yearly Load Factors/Wind Streams.parquet', index=False)
