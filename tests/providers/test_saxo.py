import pytest

from commodity.providers import MissingCredential
from commodity.providers.saxo import (
    SaxoLiveMarketDataClient,
    SaxoProbeError,
    SaxoSimMarketDataClient,
    probe_henry_hub,
    probe_live_execution_target,
    probe_market_data_entitlements,
)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self):
        return self.payload


class Session:
    def __init__(self):
        self.calls = []

    def get(self, url, params, headers, timeout):
        self.calls.append((url, params, headers, timeout))
        if url.endswith("/ref/v1/instruments"):
            return Response({"Data": [{
                "AssetType": "ContractFutures", "DisplayHint": "Continuous",
                "Description": "Henry Hub Natural Gas", "Identifier": 100, "Symbol": "NG",
            }]})
        if url.endswith("/futuresspaces/100"):
            return Response({"BaseIdentifier": "NG", "Elements": [
                {"Symbol": "NGZ20", "Uic": 201, "ExpiryDate": "2020-11-25T00:00:00Z", "DaysToExpiry": -2000},
                {"Symbol": "NGZ99", "Uic": 202, "ExpiryDate": "2099-11-25T00:00:00Z", "DaysToExpiry": 26000},
            ]})
        if url.endswith("/chart/v3/charts"):
            first = "2019-01-02T00:00:00Z" if params["Uic"] == 201 else "2026-01-02T00:00:00Z"
            return Response({"ChartInfo": {"FirstSampleTime": first, "ExchangeId": "NYMEX"}})
        users_route = "users"
        current_user = "me"
        entitlement_path = f"port/v1/{users_route}/{current_user}/entitlements"
        if url.endswith(f"/{entitlement_path}"):
            return Response({"Data": [{
                "ExchangeId": "NYMEX",
                "Entitlements": [{"DelayedFullBook": ["ContractFutures"]}],
            }]})
        user_path = f"port/v1/{users_route}/{current_user}"
        if url.endswith(f"/{user_path}"):
            return Response({
                "Active": True,
                "LegalAssetTypes": ["ContractFutures"],
                "MarketDataViaOpenApiTermsAccepted": True,
            })
        raise AssertionError(url)


def test_saxo_requires_configured_sim_token(monkeypatch) -> None:
    monkeypatch.delenv("SAXO_SIM_ACCESS_TOKEN", raising=False)
    client = SaxoSimMarketDataClient(session=Session())
    with pytest.raises(MissingCredential, match="SAXO_SIM_ACCESS_TOKEN"):
        client.search_contract_futures("Henry Hub Natural Gas")


def test_saxo_probe_uses_read_only_reference_and_chart_endpoints() -> None:
    session = Session()
    report = probe_henry_hub(SaxoSimMarketDataClient(session=session, access_token="test-token"))
    assert report["continuous_uic"] == 100
    assert report["base_identifier"] == "NG"
    assert report["expired_contracts_observed"] == 1
    assert report["contracts_probed"][0]["first_sample_time"] == "2019-01-02T00:00:00Z"
    assert report["canonical_market_source"] is False
    assert "saxo_chart_does_not_provide_official_settlement" in report["blockers"]
    assert all(call[2]["Authorization"] == "Bearer test-token" for call in session.calls)


def test_saxo_live_entitlement_probe_is_read_only_and_environment_bound() -> None:
    session = Session()
    client = SaxoLiveMarketDataClient(session=session, access_token="live-test-token")
    report = probe_market_data_entitlements(client)
    assert report["provider"] == "saxo_openapi_live"
    assert report["read_only"] is True
    assert report["user_active"] is True
    assert report["legal_asset_types"] == ["ContractFutures"]
    assert report["market_data_via_openapi_terms_accepted"] is True
    exchange = report["exchange_entitlements"][0]
    assert exchange["ExchangeId"] == "NYMEX"
    assert exchange["Entitlements"][0]["DelayedFullBook"] == ["ContractFutures"]
    assert len(session.calls) == 2
    assert all(call[1] is None for call in session.calls)
    assert all(call[2]["Authorization"] == "Bearer live-test-token" for call in session.calls)


