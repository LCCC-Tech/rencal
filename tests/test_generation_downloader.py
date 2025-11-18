"""Integration test suite for GenerationDataDownloader public API.

This module contains comprehensive integration tests for the GenerationDataDownloader
class using the public download() method. Tests focus on UK timezone handling during
DST transitions and proper end-to-end workflow validation with file I/O.

Test scenarios covered:
- Normal day: 48 settlement periods → 24 UTC hours
- Spring forward (DST start): 46 periods → 23 UTC hours (periods 3&4 missing per Elexon rules)
- Fall back (DST end): 50 periods → 25 UTC hours (spans midnight UTC)
- File creation and skip-if-exists behavior
- Complete download workflow with mocked external dependencies

Output format: cfd_id, time (UTC), quantity
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
    return Path(__file__).parent / "samples"


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
            assert list(result.columns) == ["cfd_id", "time", "quantity"]

            # Normal day should have exactly 24 UTC hours
            assert len(result) == 24, f"Expected 24 records for normal day, got {len(result)}"

            # Parse time column and verify it's UTC
            result["parsed_datetime"] = pd.to_datetime(result["time"])
            
            # Check that all datetimes are on expected date and in UTC
            expected_date = date(2023, 1, 15)
            dates = result["parsed_datetime"].dt.date.unique()
            assert len(dates) <= 2, "Normal day should span at most 2 UTC dates"
            assert expected_date in dates, f"Expected date {expected_date} should be present"
            
            # Verify timezone is UTC (should end with +00:00)
            assert all(dt_str.endswith("+00:00") for dt_str in result["time"]), (
                "All datetimes should be in UTC format (+00:00)"
            )

            # Enhanced UTC time range validation for normal day
            sorted_times = sorted(result["parsed_datetime"])
            expected_start = pd.Timestamp("2023-01-15 00:00:00+00:00")
            expected_end = pd.Timestamp("2023-01-15 23:00:00+00:00")
            assert sorted_times[0] == expected_start, (
                f"Normal day should start at {expected_start}, got {sorted_times[0]}"
            )
            assert sorted_times[-1] == expected_end, (
                f"Normal day should end at {expected_end}, got {sorted_times[-1]}"
            )
            
            # Verify 1-hour intervals between aggregated records
            for i in range(1, len(sorted_times)):
                interval = sorted_times[i] - sorted_times[i-1]
                assert interval == pd.Timedelta(hours=1), (
                    f"Expected 1-hour intervals, got {interval} between {sorted_times[i-1]} and {sorted_times[i]}"
                )

            # Test raw settlement period mapping (before aggregation)
            raw_utc_times = downloader_with_temp_dir._create_hourly_utc_datetime(
                normal_day_generation_df.rename(columns={
                    "settlementDate": "settlement_date",
                    "settlementPeriod": "settlement_period"
                })
            )
            
            # Verify 30-minute periods map correctly - should be 2 periods per hour
            raw_unique = sorted(raw_utc_times.dt.floor('h').unique())
            assert len(raw_unique) == 24, f"Raw periods should map to 24 unique hours, got {len(raw_unique)}"
            
            # Check that we have exactly 2 periods per hour (30-min intervals)
            hour_counts = raw_utc_times.dt.floor('h').value_counts()
            assert all(count == 2 for count in hour_counts), (
                f"Each hour should have exactly 2 periods (30-min intervals), got: {hour_counts.to_dict()}"
            )

            # Verify CfD ID is preserved
            assert all(result["cfd_id"] == "TEST-CFD-001"), "CfD ID should be preserved"

            # Verify total quantity preservation
            original_total = normal_day_generation_df["quantity"].sum()
            aggregated_total = result["quantity"].sum()
            assert abs(original_total - aggregated_total) < 0.05, (
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

            # Spring forward: 46 periods should produce 23 UTC hours
            # (periods 3&4 are missing per official Elexon rules)
            # Fixed: Now using correct Elexon settlement period mapping
            expected_records = 23  # Periods 3&4 missing = 23 unique hours
            assert len(result) == expected_records, (
                f"Expected {expected_records} records for spring forward, got {len(result)}"
            )

            # Verify all datetimes are UTC format
            assert all(dt_str.endswith("+00:00") for dt_str in result["time"]), (
                "All datetimes should be in UTC format (+00:00)"
            )
            
            # Parse datetimes to verify date range
            result["parsed_datetime"] = pd.to_datetime(result["time"])
            dates = result["parsed_datetime"].dt.date.unique()
            expected_date = date(2023, 3, 26)
            assert expected_date in dates, f"Expected date {expected_date} should be present"

            # Enhanced UTC time range validation for spring forward day
            sorted_times = sorted(result["parsed_datetime"])
            expected_start = pd.Timestamp("2023-03-26 00:00:00+00:00")
            expected_end = pd.Timestamp("2023-03-26 22:00:00+00:00")  # Missing 23:00 hour
            assert sorted_times[0] == expected_start, (
                f"Spring forward day should start at {expected_start}, got {sorted_times[0]}"
            )
            assert sorted_times[-1] == expected_end, (
                f"Spring forward day should end at {expected_end}, got {sorted_times[-1]}"
            )
            
            # Verify 1-hour intervals between aggregated records (except missing hour)
            expected_hours = list(range(0, 23))  # Hours 0-22 (missing hour 23)
            actual_hours = [t.hour for t in sorted_times]
            assert actual_hours == expected_hours, (
                f"Spring forward should have hours 0-22, got {actual_hours}"
            )

            # Test raw settlement period mapping (before aggregation)  
            raw_utc_times = downloader_with_temp_dir._create_hourly_utc_datetime(
                spring_forward_generation_df.rename(columns={
                    "settlementDate": "settlement_date", 
                    "settlementPeriod": "settlement_period"
                })
            )
            
            # Verify 46 periods map to 23 unique hours (2 periods per hour)
            raw_unique = sorted(raw_utc_times.dt.floor('h').unique())
            assert len(raw_unique) == 23, f"Raw periods should map to 23 unique hours, got {len(raw_unique)}"
            
            # Check that we have exactly 2 periods per hour (30-min intervals)
            hour_counts = raw_utc_times.dt.floor('h').value_counts()
            assert all(count == 2 for count in hour_counts), (
                f"Each hour should have exactly 2 periods (30-min intervals), got: {hour_counts.to_dict()}"
            )
            
            # Verify the missing hour in raw data
            raw_hours = [t.hour for t in raw_unique]
            assert raw_hours == expected_hours, (
                f"Raw data should span hours 0-22 (missing 23), got {raw_hours}"
            )

            # Verify quantity preservation
            original_total = spring_forward_generation_df["quantity"].sum()
            aggregated_total = result["quantity"].sum()
            assert abs(original_total - aggregated_total) < 0.05, (
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
            assert all(dt_str.endswith("+00:00") for dt_str in result["time"]), (
                "All datetimes should be in UTC format (+00:00)"
            )

            # Parse datetimes to verify date range spans multiple dates
            result["parsed_datetime"] = pd.to_datetime(result["time"])
            dates = result["parsed_datetime"].dt.date.unique()
            expected_date = date(2023, 10, 29)
            assert expected_date in dates, f"Expected date {expected_date} should be present"
            # Fall back should span multiple UTC dates
            assert len(dates) > 1, "Fall back should span multiple UTC dates due to timezone change"

            # Enhanced UTC time range validation for fall back day
            sorted_times = sorted(result["parsed_datetime"])
            expected_start = pd.Timestamp("2023-10-28 23:00:00+00:00")  # Starts night before
            expected_end = pd.Timestamp("2023-10-29 23:00:00+00:00")    # Ends at 23:00 next day
            assert sorted_times[0] == expected_start, (
                f"Fall back day should start at {expected_start}, got {sorted_times[0]}"
            )
            assert sorted_times[-1] == expected_end, (
                f"Fall back day should end at {expected_end}, got {sorted_times[-1]}"
            )
            
            # Verify we have 25 unique hours including the duplicate
            # Should have: 28th 23:00, 29th 00:00-23:00 (with one hour duplicated)
            time_hours = [(t.date(), t.hour) for t in sorted_times]
            assert len(time_hours) == 25, f"Should have 25 unique hour records, got {len(time_hours)}"

            # Test raw settlement period mapping (before aggregation)
            raw_utc_times = downloader_with_temp_dir._create_hourly_utc_datetime(
                fall_back_generation_df.rename(columns={
                    "settlementDate": "settlement_date",
                    "settlementPeriod": "settlement_period"
                })
            )
            
            # Verify 50 periods map to 25 unique hours (2 periods per hour)
            raw_unique = sorted(raw_utc_times.dt.floor('h').unique())
            assert len(raw_unique) == 25, f"Raw periods should map to 25 unique hours, got {len(raw_unique)}"
            
            # Check that we have exactly 2 periods per hour (30-min intervals)
            hour_counts = raw_utc_times.dt.floor('h').value_counts()
            assert all(count == 2 for count in hour_counts), (
                f"Each hour should have exactly 2 periods (30-min intervals), got: {hour_counts.to_dict()}"
            )
            
            # Verify the time span in raw data
            raw_start = raw_utc_times.min()
            raw_end = raw_utc_times.max()
            assert raw_start == expected_start, (
                f"Raw data should start at {expected_start}, got {raw_start}"
            )
            assert raw_end == expected_end, (
                f"Raw data should end at {expected_end}, got {raw_end}"
            )

            # Verify quantity preservation
            original_total = fall_back_generation_df["quantity"].sum()
            aggregated_total = result["quantity"].sum()
            assert abs(original_total - aggregated_total) < 0.05, (
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
            assert "time" in final_data.columns, (
                "Final data should have time column"
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
        output_file.write_text("cfd_id,time,quantity\nTEST,2023-01-01 00:00:00+00:00,100.0\n")

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

    def test_large_dataset_aggregation_efficiency_regression(
        self,
        downloader_with_temp_dir: GenerationDataDownloader,
    ) -> None:
        """Regression test for timezone/aggregation bug that caused 'AmbiguousTimeError: 165 DST switches'.
        
        This test prevents the bug where datetime creation was done BEFORE BMU aggregation,
        causing massive duplicate datetimes that confused pandas timezone localization.
        
        The fix: BMU data must be aggregated by (CFD, settlement_date, settlement_period) 
        BEFORE creating timezone-aware datetimes.
        """
        from unittest.mock import patch
        import pandas as pd
        
        # Create realistic test data that would trigger the original bug:
        # Multiple BMUs (simulating 40+ real BMUs) with overlapping settlement periods
        bmui_ids = [f"BMU_{i:03d}" for i in range(40)]  # 40 BMUs (similar to real scale)
        settlement_dates = ["2023-01-01", "2023-01-02"]  # Multiple dates
        settlement_periods = list(range(1, 49))  # Full day of periods
        
        # Generate realistic BMU data (40 BMUs × 2 dates × 48 periods = 3,840 records)
        bmu_data = []
        for bmu_id in bmui_ids:
            for date in settlement_dates:
                for period in settlement_periods:
                    bmu_data.append({
                        "settlementDate": date,
                        "settlementPeriod": period, 
                        "bmUnit": bmu_id,
                        "quantity": 1.5  # Consistent quantity for easier testing
                    })
        
        bmu_generation_df = pd.DataFrame(bmu_data)
        
        # Create CFD mapping (map all BMUs to fewer CFDs to force aggregation)
        cfd_data = []
        for i, bmu_id in enumerate(bmui_ids):
            cfd_id = f"CFD_{i // 10:02d}"  # Group every 10 BMUs into same CFD
            cfd_data.append({"cfd_id": cfd_id, "bmu_id": bmu_id})
        
        cfd_df = pd.DataFrame(cfd_data)
        
        with (
            patch.object(downloader_with_temp_dir, "_get_cfd_plants") as mock_cfd,
            patch.object(downloader_with_temp_dir, "_download_generation_data") as mock_bmu_data, 
        ):
            mock_cfd.return_value = cfd_df
            mock_bmu_data.return_value = bmu_generation_df
            
            # The key test: This should NOT raise AmbiguousTimeError about DST switches
            downloader_with_temp_dir.download()
            
            # Verify the result shows proper aggregation occurred
            output_file = downloader_with_temp_dir.output_dir / "generation_data.csv"
            result = pd.read_csv(output_file)
            
            # Check that aggregation worked correctly:
            # - 4 CFDs (every 10 BMUs grouped) 
            # - 2 dates × 24 hours = 48 unique datetimes
            # - Expected: 4 CFDs × 48 hours = 192 final records (not 3,840 raw BMU records)
            expected_max_records = 4 * 48  # 4 CFDs × 48 hours
            assert len(result) <= expected_max_records, (
                f"Result should be aggregated to ≤{expected_max_records} records, got {len(result)}"
            )
            
            # Verify no single CFD has impossible number of records  
            cfd_counts = result["cfd_id"].value_counts()
            max_count = cfd_counts.max()
            assert max_count <= 48, (
                f"No CFD should have >48 hourly records, got max: {max_count}, counts: {cfd_counts.to_dict()}"
            )
            
            # Verify quantities were properly aggregated (10 BMUs × 1.5 each = 15.0 per CFD per period)
            expected_quantity_per_record = 10 * 1.5  # 10 BMUs per CFD × 1.5 each
            # Allow some tolerance for hourly aggregation (periods within same hour are summed)
            assert result["quantity"].min() >= expected_quantity_per_record, (
                f"Aggregated quantities should be ≥{expected_quantity_per_record}, "
                f"got min: {result['quantity'].min()}"
            )
            
            # Most importantly: verify datetime creation succeeded without timezone errors
            # (The test passing means no AmbiguousTimeError was raised)
            assert "time" in result.columns, "DateTime column should be created successfully"
            na_count = result["time"].isna().sum()
            assert na_count == 0, f"All datetime values should be valid, found {na_count} NaT values"


# Original integration tests (kept for comparison during migration)


if __name__ == "__main__":
    # Allow running tests directly with python -m pytest tests/test_generation_downloader.py
    pytest.main([__file__, "-vv"])
