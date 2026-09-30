from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss


class Issue428DecisionError(ValueError):
    """Raised when the frozen #428 decision-optimization contract is violated."""


_PROTECTED_START = pd.Timestamp("2023-01-01T00:00:00Z")
_EXPECTED_CANDIDATE_GRID_SIGNATURE = (
    (0.50, 0.65, 0.80),
    True,
    (3, 4, 5),
    ((0.50, 0.65), (3, 4)),
    (0.75, 0.90),
    (0.75, 0.90),
    (0.75, 0.90),
    (1, 2, 3),
    (0.50, 0.55, 0.60, 0.65),
    (0.50, 0.55, 0.60, 0.65),
    29,
)


@dataclass(frozen=True)
class DecisionConfig:
    config_id: str
    kind: str
    complexity: int
    strength_quantile: float | None = None
    favored_signal_count: int | None = None
    veto_quantile: float | None = None
    persistence: int | None = None
    probability_threshold: float | None = None
    meta_mode: str | None = None


@dataclass(frozen=True)
class Issue428State:
    signal_states: dict[str, dict[str, Any]]
    strength_quantiles: dict[float, float]
    jump_quantiles: dict[float, float]
    vol_of_vol_quantiles: dict[float, float]
    jump_median: float
    vol_of_vol_median: float
    favorable_regimes: tuple[str, ...]
    regime_diagnostics: dict[str, dict[str, float | int]]


@dataclass(frozen=True)
class ConditionalSignalState:
    column: str
    threshold: float
    mean: float
    std: float
    favored: str
    low_rows: int
    high_rows: int
    low_mean_utility_usd: float
    high_mean_utility_usd: float


@dataclass(frozen=True)
class MetaConfidenceState:
    active: bool
    mode: str
    feature_columns: tuple[str, ...]
    training_rows: int
    calibration_rows: int
    training_end: pd.Timestamp | None
    calibration_start: pd.Timestamp | None
    positive_label_rate: float | None
    brier_score: float | None
    ece: float | None
    model: Any = None
    calibrator: Any = None


def _grid_section(prereg: Mapping[str, object]) -> Mapping[str, object]:
    grid = prereg.get("candidate_grid")
    if not isinstance(grid, Mapping):
        raise Issue428DecisionError("issue-428 preregistration lacks candidate_grid")
    return grid


