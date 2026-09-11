from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS_PATH = REPO_ROOT / "config" / "models.json"
BUNDLE = Path(__file__).with_name("moirai-context-bundle.json")
EXPECTED_BUNDLE_SHA256 = "de594857d600ab38d51f28ded0b01abd4d620bd278dd94ddd71af8435ccccbee"
EXPECTED_SAMPLE_SHA256 = "b8558d19e8edc90937d46a17ea06a807fdac9548495e7e39e0552af9771100ba"
PRED_LEN = 5
CONTEXT_LEN = 512
TARGET_COLUMNS = ("open", "high", "low", "close", "volume")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _writer_lock(path: Path):
    import msvcrt
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError(f"checkpoint writer already active: {path}") from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _snapshot(cache: Path, model_id: str, revision: str) -> Path:
    return cache / ("models--" + model_id.replace("/", "--")) / "snapshots" / revision


def _load_bundle() -> dict[str, Any]:
    if _sha256(BUNDLE) != EXPECTED_BUNDLE_SHA256:
        raise RuntimeError("Moirai frozen context bundle hash changed")
    payload = json.loads(BUNDLE.read_text(encoding="utf-8"))
    if payload.get("sample_keys_sha256") != EXPECTED_SAMPLE_SHA256:
        raise RuntimeError("Moirai bundle sample-key hash mismatch")
    if payload.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("Moirai bundle protected-boundary flag invalid")
    if len(payload.get("rows", [])) != 96:
        raise RuntimeError("Moirai bundle must contain exactly 96 origins")
    return payload


