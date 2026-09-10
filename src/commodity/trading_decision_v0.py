from __future__ import annotations

import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from commodity.data_assurance import DataAssuranceError, assert_research_ready
from commodity.models.baselines import baseline_factory


class DecisionSystemError(ValueError):
    """Raised when the Phase-1 decision-system contract cannot be reconstructed."""


@dataclass(frozen=True)
class ExecutionCostAssumptions:
    commission_usd_per_side: float
    exchange_clearing_fees_usd_per_side: float
    half_spread_ticks_per_side: float
    slippage_ticks_per_side: float
    initial_margin_usd_per_contract: float
    tick_value_usd: float

    @property
    def per_side_usd(self) -> float:
        market_friction_ticks = self.half_spread_ticks_per_side + self.slippage_ticks_per_side
        return (
            self.commission_usd_per_side
            + self.exchange_clearing_fees_usd_per_side
            + market_friction_ticks * self.tick_value_usd
        )

    @property
    def round_trip_usd(self) -> float:
        return 2.0 * self.per_side_usd


@dataclass(frozen=True)
class PaperRiskPolicy:
    capital_usd: float
    max_contracts: int
    daily_loss_fraction: float
    peak_drawdown_kill_fraction: float
    after_kill: str
    live_trading_allowed: bool


@dataclass(frozen=True)
class InputBoundary:
    instrument: str
    roll_policy: str
    evidence_partition: str
    protected_confirmation_accessed: bool
    data_assurance_sha256: str


_COST_STATUS = "declared_research_assumption_unverified_broker_terms"
_AFTER_KILL = "remain_flat_until_explicit_operator_restart"


def _finite_nonnegative(value: object, label: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise DecisionSystemError(f"{label} must be finite and non-negative")
    return parsed


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        check=False,
    )


def governed_input_authority_identity(
    authority_path: Path,
    *,
    repo_root: Path,
    expected_sha256: str,
) -> dict[str, str]:
    repo = Path(repo_root).resolve()
    raw_authority = Path(authority_path)
    if raw_authority.is_symlink():
        raise DecisionSystemError("input authority must be a regular repository file")
    try:
        authority = raw_authority.resolve(strict=True)
        relative = authority.relative_to(repo)
    except (FileNotFoundError, ValueError) as exc:
        raise DecisionSystemError("input authority must be inside the Commodity repository") from exc
    if not authority.is_file():
        raise DecisionSystemError("input authority must be a regular repository file")

    top = _git(repo, "rev-parse", "--show-toplevel")
    if top.returncode != 0 or Path(top.stdout.decode().strip()).resolve() != repo:
        raise DecisionSystemError("input authority repository identity cannot be verified")
    relative_git = relative.as_posix()
    head = _git(repo, "rev-parse", "HEAD")
    blob = _git(repo, "rev-parse", f"HEAD:{relative_git}")
    clean = _git(repo, "diff", "--quiet", "HEAD", "--", relative_git)
    if head.returncode != 0 or blob.returncode != 0 or clean.returncode != 0:
        raise DecisionSystemError("input authority must be Git-committed and unchanged at HEAD")

    observed_sha256 = hashlib.sha256(authority.read_bytes()).hexdigest()
    clean_after_read = _git(repo, "diff", "--quiet", "HEAD", "--", relative_git)
    if clean_after_read.returncode != 0 or observed_sha256 != expected_sha256.lower():
        raise DecisionSystemError("input authority changed while being validated")
    return {
        "repo_relative_path": relative_git,
        "git_commit": head.stdout.decode().strip().lower(),
        "git_blob": blob.stdout.decode().strip().lower(),
        "sha256": observed_sha256,
    }


