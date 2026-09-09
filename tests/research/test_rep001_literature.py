from __future__ import annotations

import numpy as np
import pandas as pd

from commodity.rep001_literature import (
    _scale_garchx_exog,
    build_ergen_maturity_panel,
    build_mu_return_series,
    fit_gaussian_garch,
)


def _contracts() -> pd.DataFrame:
    dates = pd.to_datetime(
        ["2022-12-27", "2022-12-28", "2022-12-29", "2022-12-30"], utc=True
    )
    rows: list[dict[str, object]] = []
    specs = {
        "A": ("2022-12-29 18:30Z", [4.0, 4.4, 4.84]),
        "B": ("2023-01-05 18:30Z", [5.0, 5.5, 6.05, 6.655]),
        "C": ("2023-01-12 18:30Z", [6.0, 6.3, 6.615, 6.94575]),
    }
    for contract_id, (expiration, settles) in specs.items():
        for trade_date, settle in zip(dates, settles, strict=False):
            rows.append(
                {"trade_date": trade_date, "contract_id": contract_id,
                 "expiration": pd.Timestamp(expiration), "settle": settle}
            )
    return pd.DataFrame(rows)


def test_mu_series_substitutes_second_nearby_on_front_final_day() -> None:
    series = build_mu_return_series(
        _contracts(), cutoff=pd.Timestamp("2023-01-01", tz="UTC")
    )
    final_day = pd.Timestamp("2022-12-29", tz="UTC")
    row = series.loc[series["trade_date"].eq(final_day)].iloc[0]
    assert row["ret1_source_rank"] == 2
    assert row["ret1_contract_id"] == "B"
    assert np.isclose(row["ret1"], np.log(6.05 / 5.5))
    assert row["ret2_contract_id"] == "B"
    assert np.isclose(row["ret2"], np.log(6.05 / 5.5))


def test_ergen_panel_selects_return_after_same_contract_calculation() -> None:
    panel = build_ergen_maturity_panel(
        _contracts(), cutoff=pd.Timestamp("2023-01-01", tz="UTC")
    )
    rollover = panel.loc[
        panel["trade_date"].eq(pd.Timestamp("2022-12-30", tz="UTC"))
    ].iloc[0]
    assert rollover["contract_id"] == "B"
    assert np.isclose(rollover["return"], np.log(6.655 / 6.05))
    assert rollover["winter"] == 1.0
    assert rollover["ttm_business_days"] > 0


def test_garchx_internal_scaling_preserves_source_coefficient_units() -> None:
    matrix = np.array([[0.0, 1.0, 23.0], [1.0, 0.0, 1.0]])
    scaled, scales = _scale_garchx_exog(matrix)
    source_gamma = np.array([0.4, -0.2, -0.03])
    optimizer_gamma = source_gamma * scales
    assert np.allclose(matrix @ source_gamma, scaled @ optimizer_gamma)
    assert np.allclose(scales, np.array([1.0, 1.0, 23.0]))


def test_gaussian_garch_returns_positive_conditional_variance() -> None:
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0, 0.02, size=240)
    result = fit_gaussian_garch(returns)
    assert result["converged"] is True
    assert result["omega"] > 0.0
    assert 0.0 <= result["alpha"] < 1.0
    assert 0.0 <= result["beta"] < 1.0
    assert result["alpha"] + result["beta"] < 1.0
    assert np.asarray(result["conditional_variance"]).min() > 0.0
