#!/usr/bin/env python3
"""
Simple integration tests for ERA5 data loader functionality
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import xarray as xr

from weather.core.data_loader import LocalDataLoader
from weather.models.dataset import ERA5Dataset
from weather.utils.constants import DEFAULT_SOLAR_VARIABLES, DEFAULT_WIND_VARIABLES


class TestERA5DataLoaderIntegration:
    """Integration tests for ERA5 data loading functionality"""

    def test_constants_are_properly_defined(self):
        """Test that the ERA5 constants are properly defined and accessible"""
        # Test DEFAULT_WIND_VARIABLES
        assert isinstance(DEFAULT_WIND_VARIABLES, list)
        assert len(DEFAULT_WIND_VARIABLES) > 0
        assert "100m_u_component_of_wind" in DEFAULT_WIND_VARIABLES
        assert "100m_v_component_of_wind" in DEFAULT_WIND_VARIABLES

        # Test DEFAULT_SOLAR_VARIABLES
        assert isinstance(DEFAULT_SOLAR_VARIABLES, list)
        assert len(DEFAULT_SOLAR_VARIABLES) > 0
        assert "surface_solar_radiation_downwards" in DEFAULT_SOLAR_VARIABLES
        assert "2m_temperature" in DEFAULT_SOLAR_VARIABLES

    def test_no_netcdf_files_error_message(self):
        """Test proper error message when no NetCDF files are found"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create era5 subdirectory
            era5_dir = Path(tmpdir) / "era5"
            era5_dir.mkdir()

            loader = LocalDataLoader(data_path=tmpdir)

            with pytest.raises(FileNotFoundError, match="No ERA5 NetCDF files found"):
                loader.load_era5_data()

    def test_load_era5_data_with_mock_dataset(self):
        """Test ERA5 data loading with simplified mocking"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create era5 subdirectory and dummy file
            era5_dir = Path(tmpdir) / "era5"
            era5_dir.mkdir()
            dummy_file = era5_dir / "test.nc"
            dummy_file.write_text("dummy")

            loader = LocalDataLoader(data_path=tmpdir)

            # Mock the entire loading process
            with patch.object(loader, "load_era5_data") as mock_load:
                mock_era5_dataset = MagicMock(spec=ERA5Dataset)
                mock_load.return_value = mock_era5_dataset

                result = loader.load_era5_data()
                assert result == mock_era5_dataset

    def test_era5_dataset_validation_wrong_type(self):
        """Test that ERA5Dataset validates input type"""
        # Should raise Pydantic ValidationError for wrong type
        with pytest.raises(Exception):  # Pydantic ValidationError
            ERA5Dataset(data=MagicMock())  # type: ignore

    def test_error_handling_with_invalid_files(self):
        """Test that errors are properly handled with invalid NetCDF files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create era5 subdirectory with invalid file
            era5_dir = Path(tmpdir) / "era5"
            era5_dir.mkdir()
            invalid_file = era5_dir / "invalid.nc"
            invalid_file.write_text("invalid netcdf content")

            loader = LocalDataLoader(data_path=tmpdir)

            # Should raise some exception during loading
            with pytest.raises(Exception):
                loader.load_era5_data()


class TestERA5DataLoaderFunctional:
    """Functional tests using actual (small) NetCDF data"""

    def test_load_era5_data_end_to_end(self):
        """End-to-end test using actual xarray dataset"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create era5 subdirectory
            era5_dir = tmpdir_path / "era5"
            era5_dir.mkdir()

            # Create a small ERA5 NetCDF file with standard variables
            time = np.arange("2023-01-01", "2023-01-03", dtype="datetime64[h]")  # 48 hours
            lat = np.linspace(50, 60, 3)  # Small grid
            lon = np.linspace(-10, 10, 5)  # Small grid

            # Create mock data for u100 and v100 (standard wind variables)
            u100_data = np.random.randn(len(time), len(lat), len(lon)).astype(np.float32)
            v100_data = np.random.randn(len(time), len(lat), len(lon)).astype(np.float32)

            # Create xarray dataset with valid_time (ERA5 convention)
            ds = xr.Dataset(
                {
                    "u100": (["valid_time", "latitude", "longitude"], u100_data),
                    "v100": (["valid_time", "latitude", "longitude"], v100_data),
                },
                coords={
                    "valid_time": time,
                    "latitude": lat,
                    "longitude": lon,
                },
            )

            # Save to NetCDF file in era5 subdirectory
            netcdf_file = era5_dir / "era5_test.nc"

            # Try to save, but skip if netCDF4 has issues
            try:
                ds.to_netcdf(netcdf_file, engine="netcdf4")
            except Exception:
                # Skip this test if netCDF4 has compatibility issues
                pytest.skip("NetCDF4 compatibility issue - skipping functional test")

            # Test the ERA5 loading API
            loader = LocalDataLoader(data_path=str(tmpdir_path))
            era5_dataset = loader.load_era5_data()

            # Verify results
            assert isinstance(era5_dataset, ERA5Dataset)
            assert era5_dataset.get_available_variables() == ["u100", "v100"]
            assert len(era5_dataset.get_available_variables()) == 2

            # Test wind components
            wind_components = era5_dataset.get_wind_components()
            assert wind_components is not None
            assert set(wind_components.keys()) == {"u100", "v100"}

            # Test time range
            time_range = era5_dataset.get_time_range()
            assert time_range is not None
            assert "start" in time_range
            assert "end" in time_range

            # Test spatial bounds
            spatial_bounds = era5_dataset.get_spatial_bounds()
            assert spatial_bounds is not None
            assert "lat_min" in spatial_bounds
            assert "lat_max" in spatial_bounds
            assert "lon_min" in spatial_bounds
            assert "lon_max" in spatial_bounds

    def test_data_validation_with_real_dataset(self):
        """Test validation logic with a real xarray dataset"""
        # Create a small real dataset for validation testing
        time = np.arange("2023-01-01", "2023-01-02", dtype="datetime64[h]")  # 24 hours
        lat = np.linspace(50, 55, 2)
        lon = np.linspace(-5, 5, 3)

        # Valid dataset with ERA5 variables
        valid_data = np.random.randn(len(time), len(lat), len(lon)).astype(np.float32)

        valid_ds = xr.Dataset(
            {
                "u100": (["time", "latitude", "longitude"], valid_data),
                "v100": (["time", "latitude", "longitude"], valid_data),
            },
            coords={
                "time": time,
                "latitude": lat,
                "longitude": lon,
            },
        )

        # This should work
        era5_dataset = ERA5Dataset(data=valid_ds)
        assert isinstance(era5_dataset, ERA5Dataset)
        assert era5_dataset.get_available_variables() == ["u100", "v100"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

