from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
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


_ISSUE426_SOURCES = {
    "storage": "eia_storage",
    "weather": "weather",
    "power": "nyiso_load_forecast",
    "positioning": "cftc_cot",
}
_ISSUE426_WEATHER_ARCHIVE_MISSING_REASONS = {
    "required 2m temperature variable absent from archived lead",
    "archived forecast lead file absent",
}

_ISSUE426_REPRESENTATION_SUFFIXES = {
    "storage": {
        "level": ("lower48_bcf", "east_bcf", "midwest_bcf", "mountain_bcf", "pacific_bcf", "south_central_bcf"),
        "seasonal_deviation": ("seasonal_deviation_bcf",),
        "change": ("change_bcf",),
        "release_surprise": ("release_surprise_bcf", "implied_flow_bcf"),
        "revision": ("reclassification_event", "reclassification_bcf"),
        "event_timing": ("days_since_previous_release",),
    },
    "positioning": {
        "managed_money_net": ("managed_money_net",),
        "managed_money_pct_oi": ("managed_money_pct_oi",),
        "producer_merchant_net": ("producer_merchant_net", "producer_merchant_pct_oi"),
        "swap_dealer_net": ("swap_dealer_net", "swap_dealer_pct_oi"),
        "change": ("managed_money_change", "producer_merchant_change", "swap_dealer_change"),
        "zscore": ("managed_money_zscore_52",),
    },
    "weather": {
        "level": ("temp_mean_c",),
        "hdd_cdd": ("hdd65_mean_c", "cdd65_mean_c"),
        "anomaly": ("temp_seasonal_anomaly_c", "hdd65_seasonal_anomaly_c"),
        "revision": ("revision_temp_mean_c", "revision_hdd65_mean_c"),
        "geography": (
            "midwest_chicago_temp_mean_c",
            "northeast_new_york_temp_mean_c",
            "southeast_atlanta_temp_mean_c",
            "south_central_houston_temp_mean_c",
        ),
        "horizon": (
            "near_temp_mean_c",
            "far_temp_mean_c",
            "near_minus_far_temp_c",
            "near_hdd65_mean_c",
            "far_hdd65_mean_c",
        ),
        "dispersion": (
            "temp_dispersion_c",
            "anchor_temp_dispersion_c",
        ),
        "forecast_error_history": ("revision_error_proxy_mae_30d_c",),
    },
    "power": {},
}


