from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rencal.calibration.solar.solar_calibrator import SolarCalibrator
from rencal.utils.constants import INTERNAL_PLANT_ID, PLANT_ID_OUTPUT


@pytest.fixture
def output_calibrator(tmp_path: Path) -> SolarCalibrator:
    """Isolate output writers from calibration input loading and external data."""
    calibrator = SolarCalibrator.__new__(SolarCalibrator)
    calibrator.output_path = tmp_path
    return calibrator


@pytest.mark.parametrize(
    ("method", "attribute", "filename"),
    [
        (
            "output_resource_per_plant",
            "plant_irradiance",
            "solar_resource.csv",
        ),
        (
            "output_historical_load_factor_distribution_parameters",
            "historical_load_factor_distributions",
            "solar_distribution_params.csv",
        ),
        (
            "output_estimated_load_factors_tabular",
            "summary",
            "solar_calibration_summary.csv",
        ),
    ],
)
def test_csv_output_names(output_calibrator, method, attribute, filename):
    """CSV writers use snake_case filenames without changing their data."""
    data = pd.DataFrame({"plant_id": ["AR4-BSP-700"], "value": [0.25]})
    setattr(output_calibrator, attribute, data)

    getattr(output_calibrator, method)()

    assert {path.name for path in output_calibrator.output_path.iterdir()} == {filename}
    pd.testing.assert_frame_equal(pd.read_csv(output_calibrator.output_path / filename), data)


@pytest.mark.parametrize("npy_output", [False, True])
def test_stream_output_names(output_calibrator, npy_output):
    """Parquet and optional NPY outputs share the snake_case basename."""
    output_calibrator.stream_npy_output = npy_output
    output_calibrator.solar_streams = pd.DataFrame(
        {
            "Times": pd.date_range("2025-01-01", periods=2, freq="h", tz="UTC"),
            "AR4-BSP-700": [0.0, 0.25],
        }
    )

    output_calibrator.output_resource_streams()

    expected_names = {"solar_streams.parquet"}
    if npy_output:
        expected_names.add("solar_streams.npy")
        streams = np.load(output_calibrator.output_path / "solar_streams.npy")
        np.testing.assert_array_equal(streams, np.array([[0.0], [0.25]], dtype=np.float32))
        assert streams.dtype == np.float32
    assert {path.name for path in output_calibrator.output_path.iterdir()} == expected_names
    pd.testing.assert_frame_equal(
        pd.read_parquet(output_calibrator.output_path / "solar_streams.parquet"),
        output_calibrator.solar_streams,
    )


def test_plot_output_name(output_calibrator):
    """Plot prefixes use snake_case while preserving the original plant ID."""
    load_factors = pd.DataFrame(
        {
            INTERNAL_PLANT_ID: ["AR4-BSP-700"] * 3,
            "irradiance": [0.0, 400.0, 800.0],
            "temperature": [20.0, 21.0, 22.0],
            "load_factor": [0.0, 0.35, 0.7],
        }
    )

    output_calibrator.output_estimated_load_factors_visual(np.array([0.004, 40.0]), load_factors)

    assert {path.name for path in output_calibrator.output_path.iterdir()} == {
        "pv_curve_fit_AR4-BSP-700.png"
    }
    assert (output_calibrator.output_path / "pv_curve_fit_AR4-BSP-700.png").stat().st_size > 0


def test_summary_column_names_unchanged(output_calibrator):
    """Filename changes must not alter the existing summary schema."""
    output_calibrator.summary = pd.DataFrame(
        {
            INTERNAL_PLANT_ID: ["AR4-BSP-700"],
            "gamma": [0.004],
            "NOCT": [40.0],
            "estimated_load_factor": [0.25],
        }
    )

    output_calibrator._rename_output_summary_columns()

    assert list(output_calibrator.summary.columns) == [
        PLANT_ID_OUTPUT,
        "Gamma",
        "NOCT",
        "Estimated Load Factor",
    ]
