from __future__ import annotations

import json

import pandas as pd
import pytest

from commodity.data_assurance import (
    DataAssuranceError,
    assert_post_unblinding_research_ready,
    assert_preoutcome_freeze_ready,
    bind_post_unblinding_assurance,
    build_construction_contract,
    build_preoutcome_assurance,
    build_semantic_evidence,
    canonical_frame_sha256,
    verify_reconstruction_pair,
    verify_semantic_assurance,
)
from commodity.research_methodology import (
    MethodologyError,
    validate_post_unblinding_dataset_assurance,
)


def _semantics() -> dict[str, bool]:
    return {"settlement_semantics_verified": True}


def _preoutcome() -> dict:
    return build_preoutcome_assurance(
        dataset_identity={
            "dataset_id": "henry-hub-history",
            "vintage_id": "through-2026-08-12",
            "split_id": "confirmatory",
        },
        source_inputs=[{"id": "definitions", "sha256": "1" * 64}],
        schema_sha256="2" * 64,
        timestamp_contract_sha256="3" * 64,
        contract_mapping_sha256="4" * 64,
        pit_rules_sha256="5" * 64,
        transformation_sha256={"runner": "6" * 64},
        expected_coverage={"start": "2010-01-01", "end": "2026-08-12"},
        structural_invariants=[{"name": "contract_identity", "expected": "time-valid"}],
    )


def _ready_assurance() -> dict:
    frame = pd.DataFrame(
        {"settle": [3.1, 3.2]},
        index=pd.date_range("2026-01-01", periods=2, freq="D", tz="UTC"),
    )
    construction = build_construction_contract(
        source_inputs=[{"id": "settlements", "sha256": "7" * 64}],
        layers=[{
            "name": "settlement_dataset",
            "status": "constructed",
            "sha256": canonical_frame_sha256(frame),
        }],
        transformation_sha256={"runner": "8" * 64},
    )
    replay = verify_reconstruction_pair(frame, construction, frame.copy(), construction)
    return verify_semantic_assurance(
        replay,
        semantic_evidence=build_semantic_evidence(_semantics),
    )


def test_preoutcome_assurance_is_structural_and_value_free() -> None:
    assurance = assert_preoutcome_freeze_ready(_preoutcome())
    assert assurance["assurance_stage"] == "pre_outcome"
    assert assurance["outcome_access_state"] == "not_accessed"
    assert "dataset_sha256" not in assurance
    assert "frame_sha256" not in assurance


@pytest.mark.parametrize("field", ["dataset_sha256", "frame_sha256", "outcome_values"])
def test_preoutcome_assurance_rejects_outcome_bearing_top_level_fields(field: str) -> None:
    broken = json.loads(json.dumps(_preoutcome()))
    broken[field] = "9" * 64
    with pytest.raises(DataAssuranceError, match="outside the outcome-blind contract"):
        assert_preoutcome_freeze_ready(broken)


def test_preoutcome_assurance_is_tamper_evident() -> None:
    broken = json.loads(json.dumps(_preoutcome()))
    broken["expected_coverage"]["end"] = "2026-07-31"
    with pytest.raises(DataAssuranceError, match="identity"):
        assert_preoutcome_freeze_ready(broken)


def test_preoutcome_assurance_requires_structural_invariants() -> None:
    broken = json.loads(json.dumps(_preoutcome()))
    broken["structural_invariants"] = []
    broken["assurance_sha256"] = "0" * 64
    with pytest.raises(DataAssuranceError, match="structural invariants"):
        assert_preoutcome_freeze_ready(broken)


def test_post_unblinding_assurance_requires_frozen_preoutcome_binding() -> None:
    ready = _ready_assurance()
    frozen = _preoutcome()["assurance_sha256"]
    with pytest.raises(DataAssuranceError, match="pre-outcome assurance binding"):
        assert_post_unblinding_research_ready(
            ready,
            preoutcome_assurance_sha256=frozen,
        )


def test_post_unblinding_assurance_rejects_mismatched_binding() -> None:
    ready = bind_post_unblinding_assurance(
        _ready_assurance(),
        preoutcome_assurance_sha256="9" * 64,
    )
    with pytest.raises(DataAssuranceError, match="does not match frozen pre-outcome assurance"):
        assert_post_unblinding_research_ready(
            ready,
            preoutcome_assurance_sha256=_preoutcome()["assurance_sha256"],
        )


def test_post_unblinding_assurance_accepts_exact_frozen_binding() -> None:
    frozen = _preoutcome()["assurance_sha256"]
    ready = bind_post_unblinding_assurance(
        _ready_assurance(),
        preoutcome_assurance_sha256=frozen,
    )
    checked = assert_post_unblinding_research_ready(
        ready,
        preoutcome_assurance_sha256=frozen,
    )
    assert checked["preoutcome_assurance_sha256"] == frozen


def test_post_unblinding_manifest_must_bind_to_frozen_preoutcome_identity() -> None:
    prereg = {
        "datasets": [{
            "id": "henry-hub-history",
            "vintage": "through-2026-08-12",
            "split_id": "confirmatory",
        }]
    }
    frozen = _preoutcome()
    freeze = {
        "schema_version": 3,
        "dataset_assurance": {
            "dataset_id": "henry-hub-history",
            "vintage_id": "through-2026-08-12",
            "split_id": "confirmatory",
            "assurance_sha256": frozen["assurance_sha256"],
        },
    }
    ready = bind_post_unblinding_assurance(
        _ready_assurance(),
        preoutcome_assurance_sha256=frozen["assurance_sha256"],
    )
    manifest = {
        "dataset_id": "henry-hub-history",
        "vintage_id": "through-2026-08-12",
        "split_id": "confirmatory",
        "data_assurance": ready,
    }
    checked = validate_post_unblinding_dataset_assurance(prereg, freeze, manifest)
    assert checked["preoutcome_assurance_sha256"] == frozen["assurance_sha256"]


def test_post_unblinding_manifest_rejects_preregistration_identity_drift() -> None:
    prereg = {
        "datasets": [{
            "id": "henry-hub-history",
            "vintage": "through-2026-08-12",
            "split_id": "confirmatory",
        }]
    }
    manifest = {
        "dataset_id": "henry-hub-history",
        "vintage_id": "through-2026-07-31",
        "split_id": "confirmatory",
        "data_assurance": {},
    }
    with pytest.raises(MethodologyError, match="does not match preregistration"):
        validate_post_unblinding_dataset_assurance(
            prereg,
            {"schema_version": 3, "dataset_assurance": {}},
            manifest,
        )
