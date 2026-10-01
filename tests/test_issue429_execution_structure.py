from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/research"))

import run_issue429_execution_structure as issue429


def _sessions() -> pd.DataFrame:
    dates = pd.date_range("2022-01-03", periods=6, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "trade_date": dates,
            "session_open": dates + pd.Timedelta(hours=14),
        }
    )


def _policy(positions: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2022-01-03", periods=len(positions), freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "fill_trade_date": dates,
            "signal_timestamp": dates + pd.Timedelta(hours=12),
            "fill_timestamp": dates + pd.Timedelta(hours=14),
            "target_end_timestamp": dates + pd.Timedelta(days=3, hours=14),
            "signal_requested_position": positions,
            "forecast_id": [f"f{i}" for i in range(len(positions))],
        }
    )

def test_prereg_declares_complete_trial_budget() -> None:
    prereg = issue429.load_prereg()
    assert prereg["status"] == "frozen_before_issue429_scoring"
    assert len(prereg["contribution_ablation"]["policies"]) == 7
    assert len(prereg["lifecycle_search"]["variants"]) == 12
    assert prereg["evaluation"]["expected_outer_cost_trial_count"] == 114


def test_hold_on_abstain_drops_zero_decision() -> None:
    policy = _policy([1.0, 0.0, 1.0])
    transformed = issue429.transform_policy_decisions(
        policy,
        _sessions(),
        {"id": "hold", "abstain_mode": "hold"},
    )
    assert transformed["fill_trade_date"].tolist() == [
        policy.loc[0, "fill_trade_date"],
        policy.loc[2, "fill_trade_date"],
    ]


def test_ignore_same_direction_refresh_drops_active_refresh() -> None:
    policy = _policy([1.0, 1.0, -1.0])
    transformed = issue429.transform_policy_decisions(
        policy,
        _sessions(),
        {"id": "ignore", "same_direction_mode": "ignore_while_active"},
    )
    assert transformed["signal_requested_position"].tolist() == [1.0, -1.0]

def test_exit_only_on_opposite_flattens_instead_of_reversing() -> None:
    policy = _policy([1.0, -1.0, -1.0])
    transformed = issue429.transform_policy_decisions(
        policy,
        _sessions(),
        {"id": "exit", "opposite_mode": "exit_only"},
    )
    assert transformed["signal_requested_position"].tolist() == [1.0, 0.0, -1.0]


def test_decision_delay_moves_to_next_session_without_extending_target() -> None:
    policy = _policy([1.0, -1.0])
    original_target = policy["target_end_timestamp"].tolist()
    transformed = issue429.transform_policy_decisions(
        policy,
        _sessions(),
        {"id": "delay", "decision_delay_sessions": 1},
    )
    expected_dates = _sessions()["trade_date"].iloc[1:3].tolist()
    assert transformed["fill_trade_date"].tolist() == expected_dates
    assert transformed["target_end_timestamp"].tolist() == original_target
    assert (transformed["signal_timestamp"] < transformed["fill_timestamp"]).all()


def test_max_hold_caps_target_end_on_session_calendar() -> None:
    policy = _policy([1.0])
    transformed = issue429.transform_policy_decisions(
        policy,
        _sessions(),
        {"id": "cap", "max_hold_sessions": 1},
    )
    assert transformed.loc[0, "target_end_timestamp"] == _sessions().loc[1, "session_open"]

def test_one_signal_per_target_window_suppresses_intermediate_decisions() -> None:
    policy = _policy([1.0, -1.0, 1.0, -1.0])
    transformed = issue429.transform_policy_decisions(
        policy,
        _sessions(),
        {"id": "cadence", "cadence_mode": "one_per_target_window"},
    )
    assert transformed["fill_trade_date"].tolist() == [
        policy.loc[0, "fill_trade_date"],
        policy.loc[3, "fill_trade_date"],
    ]


def test_transform_rejects_protected_2023_decision() -> None:
    policy = _policy([1.0])
    policy.loc[0, "fill_trade_date"] = pd.Timestamp("2023-01-03", tz="UTC")
    policy.loc[0, "signal_timestamp"] = pd.Timestamp("2023-01-03 12:00", tz="UTC")
    policy.loc[0, "fill_timestamp"] = pd.Timestamp("2023-01-03 14:00", tz="UTC")
    policy.loc[0, "target_end_timestamp"] = pd.Timestamp("2023-01-04 14:00", tz="UTC")
    with pytest.raises(RuntimeError, match="protected"):
        issue429.transform_policy_decisions(
            policy,
            _sessions(),
            {"id": "control"},
        )


def test_context_ablation_removes_only_declared_retained_families() -> None:
    selected = {
        "market_structure.positioning": "positioning_col",
        "ta.range_breakout": "range_col",
        "ta.trend_strength": "trend_col",
        "ta.volume_confirmation": "volume_col",
    }
    columns = issue429.context_columns_for_ablation(
        selected,
        ["ta.range_breakout", "ta.trend_strength", "ta.volume_confirmation"],
    )
    assert columns == [
        "positioning_col",
        "feature_issue427_jump_intensity",
        "feature_issue427_vol_of_vol",
    ]


@pytest.mark.skipif(
    not (issue429.issue428.issue448.CACHE / "preflight-features.parquet").exists()
    or not (issue429.issue428.issue448.CACHE / "preflight-families.json").exists(),
    reason="requires ignored #448 local development cache",
)
def test_no_scoring_preflight_binds_parent_and_local_cache() -> None:
    report = issue429.preflight(write=False)
    assert report["status"] == "PASS"
    assert report["scoring_performed"] is False
    assert report["protected_confirmation_accessed"] is False
    assert report["feature_rows"] == 3088
    assert report["session_rows"] == 3897
    assert report["expected_outer_cost_trial_count"] == 114


def test_lifecycle_evaluation_enforces_cross_outer_and_higher_cost_robustness() -> None:
    rows = []
    for outer in ("outer-2019-2020", "outer-2021-2022"):
        for cost in ("base", "higher_1_5x", "higher_2x"):
            rows.append(
                {
                    "stage": "lifecycle_variant",
                    "policy_id": "candidate",
                    "outer_id": outer,
                    "cost_profile": cost,
                    "mean_monthly_net_return_delta": 0.001,
                    "selected_trades": 30,
                    "nonempty_months": 10,
                    "kill_trigger_regression": False,
                    "largest_incremental_month_fraction": 0.4,
                    "max_drawdown_fraction": 0.05,
                }
            )
    prereg = issue429.load_prereg()
    evaluation = issue429.evaluate_lifecycle_trials(pd.DataFrame(rows), prereg)
    assert evaluation[0]["passes_promotion_gate"] is True

    rows[-1]["mean_monthly_net_return_delta"] = -0.0001
    evaluation = issue429.evaluate_lifecycle_trials(pd.DataFrame(rows), prereg)
    assert evaluation[0]["higher_cost_nonnegative"] is False
    assert evaluation[0]["passes_promotion_gate"] is False
