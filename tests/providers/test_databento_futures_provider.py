import hashlib
import json

import pandas as pd
import pytest

from commodity.config import data_config
from commodity.market_data import DataContractViolation, validate_contract_history
from commodity.providers import MissingCredential


def _schema() -> dict:
    return data_config()["canonical_contract_schema"]


def test_databento_requires_environment_key(monkeypatch) -> None:
    from commodity.providers.databento_futures import DatabentoFuturesClient

    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    with pytest.raises(MissingCredential, match="DATABENTO_API_KEY"):
        DatabentoFuturesClient().list_schemas("GLBX.MDP3")


def test_databento_uses_basic_auth_without_query_key(monkeypatch) -> None:
    from commodity.providers.databento_futures import DatabentoFuturesClient

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
    from commodity.providers.databento_futures import DatabentoFuturesClient

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


def test_databento_phase7_triple_quote_is_metadata_only(monkeypatch) -> None:
    from commodity.providers.databento_futures import DatabentoFuturesClient

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
                return Response({"start": "2010-06-06T00:00:00Z", "end": "2026-09-12T03:39:57Z"})
            if url.endswith("metadata.get_cost"):
                return Response({"definition": 0.13, "statistics": 0.05, "ohlcv-1d": 0.06}[kwargs["params"]["schema"]])
            if url.endswith("metadata.get_record_count"):
                return Response({"definition": 158461, "statistics": 621221, "ohlcv-1d": 6147}[kwargs["params"]["schema"]])
            raise AssertionError(url)

    monkeypatch.setenv("DATABENTO_API_KEY", "db-test-secret")
    session = Session()
    report = DatabentoFuturesClient(session=session).quote_phase7_partition(
        "GLBX.MDP3", "NG", "2026-08-13", "2026-09-11"
    )
    assert report["metadata_only"] is True
    assert report["required_schemas"] == ["definition", "statistics", "ohlcv-1d"]
    assert report["estimated_total_cost_usd"] == pytest.approx(0.24)
    assert report["schemas"]["ohlcv-1d"]["record_count"] == 6147
    assert all("timeseries.get_range" not in url for url, _ in session.calls)
    assert {
        kwargs["params"]["schema"]
        for url, kwargs in session.calls
        if url.endswith("metadata.get_cost")
    } == {"definition", "statistics", "ohlcv-1d"}


