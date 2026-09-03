from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from commodity.config import data_config
from commodity.snapshots import SnapshotWriter, verify_snapshot

_SOURCE_ID = "nyiso_p7_iso_load_forecast"
_MEMBER_RE = re.compile(r"^(?P<day>\d{8})isolf\.csv$", re.IGNORECASE)
_TIMEZONE = "America/New_York"


@dataclass
class NyisoLoadForecastClient:
    session: requests.Session | None = None

    def fetch_month(self, year: int, month: int) -> tuple[bytes, str]:
        cfg = data_config()["providers"]["nyiso_mis"]
        url = cfg["p7_archive_url_template"].format(year=year, month=month)
        response = (self.session or requests.Session()).get(url, timeout=60)
        try:
            response.raise_for_status()
        except requests.RequestException:
            status = getattr(response, "status_code", "unknown")
            raise RuntimeError(f"NYISO P-7 archive request failed with HTTP {status}") from None
        return response.content, url


def _local_timestamp(value: dt.datetime) -> pd.Timestamp:
    return pd.Timestamp(value.replace(tzinfo=ZoneInfo(_TIMEZONE))).tz_convert("UTC")


def _parse_forecast_times(
    values: pd.Series,
    time_zones: pd.Series | None = None,
) -> pd.Series:
    parsed = pd.to_datetime(values, errors="raise")
    ambiguous = "infer"
    if time_zones is not None:
        ambiguous = time_zones.astype(str).str.upper().eq("EDT").to_numpy()
    localized = parsed.dt.tz_localize(_TIMEZONE, ambiguous=ambiguous)
    return localized.dt.tz_convert("UTC")


def _member_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _conservative_available_at(operating_day: dt.date) -> pd.Timestamp:
    local_noon = dt.datetime.combine(
        operating_day,
        dt.time(hour=12),
        tzinfo=ZoneInfo(_TIMEZONE),
    )
    return pd.Timestamp(local_noon).tz_convert("UTC")


