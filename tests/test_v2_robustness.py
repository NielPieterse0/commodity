import numpy as np
import pandas as pd
import pytest

from commodity.evaluation import (
    v2_assign_regimes,
    v2_chronological_period_labels,
    v2_fit_regime_thresholds,
    v2_robustness_report,
    v2_trailing_range20_signal,
)


def _market(rows: int = 24) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01T23:59:00Z", periods=rows, freq="D")
    close = np.linspace(2.0, 3.0, rows)
    return pd.DataFrame(
        {
            "trade_date": dates,
            "available_at": dates,
            "high": close * 1.05,
            "low": close * 0.95,
            "close": close,
        }
    )


def _predictions(index: pd.Index, scale: float) -> pd.DataFrame:
    actual = np.linspace(-0.04, 0.05, len(index))
    return pd.DataFrame({"prediction": actual * scale, "actual": actual}, index=index)


def test_trailing_range20_signal_is_pit_and_uses_exactly_20_rows() -> None:
    market = _market()
    cutoffs = pd.Series(
        [market.loc[19, "available_at"], market.loc[20, "available_at"]],
        index=pd.Index(["a", "b"]),
    )
    signal = v2_trailing_range20_signal(market, cutoffs)

    assert signal.index.equals(cutoffs.index)
    assert signal.loc["a"] == pytest.approx(0.1)
    assert signal.loc["b"] == pytest.approx(0.1)

    future = market.copy()
    future.loc[23, ["high", "low", "close"]] = [999.0, 1.0, 1.0]
    assert v2_trailing_range20_signal(future, cutoffs).equals(signal)


def test_trailing_range20_rejects_timezone_naive_inputs() -> None:
    market = _market()
    market["available_at"] = market["available_at"].dt.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware"):
        v2_trailing_range20_signal(
            market,
            pd.Series(["2026-01-24T23:59:00Z"], index=["x"]),
        )

    market = _market()
    with pytest.raises(ValueError, match="timezone-aware"):
        v2_trailing_range20_signal(
            market,
            pd.Series(["2026-01-24 23:59:00"], index=["x"]),
        )


def test_regime_thresholds_are_initial_train_only_and_linear() -> None:
    signal = pd.Series([0.1, 0.2, 0.3, 0.4, 9.0, 99.0], index=list("abcdef"))
    thresholds = v2_fit_regime_thresholds(signal, initial_train=4)
    expected = np.quantile(np.array([0.1, 0.2, 0.3, 0.4]), [1 / 3, 2 / 3], method="linear")
    assert thresholds == {"q1": pytest.approx(expected[0]), "q2": pytest.approx(expected[1])}

    changed_oos = signal.copy()
    changed_oos.iloc[4:] = [-999.0, 999.0]
    assert v2_fit_regime_thresholds(changed_oos, initial_train=4) == thresholds


def test_regime_thresholds_fail_closed_when_tertiles_collapse() -> None:
    with pytest.raises(ValueError, match="strictly separated"):
        v2_fit_regime_thresholds(pd.Series([0.1] * 8), initial_train=6)


def test_regime_boundaries_and_chronological_periods_are_fixed() -> None:
    signal = pd.Series([0.1, 0.2, 0.2001, 0.3, 0.3001])
    regimes = v2_assign_regimes(signal, {"q1": 0.2, "q2": 0.3})
    assert regimes.tolist() == ["low", "low", "medium", "medium", "high"]

    labels = v2_chronological_period_labels(pd.RangeIndex(10))
    assert labels.tolist() == [
        "period_1", "period_1", "period_1", "period_1",
        "period_2", "period_2", "period_2",
        "period_3", "period_3", "period_3",
    ]


def test_robustness_report_uses_frozen_period_and_regime_gate() -> None:
    full_index = pd.date_range("2026-01-01T23:59:00Z", periods=15, freq="D")
    signal = pd.Series(
        [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.10, 0.25, 0.55, 0.15, 0.35, 0.65, 0.18, 0.38, 0.68],
        index=full_index,
    )
    scored = full_index[6:]
    baseline = _predictions(scored, 0.0)
    challenger = _predictions(scored, 0.5)

    report = v2_robustness_report(
        challenger,
        baseline,
        signal,
        initial_train=6,
    )

    assert report["positive_periods"] == 3
    assert report["positive_regimes"] == 3
    assert report["passed"] is True
    assert report["period_row_counts"] == {"period_1": 3, "period_2": 3, "period_3": 3}
    assert sum(report["regime_row_counts"].values()) == len(scored)


def test_robustness_report_fails_closed_if_a_required_regime_is_empty() -> None:
    index = pd.date_range("2026-01-01T23:59:00Z", periods=12, freq="D")
    signal = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5, 0.6] + [0.1] * 6, index=index)
    baseline = _predictions(index[6:], 0.0)
    challenger = _predictions(index[6:], 0.5)
    with pytest.raises(ValueError, match="every frozen regime"):
        v2_robustness_report(challenger, baseline, signal, initial_train=6)
