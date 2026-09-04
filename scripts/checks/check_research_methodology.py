from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from commodity.research_lifecycle import (
    LIFECYCLE_STAGES,
    assert_revisit_preflight_current,
)
from commodity.research_methodology import (
    MethodologyError,
    canonical_prereg_sha256,
    parse_interpretation_markdown,
    validate_inference_ledger,
    validate_programme_context,
    verify_interpretation_metadata,
    verify_results,
)

GATES = (
    "experiment-schema",
    "experiment-freeze-integrity",
    "experiment-verification",
    "programme-inference-integrity",
)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def validate_document_value(schema_path: Path, value: dict) -> None:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    if errors:
        details = "; ".join(error.message for error in errors[:5])
        raise ValueError(f"value violates {schema_path.name}: {details}")


def validate_document(schema_path: Path, document_path: Path) -> None:
    try:
        validate_document_value(schema_path, load_json(document_path))
    except ValueError as exc:
        raise ValueError(f"{document_path.relative_to(ROOT)}: {exc}") from exc


def load_json_at_commit(commit_sha: str, path: str) -> tuple[dict, str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit_sha}:{path}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"cannot resolve {path} at bound commit {commit_sha}")
    return json.loads(result.stdout.decode("utf-8")), hashlib.sha256(result.stdout).hexdigest()


def programme_dirs() -> list[Path]:
    root = ROOT / "research" / "programmes"
    if not root.is_dir():
        raise ValueError("research/programmes is missing")
    programmes = sorted(path for path in root.iterdir() if path.is_dir())
    if not programmes:
        raise ValueError("at least one numbered research programme is required")
    return programmes


def experiment_dirs() -> list[Path]:
    directories: list[Path] = []
    for programme_dir in programme_dirs():
        programme = load_json(programme_dir / "programme.json")
        for line_ref in programme.get("line_refs", []):
            line_path = ROOT / line_ref["path"]
            line = load_json(line_path)
            for experiment_ref in line.get("experiment_refs", []):
                directories.append(ROOT / experiment_ref["path"])
    return sorted(directories)


def validate_zoom_levels() -> None:
    expected: dict[Path, str] = {}
    for programme_dir in programme_dirs():
        for name in ("programme.json", "evidence-map.json", "inference-ledger.json", "decisions.json", "backlog.json", "revisit-triggers.json", "sealed-windows.json"):
            expected[programme_dir / name] = "L1"
        for path in (programme_dir / "evidence-scans").glob("*.json"):
            expected[path] = "L1"
        for line_path in (programme_dir / "lines").glob("*/line.json"):
            expected[line_path] = "L2"
    for path, level in expected.items():
        value = load_json(path)
        if value.get("zoom_level") != level:
            raise ValueError(f"{path.relative_to(ROOT)} must declare zoom_level {level}")
    for directory in experiment_dirs():
        prereg = directory / "prereg.json"
        legacy = directory / "legacy-record.json"
        results = directory / "results.json"
        if prereg.exists() and load_json(prereg).get("zoom_level") != "L3":
            raise ValueError(f"{prereg.relative_to(ROOT)} must declare zoom_level L3")
        if legacy.exists() and load_json(legacy).get("zoom_level") != "L3":
            raise ValueError(f"{legacy.relative_to(ROOT)} must declare zoom_level L3")
        if results.exists() and load_json(results).get("zoom_level") != "L4":
            raise ValueError(f"{results.relative_to(ROOT)} must declare zoom_level L4")


