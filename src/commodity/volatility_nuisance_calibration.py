from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from commodity.config import assumptions_config, data_config
from commodity.databento_futures_provider import (
    _load_databento_module,
    decode_databento_dbn_file,
)
from commodity.rolls import build_derived_contract_path
from commodity.volatility_diagnostic import (
    EPSILON,
    _fit_log_har,
    _garman_klass_variance,
    _predict_log_har,
    _qlike,
)

RELEASE_SHA256 = "e0f649035805693d56eea35c1354920947220ddc8867e3d7d36d2405ee53ca83"
DATA_SOURCES_SHA256 = "8fb567163b1b703aebb2849a42a31c6ad1c81fa5114f334d032a3f1215609033"
CALIBRATION_IDENTITY_SHA256 = "555203a63990d77223f1becb0806409808d17bb5ddcb542883123d94c16fdaef"
TRAIN_IDENTITY_SHA256 = "f132195bc1b77ec42bf98b8c2d636f11a7131ad5350b7694cf1288885d055e1c"
CONSUMED_BASELINE_QLIKE = 0.2751895286335185
CONSUMED_BLOCK_SD = {
    20: 0.038952880421331326,
    40: 0.02905340242691949,
    60: 0.022134902630199058,
}
Z_ALPHA_OVER_2 = 1.959963984540054
Z_POWER = 0.8416212335729143
PLANNED_ROWS = 1800
TRAIN_START = pd.Timestamp("2015-09-09T23:59:00Z")
TRAIN_END = pd.Timestamp("2016-07-01T23:59:00Z")
CALIBRATION_START = pd.Timestamp("2016-07-03T23:59:00Z")
CALIBRATION_END = pd.Timestamp("2018-10-26T23:59:00Z")


