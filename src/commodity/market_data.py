from __future__ import annotations

from typing import Any

import pandas as pd

from commodity.roll_policy import parse_volume_crossover_policy


class DataContractViolation(ValueError):
    pass


def build_contract_rank_windows(
    contracts: list[dict[str, Any]],
    start_trade_date: str,
    end_trade_date: str,
    max_contracts: int,
) -> list[tuple[dict[str, Any], str, str]]:
    """Return per-contract date windows where each contract can be within M1..MN."""
    if max_contracts < 1:
        raise ValueError("max_contracts must be positive")
    start = pd.Timestamp(start_trade_date, tz="UTC")
    end = pd.Timestamp(end_trade_date, tz="UTC")
    if end < start:
        raise ValueError("end_trade_date must be on or after start_trade_date")

    normalized: list[tuple[dict[str, Any], pd.Timestamp, pd.Timestamp | None]] = []
    for contract in contracts:
        last = pd.to_datetime(contract.get("last_trade_date"), utc=True, errors="coerce")
        if pd.isna(last):
            raise DataContractViolation(
                f"Contract {contract.get('ticker', '<unknown>')} is missing a valid last_trade_date"
            )
        first = pd.to_datetime(contract.get("first_trade_date"), utc=True, errors="coerce")
        normalized.append((contract, last, None if pd.isna(first) else first))
    normalized.sort(key=lambda item: (item[1], str(item[0].get("ticker", ""))))

    windows: list[tuple[dict[str, Any], str, str]] = []
    for index, (contract, last, first) in enumerate(normalized):
        eligible = start
        if index >= max_contracts:
            eligible = max(eligible, normalized[index - max_contracts][1] + pd.Timedelta(days=1))
        if first is not None:
            eligible = max(eligible, first)
        fetch_end = min(end, last)
        if eligible <= fetch_end:
            windows.append(
                (contract, eligible.date().isoformat(), fetch_end.date().isoformat())
            )
    return windows

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
        history_reasons.append("canonical provider account history is not validated")
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
    policy = assumption.get("policy", {})
    if not roll_policy or assumption_policy != roll_policy or policy.get("method") != roll_policy:
        roll_reasons.append("canonical roll policy owner and continuous-series reference disagree")
    else:
        try:
            parse_volume_crossover_policy(policy)
        except (TypeError, ValueError) as exc:
            roll_reasons.append(f"registered roll policy semantics are not executable: {exc}")

    licensing_ready = source.get("non_display_backtesting_rights_verified") is True
    promotion_ready = source.get("backtest_evidence_allowed") is True
    source_history_ready = not history_reasons
    roll_method_ready = not roll_reasons
    canonical_allowed = (
        source_history_ready and roll_method_ready and licensing_ready and promotion_ready
    )
    reasons = history_reasons + roll_reasons
    if not licensing_ready:
        reasons.append("canonical provider non-display/backtesting rights are not verified")
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


