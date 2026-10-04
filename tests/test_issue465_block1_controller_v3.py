from __future__ import annotations

import pandas as pd
import pytest

from commodity.v2_adaptive_controller_v2 import MEMORY_BANK
from commodity.v2_adaptive_controller_v3 import (
    CandidateReplay,
    ControllerConfig,
    PositionState,
    SidePolicy,
    apply_fill,
    apply_realized_return,
    causal_prior_check,
    enforce_execution_hard_cap,
    lifecycle_target,
    mark_position,
    meta_lifecycle_inputs,
    opportunity_table,
    oracle_first_diagnostic,
    replay_targets_under_execution_stress,
    run_meta_controller,
    score_surface_for_side,
    structural_grid,
    timing_entry_decision,
)
from commodity.v2_adaptive_controller_v3_diagnostics import (
    FOUNDATION_CONTEXT_COLUMNS,
    build_foundation_actual_paths,
    build_rich_expert_consequences,
    causal_oracle_weight_predictor,
    causal_primitive_oracle_winner_predictor,
    foundation_context_frame,
    foundation_horizon_signals,
    hindsight_attribute_weight_oracle,
    oracle_predictor_causal_check,
    path_shape_features,
    rich_effectiveness_surface_for_day,
)


def ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def _profile(memories: list[int | str], horizons: list[int]) -> dict:
    return {
        "memories": memories, "horizons": horizons, "top_k": 4,
        "wait_support_floor": 0.35, "enter_support_floor": 0.55,
        "enter_confidence_floor": 0.35, "max_vol_ratio": 1.5,
        "size_scale": 1.0, "max_hold_sessions": 10,
        "add_edge_ratio": 1.1, "reduce_edge_ratio": 0.5,
        "reverse_edge_ratio": 1.2, "exit_edge_floor": 0.0,
    }


def _prereg() -> dict:
    profiles = {
        "fast": _profile([5, 10, 20], [1, 3, 5]),
        "balanced": _profile([10, 20, 40, 60], [3, 5, 10]),
        "slow": _profile([40, 60, 126, 252, "expanding"], [10, 20]),
        "broad": _profile(list(MEMORY_BANK), [1, 3, 5, 10, 20]),
    }
    return {
        "side_policy_profiles": profiles,
        "structural_search": {
            "comparable_state_weights": [0.0, 0.25, 0.5],
            "slow_cadence_sessions": [10, 20],
            "expected_candidate_count": 96,
            "uncertainty_penalty": 0.5,
            "active_family_cap": 6,
        },
    }


def test_structural_grid_has_frozen_asymmetric_and_symmetric_controls() -> None:
    configs = structural_grid(_prereg())
    assert len(configs) == 96
    assert sum(config.asymmetric for config in configs) == 72
    assert sum(not config.asymmetric for config in configs) == 24
    memories = {
        memory for config in configs
        for policy in (config.long_policy, config.short_policy)
        for memory in policy.memories
    }
    assert set(MEMORY_BANK).issubset(memories)


def test_opportunity_table_computes_weighted_support_from_sparse_weights() -> None:
    config = structural_grid(_prereg())[0]
    surface = pd.DataFrame({
        "specialist": ["a"], "horizon": [1], "direction": ["long"],
        "memory": [5], "count": [30],
        "mean_net_return": [0.02], "std_net_return": [0.001],
        "objective_30_net_return_sum": [0.30], "objective_30_std_net_return": [0.001],
        "objective_30_count": [30], "comparable_mean_net_return": [0.02],
    })
    table = opportunity_table(
        surface, pd.Series({"a": 1.0}), {"a": "trend"}, ("trend",), config,
    )
    assert len(table) == 1
    assert table.iloc[0]["support"] == pytest.approx(1.0)
    assert table.iloc[0]["weights"] == {"a": pytest.approx(1.0)}


def test_timing_layer_distinguishes_abstain_wait_and_enter_now() -> None:
    policy = structural_grid(_prereg())[0].long_policy
    state = pd.Series({"feature_vol_20": 1.0, "derived_prior60_vol20_median": 1.0})
    abstain = pd.Series({"edge": -0.01, "support": 1.0, "confidence": 1.0})
    wait = pd.Series({"edge": 0.02, "support": 0.40, "confidence": 0.50})
    enter = pd.Series({"edge": 0.02, "support": 0.80, "confidence": 0.80})
    assert timing_entry_decision(abstain, state, policy) == "ABSTAIN"
    assert timing_entry_decision(wait, state, policy) == "WAIT"
    assert timing_entry_decision(enter, state, policy) == "ENTER_NOW"


def test_position_age_and_mark_to_market_use_decision_sessions() -> None:
    position = PositionState()
    apply_fill(
        position, target=1.0, fill_price=4.0, fill_time=ts("2010-07-02"),
        decision_index=3, remaining_edge=0.02, contract_id="NGQ10",
    )
    mark = mark_position(
        position, mark_price=4.2, decision_time=ts("2010-07-09"),
        decision_index=7, multiplier=10000.0, initial_capital=100000.0,
    )
    assert mark["time_in_position_sessions"] == 4
    assert mark["unrealized_pnl_fraction"] == pytest.approx(0.02)
    assert mark["mfe_to_date_fraction"] == pytest.approx(0.02)
    assert mark["mae_to_date_fraction"] == pytest.approx(0.0)
    assert mark["edge_at_entry"] == pytest.approx(0.02)