def load_issue426_search_plan(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("issue") != 426:
        raise V2OptimizationError("unsupported issue-426 search plan")
    if payload.get("status") != "preregistered_before_issue426_scoring":
        raise V2OptimizationError("issue-426 search plan is not preregistered")
    if payload.get("evidence_class") != "development":
        raise V2OptimizationError("issue-426 search must use development evidence")
    cutoff = pd.Timestamp(str(payload.get("latest_allowed_trade_date")), tz="UTC")
    if cutoff > pd.Timestamp("2022-12-31", tz="UTC"):
        raise V2OptimizationError("issue-426 search plan crosses protected evidence")
    if not isinstance(payload.get("families"), list):
        raise V2OptimizationError("issue-426 search plan is missing families")
    return payload


def load_issue426_source_plan(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("issue") != 426:
        raise V2OptimizationError("unsupported issue-426 source plan")
    if payload.get("plan_id") != "issue426-source-plan-v2":
        raise V2OptimizationError("issue-426 source plan identity is invalid")
    if payload.get("status") != "registered_before_historical_family_scoring":
        raise V2OptimizationError("issue-426 historical sources were not preregistered")
    if payload.get("evidence_class") != "development":
        raise V2OptimizationError("issue-426 source plan must use development evidence")
    if payload.get("protected_evidence_accessed") is not False:
        raise V2OptimizationError("issue-426 source plan crossed protected evidence")
    cutoff = pd.Timestamp(str(payload.get("latest_allowed_trade_date")), tz="UTC")
    if cutoff > pd.Timestamp("2022-12-31", tz="UTC"):
        raise V2OptimizationError("issue-426 source plan crosses protected evidence")
    families = payload.get("families")
    if not isinstance(families, Mapping) or set(families) != set(_ISSUE426_SOURCES):
        raise V2OptimizationError("issue-426 source plan family set is invalid")
    return payload


def load_issue426_optimization_plan(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("issue") != 426:
        raise V2OptimizationError("unsupported issue-426 optimization plan")
    if payload.get("plan_id") != "issue426-optimization-plan-v3":
        raise V2OptimizationError("issue-426 optimization plan identity is invalid")
    if payload.get("status") != "registered_before_authoritative_issue426_scoring":
        raise V2OptimizationError("issue-426 authoritative optimization plan is not preregistered")
    if payload.get("supersedes") != "issue426-optimization-plan-v2":
        raise V2OptimizationError("issue-426 optimization-plan supersession is invalid")
    if payload.get("evidence_class") != "development":
        raise V2OptimizationError("issue-426 optimization must use development evidence")
    cutoff = pd.Timestamp(str(payload.get("latest_allowed_trade_date")), tz="UTC")
    if cutoff > pd.Timestamp("2022-12-31", tz="UTC"):
        raise V2OptimizationError("issue-426 optimization plan crosses protected evidence")
    if not isinstance(payload.get("stages"), list) or not isinstance(payload.get("roles"), Mapping):
        raise V2OptimizationError("issue-426 optimization plan lacks stages or roles")
    return payload


def load_issue426_weather_feature_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("issue") != 426:
        raise V2OptimizationError("unsupported issue-426 weather feature contract")
    if payload.get("contract_id") != "issue426-weather-feature-contract-v1":
        raise V2OptimizationError("issue-426 weather feature contract identity is invalid")
    if payload.get("status") != "preregistered_before_weather_scoring":
        raise V2OptimizationError("issue-426 weather features were not preregistered")
    if payload.get("evidence_class") != "development":
        raise V2OptimizationError("issue-426 weather contract must use development evidence")
    if payload.get("protected_confirmation_accessed") is not False:
        raise V2OptimizationError("issue-426 weather contract crossed protected evidence")
    cutoff = pd.Timestamp(str(payload.get("latest_allowed_trade_date")), tz="UTC")
    if cutoff > pd.Timestamp("2022-12-31", tz="UTC"):
        raise V2OptimizationError("issue-426 weather contract crosses protected evidence")
    if payload.get("source_id") != "ncar_gdex_d084001_gfs_0p25_issued_00utc":
        raise V2OptimizationError("issue-426 weather contract source identity is invalid")
    if int(payload.get("availability_delay_minutes", -1)) != 370:
        raise V2OptimizationError("issue-426 weather availability delay is invalid")
    if not math.isclose(float(payload.get("degree_day_base_c", math.nan)), 18.3333333333):
        raise V2OptimizationError("issue-426 weather degree-day base is invalid")
    expected_anchors = [
        "midwest_chicago",
        "northeast_new_york",
        "southeast_atlanta",
        "south_central_houston",
    ]
    if list(payload.get("anchors", [])) != expected_anchors:
        raise V2OptimizationError("issue-426 weather anchor contract is invalid")
    leads = payload.get("requested_lead_hours")
    if not isinstance(leads, Mapping) or (
        int(leads.get("start", -1)),
        int(leads.get("end", -1)),
        int(leads.get("step", -1)),
    ) != (24, 168, 3):
        raise V2OptimizationError("issue-426 weather lead contract is invalid")
    archive_rule = payload.get("archive_omission_rule")
    if not isinstance(archive_rule, Mapping) or archive_rule.get("coverage_diagnostic") != (
        "lead_coverage_fraction_not_scored"
    ):
        raise V2OptimizationError("issue-426 weather archive coverage must be diagnostic only")
    if set(map(str, archive_rule.get("allowed_archive_omission_reasons", []))) != (
        _ISSUE426_WEATHER_ARCHIVE_MISSING_REASONS
    ):
        raise V2OptimizationError("issue-426 weather archive omission reasons differ from contract")
    representations = payload.get("representations")
    expected_representations = _ISSUE426_REPRESENTATION_SUFFIXES["weather"]
    if not isinstance(representations, Mapping) or set(representations) != set(
        expected_representations
    ):
        raise V2OptimizationError("issue-426 weather representation contract is invalid")
    for name, suffixes in expected_representations.items():
        item = representations.get(name)
        if not isinstance(item, Mapping) or list(item.get("features", [])) != list(suffixes):
            raise V2OptimizationError(
                f"issue-426 weather representation features differ: {name}"
            )
    error_history = representations["forecast_error_history"]
    if error_history.get("semantic_boundary") != (
        "revision_error_proxy_not_observed_realized_forecast_error"
    ):
        raise V2OptimizationError("issue-426 weather error-history semantic boundary is invalid")
    return payload


def load_issue426_interaction_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("issue") != 426:
        raise V2OptimizationError("unsupported issue-426 interaction contract")
    if payload.get("contract_id") != "issue426-interaction-contract-v1":
        raise V2OptimizationError("issue-426 interaction contract identity is invalid")
    if payload.get("status") != "preregistered_before_combined_interaction_scoring":
        raise V2OptimizationError("issue-426 combined interaction was not preregistered")
    if payload.get("evidence_class") != "development":
        raise V2OptimizationError("issue-426 interaction contract must use development evidence")
    if payload.get("protected_confirmation_accessed") is not False:
        raise V2OptimizationError("issue-426 interaction contract crossed protected evidence")
    cutoff = pd.Timestamp(str(payload.get("latest_allowed_trade_date")), tz="UTC")
    if cutoff > pd.Timestamp("2022-12-31", tz="UTC"):
        raise V2OptimizationError("issue-426 interaction contract crosses protected evidence")
    if payload.get("required_interaction") != "storage×weather×season×volatility":
        raise V2OptimizationError("issue-426 combined interaction identity is invalid")
    if payload.get("formula") != (
        "storage_value * weather_value * season_component * feature_vol_20"
    ):
        raise V2OptimizationError("issue-426 combined interaction formula is invalid")
    if list(payload.get("season_components", [])) != [
        "feature_season_sin",
        "feature_season_cos",
    ]:
        raise V2OptimizationError("issue-426 combined interaction season contract is invalid")
    if list(payload.get("transform_basis_candidates", [])) != [
        "storage_selected_transform",
        "weather_selected_transform",
    ]:
        raise V2OptimizationError("issue-426 combined interaction transform bases are invalid")
    if int(payload.get("transform_basis_retain", -1)) != 1:
        raise V2OptimizationError("issue-426 combined interaction retain rule is invalid")
    if payload.get("lower_order_family_main_effects_in_combined_candidate") is not False:
        raise V2OptimizationError("issue-426 combined interaction ablation is not isolated")
    return payload


def validate_issue426_optimization_plan(
    registry: V2Registry, plan: Mapping[str, Any]
) -> dict[str, Any]:
    registry.assert_search_evidence(str(plan.get("evidence_class")))
    if plan.get("base_configuration") != (
        "issue425-result-v1.nested_outer[].search.selected_config matched by outer_block_id"
    ):
        raise V2OptimizationError("issue-426 base configuration is not outer matched")
    if plan.get("matched_control") != (
        "same_outer_matched_issue425_configuration_without_added_family"
    ):
        raise V2OptimizationError("issue-426 control is not outer matched")
    expected_stage_ids = [
        "representation_role",
        "lag_and_rolling_window",
        "scaling_and_normalization",
        "lookback_and_winsor",
        "registered_interactions",
    ]
    stage_ids = [str(stage.get("id")) for stage in plan.get("stages", []) if isinstance(stage, Mapping)]
    if stage_ids != expected_stage_ids:
        raise V2OptimizationError("issue-426 optimization stages differ from preregistration")
    required_roles = {
        "direct", "regime", "interaction", "filter_veto", "confidence", "sizing", "risk_modifier"
    }
    roles = plan.get("roles", {})
    if not isinstance(roles, Mapping) or set(roles) != required_roles:
        raise V2OptimizationError("issue-426 role set is invalid")
    expected_role_semantics = {
        "filter_veto": "training_only_family_strength_quantile_binary_exposure_gate",
        "confidence": "training_only_family_strength_empirical_percentile_scales_market_forecast_strength_before_cost_gate",
        "sizing": "HOLD_UNIDENTIFIABLE_UNDER_INHERITED_SINGLE_CONTRACT_EXECUTION_POLICY",
        "risk_modifier": "HOLD_UNIDENTIFIABLE_UNDER_INHERITED_FIXED_RISK_POLICY",
    }
    if any(roles.get(name) != value for name, value in expected_role_semantics.items()):
        raise V2OptimizationError("issue-426 role semantics differ from authoritative plan")
    held_role_policy = plan.get("held_role_policy")
    if not isinstance(held_role_policy, Mapping) or held_role_policy.get(
        "search_budget_consumed"
    ) is not False:
        raise V2OptimizationError("issue-426 held-role search-budget policy is invalid")
    for stage in plan.get("stages", []):
        if not isinstance(stage, Mapping):
            continue
        axes = stage.get("axes", {})
        if not isinstance(axes, Mapping):
            continue
        for name, values in axes.items():
            if not isinstance(values, list) or not values:
                raise V2OptimizationError(f"issue-426 axis {name} is empty")
            definition = registry.variable(str(name))
            for value in values:
                _validate_axis_value(str(name), definition, value)
            declared = definition.get("candidates")
            if isinstance(declared, list) and set(values) != set(declared):
                raise V2OptimizationError(f"issue-426 axis {name} lacks full candidate coverage")
    return {
        "latest_allowed_trade_date": str(plan["latest_allowed_trade_date"]),
        "stage_ids": stage_ids,
        "roles": set(roles),
    }


def validate_issue426_search_plan(
    registry: V2Registry, plan: Mapping[str, Any]
) -> dict[str, Any]:
    registry.assert_search_evidence(str(plan.get("evidence_class")))
    families = {
        str(item.get("family"))
        for item in plan.get("families", [])
        if isinstance(item, Mapping)
    }
    expected = set(_ISSUE426_SOURCES)
    if families != expected:
        raise V2OptimizationError(
            f"issue-426 families differ from registered PIT core: {sorted(families)}"
        )
    registered_families = set(registry.variable("data.feature_family_subset").get("candidates", []))
    if not families.issubset(registered_families):
        raise V2OptimizationError("issue-426 family is absent from V2 registry")
    required_interactions = {str(item) for item in plan.get("required_interactions", [])}
    if "storage×weather×season×volatility" not in required_interactions:
        raise V2OptimizationError("issue-426 plan lacks required storage/weather interaction")
    if plan.get("matched_ablation", {}).get("required") is not True:
        raise V2OptimizationError("issue-426 requires matched market-only ablations")
    return {
        "latest_allowed_trade_date": str(plan["latest_allowed_trade_date"]),
        "families": families,
        "required_interactions": required_interactions,
    }


def _issue426_declared_support_start(
    family: str, source_cfg: Mapping[str, Any]
) -> pd.Timestamp | None:
    policy = source_cfg.get("availability_policy", {})
    raw: object | None = None
    if family == "storage":
        raw = policy.get("exception_registry_coverage_start")
    elif family == "weather":
        raw = source_cfg.get("archive_start")
    elif family == "power":
        window = source_cfg.get("v1_required_window")
        raw = str(window).split(" through ", maxsplit=1)[0] if window else None
    elif family == "positioning":
        raw = policy.get("supported_report_date_start")
    if not raw:
        return None
    value = pd.Timestamp(str(raw), tz="UTC")
    return value.normalize()


def _issue426_research_pit_allowed(
    family: str, source_cfg: Mapping[str, Any]
) -> bool:
    policy = source_cfg.get("availability_policy", {})
    if family == "weather":
        return bool(policy.get("research_pit_allowed_with_immutable_issued_runs", False))
    return bool(policy.get("research_pit_allowed", False))


def build_issue426_source_gate(
    data_cfg: Mapping[str, Any],
    coverage: Mapping[str, Mapping[str, object]],
    *,
    latest_allowed_trade_date: str,
) -> dict[str, object]:
    cutoff = pd.Timestamp(latest_allowed_trade_date, tz="UTC").normalize()
    if cutoff > pd.Timestamp("2022-12-31", tz="UTC"):
        raise V2OptimizationError("issue-426 source gate crosses protected evidence")
    sources = data_cfg.get("sources")
    if not isinstance(sources, Mapping):
        raise V2OptimizationError("issue-426 source gate requires data source configuration")
    scorable: list[str] = []
    held: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    for family, source_name in _ISSUE426_SOURCES.items():
        source_cfg = sources.get(source_name)
        if not isinstance(source_cfg, Mapping):
            raise V2OptimizationError(f"issue-426 source configuration missing: {source_name}")
        observed = coverage.get(family, {})
        reasons: list[str] = []
        if not _issue426_research_pit_allowed(family, source_cfg):
            reasons.append("source_not_research_pit_admissible")
        declared_start = _issue426_declared_support_start(family, source_cfg)
        if declared_start is not None and declared_start > cutoff:
            reasons.append("configured_pit_support_starts_after_development_cutoff")
        snapshot_count = int(observed.get("snapshot_count", 0) or 0)
        earliest_raw = observed.get("earliest_preserved")
        earliest = (
            pd.Timestamp(str(earliest_raw), tz="UTC").normalize()
            if earliest_raw
            else None
        )
        if snapshot_count < 1 or earliest is None:
            reasons.append("preserved_pit_evidence_missing")
        elif earliest > cutoff:
            reasons.append("preserved_pit_evidence_starts_after_development_cutoff")
        disposition = "HOLD" if reasons else "SCORE"
        row = {
            "family": family,
            "source": source_name,
            "disposition": disposition,
            "reasons": list(dict.fromkeys(reasons)),
            "declared_support_start": None if declared_start is None else declared_start.date().isoformat(),
            "earliest_preserved": None if earliest is None else earliest.date().isoformat(),
            "snapshot_count": snapshot_count,
        }
        rows.append(row)
        if disposition == "SCORE":
            scorable.append(family)
        else:
            held.append(row)
    return {
        "latest_allowed_trade_date": latest_allowed_trade_date,
        "scorable_families": scorable,
        "held_families": held,
        "family_gate": rows,
        "protected_evidence_accessed": False,
    }


def build_issue426_historical_source_gate(
    data_cfg: Mapping[str, Any],
    source_plan: Mapping[str, Any],
    coverage: Mapping[str, Mapping[str, object]],
    *,
    latest_allowed_trade_date: str,
) -> dict[str, object]:
    cutoff = pd.Timestamp(latest_allowed_trade_date, tz="UTC").normalize()
    if cutoff > pd.Timestamp("2022-12-31", tz="UTC"):
        raise V2OptimizationError("issue-426 historical source gate crosses protected evidence")
    sources = data_cfg.get("sources")
    families = source_plan.get("families")
    if not isinstance(sources, Mapping) or not isinstance(families, Mapping):
        raise V2OptimizationError("issue-426 historical source gate lacks source configuration")
    if set(families) != set(_ISSUE426_SOURCES):
        raise V2OptimizationError("issue-426 historical source gate family set is invalid")
    scorable: list[str] = []
    held: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    for family, source_name in _ISSUE426_SOURCES.items():
        source_cfg = sources.get(source_name)
        plan_cfg = families.get(family)
        observed = coverage.get(family, {})
        if not isinstance(source_cfg, Mapping) or not isinstance(plan_cfg, Mapping):
            raise V2OptimizationError(f"issue-426 historical source configuration missing: {family}")
        reasons: list[str] = []
        if not _issue426_research_pit_allowed(family, source_cfg):
            reasons.append("source_not_research_pit_admissible")
        disposition_rule = str(plan_cfg.get("disposition", "HOLD"))
        if disposition_rule == "HOLD":
            reasons.append(str(plan_cfg.get("hold_reason", "historical_source_plan_hold")))
        elif disposition_rule not in {
            "SCORE_IF_INTEGRITY_VERIFIED",
            "SCORE_IF_COMPLETE_AND_INTEGRITY_VERIFIED",
        }:
            reasons.append("historical_source_plan_disposition_invalid")
        if observed.get("integrity_verified") is not True:
            reasons.append("historical_evidence_integrity_unverified")
        if (
            disposition_rule == "SCORE_IF_COMPLETE_AND_INTEGRITY_VERIFIED"
            and observed.get("complete") is not True
        ):
            reasons.append("historical_weather_coverage_incomplete")
        support_start_raw = plan_cfg.get("support_start")
        support_start = (
            pd.Timestamp(str(support_start_raw), tz="UTC").normalize()
            if support_start_raw
            else None
        )
        if support_start is None:
            reasons.append("historical_support_start_missing")
        elif support_start > cutoff:
            reasons.append("historical_support_starts_after_development_cutoff")
        snapshot_count = int(observed.get("snapshot_count", 0) or 0)
        earliest_raw = observed.get("earliest_preserved")
        earliest = (
            pd.Timestamp(str(earliest_raw), tz="UTC").normalize()
            if earliest_raw
            else None
        )
        if snapshot_count < 1 or earliest is None:
            reasons.append("historical_pit_evidence_missing")
        elif earliest > cutoff:
            reasons.append("historical_pit_evidence_starts_after_development_cutoff")
        row = {
            "family": family,
            "source": source_name,
            "promoted_source_id": plan_cfg.get("source_id"),
            "disposition": "HOLD" if reasons else "SCORE",
            "reasons": list(dict.fromkeys(reasons)),
            "declared_support_start": None if support_start is None else support_start.date().isoformat(),
            "earliest_preserved": None if earliest is None else earliest.date().isoformat(),
            "snapshot_count": snapshot_count,
        }
        rows.append(row)
        if row["disposition"] == "SCORE":
            scorable.append(family)
        else:
            held.append(row)
    return {
        "latest_allowed_trade_date": latest_allowed_trade_date,
        "scorable_families": scorable,
        "held_families": held,
        "family_gate": rows,
        "protected_evidence_accessed": False,
    }


def inventory_issue426_historical_coverage(
    raw_root: Path, source_plan: Mapping[str, Any]
) -> dict[str, dict[str, object]]:
    root = Path(raw_root)
    families = source_plan.get("families")
    if not isinstance(families, Mapping) or set(families) != set(_ISSUE426_SOURCES):
        raise V2OptimizationError("issue-426 historical inventory family set is invalid")
    result: dict[str, dict[str, object]] = {}
    for family in _ISSUE426_SOURCES:
        cfg = families[family]
        if not isinstance(cfg, Mapping):
            raise V2OptimizationError(f"issue-426 historical inventory config invalid: {family}")
        source_id = str(cfg.get("source_id", ""))
        support_start = str(cfg.get("support_start", "")) or None
        support_end = str(cfg.get("support_end", "")) or None
        if family in {"storage", "positioning"}:
            manifest_path = root / str(cfg.get("manifest", ""))
            normalized_path = root / str(cfg.get("normalized_file", ""))
            integrity = False
            count = 0
            earliest = None
            latest = None
            manifest_sha = None
            if manifest_path.is_file() and normalized_path.is_file():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                expected_sha = str(manifest.get("normalized_sha256", ""))
                normalized = pd.read_csv(normalized_path, usecols=["observed_for"])
                observed = pd.to_datetime(normalized["observed_for"], utc=True, errors="raise").sort_values()
                count = len(observed)
                earliest = None if observed.empty else observed.iloc[0].date().isoformat()
                latest = None if observed.empty else observed.iloc[-1].date().isoformat()
                manifest_first = manifest.get("first_observed_for")
                manifest_last = manifest.get("last_observed_for")
                manifest_rows = int(manifest.get("rows", 0) or 0)
                cadence_ok = False
                if not observed.empty and observed.is_unique and support_start and support_end:
                    normalized_dates = observed.dt.normalize().reset_index(drop=True)
                    if family == "storage":
                        expected_dates = pd.Series(
                            pd.date_range(support_start, support_end, freq="7D", tz="UTC")
                        )
                        cadence_ok = normalized_dates.equals(expected_dates)
                    else:
                        gaps = normalized_dates.diff().dropna().dt.days
                        cadence_ok = bool(
                            normalized_dates.dt.weekday.isin({0, 1}).all()
                            and gaps.between(6, 8, inclusive="both").all()
                        )
                integrity = (
                    manifest.get("source_id") == source_id
                    and expected_sha != ""
                    and _sha256_file(normalized_path) == expected_sha
                    and manifest_rows == count
                    and earliest == support_start
                    and latest == support_end
                    and manifest_first is not None
                    and pd.Timestamp(str(manifest_first)).date().isoformat() == earliest
                    and manifest_last is not None
                    and pd.Timestamp(str(manifest_last)).date().isoformat() == latest
                    and manifest.get("availability_basis") == cfg.get("availability_basis")
                    and cadence_ok
                )
                manifest_sha = _sha256_file(manifest_path)
            result[family] = {
                "source_id": source_id,
                "integrity_verified": integrity,
                "complete": integrity,
                "snapshot_count": count,
                "earliest_preserved": earliest,
                "latest_preserved": latest,
                "manifest_index_sha256": manifest_sha,
            }
            continue
        if family == "power":
            manifest_path = root / str(cfg.get("manifest", ""))
            integrity = False
            count = 0
            manifest_sha = None
            if manifest_path.is_file():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                years = manifest.get("years")
                integrity = manifest.get("source_id") == source_id and isinstance(years, Mapping)
                if integrity:
                    for item in years.values():
                        if not isinstance(item, Mapping):
                            integrity = False
                            break
                        normalized_name = str(item.get("normalized_file", ""))
                        expected_sha = str(item.get("normalized_sha256", ""))
                        candidate = manifest_path.parent / normalized_name
                        if (
                            not candidate.is_file()
                            or not expected_sha
                            or _sha256_file(candidate) != expected_sha
                        ):
                            integrity = False
                            break
                count = int(manifest.get("total_rows", 0) or 0)
                manifest_sha = _sha256_file(manifest_path)
            result[family] = {
                "source_id": source_id,
                "integrity_verified": integrity,
                "complete": integrity,
                "snapshot_count": count,
                "earliest_preserved": support_start if integrity else None,
                "latest_preserved": support_end if integrity else None,
                "manifest_index_sha256": manifest_sha,
            }
            continue
        manifests = sorted(root.glob(str(cfg.get("manifest_glob", ""))))
        dates: list[pd.Timestamp] = []
        integrity = bool(manifests)
        identities: list[dict[str, object]] = []
        canonical_weather_leads = list(range(24, 169, 3))
        canonical_weather_anchors = [
            "midwest_chicago",
            "northeast_new_york",
            "southeast_atlanta",
            "south_central_houston",
        ]
        for manifest_path in manifests:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("source_id") != source_id:
                integrity = False
            issue_date = pd.Timestamp(str(manifest.get("issue_date")), tz="UTC").normalize()
            if family == "weather":
                if (
                    manifest_path.parent.name != issue_date.strftime("%Y%m%d")
                    or manifest_path.parent.parent.name != str(issue_date.year)
                ):
                    integrity = False
                actual_leads = sorted(int(value) for value in manifest.get("forecast_lead_hours", []))
                has_requested = "requested_forecast_lead_hours" in manifest
                requested_leads = (
                    sorted(int(value) for value in manifest.get("requested_forecast_lead_hours", []))
                    if has_requested
                    else canonical_weather_leads
                )
                missing_items = manifest.get("archive_missing_leads", [])
                missing_inventory_valid = isinstance(missing_items, list) and all(
                    isinstance(item, Mapping)
                    and "lead_hours" in item
                    and str(item.get("reason", "")) in _ISSUE426_WEATHER_ARCHIVE_MISSING_REASONS
                    for item in missing_items
                )
                declared_missing = sorted(
                    int(item["lead_hours"])
                    for item in missing_items
                    if isinstance(item, Mapping) and "lead_hours" in item
                )
                actual_missing = sorted(set(canonical_weather_leads) - set(actual_leads))
                if (
                    manifest.get("cycle_utc_hour") != 0
                    or list(manifest.get("anchor_ids", [])) != canonical_weather_anchors
                    or requested_leads != canonical_weather_leads
                    or not set(actual_leads).issubset(set(canonical_weather_leads))
                    or not missing_inventory_valid
                    or len(declared_missing) != len(set(declared_missing))
                    or (not has_requested and (actual_leads != canonical_weather_leads or declared_missing))
                    or (has_requested and declared_missing != actual_missing)
                    or int(manifest.get("record_count", -1)) != len(actual_leads) * 4
                    or int(manifest.get("payload_count", -1)) != len(actual_leads)
                ):
                    integrity = False
            dates.append(issue_date)
            files = manifest.get("files")
            if not isinstance(files, Mapping) or not files:
                integrity = False
                continue
            for name, metadata in files.items():
                if not isinstance(metadata, Mapping):
                    integrity = False
                    continue
                candidate = manifest_path.parent / str(name)
                expected_sha = str(metadata.get("sha256", ""))
                expected_bytes = int(metadata.get("bytes", -1))
                if (
                    not candidate.is_file()
                    or candidate.stat().st_size != expected_bytes
                    or not expected_sha
                    or _sha256_file(candidate) != expected_sha
                ):
                    integrity = False
            identities.append(
                {
                    "path": manifest_path.relative_to(root).as_posix(),
                    "sha256": _sha256_file(manifest_path),
                }
            )
        expected_count = int(cfg.get("expected_issue_days", 0) or 0)
        unique_dates = sorted(set(dates))
        expected_dates = (
            []
            if not support_start or not support_end
            else list(pd.date_range(support_start, support_end, freq="D", tz="UTC"))
        )
        complete = (
            integrity
            and expected_count > 0
            and len(unique_dates) == expected_count
            and unique_dates == expected_dates
        )
        result[family] = {
            "source_id": source_id,
            "integrity_verified": integrity,
            "complete": complete,
            "snapshot_count": len(unique_dates),
            "earliest_preserved": None if not unique_dates else unique_dates[0].date().isoformat(),
            "latest_preserved": None if not unique_dates else unique_dates[-1].date().isoformat(),
            "manifest_index_sha256": _sha256_payload(identities),
        }
    return result


def _issue426_snapshot_date(family: str, name: str) -> pd.Timestamp:
    try:
        if family == "storage":
            raw = name[:10]
        elif family == "weather":
            raw = f"{name[:4]}-{name[4:6]}-{name[6:8]}"
        elif family == "power":
            raw = f"{name[:4]}-{name[4:6]}-01"
        elif family == "positioning":
            raw = f"{name[:4]}-01-01"
        else:
            raise V2OptimizationError(f"unsupported issue-426 family: {family}")
        return pd.Timestamp(raw, tz="UTC").normalize()
    except (ValueError, TypeError) as exc:
        raise V2OptimizationError(
            f"issue-426 snapshot identity is invalid for {family}: {name}"
        ) from exc


def inventory_issue426_snapshot_coverage(snapshot_root: Path) -> dict[str, dict[str, object]]:
    root = Path(snapshot_root)
    directories = {
        "storage": "eia_wngsr",
        "weather": "open_meteo_v1",
        "power": "nyiso_p7",
        "positioning": "cftc_cot",
    }
    result: dict[str, dict[str, object]] = {}
    for family, directory in directories.items():
        manifests = sorted((root / directory).glob("*/manifest.json"))
        dates = [_issue426_snapshot_date(family, path.parent.name) for path in manifests]
        result[family] = {
            "snapshot_count": len(manifests),
            "earliest_preserved": None if not dates else min(dates).date().isoformat(),
            "latest_preserved": None if not dates else max(dates).date().isoformat(),
            "manifest_index_sha256": _sha256_payload(
                [path.relative_to(root).as_posix() for path in manifests]
            ),
        }
    return result


def _load_issue425_control(path: Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("issue") != 425 or payload.get("evidence_class") != "development":
        raise V2OptimizationError("issue-426 market control is not issue-425 development evidence")
    for key in (
        "protected_confirmation_accessed",
        "true_forward_accessed",
        "saxo_sim_accessed",
        "saxo_live_accessed",
    ):
        if payload.get(key) is not False:
            raise V2OptimizationError(f"issue-426 market control crossed protected evidence: {key}")
    score = payload.get("nested_selection_score")
    handoff = payload.get("latest_preregistered_handoff_config")
    if not isinstance(score, Mapping) or not isinstance(handoff, Mapping):
        raise V2OptimizationError("issue-426 market control lacks issue-425 handoff evidence")
    return {
        "issue425_result_sha256": _sha256_file(Path(path)),
        "nested_selection_score": dict(score),
        "handoff_config": dict(handoff),
    }


def load_issue426_outer_matched_controls(path: Path) -> dict[str, dict[str, object]]:
    _load_issue425_control(path)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    nested = payload.get("nested_outer")
    if not isinstance(nested, list) or not nested:
        raise V2OptimizationError("issue-426 market control lacks nested outer evidence")
    controls: dict[str, dict[str, object]] = {}
    for item in nested:
        if not isinstance(item, Mapping):
            raise V2OptimizationError("issue-426 nested outer control is invalid")
        block = item.get("outer_block")
        search = item.get("search")
        selected = item.get("selected_outer_result")
        if not all(isinstance(value, Mapping) for value in (block, search, selected)):
            raise V2OptimizationError("issue-426 nested outer control lacks block/search/result")
        block_id = str(block.get("id", ""))
        config = search.get("selected_config")
        monthly_score = selected.get("monthly_score")
        if not block_id or not isinstance(config, Mapping) or not isinstance(monthly_score, Mapping):
            raise V2OptimizationError("issue-426 nested outer control lacks config or score")
        if block_id in controls:
            raise V2OptimizationError(f"issue-426 duplicate outer control: {block_id}")
        controls[block_id] = {
            "outer_block_id": block_id,
            "outer_block": dict(block),
            "config": dict(config),
            "monthly_score": dict(monthly_score),
            "selected_candidate_id": str(search.get("selected_candidate_id", "")),
        }
    return controls


def run_issue426_development_source_gate(
    *,
    registry_path: Path,
    search_plan_path: Path,
    data_sources_path: Path,
    issue425_result_path: Path,
    snapshot_root: Path,
) -> dict[str, object]:
    registry = load_v2_registry(registry_path)
    plan = load_issue426_search_plan(search_plan_path)
    validation = validate_issue426_search_plan(registry, plan)
    data_cfg = json.loads(Path(data_sources_path).read_text(encoding="utf-8"))
    coverage = inventory_issue426_snapshot_coverage(snapshot_root)
    gate = build_issue426_source_gate(
        data_cfg,
        coverage,
        latest_allowed_trade_date=str(validation["latest_allowed_trade_date"]),
    )
    market_control = _load_issue425_control(issue425_result_path)
    held_families = {str(item["family"]) for item in gate["held_families"]}
    interaction_dispositions: list[dict[str, object]] = []
    for interaction in sorted(validation["required_interactions"]):
        blocked_by = sorted(
            family for family in held_families if family in str(interaction)
        )
        interaction_dispositions.append(
            {
                "interaction": interaction,
                "disposition": "HOLD" if blocked_by else "READY",
                "blocked_by": blocked_by,
            }
        )
    attempts = [
        {
            **dict(item),
            "attempt_type": "source_gate",
            "eligible_for_scoring": item["disposition"] == "SCORE",
            "search_budget_consumed": False,
        }
        for item in gate["family_gate"]
    ]
    scorable = list(gate["scorable_families"])
    status = (
        "ready_for_family_scoring"
        if scorable
        else "complete_development_only_source_gated"
    )
    return {
        "schema_version": 1,
        "issue": 426,
        "programme_issue": 393,
        "status": status,
        "evidence_class": "development",
        "latest_allowed_trade_date": str(validation["latest_allowed_trade_date"]),
        "protected_confirmation_accessed": False,
        "true_forward_accessed": False,
        "prospective_paper_accessed": False,
        "saxo_sim_accessed": False,
        "saxo_live_accessed": False,
        "registry_id": registry.registry_id,
        "registry_sha256": _sha256_file(Path(registry_path)),
        "search_plan_sha256": _sha256_file(Path(search_plan_path)),
        "data_sources_sha256": _sha256_file(Path(data_sources_path)),
        "code_id": _sha256_file(Path(__file__)),
        "snapshot_coverage_sha256": _sha256_payload(coverage),
        "snapshot_coverage": coverage,
        "source_gate": gate,
        "source_gate_attempt_count": len(attempts),
        "attempt_history": attempts,
        "scorable_families": scorable,
        "trial_count": 0,
        "market_only_control": market_control,
        "interaction_dispositions": interaction_dispositions,
        "segregated_families": dict(plan.get("segregated_families", {})),
        "revisit_triggers": list(plan.get("revisit_triggers", [])),
        "claim_boundary": (
            "development-only source-gate result; no exogenous edge claim and no "
            "protected evidence access"
        ),
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


def _issue426_prior_seasonal_mean(
    values: pd.Series, observed_for: pd.Series
) -> pd.Series:
    week = pd.to_datetime(observed_for, utc=True, errors="raise").dt.isocalendar().week
    working = pd.DataFrame({"value": pd.to_numeric(values, errors="raise"), "week": week})
    return working.groupby("week", sort=False)["value"].transform(
        lambda series: series.shift(1).expanding(min_periods=1).mean()
    )


def _issue426_signed_note_value(note: object, pattern: str) -> float:
    if not isinstance(note, str) or not note.strip():
        return 0.0
    match = re.search(pattern, note, flags=re.IGNORECASE)
    if match is None:
        return 0.0
    direction = match.group(1).lower()
    value = float(match.group(2))
    return value if direction in {"increase", "increased"} else -value


def build_issue426_storage_family_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(Path(path))
    required = {
        "observed_for",
        "available_at",
        "storage_lower48_bcf",
        "storage_east_bcf",
        "storage_midwest_bcf",
        "storage_mountain_bcf",
        "storage_pacific_bcf",
        "storage_south_central_bcf",
        "release_note",
    }
    if not required.issubset(frame.columns):
        missing = sorted(required - set(frame.columns))
        raise V2OptimizationError(f"issue-426 storage evidence lacks columns: {missing}")
    frame["observed_for"] = pd.to_datetime(frame["observed_for"], utc=True, errors="raise")
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True, errors="raise")
    frame = frame.sort_values("available_at", kind="stable").reset_index(drop=True)
    if frame["available_at"].duplicated().any():
        raise V2OptimizationError("issue-426 storage availability timestamps are not unique")
    if frame["available_at"].lt(frame["observed_for"]).any():
        raise V2OptimizationError("issue-426 storage evidence is available before observation")
    level = pd.to_numeric(frame["storage_lower48_bcf"], errors="raise").astype(float)
    change = level.diff()
    seasonal_level = _issue426_prior_seasonal_mean(level, frame["observed_for"])
    seasonal_change = _issue426_prior_seasonal_mean(change, frame["observed_for"])
    note = frame["release_note"]
    out = pd.DataFrame(
        {
            "observed_for": frame["observed_for"],
            "available_at": frame["available_at"],
            "lower48_bcf": level,
            "change_bcf": change,
            "seasonal_deviation_bcf": level - seasonal_level,
            "release_surprise_bcf": change - seasonal_change,
            "days_since_previous_release": frame["available_at"].diff().dt.total_seconds() / 86400.0,
            "reclassification_event": note.fillna("").astype(str).str.contains(
                "reclass", case=False, regex=False
            ).astype(float),
            "reclassification_bcf": note.map(
                lambda value: _issue426_signed_note_value(
                    value,
                    r"\b(increased|decreased)\b.*?approximately\s+([0-9]+(?:\.[0-9]+)?)\s+Bcf",
                )
            ),
            "implied_flow_bcf": note.map(
                lambda value: _issue426_signed_note_value(
                    value,
                    r"implied flow.*?\b(increase|decrease)\b\s+of\s+([0-9]+(?:\.[0-9]+)?)\s+Bcf",
                )
            ),
        }
    )
    for column in (
        "storage_east_bcf",
        "storage_midwest_bcf",
        "storage_mountain_bcf",
        "storage_pacific_bcf",
        "storage_south_central_bcf",
    ):
        out[column.removeprefix("storage_")] = pd.to_numeric(frame[column], errors="raise").astype(float)
    return out


def build_issue426_positioning_family_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(Path(path))
    required = {
        "observed_for",
        "available_at",
        "open_interest",
        "managed_money_net",
        "producer_merchant_net",
        "swap_dealer_net",
    }
    if not required.issubset(frame.columns):
        missing = sorted(required - set(frame.columns))
        raise V2OptimizationError(f"issue-426 positioning evidence lacks columns: {missing}")
    frame["observed_for"] = pd.to_datetime(frame["observed_for"], utc=True, errors="raise")
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True, errors="raise")
    frame = frame.sort_values("available_at", kind="stable").reset_index(drop=True)
    if frame["available_at"].duplicated().any():
        raise V2OptimizationError("issue-426 positioning availability timestamps are not unique")
    if frame["available_at"].lt(frame["observed_for"]).any():
        raise V2OptimizationError("issue-426 positioning evidence is available before observation")
    open_interest = pd.to_numeric(frame["open_interest"], errors="raise").astype(float)
    if open_interest.le(0.0).any():
        raise V2OptimizationError("issue-426 positioning open interest must be positive")
    managed = pd.to_numeric(frame["managed_money_net"], errors="raise").astype(float)
    producer = pd.to_numeric(frame["producer_merchant_net"], errors="raise").astype(float)
    swap = pd.to_numeric(frame["swap_dealer_net"], errors="raise").astype(float)
    history = managed.shift(1).rolling(window=52, min_periods=13)
    mean = history.mean()
    std = history.std(ddof=0).replace(0.0, np.nan)
    return pd.DataFrame(
        {
            "observed_for": frame["observed_for"],
            "available_at": frame["available_at"],
            "managed_money_net": managed,
            "managed_money_pct_oi": managed / open_interest,
            "producer_merchant_net": producer,
            "producer_merchant_pct_oi": producer / open_interest,
            "swap_dealer_net": swap,
            "swap_dealer_pct_oi": swap / open_interest,
            "managed_money_change": managed.diff(),
            "producer_merchant_change": producer.diff(),
            "swap_dealer_change": swap.diff(),
            "managed_money_zscore_52": (managed - mean) / std,
        }
    )


def build_issue426_weather_family_frame(
    raw_root: Path,
    *,
    availability_delay_minutes: int = 370,
    degree_day_base_c: float = 18.3333333333,
) -> pd.DataFrame:
    root = Path(raw_root)
    manifests = sorted(root.glob("*/*/manifest.json"))
    if not manifests:
        raise V2OptimizationError("issue-426 weather archive has no daily manifests")
    expected_source_id = "ncar_gdex_d084001_gfs_0p25_issued_00utc"
    expected_anchors = {
        "midwest_chicago",
        "northeast_new_york",
        "southeast_atlanta",
        "south_central_houston",
    }
    records: list[dict[str, object]] = []
    previous_frame: pd.DataFrame | None = None
    previous_issue: pd.Timestamp | None = None
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("source_id") != expected_source_id:
            raise V2OptimizationError("issue-426 weather source identity mismatch")
        issue = pd.Timestamp(str(manifest.get("issue_date")), tz="UTC").normalize()
        if (
            manifest_path.parent.name != issue.strftime("%Y%m%d")
            or manifest_path.parent.parent.name != str(issue.year)
        ):
            raise V2OptimizationError("issue-426 weather manifest path does not match issue date")
        csv_path = manifest_path.parent / "anchor_temperature.csv"
        metadata = manifest.get("files", {}).get("anchor_temperature.csv", {})
        expected_sha = str(metadata.get("sha256", "")) if isinstance(metadata, Mapping) else ""
        if not csv_path.is_file() or not expected_sha or _sha256_file(csv_path) != expected_sha:
            raise V2OptimizationError(
                f"issue-426 weather daily integrity failed: {issue.date().isoformat()}"
            )
        frame = pd.read_csv(csv_path)
        required = {
            "issued_at",
            "forecast_valid_at",
            "lead_hours",
            "anchor_id",
            "temperature_c",
        }
        if not required.issubset(frame.columns):
            missing = sorted(required - set(frame.columns))
            raise V2OptimizationError(
                f"issue-426 weather evidence lacks columns: {missing}"
            )
        frame["issued_at"] = pd.to_datetime(frame["issued_at"], utc=True, errors="raise")
        frame["forecast_valid_at"] = pd.to_datetime(
            frame["forecast_valid_at"], utc=True, errors="raise"
        )
        frame["lead_hours"] = pd.to_numeric(frame["lead_hours"], errors="raise").astype(int)
        frame["temperature_c"] = pd.to_numeric(
            frame["temperature_c"], errors="raise"
        ).astype(float)
        if not frame["issued_at"].eq(issue).all():
            raise V2OptimizationError("issue-426 weather rows do not match exact 00 UTC issue cycle")
        if frame[["lead_hours", "anchor_id"]].duplicated().any():
            raise V2OptimizationError("issue-426 weather daily anchor/lead keys are not unique")
        anchors = set(frame["anchor_id"].astype(str))
        if anchors != expected_anchors:
            raise V2OptimizationError(
                f"issue-426 weather anchor set is invalid: {sorted(anchors)}"
            )
        canonical_requested_leads = list(range(24, 169, 3))
        has_requested_inventory = "requested_forecast_lead_hours" in manifest
        requested_leads = [
            int(value)
            for value in manifest.get(
                "requested_forecast_lead_hours", canonical_requested_leads
            )
        ]
        actual_leads = sorted(frame["lead_hours"].unique().tolist())
        declared_leads = [int(value) for value in manifest.get("forecast_lead_hours", [])]
        if (
            requested_leads != canonical_requested_leads
            or actual_leads != sorted(declared_leads)
            or not set(actual_leads).issubset(set(requested_leads))
            or (not has_requested_inventory and actual_leads != canonical_requested_leads)
        ):
            raise V2OptimizationError("issue-426 weather lead inventory is inconsistent")
        missing_items = manifest.get("archive_missing_leads", [])
        if not isinstance(missing_items, list) or any(
            not isinstance(item, Mapping)
            or "lead_hours" not in item
            or str(item.get("reason", "")) not in _ISSUE426_WEATHER_ARCHIVE_MISSING_REASONS
            for item in missing_items
        ):
            raise V2OptimizationError("issue-426 weather archive omission reason is invalid")
        declared_missing = sorted(int(item["lead_hours"]) for item in missing_items)
        if len(declared_missing) != len(set(declared_missing)):
            raise V2OptimizationError("issue-426 weather archive omission inventory is duplicated")
        if not has_requested_inventory and declared_missing:
            raise V2OptimizationError("issue-426 legacy weather manifest cannot declare omissions")
        if has_requested_inventory:
            actual_missing = sorted(set(requested_leads) - set(actual_leads))
            if declared_missing != actual_missing:
                raise V2OptimizationError(
                    "issue-426 weather archive omissions are not exactly declared"
                )
        anchors_per_lead = frame.groupby("lead_hours")["anchor_id"].nunique()
        if not anchors_per_lead.eq(len(expected_anchors)).all():
            raise V2OptimizationError("issue-426 weather lead is missing one or more anchors")
        expected_valid_at = frame["issued_at"] + pd.to_timedelta(frame["lead_hours"], unit="h")
        if not frame["forecast_valid_at"].eq(expected_valid_at).all():
            raise V2OptimizationError("issue-426 weather valid timestamps do not match lead hours")
        temperature = frame["temperature_c"]
        frame["hdd65"] = (float(degree_day_base_c) - temperature).clip(lower=0.0)
        frame["cdd65"] = (temperature - float(degree_day_base_c)).clip(lower=0.0)
        anchor_means = frame.groupby("anchor_id", sort=True)["temperature_c"].mean()
        near = frame.loc[frame["lead_hours"].between(24, 72, inclusive="both")]
        far = frame.loc[frame["lead_hours"].between(120, 168, inclusive="both")]
        if near.empty or far.empty:
            raise V2OptimizationError("issue-426 weather archive lacks near/far horizon support")
        revision_temp = math.nan
        revision_hdd = math.nan
        if (
            previous_frame is not None
            and previous_issue is not None
            and issue - previous_issue == pd.Timedelta(days=1)
        ):
            overlap = frame.merge(
                previous_frame[
                    ["forecast_valid_at", "anchor_id", "temperature_c", "hdd65"]
                ],
                on=["forecast_valid_at", "anchor_id"],
                how="inner",
                suffixes=("_current", "_previous"),
                validate="one_to_one",
            )
            if not overlap.empty:
                revision_temp = float(
                    (overlap["temperature_c_current"] - overlap["temperature_c_previous"]).mean()
                )
                revision_hdd = float(
                    (overlap["hdd65_current"] - overlap["hdd65_previous"]).mean()
                )
        record: dict[str, object] = {
            "observed_for": issue,
            "available_at": issue + pd.Timedelta(minutes=int(availability_delay_minutes)),
            "temp_mean_c": float(temperature.mean()),
            "hdd65_mean_c": float(frame["hdd65"].mean()),
            "cdd65_mean_c": float(frame["cdd65"].mean()),
            "revision_temp_mean_c": revision_temp,
            "revision_hdd65_mean_c": revision_hdd,
            "near_temp_mean_c": float(near["temperature_c"].mean()),
            "far_temp_mean_c": float(far["temperature_c"].mean()),
            "near_minus_far_temp_c": float(
                near["temperature_c"].mean() - far["temperature_c"].mean()
            ),
            "near_hdd65_mean_c": float(near["hdd65"].mean()),
            "far_hdd65_mean_c": float(far["hdd65"].mean()),
            "temp_dispersion_c": float(temperature.std(ddof=0)),
            "anchor_temp_dispersion_c": float(anchor_means.std(ddof=0)),
            "lead_coverage_fraction": float(len(actual_leads) / len(requested_leads)),
        }
        for anchor_id in sorted(expected_anchors):
            record[f"{anchor_id}_temp_mean_c"] = float(anchor_means.loc[anchor_id])
        records.append(record)
        previous_frame = frame
        previous_issue = issue
    out = pd.DataFrame(records).sort_values("available_at", kind="stable").reset_index(drop=True)
    if out["available_at"].duplicated().any():
        raise V2OptimizationError("issue-426 weather availability timestamps are not unique")
    seasonal_temp = _issue426_prior_seasonal_mean(out["temp_mean_c"], out["observed_for"])
    seasonal_hdd = _issue426_prior_seasonal_mean(out["hdd65_mean_c"], out["observed_for"])
    out["temp_seasonal_anomaly_c"] = out["temp_mean_c"] - seasonal_temp
    out["hdd65_seasonal_anomaly_c"] = out["hdd65_mean_c"] - seasonal_hdd
    out["revision_error_proxy_mae_30d_c"] = (
        out["revision_temp_mean_c"].abs().shift(1).rolling(window=30, min_periods=10).mean()
    )
    return out


def merge_issue426_pit_family(
    market_features: pd.DataFrame,
    family_frame: pd.DataFrame,
    *,
    family: str,
    value_columns: Sequence[str],
    max_staleness: pd.Timedelta,
    latest_allowed_trade_date: str,
) -> pd.DataFrame:
    if family not in _ISSUE426_SOURCES:
        raise V2OptimizationError(f"unsupported issue-426 family: {family}")
    required_market = {"trade_date", "available_at"}
    if not required_market.issubset(market_features.columns):
        raise V2OptimizationError("issue-426 market features lack time columns")
    required_family = {"available_at", *value_columns}
    if not required_family.issubset(family_frame.columns):
        missing = sorted(required_family - set(family_frame.columns))
        raise V2OptimizationError(f"issue-426 family frame lacks columns: {missing}")
    cutoff = pd.Timestamp(latest_allowed_trade_date, tz="UTC").normalize()
    left = market_features.copy()
    left["trade_date"] = pd.to_datetime(left["trade_date"], utc=True, errors="raise")
    left["available_at"] = pd.to_datetime(left["available_at"], utc=True, errors="raise")
    if left["trade_date"].dt.normalize().gt(cutoff).any():
        raise V2OptimizationError("issue-426 market features cross development cutoff")
    right = family_frame[["available_at", *value_columns]].copy()
    right["available_at"] = pd.to_datetime(right["available_at"], utc=True, errors="raise")
    if right["available_at"].duplicated().any():
        raise V2OptimizationError("issue-426 family availability timestamps must be unique")
    prefix = f"feature_{family}_"
    renamed = {column: f"{prefix}{column}" for column in value_columns}
    family_time = f"{prefix}available_at"
    right = right.rename(columns={"available_at": family_time, **renamed})
    merged = pd.merge_asof(
        left.sort_values("available_at", kind="stable"),
        right.sort_values(family_time, kind="stable"),
        left_on="available_at",
        right_on=family_time,
        direction="backward",
        tolerance=max_staleness,
        allow_exact_matches=True,
    ).sort_values("trade_date", kind="stable").reset_index(drop=True)
    matched = merged[family_time].notna()
    if (
        merged.loc[matched, family_time]
        .gt(merged.loc[matched, "available_at"])
        .any()
    ):
        raise V2OptimizationError("issue-426 PIT join used future family evidence")
    return merged


def _issue426_feature_columns(
    frame: pd.DataFrame,
    family: str,
    representation: str | None = None,
    market_control_family: str = "market",
) -> list[str]:
    market = _issue425_family_columns(frame, market_control_family)
    family_columns = sorted(
        column
        for column in frame
        if column.startswith(f"feature_{family}_")
        and not column.endswith("available_at")
    )
    if representation:
        suffixes = _ISSUE426_REPRESENTATION_SUFFIXES.get(family, {}).get(representation)
        if not suffixes:
            raise V2OptimizationError(
                f"unsupported issue-426 representation: {family}/{representation}"
            )
        family_columns = [
            column for column in family_columns if any(column.endswith(suffix) for suffix in suffixes)
        ]
    if not family_columns:
        raise V2OptimizationError(f"issue-426 family {family} has no feature columns")
    return [*market, *family_columns]


def prepare_issue426_features(
    features: pd.DataFrame, config: Mapping[str, object]
) -> tuple[pd.DataFrame, list[str]]:
    required = {"trade_date", "available_at"}
    if not required.issubset(features.columns):
        raise V2OptimizationError("issue-426 features lack time columns")
    frame = features.copy().sort_values("trade_date", kind="stable")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True, errors="raise")
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True, errors="raise")
    _issue425_return_transform(frame, str(config["return_transform"]))
    family = str(config["feature_family_subset"])
    if family not in _ISSUE426_SOURCES:
        raise V2OptimizationError(f"unsupported issue-426 feature family: {family}")
    representation_raw = config.get("representation")
    representation = None if representation_raw is None else str(representation_raw)
    market_control_family = str(config.get("market_control_family", "market"))
    base_columns = _issue426_feature_columns(
        frame,
        family,
        representation,
        market_control_family,
    )
    numeric = frame[base_columns].apply(pd.to_numeric, errors="raise").astype(float)
    family_columns = [
        column for column in base_columns if column.startswith(f"feature_{family}_")
    ]
    role = str(config.get("role", "direct"))
    allowed_roles = {
        "direct", "regime", "interaction", "filter_veto", "confidence", "sizing", "risk_modifier"
    }
    if role not in allowed_roles:
        raise V2OptimizationError(f"unsupported issue-426 role: {role}")
    interaction_context: list[tuple[str, str]] = []
    if role == "regime":
        interaction_context = [
            ("season_sin", "feature_season_sin"),
            ("season_cos", "feature_season_cos"),
            ("vol20", "feature_vol_20"),
        ]
    elif role == "interaction":
        if family in {"storage", "weather"}:
            interaction_context = [
                ("season_sin", "feature_season_sin"),
                ("season_cos", "feature_season_cos"),
            ]
        elif family == "positioning":
            interaction_context = [("vol20", "feature_vol_20")]
        elif family == "power":
            raise V2OptimizationError("issue-426 power interaction requires weather companion evidence")
    if interaction_context:
        interactions: dict[str, pd.Series] = {}
        for family_column in family_columns:
            family_values = pd.to_numeric(frame[family_column], errors="raise").astype(float)
            for suffix, market_column in interaction_context:
                if market_column not in frame:
                    raise V2OptimizationError(
                        f"issue-426 role {role} lacks interaction context {market_column}"
                    )
                market_values = pd.to_numeric(frame[market_column], errors="raise").astype(float)
                interactions[f"{family_column}__x_{suffix}"] = family_values * market_values
        numeric = pd.concat([numeric, pd.DataFrame(interactions, index=frame.index)], axis=1)
    lookback = int(config["lookback_sessions"])
    lag = int(config["lag_sessions"])
    stat_window = int(config["rolling_stat_window_sessions"])
    norm_window = int(config["normalization_window_sessions"])
    winsor = float(config["winsor_quantile"])
    if min(lookback, lag, stat_window, norm_window) < 1:
        raise V2OptimizationError("issue-426 transform windows must be positive")
    if not 0.0 <= winsor < 0.5:
        raise V2OptimizationError("issue-426 winsor quantile is invalid")
    if winsor > 0.0:
        shifted = numeric.shift(1)
        history = shifted.rolling(window=lookback, min_periods=min(20, lookback))
        lower = history.quantile(winsor)
        upper = history.quantile(1.0 - winsor)
        numeric = numeric.clip(lower=lower, upper=upper, axis=1)
    lagged = numeric.shift(lag)
    history = numeric.shift(1).rolling(window=stat_window, min_periods=stat_window)
    rolling_mean = history.mean().add_suffix(f"__mean{stat_window}")
    rolling_std = history.std(ddof=0).add_suffix(f"__std{stat_window}")
    derived = pd.concat([lagged, rolling_mean, rolling_std], axis=1)
    scaled = _issue425_rolling_scale(derived, str(config["scaling"]), norm_window)
    output_columns = list(scaled.columns)
    output = pd.concat(
        [frame[["trade_date", "available_at"]], scaled], axis=1
    ).replace([np.inf, -np.inf], np.nan)
    output = output.dropna(subset=output_columns).copy()
    if output.empty:
        raise V2OptimizationError("issue-426 transforms produced no complete rows")
    if not np.isfinite(output[output_columns].to_numpy(dtype=float)).all():
        raise V2OptimizationError("issue-426 transformed features are non-finite")
    return output, output_columns


def prepare_issue426_storage_weather_interaction_features(
    features: pd.DataFrame,
    config: Mapping[str, object],
    *,
    storage_representation: str,
    weather_representation: str,
) -> tuple[pd.DataFrame, list[str]]:
    required = {
        "trade_date",
        "available_at",
        "feature_season_sin",
        "feature_season_cos",
        "feature_vol_20",
    }
    if not required.issubset(features.columns):
        missing = sorted(required - set(features.columns))
        raise V2OptimizationError(
            f"issue-426 combined interaction lacks context columns: {missing}"
        )
    frame = features.copy().sort_values("trade_date", kind="stable")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True, errors="raise")
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True, errors="raise")
    _issue425_return_transform(frame, str(config["transforms.return_transform"]))
    market_columns = _issue425_family_columns(
        frame, str(config["data.feature_family_subset"])
    )

    def representation_columns(family: str, representation: str) -> list[str]:
        suffixes = _ISSUE426_REPRESENTATION_SUFFIXES.get(family, {}).get(representation)
        if not suffixes:
            raise V2OptimizationError(
                f"unsupported issue-426 representation: {family}/{representation}"
            )
        columns = [
            column
            for column in frame.columns
            if column.startswith(f"feature_{family}_")
            and not column.endswith("available_at")
            and any(column.endswith(suffix) for suffix in suffixes)
        ]
        if not columns:
            raise V2OptimizationError(
                f"issue-426 combined interaction lacks {family}/{representation} features"
            )
        return columns

    storage_columns = representation_columns("storage", storage_representation)
    weather_columns = representation_columns("weather", weather_representation)
    interactions: dict[str, pd.Series] = {}
    season_columns = ("feature_season_sin", "feature_season_cos")
    volatility = pd.to_numeric(frame["feature_vol_20"], errors="raise").astype(float)
    for storage_column, weather_column, season_column in itertools.product(
        storage_columns, weather_columns, season_columns
    ):
        storage = pd.to_numeric(frame[storage_column], errors="raise").astype(float)
        weather = pd.to_numeric(frame[weather_column], errors="raise").astype(float)
        season = pd.to_numeric(frame[season_column], errors="raise").astype(float)
        name = (
            "feature_issue426_combined_"
            f"{storage_column.removeprefix('feature_storage_')}__x_"
            f"{weather_column.removeprefix('feature_weather_')}__x_"
            f"{season_column.removeprefix('feature_')}__x_vol20"
        )
        interactions[name] = storage * weather * season * volatility
    numeric = pd.concat(
        [
            frame[market_columns].apply(pd.to_numeric, errors="raise").astype(float),
            pd.DataFrame(interactions, index=frame.index),
        ],
        axis=1,
    )
    lookback = int(config["data.lookback_sessions"])
    lag = int(config["transforms.lag_sessions"])
    stat_window = int(config["transforms.rolling_stat_window_sessions"])
    norm_window = int(config["transforms.normalization_window_sessions"])
    winsor = float(config["transforms.winsor_quantile"])
    if min(lookback, lag, stat_window, norm_window) < 1:
        raise V2OptimizationError("issue-426 combined transform windows must be positive")
    if not 0.0 <= winsor < 0.5:
        raise V2OptimizationError("issue-426 combined winsor quantile is invalid")
    if winsor > 0.0:
        shifted = numeric.shift(1)
        history = shifted.rolling(window=lookback, min_periods=min(20, lookback))
        lower = history.quantile(winsor)
        upper = history.quantile(1.0 - winsor)
        numeric = numeric.clip(lower=lower, upper=upper, axis=1)
    lagged = numeric.shift(lag)
    history = numeric.shift(1).rolling(window=stat_window, min_periods=stat_window)
    rolling_mean = history.mean().add_suffix(f"__mean{stat_window}")
    rolling_std = history.std(ddof=0).add_suffix(f"__std{stat_window}")
    derived = pd.concat([lagged, rolling_mean, rolling_std], axis=1)
    scaled = _issue425_rolling_scale(
        derived, str(config["transforms.scaling"]), norm_window
    )
    output_columns = list(scaled.columns)
    output = pd.concat(
        [frame[["trade_date", "available_at"]], scaled], axis=1
    ).replace([np.inf, -np.inf], np.nan)
    output = output.dropna(subset=output_columns).copy()
    if output.empty:
        raise V2OptimizationError("issue-426 combined transforms produced no complete rows")
    if not np.isfinite(output[output_columns].to_numpy(dtype=float)).all():
        raise V2OptimizationError("issue-426 combined transformed features are non-finite")
    if not any(column.startswith("feature_issue426_combined_") for column in output_columns):
        raise V2OptimizationError("issue-426 combined interaction produced no interaction columns")
    return output, output_columns


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


