"""Detail source-era settlement conflicts, never promoting inferred reference dates.

Read only explicitly pinned 2010-2015 isolated input cohorts. Report aggregates
and stable hashes, not unapproved row-level historical dates or model features.
"""
from __future__ import annotations

import bisect
import csv
import gzip
import hashlib
import io
import json
import re
import tempfile
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import UTC, date, datetime

from audit_settlement_reference_linkage import (
    MISSING_SHA256,
    STAGE,
    STATISTICS_SHA256,
)

EXPECTED_AMBIGUOUS = 1870
EXPECTED_OUTSIDE = 190


@contextmanager
def verified_bytes(path, expected_sha256):
    """Consume one hash-verified private snapshot, never a second path open."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("pinned source missing or symlinked")
    digest = hashlib.sha256()
    with tempfile.TemporaryFile(mode="w+b", dir=STAGE) as snapshot:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
                snapshot.write(chunk)
        if digest.hexdigest() != expected_sha256:
            raise ValueError("pinned source content hash mismatch")
        snapshot.seek(0)
        yield snapshot


UTC_SOURCE_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.(?P<fraction>[0-9]{1,9}))?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)


def exact_clock(value: str) -> datetime:
    """Require full second precision and timezone on provider-native clocks."""
    if not isinstance(value, str) or UTC_SOURCE_CLOCK.fullmatch(value) is None:
        raise ValueError("incomplete or noncanonical source timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("source timestamp timezone missing")
    return parsed


def clock_identity(value: str) -> tuple[datetime, int]:
    """UTC microsecond plus residual nanoseconds, with no lexical timestamp ties."""
    stamp = exact_clock(value).astimezone(UTC)
    match = UTC_SOURCE_CLOCK.fullmatch(value)
    assert match is not None  # exact_clock just validated the whole value.
    fraction = (match.group("fraction") or "").ljust(9, "0")
    return stamp, int(fraction[6:])


def settlement_clock_rows(year: int):
    """Read one independently pinned curated annual settlement cohort."""
    path = STAGE / f"statistics-{year}.csv"
    rows = defaultdict(list)
    with verified_bytes(path, STATISTICS_SHA256[year]) as data, io.TextIOWrapper(
        data, encoding="utf-8", newline=""
    ) as source:
        for row in csv.DictReader(source):
            if row["stat_type"] != "3" or not row["ts_ref"].strip():
                continue
            try:
                reference_at = exact_clock(row["ts_ref"])
            except ValueError as exc:
                raise ValueError("invalid complete settlement ts_ref") from exc
            reference_day = reference_at.date().isoformat()
            source_clock = max(
                clock_identity(row["ts_event"]), clock_identity(row["ts_recv"])
            )
            rows[row["instrument_id"]].append((
                source_clock, reference_day,
                row.get("stat_flags", ""), row.get("is_final", ""),
            ))
    for versions in rows.values():
        versions.sort()
    return rows


def detail_for(versions, event: str) -> dict:
    """Inspect the latest not-after-event settlement clock without promotion."""
    event_identity = clock_identity(event)
    event_time = event_identity[0]
    index = bisect.bisect_right(versions, (event_identity, "~")) - 1
    if index < 0:
        return {"status": "no_prior_settlement"}
    at = versions[index][0]
    first = index
    while first > 0 and versions[first - 1][0] == at:
        first -= 1
    same_clock = versions[first:index + 1]
    reference_dates = sorted({item[1] for item in same_clock})
    for reference_day in reference_dates:
        date.fromisoformat(reference_day)  # Reject malformed contradictory dates.
    if len(reference_dates) > 1:
        return {
            "status": "ambiguous_same_clock_settlement",
            "distinct_reference_dates": len(reference_dates),
            "settlement_versions": len(same_clock),
            "flag_shapes": sorted({item[2] for item in same_clock}),
            "finality_shapes": sorted({item[3] for item in same_clock}),
        }
    day = reference_dates[0]
    lag = (event_time.date() - date.fromisoformat(day)).days
    return {"status": "outside_1_4_day_lag" if not 1 <= lag <= 4
            else "candidate_1_4_day_lag", "calendar_day_lag": lag}


def inspect() -> dict:
    reason_by_type = defaultdict(Counter)
    same_clock_shape = Counter()
    same_clock_flags = Counter()
    same_clock_finality = Counter()
    outside_lags = Counter()
    # Private drift check only: never publish a source-event month in the receipt.
    outside_source_event_months = Counter()
    annual = {}
    for year in range(2010, 2016):
        settled = settlement_clock_rows(year)
        source = STAGE / "unreferenced-statistics-2010-2015" / (
            f"undefined-ref-{year}.csv.gz"
        )
        count = Counter()
        identities = defaultdict(list)
        with verified_bytes(source, MISSING_SHA256[year]) as data, gzip.open(
            data, "rt", encoding="utf-8", newline=""
        ) as handle:
            for row in csv.DictReader(handle):
                if (row["source_year"] != str(year)
                        or row["stat_type"] not in {"6", "9"}
                        or row["ts_ref"].strip()):
                    raise ValueError("unexpected unreferenced source record")
                exact_clock(row["ts_event"])
                exact_clock(row["ts_recv"])
                detail = detail_for(settled.get(row["instrument_id"], []),
                                    row["ts_event"])
                reason = detail["status"]
                if reason not in {"ambiguous_same_clock_settlement",
                                  "outside_1_4_day_lag"}:
                    continue
                count[reason] += 1
                reason_by_type[reason][row["stat_type"]] += 1
                identity = json.dumps(row, sort_keys=True, separators=(",", ":"))
                identities[reason].append(
                    hashlib.sha256(identity.encode("utf-8")).hexdigest()
                )
                if reason == "ambiguous_same_clock_settlement":
                    same_clock_shape[(
                        year, detail["distinct_reference_dates"],
                        detail["settlement_versions"]
                    )] += 1
                    same_clock_flags[tuple(detail["flag_shapes"])] += 1
                    same_clock_finality[tuple(detail["finality_shapes"])] += 1
                else:
                    outside_lags[detail["calendar_day_lag"]] += 1
                    outside_source_event_months[row["ts_event"][:7]] += 1
        annual[str(year)] = {
            "ambiguous_same_clock_settlement": count[
                "ambiguous_same_clock_settlement"],
            "outside_1_4_day_lag": count["outside_1_4_day_lag"],
            "exception_cohort_sha256": {
                key: hashlib.sha256("\n".join(sorted(values)).encode("ascii")
                ).hexdigest()
                for key, values in sorted(identities.items())
            },
        }
    total_ambiguous = sum(x["ambiguous_same_clock_settlement"]
                          for x in annual.values())
    total_outside = sum(x["outside_1_4_day_lag"] for x in annual.values())
    if (total_ambiguous, total_outside) != (
        EXPECTED_AMBIGUOUS, EXPECTED_OUTSIDE
    ):
        raise ValueError("historical exception denominator drift")
    if same_clock_flags != Counter({("0", "100"): EXPECTED_AMBIGUOUS}):
        raise ValueError("historical conflict settlement flag signature drift")
    if outside_lags != Counter({0: EXPECTED_OUTSIDE}):
        raise ValueError("historical outside-lag zero-day signature drift")
    if outside_source_event_months != Counter({"2010-11": EXPECTED_OUTSIDE}):
        raise ValueError("historical source publication month signature drift")
    return {
        "schema_version": 1, "issue": 482,
        "status": "source_pinned_diagnostic_only_no_reference_dates_promoted",
        "exception_records": {"same_clock": total_ambiguous,
                              "outside_lag": total_outside},
        "by_source_year": annual,
        "by_statistic_type": {name: dict(sorted(counts.items()))
                              for name, counts in sorted(reason_by_type.items())},
        "same_clock_shape_year_dates_versions": [
            {"year": year, "distinct_reference_dates": dates,
             "settlement_versions": versions, "records": n}
            for (year, dates, versions), n in sorted(same_clock_shape.items())
        ],
        "same_clock_flags": [
            {"flags": list(flags), "records": count}
            for flags, count in sorted(same_clock_flags.items())
        ],
        "same_clock_finality": [
            {"finality": list(flags), "records": count}
            for flags, count in sorted(same_clock_finality.items())
        ],
        "outside_calendar_lags": {str(k): v for k, v in sorted(outside_lags.items())},
        "independent_contract_date_confirmation": False,
        "publication_clocks_are_not_verified_original_exchange_reference_dates": True,
        "historical_dates_promoted": 0,
        "protected_confirmation_accessed": False,
    }


if __name__ == "__main__":
    print(json.dumps(inspect(), indent=2, sort_keys=True))
