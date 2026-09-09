from __future__ import annotations

import numpy as np
import pandas as pd

from commodity.rep005_literature import (
    build_continuous_front_monthly_volatility,
    build_front_month_monthly_volatility,
    build_geman_ohana_panel,
    geman_ohana_correlation_tests,
)


def _contracts() -> pd.DataFrame:
    dates = pd.bdate_range("2022-01-03", "2022-03-31", tz="UTC")
    rows: list[dict[str, object]] = []
    for index, trade_date in enumerate(dates):
        month = trade_date.month
        near_id = "A" if month == 1 else "B" if month == 2 else "C"
        far_id = "B" if month == 1 else "C" if month == 2 else "D"
        near_exp = pd.Timestamp(f"2022-{month:02d}-28", tz="UTC")
        far_exp = near_exp + pd.Timedelta(days=31)
        base = 4.0 + 0.01 * index
        rows.append({"trade_date": trade_date, "contract_id": near_id,
                     "expiration": near_exp, "settle": base})
        rows.append({"trade_date": trade_date, "contract_id": far_id,
                     "expiration": far_exp, "settle": base + 0.2})
    return pd.DataFrame(rows)


def test_front_month_volatility_reports_roll_and_same_contract_variants() -> None:
    result = build_front_month_monthly_volatility(
        _contracts(), cutoff=pd.Timestamp("2022-04-15", tz="UTC")
    )
    assert result["month_id"].tolist() == ["2022-01", "2022-02", "2022-03"]
    assert (result["source_front_volatility"] > 0.0).all()
    assert (result["same_contract_front_volatility"] > 0.0).all()
    assert result["roll_return_count"].sum() == 2
    assert result["same_contract_return_count"].sum() >= result["daily_return_count"].sum() - 1


def test_geman_ohana_panel_uses_source_trigonometric_residuals_and_lag() -> None:
    periods = pd.period_range("2011-01", periods=72, freq="M")
    t = np.arange(1, len(periods) + 1, dtype=float)
    seasonal = 100.0 + 20.0 * np.cos(2.0 * np.pi * t / 12.0)
    inventory = pd.DataFrame({"month_id": periods.astype(str), "inventory": seasonal})
    volatility = pd.DataFrame({
        "month_id": periods.astype(str),
        "source_front_volatility": 50.0 + 8.0 * np.cos(2.0 * np.pi * t / 12.0),
        "same_contract_front_volatility": 49.0 + 7.0 * np.cos(2.0 * np.pi * t / 12.0),
    })
    panel = build_geman_ohana_panel(volatility, inventory)
    assert len(panel) == 71
    assert np.max(np.abs(panel["lagged_inventory_deseasonalized"])) < 1e-8


def test_geman_ohana_pattern_requires_negative_scarcity_not_whole_sample() -> None:
    scarcity_inventory = np.linspace(-20.0, -1.0, 40)
    normal_inventory = np.linspace(1.0, 20.0, 40)
    inventory = np.r_[scarcity_inventory, normal_inventory]
    source_vol = np.r_[-scarcity_inventory, normal_inventory]
    panel = pd.DataFrame({
        "lagged_inventory_deseasonalized": inventory,
        "source_front_volatility": source_vol,
        "source_front_volatility_deseasonalized": source_vol,
        "same_contract_front_volatility": source_vol,
        "same_contract_front_volatility_deseasonalized": source_vol,
        "calendar_month": np.tile(np.arange(1, 13), 7)[:80],
    })
    result = geman_ohana_correlation_tests(
        panel,
        volatility_prefix="source_front_volatility",
    )
    assert result["source_pattern_reproduced"] is True
    assert result["original_volatility_scarcity"]["rho"] < -0.9
    assert result["original_volatility_scarcity"]["one_sided_pvalue"] < 0.05
    assert result["original_volatility_whole"]["one_sided_pvalue"] >= 0.05


def test_continuous_front_monthly_volatility_uses_consecutive_daily_prices() -> None:
    dates = pd.bdate_range("2020-01-02", "2020-02-28", tz="UTC")
    prices = pd.DataFrame(
        {
            "trade_date": dates,
            "price": 3.0 * np.exp(np.linspace(0.0, 0.25, len(dates))),
        }
    )
    result = build_continuous_front_monthly_volatility(prices)
    assert result["month_id"].tolist() == ["2020-01", "2020-02"]
    assert (result["source_front_volatility"] > 0.0).all()
    assert result["daily_return_count"].sum() == len(prices) - 1
