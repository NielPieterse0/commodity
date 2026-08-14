from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from commodity.config import data_config
from commodity.databento_futures_provider import (
    DATABENTO_DATASET,
    canonicalize_databento_dbn_history,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rows_sha256(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(
        index=False,
        lineterminator="\n",
        date_format="%Y-%m-%dT%H:%M:%S.%f%z",
        float_format="%.12g",
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


_ARROW_TYPES = {
    "trade_date": pa.timestamp("ns", tz="UTC"),
    "contract_id": pa.string(),
    "expiration": pa.timestamp("ns", tz="UTC"),
    "settle": pa.float64(),
    "open": pa.float64(),
    "high": pa.float64(),
    "low": pa.float64(),
    "close": pa.float64(),
    "volume": pa.float64(),
    "open_interest": pa.float64(),
    "available_at": pa.timestamp("ns", tz="UTC"),
}


def _canonical_arrow_table(frame: pd.DataFrame, schema: dict[str, Any]) -> pa.Table:
    ordered = [
        column
        for column in schema["required_columns"] + schema.get("optional_columns", [])
        if column in frame.columns
    ]
    unknown = sorted(set(frame.columns) - set(ordered))
    if unknown:
        raise ValueError(f"Unsupported canonical Parquet columns: {unknown}")
    arrow_schema = pa.schema([(column, _ARROW_TYPES[column]) for column in ordered])
    return pa.Table.from_pandas(
        frame.loc[:, ordered],
        schema=arrow_schema,
        preserve_index=False,
        safe=True,
    ).replace_schema_metadata(None)


def convert_dbn_to_parquet(
    definition_path: Path,
    statistics_path: Path,
    output_path: Path,
    metadata_path: Path,
    *,
    product_code: str,
    retrieved_at: str,
    dataset: str = DATABENTO_DATASET,
) -> dict[str, Any]:
    contract_schema = data_config()["canonical_contract_schema"]
    frame, metadata = canonicalize_databento_dbn_history(
        definition_path,
        statistics_path,
        schema=contract_schema,
        product_code=product_code,
        retrieved_at=retrieved_at,
        dataset=dataset,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    table = _canonical_arrow_table(frame, contract_schema)
    frame = frame.loc[:, table.column_names]
    pq.write_table(
        table,
        output_path,
        compression="zstd",
        version="2.6",
        data_page_version="1.0",
        use_dictionary=False,
        write_statistics=True,
    )
    receipt = {
        "dataset": dataset,
        "product_code": product_code,
        "retrieved_at": retrieved_at,
        "rows": len(frame),
        "columns": list(frame.columns),
        "rows_sha256": _rows_sha256(frame),
        "parquet_sha256": _sha256_file(output_path),
        "canonical_metadata": metadata,
    }
    metadata_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return receipt


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Canonicalize preserved Databento DBN files to deterministic Parquet."
    )
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--statistics", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--metadata-output", required=True, type=Path)
    parser.add_argument("--product-code", required=True)
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--dataset", default=DATABENTO_DATASET)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    receipt = convert_dbn_to_parquet(
        args.definition,
        args.statistics,
        args.output,
        args.metadata_output,
        product_code=args.product_code,
        retrieved_at=args.retrieved_at,
        dataset=args.dataset,
    )
    print(json.dumps(receipt, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
