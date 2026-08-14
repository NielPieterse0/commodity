import json

import pandas as pd
import pytest

from commodity.config import data_config
from commodity.market_data import DataContractViolation, validate_contract_history
from commodity.providers import MissingCredential


def _schema() -> dict:
    return data_config()["canonical_contract_schema"]


def test_databento_requires_environment_key(monkeypatch) -> None:
    from commodity.databento_futures_provider import DatabentoFuturesClient

    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    with pytest.raises(MissingCredential, match="DATABENTO_API_KEY"):
        DatabentoFuturesClient().list_schemas("GLBX.MDP3")


def test_databento_uses_basic_auth_without_query_key(monkeypatch) -> None:
    from commodity.databento_futures_provider import DatabentoFuturesClient

    class Response:
        status_code = 200
        def json(self):
            return ["statistics", "definition"]

    class Session:
        def __init__(self) -> None:
            self.kwargs = None
        def get(self, url, **kwargs):
            self.kwargs = kwargs
            return Response()

    monkeypatch.setenv("DATABENTO_API_KEY", "db-test-secret")
    session = Session()
    assert DatabentoFuturesClient(session=session).list_schemas("GLBX.MDP3") == [
        "statistics",
        "definition",
    ]
    assert session.kwargs["auth"] == ("db-test-secret", "")
    assert "db-test-secret" not in json.dumps(session.kwargs.get("params", {}))


def test_databento_metadata_probe_is_bounded_and_non_billable(monkeypatch) -> None:
    from commodity.databento_futures_provider import DatabentoFuturesClient

    class Response:
        status_code = 200
        def __init__(self, payload):
            self.payload = payload
        def json(self):
            return self.payload

    class Session:
        def __init__(self) -> None:
            self.calls = []
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if url.endswith("metadata.list_schemas"):
                return Response(["definition", "statistics", "ohlcv-1d"])
            if url.endswith("metadata.get_dataset_range"):
                return Response({"start": "2010-06-06T00:00:00Z", "end": "2026-08-13T00:00:00Z", "schema": {"statistics": {"start": "2010-06-06T00:00:00Z", "end": "2026-08-13T00:00:00Z"}}})
            if url.endswith("metadata.get_cost"):
                return Response(0.12)
            if url.endswith("metadata.get_record_count"):
                return Response(42)
            raise AssertionError(url)

    monkeypatch.setenv("DATABENTO_API_KEY", "db-test-secret")
    session = Session()
    report = DatabentoFuturesClient(session=session).probe_history(
        dataset="GLBX.MDP3",
        product_code="NG",
        start_trade_date="2025-01-02",
        end_trade_date="2025-01-03",
    )
    assert report["dataset"] == "GLBX.MDP3"
    assert report["parent_symbol"] == "NG.FUT"
    assert report["statistics_cost_usd"] == pytest.approx(0.12)
    assert report["statistics_record_count"] == 42
    assert all("timeseries.get_range" not in url for url, _ in session.calls)
    cost_call = next(
        kwargs
        for url, kwargs in session.calls
        if url.endswith("metadata.get_cost")
        and kwargs["params"]["schema"] == "statistics"
    )
    assert cost_call["params"]["symbols"] == "NG.FUT"
    assert cost_call["params"]["stype_in"] == "parent"
    assert cost_call["params"]["schema"] == "statistics"
    # Friday 2025-01-03 volume can publish on Sunday, so the request must span it.
    assert cost_call["params"]["end"] == "2025-01-07"


def test_databento_entitlement_errors_are_redacted(monkeypatch) -> None:
    from commodity.databento_futures_provider import (
        DatabentoApiError,
        DatabentoFuturesClient,
    )

    class Response:
        status_code = 403
        def json(self):
            return {"detail": "forbidden for db-test-secret"}

    class Session:
        def get(self, url, **kwargs):
            return Response()

    monkeypatch.setenv("DATABENTO_API_KEY", "db-test-secret")
    with pytest.raises(DatabentoApiError) as exc:
        DatabentoFuturesClient(session=Session()).list_schemas("GLBX.MDP3")
    assert "HTTP 403" in str(exc.value)
    assert "db-test-secret" not in str(exc.value)
    assert "forbidden" not in str(exc.value)


