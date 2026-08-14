from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any

import pandas as pd

from commodity.availability import validate_availability
from commodity.config import data_config

_REQUIRED_EXOGENOUS_SOURCES = {
    "storage": "eia_storage",
    "weather": "weather",
    "power": "nyiso_load_forecast",
    "positioning": "cftc_cot",
}
REQUIRED_EXOGENOUS_FAMILIES = tuple(_REQUIRED_EXOGENOUS_SOURCES)


@dataclass(frozen=True)
class ExogenousFamilyAudit:
    family: str
    source_name: str
    verdict: str
    full_v1_ready: bool
    evidence_mode: str
    source_rows: int
    source_sha256: str | None
    coverage_start: str | None
    coverage_end: str | None
    availability_statuses: tuple[str, ...]
    revision_statuses: tuple[str, ...]
    blockers: tuple[str, ...]
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["availability_statuses"] = list(self.availability_statuses)
        value["revision_statuses"] = list(self.revision_statuses)
        value["blockers"] = list(self.blockers)
        value["caveats"] = list(self.caveats)
        return value


def exogenous_frame_sha256(frame: pd.DataFrame) -> str:
    canonical = frame.copy()
    timestamp_columns = [
        column
        for column in ("observed_for", "issued_at", "available_at", "forecast_valid_at")
        if column in canonical.columns
    ]
    for column in timestamp_columns:
        canonical[column] = pd.to_datetime(canonical[column], utc=True, errors="coerce")
    sort_columns = [column for column in timestamp_columns if not canonical[column].isna().all()]
    if sort_columns:
        canonical = canonical.sort_values(sort_columns, kind="mergesort")
    canonical = canonical.reset_index(drop=True)
    payload = canonical.to_csv(index=False, lineterminator="\n", float_format="%.17g")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _coverage_series(frame: pd.DataFrame) -> pd.Series:
    for column in ("available_at", "issued_at", "observed_for"):
        if column in frame.columns:
            values = pd.to_datetime(frame[column], utc=True, errors="coerce")
            if values.notna().any():
                return values
    return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")


