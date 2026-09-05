from __future__ import annotations

import hashlib
import json
from pathlib import Path

from commodity.data_assurance import (
    assert_preoutcome_freeze_ready,
    canonical_json_sha256,
)

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_ROOT = (
    ROOT
    / "research/programmes/002-henry-hub-fresh/lines/001-market-structure/experiments"
)
EXPERIMENTS = (
    "001-samuelson-maturity-volatility",
    "002-seasonal-forward-curve",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_henry_hub_preoutcome_manifests_are_self_consistent_and_outcome_blind() -> None:
    for experiment in EXPERIMENTS:
        directory = EXPERIMENT_ROOT / experiment
        prereg = _load(directory / "prereg.json")
        manifest = _load(directory / "dataset-manifest.json")
        evidence = _load(directory / "pre-outcome-evidence.json")
        dataset = prereg["datasets"][0]

        assert manifest["protected_outcomes_accessed"] is False
        assert manifest["dataset_id"] == dataset["id"]
        assert manifest["vintage_id"] == dataset["vintage"]
        assert manifest["split_id"] == dataset["split_id"]

        for ref in manifest["supporting_refs"]:
            assert _sha256(ROOT / ref["path"]) == ref["sha256"]

        assurance = assert_preoutcome_freeze_ready(
            manifest["preoutcome_data_assurance"]
        )
        components = manifest["component_contracts"]
        assert assurance["schema_sha256"] == canonical_json_sha256(
            components["schema_contract"]
        )
        assert assurance["timestamp_contract_sha256"] == canonical_json_sha256(
            components["timestamp_contract"]
        )
        assert assurance["contract_mapping_sha256"] == canonical_json_sha256(
            components["contract_mapping_contract"]
        )
        assert assurance["pit_rules_sha256"] == canonical_json_sha256(
            components["pit_rules"]
        )
        assert assurance["source_inputs"] == [
            {
                "id": "databento_definition_archive_manifest",
                "sha256": evidence["definition_manifest_sha256"],
            },
            {
                "id": "databento_statistics_archive_manifest",
                "sha256": evidence["statistics_manifest_sha256"],
            },
        ]
        assert "dataset_sha256" not in assurance
        assert "frame_sha256" not in assurance


def test_only_tranche_a_designs_receive_freeze_authority() -> None:
    contracts = _load(
        ROOT / "research/programmes/002-henry-hub-fresh/implementation-contracts.json"
    )
    entries = {item["design_id"]: item for item in contracts["entries"]}
    for design_id in (
        "rep-001-samuelson-maturity-volatility",
        "rep-002-seasonal-forward-curve",
    ):
        entry = entries[design_id]
        assert entry["preregistration_freeze_authority"] is True
        assert entry["empirical_execution_authority"] is False
        assert entry["protected_evidence_opening_authority"] is False

    for design_id, entry in entries.items():
        if design_id not in {
            "rep-001-samuelson-maturity-volatility",
            "rep-002-seasonal-forward-curve",
        }:
            assert entry["preregistration_freeze_authority"] is False
