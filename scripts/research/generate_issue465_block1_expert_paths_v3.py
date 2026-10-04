from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BLOCK_END = pd.Timestamp("2011-01-06T00:00:00Z")
HORIZONS = (1, 3, 5, 10, 20)
TIMESFM_MODEL = "google/timesfm-2.5-200m-pytorch"
TIMESFM_SOURCE_REVISION = "3dae50b20d7a724981e8ea36cda75578f80dd2dc"
TIMESFM_REVISION = "1d952420fba87f3c6dee4f240de0f1a0fbc790e3"
KRONOS_MODEL_REVISION = "2b554741eca47781b64468546e77fef3e85130e6"
KRONOS_TOKENIZER_REVISION = "0e0117387f39004a9016484a186a908917e22426"
KRONOS_SOURCE_REVISION = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
KRONOS_T = 0.6
KRONOS_TOP_P = 0.9
KRONOS_SAMPLE_COUNT = 5
TIMESFM_SHA256 = "2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8"
KRONOS_MODEL_SHA256 = "abff193acab6db1a0368e9773e75799d11403b6d054ee6d5f0a11aeabc5f4b83"
KRONOS_TOKENIZER_SHA256 = "59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_git_head(source_root: Path, expected: str, label: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    head = result.stdout.strip()
    if head != expected:
        raise RuntimeError(f"{label} source revision mismatch: {head} != {expected}")
    return head


def _verify_snapshot_contains_hash(snapshot_root: Path, expected: str, label: str) -> str:
    if not snapshot_root.is_dir():
        raise RuntimeError(f"{label} snapshot missing: {snapshot_root}")
    for path in sorted(p for p in snapshot_root.rglob("*") if p.is_file()):
        if sha256_file(path) == expected:
            return str(path.relative_to(snapshot_root))
    raise RuntimeError(f"{label} checkpoint hash not found in frozen snapshot")


