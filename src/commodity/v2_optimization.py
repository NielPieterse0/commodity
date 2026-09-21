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


def load_issue425_search_plan(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("issue") != 425:
        raise V2OptimizationError("unsupported issue-425 search plan")
    if payload.get("status") != "preregistered_before_issue425_scoring":
        raise V2OptimizationError("issue-425 search plan is not preregistered")
    if payload.get("evidence_class") != "development":
        raise V2OptimizationError("issue-425 search must use development evidence")
    cutoff = pd.Timestamp(str(payload.get("latest_allowed_trade_date")), tz="UTC")
    if cutoff > pd.Timestamp("2022-12-31", tz="UTC"):
        raise V2OptimizationError("issue-425 search plan crosses protected evidence")
    if not isinstance(payload.get("search_stages"), list):
        raise V2OptimizationError("issue-425 search plan is missing search stages")
    return payload


def _issue425_plan_axes(plan: Mapping[str, Any]) -> dict[str, list[object]]:
    axes: dict[str, list[object]] = {}
    for stage in plan.get("search_stages", []):
        stage_axes = stage.get("axes", {}) if isinstance(stage, Mapping) else {}
        if not isinstance(stage_axes, Mapping):
            raise V2OptimizationError("issue-425 stage axes are invalid")
        for name, raw_values in stage_axes.items():
            values = list(raw_values) if isinstance(raw_values, list) else []
            if not values:
                raise V2OptimizationError(f"issue-425 axis {name} is empty")
            if name in axes and axes[name] != values:
                raise V2OptimizationError(f"issue-425 axis {name} is inconsistent")
            axes[str(name)] = values
    return axes


def validate_issue425_search_plan(
    registry: V2Registry, plan: Mapping[str, Any]
) -> dict[str, Any]:
    registry.assert_search_evidence(str(plan.get("evidence_class")))
    axes = _issue425_plan_axes(plan)
    for name, values in axes.items():
        definition = registry.variable(name)
        for value in values:
            _validate_axis_value(name, definition, value)

    exact_candidate_axes = {
        "target.target_role",
        "target.aggregation",
        "model.training_window",
        "data.lookback_sessions",
        "transforms.return_transform",
        "transforms.scaling",
        "transforms.normalization_window_sessions",
        "transforms.winsor_quantile",
        "transforms.lag_sessions",
        "transforms.rolling_stat_window_sessions",
    }
    for name in exact_candidate_axes:
        declared = registry.variable(name).get("candidates")
        if isinstance(declared, list) and set(axes.get(name, [])) != set(declared):
            raise V2OptimizationError(f"issue-425 axis {name} lacks full candidate coverage")
    market_families = {"market", "market_structure", "calendar_seasonality"}
    if set(axes.get("data.feature_family_subset", [])) != market_families:
        raise V2OptimizationError("issue-425 must cover the bounded market-state feature families")
    if axes.get("target.horizon_sessions") != list(range(1, 21)):
        raise V2OptimizationError("issue-425 horizon search must cover every session 1..20")
    required_interactions = {
        "target.target_role×target.horizon_sessions",
        "model.model_id×data.feature_family_subset",
        "decision.entry_threshold_quantile×target.horizon_sessions",
    }
    registered: set[str] = set()
    for stage in plan.get("search_stages", []):
        if not isinstance(stage, Mapping):
            continue
        for item in stage.get("required_interactions", []):
            if isinstance(item, str):
                registered.add(item)
    missing = required_interactions - registered
    if missing:
        raise V2OptimizationError(
            f"issue-425 plan is missing required interactions: {sorted(missing)}"
        )
    return {
        "latest_allowed_trade_date": str(plan["latest_allowed_trade_date"]),
        "axis_count": len(axes),
        "required_interactions": required_interactions,
    }


_ISSUE425_MARKET_COLUMNS = (
    "feature_ret_1", "feature_ret_5", "feature_ret_20",
    "feature_vol_5", "feature_vol_20", "feature_range_pct",
    "feature_ma_gap_5", "feature_ma_gap_20",
    "feature_selected_dte", "feature_roll_event",
)
_ISSUE425_CALENDAR_COLUMNS = ("feature_season_sin", "feature_season_cos")


def _issue425_family_columns(frame: pd.DataFrame, family: str) -> list[str]:
    if family == "market":
        columns = [column for column in _ISSUE425_MARKET_COLUMNS if column in frame]
    elif family == "market_structure":
        columns = sorted(column for column in frame if column.startswith("feature_curve_"))
    elif family == "calendar_seasonality":
        columns = [column for column in _ISSUE425_CALENDAR_COLUMNS if column in frame]
    else:
        raise V2OptimizationError(f"unsupported issue-425 feature family: {family}")
    if not columns:
        raise V2OptimizationError(f"issue-425 feature family {family} has no columns")
    return columns


def _issue425_return_transform(frame: pd.DataFrame, mode: str) -> None:
    return_columns = [column for column in frame if column.startswith("feature_ret_")]
    if mode == "log_return":
        return
    if mode == "simple_return":
        for column in return_columns:
            frame[column] = np.expm1(pd.to_numeric(frame[column], errors="raise"))
        return
    if mode == "level_difference":
        reference = "feature_curve_log_settle_m1"
        if reference not in frame:
            raise V2OptimizationError("level_difference requires front-curve price level")
        price = np.exp(pd.to_numeric(frame[reference], errors="raise"))
        for column in return_columns:
            log_return = pd.to_numeric(frame[column], errors="raise")
            frame[column] = price * (1.0 - np.exp(-log_return))
        return
    raise V2OptimizationError(f"unsupported issue-425 return transform: {mode}")


def _issue425_rolling_scale(
    values: pd.DataFrame, mode: str, window: int
) -> pd.DataFrame:
    if mode == "none":
        return values
    history = values.shift(1).rolling(window=window, min_periods=window)
    if mode == "zscore_rolling":
        center = history.mean()
        spread = history.std(ddof=0).replace(0.0, np.nan)
    elif mode == "robust_rolling":
        center = history.median()
        lower = history.quantile(0.25)
        upper = history.quantile(0.75)
        spread = (upper - lower).replace(0.0, np.nan)
    else:
        raise V2OptimizationError(f"unsupported issue-425 scaling: {mode}")
    return (values - center) / spread


def prepare_issue425_features(
    features: pd.DataFrame, config: Mapping[str, object]
) -> tuple[pd.DataFrame, list[str]]:
    required = {"trade_date", "available_at"}
    if not required.issubset(features.columns):
        raise V2OptimizationError("issue-425 features lack time columns")
    frame = features.copy().sort_values("trade_date", kind="stable")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True, errors="raise")
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True, errors="raise")
    _issue425_return_transform(frame, str(config["return_transform"]))
    family = str(config["feature_family_subset"])
    base_columns = _issue425_family_columns(frame, family)
    numeric = frame[base_columns].apply(pd.to_numeric, errors="raise").astype(float)
    lookback = int(config["lookback_sessions"])
    lag = int(config["lag_sessions"])
    stat_window = int(config["rolling_stat_window_sessions"])
    norm_window = int(config["normalization_window_sessions"])
    winsor = float(config["winsor_quantile"])
    if min(lookback, lag, stat_window, norm_window) < 1:
        raise V2OptimizationError("issue-425 transform windows must be positive")
    if not 0.0 <= winsor < 0.5:
        raise V2OptimizationError("issue-425 winsor quantile is invalid")

    if winsor > 0.0:
        shifted = numeric.shift(1)
        history = shifted.rolling(
            window=lookback, min_periods=min(20, lookback)
        )
        lower = history.quantile(winsor)
        upper = history.quantile(1.0 - winsor)
        numeric = numeric.clip(lower=lower, upper=upper, axis=1)

    lagged = numeric.shift(lag)
    history = numeric.shift(1).rolling(window=stat_window, min_periods=stat_window)
    rolling_mean = history.mean().add_suffix(f"__mean{stat_window}")
    rolling_std = history.std(ddof=0).add_suffix(f"__std{stat_window}")
    derived = pd.concat([lagged, rolling_mean, rolling_std], axis=1)
    scaled = _issue425_rolling_scale(
        derived, str(config["scaling"]), norm_window
    )
    output_columns = list(scaled.columns)
    output = pd.concat(
        [frame[["trade_date", "available_at"]], scaled], axis=1
    ).replace([np.inf, -np.inf], np.nan)
    output = output.dropna(subset=output_columns).copy()
    if output.empty:
        raise V2OptimizationError("issue-425 transforms produced no complete rows")
    if not np.isfinite(output[output_columns].to_numpy(dtype=float)).all():
        raise V2OptimizationError("issue-425 transformed features are non-finite")
    return output, output_columns


