"""Read-only, hash-pinned 2015 NG type 6/9 ts_ref transition audit.

Only fixed pre-2023 development source files are read. No timestamp repair,
source mutation, automatic rescan, or protected outcome access is permitted.
"""
from __future__ import annotations

import collections
import csv
import gzip
import hashlib
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / ".work" / "runtime" / "market_truth_development"
KNOWN = SOURCE / "statistics-2015.csv"
MISSING = SOURCE / "unreferenced-statistics-2010-2015" / "undefined-ref-2015.csv.gz"
RAW = SOURCE / "raw_checked" / "statistics" / "glbx-mdp3-20150101-20151231.statistics.dbn.zst"
# Trusted baseline digest identities are pinned independently of local receipts.
KNOWN_SHA256 = "c47ac57a0dffd269c71c7e0a40e18052751d809692f6d7f19b7dbdbc021630c9"
MISSING_SHA256 = "7f4cc536e363fb66c55d1a0fc6e596718e1e251fca1c26e7544f7915e874774e"
RAW_SHA256 = "cfedaf6a088aca49d2c2060c41bdcab6a13c302bd4f989ca64f0b841c6b7cd4d"
STAT_TYPES = frozenset({"6", "9"})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def analyze() -> dict:
    if (sha256(KNOWN) != KNOWN_SHA256
        or sha256(MISSING) != MISSING_SHA256
        or sha256(RAW) != RAW_SHA256):
        raise ValueError("pinned source digest mismatch")
    known = collections.Counter()
    undated = collections.Counter()
    day_gaps = collections.Counter()
    known_first: dict[str, str] = {}
    missing_last: dict[str, str] = {}
    reference_first: dict[str, str] = {}
    with KNOWN.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            kind = row["stat_type"]
            if kind not in STAT_TYPES:
                continue
            event, ref = row["ts_event"], row["ts_ref"]
            if not ref.strip() or not event.startswith("2015-"):
                raise ValueError("dated cohort has invalid reference/event")
            gap = (date.fromisoformat(event[:10]) - date.fromisoformat(ref[:10])).days
            day_gaps[(kind, gap)] += 1
            known[(kind, event[:7])] += 1
            known_first[kind] = min(known_first.get(kind, event), event)
            reference_first[kind] = min(reference_first.get(kind, ref), ref)
    with gzip.open(MISSING, "rt", newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            kind, event = row["stat_type"], row["ts_event"]
            if (
                kind not in STAT_TYPES
                or row["ts_ref"].strip()
                or row["source_year"] != "2015"
                or row["source_sha256"] != RAW_SHA256
                or not event.startswith("2015-")
            ):
                raise ValueError("quarantined cohort violates source contract")
            undated[(kind, event[:7])] += 1
            missing_last[kind] = max(missing_last.get(kind, event), event)

    for kind in sorted(STAT_TYPES):
        missing_count = sum(v for (k, _), v in undated.items() if k == kind)
        dated_count = sum(v for (k, _), v in known.items() if k == kind)
        if missing_count != 62277 or dated_count != 7306:
            raise ValueError(f"2015 source count drift for {kind}")
        if {gap: n for (k, gap), n in day_gaps.items() if k == kind} != {1: 5112, 2: 652, 3: 1299, 4: 243}:
            raise ValueError(f"source publication-to-reference gap drift for {kind}")
        if not missing_last[kind] < known_first[kind]:
            raise ValueError(f"overlapping date cohorts for {kind}")
    return {
        "schema_version": 1,
        "issue": 482,
        "year": 2015,
        "state": "verified_archive_transition; no_missing_trade_date_promoted",
        "source_sha256": {"dated": KNOWN_SHA256, "undated": MISSING_SHA256,
                          "original_statistics_dbn": RAW_SHA256},
        "months_undated": {f"{kind}:{month}": n for (kind, month), n in sorted(undated.items())},
        "months_dated": {f"{kind}:{month}": n for (kind, month), n in sorted(known.items())},
        "undated_total": sum(undated.values()),
        "dated_total": sum(known.values()),
        "dated_publication_day_gaps": {f"{kind}:{gap}": n for (kind, gap), n in sorted(day_gaps.items())},
        "first_dated_publication": known_first,
        "last_undated_publication": missing_last,
        "first_dated_reference_timestamp": reference_first,
        "inferred_trade_dates": 0,
        "protected_confirmation_accessed": False,
    }


if __name__ == "__main__":
    print(json.dumps(analyze(), sort_keys=True, indent=2))
