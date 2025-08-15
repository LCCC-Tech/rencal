# Databricks notebook source
import sys
sys.path.append("/Workspace/Data/Libraries/")
from synapse_connection import fn_write_df_to_synapse_append, fn_write_df_to_synapse_truncate, fn_write_df_to_synapse_overwrite, fn_read_table_from_synapse_to_df, fn_read_query_from_synapse_to_df

# COMMAND ----------

pip install pyodbc

# COMMAND ----------

from azure.storage.blob import BlobServiceClient, BlobClient
from datetime import datetime, timedelta
from io import StringIO
!pip install seaborn
!pip install scipy
from scipy.integrate import quad
from scipy.optimize import curve_fit
!pip install netCDF4
from netCDF4 import Dataset, num2date
import io
import matplotlib.pyplot as plt
import numpy as np
import os
import pandas as pd
import pyodbc
import seaborn as sns
import tempfile
from pathlib import Path

# COMMAND ----------

def process_file(file_path, solar_farm_df, w, j):
    data_rows = []

    with Dataset(file_path, mode='r') as nc:
        longitude_values = nc.variables['longitude'][:]
        latitude_values = nc.variables['latitude'][:]
        time_units = nc.variables['time'].units
        time_values = nc.variables['time'][:]

        start_time_str = time_units.split('since ')[1]
        start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S.%f")
        timestamps = [start_time + timedelta(hours=int(t)) for t in time_values]

        t2m = nc.variables['t2m'][:]
        ssrd = nc.variables['ssrd'][:]

        for _, row in solar_farm_df.iterrows():
            lon_idx = np.argmin(np.abs(longitude_values - row['Longitude']))
            lat_idx = np.argmin(np.abs(latitude_values - row['Latitude']))

            # Extract data for closest location
            t2m_data = t2m[:, lat_idx, lon_idx]
            ssrd_data = ssrd[:, lat_idx, lon_idx]

            for time, t2m_val, ssrd_val in zip(timestamps, t2m_data, ssrd_data):
                data_rows.append({'UTC DateTime': time, 'CFD ID': row['CFD ID'], 'Temperature': t2m_val, 'Solar Radiation': ssrd_val})

    # Convert list of data rows to DataFrame
    z = pd.DataFrame(data_rows)

    # Check if this is the first file processed
    if j == 1:
        w = z
    else:
        w = pd.concat([w, z], ignore_index=True)

    return w

# def solar_regression_model(x_data, gamma, NOCT):
    # x_data[:, 0] represents 'temperature' and x_data[:, 1] represents 'solar_radiation'
 #   temperature = x_data[:, 0]  # All rows, first column
  #  solar_radiation = x_data[:, 1]  # All rows, second column
   # return (1 - gamma * ((temperature + (NOCT - 20) * solar_radiation / 800) - 25)) * solar_radiation / 1000

def solar_regression_model(x_data, gamma, noct):
    temperature, solar_radiation = x_data
    return (1 - gamma * ((temperature + (noct - 20) * solar_radiation / 800) - 25)) * solar_radiation / 1000


# COMMAND ----------

container_name = "dw-bronze"
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
solar_farm_df = cfd_master_list[cfd_master_list['Technology'].str.contains('Solar PV')]

# COMMAND ----------

results = pd.DataFrame()

# COMMAND ----------

import warnings
warnings.filterwarnings('ignore')

for i, row in solar_farm_df.iterrows():
    cfd_id = row['CFD ID']    
    query = f"""
        SELECT
            settlement_date AS 'SettlementDate',
            settlement_unit_id AS 'SettlementUnitID',
            settlement_code AS 'SettlementCode',
            cfd_id AS 'CFDID',
            metered_volume AS 'MeteredVolume',
            Transmission_Loss_Multiplier AS 'TLM',
            CONVERT(VARCHAR, CASE 
                WHEN MONTH(settlement_date) = 3 AND DAY(settlement_date) >= 25 AND DATENAME(weekday, settlement_date) = 'Sunday' AND settlement_unit_id >= 3 THEN
                    DATEADD(hour, CAST(settlement_unit_id AS numeric) - 1, CAST(settlement_date AS datetime))
                WHEN MONTH(settlement_date) = 10 AND DAY(settlement_date) >= 25 AND DATENAME(weekday, settlement_date) = 'Sunday' AND settlement_unit_id >= 3 THEN
                    DATEADD(hour, CAST(settlement_unit_id AS numeric) - 2, CAST(settlement_date AS datetime))
                ELSE
                    CONVERT(datetime, DATEADD(hour, CAST(settlement_unit_id AS numeric) - 1, CAST(settlement_date AS datetime))) AT TIME ZONE 'GMT Standard Time' AT TIME ZONE 'UTC'
            END, 120) AS 'UTCDateTime',
            metered_volume / Transmission_Loss_Multiplier AS 'GrossMeteredVolume'
        FROM 
            (SELECT
                b.settlement_date,
                b.settlement_unit_id,
                b.settlement_code,
                b.cfd_id,
                AVG(b.metered_volume) as metered_volume,
                MIN(b.Transmission_Loss_Multiplier) as Transmission_Loss_Multiplier
                    FROM
                        (SELECT *
                        FROM [slv].[T025_Generator_Settlement_Backing_Data] AS a
                        WHERE CAST(EMR_Invoice_Number AS numeric) = 
                            (SELECT MAX(CAST(EMR_Invoice_Number AS numeric))
                            FROM [slv].[T025_Generator_Settlement_Backing_Data]
                            WHERE Settlement_Date = a.Settlement_Date AND Settlement_Unit_Id = a.Settlement_Unit_Id AND CFD_Id = a.CFD_Id)) AS b
                    GROUP BY b.settlement_date, b.settlement_unit_id, b.settlement_code, b.cfd_id) AS c
                WHERE c.cfd_id = '{cfd_id}'
    """
    # Executing the SQL query
    query = fn_read_query_from_synapse_to_df(query).toPandas()
    if query['SettlementDate'].nunique() >= 365:
        results = pd.concat([results, query], ignore_index=True)

