from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import commodity.v2_adaptive_controller_v3 as v3
from commodity.v2_adaptive_controller_v2 import (
    precompute_comparable_refs,
    precompute_surfaces,
)
from commodity.v2_adaptive_controller_v3 import (
    CandidateReplay,
    ControllerConfig,
    SidePolicy,
    oracle_first_diagnostic,
    precompute_profile_score_cache,
    profile_score_cache_key,
    score_surface_for_side,
)
from commodity.v2_adaptive_controller_v3_diagnostics import (
    causal_oracle_weight_predictor,
    causal_primitive_oracle_winner_predictor,
    oracle_weight_predictor_causal_projection,
    precompute_rich_surfaces_incremental,
    primitive_oracle_predictor_causal_projection,
    rich_effectiveness_surface_for_day,
)


def _policy() -> SidePolicy:
    return SidePolicy(
        "p", (5,), (1,), 1, 0.0, 0.0, 0.0, 99.0, 1.0, 20,
        1.0, 0.5, 1.0, 0.0,
    )


def _config() -> ControllerConfig:
    policy = _policy()
    return ControllerConfig("c1", policy, policy, 0.0, 10, 0.5, 1)


def _candidate_inputs(fill_price: float):
    stamp = pd.Timestamp("2010-07-01", tz="UTC")
    state = pd.DataFrame({
        "decision_time": [stamp], "derived_settle_m1": [4.0],
        "market_observation_time": [stamp],
    })
    specialists = pd.DataFrame({"decision_time": [stamp], "s": [1.0]})
    path = pd.DataFrame({
        "decision_time": [stamp], "fill_timestamp": [stamp + pd.Timedelta(hours=1)],
        "fill_price": [fill_price], "fill_contract_id": ["NGQ10"],
        "holding_outcome_available_at": [stamp + pd.Timedelta(days=1)],
        "holding_move_per_mmbtu": [0.1], "holding_session_count": [1],
        "holding_roll_count": [0], "holding_terminal_basis_price": [4.1],
        "holding_terminal_contract_id": ["NGQ10"],
    })
    return stamp, state, specialists, path


def test_candidate_decision_target_is_invariant_to_post_decision_fill_price(monkeypatch) -> None:
    selected = pd.Series({
        "direction": "long", "edge": 0.05, "uncertainty": 0.0,
        "support": 1.0, "confidence": 1.0, "weights": {"s": 1.0}, "horizon": 1,
    })
    monkeypatch.setattr(v3, "opportunity_table", lambda *args, **kwargs: pd.DataFrame([selected]))
    monkeypatch.setattr(v3, "select_timed_opportunity", lambda *args, **kwargs: (selected, "ENTER_NOW"))
    monkeypatch.setattr(
        v3, "dynamic_target_exposure",
        lambda *args, **kwargs: (1.5, {"risk_capacity": 1.0, "hard_exposure_cap": 1.5}),
    )

    rows = []
    for fill_price in (4.0, 100.0):
        stamp, state, specialists, path = _candidate_inputs(fill_price)
        replay = v3.replay_candidate(
            _config(), state, specialists, path,
            {stamp: pd.DataFrame()}, {stamp: []}, {"s": "g"},
            execution_scenario={"id": "base"},
        )
        rows.append(replay.decisions.iloc[0])

    assert rows[0]["target_exposure"] == pytest.approx(1.5)
    assert rows[1]["target_exposure"] == pytest.approx(1.5)
    assert rows[0]["executed_target_exposure"] == pytest.approx(1.5)
    assert rows[1]["executed_target_exposure"] == pytest.approx(0.1)
    assert rows[0]["execution_audit"]["available_at"] == rows[0]["planned_fill_time"]


