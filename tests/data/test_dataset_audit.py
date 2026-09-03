from __future__ import annotations

import numpy as np
import pandas as pd

from commodity.data_assurance import (
    build_construction_contract,
    build_semantic_evidence,
    verify_reconstruction_pair,
    verify_semantic_assurance,
)
from commodity.research_dataset import dataframe_sha256


def _fixture_semantics() -> dict[str, bool]:
    return {"fixture_semantics_reviewed": True}


def _fixture(rows: int = 300) -> tuple[pd.DataFrame, dict]:
    index = pd.date_range("2025-01-01", periods=rows, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "market_feature": np.linspace(-1.0, 1.0, rows),
            "storage_feature": np.linspace(0.0, 1.0, rows),
            "weather_feature": np.linspace(10.0, 20.0, rows),
            "power_feature": np.linspace(100.0, 120.0, rows),
            "positioning_feature": np.linspace(-2.0, 2.0, rows),
            "target_ret_1": np.linspace(-0.01, 0.01, rows),
        },
        index=index,
    )
    required = [
        "market", "market_structure", "storage", "weather", "power",
        "positioning", "calendar_seasonality",
    ]
    exogenous = []
    for family in ("storage", "weather", "power", "positioning"):
        exogenous.append(
            {
                "family": family,
                "source_id": f"source-{family}",
                "source_vintage": "2025-v1",
                "source_sha256": {
                    "storage": "a", "weather": "b", "power": "c", "positioning": "d"
                }[family] * 64,
                "availability_statuses": ["verified"],
                "availability_bases": ["source_timestamp"],
                "revision_statuses": ["point_in_time"],
                "join_coverage_ratio": 1.0,
                "unmatched_rows": 0,
            }
        )
    family_audits = {}
    for family in ("storage", "weather", "power", "positioning"):
        family_audits[family] = [{"verdict": "fit", "full_v1_ready": True}]
    construction = {
        "source_inputs": [{"id": "fixture", "sha256": "9" * 64}],
        "layers": [
            {"name": "feature_construction", "status": "constructed", "sha256": dataframe_sha256(frame)}
        ],
        "transformation_sha256": {"fixture": "8" * 64},
    }
    first = build_construction_contract(**construction)
    second = build_construction_contract(**construction)
    reconstruction = verify_reconstruction_pair(frame, first, frame.copy(), second)
    assurance = verify_semantic_assurance(
        reconstruction,
        semantic_evidence=build_semantic_evidence(_fixture_semantics),
    )
    manifest = {
        "dataset_id": "full-v1-test",
        "dataset_sha256": dataframe_sha256(frame),
        "dataset_artifact_sha256": dataframe_sha256(frame),
        "completeness": "full_v1",
        "evidence_mode": "research_pit",
        "required_feature_families": required,
        "included_feature_families": required,
        "missing_feature_families": [],
        "rows": len(frame),
        "target": "target_ret_1",
        "data_assurance": assurance,
        "initial_train_rows": 252,
        "exogenous_sources": exogenous,
        "exogenous_family_audits": family_audits,
        "market_structure": {
            "contract_input_sha256": "a" * 64,
            "selected_path_sha256": "b" * 64,
            "roll_ledger_sha256": "c" * 64,
            "curve_features_sha256": "d" * 64,
            "curve_audit_sha256": "e" * 64,
            "roll_policy_sha256": "f" * 64,
        },
    }
    return frame, manifest


def test_clean_full_v1_fixture_is_fit() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture()
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "fit"
    assert result.blockers == ()
    assert result.oos_rows == 48


def test_audit_requires_verified_data_assurance() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture()
    manifest.pop("data_assurance")
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "not-fit"
    assert "data_assurance_unverified" in result.blockers


def test_audit_rejects_insufficient_oos_capacity() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture(252)
    manifest["dataset_sha256"] = dataframe_sha256(frame)
    manifest["dataset_artifact_sha256"] = manifest["dataset_sha256"]
    manifest["rows"] = len(frame)
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "not-fit"
    assert "insufficient_oos_rows" in result.blockers


