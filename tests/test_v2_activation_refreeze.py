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
            "3e55213b967b590187223e2b286063c81672274a",
            "3924274b59f9081247dfb7ad6c9280363a359196",
        ),
    }
    for issue, (candidate_id, prep_sha, implementation_sha) in expected.items():
        assert prep[issue]["head"] == prep_sha
        assert implementation[issue]["head"] == implementation_sha
        assert len(prep_sha) == 40
        assert len(implementation_sha) == 40
        assert candidates[candidate_id]["preparation_revision"]["head"] == prep_sha
        assert candidates[candidate_id]["implementation_revision"]["head"] == implementation_sha
        assert candidates[candidate_id]["execution_authorized"] is True
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
    assert impl83["normal_ci_run"] == 32299571389
    assert impl83["implementation_preflight_run"] == 32299571393
    assert impl83["source_manifest_sha256"] == (
        "91e1f9f899086ee2fe677b28b3b9d6f72a2daca8d7d503a4d5da254ded004c16"
    )
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


def test_independent_88_release_is_limited_to_component_candidates() -> None:
    contract = _load(CONTRACT)
    candidates = _load(CANDIDATES)
    gate = contract["empirical_release_gate"]
    assert contract["execution_authorized"] is True
    assert candidates["freeze"]["execution_authorized"] is True
    assert gate["88"]["satisfied"] is True
    assert gate["88"]["current_state"] == gate["88"]["required_state"]
    assert gate["release_state"] == {"82": True, "83": True, "84": False, "85": False}
