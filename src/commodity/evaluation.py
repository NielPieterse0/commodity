from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from commodity.contracts import ForecastModel


def walk_forward_predict(
    model_factory: Callable[[], ForecastModel],
    x: pd.DataFrame,
    y: pd.Series,
    initial_train: int = 252,
    retrain_every: int = 5,
) -> pd.DataFrame:
    if not x.index.equals(y.index):
        raise ValueError("Feature and target indexes must match")
    if not x.index.is_monotonic_increasing or x.index.has_duplicates:
        raise ValueError("Walk-forward inputs must be chronological and unique")
    if initial_train < 20 or initial_train >= len(x):
        raise ValueError("initial_train must leave an out-of-sample period")
    if retrain_every < 1:
        raise ValueError("retrain_every must be at least 1")
    rows: list[dict[str, object]] = []
    model: ForecastModel | None = None
    for i in range(initial_train, len(x)):
        if model is None or (i - initial_train) % retrain_every == 0:
            model = model_factory().fit(x.iloc[:i], y.iloc[:i])
        pred = float(model.predict(x.iloc[[i]]).iloc[0])
        rows.append({"date": x.index[i], "prediction": pred, "actual": float(y.iloc[i])})
    return pd.DataFrame(rows).set_index("date")


def evaluate_predictions(pred: pd.DataFrame) -> dict[str, float]:
    """Score forecast quality only; strategy and execution metrics live downstream."""
    error = pred["prediction"] - pred["actual"]
    corr = pred[["prediction", "actual"]].corr().iloc[0, 1]
    return {
        "n": float(len(pred)),
        "mae": float(error.abs().mean()),
        "rmse": float(np.sqrt((error ** 2).mean())),
        "bias": float(error.mean()),
        "direction_accuracy": float(
            (np.sign(pred["prediction"]) == np.sign(pred["actual"])).mean()
        ),
        "prediction_actual_corr": float(corr) if np.isfinite(corr) else 0.0,
    }


def paired_block_bootstrap_rmse(
    challenger: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    block_size: int,
    resamples: int,
    confidence: float,
    seed: int,
) -> dict[str, float | int | bool | str]:
    if not challenger.index.equals(baseline.index):
        raise ValueError("Paired forecasts must have identical indexes")
    if not np.allclose(challenger["actual"], baseline["actual"], equal_nan=False):
        raise ValueError("Paired forecasts must have identical actual values")
    n = len(challenger)
    if n < 2 or block_size < 1 or block_size > n:
        raise ValueError("block_size must be between 1 and the paired sample size")
    if resamples < 100:
        raise ValueError("resamples must be at least 100")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")

    actual = challenger["actual"].to_numpy(dtype=float)
    challenger_pred = challenger["prediction"].to_numpy(dtype=float)
    baseline_pred = baseline["prediction"].to_numpy(dtype=float)

    def improvement(indices: np.ndarray) -> float:
        base_error = baseline_pred[indices] - actual[indices]
        challenger_error = challenger_pred[indices] - actual[indices]
        base_rmse = float(np.sqrt(np.mean(base_error**2)))
        challenger_rmse = float(np.sqrt(np.mean(challenger_error**2)))
        return base_rmse - challenger_rmse

    observed = improvement(np.arange(n))
    if observed == 0.0 and np.array_equal(challenger_pred, baseline_pred):
        return {
            "method": "moving_block_bootstrap",
            "rmse_improvement": 0.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "p_value": 1.0,
            "significant": False,
            "block_size": block_size,
            "resamples": resamples,
        }

    rng = np.random.default_rng(seed)
    max_start = n - block_size
    draws = np.empty(resamples, dtype=float)
    blocks_needed = int(np.ceil(n / block_size))
    for i in range(resamples):
        starts = rng.integers(0, max_start + 1, size=blocks_needed)
        indices = np.concatenate([np.arange(s, s + block_size) for s in starts])[:n]
        draws[i] = improvement(indices)

    alpha = 1.0 - confidence
    lower, upper = np.quantile(draws, [alpha / 2.0, 1.0 - alpha / 2.0])
    centered_null = draws - observed
    p_value = float(
        (1 + np.count_nonzero(np.abs(centered_null) >= abs(observed)))
        / (resamples + 1)
    )
    return {
        "method": "moving_block_bootstrap",
        "rmse_improvement": float(observed),
        "ci_lower": float(lower),
        "ci_upper": float(upper),
        "p_value": p_value,
        "significant": bool(lower > 0.0),
        "block_size": block_size,
        "resamples": resamples,
    }


class _WalkForwardAuditModel:
    def __init__(self) -> None:
        self.last_training_time: object | None = None

    def fit(self, x: pd.DataFrame, y: pd.Series) -> _WalkForwardAuditModel:
        if not x.index.equals(y.index) or x.empty:
            raise ValueError("Leakage audit received invalid training data")
        self.last_training_time = x.index[-1]
        return self

    def predict(self, x: pd.DataFrame) -> pd.Series:
        if len(x) != 1 or self.last_training_time is None:
            raise ValueError("Leakage audit requires one forecast row after fitting")
        if self.last_training_time >= x.index[0]:
            raise ValueError("Walk-forward leakage audit detected future-label access")
        return pd.Series([0.0], index=x.index)


def audit_walk_forward_label_isolation(
    x: pd.DataFrame,
    y: pd.Series,
    *,
    initial_train: int,
    retrain_every: int,
) -> str:
    walk_forward_predict(
        _WalkForwardAuditModel,
        x,
        y,
        initial_train=initial_train,
        retrain_every=retrain_every,
    )
    return "passed"
