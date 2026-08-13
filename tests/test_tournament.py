import numpy as np
import pandas as pd
import pytest


def _xy(n: int = 90) -> tuple[pd.DataFrame, pd.Series]:
    index = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    x = pd.DataFrame(
        {
            "ret_1": np.sin(np.arange(n) / 3.0) / 100,
            "vol_5": 0.02 + np.cos(np.arange(n) / 7.0) / 1000,
            "season_sin": np.sin(2 * np.pi * index.dayofyear / 365.25),
        },
        index=index,
    )
    y = pd.Series(
        np.roll(x["ret_1"].to_numpy(), -1),
        index=index,
        name="target_ret_1",
    )
    return x.iloc[:-1], y.iloc[:-1]


def _models() -> dict:
    return {
        "naive": {
            "enabled": True,
            "baseline_implementation": "zero_return",
        },
        "ridge": {
            "enabled": True,
            "baseline_implementation": "ridge_return",
            "alpha": 1.0,
        },
        "hist_gb": {
            "enabled": True,
            "baseline_implementation": "hist_gradient_boosting_return",
            "learning_rate": 0.05,
            "max_iter": 20,
            "max_leaf_nodes": 7,
        },
    }


def test_models_share_prediction_count() -> None:
    from commodity.tournament import run_tournament

    x, y = _xy()
    summary, predictions = run_tournament(
        x,
        y,
        model_names=("naive", "ridge", "hist_gb"),
        models=_models(),
        initial_train=40,
        retrain_every=5,
    )
    assert set(summary["model"]) == {"naive", "ridge", "hist_gb"}
    assert {len(frame) for frame in predictions.values()} == {len(x) - 40}
    assert list(summary.sort_values("rank")["rank"]) == [1, 2, 3]


def test_tournament_rejects_nonchronological_rows() -> None:
    from commodity.tournament import run_tournament

    x, y = _xy()
    x = x.iloc[::-1]
    y = y.reindex(x.index)
    with pytest.raises(ValueError, match="chronological"):
        run_tournament(
            x,
            y,
            model_names=("naive",),
            models=_models(),
            initial_train=40,
            retrain_every=5,
        )
