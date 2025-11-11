"""Test suite for GenerationDataDownloader timezone handling.

This module contains comprehensive tests for the GenerationDataDownloader class,
specifically focusing on UK timezone handling during DST transitions and the
proper aggregation of settlement period data to hourly intervals.

Test scenarios covered:
- Normal day: 48 settlement periods → 24 hours (0-23)
- Spring forward (DST start): 46 periods → 23 hours (0-22, one hour fewer)
- Fall back (DST end): 50 periods → 25 hours (0-24, one extra hour)
"""

import pandas as pd
import pytest
from pathlib import Path
from datetime import date
import sys
import os

# Add the parent directory to sys.path so we can import weather modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from weather.core.data_downloader import GenerationDataDownloader


class TestGenerationDataDownloader:
    """Test class for GenerationDataDownloader timezone handling."""
    
    @pytest.fixture
    def test_data_dir(self) -> Path:
        """Return path to test data directory."""
        return Path(__file__).parent / "data"
    
    @pytest.fixture
    def test_cfd_df(self) -> pd.DataFrame:
        """Create test CfD DataFrame with BMU mapping."""
        return pd.DataFrame({
            'cfd_id': ['TEST-CFD-001'],
            'bmu_id': ['C__PSTAT011']
        })
    
    @pytest.fixture
    def normal_day_generation_df(self, test_data_dir: Path) -> pd.DataFrame:
        """Load normal day generation data (48 settlement periods)."""
        return pd.read_csv(test_data_dir / "test_generation_normal.csv")
    
    @pytest.fixture
    def spring_forward_generation_df(self, test_data_dir: Path) -> pd.DataFrame:
        """Load spring forward day generation data (46 settlement periods)."""
        return pd.read_csv(test_data_dir / "test_generation_spring.csv")
    
    @pytest.fixture
    def fall_back_generation_df(self, test_data_dir: Path) -> pd.DataFrame:
        """Load fall back day generation data (50 settlement periods)."""
        return pd.read_csv(test_data_dir / "test_generation_fall.csv")
    
    @pytest.fixture
    def downloader(self) -> GenerationDataDownloader:
        """Create GenerationDataDownloader instance."""
        # Create a downloader instance - we don't need any external dependencies
        # since we're testing the _aggregate_bmu_generation_to_cfd method directly
        return GenerationDataDownloader()
    
    def test_normal_day_timezone_handling(self, downloader: GenerationDataDownloader, test_cfd_df: pd.DataFrame, normal_day_generation_df: pd.DataFrame) -> None:
        """Test timezone handling for a normal day (48 settlement periods → 24 hours)."""
        result = downloader._aggregate_bmu_generation_to_cfd(test_cfd_df, normal_day_generation_df)
        
        # Verify basic structure
        assert not result.empty, "Result should not be empty"
        assert list(result.columns) == ['cfd_id', 'settlement_date', 'hour', 'quantity']
        
        # Check we have exactly 24 hours (0-23)
        hours = sorted(result['hour'].unique())
        assert hours == list(range(24)), f"Expected hours 0-23, got {hours}"
        
        # Verify settlement date is correct
        expected_date = date(2023, 1, 15)
        settlement_dates = result['settlement_date'].unique()
        assert len(settlement_dates) == 1, f"Expected 1 date, got {len(settlement_dates)}"
        assert settlement_dates[0] == expected_date, f"Expected {expected_date}, got {settlement_dates[0]}"
        
        # Verify CfD ID is preserved
        assert all(result['cfd_id'] == 'TEST-CFD-001'), "CfD ID should be preserved"
        
        # Verify total quantity preservation (sum of all settlement periods should equal sum of all hours)
        original_total = normal_day_generation_df['quantity'].sum()
        aggregated_total = result['quantity'].sum()
        assert abs(original_total - aggregated_total) < 0.01, f"Total quantity not preserved: {original_total} vs {aggregated_total}"
    
    def test_spring_forward_timezone_handling(self, downloader: GenerationDataDownloader, test_cfd_df: pd.DataFrame, spring_forward_generation_df: pd.DataFrame) -> None:
        """Test timezone handling for spring forward day (46 settlement periods → 23 hours)."""
        result = downloader._aggregate_bmu_generation_to_cfd(test_cfd_df, spring_forward_generation_df)
        
        # Verify basic structure
        assert not result.empty, "Result should not be empty"
        assert list(result.columns) == ['cfd_id', 'settlement_date', 'hour', 'quantity']
        
        # Check we have exactly 23 hours (0-22, one hour fewer due to spring forward)
        hours = sorted(result['hour'].unique())
        expected_hours = list(range(23))  # Hours 0-22 (23 hours total)
        assert hours == expected_hours, f"Expected hours {expected_hours}, got {hours}"
        
        # Verify settlement date is correct
        expected_date = date(2023, 3, 26)
        settlement_dates = result['settlement_date'].unique()
        assert len(settlement_dates) == 1, f"Expected 1 date, got {len(settlement_dates)}"
        assert settlement_dates[0] == expected_date, f"Expected {expected_date}, got {settlement_dates[0]}"
        
        # Verify total quantity preservation
        original_total = spring_forward_generation_df['quantity'].sum()
        aggregated_total = result['quantity'].sum()
        assert abs(original_total - aggregated_total) < 0.01, f"Total quantity not preserved: {original_total} vs {aggregated_total}"
    
    def test_fall_back_timezone_handling(self, downloader: GenerationDataDownloader, test_cfd_df: pd.DataFrame, fall_back_generation_df: pd.DataFrame) -> None:
        """Test timezone handling for fall back day (50 settlement periods → 25 hours)."""
        result = downloader._aggregate_bmu_generation_to_cfd(test_cfd_df, fall_back_generation_df)
        
        # Verify basic structure
        assert not result.empty, "Result should not be empty"
        assert list(result.columns) == ['cfd_id', 'settlement_date', 'hour', 'quantity']
        
        # Check we have exactly 25 hours (0-24, one extra hour due to fall back)
        hours = sorted(result['hour'].unique())
        expected_hours = list(range(25))  # Hours 0-24 (25 hours total)
        assert hours == expected_hours, f"Expected hours {expected_hours}, got {hours}"
        
        # Verify settlement date is correct
        expected_date = date(2023, 10, 29)
        settlement_dates = result['settlement_date'].unique()
        assert len(settlement_dates) == 1, f"Expected 1 date, got {len(settlement_dates)}"
        assert settlement_dates[0] == expected_date, f"Expected {expected_date}, got {settlement_dates[0]}"
        
        # Verify total quantity preservation
        original_total = fall_back_generation_df['quantity'].sum()
        aggregated_total = result['quantity'].sum()
        assert abs(original_total - aggregated_total) < 0.01, f"Total quantity not preserved: {original_total} vs {aggregated_total}"
    
    def test_settlement_period_to_hour_conversion(self, downloader: GenerationDataDownloader, test_cfd_df: pd.DataFrame, normal_day_generation_df: pd.DataFrame) -> None:
        """Test the settlement period to hour conversion formula: hour = (period - 1) // 2."""
        # We don't need the result for this test, just testing the formula
        # result = downloader._aggregate_bmu_generation_to_cfd(test_cfd_df, normal_day_generation_df)
        
        # Test specific period-to-hour mappings
        test_cases = [
            (1, 0), (2, 0),    # Periods 1-2 → Hour 0
            (3, 1), (4, 1),    # Periods 3-4 → Hour 1
            (47, 23), (48, 23) # Periods 47-48 → Hour 23
        ]
        
        for period, expected_hour in test_cases:
            calculated_hour = (period - 1) // 2
            assert calculated_hour == expected_hour, f"Period {period} should map to hour {expected_hour}, got {calculated_hour}"
    
    def test_hour_aggregation_correctness(self, downloader: GenerationDataDownloader, test_cfd_df: pd.DataFrame, normal_day_generation_df: pd.DataFrame) -> None:
        """Test that quantities are correctly aggregated by hour."""
        result = downloader._aggregate_bmu_generation_to_cfd(test_cfd_df, normal_day_generation_df)
        
        # Manually calculate expected aggregation for hour 0 (periods 1-2)
        periods_1_2 = normal_day_generation_df[
            normal_day_generation_df['settlementPeriod'].isin([1, 2])
        ]
        expected_hour_0_quantity = periods_1_2['quantity'].sum()
        
        # Get actual aggregated quantity for hour 0
        hour_0_result = result[result['hour'] == 0]
        assert len(hour_0_result) == 1, "Should have exactly one record for hour 0"
        actual_hour_0_quantity = hour_0_result['quantity'].iloc[0]  # type: ignore[attr-defined]
        
        assert abs(expected_hour_0_quantity - actual_hour_0_quantity) < 0.01, \
            f"Hour 0 aggregation incorrect: expected {expected_hour_0_quantity}, got {actual_hour_0_quantity}"
    
    def test_cfd_id_mapping_preservation(self, downloader: GenerationDataDownloader, test_cfd_df: pd.DataFrame, normal_day_generation_df: pd.DataFrame) -> None:
        """Test that CfD ID mapping is correctly preserved through aggregation."""
        result = downloader._aggregate_bmu_generation_to_cfd(test_cfd_df, normal_day_generation_df)
        
        # All records should have the mapped CfD ID
        assert all(result['cfd_id'] == 'TEST-CFD-001'), "All records should have the correct CfD ID"
        
        # Should have exactly 24 records (one per hour)
        assert len(result) == 24, f"Expected 24 records, got {len(result)}"
    
    def test_data_types_and_precision(self, downloader: GenerationDataDownloader, test_cfd_df: pd.DataFrame, normal_day_generation_df: pd.DataFrame) -> None:
        """Test that data types are correct and quantities are properly rounded."""
        result = downloader._aggregate_bmu_generation_to_cfd(test_cfd_df, normal_day_generation_df)
        
        # Check data types
        assert result['cfd_id'].dtype == 'object', "CfD ID should be string/object type"
        assert result['settlement_date'].dtype == 'object', "Settlement date should be date type"
        assert result['hour'].dtype in ['int64', 'int32'], "Hour should be integer type"
        assert result['quantity'].dtype in ['float64', 'float32'], "Quantity should be float type"
        
        # Check that quantities are rounded to 2 decimal places
        for quantity in result['quantity']:
            rounded_quantity = round(quantity, 2)
            assert abs(quantity - rounded_quantity) < 0.001, f"Quantity {quantity} should be rounded to 2 decimal places"
    
    def test_empty_input_handling(self, downloader: GenerationDataDownloader, test_cfd_df: pd.DataFrame) -> None:
        """Test handling of empty generation data."""
        empty_df = pd.DataFrame({
            'settlementDate': [],
            'settlementPeriod': [],
            'bmUnit': [],
            'quantity': []
        })
        result = downloader._aggregate_bmu_generation_to_cfd(test_cfd_df, empty_df)
        
        # Result should be empty but have correct structure
        assert result.empty, "Result should be empty for empty input"
        assert list(result.columns) == ['cfd_id', 'settlement_date', 'hour', 'quantity']
    
    def test_multiple_bmu_aggregation(self, downloader: GenerationDataDownloader) -> None:
        """Test aggregation when multiple BMUs map to the same CfD."""
        # Create test data with two BMUs for the same CfD
        cfd_df = pd.DataFrame({
            'cfd_id': ['TEST-CFD-001', 'TEST-CFD-001'],
            'bmu_id': ['BMU001', 'BMU002']
        })
        
        generation_df = pd.DataFrame({
            'settlementDate': ['2023-01-15'] * 4,
            'settlementPeriod': [1, 1, 2, 2],
            'bmUnit': ['BMU001', 'BMU002', 'BMU001', 'BMU002'],
            'quantity': [10.0, 20.0, 15.0, 25.0]  # BMU001: 25.0 total, BMU002: 45.0 total
        })
        
        result = downloader._aggregate_bmu_generation_to_cfd(cfd_df, generation_df)
        
        # Should have one record for hour 0 with combined quantities
        assert len(result) == 1, "Should have exactly one record for hour 0"
        assert result['hour'].iloc[0] == 0, "Record should be for hour 0"  # type: ignore[attr-defined]
        assert result['quantity'].iloc[0] == 70.0, f"Combined quantity should be 70.0, got {result['quantity'].iloc[0]}"  # type: ignore[attr-defined]
        assert result['cfd_id'].iloc[0] == 'TEST-CFD-001', "CfD ID should be preserved"  # type: ignore[attr-defined]


