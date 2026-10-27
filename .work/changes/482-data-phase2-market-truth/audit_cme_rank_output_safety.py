"""New read-only route-B check: actual frozen M1-M12 rank memberships under CME fence.

Reuses pinned source/frozen inputs, does not recalculate old features or counterfactual
expiry dates, and does not permit research admission or use protected confirmation.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import duckdb
from audit_cme_frozen_cutoffs import FROZEN, PINS, SOURCE, _hash

from commodity.market_truth.core import MarketTruthError, parse_time
from commodity.market_truth.ng_expiry import (
    UNQUALIFIED_NG_EXPIRIES,
    fence_ng_expiry_definitions,
    verify_ng_expiry_policy,
)
from commodity.market_truth.query import protected_table_reads

OUTPUT = Path(__file__).with_name("cme-rank-output-safety-receipt.json")
EXPOSURE = Path(__file__).with_name("cme-expiry-exposure-receipt.json")


def run() -> dict:
    verify_ng_expiry_policy()
    paths = {
        "manifest": SOURCE / "manifest.json",
        "definitions": SOURCE / "definitions.parquet",
        "features": FROZEN / "features.parquet",
    }
    with protected_table_reads([*paths.values(), EXPOSURE]):
        for kind, path in paths.items():
            if path.is_symlink() or not path.is_file() or _hash(path) != PINS[kind]:
                raise RuntimeError("pinned source changed: " + kind)
        manifest = json.loads(paths["manifest"].read_bytes())
        if (manifest.get("dataset_scope") != "development_pre2023"
                or manifest.get("protected_confirmation_accessed") is not False
                or manifest.get("tables", {}).get("definitions", {}).get("sha256")
                != PINS["definitions"]):
            raise RuntimeError("historical development source gate mismatch")
        historical = json.loads(EXPOSURE.read_bytes())
        if (historical.get("source_sha256", {}).get("definitions") != PINS["definitions"]
                or historical.get("source_sha256", {}).get("features") != PINS["features"]
                or historical.get("frozen_feature_sessions") != 3088):
            raise RuntimeError("old exposure receipt not bound to source pins")

        with duckdb.connect(":memory:") as con:
            con.execute("SET TimeZone='UTC'")
            # Select the AS-OF source definition and its ACTUAL M1..M12 rank.
            # Historical price comparisons/counterfactual exchange schedules
            # are deliberately not executed by this check.
            rank_rows = con.execute("""
                WITH sessions AS (
                  SELECT CAST(trade_date AS DATE) AS day,
                     LEAST(CAST(available_at AS TIMESTAMPTZ),
                       CAST(trade_date AS DATE)::TIMESTAMPTZ
                       + INTERVAL '1 day' - INTERVAL '1 microsecond') membership
                  FROM read_parquet(?)
                ), ids AS (
                  SELECT DISTINCT instrument_id FROM read_parquet(?)
                ), eligible AS (
                  SELECT s.day, s.membership, d.venue, d.symbol,
                         d.instrument_id, d.expiration, d.last_trade_at,
                         d.available_at
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
                       expiration, available_at, rank
                FROM ranked WHERE rank <= 12
                ORDER BY day, rank
            """, [
                str(paths["features"]), str(paths["definitions"]),
                str(paths["definitions"]),
            ]).fetchall()

        if len(rank_rows) != 3088 * 12:
            raise RuntimeError("frozen 12-rank source selection is incomplete")
        policy = {("NYMEX", symbol, expiry)
                  for symbol, expiry in UNQUALIFIED_NG_EXPIRIES}
        days, counted, nonterminal, terminal = set(), Counter(), 0, 0
        for day, membership, venue, symbol, instrument_id, expiry, available, rank in rank_rows:
            days.add(day)
            identity = (venue, symbol, str(expiry))
            if identity not in policy:
                continue
            if parse_time(available) > parse_time(membership):
                raise RuntimeError("rank uses future unavailable source definition")
            row = {
                "venue": venue, "symbol": symbol, "expiration": str(expiry),
                "available_at": str(available),
                "instrument_id": instrument_id,
            }
            try:
                flag = fence_ng_expiry_definitions([row], parse_time(membership))[0]
            except MarketTruthError as exc:
                if "unverified CME historical expiry" not in str(exc):
                    raise
                terminal += 1
            else:
                if not flag.get("_expiry_unverified"):
                    raise RuntimeError("affected model-visible rank unmarked")
                nonterminal += 1
            counted[str(day)] += 1
        if len(days) != 3088 or not counted:
            raise RuntimeError("frozen rank date coverage incomplete")
        selected = sum(counted.values())
        if (selected != historical["uncertain_rank12_selected_rows"]
                or len(counted) != historical["uncertain_rank12_selected_sessions"]):
            raise RuntimeError("selected rank exposure disagrees with pinned old receipt")
        evidence = {
            "schema_version": 1,
            "issue": 482,
            "result": "PASS_AFFECTED_FROZEN_RANK12_POLICY_CLASSIFICATION",
            "source_pins": PINS,
            "ranked_slots_checked": len(rank_rows),
            "frozen_decision_dates_checked": len(days),
            "affected_rank12_selected_slots": selected,
            "affected_rank12_selected_dates": len(counted),
            "selected_slots_fenced_terminal": terminal,
            "selected_slots_marked_unverified_nonterminal": nonterminal,
            "all_affected_selected_slots_policy_classified": True,
            "independent_CME_intraday_verified": False,
            "selected_unaffected_fields_recomputed": False,
            "production_admission": False,
            "source_2023plus_protected_accessed": False,
            "CME_original_blocker_closed": False,
        }
        OUTPUT.write_bytes(
            (json.dumps(evidence, sort_keys=True, indent=2) + "\n").encode("utf-8")
        )
        print(json.dumps(evidence, sort_keys=True))
        return evidence


if __name__ == "__main__":
    run()