def _meta_replay_inputs():
    dates = pd.date_range("2010-01-01", periods=32, tz="UTC")
    config = _config()
    decisions = pd.DataFrame({
        "decision_time": dates, "target_exposure": [0.5] * len(dates),
        "selected_weights": [{"s": 1.0}] * len(dates),
        "selected_group_weights": [{"g": 1.0}] * len(dates),
        "selected_horizon": [1] * len(dates), "selected_direction": ["long"] * len(dates),
        "selected_side_profile": ["p"] * len(dates), "timing_decision": ["ENTER_NOW"] * len(dates),
        "action": ["STARTER"] * len(dates), "lifecycle_reason": ["x"] * len(dates),
        "remaining_edge": [1.0] * len(dates), "uncertainty": [0.0] * len(dates),
        "opportunity_table": [[] for _ in dates], "active_families": [("g",)] * len(dates),
        "structural_update": [False] * len(dates), "sizing_inputs": [{} for _ in dates],
        "position_before": [{} for _ in dates],
    })
    consequences = pd.DataFrame({
        "decision_time": dates, "outcome_available_at": dates + pd.Timedelta(hours=12),
        "holding_session_count": [1] * len(dates), "realized_net_return": [0.01] * len(dates),
    })
    replay = CandidateReplay(config, decisions, consequences)
    state = pd.DataFrame({
        "decision_time": dates, "derived_settle_m1": [4.0] * len(dates),
        "market_observation_time": dates,
    })
    specialists = pd.DataFrame({"decision_time": dates, "s": [1.0] * len(dates)})
    refs = {stamp: [] for stamp in dates}
    surfaces = {stamp: pd.DataFrame() for stamp in dates}
    return dates, replay, state, specialists, refs, surfaces


def _meta_path(dates, structural_fill_price: float) -> pd.DataFrame:
    fill_prices = [4.0] * len(dates)
    fill_prices[30] = structural_fill_price
    return pd.DataFrame({
        "decision_time": dates, "fill_timestamp": dates + pd.Timedelta(hours=1),
        "fill_price": fill_prices, "fill_contract_id": ["NG"] * len(dates),
        "holding_outcome_available_at": dates + pd.Timedelta(hours=12),
        "holding_move_per_mmbtu": [0.0] * len(dates), "holding_session_count": [1] * len(dates),
        "holding_roll_count": [0] * len(dates), "holding_terminal_basis_price": [4.0] * len(dates),
        "holding_terminal_contract_id": ["NG"] * len(dates),
    })


def test_meta_decision_target_is_invariant_to_post_decision_fill_price() -> None:
    dates, replay, state, specialists, refs, surfaces = _meta_replay_inputs()
    outputs = []
    for fill_price in (4.0, 100.0):
        brain, _, _ = v3.run_meta_controller(
            [replay], {"severe": [replay]}, state, _meta_path(dates, fill_price),
            specialists=specialists, surfaces=surfaces, refs_by_time=refs,
            objective_window=30, ensemble_size=1, structural_cadence=10, stress_floor=-0.05,
        )
        outputs.append(brain.iloc[30])
    assert outputs[0]["target_exposure"] == pytest.approx(0.5)
    assert outputs[1]["target_exposure"] == pytest.approx(0.5)
    assert outputs[0]["executed_target_exposure"] == pytest.approx(0.5)
    assert outputs[1]["executed_target_exposure"] == pytest.approx(0.1)


def _oracle_row(stamp: pd.Timestamp, available: pd.Timestamp, exposure: float) -> dict:
    side = int(exposure > 0) - int(exposure < 0)
    return {
        "decision_time": stamp,
        "horizon_solutions": {
            "1": {
                "outcome_available_at": available,
                "oracle_outcome_observed": True,
                "optimal_exposure": exposure,
                "optimal_side": side,
                "sparse_solutions": {"1": {"weights": {"x": exposure}}},
            }
        },
    }