def test_databento_normalization_prefers_final_settlement_and_joins_cleared_volume() -> None:
    from commodity.databento_futures_provider import (
        normalize_databento_contract_history,
    )

    definitions = pd.DataFrame(
        [
            {"raw_symbol": "NGF25", "instrument_class": "F", "asset": "NG", "expiration": "2025-01-29T19:30:00Z", "exchange": "XNYM"},
            {"raw_symbol": "NGF25-NGG25", "instrument_class": "S", "asset": "NG", "expiration": "2025-01-29T19:30:00Z", "exchange": "XNYM"},
        ]
    )
    statistics = pd.DataFrame(
        [
            {"symbol": "NGF25", "stat_type": 3, "stat_flags": 0, "ts_ref": "2025-01-02T00:00:00Z", "ts_event": "2025-01-02T19:29:00Z", "price": 3.01},
            {"symbol": "NGF25", "stat_type": 3, "stat_flags": 1, "ts_ref": "2025-01-02T00:00:00Z", "ts_event": "2025-01-02T19:31:00Z", "price": 3.08},
            {"symbol": "NGF25", "stat_type": 6, "stat_flags": 0, "ts_ref": "2025-01-02T00:00:00Z", "ts_event": "2025-01-03T01:00:00Z", "quantity": 1234},
        ]
    )
    frame, metadata = normalize_databento_contract_history(
        definitions, statistics, "2026-08-13T12:00:00Z", product_code="NG"
    )
    row = frame.iloc[0]
    assert len(frame) == 1
    assert row["contract_id"] == "NGF25"
    assert row["settle"] == pytest.approx(3.08)
    assert row["volume"] == 1234
    assert row["trade_date"] == pd.Timestamp("2025-01-02", tz="UTC")
    assert row["available_at"] == pd.Timestamp("2025-01-03T01:00:00Z")
    assert metadata["price_semantics"] == "cme_final_settlement_from_databento_statistics"
    validate_contract_history(frame, _schema())


def test_databento_normalization_drops_invalid_cleared_volume_sentinel() -> None:
    from commodity.databento_futures_provider import (
        normalize_databento_contract_history,
    )

    definitions = pd.DataFrame([
        {"raw_symbol": "NGF25", "instrument_class": "F", "asset": "NG", "expiration": "2025-01-29T19:30:00Z", "exchange": "XNYM"}
    ])
    statistics = pd.DataFrame([
        {"symbol": "NGF25", "stat_type": 3, "stat_flags": 1, "ts_ref": "2025-01-02T00:00:00Z", "ts_event": "2025-01-02T19:31:00Z", "price": 3.08},
        {"symbol": "NGF25", "stat_type": 6, "stat_flags": 0, "ts_ref": "2025-01-02T00:00:00Z", "ts_event": "2025-01-03T01:00:00Z", "quantity": 9223372036854775807},
    ])
    frame, _ = normalize_databento_contract_history(
        definitions, statistics, "2026-08-13T12:00:00Z", product_code="NG"
    )
    assert pd.isna(frame.iloc[0]["volume"])
    assert frame.iloc[0]["available_at"] == pd.Timestamp("2025-01-02T19:31:00Z")


def test_databento_normalization_requires_provider_product_and_exchange_identity() -> None:
    from commodity.databento_futures_provider import (
        normalize_databento_contract_history,
    )

    definitions = pd.DataFrame([
        {"raw_symbol": "NGF25", "instrument_class": "F", "expiration": "2025-01-29T19:30:00Z"}
    ])
    statistics = pd.DataFrame([
        {"symbol": "NGF25", "stat_type": 3, "stat_flags": 1, "ts_ref": "2025-01-02T00:00:00Z", "ts_event": "2025-01-02T19:31:00Z", "price": 3.08}
    ])
    with pytest.raises(DataContractViolation, match="asset.*exchange|exchange.*asset"):
        normalize_databento_contract_history(
            definitions, statistics, "2026-08-13T12:00:00Z", product_code="NG"
        )


def test_databento_normalization_rejects_intraday_settlement_as_daily_final() -> None:
    from commodity.databento_futures_provider import (
        normalize_databento_contract_history,
    )

    definitions = pd.DataFrame([
        {"raw_symbol": "NGF25", "instrument_class": "F", "asset": "NG", "expiration": "2025-01-29T19:30:00Z", "exchange": "XNYM"}
    ])
    statistics = pd.DataFrame([
        {"symbol": "NGF25", "stat_type": 3, "stat_flags": 9, "ts_ref": "2025-01-02T00:00:00Z", "ts_event": "2025-01-02T18:00:00Z", "price": 3.01}
    ])
    with pytest.raises(DataContractViolation, match="final settlement"):
        normalize_databento_contract_history(
            definitions, statistics, "2026-08-13T12:00:00Z", product_code="NG"
        )