def test_matured_path_return_rebases_mark_without_double_counting() -> None:
    position = PositionState()
    apply_fill(
        position, target=1.0, fill_price=4.0, fill_time=ts("2010-07-02"),
        decision_index=3, remaining_edge=0.02, contract_id="NGQ10",
    )
    apply_realized_return(
        position, 0.01, 100000.0,
        position_instance_id=position.instance_id,
        terminal_basis_price=4.1,
        contract_id="NGQ10",
    )
    mark = mark_position(
        position, mark_price=4.1, decision_time=ts("2010-07-03"),
        decision_index=4, multiplier=10000.0, initial_capital=100000.0,
    )
    assert mark["economic_path_pnl_fraction"] == pytest.approx(0.01)
    assert mark["current_contract_mtm_fraction"] == pytest.approx(0.0)
    assert mark["unrealized_pnl_fraction"] == pytest.approx(0.01)
    assert mark["mfe_to_date_fraction"] == pytest.approx(0.01)


def test_roll_updates_execution_basis_without_resetting_entry_identity() -> None:
    position = PositionState()
    apply_fill(
        position, target=1.0, fill_price=4.0, fill_time=ts("2010-07-02"),
        decision_index=2, remaining_edge=0.02, contract_id="NGQ10",
    )
    instance = position.instance_id
    apply_fill(
        position, target=1.0, fill_price=4.3, fill_time=ts("2010-07-20"),
        decision_index=14, remaining_edge=0.03, contract_id="NGU10",
    )
    assert position.instance_id == instance
    assert position.entry_contract_id == "NGQ10"
    assert position.current_contract_id == "NGU10"
    assert position.entry_price == pytest.approx(4.0)
    assert position.current_basis_price == pytest.approx(4.3)


def test_lifecycle_requires_remaining_edge_for_add_and_reverse() -> None:
    config = structural_grid(_prereg())[0]
    position = PositionState(exposure=0.5, edge_at_entry=0.02)
    mark = {"time_in_position_sessions": 2}
    same_side = pd.Series({"direction": "long", "edge": 0.01})
    target, reason = lifecycle_target(
        position, same_side, "ENTER_NOW", 1.0, mark, config, risk_capacity=1.0,
    )
    assert target == pytest.approx(0.5)
    assert reason == "hold_add_requires_future_marginal_edge"
    reverse = pd.Series({"direction": "short", "edge": 0.01})
    target, reason = lifecycle_target(
        position, reverse, "ENTER_NOW", -0.5, mark, config, risk_capacity=1.0,
    )
    assert target == pytest.approx(0.0)
    assert reason == "exit_reverse_edge_insufficient"


def test_lifecycle_does_not_reduce_healthy_edge_for_soft_size_shrink() -> None:
    config = structural_grid(_prereg())[0]
    position = PositionState(exposure=1.0, edge_at_entry=0.02)
    mark = {"time_in_position_sessions": 2}
    selected = pd.Series({"direction": "long", "edge": 0.019})
    target, reason = lifecycle_target(
        position, selected, "ENTER_NOW", 0.5, mark, config, risk_capacity=1.0,
    )
    assert target == pytest.approx(1.0)
    assert reason == "hold_reduction_requires_edge_or_hard_risk_deterioration"


def test_wait_cannot_bypass_binding_hard_risk_cap() -> None:
    config = structural_grid(_prereg())[0]
    position = PositionState(exposure=1.0, edge_at_entry=0.02)
    selected = pd.Series({"direction": "long", "edge": 0.019})
    target, reason = lifecycle_target(
        position, selected, "WAIT", 0.25, {"time_in_position_sessions": 2}, config,
        risk_capacity=1.0, hard_exposure_cap=0.25,
    )
    assert target == pytest.approx(0.25)
    assert reason == "reduce_hard_risk_cap"


def test_stale_pre_entry_mark_is_rejected_from_position_mtm() -> None:
    position = PositionState()
    apply_fill(
        position, target=1.0, fill_price=4.0, fill_time=ts("2010-07-03"),
        decision_index=3, remaining_edge=0.02, contract_id="NGQ10",
    )
    mark = mark_position(
        position, mark_price=2.0, decision_time=ts("2010-07-04"), decision_index=4,
        multiplier=10000.0, initial_capital=100000.0,
        mark_observation_time=ts("2010-07-02"),
    )
    assert mark["mark_valid_for_position"] is False
    assert mark["mark_rejection_reason"] == "mark_observation_precedes_position_entry"
    assert mark["current_contract_mtm_fraction"] == pytest.approx(0.0)
    assert mark["marked_equity_usd"] == pytest.approx(100000.0)