def build_issue428_candidate_grid(prereg: Mapping[str, object]) -> list[DecisionConfig]:
    grid = _grid_section(prereg)
    configs = [DecisionConfig("baseline", "baseline", 0)]
    for value in grid["strength_quantile_gates"]:
        q = float(value)
        configs.append(DecisionConfig(f"strength-q{int(q * 100):02d}", "strength", 1, strength_quantile=q))
    if bool(grid["model_agreement_gate"]):
        configs.append(DecisionConfig("model-agreement", "model_agreement", 1))
    for value in grid["favored_signal_count_gates"]:
        count = int(value)
        configs.append(DecisionConfig(f"favored-signals-ge{count}", "favored_count", 1, favored_signal_count=count))
    cross = grid["strength_fusion_cross"]
    if not isinstance(cross, Mapping):
        raise Issue428DecisionError("issue-428 strength fusion contract is invalid")
    signature = (
        tuple(float(value) for value in grid["strength_quantile_gates"]),
        bool(grid["model_agreement_gate"]),
        tuple(int(value) for value in grid["favored_signal_count_gates"]),
        (
            tuple(float(value) for value in cross["strength_quantiles"]),
            tuple(int(value) for value in cross["favored_signal_counts"]),
        ),
        tuple(float(value) for value in grid["jump_veto_quantiles"]),
        tuple(float(value) for value in grid["vol_of_vol_veto_quantiles"]),
        tuple(float(value) for value in grid["joint_volatility_veto_quantiles"]),
        tuple(int(value) for value in grid["favorable_regime_persistence"]),
        tuple(float(value) for value in grid["meta_basic_probability_thresholds"]),
        tuple(float(value) for value in grid["meta_interaction_probability_thresholds"]),
        int(grid["expected_configuration_count"]),
    )
    if signature != _EXPECTED_CANDIDATE_GRID_SIGNATURE:
        raise Issue428DecisionError("issue-428 frozen candidate-grid identity changed")
    for q in cross["strength_quantiles"]:
        for count in cross["favored_signal_counts"]:
            configs.append(DecisionConfig(
                f"strength-q{int(float(q) * 100):02d}__favored-ge{int(count)}",
                "strength_fusion", 2, strength_quantile=float(q), favored_signal_count=int(count),
            ))
    for kind, key, prefix in (
        ("jump_veto", "jump_veto_quantiles", "jump-veto"),
        ("vol_of_vol_veto", "vol_of_vol_veto_quantiles", "vol-of-vol-veto"),
        ("joint_volatility_veto", "joint_volatility_veto_quantiles", "joint-vol-veto"),
    ):
        for value in grid[key]:
            q = float(value)
            configs.append(DecisionConfig(f"{prefix}-q{int(q * 100):02d}", kind, 2 if kind.startswith("joint") else 1, veto_quantile=q))
    for value in grid["favorable_regime_persistence"]:
        persistence = int(value)
        configs.append(DecisionConfig(
            f"favorable-regime-p{persistence}", "favorable_regime",
            1 + persistence, persistence=persistence,
        ))
    for mode, key in (
        ("basic", "meta_basic_probability_thresholds"),
        ("interactions", "meta_interaction_probability_thresholds"),
    ):
        for value in grid[key]:
            threshold = float(value)
            configs.append(DecisionConfig(
                f"meta-{mode}-p{int(threshold * 100):02d}", "meta", 4 if mode == "basic" else 6,
                probability_threshold=threshold, meta_mode=mode,
            ))
    expected = int(grid["expected_configuration_count"])
    identities = [item.config_id for item in configs]
    if len(configs) != expected or len(set(identities)) != expected:
        raise Issue428DecisionError(
            f"issue-428 candidate grid changed: expected={expected} observed={len(configs)} unique={len(set(identities))}"
        )
    return configs


def validate_issue428_evidence_boundary(frame: pd.DataFrame, *, date_column: str = "trade_date") -> None:
    if date_column not in frame.columns:
        raise Issue428DecisionError(f"issue-428 evidence missing date column: {date_column}")
    dates = pd.to_datetime(frame[date_column], utc=True, errors="coerce")
    if dates.isna().any():
        raise Issue428DecisionError("issue-428 evidence contains invalid timestamps")
    if (dates >= _PROTECTED_START).any():
        raise Issue428DecisionError("protected 2023+ evidence is forbidden in issue-428")
    if "target_end_timestamp" in frame.columns:
        target_end = pd.to_datetime(frame["target_end_timestamp"], utc=True, errors="coerce")
        if target_end.isna().any():
            raise Issue428DecisionError("issue-428 evidence contains invalid target-end timestamps")
        if (target_end >= _PROTECTED_START).any():
            raise Issue428DecisionError("protected 2023+ realized outcomes are forbidden in issue-428")


def _utc_boundary(boundary: object) -> pd.Timestamp:
    cutoff = pd.Timestamp(boundary)
    return cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")


def _require_outcomes_available_before(
    frame: pd.DataFrame,
    boundary: object,
    *,
    label: str,
) -> pd.Timestamp:
    if "target_end_timestamp" not in frame.columns:
        raise Issue428DecisionError(f"issue-428 {label} lacks target_end_timestamp")
    cutoff = _utc_boundary(boundary)
    target_end = pd.to_datetime(frame["target_end_timestamp"], utc=True, errors="coerce")
    if target_end.isna().any():
        raise Issue428DecisionError(f"issue-428 {label} contains invalid target-end timestamps")
    if (target_end >= cutoff).any():
        raise Issue428DecisionError(f"issue-428 {label} crosses outcome-availability boundary")
    return cutoff


def completed_history_before(
    frame: pd.DataFrame,
    boundary: object,
) -> pd.DataFrame:
    validate_issue428_evidence_boundary(frame)
    cutoff = _utc_boundary(boundary)
    if "target_end_timestamp" not in frame.columns:
        raise Issue428DecisionError("issue-428 history lacks target_end_timestamp")
    target_end = pd.to_datetime(frame["target_end_timestamp"], utc=True, errors="coerce")
    if target_end.isna().any():
        raise Issue428DecisionError("issue-428 history contains invalid target-end timestamps")
    history = frame.loc[target_end < cutoff].copy()
    if len(history):
        _require_outcomes_available_before(history, cutoff, label="history")
    return history.sort_values("fill_timestamp", kind="stable").reset_index(drop=True)


