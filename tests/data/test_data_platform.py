import json
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[2]
PLATFORM_PATH = ROOT / "config" / "data_platform.json"
PLATFORM_SCHEMA = ROOT / "contracts" / "data_platform.schema.json"
ATLAS_PATH = ROOT / "data" / "manifests" / "ng-phase1-atlas.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_platform_contract_validates_and_freezes_phase1_stack() -> None:
    from jsonschema import ValidationError

    from commodity.data_platform import validate_data_platform

    platform = _load(PLATFORM_PATH)
    Draft202012Validator(_load(PLATFORM_SCHEMA)).validate(platform)
    with pytest.raises(ValidationError):
        validate_data_platform({})
    phase1 = platform["stages"]["phase_1"]["required_stack"]
    assert phase1 == ["postgresql", "parquet_zstd", "duckdb", "polars_arrow"]
    assert set(platform["future_optional_infrastructure"]).isdisjoint(phase1)
    assert platform["cost_policy"]["phase_1_incremental_recurring_spend_target_usd"] == 0


def test_shared_core_is_commodity_neutral_and_second_commodity_needs_no_schema_change() -> None:
    platform = _load(PLATFORM_PATH)
    core = platform["shared_core"]
    forbidden = {"henry_hub", "mmbtu", "023651", "m1_m4", "natural_gas"}
    serialized = json.dumps(core).lower()
    assert not any(token in serialized for token in forbidden)

    required = {
        "commodity", "venue", "instrument", "futures_contract", "series",
        "source", "location", "unit", "currency", "feature", "model", "dataset",
    }
    assert required.issubset(set(core["identity_types"]))
    crude = platform["commodity_module_examples"]["crude_oil"]
    assert set(crude["uses_shared_identity_types"]).issubset(set(core["identity_types"]))
    assert crude["requires_shared_core_schema_change"] is False


def test_temporal_contract_distinguishes_source_vintage_from_storage_snapshot() -> None:
    temporal = _load(PLATFORM_PATH)["temporal_contract"]
    assert "available_at" in temporal["supported_clocks"]
    assert "outcome_available_at" in temporal["supported_clocks"]
    assert temporal["causal_rule"] == "available_at <= decision_time"
    assert temporal["source_vintage_is_database_snapshot"] is False


def test_causal_asof_join_excludes_future_and_preserves_sparse_sessions() -> None:
    from commodity.data_platform import causal_asof_join

    decisions = pd.DataFrame({
        "decision_time": pd.to_datetime([
            "2022-01-03T16:00:00Z", "2022-01-04T16:00:00Z", "2022-01-05T16:00:00Z"
        ]),
        "commodity_id": ["NG", "NG", "NG"],
    })
    facts = pd.DataFrame({
        "commodity_id": ["NG", "NG"],
        "available_at": pd.to_datetime(["2022-01-03T15:00:00Z", "2022-01-05T17:00:00Z"]),
        "value": [10.0, 99.0],
        "source_vintage_id": ["v1", "v2"],
    })
    joined = causal_asof_join(
        decisions, facts, by=["commodity_id"], value_columns=["value", "source_vintage_id"]
    )
    assert list(joined["value"]) == [10.0, 10.0, 10.0]
    assert len(joined) == len(decisions)
    assert joined["protected_confirmation_accessed"].eq(False).all()


def test_causal_asof_join_uses_configured_tie_break_and_rejects_unresolved_ties() -> None:
    from commodity.data_platform import causal_asof_join

    decisions = pd.DataFrame({
        "decision_time": pd.to_datetime(["2022-01-04T16:00:00Z"]),
        "commodity_id": ["NG"],
    })
    facts = pd.DataFrame({
        "commodity_id": ["NG", "NG"],
        "available_at": pd.to_datetime([
            "2022-01-04T15:00:00Z", "2022-01-04T15:00:00Z"
        ]),
        "published_at": pd.to_datetime([
            "2022-01-04T14:00:00Z", "2022-01-04T14:30:00Z"
        ]),
        "source_vintage_id": ["v1", "v2"],
        "value": [10.0, 11.0],
    })
    joined = causal_asof_join(
        decisions, facts, by=["commodity_id"], value_columns=["value", "source_vintage_id"]
    )
    assert joined.loc[0, "value"] == 11.0
    assert joined.loc[0, "source_vintage_id"] == "v2"

    ambiguous = facts.copy()
    ambiguous.loc[1, "published_at"] = ambiguous.loc[0, "published_at"]
    ambiguous.loc[1, "source_vintage_id"] = ambiguous.loc[0, "source_vintage_id"]
    with pytest.raises(ValueError, match="remain tied"):
        causal_asof_join(
            decisions,
            ambiguous,
            by=["commodity_id"],
            value_columns=["value", "source_vintage_id"],
        )


