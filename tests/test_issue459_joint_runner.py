from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/research/run_issue459_joint_advantage.py"
ISSUE448_PREFLIGHT_CACHE = (
    ROOT / "data/raw/issue448/preflight-features.parquet"
)
ISSUE448_FAMILY_CACHE = ROOT / "data/raw/issue448/preflight-families.json"


def _load_runner():
    assert RUNNER.exists(), "issue459 joint runner is not implemented"
    spec = importlib.util.spec_from_file_location("issue459_joint_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_issue459_preflight_is_source_bound_and_does_not_score() -> None:
    if not ISSUE448_PREFLIGHT_CACHE.exists() or not ISSUE448_FAMILY_CACHE.exists():
        pytest.skip("issue459 source-bound preflight requires the local issue448 preflight cache")
    runner = _load_runner()
    report = runner.preflight(write=False)

    assert report["status"] == "PASS"
    assert report["scoring_performed"] is False
    assert report["protected_confirmation_accessed"] is False
    assert report["feature_rows"] == 3088
    assert report["session_rows"] == 3897
    assert report["wave1_candidate_count"] == 1584
    assert report["priority_clue_count"] == 8
    assert report["failures"] == []


def test_issue459_wave2_preflight_is_frozen_and_does_not_score() -> None:
    runner = _load_runner()
    report = runner.preflight_wave2(write=False)

    assert report["status"] == "PASS"
    assert report["scoring_performed"] is False
    assert report["protected_confirmation_accessed"] is False
    assert report["wave2_candidate_count"] == 46
    assert report["expected_outer_cost_trial_count"] == 276
    assert report["timesfm_rows"] == 3088
    assert report["kronos_rows"] == 3088
    assert report["failures"] == []


def test_issue459_wave2_specialist_join_is_pit_safe() -> None:
    runner = _load_runner()
    trade_dates = pd.to_datetime(["2020-01-02", "2020-01-03"], utc=True)
    policy = pd.DataFrame(
        {
            "trade_date": trade_dates,
            "signal_timestamp": pd.to_datetime(
                ["2020-01-03T00:02:00Z", "2020-01-06T00:02:00Z"], utc=True
            ),
        }
    )
    timesfm = pd.DataFrame(
        {
            "trade_date": trade_dates,
            "prediction_time": pd.to_datetime(
                ["2020-01-03T00:01:00Z", "2020-01-06T00:01:00Z"], utc=True
            ),
            "timesfm_point_return": [0.01, -0.02],
        }
    )
    kronos = timesfm.rename(columns={"timesfm_point_return": "kronos_close_return"}).copy()

    joined = runner._join_wave2_specialists(policy, timesfm, kronos)
    assert joined["timesfm_point_return"].tolist() == [0.01, -0.02]
    assert joined["kronos_close_return"].tolist() == [0.01, -0.02]

    timesfm.loc[0, "prediction_time"] = pd.Timestamp("2020-01-03T00:03:00Z")
    with pytest.raises(RuntimeError, match="after signal timestamp"):
        runner._join_wave2_specialists(policy, timesfm, kronos)
