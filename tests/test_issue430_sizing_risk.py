from __future__ import annotations

import importlib
from pathlib import Path


def test_issue430_sizing_module_exists() -> None:
    spec = importlib.util.find_spec("commodity.v2_sizing_risk")
    assert spec is not None

import pandas as pd
import pytest

from commodity import v2_sizing_risk as sizing


def _policy(positions: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2022-01-03", periods=len(positions), freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "fill_trade_date": dates,
            "signal_timestamp": dates + pd.Timedelta(hours=12),
            "fill_timestamp": dates + pd.Timedelta(hours=14),
            "target_end_timestamp": dates + pd.Timedelta(days=3, hours=14),
            "signal_requested_position": positions,
            "primary_strength": [1.0] * len(positions),
            "jump_high": [False] * len(positions),
            "vol_of_vol_high": [False] * len(positions),
            "joint_regime": ["normal"] * len(positions),
        }
    )


def test_fixed_research_scale_can_exceed_one_contract() -> None:
    out = sizing.apply_sizing_policy(_policy([1.0, -1.0, 0.0]), {"base_scale": 2.0})
    assert out["signal_requested_position"].tolist() == [2.0, -2.0, 0.0]


def test_sizing_applies_side_and_tail_multipliers_without_direction_flip() -> None:
    policy = _policy([1.0, -1.0, -1.0])
    policy["jump_high"] = [False, True, False]
    policy["vol_of_vol_high"] = [False, False, True]
    out = sizing.apply_sizing_policy(
        policy,
        {
            "base_scale": 2.0,
            "long_scale": 0.5,
            "short_scale": 1.0,
            "jump_high_scale": 0.5,
            "vol_of_vol_high_scale": 0.25,
        },
    )
    assert out["signal_requested_position"].tolist() == [1.0, -1.0, -0.5]


def test_sizing_uses_stable_favored_fraction_confidence_tiers() -> None:
    policy = _policy([1.0, -1.0])
    policy["favored_fraction"] = [0.4, 0.8]
    out = sizing.apply_sizing_policy(
        policy,
        {"confidence_threshold": 2 / 3, "low_confidence_scale": 0.5, "high_confidence_scale": 1.5},
    )
    assert out["signal_requested_position"].tolist() == [0.5, -1.5]


def test_sizing_applies_prior_regime_scale_and_contract_cap() -> None:
    policy = _policy([1.0, -1.0])
    policy["joint_regime"] = ["favored", "other"]
    out = sizing.apply_sizing_policy(
        policy,
        {
            "base_scale": 3.0,
            "favorable_regimes": ["favored"],
            "favorable_regime_scale": 1.5,
            "other_regime_scale": 0.5,
            "max_abs_contracts": 4.0,
        },
    )
    assert out["signal_requested_position"].tolist() == [4.0, -1.5]


def test_sizing_rejects_protected_evidence() -> None:
    policy = _policy([1.0])
    policy.loc[0, "fill_trade_date"] = pd.Timestamp("2023-01-03", tz="UTC")
    policy.loc[0, "signal_timestamp"] = pd.Timestamp("2023-01-03 12:00", tz="UTC")
    policy.loc[0, "fill_timestamp"] = pd.Timestamp("2023-01-03 14:00", tz="UTC")
    policy.loc[0, "target_end_timestamp"] = pd.Timestamp("2023-01-04 14:00", tz="UTC")
    with pytest.raises(ValueError, match="protected"):
        sizing.apply_sizing_policy(policy, {"base_scale": 2.0})


def test_sizing_rejects_nonfinite_positions_and_scales() -> None:
    policy = _policy([1.0])
    policy.loc[0, "signal_requested_position"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        sizing.apply_sizing_policy(policy, {"base_scale": 1.0})
    with pytest.raises(ValueError, match="finite"):
        sizing.apply_sizing_policy(_policy([1.0]), {"base_scale": float("inf")})


def _sessions_for_replay() -> pd.DataFrame:
    dates = pd.date_range("2022-01-03", periods=3, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "trade_date": dates,
            "session_open": dates + pd.Timedelta(hours=14),
            "contract_id": ["NGF22"] * 3,
            "next_selected_contract_id": ["NGF22", "NGF22", None],
            "path_move_per_mmbtu": [0.01, 0.01, 0.0],
            "open_price": [3.0, 3.1, 3.2],
        }
    )


