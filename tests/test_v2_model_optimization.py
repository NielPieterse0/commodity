from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from commodity import v2_model_optimization as model_opt
from commodity.v2_model_optimization import (
    build_issue427_model_candidates,
    evaluate_issue427_advantage,
)

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "research/programmes/004-v2-maximum-reproducible-one-month-return/issue427-prereg-v1.json"
RUNNER = ROOT / "scripts/research/run_issue427_model_optimization.py"
RUNNER_SPEC = importlib.util.spec_from_file_location("issue427_runner", RUNNER)
assert RUNNER_SPEC is not None and RUNNER_SPEC.loader is not None
issue427_runner = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(issue427_runner)


def _base_config() -> dict[str, object]:
    return {
        "model.model_id": "ridge",
        "model.training_window": "expanding",
        "target.target_role": "direction",
    }


def test_issue427_model_grid_is_frozen_and_unique() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    rows = build_issue427_model_candidates(_base_config(), prereg)
    assert len(rows) == 45
    assert {row["model.model_id"] for row in rows} == {
        "expanding_mean",
        "ridge",
        "hist_gb",
    }


def test_issue427_advantage_requires_positive_mean_and_robust_outer_fraction() -> None:
    passed = evaluate_issue427_advantage(
        [0.001, 0.0, 0.0005], required_nonnegative_fraction=2.0 / 3.0
    )
    assert passed["passes"] is True
    assert passed["mean_outer_monthly_net_return_delta"] > 0.0

    failed = evaluate_issue427_advantage(
        [0.003, -0.001, -0.001], required_nonnegative_fraction=2.0 / 3.0
    )
    assert failed["passes"] is False


def test_issue427_volatility_tail_features_are_pit_safe() -> None:
    frame = pd.DataFrame(
        {
            "trade_date": pd.date_range("2020-01-01", periods=120, tz="UTC"),
            "available_at": pd.date_range("2020-01-01", periods=120, tz="UTC"),
            "feature_ret_1": [0.01 * ((index % 7) - 3) for index in range(120)],
        }
    )
    baseline = model_opt.build_issue427_volatility_tail_features(frame)
    changed = frame.copy()
    changed.loc[100:, "feature_ret_1"] = 9.0
    mutated = model_opt.build_issue427_volatility_tail_features(changed)

    specialist_columns = [column for column in baseline if column.startswith("feature_issue427_")]
    assert set(specialist_columns) == {
        "feature_issue427_ewma_vol",
        "feature_issue427_har_rv",
        "feature_issue427_garch_vol",
        "feature_issue427_jump_intensity",
        "feature_issue427_tail_loss_state",
        "feature_issue427_vol_of_vol",
    }
    pd.testing.assert_frame_equal(
        baseline.loc[:100, specialist_columns], mutated.loc[:100, specialist_columns]
    )

def test_issue427_specialist_merge_requires_exact_pit_identity() -> None:
    dates = pd.date_range("2020-01-01", periods=3, tz="UTC")
    features = pd.DataFrame(
        {"trade_date": dates, "available_at": dates + pd.Timedelta(hours=1)}
    )
    sessions = pd.DataFrame(
        {"trade_date": dates, "contract_id": ["A", "B", "C"]}
    )
    specialist = pd.DataFrame(
        {
            "trade_date": dates,
            "contract_id": ["A", "B", "C"],
            "prediction_time": [
                "2020-01-01T01:00:00.000000+00:00",
                "2020-01-02T01:00:00+00:00",
                "2020-01-03T01:00:00.000000+00:00",
            ],
            "specialist_value": [1.0, 2.0, 3.0],
        }
    )
    merged = model_opt.merge_issue427_specialist_features(
        features, sessions, specialist, ["specialist_value"]
    )
    assert merged["specialist_value"].tolist() == [1.0, 2.0, 3.0]

    specialist.loc[1, "prediction_time"] = "2020-01-02T01:00:01+00:00"
    with pytest.raises(model_opt.Issue427OptimizationError, match="information cutoff"):
        model_opt.merge_issue427_specialist_features(
            features, sessions, specialist, ["specialist_value"]
        )


def test_issue427_foundation_budget_uses_frozen_prereg_key(monkeypatch: pytest.MonkeyPatch) -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["budgets"]["foundation_policy_configs_max"] == 64
    monkeypatch.setattr(
        issue427_runner,
        "_foundation_feature_frame",
        lambda features, sessions: (pd.DataFrame(), {}),
    )
    monkeypatch.setattr(issue427_runner, "_outer_blocks", lambda cfg: {})
    monkeypatch.setattr(issue427_runner, "_foundation_context_evidence", dict)

    result = issue427_runner._score_foundation_features(
        prereg=prereg,
        features=pd.DataFrame(),
        sessions=pd.DataFrame(),
        cfg={},
        risk=object(),
        costs=object(),
        minimum_training_rows=1,
        selected_configs={},
        trials=[],
    )

    assert result["candidate_sets"] == {}