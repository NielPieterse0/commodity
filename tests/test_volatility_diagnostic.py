from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import commodity.volatility_diagnostic as vd
from commodity.volatility_diagnostic import (
    EPSILON,
    VolatilityDiagnosticError,
    _build_candidates,
    _fit_log_har,
    _garman_klass_variance,
    _moving_block_mean_inference,
    _predict_log_har,
    _qlike,
)


def test_garman_klass_flat_bar_is_zero() -> None:
    row = pd.Series({"open": 2.0, "high": 2.0, "low": 2.0, "close": 2.0})
    assert _garman_klass_variance(row) == 0.0


def test_garman_klass_rejects_invalid_ohlc() -> None:
    row = pd.Series({"open": 2.0, "high": 1.9, "low": 1.8, "close": 2.0})
    with pytest.raises(VolatilityDiagnosticError, match="ordering"):
        _garman_klass_variance(row)


def test_log_har_ols_recovers_fixed_linear_log_relation() -> None:
    rng = np.random.default_rng(4)
    x = rng.normal(size=(30, 3))
    log_target = 0.2 + 0.4 * x[:, 0] - 0.3 * x[:, 1] + 0.1 * x[:, 2]
    training = pd.DataFrame(
        {
            "log_rv_d1": x[:, 0],
            "log_rv_w5": x[:, 1],
            "log_rv_m20": x[:, 2],
            "target_rv": np.exp(log_target),
        }
    )
    coefficients = _fit_log_har(training)
    row = pd.Series({"log_rv_d1": 0.3, "log_rv_w5": 0.8, "log_rv_m20": 0.2})
    expected = math.exp(0.2 + 0.4 * 0.3 - 0.3 * 0.8 + 0.1 * 0.2)
    assert _predict_log_har(coefficients, row) == pytest.approx(expected)


def test_qlike_is_zero_for_exact_forecast_and_finite_at_floor() -> None:
    losses = _qlike(np.asarray([2.0, 0.0]), np.asarray([2.0, 0.0]))
    assert losses[0] == pytest.approx(0.0)
    assert losses[1] == pytest.approx(0.0)
    assert np.isfinite(losses).all()
    assert EPSILON > 0.0


def test_moving_block_inference_preserves_constant_improvement() -> None:
    result = _moving_block_mean_inference(
        np.ones(204, dtype=float),
        block_size=40,
        resamples=1000,
        confidence=0.95,
        seed=0,
    )
    assert result["mean_improvement"] == pytest.approx(1.0)
    assert result["ci_lower"] == pytest.approx(1.0)
    assert result["ci_upper"] == pytest.approx(1.0)
    assert result["effective_block_equivalent_units"] == pytest.approx(5.1)
    assert result["p_value_two_sided"] == pytest.approx(1.0 / 1001.0)


def _synthetic_market() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    trade_dates = pd.bdate_range("2024-01-02", periods=477, tz="UTC")
    available = trade_dates + pd.Timedelta(hours=23, minutes=59)
    close = 2.0 + np.linspace(0.0, 0.5, len(trade_dates))
    canonical = pd.DataFrame(
        {
            "trade_date": trade_dates,
            "available_at": available,
            "contract_id": "NGX",
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
        }
    )
    selected = canonical[["trade_date", "available_at", "contract_id"]].copy()
    candidate_index = pd.DatetimeIndex(available[20:476], name="prediction_time")
    frame = pd.DataFrame({"placeholder": np.arange(456)}, index=candidate_index)
    return canonical, selected, frame


def test_candidate_builder_has_full_frozen_shape_and_same_contract_targets() -> None:
    canonical, selected, frame = _synthetic_market()
    candidates = _build_candidates(frame, canonical, selected)
    assert len(candidates) == 456
    assert candidates.index.equals(frame.index)
    assert candidates["contract_id"].eq("NGX").all()
    assert candidates["same_contract_history_rows"].min() == 21
    assert (candidates["target_available_at"] > candidates.index).all()
    assert np.isfinite(candidates[["target_rv", "baseline_rv20"]].to_numpy()).all()


def test_candidate_builder_fails_closed_when_same_contract_target_is_missing() -> None:
    canonical, selected, frame = _synthetic_market()
    target_date = pd.Timestamp(selected.iloc[21]["trade_date"])
    canonical = canonical.loc[canonical["trade_date"] != target_date].copy()
    with pytest.raises(VolatilityDiagnosticError, match="exactly one canonical row"):
        _build_candidates(frame, canonical, selected)


def test_result_publication_rolls_back_predictions_if_summary_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export = pd.DataFrame(
        {"prediction_time": ["2026-01-01T00:00:00+00:00"], "actual_rv": [1.0]}
    )
    summary = {"execution": {}}

    def fail_summary(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected summary failure")

    monkeypatch.setattr(vd, "_atomic_json", fail_summary)
    with pytest.raises(RuntimeError, match="injected summary failure"):
        vd._publish_result_artifacts(tmp_path, export, summary)

    assert not (tmp_path / "predictions.csv").exists()
    assert not (tmp_path / "summary.json").exists()
    assert not (tmp_path / "predictions.csv.tmp").exists()
    assert not (tmp_path / "summary.json.tmp").exists()


def test_result_publication_does_not_touch_artifacts_owned_by_active_writer(
    tmp_path: Path,
) -> None:
    predictions_path = tmp_path / "predictions.csv"
    summary_path = tmp_path / "summary.json"
    predictions_path.write_text("owner-predictions\n", encoding="utf-8")
    summary_path.write_text("owner-summary\n", encoding="utf-8")
    (tmp_path / ".publication.lock").write_text("owner\n", encoding="utf-8")
    export = pd.DataFrame({"actual_rv": [1.0]})

    with pytest.raises(VolatilityDiagnosticError, match="already in progress"):
        vd._publish_result_artifacts(tmp_path, export, {"execution": {}})

    assert predictions_path.read_text(encoding="utf-8") == "owner-predictions\n"
    assert summary_path.read_text(encoding="utf-8") == "owner-summary\n"
    assert (tmp_path / ".publication.lock").exists()


def test_result_publication_refuses_completed_artifacts_without_deleting_them(
    tmp_path: Path,
) -> None:
    predictions_path = tmp_path / "predictions.csv"
    summary_path = tmp_path / "summary.json"
    predictions_path.write_text("completed-predictions\n", encoding="utf-8")
    summary_path.write_text("completed-summary\n", encoding="utf-8")
    export = pd.DataFrame({"actual_rv": [1.0]})

    with pytest.raises(VolatilityDiagnosticError, match="already exists"):
        vd._publish_result_artifacts(tmp_path, export, {"execution": {}})

    assert predictions_path.read_text(encoding="utf-8") == "completed-predictions\n"
    assert summary_path.read_text(encoding="utf-8") == "completed-summary\n"
    assert not (tmp_path / ".publication.lock").exists()
