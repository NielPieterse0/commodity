import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "docs" / "development" / "v2-activation-preregistration"
CONTRACT = V2 / "activation-contract.json"
MULTIPLICITY = V2 / "multiplicity-families.json"
CANDIDATES = ROOT / "config" / "experiment_candidates.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    normalized = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def test_corrected_freeze_binds_exact_candidate_registry() -> None:
    contract = _load(CONTRACT)
    digest = _sha256(CANDIDATES)
    assert contract["freeze"]["candidate_config"] == "config/experiment_candidates.json"
    assert contract["freeze"]["candidate_config_sha256"] == digest


def test_corrected_freeze_binds_exact_multiplicity_manifest() -> None:
    contract = _load(CONTRACT)
    manifest = _load(MULTIPLICITY)
    digest = _sha256(MULTIPLICITY)
    rule = contract["frozen_execution_rules"]["multiple_testing_rule"]
    assert contract["freeze"]["multiplicity_manifest"] == (
        "docs/development/v2-activation-preregistration/multiplicity-families.json"
    )
    assert contract["freeze"]["multiplicity_manifest_sha256"] == digest
    assert rule["family_manifest_sha256"] == digest
    assert rule["families"] == [
        "F82_83_COMPONENT_PROMOTION",
        "F83_ATTRIBUTION",
        "F84_ALL_REQUIRED_COMPARATORS",
        "F85_SENSITIVITY",
    ]
    assert set(manifest["families"]) == set(rule["families"])
    assert rule["post_result_pool_split_regroup_reclassify_permitted"] is False
    assert rule["attribution_and_sensitivity_can_rescue_promotion"] is False


def test_child_preparation_and_implementation_revisions_are_bound_separately() -> None:
    contract = _load(CONTRACT)
    candidates = _load(CANDIDATES)["candidates"]
    prep = contract["preparation_bindings"]
    implementation = contract["implementation_bindings"]

    expected = {
        "82": (
            "v2-82-kronos-only",
            "0ff7497e6ce0b5e535604b9fbcfdbd6d131472d9",
            "0ff7497e6ce0b5e535604b9fbcfdbd6d131472d9",
        ),
        "83": (
            "v2-83-indicators-only",
            "2c2b260971739f6dc39437614d769dea57fe58e2",
            "cc5decb5fb9d718edbbf706cf9169e3e73c15f0f",
        ),
    }
    for issue, (candidate_id, prep_sha, implementation_sha) in expected.items():
        assert prep[issue]["head"] == prep_sha
        assert implementation[issue]["head"] == implementation_sha
        assert len(prep_sha) == 40
        assert len(implementation_sha) == 40
        assert candidates[candidate_id]["preparation_revision"]["head"] == prep_sha
        assert candidates[candidate_id]["implementation_revision"]["head"] == implementation_sha
    assert candidates["v2-82-kronos-only"]["execution_authorized"] is True
    assert candidates["v2-83-indicators-only"]["execution_authorized"] is False
    assert prep["83"]["pr"] == 117
    assert candidates["v2-83-indicators-only"]["preparation_revision"]["pr"] == 117
    assert implementation["83"]["pr"] == 172
    assert candidates["v2-83-indicators-only"]["implementation_revision"]["pr"] == 172
    assert prep["83"]["head"] != implementation["83"]["head"]


