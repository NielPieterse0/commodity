from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

_REQUIRED = {"trade_date", "contract_id", "expiration", "settle"}
_ANNUALIZATION = np.sqrt(252.0) * 100.0


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


def build_front_month_monthly_volatility(
    contracts: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    """Build source-style front-month volatility plus a same-contract robustness series."""
    out = _prepare_contracts(contracts)
    cutoff = pd.Timestamp(cutoff)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")
    out = out.loc[out["trade_date"].lt(cutoff)].copy()
    if out.empty:
        raise ValueError("front-month literature sample is empty")
    out["same_contract_return"] = out.groupby("contract_id", sort=False)["settle"].transform(
        lambda values: np.log(values / values.shift(1))
    )
    front = out.drop_duplicates("trade_date", keep="first").copy()
    front = front.sort_values("trade_date", kind="stable").reset_index(drop=True)
    front["source_return"] = np.log(front["settle"] / front["settle"].shift(1))
    front["roll_return"] = (
        front["source_return"].notna()
        & ~front["contract_id"].eq(front["contract_id"].shift(1))
    )
    front["month_id"] = front["trade_date"].dt.tz_localize(None).dt.to_period("M").astype(str)
    rows: list[dict[str, Any]] = []
    for month_id, group in front.groupby("month_id", sort=True):
        source = group["source_return"].dropna().astype(float)
        same = group["same_contract_return"].dropna().astype(float)
        if len(source) < 2 or len(same) < 2:
            continue
        rows.append(
            {
                "month_id": month_id,
                "source_front_volatility": float(source.std(ddof=1) * _ANNUALIZATION),
                "same_contract_front_volatility": float(same.std(ddof=1) * _ANNUALIZATION),
                "daily_return_count": len(source),
                "same_contract_return_count": len(same),
                "roll_return_count": int(group["roll_return"].sum()),
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("front-month monthly volatility has no eligible months")
    return result


def _trigonometric_residual(
    values: pd.Series,
    *,
    basis: str,
) -> np.ndarray:
    y = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(y).all() or len(y) < 12:
        raise ValueError("trigonometric deseasonalization needs at least 12 finite months")
    t = np.arange(1, len(y) + 1, dtype=float)
    if basis == "inventory":
        columns = [
            np.ones(len(y)),
            np.cos(2.0 * np.pi * t / 12.0),
            np.sin(2.0 * np.pi * t / 12.0),
            np.cos(2.0 * np.pi * t / 6.0),
        ]
    elif basis == "volatility":
        columns = [
            np.ones(len(y)),
            np.cos(2.0 * np.pi * t / 12.0),
            np.cos(2.0 * np.pi * t / 6.0),
            np.sin(2.0 * np.pi * t / 6.0),
        ]
    else:
        raise ValueError(f"unknown trigonometric basis: {basis}")
    design = np.column_stack(columns)
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    return y - design @ coefficients


def build_geman_ohana_panel(
    volatility: pd.DataFrame,
    inventory: pd.DataFrame,
) -> pd.DataFrame:
    """Join monthly volatility to lagged source-style deseasonalized inventory."""
    required_vol = {"month_id", "source_front_volatility"}
    required_inv = {"month_id", "inventory"}
    if missing := sorted(required_vol - set(volatility.columns)):
        raise ValueError(f"volatility frame missing required fields: {missing}")
    if missing := sorted(required_inv - set(inventory.columns)):
        raise ValueError(f"inventory frame missing required fields: {missing}")
    vol = volatility.copy().sort_values("month_id", kind="stable").reset_index(drop=True)
    inv = inventory.copy().sort_values("month_id", kind="stable").reset_index(drop=True)
    for frame, label in ((vol, "volatility"), (inv, "inventory")):
        periods = pd.PeriodIndex(frame["month_id"].astype(str), freq="M")
        if periods.duplicated().any():
            raise ValueError(f"{label} frame has duplicate month_id")
        frame["month_id"] = periods.astype(str)
    inv["inventory"] = pd.to_numeric(inv["inventory"], errors="coerce")
    inv["inventory_deseasonalized"] = _trigonometric_residual(
        inv["inventory"], basis="inventory"
    )
    lagged_inventory = inv[["month_id", "inventory", "inventory_deseasonalized"]].copy()
    lagged_periods = pd.PeriodIndex(lagged_inventory["month_id"], freq="M") + 1
    lagged_inventory["month_id"] = lagged_periods.astype(str)
    lagged_inventory = lagged_inventory.rename(
        columns={
            "inventory": "lagged_inventory",
            "inventory_deseasonalized": "lagged_inventory_deseasonalized",
        }
    )
    volatility_columns = [
        column for column in vol.columns if column.endswith("front_volatility")
    ]
    for column in volatility_columns:
        vol[column] = pd.to_numeric(vol[column], errors="coerce")
        vol[f"{column}_deseasonalized"] = _trigonometric_residual(
            vol[column], basis="volatility"
        )
    panel = vol.merge(
        lagged_inventory,
        on="month_id",
        how="inner",
        validate="one_to_one",
    )
    panel = panel.dropna(subset=["lagged_inventory_deseasonalized"]).copy()
    if panel.empty:
        raise ValueError("Geman-Ohana panel has no lagged inventory overlap")
    periods = pd.PeriodIndex(panel["month_id"], freq="M")
    panel["calendar_month"] = periods.month
    return panel.reset_index(drop=True)


def _negative_spearman(x: pd.Series, y: pd.Series) -> dict[str, float | int]:
    paired = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(paired) < 3:
        raise ValueError("Spearman test needs at least three paired observations")
    result = spearmanr(
        paired["x"].to_numpy(dtype=float),
        paired["y"].to_numpy(dtype=float),
        alternative="less",
    )
    return {
        "observations": len(paired),
        "rho": float(result.statistic),
        "one_sided_pvalue": float(result.pvalue),
    }


def geman_ohana_correlation_tests(
    panel: pd.DataFrame,
    *,
    volatility_prefix: str,
) -> dict[str, Any]:
    inventory = "lagged_inventory_deseasonalized"
    original = volatility_prefix
    deseasonalized = f"{volatility_prefix}_deseasonalized"
    required = {inventory, original, deseasonalized}
    if missing := sorted(required - set(panel.columns)):
        raise ValueError(f"Geman-Ohana panel missing required fields: {missing}")
    scarcity = panel.loc[pd.to_numeric(panel[inventory], errors="coerce").lt(0.0)]
    if len(scarcity) < 3:
        raise ValueError("Geman-Ohana scarcity subset is too small")

    cells = {
        "original_volatility_whole": _negative_spearman(panel[inventory], panel[original]),
        "original_volatility_scarcity": _negative_spearman(scarcity[inventory], scarcity[original]),
        "deseasonalized_volatility_whole": _negative_spearman(
            panel[inventory], panel[deseasonalized]
        ),
        "deseasonalized_volatility_scarcity": _negative_spearman(
            scarcity[inventory], scarcity[deseasonalized]
        ),
    }
    whole_ok = all(
        cells[key]["one_sided_pvalue"] >= 0.05
        for key in ("original_volatility_whole", "deseasonalized_volatility_whole")
    )
    scarcity_ok = all(
        cells[key]["rho"] < 0.0 and cells[key]["one_sided_pvalue"] < 0.05
        for key in (
            "original_volatility_scarcity",
            "deseasonalized_volatility_scarcity",
        )
    )
    return {
        **cells,
        "scarcity_observations": len(scarcity),
        "whole_not_significantly_negative": bool(whole_ok),
        "scarcity_significantly_negative": bool(scarcity_ok),
        "source_pattern_reproduced": bool(whole_ok and scarcity_ok),
    }


def build_continuous_front_monthly_volatility(prices: pd.DataFrame) -> pd.DataFrame:
    """Build monthly volatility from an already-defined daily front-month series."""
    required = {"trade_date", "price"}
    if missing := sorted(required - set(prices.columns)):
        raise ValueError(f"continuous front series missing required fields: {missing}")
    out = prices[["trade_date", "price"]].copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], utc=True, errors="coerce")
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    out = out.dropna(subset=["trade_date", "price"]).sort_values("trade_date", kind="stable")
    if out["trade_date"].duplicated().any() or not out["price"].gt(0.0).all():
        raise ValueError("continuous front series requires unique dates and positive prices")
    out["source_return"] = out["price"].pct_change(fill_method=None)
    out["log_return"] = np.log(out["price"] / out["price"].shift(1))
    out["month_id"] = out["trade_date"].dt.tz_localize(None).dt.to_period("M").astype(str)
    rows: list[dict[str, Any]] = []
    for month_id, group in out.groupby("month_id", sort=True):
        simple = group["source_return"].dropna().astype(float)
        logged = group["log_return"].dropna().astype(float)
        if len(simple) < 2:
            continue
        rows.append(
            {
                "month_id": month_id,
                "source_front_volatility": float(simple.std(ddof=1) * _ANNUALIZATION),
                "log_front_volatility": float(logged.std(ddof=1) * _ANNUALIZATION),
                "daily_return_count": len(simple),
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("continuous front series has no eligible monthly volatility")
    return result
