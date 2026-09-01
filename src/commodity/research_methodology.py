from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from statistics import NormalDist
from typing import Any

from jsonschema import Draft202012Validator

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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _validate_schema(payload: dict[str, Any], schema_name: str) -> None:
    schema_path = _repo_root() / "contracts" / schema_name
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        details = "; ".join(error.message for error in errors[:5])
        raise MethodologyError(f"{schema_name} validation failed: {details}")


def _compare(value: Any, operator: str, expected: Any) -> bool:
    if operator == "eq":
        return value == expected
    left = float(value)
    right = float(expected)
    if operator == "gte":
        return left >= right
    if operator == "lte":
        return left <= right
    if operator == "gt":
        return left > right
    if operator == "lt":
        return left < right
    raise MethodologyError(f"unsupported comparison operator: {operator!r}")


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
    _validate_schema(prereg, "prereg.schema.json")
    orientation = prereg["orientation"]
    _require(orientation.get("big_picture_ref") == "docs/big-picture.md", "orientation must bind docs/big-picture.md")
    _require(str(orientation.get("where_this_fits", "")).strip(), "orientation requires where_this_fits")
    _require(isinstance(orientation.get("origin_refs"), list) and orientation["origin_refs"], "orientation requires origin_refs")
    _require(str(orientation.get("programme_question", "")).strip(), "orientation requires programme_question")
    for name in ("evidence_scan_ref", "literature_snapshot_ref"):
        ref = prereg[name]
        _require(isinstance(ref, dict), f"{name} must be an immutable artifact reference")
        _require(isinstance(ref.get("path"), str) and ref["path"], f"{name} requires path")
        sha = ref.get("sha256")
        _require(isinstance(sha, str) and len(sha) == 64, f"{name} requires sha256")
    from commodity.research_lifecycle import (
        assert_governed_research_preflight,
        validate_literature_ref,
    )

    assert_governed_research_preflight()
    literature = validate_literature_ref(prereg["literature_snapshot_ref"])
    expectations = prereg["expectations"]
    _require(set(expectations["expected"]).issubset(set(literature["expected_observations"])), "confirmatory expectations must be literature-derived")
    _require(set(expectations["disconfirming"]).issubset(set(literature["disconfirming_observations"])), "confirmatory disconfirmers must be literature-derived")
    dispositions = set(prereg["permitted_human_dispositions"])
    _require(dispositions == HUMAN_DISPOSITIONS, "human disposition enum is incomplete or changed")
    for name, spec in prereg["mepi"].items():
        recomputed = recompute_mepi(spec)
        stored = float(spec.get("value"))
        _require(math.isclose(stored, recomputed, rel_tol=1e-12, abs_tol=1e-12), f"{name} does not match recomputation")
    power = verify_power(prereg)
    _require(power["status"] == "passed", "confirmatory design fails power/detectability gate")
    triggers = prereg["coherence_triggers"]
    directions = {item.get("direction") for item in triggers if isinstance(item, dict)}
    _require("unexpectedly_good" in directions or "both" in directions, "coherence triggers must cover unexpectedly good outcomes")
    _require("unexpectedly_bad" in directions or "both" in directions, "coherence triggers must cover unexpectedly bad outcomes")
    benchmarks = prereg["evaluation"].get("benchmarks")
    _require(isinstance(benchmarks, list) and benchmarks, "at least one benchmark is required")
    if prereg["evaluation"].get("claim_scope") == "trading_usefulness":
        _require("economic_mepi" in prereg["mepi"], "trading-usefulness claims require economic_mepi")
    verify_lineage(prereg)
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
    window = matches[0]
    for key in ("dataset_id", "start", "end", "content_sha256"):
        _require(sealed.get(key) == window.get(key), f"sealed window protected identity mismatch: {key}")
    result = verify_sealed_access(window, use="confirmatory")
    return {**result, "sealed_window_id": window_id, "dataset_id": window.get("dataset_id"), "content_sha256": window.get("content_sha256")}


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


