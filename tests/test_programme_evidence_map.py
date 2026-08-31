import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "config" / "programme_evidence_map.json"


def test_retrospective_programme_memory_is_complete_and_bounded():
    evidence_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    lines = evidence_map["research_lines"]
    assert len(lines) >= 8
    required = {
        "big_picture", "why_zoomed_in", "tested_role_target_horizon",
        "historical_facts", "useful_secondary_observations",
        "remaining_untested_roles", "revisit_trigger",
        "programme_interpretation", "evidence_refs", "experiment_history",
    }
    for line in lines:
        assert required <= line.keys(), line["research_line_id"]
        facts = line["historical_facts"]
        assert {"observed", "rules_out", "does_not_rule_out"} <= facts.keys()
        for ref in line["evidence_refs"]:
            assert not ref.startswith(".work/")
            assert (ROOT / ref).exists(), ref

    assert evidence_map["semantics"]["empirical_execution_authority"] is False
    assert evidence_map["current_helicopter_view"]["missing_not_negative"]
