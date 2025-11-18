import os
from abc import ABC, abstractmethod
from typing import List, Optional, Union, Dict, Any
from pathlib import Path
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone

from .dataset import Dataset


class DataLoader(ABC):
    """Abstract base class for loading different data sources"""
    
    @property
    @abstractmethod
    def base_path(self) -> str:
        pass

    @abstractmethod
    def load_cfd_register(self) -> Dataset:
        """Load CfD register with location/capacity data"""
        pass
    
    @abstractmethod 
    def load_bmu_mapping(self) -> Dataset:
        """Load CfD to BMU mapping"""
        pass
    
    @abstractmethod
    def load_generation_data(self, 
                           cfd_ids: Optional[List[str]] = None,
                           date_range: Optional[tuple] = None) -> Dataset:
        """Load settlement/generation time series"""
        pass
    
    @abstractmethod
    def load_era5_data(self, 
                      variables: List[str],
                      date_range: tuple,
                      location_bounds: Optional[Dict[str, float]] = None) -> Dataset:
        """Load ERA5 weather data"""
        pass


class LocalDataLoader(DataLoader):
    def __init__(self, data_path: Union[str, Path] = "./data"):
        self._base_path = Path(data_path)

    @property
    def base_path(self) -> str:
        return str(self._base_path)

    @base_path.setter
    def base_path(self, path: str):
        self._base_path = Path(path)

    def load_cfd_register(self) -> Dataset:
        """Load CfD register with location/capacity data from Excel file"""
        file_path = self._base_path / "CfD_Register.xlsx"
        if not file_path.exists():
            raise FileNotFoundError(f"CfD Register file not found at {file_path}")
        
        df = pd.read_excel(file_path)
        
        # Apply filtering logic from notebook - only wind technologies
        df_filtered = df[df["technology_type"].isin(["Onshore Wind", "Offshore Wind"])]
        
        # Standardize column names
        df_filtered = df_filtered.rename(columns={
            "contract_id": "CFD_Id", 
            "latitude": "Latitude",
            "longitude": "Longitude", 
            "technology_type": "Technology",
            "current_installed_capacity": "Maximum Capacity"
        })
        
        # Select relevant columns
        result_df = df_filtered[["CFD_Id", "Latitude", "Longitude", "Technology", "Maximum Capacity"]].copy()
        
        return Dataset(
            data=result_df,
            data_type="cfd_register",
            metadata={
                "source": "local_excel",
                "file_path": str(file_path),
                "filtered": True,
                "filter_criteria": "Onshore Wind, Offshore Wind only",
                "original_rows": len(df),
                "filtered_rows": len(result_df)
            }
        )
    
    def load_bmu_mapping(self) -> Dataset:
        """Load CfD to BMU mapping from CSV URL or local file"""
        local_file = self._base_path / "cfd_to_bm_unit_mapping.csv"
        
        if local_file.exists():
            df = pd.read_csv(local_file)
            source_info = {"source": "local_csv", "file_path": str(local_file)}
        else:
            # Fallback to URL from notebook
            url = "https://dp.lowcarboncontracts.uk/dataset/be8c542a-c66c-4a06-a3df-bc46db7416c0/resource/9316f493-365c-4abc-a40e-3a5e67119a0a/download/cfd_to_bm_unit_mapping.csv"
            df = pd.read_csv(url)
            source_info = {"source": "remote_csv", "url": url}
        
        # Select relevant columns
        result_df = df[["CFD_Id", "BMU_Id"]].copy()
        
        return Dataset(
            data=result_df,
            data_type="bmu_mapping",
            metadata=source_info
        )
    
    def load_generation_data(self, 
                           cfd_ids: Optional[List[str]] = None,
                           date_range: Optional[tuple] = None) -> Dataset:
        """Load generation data from BMRS API"""
        if cfd_ids is None:
            # Load all available CfD IDs from register and mapping
            cfd_register = self.load_cfd_register()
            bmu_mapping = self.load_bmu_mapping()
            merged = cfd_register.merge_with(bmu_mapping, on="CFD_Id", how="inner")
            bmu_ids = merged.data["BMU_Id"].unique().tolist()
        else:
            # Get BMU IDs for specified CfD IDs
            bmu_mapping = self.load_bmu_mapping()
            bmu_ids = bmu_mapping.data[bmu_mapping.data["CFD_Id"].isin(cfd_ids)]["BMU_Id"].tolist()
        
        if not bmu_ids:
            raise ValueError("No BMU IDs found for the specified CfD IDs")
        
        # Set date range
        if date_range is None:
            start_utc = "2023-01-01T00:00:00Z"
            end_utc = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            start_utc = date_range[0]
            end_utc = date_range[1]
        
        # Fetch data from BMRS API
        url = "https://data.elexon.co.uk/bmrs/api/v1/datasets/B1610/stream"
        params = {
            "from": start_utc,
            "to": end_utc,
            "bmUnit": bmu_ids,
            "format": "json"
        }
        
        response = requests.get(url, params=params, timeout=60, verify=False)
        response.raise_for_status()
        payload = response.json()
        
        # Parse response
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        df = pd.DataFrame(rows)
        
        if df.empty:
            raise ValueError("No generation data returned from BMRS API")
        
        # Clean and standardize data
        df["settlementDate"] = pd.to_datetime(df["settlementDate"]).dt.date
        df["settlementPeriod"] = pd.to_numeric(df["settlementPeriod"], errors="coerce")
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
        df.rename(columns={"bmUnit": "BMU_Id"}, inplace=True)
        
        # Merge with CfD mapping to add CFD_Id
        bmu_mapping = self.load_bmu_mapping()
        df_with_cfd = df.merge(bmu_mapping.data[["BMU_Id", "CFD_Id"]], on="BMU_Id", how="left")
        
        # Aggregate by CFD_Id if multiple BMUs per CfD
        df_aggregated = (
            df_with_cfd.groupby(["CFD_Id", "settlementDate", "settlementPeriod"], as_index=False)["quantity"]
            .sum()
            .round(2)
        )
        
        return Dataset(
            data=df_aggregated,
            data_type="generation",
            metadata={
                "source": "bmrs_api",
                "date_range": {"start": start_utc, "end": end_utc},
                "bmu_count": len(bmu_ids),
                "api_url": url,
                "aggregated": True
            }
        )
    
    def load_era5_data(self, 
                      variables: List[str],
                      date_range: tuple,
                      location_bounds: Optional[Dict[str, float]] = None) -> Dataset:
        """Load ERA5 weather data from NetCDF files"""
        # This is a stub implementation - users need to implement based on their ERA5 data structure
        # Expected variables: ['u100', 'v100'] for wind, ['ssrd', 't2m'] for solar
        
        era5_files = list(self._base_path.glob("*.nc"))
        if not era5_files:
            raise FileNotFoundError(f"No ERA5 NetCDF files found in {self._base_path}")
        
        # Placeholder implementation - would need xarray to properly load NetCDF
        # For now, return a minimal structure
        df = pd.DataFrame({
            'time': pd.date_range(date_range[0], date_range[1], freq='h'),
            'latitude': [55.0] * pd.date_range(date_range[0], date_range[1], freq='h').shape[0],
            'longitude': [-4.0] * pd.date_range(date_range[0], date_range[1], freq='h').shape[0],
        })
        
        # Add requested variables with placeholder data
        for var in variables:
            df[var] = 0.0  # Placeholder - real implementation would load from NetCDF
        
        return Dataset(
            data=df,
            data_type="era5",
            metadata={
                "source": "local_netcdf",
                "data_path": str(self._base_path),
                "variables": variables,
                "date_range": date_range,
                "location_bounds": location_bounds,
                "files_found": len(era5_files),
                "note": "Stub implementation - implement NetCDF loading with xarray"
            }
        )