def _risk_and_costs():
    from commodity.trading_decision_v0 import ExecutionCostAssumptions, PaperRiskPolicy

    risk = PaperRiskPolicy(100_000.0, 1, 0.02, 0.10, "remain_flat", False)
    costs = ExecutionCostAssumptions(0.0, 0.0, 0.0, 0.0, 5_000.0, 10.0)
    return risk, costs


def test_research_replay_separates_contracts_margin_and_notional_leverage() -> None:
    policy = _policy([2.0]).assign(forecast_id=["f0"])
    risk, costs = _risk_and_costs()
    ledger, summary = sizing.replay_research_policy(
        _sessions_for_replay(), policy, risk, costs,
        contract_multiplier=10_000.0, max_abs_contracts=4.0,
    )
    assert ledger["target_position"].abs().max() == 2.0
    assert summary["operational_paper_max_contracts"] == 1
    assert summary["research_max_abs_contracts"] == 2.0
    assert summary["max_margin_utilization_fraction"] == pytest.approx(0.10)
    expected_peak_leverage = (2.0 * 3.1 * 10_000.0) / 100_200.0
    assert summary["max_notional_leverage"] == pytest.approx(expected_peak_leverage)


def test_research_replay_still_rejects_insufficient_margin() -> None:
    policy = _policy([25.0]).assign(forecast_id=["f0"])
    risk, costs = _risk_and_costs()
    ledger, summary = sizing.replay_research_policy(
        _sessions_for_replay(), policy, risk, costs,
        contract_multiplier=10_000.0, max_abs_contracts=30.0,
    )
    assert ledger["target_position"].eq(0.0).all()
    assert "insufficient_margin_assumption" in set(ledger["no_trade_reason"].dropna())
    assert summary["max_margin_utilization_fraction"] == 0.0


def test_issue430_runner_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    runner = root / "scripts" / "research" / "run_issue430_sizing_risk.py"
    assert runner.exists()


def test_runner_loads_frozen_prereg_and_budget() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    prereg = issue430.load_prereg()
    assert prereg["status"] == "frozen_before_issue430_scoring"
    assert len(prereg["stage1_sizing"]["policy_configs"]) == 26
    assert len(prereg["stage2_risk"]["risk_variants"]) == 9
    assert prereg["trial_accounting"]["declared_total_trial_upper_bound"] == 318


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "data/raw/issue448/preflight-features.parquet").exists(),
    reason="requires ignored #448 local development cache",
)
def test_issue430_no_scoring_preflight_reproduces_parent() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    report = issue430.preflight(write=False)
    assert report["status"] == "PASS"
    assert report["scoring_performed"] is False
    assert report["protected_confirmation_accessed"] is False
    assert report["feature_rows"] == 3088
    assert report["session_rows"] == 3897
    assert report["declared_stage1_outer_cost_trials"] == 156
    assert report["parent_reproduction_pass"] is True


def test_dynamic_risk_control_matches_base_replay_when_off() -> None:
    policy = _policy([2.0]).assign(forecast_id=["f0"])
    risk, costs = _risk_and_costs()
    base_ledger, _ = sizing.replay_research_policy(
        _sessions_for_replay(), policy, risk, costs,
        contract_multiplier=10_000.0, max_abs_contracts=4.0,
    )
    risk_ledger, _ = sizing.replay_risk_controlled_policy(
        _sessions_for_replay(), policy, risk, costs,
        contract_multiplier=10_000.0, max_abs_contracts=4.0, risk_config={},
    )
    assert risk_ledger["target_position"].tolist() == base_ledger["target_position"].tolist()
    assert risk_ledger["net_pnl_usd"].tolist() == base_ledger["net_pnl_usd"].tolist()


