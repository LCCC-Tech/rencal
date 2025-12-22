from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from weather.calibration.wind.wind_calibrator import WindCalibrator


@pytest.fixture(scope="class")
def temp_output_dir(tmp_path: Path):
    """Temporary output directory."""
    out_dir = tmp_path / "test_wind_calibrator_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir

@pytest.fixture(scope="class")
def data_dir():
    """Directory containing input data."""
    return Path(__file__).parents[1] / "data"


class TestWindCalibrator():
    """Tests WindCalibrator class."""

    @pytest.fixture
    def default_calibrator(self, temp_output_dir: Path, data_dir: Path) -> WindCalibrator:
        """Calibrator with default values."""
        return WindCalibrator(output_path=temp_output_dir, data_path=data_dir)

    @pytest.fixture
    def visual_calibrator(self, temp_output_dir: Path, data_dir: Path) -> WindCalibrator:
        "Calibrator with visual output turned on."
        return WindCalibrator(visual_output=True, output_path=temp_output_dir, data_path=data_dir)

    def test_wind_calibrator_default_init(self, default_calibrator):
        """Test default wind calibrator."""
        assert isinstance(default_calibrator.resource.data, xr.Dataset) is True
        assert isinstance(default_calibrator.generation.data, pd.DataFrame) is True
        assert isinstance(default_calibrator.plants.data, pd.DataFrame) is True

        assert default_calibrator.resource.metadata["source"] == "local_netcdf"
        assert default_calibrator.generation.metadata["source"] == "elexon_api"
        assert default_calibrator.plants.metadata["source"] == "local_excel"

        assert default_calibrator.visual_output is False

        assert default_calibrator.plants.data["technology"].unique().sort() == np.array(["Offshore Wind", "Onshore Wind"])

    def test_wind_calibrator_visual_init(self, visual_calibrator):
        """Test visual wind calibrator."""
        assert visual_calibrator.visual_output is True

    def test_wind_calibrator_default_extract_resource_timeseries_for_plants(self, default_calibrator):
        """Tests the extract_resource_timeseries_for_plants method."""
        resources_for_plants = default_calibrator.extract_resource_timeseries_for_plants()

        assert "time" in resources_for_plants.columns
        assert "wind_speed" in resources_for_plants.columns
        assert len(resources_for_plants) == len(default_calibrator.resource.time) * len(default_calibrator.plants.data)

    def test_wind_calibrator_default_get_plant_generation_temporal_bounds(self, default_calibrator):
        """Tests the _get_plant_generation_temporal_bounds method."""
        sample_gen_data = pd.DataFrame(
            {
                "plant_id": ["A", "A", "A", "B", "B", "B", "C", "C", "C"],
                "time": [datetime.strptime(dt, format="%Y-%m-%d %H:%M:%S") for dt in ["2000-12-12 01:00:00", "2000-12-12 02:00:00", "2000-12-12 03:00:00"]] * 3,
                "quantity": [1, 1, 1, 1, 1, 1, 1, 1, 1]
            }
        )

        sample_bounds = pd.DataFrame(
            {
                "plant_id": ["A", "B", "C"],
                "hourly_start": [datetime.strptime("2000-12-12 01:00:00", format="%Y-%m-%d %H:%M:%S")] * 3,
                "hourly_end": [datetime.strptime("2000-12-12 03:00:00", format="%Y-%m-%d %H:%M:%S")] * 3
            }
        )

        assert default_calibrator._get_plant_generation_temporal_bounds(sample_gen_data) == sample_bounds

    def test_wind_calibrator_default_clip_generation_to_plant_capacity(self, default_calibrator):
        """Tests the _clip_generation_to_plant_capacity method."""
        pass
