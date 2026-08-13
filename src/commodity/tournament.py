from __future__ import annotations

from typing import Any

import pandas as pd

from commodity.evaluation import (
    evaluate_predictions,
    paired_block_bootstrap_rmse,
    walk_forward_predict,
)
from commodity.models import baseline_factory


def _validate_chronology(x: pd.DataFrame, y: pd.Series) -> None:
    if not x.index.equals(y.index):
        raise ValueError("Feature and target indexes must match")
    if not x.index.is_monotonic_increasing or x.index.has_duplicates:
        raise ValueError("Tournament inputs must be chronological and unique")


def run_tournament(
    x: pd.DataFrame,
    y: pd.Series,
    *,
    model_names: tuple[str, ...] | list[str],
    models: dict[str, dict[str, Any]],
    initial_train: int,
    retrain_every: int,
    primary_metric: str = "rmse",
    baseline_model: str | None = None,
    significance: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    _validate_chronology(x, y)
    if not model_names:
        raise ValueError("Tournament requires at least one model")
    rows: list[dict[str, float | str]] = []
    predictions: dict[str, pd.DataFrame] = {}
    for model_name in model_names:
        factory = baseline_factory(model_name, models)
        pred = walk_forward_predict(
            factory,
            x,
            y,
            initial_train=initial_train,
            retrain_every=retrain_every,
        )
        metrics = evaluate_predictions(pred)
        if primary_metric not in metrics:
            raise ValueError(f"Unknown tournament primary metric: {primary_metric!r}")
        predictions[model_name] = pred
        rows.append({"model": model_name, **metrics})

    summary = pd.DataFrame(rows)
    if significance is not None:
        if significance.get("method") != "moving_block_bootstrap":
            raise ValueError("Unsupported tournament significance method")
        if not baseline_model or baseline_model not in predictions:
            raise ValueError("Configured tournament baseline model is unavailable")
        baseline_pred = predictions[baseline_model]
        reports: dict[str, dict[str, float | int | bool | str]] = {}
        for model_name, pred in predictions.items():
            reports[model_name] = paired_block_bootstrap_rmse(
                pred,
                baseline_pred,
                block_size=int(significance["block_size"]),
                resamples=int(significance["resamples"]),
                confidence=float(significance["confidence"]),
                seed=int(significance["seed"]),
            )
        summary["rmse_improvement_vs_baseline"] = summary["model"].map(
            lambda name: reports[str(name)]["rmse_improvement"]
        )
        summary["significance_ci_lower"] = summary["model"].map(
            lambda name: reports[str(name)]["ci_lower"]
        )
        summary["significance_ci_upper"] = summary["model"].map(
            lambda name: reports[str(name)]["ci_upper"]
        )
        summary["significance_p_value"] = summary["model"].map(
            lambda name: reports[str(name)]["p_value"]
        )
        summary["significant_vs_baseline"] = summary["model"].map(
            lambda name: reports[str(name)]["significant"]
        )

    ascending = primary_metric not in {"direction_accuracy", "prediction_actual_corr"}
    summary = summary.sort_values(
        [primary_metric, "model"],
        ascending=[ascending, True],
    ).reset_index(drop=True)
    summary["rank"] = range(1, len(summary) + 1)
    return summary, predictions
