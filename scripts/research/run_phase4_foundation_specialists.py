from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from commodity.foundation_specialists import (
    SpecialistIdentity,
    probabilistic_interval_diagnostics,
    validate_specialist_features,
)
from commodity.kronos import resolve_kronos_artifacts, verify_kronos_source_checkout
from commodity.market_only_phase2 import evaluate_phase2_market_only

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_PATH = REPO_ROOT / "config" / "models.json"
TIMESFM_RESULT = REPO_ROOT / (
    "research/programmes/001-commodity-natural-gas/lines/"
    "005-timesfm-return-complementarity/experiments/001-timesfm-198-zero-shot-v1/result.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_artifact(cache: Path, repo_id: str, revision: str, filename: str) -> Path:
    slug = "models--" + repo_id.replace("/", "--")
    return cache / slug / "snapshots" / revision / filename


def _audit_model(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    env_name = cfg["checkpoint_cache_env"]
    cache_value = os.environ.get(env_name)
    artifact_cfg = cfg["checkpoint_artifacts"]["model"]
    artifact = None
    observed_hash = None
    if cache_value:
        candidate = _snapshot_artifact(
            Path(cache_value), cfg["model_id"], cfg["model_revision"], artifact_cfg["filename"]
        )
        if candidate.is_file():
            artifact = candidate
            observed_hash = _sha256(candidate)
    return {
        "name": name,
        "model_id": cfg["model_id"],
        "model_revision": cfg["model_revision"],
        "expected_sha256": artifact_cfg["sha256"],
        "cache_env": env_name,
        "cache_bound": bool(cache_value),
        "artifact_present": artifact is not None,
        "artifact_hash_match": observed_hash == artifact_cfg["sha256"],
        "observed_sha256": observed_hash,
        "license_status": cfg.get("license_status", "not_recorded_in_model_registry"),
        "pretraining_exposure": cfg.get("pretraining_exposure", "not_recorded_in_model_registry"),
    }


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def _checkpoint_writer_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(f"checkpoint writer already active: {path}") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def _read_partition_parts(checkpoint_root: Path, suffix: str) -> pd.DataFrame:
    paths = sorted((checkpoint_root / "reconstruction" / "partitions").glob(f"*-{suffix}.parquet"))
    if not paths:
        raise RuntimeError(f"no {suffix} reconstruction partitions found")
    return pd.concat((pd.read_parquet(path) for path in paths), ignore_index=True)


def _read_canonical_parts(checkpoint_root: Path) -> pd.DataFrame:
    frame = _read_partition_parts(checkpoint_root, "canonical").sort_values(
        ["trade_date", "contract_id"], ignore_index=True
    )
    for column in ("trade_date", "available_at"):
        frame[column] = pd.to_datetime(frame[column], utc=True)
    return frame


def _merge_specialist_at_phase2_origin(
    market_features: pd.DataFrame,
    session_path: pd.DataFrame,
    specialist: pd.DataFrame,
    *,
    identity: SpecialistIdentity,
    feature_columns: list[str],
) -> pd.DataFrame:
    if "trade_date" not in specialist.columns:
        raise ValueError("specialist frame missing columns: ['trade_date']")
    checked = validate_specialist_features(
        specialist,
        identity=identity,
        feature_columns=feature_columns,
    )
    checked["trade_date"] = pd.to_datetime(checked["trade_date"], utc=True, format="mixed")

    market = market_features.copy()
    market["trade_date"] = pd.to_datetime(market["trade_date"], utc=True)
    market["available_at"] = pd.to_datetime(market["available_at"], utc=True)
    selected = session_path[["trade_date", "contract_id"]].drop_duplicates().copy()
    selected["trade_date"] = pd.to_datetime(selected["trade_date"], utc=True)
    if selected["trade_date"].duplicated().any():
        raise ValueError("Phase-2 session path is not unique by selected trade date")

    expected = market.merge(selected, on="trade_date", how="left", validate="one_to_one")
    if expected["contract_id"].isna().any():
        raise ValueError("Phase-2 selected contract coverage is incomplete")
    keys = ["trade_date", "contract_id"]
    if checked.duplicated(keys).any():
        raise ValueError("specialist features are not unique at the Phase-2 PIT join grain")
    merged = expected.merge(
        checked[keys + ["prediction_time", *feature_columns]],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    if merged[feature_columns].isna().any().any() or merged["prediction_time"].isna().any():
        raise ValueError("specialist feature coverage is incomplete at the Phase-2 PIT join grain")
    expected_time = merged["available_at"].dt.floor("us")
    specialist_time = merged["prediction_time"].dt.floor("us")
    if not specialist_time.equals(expected_time):
        raise ValueError("specialist prediction time does not match the Phase-2 information cutoff")
    return merged.drop(columns=["prediction_time"])


def _timesfm_probabilistic_calibration(
    checkpoint_root: Path,
    feature_path: Path,
) -> dict[str, Any]:
    specialist = pd.read_csv(feature_path)
    specialist["trade_date"] = pd.to_datetime(specialist["trade_date"], utc=True, format="mixed")
    canonical = _read_canonical_parts(checkpoint_root)[["trade_date", "contract_id", "settle"]]
    if canonical.duplicated(["trade_date", "contract_id"]).any():
        raise RuntimeError("canonical settlements are not unique by trade date and contract")
    canonical = canonical.sort_values(["contract_id", "trade_date"]).copy()
    canonical["next_settle_same_contract"] = canonical.groupby("contract_id")["settle"].shift(-1)
    canonical["actual_return"] = canonical["next_settle_same_contract"] / canonical["settle"] - 1.0
    evaluation = specialist.merge(
        canonical[["trade_date", "contract_id", "actual_return"]],
        on=["trade_date", "contract_id"],
        how="left",
        validate="one_to_one",
    )
    if len(evaluation) != len(specialist):
        raise RuntimeError("TimesFM calibration join changed specialist origin count")
    evaluable = evaluation.loc[evaluation["actual_return"].notna()].copy()
    if evaluable.empty:
        raise RuntimeError("TimesFM calibration has no evaluable next-settlement outcomes")
    diagnostics = probabilistic_interval_diagnostics(
        actual=evaluable["actual_return"],
        lower=evaluable["timesfm_q10_return"],
        upper=evaluable["timesfm_q90_return"],
        lower_quantile=0.10,
        upper_quantile=0.90,
    )
    diagnostics.update(
        {
            "total_origins": len(evaluation),
            "excluded_no_next_same_contract_settle": int(
                evaluation["actual_return"].isna().sum()
            ),
            "target_semantics": "next canonical settlement return for the same contract",
        }
    )
    return diagnostics


def _timesfm_feature_cases(checkpoint_root: Path, *, context: int) -> list[dict[str, Any]]:
    features = _read_parquet(checkpoint_root / "inputs" / "features.parquet")
    session = _read_parquet(checkpoint_root / "inputs" / "session-path.parquet")
    canonical = _read_canonical_parts(checkpoint_root)
    features["trade_date"] = pd.to_datetime(features["trade_date"], utc=True)
    features["available_at"] = pd.to_datetime(features["available_at"], utc=True)
    session["trade_date"] = pd.to_datetime(session["trade_date"], utc=True)
    selected = session[["trade_date", "contract_id"]].drop_duplicates()
    if selected["trade_date"].duplicated().any():
        raise RuntimeError("Phase-2 session path is not unique by selected trade date")
    origins = features.merge(selected, on="trade_date", how="inner", validate="one_to_one")
    cases: list[dict[str, Any]] = []
    grouped = {name: group.sort_values("trade_date") for name, group in canonical.groupby("contract_id")}
    for row in origins.itertuples(index=False):
        history = grouped[str(row.contract_id)]
        eligible = history.loc[
            (history["trade_date"] <= row.trade_date)
            & (history["available_at"] <= row.available_at)
        ]
        if eligible.empty:
            raise RuntimeError(f"no PIT settlement history for {row.contract_id} at {row.trade_date}")
        values = eligible["settle"].astype(float).to_numpy()[-context:]
        if not np.isfinite(values).all() or np.any(values <= 0.0):
            raise RuntimeError("TimesFM settlement context contains invalid values")
        cases.append(
            {
                "prediction_time": row.available_at,
                "trade_date": row.trade_date,
                "contract_id": str(row.contract_id),
                "current_settle": float(values[-1]),
                "context": values.astype(np.float32),
            }
        )
    return cases


def _generate_timesfm_features(
    checkpoint_root: Path,
    runtime_root: Path,
    cache_dir: Path,
    output: Path,
    *,
    context: int,
    batch_size: int,
    max_origins: int | None,
) -> dict[str, Any]:
    sys.path.insert(0, str(runtime_root))
    import timesfm

    cfg = json.loads(MODELS_PATH.read_text(encoding="utf-8"))["models"]["timesfm_2_5"]
    cases = _timesfm_feature_cases(checkpoint_root, context=context)
    if max_origins is not None:
        cases = cases[:max_origins]
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
        cfg["model_id"], revision=cfg["model_revision"], cache_dir=cache_dir,
        local_files_only=True, torch_compile=False,
    )
    model.compile(
        timesfm.ForecastConfig(
            max_context=context, max_horizon=1, per_core_batch_size=batch_size,
            use_continuous_quantile_head=True, force_flip_invariance=False,
            infer_is_positive=True, fix_quantile_crossing=True,
        )
    )
    rows: list[dict[str, Any]] = []
    resumed_rows = 0
    if output.is_file():
        existing = pd.read_csv(output)
        expected_keys = [
            (pd.Timestamp(row["prediction_time"]).isoformat(), row["contract_id"])
            for row in cases[: len(existing)]
        ]
        observed_keys = [
            (pd.Timestamp(row.prediction_time).isoformat(), str(row.contract_id))
            for row in existing.itertuples(index=False)
        ]
        if observed_keys != expected_keys:
            raise RuntimeError("existing TimesFM checkpoint is not a valid origin-prefix")
        rows = existing.to_dict("records")
        resumed_rows = len(rows)
    for start in range(resumed_rows, len(cases), batch_size):
        batch = cases[start : start + batch_size]
        point, quantiles = model.forecast(horizon=1, inputs=[row["context"] for row in batch])
        for index, case in enumerate(batch):
            current = case["current_settle"]
            q = quantiles[index, 0]
            rows.append(
                {
                    "trade_date": pd.Timestamp(case["trade_date"]).isoformat(),
                    "prediction_time": pd.Timestamp(case["prediction_time"]).isoformat(),
                    "generated_at": pd.Timestamp(case["prediction_time"]).isoformat(),
                    "contract_id": case["contract_id"],
                    "timesfm_point_return": float(point[index, 0] / current - 1.0),
                    "timesfm_q10_return": float(q[1] / current - 1.0),
                    "timesfm_q90_return": float(q[9] / current - 1.0),
                    "timesfm_interval_width": float((q[9] - q[1]) / current),
                }
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(output, index=False, lineterminator="\n")
    return {
        "wallclock_execution_at_utc": _utc_iso(),
        "rows": len(rows),
        "resumed_rows": resumed_rows,
        "context": context,
        "generated_at_semantics": "historical_effective_information_cutoff; not wallclock inference time",
        "batch_size": batch_size,
        "output": str(output),
        "output_sha256": _sha256(output),
        "model_id": cfg["model_id"],
        "model_revision": cfg["model_revision"],
        "checkpoint_sha256": cfg["checkpoint_artifacts"]["model"]["sha256"],
        "protected_confirmation_accessed": False,
        "evidence_role": "retrospective_development_feature_generation",
    }


def _read_ohlcv_parts(checkpoint_root: Path) -> pd.DataFrame:
    frame = _read_partition_parts(checkpoint_root, "ohlcv").sort_values(
        ["contract_id", "trade_date"], ignore_index=True
    )
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True)
    return frame


def _kronos_feature_cases(checkpoint_root: Path, *, max_context: int) -> list[dict[str, Any]]:
    features = _read_parquet(checkpoint_root / "inputs" / "features.parquet")
    session = _read_parquet(checkpoint_root / "inputs" / "session-path.parquet")
    ohlcv = _read_ohlcv_parts(checkpoint_root)
    features["trade_date"] = pd.to_datetime(features["trade_date"], utc=True)
    features["available_at"] = pd.to_datetime(features["available_at"], utc=True)
    for column in ("trade_date", "next_trade_date"):
        session[column] = pd.to_datetime(session[column], utc=True)
    selected = session[["trade_date", "contract_id", "next_trade_date"]].drop_duplicates()
    if selected["trade_date"].duplicated().any():
        raise RuntimeError("Phase-2 session path is not unique by selected trade date")
    origins = features.merge(selected, on="trade_date", how="inner", validate="one_to_one")
    grouped = {name: group.sort_values("trade_date") for name, group in ohlcv.groupby("contract_id")}
    cases: list[dict[str, Any]] = []
    for row in origins.itertuples(index=False):
        history = grouped[str(row.contract_id)]
        eligible = history.loc[history["trade_date"] <= row.trade_date].tail(max_context).copy()
        if len(eligible) < 20:
            raise RuntimeError(f"Kronos same-contract PIT context below 20 rows for {row.contract_id}")
        values = eligible[["open", "high", "low", "close", "volume"]].astype(float)
        if not np.isfinite(values.to_numpy()).all() or (values[["open", "high", "low", "close"]] <= 0).any().any():
            raise RuntimeError("Kronos OHLCV context contains invalid values")
        cases.append(
            {
                "trade_date": row.trade_date,
                "prediction_time": row.available_at,
                "contract_id": str(row.contract_id),
                "current_close": float(values["close"].iloc[-1]),
                "future_timestamp": pd.Timestamp(row.next_trade_date),
                "history": values.set_axis(pd.DatetimeIndex(eligible["trade_date"])),
            }
        )
    return cases


def _generate_kronos_features(
    checkpoint_root: Path,
    source_root: Path,
    output: Path,
    *,
    batch_size: int,
    max_new_origins: int | None,
) -> dict[str, Any]:
    models = json.loads(MODELS_PATH.read_text(encoding="utf-8"))["models"]
    cfg = models["kronos_base"]
    source_revision = verify_kronos_source_checkout(source_root, cfg["source_revision"])
    artifacts = resolve_kronos_artifacts(cfg)
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    import torch
    from model import Kronos, KronosPredictor, KronosTokenizer

    tokenizer = KronosTokenizer.from_pretrained(artifacts["tokenizer"]["snapshot_path"])
    model = Kronos.from_pretrained(artifacts["model"]["snapshot_path"])
    predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=int(cfg["max_context"]))
    profile = json.loads(MODELS_PATH.read_text(encoding="utf-8"))["kronos_confirmation_profile"]["paper_backtest_inference"]
    cases = _kronos_feature_cases(checkpoint_root, max_context=int(cfg["max_context"]))
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
        case for case in cases
        if (pd.Timestamp(case["prediction_time"]).isoformat(), case["contract_id"]) not in existing_keys
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
                [pd.Series(pd.DatetimeIndex([case["future_timestamp"]])) for case in batch],
                pred_len=1,
                T=float(profile["T"]),
                top_p=float(profile["top_p"]),
                sample_count=int(profile["sample_count"]),
                verbose=False,
            )
            for case, forecast in zip(batch, forecasts, strict=True):
                current = case["current_close"]
                predicted_close = float(forecast["close"].iloc[0])
                predicted_high = float(forecast["high"].iloc[0])
                predicted_low = float(forecast["low"].iloc[0])
                rows.append(
                    {
                        "trade_date": pd.Timestamp(case["trade_date"]).isoformat(),
                        "prediction_time": pd.Timestamp(case["prediction_time"]).isoformat(),
                        "generated_at": pd.Timestamp(case["prediction_time"]).isoformat(),
                        "contract_id": case["contract_id"],
                        "kronos_close_return": predicted_close / current - 1.0,
                        "kronos_range_pct": (predicted_high - predicted_low) / current,
                    }
                )
            output.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(rows).sort_values(["prediction_time", "contract_id"]).to_csv(
                output, index=False, lineterminator="\n"
            )
    final = pd.read_csv(output) if output.is_file() else pd.DataFrame()
    complete = len(final) == len(cases)
    if max_new_origins is None and not complete:
        raise RuntimeError(f"Kronos feature checkpoint incomplete: {len(final)} of {len(cases)} rows")
    return {
        "wallclock_execution_at_utc": _utc_iso(),
        "rows": len(final),
        "total_origins": len(cases),
        "new_origins": len(final) - resumed_rows,
        "resumed_rows": resumed_rows,
        "complete": complete,
        "batch_size": batch_size,
        "source_revision": source_revision,
        "model_id": cfg["model_id"],
        "model_revision": cfg["model_revision"],
        "model_checkpoint_sha256": artifacts["model"]["artifact_sha256"],
        "tokenizer_revision": cfg["tokenizer_revision"],
        "tokenizer_checkpoint_sha256": artifacts["tokenizer"]["artifact_sha256"],
        "inference_profile": profile,
        "deterministic_seed": 0,
        "generated_at_semantics": "historical_effective_information_cutoff; not wallclock inference time",
        "output": str(output),
        "output_sha256": _sha256(output),
        "protected_confirmation_accessed": False,
        "evidence_role": "retrospective_development_feature_generation",
    }


