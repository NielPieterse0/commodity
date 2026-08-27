import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from commodity import timesfm_zero_shot as run

ROOT = Path(__file__).resolve().parents[1]


def _market_frames(rows: int = 30) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    dates = pd.date_range("2026-01-02", periods=rows + 1, freq="B", tz="UTC")
    cutoff = dates[rows - 1] + pd.Timedelta(hours=23, minutes=59)
    raw_rows = []
    for index, date in enumerate(dates):
        available = date + pd.Timedelta(hours=23, minutes=59)
        settle_a = 3.0 + 0.01 * index
        settle_b = 4.0 + 0.01 * index
        for contract, settle in (("NGA", settle_a), ("NGB", settle_b)):
            raw_rows.append(
                {
                    "trade_date": date,
                    "available_at": available,
                    "contract_id": contract,
                    "open": settle * 0.99,
                    "high": settle * 1.01,
                    "low": settle * 0.98,
                    "close": settle,
                    "settle": settle,
                    "volume": 1000.0,
                }
            )
    canonical = pd.DataFrame(raw_rows)
    selected_rows = []
    for index, date in enumerate(dates):
        available = date + pd.Timedelta(hours=23, minutes=59)
        selected_rows.append(
            {
                "trade_date": date,
                "available_at": available,
                "contract_id": "NGA" if index < rows else "NGB",
                "roll_reason": "volume_crossover" if index == rows else "held",
            }
        )
    selected = pd.DataFrame(selected_rows)
    return canonical, selected, cutoff


def test_execution_authority_binds_frozen_contract_without_mutating_parent_freeze() -> None:
    evidence = run.validate_execution_authority(ROOT)
    assert evidence["authority"]["execution_authorized"] is True
    assert evidence["authority"]["hypothesis_family_changed"] is False
    assert evidence["freeze"]["prediction_generation_authorized"] is False
    assert evidence["contract"]["experiment"]["execution_authorized"] is False


def test_same_contract_target_survives_selected_path_roll() -> None:
    canonical, selected, cutoff = _market_frames()
    case = run._build_case(canonical, selected, cutoff)
    assert case.contract_id == "NGA"
    assert selected.loc[selected["trade_date"] == case.target_trade_date, "contract_id"].item() == "NGB"
    target = canonical.loc[
        canonical["trade_date"].eq(case.target_trade_date)
        & canonical["contract_id"].eq("NGA"),
        "settle",
    ].item()
    assert case.actual_return == pytest.approx(math.log(target / case.current_settle))
    assert case.target_timestamp > case.prediction_time


def test_timesfm_specific_context_can_reach_1024_without_changing_legacy_helper() -> None:
    dates = pd.date_range("2020-01-01", periods=1100, freq="B", tz="UTC")
    settle = np.linspace(2.0, 5.0, len(dates))
    history = pd.DataFrame(
        {
            "trade_date": dates,
            "available_at": dates + pd.Timedelta(hours=23, minutes=59),
            "contract_id": "NGA",
            "open": settle * 0.99,
            "high": settle * 1.01,
            "low": settle * 0.98,
            "close": settle,
            "settle": settle,
            "volume": 1000.0,
        }
    )
    case = run.ForecastCase(
        prediction_time=pd.Timestamp("2026-01-01", tz="UTC"),
        target_timestamp=pd.Timestamp("2026-01-02", tz="UTC"),
        trade_date=dates[-1],
        target_trade_date=dates[-1] + pd.Timedelta(days=1),
        contract_id="NGA",
        current_settle=float(settle[-1]),
        actual_return=0.0,
        actual_gk_variance=0.0,
        history=history,
    )
    assert len(run.representation_values(case, "settlement_level", 1024)) == 1024
    assert len(run.representation_values(case, "log_return", 1024)) == 1024
    assert len(run.representation_values(case, "garman_klass_variance", 1024)) == 1024


def test_empirical_quantiles_are_linear_and_same_contract_context_capped() -> None:
    canonical, selected, cutoff = _market_frames(rows=30)
    case = run._build_case(canonical, selected, cutoff)
    settle = case.history["settle"].to_numpy(dtype=float)
    returns = np.diff(np.log(settle))[-20:]
    expected = np.quantile(returns, run.QUANTILES, method="linear")
    assert np.allclose(run.empirical_return_quantiles(case, 20), expected)


def test_rmse_bootstrap_is_deterministic_and_one_sided() -> None:
    actual = np.linspace(-0.1, 0.1, 204)
    baseline = np.zeros(204)
    challenger = actual * 0.1
    first = run._rmse_improvement(actual, challenger, baseline)
    second = run._rmse_improvement(actual, challenger, baseline)
    assert first == second
    assert first["rmse_improvement"] > 0.0
    assert 0.0 < first["p_value_one_sided_improvement"] <= 0.05


def test_return_quantile_conversion_uses_q50_layout_without_reordering() -> None:
    canonical, selected, cutoff = _market_frames()
    case = run._build_case(canonical, selected, cutoff)
    forecast = np.asarray([[case.current_settle * math.exp(value) for value in np.linspace(-0.04, 0.04, 9)]])
    converted = run._to_return_quantiles([case], "settlement_level", forecast)
    assert converted.shape == (1, 9)
    assert converted[0, 4] == pytest.approx(0.0, abs=1e-15)
    assert np.all(np.diff(converted[0]) > 0.0)