def _issue426_transform_config(config: Mapping[str, object]) -> dict[str, object]:
    return {
        "feature_family_subset": config["issue426.family"],
        "market_control_family": config["data.feature_family_subset"],
        "representation": config["issue426.representation"],
        "role": config["issue426.role"],
        "lookback_sessions": config["data.lookback_sessions"],
        "return_transform": config["transforms.return_transform"],
        "scaling": config["transforms.scaling"],
        "normalization_window_sessions": config["transforms.normalization_window_sessions"],
        "winsor_quantile": config["transforms.winsor_quantile"],
        "lag_sessions": config["transforms.lag_sessions"],
        "rolling_stat_window_sessions": config["transforms.rolling_stat_window_sessions"],
    }


def _issue426_prepare_origins(
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

    transform_config = _issue426_transform_config(config)
    transform_key = _sha256_payload(transform_config)
    prepared = feature_cache.get(transform_key)
    if prepared is None:
        prepared = prepare_issue426_features(features, transform_config)
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
            raise V2OptimizationError("issue-426 target reconstruction produced no origins")
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


def _issue426_prepare_combined_origins(
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

    storage_representation = str(config["issue426.storage_representation"])
    weather_representation = str(config["issue426.weather_representation"])
    transform_key = _sha256_payload(
        {
            "combined_interaction": "storage×weather×season×volatility",
            "storage_representation": storage_representation,
            "weather_representation": weather_representation,
            "lookback": config["data.lookback_sessions"],
            "return_transform": config["transforms.return_transform"],
            "scaling": config["transforms.scaling"],
            "normalization": config["transforms.normalization_window_sessions"],
            "winsor": config["transforms.winsor_quantile"],
            "lag": config["transforms.lag_sessions"],
            "rolling": config["transforms.rolling_stat_window_sessions"],
            "market_family": config["data.feature_family_subset"],
        }
    )
    prepared = feature_cache.get(transform_key)
    if prepared is None:
        prepared = prepare_issue426_storage_weather_interaction_features(
            features,
            config,
            storage_representation=storage_representation,
            weather_representation=weather_representation,
        )
        feature_cache[transform_key] = prepared
    prepared_features, _ = prepared
    base_key = _sha256_payload(
        {
            "combined_transform": transform_key,
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
            raise V2OptimizationError("issue-426 combined target reconstruction produced no origins")
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


def _issue426_apply_exposure_gate(
    origins: pd.DataFrame,
    forecasts: pd.DataFrame,
    *,
    family: str,
    quantile: float,
    training_window: str,
    start_timestamp: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if not 0.0 <= float(quantile) <= 1.0:
        raise V2OptimizationError("issue-426 exposure gate quantile is invalid")
    prefix = f"feature_{family}_"
    gate_columns = [column for column in origins.columns if column.startswith(prefix)]
    if not gate_columns:
        raise V2OptimizationError(f"issue-426 {family} exposure gate has no family features")
    frame = origins.copy()
    frame["fill_timestamp"] = pd.to_datetime(frame["fill_timestamp"], utc=True, errors="raise")
    frame["target_end_timestamp"] = pd.to_datetime(
        frame["target_end_timestamp"], utc=True, errors="raise"
    )
    if frame["fill_timestamp"].duplicated().any():
        raise V2OptimizationError("issue-426 exposure gate origins duplicate fill timestamps")
    training = frame.loc[frame["target_end_timestamp"] < pd.Timestamp(start_timestamp)].copy()
    training = _issue425_training_tail(training, training_window)
    if training.empty:
        raise V2OptimizationError("issue-426 exposure gate has no purge-safe training rows")
    training_strength = training[gate_columns].abs().max(axis=1)
    if not np.isfinite(training_strength.to_numpy(dtype=float)).all():
        raise V2OptimizationError("issue-426 exposure gate training strength is non-finite")
    threshold = float(np.quantile(training_strength.to_numpy(dtype=float), float(quantile)))
    keyed = frame.set_index("fill_timestamp", verify_integrity=True)
    result = forecasts.copy()
    result["fill_timestamp"] = pd.to_datetime(result["fill_timestamp"], utc=True, errors="raise")
    evaluation = keyed.reindex(result["fill_timestamp"])
    if evaluation[gate_columns].isna().any().any():
        raise V2OptimizationError("issue-426 exposure gate cannot match evaluation origins")
    evaluation_strength = evaluation[gate_columns].abs().max(axis=1).to_numpy(dtype=float)
    active = evaluation_strength >= threshold
    for column in ("predicted_path_move_per_mmbtu", "predicted_gross_pnl_usd"):
        result[column] = np.where(active, result[column].to_numpy(dtype=float), 0.0)
    return result, {
        "gate_quantile": float(quantile),
        "gate_threshold": threshold,
        "gate_active_rate": float(np.mean(active)) if len(active) else 0.0,
        "gate_feature_count": len(gate_columns),
    }


def _issue426_apply_confidence_weight(
    origins: pd.DataFrame,
    forecasts: pd.DataFrame,
    *,
    family: str,
    training_window: str,
    start_timestamp: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, object]]:
    prefix = f"feature_{family}_"
    family_columns = [column for column in origins.columns if column.startswith(prefix)]
    if not family_columns:
        raise V2OptimizationError(f"issue-426 {family} confidence role has no family features")
    frame = origins.copy()
    frame["fill_timestamp"] = pd.to_datetime(frame["fill_timestamp"], utc=True, errors="raise")
    frame["target_end_timestamp"] = pd.to_datetime(
        frame["target_end_timestamp"], utc=True, errors="raise"
    )
    if frame["fill_timestamp"].duplicated().any():
        raise V2OptimizationError("issue-426 confidence origins duplicate fill timestamps")
    training = frame.loc[frame["target_end_timestamp"] < pd.Timestamp(start_timestamp)].copy()
    training = _issue425_training_tail(training, training_window)
    if training.empty:
        raise V2OptimizationError("issue-426 confidence role has no purge-safe training rows")
    training_strength = training[family_columns].abs().max(axis=1).to_numpy(dtype=float)
    if not np.isfinite(training_strength).all():
        raise V2OptimizationError("issue-426 confidence training strength is non-finite")
    ordered = np.sort(training_strength)
    keyed = frame.set_index("fill_timestamp", verify_integrity=True)
    result = forecasts.copy()
    result["fill_timestamp"] = pd.to_datetime(result["fill_timestamp"], utc=True, errors="raise")
    evaluation = keyed.reindex(result["fill_timestamp"])
    if evaluation[family_columns].isna().any().any():
        raise V2OptimizationError("issue-426 confidence role cannot match evaluation origins")
    evaluation_strength = evaluation[family_columns].abs().max(axis=1).to_numpy(dtype=float)
    if not np.isfinite(evaluation_strength).all():
        raise V2OptimizationError("issue-426 confidence evaluation strength is non-finite")
    weights = np.searchsorted(ordered, evaluation_strength, side="right") / len(ordered)
    for column in ("predicted_path_move_per_mmbtu", "predicted_gross_pnl_usd"):
        result[column] = result[column].to_numpy(dtype=float) * weights
    return result, {
        "confidence_weight_mean": float(np.mean(weights)) if len(weights) else 0.0,
        "confidence_weight_min": float(np.min(weights)) if len(weights) else 0.0,
        "confidence_weight_max": float(np.max(weights)) if len(weights) else 0.0,
        "confidence_feature_count": len(family_columns),
        "confidence_training_rows": len(training),
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


def _rank_issue426_rows(
    rows: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    completed = [
        row
        for row in rows
        if row.get("status", "complete") == "complete"
        and isinstance(row.get("monthly_score"), Mapping)
        and isinstance(row.get("ablation"), Mapping)
    ]
    return sorted(
        completed,
        key=lambda row: (
            -float(row["ablation"]["mean_monthly_net_return_delta"]),
            float(row["monthly_score"]["max_drawdown_fraction"]),
            float(row["monthly_score"]["transaction_cost_usd"]),
            int(row.get("complexity_rank", 999)),
            str(row.get("candidate_id", "")),
        ),
    )


_ISSUE426_GATE_ROLES = {"filter_veto"}
_ISSUE426_CONFIDENCE_ROLES = {"confidence"}
_ISSUE426_UNIDENTIFIABLE_ROLES = {
    "sizing": "inherited forecast_sign policy is single-contract and cannot identify family-driven position sizing",
    "risk_modifier": "inherited risk policy is fixed for the replay and has no point-in-time family-driven risk override",
}


def _issue426_model_feature_columns(
    feature_columns: Sequence[str], *, family: str, role: str
) -> tuple[list[str], list[str]]:
    prefix = f"feature_{family}_"
    family_columns = [column for column in feature_columns if column.startswith(prefix)]
    market_columns = [column for column in feature_columns if not column.startswith(prefix)]
    if not family_columns:
        raise V2OptimizationError(f"issue-426 {family} candidate has no family features")
    if not market_columns:
        raise V2OptimizationError("issue-426 candidate has no matched market features")
    if role in _ISSUE426_GATE_ROLES | _ISSUE426_CONFIDENCE_ROLES:
        return market_columns, market_columns
    return list(feature_columns), market_columns


def _score_issue426_block(
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
    role = str(config["issue426.role"])
    gate_diagnostics: dict[str, object] = {}
    if role in _ISSUE426_GATE_ROLES:
        quantile = config.get("issue426.gate_quantile")
        if quantile is None:
            raise V2OptimizationError(f"issue-426 role {role} requires a gate quantile")
        forecasts, gate_diagnostics = _issue426_apply_exposure_gate(
            origins,
            forecasts,
            family=str(config["issue426.family"]),
            quantile=float(quantile),
            training_window=str(config["model.training_window"]),
            start_timestamp=start_timestamp,
        )
    elif role in _ISSUE426_CONFIDENCE_ROLES:
        forecasts, gate_diagnostics = _issue426_apply_confidence_weight(
            origins,
            forecasts,
            family=str(config["issue426.family"]),
            training_window=str(config["model.training_window"]),
            start_timestamp=start_timestamp,
        )
    ledger, policy_summary = simulate_policy(
        window,
        forecasts,
        "forecast_sign",
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
    diagnostics = dict(forecast_diagnostics)
    diagnostics.update(gate_diagnostics)
    return {
        "candidate_id": candidate_id,
        "block_id": block_id,
        "status": "complete",
        "champion_eligible": True,
        "complexity_rank": len(feature_columns),
        "config": dict(config),
        "monthly_score": monthly_score,
        "forecast_diagnostics": diagnostics,
        "policy_summary": {
            "kill_triggered": bool(policy_summary["kill_triggered"]),
            "kill_reason": policy_summary.get("kill_reason"),
        },
    }


def _evaluate_issue426_config(
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
        origins, all_feature_columns = _issue426_prepare_origins(
            session_path,
            features,
            config,
            round_trip_per_mmbtu=round_trip_per_mmbtu,
            feature_cache=feature_cache,
            origin_cache=origin_cache,
        )
        family = str(config["issue426.family"])
        role = str(config["issue426.role"])
        candidate_columns, control_columns = _issue426_model_feature_columns(
            all_feature_columns, family=family, role=role
        )
        candidate_rows = [
            _score_issue426_block(
                origins,
                candidate_columns,
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
        control_rows = [
            _score_issue425_block(
                origins,
                control_columns,
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
        candidate = _aggregate_issue425_blocks(candidate_rows)
        control = _aggregate_issue425_blocks(control_rows)
        candidate_score = candidate["monthly_score"]
        control_score = control["monthly_score"]
        if not isinstance(candidate_score, Mapping) or not isinstance(control_score, Mapping):
            raise V2OptimizationError("issue-426 matched ablation score is invalid")
        candidate["status"] = "complete"
        candidate["matched_control"] = control
        candidate["ablation"] = {
            "mean_monthly_net_return_delta": float(candidate_score["mean_monthly_net_return"])
            - float(control_score["mean_monthly_net_return"]),
            "total_net_pnl_usd_delta": float(candidate_score["total_net_pnl_usd"])
            - float(control_score["total_net_pnl_usd"]),
            "max_drawdown_fraction_delta": float(candidate_score["max_drawdown_fraction"])
            - float(control_score["max_drawdown_fraction"]),
            "transaction_cost_usd_delta": float(candidate_score["transaction_cost_usd"])
            - float(control_score["transaction_cost_usd"]),
            "trade_count_delta": int(candidate_score["trade_count"])
            - int(control_score["trade_count"]),
        }
        return candidate
    except (V2OptimizationError, ValueError, KeyError) as exc:
        return {
            "candidate_id": _sha256_payload(dict(config))[:20],
            "status": "failed",
            "champion_eligible": True,
            "config": dict(config),
            "reason": str(exc),
        }


def _evaluate_issue426_combined_config(
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
        origins, feature_columns = _issue426_prepare_combined_origins(
            session_path,
            features,
            config,
            round_trip_per_mmbtu=round_trip_per_mmbtu,
            feature_cache=feature_cache,
            origin_cache=origin_cache,
        )
        interaction_columns = [
            column
            for column in feature_columns
            if column.startswith("feature_issue426_combined_")
        ]
        control_columns = [
            column
            for column in feature_columns
            if not column.startswith("feature_issue426_combined_")
        ]
        if not interaction_columns or not control_columns:
            raise V2OptimizationError("issue-426 combined matched feature sets are invalid")
        candidate_rows = [
            _score_issue426_block(
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
        control_rows = [
            _score_issue425_block(
                origins,
                control_columns,
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
        candidate = _aggregate_issue425_blocks(candidate_rows)
        control = _aggregate_issue425_blocks(control_rows)
        candidate_score = candidate["monthly_score"]
        control_score = control["monthly_score"]
        if not isinstance(candidate_score, Mapping) or not isinstance(control_score, Mapping):
            raise V2OptimizationError("issue-426 combined matched ablation score is invalid")
        candidate["status"] = "complete"
        candidate["matched_control"] = control
        candidate["ablation"] = {
            "mean_monthly_net_return_delta": float(candidate_score["mean_monthly_net_return"])
            - float(control_score["mean_monthly_net_return"]),
            "total_net_pnl_usd_delta": float(candidate_score["total_net_pnl_usd"])
            - float(control_score["total_net_pnl_usd"]),
            "max_drawdown_fraction_delta": float(candidate_score["max_drawdown_fraction"])
            - float(control_score["max_drawdown_fraction"]),
            "transaction_cost_usd_delta": float(candidate_score["transaction_cost_usd"])
            - float(control_score["transaction_cost_usd"]),
            "trade_count_delta": int(candidate_score["trade_count"])
            - int(control_score["trade_count"]),
        }
        candidate["interaction_feature_count"] = len(interaction_columns)
        return candidate
    except (V2OptimizationError, ValueError, KeyError) as exc:
        return {
            "candidate_id": _sha256_payload(dict(config))[:20],
            "status": "failed",
            "champion_eligible": True,
            "config": dict(config),
            "reason": str(exc),
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


def _issue426_evaluate_trial(
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
        "issue": 426,
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
    result = _evaluate_issue426_config(
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


def _issue426_evaluate_combined_trial(
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
        "issue": 426,
        "interaction": "storage×weather×season×volatility",
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
    result = _evaluate_issue426_combined_config(
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
        "interaction": "storage×weather×season×volatility",
        "config": dict(config),
        "result": result,
    }
    ledger.append(record)
    trial_cache[trial_id] = record
    return result


def _search_issue426_combined_outer(
    *,
    outer_block: Mapping[str, str],
    inner_blocks: Sequence[Mapping[str, str]],
    storage_selected_config: Mapping[str, object],
    weather_selected_config: Mapping[str, object],
    evaluator: Any,
) -> dict[str, object]:
    if not inner_blocks:
        raise V2OptimizationError("issue-426 combined interaction has no common prior evidence")
    storage_representation = str(storage_selected_config["issue426.representation"])
    weather_representation = str(weather_selected_config["issue426.representation"])
    configs: list[dict[str, object]] = []
    for basis, selected in (
        ("storage_selected_transform", storage_selected_config),
        ("weather_selected_transform", weather_selected_config),
    ):
        config = dict(selected)
        config.update(
            {
                "issue426.family": "storage",
                "issue426.role": "direct",
                "issue426.gate_quantile": None,
                "issue426.interaction": "storage×weather×season×volatility",
                "issue426.storage_representation": storage_representation,
                "issue426.weather_representation": weather_representation,
                "issue426.interaction_transform_basis": basis,
            }
        )
        configs.append(config)
    outer_id = str(outer_block["id"])
    rows = _issue425_sweep(
        configs,
        stage="combined_interaction_transform_basis",
        outer_block_id=outer_id,
        blocks=inner_blocks,
        evaluator=evaluator,
    )
    ranked = _rank_issue426_rows(rows)
    if not ranked:
        raise V2OptimizationError("issue-426 combined interaction has no valid transform basis")
    selected_config = dict(ranked[0]["config"])
    return {
        "outer_block_id": outer_id,
        "selection_block_ids": [str(block["id"]) for block in inner_blocks],
        "selected_config": selected_config,
        "selected_candidate_id": _sha256_payload(selected_config)[:20],
        "stage_summaries": [
            {
                "stage": "combined_interaction_transform_basis",
                "trials": len(rows),
                "winner": ranked[0],
            }
        ],
        "trial_count": len(rows),
    }


def _search_issue426_outer(
    search_plan: Mapping[str, Any],
    optimization_plan: Mapping[str, Any],
    *,
    family: str,
    outer_block: Mapping[str, str],
    base_config: Mapping[str, object],
    inner_blocks: Sequence[Mapping[str, str]],
    evaluator: Any,
    representations_override: Sequence[str] | None = None,
) -> dict[str, object]:
    if not inner_blocks:
        raise V2OptimizationError("issue-426 outer block has no prior inner evidence")
    family_plan = next(
        (
            item
            for item in search_plan.get("families", [])
            if isinstance(item, Mapping) and str(item.get("family")) == family
        ),
        None,
    )
    if not isinstance(family_plan, Mapping):
        raise V2OptimizationError(f"issue-426 search plan lacks family: {family}")
    declared_representations = [
        str(value) for value in family_plan.get("representations", [])
    ]
    representations = (
        declared_representations
        if representations_override is None
        else [str(value) for value in representations_override]
    )
    supported_representations = set(_ISSUE426_REPRESENTATION_SUFFIXES.get(family, {}))
    if (
        not representations
        or not set(representations).issubset(set(declared_representations))
        or not set(representations).issubset(supported_representations)
    ):
        raise V2OptimizationError(
            f"issue-426 {family} representation implementation is incomplete"
        )
    declared_roles = [str(value) for value in family_plan.get("roles", [])]
    if not declared_roles:
        raise V2OptimizationError(f"issue-426 {family} search plan has no roles")
    held_roles = [
        {
            "role": role,
            "disposition": "HOLD_UNIDENTIFIABLE_UNDER_INHERITED_EXECUTION_POLICY",
            "reason": _ISSUE426_UNIDENTIFIABLE_ROLES[role],
            "search_budget_consumed": False,
        }
        for role in declared_roles
        if role in _ISSUE426_UNIDENTIFIABLE_ROLES
    ]
    roles = [role for role in declared_roles if role not in _ISSUE426_UNIDENTIFIABLE_ROLES]
    if not roles:
        raise V2OptimizationError(f"issue-426 {family} has no identifiable roles")
    stages = {
        str(stage.get("id")): stage
        for stage in optimization_plan.get("stages", [])
        if isinstance(stage, Mapping)
    }
    outer_id = str(outer_block["id"])
    summaries: list[dict[str, object]] = []
    representation_stage = stages["representation_role"]
    gate_quantiles = [float(value) for value in representation_stage.get("gate_quantiles", [])]
    configs: list[dict[str, object]] = []
    for representation, role in itertools.product(representations, roles):
        quantiles: Sequence[float | None] = gate_quantiles if role in _ISSUE426_GATE_ROLES else (None,)
        for gate_quantile in quantiles:
            config = dict(base_config)
            config.update(
                {
                    "issue426.family": family,
                    "issue426.representation": representation,
                    "issue426.role": role,
                    "issue426.gate_quantile": gate_quantile,
                }
            )
            configs.append(config)
    rows = _issue425_sweep(
        configs,
        stage="representation_role",
        outer_block_id=outer_id,
        blocks=inner_blocks,
        evaluator=evaluator,
    )
    ranked = _rank_issue426_rows(rows)
    if not ranked:
        raise V2OptimizationError(f"issue-426 {family} representation/role search has no valid candidate")
    current = dict(ranked[0]["config"])
    summaries.append({"stage": "representation_role", "trials": len(rows), "winner": ranked[0]})

    for stage_id in ("lag_and_rolling_window", "scaling_and_normalization", "lookback_and_winsor"):
        stage = stages[stage_id]
        axes = stage.get("axes")
        if not isinstance(axes, Mapping):
            raise V2OptimizationError(f"issue-426 stage {stage_id} lacks axes")
        names = list(axes)
        values = [list(axes[name]) for name in names]
        configs = []
        for combination in itertools.product(*values):
            config = dict(current)
            for name, value in zip(names, combination, strict=True):
                config[str(name)] = value
            configs.append(config)
        rows = _issue425_sweep(
            configs,
            stage=stage_id,
            outer_block_id=outer_id,
            blocks=inner_blocks,
            evaluator=evaluator,
        )
        ranked = _rank_issue426_rows(rows)
        if not ranked:
            raise V2OptimizationError(f"issue-426 {family} stage {stage_id} has no valid candidate")
        current = dict(ranked[0]["config"])
        summaries.append({"stage": stage_id, "trials": len(rows), "winner": ranked[0]})

    interaction_configs = [dict(current)]
    registered_interaction = {
        "storage": "storage×season",
        "weather": "weather×season",
        "positioning": "positioning×volatility",
    }.get(family)
    if registered_interaction in set(map(str, search_plan.get("required_interactions", []))):
        interaction = dict(current)
        interaction["issue426.role"] = "interaction"
        interaction["issue426.gate_quantile"] = None
        if interaction != current:
            interaction_configs.append(interaction)
    rows = _issue425_sweep(
        interaction_configs,
        stage="registered_interactions",
        outer_block_id=outer_id,
        blocks=inner_blocks,
        evaluator=evaluator,
    )
    ranked = _rank_issue426_rows(rows)
    if not ranked:
        raise V2OptimizationError(f"issue-426 {family} interaction stage has no valid candidate")
    current = dict(ranked[0]["config"])
    summaries.append({"stage": "registered_interactions", "trials": len(rows), "winner": ranked[0]})
    return {
        "outer_block_id": outer_id,
        "selection_block_ids": [str(block["id"]) for block in inner_blocks],
        "selected_config": current,
        "selected_candidate_id": _sha256_payload(current)[:20],
        "held_roles": held_roles,
        "stage_summaries": summaries,
        "trial_count": sum(int(item["trials"]) for item in summaries),
    }


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



def _load_issue426_checkpoint_frame(
    checkpoint_dir: Path, name: str
) -> tuple[pd.DataFrame, dict[str, object]]:
    manifest_path = Path(checkpoint_dir) / f"{name}.manifest.json"
    if not manifest_path.is_file():
        raise V2OptimizationError(f"issue-426 market checkpoint manifest missing: {name}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    identity = manifest.get("identity")
    if not isinstance(identity, Mapping) or identity.get("issue") != 426:
        raise V2OptimizationError(f"issue-426 market checkpoint identity invalid: {name}")
    data_path = manifest_path.parent / str(manifest.get("data_file", ""))
    expected_sha = str(manifest.get("data_sha256", ""))
    if not data_path.is_file() or not expected_sha or _sha256_file(data_path) != expected_sha:
        raise V2OptimizationError(f"issue-426 market checkpoint integrity failed: {name}")
    frame = pd.read_parquet(data_path)
    expected_columns = list(manifest.get("columns", []))
    if len(frame) != int(manifest.get("rows", -1)) or list(frame.columns) != expected_columns:
        raise V2OptimizationError(f"issue-426 market checkpoint shape mismatch: {name}")
    return frame, dict(manifest)


def _issue426_valid_inner_blocks(
    features: pd.DataFrame,
    *,
    family: str,
    inner_blocks: Sequence[Mapping[str, str]],
    outer_start: str,
    minimum_training_rows: int,
) -> list[Mapping[str, str]]:
    family_time = f"feature_{family}_available_at"
    if family_time not in features:
        raise V2OptimizationError(f"issue-426 merged {family} features lack availability")
    trade_date = pd.to_datetime(features["trade_date"], utc=True, errors="raise")
    matched = features[family_time].notna()
    outer_start_ts = pd.Timestamp(str(outer_start), tz="UTC")
    valid: list[Mapping[str, str]] = []
    for block in inner_blocks:
        if pd.Timestamp(str(block["end"]), tz="UTC") >= outer_start_ts:
            continue
        block_start = pd.Timestamp(str(block["start"]), tz="UTC")
        training_rows = int((matched & trade_date.lt(block_start)).sum())
        if training_rows >= minimum_training_rows:
            valid.append(block)
    return valid


def _issue426_common_selection_blocks(
    blocks: Sequence[Mapping[str, str]],
    representation_block_ids: Mapping[str, Sequence[str]],
) -> dict[str, object]:
    ordered_blocks = list(blocks)
    block_ids = [str(block["id"]) for block in ordered_blocks]
    if len(block_ids) != len(set(block_ids)):
        raise V2OptimizationError("issue-426 selection blocks contain duplicate ids")
    known = set(block_ids)
    available: list[str] = []
    held: list[str] = []
    block_sets: list[set[str]] = []
    for representation, raw_ids in representation_block_ids.items():
        ids = [str(value) for value in raw_ids]
        unknown = set(ids) - known
        if unknown:
            raise V2OptimizationError(
                f"issue-426 representation {representation} references unknown blocks: {sorted(unknown)}"
            )
        if ids:
            available.append(str(representation))
            block_sets.append(set(ids))
        else:
            held.append(str(representation))
    common_ids = set.intersection(*block_sets) if block_sets else set()
    return {
        "available_representations": available,
        "held_representations": held,
        "common_blocks": [
            block for block in ordered_blocks if str(block["id"]) in common_ids
        ],
    }


def _issue426_representation_selection_support(
    session_path: pd.DataFrame,
    features: pd.DataFrame,
    *,
    family: str,
    representations: Sequence[str],
    base_config: Mapping[str, object],
    inner_blocks: Sequence[Mapping[str, str]],
    minimum_training_rows: int,
    round_trip_per_mmbtu: float,
    feature_cache: dict[str, tuple[pd.DataFrame, list[str]]],
    origin_cache: dict[str, tuple[pd.DataFrame, list[str]]],
) -> dict[str, object]:
    from commodity.market_only_phase2 import _path_window

    block_ids: dict[str, list[str]] = {}
    diagnostics: dict[str, list[dict[str, object]]] = {}
    for representation in representations:
        config = dict(base_config)
        config.update(
            {
                "issue426.family": family,
                "issue426.representation": str(representation),
                "issue426.role": "direct",
                "issue426.gate_quantile": None,
            }
        )
        try:
            origins, _ = _issue426_prepare_origins(
                session_path,
                features,
                config,
                round_trip_per_mmbtu=round_trip_per_mmbtu,
                feature_cache=feature_cache,
                origin_cache=origin_cache,
            )
        except (V2OptimizationError, ValueError) as exc:
            block_ids[str(representation)] = []
            diagnostics[str(representation)] = [
                {"status": "HOLD_PREPARATION_FAILED", "reason": str(exc)}
            ]
            continue
        valid_ids: list[str] = []
        rows: list[dict[str, object]] = []
        for block in inner_blocks:
            _, start_timestamp, boundary_timestamp = _path_window(
                session_path,
                start_date=str(block["start"]),
                end_date=str(block["end"]),
            )
            training = origins.loc[
                origins["target_end_timestamp"] < start_timestamp
            ].copy()
            training = _issue425_training_tail(
                training, str(config["model.training_window"])
            )
            evaluation = origins.loc[
                origins["fill_timestamp"].ge(start_timestamp)
                & origins["target_end_timestamp"].lt(boundary_timestamp)
            ]
            eligible = len(training) >= minimum_training_rows and not evaluation.empty
            if eligible:
                valid_ids.append(str(block["id"]))
            rows.append(
                {
                    "block_id": str(block["id"]),
                    "training_rows": len(training),
                    "evaluation_rows": len(evaluation),
                    "eligible": eligible,
                }
            )
        block_ids[str(representation)] = valid_ids
        diagnostics[str(representation)] = rows
    return {"block_ids": block_ids, "diagnostics": diagnostics}


def run_issue426_development_optimization(
    *,
    registry_path: Path,
    search_plan_path: Path,
    source_plan_path: Path,
    optimization_plan_path: Path,
    data_sources_path: Path,
    phase2_config_path: Path,
    issue425_result_path: Path,
    raw_root: Path,
    market_checkpoint_dir: Path,
    trial_ledger_path: Path,
) -> dict[str, object]:
    from commodity.market_only_phase2 import (
        _inner_fold_specs,
        _load_inherited_risk_and_costs,
    )

    registry = load_v2_registry(registry_path)
    search_plan = load_issue426_search_plan(search_plan_path)
    validate_issue426_search_plan(registry, search_plan)
    source_plan = load_issue426_source_plan(source_plan_path)
    optimization_plan = load_issue426_optimization_plan(optimization_plan_path)
    validate_issue426_optimization_plan(registry, optimization_plan)
    programme_dir = Path(search_plan_path).parent
    weather_contract_path = programme_dir / "issue426-weather-feature-contract-v1.json"
    interaction_contract_path = programme_dir / "issue426-interaction-contract-v1.json"
    weather_contract = load_issue426_weather_feature_contract(weather_contract_path)
    load_issue426_interaction_contract(interaction_contract_path)
    cfg = json.loads(Path(phase2_config_path).read_text(encoding="utf-8"))
    cutoff = pd.Timestamp(str(search_plan["latest_allowed_trade_date"]), tz="UTC")
    if cutoff > pd.Timestamp("2022-12-31", tz="UTC"):
        raise V2OptimizationError("issue-426 optimization crosses protected evidence")
    data_cfg = json.loads(Path(data_sources_path).read_text(encoding="utf-8"))
    coverage = inventory_issue426_historical_coverage(raw_root, source_plan)
    source_gate = build_issue426_historical_source_gate(
        data_cfg,
        source_plan,
        coverage,
        latest_allowed_trade_date=str(search_plan["latest_allowed_trade_date"]),
    )
    session_path, session_manifest = _load_issue426_checkpoint_frame(
        market_checkpoint_dir, "session-path"
    )
    market_features, feature_manifest = _load_issue426_checkpoint_frame(
        market_checkpoint_dir, "features"
    )
    session_dates = pd.to_datetime(session_path["trade_date"], utc=True, errors="raise")
    feature_dates = pd.to_datetime(market_features["trade_date"], utc=True, errors="raise")
    if session_dates.max().normalize() > cutoff or feature_dates.max().normalize() > cutoff:
        raise V2OptimizationError("issue-426 cached market input crosses development cutoff")
    risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    costs = cost_profiles["base"]
    minimum_training_rows = int(cfg["execution_contract"]["minimum_training_rows"])
    round_trip_per_mmbtu = float(costs.round_trip_usd) / float(
        cfg["execution_contract"]["contract_multiplier_mmbtu"]
    )
    inner_blocks = _inner_fold_specs(cfg)
    outer_blocks = list(cfg["validation"]["outer_blocks"])
    outer_controls = load_issue426_outer_matched_controls(issue425_result_path)
    family_search = {
        str(item["family"]): item
        for item in search_plan["families"]
        if isinstance(item, Mapping)
    }
    scorable_families = list(source_gate["scorable_families"])
    unsupported = set(scorable_families) - {"storage", "weather", "positioning"}
    if unsupported:
        raise V2OptimizationError(
            f"issue-426 scorable family implementation missing: {sorted(unsupported)}"
        )
    ledger = TrialLedger(trial_ledger_path)
    trial_cache = ledger._records()
    code_id = _sha256_file(Path(__file__))
    family_results: dict[str, object] = {}
    family_frames: dict[str, pd.DataFrame] = {}

    for family in scorable_families:
        if family == "storage":
            family_frame = build_issue426_storage_family_frame(
                Path(raw_root) / str(source_plan["families"][family]["normalized_file"])
            )
        elif family == "weather":
            family_frame = build_issue426_weather_family_frame(
                Path(raw_root) / "weather" / "gfs_rda_025",
                availability_delay_minutes=int(weather_contract["availability_delay_minutes"]),
                degree_day_base_c=float(weather_contract["degree_day_base_c"]),
            )
        elif family == "positioning":
            family_frame = build_issue426_positioning_family_frame(
                Path(raw_root) / str(source_plan["families"][family]["normalized_file"])
            )
        else:
            raise V2OptimizationError(f"issue-426 family implementation missing: {family}")
        family_frames[family] = family_frame
        value_columns = [
            column for column in family_frame.columns if column not in {"observed_for", "available_at"}
        ]
        merged_features = merge_issue426_pit_family(
            market_features,
            family_frame,
            family=family,
            value_columns=value_columns,
            max_staleness=pd.Timedelta(str(family_search[family]["max_staleness"])),
            latest_allowed_trade_date=str(search_plan["latest_allowed_trade_date"]),
        )
        dataset_id = _sha256_payload(
            {
                "family": family,
                "session_path_sha256": session_manifest["data_sha256"],
                "market_features_sha256": feature_manifest["data_sha256"],
                "family_manifest_index_sha256": coverage[family]["manifest_index_sha256"],
                "registry_sha256": _sha256_file(Path(registry_path)),
                "data_sources_sha256": _sha256_file(Path(data_sources_path)),
                "phase2_config_sha256": _sha256_file(Path(phase2_config_path)),
                "issue425_result_sha256": _sha256_file(Path(issue425_result_path)),
                "search_plan_sha256": _sha256_file(Path(search_plan_path)),
                "source_plan_sha256": _sha256_file(Path(source_plan_path)),
                "optimization_plan_sha256": _sha256_file(Path(optimization_plan_path)),
                "weather_feature_contract_sha256": (
                    _sha256_file(weather_contract_path) if family == "weather" else None
                ),
            }
        )
        feature_cache: dict[str, tuple[pd.DataFrame, list[str]]] = {}
        origin_cache: dict[str, tuple[pd.DataFrame, list[str]]] = {}

        def evaluator(
            stage: str,
            outer_block_id: str,
            blocks: Sequence[Mapping[str, str]],
            config: Mapping[str, object],
            _features: pd.DataFrame = merged_features,
            _dataset_id: str = dataset_id,
            _feature_cache: dict[str, tuple[pd.DataFrame, list[str]]] = feature_cache,
            _origin_cache: dict[str, tuple[pd.DataFrame, list[str]]] = origin_cache,
        ) -> dict[str, object]:
            return _issue426_evaluate_trial(
                stage=stage,
                outer_block_id=outer_block_id,
                blocks=blocks,
                config=config,
                session_path=session_path,
                features=_features,
                phase2_cfg=cfg,
                risk=risk,
                costs=costs,
                minimum_training_rows=minimum_training_rows,
                ledger=ledger,
                trial_cache=trial_cache,
                dataset_id=_dataset_id,
                code_id=code_id,
                feature_cache=_feature_cache,
                origin_cache=_origin_cache,
            )

        nested_outer: list[dict[str, object]] = []
        skipped_outer: list[dict[str, object]] = []
        for outer in outer_blocks:
            outer_id = str(outer["id"])
            if outer_id not in outer_controls:
                raise V2OptimizationError(f"issue-426 missing outer control: {outer_id}")
            eligible_inner = _issue426_valid_inner_blocks(
                merged_features,
                family=family,
                inner_blocks=inner_blocks,
                outer_start=str(outer["start"]),
                minimum_training_rows=minimum_training_rows,
            )
            if not eligible_inner:
                skipped_outer.append(
                    {
                        "outer_block": dict(outer),
                        "disposition": "HOLD_INSUFFICIENT_PRIOR_FAMILY_TRAINING",
                        "minimum_training_rows": minimum_training_rows,
                    }
                )
                continue
            declared_representations = [
                str(value)
                for value in family_search[family].get("representations", [])
            ]
            support = _issue426_representation_selection_support(
                session_path,
                merged_features,
                family=family,
                representations=declared_representations,
                base_config=outer_controls[outer_id]["config"],
                inner_blocks=eligible_inner,
                minimum_training_rows=minimum_training_rows,
                round_trip_per_mmbtu=round_trip_per_mmbtu,
                feature_cache=feature_cache,
                origin_cache=origin_cache,
            )
            common = _issue426_common_selection_blocks(
                eligible_inner, support["block_ids"]
            )
            common_blocks = common["common_blocks"]
            available_representations = common["available_representations"]
            if not common_blocks or not available_representations:
                skipped_outer.append(
                    {
                        "outer_block": dict(outer),
                        "disposition": "HOLD_NO_COMMON_REPRESENTATION_SELECTION_EVIDENCE",
                        "representation_support": support,
                        "available_representations": available_representations,
                        "held_representations": common["held_representations"],
                    }
                )
                continue
            try:
                search = _search_issue426_outer(
                    search_plan,
                    optimization_plan,
                    family=family,
                    outer_block=outer,
                    base_config=outer_controls[outer_id]["config"],
                    inner_blocks=common_blocks,
                    evaluator=evaluator,
                    representations_override=available_representations,
                )
            except V2OptimizationError as exc:
                skipped_outer.append(
                    {
                        "outer_block": dict(outer),
                        "disposition": "HOLD_SEARCH_FAILED",
                        "reason": str(exc),
                        "representation_support": support,
                        "common_selection_block_ids": [
                            str(block["id"]) for block in common_blocks
                        ],
                    }
                )
                continue
            selected_config = dict(search["selected_config"])
            outer_result = evaluator(
                "outer_evaluation",
                outer_id,
                [outer],
                selected_config,
            )
            if outer_result.get("status", "complete") != "complete":
                skipped_outer.append(
                    {
                        "outer_block": dict(outer),
                        "disposition": "HOLD_SELECTED_OUTER_FAILED",
                        "reason": outer_result.get("reason"),
                        "representation_support": support,
                        "common_selection_block_ids": [
                            str(block["id"]) for block in common_blocks
                        ],
                    }
                )
                continue
            nested_outer.append(
                {
                    "outer_block": dict(outer),
                    "representation_support": support,
                    "available_representations": available_representations,
                    "held_representations": common["held_representations"],
                    "common_selection_block_ids": [
                        str(block["id"]) for block in common_blocks
                    ],
                    "search": search,
                    "selected_outer_result": outer_result,
                    "issue425_outer_control": outer_controls[outer_id],
                }
            )

        if nested_outer:
            candidate_summary = _combine_issue425_score_summaries(
                [item["selected_outer_result"]["monthly_score"] for item in nested_outer]
            )
            matched_control_summary = _combine_issue425_score_summaries(
                [
                    item["selected_outer_result"]["matched_control"]["monthly_score"]
                    for item in nested_outer
                ]
            )
            delta = float(candidate_summary["mean_monthly_net_return"]) - float(
                matched_control_summary["mean_monthly_net_return"]
            )
            disposition = (
                "RETAIN_MATCHED_MARGINAL_VALUE_AND_REGISTERED_INTERACTIONS"
                if delta > 0.0
                else "HOLD_STANDALONE_NO_MATCHED_MARGINAL_VALUE_REGISTERED_INTERACTIONS_STILL_REQUIRED"
            )
        else:
            candidate_summary = None
            matched_control_summary = None
            delta = None
            disposition = "HOLD_NO_SCORABLE_OUTER_BLOCK"
        family_results[family] = {
            "source_gate": next(
                row for row in source_gate["family_gate"] if row["family"] == family
            ),
            "held_role_dispositions": [
                {
                    "role": role,
                    "disposition": "HOLD_UNIDENTIFIABLE_UNDER_INHERITED_EXECUTION_POLICY",
                    "reason": _ISSUE426_UNIDENTIFIABLE_ROLES[role],
                    "search_budget_consumed": False,
                }
                for role in map(str, family_search[family].get("roles", []))
                if role in _ISSUE426_UNIDENTIFIABLE_ROLES
            ],
            "dataset_id": dataset_id,
            "nested_outer": nested_outer,
            "skipped_outer": skipped_outer,
            "nested_selection_score": candidate_summary,
            "matched_control_score": matched_control_summary,
            "mean_monthly_net_return_delta": delta,
            "development_disposition": disposition,
        }

    combined_interaction: dict[str, object] = {
        "interaction": "storage×weather×season×volatility",
        "disposition": "HOLD_SOURCE_GATE",
        "reason": "storage_and_weather_are_not_both_scorable",
        "nested_outer": [],
        "skipped_outer": [],
    }
    if {"storage", "weather"}.issubset(set(scorable_families)):
        combined_features = market_features.copy()
        for family in ("storage", "weather"):
            family_frame = family_frames[family]
            value_columns = [
                column
                for column in family_frame.columns
                if column not in {"observed_for", "available_at"}
            ]
            combined_features = merge_issue426_pit_family(
                combined_features,
                family_frame,
                family=family,
                value_columns=value_columns,
                max_staleness=pd.Timedelta(str(family_search[family]["max_staleness"])),
                latest_allowed_trade_date=str(search_plan["latest_allowed_trade_date"]),
            )
        combined_dataset_id = _sha256_payload(
            {
                "interaction": "storage×weather×season×volatility",
                "storage_dataset_id": family_results["storage"]["dataset_id"],
                "weather_dataset_id": family_results["weather"]["dataset_id"],
                "interaction_contract_sha256": _sha256_file(interaction_contract_path),
                "session_path_sha256": session_manifest["data_sha256"],
                "market_features_sha256": feature_manifest["data_sha256"],
            }
        )
        combined_feature_cache: dict[str, tuple[pd.DataFrame, list[str]]] = {}
        combined_origin_cache: dict[str, tuple[pd.DataFrame, list[str]]] = {}

        def combined_evaluator(
            stage: str,
            outer_block_id: str,
            blocks: Sequence[Mapping[str, str]],
            config: Mapping[str, object],
        ) -> dict[str, object]:
            return _issue426_evaluate_combined_trial(
                stage=stage,
                outer_block_id=outer_block_id,
                blocks=blocks,
                config=config,
                session_path=session_path,
                features=combined_features,
                phase2_cfg=cfg,
                risk=risk,
                costs=costs,
                minimum_training_rows=minimum_training_rows,
                ledger=ledger,
                trial_cache=trial_cache,
                dataset_id=combined_dataset_id,
                code_id=code_id,
                feature_cache=combined_feature_cache,
                origin_cache=combined_origin_cache,
            )

        storage_by_outer = {
            str(item["outer_block"]["id"]): item
            for item in family_results["storage"]["nested_outer"]
        }
        weather_by_outer = {
            str(item["outer_block"]["id"]): item
            for item in family_results["weather"]["nested_outer"]
        }
        block_by_id = {str(block["id"]): block for block in inner_blocks}
        combined_nested: list[dict[str, object]] = []
        combined_skipped: list[dict[str, object]] = []
        for outer in outer_blocks:
            outer_id = str(outer["id"])
            storage_item = storage_by_outer.get(outer_id)
            weather_item = weather_by_outer.get(outer_id)
            if storage_item is None or weather_item is None:
                combined_skipped.append(
                    {
                        "outer_block": dict(outer),
                        "disposition": "HOLD_FAMILY_OUTER_UNAVAILABLE",
                    }
                )
                continue
            common_ids = sorted(
                set(map(str, storage_item["common_selection_block_ids"]))
                & set(map(str, weather_item["common_selection_block_ids"]))
            )
            common_blocks = [block_by_id[block_id] for block_id in common_ids if block_id in block_by_id]
            if not common_blocks:
                combined_skipped.append(
                    {
                        "outer_block": dict(outer),
                        "disposition": "HOLD_NO_COMMON_PRIOR_INTERACTION_EVIDENCE",
                    }
                )
                continue
            try:
                search = _search_issue426_combined_outer(
                    outer_block=outer,
                    inner_blocks=common_blocks,
                    storage_selected_config=storage_item["search"]["selected_config"],
                    weather_selected_config=weather_item["search"]["selected_config"],
                    evaluator=combined_evaluator,
                )
            except V2OptimizationError as exc:
                combined_skipped.append(
                    {
                        "outer_block": dict(outer),
                        "disposition": "HOLD_COMBINED_SEARCH_FAILED",
                        "reason": str(exc),
                        "common_selection_block_ids": common_ids,
                    }
                )
                continue
            outer_result = combined_evaluator(
                "combined_interaction_outer_evaluation",
                outer_id,
                [outer],
                search["selected_config"],
            )
            if outer_result.get("status", "complete") != "complete":
                combined_skipped.append(
                    {
                        "outer_block": dict(outer),
                        "disposition": "HOLD_COMBINED_OUTER_FAILED",
                        "reason": outer_result.get("reason"),
                        "common_selection_block_ids": common_ids,
                    }
                )
                continue
            combined_nested.append(
                {
                    "outer_block": dict(outer),
                    "common_selection_block_ids": common_ids,
                    "storage_selected_representation": storage_item["search"]["selected_config"][
                        "issue426.representation"
                    ],
                    "weather_selected_representation": weather_item["search"]["selected_config"][
                        "issue426.representation"
                    ],
                    "search": search,
                    "selected_outer_result": outer_result,
                }
            )
        if combined_nested:
            combined_candidate = _combine_issue425_score_summaries(
                [item["selected_outer_result"]["monthly_score"] for item in combined_nested]
            )
            combined_control = _combine_issue425_score_summaries(
                [
                    item["selected_outer_result"]["matched_control"]["monthly_score"]
                    for item in combined_nested
                ]
            )
            combined_delta = float(combined_candidate["mean_monthly_net_return"]) - float(
                combined_control["mean_monthly_net_return"]
            )
            combined_disposition = (
                "RETAIN_MATCHED_MARGINAL_VALUE"
                if combined_delta > 0.0
                else "HOLD_NO_MATCHED_MARGINAL_VALUE"
            )
        else:
            combined_candidate = None
            combined_control = None
            combined_delta = None
            combined_disposition = "HOLD_NO_SCORABLE_OUTER_BLOCK"
        combined_interaction = {
            "interaction": "storage×weather×season×volatility",
            "disposition": combined_disposition,
            "dataset_id": combined_dataset_id,
            "nested_outer": combined_nested,
            "skipped_outer": combined_skipped,
            "nested_selection_score": combined_candidate,
            "matched_control_score": combined_control,
            "mean_monthly_net_return_delta": combined_delta,
        }

    registered_interaction_dispositions = {
        "storage×season": "SCORED_WITH_STORAGE_FAMILY_SEARCH" if "storage" in scorable_families else "HOLD_SOURCE_GATE",
        "weather×season": "SCORED_WITH_WEATHER_FAMILY_SEARCH" if "weather" in scorable_families else "HOLD_SOURCE_GATE",
        "positioning×volatility": (
            "SCORED_WITH_POSITIONING_FAMILY_SEARCH"
            if "positioning" in scorable_families
            else "HOLD_SOURCE_GATE"
        ),
        "storage×weather×season×volatility": combined_interaction["disposition"],
        "power×weather": "HOLD_POWER_SOURCE_GATE",
    }
    trial_records = ledger._records()
    trial_ledger_file = Path(trial_ledger_path)
    trial_ledger_sha256 = (
        _sha256_file(trial_ledger_file)
        if trial_ledger_file.is_file()
        else _sha256_payload([])
    )

    return {
        "schema_version": 1,
        "issue": 426,
        "programme_issue": 393,
        "status": (
            "development_optimization_complete"
            if "weather" in scorable_families
            else "partial_historical_family_optimization"
        ),
        "evidence_class": "development",
        "protected_confirmation_accessed": False,
        "true_forward_accessed": False,
        "prospective_paper_accessed": False,
        "saxo_sim_accessed": False,
        "saxo_live_accessed": False,
        "registry_id": registry.registry_id,
        "search_plan_sha256": _sha256_file(Path(search_plan_path)),
        "source_plan_sha256": _sha256_file(Path(source_plan_path)),
        "optimization_plan_sha256": _sha256_file(Path(optimization_plan_path)),
        "weather_feature_contract_sha256": _sha256_file(weather_contract_path),
        "interaction_contract_sha256": _sha256_file(interaction_contract_path),
        "issue425_result_sha256": _sha256_file(Path(issue425_result_path)),
        "market_session_path_sha256": session_manifest["data_sha256"],
        "market_features_sha256": feature_manifest["data_sha256"],
        "code_id": code_id,
        "source_gate": source_gate,
        "scorable_families": scorable_families,
        "family_results": family_results,
        "combined_interaction": combined_interaction,
        "registered_interaction_dispositions": registered_interaction_dispositions,
        "trial_count": len(trial_records),
        "trial_ledger_sha256": trial_ledger_sha256,
        "claim_boundary": (
            "development-only matched family and registered-interaction optimization; "
            "no protected confirmation, forward, paper, SIM, or LIVE evidence accessed"
        ),
    }
