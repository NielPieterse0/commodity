from __future__ import annotations

import pandas as pd
import pytest

from commodity.v3_prequential import (
    CandidateSpec,
    PrequentialConfig,
    run_prequential,
    validate_prequential_frame,
)


def _frame(rows: int = 12) -> pd.DataFrame:
    decision = pd.date_range("2022-01-03", periods=rows, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "decision_time": decision,
            "outcome_available_at": decision + pd.Timedelta(hours=12),
            "path_move_per_mmbtu": [1.0, -1.0] * (rows // 2) + ([1.0] if rows % 2 else []),
            "signal_flat": 0.0,
            "signal_always_short": -1.0,
            "signal_trend_short": [-1.0, 0.0] * (rows // 2) + ([-1.0] if rows % 2 else []),
        }
    )


def _specs() -> tuple[CandidateSpec, ...]:
    return (
        CandidateSpec("flat", None, "signal_flat", 0),
        CandidateSpec("always_short", "flat", "signal_always_short", 0),
        CandidateSpec("trend_short", "always_short", "signal_trend_short", 1),
    )


def _config(**overrides: object) -> PrequentialConfig:
    values = {
        "initial_train_rows": 3,
        "retrain_every_rows": 2,
        "slow_update_every_rows": 4,
        "fast_window_rows": 2,
        "slow_window_rows": 3,
        "minimum_matured_rows": 1,
        "contract_multiplier": 1.0,
        "capital_usd": 100.0,
        "base_cost_per_side_usd": 0.0,
        "severe_extra_cost_per_side_usd": 0.0,
    }
    values.update(overrides)
    return PrequentialConfig(**values)


def test_rejects_any_protected_confirmation_outcome() -> None:
    frame = _frame(3)
    frame.loc[2, "decision_time"] = pd.Timestamp("2022-12-31T12:00:00Z")
    frame.loc[2, "outcome_available_at"] = pd.Timestamp("2023-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="protected confirmation"):
        validate_prequential_frame(frame, _specs())


def test_same_time_outcome_is_not_matured_for_next_decision() -> None:
    frame = _frame(6)
    frame.loc[0, "outcome_available_at"] = frame.loc[1, "decision_time"]
    result = run_prequential(frame, _specs(), _config(initial_train_rows=1))
    first_live = result.decisions.iloc[1]
    assert first_live["matured_candidate_rows"] == 0


def test_initial_history_is_training_only_and_updates_follow_frozen_cadence() -> None:
    result = run_prequential(_frame(), _specs(), _config())
    assert result.decisions.iloc[:3]["training_only"].all()
    assert result.decisions.iloc[:3]["target_exposure"].eq(0.0).all()
    assert result.learning_events["decision_index"].tolist() == [3, 5, 7, 9, 11]
    assert result.learning_events.loc[
        result.learning_events["slow_update"], "decision_index"
    ].tolist() == [3, 7, 11]


def test_future_outcome_mutation_cannot_change_prior_decisions() -> None:
    frame = _frame(12)
    baseline = run_prequential(frame, _specs(), _config())
    mutated = frame.copy()
    mutated.loc[8:, "path_move_per_mmbtu"] *= -100.0
    changed = run_prequential(mutated, _specs(), _config())
    columns = ["decision_time", "selected_candidate_id", "target_exposure"]
    pd.testing.assert_frame_equal(
        baseline.decisions.loc[:8, columns].reset_index(drop=True),
        changed.decisions.loc[:8, columns].reset_index(drop=True),
    )


def test_failed_challenger_remains_registered_at_zero_weight() -> None:
    frame = _frame(12)
    frame["path_move_per_mmbtu"] = 1.0
    result = run_prequential(frame, _specs(), _config())
    last = result.learning_events.iloc[-1]
    assert "trend_short" in last["candidate_weights"]
    assert last["candidate_weights"]["trend_short"] == 0.0


def test_child_requires_parent_relative_severe_edge_before_promotion() -> None:
    frame = _frame(12)
    frame["path_move_per_mmbtu"] = [-1.0, 1.0] * 6
    result = run_prequential(frame, _specs(), _config())
    events = result.learning_events
    promoted = events["promoted_candidates"].tolist()
    assert all("trend_short" not in row or "always_short" in row for row in promoted)
    assert set(result.candidate_specs["candidate_id"]) == {
        "flat",
        "always_short",
        "trend_short",
    }


def test_lifetime_evidence_contains_frozen_memory_bank_and_expanding() -> None:
    result = run_prequential(_frame(), _specs(), _config())
    memories = set(result.evidence["memory"].unique())
    assert {"5", "10", "20", "40", "60", "126", "252", "expanding"}.issubset(memories)
    assert set(result.evidence["scenario"].unique()) == {"base", "severe"}
    assert result.protected_confirmation_accessed is False


def test_result_exposes_parent_relative_edge_contribution() -> None:
    result = run_prequential(_frame(), _specs(), _config())
    rows = result.edge_contribution.set_index("candidate_id")
    assert rows.loc["always_short", "parent_id"] == "flat"
    assert rows.loc["trend_short", "parent_id"] == "always_short"
    assert "incremental_severe_net_return" in rows.columns
    assert len(result.freeze_sha256) == 64


def test_default_candidate_tree_contains_permanent_ladder() -> None:
    from commodity.v3_prequential import default_candidate_specs

    specs = default_candidate_specs()
    ids = [row.candidate_id for row in specs]
    for required in (
        "flat",
        "always_short",
        "trend_short",
        "curve_short",
        "trend_curve_short",
        "timesfm_short",
        "trend_timesfm_short",
        "kronos_short",
        "low_vol_trend_short",
        "jump_veto_trend_short",
        "timesfm_long_challenger",
        "current_v3",
    ):
        assert required in ids
    by_id = {row.candidate_id: row for row in specs}
    assert by_id["always_short"].parent_id == "flat"
    assert by_id["trend_short"].parent_id == "always_short"
    assert by_id["curve_short"].parent_id == "always_short"
    assert by_id["current_v3"].complexity > by_id["trend_curve_short"].complexity
    assert any(row.role == "negative_control" for row in specs)


def test_default_signals_are_bounded_and_future_invariant() -> None:
    from commodity.v3_prequential import build_default_candidate_signals

    index = pd.date_range("2020-01-01", periods=40, freq="D", tz="UTC")
    features = pd.DataFrame(
        {
            "decision_time": index,
            "feature_ret_1": [(-0.02 if i % 2 else 0.01) for i in range(40)],
            "feature_ret_20": [(-1.0 if i % 3 else 1.0) for i in range(40)],
            "feature_ret_5": [(-0.5 if i % 2 else 0.5) for i in range(40)],
            "feature_ma_gap_20": [(-0.2 if i % 4 else 0.2) for i in range(40)],
            "feature_curve_slope_m1_m4": [(0.1 if i % 5 else -0.1) for i in range(40)],
            "feature_vol_20": [0.2 + i / 1000 for i in range(40)],
            "feature_vol_5": [0.1 + i / 1000 for i in range(40)],
            "timesfm_point_return": [(-0.01 if i % 4 else 0.02) for i in range(40)],
            "kronos_close_return": [(-0.02 if i % 5 else 0.01) for i in range(40)],
        }
    )
    baseline = build_default_candidate_signals(features)
    changed = features.copy()
    changed.loc[25:, "feature_ret_20"] *= -100
    changed.loc[25:, "feature_curve_slope_m1_m4"] *= -100
    mutated = build_default_candidate_signals(changed)
    pd.testing.assert_frame_equal(
        baseline.iloc[:25].reset_index(drop=True),
        mutated.iloc[:25].reset_index(drop=True),
    )
    signal_cols = [column for column in baseline if column.startswith("signal_")]
    assert baseline[signal_cols].isin([-1.0, 0.0, 1.0]).all().all()


def test_smallest_passing_architecture_beats_higher_return_complexity() -> None:
    from commodity.v3_prequential import select_smallest_passing_architecture

    specs = (
        CandidateSpec("flat", None, "signal_flat", 0),
        CandidateSpec("simple", "flat", "signal_simple", 1),
        CandidateSpec("complex", "simple", "signal_complex", 3),
    )
    report = pd.DataFrame(
        [
            {"candidate_id": "flat", "passes_all_gates": False, "severe_net_return": 0.0},
            {"candidate_id": "simple", "passes_all_gates": True, "severe_net_return": 0.12},
            {"candidate_id": "complex", "passes_all_gates": True, "severe_net_return": 0.30},
        ]
    )
    selected = select_smallest_passing_architecture(report, specs)
    assert selected == "simple"


def test_execution_frame_uses_first_fill_after_decision_and_safe_outcome() -> None:
    from commodity.v3_prequential import build_one_session_execution_frame

    features = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2022-12-27", "2022-12-28"], utc=True),
            "available_at": pd.to_datetime(
                ["2022-12-27T15:00:00Z", "2022-12-28T15:00:00Z"], utc=True
            ),
            "feature_curve_log_volume_m1": [2.0, 1.0],
            "signal_flat": [0.0, 0.0],
            "signal_always_short": [-1.0, -1.0],
        }
    )
    sessions = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(
                ["2022-12-27", "2022-12-28", "2022-12-29"], utc=True
            ),
            "session_open": pd.to_datetime(
                ["2022-12-27T14:00:00Z", "2022-12-28T14:00:00Z", "2022-12-29T14:00:00Z"],
                utc=True,
            ),
            "available_at": pd.to_datetime(
                ["2022-12-27T13:00:00Z", "2022-12-28T13:00:00Z", "2022-12-29T13:00:00Z"],
                utc=True,
            ),
            "next_session_open": pd.to_datetime(
                ["2022-12-28T14:00:00Z", "2022-12-29T14:00:00Z", "2022-12-30T14:00:00Z"],
                utc=True,
            ),
            "path_move_per_mmbtu": [0.1, -0.2, 0.3],
        }
    )
    out = build_one_session_execution_frame(features, sessions)
    assert out["fill_timestamp"].tolist() == [
        pd.Timestamp("2022-12-28T14:00:00Z"),
        pd.Timestamp("2022-12-29T14:00:00Z"),
    ]
    assert out["outcome_available_at"].tolist() == [
        pd.Timestamp("2022-12-29T14:00:00Z"),
        pd.Timestamp("2022-12-30T14:00:00Z"),
    ]
    assert out["path_move_per_mmbtu"].tolist() == [-0.2, 0.3]
    assert (out["decision_time"] < out["fill_timestamp"]).all()
    assert (out["outcome_available_at"] < pd.Timestamp("2023-01-01", tz="UTC")).all()


