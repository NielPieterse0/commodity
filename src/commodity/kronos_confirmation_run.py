from __future__ import annotations

import argparse
import ctypes
import gc
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from commodity.config import assumptions_config, data_config, model_config
from commodity.dataset_freeze import load_frozen_dataset
from commodity.evaluation import (
    evaluate_predictions,
    paired_block_bootstrap_rmse,
    paired_nonoverlapping_block_sign_flip_mse,
    v2_robustness_report,
    v2_trailing_range20_signal,
)
from commodity.evaluation_protocol import benjamini_hochberg_adjust
from commodity.kronos_confirmation import (
    MODEL_KEYS,
    build_released_checkpoint_adapter,
    require_independent_release,
    validate_confirmation_freeze,
)
from commodity.market_data import (
    ensure_canonical_market_availability,
    validate_contract_history,
)
from commodity.models import baseline_factory
from commodity.phase_d_evaluation import (
    feature_family_columns,
    walk_forward_distribution_predict,
)
from commodity.rolls import build_derived_continuous_series
from commodity.v2_kronos import governed_kronos_forecast, governed_return_prediction

CHECKPOINTS = ("mini", "small", "base")


class KronosConfirmationRunError(RuntimeError):
    """Raised when the frozen #180 execution cannot be reproduced exactly."""


def _normalized_sha256(path: Path) -> str:
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise KronosConfirmationRunError(f"JSON authority must be an object: {path}")
    return value


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temp, index=False, lineterminator="\n", float_format="%.17g")
    temp.replace(path)


def _git_head(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()


def _require_clean_tracked_tree(repo_root: Path) -> str:
    head = _git_head(repo_root)
    status = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=no"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        raise KronosConfirmationRunError("#180 inference requires a clean tracked execution tree")
    return head


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    import torch

    torch.manual_seed(seed)


def _peak_rss_bytes() -> int:
    if os.name == "nt":
        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        )
        if not ok:
            raise KronosConfirmationRunError("cannot read process peak RSS")
        return int(counters.PeakWorkingSetSize)
    import resource

    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value * (1 if sys.platform == "darwin" else 1024)


def _validate_evaluator_source(repo_root: Path) -> dict[str, Any]:
    freeze = validate_confirmation_freeze(repo_root)
    evaluator_path = repo_root / freeze["evaluation"]["statistical_evaluator"]
    evaluator = _json(evaluator_path)
    source_identity = evaluator.get("source_identity", {})
    hashes = source_identity.get("sha256", {})
    if not isinstance(hashes, dict) or not hashes:
        raise KronosConfirmationRunError("statistical evaluator source hashes are missing")
    for relative, expected in hashes.items():
        observed = _normalized_sha256(repo_root / str(relative))
        if observed != expected:
            raise KronosConfirmationRunError(f"statistical evaluator source drifted: {relative}")
    return evaluator


def _validate_canonical_snapshot(path: Path) -> str:
    manifest_path = path.parent / "manifest.json"
    manifest = _json(manifest_path)
    matches = [item for item in manifest.get("artifacts", []) if item.get("path") == path.name]
    if len(matches) != 1:
        raise KronosConfirmationRunError("canonical market snapshot is not uniquely manifested")
    observed = _file_sha256(path)
    if observed != matches[0].get("sha256"):
        raise KronosConfirmationRunError("canonical market snapshot hash mismatch")
    return observed


def _build_market_inputs(canonical_market_csv: Path) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    snapshot_sha256 = _validate_canonical_snapshot(canonical_market_csv)
    contracts = pd.read_csv(canonical_market_csv)
    cfg = data_config()
    assumptions = assumptions_config()
    schema = cfg["canonical_contract_schema"]
    source = cfg["sources"]["market_canonical"]
    policy = assumptions["assumptions"]["continuous_series_policy"]["policy"]
    available = ensure_canonical_market_availability(contracts, source["availability_policy"])
    canonical = validate_contract_history(available, schema)
    selected, _ = build_derived_continuous_series(canonical, schema, policy)
    return canonical, selected, snapshot_sha256


