from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import commodity.v2_execution_adaptation as execution_module
from commodity.v2_execution_adaptation import (
    adaptive_forecast_window,
    build_cost_assumptions,
    expand_execution_decisions,
)


def _path() -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=8, tz="UTC")
    return pd.DataFrame(
        {
            "trade_date": dates,
            "session_open": dates + pd.Timedelta(hours=8),
            "contract_id": ["A", "A", "A", "B", "B", "B", "B", "B"],
            "roll_reason": ["hold", "hold", "hold", "volume", "hold", "hold", "hold", "hold"],
            "open_price": np.arange(8, dtype=float) + 2.0,
            "path_move_per_mmbtu": [0.1] * 7 + [np.nan],
            "next_selected_contract_id": ["A", "A", "B", "B", "B", "B", "B", None],
        }
    )


def _decisions() -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=8, tz="UTC")
    return pd.DataFrame(
        {
            "fill_trade_date": [dates[0], dates[2], dates[5]],
            "fill_timestamp": [dates[0] + pd.Timedelta(hours=8), dates[2] + pd.Timedelta(hours=8), dates[5] + pd.Timedelta(hours=8)],
            "signal_timestamp": [dates[0], dates[2], dates[5]],
            "target_end_timestamp": [dates[2] + pd.Timedelta(hours=20), dates[5] + pd.Timedelta(hours=20), dates[7] + pd.Timedelta(hours=20)],
            "forecast_id": ["f0", "f1", "f2"],
            "signal_requested_position": [1.0, -1.0, 0.5],
            "signal_reason": ["a", "b", "c"],
        }
    )


def test_cost_assumptions_change_only_declared_execution_fields() -> None:
    base = SimpleNamespace(
        commission_usd_per_side=2.0,
        exchange_clearing_fees_usd_per_side=3.0,
        half_spread_ticks_per_side=0.5,
        slippage_ticks_per_side=0.5,
        initial_margin_usd_per_contract=5000.0,
        tick_value_usd=10.0,
    )
    stressed = build_cost_assumptions(base, half_spread_ticks_per_side=2.0, slippage_ticks_per_side=4.0)
    assert stressed.half_spread_ticks_per_side == 2.0
    assert stressed.slippage_ticks_per_side == 4.0
    assert stressed.commission_usd_per_side == 2.0
    assert stressed.initial_margin_usd_per_contract == 5000.0


def test_execution_delay_moves_only_to_future_sessions_and_preserves_expiry() -> None:
    expanded, diagnostics = expand_execution_decisions(
        _path(), _decisions(), delay_sessions=1, roll_gap_sessions=0, miss_every_nth_order=0
    )
    assert list(expanded["trade_date"]) == list(_path()["trade_date"])
    # First signal cannot execute until the next session.
    assert expanded.loc[0, "signal_requested_position"] == 0.0
    assert expanded.loc[1, "signal_requested_position"] == 1.0
    # The second signal is likewise shifted and never backdated.
    assert expanded.loc[2, "signal_requested_position"] == 1.0
    assert expanded.loc[3, "signal_requested_position"] == -1.0
    assert diagnostics["delay_sessions"] == 1
    assert diagnostics["expired_before_delayed_fill"] == 0


def test_roll_gap_flattens_declared_roll_session_without_changing_contract_path() -> None:
    expanded, diagnostics = expand_execution_decisions(
        _path(), _decisions(), delay_sessions=0, roll_gap_sessions=1, miss_every_nth_order=0
    )
    # Contract changes A -> B at index 3, so that session is forced flat.
    assert expanded.loc[3, "signal_requested_position"] == 0.0
    assert expanded.loc[4, "signal_requested_position"] == -1.0
    assert diagnostics["roll_gap_sessions"] == 1
    assert diagnostics["forced_flat_roll_sessions"] == 1