def test_audit_rejects_duplicate_or_unsorted_prediction_time() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture()
    frame.index = list(frame.index[:-1]) + [frame.index[-2]]
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "not-fit"
    assert "duplicate_prediction_time" in result.blockers


def test_audit_rejects_missing_or_nonfinite_values() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture()
    frame.iloc[10, 0] = np.nan
    frame.iloc[20, 1] = np.inf
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "not-fit"
    assert "missing_values" in result.blockers
    assert "non_finite_numeric_values" in result.blockers


def test_audit_rejects_incomplete_source_lineage() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture()
    manifest["exogenous_sources"][0]["source_sha256"] = None
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "not-fit"
    assert "incomplete_source_lineage" in result.blockers


def test_audit_rejects_join_coverage_below_configured_v1_minimum() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture()
    manifest["exogenous_sources"][0]["join_coverage_ratio"] = 0.95
    manifest["exogenous_sources"][0]["unmatched_rows"] = 15
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "not-fit"
    assert "minimum_join_coverage_not_met" in result.blockers
    assert "partial_source_join_coverage" in result.caveats


def test_audit_requires_ready_family_audits() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture()
    del manifest["exogenous_family_audits"]["weather"]
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "not-fit"
    assert "required_family_audits_incomplete" in result.blockers


def test_audit_rejects_spoofed_required_family_contract() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture()
    manifest["required_feature_families"] = ["market"]
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "not-fit"
    assert "required_feature_contract_mismatch" in result.blockers


def test_audit_requires_market_structure_lineage_hashes() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture()
    manifest["market_structure"].pop("roll_policy_sha256")
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "not-fit"
    assert "market_structure_lineage_incomplete" in result.blockers


def test_audit_requires_explicit_initial_train_rows() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture()
    del manifest["initial_train_rows"]
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "not-fit"
    assert "split_contract_mismatch" in result.blockers


def test_audit_does_not_trust_spoofed_initial_train_rows() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture(20)
    manifest["dataset_sha256"] = dataframe_sha256(frame)
    manifest["dataset_artifact_sha256"] = manifest["dataset_sha256"]
    manifest["rows"] = len(frame)
    manifest["initial_train_rows"] = 0
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "not-fit"
    assert "split_contract_mismatch" in result.blockers
    assert "insufficient_oos_rows" in result.blockers


def test_audit_rejects_duplicate_columns_and_non_numeric_target() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture()
    frame["target_text"] = "not-a-number"
    frame.columns = [*frame.columns[:-2], "dup", "dup"]
    manifest["target"] = "dup"
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "not-fit"
    assert "duplicate_columns" in result.blockers
    assert "target_not_numeric" in result.blockers


def test_audit_rejects_non_numeric_feature_columns() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture()
    frame["weather_feature"] = "not-a-number"
    manifest["dataset_sha256"] = dataframe_sha256(frame)
    manifest["dataset_artifact_sha256"] = manifest["dataset_sha256"]
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "not-fit"
    assert "non_numeric_columns" in result.blockers


def test_evaluation_full_v1_is_fit_with_explicit_nonpromotion_caveat() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture()
    manifest.update(
        {
            "evidence_mode": "evaluation_pit",
            "canonical_market_evidence": False,
            "market_evaluation_evidence": True,
            "research_evaluation_eligible": True,
            "research_promotion_eligible": False,
        }
    )
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "fit-with-caveats"
    assert "evaluation_only_market_evidence" in result.caveats
    assert result.blockers == ()


def test_evaluation_full_v1_rejects_promotion_claim() -> None:
    from commodity.dataset_audit import audit_full_v1_dataset

    frame, manifest = _fixture()
    manifest.update(
        {
            "evidence_mode": "evaluation_pit",
            "canonical_market_evidence": True,
            "market_evaluation_evidence": True,
            "research_promotion_eligible": True,
        }
    )
    result = audit_full_v1_dataset(frame, manifest)
    assert result.verdict == "not-fit"
    assert "evaluation_mode_claims_promotable_evidence" in result.blockers
