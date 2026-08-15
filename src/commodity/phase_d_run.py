from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from commodity.dataset_freeze import load_frozen_dataset
from commodity.phase_d_contract import build_phase_d_plan, validate_phase_d_lineage
from commodity.phase_d_evaluation import (
    build_walk_forward_folds,
    feature_family_columns,
    run_phase_d_evaluation,
)

_GIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def validate_phase_d_dataset_manifest(
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    manifest_sha256: str,
) -> None:
    dataset = config.get("dataset")
    if not isinstance(dataset, Mapping):
        raise TypeError("Phase D config requires a dataset contract")
    checks = {
        "dataset_id": manifest.get("dataset_id"),
        "freeze_id": manifest.get("freeze_id"),
        "dataset_sha256": manifest.get("dataset_sha256"),
    }
    for field, actual in checks.items():
        expected = dataset.get(field)
        if actual != expected:
            raise ValueError(f"Phase D dataset {field} does not match the frozen contract")
    if manifest_sha256 != dataset.get("manifest_sha256"):
        raise ValueError("Phase D dataset manifest_sha256 does not match the frozen contract")
    if manifest.get("evidence_mode") != dataset.get("required_evidence_mode"):
        raise ValueError("Phase D dataset evidence mode is not admitted by the plan")
    if (
        dataset.get("require_research_evaluation_eligible", True)
        and manifest.get("research_evaluation_eligible") is not True
    ):
        raise ValueError("Phase D dataset is not research-evaluation eligible")
    if (
        dataset.get("require_research_promotion_ineligible", True)
        and manifest.get("research_promotion_eligible") is not False
    ):
        raise ValueError("Phase D evaluation-only dataset cannot carry promotion authority")
    if manifest.get("completeness") not in {None, "full_v1"}:
        raise ValueError("Phase D dataset must be the frozen full_v1 dataset")


def _criteria_pass(item: Mapping[str, Any], criteria: Mapping[str, Any]) -> bool:
    checks = [
        float(item["adjusted_p_value"]) <= float(criteria["max_adjusted_p_value"]),
        sum(float(value) > 0.0 for value in item["period_rmse_improvements"])
        >= int(criteria["minimum_positive_periods"]),
        sum(float(value) > 0.0 for value in item["regime_rmse_improvements"].values())
        >= int(criteria["minimum_positive_regimes"]),
    ]
    if criteria.get("require_positive_rmse_improvement", True):
        checks.append(float(item["rmse_improvement"]) > 0.0)
    if criteria.get("require_positive_ci_lower", True):
        checks.append(float(item["ci_lower"]) > 0.0)
    return all(checks)


def apply_robustness_criteria(
    result: dict[str, Any], config: Mapping[str, Any]
) -> dict[str, Any]:
    criteria = config.get("robustness")
    if not isinstance(criteria, Mapping):
        raise TypeError("Phase D config requires robustness criteria")
    baseline_model = str(result["baseline_model"])
    robust_models: list[str] = []
    for comparison in result["candidate_comparisons"]:
        is_baseline = str(comparison["model"]) == baseline_model
        robust = False if is_baseline else _criteria_pass(comparison, criteria)
        comparison["robust"] = robust
        if robust:
            robust_models.append(str(comparison["model"]))
    for effect in result["ablation_effects"]:
        effect["material_incremental_value"] = _criteria_pass(effect, criteria)

    result["robustness"] = {
        "criteria": dict(criteria),
        "robust_edge_models": robust_models,
        "disposition": "robust_edge_detected" if robust_models else "no_robust_edge",
        "research_evaluation_only": True,
        "research_promotion_allowed": False,
        "trading_authority": False,
    }
    return result


