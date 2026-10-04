from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/research/run_issue465_adaptive_block.py"


def _load_runner():
    assert RUNNER.exists(), "issue465 adaptive block runner is not implemented"
    spec = importlib.util.spec_from_file_location("issue465_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_issue465_policy_grid_is_frozen_and_deterministic() -> None:
    runner = _load_runner()
    prereg = runner.load_prereg()
    policies = runner.build_policy_specs(prereg)
    assert prereg["status"] == "frozen_before_issue465_block1_scoring"
    assert len(policies) == 1126
    assert len({row["id"] for row in policies}) == 1126
    assert policies[0]["id"] == "flat"


def test_issue465_policy_grid_stays_within_research_size_boundary() -> None:
    runner = _load_runner()
    prereg = runner.load_prereg()
    policies = runner.build_policy_specs(prereg)
    exposures = {float(row["exposure"]) for row in policies}
    horizons = {int(row["horizon_sessions"]) for row in policies}
    sides = {str(row["side"]) for row in policies}
    assert exposures == {0.0, 0.75, 1.0, 1.5}
    assert horizons == {0, 1, 3, 5, 10, 20}
    assert sides == {"flat", "symmetric", "long_only", "short_only"}
    assert max(exposures) == prereg["execution_contract"]["max_abs_contracts_first_block"]


def test_issue465_block_filter_requires_outcome_to_mature_before_end() -> None:
    runner = _load_runner()
    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2011-01-03", "2011-01-04"], utc=True),
            "target_end_timestamp": pd.to_datetime(["2011-01-05", "2011-01-07"], utc=True),
        }
    )
    eligible = runner.eligible_block_origins(frame, pd.Timestamp("2011-01-06", tz="UTC"))
    assert eligible["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2011-01-03"]


def test_load_expert_frame_accepts_mixed_iso8601_precision(tmp_path: Path) -> None:
    import hashlib

    runner = _load_runner()
    path = tmp_path / "expert.csv"
    path.write_text(
        "trade_date,prediction_time,generated_at,value\n"
        "2010-07-06T00:00:00+00:00,2010-07-07T00:01:43.586000+00:00,2010-07-07T00:01:43.586000+00:00,1\n"
        "2010-07-07T00:00:00+00:00,2010-07-08T00:01:12+00:00,2010-07-08T00:01:12+00:00,2\n",
        encoding="utf-8",
    )
    expected_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    frame = runner.load_expert_frame(path, expected_sha, ["value"])
    assert len(frame) == 2
    assert str(frame["generated_at"].dtype) == "datetime64[ns, UTC]"


def test_issue465_prereg_has_explicit_historical_reentry_contract() -> None:
    runner = _load_runner()
    prereg = runner.load_prereg()
    rule = prereg["historical_reentry_rule"]
    assert rule["prior_records_are_hard_discarded"] is False
    assert "positive_clue" in rule["classifications"]
    assert "underpowered" in rule["classifications"]
    assert "source_hold" in rule["classifications"]


def test_performance_summary_tracks_cost_turnover_and_margin() -> None:
    runner = _load_runner()
    frame = pd.DataFrame(
        {
            "decision_time": pd.date_range("2010-07-01", periods=3, freq="D", tz="UTC"),
            "signal": [0.0, 1.5, -0.75],
            "turnover": [0.0, 1.5, 2.25],
            "realized_net_return": [0.0, 0.01, -0.02],
        }
    )
    summary = runner.performance_summary(
        frame, starting_capital=100000.0, cost_per_side=15.0, margin_per_contract=5000.0
    )
    assert summary["total_net_return"] == pytest.approx(-0.01)
    assert summary["turnover_contracts"] == pytest.approx(3.75)
    assert summary["transaction_cost_usd"] == pytest.approx(56.25)
    assert summary["max_abs_exposure_contracts"] == pytest.approx(1.5)
    assert summary["max_margin_utilization_fraction"] > 0.0


def test_current_code_identity_binds_runner_and_controller() -> None:
    runner = _load_runner()
    identity = runner.current_code_identity()
    assert set(identity) == {"runner_sha256", "controller_sha256"}
    assert all(len(value) == 64 for value in identity.values())


def test_validate_code_identity_rejects_stale_preflight() -> None:
    runner = _load_runner()
    identity = runner.current_code_identity()
    stale = dict(identity)
    stale["runner_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="code identity"):
        runner.validate_code_identity(stale)


def test_build_execution_path_uses_frozen_held_contract_move() -> None:
    runner = _load_runner()
    state = pd.DataFrame({
        "decision_time": pd.to_datetime(["2010-07-06T20:00:00Z"]),
        "fill_timestamp": pd.to_datetime(["2010-07-07T14:00:00Z"]),
        "fill_contract_id": ["NGQ10"],
        "target_end_timestamp": pd.to_datetime(["2010-07-08T14:00:00Z"]),
    })
    sessions = pd.DataFrame({
        "session_open": pd.to_datetime(["2010-07-07T14:00:00Z"]),
        "next_session_open": pd.to_datetime(["2010-07-08T14:00:00Z"]),
        "contract_id": ["NGQ10"],
        "path_move_per_mmbtu": [0.125],
    })
    path = runner.build_execution_path(state, sessions)
    assert path["path_move_per_mmbtu"].tolist() == [pytest.approx(0.125)]
    assert path["outcome_available_at"].iloc[0] == state["target_end_timestamp"].iloc[0]
    assert path["fill_contract_id"].tolist() == ["NGQ10"]


def test_canonicalize_executable_origins_keeps_latest_signal_per_fill() -> None:
    runner = _load_runner()
    origins = pd.DataFrame({
        "trade_date": pd.to_datetime(["2010-12-22", "2010-12-23"], utc=True),
        "signal_timestamp": pd.to_datetime(["2010-12-23T01:00:00Z", "2010-12-24T01:00:00Z"]),
        "fill_timestamp": pd.to_datetime(["2010-12-26", "2010-12-26"], utc=True),
        "fill_contract_id": ["NGF1", "NGF1"],
        "target_end_timestamp": pd.to_datetime(["2010-12-27", "2010-12-27"], utc=True),
    })
    canonical, stats = runner.canonicalize_executable_origins(origins)
    assert len(canonical) == 1
    assert canonical.iloc[0]["trade_date"] == pd.Timestamp("2010-12-23", tz="UTC")
    assert stats == {"input_origins": 2, "output_origins": 1, "collapsed": 1}
