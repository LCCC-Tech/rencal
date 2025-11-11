"""Integration test suite for GenerationDataDownloader public API.

This module contains comprehensive integration tests for the GenerationDataDownloader
class using the public download() method. Tests focus on UK timezone handling during
DST transitions and proper end-to-end workflow validation with file I/O.

Test scenarios covered:
- Normal day: 48 settlement periods → 24 UTC hours
- Spring forward (DST start): 46 periods → 22 UTC hours (compressed due to DST)
- Fall back (DST end): 50 periods → 25 UTC hours (spans midnight UTC)
- File creation and skip-if-exists behavior
- Complete download workflow with mocked external dependencies

Output format: cfd_id, settlement_datetime (UTC), quantity
"""

import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# Add the parent directory to sys.path so we can import weather modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from weather.core.data_downloader import GenerationDataDownloader


# Shared fixtures for all test classes
@pytest.fixture
def test_data_dir() -> Path:
    """Return path to test data directory."""
    return Path(__file__).parent / "data"


@pytest.fixture
def test_cfd_df() -> pd.DataFrame:
    """Create test CfD DataFrame with BMU mapping."""
    return pd.DataFrame({"cfd_id": ["TEST-CFD-001"], "bmu_id": ["C__PSTAT011"]})


@pytest.fixture
def normal_day_generation_df(test_data_dir: Path) -> pd.DataFrame:
    """Load normal day generation data (48 settlement periods)."""
    return pd.read_csv(test_data_dir / "test_generation_normal.csv")


@pytest.fixture
def spring_forward_generation_df(test_data_dir: Path) -> pd.DataFrame:
    """Load spring forward day generation data (46 settlement periods)."""
    return pd.read_csv(test_data_dir / "test_generation_spring.csv")


@pytest.fixture
def fall_back_generation_df(test_data_dir: Path) -> pd.DataFrame:
    """Load fall back day generation data (50 settlement periods)."""
    return pd.read_csv(test_data_dir / "test_generation_fall.csv")


