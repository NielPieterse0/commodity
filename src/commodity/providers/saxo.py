from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests

from commodity.config import data_config
from commodity.providers import MissingCredential


class SaxoProbeError(RuntimeError):
    pass


@dataclass
class SaxoSimMarketDataClient:
    session: requests.Session | None = None
    access_token: str | None = None

    def _provider(self) -> dict[str, Any]:
        return data_config()["providers"]["saxo_openapi_sim"]

    def _token(self) -> str:
        cfg = self._provider()
        token = self.access_token or os.getenv(cfg["env_key"])
        if not token:
            raise MissingCredential(f"Missing environment variable: {cfg['env_key']}")
        return token

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        provider = self._provider()
        session = self.session or requests.Session()
        response = session.get(
            f"{provider['api_base'].rstrip('/')}/{path.lstrip('/')}",
            params=params,
            headers={"Authorization": f"Bearer {self._token()}", "Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def search_contract_futures(self, keywords: str, top: int = 100) -> list[dict[str, Any]]:
        payload = self._get("ref/v1/instruments", {
            "Keywords": keywords,
            "AssetTypes": "ContractFutures",
            "IncludeNonTradable": "true",
            "$top": top,
        })
        return list(payload.get("Data", []))

    def futures_space(self, continuous_uic: int) -> dict[str, Any]:
        return self._get(f"ref/v1/instruments/futuresspaces/{continuous_uic}")

    def instrument_details(self, uic: int) -> dict[str, Any]:
        return self._get(f"ref/v1/instruments/details/{uic}/ContractFutures")

    def chart_info(self, uic: int, horizon: int = 1440) -> dict[str, Any]:
        return self._get("chart/v3/charts", {
            "AssetType": "ContractFutures",
            "Uic": uic,
            "Horizon": horizon,
            "Count": 1,
            "FieldGroups": "ChartInfo,DisplayAndFormat",
        })


def resolve_continuous_future(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [item for item in summaries if item.get("DisplayHint") == "Continuous"]
    if len(candidates) != 1:
        ids = [item.get("Identifier") for item in candidates]
        raise SaxoProbeError(f"Expected one continuous futures parent; candidates={ids}")
    return candidates[0]


def _contract_probe(client: SaxoSimMarketDataClient, element: dict[str, Any], horizon: int) -> dict[str, Any]:
    chart = client.chart_info(int(element["Uic"]), horizon=horizon)
    info = chart.get("ChartInfo", {})
    return {
        "symbol": element.get("Symbol"),
        "uic": int(element["Uic"]),
        "expiry_date": element.get("ExpiryDate"),
        "days_to_expiry": element.get("DaysToExpiry"),
        "first_sample_time": info.get("FirstSampleTime"),
        "exchange_id": info.get("ExchangeId"),
        "delayed_by_minutes": info.get("DelayedByMinutes"),
    }

def probe_henry_hub(
    client: SaxoSimMarketDataClient,
    continuous_uic: int | None = None,
    max_contracts: int = 24,
) -> dict[str, Any]:
    source = data_config()["sources"]["saxo_henry_hub_probe"]
    summaries = client.search_contract_futures(source["search_keywords"])
    parent = None
    if continuous_uic is None:
        parent = resolve_continuous_future(summaries)
        continuous_uic = int(parent["Identifier"])
    space = client.futures_space(continuous_uic)
    elements = sorted(space.get("Elements", []), key=lambda item: item.get("ExpiryDate", ""))
    probes = [
        _contract_probe(client, item, int(source["chart_horizon_minutes"]))
        for item in elements[:max_contracts]
    ]
    today = datetime.now(UTC).date().isoformat()
    expired = [item for item in probes if item.get("expiry_date") and item["expiry_date"][:10] < today]
    blockers = ["saxo_chart_does_not_provide_official_settlement"]
    if not expired:
        blockers.append("expired_contract_depth_not_observed")
    return {
        "schema_version": 1,
        "provider": "saxo_openapi_sim",
        "source": "saxo_henry_hub_probe",
        "searched_keywords": source["search_keywords"],
        "probed_at_utc": datetime.now(UTC).isoformat(),
        "chart_horizon_minutes": int(source["chart_horizon_minutes"]),
        "continuous_uic": continuous_uic,
        "continuous_summary": parent,
        "base_identifier": space.get("BaseIdentifier"),
        "contract_count": len(elements),
        "contracts_probed": probes,
        "expired_contracts_observed": len(expired),
        "canonical_market_source": False,
        "backtest_evidence_allowed": False,
        "blockers": blockers,
    }
