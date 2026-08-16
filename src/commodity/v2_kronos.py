from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from commodity.roll_policy import parse_volume_crossover_policy

CANDIDATE_ID = "v2-82-kronos-only"
ACTIVATION_CONTRACT_PATH = (
    "docs/development/v2-activation-preregistration/activation-contract.json"
)
MODEL_AUTHORITY = "config/models.json#models.kronos_mini"
MODEL_REVISION = "7fdcc628d87f325ccdbcae0a372622ca7e6813aa"
TOKENIZER_REVISION = "b22fb9cb30a2de2f77e8b617169cd756ba964a08"
MODEL_SHA256 = "a7d5f37e2e9fbd9891f7d7d4f72574512dd1f704fee14223e0a8cd0fbf54197c"
TOKENIZER_SHA256 = "b97ec46b3b72160509e289183eaf7bdf5f0dac5bb9b49522f6d46638a99a8717"
REQUIRED_MARKET_COLUMNS = (
    "trade_date",
    "contract_id",
    "expiration",
    "available_at",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


class KronosContractError(ValueError):
    """Raised when the frozen #82 contract would be violated."""


class EmpiricalReleaseBlocked(RuntimeError):
    """Raised until the corrected #81 freeze and independent #88 release are satisfied."""


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        )
    except (TypeError, ValueError) as exc:
        raise KronosContractError("value must be JSON-serializable") from exc


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KronosContractError(f"{label} must be an object")
    return value