def _pad_history(values: list[list[float]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    history = np.asarray(values, dtype=np.float32)
    if history.ndim != 2 or history.shape[1] != len(TARGET_COLUMNS):
        raise RuntimeError(f"invalid history shape: {history.shape}")
    if not np.isfinite(history).all():
        raise RuntimeError("history contains non-finite values")
    history = history[-CONTEXT_LEN:]
    pad_length = CONTEXT_LEN - len(history)
    target = np.empty((CONTEXT_LEN, len(TARGET_COLUMNS)), dtype=np.float32)
    observed = np.ones_like(target, dtype=bool)
    is_pad = np.zeros(CONTEXT_LEN, dtype=bool)
    if pad_length:
        target[:pad_length] = history[0]
        target[pad_length:] = history
        is_pad[:pad_length] = True
    else:
        target[:] = history
    return target, observed, is_pad


def _case_row(case: dict[str, Any], prediction: np.ndarray, quantiles: list[float]) -> dict[str, Any]:
    q10 = quantiles.index(0.1)
    q50 = quantiles.index(0.5)
    q90 = quantiles.index(0.9)
    close_idx = TARGET_COLUMNS.index("close")
    current_close = float(case["current_close"])
    close_pred = prediction[:, :, close_idx]
    median_returns = close_pred[q50] / current_close - 1.0
    lower_returns = close_pred[q10] / current_close - 1.0
    upper_returns = close_pred[q90] / current_close - 1.0
    actual = np.asarray(case["actual"], dtype=float)
    actual_returns = actual[:, close_idx] / current_close - 1.0
    pred_slope = float(np.polyfit(np.arange(1, PRED_LEN + 1), median_returns, 1)[0])
    actual_slope = float(np.polyfit(np.arange(1, PRED_LEN + 1), actual_returns, 1)[0])
    row: dict[str, Any] = {
        "outer_block_id": str(case["outer_block_id"]),
        "prediction_time": str(case["prediction_time"]),
        "generated_at": str(case["prediction_time"]),
        "contract_id": str(case["contract_id"]),
        "pred_terminal_return": float(median_returns[-1]),
        "actual_terminal_return": float(actual_returns[-1]),
        "pred_terminal_q10_return": float(lower_returns[-1]),
        "pred_terminal_q90_return": float(upper_returns[-1]),
        "pred_slope_per_step": pred_slope,
        "actual_slope_per_step": actual_slope,
        "pred_close_dispersion_pct": float(np.std(median_returns)),
        "actual_close_dispersion_pct": float(np.std(actual_returns)),
    }
    for horizon in range(PRED_LEN):
        step = horizon + 1
        row[f"pred_close_return_h{step}"] = float(median_returns[horizon])
        row[f"actual_close_return_h{step}"] = float(actual_returns[horizon])
        row[f"pred_q10_close_return_h{step}"] = float(lower_returns[horizon])
        row[f"pred_q90_close_return_h{step}"] = float(upper_returns[horizon])
    return row


def _metrics(frame: pd.DataFrame) -> dict[str, Any]:
    by_horizon: dict[str, Any] = {}
    interval_by_horizon: dict[str, Any] = {}
    for horizon in range(1, PRED_LEN + 1):
        pred = frame[f"pred_close_return_h{horizon}"].astype(float)
        actual = frame[f"actual_close_return_h{horizon}"].astype(float)
        err = pred - actual
        lower = frame[f"pred_q10_close_return_h{horizon}"].astype(float)
        upper = frame[f"pred_q90_close_return_h{horizon}"].astype(float)
        by_horizon[f"h{horizon}"] = {
            "mae_return": float(err.abs().mean()),
            "rmse_return": float(np.sqrt(np.mean(np.square(err)))),
            "direction_accuracy": float((np.sign(pred) == np.sign(actual)).mean()),
        }
        interval_by_horizon[f"h{horizon}"] = {
            "coverage": float(((actual >= lower) & (actual <= upper)).mean()),
            "mean_width": float((upper - lower).mean()),
        }
    pred_terminal = frame["pred_terminal_return"].astype(float)
    actual_terminal = frame["actual_terminal_return"].astype(float)
    pred_slope = frame["pred_slope_per_step"].astype(float)
    actual_slope = frame["actual_slope_per_step"].astype(float)
    output: dict[str, Any] = {
        "by_horizon": by_horizon,
        "interval_by_horizon": interval_by_horizon,
        "path": {
            "terminal_direction_accuracy": float((np.sign(pred_terminal) == np.sign(actual_terminal)).mean()),
            "slope_sign_accuracy": float((np.sign(pred_slope) == np.sign(actual_slope)).mean()),
            "slope_mae": float((pred_slope - actual_slope).abs().mean()),
            "dispersion_mae_pct": float(
                (frame["pred_close_dispersion_pct"] - frame["actual_close_dispersion_pct"]).abs().mean()
            ),
        },
    }
    output["by_outer_block"] = {
        str(block): {
            "rows": len(group),
            "terminal_direction_accuracy": float(
                (np.sign(group["pred_terminal_return"]) == np.sign(group["actual_terminal_return"])).mean()
            ),
            "slope_sign_accuracy": float(
                (np.sign(group["pred_slope_per_step"]) == np.sign(group["actual_slope_per_step"])).mean()
            ),
        }
        for block, group in frame.groupby("outer_block_id")
    }
    return output


def _generate(cache: Path, output: Path, batch_size: int) -> dict[str, Any]:
    import torch
    from uni2ts.model.moirai2 import Moirai2Forecast, Moirai2Module

    registry = json.loads(MODELS_PATH.read_text(encoding="utf-8"))["models"]
    model_cfg = registry["moirai_2_small"]
    snapshot = _snapshot(cache, model_cfg["model_id"], model_cfg["model_revision"])
    weight = snapshot / model_cfg["checkpoint_artifacts"]["model"]["filename"]
    config = snapshot / "config.json"
    if not weight.is_file() or _sha256(weight) != model_cfg["checkpoint_artifacts"]["model"]["sha256"]:
        raise RuntimeError("Moirai weight missing or hash mismatch")
    if not config.is_file():
        raise RuntimeError("Moirai config.json missing from exact snapshot")
    bundle = _load_bundle()
    cases = bundle["rows"]
    module = Moirai2Module.from_pretrained(snapshot)
    forecast = Moirai2Forecast(
        prediction_length=PRED_LEN,
        target_dim=len(TARGET_COLUMNS),
        feat_dynamic_real_dim=0,
        past_feat_dynamic_real_dim=0,
        context_length=CONTEXT_LEN,
        module=module,
    ).eval()
    quantiles = [float(value) for value in module.quantile_levels]
    rows: list[dict[str, Any]] = []
    existing: set[tuple[str, str]] = set()
    if output.is_file():
        frame = pd.read_csv(output)
        rows = frame.to_dict("records")
        existing = {(str(r.prediction_time), str(r.contract_id)) for r in frame.itertuples(index=False)}
    pending = [c for c in cases if (str(c["prediction_time"]), str(c["contract_id"])) not in existing]
    torch.manual_seed(0)
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        padded = [_pad_history(case["history"]) for case in batch]
        past_target = torch.tensor(np.stack([item[0] for item in padded]), dtype=torch.float32)
        past_observed = torch.tensor(np.stack([item[1] for item in padded]), dtype=torch.bool)
        past_is_pad = torch.tensor(np.stack([item[2] for item in padded]), dtype=torch.bool)
        with torch.no_grad():
            prediction = forecast(
                past_target=past_target,
                past_observed_target=past_observed,
                past_is_pad=past_is_pad,
            ).detach().cpu().numpy()
        if prediction.shape != (len(batch), len(quantiles), PRED_LEN, len(TARGET_COLUMNS)):
            raise RuntimeError(f"unexpected Moirai prediction shape: {prediction.shape}")
        for case, pred in zip(batch, prediction, strict=True):
            rows.append(_case_row(case, pred, quantiles))
        output.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).sort_values(["prediction_time", "contract_id"]).to_csv(
            output, index=False, lineterminator="\n"
        )

    final = pd.read_csv(output)
    complete = len(final) == 96
    result: dict[str, Any] = {
        "schema_version": 1,
        "authority": "github-issue-358-comment-5634786235",
        "candidate_id": "moirai-2-small-five-step-probabilistic-path",
        "model_key": "moirai_2_small",
        "model_id": model_cfg["model_id"],
        "model_revision": model_cfg["model_revision"],
        "model_checkpoint_sha256": _sha256(weight),
        "config_sha256": _sha256(config),
        "runtime_package": f"uni2ts=={importlib.metadata.version('uni2ts')}",
        "python_version": __import__('sys').version.split()[0],
        "context_bundle_sha256": _sha256(BUNDLE),
        "sample_keys_sha256": bundle["sample_keys_sha256"],
        "rows": len(final),
        "selected_origins": 96,
        "complete": complete,
        "pred_len": PRED_LEN,
        "context_length": CONTEXT_LEN,
        "target_columns": list(TARGET_COLUMNS),
        "quantiles": quantiles,
        "protected_confirmation_accessed": False,
        "evidence_role": "development_second_line_foundation_specialist_diagnostic_not_policy_selection",
        "promotion_eligibility": "research_only_noncommercial_not_deployable",
        "output_sha256": _sha256(output),
    }
    if complete:
        result["metrics"] = _metrics(final)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-4 Moirai-2-small fixed five-step path diagnostic")
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    if args.batch_size <= 0:
        raise SystemExit("batch-size must be positive")
    with _writer_lock(args.output.with_suffix(args.output.suffix + ".writer.lock")):
        result = _generate(args.cache_dir, args.output, args.batch_size)
        args.summary.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps({"rows": result["rows"], "complete": result["complete"], "protected_confirmation_accessed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
