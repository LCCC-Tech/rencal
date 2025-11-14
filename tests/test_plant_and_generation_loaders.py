#!/usr/bin/env python3
"""
Comprehensive tests for GenerationDatasetModel and PlantDatasetModel data loading functionality.
Tests both the LocalDataLoader methods and the Dataset validation.
"""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from weather.core.data_loader import LocalDataLoader
from weather.models import GenerationDatasetModel, PlantDatasetModel
from weather.utils.constants import WIND_TECHNOLOGY_TYPES


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


class TestGenerationDataLoader:
    """Tests for generation data loading and validation"""

    def test_load_generation_data_success(self):
        """Test successful loading of generation data"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create generation subdirectory and CSV file
            gen_dir = Path(tmpdir) / "generation"
            gen_dir.mkdir()
            gen_file = gen_dir / "generation_data.csv"

            # Create sample generation data with UTC timestamps
            generation_data = pd.DataFrame(
                {
                    "cfd_id": ["WIND-001", "WIND-001", "WIND-002", "WIND-002"],
                    "time": [
                        "2023-01-01T00:00:00+00:00",
                        "2023-01-01T01:00:00+00:00",
                        "2023-01-01T00:00:00+00:00",
                        "2023-01-01T01:00:00+00:00",
                    ],
                    "quantity": [85.5, 92.1, 156.7, 178.3],
                }
            )
            generation_data.to_csv(gen_file, index=False)

            # Test loading
            loader = LocalDataLoader(data_path=tmpdir)
            result = loader.load_generation_data()

            # Verify results
            assert isinstance(result, GenerationDatasetModel)
            assert len(result.data) == 4
            assert "plant_id" in result.data.columns  # Renamed from cfd_id
            assert "time" in result.data.columns
            assert "quantity" in result.data.columns

    def test_load_generation_data_file_not_found(self):
        """Test error handling when generation data file doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = LocalDataLoader(data_path=tmpdir)

            with pytest.raises(FileNotFoundError, match="Generation data file not found"):
                loader.load_generation_data()

    def test_generation_dataset_validation_success(self):
        """Test GenerationDatasetModel validation with valid data"""
        valid_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001", "WIND-001"],
                "time": pd.to_datetime(["2023-01-01T00:00:00+00:00", "2023-01-01T01:00:00+00:00"]),
                "quantity": [85.5, 92.1],
            }
        )

        dataset = GenerationDatasetModel(data=valid_data)
        assert isinstance(dataset, GenerationDatasetModel)
        assert len(dataset.data) == 2

    def test_generation_dataset_validation_missing_columns(self):
        """Test GenerationDatasetModel validation with missing required columns"""
        invalid_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001"],
                "time": pd.to_datetime(["2023-01-01T00:00:00+00:00"]),
                # Missing quantity column
            }
        )

        with pytest.raises(ValueError, match="Missing required columns"):
            GenerationDatasetModel(data=invalid_data)

    def test_generation_dataset_validation_invalid_quantity_type(self):
        """Test GenerationDatasetModel validation with non-numeric quantity"""
        invalid_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001"],
                "time": pd.to_datetime(["2023-01-01T00:00:00+00:00"]),
                "quantity": ["not_a_number"],  # Should be numeric
            }
        )

        with pytest.raises(ValueError, match="must be numeric"):
            GenerationDatasetModel(data=invalid_data)

    def test_generation_dataset_methods(self):
        """Test GenerationDatasetModel utility methods"""
        test_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001", "WIND-001", "WIND-002", "WIND-002"],
                "time": pd.to_datetime([
                    "2023-01-01T00:00:00+00:00",
                    "2023-01-01T01:00:00+00:00",
                    "2023-01-01T00:00:00+00:00",
                    "2023-01-01T01:00:00+00:00",
                ]),
                "quantity": [85.5, 92.1, 156.7, 178.3],
            }
        )

        dataset = GenerationDatasetModel(data=test_data)

        # Test plant ID retrieval
        plant_ids = dataset.get_plant_ids()
        assert set(plant_ids) == {"WIND-001", "WIND-002"}

        # Test filtering by plant ID
        wind_001_data = dataset.filter_by_plant_id("WIND-001")
        assert len(wind_001_data.data) == 2
        assert all(wind_001_data.data["plant_id"] == "WIND-001")

        # Test time range
        time_range = dataset.get_time_range()
        assert time_range is not None
        assert "2023-01-01" in time_range["start"]
        assert "2023-01-01" in time_range["end"]
        assert time_range["periods"] == 2  # Unique time periods

    def test_generation_dataset_date_filtering(self):
        """Test GenerationDatasetModel date range filtering"""
        test_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001", "WIND-001", "WIND-001"],
                "time": pd.to_datetime([
                    "2023-01-01T00:00:00+00:00",
                    "2023-01-02T00:00:00+00:00",
                    "2023-01-03T00:00:00+00:00",
                ]),
                "quantity": [85.5, 92.1, 78.3],
            }
        )

        dataset = GenerationDatasetModel(data=test_data)

        # Filter to just first two days
        filtered = dataset.filter_by_date_range("2023-01-01", "2023-01-02")
        assert len(filtered.data) == 2

        # Check metadata
        assert "filtered_date_range" in filtered.metadata
        assert filtered.metadata["filtered_date_range"]["start"] == "2023-01-01"
        assert filtered.metadata["filtered_date_range"]["end"] == "2023-01-02"

    def test_generation_dataset_timezone_handling(self):
        """Test that GenerationDatasetModel properly handles UTC timestamps"""
        # Test data with explicit UTC timestamps
        utc_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001"],
                "time": pd.to_datetime(["2023-03-26T01:00:00+00:00"]),  # During DST transition
                "quantity": [85.5],
            }
        )

        dataset = GenerationDatasetModel(data=utc_data)
        time_range = dataset.get_time_range()

        # Should handle UTC timestamps correctly
        assert time_range is not None
        assert "2023-03-26" in time_range["start"]


