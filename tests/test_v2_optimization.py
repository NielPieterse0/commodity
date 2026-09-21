from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from commodity.v2_optimization import (
    TrialLedger,
    V2OptimizationError,
    _phase2_ledger_for_monthly_score,
    bind_frozen_v1,
    build_issue425_target,
    build_trial_id,
    expand_search_axes,
    load_issue425_search_plan,
    load_v2_registry,
    prepare_issue425_features,
    score_monthly_path,
    select_issue425_candidate,
    validate_issue425_search_plan,
)


def _registry(tmp_path: Path) -> Path:
    payload = {
        "schema_version": 1,
        "registry_id": "test-v2",
        "evidence_boundary": {
            "allowed_for_search": ["development", "rolling_research_oos"],
            "prohibited_for_search": ["reserved_confirmation", "true_forward"],
            "v1_immutable": True,
        },
        "variables": {
            "target": {
                "horizon_sessions": {"type": "integer", "action": "optimize", "min": 1, "max": 20}
            },
            "model": {
                "model_id": {"type": "structural", "action": "screen_optimize_ablate", "candidates": ["naive", "ridge"]}
            },
        },
        "mandatory_interactions": ["target.horizon_sessions×model.model_id"],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_registry_fails_closed_on_protected_evidence(tmp_path: Path) -> None:
    registry = load_v2_registry(_registry(tmp_path))
    registry.assert_search_evidence("development")
    with pytest.raises(V2OptimizationError, match="prohibited"):
        registry.assert_search_evidence("reserved_confirmation")
    with pytest.raises(V2OptimizationError, match="not allowed"):
        registry.assert_search_evidence("unknown")


def test_search_axes_validate_values_and_record_interaction(tmp_path: Path) -> None:
    registry = load_v2_registry(_registry(tmp_path))
    configs = expand_search_axes(
        registry,
        {
            "target.horizon_sessions": [1, 5],
            "model.model_id": ["naive", "ridge"],
        },
        max_trials=10,
    )
    assert len(configs) == 4
    assert configs[0]["_interactions_covered"] == [
        "target.horizon_sessions×model.model_id"
    ]
    with pytest.raises(V2OptimizationError, match="outside"):
        expand_search_axes(registry, {"target.horizon_sessions": [21]}, max_trials=10)
    with pytest.raises(V2OptimizationError, match="candidate"):
        expand_search_axes(registry, {"model.model_id": ["xgboost"]}, max_trials=10)


def test_trial_id_is_deterministic_and_ledger_resumes(tmp_path: Path) -> None:
    config = {"model.model_id": "ridge", "target.horizon_sessions": 5}
    first = build_trial_id(config, seed=7, dataset_id="dev-v1", code_id="abc", evidence_class="development")
    second = build_trial_id(dict(reversed(list(config.items()))), seed=7, dataset_id="dev-v1", code_id="abc", evidence_class="development")
    assert first == second

    ledger = TrialLedger(tmp_path / "trials.jsonl")
    record = {"trial_id": first, "status": "complete", "score": {"net_return": 0.01}}
    assert ledger.append(record) is True
    assert ledger.append(record) is False
    assert ledger.completed_trial_ids() == {first}
    conflicting = {**record, "score": {"net_return": 0.02}}
    with pytest.raises(V2OptimizationError, match="conflicting"):
        ledger.append(conflicting)


def test_monthly_score_reports_economics_and_stability() -> None:
    index = pd.to_datetime([
        "2022-01-03", "2022-01-04", "2022-02-01", "2022-02-02"
    ], utc=True)
    path = pd.DataFrame(
        {
            "net_pnl_usd": [1000.0, -200.0, -500.0, 300.0],
            "transaction_cost_usd": [10.0, 10.0, 10.0, 10.0],
            "turnover": [1.0, 0.0, 2.0, 0.0],
            "gross_exposure_fraction": [1.0, 1.0, 1.0, 0.0],
            "net_exposure_fraction": [1.0, 1.0, -1.0, 0.0],
            "leverage": [1.0, 1.0, 1.0, 0.0],
            "position": [1.0, 1.0, -1.0, 0.0],
        },
        index=index,
    )
    score = score_monthly_path(path, starting_capital_usd=100_000.0)
    assert score["total_net_pnl_usd"] == pytest.approx(600.0)
    assert score["mean_monthly_net_return"] == pytest.approx(0.003)
    assert score["median_monthly_net_return"] == pytest.approx(0.003)
    assert score["worst_monthly_net_return"] == pytest.approx(-0.002)
    assert score["profitable_month_rate"] == pytest.approx(0.5)
    assert score["transaction_cost_usd"] == pytest.approx(40.0)
    assert score["trade_count"] == 3
    assert score["long_net_pnl_usd"] == pytest.approx(800.0)
    assert score["short_net_pnl_usd"] == pytest.approx(-500.0)
    assert score["flat_net_pnl_usd"] == pytest.approx(300.0)
    assert score["max_drawdown_fraction"] > 0.0


def test_phase2_ledger_adapter_preserves_values_on_datetime_index() -> None:
    ledger = pd.DataFrame(
        {
            "trade_date": ["2022-01-03", "2022-01-04"],
            "target_position": [1.0, -1.0],
            "net_pnl_usd": [125.0, -50.0],
            "transaction_cost_usd": [2.5, 3.5],
            "execution_side_count": [1.0, 2.0],
        }
    )

    normalized = _phase2_ledger_for_monthly_score(ledger)

    assert list(normalized["net_pnl_usd"]) == [125.0, -50.0]
    assert list(normalized["transaction_cost_usd"]) == [2.5, 3.5]
    assert list(normalized["turnover"]) == [1.0, 2.0]
    assert list(normalized["position"]) == [1.0, -1.0]
    assert normalized.index.equals(pd.DatetimeIndex(pd.to_datetime(ledger["trade_date"], utc=True)))
    assert normalized.notna().all().all()


def test_monthly_score_rejects_nonchronological_or_post_cutoff_path() -> None:
    path = pd.DataFrame(
        {
            "net_pnl_usd": [1.0, 1.0], "transaction_cost_usd": [0.0, 0.0],
            "turnover": [0.0, 0.0], "gross_exposure_fraction": [0.0, 0.0],
            "net_exposure_fraction": [0.0, 0.0], "leverage": [0.0, 0.0],
            "position": [0.0, 0.0],
        },
        index=pd.to_datetime(["2023-01-02", "2022-12-30"], utc=True),
    )
    with pytest.raises(V2OptimizationError, match="chronological"):
        score_monthly_path(path, starting_capital_usd=100_000.0)


def test_frozen_v1_binding_is_content_addressed(tmp_path: Path) -> None:
    payload = {
        "benchmark_id": "v1-frozen",
        "execution_boundary": {"v1_frozen_unchanged": True},
        "status": "complete",
    }
    path = tmp_path / "v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    binding = bind_frozen_v1(path)
    assert binding["benchmark_id"] == "v1-frozen"
    assert len(binding["sha256"]) == 64
    before = path.read_bytes()
    assert bind_frozen_v1(path) == binding
    assert path.read_bytes() == before

    payload["execution_boundary"]["v1_frozen_unchanged"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(V2OptimizationError, match="not frozen"):
        bind_frozen_v1(path)


def test_issue425_search_plan_covers_registered_axes() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = load_v2_registry(root / "config" / "v2_variable_registry.json")
    plan = load_issue425_search_plan(
        root
        / "research"
        / "programmes"
        / "004-v2-maximum-reproducible-one-month-return"
        / "issue425-search-plan-v1.json"
    )
    summary = validate_issue425_search_plan(registry, plan)
    assert summary["latest_allowed_trade_date"] == "2022-12-31"
    assert summary["axis_count"] >= 12
    assert summary["required_interactions"] == {
        "target.target_role×target.horizon_sessions",
        "model.model_id×data.feature_family_subset",
        "decision.entry_threshold_quantile×target.horizon_sessions",
    }
    assert plan["search_stages"][0]["axes"]["target.horizon_sessions"] == list(range(1, 21))


def _issue425_feature_fixture(rows: int = 320) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=rows, freq="D", tz="UTC")
    values = pd.Series(range(rows), dtype=float)
    return pd.DataFrame(
        {
            "trade_date": dates,
            "available_at": dates + pd.Timedelta(hours=23),
            "feature_ret_1": values / 10000.0,
            "feature_ret_5": values / 5000.0,
            "feature_ret_20": values / 2000.0,
            "feature_vol_5": 0.01 + values / 100000.0,
            "feature_vol_20": 0.02 + values / 100000.0,
            "feature_range_pct": 0.03 + values / 100000.0,
            "feature_ma_gap_5": values / 20000.0,
            "feature_ma_gap_20": values / 30000.0,
            "feature_selected_dte": 30.0 - (values % 20),
            "feature_roll_event": (values % 30 == 0).astype(float),
            "feature_season_sin": 0.0,
            "feature_season_cos": 1.0,
            "feature_curve_log_settle_m1": 1.0 + values / 10000.0,
            "feature_curve_spread_m1_m2": values / 1000.0,
        }
    )


def test_issue425_feature_transforms_are_pit_and_family_bounded() -> None:
    features = _issue425_feature_fixture()
    config = {
        "feature_family_subset": "market",
        "lookback_sessions": 60,
        "return_transform": "simple_return",
        "scaling": "zscore_rolling",
        "normalization_window_sessions": 20,
        "winsor_quantile": 0.01,
        "lag_sessions": 1,
        "rolling_stat_window_sessions": 5,
    }
    first, columns = prepare_issue425_features(features, config)
    mutated = features.copy()
    mutated.loc[mutated.index[-1], "feature_ret_1"] = 9.0
    second, second_columns = prepare_issue425_features(mutated, config)
    assert columns == second_columns
    assert columns
    assert all("curve" not in column for column in columns)
    common = first.index.intersection(second.index)
    prior = common[common < common.max()]
    pd.testing.assert_frame_equal(first.loc[prior, columns], second.loc[prior, columns])
    assert first[columns].notna().all().all()


def test_issue425_target_roles_have_explicit_economic_translation() -> None:
    moves = [0.01, -0.005, 0.02]
    returned = build_issue425_target(
        moves,
        role="return",
        aggregation="cumulative",
        round_trip_per_mmbtu=0.002,
    )
    assert returned["target_value"] == pytest.approx(0.025)
    assert returned["champion_eligible"] is True

    direction = build_issue425_target(
        moves,
        role="direction",
        aggregation="terminal",
        round_trip_per_mmbtu=0.002,
    )
    assert direction["target_value"] == 1.0
    assert direction["champion_eligible"] is True

    volatility = build_issue425_target(
        moves,
        role="volatility",
        aggregation="path_summary",
        round_trip_per_mmbtu=0.002,
    )
    assert volatility["target_value"] > 0.0
    assert volatility["champion_eligible"] is False
    assert volatility["economic_translation"] == "diagnostic_only_flat"


def test_issue425_selection_excludes_diagnostic_only_specialists() -> None:
    rows = [
        {
            "candidate_id": "volatility-flat",
            "champion_eligible": False,
            "complexity_rank": 0,
            "monthly_score": {
                "mean_monthly_net_return": 0.0,
                "max_drawdown_fraction": 0.0,
                "transaction_cost_usd": 0.0,
            },
        },
        {
            "candidate_id": "return-edge",
            "champion_eligible": True,
            "complexity_rank": 2,
            "monthly_score": {
                "mean_monthly_net_return": -0.001,
                "max_drawdown_fraction": 0.02,
                "transaction_cost_usd": 50.0,
            },
        },
    ]
    winner = select_issue425_candidate(rows)
    assert winner["candidate_id"] == "return-edge"