def check_schema() -> None:
    schema_names = (
        "programme.schema.json", "research_line.schema.json", "prereg.schema.json",
        "results.schema.json", "experiment_record.schema.json", "programme_evidence.schema.json",
        "programme_inference.schema.json", "programme_decisions.schema.json",
        "research_backlog.schema.json", "sealed_windows.schema.json",
        "exploratory_run.schema.json", "interpretation_metadata.schema.json",
        "literature_snapshot.schema.json", "revisit_triggers.schema.json",
        "legacy_experiment_record.schema.json",
    )
    for name in schema_names:
        Draft202012Validator.check_schema(load_json(ROOT / "contracts" / name))
    for programme_dir in programme_dirs():
        programme_path = programme_dir / "programme.json"
        validate_document(ROOT / "contracts/programme.schema.json", programme_path)
        programme = load_json(programme_path)
        if programme.get("programme_id") != programme_dir.name:
            raise ValueError(f"programme_id does not match numbered directory: {programme_dir.name}")
        validate_document(ROOT / "contracts/programme_evidence.schema.json", programme_dir / "evidence-map.json")
        validate_document(ROOT / "contracts/programme_inference.schema.json", programme_dir / "inference-ledger.json")
        validate_document(ROOT / "contracts/programme_decisions.schema.json", programme_dir / "decisions.json")
        validate_document(ROOT / "contracts/research_backlog.schema.json", programme_dir / "backlog.json")
        validate_document(ROOT / "contracts/sealed_windows.schema.json", programme_dir / "sealed-windows.json")
        validate_document(ROOT / "contracts/revisit_triggers.schema.json", programme_dir / "revisit-triggers.json")
        evidence = load_json(programme_dir / "evidence-map.json")
        if evidence.get("programme_id") != programme["programme_id"] or evidence.get("research_line_refs") != programme["line_refs"]:
            raise ValueError(f"programme evidence does not mirror programme child-line refs: {programme_dir.name}")
        for line_ref in programme["line_refs"]:
            line_path = ROOT / line_ref["path"]
            validate_document(ROOT / "contracts/research_line.schema.json", line_path)
            line = load_json(line_path)
            if line.get("programme_id") != programme["programme_id"] or line.get("research_line_id") != line_ref["research_line_id"]:
                raise ValueError(f"research-line parent/child identity mismatch: {line_ref['path']}")
            for experiment_ref in line.get("experiment_refs", []):
                directory = ROOT / experiment_ref["path"]
                legacy = directory / "legacy-record.json"
                prereg = directory / "prereg.json"
                if legacy.is_file() == prereg.is_file():
                    raise ValueError(f"registered experiment must contain exactly one of legacy-record.json or prereg.json: {experiment_ref['path']}")
                if legacy.is_file():
                    validate_document(ROOT / "contracts/legacy_experiment_record.schema.json", legacy)
    methodology = load_json(ROOT / "config/research_methodology.json")
    if methodology.get("issue") != 300 or methodology.get("execution_authority") is not False:
        raise ValueError("research_methodology.json must retain #300 identity and no trading authority")
    if methodology.get("new_exploratory_schema_version") != 3:
        raise ValueError("new exploratory research must use assurance-bound schema_version 3")
    confirmatory_requires = set(methodology.get("new_confirmatory_execution_requires", []))
    if not {"verified_dataset_reconstruction", "verified_dataset_semantics"} <= confirmatory_requires:
        raise ValueError("confirmatory methodology must require reconstruction and semantic verification")
    if tuple(methodology.get("lifecycle_stages", [])) != LIFECYCLE_STAGES:
        raise ValueError("research_methodology.json must declare the complete 15-stage lifecycle")
    record_schema = load_json(ROOT / "contracts/experiment_record.schema.json")
    if record_schema.get("$id") != "https://commodity.local/contracts/experiment-record/v3":
        raise ValueError("experiment record schema must use the parent-bound 15-step v3 contract")
    record_required = set(record_schema.get("required", []))
    if not {"programme_id", "research_line_id", "experiment_id", "lineage", "workflow"} <= record_required:
        raise ValueError("record.json must carry deterministic programme/research-line/experiment lineage")
    record_defs = record_schema.get("$defs") or {}
    record_stage_ids = [
        record_defs[f"step{step}"]["allOf"][1]["properties"]["stage_id"]["const"]
        for step in range(1, 16)
    ]
    if record_stage_ids != list(LIFECYCLE_STAGES):
        raise ValueError("record.json schema must mirror the authoritative 15-stage workflow exactly")
    hierarchy = methodology.get("research_hierarchy") or {}
    levels = hierarchy.get("levels") or []
    expected_levels = ["L0", "L1", "L2", "L3", "L4", "L5"]
    if [item.get("level") for item in levels] != expected_levels:
        raise ValueError("research hierarchy must declare L0 through L5 in order")
    if hierarchy.get("artifact_zoom_level_required") is not True:
        raise ValueError("research artifacts must explicitly declare zoom_level")
    if hierarchy.get("promotion_rule") != "Evidence from L4/L5 never silently becomes an L0/L1 claim. Promotion upward is explicit and evidence-linked.":
        raise ValueError("research hierarchy promotion rule drifted")
    flow = methodology.get("governed_research_workflow") or []
    if [item.get("step") for item in flow] != list(range(1, 16)):
        raise ValueError("governed research workflow must declare steps 1 through 15 exactly once and in order")
    valid_level_tokens = set(expected_levels)
    for item in flow:
        tokens = set(str(item.get("zoom_level", "")).replace("→", "/").replace("\\u2192", "/").replace(" ", "").split("/"))
        if not tokens or not tokens <= valid_level_tokens:
            raise ValueError(f"invalid programme-flow zoom level at step {item.get('step')}")
        if not item.get("stage") or not item.get("required_outcome"):
            raise ValueError(f"incomplete programme-flow declaration at step {item.get('step')}")
    details = methodology.get("governed_research_workflow_details") or []
    detail_by_step = {item.get("step"): item for item in details}
    if sorted(detail_by_step) != list(range(1, 16)):
        raise ValueError("governed research workflow detail must cover Steps 1 through 15 exactly once and in order")
    if [item.get("stage_id") for item in flow] != list(LIFECYCLE_STAGES):
        raise ValueError("governed research workflow stage_ids must be the one authoritative 15-stage lifecycle in order")
    if [item.get("stage_id") for item in details] != list(LIFECYCLE_STAGES):
        raise ValueError("workflow detail stage_ids must match the authoritative 15-stage lifecycle in order")

    step1 = detail_by_step[1]
    if step1.get("zoom_level") != "L0 → L1" or step1.get("north_star_source") != "AGENTS.md#Commodity-and-Primary-objective":
        raise ValueError("Step 1 helicopter view must combine fixed L0 authority with current L1 programme context")
    for field in ("history_synthesis_sources", "programme_synthesis_lenses", "governing_principles", "evidence_exposure_hierarchy", "legacy_evidence_rules"):
        if not step1.get(field):
            raise ValueError(f"Step 1 helicopter view is missing {field}")
    principles = " ".join(step1.get("governing_principles", [])).lower()
    for concept in ("independent confirmation evidence", "store governed facts once"):
        if concept not in principles:
            raise ValueError(f"Step 1 governing principles are missing: {concept}")
    exposure = " ".join(step1.get("evidence_exposure_hierarchy", [])).lower()
    for concept in ("development", "rolling research oos", "reserved confirmation", "true forward evidence", "partly research-trained"):
        if concept not in exposure:
            raise ValueError(f"Step 1 evidence-exposure hierarchy is missing: {concept}")

    step2 = detail_by_step[2]
    if step2.get("zoom_level") != "L1" or not step2.get("gap_rules"):
        raise ValueError("Step 2 must own one bounded decision-relevant gap")
    step3 = detail_by_step[3]
    if step3.get("zoom_level") != "L1 → L2 → L3" or not step3.get("selection_rules"):
        raise ValueError("Step 3 must perform evidence-led zoom-in through line and slice selection")
    if "novel" not in " ".join(step3.get("selection_rules", [])).lower():
        raise ValueError("Step 3 must reject novelty-only slice selection")
    step4 = detail_by_step[4]
    if step4.get("zoom_level") != "L2 → L3" or not step4.get("review_scope") or not step4.get("required_output"):
        raise ValueError("Step 4 must own the slice-specific quality literature snapshot")
    if detail_by_step[5].get("zoom_level") != "L3" or not detail_by_step[5].get("mechanism_rules"):
        raise ValueError("Step 5 must own the source-linked mechanism")
    if detail_by_step[6].get("zoom_level") != "L3" or not detail_by_step[6].get("hypothesis_rules"):
        raise ValueError("Step 6 must own falsifiable H0/H1")
    step7 = detail_by_step[7]
    if step7.get("zoom_level") != "L3" or not step7.get("expectation_rules"):
        raise ValueError("Step 7 must own expected/disconfirming observations and MEPI precommitment")

    step8 = detail_by_step[8]
    if step8.get("zoom_level") != "L3" or step8.get("gate_sequence") != ["economic/scientific relevance", "detectable effect", "available information", "go/no-go"]:
        raise ValueError("Step 8 feasibility gate drifted")
    if not step8.get("dependence_rules") or set(step8.get("failure_actions", [])) != {"redesign", "hold", "stop"}:
        raise ValueError("Step 8 must enforce design-aware power/dependence before implementation")
    confirmation_rules = " ".join(step8.get("confirmation_capacity_rules", [])).lower()
    for concept in ("rolling research-oos", "chronologically latest", "planning default", "purging", "reserved confirmation"):
        if concept not in confirmation_rules:
            raise ValueError(f"Step 8 confirmation-capacity rules are missing: {concept}")

    step9 = detail_by_step[9]
    required_step9 = {"repo_transition", "governed_change_requirements", "implementation_quality_gate", "freeze_gate", "preregistration_freeze_requirements", "benchmark_rules", "confirmation_data_rules", "binding_semantics", "scientific_artifact_model", "automation_and_enforcement"}
    if step9.get("zoom_level") != "L3" or not required_step9 <= set(step9):
        raise ValueError("Step 9 must own governed implementation, complete preregistration, confirmation policy and freeze binding")
    repo_transition = step9.get("repo_transition", "")
    transition_lower = repo_transition.lower()
    for concept in ("implementation_ready", "live kis governed-change workflow", "scientific requirements authority", "thin science-to-repository mapping", "must not restate, duplicate, reinterpret or extend"):
        if concept not in transition_lower:
            raise ValueError(f"Step 9 research-to-KIS boundary is missing: {concept}")
    change_requirements = " ".join(step9.get("governed_change_requirements", [])).lower()
    for concept in ("live kis workflow", "exact approved l3 research authority", "spec.md", "science-to-repository mapping", "engineering iteration", "exit back to l3", "preserve still-valid kis evidence", "lifecycle decision", "promotionready", "exact-head github actions", "landed identities"):
        if concept not in change_requirements:
            raise ValueError(f"Step 9 research-to-KIS translation contract is missing: {concept}")

    nested = methodology.get("nested_research_kis_workflow") or {}
    for field in ("scientific_owner", "implementation_owner", "implementation_ready_boundary", "pre_kis_iteration", "kis_iteration", "scientific_escape_rule", "evidence_reuse_rule", "post_kis_return", "spec_rule"):
        if not nested.get(field):
            raise ValueError(f"nested research/KIS workflow is missing: {field}")
    if nested.get("scientific_owner") != "Commodity research authority" or nested.get("implementation_owner") != "live KIS governed-change lifecycle":
        raise ValueError("nested workflow ownership drifted")
    nested_text = " ".join(str(nested[field]) for field in ("scientific_escape_rule", "evidence_reuse_rule", "post_kis_return", "spec_rule")).lower()
    for concept in ("return to the owning l3", "validity inputs", "exact kis implementation/landing identity", "thin science-to-repository mapping", "must not be duplicated"):
        if concept not in nested_text:
            raise ValueError(f"nested research/KIS workflow semantics are missing: {concept}")
    quality_gate = " ".join(step9.get("implementation_quality_gate", [])).lower()
    for concept in ("scientific/software contract", "test-driven development", "adversarial", "independent oracle", "correctly normalized, semantically verified data", "replicating the relevant published/reference result", "full affected regression suite", "code review", "independent review", "invalidates the affected evidence"):
        if concept not in quality_gate:
            raise ValueError(f"Step 9 implementation-quality gate is missing: {concept}")
    prereg = " ".join(step9.get("preregistration_freeze_requirements", [])).lower()
    for concept in ("information-cutoff", "effective-information", "benchmarks", "inference-ledger", "coherence", "reproduction", "lineage"):
        if concept not in prereg:
            raise ValueError(f"Step 9 preregistration completeness is missing: {concept}")
    benchmark = " ".join(step9.get("benchmark_rules", [])).lower()
    if "market-implied" not in benchmark or "unbiased" not in benchmark:
        raise ValueError("Step 9 benchmark rule must distinguish market-implied comparator from unbiased forecast")
    confirmation = " ".join(step9.get("confirmation_data_rules", [])).lower()
    for concept in ("may be known by identity", "not secrecy", "after freeze", "consumed", "opening"):
        if concept not in confirmation:
            raise ValueError(f"Step 9 reserved-confirmation rule is missing: {concept}")
    binding = " ".join(step9.get("binding_semantics", [])).lower()
    if "does not prove" not in binding or "remotely" not in binding:
        raise ValueError("Step 9 remote-binding semantics are too strong or incomplete")
    artifacts = " ".join(step9.get("scientific_artifact_model", [])).lower()
    for concept in ("prereg.json", "results.json", "interpretation.md", "executive-summary.md", "record.json", "one-way"):
        if concept not in artifacts:
            raise ValueError(f"Step 9 artifact model is missing: {concept}")
    reproduction = step9.get("environment_reproduction") or {}
    if not reproduction.get("logical_reproduction") or not reproduction.get("byte_reproduction") or len(reproduction.get("required_identity", [])) < 5:
        raise ValueError("Step 9 must declare logical/byte reproduction and complete environment identity")
    if "bitwise equality is not universal scientific proof" not in reproduction.get("rule", "").lower():
        raise ValueError("Step 9 reproduction semantics must reject universal bitwise-proof claims")

    step10 = detail_by_step[10]
    if step10.get("zoom_level") != "L4" or not step10.get("execution_rules") or not step10.get("required_output"):
        raise ValueError("Step 10 must execute and preserve raw machine results before interpretation")
    step11 = detail_by_step[11]
    if step11.get("zoom_level") != "L4" or not step11.get("verification_requirements") or not step11.get("leakage_controls"):
        raise ValueError("Step 11 must be the mechanical/bounded-risk verification stage")
    if len(step11.get("evidence_level_definitions", [])) != 7:
        raise ValueError("Step 11 must define E0 through E6")
    if step11.get("orthogonal_status") != [
        "Method compliance: VERIFIED | FAILED | INCOMPLETE",
        "Scientific evidence: E0 | E1 | E2 | E3 | E4 | E5 | E6",
        "Human disposition: ADVANCE | REPLICATE | REFINE | BRANCH | HOLD | STOP",
    ]:
        raise ValueError("Step 11 must preserve orthogonal method/evidence/disposition status")
    leakage = " ".join(step11.get("leakage_controls", [])).lower()
    for concept in ("point-in-time", "vintage", "roll", "release", "overlapping", "joins/cardinality", "no known pit violations"):
        if concept not in leakage:
            raise ValueError(f"Step 11 leakage controls are missing: {concept}")

    step12 = detail_by_step[12]
    if step12.get("zoom_level") != "L5" or not step12.get("required_questions") or not step12.get("coherence_trigger_classes"):
        raise ValueError("Step 12 must compare observed versus expected with symmetric anomaly checks")
    if "unexpectedly good" not in " ".join(step12.get("coherence_rules", [])).lower():
        raise ValueError("Step 12 coherence checks must be symmetric")
    step13 = detail_by_step[13]
    if step13.get("zoom_level") != "L5" or not step13.get("triangulation_rules") or not step13.get("required_output"):
        raise ValueError("Step 13 must perform independent post-result triangulation")
    triangulation = " ".join(step13.get("triangulation_rules", [])).lower()
    if "do not relabel" not in triangulation or "preregistration" not in triangulation:
        raise ValueError("Step 13 must prohibit reuse of preregistration literature as post-result triangulation")

    step14 = detail_by_step[14]
    required_step14 = {"hierarchy_retrace", "programme_inference_rules", "update_rules", "disposition_rules", "documentation_model", "record_rules", "executive_summary_requirements"}
    if step14.get("zoom_level") != "L5 → L1/L2" or not required_step14 <= set(step14):
        raise ValueError("Step 14 must own L4→L0 programme conclusion, inference, evidence update and disposition")
    retrace = step14.get("hierarchy_retrace", [])
    if [item.split(" ", 1)[0] for item in retrace] != ["L4", "L3", "L2", "L1", "L0"]:
        raise ValueError("Step 14 must retrace interpretation from L4 through L0 in order")
    summary = " ".join(step14.get("executive_summary_requirements", []))
    for heading in ("Where this fits", "Where the idea came from", "What we tested", "What we saw", "What it means for the bigger picture", "What next"):
        if heading not in summary:
            raise ValueError(f"Step 14 executive summary is missing heading: {heading}")
    record_rules = " ".join(step14.get("record_rules", [])).lower()
    if "record.json" not in record_rules or "competing" not in record_rules:
        raise ValueError("Step 14 must require compact record.json without competing authority")

    step15 = detail_by_step[15]
    if step15.get("zoom_level") != "L1/L2" or not step15.get("required_inputs") or not step15.get("rules"):
        raise ValueError("Step 15 must own active revisit triggers")
    step15_rules = " ".join(step15.get("rules", [])).lower()
    for concept in ("machine-testable trigger", "evaluation history", "governed research preflight", "traceable successor", "stop"):
        if concept not in step15_rules:
            raise ValueError(f"Step 15 revisit-trigger rules are missing: {concept}")

    dataset_policy = load_json(ROOT / "config/research_dataset.json").get("evaluation_evidence_policy") or {}
    if dataset_policy.get("sequence") != ["development", "rolling_research_oos", "reserved_confirmation", "true_forward"]:
        raise ValueError("research dataset evidence hierarchy drifted")
    reserved = dataset_policy.get("reserved_confirmation") or {}
    if reserved.get("placement") != "chronologically_latest_usable_block" or reserved.get("planning_fraction") != 0.2:
        raise ValueError("reserved confirmation must retain the chronological 20% planning default")
    if reserved.get("fraction_semantics") != "planning_default_not_universal_rule" or reserved.get("prediction_and_evaluation_after_freeze") is not True:
        raise ValueError("reserved confirmation split semantics drifted")
    prohibited = set(reserved.get("prohibited_before_freeze", []))
    if not {"model_fitting", "feature_selection", "model_selection", "hyperparameter_tuning", "threshold_selection", "hypothesis_formulation", "design_redesign"} <= prohibited:
        raise ValueError("reserved confirmation pre-freeze non-use contract is incomplete")
    interpretation_schema = load_json(ROOT / "contracts/interpretation_metadata.schema.json")
    if interpretation_schema.get("properties", {}).get("zoom_level", {}).get("const") != "L5":
        raise ValueError("interpretation metadata must be an L5 artifact")
    if methodology["research_hierarchy"].get("north_star_rule") != "L0 is the North Star and directional authority for L1-L5. Every lower-level research artifact must state how it serves L0, and no L1-L5 result, experiment, run or diagnostic may redefine L0 from below.":
        raise ValueError("L0 North Star rule drifted")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    if "`Commodity` is an experimental commodity-market research platform." not in agents:
        raise ValueError("AGENTS.md must own the L0 repository mandate")
    if agents.count("\n1. screen tradable instruments and market states") != 1 or "\n7. determine whether the integrated system remains robust" not in agents:
        raise ValueError("AGENTS.md must retain the seven primary objectives")
    validate_zoom_levels()
    for programme_dir in programme_dirs():
        triggers_path = programme_dir / "revisit-triggers.json"
        validate_document(ROOT / "contracts/revisit_triggers.schema.json", triggers_path)
        assert_revisit_preflight_current(load_json(triggers_path))

