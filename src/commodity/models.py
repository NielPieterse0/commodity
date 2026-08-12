from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class ZeroReturnModel:
    def fit(self, x: pd.DataFrame, y: pd.Series) -> ZeroReturnModel:
        return self

    def predict(self, x: pd.DataFrame) -> pd.Series:
        return pd.Series(0.0, index=x.index, name="prediction")


class RidgeReturnModel:
    def __init__(self, alpha: float = 10.0) -> None:
        self.pipeline = Pipeline([
            ("scale", StandardScaler()),
            ("ridge", Ridge(alpha=alpha)),
        ])

    def fit(self, x: pd.DataFrame, y: pd.Series) -> RidgeReturnModel:
        self.pipeline.fit(x, y)
        return self

    def predict(self, x: pd.DataFrame) -> pd.Series:
        values = self.pipeline.predict(x)
        return pd.Series(values, index=x.index, name="prediction")


def baseline_factory(
    model_name: str,
    models: dict[str, dict[str, Any]],
) -> Callable[[], ZeroReturnModel | RidgeReturnModel]:
    cfg = models.get(model_name)
    if cfg is None or not cfg.get("enabled", False):
        raise ValueError(f"Baseline model is not enabled: {model_name}")
    implementation = cfg.get("baseline_implementation")
    if implementation == "zero_return":
        return ZeroReturnModel
    if implementation == "ridge_return":
        alpha = float(cfg["alpha"])

        def factory() -> RidgeReturnModel:
            return RidgeReturnModel(alpha=alpha)

        return factory
    raise ValueError(f"Unsupported baseline implementation: {implementation}")