def test_saxo_live_requires_distinct_live_token(monkeypatch) -> None:
    monkeypatch.delenv("SAXO_LIVE_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("SAXO_SIM_ACCESS_TOKEN", "sim-token-must-not-be-used")
    with pytest.raises(MissingCredential, match="SAXO_LIVE_ACCESS_TOKEN"):
        SaxoLiveMarketDataClient(session=Session()).market_data_entitlements()


def test_saxo_probe_refuses_ambiguous_continuous_parent() -> None:
    class AmbiguousSession(Session):
        def get(self, url, params, headers, timeout):
            if url.endswith("/ref/v1/instruments"):
                item = {"AssetType": "ContractFutures", "DisplayHint": "Continuous"}
                return Response({"Data": [dict(item, Identifier=1), dict(item, Identifier=2)]})
            return super().get(url, params, headers, timeout)

    with pytest.raises(SaxoProbeError, match="Expected one"):
        probe_henry_hub(SaxoSimMarketDataClient(session=AmbiguousSession(), access_token="test-token"))


class LiveExecutionSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers, timeout))
        users_route = "users"
        current_user = "me"
        user_path = f"/port/v1/{users_route}/{current_user}"
        if url.endswith(f"{user_path}/entitlements"):
            return Response({"Data": [{
                "ExchangeId": "NYMEX",
                "Entitlements": [{"RealTimeTopOfBook": ["ContractFutures"]}],
            }]})
        if url.endswith(user_path):
            return Response({
                "Active": True,
                "ClientKey": "sensitive-client-key",
                "UserId": "sensitive-user-id",
                "UserKey": "sensitive-user-key",
                "LegalAssetTypes": ["ContractFutures", "Stock"],
                "MarketDataViaOpenApiTermsAccepted": True,
            })
        if url.endswith("/port/v1/accounts/me"):
            return Response({"Data": [{
                "AccountId": "sensitive-account-id",
                "AccountKey": "sensitive-account-key",
                "AccountType": "Normal",
                "Active": True,
            }]})
        if url.endswith("/ref/v1/instruments"):
            is_micro = "Micro" in params["Keywords"]
            symbol = "MNG" if is_micro else "NG"
            identifier = 110 if is_micro else 100
            return Response({"Data": [{
                "AssetType": "ContractFutures",
                "DisplayHint": "Continuous",
                "Description": f"{symbol} continuous",
                "Identifier": identifier,
                "Symbol": symbol,
            }]})
        if url.endswith("/futuresspaces/100"):
            return Response({"BaseIdentifier": "NG", "Elements": [{
                "Symbol": "NGX6", "Uic": 201,
                "ExpiryDate": "2026-10-28T00:00:00Z", "DaysToExpiry": 46,
            }]})
        if url.endswith("/futuresspaces/110"):
            return Response({"BaseIdentifier": "MNG", "Elements": [{
                "Symbol": "MNGX6", "Uic": 211,
                "ExpiryDate": "2026-10-28T00:00:00Z", "DaysToExpiry": 46,
            }]})
        if "/ref/v1/instruments/details/" in url:
            return Response({"AssetType": "ContractFutures", "CurrencyCode": "USD"})
        if url.endswith("/chart/v3/charts"):
            return Response({"ChartInfo": {
                "FirstSampleTime": "2026-01-02T00:00:00Z",
                "ExchangeId": "NYMEX", "DelayedByMinutes": 0,
            }})
        raise AssertionError(url)


def test_live_execution_target_probe_verifies_ng_mng_without_identity_leakage() -> None:
    session = LiveExecutionSession()
    report = probe_live_execution_target(
        SaxoLiveMarketDataClient(session=session, access_token="live-test-token")
    )
    assert report["provider"] == "saxo_openapi_live"
    assert report["authenticated_user_active"] is True
    assert report["market_data_terms_accepted"] is True
    assert report["contract_futures_legal"] is True
    assert report["account_count"] == 1
    assert report["nymex_entitlement_observed"] is True
    assert report["products"]["NG"]["base_identifier"] == "NG"
    assert report["products"]["MNG"]["base_identifier"] == "MNG"
    assert report["products"]["NG"]["exchange_id"] == "NYMEX"
    assert report["ready_for_read_only_shadow"] is True
    assert report["phase7_scientific_source_allowed"] is False
    assert report["phase7_settlement_source_allowed"] is False
    assert report["order_submission_allowed"] is False
    serialized = str(report)
    for secret_value in (
        "sensitive-client-key", "sensitive-user-id", "sensitive-user-key",
        "sensitive-account-id", "sensitive-account-key",
    ):
        assert secret_value not in serialized
    assert all(call[0].startswith("https://gateway.saxobank.com/openapi/") for call in session.calls)
