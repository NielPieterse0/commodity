from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from commodity.config import assumptions_config, data_config
from commodity.rolls import build_derived_contract_path
from commodity.volatility_diagnostic import (
    EPSILON,
    _fit_log_har,
    _garman_klass_variance,
    _predict_log_har,
    _qlike,
)
from commodity.volatility_nuisance_calibration import load_calibration_market

RELEASE_SHA256 = "c0a0197d8d55a932c66104dd78a6a76105a893b1b6af7b5f5359eb15b0879a0a"
DATA_SOURCES_SHA256 = "8fb567163b1b703aebb2849a42a31c6ad1c81fa5114f334d032a3f1215609033"
TRAIN_IDENTITY_SHA256 = "b928f239cca2936b1930825129125cb42c753d480cd65aa83c26ecf83eca6745"
CALIBRATION_IDENTITY_SHA256 = "2e7c428735b74e304c5ed6412b3c279b98372abca093acbf77737f537a287fc6"
DEVELOPMENT_START = pd.Timestamp("2015-09-09T23:59:00Z")
DEVELOPMENT_END = pd.Timestamp("2018-10-26T23:59:00Z")
TRAIN_EVENTS = 80
CALIBRATION_EVENTS = 80
CONFIRMATION_EVENTS = 342
Z_ALPHA_OVER_2 = 1.959963984540054
Z_POWER = 0.8416212335729143