def build_market_structure_features(
    frame: pd.DataFrame,
    schema: dict[str, Any],
    prediction_cutoffs: pd.DataFrame,
    max_contracts: int = 4,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build expiry-ranked curve features using only quotes available by each cutoff."""
    if max_contracts < 2:
        raise ValueError("max_contracts must be at least 2")
    required_quote_columns = {"available_at", "volume"}
    missing_quote_columns = sorted(required_quote_columns - set(frame.columns))
    if missing_quote_columns:
        raise DataContractViolation(
            f"Market-structure rows missing columns: {missing_quote_columns}"
        )
    required_cutoff_columns = {"trade_date", "prediction_time"}
    missing_cutoff_columns = sorted(required_cutoff_columns - set(prediction_cutoffs.columns))
    if missing_cutoff_columns:
        raise DataContractViolation(
            f"Market-structure cutoffs missing columns: {missing_cutoff_columns}"
        )
    normalized = validate_contract_history(frame, schema)
    if normalized["available_at"].isna().any():
        raise DataContractViolation("Market-structure available_at may not be null")
    cutoffs = prediction_cutoffs.copy()
    cutoffs["trade_date"] = pd.to_datetime(cutoffs["trade_date"], utc=True)
    cutoffs["prediction_time"] = pd.to_datetime(cutoffs["prediction_time"], utc=True)
    if cutoffs[["trade_date", "prediction_time"]].isna().any().any():
        raise DataContractViolation("Market-structure cutoffs contain invalid timestamps")
    if cutoffs["prediction_time"].duplicated().any():
        raise DataContractViolation("Market-structure prediction_time must be unique")

    feature_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    for _, cutoff in cutoffs.sort_values("prediction_time").iterrows():
        trade_date = pd.Timestamp(cutoff["trade_date"])
        prediction_time = pd.Timestamp(cutoff["prediction_time"])
        active = normalized[
            (normalized["trade_date"] == trade_date)
            & (normalized["expiration"] >= trade_date)
        ].sort_values(["expiration", "contract_id"])
        feature_row: dict[str, object] = {"prediction_time": prediction_time}
        audit_row: dict[str, object] = {
            "prediction_time": prediction_time,
            "trade_date": trade_date,
        }
        for rank in range(1, max_contracts + 1):
            prefix = f"m{rank}"
            if rank <= len(active):
                quote = active.iloc[rank - 1]
                quote_available = bool(quote["available_at"] <= prediction_time)
                audit_row[f"contract_id_{prefix}"] = str(quote["contract_id"])
                audit_row[f"expiration_{prefix}"] = quote["expiration"]
                audit_row[f"available_at_{prefix}"] = quote["available_at"]
                audit_row[f"quote_available_{prefix}"] = quote_available
                if quote_available:
                    feature_row[f"curve_settle_{prefix}"] = float(quote["settle"])
                    feature_row[f"curve_volume_{prefix}"] = float(quote["volume"])
                    feature_row[f"curve_dte_{prefix}"] = float(
                        (quote["expiration"] - trade_date).total_seconds() / 86400.0
                    )
                    continue
            else:
                audit_row[f"contract_id_{prefix}"] = None
                audit_row[f"expiration_{prefix}"] = pd.NaT
                audit_row[f"available_at_{prefix}"] = pd.NaT
                audit_row[f"quote_available_{prefix}"] = False
            feature_row[f"curve_settle_{prefix}"] = float("nan")
            feature_row[f"curve_volume_{prefix}"] = float("nan")
            feature_row[f"curve_dte_{prefix}"] = float("nan")
        for rank in range(1, max_contracts):
            left = feature_row[f"curve_settle_m{rank}"]
            right = feature_row[f"curve_settle_m{rank + 1}"]
            feature_row[f"curve_spread_m{rank}_m{rank + 1}"] = (
                float(left) - float(right)
                if pd.notna(left) and pd.notna(right)
                else float("nan")
            )
        first_settle = feature_row["curve_settle_m1"]
        last_settle = feature_row[f"curve_settle_m{max_contracts}"]
        first_dte = feature_row["curve_dte_m1"]
        last_dte = feature_row[f"curve_dte_m{max_contracts}"]
        dte_span = float(last_dte) - float(first_dte) if pd.notna(last_dte) and pd.notna(first_dte) else 0.0
        feature_row[f"curve_slope_m1_m{max_contracts}"] = (
            (float(last_settle) - float(first_settle)) / dte_span
            if pd.notna(first_settle) and pd.notna(last_settle) and dte_span > 0
            else float("nan")
        )
        first_volume = feature_row["curve_volume_m1"]
        second_volume = feature_row["curve_volume_m2"]
        feature_row["curve_volume_ratio_m1_m2"] = (
            float(first_volume) / float(second_volume)
            if pd.notna(first_volume) and pd.notna(second_volume) and float(second_volume) > 0
            else float("nan")
        )
        feature_rows.append(feature_row)
        audit_rows.append(audit_row)
    features = pd.DataFrame(feature_rows).set_index("prediction_time").sort_index()
    audit = pd.DataFrame(audit_rows).set_index("prediction_time").sort_index()
    return features, audit


def ensure_canonical_market_availability(
    frame: pd.DataFrame,
    policy: dict[str, Any],
) -> pd.DataFrame:
    """Preserve source availability or add an explicitly configured conservative bound."""
    out = frame.copy()
    if "available_at" in out.columns:
        out["available_at"] = pd.to_datetime(out["available_at"], utc=True, errors="coerce")
        if out["available_at"].isna().any():
            raise DataContractViolation("Canonical market available_at may not be null or invalid")
        if "availability_status" in out.columns:
            if out["availability_status"].isna().any():
                raise DataContractViolation("Canonical market availability_status may not be null")
            statuses = set(out["availability_status"].astype(str))
            allowed_statuses = {"source_timestamp", "reconstructed_conservative"}
            if len(statuses) != 1 or not statuses.issubset(allowed_statuses):
                raise DataContractViolation(
                    "Canonical market availability_status must be one supported uniform value"
                )
        else:
            out["availability_status"] = "source_timestamp"
        return out

    if policy.get("method") != "trade_date_2359_utc":
        raise DataContractViolation("Canonical market history requires explicit available_at policy")
    if policy.get("status") != "reconstructed_conservative":
        raise DataContractViolation("Canonical market availability policy must be conservative")
    if "trade_date" not in out.columns:
        raise DataContractViolation("Canonical market history requires trade_date")
    trade_date = pd.to_datetime(out["trade_date"], utc=True, errors="coerce")
    if trade_date.isna().any():
        raise DataContractViolation("Canonical market trade_date contains invalid timestamps")
    out["available_at"] = trade_date.dt.normalize() + pd.Timedelta(hours=23, minutes=59)
    out["availability_status"] = "reconstructed_conservative"
    return out