def _numeric(series: pd.Series, label: str) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").astype(float)
    if not np.isfinite(values.dropna().to_numpy(dtype=float)).all():
        raise Issue428DecisionError(f"issue-428 {label} contains non-finite values")
    return values


def _quantiles(series: pd.Series, values: Sequence[float]) -> dict[float, float]:
    clean = _numeric(series, "quantile input").dropna()
    if clean.empty:
        raise Issue428DecisionError("issue-428 quantile input is empty")
    return {float(q): float(clean.quantile(float(q))) for q in values}


def _regime_labels(frame: pd.DataFrame, jump_median: float, vol_median: float) -> pd.Series:
    jump = _numeric(frame["jump_intensity"], "jump intensity")
    vol = _numeric(frame["vol_of_vol"], "vol-of-vol")
    return pd.Series(
        [f"j{int(j > jump_median)}_v{int(v > vol_median)}" for j, v in zip(jump, vol, strict=True)],
        index=frame.index,
        dtype="object",
    )


def fit_issue428_state(
    history: pd.DataFrame,
    *,
    signal_columns: Sequence[str],
    minimum_state_rows: int,
    outcome_available_before: object,
) -> Issue428State:
    validate_issue428_evidence_boundary(history)
    _require_outcomes_available_before(
        history, outcome_available_before, label="state history"
    )
    required = {"baseline_position", "primary_strength", "jump_intensity", "vol_of_vol", "net_trade_utility_usd", *signal_columns}
    missing = sorted(required - set(history.columns))
    if missing:
        raise Issue428DecisionError(f"issue-428 state history missing columns: {missing}")
    if minimum_state_rows < 1:
        raise Issue428DecisionError("issue-428 minimum state rows must be positive")
    work = history.copy().sort_values("trade_date", kind="stable")
    work["baseline_position"] = _numeric(work["baseline_position"], "baseline position")
    work["net_trade_utility_usd"] = _numeric(work["net_trade_utility_usd"], "net trade utility")
    base = work.loc[work["baseline_position"].ne(0.0)].copy()
    if len(base) < minimum_state_rows * 2:
        raise Issue428DecisionError("issue-428 state history has insufficient trade opportunities")
    signal_states: dict[str, dict[str, Any]] = {}
    for column in signal_columns:
        values = _numeric(base[column], column)
        valid = base.loc[values.notna()].copy()
        values = values.loc[values.notna()]
        if valid.empty:
            continue
        threshold = float(values.median())
        low_mask = values.le(threshold)
        high_mask = values.gt(threshold)
        low_utility = valid.loc[low_mask, "net_trade_utility_usd"]
        high_utility = valid.loc[high_mask, "net_trade_utility_usd"]
        eligible = len(low_utility) >= minimum_state_rows and len(high_utility) >= minimum_state_rows
        favored = None
        if eligible:
            favored = "high" if float(high_utility.mean()) > float(low_utility.mean()) else "low"
        mean = float(values.mean())
        std = float(values.std(ddof=0))
        if not math.isfinite(std) or std <= 0.0:
            std = 1.0
        signal_states[str(column)] = {
            "threshold": threshold,
            "mean": mean,
            "std": std,
            "low_rows": len(low_utility),
            "high_rows": len(high_utility),
            "low_mean_utility_usd": float(low_utility.mean()) if len(low_utility) else None,
            "high_mean_utility_usd": float(high_utility.mean()) if len(high_utility) else None,
            "eligible": bool(eligible),
            "favored": favored,
        }
    if not any(bool(item["eligible"]) for item in signal_states.values()):
        raise Issue428DecisionError("issue-428 has no effective retained signal states")

    strength_quantiles = _quantiles(base["primary_strength"], (0.50, 0.65, 0.80))
    jump_quantiles = _quantiles(base["jump_intensity"], (0.50, 0.75, 0.90))
    vol_quantiles = _quantiles(base["vol_of_vol"], (0.50, 0.75, 0.90))
    jump_median = jump_quantiles[0.50]
    vol_median = vol_quantiles[0.50]
    base["joint_regime"] = _regime_labels(base, jump_median, vol_median)
    favorable: list[str] = []
    regime_diagnostics: dict[str, dict[str, float | int]] = {}
    for regime, group in base.groupby("joint_regime", sort=True):
        rows = len(group)
        mean_utility = float(group["net_trade_utility_usd"].mean())
        regime_diagnostics[str(regime)] = {"rows": rows, "mean_utility_usd": mean_utility}
        if rows >= minimum_state_rows and mean_utility > 0.0:
            favorable.append(str(regime))
    return Issue428State(
        signal_states=signal_states,
        strength_quantiles=strength_quantiles,
        jump_quantiles=jump_quantiles,
        vol_of_vol_quantiles=vol_quantiles,
        jump_median=jump_median,
        vol_of_vol_median=vol_median,
        favorable_regimes=tuple(sorted(favorable)),
        regime_diagnostics=regime_diagnostics,
    )


