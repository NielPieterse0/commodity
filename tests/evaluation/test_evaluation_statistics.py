import numpy as np
import pandas as pd


def _predictions(actual: np.ndarray, prediction: np.ndarray) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(actual), freq="D", tz="UTC")
    return pd.DataFrame({"actual": actual, "prediction": prediction}, index=index)


def test_paired_block_bootstrap_detects_rmse_improvement() -> None:
    from commodity.evaluation import paired_block_bootstrap_rmse

    actual = np.sin(np.arange(120) / 5.0) / 10
    baseline = _predictions(actual, np.zeros_like(actual))
    challenger = _predictions(actual, actual.copy())
    result = paired_block_bootstrap_rmse(
        challenger, baseline, block_size=10, resamples=300, confidence=0.95, seed=7
    )
    assert result["rmse_improvement"] > 0
    assert result["ci_lower"] > 0
    assert result["significant"] is True
    assert result["p_value"] < 0.05


def test_paired_block_bootstrap_reports_no_difference_for_same_input() -> None:
    from commodity.evaluation import paired_block_bootstrap_rmse

    actual = np.cos(np.arange(80) / 4.0) / 10
    baseline = _predictions(actual, np.zeros_like(actual))
    result = paired_block_bootstrap_rmse(
        baseline, baseline, block_size=8, resamples=200, confidence=0.95, seed=3
    )
    assert result["rmse_improvement"] == 0.0
    assert result["significant"] is False
    assert result["p_value"] == 1.0


def test_secondary_block_sign_flip_check_reports_no_edge_for_worse_model() -> None:
    from commodity.evaluation import paired_nonoverlapping_block_sign_flip_mse

    actual = np.sin(np.arange(200) / 5.0) / 10
    baseline = _predictions(actual, np.zeros_like(actual))
    challenger = _predictions(actual, np.zeros_like(actual) + 0.2)
    result = paired_nonoverlapping_block_sign_flip_mse(
        challenger, baseline, block_size=20
    )
    assert result["mse_improvement"] < 0.0
    assert result["p_value_one_sided_improvement"] > 0.5
    assert result["complete_blocks"] == 10
