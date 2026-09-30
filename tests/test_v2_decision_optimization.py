from __future__ import annotations

import pandas as pd
import pytest

from commodity.v2_decision_optimization import (
    Issue428DecisionError,
    annotate_conditional_signal,
    annotate_issue428_states,
    apply_issue428_policy,
    build_issue428_candidate_grid,
    completed_history_before,
    fit_conditional_signal_state,
    fit_issue428_state,
    fit_meta_confidence,
    predict_meta_confidence,
    select_issue428_policy,
    validate_issue428_evidence_boundary,
)
from scripts.research.run_issue428_decision_optimization import _effective_sample


def _prereg() -> dict[str, object]:
    return {
        "candidate_grid": {
            "strength_quantile_gates": [0.50, 0.65, 0.80],
            "model_agreement_gate": True,
            "favored_signal_count_gates": [3, 4, 5],
            "strength_fusion_cross": {
                "strength_quantiles": [0.50, 0.65],
                "favored_signal_counts": [3, 4],
            },
            "jump_veto_quantiles": [0.75, 0.90],
            "vol_of_vol_veto_quantiles": [0.75, 0.90],
            "joint_volatility_veto_quantiles": [0.75, 0.90],            "favorable_regime_persistence": [1, 2, 3],
            "meta_basic_probability_thresholds": [0.50, 0.55, 0.60, 0.65],
            "meta_interaction_probability_thresholds": [0.50, 0.55, 0.60, 0.65],
            "expected_configuration_count": 29,
        }
    }


def _history(rows: int = 240) -> pd.DataFrame:
    dates = pd.date_range("2014-01-02", periods=rows, freq="B", tz="UTC")
    values = pd.Series(range(rows), dtype=float)
    frame = pd.DataFrame(
        {
            "trade_date": dates,
            "fill_timestamp": dates,
            "target_end_timestamp": dates + pd.Timedelta(days=2),
            "baseline_position": [1.0 if index % 3 else -1.0 for index in range(rows)],
            "primary_strength": 0.5 + values / rows * 2.0,
            "model_agreement": [1.0 if index % 4 else 0.0 for index in range(rows)],
            "normalized_model_disagreement": [abs((index % 11) - 5) / 5.0 for index in range(rows)],
            "jump_intensity": [float(index % 20) / 20.0 for index in range(rows)],
            "vol_of_vol": [float((index * 7) % 23) / 23.0 for index in range(rows)],
            "net_trade_utility_usd": [150.0 if index % 5 else -250.0 for index in range(rows)],
            "trade_profitable": [1 if index % 5 else 0 for index in range(rows)],
        }
    )
    for offset in range(6):
        frame[f"signal_{offset}"] = ((values + offset * 7) % 37) / 37.0
    return frame


def _outcome_boundary(frame: pd.DataFrame) -> pd.Timestamp:
    target_end = pd.to_datetime(frame["target_end_timestamp"], utc=True, errors="raise")
    return pd.Timestamp(target_end.max()) + pd.Timedelta(days=1)


def test_candidate_grid_is_frozen_at_29_unique_configs() -> None:
    grid = build_issue428_candidate_grid(_prereg())
    assert len(grid) == 29
    assert len({item.config_id for item in grid}) == 29
    assert grid[0].config_id == "baseline"


def test_candidate_grid_rejects_same_size_parameter_substitution() -> None:
    prereg = _prereg()
    grid = dict(prereg["candidate_grid"])
    grid["strength_quantile_gates"] = [0.50, 0.651, 0.80]
    prereg["candidate_grid"] = grid

    with pytest.raises(Issue428DecisionError, match="frozen candidate-grid identity changed"):
        build_issue428_candidate_grid(prereg)


