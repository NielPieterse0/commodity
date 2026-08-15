from __future__ import annotations

import pandas as pd
import pytest


def _frame(rows: int = 80) -> pd.DataFrame:
    index = pd.date_range("2025-01-01T23:59:00Z", periods=rows, freq="D")
    values = pd.Series(range(rows), index=index, dtype=float)
    return pd.DataFrame(
        {
            "ret_1": (values % 7 - 3) / 100.0,
            "season_sin": (values % 12) / 12.0,
            "curve_spread_m1_m2": (values % 5) / 10.0,
            "storage_signal": values / 100.0,
            "weather_signal": (values % 9) / 10.0,
            "power_signal": (values % 11) / 10.0,
            "positioning_signal": (values % 13) / 10.0,
            "target_ret_1": ((values.shift(-1).fillna(values.iloc[-1]) % 9) - 4) / 100.0,
        },
        index=index,
    )


def _manifest() -> dict:
    return {
        "required_feature_families": [
            "market",
            "market_structure",
            "storage",
            "weather",
            "power",
            "positioning",
            "calendar_seasonality",
        ],
        "source_lineage": {
            "exogenous_sources": [
                {"family": "storage", "value_columns": ["storage_signal"]},
                {"family": "weather", "value_columns": ["weather_signal"]},
                {"family": "power", "value_columns": ["power_signal"]},
                {"family": "positioning", "value_columns": ["positioning_signal"]},
            ]
        },
    }


def _models() -> dict[str, dict]:
    return {
        "naive": {"enabled": True, "baseline_implementation": "zero_return"},
        "ridge": {
            "enabled": True,
            "baseline_implementation": "ridge_return",
            "alpha": 10.0,
        },
        "hist_gb": {
            "enabled": True,
            "baseline_implementation": "hist_gradient_boosting_return",
            "learning_rate": 0.05,
            "max_iter": 10,
            "max_leaf_nodes": 7,
        },
    }


def test_feature_family_mapping_partitions_all_features() -> None:
    from commodity.phase_d_evaluation import feature_family_columns

    frame = _frame()
    mapping = feature_family_columns(frame, _manifest(), target="target_ret_1")

    assert list(mapping) == _manifest()["required_feature_families"]
    assert mapping["market"] == ("ret_1",)
    assert mapping["calendar_seasonality"] == ("season_sin",)
    assigned = [column for columns in mapping.values() for column in columns]
    assert len(assigned) == len(set(assigned))
    assert set(assigned) == set(frame.columns) - {"target_ret_1"}


def test_walk_forward_folds_match_retrain_blocks() -> None:
    from commodity.phase_d_evaluation import build_walk_forward_folds

    index = _frame(33).index
    folds = build_walk_forward_folds(index, initial_train=20, retrain_every=5)

    assert len(folds) == 3
    assert folds[0]["train_end"] == index[19].isoformat()
    assert folds[0]["test_start"] == index[20].isoformat()
    assert folds[0]["test_end"] == index[24].isoformat()
    assert folds[-1]["test_end"] == index[-1].isoformat()


def test_distribution_predictions_do_not_use_future_targets() -> None:
    from commodity.models import ZeroReturnModel
    from commodity.phase_d_evaluation import walk_forward_distribution_predict

    frame = _frame(40)
    x = frame.drop(columns="target_ret_1")
    y = frame["target_ret_1"].copy()
    first = walk_forward_distribution_predict(
        ZeroReturnModel, x, y, initial_train=20, retrain_every=5, volatility_window=10
    )
    changed = y.copy()
    changed.iloc[30:] = changed.iloc[30:] * 1000.0
    second = walk_forward_distribution_predict(
        ZeroReturnModel, x, changed, initial_train=20, retrain_every=5, volatility_window=10
    )

    pd.testing.assert_frame_equal(first.iloc[:10], second.iloc[:10])
    assert first["predicted_sigma"].gt(0.0).all()
    assert first["up_probability"].between(0.0, 1.0).all()


def test_phase_d_evaluation_runs_full_ladder_and_all_ablations() -> None:
    from commodity.phase_d_evaluation import run_phase_d_evaluation

    result, predictions = run_phase_d_evaluation(
        _frame(),
        _manifest(),
        model_names=("naive", "ridge", "hist_gb"),
        models=_models(),
        initial_train=40,
        retrain_every=5,
        volatility_window=10,
        significance={
            "block_size": 5,
            "resamples": 100,
            "confidence": 0.95,
            "seed": 0,
        },
    )

    assert len(result["evaluations"]) == 24
    assert len(predictions) == 24
    assert {item["ablation"] for item in result["evaluations"]} == {
        "full",
        "without:market",
        "without:market_structure",
        "without:storage",
        "without:weather",
        "without:power",
        "without:positioning",
        "without:calendar_seasonality",
    }
    assert len(result["candidate_comparisons"]) == 3
    assert len(result["ablation_effects"]) == 21
    assert all(0.0 <= item["adjusted_p_value"] <= 1.0 for item in result["ablation_effects"])
    assert result["regime_thresholds"]["low"] < result["regime_thresholds"]["high"]
    assert all(len(item["period_rmse_improvements"]) == 3 for item in result["candidate_comparisons"])
    assert all(set(item["regime_rmse_improvements"]) == {"low", "medium", "high"} for item in result["ablation_effects"])
    first = result["evaluations"][0]
    assert {"return", "direction", "volatility"} <= set(first["metrics"])


def test_phase_d_evaluation_rejects_unknown_or_empty_family() -> None:
    from commodity.phase_d_evaluation import feature_family_columns

    manifest = _manifest()
    manifest["required_feature_families"] = [*manifest["required_feature_families"], "unknown"]
    with pytest.raises(ValueError, match="unknown"):
        feature_family_columns(_frame(), manifest, target="target_ret_1")
