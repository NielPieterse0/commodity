from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

_SUPPORTED_SPLITS = {"expanding_walk_forward", "rolling_walk_forward"}
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_GIT_SHA_RE = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Phase D contract values must be JSON-serializable") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _json_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _ordered_unique_strings(values: Sequence[str], *, label: str) -> list[str]:
    result = [str(value).strip() for value in values]
    if not result or any(not value for value in result):
        raise ValueError(f"{label} must contain non-empty values")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must be unique")
    return result


def _utc_timestamp(value: Any, *, label: str) -> tuple[datetime, str]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a valid timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    utc = parsed.astimezone(UTC)
    return utc, utc.isoformat()


def _normalize_folds(
    folds: Sequence[Mapping[str, Any]],
    *,
    split_strategy: str,
) -> list[dict[str, str]]:
    if not folds:
        raise ValueError("Phase D fold contract requires at least one fold")
    if split_strategy not in _SUPPORTED_SPLITS:
        raise ValueError(f"Unsupported Phase D fold strategy: {split_strategy!r}")
    normalized: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    first_train_start: datetime | None = None
    previous_train_start: datetime | None = None
    previous_train_end: datetime | None = None
    previous_test_end: datetime | None = None
    for position, fold in enumerate(folds):
        fold_id = str(fold.get("fold_id", "")).strip()
        if not fold_id or fold_id in seen_ids:
            raise ValueError("Phase D fold IDs must be non-empty and unique")
        seen_ids.add(fold_id)
        train_start, train_start_text = _utc_timestamp(
            fold.get("train_start"), label=f"fold {fold_id} train_start"
        )
        train_end, train_end_text = _utc_timestamp(
            fold.get("train_end"), label=f"fold {fold_id} train_end"
        )
        test_start, test_start_text = _utc_timestamp(
            fold.get("test_start"), label=f"fold {fold_id} test_start"
        )
        test_end, test_end_text = _utc_timestamp(
            fold.get("test_end"), label=f"fold {fold_id} test_end"
        )
        if train_start > train_end or test_start > test_end:
            raise ValueError(f"Phase D fold {fold_id} has an empty period")
        if train_end >= test_start:
            raise ValueError(f"Phase D fold {fold_id} overlaps train and test periods")
        if previous_test_end is not None and previous_test_end >= test_start:
            raise ValueError(
                "Phase D test folds must be chronological and non-overlapping"
            )
        if position == 0:
            first_train_start = train_start
        elif split_strategy == "expanding_walk_forward":
            if train_start != first_train_start:
                raise ValueError("Expanding Phase D folds must share one train_start")
            if previous_train_end is not None and train_end < previous_train_end:
                raise ValueError(
                    "Expanding Phase D folds cannot shrink training history"
                )
        elif previous_train_start is not None and train_start < previous_train_start:
            raise ValueError("Rolling Phase D folds must advance chronologically")
        if previous_train_end is not None and train_end < previous_train_end:
            raise ValueError("Phase D fold train_end values must be chronological")

        normalized.append(
            {
                "fold_id": fold_id,
                "train_start": train_start_text,
                "train_end": train_end_text,
                "test_start": test_start_text,
                "test_end": test_end_text,
            }
        )
        previous_train_start = train_start
        previous_train_end = train_end
        previous_test_end = test_end
    return normalized


def _build_ablations(feature_families: list[str]) -> list[dict[str, Any]]:
    definitions = [
        {
            "name": "full",
            "included_families": feature_families,
            "excluded_families": [],
        }
    ]
    for excluded in feature_families:
        definitions.append(
            {
                "name": f"without:{excluded}",
                "included_families": [
                    family for family in feature_families if family != excluded
                ],
                "excluded_families": [excluded],
            }
        )
    for definition in definitions:
        definition["ablation_id"] = _sha256(definition)
    return definitions


def _normalize_seeds(seeds: Sequence[int]) -> list[int]:
    normalized = list(seeds)
    if not normalized or any(
        not isinstance(seed, int) or isinstance(seed, bool) for seed in normalized
    ):
        raise ValueError("Phase D seeds must be non-empty integers")
    if len(normalized) != len(set(normalized)):
        raise ValueError("Phase D seeds must be unique")
    return normalized


