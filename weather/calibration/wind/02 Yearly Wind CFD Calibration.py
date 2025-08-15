# Databricks notebook source
import sys
sys.path.append("/Workspace/Data/Libraries/")
from synapse_connection import fn_write_df_to_synapse_append, fn_write_df_to_synapse_truncate, fn_write_df_to_synapse_overwrite, fn_read_table_from_synapse_to_df, fn_read_query_from_synapse_to_df
from Constants import ERA5_START_YEAR, DAYS_IN_YEAR, CONTAINER_NAME

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
from scipy.integrate import quad
from scipy.optimize import curve_fit
!pip install scikit-learn
from sklearn.metrics import mean_squared_error, r2_score

# COMMAND ----------

def process_file(file_path, wind_farm_df, w, j):
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
                data_rows.append({'UTC DateTime': time, 'CFD ID': row['CFD ID'], 'Wind Speed': wind_speed_val})

    # Convert list of data rows to DataFrame
    z = pd.DataFrame(data_rows)

    # Check if this is the first file processed
    if j == 1:
        w = z
    else:
        w = pd.concat([w, z], ignore_index=True)

    return w

# COMMAND ----------

container_name = CONTAINER_NAME
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

results = pd.DataFrame()

# COMMAND ----------

import warnings
warnings.filterwarnings('ignore')

for i, row in wind_farm_df.iterrows():
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
    if query['SettlementDate'].nunique() >= DAYS_IN_YEAR:
        results = pd.concat([results, query], ignore_index=True)

# COMMAND ----------

# Get a list of all files in the directory
file_path = "01-cfd/Weather Data/ERA5/Wind"
directory = f'/dbfs/mnt/{CONTAINER_NAME}/{file_path}'
files = os.listdir(f'/dbfs/mnt/{CONTAINER_NAME}/{file_path}')

# COMMAND ----------

filtered_files = [file for file in files if int(file.split('_')[2]) >= ERA5_START_YEAR]

# COMMAND ----------

w = pd.DataFrame()  # Initialize before the loop
j = 1
# Loop through the files, filter for .nc files, and append data to the list
for file in filtered_files:
        file_path = os.path.join(directory, file)
        w = process_file(file_path, wind_farm_df,w,j)
        j += 1

# COMMAND ----------

w.columns.values[1] = 'CFD ID'
w.columns.values[2] = 'Wind Speed'
results['UTCDateTime'] = pd.to_datetime(results['UTCDateTime']).dt.tz_localize(None).dt.tz_localize('UTC')
w['UTC DateTime'] = pd.to_datetime(w['UTC DateTime']).dt.tz_localize(None).dt.tz_localize('UTC')

# COMMAND ----------

m = pd.merge(results, w, left_on=['UTCDateTime', 'CFDID'], right_on=['UTC DateTime', 'CFD ID'], how='inner')

# COMMAND ----------

wind_farm_selected = wind_farm_df[['CFD ID', 'Maximum Contract Capacity (MW)']]

# COMMAND ----------

# Perform the left join
m = pd.merge(m, wind_farm_selected, on='CFD ID', how='left')

# COMMAND ----------

# Calculate the 'Load Factor'
m['Load Factor'] = m['GrossMeteredVolume'].astype(float) / m['Maximum Contract Capacity (MW)']

# COMMAND ----------

weibull = pd.read_csv("/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Yearly Load Factors/Weibull Parameters.csv")
generic_power_curve = pd.read_csv('/dbfs/mnt/dw-manual-mapping/01-cfd/Renewables Calibration/Wind/Non-CfD Calibration/power_curve_aggregated.csv')

# COMMAND ----------

summary = pd.DataFrame(columns=['CFD ID', 'a', 'b', 'c', 'd', 'g', 'Estimated Load Factor'])
directory = '/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Yearly Load Factors/Plots/'
plt.style.use('seaborn-v0_8')

# COMMAND ----------

# Iterate over DataFrame
for index, row in wind_farm_df.iterrows():
    cfd_id = row['CFD ID']
    o = m[m['CFD ID'] == cfd_id]
    params_weibull = weibull[weibull['CFD ID'] == cfd_id]

    if o.empty or params_weibull.empty:
        new_row = pd.DataFrame({'CFD ID': [cfd_id], 'a': [0], 'b': [0], 'c': [0], 'd': [0], 'g': [0], 'Estimated Load Factor': [0]})
        summary = pd.concat([summary, new_row], ignore_index=True)

    else:
        lambda_val = params_weibull['Lambda'].iloc[0]
        k_val = params_weibull['k'].iloc[0]
        estimated_load_factor = None

        try:
            def logistic_function(x, b, c, g):
                a = 0
                d = 1
                return d + (a - d) / ((1 + (x / c)**b)**g)

            # Fit model
            params, _ = curve_fit(logistic_function, o['Wind Speed'], o['Load Factor'],
                                    p0=[4.5, 9, 1], bounds=([0, 0, 0], [500, 500, 500]))

            # Calculate the long-term load factor
            estimated_load_factor = quad(
                lambda x: logistic_function(x, *params) * (k_val / lambda_val * (x / lambda_val)**(k_val - 1) * np.exp(-((x / lambda_val)**k_val))),
                0, np.inf
            )[0]


            plt.figure(figsize=(12, 10))
            plt.scatter(o['Wind Speed'], o['Load Factor'], color="#3434ba", s=3)
            plt.plot(np.linspace(0, 25, 100), logistic_function(np.linspace(0, 25, 100), *params), color="#d2d902",linewidth=3, label = f"{cfd_id} - Power Curve")
            plt.plot(generic_power_curve['wind_speed'], generic_power_curve['load_factor'], color='red', linewidth=2, label="Generic Power Curve")
            plt.title(f"Load Factor Distribution for {cfd_id}")
            plt.xlabel("Wind Speed")
            plt.ylabel("Load Factor")
            plt.xlim(0, 25)
            plt.ylim(0, 1)
            plt.grid(True)
            plt.legend()
            path_name = Path(directory, f"{cfd_id}.png")
            path_name.parents[0].mkdir(parents=True, exist_ok=True)
            plt.savefig(os.path.join(directory, f"{cfd_id}.png"))
            plt.close()

            new_row = pd.DataFrame({
                'CFD ID': [cfd_id],
                'a': [0],
                'b': [0 if params is None else params[0]],
                'c': [0 if params is None else params[1]],
                'd': [1],
                'g': [0 if params is None else params[2]],
                'Estimated Load Factor': [estimated_load_factor]
        })
            summary = pd.concat([summary, new_row], ignore_index=True)

        except Exception as ex:
            print(f"Regression failed for {cfd_id} with error: {ex}")
            new_row = pd.DataFrame({'CFD ID': [cfd_id], 'a': [-1], 'b': [-1], 'c': [-1], 'd': [-1], 'g': [-1], 'Estimated Load Factor': [-1]})
            summary = pd.concat([summary, new_row], ignore_index=True)

    # Replace 'Estimate Load Factor' with NA if the value is 0
summary['Estimated Load Factor'] = summary['Estimated Load Factor'].replace(0, 'NA')

# COMMAND ----------

os.makedirs('/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Yearly Load Factors/', exist_ok=True)
summary.to_csv(f'/dbfs/mnt/dw-silver/01-cfd/Renewables Calibration/Wind/Yearly Load Factors/Calibration Summary.csv', index=False)