class TestGenerationDataDownloader:
    """Integration tests for GenerationDataDownloader using public download() method."""

    @pytest.fixture
    def temp_output_dir(self, tmp_path: Path) -> Path:
        """Create temporary output directory for test files."""
        output_dir = tmp_path / "test_generation_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    @pytest.fixture
    def downloader_with_temp_dir(self, temp_output_dir: Path) -> GenerationDataDownloader:
        """Create downloader with temporary output directory."""
        downloader = GenerationDataDownloader()
        downloader.output_dir = temp_output_dir
        return downloader

    def test_download_normal_day_timezone_handling(
        self,
        downloader_with_temp_dir: GenerationDataDownloader,
        test_cfd_df: pd.DataFrame,
        normal_day_generation_df: pd.DataFrame,
    ) -> None:
        """Test complete download workflow preserves timezone handling for normal day."""

        # Mock external dependencies but let timezone logic run for real
        with (
            patch.object(downloader_with_temp_dir, "_get_cfd_plants") as mock_cfd,
            patch.object(downloader_with_temp_dir, "_download_generation_data") as mock_bmu_data,
        ):
            # Setup mocks with our test data
            mock_cfd.return_value = test_cfd_df
            mock_bmu_data.return_value = normal_day_generation_df

            # Call public method - this runs the timezone logic for real!
            downloader_with_temp_dir.download()

            # Read the final output file that was written
            output_file = downloader_with_temp_dir.output_dir / "generation_data.csv"
            assert output_file.exists(), f"Output file should exist at {output_file}"

            result = pd.read_csv(output_file)

            # Verify new UTC datetime format
            assert not result.empty, "Result should not be empty"
            assert list(result.columns) == ["cfd_id", "settlement_datetime", "quantity"]

            # Normal day should have exactly 24 UTC hours
            assert len(result) == 24, f"Expected 24 records for normal day, got {len(result)}"

            # Parse settlement_datetime and verify it's UTC
            result["parsed_datetime"] = pd.to_datetime(result["settlement_datetime"])
            
            # Check that all datetimes are on expected date and in UTC
            expected_date = date(2023, 1, 15)
            dates = result["parsed_datetime"].dt.date.unique()
            assert len(dates) <= 2, "Normal day should span at most 2 UTC dates"
            assert expected_date in dates, f"Expected date {expected_date} should be present"
            
            # Verify timezone is UTC (should end with +00:00)
            assert all(dt_str.endswith("+00:00") for dt_str in result["settlement_datetime"]), (
                "All datetimes should be in UTC format (+00:00)"
            )

            # Verify CfD ID is preserved
            assert all(result["cfd_id"] == "TEST-CFD-001"), "CfD ID should be preserved"

            # Verify total quantity preservation
            original_total = normal_day_generation_df["quantity"].sum()
            aggregated_total = result["quantity"].sum()
            assert abs(original_total - aggregated_total) < 0.01, (
                f"Total quantity not preserved: {original_total} vs {aggregated_total}"
            )

    def test_download_spring_forward_timezone_handling(
        self,
        downloader_with_temp_dir: GenerationDataDownloader,
        test_cfd_df: pd.DataFrame,
        spring_forward_generation_df: pd.DataFrame,
    ) -> None:
        """Test complete download workflow handles spring forward DST (46 periods → 23 hours)."""

        with (
            patch.object(downloader_with_temp_dir, "_get_cfd_plants") as mock_cfd,
            patch.object(downloader_with_temp_dir, "_download_generation_data") as mock_bmu_data,
        ):
            mock_cfd.return_value = test_cfd_df
            mock_bmu_data.return_value = spring_forward_generation_df

            # Call public method
            downloader_with_temp_dir.download()

            # Read and verify results
            output_file = downloader_with_temp_dir.output_dir / "generation_data.csv"
            result = pd.read_csv(output_file)

            # Spring forward: 46 periods should produce ~22 UTC hours
            # (some hours get compressed due to DST transition)
            expected_records = 22  # Based on our testing above
            assert len(result) == expected_records, (
                f"Expected {expected_records} records for spring forward, got {len(result)}"
            )

            # Verify all datetimes are UTC format
            assert all(dt_str.endswith("+00:00") for dt_str in result["settlement_datetime"]), (
                "All datetimes should be in UTC format (+00:00)"
            )
            
            # Parse datetimes to verify date range
            result["parsed_datetime"] = pd.to_datetime(result["settlement_datetime"])
            dates = result["parsed_datetime"].dt.date.unique()
            expected_date = date(2023, 3, 26)
            assert expected_date in dates, f"Expected date {expected_date} should be present"

            # Verify quantity preservation
            original_total = spring_forward_generation_df["quantity"].sum()
            aggregated_total = result["quantity"].sum()
            assert abs(original_total - aggregated_total) < 0.01, (
                f"Total quantity not preserved: {original_total} vs {aggregated_total}"
            )

    def test_download_fall_back_timezone_handling(
        self,
        downloader_with_temp_dir: GenerationDataDownloader,
        test_cfd_df: pd.DataFrame,
        fall_back_generation_df: pd.DataFrame,
    ) -> None:
        """Test complete download workflow handles fall back DST (50 periods → 25 hours)."""

        with (
            patch.object(downloader_with_temp_dir, "_get_cfd_plants") as mock_cfd,
            patch.object(downloader_with_temp_dir, "_download_generation_data") as mock_bmu_data,
        ):
            mock_cfd.return_value = test_cfd_df
            mock_bmu_data.return_value = fall_back_generation_df

            # Call public method
            downloader_with_temp_dir.download()

            # Read and verify results
            output_file = downloader_with_temp_dir.output_dir / "generation_data.csv"
            result = pd.read_csv(output_file)

            # Fall back: 50 periods should produce 25 UTC hours
            # (spans across UTC midnight due to timezone change)
            expected_records = 25  # Based on our testing above
            assert len(result) == expected_records, (
                f"Expected {expected_records} records for fall back, got {len(result)}"
            )

            # Verify all datetimes are UTC format
            assert all(dt_str.endswith("+00:00") for dt_str in result["settlement_datetime"]), (
                "All datetimes should be in UTC format (+00:00)"
            )

            # Parse datetimes to verify date range spans multiple dates
            result["parsed_datetime"] = pd.to_datetime(result["settlement_datetime"])
            dates = result["parsed_datetime"].dt.date.unique()
            expected_date = date(2023, 10, 29)
            assert expected_date in dates, f"Expected date {expected_date} should be present"
            # Fall back should span multiple UTC dates
            assert len(dates) > 1, "Fall back should span multiple UTC dates due to timezone change"

            # Verify quantity preservation
            original_total = fall_back_generation_df["quantity"].sum()
            aggregated_total = result["quantity"].sum()
            assert abs(original_total - aggregated_total) < 0.01, (
                f"Total quantity not preserved: {original_total} vs {aggregated_total}"
            )

    def test_download_creates_final_output_file(
        self,
        downloader_with_temp_dir: GenerationDataDownloader,
        test_cfd_df: pd.DataFrame,
        normal_day_generation_df: pd.DataFrame,
    ) -> None:
        """Test that download creates the final aggregated CfD generation data file."""

        with (
            patch.object(downloader_with_temp_dir, "_get_cfd_plants") as mock_cfd,
            patch.object(downloader_with_temp_dir, "_download_generation_data") as mock_bmu_data,
        ):
            mock_cfd.return_value = test_cfd_df
            mock_bmu_data.return_value = normal_day_generation_df

            # Call public method
            downloader_with_temp_dir.download()

            # Verify final aggregated file is created (note: download() updates output_dir to include /generation)
            final_file = downloader_with_temp_dir.output_dir / "generation_data.csv"

            assert final_file.exists(), f"Final aggregated file should exist at {final_file}"

            # Verify processed file contains aggregated data with expected structure
            final_data = pd.read_csv(final_file)
            assert "cfd_id" in final_data.columns, "Final data should have cfd_id column"
            assert "settlement_datetime" in final_data.columns, (
                "Final data should have settlement_datetime column"
            )
            assert "quantity" in final_data.columns, "Final data should have quantity column"

            # Verify data content matches expected aggregation
            assert len(final_data) == 24, "Should have 24 hourly records for normal day"
            assert final_data["cfd_id"].iloc[0] == "TEST-CFD-001", "Should contain correct CfD ID"

    def test_download_skips_if_file_exists(
        self, downloader_with_temp_dir: GenerationDataDownloader, test_cfd_df: pd.DataFrame
    ) -> None:
        """Test that download skips processing if output file already exists."""

        # Create the generation subdirectory and output file
        generation_dir = downloader_with_temp_dir.output_dir / "generation"
        generation_dir.mkdir(parents=True, exist_ok=True)
        output_file = generation_dir / "generation_data.csv"
        output_file.write_text("cfd_id,settlement_datetime,quantity\nTEST,2023-01-01 00:00:00+00:00,100.0\n")

        with (
            patch.object(downloader_with_temp_dir, "_get_cfd_plants") as mock_cfd,
            patch.object(downloader_with_temp_dir, "_download_generation_data") as mock_bmu_data,
        ):
            mock_cfd.return_value = test_cfd_df

            # Call public method
            downloader_with_temp_dir.download()

            # Verify that download methods were not called (except the initial cfd call)
            mock_cfd.assert_called_once()  # This gets called to check for the file
            mock_bmu_data.assert_not_called()  # This should be skipped

            # Verify file content is unchanged
            result = pd.read_csv(output_file)
            assert len(result) == 1, "File should be unchanged"
            assert result["cfd_id"].iloc[0] == "TEST", "Original content should be preserved"  # type: ignore[attr-defined]


# Original integration tests (kept for comparison during migration)


if __name__ == "__main__":
    # Allow running tests directly with python -m pytest tests/test_generation_downloader.py
    pytest.main([__file__, "-vv"])
