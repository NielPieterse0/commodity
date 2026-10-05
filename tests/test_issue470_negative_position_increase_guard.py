from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from commodity.v2_adaptive_controller_v3 import (
    CandidateReplay,
    ControllerConfig,
    PositionState,
    SidePolicy,
    apply_realized_return,
    lifecycle_target,
    run_meta_controller,
)
from commodity.v3_replay_engine import _lifecycle_target as compact_lifecycle_target


def _policy() -> SidePolicy:
    return SidePolicy(
        profile_id="test", memories=(20,), horizons=(20,), top_k=1,
        wait_support_floor=0.0, enter_support_floor=0.0,
        enter_confidence_floor=0.0, max_vol_ratio=10.0, size_scale=1.0,
        max_hold_sessions=99, add_edge_ratio=1.0, reduce_edge_ratio=0.5,
        reverse_edge_ratio=1.0, exit_edge_floor=-1.0,
    )


def _config() -> ControllerConfig:
    policy = _policy()
    return ControllerConfig(
        config_id="issue470-test", long_policy=policy, short_policy=policy,
        comparable_weight=0.0, slow_cadence=1, uncertainty_penalty=0.0,
        active_family_cap=1,
    )


def _selected(direction: str = "long", edge: float = 2.0) -> pd.Series:
    return pd.Series({"direction": direction, "edge": edge})


def _mark(economic_path: float, *, unrealized: float | None = None) -> dict[str, float | int]:
    return {
        "time_in_position_sessions": 2,
        "economic_path_pnl_fraction": economic_path,
        "unrealized_pnl_fraction": economic_path if unrealized is None else unrealized,
    }


@pytest.mark.parametrize(
    ("economic_path", "expected_target", "expected_reason"),
    [
        (-0.01, 1.0, "hold_add_negative_matured_position_path"),
        (0.0, 1.5, "add_future_marginal_edge_and_capacity"),
        (0.01, 1.5, "add_future_marginal_edge_and_capacity"),
    ],
)
def test_same_side_add_uses_matured_current_instance_path_only(
    economic_path: float, expected_target: float, expected_reason: str,
) -> None:
    position = PositionState(exposure=1.0, edge_at_entry=1.0)
    target, reason = lifecycle_target(
        position, _selected(), "ENTER_NOW", 1.5, _mark(economic_path), _config(),
        risk_capacity=1.0, hard_exposure_cap=1.5,
    )
    assert target == pytest.approx(expected_target)
    assert reason == expected_reason


def test_unmatured_mark_loss_does_not_block_add() -> None:
    position = PositionState(exposure=1.0, edge_at_entry=1.0)
    target, reason = lifecycle_target(
        position, _selected(), "ENTER_NOW", 1.5,
        _mark(0.0, unrealized=-0.25), _config(),
        risk_capacity=1.0, hard_exposure_cap=1.5,
    )
    assert target == pytest.approx(1.5)
    assert reason == "add_future_marginal_edge_and_capacity"


def test_hard_risk_reduction_precedes_negative_path_guard() -> None:
    position = PositionState(exposure=1.0, edge_at_entry=1.0)
    target, reason = lifecycle_target(
        position, _selected(), "ENTER_NOW", 1.5, _mark(-0.25), _config(),
        risk_capacity=1.0, hard_exposure_cap=0.5,
    )
    assert target == pytest.approx(0.5)
    assert reason == "reduce_hard_risk_cap"


def test_prior_position_instance_loss_cannot_poison_current_instance() -> None:
    position = PositionState(exposure=1.0, edge_at_entry=1.0, instance_id=2)
    apply_realized_return(
        position, -0.2, 100000.0, position_instance_id=1,
        terminal_basis_price=2.5, contract_id="old",
    )
    assert position.economic_path_pnl_fraction == pytest.approx(0.0)
    target, reason = lifecycle_target(
        position, _selected(), "ENTER_NOW", 1.5, _mark(0.0), _config(),
        risk_capacity=1.0, hard_exposure_cap=1.5,
    )
    assert target == pytest.approx(1.5)
    assert reason == "add_future_marginal_edge_and_capacity"


def test_compact_lifecycle_matches_negative_path_add_guard() -> None:
    target, reason_code = compact_lifecycle_target(
        current=1.0, selected=True, timing=2, edge=2.0,
        desired_target=1.5, direction=1, edge_at_entry=1.0, age=2,
        risk_capacity=1.0, hard_exposure_cap=1.5, max_hold_sessions=99,
        add_edge_ratio=1.0, reduce_edge_ratio=0.5, reverse_edge_ratio=1.0,
        exit_edge_floor=-1.0, economic_path_pnl=-0.01,
    )
    assert target == pytest.approx(1.0)
    assert reason_code == 16


def test_scope_audit_age_metadata_key_does_not_match_managed_money() -> None:
    audit_path = (
        Path(__file__).resolve().parents[1]
        / "scripts/research/audit_issue465_block1_controller_v3_completeness.py"
    )
    spec = importlib.util.spec_from_file_location("issue470_v3_audit", audit_path)
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    assert audit._is_age_metadata_key("market_age_seconds")
    assert audit._is_age_metadata_key("positioning_age_sessions")
    assert not audit._is_age_metadata_key("managed_money_net")


def test_checkpoint_identity_binds_compact_replay_engine() -> None:
    runner_path = (
        Path(__file__).resolve().parents[1]
        / "scripts/research/run_issue465_block1_controller_v3.py"
    )
    spec = importlib.util.spec_from_file_location("issue470_v3_runner", runner_path)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    identity = runner.current_code_identity()
    assert identity["v3_replay_engine_sha256"] == runner.sha256_file(
        Path(__file__).resolve().parents[1] / "src/commodity/v3_replay_engine.py"
    )