def _utc(value: str | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC") if pd.Timestamp(value).tzinfo is None else pd.Timestamp(value).tz_convert("UTC")


def _staleness_exceeds_limit(
    frame: pd.DataFrame,
    required_start: pd.Timestamp,
    required_end: pd.Timestamp,
    max_age: pd.Timedelta,
) -> bool:
    if max_age < pd.Timedelta(0):
        raise ValueError("maximum staleness must be non-negative")
    timestamps = _coverage_series(frame).dropna().sort_values().drop_duplicates()
    if timestamps.empty:
        return True
    available_at_start = timestamps[timestamps <= required_start]
    if available_at_start.empty:
        return True
    previous = pd.Timestamp(available_at_start.iloc[-1])
    if required_start - previous > max_age:
        return True
    for current in timestamps[(timestamps > required_start) & (timestamps <= required_end)]:
        current_ts = pd.Timestamp(current)
        if current_ts - previous > max_age:
            return True
        previous = current_ts
    return required_end - previous > max_age


def _configured_max_staleness(source_cfg: Mapping[str, Any]) -> pd.Timedelta | None:
    max_hours = source_cfg.get("max_staleness_hours")
    max_days = source_cfg.get("max_staleness_days")
    if max_hours is not None and max_days is not None:
        raise ValueError("Configure only one maximum-staleness unit per source")
    if max_hours is not None:
        return pd.Timedelta(hours=float(max_hours))
    if max_days is not None:
        return pd.Timedelta(days=float(max_days))
    return None


def audit_exogenous_family(
    *,
    family: str,
    source_name: str,
    frame: pd.DataFrame | None,
    required_start: str | pd.Timestamp,
    required_end: str | pd.Timestamp,
    evidence_mode: str = "research_pit",
) -> ExogenousFamilyAudit:
    if frame is None or frame.empty:
        return ExogenousFamilyAudit(
            family=family,
            source_name=source_name,
            verdict="not-fit",
            full_v1_ready=False,
            evidence_mode=evidence_mode,
            source_rows=0,
            source_sha256=None,
            coverage_start=None,
            coverage_end=None,
            availability_statuses=(),
            revision_statuses=(),
            blockers=("preserved_pit_evidence_missing",),
            caveats=(),
        )

    source_hash = exogenous_frame_sha256(frame)
    availability_statuses = tuple(sorted(frame.get("availability_status", pd.Series(dtype=str)).dropna().astype(str).unique()))
    revision_statuses = tuple(sorted(frame.get("revision_status", pd.Series(dtype=str)).dropna().astype(str).unique()))
    coverage = _coverage_series(frame)
    coverage_start = coverage.min() if coverage.notna().any() else pd.NaT
    coverage_end = coverage.max() if coverage.notna().any() else pd.NaT

    blockers: list[str] = []
    caveats: list[str] = []
    try:
        validate_availability(frame, evidence_mode)
    except ValueError:
        blockers.append("research_pit_ineligible_rows")

    required_start_ts = _utc(required_start)
    required_end_ts = _utc(required_end)
    if pd.isna(coverage_start) or pd.isna(coverage_end) or coverage_start > required_start_ts or coverage_end < required_end_ts:
        blockers.append("coverage_incomplete")

    if "reconstructed_conservative" in availability_statuses:
        caveats.append("conservative_availability")
    if blockers:
        verdict = "not-fit"
        full_v1_ready = False
    elif caveats:
        verdict = "fit-with-caveats"
        full_v1_ready = True
    else:
        verdict = "fit"
        full_v1_ready = True

    return ExogenousFamilyAudit(
        family=family,
        source_name=source_name,
        verdict=verdict,
        full_v1_ready=full_v1_ready,
        evidence_mode=evidence_mode,
        source_rows=len(frame),
        source_sha256=source_hash,
        coverage_start=(
            None if pd.isna(coverage_start) else pd.Timestamp(coverage_start).isoformat()
        ),
        coverage_end=(
            None if pd.isna(coverage_end) else pd.Timestamp(coverage_end).isoformat()
        ),
        availability_statuses=availability_statuses,
        revision_statuses=revision_statuses,
        blockers=tuple(dict.fromkeys(blockers)),
        caveats=tuple(dict.fromkeys(caveats)),
    )


def _configured_policy_blockers(
    family: str,
    source_cfg: Mapping[str, Any],
    evidence_mode: str,
    evidence_source_id: str | None = None,
) -> tuple[str, ...]:
    if evidence_mode not in {"research_pit", "canonical"}:
        return ()
    policy = source_cfg.get("availability_policy", {})
    if family == "storage":
        if not policy.get("research_pit_allowed", False):
            return ("configured_storage_source_not_research_pit_admissible",)
        accepted_source_ids = set(source_cfg.get("accepted_source_ids", ()))
        if evidence_source_id not in accepted_source_ids:
            return ("configured_storage_source_identity_mismatch",)
    if family == "power":
        if not policy.get("research_pit_allowed", False):
            return ("configured_power_source_not_research_pit_admissible",)
        accepted_source_ids = set(source_cfg.get("accepted_source_ids", ()))
        if evidence_source_id is not None and evidence_source_id not in accepted_source_ids:
            return ("configured_power_source_identity_mismatch",)
    if family == "weather":
        accepted_source_ids = set(source_cfg.get("accepted_source_ids", ()))
        if evidence_source_id not in accepted_source_ids:
            return ("configured_weather_source_identity_mismatch",)
    if family == "positioning":
        if not policy.get("research_pit_allowed", False):
            return ("configured_positioning_source_not_research_pit_admissible",)
        accepted_source_ids = set(source_cfg.get("accepted_source_ids", ()))
        if evidence_source_id not in accepted_source_ids:
            return ("configured_positioning_source_identity_mismatch",)
    return ()


def audit_configured_exogenous_family(
    *,
    family: str,
    source_name: str | None = None,
    evidence_source_id: str | None = None,
    frame: pd.DataFrame | None,
    required_start: str | pd.Timestamp,
    required_end: str | pd.Timestamp,
    evidence_mode: str = "research_pit",
) -> ExogenousFamilyAudit:
    expected_source = _REQUIRED_EXOGENOUS_SOURCES.get(family)
    if expected_source is None:
        raise ValueError(f"Unsupported required exogenous family: {family!r}")
    resolved_source = source_name or expected_source
    if resolved_source != expected_source:
        raise ValueError(
            f"Configured source for {family!r} is {expected_source!r}, not {resolved_source!r}"
        )
    source_cfg = data_config()["sources"][resolved_source]
    resolved_evidence_source_id = evidence_source_id
    if (
        resolved_evidence_source_id is None
        and frame is not None
        and not frame.empty
        and "source_id" in frame.columns
        and frame["source_id"].nunique(dropna=False) == 1
    ):
        resolved_evidence_source_id = str(frame["source_id"].iloc[0])
    result = audit_exogenous_family(
        family=family,
        source_name=resolved_source,
        frame=frame,
        required_start=required_start,
        required_end=required_end,
        evidence_mode=evidence_mode,
    )
    max_staleness = _configured_max_staleness(source_cfg)
    if max_staleness is not None and frame is not None and not frame.empty:
        start_ts = _utc(required_start)
        end_ts = _utc(required_end)
        if end_ts < start_ts:
            raise ValueError("required_end must be on or after required_start")
        blockers = list(result.blockers)
        caveats = list(result.caveats)
        if _staleness_exceeds_limit(
            frame,
            start_ts,
            end_ts,
            max_staleness,
        ):
            blockers.append("max_staleness_exceeded")
        else:
            coverage_end = _coverage_series(frame).max()
            if "coverage_incomplete" in blockers and coverage_end < end_ts:
                blockers.remove("coverage_incomplete")
                caveats.append("bounded_forward_fill")
        blockers_tuple = tuple(dict.fromkeys(blockers))
        caveats_tuple = tuple(dict.fromkeys(caveats))
        result = replace(
            result,
            verdict=(
                "not-fit"
                if blockers_tuple
                else "fit-with-caveats"
                if caveats_tuple
                else "fit"
            ),
            full_v1_ready=not blockers_tuple,
            blockers=blockers_tuple,
            caveats=caveats_tuple,
        )
    policy_blockers = _configured_policy_blockers(
        family,
        source_cfg,
        evidence_mode,
        evidence_source_id=resolved_evidence_source_id,
    )
    lineage_blockers: tuple[str, ...] = ()
    if family == "storage" and frame is not None and not frame.empty:
        blockers: list[str] = []
        expected_variant = str(source_cfg.get("source_variant", ""))
        if "source_variant" not in frame.columns:
            blockers.append("storage_source_variant_missing")
        elif not frame["source_variant"].astype(str).eq(expected_variant).all():
            blockers.append("storage_source_variant_invalid")
        for column in ("history_raw_sha256", "revisions_raw_sha256"):
            if column not in frame.columns:
                blockers.append(f"storage_{column}_missing")
            elif not frame[column].astype(str).str.fullmatch(r"[0-9a-f]{64}").all():
                blockers.append(f"storage_{column}_invalid")
        lineage_blockers = tuple(blockers)
    if family == "weather" and frame is not None and not frame.empty:
        blockers: list[str] = []
        if "source_id" not in frame.columns:
            blockers.append("weather_source_lineage_missing")
        elif not frame["source_id"].astype(str).eq(resolved_evidence_source_id).all():
            blockers.append("weather_source_lineage_invalid")
        if "source_raw_sha256" not in frame.columns:
            blockers.append("weather_raw_lineage_missing")
        else:
            hashes = frame["source_raw_sha256"].astype(str)
            if not hashes.str.fullmatch(r"[0-9a-f]{64}").all():
                blockers.append("weather_raw_lineage_invalid")
        lineage_blockers = tuple(blockers)
    if family == "positioning" and frame is not None and not frame.empty:
        blockers = []
        expected_variant = str(source_cfg.get("source_variant", ""))
        if "source_variant" not in frame.columns:
            blockers.append("positioning_source_variant_missing")
        elif not frame["source_variant"].astype(str).eq(expected_variant).all():
            blockers.append("positioning_source_variant_invalid")
        if "source_raw_sha256" not in frame.columns:
            blockers.append("positioning_raw_lineage_missing")
        elif not frame["source_raw_sha256"].astype(str).str.fullmatch(r"[0-9a-f]{64}").all():
            blockers.append("positioning_raw_lineage_invalid")
        lineage_blockers = tuple(blockers)
    policy_blockers = tuple(dict.fromkeys((*policy_blockers, *lineage_blockers)))
    if not policy_blockers:
        return result
    blockers = tuple(dict.fromkeys((*result.blockers, *policy_blockers)))
    return replace(result, verdict="not-fit", full_v1_ready=False, blockers=blockers)


def audit_required_exogenous_families(
    *,
    frames: Mapping[str, pd.DataFrame | None],
    required_start: str | pd.Timestamp,
    required_end: str | pd.Timestamp,
    evidence_mode: str = "research_pit",
) -> dict[str, ExogenousFamilyAudit]:
    return {
        family: audit_configured_exogenous_family(
            family=family,
            source_name=source_name,
            frame=frames.get(family),
            required_start=required_start,
            required_end=required_end,
            evidence_mode=evidence_mode,
        )
        for family, source_name in _REQUIRED_EXOGENOUS_SOURCES.items()
    }