def parse_input_boundary(
    payload: dict[str, object],
    *,
    allowed_partitions: set[str],
    observed_hashes: dict[str, str],
    expected_instrument: str | None = None,
    expected_roll_policy: str | None = None,
) -> InputBoundary:
    if payload.get("schema_version") != 2:
        raise DecisionSystemError("input boundary schema_version must be 2")
    assurance = payload.get("data_assurance")
    try:
        ready_assurance = assert_research_ready(
            assurance if isinstance(assurance, dict) else None
        )
    except DataAssuranceError as exc:
        raise DecisionSystemError(
            "input authority requires research-ready data assurance"
        ) from exc
    instrument = str(payload.get("instrument", "")).strip()
    roll_policy = str(payload.get("roll_policy", "")).strip()
    if not instrument:
        raise DecisionSystemError("input authority must declare instrument")
    if not roll_policy:
        raise DecisionSystemError("input authority must declare roll policy")
    if expected_instrument is not None and instrument != expected_instrument:
        raise DecisionSystemError(
            f"input authority instrument does not match simulation: {instrument!r}"
        )
    if expected_roll_policy is not None and roll_policy != expected_roll_policy:
        raise DecisionSystemError(
            f"input authority roll policy does not match simulation: {roll_policy!r}"
        )
    partition = str(payload.get("evidence_partition", "")).strip()
    if not partition or partition not in allowed_partitions:
        raise DecisionSystemError(f"input evidence partition is not allowed: {partition!r}")
    if payload.get("protected_confirmation_accessed") is not False:
        raise DecisionSystemError("protected confirmation is prohibited for Phase-1 decision runs")
    required_hashes = ("market_sha256", "selected_path_sha256", "features_sha256")
    missing = [key for key in required_hashes if key not in payload]
    if missing:
        raise DecisionSystemError(f"input boundary missing source hashes: {missing}")
    for key in required_hashes:
        expected = str(payload[key]).strip().lower()
        observed = str(observed_hashes.get(key, "")).strip().lower()
        if expected != observed:
            raise DecisionSystemError(f"input boundary hash mismatch: {key}")
    return InputBoundary(
        instrument=instrument,
        roll_policy=roll_policy,
        evidence_partition=partition,
        protected_confirmation_accessed=False,
        data_assurance_sha256=str(ready_assurance["assurance_sha256"]),
    )