def derive_evidence_level(raw_evidence: dict[str, Any]) -> str:
    primary = raw_evidence.get("primary") or {}
    try:
        effect = float(primary["effect"])
        p_value = float(primary["p_value"])
        alpha = float(primary["alpha"])
        scientific_mepi = float(primary["scientific_mepi"])
    except (KeyError, TypeError, ValueError):
        return "E0"
    if not all(math.isfinite(value) for value in (effect, p_value, alpha, scientific_mepi)):
        return "E0"
    if effect == 0:
        return "E0"
    level = "E1"
    if not (0 <= p_value <= alpha < 1 and abs(effect) >= scientific_mepi > 0):
        return level
    level = "E2"
    robustness = (raw_evidence.get("robustness") or {}).get("checks") or []
    if len(robustness) < 2:
        return level
    for check in robustness:
        if not isinstance(check, dict) or not _compare(check.get("value"), str(check.get("operator")), check.get("threshold")):
            return level
    level = "E3"
    economics = raw_evidence.get("economics") or {}
    try:
        if float(economics["net_effect"]) < float(economics["economic_mepi"]):
            return level
    except (KeyError, TypeError, ValueError):
        return level
    level = "E4"
    replications = (raw_evidence.get("replication") or {}).get("independent_results") or []
    successful_replication = False
    for item in replications:
        try:
            successful_replication = (
                abs(float(item["effect"])) >= float(item["scientific_mepi"]) > 0
                and 0 <= float(item["p_value"]) <= float(item["alpha"]) < 1
            )
        except (KeyError, TypeError, ValueError):
            successful_replication = False
        if successful_replication:
            break
    if not successful_replication:
        return level
    level = "E5"
    programme = raw_evidence.get("programme") or {}
    try:
        if not (0 <= float(programme["adjusted_p_value"]) <= float(programme["alpha"]) < 1):
            return level
    except (KeyError, TypeError, ValueError):
        return level
    return "E6"


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
        evidence = checks.get(name)
        _require(isinstance(evidence, dict), f"{name} requires bounded check evidence, not a boolean declaration")
        sha = evidence.get("evidence_sha256")
        _require(isinstance(sha, str) and len(sha) == 64, f"{name} evidence requires evidence_sha256")
        evidence_path = evidence.get("evidence_path")
        _require(isinstance(evidence_path, str) and evidence_path, f"{name} evidence requires evidence_path")
        artifact_path = Path(evidence_path)
        _require(artifact_path.is_file(), f"{name} evidence artifact is missing")
        actual_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        _require(actual_sha == sha, f"{name} evidence hash mismatch")
        artifact = load_json(artifact_path)
        _require("observed" in artifact, f"{name} evidence artifact lacks observed value")
        try:
            passed = _compare(artifact.get("observed"), str(evidence.get("operator")), evidence.get("expected"))
        except (TypeError, ValueError):
            findings.append(verification_finding("CHECKED", name, f"Bounded {name.replace('_', ' ')} check is incomplete."))
            continue
        message = (
            f"Bounded {name.replace('_', ' ')} check passed against evidence {sha[:12]}."
            if passed
            else f"Bounded {name.replace('_', ' ')} check failed against evidence {sha[:12]}."
        )
        findings.append(verification_finding("CHECKED", name, message))
    return findings


def derive_coherence(prereg: dict[str, Any], observed_metrics: dict[str, Any]) -> dict[str, Any]:
    triggered: list[str] = []
    declared: dict[str, str] = {}
    for item in prereg.get("coherence_triggers", []):
        trigger_id = item.get("id")
        direction = item.get("direction")
        if not trigger_id or not direction:
            continue
        declared[trigger_id] = direction
        metric = item.get("metric")
        if metric is None:
            continue
        if metric not in observed_metrics:
            continue
        if _compare(observed_metrics[metric], str(item.get("operator")), item.get("threshold")):
            triggered.append(trigger_id)
    return {
        "declared": declared,
        "triggered": sorted(triggered),
        "trigger_directions": {key: declared[key] for key in sorted(triggered)},
        "undeclared_observations": [],
        "enhanced_audit_required": bool(triggered),
    }


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
    expected_dataset = prereg["datasets"][0]
    identities = (
        (results.get("data", {}).get("dataset_id"), expected_dataset.get("id"), "dataset"),
        (results.get("data", {}).get("vintage_id"), expected_dataset.get("vintage"), "vintage"),
        (results.get("data", {}).get("split_id"), expected_dataset.get("split_id"), "split"),
        (results.get("features", {}).get("definition_id"), prereg["features"].get("definition_id"), "feature definition"),
        (results.get("features", {}).get("preprocessing_id"), prereg["features"].get("preprocessing_id"), "preprocessing"),
        (results.get("model", {}).get("family"), prereg["model"].get("family"), "model family"),
        (results.get("model", {}).get("configuration_id"), prereg["model"].get("configuration_id"), "model configuration"),
    )
    for observed, expected, label in identities:
        _require(observed == expected, f"results execution identity mismatch: {label}")
    method = results.get("method_compliance")
    _require(method in {"VERIFIED", "FAILED", "INCOMPLETE"}, "invalid method compliance")
    raw = results.get("raw_evidence")
    _require(isinstance(raw, dict), "results require raw_evidence")
    derived = derive_evidence_level(raw)
    _require(results.get("scientific_evidence") == derived, "scientific evidence must be machine-derived from numeric evidence")
    findings = results.get("verification", [])
    for finding in findings:
        verification_finding(finding["truth_class"], finding["code"], finding["message"])
    coherence = results.get("coherence") or {}
    if coherence.get("enhanced_audit_required") is True:
        _require(coherence.get("audit_completed") is True or method == "INCOMPLETE", "triggered coherence audit must be completed or results marked INCOMPLETE")
    return {"status": "verified", "prereg_sha256": expected_sha, "scientific_evidence": derived, "method_compliance": method}


