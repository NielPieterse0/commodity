from __future__ import annotations

import pandas as pd
import pytest

from commodity.stacking_policy import (
    Phase5PolicyError,
    PolicyConfig,
    apply_specialist_modifiers,
    build_policy_decisions,
    build_policy_grid,
    build_prospective_policy_decisions,
    fit_timesfm_uncertainty_state,
    replay_fractional_policy,
    select_policy_from_prior_oos,
    validate_phase5_evidence_boundary,
)
from commodity.trading_decision_v0 import ExecutionCostAssumptions, PaperRiskPolicy


def _costs() -> ExecutionCostAssumptions:
    return ExecutionCostAssumptions(
        commission_usd_per_side=2.0,
        exchange_clearing_fees_usd_per_side=3.0,
        half_spread_ticks_per_side=0.5,
        slippage_ticks_per_side=0.5,
        initial_margin_usd_per_contract=5000.0,
        tick_value_usd=10.0,
    )


def _risk() -> PaperRiskPolicy:
    return PaperRiskPolicy(
        capital_usd=100000.0,
        max_contracts=1,
        daily_loss_fraction=0.02,
        peak_drawdown_kill_fraction=0.10,
        after_kill="remain_flat_until_explicit_operator_restart",
        live_trading_allowed=False,
    )


def test_policy_join_accepts_mixed_iso_timestamp_precision() -> None:
    forecasts = pd.DataFrame(
        [{
            "trade_date": "2019-01-02T00:00:00+00:00",
            "signal_timestamp": "2019-01-02 23:59:00+00:00",
            "fill_trade_date": "2019-01-03T00:00:00+00:00",
            "fill_timestamp": "2019-01-03 14:30:00+00:00",
            "target_end_timestamp": "2019-01-10 14:30:00+00:00",
            "forecast_id": "f1",
            "predicted_gross_pnl_usd": 1000.0,
            "predicted_path_move_per_mmbtu": 0.01,
            "actual_path_move_per_mmbtu": 0.02,
        }]
    )
    timesfm = pd.DataFrame(
        [{
            "trade_date": "2019-01-02T00:00:00.000000+00:00",
            "prediction_time": "2019-01-02 23:59:00.000000+00:00",
            "timesfm_point_return": 0.01,
            "timesfm_interval_width": 0.02,
        }]
    )
    kronos = pd.DataFrame(
        [{
            "trade_date": "2019-01-02T00:00:00+00:00",
            "prediction_time": "2019-01-02 23:59:00+00:00",
            "kronos_close_return": 0.01,
        }]
    )
    result = build_policy_decisions(
        forecasts,
        timesfm,
        kronos,
        pd.DataFrame(),
        config=PolicyConfig("base", "none", "none", "none", "none"),
        costs=_costs(),
        uncertainty_state=None,
    )
    assert len(result) == 1
    assert result.loc[0, "signal_requested_position"] == 1.0


def test_policy_decision_can_be_built_before_realized_path_outcome_exists() -> None:
    forecasts = pd.DataFrame(
        [{
            "trade_date": "2026-09-14T00:00:00+00:00",
            "signal_timestamp": "2026-09-14 23:59:00+00:00",
            "fill_trade_date": "2026-09-15T00:00:00+00:00",
            "fill_timestamp": "2026-09-15 14:30:00+00:00",
            "target_end_timestamp": "2026-09-22 14:30:00+00:00",
            "forecast_id": "prospective-1",
            "predicted_gross_pnl_usd": 1000.0,
            "predicted_path_move_per_mmbtu": 0.01,
        }]
    )
    timesfm = pd.DataFrame(
        [{
            "trade_date": "2026-09-14T00:00:00+00:00",
            "prediction_time": "2026-09-14 23:59:00+00:00",
            "timesfm_point_return": 0.01,
            "timesfm_interval_width": 0.02,
        }]
    )
    kronos = pd.DataFrame(
        [{
            "trade_date": "2026-09-14T00:00:00+00:00",
            "prediction_time": "2026-09-14 23:59:00+00:00",
            "kronos_close_return": 0.01,
        }]
    )

    result = build_prospective_policy_decisions(
        forecasts,
        timesfm,
        kronos,
        pd.DataFrame(),
        config=PolicyConfig("prospective", "none", "none", "none", "none"),
        costs=_costs(),
        uncertainty_state=None,
    )

    assert result.loc[0, "signal_requested_position"] == 1.0
    assert pd.isna(result.loc[0, "baseline_abs_error"])


