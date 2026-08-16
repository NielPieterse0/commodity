from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

SPEC_REVISION = "3e55213b967b590187223e2b286063c81672274a"
SPEC_PATH = "docs/development/v2-indicator-surprise-challenger/spec.md"
SOURCE_POLICY_SHA256 = "179e53ff12a5a0a42b4276dd8baef65209c558f896dd15c08b166e18506b35fd"
ACTIVATION_CONTRACT_PATH = (
    "docs/development/v2-activation-preregistration/activation-contract.json"
)
CANDIDATE_ID = "v2-83-indicators-only"
PRIMARY_VARIANT = "I-ALL"
FAMILIES = ("W", "S", "C", "V", "P", "L")
FEATURES_BY_FAMILY = {
    "W": ("weather_hdd65_revision_1run", "weather_cdd65_revision_1run"),
    "S": ("storage_change_accel_bcf",),
    "C": (
        "curve_curvature_123",
        "curve_spread_m1_m2_change_1",
        "curve_slope_m1_m4_change_1",
    ),
    "V": ("vol_ratio_5_20",),
    "P": (
        "managed_money_net_pct_oi",
        "managed_money_net_pct_oi_change_1report",
    ),
    "L": (
        "power_next_day_load_range_mw",
        "power_next_day_load_mean_change_1run_mw",
    ),
}
ATTRIBUTION_VARIANTS = {
    "I-NO-W": "W",
    "I-NO-S": "S",
    "I-NO-C": "C",
    "I-NO-V": "V",
    "I-NO-P": "P",
    "I-NO-L": "L",
}
ALL_INCREMENT_FEATURES = tuple(
    feature for family in FAMILIES for feature in FEATURES_BY_FAMILY[family]
)
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class IndicatorContractError(ValueError):
    """Raised when the frozen #83 contract would be violated."""


class EmpiricalReleaseBlocked(RuntimeError):
    """Raised while #88 has not released #83 empirical execution."""


