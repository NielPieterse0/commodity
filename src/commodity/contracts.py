from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd


class MarketDataSource(Protocol):
    def fetch(self, start: str, end: str) -> pd.DataFrame: ...


class ForecastModel(Protocol):
    def fit(self, x: pd.DataFrame, y: pd.Series) -> ForecastModel: ...
    def predict(self, x: pd.DataFrame) -> pd.Series: ...


@dataclass(frozen=True)
class RunPaths:
    root: Path

    @property
    def predictions(self) -> Path:
        return self.root / "predictions.csv"