class VolatilityCalibrationError(RuntimeError):
    """Raised when the frozen nuisance calibration cannot execute exactly."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(path: Path, expected: str, label: str) -> None:
    observed = _sha256(path)
    if observed != expected:
        raise VolatilityCalibrationError(
            f"{label} hash drifted: expected {expected}, observed {observed}"
        )

def validate_calibration_authority(repo_root: Path) -> dict[str, Any]:
    release_path = (
        repo_root
        / "docs/development/volatility-successor-release-audit/audit-release.json"
    )
    _require_hash(release_path, RELEASE_SHA256, "#201 audit release")
    _require_hash(repo_root / "config/data_sources.json", DATA_SOURCES_SHA256, "data sources")
    release = json.loads(release_path.read_text(encoding="utf-8"))
    authority = release.get("authority", {})
    if (
        release.get("decision") != "pass_nuisance_calibration_only"
        or authority.get("nuisance_calibration_720_authorized") is not True
        or authority.get("scored_confirmation_1800_authorized") is not False
        or authority.get("existing_504_future_rows_authorized") is not False
    ):
        raise VolatilityCalibrationError("#201 release authority drifted")
    source = release.get("source_authority", {})
    if (
        source.get("canonical_market_source") is not True
        or source.get("backtest_evidence_allowed") is not True
        or source.get("licensing_rights_verified") is not True
        or source.get("historical_availability_method") != "trade_date_2359_utc"
    ):
        raise VolatilityCalibrationError("Databento source authority drifted")
    return release


def _annual_file(root: Path, schema: str, year: int) -> Path:
    dirs = list((root / schema).glob("GLBX-*"))
    if len(dirs) != 1:
        raise VolatilityCalibrationError(f"expected one Databento {schema} job directory")
    matches = list(dirs[0].glob(f"glbx-mdp3-{year}0101-{year}1231.{schema}.dbn.zst"))
    if len(matches) != 1:
        raise VolatilityCalibrationError(f"missing exact {year} {schema} archive file")
    return matches[0]

def _load_definition_identity(path: Path) -> pd.DataFrame:
    databento = _load_databento_module()
    store = databento.DBNStore.from_file(path)
    selected: list[pd.DataFrame] = []
    for chunk in store.to_df(map_symbols=False, count=250_000):
        frame = chunk.reset_index()
        keep = (
            frame["asset"].astype(str).eq("NG")
            & frame["instrument_class"].astype(str).eq("F")
        )
        if keep.any():
            selected.append(
                frame.loc[keep, ["instrument_id", "raw_symbol", "expiration", "ts_recv"]].copy()
            )
    if not selected:
        raise VolatilityCalibrationError(f"no NG outright definitions in {path.name}")
    identity = pd.concat(selected, ignore_index=True)
    identity["map_time"] = pd.to_datetime(identity["ts_recv"], utc=True)
    identity["expiration"] = pd.to_datetime(identity["expiration"], utc=True)
    return identity.sort_values("map_time").drop_duplicates(
        ["instrument_id", "map_time"], keep="last"
    )


def _load_ohlcv_year(root: Path, year: int) -> pd.DataFrame:
    definitions = _load_definition_identity(_annual_file(root, "definition", year))
    ohlcv, _ = decode_databento_dbn_file(
        _annual_file(root, "ohlcv-1d", year), expected_schema="ohlcv-1d"
    )
    ohlcv["event_time"] = pd.to_datetime(ohlcv["ts_event"], utc=True)
    mapped = pd.merge_asof(
        ohlcv.sort_values("event_time"),
        definitions[["instrument_id", "raw_symbol", "expiration", "map_time"]].sort_values("map_time"),
        left_on="event_time",
        right_on="map_time",
        by="instrument_id",
        direction="backward",
        allow_exact_matches=True,
    ).dropna(subset=["raw_symbol", "expiration"])
    mapped["trade_date"] = mapped["event_time"].dt.normalize()
    availability_offset = pd.to_timedelta(23 * 60 + 59, unit="min")
    mapped["available_at"] = mapped["trade_date"] + availability_offset
    for column in ["open", "high", "low", "close", "volume"]:
        mapped[column] = pd.to_numeric(mapped[column], errors="coerce")
    frame = mapped[
        ["trade_date", "raw_symbol", "expiration", "open", "high", "low", "close", "volume", "available_at"]
    ].rename(columns={"raw_symbol": "contract_id"})
    frame["settle"] = frame["close"]
    frame = frame.drop_duplicates(["trade_date", "contract_id"], keep="last")
    return frame


def load_calibration_market(archive_root: Path) -> pd.DataFrame:
    frames = [_load_ohlcv_year(archive_root, year) for year in range(2015, 2019)]
    market = pd.concat(frames, ignore_index=True).sort_values(
        ["trade_date", "expiration", "contract_id"]
    )
    if market.empty:
        raise VolatilityCalibrationError("Databento calibration market is empty")
    return market

def _identity_sha(frame: pd.DataFrame) -> str:
    columns = ["prediction_time", "trade_date", "contract_id", "target_trade_date"]
    payload = frame[columns].to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _candidate_rows(market: pd.DataFrame) -> pd.DataFrame:
    schema = data_config()["canonical_contract_schema"]
    policy = assumptions_config()["assumptions"]["continuous_series_policy"]["policy"]
    selected = build_derived_contract_path(market, schema, policy).copy()
    selected["trade_date"] = pd.to_datetime(selected["trade_date"], utc=True)
    selected["available_at"] = pd.to_datetime(selected["available_at"], utc=True)
    selected = selected.sort_values("trade_date").reset_index(drop=True)
    next_dates = dict(zip(selected.trade_date.iloc[:-1], selected.trade_date.iloc[1:]))
    lookup = {
        (str(row.contract_id), row.trade_date): row
        for row in market.itertuples()
    }
    histories = {
        str(cid): group.sort_values("trade_date")
        for cid, group in market.groupby(market.contract_id.astype(str), sort=False)
    }
    rows: list[dict[str, Any]] = []
    for chosen in selected.itertuples():
        prediction_time = pd.Timestamp(chosen.available_at)
        if prediction_time < TRAIN_START or prediction_time > CALIBRATION_END:
            continue
        contract_id = str(chosen.contract_id)
        trade_date = pd.Timestamp(chosen.trade_date)
        target_trade_date = next_dates.get(trade_date)
        target = lookup.get((contract_id, target_trade_date))
        if target is None:
            raise VolatilityCalibrationError("same-contract target row is unavailable")
        target_available = pd.Timestamp(target.available_at)
        if target_available <= prediction_time:
            raise VolatilityCalibrationError("target bar is not strictly future at cutoff")
        history = histories[contract_id]
        history = history.loc[
            (history["trade_date"] <= trade_date)
            & (history["available_at"] <= prediction_time)
        ]
        if len(history) < 20:
            raise VolatilityCalibrationError("fewer than 20 same-contract history bars")
        recent = np.asarray(
            [_garman_klass_variance(row) for _, row in history.tail(20).iterrows()],
            dtype=float,
        )
        target_rv = _garman_klass_variance(pd.Series(target._asdict()))
        rows.append(
            {
                "prediction_time": prediction_time,
                "trade_date": trade_date,
                "contract_id": contract_id,
                "target_trade_date": target_trade_date,
                "target_available_at": target_available,
                "target_rv": target_rv,
                "baseline_rv20": float(recent.mean()),
                "log_rv_d1": math.log(max(float(recent[-1]), EPSILON)),
                "log_rv_w5": math.log(max(float(recent[-5:].mean()), EPSILON)),
                "log_rv_m20": math.log(max(float(recent.mean()), EPSILON)),
            }
        )
    result = pd.DataFrame(rows).sort_values("prediction_time").reset_index(drop=True)
    return result


def _require_role_identity(candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = candidates.loc[candidates.prediction_time.between(TRAIN_START, TRAIN_END)].copy()
    calibration = candidates.loc[
        candidates.prediction_time.between(CALIBRATION_START, CALIBRATION_END)
    ].copy()
    if len(train) != 252 or len(calibration) != 720:
        raise VolatilityCalibrationError(
            f"frozen role row counts drifted: train={len(train)}, calibration={len(calibration)}"
        )
    if _identity_sha(train) != TRAIN_IDENTITY_SHA256:
        raise VolatilityCalibrationError("252-row training identity drifted")
    if _identity_sha(calibration) != CALIBRATION_IDENTITY_SHA256:
        raise VolatilityCalibrationError("720-row calibration identity drifted")
    combined = pd.concat([train, calibration], ignore_index=True)
    if not combined.prediction_time.is_monotonic_increasing:
        raise VolatilityCalibrationError("calibration candidate order drifted")
    return combined, calibration


def _walk_forward_losses(candidates: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    baseline_losses: list[float] = []
    paired_losses: list[float] = []
    coefficients: np.ndarray | None = None
    for position in range(252, len(candidates)):
        current = candidates.iloc[position]
        current_time = pd.Timestamp(current.prediction_time)
        if coefficients is None or (position - 252) % 5 == 0:
            prior = candidates.iloc[:position]
            training = prior.loc[prior.target_available_at <= current_time]
            if len(training) != position:
                raise VolatilityCalibrationError("training-label PIT gate failed")
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

def _centered_block_sd(values: np.ndarray, block_size: int) -> float:
    centered = np.asarray(values, dtype=float) - float(np.mean(values))
    if len(centered) < block_size:
        raise VolatilityCalibrationError("block size exceeds calibration rows")
    means = np.asarray(
        [centered[index : index + block_size].mean() for index in range(len(centered) - block_size + 1)],
        dtype=float,
    )
    return float(np.std(means, ddof=1))


def _relative_mde(block_size: int, block_sd: float, baseline_scale: float) -> float:
    absolute = (Z_ALPHA_OVER_2 + Z_POWER) * block_sd / math.sqrt(
        PLANNED_ROWS / block_size
    )
    return float(absolute / baseline_scale)


def run_calibration(repo_root: Path, archive_root: Path) -> dict[str, Any]:
    release = validate_calibration_authority(repo_root)
    market = load_calibration_market(archive_root)
    candidates = _candidate_rows(market)
    combined, calibration = _require_role_identity(candidates)
    baseline_losses, paired_losses = _walk_forward_losses(combined)
    if len(baseline_losses) != 720 or len(paired_losses) != 720:
        raise VolatilityCalibrationError("calibration loss row count drifted")
    mean_baseline = float(np.mean(baseline_losses))
    calibration_sd = {
        block: _centered_block_sd(paired_losses, block) for block in (20, 40, 60)
    }
    baseline_scale = min(CONSUMED_BASELINE_QLIKE, mean_baseline)
    relative_mde = {
        block: _relative_mde(
            block,
            max(CONSUMED_BLOCK_SD[block], calibration_sd[block]),
            baseline_scale,
        )
        for block in (20, 40, 60)
    }
    result = {
        "schema_version": 1,
        "calibration_id": "volatility-203-nuisance-v1",
        "issue": 203,
        "release_id": release["release_id"],
        "release_sha256": RELEASE_SHA256,
        "train_identity_sha256": TRAIN_IDENTITY_SHA256,
        "calibration_identity_sha256": CALIBRATION_IDENTITY_SHA256,
        "calibration_rows": len(calibration),
        "mean_baseline_qlike": mean_baseline,
        "centered_paired_loss_block_sd_20": calibration_sd[20],
        "centered_paired_loss_block_sd_40": calibration_sd[40],
        "centered_paired_loss_block_sd_60": calibration_sd[60],
        "relative_mde_at_1800": {
            "20_sessions": relative_mde[20],
            "40_sessions": relative_mde[40],
            "60_sessions": relative_mde[60],
        },
        "power_gate_pass": bool(all(value <= 0.05 for value in relative_mde.values())),
        "protected_1800_performance_inspected": False,
        "existing_504_future_rows_inspected": False,
    }
    return result


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
