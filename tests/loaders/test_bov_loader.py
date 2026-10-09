"""Test local BOV loading, sparse event preservation, and dataset validation."""

from pathlib import Path

import pandas as pd
import pytest

from rencal.core.data_loader import LocalDataLoader
from rencal.models import BOVDatasetModel, GenerationDatasetModel
from rencal.utils.constants import BOV_DATA_FILE_NAME, GENERATION_DATA_FILE_NAME


@pytest.fixture
def sparse_bov_data() -> pd.DataFrame:
    """Create reported curtailment events with gaps between UTC timestamps."""
    return pd.DataFrame(
        {
            "cfd_id": ["WIND-001", "WIND-001", "WIND-002"],
            "time": pd.to_datetime(
                ["2023-01-01T00:00Z", "2023-01-03T04:00Z", "2023-01-01T00:00Z"],
                utc=True,
            ),
            "volume": [-5.0, -12.5, -8.0],
        }
    )


@pytest.fixture
def valid_bov_data(sparse_bov_data: pd.DataFrame) -> pd.DataFrame:
    """Use the internal plant identifier expected by the dataset model."""
    return sparse_bov_data.rename(columns={"cfd_id": "plant_id"})


class TestBOVDataLoader:
    def test_load_bov_data_success(self, tmp_path: Path, sparse_bov_data: pd.DataFrame) -> None:
        """Load only reported events, retaining their values and UTC timestamps."""
        output_file = tmp_path / "bov" / BOV_DATA_FILE_NAME
        output_file.parent.mkdir()
        sparse_bov_data.to_parquet(output_file, index=False)

        result = LocalDataLoader(data_path=str(tmp_path)).load_bov_data()

        assert isinstance(result, BOVDatasetModel)
        pd.testing.assert_frame_equal(
            result.data, sparse_bov_data.rename(columns={"cfd_id": "plant_id"})
        )
        assert list(result.data.columns) == ["plant_id", "time", "volume"]
        assert str(result.data["time"].dt.tz) == "UTC"
        assert not result.data["time"].eq(pd.Timestamp("2023-01-02T00:00Z")).any()
        assert result.metadata == {"source": "elexon_api", "aggregated": True}

    def test_load_bov_data_custom_id_column(
        self, tmp_path: Path, sparse_bov_data: pd.DataFrame
    ) -> None:
        """Rename a caller-selected plant ID column to the internal identifier."""
        output_file = tmp_path / "bov" / BOV_DATA_FILE_NAME
        output_file.parent.mkdir()
        sparse_bov_data.rename(columns={"cfd_id": "contract_id"}).to_parquet(
            output_file, index=False
        )

        result = LocalDataLoader(data_path=str(tmp_path)).load_bov_data(id_column="contract_id")

        pd.testing.assert_frame_equal(
            result.data, sparse_bov_data.rename(columns={"cfd_id": "plant_id"})
        )

    def test_load_bov_data_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="bov data file not found"):
            LocalDataLoader(data_path=str(tmp_path)).load_bov_data()

    def test_bov_dataset_validation_success(self, valid_bov_data: pd.DataFrame) -> None:
        dataset = BOVDatasetModel(data=valid_bov_data)

        pd.testing.assert_frame_equal(dataset.data, valid_bov_data)
        assert dataset.data["volume"].lt(0).all()

    @pytest.mark.parametrize("column", ["plant_id", "time", "volume"])
    def test_bov_dataset_validation_missing_columns(
        self, valid_bov_data: pd.DataFrame, column: str
    ) -> None:
        with pytest.raises(ValueError, match="Missing required columns"):
            BOVDatasetModel(data=valid_bov_data.drop(columns=[column]))

    def test_bov_dataset_validation_invalid_volume_type(self, valid_bov_data: pd.DataFrame) -> None:
        invalid_data = valid_bov_data.copy()
        invalid_data["volume"] = "not_a_number"

        with pytest.raises(ValueError, match="must be numeric"):
            BOVDatasetModel(data=invalid_data)

    def test_bov_dataset_validation_invalid_time_type(self, valid_bov_data: pd.DataFrame) -> None:
        invalid_data = valid_bov_data.copy()
        invalid_data["time"] = invalid_data["time"].astype(str)

        with pytest.raises(ValueError, match="must be datetime64"):
            BOVDatasetModel(data=invalid_data)

    def test_bov_dataset_methods(self, valid_bov_data: pd.DataFrame) -> None:
        dataset = BOVDatasetModel(data=valid_bov_data)

        assert set(dataset.get_plant_ids()) == {"WIND-001", "WIND-002"}
        filtered = dataset.filter_by_plant_id("WIND-001")
        assert isinstance(filtered, BOVDatasetModel)
        pd.testing.assert_frame_equal(
            filtered.data, valid_bov_data.loc[valid_bov_data["plant_id"] == "WIND-001"]
        )
        assert filtered.metadata["filtered_plant_id"] == "WIND-001"
        time_range = dataset.get_time_range()
        assert time_range is not None
        assert time_range["start"] == str(pd.Timestamp("2023-01-01T00:00Z"))
        assert time_range["end"] == str(pd.Timestamp("2023-01-03T04:00Z"))
        assert time_range["periods"] == 2

    def test_bov_dataset_date_filtering(self, valid_bov_data: pd.DataFrame) -> None:
        dataset = BOVDatasetModel(data=valid_bov_data)

        filtered = dataset.filter_by_date_range("2023-01-01", "2023-01-02")

        pd.testing.assert_frame_equal(filtered.data, valid_bov_data.iloc[[0, 2]])
        assert filtered.metadata["filtered_date_range"] == {
            "start": "2023-01-01",
            "end": "2023-01-02",
        }

    def test_bov_dataset_timezone_handling(self) -> None:
        data = pd.DataFrame(
            {
                "plant_id": ["WIND-001", "WIND-001"],
                "time": pd.to_datetime(["2023-10-29T00:00Z", "2023-10-29T01:00Z"], utc=True),
                "volume": [-3.0, -4.0],
            }
        )

        dataset = BOVDatasetModel(data=data)

        pd.testing.assert_frame_equal(dataset.data, data)
        assert str(dataset.data["time"].dt.tz) == "UTC"
        time_range = dataset.get_time_range()
        assert time_range is not None
        assert time_range["periods"] == 2


