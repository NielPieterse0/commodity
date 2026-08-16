from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

CANDIDATE_ID = "v2-84-kronos-indicator-fusion"
KRONOS_CANDIDATE_ID = "v2-82-kronos-only"
INDICATOR_CANDIDATE_ID = "v2-83-indicators-only"
PRIMARY_VARIANT = "F-ALL"
PRIMARY_INDICATOR_VARIANT = "I-ALL"
INDICATOR_ATTRIBUTION_VARIANTS = (
    "I-NO-W",
    "I-NO-S",
    "I-NO-C",
    "I-NO-V",
    "I-NO-P",
    "I-NO-L",
)
FUSION_ATTRIBUTION_VARIANTS = tuple(
    variant.replace("I-NO-", "F-NO-") for variant in INDICATOR_ATTRIBUTION_VARIANTS
)
KRONOS_WEIGHT = 0.5
INDICATOR_WEIGHT = 0.5


class FusionContractError(ValueError):
    """Raised when the frozen #84 fusion contract would be violated."""


class FusionReleaseBlocked(RuntimeError):
    """Raised while the frozen #84 empirical release conditions are unsatisfied."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
    except (TypeError, ValueError) as exc:
        raise FusionContractError("value must be JSON-serializable") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _json_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _prediction_frame(
    frame: pd.DataFrame,
    *,
    expected_candidate_id: str,
    expected_variant: str,
    label: str,
) -> pd.DataFrame:
    required = ("sample_id", "candidate_id", "variant_id", "prediction")
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise FusionContractError(f"{label} is missing columns: {missing}")
    out = frame.loc[:, required].copy()
    if out.empty:
        raise FusionContractError(f"{label} must contain scored predictions")
    if out["sample_id"].isna().any() or out["sample_id"].duplicated().any():
        raise FusionContractError(f"{label} sample identities must be unique and known")
    candidate_ids = set(out["candidate_id"].astype(str))
    if candidate_ids != {expected_candidate_id}:
        raise FusionContractError(f"{label} candidate identity changed")
    variants = set(out["variant_id"].astype(str))
    if variants != {expected_variant}:
        raise FusionContractError(f"{label} variant identity changed")
    prediction = pd.to_numeric(out["prediction"], errors="coerce")
    if prediction.isna().any() or not np.isfinite(prediction.to_numpy()).all():
        raise FusionContractError(f"{label} predictions must be finite")
    out["prediction"] = prediction.astype(float)
    return out.reset_index(drop=True)


def _require_exact_alignment(left: pd.DataFrame, right: pd.DataFrame) -> None:
    left_ids = left["sample_id"].astype(str).tolist()
    right_ids = right["sample_id"].astype(str).tolist()
    if left_ids != right_ids:
        raise FusionContractError(
            "#84 component predictions must have identical scored-row identity and order"
        )


def fuse_predictions(
    kronos: pd.DataFrame,
    indicators: pd.DataFrame,
    *,
    indicator_variant: str = PRIMARY_INDICATOR_VARIANT,
) -> pd.DataFrame:
    """Apply the frozen equal-weight prediction-space fusion without fitting."""
    allowed = {PRIMARY_INDICATOR_VARIANT, *INDICATOR_ATTRIBUTION_VARIANTS}
    if indicator_variant not in allowed:
        raise FusionContractError("#84 indicator variant is not preregistered")
    kronos_valid = _prediction_frame(
        kronos,
        expected_candidate_id=KRONOS_CANDIDATE_ID,
        expected_variant="K-ALL",
        label="Kronos component",
    )
    indicators_valid = _prediction_frame(
        indicators,
        expected_candidate_id=INDICATOR_CANDIDATE_ID,
        expected_variant=indicator_variant,
        label="indicator component",
    )
    _require_exact_alignment(kronos_valid, indicators_valid)

    variant_id = (
        PRIMARY_VARIANT
        if indicator_variant == PRIMARY_INDICATOR_VARIANT
        else indicator_variant.replace("I-NO-", "F-NO-")
    )
    prediction = (
        KRONOS_WEIGHT * kronos_valid["prediction"].to_numpy()
        + INDICATOR_WEIGHT * indicators_valid["prediction"].to_numpy()
    )
    return pd.DataFrame(
        {
            "sample_id": kronos_valid["sample_id"].copy(),
            "candidate_id": CANDIDATE_ID,
            "variant_id": variant_id,
            "prediction": prediction,
        }
    )


def build_fusion_variants(
    kronos: pd.DataFrame,
    indicator_predictions: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """Build the fixed primary and information-family attribution variants."""
    required = (PRIMARY_INDICATOR_VARIANT, *INDICATOR_ATTRIBUTION_VARIANTS)
    missing = [variant for variant in required if variant not in indicator_predictions]
    if missing:
        raise FusionContractError(
            f"#84 requires the complete preregistered indicator variant set: {missing}"
        )
    unexpected = set(indicator_predictions) - set(required)
    if unexpected:
        raise FusionContractError(
            f"#84 does not permit post-hoc indicator variants: {sorted(unexpected)}"
        )
    outputs = {
        PRIMARY_VARIANT: fuse_predictions(
            kronos,
            indicator_predictions[PRIMARY_INDICATOR_VARIANT],
        )
    }
    for indicator_variant in INDICATOR_ATTRIBUTION_VARIANTS:
        fusion_variant = indicator_variant.replace("I-NO-", "F-NO-")
        outputs[fusion_variant] = fuse_predictions(
            kronos,
            indicator_predictions[indicator_variant],
            indicator_variant=indicator_variant,
        )
    return outputs


def require_fusion_release(
    activation_contract: Mapping[str, Any],
    *,
    component_result_state: Mapping[str, Any],
) -> None:
    """Fail closed until #88 and both exact component-result prerequisites are complete."""
    contract = _json_copy(activation_contract)
    gate = contract.get("empirical_release_gate")
    if not isinstance(gate, Mapping):
        raise FusionReleaseBlocked("#84 activation release gate is missing")
    audit = gate.get("88")
    release_state = gate.get("release_state")
    if (
        not contract.get("execution_authorized")
        or not isinstance(audit, Mapping)
        or audit.get("satisfied") is not True
        or audit.get("current_state") != audit.get("required_state")
        or not isinstance(release_state, Mapping)
        or release_state.get("84") is not True
    ):
        raise FusionReleaseBlocked("#84 remains blocked until the exact #88 release")

    for candidate_id in (KRONOS_CANDIDATE_ID, INDICATOR_CANDIDATE_ID):
        result = component_result_state.get(candidate_id)
        if not isinstance(result, Mapping):
            raise FusionReleaseBlocked(
                f"#84 requires completed exact component evidence for {candidate_id}"
            )
        if result.get("status") != "complete":
            raise FusionReleaseBlocked(
                f"#84 component result is not complete for {candidate_id}"
            )
        artifact_sha = str(result.get("prediction_artifact_sha256", ""))
        if len(artifact_sha) != 64 or any(c not in "0123456789abcdef" for c in artifact_sha):
            raise FusionReleaseBlocked(
                f"#84 exact component prediction identity is missing for {candidate_id}"
            )


def prediction_identity(frame: pd.DataFrame) -> str:
    required = ("sample_id", "candidate_id", "variant_id", "prediction")
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise FusionContractError(f"prediction artifact is missing columns: {missing}")
    records: list[dict[str, Any]] = []
    for row in frame.loc[:, required].itertuples(index=False, name=None):
        sample_id, candidate_id, variant_id, prediction = row
        value = float(prediction)
        if not np.isfinite(value):
            raise FusionContractError("prediction artifact contains non-finite values")
        records.append(
            {
                "sample_id": str(sample_id),
                "candidate_id": str(candidate_id),
                "variant_id": str(variant_id),
                "prediction": value,
            }
        )
    return canonical_sha256({"columns": list(required), "records": records})


def validate_required_comparators(comparator_ids: Sequence[str]) -> None:
    required = {
        "zero_return_naive",
        KRONOS_CANDIDATE_ID,
        INDICATOR_CANDIDATE_ID,
    }
    observed = {str(value) for value in comparator_ids}
    if observed != required:
        raise FusionContractError(
            "#84 promotion must test all and only the frozen required comparators"
        )
