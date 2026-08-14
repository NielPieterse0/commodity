from __future__ import annotations

from collections.abc import Sequence

import numpy as np

ArrayLike1D = Sequence[float] | np.ndarray


def _paired_finite_arrays(
    actual: ArrayLike1D,
    forecast: ArrayLike1D,
    *,
    forecast_name: str,
) -> tuple[np.ndarray, np.ndarray]:
    actual_values = np.asarray(actual, dtype=float)
    forecast_values = np.asarray(forecast, dtype=float)
    if actual_values.ndim != 1 or forecast_values.ndim != 1:
        raise ValueError("Evaluation inputs must be one-dimensional")
    if len(actual_values) == 0 or len(actual_values) != len(forecast_values):
        raise ValueError("Evaluation inputs must be non-empty and have equal length")
    if not np.all(np.isfinite(actual_values)):
        raise ValueError("Actual values must be finite")
    if not np.all(np.isfinite(forecast_values)):
        raise ValueError(f"{forecast_name} values must be finite")
    return actual_values, forecast_values


def evaluate_direction_probabilities(
    actual_returns: ArrayLike1D,
    up_probability: ArrayLike1D,
    *,
    threshold: float = 0.5,
) -> dict[str, float]:
    """Score P(return > 0); zero returns belong to the non-up class."""
    actual, probability = _paired_finite_arrays(
        actual_returns, up_probability, forecast_name="Probability"
    )
    if np.any((probability < 0.0) | (probability > 1.0)):
        raise ValueError("Probability values must be between 0 and 1")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")

    observed_up = (actual > 0.0).astype(float)
    clipped = np.clip(probability, np.finfo(float).eps, 1.0 - np.finfo(float).eps)
    log_loss = -np.mean(
        observed_up * np.log(clipped) + (1.0 - observed_up) * np.log(1.0 - clipped)
    )
    return {
        "n": float(len(actual)),
        "direction_accuracy": float(np.mean((probability >= threshold) == observed_up)),
        "brier_score": float(np.mean((probability - observed_up) ** 2)),
        "log_loss": float(log_loss),
        "observed_up_rate": float(np.mean(observed_up)),
        "mean_predicted_up_probability": float(np.mean(probability)),
    }


def evaluate_zero_mean_gaussian_volatility(
    actual_returns: ArrayLike1D,
    predicted_sigma: ArrayLike1D,
) -> dict[str, float]:
    """Score positive scale forecasts under an explicit zero-mean Gaussian model."""
    actual, sigma = _paired_finite_arrays(
        actual_returns, predicted_sigma, forecast_name="Predicted sigma"
    )
    if np.any(sigma <= 0.0):
        raise ValueError("Predicted sigma values must be strictly positive")

    realized_scale = np.abs(actual)
    scale_error = sigma - realized_scale
    gaussian_nll = np.mean(
        0.5 * np.log(2.0 * np.pi * sigma**2) + 0.5 * (actual / sigma) ** 2
    )
    return {
        "n": float(len(actual)),
        "volatility_mae": float(np.mean(np.abs(scale_error))),
        "volatility_rmse": float(np.sqrt(np.mean(scale_error**2))),
        "gaussian_nll": float(gaussian_nll),
        "mean_abs_return": float(np.mean(realized_scale)),
        "mean_predicted_sigma": float(np.mean(sigma)),
    }


def benjamini_hochberg_adjust(p_values: ArrayLike1D) -> list[float]:
    """Return Benjamini-Hochberg adjusted p-values in the original input order."""
    values = np.asarray(p_values, dtype=float)
    if values.ndim != 1:
        raise ValueError("p-values must be one-dimensional")
    if len(values) == 0:
        return []
    if not np.all(np.isfinite(values)) or np.any((values < 0.0) | (values > 1.0)):
        raise ValueError("p-values must be finite and between 0 and 1")

    order = np.argsort(values, kind="stable")
    ranked = values[order]
    ranks = np.arange(1, len(values) + 1, dtype=float)
    adjusted_ranked = ranked * len(values) / ranks
    adjusted_ranked = np.minimum.accumulate(adjusted_ranked[::-1])[::-1]
    adjusted_ranked = np.clip(adjusted_ranked, 0.0, 1.0)

    adjusted = np.empty_like(adjusted_ranked)
    adjusted[order] = adjusted_ranked
    return adjusted.tolist()
