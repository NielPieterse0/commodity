from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from commodity.phase7_prospective import Phase7ProspectiveError

import commodity.phase7_prospective as prospective


FEATURES = [
    "feature_ret_1",
    "feature_ret_5",
    "feature_ret_20",
    "feature_vol_5",
    "feature_vol_20",
    "feature_range_pct",
    "feature_ma_gap_5",
    "feature_ma_gap_20",
    "feature_season_sin",
    "feature_season_cos",
    "feature_selected_dte",
    "feature_roll_event",
]
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


def _feature_values(rows: int) -> dict[str, np.ndarray]:
    x = np.linspace(-0.03, 0.03, rows)
    return {
        "feature_ret_1": x,
        "feature_ret_5": x * 2.0,
        "feature_ret_20": x * 3.0,
        "feature_vol_5": np.linspace(0.01, 0.08, rows),
        "feature_vol_20": np.linspace(0.02, 0.10, rows),
        "feature_range_pct": np.linspace(0.01, 0.03, rows),
        "feature_ma_gap_5": x * 0.5,
        "feature_ma_gap_20": x * 0.25,
        "feature_season_sin": np.sin(np.arange(rows) / 30.0),
        "feature_season_cos": np.cos(np.arange(rows) / 30.0),
        "feature_selected_dte": np.linspace(40.0, 20.0, rows),
        "feature_roll_event": (np.arange(rows) % 45 == 0).astype(float),
    }


def _training(rows: int = 520) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=rows, freq="D", tz="UTC")
    features = _feature_values(rows)
    return pd.DataFrame(
        {
            "trade_date": dates,
            "signal_timestamp": dates + pd.Timedelta(hours=23, minutes=59),
            "fill_trade_date": dates + pd.Timedelta(days=1),
            "fill_timestamp": dates + pd.Timedelta(days=1),
            "fill_contract_id": ["NGFROZEN"] * rows,
            "target_end_timestamp": dates + pd.Timedelta(days=6),
            "target_path_move_per_mmbtu": (
                0.4 * features["feature_ret_1"] + 0.1 * np.sin(np.arange(rows))
            ),
            **features,
        }
    )


def _current() -> pd.DataFrame:
    values = {name: float(series[-1]) for name, series in _feature_values(520).items()}
    values["feature_ret_1"] = 0.01
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-09-14T00:00:00Z",
                "signal_timestamp": "2026-09-14T23:59:00Z",
                "fill_trade_date": "2026-09-15T00:00:00Z",
                "fill_timestamp": "2026-09-15T00:00:00Z",
                "fill_contract_id": "NGX6",
                "target_end_timestamp": "2026-09-22T00:00:00Z",
                **values,
            }
        ]
    )


def _frozen_file(
    tmp_path: Path,
    monkeypatch,
    *,
    frame: pd.DataFrame | None = None,
) -> Path:
    path = tmp_path / "origins.csv"
    (_training() if frame is None else frame).to_csv(path, index=False, lineterminator="\n")
    monkeypatch.setattr(prospective, "_FROZEN_ORIGINS_FILE_SHA256", prospective._sha256_file(path))
    return path


def _forecast(path: Path, current: pd.DataFrame | None = None, candidate=None) -> pd.DataFrame:
    return prospective.forecast_frozen_market_baseline(
        path,
        _current() if current is None else current,
        CANDIDATE if candidate is None else candidate,
    )


def test_prospective_baseline_is_outcome_blind_and_deterministic(
    tmp_path: Path, monkeypatch
) -> None:
    path = _frozen_file(tmp_path, monkeypatch)
    first = _forecast(path)
    second = _forecast(path)
    assert first["forecast_id"].iloc[0] == second["forecast_id"].iloc[0]
    assert first["input_snapshot_sha256"].iloc[0] == second["input_snapshot_sha256"].iloc[0]
    assert first["training_rows"].iloc[0] == 520
    assert first["training_snapshot_sha256"].iloc[0] == prospective._sha256_file(path)
    assert pd.Timestamp(first["latest_training_target_end"].iloc[0]) < pd.Timestamp(
        "2023-01-01T00:00:00Z"
    )
    assert "actual_path_move_per_mmbtu" not in first.columns
    assert "actual_gross_pnl_usd" not in first.columns
    assert np.isfinite(first["predicted_gross_pnl_usd"].iloc[0])


