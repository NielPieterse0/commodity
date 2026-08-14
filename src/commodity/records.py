from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from commodity.config import REPO_ROOT, experiment_config, model_config
from commodity.provenance import git_code_state, sha256_file, utc_now


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_baseline_record(
    input_path: Path,
    run_dir: Path,
    model_name: str,
    metrics: dict[str, float],
    feature_index: pd.DatetimeIndex,
    initial_train: int,
) -> dict[str, Any]:
    exp = experiment_config()
    models = model_config()["models"]
    meta = _read_json(input_path.with_suffix(".meta.json"))
    prediction_path = run_dir / "predictions.csv"
    metrics_path = run_dir / "metrics.json"
    feature_path = REPO_ROOT / "src/commodity/features.py"
    preprocessing_path = REPO_ROOT / "src/commodity/data.py"
    lock_path = REPO_ROOT / "requirements.lock.txt"
    model_cfg = models[model_name]
    family = model_cfg["family"]
    architecture = model_cfg["architecture"]
    return {
        "schema_version": 2,
        "experiment_id": exp["experiment_id"],
        "run_id": f"{model_name}-{utc_now()}",
        "project": "commodity",
        "hypothesis": exp["hypothesis"],
        "forecast": {
            "target": exp["target"]["name"],
            "horizon": f"{exp['target']['horizon_sessions']} trading session",
            "prediction_timestamp_semantics": exp["target"]["information_cutoff"],
            "target_timestamp_semantics": "next completed daily market bar",
            "information_cutoff_semantics": exp["target"]["information_cutoff"],
        },
        "datasets": [{
            "role": "evaluation", "id": "ng_f_daily_bootstrap",
            "version": meta["sha256"][:12], "sha256": meta["sha256"],
            "as_of": meta["fetched_at_utc"],
            "vintage": meta.get("vintage", f"retrieval_snapshot:{meta['fetched_at_utc']}"),
        }],
        "split": {
            "strategy": "expanding_walk_forward",
            "seed": 0,
            "train": {
                "start": feature_index[0].isoformat(),
                "end": feature_index[initial_train - 1].isoformat(),
            },
            "validation": None,
            "test": {
                "start": feature_index[initial_train].isoformat(),
                "end": feature_index[-1].isoformat(),
            },
        },
        "features": {
            "definition_id": "commodity.features.build_market_features:v1",
            "definition_sha256": sha256_file(feature_path),
            "preprocessing_id": "commodity.data.normalize_ohlcv:v1",
            "preprocessing_sha256": sha256_file(preprocessing_path),
        },
        "model": {
            "family": family,
            "architecture": architecture,
            "configuration_id": f"config/models.json#{model_name}",
            "checkpoint": None,
            "checkpoint_sha256": None,
        },
        "training": {
            "seeds": [0],
            "hyperparameters": model_cfg,
            "epochs": None,
        },
        "evaluation": {
            "primary_metric": "rmse",
            "metrics": metrics,
            "baselines": [{
                "id": "zero_return", "type": "forecast_baseline",
                "configuration_id": "config/models.json#naive",
            }],
        },
        "controls": {
            "leakage_check": exp["controls"]["leakage_check"],
            "permutation_test": None,
            "multiple_testing": None,
            "reproducibility_runs": exp["controls"]["reproducibility_runs"],
        },
        "results": {
            "primary_metric_value": metrics["rmse"],
            "uncertainty": None,
            "significance": None,
            "stability": None,
        },
        "decision": {
            "disposition": exp["decision"]["disposition"],
            "rationale": exp["decision"]["rationale"],
            "scope": "research_only",
        },
        "lineage": {
            "code_revision": git_code_state(REPO_ROOT),
            "environment": {
                "runtime": "python", "runtime_version": sys.version.split()[0],
                "dependency_lock_sha256": sha256_file(lock_path),
                "hardware_id": "docs/environment/lenovo-laptop-specification-v0.1.md",
            },
            "artifacts": [
                {
                    "role": "predictions", "uri": str(prediction_path),
                    "sha256": sha256_file(prediction_path),
                },
                {
                    "role": "metrics", "uri": str(metrics_path),
                    "sha256": sha256_file(metrics_path),
                },
            ],
        },
    }


