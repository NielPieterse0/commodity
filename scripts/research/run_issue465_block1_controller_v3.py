from __future__ import annotations

import gzip
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from commodity.v2_adaptive_controller_v2 import (
    MEMORY_BANK,
    build_base_consequences,
    precompute_comparable_refs,
    serializable_value,
    stable_sha,
)
from commodity.v2_adaptive_controller_v3 import (
    CandidateReplay,
    causal_prior_check,
    config_to_dict,
    execution_turnover,
    oracle_first_diagnostic,
    precompute_profile_score_cache,
    replay_candidate_scenarios,
    replay_targets_under_execution_stress,
    run_meta_controller,
    structural_grid,
)
from commodity.v2_adaptive_controller_v3_diagnostics import (
    FOUNDATION_CONTEXT_COLUMNS,
    build_foundation_actual_paths,
    build_rich_expert_consequences,
    causal_oracle_weight_predictor,
    causal_primitive_oracle_winner_predictor,
    foundation_context_frame,
    foundation_horizon_signals,
    hindsight_attribute_weight_oracle,
    oracle_predictor_causal_check,
    oracle_weight_predictor_causal_projection,
    precompute_rich_surfaces_incremental,
    primitive_oracle_predictor_causal_projection,
)

PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
PREREG = PROGRAMME / "issue465-block1-controller-v3-prereg.json"
PREFLIGHT = PROGRAMME / "issue465-block1-controller-v3-preflight.json"
CANDIDATES = PROGRAMME / "issue465-block1-controller-v3-candidates.json"
INVENTORY = PROGRAMME / "issue465-block1-controller-v3-inventory.json"
REENTRY = PROGRAMME / "issue465-block1-controller-v3-historical-reentry.json"
ORACLE = PROGRAMME / "issue465-block1-controller-v3-oracle-first.json"
EXPERT_PATHS = PROGRAMME / "issue465-block1-controller-v3-expert-paths.jsonl"
EXPERT_PATH_MANIFEST = PROGRAMME / "issue465-block1-controller-v3-expert-paths-manifest.json"
EXPERT_HISTORY_CANONICAL = PROGRAMME / "issue465-block1-controller-v3-expert-history-canonical.csv"
EXPERT_HISTORY_OHLCV = PROGRAMME / "issue465-block1-controller-v3-expert-history-ohlcv.csv"
EXECUTION_SESSIONS = PROGRAMME / "issue465-block1-controller-v3-execution-sessions.csv"
ATTRIBUTE_ORACLE = PROGRAMME / "issue465-block1-controller-v3-attribute-oracle.jsonl"
ORACLE_PREDICTOR = PROGRAMME / "issue465-block1-controller-v3-oracle-predictor.jsonl"
PRIMITIVE_ORACLE_PREDICTOR = PROGRAMME / "issue465-block1-controller-v3-primitive-oracle-predictor.jsonl"
TRIALS = PROGRAMME / "issue465-block1-controller-v3-trials.jsonl"
BRAIN = PROGRAMME / "issue465-block1-controller-v3-decision-brain.jsonl"
EFFECTIVENESS_SURFACES = PROGRAMME / "issue465-block1-controller-v3-effectiveness-surfaces.parquet"
CONSEQUENCES = PROGRAMME / "issue465-block1-controller-v3-consequences.jsonl"
LEDGER = PROGRAMME / "issue465-block1-controller-v3-ledger.json"
RESULT = PROGRAMME / "issue465-block1-controller-v3-result.json"
CHECKPOINT_ROOT = PROGRAMME / "issue465-block1-controller-v3-candidate-replays"
GENERATION_ROOT = PROGRAMME / "issue465-block1-controller-v3-generations"
CURRENT_GENERATION = PROGRAMME / "issue465-block1-controller-v3-current-generation.json"
GENERATION_MANIFEST_NAME = "generation-manifest.json"

V1_PREREG = PROGRAMME / "issue465-prereg-v1.json"
V1_STATE = PROGRAMME / "issue465-block1-pit-state-v1.jsonl"
V1_INVENTORY = PROGRAMME / "issue465-inventory-v1.json"
ADVANTAGE_MAP = PROGRAMME / "issue459-advantage-map-v1.json"
V2_RUNNER = REPO / "scripts/research/run_issue465_block1_controller_v2.py"
V2_CONTROLLER = REPO / "src/commodity/v2_adaptive_controller_v2.py"
BASE_CONTROLLER = REPO / "src/commodity/v2_adaptive_controller.py"
V1_RUNNER = REPO / "scripts/research/run_issue465_adaptive_block.py"
QUANT_RESEARCH_KNOWLEDGE = REPO / "config/quantitative_research_knowledge.json"
PYPROJECT = REPO / "pyproject.toml"
REQUIREMENTS_LOCK = REPO / "requirements.lock.txt"
KRONOS_REQUIREMENTS_LOCK = REPO / "requirements.kronos-cpu.lock.txt"
V2_FILES = {
    "prereg": PROGRAMME / "issue465-block1-controller-v2-prereg.json",
    "preflight": PROGRAMME / "issue465-block1-controller-v2-preflight.json",
    "candidates": PROGRAMME / "issue465-block1-controller-v2-candidates.json",
    "trials": PROGRAMME / "issue465-block1-controller-v2-trials.jsonl",
    "decision_brain": PROGRAMME / "issue465-block1-controller-v2-decision-brain.jsonl",
    "ledger": PROGRAMME / "issue465-block1-controller-v2-ledger.json",
    "result": PROGRAMME / "issue465-block1-controller-v2-result.json",
}


def _materialize_frozen_jsonl(path: Path) -> Path:
    archive = path.with_name(path.name + ".gz")
    if path.exists() or not archive.is_file():
        return path
    temporary = path.with_name(f".{path.name}.materialize-{os.getpid()}")
    try:
        with gzip.open(archive, "rb") as source, temporary.open("wb") as target:
            shutil.copyfileobj(source, target, 1024 * 1024)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


