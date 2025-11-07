from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

import pandas as pd

from weather.utils.constants import DOWNLOAD_DATA_DIR, PLANT_DATA_FILE_NAME, WIND_TECHNOLOGY_TYPES
from weather.utils.logger import get_logger

from .dataset import BaseDataset, PandasDataset, XarrayDataset

logger = get_logger(__name__)


class DataLoader(ABC):
    """Abstract base class for loading different data sources"""

    @abstractmethod
    def load_wind_plant_data(self) -> BaseDataset:
        """Load CfD register with location/capacity data"""
        pass

    @abstractmethod
    def load_generation_data(
        self, cfd_ids: list[str], start_date: datetime, end_date: datetime
    ) -> BaseDataset:
        """Load settlement/generation time series"""
        pass

    @abstractmethod
    def load_era5_data(
        self,
        variables: list[str],
        start_date: datetime,
        end_date: datetime,
    ) -> BaseDataset:
        """Load ERA5 weather data"""
        pass


class LocalDataLoader(DataLoader):
    def __init__(self, data_path: str = DOWNLOAD_DATA_DIR):
        self._base_path = Path(data_path)

    def load_wind_plant_data(self, id_column: str = "CFD_Id") -> BaseDataset:
        """Load CfD register with location/capacity data from Excel file"""
        file_path = self._base_path / "plant" / PLANT_DATA_FILE_NAME
        if not file_path.exists():
            raise FileNotFoundError(f"CfD plant data file not found at {file_path}")

        df = pd.read_csv(file_path)

        # Filter for wind technologies
        mask = df["technology"].isin(WIND_TECHNOLOGY_TYPES)
        wind_df = df.loc[mask].copy()

        wind_df = wind_df.rename(columns={id_column: "plant_id"})

        print(wind_df.columns)
        print(wind_df.head())

        return PandasDataset(
            data=wind_df,
            data_type="plant_data",
            metadata={
                "source": "local_excel",
                "file_path": str(file_path),
                "filtered": True,
                "filter_criteria": "Onshore Wind, Offshore Wind only",
            },
        )

    def load_generation_data(
        self, cfd_ids: list[str], start_date: datetime, end_date: datetime
    ) -> BaseDataset:
        """Load generation data from BMRS API"""
        df["settlementDate"] = pd.to_datetime(df["settlementDate"]).dt.date
        df["settlementPeriod"] = pd.to_numeric(df["settlementPeriod"], errors="coerce")
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
        df.rename(columns={"bmUnit": "BMU_Id"}, inplace=True)

        # Merge with CfD mapping to add CFD_Id
        bmu_mapping = self.load_bmu_mapping()
        df_with_cfd = df.merge(bmu_mapping.data[["BMU_Id", "CFD_Id"]], on="BMU_Id", how="left")

        # Aggregate by CFD_Id if multiple BMUs per CfD
        df_aggregated = (
            df_with_cfd.groupby(["CFD_Id", "settlementDate", "settlementPeriod"], as_index=False)[
                "quantity"
            ]
            .sum()
            .round(2)
        )

        return PandasDataset(
            data=df_aggregated,
            data_type="generation",
            metadata={
                "source": "bmrs_api",
                "date_range": {"start": start_date, "end": end_date},
                "aggregated": True,
            },
        )

    def load_era5_data(
        self,
        variables: list[str],
        start_date: datetime,
        end_date: datetime,
    ) -> XarrayDataset:
        """Load ERA5 weather data from NetCDF files"""
        # This is a stub implementation - users need to implement based on their ERA5 data structure
        # Expected variables: ['u100', 'v100'] for wind, ['ssrd', 't2m'] for solar

        era5_files = list(self._base_path.glob("*.nc"))
        if not era5_files:
            raise FileNotFoundError(f"No ERA5 NetCDF files found in {self._base_path}")

        # Placeholder implementation - would need xarray to properly load NetCDF
        # For now, return a minimal structure
        df = pd.DataFrame(
            {
                "time": pd.date_range(start_date, end_date, freq="h"),
                "latitude": [55.0] * pd.date_range(start_date, end_date, freq="h").shape[0],
                "longitude": [-4.0]
                * pd.date_range(start_date, end_date, freq="h").shape[0],
            }
        )

        # Add requested variables with placeholder data
        for var in variables:
            df[var] = 0.0  # Placeholder - real implementation would load from NetCDF

        return XarrayDataset(
            data=df,
            data_type="era5",
            metadata={
                "source": "local_netcdf",
                "data_path": str(self._base_path),
                "variables": variables,
                "files_found": len(era5_files),
                "note": "Stub implementation - implement NetCDF loading with xarray",
            },
        )
