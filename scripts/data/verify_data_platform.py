from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from commodity.data_platform import POSTGRES_CONTROL_DDL, validate_data_platform
from commodity.raw_archive import verify_artifact_bytes

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "config" / "data_platform.json"
RAW_MANIFEST = ROOT / "data" / "manifests" / "raw-artifacts.json"
RAW_SCHEMA = ROOT / "contracts" / "raw_artifact_manifest.schema.json"
ATLAS = ROOT / "data" / "manifests" / "ng-phase1-atlas.json"
SOURCES = ROOT / "config" / "data_sources.json"
COSTS = ROOT / "data" / "manifests" / "phase1-cost-ledger.json"
FEATURE_REGISTRY = ROOT / "data" / "manifests" / "ng-phase1-feature-registry.json"
BENCHMARK = ROOT / "data" / "manifests" / "phase1-benchmark.json"
CATALOG_VALIDATION = ROOT / "data" / "manifests" / "phase1-catalog-validation.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def validate_contracts(failures: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    platform = validate_data_platform()
    manifest = load_json(RAW_MANIFEST)
    schema = load_json(RAW_SCHEMA)
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    for error in sorted(validator.iter_errors(manifest), key=lambda item: list(item.path)):
        fail(f"raw manifest schema: {error.message}", failures)

    phase1 = set(platform["stages"]["phase_1"]["required_stack"])
    optional = set(platform["future_optional_infrastructure"])
    if phase1 & optional:
        fail(f"optional infrastructure leaked into Phase 1: {sorted(phase1 & optional)}", failures)
    if platform["cost_policy"]["phase_1_incremental_recurring_spend_target_usd"] != 0:
        fail("Phase 1 recurring-spend target must remain zero", failures)

    ddl = POSTGRES_CONTROL_DDL.lower()
    for token in ("henry_hub", "mmbtu", "023651", "cftc_code"):
        if token in ddl:
            fail(f"commodity-specific token leaked into shared PostgreSQL catalog: {token}", failures)
    return platform, manifest


def validate_atlas(failures: list[str]) -> None:
    atlas = load_json(ATLAS)
    source_families = load_json(SOURCES)["source_library"]["families"]
    expected = {
        f"{group}.{family}"
        for group, families in source_families.items()
        for family in families
    }
    actual = {item["family_id"] for item in atlas["source_families"]}
    if actual != expected:
        fail(
            f"NG atlas family reconciliation mismatch; missing={sorted(expected-actual)}, extra={sorted(actual-expected)}",
            failures,
        )
    counts = atlas["counts"]
    if counts != {
        "us_henry_hub": 16,
        "global_interconnect": 15,
        "norway_europe": 11,
        "total": 42,
    }:
        fail(f"NG atlas counts changed unexpectedly: {counts}", failures)
    if atlas.get("protected_confirmation_accessed") is not False:
        fail("NG atlas must record protected_confirmation_accessed=false", failures)
    bhlr = atlas.get("bhlr_realtime_vintage_audit", {})
    if bhlr.get("source_id") != "LIT-BHLR-RTDB":
        fail("BHLR real-time/vintage audit is missing or has wrong source identity", failures)
    if bhlr.get("pit_eligible_for_development") is not True:
        fail("BHLR predictor vintages must be explicitly classified for development PIT use", failures)
    if bhlr.get("protected_confirmation_accessed") is not False:
        fail("BHLR audit must record protected_confirmation_accessed=false", failures)


def validate_raw_manifest(
    platform: dict[str, Any],
    manifest: dict[str, Any],
    failures: list[str],
) -> list[str]:
    notes: list[str] = []
    if any(item.get("evidence_class") == "protected_confirmation" for item in manifest["artifacts"]):
        fail("development raw manifest must not enumerate protected-confirmation artifacts", failures)
    namespace = manifest.get("archive_namespace", {})
    if namespace.get("protected_namespace_accessible_from_development") is not False:
        fail("protected archive namespace must remain inaccessible from development", failures)

    raw_root_override = os.environ.get("COMMODITY_RAW_WORKING_ROOT")
    raw_root = Path(raw_root_override) if raw_root_override else ROOT / platform["storage_contract"]["raw_working_root"]
    for item in manifest["artifacts"]:
        relative = Path(item["local"]["relative_path"])
        candidate = raw_root / relative.relative_to("data/raw") if relative.parts[:2] == ("data", "raw") else ROOT / relative
        if candidate.is_file():
            try:
                verify_artifact_bytes(item, candidate)
            except ValueError as exc:
                fail(f"{item['raw_artifact_id']}: {exc}", failures)
        else:
            notes.append(f"raw bytes unavailable in this checkout: {relative.as_posix()}")
    return notes