# COMMAND ----------

# Get a list of all files in the directory
file_path = "01-cfd/Weather Data/ERA5/Solar"
directory = f'/dbfs/mnt/{container_name}/{file_path}'
files = os.listdir(f'/dbfs/mnt/{container_name}/{file_path}')

# COMMAND ----------

filtered_files = [file for file in files if int(file.split('_')[2]) >= 2016]

# COMMAND ----------

w = pd.DataFrame()  # Initialize before the loop
j = 1

# Loop through the files, filter for .nc files, and append data to the list
for file in filtered_files:
        file_path = os.path.join(directory, file)
        w = process_file(file_path, solar_farm_df,w,j)
        j += 1

#w = pd.concat(r, ignore_index=True)

# COMMAND ----------

results['UTCDateTime'] = pd.to_datetime(results['UTCDateTime']).dt.tz_localize(None).dt.tz_localize('UTC')
w['UTC DateTime'] = pd.to_datetime(w['UTC DateTime']).dt.tz_localize(None).dt.tz_localize('UTC')

# COMMAND ----------

m = pd.merge(results, w, left_on=['UTCDateTime', 'CFDID'], right_on=['UTC DateTime', 'CFD ID'], how='inner')

# COMMAND ----------

solar_farm_selected = solar_farm_df[['CFD ID', 'Maximum Contract Capacity (MW)']]

# COMMAND ----------

# Perform the left join
m = pd.merge(m, solar_farm_selected, on='CFD ID', how='left')

# Calculate the 'Load Factor'
m['Load Factor'] = m['GrossMeteredVolume'].astype(float) / m['Maximum Contract Capacity (MW)']

# COMMAND ----------

# Convert Temperature from K to °C and Solar Radiation from J/m2h to W/m2
m['Temperature'] = m['Temperature'] - 273.15
m['Solar Radiation'] = m['Solar Radiation'] / 3600

# COMMAND ----------

summary = pd.DataFrame(columns=['CFD ID', 'gamma', 'NOCT','Estimated Load Factor'])
os.makedirs('/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Solar/Yearly Load Factors/Plots/', exist_ok=True)
directory = '/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Solar/Yearly Load Factors/Plots/'
plt.style.use('seaborn-v0_8')

# COMMAND ----------

#Update 10.07

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from os import path, remove

def logistic_model(x, g, n):
    return (1 - g * ((x['Temperature'] + (n - 20) * x['Solar Radiation'] / 800) - 25)) * x['Solar Radiation'] / 1000

# Assuming l and m are pandas DataFrames already loaded
# l should have a column 'CFD.ID', m should have columns 'CFD ID', 'Temperature', 'Solar Radiation', 'Load Factor'

# Initialize s DataFrame
summary = pd.DataFrame(columns=['CFD ID', 'gamma', 'NOCT', 'Estimated Load Factor'])

for index, row in solar_farm_df.iterrows():
    cfd_id = row['CFD ID']
    o = m[m['CFD ID'] == cfd_id]
    
    if o.empty:
        summary.loc[index, ['CFD ID', 'gamma', 'NOCT']] = [cfd_id, 0, 0]
    else:
        try:
            params, cov = curve_fit(logistic_model, o, o['Load Factor'], p0=[0.004, 40], bounds=([0, 0], [1, 100]), maxfev=500)
            summary.loc[index, ['CFD ID', 'gamma', 'NOCT']] = [cfd_id, params[0], params[1]]
            summary.loc[index, 'Estimated Load Factor'] = np.mean(logistic_model(o, *params))
        except Exception as e:
            summary.loc[index, ['CFD ID', 'gamma', 'NOCT']] = [cfd_id, -1, -1]

        # Plotting
        plt.figure(figsize=(12, 10))
        plt.scatter(o['Solar Radiation'], o['Load Factor'], color='#d7b71a', s=3)
        plt.xlabel("Solar Radiation")
        plt.ylabel("Load Factor")        
        plt.xlim(0, 1200)
        plt.ylim(0, 1)
        plt.title(f"Load Factor Distribution for {cfd_id}")
        plt.grid(True)
        
        # Adding model prediction lines for Tmin, Tmean, Tmax
        x_vals = np.linspace(0, 1200, 400)
        for func, color, label in zip([np.min, np.mean, np.max], ['#2d2d7b', '#ff302c', '#00de9f'], ['Tmin', 'Tmean', 'Tmax']):
            y_vals = logistic_model({'Temperature': func(o['Temperature']), 'Solar Radiation': x_vals}, summary.loc[index, 'gamma'], summary.loc[index, 'NOCT'])
            plt.plot(x_vals, y_vals, color=color, label=f'{label}={func(o["Temperature"]):.2f}')
        
        plt.legend()
        path_name = Path(directory, f"{cfd_id}.png")
        path_name.parents[0].mkdir(parents=True, exist_ok=True)                         
        plt.savefig(os.path.join(directory, f"{cfd_id}.png"))      
        plt.close()

# COMMAND ----------

summary.fillna(0.00, inplace=True)
file_name = Path('/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Solar/Yearly Load Factors/Calibration Summary.csv')
file_name.parents[0].mkdir(parents=True, exist_ok=True)
summary.to_csv(file_name, index=False)