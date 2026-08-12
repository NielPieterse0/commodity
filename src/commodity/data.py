from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

OHLCV = ["open", "high", "low", "close", "volume"]


def normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.columns = [str(c).lower().replace(" ", "_") for c in out.columns]
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], utc=True)
        out = out.set_index("date")
    out.index = pd.to_datetime(out.index, utc=True)
    missing = [c for c in OHLCV[:4] if c not in out.columns]
    if missing:
        raise ValueError(f"Missing required OHLC columns: {missing}")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    return out[OHLCV].sort_index().dropna(subset=OHLCV[:4])


@dataclass(frozen=True)
class CsvMarketDataSource:
    path: Path

    def fetch(self, start: str, end: str) -> pd.DataFrame:
        frame = normalize_ohlcv(pd.read_csv(self.path))
        return frame.loc[pd.Timestamp(start, tz="UTC"):pd.Timestamp(end, tz="UTC")]


@dataclass(frozen=True)
class YFinanceMarketDataSource:
    symbol: str

    def fetch(self, start: str, end: str) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Install the 'market' extra to use yfinance") from exc
        frame = yf.download(
            self.symbol, start=start, end=end, auto_adjust=False,
            progress=False, multi_level_index=False,
        )
        return normalize_ohlcv(frame)


def save_raw(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index_label="date")
    return path
