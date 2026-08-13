from typing import ClassVar

import pandas as pd
import pytest

from commodity.config import data_config
from commodity.market_data import DataContractViolation, validate_contract_metadata
from commodity.massive import (
    MassiveFuturesClient,
    MassiveRateLimitError,
    capture_massive_archive,
    fetch_massive_canonical_history,
    normalize_massive_contract_history,
)
from commodity.providers import MissingCredential


def _schema() -> dict:
    return data_config()["canonical_contract_schema"]


def test_massive_requires_configured_environment_key(monkeypatch) -> None:
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    with pytest.raises(MissingCredential, match="MASSIVE_API_KEY"):
        MassiveFuturesClient().list_outright_contracts("NG", max_pages=1)


def test_massive_contract_discovery_paginates_and_keeps_outrights(monkeypatch) -> None:
    class Response:
        def __init__(self, payload):
            self.payload = payload
        def raise_for_status(self) -> None:
            pass
        def json(self):
            return self.payload

    class Session:
        def __init__(self) -> None:
            self.calls = 0
            self.params = []
        def get(self, url, params, timeout, headers=None):
            self.calls += 1
            self.params.append(params)
            if self.calls == 1:
                return Response({"results": [
                    {"ticker": "NG:BF F0-G0-H0", "product_code": "NG"},
                    {"ticker": "NGF5", "product_code": "NG", "last_trade_date": "2025-01-29", "date": "2025-01-01"},
                ], "next_url": "https://api.massive.com/futures/v1/contracts?cursor=next"})
            return Response({"results": [
                {"ticker": "NGF5", "product_code": "NG", "last_trade_date": "2025-01-30", "date": "2025-01-02"},
                {"ticker": "NGG5", "product_code": "NG", "last_trade_date": "2025-02-26"},
            ]})

    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    session = Session()
    rows = MassiveFuturesClient(session=session).list_outright_contracts("NG", max_pages=2)
    assert [row["ticker"] for row in rows] == ["NGF5", "NGG5"]
    assert session.calls == 2
    assert session.params[0]["ticker.gte"] == "NGF0"
    assert session.params[0]["ticker.lt"] == "NG~"
    assert rows[0]["last_trade_date"] == "2025-01-30"


