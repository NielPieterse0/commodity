import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_norway_sources_are_explicitly_not_pit_ready() -> None:
    evidence = _json("docs/development/norway-source-pit-readiness/evidence.json")
    families = evidence["families"]

    assert evidence["issue"] == 115
    assert evidence["parent_issue"] == 86
    assert evidence["activation_authorized"] is False
    assert evidence["preferred_future_candidate"] == "gassco_outage_event_revisions"

    assert "defer" in families["nod_ncs_production"]["pit_disposition"]
    assert "not historical-ready" in families["gassco_flow_and_events"]["pit_disposition"]
    assert "defer" in families["ssb_gas_exports"]["pit_disposition"]
    assert "defer" in families["entsog_norway_interfaces"]["pit_disposition"]


def test_norway_readiness_does_not_activate_an_experiment() -> None:
    evidence = _json("docs/development/norway-source-pit-readiness/evidence.json")
    registry = _json("config/experiment_candidates.json")
    serialized = json.dumps(registry, sort_keys=True)

    assert evidence["decision"] == "defer_all_historical_activation_pending_pit_closure"
    assert "norway_source" not in serialized
    assert "gassco_outage" not in serialized


def test_incremental_mechanism_is_not_geographic_novelty() -> None:
    evidence = _json("docs/development/norway-source-pit-readiness/evidence.json")
    families = evidence["families"]

    assert "unexpected upstream outage" in families["gassco_flow_and_events"]["incremental_mechanism"]
    assert "overlaps existing European-flow controls" in families["entsog_norway_interfaces"]["incremental_mechanism"]
    assert "current history forbidden" in families["ssb_gas_exports"]["pit_disposition"]
