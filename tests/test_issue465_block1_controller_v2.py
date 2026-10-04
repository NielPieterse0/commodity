from __future__ import annotations

import pandas as pd
import pytest

from commodity.v2_adaptive_controller_v2 import (
    CandidateReplay,
    ControllerConfig,
    PositionState,
    apply_fill,
    build_base_consequences,
    causal_attribute_specialists,
    dynamic_target_exposure,
    effectiveness_surface_for_day,
    execution_turnover,
    opportunity_table,
    replay_candidate,
    run_meta_controller,
    score_surface,
    structural_grid,
)


def ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def _prereg() -> dict:
    return {
        "structural_search": {
            "memory_profiles": {"short": [5, 10, 20], "balanced": [10, 20, 40], "medium": [20, 40, 60], "long": [40, 60, 126, "expanding"]},
            "top_k_specialists": [2, 4, 6], "slow_cadence_sessions": [10, 20],
            "asymmetric": [True, False], "uncertainty_penalty": 0.5,
            "expected_candidate_count": 144,
        },
        "comparable_state": {"weights": [0.0, 0.25, 0.5]},
    }


def test_structural_grid_matches_frozen_144_candidate_contract() -> None:
    configs = structural_grid(_prereg())
    assert len(configs) == 144
    assert len({config.config_id for config in configs}) == 144
    assert {config.slow_cadence for config in configs} == {10, 20}
    assert {config.asymmetric for config in configs} == {True, False}


def test_effectiveness_surface_uses_only_matured_prior_outcomes() -> None:
    base = pd.DataFrame({
        "decision_time": [ts("2010-07-01"), ts("2010-07-02"), ts("2010-07-03")],
        "outcome_available_at": [ts("2010-07-02"), ts("2010-07-03"), ts("2010-07-04")],
        "specialist": ["a", "a", "a"], "horizon": [1, 1, 1],
        "direction": ["long", "long", "long"], "net_return": [0.1, 0.2, 99.0],
    })
    surface = effectiveness_surface_for_day(
        base, ts("2010-07-04"), [ts("2010-07-02")], memories=(5, "expanding")
    )
    expanding = surface.loc[surface["memory"] == "expanding"].iloc[0]
    assert expanding["count"] == 2
    assert expanding["mean_net_return"] == pytest.approx(0.15)
    assert expanding["comparable_mean_net_return"] == pytest.approx(0.2)


def test_base_consequences_separate_long_and_short_economics() -> None:
    dates = pd.date_range("2010-07-01", periods=3, freq="D", tz="UTC")
    specialists = pd.DataFrame({"decision_time": dates, "s": [1.0, -1.0, 1.0]})
    path = pd.DataFrame({
        "decision_time": dates, "outcome_available_at": dates + pd.Timedelta(hours=12),
        "path_move_per_mmbtu": [0.01, -0.01, 0.01],
    })
    result = build_base_consequences(specialists, path, horizons=(1,), cost_per_side_usd=0.0)
    long_rows = result.loc[result["direction"] == "long"]
    short_rows = result.loc[result["direction"] == "short"]
    assert long_rows["net_return"].sum() > 0.0
    assert short_rows["net_return"].sum() > 0.0


def _config(*, asymmetric: bool = True, cadence: int = 2) -> ControllerConfig:
    return ControllerConfig(
        config_id=f"toy-{asymmetric}-{cadence}", memory_profile=(5,),
        comparable_weight=0.0, top_k=2, slow_cadence=cadence,
        asymmetric=asymmetric, uncertainty_penalty=0.0,
    )


def test_symmetric_control_uses_same_specialist_ranking_by_side() -> None:
    surface = pd.DataFrame({
        "specialist": ["a", "a", "b", "b"], "horizon": [1, 1, 1, 1],
        "direction": ["long", "short", "long", "short"],
        "memory": [5, 5, 5, 5], "count": [5] * 4,
        "mean_net_return": [0.30, 0.10, 0.10, 0.30], "std_net_return": [0.0] * 4,
        "objective_30_count": [30] * 4,
        "objective_30_net_return_sum": [0.30, 0.10, 0.10, 0.30],
        "objective_30_mean_net_return": [0.01] * 4,
        "objective_30_std_net_return": [0.0] * 4,
        "comparable_mean_net_return": [0.0] * 4, "comparable_std_net_return": [0.0] * 4,
        "comparable_count": [0] * 4,
    })
    scored = score_surface(surface, _config(asymmetric=False))
    table = opportunity_table(
        scored, pd.Series({"a": 1.0, "b": -1.0}), {"a": "x", "b": "y"},
        ("x", "y"), _config(asymmetric=False),
    )
    long_weights = table.loc[table["direction"] == "long", "weights"].iloc[0]
    short_weights = table.loc[table["direction"] == "short", "weights"].iloc[0]
    assert long_weights == short_weights


