import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROGRAMME_DIR = ROOT / "research" / "programmes" / "001-commodity-natural-gas"


def test_retrospective_programme_memory_is_complete_and_bounded():
    programme = json.loads((PROGRAMME_DIR / "programme.json").read_text(encoding="utf-8"))
    evidence_map = json.loads((PROGRAMME_DIR / "evidence-map.json").read_text(encoding="utf-8"))
    assert evidence_map["research_line_refs"] == programme["line_refs"]
    assert {ref["research_line_id"] for ref in programme["line_refs"]} == {
        "001-v1-next-session-return-baseline",
        "002-v2-original-components",
        "003-corrected-kronos-direct-return",
        "004-target-redesign-volatility-events",
        "005-timesfm-return-complementarity",
        "008-next-defensible-edge",
    }
    required = {
        "big_picture", "why_zoomed_in", "tested_role_target_horizon",
        "historical_facts", "useful_secondary_observations",
        "remaining_untested_roles", "revisit_trigger",
        "programme_interpretation", "evidence_refs", "experiment_history",
    }
    for ref in programme["line_refs"]:
        line = json.loads((ROOT / ref["path"]).read_text(encoding="utf-8"))
        assert required <= line.keys(), line["research_line_id"]
        assert line["programme_id"] == programme["programme_id"]
        facts = line["historical_facts"]
        assert {"observed", "rules_out", "does_not_rule_out"} <= facts.keys()
        for evidence_ref in line["evidence_refs"]:
            assert not evidence_ref.startswith(".work/")
            if evidence_ref.startswith("git-history:"):
                continue
            assert (ROOT / evidence_ref).exists(), evidence_ref

    assert evidence_map["semantics"]["empirical_execution_authority"] is False
    assert evidence_map["current_helicopter_view"]["missing_not_negative"]
