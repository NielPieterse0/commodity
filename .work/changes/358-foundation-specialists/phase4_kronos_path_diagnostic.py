from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from commodity.kronos import resolve_kronos_artifacts, verify_kronos_source_checkout
from commodity.market_only_phase2 import (
    _build_segmented_decision_origins,
    _canonicalize_one_origin_per_fill,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS_PATH = REPO_ROOT / "config" / "models.json"
PHASE2_CONFIG = REPO_ROOT / "config" / "phase2_market_only.json"
PRED_LEN = 5


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _writer_lock(path: Path) -> Iterator[None]:
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


def _read_ohlcv(checkpoint_root: Path) -> pd.DataFrame:
    paths = sorted((checkpoint_root / "reconstruction" / "partitions").glob("*-ohlcv.parquet"))
    if not paths:
        raise RuntimeError("no Phase-2 OHLCV reconstruction partitions found")
    frame = pd.concat((pd.read_parquet(path) for path in paths), ignore_index=True)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True)
    return frame.sort_values(["contract_id", "trade_date"], ignore_index=True)


def _outer_origins(checkpoint_root: Path, cfg: dict[str, Any]) -> pd.DataFrame:
    features = pd.read_parquet(checkpoint_root / "inputs" / "features.parquet")
    session = pd.read_parquet(checkpoint_root / "inputs" / "session-path.parquet")
    origins, _ = _build_segmented_decision_origins(
        session,
        features,
        horizon_sessions=int(cfg["execution_contract"]["horizon_sessions"]),
    )
    origins, _ = _canonicalize_one_origin_per_fill(origins)
    chunks = []
    for block in cfg["validation"]["outer_blocks"]:
        start = pd.Timestamp(block["start"], tz="UTC")
        end = pd.Timestamp(block["end"], tz="UTC") + pd.Timedelta(days=1)
        mask = (pd.to_datetime(origins["fill_trade_date"], utc=True) >= start) & (
            pd.to_datetime(origins["fill_trade_date"], utc=True) < end
        )
        chunks.append(origins.loc[mask].assign(outer_block_id=str(block["id"])))
    out = pd.concat(chunks, ignore_index=True)
    if out.duplicated(["signal_timestamp", "fill_contract_id"]).any():
        raise RuntimeError("outer origins are not unique by signal time and fill contract")
    return out


def _path_stats(current_close: float, path: pd.DataFrame) -> dict[str, float | int]:
    closes = path["close"].astype(float).to_numpy()
    highs = path["high"].astype(float).to_numpy()
    lows = path["low"].astype(float).to_numpy()
    returns = closes / current_close - 1.0
    increments = np.diff(np.concatenate(([current_close], closes)))
    signs = np.sign(increments)
    turning_count = int(np.sum((signs[1:] * signs[:-1]) < 0))
    slope = float(np.polyfit(np.arange(1, len(closes) + 1), returns, 1)[0])
    result: dict[str, float | int] = {
        "terminal_return": float(returns[-1]),
        "slope_per_step": slope,
        "range_pct": float((highs.max() - lows.min()) / current_close),
        "close_dispersion_pct": float(np.std(returns)),
        "max_upside_pct": float(highs.max() / current_close - 1.0),
        "max_downside_pct": float(lows.min() / current_close - 1.0),
        "turning_count": turning_count,
    }
    for index, value in enumerate(returns, start=1):
        result[f"close_return_h{index}"] = float(value)
    return result