def normalize_p7_archive(content: bytes, *, archive_id: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = [
            info
            for info in archive.infolist()
            if not info.is_dir() and _MEMBER_RE.match(Path(info.filename).name)
        ]
        if not members:
            raise ValueError("NYISO P-7 archive contains no isolf CSV members")

        for info in sorted(members, key=lambda item: Path(item.filename).name):
            match = _MEMBER_RE.match(Path(info.filename).name)
            assert match is not None
            day = match.group("day")
            operating_day = dt.date.fromisoformat(
                f"{day[:4]}-{day[4:6]}-{day[6:]}"
            )
            source_updated_at = _local_timestamp(
                dt.datetime(*info.date_time, tzinfo=ZoneInfo(_TIMEZONE))
            )
            available_at = _conservative_available_at(operating_day)
            if source_updated_at > available_at:
                raise ValueError(
                    f"NYISO P-7 member {info.filename!r} was updated later than "
                    "conservative availability bound"
                )

            member_bytes = archive.read(info)
            frame = pd.read_csv(io.BytesIO(member_bytes))
            required = {"Time Stamp", "NYISO"}
            missing = sorted(required - set(frame.columns))
            if missing:
                raise ValueError(
                    f"NYISO P-7 member {info.filename!r} missing required columns: {missing}"
                )
            if frame.empty:
                raise ValueError(f"NYISO P-7 member {info.filename!r} is empty")

            valid_at = _parse_forecast_times(
                frame["Time Stamp"],
                frame.get("Time Zone"),
            )
            nyiso_load = pd.to_numeric(frame["NYISO"], errors="coerce")
            if nyiso_load.isna().any():
                raise ValueError(
                    f"NYISO P-7 member {info.filename!r} has non-numeric NYISO load"
                )
            next_day = operating_day + dt.timedelta(days=1)
            local_dates = valid_at.dt.tz_convert(_TIMEZONE).dt.date
            next_day_load = nyiso_load.loc[local_dates == next_day]
            if next_day_load.empty:
                raise ValueError(
                    f"NYISO P-7 member {info.filename!r} has no next-day NYISO forecast"
                )

            forecast_day_local = dt.datetime.combine(
                next_day,
                dt.time.min,
                tzinfo=ZoneInfo(_TIMEZONE),
            )
            observed_local = dt.datetime.combine(
                operating_day,
                dt.time.min,
                tzinfo=ZoneInfo(_TIMEZONE),
            )
            rows.append(
                {
                    "observed_for": pd.Timestamp(observed_local).tz_convert("UTC"),
                    "issued_at": source_updated_at,
                    "available_at": available_at,
                    "forecast_valid_at": pd.Timestamp(forecast_day_local).tz_convert("UTC"),
                    "power_next_day_load_mean_mw": float(next_day_load.mean()),
                    "power_next_day_load_max_mw": float(next_day_load.max()),
                    "power_next_day_load_min_mw": float(next_day_load.min()),
                    "availability_status": "reconstructed_conservative",
                    "revision_status": "issued_run_immutable",
                    "availability_basis": "nyiso_p7_noon_et_bound",
                    "source_id": _SOURCE_ID,
                    "source_archive_id": archive_id,
                    "source_member": Path(info.filename).name,
                    "source_member_sha256": _member_sha256(member_bytes),
                    "source_updated_at": source_updated_at,
                }
            )

    result = pd.DataFrame(rows).sort_values("available_at", kind="mergesort").reset_index(drop=True)
    if result["available_at"].duplicated().any():
        raise ValueError("NYISO P-7 archive produces duplicate availability timestamps")
    return result


def capture_p7_month(
    client: NyisoLoadForecastClient,
    year: int,
    month: int,
    snapshot_root: Path,
    snapshot_id: str,
    retrieved_at: str,
) -> Path:
    content, source_url = client.fetch_month(year, month)
    archive_id = f"{year:04d}-{month:02d}"
    frame = normalize_p7_archive(content, archive_id=archive_id)
    writer = SnapshotWriter(Path(snapshot_root), "nyiso_p7", snapshot_id)
    writer.write_bytes("archive.zip", content)
    writer.write_bytes("power_features.csv", frame.to_csv(index=False).encode("utf-8"))
    return writer.finalize(
        {
            "source_id": _SOURCE_ID,
            "source_url": source_url,
            "archive_id": archive_id,
            "retrieved_at": retrieved_at,
            "normalized_rows": len(frame),
            "availability_status": "reconstructed_conservative",
            "revision_status": "issued_run_immutable",
            "point_in_time_backtest_ready": True,
            "availability_basis": "nyiso_p7_noon_et_bound",
        }
    )


def _month_starts(
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
) -> pd.DatetimeIndex:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if end_ts < start_ts:
        raise ValueError("NYISO V1 end must not precede start")
    if start_ts.tzinfo is not None:
        start_ts = start_ts.tz_localize(None)
    if end_ts.tzinfo is not None:
        end_ts = end_ts.tz_localize(None)
    first = start_ts.to_period("M").to_timestamp()
    last = end_ts.to_period("M").to_timestamp()
    return pd.date_range(first, last, freq="MS")


def _month_snapshot_id(year: int, month: int) -> str:
    return f"{year:04d}{month:02d}-p7"


def capture_nyiso_v1_window(
    client: NyisoLoadForecastClient,
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
        manifest = root / "nyiso_p7" / snapshot_id / "manifest.json"
        if manifest.exists():
            verify_snapshot(manifest)
            manifests.append(manifest)
            continue
        manifests.append(
            capture_p7_month(
                client,
                year,
                month,
                root,
                snapshot_id,
                retrieved_at,
            )
        )
    return manifests


def load_nyiso_v1_window(
    snapshot_root: Path,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
) -> pd.DataFrame:
    root = Path(snapshot_root)
    frames: list[pd.DataFrame] = []
    parse_dates = [
        "observed_for",
        "issued_at",
        "available_at",
        "forecast_valid_at",
        "source_updated_at",
    ]
    for month_start in _month_starts(start, end):
        year = int(month_start.year)
        month = int(month_start.month)
        snapshot_id = _month_snapshot_id(year, month)
        manifest = root / "nyiso_p7" / snapshot_id / "manifest.json"
        if not manifest.is_file():
            raise ValueError(f"NYISO V1 missing monthly snapshot: {year:04d}-{month:02d}")
        verify_snapshot(manifest)
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        if metadata.get("source_id") != _SOURCE_ID:
            raise ValueError(f"NYISO V1 snapshot source identity mismatch: {snapshot_id}")
        if metadata.get("point_in_time_backtest_ready") is not True:
            raise ValueError(f"NYISO V1 snapshot is not research-PIT ready: {snapshot_id}")
        frame = pd.read_csv(
            manifest.parent / "power_features.csv",
            parse_dates=parse_dates,
        )
        if frame.empty:
            raise ValueError(f"NYISO V1 monthly snapshot has no rows: {snapshot_id}")
        frames.append(frame)
    result = pd.concat(frames, ignore_index=True)
    local_dates = result["observed_for"].dt.tz_convert(_TIMEZONE).dt.date
    start_date = pd.Timestamp(start).date()
    end_date = pd.Timestamp(end).date()
    result = result.loc[(local_dates >= start_date) & (local_dates <= end_date)].copy()
    result = result.sort_values("available_at", kind="mergesort").reset_index(drop=True)
    if result.empty:
        raise ValueError("NYISO V1 window contains no normalized power evidence")
    if not result["source_id"].astype(str).eq(_SOURCE_ID).all():
        raise ValueError("NYISO V1 normalized source identity mismatch")
    if not result["source_member_sha256"].astype(str).str.fullmatch(r"[0-9a-f]{64}").all():
        raise ValueError("NYISO V1 normalized source-member lineage is invalid")
    observed_dates = result["observed_for"].dt.tz_convert(_TIMEZONE).dt.normalize().dt.date
    expected_dates = pd.date_range(start_date, end_date, freq="D").date
    if list(observed_dates) != list(expected_dates):
        raise ValueError("NYISO V1 daily operating-date coverage is incomplete or duplicated")
    if result["available_at"].duplicated().any():
        raise ValueError("NYISO V1 window contains duplicate availability timestamps")
    return result