def test_execution_hard_cap_uses_actual_fill_price() -> None:
    position = PositionState()
    target, cap = enforce_execution_hard_cap(
        1.5, pd.Series({"derived_settle_m1": 4.0}), position,
        fill_price=10.0, max_abs_contracts=1.5,
        initial_margin_usd_per_contract=5000.0, contract_multiplier=10000.0,
        max_margin_fraction=1.0, max_notional_leverage=1.0,
        max_drawdown_fraction=0.25,
    )
    assert cap == pytest.approx(1.0)
    assert target == pytest.approx(1.0)


def test_marked_equity_drawdown_controls_hard_risk_capacity() -> None:
    position = PositionState()
    apply_fill(
        position, target=1.0, fill_price=4.0, fill_time=ts("2010-07-02"),
        decision_index=2, remaining_edge=0.02, contract_id="NGQ10",
    )
    mark_position(
        position, mark_price=2.0, decision_time=ts("2010-07-03"), decision_index=3,
        multiplier=10000.0, initial_capital=100000.0,
        mark_observation_time=ts("2010-07-03"),
    )
    assert position.marked_equity_usd == pytest.approx(80000.0)
    assert position.risk_drawdown_fraction == pytest.approx(0.20)
    _target, cap = enforce_execution_hard_cap(
        1.0, pd.Series({"derived_settle_m1": 2.0}), position,
        fill_price=2.0, max_abs_contracts=1.5,
        initial_margin_usd_per_contract=5000.0, contract_multiplier=10000.0,
        max_margin_fraction=1.0, max_notional_leverage=1.0,
        max_drawdown_fraction=0.15,
    )
    assert cap == pytest.approx(0.0)


def test_lifecycle_reduces_for_edge_deterioration_or_hard_risk_cap() -> None:
    config = structural_grid(_prereg())[0]
    position = PositionState(exposure=1.0, edge_at_entry=0.02)
    mark = {"time_in_position_sessions": 2}
    deteriorated = pd.Series({"direction": "long", "edge": 0.005})
    target, reason = lifecycle_target(
        position, deteriorated, "ENTER_NOW", 0.5, mark, config,
        risk_capacity=1.0, hard_exposure_cap=1.5,
    )
    assert target == pytest.approx(0.5)
    assert reason == "reduce_edge_deterioration"
    healthy = pd.Series({"direction": "long", "edge": 0.019})
    target, reason = lifecycle_target(
        position, healthy, "ENTER_NOW", 0.5, mark, config,
        risk_capacity=1.0, hard_exposure_cap=0.5,
    )
    assert target == pytest.approx(0.5)
    assert reason == "reduce_hard_risk_cap"


def test_meta_lifecycle_inputs_use_only_actual_direction_edge_and_policy() -> None:
    members = [
        {
            "direction": "short", "alpha": 0.55, "edge": 0.50, "uncertainty": 0.01,
            "timing": "ENTER_NOW", "add_edge_ratio": 1.50, "reduce_edge_ratio": 0.70,
            "reverse_edge_ratio": 1.80, "exit_edge_floor": 0.004, "max_hold_sessions": 40,
        },
        {
            "direction": "long", "alpha": 0.30, "edge": 0.01, "uncertainty": 0.02,
            "timing": "WAIT", "add_edge_ratio": 1.10, "reduce_edge_ratio": 0.50,
            "reverse_edge_ratio": 1.20, "exit_edge_floor": 0.002, "max_hold_sessions": 10,
        },
        {
            "direction": "long", "alpha": 0.15, "edge": 0.02, "uncertainty": 0.03,
            "timing": "ENTER_NOW", "add_edge_ratio": 1.20, "reduce_edge_ratio": 0.60,
            "reverse_edge_ratio": 1.40, "exit_edge_floor": 0.006, "max_hold_sessions": 20,
        },
    ]
    aligned = meta_lifecycle_inputs(
        members, current_exposure=-0.25, target_exposure=0.25,
    )
    assert aligned["lifecycle_direction"] == "long"
    assert aligned["direction_weight"] == pytest.approx(0.45)
    assert aligned["remaining_edge"] == pytest.approx(0.006)
    assert aligned["uncertainty"] == pytest.approx(0.0105)
    assert aligned["timing_decision"] == "WAIT"
    assert aligned["add_edge_ratio"] == pytest.approx((0.30 * 1.10 + 0.15 * 1.20) / 0.45)
    assert aligned["reduce_edge_ratio"] == pytest.approx((0.30 * 0.50 + 0.15 * 0.60) / 0.45)
    assert aligned["reverse_edge_ratio"] == pytest.approx((0.30 * 1.20 + 0.15 * 1.40) / 0.45)
    assert aligned["exit_edge_floor"] == pytest.approx((0.30 * 0.002 + 0.15 * 0.006) / 0.45)
    assert aligned["max_hold_sessions"] == pytest.approx((0.30 * 10 + 0.15 * 20) / 0.45)


def test_causal_prior_check_rejects_same_timestamp_outcome() -> None:
    brain = pd.DataFrame({
        "decision_time": [ts("2010-07-02"), ts("2010-07-03")],
        "max_outcome_available_at_used": [ts("2010-07-01"), ts("2010-07-03")],
    })
    assert causal_prior_check(brain) is False
    brain.loc[1, "max_outcome_available_at_used"] = ts("2010-07-02")
    assert causal_prior_check(brain) is True