def test_dynamic_sizing_is_bounded_and_drawdown_sensitive() -> None:
    opportunity = pd.Series({"edge": 0.02, "uncertainty": 0.01, "support": 1.0, "direction": "long"})
    state = pd.Series({"feature_vol_20": 1.0, "derived_prior60_vol20_median": 1.0,
                       "feature_curve_log_volume_m1": 2.0, "derived_prior20_log_volume_m1_median": 1.0})
    fresh = PositionState(equity_usd=100000.0, peak_equity_usd=100000.0)
    drawdown = PositionState(equity_usd=70000.0, peak_equity_usd=100000.0)
    fresh_target, _ = dynamic_target_exposure(opportunity, state, fresh, max_abs_contracts=1.5)
    drawdown_target, _ = dynamic_target_exposure(opportunity, state, drawdown, max_abs_contracts=1.5)
    assert 0.0 <= fresh_target <= 1.5
    assert abs(drawdown_target) <= abs(fresh_target)


def test_position_fill_tracks_entry_and_add_weighted_price() -> None:
    position = PositionState()
    apply_fill(position, target=0.75, fill_price=4.0, fill_time=ts("2010-07-02"), remaining_edge=0.02)
    assert position.entry_price == pytest.approx(4.0)
    assert position.edge_at_entry == pytest.approx(0.02)
    apply_fill(position, target=1.5, fill_price=5.0, fill_time=ts("2010-07-03"), remaining_edge=0.03)
    assert position.entry_price == pytest.approx(4.5)
    apply_fill(position, target=0.0, fill_price=5.1, fill_time=ts("2010-07-04"), remaining_edge=0.0)
    assert position.entry_price is None
    assert position.exposure == 0.0


def _toy_replay_inputs(rows: int = 8):
    dates = pd.date_range("2010-07-01", periods=rows, freq="D", tz="UTC")
    state = pd.DataFrame({
        "decision_time": dates, "derived_settle_m1": [4.0] * rows,
        "feature_vol_20": [1.0] * rows, "derived_prior60_vol20_median": [1.0] * rows,
        "feature_curve_log_volume_m1": [2.0] * rows,
        "derived_prior20_log_volume_m1_median": [1.0] * rows,
    })
    specialists = pd.DataFrame({"decision_time": dates, "a": [1.0] * rows})
    path = pd.DataFrame({
        "decision_time": dates, "fill_timestamp": dates + pd.Timedelta(hours=1),
        "fill_contract_id": ["NG"] * rows, "fill_price": [4.0] * rows,
        "outcome_available_at": dates + pd.Timedelta(hours=12),
        "path_move_per_mmbtu": [0.01] * rows,
    })
    surface = pd.DataFrame({
        "specialist": ["a"], "horizon": [1], "direction": ["long"], "memory": [5],
        "count": [5], "mean_net_return": [0.01], "std_net_return": [0.001],
        "objective_30_count": [30], "objective_30_net_return_sum": [0.10],
        "objective_30_mean_net_return": [0.0033], "objective_30_std_net_return": [0.001],
        "comparable_count": [0], "comparable_mean_net_return": [0.0], "comparable_std_net_return": [0.0],
    })
    surfaces = {stamp: surface for stamp in dates}
    refs = {stamp: [] for stamp in dates}
    return state, specialists, path, surfaces, refs


def test_replay_candidate_separates_slow_and_fast_adaptation() -> None:
    state, specialists, path, surfaces, refs = _toy_replay_inputs()
    replay = replay_candidate(
        _config(asymmetric=True, cadence=2), state, specialists, path,
        surfaces, refs, {"a": "trend"}, cost_per_side=0.0,
    )
    assert replay.decisions["structural_update"].tolist() == [True, False, True, False, True, False, True, False]
    assert replay.decisions["target_exposure"].max() <= 1.5
    assert replay.decisions["active_families"].map(lambda value: tuple(value) == ("trend",)).all()


