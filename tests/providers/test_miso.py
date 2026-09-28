from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from commodity.miso import (
    MisoLoadForecastClient,
    _normalize_daily_sheet,
    audit_miso_window,
    capture_miso_month,
    capture_miso_window,
    load_miso_window,
    normalize_miso_archive,
)
from commodity.snapshots import SnapshotIntegrityError


def _daily_sheet(
    report_day: str,
    *,
    published_date: str | None = None,
    current_actual: object = "",
    duplicate_hour: bool = False,
) -> list[list[object]]:
    day = pd.Timestamp(report_day)
    prior = day - pd.Timedelta(days=1)
    rows: list[list[object]] = [
        ["FORECASTED AND"],
        ["ACTUAL LOAD REPORT"],
        ["Published Date:", "", published_date if published_date is not None else report_day],
        ["Reporting Period:", "", day.strftime("%m/%d/%Y"), "through", prior.strftime("%m/%d/%Y")],
        [],
        ["", "Market Day", "HourEnding", "North MTLF (MWh)", "North ActualLoad (MWh)",
         "Central MTLF (MWh)", "Central ActualLoad (MWh)", "South MTLF (MWh)",
         "South ActualLoad (MWh)", "MISO MTLF (MWh)", "MISO ActualLoad (MWh)"],
    ]
    for hour in range(1, 25):
        rows.append(["", prior.strftime("%m/%d/%Y"), hour, 10.0, 9.0, 20.0, 19.0,
                     30.0, 29.0, 60_000.0 + hour, 59_000.0 + hour])
    rows.extend([
        [],
        ["", "Market Day", "HourEnding", "North MTLF (MWh)", "North ActualLoad (MWh)",
         "Central MTLF (MWh)", "Central ActualLoad (MWh)", "South MTLF (MWh)",
         "South ActualLoad (MWh)", "MISO MTLF (MWh)", "MISO ActualLoad (MWh)"],
        [day.strftime("%B %d, %Y")],
    ])
    for hour in range(1, 25):
        current_hour = 23 if duplicate_hour and hour == 24 else hour
        rows.append([
            "", day.strftime("%m/%d/%Y"), current_hour,
            11.0, "", 21.0, "", 31.0, "",
            61_000.0 + hour, current_actual,
        ])
    return rows


