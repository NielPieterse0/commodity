"""Verify existing CME exclusion policy against every frozen V3 feature cutoff.

New scoped decision-time gate only; DOES NOT recompute historic parity,
reconstruct exchange expiries, access 2023+ confirmation or grant admission.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime, time
from pathlib import Path

import duckdb

from commodity.market_truth.core import MarketTruthError, parse_time
from commodity.market_truth.ng_expiry import (
    UNQUALIFIED_NG_EXPIRIES,
    fence_ng_expiry_definitions,
    verify_ng_expiry_policy,
)
from commodity.market_truth.query import (
    MarketTruthDataset,
    protected_table_reads,
)

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / ".work/runtime/market_truth_development/market-truth-full-2010-2022-refactor-v3"
FROZEN = (ROOT.parents[1] / "worktrees/356-market-only-nested-walk-forward"
          / ".work/checkpoints/356-market-only-nested-walk-forward/inputs")
RECEIPT = Path(__file__).with_name("cme-frozen-cutoff-exclusion-receipt.json")
PINS = {
    "manifest": "6d3093305c0ae2c6a313be13151b0810bf208c1cb8f429e1bbf58a17e7d89605",
    "definitions": "b803deb0b88d7c0f57625fd46cfa4537e902dd3951cf04aeeba84f95f5dbf4d8",
    "features": "b14ae69bd6ec2910f0cf56fe62f481016801308cebc6ef69e536aa7e593d072e",
}

def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run() -> dict:
    verify_ng_expiry_policy()
    paths = {
        "manifest": SOURCE / "manifest.json",
        "definitions": SOURCE / "definitions.parquet",
        "features": FROZEN / "features.parquet",
    }
    with protected_table_reads(list(paths.values())):
        for key, path in paths.items():
            if not path.is_file() or path.is_symlink() or _hash(path) != PINS[key]:
                raise RuntimeError(f"frozen-cutoff input pin invalid: {key}")
        manifest = json.loads(paths["manifest"].read_bytes())
        if (manifest.get("dataset_scope") != "development_pre2023"
                or manifest.get("protected_confirmation_accessed") is not False
                or manifest.get("tables", {}).get("definitions", {}).get("sha256")
                != PINS["definitions"]):
            raise RuntimeError("not the pinned historical development dataset")
        with duckdb.connect(":memory:") as conn:
            conn.execute("SET TimeZone='UTC'")
            cutoffs = conn.execute("""
                SELECT CAST(trade_date AS DATE) AS day,
                       CAST(available_at AS TIMESTAMPTZ) AS cutoff
                FROM read_parquet(?) ORDER BY day
            """, [str(paths["features"])]).fetchall()
            if (len(cutoffs) != 3088 or len({day for day, _ in cutoffs}) != 3088
                    or any(day.year >= 2023 for day, _ in cutoffs)):
                raise RuntimeError("frozen V3 feature-date cohort mismatch")
            source_rows = conn.execute("""
                SELECT venue, symbol, expiration,
                       MIN(CAST(available_at AS TIMESTAMPTZ)) AS first_seen
                FROM read_parquet(?)
                WHERE venue='NYMEX'
                GROUP BY venue,symbol,expiration
            """, [str(paths["definitions"])]).fetchall()
            first_seen = {(v, s, str(e)): parse_time(a)
                          for v, s, e, a in source_rows}
            identities = {("NYMEX", symbol, exp)
                          for symbol, exp in UNQUALIFIED_NG_EXPIRIES}
            if len(identities) != 14 or not identities <= first_seen.keys():
                raise RuntimeError("policy has an unpinned or unknown contract")
            counters: Counter[str] = Counter()
            fenced_by_contract: dict[tuple[str, str, str], list] = {
                item: [] for item in identities
            }
            for day, raw_cutoff in cutoffs:
                membership = min(
                    parse_time(raw_cutoff),
                    datetime.combine(day, time.max, tzinfo=UTC),
                )
                if membership.date() < day:
                    raise RuntimeError("frozen decision clock precedes session")
                counters["feature_dates"] += 1
                for identity in sorted(identities):
                    venue, symbol, expiry_text = identity
                    if first_seen[identity] > membership:
                        counters["source_not_available_at_cutoff"] += 1
                        continue
                    row = {
                        "venue": venue, "symbol": symbol,
                        "expiration": expiry_text,
                        "available_at": first_seen[identity].isoformat(),
                    }
                    terminal = (abs(
                        (membership.date() - datetime.fromisoformat(expiry_text).date()).days
                    ) <= 7)
                    try:
                        annotated = fence_ng_expiry_definitions([row], membership)
                    except MarketTruthError as exc:
                        if not terminal or "unverified CME historical expiry" not in str(exc):
                            raise
                        counters["terminal_contract_decisions_denied"] += 1
                        fenced_by_contract[identity].append((day, membership))
                    else:
                        if terminal:
                            raise RuntimeError("terminal contract crossed original cutoff")
                        if not annotated[0].get("_expiry_unverified"):
                            raise RuntimeError("source-known uncertain expiry not marked")
                        counters["nonterminal_expiry_feature_null_contract_decisions"] += 1
            if (counters["feature_dates"] != 3088
                    or not all(fenced_by_contract.values())):
                raise RuntimeError("incomplete frozen-cutoff contract coverage")
            # Every actually observed frozen terminal cutoff is checked through
            # the real production SQL prefilter, not only one case per contract.
            # This is a policy-only check: no historical price parity recomputation.
            reader = object.__new__(MarketTruthDataset)
            reader.files = {"definitions": paths["definitions"]}
            production_cutoffs = {
                (day, cutoff)
                for exposures in fenced_by_contract.values()
                for day, cutoff in exposures
            }
            for day, cutoff in sorted(production_cutoffs):
                try:
                    reader._curve_from_parquet(conn, day, cutoff, 12)
                except MarketTruthError as exc:
                    if "unverified CME historical expiry" not in str(exc):
                        raise
                else:
                    raise RuntimeError("Parquet rank prefilter escaped frozen cutoff")
                counters["production_sql_original_cutoffs_denied"] += 1
            if not production_cutoffs:
                raise RuntimeError("no original production cutoff exercised")
            # Stable identity to bind the new evidence without storing source rows.
            selected = {
                "schema_version": 1,
                "issue": 482,
                "result": "PASS_ALL_3088_FROZEN_DECISION_CUTOFFS_SOURCE_FENCE",
                "scope": "pre2023_development_only_not_research_admission",
                "source_pins": PINS,
                "decision_dates_covered": counters["feature_dates"],
                "affected_source_contracts": len(identities),
                "source_not_yet_available_pairs":
                    counters["source_not_available_at_cutoff"],
                "terminal_contract_decisions_denied":
                    counters["terminal_contract_decisions_denied"],
                "nonterminal_source_known_pairs_flagged_unverified":
                    counters["nonterminal_expiry_feature_null_contract_decisions"],
                "production_sql_original_cutoffs_denied":
                    counters["production_sql_original_cutoffs_denied"],
                "selected_rank12_contract_identity_recomputed": False,
                "date_model_is_not_CME_exchange_proof": True,
                "release_blocker_closed": False,
                "protected_confirmation_accessed": False,
                "research_admission": False,
            }
            RECEIPT.write_bytes(
                (json.dumps(selected, indent=2, sort_keys=True) + "\n").encode("utf-8")
            )
            print(json.dumps(selected, sort_keys=True))
            return selected


if __name__ == "__main__":
    run()