def _meta_replay(config_id: str, returns: list[float], targets: list[float]) -> CandidateReplay:
    dates = pd.date_range("2010-07-01", periods=len(returns), freq="D", tz="UTC")
    config = ControllerConfig(config_id, (5,), 0.0, 1, 2, True, 0.0)
    decisions = pd.DataFrame({
        "decision_time": dates, "target_exposure": targets,
        "remaining_edge": [0.01] * len(dates), "uncertainty": [0.001] * len(dates),
        "selected_weights": [{"a": 1.0}] * len(dates),
        "selected_group_weights": [{"trend": 1.0}] * len(dates),
        "selected_horizon": [1] * len(dates), "selected_direction": ["long"] * len(dates),
        "opportunity_table": [[]] * len(dates),
    })
    consequences = pd.DataFrame({
        "decision_time": dates, "outcome_available_at": dates + pd.Timedelta(hours=12),
        "signal": targets, "turnover": [0.0] * len(dates), "realized_net_return": returns,
    })
    return CandidateReplay(config, decisions, consequences, {})


def _meta_state_path(rows: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2010-07-01", periods=rows, freq="D", tz="UTC")
    state = pd.DataFrame({"decision_time": dates, "derived_settle_m1": [4.0] * rows})
    path = pd.DataFrame({
        "decision_time": dates,
        "fill_timestamp": dates + pd.Timedelta(hours=1),
        "fill_contract_id": ["NG"] * rows,
        "fill_price": [4.0] * rows,
        "outcome_available_at": dates + pd.Timedelta(hours=12),
        "path_move_per_mmbtu": [0.01] * rows,
    })
    return state, path


def _meta_archive_inputs(state: pd.DataFrame):
    dates = pd.to_datetime(state["decision_time"], utc=True)
    specialists = pd.DataFrame({"decision_time": dates, "a": [1.0] * len(state)})
    surface = pd.DataFrame({
        "specialist": ["a"], "horizon": [1], "direction": ["long"], "memory": [5],
        "count": [5], "mean_net_return": [0.01], "std_net_return": [0.001],
        "objective_30_count": [30], "objective_30_net_return_sum": [0.10],
        "objective_30_mean_net_return": [0.0033], "objective_30_std_net_return": [0.001],
        "comparable_count": [1], "comparable_mean_net_return": [0.01], "comparable_std_net_return": [0.0],
    })
    surfaces = {pd.Timestamp(stamp): surface.copy() for stamp in dates}
    refs = {
        pd.Timestamp(stamp): ([pd.Timestamp(dates.iloc[0])] if index > 0 else [])
        for index, stamp in enumerate(dates)
    }
    return specialists, surfaces, refs


def test_meta_controller_uses_only_prior_matured_candidate_returns() -> None:
    a = _meta_replay("a", [0.01] * 6 + [-99.0], [1.0] * 7)
    b = _meta_replay("b", [0.0] * 7, [0.0] * 7)
    state, path = _meta_state_path()
    specialists, surfaces, refs = _meta_archive_inputs(state)
    brain, _consequences, _freeze = run_meta_controller(
        [a, b], state, path, {"a": "trend"},
        specialists=specialists, surfaces=surfaces, refs_by_time=refs,
        objective_window=5, cost_per_side=0.0,
    )
    row = brain.iloc[5]
    assert row["selected_ensemble"][0]["config_id"] == "a"
    assert row["max_outcome_available_at_used"] < row["decision_time"]


def test_future_candidate_outcome_cannot_change_current_meta_selection() -> None:
    a = _meta_replay("a", [0.01] * 7, [1.0] * 7)
    b = _meta_replay("b", [0.0] * 7, [0.0] * 7)
    state, path = _meta_state_path()
    specialists, surfaces, refs = _meta_archive_inputs(state)
    baseline, _consequences, _freeze = run_meta_controller(
        [a, b], state, path, {"a": "trend"},
        specialists=specialists, surfaces=surfaces, refs_by_time=refs,
        objective_window=5, cost_per_side=0.0,
    )
    a2 = _meta_replay("a", [0.01] * 6 + [-100.0], [1.0] * 7)
    changed, _consequences2, _freeze2 = run_meta_controller(
        [a2, b], state, path, {"a": "trend"},
        specialists=specialists, surfaces=surfaces, refs_by_time=refs,
        objective_window=5, cost_per_side=0.0,
    )
    cols = ["decision_time", "selected_ensemble", "target_exposure"]
    pd.testing.assert_frame_equal(baseline.loc[:5, cols], changed.loc[:5, cols])


def test_meta_controller_archives_complete_predecision_brain_and_separate_consequence() -> None:
    a = _meta_replay("a", [0.01] * 7, [1.0] * 7)
    b = _meta_replay("b", [0.0] * 7, [0.0] * 7)
    state, path = _meta_state_path()
    specialists, surfaces, refs = _meta_archive_inputs(state)
    brain, consequences, _freeze = run_meta_controller(
        [a, b], state, path, {"a": "trend"},
        specialists=specialists, surfaces=surfaces, refs_by_time=refs,
        objective_window=5, structural_cadence=2, cost_per_side=0.0,
    )
    row = brain.iloc[5]
    assert row["pit_state"]["derived_settle_m1"] == pytest.approx(4.0)
    assert row["specialist_signals"] == {"a": 1.0}
    assert row["comparable_state_refs"] == [pd.Timestamp(state.iloc[0]["decision_time"]).isoformat()]
    assert row["effectiveness_surface"][0]["memory"] == 5
    assert len(row["candidate_objective_scores"]) == 2
    assert row["structural_state"]["last_structural_update_time"] == pd.Timestamp(
        state.iloc[5]["decision_time"]
    ).isoformat()
    assert row["adaptation_state"]["fast_daily_update"] is True
    assert row["risk_state"]["hard_exposure_cap"] >= abs(row["target_exposure"])
    assert row["execution_assumptions"]["fill_price_source"] == "attached_after_decision"
    assert "realized_net_return" not in row.index
    assert "fill_price" not in row["execution_assumptions"]
    consequence = consequences.iloc[5]
    assert consequence["fill_price"] == pytest.approx(4.0)
    assert consequence["path_move_per_mmbtu"] == pytest.approx(0.01)
    assert consequence["realized_net_return"] > 0.0


def test_attribute_specialists_are_prior_only_and_sparse_capable() -> None:
    dates = pd.date_range("2010-07-01", periods=7, freq="D", tz="UTC")
    state = pd.DataFrame({"decision_time": dates, "feature_x": [1, 1, 1, 1, 1, 2, -99]})
    signals = causal_attribute_specialists(state, ["feature_x"], lookback=5, min_periods=5)
    direct = signals["attr__feature_x__direct"]
    assert direct.iloc[:5].eq(0.0).all()
    assert direct.iloc[5] == 1.0
    assert direct.iloc[6] == -1.0
    assert signals["attr__feature_x__inverse"].iloc[5] == -1.0


def test_forward_horizon_consequence_uses_terminal_availability_and_roll_costs() -> None:
    dates = pd.date_range("2010-07-01", periods=2, freq="D", tz="UTC")
    specialists = pd.DataFrame({"decision_time": dates, "s": [1.0, 1.0]})
    path = pd.DataFrame({
        "decision_time": dates,
        "h3_move_per_mmbtu": [0.06, float("nan")],
        "h3_outcome_available_at": [ts("2010-07-05"), pd.NaT],
        "h3_roll_count": [1.0, float("nan")],
    })
    result = build_base_consequences(specialists, path, horizons=(3,), cost_per_side_usd=15.0)
    row = result.loc[result["direction"] == "long"].iloc[0]
    assert row["outcome_available_at"] == ts("2010-07-05")
    assert row["turnover"] == pytest.approx(4.0)
    assert row["net_return"] == pytest.approx((0.06 * 10000.0 - 60.0) / 100000.0)


def test_execution_turnover_charges_close_and_reopen_on_contract_roll() -> None:
    same = execution_turnover(1.0, 1.0, current_contract_id="NGQ10", target_contract_id="NGQ10")
    rolled = execution_turnover(1.0, 1.0, current_contract_id="NGQ10", target_contract_id="NGU10")
    reduced_roll = execution_turnover(1.0, 0.5, current_contract_id="NGQ10", target_contract_id="NGU10")
    assert same == pytest.approx(0.0)
    assert rolled == pytest.approx(2.0)
    assert reduced_roll == pytest.approx(1.5)
