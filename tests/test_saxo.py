import pytest

from commodity.providers import MissingCredential
from commodity.saxo import SaxoProbeError, SaxoSimMarketDataClient, probe_henry_hub


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


def test_saxo_probe_refuses_ambiguous_continuous_parent() -> None:
    class AmbiguousSession(Session):
        def get(self, url, params, headers, timeout):
            if url.endswith("/ref/v1/instruments"):
                item = {"AssetType": "ContractFutures", "DisplayHint": "Continuous"}
                return Response({"Data": [dict(item, Identifier=1), dict(item, Identifier=2)]})
            return super().get(url, params, headers, timeout)

    with pytest.raises(SaxoProbeError, match="Expected one"):
        probe_henry_hub(SaxoSimMarketDataClient(session=AmbiguousSession(), access_token="test-token"))