def test_child_preflights_and_source_manifests_are_bound_exactly() -> None:
    contract = _load(CONTRACT)
    candidates = _load(CANDIDATES)["candidates"]
    prep82 = contract["preparation_bindings"]["82"]
    impl82 = contract["implementation_bindings"]["82"]
    impl83 = contract["implementation_bindings"]["83"]

    assert prep82["normal_ci_run"] == 32323382105
    assert prep82["normal_ci_conclusion"] == "success"
    assert impl82["normal_ci_run"] == 32323382105
    assert impl82["checkpoint_preflight_run"] == 32323382079
    assert impl82["source_manifest_sha256"] == (
        "8c65fdf0c100b3c6d8858f88ca54cadafada4e7470821fb202ab39418457ea72"
    )
    assert impl83["normal_ci_run"] == 32481850560
    assert impl83["implementation_preflight_run"] == 32481850498
    assert impl83["source_manifest_sha256"] == (
        "d34b907396a8df22e28de639e2bbdb5dd6e755a142346f76f7a92eac43d6f128"
    )
    assert impl83["source_manifest_paths"] == [
        "config/data_sources.json",
        "src/commodity/availability.py",
        "src/commodity/evidence_authority.py",
        "src/commodity/roll_safe_market.py",
        "src/commodity/v2_indicator_contract.py",
        "src/commodity/v2_indicator_market.py",
        "src/commodity/v2_indicator_weather_storage.py",
        "src/commodity/v2_indicators.py",
    ]
    for candidate_id, issue in (("v2-82-kronos-only", "82"), ("v2-83-indicators-only", "83")):
        candidate_impl = candidates[candidate_id]["implementation_revision"]
        assert candidate_impl["source_manifest_sha256"] == contract["implementation_bindings"][issue]["source_manifest_sha256"]
        assert candidate_impl["source_manifest_paths"] == contract["implementation_bindings"][issue]["source_manifest_paths"]


def test_robustness_regimes_use_only_ex_ante_pit_information() -> None:
    contract = _load(CONTRACT)
    robustness = contract["frozen_execution_rules"]["robustness_rule"]
    regime = robustness["regime_definition"]

    assert robustness["chronological_periods"] == 3
    assert regime["id"] == "pit-trailing-range20-initial-train-tertiles-v1"
    assert regime["signal"] == "trailing_range20_mean"
    assert "prediction cutoff" in regime["point_in_time_rule"]
    assert "no target" in regime["point_in_time_rule"]
    assert regime["threshold_fit_scope"] == "initial training window only"
    assert regime["recompute_thresholds_per_fold"] is False
    assert regime["post_result_threshold_or_label_change_permitted"] is False
    assert regime["labels"] == ["low", "medium", "high"]


def test_successor_173_refreeze_blocks_83_pending_independent_174_audit() -> None:
    contract = _load(CONTRACT)
    candidates = _load(CANDIDATES)
    gate = contract["empirical_release_gate"]
    assert contract["execution_authorized"] is True
    assert "never sufficient" in contract["execution_authorization_semantics"]
    assert candidates["freeze"]["execution_authorized"] is True
    assert "never sufficient" in candidates["freeze"]["execution_authorization_semantics"]
    assert candidates["freeze"]["activation_audit_issue"] == 174
    assert candidates["freeze"]["activation_audit_predecessor_issue"] == 164
    assert candidates["candidates"]["v2-83-indicators-only"]["execution_authorized"] is False
    assert candidates["candidates"]["v2-84-kronos-indicator-fusion"]["execution_authorized"] is False
    assert gate["88"]["historical_issue"] == 88
    assert gate["88"]["successor_issue"] == 142
    assert gate["83_successor"]["refreeze_issue"] == 173
    assert gate["83_successor"]["historical_audit_issue"] == 164
    assert gate["83_successor"]["successor_audit_issue"] == 174
    assert gate["88"]["satisfied"] is True
    assert gate["83_successor"]["satisfied"] is False
    assert gate["88"]["current_state"] == "independent_activation_audit_passed"
    assert gate["release_state"] == {"82": True, "83": False, "84": False, "85": False}


def test_release_authorization_requires_all_three_authority_keys() -> None:
    contract = _load(CONTRACT)
    registry = _load(CANDIDATES)
    candidate_ids = {
        "82": "v2-82-kronos-only",
        "83": "v2-83-indicators-only",
        "84": "v2-84-kronos-indicator-fusion",
        "85": None,
    }

    def permitted(issue: str) -> bool:
        candidate_id = candidate_ids[issue]
        candidate_authorized = bool(
            candidate_id
            and registry["candidates"].get(candidate_id, {}).get("execution_authorized")
        )
        return bool(
            contract["execution_authorized"]
            and candidate_authorized
            and contract["empirical_release_gate"]["release_state"].get(issue) is True
        )

    assert permitted("82") is True
    assert permitted("83") is False
    assert permitted("84") is False
    assert permitted("85") is False

    assert not (
        contract["execution_authorized"]
        and registry["candidates"]["v2-84-kronos-indicator-fusion"]["execution_authorized"]
        and contract["empirical_release_gate"]["release_state"]["84"]
    )
