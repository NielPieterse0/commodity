from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/research/build_issue459_advantage_map.py"


def _load_runner():
    assert RUNNER.exists(), "issue459 advantage-map builder is not implemented"
    spec = importlib.util.spec_from_file_location("issue459_advantage_map", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_issue459_classifies_holds_by_evidence_meaning() -> None:
    runner = _load_runner()
    classify = runner.classify_evidence

    assert classify("RETAIN_MATCHED_MARGINAL_VALUE", "") == "positive_clue"
    assert classify("HOLD_NO_MATCHED_MARGINAL_VALUE", "") == "empirical_negative"
    assert classify("HOLD_INSUFFICIENT_PRIOR_FEATURE_SUPPORT", "") == "underpowered"
    assert classify("HOLD_UNIDENTIFIABLE_UNDER_INHERITED_EXECUTION_POLICY", "") == "role_unidentifiable"
    assert classify("HOLD_SOURCE_NOT_PROVEN", "") == "source_or_data_hold"
    assert classify("INCONCLUSIVE", "") == "null_or_inconclusive"
    assert classify("external_literature_finding_not_yet_reproduced", "") == "untested_mechanism"
    assert (
        classify("retained_for_investigation_not_approved_for_candidate_trading_policy", "")
        == "null_or_inconclusive"
    )
    assert classify("complete_not_promoted", "") == "empirical_negative"

def test_issue459_map_contains_critical_historical_clues() -> None:
    runner = _load_runner()
    evidence = runner.build_advantage_map(ROOT)

    assert evidence["schema_version"] == 1
    assert evidence["protected_confirmation_accessed"] is False
    assert evidence["raw_evidence_count"] > 100
    clue_by_id = {row["clue_id"]: row for row in evidence["priority_clues"]}

    assert clue_by_id["timesfm-baseline-short-modifier"]["aggregate_incremental_net_pnl_usd"] == 14364.999999999996
    assert clue_by_id["kronos-baseline-long-modifier"]["aggregate_incremental_net_pnl_usd"] == 9654.999999999978
    assert clue_by_id["issue426-storage"]["mean_monthly_net_return_delta"] == 0.002528571428571434
    assert clue_by_id["issue426-positioning"]["mean_monthly_net_return_delta"] == 0.003722448979591837
    assert clue_by_id["issue426-storage-weather-interaction"]["mean_monthly_net_return_delta"] == 0.0005122448979591838
    assert clue_by_id["issue448-open-interest"]["mean_monthly_net_return_delta"] == 0.0011391025641025654
    assert clue_by_id["issue428-meta-interactions-p60"]["risk_executed_selected_trades"] == 1
    assert set(clue_by_id["issue427-retained-signals"]["signals"]) == {
        "range_breakout",
        "volume_confirmation",
        "trend_strength",
        "positioning",
        "jump_intensity",
        "volatility_of_volatility",
    }


def test_issue459_map_is_deterministic_and_source_traceable() -> None:
    runner = _load_runner()
    first = runner.build_advantage_map(ROOT)
    second = runner.build_advantage_map(ROOT)

    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(
        second, sort_keys=True, separators=(",", ":")
    )
    assert all(row["source_path"] for row in first["raw_evidence"])
    assert all(row["object_path"] for row in first["raw_evidence"])
    assert all(row["classification"] in runner.EVIDENCE_CLASSES for row in first["raw_evidence"])
    assert {row["source_kind"] for row in first["raw_evidence"]} >= {
        "research_json",
        "governed_change_record",
    }
    assert first["source_summary"]["governed_change_files_scanned"] > 50
