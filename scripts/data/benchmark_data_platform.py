from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import tempfile
import time
from pathlib import Path

import duckdb
import numpy as np
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "data" / "manifests" / "phase1-benchmark.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timed(con: duckdb.DuckDBPyConnection, sql: str, params: list[object]) -> tuple[float, object]:
    started = time.perf_counter()
    result = con.execute(sql, params).fetchone()
    return time.perf_counter() - started, None if result is None else result[0]


def _build_table(rows: int) -> pa.Table:
    rng = np.random.default_rng(479)
    index = np.arange(rows, dtype=np.int64)
    session_days = index % 4383
    base = np.datetime64("2011-01-01", "D")
    trade_date = base + session_days.astype("timedelta64[D]")
    rank = (index % 12 + 1).astype(np.int16)
    settle = 3.0 + 0.25 * np.sin(index / 31.0) + rng.normal(0.0, 0.15, rows)
    arrays: dict[str, object] = {
        "trade_date": trade_date,
        "contract_rank": rank,
        "settle": settle,
        "volume": rng.integers(1_000, 150_000, rows, dtype=np.int64),
    }
    for number in range(1, 7):
        arrays[f"feature_{number}"] = rng.normal(0.0, 1.0, rows)
    return pa.table(arrays)


def run_benchmark(rows: int) -> dict[str, object]:
    temp_root = Path(os.environ.get("COMMODITY_RUNTIME_TMP", str(ROOT / ".work" / "tmp")))
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="issue479-benchmark-", dir=temp_root) as temp_dir:
        temp = Path(temp_dir)
        parquet_path = temp / "ng_market.parquet"
        spill_dir = temp / "duckdb-spill"
        spill_dir.mkdir()
        table = _build_table(rows)
        row_group_size = 250_000
        pq.write_table(
            table,
            parquet_path,
            compression="zstd",
            row_group_size=row_group_size,
            use_dictionary=False,
        )
        metadata = pq.ParquetFile(parquet_path).metadata
        parquet_bytes = parquet_path.stat().st_size
        memory_limit_mb = max(16, min(64, max(1, parquet_bytes // (4 * 1024 * 1024))))
        con = duckdb.connect(database=":memory:")
        try:
            con.execute(f"SET memory_limit='{memory_limit_mb}MB'")
            con.execute("SET threads=2")
            con.execute("SET temp_directory=?", [str(spill_dir)])

            projection_seconds, projection_value = _timed(
                con,
                """
                SELECT avg(settle)
                FROM read_parquet(?)
                WHERE contract_rank <= 4
                  AND trade_date >= DATE '2018-01-01'
                  AND trade_date < DATE '2020-01-01'
                """,
                [str(parquet_path)],
            )
            plan = con.execute(
                """
                EXPLAIN SELECT avg(settle)
                FROM read_parquet(?)
                WHERE contract_rank <= 4
                  AND trade_date >= DATE '2018-01-01'
                  AND trade_date < DATE '2020-01-01'
                """,
                [str(parquet_path)],
            ).fetchall()
            plan_text = "\n".join(str(row) for row in plan)

            window_seconds, window_value = _timed(
                con,
                """
                SELECT sum(rolling_mean)
                FROM (
                    SELECT avg(settle) OVER (
                        PARTITION BY contract_rank
                        ORDER BY trade_date, settle, feature_6
                        ROWS BETWEEN 20 PRECEDING AND CURRENT ROW
                    ) AS rolling_mean
                    FROM read_parquet(?)
                )
                """,
                [str(parquet_path)],
            )

            constrained_seconds, constrained_value = _timed(
                con,
                """
                SELECT sum(row_number_value)
                FROM (
                    SELECT row_number() OVER (ORDER BY feature_6, settle) AS row_number_value
                    FROM read_parquet(?)
                )
                """,
                [str(parquet_path)],
            )

            decision_rows = pl.DataFrame(
                {
                    "decision_time": pl.datetime_range(
                        start=pl.datetime(2011, 1, 1),
                        end=pl.datetime(2022, 12, 31),
                        interval="1d",
                        eager=True,
                    ),
                    "commodity_id": ["NG"] * 4383,
                }
            )
            sparse_rows = decision_rows[::7].with_columns(
                pl.col("decision_time").alias("available_at"),
                (pl.arange(0, pl.len(), eager=False).cast(pl.Float64) / 10.0).alias("sparse_value"),
            ).select("commodity_id", "available_at", "sparse_value")
            con.register("decisions", decision_rows.to_arrow())
            con.register("sparse_facts", sparse_rows.to_arrow())

            asof_seconds, asof_count = _timed(
                con,
                """
                SELECT count(*)
                FROM decisions AS d
                ASOF LEFT JOIN sparse_facts AS f
                  ON d.commodity_id = f.commodity_id
                 AND d.decision_time >= f.available_at
                """,
                [],
            )
            sparse_join_seconds, sparse_nulls = _timed(
                con,
                """
                SELECT count(*) FILTER (WHERE f.sparse_value IS NULL)
                FROM decisions AS d
                LEFT JOIN sparse_facts AS f
                  ON d.commodity_id = f.commodity_id
                 AND d.decision_time = f.available_at
                """,
                [],
            )
        finally:
            con.close()

        spill_bytes = sum(
            path.stat().st_size for path in spill_dir.rglob("*") if path.is_file()
        )
        return {
            "schema_version": 1,
            "benchmark_id": "issue-479-ng-local-platform-v1",
            "protected_confirmation_accessed": False,
            "dataset": {
                "kind": "synthetic_ng_shaped_non_evidence",
                "rows": rows,
                "columns": table.num_columns,
                "parquet_files": 1,
                "parquet_bytes": parquet_bytes,
                "parquet_sha256": _sha256(parquet_path),
                "row_groups": metadata.num_row_groups,
                "row_group_target_rows": row_group_size,
                "compression": "zstd",
            },
            "engine": {
                "duckdb_version": duckdb.__version__,
                "polars_version": pl.__version__,
                "pyarrow_version": pa.__version__,
                "python_version": platform.python_version(),
                "memory_limit_mb": memory_limit_mb,
                "input_file_to_memory_limit_ratio": parquet_bytes / (memory_limit_mb * 1024 * 1024),
            },
            "workloads": {
                "parquet_projection_filter": {
                    "seconds": projection_seconds,
                    "result": projection_value,
                    "plan_has_filters": "Filters" in plan_text or "FILTER" in plan_text.upper(),
                    "plan_has_projection": "Projections" in plan_text or "PROJECTION" in plan_text.upper(),
                },
                "window": {"seconds": window_seconds, "result": window_value},
                "asof_join": {"seconds": asof_seconds, "joined_rows": int(asof_count)},
                "sparse_join": {"seconds": sparse_join_seconds, "null_rows": int(sparse_nulls)},
                "constrained_memory_scan": {
                    "seconds": constrained_seconds,
                    "result": int(constrained_value),
                    "input_exceeds_configured_memory": parquet_bytes > memory_limit_mb * 1024 * 1024,
                    "observed_spill_bytes_after_query": spill_bytes,
                },
            },
            "layout_decision": {
                "measured_row_group_rows": row_group_size,
                "measured_file_bytes": parquet_bytes,
                "tiny_file_fragmentation_observed": False,
                "decision": "retain workload-tuned Parquet layout; do not encode one universal partition/file-size rule",
                "tuning_basis": "local synthetic representative scan/window/join workload",
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1_500_000)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.rows < 100_000:
        raise SystemExit("--rows must be at least 100000 for a representative benchmark")
    evidence = run_benchmark(args.rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "output": str(args.output),
        "rows": args.rows,
        "parquet_bytes": evidence["dataset"]["parquet_bytes"],
        "input_file_to_memory_limit_ratio": evidence["engine"]["input_file_to_memory_limit_ratio"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