def build_phase_d_plan(
    *,
    model_names: Sequence[str],
    models: Mapping[str, Mapping[str, Any]],
    baseline_model: str,
    target: Mapping[str, Any],
    feature_families: Sequence[str],
    split_strategy: str,
    folds: Sequence[Mapping[str, Any]],
    seeds: Sequence[int],
) -> dict[str, Any]:
    names = _ordered_unique_strings(model_names, label="Phase D model names")
    if names[0] != baseline_model:
        raise ValueError("Phase D baseline model must be first in model_names")
    if any(name not in models for name in names):
        missing = [name for name in names if name not in models]
        raise ValueError(f"Phase D model configurations are missing: {missing}")
    target_copy = _json_copy(target)
    if (
        not isinstance(target_copy, dict)
        or not str(target_copy.get("name", "")).strip()
    ):
        raise ValueError("Phase D target requires a non-empty name")
    families = _ordered_unique_strings(
        feature_families, label="Phase D feature families"
    )
    normalized_seeds = _normalize_seeds(seeds)
    normalized_folds = _normalize_folds(folds, split_strategy=split_strategy)
    split = {
        "strategy": split_strategy,
        "folds": normalized_folds,
    }
    split["split_id"] = _sha256(split)

    candidates: list[dict[str, Any]] = []
    for order, name in enumerate(names):
        configuration = _json_copy(models[name])
        configuration_sha256 = _sha256(configuration)
        candidate_payload = {
            "name": name,
            "order": order,
            "configuration_sha256": configuration_sha256,
            "target": target_copy,
            "split_id": split["split_id"],
            "seeds": normalized_seeds,
        }
        candidates.append(
            {
                "name": name,
                "order": order,
                "configuration_sha256": configuration_sha256,
                "candidate_id": _sha256(candidate_payload),
            }
        )
    plan: dict[str, Any] = {
        "schema_version": 1,
        "baseline_model": baseline_model,
        "target": target_copy,
        "feature_families": families,
        "seeds": normalized_seeds,
        "split": split,
        "candidates": candidates,
        "ablations": _build_ablations(families),
        "lineage_contract": {
            "selection": ["candidate_id", "ablation_id", "seed"],
            "dataset": ["id", "sha256", "manifest_sha256"],
            "features": ["definition_sha256", "preprocessing_sha256"],
            "experiment": ["experiment_config_sha256"],
            "code": ["commit_sha"],
            "environment": ["dependency_lock_sha256"],
            "artifacts": ["predictions_sha256", "evaluation_sha256"],
        },
        "preserve_all_candidates": True,
        "preserve_negative_results": True,
    }
    plan["plan_id"] = _sha256(plan)
    return plan


def _require_sha256(value: Any, *, label: str) -> str:
    text = str(value)
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"Phase D lineage {label} must be a SHA-256 digest")
    return text.lower()


def _require_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"Phase D lineage {label} must be an object")
    return value


def validate_phase_d_lineage(
    plan: Mapping[str, Any],
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    plan_copy = _json_copy(plan)
    plan_id = str(plan_copy.pop("plan_id", ""))
    if not _SHA256_RE.fullmatch(plan_id) or _sha256(plan_copy) != plan_id:
        raise ValueError("Phase D plan_id does not match the supplied plan")

    selection = _require_mapping(lineage.get("selection"), label="selection")
    candidate_id = _require_sha256(
        selection.get("candidate_id"), label="selection.candidate_id"
    )
    candidate_ids = [str(item["candidate_id"]) for item in plan["candidates"]]
    if candidate_id not in candidate_ids:
        raise ValueError("Phase D lineage selection.candidate_id is not in the plan")
    ablation_id = _require_sha256(
        selection.get("ablation_id"), label="selection.ablation_id"
    )
    ablation_ids = [str(item["ablation_id"]) for item in plan["ablations"]]
    if ablation_id not in ablation_ids:
        raise ValueError("Phase D lineage selection.ablation_id is not in the plan")
    seed = selection.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed not in plan["seeds"]:
        raise ValueError("Phase D lineage selection.seed is not in the plan")

    dataset = _require_mapping(lineage.get("dataset"), label="dataset")
    dataset_id = str(dataset.get("id", "")).strip()
    if not dataset_id:
        raise ValueError("Phase D lineage dataset id must be non-empty")
    dataset_sha256 = _require_sha256(dataset.get("sha256"), label="dataset.sha256")
    manifest_sha256 = _require_sha256(
        dataset.get("manifest_sha256"), label="dataset.manifest_sha256"
    )
    features = _require_mapping(lineage.get("features"), label="features")
    definition_sha256 = _require_sha256(
        features.get("definition_sha256"), label="features.definition_sha256"
    )
    preprocessing_sha256 = _require_sha256(
        features.get("preprocessing_sha256"), label="features.preprocessing_sha256"
    )
    experiment_config_sha256 = _require_sha256(
        lineage.get("experiment_config_sha256"), label="experiment_config_sha256"
    )
    code = _require_mapping(lineage.get("code"), label="code")
    commit_sha = str(code.get("commit_sha", ""))
    if not _GIT_SHA_RE.fullmatch(commit_sha):
        raise ValueError("Phase D lineage code.commit_sha must be a Git commit digest")
    environment = _require_mapping(lineage.get("environment"), label="environment")
    dependency_lock_sha256 = _require_sha256(
        environment.get("dependency_lock_sha256"),
        label="environment.dependency_lock_sha256",
    )
    artifacts = _require_mapping(lineage.get("artifacts"), label="artifacts")
    predictions_sha256 = _require_sha256(
        artifacts.get("predictions_sha256"), label="artifacts.predictions_sha256"
    )
    evaluation_sha256 = _require_sha256(
        artifacts.get("evaluation_sha256"), label="artifacts.evaluation_sha256"
    )

    bound: dict[str, Any] = {
        "schema_version": 1,
        "plan_id": plan_id,
        "split_id": str(plan["split"]["split_id"]),
        "selection": {
            "candidate_id": candidate_id,
            "ablation_id": ablation_id,
            "seed": seed,
        },
        "candidate_ids": candidate_ids,
        "ablation_ids": ablation_ids,
        "dataset": {
            "id": dataset_id,
            "sha256": dataset_sha256,
            "manifest_sha256": manifest_sha256,
        },
        "features": {
            "definition_sha256": definition_sha256,
            "preprocessing_sha256": preprocessing_sha256,
        },
        "experiment_config_sha256": experiment_config_sha256,
        "code": {"commit_sha": commit_sha.lower()},
        "environment": {"dependency_lock_sha256": dependency_lock_sha256},
        "artifacts": {
            "predictions_sha256": predictions_sha256,
            "evaluation_sha256": evaluation_sha256,
        },
    }
    bound["lineage_id"] = _sha256(bound)
    return bound
