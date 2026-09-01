from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from commodity.config import REPO_ROOT, config_path, experiment_config
from commodity.data_assurance import (
    assert_research_ready,
    build_reconstruction_contract,
)
from commodity.dataset_audit import audit_full_v1_dataset
from commodity.provenance import sha256_file
from commodity.research_dataset import dataframe_sha256


class FrozenDatasetIntegrityError(RuntimeError):
    pass


def _json_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _dataset_csv(frame: pd.DataFrame) -> str:
    canonical = frame.copy()
    canonical.index = pd.to_datetime(canonical.index, utc=True)
    return canonical.to_csv(
        index=True,
        index_label="prediction_time",
        lineterminator="\n",
        float_format="%.17g",
    )


def _validate_full_v1(frame: pd.DataFrame, manifest: dict[str, Any]) -> None:
    required = tuple(experiment_config()["dataset"]["required_feature_families"])
    included = set(manifest.get("included_feature_families", []))
    missing = set(manifest.get("missing_feature_families", []))
    if manifest.get("completeness") != "full_v1":
        raise ValueError("Only a full_v1 dataset may be frozen")
    if not set(required).issubset(included) or missing:
        raise ValueError("full_v1 manifest is missing required feature families")
    if manifest.get("evidence_mode") not in {"research_pit", "evaluation_pit", "canonical"}:
        raise ValueError("full_v1 freeze requires PIT-admissible evidence mode")
    expected = str(manifest.get("dataset_sha256", ""))
    actual = dataframe_sha256(frame)
    if expected != actual:
        raise ValueError("Dataset bytes do not match upstream dataset_sha256")
    if int(manifest.get("rows", -1)) != len(frame):
        raise ValueError("Dataset row count does not match upstream manifest")
    assert_research_ready(manifest.get("data_assurance"))


def _stable_lineage(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "exogenous_sources": manifest.get("exogenous_sources", []),
        "exogenous_family_audits": manifest.get("exogenous_family_audits", {}),
        "market_structure": manifest.get("market_structure"),
    }


def _freeze_manifest(
    frame: pd.DataFrame,
    upstream: dict[str, Any],
    dataset_audit: dict[str, Any],
) -> dict[str, Any]:
    dataset_hash = dataframe_sha256(frame)
    experiment = experiment_config()
    configuration_sha256 = {
        "experiment": sha256_file(config_path("experiment.json")),
        "data_sources": sha256_file(config_path("data_sources.json")),
        "assumptions": sha256_file(config_path("assumptions.json")),
        "research_methodology": sha256_file(config_path("research_methodology.json")),
    }
    transformation_sha256 = {
        name.removesuffix(".py"): sha256_file(REPO_ROOT / "src" / "commodity" / name)
        for name in (
            "research_dataset.py", "availability.py", "features.py", "market_data.py",
            "rolls.py", "roll_policy.py", "roll_safe_market.py", "exogenous_audit.py",
            "dataset_audit.py", "dataset_freeze.py", "data_assurance.py",
        )
    }
    upstream_assurance = assert_research_ready(upstream.get("data_assurance"))
    freeze_assurance = build_reconstruction_contract(
        source_inputs=list(upstream_assurance["source_inputs"]),
        layers=[
            *list(upstream_assurance["layers"]),
            {"name": "experiment_freeze", "status": "verified", "sha256": dataset_hash},
        ],
        transformation_sha256={
            **dict(upstream_assurance["transformation_sha256"]),
            **transformation_sha256,
        },
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "dataset_id": upstream["dataset_id"],
        "dataset_sha256": dataset_hash,
        "dataset_artifact_sha256": dataset_hash,
        "upstream_manifest_sha256": _json_sha256(upstream),
        "completeness": "full_v1",
        "evidence_mode": upstream["evidence_mode"],
        "market_evaluation_evidence": upstream.get("market_evaluation_evidence", False),
        "canonical_market_evidence": upstream.get("canonical_market_evidence", False),
        "research_evaluation_eligible": upstream.get("research_evaluation_eligible", False),
        "research_promotion_eligible": upstream.get("research_promotion_eligible", False),
        "grain": "one row per prediction_time",
        "unique_key": ["prediction_time"],
        "rows": len(frame),
        "columns": list(frame.columns),
        "start": pd.Timestamp(frame.index[0]).isoformat(),
        "end": pd.Timestamp(frame.index[-1]).isoformat(),
        "target": upstream["target"],
        "prediction_timestamp_semantics": upstream["prediction_timestamp_semantics"],
        "required_feature_families": upstream["required_feature_families"],
        "included_feature_families": upstream["included_feature_families"],
        "missing_feature_families": upstream["missing_feature_families"],
        "initial_train_rows": int(experiment["walk_forward"]["initial_train_rows"]),
        "source_lineage": _stable_lineage(upstream),
        "dataset_audit": dataset_audit,
        "data_assurance": freeze_assurance,
        "configuration_sha256": configuration_sha256,
        "transformation_sha256": transformation_sha256,
    }
    payload["freeze_id"] = _json_sha256(payload)[:16]
    return payload