def test_wrong_frozen_origins_bytes_are_rejected(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "origins.csv"
    _training().to_csv(path, index=False, lineterminator="\n")
    monkeypatch.setattr(prospective, "_FROZEN_ORIGINS_FILE_SHA256", "0" * 64)
    try:
        _forecast(path)
    except Phase7ProspectiveError as exc:
        assert "identity mismatch" in str(exc)
    else:
        raise AssertionError("modified frozen origins were accepted")


def test_reserved_2023_outcome_is_rejected_not_silently_filtered(
    tmp_path: Path, monkeypatch
) -> None:
    training = _training()
    training.loc[training.index[-1], "target_end_timestamp"] = "2023-01-02T00:00:00Z"
    path = _frozen_file(tmp_path, monkeypatch, frame=training)
    try:
        _forecast(path)
    except Phase7ProspectiveError as exc:
        assert "reserved 2023+ outcomes" in str(exc)
    else:
        raise AssertionError("reserved historical outcome was accepted for prospective fitting")


def test_current_origin_rejects_realized_outcome_columns(tmp_path: Path, monkeypatch) -> None:
    path = _frozen_file(tmp_path, monkeypatch)
    current = _current()
    current["target_path_move_per_mmbtu"] = 0.25
    try:
        _forecast(path, current=current)
    except Phase7ProspectiveError as exc:
        assert "outcome-blind" in str(exc)
    else:
        raise AssertionError("current realized target was accepted")


def test_signal_must_be_strictly_post_freeze(tmp_path: Path, monkeypatch) -> None:
    path = _frozen_file(tmp_path, monkeypatch)
    current = _current()
    current.loc[0, "signal_timestamp"] = "2026-09-12T04:30:20Z"
    current.loc[0, "fill_timestamp"] = "2026-09-12T05:00:00Z"
    try:
        _forecast(path, current=current)
    except Phase7ProspectiveError as exc:
        assert "strictly after landed freeze" in str(exc)
    else:
        raise AssertionError("freeze-boundary signal was accepted")


def test_current_feature_change_changes_bound_input_identity(tmp_path: Path, monkeypatch) -> None:
    path = _frozen_file(tmp_path, monkeypatch)
    first = _forecast(path)
    changed = _current()
    changed.loc[0, "feature_ret_1"] = 0.02
    second = _forecast(path, current=changed)
    assert first["input_snapshot_sha256"].iloc[0] != second["input_snapshot_sha256"].iloc[0]
    assert first["forecast_id"].iloc[0] != second["forecast_id"].iloc[0]


def test_phase7_candidate_parameters_are_immutable(tmp_path: Path, monkeypatch) -> None:
    path = _frozen_file(tmp_path, monkeypatch)
    changed = dict(CANDIDATE)
    changed["parameters"] = dict(CANDIDATE["parameters"])
    changed["parameters"]["max_iter"] = 21
    try:
        _forecast(path, candidate=changed)
    except Phase7ProspectiveError as exc:
        assert "parameters drifted" in str(exc)
    else:
        raise AssertionError("mutated market baseline parameters were accepted")


def test_phase7_candidate_parameter_keys_are_immutable(tmp_path: Path, monkeypatch) -> None:
    path = _frozen_file(tmp_path, monkeypatch)
    changed = dict(CANDIDATE)
    changed["parameters"] = dict(CANDIDATE["parameters"])
    del changed["parameters"]["random_state"]
    try:
        _forecast(path, candidate=changed)
    except Phase7ProspectiveError as exc:
        assert "parameter keys drifted" in str(exc)
    else:
        raise AssertionError("incomplete market baseline parameters were accepted")


def test_phase7_training_minimum_cannot_be_relaxed(tmp_path: Path, monkeypatch) -> None:
    path = _frozen_file(tmp_path, monkeypatch, frame=_training(503))
    try:
        _forecast(path)
    except Phase7ProspectiveError as exc:
        assert "requires 504" in str(exc)
    else:
        raise AssertionError("undersized training set was accepted")