def test_drawdown_scaling_uses_only_pre_session_equity() -> None:
    from commodity.trading_decision_v0 import PaperRiskPolicy

    policy = _policy([1.0]).assign(forecast_id=["f0"])
    path = _sessions_for_replay()
    path["path_move_per_mmbtu"] = [-0.25, 0.0, 0.0]
    _, costs = _risk_and_costs()
    risk = PaperRiskPolicy(100_000.0, 1, 0.50, 0.90, "remain_flat", False)
    ledger, _ = sizing.replay_risk_controlled_policy(
        path, policy, risk, costs,
        contract_multiplier=10_000.0,
        max_abs_contracts=4.0,
        risk_config={"drawdown_threshold_fraction": 0.02, "drawdown_scale": 0.5},
    )
    assert ledger.loc[0, "target_position"] == 1.0
    assert ledger.loc[1, "target_position"] == 0.5


def test_uncertainty_stop_is_causal_and_flattens_next_session() -> None:
    policy = _policy([1.0]).assign(forecast_id=["f0"], uncertainty_usd=[500.0])
    path = _sessions_for_replay()
    path["path_move_per_mmbtu"] = [-0.10, 0.20, 0.0]
    risk, costs = _risk_and_costs()
    ledger, summary = sizing.replay_risk_controlled_policy(
        path, policy, risk, costs,
        contract_multiplier=10_000.0, max_abs_contracts=4.0,
        risk_config={"stop_loss_uncertainty_multiple": 1.0},
    )
    assert ledger.loc[0, "target_position"] == 1.0
    assert ledger.loc[0, "path_risk_trigger_after_session"] == "stop_loss"
    assert ledger.loc[1, "target_position"] == 0.0
    assert summary["stop_trigger_count"] == 1


def test_uncertainty_take_profit_flattens_only_after_profit_is_realized() -> None:
    policy = _policy([1.0]).assign(forecast_id=["f0"], uncertainty_usd=[500.0])
    path = _sessions_for_replay()
    path["path_move_per_mmbtu"] = [0.10, -0.20, 0.0]
    risk, costs = _risk_and_costs()
    ledger, summary = sizing.replay_risk_controlled_policy(
        path, policy, risk, costs,
        contract_multiplier=10_000.0, max_abs_contracts=4.0,
        risk_config={"take_profit_uncertainty_multiple": 1.5},
    )
    assert ledger.loc[0, "target_position"] == 1.0
    assert ledger.loc[0, "path_risk_trigger_after_session"] == "take_profit"
    assert ledger.loc[1, "target_position"] == 0.0
    assert summary["take_profit_trigger_count"] == 1


def test_time_stop_flattens_after_declared_session_count() -> None:
    policy = _policy([1.0]).assign(forecast_id=["f0"])
    risk, costs = _risk_and_costs()
    ledger, _ = sizing.replay_risk_controlled_policy(
        _sessions_for_replay(), policy, risk, costs,
        contract_multiplier=10_000.0, max_abs_contracts=4.0,
        risk_config={"max_hold_sessions": 1},
    )
    assert ledger.loc[0, "target_position"] == 1.0
    assert ledger.loc[1, "target_position"] == 0.0


def test_additional_loss_cooldown_uses_only_completed_prior_outcomes() -> None:
    policy = _policy([1.0, 1.0, 1.0])
    policy["net_trade_utility_usd"] = [-100.0, 100.0, 100.0]
    policy.loc[0, "target_end_timestamp"] = policy.loc[0, "fill_timestamp"] + pd.Timedelta(hours=2)
    out = sizing.apply_additional_loss_cooldown(policy, 1)
    assert out["signal_requested_position"].tolist() == [1.0, 0.0, 1.0]


def test_stage1_evaluator_requires_cross_outer_and_cost_robustness() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    rows = []
    for outer in ("outer-2019-2020", "outer-2021-2022"):
        for cost in ("base", "higher_1_5x", "higher_2x"):
            rows.append({"policy_id": "fixed_1_00", "outer_id": outer, "cost_profile": cost,
                         "mean_monthly_net_return": 0.01, "parent_mean_monthly_net_return": 0.01,
                         "mean_monthly_net_return_delta": 0.0, "hard_safety_regression": False,
                         "largest_incremental_positive_month_fraction": 0.0,
                         "max_margin_utilization_fraction": 0.05})
            rows.append({"policy_id": "candidate", "outer_id": outer, "cost_profile": cost,
                         "mean_monthly_net_return": 0.012, "parent_mean_monthly_net_return": 0.01,
                         "mean_monthly_net_return_delta": 0.002, "hard_safety_regression": False,
                         "largest_incremental_positive_month_fraction": 0.2,
                         "max_margin_utilization_fraction": 0.2})
    evaluation = issue430.evaluate_stage1(pd.DataFrame(rows), issue430.load_prereg())
    candidate = next(row for row in evaluation if row["policy_id"] == "candidate")
    assert candidate["mean_outer_monthly_net_return_delta"] == pytest.approx(0.002)
    assert candidate["passes_return_gate"] is True