def build_tournament_record(
    *,
    dataset_manifest: dict[str, Any],
    dataset_path: Path,
    model_dir: Path,
    model_name: str,
    metrics: dict[str, float],
    feature_index: pd.DatetimeIndex,
    initial_train: int,
    significance: dict[str, Any],
    leakage_check: str,
) -> dict[str, Any]:
    exp = experiment_config()
    models = model_config()["models"]
    model_cfg = models[model_name]
    prediction_path = model_dir / "predictions.csv"
    metrics_path = model_dir / "metrics.json"
    dataset_hash = str(dataset_manifest["dataset_sha256"])
    feature_path = REPO_ROOT / "src/commodity/features.py"
    preprocessing_path = REPO_ROOT / "src/commodity/research_dataset.py"
    lock_path = REPO_ROOT / "requirements.lock.txt"
    return {
        "schema_version": 2,
        "experiment_id": exp["experiment_id"],
        "run_id": f"tournament-{model_name}-{utc_now()}",
        "project": "commodity",
        "hypothesis": exp["hypothesis"],
        "forecast": {
            "target": exp["target"]["name"],
            "horizon": f"{exp['target']['horizon_sessions']} trading session",
            "prediction_timestamp_semantics": exp["target"]["information_cutoff"],
            "target_timestamp_semantics": "next completed daily market bar",
            "information_cutoff_semantics": exp["target"]["information_cutoff"],
        },
        "datasets": [{
            "role": "evaluation",
            "id": str(dataset_manifest["dataset_id"]),
            "version": dataset_hash[:12],
            "sha256": dataset_hash,
            "as_of": str(dataset_manifest["end"]),
            "vintage": f"frozen_dataset:{dataset_hash[:12]}",
        }],
        "split": {
            "strategy": exp["tournament"]["split_strategy"],
            "seed": int(exp["tournament"]["significance"]["seed"]),
            "train": {
                "start": feature_index[0].isoformat(),
                "end": feature_index[initial_train - 1].isoformat(),
            },
            "validation": None,
            "test": {
                "start": feature_index[initial_train].isoformat(),
                "end": feature_index[-1].isoformat(),
            },
        },
        "features": {
            "definition_id": "commodity.features.build_market_features:v1",
            "definition_sha256": sha256_file(feature_path),
            "preprocessing_id": "commodity.research_dataset.build_pit_dataset:v1",
            "preprocessing_sha256": sha256_file(preprocessing_path),
        },
        "model": {
            "family": model_cfg["family"],
            "architecture": model_cfg["architecture"],
            "configuration_id": f"config/models.json#{model_name}",
            "checkpoint": None,
            "checkpoint_sha256": None,
        },
        "training": {
            "seeds": [0],
            "hyperparameters": model_cfg,
            "epochs": None,
        },
        "evaluation": {
            "primary_metric": exp["tournament"]["primary_metric"],
            "metrics": metrics,
            "baselines": [{
                "id": exp["tournament"]["baseline_model"],
                "type": "forecast_baseline",
                "configuration_id": (
                    f"config/models.json#{exp['tournament']['baseline_model']}"
                ),
            }],
        },
        "controls": {
            "leakage_check": leakage_check,
            "permutation_test": None,
            "multiple_testing": None,
            "reproducibility_runs": exp["controls"]["reproducibility_runs"],
        },
        "results": {
            "primary_metric_value": float(metrics[exp["tournament"]["primary_metric"]]),
            "uncertainty": {
                "method": significance["method"],
                "ci_lower": significance["ci_lower"],
                "ci_upper": significance["ci_upper"],
                "confidence": exp["tournament"]["significance"]["confidence"],
            },
            "significance": significance,
            "stability": None,
        },
        "decision": {
            "disposition": exp["decision"]["disposition"],
            "rationale": exp["decision"]["rationale"],
            "scope": "research_only",
        },
        "lineage": {
            "code_revision": git_code_state(REPO_ROOT),
            "environment": {
                "runtime": "python",
                "runtime_version": sys.version.split()[0],
                "dependency_lock_sha256": sha256_file(lock_path),
                "hardware_id": "docs/environment/lenovo-laptop-specification-v0.1.md",
            },
            "artifacts": [
                {
                    "role": "dataset",
                    "uri": str(dataset_path),
                    "sha256": sha256_file(dataset_path),
                },
                {
                    "role": "predictions",
                    "uri": str(prediction_path),
                    "sha256": sha256_file(prediction_path),
                },
                {
                    "role": "metrics",
                    "uri": str(metrics_path),
                    "sha256": sha256_file(metrics_path),
                },
            ],
        },
    }
