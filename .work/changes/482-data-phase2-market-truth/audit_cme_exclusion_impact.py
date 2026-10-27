"""Pinned read-only scope of 14 known CME weekday-proxy differences.
No date reconstruction, no exchange-authoritative expiry claims, no protected data.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
from audit_last_trade_metadata import MONTH_CODES, third_prior_weekday

ROOT = Path(__file__).resolve().parents[3]
DATA = (
    ROOT
    / ".work/runtime/market_truth_development/market-truth-full-2010-2022-refactor-v3"
)
LEGACY = Path("/legacy")
EXPECTED = {
    "manifest": "6d3093305c0ae2c6a313be13151b0810bf208c1cb8f429e1bbf58a17e7d89605",
    "definitions": "b803deb0b88d7c0f57625fd46cfa4537e902dd3951cf04aeeba84f95f5dbf4d8",
    "features": "b14ae69bd6ec2910f0cf56fe62f481016801308cebc6ef69e536aa7e593d072e",
    "session-path": "0fe87ea79a56f98fb9d445e89e3d65b48ae7bb1175e06ba9b97da68ebe6b01e8",
}


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def uncertain_expiry(venue, symbol, expiration):
    if venue != "NYMEX":
        raise ValueError("unexpected venue")
    match = re.fullmatch(r"NG([FGHJKMNQUVXZ])([0-9]{1,4})", symbol)
    if not match:
        raise ValueError("unexpected contract identity")
    utc = datetime.fromisoformat(expiration)
    if utc.tzinfo is None or utc.utcoffset() is None:
        raise ValueError("timezone-naive source expiration")
    local = utc.astimezone(ZoneInfo("America/New_York"))
    month = MONTH_CODES[match.group(1)]
    year = local.year + (month <= local.month)
    if year % 10 ** len(match.group(2)) != int(match.group(2)):
        raise ValueError("contract year suffix mismatch")
    if local.date() >= date(2023, 1, 1):
        return False, False
    return True, local.date() != third_prior_weekday(date(year, month, 1))


def _verify_rank_coverage(db):
    for name in ("rank12", "proxy_rank12"):
        rows, slots, days = db.execute(
            f"SELECT count(*), count(DISTINCT (day,rank)), count(DISTINCT day) FROM {name}"
        ).fetchone()
        if not days or rows != slots or rows != days * 12:
            raise RuntimeError("incomplete or duplicate rank comparison slots")
    missing = db.execute("""
      SELECT count(*) FROM (
        SELECT o.day, o.rank FROM rank12 o
          ANTI JOIN proxy_rank12 p USING (day,rank)
        UNION ALL
        SELECT p.day, p.rank FROM proxy_rank12 p
          ANTI JOIN rank12 o USING (day,rank)
      )
    """).fetchone()[0]
    if missing:
        raise RuntimeError("missing or extra counterfactual rank slot")


def count_rank_differences(db):
    """Compare rank identities, separately from the expiry-value uncertainty."""
    _verify_rank_coverage(db)
    changed = db.execute("""
      SELECT count(*) slots, count(DISTINCT o.day) sessions,
        count(*) FILTER(WHERE o.rank<=4) front4_slots,
        count(DISTINCT o.day) FILTER(WHERE o.rank<=4) front4_sessions,
        count(*) FILTER(WHERE o.rank=1) front_slots,
        count(DISTINCT o.day) FILTER(WHERE o.rank=1) front_sessions
      FROM rank12 o JOIN proxy_rank12 p USING (day,rank)
      WHERE o.instrument_id != p.instrument_id
    """).fetchone()
    days = [
        str(row[0])
        for row in db.execute("""
      SELECT DISTINCT o.day
      FROM rank12 o JOIN proxy_rank12 p USING(day,rank)
      WHERE o.instrument_id != p.instrument_id
      ORDER BY o.day
    """).fetchall()
    ]
    if len(days) != changed[1]:
        raise RuntimeError("changed calendar session count mismatch")
    return changed, days


def count_expiry_value_differences(db):
    """Same-rank, same-contract changes to observed expiry-derived values."""
    _verify_rank_coverage(db)
    return db.execute("""
      SELECT count(*) changed_slots, count(DISTINCT o.day) changed_sessions,
        count(*) FILTER(WHERE o.rank<=4) changed_front4_slots,
        count(DISTINCT o.day) FILTER(WHERE o.rank<=4) changed_front4_sessions
      FROM rank12 o JOIN proxy_rank12 p USING(day,rank)
      WHERE o.instrument_id = p.instrument_id
        AND CAST(o.expiration AS TIMESTAMPTZ)
            != CAST(p.counterfactual_expiration AS TIMESTAMPTZ)
    """).fetchone()


def verify_source_pins(sources, expected):
    """Verify exact original evidence bytes and pre-2023 admission boundary."""
    if set(sources) != set(expected) or set(sources) != {
        "manifest",
        "definitions",
        "features",
        "session-path",
    }:
        raise RuntimeError("unexpected diagnostic input inventory")
    for name, path in sources.items():
        if not path.is_file() or path.is_symlink() or digest(path) != expected[name]:
            raise RuntimeError("incorrect pinned pre-2023 evidence: " + name)
    manifest = json.loads(sources["manifest"].read_bytes())
    if (
        manifest.get("dataset_scope") != "development_pre2023"
        or manifest.get("protected_confirmation_accessed") is not False
        or manifest.get("tables", {}).get("definitions", {}).get("sha256")
        != expected["definitions"]
    ):
        raise RuntimeError("unexpected data admission/scope")
    return manifest


def audit():
    sources = {
        "manifest": DATA / "manifest.json",
        "definitions": DATA / "definitions.parquet",
        "features": LEGACY / "features.parquet",
        "session-path": LEGACY / "session-path.parquet",
    }
    verify_source_pins(sources, EXPECTED)
    db = duckdb.connect(":memory:")
    db.execute("SET memory_limit='768MB'")
    db.execute("SET temp_directory='/tmp'")
    db.execute("SET TimeZone='UTC'")
    db.from_parquet(str(sources["definitions"])).create_view("defs")
    db.from_parquet(str(sources["features"])).create_view("oldfeat")
    db.from_parquet(str(sources["session-path"])).create_view("oldpath")
    contracts = db.execute(
        "SELECT DISTINCT venue,symbol,expiration FROM defs ORDER BY venue,symbol,expiration"
    ).fetchall()
    uncertain = set()
    historical = 0
    for venue, symbol, exp in contracts:
        in_history, unmatched = uncertain_expiry(venue, symbol, exp)
        historical += in_history
        if unmatched:
            uncertain.add((venue, symbol, exp))
    if len(contracts) != 307 or historical != 152 or len(uncertain) != 14:
        raise RuntimeError("pinned CME comparator cohort changed")
    canonical = json.dumps(sorted(uncertain), sort_keys=True, separators=(",", ":"))
    digest_ids = hashlib.sha256(canonical.encode()).hexdigest()
    db.execute(
        "CREATE TEMP TABLE uncertain(venue VARCHAR,symbol VARCHAR,expiration VARCHAR,weekday_proxy VARCHAR)"
    )
    projected = []
    for venue, symbol, exp in sorted(uncertain):
        local = datetime.fromisoformat(exp).astimezone(ZoneInfo("America/New_York"))
        month = MONTH_CODES[
            re.fullmatch(r"NG([FGHJKMNQUVXZ])([0-9]{1,4})", symbol).group(1)
        ]
        year = local.year + (month <= local.month)
        proxy_day = third_prior_weekday(date(year, month, 1))
        proxy = local.replace(
            year=proxy_day.year, month=proxy_day.month, day=proxy_day.day
        )
        projected.append((venue, symbol, exp, proxy.astimezone(UTC).isoformat()))
    db.executemany("INSERT INTO uncertain VALUES (?,?,?,?)", projected)
    db.execute("""
    CREATE TEMP VIEW rank12 AS
    SELECT CAST(f.trade_date AS DATE) AS day,
        CAST(f.available_at AS TIMESTAMPTZ) AS cutoff,
        d.venue, d.instrument_id, d.symbol, d.expiration,
        ROW_NUMBER() OVER (PARTITION BY f.trade_date
          ORDER BY CAST(d.expiration AS TIMESTAMPTZ), d.venue, d.symbol, d.instrument_id) rank
    FROM oldfeat f CROSS JOIN (SELECT DISTINCT instrument_id FROM defs) ids
    ASOF JOIN defs d ON ids.instrument_id=d.instrument_id
      AND CAST(d.available_at AS TIMESTAMPTZ) <= LEAST(
        CAST(f.available_at AS TIMESTAMPTZ),
        CAST(f.trade_date AS TIMESTAMPTZ)+INTERVAL '1 day'-INTERVAL '1 microsecond')
    WHERE CAST(d.expiration AS TIMESTAMPTZ) > LEAST(
        CAST(f.available_at AS TIMESTAMPTZ),
        CAST(f.trade_date AS TIMESTAMPTZ)+INTERVAL '1 day'-INTERVAL '1 microsecond')
    QUALIFY rank<=12
    """)
    # Counterfactual only: weekday model is NOT independent exchange truth.
    # Compare all 12 ranks and exact observed membership to the proxy.
    db.execute("""
    CREATE TEMP VIEW proxy_rank12 AS
    WITH selected_versions AS (
      SELECT CAST(f.trade_date AS DATE) AS day,
             CAST(f.available_at AS TIMESTAMPTZ) AS cutoff,
             d.venue, d.instrument_id, d.symbol, d.expiration,
             CAST(COALESCE(u.weekday_proxy, d.expiration) AS TIMESTAMPTZ) AS eligibility,
             LEAST(CAST(f.available_at AS TIMESTAMPTZ),
               CAST(f.trade_date AS TIMESTAMPTZ)+INTERVAL '1 day'-INTERVAL '1 microsecond') AS membership
      FROM oldfeat f CROSS JOIN (SELECT DISTINCT instrument_id FROM defs) ids
      ASOF JOIN defs d ON ids.instrument_id=d.instrument_id
        AND CAST(d.available_at AS TIMESTAMPTZ) <= LEAST(
          CAST(f.available_at AS TIMESTAMPTZ),
          CAST(f.trade_date AS TIMESTAMPTZ)+INTERVAL '1 day'-INTERVAL '1 microsecond')
      LEFT JOIN uncertain u ON d.venue=u.venue AND d.symbol=u.symbol
        AND d.expiration=u.expiration
    )
    SELECT day, venue, instrument_id, symbol, expiration,
           CAST(eligibility AS VARCHAR) AS counterfactual_expiration,
           ROW_NUMBER() OVER (PARTITION BY day
             ORDER BY eligibility, venue, symbol, instrument_id) rank
    FROM selected_versions WHERE eligibility>membership
    QUALIFY rank<=12
    """)
    changed, changed_dates = count_rank_differences(db)
    expiry_only = count_expiry_value_differences(db)
    changed_dates_sha256 = hashlib.sha256(
        json.dumps(changed_dates, separators=(",", ":")).encode()
    ).hexdigest()
    totals = db.execute("""SELECT COUNT(DISTINCT trade_date), COUNT(*)
       FROM oldfeat""").fetchone()
    if totals[0] != 3088:
        raise RuntimeError("unexpected historic evaluation cohort")
    selected = db.execute("""SELECT count(*) AS selected_rows, count(DISTINCT r.day) AS selected_days,
         count(DISTINCT r.symbol) symbols, min(r.day), max(r.day)
        FROM rank12 r JOIN uncertain u USING (venue,symbol,expiration)""").fetchone()
    exposures = db.execute("""SELECT r.rank, count(*) selected_rows,
           count(DISTINCT r.day) affected_dates
         FROM rank12 r JOIN uncertain u USING (venue,symbol,expiration)
         GROUP BY r.rank ORDER BY r.rank""").fetchall()
    front = db.execute("""SELECT count(*),count(DISTINCT p.trade_date)
        FROM oldpath p JOIN uncertain u
        ON SPLIT_PART(p.contract_id, '@',1)=u.symbol
        AND CAST(SPLIT_PART(p.contract_id,'@',2) AS DATE)=
              CAST(CAST(u.expiration AS TIMESTAMPTZ) AS DATE)
        """).fetchone()
    all_rank = db.execute("""SELECT count(*), count(DISTINCT day),
      count(*) FILTER(WHERE rank=1) FROM rank12""").fetchone()
    if all_rank[1] != 3088 or all_rank[2] != 3088:
        raise RuntimeError("historical rank selection incomplete")
    result = {
        "schema_version": 1,
        "issue": 482,
        "result": "PINNED_CME_UNCERTAINTY_EXCLUSION_IMPACT_DIAGNOSTIC",
        "historical_contracts": historical,
        "historical_weekday_comparator_differences": len(uncertain),
        "uncertain_contract_identities_sha256": digest_ids,
        "audit_script_sha256": digest(Path(__file__)),
        "weekday_proxy_counterfactual_not_official": True,
        "counterfactual_changed_rank_slots": changed[0],
        "counterfactual_changed_sessions_any_rank": changed[1],
        "counterfactual_changed_sessions_sha256": changed_dates_sha256,
        "counterfactual_same_rank_expiry_changed_slots": expiry_only[0],
        "counterfactual_same_rank_expiry_changed_sessions": expiry_only[1],
        "counterfactual_same_rank_expiry_changed_front4_slots": expiry_only[2],
        "counterfactual_same_rank_expiry_changed_front4_sessions": expiry_only[3],
        "counterfactual_changed_rank1to4_slots": changed[2],
        "counterfactual_changed_sessions_rank1to4": changed[3],
        "counterfactual_changed_front_rank_slots": changed[4],
        "counterfactual_changed_front_rank_sessions": changed[5],
        "source_sha256": EXPECTED,
        "frozen_feature_sessions": totals[0],
        "frozen_rank12_rows": all_rank[0],
        "uncertain_rank12_selected_rows": selected[0],
        "uncertain_rank12_selected_sessions": selected[1],
        "uncertain_rank12_selected_symbols": selected[2],
        "uncertain_rank12_selected_first_date": str(selected[3]),
        "uncertain_rank12_selected_last_date": str(selected[4]),
        "uncertain_selected_by_rank": [
            {"rank": rank, "rows": rows, "sessions": sessions}
            for rank, rows, sessions in exposures
        ],
        "frozen_trading_path_records_referencing_uncertain_expiries": front[0],
        "frozen_trading_path_sessions_referencing_uncertain_expiries": front[1],
        "time_and_license_boundary": "pre2023 pinned only; no protected confirmation read",
        "independent_CME_expiration_verification": False,
        "official_date_promotions": 0,
        "safe_for_unqualified_expiry_dependent_V3_research": False,
        "research_owner_approval": False,
        "immutable_storage_verified": False,
        "exclusion_policy_implemented": False,
        "next_step": "Scope explicit fail-closed expiry-dependent exclusion; do not suppress whole unaffected dates or silently change frozen parity",
    }
    verify_source_pins(sources, EXPECTED)
    db.close()
    return result


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True, separators=(",", ":")))