def test_policy_grid_is_exactly_frozen_36_configurations() -> None:
    grid = build_policy_grid()
    assert len(grid) == 36
    assert len({item.config_id for item in grid}) == 36
    assert {item.short_mode for item in grid} == {"none", "half", "veto"}
    assert {item.long_mode for item in grid} == {"none", "half", "veto"}
    assert {item.path_mode for item in grid} == {"none", "half"}
    assert {item.uncertainty_mode for item in grid} == {"none", "half_high"}


def test_phase5_boundary_rejects_protected_confirmation() -> None:
    allowed = pd.DataFrame({"trade_date": ["2022-12-30T00:00:00Z"]})
    validate_phase5_evidence_boundary(allowed)
    protected = pd.DataFrame({"trade_date": ["2023-01-03T00:00:00Z"]})
    with pytest.raises(Phase5PolicyError, match="protected"):
        validate_phase5_evidence_boundary(protected)


def test_policy_config_rejects_unknown_modes() -> None:
    with pytest.raises(Phase5PolicyError, match="short modifier"):
        PolicyConfig(
            config_id="bad",
            short_mode="invented",
            long_mode="none",
            path_mode="none",
            uncertainty_mode="none",
        )


def test_side_modifiers_only_act_on_preregistered_baseline_side() -> None:
    config = PolicyConfig("x", "veto", "veto", "none", "none")
    short = apply_specialist_modifiers(
        baseline_position=-1.0,
        timesfm_point_return=0.01,
        kronos_close_return=-0.02,
        kronos_terminal_return=None,
        timesfm_interval_width=0.05,
        config=config,
        uncertainty_state=None,
    )
    assert short.position == 0.0
    assert "timesfm_short_veto" in short.modifiers
    assert "kronos_long_veto" not in short.modifiers

    long = apply_specialist_modifiers(
        baseline_position=1.0,
        timesfm_point_return=-0.01,
        kronos_close_return=-0.02,
        kronos_terminal_return=None,
        timesfm_interval_width=0.05,
        config=config,
        uncertainty_state=None,
    )
    assert long.position == 0.0
    assert "kronos_long_veto" in long.modifiers
    assert "timesfm_short_veto" not in long.modifiers


def test_half_modifiers_do_not_compound_below_half_contract() -> None:
    config = PolicyConfig("x", "half", "none", "half", "half_high")
    result = apply_specialist_modifiers(
        baseline_position=-1.0,
        timesfm_point_return=0.01,
        kronos_close_return=-0.02,
        kronos_terminal_return=0.02,
        timesfm_interval_width=0.20,
        config=config,
        uncertainty_state={"active": True, "high_threshold": 0.10},
    )
    assert result.position == -0.5
    assert set(result.modifiers) == {
        "timesfm_short_half",
        "kronos_path_half",
        "timesfm_uncertainty_half",
    }


def test_uncertainty_state_uses_only_prior_oos_rows() -> None:
    history = pd.DataFrame(
        {
            "fill_timestamp": pd.date_range("2014-01-01", periods=60, tz="UTC"),
            "timesfm_interval_width": list(range(1, 61)),
            "baseline_abs_error": [float(value) for value in range(1, 61)],
        }
    )
    state = fit_timesfm_uncertainty_state(
        history,
        boundary_timestamp=pd.Timestamp("2014-03-15", tz="UTC"),
        minimum_rows=50,
    )
    assert state["calibration_rows"] == 60
    assert state["active"] is True
    assert state["association"] > 0.99

    early = fit_timesfm_uncertainty_state(
        history,
        boundary_timestamp=pd.Timestamp("2014-02-01", tz="UTC"),
        minimum_rows=50,
    )
    assert early["calibration_rows"] == 31
    assert early["active"] is False


def test_uncertainty_state_neutral_when_width_does_not_track_five_session_error() -> None:
    history = pd.DataFrame(
        {
            "fill_timestamp": pd.date_range("2014-01-01", periods=60, tz="UTC"),
            "timesfm_interval_width": list(range(1, 61)),
            "baseline_abs_error": [float(value) for value in range(60, 0, -1)],
        }
    )
    state = fit_timesfm_uncertainty_state(
        history,
        boundary_timestamp=pd.Timestamp("2015-01-01", tz="UTC"),
        minimum_rows=50,
    )
    assert state["active"] is False
    assert state["association"] < 0.0