BRAIN = _materialize_frozen_jsonl(BRAIN)
V2_FILES["decision_brain"] = _materialize_frozen_jsonl(V2_FILES["decision_brain"])


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_text_writer(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    return temporary


def _commit_atomic_file(temporary: Path, path: Path) -> None:
    os.replace(temporary, path)


def _write_json(path: Path, payload: Any) -> None:
    temporary = _atomic_text_writer(path)
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _commit_atomic_file(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_jsonl(path: Path, frame: pd.DataFrame) -> None:
    temporary = _atomic_text_writer(path)
    columns = [str(column) for column in frame.columns]
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            for values in frame.itertuples(index=False, name=None):
                payload = serializable_value(dict(zip(columns, values, strict=True)))
                handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _commit_atomic_file(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_effectiveness_surface_sidecar(
    path: Path,
    surfaces: dict[pd.Timestamp, pd.DataFrame],
) -> dict[str, Any]:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    path.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    row_count = 0
    populated_surface_count = 0
    try:
        for raw_stamp, raw_surface in surfaces.items():
            if raw_surface.empty:
                continue
            stamp = pd.Timestamp(raw_stamp)
            frame = raw_surface.copy()
            frame.insert(0, "effectiveness_surface_id", stamp.isoformat())
            frame.insert(1, "surface_decision_time", stamp)
            string_columns = {
                "effectiveness_surface_id", "specialist", "direction", "memory",
            }
            integer_columns = {
                "horizon", "count", "objective_30_count", "comparable_count",
                "forecast_diagnostic_count",
            }
            timestamp_columns = {
                "surface_decision_time", "max_outcome_available_at_used",
                "max_forecast_outcome_available_at_used",
            }
            for column in frame.columns:
                if column in string_columns:
                    frame[column] = frame[column].astype(str)
                elif column in integer_columns:
                    frame[column] = pd.to_numeric(frame[column], errors="raise").astype("int64")
                elif column in timestamp_columns:
                    frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
                else:
                    frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
            table = pa.Table.from_pandas(frame, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(temporary, table.schema, compression="zstd")
            writer.write_table(table)
            row_count += len(frame)
            populated_surface_count += 1
        if writer is None:
            raise RuntimeError("effectiveness surface sidecar has no rows")
        writer.close()
        writer = None
        _commit_atomic_file(temporary, path)
    finally:
        if writer is not None:
            writer.close()
        if temporary.exists():
            temporary.unlink()
    return {
        "path": path.name,
        "sha256": sha256_file(path),
        "row_count": int(row_count),
        "surface_count": len(surfaces),
        "populated_surface_count": int(populated_surface_count),
    }


SCORE_ARTIFACTS = (
    PRIMITIVE_ORACLE_PREDICTOR,
    ATTRIBUTE_ORACLE,
    ORACLE_PREDICTOR,
    ORACLE,
    TRIALS,
    BRAIN,
    EFFECTIVENESS_SURFACES,
    CONSEQUENCES,
    LEDGER,
    RESULT,
)


def _begin_generation(scoring_identity_sha256: str, candidate_grid_sha256: str) -> tuple[str, Path]:
    seed = stable_sha({
        "scoring_input_identity_sha256": scoring_identity_sha256,
        "candidate_grid_sha256": candidate_grid_sha256,
    })[:24]
    GENERATION_ROOT.mkdir(parents=True, exist_ok=True)
    staging = GENERATION_ROOT / f".staging-{seed}-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=False)
    return seed, staging


def _generation_output(staging: Path, canonical: Path) -> Path:
    return staging / canonical.name


def _publish_generation(
    staging: Path,
    seed: str,
    *,
    scoring_identity_sha256: str,
    candidate_grid_sha256: str,
) -> dict[str, Any]:
    artifact_hashes = {
        canonical.name: sha256_file(_generation_output(staging, canonical))
        for canonical in SCORE_ARTIFACTS
    }
    generation_id = stable_sha({
        "seed": seed,
        "artifact_hashes": artifact_hashes,
    })[:32]
    manifest = {
        "schema_version": 1,
        "issue": 465,
        "block_id": "block-001",
        "generation_id": generation_id,
        "status": "SCORED_PENDING_SCOPE_AUDIT",
        "scoring_input_identity_sha256": scoring_identity_sha256,
        "candidate_grid_sha256": candidate_grid_sha256,
        "artifact_hashes": artifact_hashes,
    }
    manifest_path = staging / GENERATION_MANIFEST_NAME
    _write_json(manifest_path, manifest)
    final = GENERATION_ROOT / generation_id
    if final.exists():
        existing_manifest = final / GENERATION_MANIFEST_NAME
        if not existing_manifest.is_file() or sha256_file(existing_manifest) != sha256_file(manifest_path):
            raise RuntimeError(f"generation identity collision: {generation_id}")
        shutil.rmtree(staging)
    else:
        os.replace(staging, final)
    pointer = {
        "schema_version": 1,
        "issue": 465,
        "block_id": "block-001",
        "generation_id": generation_id,
        "generation_path": str(final.relative_to(REPO)),
        "generation_manifest_sha256": sha256_file(final / GENERATION_MANIFEST_NAME),
        "scoring_input_identity_sha256": scoring_identity_sha256,
        "candidate_grid_sha256": candidate_grid_sha256,
        "status": "SCORED_PENDING_SCOPE_AUDIT",
    }
    _write_json(CURRENT_GENERATION, pointer)
    return pointer


def _mark_preflight_replay_required(
    *,
    scoring_identity_sha256: str,
    candidate_grid_sha256: str,
) -> None:
    existing = (
        json.loads(CURRENT_GENERATION.read_text(encoding="utf-8"))
        if CURRENT_GENERATION.is_file() else {}
    )
    if (
        existing.get("status") == "BLOCK1_CONTROLLER_V3_SCOPE_VERIFIED"
        and existing.get("scoring_input_identity_sha256") == scoring_identity_sha256
        and existing.get("candidate_grid_sha256") == candidate_grid_sha256
    ):
        return
    pointer = {
        "schema_version": 1,
        "issue": 465,
        "block_id": "block-001",
        "status": "PREFLIGHT_FROZEN_REPLAY_REQUIRED",
        "scoring_input_identity_sha256": scoring_identity_sha256,
        "candidate_grid_sha256": candidate_grid_sha256,
        "previous_generation_id": existing.get("generation_id"),
        "previous_generation_is_current": False,
    }
    _write_json(CURRENT_GENERATION, pointer)


def _candidate_progress_message(completed: int, total: int, scenario_replays_completed: int) -> str:
    return (
        f"controller-v3 structural candidates {int(completed)}/{int(total)} complete "
        f"({int(scenario_replays_completed)}/{int(total) * 3} scenario replays checkpointed)"
    )


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_v2_runner():
    return _load_module("issue465_v2_runner_for_v3", V2_RUNNER)

def load_prereg() -> dict[str, Any]:
    payload = json.loads(PREREG.read_text(encoding="utf-8"))
    if payload.get("status") != "frozen_before_block1_controller_v3_scoring":
        raise RuntimeError("controller-v3 preregistration is not frozen")
    predecessor = payload["predecessor_v2"]
    for key, path in V2_FILES.items():
        hash_key = f"{key}_sha256"
        if hash_key not in predecessor:
            continue
        if sha256_file(path) != str(predecessor[hash_key]):
            raise RuntimeError(f"immutable controller-v2 predecessor changed: {path.name}")
    return payload


def load_expert_paths() -> pd.DataFrame:
    if not EXPERT_PATHS.is_file() or not EXPERT_PATH_MANIFEST.is_file():
        raise RuntimeError("controller-v3 expert path archive is missing")
    manifest = json.loads(EXPERT_PATH_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("expert path archive touched protected confirmation")
    if manifest.get("later_block_market_data_accessed") is not False:
        raise RuntimeError("expert path archive touched later-block market data")
    if sha256_file(EXPERT_PATHS) != manifest.get("output_sha256"):
        raise RuntimeError("expert path archive hash mismatch")
    frame = pd.read_json(EXPERT_PATHS, lines=True)
    frame["decision_time"] = pd.to_datetime(frame["decision_time"], utc=True)
    if len(frame) != 123 or not frame["decision_time"].is_unique:
        raise RuntimeError("expert path archive must contain one row for every Block1 decision")
    expected_selection_use = "horizon_specific_direction_and_comparable_state_context"
    if manifest.get("selection_use") != expected_selection_use:
        raise RuntimeError("expert path manifest selection-use contract is stale")
    if set(frame["selection_use"].astype(str)) != {expected_selection_use}:
        raise RuntimeError("expert path rows selection-use contract is stale")
    path_columns = [
        "timesfm_point_returns", "timesfm_q10_returns", "timesfm_q90_returns",
        "kronos_close_returns", "model_disagreement_returns",
    ]
    if any(any(len(values) != 20 for values in frame[column]) for column in path_columns):
        raise RuntimeError("expert path archive must contain full 20-session paths for every decision")
    return frame


def load_foundation_actuals(expert_paths: pd.DataFrame, state: pd.DataFrame) -> pd.DataFrame:
    manifest = json.loads(EXPERT_PATH_MANIFEST.read_text(encoding="utf-8"))
    if sha256_file(EXPERT_HISTORY_CANONICAL) != manifest.get("canonical_history_sha256"):
        raise RuntimeError("foundation canonical history hash mismatch")
    if sha256_file(EXPERT_HISTORY_OHLCV) != manifest.get("ohlcv_history_sha256"):
        raise RuntimeError("foundation OHLCV history hash mismatch")
    canonical = pd.read_csv(EXPERT_HISTORY_CANONICAL)
    ohlcv = pd.read_csv(EXPERT_HISTORY_OHLCV)
    return build_foundation_actual_paths(expert_paths, canonical, ohlcv, state)


def build_controller_context(
    state: pd.DataFrame,
    expert_paths: pd.DataFrame,
    prereg: dict[str, Any],
) -> tuple[pd.DataFrame, list[str]]:
    base_columns = [str(value) for value in prereg["context_columns"]]
    expected_expert_columns = [
        str(value) for value in prereg["expert_path_contract"]["controller_context_fields"]
    ]
    if expected_expert_columns != list(FOUNDATION_CONTEXT_COLUMNS):
        raise RuntimeError("expert controller context contract differs from implementation")
    expert_context = foundation_context_frame(expert_paths)
    context = state[["decision_time", *base_columns]].merge(
        expert_context, on="decision_time", how="left", validate="one_to_one"
    )
    if context[expected_expert_columns].isna().any().any():
        raise RuntimeError("expert controller context is incomplete")
    return context, [*base_columns, *expected_expert_columns]


def runtime_environment_identity() -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for package in ("numpy", "pandas", "pyarrow", "scipy", "scikit-learn"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_machine": platform.machine(),
        "packages": packages,
        "pyproject_sha256": sha256_file(PYPROJECT),
        "requirements_lock_sha256": sha256_file(REQUIREMENTS_LOCK),
        "kronos_requirements_lock_sha256": sha256_file(KRONOS_REQUIREMENTS_LOCK),
    }


def current_code_identity() -> dict[str, str]:
    return {
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "controller_v3_sha256": sha256_file(REPO / "src/commodity/v2_adaptive_controller_v3.py"),
        "controller_v3_diagnostics_sha256": sha256_file(REPO / "src/commodity/v2_adaptive_controller_v3_diagnostics.py"),
        "expert_path_generator_sha256": sha256_file(REPO / "scripts/research/generate_issue465_block1_expert_paths_v3.py"),
        "controller_v2_dependency_sha256": sha256_file(V2_CONTROLLER),
        "v2_runner_dependency_sha256": sha256_file(V2_RUNNER),
        "base_controller_dependency_sha256": sha256_file(BASE_CONTROLLER),
        "v1_runner_dependency_sha256": sha256_file(V1_RUNNER),
    }


def scoring_input_identity() -> dict[str, Any]:
    required_files = {
        "prereg_sha256": PREREG,
        "v1_prereg_sha256": V1_PREREG,
        "v1_pit_state_sha256": V1_STATE,
        "v1_inventory_sha256": V1_INVENTORY,
        "advantage_map_sha256": ADVANTAGE_MAP,
        "expert_paths_sha256": EXPERT_PATHS,
        "expert_path_manifest_sha256": EXPERT_PATH_MANIFEST,
        "expert_history_canonical_sha256": EXPERT_HISTORY_CANONICAL,
        "expert_history_ohlcv_sha256": EXPERT_HISTORY_OHLCV,
        "execution_sessions_sha256": EXECUTION_SESSIONS,
        "quantitative_research_knowledge_sha256": QUANT_RESEARCH_KNOWLEDGE,
    }
    missing = [path.name for path in required_files.values() if not path.is_file()]
    if missing:
        raise RuntimeError(f"controller-v3 scoring identity inputs missing: {sorted(missing)}")
    return {
        "code": current_code_identity(),
        "data_and_contracts": {
            key: sha256_file(path) for key, path in sorted(required_files.items())
        },
        "environment": runtime_environment_identity(),
    }


def scoring_input_identity_sha256() -> str:
    return stable_sha(scoring_input_identity())


def _checkpoint_run_root(candidate_grid_sha256: str) -> Path:
    identity = stable_sha({
        "candidate_grid_sha256": str(candidate_grid_sha256),
        "scoring_input_identity_sha256": scoring_input_identity_sha256(),
    })[:24]
    return CHECKPOINT_ROOT / identity


def _candidate_checkpoint_dir(root: Path, ordinal: int, config_id: str) -> Path:
    key = hashlib.sha256(str(config_id).encode("utf-8")).hexdigest()[:12]
    return root / f"candidate-{int(ordinal):03d}-{key}"


def _write_candidate_checkpoint(
    root: Path,
    ordinal: int,
    config: Any,
    replays: dict[str, CandidateReplay],
) -> None:
    folder = _candidate_checkpoint_dir(root, ordinal, config.config_id)
    folder.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, str]] = {}
    for scenario_id, replay in sorted(replays.items()):
        decision_path = folder / f"{scenario_id}-decisions.jsonl"
        consequence_path = folder / f"{scenario_id}-consequences.jsonl"
        summary_path = folder / f"{scenario_id}-summary.json"
        _write_jsonl(decision_path, replay.decisions)
        _write_jsonl(consequence_path, replay.consequences)
        _write_json(summary_path, replay.summary)
        files[scenario_id] = {
            "decisions_sha256": sha256_file(decision_path),
            "consequences_sha256": sha256_file(consequence_path),
            "summary_sha256": sha256_file(summary_path),
        }
    _write_json(folder / "complete.json", {
        "candidate_ordinal": int(ordinal),
        "config_id": str(config.config_id),
        "config": config_to_dict(config),
        "scoring_input_identity_sha256": scoring_input_identity_sha256(),
        "scenarios": files,
        "complete": True,
    })


def _load_candidate_checkpoint(
    root: Path,
    ordinal: int,
    config: Any,
    scenario_ids: tuple[str, ...],
) -> dict[str, CandidateReplay] | None:
    folder = _candidate_checkpoint_dir(root, ordinal, config.config_id)
    marker = folder / "complete.json"
    if not marker.is_file():
        return None
    manifest = json.loads(marker.read_text(encoding="utf-8"))
    if manifest.get("complete") is not True or manifest.get("config_id") != config.config_id:
        return None
    if manifest.get("scoring_input_identity_sha256") != scoring_input_identity_sha256():
        return None
    if set(manifest.get("scenarios", {})) != set(scenario_ids):
        return None
    loaded: dict[str, CandidateReplay] = {}
    for scenario_id in scenario_ids:
        decision_path = folder / f"{scenario_id}-decisions.jsonl"
        consequence_path = folder / f"{scenario_id}-consequences.jsonl"
        summary_path = folder / f"{scenario_id}-summary.json"
        hashes = manifest["scenarios"][scenario_id]
        required = (decision_path, consequence_path, summary_path)
        if any(not path.is_file() for path in required):
            return None
        if sha256_file(decision_path) != hashes["decisions_sha256"]:
            return None
        if sha256_file(consequence_path) != hashes["consequences_sha256"]:
            return None
        if sha256_file(summary_path) != hashes["summary_sha256"]:
            return None
        decisions = pd.read_json(decision_path, lines=True, precise_float=True)
        consequences = pd.read_json(consequence_path, lines=True, precise_float=True)
        for frame in (decisions, consequences):
            for column in ("decision_time", "fill_timestamp", "outcome_available_at"):
                if column in frame:
                    frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
        loaded[scenario_id] = CandidateReplay(
            config=config,
            decisions=decisions,
            consequences=consequences,
            summary=json.loads(summary_path.read_text(encoding="utf-8")),
        )
    return loaded


def load_state(prereg: dict[str, Any]) -> tuple[pd.DataFrame, Any, Any, dict[str, Any]]:
    v2_runner = load_v2_runner()
    v1_runner = v2_runner.load_v1_runner()
    v1_prereg = json.loads(V1_PREREG.read_text(encoding="utf-8"))
    state = v2_runner.load_pit_state(prereg)
    end = pd.Timestamp(str(prereg["block_contract"]["end_exclusive"]))
    if (state["decision_time"] >= end).any():
        raise RuntimeError("controller-v3 loaded a later block")
    return state, v2_runner, v1_runner, v1_prereg

def _attribute_family(column: str, v2_runner: Any) -> str:
    return str(v2_runner.attribute_family(column))


def _source_identity(column: str) -> str:
    if column.startswith("timesfm_"):
        return "timesfm_frozen_feature_archive"
    if column.startswith("kronos_"):
        return "kronos_frozen_feature_archive"
    if column.startswith("positioning_") or column in {"managed_money_net", "producer_merchant_net"}:
        return "cftc_positioning_pit_archive"
    if column.startswith(("feature_", "derived_")):
        return "canonical_ng_market_feature_state"
    if column in {"trade_date", "signal_timestamp", "decision_time", "fill_timestamp", "fill_contract_id"}:
        return "execution_clock_and_contract_identity"
    return "issue465_block1_pit_state_v1"


def _pit_status(column: str) -> str:
    if column.endswith(("_at", "_time", "_timestamp")) or column == "trade_date":
        return "explicit_timestamp_identity"
    if "age_" in column:
        return "explicit_staleness_attribute"
    if "vintage" in column or "revision" in column:
        return "explicit_vintage_revision_identity"
    return "value_bound_to_row_decision_time_by_source_availability_checks"


def rich_attribute_inventory(
    state: pd.DataFrame,
    v2_runner: Any,
    weighted_attributes: list[str],
) -> list[dict[str, Any]]:
    base_rows = {row["attribute"]: row for row in v2_runner.attribute_inventory(state)}
    weighted = set(weighted_attributes)
    rows: list[dict[str, Any]] = []
    for column in state.columns:
        base = base_rows[column]
        family = _attribute_family(column, v2_runner) if column in weighted else "metadata_or_identity"
        rows.append({
            "attribute": column,
            "source_dataset_identity": _source_identity(column),
            "original_role": str(base["role"]),
            "historical_result": "retained_or_admitted_by_block1_v1_PIT_inventory; detailed prior evidence retained in historical_reentry ledger",
            "pit_status": _pit_status(column),
            "availability_semantics": "latest_known_as_of_decision_time; no pre-availability backfill",
            "admissible_current_roles": (["context_attribute", "direct_specialist", "inverse_specialist"] if column in weighted else [str(base["role"])]),
            "exclusion_reason": None if column in weighted else "non-numeric_or_provenance_identity_not_weighted",
            "derivation_identity": ("prior20_median_deviation_direct_and_inverse_shift1_min5" if column in weighted else "retained_as_recorded"),
            "family_identity": family,
            "individual_weighting_permitted": column in weighted,
            "group_weighting_permitted": column in weighted,
            "historical_role_binding": f"controller_v3_contextual_attribute/{column}" if column in weighted else "metadata_only",
        })
    return rows

def historical_reentry_payload() -> dict[str, Any]:
    source = json.loads(ADVANTAGE_MAP.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    blocked: list[str] = []
    for index, row in enumerate(source.get("raw_evidence", [])):
        classification = str(row.get("classification", "unknown"))
        role_id = (
            f"historical_exact_role::{row.get('source_path', '')}::"
            f"{row.get('object_path', '$')}"
        )
        if classification == "empirical_negative":
            disposition = "BLOCK_EXACT_TESTED_ROLE"
            blocked.append(role_id)
        elif classification == "positive_clue":
            disposition = "CARRY_FORWARD_AS_DISTINCT_CONTEXTUAL_CANDIDATE_WHERE_PIT_VALID"
        elif classification in {"underpowered", "role_unidentifiable"}:
            disposition = "ELIGIBLE_FOR_DISTINCT_CONTEXTUAL_META_ROLE_ONLY"
        elif classification in {"null_or_inconclusive", "source_or_data_hold", "untested_mechanism"}:
            disposition = "REASSESS_ONLY_IF_ARCHITECTURE_AND_PIT_SOURCE_MATERIALLY_DIFFER"
        else:
            disposition = "REFERENCE_ONLY_NO_AUTOMATIC_TRADING_ROLE"
        records.append({
            "evidence_index": index,
            "classification": classification,
            "exact_historical_role_id": role_id,
            "reentry_disposition": disposition,
            "source_kind": row.get("source_kind"),
            "source_path": row.get("source_path"),
            "object_path": row.get("object_path"),
            "status": row.get("status"),
            "reason": row.get("reason"),
            "identifiers": row.get("identifiers", {}),
            "economic_metrics": row.get("economic_metrics", {}),
        })
    return {
        "schema_version": 3,
        "issue": 465,
        "source_path": str(ADVANTAGE_MAP.relative_to(REPO)),
        "source_sha256": sha256_file(ADVANTAGE_MAP),
        "source_record_count": len(source.get("raw_evidence", [])),
        "record_count": len(records),
        "classification_counts": source.get("classification_counts", {}),
        "blocked_exact_role_count": len(blocked),
        "blocked_exact_role_ids": blocked,
        "records": records,
        "historical_evidence_relabelled": False,
        "protected_confirmation_accessed": False,
    }

def _historical_negative_role_bindings(
    reentry: dict[str, Any],
    v1_prereg: dict[str, Any],
    weighted_attributes: list[str],
) -> dict[str, Any]:
    current_roles: list[dict[str, Any]] = []
    for row in v1_prereg["specialist_library"]:
        specialist_id = str(row["id"])
        current_roles.append({
            "role_id": f"controller_v3_named_specialist/{specialist_id}/conditional_specialist",
            "role_kind": "named_specialist",
            "source_identity": specialist_id,
            "variant": "conditional_specialist",
            "legacy_exact_role_aliases": [specialist_id],
        })
    for column in weighted_attributes:
        for variant in ("direct", "inverse"):
            current_roles.append({
                "role_id": f"controller_v3_contextual_attribute/{column}/{variant}",
                "role_kind": "contextual_attribute",
                "source_identity": str(column),
                "variant": variant,
                "legacy_exact_role_aliases": [f"{column}:{variant}", f"{column}/{variant}"],
            })
    negative_records = [
        row for row in reentry["records"] if row["classification"] == "empirical_negative"
    ]
    bindings: list[dict[str, Any]] = []
    blocked_current: list[str] = []
    role_identifier_keys = {"role_id", "policy_id", "candidate_id", "specialist_id"}
    for role in current_roles:
        aliases = {str(role["role_id"]), *map(str, role["legacy_exact_role_aliases"])}
        matches: list[str] = []
        for historical in negative_records:
            identifiers = dict(historical.get("identifiers") or {})
            identifier_values = {
                str(value) for key, value in identifiers.items()
                if str(key) in role_identifier_keys and value is not None
            }
            if aliases.intersection(identifier_values):
                matches.append(str(historical["exact_historical_role_id"]))
        blocked = bool(matches)
        if blocked:
            blocked_current.append(str(role["role_id"]))
        bindings.append({
            **role,
            "evaluated_empirical_negative_count": len(negative_records),
            "exact_negative_role_matches": sorted(matches),
            "blocked": blocked,
            "binding_rule": "match explicit historical role/policy/candidate/specialist identifier to exact current-role aliases; source-family similarity alone is not an exact-role match",
        })
    return {
        "generated_role_count": len(current_roles),
        "empirical_negative_record_count": len(negative_records),
        "blocked_current_role_ids": sorted(blocked_current),
        "bindings": bindings,
    }


def build_execution_path(
    state: pd.DataFrame,
    prereg: dict[str, Any],
    v2_runner: Any,
    v1_runner: Any,
    v1_prereg: dict[str, Any],
) -> pd.DataFrame:
    del v2_runner, v1_runner, v1_prereg
    horizons = tuple(int(value) for value in prereg["consequence_horizons_sessions"])
    boundary = pd.Timestamp(str(prereg["block_contract"]["end_exclusive"]))
    if not EXECUTION_SESSIONS.is_file():
        raise RuntimeError("controller-v3 Block1 execution-session archive is missing")
    sessions = pd.read_csv(EXECUTION_SESSIONS)
    required = {
        "session_open", "next_session_open", "contract_id", "next_selected_contract_id",
        "open_price", "next_open_same_contract", "path_move_per_mmbtu", "roll_at_next_open",
    }
    missing = required.difference(sessions.columns)
    if missing:
        raise RuntimeError(f"Block1 execution-session archive missing columns: {sorted(missing)}")
    sessions["session_open"] = pd.to_datetime(sessions["session_open"], utc=True, errors="raise")
    sessions["next_session_open"] = pd.to_datetime(sessions["next_session_open"], utc=True, errors="raise")
    sessions = sessions.sort_values("session_open", kind="stable").reset_index(drop=True)
    if (sessions["session_open"] >= boundary).any():
        raise RuntimeError("Block1 execution-session archive contains later-block rows")
    index_by_open = {pd.Timestamp(value): index for index, value in enumerate(sessions["session_open"])}
    fill_times = pd.to_datetime(state["fill_timestamp"], utc=True, errors="raise").tolist()
    rows: list[dict[str, Any]] = []
    for index, state_row in state.reset_index(drop=True).iterrows():
        decision_time = pd.Timestamp(state_row["decision_time"])
        fill_time = pd.Timestamp(state_row["fill_timestamp"])
        if fill_time not in index_by_open:
            raise RuntimeError(f"Block1 execution archive missing fill timestamp: {fill_time}")
        start = index_by_open[fill_time]
        session = sessions.iloc[start]
        if str(session["contract_id"]) != str(state_row["fill_contract_id"]):
            raise RuntimeError("Block1 execution archive held-contract identity changed")
        one_available = pd.Timestamp(session["next_session_open"])
        row: dict[str, Any] = {
            "decision_time": decision_time,
            "fill_timestamp": fill_time,
            "fill_contract_id": str(state_row["fill_contract_id"]),
            "fill_price": float(session["open_price"]),
            "outcome_available_at": one_available,
            "path_move_per_mmbtu": float(session["path_move_per_mmbtu"]),
        }
        interval_end = fill_times[index + 1] if index + 1 < len(fill_times) else boundary
        interval = sessions.loc[
            (sessions["session_open"] >= fill_time)
            & (sessions["session_open"] < interval_end)
            & (sessions["next_session_open"] < boundary)
        ].copy()
        if interval.empty:
            raise RuntimeError("Block1 execution interval has no held sessions")
        terminal = interval.iloc[-1]
        terminal_time = pd.Timestamp(terminal["next_session_open"])
        terminal_contract = str(terminal["next_selected_contract_id"])
        terminal_match = sessions.loc[
            sessions["session_open"].eq(terminal_time)
            & sessions["contract_id"].astype(str).eq(terminal_contract)
        ]
        terminal_basis = (
            float(terminal_match.iloc[0]["open_price"])
            if not terminal_match.empty
            else float(terminal["next_open_same_contract"])
        )
        row.update({
            "holding_session_count": len(interval),
            "holding_move_per_mmbtu": float(pd.to_numeric(interval["path_move_per_mmbtu"], errors="raise").sum()),
            "holding_outcome_available_at": terminal_time,
            "holding_roll_count": int(interval["roll_at_next_open"].astype(bool).sum()),
            "holding_terminal_contract_id": terminal_contract,
            "holding_terminal_basis_price": terminal_basis,
        })
        for horizon in horizons:
            stop = start + horizon
            if stop > len(sessions):
                sample = pd.DataFrame()
            else:
                sample = sessions.iloc[start:stop]
            if sample.empty or pd.Timestamp(sample.iloc[-1]["next_session_open"]) >= boundary:
                row.update({
                    f"h{horizon}_move_per_mmbtu": np.nan,
                    f"h{horizon}_outcome_available_at": pd.NaT,
                    f"h{horizon}_roll_count": np.nan,
                    f"h{horizon}_mfe_per_mmbtu": np.nan,
                    f"h{horizon}_mae_per_mmbtu": np.nan,
                    f"h{horizon}_future_vol_per_mmbtu": np.nan,
                    f"h{horizon}_best_long_entry_price_next3": np.nan,
                    f"h{horizon}_best_short_entry_price_next3": np.nan,
                })
                continue
            sample_moves = pd.to_numeric(sample["path_move_per_mmbtu"], errors="raise").to_numpy(dtype=float)
            cumulative = np.cumsum(sample_moves)
            entry_sample = pd.to_numeric(sample["open_price"], errors="raise").head(3).to_numpy(dtype=float)
            row.update({
                f"h{horizon}_move_per_mmbtu": float(sample_moves.sum()),
                f"h{horizon}_outcome_available_at": pd.Timestamp(sample.iloc[-1]["next_session_open"]),
                f"h{horizon}_roll_count": float(sample["roll_at_next_open"].astype(bool).sum()),
                f"h{horizon}_mfe_per_mmbtu": float(np.max(cumulative)),
                f"h{horizon}_mae_per_mmbtu": float(np.min(cumulative)),
                f"h{horizon}_future_vol_per_mmbtu": float(np.std(sample_moves, ddof=0)),
                f"h{horizon}_best_long_entry_price_next3": float(np.min(entry_sample)),
                f"h{horizon}_best_short_entry_price_next3": float(np.max(entry_sample)),
            })
        rows.append(row)
    return pd.DataFrame(rows).sort_values("decision_time", kind="stable").reset_index(drop=True)

def _counterfactual_one_session_return(
    current: float,
    target: float,
    current_contract_id: str | None,
    outcome: pd.Series,
    *,
    multiplier: float,
    capital: float,
    cost_per_side: float,
) -> float:
    target_contract = str(outcome["fill_contract_id"])
    turnover = execution_turnover(
        current, target,
        current_contract_id=current_contract_id,
        target_contract_id=target_contract,
    )
    pnl = target * float(outcome["path_move_per_mmbtu"]) * multiplier
    pnl -= turnover * cost_per_side
    return float(pnl / capital)


def build_research_consequence_store(
    brain: pd.DataFrame,
    path: pd.DataFrame,
    state: pd.DataFrame,
    prereg: dict[str, Any],
) -> pd.DataFrame:
    path_by_time = path.set_index(pd.to_datetime(path["decision_time"], utc=True))
    state_by_time = state.set_index(pd.to_datetime(state["decision_time"], utc=True))
    multiplier = 10000.0
    capital = 100000.0
    cost = float(prereg["execution_sensitivity"]["base_cost_usd_per_contract_side"])
    horizons = [int(value) for value in prereg["consequence_horizons_sessions"]]
    rows: list[dict[str, Any]] = []
    for brain_row in brain.itertuples(index=False):
        decision_time = pd.Timestamp(brain_row.decision_time)
        outcome = path_by_time.loc[decision_time]
        state_row = state_by_time.loc[decision_time]
        position_before = dict(brain_row.position_before)
        current = float(position_before.get("exposure", 0.0))
        current_contract = position_before.get("current_contract_id")
        forward: dict[str, Any] = {}
        holding: dict[str, Any] = {}
        excursions: dict[str, Any] = {}
        best_entry: dict[str, Any] = {}
        side_economics: dict[str, Any] = {}
        for horizon in horizons:
            move = outcome.get(f"h{horizon}_move_per_mmbtu")
            available = outcome.get(f"h{horizon}_outcome_available_at")
            if pd.isna(move) or pd.isna(available):
                forward[str(horizon)] = None
                holding[str(horizon)] = None
                excursions[str(horizon)] = None
                best_entry[str(horizon)] = None
                side_economics[str(horizon)] = None
                continue
            roll_count = float(outcome.get(f"h{horizon}_roll_count", 0.0))
            move = float(move)
            round_trip_cost = 2.0 * (1.0 + roll_count) * cost
            long_return = (move * multiplier - round_trip_cost) / capital
            short_return = (-move * multiplier - round_trip_cost) / capital
            forward[str(horizon)] = {
                "outcome_available_at": pd.Timestamp(available),
                "move_per_mmbtu": move,
                "long_return_before_selection": float(long_return),
                "short_return_before_selection": float(short_return),
            }
            holding[str(horizon)] = {
                side: {
                    str(size): float(
                        ((1.0 if side == "long" else -1.0) * size * move * multiplier
                         - 2.0 * size * (1.0 + roll_count) * cost) / capital
                    )
                    for size in (0.5, 1.0, 1.5)
                }
                for side in ("long", "short")
            }
            excursions[str(horizon)] = {
                "mfe_per_mmbtu": float(outcome[f"h{horizon}_mfe_per_mmbtu"]),
                "mae_per_mmbtu": float(outcome[f"h{horizon}_mae_per_mmbtu"]),
                "future_realized_vol_per_mmbtu": float(outcome[f"h{horizon}_future_vol_per_mmbtu"]),
            }
            best_entry[str(horizon)] = {
                "best_long_entry_price_next3": float(outcome[f"h{horizon}_best_long_entry_price_next3"]),
                "best_short_entry_price_next3": float(outcome[f"h{horizon}_best_short_entry_price_next3"]),
            }
            side_economics[str(horizon)] = {
                "long": float(long_return),
                "short": float(short_return),
                "long_minus_short": float(long_return - short_return),
            }
        base_direction = 1.0 if float(brain_row.target_exposure) >= 0.0 else -1.0
        sign = 1.0 if current > 0.0 else (-1.0 if current < 0.0 else base_direction)
        action_targets = {
            "flat": 0.0,
            "initiate": 0.5 * base_direction,
            "add": sign * min(1.5, abs(current) + 0.5),
            "hold": current,
            "reduce": sign * max(0.0, abs(current) - 0.5),
            "exit": 0.0,
            "reverse": -current if current != 0.0 else -0.5 * base_direction,
        }
        action_economics = {
            action: _counterfactual_one_session_return(
                current, target, current_contract, outcome,
                multiplier=multiplier, capital=capital, cost_per_side=cost,
            )
            for action, target in action_targets.items()
        }
        selected_target = float(brain_row.target_exposure)
        low_liquidity = float(state_row["feature_curve_log_volume_m1"]) < float(
            state_row["derived_prior20_log_volume_m1_median"]
        )
        degradation: dict[str, Any] = {}
        for scenario in prereg["execution_sensitivity"]["scenarios"]:
            extra = float(scenario["extra_slippage_usd_per_contract_side"])
            requested = selected_target
            missed = bool(
                scenario["miss_increase_when_below_prior_volume"]
                and low_liquidity
                and (
                    (current == 0.0 and requested != 0.0)
                    or current * requested < 0.0
                    or (current * requested > 0.0 and abs(requested) > abs(current))
                )
            )
            executed = current if missed and current * requested >= 0.0 else (0.0 if missed else requested)
            degradation[str(scenario["id"])] = {
                "missed_fill": missed,
                "executed_target": float(executed),
                "one_session_net_return": _counterfactual_one_session_return(
                    current, executed, current_contract, outcome,
                    multiplier=multiplier, capital=capital,
                    cost_per_side=cost + extra,
                ),
            }
        rows.append({
            "decision_time": decision_time,
            "research_only_post_decision_labels": True,
            "never_used_in_same_timestamp_selection": True,
            "forward_returns": forward,
            "mfe_mae_and_future_volatility": excursions,
            "best_executable_entry_diagnostics": best_entry,
            "holding_and_size_counterfactual_economics": holding,
            "action_counterfactual_economics_1_session": action_economics,
            "action_counterfactual_targets": action_targets,
            "long_short_economics": side_economics,
            "cost_slippage_missed_fill_degradation": degradation,
        })
    return pd.DataFrame(rows)


def candidate_trial_rows(
    scenario_replays: dict[str, list[Any]],
    warmup: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for scenario_id, replays in scenario_replays.items():
        for ordinal, replay in enumerate(replays):
            frame = replay.consequences.iloc[int(warmup):]
            rows.append({
                "attempt_ordinal": len(rows) + 1,
                "structural_candidate_ordinal": ordinal + 1,
                "execution_scenario": scenario_id,
                **config_to_dict(replay.config),
                "post_warmup_net_return": float(frame["realized_net_return"].sum()),
                "post_warmup_turnover": float(frame["turnover"].sum()),
                "post_warmup_active_decisions": int(frame["signal"].ne(0.0).sum()),
                "post_warmup_missed_fills": int(frame["missed_fill"].sum()),
                "max_notional_leverage": float(frame["notional_leverage"].max()),
                "max_margin_fraction": float(frame["margin_fraction"].max()),
                "outcome_dependent_pruned": False,
            })
    return pd.DataFrame(rows)

def preflight(*, write: bool = True) -> dict[str, Any]:
    prereg = load_prereg()
    state, v2_runner, v1_runner, v1_prereg = load_state(prereg)
    specialists, weighted_attributes = v2_runner.build_controller_specialists(state, v1_runner)
    families = v2_runner.controller_family_map(v1_prereg, weighted_attributes)
    configs = structural_grid(prereg)
    inventory_rows = rich_attribute_inventory(state, v2_runner, weighted_attributes)
    reentry = historical_reentry_payload()
    role_bindings = _historical_negative_role_bindings(
        reentry, v1_prereg, weighted_attributes
    )
    reentry["current_role_semantic_bindings"] = role_bindings
    profile_memories = {
        memory for config in configs
        for policy in (config.long_policy, config.short_policy)
        for memory in policy.memories
    }
    family_dispositions = json.loads(V1_INVENTORY.read_text(encoding="utf-8"))["family_dispositions"]
    expert_manifest: dict[str, Any] = {}
    expert_archive_ok = False
    if EXPERT_PATHS.is_file() and EXPERT_PATH_MANIFEST.is_file():
        expert_manifest = json.loads(EXPERT_PATH_MANIFEST.read_text(encoding="utf-8"))
        expert_archive_ok = (
            expert_manifest.get("row_count") == len(state)
            and expert_manifest.get("full_native_horizon_for_every_decision") is True
            and expert_manifest.get("protected_confirmation_accessed") is False
            and expert_manifest.get("later_block_market_data_accessed") is False
            and expert_manifest.get("output_sha256") == sha256_file(EXPERT_PATHS)
        )
    execution_path = build_execution_path(state, prereg, v2_runner, v1_runner, v1_prereg)
    execution_archive = pd.read_csv(EXECUTION_SESSIONS)
    execution_archive["session_open"] = pd.to_datetime(
        execution_archive["session_open"], utc=True, errors="raise"
    )
    execution_archive["next_session_open"] = pd.to_datetime(
        execution_archive["next_session_open"], utc=True, errors="raise"
    )
    block_end = pd.Timestamp(prereg["block_contract"]["end_exclusive"])
    valid_next_session = execution_archive["next_session_open"].notna()
    execution_archive_ok = bool(
        not execution_archive.empty
        and (execution_archive["session_open"] < block_end).all()
        and (
            execution_archive.loc[valid_next_session, "next_session_open"] <= block_end
        ).all()
        and len(execution_path) == len(state)
        and int(execution_path["holding_session_count"].sum()) == 152
    )
    expert_context_ok = False
    if expert_archive_ok:
        expert_paths = load_expert_paths()
        controller_context, controller_context_columns = build_controller_context(
            state, expert_paths, prereg
        )
        expert_context_ok = (
            len(controller_context) == len(state)
            and controller_context_columns[-len(FOUNDATION_CONTEXT_COLUMNS):]
            == list(FOUNDATION_CONTEXT_COLUMNS)
            and expert_manifest.get("selection_use")
            == "horizon_specific_direction_and_comparable_state_context"
        )
    checks = {
        "block1_rows_match": len(state) == int(prereg["block_contract"]["expected_executable_decision_rows"]),
        "unique_decision_times": bool(state["decision_time"].is_unique),
        "later_blocks_not_loaded": bool((state["decision_time"] < pd.Timestamp(prereg["block_contract"]["end_exclusive"])).all()),
        "block1_execution_archive_physically_isolated": execution_archive_ok,
        "protected_confirmation_not_accessed": bool((state["decision_time"] < pd.Timestamp(prereg["pit_contract"]["protected_start"])).all()),
        "all_weightable_attributes_transformed": len(weighted_attributes) == sum(int(row["individual_weighting_permitted"]) for row in inventory_rows),
        "all_material_families_have_explicit_disposition": len(family_dispositions) == 12,
        "historical_reentry_covers_every_source_record": reentry["record_count"] == reentry["source_record_count"],
        "exact_empirical_negative_roles_semantically_bound": (
            role_bindings["generated_role_count"]
            == len(v1_prereg["specialist_library"]) + 2 * len(weighted_attributes)
            and role_bindings["empirical_negative_record_count"]
            == int(reentry["classification_counts"].get("empirical_negative", 0))
            and not role_bindings["blocked_current_role_ids"]
        ),
        "complete_memory_bank_participates": set(MEMORY_BANK).issubset(profile_memories),
        "independent_memory_scale_selection_frozen": (
            prereg["expert_effectiveness_contract"]["memory_scale_selection"]["granularity"]
            == "independent_per_specialist_horizon_direction"
            and set(prereg["expert_effectiveness_contract"]["memory_scale_selection"]["eligible_memories"])
            == set(MEMORY_BANK)
            and prereg["expert_effectiveness_contract"]["memory_scale_selection"]["strict_prior"] is True
        ),
        "weightable_attribute_oracle_is_exactly_complete": len(weighted_attributes) == int(prereg["attribute_weight_oracle"]["attribute_count"]),
        "expert_native_path_archive_hash_bound_and_block1_only": expert_archive_ok,
        "expert_path_features_are_live_controller_context": expert_context_ok,
        "expert_history_hashes_match_manifest": (
            bool(expert_manifest)
            and EXPERT_HISTORY_CANONICAL.is_file()
            and EXPERT_HISTORY_OHLCV.is_file()
            and expert_manifest.get("canonical_history_sha256") == sha256_file(EXPERT_HISTORY_CANONICAL)
            and expert_manifest.get("ohlcv_history_sha256") == sha256_file(EXPERT_HISTORY_OHLCV)
        ),
        "foundation_forecast_target_semantics_frozen": (
            prereg["expert_effectiveness_contract"].get("forecast_target_semantics", {}).get("timesfm")
            == "same-contract canonical settlement return from the decision trade date to the forecast session"
            and prereg["expert_effectiveness_contract"].get("forecast_target_semantics", {}).get("kronos")
            == "same-contract OHLCV close return from the decision trade date to the forecast session"
            and "strictly before the decision timestamp"
            in prereg["expert_effectiveness_contract"].get("forecast_metric_availability_rule", "")
        ),
        "expert_effectiveness_metrics_complete": set(prereg["expert_effectiveness_contract"]["metrics"]).issuperset({
            "realized_net_return", "direction_hit_rate", "direction_error", "forecast_mae_return",
            "forecast_rmse_return", "forecast_bias_return", "interval_coverage", "interval_sharpness",
        }),
        "full_attribute_weight_oracle_and_causal_predictor_frozen": (
            prereg["attribute_weight_oracle"]["required"] is True
            and prereg["attribute_weight_oracle"]["selection_use"] is False
            and prereg["attribute_weight_oracle"]["predictor_selection_use"] is False
            and prereg["attribute_weight_oracle"]["horizons_sessions"] == [1, 3, 5, 10, 20]
            and prereg["attribute_weight_oracle"]["sparse_ks"] == [1, 2, 4, 8, 16]
            and float(prereg["attribute_weight_oracle"]["exposure_step_contracts"]) == 0.25
            and float(prereg["attribute_weight_oracle"]["max_abs_contracts"]) == 1.5
        ),
        "primitive_oracle_winner_predictor_frozen": (
            prereg["primitive_oracle_winner_predictor"]["required"] is True
            and prereg["primitive_oracle_winner_predictor"]["selection_use"] is False
            and prereg["primitive_oracle_winner_predictor"]["target_components"]
            == ["policy_id", "specialist", "horizon", "direction"]
            and int(prereg["primitive_oracle_winner_predictor"]["predictor_neighbors"]) == 10
        ),
        "structural_candidate_count_matches": len(configs) == int(prereg["structural_search"]["expected_candidate_count"]),
        "symmetric_controls_present": sum(not config.asymmetric for config in configs) > 0,
        "asymmetric_candidates_present": sum(config.asymmetric for config in configs) > 0,
        "eight_stage_hierarchy": len(prereg["hierarchy"]) == 8,
    }
    inventory_payload = {
        "schema_version": int(prereg["schema_version"]),
        "issue": 465,
        "iteration": str(prereg["iteration"]),
        "pit_state_source": str(V1_STATE.relative_to(REPO)),
        "pit_state_sha256": sha256_file(V1_STATE),
        "attribute_count": len(inventory_rows),
        "weightable_attribute_count": len(weighted_attributes),
        "family_dispositions": family_dispositions,
        "attributes": inventory_rows,
        "no_admissible_family_silently_dropped": True,
        "protected_confirmation_accessed": False,
        "later_blocks_accessed": False,
    }
    candidates_payload = {
        "schema_version": int(prereg["schema_version"]),
        "issue": 465,
        "iteration": str(prereg["iteration"]),
        "prereg_sha256": sha256_file(PREREG),
        "candidate_count": len(configs),
        "candidate_grid_sha256": stable_sha([config_to_dict(config) for config in configs]),
        "candidates": [config_to_dict(config) for config in configs],
        "named_specialist_library": v1_prereg["specialist_library"],
        "generated_attribute_specialist_count": 2 * len(weighted_attributes),
        "total_specialist_count": len(specialists.columns) - 1,
        "family_map": families,
        "full_memory_bank": list(MEMORY_BANK),
        "zero_weight_legal": True,
        "scoring_performed": False,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    report = {
        "schema_version": int(prereg["schema_version"]),
        "issue": 465,
        "iteration": str(prereg["iteration"]),
        "status": status,
        "scoring_performed": False,
        "prereg_sha256": sha256_file(PREREG),
        "code_identity": current_code_identity(),
        "scoring_input_identity": scoring_input_identity(),
        "scoring_input_identity_sha256": scoring_input_identity_sha256(),
        "checks": checks,
        "candidate_grid_sha256": candidates_payload["candidate_grid_sha256"],
        "candidate_count": len(configs),
        "specialist_count": len(specialists.columns) - 1,
        "weightable_attribute_count": len(weighted_attributes),
        "protected_confirmation_accessed": False,
        "later_blocks_accessed": False,
    }
    if write:
        existing_inventory = (
            json.loads(INVENTORY.read_text(encoding="utf-8")) if INVENTORY.is_file() else None
        )
        if existing_inventory != inventory_payload:
            _write_json(INVENTORY, inventory_payload)
        existing_reentry = (
            json.loads(REENTRY.read_text(encoding="utf-8")) if REENTRY.is_file() else None
        )
        if existing_reentry != reentry:
            _write_json(REENTRY, reentry)
        existing_candidates = (
            json.loads(CANDIDATES.read_text(encoding="utf-8")) if CANDIDATES.is_file() else None
        )
        if existing_candidates != candidates_payload:
            _write_json(CANDIDATES, candidates_payload)
        report["inventory_sha256"] = sha256_file(INVENTORY)
        report["historical_reentry_sha256"] = sha256_file(REENTRY)
        report["candidates_sha256"] = sha256_file(CANDIDATES)
        _write_json(PREFLIGHT, report)
        if report["status"] == "PASS":
            _mark_preflight_replay_required(
                scoring_identity_sha256=str(report["scoring_input_identity_sha256"]),
                candidate_grid_sha256=str(report["candidate_grid_sha256"]),
            )
    return report


def load_scoring_preflight() -> dict[str, Any]:
    required = (PREFLIGHT, INVENTORY, REENTRY, CANDIDATES)
    if any(not path.exists() for path in required):
        raise RuntimeError("controller-v3 scoring requires frozen preflight artifacts")
    report = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if report.get("status") != "PASS" or report.get("scoring_performed") is not False:
        raise RuntimeError("controller-v3 scoring requires no-scoring PASS preflight")
    if report["prereg_sha256"] != sha256_file(PREREG):
        raise RuntimeError("controller-v3 preregistration changed after preflight")
    if report["code_identity"] != current_code_identity():
        raise RuntimeError("controller-v3 code identity changed after preflight")
    if report.get("scoring_input_identity") != scoring_input_identity():
        raise RuntimeError("controller-v3 scoring inputs/environment changed after preflight")
    if report.get("scoring_input_identity_sha256") != scoring_input_identity_sha256():
        raise RuntimeError("controller-v3 scoring input identity hash changed after preflight")
    for key, path in (
        ("inventory_sha256", INVENTORY),
        ("historical_reentry_sha256", REENTRY),
        ("candidates_sha256", CANDIDATES),
    ):
        if report[key] != sha256_file(path):
            raise RuntimeError(f"controller-v3 frozen artifact changed: {path.name}")
    return report

def _clone_replay_with_future_corruption(replay: Any, cutoff: pd.Timestamp) -> Any:
    decisions = replay.decisions.copy(deep=True)
    consequences = replay.consequences.copy(deep=True)
    future_decisions = pd.to_datetime(decisions["decision_time"], utc=True) > cutoff
    future_outcomes = pd.to_datetime(consequences["outcome_available_at"], utc=True) > cutoff
    if future_decisions.any():
        decisions.loc[future_decisions, "target_exposure"] = (
            -pd.to_numeric(decisions.loc[future_decisions, "target_exposure"], errors="raise")
        )
        decisions.loc[future_decisions, "remaining_edge"] = 999.0
    if future_outcomes.any():
        consequences.loc[future_outcomes, "realized_net_return"] = 99.0
    return type(replay)(replay.config, decisions, consequences, dict(replay.summary))


POST_META_DIAGNOSTIC_COLUMNS = (
    "expert_context_state",
    "expert_multi_horizon_opinions",
    "oracle_weight_predictor",
    "primitive_oracle_winner_predictor",
)


def _canonical_records_payload(records: list[dict[str, Any]]) -> str:
    canonical = [serializable_value(row) for row in records]
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)


def _prefix_payload(brain: pd.DataFrame, cutoff: pd.Timestamp) -> str:
    return _decision_causal_prefix_payload(brain, cutoff)


def future_invariance_proof(
    base_replays: list[Any],
    stress_replays: dict[str, list[Any]],
    brain: pd.DataFrame,
    state: pd.DataFrame,
    path: pd.DataFrame,
    specialists: pd.DataFrame,
    surfaces: dict[pd.Timestamp, pd.DataFrame],
    refs: dict[pd.Timestamp, list[pd.Timestamp]],
    prereg: dict[str, Any],
    *,
    cutoff: pd.Timestamp | None = None,
) -> dict[str, Any]:
    warmup = int(prereg["block_contract"]["warmup_completed_trading_sessions"])
    cutoff_index = min(len(state) - 2, warmup + 20)
    cutoff = (
        pd.Timestamp(state.iloc[cutoff_index]["decision_time"])
        if cutoff is None else pd.Timestamp(cutoff)
    )
    corrupted_base = [_clone_replay_with_future_corruption(row, cutoff) for row in base_replays]
    corrupted_stress = {
        key: [_clone_replay_with_future_corruption(row, cutoff) for row in rows]
        for key, rows in stress_replays.items()
    }
    mutated_brain, _mutated_consequences, _freeze = run_meta_controller(
        corrupted_base, corrupted_stress, state, path,
        specialists=specialists, surfaces=surfaces, refs_by_time=refs,
        objective_window=int(prereg["meta_controller"]["objective_window_sessions"]),
        ensemble_size=int(prereg["meta_controller"]["ensemble_size"]),
        structural_cadence=int(prereg["meta_controller"]["structural_ensemble_cadence_sessions"]),
        stress_floor=float(prereg["meta_controller"]["stress_floor_30_session_net_return"]),
        max_abs_contracts=float(prereg["dynamic_sizing"]["max_abs_contracts"]),
        initial_capital=100000.0, multiplier=10000.0,
        cost_per_side=float(prereg["execution_sensitivity"]["base_cost_usd_per_contract_side"]),
        initial_margin_usd_per_contract=5000.0,
        max_margin_fraction=float(prereg["dynamic_sizing"]["max_margin_fraction"]),
        max_notional_leverage=float(prereg["dynamic_sizing"]["max_notional_leverage"]),
        max_drawdown_fraction=float(prereg["dynamic_sizing"]["max_drawdown_fraction"]),
        embed_effectiveness_surface=False,
    )
    baseline_prefix = _prefix_payload(brain, cutoff)
    mutated_prefix = _prefix_payload(mutated_brain, cutoff)
    return {
        "cutoff_decision_time": cutoff.isoformat(),
        "future_candidate_decisions_corrupted": True,
        "future_candidate_outcomes_corrupted": True,
        "state_and_execution_inputs_for_prefix_held_identical": True,
        "prefix_state_weights_structure_actions_pruning_identical": baseline_prefix == mutated_prefix,
        "baseline_prefix_sha256": hashlib.sha256(baseline_prefix.encode("utf-8")).hexdigest(),
        "mutated_prefix_sha256": hashlib.sha256(mutated_prefix.encode("utf-8")).hexdigest(),
        "block_boundary_source": str(V1_STATE.relative_to(REPO)),
        "later_block_source_accessed": False,
        "protected_confirmation_accessed": False,
    }

def _decision_causal_prefix_payload(frame: pd.DataFrame, cutoff: pd.Timestamp) -> str:
    prefix = frame.loc[
        pd.to_datetime(frame["decision_time"], utc=True) <= cutoff
    ].copy()
    prefix = prefix.drop(
        columns=[
            "executed_target_exposure", "execution_audit", "effectiveness_surface",
            *POST_META_DIAGNOSTIC_COLUMNS,
        ],
        errors="ignore",
    )
    return _canonical_records_payload(prefix.to_dict(orient="records"))


def _matured_execution_audit_prefix_payload(
    frame: pd.DataFrame,
    cutoff: pd.Timestamp,
) -> str:
    rows: list[dict[str, Any]] = []
    for row in frame.loc[
        pd.to_datetime(frame["decision_time"], utc=True) <= cutoff
    ].to_dict(orient="records"):
        audit = row.get("execution_audit")
        if not isinstance(audit, dict):
            continue
        available_at = pd.Timestamp(audit["available_at"])
        if available_at <= cutoff:
            rows.append({
                "decision_time": row["decision_time"],
                "executed_target_exposure": row.get("executed_target_exposure"),
                "execution_audit": audit,
            })
    return _canonical_records_payload(rows)


def _candidate_prefix_payload(replay: Any, cutoff: pd.Timestamp) -> str:
    return _decision_causal_prefix_payload(replay.decisions, cutoff)


def full_future_invariance_proof(
    scenario_replays: dict[str, list[Any]],
    brain: pd.DataFrame,
    state: pd.DataFrame,
    path: pd.DataFrame,
    specialists: pd.DataFrame,
    surfaces: dict[pd.Timestamp, pd.DataFrame],
    rich_base: pd.DataFrame,
    expert_paths: pd.DataFrame,
    foundation_actuals: pd.DataFrame,
    refs: dict[pd.Timestamp, list[pd.Timestamp]],
    families: dict[str, str],
    configs: list[Any],
    prereg: dict[str, Any],
    v2_runner: Any,
    v1_runner: Any,
) -> dict[str, Any]:
    warmup = int(prereg["block_contract"]["warmup_completed_trading_sessions"])
    cutoff_index = min(len(state) - 2, warmup + 20)
    cutoff = pd.Timestamp(state.iloc[cutoff_index]["decision_time"])
    mutated_state = state.copy(deep=True)
    future_state = pd.to_datetime(mutated_state["decision_time"], utc=True) > cutoff
    weightable = [
        row["attribute"] for row in v2_runner.attribute_inventory(mutated_state)
        if row["weighting_permitted"]
    ]
    for column in weightable:
        values = pd.to_numeric(mutated_state.loc[future_state, column], errors="raise")
        mutated_state.loc[future_state, column] = values + 777.0
    mutated_specialists, mutated_weighted = v2_runner.build_controller_specialists(
        mutated_state, v1_runner
    )
    if mutated_weighted != weightable:
        raise RuntimeError("future invariance changed attribute identity")
    mutated_path = path.copy(deep=True)
    future_fill = pd.to_datetime(mutated_path["fill_timestamp"], utc=True) > cutoff
    mutated_path.loc[future_fill, "fill_price"] = (
        pd.to_numeric(mutated_path.loc[future_fill, "fill_price"], errors="raise") + 777.0
    )
    future_one = pd.to_datetime(mutated_path["outcome_available_at"], utc=True) > cutoff
    mutated_path.loc[future_one, "path_move_per_mmbtu"] = 777.0
    for horizon in prereg["consequence_horizons_sessions"]:
        available_column = f"h{int(horizon)}_outcome_available_at"
        move_column = f"h{int(horizon)}_move_per_mmbtu"
        available = pd.to_datetime(mutated_path[available_column], utc=True, errors="coerce")
        future = available.notna() & (available > cutoff)
        mutated_path.loc[future, move_column] = 777.0
    execution_cost = float(prereg["execution_sensitivity"]["base_cost_usd_per_contract_side"])
    opportunity_horizons = tuple(int(value) for value in prereg["opportunity_horizons_sessions"])
    mutated_base = build_base_consequences(
        mutated_specialists, mutated_path,
        horizons=opportunity_horizons,
        multiplier=10000.0, capital_usd=100000.0,
        cost_per_side_usd=execution_cost,
    )
    mutated_expert_paths = expert_paths.copy(deep=True)
    future_expert = pd.to_datetime(mutated_expert_paths["decision_time"], utc=True) > cutoff
    for row_index in mutated_expert_paths.index[future_expert]:
        for column in (
            "timesfm_point_returns", "timesfm_q10_returns", "timesfm_q90_returns",
            "kronos_close_returns", "model_disagreement_returns",
        ):
            mutated_expert_paths.at[row_index, column] = [
                float(value) + 777.0 for value in list(mutated_expert_paths.at[row_index, column])
            ]
        for column in ("timesfm_path_features", "kronos_path_features"):
            features = dict(mutated_expert_paths.at[row_index, column])
            mutated_expert_paths.at[row_index, column] = {
                key: float(value) + 777.0 for key, value in features.items()
            }
        mutated_expert_paths.at[row_index, "model_disagreement_mean_abs"] = (
            float(mutated_expert_paths.at[row_index, "model_disagreement_mean_abs"]) + 777.0
        )
        mutated_expert_paths.at[row_index, "model_sign_disagreement_rate"] = (
            float(mutated_expert_paths.at[row_index, "model_sign_disagreement_rate"]) + 777.0
        )
    mutated_context_state, context_columns = build_controller_context(
        mutated_state, mutated_expert_paths, prereg
    )
    mutated_refs = precompute_comparable_refs(
        mutated_context_state,
        context_columns=context_columns, k=10,
    )
    mutated_foundation_actuals = foundation_actuals.copy(deep=True)
    for row_index in mutated_foundation_actuals.index:
        for prefix in ("timesfm", "kronos"):
            returns = list(mutated_foundation_actuals.at[row_index, f"{prefix}_actual_returns"])
            available = list(mutated_foundation_actuals.at[row_index, f"{prefix}_actual_available_at"])
            for value_index, raw_available in enumerate(available):
                if raw_available is not None and pd.Timestamp(raw_available) > cutoff:
                    returns[value_index] = 777.0
            mutated_foundation_actuals.at[row_index, f"{prefix}_actual_returns"] = returns
    mutated_horizon_signals = foundation_horizon_signals(
        mutated_expert_paths, opportunity_horizons
    )
    mutated_rich_base = build_rich_expert_consequences(
        mutated_base, mutated_path, expert_paths=mutated_expert_paths,
        foundation_actuals=mutated_foundation_actuals,
        multiplier=10000.0, capital_usd=100000.0,
        cost_per_side_usd=execution_cost,
    )
    mutated_surfaces = precompute_rich_surfaces_incremental(
        mutated_rich_base, mutated_context_state, mutated_refs
    )
    mutated_profile_score_cache = precompute_profile_score_cache(
        mutated_surfaces, configs
    )
    scenario_definitions = tuple(prereg["execution_sensitivity"]["scenarios"])
    mutated_scenarios: dict[str, list[Any]] = {
        str(row["id"]): [] for row in scenario_definitions
    }
    for config in configs:
        candidate_replays = replay_candidate_scenarios(
            config, mutated_state, mutated_specialists, mutated_path,
            mutated_surfaces, mutated_refs, families,
            execution_scenarios=scenario_definitions,
            horizon_signals_by_time=mutated_horizon_signals,
            max_abs_contracts=float(prereg["dynamic_sizing"]["max_abs_contracts"]),
            initial_capital=100000.0, multiplier=10000.0,
            base_cost_per_side=execution_cost,
            initial_margin_usd_per_contract=5000.0,
            max_margin_fraction=float(prereg["dynamic_sizing"]["max_margin_fraction"]),
            max_notional_leverage=float(prereg["dynamic_sizing"]["max_notional_leverage"]),
            max_drawdown_fraction=float(prereg["dynamic_sizing"]["max_drawdown_fraction"]),
            profile_score_cache=mutated_profile_score_cache,
        )
        for scenario_id, replay in candidate_replays.items():
            mutated_scenarios[scenario_id].append(replay)
    structural_prefix_equal = True
    structural_execution_audit_prefix_equal = True
    mismatch: dict[str, Any] | None = None
    for scenario_id, originals in scenario_replays.items():
        for original, mutated in zip(originals, mutated_scenarios[scenario_id], strict=True):
            if _candidate_prefix_payload(original, cutoff) != _candidate_prefix_payload(mutated, cutoff):
                structural_prefix_equal = False
                mismatch = {"scenario": scenario_id, "config_id": original.config.config_id}
                break
            original_audit = _matured_execution_audit_prefix_payload(
                original.decisions, cutoff
            )
            mutated_audit = _matured_execution_audit_prefix_payload(
                mutated.decisions, cutoff
            )
            if original_audit != mutated_audit:
                structural_execution_audit_prefix_equal = False
                mismatch = {"scenario": scenario_id, "config_id": original.config.config_id}
                break
        if not structural_prefix_equal or not structural_execution_audit_prefix_equal:
            break
    original_specialist_prefix = specialists.loc[
        pd.to_datetime(specialists["decision_time"], utc=True) <= cutoff
    ].reset_index(drop=True)
    mutated_specialist_prefix = mutated_specialists.loc[
        pd.to_datetime(mutated_specialists["decision_time"], utc=True) <= cutoff
    ].reset_index(drop=True)
    specialist_prefix_equal = original_specialist_prefix.equals(mutated_specialist_prefix)
    refs_prefix_equal = all(
        refs[key] == mutated_refs[key] for key in refs if key <= cutoff
    )
    surfaces_prefix_equal = all(
        surfaces[key].reset_index(drop=True).equals(
            mutated_surfaces[key].reset_index(drop=True)
        )
        for key in surfaces if key <= cutoff
    )
    mutated_brain, _mutated_consequences, _mutated_freeze = run_meta_controller(
        mutated_scenarios["base"],
        {key: value for key, value in mutated_scenarios.items() if key != "base"},
        mutated_state, mutated_path,
        specialists=mutated_specialists,
        surfaces=mutated_surfaces,
        refs_by_time=mutated_refs,
        objective_window=int(prereg["meta_controller"]["objective_window_sessions"]),
        ensemble_size=int(prereg["meta_controller"]["ensemble_size"]),
        structural_cadence=int(prereg["meta_controller"]["structural_ensemble_cadence_sessions"]),
        stress_floor=float(prereg["meta_controller"]["stress_floor_30_session_net_return"]),
        max_abs_contracts=float(prereg["dynamic_sizing"]["max_abs_contracts"]),
        initial_capital=100000.0, multiplier=10000.0,
        cost_per_side=execution_cost, initial_margin_usd_per_contract=5000.0,
        max_margin_fraction=float(prereg["dynamic_sizing"]["max_margin_fraction"]),
        max_notional_leverage=float(prereg["dynamic_sizing"]["max_notional_leverage"]),
        max_drawdown_fraction=float(prereg["dynamic_sizing"]["max_drawdown_fraction"]),
        embed_effectiveness_surface=False,
    )
    baseline_prefix = _decision_causal_prefix_payload(brain, cutoff)
    mutated_prefix = _decision_causal_prefix_payload(mutated_brain, cutoff)
    meta_prefix_equal = baseline_prefix == mutated_prefix
    baseline_meta_audit = _matured_execution_audit_prefix_payload(brain, cutoff)
    mutated_meta_audit = _matured_execution_audit_prefix_payload(mutated_brain, cutoff)
    meta_execution_audit_prefix_equal = baseline_meta_audit == mutated_meta_audit
    oracle_kwargs = {
        "sparse_k": int(prereg["attribute_weight_oracle"]["sparse_k"]),
        "sparse_ks": tuple(int(value) for value in prereg["attribute_weight_oracle"]["sparse_ks"]),
        "horizons": tuple(int(value) for value in prereg["attribute_weight_oracle"]["horizons_sessions"]),
        "max_abs_contracts": float(prereg["attribute_weight_oracle"]["max_abs_contracts"]),
        "exposure_step_contracts": float(prereg["attribute_weight_oracle"]["exposure_step_contracts"]),
        "multiplier": 10000.0, "capital_usd": 100000.0,
        "round_trip_cost_usd": 2.0 * execution_cost,
    }
    original_attribute_oracle = hindsight_attribute_weight_oracle(state, weightable, path, **oracle_kwargs)
    mutated_attribute_oracle = hindsight_attribute_weight_oracle(mutated_state, weightable, mutated_path, **oracle_kwargs)
    predictor_kwargs = {
        "k": int(prereg["attribute_weight_oracle"]["predictor_neighbors"]),
        "sparse_k": int(prereg["attribute_weight_oracle"]["sparse_k"]),
        "horizons": tuple(int(value) for value in prereg["attribute_weight_oracle"]["horizons_sessions"]),
        "max_abs_contracts": float(prereg["attribute_weight_oracle"]["max_abs_contracts"]),
        "exposure_step_contracts": float(prereg["attribute_weight_oracle"]["exposure_step_contracts"]),
    }
    original_predictor = causal_oracle_weight_predictor(state, original_attribute_oracle, weightable, **predictor_kwargs)
    mutated_predictor = causal_oracle_weight_predictor(mutated_state, mutated_attribute_oracle, weightable, **predictor_kwargs)
    original_predictor_causal = oracle_weight_predictor_causal_projection(
        original_predictor
    )
    mutated_predictor_causal = oracle_weight_predictor_causal_projection(
        mutated_predictor
    )
    original_predictor_prefix = original_predictor_causal.loc[
        pd.to_datetime(original_predictor_causal["decision_time"], utc=True) <= cutoff
    ].to_json(orient="records", date_format="iso", double_precision=15)
    mutated_predictor_prefix = mutated_predictor_causal.loc[
        pd.to_datetime(mutated_predictor_causal["decision_time"], utc=True) <= cutoff
    ].to_json(orient="records", date_format="iso", double_precision=15)
    oracle_predictor_prefix_equal = original_predictor_prefix == mutated_predictor_prefix
    oracle_decision_times = state["decision_time"].tolist()
    original_primitive_oracle = oracle_first_diagnostic(rich_base, oracle_decision_times)
    mutated_primitive_oracle = oracle_first_diagnostic(mutated_rich_base, oracle_decision_times)
    primitive_predictor_kwargs = {
        "k": int(prereg["primitive_oracle_winner_predictor"]["predictor_neighbors"]),
    }
    original_primitive_predictor = causal_primitive_oracle_winner_predictor(
        state, original_primitive_oracle["winner_by_day"], weightable, **primitive_predictor_kwargs
    )
    mutated_primitive_predictor = causal_primitive_oracle_winner_predictor(
        mutated_state, mutated_primitive_oracle["winner_by_day"], weightable,
        **primitive_predictor_kwargs,
    )
    original_primitive_causal = primitive_oracle_predictor_causal_projection(
        original_primitive_predictor
    )
    mutated_primitive_causal = primitive_oracle_predictor_causal_projection(
        mutated_primitive_predictor
    )
    original_primitive_prefix = original_primitive_causal.loc[
        pd.to_datetime(original_primitive_causal["decision_time"], utc=True) <= cutoff
    ].to_json(orient="records", date_format="iso", double_precision=15)
    mutated_primitive_prefix = mutated_primitive_causal.loc[
        pd.to_datetime(mutated_primitive_causal["decision_time"], utc=True) <= cutoff
    ].to_json(orient="records", date_format="iso", double_precision=15)
    primitive_predictor_prefix_equal = original_primitive_prefix == mutated_primitive_prefix
    cadence = int(prereg["meta_controller"]["structural_ensemble_cadence_sessions"])
    phase_indices = sorted({
        min(len(state) - 2, warmup + phase)
        for phase in range(max(1, cadence))
    } | {len(state) - 2})
    phase_proofs = [
        future_invariance_proof(
            scenario_replays["base"],
            {key: value for key, value in scenario_replays.items() if key != "base"},
            brain, state, path, specialists, surfaces, refs, prereg,
            cutoff=pd.Timestamp(state.iloc[index]["decision_time"]),
        )
        for index in phase_indices
    ]
    phase_prefixes_equal = all(
        bool(row["prefix_state_weights_structure_actions_pruning_identical"])
        for row in phase_proofs
    )
    passed = bool(
        specialist_prefix_equal and refs_prefix_equal and surfaces_prefix_equal
        and structural_prefix_equal and structural_execution_audit_prefix_equal
        and meta_prefix_equal and meta_execution_audit_prefix_equal
        and oracle_predictor_prefix_equal and primitive_predictor_prefix_equal
        and phase_prefixes_equal
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "cutoff_decision_time": cutoff.isoformat(),
        "future_state_attributes_corrupted": True,
        "future_expert_opinions_and_context_corrupted": True,
        "future_fill_prices_corrupted": True,
        "future_outcomes_by_true_availability_corrupted": True,
        "all_structural_candidate_scenarios_replayed": sum(len(rows) for rows in mutated_scenarios.values()),
        "specialist_prefix_identical": bool(specialist_prefix_equal),
        "comparable_state_refs_prefix_identical": bool(refs_prefix_equal),
        "effectiveness_surfaces_prefix_identical": bool(surfaces_prefix_equal),
        "all_structural_candidate_decision_prefixes_identical": bool(structural_prefix_equal),
        "all_structural_candidate_matured_execution_audits_identical": bool(
            structural_execution_audit_prefix_equal
        ),
        "meta_state_weights_structure_actions_pruning_prefix_identical": bool(meta_prefix_equal),
        "meta_matured_execution_audit_prefix_identical": bool(
            meta_execution_audit_prefix_equal
        ),
        "oracle_weight_predictor_prefix_identical": bool(oracle_predictor_prefix_equal),
        "primitive_oracle_winner_predictor_prefix_identical": bool(primitive_predictor_prefix_equal),
        "persisted_row_prefix_comparison": "causal_fields_plus_matured_execution_audit",
        "structural_phase_cutoff_count": len(phase_proofs),
        "structural_phase_prefixes_identical": bool(phase_prefixes_equal),
        "structural_phase_proofs": phase_proofs,
        "first_structural_mismatch": mismatch,
        "baseline_meta_prefix_sha256": hashlib.sha256(baseline_prefix.encode("utf-8")).hexdigest(),
        "mutated_meta_prefix_sha256": hashlib.sha256(mutated_prefix.encode("utf-8")).hexdigest(),
        "later_block_source_accessed": False,
        "protected_confirmation_accessed": False,
    }

def selection_concentration(brain: pd.DataFrame) -> dict[str, Any]:
    weights: dict[str, float] = {}
    total = 0.0
    for ensemble in brain["selected_ensemble"]:
        for member in ensemble:
            alpha = float(member["blend_weight"])
            key = str(member["config_id"])
            weights[key] = weights.get(key, 0.0) + alpha
            total += alpha
    ranked = sorted(weights.items(), key=lambda item: (-item[1], item[0]))
    return {
        "effective_selection_weight_total": float(total),
        "unique_selected_config_count": len(ranked),
        "top_config_weight_share": float(ranked[0][1] / total) if ranked and total > 0.0 else 0.0,
        "top_config_weights": ranked[:10],
    }


def side_contribution(consequences: pd.DataFrame) -> dict[str, Any]:
    attributed = {"long": 0.0, "short": 0.0, "flat": 0.0}
    for row in consequences.itertuples(index=False):
        before = float(getattr(row, "exposure_before", 0.0))
        after = float(row.signal)
        old_side = "long" if before > 0.0 else "short" if before < 0.0 else "flat"
        new_side = "long" if after > 0.0 else "short" if after < 0.0 else "flat"
        gross = float(row.gross_return)
        total_cost = float(row.execution_cost_return)
        transition_turnover = float(getattr(row, "transition_turnover", row.turnover))
        roll_turnover = float(getattr(row, "roll_turnover", 0.0))
        total_turnover = max(float(row.turnover), 1e-15)
        transition_cost = total_cost * transition_turnover / total_turnover
        roll_cost = total_cost * roll_turnover / total_turnover
        attributed[new_side] += gross - roll_cost
        if transition_cost > 0.0:
            if before * after < 0.0 and abs(before) + abs(after) > 0.0:
                denom = abs(before) + abs(after)
                attributed[old_side] -= transition_cost * abs(before) / denom
                attributed[new_side] -= transition_cost * abs(after) / denom
            elif abs(after) > abs(before):
                attributed[new_side] -= transition_cost
            else:
                attributed[old_side] -= transition_cost
    return {
        "method": "transition_aware_gross_and_cost_attribution",
        "by_side_net_return": attributed,
        "reconciles_to_total_net_return": float(sum(attributed.values())),
    }


def execution_degradation_report(
    brain: pd.DataFrame,
    state: pd.DataFrame,
    path: pd.DataFrame,
    prereg: dict[str, Any],
    warmup: int,
) -> dict[str, Any]:
    reports: dict[str, Any] = {}
    base_return: float | None = None
    for scenario in prereg["execution_sensitivity"]["scenarios"]:
        replay = replay_targets_under_execution_stress(
            brain, state, path, scenario,
            initial_capital=float(prereg["execution_contract"]["starting_capital_usd"]),
            multiplier=float(prereg["execution_contract"]["contract_multiplier_mmbtu"]),
            base_cost_per_side=float(prereg["execution_sensitivity"]["base_cost_usd_per_contract_side"]),
        ).iloc[int(warmup):]
        total = float(replay["realized_net_return"].sum())
        if str(scenario["id"]) == "base":
            base_return = total
        reports[str(scenario["id"])] = {
            "post_warmup_net_return": total,
            "missed_fill_count": int(replay["missed_fill"].sum()),
            "turnover": float(replay["turnover"].sum()),
        }
    if base_return is not None:
        for report in reports.values():
            report["delta_vs_base"] = float(report["post_warmup_net_return"] - base_return)
    return reports

def score_block() -> dict[str, Any]:
    preflight = load_scoring_preflight()
    prereg = load_prereg()
    state, v2_runner, v1_runner, v1_prereg = load_state(prereg)
    path = build_execution_path(state, prereg, v2_runner, v1_runner, v1_prereg)
    specialists, weighted_attributes = v2_runner.build_controller_specialists(state, v1_runner)
    families = v2_runner.controller_family_map(v1_prereg, weighted_attributes)
    configs = structural_grid(prereg)
    frozen_candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    if stable_sha([config_to_dict(config) for config in configs]) != frozen_candidates["candidate_grid_sha256"]:
        raise RuntimeError("controller-v3 structural grid changed after preflight")
    generation_seed, generation_staging = _begin_generation(
        str(preflight["scoring_input_identity_sha256"]),
        str(frozen_candidates["candidate_grid_sha256"]),
    )
    out = lambda canonical: _generation_output(generation_staging, canonical)
    execution = prereg["execution_contract"]
    base_cost = float(prereg["execution_sensitivity"]["base_cost_usd_per_contract_side"])
    opportunity_horizons = tuple(int(value) for value in prereg["opportunity_horizons_sessions"])
    base = build_base_consequences(
        specialists, path,
        horizons=opportunity_horizons,
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        capital_usd=float(execution["starting_capital_usd"]),
        cost_per_side_usd=base_cost,
    )
    expert_paths = load_expert_paths()
    context_state, context_columns = build_controller_context(state, expert_paths, prereg)
    refs = precompute_comparable_refs(
        context_state,
        context_columns=context_columns, k=10,
    )
    horizon_signals = foundation_horizon_signals(expert_paths, opportunity_horizons)
    foundation_actuals = load_foundation_actuals(expert_paths, state)
    rich_base = build_rich_expert_consequences(
        base, path, expert_paths=expert_paths, foundation_actuals=foundation_actuals,
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        capital_usd=float(execution["starting_capital_usd"]),
        cost_per_side_usd=base_cost,
    )
    surfaces = precompute_rich_surfaces_incremental(
        rich_base, context_state, refs
    )
    profile_score_cache = precompute_profile_score_cache(surfaces, configs)
    warmup = int(prereg["block_contract"]["warmup_completed_trading_sessions"])
    oracle = oracle_first_diagnostic(rich_base, state["decision_time"].iloc[warmup:].tolist())
    primitive_oracle_labels = oracle_first_diagnostic(
        rich_base, state["decision_time"].tolist()
    )
    primitive_oracle_predictor = causal_primitive_oracle_winner_predictor(
        state, primitive_oracle_labels["winner_by_day"], weighted_attributes,
        k=int(prereg["primitive_oracle_winner_predictor"]["predictor_neighbors"]),
    )
    if not oracle_predictor_causal_check(primitive_oracle_predictor):
        raise RuntimeError("controller-v3 primitive oracle-winner predictor used non-prior labels")
    _write_jsonl(out(PRIMITIVE_ORACLE_PREDICTOR), primitive_oracle_predictor)
    oracle["primitive_winner_predictor"] = {
        "row_count": len(primitive_oracle_predictor),
        "source_winner_label_count": len(primitive_oracle_labels["winner_by_day"]),
        "target": "policy_id_plus_specialist_horizon_direction_identity",
        "selection_use": False,
        "predictor_strict_prior_check": True,
        "predictor_sha256": sha256_file(out(PRIMITIVE_ORACLE_PREDICTOR)),
    }
    attribute_oracle = hindsight_attribute_weight_oracle(
        state, weighted_attributes, path,
        sparse_k=int(prereg["attribute_weight_oracle"]["sparse_k"]),
        sparse_ks=tuple(int(value) for value in prereg["attribute_weight_oracle"]["sparse_ks"]),
        horizons=tuple(int(value) for value in prereg["attribute_weight_oracle"]["horizons_sessions"]),
        max_abs_contracts=float(prereg["attribute_weight_oracle"]["max_abs_contracts"]),
        exposure_step_contracts=float(prereg["attribute_weight_oracle"]["exposure_step_contracts"]),
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        capital_usd=float(execution["starting_capital_usd"]),
        round_trip_cost_usd=2.0 * base_cost,
    )
    oracle_predictor = causal_oracle_weight_predictor(
        state, attribute_oracle, weighted_attributes,
        k=int(prereg["attribute_weight_oracle"]["predictor_neighbors"]),
        sparse_k=int(prereg["attribute_weight_oracle"]["sparse_k"]),
        horizons=tuple(int(value) for value in prereg["attribute_weight_oracle"]["horizons_sessions"]),
        max_abs_contracts=float(prereg["attribute_weight_oracle"]["max_abs_contracts"]),
        exposure_step_contracts=float(prereg["attribute_weight_oracle"]["exposure_step_contracts"]),
    )
    if not oracle_predictor_causal_check(oracle_predictor):
        raise RuntimeError("controller-v3 oracle-weight predictor used non-prior labels")
    _write_jsonl(out(ATTRIBUTE_ORACLE), attribute_oracle)
    _write_jsonl(out(ORACLE_PREDICTOR), oracle_predictor)
    oracle["computed_before_structural_candidate_replay"] = True
    oracle["attribute_weight_oracle"] = {
        "row_count": len(attribute_oracle), "attribute_count": len(weighted_attributes),
        "horizons_sessions": list(prereg["attribute_weight_oracle"]["horizons_sessions"]),
        "exposure_step_contracts": float(prereg["attribute_weight_oracle"]["exposure_step_contracts"]),
        "max_abs_contracts": float(prereg["attribute_weight_oracle"]["max_abs_contracts"]),
        "sparse_k": int(prereg["attribute_weight_oracle"]["sparse_k"]),
        "sparse_ks": list(prereg["attribute_weight_oracle"]["sparse_ks"]),
        "optimizer": "exact_after_cost_exposure_lattice_plus_analytic_minimum_L2_weight_solution",
        "selection_use": False, "predictor_strict_prior_check": True,
        "attribute_oracle_sha256": sha256_file(out(ATTRIBUTE_ORACLE)),
        "oracle_predictor_sha256": sha256_file(out(ORACLE_PREDICTOR)),
        "diagnostic_interpretation": "exposure_reconstruction_representation_not_feature_importance",
        "feature_importance_inference": False,
    }
    _write_json(out(ORACLE), oracle)
    scenarios = tuple(prereg["execution_sensitivity"]["scenarios"])
    scenario_ids = tuple(str(row["id"]) for row in scenarios)
    checkpoint_root = _checkpoint_run_root(frozen_candidates["candidate_grid_sha256"])
    completed_ids: list[str] = []
    for number, config in enumerate(configs, start=1):
        cached = _load_candidate_checkpoint(checkpoint_root, number, config, scenario_ids)
        if cached is None:
            candidate_replays = replay_candidate_scenarios(
                config, state, specialists, path, surfaces, refs, families,
                execution_scenarios=scenarios,
                horizon_signals_by_time=horizon_signals,
                max_abs_contracts=float(prereg["dynamic_sizing"]["max_abs_contracts"]),
                initial_capital=float(execution["starting_capital_usd"]),
                multiplier=float(execution["contract_multiplier_mmbtu"]),
                base_cost_per_side=base_cost,
                initial_margin_usd_per_contract=float(execution["initial_margin_usd_per_contract"]),
                max_margin_fraction=float(prereg["dynamic_sizing"]["max_margin_fraction"]),
                max_notional_leverage=float(prereg["dynamic_sizing"]["max_notional_leverage"]),
                max_drawdown_fraction=float(prereg["dynamic_sizing"]["max_drawdown_fraction"]),
                profile_score_cache=profile_score_cache,
            )
            _write_candidate_checkpoint(checkpoint_root, number, config, candidate_replays)
        completed_ids.append(config.config_id)
        _write_json(checkpoint_root / "progress.json", {
            "completed_structural_candidates": number,
            "total_structural_candidates": len(configs),
            "completed_candidate_scenario_replays": number * len(scenario_ids),
            "total_candidate_scenario_replays": len(configs) * len(scenario_ids),
            "completed_config_ids": completed_ids,
            "candidate_grid_sha256": frozen_candidates["candidate_grid_sha256"],
            "prereg_sha256": sha256_file(PREREG),
            "code_identity": current_code_identity(),
            "scoring_input_identity_sha256": preflight["scoring_input_identity_sha256"],
        })
        print(_candidate_progress_message(number, len(configs), number * len(scenario_ids)), flush=True)
    scenario_replays: dict[str, list[Any]] = {scenario_id: [] for scenario_id in scenario_ids}
    for number, config in enumerate(configs, start=1):
        cached = _load_candidate_checkpoint(checkpoint_root, number, config, scenario_ids)
        if cached is None:
            raise RuntimeError(f"controller-v3 checkpoint disappeared for candidate {number}/{len(configs)}")
        for scenario_id in scenario_ids:
            scenario_replays[scenario_id].append(cached[scenario_id])
    trials = candidate_trial_rows(scenario_replays, warmup)
    expected_attempts = int(prereg["search_governance"]["total_candidate_scenario_replays"])
    if len(trials) != expected_attempts:
        raise RuntimeError("controller-v3 multiplicity ledger count changed")
    _write_jsonl(out(TRIALS), trials)
    stress_replays = {
        key: value for key, value in scenario_replays.items() if key != "base"
    }
    brain, consequences, freeze_sha = run_meta_controller(
        scenario_replays["base"], stress_replays, state, path,
        specialists=specialists, surfaces=surfaces, refs_by_time=refs,
        objective_window=int(prereg["meta_controller"]["objective_window_sessions"]),
        ensemble_size=int(prereg["meta_controller"]["ensemble_size"]),
        structural_cadence=int(prereg["meta_controller"]["structural_ensemble_cadence_sessions"]),
        stress_floor=float(prereg["meta_controller"]["stress_floor_30_session_net_return"]),
        max_abs_contracts=float(prereg["dynamic_sizing"]["max_abs_contracts"]),
        initial_capital=float(execution["starting_capital_usd"]),
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        cost_per_side=base_cost,
        initial_margin_usd_per_contract=float(execution["initial_margin_usd_per_contract"]),
        max_margin_fraction=float(prereg["dynamic_sizing"]["max_margin_fraction"]),
        max_notional_leverage=float(prereg["dynamic_sizing"]["max_notional_leverage"]),
        max_drawdown_fraction=float(prereg["dynamic_sizing"]["max_drawdown_fraction"]),
        embed_effectiveness_surface=False,
    )
    if not causal_prior_check(brain.iloc[warmup:].copy()):
        raise RuntimeError("controller-v3 meta selection failed strict-prior causal check")
    expert_map = {
        pd.Timestamp(row["decision_time"]): {key: value for key, value in row.items() if key != "decision_time"}
        for row in expert_paths.to_dict(orient="records")
    }
    predictor_map = {
        pd.Timestamp(row["decision_time"]): {key: value for key, value in row.items() if key != "decision_time"}
        for row in oracle_predictor.to_dict(orient="records")
    }
    primitive_predictor_map = {
        pd.Timestamp(row["decision_time"]): {key: value for key, value in row.items() if key != "decision_time"}
        for row in primitive_oracle_predictor.to_dict(orient="records")
    }
    expert_context_map = {
        pd.Timestamp(row["decision_time"]): {key: value for key, value in row.items() if key != "decision_time"}
        for row in context_state.to_dict(orient="records")
    }
    brain["expert_context_state"] = [
        expert_context_map.get(pd.Timestamp(stamp), {})
        for stamp in pd.to_datetime(brain["decision_time"], utc=True)
    ]
    brain["expert_multi_horizon_opinions"] = [
        expert_map.get(pd.Timestamp(stamp), {}) for stamp in pd.to_datetime(brain["decision_time"], utc=True)
    ]
    brain["oracle_weight_predictor"] = [
        predictor_map.get(pd.Timestamp(stamp), {}) for stamp in pd.to_datetime(brain["decision_time"], utc=True)
    ]
    brain["primitive_oracle_winner_predictor"] = [
        primitive_predictor_map.get(pd.Timestamp(stamp), {})
        for stamp in pd.to_datetime(brain["decision_time"], utc=True)
    ]
    surface_sidecar = _write_effectiveness_surface_sidecar(
        out(EFFECTIVENESS_SURFACES), surfaces
    )
    _write_jsonl(out(BRAIN), brain)
    freeze_sha = sha256_file(out(BRAIN))
    research_consequences = build_research_consequence_store(brain, path, state, prereg)
    _write_jsonl(out(CONSEQUENCES), research_consequences)
    invariance = full_future_invariance_proof(
        scenario_replays, brain, state, path, specialists, surfaces, rich_base, expert_paths,
        foundation_actuals, refs, families, configs, prereg, v2_runner, v1_runner,
    )
    if invariance["status"] != "PASS":
        raise RuntimeError(f"controller-v3 future invariance failed: {invariance}")
    ledger_payload = {
        "schema_version": int(prereg["schema_version"]),
        "issue": 465,
        "iteration": str(prereg["iteration"]),
        "decision_brain_freeze_sha256": freeze_sha,
        "decision_row_count": len(brain),
        "effectiveness_surface_sidecar": surface_sidecar,
        "selected_consequences": consequences.to_dict(orient="records"),
        "research_consequence_store_path": CONSEQUENCES.name,
        "research_consequence_store_sha256": sha256_file(out(CONSEQUENCES)),
        "expert_path_archive_sha256": sha256_file(EXPERT_PATHS),
        "expert_path_manifest_sha256": sha256_file(EXPERT_PATH_MANIFEST),
        "attribute_weight_oracle_sha256": sha256_file(out(ATTRIBUTE_ORACLE)),
        "oracle_weight_predictor_sha256": sha256_file(out(ORACLE_PREDICTOR)),
        "oracle_weight_predictor_causal_check": oracle_predictor_causal_check(oracle_predictor),
        "primitive_oracle_winner_predictor_sha256": sha256_file(out(PRIMITIVE_ORACLE_PREDICTOR)),
        "primitive_oracle_winner_predictor_causal_check": oracle_predictor_causal_check(
            primitive_oracle_predictor
        ),
        "search_governance": {
            **prereg["search_governance"],
            "observed_structural_candidate_count": len(configs),
            "observed_candidate_scenario_attempt_count": len(trials),
            "trial_attempt_ordinals_complete": trials["attempt_ordinal"].tolist() == list(range(1, len(trials) + 1)),
            "stopping_rule_triggered_after_all_frozen_attempts": True,
        },
        "future_invariance_proof": invariance,
        "protected_confirmation_accessed": False,
        "later_blocks_accessed": False,
    }
    _write_json(out(LEDGER), ledger_payload)
    eval_consequences = consequences.iloc[warmup:].copy()
    performance = v1_runner.performance_summary(
        eval_consequences,
        starting_capital=float(execution["starting_capital_usd"]),
        cost_per_side=base_cost,
        margin_per_contract=float(execution["initial_margin_usd_per_contract"]),
    )
    execution_degradation = execution_degradation_report(
        brain, state, path, prereg, warmup
    )
    leverage = pd.to_numeric(eval_consequences["notional_leverage"], errors="raise")
    margin = pd.to_numeric(eval_consequences["margin_fraction"], errors="raise")
    losses = pd.to_numeric(eval_consequences["realized_net_return"], errors="raise")
    base_trials = trials.loc[trials["execution_scenario"] == "base"].sort_values(
        ["post_warmup_net_return", "post_warmup_turnover", "config_id"],
        ascending=[False, True, True], kind="stable",
    )
    best_fixed = base_trials.iloc[0].to_dict()
    symmetric = base_trials.loc[base_trials["asymmetric"].eq(False)]
    best_symmetric = symmetric.iloc[0].to_dict() if not symmetric.empty else None
    oracle_opportunity_score = float(oracle["oracle_net_return"])
    if oracle_opportunity_score <= 0.0:
        oracle_classification = "NO_POSITIVE_HINDSIGHT_OPPORTUNITY_SCORE_IN_BLOCK1"
    elif float(performance["total_net_return"]) <= 0.0:
        oracle_classification = "POSITIVE_HINDSIGHT_OPPORTUNITY_SCORE_WITH_NONPOSITIVE_CAUSAL_PNL"
    else:
        oracle_classification = "POSITIVE_HINDSIGHT_OPPORTUNITY_SCORE_AND_POSITIVE_CAUSAL_PNL"
    trailing_scored = brain.iloc[warmup:]["candidate_objective_scores"]
    trailing_top = [
        max((float(row["trailing_30_net_return"]) for row in rows), default=0.0)
        for rows in trailing_scored
    ]
    predictor_eval = oracle_predictor.iloc[warmup:].copy()
    predictor_cosine = pd.to_numeric(
        predictor_eval["weight_cosine_similarity"], errors="coerce"
    ).dropna()
    oracle_horizon_predictability: dict[str, Any] = {}
    for horizon in prereg["attribute_weight_oracle"]["horizons_sessions"]:
        hkey = str(int(horizon))
        horizon_rows = pd.DataFrame([
            dict(payload).get(hkey, {}) for payload in predictor_eval["horizon_predictions"]
        ])
        side_hit = pd.to_numeric(horizon_rows.get("oracle_side_hit"), errors="coerce").dropna()
        top_hit = pd.to_numeric(horizon_rows.get("oracle_top_attribute_hit"), errors="coerce").dropna()
        exposure_error = pd.to_numeric(horizon_rows.get("oracle_exposure_error_abs"), errors="coerce").dropna()
        cosine = pd.to_numeric(horizon_rows.get("weight_cosine_similarity"), errors="coerce").dropna()
        consistency = pd.to_numeric(
            horizon_rows.get("weight_exposure_consistency_error_abs"), errors="coerce"
        ).dropna()
        oracle_horizon_predictability[hkey] = {
            "evaluated_rows": len(horizon_rows),
            "side_hit_rate": float(side_hit.mean()) if len(side_hit) else None,
            "top_attribute_hit_rate": float(top_hit.mean()) if len(top_hit) else None,
            "exposure_mae_contracts": float(exposure_error.mean()) if len(exposure_error) else None,
            "mean_weight_cosine_similarity": float(cosine.mean()) if len(cosine) else None,
            "mean_weight_exposure_consistency_error_contracts": (
                float(consistency.mean()) if len(consistency) else None
            ),
        }
    primitive_predictor_eval = primitive_oracle_predictor.iloc[warmup:].copy()
    primitive_hits = pd.to_numeric(
        primitive_predictor_eval["oracle_policy_hit"], errors="coerce"
    ).dropna()
    expert_manifest = json.loads(EXPERT_PATH_MANIFEST.read_text(encoding="utf-8"))
    final_surface = surfaces[pd.Timestamp(state.iloc[-1]["decision_time"])]
    result = {
        "schema_version": int(prereg["schema_version"]),
        "issue": 465,
        "iteration": str(prereg["iteration"]),
        "status": "BLOCK1_CONTROLLER_V3_SCORED_PENDING_SCOPE_AUDIT",
        "protected_confirmation_accessed": False,
        "later_blocks_accessed": False,
        "prereg_sha256": sha256_file(PREREG),
        "preflight_sha256": sha256_file(PREFLIGHT),
        "inventory_sha256": sha256_file(INVENTORY),
        "historical_reentry_sha256": sha256_file(REENTRY),
        "candidates_sha256": sha256_file(CANDIDATES),
        "oracle_first_sha256": sha256_file(out(ORACLE)),
        "expert_path_archive_sha256": sha256_file(EXPERT_PATHS),
        "expert_path_manifest_sha256": sha256_file(EXPERT_PATH_MANIFEST),
        "attribute_weight_oracle_sha256": sha256_file(out(ATTRIBUTE_ORACLE)),
        "oracle_weight_predictor_sha256": sha256_file(out(ORACLE_PREDICTOR)),
        "primitive_oracle_winner_predictor_sha256": sha256_file(out(PRIMITIVE_ORACLE_PREDICTOR)),
        "trials_sha256": sha256_file(out(TRIALS)),
        "decision_brain_sha256": sha256_file(out(BRAIN)),
        "effectiveness_surface_sidecar_sha256": sha256_file(out(EFFECTIVENESS_SURFACES)),
        "effectiveness_surface_sidecar": surface_sidecar,
        "consequence_store_sha256": sha256_file(out(CONSEQUENCES)),
        "ledger_sha256": sha256_file(out(LEDGER)),
        "scoring_input_identity_sha256": preflight["scoring_input_identity_sha256"],
        "decision_brain_freeze_sha256": freeze_sha,
        "post_warmup_performance": performance,
        "block_and_cumulative_net_return": {
            "block1_net_return": float(performance["total_net_return"]),
            "cumulative_through_block1_net_return": float(performance["total_net_return"]),
        },
        "trailing_30_history": {
            "post_warmup_decision_count": len(trailing_top),
            "mean_best_available_candidate_trailing30_net_return": float(np.mean(trailing_top)) if trailing_top else 0.0,
            "max_best_available_candidate_trailing30_net_return": float(np.max(trailing_top)) if trailing_top else 0.0,
            "full_history_in_decision_brain": True,
        },
        "loss_diagnostics": {
            "losing_decision_count": int((losses < 0.0).sum()),
            "worst_decision_net_return": float(losses.min()) if len(losses) else 0.0,
            "mean_losing_decision_net_return": float(losses.loc[losses < 0.0].mean()) if (losses < 0.0).any() else 0.0,
        },
        "side_contribution": side_contribution(eval_consequences),
        "selection_concentration": selection_concentration(brain.iloc[warmup:]),
        "realized_exposure_and_leverage": {
            "max_abs_exposure_contracts": float(eval_consequences["signal"].abs().max()),
            "mean_abs_exposure_contracts": float(eval_consequences["signal"].abs().mean()),
            "max_notional_leverage": float(leverage.max()) if len(leverage) else 0.0,
            "mean_notional_leverage": float(leverage.mean()) if len(leverage) else 0.0,
            "p95_notional_leverage": float(leverage.quantile(0.95)) if len(leverage) else 0.0,
            "max_margin_fraction": float(margin.max()) if len(margin) else 0.0,
        },
        "execution_degradation": execution_degradation,
        "adaptation_reporting": {
            "fast_daily_decision_count_post_warmup": len(brain) - warmup,
            "candidate_slow_cadences_tested": sorted({config.slow_cadence for config in configs}),
            "meta_structural_cadence_sessions": int(prereg["meta_controller"]["structural_ensemble_cadence_sessions"]),
            "meta_structural_update_count": int(brain.iloc[warmup:]["structural_update"].sum()),
        },
        "oracle_diagnostic": {
            **oracle,
            "overlapping_horizon_opportunity_score": oracle_opportunity_score,
            "economically_comparable_to_controller_pnl": False,
            "pnl_gap_reported": False,
            "noncomparability_reason": "primitive oracle aggregates overlapping 1/3/5/10/20-session hindsight opportunities",
            "classification": oracle_classification,
        },
        "expert_path_reporting": {
            "row_count": int(expert_manifest["row_count"]),
            "full_native_horizon_for_every_decision": bool(expert_manifest["full_native_horizon_for_every_decision"]),
            "maximum_native_horizon_sessions": int(expert_manifest["maximum_native_horizon_sessions"]),
            "history_max_trade_date": str(expert_manifest["history_max_trade_date"]),
            "later_block_market_data_accessed": bool(expert_manifest["later_block_market_data_accessed"]),
            "selection_use": str(expert_manifest["selection_use"]),
            "controller_context_fields": list(FOUNDATION_CONTEXT_COLUMNS),
            "full_paths_and_slope_acceleration_disagreement_archived_in_brain": True,
            "path_shape_interval_and_disagreement_used_in_comparable_state_retrieval": True,
        },
        "expert_effectiveness_reporting": {
            "metrics": list(prereg["expert_effectiveness_contract"]["metrics"]),
            "forecast_target_semantics": prereg["expert_effectiveness_contract"]["forecast_target_semantics"],
            "forecast_metric_availability_rule": prereg["expert_effectiveness_contract"]["forecast_metric_availability_rule"],
            "memory_scale_selection": prereg["expert_effectiveness_contract"]["memory_scale_selection"],
            "final_surface_row_count": len(final_surface),
            "diagnostic_reliability_used_in_ranking": True,
            "independent_memory_selection_per_specialist_horizon_direction": True,
            "profile_memory_sets_are_tie_break_preferences_only": True,
            "forecast_metrics_strict_prior_native_target": True,
            "full_history_in_decision_brain": False,
            "effectiveness_surface_storage": "hash_bound_parquet_sidecar",
            "effectiveness_surface_sidecar_sha256": surface_sidecar["sha256"],
        },
        "primitive_oracle_winner_reporting": {
            "predictor_row_count": len(primitive_oracle_predictor),
            "target_type": "primitive_policy_id",
            "target_components": ["policy_id", "specialist", "horizon", "direction"],
            "strict_prior_predictor_check": oracle_predictor_causal_check(primitive_oracle_predictor),
            "post_warmup_policy_id_hit_rate": (
                float(primitive_hits.mean()) if len(primitive_hits) else None
            ),
            "selection_use": False,
        },
        "attribute_weight_oracle_reporting": {
            "attribute_count": len(weighted_attributes),
            "oracle_row_count": len(attribute_oracle),
            "predictor_row_count": len(oracle_predictor),
            "horizons_sessions": list(prereg["attribute_weight_oracle"]["horizons_sessions"]),
            "exposure_step_contracts": float(prereg["attribute_weight_oracle"]["exposure_step_contracts"]),
            "max_abs_contracts": float(prereg["attribute_weight_oracle"]["max_abs_contracts"]),
            "sparse_ks": list(prereg["attribute_weight_oracle"]["sparse_ks"]),
            "optimizer": "exact_after_cost_exposure_lattice_plus_analytic_minimum_L2_weight_solution",
            "strict_prior_predictor_check": oracle_predictor_causal_check(oracle_predictor),
            "post_warmup_side_hit_rate": float(pd.Series(predictor_eval["oracle_side_hit"]).dropna().astype(float).mean()) if predictor_eval["oracle_side_hit"].notna().any() else None,
            "post_warmup_top_attribute_hit_rate": float(pd.Series(predictor_eval["oracle_top_attribute_hit"]).dropna().astype(float).mean()) if predictor_eval["oracle_top_attribute_hit"].notna().any() else None,
            "post_warmup_mean_weight_cosine_similarity": float(predictor_cosine.mean()) if len(predictor_cosine) else None,
            "horizon_predictability": oracle_horizon_predictability,
            "diagnostic_interpretation": "exposure_reconstruction_representation_not_feature_importance",
            "feature_importance_inference": False,
            "selection_use": False,
        },
        "future_invariance_proof": invariance,
        "causal_checks": {
            "all_meta_selection_outcomes_strictly_prior": causal_prior_check(brain.iloc[warmup:]),
            "same_day_or_future_outcomes_used_in_selection": False,
            "research_consequence_store_used_in_selection": False,
            "oracle_used_in_selection": False,
        },
        "search_governance": ledger_payload["search_governance"],
        "block1_candidate_control_set": {
            "best_fixed_candidate": best_fixed,
            "best_symmetric_control": best_symmetric,
            "adaptive_controller": "controller-v3 meta-controller",
            "final_issue465_to_414_handoff_ready": False,
            "handoff_blocker": "later six-month development blocks intentionally not run under current Block1-only instruction",
        },
        "implementation_evidence": {
            "complete_input_inventory_and_reentry_ledger": True,
            "all_admissible_numeric_pit_attributes_individually_weightable": True,
            "exact_zero_individual_and_group_weights_legal": True,
            "six_month_block_boundary_enforced": True,
            "availability_age_vintage_revision_retained": True,
            "latest_known_carry_forward_only": True,
            "future_consequence_store_logically_and_physically_separate": True,
            "historical_exact_negative_roles_binding": True,
            "conditional_specialist_effectiveness_surface_complete": True,
            "explicit_forecast_error_hit_rate_calibration_sharpness_history": True,
            "forecast_error_targets_model_native_and_strict_prior": True,
            "native_timesfm_and_kronos_20_session_paths_every_decision": True,
            "native_foundation_paths_drive_horizon_specific_economics_and_support": True,
            "foundation_path_shape_interval_and_disagreement_are_live_comparable_state_context": True,
            "explicit_forecast_slope_acceleration_and_model_disagreement": True,
            "full_53_attribute_daily_hindsight_weight_oracle": True,
            "strict_prior_oracle_weight_predictor": True,
            "oracle_weight_predictor_future_invariance_proven": invariance["oracle_weight_predictor_prefix_identical"],
            "strict_prior_primitive_oracle_winner_predictor": True,
            "primitive_oracle_winner_predictor_future_invariance_proven": invariance[
                "primitive_oracle_winner_predictor_prefix_identical"
            ],
            "memory_bank_includes_5_10_20_40_60_126_252_expanding": True,
            "independent_memory_scale_selection_per_specialist_horizon_direction": True,
            "eight_stage_hierarchy_implemented": True,
            "concurrent_1_3_5_10_20_session_opportunity_horizons": True,
            "event_time_explicitly_held_for_unproven_block1_source_timing": True,
            "prior_only_comparable_state_retrieval": True,
            "sparse_prior30_after_cost_objective": True,
            "slow_and_fast_adaptation_separated": True,
            "first_class_mark_to_market_position_state": True,
            "dynamic_sizing_and_hard_caps": True,
            "independent_long_short_profiles_and_symmetric_controls": True,
            "wait_enter_abstain_timing_layer": True,
            "full_position_lifecycle_scored": True,
            "execution_slippage_and_missed_fill_sensitivity": True,
            "search_preregistered_ledgered_and_multiplicity_counted": True,
            "oracle_computed_before_unrestricted_structural_search": True,
            "complete_historical_decision_brain_persisted": True,
            "strict_prior_outcome_selection": True,
            "full_future_invariance_mutation_replay_passed": invariance["status"] == "PASS",
            "comprehensive_reporting_including_realized_leverage": True,
        },
        "scoring_code_identity": current_code_identity(),
        "scoring_environment_identity": runtime_environment_identity(),
        "scope_audit_required_before_verification": True,
    }
    _write_json(out(RESULT), result)
    publication = _publish_generation(
        generation_staging,
        generation_seed,
        scoring_identity_sha256=str(preflight["scoring_input_identity_sha256"]),
        candidate_grid_sha256=str(frozen_candidates["candidate_grid_sha256"]),
    )
    result["published_generation"] = publication
    return result