def _prepare_inputs(
    repo_root: Path,
    dataset_dir: Path,
    canonical_market_csv: Path,
) -> dict[str, Any]:
    freeze = validate_confirmation_freeze(repo_root)
    require_independent_release(repo_root, freeze)
    evaluator = _validate_evaluator_source(repo_root)
    frame, manifest = load_frozen_dataset(dataset_dir)
    data = freeze["data_and_target"]
    if manifest.get("dataset_id") != data["dataset_id"]:
        raise KronosConfirmationRunError("frozen dataset identity mismatch")
    if manifest.get("dataset_sha256") != data["dataset_sha256"]:
        raise KronosConfirmationRunError("frozen dataset hash mismatch")
    if len(frame) - int(data["oos_rows"]) != int(manifest.get("initial_train_rows", 0)):
        raise KronosConfirmationRunError("frozen initial-train/OOS split mismatch")
    canonical, selected, market_sha256 = _build_market_inputs(canonical_market_csv)
    selected = selected.copy()
    selected["available_at"] = pd.to_datetime(selected["available_at"], utc=True)
    selected["trade_date"] = pd.to_datetime(selected["trade_date"], utc=True)
    selected["target_timestamp"] = selected["available_at"].shift(-1)
    selected["target_contract_id"] = selected["contract_id"].shift(-1)
    selected["target_return"] = selected["settle_log_return"].shift(-1)

    oos_rows = int(data["oos_rows"])
    oos = frame.iloc[-oos_rows:].copy()
    expected_start = pd.Timestamp(data["oos_start"])
    expected_end = pd.Timestamp(data["oos_end"])
    if len(oos) != oos_rows or oos.index[0] != expected_start or oos.index[-1] != expected_end:
        raise KronosConfirmationRunError("frozen OOS row identity mismatch")
    target_map = selected.set_index("available_at").reindex(oos.index)
    if target_map["contract_id"].isna().any():
        raise KronosConfirmationRunError("selected market does not cover every frozen OOS row")
    if not target_map["contract_id"].eq(target_map["target_contract_id"]).all():
        raise KronosConfirmationRunError("frozen OOS target mapping crosses a contract boundary")
    if not np.allclose(
        oos[data["forecast_target"]].to_numpy(dtype=float),
        target_map["target_return"].to_numpy(dtype=float),
        rtol=0.0,
        atol=2e-15,
    ):
        raise KronosConfirmationRunError("selected-contract target mapping differs from frozen target")
    return {
        "freeze": freeze,
        "evaluator": evaluator,
        "frame": frame,
        "manifest": manifest,
        "oos": oos,
        "canonical": canonical,
        "selected": selected,
        "target_map": target_map,
        "canonical_market_sha256": market_sha256,
    }


def _reconstruct_hist_gb_baseline(
    repo_root: Path,
    prepared: dict[str, Any],
) -> pd.DataFrame:
    frame = prepared["frame"]
    manifest = prepared["manifest"]
    freeze = prepared["freeze"]
    phase_cfg = _json(repo_root / "config/phase_d_evaluation.json")
    models = model_config()["models"]
    target = str(manifest.get("target", "target_ret_1"))
    mapping = feature_family_columns(frame, manifest, target=target)
    columns = [column for family in mapping.values() for column in family]
    walk = phase_cfg["walk_forward"]
    prediction = walk_forward_distribution_predict(
        baseline_factory("hist_gb", models),
        frame[columns].astype(float),
        frame[target].astype(float),
        initial_train=int(walk["initial_train_rows"]),
        retrain_every=int(walk["retrain_every_rows"]),
        volatility_window=int(walk["volatility_window_rows"]),
    )
    result = prediction[["prediction", "actual"]].copy()
    observed = evaluate_predictions(result)["rmse"]
    expected = float(freeze["benchmarks"]["phase_d_full_v1_hist_gb"]["rmse"])
    if not math.isclose(observed, expected, rel_tol=0.0, abs_tol=1e-15):
        raise KronosConfirmationRunError(
            f"Phase-D HistGB row reconstruction drifted: expected {expected}, observed {observed}"
        )
    return result


def _zero_baseline(oos: pd.DataFrame, target: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "prediction": np.zeros(len(oos), dtype=float),
            "actual": oos[target].to_numpy(dtype=float),
        },
        index=oos.index,
    )