def test_oracle_weight_causal_projection_ignores_future_only_evaluation_changes() -> None:
    dates = pd.to_datetime(["2010-01-01", "2010-01-03", "2010-01-05"], utc=True)
    state = pd.DataFrame({"decision_time": dates, "x": [1.0, 2.0, 3.0]})
    original = pd.DataFrame([
        _oracle_row(dates[0], pd.Timestamp("2010-01-02", tz="UTC"), 1.0),
        _oracle_row(dates[1], pd.Timestamp("2010-01-04", tz="UTC"), 1.0),
        _oracle_row(dates[2], pd.Timestamp("2010-01-06", tz="UTC"), 1.0),
    ])
    mutated = original.copy(deep=True)
    mutated.at[2, "horizon_solutions"] = _oracle_row(
        dates[2], pd.Timestamp("2010-01-06", tz="UTC"), -1.0
    )["horizon_solutions"]
    before = causal_oracle_weight_predictor(
        state, original, ["x"], k=2, sparse_k=1, horizons=(1,),
    )
    after = causal_oracle_weight_predictor(
        state, mutated, ["x"], k=2, sparse_k=1, horizons=(1,),
    )
    assert before.iloc[-1]["horizon_predictions"] != after.iloc[-1]["horizon_predictions"]
    assert oracle_weight_predictor_causal_projection(before).equals(
        oracle_weight_predictor_causal_projection(after)
    )


def test_comparable_refs_can_be_precomputed_without_legacy_surfaces() -> None:
    dates = pd.date_range("2010-01-01", periods=4, freq="D", tz="UTC")
    context = pd.DataFrame({
        "decision_time": dates,
        "x": [0.0, 1.0, 0.2, 0.9],
        "y": [0.0, 0.5, 0.1, 0.6],
    })
    consequences = pd.DataFrame({
        "decision_time": dates,
        "outcome_available_at": dates + pd.Timedelta(hours=12),
        "specialist": ["s"] * 4,
        "horizon": [1] * 4,
        "direction": ["long"] * 4,
        "net_return": [0.01, -0.02, 0.03, 0.04],
    })
    _, legacy_refs = precompute_surfaces(
        consequences, context, context_columns=["x", "y"], k=2
    )
    refs = precompute_comparable_refs(
        context, context_columns=["x", "y"], k=2
    )
    assert refs == legacy_refs


def test_incremental_rich_surfaces_match_reference_day_by_day() -> None:
    dates = pd.date_range("2010-01-01", periods=6, freq="D", tz="UTC")
    consequences = pd.DataFrame({
        "decision_time": list(dates[:4]) * 2,
        "outcome_available_at": list(dates[1:5]) * 2,
        "forecast_outcome_available_at": list(dates[2:6]) * 2,
        "specialist": ["a"] * 4 + ["b"] * 4,
        "horizon": [1] * 8,
        "direction": ["long"] * 4 + ["short"] * 4,
        "net_return": [0.01, -0.02, 0.03, 0.04, -0.01, 0.02, -0.03, 0.05],
        "direction_hit": [1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0],
        "direction_error": [0.0, 2.0, 0.0, 0.0, 2.0, 0.0, 2.0, 0.0],
        "abs_forecast_error_return": [0.01] * 8,
        "forecast_error_return": [0.01, -0.01] * 4,
        "interval_covered": [1.0, 0.0] * 4,
        "interval_width": [0.04, 0.05] * 4,
    })
    refs = {stamp: list(dates[: max(0, i - 1)])[-2:] for i, stamp in enumerate(dates)}
    context = pd.DataFrame({"decision_time": dates})
    actual = precompute_rich_surfaces_incremental(consequences, context, refs)
    for stamp in dates:
        expected = rich_effectiveness_surface_for_day(consequences, stamp, refs[stamp])
        pd.testing.assert_frame_equal(actual[stamp], expected, check_exact=True)


def _primitive_policy_row(
    decision_time: pd.Timestamp, available_at: pd.Timestamp,
    policy_id: str, net_return: float, horizon: int,
) -> dict:
    return {
        "decision_time": decision_time,
        "outcome_available_at": available_at,
        "policy_id": policy_id,
        "specialist": policy_id,
        "horizon": horizon,
        "direction": "long",
        "net_return": net_return,
    }


