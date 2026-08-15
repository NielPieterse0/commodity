from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from commodity.config import data_config
from commodity.snapshots import SnapshotWriter, verify_snapshot

_SOURCE_ID = "cftc_disaggregated_futures_only_023651"
_SOURCE_VARIANT = "disaggregated_futures_only"


@dataclass
class CftcCotClient:
    session: requests.Session | None = None

    def fetch_year(self, year: int) -> tuple[bytes, str]:
        provider = data_config()["providers"]["cftc_public_reporting"]
        url = provider["annual_disaggregated_futures_only_url_template"].format(year=year)
        response = (self.session or requests.Session()).get(url, timeout=60)
        response.raise_for_status()
        return response.content, url


def _policy() -> dict[str, Any]:
    return data_config()["sources"]["cftc_cot"]["availability_policy"]


def _local_end_of_day(value: str | dt.date) -> pd.Timestamp:
    policy = _policy()
    day = pd.Timestamp(value).date() if not isinstance(value, dt.date) else value
    local = dt.datetime.combine(
        day,
        dt.time(
            int(policy["conservative_local_hour"]),
            int(policy["conservative_local_minute"]),
        ),
        tzinfo=ZoneInfo(policy["timezone"]),
    )
    return pd.Timestamp(local).tz_convert("UTC")


def cftc_research_availability(report_date: str | pd.Timestamp) -> dict[str, Any]:
    policy = _policy()
    report_day = pd.Timestamp(report_date).date()
    report_key = report_day.isoformat()
    special = policy["special_publication_dates"].get(report_key)
    if special is not None:
        publication_day = pd.Timestamp(special).date()
        basis = policy["special_basis"]
    else:
        publication_day = None
        basis = policy["ordinary_basis"]
    if publication_day is None:
        scheduled = sorted(
            pd.Timestamp(value).date() for value in policy.get("scheduled_release_dates", ())
        )
        candidate = next((day for day in scheduled if day > report_day), None)
        max_schedule_gap = int(policy["ordinary_conservative_day_offset"])
        if candidate is not None and (candidate - report_day).days <= max_schedule_gap:
            publication_day = candidate
            basis = policy["scheduled_basis"]
    if publication_day is None:
        publication_day = report_day + dt.timedelta(
            days=int(policy["ordinary_conservative_day_offset"])
        )
    return {
        "available_at": _local_end_of_day(publication_day),
        "availability_status": "reconstructed_conservative",
        "availability_basis": basis,
    }