def _meta_guard_inputs(*, mature_loss_before_add: bool) -> tuple[
    list[pd.Timestamp], CandidateReplay, pd.DataFrame, pd.DataFrame,
    dict[pd.Timestamp, list[pd.Timestamp]], dict[pd.Timestamp, pd.DataFrame], pd.DataFrame,
]:
    dates = list(pd.date_range("2010-01-01", periods=32, tz="UTC"))
    targets = [0.0] * 30 + [0.5, 1.0]
    decisions = pd.DataFrame({
        "decision_time": dates,
        "target_exposure": targets,
        "selected_weights": [{"s": 1.0}] * len(dates),
        "selected_group_weights": [{"g": 1.0}] * len(dates),
        "selected_horizon": [20] * len(dates),
        "selected_direction": ["long"] * len(dates),
        "selected_side_profile": ["test"] * len(dates),
        "timing_decision": ["ENTER_NOW"] * len(dates),
        "action": ["HOLD"] * 30 + ["STARTER", "ADD"],
        "lifecycle_reason": ["test"] * len(dates),
        "remaining_edge": [2.0] * len(dates),
        "uncertainty": [0.0] * len(dates),
        "opportunity_table": [[] for _ in dates],
        "active_families": [("g",)] * len(dates),
        "structural_update": [False] * len(dates),
        "sizing_inputs": [{} for _ in dates],
        "position_before": [{} for _ in dates],
    })
    consequences = pd.DataFrame({
        "decision_time": dates,
        "outcome_available_at": [stamp + pd.Timedelta(hours=12) for stamp in dates],
        "holding_session_count": [1] * len(dates),
        "realized_net_return": [0.01] * len(dates),
    })
    replay = CandidateReplay(_config(), decisions, consequences)
    state = pd.DataFrame({
        "decision_time": dates,
        "derived_settle_m1": [4.0] * len(dates),
        "market_observation_time": dates,
    })
    specialists = pd.DataFrame({"decision_time": dates, "s": [1.0] * len(dates)})
    refs = {stamp: [] for stamp in dates}
    surfaces = {stamp: pd.DataFrame() for stamp in dates}
    outcome_available = [stamp + pd.Timedelta(hours=12) for stamp in dates]
    if not mature_loss_before_add:
        outcome_available[30] = dates[31]
    path = pd.DataFrame({
        "decision_time": dates,
        "fill_timestamp": [stamp + pd.Timedelta(hours=1) for stamp in dates],
        "fill_price": [4.0] * len(dates),
        "fill_contract_id": ["NG"] * len(dates),
        "holding_outcome_available_at": outcome_available,
        "holding_move_per_mmbtu": [0.0] * 30 + [-0.1, 0.0],
        "holding_session_count": [1] * len(dates),
        "holding_roll_count": [0] * len(dates),
        "holding_terminal_basis_price": [4.0] * len(dates),
        "holding_terminal_contract_id": ["NG"] * len(dates),
    })
    return dates, replay, state, specialists, refs, surfaces, path


def _run_meta_guard(*, mature_loss_before_add: bool, path_override: pd.DataFrame | None = None):
    dates, replay, state, specialists, refs, surfaces, path = _meta_guard_inputs(
        mature_loss_before_add=mature_loss_before_add
    )
    if path_override is not None:
        path = path_override
    brain, _, _ = run_meta_controller(
        [replay], {"severe": [replay]}, state, path,
        specialists=specialists, surfaces=surfaces, refs_by_time=refs,
        objective_window=30, ensemble_size=1, structural_cadence=10,
        stress_floor=-0.05, cost_per_side=0.0,
    )
    return dates, brain, path


def test_meta_controller_blocks_add_on_negative_matured_current_position_path() -> None:
    dates, brain, _ = _run_meta_guard(mature_loss_before_add=True)
    starter = brain.loc[brain["decision_time"] == dates[30]].iloc[0]
    add = brain.loc[brain["decision_time"] == dates[31]].iloc[0]
    assert starter["target_exposure"] == pytest.approx(0.5)
    assert float(add["position_before"]["economic_path_pnl_fraction"]) < 0.0
    assert add["target_exposure"] == pytest.approx(0.5)
    assert add["meta_lifecycle_reason"] == "hold_add_negative_matured_position_path"


def test_meta_controller_does_not_use_outcome_available_exactly_at_decision_time() -> None:
    dates, brain, _ = _run_meta_guard(mature_loss_before_add=False)
    add = brain.loc[brain["decision_time"] == dates[31]].iloc[0]
    assert add["position_before"]["economic_path_pnl_fraction"] == pytest.approx(0.0)
    assert add["target_exposure"] == pytest.approx(1.0)
    assert add["meta_lifecycle_reason"] == "ensemble_target_accepted"


def test_meta_guard_decision_is_invariant_to_future_path_outcome() -> None:
    dates, baseline, path = _run_meta_guard(mature_loss_before_add=True)
    changed_path = path.copy(deep=True)
    changed_path.loc[31, "holding_move_per_mmbtu"] = 99.0
    _, changed, _ = _run_meta_guard(
        mature_loss_before_add=True, path_override=changed_path
    )
    columns = ["decision_time", "target_exposure", "meta_lifecycle_reason", "position_before"]
    pd.testing.assert_frame_equal(
        baseline.loc[baseline["decision_time"] <= dates[31], columns].reset_index(drop=True),
        changed.loc[changed["decision_time"] <= dates[31], columns].reset_index(drop=True),
    )