def test_primitive_oracle_winner_label_matures_after_all_competitors() -> None:
    decision = pd.Timestamp("2010-01-01", tz="UTC")
    short_available = pd.Timestamp("2010-01-02", tz="UTC")
    long_available = pd.Timestamp("2010-01-10", tz="UTC")
    consequences = pd.DataFrame([
        _primitive_policy_row(decision, short_available, "short", 0.10, 1),
        _primitive_policy_row(decision, long_available, "long", 0.05, 20),
    ])
    oracle = oracle_first_diagnostic(consequences, [decision])
    assert oracle["winner_by_day"][decision.isoformat()]["policy_id"] == "short"
    assert oracle["winner_by_day"][decision.isoformat()]["outcome_available_at"] == long_available


def test_primitive_predictor_prefix_ignores_not_yet_mature_winner_change() -> None:
    decision = pd.Timestamp("2010-01-01", tz="UTC")
    cutoff = pd.Timestamp("2010-01-05", tz="UTC")
    long_available = pd.Timestamp("2010-01-10", tz="UTC")
    state = pd.DataFrame({
        "decision_time": [decision, cutoff, pd.Timestamp("2010-01-12", tz="UTC")],
        "x": [0.0, 1.0, 2.0],
    })
    original = pd.DataFrame([
        _primitive_policy_row(decision, pd.Timestamp("2010-01-02", tz="UTC"), "short", 0.10, 1),
        _primitive_policy_row(decision, long_available, "long", 0.05, 20),
    ])
    mutated = original.copy()
    mutated.loc[mutated["policy_id"].eq("long"), "net_return"] = 0.20
    before_labels = oracle_first_diagnostic(original, [decision])["winner_by_day"]
    after_labels = oracle_first_diagnostic(mutated, [decision])["winner_by_day"]
    before = causal_primitive_oracle_winner_predictor(state, before_labels, ["x"], k=1)
    after = causal_primitive_oracle_winner_predictor(state, after_labels, ["x"], k=1)
    prefix_before = primitive_oracle_predictor_causal_projection(before)
    prefix_after = primitive_oracle_predictor_causal_projection(after)
    prefix_before = prefix_before.loc[prefix_before["decision_time"].le(cutoff)]
    prefix_after = prefix_after.loc[prefix_after["decision_time"].le(cutoff)]
    pd.testing.assert_frame_equal(prefix_before, prefix_after, check_exact=True)


def test_meta_compact_surface_record_preserves_decision_semantics() -> None:
    dates, replay, state, specialists, refs, surfaces = _meta_replay_inputs()
    surfaces[dates[30]] = pd.DataFrame([{
        "specialist": "s", "horizon": 1, "direction": "long", "memory": 5,
        "count": 30, "mean_net_return": 0.01,
        "objective_30_net_return_sum": 0.3, "comparable_count": 0,
        "comparable_mean_net_return": 0.0,
    }])
    kwargs = {
        "specialists": specialists, "surfaces": surfaces, "refs_by_time": refs,
        "objective_window": 30, "ensemble_size": 1, "structural_cadence": 10,
        "stress_floor": -0.05,
    }
    embedded, _, _ = v3.run_meta_controller(
        [replay], {"severe": [replay]}, state, _meta_path(dates, 4.0), **kwargs
    )
    compact, _, _ = v3.run_meta_controller(
        [replay], {"severe": [replay]}, state, _meta_path(dates, 4.0),
        embed_effectiveness_surface=False, **kwargs,
    )
    assert "effectiveness_surface" in embedded.columns
    assert "effectiveness_surface" not in compact.columns
    assert compact.iloc[30]["effectiveness_surface_row_count"] == 1
    assert compact.iloc[30]["effectiveness_surface_id"] == dates[30].isoformat()
    pd.testing.assert_frame_equal(
        embedded.drop(columns=["effectiveness_surface"]), compact, check_exact=True
    )


