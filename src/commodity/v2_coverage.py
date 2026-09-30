from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ISSUE448_PREREG_SHA256 = "4ea610d1f0b42e8cf8d77efd787d0a8a45d4bb2744318c2ba43be2a40c5239d7"
ISSUE448_SOURCE_FEASIBILITY_SHA256 = "c7bace7e8fc49116b45cfde6d1aa4df3bf0a6fec3375177a9d80362c08f286b9"
ISSUE448_DEVELOPMENT_CUTOFF = pd.Timestamp("2022-12-31", tz="UTC")


class Issue448CoverageError(ValueError):
    """Raised when the #448 coverage contract or evidence boundary is violated."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Issue448Contract:
    prereg: Mapping[str, Any]
    source_feasibility: Mapping[str, Any]
    prereg_sha256: str
    source_feasibility_sha256: str
    latest_allowed_trade_date: str
    protected_confirmation_accessed: bool


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Issue448CoverageError(f"invalid issue-448 authority file: {path}") from exc
    if not isinstance(payload, dict):
        raise Issue448CoverageError("issue-448 authority payload must be an object")
    return payload


def _validate_prereg(payload: Mapping[str, Any]) -> str:
    if payload.get("schema_version") != 1 or payload.get("issue") != 448:
        raise Issue448CoverageError("unsupported issue-448 preregistration")
    if payload.get("status") != "preregistered_before_issue448_empirical_scoring":
        raise Issue448CoverageError("issue-448 preregistration status is invalid")
    if payload.get("evidence_class") != "development":
        raise Issue448CoverageError("issue-448 preregistration must use development evidence")
    if payload.get("protected_confirmation_accessed") is not False:
        raise Issue448CoverageError("issue-448 preregistration crossed protected evidence")
    cutoff_text = str(payload.get("latest_allowed_trade_date", ""))
    try:
        cutoff = pd.Timestamp(cutoff_text, tz="UTC")
    except (TypeError, ValueError) as exc:
        raise Issue448CoverageError("issue-448 cutoff is invalid") from exc
    if cutoff > ISSUE448_DEVELOPMENT_CUTOFF:
        raise Issue448CoverageError("issue-448 cutoff crosses protected evidence")
    return cutoff_text


def _validate_source_feasibility(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != 1 or payload.get("issue") != 448:
        raise Issue448CoverageError("unsupported issue-448 source feasibility")
    if payload.get("status") != "registered_before_issue448_empirical_scoring":
        raise Issue448CoverageError("issue-448 source feasibility status is invalid")
    if payload.get("protected_confirmation_accessed") is not False:
        raise Issue448CoverageError("issue-448 source feasibility crossed protected evidence")
    if payload.get("preregistration_ref", {}).get("sha256") != ISSUE448_PREREG_SHA256:
        raise Issue448CoverageError("issue-448 source feasibility preregistration binding is invalid")


def load_issue448_contract(
    prereg_path: Path,
    source_feasibility_path: Path,
) -> Issue448Contract:
    prereg = _load_json(Path(prereg_path))
    source = _load_json(Path(source_feasibility_path))
    cutoff = _validate_prereg(prereg)
    _validate_source_feasibility(source)
    prereg_sha = _sha256_file(Path(prereg_path))
    source_sha = _sha256_file(Path(source_feasibility_path))
    if prereg_sha != ISSUE448_PREREG_SHA256:
        raise Issue448CoverageError("issue-448 preregistration SHA-256 does not match authority")
    if source_sha != ISSUE448_SOURCE_FEASIBILITY_SHA256:
        raise Issue448CoverageError("issue-448 source-feasibility SHA-256 does not match authority")
    return Issue448Contract(
        prereg=prereg,
        source_feasibility=source,
        prereg_sha256=prereg_sha,
        source_feasibility_sha256=source_sha,
        latest_allowed_trade_date=cutoff,
        protected_confirmation_accessed=False,
    )


def _pairs(values: object) -> tuple[tuple[int, ...], ...]:
    if not isinstance(values, list):
        raise Issue448CoverageError("issue-448 candidate pairs are invalid")
    return tuple(tuple(int(item) for item in row) for row in values)


def _ints(values: object) -> tuple[int, ...]:
    if not isinstance(values, list):
        raise Issue448CoverageError("issue-448 candidate windows are invalid")
    return tuple(int(value) for value in values)


def issue448_family_registry(contract: Issue448Contract) -> dict[str, dict[str, object]]:
    technical = contract.prereg.get("technical_analysis")
    market_structure = contract.prereg.get("market_structure")
    if not isinstance(technical, Mapping) or not isinstance(market_structure, Mapping):
        raise Issue448CoverageError("issue-448 preregistration lacks family definitions")
    trend = technical["trend_momentum"]
    oscillator = technical["oscillator_mean_reversion"]
    breakout = technical["range_breakout"]
    envelope = technical["volatility_envelope"]
    strength = technical["trend_strength"]
    volume = technical["volume_confirmation"]
    return {
        "ta.trend_momentum": {
            "ema_pairs": _pairs(trend["ema_pairs"]),
            "macd_style": _pairs(trend["macd_style"]),
            "sma_gap_pairs": _pairs(trend["sma_gap_pairs"]),
            "primitive_controls": ("feature_ret_1", "feature_ret_5", "feature_ret_20", "feature_ma_gap_5", "feature_ma_gap_20"),
        },
        "ta.oscillator_mean_reversion": {
            "rsi_windows": _ints(oscillator["rsi_windows"]),
            "price_zscore_windows": _ints(oscillator["price_zscore_windows"]),
            "primitive_controls": ("feature_ret_1", "feature_ret_5", "feature_ret_20"),
        },
        "ta.range_breakout": {
            "donchian_windows": _ints(breakout["donchian_windows"]),
            "normalized_range_windows": _ints(breakout["normalized_range_windows"]),
            "alias_policy": "shared_normalized_range_family",
            "primitive_controls": ("feature_range_pct", "feature_ret_1"),
        },
        "ta.volatility_envelope": {
            "atr_windows": _ints(envelope["atr_windows"]),
            "bollinger_windows": _ints(envelope["bollinger_windows"]),
            "primitive_controls": ("feature_vol_5", "feature_vol_20", "feature_range_pct"),
        },
        "ta.trend_strength": {
            "adx_windows": _ints(strength["adx_windows"]),
            "directional_movement_spread": bool(strength["directional_movement_spread"]),
            "primitive_controls": ("feature_range_pct", "feature_ret_1"),
        },
        "ta.volume_confirmation": {
            "volume_zscore_windows": _ints(volume["volume_zscore_windows"]),
            "directional_volume_window": int(volume["directional_volume_window"]),
            "primitive_controls": ("feature_ret_1",),
        },
        "market_structure.carry_basis": {
            "representations": tuple(map(str, market_structure["carry_basis"])),
            "basis_momentum_sessions": _ints(market_structure["basis_momentum_sessions"]),
        },
        "market_structure.curve": {
            "representations": tuple(map(str, market_structure["curve"])),
        },
        "market_structure.open_interest": {
            "representations": tuple(map(str, market_structure["open_interest"])),
        },
        "market_structure.positioning": {
            "representations": tuple(map(str, market_structure["positioning"])),
        },
    }


def issue448_source_dispositions(contract: Issue448Contract) -> dict[str, str]:
    gates = contract.source_feasibility.get("gates")
    if not isinstance(gates, Mapping):
        raise Issue448CoverageError("issue-448 source feasibility lacks gates")
    return {
        str(name): str(item.get("disposition"))
        for name, item in gates.items()
        if isinstance(item, Mapping)
    }


def issue448_family_outer_blocks(
    contract: Issue448Contract,
) -> dict[str, tuple[dict[str, object], ...]]:
    """Return preregistered family-specific outer blocks without inventing coverage."""
    market_structure = contract.prereg.get("market_structure")
    if not isinstance(market_structure, Mapping):
        raise Issue448CoverageError("issue-448 preregistration lacks market structure")
    lane = market_structure.get("open_interest_evaluation_lane")
    if not isinstance(lane, Mapping):
        raise Issue448CoverageError("issue-448 preregistration lacks OI evaluation lane")
    raw_blocks = lane.get("outer_blocks")
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise Issue448CoverageError("issue-448 OI evaluation lane lacks outer blocks")

    cutoff = pd.Timestamp(contract.latest_allowed_trade_date, tz="UTC")
    normalized: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    previous_end: pd.Timestamp | None = None
    for raw in raw_blocks:
        if not isinstance(raw, Mapping):
            raise Issue448CoverageError("issue-448 OI outer block is invalid")
        block_id = str(raw.get("id", "")).strip()
        parent_id = str(raw.get("parent_control_outer_id", "")).strip()
        selection_ids = raw.get("selection_inner_block_ids")
        if not block_id or not parent_id:
            raise Issue448CoverageError("issue-448 OI outer block identity is invalid")
        if block_id in seen_ids:
            raise Issue448CoverageError("issue-448 OI outer block identity is duplicated")
        if not isinstance(selection_ids, list) or not selection_ids:
            raise Issue448CoverageError("issue-448 OI outer block lacks selection blocks")
        normalized_selection_ids = [str(value) for value in selection_ids]
        if len(normalized_selection_ids) != len(set(normalized_selection_ids)):
            raise Issue448CoverageError("issue-448 OI selection block identity is duplicated")
        try:
            start = pd.Timestamp(str(raw["start"]), tz="UTC")
            end = pd.Timestamp(str(raw["end"]), tz="UTC")
        except (KeyError, TypeError, ValueError) as exc:
            raise Issue448CoverageError("issue-448 OI outer block dates are invalid") from exc
        if start > end or end > cutoff:
            raise Issue448CoverageError("issue-448 OI outer block crosses development boundary")
        if previous_end is not None and start <= previous_end:
            raise Issue448CoverageError("issue-448 OI outer blocks overlap or are unordered")
        normalized.append(
            {
                "id": block_id,
                "start": str(raw["start"]),
                "end": str(raw["end"]),
                "parent_control_outer_id": parent_id,
                "selection_inner_block_ids": normalized_selection_ids,
            }
        )
        seen_ids.add(block_id)
        previous_end = end

    feasibility = contract.source_feasibility.get("open_interest_nested_coverage_feasibility")
    if not isinstance(feasibility, Mapping):
        raise Issue448CoverageError("issue-448 source feasibility lacks OI nested coverage")
    aligned = feasibility.get("availability_aligned_2020")
    first = normalized[0]
    if (
        not isinstance(aligned, Mapping)
        or first["id"] != "outer-2020-oi"
        or aligned.get("all_four_representations_supported") is not True
        or str(aligned.get("parent_control_outer_id", "")) != first["parent_control_outer_id"]
        or str(aligned.get("selection_inner_block_id", ""))
        not in first["selection_inner_block_ids"]
    ):
        raise Issue448CoverageError("issue-448 OI availability-aligned feasibility is inconsistent")

    return {"market_structure.open_interest": tuple(normalized)}


def _validated_market_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"trade_date", "available_at", "settle", "high", "low", "close", "volume"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise Issue448CoverageError(f"issue-448 technical frame lacks columns: {missing}")
    out = frame.loc[:, sorted(required)].copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], utc=True, errors="raise")
    out["available_at"] = pd.to_datetime(out["available_at"], utc=True, errors="raise")
    if not out["trade_date"].is_monotonic_increasing or not out["available_at"].is_monotonic_increasing:
        raise Issue448CoverageError("issue-448 technical frame must be chronological")
    if out["trade_date"].duplicated().any() or out["available_at"].duplicated().any():
        raise Issue448CoverageError("issue-448 availability/trade timestamps must be unique")
    if out["available_at"].lt(out["trade_date"]).any():
        raise Issue448CoverageError("issue-448 availability precedes trade date")
    if len(out) and out["trade_date"].max() > ISSUE448_DEVELOPMENT_CUTOFF:
        raise Issue448CoverageError("issue-448 technical frame crosses protected cutoff")
    for column in ("settle", "high", "low", "close", "volume"):
        out[column] = pd.to_numeric(out[column], errors="raise").astype(float)
    if not np.isfinite(out[["settle", "high", "low", "close", "volume"]].to_numpy()).all():
        raise Issue448CoverageError("issue-448 technical values must be finite")
    return out


def _rolling_zscore(values: pd.Series, window: int) -> pd.Series:
    history = values.rolling(window=window, min_periods=window)
    spread = history.std(ddof=0).replace(0.0, np.nan)
    return (values - history.mean()) / spread


def _true_range(frame: pd.DataFrame) -> pd.Series:
    previous_close = frame["close"].shift(1)
    parts = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    return parts.max(axis=1)


def _directional_movement(frame: pd.DataFrame, window: int) -> tuple[pd.Series, pd.Series]:
    up = frame["high"].diff()
    down = -frame["low"].diff()
    plus_dm = up.where((up > down) & (up > 0.0), 0.0)
    minus_dm = down.where((down > up) & (down > 0.0), 0.0)
    true_range = _true_range(frame)
    tr_sum = true_range.rolling(window, min_periods=window).sum().replace(0.0, np.nan)
    plus_di = 100.0 * plus_dm.rolling(window, min_periods=window).sum() / tr_sum
    minus_di = 100.0 * minus_dm.rolling(window, min_periods=window).sum() / tr_sum
    di_sum = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    adx = dx.rolling(window, min_periods=window).mean()
    return adx, plus_di - minus_di


def build_issue448_technical_features(
    market: pd.DataFrame,
    contract: Issue448Contract,
) -> tuple[pd.DataFrame, dict[str, tuple[str, ...]]]:
    frame = _validated_market_frame(market)
    registry = issue448_family_registry(contract)
    out = frame[["trade_date", "available_at"]].copy()
    settle = frame["settle"]
    close = frame["close"]
    families: dict[str, list[str]] = {
        name: [] for name in registry if name.startswith("ta.")
    }

    trend = registry["ta.trend_momentum"]
    for fast, slow in trend["ema_pairs"]:
        fast_ema = settle.ewm(span=fast, adjust=False, min_periods=fast).mean()
        slow_ema = settle.ewm(span=slow, adjust=False, min_periods=slow).mean()
        name = f"feature_issue448_ema_gap_{fast}_{slow}"
        out[name] = fast_ema / slow_ema - 1.0
        families["ta.trend_momentum"].append(name)
    for fast, slow in trend["sma_gap_pairs"]:
        fast_ma = settle.rolling(fast, min_periods=fast).mean()
        slow_ma = settle.rolling(slow, min_periods=slow).mean()
        name = f"feature_issue448_sma_gap_{fast}_{slow}"
        out[name] = fast_ma / slow_ma - 1.0
        families["ta.trend_momentum"].append(name)
    for fast, slow, signal in trend["macd_style"]:
        fast_ema = settle.ewm(span=fast, adjust=False, min_periods=fast).mean()
        slow_ema = settle.ewm(span=slow, adjust=False, min_periods=slow).mean()
        macd = fast_ema - slow_ema
        signal_line = macd.ewm(span=signal, adjust=False, min_periods=signal).mean()
        name = f"feature_issue448_macd_{fast}_{slow}_{signal}"
        out[name] = (macd - signal_line) / settle
        families["ta.trend_momentum"].append(name)

    oscillator = registry["ta.oscillator_mean_reversion"]
    delta = settle.diff()
    gains = delta.clip(lower=0.0)
    losses = (-delta.clip(upper=0.0))
    for window in oscillator["rsi_windows"]:
        avg_gain = gains.rolling(window, min_periods=window).mean()
        avg_loss = losses.rolling(window, min_periods=window).mean()
        rs = avg_gain / avg_loss.replace(0.0, np.nan)
        rsi = 100.0 - 100.0 / (1.0 + rs)
        rsi = rsi.where(avg_loss.ne(0.0), 100.0)
        name = f"feature_issue448_rsi_{window}"
        out[name] = rsi
        families["ta.oscillator_mean_reversion"].append(name)
    for window in oscillator["price_zscore_windows"]:
        name = f"feature_issue448_price_zscore_{window}"
        out[name] = _rolling_zscore(settle, window)
        families["ta.oscillator_mean_reversion"].append(name)

    breakout = registry["ta.range_breakout"]
    for window in breakout["donchian_windows"]:
        lower = frame["low"].rolling(window, min_periods=window).min()
        upper = frame["high"].rolling(window, min_periods=window).max()
        name = f"feature_issue448_donchian_position_{window}"
        out[name] = (close - lower) / (upper - lower).replace(0.0, np.nan)
        families["ta.range_breakout"].append(name)
    for window in breakout["normalized_range_windows"]:
        lower = frame["low"].rolling(window, min_periods=window).min()
        upper = frame["high"].rolling(window, min_periods=window).max()
        name = f"feature_issue448_normalized_range_{window}"
        out[name] = (close - lower) / (upper - lower).replace(0.0, np.nan)
        families["ta.range_breakout"].append(name)

    envelope = registry["ta.volatility_envelope"]
    true_range = _true_range(frame)
    for window in envelope["atr_windows"]:
        name = f"feature_issue448_atr_{window}"
        out[name] = true_range.rolling(window, min_periods=window).mean()
        families["ta.volatility_envelope"].append(name)
    for window in envelope["bollinger_windows"]:
        mean = settle.rolling(window, min_periods=window).mean()
        std = settle.rolling(window, min_periods=window).std(ddof=0).replace(0.0, np.nan)
        name = f"feature_issue448_bollinger_position_{window}"
        out[name] = (settle - mean) / (2.0 * std)
        families["ta.volatility_envelope"].append(name)

    strength = registry["ta.trend_strength"]
    for window in strength["adx_windows"]:
        adx, dm_spread = _directional_movement(frame, window)
        adx_name = f"feature_issue448_adx_{window}"
        dm_name = f"feature_issue448_dm_spread_{window}"
        out[adx_name] = adx
        out[dm_name] = dm_spread
        families["ta.trend_strength"].extend([adx_name, dm_name])

    volume = registry["ta.volume_confirmation"]
    for window in volume["volume_zscore_windows"]:
        name = f"feature_issue448_volume_zscore_{window}"
        out[name] = _rolling_zscore(frame["volume"], window)
        families["ta.volume_confirmation"].append(name)
    window = int(volume["directional_volume_window"])
    signed = np.sign(settle.diff()).fillna(0.0) * frame["volume"]
    name = f"feature_issue448_directional_volume_{window}"
    denominator = frame["volume"].rolling(window, min_periods=window).sum().replace(0.0, np.nan)
    out[name] = signed.rolling(window, min_periods=window).sum() / denominator
    families["ta.volume_confirmation"].append(name)

    return out, {name: tuple(columns) for name, columns in families.items()}


def _validate_curve_frame(curve: pd.DataFrame) -> pd.DataFrame:
    required = {
        "trade_date", "available_at", "log_settle_m1", "log_settle_m2",
        "log_settle_m3", "log_settle_m4", "dte_m1", "dte_m2", "dte_m4", "volume_m1",
    }
    missing = sorted(required - set(curve.columns))
    if missing:
        raise Issue448CoverageError(f"issue-448 curve frame lacks columns: {missing}")
    out = curve.loc[:, sorted(required)].copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], utc=True, errors="raise")
    out["available_at"] = pd.to_datetime(out["available_at"], utc=True, errors="raise")
    if not out["trade_date"].is_monotonic_increasing or not out["available_at"].is_monotonic_increasing:
        raise Issue448CoverageError("issue-448 curve frame must be chronological")
    if out["trade_date"].duplicated().any() or out["available_at"].duplicated().any():
        raise Issue448CoverageError("issue-448 curve availability must be unique")
    if len(out) and out["trade_date"].max() > ISSUE448_DEVELOPMENT_CUTOFF:
        raise Issue448CoverageError("issue-448 curve frame crosses protected cutoff")
    numeric = sorted(required - {"trade_date", "available_at"})
    for column in numeric:
        out[column] = pd.to_numeric(out[column], errors="raise").astype(float)
    if not np.isfinite(out[numeric].to_numpy()).all():
        raise Issue448CoverageError("issue-448 curve values must be finite")
    if (out["dte_m2"] <= out["dte_m1"]).any() or (out["dte_m4"] <= out["dte_m1"]).any():
        raise Issue448CoverageError("issue-448 curve DTE ordering is invalid")
    return out


def validate_issue448_selected_contract_ohlcv(
    selected_path: pd.DataFrame,
    bars: pd.DataFrame,
) -> pd.DataFrame:
    """Require exactly one OHLCV row for every frozen selected-contract origin."""
    key = ["trade_date", "contract_id"]
    required_bars = {*key, "high", "low", "close", "volume"}
    missing_path = sorted(set(key) - set(selected_path.columns))
    missing_bars = sorted(required_bars - set(bars.columns))
    if missing_path:
        raise Issue448CoverageError(f"issue-448 selected contract path lacks columns: {missing_path}")
    if missing_bars:
        raise Issue448CoverageError(f"issue-448 OHLCV frame lacks columns: {missing_bars}")

    path = selected_path.loc[:, key].copy()
    path["trade_date"] = pd.to_datetime(path["trade_date"], utc=True, errors="raise")
    path["contract_id"] = path["contract_id"].astype("string").str.strip()
    if path.duplicated(key).any():
        raise Issue448CoverageError("issue-448 selected contract path is not unique")
    if len(path) and path["trade_date"].max() > ISSUE448_DEVELOPMENT_CUTOFF:
        raise Issue448CoverageError("issue-448 selected contract OHLCV crosses protected cutoff")

    source = bars.loc[:, [*key, "high", "low", "close", "volume"]].copy()
    source["trade_date"] = pd.to_datetime(source["trade_date"], utc=True, errors="raise")
    source["contract_id"] = source["contract_id"].astype("string").str.strip()
    selected_source = source.merge(path, on=key, how="inner", validate="many_to_one")
    if selected_source.duplicated(key).any():
        raise Issue448CoverageError("issue-448 duplicate selected-contract OHLCV rows")
    selected = path.merge(source, on=key, how="left", validate="one_to_one", indicator=True)
    if selected["_merge"].ne("both").any():
        raise Issue448CoverageError("issue-448 missing selected-contract OHLCV rows")
    for column in ("high", "low", "close", "volume"):
        selected[column] = pd.to_numeric(selected[column], errors="raise").astype(float)
    if not np.isfinite(selected[["high", "low", "close", "volume"]].to_numpy()).all():
        raise Issue448CoverageError("issue-448 selected-contract OHLCV values must be finite")
    return selected.drop(columns="_merge")


def match_issue448_open_interest_to_contract_path(
    decisions: pd.DataFrame,
    open_interest: pd.DataFrame,
) -> pd.DataFrame:
    """Backward-join PIT OI publications to the frozen selected-contract path."""
    decision_required = {"trade_date", "available_at", "contract_id"}
    oi_required = {"contract_id", "observed_for", "available_at", "open_interest"}
    missing_decisions = sorted(decision_required - set(decisions.columns))
    missing_oi = sorted(oi_required - set(open_interest.columns))
    if missing_decisions:
        raise Issue448CoverageError(
            f"issue-448 OI contract path lacks columns: {missing_decisions}"
        )
    if missing_oi:
        raise Issue448CoverageError(
            f"issue-448 OI publication stream lacks columns: {missing_oi}"
        )

    left = decisions.loc[:, ["trade_date", "available_at", "contract_id"]].copy()
    left["_row_order"] = np.arange(len(left))
    left["trade_date"] = pd.to_datetime(left["trade_date"], utc=True, errors="raise")
    left["available_at"] = pd.to_datetime(left["available_at"], utc=True, errors="raise")
    left["contract_id"] = left["contract_id"].astype("string").str.strip()
    if left["trade_date"].duplicated().any() or left["available_at"].duplicated().any():
        raise Issue448CoverageError("issue-448 OI decision path must be unique")
    if left["contract_id"].isna().any() or left["contract_id"].eq("").any():
        raise Issue448CoverageError("issue-448 OI decision contract identity is invalid")
    if len(left) and left["trade_date"].max() > ISSUE448_DEVELOPMENT_CUTOFF:
        raise Issue448CoverageError("issue-448 OI decision path crosses protected cutoff")

    right = open_interest.loc[:, list(oi_required)].copy()
    right["contract_id"] = right["contract_id"].astype("string").str.strip()
    right["observed_for"] = pd.to_datetime(right["observed_for"], utc=True, errors="raise")
    right["available_at"] = pd.to_datetime(right["available_at"], utc=True, errors="raise")
    right["open_interest"] = pd.to_numeric(right["open_interest"], errors="raise").astype(float)
    if right["open_interest"].lt(0.0).any():
        raise Issue448CoverageError("issue-448 OI publications must be nonnegative")
    if right.duplicated(["contract_id", "observed_for", "available_at"]).any():
        raise Issue448CoverageError("issue-448 OI publication identity is not unique")

    rows: list[pd.DataFrame] = []
    for contract_id, decision_group in left.groupby("contract_id", sort=False):
        publications = right.loc[right["contract_id"].eq(contract_id)].copy()
        if publications.empty:
            matched = decision_group.copy()
            matched["observed_for"] = pd.NaT
            matched["source_available_at"] = pd.NaT
            matched["open_interest_m1"] = np.nan
        else:
            publications = publications.rename(
                columns={
                    "available_at": "source_available_at",
                    "open_interest": "open_interest_m1",
                }
            ).sort_values(["observed_for", "source_available_at"], kind="stable")
            matched = decision_group.copy()
            matched["observed_for"] = pd.Series(
                pd.NaT, index=matched.index, dtype="datetime64[ns, UTC]"
            )
            matched["source_available_at"] = pd.Series(
                pd.NaT, index=matched.index, dtype="datetime64[ns, UTC]"
            )
            matched["open_interest_m1"] = np.nan
            for row_index, decision in matched.iterrows():
                eligible = publications.loc[
                    publications["observed_for"].le(decision["trade_date"])
                    & publications["source_available_at"].le(decision["available_at"])
                ]
                if eligible.empty:
                    continue
                selected = eligible.iloc[-1]
                matched.at[row_index, "observed_for"] = selected["observed_for"]
                matched.at[row_index, "source_available_at"] = selected[
                    "source_available_at"
                ]
                matched.at[row_index, "open_interest_m1"] = selected["open_interest_m1"]
        rows.append(matched)
    if not rows:
        return pd.DataFrame(
            columns=[
                "trade_date", "available_at", "contract_id", "source_available_at",
                "ts_ref", "open_interest_m1",
            ]
        )
    out = pd.concat(rows, ignore_index=True).sort_values("_row_order", kind="stable")
    invalid_reference = out["observed_for"].notna() & out["observed_for"].gt(out["trade_date"])
    if invalid_reference.any():
        raise Issue448CoverageError("issue-448 OI reference time exceeds trade date")
    invalid_publication = out["source_available_at"].notna() & out["source_available_at"].gt(
        out["available_at"]
    )
    if invalid_publication.any():
        raise Issue448CoverageError("issue-448 OI publication exceeds decision time")
    return out.rename(columns={"observed_for": "ts_ref"})[
        [
            "trade_date", "available_at", "contract_id", "source_available_at",
            "ts_ref", "open_interest_m1",
        ]
    ].reset_index(drop=True)


def _validate_oi_frame(open_interest: pd.DataFrame) -> pd.DataFrame:
    required = {"available_at", "ts_ref", "open_interest_m1"}
    missing = sorted(required - set(open_interest.columns))
    if missing:
        raise Issue448CoverageError(f"issue-448 open-interest frame lacks columns: {missing}")
    optional = {"trade_date", "source_available_at", "contract_id"}
    columns = sorted(required | (optional & set(open_interest.columns)))
    out = open_interest.loc[:, columns].copy()
    out["available_at"] = pd.to_datetime(out["available_at"], utc=True, errors="coerce")
    out["ts_ref"] = pd.to_datetime(out["ts_ref"], utc=True, errors="coerce")
    if out["available_at"].isna().any():
        raise Issue448CoverageError("issue-448 open-interest availability is ambiguous")
    if not out["available_at"].is_monotonic_increasing or out["available_at"].duplicated().any():
        raise Issue448CoverageError("issue-448 open-interest availability must be chronological and unique")
    out["open_interest_m1"] = pd.to_numeric(out["open_interest_m1"], errors="coerce").astype(float)
    missing_value = out["open_interest_m1"].isna()
    if (out["ts_ref"].isna() != missing_value).any():
        raise Issue448CoverageError("issue-448 open-interest reference/value missingness is inconsistent")
    if out.loc[~missing_value, "open_interest_m1"].lt(0.0).any():
        raise Issue448CoverageError("issue-448 open interest must be nonnegative")
    if "trade_date" in out:
        out["trade_date"] = pd.to_datetime(out["trade_date"], utc=True, errors="coerce")
        if out["trade_date"].isna().any() or out["trade_date"].duplicated().any():
            raise Issue448CoverageError("issue-448 aligned open-interest trade date is invalid")
        if len(out) and out["trade_date"].max() > ISSUE448_DEVELOPMENT_CUTOFF:
            raise Issue448CoverageError("issue-448 aligned open-interest crosses protected cutoff")
        if (out.loc[~missing_value, "ts_ref"] > out.loc[~missing_value, "trade_date"]).any():
            raise Issue448CoverageError("issue-448 open-interest reference time exceeds trade date")
    if "source_available_at" in out:
        out["source_available_at"] = pd.to_datetime(
            out["source_available_at"], utc=True, errors="coerce"
        )
        if (out.loc[~missing_value, "source_available_at"].isna()).any():
            raise Issue448CoverageError("issue-448 open-interest source availability is ambiguous")
        if (out.loc[~missing_value, "source_available_at"] > out.loc[~missing_value, "available_at"]).any():
            raise Issue448CoverageError("issue-448 open-interest publication exceeds decision time")
    return out


def _validate_positioning_frame(positioning: pd.DataFrame) -> pd.DataFrame:
    required = {"available_at", "open_interest", "managed_money_net", "producer_merchant_net"}
    missing = sorted(required - set(positioning.columns))
    if missing:
        raise Issue448CoverageError(f"issue-448 positioning frame lacks columns: {missing}")
    out = positioning.loc[:, sorted(required)].copy()
    out["available_at"] = pd.to_datetime(out["available_at"], utc=True, errors="coerce")
    if out["available_at"].isna().any():
        raise Issue448CoverageError("issue-448 positioning availability is ambiguous")
    if not out["available_at"].is_monotonic_increasing or out["available_at"].duplicated().any():
        raise Issue448CoverageError("issue-448 positioning availability must be chronological and unique")
    for column in ("open_interest", "managed_money_net", "producer_merchant_net"):
        out[column] = pd.to_numeric(out[column], errors="raise").astype(float)
    if out["open_interest"].le(0.0).any():
        raise Issue448CoverageError("issue-448 positioning open interest must be positive")
    return out


def _asof_join(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    return pd.merge_asof(
        left.sort_values("available_at", kind="stable"),
        right.sort_values("available_at", kind="stable"),
        on="available_at",
        direction="backward",
        allow_exact_matches=True,
    )


def build_issue448_market_structure_features(
    curve: pd.DataFrame,
    open_interest: pd.DataFrame,
    positioning: pd.DataFrame,
    contract: Issue448Contract,
) -> tuple[pd.DataFrame, dict[str, tuple[str, ...]]]:
    curve_frame = _validate_curve_frame(curve)
    oi_frame = _validate_oi_frame(open_interest)
    positioning_frame = _validate_positioning_frame(positioning)
    registry = issue448_family_registry(contract)
    out = curve_frame[["trade_date", "available_at"]].copy()
    families: dict[str, list[str]] = {
        name: [] for name in registry if name.startswith("market_structure.")
    }

    basis12 = 365.0 * (
        curve_frame["log_settle_m2"] - curve_frame["log_settle_m1"]
    ) / (curve_frame["dte_m2"] - curve_frame["dte_m1"])
    basis14 = 365.0 * (
        curve_frame["log_settle_m4"] - curve_frame["log_settle_m1"]
    ) / (curve_frame["dte_m4"] - curve_frame["dte_m1"])
    basis_names = (
        ("feature_issue448_dte_normalized_m1_m2_log_basis", basis12),
        ("feature_issue448_dte_normalized_m1_m4_log_basis", basis14),
    )
    for name, values in basis_names:
        out[name] = values
        families["market_structure.carry_basis"].append(name)
    for lag in registry["market_structure.carry_basis"]["basis_momentum_sessions"]:
        for label, values in (("m1_m2", basis12), ("m1_m4", basis14)):
            name = f"feature_issue448_{label}_basis_momentum_{lag}"
            out[name] = values.diff(int(lag))
            families["market_structure.carry_basis"].append(name)

    curvature = (
        curve_frame["log_settle_m1"]
        - 2.0 * curve_frame["log_settle_m2"]
        + curve_frame["log_settle_m3"]
    )
    spread12 = curve_frame["log_settle_m1"] - curve_frame["log_settle_m2"]
    slope14 = (curve_frame["log_settle_m1"] - curve_frame["log_settle_m4"]) / 3.0
    curve_features = {
        "feature_issue448_curvature_123": curvature,
        "feature_issue448_m1_m2_change_1": spread12.diff(1),
        "feature_issue448_m1_m4_slope_change_1": slope14.diff(1),
    }
    for name, values in curve_features.items():
        out[name] = values
        families["market_structure.curve"].append(name)

    if "trade_date" in oi_frame:
        joined_oi = out[["trade_date", "available_at"]].merge(
            oi_frame[["trade_date", "open_interest_m1"]],
            on="trade_date",
            how="left",
            validate="one_to_one",
        )
    else:
        joined_oi = _asof_join(
            out[["trade_date", "available_at"]],
            oi_frame[["available_at", "open_interest_m1"]],
        )
    positive_oi = joined_oi["open_interest_m1"].where(
        joined_oi["open_interest_m1"].gt(0.0)
    )
    log_oi = np.log(positive_oi)
    oi_features = {
        "feature_issue448_log_oi_m1": log_oi,
        "feature_issue448_oi_change_1": log_oi.diff(1),
        "feature_issue448_oi_change_5": log_oi.diff(5),
        "feature_issue448_volume_to_oi_m1": curve_frame["volume_m1"] / positive_oi,
    }
    for name, values in oi_features.items():
        out[name] = values.to_numpy()
        families["market_structure.open_interest"].append(name)

    report = positioning_frame.copy()
    report["managed_money_net_pct_oi"] = report["managed_money_net"] / report["open_interest"]
    report["producer_merchant_hedging_pressure"] = -report["producer_merchant_net"] / report["open_interest"]
    report["managed_money_net_pct_oi_change_1report"] = report["managed_money_net_pct_oi"].diff()
    report["producer_merchant_hedging_pressure_change_1report"] = report[
        "producer_merchant_hedging_pressure"
    ].diff()
    position_columns = [
        "managed_money_net_pct_oi",
        "managed_money_net_pct_oi_change_1report",
        "producer_merchant_hedging_pressure",
        "producer_merchant_hedging_pressure_change_1report",
    ]
    joined_positioning = _asof_join(
        out[["trade_date", "available_at"]],
        report[["available_at", *position_columns]],
    )
    for suffix in position_columns:
        name = f"feature_issue448_{suffix}"
        out[name] = joined_positioning[suffix].to_numpy()
        families["market_structure.positioning"].append(name)

    return out, {name: tuple(columns) for name, columns in families.items()}


def prepare_issue448_candidate_features(
    features: pd.DataFrame,
    config: Mapping[str, object],
    candidate_column: str,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Prepare one #448 candidate and its exact #425 primitive-market control.

    The candidate and control are transformed together with the frozen #425
    columnwise transform semantics, then restricted to one identical complete
    row set. This keeps every non-candidate input and every evaluation origin
    matched between the two arms.
    """
    from commodity.v2_optimization import (
        V2OptimizationError,
        _issue425_family_columns,
        _issue425_return_transform,
        _issue425_rolling_scale,
    )

    required = {"trade_date", "available_at", candidate_column}
    missing = sorted(required - set(features.columns))
    if missing:
        raise Issue448CoverageError(f"issue-448 candidate frame lacks columns: {missing}")
    frame = features.copy().sort_values("trade_date", kind="stable")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True, errors="raise")
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True, errors="raise")
    if frame["trade_date"].duplicated().any() or frame["available_at"].duplicated().any():
        raise Issue448CoverageError("issue-448 candidate timestamps must be unique")
    if len(frame) and frame["trade_date"].max() > ISSUE448_DEVELOPMENT_CUTOFF:
        raise Issue448CoverageError("issue-448 candidate frame crosses protected cutoff")

    try:
        _issue425_return_transform(frame, str(config["transforms.return_transform"]))
        control_base = _issue425_family_columns(
            frame, str(config["data.feature_family_subset"])
        )
        numeric_columns = [*control_base, candidate_column]
        numeric = frame[numeric_columns].apply(pd.to_numeric, errors="raise").astype(float)
        lookback = int(config["data.lookback_sessions"])
        lag = int(config["transforms.lag_sessions"])
        stat_window = int(config["transforms.rolling_stat_window_sessions"])
        norm_window = int(config["transforms.normalization_window_sessions"])
        winsor = float(config["transforms.winsor_quantile"])
        if min(lookback, lag, stat_window, norm_window) < 1:
            raise Issue448CoverageError("issue-448 transform windows must be positive")
        if not 0.0 <= winsor < 0.5:
            raise Issue448CoverageError("issue-448 winsor quantile is invalid")
        if winsor > 0.0:
            shifted = numeric.shift(1)
            history = shifted.rolling(window=lookback, min_periods=min(20, lookback))
            numeric = numeric.clip(
                lower=history.quantile(winsor),
                upper=history.quantile(1.0 - winsor),
                axis=1,
            )
        lagged = numeric.shift(lag)
        history = numeric.shift(1).rolling(window=stat_window, min_periods=stat_window)
        derived = pd.concat(
            [
                lagged,
                history.mean().add_suffix(f"__mean{stat_window}"),
                history.std(ddof=0).add_suffix(f"__std{stat_window}"),
            ],
            axis=1,
        )
        scaled = _issue425_rolling_scale(
            derived, str(config["transforms.scaling"]), norm_window
        )
    except (KeyError, ValueError, V2OptimizationError) as exc:
        raise Issue448CoverageError(f"issue-448 candidate transform failed: {exc}") from exc

    candidate_columns = [
        candidate_column,
        f"{candidate_column}__mean{stat_window}",
        f"{candidate_column}__std{stat_window}",
    ]
    control_columns = [column for column in scaled.columns if column not in candidate_columns]
    if not control_columns or set(candidate_columns) & set(control_columns):
        raise Issue448CoverageError("issue-448 matched control identity is invalid")
    output_columns = [*candidate_columns, *control_columns]
    output = pd.concat([frame[["trade_date", "available_at"]], scaled], axis=1)
    output = output.replace([np.inf, -np.inf], np.nan).dropna(subset=output_columns).copy()
    if output.empty:
        raise Issue448CoverageError("issue-448 candidate transform produced no complete rows")
    if not np.isfinite(output[output_columns].to_numpy(dtype=float)).all():
        raise Issue448CoverageError("issue-448 candidate transform is non-finite")
    return output, candidate_columns, control_columns