def verify_interpretation_metadata(metadata: dict[str, Any], prereg: dict[str, Any], results: dict[str, Any]) -> None:
    _validate_schema(metadata, "interpretation_metadata.schema.json")
    _require(metadata.get("schema_version") == 2, "interpretation metadata schema_version must be 2")
    _require(metadata.get("experiment_id") == prereg["experiment_id"], "interpretation experiment_id mismatch")
    expected_prereg = canonical_prereg_sha256(prereg)
    _require(metadata.get("prereg_sha256") == expected_prereg, "interpretation prereg identity mismatch")
    result_sha = hashlib.sha256(canonical_json_bytes(results)).hexdigest()
    _require(metadata.get("results_sha256") == result_sha, "interpretation results identity mismatch")
    _require(metadata.get("human_disposition") in HUMAN_DISPOSITIONS, "invalid human disposition")
    from commodity.research_lifecycle import validate_literature_ref

    post_ref = metadata["post_result_literature_snapshot_ref"]
    validate_literature_ref(post_ref)
    _require(post_ref.get("sha256") != prereg["literature_snapshot_ref"].get("sha256"), "post-result triangulation must use an independent literature snapshot")
    _require(str(metadata.get("observed_vs_expected", "")).strip(), "interpretation requires expected-vs-observed comparison")
    _require(str(metadata.get("external_triangulation", "")).strip(), "interpretation requires external post-result triangulation")


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
    scan_ref = prereg.get("evidence_scan_ref") or {}
    _require(scan_ref.get("scan_id") == evidence_map.get("current_scan_id"), "preregistration evidence scan is not the current programme scan")
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
        and item.get("feasibility") == "go"
    ]
    _require(matches, "programme feasibility does not permit confirmatory freeze")
    match = matches[0]
    for key in ("scientific_mepi", "economic_mepi"):
        if key in match:
            prereg_value = float(prereg.get("mepi", {}).get(key, {}).get("value", math.nan))
            _require(math.isclose(prereg_value, float(match[key]), rel_tol=1e-12, abs_tol=1e-12), f"programme {key} MEPI mismatch")
    if match.get("market_implied_benchmark_required") is True:
        benchmarks = prereg.get("evaluation", {}).get("benchmarks", [])
        _require(any(item.get("type") == "market_implied" for item in benchmarks), "market-implied comparator is required by governed target/horizon context")
    return {"status": "selected_and_feasible", "research_line_id": line["research_line_id"], "scan_id": evidence_map.get("current_scan_id")}


