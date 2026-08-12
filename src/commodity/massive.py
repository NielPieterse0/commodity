from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
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


@dataclass
class MassiveFuturesClient:
    session: requests.Session | None = None

    def _request_page(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cfg = data_config()["providers"]["massive_futures"]
        api_key = os.getenv(cfg["env_key"])
        if not api_key:
            raise MissingCredential(f"Missing environment variable: {cfg['env_key']}")
        query = dict(params or {})
        headers = {"Authorization": f"Bearer {api_key}"}
        response = (self.session or requests.Session()).get(
            url, params=query, headers=headers, timeout=30
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") not in (None, "OK"):
            raise RuntimeError(f"Massive request failed with status: {payload.get('status')}")
        return payload

    def _paged_results(
        self,
        url: str,
        params: dict[str, Any],
        max_pages: int,
    ) -> list[dict[str, Any]]:
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        rows: list[dict[str, Any]] = []
        current_params: dict[str, Any] | None = params
        for _ in range(max_pages):
            payload = self._request_page(url, params=current_params)
            rows.extend(payload.get("results", []))
            next_url = payload.get("next_url")
            if not next_url:
                return rows
            url = str(next_url)
            current_params = {}
        raise RuntimeError("Massive pagination limit reached before response completion")

    def list_outright_contracts(
        self,
        product_code: str,
        max_pages: int = 100,
    ) -> list[dict[str, Any]]:
        cfg = data_config()["providers"]["massive_futures"]
        url = f"{cfg['api_base'].rstrip('/')}/futures/v1/contracts"
        params = {
            "product_code": product_code,
            "ticker.gte": f"{product_code}F0",
            "ticker.lt": f"{product_code}~",
            "limit": 1000,
            "sort": "ticker.asc,date.asc",
        }
        pattern = re.compile(rf"^{re.escape(product_code)}[FGHJKMNQUVXZ]\d{{1,2}}$")
        by_ticker: dict[str, dict[str, Any]] = {}
        for row in self._paged_results(url, params, max_pages):
            ticker = str(row.get("ticker", ""))
            if pattern.fullmatch(ticker):
                by_ticker[ticker] = row
        return list(by_ticker.values())

    def fetch_session_aggregates(
        self,
        ticker: str,
        start_trade_date: str,
        end_trade_date: str,
        max_pages: int = 100,
    ) -> pd.DataFrame:
        cfg = data_config()["providers"]["massive_futures"]
        url = f"{cfg['api_base'].rstrip('/')}/futures/v1/aggs/{ticker}"
        start_window = (pd.Timestamp(start_trade_date) - pd.Timedelta(days=1)).date().isoformat()
        end_window = (pd.Timestamp(end_trade_date) - pd.Timedelta(days=1)).date().isoformat()
        params = {
            "resolution": "1session",
            "window_start.gte": start_window,
            "window_start.lte": end_window,
            "limit": 50000,
            "sort": "window_start.asc",
        }
        frame = pd.DataFrame(self._paged_results(url, params, max_pages))
        if "session_end_date" in frame.columns:
            session_date = pd.to_datetime(frame["session_end_date"], errors="coerce")
            start = pd.Timestamp(start_trade_date)
            end = pd.Timestamp(end_trade_date)
            frame = frame[(session_date >= start) & (session_date <= end)].reset_index(drop=True)
        return frame



def normalize_massive_contract_history(
    contract: dict[str, Any],
    aggregates: pd.DataFrame,
    retrieved_at: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required_contract = ("ticker", "product_code", "last_trade_date", "trading_venue")
    missing_contract = [field for field in required_contract if not contract.get(field)]
    if missing_contract:
        raise DataContractViolation(f"Massive contract metadata missing fields: {missing_contract}")
    required_aggregate = ("session_end_date", "settlement_price")
    missing_aggregate = [field for field in required_aggregate if field not in aggregates.columns]
    if missing_aggregate:
        raise DataContractViolation(f"Massive aggregates missing fields: {missing_aggregate}")
    if aggregates.empty:
        raise DataContractViolation("Massive aggregates are empty")

    out = pd.DataFrame({
        "trade_date": pd.to_datetime(aggregates["session_end_date"], utc=True),
        "contract_id": str(contract["ticker"]),
        "expiration": pd.to_datetime(contract["last_trade_date"], utc=True),
        "settle": pd.to_numeric(aggregates["settlement_price"], errors="coerce"),
    })
    for source, target in (
        ("open", "open"), ("high", "high"), ("low", "low"),
        ("close", "close"), ("volume", "volume"),
    ):
        if source in aggregates.columns:
            out[target] = aggregates[source].values
    if out["settle"].isna().any():
        raise DataContractViolation("Massive aggregates contain missing settlement prices")

    source_bytes = (
        json.dumps(contract, sort_keys=True, default=str)
        + "\n"
        + aggregates.to_csv(index=False)
    ).encode("utf-8")
    metadata = {
        "source_id": "massive_futures_rest_v1",
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "retrieved_at": retrieved_at,
        "exchange": contract["trading_venue"],
        "product_code": contract["product_code"],
        "session_timezone": "America/Chicago",
        "calendar": "CME_NYMEX",
        "price_semantics": "massive_session_settlement_price",
    }
    return out, metadata


def fetch_massive_canonical_history(
    client: Any,
    schema: dict[str, Any],
    product_code: str,
    start_trade_date: str,
    end_trade_date: str,
    retrieved_at: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    start = pd.Timestamp(start_trade_date, tz="UTC")
    end = pd.Timestamp(end_trade_date, tz="UTC")
    if end < start:
        raise ValueError("end_trade_date must be on or after start_trade_date")

    frames: list[pd.DataFrame] = []
    components: list[dict[str, Any]] = []
    contracts = client.list_outright_contracts(product_code)
    exchanges: set[str] = set()
    for contract in contracts:
        first = pd.to_datetime(contract.get("first_trade_date"), utc=True, errors="coerce")
        last = pd.to_datetime(contract.get("last_trade_date"), utc=True, errors="coerce")
        if pd.isna(last):
            ticker = contract.get("ticker", "<unknown>")
            raise DataContractViolation(
                f"Massive contract {ticker} is missing a valid last_trade_date"
            )
        if last < start or (not pd.isna(first) and first > end):
            continue
        fetch_start = max(start, first) if not pd.isna(first) else start
        fetch_end = min(end, last)
        aggregates = client.fetch_session_aggregates(
            str(contract["ticker"]),
            fetch_start.date().isoformat(),
            fetch_end.date().isoformat(),
        )
        if aggregates.empty:
            continue
        normalized, metadata = normalize_massive_contract_history(
            contract, aggregates, retrieved_at=retrieved_at
        )
        validate_contract_metadata(metadata, schema)
        exchanges.add(str(metadata["exchange"]))
        frames.append(normalized)
        components.append({
            "contract_id": str(contract["ticker"]),
            "source_sha256": metadata["source_sha256"],
        })

    if not frames:
        raise DataContractViolation("Massive returned no canonical contract history for range")
    if len(exchanges) != 1:
        raise DataContractViolation(
            f"Massive canonical history spans multiple trading venues: {sorted(exchanges)}"
        )
    exchange = next(iter(exchanges))
    combined = validate_contract_history(pd.concat(frames, ignore_index=True), schema)
    combined_hash = hashlib.sha256(
        json.dumps(components, sort_keys=True).encode("utf-8")
    ).hexdigest()
    metadata = {
        "source_id": "massive_futures_rest_v1",
        "source_sha256": combined_hash,
        "retrieved_at": retrieved_at,
        "exchange": exchange,
        "product_code": product_code,
        "session_timezone": "America/Chicago",
        "calendar": "CME_NYMEX",
        "price_semantics": "massive_session_settlement_price",
        "source_contract_count": len(components),
        "source_contracts": components,
    }
    validate_contract_metadata(metadata, schema)
    return combined, metadata