class TestDataLoaderIntegration:
    def test_load_generation_and_sparse_bov_together(
        self, tmp_path: Path, sparse_bov_data: pd.DataFrame
    ) -> None:
        """BOV remains sparse even when generation covers additional hours."""
        generation_data = pd.DataFrame(
            {
                "cfd_id": ["WIND-001"] * 3 + ["WIND-002"],
                "time": pd.to_datetime(
                    [
                        "2023-01-01T00:00Z",
                        "2023-01-02T00:00Z",
                        "2023-01-03T04:00Z",
                        "2023-01-01T00:00Z",
                    ],
                    utc=True,
                ),
                "quantity": [80.0, 90.0, 75.0, 120.0],
            }
        )
        (tmp_path / "generation").mkdir()
        (tmp_path / "bov").mkdir()
        generation_data.to_parquet(tmp_path / "generation" / GENERATION_DATA_FILE_NAME, index=False)
        sparse_bov_data.to_parquet(tmp_path / "bov" / BOV_DATA_FILE_NAME, index=False)
        loader = LocalDataLoader(data_path=str(tmp_path))

        generation = loader.load_generation_data()
        bov = loader.load_bov_data()

        assert isinstance(generation, GenerationDatasetModel)
        assert isinstance(bov, BOVDatasetModel)
        pd.testing.assert_frame_equal(
            generation.data, generation_data.rename(columns={"cfd_id": "plant_id"})
        )
        pd.testing.assert_frame_equal(
            bov.data, sparse_bov_data.rename(columns={"cfd_id": "plant_id"})
        )
        assert set(generation.get_plant_ids()) == set(bov.get_plant_ids())
        assert len(generation.data) == 4
        assert len(bov.data) == 3
