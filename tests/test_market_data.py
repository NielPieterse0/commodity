import pandas as pd
import pytest

from commodity.config import data_config
from commodity.market_data import (
    DataContractViolation,
    assert_canonical_market_ready,
    build_term_structure,
    validate_contract_history,
    validate_contract_metadata,
)


def _schema() -> dict:
    return data_config()["canonical_contract_schema"]


def _contracts() -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": ["2026-01-20", "2026-01-20", "2026-01-21", "2026-01-21"],
        "contract_id": ["NGG26", "NGH26", "NGG26", "NGH26"],
        "expiration": ["2026-01-28", "2026-02-25", "2026-01-28", "2026-02-25"],
        "settle": [3.10, 3.20, 3.15, 3.25],
    })


def test_canonical_contract_history_requires_expiry_and_identity() -> None:
    frame = _contracts().drop(columns=["expiration"])
    with pytest.raises(DataContractViolation, match="expiration"):
        validate_contract_history(frame, _schema())


def test_canonical_contract_history_rejects_duplicate_grain() -> None:
    frame = pd.concat([_contracts(), _contracts().iloc[[0]]], ignore_index=True)
    with pytest.raises(DataContractViolation, match="Duplicate"):
        validate_contract_history(frame, _schema())


def test_term_structure_orders_contracts_by_expiration() -> None:
    curve = build_term_structure(_contracts(), _schema(), max_contracts=2)
    row = curve.loc[pd.Timestamp("2026-01-20", tz="UTC")]
    assert row["contract_id_1"] == "NGG26"
    assert row["contract_id_2"] == "NGH26"
    assert row["settle_1"] == pytest.approx(3.10)
    assert row["settle_2"] == pytest.approx(3.20)
    assert row["days_to_expiry_1"] == pytest.approx(8.0)


def test_canonical_evidence_remains_blocked_until_source_and_roll_are_approved() -> None:
    with pytest.raises(DataContractViolation, match="not approved"):
        assert_canonical_market_ready(data_config())


def test_canonical_dataset_requires_provenance_and_session_metadata() -> None:
    metadata = {
        "source_id": "example",
        "source_sha256": "a" * 64,
        "retrieved_at": "2026-08-12T12:00:00Z",
        "exchange": "NYMEX",
        "product_code": "NG",
        "session_timezone": "America/New_York",
        "calendar": "CME_NYMEX",
    }
    with pytest.raises(DataContractViolation, match="price_semantics"):
        validate_contract_metadata(metadata, _schema())
