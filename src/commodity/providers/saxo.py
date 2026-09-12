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


_SAXO_USERS_ROUTE = "users"
_SAXO_CURRENT_USER = "me"


@dataclass
class SaxoSimMarketDataClient:
    session: requests.Session | None = None
    access_token: str | None = None

    provider_id = "saxo_openapi_sim"

    def _provider(self) -> dict[str, Any]:
        provider = data_config()["providers"][self.provider_id]
        if provider.get("read_only") is not True:
            raise SaxoProbeError(f"Saxo provider must be read-only: {self.provider_id}")
        return provider

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
        payload = response.json()
        if not isinstance(payload, dict):
            raise SaxoProbeError("Saxo OpenAPI response must be a JSON object")
        return payload

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

    def chart_snapshot(self, uic: int, horizon: int = 1) -> dict[str, Any]:
        return self._get("chart/v3/charts", {
            "AssetType": "ContractFutures",
            "Uic": uic,
            "Horizon": horizon,
            "Count": 1,
            "FieldGroups": "ChartInfo,DisplayAndFormat,Data",
        })

    def user_details(self) -> dict[str, Any]:
        path = f"port/v1/{_SAXO_USERS_ROUTE}/{_SAXO_CURRENT_USER}"
        return self._get(path)

    def accounts(self) -> list[dict[str, Any]]:
        payload = self._get("port/v1/accounts/me", {"$top": 100})
        return list(payload.get("Data", []))

    def market_data_entitlements(self) -> dict[str, Any]:
        path = f"port/v1/{_SAXO_USERS_ROUTE}/{_SAXO_CURRENT_USER}/entitlements"
        return self._get(path)


class SaxoLiveMarketDataClient(SaxoSimMarketDataClient):
    provider_id = "saxo_openapi_live"


def resolve_continuous_future(
    summaries: list[dict[str, Any]], expected_symbol: str | None = None,
) -> dict[str, Any]:
    candidates = [item for item in summaries if item.get("DisplayHint") == "Continuous"]
    if expected_symbol is not None:
        candidates = [item for item in candidates if item.get("Symbol") == expected_symbol]
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

def probe_market_data_entitlements(client: SaxoSimMarketDataClient) -> dict[str, Any]:
    user = client.user_details()
    payload = client.market_data_entitlements()
    return {
        "schema_version": 1,
        "provider": client.provider_id,
        "read_only": True,
        "probed_at_utc": datetime.now(UTC).isoformat(),
        "user_active": bool(user.get("Active", False)),
        "legal_asset_types": list(user.get("LegalAssetTypes", [])),
        "market_data_via_openapi_terms_accepted": bool(
            user.get("MarketDataViaOpenApiTermsAccepted", False)
        ),
        "exchange_entitlements": list(payload.get("Data", [])),
    }


def probe_henry_hub(
    client: SaxoSimMarketDataClient,
    continuous_uic: int | None = None,
    max_contracts: int = 24,
) -> dict[str, Any]:
    source_id = (
        "saxo_henry_hub_live_probe"
        if client.provider_id == "saxo_openapi_live"
        else "saxo_henry_hub_probe"
    )
    source = data_config()["sources"][source_id]
    search_keywords = (
        source["products"][0]["search_keywords"]
        if source_id == "saxo_henry_hub_live_probe"
        else source["search_keywords"]
    )
    summaries = client.search_contract_futures(search_keywords)
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
        "provider": client.provider_id,
        "source": source_id,
        "searched_keywords": search_keywords,
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


def _live_product_probe(
    client: SaxoLiveMarketDataClient,
    product: dict[str, Any],
    horizon: int,
) -> dict[str, Any]:
    expected = str(product["base_identifier"])
    summaries = client.search_contract_futures(str(product["search_keywords"]))
    parent = resolve_continuous_future(summaries, expected_symbol=expected)
    continuous_uic = int(parent["Identifier"])
    space = client.futures_space(continuous_uic)
    if str(space.get("BaseIdentifier")) != expected:
        raise SaxoProbeError(f"Unexpected futures-space base identifier for {expected}")
    elements = sorted(space.get("Elements", []), key=lambda item: item.get("ExpiryDate", ""))
    active = [item for item in elements if int(item.get("DaysToExpiry", 0)) >= 0]
    if not active:
        raise SaxoProbeError(f"No active Saxo LIVE contract observed for {expected}")
    front = active[0]
    details = client.instrument_details(int(front["Uic"]))
    chart = client.chart_info(int(front["Uic"]), horizon=horizon)
    info = chart.get("ChartInfo", {})
    return {
        "base_identifier": expected,
        "continuous_uic": continuous_uic,
        "active_contract_symbol": front.get("Symbol"),
        "active_contract_uic": int(front["Uic"]),
        "active_contract_expiry": front.get("ExpiryDate"),
        "asset_type": details.get("AssetType"),
        "currency": details.get("CurrencyCode"),
        "exchange_id": info.get("ExchangeId"),
        "delayed_by_minutes": info.get("DelayedByMinutes"),
        "first_sample_time": info.get("FirstSampleTime"),
    }


def probe_live_execution_target(client: SaxoLiveMarketDataClient) -> dict[str, Any]:
    if client.provider_id != "saxo_openapi_live":
        raise SaxoProbeError("LIVE execution-target verification requires the Saxo LIVE provider")
    source = data_config()["sources"]["saxo_henry_hub_live_probe"]
    user = client.user_details()
    entitlement_payload = client.market_data_entitlements()
    accounts = client.accounts()
    legal_asset_types = {str(value) for value in user.get("LegalAssetTypes", [])}
    horizon = int(source["chart_horizon_minutes"])
    products = {
        str(product["base_identifier"]): _live_product_probe(client, product, horizon)
        for product in source["products"]
    }
    nymex_entitlements = [
        item for item in entitlement_payload.get("Data", [])
        if str(item.get("ExchangeId", "")).upper() == "NYMEX"
    ]
    blockers: list[str] = []
    if user.get("Active") is not True:
        blockers.append("live_user_not_active")
    if "ContractFutures" not in legal_asset_types:
        blockers.append("contract_futures_not_legal_for_live_user")
    if user.get("MarketDataViaOpenApiTermsAccepted") is not True:
        blockers.append("live_market_data_terms_not_accepted")
    if not accounts:
        blockers.append("no_live_account_visible")
    if not nymex_entitlements:
        blockers.append("nymex_market_data_entitlement_not_observed")
    for base, product in products.items():
        if product.get("exchange_id") != "NYMEX":
            blockers.append(f"{base.lower()}_exchange_not_nymex")
    return {
        "schema_version": 1,
        "provider": client.provider_id,
        "source": "saxo_henry_hub_live_probe",
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "authenticated_user_active": user.get("Active") is True,
        "market_data_terms_accepted": user.get("MarketDataViaOpenApiTermsAccepted") is True,
        "contract_futures_legal": "ContractFutures" in legal_asset_types,
        "account_count": len(accounts),
        "nymex_entitlement_observed": bool(nymex_entitlements),
        "products": products,
        "ready_for_read_only_shadow": not blockers,
        "canonical_market_source": False,
        "backtest_evidence_allowed": False,
        "phase7_scientific_source_allowed": False,
        "phase7_settlement_source_allowed": False,
        "order_submission_allowed": False,
        "blockers": blockers,
    }