def check_freeze_integrity() -> None:
    for directory in experiment_dirs():
        if (directory / "legacy-record.json").is_file():
            continue
        prereg = directory / "prereg.json"
        freeze = directory / "freeze.json"
        if freeze.exists() and not prereg.exists():
            raise ValueError(f"freeze exists without preregistration: {freeze.relative_to(ROOT)}")
        if prereg.exists():
            validate_document(ROOT / "contracts/prereg.schema.json", prereg)
        if not freeze.exists():
            continue
        record = load_json(freeze)
        if record.get("frozen") is not True:
            raise ValueError(f"freeze record is not frozen: {freeze.relative_to(ROOT)}")
        binding = record.get("binding") or {}
        if binding.get("preregistration_remote_bound") != "verified":
            raise ValueError(f"freeze lacks verified remote binding: {freeze.relative_to(ROOT)}")
        prereg_sha = record.get("prereg_sha256")
        if prereg_sha != canonical_prereg_sha256(load_json(prereg)):
            raise ValueError(f"freeze preregistration identity mismatch: {freeze.relative_to(ROOT)}")
        if binding.get("prereg_sha256") != prereg_sha:
            raise ValueError(f"remote binding preregistration identity mismatch: {freeze.relative_to(ROOT)}")
        context = record.get("programme_context") or {}
        if context.get("status") != "selected_and_feasible":
            raise ValueError(f"freeze lacks selected programme context: {freeze.relative_to(ROOT)}")
        commit_sha = binding.get("commit_sha")
        context_path = context.get("path")
        if not isinstance(commit_sha, str) or not isinstance(context_path, str):
            raise TypeError(f"freeze lacks bound programme context identity: {freeze.relative_to(ROOT)}")
        programme_at_freeze, programme_sha = load_json_at_commit(commit_sha, context_path)
        if programme_sha != context.get("sha256"):
            raise ValueError(f"freeze programme-context hash mismatch: {freeze.relative_to(ROOT)}")
        validate_programme_context(load_json(prereg), programme_at_freeze)