class VolatilityEventCalibrationError(RuntimeError):
    """Raised when the frozen event nuisance calibration cannot execute exactly."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_calibration_authority(repo_root: Path) -> dict[str, Any]:
    release_path = repo_root / (
        "docs/development/volatility-event-successor-release-audit/audit-release.json"
    )
    if _sha256(release_path) != RELEASE_SHA256:
        raise VolatilityEventCalibrationError("#207 release hash drifted")
    if _sha256(repo_root / "config/data_sources.json") != DATA_SOURCES_SHA256:
        raise VolatilityEventCalibrationError("data-source authority hash drifted")
    release = json.loads(release_path.read_text(encoding="utf-8"))
    authority = release.get("authority", {})
    if release.get("decision") != "pass_nuisance_calibration_only":
        raise VolatilityEventCalibrationError("#207 release decision drifted")
    if (
        authority.get("nuisance_calibration_80_authorized") is not True
        or authority.get("confirmation_342_authorized") is not False
        or authority.get("future_504_authorized") is not False
    ):
        raise VolatilityEventCalibrationError("#207 release authority drifted")
    source = release.get("source_authority", {})
    if (
        source.get("canonical_market_source") is not True
        or source.get("backtest_evidence_allowed") is not True
        or source.get("licensing_rights_verified") is not True
        or source.get("historical_availability_method") != "trade_date_2359_utc"
    ):
        raise VolatilityEventCalibrationError("Databento source authority drifted")
    return release


def _daily_anchor_sequence(market: pd.DataFrame) -> pd.DataFrame:
    schema = data_config()["canonical_contract_schema"]
    policy = assumptions_config()["assumptions"]["continuous_series_policy"]["policy"]
    selected = build_derived_contract_path(market, schema, policy).copy()
    selected["trade_date"] = pd.to_datetime(selected["trade_date"], utc=True)
    selected["available_at"] = pd.to_datetime(selected["available_at"], utc=True)
    selected = selected.sort_values("trade_date").reset_index(drop=True)
    window = selected.loc[
        selected.available_at.between(DEVELOPMENT_START, DEVELOPMENT_END)
    ].copy()
    if len(window) != 972:
        raise VolatilityEventCalibrationError(
            f"frozen 972-row development sequence drifted: {len(window)} rows"
        )
    return window

def _event_identity(rows: list[dict[str, Any]]) -> str:
    payload = "".join(
        row["prediction_time"].isoformat()
        + ","
        + row["contract_id"]
        + ","
        + "|".join(row["target_dates"])
        + "\n"
        for row in rows
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _event_from_anchor(
    anchor: Any,
    market: pd.DataFrame,
    global_dates: list[pd.Timestamp],
    date_position: dict[pd.Timestamp, int],
    lookup: dict[tuple[str, pd.Timestamp], Any],
    histories: dict[str, pd.DataFrame],
) -> dict[str, Any] | None:
    contract_id = str(anchor.contract_id)
    trade_date = pd.Timestamp(anchor.trade_date)
    prediction_time = pd.Timestamp(anchor.available_at)
    index = date_position[trade_date]
    target_dates = global_dates[index + 1 : index + 6]
    if len(target_dates) != 5:
        return None
    targets = [lookup.get((contract_id, date)) for date in target_dates]
    if any(target is None for target in targets):
        return None
    concrete_targets = [target for target in targets if target is not None]
    if not all(pd.Timestamp(target.available_at) > prediction_time for target in concrete_targets):
        raise VolatilityEventCalibrationError("five-session target PIT gate failed")
    history = histories[contract_id]
    history = history.loc[
        (history.trade_date <= trade_date) & (history.available_at <= prediction_time)
    ]
    if len(history) < 60:
        return None
    recent = history.tail(60)
    daily = np.asarray(
        [_garman_klass_variance(row) for _, row in recent.iterrows()], dtype=float
    )
    blocks = daily.reshape(12, 5).sum(axis=1)
    target_rv = float(
        sum(_garman_klass_variance(pd.Series(target._asdict())) for target in concrete_targets)
    )
    return {
        "prediction_time": prediction_time,
        "contract_id": contract_id,
        "target_dates": [pd.Timestamp(date).isoformat() for date in target_dates],
        "target_available_at": max(
            pd.Timestamp(target.available_at) for target in concrete_targets
        ),
        "target_rv": target_rv,
        "baseline_rv20": float(blocks[-4:].mean()),
        "log_rv_d1": math.log(max(float(blocks[-1]), EPSILON)),
        "log_rv_w5": math.log(max(float(blocks[-4:].mean()), EPSILON)),
        "log_rv_m20": math.log(max(float(blocks.mean()), EPSILON)),
    }


def _build_roles(market: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    market = market.copy()
    market["trade_date"] = pd.to_datetime(market.trade_date, utc=True)
    market["available_at"] = pd.to_datetime(market.available_at, utc=True)
    anchors = _daily_anchor_sequence(market).iloc[::5]
    global_dates = sorted(pd.Timestamp(date) for date in market.trade_date.unique())
    date_position = {date: index for index, date in enumerate(global_dates)}
    lookup = {(str(row.contract_id), row.trade_date): row for row in market.itertuples()}
    histories = {
        str(contract): group.sort_values("trade_date")
        for contract, group in market.groupby(market.contract_id.astype(str), sort=False)
    }
    events = [
        _event_from_anchor(anchor, market, global_dates, date_position, lookup, histories)
        for anchor in anchors.itertuples()
    ]
    admissible = [event for event in events if event is not None]
    if len(admissible) != 183:
        raise VolatilityEventCalibrationError(
            f"frozen development event count drifted: {len(admissible)}"
        )
    train = admissible[:TRAIN_EVENTS]
    calibration = admissible[TRAIN_EVENTS : TRAIN_EVENTS + CALIBRATION_EVENTS]
    if _event_identity(train) != TRAIN_IDENTITY_SHA256:
        raise VolatilityEventCalibrationError("80-event training identity drifted")
    if _event_identity(calibration) != CALIBRATION_IDENTITY_SHA256:
        raise VolatilityEventCalibrationError("80-event calibration identity drifted")
    return pd.DataFrame(train + calibration), pd.DataFrame(calibration)


def _centered_block_sd(values: np.ndarray, block_size: int) -> float:
    centered = np.asarray(values, dtype=float) - float(np.mean(values))
    means = np.asarray(
        [
            centered[index : index + block_size].mean()
            for index in range(len(centered) - block_size + 1)
        ],
        dtype=float,
    )
    return float(np.std(means, ddof=1))


def _walk_forward_losses(events: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    baseline_losses: list[float] = []
    paired_losses: list[float] = []
    coefficients: np.ndarray | None = None
    for position in range(TRAIN_EVENTS, len(events)):
        current = events.iloc[position]
        current_time = pd.Timestamp(current.prediction_time)
        if coefficients is None or (position - TRAIN_EVENTS) % 4 == 0:
            prior = events.iloc[:position]
            training = prior.loc[prior.target_available_at <= current_time]
            if len(training) != position:
                raise VolatilityEventCalibrationError("training-label PIT gate failed")
            coefficients = _fit_log_har(training)
        assert coefficients is not None
        actual = np.asarray([float(current.target_rv)])
        baseline = np.asarray([float(current.baseline_rv20)])
        challenger = np.asarray([_predict_log_har(coefficients, current)])
        baseline_loss = float(_qlike(actual, baseline)[0])
        challenger_loss = float(_qlike(actual, challenger)[0])
        baseline_losses.append(baseline_loss)
        paired_losses.append(baseline_loss - challenger_loss)
    return np.asarray(baseline_losses), np.asarray(paired_losses)


def _relative_mde(block_size: int, block_sd: float, baseline_scale: float) -> float:
    absolute = (Z_ALPHA_OVER_2 + Z_POWER) * block_sd / math.sqrt(
        CONFIRMATION_EVENTS / block_size
    )
    return float(absolute / baseline_scale)


def run_calibration(repo_root: Path, archive_root: Path) -> dict[str, Any]:
    release = validate_calibration_authority(repo_root)
    market = load_calibration_market(archive_root)
    events, calibration = _build_roles(market)
    baseline_losses, paired_losses = _walk_forward_losses(events)
    if len(baseline_losses) != CALIBRATION_EVENTS:
        raise VolatilityEventCalibrationError("calibration loss count drifted")
    mean_baseline = float(np.mean(baseline_losses))
    block_sd = {
        block: _centered_block_sd(paired_losses, block) for block in (2, 4, 8)
    }
    relative_mde = {
        block: _relative_mde(block, block_sd[block], mean_baseline)
        for block in (2, 4, 8)
    }
    return {
        "schema_version": 1,
        "calibration_id": "volatility-209-event-nuisance-v1",
        "issue": 209,
        "release_id": release["release_id"],
        "release_sha256": RELEASE_SHA256,
        "train_identity_sha256": TRAIN_IDENTITY_SHA256,
        "calibration_identity_sha256": CALIBRATION_IDENTITY_SHA256,
        "calibration_events": len(calibration),        "confirmation_events": CONFIRMATION_EVENTS,
        "mean_baseline_qlike": mean_baseline,
        "centered_paired_loss_block_sd_2": block_sd[2],
        "centered_paired_loss_block_sd_4": block_sd[4],
        "centered_paired_loss_block_sd_8": block_sd[8],
        "relative_mde_at_exact_confirmation_n": {
            "2_events": relative_mde[2],
            "4_events": relative_mde[4],
            "8_events": relative_mde[8],
        },
        "power_gate_pass": bool(all(value <= 0.05 for value in relative_mde.values())),
        "protected_confirmation_performance_inspected": False,
        "future_504_performance_inspected": False,
    }


def write_calibration_summary(
    repo_root: Path, archive_root: Path, output_path: Path
) -> dict[str, Any]:
    result = run_calibration(repo_root, archive_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result
