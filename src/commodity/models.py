from __future__ import annotations

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