def test_databento_normalization_fails_closed_without_final_settlement() -> None:
    from commodity.databento_futures_provider import (
        normalize_databento_contract_history,
    )

    definitions = pd.DataFrame([
        {"raw_symbol": "NGF25", "instrument_class": "F", "asset": "NG", "expiration": "2025-01-29T19:30:00Z", "exchange": "XNYM"}
    ])
    statistics = pd.DataFrame([
        {"symbol": "NGF25", "stat_type": 3, "stat_flags": 0, "ts_ref": "2025-01-02T00:00:00Z", "ts_event": "2025-01-02T19:29:00Z", "price": 3.01}
    ])
    with pytest.raises(DataContractViolation, match="final settlement"):
        normalize_databento_contract_history(
            definitions, statistics, "2026-08-13T12:00:00Z", product_code="NG"
        )


def test_databento_timeseries_request_is_parent_futures_json_and_secret_free(monkeypatch) -> None:
    from commodity.databento_futures_provider import DatabentoFuturesClient

    class Response:
        status_code = 200
        text = '{"hd":{"ts_event":"2025-01-02T19:31:00Z","instrument_id":42},"symbol":"NGF25","stat_type":3}\n'

    class Session:
        def post(self, url, **kwargs):
            self.url = url
            self.kwargs = kwargs
            return Response()

    monkeypatch.setenv("DATABENTO_API_KEY", "db-test-secret")
    session = Session()
    frame = DatabentoFuturesClient(session=session).fetch_statistics(
        "NG", "2025-01-02", "2025-01-03"
    )
    assert list(frame["symbol"]) == ["NGF25"]
    assert frame.iloc[0]["ts_event"] == "2025-01-02T19:31:00Z"
    assert frame.iloc[0]["instrument_id"] == 42
    assert session.url.endswith("/timeseries.get_range")
    assert session.kwargs["auth"] == ("db-test-secret", "")
    assert session.kwargs["data"]["symbols"] == "NG.FUT"
    assert session.kwargs["data"]["stype_in"] == "parent"
    assert session.kwargs["data"]["stype_out"] == "instrument_id"
    assert session.kwargs["data"]["schema"] == "statistics"
    assert session.kwargs["data"]["end"] == "2025-01-07"
    assert "db-test-secret" not in json.dumps(session.kwargs["data"])


def test_databento_cost_cap_blocks_billable_fetch() -> None:
    from commodity.databento_futures_provider import fetch_databento_canonical_history

    class Client:
        def probe_history(self, *args, **kwargs):
            return {
                "schemas": ["definition", "statistics"],
                "estimated_total_cost_usd": 1.01,
            }

        def fetch_definitions(self, *args, **kwargs):
            raise AssertionError("billable fetch must not run")

        def fetch_statistics(self, *args, **kwargs):
            raise AssertionError("billable fetch must not run")

    with pytest.raises(DataContractViolation, match="exceeds bounded cap"):
        fetch_databento_canonical_history(
            Client(), _schema(), "NG", "2025-01-02", "2025-01-03",
            "2026-08-13T12:00:00Z", max_cost_usd=1.0,
        )


def test_databento_record_cap_blocks_large_flat_rate_fetch() -> None:
    from commodity.databento_futures_provider import fetch_databento_canonical_history

    class Client:
        def probe_history(self, *args, **kwargs):
            return {
                "schemas": ["definition", "statistics"],
                "estimated_total_cost_usd": 0.0,
                "definition_record_count": 100,
                "statistics_record_count": 5000,
            }

        def fetch_definitions(self, *args, **kwargs):
            raise AssertionError("large fetch must not run")

        def fetch_statistics(self, *args, **kwargs):
            raise AssertionError("large fetch must not run")

    with pytest.raises(DataContractViolation, match="record count"):
        fetch_databento_canonical_history(
            Client(), _schema(), "NG", "2025-01-02", "2025-01-03",
            "2026-08-13T12:00:00Z", max_cost_usd=1.0, max_records=1000,
        )


def test_databento_prefers_capture_timestamp_for_availability() -> None:
    from commodity.databento_futures_provider import (
        normalize_databento_contract_history,
    )

    definitions = pd.DataFrame([
        {"raw_symbol": "NGF25", "instrument_class": "F", "asset": "NG", "expiration": "2025-01-29T19:30:00Z", "exchange": "XNYM"}
    ])
    statistics = pd.DataFrame([
        {"symbol": "NGF25", "stat_type": 3, "stat_flags": 1, "ts_ref": "2025-01-02T00:00:00Z", "ts_event": "2025-01-02T19:31:00Z", "ts_recv": "2025-01-02T19:31:00.125Z", "price": 3.08}
    ])
    frame, _ = normalize_databento_contract_history(
        definitions, statistics, "2026-08-13T12:00:00Z", product_code="NG"
    )
    assert frame.iloc[0]["available_at"] == pd.Timestamp("2025-01-02T19:31:00.125Z")