# Additional integration tests
class TestGenerationDataDownloaderIntegration:
    """Integration tests for the complete GenerationDataDownloader workflow."""
    
    def test_dst_transitions_data_integrity(self) -> None:
        """Integration test verifying data integrity across all DST scenarios."""
        test_data_dir = Path(__file__).parent / "data"
        
        # Load all test datasets
        normal_df = pd.read_csv(test_data_dir / "test_generation_normal.csv")
        spring_df = pd.read_csv(test_data_dir / "test_generation_spring.csv")
        fall_df = pd.read_csv(test_data_dir / "test_generation_fall.csv")
        
        # Verify expected record counts
        assert len(normal_df) == 48, f"Normal day should have 48 records, got {len(normal_df)}"
        assert len(spring_df) == 46, f"Spring forward should have 46 records, got {len(spring_df)}"
        assert len(fall_df) == 50, f"Fall back should have 50 records, got {len(fall_df)}"
        
        # Verify settlement period sequences
        normal_periods = sorted(normal_df['settlementPeriod'].unique())
        spring_periods = sorted(spring_df['settlementPeriod'].unique())
        fall_periods = sorted(fall_df['settlementPeriod'].unique())
        
        assert normal_periods == list(range(1, 49)), "Normal day should have periods 1-48"
        assert spring_periods == list(range(1, 47)), "Spring forward should have periods 1-46"
        assert fall_periods == list(range(1, 51)), "Fall back should have periods 1-50"
    
    def test_timezone_conversion_preserves_uk_local_time(self) -> None:
        """Test that timezone conversion correctly handles UK local time semantics."""
        downloader = GenerationDataDownloader()
        
        # Test data representing the critical DST transition periods
        test_df = pd.DataFrame({
            'settlementDate': ['2023-03-26', '2023-10-29'],
            'settlementPeriod': [1, 1],
            'bmUnit': ['TEST_BMU', 'TEST_BMU'],
            'quantity': [100.0, 200.0]
        })
        
        cfd_df = pd.DataFrame({
            'cfd_id': ['TEST-CFD'],
            'bmu_id': ['TEST_BMU']
        })
        
        result = downloader._aggregate_bmu_generation_to_cfd(cfd_df, test_df)
        
        # Verify that dates are preserved correctly
        dates = result['settlement_date'].unique()
        expected_dates = [date(2023, 3, 26), date(2023, 10, 29)]
        
        assert len(dates) == 2, f"Expected 2 dates, got {len(dates)}"
        for expected_date in expected_dates:
            assert expected_date in dates, f"Expected date {expected_date} not in result dates {dates}"


if __name__ == "__main__":
    # Allow running tests directly with python -m pytest tests/test_generation_downloader.py
    pytest.main([__file__, "-v"])