def test_oracle_is_explicitly_nontradable_and_not_for_selection() -> None:
    base = pd.DataFrame({
        "decision_time": [ts("2010-07-02"), ts("2010-07-02")],
        "policy_id": ["a", "b"], "specialist": ["x", "y"],
        "horizon": [1, 1], "direction": ["long", "short"],
        "net_return": [0.01, 0.03],
    })
    diagnostic = oracle_first_diagnostic(base, [ts("2010-07-02")])
    assert diagnostic["selection_use"] is False
    assert diagnostic["development_only_nontradable"] is True
    assert diagnostic["oracle_net_return"] == pytest.approx(0.03)


def test_execution_stress_adds_slippage_and_deterministic_missed_fill() -> None:
    dates = pd.date_range("2010-07-01", periods=2, freq="D", tz="UTC")
    brain = pd.DataFrame({"decision_time": dates, "target_exposure": [1.0, 1.0]})
    state = pd.DataFrame({
        "decision_time": dates,
        "feature_curve_log_volume_m1": [0.0, 2.0],
        "derived_prior20_log_volume_m1_median": [1.0, 1.0],
    })
    path = pd.DataFrame({
        "decision_time": dates, "fill_contract_id": ["NGQ10", "NGQ10"],
        "path_move_per_mmbtu": [0.01, 0.01],
    })
    base = replay_targets_under_execution_stress(
        brain, state, path,
        {"id": "base", "extra_slippage_usd_per_contract_side": 0.0,
         "miss_increase_when_below_prior_volume": False},
    )
    stressed = replay_targets_under_execution_stress(
        brain, state, path,
        {"id": "moderate", "extra_slippage_usd_per_contract_side": 15.0,
         "miss_increase_when_below_prior_volume": True},
    )
    assert bool(stressed.iloc[0]["missed_fill"]) is True
    assert stressed.iloc[0]["executed_target"] == pytest.approx(0.0)
    assert base["realized_net_return"].sum() > stressed["realized_net_return"].sum()


def _meta_test_inputs(base_returns: list[float], stress_returns: list[float]):
    dates = pd.date_range("2010-01-01", periods=32, tz="UTC")
    policy = SidePolicy(
        "p", (5,), (1,), 1, 0.0, 0.0, 0.0, 99.0, 1.0, 20, 1.0, 0.5, 1.0, 0.0,
    )
    config = ControllerConfig("c1", policy, policy, 0.0, 10, 0.5, 1)
    decisions = pd.DataFrame({
        "decision_time": dates, "target_exposure": [0.5] * 32,
        "selected_weights": [{"s": 1.0}] * 32,
        "selected_group_weights": [{"g": 1.0}] * 32,
        "selected_horizon": [1] * 32, "selected_direction": ["long"] * 32,
        "selected_side_profile": ["p"] * 32, "timing_decision": ["ENTER_NOW"] * 32,
        "action": ["STARTER"] * 32, "lifecycle_reason": ["x"] * 32,
        "remaining_edge": [1.0] * 32, "uncertainty": [0.0] * 32,
        "opportunity_table": [[] for _ in range(32)],
        "active_families": [("g",)] * 32, "structural_update": [False] * 32,
        "sizing_inputs": [{} for _ in range(32)], "position_before": [{} for _ in range(32)],
    })
    base = CandidateReplay(config, decisions, pd.DataFrame({
        "outcome_available_at": dates[:len(base_returns)],
        "realized_net_return": base_returns,
    }))
    stress = CandidateReplay(config, decisions, pd.DataFrame({
        "outcome_available_at": dates[:len(stress_returns)],
        "realized_net_return": stress_returns,
    }))
    state = pd.DataFrame({"decision_time": dates, "derived_settle_m1": [4.0] * 32})
    path = pd.DataFrame({
        "decision_time": dates, "fill_contract_id": ["NG"] * 32,
        "fill_price": [4.0] * 32, "fill_timestamp": dates + pd.Timedelta(hours=1),
        "holding_outcome_available_at": dates + pd.Timedelta(hours=2),
        "holding_move_per_mmbtu": [0.0] * 32, "holding_session_count": [1] * 32,
        "holding_roll_count": [0] * 32, "holding_terminal_basis_price": [4.0] * 32,
        "holding_terminal_contract_id": ["NG"] * 32,
    })
    specialists = pd.DataFrame({"decision_time": dates, "s": [1.0] * 32})
    return dates, base, stress, state, path, specialists


def test_meta_stress_gate_fails_closed_when_required_history_is_incomplete() -> None:
    dates, base, stress, state, path, specialists = _meta_test_inputs(
        [0.01] * 31, [-1.0] * 29,
    )
    brain, _, _ = run_meta_controller(
        [base], {"severe": [stress]}, state, path, specialists=specialists,
        surfaces={stamp: pd.DataFrame() for stamp in dates},
        refs_by_time={stamp: [] for stamp in dates}, objective_window=30,
        ensemble_size=1, structural_cadence=10, stress_floor=-0.05,
    )
    score = brain.iloc[30]["candidate_objective_scores"][0]
    assert score["stress_complete"] is False
    assert score["missing_stress_scenarios"] == ["severe"]
    assert score["eligible"] is False
    assert brain.iloc[30]["eligible_candidate_count"] == 0
    assert brain.iloc[30]["target_exposure"] == pytest.approx(0.0)


