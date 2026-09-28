from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests
import xlrd

from commodity.snapshots import SnapshotWriter, verify_snapshot

_SOURCE_ID = "miso_daily_regional_forecast_actual_load_miso_mtlf_v1"
_MEMBER_RE = re.compile(r"^(?P<day>\d{8})_rf_al\.xls$", re.IGNORECASE)
_FIXED_EST = dt.timezone(dt.timedelta(hours=-5), name="EST")
_FORECAST_HEADERS = {
    "midwest iso mtlf (mwh)",
    "miso mtlf (mwh)",
    "miso iso mtlf (mwh)",
}
_ACTUAL_HEADERS = {
    "midwest iso actualload (mwh)",
    "miso actualload (mwh)",
    "miso iso actualload (mwh)",
}
_NORMALIZED_COLUMNS = (
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
)


@dataclass
class MisoLoadForecastClient:
    session: requests.Session | None = None

    def fetch_month(self, year: int, month: int) -> tuple[bytes, str]:
        url = f"https://docs.misoenergy.org/marketreports/{year:04d}{month:02d}_rf_al_xls.zip"
        response = (self.session or requests.Session()).get(url, timeout=60)
        try:
            response.raise_for_status()
        except requests.RequestException:
            status = getattr(response, "status_code", "unknown")
            raise RuntimeError(f"MISO archive request failed with HTTP {status}") from None
        return response.content, url


