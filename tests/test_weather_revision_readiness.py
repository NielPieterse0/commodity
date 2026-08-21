import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_weather_revision_readiness_is_preregister_only() -> None:
    evidence = _json("docs/development/weather-revision-readiness/evidence.json")
    assumption = _json("config/assumptions.json")["assumptions"]["weather_archive"]

    assert evidence["issue"] == 114
    assert evidence["decision"] == "preregister_noaa_gfs_first_follow_on_but_do_not_activate"
    assert evidence["activation_authorized"] is False
    assert evidence["primary_candidate"] == "noaa_gfs_0p5_archive"
    assert evidence["deferred_candidate"] == "ecmwf_mars_archive"
    assert assumption["evidence"] == "docs/development/weather-revision-readiness/evidence.json"


def test_weather_revision_readiness_does_not_mutate_frozen_v2_candidates() -> None:
    registry = _json("config/experiment_candidates.json")
    serialized = json.dumps(registry, sort_keys=True)
    candidate_issues = {
        int(candidate["issue"])
        for candidate in registry["candidates"].values()
        if "issue" in candidate
    }

    assert "weather_revision_candidate" not in serialized
    assert 114 not in candidate_issues

    activation = _json("docs/development/v2-activation-preregistration/activation-contract.json")
    release_state = activation["empirical_release_gate"]["release_state"]
    assert release_state == {"82": True, "83": False, "84": False, "85": False}