def test_meta_structural_membership_is_held_between_slow_updates() -> None:
    dates, base, stress, state, path, specialists = _meta_test_inputs(
        [0.1] + [0.0] * 29 + [-0.2], [0.01] * 31,
    )
    brain, _, _ = run_meta_controller(
        [base], {"severe": [stress]}, state, path, specialists=specialists,
        surfaces={stamp: pd.DataFrame() for stamp in dates},
        refs_by_time={stamp: [] for stamp in dates}, objective_window=30,
        ensemble_size=1, structural_cadence=10, stress_floor=-0.05,
    )
    structural = brain.iloc[30]
    next_day = brain.iloc[31]
    assert bool(structural["structural_update"]) is True
    assert tuple(structural["active_structural_configs"]) == ("c1",)
    assert bool(next_day["structural_update"]) is False
    assert tuple(next_day["active_structural_configs"]) == ("c1",)
    assert [row["config_id"] for row in next_day["selected_ensemble"]] == ["c1"]
    assert next_day["selected_ensemble"][0]["blend_weight"] == pytest.approx(0.0)


def test_path_shape_features_include_slope_and_acceleration() -> None:
    features = path_shape_features([0.01, 0.02, 0.04, 0.07])
    assert features["terminal_return"] == pytest.approx(0.07)
    assert features["slope_per_session"] > 0.0
    assert features["acceleration_per_session2"] > 0.0


def test_foundation_horizon_signals_follow_matching_forecast_step() -> None:
    decision = ts("2010-07-02")
    expert_paths = pd.DataFrame({
        "decision_time": [decision],
        "timesfm_point_returns": [[0.01, 0.02, -0.03, -0.04, -0.05]],
        "kronos_close_returns": [[-0.01, -0.02, 0.03, 0.04, 0.05]],
    })
    signals = foundation_horizon_signals(expert_paths, (1, 3, 5))
    assert signals[decision][1]["timesfm_direction"] == pytest.approx(1.0)
    assert signals[decision][3]["timesfm_direction"] == pytest.approx(-1.0)
    assert signals[decision][3]["kronos_direction"] == pytest.approx(1.0)


def test_foundation_context_exposes_path_shape_quantile_width_and_disagreement() -> None:
    decision = ts("2010-07-02")
    expert_paths = pd.DataFrame({
        "decision_time": [decision],
        "timesfm_point_returns": [[0.01, 0.02, 0.03, 0.04, 0.05]],
        "timesfm_q10_returns": [[-0.01, 0.00, 0.01, 0.02, 0.03]],
        "timesfm_q90_returns": [[0.03, 0.04, 0.05, 0.06, 0.07]],
        "kronos_close_returns": [[0.00, 0.01, 0.02, 0.03, 0.04]],
        "model_disagreement_returns": [[0.01, 0.01, 0.01, 0.01, 0.01]],
        "model_disagreement_mean_abs": [0.01],
        "model_sign_disagreement_rate": [0.2],
        "timesfm_path_features": [{"slope_per_session": 0.01, "acceleration_per_session2": 0.002}],
        "kronos_path_features": [{"slope_per_session": 0.008, "acceleration_per_session2": 0.001}],
    })
    context = foundation_context_frame(expert_paths)
    assert set(FOUNDATION_CONTEXT_COLUMNS).issubset(context.columns)
    assert context.iloc[0]["expert_timesfm_slope"] == pytest.approx(0.01)
    assert context.iloc[0]["expert_timesfm_interval_width_h3"] == pytest.approx(0.04)
    assert context.iloc[0]["expert_model_disagreement_h5"] == pytest.approx(0.01)
    assert context.iloc[0]["expert_model_sign_disagreement_rate"] == pytest.approx(0.2)


def test_opportunity_support_uses_horizon_specific_foundation_signal() -> None:
    config = structural_grid(_prereg())[0]
    surface = pd.DataFrame({
        "specialist": ["timesfm_direction"], "horizon": [3], "direction": ["long"],
        "memory": [5], "count": [30], "mean_net_return": [0.01],
        "std_net_return": [0.001], "objective_30_net_return_sum": [0.30],
        "objective_30_std_net_return": [0.001], "objective_30_count": [30],
        "comparable_mean_net_return": [0.01], "direction_hit_rate": [0.8],
        "forecast_mae_return": [0.01], "interval_coverage": [0.8],
    })
    current = pd.Series({"timesfm_direction": 1.0})
    table = opportunity_table(
        surface, current, {"timesfm_direction": "timesfm"}, ("timesfm",), config,
        horizon_signal_overrides={3: {"timesfm_direction": -1.0}},
    )
    assert len(table) == 1
    assert table.iloc[0]["support"] == pytest.approx(0.0)