def bind_activation_contract(
    activation_contract: Mapping[str, Any],
    experiment_candidates: Mapping[str, Any],
    kronos_model: Mapping[str, Any],
    assumptions: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate #82 against frozen #81/model/roll authorities without running a model."""
    contract = _json_copy(activation_contract)
    candidates = _json_copy(experiment_candidates)
    model = _json_copy(kronos_model)
    assumptions_copy = _json_copy(assumptions)

    if contract.get("issue") != 81:
        raise KronosContractError("#82 must bind the issue #81 activation contract")
    candidate = _require_mapping(
        candidates.get("candidates", {}).get(CANDIDATE_ID), "#82 candidate"
    )
    if candidate.get("issue") != 82:
        raise KronosContractError("frozen #82 candidate identity is missing")
    if candidate.get("inherits_contract") != ACTIVATION_CONTRACT_PATH:
        raise KronosContractError("#82 does not inherit the frozen #81 contract")
    if candidate.get("model_authority") != MODEL_AUTHORITY:
        raise KronosContractError("#82 model authority changed")

    rules = _require_mapping(contract.get("frozen_execution_rules"), "#81 rules")
    candidate_ids = _require_mapping(rules.get("candidate_ids"), "#81 candidate IDs")
    if candidate_ids.get("82") != CANDIDATE_ID:
        raise KronosContractError("#81 candidate ID binding for #82 changed")
    namespaces = _require_mapping(rules.get("artifact_namespaces"), "artifact namespaces")
    if candidate.get("artifact_namespace") != namespaces.get("82"):
        raise KronosContractError("#82 artifact namespace diverges from #81")

    if model.get("model_revision") != MODEL_REVISION:
        raise KronosContractError("Kronos model revision changed")
    if model.get("tokenizer_revision") != TOKENIZER_REVISION:
        raise KronosContractError("Kronos tokenizer revision changed")
    if model.get("device") != "cpu" or model.get("max_context") != 512:
        raise KronosContractError("Kronos device/context authority changed")
    inference = _require_mapping(model.get("inference"), "Kronos inference authority")
    if dict(inference) != {
        "T": 1.0,
        "top_p": 0.9,
        "sample_count": 1,
        "verbose": False,
    }:
        raise KronosContractError("Kronos frozen inference knobs changed")
    if model.get("local_files_only") is not True:
        raise KronosContractError("Kronos measured loading must be local-files-only")
    artifacts = _require_mapping(model.get("checkpoint_artifacts"), "checkpoint artifacts")
    if artifacts.get("model", {}).get("sha256") != MODEL_SHA256:
        raise KronosContractError("Kronos model artifact hash changed")
    if artifacts.get("tokenizer", {}).get("sha256") != TOKENIZER_SHA256:
        raise KronosContractError("Kronos tokenizer artifact hash changed")

    seed = _require_mapping(rules.get("seed_semantics"), "seed semantics")
    expected_seed_fields = {
        "seed": 0,
        "python_random_seed": 0,
        "numpy_seed": 0,
        "pytorch_seed": 0,
        "cuda_permitted": False,
        "seed_search_permitted": False,
    }
    for key, expected in expected_seed_fields.items():
        if seed.get(key) != expected:
            raise KronosContractError(f"#81 seed semantic changed: {key}")

    coverage = _require_mapping(rules.get("coverage_thresholds"), "coverage thresholds")
    if coverage.get("primary_scored_rows") != 1.0:
        raise KronosContractError("#82 requires full scored-row coverage")
    if coverage.get("fit_rows_for_required_features") != 1.0:
        raise KronosContractError("#82 requires full required-input coverage")

    compute_cap = _require_mapping(rules.get("compute_cost_cap"), "compute cap")
    data_cap = _require_mapping(rules.get("data_cost_cap"), "data cap")
    if compute_cap.get("device") != "cpu" or compute_cap.get("paid_compute_usd") != 0:
        raise KronosContractError("#82 compute authority changed")
    if data_cap.get("new_data_acquisition_usd") != 0:
        raise KronosContractError("#82 data-cost authority changed")
    if data_cap.get("paid_provider_expansion_permitted") is not False:
        raise KronosContractError("#82 paid-provider expansion must remain prohibited")

    roll_owner = _require_mapping(
        assumptions_copy.get("assumptions", {}).get("continuous_series_policy"),
        "continuous-series authority",
    )
    if roll_owner.get("default_roll_policy") != "volume_crossover_dte_v1":
        raise KronosContractError("authoritative #82 roll-policy identity changed")
    parse_volume_crossover_policy(dict(_require_mapping(roll_owner.get("policy"), "roll policy")))

    control = _require_mapping(contract.get("frozen_v1_control"), "frozen V1 control")
    context = _require_mapping(control.get("context_identity"), "frozen V1 context")
    if context.get("forecast_target") != "target_ret_1":
        raise KronosContractError("#82 only permits frozen target_ret_1")
    if context.get("forecast_horizon") != "1 trading session":
        raise KronosContractError("#82 only permits the frozen one-session horizon")
    if control.get("baseline_id") != "zero_return_naive":
        raise KronosContractError("#82 strongest comparable V1 control changed")

    binding = {
        "schema_version": 1,
        "issue": 82,
        "candidate_id": CANDIDATE_ID,
        "activation_contract_issue": 81,
        "activation_contract_status": contract.get("status"),
        "activation_execution_authorized": bool(contract.get("execution_authorized")),
        "empirical_release_gate": contract.get("empirical_release_gate"),
        "preparation_revision": candidate.get("preparation_revision"),
        "implementation_revision": candidate.get("implementation_revision"),
        "model_authority": MODEL_AUTHORITY,
        "model_revision": MODEL_REVISION,
        "tokenizer_revision": TOKENIZER_REVISION,
        "artifact_namespace": namespaces["82"],
        "frozen_v1_control": control,
        "longitudinal_metrics_binding": contract.get("longitudinal_metrics_binding"),
        "seed_semantics": seed,
        "compute_cost_cap": compute_cap,
        "data_cost_cap": data_cap,
        "stop_failure_criteria": contract.get("stop_failure_criteria"),
    }
    binding["binding_sha256"] = canonical_sha256(binding)
    return binding


def require_empirical_release(binding: Mapping[str, Any]) -> None:
    bound = _json_copy(binding)
    digest = bound.pop("binding_sha256", None)
    if not isinstance(digest, str) or canonical_sha256(bound) != digest:
        raise KronosContractError("#82 activation binding hash is invalid")
    gate = _require_mapping(bound.get("empirical_release_gate"), "empirical release gate")
    audit = _require_mapping(gate.get("88"), "#88 release gate")
    release_state = _require_mapping(gate.get("release_state"), "candidate release state")
    if (
        not bound.get("activation_execution_authorized")
        or not audit.get("satisfied")
        or audit.get("current_state") != audit.get("required_state")
        or release_state.get("82") is not True
    ):
        raise EmpiricalReleaseBlocked(
            "#82 empirical execution remains blocked until corrected #81 and #88 release it"
        )


def seed_runtime(torch_module: Any) -> None:
    """Apply the frozen seed to all permitted stochastic runtimes."""
    random.seed(0)
    np.random.seed(0)
    if torch_module is None or not hasattr(torch_module, "manual_seed"):
        raise KronosContractError("PyTorch seed interface is unavailable")
    torch_module.manual_seed(0)
    if hasattr(torch_module, "cuda") and getattr(torch_module.cuda, "is_available", lambda: False)():
        raise KronosContractError("CUDA is prohibited by the frozen #82 contract")


def _utc_timestamp(value: Any, label: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise KronosContractError(f"{label} must be a valid timestamp") from exc
    if timestamp.tzinfo is None:
        raise KronosContractError(f"{label} must be timezone-aware")
    return timestamp.tz_convert("UTC")


def build_pit_context(
    selected_market: pd.DataFrame,
    prediction_time: Any,
    *,
    max_context: int = 512,
) -> pd.DataFrame:
    """Build the exact PIT-eligible OHLCV context while preserving contract traceability."""
    missing = [column for column in REQUIRED_MARKET_COLUMNS if column not in selected_market]
    if missing:
        raise KronosContractError(f"#82 market context is missing columns: {missing}")
    if max_context != 512:
        raise KronosContractError("#82 max_context must remain 512")
    cutoff = _utc_timestamp(prediction_time, "prediction_time")
    frame = selected_market.loc[:, REQUIRED_MARKET_COLUMNS].copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True, errors="coerce")
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True, errors="coerce")
    frame["expiration"] = pd.to_datetime(frame["expiration"], utc=True, errors="coerce")
    if frame[["trade_date", "available_at", "expiration"]].isna().any().any():
        raise KronosContractError("#82 market identity timestamps must be explicit and valid")
    if frame["trade_date"].duplicated().any():
        raise KronosContractError("#82 selected market series must have one row per trade_date")
    if not frame["trade_date"].is_monotonic_increasing:
        raise KronosContractError("#82 selected market input must already be strictly chronological")
    if (frame["contract_id"].astype(str).str.strip() == "").any():
        raise KronosContractError("#82 contract_id must be present for every source row")

    eligible = frame.loc[frame["available_at"] <= cutoff].copy()
    if eligible.empty:
        raise KronosContractError("#82 has no PIT-eligible context rows at the prediction cutoff")
    context = eligible.tail(max_context).copy()
    if len(context) > max_context:
        raise KronosContractError("#82 context exceeds the frozen maximum")

    numeric = context.loc[:, OHLCV_COLUMNS].apply(pd.to_numeric, errors="coerce")
    values = numeric.to_numpy(dtype="float64")
    if not np.isfinite(values).all():
        raise KronosContractError("#82 context contains missing or non-finite OHLCV")
    if (numeric[["open", "high", "low", "close"]] <= 0).any().any():
        raise KronosContractError("#82 OHLC prices must be strictly positive")
    if (numeric["volume"] < 0).any():
        raise KronosContractError("#82 volume must be non-negative")
    if (
        (numeric["high"] < numeric[["open", "close", "low"]].max(axis=1)).any()
        or (numeric["low"] > numeric[["open", "close", "high"]].min(axis=1)).any()
    ):
        raise KronosContractError("#82 OHLC ordering is invalid")
    context.loc[:, OHLCV_COLUMNS] = numeric.astype("float64")
    return context


