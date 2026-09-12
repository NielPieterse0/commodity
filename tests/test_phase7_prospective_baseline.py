from __future__ import annotations

import numpy as np
import pandas as pd

from commodity.phase7_prospective import Phase7ProspectiveError, forecast_frozen_market_baseline


FEATURES = ["feature_ret_1", "feature_vol_5"]
CANDIDATE = {
    "id": "histgb-core-v1",
    "model": "hist_gb",
    "feature_set": "core",
    "parameters": {
        "learning_rate": 0.05,
        "max_iter": 20,
        "max_leaf_nodes": 15,
        "random_state": 0,
    },
}


def _training(rows: int = 64) -> pd.DataFrame:
    dates = pd.date_range("2021-01-01", periods=rows, freq="D", tz="UTC")
    x = np.linspace(-0.03, 0.03, rows)
    return pd.DataFrame(
        {
            "target_end_timestamp": dates + pd.Timedelta(days=5),
            "target_path_move_per_mmbtu": 0.4 * x + 0.1 * np.sin(np.arange(rows)),
            "feature_ret_1": x,
            "feature_vol_5": np.linspace(0.01, 0.08, rows),
        }
    )


def _current() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-09-14T00:00:00Z",
                "signal_timestamp": "2026-09-14T23:59:00Z",
                "fill_trade_date": "2026-09-15T00:00:00Z",
                "fill_timestamp": "2026-09-15T00:00:00Z",
                "fill_contract_id": "NGX6",
                "target_end_timestamp": "2026-09-22T00:00:00Z",
                "feature_ret_1": 0.01,
                "feature_vol_5": 0.04,
            }
        ]
    )


def _forecast(training: pd.DataFrame | None = None, current: pd.DataFrame | None = None) -> pd.DataFrame:
    return forecast_frozen_market_baseline(
        _training() if training is None else training,
        _current() if current is None else current,
        CANDIDATE,
        FEATURES,
        freeze_landed_at="2026-09-12T04:30:20Z",
        contract_multiplier=10_000.0,
        min_train_rows=50,
        horizon_sessions=5,
    )


def test_prospective_baseline_is_outcome_blind_and_deterministic() -> None:
    first = _forecast()
    second = _forecast()
    assert first["forecast_id"].iloc[0] == second["forecast_id"].iloc[0]
    assert first["input_snapshot_sha256"].iloc[0] == second["input_snapshot_sha256"].iloc[0]
    assert first["training_rows"].iloc[0] == 64
    assert pd.Timestamp(first["latest_training_target_end"].iloc[0]) < pd.Timestamp(
        "2023-01-01T00:00:00Z"
    )
    assert "actual_path_move_per_mmbtu" not in first.columns
    assert "actual_gross_pnl_usd" not in first.columns
    assert np.isfinite(first["predicted_gross_pnl_usd"].iloc[0])


def test_reserved_2023_outcome_is_rejected_not_silently_filtered() -> None:
    training = _training()
    training.loc[training.index[-1], "target_end_timestamp"] = "2023-01-02T00:00:00Z"
    try:
        _forecast(training=training)
    except Phase7ProspectiveError as exc:
        assert "reserved 2023+ outcomes" in str(exc)
    else:
        raise AssertionError("reserved historical outcome was accepted for prospective fitting")


def test_current_origin_rejects_realized_outcome_columns() -> None:
    current = _current()
    current["target_path_move_per_mmbtu"] = 0.25
    try:
        _forecast(current=current)
    except Phase7ProspectiveError as exc:
        assert "outcome-blind" in str(exc)
    else:
        raise AssertionError("current realized target was accepted")


def test_signal_must_be_strictly_post_freeze() -> None:
    current = _current()
    current.loc[0, "signal_timestamp"] = "2026-09-12T04:30:20Z"
    current.loc[0, "fill_timestamp"] = "2026-09-12T05:00:00Z"
    try:
        _forecast(current=current)
    except Phase7ProspectiveError as exc:
        assert "strictly after landed freeze" in str(exc)
    else:
        raise AssertionError("freeze-boundary signal was accepted")


def test_current_feature_change_changes_bound_input_identity() -> None:
    first = _forecast()
    changed = _current()
    changed.loc[0, "feature_ret_1"] = 0.02
    second = _forecast(current=changed)
    assert first["input_snapshot_sha256"].iloc[0] != second["input_snapshot_sha256"].iloc[0]
    assert first["forecast_id"].iloc[0] != second["forecast_id"].iloc[0]


def test_phase7_candidate_parameters_are_immutable() -> None:
    changed = dict(CANDIDATE)
    changed["parameters"] = dict(CANDIDATE["parameters"])
    changed["parameters"]["max_iter"] = 21
    try:
        forecast_frozen_market_baseline(
            _training(),
            _current(),
            changed,
            FEATURES,
            freeze_landed_at="2026-09-12T04:30:20Z",
            contract_multiplier=10_000.0,
            min_train_rows=50,
            horizon_sessions=5,
        )
    except Phase7ProspectiveError as exc:
        assert "parameters drifted" in str(exc)
    else:
        raise AssertionError("mutated market baseline parameters were accepted")
