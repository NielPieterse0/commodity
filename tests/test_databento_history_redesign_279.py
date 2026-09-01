from __future__ import annotations

import hashlib
import json
from pathlib import Path

from commodity.research_lifecycle import (
    validate_exploratory_run,
    validate_literature_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]


def _json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _sha256(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def test_279_governed_record_and_literature_are_valid() -> None:
    pre_path = "research/literature/databento-history-redesign-279-feasibility-v1.json"
    post_path = "research/literature/databento-history-redesign-279-post-feasibility-v1.json"
    record = _json("research/exploratory/databento-history-redesign-279.json")
    validate_literature_snapshot(_json(pre_path))
    validate_literature_snapshot(_json(post_path))
    validate_exploratory_run(record, allow_legacy=True)
    assert record["literature_snapshot_ref"]["sha256"] == _sha256(pre_path)
    assert record["external_triangulation"]["literature_snapshot_ref"]["sha256"] == _sha256(post_path)


def test_279_hands_full_history_to_exploratory_literature_replication() -> None:
    record = _json("research/exploratory/databento-history-redesign-279.json")
    evidence = record["feasibility"]["evidence"]
    assert record["feasibility"]["decision"] == "go"
    assert record["promotion_decision"] == "continue"
    assert record["execution"]["protected_outcomes_accessed"] is False
    assert evidence["multiplicity_and_confirmation"]["target_outcomes_scored"] is False
    assert evidence["multiplicity_and_confirmation"]["curve_spread_returns_computed"] is False
    selected = evidence["candidate_ranking"][0]
    assert selected["id"] == "calendar_expiry_ranked_nearest_two_ohlcv_curve"
    assert selected["coverage"]["usable_dates"] == 5025
    assert selected["coverage"]["first_date"] == "2010-06-06"
    assert selected["coverage"]["last_date"] == "2026-08-12"
    assert selected["coverage"]["max_year_share"] < 0.10
    successor = evidence["selected_successor"]
    assert successor["kind"] == "literature_anchored_exploratory_replication"
    assert "inspect development outcomes" in successor["exploratory_permissions"]
    assert "freeze only the final selected specification" in successor["required_controls"][-1]


def test_279_preserves_source_semantics_and_manifest_identity() -> None:
    record = _json("research/exploratory/databento-history-redesign-279.json")
    evidence = record["feasibility"]["evidence"]
    files = [item for schema in evidence["integrity"].values() for item in schema["files"]]
    assert len(files) == 51
    assert all(len(item["sha256"]) == 64 for item in files)
    assert all(schema["all_hashes_ok"] for schema in evidence["integrity"].values())
    assert "not official venue settlement" in evidence["comparability"]["ohlcv_1d"]
    assert evidence["comparability"]["source_regime"]["boundary"] == "2017-05-21"
    assert evidence["aggregate_quality"]["ohlcv_core_duplicate_keys"] == 0
    assert evidence["aggregate_quality"]["ohlcv_core_null_cells"] == 0
    assert evidence["aggregate_quality"]["outright_expiration_mapping_misses"] == 0