def test_rich_consequence_reprices_foundation_direction_at_each_horizon() -> None:
    decision = ts("2010-07-02")
    expert_paths = pd.DataFrame({
        "decision_time": [decision], "timesfm_point_returns": [[0.01, 0.02, -0.03]],
        "timesfm_q10_returns": [[-0.01, 0.00, -0.05]],
        "timesfm_q90_returns": [[0.03, 0.04, -0.01]],
        "kronos_close_returns": [[0.0, 0.0, 0.0]],
    })
    base = pd.DataFrame({
        "decision_time": [decision, decision], "outcome_available_at": [ts("2010-07-06")] * 2,
        "specialist": ["timesfm_direction"] * 2, "horizon": [3, 3],
        "direction": ["long", "short"], "signal": [1.0, 0.0],
        "turnover": [2.0, 0.0], "net_return": [0.1, 0.0],
    })
    path = pd.DataFrame({
        "decision_time": [decision], "fill_price": [4.0],
        "h3_move_per_mmbtu": [0.2], "h3_roll_count": [0.0],
    })
    rich = build_rich_expert_consequences(base, path, expert_paths=expert_paths)
    long_row = rich.loc[rich["direction"].eq("long")].iloc[0]
    short_row = rich.loc[rich["direction"].eq("short")].iloc[0]
    assert long_row["signal"] == pytest.approx(0.0)
    assert short_row["signal"] == pytest.approx(-1.0)
    assert short_row["net_return"] == pytest.approx((-2000.0 - 30.0) / 100000.0)


def test_foundation_forecast_error_uses_native_settle_target_not_execution_return() -> None:
    decision = ts("2010-07-02")
    future = ts("2010-07-03")
    expert_paths = pd.DataFrame({
        "decision_time": [decision], "trade_date": [ts("2010-07-01")],
        "contract_id": ["NGQ10"], "forecast_sessions": [[future]],
        "timesfm_point_returns": [[0.08]], "timesfm_q10_returns": [[0.02]],
        "timesfm_q90_returns": [[0.12]], "kronos_close_returns": [[0.06]],
    })
    canonical = pd.DataFrame({
        "trade_date": [ts("2010-07-01"), future], "contract_id": ["NGQ10", "NGQ10"],
        "settle": [4.0, 4.4], "available_at": [decision, ts("2010-07-04")],
    })
    ohlcv = pd.DataFrame({
        "trade_date": [ts("2010-07-01"), future], "contract_id": ["NGQ10", "NGQ10"],
        "close": [5.0, 5.5],
    })
    state = pd.DataFrame({
        "trade_date": [ts("2010-07-01"), future],
        "decision_time": [decision, ts("2010-07-04")],
    })
    actuals = build_foundation_actual_paths(expert_paths, canonical, ohlcv, state)
    base = pd.DataFrame({
        "decision_time": [decision], "outcome_available_at": [ts("2010-07-03")],
        "specialist": ["timesfm_direction"], "horizon": [1], "direction": ["long"],
        "signal": [1.0], "net_return": [0.01],
    })
    path = pd.DataFrame({
        "decision_time": [decision], "fill_price": [4.0], "h1_move_per_mmbtu": [0.1],
    })
    rich = build_rich_expert_consequences(
        base, path, expert_paths=expert_paths, foundation_actuals=actuals,
    ).iloc[0]
    assert rich["actual_return"] == pytest.approx(0.025)
    assert rich["forecast_actual_return"] == pytest.approx(0.10)
    assert rich["forecast_error_return"] == pytest.approx(-0.02)
    assert pd.Timestamp(rich["forecast_outcome_available_at"]) == ts("2010-07-04")


def test_rich_effectiveness_delays_forecast_metrics_until_native_target_is_available() -> None:
    dates = pd.date_range("2010-07-01", periods=5, freq="D", tz="UTC")
    consequences = pd.DataFrame({
        "decision_time": [dates[0]], "outcome_available_at": [dates[1]],
        "forecast_outcome_available_at": [dates[4]],
        "specialist": ["timesfm_direction"], "horizon": [1], "direction": ["long"],
        "net_return": [0.01], "direction_hit": [1.0], "direction_error": [0.0],
        "abs_forecast_error_return": [0.02], "forecast_error_return": [0.02],
        "interval_covered": [1.0], "interval_width": [0.04],
    })
    surface = rich_effectiveness_surface_for_day(consequences, dates[3], [])
    row = surface.loc[surface["memory"].eq("expanding")].iloc[0]
    assert row["direction_hit_rate"] == pytest.approx(1.0)
    assert pd.isna(row["forecast_mae_return"])
    mature = rich_effectiveness_surface_for_day(consequences, dates[4] + pd.Timedelta(seconds=1), [])
    mature_row = mature.loc[mature["memory"].eq("expanding")].iloc[0]
    assert mature_row["forecast_mae_return"] == pytest.approx(0.02)


