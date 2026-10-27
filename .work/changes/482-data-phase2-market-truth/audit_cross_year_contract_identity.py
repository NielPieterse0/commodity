"""Source-pinned cross-year contract identity check, not historical date recovery.

Only reads fixed 2010-2014 pre-2023 development definitions and the pinned
2010-2014 statistics/recovery cohorts. No archive discovery or timestamp promotion.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime

from audit_settlement_reference_linkage import (
    MISSING_SHA256,
    STAGE,
    checked,
    classify_link,
    correlate,
    read_year,
)

DEFINITION_SHA256 = {
    2010: "5f26e2908249518a43a008e1a32b59c04ed50131b3ed6b68542f1e28f558af0a",
    2011: "5405686bc5ff5c7bc11c4a9c1fac0de6a7d060dc53306a836751a21a244189e5",
    2012: "ed6c1eb334387093d503a218373e8bb5ea4b76b4eda7d1f7a61e078389f37cf7",
    2013: "7c5b83475f4075144fb3089d7d4e7c281522799cb70c5fbe812cf0a4c608136e",
    2014: "b136640c1ba5a4ee1da2939645278e70f795a693608d9018d8fe01f58050c324",
}
CROSS_YEAR_EXPECTED = {2011: 14, 2013: 546, 2014: 570}
IDENTITY_FIELDS = ("asset", "instrument_class", "exchange", "raw_symbol", "expiration")


def latest_identity(rows: list[dict[str, str]], published_at: str) -> tuple[str, ...] | None:
    """Select an unambiguous identity actually available by the cutoff."""
    cutoff = datetime.fromisoformat(published_at)
    eligible: list[tuple[datetime, tuple[str, ...]]] = []
    for row in rows:
        available = max(datetime.fromisoformat(row["ts_event"]),
                        datetime.fromisoformat(row["ts_recv"]))
        if available <= cutoff:
            eligible.append((available, tuple(row[key] for key in IDENTITY_FIELDS)))
    if not eligible:
        return None
    latest = max(clock for clock, _ in eligible)
    identities = {identity for clock, identity in eligible if clock == latest}
    if len(identities) != 1:
        raise ValueError("ambiguous latest contract identity")
    return next(iter(identities))


def require_same_contract(previous_rows, current_rows, published_at):
    previous = latest_identity(previous_rows, published_at)
    current = latest_identity(current_rows, published_at)
    if previous is None or current is None or previous != current:
        raise ValueError("cross-year contract identity not proven")
    if previous[:3] != ("NG", "F", "XNYM"):
        raise ValueError("unexpected NG futures contract identity")
    return previous


def read_selected_definitions(year: int, selected: set[str]) -> dict[str, list[dict[str, str]]]:
    path = STAGE / f"definitions-{year}.csv"
    checked(path, DEFINITION_SHA256[year])
    definitions: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["instrument_id"] in selected:
                definitions[row["instrument_id"]].append(row)
    checked(path, DEFINITION_SHA256[year])
    return definitions


def audit() -> dict:
    summaries: dict[str, dict] = {}
    total = 0
    all_contracts = 0
    for year, expected in CROSS_YEAR_EXPECTED.items():
        previous_settlements, _ = read_year(year - 1)
        current_settlements, _ = read_year(year)
        source = STAGE / "unreferenced-statistics-2010-2015" / f"undefined-ref-{year}.csv.gz"
        checked(source, MISSING_SHA256[year])
        selected: list[tuple[str, str, str, str]] = []
        with gzip.open(source, "rt", encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                if (row["source_year"] != str(year)
                    or row["ts_ref"].strip()
                    or row["stat_type"] not in {"6", "9"}):
                    raise ValueError("invalid undated source record")
                identity = row["instrument_id"]
                event = row["ts_event"]
                if correlate(current_settlements.get(identity, []), event) != "no_prior_settlement":
                    continue
                candidate = correlate(previous_settlements.get(identity, []), event)
                if classify_link(candidate, event) == "candidate_1_4_day_lag":
                    selected.append((identity, event, candidate, row["stat_type"]))
        checked(source, MISSING_SHA256[year])
        if len(selected) != expected:
            raise ValueError(f"year-boundary candidate count changed: {year}")
        instruments = {identity for identity, _, _, _ in selected}
        previous_definitions = read_selected_definitions(year - 1, instruments)
        current_definitions = read_selected_definitions(year, instruments)
        evidence_hashes = []
        stat_types = Counter()
        for identity, event, reference_candidate, kind in selected:
            require_same_contract(
                previous_definitions.get(identity, []),
                current_definitions.get(identity, []),
                event,
            )
            evidence_hashes.append(hashlib.sha256(json.dumps(
                (year, kind, identity, event, reference_candidate),
                separators=(",", ":"),
            ).encode("utf-8")).hexdigest())
            stat_types[kind] += 1
        if stat_types["6"] != stat_types["9"]:
            raise ValueError(f"statistic type pairing drift: {year}")
        summaries[str(year)] = {
            "candidate_records": len(selected),
            "unique_contract_ids": len(instruments),
            "same_time_valid_identity": len(selected),
            "type_6": stat_types["6"],
            "type_9": stat_types["9"],
            "source_record_cohort_sha256": hashlib.sha256(
                "\n".join(sorted(evidence_hashes)).encode("ascii")
            ).hexdigest(),
        }
        total += len(selected)
        all_contracts += len(instruments)
    if total != 1130:
        raise ValueError("cross-year source totals drift")
    return {
        "schema_version": 1,
        "issue": 482,
        "state": "cross_year_identity_agrees_candidate_only",
        "year_breakdown": summaries,
        "candidate_records": total,
        "year_specific_unique_contract_ids": all_contracts,
        "identity_mismatches": 0,
        "verified_historical_reference_dates": 0,
        "promotion_allowed": False,
        "protected_confirmation_accessed": False,
        "remaining_gates": [
            "independent CME/provider trading reference for statistic types 6 and 9",
            "true availability and preliminary-versus-final evidence",
            "exchange calendar and trading session",
            "source-owner attestation and immutable file ownership",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True, indent=2))
