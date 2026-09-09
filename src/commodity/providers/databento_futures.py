from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from commodity.config import data_config
from commodity.market_data import (
    DataContractViolation,
    validate_contract_history,
    validate_contract_metadata,
)
from commodity.providers import MissingCredential
from commodity.snapshots import SnapshotWriter

DATABENTO_API_BASE = "https://hist.databento.com/v0"
DATABENTO_DATASET = "GLBX.MDP3"
DATABENTO_ENV_KEY = "DATABENTO_API_KEY"
DATABENTO_ARCHIVE_RECONSTRUCTION_VERSION = "metadata-symbology-v2"
FINAL_SETTLEMENT_FLAG = 1 << 0
INTRADAY_SETTLEMENT_FLAG = 1 << 3
LEGACY_SETTLEMENT_FLAG_NORMALIZATION_END = "2015-11-20T00:00:00Z"
LEGACY_PRELIMINARY_SETTLEMENT_FLAGS = frozenset({100, 101})
SETTLEMENT_STAT_TYPE = 3
CLEARED_VOLUME_STAT_TYPE = 6
STATISTICS_CAPTURE_GRACE_DAYS = 3
DEFAULT_MAX_AUTO_RECORDS = 50_000
OFFLINE_DBN_SCHEMAS = frozenset({"definition", "statistics", "ohlcv-1d"})


class DatabentoApiError(RuntimeError):
    pass


class DatabentoOfflineDecodeError(RuntimeError):
    pass


def _load_databento_module() -> Any:
    try:
        import databento
    except ImportError as exc:
        raise DatabentoOfflineDecodeError(
            "offline DBN decoding requires the Commodity databento dependency"
        ) from exc
    return databento


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_adjacent_databento_job_provenance(
    source_path: Path,
    *,
    expected_schema: str,
    dataset: str,
) -> dict[str, Any]:
    metadata_path = source_path.parent / "metadata.json"
    if not metadata_path.exists():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatabentoOfflineDecodeError(
            f"invalid adjacent Databento job metadata: {metadata_path}"
        ) from exc
    query = payload.get("query")
    job_id = str(payload.get("job_id", "")).strip()
    if not job_id or not isinstance(query, dict):
        raise DatabentoOfflineDecodeError(
            f"incomplete adjacent Databento job metadata: {metadata_path}"
        )
    if query.get("dataset") != dataset or query.get("schema") != expected_schema:
        raise DatabentoOfflineDecodeError(
            f"adjacent Databento job metadata does not match {expected_schema}: {metadata_path}"
        )
    return {
        "provider_job_id": job_id,
        "provider_metadata_file": metadata_path.name,
        "provider_metadata_sha256": _sha256_file(metadata_path),
    }


def _open_databento_dbn_store(
    path: Path | str,
    *,
    expected_schema: str,
    dataset: str,
) -> tuple[Any, dict[str, Any]]:
    source_path = Path(path)
    if expected_schema not in OFFLINE_DBN_SCHEMAS:
        raise DatabentoOfflineDecodeError(
            f"unsupported offline Databento DBN schema: {expected_schema}"
        )
    databento = _load_databento_module()
    try:
        store = databento.DBNStore.from_file(source_path)
    except Exception as exc:
        raise DatabentoOfflineDecodeError(
            f"failed to decode Databento DBN file: {source_path.name}"
        ) from exc
    actual_dataset = str(store.dataset)
    actual_schema = str(store.schema) if store.schema is not None else None
    if actual_dataset != dataset:
        raise DatabentoOfflineDecodeError(
            f"Databento DBN dataset mismatch: expected {dataset}, got {actual_dataset}"
        )
    if actual_schema != expected_schema:
        raise DatabentoOfflineDecodeError(
            f"Databento DBN schema mismatch: expected {expected_schema}, got {actual_schema}"
        )
    provenance = {
        "dataset": actual_dataset,
        "schema": actual_schema,
        "source_file": source_path.name,
        "source_sha256": _sha256_file(source_path),
        "source_bytes": source_path.stat().st_size,
    }
    provenance.update(
        _read_adjacent_databento_job_provenance(
            source_path,
            expected_schema=expected_schema,
            dataset=dataset,
        )
    )
    return store, provenance


def _dbn_enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _decode_dbn_bytes(values: Any) -> list[str]:
    return [bytes(value).decode("utf-8").rstrip("\x00") for value in values]


def _definition_frame_from_ndarray(records: Any) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "instrument_id": records["instrument_id"],
            "ts_event": records["ts_event"],
            "ts_recv": records["ts_recv"],
            "raw_symbol": _decode_dbn_bytes(records["raw_symbol"]),
            "instrument_class": _decode_dbn_bytes(records["instrument_class"]),
            "asset": _decode_dbn_bytes(records["asset"]),
            "expiration": records["expiration"],
            "activation": records["activation"],
            "exchange": _decode_dbn_bytes(records["exchange"]),
        }
    )


def _statistics_frame_from_ndarray(records: Any) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "instrument_id": records["instrument_id"],
            "ts_event": records["ts_event"],
            "ts_recv": records["ts_recv"],
            "ts_ref": records["ts_ref"],
            "price": records["price"].astype("float64") / 1_000_000_000.0,
            "quantity": records["quantity"],
            "stat_type": records["stat_type"],
            "stat_flags": records["stat_flags"],
        }
    )


def _low_level_record_mapping(record: Any, expected_schema: str) -> dict[str, Any]:
    if expected_schema == "definition":
        return {
            "instrument_id": record.instrument_id,
            "ts_event": record.pretty_ts_event,
            "ts_recv": record.pretty_ts_recv,
            "raw_symbol": record.raw_symbol,
            "instrument_class": str(record.instrument_class),
            "asset": record.asset,
            "expiration": record.pretty_expiration,
            "activation": record.pretty_activation,
            "exchange": record.exchange,
            "security_update_action": str(record.security_update_action),
        }
    if expected_schema == "statistics":
        return {
            "instrument_id": record.instrument_id,
            "ts_event": record.pretty_ts_event,
            "ts_recv": record.pretty_ts_recv,
            "ts_ref": record.pretty_ts_ref,
            "price": record.pretty_price,
            "quantity": record.quantity,
            "stat_type": _dbn_enum_value(record.stat_type),
            "stat_flags": record.stat_flags,
        }
    if expected_schema == "ohlcv-1d":
        return {
            "instrument_id": record.instrument_id,
            "ts_event": record.pretty_ts_event,
            "open": record.pretty_open,
            "high": record.pretty_high,
            "low": record.pretty_low,
            "close": record.pretty_close,
            "volume": record.volume,
        }
    raise DatabentoOfflineDecodeError(
        f"unsupported offline Databento DBN schema: {expected_schema}"
    )


def _decode_databento_dbn_low_level(
    path: Path | str,
    *,
    expected_schema: str,
    dataset: str,
    selected_stat_types: frozenset[int] | None = None,
    definition_product_code: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    try:
        import databento_dbn as dbn
    except ImportError as exc:
        raise DatabentoOfflineDecodeError(
            "offline DBN decoding requires the Commodity databento_dbn dependency"
        ) from exc

    source_path = Path(path)
    compression = dbn.Compression.ZSTD if source_path.suffix == ".zst" else dbn.Compression.NONE
    decoder = dbn.DBNDecoder(compression=compression)
    rows: list[dict[str, Any]] = []
    metadata_seen = False
    try:
        with source_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(64 * 1024), b""):
                for item in decoder.write_and_decode(chunk):
                    if isinstance(item, dbn.Metadata):
                        actual_dataset = str(item.dataset)
                        actual_schema = str(item.schema) if item.schema is not None else None
                        if actual_dataset != dataset:
                            raise DatabentoOfflineDecodeError(
                                f"Databento DBN dataset mismatch: expected {dataset}, got {actual_dataset}"
                            )
                        if actual_schema != expected_schema:
                            raise DatabentoOfflineDecodeError(
                                f"Databento DBN schema mismatch: expected {expected_schema}, got {actual_schema}"
                            )
                        metadata_seen = True
                        continue
                    if (
                        expected_schema == "statistics"
                        and selected_stat_types is not None
                        and _dbn_enum_value(item.stat_type) not in selected_stat_types
                    ):
                        continue
                    if (
                        expected_schema == "definition"
                        and definition_product_code is not None
                        and (
                            item.asset != definition_product_code
                            or str(item.instrument_class) != "F"
                        )
                    ):
                        continue
                    rows.append(_low_level_record_mapping(item, expected_schema))
    except DatabentoOfflineDecodeError:
        raise
    except Exception as exc:
        raise DatabentoOfflineDecodeError(
            f"failed to decode Databento DBN records: {source_path.name}"
        ) from exc
    if not metadata_seen:
        raise DatabentoOfflineDecodeError(f"Databento DBN metadata missing: {source_path.name}")
    if not rows:
        if selected_stat_types is not None:
            raise DatabentoOfflineDecodeError(
                f"Databento statistics DBN contains no canonical statistics: {source_path.name}"
            )
        raise DatabentoOfflineDecodeError(
            f"Databento DBN file decoded to no records: {source_path.name}"
        )

    provenance = {
        "dataset": dataset,
        "schema": expected_schema,
        "source_file": source_path.name,
        "source_sha256": _sha256_file(source_path),
        "source_bytes": source_path.stat().st_size,
        "decoder": "databento_dbn",
    }
    provenance.update(
        _read_adjacent_databento_job_provenance(
            source_path, expected_schema=expected_schema, dataset=dataset
        )
    )
    return pd.DataFrame.from_records(rows), provenance


