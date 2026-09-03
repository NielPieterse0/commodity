import copy

import pandas as pd
import pytest

from commodity.config import assumptions_config, data_config
from commodity.market_data import (
    DataContractViolation,
    assert_canonical_market_ready,
    assert_market_evaluation_ready,
    build_contract_rank_windows,
    canonical_market_readiness,
    validate_contract_history,
    validate_contract_metadata,
)


def _schema() -> dict:
    return data_config()["canonical_contract_schema"]


def _canonical_source(data: dict) -> dict:
    return data["sources"][data["canonical_market_source_id"]]


def _ready_configs() -> tuple[dict, dict]:
    data = copy.deepcopy(data_config())
    assumptions = copy.deepcopy(assumptions_config())
    source = _canonical_source(data)
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


def test_configured_canonical_source_is_databento_and_massive_is_evaluation_only() -> None:
    data = data_config()
    assumptions = assumptions_config()
    canonical = canonical_market_readiness(data, assumptions)
    assert canonical["source_id"] == "databento_henry_hub"
    assert canonical["canonical_evidence_allowed"] is True

    massive = canonical_market_readiness(data, assumptions, "massive_henry_hub_evaluation")
    assert massive["evaluation_evidence_allowed"] is True
    assert massive["canonical_evidence_allowed"] is False
    assert massive["is_configured_canonical"] is False
    with pytest.raises(DataContractViolation, match="configured canonical source"):
        assert_canonical_market_ready(data, assumptions, "massive_henry_hub_evaluation")


def test_canonical_readiness_exposes_licensing_as_separate_blocker() -> None:
    data, assumptions = _ready_configs()
    _canonical_source(data)["backtest_evidence_allowed"] = False
    _canonical_source(data)["non_display_backtesting_rights_verified"] = False
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


def test_canonical_metadata_values_must_match_selected_source_authority() -> None:
    data = data_config()
    authority = data["sources"][data["canonical_market_source_id"]]
    metadata = {
        "source_id": "wrong-source",
        "source_sha256": "a" * 64,
        "retrieved_at": "2026-08-12T12:00:00Z",
        "exchange": authority["exchange"],
        "product_code": authority["product_code"],
        "session_timezone": authority["session_timezone"],
        "calendar": authority["calendar"],
        "price_semantics": authority["price_semantics"],
    }
    with pytest.raises(DataContractViolation, match="source_id"):
        validate_contract_metadata(metadata, _schema(), authority)
    metadata["source_id"] = authority["allowed_metadata_source_ids"][0]
    metadata["session_timezone"] = "America/Chicago"
    with pytest.raises(DataContractViolation, match="session_timezone"):
        validate_contract_metadata(metadata, _schema(), authority)


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
        _canonical_source(data)["account_history_validated"] = False
    elif mutation == "volume":
        _canonical_source(data)["historical_volume"] = False
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


def test_canonical_readiness_does_not_duplicate_owned_policy_parameter_values() -> None:
    data, assumptions = _ready_configs()
    assumptions["assumptions"]["continuous_series_policy"]["policy"][
        "confirmation_sessions"
    ] = 3
    report = canonical_market_readiness(data, assumptions)
    assert report["roll_method_ready"] is True
    assert report["canonical_evidence_allowed"] is True


def test_contract_rank_windows_bound_each_contract_to_rank_membership() -> None:
    contracts = [
        {"ticker": "NGF5", "first_trade_date": "2024-01-01", "last_trade_date": "2025-01-29"},
        {"ticker": "NGG5", "first_trade_date": "2024-01-01", "last_trade_date": "2025-02-26"},
        {"ticker": "NGH5", "first_trade_date": "2024-01-01", "last_trade_date": "2025-03-27"},
        {"ticker": "NGJ5", "first_trade_date": "2024-01-01", "last_trade_date": "2025-04-28"},
    ]
    windows = build_contract_rank_windows(
        contracts, "2025-01-01", "2025-04-30", max_contracts=2
    )
    by_ticker = {row[0]["ticker"]: (row[1], row[2]) for row in windows}
    assert by_ticker == {
        "NGF5": ("2025-01-01", "2025-01-29"),
        "NGG5": ("2025-01-01", "2025-02-26"),
        "NGH5": ("2025-01-30", "2025-03-27"),
        "NGJ5": ("2025-02-27", "2025-04-28"),
    }