def test_postgres_catalog_ddl_has_generic_identities_and_no_ng_fields() -> None:
    from commodity.data_platform import POSTGRES_CONTROL_DDL

    ddl = POSTGRES_CONTROL_DDL.lower()
    tables = [
        "commodity", "venue", "instrument", "futures_contract", "data_source",
        "series_definition", "raw_artifact", "source_vintage", "feature_definition",
        "dataset_snapshot", "lineage_edge", "quality_result",
    ]
    for table in tables:
        assert f"create table if not exists {table}" in ddl
    for forbidden in ["henry_hub", "023651", "mmbtu", "cftc_code"]:
        assert forbidden not in ddl

    indexed_foreign_keys = [
        "location(parent_location_id)",
        "instrument(commodity_id)",
        "instrument(venue_id)",
        "instrument(quote_unit_id)",
        "instrument(quote_currency_id)",
        "futures_contract(instrument_id)",
        "series_definition(source_id)",
        "series_definition(instrument_id)",
        "series_definition(location_id)",
        "series_definition(unit_id)",
        "raw_artifact(source_id)",
        "source_vintage(source_id)",
        "source_vintage(raw_artifact_id)",
        "source_vintage(revision_of_source_vintage_id)",
        "quality_result(dataset_snapshot_id)",
    ]
    for indexed_fk in indexed_foreign_keys:
        assert f" on {indexed_fk}" in ddl


def test_ng_atlas_reconciles_all_known_families_with_explicit_disposition() -> None:
    source_library = _load(ROOT / "config" / "data_sources.json")["source_library"]["families"]
    atlas = _load(ATLAS_PATH)
    expected = {
        f"{group}.{family}" for group, families in source_library.items() for family in families
    }
    actual = {item["family_id"] for item in atlas["source_families"]}
    assert len(expected) == 42
    assert actual == expected
    allowed = {
        "materialized", "pit_safe_sparse", "pending_validation_acquisition",
        "licensing_held", "rejected",
    }
    assert all(item["disposition"] in allowed for item in atlas["source_families"])
    assert atlas["counts"] == {
        "us_henry_hub": 16, "global_interconnect": 15, "norway_europe": 11, "total": 42
    }


def test_protected_archive_policy_is_non_enumerable_from_development() -> None:
    protected = _load(PLATFORM_PATH)["protected_confirmation"]
    assert protected["development_may_enumerate_protected_assets"] is False
    assert protected["separate_namespace_required"] is True
    assert protected["separate_credentials_required"] is True


def test_bhlr_realtime_vintage_audit_is_explicit_and_protected_safe() -> None:
    atlas = _load(ATLAS_PATH)
    audit = atlas["bhlr_realtime_vintage_audit"]
    assert audit["source_id"] == "LIT-BHLR-RTDB"
    assert audit["pit_eligible_for_development"] is True
    assert audit["last_allowed_trade_date"] == "2022-12-31"
    assert set(audit["predictor_members"]) == {"production", "storage", "consumption"}
    assert audit["outcome_member_excluded"] is True
    assert audit["protected_confirmation_accessed"] is False


def test_feature_registry_versions_existing_families_without_reimplementation() -> None:
    registry = _load(ROOT / "data" / "manifests" / "ng-phase1-feature-registry.json")
    assert registry["protected_confirmation_accessed"] is False
    families = {item["family_id"]: item for item in registry["families"]}
    assert {"technical", "volatility_tail", "market_structure_positioning"} <= set(families)
    for family in families.values():
        assert family["materialization_status"] == "versioned_existing_implementation"
        assert len(family["implementation_sha256"]) == 64
        assert len(family["transform_identity_sha256"]) == 64
        assert family["reimplementation_required"] is False


def test_benchmark_evidence_covers_required_local_workloads_without_protected_data() -> None:
    benchmark = _load(ROOT / "data" / "manifests" / "phase1-benchmark.json")
    assert benchmark["protected_confirmation_accessed"] is False
    assert benchmark["dataset"]["rows"] >= 100_000
    assert benchmark["dataset"]["compression"] == "zstd"
    assert benchmark["engine"]["input_file_to_memory_limit_ratio"] > 1.0
    workloads = benchmark["workloads"]
    assert {
        "parquet_projection_filter", "window", "asof_join",
        "sparse_join", "constrained_memory_scan",
    } <= set(workloads)
    assert workloads["parquet_projection_filter"]["plan_has_filters"] is True
    assert workloads["parquet_projection_filter"]["plan_has_projection"] is True
    assert workloads["constrained_memory_scan"]["input_exceeds_configured_memory"] is True
    assert workloads["sparse_join"]["null_rows"] > 0


def test_phase1_cost_ledger_remains_zero_incremental_recurring_spend() -> None:
    ledger = _load(ROOT / "data" / "manifests" / "phase1-cost-ledger.json")
    assert ledger["target_incremental_recurring_usd_per_month"] == 0
    assert ledger["actual_incremental_recurring_usd_per_month"] == 0
    assert ledger["protected_confirmation_accessed"] is False


def test_postgres_catalog_validation_fails_closed_before_kis_db_configuration() -> None:
    evidence = _load(ROOT / "data" / "manifests" / "phase1-catalog-validation.json")
    assert evidence["static_contract_status"] == "passed"
    assert evidence["postgres_server_validation_status"] in {
        "passed", "blocked_local_runtime_unavailable"
    }
    if evidence["postgres_server_validation_status"] != "passed":
        assert evidence["configuration_rule"] == (
            "Commodity KIS/DBHub remains unconfigured until server validation passes"
        )
