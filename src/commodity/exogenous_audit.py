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
    "power": "eia_power",
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
) -> tuple[str, ...]:
    if evidence_mode not in {"research_pit", "canonical"}:
        return ()
    if family in {"storage", "power"}:
        policy = source_cfg.get("availability_policy", {})
        if not policy.get("research_pit_allowed_for_current_snapshot", False):
            return ("current_snapshot_not_research_pit_admissible",)
    if family == "positioning":
        status = str(source_cfg.get("availability_reconstruction_status", ""))
        if "incomplete" in status or "pending" in status:
            return ("historical_release_calendar_incomplete",)
    return ()


def audit_configured_exogenous_family(
    *,
    family: str,
    source_name: str | None = None,
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
    result = audit_exogenous_family(
        family=family,
        source_name=resolved_source,
        frame=frame,
        required_start=required_start,
        required_end=required_end,
        evidence_mode=evidence_mode,
    )
    policy_blockers = _configured_policy_blockers(family, source_cfg, evidence_mode)
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
