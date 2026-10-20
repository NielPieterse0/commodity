"""Bounded route-B proof: frozen source ranks cannot leak into V3 model outputs.

Uses ONLY previously SHA-pinned pre-2023 source definitions and frozen decision
clocks. Does not rerun numeric parity, reconstruct historical CME expiry times,
approve/admit a dataset, or open the protected confirmation archive.
Synthetic sentinels test the actual model-facing feature calculation, not prices.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
from audit_cme_frozen_cutoffs import FROZEN, PINS, SOURCE, _hash

from commodity.market_truth.core import MarketTruthError, parse_time, snapshot_asof
from commodity.market_truth.ng_expiry import (
    UNQUALIFIED_NG_EXPIRIES,
    fence_ng_expiry_definitions,
    model_safe_ng_curve,
    verify_ng_expiry_policy,
)
from commodity.market_truth.query import protected_table_reads

RECORD = Path(__file__).with_name("cme-model-output-history-receipt.json")
OLD_RANK = Path(__file__).with_name("cme-rank-output-safety-receipt.json")
OLD_CUTOFF = Path(__file__).with_name("cme-frozen-cutoff-exclusion-receipt.json")


def _source_rank_rows(con, features: Path, definitions: Path):
    """Repeat selection SQL strictly as needed for a NEW output-level invariant."""
    return con.execute("""
        WITH sessions AS (
          SELECT CAST(trade_date AS DATE) AS day,
                 LEAST(CAST(available_at AS TIMESTAMPTZ),
                       CAST(trade_date AS DATE)::TIMESTAMPTZ
                       + INTERVAL '1 day' - INTERVAL '1 microsecond') AS membership
          FROM read_parquet(?)
        ), ids AS (
          SELECT DISTINCT instrument_id FROM read_parquet(?)
        ), eligible AS (
          SELECT s.day, s.membership, d.venue, d.symbol,
                 d.instrument_id, d.expiration, d.last_trade_at, d.available_at
          FROM sessions s CROSS JOIN ids i
          ASOF JOIN read_parquet(?) d
            ON i.instrument_id=d.instrument_id
           AND CAST(d.available_at AS TIMESTAMPTZ) <= s.membership
          WHERE CAST(COALESCE(d.last_trade_at,d.expiration)
                     AS TIMESTAMPTZ) > s.membership
        ), ranked AS (
          SELECT *, ROW_NUMBER() OVER (
            PARTITION BY day
            ORDER BY CAST(expiration AS TIMESTAMPTZ),
                     venue, symbol, instrument_id
          ) AS rank
          FROM eligible
        )
        SELECT day, membership, venue, symbol, instrument_id,
               expiration, last_trade_at, available_at, rank
        FROM ranked
        WHERE rank <= 12 ORDER BY day, rank
    """, [str(features), str(definitions), str(definitions)]).fetchall()


def _point(row: tuple, policy: set[tuple[str, str, str]]) -> dict:
    day, _, venue, symbol, instrument_id, expiry, last_trade, available, rank = row
    qualified = (venue, symbol, str(expiry)) not in policy
    # Distinct synthetic sentinels make downstream leakage observable without
    # reading market price/volume/OI from any unadmitted research dataset.
    price = round(1 + rank / 10, 5)
    return {
        "trade_date": day.isoformat(), "rank": rank,
        "instrument_id": instrument_id, "venue": venue,
        "contract_identity": f"{venue}:{symbol}:{expiry}",
        "contract_symbol": symbol, "expiration": str(expiry),
        "last_trade_at": str(last_trade) if last_trade is not None else None,
        "last_trade_verified": qualified and last_trade is not None,
        "rank_boundary_status": (
            "expiry_fallback_unverified" if qualified and last_trade is None
            else "verified_last_trade" if qualified
            else "unverified_exchange_expiry"
        ),
        "days_to_expiry": (
            (parse_time(expiry).date() - day).days if qualified else None
        ),
        "open": price, "high": price + .1, "low": price - .1,
        "close": price, "volume": 100 + rank, "settle": price,
        "open_interest": 1000 + rank, "cleared_volume": 100 + rank,
        "missing_reason": "none", "available_at": str(available),
        "evidence_ids": [f"synthetic-rank-{rank}"],
    }


def run() -> dict:
    verify_ng_expiry_policy()
    paths = {
        "manifest": SOURCE / "manifest.json",
        "definitions": SOURCE / "definitions.parquet",
        "features": FROZEN / "features.parquet",
    }
    policy = {("NYMEX", symbol, expiry) for symbol, expiry in UNQUALIFIED_NG_EXPIRIES}
    if len(policy) != 14:
        raise RuntimeError("unqualified CME cohort altered")
    with protected_table_reads([*paths.values(), OLD_RANK, OLD_CUTOFF]):
        for kind, path in paths.items():
            if path.is_symlink() or not path.is_file() or _hash(path) != PINS[kind]:
                raise RuntimeError("pinned input changed: " + kind)
        manifest = json.loads(paths["manifest"].read_bytes())
        if (manifest.get("dataset_scope") != "development_pre2023"
            or manifest.get("protected_confirmation_accessed") is not False
            or manifest.get("tables", {}).get("definitions", {}).get("sha256")
                != PINS["definitions"]):
            raise RuntimeError("pre-2023 source provenance failed")
        old = json.loads(OLD_RANK.read_bytes())
        cutoff_record = json.loads(OLD_CUTOFF.read_bytes())
        if (old.get("source_pins") != PINS
            or old.get("ranked_slots_checked") != 37056
            or old.get("affected_rank12_selected_slots") != 3156
            or old.get("selected_slots_marked_unverified_nonterminal") != 3087
            or cutoff_record.get("source_pins") != PINS
            or cutoff_record.get("production_sql_original_cutoffs_denied") != 134):
            raise RuntimeError("prior signed-off boundary counts/source pins changed")
        with duckdb.connect(":memory:") as con:
            con.execute("SET TimeZone='UTC'")
            source_rows = _source_rank_rows(con, paths["features"], paths["definitions"])

    # Protected source handles close before any output evidence is written.
    if len(source_rows) != 37056:
        raise RuntimeError("frozen rank selection has changed")
    groups = defaultdict(list)
    for row in source_rows:
        day, membership, _, _, _, _, _, available, _ = row
        if day.year >= 2023 or parse_time(available) > parse_time(membership):
            raise RuntimeError("future/protected source data entered model cohort")
        groups[(day, membership)].append(row)
    if len(groups) != 3088:
        raise RuntimeError("frozen historical decision clock coverage changed")

    counts = Counter()
    affected_days = set()
    terminal_slots = 0
    nonterminal_slots = 0
    for (day, cutoff), rank_rows in sorted(groups.items()):
        if [row[8] for row in rank_rows] != list(range(1, 13)):
            raise RuntimeError("incomplete or out-of-order M1..M12 rank")
        affected = [
            r for r in rank_rows
            if (r[2], r[3], str(r[5])) in policy
        ]
        if affected:
            affected_days.add(day)
        terminal = False
        for row in affected:
            source = {
                "venue": row[2], "symbol": row[3],
                "expiration": str(row[5]), "available_at": str(row[7]),
            }
            try:
                observed = fence_ng_expiry_definitions([source], parse_time(cutoff))
            except MarketTruthError as exc:
                if "unverified CME historical expiry" not in str(exc):
                    raise
                terminal = True
                terminal_slots += 1
            else:
                if not observed[0].get("_expiry_unverified"):
                    raise RuntimeError("unsafe nonterminal contract not annotated")
                nonterminal_slots += 1
        if terminal:
            counts["decision_clocks_with_selected_terminal_fence"] += 1
            continue
        original = [_point(row, policy) for row in rank_rows]
        protected = model_safe_ng_curve(original)
        first_bad = next((
            index for index, point in enumerate(original)
            if point["rank_boundary_status"] == "unverified_exchange_expiry"
        ), 12)
        counts["nonterminal_decision_clocks"] += 1
        if first_bad < 12:
            counts["decision_clocks_with_rank_mask"] += 1
        for index, (before, after) in enumerate(zip(original, protected, strict=True)):
            if index < first_bad:
                if after != before:
                    raise RuntimeError("valid historical prefix changed")
                counts["retained_unaffected_slots"] += 1
            else:
                if any(after[field] is not None for field in (
                    "instrument_id", "venue", "contract_identity", "contract_symbol",
                    "expiration", "last_trade_at", "days_to_expiry", "open", "high",
                    "low", "close", "volume", "settle", "open_interest",
                    "cleared_volume", "available_at"
                )) or after["evidence_ids"]:
                    raise RuntimeError("uncertain rank or dependent suffix leaked")
                if (after["missing_reason"] != "unverified_exchange_expiry_rank"
                    or after["rank_boundary_status"] != "unverified_exchange_expiry_rank"):
                    raise RuntimeError("masked rank lacks missingness provenance")
                counts["excluded_unsafe_suffix_slots"] += 1
        # Actual shared production feature evaluator. Source rank identities are
        # historical; numeric inputs are synthetic sentinels, not admitted data.
        snapshot = snapshot_asof(
            {"source_sha256": {"definitions": PINS["definitions"]}},
            day, cutoff, curve_lookup=lambda _day, n, fixed=protected: fixed[:n],
        )
        features = snapshot["features"]
        if first_bad < 12:
            if any(features[field] is not None for field in (
                "curve_mean_price_per_unit", "winter_minus_summer_strip",
                "winter_strip_contracts", "summer_strip_contracts"
            )):
                raise RuntimeError("unsafe full-curve feature emitted")
            if first_bad < 3 and features["m1_m3_slope_per_rank"] is not None:
                raise RuntimeError("uncertain rank leaked via three-rank slope")
            if first_bad < 2 and (
                features["m1_m2_spread_price_per_unit"] is not None
                or features["m1_m2_annualized_carry_proxy"] is not None
            ):
                raise RuntimeError("uncertain rank leaked via M1-M2 spread/carry")
            if first_bad == 0 and any(features[field] is not None for field in (
                "front_price", "front_volume", "front_open_interest",
                "front_liquidity_volume_oi_ratio", "front_days_to_expiry"
            )):
                raise RuntimeError("unverified M1 leaked front features")
        counts["production_feature_evaluations"] += 1
    if (len(affected_days) != old["affected_rank12_selected_dates"]
        or terminal_slots != old["selected_slots_fenced_terminal"]
        or nonterminal_slots != old["selected_slots_marked_unverified_nonterminal"]
        or counts["retained_unaffected_slots"]
            + counts["excluded_unsafe_suffix_slots"]
            != counts["nonterminal_decision_clocks"] * 12):
        raise RuntimeError("source rank cohort and model-output evidence disagree")
    evidence = {
        "schema_version": 1,
        "issue": 482,
        "result": "PASS_CME_FROZEN_SOURCE_RANK_TO_MODEL_OUTPUT_EXCLUSION",
        "source_pins": PINS,
        "pre2023_frozen_cutoffs": len(groups),
        "source_rank_slots": len(source_rows),
        "affected_rank12_selected_dates": len(affected_days),
        "affected_rank12_selected_slots": terminal_slots + nonterminal_slots,
        "terminal_selected_slots_existing_source_fence": terminal_slots,
        "nonterminal_selected_slots_excluded_from_unsafe_rank_suffix": nonterminal_slots,
        "model_output_invariant": dict(sorted(counts.items())),
        "prior_production_cutoff_denials_reused_not_reexecuted": 134,
        "source_rank_to_model_numeric_values": "synthetic_sentinels_only",
        "underlying_source_prices_and_volumes_modified": False,
        "historical_parity_recomputed": False,
        "independent_exchange_intraday_proven": False,
        "research_admitted": False,
        "protected_2023plus_accessed": False,
    }
    RECORD.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    print(json.dumps(evidence, sort_keys=True))
    return evidence


if __name__ == "__main__":
    run()