class TestDataLoaderIntegration:
    """Integration tests for multiple data loaders working together"""

    def test_load_all_datasets_together(self):
        """Test loading plant and generation data together"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create plant data
            plant_dir = Path(tmpdir) / "plant"
            plant_dir.mkdir()
            plant_file = plant_dir / "plant_data.csv"

            plant_data = pd.DataFrame(
                {
                    "cfd_id": ["WIND-001", "WIND-002"],
                    "technology": ["Onshore Wind", "Offshore Wind"],
                    "latitude": [51.5, 52.0],
                    "longitude": [-1.0, 1.5],
                    "capacity": [100.0, 250.0],
                }
            )
            plant_data.to_csv(plant_file, index=False)

            # Create generation data
            gen_dir = Path(tmpdir) / "generation"
            gen_dir.mkdir()
            gen_file = gen_dir / "generation_data.csv"

            generation_data = pd.DataFrame(
                {
                    "cfd_id": ["WIND-001", "WIND-002"],
                    "time": ["2023-01-01T00:00:00+00:00", "2023-01-01T00:00:00+00:00"],
                    "quantity": [85.5, 156.7],
                }
            )
            generation_data.to_csv(gen_file, index=False)

            # Test loading both
            loader = LocalDataLoader(data_path=tmpdir)
            plant_dataset = loader.load_plant_data()
            generation_dataset = loader.load_generation_data()

            # Verify both loaded correctly
            assert isinstance(plant_dataset, PlantDatasetModel)
            assert isinstance(generation_dataset, GenerationDatasetModel)
            assert len(plant_dataset.data) == 2
            assert len(generation_dataset.data) == 2

            # Check that plant IDs match between datasets
            plant_ids = set(plant_dataset.data["plant_id"])
            gen_plant_ids = set(generation_dataset.data["plant_id"])
            assert plant_ids == gen_plant_ids

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