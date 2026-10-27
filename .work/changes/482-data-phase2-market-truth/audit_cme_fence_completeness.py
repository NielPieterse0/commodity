"""Single-purpose source-pinned check of the released 14-contract NG exclusion.
No CME date reconstruction, V2/V3 parity rerun, or research admission.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, time
from pathlib import Path

import duckdb

from commodity.market_truth.core import MarketTruthError
from commodity.market_truth.ng_expiry import (
    UNQUALIFIED_NG_EXPIRIES,
    fence_ng_expiry_definitions,
    verify_ng_expiry_policy,
)

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / ".work/runtime/market_truth_development/market-truth-full-2010-2022-refactor-v3"
OUTPUT = Path(__file__).with_name("cme-fence-completeness-receipt.json")
PINS = {
    "manifest.json": "6d3093305c0ae2c6a313be13151b0810bf208c1cb8f429e1bbf58a17e7d89605",
    "definitions.parquet": "b803deb0b88d7c0f57625fd46cfa4537e902dd3951cf04aeeba84f95f5dbf4d8",
}

def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as reader:
        for block in iter(lambda: reader.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def audit() -> None:
    verify_ng_expiry_policy()
    for name, sha in PINS.items():
        path = DATA / name
        if not path.is_file() or path.is_symlink() or digest(path) != sha:
            raise RuntimeError("wrong pinned historical input: " + name)
    manifest = json.loads((DATA / "manifest.json").read_bytes())
    if (manifest.get("dataset_scope") != "development_pre2023"
            or manifest.get("protected_confirmation_accessed") is not False
            or manifest.get("tables", {}).get("definitions", {}).get("sha256")
            != PINS["definitions.parquet"]):
        raise RuntimeError("not the approved-for-diagnostic pre-2023 scope")
    con = duckdb.connect(":memory:")
    con.execute("SET TimeZone='UTC'")
    rows = con.execute("""
        SELECT venue, symbol, expiration,
               MIN(CAST(available_at AS TIMESTAMPTZ)) first_available
        FROM read_parquet(?)
        WHERE venue='NYMEX'
        GROUP BY venue, symbol, expiration
    """, [str(DATA / "definitions.parquet")]).fetchall()
    actual = {(venue, symbol, str(exp)): available for
              venue, symbol, exp, available in rows}
    expected = {("NYMEX", symbol, expiration)
                for symbol, expiration in UNQUALIFIED_NG_EXPIRIES}
    if not expected <= set(actual):
        raise RuntimeError("source cohort missing pinned CME exclusions")
    bars = DATA / "bars.parquet"
    if (bars.is_symlink() or
            digest(bars) != manifest["tables"]["bars"]["sha256"]):
        raise RuntimeError("bar-session reference changed")
    sessions = [
        row[0] for row in con.execute(
            "SELECT DISTINCT CAST(trade_date AS DATE) FROM read_parquet(?) "
            "WHERE trade_date < '2023-01-01' ORDER BY 1",
            [str(bars)],
        ).fetchall()
    ]
    if not sessions:
        raise RuntimeError("no pre-2023 sessions")
    checked = 0
    eligible_contracts = set()
    for venue, symbol, expiry in sorted(expected):
        source = {
            "venue": venue, "symbol": symbol, "expiration": expiry,
            "available_at": actual[(venue, symbol, expiry)].isoformat(),
        }
        expiry_day = datetime.fromisoformat(expiry).date()
        for day in sessions:
            if abs((day - expiry_day).days) > 7:
                continue
            cutoff = datetime.combine(day, time(23, 59, 59, tzinfo=UTC))
            if actual[(venue, symbol, expiry)] > cutoff:
                continue
            try:
                fence_ng_expiry_definitions([source], cutoff)
            except MarketTruthError as exc:
                if "unverified CME historical expiry" not in str(exc):
                    raise
            else:
                raise RuntimeError("CME terminal rank escaped fence")
            eligible_contracts.add((venue, symbol, expiry))
            checked += 1
    if eligible_contracts != expected or checked == 0:
        raise RuntimeError("one or more source-contract windows untested")
    # Exercise the production SQL prefilter on every distinct source contract.
    # Diagnostic only: no dataset admission is forged or asserted here.
    from commodity.market_truth.query import MarketTruthDataset

    reader = object.__new__(MarketTruthDataset)
    reader.files = {"definitions": DATA / "definitions.parquet"}
    parquet_denied = 0
    for _, _, expiry in sorted(expected):
        day = datetime.fromisoformat(expiry).date()
        cutoff = datetime.combine(day, time(23, 59, 59, tzinfo=UTC))
        try:
            reader._curve_from_parquet(con, day, cutoff, 12)
        except MarketTruthError as exc:
            if "unverified CME historical expiry" not in str(exc):
                raise
        else:
            raise RuntimeError("production Parquet CME prefilter escaped")
        parquet_denied += 1
    receipt = {
        "schema_version": 1,
        "issue": 482,
        "result": "PASS_SOURCE_COHORT_TERMINAL_FENCE_ONLY",
        "source_scope": "development_pre2023",
        "source_pins": PINS,
        "bar_sha256": manifest["tables"]["bars"]["sha256"],
        "historical_observed_session_dates": len(sessions),
        "policy_contracts": len(expected),
        "contracts_with_fenced_historical_session": len(eligible_contracts),
        "observed_contract_session_windows_denied": checked,
        "production_parquet_expiry_checks_denied": parquet_denied,
        "frozen_3088_feature_dates_full_replay": False,
        "previous_receipt_for_frozen_date_subset":
            "frozen-v2-v3-feature-parity-receipt.json",
        "official_exchange_expiry_qualified": False,
        "research_admission": False,
        "protected_confirmation_accessed": False,
    }
    OUTPUT.write_bytes((json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    con.close()
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    audit()
