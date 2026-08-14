import copy

import pytest


def _folds() -> list[dict[str, str]]:
    return [
        {
            "fold_id": "fold-001",
            "train_start": "2025-01-01T00:00:00+00:00",
            "train_end": "2025-06-30T00:00:00+00:00",
            "test_start": "2025-07-01T00:00:00+00:00",
            "test_end": "2025-07-31T00:00:00+00:00",
        },
        {
            "fold_id": "fold-002",
            "train_start": "2025-01-01T00:00:00+00:00",
            "train_end": "2025-07-31T00:00:00+00:00",
            "test_start": "2025-08-01T00:00:00+00:00",
            "test_end": "2025-08-31T00:00:00+00:00",
        },
    ]


def _models() -> dict[str, dict[str, object]]:
    return {
        "naive": {"family": "linear_baseline", "architecture": "zero_return"},
        "ridge": {"family": "linear_baseline", "architecture": "ridge", "alpha": 1.0},
        "hist_gb": {"family": "tree_boosting_baseline", "max_iter": 20},
    }


def _plan() -> dict[str, object]:
    from commodity.phase_d_contract import build_phase_d_plan

    return build_phase_d_plan(
        model_names=("naive", "ridge", "hist_gb"),
        models=_models(),
        baseline_model="naive",
        target={"name": "next_session_log_return", "horizon_sessions": 1},
        feature_families=("market", "storage", "weather"),
        split_strategy="expanding_walk_forward",
        folds=_folds(),
        seeds=(0,),
    )


def test_phase_d_plan_identity_is_deterministic_and_preserves_model_order() -> None:
    first = _plan()
    reordered_models = _models()
    reordered_models["ridge"] = {
        "alpha": 1.0,
        "architecture": "ridge",
        "family": "linear_baseline",
    }

    from commodity.phase_d_contract import build_phase_d_plan

    second = build_phase_d_plan(
        model_names=("naive", "ridge", "hist_gb"),
        models=reordered_models,
        baseline_model="naive",
        target={"name": "next_session_log_return", "horizon_sessions": 1},
        feature_families=("market", "storage", "weather"),
        split_strategy="expanding_walk_forward",
        folds=_folds(),
        seeds=(0,),
    )

    assert first["plan_id"] == second["plan_id"]
    assert [item["name"] for item in first["candidates"]] == [
        "naive",
        "ridge",
        "hist_gb",
    ]
    assert [item["candidate_id"] for item in first["candidates"]] == [
        item["candidate_id"] for item in second["candidates"]
    ]


def test_phase_d_plan_defines_full_and_leave_one_family_out_ablations() -> None:
    plan = _plan()

    assert [item["name"] for item in plan["ablations"]] == [
        "full",
        "without:market",
        "without:storage",
        "without:weather",
    ]
    storage = plan["ablations"][2]
    assert storage["excluded_families"] == ["storage"]
    assert storage["included_families"] == ["market", "weather"]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda folds: [],
        lambda folds: [
            {**folds[0], "train_end": "2025-07-02T00:00:00+00:00"},
            folds[1],
        ],
        lambda folds: [
            folds[0],
            {**folds[1], "test_start": "2025-07-15T00:00:00+00:00"},
        ],
        lambda folds: list(reversed(folds)),
    ],
)
def test_phase_d_plan_rejects_invalid_walk_forward_folds(mutator) -> None:
    from commodity.phase_d_contract import build_phase_d_plan

    with pytest.raises(ValueError, match="fold"):
        build_phase_d_plan(
            model_names=("naive", "ridge", "hist_gb"),
            models=_models(),
            baseline_model="naive",
            target={"name": "next_session_log_return", "horizon_sessions": 1},
            feature_families=("market", "storage", "weather"),
            split_strategy="expanding_walk_forward",
            folds=mutator(_folds()),
            seeds=(0,),
        )


def test_phase_d_plan_requires_the_baseline_to_be_first() -> None:
    from commodity.phase_d_contract import build_phase_d_plan

    with pytest.raises(ValueError, match="baseline model must be first"):
        build_phase_d_plan(
            model_names=("ridge", "naive", "hist_gb"),
            models=_models(),
            baseline_model="naive",
            target={"name": "next_session_log_return", "horizon_sessions": 1},
            feature_families=("market", "storage", "weather"),
            split_strategy="expanding_walk_forward",
            folds=_folds(),
            seeds=(0,),
        )


def test_phase_d_lineage_binds_plan_split_models_ablations_and_artifacts() -> None:
    from commodity.phase_d_contract import validate_phase_d_lineage

    plan = _plan()
    lineage = {
        "selection": {
            "candidate_id": plan["candidates"][1]["candidate_id"],
            "ablation_id": plan["ablations"][2]["ablation_id"],
            "seed": 0,
        },
        "dataset": {
            "id": "full-v1-example",
            "sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
        },
        "features": {
            "definition_sha256": "c" * 64,
            "preprocessing_sha256": "d" * 64,
        },
        "experiment_config_sha256": "e" * 64,
        "code": {"commit_sha": "f" * 40},
        "environment": {"dependency_lock_sha256": "1" * 64},
        "artifacts": {
            "predictions_sha256": "2" * 64,
            "evaluation_sha256": "3" * 64,
        },
    }

    bound = validate_phase_d_lineage(plan, lineage)

    assert bound["plan_id"] == plan["plan_id"]
    assert bound["split_id"] == plan["split"]["split_id"]
    assert bound["selection"] == lineage["selection"]
    assert bound["candidate_ids"] == [
        item["candidate_id"] for item in plan["candidates"]
    ]
    assert bound["ablation_ids"] == [item["ablation_id"] for item in plan["ablations"]]
    assert len(bound["lineage_id"]) == 64

    incomplete = copy.deepcopy(lineage)
    del incomplete["artifacts"]["evaluation_sha256"]
    with pytest.raises(ValueError, match="evaluation_sha256"):
        validate_phase_d_lineage(plan, incomplete)


def test_phase_d_lineage_rejects_selection_outside_the_plan() -> None:
    from commodity.phase_d_contract import validate_phase_d_lineage

    plan = _plan()
    lineage = {
        "selection": {
            "candidate_id": "9" * 64,
            "ablation_id": plan["ablations"][0]["ablation_id"],
            "seed": 0,
        },
        "dataset": {
            "id": "full-v1-example",
            "sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
        },
        "features": {"definition_sha256": "c" * 64, "preprocessing_sha256": "d" * 64},
        "experiment_config_sha256": "e" * 64,
        "code": {"commit_sha": "f" * 40},
        "environment": {"dependency_lock_sha256": "1" * 64},
        "artifacts": {"predictions_sha256": "2" * 64, "evaluation_sha256": "3" * 64},
    }

    with pytest.raises(ValueError, match="candidate_id"):
        validate_phase_d_lineage(plan, lineage)

    lineage["selection"]["candidate_id"] = plan["candidates"][0]["candidate_id"]
    lineage["selection"]["seed"] = 99
    with pytest.raises(ValueError, match="seed"):
        validate_phase_d_lineage(plan, lineage)
