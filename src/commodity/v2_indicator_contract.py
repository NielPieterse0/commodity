from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SPEC_REVISION = "2c2b260971739f6dc39437614d769dea57fe58e2"
SPEC_PATH = "docs/development/v2-indicator-surprise-challenger/spec.md"
SOURCE_POLICY_SHA256 = "63464479a32baf1e72980d19cd084c37007a3270b0b577a3b88dda175cbb3ba5"
ACTIVATION_CONTRACT_PATH = (
    "docs/development/v2-activation-preregistration/activation-contract.json"
)
EXPERIMENT_CANDIDATES_PATH = "config/experiment_candidates.json"
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
MULTIPLICITY_MANIFEST_PATH = (
    "docs/development/v2-activation-preregistration/multiplicity-families.json"
)
MULTIPLICITY_MANIFEST_SHA256 = (
    "07ebd1f753268a81687cc2759aa009348cb389377c53603f22fab32fe7939a86"
)
MULTIPLICITY_FAMILIES = (
    "F82_83_COMPONENT_PROMOTION",
    "F83_ATTRIBUTION",
    "F84_ALL_REQUIRED_COMPARATORS",
    "F85_SENSITIVITY",
)
ALL_INCREMENT_FEATURES = tuple(
    feature for family in FAMILIES for feature in FEATURES_BY_FAMILY[family]
)
IMPLEMENTATION_SOURCE_PATHS = (
    "config/data_sources.json",
    "src/commodity/roll_safe_market.py",
    "src/commodity/v2_indicator_contract.py",
    "src/commodity/v2_indicator_market.py",
    "src/commodity/v2_indicator_weather_storage.py",
    "src/commodity/v2_indicators.py",
)
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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


def _require_git_sha(value: Any, *, label: str) -> str:
    normalized = str(value).lower()
    if not _GIT_SHA_RE.fullmatch(normalized):
        raise IndicatorContractError(f"{label} must be an exact 40-hex Git SHA")
    return normalized


def _require_sha256(value: Any, *, label: str) -> str:
    normalized = str(value).lower()
    if not _SHA256_RE.fullmatch(normalized):
        raise IndicatorContractError(f"{label} must be an exact 64-hex SHA-256")
    return normalized


def _sha256_file(path: Path) -> str:
    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def build_implementation_source_manifest(repo_root: Path) -> dict[str, Any]:
    """Hash every result-affecting #83 implementation/config source."""
    root = repo_root.resolve()
    files: dict[str, str] = {}
    for relative in IMPLEMENTATION_SOURCE_PATHS:
        path = root / relative
        if not path.is_file():
            raise IndicatorContractError(
                f"required #83 implementation source is missing: {relative}"
            )
        files[relative] = _sha256_file(path)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "candidate_id": CANDIDATE_ID,
        "files": files,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


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


