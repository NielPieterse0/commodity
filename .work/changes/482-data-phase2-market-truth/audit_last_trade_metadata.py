"""Read-only pre-2023 NG definition metadata coverage diagnostic.

This does not reconstruct an official exchange calendar or approve research data.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / ".work" / "runtime" / "market_truth_development"
BASE = DATA / "market-truth-full-2010-2022-refactor-v3"
DEFINITIONS = BASE / "definitions.parquet"
SOURCE_MANIFEST = DATA / "source-manifest-full-2010-2022-curated.json"
SOURCE_DEFINITIONS_CSV = DATA / "definitions-full-2010-2022.csv"
EXPECTED_SOURCE_DEFINITIONS = "dfd96778a31399c950425171c970ca1d0ccff6a933415a69412679499217fa23"
EXPECTED_SOURCE_COLUMNS = (
    "instrument_id", "ts_event", "ts_recv", "asset", "instrument_class",
    "raw_symbol", "expiration", "exchange",
)
EXPECTED_MANIFEST = "6d3093305c0ae2c6a313be13151b0810bf208c1cb8f429e1bbf58a17e7d89605"
EXPECTED_SOURCE = "8a86789673c8458c5745f14b550f3c16b6e4885cac026578cb2989cbc80e5240"
EXPECTED_DEFINITIONS = "b803deb0b88d7c0f57625fd46cfa4537e902dd3951cf04aeeba84f95f5dbf4d8"
EXPECTED_ROWS = 525810
EXPECTED_DEFINITION_TOTALS = {
    "rows": 525810, "unique_instrument_ids": 306,
    "unique_contract_definitions": 307, "missing_last_trade_at": 525810,
    "present_last_trade_at": 0, "invalid_last_trade_at": 0,
    "invalid_expiration": 0, "midnight_utc_expiration": 0,
    "intraday_utc_expiration": 525810, "last_trade_after_expiration": 0,
}
EXPECTED_CONTRACT_COUNTS = {
    "EDT": 205, "EST": 102, "adjacent_symbol_delivery_month": 307,
    "distinct_contracts": 307, "local_1430_expiration": 306,
    "non_1430_local_expiration": 1,
    "symbol_year_suffix_matches_delivery_year": 307,
    "third_prior_weekday_exact_match": 280,
    "weekday_only_comparator_mismatch": 27,
}
EXPECTED_EXPIRATION_COHORTS = {
    "expired_before_2023": {
        "contracts": 152, "non_1430_local_expiration": 1,
        "third_prior_weekday_exact_match": 138,
        "weekday_only_comparator_mismatch": 14,
    },
    "future_listed_expiration_2023_plus": {
        "contracts": 155, "third_prior_weekday_exact_match": 142,
        "weekday_only_comparator_mismatch": 13,
    },
}
EXPECTED_YEAR_ROWS = {
    2010: 18117, 2011: 32052, 2012: 31864, 2013: 32130,
    2014: 37113, 2015: 42378, 2016: 47280, 2017: 47546,
    2018: 47893, 2019: 47452, 2020: 47592, 2021: 47281, 2022: 47112,
}
EXPECTED_YEAR_INSTRUMENT_IDS = {
    2010: 115, 2011: 119, 2012: 107, 2013: 130,
    2014: 130, 2015: 168, 2016: 168, 2017: 167,
    2018: 167, 2019: 167, 2020: 167, 2021: 168, 2022: 167,
}
EXPECTED_YEAR_MISMATCHES = {
    **{str(year): 1 for year in range(2015, 2024)},
    **{str(year): 1 for year in range(2025, 2035)},
    "2010": 2, "2011": 1, "2013": 2, "2014": 1, "2024": 2,
}
SOURCE_FILES = {
    "dataset_manifest": (BASE / "manifest.json", EXPECTED_MANIFEST, 1024 * 1024),
    "source_manifest": (SOURCE_MANIFEST, EXPECTED_SOURCE, 1024 * 1024),
    "source_csv": (SOURCE_DEFINITIONS_CSV, EXPECTED_SOURCE_DEFINITIONS, 128 * 1024 * 1024),
    "definitions": (DEFINITIONS, EXPECTED_DEFINITIONS, 128 * 1024 * 1024),
}


@contextmanager
def verified_source_snapshots() -> Iterator[dict[str, Path]]:
    """Consume exactly the bytes hashed into private, isolated output copies."""
    with tempfile.TemporaryDirectory(prefix=".ng-lasttrade-audit-", dir=DATA) as temporary:
        stage = Path(temporary)
        snapshots = {}
        for family, (source, expected, maximum) in SOURCE_FILES.items():
            if source.is_symlink() or not source.is_file():
                raise RuntimeError("pinned diagnostic input unavailable")
            destination = stage / (family + source.suffix)
            digest = hashlib.sha256()
            total = 0
            with source.open("rb") as reader, destination.open("xb") as writer:
                for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                    total += len(chunk)
                    if total > maximum:
                        raise RuntimeError("pinned source exceeds snapshot byte budget")
                    digest.update(chunk)
                    writer.write(chunk)
            if digest.hexdigest() != expected:
                raise RuntimeError("source bytes changed while staging diagnostic")
            snapshots[family] = destination
        yield snapshots


def sha(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("required pre-2023 pinned diagnostic source missing")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


MONTH_CODES = dict(zip("FGHJKMNQUVXZ", range(1, 13), strict=True))


def third_prior_weekday(first_delivery_day: date) -> date:
    """Weekday-only comparator, explicitly NOT the historical CME calendar."""
    prior = first_delivery_day
    count = 0
    while count < 3:
        prior -= timedelta(days=1)
        if prior.weekday() < 5:
            count += 1
    return prior


def analyze_contract_expirations(contracts: list[tuple[str, str, str]]) -> dict:
    """Aggregate contract-level dates without publishing proprietary source rows."""
    if not contracts:
        raise RuntimeError("no pinned futures definition contracts")
    east = ZoneInfo("America/New_York")
    counters = Counter()
    discrepancy_years = Counter()
    discrepancy_offsets = Counter()
    unusual_local_clocks = Counter()
    unusual_local_years = Counter()
    development_expiration_cohorts = {
        "expired_before_2023": Counter(),
        "future_listed_expiration_2023_plus": Counter(),
    }
    for venue, symbol, expiration in contracts:
        counters["distinct_contracts"] += 1
        if venue != "NYMEX":
            counters["unexpected_venue"] += 1
        observed = datetime.fromisoformat(expiration)
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise RuntimeError("definition expiration lacks timezone")
        observed_utc = observed.astimezone(UTC)
        local = observed_utc.astimezone(east)
        cohort = development_expiration_cohorts[
            "expired_before_2023" if local.date() < date(2023, 1, 1)
            else "future_listed_expiration_2023_plus"
        ]
        cohort["contracts"] += 1
        if (local.hour, local.minute, local.second, local.microsecond) == (14, 30, 0, 0):
            counters["local_1430_expiration"] += 1
        else:
            counters["non_1430_local_expiration"] += 1
            cohort["non_1430_local_expiration"] += 1
            unusual_local_clocks[local.strftime("%H:%M:%S")] += 1
            unusual_local_years[str(local.year)] += 1
        if local.date().weekday() >= 5:
            counters["weekend_expiration"] += 1
        if local.utcoffset() == timedelta(hours=-4):
            counters["EDT"] += 1
        elif local.utcoffset() == timedelta(hours=-5):
            counters["EST"] += 1
        else:
            counters["unexpected_timezone_offset"] += 1
        # The contract symbol identifies DELIVERY month, not the prior month's
        # expiration. Validate the month-code without trusting year suffixes.
        match = re.fullmatch(r"NG([FGHJKMNQUVXZ])([0-9]{1,4})", symbol)
        if not match:
            counters["unparseable_NG_symbol"] += 1
            continue
        month = MONTH_CODES[match.group(1)]
        delivery_year = local.year + (1 if month <= local.month else 0)
        suffix = match.group(2)
        if len(suffix) == 4:
            suffix_matches = int(suffix) == delivery_year
        else:
            suffix_matches = delivery_year % (10 ** len(suffix)) == int(suffix)
        if suffix_matches:
            counters["symbol_year_suffix_matches_delivery_year"] += 1
        else:
            counters["symbol_year_suffix_mismatch"] += 1
        first_delivery = date(delivery_year, month, 1)
        if not (first_delivery > local.date() and (first_delivery - local.date()).days <= 35):
            counters["nonadjacent_symbol_delivery_month"] += 1
            continue
        counters["adjacent_symbol_delivery_month"] += 1
        expected = third_prior_weekday(first_delivery)
        deviation = (local.date() - expected).days
        if deviation == 0:
            counters["third_prior_weekday_exact_match"] += 1
            cohort["third_prior_weekday_exact_match"] += 1
        else:
            counters["weekday_only_comparator_mismatch"] += 1
            cohort["weekday_only_comparator_mismatch"] += 1
            discrepancy_years[str(local.year)] += 1
            discrepancy_offsets[str(deviation)] += 1
    return {
        "counts": dict(sorted(counters.items())),
        "weekday_comparator_mismatch_by_expiration_year": dict(sorted(discrepancy_years.items())),
        "weekday_comparator_deviation_days": dict(sorted(discrepancy_offsets.items())),
        "unusual_local_clock_values": dict(sorted(unusual_local_clocks.items())),
        "unusual_local_clock_years": dict(sorted(unusual_local_years.items())),
        "development_expiration_cohorts": {
            name: dict(sorted(counts.items()))
            for name, counts in development_expiration_cohorts.items()
        },
        "weekday_model_is_official_CME_holiday_calendar": False,
        "regulatory_exchange_calendar_independently_verified": False,
    }


def verify_expected_coverage(
    totals: dict, calendar: dict, year_counts: list[dict], clock_distribution: list[dict],
) -> None:
    """Fail if pinned source classifications drift, even when row totals agree."""
    if totals != EXPECTED_DEFINITION_TOTALS:
        raise RuntimeError("pinned definition metadata classification changed")
    if calendar["counts"] != EXPECTED_CONTRACT_COUNTS:
        raise RuntimeError("pinned contract anomaly classification changed")
    if calendar["development_expiration_cohorts"] != EXPECTED_EXPIRATION_COHORTS:
        raise RuntimeError("pinned pre-2023 versus forward-listed contract cohorts changed")
    if (
        calendar["weekday_comparator_mismatch_by_expiration_year"] != EXPECTED_YEAR_MISMATCHES
        or calendar["weekday_comparator_deviation_days"] != {"-1": 22, "-2": 1, "-3": 4}
        or calendar["unusual_local_clock_values"] != {"13:30:00": 1}
        or calendar["unusual_local_clock_years"] != {"2021": 1}
        or calendar["weekday_model_is_official_CME_holiday_calendar"] is not False
        or calendar["regulatory_exchange_calendar_independently_verified"] is not False
    ):
        raise RuntimeError("pinned expiration anomalies unexpectedly changed")
    actual_years = {
        item["available_year"]: item for item in year_counts
    }
    if (
        len(actual_years) != len(year_counts)
        or set(actual_years) != set(EXPECTED_YEAR_ROWS)
        or any(
            actual_years[year] != {
                "available_year": year, "rows": rows, "explicit_last_trade": 0,
                "distinct_instrument_ids": EXPECTED_YEAR_INSTRUMENT_IDS[year],
            }
            for year, rows in EXPECTED_YEAR_ROWS.items()
        )
    ):
        raise RuntimeError("pinned annual definition coverage unexpectedly changed")
    if clock_distribution != [
        {"utc_clock": "18:30:00", "definition_versions": 352720, "distinct_contracts": 206},
        {"utc_clock": "19:30:00", "definition_versions": 173090, "distinct_contracts": 101},
    ]:
        raise RuntimeError("pinned expiration clock distribution changed")


def audit() -> dict:
    with verified_source_snapshots() as snapshots:
        return _audit_verified_snapshots(snapshots)


def _audit_verified_snapshots(snapshots: dict[str, Path]) -> dict:
    """No original source pathname is reopened after the verified stage."""
    with snapshots["source_csv"].open("rb") as source_reader:
        header = source_reader.readline(1024)
    if tuple(header.decode("ascii").strip().split(",")) != EXPECTED_SOURCE_COLUMNS:
        raise RuntimeError("source definition CSV columns unexpectedly changed")
    source_manifest = json.loads(snapshots["source_manifest"].read_bytes())
    if (
        source_manifest.get("schema_version") != 1
        or source_manifest.get("evidence_class") != "development"
        or source_manifest.get("dataset") != "GLBX.MDP3"
        or source_manifest.get("product_code") != "NG"
        or source_manifest.get("max_trade_date") != "2022-12-31"
        or source_manifest.get("protected_confirmation_accessed") is not False
        or source_manifest.get("inputs", {}).get("definitions", {}).get("sha256")
        != EXPECTED_SOURCE_DEFINITIONS
    ):
        raise RuntimeError("original curated source outside pre-2023 diagnostic scope")
    manifest = json.loads(snapshots["dataset_manifest"].read_bytes())
    if (
        manifest.get("dataset_scope") != "development_pre2023"
        or manifest.get("protected_confirmation_accessed") is not False
        or manifest.get("tables", {}).get("definitions", {}).get("rows") != EXPECTED_ROWS
        or manifest["tables"]["definitions"]["sha256"] != EXPECTED_DEFINITIONS
        or manifest.get("source_manifest_sha256") != EXPECTED_SOURCE
    ):
        raise RuntimeError("not the exact approved-for-diagnostics pre-2023 table")

    import duckdb

    con = duckdb.connect(":memory:")
    con.execute("SET memory_limit='512MB'")
    con.execute("SET TimeZone='UTC'")
    path = str(snapshots["definitions"])
    try:
        all_rows = con.execute("""
            SELECT COUNT(*) AS rows,
                   COUNT(DISTINCT instrument_id) AS unique_instrument_ids,
                   COUNT(DISTINCT (venue, symbol, expiration)) AS unique_contract_definitions,
                   COUNT(*) FILTER (WHERE last_trade_at IS NULL) AS missing_last_trade_at,
                   COUNT(*) FILTER (WHERE last_trade_at IS NOT NULL) AS present_last_trade_at,
                   COUNT(*) FILTER (WHERE last_trade_at IS NOT NULL
                       AND TRY_CAST(last_trade_at AS TIMESTAMPTZ) IS NULL) AS invalid_last_trade_at,
                   COUNT(*) FILTER (WHERE TRY_CAST(expiration AS TIMESTAMPTZ) IS NULL) AS invalid_expiration,
                   COUNT(*) FILTER (WHERE CAST(expiration AS TIMESTAMPTZ) =
                       DATE_TRUNC('day', CAST(expiration AS TIMESTAMPTZ))) AS midnight_utc_expiration,
                   COUNT(*) FILTER (WHERE CAST(expiration AS TIMESTAMPTZ) !=
                       DATE_TRUNC('day', CAST(expiration AS TIMESTAMPTZ))) AS intraday_utc_expiration,
                   COUNT(*) FILTER (WHERE last_trade_at IS NOT NULL AND
                       TRY_CAST(last_trade_at AS TIMESTAMPTZ) >
                       TRY_CAST(expiration AS TIMESTAMPTZ)) AS last_trade_after_expiration
            FROM read_parquet(?)
        """, [path]).fetchone()
        names = [
            "rows", "unique_instrument_ids", "unique_contract_definitions",
            "missing_last_trade_at", "present_last_trade_at", "invalid_last_trade_at",
            "invalid_expiration", "midnight_utc_expiration",
            "intraday_utc_expiration", "last_trade_after_expiration",
        ]
        totals = dict(zip(names, all_rows, strict=True))
        if totals["rows"] != EXPECTED_ROWS:
            raise RuntimeError("definition row count changed from pinned materialization")
        yearly = con.execute("""
            SELECT EXTRACT(YEAR FROM TRY_CAST(available_at AS TIMESTAMPTZ))::INTEGER AS observed_year,
                   COUNT(*) AS rows,
                   COUNT(*) FILTER (WHERE last_trade_at IS NOT NULL) AS explicit_last_trade,
                   COUNT(DISTINCT instrument_id) AS instrument_ids
            FROM read_parquet(?)
            GROUP BY 1 ORDER BY 1
        """, [path]).fetchall()
        year_counts = [
            {"available_year": year, "rows": rows,
             "explicit_last_trade": explicit, "distinct_instrument_ids": ids}
            for year, rows, explicit, ids in yearly
        ]
        expiration_clock = con.execute("""
            SELECT STRFTIME(CAST(expiration AS TIMESTAMPTZ), '%H:%M:%S') AS utc_clock,
                   COUNT(*) AS definition_versions,
                   COUNT(DISTINCT (venue, symbol, expiration)) AS contracts
            FROM read_parquet(?)
            GROUP BY 1 ORDER BY definition_versions DESC, utc_clock
            LIMIT 15
        """, [path]).fetchall()
        expiration_clock_distribution = [
            {"utc_clock": clock, "definition_versions": count,
             "distinct_contracts": contracts}
            for clock, count, contracts in expiration_clock
        ]
        contract_rows = con.execute("""
            SELECT DISTINCT venue, symbol, expiration
            FROM read_parquet(?)
            ORDER BY expiration, venue, symbol
        """, [path]).fetchall()
        contract_calendar = analyze_contract_expirations(contract_rows)
        verify_expected_coverage(totals, contract_calendar, year_counts, expiration_clock_distribution)
        if contract_calendar["counts"]["distinct_contracts"] != totals["unique_contract_definitions"]:
            raise RuntimeError("definition contract identity count changed")
        lag_distribution = con.execute("""
            SELECT
                DATEDIFF('day',
                    CAST(last_trade_at AS TIMESTAMPTZ),
                    CAST(expiration AS TIMESTAMPTZ)) AS days_before_expiration,
                COUNT(*) AS definition_versions
            FROM read_parquet(?)
            WHERE last_trade_at IS NOT NULL
            GROUP BY 1 ORDER BY definition_versions DESC, days_before_expiration
            LIMIT 20
        """, [path]).fetchall()
        lag_top = [
            {"days_before_expiration": lag, "definition_versions": count}
            for lag, count in lag_distribution
        ]
    finally:
        con.close()

    # Verify only staged bytes, not the mutable host paths; all DuckDB reads
    # consumed the same private verified copy. No trust in host immutability.
    for family, (_, expected, _) in SOURCE_FILES.items():
        if sha(snapshots[family]) != expected:
            raise RuntimeError("private diagnostic snapshot mutated during query")
    return {
        "schema_version": 1,
        "issue": 482,
        "result": "SOURCE_METADATA_COVERAGE_DIAGNOSTIC_ONLY",
        "source_manifest_sha256": EXPECTED_SOURCE,
        "dataset_manifest_sha256": EXPECTED_MANIFEST,
        "definitions_parquet_sha256": EXPECTED_DEFINITIONS,
        "decoded_source_definitions_csv_sha256": EXPECTED_SOURCE_DEFINITIONS,
        "decoded_source_columns": list(EXPECTED_SOURCE_COLUMNS),
        "decoded_source_contains_independent_last_trade_field": False,
        "definitions": totals,
        "per_available_year": year_counts,
        "last_trade_expiration_day_differences_top20": lag_top,
        "expiration_utc_clock_distribution_top15": expiration_clock_distribution,
        "contract_calendar_coverage": contract_calendar,
        "databento_definition_expiration_semantics": "last_eligible_trade_time_may_have_date_only_precision",
        "databento_public_documentation": "https://databento.com/docs/schemas-and-data-formats/instrument-definitions",
        "CME_official_last_trade_calendar_independently_verified": False,
        "immutable_source_owner_approved": False,
        "official_date_candidates_promoted": 0,
        "protected_confirmation_accessed": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True, indent=2))