def _evaluate_timesfm_increment(
    checkpoint_root: Path,
    feature_path: Path,
) -> dict[str, Any]:
    phase2_cfg = json.loads((REPO_ROOT / "config" / "phase2_market_only.json").read_text(encoding="utf-8"))
    market_features = _read_parquet(checkpoint_root / "inputs" / "features.parquet")
    session_path = _read_parquet(checkpoint_root / "inputs" / "session-path.parquet")
    specialist = pd.read_csv(feature_path)
    model_cfg = json.loads(MODELS_PATH.read_text(encoding="utf-8"))["models"]["timesfm_2_5"]
    identity = SpecialistIdentity(
        name="timesfm_2_5",
        model_id=model_cfg["model_id"],
        model_revision=model_cfg["model_revision"],
        checkpoint_sha256=model_cfg["checkpoint_artifacts"]["model"]["sha256"],
        pretraining_exposure=model_cfg["pretraining_exposure"],
        license_status="verified_for_research_use",
    )
    specialist_columns = [
        "timesfm_point_return",
        "timesfm_q10_return",
        "timesfm_q90_return",
        "timesfm_interval_width",
    ]
    model_feature_columns = [f"feature_{column}" for column in specialist_columns]
    enriched = _merge_specialist_at_phase2_origin(
        market_features,
        session_path,
        specialist,
        identity=identity,
        feature_columns=specialist_columns,
    ).rename(columns=dict(zip(specialist_columns, model_feature_columns, strict=True)))
    cfg = json.loads(json.dumps(phase2_cfg))
    core = list(cfg["feature_sets"]["core"])
    cfg["feature_sets"] = {"core": core, "core_timesfm": [*core, *model_feature_columns]}
    frozen = next(item for item in phase2_cfg["candidates"] if item["id"] == "histgb-core-v1")
    augmented = json.loads(json.dumps(frozen))
    augmented["id"] = "histgb-core-timesfm-v1"
    augmented["feature_set"] = "core_timesfm"
    augmented["simplicity_rank"] = int(frozen["simplicity_rank"]) + 1
    cfg["candidates"] = [json.loads(json.dumps(frozen)), augmented]
    evaluation = evaluate_phase2_market_only(session_path, enriched, cfg)
    aggregates = {row["candidate_id"]: row for row in evaluation["final_candidate_aggregate"]}
    baseline = aggregates["histgb-core-v1"]
    timesfm = aggregates["histgb-core-timesfm-v1"]
    expected_baseline = 26040.000000000036
    if abs(float(baseline["net_pnl_usd"]) - expected_baseline) > 1e-6:
        raise RuntimeError("Phase-4 control does not reproduce the frozen Phase-2 baseline")
    return {
        "comparison_role": "development_only_not_clean_historical_confirmation",
        "baseline": baseline,
        "timesfm_augmented": timesfm,
        "incremental_net_pnl_usd": float(timesfm["net_pnl_usd"]) - float(baseline["net_pnl_usd"]),
        "probabilistic_calibration": _timesfm_probabilistic_calibration(
            checkpoint_root, feature_path
        ),
        "winner": evaluation["final_baseline"],
        "winner_diagnostics": evaluation["diagnostics"],
        "nested_selection": evaluation["nested_selection"],
        "protected_confirmation_accessed": False,
    }


