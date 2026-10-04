from __future__ import annotations

import pandas as pd
import pytest

from commodity.v2_adaptive_controller import (
    AdaptiveContractError,
    assert_causal_state_columns,
    comparable_state_refs,
    first_block_spec,
    latest_known_state,
    matured_consequences,
    memory_snapshot,
    next_position_state,
    oracle_diagnostic,
    rebalance_target_signal,
    run_adaptive_block,
    sparse_policy_signal,
)


def ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def test_first_block_is_six_calendar_months_from_earliest_feature() -> None:
    block = first_block_spec(pd.Series([ts("2010-07-06"), ts("2010-08-01")]))
    assert block.block_id == "block-001"
    assert block.start == ts("2010-07-06")
    assert block.end_exclusive == ts("2011-01-06")


def test_latest_known_state_waits_for_actual_availability() -> None:
    observations = pd.DataFrame(
        {
            "observation_time": [ts("2010-07-06"), ts("2010-07-07")],
            "available_at": [ts("2010-07-07 00:01"), ts("2010-07-08 00:01")],
            "feature_x": [1.0, 2.0],
            "source_id": ["market", "market"],
        }
    )
    decisions = pd.Series([ts("2010-07-07 00:00"), ts("2010-07-08 00:00")])
    joined = latest_known_state(observations, decisions)
    assert pd.isna(joined.iloc[0]["feature_x"])
    assert joined.iloc[1]["feature_x"] == 1.0
    assert joined.iloc[1]["available_at"] < joined.iloc[1]["decision_time"]


def test_causal_state_rejects_consequence_columns() -> None:
    with pytest.raises(AdaptiveContractError, match="causal state"):
        assert_causal_state_columns(["feature_ret_5", "future_pnl_usd"])


def test_matured_consequences_are_strictly_prior() -> None:
    consequences = pd.DataFrame(
        {
            "outcome_available_at": [ts("2010-08-01"), ts("2010-08-02")],
            "policy_id": ["trend", "trend"],
            "net_return": [0.01, 0.50],
        }
    )
    matured = matured_consequences(consequences, ts("2010-08-02"), window=30)
    assert matured["net_return"].tolist() == [0.01]


def test_add_requires_positive_marginal_edge_and_risk_capacity() -> None:
    assert next_position_state("FULL", 1, marginal_edge=0.1, risk_capacity=0.5) == "ADD"
    assert next_position_state("FULL", 1, marginal_edge=0.0, risk_capacity=0.5) == "FULL"
    assert next_position_state("FULL", 1, marginal_edge=0.1, risk_capacity=0.0) == "FULL"
    assert next_position_state("STARTER", 0, marginal_edge=0.0, risk_capacity=1.0) == "EXIT"


def _toy_state(rows: int = 40) -> pd.DataFrame:
    dates = pd.date_range("2010-07-06", periods=rows, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "decision_time": dates,
            "flat": 0.0,
            "trend": 1.0,
            "mean_reversion": -1.0,
        }
    )


def _toy_path(rows: int = 40) -> pd.DataFrame:
    dates = pd.date_range("2010-07-06", periods=rows, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "decision_time": dates,
            "outcome_available_at": dates + pd.Timedelta(hours=12),
            "path_move_per_mmbtu": [0.01] * rows,
        }
    )


def test_block_has_exact_30_row_warmup_and_prior_only_selection() -> None:
    result = run_adaptive_block(_toy_state(), _toy_path(), objective_window=30)
    ledger = result.ledger
    assert ledger.iloc[:30]["selected_policy_id"].eq("warmup").all()
    assert ledger.iloc[30]["selected_policy_id"] == "trend"
    assert ledger.iloc[30]["max_outcome_available_at_used"] < ledger.iloc[30]["decision_time"]


