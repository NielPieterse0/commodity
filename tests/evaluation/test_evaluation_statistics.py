import numpy as np
import pandas as pd
import pytest


def _predictions(actual: np.ndarray, prediction: np.ndarray) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(actual), freq="D", tz="UTC")
    return pd.DataFrame({"actual": actual, "prediction": prediction}, index=index)


def test_paired_block_bootstrap_detects_rmse_improvement() -> None:
    from commodity.evaluation import paired_block_bootstrap_rmse

    actual = np.sin(np.arange(120) / 5.0) / 10
    baseline = _predictions(actual, np.zeros_like(actual))
    challenger = _predictions(actual, actual.copy())
    result = paired_block_bootstrap_rmse(
        challenger, baseline, block_size=10, resamples=300, confidence=0.95, seed=7
    )
    assert result["rmse_improvement"] > 0
    assert result["ci_lower"] > 0
    assert result["significant"] is True
    assert result["p_value"] < 0.05


def test_paired_block_bootstrap_reports_no_difference_for_same_input() -> None:
    from commodity.evaluation import paired_block_bootstrap_rmse

    actual = np.cos(np.arange(80) / 4.0) / 10
    baseline = _predictions(actual, np.zeros_like(actual))
    result = paired_block_bootstrap_rmse(
        baseline, baseline, block_size=8, resamples=200, confidence=0.95, seed=3
    )
    assert result["rmse_improvement"] == 0.0
    assert result["significant"] is False
    assert result["p_value"] == 1.0


def test_moving_block_capacity_gate_matches_bootstrap_minimum() -> None:
    from commodity.evaluation import validate_moving_block_bootstrap_capacity

    passing = validate_moving_block_bootstrap_capacity(sample_rows=160, block_size=20)
    assert passing["effective_blocks"] == pytest.approx(8.0)
    assert passing["status"] == "passed"
    with pytest.raises(ValueError, match="at least 8 effective blocks"):
        validate_moving_block_bootstrap_capacity(sample_rows=108, block_size=20)
    with pytest.raises(ValueError, match="at least 8 effective blocks"):
        validate_moving_block_bootstrap_capacity(sample_rows=28, block_size=4)


def test_walk_forward_with_label_availability_excludes_unresolved_labels() -> None:
    from commodity.evaluation import walk_forward_predict_with_label_availability

    index = pd.date_range("2026-01-01 23:59", periods=30, freq="D", tz="UTC")
    x = pd.DataFrame({"feature": np.arange(30, dtype=float)}, index=index)
    y = pd.Series(np.arange(30, dtype=float), index=index)
    label_available_at = pd.Series(index + pd.Timedelta(days=2), index=index)
    fits: list[pd.DatetimeIndex] = []

    class RecordingModel:
        def fit(self, train_x, train_y):
            assert train_x.index.equals(train_y.index)
            fits.append(train_x.index.copy())
            return self

        def predict(self, predict_x):
            return pd.Series([0.0], index=predict_x.index)

    result = walk_forward_predict_with_label_availability(
        RecordingModel,
        x,
        y,
        label_available_at,
        initial_train=22,
        retrain_every=1,
    )
    assert result.index[0] == index[22]
    assert fits[0][-1] == index[20]
    assert index[21] not in fits[0]
    for prediction_time, training_index in zip(result.index, fits, strict=True):
        assert (label_available_at.loc[training_index] <= prediction_time).all()


def test_secondary_block_sign_flip_check_reports_no_edge_for_worse_model() -> None:
    from commodity.evaluation import paired_nonoverlapping_block_sign_flip_mse

    actual = np.sin(np.arange(200) / 5.0) / 10
    baseline = _predictions(actual, np.zeros_like(actual))
    challenger = _predictions(actual, np.zeros_like(actual) + 0.2)
    result = paired_nonoverlapping_block_sign_flip_mse(
        challenger, baseline, block_size=20
    )
    assert result["mse_improvement"] < 0.0
    assert result["p_value_one_sided_improvement"] > 0.5
    assert result["complete_blocks"] == 10