def test_contract_rank_windows_clip_to_first_trade_date() -> None:
    contracts = [
        {"ticker": "NGF5", "first_trade_date": "2025-01-10", "last_trade_date": "2025-01-29"},
        {"ticker": "NGG5", "first_trade_date": "2025-01-15", "last_trade_date": "2025-02-26"},
    ]
    windows = build_contract_rank_windows(
        contracts, "2025-01-01", "2025-02-28", max_contracts=2
    )
    assert [(row[0]["ticker"], row[1], row[2]) for row in windows] == [
        ("NGF5", "2025-01-10", "2025-01-29"),
        ("NGG5", "2025-01-15", "2025-02-26"),
    ]


def test_contract_rank_windows_reject_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="max_contracts"):
        build_contract_rank_windows([], "2025-01-01", "2025-01-31", max_contracts=0)
    with pytest.raises(DataContractViolation, match="last_trade_date"):
        build_contract_rank_windows(
            [{"ticker": "NGF5"}], "2025-01-01", "2025-01-31", max_contracts=1
        )


def test_canonical_readiness_messages_are_provider_neutral() -> None:
    data, assumptions = _ready_configs()
    _canonical_source(data)["account_history_validated"] = False
    _canonical_source(data)["non_display_backtesting_rights_verified"] = False
    report = canonical_market_readiness(data, assumptions)
    assert all("Massive" not in reason for reason in report["reasons"])


def test_market_structure_excludes_quotes_after_prediction_cutoff() -> None:
    from commodity import market_data

    frame = pd.DataFrame([
        {"trade_date": "2026-01-20", "contract_id": "NGG26", "expiration": "2026-01-28", "settle": 3.10, "volume": 100, "available_at": "2026-01-20T21:00:00Z"},
        {"trade_date": "2026-01-20", "contract_id": "NGH26", "expiration": "2026-02-25", "settle": 3.20, "volume": 80, "available_at": "2026-01-20T23:00:00Z"},
    ])
    cutoffs = pd.DataFrame({
        "trade_date": [pd.Timestamp("2026-01-20", tz="UTC")],
        "prediction_time": [pd.Timestamp("2026-01-20T22:00:00Z")],
    })
    features, audit = market_data.build_market_structure_features(
        frame, _schema(), cutoffs, max_contracts=2
    )
    row = features.iloc[0]
    assert row["curve_settle_m1"] == pytest.approx(3.10)
    assert pd.isna(row["curve_settle_m2"])
    assert audit.iloc[0]["contract_id_m2"] == "NGH26"
    assert bool(audit.iloc[0]["quote_available_m2"]) is False


def test_market_structure_derives_ranked_curve_features_deterministically() -> None:
    from commodity import market_data

    rows = [
        {"trade_date": "2026-01-20", "contract_id": "NGG26", "expiration": "2026-01-28", "settle": 3.10, "volume": 100, "available_at": "2026-01-20T21:00:00Z"},
        {"trade_date": "2026-01-20", "contract_id": "NGH26", "expiration": "2026-02-25", "settle": 3.20, "volume": 80, "available_at": "2026-01-20T21:00:00Z"},
        {"trade_date": "2026-01-20", "contract_id": "NGJ26", "expiration": "2026-03-27", "settle": 3.35, "volume": 60, "available_at": "2026-01-20T21:00:00Z"},
        {"trade_date": "2026-01-20", "contract_id": "NGK26", "expiration": "2026-04-28", "settle": 3.55, "volume": 50, "available_at": "2026-01-20T21:00:00Z"},
    ]
    cutoffs = pd.DataFrame({"trade_date": ["2026-01-20"], "prediction_time": ["2026-01-20T22:00:00Z"]})
    first, first_audit = market_data.build_market_structure_features(pd.DataFrame(rows), _schema(), cutoffs)
    second, second_audit = market_data.build_market_structure_features(pd.DataFrame(rows), _schema(), cutoffs)
    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(first_audit, second_audit)
    row = first.iloc[0]
    assert row["curve_spread_m1_m2"] == pytest.approx(-0.10)
    assert row["curve_volume_ratio_m1_m2"] == pytest.approx(1.25)
    assert row["curve_slope_m1_m4"] > 0


