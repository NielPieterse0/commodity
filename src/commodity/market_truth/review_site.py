"""Private owner review site via loopback or authenticated Tailscale Serve.

Signed decisions are governed admission *candidates*, NEVER self-admission.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import secrets
import socket
import stat
import threading
from datetime import UTC, date, datetime, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import review_signing
from .errors import MarketTruthError
from .ng_expiry import model_safe_ng_curve
from .protected_reads import protected_table_reads
from .query import MarketTruthDataset

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / ".work/runtime/market_truth_development"
FINAL = DATA / "market-truth-full-2010-2022-refactor-v3"
SOURCE_MANIFEST = DATA / "source-manifest-full-2010-2022-curated.json"
SOURCE_CSV = DATA / "bars-full-2010-2022.csv"
FINAL_MANIFEST = FINAL / "manifest.json"
FINAL_BARS = FINAL / "bars.parquet"
ASSETS = Path(__file__).with_name("review_site_assets")
DECISIONS = DATA / "owner-approval-evidence/decisions"
METRICS = frozenset(("open", "high", "low", "close", "volume"))


def reconcile_definition_fields(db, source: Path, final: Path) -> dict:
    """Compare the whole original definition multiset to mapped final values.

    No source-time assumption is inferred: exchange expiry and finality remain
    independently unqualified. The source and Parquet bytes must be pinned by
    the caller before and after this read-only query.
    """
    query = """
        WITH original AS (
          SELECT CAST(instrument_id AS VARCHAR) AS instrument_id,
                 'NYMEX' AS venue, TRIM(raw_symbol) AS symbol,
                 CAST(expiration AS TIMESTAMPTZ) AS expiration,
                 GREATEST(CAST(ts_event AS TIMESTAMPTZ),
                          CAST(ts_recv AS TIMESTAMPTZ)) AS available_at,
                 CAST(ts_event AS TIMESTAMPTZ) AS event_at,
                 CAST(NULL AS TIMESTAMPTZ) AS last_trade_at,
                 CAST(10000 AS BIGINT) AS contract_size,
                 'USD/MMBtu' AS quote_unit, CAST(0.001 AS DOUBLE) AS tick_size,
                 CAST(NULL AS VARCHAR) AS source_vintage_id
          FROM read_csv_auto(?, header=true, all_varchar=true, strict_mode=true)
          WHERE asset='NG' AND instrument_class='F'
            AND exchange IN ('XNYM', 'NYMEX')
        ), normalized AS (
          SELECT instrument_id, venue, symbol,
                 CAST(expiration AS TIMESTAMPTZ) AS expiration,
                 CAST(available_at AS TIMESTAMPTZ) AS available_at,
                 CAST(event_at AS TIMESTAMPTZ) AS event_at,
                 CAST(last_trade_at AS TIMESTAMPTZ) AS last_trade_at,
                 contract_size, quote_unit, tick_size, source_vintage_id
          FROM read_parquet(?)
        ), missing AS (SELECT * FROM original EXCEPT ALL SELECT * FROM normalized),
           extra AS (SELECT * FROM normalized EXCEPT ALL SELECT * FROM original)
        SELECT (SELECT COUNT(*) FROM original),
               (SELECT COUNT(*) FROM normalized),
               (SELECT COUNT(*) FROM missing),
               (SELECT COUNT(*) FROM extra),
               (SELECT COUNT(*) FROM (
                  SELECT venue, instrument_id, available_at
                  FROM normalized GROUP BY ALL HAVING COUNT(*) > 1
               ))
    """
    original, normalized, missing, extra, duplicate = db.execute(
        query, [str(source), str(final)]
    ).fetchone()
    return {
        "source_rows": original, "final_rows": normalized,
        "source_only_field_tuples": missing, "final_only_field_tuples": extra,
        "duplicate_final_revision_grains": duplicate,
        "compared_fields": [
            "instrument_id", "venue", "symbol", "expiration",
            "available_at", "event_at", "last_trade_at", "contract_size",
            "quote_unit", "tick_size", "source_vintage_id",
        ],
        "exact": missing == 0 and extra == 0 and duplicate == 0,
        "research_admitted": False,
        "exchange_expiry_independently_verified": False,
    }


def reconcile_bar_fields(db, source: Path, final: Path) -> dict:
    """Compare every source/final OHLCV value at exact contract-session grain.

    This is normalized-fact reconciliation, not V3 admission or a PIT source
    certification. Duplicate keys reject the audit rather than multiplying joins.
    """
    source_ref, final_ref = str(source), str(final)
    for path, relation in (
        (source_ref, "read_csv_auto(?, header=true, all_varchar=true, strict_mode=true)"),
        (final_ref, "read_parquet(?)"),
    ):
        duplicates = db.execute(
            f"""SELECT COUNT(*) FROM (
                SELECT CAST(instrument_id AS VARCHAR), CAST(trade_date AS DATE)
                FROM {relation}
                GROUP BY 1, 2 HAVING COUNT(*) > 1
            )""", [path],
        ).fetchone()[0]
        if duplicates:
            raise MarketTruthError("duplicate original or final bar contract/session key")
    metric_values = ", ".join(
        f"('{metric}', s.{metric}, f.{metric})"
        for metric in ("open", "high", "low", "close", "volume")
    )
    values = ", ".join(
        f"CAST({metric} AS DOUBLE) AS {metric}"
        for metric in ("open", "high", "low", "close", "volume")
    )
    sql = f"""
        WITH s AS (
            SELECT CAST(instrument_id AS VARCHAR) AS instrument_id,
                   CAST(trade_date AS DATE) AS trade_date, {values},
                   TRUE AS present
            FROM read_csv_auto(?, header=true, all_varchar=true, strict_mode=true)
        ), f AS (
            SELECT CAST(instrument_id AS VARCHAR) AS instrument_id,
                   CAST(trade_date AS DATE) AS trade_date,
                   open, high, low, close, CAST(volume AS DOUBLE) AS volume,
                   TRUE AS present
            FROM read_parquet(?)
        ), paired AS (
            SELECT EXTRACT(YEAR FROM COALESCE(s.trade_date, f.trade_date)) AS yr,
                   m.metric, m.sv, m.fv,
                   COALESCE(s.present, FALSE) AS source_present,
                   COALESCE(f.present, FALSE) AS final_present
            FROM s FULL OUTER JOIN f USING (instrument_id, trade_date)
            CROSS JOIN LATERAL (VALUES {metric_values}) AS m(metric, sv, fv)
        )
        SELECT yr, metric,
               COUNT(*) FILTER (WHERE source_present) AS source_rows,
               COUNT(*) FILTER (WHERE final_present) AS final_rows,
               COUNT(*) FILTER (WHERE source_present AND final_present) AS paired_rows,
               COUNT(*) FILTER (WHERE source_present AND NOT final_present) AS source_only,
               COUNT(*) FILTER (WHERE final_present AND NOT source_present) AS final_only,
               COUNT(*) FILTER (WHERE source_present AND final_present
                                 AND sv IS NULL AND fv IS NULL) AS both_null,
               COUNT(*) FILTER (WHERE source_present AND final_present
                     AND ((sv IS NULL) != (fv IS NULL))) AS null_mismatch,
               COUNT(*) FILTER (WHERE source_present AND final_present
                     AND sv IS NOT NULL AND fv IS NOT NULL AND sv != fv) AS differing,
               COUNT(*) FILTER (WHERE source_present AND final_present
                     AND sv IS NOT NULL AND fv IS NOT NULL) AS numeric_pairs,
               MAX(ABS(fv - sv)) FILTER (WHERE source_present AND final_present)
                   AS max_abs_delta,
               SUM(ABS(fv - sv)) FILTER (WHERE source_present AND final_present)
                   AS sum_abs_delta
        FROM paired
        GROUP BY yr, metric
        ORDER BY yr, metric
    """
    fields = ("year", "metric", "source_rows", "final_rows", "paired_rows",
              "source_only", "final_only", "both_null", "null_mismatch",
              "differing", "numeric_pairs", "max_abs_delta", "sum_abs_delta")
    yearly = [dict(zip(fields, row)) for row in db.execute(
        sql, [source_ref, final_ref],
    ).fetchall()]
    if any(not isinstance(r["year"], int) or not 2010 <= r["year"] <= 2022
           for r in yearly):
        raise MarketTruthError("bar reconciliation includes out-of-scope year")
    aggregate = []
    for metric in ("open", "high", "low", "close", "volume"):
        rows = [r for r in yearly if r["metric"] == metric]
        totals = {name: sum(r[name] for r in rows) for name in (
            "source_rows", "final_rows", "paired_rows", "source_only",
            "final_only", "both_null", "null_mismatch", "differing", "numeric_pairs"
        )}
        total_delta = sum(r["sum_abs_delta"] or 0 for r in rows)
        totals.update(
            metric=metric,
            exact=(totals["source_only"] == totals["final_only"] ==
                   totals["null_mismatch"] == totals["differing"] == 0),
            max_abs_delta=max((r["max_abs_delta"] for r in rows
                               if r["max_abs_delta"] is not None), default=None),
            mean_abs_delta=(total_delta / totals["numeric_pairs"]
                            if totals["numeric_pairs"] else None),
        )
        aggregate.append(totals)
    return {
        "years": yearly, "metrics": aggregate,
        "exact": bool(yearly) and all(item["exact"] for item in aggregate),
        "research_admitted": False,
        "scope": "all pre-2023 normalized OHLCV facts; not V3 selection",
    }


class _VerifiedDiagnosticCurve:
    """Use the production V3 rank/revision selector on hash-pinned development files.

    This adapter does not instantiate or authorize an admitted MarketTruthDataset.
    It is restricted to the read-only owner-review diagnostic boundary.
    """

    _select = staticmethod(MarketTruthDataset._select)
    _curve_from_parquet = MarketTruthDataset._curve_from_parquet

    def __init__(self) -> None:
        self.files = {
            family: FINAL / f"{family}.parquet"
            for family in ("bars", "definitions", "statistics")
        }




def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _physical_rows(path: Path, *, csv_source: bool) -> int:
    """Count actual logical records, not manifest assertions or raw newline bytes."""
    import duckdb

    query = (
        "SELECT count(*) FROM read_csv_auto(?, header=true, all_varchar=true)"
        if csv_source
        else "SELECT count(*) FROM read_parquet(?)"
    )
    try:
        with duckdb.connect(":memory:") as connection:
            return int(connection.execute(query, [str(path)]).fetchone()[0])
    except duckdb.Error as exc:
        raise MarketTruthError("verified inventory file is not readable") from exc


def pinned_metadata(*, count_rows: bool = True) -> dict:
    """Verify all pinned bytes; initial admission also checks physical row counts."""
    source = json.loads(SOURCE_MANIFEST.read_bytes())
    final = json.loads(FINAL_MANIFEST.read_bytes())
    if (
        source.get("evidence_class") != "development"
        or source.get("max_trade_date") != "2022-12-31"
        or source.get("protected_confirmation_accessed") is not False
        or final.get("dataset_scope") != "development_pre2023"
        or final.get("protected_confirmation_accessed") is not False
        or final.get("source_manifest_sha256") != digest_file(SOURCE_MANIFEST)
    ):
        raise MarketTruthError("development-only source boundary is not verified")
    input_id = source["inputs"]["bars"]
    output_id = final["tables"]["bars"]
    if (
        input_id["relative_path"] != SOURCE_CSV.name
        or output_id["relative_path"] != FINAL_BARS.name
        or input_id["sha256"] != digest_file(SOURCE_CSV)
        or output_id["sha256"] != digest_file(FINAL_BARS)
    ):
        raise MarketTruthError("original or final historical data hash mismatch")
    families = {}
    for family in ("bars", "definitions", "statistics"):
        original = source["inputs"][family]
        imported = final["tables"][family]
        comparison = final["source_row_reconciliation"][family]
        expected_source = DATA / original["relative_path"]
        expected_final = FINAL / f"{family}.parquet"
        if (
            original["relative_path"] != {
                "bars": SOURCE_CSV.name,
                "definitions": "definitions-full-2010-2022.csv",
                "statistics": "statistics-full-2010-2022-curated.csv",
            }[family]
            or imported["relative_path"] != expected_final.name
            or not expected_source.is_file()
            or not expected_final.is_file()
            or digest_file(expected_source) != original["sha256"]
            or digest_file(expected_final) != imported["sha256"]
            or final["source_sha256"][family] != original["sha256"]
            or comparison["source_rows"] != original["row_count"]
            or comparison["normalized_rows"] != imported["rows"]
            or comparison["source_rows"] != (
                comparison["normalized_rows"]
                + comparison["excluded_or_exact_retransmissions"]
            )
        ):
            raise MarketTruthError(f"{family} source/final evidence mismatch")
        if count_rows and (
            _physical_rows(expected_source, csv_source=True) != original["row_count"]
            or _physical_rows(expected_final, csv_source=False) != imported["rows"]
        ):
            raise MarketTruthError(f"{family} physical row-count mismatch")
        families[family] = {
            "source_rows": original["row_count"],
            "final_rows": imported["rows"],
            "excluded_or_retransmissions": comparison[
                "excluded_or_exact_retransmissions"
            ],
            "source_sha256": original["sha256"],
            "final_sha256": imported["sha256"],
            "audit_level": "hash-bound counts; not row-by-row value parity",
        }
    return {
        "issue": 482,
        "scope": "2010–2022 / development diagnostic",
        "source_sha256": input_id["sha256"],
        "final_sha256": output_id["sha256"],
        "source_rows": input_id["row_count"],
        "final_rows": output_id["rows"],
        "families": families,
        "source_manifest_sha256": digest_file(SOURCE_MANIFEST),
        "final_manifest_sha256": digest_file(FINAL_MANIFEST),
        "dataset_content_sha256": final["content_sha256"],
        "approved": False,
        "research_admitted": False,
        "source_kind": "SHA-256-pinned decoded original Databento CSV",
        "final_kind": "Final normalized Parquet fact table (not admitted V3 snapshot)",
        "limitations": [
            "Undated statistics remain quarantined",
            "Historical CME expiry timestamps unverified; rank-dependent outputs safely excluded",
            "No signed source-owner admission",
            "No independent immutable storage certificate",
        ],
    }


STATISTICS_AUDIT_RECEIPT = (
    ROOT / ".work/changes/482-data-phase2-market-truth/"
    "statistics-source-final-value-receipt.json"
)
# This hash binds an existing completed source-value diagnostic, NOT admission.
STATISTICS_AUDIT_SHA256 = (
    "cc501c092bd3344ed28c7da0a1cc38edcf0038992dfc7387244545b124b3d309"
)


def _read_pinned_receipt(path: Path, expected_digest: str, max_bytes: int) -> dict:
    """Authenticate the exact bytes read via one retained, non-following handle."""
    try:
        if path.is_symlink():
            raise MarketTruthError("pinned receipt symlink not allowed")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            source_stat = os.fstat(stream.fileno())
            if not stat.S_ISREG(source_stat.st_mode) or not (
                0 < source_stat.st_size <= max_bytes
            ):
                raise MarketTruthError("pinned receipt is not a bounded regular file")
            raw = stream.read(max_bytes + 1)
    except OSError as exc:
        raise MarketTruthError("pinned receipt not verified") from exc
    if (
        len(raw) != source_stat.st_size
        or hashlib.sha256(raw).hexdigest() != expected_digest
    ):
        raise MarketTruthError("pinned receipt not verified")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise MarketTruthError("pinned receipt unreadable") from exc


def verify_statistics_receipt(path: Path, meta: dict) -> dict:
    """Re-use completed statistics evidence, rejecting tampering or false parity."""
    report = _read_pinned_receipt(path, STATISTICS_AUDIT_SHA256, 100_000)
    family = meta["families"]["statistics"]
    if (
        report.get("schema_version") != 1
        or report.get("issue") != 482
        or report.get("result") != "PINNED_STATISTICS_SOURCE_TO_FINAL_VALUE_DIAGNOSTIC"
        or report.get("source_sha256") != family["source_sha256"]
        or report.get("final_sha256") != family["final_sha256"]
        or report.get("source_manifest_sha256") != meta["source_manifest_sha256"]
        or report.get("final_manifest_sha256") != meta["final_manifest_sha256"]
        or report.get("source_rows") != family["source_rows"]
        or report.get("final_rows") != family["final_rows"]
        or report.get("research_admitted") is not False
        or report.get("protected_2023plus_accessed") is not False
        or report.get("parquet_final_has_exact_source_row") is not True
        or report.get("duplicate_final_natural_grains") != 0
        or report.get("excess_final_source_occurrences") != 0
        or report.get("unmatched_final_by_type") != {}
    ):
        raise MarketTruthError("statistics receipt identity or release boundary invalid")
    source_counts = report.get("source_rows_by_type")
    final_counts = report.get("final_rows_by_type")
    grains = report.get("eligible_source_revision_grains_by_type")
    types = ("settle", "open_interest", "cleared_volume")
    if (
        not all(isinstance(value, dict) for value in (source_counts, final_counts, grains))
        or set(source_counts) != set(types)
        or set(final_counts) != set(types)
        or set(grains) != set(types)
        or any(
            type(source_counts[k]) is not int or source_counts[k] < 0
            or type(final_counts[k]) is not int or final_counts[k] < 0
            or not isinstance(grains[k], dict)
            or grains[k].get("eligible_distinct_revision_grains") != final_counts[k]
            or grains[k].get("conflicting_eligible_values") != 0
            for k in types
        )
        or sum(source_counts.values()) != report["source_rows"]
        or sum(final_counts.values()) != report["final_rows"]
        or type(report.get("source_side_exclusion_total")) is not int
        or report["source_side_exclusion_total"] != (
            report["source_rows"] - report["final_rows"]
        )
        or report.get("source_side_exclusion_total") != (
            report.get("source_side_exclusion_policy_rejected", -1)
            + report.get("source_side_economic_equivalent_retransmissions", -1)
        )
    ):
        raise MarketTruthError("statistics receipt count or revision accounting invalid")
    return {
        "status": "pinned_preapproval_statistics_value_diagnostic",
        "research_admitted": False,
        "source_pit_qualified": False,
        "source_rows_by_type": source_counts,
        "final_rows_by_type": final_counts,
        "excluded_by_policy": report["source_side_exclusion_policy_rejected"],
        "excluded_retransmissions": report[
            "source_side_economic_equivalent_retransmissions"
        ],
        "source_only_occurrences": report["source_side_exclusion_total"],
        "final_unmatched": report["excess_final_source_occurrences"],
        "conflicting_eligible_values": 0,
        "source_sha256": family["source_sha256"],
        "final_sha256": family["final_sha256"],
        "dataset_content_sha256": meta["dataset_content_sha256"],
        "receipt_sha256": STATISTICS_AUDIT_SHA256,
        "limitations": (
            "Only eligible dated source statistics were normalized; undated "
            "records stay quarantined. No independent publication-time, "
            "settlement finality, owner approval or WORM certification."
        ),
    }


V3_AUDIT_RECEIPT = (
    ROOT / ".work/changes/482-data-phase2-market-truth/"
    "v3-full-history-selected-receipt.json"
)
# Independent integrity of this diagnostic publication is NOT a source-owner
# signature, research admission, or object-lock/immutable storage certificate.
V3_AUDIT_SHA256 = "46d7acaf4a70efeee86f7e6022539724de1eafab801093085efe3b18ef5e3ecf"
V3_AUDIT_STATUSES = (
    "numeric_pairs", "missing_source", "null_value", "unavailable_rank",
    "excluded_rank", "excluded_window",
)


def verify_v3_history_receipt(path: Path, meta: dict) -> dict:
    """Fail closed on missing/tampered or partially accounted full-history evidence.

    The digest pins a completed 2010-2022 *diagnostic* receipt to this code
    revision. Neither this pin nor the successful audit authenticates source PIT.
    """
    report = _read_pinned_receipt(path, V3_AUDIT_SHA256, 500_000)
    if (
        report.get("schema_version") != 1 or report.get("issue") != 482
        or report.get("status") != "full_history_v3_selected_preapproval_diagnostic"
        or report.get("decision_clock_utc") != "23:59"
        or report.get("dataset_content_sha256") != meta["dataset_content_sha256"]
        or report.get("original_sha256") != meta["source_sha256"]
        or report.get("final_sha256") != meta["final_sha256"]
        or report.get("research_admitted") is not False
        or report.get("signed_owner_approval") is not False
        or report.get("source_pit_qualified") is not False
        or report.get("protected_2023plus_accessed") is not False
        or type(report.get("scanned_sessions")) is not int
        or report["scanned_sessions"] < 1
    ):
        raise MarketTruthError("V3 historical receipt identity or boundaries invalid")
    groups = report.get("by_year_rank_field")
    if not isinstance(groups, list) or len(groups) != 13 * 12 * 5:
        raise MarketTruthError("V3 historical audit incomplete year/rank/field coverage")
    seen = set()
    totals = {name: 0 for name in (*V3_AUDIT_STATUSES, "exact", "different")}
    yearly: dict[int, dict] = {}
    counts_by_year = {}
    for item in groups:
        year, rank, metric = item.get("year"), item.get("rank"), item.get("metric")
        if (
            type(year) is not int or not 2010 <= year <= 2022
            or type(rank) is not int or not 1 <= rank <= 12
            or metric not in METRICS or (year, rank, metric) in seen
        ):
            raise MarketTruthError("V3 receipt duplicate or out-of-scope rank/field")
        seen.add((year, rank, metric))
        if any(type(item.get(name)) is not int or item[name] < 0 for name in totals):
            raise MarketTruthError("V3 receipt invalid comparison counts")
        if item["exact"] + item["different"] != item["numeric_pairs"]:
            raise MarketTruthError("V3 receipt incorrect numeric pair accounting")
        sessions = sum(item[name] for name in V3_AUDIT_STATUSES)
        if year in counts_by_year and counts_by_year[year] != sessions:
            raise MarketTruthError("V3 receipt rank/field sessions inconsistent")
        counts_by_year[year] = sessions
        bucket = yearly.setdefault(year, {name: 0 for name in totals})
        for name in totals:
            totals[name] += item[name]
            bucket[name] += item[name]
    reported = report.get("totals")
    if (
        not isinstance(reported, dict)
        or any(reported.get(name) != count for name, count in totals.items())
        or sum(counts_by_year.values()) != report["scanned_sessions"]
        or sum(totals[name] for name in V3_AUDIT_STATUSES)
        != report["scanned_sessions"] * 12 * len(METRICS)
        or report.get("year_rank_field_groups") != len(groups)
    ):
        raise MarketTruthError("V3 historical receipt slot accounting mismatch")
    return {
        "status": "verified_pinned_preapproval_diagnostic_only",
        "research_admitted": False,
        "owner_signed": False,
        "external_storage_required": False,
        "source_pit_qualified": False,
        "dataset_content_sha256": report["dataset_content_sha256"],
        "receipt_sha256": V3_AUDIT_SHA256,
        "scanned_sessions": report["scanned_sessions"],
        "classified_slots": report["scanned_sessions"] * 60,
        "groups": groups,
        "totals": totals,
        "by_year": [{"year": year, "sessions": counts_by_year[year], **yearly[year]}
                    for year in sorted(counts_by_year)],
    }


class ReviewData:
    def __init__(self) -> None:
        import duckdb

        self.meta = pinned_metadata()
        self.db = duckdb.connect(":memory:")
        self.lock = threading.RLock()

    def _assert_current(self) -> None:
        # Physical counts were established at open; exact hashes are checked again.
        current = pinned_metadata(count_rows=False)
        if current != self.meta:
            raise MarketTruthError("verified dataset identity changed; restart review")

    def v3_full_history_audit(self) -> dict:
        """Serve the exact historical V3 diagnostic receipt without rerunning it."""
        with self.lock, protected_table_reads([
            SOURCE_MANIFEST, SOURCE_CSV, FINAL_MANIFEST, FINAL_BARS,
            V3_AUDIT_RECEIPT,
        ]):
            self._assert_current()
            result = verify_v3_history_receipt(V3_AUDIT_RECEIPT, self.meta)
            self._assert_current()
            return result

    def statistics_audit(self) -> dict:
        """Expose the existing pinned statistics audit; never rerun source scans."""
        with self.lock, protected_table_reads([
            SOURCE_MANIFEST, FINAL_MANIFEST, STATISTICS_AUDIT_RECEIPT,
        ]):
            self._assert_current()
            result = verify_statistics_receipt(STATISTICS_AUDIT_RECEIPT, self.meta)
            self._assert_current()
            return result

    def definitions_audit(self) -> dict:
        """Reconcile all historical definition values under retained file locks."""
        source = DATA / "definitions-full-2010-2022.csv"
        final = FINAL / "definitions.parquet"
        with self.lock, protected_table_reads([
            SOURCE_MANIFEST, source, FINAL_MANIFEST, final,
        ]):
            self._assert_current()
            result = reconcile_definition_fields(self.db, source, final)
            self._assert_current()
            expected = self.meta["families"]["definitions"]
            if (result["source_rows"] != expected["source_rows"]
                    or result["final_rows"] != expected["final_rows"]):
                raise MarketTruthError("definition reconciliation row count mismatch")
            return {
                **result,
                "source_sha256": expected["source_sha256"],
                "final_sha256": expected["final_sha256"],
                "dataset_content_sha256": self.meta["dataset_content_sha256"],
                "evidence_scope": "pre-approval original-to-final definition values",
            }

    def bars_audit(self) -> dict:
        """Reconcile all original OHLCV rows, without accepting research data."""
        with self.lock, protected_table_reads([
            SOURCE_MANIFEST, SOURCE_CSV, FINAL_MANIFEST, FINAL_BARS,
        ]):
            self._assert_current()
            result = reconcile_bar_fields(self.db, SOURCE_CSV, FINAL_BARS)
            self._assert_current()
            expected = self.meta["families"]["bars"]
            if any(
                metric["source_rows"] != expected["source_rows"]
                or metric["final_rows"] != expected["final_rows"]
                for metric in result["metrics"]
            ):
                raise MarketTruthError("bar reconciliation total count mismatch")
            return {
                **result,
                "source_sha256": expected["source_sha256"],
                "final_sha256": expected["final_sha256"],
                "dataset_content_sha256": self.meta["dataset_content_sha256"],
            }

    def contracts(self, year: int) -> list[dict]:
        with self.lock:
            self._assert_current()
            rows = self.db.execute(
                """
                WITH original AS (
                    SELECT CAST(instrument_id AS VARCHAR) AS instrument_id,
                           COUNT(*) AS source_rows
                    FROM read_csv_auto(?, header=true)
                    WHERE trade_date >= CAST(? AS DATE) AND trade_date < CAST(? AS DATE)
                    GROUP BY 1
                ), imported AS (
                    SELECT instrument_id, COUNT(*) AS final_rows
                    FROM read_parquet(?)
                    WHERE trade_date >= ? AND trade_date < ?
                    GROUP BY 1
                ), combined AS (
                    SELECT COALESCE(o.instrument_id, i.instrument_id) AS instrument_id,
                           COALESCE(o.source_rows, 0) AS source_rows,
                           COALESCE(i.final_rows, 0) AS final_rows
                    FROM original o FULL OUTER JOIN imported i USING (instrument_id)
                )
                SELECT c.instrument_id,
                       COALESCE(d.symbol, 'ID ' || c.instrument_id) AS symbol,
                       GREATEST(c.source_rows, c.final_rows) AS observations,
                       c.source_rows, c.final_rows
                FROM combined c LEFT JOIN (
                    SELECT instrument_id, arg_max(symbol, available_at) AS symbol
                    FROM read_parquet(?)
                    WHERE CAST(available_at AS TIMESTAMPTZ) < CAST(? AS TIMESTAMPTZ)
                    GROUP BY instrument_id
                ) d USING (instrument_id)
                ORDER BY CASE WHEN c.source_rows=0 OR c.final_rows=0 THEN 0 ELSE 1 END,
                         observations DESC, symbol, c.instrument_id
            """,
                [
                    str(SOURCE_CSV),
                    f"{year}-01-01",
                    f"{year + 1}-01-01",
                    str(FINAL_BARS),
                    f"{year}-01-01",
                    f"{year + 1}-01-01",
                    str(FINAL / "definitions.parquet"),
                    f"{year + 1}-01-01",
                ],
            ).fetchall()
            return [
                {
                    "id": row[0],
                    "symbol": row[1],
                    "observations": row[2],
                    "source_rows": row[3],
                    "final_rows": row[4],
                }
                for row in rows
            ]

    def series(self, year: int, instrument_id: str, metric: str) -> dict:
        if (
            metric not in METRICS
            or not instrument_id.isdecimal()
            or len(instrument_id) > 12
        ):
            raise ValueError("unknown metric or instrument")
        with self.lock:
            self._assert_current()
            # Identical source contract ID and trade date; no calendar-only joins.
            sql = f"""
                WITH source AS (
                    SELECT CAST(instrument_id AS VARCHAR) AS instrument_id,
                           CAST(trade_date AS VARCHAR) AS trade_date,
                           CAST({metric} AS DOUBLE) AS source_value, TRUE AS source_present,
                           COUNT(*) OVER (PARTITION BY instrument_id, trade_date) AS source_key_count
                    FROM read_csv_auto(?, header=true)
                    WHERE CAST(instrument_id AS VARCHAR)=?
                      AND trade_date>=CAST(? AS DATE) AND trade_date<CAST(? AS DATE)
                ), final AS (
                    SELECT instrument_id,trade_date,
                           CAST({metric} AS DOUBLE) AS final_value, TRUE AS final_present,
                           COUNT(*) OVER (PARTITION BY instrument_id, trade_date) AS final_key_count
                    FROM read_parquet(?)
                    WHERE instrument_id=? AND trade_date>=? AND trade_date<?
                )
                SELECT COALESCE(source.trade_date,final.trade_date) AS day,
                       source_value, final_value,
                       COALESCE(source_present,FALSE) AS s_present,
                       COALESCE(final_present,FALSE) AS f_present,
                       source_key_count, final_key_count
                FROM source FULL OUTER JOIN final USING(instrument_id,trade_date)
                ORDER BY day
            """
            args = [
                str(SOURCE_CSV),
                instrument_id,
                f"{year}-01-01",
                f"{year + 1}-01-01",
                str(FINAL_BARS),
                instrument_id,
                f"{year}-01-01",
                f"{year + 1}-01-01",
            ]
            results = self.db.execute(sql, args).fetchall()
            if any(
                (source_count or 0) > 1 or (final_count or 0) > 1
                for _, _, _, _, _, source_count, final_count in results
            ):
                raise MarketTruthError(
                    "duplicate instrument/date source or final key: reconciliation blocked"
                )
            points = []
            for day, source, final, s_present, f_present, _, _ in results:
                delta = (
                    final - source if source is not None and final is not None else None
                )
                if not s_present:
                    status = "final_only"
                elif not f_present:
                    status = "source_only"
                elif (source is None) != (final is None):
                    status = "null_mismatch"
                elif delta is not None and delta != 0:
                    status = "value_mismatch"
                elif source is None:
                    status = "both_null"
                else:
                    status = "equal"
                points.append(
                    {
                        "date": day,
                        "source": source,
                        "final": final,
                        "delta": delta,
                        "source_present": s_present,
                        "final_present": f_present,
                        "status": status,
                    }
                )
            paired = [p for p in points if p["source_present"] and p["final_present"]]
            numeric_pairs = [p for p in paired if p["delta"] is not None]
            differences = [
                p for p in paired if p["status"] in ("null_mismatch", "value_mismatch")
            ]
            missing = [p for p in points if p["status"] == "source_only"]
            extra = [p for p in points if p["status"] == "final_only"]
            return {
                "instrument_id": instrument_id,
                "year": year,
                "metric": metric,
                "points": points,
                "summary": {
                    "source": sum(point["source_present"] for point in points),
                    "final": sum(point["final_present"] for point in points),
                    "matched": len(paired),
                    "different": len(differences),
                    "null_mismatches": sum(
                        p["status"] == "null_mismatch" for p in paired
                    ),
                    "both_null": sum(p["status"] == "both_null" for p in paired),
                    "numeric_pairs": len(numeric_pairs),
                    "missing_final": len(missing),
                    "extra_final": len(extra),
                    "max_abs_delta": max(
                        (abs(p["delta"]) for p in numeric_pairs), default=None
                    ),
                    "mean_abs_delta": (
                        sum(abs(p["delta"]) for p in numeric_pairs) / len(numeric_pairs)
                    )
                    if numeric_pairs
                    else None,
                },
            }


    def v3_series(
        self, year: int, end_day: str, clock: str, rank: int,
        metric: str, window: str = "20",
    ) -> dict:
        """Display the actual production V3 rank selector before admission.

        Diagnostic only: original source is not retrospectively declared PIT-
        available, and the selection is not an approved research snapshot.
        """
        import re

        if (window not in {"20", "year"}
                or metric not in METRICS or type(rank) is not int or not 1 <= rank <= 12
                or not isinstance(clock, str)
                or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock)
                or not isinstance(end_day, str)
                or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end_day)):
            raise ValueError("invalid V3 review selection")
        target = date.fromisoformat(end_day)
        if year != validate_year(str(year)) or target.year != year:
            raise ValueError("V3 review date outside selected pre-2023 year")
        with self.lock:
            selector = _VerifiedDiagnosticCurve()
            locked_files = [
                SOURCE_MANIFEST, SOURCE_CSV, FINAL_MANIFEST,
                *selector.files.values(),
            ]
            with protected_table_reads(locked_files):
                self._assert_current()
                # Session membership must be observable at the requested
                # decision clock, not inferred from rows published later.
                # All candidate sessions use their own calendar-day cutoff.
                days = [
                    date.fromisoformat(str(row[0]))
                    for row in reversed(self.db.execute(
                        """SELECT DISTINCT trade_date
                           FROM read_parquet(?)
                           WHERE trade_date >= ? AND trade_date <= ?
                             AND CAST(available_at AS TIMESTAMPTZ) <=
                               CAST(CAST(trade_date AS VARCHAR) || 'T' ||
                                    ? || ':00+00:00' AS TIMESTAMPTZ)
                           ORDER BY trade_date DESC LIMIT ?""",
                        [str(FINAL_BARS), f"{year}-01-01", end_day, clock,
                         20 if window == "20" else 400],
                    ).fetchall())
                ]
                points = []
                previous_identity = None
                for session in days:
                    cutoff = datetime.combine(
                        session, time(int(clock[:2]), int(clock[3:])), tzinfo=UTC,
                    )
                    try:
                        selected = model_safe_ng_curve(selector._curve_from_parquet(
                            self.db, session, cutoff, 12,
                        ))[rank - 1]
                    except MarketTruthError as exc:
                        if "unverified CME historical expiry decision window" not in str(exc):
                            raise
                        # Display the deliberate model-denial as a missing-data
                        # decision, never as an observed zero or an unlisted rank.
                        points.append({
                            "date": session.isoformat(), "source": None,
                            "final": None, "delta": None,
                            "source_present": False, "final_present": False,
                            "status": "excluded_unverified_expiry_window",
                            "instrument_id": None, "contract_symbol": None,
                            "contract_identity": None,
                            "rank_boundary_status": "excluded_unverified_expiry_window",
                            "roll_transition": None, "selected_available_at": None,
                            "evidence_ids": [],
                        })
                        previous_identity = None
                        continue
                    instrument = selected["instrument_id"]
                    original = []
                    if instrument is not None:
                        original = self.db.execute(
                            f"""SELECT CAST({metric} AS DOUBLE)
                                FROM read_csv_auto(?, header=true)
                                WHERE CAST(instrument_id AS VARCHAR)=?
                                AND trade_date=CAST(? AS DATE)""",
                            [str(SOURCE_CSV), str(instrument), session.isoformat()],
                        ).fetchall()
                    if len(original) > 1:
                        raise MarketTruthError("duplicate selected original source key")
                    source_present = bool(original)
                    source = original[0][0] if original else None
                    final_present = False
                    if instrument is not None:
                        final_present = bool(self.db.execute(
                            """SELECT count(*) FROM read_parquet(?)
                               WHERE instrument_id=? AND trade_date=?
                               AND CAST(available_at AS TIMESTAMPTZ) <=
                                   CAST(? AS TIMESTAMPTZ)""",
                            [str(FINAL_BARS), instrument, session.isoformat(),
                             cutoff.isoformat()],
                        ).fetchone()[0])
                    final = selected[metric]
                    delta = final - source if source is not None and final is not None else None
                    identity = selected["contract_identity"]
                    roll = (previous_identity is not None and identity is not None
                            and identity != previous_identity)
                    previous_identity = identity
                    if selected["rank_boundary_status"] == "unverified_exchange_expiry_rank":
                        status = "excluded_unverified_expiry_rank"
                    elif instrument is None:
                        status = "not_listed"
                    elif not source_present and not final_present:
                        status = "unavailable"
                    elif not source_present:
                        status = "final_only"
                    elif not final_present:
                        status = "source_only"
                    elif (source is None) != (final is None):
                        status = "null_mismatch"
                    elif source is None:
                        status = "both_null"
                    elif delta != 0:
                        status = "value_mismatch"
                    else:
                        status = "equal"
                    points.append({
                        "date": session.isoformat(), "source": source,
                        "final": final, "delta": delta,
                        "source_present": source_present,
                        "final_present": final_present,
                        "status": status, "instrument_id": instrument,
                        "contract_symbol": selected["contract_symbol"],
                        "contract_identity": identity,
                        "rank_boundary_status": selected["rank_boundary_status"],
                        "roll_transition": roll, "selected_available_at": selected["available_at"],
                        "evidence_ids": selected["evidence_ids"],
                    })
                self._assert_current()
        numeric = [p["delta"] for p in points if p["delta"] is not None]
        return {
            "selection": "production_V3_curve_selector_preapproval_diagnostic",
            "research_admitted": False,
            "source_pit_status": "raw_original_not_independently_PIT_qualified",
            "dataset_content_sha256": self.meta["dataset_content_sha256"],
            "year": year, "rank": rank, "metric": metric, "cutoff_clock_utc": clock,
            "window": window, "year_complete_through": end_day if window == "year" else None,
            "points": points,
            "summary": {
                "matched": sum(p["source_present"] and p["final_present"] for p in points),
                "different": sum(
                    p["status"] in ("value_mismatch", "null_mismatch")
                    for p in points
                ),
                "missing_final": sum(p["status"] == "source_only" for p in points),
                "extra_final": sum(p["status"] == "final_only" for p in points),
                "both_null": sum(p["status"] == "both_null" for p in points),
                "numeric_pairs": len(numeric),
                "roll_transitions": sum(bool(p["roll_transition"]) for p in points),
                "unverified_expiry_boundaries": sum(
                    p["rank_boundary_status"] in (
                        "expiry_fallback_unverified", "unverified_exchange_expiry_rank",
                        "excluded_unverified_expiry_window",
                    )
                    for p in points
                ),
                "excluded_unverified_expiry_rank": sum(
                    p["status"] == "excluded_unverified_expiry_rank"
                    for p in points
                ),
                "excluded_unverified_expiry_window": sum(
                    p["status"] == "excluded_unverified_expiry_window"
                    for p in points
                ),
                "max_abs_delta": max(map(abs, numeric), default=None),
                "mean_abs_delta": (sum(map(abs, numeric)) / len(numeric)) if numeric else None,
            },
        }

def _decision_payload(body: dict, meta: dict) -> dict:
    """Never mint an independently signed catalog record from a UI event."""
    if set(body) != {
        "decision",
        "reviewer",
        "notes",
        "dataset_content_sha256",
        "acknowledge_not_admitted",
    }:
        raise ValueError("invalid decision fields")
    if body["decision"] not in {"approve", "reject", "needs_review"}:
        raise ValueError("invalid decision")
    reviewer, notes = body["reviewer"], body["notes"]
    if (
        not isinstance(reviewer, str)
        or not reviewer.strip()
        or len(reviewer) > 80
        or not isinstance(notes, str)
        or len(notes) > 2000
        or body["dataset_content_sha256"] != meta["dataset_content_sha256"]
        or body["acknowledge_not_admitted"] is not True
    ):
        raise ValueError("review identity, notes or dataset identity invalid")
    return {
        "schema_version": 1,
        "issue": 482,
        "decision": body["decision"],
        "reviewer_label_unverified": reviewer.strip(),
        "notes": notes.strip(),
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_csv_sha256": meta["source_sha256"],
        "final_parquet_sha256": meta["final_sha256"],
        "dataset_content_sha256": meta["dataset_content_sha256"],
        "evidence_type": "LOCAL_UNSIGNED_OWNER_REVIEW_INTENT_ONLY",
        "signed_admission": False,
        "external_storage_required": False,
        "research_admitted": False,
    }


def validate_year(value: str) -> int:
    if not value.isdecimal() or not 2010 <= int(value) <= 2022:
        raise ValueError("review date outside pre-2023 development cohort")
    return int(value)


def _verified_tailscale_service_pid() -> int | None:
    """Read the running service identity from Windows SCM, not process ACLs.

    Tailscaled runs as LocalSystem and may deny user OpenProcess requests.
    SCM independently supplies the running service PID and pinned service binary.
    A missing, changed or stopped service fails closed.
    """
    if os.name != "nt":
        return None
    from ctypes import wintypes

    class ServiceStatus(ctypes.Structure):
        _fields_ = [(field, wintypes.DWORD) for field in (
            "service_type", "state", "controls", "win_exit", "service_exit",
            "checkpoint", "wait_hint", "pid", "flags",
        )]

    class ServiceConfig(ctypes.Structure):
        _fields_ = [
            ("service_type", wintypes.DWORD),
            ("start_type", wintypes.DWORD),
            ("error_control", wintypes.DWORD),
            ("binary_path", wintypes.LPWSTR),
            ("load_order_group", wintypes.LPWSTR),
            ("tag_id", wintypes.DWORD),
            ("dependencies", wintypes.LPWSTR),
            ("service_account", wintypes.LPWSTR),
            ("display_name", wintypes.LPWSTR),
        ]

    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    api.OpenSCManagerW.restype = wintypes.HANDLE
    api.OpenServiceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
    api.OpenServiceW.restype = wintypes.HANDLE
    api.QueryServiceStatusEx.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.BYTE),
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]
    api.QueryServiceStatusEx.restype = wintypes.BOOL
    api.QueryServiceConfigW.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    api.QueryServiceConfigW.restype = wintypes.BOOL
    api.CloseServiceHandle.argtypes = [wintypes.HANDLE]
    api.CloseServiceHandle.restype = wintypes.BOOL
    manager = api.OpenSCManagerW(None, None, 0x0001)
    if not manager:
        return None
    try:
        service = api.OpenServiceW(manager, "Tailscale", 0x0005)
        if not service:
            return None
        try:
            status = ServiceStatus()
            needed = wintypes.DWORD()
            if not api.QueryServiceStatusEx(
                service, 0,
                ctypes.cast(ctypes.byref(status), ctypes.POINTER(wintypes.BYTE)),
                ctypes.sizeof(status), ctypes.byref(needed),
            ):
                return None
            if status.state != 4 or status.service_type != 0x10 or status.pid <= 4:
                return None
            buffer = ctypes.create_string_buffer(8192)
            if not api.QueryServiceConfigW(
                service, buffer, len(buffer), ctypes.byref(needed),
            ):
                return None
            config = ctypes.cast(buffer, ctypes.POINTER(ServiceConfig)).contents
            binary = (config.binary_path or "").strip('"')
            pinned = r"C:\Program Files\Tailscale\tailscaled.exe"
            if os.path.normcase(binary) != os.path.normcase(pinned):
                return None
            if config.service_account != "LocalSystem":
                return None
            # A same-account local caller could forge child ancestry only if
            # it could acquire PROCESS_CREATE_PROCESS on the protected service.
            # Refuse to trust this service when that right is available or
            # when Windows cannot prove the expected access-denied boundary.
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [
                wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
            ]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.restype = wintypes.BOOL
            parent_handle = kernel.OpenProcess(0x0080, False, status.pid)
            if parent_handle:
                kernel.CloseHandle(parent_handle)
                return None
            if ctypes.get_last_error() != 5:  # ERROR_ACCESS_DENIED
                return None
            return int(status.pid)
        finally:
            api.CloseServiceHandle(service)
    finally:
        api.CloseServiceHandle(manager)


def _verified_tailscale_proxy_process(pid: int, service_pid: int) -> bool:
    """Accept the pinned SCM service or its same-session tailscaled child.

    Windows Tailscale Serve's TCP proxy runs in a direct service child. The
    parent is validated against the independently queried live SCM service.
    Arbitrary same-name processes without that parent are not trusted.
    """
    if os.name != "nt" or pid <= 4:
        return False
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD), ("usage", wintypes.DWORD),
            ("pid", wintypes.DWORD), ("heap", ctypes.c_size_t),
            ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
            ("parent", wintypes.DWORD), ("priority", wintypes.LONG),
            ("flags", wintypes.DWORD), ("name", wintypes.WCHAR * 260),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # Protected system-owned Tailscale children deny process-token queries.
    # Kernel snapshot ancestry is bound to the live SCM service PID instead.
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return False
    try:
        entry = ProcessEntry()
        entry.size = ctypes.sizeof(entry)
        if not kernel.Process32FirstW(snapshot, ctypes.byref(entry)):
            return False
        while True:
            if entry.pid == pid:
                return bool(
                    entry.name.casefold() == "tailscaled.exe"
                    and (pid == service_pid or entry.parent == service_pid)
                )
            if not kernel.Process32NextW(snapshot, ctypes.byref(entry)):
                return False
    finally:
        kernel.CloseHandle(snapshot)


def _trusted_tailscale_proxy_client(peer_port: int, listener_port: int) -> bool:
    """Require a Windows loopback socket owned by the verified Tailscale service.

    Reject untrusted identity headers unless kernel TCP ownership and SCM's
    running service identity agree in two checks; deny missing evidence.
    """
    if os.name != "nt":
        return False
    from ctypes import wintypes

    class TcpOwner(ctypes.Structure):
        _fields_ = [
            ("state", wintypes.DWORD), ("local_addr", wintypes.DWORD),
            ("local_port", wintypes.DWORD), ("remote_addr", wintypes.DWORD),
            ("remote_port", wintypes.DWORD), ("pid", wintypes.DWORD),
        ]

    iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
    size = wintypes.ULONG()
    iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), False, 2, 5, 0)
    if not 4 <= size.value <= 4_000_000:
        return False
    table = ctypes.create_string_buffer(size.value)
    if iphlpapi.GetExtendedTcpTable(table, ctypes.byref(size), False, 2, 5, 0):
        return False
    count = wintypes.DWORD.from_buffer_copy(table).value
    if count > (size.value - 4) // ctypes.sizeof(TcpOwner):
        return False
    service_pid = _verified_tailscale_service_pid()
    if service_pid is None:
        return False
    for index in range(count):
        row = TcpOwner.from_buffer_copy(table, 4 + index * ctypes.sizeof(TcpOwner))
        if (
            socket.ntohs(row.local_port & 0xFFFF) != peer_port
            or socket.ntohs(row.remote_port & 0xFFFF) != listener_port
            or row.local_addr.to_bytes(4, "little") != b"\x7f\x00\x00\x01"
            or row.remote_addr.to_bytes(4, "little") != b"\x7f\x00\x00\x01"
        ):
            continue
        if not _verified_tailscale_proxy_process(row.pid, service_pid):
            continue
        # Recheck the kernel socket row, daemon ancestry, and live SCM identity.
        # A forged child must acquire the protected service as its parent.
        again_size = wintypes.ULONG()
        iphlpapi.GetExtendedTcpTable(
            None, ctypes.byref(again_size), False, 2, 5, 0
        )
        if not 4 <= again_size.value <= 4_000_000:
            return False
        again = ctypes.create_string_buffer(again_size.value)
        if iphlpapi.GetExtendedTcpTable(
            again, ctypes.byref(again_size), False, 2, 5, 0
        ):
            return False
        again_count = wintypes.DWORD.from_buffer_copy(again).value
        if again_count > (again_size.value - 4) // ctypes.sizeof(TcpOwner):
            return False
        if (_verified_tailscale_service_pid() != service_pid
                or not _verified_tailscale_proxy_process(row.pid, service_pid)):
            return False
        source = bytes(table[
            4 + index * ctypes.sizeof(TcpOwner):
            4 + (index + 1) * ctypes.sizeof(TcpOwner)
        ])
        return any(
            bytes(again[
                4 + n * ctypes.sizeof(TcpOwner):
                4 + (n + 1) * ctypes.sizeof(TcpOwner)
            ]) == source
            for n in range(again_count)
        )
    return False


def make_handler(review: ReviewData, token: str, *,
                 tailscale_host: str | None = None,
                 owner_login: str | None = None):
    if bool(tailscale_host) != bool(owner_login):
        raise ValueError("Tailscale hostname and owner login must be configured together")
    host = tailscale_host.lower().rstrip(".") if tailscale_host else None
    if host and (not host.endswith(".ts.net") or "/" in host or ":" in host):
        raise ValueError("invalid Tailscale Serve hostname")
    owner = owner_login.strip().casefold() if owner_login else None

    class Handler(BaseHTTPRequestHandler):
        server_version = "CommodityOwnerReview/1.0"

        def _origin(self) -> str:
            if host and self.headers.get("Host", "").lower() == host:
                return f"https://{host}"
            return f"http://127.0.0.1:{self.server.server_port}"

        def _mobile_owner(self) -> bool:
            return bool(
                host and owner
                and self.headers.get("Host", "").lower() == host
                and self.headers.get("Tailscale-User-Login", "").casefold() == owner
                and _trusted_tailscale_proxy_client(
                    self.client_address[1], self.server.server_port
                )
            )

        def _headers_ok(self) -> bool:
            if self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}":
                # Direct localhost is trusted only without proxy/identity headers.
                return not any(self.headers.get(header) for header in (
                    "Tailscale-User-Login", "X-Forwarded-For",
                    "X-Forwarded-Host", "X-Forwarded-Proto",
                ))
            return self._mobile_owner()

        def _send(self, code: int, data: bytes, mime: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'self'; script-src 'self'; "
                "connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'self'",
            )
            self.end_headers()
            self.wfile.write(data)

        def _json(self, value: dict | list, code: int = 200) -> None:
            self._send(
                code,
                json.dumps(value, separators=(",", ":"), allow_nan=False).encode(
                    "utf-8"
                ),
                "application/json",
            )

        def do_GET(self) -> None:
            if not self._headers_ok():
                return self._json({"error": "invalid host"}, 403)
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/meta":
                    self._json({"data": review.meta, "review_token": token,
                                "signing_ready": (
                                    review_signing.PRIVATE_KEY.is_file()
                                    and review_signing.PUBLIC_KEY.is_file()
                                    and review_signing.approval_code_ready(
                                        review.meta["dataset_content_sha256"]
                                    )
                                )})
                elif parsed.path == "/api/definitions-audit":
                    self._json(review.definitions_audit())
                elif parsed.path == "/api/statistics-audit":
                    self._json(review.statistics_audit())
                elif parsed.path == "/api/bars-audit":
                    self._json(review.bars_audit())
                elif parsed.path == "/api/v3-full-history-audit":
                    self._json(review.v3_full_history_audit())
                elif parsed.path == "/api/contracts":
                    year = validate_year(
                        parse_qs(parsed.query).get("year", ["2022"])[0]
                    )
                    self._json(review.contracts(year))
                elif parsed.path == "/api/series":
                    qs = parse_qs(parsed.query)
                    year = validate_year(qs.get("year", ["2022"])[0])
                    self._json(
                        review.series(
                            year, qs.get("id", [""])[0], qs.get("metric", ["close"])[0]
                        )
                    )
                elif parsed.path == "/api/v3-series":
                    qs = parse_qs(parsed.query)
                    year = validate_year(qs.get("year", ["2022"])[0])
                    self._json(review.v3_series(
                        year, qs.get("end_day", [""])[0],
                        qs.get("clock", ["23:59"])[0],
                        int(qs.get("rank", ["1"])[0]),
                        qs.get("metric", ["close"])[0],
                        window=qs.get("window", ["20"])[0],
                    ))
                elif parsed.path == "/api/signed-decisions":
                    if not review_signing.SIGNED_DECISIONS.is_dir():
                        return self._json([])
                    records = []
                    for path in sorted(review_signing.SIGNED_DECISIONS.glob("*.json"), reverse=True)[:25]:
                        record = json.loads(path.read_bytes())
                        review_signing.verify_signed_receipt(record)
                        if record.get("review", {}).get("dataset_content_sha256") == review.meta["dataset_content_sha256"]:
                            records.append(record)
                    self._json(records)
                elif parsed.path == "/api/decisions":
                    if not DECISIONS.exists():
                        return self._json([])
                    receipts = []
                    for path in sorted(DECISIONS.glob("*.json"), reverse=True)[:25]:
                        data = json.loads(path.read_bytes())
                        if (
                            data.get("dataset_content_sha256")
                            == review.meta["dataset_content_sha256"]
                        ):
                            receipts.append(data)
                    self._json(receipts)
                else:
                    path = {
                        "/": "index.html",
                        "/app.js": "app.js",
                        "/styles.css": "styles.css",
                    }.get(parsed.path)
                    if path is None:
                        return self._json({"error": "not found"}, 404)
                    mime = (
                        "text/html"
                        if path.endswith(".html")
                        else "application/javascript"
                        if path.endswith(".js")
                        else "text/css"
                    )
                    self._send(200, (ASSETS / path).read_bytes(), mime)
            except (MarketTruthError, ValueError, OSError, KeyError) as exc:
                self._json({"error": str(exc)}, 422)

        def do_POST(self) -> None:
            if not self._headers_ok() or self.path not in ("/api/decision", "/api/owner-approve"):
                return self._json({"error": "forbidden"}, 403)
            if self.path == "/api/owner-approve" and not self._mobile_owner():
                return self._json({"error": "authenticated Tailscale owner required"}, 403)
            if (
                self.headers.get("Origin") != self._origin()
                or self.headers.get("X-Review-Token") != token
                or self.headers.get("Content-Type") != "application/json"
            ):
                return self._json({"error": "unauthorized local review request"}, 403)
            if (self.path == "/api/owner-approve"
                    and not review_signing.verify_mobile_approval_code(
                        self.headers.get("X-Owner-Approval-Code", ""),
                        review.meta["dataset_content_sha256"],
                    )):
                return self._json({"error": "owner approval code required"}, 403)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4096:
                    raise ValueError("invalid decision size")
                body = json.loads(self.rfile.read(size))
                review._assert_current()
                receipt = _decision_payload(body, review.meta)
                if self.path == "/api/owner-approve":
                    if receipt["decision"] != "approve":
                        raise ValueError("owner signature requires explicit approval")
                    # Reuse completed pinned audits, without repeating historical scans.
                    review.v3_full_history_audit()
                    review.statistics_audit()
                    review._assert_current()
                    if not review_signing.consume_mobile_approval_code(
                        self.headers.get("X-Owner-Approval-Code", ""),
                        review.meta["dataset_content_sha256"],
                    ):
                        raise MarketTruthError("approval code expired, used or rotated")
                    signed = review_signing.sign_owner_approval(
                        review.meta, reviewer_login=owner,
                        reviewer_label=receipt["reviewer_label_unverified"],
                        notes=receipt["notes"], verified=True,
                    )
                    return self._json({
                        "saved": True, "signed": True,
                        "status": "Ed25519-signed owner approval; governed admission pending",
                        "receipt": signed,
                    })
                DECISIONS.mkdir(parents=True, exist_ok=True)
                path = DECISIONS / (
                    datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
                    + "-"
                    + secrets.token_hex(6)
                    + ".json"
                )
                with path.open("xb") as stream:
                    stream.write(
                        (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
                    )
                self._json(
                    {
                        "saved": True,
                        "status": "unsigned intent; admission blocked",
                        "receipt": receipt,
                    }
                )
            except (MarketTruthError, ValueError, OSError, TypeError) as exc:
                self._json({"error": str(exc)}, 422)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Private loopback owner-data review")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--tailscale-host", help="Exact private Tailscale Serve HTTPS hostname")
    parser.add_argument("--owner-login", help="Exact Tailscale owner LoginName")
    parser.add_argument("--commission-owner-key", action="store_true",
                        help="Create a Windows owner-only Ed25519 signing key and exit")
    parser.add_argument("--commission-approval-code", action="store_true",
                        help="Show the private one-time setup approval code on this console only")
    args = parser.parse_args()
    if args.commission_owner_key:
        print(json.dumps(review_signing.commission_owner_key(), sort_keys=True))
        return
    if args.commission_approval_code:
        print("Keep this 30-minute, single-use code private. Enter it on your phone to sign:")
        # Read only small source/final manifests for dataset identity; do not
        # repeat the previously completed full historical source audits.
        final = json.loads(FINAL_MANIFEST.read_bytes())
        print(review_signing.commission_mobile_approval_code(final["content_sha256"]))
        return
    if not 1024 <= args.port <= 65535:
        parser.error("choose an unprivileged port")
    review = ReviewData()
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        make_handler(review, secrets.token_urlsafe(32),
                     tailscale_host=args.tailscale_host, owner_login=args.owner_login),
    )
    print(f"Commodity owner review: http://127.0.0.1:{server.server_port}/", flush=True)
    print("Review data read-only; owner signing produces a pending admission candidate.", flush=True)
    if args.tailscale_host:
        print(f"Private mobile dashboard: https://{args.tailscale_host}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