def build_issue425_target(
    moves: Sequence[float],
    *,
    role: str,
    aggregation: str,
    round_trip_per_mmbtu: float,
) -> dict[str, object]:
    values = np.asarray(list(moves), dtype=float)
    if not len(values) or not np.isfinite(values).all():
        raise V2OptimizationError("issue-425 target moves must be finite and non-empty")
    cumulative = float(values.sum())
    terminal = float(values[-1])
    norm = float(np.sqrt(np.square(values).sum()))
    path_summary = 0.0 if norm == 0.0 else cumulative / norm
    if aggregation == "terminal":
        aggregate = terminal
    elif aggregation == "cumulative":
        aggregate = cumulative
    elif aggregation == "path_summary":
        aggregate = path_summary
    else:
        raise V2OptimizationError(f"unsupported issue-425 aggregation: {aggregation}")
    realized_volatility = float(np.sqrt(np.mean(np.square(values))))
    direction = float(np.sign(aggregate))
    if role == "return":
        target_value = aggregate
        eligible = True
        translation = "forecast_sign_horizon_hold"
    elif role == "direction":
        target_value = direction
        eligible = True
        translation = "forecast_sign_horizon_hold"
    elif role == "volatility":
        target_value = realized_volatility
        eligible = False
        translation = "diagnostic_only_flat"
    elif role == "direction_plus_volatility":
        target_value = direction * realized_volatility
        eligible = True
        translation = "forecast_sign_horizon_hold"
    elif role == "cost_aware_utility":
        excess = max(abs(cumulative) - float(round_trip_per_mmbtu), 0.0)
        target_value = float(np.sign(cumulative)) * excess
        eligible = True
        translation = "forecast_sign_horizon_hold"
    else:
        raise V2OptimizationError(f"unsupported issue-425 target role: {role}")
    return {
        "target_value": float(target_value),
        "champion_eligible": eligible,
        "economic_translation": translation,
        "aggregate_value": float(aggregate),
        "realized_cumulative_move_per_mmbtu": cumulative,
        "realized_volatility_per_mmbtu": realized_volatility,
    }


