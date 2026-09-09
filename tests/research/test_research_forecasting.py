from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from commodity.research_forecasting import (
    build_bhlr_physical_bottleneck_panel,
    predict_c_from_frozen_b_models,
    score_bottleneck_pair,
    walk_forward_ab,
)


def _matrix(base: float) -> np.ndarray:
    rows, cols = 24, 12
    values = np.empty((rows, cols), dtype=float)
    for r in range(rows):
        for c in range(cols):
            values[r, c] = base + r + c / 100.0
    return values


def test_bhlr_panel_separates_realized_and_origin_vintage_physical_inputs() -> None:
    periods = pd.period_range("2000-01", periods=4, freq="M")
    panel = build_bhlr_physical_bottleneck_panel(
        ng_henry=_matrix(10.0),
        production=_matrix(100.0),
        storage=_matrix(200.0),
        consumption=_matrix(300.0),
        origin_periods=periods,
        start_row=5,
        start_column=2,
        final_column=11,
    )
    assert panel.index.tolist() == periods.tolist()
    assert panel.loc[periods[0], "pit_log_production"] == pytest.approx(np.log(105.02))
    assert panel.loc[periods[0], "realized_log_production"] == pytest.approx(np.log(105.11))
    assert panel.loc[periods[0], "target_log_hh"] == pytest.approx(np.log(16.11))
    assert panel.loc[periods[0], "market_log_hh"] == pytest.approx(np.log(15.02))
    assert np.isfinite(panel.to_numpy(dtype=float)).all()


def _forecast_panel(rows: int = 18) -> pd.DataFrame:
    index = pd.period_range("2000-01", periods=rows, freq="M")
    x = np.arange(rows, dtype=float)
    return pd.DataFrame(
        {
            "market_log_hh": 2.0 + x / 100.0,
            "season_sin": np.sin(2.0 * np.pi * (x % 12 + 1) / 12.0),
            "season_cos": np.cos(2.0 * np.pi * (x % 12 + 1) / 12.0),
            "realized_log_production": 4.0 + x / 200.0,
            "realized_log_storage": 5.0 + x / 150.0,
            "realized_log_consumption": 6.0 + x / 175.0,
            "pit_log_production": 4.0 + x / 200.0 + 0.02,
            "pit_log_storage": 5.0 + x / 150.0 - 0.03,
            "pit_log_consumption": 6.0 + x / 175.0 + 0.01,
            "target_log_hh": 2.01 + x / 100.0,
        },
        index=index,
    )


def test_c_reuses_frozen_b_models_without_fitting() -> None:
    panel = _forecast_panel(rows=30)
    a, b, frozen = walk_forward_ab(panel, development_rows=20, alpha=10.0)
    c = predict_c_from_frozen_b_models(panel, frozen)
    assert len(a) == len(b) == len(c) == 10
    assert a.index.equals(b.index) and b.index.equals(c.index)
    assert all(state.fit_count == 1 for state in frozen.values())
    assert all(state.c_prediction_count == 1 for state in frozen.values())
    assert np.isfinite(c["prediction"]).all()
    assert np.allclose(c["actual"], b["actual"])


def test_pair_scoring_uses_fixed_primary_block_and_chronological_thirds() -> None:
    index = pd.period_range("2000-01", periods=18, freq="M")
    actual = np.linspace(1.0, 2.0, len(index))
    baseline = pd.DataFrame({"prediction": actual + 0.20, "actual": actual}, index=index)
    challenger = pd.DataFrame({"prediction": actual + 0.10, "actual": actual}, index=index)
    result = score_bottleneck_pair(
        challenger,
        baseline,
        primary_block_size=2,
        sensitivity_block_sizes=(1,),
        resamples=200,
        confidence=0.95,
        seed=348,
    )
    assert result["relative_rmse_improvement"] == pytest.approx(0.5)
    assert result["primary"]["block_size"] == 2
    assert result["nonnegative_chronological_thirds"] == 3
    assert result["survives_primary_rule"] is True