def test_same_day_and_future_outcomes_do_not_change_current_decision() -> None:
    state = _toy_state()
    path = _toy_path()
    baseline = run_adaptive_block(state, path, objective_window=30).ledger
    mutated = path.copy()
    mutated.loc[mutated["decision_time"] >= state.iloc[30]["decision_time"], "path_move_per_mmbtu"] = -99.0
    changed = run_adaptive_block(state, mutated, objective_window=30).ledger
    cols = ["decision_time", "selected_policy_id", "selected_signal"]
    pd.testing.assert_frame_equal(baseline.loc[:30, cols], changed.loc[:30, cols])


def test_appending_later_block_rows_cannot_change_block1() -> None:
    state = _toy_state(190)
    path = _toy_path(190)
    block_end = ts("2011-01-06")
    base = run_adaptive_block(state[state["decision_time"] < block_end], path, objective_window=30)
    future_state = pd.concat(
        [state, pd.DataFrame({"decision_time": [ts("2012-01-01")], "flat": [0.0], "trend": [-1.0], "mean_reversion": [1.0]})],
        ignore_index=True,
    )
    future_path = pd.concat(
        [path, pd.DataFrame({"decision_time": [ts("2012-01-01")], "outcome_available_at": [ts("2012-01-02")], "path_move_per_mmbtu": [-100.0]})],
        ignore_index=True,
    )
    changed = run_adaptive_block(future_state[future_state["decision_time"] < block_end], future_path, objective_window=30)
    pd.testing.assert_frame_equal(base.ledger, changed.ledger)
    assert base.freeze_sha256 == changed.freeze_sha256


def test_memory_snapshot_is_prior_only_across_declared_windows() -> None:
    consequences = pd.DataFrame(
        {
            "outcome_available_at": pd.date_range("2010-07-01", periods=12, freq="D", tz="UTC"),
            "net_return": [0.01] * 11 + [99.0],
        }
    )
    snapshot = memory_snapshot(
        consequences,
        ts("2010-07-12"),
        windows=(5, 10),
    )
    assert snapshot["w5"]["count"] == 5
    assert snapshot["w5"]["net_return_sum"] == pytest.approx(0.05)
    assert snapshot["w10"]["net_return_sum"] == pytest.approx(0.10)
    assert snapshot["expanding"]["count"] == 11


def test_ledger_records_sparse_selected_weights() -> None:
    ledger = run_adaptive_block(_toy_state(), _toy_path(), objective_window=30).ledger
    assert ledger.iloc[30]["selected_weights"] == {"trend": 1.0}


def test_rebalance_target_signal_holds_between_causal_rebalances() -> None:
    signal = pd.Series([1.0, -1.0, -1.0, 1.0, 1.0, -1.0])
    held = rebalance_target_signal(signal, cadence_sessions=3)
    assert held.tolist() == [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]


def test_sparse_policy_signal_supports_side_and_fractional_exposure() -> None:
    specialists = pd.DataFrame({"trend": [1.0, -1.0], "expert": [1.0, 1.0]})
    signal = sparse_policy_signal(
        specialists,
        weights={"trend": 0.5, "expert": 0.5},
        cadence_sessions=1,
        side="long_only",
        exposure=1.5,
    )
    assert signal.tolist() == [1.5, 0.0]


def test_comparable_state_refs_never_use_current_or_future_rows() -> None:
    frame = pd.DataFrame(
        {
            "decision_time": pd.date_range("2010-07-01", periods=6, freq="D", tz="UTC"),
            "feature_a": [0.0, 1.0, 2.0, 3.0, 2.1, 99.0],
            "feature_b": [0.0, 0.0, 0.0, 0.0, 0.0, 99.0],
        }
    )
    refs = comparable_state_refs(frame, ts("2010-07-05"), k=2)
    assert refs == [ts("2010-07-03"), ts("2010-07-04")]
    assert all(value < ts("2010-07-05") for value in refs)