def check_verification() -> None:
    for directory in experiment_dirs():
        if (directory / "legacy-record.json").is_file():
            continue
        prereg_path = directory / "prereg.json"
        results_path = directory / "results.json"
        interpretation_path = directory / "interpretation.md"
        summary_path = directory / "executive-summary.md"
        if results_path.exists() and not prereg_path.exists():
            raise ValueError(f"results exist without preregistration: {results_path.relative_to(ROOT)}")
        if not results_path.exists():
            if interpretation_path.exists() or summary_path.exists():
                raise ValueError(f"interpretation/summary exists without results: {directory.relative_to(ROOT)}")
            continue
        validate_document(ROOT / "contracts/results.schema.json", results_path)
        prereg = load_json(prereg_path)
        results = load_json(results_path)
        verify_results(prereg, results)
        if interpretation_path.exists():
            text = interpretation_path.read_text(encoding="utf-8")
            metadata, _ = parse_interpretation_markdown(text)
            validate_document_value(ROOT / "contracts/interpretation_metadata.schema.json", metadata)
            verify_interpretation_metadata(metadata, prereg, results)
        if summary_path.exists() and not interpretation_path.exists():
            raise ValueError(f"executive summary exists without interpretation: {summary_path.relative_to(ROOT)}")


def check_programme_inference() -> None:
    for programme_dir in programme_dirs():
        programme = load_json(programme_dir / "programme.json")
        ledger = load_json(programme_dir / "inference-ledger.json")
        validate_inference_ledger(ledger)
        if ledger.get("programme_id") != programme.get("programme_id"):
            raise ValueError(f"inference ledger programme mismatch: {programme_dir.name}")
        sealed = load_json(programme_dir / "sealed-windows.json")
        if sealed.get("programme_id") != programme.get("programme_id"):
            raise ValueError(f"sealed-window registry programme mismatch: {programme_dir.name}")
        ids: set[str] = set()
        for window in sealed.get("windows", []):
            window_id = window.get("sealed_window_id")
            if window_id in ids:
                raise ValueError(f"duplicate sealed_window_id: {window_id}")
            ids.add(window_id)
            openings = window.get("openings", [])
            if len(openings) > int(window.get("permitted_openings", 0)):
                raise ValueError(f"sealed window over-opened: {window_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", choices=GATES, required=True)
    args = parser.parse_args()
    checks = {
        "experiment-schema": check_schema,
        "experiment-freeze-integrity": check_freeze_integrity,
        "experiment-verification": check_verification,
        "programme-inference-integrity": check_programme_inference,
    }
    try:
        checks[args.check]()
    except (OSError, TypeError, ValueError, MethodologyError, json.JSONDecodeError) as exc:
        print(f"{args.check}: FAILED: {exc}")
        return 2
    print(f"{args.check}: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
