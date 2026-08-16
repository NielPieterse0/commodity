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


def test_corrected_freeze_binds_exact_multiplicity_manifest() -> None:
    contract = _load(CONTRACT)
    manifest = _load(MULTIPLICITY)
    digest = hashlib.sha256(MULTIPLICITY.read_bytes()).hexdigest()
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
            "f150a0bb001af078632b1e3b33720b5dddf362ff",
            "34a6e388695932722b8bb54377cc6fe67431be36",
        ),
        "83": (
            "v2-83-indicators-only",
            "3e55213b967b590187223e2b286063c81672274a",
            "a8861e48082d2a280075f27a7224e7f8d642460b",
        ),
    }
    for issue, (candidate_id, prep_sha, implementation_sha) in expected.items():
        assert prep[issue]["head"] == prep_sha
        assert implementation[issue]["head"] == implementation_sha
        assert prep_sha != implementation_sha
        assert len(prep_sha) == 40
        assert len(implementation_sha) == 40
        assert candidates[candidate_id]["preparation_revision"]["head"] == prep_sha
        assert candidates[candidate_id]["implementation_revision"]["head"] == implementation_sha
        assert candidates[candidate_id]["execution_authorized"] is False


def test_82_checkpoint_preflight_and_83_ci_are_bound_to_exact_implementation_heads() -> None:
    contract = _load(CONTRACT)
    prep82 = contract["preparation_bindings"]["82"]
    impl82 = contract["implementation_bindings"]["82"]
    impl83 = contract["implementation_bindings"]["83"]
    assert prep82["normal_ci_run"] == 31932345360
    assert prep82["normal_ci_conclusion"] == "success"
    assert impl82["normal_ci_run"] == 31932248200
    assert impl82["normal_ci_conclusion"] == "success"
    assert impl82["checkpoint_preflight_run"] == 31932248268
    assert impl82["checkpoint_preflight_conclusion"] == "success"
    assert impl83["normal_ci_run"] == 31931096518
    assert impl83["normal_ci_conclusion"] == "success"


def test_refreeze_does_not_release_any_empirical_candidate() -> None:
    contract = _load(CONTRACT)
    candidates = _load(CANDIDATES)
    gate = contract["empirical_release_gate"]
    assert contract["execution_authorized"] is False
    assert candidates["freeze"]["execution_authorized"] is False
    assert gate["88"]["satisfied"] is False
    assert gate["88"]["current_state"] == "not_executed"
    assert not any(gate["release_state"].values())