def _validate_evaluation_config(config: Mapping[str, Any]) -> None:
    if config.get("phase") != "D":
        raise ValueError("Phase D evaluation config has the wrong phase")
    if config.get("evaluation_scope") != "research_evaluation_only":
        raise ValueError("Phase D execution is restricted to research evaluation")
    walk = config.get("walk_forward")
    significance = config.get("significance")
    sensitivity = config.get("sensitivity")
    if not isinstance(walk, Mapping) or walk.get("strategy") != "expanding_walk_forward":
        raise ValueError("Phase D V1 requires expanding walk-forward evaluation")
    if not isinstance(significance, Mapping) or significance.get("method") != "moving_block_bootstrap":
        raise ValueError("Phase D V1 requires moving-block bootstrap significance")
    if significance.get("multiple_testing") != "benjamini_hochberg":
        raise ValueError("Phase D V1 requires Benjamini-Hochberg adjustment")
    if not isinstance(sensitivity, Mapping):
        raise TypeError("Phase D V1 requires sensitivity controls")
    if int(sensitivity.get("chronological_periods", 0)) != 3:
        raise ValueError("Phase D V1 currently requires three chronological periods")
    if sensitivity.get("regime_definition") != "absolute_target_return_initial_train_tertiles":
        raise ValueError("Phase D V1 regime definition does not match the evaluator")
    controls = config.get("controls", {})
    if controls.get("hyperparameter_tuning") != "prohibited":
        raise ValueError("Phase D V1 empirical run prohibits hyperparameter tuning")
    authority = config.get("authority", {})
    if authority.get("research_promotion_allowed") is not False:
        raise ValueError("Phase D V1 evaluation config cannot grant research promotion")
    if authority.get("trading_authority") is not False:
        raise ValueError("Phase D V1 evaluation config cannot grant trading authority")


def _build_plan(
    frame: pd.DataFrame,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    models: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, tuple[str, ...]]]:
    target_name = str(config["target"]["name"])
    if manifest.get("target") != target_name:
        raise ValueError("Phase D target does not match the frozen dataset target")
    mapping = feature_family_columns(frame, manifest, target=target_name)
    walk = config["walk_forward"]
    folds = build_walk_forward_folds(
        frame.index,
        initial_train=int(walk["initial_train_rows"]),
        retrain_every=int(walk["retrain_every_rows"]),
    )
    model_names = [str(name) for name in config["models"]]
    model_table = models.get("models")
    if not isinstance(model_table, Mapping):
        raise TypeError("Phase D models config requires a models object")
    selected_models = {name: model_table[name] for name in model_names if name in model_table}
    if set(selected_models) != set(model_names):
        missing = sorted(set(model_names) - set(selected_models))
        raise ValueError(f"Phase D model configurations are missing: {missing}")
    significance = config["significance"]
    plan = build_phase_d_plan(
        model_names=model_names,
        models=selected_models,
        baseline_model=str(config["baseline_model"]),
        target=config["target"],
        feature_families=list(mapping),
        split_strategy=str(walk["strategy"]),
        folds=folds,
        seeds=[int(significance["seed"])],
    )
    return plan, mapping


def _prediction_csv(frame: pd.DataFrame) -> str:
    return frame.to_csv(
        index=True,
        index_label="date",
        lineterminator="\n",
        float_format="%.17g",
    )


def _artifact_name(model: str, ablation: str) -> str:
    safe_ablation = ablation.replace(":", "_")
    return f"{model}__{safe_ablation}.csv"


