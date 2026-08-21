from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from commodity.kronos import KronosCheckpointAdapter
from commodity.v2_kronos import governed_kronos_forecast, governed_return_prediction

CONFIRMATION_CONFIG_PATH = "config/kronos_confirmation.json"
AUDIT_RELEASE_PATH = (
    "docs/development/kronos-three-checkpoint-confirmation/audit-release.json"
)
MODEL_KEYS = {
    "mini": "kronos_mini",
    "small": "kronos_small",
    "base": "kronos_base",
}


class KronosConfirmationError(RuntimeError):
    """Raised when the frozen #180 confirmation contract cannot be proven."""


def _normalized_sha256(path: Path) -> str:
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(raw).hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KronosConfirmationError(f"cannot read frozen JSON: {path}") from exc
    if not isinstance(value, dict):
        raise KronosConfirmationError(f"frozen JSON must be an object: {path}")
    return value


def load_confirmation_freeze(repo_root: Path) -> dict[str, Any]:
    return _load_json(repo_root / CONFIRMATION_CONFIG_PATH)


def _require_file_hash(repo_root: Path, relative: str, expected: str) -> None:
    path = repo_root / relative
    if not path.is_file() or _normalized_sha256(path) != expected:
        raise KronosConfirmationError(f"frozen authority drifted: {relative}")