def test_market_structure_curve_dte_preserves_exact_expiry_time_spans() -> None:
    from commodity import market_data

    rows = [
        {"trade_date": "2026-01-20T12:00:00Z", "contract_id": "NGG26", "expiration": "2026-01-21T00:00:00Z", "settle": 3.10, "volume": 100, "available_at": "2026-01-20T13:00:00Z"},
        {"trade_date": "2026-01-20T12:00:00Z", "contract_id": "NGH26", "expiration": "2026-01-22T12:00:00Z", "settle": 3.40, "volume": 80, "available_at": "2026-01-20T13:00:00Z"},
    ]
    cutoffs = pd.DataFrame({
        "trade_date": ["2026-01-20T12:00:00Z"],
        "prediction_time": ["2026-01-20T14:00:00Z"],
    })
    features, _ = market_data.build_market_structure_features(
        pd.DataFrame(rows), _schema(), cutoffs, max_contracts=2
    )
    row = features.iloc[0]
    assert row["curve_dte_m1"] == pytest.approx(0.5)
    assert row["curve_dte_m2"] == pytest.approx(2.0)
    assert row["curve_slope_m1_m2"] == pytest.approx(0.2)


def test_canonical_market_availability_reconstructs_conservative_bound() -> None:
    from commodity.market_data import ensure_canonical_market_availability

    frame = _contracts()
    policy = {
        "method": "trade_date_2359_utc",
        "status": "reconstructed_conservative",
    }
    result = ensure_canonical_market_availability(frame, policy)
    assert result.loc[0, "available_at"] == pd.Timestamp("2026-01-20T23:59:00Z")
    assert result["availability_status"].eq("reconstructed_conservative").all()


def test_canonical_market_availability_preserves_exact_source_timestamp() -> None:
    from commodity.market_data import ensure_canonical_market_availability

    frame = _contracts()
    frame["available_at"] = pd.Timestamp("2026-01-20T21:17:00Z")
    result = ensure_canonical_market_availability(frame, {})
    assert result["available_at"].eq(pd.Timestamp("2026-01-20T21:17:00Z")).all()
    assert result["availability_status"].eq("source_timestamp").all()


def test_canonical_market_availability_preserves_existing_status() -> None:
    from commodity.market_data import ensure_canonical_market_availability

    frame = _contracts()
    frame["available_at"] = pd.Timestamp("2026-01-20T23:59:00Z")
    frame["availability_status"] = "reconstructed_conservative"
    result = ensure_canonical_market_availability(frame, {})
    assert result["availability_status"].eq("reconstructed_conservative").all()


def test_market_evaluation_readiness_does_not_require_promotion_rights() -> None:
    data, assumptions = _ready_configs()
    source = _canonical_source(data)
    source["non_display_backtesting_rights_verified"] = False
    source["backtest_evidence_allowed"] = False
    report = canonical_market_readiness(data, assumptions)
    assert report["evaluation_evidence_allowed"] is True
    assert report["canonical_evidence_allowed"] is False
    assert_market_evaluation_ready(data, assumptions)
    with pytest.raises(DataContractViolation, match="rights"):
        assert_canonical_market_ready(data, assumptions)