def _checkpoint_paths(repo_root: Path, freeze: dict[str, Any], checkpoint: str) -> tuple[Path, Path]:
    directory = repo_root / str(freeze["artifacts"][checkpoint])
    return directory / "predictions.csv", directory / "prediction-manifest.json"


def _existing_checkpoint_is_valid(
    repo_root: Path,
    freeze: dict[str, Any],
    checkpoint: str,
    *,
    execution_revision: str | None = None,
) -> bool:
    predictions_path, manifest_path = _checkpoint_paths(repo_root, freeze, checkpoint)
    if not predictions_path.is_file() or not manifest_path.is_file():
        return False
    manifest = _json(manifest_path)
    return (
        manifest.get("experiment_id") == freeze["experiment_id"]
        and manifest.get("checkpoint") == checkpoint
        and (
            execution_revision is None
            or manifest.get("execution_runner_commit") == execution_revision
        )
        and manifest.get("state") == "prediction_complete_pending_joint_evaluation"
        and manifest.get("rows") == int(freeze["data_and_target"]["oos_rows"])
        and manifest.get("predictions_sha256") == _file_sha256(predictions_path)
    )


def run_checkpoint(
    *,
    repo_root: Path,
    dataset_dir: Path,
    canonical_market_csv: Path,
    checkpoint: str,
) -> dict[str, Any]:
    if checkpoint not in CHECKPOINTS:
        raise KronosConfirmationRunError(f"unknown checkpoint: {checkpoint}")
    execution_revision = _require_clean_tracked_tree(repo_root)
    prepared = _prepare_inputs(repo_root, dataset_dir, canonical_market_csv)
    freeze = prepared["freeze"]
    if _existing_checkpoint_is_valid(
        repo_root,
        freeze,
        checkpoint,
        execution_revision=execution_revision,
    ):
        return _json(_checkpoint_paths(repo_root, freeze, checkpoint)[1])
    predictions_path, manifest_path = _checkpoint_paths(repo_root, freeze, checkpoint)
    if predictions_path.exists() or manifest_path.exists():
        raise KronosConfirmationRunError(f"incomplete existing checkpoint artifact: {checkpoint}")

    seed = int(freeze["common_execution"]["seed"])
    _set_seed(seed)
    started = time.perf_counter()
    adapter, released_freeze = build_released_checkpoint_adapter(repo_root, checkpoint)
    if released_freeze["experiment_id"] != freeze["experiment_id"]:
        raise KronosConfirmationRunError("released adapter is bound to a different experiment")

    rows: list[dict[str, Any]] = []
    oos = prepared["oos"]
    target_map = prepared["target_map"]
    target = freeze["data_and_target"]["forecast_target"]
    for prediction_time, row in oos.iterrows():
        mapping = target_map.loc[prediction_time]
        target_timestamp = pd.Timestamp(mapping["target_timestamp"])
        target_contract_id = str(mapping["target_contract_id"])
        forecast, context = governed_kronos_forecast(
            adapter=adapter,
            canonical_market=prepared["canonical"],
            selected_market=prepared["selected"],
            prediction_time=prediction_time,
            target_timestamp=target_timestamp,
            max_context=int(freeze["common_execution"]["max_context"]),
        )
        predicted_close = float(forecast.iloc[0]["close"])
        observed_close = float(context.iloc[-1]["close"])
        predicted_return = governed_return_prediction(
            predicted_close_next=predicted_close,
            observed_close_at_cutoff=observed_close,
            current_contract_id=str(context.iloc[-1]["contract_id"]),
            target_contract_id=target_contract_id,
        )
        rows.append(
            {
                "prediction_time": prediction_time.isoformat(),
                "target_timestamp": target_timestamp.isoformat(),
                "checkpoint": checkpoint,
                "contract_id": target_contract_id,
                "prediction": float(predicted_return),
                "actual": float(row[target]),
                "predicted_close": predicted_close,
                "observed_close_at_cutoff": observed_close,
                "context_rows": len(context),
                "context_start": pd.Timestamp(context.index[0]).isoformat(),
                "context_end": pd.Timestamp(context.index[-1]).isoformat(),
                "transformation": str(context.iloc[-1]["transformation"]),
            }
        )

    elapsed = time.perf_counter() - started
    max_hours = float(freeze["resource_observations"]["max_wall_clock_hours_per_checkpoint"])
    if elapsed > max_hours * 3600.0:
        raise KronosConfirmationRunError(f"checkpoint exceeded frozen wall-clock cap: {checkpoint}")
    predictions = pd.DataFrame(rows)
    expected_rows = int(freeze["data_and_target"]["oos_rows"])
    finite = np.isfinite(
        predictions[["prediction", "actual", "predicted_close", "observed_close_at_cutoff"]]
        .to_numpy(dtype=float)
    ).all()
    if len(predictions) != expected_rows or not finite:
        raise KronosConfirmationRunError(f"checkpoint coverage failed: {checkpoint}")
    _atomic_csv(predictions_path, predictions)
    manifest = {
        "schema_version": 1,
        "experiment_id": freeze["experiment_id"],
        "checkpoint": checkpoint,
        "model_key": MODEL_KEYS[checkpoint],
        "execution_runner_commit": execution_revision,
        "state": "prediction_complete_pending_joint_evaluation",
        "rows": len(predictions),
        "predictions_sha256": _file_sha256(predictions_path),
        "seed": seed,
        "inference": freeze["common_execution"]["inference"],
        "artifact_manifest": adapter.artifact_manifest,
        "observed_device": "cpu",
        "wall_clock_seconds": elapsed,
        "peak_process_rss_bytes": _peak_rss_bytes(),
        "canonical_market_sha256": prepared["canonical_market_sha256"],
    }
    _atomic_json(manifest_path, manifest)
    del adapter
    gc.collect()
    validate_confirmation_freeze(repo_root)
    _validate_evaluator_source(repo_root)
    return manifest