def test_rich_effectiveness_surface_exposes_error_hit_and_calibration() -> None:
    dates = pd.date_range("2010-07-01", periods=3, freq="D", tz="UTC")
    consequences = pd.DataFrame({
        "decision_time": dates[:2], "outcome_available_at": dates[1:3],
        "specialist": ["timesfm_direction", "timesfm_direction"],
        "horizon": [1, 1], "direction": ["long", "long"],
        "net_return": [0.01, 0.02], "direction_hit": [1.0, 0.0],
        "direction_error": [0.0, 2.0], "abs_forecast_error_return": [0.01, 0.03],
        "forecast_error_return": [0.01, -0.03], "interval_covered": [1.0, 0.0],
        "interval_width": [0.04, 0.05],
    })
    surface = rich_effectiveness_surface_for_day(consequences, dates[2] + pd.Timedelta(days=1), [])
    row = surface.loc[surface["memory"].eq("expanding")].iloc[0]
    assert row["direction_hit_rate"] == pytest.approx(0.5)
    assert row["forecast_mae_return"] == pytest.approx(0.02)
    assert row["interval_coverage"] == pytest.approx(0.5)


def test_diagnostic_reliability_changes_rank_score_but_keeps_30_count_gate() -> None:
    config = structural_grid(_prereg())[0]
    surface = pd.DataFrame({
        "specialist": ["a", "b"], "horizon": [1, 1], "direction": ["long", "long"],
        "memory": [5, 5], "count": [30, 30],
        "mean_net_return": [0.01, 0.01], "std_net_return": [0.001, 0.001],
        "objective_30_net_return_sum": [0.30, 0.30],
        "objective_30_std_net_return": [0.001, 0.001], "objective_30_count": [30, 30],
        "comparable_mean_net_return": [0.01, 0.01],
        "direction_hit_rate": [0.8, 0.2], "forecast_mae_return": [None, None],
        "interval_coverage": [None, None],
    })
    scored = score_surface_for_side(surface, config, "long").set_index("specialist")
    assert scored.loc["a", "rank_score"] > scored.loc["b", "rank_score"]


def test_memory_scale_is_selected_independently_per_specialist_across_full_bank() -> None:
    config = next(row for row in structural_grid(_prereg()) if row.long_policy.profile_id == "fast")
    rows = []
    for specialist, preferred in (("a", 126), ("b", 5)):
        for memory in (5, 20, 126, "expanding"):
            value = 0.03 if memory == preferred else 0.005
            rows.append({
                "specialist": specialist, "horizon": 1, "direction": "long",
                "memory": memory, "count": 40, "mean_net_return": value,
                "std_net_return": 0.001, "objective_30_net_return_sum": 0.30,
                "objective_30_std_net_return": 0.001, "objective_30_count": 30,
                "comparable_mean_net_return": value, "direction_hit_rate": 0.7,
                "forecast_mae_return": None, "interval_coverage": None,
            })
    scored = score_surface_for_side(pd.DataFrame(rows), config, "long").set_index("specialist")
    assert scored.loc["a", "selected_memory"] == 126
    assert scored.loc["b", "selected_memory"] == 5
    assert scored.loc["a", "memory_weights"] == {"126": pytest.approx(1.0)}
    assert 126 not in config.long_policy.memories


def test_attribute_oracle_optimizes_exposure_across_horizons_and_sparse_ladder() -> None:
    dates = pd.date_range("2010-07-01", periods=4, freq="D", tz="UTC")
    state = pd.DataFrame({
        "decision_time": dates, "a": [0.0, 1.0, 2.0, 4.0], "b": [1.0, 1.0, 2.0, 3.0],
    })
    path = pd.DataFrame({
        "decision_time": dates,
        "h1_move_per_mmbtu": [0.1, 0.1, 0.1, 0.2],
        "h1_outcome_available_at": dates + pd.Timedelta(hours=12),
        "h1_roll_count": [0.0] * 4,
        "h3_move_per_mmbtu": [-0.2, -0.2, -0.2, -0.3],
        "h3_outcome_available_at": dates + pd.Timedelta(days=3),
        "h3_roll_count": [0.0] * 4,
    })
    oracle = hindsight_attribute_weight_oracle(
        state, ["a", "b"], path, horizons=(1, 3), sparse_ks=(1, 2), sparse_k=2,
        max_abs_contracts=1.5, exposure_step_contracts=0.25,
    )
    row = oracle.iloc[-1]
    assert row["oracle_exposure"] == pytest.approx(1.5)
    assert row["horizon_solutions"]["1"]["optimal_exposure"] == pytest.approx(1.5)
    assert row["horizon_solutions"]["3"]["optimal_exposure"] == pytest.approx(-1.5)
    assert set(row["horizon_solutions"]["1"]["sparse_solutions"]) == {"1", "2"}
    vector = row["normalized_attribute_vector"]
    dense = row["horizon_solutions"]["1"]["dense_weights"]
    reconstructed = sum(float(dense[name]) * float(vector[name]) for name in ("a", "b"))
    assert reconstructed == pytest.approx(1.5)


