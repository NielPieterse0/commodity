from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
FINAL_SETTLEMENT_FLAG = 1 << 0
INTRADAY_SETTLEMENT_FLAG = 1 << 3
SETTLEMENT_STAT_TYPE = 3
CLEARED_VOLUME_STAT_TYPE = 6
STATISTICS_CAPTURE_GRACE_DAYS = 3
DEFAULT_MAX_AUTO_RECORDS = 50_000


class DatabentoApiError(RuntimeError):
    pass


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
    definitions["expiration"] = pd.to_datetime(definitions["expiration"], utc=True, errors="coerce")
    if definitions["expiration"].isna().any():
        raise DataContractViolation("Databento definitions contain invalid expiration")
    definitions = definitions.sort_values("expiration").drop_duplicates("raw_symbol", keep="last")

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

    settlements = stats[stats["stat_type"].eq(SETTLEMENT_STAT_TYPE)].copy()
    settlements = settlements[
        settlements["stat_flags"].map(
            lambda value: bool(int(value) & FINAL_SETTLEMENT_FLAG)
            and not bool(int(value) & INTRADAY_SETTLEMENT_FLAG)
        )
    ]
    if settlements.empty:
        raise DataContractViolation("Databento returned no final settlement statistics")
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
    settlements = settlements[
        ["_symbol", "ts_ref", "ts_event", "_available_at", "price"]
    ].copy()

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

    definition_cols = ["raw_symbol", "expiration", "exchange"]
    out = settlements.merge(
        definitions[definition_cols],
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
            "contract_id": out["raw_symbol"].astype(str),
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
    metadata = {
        "source_id": "databento_glbx_mdp3_statistics_v0",
        "source_sha256": source_sha256,
        "retrieved_at": retrieved_at,
        "exchange": exchange,
        "product_code": product_code,
        "session_timezone": "America/Chicago",
        "calendar": "CME_NYMEX",
        "price_semantics": "cme_final_settlement_from_databento_statistics",
        "settlement_availability_semantics": "statistics_ts_recv_else_ts_event",
        "volume_semantics": "cme_cleared_volume_from_databento_statistics",
    }
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
    validate_contract_metadata(metadata, schema)
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