def test_stage1_evaluator_rejects_each_frozen_gate_failure() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    rows = []
    for outer in ("outer-2019-2020", "outer-2021-2022"):
        for cost in ("base", "higher_1_5x", "higher_2x"):
            rows.append({
                "policy_id": "candidate", "outer_id": outer, "cost_profile": cost,
                "mean_monthly_net_return": 0.012,
                "parent_mean_monthly_net_return": 0.01,
                "mean_monthly_net_return_delta": 0.002,
                "hard_safety_regression": False,
                "largest_incremental_positive_month_fraction": 0.2,
                "max_margin_utilization_fraction": 0.2,
            })
    baseline = pd.DataFrame(rows)
    cases: list[tuple[str, object, pd.Series]] = [
        ("mean_monthly_net_return_delta", -0.001,
         baseline["outer_id"].eq("outer-2019-2020") & baseline["cost_profile"].eq("base")),
        ("mean_monthly_net_return_delta", -0.001, baseline["cost_profile"].eq("higher_2x")),
        ("hard_safety_regression", True, baseline.index.to_series().eq(0)),
        ("largest_incremental_positive_month_fraction", 0.6, baseline["cost_profile"].eq("base")),
        ("max_margin_utilization_fraction", 0.5, baseline.index.to_series().eq(0)),
    ]
    prereg = issue430.load_prereg()
    for column, value, mask in cases:
        trial = baseline.copy()
        trial.loc[mask, column] = value
        candidate = issue430.evaluate_stage1(trial, prereg)[0]
        assert candidate["passes_return_gate"] is False


def test_stage2_parent_selection_is_mechanical_and_safety_bounded() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    evaluation = [
        {"policy_id": "unsafe_best", "mean_outer_monthly_net_return_delta": 0.05,
         "hard_safety_clear": False},
        {"policy_id": "safe_second", "mean_outer_monthly_net_return_delta": 0.03,
         "hard_safety_clear": True},
        {"policy_id": "safe_third", "mean_outer_monthly_net_return_delta": 0.02,
         "hard_safety_clear": True},
        {"policy_id": "safe_fourth", "mean_outer_monthly_net_return_delta": 0.01,
         "hard_safety_clear": True},
        {"policy_id": "safe_fifth", "mean_outer_monthly_net_return_delta": -0.01,
         "hard_safety_clear": True},
    ]
    selected = issue430.select_stage2_parents(evaluation, issue430.load_prereg())
    assert selected == ["safe_second", "safe_third", "safe_fourth"]


def test_stage1_config_binds_prior_regimes_and_research_cap() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    spec = {
        "id": "regime_candidate",
        "use_prior_favorable_regimes": True,
        "favorable_regime_scale": 1.5,
        "other_regime_scale": 0.75,
    }
    config = issue430.materialize_stage1_config(
        spec,
        favorable_regimes=("j0_v0", "j1_v1"),
        max_abs_contracts=4.0,
    )
    assert config["favorable_regimes"] == ["j0_v0", "j1_v1"]
    assert config["max_abs_contracts"] == 4.0
    assert "use_prior_favorable_regimes" not in config


def test_largest_losing_month_fraction_uses_absolute_monthly_losses() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    ledger = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(
                ["2022-01-03", "2022-02-03", "2022-03-03"], utc=True
            ),
            "net_pnl_usd": [-100.0, -300.0, 200.0],
        }
    )
    assert issue430.largest_losing_month_fraction(ledger) == pytest.approx(0.75)