def _archive_bytes(days: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for day in days:
            archive.writestr(f"{day.replace('-', '')}_rf_al.xls", f"fixture-{day}".encode())
    return buffer.getvalue()


def test_miso_client_uses_monthly_regional_forecast_archive() -> None:
    class Response:
        content = b"zip"
        def raise_for_status(self) -> None: pass

    class Session:
        def __init__(self) -> None: self.url: str | None = None
        def get(self, url: str, timeout: int) -> Response:
            self.url = url
            assert timeout == 60
            return Response()
    session = Session()
    payload, source_url = MisoLoadForecastClient(session=session).fetch_month(2011, 1)
    assert payload == b"zip"
    assert source_url == "https://docs.misoenergy.org/marketreports/201101_rf_al_xls.zip"
    assert session.url == source_url


def test_normal_daily_workbook_accepts_only_current_day_mtlf() -> None:
    frame, exclusion = _normalize_daily_sheet(
        _daily_sheet("2011-01-01"),
        datemode=0,
        source_member="20110101_rf_al.xls",
        archive_id="2011-01",
        member_sha256="a" * 64,
    )
    assert exclusion is None
    assert frame["observed_for"] == pd.Timestamp("2011-01-01T05:00:00Z")
    assert frame["available_at"] == pd.Timestamp("2011-01-02T05:00:00Z")
    assert frame["issued_load_level"] == pytest.approx(sum(61_000 + x for x in range(1, 25)) / 24)
    assert frame["source_id"] == "miso_daily_regional_forecast_actual_load_miso_mtlf_v1"
    assert frame["source_member"] == "20110101_rf_al.xls"
    assert frame["source_member_sha256"] == "a" * 64
    assert frame["forecast_hour_count"] == 24


def test_wrong_or_blank_publication_date_is_excluded() -> None:
    for published in ("", "2011-01-03"):
        frame, exclusion = _normalize_daily_sheet(
            _daily_sheet("2011-01-01", published_date=published),
            datemode=0,
            source_member="20110101_rf_al.xls",
            archive_id="2011-01",
            member_sha256="b" * 64,
        )
        assert frame is None
        assert exclusion is not None
        assert exclusion["source_member"] == "20110101_rf_al.xls"
        assert exclusion["reason"] == "invalid_or_mismatched_internal_published_date"


def test_misplaced_publication_date_is_excluded() -> None:
    rows = _daily_sheet("2011-05-04")
    rows[2][1] = rows[2][2]
    rows[2][2] = ""
    frame, exclusion = _normalize_daily_sheet(
        rows,
        datemode=0,
        source_member="20110504_rf_al.xls",
        archive_id="2011-05",
        member_sha256="c" * 64,
    )
    assert frame is None
    assert exclusion is not None
    assert exclusion["source_member"] == "20110504_rf_al.xls"
    assert exclusion["published_date"] is None
    assert exclusion["reason"] == "invalid_or_mismatched_internal_published_date"


def test_current_day_actual_load_leakage_is_rejected() -> None:
    with pytest.raises(ValueError, match="current-day actual load"):
        _normalize_daily_sheet(
            _daily_sheet("2020-01-01", current_actual=123.0),
            datemode=0,
            source_member="20200101_rf_al.xls",
            archive_id="2020-01",
            member_sha256="c" * 64,
        )


def test_duplicate_or_missing_current_day_hours_are_rejected() -> None:
    with pytest.raises(ValueError, match="24 unique current-day forecast hours"):
        _normalize_daily_sheet(
            _daily_sheet("2020-01-01", duplicate_hour=True),
            datemode=0,
            source_member="20200101_rf_al.xls",
            archive_id="2020-01",
            member_sha256="d" * 64,
        )


def test_fractional_current_day_hour_is_rejected() -> None:
    rows = _daily_sheet("2020-01-01")
    rows[-24][2] = 1.5
    with pytest.raises(ValueError, match="invalid hour/load"):
        _normalize_daily_sheet(
            rows,
            datemode=0,
            source_member="20200101_rf_al.xls",
            archive_id="2020-01",
            member_sha256="e" * 64,
        )


def test_archive_rejects_duplicate_report_days(monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _archive_bytes(["2020-01-01", "2020-01-01"])
    monkeypatch.setattr(
        "commodity.miso._read_xls_rows",
        lambda content: (_daily_sheet("2020-01-01"), 0),
    )
    with pytest.raises(ValueError, match="duplicate MISO report day"):
        normalize_miso_archive(archive, archive_id="2020-01")


def test_all_excluded_month_remains_loadable_and_auditable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _archive_bytes(["2020-01-01"])

    class Client:
        def fetch_month(self, year: int, month: int) -> tuple[bytes, str]:
            return archive, f"fixture://{year:04d}-{month:02d}"

    monkeypatch.setattr(
        "commodity.miso._read_xls_rows",
        lambda content: (_daily_sheet("2020-01-01", published_date="2020-01-02"), 0),
    )
    manifest = capture_miso_month(
        Client(),
        2020,
        1,
        tmp_path,
        "202001-rf-al",
        "2020-02-01T00:00:00Z",
    )
    persisted_exclusions = json.loads(
        (manifest.parent / "excluded_members.json").read_text(encoding="utf-8")
    )
    assert persisted_exclusions == [
        {
            "published_date": "2020-01-02",
            "reason": "invalid_or_mismatched_internal_published_date",
            "report_day": "2020-01-01",
            "source_member": "20200101_rf_al.xls",
            "source_member_sha256": hashlib.sha256(b"fixture-2020-01-01").hexdigest(),
        }
    ]
    frame = load_miso_window(tmp_path, "2020-01-01", "2020-01-01")
    assert frame.empty
    assert list(frame.columns) == [
        "observed_for",
        "available_at",
        "published_on",
        "forecast_valid_at",
        "issued_load_level",
        "issued_load_max",
        "issued_load_min",
        "forecast_hour_count",
        "availability_status",
        "availability_basis",
        "revision_status",
        "source_id",
        "source_archive_id",
        "source_member",
        "source_member_sha256",
    ]
    audit = audit_miso_window(tmp_path, "2020-01-01", "2020-01-01")
    assert audit["usable_day_count"] == 0
    assert audit["excluded_member_count"] == 1
    assert audit["research_pit_ready"] is True


def test_archive_normalization_preserves_member_hashes_and_exclusions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = _archive_bytes(["2020-01-01", "2020-01-02"])

    def fake_reader(content: bytes) -> tuple[list[list[object]], int]:
        day = content.decode().removeprefix("fixture-")
        published = day if day == "2020-01-01" else "2020-01-03"
        return _daily_sheet(day, published_date=published), 0

    monkeypatch.setattr("commodity.miso._read_xls_rows", fake_reader)
    frame, exclusions = normalize_miso_archive(archive, archive_id="2020-01")
    assert len(frame) == 1
    assert frame.iloc[0]["source_member"] == "20200101_rf_al.xls"
    expected_hash = hashlib.sha256(b"fixture-2020-01-01").hexdigest()
    assert frame.iloc[0]["source_member_sha256"] == expected_hash
    excluded_hash = hashlib.sha256(b"fixture-2020-01-02").hexdigest()
    assert exclusions == [{
        "source_member": "20200102_rf_al.xls",
        "source_member_sha256": excluded_hash,
        "report_day": "2020-01-02",
        "published_date": "2020-01-03",
        "reason": "invalid_or_mismatched_internal_published_date",
    }]


def test_capture_loader_and_audit_fail_closed_on_integrity_and_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Client:
        def fetch_month(self, year: int, month: int) -> tuple[bytes, str]:
            assert (year, month) == (2020, 1)
            return _archive_bytes(["2020-01-01", "2020-01-02"]), (
                "https://docs.misoenergy.org/marketreports/202001_rf_al_xls.zip"
            )

    monkeypatch.setattr(
        "commodity.miso._read_xls_rows",
        lambda content: (_daily_sheet(content.decode().removeprefix("fixture-")), 0),
    )
    manifest = capture_miso_month(
        Client(), 2020, 1, tmp_path, "202001-rf-al", "2026-09-27T08:00:00Z"
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["source_id"] == "miso_daily_regional_forecast_actual_load_miso_mtlf_v1"
    assert payload["archive_member_count"] == 2
    assert payload["usable_day_count"] == 2
    assert payload["excluded_member_count"] == 0
    assert payload["point_in_time_backtest_ready"] is True
    assert {item["path"] for item in payload["artifacts"]} == {
        "archive.zip", "excluded_members.json", "power_features.csv"
    }

    loaded = load_miso_window(tmp_path, "2020-01-01", "2020-01-02")
    assert len(loaded) == 2
    report = audit_miso_window(tmp_path, "2020-01-01", "2020-01-02")
    assert report["archive_month_count"] == 1
    assert report["calendar_day_count"] == 2
    assert report["usable_day_count"] == 2
    assert report["research_pit_ready"] is True

    archive_path = manifest.parent / "archive.zip"
    archive_path.write_bytes(archive_path.read_bytes() + b"corrupt")
    with pytest.raises(SnapshotIntegrityError, match="integrity"):
        load_miso_window(tmp_path, "2020-01-01", "2020-01-02")


def test_loader_rejects_source_identity_corruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Client:
        def fetch_month(self, year: int, month: int) -> tuple[bytes, str]:
            return _archive_bytes(["2020-01-01"]), "https://example.test/miso.zip"

    monkeypatch.setattr(
        "commodity.miso._read_xls_rows",
        lambda content: (_daily_sheet("2020-01-01"), 0),
    )
    manifest = capture_miso_month(
        Client(), 2020, 1, tmp_path, "202001-rf-al", "2026-09-27T08:00:00Z"
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["source_id"] = "wrong-source"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="source identity mismatch"):
        load_miso_window(tmp_path, "2020-01-01", "2020-01-01")


def test_window_detects_missing_calendar_days(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Client:
        def fetch_month(self, year: int, month: int) -> tuple[bytes, str]:
            return _archive_bytes(["2020-01-01", "2020-01-03"]), "https://example.test/miso.zip"

    monkeypatch.setattr(
        "commodity.miso._read_xls_rows",
        lambda content: (_daily_sheet(content.decode().removeprefix("fixture-")), 0),
    )
    capture_miso_month(
        Client(), 2020, 1, tmp_path, "202001-rf-al", "2026-09-27T08:00:00Z"
    )
    with pytest.raises(ValueError, match="daily report coverage"):
        load_miso_window(tmp_path, "2020-01-01", "2020-01-03")


def test_window_capture_is_resumable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Client:
        def __init__(self) -> None: self.calls = 0
        def fetch_month(self, year: int, month: int) -> tuple[bytes, str]:
            self.calls += 1
            return _archive_bytes(["2020-01-01"]), "https://example.test/miso.zip"

    monkeypatch.setattr(
        "commodity.miso._read_xls_rows",
        lambda content: (_daily_sheet("2020-01-01"), 0),
    )
    client = Client()
    first = capture_miso_window(client, "2020-01-01", "2020-01-01", tmp_path, "2026-09-27T08:00:00Z")
    second = capture_miso_window(client, "2020-01-01", "2020-01-01", tmp_path, "2026-09-27T09:00:00Z")
    assert first == second
    assert client.calls == 1


def test_loader_recomputes_member_hash_from_archived_workbook(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Client:
        def fetch_month(self, year: int, month: int) -> tuple[bytes, str]:
            return _archive_bytes(["2020-01-01"]), "https://example.test/miso.zip"

    monkeypatch.setattr(
        "commodity.miso._read_xls_rows",
        lambda content: (_daily_sheet("2020-01-01"), 0),
    )
    manifest = capture_miso_month(
        Client(), 2020, 1, tmp_path, "202001-rf-al", "2026-09-27T08:00:00Z"
    )
    features_path = manifest.parent / "power_features.csv"
    frame = pd.read_csv(features_path)
    frame.loc[0, "source_member_sha256"] = "f" * 64
    payload_bytes = frame.to_csv(index=False).encode()
    features_path.write_bytes(payload_bytes)

    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    artifact = next(item for item in metadata["artifacts"] if item["path"] == "power_features.csv")
    artifact["bytes"] = len(payload_bytes)
    artifact["sha256"] = hashlib.sha256(payload_bytes).hexdigest()
    manifest.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="member hash lineage mismatch"):
        load_miso_window(tmp_path, "2020-01-01", "2020-01-01")
