import copy

import pandas as pd
import pytest

from commodity.config import assumptions_config, data_config
from commodity.market_data import (
    DataContractViolation,
    assert_canonical_market_ready,
    build_term_structure,
    canonical_market_readiness,
    validate_contract_history,
    validate_contract_metadata,
)


def _schema() -> dict:
    return data_config()["canonical_contract_schema"]


def _ready_configs() -> tuple[dict, dict]:
    data = copy.deepcopy(data_config())
    assumptions = copy.deepcopy(assumptions_config())
    source = data["sources"]["market_canonical"]
    source.update({
        "backtest_evidence_allowed": True,
        "account_history_validated": True,
        "history_depth_status": "verified_account_boundary",
        "history_earliest_verified_trade_date": "2024-08-13",
        "historical_volume": True,
        "non_display_backtesting_rights_verified": True,
    })
    data["canonical_contract_schema"]["continuous_contract"]["default_roll_policy"] = (
        "volume_crossover_dte_v1"
    )
    policy = assumptions["assumptions"]["continuous_series_policy"]
    policy["default_roll_policy"] = "volume_crossover_dte_v1"
    policy["policy"] = {
        "method": "volume_crossover_dte_v1",
        "confirmation_sessions": 2,
        "forced_roll_days_before_expiry": 3,
        "volume_evidence": "prior_observed_session",
        "crossover": "strict_greater_than",
        "tie_behavior": "reset_confirmation_and_hold",
        "missing_volume_behavior": "reset_confirmation_and_hold",
        "holiday_behavior": "count_observed_sessions_only",
        "contract_unavailable_behavior": "nearest_later_eligible",
        "no_later_contract_behavior": "fail_closed",
    }
    return data, assumptions


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


def test_canonical_readiness_exposes_licensing_as_separate_blocker() -> None:
    data, assumptions = _ready_configs()
    data["sources"]["market_canonical"]["backtest_evidence_allowed"] = False
    data["sources"]["market_canonical"]["non_display_backtesting_rights_verified"] = False
    report = canonical_market_readiness(data, assumptions)
    assert report["source_history_ready"] is True
    assert report["roll_method_ready"] is True
    assert report["licensing_ready"] is False
    assert report["canonical_evidence_allowed"] is False
    with pytest.raises(DataContractViolation, match="non-display/backtesting rights"):
        assert_canonical_market_ready(data, assumptions)


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


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("history", "account history"),
        ("volume", "historical volume"),
        ("policy", "roll policy"),
        ("policy_semantics", "registered roll policy semantics"),
        ("cross_returns", "cross-contract returns"),
    ],
)
def test_canonical_evidence_fails_closed_on_required_prerequisites(mutation, match) -> None:
    data, assumptions = _ready_configs()
    if mutation == "history":
        data["sources"]["market_canonical"]["account_history_validated"] = False
    elif mutation == "volume":
        data["sources"]["market_canonical"]["historical_volume"] = False
    elif mutation == "policy":
        assumptions["assumptions"]["continuous_series_policy"]["default_roll_policy"] = "unknown"
    elif mutation == "policy_semantics":
        assumptions["assumptions"]["continuous_series_policy"]["policy"]["tie_behavior"] = "hold"
    else:
        data["canonical_contract_schema"]["continuous_contract"]["cross_contract_returns_allowed"] = True
    with pytest.raises(DataContractViolation, match=match):
        assert_canonical_market_ready(data, assumptions)


def test_canonical_evidence_passes_when_all_prerequisites_are_verified() -> None:
    data, assumptions = _ready_configs()
    report = canonical_market_readiness(data, assumptions)
    assert report["canonical_evidence_allowed"] is True
    assert_canonical_market_ready(data, assumptions)