def test_stage1_candidate_scoring_reproduces_control_and_tracks_exposure() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    parent = _policy([1.0]).assign(forecast_id=["f0"], favored_fraction=[0.8])
    risk, costs = _risk_and_costs()
    control = issue430.score_stage1_candidate(
        path=_sessions_for_replay(), parent_policy=parent,
        spec={"id": "fixed_1_00", "base_scale": 1.0}, favorable_regimes=(),
        risk=risk, costs=costs, contract_multiplier=10_000.0,
        max_abs_contracts=4.0, outer_id="outer-test", cost_profile="base",
    )
    scaled = issue430.score_stage1_candidate(
        path=_sessions_for_replay(), parent_policy=parent,
        spec={"id": "fixed_2_00", "base_scale": 2.0}, favorable_regimes=(),
        risk=risk, costs=costs, contract_multiplier=10_000.0,
        max_abs_contracts=4.0, outer_id="outer-test", cost_profile="base",
    )
    assert control["mean_monthly_net_return_delta"] == pytest.approx(0.0)
    assert scaled["mean_monthly_net_return"] > control["mean_monthly_net_return"]
    assert scaled["research_max_abs_contracts"] == 2.0
    assert scaled["operational_paper_max_contracts"] == 1


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "data/raw/issue448/preflight-features.parquet").exists(),
    reason="requires ignored #448 local development cache",
)
def test_stage1_subset_reproduces_fixed_one_contract_parent() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    result = issue430.score_stage1_subset(["fixed_1_00"])
    trials = result["trials"]
    assert len(trials) == 6
    assert result["protected_confirmation_accessed"] is False
    assert {row["policy_id"] for row in trials} == {"fixed_1_00"}
    assert all(abs(float(row["mean_monthly_net_return_delta"])) < 1e-12 for row in trials)
    assert all(int(row["operational_paper_max_contracts"]) == 1 for row in trials)


def test_stage1_scoring_refuses_missing_preflight(monkeypatch, tmp_path: Path) -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    monkeypatch.setattr(issue430, "PREFLIGHT", tmp_path / "missing-preflight.json")
    with pytest.raises(RuntimeError, match="preflight"):
        issue430.score_stage1(write=False)


def test_stage2_control_reproduces_sized_parent() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    parent = _policy([2.0]).assign(
        forecast_id=["f0"], favored_fraction=[0.8], net_trade_utility_usd=[100.0]
    )
    risk, costs = _risk_and_costs()
    row = issue430.score_stage2_candidate(
        path=_sessions_for_replay(), sized_parent_policy=parent,
        parent_policy_id="fixed_2_00", risk_spec={"id": "risk_control", "kind": "control"},
        risk=risk, costs=costs, contract_multiplier=10_000.0,
        max_abs_contracts=4.0, outer_id="outer-test", cost_profile="base",
    )
    assert row["mean_monthly_net_return_delta_vs_sized_parent"] == pytest.approx(0.0)
    assert row["research_max_abs_contracts"] == 2.0
    assert row["operational_paper_max_contracts"] == 1


def test_stage2_evaluator_requires_incremental_cross_outer_cost_robustness() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    rows = []
    for outer in ("outer-2019-2020", "outer-2021-2022"):
        for cost in ("base", "higher_1_5x", "higher_2x"):
            for risk_id, delta in (("risk_control", 0.0), ("candidate", 0.001)):
                rows.append({
                    "parent_policy_id": "parent", "risk_variant_id": risk_id,
                    "outer_id": outer, "cost_profile": cost,
                    "mean_monthly_net_return_delta_vs_sized_parent": delta,
                    "hard_safety_regression": False,
                    "largest_incremental_positive_month_fraction": 0.2,
                    "max_margin_utilization_fraction": 0.2,
                })
    evaluation = issue430.evaluate_stage2(pd.DataFrame(rows), issue430.load_prereg())
    candidate = next(row for row in evaluation if row["risk_variant_id"] == "candidate")
    assert candidate["mean_outer_monthly_net_return_delta"] == pytest.approx(0.001)
    assert candidate["passes_risk_gate"] is True


