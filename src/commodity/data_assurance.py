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


def build_reconstruction_contract(
    *,
    source_inputs: list[dict[str, Any]],
    layers: list[dict[str, Any]],
    transformation_sha256: dict[str, str],
) -> dict[str, Any]:
    if not source_inputs:
        raise DataAssuranceError("reconstruction contract requires retained source inputs")
    for source in source_inputs:
        digest = str(source.get("sha256", ""))
        if len(digest) != 64:
            raise DataAssuranceError("retained source input lacks canonical SHA-256 identity")
    if not layers or any(item.get("status") != "verified" for item in layers):
        raise DataAssuranceError("every reconstruction layer must be independently verified")
    if not transformation_sha256 or any(len(str(value)) != 64 for value in transformation_sha256.values()):
        raise DataAssuranceError("material transformation identity is incomplete")
    contract = {
        "schema_version": 1,
        "source_inputs": source_inputs,
        "layers": layers,
        "transformation_sha256": dict(sorted(transformation_sha256.items())),
        "reconstruction_status": "verified",
        "semantic_status": "verified",
        "comparison_contract": "rows_columns_timestamps_values_and_canonical_identity",
    }
    contract["assurance_sha256"] = canonical_json_sha256(contract)
    return contract


def assert_research_ready(assurance: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(assurance, dict):
        raise DataAssuranceError("research dataset lacks data-assurance contract")
    if assurance.get("reconstruction_status") != "verified":
        raise DataAssuranceError("research dataset reconstruction is not verified")
    if assurance.get("semantic_status") != "verified":
        raise DataAssuranceError("research dataset semantic correctness is not verified")
    layers = assurance.get("layers")
    if not isinstance(layers, list) or not layers or any(item.get("status") != "verified" for item in layers):
        raise DataAssuranceError("research dataset has an unverified reconstruction layer")
    expected = str(assurance.get("assurance_sha256", ""))
    actual = canonical_json_sha256({key: value for key, value in assurance.items() if key != "assurance_sha256"})
    if expected != actual:
        raise DataAssuranceError("research dataset assurance identity is invalid")
    return assurance
