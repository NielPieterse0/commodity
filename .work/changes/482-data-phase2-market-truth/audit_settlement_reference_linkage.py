"""Hash-bound diagnostic: settlement reference linkage, never date promotion.

Read only named pre-2023, previously isolated NG development sources.
A candidate is NOT an approved historical timestamp or an admissible model fact.
"""
from __future__ import annotations

import bisect
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STAGE = ROOT / ".work" / "runtime" / "market_truth_development"
STATISTICS_SHA256 = {
    2010: "6f12bf3bdf0558bedb45e0d576f5fa0a806298817c3aa8b52def6c531e0dc043",
    2011: "929f214c3c63c0ba7194fa8048bbb3fb68c47fa7bc0bafc641529ad56a199488",
    2012: "4eefbe87a84857bda9d82b094ca528e0bd33c052537d29ac5e1aebe47493d0ac",
    2013: "bb286e3eb1fe59bdf123b062eb4fce247795ad35891d981da33c09b74f4c623c",
    2014: "527d488231cda385dab94bf5530ba496539b0ce20b369d07436649971ca97ccf",
    2015: "c47ac57a0dffd269c71c7e0a40e18052751d809692f6d7f19b7dbdbc021630c9",
    2016: "075e36b6c85a7250a7505b21070f5872b3373fd80d0307c7af89b2d23861e3cb",
}
MISSING_SHA256 = {
    2010: "6106a9f0faa235a0f58d328ba7fb5a8f90b242ef05a5420b549e4bd0483c9e2a",
    2011: "3d032af56d6f758691468068d877a18939e93100ec259e530ea730384fb08cdb",
    2012: "5d8bc87b760a1bac1f2914ff647e9070cbeec422b361f645cb1169078de226f0",
    2013: "d23e2fb3bb2333d00ac4ffd7a195bc3c26e8a2299cfab3d89ae75a8b74963d9d",
    2014: "bae23ac2eb1873aa38a9815efa8016cd593399362d075142a4a6171b0076c6a2",
    2015: "7f4cc536e363fb66c55d1a0fc6e596718e1e251fca1c26e7544f7915e874774e",
}
MISSING_PER_TYPE = {2010: 45042, 2011: 75049, 2012: 71686,
                    2013: 75903, 2014: 73560, 2015: 62277}
KNOWN_PER_TYPE = {2015: 7306, 2016: 65034}


