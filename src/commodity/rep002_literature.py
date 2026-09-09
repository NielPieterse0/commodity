from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import kruskal

_REQUIRED = {"trade_date", "contract_id", "expiration", "settle"}
_SOURCE_CRITICAL_99 = 24.725


def _prepare_contracts(contracts: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_REQUIRED - set(contracts.columns))
    if missing:
        raise ValueError(f"contract frame missing required fields: {missing}")
    out = contracts[list(_REQUIRED)].copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], utc=True)
    out["expiration"] = pd.to_datetime(out["expiration"], utc=True)
    out["settle"] = pd.to_numeric(out["settle"], errors="coerce")
    out = out.loc[out["settle"].gt(0.0)].copy()
    if out.duplicated(["trade_date", "contract_id"]).any():
        raise ValueError("contract frame has duplicate contract-day keys")
    return out.sort_values(["trade_date", "expiration", "contract_id"])


def build_mirantes_weekly_curve(
    contracts: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    prepared = _prepare_contracts(contracts)
    prepared = prepared.loc[
        prepared["trade_date"].lt(pd.Timestamp(cutoff))
        & prepared["trade_date"].dt.weekday.eq(0)
    ].copy()
    prepared["maturity_rank"] = prepared.groupby("trade_date").cumcount() + 1
    first_ten = prepared.loc[prepared["maturity_rank"].le(10)].copy()
    prices = first_ten.pivot(
        index="trade_date", columns="maturity_rank", values="settle"
    ).sort_index()
    complete = prices.dropna(subset=list(range(1, 11))).copy()
    complete.columns = [f"F{int(rank)}" for rank in complete.columns]
    for rank in range(1, 10):
        complete[f"carry{rank}"] = -np.log(
            complete[f"F{rank + 1}"] / complete[f"F{rank}"]
        )
    complete = complete.reset_index()
    complete["calendar_month"] = complete["trade_date"].dt.month.astype(int)
    complete["month_id"] = complete["trade_date"].dt.strftime("%Y-%m")
    return complete


def monthly_series_averages(panel: pd.DataFrame) -> pd.DataFrame:
    required = {"trade_date", "calendar_month", "month_id"}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise ValueError(f"weekly panel missing required fields: {missing}")
    value_columns = [f"F{i}" for i in range(1, 10)] + [
        f"carry{i}" for i in range(1, 10)
    ]
    missing_values = [column for column in value_columns if column not in panel.columns]
    if missing_values:
        raise ValueError(f"weekly panel missing source series: {missing_values}")
    monthly = (
        panel.groupby(["month_id", "calendar_month"], as_index=False)[value_columns]
        .mean()
        .sort_values("month_id", kind="stable")
        .reset_index(drop=True)
    )
    counts = panel.groupby("month_id").size().rename("weekly_observations")
    monthly["weekly_observations"] = monthly["month_id"].map(counts).astype(int)
    return monthly


def _series_kruskal(monthly: pd.DataFrame, column: str) -> dict[str, Any]:
    present_months = sorted(monthly["calendar_month"].dropna().astype(int).unique())
    if present_months != list(range(1, 13)):
        raise ValueError("seasonality test requires all 12 calendar months")
    groups = [
        monthly.loc[monthly["calendar_month"].eq(month), column].to_numpy(dtype=float)
        for month in range(1, 13)
    ]
    if any(len(group) == 0 or not np.isfinite(group).all() for group in groups):
        raise ValueError(f"seasonality groups are incomplete for {column}")
    result = kruskal(*groups)
    statistic = float(result.statistic)
    pvalue = float(result.pvalue)
    return {
        "statistic": statistic,
        "pvalue": pvalue,
        "critical_value_99": _SOURCE_CRITICAL_99,
        "reject_no_monthly_seasonality_99": statistic > _SOURCE_CRITICAL_99,
        "monthly_averages": int(sum(len(group) for group in groups)),
    }


def seasonality_statistics(monthly: pd.DataFrame) -> dict[str, dict[str, Any]]:
    return {
        "futures": {f"F{i}": _series_kruskal(monthly, f"F{i}") for i in range(1, 10)},
        "carry": {
            f"carry{i}": _series_kruskal(monthly, f"carry{i}")
            for i in range(1, 10)
        },
    }


def source_pattern_summary(statistics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    carry_rejections = [
        bool(statistics["carry"][f"carry{i}"]["reject_no_monthly_seasonality_99"])
        for i in range(1, 10)
    ]
    futures_rejections = [
        bool(statistics["futures"][f"F{i}"]["reject_no_monthly_seasonality_99"])
        for i in range(1, 10)
    ]
    return {
        "carry_reject_count_99": int(sum(carry_rejections)),
        "futures_reject_count_99": int(sum(futures_rejections)),
        "all_nine_carry_reject_99": all(carry_rejections),
        "no_futures_reject_99": not any(futures_rejections),
        "source_pattern_near_reproduced": bool(
            all(carry_rejections) and not any(futures_rejections)
        ),
    }