def test_robustness_rejects_one_period_edge_and_accepts_recurring_edge() -> None:
    from commodity.v3_prequential import RobustnessConfig, evaluate_robustness

    times = pd.to_datetime(["2018-06-01", "2019-06-01", "2020-06-01", "2021-06-01"], utc=True)
    rows = []
    for scenario, multiplier in (("base", 1.1), ("severe", 1.0)):
        for candidate_id, returns in (
            ("flat", [0.0, 0.0, 0.0, 0.0]),
            ("recurring", [0.10, 0.08, 0.07, 0.06]),
            ("one_hit", [0.50, -0.01, -0.01, -0.01]),
        ):
            for stamp, value in zip(times, returns, strict=True):
                rows.append(
                    {
                        "decision_time": stamp,
                        "candidate_id": candidate_id,
                        "scenario": scenario,
                        "realized_net_return": value * multiplier,
                        "executed_signal": 1.0 if candidate_id != "flat" else 0.0,
                        "turnover": 1.0 if candidate_id != "flat" else 0.0,
                    }
                )
    specs = (
        CandidateSpec("flat", None, "signal_flat", 0),
        CandidateSpec("recurring", "flat", "signal_recurring", 1),
        CandidateSpec("one_hit", "flat", "signal_one_hit", 1),
    )
    report = evaluate_robustness(
        pd.DataFrame(rows),
        specs,
        RobustnessConfig(
            minimum_positive_periods=3,
            minimum_recurrence_rate=0.60,
            max_drawdown_fraction=0.25,
            max_best_period_concentration=0.70,
            multiplicity_alpha=1.0,
        ),
    ).set_index("candidate_id")
    assert bool(report.loc["recurring", "passes_all_gates"])
    assert not bool(report.loc["one_hit", "passes_all_gates"])
    assert report.loc["one_hit", "leave_best_period_incremental_return"] < 0.0