def annotate_issue428_states(
    frame: pd.DataFrame,
    state: Issue428State,
    *,
    signal_columns: Sequence[str],
) -> pd.DataFrame:
    validate_issue428_evidence_boundary(frame)
    missing = sorted({"baseline_position", "primary_strength", "model_agreement", "normalized_model_disagreement", "jump_intensity", "vol_of_vol", *signal_columns} - set(frame.columns))
    if missing:
        raise Issue428DecisionError(f"issue-428 scoring frame missing columns: {missing}")
    out = frame.copy().sort_values("trade_date", kind="stable")
    favored_columns: list[str] = []
    eligible = 0
    for column in signal_columns:
        info = state.signal_states.get(str(column))
        if not info or not bool(info["eligible"]):
            continue
        eligible += 1
        values = _numeric(out[column], column)
        if values.isna().any():
            raise Issue428DecisionError(
                f"issue-428 retained signal contains missing values: {column}"
            )
        out[f"{column}__z"] = ((values - float(info["mean"])) / float(info["std"])).clip(-5.0, 5.0)
        high = values.gt(float(info["threshold"]))
        favored = high if info["favored"] == "high" else ~high
        name = f"{column}__favored"
        out[name] = favored.astype(int)
        favored_columns.append(name)
    if eligible < 1:
        raise Issue428DecisionError("issue-428 scoring frame has no eligible retained signals")
    out["eligible_signal_count"] = eligible
    out["favored_count"] = out[favored_columns].sum(axis=1)
    out["favored_fraction"] = out["favored_count"] / float(eligible)
    out["joint_regime"] = _regime_labels(out, state.jump_median, state.vol_of_vol_median)
    persistence: list[int] = []
    prior: str | None = None
    count = 0
    for value in out["joint_regime"].astype(str):
        count = count + 1 if value == prior else 1
        persistence.append(count)
        prior = value
    out["regime_persistence"] = persistence
    out["jump_high"] = (_numeric(out["jump_intensity"], "jump intensity") > state.jump_median).astype(float)
    out["vol_of_vol_high"] = (_numeric(out["vol_of_vol"], "vol-of-vol") > state.vol_of_vol_median).astype(float)
    return out


