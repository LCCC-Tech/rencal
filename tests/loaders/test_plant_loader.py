#!/usr/bin/env python3
"""
Tests for PlantDatasetModel data loading functionality.
Tests both the LocalDataLoader methods and the Dataset validation.
"""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from rencal.core.data_loader import LocalDataLoader
from rencal.models import PlantDatasetModel
from rencal.utils.constants import WIND_TECHNOLOGY_TYPES


class TestPlantDataLoader:
    """Tests for plant data loading and validation"""

    def test_load_plant_data_success(self):
        """Test successful loading of plant data"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create plant subdirectory and CSV file
            plant_dir = Path(tmpdir) / "plant"
            plant_dir.mkdir()
            plant_file = plant_dir / "plant_data.csv"

            # Create sample plant data
            plant_data = pd.DataFrame(
                {
                    "cfd_id": ["WIND-001", "WIND-002", "SOLAR-001"],
                    "technology": ["Onshore Wind", "Offshore Wind", "Solar PV"],
                    "latitude": [51.5, 52.0, 50.5],
                    "longitude": [-1.0, 1.5, -2.0],
                    "capacity": [100.0, 250.0, 50.0],
                    "commission_date": ["2020-01-01", "2021-06-01", "2019-03-15"],
                    "plant_name": ["Wind Farm A", "Wind Farm B", "Solar Farm C"],
                }
            )
            plant_data.to_csv(plant_file, index=False)

            # Test loading
            loader = LocalDataLoader(data_path=tmpdir)
            result = loader.load_plant_data()

            # Verify results
            assert isinstance(result, PlantDatasetModel)
            # Filter to wind plants for testing
            wind_plants = result.get_wind_plants()
            assert len(wind_plants.data) == 2  # Only wind plants should be loaded
            assert all(wind_plants.data["technology"].isin(list(WIND_TECHNOLOGY_TYPES)))
            assert "plant_id" in result.data.columns  # Renamed from cfd_id

    def test_load_plant_data_file_not_found(self):
        """Test error handling when plant data file doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = LocalDataLoader(data_path=tmpdir)

            with pytest.raises(FileNotFoundError, match="Plant data file not found"):
                loader.load_plant_data()

    def test_plant_dataset_validation_success(self):
        """Test PlantDatasetModel validation with valid data"""
        valid_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001", "WIND-002"],
                "technology": ["Onshore Wind", "Offshore Wind"],
                "latitude": [51.5, 52.0],
                "longitude": [-1.0, 1.5],
                "capacity": [100.0, 250.0],
            }
        )

        dataset = PlantDatasetModel(data=valid_data)
        assert isinstance(dataset, PlantDatasetModel)
        assert len(dataset.data) == 2

    def test_plant_dataset_validation_missing_columns(self):
        """Test PlantDatasetModel validation with missing required columns"""
        invalid_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001"],
                "technology": ["Onshore Wind"],
                # Missing latitude, longitude, capacity
            }
        )

        with pytest.raises(ValueError, match="Missing required columns"):
            PlantDatasetModel(data=invalid_data)

    def test_plant_dataset_validation_invalid_types(self):
        """Test PlantDatasetModel validation with invalid data types"""
        invalid_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001"],
                "technology": ["Onshore Wind"],
                "latitude": ["not_a_number"],  # Should be numeric
                "longitude": [-1.0],
                "capacity": [100.0],
            }
        )

        with pytest.raises(ValueError, match="must be numeric"):
            PlantDatasetModel(data=invalid_data)

    def test_plant_dataset_methods(self):
        """Test PlantDatasetModel utility methods"""
        test_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001", "WIND-002", "SOLAR-001"],
                "technology": ["Onshore Wind", "Offshore Wind", "Solar PV"],
                "latitude": [51.5, 52.0, 50.5],
                "longitude": [-1.0, 1.5, -2.0],
                "capacity": [100.0, 250.0, 50.0],
            }
        )

        dataset = PlantDatasetModel(data=test_data)

        # Test filtering by technology
        wind_only = dataset.filter_by_technology(["Onshore Wind"])
        assert len(wind_only.data) == 1
        assert wind_only.data.iloc[0]["technology"] == "Onshore Wind"

        # Test geographic bounds
        bounds = dataset.get_geographic_bounds()
        assert bounds["lat_min"] == 50.5
        assert bounds["lat_max"] == 52.0
        assert bounds["lon_min"] == -2.0
        assert bounds["lon_max"] == 1.5

    def test_custom_plant_id_column(self):
        """Test loading with custom plant ID column name"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create plant data with different column name
            plant_dir = Path(tmpdir) / "plant"
            plant_dir.mkdir()
            plant_file = plant_dir / "plant_data.csv"

            plant_data = pd.DataFrame(
                {
                    "facility_id": ["WIND-001"],  # Different column name
                    "technology": ["Onshore Wind"],
                    "latitude": [51.5],
                    "longitude": [-1.0],
                    "capacity": [100.0],
                }
            )
            plant_data.to_csv(plant_file, index=False)

            # Test loading with custom column name
            loader = LocalDataLoader(data_path=tmpdir)
            result = loader.load_plant_data(id_column="facility_id")

            # Should rename to plant_id
            assert "plant_id" in result.data.columns
            assert "facility_id" not in result.data.columns
            assert result.data.iloc[0]["plant_id"] == "WIND-001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