def issue448_representation_selection_support(
    session_path: pd.DataFrame,
    features: pd.DataFrame,
    *,
    config: Mapping[str, object],
    representations: Sequence[str],
    inner_blocks: Sequence[Mapping[str, str]],
    outer_block: Mapping[str, str],
    phase2_cfg: Mapping[str, Any],
    costs: object,
    minimum_training_rows: int,
) -> dict[str, object]:
    """Resolve PIT-safe representation support before any model scoring."""
    from commodity import v2_optimization as v2
    from commodity.market_only_phase2 import (
        _build_segmented_decision_origins,
        _canonicalize_one_origin_per_fill,
        _path_window,
    )

    outer_start = pd.Timestamp(str(outer_block["start"]), tz="UTC")
    prior_blocks = [
        dict(block)
        for block in inner_blocks
        if pd.Timestamp(str(block["end"]), tz="UTC") < outer_start
    ]
    multiplier = float(phase2_cfg["execution_contract"]["contract_multiplier_mmbtu"])
    round_trip_per_mmbtu = float(costs.round_trip_usd) / multiplier
    block_ids: dict[str, list[str]] = {}
    diagnostics: dict[str, object] = {}
    available: list[str] = []
    held: list[str] = []

    for representation in representations:
        representation = str(representation)
        try:
            prepared, candidate_columns, control_columns = prepare_issue448_candidate_features(
                features, config, representation
            )
            origins, feature_columns = _build_segmented_decision_origins(
                session_path,
                prepared,
                horizon_sessions=int(config["target.horizon_sessions"]),
            )
            if origins.empty:
                raise Issue448CoverageError("issue-448 support reconstruction produced no origins")
            origins, _ = _canonicalize_one_origin_per_fill(origins)
            expected = set(candidate_columns) | set(control_columns)
            if set(feature_columns) != expected:
                raise Issue448CoverageError("issue-448 support feature identity changed")
            origins = v2._attach_issue425_targets(
                origins,
                session_path,
                horizon_sessions=int(config["target.horizon_sessions"]),
                role=str(config["target.target_role"]),
                aggregation=str(config["target.aggregation"]),
                round_trip_per_mmbtu=round_trip_per_mmbtu,
            )
            rows: list[dict[str, object]] = []
            valid_ids: list[str] = []
            for block in prior_blocks:
                _, start_timestamp, boundary_timestamp = _path_window(
                    session_path,
                    start_date=str(block["start"]),
                    end_date=str(block["end"]),
                )
                training = origins.loc[
                    origins["target_end_timestamp"] < start_timestamp
                ].copy()
                training = v2._issue425_training_tail(
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
            _, outer_start_timestamp, outer_boundary_timestamp = _path_window(
                session_path,
                start_date=str(outer_block["start"]),
                end_date=str(outer_block["end"]),
            )
            outer_evaluation = origins.loc[
                origins["fill_timestamp"].ge(outer_start_timestamp)
                & origins["target_end_timestamp"].lt(outer_boundary_timestamp)
            ]
            outer_eligible = not outer_evaluation.empty
            block_ids[representation] = valid_ids
            diagnostics[representation] = {
                "status": "SUPPORTED" if valid_ids and outer_eligible else "PRE_SOURCE_OR_INSUFFICIENT_HISTORY",
                "blocks": rows,
                "outer_evaluation_rows": len(outer_evaluation),
                "outer_eligible": outer_eligible,
            }
            if valid_ids and outer_eligible:
                available.append(representation)
            else:
                held.append(representation)
        except (Issue448CoverageError, v2.V2OptimizationError, KeyError, TypeError, ValueError) as exc:
            block_ids[representation] = []
            diagnostics[representation] = {
                "status": "PREPARATION_FAILED",
                "reason": str(exc),
            }
            held.append(representation)

    common_ids = (
        set.intersection(*(set(block_ids[representation]) for representation in available))
        if available
        else set()
    )
    return {
        "available_representations": available,
        "held_representations": held,
        "common_selection_block_ids": [
            str(block["id"]) for block in prior_blocks if str(block["id"]) in common_ids
        ],
        "representation_block_ids": block_ids,
        "representation_diagnostics": diagnostics,
    }


def evaluate_issue448_matched_candidate(
    *,
    session_path: pd.DataFrame,
    features: pd.DataFrame,
    config: Mapping[str, object],
    candidate_column: str,
    blocks: Sequence[Mapping[str, str]],
    phase2_cfg: Mapping[str, Any],
    risk: object,
    costs: object,
    minimum_training_rows: int,
) -> dict[str, object]:
    """Score one #448 representation and its exact matched #425 control."""
    from commodity import v2_optimization as v2
    from commodity.market_only_phase2 import (
        _build_segmented_decision_origins,
        _canonicalize_one_origin_per_fill,
    )

    try:
        prepared, candidate_only, control_columns = prepare_issue448_candidate_features(
            features, config, candidate_column
        )
        origins, feature_columns = _build_segmented_decision_origins(
            session_path,
            prepared,
            horizon_sessions=int(config["target.horizon_sessions"]),
        )
        if origins.empty:
            raise Issue448CoverageError("issue-448 target reconstruction produced no origins")
        origins, _ = _canonicalize_one_origin_per_fill(origins)
        expected = set(candidate_only) | set(control_columns)
        if set(feature_columns) != expected:
            raise Issue448CoverageError("issue-448 prepared feature identity changed during origin build")
        multiplier = float(phase2_cfg["execution_contract"]["contract_multiplier_mmbtu"])
        round_trip_per_mmbtu = float(costs.round_trip_usd) / multiplier
        origins = v2._attach_issue425_targets(
            origins,
            session_path,
            horizon_sessions=int(config["target.horizon_sessions"]),
            role=str(config["target.target_role"]),
            aggregation=str(config["target.aggregation"]),
            round_trip_per_mmbtu=round_trip_per_mmbtu,
        )
        candidate_columns = [*control_columns, *candidate_only]
        candidate_rows = [
            v2._score_issue425_block(
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
            v2._score_issue425_block(
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
        candidate = v2._aggregate_issue425_blocks(candidate_rows)
        control = v2._aggregate_issue425_blocks(control_rows)
        candidate_score = candidate["monthly_score"]
        control_score = control["monthly_score"]
        if not isinstance(candidate_score, Mapping) or not isinstance(control_score, Mapping):
            raise Issue448CoverageError("issue-448 matched score payload is invalid")
        candidate["status"] = "complete"
        candidate["representation"] = candidate_column
        candidate["matched_control"] = control
        candidate["matched_origin_count"] = len(origins)
        candidate["candidate_feature_columns"] = candidate_only
        candidate["control_feature_columns"] = control_columns
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
    except (Issue448CoverageError, v2.V2OptimizationError, ValueError, KeyError) as exc:
        return {
            "candidate_id": _stable_sha256(
                {"config": dict(config), "representation": candidate_column}
            )[:20],
            "status": "failed",
            "champion_eligible": True,
            "representation": candidate_column,
            "config": dict(config),
            "reason": str(exc),
        }


_STORAGE_GATE_KEYS = {
    "historical PIT publication timestamp": "historical_pit_publication_timestamp",
    "fixed consensus value before release": "fixed_consensus_value_before_release",
    "2010-2022 usable depth": "usable_depth_2010_2022",
    "private-research licensing permission": "private_research_licensing_permission",
    "reproducible source identity": "reproducible_source_identity",
}


def evaluate_issue448_storage_surprise_gate(
    source: Mapping[str, Any] | None,
    contract: Issue448Contract,
) -> dict[str, object]:
    gate = contract.prereg.get("storage_surprise_gate")
    if not isinstance(gate, Mapping):
        raise Issue448CoverageError("issue-448 storage surprise gate is missing")
    required = [str(value) for value in gate.get("activation_requires", [])]
    if required != list(_STORAGE_GATE_KEYS):
        raise Issue448CoverageError("issue-448 storage surprise activation gates differ from preregistration")
    if source is None:
        missing = required
    else:
        if source.get("expectation_kind") != "pre_release_market_consensus":
            raise Issue448CoverageError("issue-448 consensus substitution is prohibited")
        missing = [
            label
            for label, key in _STORAGE_GATE_KEYS.items()
            if source.get(key) is not True
        ]
    return {
        "disposition": "SCORE" if not missing else "HOLD",
        "missing_gates": missing,
        "search_budget_consumed": not bool(missing),
        "protected_confirmation_accessed": False,
    }


def build_issue448_event_timing_features(
    decision_times: pd.DatetimeIndex | pd.Series | list[object],
    releases: pd.DataFrame,
    contract: Issue448Contract,
) -> pd.DataFrame:
    event = contract.prereg.get("scheduled_event_timing")
    if not isinstance(event, Mapping) or event.get("event") != "EIA Weekly Natural Gas Storage Report":
        raise Issue448CoverageError("issue-448 scheduled-event contract is invalid")
    decisions = pd.DatetimeIndex(pd.to_datetime(decision_times, utc=True, errors="raise"))
    if not decisions.is_monotonic_increasing or decisions.has_duplicates:
        raise Issue448CoverageError("issue-448 decision times must be chronological and unique")
    if "available_at" not in releases:
        raise Issue448CoverageError("issue-448 release stream lacks available_at")
    release_times = pd.DatetimeIndex(
        pd.to_datetime(releases["available_at"], utc=True, errors="raise")
    )
    if not release_times.is_monotonic_increasing or release_times.has_duplicates:
        raise Issue448CoverageError("issue-448 release availability must be chronological and unique")

    rows: list[dict[str, object]] = []
    first_after: set[pd.Timestamp] = set()
    for release in release_times:
        later = decisions[decisions > release]
        if len(later):
            first_after.add(later[0])
    for decision in decisions:
        prior = release_times[release_times < decision]
        following = release_times[release_times >= decision]
        rows.append(
            {
                "decision_at": decision,
                "hours_to_next_release": (
                    (following[0] - decision).total_seconds() / 3600.0 if len(following) else np.nan
                ),
                "hours_since_last_release": (
                    (decision - prior[-1]).total_seconds() / 3600.0 if len(prior) else np.nan
                ),
                "first_executable_session_after_release": float(decision in first_after),
            }
        )
    return pd.DataFrame.from_records(rows)


def evaluate_issue448_options_preflight(
    preflight: Mapping[str, Any],
    contract: Issue448Contract,
) -> dict[str, object]:
    gate = contract.prereg.get("options_implied_gate")
    if not isinstance(gate, Mapping):
        raise Issue448CoverageError("issue-448 options-implied gate is missing")
    cost = preflight.get("quoted_cost_usd")
    zero_cost = isinstance(cost, (int, float)) and not isinstance(cost, bool) and float(cost) == 0.0
    metadata_ready = preflight.get("metadata_schema_compatible") is True
    preflight_pass = zero_cost and metadata_ready
    activation_checks = {
        "local_inventory": preflight.get("local_inventory") is True,
        "metadata_schema_compatible": metadata_ready,
        "zero_spend": zero_cost,
        "private_research_licensing_permission": preflight.get(
            "private_research_licensing_permission"
        ) is True,
        "strike_expiry_depth_verified": preflight.get("strike_expiry_depth_verified") is True,
        "pit_timestamp_semantics_verified": preflight.get(
            "pit_timestamp_semantics_verified"
        ) is True,
    }
    missing = [name for name, passed in activation_checks.items() if not passed]
    return {
        "preflight_disposition": "PASS_ZERO_SPEND" if preflight_pass else "HOLD",
        "activation_disposition": "SCORE" if not missing else "HOLD",
        "missing_activation_gates": missing,
        "v2_blocking": False,
        "billable_acquisition_allowed": False,
    }


def issue448_volatility_tail_handoff(contract: Issue448Contract) -> dict[str, tuple[object, ...]]:
    handoff = contract.prereg.get("volatility_tail_handoff")
    if not isinstance(handoff, Mapping):
        raise Issue448CoverageError("issue-448 volatility/tail handoff is missing")
    return {
        "downstream_issues": tuple(int(value) for value in handoff["downstream_issues"]),
        "specialists": tuple(map(str, handoff["specialists"])),
        "state_features": tuple(map(str, handoff["state_features"])),
        "evaluation_roles": tuple(map(str, handoff["evaluation_roles"])),
    }


def _stable_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_issue448_blocks(
    blocks: list[Mapping[str, str]],
    *,
    cutoff: pd.Timestamp,
    label: str,
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in blocks:
        block_id = str(raw.get("id", ""))
        if not block_id or block_id in seen:
            raise Issue448CoverageError(f"issue-448 {label} block identity is invalid")
        seen.add(block_id)
        start = pd.Timestamp(str(raw.get("start", "")), tz="UTC")
        end = pd.Timestamp(str(raw.get("end", "")), tz="UTC")
        if start > end:
            raise Issue448CoverageError(f"issue-448 {label} block is not chronological")
        if end > cutoff:
            raise Issue448CoverageError(f"issue-448 {label} block crosses protected cutoff")
        normalized.append(
            {"id": block_id, "start": start.date().isoformat(), "end": end.date().isoformat()}
        )
    return normalized


def _issue448_trial_record(
    *,
    stage: str,
    family: str,
    representation: str | None,
    outer_block_id: str | None,
    blocks: list[dict[str, str]],
    result: Mapping[str, object],
) -> dict[str, object]:
    record = {
        "issue": 448,
        "evidence_class": "development",
        "stage": stage,
        "family": family,
        "representation": representation,
        "outer_block_id": outer_block_id,
        "selection_block_ids": [block["id"] for block in blocks],
        "result": dict(result),
    }
    return {"trial_id": _stable_sha256(record), **record}


def run_issue448_development_coverage(
    *,
    contract: Issue448Contract,
    family_candidates: Mapping[str, tuple[str, ...]],
    held_families: Mapping[str, str],
    inner_blocks: list[Mapping[str, str]],
    outer_blocks: list[Mapping[str, str]],
    evaluator: Any,
    selection_supporter: Any | None = None,
    family_outer_blocks: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
) -> dict[str, object]:
    cutoff = pd.Timestamp(contract.latest_allowed_trade_date, tz="UTC")
    if cutoff > ISSUE448_DEVELOPMENT_CUTOFF or contract.protected_confirmation_accessed:
        raise Issue448CoverageError("issue-448 development coverage crossed protected evidence")
    inners = _validate_issue448_blocks(inner_blocks, cutoff=cutoff, label="inner")
    outers = _validate_issue448_blocks(outer_blocks, cutoff=cutoff, label="outer")
    normalized_family_outers = {
        str(family): _validate_issue448_blocks(
            list(blocks), cutoff=cutoff, label=f"outer-{family}"
        )
        for family, blocks in (family_outer_blocks or {}).items()
    }
    trials: list[dict[str, object]] = []
    family_results: dict[str, object] = {}

    for family, disposition in sorted(held_families.items()):
        held_result = {
            "disposition": str(disposition),
            "search_budget_consumed": False,
            "nested_outer": [],
        }
        family_results[family] = held_result
        trials.append(
            _issue448_trial_record(
                stage="source_gate_hold",
                family=family,
                representation=None,
                outer_block_id=None,
                blocks=[],
                result=held_result,
            )
        )

    for family, representations in sorted(family_candidates.items()):
        if not representations or len(set(representations)) != len(representations):
            raise Issue448CoverageError(f"issue-448 family {family} has invalid candidates")
        nested_outer: list[dict[str, object]] = []
        skipped_outer: list[dict[str, object]] = []
        active_outers = normalized_family_outers.get(family, outers)
        for outer in active_outers:
            outer_start = pd.Timestamp(outer["start"], tz="UTC")
            eligible = [
                block
                for block in inners
                if pd.Timestamp(block["end"], tz="UTC") < outer_start
            ]
            if not eligible:
                skipped_outer.append(
                    {"outer_block": outer, "disposition": "SKIP_NO_PRIOR_INNER_EVIDENCE"}
                )
                continue

            if selection_supporter is None:
                support: dict[str, object] = {
                    "available_representations": list(representations),
                    "held_representations": [],
                    "common_selection_block_ids": [block["id"] for block in eligible],
                    "representation_diagnostics": {},
                }
            else:
                support = dict(selection_supporter(outer, family, representations, eligible))
            available_representations = [
                str(value) for value in support.get("available_representations", [])
            ]
            held_representations = [
                str(value) for value in support.get("held_representations", [])
            ]
            if (
                not set(available_representations).issubset(set(representations))
                or not set(held_representations).issubset(set(representations))
                or set(available_representations) & set(held_representations)
            ):
                raise Issue448CoverageError(
                    f"issue-448 family {family} selection support is inconsistent"
                )
            common_ids = [
                str(value) for value in support.get("common_selection_block_ids", [])
            ]
            eligible_by_id = {block["id"]: block for block in eligible}
            if len(common_ids) != len(set(common_ids)) or not set(common_ids).issubset(
                eligible_by_id
            ):
                raise Issue448CoverageError(
                    f"issue-448 family {family} selection support references invalid blocks"
                )
            common_blocks = [block for block in eligible if block["id"] in set(common_ids)]
            diagnostics = support.get("representation_diagnostics", {})
            for representation in held_representations:
                held_result = {
                    "disposition": "HOLD_INSUFFICIENT_PRIOR_FEATURE_SUPPORT",
                    "search_budget_consumed": False,
                    "support": (
                        diagnostics.get(representation)
                        if isinstance(diagnostics, Mapping)
                        else None
                    ),
                }
                trials.append(
                    _issue448_trial_record(
                        stage="selection_support_hold",
                        family=family,
                        representation=representation,
                        outer_block_id=outer["id"],
                        blocks=[],
                        result=held_result,
                    )
                )
            if not common_blocks or not available_representations:
                skipped_outer.append(
                    {
                        "outer_block": outer,
                        "disposition": "SKIP_INSUFFICIENT_PRIOR_FEATURE_SUPPORT",
                        "available_representations": available_representations,
                        "held_representations": held_representations,
                        "common_selection_block_ids": common_ids,
                    }
                )
                continue

            selection_rows: list[tuple[str, dict[str, object]]] = []
            for representation in available_representations:
                result = dict(
                    evaluator(
                        "inner_selection",
                        outer["id"],
                        common_blocks,
                        family,
                        representation,
                    )
                )
                trials.append(
                    _issue448_trial_record(
                        stage="inner_selection",
                        family=family,
                        representation=representation,
                        outer_block_id=outer["id"],
                        blocks=common_blocks,
                        result=result,
                    )
                )
                if result.get("status", "complete") == "complete":
                    selection_rows.append((representation, result))
            if not selection_rows:
                skipped_outer.append(
                    {"outer_block": outer, "disposition": "HOLD_ALL_INNER_CANDIDATES_FAILED"}
                )
                continue
            def selection_key(item: tuple[str, dict[str, object]]) -> tuple[float, int, str]:
                representation, result = item
                ablation = result.get("ablation")
                if not isinstance(ablation, Mapping):
                    raise Issue448CoverageError("issue-448 evaluator omitted matched ablation")
                delta = float(ablation["mean_monthly_net_return_delta"])
                complexity = int(result.get("complexity_rank", 0))
                return (-delta, complexity, representation)

            selected_representation, selected_inner = min(selection_rows, key=selection_key)
            outer_result = dict(
                evaluator(
                    "outer_evaluation",
                    outer["id"],
                    [outer],
                    family,
                    selected_representation,
                )
            )
            trials.append(
                _issue448_trial_record(
                    stage="outer_evaluation",
                    family=family,
                    representation=selected_representation,
                    outer_block_id=outer["id"],
                    blocks=[outer],
                    result=outer_result,
                )
            )
            if outer_result.get("status", "complete") != "complete":
                skipped_outer.append(
                    {
                        "outer_block": outer,
                        "disposition": "HOLD_SELECTED_OUTER_FAILED",
                        "selected_representation": selected_representation,
                    }
                )
                continue
            nested_outer.append(
                {
                    "outer_block": outer,
                    "selection_block_ids": [block["id"] for block in common_blocks],
                    "available_representations": available_representations,
                    "held_representations": held_representations,
                    "selection_support": support,
                    "selected_representation": selected_representation,
                    "selected_inner_result": selected_inner,
                    "outer_result": outer_result,
                }
            )

        deltas = [
            float(item["outer_result"]["ablation"]["mean_monthly_net_return_delta"])
            for item in nested_outer
        ]
        mean_delta = float(np.mean(deltas)) if deltas else None
        disposition = (
            "RETAIN_MATCHED_MARGINAL_VALUE"
            if mean_delta is not None and mean_delta > 0.0
            else "HOLD_NO_MATCHED_MARGINAL_VALUE"
            if mean_delta is not None
            else "HOLD_NO_SCORABLE_OUTER_BLOCK"
        )
        family_results[family] = {
            "disposition": disposition,
            "search_budget_consumed": True,
            "nested_outer": nested_outer,
            "skipped_outer": skipped_outer,
            "mean_monthly_net_return_delta": mean_delta,
        }

    trial_ledger_sha = _stable_sha256(trials)
    result_core: dict[str, object] = {
        "schema_version": 1,
        "issue": 448,
        "evidence_class": "development",
        "latest_allowed_trade_date": contract.latest_allowed_trade_date,
        "protected_confirmation_accessed": False,
        "prereg_sha256": contract.prereg_sha256,
        "source_feasibility_sha256": contract.source_feasibility_sha256,
        "family_results": family_results,
        "trial_count": len(trials),
        "trials": trials,
        "trial_ledger_sha256": trial_ledger_sha,
    }
    result_core["result_sha256"] = _stable_sha256(result_core)
    return result_core
