from __future__ import annotations

import numpy as np
import pandas as pd


def build_market_features(ohlcv: pd.DataFrame) -> pd.DataFrame:
    close = ohlcv["close"].astype(float)
    ret = np.log(close).diff()
    out = pd.DataFrame(index=ohlcv.index)
    out["ret_1"] = ret
    out["ret_5"] = np.log(close).diff(5)
    out["range_pct"] = (ohlcv["high"] - ohlcv["low"]) / close
    out["vol_5"] = ret.rolling(5).std()
    out["vol_20"] = ret.rolling(20).std()
    out["ma_gap_5"] = close / close.rolling(5).mean() - 1.0
    out["ma_gap_20"] = close / close.rolling(20).mean() - 1.0
    doy = out.index.dayofyear
    out["season_sin"] = np.sin(2 * np.pi * doy / 365.25)
    out["season_cos"] = np.cos(2 * np.pi * doy / 365.25)
    return out.replace([np.inf, -np.inf], np.nan)


def make_supervised(ohlcv: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    x = build_market_features(ohlcv)
    y = np.log(ohlcv["close"].shift(-1) / ohlcv["close"]).rename("target_ret_1")
    joined = x.join(y).dropna()
    return joined.drop(columns=["target_ret_1"]), joined["target_ret_1"]
