import json
import math
from pathlib import Path

from commodity.research_lifecycle import (
    assert_revisit_preflight_current,
    validate_exploratory_run,
    validate_literature_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]


def _json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_277_governed_record_and_literature_are_valid() -> None:
    pre = _json("research/literature/volatility-reopening-277-feasibility-v1.json")
    post = _json("research/literature/volatility-reopening-277-post-feasibility-v1.json")
    record = _json("research/exploratory/volatility-reopening-gate-277.json")
    validate_literature_snapshot(pre)
    validate_literature_snapshot(post)
    validate_exploratory_run(record, allow_legacy=True)
    assert record["feasibility"]["decision"] == "hold"
    assert record["execution"]["protected_outcomes_accessed"] is False
    assert record["feasibility"]["evidence"]["mepi"]["value"] == 0.05


def test_277_required_information_envelopes_recompute() -> None:
    record = _json("research/exploratory/volatility-reopening-gate-277.json")
    evidence = record["feasibility"]["evidence"]
    mepi = evidence["mepi"]["value"]
    daily = _json("docs/development/volatility-nuisance-calibration/result.json")
    expected_daily = {
        block: math.ceil(1800 * (mde / mepi) ** 2)
        for block, mde in daily["relative_mde_at_1800"].items()
    }
    assert evidence["redesign_classes"]["same_daily_history_extension"]["required_rows_for_5pct"] == expected_daily

    event = _json("docs/development/volatility-event-nuisance-calibration/result.json")
    expected_event = {
        key: math.ceil(event["confirmation_events"] * (mde / mepi) ** 2)
        for key, mde in event["relative_mde_at_exact_confirmation_n"].items()
    }
    assert evidence["redesign_classes"]["five_session_nonoverlap_extension"]["required_events_for_5pct"] == expected_event


def test_277_reopening_trigger_is_active_and_current() -> None:
    registry = _json("config/research_revisit_triggers.json")
    assert_revisit_preflight_current(registry)
    trigger = next(item for item in registry["triggers"] if item["trigger_id"] == "volatility-material-power-reopening")
    assert trigger["operator"] == "lte"
    assert trigger["threshold"] == 1.0
    gate = _json("config/programme_evidence_map.json")["reopening_gates"]["volatility"]
    assert gate["current_best_ratio"] > gate["release_threshold_ratio"]
    assert gate["fresh_confirmation_path_proven"] is False