def test_massive_session_aggregates_use_session_resolution_and_range(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            pass
        def json(self):
            return {"results": [{"ticker": "NGF5", "session_end_date": "2025-01-02", "settlement_price": 3.1, "volume": 100}]}

    class Session:
        def __init__(self) -> None:
            self.params = None
        def get(self, url, params, timeout, headers=None):
            self.params = params
            assert url.endswith("/futures/v1/aggs/NGF5")
            return Response()

    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    session = Session()
    frame = MassiveFuturesClient(session=session).fetch_session_aggregates("NGF5", "2025-01-01", "2025-01-31")
    assert session.params["resolution"] == "1session"
    assert session.params["window_start.gte"] == "2024-12-31"
    assert session.params["window_start.lte"] == "2025-01-30"
    assert frame.iloc[0]["settlement_price"] == pytest.approx(3.1)


def test_massive_rejects_silent_pagination_truncation(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            pass
        def json(self):
            return {"results": [{"ticker": "NGF5", "product_code": "NG"}], "next_url": "https://api.massive.com/futures/v1/contracts?cursor=next"}
    class Session:
        def get(self, url, params, timeout, headers=None):
            return Response()
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    with pytest.raises(RuntimeError, match="pagination limit"):
        MassiveFuturesClient(session=Session()).list_outright_contracts("NG", max_pages=1)


def test_massive_contract_history_normalizes_to_canonical_grain() -> None:
    contract = {"ticker": "NGF5", "product_code": "NG", "last_trade_date": "2025-01-29", "trading_venue": "XNYM"}
    aggregates = pd.DataFrame([{"ticker": "NGF5", "session_end_date": "2025-01-02", "open": 3.0, "high": 3.2, "low": 2.9, "close": 3.1, "settlement_price": 3.08, "volume": 1234}])
    frame, metadata = normalize_massive_contract_history(contract, aggregates, "2026-08-12T18:00:00Z")
    row = frame.iloc[0]
    assert row["contract_id"] == "NGF5"
    assert row["settle"] == pytest.approx(3.08)
    assert row["volume"] == 1234
    assert row["trade_date"] == pd.Timestamp("2025-01-02", tz="UTC")
    validate_contract_metadata(metadata, _schema())


def test_massive_canonical_ingestion_filters_contracts_and_combines_history() -> None:
    class Client:
        def __init__(self) -> None:
            self.fetched = []
        def list_outright_contracts(self, product_code, **kwargs):
            return [
                {"ticker": "NGZ4", "product_code": "NG", "first_trade_date": "2024-01-01", "last_trade_date": "2024-11-27", "trading_venue": "XNYM"},
                {"ticker": "NGF5", "product_code": "NG", "first_trade_date": "2024-02-01", "last_trade_date": "2025-01-29", "trading_venue": "XNYM"},
                {"ticker": "NGG5", "product_code": "NG", "first_trade_date": "2024-03-01", "last_trade_date": "2025-02-26", "trading_venue": "XNYM"},
            ]
        def fetch_session_aggregates(self, ticker, start_trade_date, end_trade_date, max_pages=100):
            self.fetched.append((ticker, start_trade_date, end_trade_date))
            settle = {"NGF5": 3.08, "NGG5": 3.18}[ticker]
            return pd.DataFrame([{"ticker": ticker, "session_end_date": "2025-01-02", "settlement_price": settle, "volume": 100}])

    client = Client()
    frame, metadata = fetch_massive_canonical_history(client, _schema(), "NG", "2025-01-01", "2025-01-31", "2026-08-12T18:00:00Z")
    assert list(frame["contract_id"]) == ["NGF5", "NGG5"]
    assert [item[0] for item in client.fetched] == ["NGF5", "NGG5"]
    assert metadata["source_contract_count"] == 2


def test_massive_canonical_ingestion_rejects_missing_expiry_metadata() -> None:
    class Client:
        def list_outright_contracts(self, product_code, **kwargs):
            return [{"ticker": "NGF5", "product_code": product_code, "first_trade_date": "2024-02-01", "trading_venue": "XNYM"}]
    with pytest.raises(DataContractViolation, match="last_trade_date"):
        fetch_massive_canonical_history(Client(), _schema(), "NG", "2025-01-01", "2025-01-31", "2026-08-12T18:00:00Z")


def test_massive_uses_bearer_header_not_query_string(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            pass
        def json(self):
            return {"results": []}
    class Session:
        def __init__(self) -> None:
            self.params = None
            self.headers = None
        def get(self, url, params, timeout, headers=None):
            self.params = params
            self.headers = headers
            return Response()
    monkeypatch.setenv("MASSIVE_API_KEY", "secret-test-key")
    session = Session()
    MassiveFuturesClient(session=session).list_outright_contracts("NG", max_pages=1)
    assert "apiKey" not in session.params
    assert session.headers == {"Authorization": "Bearer secret-test-key"}


def test_massive_retries_429_using_retry_after(monkeypatch) -> None:
    class Response:
        def __init__(self, status_code, payload, headers=None):
            self.status_code = status_code
            self.payload = payload
            self.headers = headers or {}
        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")
        def json(self):
            return self.payload
    class Session:
        def __init__(self) -> None:
            self.calls = 0
        def get(self, url, params, timeout, headers=None):
            self.calls += 1
            return Response(429, {}, {"Retry-After": "2"}) if self.calls == 1 else Response(200, {"results": []})
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    waits = []
    client = MassiveFuturesClient(session=Session(), sleep=waits.append, max_retries=2)
    assert client.list_outright_contracts("NG", max_pages=1) == []
    assert waits == [2.0]


def test_massive_rate_limit_exhaustion_fails_closed(monkeypatch) -> None:
    class Response:
        status_code = 429
        headers: ClassVar[dict[str, str]] = {}
        def raise_for_status(self) -> None:
            raise AssertionError("429 must be handled before raise_for_status")
        def json(self):
            return {}
    class Session:
        def get(self, url, params, timeout, headers=None):
            return Response()
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    waits = []
    client = MassiveFuturesClient(session=Session(), sleep=waits.append, max_retries=2, base_backoff_seconds=0.5)
    with pytest.raises(MassiveRateLimitError, match="rate limit"):
        client.list_outright_contracts("NG", max_pages=1)
    assert waits == [0.5, 1.0]


def test_massive_contract_discovery_can_bound_reference_history(monkeypatch) -> None:
    class Response:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}
        def raise_for_status(self) -> None:
            pass
        def json(self):
            return {"results": [{"ticker": "NGU26", "product_code": "NG"}]}
    class Session:
        def __init__(self) -> None:
            self.params = []
        def get(self, url, params, timeout, headers=None):
            self.params.append(params)
            return Response()
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    session = Session()
    MassiveFuturesClient(session=session).list_outright_contracts("NG", start_trade_date="2024-08-13", end_trade_date="2026-08-12", max_pages=1)
    assert [params["date"] for params in session.params] == ["2024-08-13", "2026-08-12"]


def test_massive_schedule_fetch_chunks_long_ranges(monkeypatch) -> None:
    class Response:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}
        def __init__(self, params):
            self.params = params
        def raise_for_status(self) -> None:
            pass
        def json(self):
            start = self.params["session_end_date.gte"]
            return {"results": [{"product_code": "NG", "event": "close", "session_end_date": start, "timestamp": f"{start}T22:00:00Z", "trading_venue": "XNYM"}]}
    class Session:
        def __init__(self):
            self.params = []
        def get(self, url, params, timeout, headers=None):
            self.params.append(dict(params))
            return Response(params)
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    session = Session()
    rows = MassiveFuturesClient(session=session).fetch_schedules("NG", "2026-01-01", "2026-04-15", chunk_days=30)
    assert len(session.params) == 4
    assert len(rows) == 4
    assert all("sort" not in params for params in session.params)


def test_massive_archive_resumes_only_hashed_checkpoint_artifacts(tmp_path) -> None:
    contracts = [
        {"ticker": "NGF5", "product_code": "NG", "first_trade_date": "2024-01-01", "last_trade_date": "2025-01-29", "trading_venue": "XNYM"},
        {"ticker": "NGG5", "product_code": "NG", "first_trade_date": "2024-02-01", "last_trade_date": "2025-02-26", "trading_venue": "XNYM"},
    ]
    class FailingClient:
        def __init__(self) -> None:
            self.fetched = []
        def list_outright_contracts(self, product_code, **kwargs):
            return contracts
        def fetch_schedules(self, product_code, start_trade_date, end_trade_date):
            return [{"product_code": product_code, "event": "open", "session_end_date": "2025-01-02", "timestamp": "2025-01-01T23:00:00Z"}]
        def fetch_session_aggregates(self, ticker, start_trade_date, end_trade_date):
            self.fetched.append(ticker)
            if ticker == "NGG5":
                raise RuntimeError("provider interruption")
            return pd.DataFrame([{"ticker": ticker, "session_end_date": "2025-01-02", "settlement_price": 3.08, "volume": 100}])
    first = FailingClient()
    with pytest.raises(RuntimeError, match="provider interruption"):
        capture_massive_archive(first, _schema(), "NG", "2025-01-01", "2025-01-31", "2026-08-13T08:00:00Z", tmp_path, "snap-1")
    class ResumeClient(FailingClient):
        def fetch_session_aggregates(self, ticker, start_trade_date, end_trade_date):
            self.fetched.append(ticker)
            return pd.DataFrame([{"ticker": ticker, "session_end_date": "2025-01-02", "settlement_price": 3.18, "volume": 200}])
    second = ResumeClient()
    manifest = capture_massive_archive(second, _schema(), "NG", "2025-01-01", "2025-01-31", "2026-08-13T08:00:00Z", tmp_path, "snap-1")
    assert second.fetched == ["NGG5"]
    assert manifest.name == "manifest.json"
    assert not (manifest.parent / ".checkpoint.json").exists()
