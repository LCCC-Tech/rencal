from typing import Union, Dict, Any, Optional
from pydantic import BaseModel, Field, validator
import pandas as pd
import xarray as xr
from datetime import datetime
from pathlib import Path


class Dataset(BaseModel):
    """Wrapper for weather/energy datasets with validation and format conversion"""
    
    data: pd.DataFrame = Field(..., description="Main dataset")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    data_type: str = Field(..., description="Type: 'cfd_register', 'bmu_mapping', 'generation', 'era5'")
    
    class Config:
        arbitrary_types_allowed = True
    
    @validator('data')
    def validate_data_structure(cls, v, values):
        """Validate required columns based on data type"""
        data_type = values.get('data_type')
        
        if data_type == 'cfd_register':
            required_cols = {'CFD_Id', 'Latitude', 'Longitude', 'Technology'}
            if not required_cols.issubset(set(v.columns)):
                raise ValueError(f"Missing required columns for CfD register data: {required_cols - set(v.columns)}")
                
        elif data_type == 'bmu_mapping':
            required_cols = {'CFD_Id', 'BMU_Id'}
            if not required_cols.issubset(set(v.columns)):
                raise ValueError(f"Missing required columns for BMU mapping data: {required_cols - set(v.columns)}")
                
        elif data_type == 'generation':
            required_cols = {'CFD_Id', 'settlementDate', 'quantity'}
            if not required_cols.issubset(set(v.columns)):
                raise ValueError(f"Missing required columns for generation data: {required_cols - set(v.columns)}")
                
        elif data_type == 'era5':
            # ERA5 validation can be more flexible since variables vary
            if 'time' not in v.columns and 'Times' not in v.columns:
                raise ValueError("ERA5 data must contain a time dimension ('time' or 'Times')")
                
        return v
    
    def to_xarray(self) -> xr.Dataset:
        """Convert to xarray for time series operations and n-dimensional data"""
        if self.data_type == 'generation':
            # For generation data, create time series with CFD_Id as coordinate
            df = self.data.copy()
            if 'settlementDate' in df.columns:
                df['settlementDate'] = pd.to_datetime(df['settlementDate'])
                return df.set_index(['CFD_Id', 'settlementDate']).to_xarray()
            elif 'Times' in df.columns:
                df['Times'] = pd.to_datetime(df['Times'])
                return df.set_index(['CFD_Id', 'Times']).to_xarray()
                
        elif self.data_type == 'era5':
            # For ERA5 data, preserve spatial and temporal dimensions
            df = self.data.copy()
            if 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'])
                if all(col in df.columns for col in ['latitude', 'longitude', 'time']):
                    return df.set_index(['latitude', 'longitude', 'time']).to_xarray()
                elif 'time' in df.columns:
                    return df.set_index('time').to_xarray()
                    
        # Default conversion for other data types
        return xr.Dataset.from_dataframe(self.data)
    
    def to_parquet(self, path: Union[str, Path]):
        """Save to efficient parquet format"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.data.to_parquet(path)
        
        # Save metadata separately
        metadata_path = path.with_suffix('.metadata.json')
        import json
        with open(metadata_path, 'w') as f:
            json.dump({
                'data_type': self.data_type,
                'metadata': self.metadata,
                'columns': list(self.data.columns),
                'shape': list(self.data.shape)
            }, f, indent=2, default=str)
    
    def to_zarr(self, path: Union[str, Path]):
        """Convert to zarr format for cloud storage and large datasets"""
        xr_dataset = self.to_xarray()
        xr_dataset.to_zarr(path)
    
    @classmethod
    def from_parquet(cls, path: Union[str, Path]) -> 'Dataset':
        """Load Dataset from parquet file with metadata"""
        path = Path(path)
        data = pd.read_parquet(path)
        
        # Load metadata if available
        metadata_path = path.with_suffix('.metadata.json')
        if metadata_path.exists():
            import json
            with open(metadata_path, 'r') as f:
                meta_info = json.load(f)
            data_type = meta_info.get('data_type', 'unknown')
            metadata = meta_info.get('metadata', {})
        else:
            data_type = 'unknown'
            metadata = {}
            
        return cls(data=data, data_type=data_type, metadata=metadata)
    
    @classmethod
    def from_zarr(cls, path: Union[str, Path], data_type: str) -> 'Dataset':
        """Load Dataset from zarr format"""
        xr_dataset = xr.open_zarr(path)
        data = xr_dataset.to_dataframe().reset_index()
        return cls(data=data, data_type=data_type, metadata={'source': 'zarr', 'path': str(path)})
    
    def filter_by_date_range(self, start_date: str, end_date: str, date_col: Optional[str] = None) -> 'Dataset':
        """Filter dataset by date range"""
        df = self.data.copy()
        
        # Auto-detect date column if not specified
        if date_col is None:
            date_cols = ['settlementDate', 'time', 'Times', 'date']
            date_col = next((col for col in date_cols if col in df.columns), None)
            if date_col is None:
                raise ValueError("No date column found in dataset")
        
        df[date_col] = pd.to_datetime(df[date_col])
        mask = (df[date_col] >= start_date) & (df[date_col] <= end_date)
        filtered_data = df[mask]
        
        new_metadata = self.metadata.copy()
        new_metadata['filtered_date_range'] = {'start': start_date, 'end': end_date}
        
        return Dataset(
            data=filtered_data,
            data_type=self.data_type,
            metadata=new_metadata
        )
    
    def merge_with(self, other: 'Dataset', on: Union[str, list], how: str = 'inner') -> 'Dataset':
        """Merge with another Dataset"""
        merged_data = self.data.merge(other.data, on=on, how=how)
        
        new_metadata = self.metadata.copy()
        new_metadata['merged_with'] = {
            'other_data_type': other.data_type,
            'merge_keys': on,
            'merge_type': how
        }
        
        # Determine new data type based on merge
        if self.data_type == other.data_type:
            new_data_type = self.data_type
        else:
            new_data_type = f"{self.data_type}_merged_with_{other.data_type}"
        
        return Dataset(
            data=merged_data,
            data_type=new_data_type,
            metadata=new_metadata
        )
    
    @property
    def shape(self) -> tuple:
        """Return shape of underlying data"""
        return self.data.shape
    
    @property
    def columns(self) -> list:
        """Return column names"""
        return list(self.data.columns)
    
    def __repr__(self) -> str:
        return f"Dataset(type='{self.data_type}', shape={self.shape}, columns={len(self.columns)})"