def test_databento_capture_archive_is_rank_bounded_and_secret_free(tmp_path) -> None:
    from commodity.databento_futures_provider import DatabentoFuturesProvider

    class Client:
        def probe_history(self, *args, **kwargs):
            return {
                "dataset": "GLBX.MDP3",
                "product_code": "NG",
                "parent_symbol": "NG.FUT",
                "schemas": ["definition", "statistics"],
                "dataset_range": {"start": "2010-06-06T00:00:00Z"},
                "definition_cost_usd": 0.01,
                "statistics_cost_usd": 0.01,
                "estimated_total_cost_usd": 0.02,
                "definition_record_count": 2,
                "statistics_record_count": 4,
                "metadata_only": True,
            }

        def fetch_definitions(self, *args, **kwargs):
            return pd.DataFrame([
                {"raw_symbol": "NGF25", "instrument_class": "F", "asset": "NG", "expiration": "2025-01-29T19:30:00Z", "exchange": "XNYM"},
                {"raw_symbol": "NGG25", "instrument_class": "F", "asset": "NG", "expiration": "2025-02-26T19:30:00Z", "exchange": "XNYM"},
            ])

        def fetch_statistics(self, *args, **kwargs):
            return pd.DataFrame([
                {"symbol": "NGF25", "stat_type": 3, "stat_flags": 1, "ts_ref": "2025-01-02T00:00:00Z", "ts_event": "2025-01-02T19:31:00Z", "price": 3.08},
                {"symbol": "NGF25", "stat_type": 6, "stat_flags": 0, "ts_ref": "2025-01-02T00:00:00Z", "ts_event": "2025-01-03T01:00:00Z", "quantity": 100},
                {"symbol": "NGG25", "stat_type": 3, "stat_flags": 1, "ts_ref": "2025-01-02T00:00:00Z", "ts_event": "2025-01-02T19:31:00Z", "price": 3.18},
                {"symbol": "NGG25", "stat_type": 6, "stat_flags": 0, "ts_ref": "2025-01-02T00:00:00Z", "ts_event": "2025-01-03T01:00:00Z", "quantity": 90},
            ])

    manifest_path = DatabentoFuturesProvider(client=Client()).capture_archive(
        _schema(), "NG", "2025-01-02", "2025-01-02", "2026-08-13T12:00:00Z",
        tmp_path, "bounded", max_contracts=1,
    )
    canonical = pd.read_csv(manifest_path.parent / "canonical.csv")
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert (manifest_path.parent / "definitions.csv").is_file()
    assert (manifest_path.parent / "statistics.csv").is_file()
    assert list(canonical["contract_id"]) == ["NGF25"]
    assert manifest["request"]["max_contracts"] == 1
    assert manifest["canonical_evidence"] is False
    assert manifest["licensing_rights_verified"] is False
    assert manifest["preflight"]["metadata_only"] is True
    assert manifest["preflight"]["estimated_total_cost_usd"] == pytest.approx(0.02)
    assert "DATABENTO_API_KEY" not in manifest_text
    assert "db-" not in manifest_text


def test_databento_factory_satisfies_provider_surface() -> None:
    from commodity.databento_futures_provider import create_provider

    config = data_config()
    provider = create_provider()
    assert callable(provider.fetch_contract_history)
    assert callable(provider.capture_archive)
    assert provider.dataset == "GLBX.MDP3"
    assert provider.max_auto_cost_usd == pytest.approx(1.0)
    assert provider.max_auto_records == 50_000
    assert config["sources"]["databento_henry_hub_probe"]["provider"] == "databento_futures"
    assert config["sources"]["market_canonical"]["provider"] == "massive_futures"


def test_existing_full_history_acquisition_remains_quarantined_after_integrity_repair() -> None:
    config = data_config()
    provider = config["providers"]["databento_futures"]
    source = config["sources"]["databento_henry_hub_probe"]
    assert provider["account_probe_status"] == "full_history_acquired_integrity_verified_quarantined"
    assert source["status"] == "acquired_quarantined_integrity_complete"
    assert source["acquisition_governance_status"] == "quarantined_pre_governance_acquisition"
    assert source["integrity_status"] == "complete"
    assert source["integrity_verified_complete_through"] == "2026-08-12"
    assert source["paid_reacquisition_approved"] is False
    assert source["account_history_validated"] is True
    assert source["licensing_rights_verified"] is False
    assert source["backtest_evidence_allowed"] is False
    assert source["canonical_market_source"] is False
    assert source["quarantine_evidence"].endswith(
        "databento-full-history-acquisition/evidence.json"
    )
    assert source["repair_evidence"].endswith(
        "databento-full-history-acquisition/repair-evidence.json"
    )
