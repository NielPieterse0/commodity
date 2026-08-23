from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from commodity.config import assumptions_config, data_config
from commodity.dataset_freeze import load_frozen_dataset
from commodity.market_data import (
    ensure_canonical_market_availability,
    validate_contract_history,
)
from commodity.rolls import build_derived_continuous_series

EXPERIMENT_ID = "volatility-195-gk-har-v1"
EPSILON = 1e-12
EXPECTED_RELEASE_SHA256 = (
    "8ad51c693ed1406799d4e116815b0872ee6f40cb719c57fe196c327404ca16cd"
)
EXPECTED_DATASET_SHA256 = (
    "0c0a39b3669215b4bdc45a0fdedf90697f0c2c92690cb33700bd0bc47c80a45f"
)
EXPECTED_CANONICAL_MARKET_SHA256 = (
    "83faf07a8de1fe3fea4cd6548dd25d9c02828e1ef4faa13a234ac8f2ad03d655"
)
EXPECTED_DATA_SOURCES_SHA256 = (
    "63464479a32baf1e72980d19cd084c37007a3270b0b577a3b88dda175cbb3ba5"
)
EXPECTED_ASSUMPTIONS_SHA256 = (
    "331e0f4ffed84a4e94b29623835b59e763e3be9b2db2cc2417142b3f54b760fc"
)
EXPECTED_LEDGER_SHA256 = (
    "aa74a995571c9d668b0a869eb83076ce728a27535913a44a8fd22e4fe16f32a0"
)


class VolatilityDiagnosticError(RuntimeError):
    """Raised when the frozen #195 diagnostic cannot execute exactly."""


def _normalized_sha256(path: Path) -> str:
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VolatilityDiagnosticError(f"JSON authority must be an object: {path}")
    return value


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temp.replace(path)


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        frame.to_csv(handle, index=False, lineterminator="\n", float_format="%.17g")
    temp.replace(path)


def _git_head(repo_root: Path) -> str:
    return (
        subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
        .lower()
    )


def _require_clean_tracked_tree(repo_root: Path) -> str:
    head = _git_head(repo_root)
    status = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=no"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        raise VolatilityDiagnosticError(
            "#195 execution requires a clean tracked execution tree"
        )
    return head


def _require_hash(path: Path, expected: str, label: str) -> None:
    observed = _normalized_sha256(path)
    if observed != expected:
        raise VolatilityDiagnosticError(
            f"{label} hash drifted: expected {expected}, observed {observed}"
        )


