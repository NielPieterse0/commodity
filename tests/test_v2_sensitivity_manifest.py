import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/development/v2-sensitivity/sensitivity-manifest.json"
ACTIVATION = ROOT / "docs/development/v2-activation-preregistration/activation-contract.json"
MULTIPLICITY = ROOT / "docs/development/v2-activation-preregistration/multiplicity-families.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_sensitivity_manifest_is_frozen_and_non_releasing() -> None:
    manifest = _load(MANIFEST)

    assert manifest["issue"] == 85
    assert manifest["status"] == "frozen_pending_empirical_release"
    assert manifest["execution_authorized"] is False
    assert manifest["authority"]["independent_activation_gate_issue"] == 88
    assert manifest["primary_boundary"]["primary_target"] == "target_ret_1"
    assert manifest["primary_boundary"]["replacement_by_sensitivity_permitted"] is False
    assert manifest["primary_boundary"]["rescue_failed_primary_permitted"] is False


def test_exactly_one_secondary_horizon_is_frozen() -> None:
    manifest = _load(MANIFEST)
    horizons = manifest["secondary_horizons"]

    assert len(horizons) == 1
    h5 = horizons[0]
    assert h5["id"] == "H5"
    assert h5["horizon_sessions"] == 5
    assert h5["target_id"] == "target_ret_5_same_contract"
    assert "H-1 = 4" in h5["purge_rule"]
    assert "cross-contract" in h5["roll_rule"]
    assert "100%" in h5["coverage_rule"]
    assert "no hyperparameter" in h5["model_rule"]


def test_regime_sensitivity_reuses_exact_ex_ante_activation_regime() -> None:
    manifest = _load(MANIFEST)
    activation = _load(ACTIVATION)
    regime = activation["frozen_execution_rules"]["robustness_rule"]["regime_definition"]

    assert regime["id"] == "pit-trailing-range20-initial-train-tertiles-v1"
    assert regime["threshold_fit_scope"] == "initial training window only"
    assert regime["recompute_thresholds_per_fold"] is False
    assert manifest["regime_and_period_sensitivity"]["new_regime_definitions_permitted"] is False
    assert manifest["regime_and_period_sensitivity"]["new_calendar_slices_permitted"] is False
    assert "pit-trailing-range20-initial-train-tertiles-v1" in manifest["regime_and_period_sensitivity"]["regime_definition"]


def test_f85_has_exactly_three_h5_inferential_members() -> None:
    manifest = _load(MANIFEST)
    multiplicity = _load(MULTIPLICITY)
    members = manifest["inferential_members"]
    ids = [member["id"] for member in members]

    assert ids == [
        "S85_H5_FUSION_V1",
        "S85_H5_FUSION_KRONOS",
        "S85_H5_FUSION_INDICATORS",
    ]
    assert manifest["multiplicity"]["members"] == ids
    assert manifest["multiplicity"]["method"] == "benjamini_hochberg"
    assert manifest["multiplicity"]["all_members_adjusted_together"] is True
    assert manifest["multiplicity"]["post_result_member_add_drop_regroup_permitted"] is False
    assert manifest["multiplicity"]["promotion_or_rescue_authority"] is False

    f85 = multiplicity["families"]["F85_SENSITIVITY"]
    assert f85["manifest_required_before_execution"] is True
    assert f85["adjust_together"] is True
    assert f85["unmanifested_post_hoc_supports_promotion"] is False


def test_pending_component_reaudit_does_not_release_sensitivity_work() -> None:
    activation = _load(ACTIVATION)

    assert activation["execution_authorized"] is False
    assert activation["empirical_release_gate"]["88"]["satisfied"] is False
    assert activation["empirical_release_gate"]["release_state"] == {
        "82": True,
        "83": False,
        "84": False,
        "85": False,
    }
