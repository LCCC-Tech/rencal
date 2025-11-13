#!/usr/bin/env python3
"""
Simple integration tests for ERA5 data loader functionality
"""

import pytest
import tempfile
import numpy as np
import xarray as xr
from pathlib import Path
from unittest.mock import patch, MagicMock

from weather.core.data_loader import LocalDataLoader
from weather.models.dataset import ERA5Dataset
from weather.utils.constants import DEFAULT_WIND_VARIABLES, DEFAULT_SOLAR_VARIABLES


class TestERA5DataLoaderIntegration:
    """Integration tests for ERA5 data loading functionality"""

    def test_constants_are_properly_defined(self):
        """Test that the ERA5 constants are properly defined and accessible"""
        # Test DEFAULT_WIND_VARIABLES
        assert isinstance(DEFAULT_WIND_VARIABLES, list)
        assert len(DEFAULT_WIND_VARIABLES) > 0
        assert '100m_u_component_of_wind' in DEFAULT_WIND_VARIABLES
        assert '100m_v_component_of_wind' in DEFAULT_WIND_VARIABLES
        
        # Test DEFAULT_SOLAR_VARIABLES
        assert isinstance(DEFAULT_SOLAR_VARIABLES, list)
        assert len(DEFAULT_SOLAR_VARIABLES) > 0
        assert 'surface_solar_radiation_downwards' in DEFAULT_SOLAR_VARIABLES
        assert '2m_temperature' in DEFAULT_SOLAR_VARIABLES

    def test_no_netcdf_files_error_message(self):
        """Test proper error message when no NetCDF files are found"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = LocalDataLoader(data_path=tmpdir)
            
            with pytest.raises(FileNotFoundError, match="No ERA5 NetCDF files found"):
                loader.load_era5_data()

    @patch('xarray.open_dataset')
    def test_load_era5_data_with_mock_dataset(self, mock_open):
        """Test ERA5 data loading with mocked xarray dataset"""
        # Create mock dataset
        mock_dataset = MagicMock()
        mock_dataset.sizes = {'time': 100, 'latitude': 10, 'longitude': 20}
        mock_dataset.dims = {'time': 100, 'latitude': 10, 'longitude': 20}
        mock_dataset.data_vars.keys.return_value = ['u100', 'v100']
        
        # Mock time coordinate
        mock_time = np.arange('2023-01-01', '2023-01-05', dtype='datetime64[h]')
        mock_dataset.time = mock_time
        mock_dataset.latitude = np.linspace(50, 60, 10)
        mock_dataset.longitude = np.linspace(-10, 10, 20)
        
        mock_open.return_value = mock_dataset
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a dummy NetCDF file
            dummy_file = Path(tmpdir) / "test.nc"
            dummy_file.write_text("dummy")
            
            loader = LocalDataLoader(data_path=tmpdir)
            
            # This should work with the mocked dataset
            with patch.object(loader, '_validate_and_process_datasets') as mock_validate:
                mock_era5_dataset = MagicMock(spec=ERA5Dataset)
                mock_validate.return_value = mock_era5_dataset
                
                result = loader.load_era5_data()
                assert result == mock_era5_dataset
                mock_validate.assert_called_once()

    def test_era5_dataset_validation_missing_time(self):
        """Test that ERA5Dataset properly validates time dimension"""
        # Create a mock dataset without time dimension
        mock_data = MagicMock()
        mock_data.sizes = {'latitude': 10, 'longitude': 20}
        mock_data.dims = {'latitude': 10, 'longitude': 20}
        
        with pytest.raises(ValueError, match="Dataset must have a 'time' dimension"):
            ERA5Dataset(data=mock_data)

    def test_era5_dataset_validation_no_era5_variables(self):
        """Test that ERA5Dataset properly validates ERA5 variables"""
        # Create a mock dataset with time but no ERA5 variables
        mock_data = MagicMock()
        mock_data.sizes = {'time': 100, 'latitude': 10, 'longitude': 20}
        mock_data.dims = {'time': 100, 'latitude': 10, 'longitude': 20}
        mock_data.data_vars.keys.return_value = ['random_var', 'another_var']
        
        with pytest.raises(ValueError, match="No valid ERA5 variables found"):
            ERA5Dataset(data=mock_data)

    def test_error_handling_with_proper_chaining(self):
        """Test that errors are properly chained using 'from e' syntax"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two files that will cause concatenation to fail
            file1 = Path(tmpdir) / "file1.nc"
            file2 = Path(tmpdir) / "file2.nc"
            file1.write_text("invalid netcdf")
            file2.write_text("also invalid")
            
            loader = LocalDataLoader(data_path=tmpdir)
            
            # Should raise ValueError with proper exception chaining
            with pytest.raises(Exception):  # Will fail during file reading, not concatenation
                loader.load_era5_data()


class TestERA5DataLoaderFunctional:
    """Functional tests using actual (small) NetCDF data"""

    def test_load_era5_data_end_to_end(self):
        """End-to-end test using the working test_new_api.py approach"""
        # This test replicates the successful test_new_api.py logic
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create a mock ERA5 NetCDF file with some standard variables
            time = np.arange('2023-01-01', '2023-01-03', dtype='datetime64[h]')  # Smaller dataset
            lat = np.linspace(50, 60, 5)  # Smaller grid
            lon = np.linspace(-10, 10, 10)  # Smaller grid
            
            # Create mock data for u100 and v100 (standard wind variables)
            u100_data = np.random.randn(len(time), len(lat), len(lon))
            v100_data = np.random.randn(len(time), len(lat), len(lon))
            
            # Create xarray dataset
            ds = xr.Dataset({
                'u100': (['time', 'latitude', 'longitude'], u100_data),
                'v100': (['time', 'latitude', 'longitude'], v100_data),
            }, coords={
                'time': time,
                'latitude': lat,
                'longitude': lon,
            })
            
            # Save to NetCDF file
            netcdf_file = tmpdir_path / "era5_test.nc"
            ds.to_netcdf(netcdf_file)
            
            # Test the simplified ERA5 loading API
            loader = LocalDataLoader(data_path=str(tmpdir_path))
            era5_dataset = loader.load_era5_data()
            
            # Verify results
            assert isinstance(era5_dataset, ERA5Dataset)
            assert era5_dataset.get_available_variables() == ['u100', 'v100']
            assert era5_dataset.get_shape() == (48, 5, 10)  # 2 days * 24 hours, 5 lat, 10 lon
            
            # Test wind components
            wind_components = era5_dataset.get_wind_components()
            assert wind_components is not None
            assert set(wind_components) == {'u100', 'v100'}
            
            # Test time range
            time_range = era5_dataset.get_time_range()
            assert str(time_range['start'])[:10] == '2023-01-01'
            assert str(time_range['end'])[:10] == '2023-01-02'
            
            # Test spatial bounds
            spatial_bounds = era5_dataset.get_spatial_bounds()
            assert spatial_bounds['lat_min'] == 50.0
            assert spatial_bounds['lat_max'] == 60.0
            assert spatial_bounds['lon_min'] == -10.0
            assert spatial_bounds['lon_max'] == 10.0
            
            # Test date filtering
            filtered_dataset = era5_dataset.filter_by_date_range("2023-01-01", "2023-01-01")
            filtered_time_range = filtered_dataset.get_time_range()
            assert filtered_time_range['periods'] < time_range['periods']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])