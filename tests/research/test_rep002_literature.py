from __future__ import annotations

import numpy as np
import pandas as pd

from commodity.rep002_literature import (
    build_mirantes_weekly_curve,
    monthly_series_averages,
    seasonality_statistics,
)


def _contracts() -> pd.DataFrame:
    dates = pd.to_datetime(
        ["2022-01-03", "2022-01-04", "2022-01-10", "2022-02-07"], utc=True
    )
    rows: list[dict[str, object]] = []
    for date_index, trade_date in enumerate(dates):
        for rank in range(1, 11):
            rows.append(
                {
                    "trade_date": trade_date,
                    "contract_id": f"C{rank}",
                    "expiration": trade_date + pd.Timedelta(days=30 * rank),
                    "settle": 4.0 + rank * 0.1 + date_index * 0.01,
                }
            )
    return pd.DataFrame(rows)


def test_weekly_curve_uses_monday_exact_ranked_contracts() -> None:
    panel = build_mirantes_weekly_curve(
        _contracts(), cutoff=pd.Timestamp("2022-03-01", tz="UTC")
    )
    assert panel["trade_date"].dt.weekday.eq(0).all()
    assert panel["trade_date"].tolist() == list(
        pd.to_datetime(["2022-01-03", "2022-01-10", "2022-02-07"], utc=True)
    )
    first = panel.iloc[0]
    assert np.isclose(first["F1"], 4.1)
    assert np.isclose(first["F10"], 5.0)
    assert np.isclose(first["carry1"], -np.log(4.2 / 4.1))
    assert np.isclose(first["carry9"], -np.log(5.0 / 4.9))


def test_monthly_averages_reduce_weekly_observations() -> None:
    panel = build_mirantes_weekly_curve(
        _contracts(), cutoff=pd.Timestamp("2022-03-01", tz="UTC")
    )
    monthly = monthly_series_averages(panel)
    assert monthly["month_id"].tolist() == ["2022-01", "2022-02"]
    january = monthly.loc[monthly["month_id"].eq("2022-01")].iloc[0]
    expected = panel.loc[panel["trade_date"].dt.month.eq(1), "F1"].mean()
    assert np.isclose(january["F1"], expected)


def test_seasonality_statistics_return_futures_and_carry_series() -> None:
    rows: list[dict[str, float | int | str]] = []
    for year in range(2010, 2015):
        for month in range(1, 13):
            row: dict[str, float | int | str] = {
                "month_id": f"{year}-{month:02d}",
                "calendar_month": month,
            }
            for rank in range(1, 10):
                row[f"F{rank}"] = float(year - 2000)
                row[f"carry{rank}"] = float(month + rank / 100.0)
            rows.append(row)
    statistics = seasonality_statistics(pd.DataFrame(rows))
    assert set(statistics) == {"futures", "carry"}
    assert set(statistics["futures"]) == {f"F{i}" for i in range(1, 10)}
    assert set(statistics["carry"]) == {f"carry{i}" for i in range(1, 10)}
    assert statistics["carry"]["carry1"]["statistic"] > 24.725
    assert statistics["futures"]["F1"]["statistic"] < 24.725
