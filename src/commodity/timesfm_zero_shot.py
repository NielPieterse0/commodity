from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from commodity.config import assumptions_config, data_config, model_config
from commodity.dataset_freeze import load_frozen_dataset
from commodity.evaluation import evaluate_predictions
from commodity.evaluation_protocol import benjamini_hochberg_adjust
from commodity.market_data import (
    ensure_canonical_market_availability,
    validate_contract_history,
)
from commodity.models import baseline_factory
from commodity.phase_d_evaluation import (
    feature_family_columns,
    walk_forward_distribution_predict,
)
from commodity.rolls import build_derived_continuous_series
from commodity.volatility_diagnostic import EPSILON, _qlike

CONTRACT_PATH = Path("docs/development/timesfm-zero-shot-preregistration/contract.json")
FREEZE_PATH = Path("docs/development/timesfm-zero-shot-preregistration/freeze.json")
AUTHORITY_PATH = Path("docs/development/timesfm-zero-shot-execution/execution-authority.json")
PHASE_D_CONFIG_PATH = Path("config/phase_d_evaluation.json")
LANDED_FREEZE_REVISION = "56dcfeff0e65c6f61c8296f0f72928b616f6713f"
EXPECTED_CONTRACT_SHA256 = "a5d3fbc10158776f035f2ee3010fdf28a45c654dda44d38632775cee8e9d3325"
EXPECTED_SOURCE_REVISION = "3dae50b20d7a724981e8ea36cda75578f80dd2dc"
EXPECTED_MODEL_REVISION = "1d952420fba87f3c6dee4f240de0f1a0fbc790e3"
EXPECTED_WEIGHTS_SHA256 = "2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8"
EXPECTED_DATASET_SHA256 = "0c0a39b3669215b4bdc45a0fdedf90697f0c2c92690cb33700bd0bc47c80a45f"
EXPECTED_COVERAGE_SHA256 = "3621260e37817b4063527f485701f8d7fea45284547db4a8397691b400ffbd36"
EXPECTED_HISTGB_RMSE = 0.04650733779411404
EXPECTED_ZERO_RMSE = 0.0453230577562102
CONTEXTS = (128, 256, 512, 1024)
RETURN_REPRESENTATIONS = ("settlement_level", "log_settlement", "log_return")
VOLATILITY_REPRESENTATION = "garman_klass_variance"
QUANTILES = tuple(value / 10.0 for value in range(1, 10))


class TimesFMZeroShotError(RuntimeError):
    """Raised when the frozen #198/#224 experiment cannot execute exactly."""


@dataclass(frozen=True)
class ForecastCase:
    prediction_time: pd.Timestamp
    target_timestamp: pd.Timestamp
    trade_date: pd.Timestamp
    target_trade_date: pd.Timestamp
    contract_id: str
    current_settle: float
    actual_return: float
    actual_gk_variance: float
    history: pd.DataFrame


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TimesFMZeroShotError(f"JSON authority must be an object: {path}")
    return value


