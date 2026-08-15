from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from commodity.contracts import ForecastModel
from commodity.evaluation import (
    evaluate_predictions,
    paired_block_bootstrap_rmse,
    walk_forward_predict,
)
from commodity.evaluation_protocol import (
    benjamini_hochberg_adjust,
    evaluate_direction_probabilities,
    evaluate_zero_mean_gaussian_volatility,
)
from commodity.models import baseline_factory

_SUPPORTED_FAMILIES = {
    "market",
    "market_structure",
    "storage",
    "weather",
    "power",
    "positioning",
    "calendar_seasonality",
}


def _validate_index(index: pd.Index, *, initial_train: int, retrain_every: int) -> None:
    if not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("Phase D inputs must be chronological and unique")
    if initial_train < 20 or initial_train >= len(index):
        raise ValueError("initial_train must leave an out-of-sample period")
    if retrain_every < 1:
        raise ValueError("retrain_every must be at least 1")


def _exogenous_sources(manifest: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    lineage = manifest.get("source_lineage", {})
    if isinstance(lineage, Mapping) and "exogenous_sources" in lineage:
        sources = lineage.get("exogenous_sources", [])
    else:
        sources = manifest.get("exogenous_sources", [])
    if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)):
        raise TypeError("Phase D manifest exogenous sources must be a sequence")
    return [source for source in sources if isinstance(source, Mapping)]


def feature_family_columns(
    frame: pd.DataFrame,
    manifest: Mapping[str, Any],
    *,
    target: str,
) -> dict[str, tuple[str, ...]]:
    families = [str(value) for value in manifest.get("required_feature_families", [])]
    if not families or len(families) != len(set(families)):
        raise ValueError("Phase D requires unique feature families")
    unknown = sorted(set(families) - _SUPPORTED_FAMILIES)
    if unknown:
        raise ValueError(f"Unsupported Phase D feature families: {unknown}")
    if target not in frame.columns:
        raise ValueError(f"Phase D target column is missing: {target}")

    feature_columns = [column for column in frame.columns if column != target]
    assigned: dict[str, list[str]] = {family: [] for family in families}
    claimed: set[str] = set()
    for source in _exogenous_sources(manifest):
        family = str(source.get("family", ""))
        if family not in assigned:
            continue
        for column in source.get("value_columns", []):
            name = str(column)
            if name in feature_columns and name not in claimed:
                assigned[family].append(name)
                claimed.add(name)

    prefix_families = {
        "market_structure": "curve_",
        "calendar_seasonality": "season_",
    }
    for family, prefix in prefix_families.items():
        if family not in assigned:
            continue
        for column in feature_columns:
            if column.startswith(prefix) and column not in claimed:
                assigned[family].append(column)
                claimed.add(column)

    if "market" in assigned:
        for column in feature_columns:
            if column not in claimed:
                assigned["market"].append(column)
                claimed.add(column)

    unassigned = [column for column in feature_columns if column not in claimed]
    empty = [family for family, columns in assigned.items() if not columns]
    if unassigned or empty:
        raise ValueError(
            "Phase D feature-family partition is incomplete: "
            f"unassigned={unassigned}, empty={empty}"
        )
    return {family: tuple(columns) for family, columns in assigned.items()}


def build_walk_forward_folds(
    index: pd.Index,
    *,
    initial_train: int,
    retrain_every: int,
) -> list[dict[str, str]]:
    _validate_index(index, initial_train=initial_train, retrain_every=retrain_every)
    folds: list[dict[str, str]] = []
    for fold_number, test_start in enumerate(range(initial_train, len(index), retrain_every)):
        test_end = min(test_start + retrain_every - 1, len(index) - 1)
        folds.append(
            {
                "fold_id": f"fold-{fold_number:03d}",
                "train_start": pd.Timestamp(index[0]).isoformat(),
                "train_end": pd.Timestamp(index[test_start - 1]).isoformat(),
                "test_start": pd.Timestamp(index[test_start]).isoformat(),
                "test_end": pd.Timestamp(index[test_end]).isoformat(),
            }
        )
    return folds


def _rolling_sigma(y: pd.Series, *, end: int, window: int) -> float:
    history = y.iloc[max(0, end - window):end].astype(float)
    sigma = float(history.std(ddof=1)) if len(history) > 1 else float("nan")
    if not np.isfinite(sigma) or sigma <= 0.0:
        fallback = y.iloc[:end].astype(float)
        sigma = float(fallback.std(ddof=1)) if len(fallback) > 1 else float("nan")
    if not np.isfinite(sigma) or sigma <= 0.0:
        sigma = float(np.finfo(float).eps)
    return sigma