def run_phase_d_from_frozen(
    *,
    dataset_dir: Path,
    config_path: Path,
    models_path: Path,
    dependency_lock_path: Path,
    output_dir: Path,
    code_commit: str,
) -> dict[str, Any]:
    if not _GIT_SHA_RE.fullmatch(code_commit):
        raise ValueError("Phase D code_commit must be an exact 40-character Git SHA")
    config = _load_json(config_path)
    models = _load_json(models_path)
    _validate_evaluation_config(config)

    manifest_path = Path(dataset_dir) / "manifest.json"
    manifest_sha256 = _file_sha256(manifest_path)
    frame, manifest = load_frozen_dataset(Path(dataset_dir))
    validate_phase_d_dataset_manifest(
        manifest, config, manifest_sha256=manifest_sha256
    )
    plan, mapping = _build_plan(frame, manifest, config, models)

    walk = config["walk_forward"]
    selected_models = models["models"]
    result, predictions = run_phase_d_evaluation(
        frame,
        manifest,
        model_names=[str(name) for name in config["models"]],
        models=selected_models,
        initial_train=int(walk["initial_train_rows"]),
        retrain_every=int(walk["retrain_every_rows"]),
        volatility_window=int(walk["volatility_window_rows"]),
        significance=config["significance"],
    )
    result = apply_robustness_criteria(result, config)

    output_dir = Path(output_dir)
    predictions_dir = output_dir / "predictions"
    predictions_dir.mkdir(parents=True, exist_ok=True)
    config_sha256 = _file_sha256(config_path)
    models_sha256 = _file_sha256(models_path)
    dependency_lock_sha256 = _file_sha256(dependency_lock_path)
    feature_definition_sha256 = _json_sha256(mapping)
    preprocessing_sha256 = _json_sha256(
        {
            "preprocessing": config["preprocessing"],
            "models": {name: selected_models[name] for name in config["models"]},
        }
    )

    candidates = {item["name"]: item for item in plan["candidates"]}
    ablations = {item["name"]: item for item in plan["ablations"]}
    evaluation_index = {
        (item["model"], item["ablation"]): item for item in result["evaluations"]
    }

    artifact_index: list[dict[str, Any]] = []
    seed = int(config["significance"]["seed"])
    for key, prediction in predictions.items():
        model, ablation = key.split("|", 1)
        filename = _artifact_name(model, ablation)
        prediction_path = predictions_dir / filename
        prediction_path.write_text(
            _prediction_csv(prediction), encoding="utf-8", newline=""
        )
        predictions_sha256 = _file_sha256(prediction_path)
        evaluation = evaluation_index[(model, ablation)]
        evaluation_sha256 = _json_sha256(evaluation)
        lineage = validate_phase_d_lineage(
            plan,
            {
                "selection": {
                    "candidate_id": candidates[model]["candidate_id"],
                    "ablation_id": ablations[ablation]["ablation_id"],
                    "seed": seed,
                },
                "dataset": {
                    "id": manifest["dataset_id"],
                    "sha256": manifest["dataset_sha256"],
                    "manifest_sha256": manifest_sha256,
                },
                "features": {
                    "definition_sha256": feature_definition_sha256,
                    "preprocessing_sha256": preprocessing_sha256,
                },
                "experiment_config_sha256": config_sha256,
                "code": {"commit_sha": code_commit},
                "environment": {"dependency_lock_sha256": dependency_lock_sha256},
                "artifacts": {
                    "predictions_sha256": predictions_sha256,
                    "evaluation_sha256": evaluation_sha256,
                },
            },
        )
        artifact_index.append(
            {
                "model": model,
                "ablation": ablation,
                "predictions_path": f"predictions/{filename}",
                "predictions_sha256": predictions_sha256,
                "evaluation_sha256": evaluation_sha256,
                "lineage": lineage,
            }
        )

    evidence: dict[str, Any] = {
        "schema_version": 1,
        "phase": "D",
        "dataset": {
            "dataset_id": manifest["dataset_id"],
            "freeze_id": manifest["freeze_id"],
            "dataset_sha256": manifest["dataset_sha256"],
            "manifest_sha256": manifest_sha256,
            "rows": len(frame),
            "oos_rows": len(frame) - int(walk["initial_train_rows"]),
            "audit_verdict": manifest.get("dataset_audit", {}).get("verdict"),
        },
        "execution": {
            "code_commit": code_commit.lower(),
            "phase_d_config_sha256": config_sha256,
            "models_config_sha256": models_sha256,
            "dependency_lock_sha256": dependency_lock_sha256,
            "hyperparameter_tuning": "prohibited",
        },
        "plan": plan,
        "results": result,
        "artifacts": artifact_index,
        "authority": {
            "research_evaluation_eligible": True,
            "research_promotion_eligible": False,
            "trading_authority": False,
        },
    }
    evidence["evidence_sha256"] = _json_sha256(evidence)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run frozen V1 Phase D research evaluation")
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--dependency-lock", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--evidence-output", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    evidence = run_phase_d_from_frozen(
        dataset_dir=args.dataset_dir,
        config_path=args.config,
        models_path=args.models,
        dependency_lock_path=args.dependency_lock,
        output_dir=args.output_dir,
        code_commit=args.code_commit,
    )
    if args.evidence_output is not None:
        args.evidence_output.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_output.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )


if __name__ == "__main__":
    main()