def _normalized_sha256(path: Path) -> str:
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_revision(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()


def _require_clean_execution_tree(repo_root: Path) -> str:
    head = _git_revision(repo_root)
    status = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=no"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        raise TimesFMZeroShotError("TimesFM inference requires a clean tracked execution tree")
    protected = subprocess.run(
        [
            "git", "-C", str(repo_root), "diff", "--name-only",
            f"{LANDED_FREEZE_REVISION}..HEAD", "--",
            "config/models.json", "config/experiment_candidates.json",
            str(CONTRACT_PATH).replace("\\", "/"), str(FREEZE_PATH).replace("\\", "/"),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if protected:
        raise TimesFMZeroShotError(f"protected frozen authority drifted: {protected}")
    return head


def validate_execution_authority(repo_root: Path, *, require_clean: bool = False) -> dict[str, Any]:
    contract_path = repo_root / CONTRACT_PATH
    freeze_path = repo_root / FREEZE_PATH
    authority_path = repo_root / AUTHORITY_PATH
    if _normalized_sha256(contract_path) != EXPECTED_CONTRACT_SHA256:
        raise TimesFMZeroShotError("frozen TimesFM contract hash drifted")
    contract = _json(contract_path)
    freeze = _json(freeze_path)
    authority = _json(authority_path)
    if contract.get("contract_id") != "timesfm-198-zero-shot-v1":
        raise TimesFMZeroShotError("unexpected TimesFM contract id")
    if freeze.get("contract_sha256") != EXPECTED_CONTRACT_SHA256:
        raise TimesFMZeroShotError("freeze does not bind the expected contract")
    if freeze.get("timesfm_results_inspected") is not False:
        raise TimesFMZeroShotError("freeze says TimesFM results were already inspected")
    if freeze.get("prediction_generation_authorized") is not False:
        raise TimesFMZeroShotError("parent freeze unexpectedly self-authorizes execution")
    if authority.get("execution_authorized") is not True:
        raise TimesFMZeroShotError("#224 execution authority is not enabled")
    if authority.get("hypothesis_family_changed") is not False:
        raise TimesFMZeroShotError("#224 may not change the frozen hypothesis family")
    if authority.get("frozen_contract_sha256") != EXPECTED_CONTRACT_SHA256:
        raise TimesFMZeroShotError("#224 authority binds the wrong frozen contract")
    model = contract["model"]
    if model["source_revision"] != EXPECTED_SOURCE_REVISION:
        raise TimesFMZeroShotError("TimesFM source revision drifted")
    if model["model_revision"] != EXPECTED_MODEL_REVISION:
        raise TimesFMZeroShotError("TimesFM model revision drifted")
    if model["checkpoint_artifacts"]["model"]["sha256"] != EXPECTED_WEIGHTS_SHA256:
        raise TimesFMZeroShotError("TimesFM checkpoint hash drifted")
    if require_clean:
        authority["execution_revision"] = _require_clean_execution_tree(repo_root)
    return {"contract": contract, "freeze": freeze, "authority": authority}


def _validate_canonical_snapshot(path: Path) -> str:
    manifest = _json(path.parent / "manifest.json")
    matches = [item for item in manifest.get("artifacts", []) if item.get("path") == path.name]
    if len(matches) != 1:
        raise TimesFMZeroShotError("canonical market snapshot is not uniquely manifested")
    observed = _file_sha256(path)
    if observed != matches[0].get("sha256"):
        raise TimesFMZeroShotError("canonical market snapshot hash mismatch")
    return observed


def _market_inputs(canonical_market_csv: Path) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    snapshot_sha = _validate_canonical_snapshot(canonical_market_csv)
    raw = pd.read_csv(canonical_market_csv)
    cfg = data_config()
    assumptions = assumptions_config()
    schema = cfg["canonical_contract_schema"]
    source = cfg["sources"]["market_canonical"]
    policy = assumptions["assumptions"]["continuous_series_policy"]["policy"]
    available = ensure_canonical_market_availability(raw, source["availability_policy"])
    canonical = validate_contract_history(available, schema)
    selected, _ = build_derived_continuous_series(canonical, schema, policy)
    for frame in (canonical, selected):
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True)
        frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True)
    return canonical, selected, snapshot_sha


def _require_frozen_dataset(repo_root: Path, dataset_dir: Path, contract: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    frame, manifest = load_frozen_dataset(dataset_dir)
    data = contract["experiment"]["data_identity"]
    if manifest.get("dataset_sha256") != EXPECTED_DATASET_SHA256 or data["dataset_sha256"] != EXPECTED_DATASET_SHA256:
        raise TimesFMZeroShotError("frozen dataset identity drifted")
    activation = _json(repo_root / data["inherits_activation_contract"])
    identity = activation["frozen_v1_control"]["context_identity"]
    if identity.get("coverage_signature_sha256") != EXPECTED_COVERAGE_SHA256:
        raise TimesFMZeroShotError("frozen coverage signature drifted")
    oos_rows = int(data["oos_rows"])
    oos = frame.iloc[-oos_rows:].copy()
    if len(oos) != 204:
        raise TimesFMZeroShotError("frozen OOS row count drifted")
    if oos.index[0] != pd.Timestamp(data["oos_start"]) or oos.index[-1] != pd.Timestamp(data["oos_end"]):
        raise TimesFMZeroShotError("frozen OOS boundary drifted")
    target = data["forecast_target"]
    if not np.isfinite(oos[target].to_numpy(dtype=float)).all():
        raise TimesFMZeroShotError("frozen OOS target contains non-finite values")
    return frame, manifest, oos


def _garman_klass(frame: pd.DataFrame) -> np.ndarray:
    values = frame[["open", "high", "low", "close"]].astype(float).to_numpy()
    if not np.isfinite(values).all() or np.any(values <= 0.0):
        raise TimesFMZeroShotError("Garman-Klass requires finite positive OHLC")
    open_, high, low, close = (values[:, index] for index in range(4))
    result = 0.5 * np.log(high / low) ** 2 - (2.0 * math.log(2.0) - 1.0) * np.log(close / open_) ** 2
    if not np.isfinite(result).all():
        raise TimesFMZeroShotError("Garman-Klass produced non-finite values")
    return np.maximum(result, 0.0)


def _build_case(canonical: pd.DataFrame, selected: pd.DataFrame, prediction_time: pd.Timestamp, *, minimum_rows: int = 20) -> ForecastCase:
    cutoff = pd.Timestamp(prediction_time)
    chosen = selected.loc[selected["available_at"] == cutoff]
    if len(chosen) != 1:
        raise TimesFMZeroShotError(f"selected-path cutoff row is not unique: {cutoff.isoformat()}")
    current = chosen.iloc[0]
    trade_date = pd.Timestamp(current["trade_date"])
    future_sessions = selected.loc[selected["trade_date"] > trade_date].sort_values("trade_date")
    if future_sessions.empty:
        raise TimesFMZeroShotError("next selected-path trading session is unavailable")
    target_trade_date = pd.Timestamp(future_sessions.iloc[0]["trade_date"])
    contract_id = str(current["contract_id"])
    history = canonical.loc[
        canonical["contract_id"].astype(str).eq(contract_id)
        & (canonical["available_at"] <= cutoff)
        & (canonical["trade_date"] <= trade_date)
    ].sort_values("trade_date").copy()
    if len(history) < minimum_rows:
        raise TimesFMZeroShotError(f"same-contract history below frozen minimum: {contract_id} {cutoff.isoformat()}")
    if not history["trade_date"].is_unique:
        raise TimesFMZeroShotError("same-contract history has duplicate trade dates")
    target = canonical.loc[
        canonical["contract_id"].astype(str).eq(contract_id)
        & canonical["trade_date"].eq(target_trade_date)
    ]
    if len(target) != 1:
        raise TimesFMZeroShotError(f"same-contract target is missing or ambiguous: {contract_id} {target_trade_date.isoformat()}")
    target_row = target.iloc[0]
    target_timestamp = pd.Timestamp(target_row["available_at"])
    if target_timestamp <= cutoff:
        raise TimesFMZeroShotError("same-contract target is available at or before prediction time")
    current_settle = float(history.iloc[-1]["settle"])
    target_settle = float(target_row["settle"])
    if not math.isfinite(current_settle) or not math.isfinite(target_settle) or current_settle <= 0.0 or target_settle <= 0.0:
        raise TimesFMZeroShotError("same-contract settlement target is invalid")
    target_gk = float(_garman_klass(target.iloc[[0]])[0])
    return ForecastCase(
        prediction_time=cutoff,
        target_timestamp=target_timestamp,
        trade_date=trade_date,
        target_trade_date=target_trade_date,
        contract_id=contract_id,
        current_settle=current_settle,
        actual_return=float(math.log(target_settle / current_settle)),
        actual_gk_variance=target_gk,
        history=history,
    )


def representation_values(case: ForecastCase, representation: str, context: int) -> np.ndarray:
    if context not in CONTEXTS:
        raise TimesFMZeroShotError(f"context is not frozen: {context}")
    history = case.history
    if representation == "settlement_level":
        values = history["settle"].to_numpy(dtype=float)
    elif representation == "log_settlement":
        settle = history["settle"].to_numpy(dtype=float)
        if np.any(settle <= 0.0):
            raise TimesFMZeroShotError("log settlement history contains non-positive values")
        values = np.log(settle)
    elif representation == "log_return":
        settle = history["settle"].to_numpy(dtype=float)
        if np.any(settle <= 0.0):
            raise TimesFMZeroShotError("return history contains non-positive settlement")
        values = np.diff(np.log(settle))
    elif representation == VOLATILITY_REPRESENTATION:
        values = _garman_klass(history)
    else:
        raise TimesFMZeroShotError(f"unknown representation: {representation}")
    values = np.asarray(values[-context:], dtype=np.float64)
    if len(values) == 0 or not np.isfinite(values).all():
        raise TimesFMZeroShotError("TimesFM representation is empty or non-finite")
    return values


def empirical_return_quantiles(case: ForecastCase, context: int) -> np.ndarray:
    settle = case.history["settle"].to_numpy(dtype=float)
    values = np.diff(np.log(settle))[-context:]
    if len(values) == 0 or not np.isfinite(values).all():
        raise TimesFMZeroShotError("empirical return baseline is unavailable")
    return np.quantile(values, QUANTILES, method="linear").astype(float)


def _reconstruct_histgb(repo_root: Path, frame: pd.DataFrame, manifest: dict[str, Any]) -> pd.DataFrame:
    phase_cfg = _json(repo_root / PHASE_D_CONFIG_PATH)
    models = model_config()["models"]
    target = str(manifest.get("target", "target_ret_1"))
    mapping = feature_family_columns(frame, manifest, target=target)
    columns = [column for family in mapping.values() for column in family]
    walk = phase_cfg["walk_forward"]
    prediction = walk_forward_distribution_predict(
        baseline_factory("hist_gb", models),
        frame[columns].astype(float),
        frame[target].astype(float),
        initial_train=int(walk["initial_train_rows"]),
        retrain_every=int(walk["retrain_every_rows"]),
        volatility_window=int(walk["volatility_window_rows"]),
    )[["prediction", "actual"]].copy()
    observed = float(evaluate_predictions(prediction)["rmse"])
    if not math.isclose(observed, EXPECTED_HISTGB_RMSE, rel_tol=0.0, abs_tol=1e-15):
        raise TimesFMZeroShotError(f"Phase-D HistGB reconstruction drifted: {observed}")
    return prediction


def prepare_inputs(repo_root: Path, dataset_dir: Path, canonical_market_csv: Path) -> dict[str, Any]:
    authority = validate_execution_authority(repo_root)
    contract = authority["contract"]
    frame, manifest, oos = _require_frozen_dataset(repo_root, dataset_dir, contract)
    canonical, selected, market_sha = _market_inputs(canonical_market_csv)
    cases = [_build_case(canonical, selected, pd.Timestamp(timestamp)) for timestamp in oos.index]
    actual = np.asarray([case.actual_return for case in cases])
    frozen_target = oos[contract["experiment"]["data_identity"]["forecast_target"]].to_numpy(dtype=float)
    if not np.allclose(actual, frozen_target, rtol=0.0, atol=2e-15):
        raise TimesFMZeroShotError("same-contract target reconstruction differs from frozen target")
    histgb = _reconstruct_histgb(repo_root, frame, manifest)
    histgb = histgb.reindex(oos.index)
    if histgb.isna().any().any():
        raise TimesFMZeroShotError("HistGB baseline does not cover every frozen OOS row")
    zero_rmse = float(np.sqrt(np.mean(actual**2)))
    if not math.isclose(zero_rmse, EXPECTED_ZERO_RMSE, rel_tol=0.0, abs_tol=1e-15):
        raise TimesFMZeroShotError(f"zero-return RMSE drifted: {zero_rmse}")
    return {
        **authority,
        "frame": frame,
        "manifest": manifest,
        "oos": oos,
        "canonical": canonical,
        "selected": selected,
        "cases": cases,
        "histgb": histgb,
        "canonical_market_sha256": market_sha,
    }


def verify_model_assets(source_dir: Path, checkpoint_dir: Path) -> dict[str, str]:
    if _git_revision(source_dir) != EXPECTED_SOURCE_REVISION:
        raise TimesFMZeroShotError("TimesFM source checkout is not at the frozen revision")
    weights = checkpoint_dir / "model.safetensors"
    if not weights.is_file():
        raise TimesFMZeroShotError("TimesFM model.safetensors is missing")
    observed = _file_sha256(weights)
    if observed != EXPECTED_WEIGHTS_SHA256:
        raise TimesFMZeroShotError("TimesFM model.safetensors hash mismatch")
    return {"source_revision": EXPECTED_SOURCE_REVISION, "checkpoint_sha256": observed}


def _load_model(source_dir: Path, checkpoint_dir: Path) -> tuple[Any, Any]:
    verify_model_assets(source_dir, checkpoint_dir)
    source_python = str((source_dir / "src").resolve())
    if source_python not in sys.path:
        sys.path.insert(0, source_python)
    import timesfm
    from timesfm.timesfm_2p5.timesfm_2p5_torch import TimesFM_2p5_200M_torch

    model = TimesFM_2p5_200M_torch.from_pretrained(
        str(checkpoint_dir), local_files_only=True, torch_compile=False
    )
    return timesfm, model


def _compile_model(timesfm: Any, model: Any, *, infer_is_positive: bool) -> None:
    model.compile(
        timesfm.ForecastConfig(
            max_context=1024,
            max_horizon=1,
            normalize_inputs=True,
            use_continuous_quantile_head=True,
            force_flip_invariance=True,
            infer_is_positive=infer_is_positive,
            fix_quantile_crossing=True,
        )
    )


def _forecast_quantiles(model: Any, inputs: list[np.ndarray]) -> np.ndarray:
    _, quantile_forecast = model.forecast(horizon=1, inputs=inputs)
    values = np.asarray(quantile_forecast, dtype=float)
    if values.shape != (len(inputs), 1, 10):
        raise TimesFMZeroShotError(f"unexpected TimesFM quantile output shape: {values.shape}")
    quantiles = values[:, 0, 1:10]
    if not np.isfinite(quantiles).all():
        raise TimesFMZeroShotError("TimesFM emitted non-finite quantiles")
    return quantiles


def _to_return_quantiles(cases: list[ForecastCase], representation: str, forecast: np.ndarray) -> np.ndarray:
    result = np.asarray(forecast, dtype=float).copy()
    if representation == "settlement_level":
        current = np.asarray([case.current_settle for case in cases], dtype=float)[:, None]
        if np.any(result <= 0.0):
            raise TimesFMZeroShotError("settlement-level forecast contains non-positive values")
        result = np.log(result / current)
    elif representation == "log_settlement":
        current_log = np.log(np.asarray([case.current_settle for case in cases], dtype=float))[:, None]
        result = result - current_log
    elif representation != "log_return":
        raise TimesFMZeroShotError("return conversion requested for non-return representation")
    return result


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        frame.to_csv(handle, index=False, lineterminator="\n", float_format="%.17g")
    temp.replace(path)


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    temp.replace(path)


def generate_predictions(prepared: dict[str, Any], source_dir: Path, checkpoint_dir: Path, output_dir: Path) -> dict[str, Any]:
    execution_revision = _require_clean_execution_tree(Path(prepared["repo_root"])) if "repo_root" in prepared else None
    timesfm, model = _load_model(source_dir, checkpoint_dir)
    cases: list[ForecastCase] = prepared["cases"]
    rows: list[dict[str, Any]] = []
    for representation in (*RETURN_REPRESENTATIONS, VOLATILITY_REPRESENTATION):
        positive = bool(prepared["contract"]["experiment"]["representations"][representation]["positive"])
        _compile_model(timesfm, model, infer_is_positive=positive)
        for context in CONTEXTS:
            inputs = [representation_values(case, representation, context) for case in cases]
            forecast = _forecast_quantiles(model, inputs)
            scored = forecast if representation == VOLATILITY_REPRESENTATION else _to_return_quantiles(cases, representation, forecast)
            for case, values, input_values in zip(cases, scored, inputs, strict=True):
                row = {
                    "prediction_time": case.prediction_time.isoformat(),
                    "target_timestamp": case.target_timestamp.isoformat(),
                    "contract_id": case.contract_id,
                    "representation": representation,
                    "context": context,
                    "realized_context_length": len(input_values),
                    "actual": case.actual_gk_variance if representation == VOLATILITY_REPRESENTATION else case.actual_return,
                    "point": float(values[4]),
                }
                row.update({f"q{int(q * 100):02d}": float(value) for q, value in zip(QUANTILES, values, strict=True)})
                rows.append(row)
    predictions = pd.DataFrame(rows)
    expected = 204 * 4 * 4
    if len(predictions) != expected:
        raise TimesFMZeroShotError(f"prediction coverage is incomplete: {len(predictions)} != {expected}")
    predictions_path = output_dir / "predictions.csv"
    _atomic_csv(predictions_path, predictions)
    manifest = {
        "schema_version": 1,
        "execution_id": "timesfm-224-zero-shot-execution-v1",
        "execution_revision": execution_revision,
        "rows": len(predictions),
        "scored_oos_rows": 204,
        "contexts": list(CONTEXTS),
        "representations": [*RETURN_REPRESENTATIONS, VOLATILITY_REPRESENTATION],
        "predictions_sha256": _file_sha256(predictions_path),
        "source_revision": EXPECTED_SOURCE_REVISION,
        "model_revision": EXPECTED_MODEL_REVISION,
        "checkpoint_sha256": EXPECTED_WEIGHTS_SHA256,
        "dataset_sha256": EXPECTED_DATASET_SHA256,
        "coverage_signature_sha256": EXPECTED_COVERAGE_SHA256,
        "canonical_market_sha256": prepared["canonical_market_sha256"],
    }
    _atomic_json(output_dir / "prediction-manifest.json", manifest)
    return manifest


def _moving_block_indices(n: int, block_size: int, resamples: int, seed: int) -> Iterable[np.ndarray]:
    if block_size < 1 or block_size > n:
        raise TimesFMZeroShotError("invalid moving-block size")
    rng = np.random.default_rng(seed)
    starts_max = n - block_size
    blocks = math.ceil(n / block_size)
    for _ in range(resamples):
        starts = rng.integers(0, starts_max + 1, size=blocks)
        yield np.concatenate([np.arange(start, start + block_size) for start in starts])[:n]


def _rmse_improvement(actual: np.ndarray, challenger: np.ndarray, baseline: np.ndarray, *, block_size: int = 20, resamples: int = 1000, seed: int = 0) -> dict[str, float | int | str]:
    actual = np.asarray(actual, dtype=float)
    challenger = np.asarray(challenger, dtype=float)
    baseline = np.asarray(baseline, dtype=float)
    observed = float(np.sqrt(np.mean((baseline - actual) ** 2)) - np.sqrt(np.mean((challenger - actual) ** 2)))
    draws = np.empty(resamples, dtype=float)
    for index, sampled in enumerate(_moving_block_indices(len(actual), block_size, resamples, seed)):
        draws[index] = float(
            np.sqrt(np.mean((baseline[sampled] - actual[sampled]) ** 2))
            - np.sqrt(np.mean((challenger[sampled] - actual[sampled]) ** 2))
        )
    centered = draws - observed
    p_value = float((1 + np.count_nonzero(centered <= -observed)) / (resamples + 1))
    lower, upper = np.quantile(draws, [0.025, 0.975])
    return {
        "method": "moving_block_bootstrap_rmse_improvement",
        "rmse_improvement": observed,
        "ci_lower": float(lower),
        "ci_upper": float(upper),
        "p_value_one_sided_improvement": p_value,
        "block_size": block_size,
        "resamples": resamples,
    }


def _mean_loss_improvement(baseline_loss: np.ndarray, challenger_loss: np.ndarray, *, block_size: int = 20, resamples: int = 1000, seed: int = 0) -> dict[str, float | int | str]:
    delta = np.asarray(baseline_loss, dtype=float) - np.asarray(challenger_loss, dtype=float)
    observed = float(delta.mean())
    draws = np.asarray([float(delta[index].mean()) for index in _moving_block_indices(len(delta), block_size, resamples, seed)])
    centered = draws - observed
    p_value = float((1 + np.count_nonzero(centered <= -observed)) / (resamples + 1))
    lower, upper = np.quantile(draws, [0.025, 0.975])
    return {
        "method": "moving_block_bootstrap_mean_loss_improvement",
        "mean_loss_improvement": observed,
        "ci_lower": float(lower),
        "ci_upper": float(upper),
        "p_value_one_sided_improvement": p_value,
        "block_size": block_size,
        "resamples": resamples,
    }


def _dm_squared_error(actual: np.ndarray, challenger: np.ndarray, baseline: np.ndarray) -> dict[str, float | str]:
    differential = (baseline - actual) ** 2 - (challenger - actual) ** 2
    mean = float(np.mean(differential))
    variance = float(np.var(differential, ddof=1))
    if not math.isfinite(variance) or variance <= 0.0:
        return {"method": "diebold_mariano_h1_hac0", "statistic": 0.0, "p_value_two_sided": 1.0}
    statistic = mean / math.sqrt(variance / len(differential))
    p_value = math.erfc(abs(statistic) / math.sqrt(2.0))
    return {"method": "diebold_mariano_h1_hac0", "statistic": float(statistic), "p_value_two_sided": float(p_value)}


def _pinball(actual: np.ndarray, quantiles: np.ndarray) -> np.ndarray:
    actual = np.asarray(actual, dtype=float)[:, None]
    quantiles = np.asarray(quantiles, dtype=float)
    errors = actual - quantiles
    q = np.asarray(QUANTILES, dtype=float)[None, :]
    return np.maximum(q * errors, (q - 1.0) * errors)


def _return_metrics(actual: np.ndarray, point: np.ndarray, zero_mae: float) -> dict[str, float]:
    errors = point - actual
    corr = 0.0 if np.std(point) == 0.0 else float(np.corrcoef(point, actual)[0, 1])
    mae = float(np.mean(np.abs(errors)))
    return {
        "n": float(len(actual)),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "mae": mae,
        "mase": float(mae / zero_mae),
        "direction_accuracy": float(np.mean(np.sign(point) == np.sign(actual))),
        "prediction_actual_correlation": corr,
    }


def evaluate_results(prepared: dict[str, Any], predictions_path: Path, output_dir: Path) -> dict[str, Any]:
    predictions = pd.read_csv(predictions_path)
    cases: list[ForecastCase] = prepared["cases"]
    actual = np.asarray([case.actual_return for case in cases], dtype=float)
    histgb = prepared["histgb"]["prediction"].to_numpy(dtype=float)
    zero = np.zeros(len(actual), dtype=float)
    zero_mae = float(np.mean(np.abs(actual)))
    primary: list[dict[str, Any]] = []
    distribution: list[dict[str, Any]] = []
    blends: list[dict[str, Any]] = []
    variant_metrics: dict[str, Any] = {}
    for representation in RETURN_REPRESENTATIONS:
        for context in CONTEXTS:
            subset = predictions.loc[(predictions["representation"] == representation) & (predictions["context"] == context)]
            if len(subset) != 204:
                raise TimesFMZeroShotError("return variant coverage is not 204 rows")
            point = subset["point"].to_numpy(dtype=float)
            quantile_values = subset[[f"q{int(q * 100):02d}" for q in QUANTILES]].to_numpy(dtype=float)
            key = f"{representation}:{context}"
            variant_metrics[key] = _return_metrics(actual, point, zero_mae)
            for baseline_name, baseline in (("zero_return_naive", zero), ("phase_d_full_v1_hist_gb", histgb)):
                inference = _rmse_improvement(actual, point, baseline)
                primary.append({
                    "representation": representation,
                    "context": context,
                    "baseline": baseline_name,
                    "rmse_improvement": inference["rmse_improvement"],
                    "p_value": inference["p_value_one_sided_improvement"],
                    "bootstrap": inference,
                    "diebold_mariano": _dm_squared_error(actual, point, baseline),
                })
            empirical = np.vstack([empirical_return_quantiles(case, context) for case in cases])
            model_loss = _pinball(actual, quantile_values).mean(axis=1)
            baseline_loss = _pinball(actual, empirical).mean(axis=1)
            distribution_inference = _mean_loss_improvement(baseline_loss, model_loss)
            coverage80 = float(np.mean((actual >= quantile_values[:, 0]) & (actual <= quantile_values[:, 8])))
            coverage60 = float(np.mean((actual >= quantile_values[:, 1]) & (actual <= quantile_values[:, 7])))
            distribution.append({
                "representation": representation,
                "context": context,
                "mean_pinball_loss": float(model_loss.mean()),
                "baseline_mean_pinball_loss": float(baseline_loss.mean()),
                "pinball_improvement": distribution_inference["mean_loss_improvement"],
                "p_value": distribution_inference["p_value_one_sided_improvement"],
                "coverage_80": coverage80,
                "coverage_60": coverage60,
                "coverage_80_error": abs(coverage80 - 0.8),
                "coverage_60_error": abs(coverage60 - 0.6),
                "bootstrap": distribution_inference,
            })
            blend = 0.5 * point + 0.5 * histgb
            blend_inference = _rmse_improvement(actual, blend, histgb)
            blends.append({
                "representation": representation,
                "context": context,
                "rmse": float(np.sqrt(np.mean((blend - actual) ** 2))),
                "rmse_improvement": blend_inference["rmse_improvement"],
                "p_value": blend_inference["p_value_one_sided_improvement"],
                "bootstrap": blend_inference,
                "diebold_mariano": _dm_squared_error(actual, blend, histgb),
            })
    primary_adjusted = benjamini_hochberg_adjust([item["p_value"] for item in primary])
    for item, adjusted in zip(primary, primary_adjusted, strict=True):
        item["adjusted_p_value"] = adjusted
    distribution_adjusted = benjamini_hochberg_adjust([item["p_value"] for item in distribution])
    for item, adjusted in zip(distribution, distribution_adjusted, strict=True):
        item["adjusted_p_value"] = adjusted
    blend_adjusted = benjamini_hochberg_adjust([item["p_value"] for item in blends])
    for item, adjusted in zip(blends, blend_adjusted, strict=True):
        item["adjusted_p_value"] = adjusted

    volatility: dict[str, Any] = {}
    actual_gk = np.asarray([case.actual_gk_variance for case in cases], dtype=float)
    for context in CONTEXTS:
        subset = predictions.loc[(predictions["representation"] == VOLATILITY_REPRESENTATION) & (predictions["context"] == context)]
        point = np.maximum(subset["point"].to_numpy(dtype=float), EPSILON)
        baseline = np.asarray([float(np.mean(_garman_klass(case.history)[-20:])) for case in cases])
        mae = float(np.mean(np.abs(point - actual_gk)))
        baseline_mae = float(np.mean(np.abs(baseline - actual_gk)))
        volatility[str(context)] = {
            "rmse": float(np.sqrt(np.mean((point - actual_gk) ** 2))),
            "mae": mae,
            "mase": float(mae / baseline_mae),
            "qlike": float(np.mean(_qlike(actual_gk, point))),
            "baseline_rmse": float(np.sqrt(np.mean((baseline - actual_gk) ** 2))),
            "baseline_mae": baseline_mae,
            "baseline_qlike": float(np.mean(_qlike(actual_gk, baseline))),
        }

    alpha = 0.05
    standalone_keep = any(
        left["representation"] == right["representation"]
        and left["context"] == right["context"]
        and left["baseline"] == "zero_return_naive"
        and right["baseline"] == "phase_d_full_v1_hist_gb"
        and left["rmse_improvement"] > 0.0 and right["rmse_improvement"] > 0.0
        and left["adjusted_p_value"] <= alpha and right["adjusted_p_value"] <= alpha
        for left in primary for right in primary
    )
    distribution_keep = any(
        item["pinball_improvement"] > 0.0
        and item["adjusted_p_value"] <= alpha
        and item["coverage_80_error"] <= 0.05
        and item["coverage_60_error"] <= 0.05
        for item in distribution
    )
    complementarity_keep = any(item["rmse_improvement"] > 0.0 and item["adjusted_p_value"] <= alpha for item in blends)
    result = {
        "schema_version": 1,
        "execution_id": "timesfm-224-zero-shot-execution-v1",
        "rows": 204,
        "variant_metrics": variant_metrics,
        "primary_family": primary,
        "distribution_family": distribution,
        "complementarity_family": blends,
        "volatility": volatility,
        "benchmarks": {
            "zero_return_rmse": EXPECTED_ZERO_RMSE,
            "phase_d_histgb_rmse": EXPECTED_HISTGB_RMSE,
        },
        "decision": {
            "standalone_point_keep": standalone_keep,
            "distribution_keep": distribution_keep,
            "complementarity_keep": complementarity_keep,
            "return_programme_keep": bool(standalone_keep or distribution_keep or complementarity_keep),
            "volatility_can_rescue": False,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(output_dir / "result.json", result)
    return result


def run_experiment(*, repo_root: Path, dataset_dir: Path, canonical_market_csv: Path, source_dir: Path, checkpoint_dir: Path, output_dir: Path) -> dict[str, Any]:
    execution_revision = _require_clean_execution_tree(repo_root)
    prepared = prepare_inputs(repo_root, dataset_dir, canonical_market_csv)
    prepared["repo_root"] = str(repo_root)
    assets = verify_model_assets(source_dir, checkpoint_dir)
    manifest = generate_predictions(prepared, source_dir, checkpoint_dir, output_dir)
    result = evaluate_results(prepared, output_dir / "predictions.csv", output_dir)
    run_manifest = {
        "schema_version": 1,
        "execution_revision": execution_revision,
        "source_revision": assets["source_revision"],
        "checkpoint_sha256": assets["checkpoint_sha256"],
        "predictions_sha256": manifest["predictions_sha256"],
        "result_sha256": _file_sha256(output_dir / "result.json"),
    }
    _atomic_json(output_dir / "run-manifest.json", run_manifest)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute frozen TimesFM 2.5 zero-shot experiment")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--canonical-market-csv", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    prepared = prepare_inputs(args.repo_root, args.dataset_dir, args.canonical_market_csv)
    assets = verify_model_assets(args.source_dir, args.checkpoint_dir)
    if args.preflight_only:
        print(json.dumps({"rows": len(prepared["cases"]), **assets}, indent=2, sort_keys=True))
        return
    result = run_experiment(
        repo_root=args.repo_root,
        dataset_dir=args.dataset_dir,
        canonical_market_csv=args.canonical_market_csv,
        source_dir=args.source_dir,
        checkpoint_dir=args.checkpoint_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