def parse_cost_assumptions(
    payload: dict[str, object], *, tick_value_usd: float
) -> ExecutionCostAssumptions:
    if payload.get("assumption_status") != _COST_STATUS:
        raise DecisionSystemError("cost inputs must remain an explicit unverified research assumption")
    required = (
        "commission_usd_per_side",
        "exchange_clearing_fees_usd_per_side",
        "half_spread_ticks_per_side",
        "slippage_ticks_per_side",
        "initial_margin_usd_per_contract",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise DecisionSystemError(f"cost assumptions missing explicit fields: {missing}")
    tick_value = _finite_nonnegative(tick_value_usd, "tick_value_usd")
    if tick_value <= 0:
        raise DecisionSystemError("tick_value_usd must be positive")
    return ExecutionCostAssumptions(
        commission_usd_per_side=_finite_nonnegative(
            payload["commission_usd_per_side"], "commission_usd_per_side"
        ),
        exchange_clearing_fees_usd_per_side=_finite_nonnegative(
            payload["exchange_clearing_fees_usd_per_side"],
            "exchange_clearing_fees_usd_per_side",
        ),
        half_spread_ticks_per_side=_finite_nonnegative(
            payload["half_spread_ticks_per_side"], "half_spread_ticks_per_side"
        ),
        slippage_ticks_per_side=_finite_nonnegative(
            payload["slippage_ticks_per_side"], "slippage_ticks_per_side"
        ),
        initial_margin_usd_per_contract=_finite_nonnegative(
            payload["initial_margin_usd_per_contract"], "initial_margin_usd_per_contract"
        ),
        tick_value_usd=tick_value,
    )


def parse_risk_policy(payload: dict[str, object]) -> PaperRiskPolicy:
    required = (
        "capital_usd",
        "max_standard_contracts",
        "daily_loss_fraction",
        "peak_drawdown_kill_fraction",
        "after_kill",
        "live_trading_allowed",
        "model_tunable",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise DecisionSystemError(f"risk policy missing operator-owned fields: {missing}")
    capital = _finite_nonnegative(payload["capital_usd"], "capital_usd")
    max_contracts = int(payload["max_standard_contracts"])
    daily_loss = float(payload["daily_loss_fraction"])
    drawdown = float(payload["peak_drawdown_kill_fraction"])
    if capital <= 0 or max_contracts < 0:
        raise DecisionSystemError("paper capital must be positive and max contracts non-negative")
    if not 0 < daily_loss < 1 or not 0 < drawdown < 1:
        raise DecisionSystemError("loss and drawdown fractions must be between zero and one")
    if payload["after_kill"] != _AFTER_KILL:
        raise DecisionSystemError("kill behavior must require explicit operator restart")
    if payload["live_trading_allowed"] is not False:
        raise DecisionSystemError("Phase-1 risk policy must prohibit live trading")
    if payload["model_tunable"] is not False:
        raise DecisionSystemError("Phase-1 operator risk policy must not be model-tunable")
    return PaperRiskPolicy(
        capital_usd=capital,
        max_contracts=max_contracts,
        daily_loss_fraction=daily_loss,
        peak_drawdown_kill_fraction=drawdown,
        after_kill=str(payload["after_kill"]),
        live_trading_allowed=False,
    )


def _utc_column(frame: pd.DataFrame, column: str, label: str) -> pd.Series:
    values = pd.to_datetime(frame[column], utc=True, errors="coerce")
    if values.isna().any():
        raise DecisionSystemError(f"{label} contains invalid {column}")
    return values


def build_roll_safe_session_path(
    canonical_rows: pd.DataFrame,
    selected_path: pd.DataFrame,
    *,
    price_col: str = "open",
) -> pd.DataFrame:
    market_required = {"trade_date", "contract_id", price_col}
    selected_required = {
        "trade_date",
        "contract_id",
        "available_at",
        "session_open",
        "roll_reason",
    }
    missing_market = sorted(market_required - set(canonical_rows.columns))
    missing_selected = sorted(selected_required - set(selected_path.columns))
    if missing_market:
        raise DecisionSystemError(f"canonical rows missing columns: {missing_market}")
    if missing_selected:
        raise DecisionSystemError(f"selected path missing columns: {missing_selected}")

    market = canonical_rows.copy()
    selected = selected_path.copy()
    market["trade_date"] = _utc_column(market, "trade_date", "canonical rows")
    selected["trade_date"] = _utc_column(selected, "trade_date", "selected path")
    selected["available_at"] = _utc_column(selected, "available_at", "selected path")
    selected["session_open"] = _utc_column(selected, "session_open", "selected path")
    market[price_col] = pd.to_numeric(market[price_col], errors="coerce")
    if not np.isfinite(market[price_col].to_numpy(dtype="float64")).all():
        raise DecisionSystemError(f"canonical rows contain non-finite {price_col}")
    if (market[price_col] <= 0).any():
        raise DecisionSystemError(f"canonical rows require positive {price_col}")
    if market.duplicated(["trade_date", "contract_id"]).any():
        raise DecisionSystemError("canonical rows must be unique by trade_date and contract_id")
    if selected["trade_date"].duplicated().any():
        raise DecisionSystemError("selected path must contain one contract per trade_date")
    selected = selected.sort_values("trade_date").reset_index(drop=True)
    if not selected["session_open"].is_monotonic_increasing:
        raise DecisionSystemError("selected session opens must be chronological")
    if selected["session_open"].duplicated().any():
        raise DecisionSystemError("selected session opens must be unique")
    if (selected["available_at"] > selected["session_open"]).any():
        raise DecisionSystemError(
            "selected contract must be known no later than its executable session open"
        )

    market_index = market.set_index(["trade_date", "contract_id"])
    records: list[dict[str, object]] = []
    for index, current in selected.iterrows():
        key = (current["trade_date"], current["contract_id"])
        if key not in market_index.index:
            raise DecisionSystemError(f"selected contract open missing: {key}")
        current_price = float(market_index.loc[key, price_col])
        record = current.to_dict()
        record["open_price"] = current_price
        if index + 1 < len(selected):
            nxt = selected.iloc[index + 1]
            next_key = (nxt["trade_date"], current["contract_id"])
            if next_key not in market_index.index:
                raise DecisionSystemError(
                    "same-contract next open is missing for held contract "
                    f"{current['contract_id']} at {nxt['trade_date'].isoformat()}"
                )
            next_same_contract = float(market_index.loc[next_key, price_col])
            record.update({
                "next_trade_date": nxt["trade_date"],
                "next_session_open": nxt["session_open"],
                "next_selected_contract_id": str(nxt["contract_id"]),
                "next_open_same_contract": next_same_contract,
                "path_move_per_mmbtu": next_same_contract - current_price,
                "roll_at_next_open": str(nxt["contract_id"]) != str(current["contract_id"]),
            })
        else:
            record.update({
                "next_trade_date": pd.NaT,
                "next_session_open": pd.NaT,
                "next_selected_contract_id": None,
                "next_open_same_contract": np.nan,
                "path_move_per_mmbtu": np.nan,
                "roll_at_next_open": False,
            })
        records.append(record)
    return pd.DataFrame(records)


def _normalize_features(features: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    required = {"trade_date", "available_at"}
    missing = sorted(required - set(features.columns))
    if missing:
        raise DecisionSystemError(f"features missing columns: {missing}")
    out = features.copy()
    out["trade_date"] = _utc_column(out, "trade_date", "features")
    out["available_at"] = _utc_column(out, "available_at", "features")
    if out["trade_date"].duplicated().any():
        raise DecisionSystemError("features must contain one row per trade_date")
    feature_columns = sorted(column for column in out.columns if column.startswith("feature_"))
    if not feature_columns:
        raise DecisionSystemError("features require at least one feature_ column")
    for column in feature_columns:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    if not np.isfinite(out[feature_columns].to_numpy(dtype="float64")).all():
        raise DecisionSystemError("features contain non-finite values")
    return out.sort_values("trade_date").reset_index(drop=True), feature_columns


def _decision_origins(
    path: pd.DataFrame,
    features: pd.DataFrame,
    *,
    horizon_sessions: int,
) -> tuple[pd.DataFrame, list[str]]:
    if horizon_sessions < 1:
        raise DecisionSystemError("horizon_sessions must be positive")
    feature_frame, feature_columns = _normalize_features(features)
    selected = path[["trade_date", "available_at"]].rename(
        columns={"available_at": "selected_available_at"}
    )
    merged = feature_frame.merge(selected, on="trade_date", how="inner", validate="one_to_one")
    if len(merged) != len(feature_frame):
        raise DecisionSystemError("every feature origin must map to the selected contract path")
    merged["signal_timestamp"] = merged[["available_at", "selected_available_at"]].max(axis=1)
    opens = path["session_open"].tolist()
    records: list[dict[str, object]] = []
    for _, origin in merged.sort_values("trade_date").iterrows():
        signal = pd.Timestamp(origin["signal_timestamp"])
        fill_index = next((i for i, value in enumerate(opens) if pd.Timestamp(value) > signal), None)
        if fill_index is None or fill_index + horizon_sessions > len(path) - 1:
            continue
        target_slice = path.iloc[fill_index : fill_index + horizon_sessions]
        moves = target_slice["path_move_per_mmbtu"].to_numpy(dtype="float64")
        if len(moves) != horizon_sessions or not np.isfinite(moves).all():
            raise DecisionSystemError("five-session target cannot be reconstructed exactly")
        target_end = pd.Timestamp(target_slice.iloc[-1]["next_session_open"])
        record = origin.to_dict()
        record.update({
            "fill_index": int(fill_index),
            "fill_trade_date": path.iloc[fill_index]["trade_date"],
            "fill_timestamp": path.iloc[fill_index]["session_open"],
            "fill_contract_id": str(path.iloc[fill_index]["contract_id"]),
            "target_end_timestamp": target_end,
            "target_path_move_per_mmbtu": float(moves.sum()),
        })
        records.append(record)
    return pd.DataFrame(records), feature_columns


def build_decision_origins(
    path: pd.DataFrame,
    features: pd.DataFrame,
    *,
    horizon_sessions: int,
) -> tuple[pd.DataFrame, list[str]]:
    """Expose the Phase-1 target/origin contract for later governed research phases."""
    return _decision_origins(path, features, horizon_sessions=horizon_sessions)


def _uncertainty(target: pd.Series, residuals: pd.Series | None = None) -> float:
    values = residuals if residuals is not None and len(residuals) > 1 else target
    if len(values) <= 1:
        return 0.0
    result = float(values.std(ddof=1))
    return result if math.isfinite(result) else 0.0


def _forecast_id(origin_date: pd.Timestamp, fill_date: pd.Timestamp, model_id: str) -> str:
    payload = json.dumps(
        {
            "origin": origin_date.isoformat(),
            "fill": fill_date.isoformat(),
            "model": model_id,
            "contract": "phase1-v0",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def build_walk_forward_forecasts(
    path: pd.DataFrame,
    features: pd.DataFrame,
    *,
    models: dict[str, dict[str, Any]],
    horizon_sessions: int,
    contract_multiplier: float,
    selected_model: str,
    min_train_rows: int = 20,
) -> pd.DataFrame:
    origins, feature_columns = _decision_origins(
        path, features, horizon_sessions=horizon_sessions
    )
    if origins.empty:
        return pd.DataFrame()
    enabled_implementations = {
        str(cfg.get("baseline_implementation"))
        for cfg in models.values()
        if cfg.get("enabled", False)
    }
    fixed_baselines: list[str] = []
    if "zero_return" in enabled_implementations:
        fixed_baselines.append("zero")
    if "expanding_mean_return" in enabled_implementations:
        fixed_baselines.append("expanding_mean")
    candidate_models = [
        name
        for name, cfg in models.items()
        if cfg.get("enabled", False)
        and cfg.get("baseline_implementation") in {
            "ridge_return",
            "hist_gradient_boosting_return",
        }
    ]
    allowed_models = {*fixed_baselines, *candidate_models}
    if selected_model not in allowed_models:
        raise DecisionSystemError(f"selected model is not in the Phase-1 ladder: {selected_model}")
    multiplier = _finite_nonnegative(contract_multiplier, "contract_multiplier")
    if multiplier <= 0:
        raise DecisionSystemError("contract_multiplier must be positive")
    if min_train_rows < 1:
        raise DecisionSystemError("min_train_rows must be positive")

    output: list[dict[str, object]] = []
    for _, origin in origins.sort_values("signal_timestamp").iterrows():
        signal = pd.Timestamp(origin["signal_timestamp"])
        training = origins.loc[origins["target_end_timestamp"] <= signal]
        if len(training) < min_train_rows:
            continue
        x_train = training[feature_columns]
        y_train = training["target_path_move_per_mmbtu"].astype(float)
        x_current = pd.DataFrame([origin[feature_columns].to_dict()], columns=feature_columns)
        latest_training_end = pd.Timestamp(training["target_end_timestamp"].max())
        for model_id in [*fixed_baselines, *candidate_models]:
            residuals: pd.Series | None = None
            if model_id == "zero":
                prediction = 0.0
                residuals = y_train.copy()
            elif model_id == "expanding_mean":
                prediction = float(y_train.mean())
                residuals = y_train - prediction
            else:
                model = baseline_factory(model_id, models)()
                model.fit(x_train, y_train)
                prediction = float(model.predict(x_current).iloc[0])
                train_prediction = model.predict(x_train).astype(float)
                residuals = y_train.reset_index(drop=True) - train_prediction.reset_index(drop=True)
            uncertainty = _uncertainty(y_train, residuals)
            output.append({
                "forecast_id": _forecast_id(
                    pd.Timestamp(origin["trade_date"]),
                    pd.Timestamp(origin["fill_trade_date"]),
                    model_id,
                ),
                "model_id": model_id,
                "origin_trade_date": origin["trade_date"],
                "signal_timestamp": signal,
                "fill_trade_date": origin["fill_trade_date"],
                "fill_timestamp": origin["fill_timestamp"],
                "fill_contract_id": origin["fill_contract_id"],
                "target_end_timestamp": origin["target_end_timestamp"],
                "latest_training_target_end": latest_training_end,
                "training_rows": len(training),
                "predicted_path_move_per_mmbtu": prediction,
                "predicted_gross_pnl_usd": prediction * multiplier,
                "uncertainty_per_mmbtu": uncertainty,
                "uncertainty_usd": uncertainty * multiplier,
                "actual_path_move_per_mmbtu": origin["target_path_move_per_mmbtu"],
                "actual_gross_pnl_usd": float(origin["target_path_move_per_mmbtu"]) * multiplier,
                "horizon_sessions": int(horizon_sessions),
            })
    result = pd.DataFrame(output)
    if not result.empty:
        result = result.sort_values(["fill_timestamp", "model_id"]).reset_index(drop=True)
    return result


def _forecast_for_date(forecasts: pd.DataFrame, trade_date: pd.Timestamp) -> pd.Series | None:
    if forecasts.empty or "fill_trade_date" not in forecasts.columns:
        return None
    normalized = forecasts.copy()
    normalized["fill_trade_date"] = pd.to_datetime(
        normalized["fill_trade_date"], utc=True, errors="coerce"
    )
    matches = normalized.loc[normalized["fill_trade_date"] == trade_date]
    if len(matches) > 1:
        raise DecisionSystemError("a policy may consume only one selected-model forecast per fill")
    return None if matches.empty else matches.iloc[0]


def _requested_target(
    policy_id: str,
    forecast: pd.Series | None,
    costs: ExecutionCostAssumptions,
) -> tuple[int, str | None]:
    if policy_id == "flat":
        return 0, "flat_control"
    if policy_id == "long_only":
        return 1, None
    if policy_id != "forecast_sign":
        raise DecisionSystemError(f"unsupported benchmark policy: {policy_id}")
    if forecast is None:
        return 0, "no_forecast"
    predicted = float(forecast["predicted_gross_pnl_usd"])
    if not math.isfinite(predicted):
        raise DecisionSystemError("forecast predicted gross P&L must be finite")
    if abs(predicted) <= costs.round_trip_usd:
        return 0, "predicted_gross_pnl_not_above_round_trip_cost"
    return (1 if predicted > 0 else -1), None


def _forecast_horizon(
    forecast: pd.Series,
    path: pd.DataFrame,
    *,
    index: int,
    session_open: pd.Timestamp,
) -> tuple[pd.Timestamp, int]:
    required = {"target_end_timestamp", "horizon_sessions"}
    missing = sorted(required - set(forecast.index))
    if missing:
        raise DecisionSystemError(f"forecast missing horizon fields: {missing}")
    target_end = pd.to_datetime(forecast["target_end_timestamp"], utc=True, errors="coerce")
    if pd.isna(target_end):
        raise DecisionSystemError("forecast target end timestamp is invalid")
    target_end = pd.Timestamp(target_end)
    horizon = int(forecast["horizon_sessions"])
    if horizon < 1 or target_end <= session_open:
        raise DecisionSystemError("forecast horizon must end after its executable fill")
    future_next_opens = pd.to_datetime(
        path.iloc[index:]["next_session_open"], utc=True, errors="coerce"
    )
    remaining = int(((future_next_opens.notna()) & (future_next_opens <= target_end)).sum())
    if target_end not in set(future_next_opens.dropna()) or remaining != horizon:
        raise DecisionSystemError("forecast horizon does not match the executable session path")
    return target_end, horizon


def _remaining_horizon_sessions(
    path: pd.DataFrame,
    *,
    index: int,
    target_end: pd.Timestamp,
) -> int:
    future_next_opens = pd.to_datetime(
        path.iloc[index:]["next_session_open"], utc=True, errors="coerce"
    )
    return int(((future_next_opens.notna()) & (future_next_opens <= target_end)).sum())


def simulate_policy(
    path: pd.DataFrame,
    forecasts: pd.DataFrame,
    policy_id: str,
    risk: PaperRiskPolicy,
    costs: ExecutionCostAssumptions,
    *,
    contract_multiplier: float,
) -> tuple[pd.DataFrame, dict[str, object]]:
    multiplier = _finite_nonnegative(contract_multiplier, "contract_multiplier")
    if multiplier <= 0:
        raise DecisionSystemError("contract_multiplier must be positive")
    required = {
        "trade_date",
        "contract_id",
        "session_open",
        "open_price",
        "path_move_per_mmbtu",
        "next_selected_contract_id",
    }
    missing = sorted(required - set(path.columns))
    if missing:
        raise DecisionSystemError(f"session path missing simulation fields: {missing}")

    equity = risk.capital_usd
    peak_equity = equity
    previous_position = 0
    previous_contract: str | None = None
    killed = False
    kill_reason: str | None = None
    active_forecast: pd.Series | None = None
    active_target_end: pd.Timestamp | None = None
    rows: list[dict[str, object]] = []

    path = path.reset_index(drop=True)
    for index, session in path.iterrows():
        trade_date = pd.Timestamp(session["trade_date"])
        session_open = pd.Timestamp(session["session_open"])
        current_contract = str(session["contract_id"])
        fresh_forecast = _forecast_for_date(forecasts, trade_date)
        forecast = fresh_forecast
        expired_forecast = False
        if policy_id == "forecast_sign":
            if fresh_forecast is not None:
                active_target_end, _ = _forecast_horizon(
                    fresh_forecast,
                    path,
                    index=index,
                    session_open=session_open,
                )
                active_forecast = fresh_forecast
            elif active_forecast is not None and active_target_end is not None:
                if session_open < active_target_end:
                    forecast = active_forecast
                else:
                    forecast = None
                    active_forecast = None
                    active_target_end = None
                    expired_forecast = True
            requested, no_trade_reason = _requested_target(policy_id, forecast, costs)
            if expired_forecast:
                no_trade_reason = "forecast_horizon_expired"
        else:
            requested, no_trade_reason = _requested_target(policy_id, forecast, costs)
        if abs(requested) > risk.max_contracts:
            requested = int(math.copysign(risk.max_contracts, requested))
            no_trade_reason = "hard_contract_cap"
        if killed:
            requested = 0
            no_trade_reason = "risk_killed_until_explicit_operator_restart"
        if index == len(path) - 1:
            requested = 0
            no_trade_reason = "end_of_sample_liquidation"
        if requested and costs.initial_margin_usd_per_contract * abs(requested) > equity:
            requested = 0
            no_trade_reason = "insufficient_margin_assumption"

        contract_changed = (
            previous_position != 0
            and previous_contract is not None
            and previous_contract != current_contract
        )
        order_delta = requested - previous_position
        if contract_changed:
            execution_sides = abs(previous_position) + abs(requested)
            roll_sides = execution_sides
        else:
            execution_sides = abs(order_delta)
            roll_sides = 0
        transaction_cost = execution_sides * costs.per_side_usd
        equity_before = equity
        equity -= transaction_cost

        path_move = session["path_move_per_mmbtu"]
        if pd.isna(path_move):
            gross_pnl = 0.0
        else:
            gross_pnl = requested * float(path_move) * multiplier
            equity += gross_pnl
        net_pnl = gross_pnl - transaction_cost
        peak_equity = max(peak_equity, equity)
        daily_loss_usd = max(0.0, equity_before - equity)
        drawdown = 0.0 if peak_equity <= 0 else max(0.0, (peak_equity - equity) / peak_equity)
        trigger_reasons: list[str] = []
        if daily_loss_usd >= risk.capital_usd * risk.daily_loss_fraction:
            trigger_reasons.append("daily_loss_limit")
        if drawdown >= risk.peak_drawdown_kill_fraction:
            trigger_reasons.append("peak_drawdown_kill")
        if trigger_reasons and not killed:
            killed = True
            kill_reason = "+".join(trigger_reasons)

        forecast_id = None if forecast is None else str(forecast["forecast_id"])
        model_id = None if forecast is None else str(forecast["model_id"])
        predicted_gross = None if forecast is None else float(forecast["predicted_gross_pnl_usd"])
        uncertainty = None
        signal_timestamp = None
        forecast_horizon = 0
        remaining_horizon = 0
        if forecast is not None:
            if "uncertainty_usd" in forecast.index:
                uncertainty = float(forecast["uncertainty_usd"])
            if "signal_timestamp" in forecast.index:
                signal_timestamp = forecast["signal_timestamp"]
            if "horizon_sessions" in forecast.index:
                forecast_horizon = int(forecast["horizon_sessions"])
            if policy_id == "forecast_sign" and requested != 0:
                if active_target_end is None:
                    raise DecisionSystemError("active forecast target end is unavailable")
                remaining_horizon = _remaining_horizon_sessions(
                    path,
                    index=index,
                    target_end=active_target_end,
                )
        rows.append({
            "trade_date": trade_date,
            "session_open": session["session_open"],
            "fill_timestamp": session["session_open"],
            "contract_id": current_contract,
            "forecast_id": forecast_id,
            "signal_timestamp": signal_timestamp,
            "model_id": model_id,
            "predicted_gross_pnl_usd": predicted_gross,
            "forecast_uncertainty_usd": uncertainty,
            "prior_target_position": previous_position,
            "revised_target_position": requested,
            "target_position": requested,
            "order_delta": order_delta,
            "forecast_horizon_sessions": forecast_horizon,
            "remaining_horizon_sessions": remaining_horizon,
            "execution_side_count": int(execution_sides),
            "roll_side_count": int(roll_sides),
            "transaction_cost_usd": float(transaction_cost),
            "gross_pnl_usd": float(gross_pnl),
            "net_pnl_usd": float(net_pnl),
            "equity_usd": float(equity),
            "peak_equity_usd": float(peak_equity),
            "daily_loss_usd": float(daily_loss_usd),
            "drawdown_fraction": float(drawdown),
            "risk_state": "killed" if killed else "active",
            "kill_reason": kill_reason,
            "no_trade_reason": no_trade_reason,
            "roll_at_open": bool(contract_changed),
            "next_selected_contract_id": session["next_selected_contract_id"],
        })
        previous_position = requested
        previous_contract = current_contract if requested != 0 else None

    ledger = pd.DataFrame(rows)
    summary: dict[str, object] = {
        "policy_id": policy_id,
        "starting_capital_usd": float(risk.capital_usd),
        "ending_equity_usd": float(equity),
        "net_pnl_usd": float(equity - risk.capital_usd),
        "total_transaction_cost_usd": float(ledger["transaction_cost_usd"].sum()),
        "max_abs_contracts": int(ledger["target_position"].abs().max()) if len(ledger) else 0,
        "kill_triggered": bool(killed),
        "kill_reason": kill_reason,
        "operator_restart_required_after_kill": bool(killed),
        "risk_state_scope": "single_offline_replay",
        "persistent_paper_state_supported": False,
        "live_trading_allowed": False,
    }
    return ledger, summary


def selected_model_forecasts(forecasts: pd.DataFrame, model_id: str) -> pd.DataFrame:
    if forecasts.empty:
        raise DecisionSystemError(f"selected model produced no forecasts: {model_id}")
    selected = forecasts.loc[forecasts["model_id"] == model_id].copy()
    if selected.empty:
        raise DecisionSystemError(f"selected model produced no forecasts: {model_id}")
    return selected.reset_index(drop=True)
