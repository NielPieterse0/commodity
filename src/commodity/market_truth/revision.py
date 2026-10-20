"""Provider-neutral single owner for same-clock revision semantics.

A retransmission may only change event time and source evidence identity.
The canonical representative is the earliest event, then evidence digest.
Eager Python and SQLite streaming consumers use these same rules.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .errors import MarketTruthError

RETRANSMISSION_FIELDS = frozenset({"event_at", "evidence_id"})
REVISION_GRAINS = {
    "definitions": ("venue", "instrument_id"),
    "bars": ("instrument_id", "trade_date"),
    "statistics": ("instrument_id", "trade_date", "stat_type"),
}
REVISION_TABLES = frozenset(REVISION_GRAINS)


def equivalent_economic_facts(first: dict[str, Any], second: dict[str, Any]) -> bool:
    first_keys = set(first) - RETRANSMISSION_FIELDS
    second_keys = set(second) - RETRANSMISSION_FIELDS
    return first_keys == second_keys and all(
        first[field] == second[field] for field in first_keys
    )


def canonical_preference(row: dict[str, Any]) -> tuple[str, str]:
    return str(row["event_at"]), str(row["evidence_id"])


def canonicalize_versions(
    rows: Iterable[dict[str, Any]], grain: tuple[str, ...], label: str
) -> list[dict[str, Any]]:
    """Deduplicate only economically identical observations at the same clock."""
    selected: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(row[field] for field in grain) + (row["available_at"],)
        previous = selected.get(key)
        if previous is None:
            selected[key] = row
            continue
        if not equivalent_economic_facts(previous, row):
            raise MarketTruthError(f"ambiguous {label} revision at same availability")
        if canonical_preference(row) < canonical_preference(previous):
            selected[key] = row
    return sorted(
        selected.values(),
        key=lambda row: (
            tuple(str(row[field]) for field in grain)
            + (row["available_at"], row["evidence_id"])
        ),
    )


def sqlite_revision_upsert(family: str) -> str:
    """Compile the same revision comparison into a fixed SQLite upsert."""
    if family not in REVISION_TABLES:
        raise MarketTruthError("unknown revision table")
    fields = ", ".join(f"'$.{field}'" for field in sorted(RETRANSMISSION_FIELDS))
    matching = (
        f"json_remove(payload, {fields}) = "
        f"json_remove(excluded.payload, {fields})"
    )
    earlier = (
        "(json_extract(excluded.payload, '$.event_at'), excluded.evidence_id) < "
        "(json_extract(payload, '$.event_at'), evidence_id)"
    )
    return (
        f"INSERT INTO {family} "
        "(grain, available_at, evidence_id, payload) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(grain, available_at) DO UPDATE SET "
        f"payload = CASE WHEN {matching} AND {earlier} "
        "THEN excluded.payload ELSE payload END, "
        f"evidence_id = CASE WHEN NOT ({matching}) THEN '' "
        f"WHEN {earlier} THEN excluded.evidence_id ELSE evidence_id END"
    )