def fit_conditional_signal_state(
    history: pd.DataFrame,
    *,
    column: str,
    minimum_history_rows: int,
    minimum_state_rows: int,
    outcome_available_before: object,
) -> ConditionalSignalState:
    validate_issue428_evidence_boundary(history)
    _require_outcomes_available_before(
        history, outcome_available_before, label="conditional history"
    )
    required = {"baseline_position", "net_trade_utility_usd", column}
    missing = sorted(required - set(history.columns))
    if missing:
        raise Issue428DecisionError(f"issue-428 conditional history missing columns: {missing}")
    work = history.copy().sort_values("trade_date", kind="stable")
    base = work.loc[_numeric(work["baseline_position"], "baseline position").ne(0.0)].copy()
    values = _numeric(base[column], column)
    base = base.loc[values.notna()].copy()
    values = values.loc[values.notna()]
    if len(base) < int(minimum_history_rows):
        raise Issue428DecisionError("issue-428 conditional signal has insufficient history")
    threshold = float(values.median())
    low = base.loc[values.le(threshold), "net_trade_utility_usd"]
    high = base.loc[values.gt(threshold), "net_trade_utility_usd"]
    if len(low) < int(minimum_state_rows) or len(high) < int(minimum_state_rows):
        raise Issue428DecisionError("issue-428 conditional signal states are undersized")
    std = float(values.std(ddof=0))
    if not math.isfinite(std) or std <= 0.0:
        std = 1.0
    return ConditionalSignalState(
        column=column,
        threshold=threshold,
        mean=float(values.mean()),
        std=std,
        favored="high" if float(high.mean()) > float(low.mean()) else "low",
        low_rows=len(low),
        high_rows=len(high),
        low_mean_utility_usd=float(low.mean()),
        high_mean_utility_usd=float(high.mean()),
    )


def annotate_conditional_signal(frame: pd.DataFrame, state: ConditionalSignalState) -> pd.DataFrame:
    validate_issue428_evidence_boundary(frame)
    if state.column not in frame.columns:
        raise Issue428DecisionError(f"issue-428 conditional frame missing {state.column}")
    out = frame.copy()
    values = _numeric(out[state.column], state.column)
    if values.isna().any():
        raise Issue428DecisionError("issue-428 conditional signal contains missing values")
    out[f"{state.column}__z"] = ((values - state.mean) / state.std).clip(-5.0, 5.0)
    high = values.gt(state.threshold)
    favored = high if state.favored == "high" else ~high
    out[f"{state.column}__favored"] = favored.astype(int)
    return out


def _meta_matrix(
    frame: pd.DataFrame,
    *,
    signal_columns: Sequence[str],
    mode: str,
    extra_feature_columns: Sequence[str] = (),
) -> pd.DataFrame:
    if mode not in {"basic", "interactions"}:
        raise Issue428DecisionError(f"unsupported issue-428 meta mode: {mode}")
    strength = _numeric(frame["primary_strength"], "primary strength").clip(lower=0.0)
    matrix = pd.DataFrame(index=frame.index)
    matrix["log_primary_strength"] = np.log1p(strength)
    matrix["model_agreement"] = _numeric(frame["model_agreement"], "model agreement")
    matrix["normalized_model_disagreement"] = _numeric(frame["normalized_model_disagreement"], "model disagreement")
    matrix["favored_fraction"] = _numeric(frame["favored_fraction"], "favored fraction")
    matrix["jump_high"] = _numeric(frame["jump_high"], "jump high")
    matrix["vol_of_vol_high"] = _numeric(frame["vol_of_vol_high"], "vol-of-vol high")
    if mode == "interactions":
        for column in signal_columns:
            z_column = f"{column}__z"
            if z_column not in frame.columns:
                raise Issue428DecisionError(f"issue-428 interaction frame missing {z_column}")
            matrix[z_column] = _numeric(frame[z_column], z_column)
        matrix["strength_x_favored_fraction"] = matrix["log_primary_strength"] * matrix["favored_fraction"]
        matrix["jump_x_vol_of_vol"] = matrix["jump_high"] * matrix["vol_of_vol_high"]
        matrix["model_agreement_x_favored_fraction"] = matrix["model_agreement"] * matrix["favored_fraction"]
        for column in extra_feature_columns:
            if column not in frame.columns:
                raise Issue428DecisionError(f"issue-428 extra meta feature missing {column}")
            matrix[str(column)] = _numeric(frame[column], str(column))
    elif extra_feature_columns:
        raise Issue428DecisionError("issue-428 extra meta features require interactions mode")
    if matrix.isna().any().any() or not np.isfinite(matrix.to_numpy(dtype=float)).all():
        raise Issue428DecisionError("issue-428 meta features contain invalid values")
    return matrix


