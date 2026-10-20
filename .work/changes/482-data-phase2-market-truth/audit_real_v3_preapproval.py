"""Read-only real-history V3 technical diagnostic, never research admission.

Requires exact independently recorded pre-2023 Parquet hashes before parquet reads.
Uses an explicitly test-only, process-scoped admission stub; never asserts
source-owner approval or immutable storage and never alters production trust.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path
from unittest.mock import patch

from commodity.market_truth import MarketTruthDataset, MarketTruthError, approval
from commodity.market_truth import query as market_query

ROOT = Path(__file__).resolve().parents[3]
STORAGE = ROOT / ".work" / "runtime" / "market_truth_development"
DATASET = STORAGE / "market-truth-full-2010-2022-refactor-v3"
EXPECTED_MANIFEST_SHA = "6d3093305c0ae2c6a313be13151b0810bf208c1cb8f429e1bbf58a17e7d89605"
EXPECTED_CONTENT_SHA = "943780ea8eaa7315157385c687e3939777089420c186fd7d8d4b7d781a1f5d94"
EXPECTED_BARS_SHA = "d7b72c4295e67a2c60f64cc1e23c9904885724b096d59d949ea6729e18f9a5ec"
YEARS = tuple(range(2010, 2023))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(years: tuple[int, ...] = YEARS) -> dict:
    import pyarrow.parquet as pq

    manifest_path = DATASET / "manifest.json"
    bars_path = DATASET / "bars.parquet"
    if approval.TRUSTED_SIGNERS:
        raise RuntimeError("production signers unexpectedly configured; refuse diagnostic")
    # Retain real Windows no-write/no-delete-sharing handles from before the
    # first source byte read until after the verified pre-2023 Parquet decode.
    # Other platforms remain fail-closed through the production guard.
    with market_query.protected_table_reads([manifest_path, bars_path]):
        if sha256(manifest_path) != EXPECTED_MANIFEST_SHA:
            raise RuntimeError("pinned real dataset manifest differs; no diagnostic read")
        manifest = json.loads(manifest_path.read_bytes())
        if (manifest["content_sha256"] != EXPECTED_CONTENT_SHA
                or manifest["dataset_scope"] != "development_pre2023"
                or manifest["protected_confirmation_accessed"] is not False
                or manifest["tables"]["bars"]["sha256"] != EXPECTED_BARS_SHA):
            raise RuntimeError("real dataset identity or development boundary differs")
        # Only bytes from the previously audited 2010-2022 bar artifact may
        # be decoded. Never enumerate protected 2023+ archive namespaces.
        if sha256(bars_path) != EXPECTED_BARS_SHA:
            raise RuntimeError("unverified bars bytes; refuse any Parquet decode")
        sessions = sorted({
            str(day) for day in pq.read_table(
                bars_path,
                columns=["trade_date"],
                filters=[("trade_date", "<", "2023-01-01")],
            ).column("trade_date").to_pylist()
            if day is not None and str(day) < "2023-01-01"
        })
    # Confirm unmodified production admission denies this real dataset.
    try:
        MarketTruthDataset(DATASET, expected_content_sha256=EXPECTED_CONTENT_SHA)
    except MarketTruthError as exc:
        if "approval" not in str(exc):
            raise
    else:
        raise RuntimeError("unexpected production approval of real dataset")
    chosen = []
    for year in years:
        matching = [day for day in sessions if day.startswith(str(year) + "-")]
        if not matching:
            raise RuntimeError(f"expected pre-2023 market sessions missing: {year}")
        chosen.append(matching[len(matching) // 2])
    results = []
    # This patch is ONLY a bounded technical API exercise, not a signed catalog.
    # A new guarded source recheck occurs after the admission-denied probe.
    # Keep the same held file/directory handles through every technical query.
    with (
        market_query.protected_table_reads([
            manifest_path, bars_path,
            DATASET / "definitions.parquet", DATASET / "statistics.parquet",
            market_query.DEFAULT_APPROVAL_CATALOG,
        ]),
        patch.object(market_query, "_assert_independent_admission", return_value=None),
    ):
        if (sha256(manifest_path) != EXPECTED_MANIFEST_SHA
                or sha256(bars_path) != EXPECTED_BARS_SHA):
            raise RuntimeError("source mutated before guarded V3 API read")
        reader = MarketTruthDataset(DATASET, expected_content_sha256=EXPECTED_CONTENT_SHA)
        for day in chosen:
            index = bisect.bisect_left(sessions, day)
            previous = sessions[max(0, index - 20):index]
            response = reader.snapshot(
                day,
                datetime.combine(
                    date.fromisoformat(day), time(23, 59, 59), tzinfo=UTC,
                ),
                session_history=previous,
            )
            if (response["dataset_content_sha256"] != EXPECTED_CONTENT_SHA
                    or response["protected_confirmation_accessed"] is not False
                    or len(response["curve_points"]) != 12
                    or len(response["features"]) != 21):
                raise RuntimeError("real V3 API response contract mismatch")
            if (int(day[:4]) <= 2014
                    and response["features"]["front_open_interest"] is not None):
                raise RuntimeError("undated 2010-14 open interest illegally promoted")
            results.append({
                "year": int(day[:4]),
                "history_sessions": len(previous),
                "curve_slots": len(response["curve_points"]),
                "available_curve_slots": response["features"]["available_curve_slots"],
                "front_price_available": response["features"]["front_price"] is not None,
                "front_open_interest_available": response["features"]["front_open_interest"] is not None,
            })
    if approval.TRUSTED_SIGNERS:
        raise RuntimeError("real trust unexpectedly modified by read-only diagnostic")
    return {
        "status": "diagnostic_pass_not_research_admission",
        "dataset_content_sha256": EXPECTED_CONTENT_SHA,
        "production_admission_denied": True,
        "test_bypass_scope_only": True,
        "independent_signer_commissioned": False,
        "immutable_storage_proven": False,
        "tested_years": results,
        "protected_confirmation_accessed": False,
    }


if __name__ == "__main__":
    requested = tuple(int(value) for value in sys.argv[1:]) or YEARS
    if not set(requested).issubset(YEARS):
        raise SystemExit("diagnostic restricted to pre-2023 years")
    print(json.dumps(run(requested), indent=2, sort_keys=True))