@dataclass(frozen=True)
class PinnedSourcePolicy:
    payload: Mapping[str, Any]
    sha256: str = SOURCE_POLICY_SHA256


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
    except (TypeError, ValueError) as exc:
        raise IndicatorContractError("value must be JSON-serializable") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _json_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def parse_pinned_source_policy(raw: bytes) -> PinnedSourcePolicy:
    normalized_lf = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    newline_representations = (
        raw,
        normalized_lf,
        normalized_lf.replace(b"\n", b"\r\n"),
    )
    digests = {
        hashlib.sha256(candidate).hexdigest()
        for candidate in newline_representations
    }
    if SOURCE_POLICY_SHA256 not in digests:
        observed = ",".join(sorted(digests))
        raise IndicatorContractError(
            "config/data_sources.json does not match the #83 preparation pin; "
            f"observed newline-normalized digests={observed}"
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IndicatorContractError("source policy must be valid UTF-8 JSON") from exc
    if not isinstance(payload, Mapping):
        raise IndicatorContractError("source policy must be a JSON object")
    return PinnedSourcePolicy(payload=_json_copy(payload))


def bind_activation_contract(
    activation_contract: Mapping[str, Any],
    experiment_candidates: Mapping[str, Any],
) -> dict[str, Any]:
    contract = _json_copy(activation_contract)
    candidates = _json_copy(experiment_candidates)
    if contract.get("issue") != 81:
        raise IndicatorContractError("#83 must bind the issue #81 activation contract")

    candidate = candidates.get("candidates", {}).get(CANDIDATE_ID)
    if not isinstance(candidate, Mapping) or candidate.get("issue") != 83:
        raise IndicatorContractError("frozen #83 candidate identity is missing")
    prep = candidate.get("preparation_revision")
    if not isinstance(prep, Mapping):
        raise IndicatorContractError("#83 preparation revision is missing")
    if prep.get("head") != SPEC_REVISION or prep.get("path") != SPEC_PATH:
        raise IndicatorContractError(
            "#83 preparation revision does not match the frozen spec"
        )
    if candidate.get("inherits_contract") != ACTIVATION_CONTRACT_PATH:
        raise IndicatorContractError(
            "#83 candidate does not inherit the #81 activation contract"
        )
    if rules := contract.get("frozen_execution_rules"):
        candidate_ids = (
            rules.get("candidate_ids", {}) if isinstance(rules, Mapping) else {}
        )
        if candidate_ids.get("83") != CANDIDATE_ID:
            raise IndicatorContractError("#81 candidate ID binding for #83 has changed")
    if candidate.get("primary_variant") != PRIMARY_VARIANT:
        raise IndicatorContractError("I-ALL must remain the sole primary #83 variant")
    if tuple(candidate.get("attribution_only_variants", ())) != tuple(
        ATTRIBUTION_VARIANTS
    ):
        raise IndicatorContractError("the fixed I-NO-* attribution set has changed")

    rules = contract.get("frozen_execution_rules")
    if not isinstance(rules, Mapping):
        raise IndicatorContractError("#81 frozen execution rules are missing")
    namespaces = rules.get("artifact_namespaces")
    if not isinstance(namespaces, Mapping):
        raise IndicatorContractError("#81 artifact namespaces are missing")
    if candidate.get("artifact_namespace") != namespaces.get("83"):
        raise IndicatorContractError("#83 artifact namespace diverges from #81")

    required_rule_keys = (
        "seed_semantics",
        "leakage_guard",
        "coverage_thresholds",
        "material_improvement_rule",
        "uncertainty_significance_rule",
        "multiple_testing_rule",
        "robustness_rule",
        "compute_cost_cap",
        "data_cost_cap",
    )
    missing = [key for key in required_rule_keys if key not in rules]
    if missing:
        raise IndicatorContractError(f"#81 frozen execution rules are missing: {missing}")

    binding = {
        "schema_version": 1,
        "candidate_id": CANDIDATE_ID,
        "issue": 83,
        "preparation_revision": {
            "head": SPEC_REVISION,
            "path": SPEC_PATH,
        },
        "activation_contract_issue": 81,
        "activation_contract_status": contract.get("status"),
        "activation_execution_authorized": bool(contract.get("execution_authorized")),
        "model_authority": candidate.get("model_authority"),
        "frozen_v1_control": contract.get("frozen_v1_control"),
        "longitudinal_metrics_binding": contract.get("longitudinal_metrics_binding"),
        "execution_rules": {key: rules[key] for key in required_rule_keys},
        "artifact_namespace": namespaces["83"],
        "stop_failure_criteria": contract.get("stop_failure_criteria"),
        "empirical_release_gate": contract.get("empirical_release_gate"),
    }
    binding["binding_sha256"] = canonical_sha256(binding)
    return binding


def require_empirical_release(binding: Mapping[str, Any]) -> None:
    bound = _json_copy(binding)
    digest = bound.pop("binding_sha256", None)
    if not isinstance(digest, str) or canonical_sha256(bound) != digest:
        raise IndicatorContractError("#83 activation binding hash is invalid")
    gate = bound.get("empirical_release_gate", {}).get("88", {})
    if (
        not bound.get("activation_execution_authorized")
        or not isinstance(gate, Mapping)
        or not gate.get("satisfied")
        or gate.get("current_state") != gate.get("required_state")
    ):
        raise EmpiricalReleaseBlocked(
            "#83 empirical execution remains blocked until #88 passes the exact binding"
        )


def _utc_timestamp(value: Any, *, label: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise IndicatorContractError(f"{label} must be a valid timestamp") from exc
    if timestamp.tzinfo is None:
        raise IndicatorContractError(f"{label} must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise IndicatorContractError(f"{label} is missing columns: {missing}")


def _finite(value: Any, *, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise IndicatorContractError(f"{label} must be numeric") from exc
    if not np.isfinite(number):
        raise IndicatorContractError(f"{label} must be finite")
    return number


def _eligible_before(
    frame: pd.DataFrame,
    prediction_time: Any,
    *,
    label: str,
) -> tuple[pd.DataFrame, pd.Timestamp]:
    _require_columns(frame, ("available_at",), label=label)
    cutoff = _utc_timestamp(prediction_time, label="prediction_time")
    out = frame.copy()
    out["available_at"] = pd.to_datetime(out["available_at"], utc=True, errors="coerce")
    if out["available_at"].isna().any():
        raise IndicatorContractError(f"{label} has unknown available_at values")
    return out.loc[out["available_at"] <= cutoff].copy(), cutoff


def _source_settings(policy: PinnedSourcePolicy, source_key: str) -> Mapping[str, Any]:
    source = policy.payload.get("sources", {}).get(source_key)
    if not isinstance(source, Mapping):
        raise IndicatorContractError(
            f"pinned source policy is missing sources.{source_key}"
        )
    return source


def _accepted_source_ids(
    policy: PinnedSourcePolicy,
    source_key: str,
) -> set[str]:
    source = _source_settings(policy, source_key)
    values = source.get("accepted_source_ids")
    if not isinstance(values, list) or not values:
        raise IndicatorContractError(
            f"pinned source policy lacks accepted_source_ids for {source_key}"
        )
    result = {str(value) for value in values}
    if not all(result):
        raise IndicatorContractError(
            f"pinned source policy has invalid source identities for {source_key}"
        )
    return result


def _require_accepted_source(
    frame: pd.DataFrame,
    policy: PinnedSourcePolicy,
    source_key: str,
    *,
    label: str,
) -> None:
    _require_columns(frame, ("source_id",), label=label)
    accepted = _accepted_source_ids(policy, source_key)
    observed = set(frame["source_id"].astype(str))
    if not observed or not observed.issubset(accepted):
        raise IndicatorContractError(
            f"{label} uses source identities outside the pinned {source_key} contract"
        )


def _max_staleness(
    policy: PinnedSourcePolicy,
    source_key: str,
) -> pd.Timedelta:
    source = _source_settings(policy, source_key)
    if "max_staleness_hours" in source:
        value = float(source["max_staleness_hours"])
        unit = "h"
    elif "max_staleness_days" in source:
        value = float(source["max_staleness_days"])
        unit = "D"
    else:
        raise IndicatorContractError(
            f"pinned source policy lacks a staleness bound for {source_key}"
        )
    if not np.isfinite(value) or value < 0:
        raise IndicatorContractError(
            f"pinned source policy has invalid staleness for {source_key}"
        )
    return pd.Timedelta(value, unit=unit)


def _require_fresh_current_state(
    available_at: Any,
    cutoff: pd.Timestamp,
    policy: PinnedSourcePolicy,
    source_key: str,
    *,
    label: str,
) -> None:
    available = _utc_timestamp(available_at, label=f"{label} available_at")
    age = cutoff - available
    if age < pd.Timedelta(0) or age > _max_staleness(policy, source_key):
        raise IndicatorContractError(
            f"{label} exceeds the pinned {source_key} staleness bound"
        )


def _json_scalar(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        if value.tzinfo is None:
            return value.isoformat()
        return value.tz_convert("UTC").isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        if not np.isfinite(value):
            raise IndicatorContractError("cannot hash non-finite dataframe values")
        return value
    if pd.isna(value):
        return None
    return value


def dataframe_sha256(frame: pd.DataFrame) -> str:
    normalized = frame.copy()
    normalized = normalized.reset_index(names="__row_index__")
    columns = sorted(str(column) for column in normalized.columns)
    if len(columns) != len(set(columns)):
        raise IndicatorContractError("dataframe columns must be unique for hashing")
    normalized.columns = [str(column) for column in normalized.columns]
    normalized = normalized.loc[:, columns]
    records = [
        {key: _json_scalar(value) for key, value in record.items()}
        for record in normalized.to_dict(orient="records")
    ]
    return canonical_sha256({"columns": columns, "records": records})


def build_lineage_handoff(
    *,
    binding: Mapping[str, Any],
    input_frame: pd.DataFrame,
    feature_frame: pd.DataFrame,
    implementation_config: Mapping[str, Any],
    implementation_revision: str,
) -> dict[str, Any]:
    bound = _json_copy(binding)
    digest = bound.pop("binding_sha256", None)
    if not isinstance(digest, str) or canonical_sha256(bound) != digest:
        raise IndicatorContractError("#83 activation binding hash is invalid")
    if not _GIT_SHA_RE.fullmatch(str(implementation_revision).lower()):
        raise IndicatorContractError(
            "implementation_revision must be an exact 40-hex Git SHA"
        )
    feature_definition = {
        "spec_revision": SPEC_REVISION,
        "spec_path": SPEC_PATH,
        "families": list(FAMILIES),
        "features_by_family": {
            family: list(FEATURES_BY_FAMILY[family]) for family in FAMILIES
        },
        "primary_variant": PRIMARY_VARIANT,
        "attribution_only_variants": list(ATTRIBUTION_VARIANTS),
    }
    handoff = {
        "candidate_id": CANDIDATE_ID,
        "activation_binding_sha256": digest,
        "implementation_revision": str(implementation_revision).lower(),
        "input_sha256": dataframe_sha256(input_frame),
        "feature_sha256": dataframe_sha256(feature_frame),
        "feature_definition_sha256": canonical_sha256(feature_definition),
        "implementation_config_sha256": canonical_sha256(
            _json_copy(implementation_config)
        ),
        "artifact_namespace": bound["artifact_namespace"],
        "longitudinal_metrics_binding": bound["longitudinal_metrics_binding"],
    }
    handoff["artifact_identity_sha256"] = canonical_sha256(handoff)
    return handoff