def _read_archive(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = [
            info for info in archive.infolist()
            if not info.is_dir() and Path(info.filename).suffix.lower() in {".txt", ".csv"}
        ]
        if len(members) != 1:
            raise ValueError("CFTC annual archive must contain exactly one text/CSV data file")
        with archive.open(members[0]) as handle:
            frame = pd.read_csv(handle, dtype=str, low_memory=False)
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def _require(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        raise ValueError(f"CFTC annual archive missing required column {column!r}")
    return frame[column]


def _number(frame: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(_require(frame, column), errors="coerce")
    if values.isna().any():
        raise ValueError(f"CFTC annual archive has missing/non-numeric {column!r} values")
    return values


def _first_column(frame: pd.DataFrame, *columns: str) -> str:
    for column in columns:
        if column in frame.columns:
            return column
    raise ValueError(f"CFTC annual archive missing required column alternatives: {columns}")


def normalize_disaggregated_futures_only_archive(
    content: bytes,
    *,
    year: int,
) -> pd.DataFrame:
    source = data_config()["sources"]["cftc_cot"]
    raw = _read_archive(content)
    market_codes = _require(raw, "CFTC_Contract_Market_Code").astype(str).str.strip().str.zfill(6)
    frame = raw.loc[market_codes.eq(source["contract_market_code"])].copy()
    if frame.empty:
        raise ValueError(f"CFTC annual archive {year} contains no Henry Hub rows")
    variant = _require(frame, "FutOnly_or_Combined").astype(str).str.strip()
    if not variant.eq("FutOnly").all():
        raise ValueError("CFTC Henry Hub annual rows are not exclusively Futures Only")
    report_date_column = _first_column(
        frame,
        "Report_Date_as_YYYY-MM-DD",
        "As_of_Date_Form_YYYY-MM-DD",
    )
    report_dates = pd.to_datetime(
        _require(frame, report_date_column), utc=True, errors="coerce"
    )
    if report_dates.isna().any():
        raise ValueError("CFTC annual archive contains invalid report dates")
    if not report_dates.dt.year.eq(year).all():
        raise ValueError(f"CFTC annual archive contains report dates outside {year}")

    swap_short_column = _first_column(
        frame, "Swap__Positions_Short_All", "Swap_Positions_Short_All"
    )
    archive_sha = hashlib.sha256(content).hexdigest()
    rows = pd.DataFrame(index=frame.index)
    rows["observed_for"] = report_dates
    availability = [cftc_research_availability(value) for value in report_dates]
    rows["available_at"] = [item["available_at"] for item in availability]
    rows["availability_status"] = [item["availability_status"] for item in availability]
    rows["availability_basis"] = [item["availability_basis"] for item in availability]
    rows["revision_status"] = "point_in_time"
    rows["source_id"] = _SOURCE_ID
    rows["source_variant"] = _SOURCE_VARIANT
    rows["source_archive_year"] = year
    rows["source_raw_sha256"] = archive_sha
    rows["market_name"] = _require(frame, "Market_and_Exchange_Names").astype(str).str.strip()
    rows["contract_market_code"] = source["contract_market_code"]
    rows["open_interest"] = _number(frame, "Open_Interest_All")
    rows["producer_merchant_long"] = _number(frame, "Prod_Merc_Positions_Long_All")
    rows["producer_merchant_short"] = _number(frame, "Prod_Merc_Positions_Short_All")
    rows["producer_merchant_net"] = rows["producer_merchant_long"] - rows["producer_merchant_short"]
    rows["swap_dealer_long"] = _number(frame, "Swap_Positions_Long_All")
    rows["swap_dealer_short"] = _number(frame, swap_short_column)
    rows["swap_dealer_net"] = rows["swap_dealer_long"] - rows["swap_dealer_short"]
    rows["managed_money_long"] = _number(frame, "M_Money_Positions_Long_All")
    rows["managed_money_short"] = _number(frame, "M_Money_Positions_Short_All")
    rows["managed_money_spread"] = _number(frame, "M_Money_Positions_Spread_All")
    rows["managed_money_net"] = rows["managed_money_long"] - rows["managed_money_short"]
    rows["other_reportable_long"] = _number(frame, "Other_Rept_Positions_Long_All")
    rows["other_reportable_short"] = _number(frame, "Other_Rept_Positions_Short_All")
    rows["other_reportable_net"] = rows["other_reportable_long"] - rows["other_reportable_short"]
    rows["managed_money_long_pct_oi"] = _number(frame, "Pct_of_OI_M_Money_Long_All")
    rows["managed_money_short_pct_oi"] = _number(frame, "Pct_of_OI_M_Money_Short_All")
    rows = rows.sort_values("observed_for", kind="mergesort").reset_index(drop=True)
    if rows["observed_for"].duplicated().any():
        raise ValueError("CFTC annual archive contains duplicate Henry Hub report dates")
    return rows


def _snapshot_id(year: int) -> str:
    return f"{year}-disaggregated-futures-only"


def capture_cftc_year(
    client: CftcCotClient,
    year: int,
    snapshot_root: Path,
    retrieved_at: str,
) -> Path:
    content, source_url = client.fetch_year(year)
    frame = normalize_disaggregated_futures_only_archive(content, year=year)
    writer = SnapshotWriter(Path(snapshot_root), "cftc_cot", _snapshot_id(year))
    writer.write_bytes("archive.zip", content)
    writer.write_bytes(
        "positioning_features.csv", frame.to_csv(index=False).encode("utf-8")
    )
    return writer.finalize(
        {
            "source_id": _SOURCE_ID,
            "source_variant": _SOURCE_VARIANT,
            "source_url": source_url,
            "year": year,
            "retrieved_at": retrieved_at,
            "source_raw_sha256": hashlib.sha256(content).hexdigest(),
            "normalized_rows": len(frame),
            "point_in_time_backtest_ready": True,
            "availability_status": "reconstructed_conservative",
            "revision_status": "point_in_time",
        }
    )


def capture_cftc_v1_window(
    client: CftcCotClient,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    snapshot_root: Path,
    retrieved_at: str,
) -> list[Path]:
    start_year = pd.Timestamp(start).year
    end_year = pd.Timestamp(end).year
    if end_year < start_year:
        raise ValueError("CFTC V1 end must not precede start")
    root = Path(snapshot_root)
    manifests: list[Path] = []
    for year in range(start_year, end_year + 1):
        manifest = root / "cftc_cot" / _snapshot_id(year) / "manifest.json"
        if manifest.exists():
            verify_snapshot(manifest)
            manifests.append(manifest)
            continue
        manifests.append(capture_cftc_year(client, year, root, retrieved_at))
    return manifests


def load_cftc_v1_window(
    snapshot_root: Path,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
) -> pd.DataFrame:
    root = Path(snapshot_root)
    frames: list[pd.DataFrame] = []
    for year in range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1):
        manifest = root / "cftc_cot" / _snapshot_id(year) / "manifest.json"
        if not manifest.is_file():
            raise ValueError(f"CFTC V1 missing annual snapshot: {year}")
        verify_snapshot(manifest)
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        if metadata.get("source_id") != _SOURCE_ID:
            raise ValueError(f"CFTC V1 snapshot source identity mismatch: {year}")
        if metadata.get("source_variant") != _SOURCE_VARIANT:
            raise ValueError(f"CFTC V1 snapshot variant mismatch: {year}")
        frame = pd.read_csv(
            manifest.parent / "positioning_features.csv",
            parse_dates=["observed_for", "available_at"],
        )
        if frame.empty:
            raise ValueError(f"CFTC V1 annual snapshot has no normalized rows: {year}")
        if not frame["source_id"].astype(str).eq(_SOURCE_ID).all():
            raise ValueError(f"CFTC V1 normalized source identity mismatch: {year}")
        if not frame["source_variant"].astype(str).eq(_SOURCE_VARIANT).all():
            raise ValueError(f"CFTC V1 normalized source variant mismatch: {year}")
        hashes = frame["source_raw_sha256"].astype(str)
        if not hashes.str.fullmatch(r"[0-9a-f]{64}").all():
            raise ValueError(f"CFTC V1 normalized raw lineage invalid: {year}")
        if not hashes.eq(str(metadata.get("source_raw_sha256", ""))).all():
            raise ValueError(f"CFTC V1 normalized raw lineage does not match manifest: {year}")
        frames.append(frame)
    result = pd.concat(frames, ignore_index=True)
    result = result.sort_values("available_at", kind="mergesort").reset_index(drop=True)
    if result["observed_for"].duplicated().any():
        raise ValueError("CFTC V1 window contains duplicate report dates")
    if (result["available_at"] < result["observed_for"]).any():
        raise ValueError("CFTC V1 availability precedes report date")
    return result