def build_results(
    prereg: dict[str, Any], *, run_id: str, code: dict[str, Any], data: dict[str, Any],
    model: dict[str, Any], environment: dict[str, Any], raw_evidence: dict[str, Any],
    verification: list[dict[str, str]], coherence: dict[str, Any] | None, artifacts: list[dict[str, Any]],
    features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prereg_check = verify_preregistration(prereg)
    checked_messages = [
        item.get("message", "").lower()
        for item in verification
        if item.get("truth_class") == "CHECKED"
    ]
    detected_violation = any("failed" in message or "detected a violation" in message for message in checked_messages)
    incomplete_check = any("incomplete" in message for message in checked_messages)
    derived_coherence = derive_coherence(prereg, raw_evidence.get("metrics", {}))
    supplied_coherence = coherence or {}
    derived_coherence["audit_completed"] = supplied_coherence.get("audit_completed") is True
    coherence_incomplete = derived_coherence["enhanced_audit_required"] and not derived_coherence["audit_completed"]
    if detected_violation:
        method_compliance = "FAILED"
    elif incomplete_check or coherence_incomplete:
        method_compliance = "INCOMPLETE"
    else:
        method_compliance = "VERIFIED"
    evidence = derive_evidence_level(raw_evidence)
    family_record = run_family_inference(prereg, raw_evidence) if raw_evidence.get("family_inference") else None
    feature_identity = features or {
        "definition_id": prereg["features"].get("definition_id"),
        "preprocessing_id": prereg["features"].get("preprocessing_id"),
    }
    return {
        "schema_version": 1,
        "experiment_id": prereg["experiment_id"],
        "run_id": run_id,
        "prereg_sha256": prereg_check["prereg_sha256"],
        "code": code, "data": data, "features": feature_identity, "model": model, "environment": environment,
        "raw_evidence": raw_evidence, "verification": verification,
        "method_compliance": method_compliance, "scientific_evidence": evidence,
        "coherence": derived_coherence, "family_inference": family_record, "artifacts": artifacts,
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
    signature = subprocess.run(
        ["git", "-C", str(repo_root), "verify-tag", tag],
        capture_output=True,
        text=True,
        check=False,
    )
    _require(signature.returncode == 0, f"preregistration tag signature verification failed: {signature.stderr.strip()}")
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


def verify_reference_artifact(ref: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    _require(isinstance(ref, dict), "frozen reference must be an object")
    relative = ref.get("path")
    _require(isinstance(relative, str) and relative, "frozen reference requires path")
    root = Path(repo_root).resolve()
    path = (root / relative).resolve()
    _require(root == path or root in path.parents, "frozen reference escapes repository root")
    _require(path.is_file(), f"frozen reference artifact does not exist: {relative}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    _require(actual == ref.get("sha256"), f"frozen reference hash mismatch: {relative}")
    return {"path": relative, "sha256": actual}


def verify_lineage(
    prereg: dict[str, Any],
    known_predecessor_sha256: str | None = None,
    repo_root: Path | None = None,
) -> None:
    lineage = prereg.get("lineage") or {}
    predecessor = lineage.get("supersedes_prereg_sha256")
    if predecessor is None:
        _require(not lineage.get("amendment_reason"), "initial preregistration cannot declare amendment reason")
        _require(not lineage.get("supersedes_prereg_path"), "initial preregistration cannot declare predecessor path")
        return
    _require(isinstance(predecessor, str) and len(predecessor) == 64, "successor preregistration requires exact predecessor SHA")
    predecessor_path = lineage.get("supersedes_prereg_path")
    _require(isinstance(predecessor_path, str) and predecessor_path, "successor preregistration requires predecessor path")
    _require(str(lineage.get("amendment_reason", "")).strip(), "successor preregistration requires amendment reason")
    if known_predecessor_sha256 is not None:
        _require(predecessor == known_predecessor_sha256, "successor preregistration predecessor mismatch")
    if repo_root is not None:
        root = Path(repo_root).resolve()
        path = (root / predecessor_path).resolve()
        _require(root in path.parents, "successor predecessor path escapes repository root")
        _require(path.is_file(), "successor predecessor preregistration is missing")
        _require(canonical_prereg_sha256(load_json(path)) == predecessor, "successor predecessor preregistration identity mismatch")


def run_family_inference(prereg: dict[str, Any], raw_evidence: dict[str, Any]) -> dict[str, Any]:
    from commodity.programme_inference import (
        benjamini_hochberg,
        hansen_spa,
        model_confidence_set,
        white_reality_check,
    )

    spec = raw_evidence.get("family_inference") or {}
    procedure = spec.get("procedure")
    frozen_procedure = prereg.get("evaluation", {}).get("programme_inference_procedure")
    _require(procedure == frozen_procedure, "family inference procedure does not match frozen preregistration")
    declared = set(prereg.get("evaluation", {}).get("candidate_family", []))
    if procedure in {"white_reality_check", "hansen_spa"}:
        values = spec.get("loss_differentials") or {}
        _require(set(values) == declared, "family inference inputs do not match declared candidate family")
        fn = white_reality_check if procedure == "white_reality_check" else hansen_spa
        result = fn(values, bootstrap_samples=int(spec.get("bootstrap_samples", 2000)), block_length=int(spec.get("block_length", 5)), seed=int(spec.get("seed", 0)))
    elif procedure == "model_confidence_set":
        values = spec.get("losses") or {}
        _require(set(values) == declared, "family inference inputs do not match declared candidate family")
        result = model_confidence_set(values, alpha=float(spec.get("alpha", 0.05)), bootstrap_samples=int(spec.get("bootstrap_samples", 2000)), block_length=int(spec.get("block_length", 5)), seed=int(spec.get("seed", 0)))
    elif procedure == "benjamini_hochberg":
        values = spec.get("pvalues") or {}
        _require(set(values) == declared, "family inference inputs do not match declared candidate family")
        result = benjamini_hochberg(values, alpha=float(spec.get("alpha", 0.05)))
        result["inputs_sha256"] = hashlib.sha256(canonical_json_bytes(values)).hexdigest()
    else:
        raise MethodologyError(f"unsupported family inference procedure: {procedure!r}")
    return {"family_id": prereg["evaluation"]["statistical_family"], "procedure": procedure, "inputs_sha256": result["inputs_sha256"], "implementation_ref": f"commodity.programme_inference.{procedure}", "result": result}


def update_programme_evidence_map(
    evidence_map: dict[str, Any], prereg: dict[str, Any], results: dict[str, Any], *, new_scan_id: str
) -> dict[str, Any]:
    _require(evidence_map.get("programme_id") == prereg.get("programme_id"), "programme evidence does not match preregistration")
    _require(isinstance(new_scan_id, str) and new_scan_id.strip(), "programme update requires new_scan_id")
    updated = json.loads(json.dumps(evidence_map))
    matches = [item for item in updated.get("research_lines", []) if item.get("research_line_id") == prereg.get("research_line_id")]
    _require(len(matches) == 1, "programme update research line is missing or ambiguous")
    line = matches[0]
    history = line.setdefault("experiment_history", [])
    _require(not any(item.get("experiment_id") == prereg["experiment_id"] for item in history), "programme evidence already records experiment")
    history.append({
        "experiment_id": prereg["experiment_id"],
        "prereg_sha256": canonical_prereg_sha256(prereg),
        "scientific_evidence": results.get("scientific_evidence"),
        "method_compliance": results.get("method_compliance"),
    })
    updated["previous_scan_id"] = updated.get("current_scan_id")
    updated["current_scan_id"] = new_scan_id
    return updated


def execute_reproduction(
    command: list[str], output_path: Path, reference: dict[str, Any], tolerance: dict[str, float], *, cwd: Path
) -> dict[str, Any]:
    _require(isinstance(command, list) and command and all(isinstance(item, str) and item for item in command), "reproduction requires argv")
    output_path = Path(output_path)
    _require(not output_path.exists(), "reproduction output must not pre-exist")
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, check=False)
    _require(result.returncode == 0, f"reproduction command failed: {result.stderr.strip()}")
    _require(output_path.is_file(), "reproduction command did not produce declared output")
    candidate = load_json(output_path)
    verified = verify_reproduction(reference, candidate, tolerance)
    command_sha = hashlib.sha256(canonical_json_bytes({"argv": command})).hexdigest()
    return {**verified, "executed": True, "command_sha256": command_sha, "output": str(output_path)}


def verify_completion_artifacts(experiment_dir: Path) -> dict[str, Any]:
    experiment_dir = Path(experiment_dir)
    required = ("prereg.json", "results.json", "interpretation.md", "record.json", "executive-summary.md")
    missing = [name for name in required if not (experiment_dir / name).is_file()]
    _require(not missing, f"completed experiment missing required artifacts: {', '.join(missing)}")
    return {"status": "complete", "artifacts": list(required)}


def verify_reproduction_contract(prereg: dict[str, Any], command_spec_path: Path, output_path: Path) -> dict[str, Any]:
    reproduction = prereg.get("reproduction") or {}
    expected_sha = reproduction.get("command_spec_sha256")
    _require(isinstance(expected_sha, str) and len(expected_sha) == 64, "frozen reproduction contract does not permit command execution")
    command_spec_path = Path(command_spec_path)
    _require(command_spec_path.is_file(), "reproduction command spec is missing")
    actual_sha = hashlib.sha256(command_spec_path.read_bytes()).hexdigest()
    _require(actual_sha == expected_sha, "reproduction command spec does not match frozen contract")
    expected_output = reproduction.get("output_filename")
    if expected_output is not None:
        _require(Path(output_path).name == expected_output, "reproduction output does not match frozen contract")
    return {"command_spec_sha256": actual_sha, "output_filename": Path(output_path).name}