def path_features(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    x = np.arange(1, len(array) + 1, dtype=float)
    return {
        "slope_per_session": float(np.polyfit(x, array, 1)[0]) if len(array) >= 2 else 0.0,
        "acceleration_per_session2": float(2.0 * np.polyfit(x, array, 2)[0]) if len(array) >= 3 else 0.0,
        "dispersion": float(np.std(array, ddof=0)),
    }

def read_parts(root: Path, suffix: str) -> pd.DataFrame:
    paths = sorted((root / "reconstruction" / "partitions").glob(f"*-{suffix}.parquet"))
    if not paths:
        raise RuntimeError(f"no {suffix} reconstruction partitions")
    return pd.concat((pd.read_parquet(path) for path in paths), ignore_index=True)


def load_inputs(
    pit_state: Path, canonical_csv: Path, ohlcv_csv: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    state = pd.read_json(pit_state, lines=True)
    state["decision_time"] = pd.to_datetime(state["decision_time"], utc=True)
    state["trade_date"] = pd.to_datetime(state["trade_date"], utc=True)
    if len(state) != 123 or (state["decision_time"] >= BLOCK_END).any():
        raise RuntimeError("expert path generator must remain inside the 123-row Block1 state")
    canonical = pd.read_csv(canonical_csv)
    ohlcv = pd.read_csv(ohlcv_csv)
    canonical["trade_date"] = pd.to_datetime(canonical["trade_date"], utc=True)
    canonical["available_at"] = pd.to_datetime(canonical["available_at"], utc=True)
    ohlcv["trade_date"] = pd.to_datetime(ohlcv["trade_date"], utc=True)
    return state, canonical, ohlcv


def build_cases(state: pd.DataFrame, canonical: pd.DataFrame, ohlcv: pd.DataFrame) -> list[dict[str, Any]]:
    canon_groups = {str(key): group.sort_values("trade_date") for key, group in canonical.groupby("contract_id")}
    ohl_groups = {str(key): group.sort_values("trade_date") for key, group in ohlcv.groupby("contract_id")}
    session_dates = list(pd.to_datetime(state["trade_date"], utc=True))
    cases: list[dict[str, Any]] = []
    for index, row in state.reset_index(drop=True).iterrows():
        contract = str(row["fill_contract_id"])
        if contract not in canon_groups or contract not in ohl_groups:
            raise RuntimeError(f"missing same-contract history for {contract}")
        canon = canon_groups[contract]
        eligible_canon = canon.loc[
            (canon["trade_date"] <= row["trade_date"])
            & (canon["available_at"] <= row["decision_time"])
        ].tail(128)
        history = ohl_groups[contract].loc[
            ohl_groups[contract]["trade_date"] <= row["trade_date"]
        ].tail(512)
        if len(eligible_canon) < 20 or len(history) < 20:
            raise RuntimeError("foundation-model history below minimum context")
        future_dates = list(session_dates[index + 1 : index + 21])
        if len(future_dates) < 20:
            anchor = future_dates[-1] if future_dates else pd.Timestamp(row["trade_date"])
            continuation = pd.bdate_range(
                start=anchor + pd.offsets.BDay(1), periods=20 - len(future_dates), tz="UTC"
            )
            future_dates.extend(list(continuation))
        cases.append({
            "decision_time": pd.Timestamp(row["decision_time"]),
            "trade_date": pd.Timestamp(row["trade_date"]),
            "contract_id": contract,
            "timesfm_context": eligible_canon["settle"].astype(float).to_numpy(dtype=np.float32),
            "timesfm_current": float(eligible_canon["settle"].iloc[-1]),
            "kronos_history": history[["open", "high", "low", "close", "volume"]].astype(float).set_axis(pd.DatetimeIndex(history["trade_date"])),
            "kronos_current": float(history["close"].iloc[-1]),
            "future_dates": pd.DatetimeIndex(future_dates),
        })
    return cases


def load_timesfm(source_root: Path, cache_dir: Path):
    _verified_git_head(source_root, TIMESFM_SOURCE_REVISION, "TimesFM")
    snapshot_root = (
        cache_dir / "models--google--timesfm-2.5-200m-pytorch" / "snapshots" / TIMESFM_REVISION
    )
    _verify_snapshot_contains_hash(snapshot_root, TIMESFM_SHA256, "TimesFM")
    sys.path.insert(0, str(source_root))
    import timesfm
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
        TIMESFM_MODEL, revision=TIMESFM_REVISION, cache_dir=cache_dir,
        local_files_only=True, torch_compile=False,
    )
    model.compile(timesfm.ForecastConfig(
        max_context=128, max_horizon=20, per_core_batch_size=16,
        use_continuous_quantile_head=True, force_flip_invariance=False,
        infer_is_positive=True, fix_quantile_crossing=True,
    ))
    return model

def load_kronos(source_root: Path, cache_dir: Path):
    _verified_git_head(source_root, KRONOS_SOURCE_REVISION, "Kronos")
    sys.path.insert(0, str(source_root))
    import torch
    from model import Kronos, KronosPredictor, KronosTokenizer
    model_root = cache_dir / "models--NeoQuasar--Kronos-base" / "snapshots" / KRONOS_MODEL_REVISION
    tokenizer_root = cache_dir / "models--NeoQuasar--Kronos-Tokenizer-base" / "snapshots" / KRONOS_TOKENIZER_REVISION
    if sha256_file(model_root / "model.safetensors") != KRONOS_MODEL_SHA256:
        raise RuntimeError("Kronos model hash mismatch")
    if sha256_file(tokenizer_root / "model.safetensors") != KRONOS_TOKENIZER_SHA256:
        raise RuntimeError("Kronos tokenizer hash mismatch")
    tokenizer = KronosTokenizer.from_pretrained(str(tokenizer_root))
    model = Kronos.from_pretrained(str(model_root))
    torch.manual_seed(0)
    return KronosPredictor(model, tokenizer, device="cpu", max_context=512)


def _horizon_fields(prefix: str, values: list[float]) -> dict[str, float | None]:
    return {
        f"{prefix}_h{h}": float(values[h - 1]) if len(values) >= h else None
        for h in HORIZONS
    }


def generate(cases: list[dict[str, Any]], timesfm_model: Any, kronos_predictor: Any) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    import torch
    for case in cases:
        horizon = len(case["future_dates"])
        point, quantiles = timesfm_model.forecast(horizon=horizon, inputs=[case["timesfm_context"]])
        tf_point = (point[0, :horizon] / case["timesfm_current"] - 1.0).astype(float).tolist()
        tf_q10 = (quantiles[0, :horizon, 1] / case["timesfm_current"] - 1.0).astype(float).tolist()
        tf_q90 = (quantiles[0, :horizon, 9] / case["timesfm_current"] - 1.0).astype(float).tolist()
        torch.manual_seed(0)
        forecast = kronos_predictor.predict(
            case["kronos_history"], pd.Series(case["kronos_history"].index),
            pd.Series(case["future_dates"]), pred_len=horizon,
            T=KRONOS_T, top_p=KRONOS_TOP_P, sample_count=KRONOS_SAMPLE_COUNT, verbose=False,
        )
        if isinstance(forecast, list):
            forecast = forecast[0]
        kr = (forecast["close"].astype(float).to_numpy() / case["kronos_current"] - 1.0).tolist()
        disagreement = [float(a - b) for a, b in zip(tf_point, kr, strict=True)]
        row: dict[str, Any] = {
            "decision_time": case["decision_time"].isoformat(),
            "trade_date": case["trade_date"].isoformat(),
            "contract_id": case["contract_id"],
            "forecast_sessions": [stamp.isoformat() for stamp in case["future_dates"]],
            "timesfm_point_returns": tf_point,
            "timesfm_q10_returns": tf_q10,
            "timesfm_q90_returns": tf_q90,
            "kronos_close_returns": kr,
            "model_disagreement_returns": disagreement,
            "model_sign_disagreement_rate": float(np.mean(np.sign(tf_point) != np.sign(kr))),
            "model_disagreement_mean_abs": float(np.mean(np.abs(disagreement))),
            "timesfm_path_features": path_features(tf_point),
            "kronos_path_features": path_features(kr),
            "selection_use": "horizon_specific_direction_and_comparable_state_context",
        }
        row.update(_horizon_fields("timesfm_point_return", tf_point))
        row.update(_horizon_fields("timesfm_q10_return", tf_q10))
        row.update(_horizon_fields("timesfm_q90_return", tf_q90))
        row.update(_horizon_fields("kronos_close_return", kr))
        row.update(_horizon_fields("model_disagreement", disagreement))
        rows.append(row)
    return pd.DataFrame(rows)


def write_jsonl(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in frame.to_dict(orient="records"):
            handle.write(json.dumps(row, sort_keys=True) + "\n")

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PIT-native Block1 TimesFM/Kronos expert trajectories")
    parser.add_argument("--pit-state", type=Path, required=True)
    parser.add_argument("--canonical-csv", type=Path, required=True)
    parser.add_argument("--ohlcv-csv", type=Path, required=True)
    parser.add_argument("--timesfm-source-root", type=Path, required=True)
    parser.add_argument("--timesfm-cache-dir", type=Path, required=True)
    parser.add_argument("--kronos-source-root", type=Path, required=True)
    parser.add_argument("--kronos-cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    state, canonical, ohlcv = load_inputs(args.pit_state, args.canonical_csv, args.ohlcv_csv)
    cases = build_cases(state, canonical, ohlcv)
    timesfm_model = load_timesfm(args.timesfm_source_root, args.timesfm_cache_dir)
    kronos_predictor = load_kronos(args.kronos_source_root, args.kronos_cache_dir)
    frame = generate(cases, timesfm_model, kronos_predictor)
    write_jsonl(args.output, frame)
    manifest = {
        "schema_version": 1, "issue": 465, "block_id": "block-001",
        "row_count": len(frame), "pit_state_sha256": sha256_file(args.pit_state),
        "output_sha256": sha256_file(args.output), "timesfm_model": TIMESFM_MODEL,
        "timesfm_source_revision": TIMESFM_SOURCE_REVISION,
        "timesfm_revision": TIMESFM_REVISION, "timesfm_checkpoint_sha256": TIMESFM_SHA256,
        "kronos_source_revision": KRONOS_SOURCE_REVISION,
        "kronos_model_revision": KRONOS_MODEL_REVISION,
        "kronos_model_checkpoint_sha256": KRONOS_MODEL_SHA256,
        "kronos_tokenizer_revision": KRONOS_TOKENIZER_REVISION,
        "kronos_tokenizer_checkpoint_sha256": KRONOS_TOKENIZER_SHA256,
        "kronos_inference_profile": {"T": KRONOS_T, "top_p": KRONOS_TOP_P, "sample_count": KRONOS_SAMPLE_COUNT},
        "maximum_native_horizon_sessions": 20,
        "full_native_horizon_for_every_decision": True,
        "future_calendar_semantics": "known Block1 decision dates then synthetic UTC business-day continuation; no later-block market data",
        "canonical_history_sha256": sha256_file(args.canonical_csv),
        "ohlcv_history_sha256": sha256_file(args.ohlcv_csv),
        "history_max_trade_date": str(max(canonical["trade_date"].max(), ohlcv["trade_date"].max())),
        "protected_confirmation_accessed": False, "later_block_market_data_accessed": False,
        "selection_use": "horizon_specific_direction_and_comparable_state_context",
    }
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