def adapter_frame(context: pd.DataFrame) -> pd.DataFrame:
    """Strip identity columns only at the adapter boundary after manifesting them."""
    if context.empty:
        raise KronosContractError("#82 adapter context cannot be empty")
    out = context.loc[:, OHLCV_COLUMNS].copy().astype("float64")
    out.index = pd.DatetimeIndex(context["trade_date"], name="timestamp")
    if not out.index.is_monotonic_increasing or not out.index.is_unique:
        raise KronosContractError("#82 adapter index must be strictly increasing and unique")
    return out


def governed_return_prediction(
    *,
    predicted_close_next: Any,
    observed_close_at_cutoff: Any,
    current_contract_id: str,
    target_contract_id: str,
) -> float:
    """Map the model close forecast to target_ret_1 without permitting a cross-contract return."""
    if str(current_contract_id) != str(target_contract_id):
        raise KronosContractError("cross-contract target returns are prohibited")
    try:
        predicted = float(predicted_close_next)
        observed = float(observed_close_at_cutoff)
    except (TypeError, ValueError) as exc:
        raise KronosContractError("#82 close values must be numeric") from exc
    if not math.isfinite(predicted) or not math.isfinite(observed):
        raise KronosContractError("#82 close values must be finite")
    if predicted <= 0 or observed <= 0:
        raise KronosContractError("#82 close values must be strictly positive")
    return float(math.log(predicted / observed))


