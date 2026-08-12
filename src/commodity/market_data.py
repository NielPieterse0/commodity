from __future__ import annotations

from typing import Any

import pandas as pd


class DataContractViolation(ValueError):
    pass


def validate_contract_history(
    frame: pd.DataFrame,
    schema: dict[str, Any],
) -> pd.DataFrame:
    """Validate and normalize an expiry-aware futures contract table."""
    out = frame.copy()
    required = list(schema["required_columns"])
    missing = [column for column in required if column not in out.columns]
    if missing:
        raise DataContractViolation(f"Missing canonical contract columns: {missing}")
    if out[required].isna().any().any():
        raise DataContractViolation("Canonical contract columns may not contain null values")
    for column in schema.get("timestamp_columns", []):
        if column in out.columns:
            out[column] = pd.to_datetime(out[column], utc=True)
    key = list(schema["unique_key"])
    if out.duplicated(key).any():
        raise DataContractViolation(f"Duplicate canonical contract key: {key}")
    expired = out["trade_date"] > out["expiration"]
    if expired.any():
        raise DataContractViolation("Contract rows may not occur after expiration")
    return out.sort_values(["trade_date", "expiration", "contract_id"]).reset_index(drop=True)


def build_term_structure(
    frame: pd.DataFrame,
    schema: dict[str, Any],
    max_contracts: int = 4,
) -> pd.DataFrame:
    """Build point-in-time contract-rank fields from canonical contract rows."""
    if max_contracts < 1:
        raise ValueError("max_contracts must be positive")
    normalized = validate_contract_history(frame, schema)
    active = normalized[normalized["expiration"] >= normalized["trade_date"]].copy()
    active["contract_rank"] = active.groupby("trade_date").cumcount() + 1
    active = active[active["contract_rank"] <= max_contracts]
    active["days_to_expiry"] = (
        active["expiration"] - active["trade_date"]
    ).dt.total_seconds() / 86400.0

    value_columns = [schema["term_structure_price"], "contract_id", "expiration", "days_to_expiry"]
    pieces = []
    for column in value_columns:
        pivot = active.pivot(index="trade_date", columns="contract_rank", values=column)
        pivot.columns = [f"{column}_{int(rank)}" for rank in pivot.columns]
        pieces.append(pivot)
    return pd.concat(pieces, axis=1).sort_index()


def assert_canonical_market_ready(data_cfg: dict[str, Any]) -> None:
    source = data_cfg["sources"]["market_canonical"]
    continuous = data_cfg["canonical_contract_schema"]["continuous_contract"]
    if not source.get("backtest_evidence_allowed", False):
        raise DataContractViolation("Canonical market source is not approved for backtest evidence")
    if continuous.get("authoritative_storage") != "raw_per_contract":
        raise DataContractViolation("Canonical market evidence must preserve raw per-contract rows")
    if continuous.get("adjustment_method") != "none_stored_raw":
        raise DataContractViolation("Canonical storage may not contain adjusted continuous prices")
    if continuous.get("cross_contract_returns_allowed") is not False:
        raise DataContractViolation("Canonical methodology must prohibit cross-contract returns")


def validate_contract_metadata(
    metadata: dict[str, Any],
    schema: dict[str, Any],
) -> None:
    required = list(schema.get("required_metadata", []))
    missing = [field for field in required if not metadata.get(field)]
    if missing:
        raise DataContractViolation(f"Missing canonical dataset metadata: {missing}")
    retrieved_at = pd.to_datetime(metadata["retrieved_at"], utc=True, errors="coerce")
    if pd.isna(retrieved_at):
        raise DataContractViolation("Canonical dataset metadata has invalid retrieved_at")
