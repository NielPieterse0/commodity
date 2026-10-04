from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
PREREG = PROGRAMME / "issue465-block1-controller-v3-prereg.json"
PREFLIGHT = PROGRAMME / "issue465-block1-controller-v3-preflight.json"
INVENTORY = PROGRAMME / "issue465-block1-controller-v3-inventory.json"
REENTRY = PROGRAMME / "issue465-block1-controller-v3-historical-reentry.json"
BRAIN = PROGRAMME / "issue465-block1-controller-v3-decision-brain.jsonl"
CONSEQUENCES = PROGRAMME / "issue465-block1-controller-v3-consequences.jsonl"
RESULT = PROGRAMME / "issue465-block1-controller-v3-result.json"
EXPERT_PATHS = PROGRAMME / "issue465-block1-controller-v3-expert-paths.jsonl"
EXPERT_MANIFEST = PROGRAMME / "issue465-block1-controller-v3-expert-paths-manifest.json"
ATTRIBUTE_ORACLE = PROGRAMME / "issue465-block1-controller-v3-attribute-oracle.jsonl"
ORACLE_PREDICTOR = PROGRAMME / "issue465-block1-controller-v3-oracle-predictor.jsonl"
PRIMITIVE_ORACLE_PREDICTOR = PROGRAMME / "issue465-block1-controller-v3-primitive-oracle-predictor.jsonl"
ORACLE_FIRST = PROGRAMME / "issue465-block1-controller-v3-oracle-first.json"
TRIALS = PROGRAMME / "issue465-block1-controller-v3-trials.jsonl"
LEDGER = PROGRAMME / "issue465-block1-controller-v3-ledger.json"
CANDIDATES = PROGRAMME / "issue465-block1-controller-v3-candidates.json"
EXPERT_HISTORY_CANONICAL = PROGRAMME / "issue465-block1-controller-v3-expert-history-canonical.csv"
EXPERT_HISTORY_OHLCV = PROGRAMME / "issue465-block1-controller-v3-expert-history-ohlcv.csv"
EXECUTION_SESSIONS = PROGRAMME / "issue465-block1-controller-v3-execution-sessions.csv"
V1_STATE = PROGRAMME / "issue465-block1-pit-state-v1.jsonl"
OUTPUT = PROGRAMME / "issue465-block1-controller-v3-completeness-audit.json"
V1_INVENTORY = PROGRAMME / "issue465-inventory-v1.json"
CURRENT_GENERATION = PROGRAMME / "issue465-block1-controller-v3-current-generation.json"
GENERATION_MANIFEST_NAME = "generation-manifest.json"
SCORE_ARTIFACT_NAMES = {
    "issue465-block1-controller-v3-primitive-oracle-predictor.jsonl",
    "issue465-block1-controller-v3-attribute-oracle.jsonl",
    "issue465-block1-controller-v3-oracle-predictor.jsonl",
    "issue465-block1-controller-v3-oracle-first.json",
    "issue465-block1-controller-v3-trials.jsonl",
    "issue465-block1-controller-v3-decision-brain.jsonl",
    "issue465-block1-controller-v3-consequences.jsonl",
    "issue465-block1-controller-v3-ledger.json",
    "issue465-block1-controller-v3-result.json",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(condition: Any, evidence: Any) -> dict[str, Any]:
    return {"pass": bool(condition), "evidence": evidence}


def _write_json_atomic(path: Path, payload: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _resolve_generation() -> tuple[dict[str, Any], dict[str, Any], Path, dict[str, Path]]:
    pointer = json.loads(CURRENT_GENERATION.read_text(encoding="utf-8"))
    generation_dir = REPO / str(pointer["generation_path"])
    manifest_path = generation_dir / GENERATION_MANIFEST_NAME
    if sha256_file(manifest_path) != pointer["generation_manifest_sha256"]:
        raise RuntimeError("published generation manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if pointer["generation_id"] != manifest["generation_id"]:
        raise RuntimeError("published generation identity mismatch")
    paths = {name: generation_dir / name for name in SCORE_ARTIFACT_NAMES}
    if set(manifest.get("artifact_hashes", {})) != SCORE_ARTIFACT_NAMES:
        raise RuntimeError("published generation manifest does not enumerate the complete score artifact set")
    for name, path in paths.items():
        if not path.is_file() or sha256_file(path) != manifest["artifact_hashes"][name]:
            raise RuntimeError(f"published generation artifact hash mismatch: {name}")
    return pointer, manifest, generation_dir, paths


def main() -> int:
    pointer, generation_manifest, _generation_dir, generation_paths = _resolve_generation()
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    reentry = json.loads(REENTRY.read_text(encoding="utf-8"))
    result_path = generation_paths[RESULT.name]
    brain_path = generation_paths[BRAIN.name]
    consequences_path = generation_paths[CONSEQUENCES.name]
    attribute_oracle_path = generation_paths[ATTRIBUTE_ORACLE.name]
    oracle_predictor_path = generation_paths[ORACLE_PREDICTOR.name]
    primitive_predictor_path = generation_paths[PRIMITIVE_ORACLE_PREDICTOR.name]
    result = json.loads(result_path.read_text(encoding="utf-8"))
    v1_inventory = json.loads(V1_INVENTORY.read_text(encoding="utf-8"))
    expert_manifest = json.loads(EXPERT_MANIFEST.read_text(encoding="utf-8"))
    oracle_first = json.loads(generation_paths[ORACLE_FIRST.name].read_text(encoding="utf-8"))
    ledger = json.loads(generation_paths[LEDGER.name].read_text(encoding="utf-8"))
    selected_consequences = pd.DataFrame(ledger.get("selected_consequences", []))
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    brain = pd.read_json(brain_path, lines=True)
    consequences = pd.read_json(consequences_path, lines=True)
    _trials = pd.read_json(generation_paths[TRIALS.name], lines=True)
    expert_paths = pd.read_json(EXPERT_PATHS, lines=True)
    oracle = pd.read_json(attribute_oracle_path, lines=True)
    predictor = pd.read_json(oracle_predictor_path, lines=True)
    primitive_predictor = pd.read_json(primitive_predictor_path, lines=True)
    v1_state = pd.read_json(V1_STATE, lines=True)
    execution_sessions = pd.read_csv(EXECUTION_SESSIONS)
    expert_history_canonical = pd.read_csv(EXPERT_HISTORY_CANONICAL)
    expert_history_ohlcv = pd.read_csv(EXPERT_HISTORY_OHLCV)
    brain["decision_time"] = pd.to_datetime(brain["decision_time"], utc=True)
    predictor["decision_time"] = pd.to_datetime(predictor["decision_time"], utc=True)
    primitive_predictor["decision_time"] = pd.to_datetime(
        primitive_predictor["decision_time"], utc=True
    )
    predictor["max_label_available_at"] = pd.to_datetime(
        predictor["max_label_available_at"], utc=True, errors="coerce"
    )
    primitive_predictor["max_label_available_at"] = pd.to_datetime(
        primitive_predictor["max_label_available_at"], utc=True, errors="coerce"
    )
    block_end = pd.Timestamp(prereg["block_contract"]["end_exclusive"])
    protected_start = pd.Timestamp(prereg["pit_contract"]["protected_start"])
    v1_state["decision_time"] = pd.to_datetime(v1_state["decision_time"], utc=True)
    execution_sessions["session_open"] = pd.to_datetime(
        execution_sessions["session_open"], utc=True, errors="raise"
    )
    execution_sessions["next_session_open"] = pd.to_datetime(
        execution_sessions["next_session_open"], utc=True, errors="coerce"
    )
    expert_history_canonical["trade_date"] = pd.to_datetime(
        expert_history_canonical["trade_date"], utc=True, errors="raise"
    )
    expert_history_ohlcv["trade_date"] = pd.to_datetime(
        expert_history_ohlcv["trade_date"], utc=True, errors="raise"
    )
    holds = {
        row["family"]: row.get("reason") for row in v1_inventory["family_dispositions"]
        if row["block1"] == "HOLD"
    }
    pit_samples = [value for value in brain["pit_state"] if isinstance(value, dict)]
    pit_metadata_keys = sorted({
        str(key) for sample in pit_samples for key in sample
        if any(token in str(key).lower() for token in ("age", "vintage", "revision", "available_at", "observation_time"))
    })
    pit_timestamp_violations: list[dict[str, Any]] = []
    for brain_row in brain.itertuples(index=False):
        decision_time = pd.Timestamp(brain_row.decision_time)
        sample = brain_row.pit_state if isinstance(brain_row.pit_state, dict) else {}
        for key, value in sample.items():
            if not any(token in str(key).lower() for token in ("available_at", "observation_time")):
                continue
            if value is None or pd.isna(value):
                continue
            try:
                observed = pd.Timestamp(value)
            except (TypeError, ValueError):
                continue
            if observed.tzinfo is None:
                observed = observed.tz_localize("UTC")
            else:
                observed = observed.tz_convert("UTC")
            if observed > decision_time:
                pit_timestamp_violations.append({
                    "decision_time": decision_time.isoformat(),
                    "field": str(key),
                    "observed_at": observed.isoformat(),
                })
    age_values: list[float] = []
    for sample in pit_samples:
        for key, value in sample.items():
            if "age" not in str(key).lower() or value is None or pd.isna(value):
                continue
            try:
                age_values.append(float(value))
            except (TypeError, ValueError):
                pass
    valid_next = execution_sessions["next_session_open"].notna()
    physical_block1_sources = bool(
        len(v1_state) == 123
        and (v1_state["decision_time"] < block_end).all()
        and (execution_sessions["session_open"] < block_end).all()
        and (execution_sessions.loc[valid_next, "next_session_open"] <= block_end).all()
        and (expert_history_canonical["trade_date"] < block_end).all()
        and (expert_history_ohlcv["trade_date"] < block_end).all()
        and max(
            v1_state["decision_time"].max(),
            execution_sessions["session_open"].max(),
            expert_history_canonical["trade_date"].max(),
            expert_history_ohlcv["trade_date"].max(),
        ) < protected_start
    )
    pit_metadata_complete = bool(
        any("age" in key.lower() for key in pit_metadata_keys)
        and any("vintage" in key.lower() or "revision" in key.lower() for key in pit_metadata_keys)
        and any(
            "available_at" in key.lower() or "observation_time" in key.lower()
            for key in pit_metadata_keys
        )
        and not pit_timestamp_violations
        and age_values
        and min(age_values) >= 0.0
    )
    used_outcomes = pd.to_datetime(
        brain["max_outcome_available_at_used"], utc=True, errors="coerce"
    )
    direct_causal_selection = bool(
        (
            used_outcomes.loc[used_outcomes.notna()].to_numpy()
            < brain.loc[used_outcomes.notna(), "decision_time"].to_numpy()
        ).all()
    )
    comparable_ref_violations: list[dict[str, Any]] = []
    for row in brain.itertuples(index=False):
        decision_time = pd.Timestamp(row.decision_time)
        for raw_ref in row.comparable_state_refs:
            ref = pd.Timestamp(raw_ref)
            if ref >= decision_time:
                comparable_ref_violations.append({
                    "decision_time": decision_time.isoformat(), "reference": ref.isoformat()
                })
    required_surface_fields = {
        "specialist", "horizon", "direction", "memory", "count",
        "mean_net_return", "objective_30_net_return_sum", "comparable_count",
        "comparable_mean_net_return",
    }
    effectiveness_surface_complete = bool(
        brain["effectiveness_surface"].map(
            lambda rows: isinstance(rows, list)
            and bool(rows)
            and all(required_surface_fields.issubset(row) for row in rows)
        ).all()
    )
    candidate_rows = list(candidates.get("candidates", []))
    independent_long_short_profiles = bool(
        any(
            row.get("asymmetric") is True
            and row.get("long_policy", {}).get("profile_id")
            != row.get("short_policy", {}).get("profile_id")
            for row in candidate_rows
        )
        and any(row.get("asymmetric") is False for row in candidate_rows)
    )
    checks: dict[str, dict[str, Any]] = {}
    checks["one_brain_per_decision_timestamp"] = check(
        len(brain) == 123 and brain["decision_time"].is_unique, len(brain)
    )
    checks["block1_only"] = check(
        (brain["decision_time"] < pd.Timestamp(prereg["block_contract"]["end_exclusive"])).all(),
        str(brain["decision_time"].max()),
    )
    checks["protected_2023_plus_sealed"] = check(
        physical_block1_sources,
        {
            "v1_state_max": str(v1_state["decision_time"].max()),
            "execution_session_max": str(execution_sessions["session_open"].max()),
            "canonical_history_max": str(expert_history_canonical["trade_date"].max()),
            "ohlcv_history_max": str(expert_history_ohlcv["trade_date"].max()),
        },
    )
    checks["pit_state_snapshot_archived_every_timestamp"] = check(
        "pit_state" in brain and brain["pit_state"].map(lambda value: isinstance(value, dict) and len(value) > 0).all(),
        "brain.pit_state",
    )
    checks["availability_age_vintage_revision_retained"] = check(
        pit_metadata_complete,
        {"metadata_keys": pit_metadata_keys, "timestamp_violations": pit_timestamp_violations[:5]},
    )
    checks["latest_known_carry_forward_only"] = check(
        not pit_timestamp_violations and bool(age_values) and min(age_values) >= 0.0,
        {"timestamp_violations": pit_timestamp_violations[:5], "minimum_age": min(age_values) if age_values else None},
    )
    checks["market_curve_technical_go"] = check(
        any(row["family"] == "market_curve_technical" and row["block1"] == "GO" for row in v1_inventory["family_dispositions"]),
        "market_curve_technical GO",
    )
    checks["cftc_positioning_go"] = check(
        any(row["family"] == "cftc_positioning" and row["block1"] == "GO" for row in v1_inventory["family_dispositions"]),
        "cftc_positioning GO",
    )
    expected_holds = {
        "futures_open_interest": "no_valid_referenced_records_2010",
        "storage": "PIT_support_starts_2015_06_19",
        "weather": "PIT_support_starts_2015_01_15",
        "power": "historical_publication_timing_not_promoted",
        "storage_consensus_surprise": "source_not_proven",
        "lng_physical": "no_registered_PIT_block1_source_through_issue431",
    }
    for family, reason in expected_holds.items():
        checks[f"hold_{family}"] = check(holds.get(family) == reason, holds.get(family))
    checks["timesfm_and_kronos_timestamped_experts"] = check(
        all(
            any(row["family"] == family and row["block1"] == "GO" for row in v1_inventory["family_dispositions"])
            for family in ("timesfm", "kronos")
        ),
        ["timesfm", "kronos"],
    )
    checks["full_native_foundation_paths_every_decision"] = check(
        len(expert_paths) == 123
        and expert_manifest["full_native_horizon_for_every_decision"] is True
        and all(
            all(len(values) == 20 for values in expert_paths[column])
            for column in (
                "timesfm_point_returns", "timesfm_q10_returns", "timesfm_q90_returns",
                "kronos_close_returns", "model_disagreement_returns",
            )
        ),
        {"rows": len(expert_paths), "horizon": expert_manifest["maximum_native_horizon_sessions"]},
    )
    checks["forecast_slope_acceleration_disagreement"] = check(
        {"timesfm_path_features", "kronos_path_features", "model_disagreement_returns", "model_sign_disagreement_rate"}.issubset(expert_paths.columns),
        sorted(set(expert_paths.columns) & {"timesfm_path_features", "kronos_path_features", "model_disagreement_returns", "model_sign_disagreement_rate"}),
    )
    expert_context_fields = set(prereg["expert_path_contract"]["controller_context_fields"])
    expert_context_samples = [
        value for value in brain.get("expert_context_state", []) if isinstance(value, dict)
    ]
    checks["foundation_path_context_live_in_controller"] = check(
        prereg["expert_path_contract"]["selection_use"]
        == "horizon_specific_direction_and_comparable_state_context_with_strict_prior_effectiveness"
        and expert_manifest["selection_use"]
        == "horizon_specific_direction_and_comparable_state_context"
        and len(expert_context_samples) == 123
        and all(expert_context_fields.issubset(sample) for sample in expert_context_samples)
        and brain["comparable_state_refs"].map(lambda value: isinstance(value, list)).all(),
        {
            "context_field_count": len(expert_context_fields),
            "archived_context_rows": len(expert_context_samples),
            "selection_use": expert_manifest.get("selection_use"),
        },
    )
    consequence_columns = set(consequences.columns)
    checks["research_consequence_store_separate"] = check(
        consequences_path != brain_path
        and generation_manifest["artifact_hashes"][CONSEQUENCES.name]
        != generation_manifest["artifact_hashes"][BRAIN.name],
        {"brain": brain_path.name, "consequences": consequences_path.name},
    )
    checks["future_returns_1_2_3_5_10_20"] = check(
        set(prereg["consequence_horizons_sessions"]) == {1, 2, 3, 5, 10, 20}
        and "forward_returns" in consequence_columns,
        prereg["consequence_horizons_sessions"],
    )
    checks["mfe_mae_future_realized_vol"] = check(
        "mfe_mae_and_future_volatility" in consequence_columns,
        "consequence store",
    )
    checks["best_executable_entry"] = check(
        "best_executable_entry_diagnostics" in consequence_columns,
        "consequence store",
    )
    checks["holding_and_size_counterfactuals"] = check(
        "holding_and_size_counterfactual_economics" in consequence_columns,
        "consequence store",
    )
    checks["action_counterfactuals"] = check(
        {"action_counterfactual_economics_1_session", "action_counterfactual_targets"}.issubset(consequence_columns),
        "consequence store",
    )
    checks["long_short_economics"] = check("long_short_economics" in consequence_columns, "consequence store")
    checks["slippage_missed_fill_diagnostics"] = check(
        "cost_slippage_missed_fill_degradation" in consequence_columns,
        "consequence store",
    )
    checks["same_timestamp_consequence_never_used"] = check(
        consequences["never_used_in_same_timestamp_selection"].astype(bool).all(),
        True,
    )
    checks["chronological_causal_replay"] = check(
        direct_causal_selection and not comparable_ref_violations,
        {
            "max_outcome_available_at_violations": int((~(
                used_outcomes.loc[used_outcomes.notna()].to_numpy()
                < brain.loc[used_outcomes.notna(), "decision_time"].to_numpy()
            )).sum()),
            "comparable_ref_violations": comparable_ref_violations[:5],
        },
    )
    future_proof = result["future_invariance_proof"]
    checks["full_future_mutation_invariance"] = check(
        future_proof["status"] == "PASS"
        and future_proof.get("full_persisted_row_prefix_comparison") is True
        and future_proof.get("structural_phase_prefixes_identical") is True
        and int(future_proof.get("structural_phase_cutoff_count", 0))
        >= int(prereg["meta_controller"]["structural_ensemble_cadence_sessions"]),
        future_proof,
    )
    checks["context_dependent_expert_effectiveness"] = check(
        effectiveness_surface_complete and not comparable_ref_violations,
        {
            "surface_rows_complete": effectiveness_surface_complete,
            "comparable_ref_violations": comparable_ref_violations[:5],
        },
    )
    checks["independent_long_short_effectiveness"] = check(
        independent_long_short_profiles,
        {"candidate_count": len(candidate_rows)},
    )
    checks["opportunity_horizons_1_3_5_10_20"] = check(
        set(prereg["opportunity_horizons_sessions"]) == {1, 3, 5, 10, 20},
        prereg["opportunity_horizons_sessions"],
    )
    checks["memory_bank_complete"] = check(
        set(map(str, prereg["expert_effectiveness_contract"]["memories"]))
        == {"5", "10", "20", "40", "60", "126", "252", "expanding"},
        prereg["expert_effectiveness_contract"]["memories"],
    )
    memory_contract = prereg["expert_effectiveness_contract"]["memory_scale_selection"]
    final_surface_memories = {
        str(row.get("memory")) for row in brain.iloc[-1]["effectiveness_surface"]
    }
    checks["independent_memory_scale_per_quantity"] = check(
        memory_contract["granularity"] == "independent_per_specialist_horizon_direction"
        and set(map(str, memory_contract["eligible_memories"]))
        == {"5", "10", "20", "40", "60", "126", "252", "expanding"}
        and memory_contract["strict_prior"] is True
        and {"5", "10", "20", "40", "60", "126", "252", "expanding"}.issubset(
            final_surface_memories
        ),
        {"contract": memory_contract, "observed_final_memories": sorted(final_surface_memories)},
    )
    forecast_metric_fields = {
        "direction_hit_rate", "forecast_mae_return", "interval_coverage",
        "max_forecast_outcome_available_at_used",
    }
    forecast_metric_rows = [
        row for rows in brain["effectiveness_surface"] for row in rows
        if str(row.get("specialist")) in {"timesfm_direction", "kronos_direction"}
    ]
    checks["forecast_error_hit_calibration_first_class"] = check(
        bool(forecast_metric_rows)
        and all(forecast_metric_fields.issubset(row) for row in forecast_metric_rows),
        {"row_count": len(forecast_metric_rows), "required_fields": sorted(forecast_metric_fields)},
    )
    forecast_surface_violations: list[dict[str, Any]] = []
    for brain_row in brain.itertuples(index=False):
        decision_time = pd.Timestamp(brain_row.decision_time)
        for surface_row in brain_row.effectiveness_surface:
            raw_used = surface_row.get("max_forecast_outcome_available_at_used")
            if raw_used is None or pd.isna(raw_used):
                continue
            used_at = pd.Timestamp(raw_used)
            if used_at >= decision_time:
                forecast_surface_violations.append({
                    "decision_time": decision_time.isoformat(),
                    "used_at": used_at.isoformat(),
                    "specialist": surface_row.get("specialist"),
                    "horizon": surface_row.get("horizon"),
                })
    checks["forecast_diagnostics_native_target_and_strict_prior"] = check(
        not forecast_surface_violations
        and bool(prereg["expert_effectiveness_contract"].get("forecast_target_semantics"))
        and bool(prereg["expert_effectiveness_contract"].get("forecast_metric_availability_rule")),
        {
            "target_semantics": prereg["expert_effectiveness_contract"].get("forecast_target_semantics"),
            "availability_rule": prereg["expert_effectiveness_contract"].get("forecast_metric_availability_rule"),
            "violations": forecast_surface_violations[:5],
        },
    )
    expected_reentry = {
        "positive_clue": 140, "underpowered": 187, "role_unidentifiable": 24,
        "source_or_data_hold": 19, "untested_mechanism": 27,
        "null_or_inconclusive": 30, "empirical_negative": 33,
    }
    counts = reentry.get("classification_counts", {})
    checks["historical_repository_record_coverage"] = check(
        reentry["record_count"] == reentry["source_record_count"] == 3929,
        {"record_count": reentry["record_count"], "source_record_count": reentry["source_record_count"]},
    )
    checks["historical_evidence_classes_reentered"] = check(
        all(int(counts.get(key, -1)) == value for key, value in expected_reentry.items()),
        counts,
    )
    role_bindings = reentry.get("current_role_semantic_bindings", {})
    checks["exact_empirical_negative_roles_only_blocked"] = check(
        reentry["blocked_exact_role_count"] == 33
        and int(role_bindings.get("empirical_negative_record_count", -1)) == 33
        and int(role_bindings.get("generated_role_count", -1)) == 123
        and role_bindings.get("blocked_current_role_ids") == []
        and all(
            int(row.get("evaluated_empirical_negative_count", -1)) == 33
            for row in role_bindings.get("bindings", [])
        ),
        {
            "historical_negative_count": reentry["blocked_exact_role_count"],
            "current_role_binding_count": len(role_bindings.get("bindings", [])),
            "blocked_current_role_ids": role_bindings.get("blocked_current_role_ids"),
        },
    )
    checks["all_53_pit_attributes_weightable"] = check(
        inventory["weightable_attribute_count"] == 53
        and sum(bool(row.get("individual_weighting_permitted")) for row in inventory["attributes"]) == 53,
        inventory["weightable_attribute_count"],
    )
    checks["123_specialists"] = check(
        preflight["specialist_count"] == 123,
        preflight["specialist_count"],
    )
    sparse_weight_lengths = [
        len(value) for value in brain["selected_weights"] if isinstance(value, dict) and value
    ]
    checks["zero_sparse_weights_legal"] = check(
        bool(sparse_weight_lengths) and min(sparse_weight_lengths) < int(preflight["specialist_count"]),
        {"minimum_nonzero_weight_count": min(sparse_weight_lengths) if sparse_weight_lengths else None},
    )
    position_fields = {
        "direction", "exposure", "entry_price", "entry_time", "entry_contract_id",
        "current_contract_id", "current_execution_basis_price", "equity_usd",
        "marked_equity_usd", "peak_marked_equity_usd", "risk_drawdown_fraction",
        "drawdown_fraction", "time_in_position_sessions", "unrealized_pnl_fraction",
        "mfe_to_date_fraction", "mae_to_date_fraction", "edge_at_entry",
        "mark_valid_for_position", "mark_rejection_reason",
    }
    position_samples = [value for value in brain["position_before"] if isinstance(value, dict)]
    checks["position_is_first_class_state"] = check(
        bool(position_samples) and all(position_fields.issubset(sample) for sample in position_samples),
        sorted(position_samples[-1].keys()) if position_samples else [],
    )
    checks["remaining_edge_and_edge_change"] = check(
        {"remaining_edge", "edge_change_since_entry"}.issubset(brain.columns),
        sorted(set(brain.columns) & {"remaining_edge", "edge_change_since_entry"}),
    )
    allowed_actions = {"FLAT", "STARTER", "FULL", "ADD", "REDUCE", "EXIT", "REVERSE"}
    lifecycle_policy_fields = {
        "blended_add_edge_ratio", "blended_reduce_edge_ratio", "blended_reverse_edge_ratio",
        "blended_exit_edge_floor", "blended_max_hold_sessions",
    }
    lifecycle_policies = [
        value for value in brain["meta_lifecycle_policy"] if isinstance(value, dict)
    ]
    checks["lifecycle_state_machine_complete"] = check(
        set(brain["action"].astype(str)).issubset(allowed_actions)
        and len(lifecycle_policies) == len(brain)
        and all(lifecycle_policy_fields.issubset(value) for value in lifecycle_policies),
        {"observed_actions": sorted(set(brain["action"].astype(str)))},
    )
    checks["remaining_edge_add_reduce_reverse_rules"] = check(
        {"remaining_edge", "edge_change_since_entry", "meta_lifecycle_reason"}.issubset(brain.columns)
        and all(lifecycle_policy_fields.issubset(value) for value in lifecycle_policies),
        sorted(lifecycle_policy_fields),
    )
    checks["prediction_action_separated_eight_stages"] = check(
        len(prereg["hierarchy"]) == 8
        and {"opportunity_table", "timing_decision", "action", "target_exposure"}.issubset(brain.columns),
        prereg["hierarchy"],
    )
    observed_timing = set(brain["timing_decision"].astype(str))
    checks["wait_enter_abstain"] = check(
        observed_timing.issubset({"WAIT", "ENTER_NOW", "ABSTAIN"}) and bool(observed_timing),
        sorted(observed_timing),
    )
    risk_states = [value for value in brain["risk_state"] if isinstance(value, dict)]
    max_leverage = float(pd.to_numeric(selected_consequences["notional_leverage"], errors="raise").max())
    max_margin = float(pd.to_numeric(selected_consequences["margin_fraction"], errors="raise").max())
    max_exposure = float(pd.to_numeric(selected_consequences["signal"], errors="raise").abs().max())
    checks["dynamic_sizing"] = check(
        len(risk_states) == len(brain)
        and all(
            {"hard_exposure_cap", "execution_price_hard_exposure_cap", "risk_drawdown_fraction"}.issubset(row)
            for row in risk_states
        ),
        {"risk_state_rows": len(risk_states)},
    )
    checks["hard_leverage_margin_drawdown_caps"] = check(
        max_exposure <= float(prereg["dynamic_sizing"]["max_abs_contracts"]) + 1e-12
        and max_margin <= float(prereg["dynamic_sizing"]["max_margin_fraction"]) + 1e-12
        and max_leverage <= float(prereg["dynamic_sizing"]["max_notional_leverage"]) + 1e-12
        and all(float(row["risk_drawdown_fraction"]) >= 0.0 for row in risk_states),
        {"max_exposure": max_exposure, "max_margin": max_margin, "max_leverage": max_leverage},
    )
    expected_scenarios = {str(row["id"]) for row in prereg["execution_sensitivity"]["scenarios"]}
    observed_scenarios = set(result.get("execution_degradation", {}))
    checks["risk_execution_layer"] = check(
        expected_scenarios == observed_scenarios
        and all(
            {"post_warmup_net_return", "missed_fill_count", "turnover", "delta_vs_base"}.issubset(payload)
            for payload in result["execution_degradation"].values()
        ),
        {"expected_scenarios": sorted(expected_scenarios), "observed_scenarios": sorted(observed_scenarios)},
    )
    checks["oracle_before_search_and_diagnostic_only"] = check(
        oracle_first.get("computed_before_structural_candidate_replay") is True
        and oracle_first.get("selection_use") is False
        and oracle_first.get("development_only_nontradable") is True
        and predictor["selection_use"].eq(False).all()
        and primitive_predictor["selection_use"].eq(False).all(),
        {
            "oracle_selection_use": oracle_first.get("selection_use"),
            "oracle_nontradable": oracle_first.get("development_only_nontradable"),
        },
    )
    checks["primitive_oracle_present"] = check(
        "winner_by_day" in oracle_first and len(oracle_first["winner_by_day"]) > 0,
        "primitive specialist x horizon x direction",
    )
    checks["full_53_attribute_weight_oracle"] = check(
        len(oracle) == 123
        and oracle["dense_weights"].map(lambda value: isinstance(value, dict) and len(value) == 53).all()
        and oracle["selection_use"].eq(False).all()
        and oracle["feature_importance_inference"].eq(False).all(),
        {"rows": len(oracle), "dense_weight_count_first": len(oracle.iloc[0]["dense_weights"])},
    )
    predictor_used = predictor.loc[predictor["training_label_count"] > 0]
    checks["causal_oracle_weight_predictor"] = check(
        (
            predictor_used["max_label_available_at"] < predictor_used["decision_time"]
        ).all()
        and predictor["selection_use"].eq(False).all()
        and predictor["feature_importance_inference"].eq(False).all(),
        {"used_rows": len(predictor_used)},
    )
    checks["oracle_predictor_future_invariance"] = check(
        result["future_invariance_proof"]["oracle_weight_predictor_prefix_identical"] is True,
        result["future_invariance_proof"]["oracle_weight_predictor_prefix_identical"],
    )
    primitive_predictor_used = primitive_predictor.loc[
        primitive_predictor["training_label_count"] > 0
    ]
    checks["causal_primitive_oracle_winner_predictor"] = check(
        (
            primitive_predictor_used["max_label_available_at"]
            < primitive_predictor_used["decision_time"]
        ).all()
        and set(primitive_predictor["target_type"].astype(str)) == {"primitive_policy_id"}
        and primitive_predictor["selection_use"].eq(False).all(),
        {"used_rows": len(primitive_predictor_used)},
    )
    checks["primitive_oracle_winner_predictor_future_invariance"] = check(
        result["future_invariance_proof"][
            "primitive_oracle_winner_predictor_prefix_identical"
        ] is True,
        result["future_invariance_proof"][
            "primitive_oracle_winner_predictor_prefix_identical"
        ],
    )
    brain_fields = {
        "pit_state", "specialist_signals", "effectiveness_surface", "comparable_state_refs",
        "selected_weights", "selected_group_weights", "candidate_objective_scores",
        "opportunity_table", "action", "target_exposure", "lifecycle_reason",
        "execution_assumptions", "expert_context_state", "expert_multi_horizon_opinions",
        "oracle_weight_predictor", "primitive_oracle_winner_predictor",
    }
    checks["complete_historical_brain_archive"] = check(
        len(brain) == 123 and brain_fields.issubset(brain.columns),
        sorted(brain_fields - set(brain.columns)),
    )
    checks["expert_predictions_archived"] = check(
        brain["specialist_signal_count"].eq(123).all()
        and brain["expert_multi_horizon_opinions"].map(lambda value: isinstance(value, dict) and len(value) > 0).all(),
        "123 specialist signals + foundation paths per timestamp",
    )
    checks["controller_weights_and_attribution_archived"] = check(
        {"selected_weights", "selected_group_weights", "selected_specialists", "reason_codes"}.issubset(brain.columns),
        "brain controller state",
    )
    checks["fills_and_later_outcomes_archived_separately"] = check(
        "execution_assumptions" in brain and "forward_returns" in consequences,
        "brain + separate consequence store",
    )
    checks["preflight_pass"] = check(preflight["status"] == "PASS", preflight["checks"])
    checks["scored_result_pending_scope_audit"] = check(
        result["status"] == "BLOCK1_CONTROLLER_V3_SCORED_PENDING_SCOPE_AUDIT"
        and generation_manifest["status"] == "SCORED_PENDING_SCOPE_AUDIT",
        {"result": result["status"], "generation": generation_manifest["status"]},
    )
    frozen_identity = preflight.get("scoring_input_identity", {})
    frozen_inputs = frozen_identity.get("data_and_contracts", {})
    generation_identity_ok = bool(
        result.get("scoring_input_identity_sha256")
        == preflight.get("scoring_input_identity_sha256")
        == generation_manifest.get("scoring_input_identity_sha256")
        and result.get("scoring_code_identity") == frozen_identity.get("code")
        and result.get("scoring_environment_identity") == frozen_identity.get("environment")
    )
    input_identity_ok = bool(
        frozen_inputs.get("prereg_sha256") == sha256_file(PREREG)
        and frozen_inputs.get("v1_pit_state_sha256") == sha256_file(V1_STATE)
        and frozen_inputs.get("expert_paths_sha256") == sha256_file(EXPERT_PATHS)
        and frozen_inputs.get("expert_path_manifest_sha256") == sha256_file(EXPERT_MANIFEST)
        and frozen_inputs.get("expert_history_canonical_sha256") == sha256_file(EXPERT_HISTORY_CANONICAL)
        and frozen_inputs.get("expert_history_ohlcv_sha256") == sha256_file(EXPERT_HISTORY_OHLCV)
        and frozen_inputs.get("execution_sessions_sha256") == sha256_file(EXECUTION_SESSIONS)
    )
    result_bindings_ok = bool(
        result["prereg_sha256"] == sha256_file(PREREG)
        and result["preflight_sha256"] == sha256_file(PREFLIGHT)
        and result["inventory_sha256"] == sha256_file(INVENTORY)
        and result["historical_reentry_sha256"] == sha256_file(REENTRY)
        and result["candidates_sha256"] == sha256_file(CANDIDATES)
        and result["oracle_first_sha256"] == sha256_file(generation_paths[ORACLE_FIRST.name])
        and result["expert_path_archive_sha256"] == sha256_file(EXPERT_PATHS)
        and result["expert_path_manifest_sha256"] == sha256_file(EXPERT_MANIFEST)
        and result["attribute_weight_oracle_sha256"] == sha256_file(attribute_oracle_path)
        and result["oracle_weight_predictor_sha256"] == sha256_file(oracle_predictor_path)
        and result["primitive_oracle_winner_predictor_sha256"] == sha256_file(primitive_predictor_path)
        and result["trials_sha256"] == sha256_file(generation_paths[TRIALS.name])
        and result["decision_brain_sha256"] == sha256_file(brain_path)
        and result["consequence_store_sha256"] == sha256_file(consequences_path)
        and result["ledger_sha256"] == sha256_file(generation_paths[LEDGER.name])
    )
    checks["complete_generation_and_scoring_identity_bound"] = check(
        generation_identity_ok and input_identity_ok and result_bindings_ok,
        {
            "generation_id": generation_manifest["generation_id"],
            "generation_identity_ok": generation_identity_ok,
            "input_identity_ok": input_identity_ok,
            "result_bindings_ok": result_bindings_ok,
        },
    )
    failures = [name for name, payload in checks.items() if not payload["pass"]]
    payload = {
        "schema_version": 2,
        "issue": 465,
        "scope": "V3 Block1 literal agreed-feature completeness double-check",
        "status": "PASS" if not failures else "FAIL",
        "generation_id": generation_manifest["generation_id"],
        "generation_manifest_sha256": pointer["generation_manifest_sha256"],
        "scoring_input_identity_sha256": generation_manifest["scoring_input_identity_sha256"],
        "source_isolation_verified": physical_block1_sources,
        "check_count": len(checks),
        "passed_count": len(checks) - len(failures),
        "failed_count": len(failures),
        "failed_checks": failures,
        "checks": checks,
        "protected_confirmation_accessed": False,
        "later_blocks_accessed": False,
    }
    _write_json_atomic(OUTPUT, payload)
    promoted_pointer = dict(pointer)
    promoted_pointer["scoring_input_identity_sha256"] = generation_manifest[
        "scoring_input_identity_sha256"
    ]
    promoted_pointer["completeness_audit_path"] = str(OUTPUT.relative_to(REPO))
    promoted_pointer["completeness_audit_sha256"] = sha256_file(OUTPUT)
    if failures:
        promoted_pointer["status"] = "SCORED_PENDING_SCOPE_AUDIT"
        promoted_pointer["latest_scope_audit_status"] = "FAIL"
        promoted_pointer["latest_scope_audit_failed_checks"] = failures
    else:
        promoted_pointer["status"] = "BLOCK1_CONTROLLER_V3_SCOPE_VERIFIED"
        promoted_pointer["latest_scope_audit_status"] = "PASS"
        promoted_pointer.pop("latest_scope_audit_failed_checks", None)
    _write_json_atomic(CURRENT_GENERATION, promoted_pointer)
    print(json.dumps({key: payload[key] for key in ("status", "check_count", "passed_count", "failed_count", "failed_checks")}, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
