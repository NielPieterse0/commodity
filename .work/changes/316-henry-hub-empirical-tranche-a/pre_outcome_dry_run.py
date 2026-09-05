from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import databento
import pandas as pd
from databento_dbn import StatMsg

from commodity.providers.databento_futures import (
    CLEARED_VOLUME_STAT_TYPE,
    DATABENTO_DATASET,
    databento_contract_id,
    decode_databento_dbn_file,
    map_databento_instrument_symbols,
)
from commodity.research_construction import (
    build_samuelson_eligibility,
    select_last_eligible_curve_date_per_month,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_definitions(files: list[Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    keep = [
        "instrument_id",
        "raw_symbol",
        "ts_recv",
        "ts_event",
        "instrument_class",
        "asset",
        "exchange",
        "activation",
        "expiration",
    ]
    for path in files:
        frame, _ = decode_databento_dbn_file(
            path,
            expected_schema="definition",
            dataset=DATABENTO_DATASET,
        )
        frames.append(frame.loc[:, keep].copy())
    definitions = pd.concat(frames, ignore_index=True)
    definitions = definitions[
        definitions["asset"].astype(str).eq("NG")
        & definitions["instrument_class"].astype(str).eq("F")
        & definitions["exchange"].astype(str).eq("XNYM")
    ].copy()
    if definitions.empty:
        raise ValueError("no NYMEX NG outright definitions")
    return definitions


def load_cleared_volume(files: list[Path]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for path in files:
        store = databento.DBNStore.from_file(path)
        if str(store.dataset) != DATABENTO_DATASET or str(store.schema) != "statistics":
            raise ValueError(f"statistics identity mismatch: {path.name}")
        for record in store:
            if not isinstance(record, StatMsg):
                continue
            if int(record.stat_type) != CLEARED_VOLUME_STAT_TYPE:
                continue
            quantity = int(record.quantity)
            ts_ref = int(record.ts_ref)
            if quantity < 0 or quantity >= 2**63 - 1:
                continue
            if ts_ref <= 0 or ts_ref >= 2**63 - 1:
                continue
            rows.append(
                {
                    "instrument_id": int(record.instrument_id),
                    "ts_ref": pd.Timestamp(ts_ref, unit="ns", tz="UTC"),
                    "ts_event": pd.Timestamp(int(record.ts_event), unit="ns", tz="UTC"),
                    "ts_recv": pd.Timestamp(int(record.ts_recv), unit="ns", tz="UTC"),
                    "quantity": quantity,
                }
            )
    if not rows:
        raise ValueError("no valid cleared-volume records")
    return pd.DataFrame(rows)


def build_volume_contract_days(
    definitions: pd.DataFrame,
    volume: pd.DataFrame,
) -> pd.DataFrame:
    volume = volume.copy()
    volume["instrument_id"] = volume["instrument_id"].astype(
        definitions["instrument_id"].dtype
    )
    mapped = map_databento_instrument_symbols(definitions, volume)
    for column in ("definition_activation", "definition_expiration"):
        mapped[column] = pd.to_datetime(mapped[column], utc=True, errors="coerce")
    if mapped[["definition_activation", "definition_expiration"]].isna().any().any():
        raise ValueError("mapped volume rows lack time-valid activation/expiration identity")
    mapped["trade_date"] = mapped["ts_ref"].dt.normalize()
    mapped["contract_id"] = databento_contract_id(
        mapped["symbol"], mapped["definition_expiration"]
    )
    mapped = mapped.sort_values(
        ["contract_id", "trade_date", "ts_event"], kind="stable"
    ).drop_duplicates(["contract_id", "trade_date"], keep="last")
    mapped = mapped[
        mapped["trade_date"].ge(mapped["definition_activation"].dt.normalize())
        & mapped["trade_date"].le(mapped["definition_expiration"].dt.normalize())
    ].copy()
    return pd.DataFrame(
        {
            "trade_date": mapped["trade_date"],
            "contract_id": mapped["contract_id"],
            "expiration": mapped["definition_expiration"],
            "volume": mapped["quantity"],
        }
    )


def build_active_identity_panel(definitions: pd.DataFrame) -> pd.DataFrame:
    panel = definitions.loc[
        :, ["instrument_id", "raw_symbol", "ts_recv", "activation", "expiration"]
    ].copy()
    panel["_definition_time"] = pd.to_datetime(panel["ts_recv"], utc=True, errors="coerce")
    panel["activation"] = pd.to_datetime(panel["activation"], utc=True, errors="coerce")
    panel["expiration"] = pd.to_datetime(panel["expiration"], utc=True, errors="coerce")
    if panel[["_definition_time", "activation", "expiration"]].isna().any().any():
        raise ValueError("definition panel contains invalid timestamps")
    panel["trade_date"] = panel["_definition_time"].dt.normalize()
    panel = panel[panel["trade_date"].dt.weekday.lt(5)].copy()
    panel = panel.sort_values(
        ["trade_date", "instrument_id", "_definition_time"], kind="stable"
    ).drop_duplicates(["trade_date", "instrument_id"], keep="last")
    panel = panel[
        panel["trade_date"].ge(panel["activation"].dt.normalize())
        & panel["trade_date"].le(panel["expiration"].dt.normalize())
    ].copy()
    panel["contract_id"] = databento_contract_id(panel["raw_symbol"], panel["expiration"])
    return panel[["trade_date", "contract_id", "expiration"]].drop_duplicates()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    definition_dir = args.archive_root / "definition" / "GLBX-20260813-4LWDSMFX5T"
    statistics_dir = args.archive_root / "statistics" / "GLBX-20260813-TVQMDDWSDJ"
    definition_files = sorted(definition_dir.glob("*.definition.dbn.zst"))
    statistics_files = sorted(statistics_dir.glob("*.statistics.dbn.zst"))
    if len(definition_files) != 17 or len(statistics_files) != 17:
        raise ValueError("expected 17 annual/partial archive files per schema")

    definitions = load_definitions(definition_files)
    volume = load_cleared_volume(statistics_files)
    contract_days = build_volume_contract_days(definitions, volume)
    samuelson = build_samuelson_eligibility(contract_days)
    primary = samuelson[samuelson["eligible_primary"]].copy()

    active_panel = build_active_identity_panel(definitions)
    curve_dates = select_last_eligible_curve_date_per_month(
        active_panel,
        required_maturities=6,
    )
    symbol_counts = definitions.groupby("instrument_id")["raw_symbol"].nunique()
    reused_ids = int(symbol_counts.gt(1).sum())
    evidence = {
        "schema_version": 1,
        "archive_root": args.archive_root.as_posix(),
        "protected_settlement_price_accessed": False,
        "statistics_access_contract": {
            "all_records": ["stat_type"],
            "cleared_volume_only": [
                "instrument_id",
                "ts_ref",
                "ts_event",
                "ts_recv",
                "quantity",
            ],
            "settlement_price": "never accessed",
        },
        "definition_files": len(definition_files),
        "statistics_files": len(statistics_files),
        "definition_manifest_sha256": sha256_file(definition_dir / "manifest.json"),
        "statistics_manifest_sha256": sha256_file(statistics_dir / "manifest.json"),
        "instrument_ids_reused_across_symbols": reused_ids,
        "rep001": {
            "raw_cleared_volume_contract_days": len(contract_days),
            "positive_volume_contract_days": len(primary),
            "contract_clusters": int(primary["contract_id"].nunique()),
            "dte_bucket_counts": {
                str(key): int(value)
                for key, value in primary["dte_bucket"].value_counts(sort=False).items()
            },
        },
        "rep002": {
            "trade_dates_screened": int(active_panel["trade_date"].nunique()),
            "eligible_months": len(curve_dates),
            "first_snapshot": curve_dates["trade_date"].min().date().isoformat(),
            "last_snapshot": curve_dates["trade_date"].max().date().isoformat(),
            "minimum_active_maturities": int(curve_dates["available_maturities"].min()),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