def _is_high_level_import_failure(exc: DatabentoOfflineDecodeError) -> bool:
    return isinstance(exc.__cause__, ImportError)


def _read_databento_dbn_symbol_mappings(
    path: Path | str,
    *,
    expected_schema: str,
    dataset: str,
) -> Mapping[str, Any]:
    try:
        store, _ = _open_databento_dbn_store(
            path,
            expected_schema=expected_schema,
            dataset=dataset,
        )
        mappings = store.mappings
    except DatabentoOfflineDecodeError as exc:
        if not _is_high_level_import_failure(exc):
            raise
        try:
            import databento_dbn as dbn
        except ImportError as low_level_exc:
            raise DatabentoOfflineDecodeError(
                "offline DBN symbology requires the Commodity databento_dbn dependency"
            ) from low_level_exc
        source_path = Path(path)
        compression = dbn.Compression.ZSTD if source_path.suffix == ".zst" else dbn.Compression.NONE
        decoder = dbn.DBNDecoder(compression=compression)
        mappings = None
        try:
            with source_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(64 * 1024), b""):
                    for item in decoder.write_and_decode(chunk):
                        if isinstance(item, dbn.Metadata):
                            actual_dataset = str(item.dataset)
                            actual_schema = str(item.schema) if item.schema is not None else None
                            if actual_dataset != dataset or actual_schema != expected_schema:
                                raise DatabentoOfflineDecodeError(
                                    f"Databento DBN metadata mismatch: {source_path.name}"
                                )
                            mappings = item.mappings
                            break
                    if mappings is not None:
                        break
        except DatabentoOfflineDecodeError:
            raise
        except Exception as low_level_exc:
            raise DatabentoOfflineDecodeError(
                f"failed to read Databento DBN symbology: {source_path.name}"
            ) from low_level_exc
    if not isinstance(mappings, Mapping) or not mappings:
        raise DatabentoOfflineDecodeError(
            f"Databento DBN contains no date-bounded symbology mappings: {Path(path).name}"
        )
    return mappings


