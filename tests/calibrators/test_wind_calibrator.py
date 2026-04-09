from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from weather.calibration.wind.wind_calibrator import WindCalibrator


@pytest.fixture
def temp_output_dir(tmp_path: Path):
    """Temporary output directory."""
    out_dir = tmp_path / "test_wind_calibrator_output"
    out_dir.mkdir(exist_ok=True)
    return out_dir


@pytest.fixture(scope="class")
def data_dir():
    """Directory containing input data."""
    return Path(__file__).parents[1] / "data"


class TestWindCalibrator:
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

        assert (
            np.array_equal(
                sorted(default_calibrator.plants.data["technology"].unique()),
                ["Offshore Wind", "Onshore Wind"],
            )
            is True
        )

    def test_wind_calibrator_visual_init(self, visual_calibrator):
        """Test visual wind calibrator."""
        assert visual_calibrator.visual_output is True

    def test_wind_calibrator_default_extract_resource_timeseries_for_plants(
        self, default_calibrator
    ):
        """Tests the extract_resource_timeseries_for_plants method."""
        resources_for_plants = default_calibrator.extract_resource_timeseries_for_plants()

        assert "time" in resources_for_plants.columns
        assert "wind_speed" in resources_for_plants.columns
        assert len(resources_for_plants) == len(default_calibrator.resource.data.time) * len(
            default_calibrator.plants.data
        )

    def test_wind_calibrator_default_get_plant_generation_temporal_bounds(self, default_calibrator):
        """Tests the _get_plant_generation_temporal_bounds method."""
        sample_gen_data = pd.DataFrame(
            {
                "plant_id": ["A", "A", "A", "B", "B", "B", "C", "C", "C"],
                "time": [
                    datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
                    for dt in ["2000-12-12 01:00:00", "2000-12-12 02:00:00", "2000-12-12 03:00:00"]
                ]
                * 3,
                "quantity": [1, 1, 1, 1, 1, 1, 1, 1, 1],
            }
        )

        sample_bounds = pd.DataFrame(
            {
                "plant_id": ["A", "B", "C"],
                "hourly_start": [datetime.strptime("2000-12-12 01:00:00", "%Y-%m-%d %H:%M:%S")] * 3,
                "hourly_end": [datetime.strptime("2000-12-12 03:00:00", "%Y-%m-%d %H:%M:%S")] * 3,
            }
        )

        assert default_calibrator._get_plant_generation_temporal_bounds(sample_gen_data).equals(
            sample_bounds
        )

    def test_wind_calibrator_default_remove_duplicate_plant_time_from_generation(
        self, default_calibrator
    ):
        """Tests the _remove_duplicate_plant_time_from_generation method."""
        duplicated_gen = pd.DataFrame(
            {
                "plant_id": ["A", "A", "B", "B"],
                "time": [datetime.strptime("2000-12-12 01:00:00", "%Y-%m-%d %H:%M:%S")] * 4,
                "quantity": [1, 3, 5, 7],
            }
        )
        expected_output = pd.DataFrame(
            {
                "plant_id": ["A", "B"],
                "time": [datetime.strptime("2000-12-12 01:00:00", "%Y-%m-%d %H:%M:%S")] * 2,
                "quantity": [4, 12],
            }
        )
        deduplicated_gen = default_calibrator._remove_duplicate_plant_time_from_generation(
            duplicated_gen
        )

        assert deduplicated_gen.equals(expected_output)

    def test_wind_calibrator_default_fit_weibull_dist_to_plant(self, default_calibrator):
        """Tests the _fit_weibull_dist_to_plant method."""
        assert default_calibrator._fit_weibull_dist_to_plant(
            ("A", np.array([1.0, 2.0], dtype=np.float32))
        ) == ("A", np.nan, np.nan)
        assert default_calibrator._fit_weibull_dist_to_plant(
            ("B", np.array([1.0, 2.0, 3.0], dtype=np.float32))
        ) == ("B", pytest.approx(2.738554), pytest.approx(2.258588))

    def test_wind_calibrator_default_logistic_function(self, default_calibrator):
        """Tests the logistic_function method."""
        assert default_calibrator.logistic_function(x=1.0, b=1.0, c=1.0, g=-3.0) == pytest.approx(
            -7.0
        )

    def test_wind_calibrator_default_drop_invalid_rows(self, default_calibrator):
        """Tests the _drop_invalid_rows method."""
        input_data = pd.DataFrame(
            {
                "plant_id": ["A", "B"],
                "wind_speed": [10, 20],
                "quantity": [0.3, -np.inf],
                "load_factor": [0.5, np.inf],
            }
        )
        expected_output = pd.DataFrame(
            {"plant_id": ["A"], "wind_speed": [10], "quantity": [0.3], "load_factor": [0.5]}
        )

        assert default_calibrator._drop_invalid_rows(input_data).equals(expected_output)

    def test_wind_calibrator_default_clip_extreme_wind_speeds(self, default_calibrator):
        """Tests the _clip_extreme_wind_speeds method."""
        input_data = pd.DataFrame({"plant_id": ["A", "B"], "wind_speed": [10, 50]})
        expected_output = pd.DataFrame({"plant_id": ["A", "B"], "wind_speed": [10, 40]})

        assert default_calibrator._replace_extreme_wind_speeds(input_data).equals(expected_output)


class TestWindCalibratorIntegration:
    """Integration test for wind calibration."""

    def test_calibration(self, temp_output_dir):
        """Tests the combined working of the modules through the calibrate method."""
        calibrator = WindCalibrator(
            data_path=Path(__file__).parents[1] / "data",
            output_path=temp_output_dir,
            visual_output=True,
            stream_npy_output=True,
        )

        # Initial values
        assert len(calibrator.plants.data) == 10
        assert calibrator.plants.data["capacity"].sum() == 1634.189
        assert len(calibrator.generation.data) == 26040
        assert len(calibrator.generation.data["plant_id"].unique()) == 35
        assert len(calibrator.resource.data.variables) == 5
        assert len(calibrator.resource.data.data_vars) == 2
        assert len(calibrator.resource.data.dims) == 3
        assert calibrator.output_path == temp_output_dir
        assert calibrator.visual_output is True
        assert calibrator.stream_npy_output is True

        calibrator.calibrate()

        # Post-calibration values
        assert len(calibrator.summary) == 8
        assert calibrator.summary.isna().values.any() == np.False_
        assert len(calibrator.wind_streams) == 24
        assert len(calibrator.wind_streams.columns) == 11
        assert calibrator.wind_streams.isna().values.any() == np.False_
        assert len(list(calibrator.output_path.glob("PowerCurveFit_*"))) == 6
        assert (calibrator.output_path / "Calibration Summary.csv").exists() is True
        assert (calibrator.output_path / "Weibull Params.csv").exists() is True
        assert (calibrator.output_path / "Wind Streams.parquet").exists() is True
        assert (calibrator.output_path / "Wind Streams.npy").exists() is True
        assert (calibrator.output_path / "Wind Speeds.csv").exists() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
