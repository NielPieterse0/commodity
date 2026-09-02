from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd


class DataAssuranceError(RuntimeError):
    """Raised when governed research data cannot prove reconstruction and semantics."""


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_records_sha256(frame: pd.DataFrame) -> str:
    """Hash tabular source records independently of incidental column ordering."""
    canonical = frame.copy()
    canonical = canonical.reindex(sorted(str(column) for column in canonical.columns), axis=1)
    records = canonical.where(pd.notna(canonical), None).to_dict(orient="records")
    return canonical_json_sha256(records)


def canonical_frame_sha256(frame: pd.DataFrame) -> str:
    canonical = frame.copy()
    canonical.index = canonical.index.map(str)
    payload = {
        "index": list(canonical.index),
        "index_name": canonical.index.name,
        "columns": [str(column) for column in canonical.columns],
        "records_sha256": canonical_records_sha256(canonical),
        "rows": len(canonical),
    }
    return canonical_json_sha256(payload)


def file_identity(paths: Iterable[Path]) -> dict[str, str]:
    identities: dict[str, str] = {}
    for path in paths:
        concrete = Path(path)
        identities[concrete.name] = hashlib.sha256(concrete.read_bytes()).hexdigest()
    return identities


def verify_reconstructed_frame(
    expected: pd.DataFrame,
    reconstructed: pd.DataFrame,
    *,
    layer: str,
) -> dict[str, Any]:
    if list(expected.columns) != list(reconstructed.columns):
        raise DataAssuranceError(f"{layer} reconstruction columns differ")
    if not expected.index.equals(reconstructed.index):
        raise DataAssuranceError(f"{layer} reconstruction timestamps/index differ")
    if len(expected) != len(reconstructed):
        raise DataAssuranceError(f"{layer} reconstruction row count differs")
    try:
        pd.testing.assert_frame_equal(expected, reconstructed, check_exact=True)
    except AssertionError as exc:
        raise DataAssuranceError(f"{layer} reconstruction values differ") from exc
    digest = canonical_frame_sha256(expected)
    if digest != canonical_frame_sha256(reconstructed):
        raise DataAssuranceError(f"{layer} reconstruction identity differs")
    return {"name": layer, "status": "verified", "sha256": digest}


def _validate_contract_components(
    source_inputs: list[dict[str, Any]],
    transformation_sha256: dict[str, str],
) -> None:
    if not source_inputs:
        raise DataAssuranceError("reconstruction contract requires retained source inputs")
    for source in source_inputs:
        digest = str(source.get("sha256", ""))
        if len(digest) != 64:
            raise DataAssuranceError("retained source input lacks canonical SHA-256 identity")
    if not transformation_sha256 or any(
        len(str(value)) != 64 for value in transformation_sha256.values()
    ):
        raise DataAssuranceError("material transformation identity is incomplete")


def _assert_assurance_identity(assurance: dict[str, Any]) -> None:
    expected = str(assurance.get("assurance_sha256", ""))
    actual = canonical_json_sha256(
        {key: value for key, value in assurance.items() if key != "assurance_sha256"}
    )
    if expected != actual:
        raise DataAssuranceError("research dataset assurance identity is invalid")


def build_construction_contract(
    *,
    source_inputs: list[dict[str, Any]],
    layers: list[dict[str, Any]],
    transformation_sha256: dict[str, str],
) -> dict[str, Any]:
    _validate_contract_components(source_inputs, transformation_sha256)
    if not layers or any(item.get("status") != "constructed" for item in layers):
        raise DataAssuranceError("construction layers must be explicitly marked constructed")
    contract = {
        "schema_version": 1,
        "source_inputs": source_inputs,
        "layers": layers,
        "transformation_sha256": dict(sorted(transformation_sha256.items())),
        "reconstruction_status": "pending_reconstruction_verification",
        "semantic_status": "pending_semantic_verification",
        "comparison_contract": "rows_columns_timestamps_values_and_canonical_identity",
    }
    contract["assurance_sha256"] = canonical_json_sha256(contract)
    return contract


