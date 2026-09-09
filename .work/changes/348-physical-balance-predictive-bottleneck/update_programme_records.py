from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROGRAMME = ROOT / "research/programmes/002-henry-hub-fresh"
DESIGN = "rep-021-physical-balance-predictive-bottleneck"
RESULT_REF = (
    "research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/"
    "experiments/rep-021-physical-balance-predictive-bottleneck/result.json"
)
ACCEPTANCE_REF = (
    "research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/"
    "experiments/rep-021-physical-balance-predictive-bottleneck/acceptance-review.json"
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def append_unique(items: list, value: object, *, key: str | None = None) -> None:
    if key is None:
        if value not in items:
            items.append(value)
        return
    expected = value[key]
    if all(item.get(key) != expected for item in items):
        items.append(value)


def update_line() -> None:
    path = PROGRAMME / "lines/005-fundamental-balance/line.json"
    data = read_json(path)
    append_unique(data["experiment_history"], {"experiment_id": DESIGN}, key="experiment_id")
    append_unique(
        data["experiment_refs"],
        {
            "experiment_id": DESIGN,
            "path": "research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/experiments/rep-021-physical-balance-predictive-bottleneck",
        },
        key="experiment_id",
    )
    data["historical_facts"]["observed"] += (
        " rep-021 then produced narrower historical successor evidence: under a spot-plus-seasonal "
        "ridge, final-vintage origin-period production/storage/total-consumption improved RMSE by "
        "0.895%, with a three-month MBB 95% CI spanning zero. Post-result acceptance review found "
        "that this mapping does not satisfy #348's intended target-matched futures baseline, realized "
        "target-period physical-input, and pre-outcome detectability requirements."
    )
    data["programme_interpretation"] = (
        "Line 005 has successful rep-012/014 literature reproductions plus rep-021 narrower historical "
        "successor evidence. rep-021 is INCONCLUSIVE and C was correctly not scored under its frozen "
        "stop rule, but #348's intended mapping remains incompletely answered. Phase 2 remains closed."
    )
    data["tested_role_target_horizon"] = (
        "rep-021 tested a narrower one-month log nominal Henry Hub specification on 212 rolling OOS "
        "months using current spot plus seasonal terms versus the same ridge plus final-vintage origin-period "
        "physical inputs. A-to-B was INCONCLUSIVE at 0.895% relative RMSE improvement and C was not reached."
    )
    append_unique(
        data["useful_secondary_observations"],
        "rep-021-physical-balance-predictive-bottleneck:narrower_subdiagnostic_inconclusive_issue348_mapping_incomplete",
    )
    data["stopping_rules"]["successor_execution_authorized_issue"] = 348
    write_json(path, data)


def update_backlog() -> None:
    path = PROGRAMME / "backlog.json"
    data = read_json(path)
    additions = [
        {
            "id": "rep021-prospective-exact-contract-confirmation",
            "item": "Do not allocate genuinely unexposed future confirmation observations to the narrower frozen rep-021 mapping unless a later explicit research decision retains that mapping as independently worthwhile; existing Programme-002 sealed windows remain unopened.",
            "kind": "recommendation",
            "status": "open",
            "source_record": ACCEPTANCE_REF,
            "work_ref": "issue-348",
        },
        {
            "id": "physical-balance-one-month-change-successor",
            "item": "Any revised scored one-month target/horizon/model mapping must use a new research identity after feasibility is established; do not adapt rep-021 features, target semantics, baseline, predictor timing or thresholds post hoc.",
            "kind": "recommendation",
            "status": "open",
            "source_record": ACCEPTANCE_REF,
            "work_ref": "issue-348",
        },
        {
            "id": "issue348-intended-diagnostic-feasibility",
            "item": "Before any new scoring, perform an unscored data-and-capacity feasibility assessment for #348's intended target-matched diagnostic: calendar-average target/delivery semantics, market/futures calibration history, realized target-period physical inputs, matching PIT inputs, programme-wide outcome exposure, and detectability of the 1% material-effect threshold under plausible dependence.",
            "kind": "recommendation",
            "status": "open",
            "source_record": ACCEPTANCE_REF,
            "work_ref": "issue-348",
        },
    ]
    for addition in additions:
        append_unique(data["items"], addition, key="id")
    write_json(path, data)


def update_synthesis() -> None:
    path = PROGRAMME / "research-synthesis.json"
    data = read_json(path)
    data["successor_evidence"] = {
        "issue_348": {
            "design_id": DESIGN,
            "result_ref": RESULT_REF,
            "acceptance_review_ref": ACCEPTANCE_REF,
            "acceptance_status": "bounded_subdiagnostic_not_issue_complete",
            "A_to_B_disposition": "INCONCLUSIVE_REALIZED_PHYSICAL_SIGNAL",
            "relative_rmse_improvement": 0.008949028080413979,
            "primary_mbb_ci": [-0.0032323013640507586, 0.005231112063812548],
            "nonnegative_chronological_thirds": 2,
            "C_scored": False,
            "protected_confirmation_accessed": False,
            "interpretation": "rep-021 is useful narrower historical evidence only; post-result acceptance review found that it does not satisfy #348's intended target-matched futures baseline, realized target-period physical inputs, or pre-outcome detectability requirement.",
        }
    }
    data["next_stage"] = (
        "Issue 348 remains scientifically incomplete. rep-021 is preserved as a narrower historical "
        "sub-diagnostic, and the next investment is an unscored data-and-capacity feasibility assessment "
        "under a new research identity. Phase 2 remains closed."
    )
    data["scientific_design_state"] = (
        "phase1_closed_rep021_narrow_subdiagnostic_issue348_intended_mapping_incomplete_no_phase2_survivor"
    )
    write_json(path, data)


if __name__ == "__main__":
    update_line()
    update_backlog()
    update_synthesis()
