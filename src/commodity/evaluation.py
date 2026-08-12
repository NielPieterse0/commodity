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