def walk_forward_distribution_predict(
    model_factory: Callable[[], ForecastModel],
    x: pd.DataFrame,
    y: pd.Series,
    *,
    initial_train: int,
    retrain_every: int,
    volatility_window: int,
) -> pd.DataFrame:
    if volatility_window < 2:
        raise ValueError("volatility_window must be at least 2")
    mean_predictions = walk_forward_predict(
        model_factory,
        x,
        y,
        initial_train=initial_train,
        retrain_every=retrain_every,
    )
    normal = NormalDist()
    sigmas: list[float] = []
    probabilities: list[float] = []
    for offset, row in enumerate(mean_predictions.itertuples()):
        position = initial_train + offset
        sigma = _rolling_sigma(y, end=position, window=volatility_window)
        mean = float(row.prediction)
        probability = float(np.clip(normal.cdf(mean / sigma), 0.0, 1.0))
        sigmas.append(sigma)
        probabilities.append(probability)
    out = mean_predictions.copy()
    out["predicted_sigma"] = sigmas
    out["up_probability"] = probabilities
    return out


def _regime_thresholds(y: pd.Series, *, initial_train: int) -> dict[str, float]:
    observed = y.iloc[:initial_train].abs().to_numpy(dtype=float)
    low, high = np.quantile(observed, [1.0 / 3.0, 2.0 / 3.0])
    low_value = float(low)
    high_value = float(high)
    if high_value <= low_value:
        high_value = float(np.nextafter(low_value, np.inf))
    return {"low": low_value, "high": high_value}


def _regime_masks(actual: pd.Series, thresholds: Mapping[str, float]) -> dict[str, pd.Series]:
    magnitude = actual.abs()
    low = float(thresholds["low"])
    high = float(thresholds["high"])
    return {
        "low": magnitude <= low,
        "medium": (magnitude > low) & (magnitude <= high),
        "high": magnitude > high,
    }


def _score_predictions(predictions: pd.DataFrame) -> dict[str, dict[str, float]]:
    return {
        "return": evaluate_predictions(predictions),
        "direction": evaluate_direction_probabilities(
            predictions["actual"], predictions["up_probability"]
        ),
        "volatility": evaluate_zero_mean_gaussian_volatility(
            predictions["actual"], predictions["predicted_sigma"]
        ),
    }


def _regime_scores(
    predictions: pd.DataFrame,
    thresholds: Mapping[str, float],
) -> dict[str, dict[str, float]]:
    scores: dict[str, dict[str, float]] = {}
    for name, mask in _regime_masks(predictions["actual"], thresholds).items():
        subset = predictions.loc[mask]
        if subset.empty:
            scores[name] = {"n": 0.0}
        else:
            scores[name] = evaluate_predictions(subset)
    return scores


def _rmse_improvement(challenger: pd.DataFrame, baseline: pd.DataFrame) -> float:
    challenger_rmse = evaluate_predictions(challenger)["rmse"]
    baseline_rmse = evaluate_predictions(baseline)["rmse"]
    return float(baseline_rmse - challenger_rmse)


def _period_rmse_improvements(
    challenger: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    periods: int = 3,
) -> list[float]:
    if not challenger.index.equals(baseline.index):
        raise ValueError("Period comparisons require identical prediction indexes")
    improvements: list[float] = []
    for positions in np.array_split(np.arange(len(challenger)), periods):
        if len(positions) == 0:
            improvements.append(0.0)
            continue
        improvements.append(
            _rmse_improvement(challenger.iloc[positions], baseline.iloc[positions])
        )
    return improvements


def _regime_rmse_improvements(
    challenger: pd.DataFrame,
    baseline: pd.DataFrame,
    thresholds: Mapping[str, float],
) -> dict[str, float]:
    if not challenger.index.equals(baseline.index):
        raise ValueError("Regime comparisons require identical prediction indexes")
    improvements: dict[str, float] = {}
    masks = _regime_masks(challenger["actual"], thresholds)
    for name, mask in masks.items():
        challenger_subset = challenger.loc[mask]
        baseline_subset = baseline.loc[mask]
        improvements[name] = (
            _rmse_improvement(challenger_subset, baseline_subset)
            if not challenger_subset.empty
            else 0.0
        )
    return improvements


