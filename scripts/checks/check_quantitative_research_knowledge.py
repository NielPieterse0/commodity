from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
ROUTER_PATH = ROOT / "config" / "quantitative_research_knowledge.json"
SCHEMA_PATH = ROOT / "contracts" / "quantitative_research_knowledge.schema.json"

CORE_SOURCES = {"ml4t3", "fpp3", "fde", "dmls"}
REQUIRED_ROUTING = {
    "data_engineering",
    "forecasting",
    "financial_ml_research",
    "feature_engineering",
    "model_selection_and_tuning",
    "temporal_integrity_and_leakage",
    "backtesting_and_trading",
    "production_monitoring",
}
REQUIRED_PLAYBOOKS = {
    "temporal_integrity",
    "target_definition",
    "feature_engineering",
    "validation_and_cross_validation",
    "model_selection_and_tuning",
    "forecast_evaluation",
    "backtesting",
}
REQUIRED_GAPS = {
    "baseline-ladder-and-residual-diagnostics",
    "nested-walk-forward-model-selection",
    "complete-execution-ledger",
    "probabilistic-calibration",
    "training-serving-skew-and-drift",
    "data-pipeline-observability",
}
REQUIRED_LEGACY_ISSUES = {290, 291, 292, 310, 311, 312, 313, 314, 335, 341}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_owner_ref(ref: str) -> None:
    path = ROOT / ref.rstrip("/")
    require(path.exists(), f"knowledge-router owner ref does not exist: {ref}")


def validate_schema(router: dict, schema: dict) -> None:
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(router), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise ValueError(f"knowledge-router schema violation at {location}: {first.message}")


def validate_sources(router: dict) -> None:
    sources = router["sources"]
    require(CORE_SOURCES <= set(sources), "knowledge-router core source set is incomplete")
    require(sources.get("ddia2", {}).get("tier") == 2, "DDIA must remain tier 2")
    for source_id, source in sources.items():
        require(source["url"].startswith("https://"), f"source URL is not stable HTTPS: {source_id}")
        require(bool(source["access"]), f"source access note missing: {source_id}")
        require(bool(source["license_or_copyright"]), f"source rights note missing: {source_id}")


def validate_routes(router: dict) -> None:
    routing = router["routing"]
    source_ids = set(router["sources"])
    require(REQUIRED_ROUTING <= set(routing), "knowledge-router routing domain set is incomplete")
    for route_id, route in routing.items():
        referenced = set(route["primary_sources"]) | set(route["secondary_sources"])
        require(referenced <= source_ids, f"route references unknown source: {route_id}")
        for ref in route["owner_refs"]:
            require_owner_ref(ref)


def validate_playbooks(router: dict) -> None:
    playbooks = router["playbooks"]
    source_ids = set(router["sources"])
    require(REQUIRED_PLAYBOOKS <= set(playbooks), "knowledge-router playbook set is incomplete")
    for playbook_id, playbook in playbooks.items():
        for expected_order, rule in enumerate(playbook["rules"], start=1):
            require(rule["order"] == expected_order, f"playbook order is not sequential: {playbook_id}")
            require(rule["rule_id"].startswith(f"{playbook_id}-"), f"playbook rule id has wrong prefix: {rule['rule_id']}")
            require(set(rule["source_ids"]) <= source_ids, f"playbook rule references unknown source: {rule['rule_id']}")
            for ref in rule["owner_refs"]:
                require_owner_ref(ref)


def validate_methodology_map(router: dict) -> None:
    source_ids = set(router["sources"])
    statuses = {item["status"] for item in router["methodology_map"]}
    require({"covered", "partial", "missing"} <= statuses, "methodology map must expose covered, partial, and missing controls")
    for item in router["methodology_map"]:
        require(set(item["source_authority"]) <= source_ids, f"methodology map references unknown source: {item['control_id']}")
        for ref in item["owner_refs"]:
            require_owner_ref(ref)
        if item["status"] == "covered":
            require(item["missing_control"] is None, f"covered control declares a gap: {item['control_id']}")
        else:
            require(bool(item["missing_control"]), f"non-covered control lacks explicit gap: {item['control_id']}")

    gap_ids = {item["control_id"] for item in router["missing_controls"]}
    require(REQUIRED_GAPS <= gap_ids, "explicit missing-control register is incomplete")
    for item in router["missing_controls"]:
        require(set(item["source_authority"]) <= source_ids, f"missing control references unknown source: {item['control_id']}")


def validate_boundaries(router: dict) -> None:
    legacy = {item["issue"] for item in router["legacy_inputs"]}
    require(REQUIRED_LEGACY_ISSUES <= legacy, "legacy Phase-0 inputs are incomplete")
    copyright_policy = router["copyright_policy"]
    require(copyright_policy["copy_book_prose"] is False, "book prose copying must remain prohibited")
    require(copyright_policy["third_party_code_requires_license_review"] is True, "third-party code must require license review")
    require(copyright_policy["third_party_code_imported_in_phase_zero"] is False, "Phase 0 must not import third-party code")
    protected = router["protected_confirmation_boundary"]
    require(protected["outcomes_must_remain_unread"] is True, "protected outcomes must remain unread")
    require(protected["outcomes_must_not_influence_design_or_selection"] is True, "protected outcomes must not influence design or selection")



def main() -> int:
    try:
        router = load_json(ROUTER_PATH)
        schema = load_json(SCHEMA_PATH)
        validate_schema(router, schema)
        validate_sources(router)
        validate_routes(router)
        validate_playbooks(router)
        validate_methodology_map(router)
        validate_boundaries(router)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"quantitative-research-knowledge: FAILED: {exc}")
        return 2
    print("quantitative-research-knowledge: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
