"""Independent-frequency, point-in-time alignment of versioned source facts.

Source adapters establish source clock semantics first. This module never infers
missing reference dates, fabricates observations or queries provider archives.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Literal

ReferenceState = Literal["valid", "unresolved"]
SelectionState = Literal[
    "available", "source_missing", "not_yet_published",
    "reference_unresolved", "stale", "source_value_missing",
]


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class SourceCadence:
    """One logical series, with its own frequency, age and forecast rules."""

    source_id: str
    series_id: str
    cadence: str
    max_age: timedelta | None
    forecast: bool = False

    def __post_init__(self) -> None:
        if not self.source_id or not self.series_id or not self.cadence:
            raise ValueError("source, series and cadence must be explicit")
        if self.max_age is not None and self.max_age < timedelta(0):
            raise ValueError("negative freshness limit")


@dataclass(frozen=True)
class SourceFact:
    """A source-native value; ingest time is provenance, not market availability."""

    source_id: str
    series_id: str
    value: float | None
    observed_for: datetime | None
    available_at: datetime
    source_vintage_id: str
    published_at: datetime | None = None
    issued_at: datetime | None = None
    ingested_at: datetime | None = None
    forecast_valid_at: datetime | None = None
    reference_state: ReferenceState = "valid"

    def __post_init__(self) -> None:
        if not self.source_id or not self.series_id or not self.source_vintage_id:
            raise ValueError("source identity and immutable vintage are required")
        available = _utc(self.available_at, "available_at")
        for name in ("observed_for", "published_at", "issued_at", "ingested_at", "forecast_valid_at"):
            stamp = getattr(self, name)
            if stamp is not None:
                normalized = _utc(stamp, name)
                if name in ("published_at", "issued_at") and normalized > available:
                    raise ValueError(f"{name} is later than declared availability")
        if self.reference_state not in ("valid", "unresolved"):
            raise ValueError("invalid reference state")
        if self.reference_state == "valid" and self.observed_for is None:
            raise ValueError("valid fact requires a verified observation reference")
        if self.reference_state == "unresolved" and self.observed_for is not None:
            raise ValueError("unresolved reference must not invent a date")
        if self.value is not None and (
            isinstance(self.value, bool)
            or not isinstance(self.value, (int, float))
            or not isfinite(self.value)
        ):
            raise ValueError("fact value must be finite or explicitly missing")


@dataclass(frozen=True)
class AsOfValue:
    state: SelectionState
    value: float | None
    fact: SourceFact | None
    age_seconds: float | None
    # Raw entries with unknown reference dates remain auditable, never selectable.
    unresolved_reference_rows: int


def align_asof(
    decision_time: datetime,
    facts: Iterable[SourceFact],
    policies: Iterable[SourceCadence],
    *,
    max_fact_rows: int = 1_000_000,
    knowledge_asof: datetime | None = None,
) -> dict[tuple[str, str], AsOfValue]:
    """Select each series independently using only available, dated versions.

    For observations select the latest observed period, then its last known
    publication. For forecasts use the latest issued forecast, independently
    of its future target period. Freshness is measured from availability,
    not from ingestion. An optional knowledge cutoff limits acquired vintages.
    """
    decision = _utc(decision_time, "decision_time")
    knowledge = _utc(knowledge_asof, "knowledge_asof") if knowledge_asof else None
    keyed: dict[tuple[str, str], SourceCadence] = {}
    for policy in policies:
        key = (policy.source_id, policy.series_id)
        if key in keyed:
            raise ValueError("duplicate series policy")
        keyed[key] = policy
    selected: dict[tuple[str, str], SourceFact] = {}
    unresolved = dict.fromkeys(keyed, 0)
    future = dict.fromkeys(keyed, False)
    seen: dict[tuple[str, str, datetime, datetime, datetime | None, datetime | None, datetime | None], float | None] = {}
    forecast_targets: dict[tuple[str, str], datetime] = {}
    for count, fact in enumerate(facts, start=1):
        if count > max_fact_rows:
            raise ValueError("bounded alignment row budget exceeded")
        key = (fact.source_id, fact.series_id)
        policy = keyed.get(key)
        if policy is None:
            raise ValueError("fact supplied for undeclared series")
        if knowledge is not None:
            if fact.ingested_at is None:
                raise ValueError("knowledge cutoff requires ingestion timestamp")
            if _utc(fact.ingested_at, "ingested_at") > knowledge:
                continue
        if fact.reference_state == "unresolved":
            if _utc(fact.available_at, "available_at") <= decision:
                unresolved[key] += 1
            else:
                future[key] = True
            continue
        assert fact.observed_for is not None
        reference = _utc(fact.observed_for, "observed_for")
        if not policy.forecast and reference > decision:
            future[key] = True
            continue
        if policy.forecast and fact.issued_at is None:
            raise ValueError("forecast requires source-issued timestamp")
        if policy.forecast:
            if fact.forecast_valid_at is None:
                raise ValueError("forecast target time required")
            target = _utc(fact.forecast_valid_at, "forecast_valid_at")
            if reference != target:
                raise ValueError("forecast observation reference must name target period")
            if key in forecast_targets and forecast_targets[key] != target:
                raise ValueError("mixed forecast targets require different series identities")
            forecast_targets[key] = target
        available = _utc(fact.available_at, "available_at")
        if available > decision:
            future[key] = True
            continue
        grouping = _utc(fact.issued_at, "issued_at") if policy.forecast else reference
        duplicate_key = (
            fact.source_id, fact.series_id, grouping, available,
            (_utc(fact.published_at, "published_at") if fact.published_at else None),
            (_utc(fact.issued_at, "issued_at") if fact.issued_at else None),
            (_utc(fact.ingested_at, "ingested_at") if fact.ingested_at else None),
        )
        if duplicate_key in seen and seen[duplicate_key] != fact.value:
            raise ValueError("conflicting same-clock source publications")
        seen[duplicate_key] = fact.value
        # The configured source revision tiebreak applies *after* the
        # observation period (or forecast issue) is fixed.
        def order(item: SourceFact, cadence: SourceCadence) -> tuple:
            source_period = (
                _utc(item.issued_at, "issued_at") if cadence.forecast
                else _utc(item.observed_for, "observed_for")
            )
            return (
                source_period, _utc(item.available_at, "available_at"),
                (_utc(item.published_at, "published_at") if item.published_at else datetime.min.replace(tzinfo=UTC)),
                (_utc(item.issued_at, "issued_at") if item.issued_at else datetime.min.replace(tzinfo=UTC)),
                (_utc(item.ingested_at, "ingested_at") if item.ingested_at else datetime.min.replace(tzinfo=UTC)),
                item.source_vintage_id,
            )
        prior = selected.get(key)
        if prior is None or order(fact, policy) > order(prior, policy):
            selected[key] = fact

    output: dict[tuple[str, str], AsOfValue] = {}
    for key, policy in keyed.items():
        fact = selected.get(key)
        missing = unresolved[key]
        if fact is None:
            state: SelectionState = (
                "not_yet_published" if future[key]
                else "reference_unresolved" if missing
                else "source_missing"
            )
            output[key] = AsOfValue(state, None, None, None, missing)
            continue
        age = (decision - _utc(fact.available_at, "available_at")).total_seconds()
        if policy.max_age is not None and age > policy.max_age.total_seconds():
            output[key] = AsOfValue("stale", None, fact, age, missing)
        elif fact.value is None:
            output[key] = AsOfValue("source_value_missing", None, fact, age, missing)
        else:
            output[key] = AsOfValue("available", fact.value, fact, age, missing)
    return output
