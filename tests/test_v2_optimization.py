from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from commodity.v2_optimization import (
    TrialLedger,
    V2OptimizationError,
    _issue426_apply_confidence_weight,
    _issue426_apply_exposure_gate,
    _issue426_common_selection_blocks,
    _issue426_valid_inner_blocks,
    _phase2_ledger_for_monthly_score,
    _rank_issue426_rows,
    _search_issue426_outer,
    bind_frozen_v1,
    build_issue425_target,
    build_issue426_historical_source_gate,
    build_issue426_positioning_family_frame,
    build_issue426_source_gate,
    build_issue426_storage_family_frame,
    build_issue426_weather_family_frame,
    build_trial_id,
    expand_search_axes,
    inventory_issue426_historical_coverage,
    inventory_issue426_snapshot_coverage,
    load_issue425_search_plan,
    load_issue426_interaction_contract,
    load_issue426_optimization_plan,
    load_issue426_outer_matched_controls,
    load_issue426_search_plan,
    load_issue426_source_plan,
    load_issue426_weather_feature_contract,
    load_v2_registry,
    merge_issue426_pit_family,
    prepare_issue425_features,
    prepare_issue426_features,
    prepare_issue426_storage_weather_interaction_features,
    run_issue426_development_source_gate,
    score_monthly_path,
    select_issue425_candidate,
    validate_issue425_search_plan,
    validate_issue426_optimization_plan,
    validate_issue426_search_plan,
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


def test_issue426_search_plan_preserves_development_boundary() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = load_v2_registry(root / "config" / "v2_variable_registry.json")
    plan = load_issue426_search_plan(
        root
        / "research"
        / "programmes"
        / "004-v2-maximum-reproducible-one-month-return"
        / "issue426-search-plan-v1.json"
    )
    summary = validate_issue426_search_plan(registry, plan)
    assert summary["latest_allowed_trade_date"] == "2022-12-31"
    assert summary["families"] == {"storage", "weather", "power", "positioning"}
    assert "storage×weather×season×volatility" in summary["required_interactions"]
    assert plan["protected_evidence"] == [
        "reserved_confirmation",
        "true_forward",
        "prospective_paper",
        "saxo_sim",
        "saxo_live",
    ]


def test_issue426_pit_join_is_backward_only_and_staleness_bounded() -> None:
    market = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2022-01-03", "2022-01-04", "2022-01-10"], utc=True),
            "available_at": pd.to_datetime(["2022-01-03 23:00Z", "2022-01-04 23:00Z", "2022-01-10 23:00Z"]),
            "feature_ret_1": [0.01, 0.02, -0.01],
        }
    )
    family = pd.DataFrame(
        {
            "available_at": pd.to_datetime(["2022-01-03 12:00Z", "2022-01-05 12:00Z"]),
            "storage_level": [100.0, 999.0],
        }
    )
    merged = merge_issue426_pit_family(
        market,
        family,
        family="storage",
        value_columns=("storage_level",),
        max_staleness=pd.Timedelta(days=3),
        latest_allowed_trade_date="2022-12-31",
    )
    assert merged.loc[0, "feature_storage_storage_level"] == 100.0
    assert merged.loc[1, "feature_storage_storage_level"] == 100.0
    assert pd.isna(merged.loc[2, "feature_storage_storage_level"])


def test_issue426_feature_transform_keeps_market_control_and_family_increment() -> None:
    features = _issue425_feature_fixture()
    features["feature_storage_level"] = pd.Series(range(len(features)), dtype=float) / 100.0
    config = {
        "feature_family_subset": "storage",
        "lookback_sessions": 60,
        "return_transform": "log_return",
        "scaling": "none",
        "normalization_window_sessions": 20,
        "winsor_quantile": 0.0,
        "lag_sessions": 1,
        "rolling_stat_window_sessions": 5,
    }
    transformed, columns = prepare_issue426_features(features, config)
    assert transformed[columns].notna().all().all()
    assert any(column.startswith("feature_storage_") for column in columns)
    assert any(column.startswith("feature_ret_") for column in columns)
    assert all("curve" not in column for column in columns)


def test_issue426_source_gate_holds_sources_whose_pit_support_starts_after_cutoff() -> None:
    data_cfg = {
        "sources": {
            "eia_storage": {"availability_policy": {"research_pit_allowed": True, "exception_registry_coverage_start": "2024-08-01"}},
            "weather": {"archive_start": "2024-03-14", "availability_policy": {"research_pit_allowed_with_immutable_issued_runs": True}},
            "nyiso_load_forecast": {"v1_required_window": "2024-08-13 through 2026-08-12", "availability_policy": {"research_pit_allowed": True}},
            "cftc_cot": {"availability_policy": {"research_pit_allowed": True, "supported_report_date_start": "2024-01-01"}},
        }
    }
    coverage = {
        family: {"snapshot_count": 1, "earliest_preserved": "2024-01-01"}
        for family in ("storage", "weather", "power", "positioning")
    }
    report = build_issue426_source_gate(
        data_cfg,
        coverage,
        latest_allowed_trade_date="2022-12-31",
    )
    assert report["scorable_families"] == []
    assert {item["family"] for item in report["held_families"]} == {
        "storage", "weather", "power", "positioning"
    }
    assert all(item["disposition"] == "HOLD" for item in report["held_families"])


