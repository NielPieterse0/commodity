from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from commodity.config import config_path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_SCHEMA_PATH = REPO_ROOT / "contracts" / "data_platform.schema.json"

POSTGRES_CONTROL_DDL = """
CREATE TABLE IF NOT EXISTS commodity (
    commodity_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS venue (
    venue_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    timezone TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS unit (
    unit_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    dimension TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS currency (
    currency_id TEXT PRIMARY KEY,
    iso_code TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS location (
    location_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_location_id TEXT REFERENCES location(location_id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS instrument (
    instrument_id TEXT PRIMARY KEY,
    commodity_id TEXT NOT NULL REFERENCES commodity(commodity_id),
    venue_id TEXT REFERENCES venue(venue_id),
    instrument_type TEXT NOT NULL,
    quote_unit_id TEXT REFERENCES unit(unit_id),
    quote_currency_id TEXT REFERENCES currency(currency_id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS futures_contract (
    contract_id TEXT PRIMARY KEY,
    instrument_id TEXT NOT NULL REFERENCES instrument(instrument_id),
    exchange_symbol TEXT NOT NULL,
    expiration_at TIMESTAMPTZ NOT NULL,
    first_notice_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS data_source (
    source_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    source_family TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS series_definition (
    series_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES data_source(source_id),
    instrument_id TEXT REFERENCES instrument(instrument_id),
    location_id TEXT REFERENCES location(location_id),
    unit_id TEXT REFERENCES unit(unit_id),
    natural_grain TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS raw_artifact (
    raw_artifact_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES data_source(source_id),
    sha256 CHAR(64) NOT NULL UNIQUE,
    byte_size BIGINT NOT NULL CHECK (byte_size >= 0),
    retrieved_at TIMESTAMPTZ NOT NULL,
    archive_uri TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS source_vintage (
    source_vintage_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES data_source(source_id),
    raw_artifact_id TEXT REFERENCES raw_artifact(raw_artifact_id),
    issued_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    available_at TIMESTAMPTZ,
    revision_of_source_vintage_id TEXT REFERENCES source_vintage(source_vintage_id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS feature_definition (
    feature_id TEXT PRIMARY KEY,
    feature_family TEXT NOT NULL,
    implementation_version TEXT NOT NULL,
    transform_sha256 CHAR(64) NOT NULL,
    availability_semantics TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS model_definition (
    model_id TEXT PRIMARY KEY,
    implementation_version TEXT NOT NULL,
    code_config_sha256 CHAR(64) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS dataset_snapshot (
    dataset_snapshot_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    protected_confirmation_accessed BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS lineage_edge (
    lineage_edge_id BIGSERIAL PRIMARY KEY,
    parent_identity TEXT NOT NULL,
    child_identity TEXT NOT NULL,
    relationship TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (parent_identity, child_identity, relationship)
);
CREATE TABLE IF NOT EXISTS quality_result (
    quality_result_id BIGSERIAL PRIMARY KEY,
    dataset_snapshot_id TEXT REFERENCES dataset_snapshot(dataset_snapshot_id),
    check_id TEXT NOT NULL,
    status TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS policy_record (
    policy_id TEXT PRIMARY KEY,
    policy_type TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_location_parent_location_id ON location(parent_location_id);
CREATE INDEX IF NOT EXISTS idx_instrument_commodity_id ON instrument(commodity_id);
CREATE INDEX IF NOT EXISTS idx_instrument_venue_id ON instrument(venue_id);
CREATE INDEX IF NOT EXISTS idx_instrument_quote_unit_id ON instrument(quote_unit_id);
CREATE INDEX IF NOT EXISTS idx_instrument_quote_currency_id ON instrument(quote_currency_id);
CREATE INDEX IF NOT EXISTS idx_futures_contract_instrument_id ON futures_contract(instrument_id);
CREATE INDEX IF NOT EXISTS idx_series_definition_source_id ON series_definition(source_id);
CREATE INDEX IF NOT EXISTS idx_series_definition_instrument_id ON series_definition(instrument_id);
CREATE INDEX IF NOT EXISTS idx_series_definition_location_id ON series_definition(location_id);
CREATE INDEX IF NOT EXISTS idx_series_definition_unit_id ON series_definition(unit_id);
CREATE INDEX IF NOT EXISTS idx_raw_artifact_source_id ON raw_artifact(source_id);
CREATE INDEX IF NOT EXISTS idx_source_vintage_source_id ON source_vintage(source_id);
CREATE INDEX IF NOT EXISTS idx_source_vintage_raw_artifact_id ON source_vintage(raw_artifact_id);
CREATE INDEX IF NOT EXISTS idx_source_vintage_revision_id ON source_vintage(revision_of_source_vintage_id);
CREATE INDEX IF NOT EXISTS idx_quality_result_dataset_snapshot_id ON quality_result(dataset_snapshot_id);
"""


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_data_platform() -> dict[str, Any]:
    return json.loads(config_path("data_platform.json").read_text(encoding="utf-8"))