def test_stage2_evaluator_rejects_each_frozen_gate_failure() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    rows = []
    for outer in ("outer-2019-2020", "outer-2021-2022"):
        for cost in ("base", "higher_1_5x", "higher_2x"):
            rows.append({
                "parent_policy_id": "parent", "risk_variant_id": "candidate",
                "outer_id": outer, "cost_profile": cost,
                "mean_monthly_net_return_delta_vs_sized_parent": 0.001,
                "hard_safety_regression": False,
                "largest_incremental_positive_month_fraction": 0.2,
                "max_margin_utilization_fraction": 0.2,
            })
    baseline = pd.DataFrame(rows)
    cases: list[tuple[str, object, pd.Series]] = [
        ("mean_monthly_net_return_delta_vs_sized_parent", -0.001,
         baseline["outer_id"].eq("outer-2019-2020") & baseline["cost_profile"].eq("base")),
        ("mean_monthly_net_return_delta_vs_sized_parent", -0.001,
         baseline["cost_profile"].eq("higher_2x")),
        ("hard_safety_regression", True, baseline.index.to_series().eq(0)),
        ("largest_incremental_positive_month_fraction", 0.6,
         baseline["cost_profile"].eq("base")),
        ("max_margin_utilization_fraction", 0.5, baseline.index.to_series().eq(0)),
    ]
    prereg = issue430.load_prereg()
    for column, value, mask in cases:
        trial = baseline.copy()
        trial.loc[mask, column] = value
        candidate = issue430.evaluate_stage2(trial, prereg)[0]
        assert candidate["passes_risk_gate"] is False


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "data/raw/issue448/preflight-features.parquet").exists(),
    reason="requires ignored #448 local development cache",
)
def test_stage2_subset_reproduces_risk_control_for_fixed_parent() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    result = issue430.score_stage2_subset(["fixed_1_00"], ["risk_control"])
    trials = result["trials"]
    assert len(trials) == 6
    assert {row["risk_variant_id"] for row in trials} == {"risk_control"}
    assert all(
        abs(float(row["mean_monthly_net_return_delta_vs_sized_parent"])) < 1e-12
        for row in trials
    )


def test_allocation_efficiency_compares_dynamic_policy_to_nearest_fixed_exposure() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    rows = []
    for outer, fixed2_return, dynamic_return in (
        ("outer-2019-2020", 0.020, 0.021),
        ("outer-2021-2022", 0.018, 0.019),
    ):
        rows.extend([
            {"policy_id": "fixed_1_00", "outer_id": outer, "cost_profile": "base",
             "mean_monthly_net_return": 0.010, "mean_notional_leverage": 0.30},
            {"policy_id": "fixed_2_00", "outer_id": outer, "cost_profile": "base",
             "mean_monthly_net_return": fixed2_return, "mean_notional_leverage": 0.60},
            {"policy_id": "dynamic", "outer_id": outer, "cost_profile": "base",
             "mean_monthly_net_return": dynamic_return, "mean_notional_leverage": 0.58},
        ])
    summary = issue430.allocation_efficiency_summary(pd.DataFrame(rows))
    dynamic = next(row for row in summary if row["policy_id"] == "dynamic")
    assert dynamic["nearest_fixed_policy_ids"] == {
        "outer-2019-2020": "fixed_2_00", "outer-2021-2022": "fixed_2_00"
    }
    assert dynamic["mean_monthly_return_delta_vs_nearest_fixed"] == pytest.approx(0.001)
    assert dynamic["distinct_allocation_value"] is True


def test_full_issue430_scoring_refuses_missing_preflight(monkeypatch, tmp_path: Path) -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    monkeypatch.setattr(issue430, "PREFLIGHT", tmp_path / "missing-preflight.json")
    with pytest.raises(RuntimeError, match="preflight"):
        issue430.score_issue430()


def test_replay_rejects_fill_after_session_execution_point() -> None:
    policy = _policy([1.0]).assign(forecast_id=["f0"])
    policy.loc[0, "fill_timestamp"] = pd.Timestamp("2022-01-03 15:00", tz="UTC")
    risk, costs = _risk_and_costs()
    with pytest.raises(ValueError, match="execution point"):
        sizing.replay_research_policy(
            _sessions_for_replay(), policy, risk, costs,
            contract_multiplier=10_000.0, max_abs_contracts=4.0,
        )


