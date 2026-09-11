from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
CHANGE_DIR = Path(__file__).resolve().parent
MODELS_PATH = REPO_ROOT / "config" / "models.json"
PHASE2_CONFIG = REPO_ROOT / "config" / "phase2_market_only.json"
SAMPLE_KEYS = CHANGE_DIR / "second-line-sample-keys.csv"
KDIAG_PATH = CHANGE_DIR / "phase4_kronos_path_diagnostic.py"
EXPECTED_SAMPLE_SHA256 = "b8558d19e8edc90937d46a17ea06a807fdac9548495e7e39e0552af9771100ba"
PRED_LEN = 5
TARGET_COLUMNS = ("open", "high", "low", "close", "volume")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_kdiag():
    spec = importlib.util.spec_from_file_location("phase4_kdiag", KDIAG_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Kronos path diagnostic helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _snapshot(cache: Path, model_id: str, revision: str) -> Path:
    slug = "models--" + model_id.replace("/", "--")
    return cache / slug / "snapshots" / revision


def _selected_cases(all_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if _sha256(SAMPLE_KEYS) != EXPECTED_SAMPLE_SHA256:
        raise RuntimeError("second-line sample-key hash changed")
    keys = pd.read_csv(SAMPLE_KEYS)
    keys["prediction_time"] = pd.to_datetime(keys["prediction_time"], utc=True)
    lookup = {
        (str(case["outer_block_id"]), pd.Timestamp(case["prediction_time"]), str(case["contract_id"])): case
        for case in all_cases
    }
    selected: list[dict[str, Any]] = []
    for row in keys.itertuples(index=False):
        key = (str(row.outer_block_id), pd.Timestamp(row.prediction_time), str(row.contract_id))
        if key not in lookup:
            raise RuntimeError(f"frozen second-line key missing from eligible cases: {key}")
        selected.append(lookup[key])
    if len(selected) != 96 or len({(c["prediction_time"], c["contract_id"]) for c in selected}) != 96:
        raise RuntimeError("frozen second-line sample is not exactly 96 unique origins")
    return selected


def _case_row(case: dict[str, Any], prediction: np.ndarray, quantiles: list[float]) -> dict[str, Any]:
    q10 = quantiles.index(0.1)
    q50 = quantiles.index(0.5)
    q90 = quantiles.index(0.9)
    close_index = TARGET_COLUMNS.index("close")
    current_close = float(case["current_close"])
    close_pred = prediction[close_index]
    median_returns = close_pred[q50] / current_close - 1.0
    lower_returns = close_pred[q10] / current_close - 1.0
    upper_returns = close_pred[q90] / current_close - 1.0
    actual_close = case["actual"]["close"].astype(float).to_numpy()
    actual_returns = actual_close / current_close - 1.0
    pred_slope = float(np.polyfit(np.arange(1, PRED_LEN + 1), median_returns, 1)[0])
    actual_slope = float(np.polyfit(np.arange(1, PRED_LEN + 1), actual_returns, 1)[0])
    row: dict[str, Any] = {
        "outer_block_id": str(case["outer_block_id"]),
        "trade_date": pd.Timestamp(case["trade_date"]).isoformat(),
        "prediction_time": pd.Timestamp(case["prediction_time"]).isoformat(),
        "generated_at": pd.Timestamp(case["prediction_time"]).isoformat(),
        "fill_trade_date": pd.Timestamp(case["fill_trade_date"]).isoformat(),
        "contract_id": str(case["contract_id"]),
        "future_end": pd.Timestamp(case["future_index"][-1]).isoformat(),
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


def _generate(checkpoint_root: Path, cache: Path, output: Path, batch_size: int) -> dict[str, Any]:
    import torch
    from chronos import Chronos2Pipeline
    from chronos import __version__ as chronos_version

    registry = json.loads(MODELS_PATH.read_text(encoding="utf-8"))["models"]
    model_cfg = registry["chronos_2"]
    snapshot = _snapshot(cache, model_cfg["model_id"], model_cfg["model_revision"])
    weight = snapshot / model_cfg["checkpoint_artifacts"]["model"]["filename"]
    config = snapshot / "config.json"
    if not weight.is_file() or _sha256(weight) != model_cfg["checkpoint_artifacts"]["model"]["sha256"]:
        raise RuntimeError("Chronos-2 weight missing or hash mismatch")
    if not config.is_file():
        raise RuntimeError("Chronos-2 config.json missing from exact snapshot")
    phase2_cfg = json.loads(PHASE2_CONFIG.read_text(encoding="utf-8"))
    kdiag = _load_kdiag()
    all_cases, excluded = kdiag._cases(checkpoint_root, phase2_cfg, int(model_cfg["max_context"]))
    cases = _selected_cases(all_cases)
    rows: list[dict[str, Any]] = []
    existing: set[tuple[str, str]] = set()
    if output.is_file():
        frame = pd.read_csv(output)
        rows = frame.to_dict("records")
        existing = {(pd.Timestamp(r.prediction_time).isoformat(), str(r.contract_id)) for r in frame.itertuples(index=False)}
    pending = [c for c in cases if (pd.Timestamp(c["prediction_time"]).isoformat(), str(c["contract_id"])) not in existing]
    pipe = Chronos2Pipeline.from_pretrained(snapshot, local_files_only=True, device_map="cpu")
    quantiles = [float(value) for value in pipe.quantiles]
    torch.manual_seed(0)
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        inputs = [
            {"target": case["history"][list(TARGET_COLUMNS)].astype("float32").to_numpy().T}
            for case in batch
        ]
        predictions = pipe.predict(inputs, prediction_length=PRED_LEN, batch_size=batch_size)
        for case, prediction in zip(batch, predictions, strict=True):
            rows.append(_case_row(case, prediction.detach().cpu().numpy(), quantiles))
        output.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).sort_values(["prediction_time", "contract_id"]).to_csv(
            output, index=False, lineterminator="\n"
        )
    final = pd.read_csv(output)
    complete = len(final) == 96
    result: dict[str, Any] = {
        "schema_version": 1,
        "authority": "github-issue-358-comment-5634786235",
        "candidate_id": "chronos-2-five-step-probabilistic-path",
        "model_key": "chronos_2",
        "model_id": model_cfg["model_id"],
        "model_revision": model_cfg["model_revision"],
        "model_checkpoint_sha256": _sha256(weight),
        "config_sha256": _sha256(config),
        "runtime_package": f"chronos-forecasting=={chronos_version}",
        "sample_keys_sha256": _sha256(SAMPLE_KEYS),
        "rows": len(final),
        "selected_origins": 96,
        "complete": complete,
        "pred_len": PRED_LEN,
        "target_columns": list(TARGET_COLUMNS),
        "quantiles": quantiles,
        "excluded_before_frozen_sample": excluded,
        "protected_confirmation_accessed": False,
        "evidence_role": "development_second_line_foundation_specialist_diagnostic_not_policy_selection",
        "promotion_eligibility": "deployment_candidate",
        "output_sha256": _sha256(output),
    }
    if complete:
        result["metrics"] = _metrics(final)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-4 Chronos-2 fixed five-step path diagnostic")
    parser.add_argument("--phase2-checkpoint-root", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    if args.batch_size <= 0:
        raise SystemExit("batch-size must be positive")
    kdiag = _load_kdiag()
    with kdiag._writer_lock(args.output.with_suffix(args.output.suffix + ".writer.lock")):
        result = _generate(args.phase2_checkpoint_root, args.cache_dir, args.output, args.batch_size)
        args.summary.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps({"rows": result["rows"], "complete": result["complete"], "protected_confirmation_accessed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