def test_evidence_boundary_rejects_2023_rows() -> None:
    validate_issue428_evidence_boundary(pd.DataFrame({"trade_date": ["2022-12-30"]}))
    with pytest.raises(Issue428DecisionError, match="protected"):
        validate_issue428_evidence_boundary(pd.DataFrame({"trade_date": ["2023-01-03"]}))
    with pytest.raises(Issue428DecisionError, match="realized outcomes"):
        validate_issue428_evidence_boundary(
            pd.DataFrame(
                {
                    "trade_date": ["2022-12-01"],
                    "target_end_timestamp": ["2023-01-01"],
                }
            )
        )


def test_completed_history_requires_outcome_strictly_before_boundary() -> None:
    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2018-12-27", "2018-12-28", "2018-12-29"], utc=True),
            "fill_timestamp": pd.to_datetime(["2018-12-27", "2018-12-28", "2018-12-29"], utc=True),
            "target_end_timestamp": pd.to_datetime(
                ["2018-12-31", "2019-01-01", "2019-01-02"], utc=True
            ),
            "row_id": ["completed", "equal_boundary", "future_outcome"],
        }
    )

    history = completed_history_before(frame, pd.Timestamp("2019-01-01", tz="UTC"))

    assert history["row_id"].tolist() == ["completed"]
    assert history["target_end_timestamp"].max() < pd.Timestamp("2019-01-01", tz="UTC")


def test_effective_sample_counts_risk_executed_ledger_trades() -> None:
    dates = pd.to_datetime(["2020-01-03", "2020-02-03", "2020-03-03"], utc=True)
    policy = pd.DataFrame(
        {
            "fill_trade_date": dates,
            "baseline_position": [1.0, 1.0, 1.0],
            "signal_requested_position": [1.0, 1.0, 1.0],
            "policy_abstained": [False, False, False],
        }
    )
    ledger = pd.DataFrame(
        {
            "trade_date": dates,
            "target_position": [1.0, 0.0, 1.0],
        }
    )
    prereg = {
        "effective_sample_controls": {
            "minimum_outer_trade_opportunities": 3,
            "minimum_selected_trades": 3,
            "minimum_nonempty_months": 3,
        }
    }

    effective = _effective_sample(
        policy,
        ledger,
        {"signal_abstention_sessions": 0, "risk_shutdown_sessions": 1},
        prereg,
    )

    assert effective["requested_selected_trades"] == 3
    assert effective["selected_trades"] == 2
    assert effective["risk_or_margin_excluded_selected_trades"] == 1
    assert effective["monthly_trade_counts"] == {"2020-01": 1, "2020-03": 1}
    assert effective["passes_outer_minimums"] is False


def test_fitted_signal_states_use_prior_utility_not_future_rows() -> None:
    history = _history()
    signals = [f"signal_{index}" for index in range(6)]
    state = fit_issue428_state(
        history,
        signal_columns=signals,
        minimum_state_rows=30,
        outcome_available_before=_outcome_boundary(history),
    )
    mutated = history.copy()
    mutated.loc[mutated.index[-20:], "net_trade_utility_usd"] = 1_000_000.0
    earlier = fit_issue428_state(
        mutated.iloc[:-20],
        signal_columns=signals,
        minimum_state_rows=30,
        outcome_available_before=_outcome_boundary(mutated.iloc[:-20]),
    )
    reference = fit_issue428_state(
        history.iloc[:-20],
        signal_columns=signals,
        minimum_state_rows=30,
        outcome_available_before=_outcome_boundary(history.iloc[:-20]),
    )
    assert earlier.signal_states == reference.signal_states
    assert state.signal_states