def validate_data_platform(
    platform: dict[str, Any] | None = None,
    *,
    schema_path: Path = PLATFORM_SCHEMA_PATH,
) -> dict[str, Any]:
    from jsonschema import Draft202012Validator

    payload = load_data_platform() if platform is None else platform
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(payload)
    return payload


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")


def _quote_identifier(name: str) -> str:
    if not name or not name.replace("_", "").isalnum() or name[0].isdigit():
        raise ValueError(f"unsafe identifier: {name!r}")
    return f'"{name}"'


def _deduplicate_asof_facts(
    facts: pd.DataFrame,
    *,
    by: Sequence[str],
    available_at: str,
) -> pd.DataFrame:
    keys = [*by, available_at]
    if not bool(facts.duplicated(keys, keep=False).any()):
        return facts

    configured = load_data_platform()["temporal_contract"]["asof_tie_break"]
    tie_columns = [
        column for column in configured
        if column != "available_at" and column in facts.columns
    ]
    if not tie_columns:
        raise ValueError(
            "ambiguous causal AS-OF facts share available_at without configured tie-break evidence"
        )

    tied = facts.groupby([*keys, *tie_columns], dropna=False).size()
    if bool((tied > 1).any()):
        raise ValueError(
            "ambiguous causal AS-OF facts remain tied after configured tie-break columns"
        )

    ordered = facts.sort_values(
        [*keys, *tie_columns],
        kind="mergesort",
        na_position="first",
    )
    return ordered.drop_duplicates(keys, keep="last")


def causal_asof_join(
    decisions: pd.DataFrame,
    facts: pd.DataFrame,
    *,
    by: Sequence[str],
    value_columns: Sequence[str],
    decision_time: str = "decision_time",
    available_at: str = "available_at",
) -> pd.DataFrame:
    import duckdb

    _require_columns(decisions, [decision_time, *by], "decisions")
    _require_columns(facts, [available_at, *by, *value_columns], "facts")
    if decisions.empty:
        result = decisions.copy()
        result["protected_confirmation_accessed"] = False
        return result

    left = decisions.copy()
    left["_decision_order"] = range(len(left))
    right = _deduplicate_asof_facts(
        facts.copy(),
        by=by,
        available_at=available_at,
    )
    con = duckdb.connect(database=":memory:")
    try:
        con.register("decision_rows", left)
        con.register("fact_rows", right)
        equality = " AND ".join(
            f"d.{_quote_identifier(column)} = f.{_quote_identifier(column)}" for column in by
        )
        inequality = (
            f"d.{_quote_identifier(decision_time)} >= f.{_quote_identifier(available_at)}"
        )
        on_clause = f"{equality} AND {inequality}" if equality else inequality
        selected_values = ", ".join(
            f"f.{_quote_identifier(column)} AS {_quote_identifier(column)}"
            for column in value_columns
        )
        extra = f", {selected_values}" if selected_values else ""
        query = f"""
            SELECT d.*,
                   f.{_quote_identifier(available_at)} AS matched_available_at
                   {extra}
            FROM decision_rows AS d
            ASOF LEFT JOIN fact_rows AS f
              ON {on_clause}
            ORDER BY d._decision_order
        """
        result = con.execute(query).df()
    finally:
        con.close()

    if not result.empty and result["matched_available_at"].notna().any():
        invalid = result["matched_available_at"] > result[decision_time]
        if bool(invalid.fillna(False).any()):
            raise ValueError("causal AS-OF join selected a future-available fact")
    result = result.drop(columns=["_decision_order"])
    result["protected_confirmation_accessed"] = False
    return result