def checked(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as reader:
        for block in iter(lambda: reader.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError("hash mismatch in pinned pre-2023 statistics source")


def publication_clock(row: dict[str, str]) -> datetime:
    """Use both supplied source clocks, not proof of a real MDP2 receive clock."""
    return max(datetime.fromisoformat(row["ts_event"]),
               datetime.fromisoformat(row["ts_recv"]))


def read_year(year: int):
    """Read one fixed year's already-curated source; reject unpinned changes."""
    path = STAGE / f"statistics-{year}.csv"
    checked(path, STATISTICS_SHA256[year])
    settlements = defaultdict(list)
    controls = []
    with path.open(encoding="utf-8", newline="") as reader:
        for row in csv.DictReader(reader):
            kind = row["stat_type"]
            if kind == "3":
                if row["ts_ref"].strip():
                    settlements[row["instrument_id"]].append(
                        (publication_clock(row), row["ts_ref"][:10]))
            elif kind in {"6", "9"} and row["ts_ref"].strip():
                controls.append((row["instrument_id"], row["ts_event"],
                                 row["ts_ref"][:10], kind))
    checked(path, STATISTICS_SHA256[year])  # detects non-atomic input replacement
    for rows in settlements.values():
        rows.sort()
    return settlements, controls


def correlate(rows: list, event: str):
    """Nearest published settlement, with same-clock contradiction veto."""
    if not rows:
        return "no_prior_settlement"
    t = datetime.fromisoformat(event)
    i = bisect.bisect_right(rows, (t, "~")) - 1
    if i < 0:
        return "no_prior_settlement"
    j = i
    while j > 0 and rows[j - 1][0] == rows[i][0]:
        if rows[j - 1][1] != rows[i][1]:
            return "ambiguous_same_clock_settlement"
        j -= 1
    return rows[i][1]


def classify_link(outcome: str, published_at: str) -> str:
    """Classify a candidate without asserting an historical reference date."""
    if outcome in {"no_prior_settlement", "ambiguous_same_clock_settlement"}:
        return outcome
    lag = (datetime.fromisoformat(published_at).date()
           - date.fromisoformat(outcome)).days
    return "candidate_1_4_day_lag" if 1 <= lag <= 4 else "outside_1_4_day_lag"


def audit() -> dict:
    candidate_by_year = {}
    exception_triage_by_year = {}
    known_controls = Counter()
    previous_year_settlements = None
    for year in range(2010, 2017):
        settlements, controls = read_year(year)
        if year in KNOWN_PER_TYPE:
            observed = Counter()
            for inst, event, truth, kind in controls:
                outcome = correlate(settlements.get(inst, []), event)
                observed[(kind, "match" if outcome == truth else "mismatch")] += 1
            for kind in ("6", "9"):
                if (observed[(kind, "match")] != KNOWN_PER_TYPE[year]
                    or observed[(kind, "mismatch")]):
                    raise ValueError(f"dated {year} {kind} control mismatch")
            known_controls[str(year)] = sum(observed.values())
        if year == 2016:
            continue
        source = (STAGE / "unreferenced-statistics-2010-2015"
                  / f"undefined-ref-{year}.csv.gz")
        checked(source, MISSING_SHA256[year])
        counters = Counter()
        by_type = defaultdict(Counter)
        exception_contracts = defaultdict(set)
        exception_days = defaultdict(set)
        exception_ids = defaultdict(list)
        previous_year_probe = Counter()
        with gzip.open(source, "rt", encoding="utf-8", newline="") as stream:
            for item in csv.DictReader(stream):
                if (
                    item["source_year"] != str(year)
                    or item["ts_ref"].strip()
                    or item["stat_type"] not in {"6", "9"}
                ):
                    raise ValueError(f"invalid undated archive cohort for {year}")
                outcome = correlate(
                    settlements.get(item["instrument_id"], []), item["ts_event"]
                )
                reason = classify_link(outcome, item["ts_event"])
                counters[reason] += 1
                kind = item["stat_type"]
                by_type[kind][reason] += 1
                if reason == "no_prior_settlement" and previous_year_settlements is not None:
                    prior = correlate(previous_year_settlements.get(item["instrument_id"], []), item["ts_event"])
                    previous_year_probe[classify_link(prior, item["ts_event"])] += 1
                if reason != "candidate_1_4_day_lag":
                    exception_contracts[reason].add(item["instrument_id"])
                    exception_days[reason].add(item["ts_event"][:10])
                    # Stable, source-scoped record fingerprints only; no raw
                    # identifiers or conjectural trade dates in the audit.
                    identity = json.dumps(item, sort_keys=True, separators=(",", ":"))
                    exception_ids[reason].append(
                        hashlib.sha256(identity.encode("utf-8")).hexdigest()
                    )
        checked(source, MISSING_SHA256[year])  # still requires trusted read-only source ownership
        if sum(counters.values()) != 2 * MISSING_PER_TYPE[year]:
            raise ValueError(f"missing undated record count drift {year}")
        if any(sum(by_type[kind].values()) != MISSING_PER_TYPE[year]
               for kind in ("6", "9")):
            raise ValueError(f"annual type 6/9 count drift {year}")
        if (previous_year_settlements is not None
                and sum(previous_year_probe.values()) != counters["no_prior_settlement"]):
            raise ValueError(f"year-boundary diagnostic drift {year}")
        candidate_by_year[str(year)] = dict(counters)
        exception_triage_by_year[str(year)] = {
            "previous_year_settlement_probe_for_no_prior_only": dict(sorted(previous_year_probe.items())),
            "by_stat_type": {
                kind: dict(sorted(by_type[kind].items())) for kind in ("6", "9")
            },
            "exceptions": {
                reason: {
                    "rows": counters[reason],
                    "unique_instrument_ids": len(exception_contracts[reason]),
                    "unique_publication_dates": len(exception_days[reason]),
                    "earliest_publication_day": min(exception_days[reason]),
                    "latest_publication_day": max(exception_days[reason]),
                    "source_cohort_sha256": hashlib.sha256(
                        "\n".join(sorted(exception_ids[reason])).encode("ascii")
                    ).hexdigest(),
                }
                for reason in (
                    "no_prior_settlement",
                    "ambiguous_same_clock_settlement",
                    "outside_1_4_day_lag",
                )
                if counters[reason]
            },
        }
        previous_year_settlements = settlements
    result = Counter()
    for annual in candidate_by_year.values():
        result.update(annual)
    if sum(result.values()) != 807034 or sum(known_controls.values()) != 144680:
        raise ValueError("expected 2010-2016 type6/9 control total drift")
    return {
        "schema_version": 1, "issue": 482,
        "state": "candidate_only_not_historical_date_recovery",
        "known_reference_controls": dict(known_controls),
        "known_reference_mismatches": 0,
        "undated_source_total": sum(result.values()),
        "undated_candidate_counts_by_year": candidate_by_year,
        "undated_candidate_totals": dict(result),
        "exception_triage_by_year": exception_triage_by_year,
        "historical_dates_promoted": 0,
        "provenance": "fixed pre-2023 manifest hashes of annual statistics CSV and recovered GZ",
        "open_gates": ["time-valid contract identity", "independent dated CME or provider confirmation",
                       "revision/finality/availability", "ambiguous and unmatched reconciliation"],
        "protected_confirmation_accessed": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True, indent=2))