def _validate_implementation_revision(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise IndicatorContractError("#83 implementation revision must be an object")
    implementation = _json_copy(value)
    _require_git_sha(
        implementation.get("head"), label="#83 implementation revision head"
    )
    if implementation.get("path") != "src/commodity/v2_indicator_contract.py":
        raise IndicatorContractError("#83 implementation path changed")
    _require_sha256(
        implementation.get("source_manifest_sha256"),
        label="#83 implementation source manifest SHA-256",
    )
    if tuple(implementation.get("source_manifest_paths", ())) != IMPLEMENTATION_SOURCE_PATHS:
        raise IndicatorContractError("#83 implementation source-manifest paths changed")
    return implementation


def _read_committed_bytes(repo_root: Path, relative_path: str, *, label: str) -> bytes:
    try:
        return subprocess.check_output(
            [
                "git",
                "-C",
                str(repo_root.resolve()),
                "show",
                f"HEAD:{relative_path}",
            ]
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise IndicatorContractError(f"unable to read committed {label}") from exc


def _read_committed_json(repo_root: Path, relative_path: str, *, label: str) -> dict[str, Any]:
    raw = _read_committed_bytes(repo_root, relative_path, label=label)
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IndicatorContractError(f"committed {label} must be valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise IndicatorContractError(f"committed {label} must be an object")
    return _json_copy(payload)


def read_frozen_multiplicity_manifest(repo_root: Path) -> bytes:
    return _read_committed_bytes(
        repo_root,
        MULTIPLICITY_MANIFEST_PATH,
        label="frozen #83 multiplicity manifest",
    )


def _verify_multiplicity_manifest(raw: bytes) -> dict[str, Any]:
    if hashlib.sha256(raw).hexdigest() != MULTIPLICITY_MANIFEST_SHA256:
        raise IndicatorContractError("#83 multiplicity manifest differs from the frozen payload")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IndicatorContractError("#83 multiplicity manifest must be valid UTF-8 JSON") from exc
    if not isinstance(payload, Mapping):
        raise IndicatorContractError("#83 multiplicity manifest must be an object")
    return _json_copy(payload)


def _validate_multiple_testing_rule(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise IndicatorContractError("#83 multiplicity rule is missing")
    rule = _json_copy(value)
    expected = {
        "method": "benjamini_hochberg",
        "max_adjusted_p_value": 0.05,
        "family_manifest": MULTIPLICITY_MANIFEST_PATH,
        "family_manifest_sha256": MULTIPLICITY_MANIFEST_SHA256,
        "family_membership_frozen_before_results": True,
        "families": list(MULTIPLICITY_FAMILIES),
        "missing_invalid_prespecified_member_rule": (
            "fail_closed_and_use_p_1_if_numeric_vector_required"
        ),
        "post_result_pool_split_regroup_reclassify_permitted": False,
        "attribution_and_sensitivity_can_rescue_promotion": False,
    }
    if rule != expected:
        raise IndicatorContractError("#83 multiplicity rule differs from the frozen family contract")
    return rule


def bind_activation_contract(
    activation_contract: Mapping[str, Any],
    experiment_candidates: Mapping[str, Any],
    multiplicity_manifest_raw: bytes,
) -> dict[str, Any]:
    contract = _json_copy(activation_contract)
    candidates = _json_copy(experiment_candidates)
    _verify_multiplicity_manifest(multiplicity_manifest_raw)
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
    implementation = _validate_implementation_revision(
        candidate.get("implementation_revision")
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
    multiple_testing_rule = _validate_multiple_testing_rule(
        rules["multiple_testing_rule"]
    )

    binding = {
        "schema_version": 1,
        "candidate_id": CANDIDATE_ID,
        "issue": 83,
        "preparation_revision": {
            "head": SPEC_REVISION,
            "path": SPEC_PATH,
        },
        "implementation_revision": implementation,
        "activation_contract_issue": 81,
        "activation_contract_status": contract.get("status"),
        "activation_execution_authorized": bool(contract.get("execution_authorized")),
        "candidate_execution_authorized": bool(candidate.get("execution_authorized")),
        "model_authority": candidate.get("model_authority"),
        "frozen_v1_control": contract.get("frozen_v1_control"),
        "longitudinal_metrics_binding": contract.get("longitudinal_metrics_binding"),
        "execution_rules": {
            key: multiple_testing_rule if key == "multiple_testing_rule" else rules[key]
            for key in required_rule_keys
        },
        "artifact_namespace": namespaces["83"],
        "stop_failure_criteria": contract.get("stop_failure_criteria"),
        "empirical_release_gate": contract.get("empirical_release_gate"),
    }
    binding["binding_sha256"] = canonical_sha256(binding)
    return binding


def _validated_activation_binding(binding: Mapping[str, Any]) -> dict[str, Any]:
    bound = _json_copy(binding)
    digest = bound.pop("binding_sha256", None)
    if not isinstance(digest, str) or canonical_sha256(bound) != digest:
        raise IndicatorContractError("#83 activation binding hash is invalid")
    return bound


def require_empirical_release(binding: Mapping[str, Any]) -> None:
    """Require release state reconstructed from exact committed authorities.

    The caller-supplied binding is evidence only. It is never itself release authority:
    a canonical checksum can detect accidental mutation but cannot authorize execution.
    """
    supplied = _json_copy(binding)
    _validated_activation_binding(supplied)
    repo_root = Path(__file__).resolve().parents[2]
    try:
        committed_contract = _read_committed_json(
            repo_root,
            ACTIVATION_CONTRACT_PATH,
            label="#81 activation contract",
        )
        committed_candidates = _read_committed_json(
            repo_root,
            EXPERIMENT_CANDIDATES_PATH,
            label="experiment candidate registry",
        )
        committed_multiplicity = read_frozen_multiplicity_manifest(repo_root)
        authoritative = bind_activation_contract(
            committed_contract,
            committed_candidates,
            committed_multiplicity,
        )
    except IndicatorContractError as exc:
        raise EmpiricalReleaseBlocked(
            "#83 empirical execution remains blocked until the exact committed #81/#83 "
            "authorities are frozen and internally consistent"
        ) from exc

    if supplied != authoritative:
        raise IndicatorContractError(
            "#83 activation binding differs from exact committed frozen authorities"
        )

    bound = _validated_activation_binding(authoritative)
    gate = bound.get("empirical_release_gate")
    if not isinstance(gate, Mapping):
        raise EmpiricalReleaseBlocked("#83 empirical release gate is missing")
    audit = gate.get("88")
    release_state = gate.get("release_state")
    implementation = bound.get("implementation_revision")
    if (
        not bound.get("activation_execution_authorized")
        or not bound.get("candidate_execution_authorized")
        or not isinstance(audit, Mapping)
        or not audit.get("satisfied")
        or audit.get("current_state") != audit.get("required_state")
        or not isinstance(release_state, Mapping)
        or release_state.get("83") is not True
        or not isinstance(implementation, Mapping)
    ):
        raise EmpiricalReleaseBlocked(
            "#83 empirical execution remains blocked until corrected #81 and #88 "
            "release the exact bound implementation"
        )


def _utc_timestamp(value: Any, *, label: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise IndicatorContractError(f"{label} must be a valid timestamp") from exc
    if timestamp.tzinfo is None:
        raise IndicatorContractError(f"{label} must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _utc_series(frame: pd.DataFrame, column: str, *, label: str) -> pd.Series:
    values = [
        _utc_timestamp(value, label=f"{label} {column}[{index}]")
        for index, value in frame[column].items()
    ]
    return pd.Series(values, index=frame.index, dtype="datetime64[ns, UTC]")


def _date_identity_series(frame: pd.DataFrame, column: str, *, label: str) -> pd.Series:
    values: list[pd.Timestamp] = []
    for index, value in frame[column].items():
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError) as exc:
            raise IndicatorContractError(
                f"{label} {column}[{index}] must be a valid calendar-date identity"
            ) from exc
        if pd.isna(timestamp):
            raise IndicatorContractError(
                f"{label} {column}[{index}] must be a known calendar-date identity"
            )
        values.append(pd.Timestamp(timestamp.date(), tz="UTC"))
    return pd.Series(values, index=frame.index, dtype="datetime64[ns, UTC]")


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
    for column in ("available_at", "issued_at", "forecast_valid_at"):
        if column in out.columns:
            out[column] = _utc_series(out, column, label=label)
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


def _verify_runtime_source_manifest(
    implementation: Mapping[str, Any],
    runtime_source_manifest: Mapping[str, Any],
) -> str:
    expected = _require_sha256(
        implementation.get("source_manifest_sha256"),
        label="#83 bound implementation source manifest SHA-256",
    )
    observed = _json_copy(runtime_source_manifest)
    observed_digest = observed.pop("manifest_sha256", None)
    observed_digest = _require_sha256(
        observed_digest, label="#83 runtime implementation source manifest SHA-256"
    )
    if canonical_sha256(observed) != observed_digest:
        raise IndicatorContractError(
            "#83 runtime implementation source manifest hash is invalid"
        )
    if observed.get("candidate_id") != CANDIDATE_ID:
        raise IndicatorContractError("#83 runtime source manifest candidate changed")
    if tuple(observed.get("files", {}).keys()) != IMPLEMENTATION_SOURCE_PATHS:
        raise IndicatorContractError("#83 runtime source-manifest paths changed")
    if observed_digest != expected:
        raise IndicatorContractError(
            "#83 runtime implementation sources differ from the exact child "
            "implementation bound by #81"
        )
    return observed_digest


def build_lineage_handoff(
    *,
    binding: Mapping[str, Any],
    input_frame: pd.DataFrame,
    feature_frame: pd.DataFrame,
    implementation_config: Mapping[str, Any],
    implementation_revision: str,
    runtime_source_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    bound = _json_copy(binding)
    digest = bound.pop("binding_sha256", None)
    if not isinstance(digest, str) or canonical_sha256(bound) != digest:
        raise IndicatorContractError("#83 activation binding hash is invalid")
    runtime_revision = _require_git_sha(
        implementation_revision, label="#83 integrated runtime code revision"
    )
    implementation = bound.get("implementation_revision")
    bound_revision: str | None = None
    source_manifest_digest: str | None = None
    if implementation is not None:
        if not isinstance(implementation, Mapping):
            raise IndicatorContractError("#83 implementation revision is invalid")
        bound_revision = _require_git_sha(
            implementation.get("head"), label="#83 bound implementation revision"
        )
        if runtime_source_manifest is None:
            raise IndicatorContractError(
                "#83 runtime implementation source manifest is required"
            )
        source_manifest_digest = _verify_runtime_source_manifest(
            implementation, runtime_source_manifest
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
        "bound_implementation_revision": bound_revision,
        "implementation_source_manifest_sha256": source_manifest_digest,
        "runtime_code_revision": runtime_revision,
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
