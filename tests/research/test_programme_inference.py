import pytest

from commodity.programme_inference import (
    InferenceError,
    benjamini_hochberg,
    model_confidence_set,
    validate_family_inference_record,
)


def test_benjamini_hochberg_controls_declared_family() -> None:
    result = benjamini_hochberg({"a": 0.001, "b": 0.02, "c": 0.2}, alpha=0.05)
    assert result["procedure"] == "benjamini_hochberg"
    assert result["rejected"] == ["a", "b"]
    assert result["family_size"] == 3


def test_family_inference_supports_finance_failure_mode_methods() -> None:
    for procedure in (
        "white_reality_check",
        "hansen_spa",
        "model_confidence_set",
        "benjamini_hochberg",
        "justified_alternative",
    ):
        record = {
            "family_id": "fam-1",
            "procedure": procedure,
            "inputs_sha256": "a" * 64,
            "implementation_ref": "approved-evaluator:v1",
            "result": {"status": "computed"},
        }
        if procedure == "justified_alternative":
            record["justification"] = "The declared family structure requires a different correction."
        validate_family_inference_record(record)


def test_model_confidence_set_uses_studentized_pairwise_statistics() -> None:
    losses = {
        "best": [1.00, 1.01, 0.99, 1.00, 1.02, 0.98, 1.00, 1.01, 0.99, 1.00],
        "peer": [1.01, 1.00, 1.02, 0.99, 1.01, 1.00, 1.02, 0.99, 1.01, 1.00],
        "bad": [1.50, 1.51, 1.49, 1.50, 1.52, 1.48, 1.50, 1.51, 1.49, 1.50],
    }
    result = model_confidence_set(
        losses,
        alpha=0.10,
        bootstrap_samples=200,
        block_length=2,
        seed=7,
    )
    assert result["implementation"] == "studentized_pairwise_moving_block_bootstrap_mcs"
    assert "bad" not in result["included_models"]
    assert result["eliminations"]
    assert "studentized_worst_relative_loss" in result["eliminations"][0]


def test_justified_alternative_requires_reason() -> None:
    with pytest.raises(InferenceError, match="justification"):
        validate_family_inference_record({
            "family_id": "fam-1", "procedure": "justified_alternative",
            "inputs_sha256": "a" * 64, "implementation_ref": "x", "result": {},
        })


def test_family_inference_record_can_be_appended_without_rewriting_attempts() -> None:
    from commodity.research_methodology import record_family_inference

    ledger = {"schema_version": 1, "programme_id": "commodity-ng", "entries": [], "family_inference": []}
    record = {
        "family_id": "fam-1",
        "procedure": "benjamini_hochberg",
        "inputs_sha256": "a" * 64,
        "implementation_ref": "commodity.programme_inference:benjamini_hochberg",
        "result": {"family_size": 3, "rejected": ["a"]},
    }
    updated = record_family_inference(ledger, record)
    assert ledger["family_inference"] == []
    assert updated["family_inference"] == [record]
    with pytest.raises(Exception, match="already exists"):
        record_family_inference(updated, record)