def _ece(labels: np.ndarray, probabilities: np.ndarray, bins: int = 10) -> float:
    total = len(labels)
    if total == 0:
        return 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    value = 0.0
    for index in range(bins):
        lower, upper = edges[index], edges[index + 1]
        mask = (probabilities >= lower) & (probabilities < upper if index < bins - 1 else probabilities <= upper)
        if not np.any(mask):
            continue
        value += float(np.mean(mask)) * abs(float(np.mean(labels[mask])) - float(np.mean(probabilities[mask])))
    return float(value)


def fit_meta_confidence(
    history: pd.DataFrame,
    *,
    signal_columns: Sequence[str],
    mode: str,
    minimum_train_rows: int,
    minimum_calibration_rows: int,
    outcome_available_before: object,
    extra_feature_columns: Sequence[str] = (),
    excluded_features: Sequence[str] = (),
) -> MetaConfidenceState:
    validate_issue428_evidence_boundary(history)
    _require_outcomes_available_before(
        history, outcome_available_before, label="meta history"
    )
    required = {"trade_date", "target_end_timestamp", "baseline_position", "trade_profitable"}
    missing = sorted(required - set(history.columns))
    if missing:
        raise Issue428DecisionError(f"issue-428 meta history missing columns: {missing}")
    work = history.copy().sort_values("trade_date", kind="stable")
    work = work.loc[_numeric(work["baseline_position"], "baseline position").ne(0.0)].copy()
    labels = pd.to_numeric(work["trade_profitable"], errors="coerce")
    work = work.loc[labels.notna()].copy()
    labels = labels.loc[labels.notna()].astype(int)
    if not set(labels.unique()).issubset({0, 1}):
        raise Issue428DecisionError("issue-428 meta labels must be binary")
    requested_calibration_rows = max(
        int(minimum_calibration_rows), math.ceil(len(work) * 0.25)
    )
    requested_training_rows = len(work) - requested_calibration_rows
    if requested_training_rows < int(minimum_train_rows):
        raise Issue428DecisionError("issue-428 meta history has insufficient chronological rows")
    trade_dates = pd.to_datetime(work["trade_date"], utc=True, errors="raise")
    calibration_boundary = pd.Timestamp(trade_dates.iloc[requested_training_rows])
    train_candidates = work.loc[trade_dates < calibration_boundary].copy()
    calibrate = work.loc[trade_dates >= calibration_boundary].copy()
    train_target_end = pd.to_datetime(
        train_candidates["target_end_timestamp"], utc=True, errors="raise"
    )
    train = train_candidates.loc[train_target_end < calibration_boundary].copy()
    training_rows = len(train)
    calibration_rows = len(calibrate)
    if training_rows < int(minimum_train_rows) or calibration_rows < int(minimum_calibration_rows):
        raise Issue428DecisionError("issue-428 meta history has insufficient outcome-available rows")
    y_train = pd.to_numeric(train["trade_profitable"], errors="raise").astype(int).to_numpy()
    y_cal = pd.to_numeric(calibrate["trade_profitable"], errors="raise").astype(int).to_numpy()
    if len(np.unique(y_train)) < 2 or len(np.unique(y_cal)) < 2:
        raise Issue428DecisionError("issue-428 chronological meta split requires both label classes")
    x_train = _meta_matrix(
        train,
        signal_columns=signal_columns,
        mode=mode,
        extra_feature_columns=extra_feature_columns,
    )
    x_cal = _meta_matrix(
        calibrate,
        signal_columns=signal_columns,
        mode=mode,
        extra_feature_columns=extra_feature_columns,
    )
    excluded = {str(column) for column in excluded_features}
    missing_excluded = sorted(excluded - set(x_train.columns))
    if missing_excluded:
        raise Issue428DecisionError(
            f"issue-428 excluded meta features are unknown: {missing_excluded}"
        )
    if excluded:
        x_train = x_train.drop(columns=sorted(excluded))
        x_cal = x_cal.drop(columns=sorted(excluded))
    if x_train.shape[1] < 1:
        raise Issue428DecisionError("issue-428 meta ablation removed every feature")
    model = LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000)
    model.fit(x_train, y_train)
    raw = np.clip(model.predict_proba(x_cal)[:, 1], 1e-6, 1.0 - 1e-6)
    logit = np.log(raw / (1.0 - raw)).reshape(-1, 1)
    calibrator = LogisticRegression(C=1.0, max_iter=1000)
    calibrator.fit(logit, y_cal)
    calibrated = calibrator.predict_proba(logit)[:, 1]
    training_target_end = pd.to_datetime(
        train["target_end_timestamp"], utc=True, errors="raise"
    )
    calibration_dates = pd.to_datetime(calibrate["trade_date"], utc=True, errors="raise")
    return MetaConfidenceState(
        active=True,
        mode=mode,
        feature_columns=tuple(x_train.columns),
        training_rows=int(training_rows),
        calibration_rows=int(calibration_rows),
        training_end=pd.Timestamp(training_target_end.max()),
        calibration_start=pd.Timestamp(calibration_dates.min()),
        positive_label_rate=float(np.mean(y_cal)),
        brier_score=float(brier_score_loss(y_cal, calibrated)),
        ece=_ece(y_cal, calibrated),
        model=model,
        calibrator=calibrator,
    )


