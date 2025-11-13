#!/usr/bin/env python3
"""
Comprehensive tests for GenerationDataset and PlantDataset data loading functionality.
Tests both the LocalDataLoader methods and the Dataset validation.
"""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from weather.core.data_loader import LocalDataLoader
from weather.models.dataset import GenerationDataset, PlantDataset
from weather.utils.constants import WIND_TECHNOLOGY_TYPES


class TestPlantDataLoader:
    """Tests for plant data loading and validation"""

    def test_load_wind_plant_data_success(self):
        """Test successful loading of wind plant data"""
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
            result = loader.load_wind_plant_data()

            # Verify results
            assert isinstance(result, PlantDataset)
            assert len(result.data) == 2  # Only wind plants should be loaded
            assert all(result.data["technology"].isin(list(WIND_TECHNOLOGY_TYPES)))
            assert "plant_id" in result.data.columns  # Renamed from cfd_id
            assert set(result.get_columns()) == {
                "plant_id",
                "technology",
                "latitude",
                "longitude",
                "capacity",
                "commission_date",
                "plant_name",
            }

    def test_load_wind_plant_data_file_not_found(self):
        """Test error handling when plant data file doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = LocalDataLoader(data_path=tmpdir)

            with pytest.raises(FileNotFoundError, match="Plant data file not found"):
                loader.load_wind_plant_data()

    def test_plant_dataset_validation_success(self):
        """Test PlantDataset validation with valid data"""
        valid_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001", "WIND-002"],
                "technology": ["Onshore Wind", "Offshore Wind"],
                "latitude": [51.5, 52.0],
                "longitude": [-1.0, 1.5],
                "capacity": [100.0, 250.0],
            }
        )

        dataset = PlantDataset(data=valid_data)
        assert isinstance(dataset, PlantDataset)
        assert len(dataset.data) == 2

    def test_plant_dataset_validation_missing_columns(self):
        """Test PlantDataset validation with missing required columns"""
        invalid_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001"],
                "technology": ["Onshore Wind"],
                # Missing latitude, longitude, capacity
            }
        )

        with pytest.raises(ValueError, match="Missing required columns"):
            PlantDataset(data=invalid_data)

    def test_plant_dataset_validation_invalid_types(self):
        """Test PlantDataset validation with invalid data types"""
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
            PlantDataset(data=invalid_data)

    def test_plant_dataset_methods(self):
        """Test PlantDataset utility methods"""
        test_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001", "WIND-002", "SOLAR-001"],
                "technology": ["Onshore Wind", "Offshore Wind", "Solar PV"],
                "latitude": [51.5, 52.0, 50.5],
                "longitude": [-1.0, 1.5, -2.0],
                "capacity": [100.0, 250.0, 50.0],
            }
        )

        dataset = PlantDataset(data=test_data)

        # Test filtering by technology
        wind_only = dataset.filter_by_technology("Onshore Wind")
        assert len(wind_only.data) == 1
        assert wind_only.data.iloc[0]["technology"] == "Onshore Wind"

        # Test geographic bounds
        bounds = dataset.get_geographic_bounds()
        assert bounds["lat_min"] == 50.5
        assert bounds["lat_max"] == 52.0
        assert bounds["lon_min"] == -2.0
        assert bounds["lon_max"] == 1.5

        # Test capacity summary
        capacity_summary = dataset.get_capacity_summary()
        assert capacity_summary["total_capacity"] == 400.0
        assert capacity_summary["capacity_count"] == 3
        assert capacity_summary["mean_capacity"] == pytest.approx(133.33, rel=1e-2)


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
            assert isinstance(result, GenerationDataset)
            assert len(result.data) == 4
            assert "plant_id" in result.data.columns  # Renamed from cfd_id
            assert "time" in result.data.columns
            assert "quantity" in result.data.columns
            assert set(result.get_columns()) == {"plant_id", "time", "quantity"}

    def test_load_generation_data_file_not_found(self):
        """Test error handling when generation data file doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = LocalDataLoader(data_path=tmpdir)

            with pytest.raises(FileNotFoundError, match="Generation data file not found"):
                loader.load_generation_data()

    def test_generation_dataset_validation_success(self):
        """Test GenerationDataset validation with valid data"""
        valid_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001", "WIND-001"],
                "time": ["2023-01-01T00:00:00+00:00", "2023-01-01T01:00:00+00:00"],
                "quantity": [85.5, 92.1],
            }
        )

        dataset = GenerationDataset(data=valid_data)
        assert isinstance(dataset, GenerationDataset)
        assert len(dataset.data) == 2

    def test_generation_dataset_validation_missing_columns(self):
        """Test GenerationDataset validation with missing required columns"""
        invalid_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001"],
                "time": ["2023-01-01T00:00:00+00:00"],
                # Missing quantity column
            }
        )

        with pytest.raises(ValueError, match="Missing required columns"):
            GenerationDataset(data=invalid_data)

    def test_generation_dataset_validation_invalid_quantity_type(self):
        """Test GenerationDataset validation with non-numeric quantity"""
        invalid_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001"],
                "time": ["2023-01-01T00:00:00+00:00"],
                "quantity": ["not_a_number"],  # Should be numeric
            }
        )

        with pytest.raises(ValueError, match="must be numeric"):
            GenerationDataset(data=invalid_data)

    def test_generation_dataset_methods(self):
        """Test GenerationDataset utility methods"""
        test_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001", "WIND-001", "WIND-002", "WIND-002"],
                "time": [
                    "2023-01-01T00:00:00+00:00",
                    "2023-01-01T01:00:00+00:00",
                    "2023-01-01T00:00:00+00:00",
                    "2023-01-01T01:00:00+00:00",
                ],
                "quantity": [85.5, 92.1, 156.7, 178.3],
            }
        )

        dataset = GenerationDataset(data=test_data)

        # Test plant ID retrieval
        plant_ids = dataset.get_plant_ids()
        assert set(plant_ids) == {"WIND-001", "WIND-002"}

        # Test filtering by plant ID
        wind_001_data = dataset.filter_by_plant_id("WIND-001")
        assert len(wind_001_data.data) == 2
        assert all(wind_001_data.data["plant_id"] == "WIND-001")

        # Test generation summary
        summary = dataset.get_generation_summary()
        assert summary["total_generation"] == pytest.approx(512.6)
        assert summary["plant_count"] == 2
        assert summary["time_periods"] == 4
        assert summary["mean_generation"] == pytest.approx(128.15)

        # Test time range
        time_range = dataset.get_time_range()
        assert time_range is not None
        assert "2023-01-01" in time_range["start"]
        assert "2023-01-01" in time_range["end"]
        assert time_range["periods"] == 2  # Unique time periods

    def test_generation_dataset_date_filtering(self):
        """Test GenerationDataset date range filtering"""
        test_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001", "WIND-001", "WIND-001"],
                "time": [
                    "2023-01-01T00:00:00+00:00",
                    "2023-01-02T00:00:00+00:00",
                    "2023-01-03T00:00:00+00:00",
                ],
                "quantity": [85.5, 92.1, 78.3],
            }
        )

        dataset = GenerationDataset(data=test_data)

        # Filter to just first two days
        filtered = dataset.filter_by_date_range("2023-01-01", "2023-01-02")
        assert len(filtered.data) == 2

        # Check metadata
        assert "filtered_date_range" in filtered.metadata
        assert filtered.metadata["filtered_date_range"]["start"] == "2023-01-01"
        assert filtered.metadata["filtered_date_range"]["end"] == "2023-01-02"

    def test_generation_dataset_timezone_handling(self):
        """Test that GenerationDataset properly handles UTC timestamps"""
        # Test data with explicit UTC timestamps
        utc_data = pd.DataFrame(
            {
                "plant_id": ["WIND-001"],
                "time": ["2023-03-26T01:00:00+00:00"],  # During DST transition
                "quantity": [85.5],
            }
        )

        dataset = GenerationDataset(data=utc_data)
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
            plant_dataset = loader.load_wind_plant_data()
            generation_dataset = loader.load_generation_data()

            # Verify both loaded correctly
            assert isinstance(plant_dataset, PlantDataset)
            assert isinstance(generation_dataset, GenerationDataset)
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
            result = loader.load_wind_plant_data(id_column="facility_id")

            # Should rename to plant_id
            assert "plant_id" in result.data.columns
            assert "facility_id" not in result.data.columns
            assert result.data.iloc[0]["plant_id"] == "WIND-001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

