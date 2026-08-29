from __future__ import annotations

import math
from typing import Any


class InferenceError(ValueError):
    """Raised when programme-level inference evidence is malformed."""


SUPPORTED_PROCEDURES = {
    "white_reality_check",
    "hansen_spa",
    "model_confidence_set",
    "benjamini_hochberg",
    "justified_alternative",
}


def benjamini_hochberg(pvalues: dict[str, float], *, alpha: float) -> dict[str, Any]:
    if not 0 < alpha < 1:
        raise InferenceError("alpha must be inside (0, 1)")
    if not pvalues:
        raise InferenceError("p-value family cannot be empty")
    ordered = sorted((float(value), name) for name, value in pvalues.items())
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value, _ in ordered):
        raise InferenceError("p-values must be finite and inside [0, 1]")
    threshold_index = 0
    count = len(ordered)
    for rank, (value, _) in enumerate(ordered, start=1):
        if value <= alpha * rank / count:
            threshold_index = rank
    rejected = sorted(name for _, name in ordered[:threshold_index])
    return {
        "procedure": "benjamini_hochberg",
        "alpha": alpha,
        "family_size": count,
        "rejected": rejected,
    }


def validate_family_inference_record(record: dict[str, Any]) -> None:
    family_id = record.get("family_id")
    if not isinstance(family_id, str) or not family_id:
        raise InferenceError("family inference requires family_id")
    procedure = record.get("procedure")
    if procedure not in SUPPORTED_PROCEDURES:
        raise InferenceError(f"unsupported family inference procedure: {procedure!r}")
    sha = record.get("inputs_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in sha):
        raise InferenceError("family inference requires inputs_sha256")
    implementation = record.get("implementation_ref")
    if not isinstance(implementation, str) or not implementation:
        raise InferenceError("family inference requires implementation_ref")
    if not isinstance(record.get("result"), dict):
        raise InferenceError("family inference requires structured result")
    if procedure == "justified_alternative":
        justification = record.get("justification")
        if not isinstance(justification, str) or not justification.strip():
            raise InferenceError("justified alternative requires justification")