def select_issue425_candidate(
    rows: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    eligible = [row for row in rows if bool(row.get("champion_eligible", True))]
    if not eligible:
        raise V2OptimizationError("issue-425 selection has no champion-eligible rows")

    def key(row: Mapping[str, object]) -> tuple[float, float, float, int, str]:
        score = row.get("monthly_score")
        if not isinstance(score, Mapping):
            raise V2OptimizationError("issue-425 candidate lacks monthly score")
        return (
            -float(score["mean_monthly_net_return"]),
            float(score["max_drawdown_fraction"]),
            float(score["transaction_cost_usd"]),
            int(row.get("complexity_rank", 999)),
            str(row.get("candidate_id", "")),
        )

    return min(eligible, key=key)


def _attach_issue425_targets(
    origins: pd.DataFrame,
    session_path: pd.DataFrame,
    *,
    horizon_sessions: int,
    role: str,
    aggregation: str,
    round_trip_per_mmbtu: float,
) -> pd.DataFrame:
    if origins.empty:
        raise V2OptimizationError("issue-425 target reconstruction has no origins")
    segments = {
        int(segment_id): part.sort_values("trade_date", kind="stable").reset_index(drop=True)
        for segment_id, part in session_path.groupby("segment_id", sort=False)
    }
    records: list[dict[str, object]] = []
    for _, origin in origins.iterrows():
        segment_id = int(origin.get("segment_id", 0))
        segment = segments.get(segment_id)
        if segment is None:
            raise V2OptimizationError("issue-425 origin references an unknown segment")
        fill_index = int(origin["fill_index"])
        moves = segment.iloc[fill_index : fill_index + horizon_sessions][
            "path_move_per_mmbtu"
        ].to_numpy(dtype=float)
        if len(moves) != horizon_sessions or not np.isfinite(moves).all():
            raise V2OptimizationError("issue-425 target path cannot be reconstructed")
        target = build_issue425_target(
            moves,
            role=role,
            aggregation=aggregation,
            round_trip_per_mmbtu=round_trip_per_mmbtu,
        )
        record = origin.to_dict()
        record.update(
            {
                "issue425_target": target["target_value"],
                "issue425_aggregate": target["aggregate_value"],
                "issue425_realized_cumulative": target[
                    "realized_cumulative_move_per_mmbtu"
                ],
                "issue425_realized_volatility": target[
                    "realized_volatility_per_mmbtu"
                ],
                "issue425_champion_eligible": target["champion_eligible"],
                "issue425_economic_translation": target["economic_translation"],
            }
        )
        records.append(record)
    return pd.DataFrame(records).sort_values("signal_timestamp", kind="stable").reset_index(drop=True)


def _issue425_training_tail(frame: pd.DataFrame, training_window: str) -> pd.DataFrame:
    if training_window == "expanding":
        return frame
    if not training_window.startswith("rolling_"):
        raise V2OptimizationError(f"unsupported issue-425 training window: {training_window}")
    rows = int(training_window.split("_", maxsplit=1)[1])
    return frame.tail(rows).copy()


def _issue425_labels(
    frame: pd.DataFrame,
    *,
    role: str,
    dead_band_per_mmbtu: float,
    round_trip_per_mmbtu: float,
) -> pd.Series:
    cumulative = frame["issue425_realized_cumulative"].astype(float)
    aggregate = frame["issue425_aggregate"].astype(float)
    volatility = frame["issue425_realized_volatility"].astype(float)
    active = cumulative.abs() > float(dead_band_per_mmbtu)
    if role == "return":
        return frame["issue425_target"].astype(float)
    if role == "direction":
        return pd.Series(np.where(active, np.sign(aggregate), 0.0), index=frame.index)
    if role == "volatility":
        return volatility
    if role == "direction_plus_volatility":
        return pd.Series(
            np.where(active, np.sign(aggregate) * volatility, 0.0), index=frame.index
        )
    if role == "cost_aware_utility":
        hurdle = max(float(dead_band_per_mmbtu), float(round_trip_per_mmbtu))
        excess = np.maximum(cumulative.abs().to_numpy(dtype=float) - hurdle, 0.0)
        return pd.Series(np.sign(cumulative.to_numpy(dtype=float)) * excess, index=frame.index)
    raise V2OptimizationError(f"unsupported issue-425 target role: {role}")


def _issue425_model(model_id: str) -> object | None:
    from commodity.models.baselines import (
        HistGradientBoostingReturnModel,
        RidgeReturnModel,
    )

    if model_id == "expanding_mean":
        return None
    if model_id == "ridge":
        return RidgeReturnModel(alpha=10.0)
    if model_id == "hist_gb":
        return HistGradientBoostingReturnModel(
            learning_rate=0.05, max_iter=20, max_leaf_nodes=15, random_state=0
        )
    raise V2OptimizationError(f"unsupported issue-425 model: {model_id}")


def _fit_issue425_forecast_window(
    origins: pd.DataFrame,
    feature_columns: Sequence[str],
    config: Mapping[str, object],
    *,
    start_timestamp: pd.Timestamp,
    boundary_timestamp: pd.Timestamp,
    contract_multiplier: float,
    round_trip_usd: float,
    minimum_training_rows: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    start = pd.Timestamp(start_timestamp)
    boundary = pd.Timestamp(boundary_timestamp)
    frame = origins.copy()
    for column in ("signal_timestamp", "fill_timestamp", "target_end_timestamp"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
    training = frame.loc[frame["target_end_timestamp"] < start].copy()
    evaluation = frame.loc[
        frame["fill_timestamp"].ge(start)
        & frame["target_end_timestamp"].lt(boundary)
    ].copy()
    training = _issue425_training_tail(training, str(config["model.training_window"]))
    if len(training) < minimum_training_rows:
        raise V2OptimizationError(
            f"issue-425 has {len(training)} training rows; requires {minimum_training_rows}"
        )
    if evaluation.empty:
        raise V2OptimizationError("issue-425 block has no purge-safe evaluation origins")
    latest_training_end = pd.Timestamp(training["target_end_timestamp"].max())
    if latest_training_end >= start:
        raise V2OptimizationError("issue-425 training target overlaps evaluation")
    role = str(config["target.target_role"])
    dead_quantile = float(config["target.dead_band_quantile"])
    if role not in {"direction", "direction_plus_volatility", "cost_aware_utility"} and dead_quantile != 0.0:
        raise V2OptimizationError("issue-425 dead band applies only to directional target roles")
    dead_band = (
        0.0
        if dead_quantile == 0.0
        else float(training["issue425_realized_cumulative"].abs().quantile(dead_quantile))
    )
    round_trip_per_mmbtu = float(round_trip_usd) / float(contract_multiplier)
    y_train = _issue425_labels(
        training,
        role=role,
        dead_band_per_mmbtu=dead_band,
        round_trip_per_mmbtu=round_trip_per_mmbtu,
    )
    y_eval = _issue425_labels(
        evaluation,
        role=role,
        dead_band_per_mmbtu=dead_band,
        round_trip_per_mmbtu=round_trip_per_mmbtu,
    )
    x_train = training[list(feature_columns)]
    x_eval = evaluation[list(feature_columns)]
    model_id = str(config["model.model_id"])
    model = _issue425_model(model_id)
    if model is None:
        mean_value = float(y_train.mean())
        train_prediction = np.full(len(training), mean_value, dtype=float)
        prediction = np.full(len(evaluation), mean_value, dtype=float)
    else:
        model.fit(x_train, y_train)
        train_prediction = model.predict(x_train).to_numpy(dtype=float)
        prediction = model.predict(x_eval).to_numpy(dtype=float)
    aggregation = str(config["target.aggregation"])
    scale = 1.0
    if role == "direction" or aggregation == "path_summary":
        scale = float(training["issue425_realized_cumulative"].abs().median())
        if not math.isfinite(scale) or scale <= 0.0:
            scale = 1.0
    train_economic = train_prediction * scale
    economic_prediction = prediction * scale
    threshold_quantile = float(config["decision.entry_threshold_quantile"])
    threshold = float(np.quantile(np.abs(train_economic), threshold_quantile))
    if role == "volatility":
        economic_prediction = np.zeros(len(evaluation), dtype=float)
        threshold = math.inf
    else:
        economic_prediction = np.where(
            np.abs(economic_prediction) >= threshold, economic_prediction, 0.0
        )

    residual = y_train.to_numpy(dtype=float) - train_prediction
    uncertainty = float(np.std(residual, ddof=1)) if len(residual) > 1 else 0.0
    candidate_id = _sha256_payload(dict(config))[:20]
    output = evaluation.copy()
    output["forecast_id"] = [
        _sha256_payload({"candidate_id": candidate_id, "fill": pd.Timestamp(value).isoformat()})[:20]
        for value in output["fill_timestamp"]
    ]
    output["model_id"] = candidate_id
    output["prediction"] = prediction
    output["predicted_path_move_per_mmbtu"] = economic_prediction
    output["predicted_gross_pnl_usd"] = economic_prediction * float(contract_multiplier)
    output["uncertainty_per_mmbtu"] = uncertainty
    output["uncertainty_usd"] = uncertainty * float(contract_multiplier)
    output["actual_path_move_per_mmbtu"] = output["issue425_realized_cumulative"].astype(float)
    output["actual_gross_pnl_usd"] = output["actual_path_move_per_mmbtu"] * float(contract_multiplier)
    output["training_rows"] = len(training)
    output["latest_training_target_end"] = latest_training_end
    output["horizon_sessions"] = int(config["target.horizon_sessions"])
    output["issue425_actual_target"] = y_eval.to_numpy(dtype=float)
    required = [
        "forecast_id", "model_id", "signal_timestamp", "fill_trade_date",
        "fill_timestamp", "fill_contract_id", "target_end_timestamp",
        "latest_training_target_end", "training_rows", "prediction",
        "predicted_path_move_per_mmbtu", "predicted_gross_pnl_usd",
        "uncertainty_per_mmbtu", "uncertainty_usd",
        "actual_path_move_per_mmbtu", "actual_gross_pnl_usd", "horizon_sessions",
        "issue425_actual_target",
    ]
    diagnostics = {
        "training_rows": len(training),
        "evaluation_rows": len(evaluation),
        "latest_training_target_end": latest_training_end.isoformat(),
        "dead_band_per_mmbtu": dead_band,
        "entry_threshold_per_mmbtu": None if not math.isfinite(threshold) else threshold,
        "target_rmse": float(np.sqrt(np.mean(np.square(prediction - y_eval.to_numpy(dtype=float))))),
        "target_mae": float(np.mean(np.abs(prediction - y_eval.to_numpy(dtype=float)))),
        "target_direction_accuracy": float(
            np.mean(np.sign(prediction) == np.sign(y_eval.to_numpy(dtype=float)))
        ),
    }
    return output[required].sort_values("fill_timestamp").reset_index(drop=True), diagnostics


def _score_issue425_block(
    origins: pd.DataFrame,
    feature_columns: Sequence[str],
    session_path: pd.DataFrame,
    config: Mapping[str, object],
    phase2_cfg: Mapping[str, Any],
    risk: object,
    costs: object,
    *,
    block_id: str,
    start_date: str,
    end_date: str,
    minimum_training_rows: int,
) -> dict[str, object]:
    from commodity.market_only_phase2 import _path_window
    from commodity.trading_decision_v0 import simulate_policy

    window, start_timestamp, boundary_timestamp = _path_window(
        session_path, start_date=start_date, end_date=end_date
    )
    multiplier = float(phase2_cfg["execution_contract"]["contract_multiplier_mmbtu"])
    forecasts, forecast_diagnostics = _fit_issue425_forecast_window(
        origins,
        feature_columns,
        config,
        start_timestamp=start_timestamp,
        boundary_timestamp=boundary_timestamp,
        contract_multiplier=multiplier,
        round_trip_usd=float(costs.round_trip_usd),
        minimum_training_rows=minimum_training_rows,
    )
    champion_eligible = str(config["target.target_role"]) != "volatility"
    policy_id = "forecast_sign" if champion_eligible else "flat"
    ledger, policy_summary = simulate_policy(
        window,
        forecasts,
        policy_id,
        risk,
        costs,
        contract_multiplier=multiplier,
    )
    monthly_score = score_monthly_path(
        _phase2_ledger_for_monthly_score(ledger),
        starting_capital_usd=float(risk.capital_usd),
        latest_allowed_timestamp=phase2_cfg["evidence_boundary"]["last_allowed_trade_date"],
    )
    candidate_id = _sha256_payload(dict(config))[:20]
    return {
        "candidate_id": candidate_id,
        "block_id": block_id,
        "status": "complete",
        "champion_eligible": champion_eligible,
        "complexity_rank": len(feature_columns)
        + {"expanding_mean": 0, "ridge": 1, "hist_gb": 2}[str(config["model.model_id"])],
        "config": dict(config),
        "monthly_score": monthly_score,
        "forecast_diagnostics": forecast_diagnostics,
        "policy_summary": {
            "kill_triggered": bool(policy_summary["kill_triggered"]),
            "kill_reason": policy_summary.get("kill_reason"),
        },
    }


def _issue425_transform_config(config: Mapping[str, object]) -> dict[str, object]:
    return {
        "feature_family_subset": config["data.feature_family_subset"],
        "lookback_sessions": config["data.lookback_sessions"],
        "return_transform": config["transforms.return_transform"],
        "scaling": config["transforms.scaling"],
        "normalization_window_sessions": config["transforms.normalization_window_sessions"],
        "winsor_quantile": config["transforms.winsor_quantile"],
        "lag_sessions": config["transforms.lag_sessions"],
        "rolling_stat_window_sessions": config["transforms.rolling_stat_window_sessions"],
    }


def _issue425_prepare_origins(
    session_path: pd.DataFrame,
    features: pd.DataFrame,
    config: Mapping[str, object],
    *,
    round_trip_per_mmbtu: float,
    feature_cache: dict[str, tuple[pd.DataFrame, list[str]]],
    origin_cache: dict[str, tuple[pd.DataFrame, list[str]]],
) -> tuple[pd.DataFrame, list[str]]:
    from commodity.market_only_phase2 import (
        _build_segmented_decision_origins,
        _canonicalize_one_origin_per_fill,
    )

    transform_config = _issue425_transform_config(config)
    transform_key = _sha256_payload(transform_config)
    prepared = feature_cache.get(transform_key)
    if prepared is None:
        prepared = prepare_issue425_features(features, transform_config)
        feature_cache[transform_key] = prepared
    prepared_features, _ = prepared
    base_key = _sha256_payload(
        {
            "transform": transform_key,
            "horizon": int(config["target.horizon_sessions"]),
        }
    )
    base = origin_cache.get(base_key)
    if base is None:
        origins, feature_columns = _build_segmented_decision_origins(
            session_path,
            prepared_features,
            horizon_sessions=int(config["target.horizon_sessions"]),
        )
        if origins.empty:
            raise V2OptimizationError("issue-425 target reconstruction produced no origins")
        origins, _ = _canonicalize_one_origin_per_fill(origins)
        base = (origins, feature_columns)
        origin_cache[base_key] = base
    base_origins, feature_columns = base
    attached = _attach_issue425_targets(
        base_origins,
        session_path,
        horizon_sessions=int(config["target.horizon_sessions"]),
        role=str(config["target.target_role"]),
        aggregation=str(config["target.aggregation"]),
        round_trip_per_mmbtu=round_trip_per_mmbtu,
    )
    return attached, feature_columns


def _aggregate_issue425_blocks(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    completed = [row for row in rows if row.get("status") == "complete"]
    if len(completed) != len(rows) or not completed:
        raise V2OptimizationError("issue-425 aggregate requires complete block scores")
    scores = [row["monthly_score"] for row in completed]
    if not all(isinstance(score, Mapping) for score in scores):
        raise V2OptimizationError("issue-425 block score is invalid")
    month_count = sum(int(score["month_count"]) for score in scores)
    if month_count < 1:
        raise V2OptimizationError("issue-425 aggregate has no scored months")

    def weighted(name: str) -> float:
        return sum(
            float(score[name]) * int(score["month_count"]) for score in scores
        ) / month_count

    aggregate_score = {
        "session_count": sum(int(score["session_count"]) for score in scores),
        "month_count": month_count,
        "total_net_pnl_usd": sum(float(score["total_net_pnl_usd"]) for score in scores),
        "mean_monthly_net_return": weighted("mean_monthly_net_return"),
        "median_monthly_net_return": weighted("median_monthly_net_return"),
        "worst_monthly_net_return": min(float(score["worst_monthly_net_return"]) for score in scores),
        "best_monthly_net_return": max(float(score["best_monthly_net_return"]) for score in scores),
        "profitable_month_rate": weighted("profitable_month_rate"),
        "monthly_net_return_std": weighted("monthly_net_return_std"),
        "max_drawdown_fraction": max(float(score["max_drawdown_fraction"]) for score in scores),
        "transaction_cost_usd": sum(float(score["transaction_cost_usd"]) for score in scores),
        "turnover": sum(float(score["turnover"]) for score in scores),
        "max_gross_exposure_fraction": max(float(score["max_gross_exposure_fraction"]) for score in scores),
        "max_abs_net_exposure_fraction": max(float(score["max_abs_net_exposure_fraction"]) for score in scores),
        "max_leverage": max(float(score["max_leverage"]) for score in scores),
        "trade_count": sum(int(score["trade_count"]) for score in scores),
        "long_net_pnl_usd": sum(float(score["long_net_pnl_usd"]) for score in scores),
        "short_net_pnl_usd": sum(float(score["short_net_pnl_usd"]) for score in scores),
        "flat_net_pnl_usd": sum(float(score["flat_net_pnl_usd"]) for score in scores),
        "largest_positive_month_profit_fraction": max(
            float(score["largest_positive_month_profit_fraction"]) for score in scores
        ),
    }
    first = completed[0]
    return {
        "candidate_id": first["candidate_id"],
        "champion_eligible": bool(first["champion_eligible"]),
        "complexity_rank": int(first["complexity_rank"]),
        "config": dict(first["config"]),
        "monthly_score": aggregate_score,
        "block_scores": [dict(row) for row in completed],
    }


def _evaluate_issue425_config(
    session_path: pd.DataFrame,
    features: pd.DataFrame,
    phase2_cfg: Mapping[str, Any],
    risk: object,
    costs: object,
    config: Mapping[str, object],
    blocks: Sequence[Mapping[str, str]],
    *,
    minimum_training_rows: int,
    feature_cache: dict[str, tuple[pd.DataFrame, list[str]]],
    origin_cache: dict[str, tuple[pd.DataFrame, list[str]]],
) -> dict[str, object]:
    try:
        round_trip_per_mmbtu = float(costs.round_trip_usd) / float(
            phase2_cfg["execution_contract"]["contract_multiplier_mmbtu"]
        )
        origins, feature_columns = _issue425_prepare_origins(
            session_path,
            features,
            config,
            round_trip_per_mmbtu=round_trip_per_mmbtu,
            feature_cache=feature_cache,
            origin_cache=origin_cache,
        )
        rows = [
            _score_issue425_block(
                origins,
                feature_columns,
                session_path,
                config,
                phase2_cfg,
                risk,
                costs,
                block_id=str(block["id"]),
                start_date=str(block["start"]),
                end_date=str(block["end"]),
                minimum_training_rows=minimum_training_rows,
            )
            for block in blocks
        ]
        return _aggregate_issue425_blocks(rows)
    except (V2OptimizationError, ValueError) as exc:
        return {
            "candidate_id": _sha256_payload(dict(config))[:20],
            "status": "failed",
            "champion_eligible": str(config.get("target.target_role")) != "volatility",
            "config": dict(config),
            "reason": str(exc),
        }


def _issue425_default_config() -> dict[str, object]:
    return {
        "target.target_role": "return",
        "target.horizon_sessions": 5,
        "target.dead_band_quantile": 0.0,
        "target.aggregation": "cumulative",
        "model.model_id": "ridge",
        "model.training_window": "expanding",
        "data.feature_family_subset": "market",
        "data.lookback_sessions": 252,
        "transforms.return_transform": "log_return",
        "transforms.scaling": "none",
        "transforms.normalization_window_sessions": 60,
        "transforms.winsor_quantile": 0.0,
        "transforms.lag_sessions": 1,
        "transforms.rolling_stat_window_sessions": 20,
        "decision.entry_threshold_quantile": 0.5,
    }


def _rank_issue425_rows(rows: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    completed = [
        row
        for row in rows
        if row.get("status", "complete") == "complete"
        and bool(row.get("champion_eligible", True))
        and isinstance(row.get("monthly_score"), Mapping)
    ]
    return sorted(
        completed,
        key=lambda row: (
            -float(row["monthly_score"]["mean_monthly_net_return"]),
            float(row["monthly_score"]["max_drawdown_fraction"]),
            float(row["monthly_score"]["transaction_cost_usd"]),
            int(row.get("complexity_rank", 999)),
            str(row.get("candidate_id", "")),
        ),
    )


def _issue425_evaluate_trial(
    *,
    stage: str,
    outer_block_id: str,
    blocks: Sequence[Mapping[str, str]],
    config: Mapping[str, object],
    session_path: pd.DataFrame,
    features: pd.DataFrame,
    phase2_cfg: Mapping[str, Any],
    risk: object,
    costs: object,
    minimum_training_rows: int,
    ledger: TrialLedger,
    trial_cache: dict[str, dict[str, object]],
    dataset_id: str,
    code_id: str,
    feature_cache: dict[str, tuple[pd.DataFrame, list[str]]],
    origin_cache: dict[str, tuple[pd.DataFrame, list[str]]],
) -> dict[str, object]:
    trial_config = {
        "stage": stage,
        "outer_block_id": outer_block_id,
        "selection_blocks": [str(block["id"]) for block in blocks],
        "config": dict(config),
    }
    trial_id = build_trial_id(
        trial_config,
        seed=0,
        dataset_id=dataset_id,
        code_id=code_id,
        evidence_class="development",
    )
    existing = trial_cache.get(trial_id)
    if existing is not None:
        return dict(existing["result"])
    result = _evaluate_issue425_config(
        session_path,
        features,
        phase2_cfg,
        risk,
        costs,
        config,
        blocks,
        minimum_training_rows=minimum_training_rows,
        feature_cache=feature_cache,
        origin_cache=origin_cache,
    )
    status = "complete" if result.get("status", "complete") == "complete" else "failed"
    record: dict[str, object] = {
        "trial_id": trial_id,
        "status": status,
        "evidence_class": "development",
        "dataset_id": dataset_id,
        "code_id": code_id,
        "seed": 0,
        "stage": stage,
        "outer_block_id": outer_block_id,
        "selection_blocks": [str(block["id"]) for block in blocks],
        "config": dict(config),
        "result": result,
    }
    ledger.append(record)
    trial_cache[trial_id] = record
    return result


def _issue425_sweep(
    configs: Sequence[Mapping[str, object]],
    *,
    stage: str,
    outer_block_id: str,
    blocks: Sequence[Mapping[str, str]],
    evaluator: Any,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for config in configs:
        config_id = _sha256_payload(dict(config))
        if config_id in seen:
            continue
        seen.add(config_id)
        rows.append(evaluator(stage, outer_block_id, blocks, dict(config)))
    return rows


def _search_issue425_outer(
    plan: Mapping[str, Any],
    outer_block: Mapping[str, str],
    inner_blocks: Sequence[Mapping[str, str]],
    evaluator: Any,
) -> dict[str, object]:
    if not inner_blocks:
        raise V2OptimizationError("issue-425 outer block has no prior inner evidence")
    axes = _issue425_plan_axes(plan)
    outer_id = str(outer_block["id"])
    base = _issue425_default_config()
    stage_summaries: list[dict[str, object]] = []

    structural_configs: list[dict[str, object]] = []
    for role, horizon, aggregation in itertools.product(
        axes["target.target_role"],
        axes["target.horizon_sessions"],
        axes["target.aggregation"],
    ):
        config = dict(base)
        config.update(
            {
                "target.target_role": role,
                "target.horizon_sessions": horizon,
                "target.dead_band_quantile": 0.0,
                "target.aggregation": aggregation,
            }
        )
        structural_configs.append(config)
    structural_rows = _issue425_sweep(
        structural_configs,
        stage="structural_target_horizon",
        outer_block_id=outer_id,
        blocks=inner_blocks,
        evaluator=evaluator,
    )
    structural_ranked = _rank_issue425_rows(structural_rows)
    if not structural_ranked:
        raise V2OptimizationError("issue-425 structural search produced no economic candidate")
    current = dict(structural_ranked[0]["config"])
    stage_summaries.append(
        {
            "stage": "structural_target_horizon",
            "trials": len(structural_rows),
            "winner": structural_ranked[0],
        }
    )

    directional_roles = {
        "direction", "direction_plus_volatility", "cost_aware_utility"
    }
    deadband_configs: list[dict[str, object]] = []
    for role in sorted(directional_roles):
        role_rows = [
            row
            for row in structural_rows
            if row.get("status", "complete") == "complete"
            and row.get("config", {}).get("target.target_role") == role
        ]
        ranked = _rank_issue425_rows(role_rows)
        if not ranked:
            continue
        role_base = dict(ranked[0]["config"])
        for value in axes["target.dead_band_quantile"]:
            config = dict(role_base)
            config["target.dead_band_quantile"] = value
            deadband_configs.append(config)
    deadband_rows = _issue425_sweep(
        deadband_configs,
        stage="target_dead_band",
        outer_block_id=outer_id,
        blocks=inner_blocks,
        evaluator=evaluator,
    )
    combined_target_rows = [*structural_rows, *deadband_rows]
    combined_ranked = _rank_issue425_rows(combined_target_rows)
    if combined_ranked:
        current = dict(combined_ranked[0]["config"])
    stage_summaries.append(
        {
            "stage": "target_dead_band",
            "trials": len(deadband_rows),
            "winner": combined_ranked[0] if combined_ranked else structural_ranked[0],
        }
    )

    model_feature_configs: list[dict[str, object]] = []
    for model_id, training_window, family in itertools.product(
        axes["model.model_id"],
        axes["model.training_window"],
        axes["data.feature_family_subset"],
    ):
        config = dict(current)
        config.update(
            {
                "model.model_id": model_id,
                "model.training_window": training_window,
                "data.feature_family_subset": family,
            }
        )
        model_feature_configs.append(config)
    model_feature_rows = _issue425_sweep(
        model_feature_configs,
        stage="model_feature_interaction",
        outer_block_id=outer_id,
        blocks=inner_blocks,
        evaluator=evaluator,
    )
    ranked = _rank_issue425_rows(model_feature_rows)
    if ranked:
        current = dict(ranked[0]["config"])
    stage_summaries.append(
        {
            "stage": "model_feature_interaction",
            "trials": len(model_feature_rows),
            "winner": ranked[0] if ranked else None,
        }
    )
    coordinate_axes = [
        "transforms.return_transform",
        "transforms.scaling",
        "transforms.normalization_window_sessions",
        "transforms.winsor_quantile",
        "data.lookback_sessions",
        "transforms.lag_sessions",
        "transforms.rolling_stat_window_sessions",
        "decision.entry_threshold_quantile",
    ]
    top_values: dict[str, list[object]] = {}
    for axis in coordinate_axes:
        configs: list[dict[str, object]] = []
        for value in axes[axis]:
            config = dict(current)
            config[axis] = value
            configs.append(config)
        rows = _issue425_sweep(
            configs,
            stage=f"coordinate:{axis}",
            outer_block_id=outer_id,
            blocks=inner_blocks,
            evaluator=evaluator,
        )
        ranked = _rank_issue425_rows(rows)
        if ranked:
            current = dict(ranked[0]["config"])
            values: list[object] = []
            for row in ranked:
                value = row["config"][axis]
                if value not in values:
                    values.append(value)
                if len(values) == 2:
                    break
            top_values[axis] = values
        stage_summaries.append(
            {
                "stage": f"coordinate:{axis}",
                "trials": len(rows),
                "winner": ranked[0] if ranked else None,
            }
        )
    threshold_horizon_configs: list[dict[str, object]] = []
    for threshold, horizon in itertools.product(
        axes["decision.entry_threshold_quantile"],
        axes["target.horizon_sessions"],
    ):
        config = dict(current)
        config["decision.entry_threshold_quantile"] = threshold
        config["target.horizon_sessions"] = horizon
        threshold_horizon_configs.append(config)
    threshold_horizon_rows = _issue425_sweep(
        threshold_horizon_configs,
        stage="threshold_horizon_interaction",
        outer_block_id=outer_id,
        blocks=inner_blocks,
        evaluator=evaluator,
    )
    ranked = _rank_issue425_rows(threshold_horizon_rows)
    if ranked:
        current = dict(ranked[0]["config"])
    stage_summaries.append(
        {
            "stage": "threshold_horizon_interaction",
            "trials": len(threshold_horizon_rows),
            "winner": ranked[0] if ranked else None,
        }
    )

    interaction_axes = [
        "data.lookback_sessions",
        "transforms.return_transform",
        "transforms.scaling",
        "transforms.normalization_window_sessions",
        "transforms.winsor_quantile",
        "transforms.lag_sessions",
        "transforms.rolling_stat_window_sessions",
    ]
    interaction_values = [top_values.get(axis, [current[axis]]) for axis in interaction_axes]
    interaction_configs: list[dict[str, object]] = []
    for values in itertools.product(*interaction_values):
        config = dict(current)
        for axis, value in zip(interaction_axes, values, strict=True):
            config[axis] = value
        interaction_configs.append(config)
    interaction_rows = _issue425_sweep(
        interaction_configs,
        stage="transform_top_pair_interactions",
        outer_block_id=outer_id,
        blocks=inner_blocks,
        evaluator=evaluator,
    )
    ranked = _rank_issue425_rows(interaction_rows)
    if ranked:
        current = dict(ranked[0]["config"])
    stage_summaries.append(
        {
            "stage": "transform_top_pair_interactions",
            "trials": len(interaction_rows),
            "winner": ranked[0] if ranked else None,
        }
    )

    volatility_rows = [
        row
        for row in structural_rows
        if row.get("status", "complete") == "complete"
        and row.get("config", {}).get("target.target_role") == "volatility"
    ]
    volatility_specialist = None
    if volatility_rows:
        volatility_specialist = min(
            volatility_rows,
            key=lambda row: float(
                np.mean(
                    [
                        block["forecast_diagnostics"]["target_rmse"]
                        for block in row["block_scores"]
                    ]
                )
            ),
        )
    total_trials = sum(int(item["trials"]) for item in stage_summaries)
    return {
        "outer_block_id": outer_id,
        "selection_block_ids": [str(block["id"]) for block in inner_blocks],
        "selected_config": current,
        "selected_candidate_id": _sha256_payload(current)[:20],
        "stage_summaries": stage_summaries,
        "volatility_specialist": volatility_specialist,
        "trial_count": total_trials,
    }


def _score_issue425_control(
    session_path: pd.DataFrame,
    phase2_cfg: Mapping[str, Any],
    risk: object,
    costs: object,
    *,
    policy_id: str,
    block: Mapping[str, str],
) -> dict[str, object]:
    from commodity.market_only_phase2 import _path_window
    from commodity.trading_decision_v0 import simulate_policy

    window, _, _ = _path_window(
        session_path, start_date=str(block["start"]), end_date=str(block["end"])
    )
    ledger, policy_summary = simulate_policy(
        window,
        pd.DataFrame(),
        policy_id,
        risk,
        costs,
        contract_multiplier=float(phase2_cfg["execution_contract"]["contract_multiplier_mmbtu"]),
    )
    return {
        "policy_id": policy_id,
        "block_id": str(block["id"]),
        "monthly_score": score_monthly_path(
            _phase2_ledger_for_monthly_score(ledger),
            starting_capital_usd=float(risk.capital_usd),
            latest_allowed_timestamp=phase2_cfg["evidence_boundary"]["last_allowed_trade_date"],
        ),
        "kill_triggered": bool(policy_summary["kill_triggered"]),
    }


def _issue425_v1_development_comparator(
    path: Path, block: Mapping[str, str], *, starting_capital_usd: float
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("protected_confirmation_accessed") is not False:
        raise V2OptimizationError("V1 development comparator crossed protected evidence")
    if payload.get("decision") != "reject_annual_refit_retain_frozen_phase5_cadence":
        raise V2OptimizationError("V1 development comparator is not the retained frozen cadence")
    yearly = payload.get("frozen_two_year_cadence", {}).get("yearly_path", [])
    start_year = pd.Timestamp(str(block["start"])).year
    end_year = pd.Timestamp(str(block["end"])).year
    selected = [row for row in yearly if start_year <= int(row["year"]) <= end_year]
    expected_years = set(range(start_year, end_year + 1))
    if {int(row["year"]) for row in selected} != expected_years:
        raise V2OptimizationError("V1 comparator lacks required development years")
    net = sum(float(row["net_pnl_usd"]) for row in selected)
    costs = sum(float(row["transaction_cost_usd"]) for row in selected)
    max_drawdown = max(float(row["max_drawdown_fraction"]) for row in selected)
    months = 12 * len(selected)
    return {
        "block_id": str(block["id"]),
        "source": "phase6_frozen_two_year_cadence_development",
        "year_count": len(selected),
        "month_count": months,
        "total_net_pnl_usd": net,
        "mean_monthly_net_return": net / (float(starting_capital_usd) * months),
        "transaction_cost_usd": costs,
        "max_drawdown_fraction": max_drawdown,
        "yearly_path": selected,
    }


def _combine_issue425_score_summaries(
    scores: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    if not scores:
        raise V2OptimizationError("issue-425 score combination is empty")
    months = sum(int(score["month_count"]) for score in scores)
    if months < 1:
        raise V2OptimizationError("issue-425 score combination has no months")

    def weighted(name: str) -> float:
        return sum(float(score[name]) * int(score["month_count"]) for score in scores) / months

    return {
        "month_count": months,
        "total_net_pnl_usd": sum(float(score["total_net_pnl_usd"]) for score in scores),
        "mean_monthly_net_return": weighted("mean_monthly_net_return"),
        "median_monthly_net_return": weighted("median_monthly_net_return"),
        "worst_monthly_net_return": min(float(score["worst_monthly_net_return"]) for score in scores),
        "best_monthly_net_return": max(float(score["best_monthly_net_return"]) for score in scores),
        "profitable_month_rate": weighted("profitable_month_rate"),
        "max_drawdown_fraction": max(float(score["max_drawdown_fraction"]) for score in scores),
        "transaction_cost_usd": sum(float(score["transaction_cost_usd"]) for score in scores),
        "turnover": sum(float(score["turnover"]) for score in scores),
        "trade_count": sum(int(score["trade_count"]) for score in scores),
        "long_net_pnl_usd": sum(float(score["long_net_pnl_usd"]) for score in scores),
        "short_net_pnl_usd": sum(float(score["short_net_pnl_usd"]) for score in scores),
    }


def run_issue425_development_optimization(
    *,
    registry_path: Path,
    search_plan_path: Path,
    phase2_config_path: Path,
    databento_root: Path,
    v1_development_comparator_path: Path,
    trial_ledger_path: Path,
    checkpoint_dir: Path | None = None,
    heartbeat_seconds: float = 30.0,
) -> dict[str, object]:
    from commodity.market_only_phase2 import (
        _inner_fold_specs,
        _load_inherited_risk_and_costs,
        build_phase2_inputs,
        reconstruct_market_history,
        validate_phase2_config,
    )
    from commodity.phase2_runtime import Phase2CheckpointStore, Phase2Telemetry

    registry = load_v2_registry(registry_path)
    plan = load_issue425_search_plan(search_plan_path)
    validation = validate_issue425_search_plan(registry, plan)
    cfg = json.loads(Path(phase2_config_path).read_text(encoding="utf-8"))
    validate_phase2_config(cfg)
    cutoff = pd.Timestamp(cfg["evidence_boundary"]["last_allowed_trade_date"], tz="UTC")
    plan_cutoff = pd.Timestamp(str(validation["latest_allowed_trade_date"]), tz="UTC")
    if cutoff > plan_cutoff or cutoff > pd.Timestamp("2022-12-31", tz="UTC"):
        raise V2OptimizationError("issue-425 data exceeds preregistered development cutoff")
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
            "issue": 425,
            "registry_id": registry.registry_id,
            "phase2_config_sha256": _sha256_file(Path(phase2_config_path)),
            "source_provenance_sha256": str(provenance["provenance_sha256"]),
            "v2_optimization_code_sha256": _sha256_file(Path(__file__)),
        }
        session_path = None
        features = None
        if checkpoint_store is not None:
            session_path = checkpoint_store.load_frame("issue425/inputs/session-path", input_identity)
            features = checkpoint_store.load_frame("issue425/inputs/features", input_identity)
        if session_path is None or features is None:
            with telemetry.stage("issue425_input_build"):
                session_path, features = build_phase2_inputs(
                    canonical, market, execution_bars, cfg, telemetry=telemetry
                )
            if checkpoint_store is not None:
                checkpoint_store.save_frame("issue425/inputs/session-path", session_path, input_identity)
                checkpoint_store.save_frame("issue425/inputs/features", features, input_identity)
    risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    costs = cost_profiles["base"]
    inner_folds = _inner_fold_specs(cfg)
    outer_blocks = list(cfg["validation"]["outer_blocks"])
    planned_outer = list(plan["validation"]["outer_blocks"])
    observed_outer = [f"{block['start']}/{block['end']}" for block in outer_blocks]
    if observed_outer != planned_outer:
        raise V2OptimizationError("issue-425 outer blocks differ from preregistration")
    minimum_training_rows = int(plan["validation"]["minimum_training_rows"])

    ledger = TrialLedger(trial_ledger_path)
    trial_cache = ledger._records()
    dataset_id = str(provenance["provenance_sha256"])
    code_id = _sha256_file(Path(__file__))
    feature_cache: dict[str, tuple[pd.DataFrame, list[str]]] = {}
    origin_cache: dict[str, tuple[pd.DataFrame, list[str]]] = {}

    def evaluator(
        stage: str,
        outer_block_id: str,
        blocks: Sequence[Mapping[str, str]],
        config: Mapping[str, object],
    ) -> dict[str, object]:
        return _issue425_evaluate_trial(
            stage=stage,
            outer_block_id=outer_block_id,
            blocks=blocks,
            config=config,
            session_path=session_path,
            features=features,
            phase2_cfg=cfg,
            risk=risk,
            costs=costs,
            minimum_training_rows=minimum_training_rows,
            ledger=ledger,
            trial_cache=trial_cache,
            dataset_id=dataset_id,
            code_id=code_id,
            feature_cache=feature_cache,
            origin_cache=origin_cache,
        )
    nested_outer: list[dict[str, object]] = []
    for outer in outer_blocks:
        outer_start = pd.Timestamp(str(outer["start"]))
        eligible_inner = [
            fold
            for fold in inner_folds
            if pd.Timestamp(str(fold["end"])) < outer_start
        ]
        search = _search_issue425_outer(plan, outer, eligible_inner, evaluator)
        selected_config = dict(search["selected_config"])
        outer_result = evaluator(
            "outer_evaluation",
            str(outer["id"]),
            [outer],
            selected_config,
        )
        if outer_result.get("status", "complete") != "complete":
            raise V2OptimizationError(
                f"issue-425 selected outer candidate failed: {outer_result.get('reason')}"
            )
        controls = {
            policy: _score_issue425_control(
                session_path,
                cfg,
                risk,
                costs,
                policy_id=policy,
                block=outer,
            )
            for policy in ("flat", "long_only")
        }
        v1 = _issue425_v1_development_comparator(
            v1_development_comparator_path,
            outer,
            starting_capital_usd=float(risk.capital_usd),
        )
        nested_outer.append(
            {
                "outer_block": dict(outer),
                "search": search,
                "selected_outer_result": outer_result,
                "controls": controls,
                "v1_development_comparator": v1,
            }
        )
    nested_score = _combine_issue425_score_summaries(
        [item["selected_outer_result"]["monthly_score"] for item in nested_outer]
    )
    control_summary = {
        policy: _combine_issue425_score_summaries(
            [item["controls"][policy]["monthly_score"] for item in nested_outer]
        )
        for policy in ("flat", "long_only")
    }
    v1_rows = [item["v1_development_comparator"] for item in nested_outer]
    v1_months = sum(int(item["month_count"]) for item in v1_rows)
    v1_total = sum(float(item["total_net_pnl_usd"]) for item in v1_rows)
    v1_summary = {
        "month_count": v1_months,
        "total_net_pnl_usd": v1_total,
        "mean_monthly_net_return": v1_total / (float(risk.capital_usd) * v1_months),
        "max_drawdown_fraction": max(float(item["max_drawdown_fraction"]) for item in v1_rows),
        "transaction_cost_usd": sum(float(item["transaction_cost_usd"]) for item in v1_rows),
    }
    latest_handoff = dict(nested_outer[-1]["search"]["selected_config"])
    total_trials = len(ledger._records())
    return {
        "schema_version": 1,
        "issue": 425,
        "programme_issue": 393,
        "status": "complete_development_only",
        "evidence_class": "development",
        "protected_confirmation_accessed": False,
        "true_forward_accessed": False,
        "saxo_sim_accessed": False,
        "saxo_live_accessed": False,
        "registry_id": registry.registry_id,
        "search_plan_sha256": _sha256_file(Path(search_plan_path)),
        "source_provenance_sha256": dataset_id,
        "code_id": code_id,
        "trial_count": total_trials,
        "nested_outer": nested_outer,
        "nested_selection_score": nested_score,
        "simple_controls": control_summary,
        "v1_development_comparator": v1_summary,
        "latest_preregistered_handoff_config": latest_handoff,
        "claim_boundary": "development family optimization only; no confirmed V2 edge claim",
    }