def _member_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _parse_date(value: object, *, datemode: int) -> dt.date | None:
    if _is_blank(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return xlrd.xldate_as_datetime(float(value), datemode).date()
        except (ValueError, TypeError, OverflowError):
            return None
    parsed = pd.to_datetime(str(value).strip(), errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _read_xls_rows(content: bytes) -> tuple[list[list[object]], int]:
    try:
        workbook = xlrd.open_workbook(file_contents=content)
    except (xlrd.XLRDError, ValueError) as exc:
        raise ValueError("MISO daily member is not a readable XLS workbook") from exc
    if workbook.nsheets != 1:
        raise ValueError("MISO daily workbook must contain exactly one worksheet")
    sheet = workbook.sheet_by_index(0)
    rows = [
        [sheet.cell_value(row, column) for column in range(sheet.ncols)]
        for row in range(sheet.nrows)
    ]
    return rows, workbook.datemode


def _row_value(row: list[object], index: int) -> object:
    return row[index] if index < len(row) else ""


def _find_labeled_dates(
    rows: list[list[object]], label: str, *, datemode: int
) -> list[dt.date]:
    wanted = label.strip().lower()
    for row in rows:
        for index, value in enumerate(row):
            if str(value).strip().lower() != wanted:
                continue
            return [
                parsed
                for candidate in row[index + 1 :]
                if (parsed := _parse_date(candidate, datemode=datemode)) is not None
            ]
    return []


def _find_labeled_date(
    rows: list[list[object]], label: str, *, datemode: int
) -> dt.date | None:
    dates = _find_labeled_dates(rows, label, datemode=datemode)
    return dates[0] if dates else None


def _find_labeled_date_at_offset(
    rows: list[list[object]], label: str, *, offset: int, datemode: int
) -> dt.date | None:
    wanted = label.strip().lower()
    for row in rows:
        for index, value in enumerate(row):
            if str(value).strip().lower() != wanted:
                continue
            return _parse_date(_row_value(row, index + offset), datemode=datemode)
    return None


def _header_indexes(row: list[object]) -> tuple[int, int, int, int] | None:
    normalized = [str(value).strip().lower() for value in row]
    if "market day" not in normalized or "hourending" not in normalized:
        return None
    forecast = [index for index, value in enumerate(normalized) if value in _FORECAST_HEADERS]
    actual = [index for index, value in enumerate(normalized) if value in _ACTUAL_HEADERS]
    if len(forecast) != 1 or len(actual) != 1:
        raise ValueError("MISO daily workbook lacks an unambiguous MISO-wide forecast/actual header")
    return normalized.index("market day"), normalized.index("hourending"), forecast[0], actual[0]


def _fixed_est_midnight(day: dt.date) -> pd.Timestamp:
    return pd.Timestamp(dt.datetime.combine(day, dt.time.min, tzinfo=_FIXED_EST)).tz_convert("UTC")


def _normalize_daily_sheet(
    rows: list[list[object]],
    *,
    datemode: int,
    source_member: str,
    archive_id: str,
    member_sha256: str,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    match = _MEMBER_RE.match(Path(source_member).name)
    if match is None:
        raise ValueError(f"invalid MISO daily member identity: {source_member}")
    raw_day = match.group("day")
    report_day = dt.date(int(raw_day[:4]), int(raw_day[4:6]), int(raw_day[6:]))
    if archive_id != f"{report_day.year:04d}-{report_day.month:02d}":
        raise ValueError("MISO member month does not match archive identity")
    published = _find_labeled_date_at_offset(
        rows, "Published Date:", offset=2, datemode=datemode
    )
    if published != report_day:
        return None, {
            "source_member": Path(source_member).name,
            "source_member_sha256": member_sha256,
            "report_day": report_day.isoformat(),
            "published_date": None if published is None else published.isoformat(),
            "reason": "invalid_or_mismatched_internal_published_date",
        }
    reporting_days = _find_labeled_dates(rows, "Reporting Period:", datemode=datemode)
    if report_day not in reporting_days:
        raise ValueError("MISO internal reporting-period day does not match member identity")

    current_rows: list[tuple[int, float]] = []
    current_actual_values: list[object] = []
    active_header: tuple[int, int, int, int] | None = None
    for row in rows:
        header = _header_indexes(row)
        if header is not None:
            active_header = header
            continue
        if active_header is None:
            continue
        market_index, hour_index, forecast_index, actual_index = active_header
        market_day = _parse_date(_row_value(row, market_index), datemode=datemode)
        if market_day != report_day:
            continue
        hour_raw = _row_value(row, hour_index)
        forecast_raw = _row_value(row, forecast_index)
        try:
            hour_value = float(hour_raw)
            forecast = float(forecast_raw)
        except (TypeError, ValueError):
            raise ValueError("MISO current-day forecast row contains invalid hour/load") from None
        if not math.isfinite(hour_value) or not hour_value.is_integer():
            raise ValueError("MISO current-day forecast row contains invalid hour/load")
        hour = int(hour_value)
        if not math.isfinite(forecast) or forecast <= 0.0:
            raise ValueError("MISO current-day forecast load must be positive and finite")
        current_rows.append((hour, forecast))
        current_actual_values.append(_row_value(row, actual_index))

    hours = [hour for hour, _ in current_rows]
    if len(hours) != 24 or set(hours) != set(range(1, 25)):
        raise ValueError("MISO daily workbook must contain 24 unique current-day forecast hours")
    if any(not _is_blank(value) for value in current_actual_values):
        raise ValueError("MISO current-day actual load must be absent to prevent leakage")
    forecasts = [value for _, value in sorted(current_rows)]
    observed_for = _fixed_est_midnight(report_day)
    available_at = _fixed_est_midnight(report_day + dt.timedelta(days=1))
    return {
        "observed_for": observed_for,
        "available_at": available_at,
        "published_on": report_day.isoformat(),
        "forecast_valid_at": observed_for,
        "issued_load_level": float(sum(forecasts) / len(forecasts)),
        "issued_load_max": float(max(forecasts)),
        "issued_load_min": float(min(forecasts)),
        "forecast_hour_count": len(forecasts),
        "availability_status": "reconstructed_conservative",
        "availability_basis": "miso_internal_published_date_plus_one_day_0000_fixed_est",
        "revision_status": "single_daily_issue_same_target_revision_not_identifiable",
        "source_id": _SOURCE_ID,
        "source_archive_id": archive_id,
        "source_member": Path(source_member).name,
        "source_member_sha256": member_sha256,
    }, None


def normalize_miso_archive(
    content: bytes, *, archive_id: str
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    exclusions: list[dict[str, object]] = []
    seen_days: set[str] = set()
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ValueError("MISO monthly archive is not a valid ZIP") from exc
    with archive:
        members = [
            info for info in archive.infolist()
            if not info.is_dir() and _MEMBER_RE.match(Path(info.filename).name)
        ]
        if not members:
            raise ValueError("MISO monthly archive contains no daily forecast workbooks")
        for info in sorted(members, key=lambda item: Path(item.filename).name):
            name = Path(info.filename).name
            match = _MEMBER_RE.match(name)
            assert match is not None
            day = match.group("day")
            report_day = f"{day[:4]}-{day[4:6]}-{day[6:]}"
            if report_day in seen_days:
                raise ValueError(f"duplicate MISO report day in archive: {report_day}")
            seen_days.add(report_day)
            member_bytes = archive.read(info)
            sheet_rows, datemode = _read_xls_rows(member_bytes)
            normalized, exclusion = _normalize_daily_sheet(
                sheet_rows,
                datemode=datemode,
                source_member=name,
                archive_id=archive_id,
                member_sha256=_member_sha256(member_bytes),
            )
            if exclusion is not None:
                exclusions.append(exclusion)
            elif normalized is not None:
                rows.append(normalized)
    frame = pd.DataFrame(rows, columns=_NORMALIZED_COLUMNS)
    if not frame.empty:
        frame = frame.sort_values("observed_for", kind="stable").reset_index(drop=True)
        if frame["observed_for"].duplicated().any():
            raise ValueError("MISO normalized archive contains duplicate report days")
        if frame["available_at"].duplicated().any():
            raise ValueError("MISO normalized archive contains duplicate availability timestamps")
    return frame, exclusions


def _month_starts(start: str | pd.Timestamp, end: str | pd.Timestamp) -> pd.DatetimeIndex:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if end_ts < start_ts:
        raise ValueError("MISO window end must not precede start")
    if start_ts.tzinfo is not None:
        start_ts = start_ts.tz_localize(None)
    if end_ts.tzinfo is not None:
        end_ts = end_ts.tz_localize(None)
    first = start_ts.to_period("M").to_timestamp()
    last = end_ts.to_period("M").to_timestamp()
    return pd.date_range(first, last, freq="MS")


def _month_snapshot_id(year: int, month: int) -> str:
    return f"{year:04d}{month:02d}-rf-al"


def capture_miso_month(
    client: MisoLoadForecastClient,
    year: int,
    month: int,
    snapshot_root: Path,
    snapshot_id: str,
    retrieved_at: str,
) -> Path:
    content, source_url = client.fetch_month(year, month)
    archive_id = f"{year:04d}-{month:02d}"
    frame, exclusions = normalize_miso_archive(content, archive_id=archive_id)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        archive_member_count = sum(
            1
            for info in archive.infolist()
            if not info.is_dir() and _MEMBER_RE.match(Path(info.filename).name)
        )
    writer = SnapshotWriter(Path(snapshot_root), "miso_rf_al", snapshot_id)
    writer.write_bytes("archive.zip", content)
    writer.write_bytes("power_features.csv", frame.to_csv(index=False).encode("utf-8"))
    writer.write_bytes(
        "excluded_members.json",
        (json.dumps(exclusions, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return writer.finalize(
        {
            "source_id": _SOURCE_ID,
            "source_url": source_url,
            "archive_id": archive_id,
            "retrieved_at": retrieved_at,
            "archive_member_count": archive_member_count,
            "usable_day_count": len(frame),
            "excluded_member_count": len(exclusions),
            "availability_status": "reconstructed_conservative",
            "availability_basis": "miso_internal_published_date_plus_one_day_0000_fixed_est",
            "revision_status": "single_daily_issue_same_target_revision_not_identifiable",
            "point_in_time_backtest_ready": True,
        }
    )


def capture_miso_window(
    client: MisoLoadForecastClient,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    snapshot_root: Path,
    retrieved_at: str,
) -> list[Path]:
    root = Path(snapshot_root)
    manifests: list[Path] = []
    for month_start in _month_starts(start, end):
        year = int(month_start.year)
        month = int(month_start.month)
        snapshot_id = _month_snapshot_id(year, month)
        manifest = root / "miso_rf_al" / snapshot_id / "manifest.json"
        if manifest.exists():
            verify_snapshot(manifest)
            manifests.append(manifest)
            continue
        manifests.append(
            capture_miso_month(
                client, year, month, root, snapshot_id, retrieved_at
            )
        )
    return manifests


def _archive_member_hashes(archive_path: Path) -> dict[str, str]:
    try:
        archive = zipfile.ZipFile(archive_path)
    except zipfile.BadZipFile as exc:
        raise ValueError("MISO preserved monthly archive is not a valid ZIP") from exc
    hashes: dict[str, str] = {}
    with archive:
        for info in archive.infolist():
            if info.is_dir() or _MEMBER_RE.match(Path(info.filename).name) is None:
                continue
            name = Path(info.filename).name
            if name in hashes:
                raise ValueError(f"duplicate MISO member identity in preserved archive: {name}")
            hashes[name] = _member_sha256(archive.read(info))
    if not hashes:
        raise ValueError("MISO preserved monthly archive contains no daily forecast workbooks")
    return hashes


def _load_month_snapshot(
    manifest: Path,
    *,
    expected_archive_id: str,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    verify_snapshot(manifest)
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    if metadata.get("source_id") != _SOURCE_ID:
        raise ValueError(f"MISO snapshot source identity mismatch: {manifest.parent.name}")
    if metadata.get("archive_id") != expected_archive_id:
        raise ValueError(f"MISO snapshot archive identity mismatch: {manifest.parent.name}")
    if metadata.get("point_in_time_backtest_ready") is not True:
        raise ValueError(f"MISO snapshot is not research-PIT ready: {manifest.parent.name}")
    frame = pd.read_csv(
        manifest.parent / "power_features.csv",
        parse_dates=["observed_for", "available_at", "forecast_valid_at"],
    )
    exclusions = json.loads(
        (manifest.parent / "excluded_members.json").read_text(encoding="utf-8")
    )
    if not isinstance(exclusions, list):
        raise TypeError("MISO exclusion evidence is invalid")
    if len(frame) != int(metadata.get("usable_day_count", -1)):
        raise ValueError("MISO normalized row count differs from manifest")
    if len(exclusions) != int(metadata.get("excluded_member_count", -1)):
        raise ValueError("MISO exclusion count differs from manifest")
    if int(metadata.get("archive_member_count", -1)) != len(frame) + len(exclusions):
        raise ValueError("MISO archive member accounting is inconsistent")
    if any(
        not isinstance(item, dict)
        or re.fullmatch(r"[0-9a-f]{64}", str(item.get("source_member_sha256", ""))) is None
        for item in exclusions
    ):
        raise ValueError("MISO excluded-member lineage is invalid")
    archive_hashes = _archive_member_hashes(manifest.parent / "archive.zip")
    if len(archive_hashes) != int(metadata.get("archive_member_count", -1)):
        raise ValueError("MISO preserved archive member count differs from manifest")
    accepted_lineage = {
        str(row.source_member): str(row.source_member_sha256)
        for row in frame[["source_member", "source_member_sha256"]].itertuples(index=False)
    }
    excluded_lineage = {
        str(item["source_member"]): str(item["source_member_sha256"])
        for item in exclusions
    }
    if len(accepted_lineage) != len(frame) or len(excluded_lineage) != len(exclusions):
        raise ValueError("MISO snapshot contains duplicate member lineage identities")
    if set(accepted_lineage) & set(excluded_lineage):
        raise ValueError("MISO member identity appears in both accepted and excluded evidence")
    recorded_lineage = accepted_lineage | excluded_lineage
    if set(recorded_lineage) != set(archive_hashes) or any(
        recorded_lineage[name] != archive_hashes[name] for name in archive_hashes
    ):
        raise ValueError("MISO member hash lineage mismatch against preserved archive")
    if not frame.empty:
        if not frame["source_id"].astype(str).eq(_SOURCE_ID).all():
            raise ValueError("MISO normalized source identity mismatch")
        if not frame["source_member_sha256"].astype(str).str.fullmatch(r"[0-9a-f]{64}").all():
            raise ValueError("MISO normalized member lineage is invalid")
        if not frame["forecast_hour_count"].eq(24).all():
            raise ValueError("MISO normalized forecast-hour coverage is invalid")
        if frame["observed_for"].duplicated().any() or frame["available_at"].duplicated().any():
            raise ValueError("MISO normalized snapshot contains duplicate days")
    return frame, exclusions


def load_miso_window(
    snapshot_root: Path,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
) -> pd.DataFrame:
    root = Path(snapshot_root)
    frames: list[pd.DataFrame] = []
    covered_days: list[str] = []
    for month_start in _month_starts(start, end):
        year = int(month_start.year)
        month = int(month_start.month)
        snapshot_id = _month_snapshot_id(year, month)
        manifest = root / "miso_rf_al" / snapshot_id / "manifest.json"
        if not manifest.is_file():
            raise ValueError(f"MISO missing monthly snapshot: {year:04d}-{month:02d}")
        frame, exclusions = _load_month_snapshot(
            manifest, expected_archive_id=f"{year:04d}-{month:02d}"
        )
        if not frame.empty:
            frames.append(frame)
            covered_days.extend(
                frame["observed_for"]
                .dt.tz_convert(_FIXED_EST)
                .dt.date.astype(str)
                .tolist()
            )
        covered_days.extend(str(item["report_day"]) for item in exclusions)
    start_date = pd.Timestamp(start).date()
    end_date = pd.Timestamp(end).date()
    expected = [value.date().isoformat() for value in pd.date_range(start_date, end_date, freq="D")]
    requested_coverage = sorted(
        day for day in covered_days if start_date <= dt.date.fromisoformat(day) <= end_date
    )
    if requested_coverage != expected:
        raise ValueError("MISO daily report coverage is incomplete or duplicated")
    if not frames:
        return pd.DataFrame(columns=_NORMALIZED_COLUMNS)
    result = pd.concat(frames, ignore_index=True)
    local_dates = result["observed_for"].dt.tz_convert(_FIXED_EST).dt.date
    result = result.loc[(local_dates >= start_date) & (local_dates <= end_date)].copy()
    result = result.sort_values("available_at", kind="stable").reset_index(drop=True)
    if result["observed_for"].duplicated().any():
        raise ValueError("MISO accepted window contains duplicate report days")
    return result


def audit_miso_window(
    snapshot_root: Path,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
) -> dict[str, object]:
    frame = load_miso_window(snapshot_root, start, end)
    root = Path(snapshot_root)
    exclusions: list[dict[str, object]] = []
    archive_member_count = 0
    for month_start in _month_starts(start, end):
        year = int(month_start.year)
        month = int(month_start.month)
        manifest = root / "miso_rf_al" / _month_snapshot_id(year, month) / "manifest.json"
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        archive_member_count += int(metadata["archive_member_count"])
        exclusions.extend(
            json.loads((manifest.parent / "excluded_members.json").read_text(encoding="utf-8"))
        )
    start_date = pd.Timestamp(start).date()
    end_date = pd.Timestamp(end).date()
    relevant_exclusions = [
        item
        for item in exclusions
        if start_date <= dt.date.fromisoformat(str(item["report_day"])) <= end_date
    ]
    calendar_day_count = len(pd.date_range(start_date, end_date, freq="D"))
    accepted_hashes_valid = bool(
        frame.empty
        or frame["source_member_sha256"].astype(str).str.fullmatch(r"[0-9a-f]{64}").all()
    )
    excluded_hashes_valid = all(
        isinstance(item, dict)
        and re.fullmatch(r"[0-9a-f]{64}", str(item.get("source_member_sha256", ""))) is not None
        for item in relevant_exclusions
    )
    all_hashes_valid = bool(accepted_hashes_valid and excluded_hashes_valid)
    return {
        "source_id": _SOURCE_ID,
        "required_start": start_date.isoformat(),
        "required_end": end_date.isoformat(),
        "archive_month_count": len(_month_starts(start, end)),
        "archive_member_count": int(archive_member_count),
        "calendar_day_count": int(calendar_day_count),
        "usable_day_count": len(frame),
        "excluded_member_count": len(relevant_exclusions),
        "excluded_members": relevant_exclusions,
        "all_member_hashes_valid": all_hashes_valid,
        "forecast_hours_per_accepted_day": 24,
        "actual_load_current_day_forbidden": True,
        "availability_basis": "miso_internal_published_date_plus_one_day_0000_fixed_est",
        "revision_status": "single_daily_issue_same_target_revision_not_identifiable",
        "research_pit_ready": bool(
            all_hashes_valid
            and len(frame) + len(relevant_exclusions) == calendar_day_count
        ),
    }
