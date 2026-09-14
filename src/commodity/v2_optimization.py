from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


class V2OptimizationError(ValueError):
    """Raised when a V2 optimization evidence or execution contract is violated."""


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256_payload(payload: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class V2Registry:
    payload: dict[str, Any]

    @property
    def registry_id(self) -> str:
        return str(self.payload["registry_id"])

    def assert_search_evidence(self, evidence_class: str) -> None:
        boundary = self.payload["evidence_boundary"]
        prohibited = {str(item) for item in boundary["prohibited_for_search"]}
        allowed = {str(item) for item in boundary["allowed_for_search"]}
        if evidence_class in prohibited:
            raise V2OptimizationError(
                f"evidence class {evidence_class!r} is prohibited for V2 search"
            )
        if evidence_class not in allowed:
            raise V2OptimizationError(
                f"evidence class {evidence_class!r} is not allowed for V2 search"
            )

    def variable(self, dotted_name: str) -> Mapping[str, Any]:
        try:
            family, variable = dotted_name.split(".", maxsplit=1)
            definition = self.payload["variables"][family][variable]
        except (ValueError, KeyError, TypeError) as exc:
            raise V2OptimizationError(
                f"unknown V2 registry variable: {dotted_name}"
            ) from exc
        if not isinstance(definition, Mapping):
            raise V2OptimizationError(f"invalid V2 registry variable: {dotted_name}")
        return definition


def load_v2_registry(path: Path) -> V2Registry:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not payload.get("registry_id"):
        raise V2OptimizationError("unsupported or incomplete V2 registry")
    boundary = payload.get("evidence_boundary")
    if not isinstance(boundary, dict):
        raise V2OptimizationError("V2 registry is missing evidence_boundary")
    if boundary.get("v1_immutable") is not True:
        raise V2OptimizationError("V2 registry must preserve immutable V1")
    allowed = boundary.get("allowed_for_search")
    prohibited = boundary.get("prohibited_for_search")
    if not isinstance(allowed, list) or not isinstance(prohibited, list):
        raise V2OptimizationError("V2 registry search evidence classes are invalid")
    if set(map(str, allowed)) & set(map(str, prohibited)):
        raise V2OptimizationError("V2 registry evidence classes overlap")
    if not isinstance(payload.get("variables"), dict):
        raise V2OptimizationError("V2 registry variables are missing")
    return V2Registry(payload=payload)


def _validate_axis_value(name: str, definition: Mapping[str, Any], value: object) -> None:
    candidates = definition.get("candidates")
    if isinstance(candidates, list):
        if value not in candidates:
            raise V2OptimizationError(
                f"{name} value {value!r} is not a declared candidate"
            )
        return
    if "min" in definition and "max" in definition:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise V2OptimizationError(f"{name} requires a numeric value")
        if not float(definition["min"]) <= float(value) <= float(definition["max"]):
            raise V2OptimizationError(f"{name} value {value!r} is outside declared bounds")
        return
    raise V2OptimizationError(f"{name} has no executable candidate set or bounds")


def expand_search_axes(
    registry: V2Registry,
    axes: Mapping[str, Sequence[object]],
    *,
    max_trials: int,
) -> list[dict[str, object]]:
    if max_trials < 1:
        raise V2OptimizationError("max_trials must be positive")
    if not axes:
        raise V2OptimizationError("at least one V2 search axis is required")
    ordered_names = sorted(axes)
    ordered_values: list[list[object]] = []
    for name in ordered_names:
        definition = registry.variable(name)
        values = list(axes[name])
        if not values:
            raise V2OptimizationError(f"{name} search axis is empty")
        for value in values:
            _validate_axis_value(name, definition, value)
        ordered_values.append(values)
    combinations = math.prod(len(values) for values in ordered_values)
    if combinations > max_trials:
        raise V2OptimizationError(
            f"search grid has {combinations} trials, exceeding budget {max_trials}"
        )
    present = set(ordered_names)
    interactions = [
        str(item)
        for item in registry.payload.get("mandatory_interactions", [])
        if set(str(item).split("×")).issubset(present)
    ]
    configs: list[dict[str, object]] = []
    for values in itertools.product(*ordered_values):
        config = dict(zip(ordered_names, values, strict=True))
        config["_interactions_covered"] = interactions
        configs.append(config)
    return configs


def build_trial_id(
    config: Mapping[str, object],
    *,
    seed: int,
    dataset_id: str,
    code_id: str,
    evidence_class: str,
) -> str:
    payload = {
        "config": dict(config),
        "seed": int(seed),
        "dataset_id": str(dataset_id),
        "code_id": str(code_id),
        "evidence_class": str(evidence_class),
    }
    return _sha256_payload(payload)


class TrialLedger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _records(self) -> dict[str, dict[str, object]]:
        records: dict[str, dict[str, object]] = {}
        if not self.path.exists():
            return records
        for line_number, raw in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise V2OptimizationError(
                    f"trial ledger contains invalid JSON at line {line_number}"
                ) from exc
            trial_id = str(record.get("trial_id", ""))
            if not trial_id:
                raise V2OptimizationError("trial ledger record is missing trial_id")
            if trial_id in records and records[trial_id] != record:
                raise V2OptimizationError(
                    f"trial ledger has conflicting duplicate {trial_id}"
                )
            records[trial_id] = record
        return records

    def completed_trial_ids(self) -> set[str]:
        return {
            trial_id
            for trial_id, record in self._records().items()
            if record.get("status") == "complete"
        }

    def append(self, record: Mapping[str, object]) -> bool:
        payload = dict(record)
        trial_id = str(payload.get("trial_id", ""))
        if not trial_id:
            raise V2OptimizationError("trial record requires trial_id")
        existing = self._records().get(trial_id)
        if existing is not None:
            if existing == payload:
                return False
            raise V2OptimizationError(
                f"trial ledger conflicting duplicate for {trial_id}"
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(_canonical_json_bytes(payload).decode("utf-8") + "\n")
            handle.flush()
        return True


def _max_drawdown_fraction(net_pnl: pd.Series, starting_capital_usd: float) -> float:
    equity = float(starting_capital_usd) + net_pnl.cumsum()
    running_peak = equity.cummax()
    drawdown = (running_peak - equity) / running_peak
    return float(drawdown.max()) if len(drawdown) else 0.0


def _trade_count(position: pd.Series) -> int:
    values = position.to_numpy(dtype=float)
    if len(values) == 0:
        return 0
    count = int(values[0] != 0.0)
    count += int(np.count_nonzero(values[1:] != values[:-1]))
    return count


def score_monthly_path(
    path: pd.DataFrame,
    *,
    starting_capital_usd: float,
    latest_allowed_timestamp: object | None = None,
) -> dict[str, float | int]:
    if starting_capital_usd <= 0.0:
        raise V2OptimizationError("starting capital must be positive")
    if not isinstance(path.index, pd.DatetimeIndex):
        raise V2OptimizationError("scored path requires a DatetimeIndex")
    if path.index.has_duplicates or not path.index.is_monotonic_increasing:
        raise V2OptimizationError("scored path must be chronological and unique")
    index = pd.to_datetime(path.index, utc=True, errors="coerce")
    if index.isna().any():
        raise V2OptimizationError("scored path contains invalid timestamps")
    if latest_allowed_timestamp is not None:
        cutoff = pd.Timestamp(latest_allowed_timestamp)
        cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
        if len(index) and index.max() > cutoff:
            raise V2OptimizationError("scored path crosses the allowed evidence cutoff")

    required = {
        "net_pnl_usd", "transaction_cost_usd", "turnover",
        "gross_exposure_fraction", "net_exposure_fraction", "leverage", "position",
    }
    missing = sorted(required - set(path.columns))
    if missing:
        raise V2OptimizationError(f"scored path is missing columns: {missing}")
    frame = path.loc[:, sorted(required)].copy()
    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
    if not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise V2OptimizationError("scored path values must be finite")

    net = frame["net_pnl_usd"]
    month = index.tz_convert(None).to_period("M")
    monthly_pnl = net.groupby(month).sum()
    monthly_return = monthly_pnl / float(starting_capital_usd)
    positive = monthly_pnl[monthly_pnl > 0.0]
    positive_total = float(positive.sum())
    concentration = (
        float(positive.max() / positive_total) if positive_total > 0.0 else 0.0
    )
    position = frame["position"]
    long_pnl = float(net[position > 0.0].sum())
    short_pnl = float(net[position < 0.0].sum())
    flat_pnl = float(net[position == 0.0].sum())
    monthly_std = float(monthly_return.std(ddof=0)) if len(monthly_return) else 0.0

    return {
        "session_count": len(frame),
        "month_count": len(monthly_return),
        "total_net_pnl_usd": float(net.sum()),
        "mean_monthly_net_return": float(monthly_return.mean()),
        "median_monthly_net_return": float(monthly_return.median()),
        "worst_monthly_net_return": float(monthly_return.min()),
        "best_monthly_net_return": float(monthly_return.max()),
        "profitable_month_rate": float((monthly_return > 0.0).mean()),
        "monthly_net_return_std": monthly_std,
        "max_drawdown_fraction": _max_drawdown_fraction(net, starting_capital_usd),
        "transaction_cost_usd": float(frame["transaction_cost_usd"].sum()),
        "turnover": float(frame["turnover"].sum()),
        "max_gross_exposure_fraction": float(frame["gross_exposure_fraction"].abs().max()),
        "max_abs_net_exposure_fraction": float(frame["net_exposure_fraction"].abs().max()),
        "max_leverage": float(frame["leverage"].abs().max()),
        "trade_count": _trade_count(position),
        "long_net_pnl_usd": long_pnl,
        "short_net_pnl_usd": short_pnl,
        "flat_net_pnl_usd": flat_pnl,
        "largest_positive_month_profit_fraction": concentration,
    }


def bind_frozen_v1(path: Path) -> dict[str, str]:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    boundary = payload.get("execution_boundary", {})
    if boundary.get("v1_frozen_unchanged") is not True:
        raise V2OptimizationError("V1 comparator is not frozen unchanged")
    benchmark_id = str(payload.get("benchmark_id", ""))
    if not benchmark_id:
        raise V2OptimizationError("V1 comparator is missing benchmark_id")
    return {
        "benchmark_id": benchmark_id,
        "sha256": _sha256_file(path),
    }


def _phase2_ledger_for_monthly_score(ledger: pd.DataFrame) -> pd.DataFrame:
    required = {
        "trade_date", "target_position", "net_pnl_usd",
        "transaction_cost_usd", "execution_side_count",
    }
    missing = sorted(required - set(ledger.columns))
    if missing:
        raise V2OptimizationError(f"Phase-2 pilot ledger is missing columns: {missing}")
    index = pd.to_datetime(ledger["trade_date"], utc=True, errors="coerce")
    if index.isna().any():
        raise V2OptimizationError("Phase-2 pilot ledger has invalid trade dates")
    position = pd.to_numeric(ledger["target_position"], errors="raise").to_numpy(dtype=float)
    normalized = pd.DataFrame(
        {
            "net_pnl_usd": pd.to_numeric(ledger["net_pnl_usd"], errors="raise").to_numpy(dtype=float),
            "transaction_cost_usd": pd.to_numeric(ledger["transaction_cost_usd"], errors="raise").to_numpy(dtype=float),
            "turnover": pd.to_numeric(ledger["execution_side_count"], errors="raise").to_numpy(dtype=float),
            "gross_exposure_fraction": np.abs(position),
            "net_exposure_fraction": position,
            "leverage": np.abs(position),
            "position": position,
        },
        index=index,
    )
    return normalized.sort_index(kind="stable")


def run_phase2_development_pilot(
    *,
    registry_path: Path,
    phase2_config_path: Path,
    databento_root: Path,
    trial_ledger_path: Path,
    candidate_ids: Sequence[str],
    checkpoint_dir: Path | None = None,
    heartbeat_seconds: float = 30.0,
    start_date: str = "2022-01-01",
    end_date: str = "2022-12-31",
) -> dict[str, object]:
    """Run a small pre-2023 harness pilot without changing Phase-2/V1 authority."""
    from commodity.market_only_phase2 import (
        _build_segmented_decision_origins,
        _canonicalize_one_origin_per_fill,
        _load_inherited_risk_and_costs,
        _score_candidate_window,
        build_phase2_inputs,
        reconstruct_market_history,
        validate_phase2_config,
    )
    from commodity.phase2_runtime import Phase2CheckpointStore, Phase2Telemetry

    registry = load_v2_registry(registry_path)
    registry.assert_search_evidence("development")
    cfg = json.loads(Path(phase2_config_path).read_text(encoding="utf-8"))
    validate_phase2_config(cfg)
    cutoff = pd.Timestamp(cfg["evidence_boundary"]["last_allowed_trade_date"], tz="UTC")
    requested_end = pd.Timestamp(end_date, tz="UTC")
    if requested_end > cutoff or cutoff > pd.Timestamp("2022-12-31", tz="UTC"):
        raise V2OptimizationError("V2 pilot must remain inside pre-2023 development evidence")

    candidates_by_id = {str(item["id"]): item for item in cfg["candidates"]}
    if not candidate_ids or any(item not in candidates_by_id for item in candidate_ids):
        raise V2OptimizationError("V2 pilot references unknown Phase-2 candidate IDs")
    selected_candidates = [candidates_by_id[item] for item in candidate_ids]
    model_map = {
        "zero": "naive",
        "expanding_mean": "expanding_mean",
        "ridge": "ridge",
        "hist_gb": "hist_gb",
    }
    for candidate in selected_candidates:
        model_id = model_map.get(str(candidate["model"]))
        if model_id is None:
            raise V2OptimizationError("V2 pilot candidate is outside registry model family")
        _validate_axis_value("model.model_id", registry.variable("model.model_id"), model_id)

    telemetry_path = None if checkpoint_dir is None else Path(checkpoint_dir) / "telemetry.jsonl"
    telemetry = Phase2Telemetry(
        telemetry_path,
        heartbeat_seconds=heartbeat_seconds,
        echo=True,
    )
    checkpoint_store = (
        None if checkpoint_dir is None else Phase2CheckpointStore(Path(checkpoint_dir), telemetry)
    )
    lock_context = nullcontext() if checkpoint_store is None else checkpoint_store.run_lock()
    with lock_context:
        canonical, market, execution_bars, provenance = reconstruct_market_history(
            Path(databento_root),
            cfg,
            checkpoint_store=checkpoint_store,
            telemetry=telemetry,
        )
        input_identity = {
            "cache_version": 1,
            "registry_id": registry.registry_id,
            "phase2_config_sha256": _sha256_file(Path(phase2_config_path)),
            "source_provenance_sha256": str(provenance["provenance_sha256"]),
            "v2_optimization_code_sha256": _sha256_file(Path(__file__)),
        }
        session_path = None
        features = None
        if checkpoint_store is not None:
            session_path = checkpoint_store.load_frame("v2-pilot/inputs/session-path", input_identity)
            features = checkpoint_store.load_frame("v2-pilot/inputs/features", input_identity)
        if session_path is None or features is None:
            with telemetry.stage("v2_pilot_input_build"):
                session_path, features = build_phase2_inputs(
                    canonical, market, execution_bars, cfg, telemetry=telemetry
                )
            if checkpoint_store is not None:
                checkpoint_store.save_frame(
                    "v2-pilot/inputs/session-path", session_path, input_identity
                )
                checkpoint_store.save_frame("v2-pilot/inputs/features", features, input_identity)

    horizon = int(cfg["execution_contract"]["horizon_sessions"])
    origins, _ = _build_segmented_decision_origins(
        session_path, features, horizon_sessions=horizon
    )
    origins, canonicalization = _canonicalize_one_origin_per_fill(origins)
    risk, costs = _load_inherited_risk_and_costs(cfg)
    ledger = TrialLedger(trial_ledger_path)
    completed = ledger.completed_trial_ids()
    code_id = _sha256_file(Path(__file__))
    dataset_id = str(provenance["provenance_sha256"])
    executed = 0
    skipped = 0
    records: list[dict[str, object]] = []
    for candidate in selected_candidates:
        config = {
            "phase2_candidate_id": str(candidate["id"]),
            "model.model_id": model_map[str(candidate["model"])],
            "target.horizon_sessions": horizon,
            "window": {"start": start_date, "end": end_date},
        }
        trial_id = build_trial_id(
            config,
            seed=0,
            dataset_id=dataset_id,
            code_id=code_id,
            evidence_class="development",
        )
        if trial_id in completed:
            skipped += 1
            continue
        legacy_score, _, phase2_ledger = _score_candidate_window(
            origins,
            session_path,
            candidate,
            cfg,
            costs["base"],
            risk,
            start_date=start_date,
            end_date=end_date,
        )
        monthly_score = score_monthly_path(
            _phase2_ledger_for_monthly_score(phase2_ledger),
            starting_capital_usd=float(risk.capital_usd),
            latest_allowed_timestamp=cutoff,
        )
        record: dict[str, object] = {
            "trial_id": trial_id,
            "status": "complete",
            "evidence_class": "development",
            "registry_id": registry.registry_id,
            "dataset_id": dataset_id,
            "code_id": code_id,
            "seed": 0,
            "config": config,
            "monthly_score": monthly_score,
            "legacy_phase2_score": {
                "net_pnl_usd": legacy_score["net_pnl_usd"],
                "max_drawdown_fraction": legacy_score["max_drawdown_fraction"],
                "transaction_cost_usd": legacy_score["transaction_cost_usd"],
            },
        }
        ledger.append(record)
        records.append(record)
        executed += 1

    return {
        "status": "complete",
        "evidence_class": "development",
        "registry_id": registry.registry_id,
        "cutoff": cutoff.date().isoformat(),
        "pilot_window": {"start": start_date, "end": end_date},
        "candidate_ids": list(candidate_ids),
        "executed_trials": executed,
        "skipped_completed_trials": skipped,
        "trial_count_after_run": len(ledger._records()),
        "source_provenance_sha256": dataset_id,
        "origin_canonicalization": canonicalization,
        "new_records": records,
    }