def _cases(checkpoint_root: Path, cfg: dict[str, Any], max_context: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    origins = _outer_origins(checkpoint_root, cfg)
    ohlcv = _read_ohlcv(checkpoint_root)
    cutoff = pd.Timestamp(cfg["evidence_boundary"]["last_allowed_trade_date"], tz="UTC")
    grouped = {str(key): group for key, group in ohlcv.groupby("contract_id", sort=False)}
    cases: list[dict[str, Any]] = []
    excluded = {"insufficient_history": 0, "insufficient_future_path": 0, "future_crosses_cutoff": 0}
    for row in origins.itertuples(index=False):
        contract = str(row.fill_contract_id)
        history_all = grouped.get(contract)
        if history_all is None:
            excluded["insufficient_history"] += 1
            continue
        signal_trade_date = pd.Timestamp(row.trade_date)
        history = history_all.loc[history_all["trade_date"] <= signal_trade_date].tail(max_context).copy()
        if len(history) < 20:
            excluded["insufficient_history"] += 1
            continue
        fill_trade_date = pd.Timestamp(row.fill_trade_date)
        future_all = history_all.loc[history_all["trade_date"] >= fill_trade_date].head(PRED_LEN).copy()
        if len(future_all) < PRED_LEN:
            excluded["insufficient_future_path"] += 1
            continue
        if pd.Timestamp(future_all["trade_date"].max()) > cutoff:
            excluded["future_crosses_cutoff"] += 1
            continue
        values = history[["open", "high", "low", "close", "volume"]].astype(float)
        actual = future_all[["open", "high", "low", "close", "volume"]].astype(float)
        if not np.isfinite(values.to_numpy()).all() or not np.isfinite(actual.to_numpy()).all():
            raise RuntimeError("Kronos path case contains non-finite OHLCV values")
        if (values[["open", "high", "low", "close"]] <= 0).any().any():
            raise RuntimeError("Kronos path history contains non-positive prices")
        cases.append({
            "trade_date": signal_trade_date,
            "prediction_time": pd.Timestamp(row.signal_timestamp),
            "fill_trade_date": pd.Timestamp(row.fill_trade_date),
            "contract_id": contract,
            "outer_block_id": str(row.outer_block_id),
            "current_close": float(values["close"].iloc[-1]),
            "history": values.set_axis(pd.DatetimeIndex(history["trade_date"])),
            "future_index": pd.DatetimeIndex(future_all["trade_date"]),
            "actual": actual.set_axis(pd.DatetimeIndex(future_all["trade_date"])),
        })
    return cases, excluded


def _select_cases(cases: list[dict[str, Any]], max_per_block: int | None) -> list[dict[str, Any]]:
    if max_per_block is None:
        return cases
    if max_per_block <= 0:
        raise ValueError("max_per_block must be positive")
    selected: list[dict[str, Any]] = []
    block_ids = sorted({str(case["outer_block_id"]) for case in cases})
    for block_id in block_ids:
        block_cases = sorted(
            (case for case in cases if str(case["outer_block_id"]) == block_id),
            key=lambda case: (case["prediction_time"], case["contract_id"]),
        )
        if len(block_cases) <= max_per_block:
            selected.extend(block_cases)
            continue
        indexes = np.linspace(0, len(block_cases) - 1, num=max_per_block, dtype=int)
        selected.extend(block_cases[int(index)] for index in indexes)
    return sorted(selected, key=lambda case: (case["prediction_time"], case["contract_id"]))


def _row(case: dict[str, Any], forecast: pd.DataFrame) -> dict[str, Any]:
    predicted = _path_stats(case["current_close"], forecast)
    actual = _path_stats(case["current_close"], case["actual"])
    row: dict[str, Any] = {
        "trade_date": case["trade_date"].isoformat(),
        "prediction_time": case["prediction_time"].isoformat(),
        "generated_at": case["prediction_time"].isoformat(),
        "fill_trade_date": case["fill_trade_date"].isoformat(),
        "contract_id": case["contract_id"],
        "outer_block_id": case["outer_block_id"],
        "future_end": case["future_index"][-1].isoformat(),
    }
    row.update({f"pred_{key}": value for key, value in predicted.items()})
    row.update({f"actual_{key}": value for key, value in actual.items()})
    return row


def _metric_summary(frame: pd.DataFrame) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for horizon in range(1, PRED_LEN + 1):
        pred = frame[f"pred_close_return_h{horizon}"].astype(float)
        actual = frame[f"actual_close_return_h{horizon}"].astype(float)
        error = pred - actual
        output[f"h{horizon}"] = {
            "mae_return": float(error.abs().mean()),
            "rmse_return": float(np.sqrt(np.mean(np.square(error)))),
            "direction_accuracy": float((np.sign(pred) == np.sign(actual)).mean()),
        }
    pred_terminal = frame["pred_terminal_return"].astype(float)
    actual_terminal = frame["actual_terminal_return"].astype(float)
    pred_slope = frame["pred_slope_per_step"].astype(float)
    actual_slope = frame["actual_slope_per_step"].astype(float)
    output["path"] = {
        "terminal_direction_accuracy": float((np.sign(pred_terminal) == np.sign(actual_terminal)).mean()),
        "slope_sign_accuracy": float((np.sign(pred_slope) == np.sign(actual_slope)).mean()),
        "slope_mae": float((pred_slope - actual_slope).abs().mean()),
        "range_mae_pct": float((frame["pred_range_pct"] - frame["actual_range_pct"]).abs().mean()),
        "dispersion_mae_pct": float(
            (frame["pred_close_dispersion_pct"] - frame["actual_close_dispersion_pct"]).abs().mean()
        ),
        "turning_count_mae": float((frame["pred_turning_count"] - frame["actual_turning_count"]).abs().mean()),
        "turning_count_exact_rate": float((frame["pred_turning_count"] == frame["actual_turning_count"]).mean()),
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


def _generate(
    *,
    checkpoint_root: Path,
    source_root: Path,
    output: Path,
    batch_size: int,
    max_new_origins: int | None,
    max_per_block: int | None,
    profile_name: str,
    model_key: str = "kronos_base",
) -> dict[str, Any]:
    cfg = json.loads(PHASE2_CONFIG.read_text(encoding="utf-8"))
    models = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
    if model_key not in {"kronos_base", "kronos_small"}:
        raise ValueError(f"unsupported Kronos path diagnostic model: {model_key}")
    model_cfg = models["models"][model_key]
    source_revision = verify_kronos_source_checkout(source_root, model_cfg["source_revision"])
    artifacts = resolve_kronos_artifacts(model_cfg)
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    import torch
    from model import Kronos, KronosPredictor, KronosTokenizer

    tokenizer = KronosTokenizer.from_pretrained(artifacts["tokenizer"]["snapshot_path"])
    model = Kronos.from_pretrained(artifacts["model"]["snapshot_path"])
    predictor = KronosPredictor(
        model, tokenizer, device="cpu", max_context=int(model_cfg["max_context"])
    )
    profile = models["kronos_confirmation_profile"][profile_name]
    eligible_cases, excluded = _cases(checkpoint_root, cfg, int(model_cfg["max_context"]))
    cases = _select_cases(eligible_cases, max_per_block)
    existing_keys: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    if output.is_file():
        existing = pd.read_csv(output)
        rows = existing.to_dict("records")
        existing_keys = {
            (pd.Timestamp(row.prediction_time).isoformat(), str(row.contract_id))
            for row in existing.itertuples(index=False)
        }
    pending = [
        case
        for case in cases
        if (case["prediction_time"].isoformat(), case["contract_id"]) not in existing_keys
    ]
    resumed_rows = len(rows)
    if max_new_origins is not None:
        if max_new_origins <= 0:
            raise ValueError("max_new_origins must be positive")
        pending = pending[:max_new_origins]
    by_length: dict[int, list[dict[str, Any]]] = {}
    for case in pending:
        by_length.setdefault(len(case["history"]), []).append(case)
    torch.manual_seed(0)
    for history_length in sorted(by_length):
        group = by_length[history_length]
        for start in range(0, len(group), batch_size):
            batch = group[start : start + batch_size]
            forecasts = predictor.predict_batch(
                [case["history"] for case in batch],
                [pd.Series(case["history"].index) for case in batch],
                [pd.Series(case["future_index"]) for case in batch],
                pred_len=PRED_LEN,
                T=float(profile["T"]),
                top_p=float(profile["top_p"]),
                sample_count=int(profile["sample_count"]),
                verbose=False,
            )
            for case, forecast in zip(batch, forecasts, strict=True):
                if len(forecast) != PRED_LEN:
                    raise RuntimeError("Kronos native path forecast length mismatch")
                rows.append(_row(case, forecast))
            output.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(rows).sort_values(["prediction_time", "contract_id"]).to_csv(
                output, index=False, lineterminator="\n"
            )
    final = pd.read_csv(output) if output.is_file() else pd.DataFrame()
    complete = len(final) == len(cases)
    result: dict[str, Any] = {
        "rows": len(final),
        "total_eligible_origins": len(eligible_cases),
        "selected_origins": len(cases),
        "selection": {
            "method": "outcome_blind_evenly_spaced_within_outer_block",
            "max_per_block": max_per_block,
        },
        "new_origins": int(len(final) - resumed_rows),
        "resumed_rows": int(resumed_rows),
        "complete": bool(complete),
        "excluded": excluded,
        "pred_len": PRED_LEN,
        "batch_size": int(batch_size),
        "inference_profile_name": profile_name,
        "model_key": model_key,
        "source_revision": source_revision,
        "model_id": model_cfg["model_id"],
        "model_revision": model_cfg["model_revision"],
        "model_checkpoint_sha256": artifacts["model"]["artifact_sha256"],
        "tokenizer_revision": model_cfg["tokenizer_revision"],
        "tokenizer_checkpoint_sha256": artifacts["tokenizer"]["artifact_sha256"],
        "inference_profile": profile,
        "deterministic_seed": 0,
        "protected_confirmation_accessed": False,
        "evidence_role": "development_native_sequence_path_diagnostic",
        "output": str(output),
    }
    if output.is_file():
        result["output_sha256"] = _sha256(output)
    if complete and not final.empty:
        result["metrics"] = _metric_summary(final)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-4 Kronos native five-step path diagnostic")
    parser.add_argument("--phase2-checkpoint-root", type=Path, required=True)
    parser.add_argument("--kronos-source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-new-origins", type=int)
    parser.add_argument("--max-per-block", type=int)
    parser.add_argument(
        "--model-key",
        choices=("kronos_base", "kronos_small"),
        default="kronos_base",
    )
    parser.add_argument(
        "--profile",
        choices=("upstream_usage_defaults", "paper_backtest_inference"),
        default="upstream_usage_defaults",
    )
    args = parser.parse_args()
    if args.batch_size <= 0:
        raise SystemExit("batch-size must be positive")
    lock_path = args.output.with_suffix(args.output.suffix + ".writer.lock")
    with _writer_lock(lock_path):
        result = _generate(
            checkpoint_root=args.phase2_checkpoint_root,
            source_root=args.kronos_source_root,
            output=args.output,
            batch_size=args.batch_size,
            max_new_origins=args.max_new_origins,
            max_per_block=args.max_per_block,
            profile_name=args.profile,
            model_key=args.model_key,
        )
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps({
        "rows": result["rows"],
        "total_eligible_origins": result["total_eligible_origins"],
        "complete": result["complete"],
        "protected_confirmation_accessed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