def validate_release_authority(
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    release_path = (
        repo_root
        / "docs/development/volatility-preregistration-release-audit/audit-release.json"
    )
    _require_hash(release_path, EXPECTED_RELEASE_SHA256, "#193 audit release")
    _require_hash(
        repo_root / "config/data_sources.json",
        EXPECTED_DATA_SOURCES_SHA256,
        "data-source authority",
    )
    _require_hash(
        repo_root / "config/assumptions.json",
        EXPECTED_ASSUMPTIONS_SHA256,
        "roll assumption authority",
    )
    _require_hash(
        repo_root / "artifacts/research-metrics/longitudinal-ledger.json",
        EXPECTED_LEDGER_SHA256,
        "Phase-D row ledger",
    )
    release = _load_json(release_path)

    if (
        release.get("release_id")
        != "volatility-preregistration-191-diagnostic-release-v1"
    ):
        raise VolatilityDiagnosticError("#193 release identity changed")
    if release.get("decision") != "pass_diagnostic_only":
        raise VolatilityDiagnosticError("#193 does not release the diagnostic")
    authority = release.get("authority", {})
    if (
        authority.get("diagnostic_execution_authorized") is not True
        or authority.get("confirmation_execution_authorized") is not False
        or authority.get("research_promotion_authorized") is not False
        or authority.get("trading_authority") is not False
        or authority.get("model_or_feature_search_authorized") is not False
    ):
        raise VolatilityDiagnosticError("#193 authority boundary drifted")

    identities = release.get("identities", {})
    identity_paths = {
        "contract_sha256": "docs/development/volatility-preregistration/contract.json",
        "preregistration_sha256": "docs/development/volatility-preregistration/preregistration.md",
        "roll_safe_market_sha256": "src/commodity/roll_safe_market.py",
        "rolls_sha256": "src/commodity/rolls.py",
    }
    for key, relative in identity_paths.items():
        expected = identities.get(key)
        if not isinstance(expected, str):
            raise VolatilityDiagnosticError(f"#193 release is missing {key}")
        _require_hash(repo_root / relative, expected, relative)

    contract = _load_json(repo_root / identity_paths["contract_sha256"])
    diagnostic = contract.get("diagnostic", {})
    confirmation = contract.get("confirmation", {})
    if (
        diagnostic.get("candidate_rows") != 456
        or diagnostic.get("initial_train_rows") != 252
    ):
        raise VolatilityDiagnosticError("#191 diagnostic row counts drifted")
    if (
        diagnostic.get("scored_rows") != 204
        or diagnostic.get("promotion_authority") is not False
    ):
        raise VolatilityDiagnosticError("#191 diagnostic authority drifted")

    if diagnostic.get("oos_start") != "2025-10-03T23:59:00+00:00":
        raise VolatilityDiagnosticError("#191 diagnostic OOS start drifted")
    if diagnostic.get("oos_end") != "2026-08-11T23:59:00+00:00":
        raise VolatilityDiagnosticError("#191 diagnostic OOS end drifted")
    if (
        confirmation.get("scored_rows") != 504
        or confirmation.get("current_status") != "locked"
    ):
        raise VolatilityDiagnosticError("#191 confirmation lock drifted")
    if (
        confirmation.get("boundary")
        != "prediction_time_strictly_after_2026-08-11T23:59:00+00:00"
    ):
        raise VolatilityDiagnosticError("#191 confirmation boundary drifted")
    if (
        contract.get("authority", {}).get(
            "issue_51_must_remain_untouched_without_operator_request"
        )
        is not True
    ):
        raise VolatilityDiagnosticError("#51 operator-deferred boundary drifted")
    return contract, release


def _validate_dataset(
    dataset_dir: Path, contract: dict[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame, manifest = load_frozen_dataset(dataset_dir)
    if manifest.get("dataset_sha256") != EXPECTED_DATASET_SHA256:
        raise VolatilityDiagnosticError("frozen Phase-D dataset identity drifted")
    if _file_sha256(dataset_dir / "dataset.csv") != EXPECTED_DATASET_SHA256:
        raise VolatilityDiagnosticError("frozen Phase-D dataset bytes drifted")
    if len(frame) != int(contract["diagnostic"]["candidate_rows"]):
        raise VolatilityDiagnosticError("frozen diagnostic candidate-row count drifted")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise VolatilityDiagnosticError("frozen diagnostic row index is invalid")
    initial = int(contract["diagnostic"]["initial_train_rows"])
    oos = frame.iloc[initial:]
    if len(oos) != int(contract["diagnostic"]["scored_rows"]):
        raise VolatilityDiagnosticError("frozen diagnostic scored-row count drifted")
    if oos.index[0] != pd.Timestamp(contract["diagnostic"]["oos_start"]):
        raise VolatilityDiagnosticError(
            "frozen diagnostic OOS start does not match #191"
        )
    if oos.index[-1] != pd.Timestamp(contract["diagnostic"]["oos_end"]):
        raise VolatilityDiagnosticError("frozen diagnostic OOS end does not match #191")
    return frame, manifest


def _garman_klass_variance(row: pd.Series) -> float:
    values = np.asarray(
        [row["open"], row["high"], row["low"], row["close"]], dtype=float
    )
    if not np.isfinite(values).all() or (values <= 0).any():
        raise VolatilityDiagnosticError(
            "target/history OHLC must be finite and positive"
        )
    open_, high, low, close = values
    if high < max(open_, close, low) or low > min(open_, close, high):
        raise VolatilityDiagnosticError("target/history OHLC ordering is invalid")
    value = (
        0.5 * math.log(high / low) ** 2
        - (2.0 * math.log(2.0) - 1.0) * math.log(close / open_) ** 2
    )
    if not math.isfinite(value) or value < -1e-15:
        raise VolatilityDiagnosticError("Garman-Klass variance is invalid")
    return max(float(value), 0.0)


def _require_committed_evaluator(repo_root: Path) -> str:
    relative = Path("src/commodity/volatility_diagnostic.py")
    head = _require_clean_tracked_tree(repo_root)
    tracked = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "ls-files",
            "--error-unmatch",
            relative.as_posix(),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise VolatilityDiagnosticError(
            "#195 evaluator must be committed before execution"
        )
    committed = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"HEAD:{relative.as_posix()}"],
        check=True,
        capture_output=True,
    ).stdout
    if hashlib.sha256(committed).hexdigest() != _file_sha256(repo_root / relative):
        raise VolatilityDiagnosticError(
            "#195 evaluator bytes differ from committed HEAD"
        )
    return head


def _build_market_inputs(
    canonical_market_csv: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if _file_sha256(canonical_market_csv) != EXPECTED_CANONICAL_MARKET_SHA256:
        raise VolatilityDiagnosticError("canonical market bytes drifted")
    raw = pd.read_csv(canonical_market_csv)
    cfg = data_config()
    assumptions = assumptions_config()
    schema = cfg["canonical_contract_schema"]
    source = cfg["sources"]["market_canonical"]
    policy = assumptions["assumptions"]["continuous_series_policy"]["policy"]
    available = ensure_canonical_market_availability(raw, source["availability_policy"])
    canonical = validate_contract_history(available, schema)
    selected, _ = build_derived_continuous_series(canonical, schema, policy)
    selected = selected.copy()
    selected["trade_date"] = pd.to_datetime(selected["trade_date"], utc=True)
    selected["available_at"] = pd.to_datetime(selected["available_at"], utc=True)
    if (
        selected["trade_date"].duplicated().any()
        or selected["available_at"].duplicated().any()
    ):
        raise VolatilityDiagnosticError(
            "selected market path is not one-to-one by session"
        )
    return canonical, selected


def _next_session_trade_dates(
    selected: pd.DataFrame,
) -> dict[pd.Timestamp, pd.Timestamp]:
    dates = list(pd.DatetimeIndex(selected["trade_date"]).sort_values())
    return {current: following for current, following in pairwise(dates)}


def _exact_canonical_row(
    canonical: pd.DataFrame, contract_id: str, trade_date: pd.Timestamp
) -> pd.Series:
    matched = canonical.loc[
        canonical["contract_id"].astype(str).eq(contract_id)
        & pd.to_datetime(canonical["trade_date"], utc=True).eq(trade_date)
    ]
    if len(matched) != 1:
        raise VolatilityDiagnosticError(
            f"expected exactly one canonical row for {contract_id} on {trade_date.isoformat()}"
        )
    return matched.iloc[0]


def _build_candidates(
    frame: pd.DataFrame,
    canonical: pd.DataFrame,
    selected: pd.DataFrame,
) -> pd.DataFrame:
    selected_by_cutoff = selected.set_index("available_at", drop=False)
    next_dates = _next_session_trade_dates(selected)
    records: list[dict[str, Any]] = []
    for prediction_time in frame.index:
        if prediction_time not in selected_by_cutoff.index:
            raise VolatilityDiagnosticError(
                f"no selected contract at {prediction_time.isoformat()}"
            )
        chosen = selected_by_cutoff.loc[prediction_time]
        if isinstance(chosen, pd.DataFrame):
            raise VolatilityDiagnosticError("selected market cutoff is ambiguous")
        contract_id = str(chosen["contract_id"])
        trade_date = pd.Timestamp(chosen["trade_date"])
        target_trade_date = next_dates.get(trade_date)
        if target_trade_date is None:
            raise VolatilityDiagnosticError("next trading session is unavailable")
        target_row = _exact_canonical_row(canonical, contract_id, target_trade_date)
        target_available = pd.Timestamp(target_row["available_at"])
        if target_available <= prediction_time:
            raise VolatilityDiagnosticError(
                "target bar is available at or before prediction cutoff"
            )

        history = canonical.loc[
            canonical["contract_id"].astype(str).eq(contract_id)
            & (pd.to_datetime(canonical["available_at"], utc=True) <= prediction_time)
            & (pd.to_datetime(canonical["trade_date"], utc=True) <= trade_date)
        ].sort_values("trade_date")
        if len(history) < 20:
            raise VolatilityDiagnosticError(
                "candidate row lacks 20 same-contract history bars"
            )
        rv = np.asarray(
            [_garman_klass_variance(row) for _, row in history.iterrows()], dtype=float
        )
        recent = rv[-20:]
        target_rv = _garman_klass_variance(target_row)
        records.append(
            {
                "prediction_time": prediction_time,
                "trade_date": trade_date,
                "contract_id": contract_id,
                "target_trade_date": target_trade_date,
                "target_available_at": target_available,
                "target_rv": target_rv,
                "baseline_rv20": float(recent.mean()),
                "last_rv": float(recent[-1]),
                "log_rv_d1": math.log(max(float(recent[-1]), EPSILON)),
                "log_rv_w5": math.log(max(float(recent[-5:].mean()), EPSILON)),
                "log_rv_m20": math.log(max(float(recent.mean()), EPSILON)),
                "same_contract_history_rows": len(history),
            }
        )
    candidates = pd.DataFrame(records).set_index("prediction_time")
    if not candidates.index.equals(frame.index):
        raise VolatilityDiagnosticError(
            "candidate row identity differs from frozen dataset"
        )
    if (
        len(candidates) != 456
        or int(candidates["same_contract_history_rows"].min()) < 20
    ):
        raise VolatilityDiagnosticError("diagnostic coverage gate failed")
    if candidates["target_available_at"].isna().any():
        raise VolatilityDiagnosticError("diagnostic target availability is incomplete")
    return candidates


def prepare_diagnostic_inputs(
    repo_root: Path, dataset_dir: Path, canonical_market_csv: Path
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    contract, release = validate_release_authority(repo_root)
    frame, manifest = _validate_dataset(dataset_dir, contract)
    canonical, selected = _build_market_inputs(canonical_market_csv)
    candidates = _build_candidates(frame, canonical, selected)
    return candidates, contract, {"release": release, "manifest": manifest}


_FEATURES = ["log_rv_d1", "log_rv_w5", "log_rv_m20"]


def _fit_log_har(training: pd.DataFrame) -> np.ndarray:
    if training.empty:
        raise VolatilityDiagnosticError("HAR training set is empty")
    x = training[_FEATURES].to_numpy(dtype=float)
    y = np.log(np.maximum(training["target_rv"].to_numpy(dtype=float), EPSILON))
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise VolatilityDiagnosticError("HAR training data contains non-finite values")
    design = np.column_stack([np.ones(len(x), dtype=float), x])
    coefficients, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    if not np.isfinite(coefficients).all():
        raise VolatilityDiagnosticError("HAR fit produced non-finite coefficients")
    return coefficients


def _predict_log_har(coefficients: np.ndarray, row: pd.Series) -> float:
    values = np.asarray(
        [1.0, *(float(row[column]) for column in _FEATURES)], dtype=float
    )
    predicted_log = float(values @ coefficients)
    forecast = max(math.exp(predicted_log), EPSILON)
    if not math.isfinite(forecast):
        raise VolatilityDiagnosticError("HAR forecast is non-finite")
    return forecast


def _walk_forward_predictions(
    candidates: pd.DataFrame, contract: dict[str, Any]
) -> pd.DataFrame:
    initial = int(contract["walk_forward"]["initial_train_rows"])
    refit_every = int(contract["walk_forward"]["refit_every_scored_rows"])
    rows: list[dict[str, Any]] = []
    coefficients: np.ndarray | None = None
    for position in range(initial, len(candidates)):
        current_time = candidates.index[position]
        if coefficients is None or (position - initial) % refit_every == 0:
            prior = candidates.iloc[:position]
            training = prior.loc[prior["target_available_at"] <= current_time]
            if len(training) != position:
                raise VolatilityDiagnosticError(
                    "walk-forward labels are not fully available at refit cutoff"
                )
            coefficients = _fit_log_har(training)
        current = candidates.iloc[position]
        assert coefficients is not None
        rows.append(
            {
                "prediction_time": current_time,
                "target_trade_date": current["target_trade_date"],
                "target_available_at": current["target_available_at"],
                "contract_id": current["contract_id"],
                "actual_rv": float(current["target_rv"]),
                "baseline_rv20": float(current["baseline_rv20"]),
                "challenger_log_har": _predict_log_har(coefficients, current),
                "last_observation_rv": float(current["last_rv"]),
            }
        )
    result = pd.DataFrame(rows).set_index("prediction_time")
    expected = candidates.index[initial:]
    if not result.index.equals(expected):
        raise VolatilityDiagnosticError("walk-forward prediction identity drifted")
    return result


def _qlike(actual: np.ndarray, forecast: np.ndarray) -> np.ndarray:
    y = np.maximum(np.asarray(actual, dtype=float), EPSILON)
    h = np.maximum(np.asarray(forecast, dtype=float), EPSILON)
    ratio = y / h
    values = ratio - np.log(ratio) - 1.0
    if not np.isfinite(values).all():
        raise VolatilityDiagnosticError("QLIKE produced non-finite loss")
    return values


def _moving_block_mean_inference(
    delta: np.ndarray, *, block_size: int, resamples: int, confidence: float, seed: int
) -> dict[str, float | int | str]:
    values = np.asarray(delta, dtype=float)
    n = len(values)
    if n < 2 or block_size < 1 or block_size > n or resamples < 100:
        raise VolatilityDiagnosticError("invalid moving-block bootstrap configuration")
    observed = float(values.mean())
    rng = np.random.default_rng(seed)
    max_start = n - block_size
    blocks_needed = math.ceil(n / block_size)
    draws = np.empty(resamples, dtype=float)
    for index in range(resamples):
        starts = rng.integers(0, max_start + 1, size=blocks_needed)
        sampled = np.concatenate(
            [np.arange(start, start + block_size) for start in starts]
        )[:n]
        draws[index] = float(values[sampled].mean())
    alpha = 1.0 - confidence
    lower, upper = np.quantile(draws, [alpha / 2.0, 1.0 - alpha / 2.0])
    centered_null = draws - observed
    p_value = float(
        (1 + np.count_nonzero(np.abs(centered_null) >= abs(observed))) / (resamples + 1)
    )
    return {
        "method": "moving_block_bootstrap",
        "mean_improvement": observed,
        "ci_lower": float(lower),
        "ci_upper": float(upper),
        "p_value_two_sided": p_value,
        "block_size": block_size,
        "effective_block_equivalent_units": float(n / block_size),
        "resamples": resamples,
    }


def _robustness_counts(
    predictions: pd.DataFrame,
    delta: np.ndarray,
    initial_baselines: np.ndarray,
) -> dict[str, Any]:
    period_positions = np.array_split(np.arange(len(predictions)), 3)
    period_means = [float(delta[position].mean()) for position in period_positions]
    cutpoints = np.quantile(initial_baselines, [1.0 / 3.0, 2.0 / 3.0])
    regimes = np.searchsorted(
        cutpoints, predictions["baseline_rv20"].to_numpy(dtype=float), side="right"
    )
    regime_means: list[float] = []
    regime_counts: list[int] = []
    for regime in range(3):
        mask = regimes == regime
        if not mask.any():
            raise VolatilityDiagnosticError(
                "a frozen volatility regime has no scored rows"
            )
        regime_counts.append(int(mask.sum()))
        regime_means.append(float(delta[mask].mean()))
    return {
        "period_mean_improvements": period_means,
        "positive_periods": int(sum(value > 0.0 for value in period_means)),
        "regime_cutpoints": [float(value) for value in cutpoints],
        "regime_counts": regime_counts,
        "regime_mean_improvements": regime_means,
        "positive_regimes": int(sum(value > 0.0 for value in regime_means)),
    }


def _evaluate_predictions(
    predictions: pd.DataFrame,
    candidates: pd.DataFrame,
    contract: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    actual = predictions["actual_rv"].to_numpy(dtype=float)
    baseline = predictions["baseline_rv20"].to_numpy(dtype=float)
    challenger = predictions["challenger_log_har"].to_numpy(dtype=float)
    baseline_loss = _qlike(actual, baseline)
    challenger_loss = _qlike(actual, challenger)
    delta = baseline_loss - challenger_loss
    scored = predictions.copy()
    scored["baseline_qlike"] = baseline_loss
    scored["challenger_qlike"] = challenger_loss
    scored["qlike_improvement"] = delta

    inference_cfg = contract["inference"]
    inference: dict[str, Any] = {}
    for block_size in [
        int(inference_cfg["primary_block_size_sessions"]),
        *(int(value) for value in inference_cfg["block_sensitivity_sessions"]),
    ]:
        inference[str(block_size)] = _moving_block_mean_inference(
            delta,
            block_size=block_size,
            resamples=int(inference_cfg["resamples"]),
            confidence=float(inference_cfg["confidence"]),
            seed=int(inference_cfg["seed"]),
        )
    primary = inference[str(inference_cfg["primary_block_size_sessions"])]
    mean_baseline = float(baseline_loss.mean())
    mean_challenger = float(challenger_loss.mean())
    if mean_baseline <= 0.0:
        raise VolatilityDiagnosticError("primary baseline mean QLIKE is not positive")
    relative_improvement = float((mean_baseline - mean_challenger) / mean_baseline)
    robustness = _robustness_counts(
        scored,
        delta,
        candidates.iloc[: int(contract["diagnostic"]["initial_train_rows"])][
            "baseline_rv20"
        ].to_numpy(dtype=float),
    )
    materiality = float(contract["materiality"]["minimum_relative_improvement"])
    max_p = float(inference_cfg["primary_p_value_max"])
    gates = {
        "mean_qlike_improvement_positive": float(delta.mean()) > 0.0,
        "primary_ci_lower_positive": float(primary["ci_lower"]) > 0.0,
        "primary_p_value_at_most_threshold": float(primary["p_value_two_sided"])
        <= max_p,
        "relative_qlike_improvement_at_least_materiality": relative_improvement
        >= materiality,
        "period_robustness": robustness["positive_periods"]
        >= int(inference_cfg["period_robustness"]["minimum_positive_periods"]),
        "regime_robustness": robustness["positive_regimes"]
        >= int(inference_cfg["regime_robustness"]["minimum_positive_regimes"]),
    }
    primary_pass = all(gates.values())

    paired_sd = float(np.std(delta, ddof=1))
    confirmation_absolute_mde = (
        float(contract["power"]["confirmation_standardized_mde"]) * paired_sd
    )
    confirmation_relative_mde = confirmation_absolute_mde / mean_baseline
    sqrt_actual = np.sqrt(np.maximum(actual, 0.0))
    secondary_rmse = {
        "baseline_rv20": float(
            np.sqrt(np.mean((np.sqrt(np.maximum(baseline, 0.0)) - sqrt_actual) ** 2))
        ),
        "challenger_log_har": float(
            np.sqrt(np.mean((np.sqrt(np.maximum(challenger, 0.0)) - sqrt_actual) ** 2))
        ),
        "last_observation": float(
            np.sqrt(
                np.mean(
                    (
                        np.sqrt(
                            np.maximum(
                                predictions["last_observation_rv"].to_numpy(
                                    dtype=float
                                ),
                                0.0,
                            )
                        )
                        - sqrt_actual
                    )
                    ** 2
                )
            )
        ),
    }
    summary = {
        "experiment_id": EXPERIMENT_ID,
        "authority": {
            "diagnostic_only": True,
            "research_promotion_authorized": False,
            "confirmation_execution_authorized": False,
            "trading_authority": False,
            "issue_51_touched": False,
        },
        "primary": {
            "rows": len(scored),
            "mean_baseline_qlike": mean_baseline,
            "mean_challenger_qlike": mean_challenger,
            "mean_qlike_improvement": float(delta.mean()),
            "relative_qlike_improvement": relative_improvement,
            "materiality_threshold": materiality,
            "inference": inference,
            "robustness": robustness,
            "gates": gates,
            "passes_all_primary_gates": primary_pass,
            "disposition": "diagnostic_pass"
            if primary_pass
            else "diagnostic_primary_failure",
        },
        "confirmation_power_planning": {
            "paired_qlike_improvement_sd": paired_sd,
            "confirmation_standardized_mde": float(
                contract["power"]["confirmation_standardized_mde"]
            ),
            "confirmation_absolute_qlike_mde": confirmation_absolute_mde,
            "confirmation_relative_mde_vs_baseline_qlike": confirmation_relative_mde,
            "materiality_threshold": materiality,
            "sample_size_power_gate_passes": confirmation_relative_mde <= materiality,
            "confirmation_remains_locked": True,
        },
        "secondary_descriptive_only": {"sqrt_realized_variance_rmse": secondary_rmse},
    }
    return scored, summary


def _publish_result_artifacts(
    output_dir: Path, export: pd.DataFrame, summary: dict[str, Any]
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir / ".publication.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise VolatilityDiagnosticError(
            "#195 result publication is already in progress"
        ) from exc
    os.close(descriptor)

    predictions_path = output_dir / "predictions.csv"
    summary_path = output_dir / "summary.json"
    try:
        if predictions_path.exists() or summary_path.exists():
            raise VolatilityDiagnosticError(
                "#195 result artifact already exists; refusing overwrite"
            )
        try:
            _atomic_csv(predictions_path, export)
            summary["execution"]["predictions_sha256"] = _file_sha256(predictions_path)
            _atomic_json(summary_path, summary)
        except BaseException:
            predictions_path.unlink(missing_ok=True)
            summary_path.unlink(missing_ok=True)
            predictions_path.with_suffix(predictions_path.suffix + ".tmp").unlink(
                missing_ok=True
            )
            summary_path.with_suffix(summary_path.suffix + ".tmp").unlink(
                missing_ok=True
            )
            raise
    finally:
        lock_path.unlink(missing_ok=True)


def run_diagnostic(
    *,
    repo_root: Path,
    dataset_dir: Path,
    canonical_market_csv: Path,
    output_dir: Path,
) -> dict[str, Any]:
    execution_revision = _require_committed_evaluator(repo_root)
    candidates, contract, evidence = prepare_diagnostic_inputs(
        repo_root, dataset_dir, canonical_market_csv
    )
    predictions = _walk_forward_predictions(candidates, contract)
    scored, summary = _evaluate_predictions(predictions, candidates, contract)
    export = scored.reset_index()
    for column in ("prediction_time", "target_trade_date", "target_available_at"):
        export[column] = pd.to_datetime(export[column], utc=True).map(
            pd.Timestamp.isoformat
        )
    summary["execution"] = {
        "execution_revision": execution_revision,
        "evaluator_sha256": _file_sha256(
            repo_root / "src/commodity/volatility_diagnostic.py"
        ),
        "release_sha256": EXPECTED_RELEASE_SHA256,
        "dataset_sha256": EXPECTED_DATASET_SHA256,
        "canonical_market_sha256": EXPECTED_CANONICAL_MARKET_SHA256,
        "frozen_dataset_id": evidence["manifest"].get("dataset_id"),
    }
    _publish_result_artifacts(output_dir, export, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute frozen #195 volatility diagnostic"
    )
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--canonical-market-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = run_diagnostic(
        repo_root=args.repo_root,
        dataset_dir=args.dataset_dir,
        canonical_market_csv=args.canonical_market_csv,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