def _paired_report(
    challenger: pd.DataFrame,
    baseline: pd.DataFrame,
    significance: Mapping[str, Any],
) -> dict[str, Any]:
    report = paired_block_bootstrap_rmse(
        challenger,
        baseline,
        block_size=int(significance["block_size"]),
        resamples=int(significance["resamples"]),
        confidence=float(significance["confidence"]),
        seed=int(significance["seed"]),
    )
    return dict(report)


def _ablation_names(families: Sequence[str]) -> list[tuple[str, str | None]]:
    return [("full", None), *[(f"without:{family}", family) for family in families]]


def run_phase_d_evaluation(
    frame: pd.DataFrame,
    manifest: Mapping[str, Any],
    *,
    model_names: Sequence[str],
    models: dict[str, dict[str, Any]],
    initial_train: int,
    retrain_every: int,
    volatility_window: int,
    significance: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    target = str(manifest.get("target", "target_ret_1"))
    mapping = feature_family_columns(frame, manifest, target=target)
    families = list(mapping)
    _validate_index(frame.index, initial_train=initial_train, retrain_every=retrain_every)
    if not model_names:
        raise ValueError("Phase D requires at least one model")
    y = frame[target].astype(float)
    thresholds = _regime_thresholds(y, initial_train=initial_train)
    folds = build_walk_forward_folds(
        frame.index, initial_train=initial_train, retrain_every=retrain_every
    )

    evaluations: list[dict[str, Any]] = []
    predictions: dict[str, pd.DataFrame] = {}
    for model_name in model_names:
        factory = baseline_factory(str(model_name), models)
        for ablation_name, excluded_family in _ablation_names(families):
            included = [family for family in families if family != excluded_family]
            columns = [column for family in included for column in mapping[family]]
            if not columns:
                raise ValueError(f"Phase D ablation {ablation_name!r} has no features")
            prediction = walk_forward_distribution_predict(
                factory,
                frame[columns].astype(float),
                y,
                initial_train=initial_train,
                retrain_every=retrain_every,
                volatility_window=volatility_window,
            )
            key = f"{model_name}|{ablation_name}"
            predictions[key] = prediction
            evaluations.append(
                {
                    "model": str(model_name),
                    "ablation": ablation_name,
                    "included_families": included,
                    "feature_columns": columns,
                    "metrics": _score_predictions(prediction),
                    "regime_metrics": _regime_scores(prediction, thresholds),
                }
            )

    baseline_model = str(model_names[0])
    baseline_full = predictions[f"{baseline_model}|full"]
    candidate_comparisons: list[dict[str, Any]] = []
    for model_name in model_names:
        challenger = predictions[f"{model_name}|full"]
        report = _paired_report(challenger, baseline_full, significance)
        candidate_comparisons.append(
            {
                "model": str(model_name),
                "baseline_model": baseline_model,
                **report,
                "period_rmse_improvements": _period_rmse_improvements(
                    challenger, baseline_full
                ),
                "regime_rmse_improvements": _regime_rmse_improvements(
                    challenger, baseline_full, thresholds
                ),
            }
        )
    candidate_adjusted = benjamini_hochberg_adjust(
        [float(item["p_value"]) for item in candidate_comparisons]
    )
    for item, adjusted in zip(candidate_comparisons, candidate_adjusted, strict=True):
        item["adjusted_p_value"] = adjusted

    ablation_effects: list[dict[str, Any]] = []
    for model_name in model_names:
        full = predictions[f"{model_name}|full"]
        for family in families:
            ablated = predictions[f"{model_name}|without:{family}"]
            report = _paired_report(full, ablated, significance)
            ablation_effects.append(
                {
                    "model": str(model_name),
                    "family": family,
                    **report,
                    "period_rmse_improvements": _period_rmse_improvements(full, ablated),
                    "regime_rmse_improvements": _regime_rmse_improvements(
                        full, ablated, thresholds
                    ),
                }
            )
    ablation_adjusted = benjamini_hochberg_adjust(
        [float(item["p_value"]) for item in ablation_effects]
    )
    for item, adjusted in zip(ablation_effects, ablation_adjusted, strict=True):
        item["adjusted_p_value"] = adjusted

    result: dict[str, Any] = {
        "schema_version": 1,
        "target": target,
        "baseline_model": baseline_model,
        "feature_families": mapping,
        "folds": folds,
        "regime_thresholds": thresholds,
        "evaluations": evaluations,
        "candidate_comparisons": candidate_comparisons,
        "ablation_effects": ablation_effects,
        "preserve_all_candidates": True,
        "preserve_negative_results": True,
    }
    return result, predictions