def test_dynamic_margin_uses_post_cost_equity_and_does_not_advance_path_state() -> None:
    from commodity.trading_decision_v0 import ExecutionCostAssumptions, PaperRiskPolicy

    policy = _policy([2.0]).assign(forecast_id=["f0"], uncertainty_usd=[100.0])
    path = _sessions_for_replay()
    path["path_move_per_mmbtu"] = [-1.0, 0.0, 0.0]
    risk = PaperRiskPolicy(10_000.0, 1, 0.50, 0.90, "remain_flat", False)
    costs = ExecutionCostAssumptions(1.0, 0.0, 0.0, 0.0, 5_000.0, 10.0)
    ledger, summary = sizing.replay_risk_controlled_policy(
        path, policy, risk, costs,
        contract_multiplier=10_000.0, max_abs_contracts=2.0,
        risk_config={"stop_loss_uncertainty_multiple": 1.0},
    )
    assert ledger.loc[0, "target_position"] == 0.0
    assert ledger.loc[0, "no_trade_reason"] == "insufficient_margin_assumption"
    assert ledger.loc[0, "path_risk_trigger_after_session"] is None
    assert summary["stop_trigger_count"] == 0


@pytest.mark.parametrize(
    ("risk_config", "first_move", "expected_trigger"),
    [
        ({"stop_loss_uncertainty_multiple": 1.0}, 0.10, "stop_loss"),
        ({"take_profit_uncertainty_multiple": 1.5}, -0.10, "take_profit"),
    ],
)
def test_short_uncertainty_risk_triggers_use_position_direction(
    risk_config: dict[str, float], first_move: float, expected_trigger: str
) -> None:
    policy = _policy([-1.0]).assign(forecast_id=["f0"], uncertainty_usd=[500.0])
    path = _sessions_for_replay()
    path["path_move_per_mmbtu"] = [first_move, 0.0, 0.0]
    risk, costs = _risk_and_costs()
    ledger, _ = sizing.replay_risk_controlled_policy(
        path, policy, risk, costs,
        contract_multiplier=10_000.0, max_abs_contracts=4.0,
        risk_config=risk_config,
    )
    assert ledger.loc[0, "target_position"] == -1.0
    assert ledger.loc[0, "path_risk_trigger_after_session"] == expected_trigger
    assert ledger.loc[1, "target_position"] == 0.0


def test_dynamic_replay_rejects_finite_input_overflow() -> None:
    from commodity.trading_decision_v0 import ExecutionCostAssumptions, PaperRiskPolicy

    policy = _policy([1e200]).assign(forecast_id=["f0"], uncertainty_usd=[1.0])
    path = _sessions_for_replay()
    path["path_move_per_mmbtu"] = [1e200, 0.0, 0.0]
    risk = PaperRiskPolicy(1e300, 1, 0.50, 0.90, "remain_flat", False)
    costs = ExecutionCostAssumptions(0.0, 0.0, 0.0, 0.0, 0.0, 10.0)
    with pytest.raises(ValueError, match="gross pnl"):
        sizing.replay_risk_controlled_policy(
            path, policy, risk, costs,
            contract_multiplier=1e200, max_abs_contracts=1e200,
            risk_config={"stop_loss_uncertainty_multiple": 1.0},
        )


def test_dynamic_path_risk_rejects_unit_pnl_overflow() -> None:
    from commodity.trading_decision_v0 import ExecutionCostAssumptions, PaperRiskPolicy

    policy = _policy([1e-200]).assign(forecast_id=["f0"], uncertainty_usd=[1.0])
    path = _sessions_for_replay()
    path["path_move_per_mmbtu"] = [1e200, 0.0, 0.0]
    risk = PaperRiskPolicy(1e300, 1, 0.50, 0.90, "remain_flat", False)
    costs = ExecutionCostAssumptions(0.0, 0.0, 0.0, 0.0, 0.0, 10.0)
    with pytest.raises(ValueError, match="unit path pnl"):
        sizing.replay_risk_controlled_policy(
            path, policy, risk, costs,
            contract_multiplier=1e200, max_abs_contracts=1.0,
            risk_config={"stop_loss_uncertainty_multiple": 1.0},
        )


