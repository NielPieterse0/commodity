import pandas as pd
import pytest

from commodity.config import data_config
from commodity.massive import MassiveFuturesClient, fetch_massive_canonical_history


def _schema() -> dict:
    return data_config()["canonical_contract_schema"]


def test_massive_aggregates_reject_silent_pagination_truncation(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self):
            return {
                "results": [
                    {
                        "ticker": "NGF5",
                        "session_end_date": "2025-01-02",
                        "settlement_price": 3.1,
                    }
                ],
                "next_url": "https://api.massive.com/futures/v1/aggs/NGF5?cursor=next",
            }

    class Session:
        def get(self, url, params, timeout, headers=None):
            return Response()

    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    with pytest.raises(RuntimeError, match="pagination limit"):
        MassiveFuturesClient(session=Session()).fetch_session_aggregates(
            "NGF5", "2025-01-01", "2025-01-31", max_pages=1
        )


def test_massive_dataset_metadata_derives_exchange_from_contracts() -> None:
    class Client:
        def list_outright_contracts(self, product_code, **kwargs):
            return [
                {
                    "ticker": "GCF5",
                    "product_code": product_code,
                    "first_trade_date": "2024-01-01",
                    "last_trade_date": "2025-01-29",
                    "trading_venue": "XCEC",
                }
            ]

        def fetch_session_aggregates(
            self, ticker, start_trade_date, end_trade_date, max_pages=100
        ):
            return pd.DataFrame(
                [
                    {
                        "ticker": ticker,
                        "session_end_date": "2025-01-02",
                        "settlement_price": 2600.0,
                        "volume": 100,
                    }
                ]
            )

    _, metadata = fetch_massive_canonical_history(
        Client(),
        _schema(),
        "GC",
        "2025-01-01",
        "2025-01-31",
        "2026-08-12T18:00:00Z",
    )
    assert metadata["exchange"] == "XCEC"
