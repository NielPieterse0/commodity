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


def canonical_market_readiness(
    data_cfg: dict[str, Any],
    assumptions_cfg: dict[str, Any],
) -> dict[str, Any]:
    source = data_cfg["sources"]["market_canonical"]
    continuous = data_cfg["canonical_contract_schema"]["continuous_contract"]
    assumption = assumptions_cfg["assumptions"]["continuous_series_policy"]

    history_reasons: list[str] = []
    if not source.get("approved_for_contract_price_history", False):
        history_reasons.append("canonical contract price history is not approved")
    if not source.get("account_history_validated", False):
        history_reasons.append("Massive account history is not validated")
    if not source.get("history_earliest_verified_trade_date"):
        history_reasons.append("verified account history boundary is missing")
    if not source.get("provides_contract_id", False) or not source.get("provides_expiration", False):
        history_reasons.append("canonical contract identity or expiration is unavailable")
    if not source.get("provides_settlement", False):
        history_reasons.append("historical settlement is unavailable")
    if not source.get("historical_volume", False):
        history_reasons.append("historical volume required by the canonical roll policy is unavailable")

    roll_reasons: list[str] = []
    if continuous.get("authoritative_storage") != "raw_per_contract":
        roll_reasons.append("canonical evidence must preserve raw per-contract rows")
    if continuous.get("adjustment_method") != "none_stored_raw":
        roll_reasons.append("canonical storage may not contain adjusted continuous prices")
    if continuous.get("cross_contract_returns_allowed") is not False:
        roll_reasons.append("canonical methodology must prohibit cross-contract returns")
    roll_policy = continuous.get("default_roll_policy")
    assumption_policy = assumption.get("default_roll_policy")
    if roll_policy != "volume_crossover_dte_v1" or assumption_policy != roll_policy:
        roll_reasons.append("canonical roll policy is not the registered volume_crossover_dte_v1")
    policy = assumption.get("policy", {})
    expected_policy = {
        "method": "volume_crossover_dte_v1",
        "confirmation_sessions": 2,
        "forced_roll_days_before_expiry": 3,
        "volume_evidence": "prior_observed_session",
        "crossover": "strict_greater_than",
        "tie_behavior": "reset_confirmation_and_hold",
        "missing_volume_behavior": "reset_confirmation_and_hold",
        "holiday_behavior": "count_observed_sessions_only",
        "contract_unavailable_behavior": "nearest_later_eligible",
        "no_later_contract_behavior": "fail_closed",
    }
    if any(policy.get(key) != value for key, value in expected_policy.items()):
        roll_reasons.append("registered roll policy semantics do not match volume_crossover_dte_v1")

    licensing_ready = source.get("non_display_backtesting_rights_verified") is True
    promotion_ready = source.get("backtest_evidence_allowed") is True
    source_history_ready = not history_reasons
    roll_method_ready = not roll_reasons
    canonical_allowed = (
        source_history_ready and roll_method_ready and licensing_ready and promotion_ready
    )
    reasons = history_reasons + roll_reasons
    if not licensing_ready:
        reasons.append("Massive non-display/backtesting rights are not verified")
    elif not promotion_ready:
        reasons.append("canonical market source is not approved for backtest evidence")
    return {
        "source_history_ready": source_history_ready,
        "roll_method_ready": roll_method_ready,
        "licensing_ready": licensing_ready,
        "promotion_ready": promotion_ready,
        "canonical_evidence_allowed": canonical_allowed,
        "reasons": reasons,
    }


def assert_canonical_market_ready(
    data_cfg: dict[str, Any],
    assumptions_cfg: dict[str, Any],
) -> None:
    report = canonical_market_readiness(data_cfg, assumptions_cfg)
    if not report["canonical_evidence_allowed"]:
        raise DataContractViolation(report["reasons"][0])


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