def test_dynamic_path_risk_rejects_threshold_overflow() -> None:
    from commodity.trading_decision_v0 import ExecutionCostAssumptions, PaperRiskPolicy

    policy = _policy([1.0]).assign(forecast_id=["f0"], uncertainty_usd=[1e308])
    path = _sessions_for_replay()
    path["path_move_per_mmbtu"] = [0.0, 0.0, 0.0]
    risk = PaperRiskPolicy(100_000.0, 1, 0.50, 0.90, "remain_flat", False)
    costs = ExecutionCostAssumptions(0.0, 0.0, 0.0, 0.0, 0.0, 10.0)
    with pytest.raises(ValueError, match="stop-loss threshold"):
        sizing.replay_risk_controlled_policy(
            path, policy, risk, costs,
            contract_multiplier=10_000.0, max_abs_contracts=1.0,
            risk_config={"stop_loss_uncertainty_multiple": 2.0},
        )


def test_issue430_preflight_self_hash_fails_closed(monkeypatch, tmp_path: Path) -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    payload = issue430.json.loads(issue430.PREFLIGHT.read_text(encoding="utf-8"))
    payload["feature_rows"] = int(payload["feature_rows"]) + 1
    stale = tmp_path / "stale-preflight.json"
    stale.write_text(issue430.json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(issue430, "PREFLIGHT", stale)
    with pytest.raises(RuntimeError, match="self-hash"):
        issue430._require_preflight()


def test_issue430_completed_result_blocks_rescoring(monkeypatch, tmp_path: Path) -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    preflight = tmp_path / "preflight.json"
    preflight.write_text(issue430.PREFLIGHT.read_text(encoding="utf-8"), encoding="utf-8")
    completed = tmp_path / "result.json"
    completed.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(issue430, "PREFLIGHT", preflight)
    monkeypatch.setattr(issue430, "RESULT", completed)
    with pytest.raises(RuntimeError, match="frozen"):
        issue430._require_preflight()


def test_stage2_promotion_requires_a_stage1_passing_parent() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    stage1 = [
        {"policy_id": "pass", "passes_return_gate": True},
        {"policy_id": "fail", "passes_return_gate": False},
    ]
    stage2 = [
        {"parent_policy_id": "fail", "risk_variant_id": "r1", "passes_risk_gate": True},
        {"parent_policy_id": "pass", "risk_variant_id": "r2", "passes_risk_gate": True},
    ]
    promoted = issue430.promotable_stage2_variants(stage1, stage2)
    assert [(row["parent_policy_id"], row["risk_variant_id"]) for row in promoted] == [
        ("pass", "r2")
    ]


def test_committed_issue430_trial_ledger_is_complete_and_unique() -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts" / "research"))
    import run_issue430_sizing_risk as issue430

    ledger = pd.read_json(issue430.LEDGER, lines=True)
    prereg = issue430.load_prereg()
    result = issue430.json.loads(issue430.RESULT.read_text(encoding="utf-8"))
    assert set(ledger["stage"]) == {"stage1_sizing", "stage2_risk"}
    stage1 = ledger.loc[ledger["stage"].eq("stage1_sizing")]
    stage2 = ledger.loc[ledger["stage"].eq("stage2_risk")]
    expected_stage1 = {
        (str(spec["id"]), str(outer), str(cost))
        for spec in prereg["stage1_sizing"]["policy_configs"]
        for outer in prereg["outer_blocks"]
        for cost in prereg["cost_profiles"]
    }
    actual_stage1 = {
        (str(row.policy_id), str(row.outer_id), str(row.cost_profile))
        for row in stage1.itertuples(index=False)
    }
    expected_stage2 = {
        (str(parent), str(spec["id"]), str(outer), str(cost))
        for parent in result["selected_stage2_parent_policy_ids"]
        for spec in prereg["stage2_risk"]["risk_variants"]
        for outer in prereg["outer_blocks"]
        for cost in prereg["cost_profiles"]
    }
    actual_stage2 = {
        (
            str(row.parent_policy_id), str(row.risk_variant_id),
            str(row.outer_id), str(row.cost_profile),
        )
        for row in stage2.itertuples(index=False)
    }
    assert actual_stage1 == expected_stage1
    assert actual_stage2 == expected_stage2
    assert len(ledger) == len(expected_stage1) + len(expected_stage2) == 318
    assert ledger["operational_paper_max_contracts"].eq(1).all()
    assert pd.to_numeric(ledger["research_max_abs_contracts"]).le(4.0).all()