def _load_checkpoint_predictions(
    repo_root: Path,
    freeze: dict[str, Any],
    checkpoint: str,
    *,
    execution_revision: str,
) -> pd.DataFrame:
    predictions_path, manifest_path = _checkpoint_paths(repo_root, freeze, checkpoint)
    if not _existing_checkpoint_is_valid(
        repo_root,
        freeze,
        checkpoint,
        execution_revision=execution_revision,
    ):
        raise KronosConfirmationRunError(f"checkpoint prediction artifact is incomplete: {checkpoint}")
    frame = pd.read_csv(predictions_path)
    frame["prediction_time"] = pd.to_datetime(frame["prediction_time"], utc=True)
    frame = frame.set_index("prediction_time")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise KronosConfirmationRunError(f"checkpoint prediction rows are invalid: {checkpoint}")
    manifest = _json(manifest_path)
    if manifest["predictions_sha256"] != _file_sha256(predictions_path):
        raise KronosConfirmationRunError(f"checkpoint prediction hash drifted: {checkpoint}")
    return frame


def _pairwise_report(
    challenger: pd.DataFrame,
    baseline: pd.DataFrame,
    freeze: dict[str, Any],
) -> dict[str, Any]:
    bootstrap = freeze["evaluation"]["bootstrap"]
    primary = paired_block_bootstrap_rmse(
        challenger,
        baseline,
        block_size=int(bootstrap["block_size"]),
        resamples=int(bootstrap["resamples"]),
        confidence=float(bootstrap["confidence"]),
        seed=int(bootstrap["seed"]),
    )
    secondary = paired_nonoverlapping_block_sign_flip_mse(
        challenger,
        baseline,
        block_size=int(bootstrap["block_size"]),
    )
    return {"primary": primary, "secondary_diagnostic": secondary}


def _comparison_pairs(
    predictions: dict[str, pd.DataFrame],
    zero: pd.DataFrame,
    hist_gb: pd.DataFrame,
) -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    return {
        "mini_vs_zero": (predictions["mini"], zero),
        "mini_vs_v1_hist_gb": (predictions["mini"], hist_gb),
        "small_vs_zero": (predictions["small"], zero),
        "small_vs_v1_hist_gb": (predictions["small"], hist_gb),
        "base_vs_zero": (predictions["base"], zero),
        "base_vs_v1_hist_gb": (predictions["base"], hist_gb),
        "small_vs_mini": (predictions["small"], predictions["mini"]),
        "base_vs_mini": (predictions["base"], predictions["mini"]),
        "base_vs_small": (predictions["base"], predictions["small"]),
    }