def test_profile_score_cache_matches_uncached_reference_exactly() -> None:
    stamp = pd.Timestamp("2010-01-01", tz="UTC")
    surface = pd.DataFrame({
        "specialist": ["a", "b"], "horizon": [1, 1],
        "direction": ["long", "long"], "memory": [5, 5],
        "count": [30, 30], "mean_net_return": [0.02, 0.01],
        "std_net_return": [0.01, 0.02],
        "objective_30_count": [30, 30],
        "objective_30_net_return_sum": [0.3, 0.2],
        "objective_30_std_net_return": [0.01, 0.02],
        "comparable_mean_net_return": [0.01, 0.03],
        "direction_hit_rate": [0.6, 0.7],
        "forecast_mae_return": [0.01, 0.02],
        "interval_coverage": [0.8, 0.9],
    })
    config = _config()
    expected = score_surface_for_side(surface, config, "long")
    cache = precompute_profile_score_cache({stamp: surface}, [config])
    actual = cache[profile_score_cache_key(stamp, config, "long")]
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)



def test_meta_score_tensor_matches_dataframe_reference_at_maturity_boundaries() -> None:
    decision_times = pd.to_datetime([
        "2010-01-02", "2010-01-03", "2010-01-05", "2010-01-06",
    ], utc=True)
    available = pd.to_datetime([
        "2010-01-02", "2010-01-03", "2010-01-04", "2010-01-05",
    ], utc=True)
    consequences = pd.DataFrame({
        "outcome_available_at": available,
        "holding_session_count": [2, 1, 3, 1],
        "realized_net_return": [0.01, 0.02, 0.03, 0.04],
    })
    base = CandidateReplay(_config(), pd.DataFrame(), consequences)
    stress_consequences = consequences.copy()
    stress_consequences["realized_net_return"] *= -2.0
    stress = CandidateReplay(_config(), pd.DataFrame(), stress_consequences)

    tensor = v3.build_meta_score_tensor(
        [base], {"severe": [stress]}, decision_times, window=3,
    )
    assert tensor.candidate_ids == ("c1",)
    assert tensor.scenario_ids == ("base", "severe")
    for scenario_id, replay in (("base", base), ("severe", stress)):
        for decision_index, decision_time in enumerate(decision_times):
            expected = v3._matured_candidate_score(
                replay.consequences, decision_time, window=3,
            )
            actual = tensor.score_at(scenario_id, "c1", decision_index)
            if expected is None:
                assert actual is None
            else:
                assert actual is not None
                assert actual[0] == pytest.approx(expected[0], abs=0.0)
                assert actual[1] == expected[1]



def test_meta_controller_uses_score_tensor_instead_of_dataframe_rescans(monkeypatch) -> None:
    dates, replay, state, specialists, refs, surfaces = _meta_replay_inputs()

    def fail_legacy_score(*args, **kwargs):
        raise AssertionError("legacy DataFrame score path used")

    monkeypatch.setattr(v3, "_matured_candidate_score", fail_legacy_score)
    brain, _, _ = v3.run_meta_controller(
        [replay], {"severe": [replay]}, state, _meta_path(dates, 4.0),
        specialists=specialists, surfaces=surfaces, refs_by_time=refs,
        objective_window=30, ensemble_size=1, structural_cadence=10,
        stress_floor=-0.05,
    )
    assert brain.iloc[30]["eligible_candidate_count"] == 1
    assert brain.iloc[30]["active_structural_configs"] == ("c1",)



def _planned_candidate_inputs():
    dates = pd.date_range("2010-02-01", periods=5, freq="D", tz="UTC")
    state = pd.DataFrame({
        "decision_time": dates,
        "derived_settle_m1": [4.00, 4.02, 4.01, 4.05, 4.04],
        "market_observation_time": dates,
        "feature_vol_20": [0.02] * len(dates),
        "derived_prior60_vol20_median": [0.02] * len(dates),
        "feature_curve_log_volume_m1": [10.0] * len(dates),
        "derived_prior20_log_volume_m1_median": [9.0] * len(dates),
    })
    specialists = pd.DataFrame({"decision_time": dates, "s": [1.0] * len(dates)})
    fill = [4.01, 4.03, 4.02, 4.06, 4.05]
    path = pd.DataFrame({
        "decision_time": dates,
        "fill_timestamp": dates + pd.Timedelta(hours=1),
        "fill_price": fill,
        "fill_contract_id": ["NG"] * len(dates),
        "holding_outcome_available_at": dates + pd.Timedelta(hours=12),
        "holding_move_per_mmbtu": [0.01, -0.01, 0.02, -0.01, 0.0],
        "holding_session_count": [1] * len(dates),
        "holding_roll_count": [0] * len(dates),
        "holding_terminal_basis_price": [value + 0.01 for value in fill],
        "holding_terminal_contract_id": ["NG"] * len(dates),
    })
    surface = pd.DataFrame({
        "specialist": ["s"], "horizon": [1], "direction": ["long"], "memory": [5],
        "count": [30], "mean_net_return": [0.02], "std_net_return": [0.01],
        "objective_30_count": [30], "objective_30_net_return_sum": [0.30],
        "objective_30_std_net_return": [0.01], "comparable_mean_net_return": [0.02],
        "direction_hit_rate": [0.7], "forecast_mae_return": [0.01],
        "interval_coverage": [0.8],
    })
    surfaces = {stamp: surface.copy() for stamp in dates}
    refs = {stamp: [] for stamp in dates}
    return dates, state, specialists, path, surfaces, refs


