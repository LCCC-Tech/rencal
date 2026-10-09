"""Test BOV downloads with sparse curtailment events and mocked external inputs."""

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from rencal.core.data_downloader import BOVDataDownloader, DownloadManager


@pytest.fixture
def test_cfd_df() -> pd.DataFrame:
    """Create a CfD plant with its BMU mapping."""
    return pd.DataFrame(
        {"cfd_id": ["TEST-CFD-001"], "bmu_id": ["TEST-BMU-001"], "capacity": [100.0]}
    )


@pytest.fixture
def downloader_with_temp_dir(tmp_path: Path) -> BOVDataDownloader:
    """Keep downloader output isolated from committed fixtures."""
    downloader = BOVDataDownloader()
    downloader.output_dir = tmp_path
    return downloader


@pytest.fixture
def sparse_bov_df() -> pd.DataFrame:
    """Report two events separated by hours with no curtailment records."""
    return pd.DataFrame(
        {
            "settlementDate": ["2023-01-15"] * 3,
            "settlementPeriod": [1, 2, 9],
            "bmUnit": ["TEST-BMU-001"] * 3,
            "volume": [-2.0, -3.0, -4.0],
        }
    )


class TestBOVDataDownloader:
    @pytest.mark.parametrize(
        ("include_bov_data", "expected"),
        [(None, False), (False, False), (True, True)],
    )
    def test_download_manager_honors_bov_option(
        self, include_bov_data: bool | None, expected: bool, monkeypatch
    ) -> None:
        """Use the config default unless the caller explicitly selects a value."""
        monkeypatch.setattr("rencal.core.data_downloader.INCLUDE_BOV_DATA", False)
        manager = DownloadManager(include_bov_data=include_bov_data)
        with (
            patch.object(manager, "download_cfd"),
            patch.object(manager, "download_generation_data"),
            patch.object(manager, "download_bov_data") as download_bov,
            patch.object(manager, "download_era5"),
        ):
            manager.download_all()

        assert manager.include_bov_data is expected
        assert download_bov.called is expected

    @pytest.mark.parametrize(
        ("date", "periods", "expected_times", "expected_volumes"),
        [
            (
                "2023-01-15",
                [1, 2, 9, 48],
                ["2023-01-15T00:00Z", "2023-01-15T04:00Z", "2023-01-15T23:00Z"],
                [-3.0, -3.0, -4.0],
            ),
            (
                "2023-03-26",
                [1, 2, 9, 46],
                ["2023-03-26T00:00Z", "2023-03-26T04:00Z", "2023-03-26T22:00Z"],
                [-3.0, -3.0, -4.0],
            ),
            (
                "2023-10-29",
                [1, 2, 3, 4, 5, 6, 9, 50],
                [
                    "2023-10-28T23:00Z",
                    "2023-10-29T00:00Z",
                    "2023-10-29T01:00Z",
                    "2023-10-29T03:00Z",
                    "2023-10-29T23:00Z",
                ],
                [-3.0, -7.0, -11.0, -7.0, -8.0],
            ),
        ],
        ids=["normal-day", "spring-forward", "fall-back"],
    )
    def test_download_preserves_sparse_hours_and_utc_mapping(
        self,
        downloader_with_temp_dir: BOVDataDownloader,
        test_cfd_df: pd.DataFrame,
        date: str,
        periods: list[int],
        expected_times: list[str],
        expected_volumes: list[float],
        tmp_path: Path,
    ) -> None:
        """Aggregate only reported periods without filling missing UTC hours."""
        raw_data = pd.DataFrame(
            {
                "settlementDate": [date] * len(periods),
                "settlementPeriod": periods,
                "bmUnit": ["TEST-BMU-001"] * len(periods),
                "volume": [-float(index + 1) for index in range(len(periods))],
            }
        )
        with (
            patch.object(downloader_with_temp_dir, "_get_cfd_plants", return_value=test_cfd_df),
            patch.object(downloader_with_temp_dir, "_download_bov_data", return_value=raw_data),
        ):
            downloader_with_temp_dir.download()

        output_file = tmp_path / "bov" / "bov_data.parquet"
        assert output_file.exists()
        result = pd.read_parquet(output_file)
        assert list(result.columns) == ["cfd_id", "time", "volume"]
        assert result["cfd_id"].eq("TEST-CFD-001").all()
        assert str(result["time"].dt.tz) == "UTC"
        assert result["time"].tolist() == pd.to_datetime(expected_times, utc=True).tolist()
        assert result["volume"].tolist() == expected_volumes
        assert result["volume"].sum() == pytest.approx(raw_data["volume"].sum())
        assert not result.duplicated(["cfd_id", "time"]).any()
        assert len(result) < 23

    def test_download_skips_existing_file(
        self,
        downloader_with_temp_dir: BOVDataDownloader,
        test_cfd_df: pd.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Preserve the existing Parquet artifact without fetching BOV again."""
        output_file = tmp_path / "bov" / "bov_data.parquet"
        output_file.parent.mkdir()
        existing = pd.DataFrame(
            {
                "cfd_id": ["TEST-CFD-001"],
                "time": pd.to_datetime(["2023-01-15T00:00Z"], utc=True),
                "volume": [-5.0],
            }
        )
        existing.to_parquet(output_file, index=False)
        original_bytes = output_file.read_bytes()
        with (
            patch.object(downloader_with_temp_dir, "_get_cfd_plants", return_value=test_cfd_df),
            patch.object(downloader_with_temp_dir, "_download_bov_data") as mock_download,
        ):
            downloader_with_temp_dir.download()

        mock_download.assert_not_called()
        assert output_file.read_bytes() == original_bytes
        pd.testing.assert_frame_equal(pd.read_parquet(output_file), existing)

    def test_download_excludes_positive_hourly_volumes(
        self,
        downloader_with_temp_dir: BOVDataDownloader,
        test_cfd_df: pd.DataFrame,
        sparse_bov_df: pd.DataFrame,
    ) -> None:
        """Do not retain a positive offer-only hour as a curtailment event."""
        raw_data = sparse_bov_df.copy()
        raw_data.loc[raw_data["settlementPeriod"] == 9, "volume"] = 4.0
        with (
            patch.object(downloader_with_temp_dir, "_get_cfd_plants", return_value=test_cfd_df),
            patch.object(downloader_with_temp_dir, "_download_bov_data", return_value=raw_data),
        ):
            downloader_with_temp_dir.download()

        result = pd.read_parquet(downloader_with_temp_dir.output_dir / "bov_data.parquet")
        assert result["time"].tolist() == [pd.Timestamp("2023-01-15T00:00Z")]
        assert result["volume"].tolist() == [-5.0]

    def test_download_allocates_shared_bmu_by_capacity(
        self,
        downloader_with_temp_dir: BOVDataDownloader,
        sparse_bov_df: pd.DataFrame,
    ) -> None:
        """Preserve total curtailment when a BMU is shared by two plants."""
        plants = pd.DataFrame(
            {
                "cfd_id": ["TEST-CFD-001", "TEST-CFD-002"],
                "bmu_id": ["TEST-BMU-001"] * 2,
                "capacity": [25.0, 75.0],
            }
        )
        with (
            patch.object(downloader_with_temp_dir, "_get_cfd_plants", return_value=plants),
            patch.object(
                downloader_with_temp_dir, "_download_bov_data", return_value=sparse_bov_df
            ),
        ):
            downloader_with_temp_dir.download()

        result = pd.read_parquet(downloader_with_temp_dir.output_dir / "bov_data.parquet")
        assert len(result) == 4
        assert result.loc[result["cfd_id"] == "TEST-CFD-001", "volume"].tolist() == [-1.25, -1.0]
        assert result.loc[result["cfd_id"] == "TEST-CFD-002", "volume"].tolist() == [-3.75, -3.0]
        assert result["volume"].sum() == pytest.approx(sparse_bov_df["volume"].sum())

    def test_fetch_loops_over_dates_periods_and_bid_offer(
        self, downloader_with_temp_dir: BOVDataDownloader
    ) -> None:
        """Fetch both stacks for periods 1-50, keeping only relevant BMUs."""
        downloader = downloader_with_temp_dir
        downloader.bmu_ids = ["TEST-BMU-001"]
        columns = ["settlementDate", "settlementPeriod", "id", "volume"]

        def response_for_period(
            params: dict, columns: list[str], override_url: str
        ) -> pd.DataFrame:
            bid_offer, date, period = override_url.rsplit("/", 3)[-3:]
            assert params == {"format": "json"}
            if date == "2023-01-15" and period == "1":
                volume = -5.0 if bid_offer == "bid" else 1.0
                return pd.DataFrame(
                    [[date, 1, "TEST-BMU-001", volume], [date, 1, "OTHER-BMU", -99.0]],
                    columns=columns,
                )
            return pd.DataFrame(columns=columns)

        with (
            patch("rencal.core.data_downloader.CALIBRATION_START_DATE", "2023-01-15"),
            patch("rencal.core.data_downloader.CALIBRATION_END_DATE", "2023-01-16"),
            patch.object(
                downloader, "_download_data", side_effect=response_for_period
            ) as mock_fetch,
        ):
            result = downloader._download_bov_data()

        expected_urls = [
            f"{downloader._api.url}/{bid_offer}/{date}/{period}"
            for bid_offer in ["bid", "offer"]
            for date in ["2023-01-15", "2023-01-16"]
            for period in range(1, 51)
        ]
        assert [call.kwargs["override_url"] for call in mock_fetch.call_args_list] == expected_urls
        assert all(call.kwargs["columns"] == columns for call in mock_fetch.call_args_list)
        assert list(result.columns) == ["settlementDate", "settlementPeriod", "bmUnit", "volume"]
        assert result["bmUnit"].tolist() == ["TEST-BMU-001"]
        assert result["volume"].tolist() == [-4.0]