def test_authoritative_freeze_requires_exact_code_data_and_protected_boundary() -> None:
    from commodity.v3_prequential import validate_authoritative_freeze

    expected = {
        "engine_sha256": "a" * 64,
        "runner_sha256": "b" * 64,
        "features_sha256": "c" * 64,
        "session_path_sha256": "d" * 64,
        "sealed_registry_sha256": "e" * 64,
    }
    freeze = {
        "status": "FROZEN_BEFORE_AUTHORITATIVE_TRAVERSAL",
        "protected_confirmation_accessed": False,
        "protected_start": "2023-01-01T00:00:00Z",
        "identity": dict(expected),
    }
    validate_authoritative_freeze(freeze, expected)
    broken = {**freeze, "identity": {**expected, "runner_sha256": "f" * 64}}
    with pytest.raises(ValueError, match="runner_sha256"):
        validate_authoritative_freeze(broken, expected)


def test_future_invariance_proof_mutates_only_future_suffix() -> None:
    from commodity.v3_prequential import future_invariance_proof

    frame = _frame(14)
    proof = future_invariance_proof(
        frame,
        _specs(),
        _config(),
        cut_indices=(6, 10),
        mutation_scale=-37.0,
    )
    assert proof["status"] == "PASS"
    assert proof["cut_count"] == 2
    assert all(row["prefix_equal"] for row in proof["checks"])