def decode_databento_dbn_file(
    path: Path | str,
    *,
    expected_schema: str,
    dataset: str = DATABENTO_DATASET,
    definition_product_code: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    try:
        store, provenance = _open_databento_dbn_store(
            path,
            expected_schema=expected_schema,
            dataset=dataset,
        )
    except DatabentoOfflineDecodeError as exc:
        if _is_high_level_import_failure(exc):
            return _decode_databento_dbn_low_level(
                path,
                expected_schema=expected_schema,
                dataset=dataset,
                definition_product_code=definition_product_code,
            )
        raise
    try:
        if expected_schema == "definition" and definition_product_code is not None:
            selected = [
                _definition_frame_from_ndarray(chunk)
                for chunk in store.to_ndarray(count=250_000)
                if len(chunk)
            ]
            if not selected:
                raise DatabentoOfflineDecodeError(
                    f"Databento definition DBN decoded to no records: {Path(path).name}"
                )
            frame = pd.concat(selected, ignore_index=True)
            outright = frame["asset"].eq(definition_product_code) & frame[
                "instrument_class"
            ].eq("F")
            target_ids = frame.loc[outright, "instrument_id"].unique()
            if not len(target_ids):
                raise DatabentoOfflineDecodeError(
                    f"Databento definition DBN contains no {definition_product_code} outright futures: {Path(path).name}"
                )
            frame = frame.loc[frame["instrument_id"].isin(target_ids)].copy()
        else:
            frame = store.to_df(map_symbols=False).reset_index()
    except DatabentoOfflineDecodeError:
        raise
    except Exception as exc:
        raise DatabentoOfflineDecodeError(
            f"failed to decode Databento DBN records: {Path(path).name}"
        ) from exc
    if frame.empty:
        raise DatabentoOfflineDecodeError(
            f"Databento DBN file decoded to no records: {Path(path).name}"
        )
    return frame, provenance


def _decode_databento_canonical_statistics(
    path: Path | str,
    *,
    dataset: str,
    chunk_size: int = 250_000,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    try:
        store, provenance = _open_databento_dbn_store(
            path,
            expected_schema="statistics",
            dataset=dataset,
        )
    except DatabentoOfflineDecodeError as exc:
        if _is_high_level_import_failure(exc):
            return _decode_databento_dbn_low_level(
                path,
                expected_schema="statistics",
                dataset=dataset,
                selected_stat_types=frozenset(
                    {SETTLEMENT_STAT_TYPE, CLEARED_VOLUME_STAT_TYPE}
                ),
            )
        raise
    selected: list[pd.DataFrame] = []
    try:
        for chunk in store.to_ndarray(count=chunk_size):
            keep = np.isin(
                chunk["stat_type"],
                [SETTLEMENT_STAT_TYPE, CLEARED_VOLUME_STAT_TYPE],
            )
            if keep.any():
                selected.append(_statistics_frame_from_ndarray(chunk[keep]))
    except DatabentoOfflineDecodeError:
        raise
    except Exception as exc:
        raise DatabentoOfflineDecodeError(
            f"failed to stream Databento statistics DBN: {Path(path).name}"
        ) from exc
    if not selected:
        raise DatabentoOfflineDecodeError(
            f"Databento statistics DBN contains no canonical statistics: {Path(path).name}"
        )
    return pd.concat(selected, ignore_index=True), provenance


def _exclusive_end(end_trade_date: str, grace_days: int = 0) -> str:
    return (
        pd.Timestamp(end_trade_date) + pd.Timedelta(days=1 + grace_days)
    ).date().isoformat()


def _parent_symbol(product_code: str) -> str:
    return f"{product_code}.FUT"


@dataclass
class DatabentoFuturesClient:
    session: Any | None = None
    api_base: str = DATABENTO_API_BASE
    env_key: str = DATABENTO_ENV_KEY
    timeout_seconds: float = 30.0

    def _api_key(self) -> str:
        value = os.getenv(self.env_key)
        if not value:
            raise MissingCredential(f"Missing environment variable: {self.env_key}")
        return value

    def _handle_response(self, response: Any, operation: str) -> Any:
        status = int(getattr(response, "status_code", 0))
        if status in {200, 206}:
            return response
        if status in {401, 402, 403}:
            raise DatabentoApiError(f"Databento {operation} failed with HTTP {status}")
        raise DatabentoApiError(f"Databento {operation} failed with HTTP {status or 'unknown'}")

    def _metadata_get(self, method: str, params: dict[str, Any]) -> Any:
        session = self.session or requests.Session()
        response = session.get(
            f"{self.api_base.rstrip('/')}/{method}",
            params=params,
            auth=(self._api_key(), ""),
            timeout=self.timeout_seconds,
        )
        return self._handle_response(response, method).json()

    def _timeseries_json(self, params: dict[str, Any]) -> pd.DataFrame:
        session = self.session or requests.Session()
        payload = {
            **params,
            "encoding": "json",
            "compression": "none",
            "pretty_px": "true",
            "pretty_ts": "true",
            "map_symbols": "true",
        }
        response = session.post(
            f"{self.api_base.rstrip('/')}/timeseries.get_range",
            data=payload,
            auth=(self._api_key(), ""),
            timeout=self.timeout_seconds,
        )
        response = self._handle_response(response, "timeseries.get_range")
        text = str(getattr(response, "text", ""))
        if not text.strip():
            return pd.DataFrame()
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            header = row.pop("hd", None)
            if isinstance(header, dict):
                for key, value in header.items():
                    row.setdefault(key, value)
            rows.append(row)
        return pd.DataFrame(rows)

    def list_schemas(self, dataset: str = DATABENTO_DATASET) -> list[str]:
        result = self._metadata_get("metadata.list_schemas", {"dataset": dataset})
        return [str(value) for value in result]

    def get_dataset_range(self, dataset: str = DATABENTO_DATASET) -> dict[str, Any]:
        result = self._metadata_get("metadata.get_dataset_range", {"dataset": dataset})
        if not isinstance(result, dict):
            raise DatabentoApiError("Databento metadata.get_dataset_range returned invalid data")
        return result

    def _request_estimate(
        self,
        method: str,
        dataset: str,
        parent_symbol: str,
        schema: str,
        start_trade_date: str,
        end_trade_date: str,
        grace_days: int = 0,
    ) -> float | int:
        return self._metadata_get(
            method,
            {
                "dataset": dataset,
                "symbols": parent_symbol,
                "schema": schema,
                "stype_in": "parent",
                "start": start_trade_date,
                "end": _exclusive_end(end_trade_date, grace_days=grace_days),
            },
        )

    def probe_history(
        self,
        dataset: str,
        product_code: str,
        start_trade_date: str,
        end_trade_date: str,
    ) -> dict[str, Any]:
        schemas = self.list_schemas(dataset)
        dataset_range = self.get_dataset_range(dataset)
        parent = _parent_symbol(product_code)
        definition_cost = float(
            self._request_estimate(
                "metadata.get_cost",
                dataset,
                parent,
                "definition",
                start_trade_date,
                end_trade_date,
            )
        )
        statistics_cost = float(
            self._request_estimate(
                "metadata.get_cost",
                dataset,
                parent,
                "statistics",
                start_trade_date,
                end_trade_date,
                grace_days=STATISTICS_CAPTURE_GRACE_DAYS,
            )
        )
        definition_count = int(
            self._request_estimate(
                "metadata.get_record_count",
                dataset,
                parent,
                "definition",
                start_trade_date,
                end_trade_date,
            )
        )
        statistics_count = int(
            self._request_estimate(
                "metadata.get_record_count",
                dataset,
                parent,
                "statistics",
                start_trade_date,
                end_trade_date,
                grace_days=STATISTICS_CAPTURE_GRACE_DAYS,
            )
        )
        return {
            "dataset": dataset,
            "product_code": product_code,
            "parent_symbol": parent,
            "schemas": schemas,
            "dataset_range": dataset_range,
            "definition_cost_usd": definition_cost,
            "statistics_cost_usd": statistics_cost,
            "estimated_total_cost_usd": definition_cost + statistics_cost,
            "definition_record_count": definition_count,
            "statistics_record_count": statistics_count,
            "metadata_only": True,
        }

    def fetch_definitions(
        self,
        product_code: str,
        start_trade_date: str,
        end_trade_date: str,
        dataset: str = DATABENTO_DATASET,
    ) -> pd.DataFrame:
        return self._timeseries_json(
            {
                "dataset": dataset,
                "symbols": _parent_symbol(product_code),
                "stype_in": "parent",
                "stype_out": "instrument_id",
                "schema": "definition",
                "start": start_trade_date,
                "end": _exclusive_end(end_trade_date),
            }
        )

    def fetch_statistics(
        self,
        product_code: str,
        start_trade_date: str,
        end_trade_date: str,
        dataset: str = DATABENTO_DATASET,
    ) -> pd.DataFrame:
        return self._timeseries_json(
            {
                "dataset": dataset,
                "symbols": _parent_symbol(product_code),
                "stype_in": "parent",
                "stype_out": "instrument_id",
                "schema": "statistics",
                "start": start_trade_date,
                "end": _exclusive_end(
                    end_trade_date, grace_days=STATISTICS_CAPTURE_GRACE_DAYS
                ),
            }
        )


def _symbol_column(frame: pd.DataFrame) -> str:
    for candidate in ("symbol", "raw_symbol"):
        if candidate in frame.columns:
            return candidate
    raise DataContractViolation("Databento statistics are missing mapped raw symbols")


def databento_contract_id(
    symbols: pd.Series,
    expirations: pd.Series,
) -> pd.Series:
    """Build a stable listed-contract identity across Databento symbol reuse eras."""
    symbol = symbols.astype("string").str.strip()
    expiration = pd.to_datetime(expirations, utc=True, errors="coerce")
    if symbol.isna().any() or symbol.eq("").any() or expiration.isna().any():
        raise DataContractViolation("Databento contract identity contains invalid symbol or expiration")
    return symbol + "@" + expiration.dt.strftime("%Y-%m-%d")


def _databento_metadata_mapping_frame(
    mappings: Mapping[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for raw_symbol, intervals in mappings.items():
        symbol = str(raw_symbol).strip()
        if not symbol or not isinstance(intervals, list):
            raise DataContractViolation("Databento metadata contains invalid symbol mappings")
        for interval in intervals:
            if not isinstance(interval, Mapping):
                raise DataContractViolation("Databento metadata mapping interval must be an object")
            rows.append(
                {
                    "instrument_id": interval.get("symbol"),
                    "raw_symbol": symbol,
                    "mapping_start": interval.get("start_date"),
                    "mapping_end": interval.get("end_date"),
                }
            )
    if not rows:
        raise DataContractViolation("Databento statistics metadata contains no symbol mappings")
    frame = pd.DataFrame.from_records(rows).drop_duplicates()
    frame["instrument_id"] = pd.to_numeric(frame["instrument_id"], errors="coerce")
    frame["mapping_start"] = pd.to_datetime(frame["mapping_start"], utc=True, errors="coerce")
    frame["mapping_end"] = pd.to_datetime(frame["mapping_end"], utc=True, errors="coerce")
    if frame[["instrument_id", "mapping_start", "mapping_end"]].isna().any().any():
        raise DataContractViolation("Databento metadata symbol mappings contain invalid intervals")
    if frame["mapping_start"].ge(frame["mapping_end"]).any():
        raise DataContractViolation("Databento metadata symbol mapping intervals must be non-empty")
    frame["instrument_id"] = frame["instrument_id"].astype("uint64")
    frame = frame.sort_values(
        ["instrument_id", "mapping_start", "mapping_end", "raw_symbol"], kind="stable"
    ).reset_index(drop=True)
    prior_end = frame.groupby("instrument_id", sort=False)["mapping_end"].shift(1)
    if frame["mapping_start"].lt(prior_end).fillna(False).any():
        raise DataContractViolation("Databento metadata contains overlapping instrument mapping intervals")
    return frame


def resolve_databento_metadata_symbols(
    observations: pd.DataFrame,
    mappings: Mapping[str, Any],
) -> pd.DataFrame:
    """Resolve each observation through the DBN date-bounded symbology mapping."""
    required = {"instrument_id", "ts_event"}
    missing = sorted(required - set(observations.columns))
    if missing:
        raise DataContractViolation(f"Databento observations missing mapping fields: {missing}")
    intervals = _databento_metadata_mapping_frame(mappings)
    out = observations.copy()
    out["_row_order"] = range(len(out))
    out["instrument_id"] = pd.to_numeric(out["instrument_id"], errors="coerce")
    out["_mapping_date"] = pd.to_datetime(out["ts_event"], utc=True, errors="coerce").dt.normalize()
    if out[["instrument_id", "_mapping_date"]].isna().any().any():
        raise DataContractViolation("Databento observations contain invalid mapping keys")
    out["instrument_id"] = out["instrument_id"].astype("uint64")
    resolved = pd.merge_asof(
        out.sort_values("_mapping_date", kind="stable"),
        intervals.sort_values("mapping_start", kind="stable"),
        left_on="_mapping_date",
        right_on="mapping_start",
        by="instrument_id",
        direction="backward",
        allow_exact_matches=True,
    )
    valid = resolved["raw_symbol"].notna() & resolved["_mapping_date"].lt(resolved["mapping_end"])
    if not valid.all():
        raise DataContractViolation("Databento observations lack exactly one valid metadata symbol mapping")
    resolved["symbol"] = resolved["raw_symbol"]
    return resolved.sort_values("_row_order", kind="stable").drop(
        columns=["_row_order", "_mapping_date", "raw_symbol", "mapping_start", "mapping_end"]
    )


def _filter_resolved_target_observations(
    definitions: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    product_code: str,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Keep target observations and safely reject publication-order pre-activation rows."""
    target = definitions.loc[
        definitions["asset"].astype(str).eq(product_code)
        & definitions["instrument_class"].astype(str).eq("F")
    ].copy()
    if target.empty:
        raise DataContractViolation("Databento definitions contain no target outright futures")
    definition_time = "ts_recv" if "ts_recv" in target.columns else "ts_event"
    target["raw_symbol"] = target["raw_symbol"].astype("string").str.strip()
    target["_definition_time"] = pd.to_datetime(
        target[definition_time], utc=True, errors="coerce"
    )
    target["_activation"] = pd.to_datetime(target["activation"], utc=True, errors="coerce")
    if target[["raw_symbol", "_definition_time", "_activation"]].isna().any().any():
        raise DataContractViolation("Databento target definitions contain invalid activation timing")

    first = (
        target.sort_values(["raw_symbol", "_definition_time"], kind="stable")
        .drop_duplicates("raw_symbol", keep="first")
        [["raw_symbol", "_definition_time", "_activation"]]
        .rename(columns={"raw_symbol": "symbol"})
    )
    out = observations.copy()
    out["symbol"] = out["symbol"].astype("string").str.strip()
    target_symbols = set(first["symbol"].astype(str))
    target_rows = out.loc[out["symbol"].astype(str).isin(target_symbols)].copy()
    excluded_non_target = len(out) - len(target_rows)
    if target_rows.empty:
        return target_rows, {
            "excluded_non_target_symbol": excluded_non_target,
            "excluded_before_target_activation": 0,
        }

    target_rows["_observation_time"] = pd.to_datetime(
        target_rows["ts_event"], utc=True, errors="coerce"
    )
    target_rows["_trade_date"] = pd.to_datetime(
        target_rows["ts_ref"], utc=True, errors="coerce"
    ).dt.normalize()
    target_rows = target_rows.merge(first, on="symbol", how="left", validate="many_to_one")
    pre_definition = target_rows["_observation_time"].lt(target_rows["_definition_time"])
    safe_pre_activation = (
        pre_definition
        & target_rows["_trade_date"].notna()
        & target_rows["_trade_date"].lt(target_rows["_activation"].dt.normalize())
    )
    unsafe = pre_definition & ~safe_pre_activation
    if unsafe.any():
        raise DataContractViolation(
            "Databento target observations lack time-valid definition identity after activation"
        )
    excluded_pre_activation = int(safe_pre_activation.sum())
    helper = ["_observation_time", "_trade_date", "_definition_time", "_activation"]
    kept = target_rows.loc[~safe_pre_activation].drop(columns=helper)
    return kept, {
        "excluded_non_target_symbol": excluded_non_target,
        "excluded_before_target_activation": excluded_pre_activation,
    }


def map_databento_resolved_symbols_to_target_definitions(
    definitions: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    product_code: str,
) -> pd.DataFrame:
    """Join metadata-resolved symbols to time-valid target outright definitions."""
    required_definitions = {
        "raw_symbol",
        "instrument_class",
        "asset",
        "expiration",
        "activation",
        "exchange",
    }
    missing = sorted(required_definitions - set(definitions.columns))
    if missing:
        raise DataContractViolation(f"Databento definitions missing target identity fields: {missing}")
    if "symbol" not in observations.columns or "ts_event" not in observations.columns:
        raise DataContractViolation("Databento resolved observations require symbol and ts_event")

    target = definitions.loc[
        definitions["asset"].astype(str).eq(product_code)
        & definitions["instrument_class"].astype(str).eq("F")
    ].copy()
    if target.empty:
        raise DataContractViolation("Databento definitions contain no target outright futures")
    definition_time = "ts_recv" if "ts_recv" in target.columns else "ts_event"
    target["raw_symbol"] = target["raw_symbol"].astype("string").str.strip()
    target["_definition_time"] = pd.to_datetime(target[definition_time], utc=True, errors="coerce")
    if target[["raw_symbol", "_definition_time"]].isna().any().any() or target["raw_symbol"].eq("").any():
        raise DataContractViolation("Databento target definitions contain invalid symbol timing")
    payload = ["expiration", "activation", "exchange", "asset", "instrument_class"]
    signature = target[["raw_symbol", "_definition_time", *payload]].astype("string").fillna("<NA>")
    target["_definition_signature"] = signature[payload].agg("\x1f".join, axis=1)
    ambiguous = target.groupby(["raw_symbol", "_definition_time"])["_definition_signature"].nunique().gt(1)
    if ambiguous.any():
        raise DataContractViolation("Databento target definitions contain ambiguous symbol identity")
    target = target.drop_duplicates(["raw_symbol", "_definition_time"], keep="last")
    target = target[["raw_symbol", "_definition_time", "_definition_signature", *payload]].copy()

    out = observations.copy()
    out["_row_order"] = range(len(out))
    out["symbol"] = out["symbol"].astype("string").str.strip()
    out["_observation_time"] = pd.to_datetime(out["ts_event"], utc=True, errors="coerce")
    if out[["symbol", "_observation_time"]].isna().any().any() or out["symbol"].eq("").any():
        raise DataContractViolation("Databento resolved observations contain invalid symbol timing")
    target_symbols = set(target["raw_symbol"].astype(str))
    out = out.loc[out["symbol"].astype(str).isin(target_symbols)].copy()
    if out.empty:
        return observations.iloc[0:0].copy()
    target = target.rename(
        columns={field: f"_mapped_{field}" for field in payload}
    )
    mapped = pd.merge_asof(
        out.sort_values("_observation_time", kind="stable"),
        target.sort_values("_definition_time", kind="stable"),
        left_on="_observation_time",
        right_on="_definition_time",
        left_by="symbol",
        right_by="raw_symbol",
        direction="backward",
        allow_exact_matches=True,
    )
    if mapped["_mapped_expiration"].isna().any():
        raise DataContractViolation("Databento target observations lack time-valid definition identity")
    for field in payload:
        mapped[f"definition_{field}"] = mapped[f"_mapped_{field}"]
    helper = [
        "_row_order",
        "_observation_time",
        "_definition_time",
        "_definition_signature",
        "raw_symbol",
        *[f"_mapped_{field}" for field in payload],
    ]
    return mapped.sort_values("_row_order", kind="stable").drop(columns=helper)


def _select_databento_final_settlements(
    stats: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    settlements = stats[stats["stat_type"].eq(SETTLEMENT_STAT_TYPE)].copy()
    if settlements.empty:
        raise DataContractViolation("Databento returned no settlement statistics")
    boundary = pd.Timestamp(LEGACY_SETTLEMENT_FLAG_NORMALIZATION_END)
    legacy = settlements.loc[settlements["ts_ref"].lt(boundary)].copy()
    modern = settlements.loc[settlements["ts_ref"].ge(boundary)].copy()

    legacy_groups = legacy[["_symbol", "ts_ref"]].drop_duplicates().shape[0]
    if not legacy.empty:
        legacy = legacy.loc[
            ~legacy["stat_flags"].isin(LEGACY_PRELIMINARY_SETTLEMENT_FLAGS)
        ].copy()
        legacy = (
            legacy.sort_values(["_symbol", "ts_ref", "ts_event", "_available_at"])
            .drop_duplicates(["_symbol", "ts_ref"], keep="last")
            .copy()
        )

    if not modern.empty:
        modern = modern.loc[
            modern["stat_flags"].map(
                lambda value: bool(int(value) & FINAL_SETTLEMENT_FLAG)
                and not bool(int(value) & INTRADAY_SETTLEMENT_FLAG)
            )
        ].copy()
        modern = (
            modern.sort_values(["_symbol", "ts_ref", "ts_event", "_available_at"])
            .drop_duplicates(["_symbol", "ts_ref"], keep="last")
            .copy()
        )

    selected = pd.concat([legacy, modern], ignore_index=True)
    if selected.empty:
        raise DataContractViolation("Databento returned no final settlement statistics")
    diagnostics = {
        "legacy_normalization_boundary": LEGACY_SETTLEMENT_FLAG_NORMALIZATION_END,
        "legacy_selection": "latest_published_non_known_preliminary",
        "legacy_groups": legacy_groups,
        "legacy_selected_groups": len(legacy),
        "legacy_dropped_known_preliminary_groups": legacy_groups - len(legacy),
        "modern_selection": "final_bit_set_and_intraday_bit_unset",
        "modern_selected_groups": len(modern),
    }
    return selected, diagnostics


def normalize_databento_contract_history(
    definitions: pd.DataFrame,
    statistics: pd.DataFrame,
    retrieved_at: str,
    product_code: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    source_bytes = (
        definitions.to_csv(index=False) + "\n" + statistics.to_csv(index=False)
    ).encode("utf-8")
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()

    required_definitions = {
        "raw_symbol",
        "instrument_class",
        "asset",
        "expiration",
        "exchange",
    }
    missing_definitions = sorted(required_definitions - set(definitions.columns))
    if missing_definitions:
        raise DataContractViolation(
            f"Databento definitions missing fields: {missing_definitions}"
        )
    if statistics.empty:
        raise DataContractViolation("Databento statistics are empty")
    required_statistics = {"stat_type", "stat_flags", "ts_ref", "ts_event", "price"}
    missing_statistics = sorted(required_statistics - set(statistics.columns))
    if missing_statistics:
        raise DataContractViolation(
            f"Databento statistics missing fields: {missing_statistics}"
        )

    definitions = definitions.copy()
    definitions = definitions[definitions["asset"].astype(str) == product_code]
    definitions = definitions[definitions["instrument_class"].astype(str) == "F"].copy()
    if definitions.empty:
        raise DataContractViolation("Databento definitions contain no outright futures")
    definitions["raw_symbol"] = definitions["raw_symbol"].astype("string").str.strip()
    definitions["expiration"] = pd.to_datetime(definitions["expiration"], utc=True, errors="coerce")
    if definitions["raw_symbol"].isna().any() or definitions["raw_symbol"].eq("").any():
        raise DataContractViolation("Databento definitions contain invalid raw_symbol")
    if definitions["expiration"].isna().any():
        raise DataContractViolation("Databento definitions contain invalid expiration")

    stats = statistics.copy()
    symbol_col = _symbol_column(stats)
    stats["_symbol"] = stats[symbol_col].astype(str)
    stats["stat_type"] = pd.to_numeric(stats["stat_type"], errors="coerce")
    stats["stat_flags"] = pd.to_numeric(stats["stat_flags"], errors="coerce").fillna(0).astype("int64")
    stats["ts_ref"] = pd.to_datetime(stats["ts_ref"], utc=True, errors="coerce")
    stats["ts_event"] = pd.to_datetime(stats["ts_event"], utc=True, errors="coerce")
    if "ts_recv" in stats.columns:
        received = pd.to_datetime(stats["ts_recv"], utc=True, errors="coerce")
        stats["_available_at"] = received.fillna(stats["ts_event"])
    else:
        stats["_available_at"] = stats["ts_event"]

    temporal_fields = {"definition_expiration", "definition_exchange"}
    temporal_present = temporal_fields.intersection(stats.columns)
    if temporal_present and temporal_present != temporal_fields:
        raise DataContractViolation("Databento statistics contain incomplete temporal definition identity")
    has_temporal_definition = temporal_present == temporal_fields
    if has_temporal_definition:
        stats["definition_expiration"] = pd.to_datetime(
            stats["definition_expiration"], utc=True, errors="coerce"
        )
        if stats["definition_expiration"].isna().any():
            raise DataContractViolation("Databento statistics contain invalid temporal expiration")
        if "definition_asset" in stats.columns:
            stats = stats[stats["definition_asset"].astype(str).eq(product_code)].copy()
        if "definition_instrument_class" in stats.columns:
            stats = stats[
                stats["definition_instrument_class"].astype(str).eq("F")
            ].copy()

    settlements, settlement_selection = _select_databento_final_settlements(stats)
    if settlements[["ts_ref", "ts_event", "price"]].isna().any().any():
        raise DataContractViolation("Databento final settlement statistics contain invalid values")
    settlements["price"] = pd.to_numeric(settlements["price"], errors="coerce")
    if settlements["price"].isna().any():
        raise DataContractViolation("Databento final settlement statistics contain invalid prices")
    settlements = (
        settlements.sort_values("ts_event")
        .drop_duplicates(["_symbol", "ts_ref"], keep="last")
        .copy()
    )
    settlement_columns = ["_symbol", "ts_ref", "ts_event", "_available_at", "price"]
    if has_temporal_definition:
        settlement_columns.extend(["definition_expiration", "definition_exchange"])
    settlements = settlements[settlement_columns].copy()

    volumes = stats[stats["stat_type"].eq(CLEARED_VOLUME_STAT_TYPE)].copy()
    if not volumes.empty and "quantity" in volumes.columns:
        volumes["quantity"] = pd.to_numeric(volumes["quantity"], errors="coerce")
        volumes = volumes[
            volumes["quantity"].notna()
            & volumes["quantity"].ge(0)
            & volumes["quantity"].lt(2**63 - 1)
        ].copy()
        volumes = (
            volumes.sort_values("ts_event")
            .drop_duplicates(["_symbol", "ts_ref"], keep="last")
            [["_symbol", "ts_ref", "quantity", "_available_at"]]
            .rename(columns={"_available_at": "_volume_available_at"})
        )
        settlements = settlements.merge(
            volumes,
            on=["_symbol", "ts_ref"],
            how="left",
        )
        settlements["_available_at"] = settlements[
            ["_available_at", "_volume_available_at"]
        ].max(axis=1)

    if has_temporal_definition:
        out = settlements.rename(
            columns={
                "definition_expiration": "expiration",
                "definition_exchange": "exchange",
            }
        ).copy()
        out["raw_symbol"] = out["_symbol"].astype("string").str.strip()
        if out[["expiration", "exchange"]].isna().any().any():
            raise DataContractViolation("Databento temporal definition identity is incomplete")
    else:
        definition_identity = definitions[
            ["raw_symbol", "expiration", "exchange"]
        ].drop_duplicates()
        reused = definition_identity.groupby("raw_symbol").agg(
            expirations=("expiration", "nunique"),
            exchanges=("exchange", "nunique"),
        )
        if reused[["expirations", "exchanges"]].gt(1).any(axis=1).any():
            raise DataContractViolation(
                "Databento reused raw_symbol requires temporal definition identity"
            )
        definition_identity = definition_identity.drop_duplicates("raw_symbol", keep="last")
        out = settlements.merge(
            definition_identity,
            left_on="_symbol",
            right_on="raw_symbol",
            how="inner",
            validate="many_to_one",
        )
    if out.empty:
        raise DataContractViolation("Databento final settlements do not match outright definitions")
    canonical = pd.DataFrame(
        {
            "trade_date": out["ts_ref"].dt.normalize(),
            "contract_id": databento_contract_id(out["raw_symbol"], out["expiration"]),
            "expiration": out["expiration"],
            "settle": out["price"],
            "available_at": out["_available_at"],
        }
    )
    if "quantity" in out.columns:
        canonical["volume"] = out["quantity"].values

    exchanges = {str(value) for value in definitions["exchange"].dropna()}
    if len(exchanges) != 1:
        raise DataContractViolation(
            f"Databento definitions must identify exactly one exchange: {sorted(exchanges)}"
        )
    exchange = next(iter(exchanges))
    canonical_exchange = {"XNYM": "NYMEX"}.get(exchange, exchange)
    metadata = {
        "source_id": "databento_glbx_mdp3_statistics_v0",
        "source_sha256": source_sha256,
        "retrieved_at": retrieved_at,
        "exchange": canonical_exchange,
        "product_code": product_code,
        "session_timezone": data_config()["sources"]["databento_henry_hub"]["session_timezone"],
        "calendar": "CME_NYMEX",
        "price_semantics": "cme_final_settlement_from_databento_statistics",
        "settlement_availability_semantics": "statistics_ts_recv_else_ts_event",
        "settlement_selection": settlement_selection,
        "volume_semantics": "cme_cleared_volume_from_databento_statistics",
    }
    return canonical, metadata


def map_databento_instrument_symbols(
    definitions: pd.DataFrame,
    observations: pd.DataFrame,
) -> pd.DataFrame:
    required_definitions = {"instrument_id", "raw_symbol"}
    missing_definitions = sorted(required_definitions - set(definitions.columns))
    if missing_definitions:
        raise DataContractViolation(
            f"Databento offline definitions missing identity fields: {missing_definitions}"
        )
    if "instrument_id" not in observations.columns:
        raise DataContractViolation(
            "Databento offline observations are missing instrument_id"
        )
    definition_time = "ts_recv" if "ts_recv" in definitions.columns else "ts_event"
    observation_time = "ts_recv" if "ts_recv" in observations.columns else "ts_event"
    if definition_time not in definitions.columns or observation_time not in observations.columns:
        raise DataContractViolation(
            "Databento offline identity mapping requires definition/observation timestamps"
        )

    payload_fields = [
        column
        for column in ("expiration", "activation", "exchange", "asset", "instrument_class")
        if column in definitions.columns
    ]
    identity = definitions[
        ["instrument_id", "raw_symbol", definition_time, *payload_fields]
    ].copy()
    identity["instrument_id"] = pd.to_numeric(identity["instrument_id"], errors="coerce")
    identity["_definition_time"] = pd.to_datetime(
        identity[definition_time], utc=True, errors="coerce"
    )
    identity["_mapped_symbol"] = identity["raw_symbol"].astype("string").str.strip()
    identity = identity.dropna(
        subset=["instrument_id", "_definition_time", "_mapped_symbol"]
    )
    identity = identity.loc[identity["_mapped_symbol"].ne("")].copy()
    if identity.empty:
        raise DataContractViolation(
            "Databento offline definitions contain no usable point-in-time symbols"
        )
    identity["instrument_id"] = identity["instrument_id"].astype("uint64")
    signature_fields = ["_mapped_symbol", *payload_fields]
    identity["_identity_signature"] = (
        identity[signature_fields].astype("string").fillna("<NA>").agg("\x1f".join, axis=1)
    )
    ambiguous = (
        identity.groupby(["instrument_id", "_definition_time"])["_identity_signature"]
        .nunique()
        .gt(1)
    )
    if ambiguous.any():
        raise DataContractViolation(
            "Databento offline definitions contain ambiguous point-in-time identity"
        )
    identity = identity.drop_duplicates(
        ["instrument_id", "_definition_time"], keep="last"
    )
    payload_columns = {field: f"_mapped_{field}" for field in payload_fields}
    identity = identity.rename(columns=payload_columns)
    identity_columns = [
        "instrument_id",
        "_definition_time",
        "_mapped_symbol",
        *payload_columns.values(),
    ]
    identity = identity[identity_columns]

    mapped = observations.copy()
    mapped["_row_order"] = range(len(mapped))
    mapped["instrument_id"] = pd.to_numeric(mapped["instrument_id"], errors="coerce")
    mapped["_observation_time"] = pd.to_datetime(
        mapped[observation_time], utc=True, errors="coerce"
    )
    if mapped[["instrument_id", "_observation_time"]].isna().any().any():
        raise DataContractViolation(
            "Databento offline observations contain invalid identity keys or timestamps"
        )
    mapped["instrument_id"] = mapped["instrument_id"].astype("uint64")
    mapped = pd.merge_asof(
        mapped.sort_values("_observation_time"),
        identity.sort_values("_definition_time"),
        left_on="_observation_time",
        right_on="_definition_time",
        by="instrument_id",
        direction="backward",
        allow_exact_matches=True,
    )
    if mapped["_mapped_symbol"].isna().any():
        raise DataContractViolation(
            "Databento offline observations contain unmapped point-in-time instrument_id values"
        )
    mapped["symbol"] = mapped["_mapped_symbol"]
    for field, mapped_column in payload_columns.items():
        mapped[f"definition_{field}"] = mapped[mapped_column]
    helper_columns = [
        "_row_order",
        "_observation_time",
        "_definition_time",
        "_mapped_symbol",
        *payload_columns.values(),
    ]
    return mapped.sort_values("_row_order").drop(columns=helper_columns)


def _map_offline_statistics_symbols(
    definitions: pd.DataFrame,
    statistics: pd.DataFrame,
) -> pd.DataFrame:
    return map_databento_instrument_symbols(definitions, statistics)


def _drop_observations_before_first_target_definition(
    definitions: pd.DataFrame,
    observations: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    definition_time = "ts_recv" if "ts_recv" in definitions.columns else "ts_event"
    observation_time = "ts_recv" if "ts_recv" in observations.columns else "ts_event"
    first = definitions[["instrument_id", definition_time]].copy()
    first["instrument_id"] = pd.to_numeric(first["instrument_id"], errors="coerce")
    first["_first_target_definition"] = pd.to_datetime(
        first[definition_time], utc=True, errors="coerce"
    )
    first = first.dropna(subset=["instrument_id", "_first_target_definition"])
    first = first.groupby("instrument_id", as_index=False)["_first_target_definition"].min()

    out = observations.copy()
    out["instrument_id"] = pd.to_numeric(out["instrument_id"], errors="coerce")
    out["_observation_time"] = pd.to_datetime(out[observation_time], utc=True, errors="coerce")
    if out[["instrument_id", "_observation_time"]].isna().any().any():
        raise DataContractViolation("Databento archive observations contain invalid identity timing")
    out = out.merge(first, on="instrument_id", how="left", validate="many_to_one")
    if out["_first_target_definition"].isna().any():
        raise DataContractViolation("Databento archive observations lack target definition history")
    keep = out["_observation_time"].ge(out["_first_target_definition"])
    dropped = int((~keep).sum())
    return out.loc[keep, observations.columns].copy(), dropped


def _filter_mapped_observations_to_contract_lifetime(
    observations: pd.DataFrame,
) -> tuple[pd.DataFrame, int, int]:
    required = {"definition_activation", "definition_expiration", "ts_ref"}
    missing = sorted(required - set(observations.columns))
    if missing:
        raise DataContractViolation(f"Databento mapped observations missing lifetime fields: {missing}")
    activation = pd.to_datetime(observations["definition_activation"], utc=True, errors="coerce")
    expiration = pd.to_datetime(observations["definition_expiration"], utc=True, errors="coerce")
    if activation.isna().any() or expiration.isna().any():
        raise DataContractViolation("Databento mapped observations contain invalid contract lifetime")
    trade_date = pd.to_datetime(observations["ts_ref"], utc=True, errors="coerce").dt.normalize()
    valid_reference = trade_date.notna()
    dropped_invalid_reference = int((~valid_reference).sum())
    keep = (
        valid_reference
        & trade_date.ge(activation.dt.normalize())
        & trade_date.le(expiration.dt.normalize())
    )
    dropped_outside_lifetime = int((valid_reference & ~keep).sum())
    return (
        observations.loc[keep].copy(),
        dropped_invalid_reference,
        dropped_outside_lifetime,
    )


def canonicalize_databento_dbn_history(
    definition_path: Path | str,
    statistics_path: Path | str,
    *,
    schema: dict[str, Any],
    product_code: str,
    retrieved_at: str,
    dataset: str = DATABENTO_DATASET,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    definitions, definition_provenance = decode_databento_dbn_file(
        definition_path,
        expected_schema="definition",
        dataset=dataset,
        definition_product_code=product_code,
    )
    statistics, statistics_provenance = _decode_databento_canonical_statistics(
        statistics_path,
        dataset=dataset,
    )
    target_ids = definitions["instrument_id"].dropna().unique()
    statistics = statistics.loc[statistics["instrument_id"].isin(target_ids)].copy()
    if statistics.empty:
        raise DatabentoOfflineDecodeError(
            f"Databento statistics DBN has no observations for mapped outright identities: {Path(statistics_path).name}"
        )
    statistics = _map_offline_statistics_symbols(definitions, statistics)

    frame, metadata = normalize_databento_contract_history(
        definitions,
        statistics,
        retrieved_at,
        product_code,
    )
    artifacts = [definition_provenance, statistics_provenance]
    bundle_bytes = json.dumps(
        [
            {
                "schema": item["schema"],
                "source_file": item["source_file"],
                "source_sha256": item["source_sha256"],
                **{
                    key: item[key]
                    for key in ("provider_job_id", "provider_metadata_sha256")
                    if key in item
                },
            }
            for item in artifacts
        ],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    metadata.update(
        {
            "source_id": "databento_glbx_mdp3_offline_dbn_v1",
            "source_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
            "source_artifacts": artifacts,
            "offline_decode": True,
            "canonical_evidence": False,
            "licensing_rights_verified": False,
        }
    )
    frame = validate_contract_history(frame, schema)
    validate_contract_metadata(
        metadata,
        schema,
        data_config()["sources"]["databento_henry_hub"],
    )
    return frame, metadata


def load_databento_definition_archive(
    definition_paths: list[Path | str],
    *,
    product_code: str,
    dataset: str = DATABENTO_DATASET,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Decode one global target-definition authority for partitioned reconstruction."""
    if not definition_paths:
        raise ValueError("Databento definition archive requires source files")
    frames: list[pd.DataFrame] = []
    artifacts: list[dict[str, Any]] = []
    for path in definition_paths:
        definitions, provenance = decode_databento_dbn_file(
            path,
            expected_schema="definition",
            dataset=dataset,
            definition_product_code=product_code,
        )
        frames.append(definitions)
        artifacts.append(provenance)
    global_definitions = pd.concat(frames, ignore_index=True)
    target = global_definitions.loc[
        global_definitions["asset"].astype(str).eq(product_code)
        & global_definitions["instrument_class"].astype(str).eq("F")
    ]
    if target.empty:
        raise DatabentoOfflineDecodeError(
            f"Databento definition archive contains no {product_code} outright identities"
        )
    authority_payload = {
        "dataset": dataset,
        "product_code": product_code,
        "reconstruction_version": DATABENTO_ARCHIVE_RECONSTRUCTION_VERSION,
        "artifacts": [
            {
                "source_file": item["source_file"],
                "source_sha256": item["source_sha256"],
            }
            for item in artifacts
        ],
    }
    authority_sha256 = hashlib.sha256(
        json.dumps(
            authority_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return global_definitions, {
        **authority_payload,
        "definition_artifacts": artifacts,
        "definition_authority_sha256": authority_sha256,
    }


def canonicalize_databento_dbn_partition(
    global_definitions: pd.DataFrame,
    statistics_path: Path | str,
    *,
    schema: dict[str, Any],
    product_code: str,
    retrieved_at: str,
    definition_authority_sha256: str,
    dataset: str = DATABENTO_DATASET,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Canonicalize and validate one independently resumable statistics partition."""
    statistics, provenance = _decode_databento_canonical_statistics(
        statistics_path,
        dataset=dataset,
    )
    candidate_statistics_rows = len(statistics)
    mappings = _read_databento_dbn_symbol_mappings(
        statistics_path,
        expected_schema="statistics",
        dataset=dataset,
    )
    resolved = resolve_databento_metadata_symbols(statistics, mappings)
    target_observations, target_filter = _filter_resolved_target_observations(
        global_definitions,
        resolved,
        product_code=product_code,
    )
    statistics = map_databento_resolved_symbols_to_target_definitions(
        global_definitions,
        target_observations,
        product_code=product_code,
    )
    if statistics.empty:
        raise DatabentoOfflineDecodeError(
            f"Databento statistics partition has no resolved target observations: {Path(statistics_path).name}"
        )
    (
        statistics,
        dropped_invalid_reference,
        dropped_outside_lifetime,
    ) = _filter_mapped_observations_to_contract_lifetime(statistics)
    if statistics.empty:
        raise DatabentoOfflineDecodeError(
            f"Databento statistics partition has no active-lifetime target observations: {Path(statistics_path).name}"
        )
    frame, metadata = normalize_databento_contract_history(
        global_definitions,
        statistics,
        retrieved_at,
        product_code,
    )
    frame = validate_contract_history(frame, schema)
    accounting = {
        "candidate_statistics_rows": candidate_statistics_rows,
        "resolved_statistics_rows": len(resolved),
        "excluded_non_target_symbol": target_filter["excluded_non_target_symbol"],
        "excluded_before_target_activation": target_filter[
            "excluded_before_target_activation"
        ],
        "dropped_invalid_reference_timestamp": dropped_invalid_reference,
        "dropped_outside_contract_lifetime": dropped_outside_lifetime,
        "canonical_contract_days": len(frame),
        "positive_volume_contract_days": (
            int(frame["volume"].gt(0).sum()) if "volume" in frame.columns else 0
        ),
        "volume_observed_contract_days": (
            int(frame["volume"].notna().sum()) if "volume" in frame.columns else 0
        ),
        "missing_volume_contract_days": (
            int(frame["volume"].isna().sum()) if "volume" in frame.columns else len(frame)
        ),
    }
    partition_payload = {
        "definition_authority_sha256": definition_authority_sha256,
        "statistics_source_sha256": provenance["source_sha256"],
        "reconstruction_version": DATABENTO_ARCHIVE_RECONSTRUCTION_VERSION,
    }
    metadata.update(
        {
            "source_id": "databento_glbx_mdp3_offline_dbn_v1",
            "source_sha256": hashlib.sha256(
                json.dumps(
                    partition_payload, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest(),
            "statistics_artifact": provenance,
            "definition_authority_sha256": definition_authority_sha256,
            "reconstruction_version": DATABENTO_ARCHIVE_RECONSTRUCTION_VERSION,
            "identity_resolution_semantics": (
                "statistics_metadata_date_bounded_symbology_then_time_valid_target_definition"
            ),
            "partition_accounting": accounting,
            "offline_decode": True,
            "canonical_evidence": False,
            "licensing_rights_verified": False,
        }
    )
    validate_contract_metadata(
        metadata,
        schema,
        data_config()["sources"]["databento_henry_hub"],
    )
    return frame, metadata


def assemble_databento_dbn_partitions(
    partitions: list[pd.DataFrame],
    *,
    schema: dict[str, Any],
) -> pd.DataFrame:
    """Assemble independently validated partitions and enforce global invariants."""
    if not partitions:
        raise ValueError("Databento archive assembly requires partitions")
    canonical = pd.concat(partitions, ignore_index=True)
    if canonical.duplicated(["trade_date", "contract_id"]).any():
        raise DataContractViolation(
            "Databento archive partitions overlap on canonical trade_date/contract_id"
        )
    canonical = canonical.sort_values(
        ["trade_date", "expiration", "contract_id"], kind="stable"
    ).reset_index(drop=True)
    return validate_contract_history(canonical, schema)


def canonicalize_databento_dbn_archive(
    definition_paths: list[Path | str],
    statistics_paths: list[Path | str],
    *,
    schema: dict[str, Any],
    product_code: str,
    retrieved_at: str,
    dataset: str = DATABENTO_DATASET,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Canonicalize a split DBN archive using one global time-valid definition history."""
    if not definition_paths or not statistics_paths:
        raise ValueError("Databento offline archive requires definition and statistics files")

    definition_frames: list[pd.DataFrame] = []
    definition_artifacts: list[dict[str, Any]] = []
    for path in definition_paths:
        definitions, provenance = decode_databento_dbn_file(
            path,
            expected_schema="definition",
            dataset=dataset,
            definition_product_code=product_code,
        )
        definition_frames.append(definitions)
        definition_artifacts.append(provenance)
    global_definitions = pd.concat(definition_frames, ignore_index=True)
    target_definitions = global_definitions.loc[
        global_definitions["asset"].astype(str).eq(product_code)
        & global_definitions["instrument_class"].astype(str).eq("F")
    ]
    if target_definitions.empty:
        raise DatabentoOfflineDecodeError(
            f"Databento definition archive contains no {product_code} outright identities"
        )

    frames: list[pd.DataFrame] = []
    statistics_artifacts: list[dict[str, Any]] = []
    selection_by_source: list[dict[str, Any]] = []
    identity_window_by_source: list[dict[str, Any]] = []
    base_metadata: dict[str, Any] | None = None
    for path in statistics_paths:
        statistics, provenance = _decode_databento_canonical_statistics(
            path,
            dataset=dataset,
        )
        mappings = _read_databento_dbn_symbol_mappings(
            path,
            expected_schema="statistics",
            dataset=dataset,
        )
        resolved = resolve_databento_metadata_symbols(statistics, mappings)
        resolved_rows = len(resolved)
        target_observations, target_filter = _filter_resolved_target_observations(
            global_definitions,
            resolved,
            product_code=product_code,
        )
        statistics = map_databento_resolved_symbols_to_target_definitions(
            global_definitions,
            target_observations,
            product_code=product_code,
        )
        if statistics.empty:
            raise DatabentoOfflineDecodeError(
                f"Databento statistics archive file has no resolved target observations: {Path(path).name}"
            )
        (
            statistics,
            dropped_invalid_reference,
            dropped_outside_lifetime,
        ) = _filter_mapped_observations_to_contract_lifetime(statistics)
        if statistics.empty:
            raise DatabentoOfflineDecodeError(
                f"Databento statistics archive file has no active-lifetime target observations: {Path(path).name}"
            )
        identity_window_by_source.append(
            {
                "source_file": provenance["source_file"],
                "metadata_mapping_intervals": sum(len(items) for items in mappings.values()),
                "resolved_statistics_rows": resolved_rows,
                "excluded_non_target_symbol": target_filter["excluded_non_target_symbol"],
                "excluded_before_target_activation": target_filter[
                    "excluded_before_target_activation"
                ],
                "dropped_invalid_reference_timestamp": dropped_invalid_reference,
                "dropped_outside_contract_lifetime": dropped_outside_lifetime,
            }
        )
        frame, metadata = normalize_databento_contract_history(
            global_definitions,
            statistics,
            retrieved_at,
            product_code,
        )
        frames.append(frame)
        statistics_artifacts.append(provenance)
        selection_by_source.append(
            {
                "source_file": provenance["source_file"],
                **metadata["settlement_selection"],
            }
        )
        if base_metadata is None:
            base_metadata = metadata

    canonical = pd.concat(frames, ignore_index=True)
    canonical = canonical.sort_values(
        ["trade_date", "contract_id", "available_at"], kind="stable"
    ).drop_duplicates(["trade_date", "contract_id"], keep="last")
    canonical = validate_contract_history(canonical, schema)

    artifacts = [*definition_artifacts, *statistics_artifacts]
    bundle_bytes = json.dumps(
        [
            {
                "schema": item["schema"],
                "source_file": item["source_file"],
                "source_sha256": item["source_sha256"],
                **{
                    key: item[key]
                    for key in ("provider_job_id", "provider_metadata_sha256")
                    if key in item
                },
            }
            for item in artifacts
        ],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    metadata = dict(base_metadata or {})
    metadata.update(
        {
            "source_id": "databento_glbx_mdp3_offline_dbn_v1",
            "source_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
            "source_artifacts": artifacts,
            "offline_decode": True,
            "canonical_evidence": False,
            "licensing_rights_verified": False,
            "archive_definition_files": len(definition_artifacts),
            "archive_statistics_files": len(statistics_artifacts),
            "identity_resolution_semantics": (
                "statistics_metadata_date_bounded_symbology_then_time_valid_target_definition"
            ),
            "settlement_selection_by_source": selection_by_source,
            "identity_window_filter_by_source": identity_window_by_source,
        }
    )
    validate_contract_metadata(
        metadata,
        schema,
        data_config()["sources"]["databento_henry_hub"],
    )
    return canonical, metadata


def _fetch_bounded_databento_source(
    client: DatabentoFuturesClient,
    product_code: str,
    start_trade_date: str,
    end_trade_date: str,
    dataset: str,
    max_cost_usd: float,
    max_records: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if max_cost_usd <= 0:
        raise ValueError("max_cost_usd must be positive")
    if max_records < 1:
        raise ValueError("max_records must be positive")
    probe = client.probe_history(dataset, product_code, start_trade_date, end_trade_date)
    required = {"definition", "statistics"}
    missing = sorted(required - set(probe["schemas"]))
    if missing:
        raise DataContractViolation(f"Databento dataset is missing required schemas: {missing}")
    estimated_cost = float(probe["estimated_total_cost_usd"])
    if estimated_cost > max_cost_usd:
        raise DataContractViolation(
            f"Databento estimated request cost ${estimated_cost:.4f} exceeds bounded cap ${max_cost_usd:.4f}"
        )
    estimated_records = int(probe["definition_record_count"]) + int(
        probe["statistics_record_count"]
    )
    if estimated_records > max_records:
        raise DataContractViolation(
            f"Databento estimated record count {estimated_records} exceeds bounded cap {max_records}"
        )
    definitions = client.fetch_definitions(
        product_code, start_trade_date, end_trade_date, dataset=dataset
    )
    statistics = client.fetch_statistics(
        product_code, start_trade_date, end_trade_date, dataset=dataset
    )
    return definitions, statistics, probe


def _canonicalize_databento_source(
    definitions: pd.DataFrame,
    statistics: pd.DataFrame,
    probe: dict[str, Any],
    schema: dict[str, Any],
    product_code: str,
    start_trade_date: str,
    end_trade_date: str,
    retrieved_at: str,
    dataset: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame, metadata = normalize_databento_contract_history(
        definitions, statistics, retrieved_at, product_code
    )
    trade_start = pd.to_datetime(start_trade_date, utc=True)
    trade_end = pd.to_datetime(end_trade_date, utc=True) + pd.Timedelta(days=1)
    frame = frame[(frame["trade_date"] >= trade_start) & (frame["trade_date"] < trade_end)]
    if frame.empty:
        raise DataContractViolation("Databento returned no final settlements in trade-date range")
    frame = validate_contract_history(frame, schema)
    metadata.update(
        {
            "dataset": dataset,
            "metadata_probe": probe,
            "estimated_request_cost_usd": float(probe["estimated_total_cost_usd"]),
            "source_contract_count": int(frame["contract_id"].nunique()),
            "statistics_capture_grace_days": STATISTICS_CAPTURE_GRACE_DAYS,
        }
    )
    validate_contract_metadata(
        metadata,
        schema,
        data_config()["sources"]["databento_henry_hub"],
    )
    return frame, metadata


def fetch_databento_canonical_history(
    client: DatabentoFuturesClient,
    schema: dict[str, Any],
    product_code: str,
    start_trade_date: str,
    end_trade_date: str,
    retrieved_at: str,
    dataset: str = DATABENTO_DATASET,
    max_cost_usd: float = 1.0,
    max_records: int = DEFAULT_MAX_AUTO_RECORDS,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    definitions, statistics, probe = _fetch_bounded_databento_source(
        client,
        product_code,
        start_trade_date,
        end_trade_date,
        dataset,
        max_cost_usd,
        max_records,
    )
    return _canonicalize_databento_source(
        definitions,
        statistics,
        probe,
        schema,
        product_code,
        start_trade_date,
        end_trade_date,
        retrieved_at,
        dataset,
    )


@dataclass
class DatabentoFuturesProvider:
    client: DatabentoFuturesClient | None = None
    dataset: str = DATABENTO_DATASET
    max_auto_cost_usd: float = 1.0
    max_auto_records: int = DEFAULT_MAX_AUTO_RECORDS

    def _client(self) -> DatabentoFuturesClient:
        return self.client or DatabentoFuturesClient()

    def fetch_contract_history(
        self,
        schema: dict[str, Any],
        product_code: str,
        start_trade_date: str,
        end_trade_date: str,
        retrieved_at: str,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        return fetch_databento_canonical_history(
            self._client(),
            schema,
            product_code,
            start_trade_date,
            end_trade_date,
            retrieved_at,
            dataset=self.dataset,
            max_cost_usd=self.max_auto_cost_usd,
            max_records=self.max_auto_records,
        )

    def capture_archive(
        self,
        schema: dict[str, Any],
        product_code: str,
        start_trade_date: str,
        end_trade_date: str,
        retrieved_at: str,
        snapshot_root: Path,
        snapshot_id: str,
        max_contracts: int,
    ) -> Path:
        if max_contracts < 1:
            raise ValueError("max_contracts must be positive")
        definitions, statistics, probe = _fetch_bounded_databento_source(
            self._client(),
            product_code,
            start_trade_date,
            end_trade_date,
            self.dataset,
            self.max_auto_cost_usd,
            self.max_auto_records,
        )
        frame, metadata = _canonicalize_databento_source(
            definitions,
            statistics,
            probe,
            schema,
            product_code,
            start_trade_date,
            end_trade_date,
            retrieved_at,
            self.dataset,
        )
        ranked = frame.sort_values(["trade_date", "expiration", "contract_id"]).copy()
        ranked["_rank"] = ranked.groupby("trade_date").cumcount() + 1
        ranked = ranked[ranked["_rank"] <= max_contracts].drop(columns=["_rank"])
        writer = SnapshotWriter(Path(snapshot_root), "databento", snapshot_id)
        writer.write_bytes(
            "definitions.csv", definitions.to_csv(index=False).encode("utf-8")
        )
        writer.write_bytes(
            "statistics.csv", statistics.to_csv(index=False).encode("utf-8")
        )
        writer.write_bytes("canonical.csv", ranked.to_csv(index=False).encode("utf-8"))
        probe = metadata.pop("metadata_probe")
        writer.write_bytes(
            "metadata-probe.json",
            (json.dumps(probe, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8"),
        )
        return writer.finalize(
            {
                "request": {
                    "product_code": product_code,
                    "dataset": self.dataset,
                    "start_trade_date": start_trade_date,
                    "end_trade_date": end_trade_date,
                    "max_contracts": max_contracts,
                    "curve_selection": "expiration_rank_per_trade_date",
                },
                "retrieved_at": retrieved_at,
                "canonical_rows": len(ranked),
                "canonical_evidence": False,
                "licensing_rights_verified": False,
                "preflight": {
                    "metadata_only": bool(probe.get("metadata_only", False)),
                    "estimated_total_cost_usd": float(
                        probe["estimated_total_cost_usd"]
                    ),
                    "definition_record_count": int(probe["definition_record_count"]),
                    "statistics_record_count": int(probe["statistics_record_count"]),
                },
                "metadata": metadata,
            }
        )


def create_provider() -> DatabentoFuturesProvider:
    provider_config = data_config()["providers"]["databento_futures"]
    client = DatabentoFuturesClient(
        api_base=str(provider_config["api_base"]),
        env_key=str(provider_config["env_key"]),
    )
    return DatabentoFuturesProvider(
        client=client,
        dataset=str(provider_config["dataset"]),
        max_auto_cost_usd=float(provider_config["max_auto_cost_usd"]),
        max_auto_records=int(provider_config["max_auto_records"]),
    )
