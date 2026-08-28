from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from commodity.availability import resolve_wngsr_release
from commodity.config import data_config
from commodity.snapshots import SnapshotWriter, verify_snapshot

_SOURCE_ID = "eia_wngsr_vintage_reconstruction"
_SOURCE_VARIANT = "original_plus_published_revisions"


@dataclass
class WngsrEvidenceClient:
    session: requests.Session | None = None

    def fetch_bundle(self) -> tuple[bytes, bytes, dict[str, str]]:
        cfg = data_config()["providers"]["eia_wngsr"]
        session = self.session or requests.Session()
        payloads: list[bytes] = []
        urls: dict[str, str] = {}
        for label, key in (("history", "history_url"), ("revisions", "revisions_url")):
            url = str(cfg[key])
            response = session.get(url, timeout=60)
            try:
                response.raise_for_status()
            except requests.RequestException:
                status = getattr(response, "status_code", "unknown")
                raise RuntimeError(
                    f"EIA WNGSR {label} request failed with HTTP {status}"
                ) from None
            payloads.append(response.content)
            urls[f"{label}_url"] = url
        return payloads[0], payloads[1], urls


def _canonical(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()


def _find_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str:
    mapping = {_canonical(column): str(column) for column in frame.columns}
    for alias in aliases:
        key = _canonical(alias)
        if key in mapping:
            return mapping[key]
    for alias in aliases:
        key = _canonical(alias)
        matches = [column for normalized, column in mapping.items() if key in normalized]
        if len(matches) == 1:
            return matches[0]
    raise ValueError(f"WNGSR table missing required column aliases: {aliases}")


def _find_optional_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    try:
        return _find_column(frame, aliases)
    except ValueError:
        return None


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(frame[column], errors="coerce")
    if values.isna().any():
        raise ValueError(f"WNGSR table has missing/non-numeric {column!r} values")
    return values.astype(float)


def normalize_wngsr_history_table(frame: pd.DataFrame) -> pd.DataFrame:
    week_col = _find_column(
        frame,
        ("Week ending", "Week ending date", "week_ending", "Date"),
    )
    total_col = _find_column(
        frame,
        ("Lower 48 States", "Lower 48", "Total Working Gas", "Total"),
    )
    observed = pd.to_datetime(frame[week_col], utc=True, errors="coerce")
    if observed.isna().any():
        raise ValueError("WNGSR history contains invalid week-ending dates")
    out = pd.DataFrame(
        {
            "observed_for": observed,
            "storage_lower48_bcf": _numeric(frame, total_col),
        }
    )
    out = out.sort_values("observed_for", kind="mergesort").reset_index(drop=True)
    if out["observed_for"].duplicated().any():
        raise ValueError("WNGSR history contains duplicate week-ending dates")
    return out


def normalize_wngsr_revisions_table(frame: pd.DataFrame) -> pd.DataFrame:
    week_col = _find_column(frame, ("Week ending", "Week ending date", "week_ending"))
    original_col = _find_column(
        frame,
        ("Original Estimate", "Original Working Gas", "Original"),
    )
    revised_col = _find_optional_column(
        frame,
        ("Revised Estimate", "Revised Working Gas", "Revised"),
    )
    date_col = _find_column(
        frame,
        ("Revision Date", "Date of Revision", "Release Date", "Published Date"),
    )
    observed = pd.to_datetime(frame[week_col], utc=True, errors="coerce")
    revision_date = pd.to_datetime(frame[date_col], utc=True, errors="coerce")
    if observed.isna().any() or revision_date.isna().any():
        raise ValueError("WNGSR revisions contain invalid observation/revision dates")
    explicit_revised = (
        pd.to_numeric(frame[revised_col], errors="coerce").astype(float)
        if revised_col is not None
        else pd.Series(float("nan"), index=frame.index, dtype=float)
    )
    if revised_col is not None and explicit_revised.isna().any():
        raise ValueError(f"WNGSR table has missing/non-numeric {revised_col!r} values")
    out = pd.DataFrame(
        {
            "observed_for": observed,
            "original_storage_lower48_bcf": _numeric(frame, original_col),
            "revised_storage_lower48_bcf": explicit_revised,
            "revision_date": revision_date,
            "revision_date_basis": "published_revision_date",
        }
    )
    return out.sort_values(["revision_date", "observed_for"], kind="mergesort").reset_index(drop=True)


def _storage_cfg() -> dict[str, Any]:
    return data_config()["sources"]["eia_storage"]


def resolve_wngsr_release_availability(
    observed_for: str | pd.Timestamp,
) -> pd.Timestamp:
    available_at, status, _ = resolve_wngsr_release(observed_for, _storage_cfg())
    if status == "unresolved" or pd.isna(available_at):
        raise ValueError(
            f"WNGSR release timing unresolved outside registry for {pd.Timestamp(observed_for).date()}"
        )
    return pd.Timestamp(available_at)


def _revision_availability(row: pd.Series) -> tuple[pd.Timestamp, str, str]:
    policy = _storage_cfg()["availability_policy"]
    observed_key = pd.Timestamp(row["observed_for"]).date().isoformat()
    revision_day = pd.Timestamp(row["revision_date"]).date()
    sample_weeks = set(policy.get("sample_reselection_weeks", ()))
    for event_name, event_value in policy.get("special_revision_events", {}).items():
        event = pd.Timestamp(event_value)
        if event.tzinfo is None:
            raise ValueError(f"WNGSR special revision event lacks timezone: {event_value!r}")
        if observed_key in sample_weeks and revision_day == event.date():
            return event.tz_convert("UTC"), "verified", f"wngsr_{event_name}"
    zone = ZoneInfo(str(policy["timezone"]))
    local = dt.datetime.combine(revision_day, dt.time(23, 59), tzinfo=zone)
    basis = (
        "wngsr_revision_snapshot_retrieval_end_of_day"
        if row.get("revision_date_basis") == "snapshot_retrieval_date"
        else "wngsr_revision_publication_date_end_of_day"
    )
    return (
        pd.Timestamp(local).tz_convert("UTC"),
        "reconstructed_conservative",
        basis,
    )


def _event_row(
    state: dict[pd.Timestamp, float],
    *,
    available_at: pd.Timestamp,
    availability_status: str,
    availability_basis: str,
    event_type: str,
    revision_targets: tuple[pd.Timestamp, ...],
    history_raw_sha256: str,
    revisions_raw_sha256: str,
) -> dict[str, Any]:
    ordered = sorted(state)
    if not ordered:
        raise ValueError("WNGSR event state cannot be empty")
    latest = ordered[-1]
    previous = ordered[-2] if len(ordered) > 1 else None
    latest_value = float(state[latest])
    weekly_change = None if previous is None else latest_value - float(state[previous])
    return {
        "observed_for": latest,
        "available_at": available_at,
        "storage_lower48_bcf": latest_value,
        "storage_weekly_change_bcf": weekly_change,
        "availability_status": availability_status,
        "revision_status": "point_in_time",
        "availability_basis": availability_basis,
        "source_id": _SOURCE_ID,
        "source_variant": _SOURCE_VARIANT,
        "source_event_type": event_type,
        "revision_target_count": len(revision_targets),
        "revision_targets": ",".join(
            value.date().isoformat() for value in sorted(revision_targets)
        ),
        "history_raw_sha256": history_raw_sha256,
        "revisions_raw_sha256": revisions_raw_sha256,
    }


def _resolve_revision_values(
    history: pd.DataFrame,
    revisions: pd.DataFrame,
) -> pd.DataFrame:
    finals = {
        pd.Timestamp(row.observed_for): float(row.storage_lower48_bcf)
        for row in history.itertuples(index=False)
    }
    resolved = revisions.copy()
    resolved["_revision_available_at"] = [
        _revision_availability(row)[0] for _, row in resolved.iterrows()
    ]
    resolved["_effective_revised_storage_lower48_bcf"] = float("nan")
    for observed, group in resolved.groupby("observed_for", sort=False):
        observed_ts = pd.Timestamp(observed)
        if observed_ts not in finals:
            raise ValueError(f"WNGSR revision targets unknown history week: {observed_ts.date()}")
        ordered = group.sort_values(
            ["_revision_available_at", "revision_date"], kind="mergesort"
        )
        if ordered["_revision_available_at"].duplicated().any():
            raise ValueError("WNGSR has multiple same-week revisions at one publication time")
        indices = list(ordered.index)
        for position, index in enumerate(indices):
            explicit = resolved.at[index, "revised_storage_lower48_bcf"]
            inferred = (
                float(resolved.at[indices[position + 1], "original_storage_lower48_bcf"])
                if position + 1 < len(indices)
                else finals[observed_ts]
            )
            if pd.notna(explicit) and abs(float(explicit) - inferred) > 1e-9:
                raise ValueError("WNGSR explicit revised estimate conflicts with revision chain")
            resolved.at[index, "_effective_revised_storage_lower48_bcf"] = inferred
    return resolved


def build_wngsr_feature_events(
    history: pd.DataFrame,
    revisions: pd.DataFrame,
    *,
    history_raw_sha256: str,
    revisions_raw_sha256: str,
) -> pd.DataFrame:
    if not re.fullmatch(r"[0-9a-f]{64}", history_raw_sha256):
        raise ValueError("WNGSR history SHA-256 is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", revisions_raw_sha256):
        raise ValueError("WNGSR revisions SHA-256 is invalid")
    history = history.sort_values("observed_for", kind="mergesort").reset_index(drop=True)
    revisions = _resolve_revision_values(history, revisions).sort_values(
        ["_revision_available_at", "observed_for"], kind="mergesort"
    ).reset_index(drop=True)
    baseline = {
        pd.Timestamp(row.observed_for): float(row.storage_lower48_bcf)
        for row in history.itertuples(index=False)
    }
    for observed, group in revisions.groupby("observed_for", sort=False):
        first = group.sort_values("_revision_available_at", kind="mergesort").iloc[0]
        baseline[pd.Timestamp(observed)] = float(first["original_storage_lower48_bcf"])

    revision_specs: list[dict[str, Any]] = []
    for row_index, row in revisions.iterrows():
        observed = pd.Timestamp(row["observed_for"])
        available_at, status, basis = _revision_availability(row)
        if available_at <= resolve_wngsr_release_availability(observed):
            raise ValueError("WNGSR revision availability must follow original release")
        revision_specs.append(
            {
                "observed_for": observed,
                "available_at": available_at,
                "value": float(row["_effective_revised_storage_lower48_bcf"]),
                "availability_status": status,
                "availability_basis": basis,
                "row_index": row_index,
            }
        )
    specs: dict[pd.Timestamp, dict[str, Any]] = {}
    for observed, value in baseline.items():
        available_at = resolve_wngsr_release_availability(observed)
        spec = specs.setdefault(
            available_at,
            {
                "releases": [],
                "revisions": [],
                "statuses": [],
                "bases": [],
            },
        )
        spec["releases"].append((observed, value))
        spec["statuses"].append("reconstructed_conservative")
        spec["bases"].append("wngsr_release_schedule")
    for revision in revision_specs:
        spec = specs.setdefault(
            revision["available_at"],
            {"releases": [], "revisions": [], "statuses": [], "bases": []},
        )
        spec["revisions"].append(revision)
        spec["statuses"].append(revision["availability_status"])
        spec["bases"].append(revision["availability_basis"])

    state: dict[pd.Timestamp, float] = {}
    rows: list[dict[str, Any]] = []
    for available_at in sorted(specs):
        spec = specs[available_at]
        for observed, value in sorted(spec["releases"], key=lambda item: item[0]):
            state[observed] = float(value)
        revision_targets: list[pd.Timestamp] = []
        for revision in sorted(spec["revisions"], key=lambda item: item["row_index"]):
            observed = pd.Timestamp(revision["observed_for"])
            if observed not in state:
                raise ValueError("WNGSR revision targets a week not yet publicly released")
            state[observed] = float(revision["value"])
            revision_targets.append(observed)

        has_release = bool(spec["releases"])
        has_revision = bool(spec["revisions"])
        event_type = (
            "release+revision" if has_release and has_revision
            else "revision" if has_revision
            else "release"
        )
        statuses = set(spec["statuses"])
        status = "verified" if statuses == {"verified"} else "reconstructed_conservative"
        bases = tuple(dict.fromkeys(str(value) for value in spec["bases"]))
        rows.append(
            _event_row(
                state,
                available_at=available_at,
                availability_status=status,
                availability_basis="+".join(bases),
                event_type=event_type,
                revision_targets=tuple(revision_targets),
                history_raw_sha256=history_raw_sha256,
                revisions_raw_sha256=revisions_raw_sha256,
            )
        )
    result = pd.DataFrame(rows).sort_values("available_at", kind="mergesort").reset_index(drop=True)
    if result["available_at"].duplicated().any():
        raise ValueError("WNGSR event stream contains duplicate availability times")
    if not result["available_at"].is_monotonic_increasing:
        raise ValueError("WNGSR event stream is not chronologically ordered")
    return result


def _promote_candidate_headers(sheet: pd.DataFrame) -> list[pd.DataFrame]:
    candidates: list[pd.DataFrame] = []
    for row_index in range(min(30, len(sheet))):
        header = [str(value).strip() for value in sheet.iloc[row_index].tolist()]
        normalized = {_canonical(value) for value in header if value and value != "nan"}
        if not any("week ending" in value for value in normalized):
            continue
        candidate = sheet.iloc[row_index + 1 :].copy()
        candidate.columns = header
        candidate = candidate.dropna(axis=0, how="all").dropna(axis=1, how="all")
        candidates.append(candidate.reset_index(drop=True))
    return candidates


def _read_xls_candidates(content: bytes) -> list[pd.DataFrame]:
    sheets = pd.read_excel(
        io.BytesIO(content), sheet_name=None, header=None, engine="xlrd"
    )
    return [
        candidate
        for sheet in sheets.values()
        for candidate in _promote_candidate_headers(sheet)
    ]


def _normalize_wngsr_original_data_revisions(
    frame: pd.DataFrame,
    history: pd.DataFrame,
    *,
    retrieved_at: str | pd.Timestamp | None,
) -> pd.DataFrame:
    if retrieved_at is None:
        raise ValueError("WNGSR original-data revision ledger requires retrieval time")
    week_col = _find_column(frame, ("Week ending", "Week ending date", "week_ending"))
    original_col = _find_column(
        frame,
        ("Lower 48 States", "Lower 48", "Total Working Gas", "Total"),
    )
    observed = pd.to_datetime(frame[week_col], utc=True, errors="coerce")
    original = pd.to_numeric(frame[original_col], errors="coerce")
    if observed.isna().any() or original.isna().any():
        raise ValueError("WNGSR original-data ledger contains invalid week/value rows")
    originals = pd.DataFrame(
        {
            "observed_for": observed,
            "original_storage_lower48_bcf": original.astype(float),
        }
    )
    if originals["observed_for"].duplicated().any():
        raise ValueError("WNGSR original-data ledger contains duplicate week-ending dates")
    finals = history[["observed_for", "storage_lower48_bcf"]].copy()
    merged = originals.merge(finals, on="observed_for", how="left", validate="one_to_one")
    if merged["storage_lower48_bcf"].isna().any():
        raise ValueError("WNGSR original-data ledger contains weeks absent from current history")
    changed = merged.loc[
        (merged["original_storage_lower48_bcf"] - merged["storage_lower48_bcf"]).abs() > 1e-9
    ].copy()
    retrieved = pd.Timestamp(retrieved_at)
    if retrieved.tzinfo is None:
        raise ValueError("WNGSR retrieval time must include timezone")
    policy = _storage_cfg()["availability_policy"]
    sample_weeks = set(policy.get("sample_reselection_weeks", ()))
    sample_revision_day = pd.Timestamp(
        policy["special_revision_events"]["2024_sample_reselection"]
    ).date()
    changed["revision_date"] = pd.to_datetime(
        [
            sample_revision_day
            if value.date().isoformat() in sample_weeks
            else retrieved.date()
            for value in changed["observed_for"]
        ],
        utc=True,
    )
    changed["revised_storage_lower48_bcf"] = changed["storage_lower48_bcf"].astype(float)
    changed["revision_date_basis"] = "snapshot_retrieval_date"
    return changed[
        [
            "observed_for",
            "original_storage_lower48_bcf",
            "revised_storage_lower48_bcf",
            "revision_date",
            "revision_date_basis",
        ]
    ].sort_values(["revision_date", "observed_for"], kind="mergesort").reset_index(drop=True)


def _require_unique_normalized_candidate(
    results: list[pd.DataFrame],
    *,
    label: str,
) -> pd.DataFrame:
    if not results:
        raise ValueError(f"WNGSR {label} workbook has no recognizable table")
    if len(results) > 1:
        raise ValueError(
            f"WNGSR {label} workbook has multiple admissible tables; "
            "table selection is ambiguous"
        )
    return results[0]


def parse_wngsr_workbooks(
    history_content: bytes,
    revisions_content: bytes,
    *,
    retrieved_at: str | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    history_results: list[pd.DataFrame] = []
    for candidate in _read_xls_candidates(history_content):
        try:
            history_results.append(normalize_wngsr_history_table(candidate))
        except ValueError:
            continue
    history_result = _require_unique_normalized_candidate(
        history_results,
        label="history",
    )

    revisions_results: list[pd.DataFrame] = []
    for candidate in _read_xls_candidates(revisions_content):
        try:
            revisions_results.append(normalize_wngsr_revisions_table(candidate))
            continue
        except ValueError:
            pass
        try:
            revisions_results.append(
                _normalize_wngsr_original_data_revisions(
                    candidate,
                    history_result,
                    retrieved_at=retrieved_at,
                )
            )
        except ValueError:
            continue
    revisions_result = _require_unique_normalized_candidate(
        revisions_results,
        label="revisions",
    )
    return history_result, revisions_result


def _window_history(history: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=21)
    end_ts = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    selected = history.loc[
        (history["observed_for"] >= start_ts) & (history["observed_for"] < end_ts)
    ].copy()
    if selected.empty:
        raise ValueError("WNGSR history has no rows in the bounded V1 context window")
    return selected


def _window_revisions(
    revisions: pd.DataFrame,
    history: pd.DataFrame,
) -> pd.DataFrame:
    weeks = set(pd.to_datetime(history["observed_for"], utc=True))
    selected = revisions.loc[
        pd.to_datetime(revisions["observed_for"], utc=True).isin(weeks)
    ].copy()
    return selected.reset_index(drop=True)


def _window_events(events: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    cfg = _storage_cfg()
    context_days = int(cfg.get("max_staleness_days", 14))
    start_ts = pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=context_days)
    end_ts = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    selected = events.loc[
        (events["available_at"] >= start_ts) & (events["available_at"] < end_ts)
    ].copy()
    if selected.empty:
        raise ValueError("WNGSR event stream has no evidence in the requested V1 window")
    return selected.reset_index(drop=True)


def _snapshot_id(start: str, end: str) -> str:
    return f"{pd.Timestamp(start).date().isoformat()}_{pd.Timestamp(end).date().isoformat()}"


def capture_wngsr_v1_window(
    client: WngsrEvidenceClient,
    start: str,
    end: str,
    snapshot_root: Path,
    retrieved_at: str,
) -> Path:
    root = Path(snapshot_root)
    snapshot_id = _snapshot_id(start, end)
    manifest = root / "eia_wngsr" / snapshot_id / "manifest.json"
    if manifest.exists():
        verify_snapshot(manifest)
        return manifest

    history_content, revisions_content, urls = client.fetch_bundle()
    history_hash = hashlib.sha256(history_content).hexdigest()
    revisions_hash = hashlib.sha256(revisions_content).hexdigest()
    history, revisions = parse_wngsr_workbooks(
        history_content,
        revisions_content,
        retrieved_at=retrieved_at,
    )
    history = _window_history(history, start, end)
    revisions = _window_revisions(revisions, history)
    events = build_wngsr_feature_events(
        history,
        revisions,
        history_raw_sha256=history_hash,
        revisions_raw_sha256=revisions_hash,
    )
    events = _window_events(events, start, end)
    writer = SnapshotWriter(root, "eia_wngsr", snapshot_id)
    writer.write_bytes("ngshistory.xls", history_content)
    writer.write_bytes("revisions.xls", revisions_content)
    writer.write_bytes(
        "storage_feature_events.csv", events.to_csv(index=False).encode("utf-8")
    )
    return writer.finalize(
        {
            "source_id": _SOURCE_ID,
            "source_variant": _SOURCE_VARIANT,
            "history_url": urls["history_url"],
            "revisions_url": urls["revisions_url"],
            "history_raw_sha256": history_hash,
            "revisions_raw_sha256": revisions_hash,
            "requested_start": start,
            "requested_end": end,
            "retrieved_at": retrieved_at,
            "normalized_rows": len(events),
            "availability_status": "reconstructed_conservative",
            "revision_status": "point_in_time",
            "point_in_time_backtest_ready": True,
        }
    )


def load_wngsr_v1_window(
    snapshot_root: Path,
    start: str,
    end: str,
) -> pd.DataFrame:
    manifest = Path(snapshot_root) / "eia_wngsr" / _snapshot_id(start, end) / "manifest.json"
    if not manifest.is_file():
        raise ValueError(f"WNGSR V1 snapshot is missing: {_snapshot_id(start, end)}")
    verify_snapshot(manifest)
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    if metadata.get("source_id") != _SOURCE_ID:
        raise ValueError("WNGSR V1 snapshot source identity mismatch")
    if metadata.get("source_variant") != _SOURCE_VARIANT:
        raise ValueError("WNGSR V1 snapshot source variant mismatch")
    frame = pd.read_csv(
        manifest.parent / "storage_feature_events.csv",
        parse_dates=["observed_for", "available_at"],
    )
    if frame.empty:
        raise ValueError("WNGSR V1 snapshot has no storage feature events")
    if not frame["source_id"].astype(str).eq(_SOURCE_ID).all():
        raise ValueError("WNGSR V1 normalized source identity mismatch")
    if not frame["source_variant"].astype(str).eq(_SOURCE_VARIANT).all():
        raise ValueError("WNGSR V1 normalized source variant mismatch")
    for column, metadata_key in (
        ("history_raw_sha256", "history_raw_sha256"),
        ("revisions_raw_sha256", "revisions_raw_sha256"),
    ):
        hashes = frame[column].astype(str)
        if not hashes.str.fullmatch(r"[0-9a-f]{64}").all():
            raise ValueError(f"WNGSR V1 normalized {column} lineage invalid")
        if not hashes.eq(str(metadata.get(metadata_key, ""))).all():
            raise ValueError(f"WNGSR V1 normalized {column} lineage mismatches manifest")
    frame = frame.sort_values("available_at", kind="mergesort").reset_index(drop=True)
    if frame["available_at"].duplicated().any():
        raise ValueError("WNGSR V1 normalized events have duplicate availability times")
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    prior = frame.loc[frame["available_at"] <= start_ts]
    if prior.empty:
        raise ValueError("WNGSR V1 snapshot has no evidence available at research start")
    max_staleness = pd.Timedelta(days=int(_storage_cfg().get("max_staleness_days", 14)))
    latest_before_end = frame.loc[frame["available_at"] < end_ts, "available_at"].max()
    if pd.isna(latest_before_end) or latest_before_end + max_staleness < pd.Timestamp(end, tz="UTC"):
        raise ValueError("WNGSR V1 snapshot does not cover research end within staleness bound")
    return frame