def test_execution_frame_drops_terminal_rows_without_matured_safe_outcome() -> None:
    from commodity.v3_prequential import build_one_session_execution_frame

    features = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2022-12-29"], utc=True),
            "available_at": pd.to_datetime(["2022-12-30T14:30:00Z"], utc=True),
        }
    )
    sessions = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2022-12-29", "2022-12-30"], utc=True),
            "session_open": pd.to_datetime(
                ["2022-12-29T00:00:00Z", "2022-12-30T00:00:00Z"], utc=True
            ),
            "available_at": pd.to_datetime(
                ["2022-12-28T15:00:00Z", "2022-12-29T15:00:00Z"], utc=True
            ),
            "next_session_open": pd.to_datetime(
                ["2022-12-30T00:00:00Z", None], utc=True
            ),
            "path_move_per_mmbtu": [0.1, 0.0],
        }
    )
    out = build_one_session_execution_frame(features, sessions)
    assert out.empty


def test_score_exposure_path_applies_training_flat_and_execution_stress() -> None:
    from commodity.v3_prequential import score_exposure_path

    frame = _frame(8)
    exposure = pd.Series([0.0, 0.0, -1.0, -1.0, -1.0, 0.0, -1.0, -1.0])
    scored = score_exposure_path(frame, exposure, _config())
    assert set(scored["scenario"]) == {"base", "severe"}
    base = scored.loc[scored["scenario"] == "base"].reset_index(drop=True)
    assert base.loc[:1, "signal"].eq(0.0).all()
    assert base.loc[2, "signal"] == -1.0
    severe = scored.loc[scored["scenario"] == "severe"].reset_index(drop=True)
    assert severe["realized_net_return"].sum() <= base["realized_net_return"].sum()


def test_foundation_expert_merge_requires_strictly_available_rows() -> None:
    from commodity.v3_prequential import attach_foundation_experts

    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2020-01-02", "2020-01-03"], utc=True),
            "decision_time": pd.to_datetime(
                ["2020-01-03T14:00:00Z", "2020-01-04T14:00:00Z"], utc=True
            ),
        }
    )
    common = {
        "trade_date": pd.to_datetime(["2020-01-02", "2020-01-03"], utc=True),
        "prediction_time": pd.to_datetime(
            ["2020-01-03T00:00:00Z", "2020-01-04T00:00:00Z"], utc=True
        ),
        "generated_at": pd.to_datetime(
            ["2020-01-03T00:00:00Z", "2020-01-04T00:00:00Z"], utc=True
        ),
    }
    timesfm = pd.DataFrame(
        {**common, "timesfm_point_return": [-0.1, 0.2], "timesfm_q10_return": [-0.2, -0.1], "timesfm_q90_return": [0.1, 0.4], "timesfm_interval_width": [0.3, 0.5]}
    )
    kronos = pd.DataFrame({**common, "kronos_close_return": [-0.2, 0.1], "kronos_range_pct": [0.04, 0.05]})
    merged = attach_foundation_experts(frame, timesfm, kronos)
    assert merged["timesfm_point_return"].tolist() == [-0.1, 0.2]
    assert merged["kronos_close_return"].tolist() == [-0.2, 0.1]
    bad = timesfm.copy()
    bad.loc[1, "generated_at"] = pd.Timestamp("2020-01-05T00:00:00Z")
    with pytest.raises(ValueError, match="TimesFM.*decision"):
        attach_foundation_experts(frame, bad, kronos)