def test_candidate_decision_plan_reuse_preserves_exact_replay_semantics() -> None:
    _, state, specialists, path, surfaces, refs = _planned_candidate_inputs()
    config = _config()
    families = {"s": "g"}
    plan = v3.prepare_candidate_decision_plan(
        config, state, specialists, surfaces, families,
    )
    assert plan.selected_direction.dtype.name == "int8"
    assert plan.edge.dtype.name == "float64"
    assert plan.structural_update.dtype.name == "bool"
    for scenario in (
        {"id": "base"},
        {"id": "stress", "extra_slippage_usd_per_contract_side": 25.0,
         "miss_increase_when_below_prior_volume": True},
    ):
        expected = v3.replay_candidate(
            config, state, specialists, path, surfaces, refs, families,
            execution_scenario=scenario,
        )
        actual = v3.replay_candidate(
            config, state, specialists, path, surfaces, refs, families,
            execution_scenario=scenario, decision_plan=plan,
        )
        pd.testing.assert_frame_equal(actual.decisions, expected.decisions, check_exact=True)
        pd.testing.assert_frame_equal(actual.consequences, expected.consequences, check_exact=True)
        assert actual.summary == expected.summary



def test_candidate_scenario_batch_prepares_decision_plan_once(monkeypatch) -> None:
    _, state, specialists, path, surfaces, refs = _planned_candidate_inputs()
    config = _config()
    families = {"s": "g"}
    calls = 0
    kernel_input_calls = 0
    original = v3.prepare_candidate_decision_plan
    original_kernel_inputs = v3.prepare_replay_kernel_inputs

    def counted_plan(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    def counted_kernel_inputs(*args, **kwargs):
        nonlocal kernel_input_calls
        kernel_input_calls += 1
        return original_kernel_inputs(*args, **kwargs)

    monkeypatch.setattr(v3, "prepare_candidate_decision_plan", counted_plan)
    monkeypatch.setattr(v3, "prepare_replay_kernel_inputs", counted_kernel_inputs)
    replays = v3.replay_candidate_scenarios(
        config, state, specialists, path, surfaces, refs, families,
        execution_scenarios=(
            {"id": "base"},
            {"id": "stress", "extra_slippage_usd_per_contract_side": 25.0},
        ),
    )
    assert calls == 1
    assert kernel_input_calls == 1
    assert tuple(replays) == ("base", "stress")


def test_compact_serial_replay_kernel_matches_reference_numerics_exactly() -> None:
    from commodity.v3_replay_engine import (
        LIFECYCLE_REASON_LABELS,
        ReplayKernelLimits,
        prepare_replay_kernel_inputs,
        run_replay_kernel_serial,
    )

    dates, state, specialists, path, surfaces, refs = _planned_candidate_inputs()
    state = state.copy()
    path = path.copy()
    state["feature_curve_log_volume_m1"] = [10.0, 8.0, 10.0, 8.0, 10.0]
    path["holding_outcome_available_at"] = [
        dates[2] + pd.Timedelta(hours=12),
        dates[2] + pd.Timedelta(hours=6),
        dates[3] + pd.Timedelta(hours=12),
        dates[4] + pd.Timedelta(hours=12),
        dates[4] + pd.Timedelta(hours=12),
    ]
    config = _config()
    families = {"s": "g"}
    scenario = {
        "id": "stress",
        "extra_slippage_usd_per_contract_side": 25.0,
        "miss_increase_when_below_prior_volume": True,
    }
    plan = v3.prepare_candidate_decision_plan(
        config, state, specialists, surfaces, families,
    )
    expected = v3.replay_candidate(
        config, state, specialists, path, surfaces, refs, families,
        execution_scenario=scenario, decision_plan=plan,
    )
    inputs = prepare_replay_kernel_inputs(config, state, path, plan)
    limits = ReplayKernelLimits(
        max_abs_contracts=1.5,
        initial_capital=100000.0,
        multiplier=10000.0,
        base_cost_per_side=15.0,
        initial_margin_usd_per_contract=5000.0,
        max_margin_fraction=0.15,
        max_notional_leverage=1.0,
        max_drawdown_fraction=0.25,
    )
    actual = run_replay_kernel_serial(
        inputs, limits,
        extra_slippage_usd_per_contract_side=25.0,
        miss_increase_when_below_prior_volume=True,
    )
    decision_columns = {
        "decision_target": "target_exposure",
        "executed_target": "executed_target_exposure",
        "remaining_edge": "remaining_edge",
        "uncertainty": "uncertainty",
    }
    for actual_name, expected_name in decision_columns.items():
        np.testing.assert_array_equal(
            getattr(actual, actual_name),
            expected.decisions[expected_name].to_numpy(dtype=float),
        )
    consequence_columns = {
        "signal": "signal",
        "turnover": "turnover",
        "gross_return": "gross_return",
        "execution_cost_return": "execution_cost_return",
        "realized_net_return": "realized_net_return",
        "notional_leverage": "notional_leverage",
        "margin_fraction": "margin_fraction",
    }
    for actual_name, expected_name in consequence_columns.items():
        np.testing.assert_array_equal(
            getattr(actual, actual_name),
            expected.consequences[expected_name].to_numpy(dtype=float),
        )
    np.testing.assert_array_equal(
        actual.missed_fill,
        expected.decisions["missed_fill"].to_numpy(dtype=bool),
    )
    assert [LIFECYCLE_REASON_LABELS[int(code)] for code in actual.lifecycle_reason] == list(
        expected.decisions["lifecycle_reason"]
    )
    np.testing.assert_array_equal(
        actual.position_exposure_before,
        np.asarray([row["exposure"] for row in expected.decisions["position_before"]], dtype=float),
    )
    np.testing.assert_array_equal(
        actual.position_equity_before,
        np.asarray([row["equity_usd"] for row in expected.decisions["position_before"]], dtype=float),
    )


def test_candidate_scenario_batch_matches_reference_replays_exactly() -> None:
    _, state, specialists, path, surfaces, refs = _planned_candidate_inputs()
    state = state.copy()
    state["feature_curve_log_volume_m1"] = [10.0, 8.0, 10.0, 8.0, 10.0]
    config = _config()
    families = {"s": "g"}
    scenarios = (
        {"id": "base"},
        {
            "id": "stress",
            "extra_slippage_usd_per_contract_side": 25.0,
            "miss_increase_when_below_prior_volume": True,
        },
    )
    expected = {
        str(scenario["id"]): v3.replay_candidate(
            config, state, specialists, path, surfaces, refs, families,
            execution_scenario=scenario,
        )
        for scenario in scenarios
    }
    actual = v3.replay_candidate_scenarios(
        config, state, specialists, path, surfaces, refs, families,
        execution_scenarios=scenarios,
    )
    for scenario_id, reference in expected.items():
        pd.testing.assert_frame_equal(actual[scenario_id].decisions, reference.decisions, check_exact=True)
        pd.testing.assert_frame_equal(
            actual[scenario_id].consequences, reference.consequences, check_exact=True
        )
        assert actual[scenario_id].summary == reference.summary