def test_issue426_snapshot_inventory_reports_preserved_coverage(tmp_path: Path) -> None:
    fixtures = {
        "eia_wngsr/2024-08-13_2026-08-12": "2024-08-13",
        "open_meteo_v1/20240813T0000Z": "2024-08-13",
        "nyiso_p7/202408-p7": "2024-08-01",
        "cftc_cot/2024-disaggregated-futures-only": "2024-01-01",
    }
    for relative in fixtures:
        directory = tmp_path / relative
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text("{}", encoding="utf-8")
    coverage = inventory_issue426_snapshot_coverage(tmp_path)
    assert coverage["storage"]["earliest_preserved"] == "2024-08-13"
    assert coverage["weather"]["earliest_preserved"] == "2024-08-13"
    assert coverage["power"]["earliest_preserved"] == "2024-08-01"
    assert coverage["positioning"]["earliest_preserved"] == "2024-01-01"
    assert all(item["snapshot_count"] == 1 for item in coverage.values())


def test_issue426_source_gate_result_binds_market_control_without_scoring(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_cfg = {
        "sources": {
            "eia_storage": {"availability_policy": {"research_pit_allowed": True, "exception_registry_coverage_start": "2024-08-01"}},
            "weather": {"archive_start": "2024-03-14", "availability_policy": {"research_pit_allowed_with_immutable_issued_runs": True}},
            "nyiso_load_forecast": {"v1_required_window": "2024-08-13 through 2026-08-12", "availability_policy": {"research_pit_allowed": True}},
            "cftc_cot": {"availability_policy": {"research_pit_allowed": True, "supported_report_date_start": "2024-01-01"}},
        }
    }
    data_path = tmp_path / "data_sources.json"
    data_path.write_text(json.dumps(data_cfg), encoding="utf-8")
    issue425 = {
        "issue": 425,
        "evidence_class": "development",
        "protected_confirmation_accessed": False,
        "true_forward_accessed": False,
        "saxo_sim_accessed": False,
        "saxo_live_accessed": False,
        "nested_selection_score": {"mean_monthly_net_return": 0.001, "max_drawdown_fraction": 0.02},
        "latest_preregistered_handoff_config": {"data.feature_family_subset": "market"},
    }
    issue425_path = tmp_path / "issue425.json"
    issue425_path.write_text(json.dumps(issue425), encoding="utf-8")
    for relative in (
        "eia_wngsr/2024-08-13_2026-08-12",
        "open_meteo_v1/20240813T0000Z",
        "nyiso_p7/202408-p7",
        "cftc_cot/2024-disaggregated-futures-only",
    ):
        directory = tmp_path / "snapshots" / relative
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text("{}", encoding="utf-8")
    result = run_issue426_development_source_gate(
        registry_path=root / "config" / "v2_variable_registry.json",
        search_plan_path=root / "research" / "programmes" / "004-v2-maximum-reproducible-one-month-return" / "issue426-search-plan-v1.json",
        data_sources_path=data_path,
        issue425_result_path=issue425_path,
        snapshot_root=tmp_path / "snapshots",
    )
    assert result["status"] == "complete_development_only_source_gated"
    assert result["trial_count"] == 0
    assert result["source_gate_attempt_count"] == 4
    assert result["market_only_control"]["nested_selection_score"]["mean_monthly_net_return"] == 0.001
    assert result["protected_confirmation_accessed"] is False


def test_issue426_source_plan_registers_historical_promotions_before_scoring() -> None:
    root = Path(__file__).resolve().parents[1]
    plan = load_issue426_source_plan(
        root
        / "research"
        / "programmes"
        / "004-v2-maximum-reproducible-one-month-return"
        / "issue426-source-plan-v2.json"
    )
    assert plan["status"] == "registered_before_historical_family_scoring"
    assert set(plan["families"]) == {"storage", "weather", "power", "positioning"}
    assert plan["families"]["storage"]["disposition"] == "SCORE_IF_INTEGRITY_VERIFIED"
    assert plan["families"]["positioning"]["disposition"] == "SCORE_IF_INTEGRITY_VERIFIED"
    assert plan["families"]["weather"]["expected_issue_days"] == 2908
    assert plan["families"]["power"]["disposition"] == "HOLD"
    assert plan["protected_evidence_accessed"] is False


def test_issue426_historical_gate_promotes_only_verified_ready_families() -> None:
    data_cfg = {"sources": {
        "eia_storage": {"availability_policy": {"research_pit_allowed": True}},
        "weather": {"availability_policy": {"research_pit_allowed_with_immutable_issued_runs": True}},
        "nyiso_load_forecast": {"availability_policy": {"research_pit_allowed": True}},
        "cftc_cot": {"availability_policy": {"research_pit_allowed": True}},
    }}
    source_plan = {"families": {
        "storage": {"disposition": "SCORE_IF_INTEGRITY_VERIFIED", "support_start": "2015-06-19"},
        "weather": {"disposition": "SCORE_IF_COMPLETE_AND_INTEGRITY_VERIFIED", "support_start": "2015-01-15"},
        "power": {"disposition": "HOLD", "support_start": "2011-01-01", "hold_reason": "publication_timing_unverified"},
        "positioning": {"disposition": "SCORE_IF_INTEGRITY_VERIFIED", "support_start": "2010-01-05"},
    }}
    coverage = {
        "storage": {"integrity_verified": True, "snapshot_count": 394, "earliest_preserved": "2015-06-19"},
        "weather": {"integrity_verified": True, "complete": False, "snapshot_count": 100, "earliest_preserved": "2015-01-15"},
        "power": {"integrity_verified": True, "snapshot_count": 12, "earliest_preserved": "2011-01-01"},
        "positioning": {"integrity_verified": True, "snapshot_count": 678, "earliest_preserved": "2010-01-05"},
    }
    report = build_issue426_historical_source_gate(
        data_cfg, source_plan, coverage, latest_allowed_trade_date="2022-12-31"
    )
    assert report["scorable_families"] == ["storage", "positioning"]
    held = {item["family"]: item for item in report["held_families"]}
    assert "historical_weather_coverage_incomplete" in held["weather"]["reasons"]
    assert "publication_timing_unverified" in held["power"]["reasons"]


def test_issue426_historical_inventory_verifies_preserved_normalized_hashes(tmp_path: Path) -> None:
    storage_file = tmp_path / "eia_wngsr" / "storage.csv"
    positioning_file = tmp_path / "cftc" / "positioning.csv"
    storage_file.parent.mkdir(parents=True)
    positioning_file.parent.mkdir(parents=True)
    pd.DataFrame({"observed_for": ["2020-01-03", "2020-01-10", "2020-01-17"]}).to_csv(
        storage_file, index=False
    )
    pd.DataFrame({"observed_for": ["2020-01-07", "2020-01-14", "2020-01-21"]}).to_csv(
        positioning_file, index=False
    )
    storage_manifest = {
        "source_id": "storage-source",
        "normalized_file": "storage.csv",
        "normalized_sha256": hashlib.sha256(storage_file.read_bytes()).hexdigest(),
        "rows": 3,
        "first_observed_for": "2020-01-03T00:00:00+00:00",
        "last_observed_for": "2020-01-17T00:00:00+00:00",
        "availability_basis": "storage-test-basis",
    }
    positioning_manifest = {
        "source_id": "positioning-source",
        "normalized_file": "positioning.csv",
        "normalized_sha256": hashlib.sha256(positioning_file.read_bytes()).hexdigest(),
        "rows": 3,
        "first_observed_for": "2020-01-07T00:00:00+00:00",
        "last_observed_for": "2020-01-21T00:00:00+00:00",
        "availability_basis": "positioning-test-basis",
    }
    (storage_file.parent / "manifest.json").write_text(json.dumps(storage_manifest), encoding="utf-8")
    (positioning_file.parent / "manifest.json").write_text(json.dumps(positioning_manifest), encoding="utf-8")
    plan = {"families": {
        "storage": {"source_id": "storage-source", "manifest": "eia_wngsr/manifest.json", "normalized_file": "eia_wngsr/storage.csv", "support_start": "2020-01-03", "support_end": "2020-01-17", "availability_basis": "storage-test-basis"},
        "positioning": {"source_id": "positioning-source", "manifest": "cftc/manifest.json", "normalized_file": "cftc/positioning.csv", "support_start": "2020-01-07", "support_end": "2020-01-21", "availability_basis": "positioning-test-basis"},
        "weather": {"source_id": "weather-source", "manifest_glob": "weather/*/manifest.json", "support_start": "2015-01-15", "support_end": "2015-01-15", "expected_issue_days": 1},
        "power": {"source_id": "power-source", "manifest": "pjm/manifest.json", "support_start": "2011-01-01", "support_end": "2022-12-31"},
    }}
    coverage = inventory_issue426_historical_coverage(tmp_path, plan)
    assert coverage["storage"]["integrity_verified"] is True
    assert coverage["storage"]["snapshot_count"] == 3
    assert coverage["positioning"]["integrity_verified"] is True
    assert coverage["positioning"]["snapshot_count"] == 3
    assert coverage["weather"]["integrity_verified"] is False
    assert coverage["power"]["integrity_verified"] is False

    pd.DataFrame({"observed_for": ["2020-01-03", "2020-01-17"]}).to_csv(storage_file, index=False)
    storage_manifest["normalized_sha256"] = hashlib.sha256(storage_file.read_bytes()).hexdigest()
    storage_manifest["rows"] = 2
    (storage_file.parent / "manifest.json").write_text(json.dumps(storage_manifest), encoding="utf-8")
    broken = inventory_issue426_historical_coverage(tmp_path, plan)
    assert broken["storage"]["integrity_verified"] is False


def test_issue426_storage_family_frame_uses_conservative_release_stream(tmp_path: Path) -> None:
    path = tmp_path / "storage.csv"
    pd.DataFrame({
        "observed_for": ["2020-01-03", "2020-01-10", "2020-01-17"],
        "available_at": ["2020-01-14T04:59:00Z", "2020-01-21T04:59:00Z", "2020-01-28T04:59:00Z"],
        "storage_lower48_bcf": [3000, 2950, 2900],
        "storage_east_bcf": [600, 590, 580],
        "storage_midwest_bcf": [700, 690, 680],
        "storage_mountain_bcf": [200, 195, 190],
        "storage_pacific_bcf": [300, 295, 290],
        "storage_south_central_bcf": [1200, 1180, 1160],
        "release_note": [None, "Reclassifications from base gas to working gas resulted in increased working gas stocks of approximately 8 Bcf. The implied flow for the week is a decrease of 42 Bcf.", None],
    }).to_csv(path, index=False)
    frame = build_issue426_storage_family_frame(path)
    assert frame["available_at"].is_monotonic_increasing
    assert frame.loc[1, "change_bcf"] == -50.0
    assert frame.loc[1, "reclassification_bcf"] == 8.0
    assert frame.loc[1, "implied_flow_bcf"] == -42.0


def test_issue426_positioning_family_frame_is_pit_and_scaled_by_open_interest(tmp_path: Path) -> None:
    path = tmp_path / "positioning.csv"
    rows = 60
    pd.DataFrame({
        "observed_for": pd.date_range("2020-01-07", periods=rows, freq="7D", tz="UTC"),
        "available_at": pd.date_range("2020-01-15", periods=rows, freq="7D", tz="UTC"),
        "open_interest": [1000 + i for i in range(rows)],
        "managed_money_net": [100 + i for i in range(rows)],
        "producer_merchant_net": [-200 - i for i in range(rows)],
        "swap_dealer_net": [50 + 2 * i for i in range(rows)],
    }).to_csv(path, index=False)
    frame = build_issue426_positioning_family_frame(path)
    assert frame["available_at"].is_monotonic_increasing
    assert frame.loc[1, "managed_money_change"] == 1.0
    assert frame.loc[0, "managed_money_pct_oi"] == pytest.approx(0.1)
    assert frame["managed_money_zscore_52"].iloc[-1] > 0.0


def test_issue426_feature_transform_selects_only_registered_representation() -> None:
    features = _issue425_feature_fixture()
    features["feature_storage_lower48_bcf"] = pd.Series(range(len(features)), dtype=float)
    features["feature_storage_change_bcf"] = pd.Series(range(len(features)), dtype=float) / 10.0
    config = {
        "feature_family_subset": "storage",
        "representation": "change",
        "lookback_sessions": 60,
        "return_transform": "log_return",
        "scaling": "none",
        "normalization_window_sessions": 20,
        "winsor_quantile": 0.0,
        "lag_sessions": 1,
        "rolling_stat_window_sessions": 5,
    }
    _, columns = prepare_issue426_features(features, config)
    family = [column for column in columns if column.startswith("feature_storage_")]
    assert family
    assert all("change_bcf" in column for column in family)


def test_issue426_optimization_plan_uses_outer_matched_issue425_controls() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = load_v2_registry(root / "config" / "v2_variable_registry.json")
    plan = load_issue426_optimization_plan(
        root
        / "research"
        / "programmes"
        / "004-v2-maximum-reproducible-one-month-return"
        / "issue426-optimization-plan-v3.json"
    )
    summary = validate_issue426_optimization_plan(registry, plan)
    assert summary["latest_allowed_trade_date"] == "2022-12-31"
    assert plan["base_configuration"] == (
        "issue425-result-v1.nested_outer[].search.selected_config matched by outer_block_id"
    )
    assert plan["matched_control"] == (
        "same_outer_matched_issue425_configuration_without_added_family"
    )
    assert summary["stage_ids"] == [
        "representation_role",
        "lag_and_rolling_window",
        "scaling_and_normalization",
        "lookback_and_winsor",
        "registered_interactions",
    ]
    assert plan["roles"]["confidence"] == (
        "training_only_family_strength_empirical_percentile_scales_market_forecast_strength_before_cost_gate"
    )
    assert plan["roles"]["sizing"].startswith("HOLD_UNIDENTIFIABLE")
    assert plan["roles"]["risk_modifier"].startswith("HOLD_UNIDENTIFIABLE")
    assert plan["held_role_policy"]["search_budget_consumed"] is False


def test_issue426_transform_preserves_outer_matched_market_family() -> None:
    features = _issue425_feature_fixture()
    features["feature_storage_change_bcf"] = pd.Series(
        range(len(features)), dtype=float
    ) / 10.0
    config = {
        "feature_family_subset": "storage",
        "market_control_family": "market_structure",
        "representation": "change",
        "lookback_sessions": 60,
        "return_transform": "log_return",
        "scaling": "none",
        "normalization_window_sessions": 20,
        "winsor_quantile": 0.0,
        "lag_sessions": 1,
        "rolling_stat_window_sessions": 5,
    }
    _, columns = prepare_issue426_features(features, config)
    assert any(column.startswith("feature_curve_") for column in columns)
    assert any(column.startswith("feature_storage_") for column in columns)
    assert "feature_ret_1" not in columns


def test_issue426_outer_matched_controls_use_issue425_nested_outer_configs() -> None:
    root = Path(__file__).resolve().parents[1]
    controls = load_issue426_outer_matched_controls(
        root
        / "research"
        / "programmes"
        / "004-v2-maximum-reproducible-one-month-return"
        / "issue425-result-v1.json"
    )
    assert list(controls) == [
        "outer-2017-2018",
        "outer-2019-2020",
        "outer-2021-2022",
    ]
    for block_id, control in controls.items():
        assert control["outer_block_id"] == block_id
        assert control["config"]["data.feature_family_subset"] in {
            "market", "market_structure", "calendar_seasonality"
        }
        assert control["monthly_score"]["month_count"] > 0


def test_issue426_regime_role_adds_only_pit_market_interactions() -> None:
    features = _issue425_feature_fixture()
    features["feature_storage_change_bcf"] = pd.Series(
        range(len(features)), dtype=float
    ) / 10.0
    config = {
        "feature_family_subset": "storage",
        "market_control_family": "market",
        "representation": "change",
        "role": "regime",
        "lookback_sessions": 60,
        "return_transform": "log_return",
        "scaling": "none",
        "normalization_window_sessions": 20,
        "winsor_quantile": 0.0,
        "lag_sessions": 1,
        "rolling_stat_window_sessions": 5,
    }
    _, columns = prepare_issue426_features(features, config)
    family = [column for column in columns if column.startswith("feature_storage_")]
    assert any("__x_season_sin" in column for column in family)
    assert any("__x_season_cos" in column for column in family)
    assert any("__x_vol20" in column for column in family)


def test_issue426_exposure_gate_uses_training_only_quantile() -> None:
    start = pd.Timestamp("2020-01-01", tz="UTC")
    origins = pd.DataFrame({
        "fill_timestamp": pd.date_range("2019-12-27", periods=6, freq="D", tz="UTC"),
        "target_end_timestamp": pd.to_datetime(
            ["2019-12-28", "2019-12-29", "2019-12-30", "2020-01-02", "2020-01-03", "2020-01-04"],
            utc=True,
        ),
        "feature_storage_change_bcf": [1.0, 2.0, 100.0, 1.0, 50.0, 200.0],
    })
    forecasts = pd.DataFrame({
        "fill_timestamp": origins.loc[3:, "fill_timestamp"].reset_index(drop=True),
        "predicted_path_move_per_mmbtu": [1.0, 1.0, 1.0],
        "predicted_gross_pnl_usd": [1000.0, 1000.0, 1000.0],
    })
    gated, diagnostics = _issue426_apply_exposure_gate(
        origins,
        forecasts,
        family="storage",
        quantile=0.5,
        training_window="expanding",
        start_timestamp=start,
    )
    assert diagnostics["gate_threshold"] == 2.0
    assert diagnostics["gate_active_rate"] == pytest.approx(2.0 / 3.0)
    assert gated["predicted_path_move_per_mmbtu"].tolist() == [0.0, 1.0, 1.0]


def test_issue426_confidence_weight_uses_training_only_strength_percentile() -> None:
    start = pd.Timestamp("2020-01-01", tz="UTC")
    origins = pd.DataFrame({
        "fill_timestamp": pd.date_range("2019-12-27", periods=6, freq="D", tz="UTC"),
        "target_end_timestamp": pd.to_datetime(
            ["2019-12-28", "2019-12-29", "2019-12-30", "2020-01-02", "2020-01-03", "2020-01-04"],
            utc=True,
        ),
        "feature_weather_dispersion": [1.0, 2.0, 100.0, 1.0, 50.0, 200.0],
    })
    forecasts = pd.DataFrame({
        "fill_timestamp": origins.loc[3:, "fill_timestamp"].reset_index(drop=True),
        "predicted_path_move_per_mmbtu": [1.0, 1.0, 1.0],
        "predicted_gross_pnl_usd": [900.0, 900.0, 900.0],
    })
    weighted, diagnostics = _issue426_apply_confidence_weight(
        origins,
        forecasts,
        family="weather",
        training_window="expanding",
        start_timestamp=start,
    )
    assert weighted["predicted_gross_pnl_usd"].tolist() == pytest.approx([300.0, 600.0, 900.0])
    assert diagnostics["confidence_training_rows"] == 3
    assert diagnostics["confidence_weight_mean"] == pytest.approx(2.0 / 3.0)


def test_issue426_ranking_prefers_incremental_matched_ablation_value() -> None:
    rows = [
        {"candidate_id": "a", "status": "complete", "ablation": {"mean_monthly_net_return_delta": 0.01},
         "monthly_score": {"max_drawdown_fraction": 0.01, "transaction_cost_usd": 10.0}, "complexity_rank": 2},
        {"candidate_id": "b", "status": "complete", "ablation": {"mean_monthly_net_return_delta": 0.02},
         "monthly_score": {"max_drawdown_fraction": 0.02, "transaction_cost_usd": 20.0}, "complexity_rank": 3},
    ]
    ranked = _rank_issue426_rows(rows)
    assert [row["candidate_id"] for row in ranked] == ["b", "a"]


def test_issue426_inner_blocks_require_prior_family_training_support() -> None:
    dates = pd.date_range("2014-01-01", "2020-12-31", freq="D", tz="UTC")
    features = pd.DataFrame({
        "trade_date": dates,
        "feature_storage_available_at": pd.Series(pd.NaT, index=range(len(dates)), dtype="datetime64[ns, UTC]"),
    })
    supported = dates >= pd.Timestamp("2015-07-01", tz="UTC")
    features.loc[supported, "feature_storage_available_at"] = dates[supported]
    blocks = [
        {"id": "2015", "start": "2015-01-01", "end": "2015-12-31"},
        {"id": "2016", "start": "2016-01-01", "end": "2016-12-31"},
        {"id": "2017", "start": "2017-01-01", "end": "2017-12-31"},
        {"id": "2018", "start": "2018-01-01", "end": "2018-12-31"},
    ]
    valid = _issue426_valid_inner_blocks(
        features,
        family="storage",
        inner_blocks=blocks,
        outer_start="2019-01-01",
        minimum_training_rows=504,
    )
    assert [block["id"] for block in valid] == ["2017", "2018"]


def test_issue426_common_selection_blocks_use_representation_intersection() -> None:
    blocks = [
        {"id": "inner-2018", "start": "2018-01-01", "end": "2018-12-31"},
        {"id": "inner-2019", "start": "2019-01-01", "end": "2019-12-31"},
        {"id": "inner-2020", "start": "2020-01-01", "end": "2020-12-31"},
    ]
    summary = _issue426_common_selection_blocks(
        blocks,
        {
            "level": ["inner-2018", "inner-2019", "inner-2020"],
            "seasonal_deviation": ["inner-2019", "inner-2020"],
            "release_surprise": [],
        },
    )
    assert summary["available_representations"] == ["level", "seasonal_deviation"]
    assert summary["held_representations"] == ["release_surprise"]
    assert [block["id"] for block in summary["common_blocks"]] == ["inner-2019", "inner-2020"]


def test_issue426_search_respects_common_representation_override() -> None:
    search_plan = {
        "families": [
            {
                "family": "storage",
                "representations": ["level", "change"],
                "roles": ["direct", "sizing", "risk_modifier"],
            }
        ],
        "required_interactions": [],
    }
    optimization_plan = {
        "stages": [
            {"id": "representation_role", "gate_quantiles": [0.25, 0.5, 0.75]},
            {
                "id": "lag_and_rolling_window",
                "axes": {
                    "transforms.lag_sessions": [1],
                    "transforms.rolling_stat_window_sessions": [5],
                },
            },
            {
                "id": "scaling_and_normalization",
                "axes": {
                    "transforms.scaling": ["none"],
                    "transforms.normalization_window_sessions": [20],
                },
            },
            {
                "id": "lookback_and_winsor",
                "axes": {
                    "data.lookback_sessions": [60],
                    "transforms.winsor_quantile": [0.0],
                },
            },
            {"id": "registered_interactions", "axes": []},
        ]
    }
    seen_representations: set[str] = set()
    seen_roles: set[str] = set()

    def evaluator(stage, outer_id, blocks, config):
        del stage, outer_id, blocks
        representation = str(config["issue426.representation"])
        seen_representations.add(representation)
        seen_roles.add(str(config["issue426.role"]))
        return {
            "candidate_id": representation,
            "status": "complete",
            "config": dict(config),
            "ablation": {"mean_monthly_net_return_delta": 0.01},
            "monthly_score": {
                "max_drawdown_fraction": 0.01,
                "transaction_cost_usd": 10.0,
            },
            "complexity_rank": 1,
        }

    result = _search_issue426_outer(
        search_plan,
        optimization_plan,
        family="storage",
        outer_block={"id": "outer", "start": "2021-01-01", "end": "2022-12-31"},
        base_config={},
        inner_blocks=[{"id": "inner", "start": "2019-01-01", "end": "2020-12-31"}],
        evaluator=evaluator,
        representations_override=["level"],
    )
    assert seen_representations == {"level"}
    assert seen_roles == {"direct"}
    assert result["selected_config"]["issue426.representation"] == "level"
    assert [item["role"] for item in result["held_roles"]] == ["sizing", "risk_modifier"]
    assert all(item["search_budget_consumed"] is False for item in result["held_roles"])


def test_issue426_weather_builder_uses_issued_runs_and_prior_only_history(tmp_path: Path) -> None:
    root = tmp_path / "weather"
    anchors = [
        "midwest_chicago",
        "northeast_new_york",
        "southeast_atlanta",
        "south_central_houston",
    ]
    leads = list(range(24, 169, 3))
    first = pd.Timestamp("2020-01-01", tz="UTC")
    for day_index in range(12):
        issued = first + pd.Timedelta(days=day_index)
        directory = root / str(issued.year) / issued.strftime("%Y%m%d")
        directory.mkdir(parents=True)
        rows = []
        for anchor_index, anchor_id in enumerate(anchors):
            for lead in leads:
                valid = issued + pd.Timedelta(hours=lead)
                temperature = (
                    5.0
                    + float(valid.dayofyear) / 10.0
                    + float(anchor_index)
                    + 0.1 * day_index
                )
                rows.append(
                    {
                        "issued_at": issued.isoformat(),
                        "forecast_valid_at": valid.isoformat(),
                        "lead_hours": lead,
                        "anchor_id": anchor_id,
                        "temperature_c": temperature,
                    }
                )
        csv_path = directory / "anchor_temperature.csv"
        pd.DataFrame(rows).to_csv(csv_path, index=False)
        csv_sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        manifest = {
            "schema_version": 1,
            "source_id": "ncar_gdex_d084001_gfs_0p25_issued_00utc",
            "issue_date": issued.date().isoformat(),
            "requested_forecast_lead_hours": leads,
            "forecast_lead_hours": leads,
            "files": {
                "anchor_temperature.csv": {
                    "sha256": csv_sha,
                    "bytes": csv_path.stat().st_size,
                }
            },
        }
        (directory / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    frame = build_issue426_weather_family_frame(root)
    assert len(frame) == 12
    assert frame.loc[0, "available_at"] == first + pd.Timedelta(minutes=370)
    assert pd.isna(frame.loc[0, "revision_temp_mean_c"])
    assert frame.loc[1, "revision_temp_mean_c"] == pytest.approx(0.1)
    assert frame.loc[1, "revision_hdd65_mean_c"] == pytest.approx(-0.1)
    assert frame.loc[1, "temp_seasonal_anomaly_c"] > 0.0
    assert frame.loc[11, "revision_error_proxy_mae_30d_c"] == pytest.approx(0.1)
    assert frame["lead_coverage_fraction"].eq(1.0).all()
    assert frame["near_temp_mean_c"].notna().all()
    assert frame["far_temp_mean_c"].notna().all()


def test_issue426_weather_builder_rejects_undeclared_archive_omission(tmp_path: Path) -> None:
    root = tmp_path / "weather"
    directory = root / "2020" / "20200101"
    directory.mkdir(parents=True)
    anchors = [
        "midwest_chicago",
        "northeast_new_york",
        "southeast_atlanta",
        "south_central_houston",
    ]
    requested = list(range(24, 169, 3))
    actual = requested[:-1]
    issued = pd.Timestamp("2020-01-01", tz="UTC")
    rows = [
        {
            "issued_at": issued.isoformat(),
            "forecast_valid_at": (issued + pd.Timedelta(hours=lead)).isoformat(),
            "lead_hours": lead,
            "anchor_id": anchor,
            "temperature_c": 10.0,
        }
        for anchor in anchors
        for lead in actual
    ]
    csv_path = directory / "anchor_temperature.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    manifest = {
        "source_id": "ncar_gdex_d084001_gfs_0p25_issued_00utc",
        "issue_date": "2020-01-01",
        "requested_forecast_lead_hours": requested,
        "forecast_lead_hours": actual,
        "archive_missing_leads": [],
        "files": {
            "anchor_temperature.csv": {
                "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest()
            }
        },
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(V2OptimizationError, match="archive omissions are not exactly declared"):
        build_issue426_weather_family_frame(root)

    manifest["archive_missing_leads"] = [
        {"lead_hours": requested[-1], "reason": "transient request error"}
    ]
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(V2OptimizationError, match="archive omission reason is invalid"):
        build_issue426_weather_family_frame(root)

    manifest["archive_missing_leads"] = [
        {
            "lead_hours": requested[-1],
            "reason": "required 2m temperature variable absent from archived lead",
        }
    ]
    manifest["issue_date"] = "2020-01-02"
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(V2OptimizationError, match="manifest path does not match issue date"):
        build_issue426_weather_family_frame(root)

    manifest["issue_date"] = "2020-01-01"
    shifted_issue = issued + pd.Timedelta(hours=6)
    shifted_rows = [
        {
            **row,
            "issued_at": shifted_issue.isoformat(),
            "forecast_valid_at": (
                shifted_issue + pd.Timedelta(hours=int(row["lead_hours"]))
            ).isoformat(),
        }
        for row in rows
    ]
    pd.DataFrame(shifted_rows).to_csv(csv_path, index=False)
    manifest["files"]["anchor_temperature.csv"]["sha256"] = hashlib.sha256(
        csv_path.read_bytes()
    ).hexdigest()
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(V2OptimizationError, match="exact 00 UTC issue cycle"):
        build_issue426_weather_family_frame(root)


def test_issue426_weather_feature_contract_is_preregistered_and_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    contract = load_issue426_weather_feature_contract(
        root
        / "research"
        / "programmes"
        / "004-v2-maximum-reproducible-one-month-return"
        / "issue426-weather-feature-contract-v1.json"
    )
    assert contract["status"] == "preregistered_before_weather_scoring"
    assert contract["availability_delay_minutes"] == 370
    assert contract["archive_omission_rule"]["coverage_diagnostic"] == (
        "lead_coverage_fraction_not_scored"
    )
    assert set(contract["archive_omission_rule"]["allowed_archive_omission_reasons"]) == {
        "required 2m temperature variable absent from archived lead",
        "archived forecast lead file absent",
    }
    assert contract["representations"]["dispersion"]["features"] == [
        "temp_dispersion_c",
        "anchor_temp_dispersion_c",
    ]
    assert contract["representations"]["forecast_error_history"]["semantic_boundary"] == (
        "revision_error_proxy_not_observed_realized_forecast_error"
    )


def test_issue426_combined_interaction_contract_is_preregistered_and_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    contract = load_issue426_interaction_contract(
        root
        / "research"
        / "programmes"
        / "004-v2-maximum-reproducible-one-month-return"
        / "issue426-interaction-contract-v1.json"
    )
    assert contract["status"] == "preregistered_before_combined_interaction_scoring"
    assert contract["required_interaction"] == "storage×weather×season×volatility"
    assert contract["transform_basis_candidates"] == [
        "storage_selected_transform",
        "weather_selected_transform",
    ]
    assert contract["lower_order_family_main_effects_in_combined_candidate"] is False


def test_issue426_combined_interaction_is_pure_four_way_market_increment() -> None:
    features = _issue425_feature_fixture()
    values = pd.Series(range(len(features)), dtype=float)
    features["feature_storage_lower48_bcf"] = 1000.0 + values
    features["feature_weather_temp_mean_c"] = 10.0 + values / 100.0
    config = {
        "data.feature_family_subset": "market",
        "data.lookback_sessions": 60,
        "transforms.return_transform": "log_return",
        "transforms.scaling": "none",
        "transforms.normalization_window_sessions": 20,
        "transforms.winsor_quantile": 0.0,
        "transforms.lag_sessions": 1,
        "transforms.rolling_stat_window_sessions": 5,
    }
    transformed, columns = prepare_issue426_storage_weather_interaction_features(
        features,
        config,
        storage_representation="level",
        weather_representation="level",
    )
    interaction_columns = [
        column for column in columns if column.startswith("feature_issue426_combined_")
    ]
    assert transformed[columns].notna().all().all()
    assert interaction_columns
    assert any("__x_season_sin__x_vol20" in column for column in interaction_columns)
    assert any("__x_season_cos__x_vol20" in column for column in interaction_columns)
    assert not any(column.startswith("feature_storage_") for column in columns)
    assert not any(column.startswith("feature_weather_") for column in columns)
    assert any(column.startswith("feature_ret_") for column in columns)


def test_issue426_weather_inventory_rejects_undeclared_archive_omission(tmp_path: Path) -> None:
    directory = tmp_path / "weather" / "gfs_rda_025" / "2020" / "20200101"
    directory.mkdir(parents=True)
    payload = directory / "anchor_temperature.csv"
    payload.write_text("x\n1\n", encoding="utf-8")
    requested = list(range(24, 169, 3))
    actual = requested[:-1]
    manifest = {
        "source_id": "ncar_gdex_d084001_gfs_0p25_issued_00utc",
        "issue_date": "2020-01-01",
        "cycle_utc_hour": 0,
        "requested_forecast_lead_hours": requested,
        "forecast_lead_hours": actual,
        "archive_missing_leads": [],
        "anchor_ids": [
            "midwest_chicago",
            "northeast_new_york",
            "southeast_atlanta",
            "south_central_houston",
        ],
        "record_count": len(actual) * 4,
        "payload_count": len(actual),
        "files": {
            payload.name: {
                "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
                "bytes": payload.stat().st_size,
            }
        },
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    repo = Path(__file__).resolve().parents[1]
    source_plan = load_issue426_source_plan(
        repo
        / "research"
        / "programmes"
        / "004-v2-maximum-reproducible-one-month-return"
        / "issue426-source-plan-v2.json"
    )
    coverage = inventory_issue426_historical_coverage(tmp_path, source_plan)
    assert coverage["weather"]["snapshot_count"] == 1
    assert coverage["weather"]["integrity_verified"] is False
    assert coverage["weather"]["complete"] is False