def validate_feature_registry(failures: list[str]) -> None:
    registry = load_json(FEATURE_REGISTRY)
    if registry.get("protected_confirmation_accessed") is not False:
        fail("feature registry must record protected_confirmation_accessed=false", failures)
    families = {item.get("family_id"): item for item in registry.get("families", [])}
    required = {"technical", "volatility_tail", "market_structure_positioning"}
    if not required.issubset(families):
        fail(f"feature registry missing required families: {sorted(required - set(families))}", failures)
    for family_id in required & set(families):
        item = families[family_id]
        if item.get("materialization_status") != "versioned_existing_implementation":
            fail(f"{family_id} is not versioned as an existing implementation", failures)
        if item.get("reimplementation_required") is not False:
            fail(f"{family_id} incorrectly requires reimplementation", failures)
        for key in ("implementation_sha256", "transform_identity_sha256"):
            value = str(item.get(key, ""))
            if len(value) != 64:
                fail(f"{family_id} has invalid {key}", failures)


def validate_benchmark(failures: list[str]) -> None:
    benchmark = load_json(BENCHMARK)
    if benchmark.get("protected_confirmation_accessed") is not False:
        fail("benchmark must record protected_confirmation_accessed=false", failures)
    dataset = benchmark.get("dataset", {})
    if int(dataset.get("rows", 0)) < 100_000:
        fail("benchmark row count is not representative", failures)
    if dataset.get("compression") != "zstd":
        fail("benchmark must exercise Parquet/Zstd", failures)
    row_group_rows = int(dataset.get("row_group_target_rows", 0))
    if not 100_000 <= row_group_rows <= 1_000_000:
        fail("benchmark row-group choice is outside the measured tuning start range", failures)
    workloads = benchmark.get("workloads", {})
    required = {"parquet_projection_filter", "window", "asof_join", "sparse_join", "constrained_memory_scan"}
    if not required.issubset(workloads):
        fail(f"benchmark missing workloads: {sorted(required - set(workloads))}", failures)
    pruning = workloads.get("parquet_projection_filter", {})
    if pruning.get("plan_has_filters") is not True or pruning.get("plan_has_projection") is not True:
        fail("benchmark did not prove DuckDB filter/projection pruning plan", failures)
    constrained = workloads.get("constrained_memory_scan", {})
    if constrained.get("input_exceeds_configured_memory") is not True:
        fail("benchmark did not exercise input larger than configured memory", failures)
    if int(workloads.get("asof_join", {}).get("joined_rows", 0)) <= 0:
        fail("benchmark AS OF join produced no rows", failures)
    if int(workloads.get("sparse_join", {}).get("null_rows", 0)) <= 0:
        fail("benchmark sparse join did not preserve sparse missingness", failures)


def validate_catalog(failures: list[str], *, require_postgres: bool) -> list[str]:
    evidence = load_json(CATALOG_VALIDATION)
    notes: list[str] = []
    ddl_sha256 = hashlib.sha256(POSTGRES_CONTROL_DDL.encode("utf-8")).hexdigest()
    if evidence.get("ddl_sha256") != ddl_sha256:
        fail("PostgreSQL catalog validation evidence is stale for current DDL", failures)
    if evidence.get("static_contract_status") != "passed":
        fail("PostgreSQL catalog static contract validation failed", failures)
    server_status = evidence.get("postgres_server_validation_status")
    if server_status == "passed":
        return notes
    if require_postgres:
        fail(f"PostgreSQL server validation is not complete: {server_status}", failures)
    else:
        notes.append(f"PostgreSQL server validation pending: {server_status}")
    return notes


def validate_costs(failures: list[str]) -> None:
    costs = load_json(COSTS)
    if costs["target_incremental_recurring_usd_per_month"] != 0:
        fail("cost ledger target must remain $0", failures)
    if costs["actual_incremental_recurring_usd_per_month"] != 0:
        fail("Phase 1 introduced recurring spend without explicit approval", failures)
    if costs.get("protected_confirmation_accessed") is not False:
        fail("cost ledger must record protected_confirmation_accessed=false", failures)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-durable-raw", action="store_true")
    parser.add_argument("--require-postgres", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []
    platform, manifest = validate_contracts(failures)
    validate_atlas(failures)
    notes = validate_raw_manifest(platform, manifest, failures)
    validate_feature_registry(failures)
    validate_benchmark(failures)
    notes.extend(validate_catalog(failures, require_postgres=args.require_postgres))
    validate_costs(failures)

    if args.require_durable_raw:
        incomplete = [
            item["raw_artifact_id"]
            for item in manifest["artifacts"]
            if item["durability_status"] != "durably_acquired"
            and item["durability_status"] != "replication_prohibited_by_license"
        ]
        if incomplete:
            fail(f"raw artifacts are not durably acquired: {incomplete}", failures)

    if failures:
        print("data-platform-verification: FAILED")
        for item in failures:
            print(f"- {item}")
        return 2

    print("data-platform-verification: passed")
    for note in notes:
        print(f"- NOTE: {note}")
    namespace_status = manifest.get("archive_namespace", {}).get("status", "not_configured")
    print(f"- raw archive namespace status: {namespace_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