def test_liquidity_stress_skips_every_nth_position_change_without_future_information() -> None:
    expanded, diagnostics = expand_execution_decisions(
        _path(), _decisions(), delay_sessions=0, roll_gap_sessions=0, miss_every_nth_order=2
    )
    # Requested changes are 0->1, 1->-1, -1->0.5; the second is missed.
    assert expanded.loc[0, "signal_requested_position"] == 1.0
    assert expanded.loc[2, "signal_requested_position"] == 1.0
    assert expanded.loc[5, "signal_requested_position"] == 0.5
    assert diagnostics["missed_position_changes"] == 1


def _origins() -> pd.DataFrame:
    dates = pd.date_range("2018-01-01", periods=150, freq="D", tz="UTC")
    x = np.linspace(-1.0, 1.0, len(dates))
    realized = 0.03 * x + 0.002 * np.sin(np.arange(len(dates)))
    return pd.DataFrame(
        {
            "signal_timestamp": dates,
            "fill_trade_date": dates.normalize(),
            "fill_timestamp": dates + pd.Timedelta(hours=8),
            "fill_contract_id": ["NG"] * len(dates),
            "target_end_timestamp": dates + pd.Timedelta(days=2, hours=20),
            "feature_x": x,
            "issue425_target": realized,
            "issue425_realized_cumulative": realized,
            "issue425_aggregate": realized,
            "issue425_realized_volatility": np.abs(realized),
        }
    )


def _config() -> dict[str, object]:
    return {
        "model.model_id": "ridge",
        "model.ridge_alpha": 10.0,
        "model.training_window": "expanding",
        "target.target_role": "return",
        "target.dead_band_quantile": 0.0,
        "target.aggregation": "cumulative",
        "target.horizon_sessions": 2,
        "decision.entry_threshold_quantile": 0.0,
    }


def test_adaptive_forecast_is_chronological_and_honors_rolling_window() -> None:
    origins = _origins()
    start = pd.Timestamp("2018-04-11", tz="UTC")
    boundary = pd.Timestamp("2018-05-31", tz="UTC")
    forecasts, diagnostics = adaptive_forecast_window(
        origins,
        ["feature_x"],
        _config(),
        start_timestamp=start,
        boundary_timestamp=boundary,
        contract_multiplier=10_000.0,
        round_trip_usd=30.0,
        minimum_training_rows=20,
        refit_mode="rolling",
        retrain_every_sessions=5,
        rolling_train_sessions=40,
        decay_half_life_sessions=None,
        recalibration_cadence_sessions=None,
        drift_trigger="off",
    )
    assert not forecasts.empty
    assert forecasts["training_rows"].max() <= 40
    assert (
        pd.to_datetime(forecasts["latest_training_target_end"], utc=True)
        < pd.to_datetime(forecasts["fill_timestamp"], utc=True)
    ).all()
    assert diagnostics["refit_count"] >= 2
    assert diagnostics["protected_confirmation_accessed"] is False


def test_adaptive_forecast_rejects_protected_dates() -> None:
    origins = _origins()
    with pytest.raises(ValueError, match="protected"):
        adaptive_forecast_window(
            origins, ["feature_x"], _config(),
            start_timestamp=pd.Timestamp("2023-01-01", tz="UTC"),
            boundary_timestamp=pd.Timestamp("2023-02-01", tz="UTC"),
            contract_multiplier=10_000.0, round_trip_usd=30.0,
            minimum_training_rows=20, refit_mode="expanding",
            retrain_every_sessions=5, rolling_train_sessions=None,
            decay_half_life_sessions=None, recalibration_cadence_sessions=None,
            drift_trigger="off",
        )


def test_rolling_variant_below_inherited_training_floor_is_infeasible() -> None:
    helper = getattr(execution_module, "adaptation_variant_feasibility", None)
    assert helper is not None
    feasible, reason = helper(
        {
            "id": "rolling252_r5",
            "refit_mode": "rolling",
            "rolling_train_sessions": 252,
        },
        minimum_training_rows=504,
    )
    assert feasible is False
    assert reason == "rolling_window_below_minimum_training_rows:252<504"
