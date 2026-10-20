"""Development-only synthetic ingestion benchmark; no Databento archive access."""

from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

# Executed as a change-local script, not as a repository-root module.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commodity.market_truth import MarketTruthDataset
from commodity.market_truth import query as market_truth_query
from scripts.data import build_ng_market_truth as pipeline


def peak_process_rss_bytes() -> int | None:
    """Read the OS-reported lifetime peak resident set (Windows benchmark)."""
    if sys.platform != "win32":
        return None

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong), ("page_fault_count", ctypes.c_ulong),
            ("peak_working_set_size", ctypes.c_size_t),
            ("working_set_size", ctypes.c_size_t),
            ("quota_peak_paged_pool_usage", ctypes.c_size_t),
            ("quota_paged_pool_usage", ctypes.c_size_t),
            ("quota_peak_nonpaged_pool_usage", ctypes.c_size_t),
            ("quota_nonpaged_pool_usage", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    current = ctypes.windll.kernel32.GetCurrentProcess
    current.restype = ctypes.c_void_p
    get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
    get_memory.restype = ctypes.c_int
    ok = get_memory(
        current(), ctypes.byref(counters), ctypes.sizeof(counters),
    )
    return int(counters.peak_working_set_size) if ok else None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate(root: Path, contracts: int, sessions: int) -> tuple[Path, list[str]]:
    start = date(2022, 4, 1)
    days = [(start + timedelta(days=index)).isoformat() for index in range(sessions)]
    records = {}
    definition_path = root / "definitions.csv"
    with definition_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["instrument_id", "raw_symbol", "expiration", "exchange", "asset", "instrument_class", "ts_event", "ts_recv"])
        for index in range(contracts):
            writer.writerow([
                str(index + 1000), f"NGTEST{index:07d}",
                "2022-12-20T00:00:00Z", "XNYM", "NG", "F",
                "2022-01-01T12:00:00Z", "2022-01-01T12:00:01Z",
            ])
    records["definitions"] = contracts
    bar_path = root / "bars.csv"
    stat_path = root / "statistics.csv"
    with (
        bar_path.open("w", newline="", encoding="utf-8") as bar_stream,
        stat_path.open("w", newline="", encoding="utf-8") as stat_stream,
    ):
        bar_writer, stat_writer = csv.writer(bar_stream), csv.writer(stat_stream)
        bar_writer.writerow(["instrument_id", "trade_date", "ts_event", "available_at", "open", "high", "low", "close", "volume"])
        stat_writer.writerow(["instrument_id", "trade_date", "ts_event", "ts_recv", "stat_type", "quantity"])
        for day in days:
            for index in range(contracts):
                instrument = str(index + 1000)
                bar_writer.writerow([
                    instrument, day, day + "T20:00:00Z",
                    day + "T23:59:00Z", "5.1", "5.4", "5.0", "5.2", "100",
                ])
                stat_writer.writerow([
                    instrument, day, day + "T20:00:00Z",
                    day + "T20:00:01Z", "9", "200",
                ])
    records["bars"] = contracts * sessions
    records["statistics"] = contracts * sessions
    payload = {
        "schema_version": 1, "evidence_class": "development",
        "protected_confirmation_accessed": False,
        "dataset": "GLBX.MDP3", "product_code": "NG",
        "max_trade_date": days[-1],
        "inputs": {
            family: {
                "schema": pipeline.SCHEMAS[family],
                "relative_path": family + ".csv",
                "sha256": sha256(root / (family + ".csv")),
                "row_count": records[family],
            }
            for family in pipeline.SCHEMAS
        },
    }
    manifest = root / "source_manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return manifest, days


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contracts", type=int, default=2000)
    parser.add_argument("--sessions", type=int, default=30)
    args = parser.parse_args()
    if not (1 <= args.contracts <= 20000 and 21 <= args.sessions <= 100):
        raise ValueError("synthetic benchmark size outside bounds")
    runtime = pipeline.ROOT / ".work" / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=runtime, prefix="mt-benchmark-") as folder:
        root = Path(folder)
        began = time.perf_counter()
        manifest, days = generate(root, args.contracts, args.sessions)
        generated_sec = time.perf_counter() - began
        start = time.perf_counter()
        with patch.object(pipeline, "ALLOWED_INPUT_ROOT", root):
            metadata = pipeline.build_from_manifest(
                manifest, root / "materialized", streaming=True
            )
        ingestion_sec = time.perf_counter() - start
        start = time.perf_counter()
        with patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root):
            dataset = MarketTruthDataset(
                root / "materialized",
                expected_content_sha256=metadata["content_sha256"],
            )
            snapshot = dataset.snapshot(
                days[-1], days[-1] + "T23:59:30Z",
                session_history=days[:-1],
            )
        query_sec = time.perf_counter() - start
        print(json.dumps({
            "synthetic_only": True,
            "protected_confirmation_accessed": False,
            "definitions": args.contracts,
            "bars": args.contracts * args.sessions,
            "statistics": args.contracts * args.sessions,
            "rows_processed": args.contracts * (2 * args.sessions + 1),
            "source_csv_bytes": sum((root / f"{name}.csv").stat().st_size for name in pipeline.SCHEMAS),
            "parquet_bytes": sum(info["bytes"] for info in metadata["tables"].values()),
            "generate_seconds": round(generated_sec, 3),
            "ingest_seconds": round(ingestion_sec, 3),
            "ingest_rows_per_second": round(args.contracts * (2 * args.sessions + 1) / ingestion_sec, 1),
            "snapshot_seconds_including_integrity_verification": round(query_sec, 3),
            "snapshot_slots": len(snapshot["curve_points"]),
            "peak_process_rss_bytes": peak_process_rss_bytes(),
            "source_row_reconciliation": metadata["source_row_reconciliation"],
        }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
