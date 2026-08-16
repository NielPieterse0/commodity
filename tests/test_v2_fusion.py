from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from commodity.v2_fusion import (
    CANDIDATE_ID,
    FUSION_ATTRIBUTION_VARIANTS,
    FusionContractError,
    FusionReleaseBlocked,
    build_fusion_variants,
    fuse_predictions,
    prediction_identity,
    require_fusion_release,
    validate_required_comparators,
)

ROOT = Path(__file__).resolve().parents[1]


def _predictions(candidate: str, variant: str, values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample_id": [f"row-{i}" for i in range(len(values))],
            "candidate_id": candidate,
            "variant_id": variant,
            "prediction": values,
        }
    )


def _kronos() -> pd.DataFrame:
    return _predictions("v2-82-kronos-only", "K-ALL", [0.1, -0.2, 0.3])


def _indicator_variants() -> dict[str, pd.DataFrame]:
    values = {
        "I-ALL": [0.3, 0.2, -0.1],
        "I-NO-W": [0.2, 0.1, -0.1],
        "I-NO-S": [0.3, 0.1, -0.2],
        "I-NO-C": [0.2, 0.2, -0.2],
        "I-NO-V": [0.4, 0.1, -0.1],
        "I-NO-P": [0.3, 0.3, -0.2],
        "I-NO-L": [0.2, 0.3, -0.1],
    }
    return {
        variant: _predictions("v2-83-indicators-only", variant, predictions)
        for variant, predictions in values.items()
    }


def test_primary_fusion_is_fixed_equal_weight_prediction_average() -> None:
    result = fuse_predictions(_kronos(), _indicator_variants()["I-ALL"])
    assert result["candidate_id"].tolist() == [CANDIDATE_ID] * 3
    assert result["variant_id"].tolist() == ["F-ALL"] * 3
    assert result["prediction"].tolist() == pytest.approx([0.2, 0.0, 0.1])


def test_all_preregistered_attribution_variants_are_built_and_no_others() -> None:
    variants = build_fusion_variants(_kronos(), _indicator_variants())
    assert set(variants) == {"F-ALL", *FUSION_ATTRIBUTION_VARIANTS}

    expanded = _indicator_variants()
    expanded["I-POSTHOC"] = _predictions(
        "v2-83-indicators-only", "I-POSTHOC", [0.0, 0.0, 0.0]
    )
    with pytest.raises(FusionContractError, match="post-hoc"):
        build_fusion_variants(_kronos(), expanded)


def test_fusion_fails_closed_on_component_row_misalignment() -> None:
    indicators = _indicator_variants()["I-ALL"].copy()
    indicators.loc[1, "sample_id"] = "different-row"
    with pytest.raises(FusionContractError, match="identical scored-row identity"):
        fuse_predictions(_kronos(), indicators)


def test_fusion_fails_closed_on_missing_or_nonfinite_component_predictions() -> None:
    missing = _indicator_variants()["I-ALL"].iloc[:-1]
    with pytest.raises(FusionContractError, match="identical scored-row identity"):
        fuse_predictions(_kronos(), missing)

    nonfinite = _indicator_variants()["I-ALL"].copy()
    nonfinite.loc[0, "prediction"] = float("nan")
    with pytest.raises(FusionContractError, match="finite"):
        fuse_predictions(_kronos(), nonfinite)


def test_required_comparator_set_is_exact() -> None:
    validate_required_comparators(
        [
            "zero_return_naive",
            "v2-82-kronos-only",
            "v2-83-indicators-only",
        ]
    )
    with pytest.raises(FusionContractError, match="all and only"):
        validate_required_comparators(
            ["zero_return_naive", "v2-82-kronos-only"]
        )


def test_prediction_identity_is_deterministic_and_value_sensitive() -> None:
    result = fuse_predictions(_kronos(), _indicator_variants()["I-ALL"])
    first = prediction_identity(result)
    assert prediction_identity(result.copy()) == first
    changed = result.copy()
    changed.loc[0, "prediction"] += 1e-6
    assert prediction_identity(changed) != first


def test_current_frozen_activation_contract_keeps_84_blocked() -> None:
    contract = json.loads(
        (
            ROOT
            / "docs"
            / "development"
            / "v2-activation-preregistration"
            / "activation-contract.json"
        ).read_text(encoding="utf-8")
    )
    component_state = {
        "v2-82-kronos-only": {
            "status": "complete",
            "prediction_artifact_sha256": "a" * 64,
        },
        "v2-83-indicators-only": {
            "status": "complete",
            "prediction_artifact_sha256": "b" * 64,
        },
    }
    with pytest.raises(FusionReleaseBlocked, match="blocked"):
        require_fusion_release(contract, component_result_state=component_state)


def test_fusion_contract_is_explicitly_nonempirical_and_nonrescuing() -> None:
    contract = json.loads(
        (
            ROOT
            / "docs"
            / "development"
            / "v2-fusion-challenger"
            / "fusion-contract.json"
        ).read_text(encoding="utf-8")
    )
    assert contract["execution_authorized"] is False
    assert contract["component_import_contract"]["kronos_variant_id"] == "K-ALL"
    assert "#84-local normalized import label" in contract["component_import_contract"][
        "kronos_variant_semantics"
    ]
    assert contract["component_import_contract"]["component_prediction_values_may_be_transformed"] is False
    assert contract["primary_variant"]["weights"] == {
        "kronos": 0.5,
        "indicators": 0.5,
    }
    assert contract["primary_variant"]["trainable_fusion_parameters"] is False
    assert contract["primary_variant"]["weight_search_permitted"] is False
    assert contract["attribution_semantics"]["component_ablations_can_rescue_primary"] is False
    assert contract["attribution_semantics"]["information_family_variants_can_rescue_primary"] is False