def test_outcome_dependent_fitters_reject_history_crossing_as_of_boundary() -> None:
    history = _history(260)
    history["oi_signal"] = (pd.Series(range(len(history)), dtype=float) % 41) / 41.0
    signals = [f"signal_{index}" for index in range(6)]
    boundary = pd.Timestamp(history.loc[180, "trade_date"])
    safe_history = completed_history_before(history, boundary)
    state = fit_issue428_state(
        safe_history,
        signal_columns=signals,
        minimum_state_rows=30,
        outcome_available_before=boundary,
    )
    annotated = annotate_issue428_states(history, state, signal_columns=signals)

    with pytest.raises(Issue428DecisionError, match="outcome-availability boundary"):
        fit_issue428_state(
            history,
            signal_columns=signals,
            minimum_state_rows=30,
            outcome_available_before=boundary,
        )
    with pytest.raises(Issue428DecisionError, match="outcome-availability boundary"):
        fit_conditional_signal_state(
            history,
            column="oi_signal",
            minimum_history_rows=100,
            minimum_state_rows=30,
            outcome_available_before=boundary,
        )
    with pytest.raises(Issue428DecisionError, match="outcome-availability boundary"):
        fit_meta_confidence(
            annotated,
            signal_columns=signals,
            mode="basic",
            minimum_train_rows=100,
            minimum_calibration_rows=50,
            outcome_available_before=boundary,
        )


def test_annotation_produces_favored_fraction_and_persistent_regime() -> None:
    history = _history()
    signals = [f"signal_{index}" for index in range(6)]
    state = fit_issue428_state(
        history.iloc[:180],
        signal_columns=signals,
        minimum_state_rows=30,
        outcome_available_before=_outcome_boundary(history.iloc[:180]),
    )
    scored = annotate_issue428_states(history.iloc[180:].copy(), state, signal_columns=signals)
    assert scored["eligible_signal_count"].min() >= 1
    assert scored["favored_fraction"].between(0.0, 1.0).all()
    assert set(scored["regime_persistence"].astype(int)) <= set(range(1, len(scored) + 1))


def test_annotation_rejects_missing_retained_signal_value() -> None:
    history = _history()
    signals = [f"signal_{index}" for index in range(6)]
    state = fit_issue428_state(
        history.iloc[:180],
        signal_columns=signals,
        minimum_state_rows=30,
        outcome_available_before=_outcome_boundary(history.iloc[:180]),
    )
    eligible_column = next(
        column for column, info in state.signal_states.items() if bool(info["eligible"])
    )
    scored = history.iloc[180:].copy()
    scored.loc[scored.index[0], eligible_column] = float("nan")

    with pytest.raises(Issue428DecisionError, match="retained signal contains missing values"):
        annotate_issue428_states(scored, state, signal_columns=signals)


def test_simple_gate_abstains_without_changing_trade_side() -> None:
    history = _history()
    signals = [f"signal_{index}" for index in range(6)]
    state = fit_issue428_state(
        history.iloc[:180],
        signal_columns=signals,
        minimum_state_rows=30,
        outcome_available_before=_outcome_boundary(history.iloc[:180]),
    )
    scored = annotate_issue428_states(history.iloc[180:].copy(), state, signal_columns=signals)
    config = next(item for item in build_issue428_candidate_grid(_prereg()) if item.kind == "model_agreement")
    decisions = apply_issue428_policy(scored, config, state)
    assert set(decisions["signal_requested_position"].unique()) <= {-1.0, 0.0, 1.0}
    kept = decisions["signal_requested_position"] != 0.0
    assert (decisions.loc[kept, "signal_requested_position"] == scored.loc[kept, "baseline_position"]).all()
    assert (decisions.loc[~scored["model_agreement"].astype(bool), "signal_requested_position"] == 0.0).all()


def test_meta_confidence_uses_chronological_calibration_split() -> None:
    history = _history()
    signals = [f"signal_{index}" for index in range(6)]
    boundary = _outcome_boundary(history)
    state = fit_issue428_state(
        history,
        signal_columns=signals,
        minimum_state_rows=30,
        outcome_available_before=boundary,
    )
    annotated = annotate_issue428_states(history, state, signal_columns=signals)
    meta = fit_meta_confidence(
        annotated,
        signal_columns=signals,
        mode="basic",
        minimum_train_rows=100,
        minimum_calibration_rows=50,
        outcome_available_before=boundary,
    )
    assert meta.active is True
    assert meta.training_end < meta.calibration_start
    assert meta.calibration_rows >= 50
    predicted = predict_meta_confidence(annotated.tail(20), meta, signal_columns=signals)
    assert predicted.between(0.0, 1.0).all()
    assert meta.brier_score is not None