def test_databento_entitlement_errors_are_redacted(monkeypatch) -> None:
    from commodity.providers.databento_futures import (
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
    from commodity.providers.databento_futures import (
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
    assert row["contract_id"] == "NGF25@2025-01-29"
    assert row["settle"] == pytest.approx(3.08)
    assert row["volume"] == 1234
    assert row["trade_date"] == pd.Timestamp("2025-01-02", tz="UTC")
    assert row["available_at"] == pd.Timestamp("2025-01-03T01:00:00Z")
    assert metadata["price_semantics"] == "cme_final_settlement_from_databento_statistics"
    validate_contract_history(frame, _schema())


def test_databento_normalization_drops_invalid_cleared_volume_sentinel() -> None:
    from commodity.providers.databento_futures import (
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
    from commodity.providers.databento_futures import (
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
    from commodity.providers.databento_futures import (
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
    from commodity.providers.databento_futures import (
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


def test_databento_normalization_uses_latest_nonpreliminary_legacy_settlement() -> None:
    from commodity.providers.databento_futures import (
        normalize_databento_contract_history,
    )

    definitions = pd.DataFrame([
        {"raw_symbol": "NGF11", "instrument_class": "F", "asset": "NG", "expiration": "2010-12-28T19:30:00Z", "exchange": "XNYM"}
    ])
    statistics = pd.DataFrame([
        {"symbol": "NGF11", "stat_type": 3, "stat_flags": 100, "ts_ref": "2010-12-20T00:00:00Z", "ts_event": "2010-12-20T19:00:00Z", "price": 4.01},
        {"symbol": "NGF11", "stat_type": 3, "stat_flags": 0, "ts_ref": "2010-12-20T00:00:00Z", "ts_event": "2010-12-20T19:31:00Z", "price": 4.08},
    ])
    frame, metadata = normalize_databento_contract_history(
        definitions, statistics, "2026-08-13T12:00:00Z", product_code="NG"
    )
    assert frame.iloc[0]["settle"] == pytest.approx(4.08)
    selection = metadata["settlement_selection"]
    assert selection["legacy_selected_groups"] == 1
    assert selection["legacy_dropped_known_preliminary_groups"] == 0


def test_databento_normalization_ignores_later_legacy_preliminary_after_final() -> None:
    from commodity.providers.databento_futures import (
        normalize_databento_contract_history,
    )

    definitions = pd.DataFrame([
        {"raw_symbol": "NGF11", "instrument_class": "F", "asset": "NG", "expiration": "2010-12-28T19:30:00Z", "exchange": "XNYM"}
    ])
    statistics = pd.DataFrame([
        {"symbol": "NGF11", "stat_type": 3, "stat_flags": 0, "ts_ref": "2010-12-20T00:00:00Z", "ts_event": "2010-12-20T19:31:00Z", "price": 4.08},
        {"symbol": "NGF11", "stat_type": 3, "stat_flags": 100, "ts_ref": "2010-12-20T00:00:00Z", "ts_event": "2010-12-20T20:00:00Z", "price": 4.01},
    ])
    frame, _ = normalize_databento_contract_history(
        definitions, statistics, "2026-08-13T12:00:00Z", product_code="NG"
    )
    assert frame.iloc[0]["settle"] == pytest.approx(4.08)


def test_databento_normalization_drops_legacy_group_with_only_known_preliminary() -> None:
    from commodity.providers.databento_futures import (
        normalize_databento_contract_history,
    )

    definitions = pd.DataFrame([
        {"raw_symbol": "NGF11", "instrument_class": "F", "asset": "NG", "expiration": "2010-12-28T19:30:00Z", "exchange": "XNYM"}
    ])
    statistics = pd.DataFrame([
        {"symbol": "NGF11", "stat_type": 3, "stat_flags": 100, "ts_ref": "2010-12-20T00:00:00Z", "ts_event": "2010-12-20T19:00:00Z", "price": 4.01}
    ])
    with pytest.raises(DataContractViolation, match="final settlement"):
        normalize_databento_contract_history(
            definitions, statistics, "2026-08-13T12:00:00Z", product_code="NG"
        )


def test_databento_timeseries_request_is_parent_futures_json_and_secret_free(monkeypatch) -> None:
    from commodity.providers.databento_futures import DatabentoFuturesClient

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
    from commodity.providers.databento_futures import fetch_databento_canonical_history

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


def test_databento_default_fetch_is_disabled_until_cost_is_explicitly_approved() -> None:
    from commodity.providers.databento_futures import fetch_databento_canonical_history

    class Client:
        def probe_history(self, *args, **kwargs):
            raise AssertionError("quote/fetch must not run with zero spend authority")

    with pytest.raises(ValueError, match="max_cost_usd must be positive"):
        fetch_databento_canonical_history(
            Client(), _schema(), "NG", "2025-01-02", "2025-01-03",
            "2026-08-13T12:00:00Z",
        )


def test_databento_record_cap_blocks_large_flat_rate_fetch() -> None:
    from commodity.providers.databento_futures import fetch_databento_canonical_history

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
    from commodity.providers.databento_futures import (
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
    from commodity.providers.databento_futures import DatabentoFuturesProvider

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

    manifest_path = DatabentoFuturesProvider(
        client=Client(), max_auto_cost_usd=0.02
    ).capture_archive(
        _schema(), "NG", "2025-01-02", "2025-01-02", "2026-08-13T12:00:00Z",
        tmp_path, "bounded", max_contracts=1,
    )
    canonical = pd.read_csv(manifest_path.parent / "canonical.csv")
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert (manifest_path.parent / "definitions.csv").is_file()
    assert (manifest_path.parent / "statistics.csv").is_file()
    assert list(canonical["contract_id"]) == ["NGF25@2025-01-29"]
    assert manifest["request"]["max_contracts"] == 1
    assert manifest["canonical_evidence"] is False
    assert manifest["licensing_rights_verified"] is False
    assert manifest["preflight"]["metadata_only"] is True
    assert manifest["preflight"]["estimated_total_cost_usd"] == pytest.approx(0.02)
    assert "DATABENTO_API_KEY" not in manifest_text
    assert "db-" not in manifest_text


def test_databento_factory_satisfies_provider_surface() -> None:
    from commodity.providers.databento_futures import create_provider

    config = data_config()
    provider = create_provider()
    assert callable(provider.fetch_contract_history)
    assert callable(provider.capture_archive)
    assert provider.dataset == "GLBX.MDP3"
    assert provider.max_auto_cost_usd == pytest.approx(0.0)
    assert provider.max_auto_records == 50_000
    assert config["sources"]["databento_henry_hub"]["provider"] == "databento_futures"
    assert config["canonical_market_source_id"] == "databento_henry_hub"
    assert config["sources"][config["canonical_market_source_id"]]["provider"] == "databento_futures"


def test_existing_full_history_acquisition_is_approved_for_private_research() -> None:
    config = data_config()
    provider = config["providers"]["databento_futures"]
    source = config["sources"]["databento_henry_hub"]
    assert provider["account_probe_status"] == "full_history_acquired_integrity_verified_research_approved"
    assert source["status"] == "acquired_integrity_complete_research_approved"
    assert source["acquisition_governance_status"] == "operator_approved_existing_purchase_private_research"
    assert source["integrity_status"] == "complete"
    assert source["integrity_verified_complete_through"] == "2026-08-12"
    assert source["paid_reacquisition_approved"] is False
    assert source["account_history_validated"] is True
    assert source["licensing_rights_verified"] is True
    assert source["backtest_evidence_allowed"] is True
    assert source["canonical_market_source"] is True
    assert "no redistribution authority" in source["approved_use_scope"]
    assert source["quarantine_evidence"].endswith(
        "databento-full-history-acquisition/evidence.json"
    )
    assert source["repair_evidence"].endswith(
        "databento-full-history-acquisition/repair-evidence.json"
    )
    assert source["offline_decode_status"] == "validated_preserved_2015_pair"
    assert source["offline_decode_evidence"].endswith(
        "databento-offline-dbn/evidence.json"
    )


def _dbn_bytes(schema_name: str) -> bytes:
    import databento_dbn as dbn

    ts = 1735776000000000000
    schema = dbn.Schema.from_str(schema_name)
    metadata = dbn.Metadata(
        dataset="GLBX.MDP3",
        start=ts,
        stype_in=dbn.SType.INSTRUMENT_ID,
        stype_out=dbn.SType.INSTRUMENT_ID,
        schema=schema,
        symbols=["42"],
        end=ts + 86400 * 10**9,
    )
    if schema_name == "definition":
        record = dbn.InstrumentDefMsg(
            publisher_id=1,
            instrument_id=42,
            ts_event=ts,
            ts_recv=ts,
            min_price_increment=1_000_000,
            display_factor=1_000_000_000,
            raw_symbol="NGF25",
            asset="NG",
            security_type="FUT",
            instrument_class=dbn.InstrumentClass.FUTURE,
            security_update_action=dbn.SecurityUpdateAction.ADD,
            expiration=ts + 30 * 86400 * 10**9,
            exchange="XNYM",
        )
    elif schema_name == "statistics":
        record = dbn.StatMsg(
            publisher_id=1,
            instrument_id=42,
            ts_event=ts + 100,
            ts_recv=ts + 200,
            ts_ref=ts,
            price=3_080_000_000,
            quantity=dbn.UNDEF_STAT_QUANTITY,
            stat_type=dbn.StatType.SETTLEMENT_PRICE,
            stat_flags=1,
        )
    elif schema_name == "ohlcv-1d":
        record = dbn.OHLCVMsg(
            rtype=dbn.RType.OHLCV_1D.value,
            publisher_id=1,
            instrument_id=42,
            ts_event=ts,
            open=3_000_000_000,
            high=3_100_000_000,
            low=2_900_000_000,
            close=3_050_000_000,
            volume=123,
        )
    else:
        raise AssertionError(schema_name)
    return metadata.encode() + bytes(record)


def test_databento_offline_decoder_reads_definition_and_compressed_ohlcv(tmp_path) -> None:
    import zstandard

    from commodity.providers.databento_futures import decode_databento_dbn_file

    definition_path = tmp_path / "sample.definition.dbn"
    definition_path.write_bytes(_dbn_bytes("definition"))
    definition, provenance = decode_databento_dbn_file(
        definition_path, expected_schema="definition"
    )
    assert definition.iloc[0]["raw_symbol"] == "NGF25"
    assert definition.iloc[0]["instrument_id"] == 42
    assert provenance["schema"] == "definition"
    assert provenance["source_sha256"] == hashlib.sha256(definition_path.read_bytes()).hexdigest()

    ohlcv_path = tmp_path / "sample.ohlcv-1d.dbn.zst"
    ohlcv_path.write_bytes(zstandard.ZstdCompressor().compress(_dbn_bytes("ohlcv-1d")))
    ohlcv, provenance = decode_databento_dbn_file(
        ohlcv_path, expected_schema="ohlcv-1d"
    )
    assert ohlcv.iloc[0]["close"] == pytest.approx(3.05)
    assert ohlcv.iloc[0]["volume"] == 123
    assert provenance["schema"] == "ohlcv-1d"


def test_databento_offline_canonicalization_preserves_exact_artifact_provenance(tmp_path) -> None:
    import zstandard

    from commodity.providers.databento_futures import canonicalize_databento_dbn_history

    definition_dir = tmp_path / "definition" / "GLBX-TEST-DEFINITION"
    statistics_dir = tmp_path / "statistics" / "GLBX-TEST-STATISTICS"
    definition_dir.mkdir(parents=True)
    statistics_dir.mkdir(parents=True)
    definition_path = definition_dir / "sample.definition.dbn.zst"
    statistics_path = statistics_dir / "sample.statistics.dbn.zst"
    compressor = zstandard.ZstdCompressor()
    definition_path.write_bytes(compressor.compress(_dbn_bytes("definition")))
    statistics_path.write_bytes(compressor.compress(_dbn_bytes("statistics")))
    definition_metadata = {
        "job_id": "GLBX-TEST-DEFINITION",
        "query": {"dataset": "GLBX.MDP3", "schema": "definition"},
    }
    statistics_metadata = {
        "job_id": "GLBX-TEST-STATISTICS",
        "query": {"dataset": "GLBX.MDP3", "schema": "statistics"},
    }
    (definition_dir / "metadata.json").write_text(json.dumps(definition_metadata), encoding="utf-8")
    (statistics_dir / "metadata.json").write_text(json.dumps(statistics_metadata), encoding="utf-8")

    frame, metadata = canonicalize_databento_dbn_history(
        definition_path,
        statistics_path,
        schema=_schema(),
        product_code="NG",
        retrieved_at="2026-08-14T12:00:00Z",
    )
    assert list(frame["contract_id"]) == ["NGF25@2025-02-01"]
    assert frame.iloc[0]["settle"] == pytest.approx(3.08)
    assert frame.iloc[0]["available_at"] == pd.Timestamp(
        "2025-01-02T00:00:00.000000200Z"
    )
    assert metadata["offline_decode"] is True
    assert metadata["canonical_evidence"] is False
    artifacts = {item["schema"]: item for item in metadata["source_artifacts"]}
    assert artifacts["definition"]["source_sha256"] == hashlib.sha256(
        definition_path.read_bytes()
    ).hexdigest()
    assert artifacts["statistics"]["source_sha256"] == hashlib.sha256(
        statistics_path.read_bytes()
    ).hexdigest()
    assert artifacts["definition"]["provider_job_id"] == "GLBX-TEST-DEFINITION"
    assert artifacts["statistics"]["provider_job_id"] == "GLBX-TEST-STATISTICS"
    assert artifacts["definition"]["provider_metadata_sha256"] == hashlib.sha256(
        (definition_dir / "metadata.json").read_bytes()
    ).hexdigest()
    assert artifacts["statistics"]["provider_metadata_sha256"] == hashlib.sha256(
        (statistics_dir / "metadata.json").read_bytes()
    ).hexdigest()


def test_databento_offline_archive_uses_definition_history_across_file_boundaries(
    monkeypatch,
) -> None:
    import commodity.providers.databento_futures as provider

    definitions = {
        "2010.definition": pd.DataFrame(
            [
                {
                    "instrument_id": 42,
                    "raw_symbol": "NGF11",
                    "ts_recv": "2010-12-01T00:00:00Z",
                    "ts_event": "2010-12-01T00:00:00Z",
                    "instrument_class": "F",
                    "asset": "NG",
                    "expiration": "2011-01-27T19:30:00Z",
                    "activation": "2010-10-01T00:00:00Z",
                    "exchange": "XNYM",
                }
            ]
        ),
        "2011.definition": pd.DataFrame(
            [
                {
                    "instrument_id": 43,
                    "raw_symbol": "NGG11",
                    "ts_recv": "2011-01-02T00:00:00Z",
                    "ts_event": "2011-01-02T00:00:00Z",
                    "instrument_class": "F",
                    "asset": "NG",
                    "expiration": "2011-02-24T19:30:00Z",
                    "activation": "2010-11-01T00:00:00Z",
                    "exchange": "XNYM",
                }
            ]
        ),
    }
    statistics = {
        "2010.statistics": pd.DataFrame(
            [
                {
                    "instrument_id": 42,
                    "ts_event": "2010-12-31T19:31:00Z",
                    "ts_recv": "2010-12-31T19:31:01Z",
                    "ts_ref": "2010-12-31T00:00:00Z",
                    "price": 4.40,
                    "quantity": 0,
                    "stat_type": 3,
                    "stat_flags": 0,
                },
                {
                    "instrument_id": 42,
                    "ts_event": "2010-12-31T20:00:00Z",
                    "ts_recv": "2010-12-31T20:00:01Z",
                    "ts_ref": "2010-12-31T00:00:00Z",
                    "price": 0.0,
                    "quantity": 100,
                    "stat_type": 6,
                    "stat_flags": 0,
                },
                {
                    "instrument_id": 43,
                    "ts_event": "2010-12-30T19:31:00Z",
                    "ts_recv": "2010-12-30T19:31:01Z",
                    "ts_ref": "2010-12-30T00:00:00Z",
                    "price": 99.0,
                    "quantity": 0,
                    "stat_type": 3,
                    "stat_flags": 0,
                },
                {
                    "instrument_id": 42,
                    "ts_event": "2010-12-29T19:31:00Z",
                    "ts_recv": "2010-12-29T19:31:01Z",
                    "ts_ref": 2**64 - 1,
                    "price": 99.0,
                    "quantity": 0,
                    "stat_type": 3,
                    "stat_flags": 0,
                },
            ]
        ),
        "2011.statistics": pd.DataFrame(
            [
                {
                    "instrument_id": 42,
                    "ts_event": "2011-01-03T19:31:00Z",
                    "ts_recv": "2011-01-03T19:31:01Z",
                    "ts_ref": "2011-01-03T00:00:00Z",
                    "price": 4.45,
                    "quantity": 0,
                    "stat_type": 3,
                    "stat_flags": 0,
                },
                {
                    "instrument_id": 42,
                    "ts_event": "2011-01-03T20:00:00Z",
                    "ts_recv": "2011-01-03T20:00:01Z",
                    "ts_ref": "2011-01-03T00:00:00Z",
                    "price": 0.0,
                    "quantity": 110,
                    "stat_type": 6,
                    "stat_flags": 0,
                },
            ]
        ),
    }

    def fake_definitions(path, **_kwargs):
        name = str(path)
        frame = next(value for key, value in definitions.items() if key in name)
        return frame.copy(), {
            "dataset": "GLBX.MDP3",
            "schema": "definition",
            "source_file": name,
            "source_sha256": hashlib.sha256(name.encode()).hexdigest(),
        }

    def fake_statistics(path, **_kwargs):
        name = str(path)
        frame = next(value for key, value in statistics.items() if key in name)
        return frame.copy(), {
            "dataset": "GLBX.MDP3",
            "schema": "statistics",
            "source_file": name,
            "source_sha256": hashlib.sha256(name.encode()).hexdigest(),
        }

    mappings = {
        "2010.statistics": {
            "NGF11": [
                {"start_date": "2010-10-01", "end_date": "2011-01-01", "symbol": "42"}
            ],
            "NG:WS F11-G11": [
                {"start_date": "2010-10-01", "end_date": "2011-01-01", "symbol": "43"}
            ],
        },
        "2011.statistics": {
            "NGF11": [
                {"start_date": "2011-01-01", "end_date": "2011-01-28", "symbol": "42"}
            ]
        },
    }

    def fake_mappings(path, **_kwargs):
        name = str(path)
        return next(value for key, value in mappings.items() if key in name)

    monkeypatch.setattr(provider, "decode_databento_dbn_file", fake_definitions)
    monkeypatch.setattr(provider, "_decode_databento_canonical_statistics", fake_statistics)
    monkeypatch.setattr(provider, "_read_databento_dbn_symbol_mappings", fake_mappings)
    frame, metadata = provider.canonicalize_databento_dbn_archive(
        ["2010.definition", "2011.definition"],
        ["2010.statistics", "2011.statistics"],
        schema=_schema(),
        product_code="NG",
        retrieved_at="2026-08-14T12:00:00Z",
    )
    assert frame[["trade_date", "contract_id", "volume"]].to_dict("records") == [
        {
            "trade_date": pd.Timestamp("2010-12-31T00:00:00Z"),
            "contract_id": "NGF11@2011-01-27",
            "volume": 100,
        },
        {
            "trade_date": pd.Timestamp("2011-01-03T00:00:00Z"),
            "contract_id": "NGF11@2011-01-27",
            "volume": 110,
        },
    ]
    assert metadata["offline_decode"] is True
    assert len(metadata["source_artifacts"]) == 4
    identity_filters = metadata["identity_window_filter_by_source"]
    assert identity_filters[0]["metadata_mapping_intervals"] == 2
    assert identity_filters[0]["resolved_statistics_rows"] == 4
    assert identity_filters[0]["excluded_non_target_symbol"] == 1
    assert identity_filters[0]["dropped_invalid_reference_timestamp"] == 1
    assert identity_filters[0]["dropped_outside_contract_lifetime"] == 0


def test_databento_offline_decoder_rejects_mismatched_adjacent_job_metadata(tmp_path) -> None:
    from commodity.providers.databento_futures import (
        DatabentoOfflineDecodeError,
        decode_databento_dbn_file,
    )

    job_dir = tmp_path / "GLBX-TEST-DEFINITION"
    job_dir.mkdir()
    definition_path = job_dir / "sample.definition.dbn"
    definition_path.write_bytes(_dbn_bytes("definition"))
    (job_dir / "metadata.json").write_text(
        json.dumps(
            {
                "job_id": "GLBX-TEST-DEFINITION",
                "query": {"dataset": "GLBX.MDP3", "schema": "statistics"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(DatabentoOfflineDecodeError, match="job metadata does not match"):
        decode_databento_dbn_file(definition_path, expected_schema="definition")


def test_databento_metadata_mapping_resolves_instrument_id_by_event_date() -> None:
    from commodity.providers.databento_futures import resolve_databento_metadata_symbols

    mappings = {
        "NG:WS N6-J7": [
            {"start_date": "2016-05-12", "end_date": "2016-07-19", "symbol": "10341"}
        ],
        "NGM35": [
            {"start_date": "2022-11-15", "end_date": "2023-01-01", "symbol": "10341"}
        ],
    }
    observations = pd.DataFrame(
        [
            {"instrument_id": 10341, "ts_event": "2016-06-01T19:31:00Z"},
            {"instrument_id": 10341, "ts_event": "2022-12-01T19:31:00Z"},
        ]
    )
    resolved = resolve_databento_metadata_symbols(observations, mappings)
    assert resolved["symbol"].tolist() == ["NG:WS N6-J7", "NGM35"]


def test_databento_predefinition_target_row_is_excluded_only_before_activation() -> None:
    from commodity.providers.databento_futures import (
        _filter_resolved_target_observations,
    )

    definitions = pd.DataFrame(
        [
            {
                "raw_symbol": "NGF30",
                "instrument_class": "F",
                "asset": "NG",
                "ts_event": "2017-11-15T00:02:03.537Z",
                "ts_recv": "2017-11-15T00:02:03.547Z",
                "activation": "2017-11-29T00:00:00Z",
            }
        ]
    )
    observations = pd.DataFrame(
        [
            {
                "instrument_id": 37857,
                "symbol": "NGF30",
                "ts_event": "2017-11-15T00:02:03.537Z",
                "ts_ref": "2017-11-14T00:00:00Z",
            }
        ]
    )
    filtered, diagnostics = _filter_resolved_target_observations(
        definitions, observations, product_code="NG"
    )
    assert filtered.empty
    assert diagnostics == {
        "excluded_non_target_symbol": 0,
        "excluded_before_target_activation": 1,
    }


def test_databento_predefinition_target_row_fails_closed_after_activation() -> None:
    from commodity.providers.databento_futures import (
        _filter_resolved_target_observations,
    )

    definitions = pd.DataFrame(
        [
            {
                "raw_symbol": "NGF30",
                "instrument_class": "F",
                "asset": "NG",
                "ts_recv": "2017-11-15T00:02:03.547Z",
                "activation": "2017-11-01T00:00:00Z",
            }
        ]
    )
    observations = pd.DataFrame(
        [
            {
                "instrument_id": 37857,
                "symbol": "NGF30",
                "ts_event": "2017-11-15T00:02:03.537Z",
                "ts_ref": "2017-11-14T00:00:00Z",
            }
        ]
    )
    with pytest.raises(DataContractViolation, match="after activation"):
        _filter_resolved_target_observations(definitions, observations, product_code="NG")


def test_databento_metadata_mapping_filters_post_target_spread_reuse() -> None:
    from commodity.providers.databento_futures import (
        map_databento_resolved_symbols_to_target_definitions,
        resolve_databento_metadata_symbols,
    )

    mappings = {
        "NGF25": [
            {"start_date": "2024-01-01", "end_date": "2024-06-01", "symbol": "42"}
        ],
        "NGF25-NGG25": [
            {"start_date": "2024-06-01", "end_date": "2024-08-01", "symbol": "42"}
        ],
    }
    definitions = pd.DataFrame(
        [
            {
                "instrument_id": 42,
                "raw_symbol": "NGF25",
                "ts_event": "2024-01-01T00:00:00Z",
                "instrument_class": "F",
                "asset": "NG",
                "expiration": "2025-01-29T19:30:00Z",
                "activation": "2023-11-01T00:00:00Z",
                "exchange": "XNYM",
            }
        ]
    )
    observations = pd.DataFrame(
        [
            {"instrument_id": 42, "ts_event": "2024-05-15T19:31:00Z", "ts_ref": "2024-05-15T00:00:00Z"},
            {"instrument_id": 42, "ts_event": "2024-06-15T19:31:00Z", "ts_ref": "2024-06-15T00:00:00Z"},
        ]
    )
    resolved = resolve_databento_metadata_symbols(observations, mappings)
    target = map_databento_resolved_symbols_to_target_definitions(
        definitions, resolved, product_code="NG"
    )
    assert target["symbol"].tolist() == ["NGF25"]
    assert target["ts_ref"].tolist() == ["2024-05-15T00:00:00Z"]


def test_databento_offline_symbol_mapping_is_point_in_time() -> None:
    from commodity.providers.databento_futures import _map_offline_statistics_symbols

    definitions = pd.DataFrame(
        [
            {"instrument_id": 42, "raw_symbol": "NGF25", "ts_recv": "2025-01-01T00:00:00Z"},
            {"instrument_id": 42, "raw_symbol": "NGG25", "ts_recv": "2025-02-01T00:00:00Z"},
            {"instrument_id": 43, "raw_symbol": "NGH25", "ts_recv": "2025-01-01T00:00:00Z"},
        ]
    )
    statistics = pd.DataFrame(
        [
            {"instrument_id": 42, "ts_recv": "2025-01-15T00:00:00Z"},
            {"instrument_id": 43, "ts_recv": "2025-01-20T00:00:00Z"},
            {"instrument_id": 42, "ts_recv": "2025-02-15T00:00:00Z"},
        ]
    )
    mapped = _map_offline_statistics_symbols(definitions, statistics)
    assert list(mapped["symbol"]) == ["NGF25", "NGH25", "NGG25"]


def test_databento_instrument_mapping_handles_id_reuse_across_eras() -> None:
    from commodity.providers.databento_futures import map_databento_instrument_symbols

    definitions = pd.DataFrame(
        [
            {"instrument_id": 42, "raw_symbol": "NGF15", "ts_event": "2015-01-01T00:00:00Z"},
            {"instrument_id": 42, "raw_symbol": "NGF26", "ts_event": "2026-01-01T00:00:00Z"},
        ]
    )
    observations = pd.DataFrame(
        [
            {"instrument_id": 42, "ts_event": "2015-01-15T00:00:00Z", "close": 3.0},
            {"instrument_id": 42, "ts_event": "2026-01-15T00:00:00Z", "close": 4.0},
        ]
    )
    mapped = map_databento_instrument_symbols(definitions, observations)
    assert mapped["symbol"].tolist() == ["NGF15", "NGF26"]
    assert mapped["close"].tolist() == [3.0, 4.0]


def test_databento_instrument_mapping_carries_time_valid_expiration() -> None:
    from commodity.providers.databento_futures import map_databento_instrument_symbols

    definitions = pd.DataFrame(
        [
            {
                "instrument_id": 42,
                "raw_symbol": "NGF0",
                "expiration": "2010-01-27T19:30:00Z",
                "ts_event": "2009-12-01T00:00:00Z",
            },
            {
                "instrument_id": 84,
                "raw_symbol": "NGF0",
                "expiration": "2020-01-29T19:30:00Z",
                "ts_event": "2019-12-01T00:00:00Z",
            },
        ]
    )
    observations = pd.DataFrame(
        [
            {"instrument_id": 42, "ts_event": "2010-01-15T00:00:00Z"},
            {"instrument_id": 84, "ts_event": "2020-01-15T00:00:00Z"},
        ]
    )
    mapped = map_databento_instrument_symbols(definitions, observations)
    assert mapped["symbol"].tolist() == ["NGF0", "NGF0"]
    assert pd.to_datetime(mapped["definition_expiration"], utc=True).tolist() == [
        pd.Timestamp("2010-01-27T19:30:00Z"),
        pd.Timestamp("2020-01-29T19:30:00Z"),
    ]


def test_databento_instrument_mapping_carries_definition_updates_for_same_contract() -> None:
    from commodity.providers.databento_futures import map_databento_instrument_symbols

    definitions = pd.DataFrame(
        [
            {"instrument_id": 42, "raw_symbol": "NGZ1", "expiration": "2021-11-26T19:30:00Z", "ts_recv": "2021-11-19T00:00:00Z"},
            {"instrument_id": 42, "raw_symbol": "NGZ1", "expiration": "2021-11-26T18:30:00Z", "ts_recv": "2021-11-19T14:12:19Z"},
        ]
    )
    observations = pd.DataFrame(
        [
            {"instrument_id": 42, "ts_recv": "2021-11-19T12:00:00Z"},
            {"instrument_id": 42, "ts_recv": "2021-11-19T15:00:00Z"},
        ]
    )
    mapped = map_databento_instrument_symbols(definitions, observations)
    assert pd.to_datetime(mapped["definition_expiration"], utc=True).tolist() == [
        pd.Timestamp("2021-11-26T19:30:00Z"),
        pd.Timestamp("2021-11-26T18:30:00Z"),
    ]


def test_databento_contract_id_is_unique_when_raw_symbol_is_reused() -> None:
    from commodity.providers.databento_futures import (
        normalize_databento_contract_history,
    )

    definitions = pd.DataFrame(
        [
            {"raw_symbol": "NGF0", "instrument_class": "F", "asset": "NG", "expiration": "2010-01-27T19:30:00Z", "exchange": "XNYM"},
            {"raw_symbol": "NGF0", "instrument_class": "F", "asset": "NG", "expiration": "2020-01-29T19:30:00Z", "exchange": "XNYM"},
        ]
    )
    statistics = pd.DataFrame(
        [
            {"symbol": "NGF0", "stat_type": 3, "stat_flags": 1, "ts_ref": "2010-01-15T00:00:00Z", "ts_event": "2010-01-15T19:31:00Z", "price": 5.0, "definition_expiration": "2010-01-27T19:30:00Z", "definition_exchange": "XNYM"},
            {"symbol": "NGF0", "stat_type": 3, "stat_flags": 1, "ts_ref": "2020-01-15T00:00:00Z", "ts_event": "2020-01-15T19:31:00Z", "price": 2.0, "definition_expiration": "2020-01-29T19:30:00Z", "definition_exchange": "XNYM"},
        ]
    )
    frame, _ = normalize_databento_contract_history(
        definitions, statistics, "2026-08-13T12:00:00Z", product_code="NG"
    )
    assert frame["expiration"].tolist() == [
        pd.Timestamp("2010-01-27T19:30:00Z"),
        pd.Timestamp("2020-01-29T19:30:00Z"),
    ]
    assert frame["contract_id"].nunique() == 2


def test_databento_instrument_mapping_rejects_ambiguous_same_time_identity() -> None:
    from commodity.providers.databento_futures import map_databento_instrument_symbols

    definitions = pd.DataFrame(
        [
            {"instrument_id": 42, "raw_symbol": "NGF26", "ts_event": "2026-01-01T00:00:00Z"},
            {"instrument_id": 42, "raw_symbol": "NGG26", "ts_event": "2026-01-01T00:00:00Z"},
        ]
    )
    observations = pd.DataFrame(
        [{"instrument_id": 42, "ts_event": "2026-01-15T00:00:00Z"}]
    )
    with pytest.raises(DataContractViolation, match="ambiguous point-in-time identity"):
        map_databento_instrument_symbols(definitions, observations)


def test_databento_instrument_mapping_rejects_observation_before_first_definition() -> None:
    from commodity.providers.databento_futures import map_databento_instrument_symbols

    definitions = pd.DataFrame(
        [{"instrument_id": 42, "raw_symbol": "NGF26", "ts_event": "2026-01-01T00:00:00Z"}]
    )
    observations = pd.DataFrame(
        [{"instrument_id": 42, "ts_event": "2025-12-31T23:59:59Z"}]
    )
    with pytest.raises(DataContractViolation, match="unmapped point-in-time instrument_id"):
        map_databento_instrument_symbols(definitions, observations)


def test_databento_offline_symbol_mapping_rejects_null_or_blank_identity() -> None:
    from commodity.providers.databento_futures import _map_offline_statistics_symbols

    statistics = pd.DataFrame(
        [{"instrument_id": 42, "ts_recv": "2025-01-15T00:00:00Z"}]
    )
    for raw_symbol in (None, "   "):
        definitions = pd.DataFrame(
            [
                {
                    "instrument_id": 42,
                    "raw_symbol": raw_symbol,
                    "ts_recv": "2025-01-01T00:00:00Z",
                }
            ]
        )
        with pytest.raises(DataContractViolation, match="no usable point-in-time symbols"):
            _map_offline_statistics_symbols(definitions, statistics)


def test_databento_offline_decoder_fails_closed_on_schema_mismatch_and_corruption(tmp_path) -> None:
    from commodity.providers.databento_futures import (
        DatabentoOfflineDecodeError,
        decode_databento_dbn_file,
    )

    definition_path = tmp_path / "sample.definition.dbn"
    definition_path.write_bytes(_dbn_bytes("definition"))
    with pytest.raises(DatabentoOfflineDecodeError, match="schema"):
        decode_databento_dbn_file(definition_path, expected_schema="statistics")
    with pytest.raises(DatabentoOfflineDecodeError, match="unsupported"):
        decode_databento_dbn_file(definition_path, expected_schema="mbo")

    for name in ("corrupt.statistics.dbn", "corrupt.statistics.dbn.zst"):
        corrupt_path = tmp_path / name
        corrupt_path.write_bytes(b"not-a-dbn-file")
        with pytest.raises(DatabentoOfflineDecodeError, match="decode"):
            decode_databento_dbn_file(corrupt_path, expected_schema="statistics")


def test_dbn_to_parquet_golden_fixture_is_deterministic(tmp_path) -> None:
    import runpy
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    fixture_root = repo_root / "tests" / "fixtures" / "mdp3-golden"
    convert = runpy.run_path(str(repo_root / "scripts" / "data" / "dbn_to_parquet.py"))[
        "convert_dbn_to_parquet"
    ]
    expected = json.loads((fixture_root / "expected.json").read_text(encoding="utf-8"))
    definition = (
        fixture_root
        / "definition"
        / "GLBX-SYNTH-DEFINITION"
        / "sample.definition.dbn.zst"
    )
    statistics = (
        fixture_root
        / "statistics"
        / "GLBX-SYNTH-STATISTICS"
        / "sample.statistics.dbn.zst"
    )
    receipts = []
    outputs = []
    for index in range(2):
        output = tmp_path / f"sample-{index}.parquet"
        metadata = tmp_path / f"sample-{index}.json"
        receipt = convert(
            definition,
            statistics,
            output,
            metadata,
            product_code="NG",
            retrieved_at="2026-08-14T12:00:00Z",
        )
        receipts.append(receipt)
        outputs.append(output.read_bytes())
        assert json.loads(metadata.read_text(encoding="utf-8")) == expected

    assert receipts == [expected, expected]
    assert outputs[0] == outputs[1]
    assert outputs[0] == (fixture_root / "sample.parquet").read_bytes()
    assert hashlib.sha256(outputs[0]).hexdigest() == expected["parquet_sha256"]
    canonical = pd.read_parquet(fixture_root / "sample.parquet")
    assert len(canonical) == expected["rows"] == 1
    assert list(canonical.columns) == expected["columns"]


def test_databento_offline_statistics_fails_closed_without_canonical_stats(tmp_path) -> None:
    import databento_dbn as dbn

    from commodity.providers.databento_futures import (
        DatabentoOfflineDecodeError,
        _decode_databento_canonical_statistics,
    )

    ts = 1735776000000000000
    metadata = dbn.Metadata(
        dataset="GLBX.MDP3",
        start=ts,
        stype_in=dbn.SType.INSTRUMENT_ID,
        stype_out=dbn.SType.INSTRUMENT_ID,
        schema=dbn.Schema.STATISTICS,
        symbols=["42"],
        end=ts + 86400 * 10**9,
    )
    record = dbn.StatMsg(
        publisher_id=1,
        instrument_id=42,
        ts_event=ts + 100,
        ts_recv=ts + 200,
        ts_ref=ts,
        price=0,
        quantity=1,
        stat_type=dbn.StatType.OPEN_INTEREST,
        stat_flags=0,
    )
    statistics_path = tmp_path / "open-interest.statistics.dbn"
    statistics_path.write_bytes(metadata.encode() + bytes(record))
    with pytest.raises(DatabentoOfflineDecodeError, match="no canonical statistics"):
        _decode_databento_canonical_statistics(
            statistics_path,
            dataset="GLBX.MDP3",
        )