def validate_confirmation_freeze(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    freeze = load_confirmation_freeze(root)
    if freeze.get("experiment_id") != "kronos-180-corrected-three-checkpoint-v1":
        raise KronosConfirmationError("unexpected Kronos confirmation experiment identity")
    if (freeze.get("issue"), freeze.get("freeze_issue"), freeze.get("audit_issue")) != (
        180,
        182,
        183,
    ):
        raise KronosConfirmationError("Kronos confirmation issue lineage changed")
    if freeze.get("freeze_self_authorizes_execution") is not False:
        raise KronosConfirmationError("the freeze must never self-authorize execution")

    implementation = freeze.get("implementation_authority", {})
    manifest = dict(implementation.get("source_manifest", {}))
    digest = manifest.pop("manifest_sha256", None)
    if not isinstance(digest, str) or _canonical_sha256(manifest) != digest:
        raise KronosConfirmationError("corrected implementation manifest digest is invalid")
    files = manifest.get("files", {})
    if not isinstance(files, dict):
        raise KronosConfirmationError("corrected implementation manifest files are invalid")
    for relative, expected in files.items():
        _require_file_hash(root, str(relative), str(expected))

    models = _load_json(root / "config/models.json")["models"]
    frozen_models = freeze.get("models", {})
    for label, model_key in MODEL_KEYS.items():
        model = models[model_key]
        frozen = frozen_models[label]
        checks = {
            "model_id": model.get("model_id"),
            "model_revision": model.get("model_revision"),
            "tokenizer_id": model.get("tokenizer_id"),
            "tokenizer_revision": model.get("tokenizer_revision"),
            "model_sha256": model.get("checkpoint_artifacts", {}).get("model", {}).get("sha256"),
            "tokenizer_sha256": model.get("checkpoint_artifacts", {}).get("tokenizer", {}).get("sha256"),
        }
        for field, observed in checks.items():
            if frozen.get(field) != observed:
                raise KronosConfirmationError(f"{label} frozen {field} drifted")
        if model.get("device") != "cpu" or model.get("max_context") != 512:
            raise KronosConfirmationError(f"{label} device/context drifted")
        if model.get("local_files_only") is not True:
            raise KronosConfirmationError(f"{label} must remain local-files-only")

    common = freeze.get("common_execution", {})
    if common.get("max_context") != 512 or common.get("horizon_trading_sessions") != 1:
        raise KronosConfirmationError("common Kronos context/horizon drifted")
    if common.get("context_transformation") != "same_contract_history_v1":
        raise KronosConfirmationError("same-contract transformation drifted")
    if common.get("single_contract_required") is not True:
        raise KronosConfirmationError("single-contract guard must remain enabled")
    if common.get("cross_contract_target_return_permitted") is not False:
        raise KronosConfirmationError("cross-contract target returns must remain prohibited")
    if common.get("inference") != {
        "T": 1.0,
        "top_p": 0.9,
        "sample_count": 1,
        "verbose": False,
    }:
        raise KronosConfirmationError("common inference profile drifted")

    data = freeze.get("data_and_target", {})
    _require_file_hash(
        root,
        data["inherits_activation_contract"],
        data["activation_contract_sha256"],
    )
    _require_file_hash(root, data["v1_experiment"], data["v1_experiment_sha256"])
    evaluation = freeze.get("evaluation", {})
    _require_file_hash(
        root,
        evaluation["statistical_evaluator"],
        evaluation["statistical_evaluator_sha256"],
    )
    benchmarks = freeze.get("benchmarks", {})
    _require_file_hash(root, benchmarks["authority"], benchmarks["authority_sha256"])

    activation = _load_json(root / data["inherits_activation_contract"])
    context = activation["frozen_v1_control"]["context_identity"]
    for field in (
        "dataset_id", "data_vintage_id", "dataset_sha256", "forecast_target",
        "forecast_horizon", "oos_rows", "oos_start", "oos_end",
        "coverage_signature_sha256", "protocol_id", "protocol_sha256", "split_id",
        "split_sha256", "availability_rule_id", "availability_rule_sha256",
    ):
        if data.get(field) != context.get(field):
            raise KronosConfirmationError(f"frozen data/target field drifted: {field}")

    phase_d = _load_json(root / benchmarks["authority"])
    findings = phase_d.get("candidate_findings", {})
    if benchmarks.get("zero_return_naive", {}).get("rmse") != findings.get("naive", {}).get("rmse"):
        raise KronosConfirmationError("zero-return benchmark drifted")
    if benchmarks.get("phase_d_full_v1_hist_gb", {}).get("rmse") != findings.get("hist_gb", {}).get("rmse"):
        raise KronosConfirmationError("Phase-D HistGB benchmark drifted")

    evaluation = freeze.get("evaluation", {})
    comparisons = evaluation.get("primary_comparisons", [])
    if len(comparisons) != 9 or len(set(comparisons)) != 9:
        raise KronosConfirmationError("the nine primary comparisons must stay fixed")
    multiple = evaluation.get("multiple_testing", {})
    if multiple.get("method") != "benjamini_hochberg" or multiple.get("members") != 9:
        raise KronosConfirmationError("confirmation multiplicity family drifted")

    artifacts = freeze.get("artifacts", {})
    namespaces = [artifacts.get(label) for label in MODEL_KEYS]
    if len(set(namespaces)) != 3 or any(not value for value in namespaces):
        raise KronosConfirmationError("checkpoint artifact namespaces must be distinct")
    historical = artifacts.get("historical_82_namespace_prohibited")
    if historical in namespaces:
        raise KronosConfirmationError("historical #82 artifacts cannot be reused")

    gate = freeze.get("release_gate", {})
    if gate.get("independent_audit_issue") != 183:
        raise KronosConfirmationError("independent audit binding drifted")
    if gate.get("audit_release_required") is not True:
        raise KronosConfirmationError("independent audit release must remain mandatory")
    return freeze


def require_independent_release(repo_root: Path, freeze: dict[str, Any]) -> dict[str, Any]:
    release_path = repo_root / AUDIT_RELEASE_PATH
    if not release_path.is_file():
        raise KronosConfirmationError("#180 is blocked until the #183 audit release exists")
    release = _load_json(release_path)
    if release.get("experiment_id") != freeze.get("experiment_id"):
        raise KronosConfirmationError("audit release experiment identity mismatch")
    if release.get("audit_issue") != 183:
        raise KronosConfirmationError("audit release issue mismatch")
    if release.get("state") != "independent_audit_passed":
        raise KronosConfirmationError("independent audit has not passed")
    if release.get("execution_authorized") is not True:
        raise KronosConfirmationError("#183 has not authorized #180 execution")
    expected_freeze = _normalized_sha256(repo_root / CONFIRMATION_CONFIG_PATH)
    if release.get("freeze_sha256") != expected_freeze:
        raise KronosConfirmationError("audit release does not bind this exact freeze")
    return release


def build_released_checkpoint_adapter(
    repo_root: Path, checkpoint: str
) -> tuple[KronosCheckpointAdapter, dict[str, Any]]:
    freeze = validate_confirmation_freeze(repo_root)
    require_independent_release(repo_root, freeze)
    if checkpoint not in MODEL_KEYS:
        raise KronosConfirmationError(f"unknown confirmation checkpoint: {checkpoint}")
    adapter = KronosCheckpointAdapter(
        MODEL_KEYS[checkpoint], freeze["common_execution"]["inference"]
    )
    return adapter, freeze


def governed_confirmation_prediction(
    *,
    repo_root: Path,
    checkpoint: str,
    canonical_market: pd.DataFrame,
    selected_market: pd.DataFrame,
    prediction_time: Any,
    target_timestamp: Any,
    target_contract_id: str,
) -> tuple[float, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Generate one released #180 prediction through the corrected governed boundary."""
    adapter, freeze = build_released_checkpoint_adapter(repo_root, checkpoint)
    forecast, context = governed_kronos_forecast(
        adapter=adapter,
        canonical_market=canonical_market,
        selected_market=selected_market,
        prediction_time=prediction_time,
        target_timestamp=target_timestamp,
        max_context=int(freeze["common_execution"]["max_context"]),
    )
    predicted_return = governed_return_prediction(
        predicted_close_next=forecast.iloc[0]["close"],
        observed_close_at_cutoff=context.iloc[-1]["close"],
        current_contract_id=str(context.iloc[-1]["contract_id"]),
        target_contract_id=target_contract_id,
    )
    evidence = {
        "checkpoint": checkpoint,
        "model_key": MODEL_KEYS[checkpoint],
        "artifact_manifest": adapter.artifact_manifest,
    }
    return predicted_return, forecast, context, evidence
