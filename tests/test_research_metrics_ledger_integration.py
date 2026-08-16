from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from commodity.cli import build_parser
from commodity.research_metrics import (
    evaluate_comparisons,
    latest_closeout,
    load_ledger,
)

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "artifacts/research-metrics/longitudinal-ledger.json"


def test_governed_v1_ledger_matches_preserved_metric_evidence() -> None:
    ledger = load_ledger(LEDGER_PATH)
    retrospective = json.loads(
        (ROOT / "docs/development/v1-research-completion/retrospective-v0-v1-metrics.json").read_text(
            encoding="utf-8"
        )
    )
    diagnostic = json.loads(
        (ROOT / "docs/development/v1-research-completion/phase-d-regression-diagnostics.json").read_text(
            encoding="utf-8"
        )
    )

    checkpoints = {item["id"]: item for item in retrospective["checkpoints"]}
    stages = {item["stage_id"]: item for item in ledger["stages"]}
    provider = stages["provider-boundary-screening"]
    pit = stages["pit-core-tournament-smoke"]
    phase_d = stages["phase-d-full-v1-hist-gb"]

    assert [item["stage_id"] for item in ledger["stages"]] == [
        "provider-boundary-screening",
        "pit-core-tournament-smoke",
        "phase-d-full-v1-hist-gb",
    ]
    assert provider["evidence_status"] == "partial"
    assert provider["context"]["dataset"]["dataset_sha256"] is None
    assert pit["metrics"]["model_rmse"]["value"] == pytest.approx(
        checkpoints["pit_core_tournament_smoke"]["return_rmse"]["hist_gb"]
    )
    assert pit["metrics"]["baseline_rmse"]["value"] == pytest.approx(
        checkpoints["pit_core_tournament_smoke"]["return_rmse"]["naive"]
    )
    assert phase_d["metrics"]["model_rmse"]["value"] == pytest.approx(
        checkpoints["phase_d_full_v1"]["return_rmse"]["hist_gb"]
    )
    assert phase_d["metrics"]["baseline_rmse"]["value"] == pytest.approx(
        checkpoints["phase_d_full_v1"]["return_rmse"]["naive"]
    )
    assert phase_d["metrics"]["material_incremental_value_count"]["value"] == checkpoints[
        "phase_d_full_v1"
    ]["material_incremental_value_count"]
    assert diagnostic["per_fold_loss"]["fold_count"] == 41
    assert diagnostic["conclusion"]["new_defect_established"] is False


def test_real_v1_transition_is_non_comparable_not_a_regression_alarm() -> None:
    ledger = load_ledger(LEDGER_PATH)
    phase_d = ledger["stages"][-1]
    result = evaluate_comparisons(phase_d, ledger["stages"][:-1], ledger["comparison_policy"])

    assert result["previous_context"]["status"] == "non_comparable"
    assert "dataset.dataset_sha256" in result["previous_context"]["hard_context_changes"]
    assert "evaluation.split_sha256" in result["previous_context"]["hard_context_changes"]
    assert "features.feature_family_ids" in result["previous_context"]["methodology_movements"]
    assert not any(item["status"] == "regression" for item in result["metric_comparisons"])
    assert latest_closeout(ledger)["status"] == "passed"


def test_real_v1_ledger_conforms_to_contract_schema() -> None:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "contracts/research_metrics.schema.json").read_text(encoding="utf-8-sig"))
    Draft202012Validator(schema).validate(ledger)


def test_default_metrics_cli_operates_on_real_v1_ledger(capsys) -> None:
    args = build_parser().parse_args(["check-research-metrics"])
    args.func(args)
    output = json.loads(capsys.readouterr().out)

    assert output["status"] == "passed"
    assert output["blockers"] == []
    assert output["previous_context"]["status"] == "non_comparable"


def test_backfilled_identity_hashes_are_reproducible_from_documented_preimages() -> None:
    ledger = load_ledger(LEDGER_PATH)
    identity_record = json.loads(
        (
            ROOT
            / "docs/development/longitudinal-research-metrics/backfill-identity-record.json"
        ).read_text(encoding="utf-8")
    )
    stages = {stage["stage_id"]: stage for stage in ledger["stages"]}

    for item in identity_record["derived_identities"]:
        payload = json.dumps(
            item["preimage"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        actual_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        assert actual_hash == item["sha256"]

        value = stages[item["stage_id"]]
        for part in item["field"].split("."):
            value = value[part]
        assert value == item["sha256"]
