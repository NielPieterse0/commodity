from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/research/run_issue465_block1_controller_v3.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("issue465_v3_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v3_prereg_is_frozen_and_block1_only() -> None:
    runner = _load_runner()
    prereg = runner.load_prereg()
    assert prereg["status"] == "frozen_before_block1_controller_v3_scoring"
    assert prereg["block_contract"]["later_blocks_available"] is False
    assert prereg["block_contract"]["end_exclusive"] == "2011-01-06T00:00:00Z"
    assert prereg["freeze_rules"]["protected_2023_plus_remains_sealed"] is True
    assert prereg["schema_version"] == 4
    assert prereg["expert_path_contract"]["full_native_horizon_for_every_decision"] is True
    assert prereg["attribute_weight_oracle"]["attribute_count"] == 53
    assert prereg["attribute_weight_oracle"]["selection_use"] is False
    assert prereg["attribute_weight_oracle"]["horizons_sessions"] == [1, 3, 5, 10, 20]
    assert prereg["attribute_weight_oracle"]["sparse_ks"] == [1, 2, 4, 8, 16]
    assert prereg["attribute_weight_oracle"]["exposure_step_contracts"] == 0.25
    assert prereg["expert_effectiveness_contract"]["memory_scale_selection"]["granularity"] == (
        "independent_per_specialist_horizon_direction"
    )
    assert prereg["primitive_oracle_winner_predictor"]["target_components"] == [
        "policy_id", "specialist", "horizon", "direction",
    ]
    assert prereg["primitive_oracle_winner_predictor"]["selection_use"] is False


def test_v3_keeps_controller_v2_predecessor_immutable() -> None:
    runner = _load_runner()
    prereg = runner.load_prereg()
    predecessor = prereg["predecessor_v2"]
    for key, path in runner.V2_FILES.items():
        hash_key = f"{key}_sha256"
        if hash_key in predecessor:
            assert runner.sha256_file(path) == predecessor[hash_key]


def test_v3_dry_preflight_passes_without_scoring() -> None:
    runner = _load_runner()
    report = runner.preflight(write=False)
    assert report["status"] == "PASS"
    assert report["scoring_performed"] is False
    assert report["candidate_count"] == 96
    assert report["checks"]["complete_memory_bank_participates"] is True
    assert report["checks"]["independent_memory_scale_selection_frozen"] is True
    assert report["checks"]["primitive_oracle_winner_predictor_frozen"] is True
    assert report["checks"]["historical_reentry_covers_every_source_record"] is True
    assert report["checks"]["exact_empirical_negative_roles_semantically_bound"] is True
    assert report["checks"]["block1_execution_archive_physically_isolated"] is True
    assert report["checks"]["weightable_attribute_oracle_is_exactly_complete"] is True
    assert report["checks"]["expert_native_path_archive_hash_bound_and_block1_only"] is True
    assert report["checks"]["expert_effectiveness_metrics_complete"] is True
    assert report["checks"]["full_attribute_weight_oracle_and_causal_predictor_frozen"] is True
    assert report["checks"]["later_blocks_not_loaded"] is True
    assert report["checks"]["protected_confirmation_not_accessed"] is True


def test_v3_jsonl_writer_streams_without_dataframe_to_json(tmp_path, monkeypatch) -> None:
    runner = _load_runner()
    frame = pd.DataFrame({
        "decision_time": pd.date_range("2010-07-01", periods=2, freq="D", tz="UTC"),
        "payload": [{"x": 1}, {"x": 2}],
    })
    monkeypatch.setattr(
        pd.DataFrame, "to_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("full-frame to_json forbidden")),
    )
    target = tmp_path / "stream.jsonl"
    runner._write_jsonl(target, frame)
    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["payload"] == {"x": 1}


def test_v3_progress_reports_every_candidate() -> None:
    runner = _load_runner()
    assert runner._candidate_progress_message(1, 96, 3) == (
        "controller-v3 structural candidates 1/96 complete (3/288 scenario replays checkpointed)"
    )
    assert "96/96 complete" in runner._candidate_progress_message(96, 96, 288)


def test_v3_candidate_checkpoint_round_trips_atomically(tmp_path) -> None:
    runner = _load_runner()
    prereg = runner.load_prereg()
    config = runner.structural_grid(prereg)[0]
    scenario_ids = tuple(str(row["id"]) for row in prereg["execution_sensitivity"]["scenarios"])
    replays = {}
    for scenario_id in scenario_ids:
        decisions = pd.DataFrame({
            "decision_time": [pd.Timestamp("2010-07-06T00:00:00Z")],
            "target_exposure": [0.5],
            "nested": [{"scenario": scenario_id}],
        })
        consequences = pd.DataFrame({
            "decision_time": [pd.Timestamp("2010-07-06T00:00:00Z")],
            "outcome_available_at": [pd.Timestamp("2010-07-07T00:00:00Z")],
            "realized_net_return": [0.001],
        })
        replays[scenario_id] = runner.CandidateReplay(
            config=config, decisions=decisions, consequences=consequences,
            summary={"execution_scenario": scenario_id},
        )
    runner._write_candidate_checkpoint(tmp_path, 1, config, replays)
    loaded = runner._load_candidate_checkpoint(tmp_path, 1, config, scenario_ids)
    assert loaded is not None
    assert set(loaded) == set(scenario_ids)
    assert loaded[scenario_ids[0]].config.config_id == config.config_id
    assert loaded[scenario_ids[0]].decisions.iloc[0]["nested"]["scenario"] == scenario_ids[0]
    assert loaded[scenario_ids[0]].summary["execution_scenario"] == scenario_ids[0]


def test_v3_candidate_causal_prefix_is_stable_across_checkpoint_round_trip(tmp_path) -> None:
    runner = _load_runner()
    prereg = runner.load_prereg()
    config = runner.structural_grid(prereg)[0]
    scenario_ids = ("base",)
    decision_time = pd.Timestamp("2010-07-06T00:00:00Z")
    decisions = pd.DataFrame([{
        "decision_time": decision_time,
        "active_families": ("trend",),
        "position_before": {
            "decision_time": decision_time,
            "mark_observation_time": pd.Timestamp("2010-07-05T23:00:00Z"),
        },
        "target_exposure": 0.04144196217119536,
        "executed_target_exposure": 0.04144196217119536,
        "execution_audit": {
            "available_at": pd.Timestamp("2010-07-06T01:00:00Z"),
            "fill_price": 4.123456789012345,
        },
    }])
    consequences = pd.DataFrame([{
        "decision_time": decision_time,
        "outcome_available_at": pd.Timestamp("2010-07-07T00:00:00Z"),
        "realized_net_return": 0.001,
    }])
    original = runner.CandidateReplay(config, decisions, consequences, {"execution_scenario": "base"})
    runner._write_candidate_checkpoint(tmp_path, 1, config, {"base": original})
    loaded = runner._load_candidate_checkpoint(tmp_path, 1, config, scenario_ids)
    assert loaded is not None
    cutoff = pd.Timestamp("2010-07-06T00:30:00Z")
    assert runner._candidate_prefix_payload(original, cutoff) == runner._candidate_prefix_payload(
        loaded["base"], cutoff
    )
    audit_cutoff = pd.Timestamp("2010-07-06T02:00:00Z")
    assert runner._matured_execution_audit_prefix_payload(
        original.decisions, audit_cutoff
    ) == runner._matured_execution_audit_prefix_payload(loaded["base"].decisions, audit_cutoff)


def test_v3_meta_causal_prefix_excludes_post_controller_diagnostic_enrichment() -> None:
    runner = _load_runner()
    decision_time = pd.Timestamp("2010-07-06T00:00:00Z")
    core = pd.DataFrame([{
        "decision_time": decision_time,
        "active_structural_configs": ("c1",),
        "target_exposure": 0.5,
    }])
    enriched = core.copy(deep=True)
    enriched["expert_context_state"] = [{"x": 1.0}]
    enriched["expert_multi_horizon_opinions"] = [{"h1": 0.01}]
    enriched["oracle_weight_predictor"] = [{"selection_use": False}]
    enriched["primitive_oracle_winner_predictor"] = [{"selection_use": False}]
    cutoff = decision_time
    assert runner._decision_causal_prefix_payload(enriched, cutoff) == (
        runner._decision_causal_prefix_payload(core, cutoff)
    )
    assert runner._prefix_payload(enriched, cutoff) == runner._prefix_payload(core, cutoff)


def test_v3_scoring_identity_binds_runtime_code_data_and_environment() -> None:
    runner = _load_runner()
    identity = runner.scoring_input_identity()
    assert {
        "base_controller_dependency_sha256", "v1_runner_dependency_sha256",
        "controller_v2_dependency_sha256", "v2_runner_dependency_sha256",
    }.issubset(identity["code"])
    assert {
        "v1_prereg_sha256", "v1_pit_state_sha256", "expert_paths_sha256",
        "expert_path_manifest_sha256", "expert_history_canonical_sha256",
        "expert_history_ohlcv_sha256", "execution_sessions_sha256",
    }.issubset(identity["data_and_contracts"])
    assert {"python_version", "packages", "pyproject_sha256", "requirements_lock_sha256"}.issubset(
        identity["environment"]
    )


def test_v3_checkpoint_namespace_changes_with_scoring_identity(monkeypatch) -> None:
    runner = _load_runner()
    monkeypatch.setattr(runner, "scoring_input_identity_sha256", lambda: "a" * 64)
    first = runner._checkpoint_run_root("grid")
    monkeypatch.setattr(runner, "scoring_input_identity_sha256", lambda: "b" * 64)
    second = runner._checkpoint_run_root("grid")
    assert first != second


def test_v3_generation_publication_is_atomic_and_pending_scope_audit(tmp_path, monkeypatch) -> None:
    runner = _load_runner()
    monkeypatch.setattr(runner, "REPO", tmp_path)
    monkeypatch.setattr(runner, "GENERATION_ROOT", tmp_path / "generations")
    monkeypatch.setattr(runner, "CURRENT_GENERATION", tmp_path / "current-generation.json")
    runner.GENERATION_ROOT.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    for canonical in runner.SCORE_ARTIFACTS:
        (staging / canonical.name).write_text(f"{canonical.name}\n", encoding="utf-8")
    pointer = runner._publish_generation(
        staging, "seed", scoring_identity_sha256="identity", candidate_grid_sha256="grid",
    )
    assert pointer["status"] == "SCORED_PENDING_SCOPE_AUDIT"
    persisted = json.loads(runner.CURRENT_GENERATION.read_text(encoding="utf-8"))
    assert persisted == pointer
    manifest_path = tmp_path / pointer["generation_path"] / runner.GENERATION_MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "SCORED_PENDING_SCOPE_AUDIT"
    assert set(manifest["artifact_hashes"]) == {path.name for path in runner.SCORE_ARTIFACTS}


def test_v3_execution_path_books_all_sessions_until_next_fill(tmp_path, monkeypatch) -> None:
    runner = _load_runner()
    sessions_path = tmp_path / "execution-sessions.csv"
    pd.DataFrame({
        "session_open": pd.to_datetime([
            "2010-07-01T00:00:00Z", "2010-07-02T00:00:00Z",
            "2010-07-03T00:00:00Z", "2010-07-04T00:00:00Z",
        ]),
        "next_session_open": pd.to_datetime([
            "2010-07-02T00:00:00Z", "2010-07-03T00:00:00Z",
            "2010-07-04T00:00:00Z", "2010-07-05T00:00:00Z",
        ]),
        "contract_id": ["NG"] * 4,
        "next_selected_contract_id": ["NG"] * 4,
        "open_price": [4.0, 4.1, 4.2, 4.3],
        "next_open_same_contract": [4.1, 4.2, 4.3, 4.4],
        "path_move_per_mmbtu": [0.1, 0.2, 0.3, 0.4],
        "roll_at_next_open": [False] * 4,
    }).to_csv(sessions_path, index=False)
    monkeypatch.setattr(runner, "EXECUTION_SESSIONS", sessions_path)
    state = pd.DataFrame({
        "decision_time": pd.to_datetime(["2010-07-01T00:00:00Z", "2010-07-03T00:00:00Z"]),
        "fill_timestamp": pd.to_datetime(["2010-07-01T00:00:00Z", "2010-07-03T00:00:00Z"]),
        "fill_contract_id": ["NG", "NG"],
    })
    prereg = {
        "consequence_horizons_sessions": [1],
        "block_contract": {"end_exclusive": "2010-07-05T00:00:00Z"},
    }
    path = runner.build_execution_path(state, prereg, None, None, {})
    assert path.iloc[0]["holding_session_count"] == 2
    assert path.iloc[0]["holding_move_per_mmbtu"] == pytest.approx(0.3)
    assert pd.Timestamp(path.iloc[0]["holding_outcome_available_at"]) == pd.Timestamp(
        "2010-07-03T00:00:00Z"
    )


def test_v3_side_contribution_attributes_exit_cost_to_closed_side() -> None:
    runner = _load_runner()
    consequences = pd.DataFrame({
        "exposure_before": [1.0], "signal": [0.0], "gross_return": [0.0],
        "execution_cost_return": [0.001], "transition_turnover": [1.0],
        "roll_turnover": [0.0], "turnover": [1.0],
    })
    contribution = runner.side_contribution(consequences)
    assert contribution["method"] == "transition_aware_gross_and_cost_attribution"
    assert contribution["by_side_net_return"]["long"] == -0.001
    assert contribution["by_side_net_return"]["flat"] == 0.0
    assert contribution["reconciles_to_total_net_return"] == -0.001
