"""Read-only, source-hash-pinned statistics-versus-normalized-Parquet diagnostic.

This is table-level lineage evidence, not the owner-approved V3 selection view.
No timestamps are reconstructed, no missing values filled, no research admission.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STAGE = ROOT / ".work/runtime/market_truth_development"
SOURCE = STAGE / "statistics-full-2010-2022-curated.csv"
OUTPUT = STAGE / "market-truth-full-2010-2022-refactor-v3/statistics.parquet"
SOURCE_MANIFEST = STAGE / "source-manifest-full-2010-2022-curated.json"
FINAL_MANIFEST = OUTPUT.parent / "manifest.json"
PINNED = {
    "source_manifest": "8a86789673c8458c5745f14b550f3c16b6e4885cac026578cb2989cbc80e5240",
    "final_manifest": "6d3093305c0ae2c6a313be13151b0810bf208c1cb8f429e1bbf58a17e7d89605",
    "source_statistics": "18990effe305c19b80ebc2fbfb29aa6f7752f440b68c9eb9d2cbef33a784377e",
    "final_statistics": "08238152f29f5e6c2296e098671448b0cb36470626faa421c6a461140f034e8b",
}


def sha256(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("required pinned statistic evidence missing")
    result = hashlib.sha256()
    with path.open("rb") as reader:
        for chunk in iter(lambda: reader.read(1 << 20), b""):
            result.update(chunk)
    return result.hexdigest()


def verify_pins() -> tuple[dict, dict]:
    actual = {
        "source_manifest": sha256(SOURCE_MANIFEST),
        "final_manifest": sha256(FINAL_MANIFEST),
        "source_statistics": sha256(SOURCE),
        "final_statistics": sha256(OUTPUT),
    }
    if actual != PINNED:
        raise RuntimeError("pinned source/final statistics changed")
    source = json.loads(SOURCE_MANIFEST.read_bytes())
    final = json.loads(FINAL_MANIFEST.read_bytes())
    if (
        source.get("evidence_class") != "development"
        or source.get("max_trade_date") != "2022-12-31"
        or source.get("protected_confirmation_accessed") is not False
        or final.get("dataset_scope") != "development_pre2023"
        or final.get("protected_confirmation_accessed") is not False
        or source["inputs"]["statistics"]["sha256"] != PINNED["source_statistics"]
        or final["tables"]["statistics"]["sha256"] != PINNED["final_statistics"]
        or final["source_manifest_sha256"] != PINNED["source_manifest"]
    ):
        raise RuntimeError("source/final statistic admission boundary changed")
    return source, final


def audit() -> dict:
    import duckdb

    source, final = verify_pins()
    db = duckdb.connect(":memory:")
    try:
        db.execute("SET memory_limit='768MB'")
        db.execute("SET TimeZone='UTC'")
        db.execute(
            f"""CREATE TEMP VIEW original AS
            SELECT
              CAST(instrument_id AS VARCHAR) AS instrument_id,
              CAST(trade_date AS VARCHAR) AS trade_date,
              CASE CAST(stat_type AS INTEGER)
                WHEN 3 THEN 'settle'
                WHEN 6 THEN 'cleared_volume'
                WHEN 9 THEN 'open_interest'
              END AS stat_type,
              CASE WHEN CAST(stat_type AS INTEGER) = 3
                THEN TRY_CAST(price AS DOUBLE)
                ELSE TRY_CAST(quantity AS DOUBLE)
              END AS value,
              GREATEST(CAST(ts_event AS TIMESTAMPTZ),
                       CAST(ts_recv AS TIMESTAMPTZ)) AS available_at,
              CAST(ts_event AS TIMESTAMPTZ) AS event_at,
              CASE
                WHEN CAST(stat_type AS INTEGER) != 3 THEN TRUE
                WHEN CAST(stat_flags AS INTEGER) IN (100,101)
                     OR (CAST(stat_flags AS INTEGER) & 8) != 0 THEN FALSE
                WHEN CAST(trade_date AS DATE) < DATE '2015-11-20' THEN TRUE
                ELSE (CAST(stat_flags AS INTEGER) & 1) = 1
              END AS eligible,
              CASE
                WHEN CAST(stat_type AS INTEGER) != 3 THEN 'non_settlement'
                WHEN CAST(stat_flags AS INTEGER) IN (100,101)
                     OR (CAST(stat_flags AS INTEGER) & 8) != 0
                     THEN 'rejected_preliminary_or_intraday'
                WHEN CAST(trade_date AS DATE) < DATE '2015-11-20'
                     THEN 'eligible_legacy'
                WHEN (CAST(stat_flags AS INTEGER) & 1) = 1
                     THEN 'eligible_final_bit'
                ELSE 'rejected_missing_final_bit'
              END AS policy_category
            FROM read_csv_auto('{SOURCE.as_posix()}', header=true, all_varchar=true, strict_mode=true)
            WHERE CAST(stat_type AS INTEGER) IN (3,6,9)""",
        )
        db.execute(
            f"CREATE TEMP VIEW final AS SELECT * FROM read_parquet('{OUTPUT.as_posix()}')"
        )
        source_rows, final_rows = db.execute(
            "SELECT (SELECT count(*) FROM read_csv_auto(?, header=true, all_varchar=true)),"
            " (SELECT count(*) FROM final)",
            [str(SOURCE)],
        ).fetchone()
        if (
            source_rows != source["inputs"]["statistics"]["row_count"]
            or final_rows != final["tables"]["statistics"]["rows"]
        ):
            raise RuntimeError("statistics source/final physical count changed")
        unmatched = db.execute(
            """SELECT f.stat_type, count(*)
               FROM final f ANTI JOIN original s
                 ON s.eligible AND f.instrument_id=s.instrument_id
                AND f.trade_date=s.trade_date
                AND f.stat_type=s.stat_type
                AND CAST(f.available_at AS TIMESTAMPTZ)=s.available_at
                AND CAST(f.event_at AS TIMESTAMPTZ)=s.event_at
                AND f.value=s.value
               GROUP BY f.stat_type ORDER BY f.stat_type"""
        ).fetchall()
        # Existence alone would accept a final duplicate substituting for another
        # fact. Enforce the native final revision grain and full-tuple multiset
        # containment before counting a final record as source-grounded.
        duplicate_final_grains = db.execute(
            """SELECT count(*) FROM (
                 SELECT instrument_id, trade_date, stat_type, available_at
                 FROM final GROUP BY ALL HAVING count(*) > 1
               )"""
        ).fetchone()[0]
        excess_final_occurrences = db.execute(
            """WITH final_counts AS (
                 SELECT instrument_id, trade_date, stat_type,
                   CAST(available_at AS TIMESTAMPTZ) AS available_at,
                   CAST(event_at AS TIMESTAMPTZ) AS event_at,
                   value, count(*) AS n
                 FROM final GROUP BY ALL
               ), source_counts AS (
                 SELECT instrument_id, trade_date, stat_type, available_at,
                   event_at, value, count(*) AS n
                 FROM original GROUP BY ALL
               )
               SELECT COALESCE(SUM(GREATEST(f.n-COALESCE(s.n,0),0)),0)
               FROM final_counts f LEFT JOIN source_counts s USING (
                 instrument_id, trade_date, stat_type, available_at,
                 event_at, value
               )"""
        ).fetchone()[0]
        policy_by_type = db.execute(
            """SELECT stat_type, policy_category, count(*)
               FROM original GROUP BY 1,2 ORDER BY 1,2"""
        ).fetchall()
        eligible_grains = db.execute(
            """WITH revisions AS (
                 SELECT instrument_id, trade_date, stat_type, available_at,
                        count(*) AS occurrences,
                        count(DISTINCT value) AS distinct_economic_values,
                        count(DISTINCT (event_at, value)) AS event_value_versions
                 FROM original WHERE eligible
                 GROUP BY 1,2,3,4
               )
               SELECT stat_type, SUM(occurrences) AS accepted_source_rows,
                      count(*) AS accepted_source_grains,
                      SUM(occurrences - 1) AS same_grain_retransmissions,
                      SUM(occurrences - event_value_versions) AS exact_tuples,
                      SUM(event_value_versions - 1) AS event_variants,
                      count(*) FILTER (WHERE distinct_economic_values > 1) AS conflicts
               FROM revisions GROUP BY stat_type ORDER BY stat_type"""
        ).fetchall()
        original_by_type = db.execute(
            "SELECT stat_type, count(*) FROM original GROUP BY stat_type ORDER BY stat_type"
        ).fetchall()
        final_by_type = db.execute(
            "SELECT stat_type, count(*) FROM final GROUP BY stat_type ORDER BY stat_type"
        ).fetchall()
    finally:
        db.close()
    verify_pins()
    expected_source = {
        "settle": 1594207,
        "cleared_volume": 344245,
        "open_interest": 344245,
    }
    expected_final = {
        "settle": 489214,
        "cleared_volume": 344243,
        "open_interest": 344243,
    }
    policy = {}
    for family, category, count in policy_by_type:
        policy.setdefault(family, {})[category] = count
    eligible_grain_summary = {
        family: {
            "eligible_original_occurrences": int(occurrences),
            "eligible_distinct_revision_grains": int(grains),
            "economic_equivalent_retransmissions": int(retransmissions),
            "exact_full_tuple_retransmissions": int(exact_tuples),
            "different_event_time_retransmissions": int(event_variants),
            "conflicting_eligible_values": int(conflicts),
        }
        for (family, occurrences, grains, retransmissions,
             exact_tuples, event_variants, conflicts) in eligible_grains
    }
    expected_policy = {
        "settle": {
            "eligible_final_bit": 316506,
            "eligible_legacy": 173235,
            "rejected_missing_final_bit": 661151,
            "rejected_preliminary_or_intraday": 443315,
        },
        "cleared_volume": {"non_settlement": 344245},
        "open_interest": {"non_settlement": 344245},
    }
    expected_retransmissions = {
        "settle": 527, "cleared_volume": 2, "open_interest": 2,
    }
    for family, metrics in eligible_grain_summary.items():
        if (
            metrics["eligible_distinct_revision_grains"]
            != dict(final_by_type).get(family)
            or metrics["conflicting_eligible_values"] != 0
            or metrics["economic_equivalent_retransmissions"]
            != expected_retransmissions.get(family)
            or (
                metrics["exact_full_tuple_retransmissions"]
                + metrics["different_event_time_retransmissions"]
                != metrics["economic_equivalent_retransmissions"]
            )
            or sum(policy.get(family, {}).values())
            != dict(original_by_type).get(family)
        ):
            raise RuntimeError("unreconciled policy exclusions or revisions")
    if policy != expected_policy or set(eligible_grain_summary) != set(expected_final):
        raise RuntimeError("statistic policy flags have changed")
    rejected = sum(
        count for groups in policy.values()
        for category, count in groups.items()
        if category.startswith("rejected_")
    )
    retransmissions = sum(
        metrics["economic_equivalent_retransmissions"]
        for metrics in eligible_grain_summary.values()
    )
    if rejected + retransmissions != source_rows - final_rows:
        raise RuntimeError("source-side exclusion ledger does not balance")
    if (
        unmatched
        or duplicate_final_grains
        or excess_final_occurrences
        or dict(original_by_type) != expected_source
        or dict(final_by_type) != expected_final
        or sum(dict(final_by_type).values()) != final_rows
        or sum(dict(original_by_type).values()) != source_rows
    ):
        raise RuntimeError("source or final statistics provenance mismatch")
    return {
        "schema_version": 1,
        "issue": 482,
        "result": "PINNED_STATISTICS_SOURCE_TO_FINAL_VALUE_DIAGNOSTIC",
        "source_sha256": PINNED["source_statistics"],
        "final_sha256": PINNED["final_statistics"],
        "source_manifest_sha256": PINNED["source_manifest"],
        "final_manifest_sha256": PINNED["final_manifest"],
        "source_rows": source_rows,
        "final_rows": final_rows,
        "unmatched_final_by_type": dict(unmatched),
        "duplicate_final_natural_grains": duplicate_final_grains,
        "excess_final_source_occurrences": excess_final_occurrences,
        "source_rows_by_type": dict(original_by_type),
        "final_rows_by_type": dict(final_by_type),
        "source_policy_by_type": policy,
        "eligible_source_revision_grains_by_type": eligible_grain_summary,
        "source_side_exclusion_total": int(source_rows - final_rows),
        "source_side_exclusion_policy_rejected": rejected,
        "source_side_economic_equivalent_retransmissions": retransmissions,
        "source_side_exact_full_tuple_retransmissions": sum(
            x["exact_full_tuple_retransmissions"]
            for x in eligible_grain_summary.values()
        ),
        "source_side_different_event_time_retransmissions": sum(
            x["different_event_time_retransmissions"]
            for x in eligible_grain_summary.values()
        ),
        "parquet_final_has_exact_source_row": len(unmatched) == 0,
        "scope": "raw dated source statistics to final table at exact instrument, date, type, availability, event and value",
        "not_verified": [
            "V3 snapshot selected as-of subset, curve rank, owner plotted comparison",
            "quarantined undated statistic rows and independent finality semantics",
            "independent CME expiry and external immutable storage",
            "owner research fitness or signed research admission",
        ],
        "protected_2023plus_accessed": False,
        "research_admitted": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True, indent=2))
