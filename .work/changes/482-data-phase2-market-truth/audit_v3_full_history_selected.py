"""One-pass source-versus-production-V3 selected OHLCV audit, preapproval only.

Reads exactly the SHA-256-pinned 2010-2022 development cohort. Never grants
catalog admission or infers historical source publication timestamps.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, date, datetime, time
from pathlib import Path

from commodity.market_truth.errors import MarketTruthError
from commodity.market_truth.ng_expiry import model_safe_ng_curve
from commodity.market_truth.protected_reads import protected_table_reads
from commodity.market_truth.review_site import (
    FINAL_BARS,
    FINAL_MANIFEST,
    SOURCE_CSV,
    SOURCE_MANIFEST,
    ReviewData,
    _VerifiedDiagnosticCurve,
)

METRICS = ("open", "high", "low", "close", "volume")
CONTENT_ID = "943780ea8eaa7315157385c687e3939777089420c186fd7d8d4b7d781a1f5d94"


def _new_bucket() -> dict:
    return {
        "numeric_pairs": 0, "exact": 0, "different": 0,
        "missing_source": 0, "null_value": 0, "unavailable_rank": 0,
        "excluded_rank": 0, "excluded_window": 0,
        "max_abs_delta": 0.0, "sum_abs_delta": 0.0,
    }


def update_bucket(bucket: dict, outcome: str, delta: float | None = None) -> None:
    """Preserve exclusions and null states separately from numeric equality."""
    if outcome not in {
        "numeric", "missing_source", "null_value", "unavailable_rank",
        "excluded_rank", "excluded_window",
    }:
        raise ValueError("unknown comparison outcome")
    if outcome != "numeric":
        bucket[outcome] += 1
        return
    if delta is None:
        raise ValueError("numeric comparison requires signed delta")
    bucket["numeric_pairs"] += 1
    if delta == 0:
        bucket["exact"] += 1
    else:
        bucket["different"] += 1
    difference = abs(delta)
    bucket["max_abs_delta"] = max(bucket["max_abs_delta"], difference)
    bucket["sum_abs_delta"] += difference


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()

def run() -> dict:
    review = ReviewData()
    selector = _VerifiedDiagnosticCurve()
    locked = [SOURCE_MANIFEST, SOURCE_CSV, FINAL_MANIFEST, *selector.files.values()]
    if review.meta["dataset_content_sha256"] != CONTENT_ID:
        raise MarketTruthError("unrecognized preapproval dataset identity")
    buckets = defaultdict(_new_bucket)
    exceptions = []
    scanned_sessions = 0
    with review.lock, protected_table_reads(locked):
        review._assert_current()
        # One bounded original bar load, avoiding 12 * 5 CSV scans per date.
        original_rows = review.db.execute(
            """SELECT CAST(instrument_id AS VARCHAR),
                      CAST(trade_date AS VARCHAR),
                      CAST(open AS DOUBLE), CAST(high AS DOUBLE),
                      CAST(low AS DOUBLE), CAST(close AS DOUBLE),
                      CAST(volume AS DOUBLE)
               FROM read_csv_auto(?, header=true, all_varchar=true, strict_mode=true)
               WHERE CAST(trade_date AS DATE) < DATE '2023-01-01'""",
            [str(SOURCE_CSV)],
        ).fetchall()
        if len(original_rows) != review.meta["source_rows"]:
            raise MarketTruthError("full-history source count changed")
        source = {}
        for instrument, day, *values in original_rows:
            key = (instrument, day)
            if key in source:
                raise MarketTruthError("duplicate full-history original contract/session")
            source[key] = dict(zip(METRICS, values, strict=True))
        days = [
            date.fromisoformat(str(row[0]))
            for row in review.db.execute(
                """SELECT DISTINCT CAST(trade_date AS DATE)
                   FROM read_parquet(?)
                   WHERE trade_date < '2023-01-01'
                     AND CAST(available_at AS TIMESTAMPTZ) <=
                         CAST(CAST(trade_date AS VARCHAR) ||
                              'T23:59:00+00:00' AS TIMESTAMPTZ)
                   ORDER BY 1""",
                [str(FINAL_BARS)],
            ).fetchall()
        ]
        if not days or any(not 2010 <= day.year <= 2022 for day in days):
            raise MarketTruthError("unexpected historical decision sessions")
        for day in days:
            scanned_sessions += 1
            cutoff = datetime.combine(day, time(23, 59), tzinfo=UTC)
            try:
                selected = model_safe_ng_curve(
                    selector._curve_from_parquet(review.db, day, cutoff, 12)
                )
            except MarketTruthError as exc:
                if "unverified CME historical expiry decision window" not in str(exc):
                    raise
                for rank in range(1, 13):
                    for metric in METRICS:
                        update_bucket(buckets[(day.year, rank, metric)], "excluded_window")
                continue
            if len(selected) != 12:
                raise MarketTruthError("production V3 did not return all twelve rank slots")
            for rank, point in enumerate(selected, 1):
                instrument = point["instrument_id"]
                status = point["rank_boundary_status"]
                original = source.get((str(instrument), day.isoformat())) if instrument else None
                for metric in METRICS:
                    bucket = buckets[(day.year, rank, metric)]
                    if status == "unverified_exchange_expiry_rank":
                        update_bucket(bucket, "excluded_rank")
                    elif instrument is None:
                        update_bucket(bucket, "unavailable_rank")
                    elif original is None:
                        update_bucket(bucket, "missing_source")
                    elif original[metric] is None or point[metric] is None:
                        update_bucket(bucket, "null_value")
                    else:
                        delta = float(point[metric]) - float(original[metric])
                        update_bucket(bucket, "numeric", delta)
                        if delta != 0 and len(exceptions) < 30:
                            exceptions.append({
                                "day": day.isoformat(), "rank": rank,
                                "metric": metric, "instrument_id": instrument,
                                "delta": delta,
                            })
        review._assert_current()
    if _hash(SOURCE_CSV) != review.meta["source_sha256"]:
        raise MarketTruthError("original source changed after audit")
    grouped = []
    total = _new_bucket()
    for (year, rank, metric), bucket in sorted(buckets.items()):
        for field in total:
            if field == "max_abs_delta":
                total[field] = max(total[field], bucket[field])
            else:
                total[field] += bucket[field]
        grouped.append({
            "year": year, "rank": rank, "metric": metric, **bucket,
            "mean_abs_delta": (bucket["sum_abs_delta"] / bucket["numeric_pairs"]
                               if bucket["numeric_pairs"] else None),
        })
    return {
        "schema_version": 1, "issue": 482,
        "status": "full_history_v3_selected_preapproval_diagnostic",
        "research_admitted": False, "source_pit_qualified": False,
        "protected_2023plus_accessed": False, "signed_owner_approval": False,
        "dataset_content_sha256": CONTENT_ID,
        "original_sha256": review.meta["source_sha256"],
        "final_sha256": review.meta["final_sha256"],
        "decision_clock_utc": "23:59",
        "scanned_sessions": scanned_sessions, "year_rank_field_groups": len(grouped),
        "totals": total, "by_year_rank_field": grouped,
        "first_value_differences": exceptions,
    }


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, indent=2))