def _evaluate_foundation_variants(
    checkpoint_root: Path,
    timesfm_path: Path,
    kronos_path: Path,
) -> dict[str, Any]:
    phase2_cfg = json.loads((REPO_ROOT / "config" / "phase2_market_only.json").read_text(encoding="utf-8"))
    market_features = _read_parquet(checkpoint_root / "inputs" / "features.parquet")
    session_path = _read_parquet(checkpoint_root / "inputs" / "session-path.parquet")
    market_features["trade_date"] = pd.to_datetime(market_features["trade_date"], utc=True)
    models = json.loads(MODELS_PATH.read_text(encoding="utf-8"))["models"]

    frames: dict[str, pd.DataFrame] = {}
    definitions = {
        "timesfm": (
            timesfm_path,
            models["timesfm_2_5"],
            ["timesfm_point_return", "timesfm_q10_return", "timesfm_q90_return", "timesfm_interval_width"],
        ),
        "kronos": (
            kronos_path,
            models["kronos_base"],
            ["kronos_close_return", "kronos_range_pct"],
        ),
    }
    for name, (path, model_cfg, raw_columns) in definitions.items():
        frame = pd.read_csv(path)
        identity = SpecialistIdentity(
            name=name,
            model_id=model_cfg["model_id"],
            model_revision=model_cfg["model_revision"],
            checkpoint_sha256=model_cfg["checkpoint_artifacts"]["model"]["sha256"],
            pretraining_exposure=model_cfg["pretraining_exposure"],
            license_status="verified_for_research_use",
        )
        model_columns = [f"feature_{column}" for column in raw_columns]
        validated = _merge_specialist_at_phase2_origin(
            market_features,
            session_path,
            frame,
            identity=identity,
            feature_columns=raw_columns,
        )
        frames[name] = validated[["trade_date", *raw_columns]].rename(
            columns=dict(zip(raw_columns, model_columns, strict=True))
        )

    enriched = market_features.merge(frames["kronos"], on="trade_date", how="inner", validate="one_to_one")
    enriched = enriched.merge(frames["timesfm"], on="trade_date", how="inner", validate="one_to_one")
    if len(enriched) != len(market_features):
        raise RuntimeError("foundation specialist features do not cover the complete Phase-2 feature frame")

    core = list(phase2_cfg["feature_sets"]["core"])
    kronos_columns = [column for column in enriched.columns if column.startswith("feature_kronos_")]
    timesfm_columns = [column for column in enriched.columns if column.startswith("feature_timesfm_")]
    cfg = json.loads(json.dumps(phase2_cfg))
    cfg["feature_sets"] = {
        "core": core,
        "core_kronos": [*core, *kronos_columns],
        "core_timesfm": [*core, *timesfm_columns],
        "core_both": [*core, *kronos_columns, *timesfm_columns],
    }
    frozen = next(item for item in phase2_cfg["candidates"] if item["id"] == "histgb-core-v1")
    cfg["candidates"] = [json.loads(json.dumps(frozen))]
    for candidate_id, feature_set, rank in (
        ("histgb-core-kronos-v1", "core_kronos", 5),
        ("histgb-core-timesfm-v1", "core_timesfm", 5),
        ("histgb-core-both-v1", "core_both", 6),
    ):
        candidate = json.loads(json.dumps(frozen))
        candidate["id"] = candidate_id
        candidate["feature_set"] = feature_set
        candidate["simplicity_rank"] = rank
        cfg["candidates"].append(candidate)
    evaluation = evaluate_phase2_market_only(session_path, enriched, cfg)
    aggregates = {row["candidate_id"]: row for row in evaluation["final_candidate_aggregate"]}
    if abs(float(aggregates["histgb-core-v1"]["net_pnl_usd"]) - 26040.000000000036) > 1e-6:
        raise RuntimeError("Phase-4 four-way control does not reproduce the frozen Phase-2 baseline")
    return {
        "comparison_role": "development_only_not_clean_historical_confirmation",
        "aggregates": aggregates,
        "winner": evaluation["final_baseline"],
        "winner_diagnostics": evaluation["diagnostics"],
        "nested_selection": evaluation["nested_selection"],
        "remove_one_if_combined": {
            "remove_kronos": aggregates["histgb-core-timesfm-v1"],
            "remove_timesfm": aggregates["histgb-core-kronos-v1"],
        },
        "protected_confirmation_accessed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit and execute Phase-4 foundation specialists.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase2-checkpoint-root", type=Path)
    parser.add_argument("--timesfm-runtime-root", type=Path)
    parser.add_argument("--timesfm-cache-dir", type=Path)
    parser.add_argument("--timesfm-feature-output", type=Path)
    parser.add_argument("--timesfm-context", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-origins", type=int)
    parser.add_argument("--kronos-source-root", type=Path)
    parser.add_argument("--kronos-feature-output", type=Path)
    parser.add_argument("--kronos-batch-size", type=int, default=32)
    parser.add_argument("--kronos-max-new-origins", type=int)
    args = parser.parse_args()

    models = json.loads(MODELS_PATH.read_text(encoding="utf-8"))["models"]
    timesfm_result = json.loads(TIMESFM_RESULT.read_text(encoding="utf-8"))
    payload = {
        "schema_version": 1,
        "phase_issue": 358,
        "l3_authority_comment": 5628520758,
        "protected_confirmation_accessed": False,
        "specialists": [
            _audit_model("kronos_base", models["kronos_base"]),
            _audit_model("timesfm_2_5", models["timesfm_2_5"]),
        ],
        "prior_timesfm_scope": {
            "evidence_role": "consumed_development_background",
            "decision": timesfm_result["decision"],
            "fresh_confirmation": False,
        },
        "license_evidence": {
            "kronos": "MIT; NeoQuasar/Kronos-base model card and upstream project",
            "timesfm_2_5": "Apache-2.0; google-research/timesfm and model card",
            "timesfm_3": "excluded: pretrained weights non-commercial/non-production",
            "reviewed_on": "2026-09-11",
        },
    }
    timesfm_generation_requested = any(
        value is not None for value in (args.timesfm_runtime_root, args.timesfm_cache_dir)
    )
    if timesfm_generation_requested:
        generation_args = (
            args.phase2_checkpoint_root,
            args.timesfm_runtime_root,
            args.timesfm_cache_dir,
            args.timesfm_feature_output,
        )
        if not all(value is not None for value in generation_args):
            raise SystemExit("TimesFM generation requires checkpoint, runtime, cache and output paths")
        payload["timesfm_generation"] = _generate_timesfm_features(
            args.phase2_checkpoint_root,
            args.timesfm_runtime_root,
            args.timesfm_cache_dir,
            args.timesfm_feature_output,
            context=args.timesfm_context,
            batch_size=args.batch_size,
            max_origins=args.max_origins,
        )
        if args.max_origins is None:
            payload["timesfm_whole_system_evaluation"] = _evaluate_timesfm_increment(
                args.phase2_checkpoint_root,
                args.timesfm_feature_output,
            )
    elif (
        args.timesfm_feature_output is not None
        and args.timesfm_feature_output.is_file()
        and args.output.is_file()
    ):
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        generation = previous.get("timesfm_generation")
        if generation is None or generation.get("output_sha256") != _sha256(args.timesfm_feature_output):
            raise RuntimeError("existing TimesFM feature evidence does not match the reusable checkpoint")
        payload["timesfm_generation"] = generation
        if "timesfm_whole_system_evaluation" in previous:
            evaluation = previous["timesfm_whole_system_evaluation"]
            evaluation["probabilistic_calibration"] = _timesfm_probabilistic_calibration(
                args.phase2_checkpoint_root, args.timesfm_feature_output
            )
            payload["timesfm_whole_system_evaluation"] = evaluation
    kronos_args = (args.phase2_checkpoint_root, args.kronos_source_root, args.kronos_feature_output)
    if any(value is not None for value in kronos_args):
        if not all(value is not None for value in kronos_args):
            raise SystemExit("Kronos generation requires checkpoint, source and output paths")
        lock_path = args.kronos_feature_output.with_suffix(
            args.kronos_feature_output.suffix + ".writer.lock"
        )
        with _checkpoint_writer_lock(lock_path):
            payload["kronos_generation"] = _generate_kronos_features(
                args.phase2_checkpoint_root,
                args.kronos_source_root,
                args.kronos_feature_output,
                batch_size=args.kronos_batch_size,
                max_new_origins=args.kronos_max_new_origins,
            )
    if (
        args.phase2_checkpoint_root is not None
        and args.timesfm_feature_output is not None
        and args.kronos_feature_output is not None
        and args.timesfm_feature_output.is_file()
        and args.kronos_feature_output.is_file()
        and payload.get("kronos_generation", {}).get("complete") is True
    ):
        payload["four_way_whole_system_evaluation"] = _evaluate_foundation_variants(
            args.phase2_checkpoint_root,
            args.timesfm_feature_output,
            args.kronos_feature_output,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