def test_meta_confidence_keeps_duplicate_boundary_dates_on_calibration_side() -> None:
    history = _history(320)
    boundary_date = history.loc[240, "trade_date"]
    history.loc[238:242, "trade_date"] = boundary_date
    signals = [f"signal_{index}" for index in range(6)]
    outcome_boundary = _outcome_boundary(history)
    state = fit_issue428_state(
        history,
        signal_columns=signals,
        minimum_state_rows=30,
        outcome_available_before=outcome_boundary,
    )
    annotated = annotate_issue428_states(history, state, signal_columns=signals)

    meta = fit_meta_confidence(
        annotated,
        signal_columns=signals,
        mode="basic",
        minimum_train_rows=100,
        minimum_calibration_rows=50,
        outcome_available_before=outcome_boundary,
    )

    assert meta.training_end < meta.calibration_start
    assert meta.calibration_rows == 82


def test_meta_confidence_excludes_training_candidate_with_late_outcome() -> None:
    reference_history = _history(320)
    mutated_history = reference_history.copy()
    mutated_history.loc[200, "target_end_timestamp"] = mutated_history.loc[260, "trade_date"]
    signals = [f"signal_{index}" for index in range(6)]
    outcome_boundary = _outcome_boundary(reference_history)
    state = fit_issue428_state(
        reference_history,
        signal_columns=signals,
        minimum_state_rows=30,
        outcome_available_before=outcome_boundary,
    )
    reference = fit_meta_confidence(
        annotate_issue428_states(reference_history, state, signal_columns=signals),
        signal_columns=signals,
        mode="basic",
        minimum_train_rows=100,
        minimum_calibration_rows=50,
        outcome_available_before=outcome_boundary,
    )
    mutated = fit_meta_confidence(
        annotate_issue428_states(mutated_history, state, signal_columns=signals),
        signal_columns=signals,
        mode="basic",
        minimum_train_rows=100,
        minimum_calibration_rows=50,
        outcome_available_before=outcome_boundary,
    )

    assert mutated.training_rows == reference.training_rows - 1
    assert mutated.training_end < mutated.calibration_start


def test_meta_interaction_feature_set_accepts_six_retained_signals() -> None:
    history = _history(320)
    signals = [f"signal_{index}" for index in range(6)]
    boundary = _outcome_boundary(history)
    state = fit_issue428_state(
        history,
        signal_columns=signals,
        minimum_state_rows=30,
        outcome_available_before=boundary,
    )
    annotated = annotate_issue428_states(history, state, signal_columns=signals)
    meta = fit_meta_confidence(
        annotated,
        signal_columns=signals,
        mode="interactions",
        minimum_train_rows=100,
        minimum_calibration_rows=50,
        outcome_available_before=boundary,
    )
    assert meta.active is True
    assert len(meta.feature_columns) > 6


def test_selection_uses_only_complete_prior_years_and_prefers_simpler_tie() -> None:
    scores = pd.DataFrame(
        [
            {"config_id": cfg, "year": year, "net_pnl_usd": pnl, "mean_monthly_net_return": pnl / 10000.0,
             "max_drawdown_fraction": 0.05, "transaction_cost_usd": 20.0, "complexity": complexity}
            for cfg, complexity, pnl in (("simple", 1, 100.0), ("complex", 5, 100.0))
            for year in (2015, 2016)
        ]
        + [{"config_id": "complex", "year": 2019, "net_pnl_usd": 9999.0,
            "mean_monthly_net_return": 0.9, "max_drawdown_fraction": 0.01,
            "transaction_cost_usd": 1.0, "complexity": 5}]
    )
    selected = select_issue428_policy(scores, outer_start_year=2019)
    assert selected["config_id"] == "simple"
    assert selected["years"] == [2015, 2016]
    assert 2019 not in selected["years"]


