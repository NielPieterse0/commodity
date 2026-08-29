from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any

from commodity.provenance import canonical_json_bytes


class MethodologyError(ValueError):
    """Raised when a research-methodology invariant is violated."""


TRUTH_CLASSES = {"PROVEN", "CHECKED", "RECORDED"}
HUMAN_DISPOSITIONS = {"advance", "replicate", "refine", "branch", "hold", "stop"}
EVIDENCE_LEVELS = tuple(f"E{i}" for i in range(7))
FORBIDDEN_PREREG_FIELDS = {"results", "decision", "evidence_level", "prereg_sha256", "result_sha256"}


def canonical_prereg_sha256(prereg: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(prereg)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MethodologyError(message)


def recompute_mepi(spec: dict[str, Any]) -> float:
    formula = spec.get("formula")
    inputs = spec.get("inputs")
    _require(isinstance(inputs, dict), "MEPI requires declared inputs")
    if formula == "absolute":
        value = float(inputs["minimum_effect"])
    elif formula == "cost_adjusted":
        value = float(inputs["minimum_net_effect"]) + float(inputs["cost"])
    elif formula == "sum":
        values = inputs.get("values")
        _require(isinstance(values, list) and values, "sum MEPI requires values")
        value = sum(float(item) for item in values)
    else:
        raise MethodologyError(f"unsupported MEPI formula: {formula!r}")
    _require(math.isfinite(value) and value > 0, "MEPI must be finite and positive")
    return value


def compute_effective_information(dependence: dict[str, Any]) -> dict[str, Any]:
    raw_n = int(dependence.get("raw_n", 0))
    _require(raw_n > 1, "dependence.raw_n must exceed one")
    method = dependence.get("method")
    parameters = dependence.get("parameters") or {}
    if method == "independent":
        effective = float(raw_n)
    elif method == "ar1":
        rho = float(parameters.get("rho"))
        _require(-0.99 < rho < 0.99, "ar1 rho must be inside (-0.99, 0.99)")
        effective = raw_n * (1.0 - rho) / (1.0 + rho)
    elif method == "overlapping_horizon":
        horizon = int(parameters.get("horizon", 0))
        _require(horizon >= 1, "overlapping horizon must be positive")
        effective = raw_n / horizon
    elif method == "event_clusters":
        clusters = int(parameters.get("clusters", 0))
        _require(1 < clusters <= raw_n, "event clusters must be between two and raw_n")
        effective = float(clusters)
    else:
        raise MethodologyError(f"unsupported dependence method: {method!r}")
    _require(effective > 1, "effective information is insufficient")
    return {"raw_n": raw_n, "method": method, "parameters": parameters, "effective_information": effective}


def verify_power(prereg: dict[str, Any]) -> dict[str, Any]:
    power = prereg.get("power") or {}
    _require(power.get("method") == "normal_effect_size", "unsupported power method")
    alpha = float(power.get("alpha", 0))
    target_power = float(power.get("target_power", 0))
    minimum_effect = float(power.get("minimum_effect", 0))
    _require(0 < alpha < 0.5, "alpha must be inside (0, 0.5)")
    _require(0.5 < target_power < 1, "target_power must be inside (0.5, 1)")
    _require(minimum_effect > 0, "minimum_effect must be positive")
    effective = compute_effective_information(prereg["dependence"])
    z_alpha = NormalDist().inv_cdf(1 - alpha / 2)
    z_power = NormalDist().inv_cdf(target_power)
    detectable = (z_alpha + z_power) / math.sqrt(effective["effective_information"])
    status = "passed" if detectable <= minimum_effect else "failed"
    return {
        "status": status,
        "method": power["method"],
        "alpha": alpha,
        "target_power": target_power,
        "minimum_effect": minimum_effect,
        "detectable_effect": detectable,
        "effective_information": effective,
    }


def verify_preregistration(prereg: dict[str, Any]) -> dict[str, Any]:
    forbidden = sorted(FORBIDDEN_PREREG_FIELDS.intersection(prereg))
    _require(not forbidden, f"preregistration contains forbidden result fields: {forbidden}")
    required = {
        "experiment_id", "programme_id", "research_line_id", "slice_id",
        "evidence_scan_ref", "literature_snapshot_ref", "parent_question",
        "uncertainty_reduced", "mechanism", "hypotheses", "mepi", "forecast",
        "datasets", "dependence", "power", "features", "model", "evaluation",
        "inference_ledger_entry_id", "sealed_window", "coherence_triggers",
        "outcome_logic", "permitted_human_dispositions", "reproduction", "lineage",
    }
    missing = sorted(required.difference(prereg))
    _require(not missing, f"preregistration missing required fields: {missing}")
    _require(prereg.get("schema_version") == 1, "preregistration schema_version must be 1")
    dispositions = set(prereg["permitted_human_dispositions"])
    _require(dispositions == HUMAN_DISPOSITIONS, "human disposition enum is incomplete or changed")
    for name, spec in prereg["mepi"].items():
        recomputed = recompute_mepi(spec)
        stored = float(spec.get("value"))
        _require(math.isclose(stored, recomputed, rel_tol=1e-12, abs_tol=1e-12), f"{name} does not match recomputation")
    power = verify_power(prereg)
    _require(power["status"] == "passed", "confirmatory design fails power/detectability gate")
    triggers = prereg["coherence_triggers"]
    _require(isinstance(triggers, list) and len(triggers) >= 2, "at least two symmetric coherence triggers are required")
    directions = {item.get("direction") for item in triggers if isinstance(item, dict)}
    _require("unexpectedly_good" in directions or "both" in directions, "coherence triggers must cover unexpectedly good outcomes")
    _require("unexpectedly_bad" in directions or "both" in directions, "coherence triggers must cover unexpectedly bad outcomes")
    evaluation = prereg["evaluation"]
    benchmarks = evaluation.get("benchmarks")
    _require(isinstance(benchmarks, list) and benchmarks, "at least one benchmark is required")
    if evaluation.get("market_implied_relevant") is True:
        _require(any(item.get("type") == "market_implied" for item in benchmarks), "market-implied comparator is required when economically relevant")
    if evaluation.get("claim_scope") == "trading_usefulness":
        _require("economic_mepi" in prereg["mepi"], "trading-usefulness claims require economic_mepi")
    return {"status": "verified", "prereg_sha256": canonical_prereg_sha256(prereg), "power": power}


def verify_sealed_access(window: dict[str, Any], *, use: str) -> dict[str, Any]:
    if use in {"exploratory", "diagnostic"}:
        raise MethodologyError("exploratory or diagnostic access to sealed confirmation is prohibited")
    _require(window.get("eligibility") == "eligible", "sealed window is not eligible")
    permitted = int(window.get("permitted_openings", 0))
    openings = window.get("openings") or []
    _require(len(openings) < permitted, "sealed window opening allowance is exhausted")
    return {"status": "eligible", "next_opening": len(openings) + 1, "remaining_after": permitted - len(openings) - 1}


def validate_sealed_policy(prereg: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    sealed = prereg.get("sealed_window") or {}
    use = sealed.get("use")
    if use in {None, "none"}:
        return {"status": "not_used"}
    _require(use == "confirmatory", "invalid sealed-window use")
    window_id = sealed.get("sealed_window_id")
    matches = [item for item in registry.get("windows", []) if item.get("sealed_window_id") == window_id]
    _require(len(matches) == 1, "sealed confirmation window is missing or ambiguous")
    return verify_sealed_access(matches[0], use="confirmatory")


def classify_evidence(flags: dict[str, Any]) -> str:
    ordered = [
        ("programme_level", "E6"),
        ("replicated", "E5"),
        ("economic_relevance", "E4"),
        ("robust_forecasting", "E3"),
        ("statistical_support", "E2"),
        ("interesting_signal", "E1"),
    ]
    for key, level in ordered:
        if flags.get(key) is True:
            prerequisite_keys = [item[0] for item in reversed(ordered[ordered.index((key, level)) + 1 :])]
            if all(flags.get(name) is True for name in prerequisite_keys):
                return level
    return "E0"


def verification_finding(truth_class: str, code: str, message: str) -> dict[str, str]:
    _require(truth_class in TRUTH_CLASSES, "invalid verification truth class")
    if truth_class == "CHECKED":
        lowered = message.lower()
        _require("no leakage" not in lowered and "leakage-free" not in lowered, "bounded checks cannot claim universal no leakage")
    return {"truth_class": truth_class, "code": code, "message": message}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def validate_inference_ledger(ledger: dict[str, Any]) -> None:
    from commodity.programme_inference import validate_family_inference_record

    _require(ledger.get("schema_version") == 1, "inference ledger schema_version must be 1")
    entries = ledger.get("entries")
    _require(isinstance(entries, list), "inference ledger entries must be a list")
    ids: set[str] = set()
    tests: set[str] = set()
    for entry in entries:
        entry_id = entry.get("entry_id")
        test_id = entry.get("programme_test_id")
        _require(isinstance(entry_id, str) and entry_id, "inference entry requires entry_id")
        _require(isinstance(test_id, str) and test_id, "inference entry requires programme_test_id")
        _require(entry_id not in ids, f"duplicate inference entry_id: {entry_id}")
        _require(test_id not in tests, f"duplicate programme_test_id: {test_id}")
        _require(entry.get("mode") in {"confirmatory", "exploratory"}, "invalid inference mode")
        ids.add(entry_id)
        tests.add(test_id)
    family_records = ledger.get("family_inference")
    _require(isinstance(family_records, list), "inference ledger family_inference must be a list")
    family_keys: set[tuple[str, str]] = set()
    for record in family_records:
        validate_family_inference_record(record)
        key = (record["family_id"], record["inputs_sha256"])
        _require(key not in family_keys, f"duplicate family inference record: {key[0]}")
        family_keys.add(key)


def register_inference_entry(ledger: dict[str, Any], prereg: dict[str, Any]) -> dict[str, Any]:
    validate_inference_ledger(ledger)
    entry_id = prereg["inference_ledger_entry_id"]
    _require(not any(item["entry_id"] == entry_id for item in ledger["entries"]), "inference entry already exists")
    entry = {
        "entry_id": entry_id,
        "programme_test_id": f"{prereg['programme_id']}:{prereg['experiment_id']}",
        "family_id": prereg["evaluation"]["statistical_family"],
        "research_line_id": prereg["research_line_id"],
        "experiment_id": prereg["experiment_id"],
        "mode": "confirmatory",
        "target": prereg["forecast"]["target"],
        "horizon": prereg["forecast"]["horizon"],
        "information_family": ",".join(prereg["features"].get("information_families", [])),
        "model_family": prereg["model"]["family"],
        "primary_metric": prereg["evaluation"]["primary_metric"],
        "windows_touched": [item.get("id") for item in prereg["datasets"]],
        "sealed_window_history": [],
        "exploratory_ancestry": prereg.get("lineage", {}).get("exploratory_ancestry", []),
        "outcome": None,
        "influenced_later_design": False,
    }
    updated = json.loads(json.dumps(ledger))
    updated["entries"].append(entry)
    validate_inference_ledger(updated)
    return updated


def record_inference_outcome(ledger: dict[str, Any], experiment_id: str, outcome: str) -> dict[str, Any]:
    validate_inference_ledger(ledger)
    updated = json.loads(json.dumps(ledger))
    matches = [item for item in updated["entries"] if item.get("experiment_id") == experiment_id]
    _require(len(matches) == 1, "inference outcome experiment is missing or ambiguous")
    entry = matches[0]
    _require(entry.get("outcome") is None, "inference outcome is already recorded")
    _require(isinstance(outcome, str) and outcome, "inference outcome must be non-empty")
    entry["outcome"] = outcome
    validate_inference_ledger(updated)
    return updated


def mark_inference_influenced_design(ledger: dict[str, Any], experiment_id: str) -> dict[str, Any]:
    validate_inference_ledger(ledger)
    updated = json.loads(json.dumps(ledger))
    matches = [item for item in updated["entries"] if item.get("experiment_id") == experiment_id]
    _require(len(matches) == 1, "inference design-influence experiment is missing or ambiguous")
    matches[0]["influenced_later_design"] = True
    validate_inference_ledger(updated)
    return updated


def record_sealed_opening(registry: dict[str, Any], sealed_window_id: str, experiment_id: str, artifacts_exposed: list[str]) -> dict[str, Any]:
    updated = json.loads(json.dumps(registry))
    matches = [item for item in updated.get("windows", []) if item.get("sealed_window_id") == sealed_window_id]
    _require(len(matches) == 1, f"sealed window not found or duplicated: {sealed_window_id}")
    window = matches[0]
    eligibility = verify_sealed_access(window, use="confirmatory")
    opening = {
        "opening_number": eligibility["next_opening"],
        "experiment_id": experiment_id,
        "artifacts_exposed": list(artifacts_exposed),
    }
    window["openings"].append(opening)
    if len(window["openings"]) >= int(window["permitted_openings"]):
        window["eligibility"] = "exhausted"
    return updated


def audit_leakage(checks: dict[str, Any]) -> list[dict[str, str]]:
    required = (
        "pit_cutoffs", "vintage_timing", "roll_contract_identity", "release_calendar",
        "overlapping_horizons", "event_windows", "join_cardinality", "feature_availability",
    )
    findings: list[dict[str, str]] = []
    for name in required:
        state = checks.get(name)
        if state is True:
            findings.append(verification_finding("CHECKED", name, f"No known {name.replace('_', ' ')} violation detected by the declared check."))
        elif state is False:
            findings.append(verification_finding("CHECKED", name, f"Declared {name.replace('_', ' ')} check detected a violation."))
        else:
            findings.append(verification_finding("CHECKED", name, f"Declared {name.replace('_', ' ')} check is incomplete."))
    return findings


def evaluate_coherence(prereg: dict[str, Any], observed_triggers: list[str]) -> dict[str, Any]:
    declared = {
        item["id"]: item["direction"]
        for item in prereg.get("coherence_triggers", [])
        if isinstance(item, dict) and item.get("id") and item.get("direction")
    }
    observed = set(observed_triggers)
    undeclared = sorted(observed.difference(declared))
    triggered = sorted(observed.intersection(declared))
    return {
        "declared": declared,
        "triggered": triggered,
        "trigger_directions": {key: declared[key] for key in triggered},
        "undeclared_observations": undeclared,
        "enhanced_audit_required": bool(observed),
    }


def verify_results(prereg: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    prereg_verification = verify_preregistration(prereg)
    expected_sha = prereg_verification["prereg_sha256"]
    _require(results.get("prereg_sha256") == expected_sha, "results do not bind to exact preregistration")
    _require(results.get("experiment_id") == prereg["experiment_id"], "results experiment_id mismatch")
    method = results.get("method_compliance")
    _require(method in {"VERIFIED", "FAILED", "INCOMPLETE"}, "invalid method compliance")
    raw = results.get("raw_evidence")
    _require(isinstance(raw, dict), "results require raw_evidence")
    derived = classify_evidence(raw.get("evidence_flags", {}))
    _require(results.get("scientific_evidence") == derived, "scientific evidence must be machine-derived")
    findings = results.get("verification", [])
    for finding in findings:
        verification_finding(finding["truth_class"], finding["code"], finding["message"])
    return {"status": "verified", "prereg_sha256": expected_sha, "scientific_evidence": derived, "method_compliance": method}


def verify_interpretation_metadata(metadata: dict[str, Any], prereg: dict[str, Any], results: dict[str, Any]) -> None:
    _require(metadata.get("schema_version") == 1, "interpretation metadata schema_version must be 1")
    _require(metadata.get("experiment_id") == prereg["experiment_id"], "interpretation experiment_id mismatch")
    expected_prereg = canonical_prereg_sha256(prereg)
    _require(metadata.get("prereg_sha256") == expected_prereg, "interpretation prereg identity mismatch")
    result_sha = hashlib.sha256(canonical_json_bytes(results)).hexdigest()
    _require(metadata.get("results_sha256") == result_sha, "interpretation results identity mismatch")
    _require(metadata.get("human_disposition") in HUMAN_DISPOSITIONS, "invalid human disposition")


def render_executive_summary(sections: dict[str, str]) -> str:
    headings = (
        "Where this fits", "Where the idea came from", "What we tested",
        "What we saw", "What it means for the bigger picture", "What next",
    )
    missing = [heading for heading in headings if not str(sections.get(heading, "")).strip()]
    _require(not missing, f"executive summary missing sections: {missing}")
    body = "\n\n".join(f"## {heading}\n\n{sections[heading].strip()}" for heading in headings)
    words = len(" ".join(sections.values()).split())
    _require(80 <= words <= 240, "executive summary must remain compact (normally 120-200 words)")
    return "# Executive Summary\n\n" + body + "\n"


def verify_reproduction(reference: dict[str, Any], candidate: dict[str, Any], tolerance: dict[str, float], *, byte_mode: bool = False) -> dict[str, Any]:
    if byte_mode:
        _require(reference.get("artifact_sha256") == candidate.get("artifact_sha256"), "byte reproduction mismatch")
        return {"status": "passed", "mode": "byte"}
    for key in ("dataset_id", "prediction_id", "result_id"):
        _require(reference.get(key) == candidate.get(key), f"logical reproduction identity mismatch: {key}")
    ref_values = reference.get("values", {})
    cand_values = candidate.get("values", {})
    _require(set(ref_values) == set(cand_values), "logical reproduction value keys mismatch")
    absolute = float(tolerance.get("absolute", 0))
    relative = float(tolerance.get("relative", 0))
    for key in ref_values:
        _require(math.isclose(float(ref_values[key]), float(cand_values[key]), abs_tol=absolute, rel_tol=relative), f"logical reproduction tolerance exceeded: {key}")
    return {"status": "passed", "mode": "logical"}


def validate_research_line(line: dict[str, Any]) -> None:
    _require(line.get("research_line_id"), "research line requires research_line_id")
    _require(line.get("selection_basis") in {"external_evidence", "internal_contradiction", "high_value_gap"}, "research line requires evidence-based selection_basis")
    rules = line.get("stopping_rules")
    _require(isinstance(rules, dict), "research line requires stopping_rules")
    for key in ("negative_evidence", "feasible_power", "economic_relevance", "confirmation_capacity", "expected_information_value"):
        _require(key in rules, f"research line stopping rules missing: {key}")


def validate_programme_context(prereg: dict[str, Any], evidence_map: dict[str, Any]) -> dict[str, Any]:
    _require(evidence_map.get("schema_version") == 1, "programme evidence schema_version must be 1")
    _require(evidence_map.get("programme_id") == prereg.get("programme_id"), "programme evidence does not match preregistration")
    lines = [item for item in evidence_map.get("research_lines", []) if item.get("research_line_id") == prereg.get("research_line_id")]
    _require(len(lines) == 1, "research line is missing or ambiguous in programme evidence map")
    line = lines[0]
    validate_research_line(line)
    _require(line.get("status") == "selected", "research line is not selected for confirmatory work")
    families = set(prereg.get("features", {}).get("information_families", []))
    matches = [
        item for item in evidence_map.get("feasibility_map", [])
        if item.get("target") == prereg.get("forecast", {}).get("target")
        and item.get("horizon") == prereg.get("forecast", {}).get("horizon")
        and item.get("information_family") in families
    ]
    _require(matches, "no matching programme feasibility entry exists")
    _require(any(item.get("feasibility") == "go" for item in matches), "programme feasibility does not permit confirmatory freeze")
    return {"status": "selected_and_feasible", "research_line_id": line["research_line_id"]}


def build_results(
    prereg: dict[str, Any], *, run_id: str, code: dict[str, Any], data: dict[str, Any],
    model: dict[str, Any], environment: dict[str, Any], raw_evidence: dict[str, Any],
    verification: list[dict[str, str]], coherence: dict[str, Any], artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    prereg_check = verify_preregistration(prereg)
    checked_messages = [
        item.get("message", "").lower()
        for item in verification
        if item.get("truth_class") == "CHECKED"
    ]
    detected_violation = any("detected a violation" in message for message in checked_messages)
    incomplete_check = any("incomplete" in message for message in checked_messages)
    coherence_incomplete = (
        coherence.get("enhanced_audit_required") is True
        and coherence.get("audit_completed") is not True
    )
    if detected_violation:
        method_compliance = "FAILED"
    elif incomplete_check or coherence_incomplete:
        method_compliance = "INCOMPLETE"
    else:
        method_compliance = "VERIFIED"
    evidence = classify_evidence(raw_evidence.get("evidence_flags", {}))
    return {
        "schema_version": 1,
        "experiment_id": prereg["experiment_id"],
        "run_id": run_id,
        "prereg_sha256": prereg_check["prereg_sha256"],
        "code": code, "data": data, "model": model, "environment": environment,
        "raw_evidence": raw_evidence, "verification": verification,
        "method_compliance": method_compliance, "scientific_evidence": evidence,
        "coherence": coherence, "artifacts": artifacts,
    }


def _git_text(repo_root: Path, *args: str) -> str:
    import subprocess

    result = subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise MethodologyError(f"git command failed: {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def _require_clean_repository(repo_root: Path) -> None:
    status = _git_text(Path(repo_root), "status", "--porcelain")
    _require(not status, "remote preregistration binding requires a clean repository")


def verify_remote_prereg_binding(repo_root: Path, prereg_path: Path, tag: str, remote: str = "origin") -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    prereg_path = Path(prereg_path).resolve()
    _require_clean_repository(repo_root)
    relative = prereg_path.relative_to(repo_root).as_posix()
    local = load_json(prereg_path)
    prereg_sha = canonical_prereg_sha256(local)
    committed_text = _git_text(repo_root, "show", f"HEAD:{relative}")
    committed = json.loads(committed_text)
    _require(canonical_prereg_sha256(committed) == prereg_sha, "HEAD does not contain exact preregistration content")
    head = _git_text(repo_root, "rev-parse", "HEAD")
    tag_commit = _git_text(repo_root, "rev-list", "-n", "1", tag)
    _require(tag_commit == head, "preregistration tag does not point at HEAD")
    import subprocess
    remote_tag = subprocess.run(["git", "-C", str(repo_root), "ls-remote", remote, f"refs/tags/{tag}^{{}}"], capture_output=True, text=True, check=False)
    if remote_tag.returncode != 0 or not remote_tag.stdout.strip():
        remote_tag = subprocess.run(["git", "-C", str(repo_root), "ls-remote", remote, f"refs/tags/{tag}"], capture_output=True, text=True, check=False)
    _require(remote_tag.returncode == 0 and remote_tag.stdout.strip(), "preregistration tag is not published remotely")
    remote_commit = remote_tag.stdout.split()[0]
    _require(remote_commit == head, "remote preregistration tag does not resolve to HEAD")
    return {"preregistration_remote_bound": "verified", "prereg_sha256": prereg_sha, "commit_sha": head, "tag": tag, "remote": remote}


def write_immutable_json(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    if path.exists():
        raise MethodologyError(f"immutable artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def parse_interpretation_markdown(text: str) -> tuple[dict[str, Any], dict[str, str]]:
    marker = "```json\n"
    start = text.find(marker)
    _require(start >= 0, "interpretation requires a JSON metadata block")
    end = text.find("\n```", start + len(marker))
    _require(end >= 0, "interpretation JSON metadata block is not closed")
    metadata = json.loads(text[start + len(marker) : end])
    headings = (
        "Where this fits", "Where the idea came from", "What we tested",
        "What we saw", "What it means for the bigger picture", "What next",
    )
    sections: dict[str, str] = {}
    for index, heading in enumerate(headings):
        token = f"## {heading}\n"
        pos = text.find(token, end)
        _require(pos >= 0, f"interpretation missing section: {heading}")
        body_start = pos + len(token)
        next_positions = [text.find(f"## {later}\n", body_start) for later in headings[index + 1 :]]
        next_positions = [item for item in next_positions if item >= 0]
        body_end = min(next_positions) if next_positions else len(text)
        body = text[body_start:body_end].strip()
        _require(bool(body), f"interpretation section is empty: {heading}")
        sections[heading] = body
    return metadata, sections


def render_executive_summary_from_interpretation(text: str, prereg: dict[str, Any], results: dict[str, Any]) -> str:
    metadata, sections = parse_interpretation_markdown(text)
    verify_interpretation_metadata(metadata, prereg, results)
    return render_executive_summary(sections)


def assert_confirmatory_execution_allowed(
    prereg: dict[str, Any],
    freeze_record: dict[str, Any],
    inference_ledger: dict[str, Any],
    sealed_registry: dict[str, Any],
) -> dict[str, Any]:
    verification = verify_preregistration(prereg)
    prereg_sha = verification["prereg_sha256"]
    _require(freeze_record.get("frozen") is True, "confirmatory experiment is not frozen")
    _require(freeze_record.get("experiment_id") == prereg["experiment_id"], "freeze experiment_id mismatch")
    _require(freeze_record.get("prereg_sha256") == prereg_sha, "freeze prereg identity mismatch")
    binding = freeze_record.get("binding") or {}
    _require(binding.get("preregistration_remote_bound") == "verified", "preregistration is not remotely bound")
    _require(binding.get("prereg_sha256") == prereg_sha, "remote binding prereg identity mismatch")
    programme_context = freeze_record.get("programme_context") or {}
    _require(programme_context.get("status") == "selected_and_feasible", "freeze lacks selected programme context")
    context_sha = programme_context.get("sha256")
    _require(isinstance(context_sha, str) and len(context_sha) == 64, "freeze lacks programme evidence identity")
    validate_inference_ledger(inference_ledger)
    matches = [
        entry for entry in inference_ledger["entries"]
        if entry.get("entry_id") == prereg["inference_ledger_entry_id"]
        and entry.get("experiment_id") == prereg["experiment_id"]
    ]
    _require(len(matches) == 1, "programme inference registration is missing or ambiguous")
    sealed = prereg.get("sealed_window") or {}
    if sealed.get("use") not in {None, "none"}:
        window_id = sealed.get("sealed_window_id")
        windows = [item for item in sealed_registry.get("windows", []) if item.get("sealed_window_id") == window_id]
        _require(len(windows) == 1, "sealed confirmation window is missing or ambiguous")
        verify_sealed_access(windows[0], use="confirmatory")
    return {"allowed": True, "experiment_id": prereg["experiment_id"], "prereg_sha256": prereg_sha}


def record_family_inference(ledger: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    from commodity.programme_inference import validate_family_inference_record

    validate_inference_ledger(ledger)
    validate_family_inference_record(record)
    key = (record["family_id"], record["inputs_sha256"])
    _require(
        not any((item["family_id"], item["inputs_sha256"]) == key for item in ledger["family_inference"]),
        "family inference record already exists",
    )
    updated = json.loads(json.dumps(ledger))
    updated["family_inference"].append(json.loads(json.dumps(record)))
    validate_inference_ledger(updated)
    return updated