def _path_for_replay() -> pd.DataFrame:
    dates = pd.date_range("2019-01-02", periods=4, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "trade_date": dates,
            "contract_id": ["NGH9"] * 4,
            "session_open": dates,
            "open_price": [3.0, 2.7, 2.8, 2.9],
            "path_move_per_mmbtu": [-0.30, 0.10, 0.10, 0.0],
            "next_selected_contract_id": ["NGH9", "NGH9", "NGH9", None],
        }
    )


def _decisions(position: float) -> pd.DataFrame:
    dates = pd.date_range("2019-01-02", periods=4, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "trade_date": dates,
            "signal_requested_position": [position] * 4,
            "signal_reason": ["forecast_signal"] * 4,
            "forecast_id": [f"f{i}" for i in range(4)],
        }
    )


def test_standard_replay_separates_signal_from_risk_shutdown() -> None:
    ledger, summary = replay_fractional_policy(
        _path_for_replay(),
        _decisions(1.0),
        _risk(),
        _costs(),
        contract_multiplier=10000.0,
        enforce_risk=True,
    )
    assert summary["kill_triggered"] is True
    assert ledger.loc[0, "signal_requested_position"] == 1.0
    assert ledger.loc[1, "signal_requested_position"] == 1.0
    assert ledger.loc[1, "target_position"] == 0.0
    assert bool(ledger.loc[1, "signal_abstained"]) is False
    assert bool(ledger.loc[1, "risk_shutdown"]) is True


def test_continuous_replay_does_not_carry_risk_kill() -> None:
    ledger, summary = replay_fractional_policy(
        _path_for_replay(),
        _decisions(1.0),
        _risk(),
        _costs(),
        contract_multiplier=10000.0,
        enforce_risk=False,
    )
    assert summary["kill_triggered"] is False
    assert ledger.loc[1, "target_position"] == 1.0
    assert not ledger["risk_shutdown"].any()


def test_fractional_position_change_charges_fractional_execution_sides() -> None:
    decisions = _decisions(0.5)
    ledger, _ = replay_fractional_policy(
        _path_for_replay(),
        decisions,
        _risk(),
        _costs(),
        contract_multiplier=10000.0,
        enforce_risk=False,
    )
    assert ledger.loc[0, "execution_side_count"] == pytest.approx(0.5)
    assert ledger.loc[0, "transaction_cost_usd"] == pytest.approx(0.5 * _costs().per_side_usd)


def test_replay_expires_a_signal_at_its_target_end() -> None:
    decisions = _decisions(1.0).iloc[[0]].copy()
    decisions["target_end_timestamp"] = pd.Timestamp("2019-01-04T00:00:00Z")
    ledger, _ = replay_fractional_policy(
        _path_for_replay(),
        decisions,
        _risk(),
        _costs(),
        contract_multiplier=10000.0,
        enforce_risk=False,
    )
    assert ledger.loc[0, "target_position"] == 1.0
    assert ledger.loc[1, "target_position"] == 1.0
    assert ledger.loc[2, "target_position"] == 0.0
    assert ledger.loc[2, "no_trade_reason"] == "forecast_horizon_expired"


def test_selection_uses_only_years_before_outer_boundary() -> None:
    scores = pd.DataFrame(
        [
            {"config_id": "a", "year": 2014, "net_pnl_usd": 10.0, "transaction_cost_usd": 1.0, "complexity": 0},
            {"config_id": "a", "year": 2015, "net_pnl_usd": 10.0, "transaction_cost_usd": 1.0, "complexity": 0},
            {"config_id": "b", "year": 2014, "net_pnl_usd": 20.0, "transaction_cost_usd": 3.0, "complexity": 1},
            {"config_id": "b", "year": 2015, "net_pnl_usd": 5.0, "transaction_cost_usd": 3.0, "complexity": 1},
            {"config_id": "b", "year": 2017, "net_pnl_usd": 9999.0, "transaction_cost_usd": 3.0, "complexity": 1},
        ]
    )
    selected = select_policy_from_prior_oos(scores, outer_start_year=2017)
    assert selected["config_id"] == "b"
    assert selected["years"] == [2014, 2015]
    assert 2017 not in selected["years"]