def predict_meta_confidence(
    frame: pd.DataFrame,
    state: MetaConfidenceState,
    *,
    signal_columns: Sequence[str],
    extra_feature_columns: Sequence[str] = (),
) -> pd.Series:
    if not state.active or state.model is None or state.calibrator is None:
        raise Issue428DecisionError("issue-428 meta confidence is inactive")
    matrix = _meta_matrix(
        frame,
        signal_columns=signal_columns,
        mode=state.mode,
        extra_feature_columns=extra_feature_columns,
    )
    missing = sorted(set(state.feature_columns) - set(matrix.columns))
    if missing:
        raise Issue428DecisionError(f"issue-428 meta feature identity changed: {missing}")
    matrix = matrix.loc[:, list(state.feature_columns)]
    raw = np.clip(state.model.predict_proba(matrix)[:, 1], 1e-6, 1.0 - 1e-6)
    logit = np.log(raw / (1.0 - raw)).reshape(-1, 1)
    calibrated = state.calibrator.predict_proba(logit)[:, 1]
    return pd.Series(calibrated, index=frame.index, dtype=float)


def apply_issue428_policy(
    frame: pd.DataFrame,
    config: DecisionConfig,
    state: Issue428State,
) -> pd.DataFrame:
    required = {"baseline_position", "primary_strength", "model_agreement", "favored_count", "jump_intensity", "vol_of_vol", "joint_regime", "regime_persistence"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise Issue428DecisionError(f"issue-428 policy frame missing columns: {missing}")
    out = frame.copy()
    baseline = _numeric(out["baseline_position"], "baseline position")
    if not set(baseline.dropna().unique()).issubset({-1.0, 0.0, 1.0}):
        raise Issue428DecisionError("issue-428 baseline position must be -1, 0 or +1")
    admit = baseline.ne(0.0)
    if config.kind == "baseline":
        pass
    elif config.kind == "strength":
        threshold = state.strength_quantiles[float(config.strength_quantile)]
        admit &= _numeric(out["primary_strength"], "primary strength").ge(threshold)
    elif config.kind == "model_agreement":
        admit &= out["model_agreement"].astype(bool)
    elif config.kind == "favored_count":
        admit &= _numeric(out["favored_count"], "favored count").ge(int(config.favored_signal_count))
    elif config.kind == "strength_fusion":
        threshold = state.strength_quantiles[float(config.strength_quantile)]
        admit &= _numeric(out["primary_strength"], "primary strength").ge(threshold)
        admit &= _numeric(out["favored_count"], "favored count").ge(int(config.favored_signal_count))
    elif config.kind in {"jump_veto", "vol_of_vol_veto", "joint_volatility_veto"}:
        q = float(config.veto_quantile)
        if config.kind in {"jump_veto", "joint_volatility_veto"}:
            admit &= _numeric(out["jump_intensity"], "jump intensity").le(state.jump_quantiles[q])
        if config.kind in {"vol_of_vol_veto", "joint_volatility_veto"}:
            admit &= _numeric(out["vol_of_vol"], "vol-of-vol").le(state.vol_of_vol_quantiles[q])
    elif config.kind == "favorable_regime":
        admit &= out["joint_regime"].astype(str).isin(state.favorable_regimes)
        admit &= _numeric(out["regime_persistence"], "regime persistence").ge(int(config.persistence))
    elif config.kind == "meta":
        if "meta_probability" not in out.columns:
            raise Issue428DecisionError("issue-428 meta policy lacks calibrated probability")
        admit &= _numeric(out["meta_probability"], "meta probability").ge(float(config.probability_threshold))
    else:
        raise Issue428DecisionError(f"unsupported issue-428 decision kind: {config.kind}")
    out["trade_admitted"] = admit.astype(bool)
    out["signal_requested_position"] = np.where(admit, baseline, 0.0).astype(float)
    out["policy_abstained"] = baseline.ne(0.0) & ~admit
    out["signal_reason"] = np.where(
        baseline.eq(0.0),
        "baseline_abstain",
        np.where(admit, "forecast_signal", f"issue428_{config.config_id}_abstain"),
    )
    return out


def select_issue428_policy(
    scores: pd.DataFrame,
    *,
    outer_start_year: int,
    required_years: Sequence[int] | None = None,
) -> dict[str, Any]:
    required = {
        "config_id", "year", "net_pnl_usd", "mean_monthly_net_return",
        "max_drawdown_fraction", "transaction_cost_usd", "complexity",
    }
    missing = sorted(required - set(scores.columns))
    if missing:
        raise Issue428DecisionError(f"issue-428 policy scores missing columns: {missing}")
    prior = scores.loc[pd.to_numeric(scores["year"], errors="coerce") < int(outer_start_year)].copy()
    if prior.empty:
        raise Issue428DecisionError("issue-428 has no prior policy scores before outer boundary")
    prior["year"] = pd.to_numeric(prior["year"], errors="raise").astype(int)
    if required_years is None:
        expected_years = sorted(prior["year"].unique().tolist())
    else:
        expected_years = sorted({int(year) for year in required_years})
        if not expected_years or expected_years[-1] >= int(outer_start_year):
            raise Issue428DecisionError("issue-428 required policy years must be nonempty and strictly prior to outer")
        prior = prior.loc[prior["year"].isin(expected_years)].copy()
        if prior.empty:
            raise Issue428DecisionError("issue-428 has no policy scores for required comparison years")
    rows: list[dict[str, Any]] = []
    for config_id, group in prior.groupby("config_id", sort=True):
        years = sorted(group["year"].unique().tolist())
        if years != expected_years or group["year"].duplicated().any():
            continue
        numeric = group[[
            "net_pnl_usd", "mean_monthly_net_return", "max_drawdown_fraction",
            "transaction_cost_usd", "complexity",
        ]].apply(pd.to_numeric, errors="coerce")
        if numeric.isna().any().any() or not np.isfinite(
            numeric.to_numpy(dtype=float)
        ).all():
            continue
        complexity_values = sorted(set(numeric["complexity"].astype(int).tolist()))
        if len(complexity_values) != 1:
            raise Issue428DecisionError("issue-428 configuration complexity changed across years")
        rows.append({
            "config_id": str(config_id),
            "years": years,
            "median_yearly_net_pnl_usd": float(numeric["net_pnl_usd"].median()),
            "mean_monthly_net_return": float(numeric["mean_monthly_net_return"].mean()),
            "worst_yearly_net_pnl_usd": float(numeric["net_pnl_usd"].min()),
            "max_drawdown_fraction": float(numeric["max_drawdown_fraction"].max()),
            "transaction_cost_usd": float(numeric["transaction_cost_usd"].sum()),
            "complexity": int(complexity_values[0]),
        })
    if not rows:
        raise Issue428DecisionError("issue-428 has no complete prior policy configuration")
    ranking = pd.DataFrame(rows).sort_values(
        [
            "median_yearly_net_pnl_usd",
            "mean_monthly_net_return",
            "worst_yearly_net_pnl_usd",
            "max_drawdown_fraction",
            "transaction_cost_usd",
            "complexity",
            "config_id",
        ],
        ascending=[False, False, False, True, True, True, True],
        kind="stable",
    )
    selected = ranking.iloc[0].to_dict()
    selected["years"] = [int(value) for value in selected["years"]]
    selected["ranking"] = ranking.to_dict("records")
    return selected
