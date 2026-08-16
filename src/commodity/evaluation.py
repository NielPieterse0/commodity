from __future__ import annotations

from collections.abc import Callable, Mapping

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


def paired_nonoverlapping_block_sign_flip_mse(
    challenger: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    block_size: int,
) -> dict[str, float | int | str]:
    if not challenger.index.equals(baseline.index):
        raise ValueError("Paired forecasts must have identical indexes")
    if not np.allclose(challenger["actual"], baseline["actual"], equal_nan=False):
        raise ValueError("Paired forecasts must have identical actual values")
    n_blocks = len(challenger) // block_size
    if block_size < 1 or n_blocks < 8:
        raise ValueError("block sign-flip check requires at least 8 complete blocks")
    n = n_blocks * block_size
    actual = challenger["actual"].to_numpy(dtype=float)[:n]
    challenger_error = challenger["prediction"].to_numpy(dtype=float)[:n] - actual
    baseline_error = baseline["prediction"].to_numpy(dtype=float)[:n] - actual
    row_delta = baseline_error**2 - challenger_error**2
    block_delta = row_delta.reshape(n_blocks, block_size).mean(axis=1)
    observed = float(block_delta.mean())
    if n_blocks > 20:
        raise ValueError("exact block sign-flip check supports at most 20 complete blocks")
    masks = np.arange(1 << n_blocks, dtype=np.uint64)[:, None]
    bits = (masks >> np.arange(n_blocks, dtype=np.uint64)) & 1
    signs = bits.astype(float) * 2.0 - 1.0
    null = (signs * block_delta).mean(axis=1)
    p_value = float((1 + np.count_nonzero(null >= observed)) / (len(null) + 1))
    return {
        "method": "nonoverlapping_block_sign_flip_mse",
        "mse_improvement": observed,
        "p_value_one_sided_improvement": p_value,
        "complete_blocks": n_blocks,
        "block_size": block_size,
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
    effective_blocks = n / block_size
    if effective_blocks < 8:
        raise ValueError("moving-block bootstrap requires at least 8 effective blocks")
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
            "effective_blocks": float(effective_blocks),
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
        "significant": bool(lower > 0.0 and p_value <= alpha),
        "block_size": block_size,
        "effective_blocks": float(effective_blocks),
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


def _v2_utc_timestamp(value: object, *, label: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a valid timestamp") from exc
    if timestamp.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return timestamp.tz_convert("UTC")


def v2_trailing_range20_signal(
    selected_market: pd.DataFrame,
    prediction_times: pd.Series,
) -> pd.Series:
    required = {"trade_date", "available_at", "high", "low", "close"}
    missing = sorted(required - set(selected_market.columns))
    if missing:
        raise ValueError(f"V2 robustness market input is missing columns: {missing}")
    if prediction_times.index.has_duplicates:
        raise ValueError("V2 robustness prediction-time index must be unique")

    frame = selected_market.loc[:, sorted(required)].copy()
    for column in ("trade_date", "available_at"):
        frame[column] = [
            _v2_utc_timestamp(value, label=f"{column}[{index}]")
            for index, value in frame[column].items()
        ]
    if frame["trade_date"].duplicated().any():
        raise ValueError("V2 robustness market input requires unique trade_date values")
    frame = frame.sort_values("trade_date", kind="stable").reset_index(drop=True)

    for column in ("high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
    values = frame[["high", "low", "close"]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("V2 robustness market OHLC values must be finite")
    if (frame["close"] <= 0.0).any() or (frame["high"] < frame["low"]).any():
        raise ValueError("V2 robustness market OHLC values are invalid")
    frame["range_pct"] = (frame["high"] - frame["low"]) / frame["close"]

    result: list[float] = []
    for index, value in prediction_times.items():
        cutoff = _v2_utc_timestamp(value, label=f"prediction_time[{index}]")
        eligible = frame.loc[
            (frame["trade_date"] <= cutoff) & (frame["available_at"] <= cutoff)
        ]
        if len(eligible) < 20:
            result.append(float("nan"))
            continue
        context = eligible.tail(20)
        result.append(float(context["range_pct"].mean()))
    return pd.Series(result, index=prediction_times.index, dtype=float)


def v2_fit_regime_thresholds(
    signal: pd.Series,
    *,
    initial_train: int,
) -> dict[str, float]:
    if signal.index.has_duplicates or not signal.index.is_monotonic_increasing:
        raise ValueError("V2 robustness signal index must be chronological and unique")
    if initial_train < 1 or initial_train >= len(signal):
        raise ValueError("initial_train must leave an out-of-sample period")
    observed = signal.iloc[:initial_train].to_numpy(dtype=float)
    finite = observed[np.isfinite(observed)]
    if finite.size == 0:
        raise ValueError("V2 robustness initial training signal has no finite values")
    q1, q2 = np.quantile(finite, [1.0 / 3.0, 2.0 / 3.0], method="linear")
    low = float(q1)
    high = float(q2)
    if not np.isfinite([low, high]).all() or not low < high:
        raise ValueError("V2 robustness tertile thresholds must be strictly separated")
    return {"q1": low, "q2": high}


def v2_assign_regimes(
    signal: pd.Series,
    thresholds: Mapping[str, float],
) -> pd.Series:
    q1 = float(thresholds["q1"])
    q2 = float(thresholds["q2"])
    if not np.isfinite([q1, q2]).all() or not q1 < q2:
        raise ValueError("V2 robustness thresholds must satisfy finite q1 < q2")
    labels: list[str | None] = []
    for value in signal.to_numpy(dtype=float):
        if not np.isfinite(value):
            labels.append(None)
        elif value <= q1:
            labels.append("low")
        elif value <= q2:
            labels.append("medium")
        else:
            labels.append("high")
    return pd.Series(labels, index=signal.index, dtype="object")


def v2_chronological_period_labels(index: pd.Index) -> pd.Series:
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("V2 robustness scored index must be chronological and unique")
    if len(index) < 3:
        raise ValueError("V2 robustness requires at least three scored rows")
    base, remainder = divmod(len(index), 3)
    sizes = [base + (1 if period < remainder else 0) for period in range(3)]
    labels = [
        f"period_{period + 1}"
        for period, size in enumerate(sizes)
        for _ in range(size)
    ]
    return pd.Series(labels, index=index, dtype="object")


def _v2_rmse_improvement(challenger: pd.DataFrame, baseline: pd.DataFrame) -> float:
    actual = challenger["actual"].to_numpy(dtype=float)
    challenger_error = challenger["prediction"].to_numpy(dtype=float) - actual
    baseline_error = baseline["prediction"].to_numpy(dtype=float) - actual
    return float(np.sqrt(np.mean(baseline_error**2)) - np.sqrt(np.mean(challenger_error**2)))


def v2_robustness_report(
    challenger: pd.DataFrame,
    baseline: pd.DataFrame,
    signal: pd.Series,
    *,
    initial_train: int,
) -> dict[str, object]:
    if not challenger.index.equals(baseline.index):
        raise ValueError("V2 robustness paired forecasts must have identical indexes")
    if challenger.empty:
        raise ValueError("V2 robustness requires scored forecasts")
    if not challenger.index.is_monotonic_increasing or challenger.index.has_duplicates:
        raise ValueError("V2 robustness scored forecasts must be chronological and unique")
    required = {"prediction", "actual"}
    if not required.issubset(challenger.columns) or not required.issubset(baseline.columns):
        raise ValueError("V2 robustness forecasts require prediction and actual columns")
    if not np.allclose(challenger["actual"], baseline["actual"], equal_nan=False):
        raise ValueError("V2 robustness paired forecasts must have identical actual values")

    thresholds = v2_fit_regime_thresholds(signal, initial_train=initial_train)
    scored_signal = signal.reindex(challenger.index)
    if scored_signal.isna().any() or not np.isfinite(scored_signal.to_numpy(dtype=float)).all():
        raise ValueError("V2 robustness requires a finite PIT regime signal for every scored row")
    regimes = v2_assign_regimes(scored_signal, thresholds)
    periods = v2_chronological_period_labels(challenger.index)

    period_improvements: dict[str, float] = {}
    period_counts: dict[str, int] = {}
    for label in ("period_1", "period_2", "period_3"):
        mask = periods == label
        period_counts[label] = int(mask.sum())
        period_improvements[label] = _v2_rmse_improvement(
            challenger.loc[mask], baseline.loc[mask]
        )

    regime_improvements: dict[str, float] = {}
    regime_counts: dict[str, int] = {}
    for label in ("low", "medium", "high"):
        mask = regimes == label
        count = int(mask.sum())
        if count == 0:
            raise ValueError("V2 robustness requires every frozen regime in scored rows")
        regime_counts[label] = count
        regime_improvements[label] = _v2_rmse_improvement(
            challenger.loc[mask], baseline.loc[mask]
        )

    positive_periods = sum(value > 0.0 for value in period_improvements.values())
    positive_regimes = sum(value > 0.0 for value in regime_improvements.values())
    return {
        "regime_thresholds": thresholds,
        "period_rmse_improvements": period_improvements,
        "regime_rmse_improvements": regime_improvements,
        "period_row_counts": period_counts,
        "regime_row_counts": regime_counts,
        "positive_periods": positive_periods,
        "positive_regimes": positive_regimes,
        "passed": positive_periods >= 2 and positive_regimes >= 2,
    }