def _build_verified_contract(
    *,
    source_inputs: list[dict[str, Any]],
    layers: list[dict[str, Any]],
    transformation_sha256: dict[str, str],
    semantic_status: str,
    semantic_verification_method: str | None = None,
    semantic_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_contract_components(source_inputs, transformation_sha256)
    if not layers or any(item.get("status") != "verified" for item in layers):
        raise DataAssuranceError("every reconstruction layer must be verified")
    if semantic_status not in {"pending_semantic_verification", "verified"}:
        raise DataAssuranceError("semantic verification status is invalid")
    contract = {
        "schema_version": 1,
        "source_inputs": source_inputs,
        "layers": layers,
        "transformation_sha256": dict(sorted(transformation_sha256.items())),
        "reconstruction_status": "verified",
        "semantic_status": semantic_status,
        "verification_method": "deterministic_rebuild_exact_comparison",
        "comparison_contract": "rows_columns_timestamps_values_and_canonical_identity",
    }
    if semantic_verification_method is not None:
        contract["semantic_verification_method"] = semantic_verification_method
    if semantic_evidence is not None:
        contract["semantic_evidence"] = semantic_evidence
    contract["assurance_sha256"] = canonical_json_sha256(contract)
    return contract


def verify_reconstruction_pair(
    expected: pd.DataFrame,
    expected_assurance: dict[str, Any],
    reconstructed: pd.DataFrame,
    reconstructed_assurance: dict[str, Any],
) -> dict[str, Any]:
    for assurance in (expected_assurance, reconstructed_assurance):
        _assert_assurance_identity(assurance)
        if assurance.get("reconstruction_status") != "pending_reconstruction_verification":
            raise DataAssuranceError("reconstruction comparison requires provisional assurance")
    if expected_assurance.get("source_inputs") != reconstructed_assurance.get("source_inputs"):
        raise DataAssuranceError("reconstruction source inputs differ")
    if expected_assurance.get("transformation_sha256") != reconstructed_assurance.get(
        "transformation_sha256"
    ):
        raise DataAssuranceError("reconstruction transformation identity differs")

    expected_layers = [
        (item.get("name"), item.get("sha256")) for item in expected_assurance.get("layers", [])
    ]
    reconstructed_layers = [
        (item.get("name"), item.get("sha256"))
        for item in reconstructed_assurance.get("layers", [])
    ]
    if expected_layers != reconstructed_layers:
        raise DataAssuranceError("reconstruction layer identities differ")

    comparison = verify_reconstructed_frame(
        expected,
        reconstructed,
        layer="repeat_full_dataset_rebuild",
    )
    verified_layers = [
        {"name": name, "status": "verified", "sha256": digest}
        for name, digest in expected_layers
    ]
    verified_layers.append(comparison)
    return _build_verified_contract(
        source_inputs=list(expected_assurance["source_inputs"]),
        layers=verified_layers,
        transformation_sha256=dict(expected_assurance["transformation_sha256"]),
        semantic_status="pending_semantic_verification",
    )


def verify_semantic_assurance(
    assurance: dict[str, Any],
    *,
    semantic_evidence: dict[str, Any],
) -> dict[str, Any]:
    _assert_assurance_identity(assurance)
    if assurance.get("reconstruction_status") != "verified":
        raise DataAssuranceError("semantic verification requires verified reconstruction")
    if assurance.get("semantic_status") != "pending_semantic_verification":
        raise DataAssuranceError("semantic verification requires pending semantic assurance")
    method = str(semantic_evidence.get("method", ""))
    checks = semantic_evidence.get("checks")
    if method != "explicit_dataset_semantics_v1":
        raise DataAssuranceError("semantic verification method is unsupported")
    if not isinstance(checks, dict) or not checks or any(value is not True for value in checks.values()):
        raise DataAssuranceError("semantic verification requires explicit passing checks")
    payload = {"method": method, "checks": dict(sorted(checks.items()))}
    semantic_layer = {
        "name": "semantic_validation",
        "status": "verified",
        "sha256": canonical_json_sha256(payload),
    }
    return _build_verified_contract(
        source_inputs=list(assurance["source_inputs"]),
        layers=[*list(assurance["layers"]), semantic_layer],
        transformation_sha256=dict(assurance["transformation_sha256"]),
        semantic_status="verified",
        semantic_verification_method=method,
        semantic_evidence=payload,
    )


def assert_research_ready(assurance: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(assurance, dict):
        raise DataAssuranceError("research dataset lacks data-assurance contract")
    if assurance.get("reconstruction_status") != "verified":
        raise DataAssuranceError("research dataset reconstruction is not verified")
    if assurance.get("semantic_status") != "verified":
        raise DataAssuranceError("research dataset semantic correctness is not verified")
    if assurance.get("verification_method") != "deterministic_rebuild_exact_comparison":
        raise DataAssuranceError("research dataset lacks deterministic reconstruction evidence")
    if assurance.get("semantic_verification_method") != "explicit_dataset_semantics_v1":
        raise DataAssuranceError("research dataset lacks explicit semantic verification evidence")
    semantic_evidence = assurance.get("semantic_evidence")
    if not isinstance(semantic_evidence, dict):
        raise DataAssuranceError("research dataset lacks inspectable semantic evidence")
    checks = semantic_evidence.get("checks")
    if semantic_evidence.get("method") != "explicit_dataset_semantics_v1" or not isinstance(checks, dict):
        raise DataAssuranceError("research dataset semantic evidence contract is invalid")
    if not checks or any(value is not True for value in checks.values()):
        raise DataAssuranceError("research dataset semantic evidence contains failed checks")
    layers = assurance.get("layers")
    if not isinstance(layers, list) or not layers or any(
        item.get("status") != "verified" for item in layers
    ):
        raise DataAssuranceError("research dataset has an unverified reconstruction layer")
    semantic_layers = [item for item in layers if item.get("name") == "semantic_validation"]
    if len(semantic_layers) != 1:
        raise DataAssuranceError("research dataset requires exactly one semantic validation layer")
    if semantic_layers[0].get("sha256") != canonical_json_sha256(semantic_evidence):
        raise DataAssuranceError("research dataset semantic evidence identity is invalid")
    _assert_assurance_identity(assurance)
    return assurance


def extend_verified_assurance(
    assurance: dict[str, Any],
    *,
    layer: dict[str, Any],
    transformation_sha256: dict[str, str],
) -> dict[str, Any]:
    ready = assert_research_ready(assurance)
    if layer.get("status") != "verified" or len(str(layer.get("sha256", ""))) != 64:
        raise DataAssuranceError("extended assurance layer must be independently verified")
    merged_transformations = {
        **dict(ready["transformation_sha256"]),
        **transformation_sha256,
    }
    return _build_verified_contract(
        source_inputs=list(ready["source_inputs"]),
        layers=[*list(ready["layers"]), layer],
        transformation_sha256=merged_transformations,
        semantic_status="verified",
        semantic_verification_method=str(ready["semantic_verification_method"]),
        semantic_evidence=dict(ready["semantic_evidence"]),
    )