def _joint_robustness(
    predictions: dict[str, pd.DataFrame],
    zero: pd.DataFrame,
    hist_gb: pd.DataFrame,
    prepared: dict[str, Any],
) -> dict[str, Any]:
    frame = prepared["frame"]
    prediction_times = pd.Series(frame.index, index=frame.index)
    signal = v2_trailing_range20_signal(prepared["selected"], prediction_times)
    initial_train = len(frame) - int(prepared["freeze"]["data_and_target"]["oos_rows"])
    result: dict[str, Any] = {}
    for checkpoint in CHECKPOINTS:
        result[checkpoint] = {
            "vs_zero": v2_robustness_report(
                predictions[checkpoint], zero, signal, initial_train=initial_train
            ),
            "vs_v1_hist_gb": v2_robustness_report(
                predictions[checkpoint], hist_gb, signal, initial_train=initial_train
            ),
        }
    return result


def finalize_run(
    *,
    repo_root: Path,
    dataset_dir: Path,
    canonical_market_csv: Path,
) -> dict[str, Any]:
    execution_revision = _require_clean_tracked_tree(repo_root)
    prepared = _prepare_inputs(repo_root, dataset_dir, canonical_market_csv)
    freeze = prepared["freeze"]
    target = freeze["data_and_target"]["forecast_target"]
    predictions = {
        checkpoint: _load_checkpoint_predictions(
            repo_root,
            freeze,
            checkpoint,
            execution_revision=execution_revision,
        )[["prediction", "actual"]].copy()
        for checkpoint in CHECKPOINTS
    }
    expected_index = prepared["oos"].index
    expected_actual = prepared["oos"][target].to_numpy(dtype=float)
    for checkpoint, frame in predictions.items():
        if not frame.index.equals(expected_index):
            raise KronosConfirmationRunError(f"scored rows differ for checkpoint: {checkpoint}")
        if not np.allclose(frame["actual"].to_numpy(dtype=float), expected_actual, rtol=0.0, atol=2e-15):
            raise KronosConfirmationRunError(f"actual target differs for checkpoint: {checkpoint}")

    zero = _zero_baseline(prepared["oos"], target)
    hist_gb = _reconstruct_hist_gb_baseline(repo_root, prepared)
    zero_rmse = evaluate_predictions(zero)["rmse"]
    expected_zero = float(freeze["benchmarks"]["zero_return_naive"]["rmse"])
    if not math.isclose(zero_rmse, expected_zero, rel_tol=0.0, abs_tol=1e-15):
        raise KronosConfirmationRunError("zero-return baseline reconstruction drifted")

    metrics = {checkpoint: evaluate_predictions(frame) for checkpoint, frame in predictions.items()}
    pairs = _comparison_pairs(predictions, zero, hist_gb)
    expected_names = list(freeze["evaluation"]["primary_comparisons"])
    if list(pairs) != expected_names:
        raise KronosConfirmationRunError("nine-member comparison family order drifted")
    comparisons = {name: _pairwise_report(*pairs[name], freeze) for name in expected_names}
    adjusted = benjamini_hochberg_adjust(
        [float(comparisons[name]["primary"]["p_value"]) for name in expected_names]
    )
    alpha = float(freeze["evaluation"]["multiple_testing"]["max_adjusted_p_value"])
    for name, adjusted_p in zip(expected_names, adjusted, strict=True):
        primary = comparisons[name]["primary"]
        primary["adjusted_p_value"] = float(adjusted_p)
        primary["passes_frozen_gate"] = bool(
            float(primary["rmse_improvement"]) > 0.0
            and float(primary["ci_lower"]) > 0.0
            and float(adjusted_p) <= alpha
        )

    robustness = _joint_robustness(predictions, zero, hist_gb, prepared)
    checkpoint_keep: dict[str, bool] = {}
    for checkpoint in CHECKPOINTS:
        vs_zero = comparisons[f"{checkpoint}_vs_zero"]["primary"]
        vs_v1 = comparisons[f"{checkpoint}_vs_v1_hist_gb"]["primary"]
        checkpoint_keep[checkpoint] = bool(
            metrics[checkpoint]["rmse"] < expected_zero
            and metrics[checkpoint]["rmse"]
            < float(freeze["benchmarks"]["phase_d_full_v1_hist_gb"]["rmse"])
            and vs_zero["passes_frozen_gate"]
            and vs_v1["passes_frozen_gate"]
            and robustness[checkpoint]["vs_zero"]["passed"]
            and robustness[checkpoint]["vs_v1_hist_gb"]["passed"]
        )

    rmses = {checkpoint: float(metrics[checkpoint]["rmse"]) for checkpoint in CHECKPOINTS}
    monotonic_size_improvement = bool(rmses["base"] < rmses["small"] < rmses["mini"])
    kept = [checkpoint for checkpoint in CHECKPOINTS if checkpoint_keep[checkpoint]]
    materially_fail_both = {
        checkpoint: bool(
            rmses[checkpoint] >= expected_zero
            and rmses[checkpoint]
            >= float(freeze["benchmarks"]["phase_d_full_v1_hist_gb"]["rmse"])
        )
        for checkpoint in CHECKPOINTS
    }
    disposition = "keep_direct_one_step_kronos" if kept else "drop_direct_one_step_kronos"
    reason = (
        f"Frozen keep gate passed by: {', '.join(kept)}."
        if kept
        else "No checkpoint passed the complete frozen RMSE, bootstrap/BH, and robustness keep gate."
    )

    resource_observations = {
        checkpoint: _json(_checkpoint_paths(repo_root, freeze, checkpoint)[1])
        for checkpoint in CHECKPOINTS
    }
    result = {
        "schema_version": 1,
        "experiment_id": freeze["experiment_id"],
        "issue": 180,
        "state": "complete",
        "rows": int(freeze["data_and_target"]["oos_rows"]),
        "metrics": metrics,
        "benchmarks": {
            "zero_return": evaluate_predictions(zero),
            "phase_d_full_v1_hist_gb": evaluate_predictions(hist_gb),
        },
        "comparisons": comparisons,
        "robustness": robustness,
        "decision": {
            "disposition": disposition,
            "reason": reason,
            "checkpoint_keep": checkpoint_keep,
            "all_three_materially_fail_both_rmse": all(materially_fail_both.values()),
            "materially_fail_both_rmse": materially_fail_both,
            "checkpoint_size_improves": monotonic_size_improvement,
            "checkpoint_size_statement": (
                "RMSE is strictly ordered Base < Small < Mini."
                if monotonic_size_improvement
                else "RMSE is not strictly ordered Base < Small < Mini; larger checkpoint size is not established as an improvement."
            ),
            "post_result_tuning_permitted": False,
        },
        "resources": {
            checkpoint: {
                key: resource_observations[checkpoint][key]
                for key in (
                    "model_key",
                    "observed_device",
                    "wall_clock_seconds",
                    "peak_process_rss_bytes",
                )
            }
            for checkpoint in CHECKPOINTS
        },
    }

    validate_confirmation_freeze(repo_root)
    _validate_evaluator_source(repo_root)
    artifact_root = repo_root / str(freeze["artifacts"]["root"])
    for checkpoint in CHECKPOINTS:
        metrics_path = repo_root / str(freeze["artifacts"][checkpoint]) / "metrics.json"
        _atomic_json(metrics_path, metrics[checkpoint])
    comparisons_path = artifact_root / "comparisons.json"
    result_path = artifact_root / "result.json"
    _atomic_json(comparisons_path, comparisons)
    _atomic_json(result_path, result)
    manifest = {
        "schema_version": 1,
        "experiment_id": freeze["experiment_id"],
        "state": "complete_no_rescue_search",
        "execution_runner_commit": execution_revision,
        "freeze_sha256": _normalized_sha256(repo_root / "config/kronos_confirmation.json"),
        "audit_release_sha256": _normalized_sha256(
            repo_root / "docs/development/kronos-three-checkpoint-confirmation/audit-release.json"
        ),
        "dataset_sha256": freeze["data_and_target"]["dataset_sha256"],
        "canonical_market_sha256": prepared["canonical_market_sha256"],
        "result_sha256": _file_sha256(result_path),
        "comparisons_sha256": _file_sha256(comparisons_path),
        "checkpoint_prediction_sha256": {
            checkpoint: resource_observations[checkpoint]["predictions_sha256"]
            for checkpoint in CHECKPOINTS
        },
        "no_checkpoint_specific_tuning": True,
        "no_calibration": True,
        "no_post_result_metric_or_multiplicity_changes": True,
    }
    _atomic_json(artifact_root / "run-manifest.json", manifest)
    return result


