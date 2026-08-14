from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from commodity.nyiso import (
    NyisoLoadForecastClient,
    capture_p7_month,
    normalize_p7_archive,
)


def _forecast_csv(valid_day: str, values: list[float]) -> bytes:
    timestamps = pd.date_range(valid_day, periods=len(values), freq="h")
    frame = pd.DataFrame(
        {
            "Time Stamp": timestamps.strftime("%m/%d/%Y %H:%M"),
            "NYISO": values,
        }
    )
    return frame.to_csv(index=False).encode("utf-8")


def _archive_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        first = zipfile.ZipInfo("20240813isolf.csv", date_time=(2024, 8, 12, 7, 10, 0))
        archive.writestr(first, _forecast_csv("2024-08-14", [100.0, 120.0, 140.0]))
        second = zipfile.ZipInfo("20240814isolf.csv", date_time=(2024, 8, 13, 7, 20, 0))
        archive.writestr(second, _forecast_csv("2024-08-15", [110.0, 130.0, 150.0]))
    return buffer.getvalue()


def test_p7_client_uses_monthly_iso_load_forecast_archive() -> None:
    class Response:
        content = b"zip"

        def raise_for_status(self) -> None:
            pass

    class Session:
        def __init__(self) -> None:
            self.url: str | None = None

        def get(self, url: str, timeout: int) -> Response:
            self.url = url
            assert timeout == 60
            return Response()

    session = Session()
    payload, source_url = NyisoLoadForecastClient(session=session).fetch_month(2024, 8)
    assert payload == b"zip"
    assert source_url.endswith("/20240801isolf_csv.zip")
    assert session.url == source_url


def test_normalize_p7_archive_preserves_vintage_and_conservative_availability() -> None:
    frame = normalize_p7_archive(_archive_bytes(), archive_id="2024-08")
    assert list(frame["observed_for"].dt.date.astype(str)) == ["2024-08-13", "2024-08-14"]
    assert list(frame["forecast_valid_at"].dt.date.astype(str)) == ["2024-08-14", "2024-08-15"]
    assert frame.iloc[0]["issued_at"] == pd.Timestamp("2024-08-12T11:10:00Z")
    assert frame.iloc[0]["available_at"] == pd.Timestamp("2024-08-13T16:00:00Z")
    assert frame.iloc[0]["power_next_day_load_mean_mw"] == pytest.approx(120.0)
    assert frame.iloc[0]["power_next_day_load_max_mw"] == pytest.approx(140.0)
    assert frame.iloc[0]["power_next_day_load_min_mw"] == pytest.approx(100.0)
    assert frame["availability_status"].eq("reconstructed_conservative").all()
    assert frame["revision_status"].eq("issued_run_immutable").all()
    assert frame["source_member_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert frame["source_archive_id"].eq("2024-08").all()


def test_normalize_p7_archive_fails_closed_when_source_update_exceeds_noon_bound() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        late = zipfile.ZipInfo("20240813isolf.csv", date_time=(2024, 8, 13, 12, 30, 0))
        archive.writestr(late, _forecast_csv("2024-08-14", [100.0]))
    with pytest.raises(ValueError, match="later than conservative availability bound"):
        normalize_p7_archive(buffer.getvalue(), archive_id="2024-08")


def test_p7_snapshot_preserves_raw_archive_and_normalized_lineage(tmp_path: Path) -> None:
    class Client:
        def fetch_month(self, year: int, month: int) -> tuple[bytes, str]:
            assert (year, month) == (2024, 8)
            return _archive_bytes(), "https://mis.nyiso.com/public/csv/isolf/20240801isolf_csv.zip"

    manifest = capture_p7_month(
        Client(),
        2024,
        8,
        tmp_path,
        "202408-p7",
        "2026-08-14T02:00:00Z",
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["source_id"] == "nyiso_p7_iso_load_forecast"
    assert payload["point_in_time_backtest_ready"] is True
    assert payload["revision_status"] == "issued_run_immutable"
    assert payload["normalized_rows"] == 2
    assert {item["path"] for item in payload["artifacts"]} == {
        "archive.zip",
        "power_features.csv",
    }
