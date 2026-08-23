from __future__ import annotations

import csv
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
    volatility_summary = json.loads(
        (ROOT / "artifacts/volatility-diagnostic/volatility-195-gk-har-v1/summary.json").read_text(
            encoding="utf-8"
        )
    )
    volatility_manifest = json.loads(
        (ROOT / "artifacts/volatility-diagnostic/volatility-195-gk-har-v1/run-manifest.json").read_text(
            encoding="utf-8"
        )
    )

    checkpoints = {item["id"]: item for item in retrospective["checkpoints"]}
    stages = {item["stage_id"]: item for item in ledger["stages"]}
    provider = stages["provider-boundary-screening"]
    pit = stages["pit-core-tournament-smoke"]
    phase_d = stages["phase-d-full-v1-hist-gb"]
    kronos = stages["kronos-180-corrected-three-checkpoint"]
    volatility = stages["volatility-195-gk-har-diagnostic"]

    assert [item["stage_id"] for item in ledger["stages"]] == [
        "provider-boundary-screening",
        "pit-core-tournament-smoke",
        "phase-d-full-v1-hist-gb",
        "kronos-180-corrected-three-checkpoint",
        "volatility-195-gk-har-diagnostic",
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
    assert kronos["metrics"]["model_rmse"]["value"] == pytest.approx(0.05529307513018762)
    assert kronos["metrics"]["kronos_mini_rmse"]["value"] == pytest.approx(0.06160964344136518)
    assert kronos["metrics"]["kronos_base_rmse"]["value"] == pytest.approx(0.06648013639481652)
    assert kronos["evidence"]["reproducibility_status"] == "passed"
    assert volatility["metrics"]["mean_challenger_qlike"]["value"] == pytest.approx(
        volatility_summary["primary"]["mean_challenger_qlike"]
    )
    assert volatility["metrics"]["relative_qlike_improvement_pct"]["value"] == pytest.approx(
        100.0 * volatility_summary["primary"]["relative_qlike_improvement"]
    )
    assert volatility["metrics"]["confirmation_relative_mde_pct"]["value"] == pytest.approx(
        100.0 * volatility_summary["confirmation_power_planning"]["confirmation_relative_mde_vs_baseline_qlike"]
    )
    assert volatility["metrics"]["robust_edge_demonstrated"]["value"] == 0
    assert volatility["metrics"]["primary_qlike_gate_passes"]["value"] == 1
    assert volatility["metrics"]["rmse_secondary_descriptive_only"]["value"] == 1
    assert volatility["metrics"]["model_rmse"]["unit"].startswith("secondary_descriptive_")
    assert volatility["evidence"]["reproducibility_status"] == "passed"
    assert volatility_manifest["execution_revision"] == volatility["evidence"]["code_revision"]
    assert volatility_manifest["result_disposition"] == "diagnostic_pass_confirmation_power_gate_fail"


def test_volatility_195_manifest_binds_exact_result_artifacts() -> None:
    result_dir = ROOT / "artifacts/volatility-diagnostic/volatility-195-gk-har-v1"
    manifest = json.loads((result_dir / "run-manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((result_dir / "summary.json").read_text(encoding="utf-8"))
    coverage = json.loads((result_dir / "coverage.json").read_text(encoding="utf-8"))
    ledger = load_ledger(LEDGER_PATH)
    stage = next(item for item in ledger["stages"] if item["stage_id"] == "volatility-195-gk-har-diagnostic")

    expected_hashes = {
        "predictions.csv": manifest["predictions_sha256"],
        "summary.json": manifest["summary_sha256"],
        "coverage.json": manifest["coverage_sha256"],
        "run-manifest.json": "bb43485ece5330f92c1fab270404daeaac5ed9a703b6dcab30d01149a9a409b2",
        "candidate-prediction-times.txt": manifest["candidate_prediction_times_sha256"],
    }
    for filename, expected in expected_hashes.items():
        observed = hashlib.sha256((result_dir / filename).read_bytes()).hexdigest()
        assert observed == expected
        assert expected in stage["evidence"]["artifact_sha256s"]

    candidate_bytes = (result_dir / "candidate-prediction-times.txt").read_bytes()
    candidate_times = candidate_bytes.decode("utf-8").splitlines()
    assert len(candidate_times) == coverage["candidate_rows"] == 456
    assert hashlib.sha256(candidate_bytes).hexdigest() == coverage["candidate_prediction_times_sha256"]
    assert candidate_times[0] == "2024-09-12 23:59:00+00:00"
    assert candidate_times[-1] == "2026-08-11 23:59:00+00:00"

    with (result_dir / "predictions.csv").open(encoding="utf-8", newline="") as handle:
        scored_times = [row["prediction_time"] for row in csv.DictReader(handle)]
    scored_preimage = ("\n".join(scored_times) + "\n").encode()
    assert len(scored_times) == coverage["scored_rows"] == 204
    assert scored_times[0] == coverage["oos_start"]
    assert scored_times[-1] == coverage["oos_end"]
    assert hashlib.sha256(scored_preimage).hexdigest() == coverage["scored_prediction_times_sha256"]

    assert summary["authority"]["diagnostic_only"] is True
    assert summary["authority"]["confirmation_execution_authorized"] is False
    assert summary["authority"]["research_promotion_authorized"] is False
    assert summary["authority"]["trading_authority"] is False
    assert summary["authority"]["issue_51_touched"] is False
    assert manifest["diagnostic_execution_authorized"] is True
    assert manifest["confirmation_execution_authorized"] is False
    assert manifest["research_promotion_authorized"] is False
    assert manifest["trading_authority"] is False
    assert manifest["issue_51_touched"] is False
    assert manifest["reproducibility_runs"] == 2
    assert coverage["row_drops"] == 0
    assert coverage["cross_contract_substitutions"] == 0


def test_real_v1_transition_is_non_comparable_not_a_regression_alarm() -> None:
    ledger = load_ledger(LEDGER_PATH)
    phase_d_index = next(
        index for index, stage in enumerate(ledger["stages"])
        if stage["stage_id"] == "phase-d-full-v1-hist-gb"
    )
    phase_d = ledger["stages"][phase_d_index]
    result = evaluate_comparisons(
        phase_d, ledger["stages"][:phase_d_index], ledger["comparison_policy"]
    )

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


def test_default_metrics_cli_operates_on_real_longitudinal_ledger(capsys) -> None:
    args = build_parser().parse_args(["check-research-metrics"])
    args.func(args)
    output = json.loads(capsys.readouterr().out)

    assert output["status"] == "passed"
    assert output["blockers"] == []
    assert output["previous_context"]["status"] == "non_comparable"
    assert "forecast.target" in output["previous_context"]["hard_context_changes"]
    assert "evaluation.protocol_id" in output["previous_context"]["hard_context_changes"]
    assert "model.family" in output["previous_context"]["methodology_movements"]
    assert not any(item["status"] == "regression" for item in output["metric_comparisons"])


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