def build_input_manifest(context: pd.DataFrame, prediction_time: Any) -> dict[str, Any]:
    trace: list[dict[str, Any]] = []
    for row in context.loc[:, REQUIRED_MARKET_COLUMNS].to_dict(orient="records"):
        normalized = dict(row)
        for field in ("trade_date", "expiration", "available_at"):
            normalized[field] = pd.Timestamp(normalized[field]).isoformat()
        for field in OHLCV_COLUMNS:
            normalized[field] = float(normalized[field])
        normalized["contract_id"] = str(normalized["contract_id"])
        trace.append(normalized)
    manifest = {
        "schema_version": 1,
        "candidate_id": CANDIDATE_ID,
        "prediction_time": _utc_timestamp(prediction_time, "prediction_time").isoformat(),
        "row_count": len(trace),
        "columns": list(REQUIRED_MARKET_COLUMNS),
        "rows": trace,
    }
    manifest["context_sha256"] = canonical_sha256(manifest)
    return manifest


def build_model_manifest(
    kronos_model: Mapping[str, Any], artifacts: Mapping[str, Any]
) -> dict[str, Any]:
    model = _json_copy(kronos_model)
    manifest = {
        "schema_version": 1,
        "candidate_id": CANDIDATE_ID,
        "model_id": model.get("model_id"),
        "model_revision": model.get("model_revision"),
        "tokenizer_id": model.get("tokenizer_id"),
        "tokenizer_revision": model.get("tokenizer_revision"),
        "device": model.get("device"),
        "max_context": model.get("max_context"),
        "inference": model.get("inference"),
        "local_files_only": model.get("local_files_only"),
        "artifacts": _json_copy(artifacts),
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def verify_replay(primary_prediction_sha256: str, replay_prediction_sha256: str) -> None:
    if primary_prediction_sha256 != replay_prediction_sha256:
        raise KronosContractError("#82 deterministic replay prediction hash mismatch")


def enforce_cost_caps(
    *,
    elapsed_hours: float,
    paid_compute_usd: float,
    new_data_acquisition_usd: float,
    max_wall_clock_hours: float,
) -> None:
    values = (elapsed_hours, paid_compute_usd, new_data_acquisition_usd, max_wall_clock_hours)
    if any(not math.isfinite(float(value)) or float(value) < 0 for value in values):
        raise KronosContractError("#82 cost/runtime values must be finite and non-negative")
    if elapsed_hours > max_wall_clock_hours:
        raise KronosContractError("#82 runtime exceeded the frozen compute cap")
    if paid_compute_usd != 0:
        raise KronosContractError("#82 paid compute is prohibited")
    if new_data_acquisition_usd != 0:
        raise KronosContractError("#82 new paid data acquisition is prohibited")


def build_longitudinal_handoff(
    binding: Mapping[str, Any],
    *,
    code_revision: str,
    config_sha256: str,
    artifact_sha256s: list[str],
) -> dict[str, Any]:
    metrics = _require_mapping(binding.get("longitudinal_metrics_binding"), "metrics binding")
    if metrics.get("comparison_kinds") != ["previous_stage", "best_comparable"]:
        raise KronosContractError("#78 longitudinal comparison kinds changed")
    if not code_revision or not isinstance(code_revision, str):
        raise KronosContractError("#82 longitudinal handoff requires exact code revision")
    if len(config_sha256) != 64 or any(len(value) != 64 for value in artifact_sha256s):
        raise KronosContractError("#82 longitudinal handoff requires SHA-256 identities")
    return {
        "schema_version": 1,
        "candidate_id": CANDIDATE_ID,
        "authority_contract": metrics.get("authority_contract"),
        "authority_ledger": metrics.get("authority_ledger"),
        "ledger_id": metrics.get("ledger_id"),
        "policy_id": metrics.get("policy_id"),
        "comparison_kinds": list(metrics["comparison_kinds"]),
        "required_metric_ids": list(metrics.get("required_metric_ids", [])),
        "code_revision": code_revision,
        "config_sha256": config_sha256,
        "artifact_sha256s": list(artifact_sha256s),
        "result_disposition_required": True,
    }