def run_all(
    *,
    repo_root: Path,
    dataset_dir: Path,
    canonical_market_csv: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    execution_revision = _require_clean_tracked_tree(repo_root)
    prepared = _prepare_inputs(repo_root, dataset_dir, canonical_market_csv)
    freeze = prepared["freeze"]
    final_path = repo_root / str(freeze["artifacts"]["root"]) / "result.json"
    if final_path.is_file():
        result = _json(final_path)
        if result.get("experiment_id") != freeze["experiment_id"] or result.get("state") != "complete":
            raise KronosConfirmationRunError("existing final result is incomplete or belongs to another experiment")
        return result
    env = os.environ.copy()
    env["COMMODITY_KRONOS_CACHE_DIR"] = str(cache_dir.resolve())
    for checkpoint in CHECKPOINTS:
        if _existing_checkpoint_is_valid(
            repo_root,
            freeze,
            checkpoint,
            execution_revision=execution_revision,
        ):
            continue
        command = [
            sys.executable,
            "-m",
            "commodity.kronos_confirmation_run",
            "checkpoint",
            "--repo-root",
            str(repo_root),
            "--dataset-dir",
            str(dataset_dir),
            "--canonical-market-csv",
            str(canonical_market_csv),
            "--checkpoint",
            checkpoint,
            "--cache-dir",
            str(cache_dir),
        ]
        subprocess.run(command, check=True, cwd=repo_root, env=env)
    return finalize_run(
        repo_root=repo_root,
        dataset_dir=dataset_dir,
        canonical_market_csv=canonical_market_csv,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run frozen #180 Kronos confirmation")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "checkpoint", "finalize", "all"):
        command = sub.add_parser(name)
        command.add_argument("--repo-root", type=Path, required=True)
        command.add_argument("--dataset-dir", type=Path, required=True)
        command.add_argument("--canonical-market-csv", type=Path, required=True)
        if name in {"checkpoint", "all"}:
            command.add_argument("--cache-dir", type=Path, required=True)
        if name == "checkpoint":
            command.add_argument("--checkpoint", choices=CHECKPOINTS, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    repo_root = args.repo_root.resolve()
    dataset_dir = args.dataset_dir.resolve()
    canonical_market_csv = args.canonical_market_csv.resolve()
    if args.command == "preflight":
        prepared = _prepare_inputs(repo_root, dataset_dir, canonical_market_csv)
        print(
            json.dumps(
                {
                    "status": "passed",
                    "experiment_id": prepared["freeze"]["experiment_id"],
                    "oos_rows": len(prepared["oos"]),
                    "canonical_market_sha256": prepared["canonical_market_sha256"],
                },
                sort_keys=True,
            )
        )
        return
    if args.command == "checkpoint":
        os.environ["COMMODITY_KRONOS_CACHE_DIR"] = str(args.cache_dir.resolve())
        manifest = run_checkpoint(
            repo_root=repo_root,
            dataset_dir=dataset_dir,
            canonical_market_csv=canonical_market_csv,
            checkpoint=args.checkpoint,
        )
        print(json.dumps({"status": "prediction_complete", "checkpoint": manifest["checkpoint"]}))
        return
    if args.command == "finalize":
        result = finalize_run(
            repo_root=repo_root,
            dataset_dir=dataset_dir,
            canonical_market_csv=canonical_market_csv,
        )
    else:
        result = run_all(
            repo_root=repo_root,
            dataset_dir=dataset_dir,
            canonical_market_csv=canonical_market_csv,
            cache_dir=args.cache_dir.resolve(),
        )
    print(json.dumps({"status": "complete", "experiment_id": result["experiment_id"]}))


if __name__ == "__main__":
    main()