def test_oracle_diagnostic_is_hindsight_only_and_bounded_to_requested_days() -> None:
    candidate = pd.DataFrame(
        {
            "decision_time": [ts("2010-07-01"), ts("2010-07-01"), ts("2010-07-02"), ts("2010-07-02")],
            "policy_id": ["a", "b", "a", "b"],
            "net_return": [0.01, -0.01, -0.02, 0.03],
        }
    )
    result = oracle_diagnostic(candidate, [ts("2010-07-02")])
    assert result["oracle_net_return"] == pytest.approx(0.03)
    assert result["oracle_policy_by_day"] == {"2010-07-02T00:00:00+00:00": "b"}


def test_state_available_exactly_at_decision_time_is_eligible() -> None:
    observations = pd.DataFrame(
        {
            "observation_time": [ts("2010-07-01")],
            "available_at": [ts("2010-07-02")],
            "source_id": ["pit"],
            "feature_x": [7.0],
        }
    )
    joined = latest_known_state(observations, pd.Series([ts("2010-07-02")]))
    assert joined.iloc[0]["feature_x"] == 7.0


def test_fractional_exposure_is_not_truncated_by_position_state() -> None:
    state = _toy_state()
    state["trend"] = 1.5
    result = run_adaptive_block(state, _toy_path(), objective_window=30)
    assert result.ledger.iloc[30]["selected_signal"] == pytest.approx(1.5)
    assert result.ledger.iloc[30]["position_state"] == "STARTER"


def test_position_state_detects_reverse_and_reduce_from_current_exposure() -> None:
    assert next_position_state(
        "FULL", -1.0, current_position=1.0, marginal_edge=0.2, risk_capacity=1.0
    ) == "REVERSE"
    assert next_position_state(
        "FULL", 0.75, current_position=1.0, marginal_edge=0.2, risk_capacity=1.0
    ) == "REDUCE"


def test_decision_brain_records_underlying_sparse_policy_metadata() -> None:
    metadata = {
        "trend": {
            "weights": {"trend_ret20": 1.0},
            "horizon_sessions": 5,
            "side": "symmetric",
            "exposure": 1.5,
            "complexity": 1,
        }
    }
    state = _toy_state()
    result = run_adaptive_block(
        state[["decision_time", "trend"]],
        _toy_path(),
        objective_window=30,
        policy_metadata=metadata,
    )
    row = result.ledger.iloc[30]
    assert row["selected_weights"] == {"trend_ret20": 1.0}
    assert row["selected_horizon_sessions"] == 5
    assert row["selected_exposure"] == pytest.approx(1.5)


def test_decision_brain_comparable_state_refs_are_strictly_prior() -> None:
    state = _toy_state()
    context = pd.DataFrame(
        {
            "decision_time": state["decision_time"],
            "feature_context": range(len(state)),
        }
    )
    result = run_adaptive_block(
        state,
        _toy_path(),
        objective_window=30,
        context_state=context,
        similar_state_k=3,
    )
    row = result.ledger.iloc[30]
    assert len(row["similar_state_refs"]) == 3
    assert all(value < row["decision_time"] for value in row["similar_state_refs"])


def test_candidate_consequence_store_supports_non_identifier_policy_ids() -> None:
    from commodity.v2_adaptive_controller import candidate_consequence_store

    policy_id = "trend_ret20:1__h1__symmetric__x0p75"
    state = pd.DataFrame({
        "decision_time": pd.to_datetime(["2010-07-01", "2010-07-02"], utc=True),
        policy_id: [0.75, -0.75],
    })
    path = pd.DataFrame({
        "decision_time": state["decision_time"],
        "outcome_available_at": pd.to_datetime(["2010-07-02", "2010-07-03"], utc=True),
        "path_move_per_mmbtu": [0.01, -0.02],
    })
    result = candidate_consequence_store(state, path, [policy_id])
    assert result["policy_id"].tolist() == [policy_id, policy_id]
    assert result["signal"].tolist() == [pytest.approx(0.75), pytest.approx(-0.75)]
