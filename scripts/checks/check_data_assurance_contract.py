from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from commodity.data_assurance import (
    DataAssuranceError,
    assert_research_ready,
    build_construction_contract,
    build_semantic_evidence,
    canonical_frame_sha256,
    verify_reconstruction_pair,
    verify_semantic_assurance,
)

ROOT = Path(__file__).resolve().parents[2]
RECONSTRUCTION_METHOD = "deterministic_rebuild_exact_comparison"
SEMANTIC_METHOD = "explicit_dataset_semantics_v1"


def _passing_semantics() -> dict[str, bool]:
    return {"semantic_check": True}


def _failing_semantics() -> dict[str, bool]:
    return {"semantic_check": False}


def _construction(frame: pd.DataFrame) -> dict:
    return build_construction_contract(
        source_inputs=[{"id": "contract-check", "sha256": "1" * 64}],
        layers=[{
            "name": "feature_construction",
            "status": "constructed",
            "sha256": canonical_frame_sha256(frame),
        }],
        transformation_sha256={"contract-check": "2" * 64},
    )


def main() -> int:
    methodology = json.loads(
        (ROOT / "config/research_methodology.json").read_text(encoding="utf-8")
    )
    if methodology.get("dataset_reconstruction_verification_method") != RECONSTRUCTION_METHOD:
        raise DataAssuranceError("methodology reconstruction verification method drifted")
    if methodology.get("dataset_semantic_verification_method") != SEMANTIC_METHOD:
        raise DataAssuranceError("methodology semantic verification method drifted")

    frame = pd.DataFrame(
        {"value": [1.0, 2.0]},
        index=pd.date_range("2026-01-01", periods=2, freq="D", tz="UTC"),
    )
    replay = verify_reconstruction_pair(
        frame,
        _construction(frame),
        frame.copy(),
        _construction(frame.copy()),
    )
    if replay.get("verification_method") != RECONSTRUCTION_METHOD:
        raise DataAssuranceError("reconstruction verification method does not match authority")
    if replay.get("semantic_status") != "pending_semantic_verification":
        raise DataAssuranceError("deterministic replay incorrectly certifies semantics")

    try:
        assert_research_ready(replay)
    except DataAssuranceError:
        pass
    else:
        raise DataAssuranceError("replay-only assurance passed research-ready gate")

    try:
        verify_semantic_assurance(
            replay,
            semantic_evidence=build_semantic_evidence(_failing_semantics),
        )
    except DataAssuranceError:
        pass
    else:
        raise DataAssuranceError("failed semantic check was accepted")

    ready = verify_semantic_assurance(
        replay,
        semantic_evidence=build_semantic_evidence(_passing_semantics),
    )
    assert_research_ready(ready)
    print("data-assurance-contract: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