def _verify_existing(directory: Path, expected: dict[str, Any]) -> None:
    manifest_path = directory / "manifest.json"
    dataset_path = directory / "dataset.csv"
    upstream_path = directory / "upstream-manifest.json"
    if not manifest_path.is_file() or not dataset_path.is_file() or not upstream_path.is_file():
        raise FrozenDatasetIntegrityError("Frozen dataset directory is incomplete")
    actual = json.loads(manifest_path.read_text(encoding="utf-8"))
    if actual != expected:
        raise FrozenDatasetIntegrityError("Existing frozen manifest conflicts with requested freeze")
    if sha256_file(dataset_path) != expected["dataset_artifact_sha256"]:
        raise FrozenDatasetIntegrityError("Existing frozen dataset artifact failed hash verification")
    upstream = json.loads(upstream_path.read_text(encoding="utf-8"))
    if _json_sha256(upstream) != expected["upstream_manifest_sha256"]:
        raise FrozenDatasetIntegrityError("Frozen upstream manifest failed hash verification")


def freeze_full_v1_dataset(
    frame: pd.DataFrame,
    upstream_manifest: dict[str, Any],
    output_root: Path,
) -> Path:
    _validate_full_v1(frame, upstream_manifest)
    audit = audit_full_v1_dataset(frame, upstream_manifest)
    if audit.verdict == "not-fit":
        raise ValueError(f"full_v1 dataset failed independent audit: {audit.blockers}")
    frozen_manifest = _freeze_manifest(frame, upstream_manifest, audit.to_dict())
    directory = Path(output_root) / f"{upstream_manifest['dataset_id']}-{frozen_manifest['freeze_id']}"
    if directory.exists():
        _verify_existing(directory, frozen_manifest)
        return directory
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir()
    (directory / "dataset.csv").write_text(_dataset_csv(frame), encoding="utf-8", newline="")
    (directory / "manifest.json").write_text(
        json.dumps(frozen_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    (directory / "upstream-manifest.json").write_text(
        json.dumps(upstream_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    _verify_existing(directory, frozen_manifest)
    return directory


def load_frozen_dataset(directory: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    _verify_existing(directory, manifest)
    expected_freeze_id = _json_sha256(
        {key: value for key, value in manifest.items() if key != "freeze_id"}
    )[:16]
    if manifest.get("freeze_id") != expected_freeze_id:
        raise FrozenDatasetIntegrityError("Frozen manifest identity is invalid")
    frame = pd.read_csv(
        directory / "dataset.csv",
        index_col="prediction_time",
        float_precision="round_trip",
    )
    frame.index = pd.to_datetime(frame.index, utc=True)
    frame.index.name = None
    if dataframe_sha256(frame) != manifest.get("dataset_sha256"):
        raise FrozenDatasetIntegrityError("Frozen dataset content hash is invalid")
    try:
        assert_research_ready(manifest.get("data_assurance"))
    except Exception as exc:
        raise FrozenDatasetIntegrityError("Frozen dataset data-assurance contract is invalid") from exc
    return frame, manifest