def test_full_attribute_oracle_and_predictor_are_strictly_prior() -> None:
    dates = pd.date_range("2010-07-01", periods=8, freq="D", tz="UTC")
    state = pd.DataFrame({"decision_time": dates, "a": range(8), "b": [1, 2, 1, 2, 3, 2, 4, 5]})
    path = pd.DataFrame({
        "decision_time": dates,
        "h1_move_per_mmbtu": [0.1, -0.1, 0.2, -0.2, 0.1, -0.1, 0.3, -0.3],
        "h1_outcome_available_at": dates + pd.Timedelta(hours=12),
        "h1_roll_count": [0.0] * 8,
        "h3_move_per_mmbtu": [0.2, -0.2, 0.1, -0.1, 0.2, -0.2, 0.4, -0.4],
        "h3_outcome_available_at": dates + pd.Timedelta(days=3),
        "h3_roll_count": [0.0] * 8,
    })
    oracle = hindsight_attribute_weight_oracle(
        state, ["a", "b"], path, sparse_k=2, sparse_ks=(1, 2), horizons=(1, 3),
    )
    assert len(oracle) == len(state)
    assert all(len(weights) == 2 for weights in oracle["dense_weights"])
    assert all(row is False for row in oracle["selection_use"])
    predictor = causal_oracle_weight_predictor(
        state, oracle, ["a", "b"], k=3, sparse_k=2, horizons=(1, 3),
    )
    assert oracle_predictor_causal_check(predictor)
    used = predictor.loc[predictor["training_label_count"] > 0]
    assert (pd.to_datetime(used["max_label_available_at"], utc=True) < pd.to_datetime(used["decision_time"], utc=True)).all()
    assert "predicted_exposure" in predictor.columns
    assert all(abs(float(value) * 4.0 - round(float(value) * 4.0)) < 1e-12 for value in predictor["predicted_exposure"])
    assert all(abs(float(value)) <= 1.5 for value in predictor["predicted_exposure"])
    assert all(set(value) == {"1", "3"} for value in predictor["horizon_predictions"])


def test_oracle_predictor_excludes_unobserved_current_outcome_from_evaluation() -> None:
    state = pd.DataFrame({
        "decision_time": pd.to_datetime(["2010-01-01", "2010-01-03"], utc=True),
        "x": [1.0, 2.0],
    })
    prior = {
        "outcome_available_at": pd.Timestamp("2010-01-02", tz="UTC"),
        "oracle_outcome_observed": True,
        "optimal_exposure": 1.0, "optimal_side": 1,
        "sparse_solutions": {"1": {"weights": {"x": 1.0}}},
    }
    unobserved = {
        "outcome_available_at": pd.NaT,
        "oracle_outcome_observed": False,
        "optimal_exposure": 0.0, "optimal_side": 0,
        "sparse_solutions": {"1": {"weights": {}}},
    }
    oracle = pd.DataFrame({
        "decision_time": state["decision_time"],
        "horizon_solutions": [{"1": prior}, {"1": unobserved}],
    })
    predictor = causal_oracle_weight_predictor(
        state, oracle, ["x"], k=1, sparse_k=1, horizons=(1,),
    )
    payload = predictor.iloc[1]["horizon_predictions"]["1"]
    assert payload["oracle_outcome_observed"] is False
    assert payload["oracle_exposure_error_abs"] is None
    assert payload["oracle_side_hit"] is None
    assert payload["oracle_top_attribute_hit"] is None


def test_primitive_oracle_winner_predictor_targets_policy_identity_strictly_prior() -> None:
    dates = pd.date_range("2010-07-01", periods=7, freq="D", tz="UTC")
    state = pd.DataFrame({
        "decision_time": dates,
        "a": [0.0, 0.1, 0.2, 3.0, 3.1, 3.2, 0.15],
        "b": [1.0, 1.1, 0.9, -1.0, -1.1, -0.9, 1.05],
    })
    rows = []
    for index, stamp in enumerate(dates):
        winner = "policy-long" if index < 3 or index == 6 else "policy-short"
        for policy_id, specialist, direction in (
            ("policy-long", "attr_a", "long"),
            ("policy-short", "attr_b", "short"),
        ):
            rows.append({
                "decision_time": stamp,
                "outcome_available_at": stamp + pd.Timedelta(hours=12),
                "policy_id": policy_id,
                "specialist": specialist,
                "horizon": 1,
                "direction": direction,
                "net_return": 0.02 if policy_id == winner else -0.01,
            })
    oracle = oracle_first_diagnostic(pd.DataFrame(rows), list(dates))
    predictor = causal_primitive_oracle_winner_predictor(
        state, oracle["winner_by_day"], ["a", "b"], k=3,
    )
    assert oracle_predictor_causal_check(predictor)
    used = predictor.loc[predictor["training_label_count"] > 0]
    assert (pd.to_datetime(used["max_label_available_at"], utc=True) < pd.to_datetime(used["decision_time"], utc=True)).all()
    assert set(used["predicted_policy_id"].dropna()).issubset({"policy-long", "policy-short"})
    assert set(predictor["target_type"]) == {"primitive_policy_id"}
    assert set(predictor["selection_use"]) == {False}
    assert predictor.iloc[-1]["actual_policy_id"] == "policy-long"
