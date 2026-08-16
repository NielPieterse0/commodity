import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT
    / "docs"
    / "development"
    / "v2-activation-preregistration"
    / "multiplicity-families.json"
)


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_component_promotion_family_is_exact_and_bounded() -> None:
    family = _manifest()["families"]["F82_83_COMPONENT_PROMOTION"]
    assert [member["id"] for member in family["members"]] == ["P82_V1", "P83_V1"]
    assert [member["comparator"] for member in family["members"]] == [
        "zero_return_naive",
        "zero_return_naive",
    ]
    assert family["adjust_together"] is True


def test_indicator_attribution_family_is_exact_and_non_rescuing() -> None:
    manifest = _manifest()
    family = manifest["families"]["F83_ATTRIBUTION"]
    assert [member["id"] for member in family["members"]] == [
        "A83_NO_W",
        "A83_NO_S",
        "A83_NO_C",
        "A83_NO_V",
        "A83_NO_P",
        "A83_NO_L",
    ]
    assert [member["removed_family"] for member in family["members"]] == [
        "W",
        "S",
        "C",
        "V",
        "P",
        "L",
    ]
    assert "cannot promote or rescue" in family["semantics"]
    assert manifest["global_rules"]["attribution_and_sensitivity_non_rescuing"] is True


def test_fusion_family_requires_all_three_comparators() -> None:
    family = _manifest()["families"]["F84_ALL_REQUIRED_COMPARATORS"]
    assert [member["id"] for member in family["members"]] == [
        "P84_V1",
        "P84_KRONOS",
        "P84_INDICATORS",
    ]
    assert [member["comparator"] for member in family["members"]] == [
        "zero_return_naive",
        "v2-82-kronos-only",
        "v2-83-indicators-only",
    ]
    assert family["all_members_must_pass"] is True


def test_sensitivity_family_is_manifest_bounded_and_non_rescuing() -> None:
    family = _manifest()["families"]["F85_SENSITIVITY"]
    assert family["manifest_required_before_execution"] is True
    assert family["unmanifested_post_hoc_supports_promotion"] is False
    assert "cannot rescue" in family["semantics"]


def test_missing_or_invalid_prespecified_member_fails_closed() -> None:
    manifest = _manifest()
    assert manifest["method"] == "benjamini_hochberg"
    assert manifest["max_adjusted_p_value"] == 0.05
    rule = manifest["global_rules"]["missing_invalid_prespecified_member_rule"]
    assert "Fail closed" in rule
    assert "p=1.0" in rule
    assert manifest["global_rules"]["post_result_pool_split_regroup_reclassify_permitted"] is False