def test_selection_can_require_common_comparison_years() -> None:
    rows = []
    for config_id, complexity, yearly in (
        ("simple", 1, {2018: 1000.0, 2019: 100.0, 2020: 100.0}),
        ("meta", 5, {2019: 200.0, 2020: 200.0}),
    ):
        for year, pnl in yearly.items():
            rows.append({
                "config_id": config_id,
                "year": year,
                "net_pnl_usd": pnl,
                "mean_monthly_net_return": pnl / 10000.0,
                "max_drawdown_fraction": 0.05,
                "transaction_cost_usd": 20.0,
                "complexity": complexity,
            })
    selected = select_issue428_policy(
        pd.DataFrame(rows),
        outer_start_year=2021,
        required_years=[2019, 2020],
    )
    assert selected["config_id"] == "meta"
    assert selected["years"] == [2019, 2020]


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("net_pnl_usd", float("inf")),
        ("mean_monthly_net_return", float("inf")),
        ("max_drawdown_fraction", float("-inf")),
        ("transaction_cost_usd", float("-inf")),
        ("complexity", float("-inf")),
    ],
)
def test_selection_excludes_non_finite_ranking_metrics(
    field: str,
    invalid_value: float,
) -> None:
    rows = []
    for config_id, pnl in (("finite", 100.0), ("invalid", 200.0)):
        for year in (2019, 2020):
            row = {
                "config_id": config_id,
                "year": year,
                "net_pnl_usd": pnl,
                "mean_monthly_net_return": pnl / 10000.0,
                "max_drawdown_fraction": 0.05,
                "transaction_cost_usd": 20.0,
                "complexity": 1,
            }
            if config_id == "invalid":
                row[field] = invalid_value
            rows.append(row)

    selected = select_issue428_policy(
        pd.DataFrame(rows),
        outer_start_year=2021,
        required_years=[2019, 2020],
    )

    assert selected["config_id"] == "finite"


def test_conditional_signal_state_is_prior_only_and_annotatable() -> None:
    history = _history(260)
    history["oi_signal"] = (pd.Series(range(len(history)), dtype=float) % 41) / 41.0
    state = fit_conditional_signal_state(
        history.iloc[:200],
        column="oi_signal",
        minimum_history_rows=100,
        minimum_state_rows=30,
        outcome_available_before=_outcome_boundary(history.iloc[:200]),
    )
    scored = annotate_conditional_signal(history.iloc[200:].copy(), state)
    assert state.favored in {"high", "low"}
    assert scored["oi_signal__z"].notna().all()
    assert set(scored["oi_signal__favored"].unique()) <= {0, 1}


def test_meta_confidence_supports_extra_features_and_remove_one_ablation() -> None:
    history = _history(360)
    signals = [f"signal_{index}" for index in range(6)]
    boundary = _outcome_boundary(history)
    state = fit_issue428_state(
        history,
        signal_columns=signals,
        minimum_state_rows=30,
        outcome_available_before=boundary,
    )
    annotated = annotate_issue428_states(history, state, signal_columns=signals)
    annotated["oi_extra"] = (pd.Series(range(len(annotated)), index=annotated.index) % 17) / 17.0
    full = fit_meta_confidence(
        annotated,
        signal_columns=signals,
        mode="interactions",
        minimum_train_rows=100,
        minimum_calibration_rows=50,
        outcome_available_before=boundary,
        extra_feature_columns=["oi_extra"],
    )
    ablated = fit_meta_confidence(
        annotated,
        signal_columns=signals,
        mode="interactions",
        minimum_train_rows=100,
        minimum_calibration_rows=50,
        outcome_available_before=boundary,
        extra_feature_columns=["oi_extra"],
        excluded_features=["oi_extra"],
    )
    assert "oi_extra" in full.feature_columns
    assert "oi_extra" not in ablated.feature_columns
    predicted = predict_meta_confidence(
        annotated.tail(20),
        ablated,
        signal_columns=signals,
        extra_feature_columns=["oi_extra"],
    )
    assert predicted.between(0.0, 1.0).all()
