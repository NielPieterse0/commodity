from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from commodity.evaluation import evaluate_predictions, paired_block_bootstrap_rmse
from commodity.models.baselines import RidgeReturnModel

A_FEATURES = ("market_log_hh", "season_sin", "season_cos")
B_PHYSICAL_FEATURES = (
    "realized_log_production",
    "realized_log_storage",
    "realized_log_consumption",
)
C_PHYSICAL_FEATURES = (
    "pit_log_production",
    "pit_log_storage",
    "pit_log_consumption",
)


@dataclass
class FrozenBModel:
    model: RidgeReturnModel
    fit_count: int = 1
    c_prediction_count: int = 0

    def predict_c(self, row: pd.DataFrame) -> pd.Series:
        self.c_prediction_count += 1
        return self.model.predict(row)


def _validate_bhlr_matrix(name: str, matrix: np.ndarray) -> np.ndarray:
    values = np.asarray(matrix, dtype=float)
    if values.ndim != 2:
        raise ValueError(f"{name} must be a two-dimensional vintage matrix")
    return values


def build_bhlr_physical_bottleneck_panel(
    *,
    ng_henry: np.ndarray,
    production: np.ndarray,
    storage: np.ndarray,
    consumption: np.ndarray,
    origin_periods: pd.PeriodIndex,
    start_row: int,
    start_column: int,
    final_column: int = -1,
) -> pd.DataFrame:
    matrices = {
        "ng_henry": _validate_bhlr_matrix("ng_henry", ng_henry),
        "production": _validate_bhlr_matrix("production", production),
        "storage": _validate_bhlr_matrix("storage", storage),
        "consumption": _validate_bhlr_matrix("consumption", consumption),
    }
    shapes = {matrix.shape for matrix in matrices.values()}
    if len(shapes) != 1:
        raise ValueError("BHLR bottleneck matrices must have identical shapes")
    if not isinstance(origin_periods, pd.PeriodIndex) or origin_periods.freqstr != "M":
        raise ValueError("origin_periods must be a monthly PeriodIndex")
    n = len(origin_periods)
    rows = np.arange(start_row, start_row + n)
    columns = np.arange(start_column, start_column + n)
    row_count, column_count = next(iter(shapes))
    resolved_final_column = final_column if final_column >= 0 else column_count + final_column
    if n < 2 or rows[-1] + 1 >= row_count or columns[-1] >= column_count:
        raise ValueError("BHLR bottleneck origin range exceeds matrix coverage")
    if not 0 <= resolved_final_column < column_count:
        raise ValueError("BHLR bottleneck final_column is outside matrix coverage")

    diagonal = {name: values[rows, columns] for name, values in matrices.items()}
    realized = {name: values[rows, resolved_final_column] for name, values in matrices.items()}
    target = matrices["ng_henry"][rows + 1, resolved_final_column]
    required = [*diagonal.values(), realized["production"], realized["storage"], realized["consumption"], target]
    if any((~np.isfinite(values)).any() or (values <= 0.0).any() for values in required):
        raise ValueError("BHLR bottleneck requires finite positive values on every frozen row")

    target_month = np.array([(period + 1).month for period in origin_periods], dtype=float)
    angle = 2.0 * np.pi * target_month / 12.0
    return pd.DataFrame(
        {
            "market_log_hh": np.log(diagonal["ng_henry"]),
            "season_sin": np.sin(angle),
            "season_cos": np.cos(angle),
            "realized_log_production": np.log(realized["production"]),
            "realized_log_storage": np.log(realized["storage"]),
            "realized_log_consumption": np.log(realized["consumption"]),
            "pit_log_production": np.log(diagonal["production"]),
            "pit_log_storage": np.log(diagonal["storage"]),
            "pit_log_consumption": np.log(diagonal["consumption"]),
            "target_log_hh": np.log(target),
        },
        index=origin_periods,
    )


def _prediction_frame(index: object, prediction: float, actual: float) -> dict[str, object]:
    return {"date": index, "prediction": float(prediction), "actual": float(actual)}


def walk_forward_ab(
    panel: pd.DataFrame,
    *,
    development_rows: int,
    alpha: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[pd.Period, FrozenBModel]]:
    required = {*A_FEATURES, *B_PHYSICAL_FEATURES, "target_log_hh"}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise ValueError(f"Physical bottleneck panel is missing columns: {missing}")
    if development_rows < 20 or development_rows >= len(panel):
        raise ValueError("development_rows must leave a non-empty OOS period")
    if not panel.index.is_monotonic_increasing or panel.index.has_duplicates:
        raise ValueError("Physical bottleneck panel must be chronological and unique")

    a_rows: list[dict[str, object]] = []
    b_rows: list[dict[str, object]] = []
    frozen: dict[pd.Period, FrozenBModel] = {}
    y = panel["target_log_hh"]
    for i in range(development_rows, len(panel)):
        train = panel.iloc[:i]
        a_model = RidgeReturnModel(alpha=alpha).fit(train[list(A_FEATURES)], y.iloc[:i])
        b_columns = [*A_FEATURES, *B_PHYSICAL_FEATURES]
        b_model = RidgeReturnModel(alpha=alpha).fit(train[b_columns], y.iloc[:i])
        row = panel.iloc[[i]]
        actual = float(y.iloc[i])
        a_prediction = float(a_model.predict(row[list(A_FEATURES)]).iloc[0])
        b_prediction = float(b_model.predict(row[b_columns]).iloc[0])
        index = panel.index[i]
        a_rows.append(_prediction_frame(index, a_prediction, actual))
        b_rows.append(_prediction_frame(index, b_prediction, actual))
        frozen[index] = FrozenBModel(b_model)

    def frame(rows: list[dict[str, object]]) -> pd.DataFrame:
        return pd.DataFrame(rows).set_index("date")

    return frame(a_rows), frame(b_rows), frozen


def predict_c_from_frozen_b_models(
    panel: pd.DataFrame,
    frozen: dict[pd.Period, FrozenBModel],
) -> pd.DataFrame:
    if not frozen:
        raise ValueError("C prediction requires frozen B models")
    rows: list[dict[str, object]] = []
    for index, state in frozen.items():
        source = panel.loc[[index]]
        c_row = source[list(A_FEATURES)].copy()
        for b_column, c_column in zip(B_PHYSICAL_FEATURES, C_PHYSICAL_FEATURES, strict=True):
            c_row[b_column] = source[c_column].to_numpy(dtype=float)
        c_row = c_row[[*A_FEATURES, *B_PHYSICAL_FEATURES]]
        prediction = float(state.predict_c(c_row).iloc[0])
        rows.append(_prediction_frame(index, prediction, float(source["target_log_hh"].iloc[0])))
    return pd.DataFrame(rows).set_index("date")


def _rmse(predictions: pd.DataFrame) -> float:
    error = predictions["prediction"].to_numpy(dtype=float) - predictions["actual"].to_numpy(dtype=float)
    return float(np.sqrt(np.mean(error**2)))


def _chronological_thirds(
    challenger: pd.DataFrame,
    baseline: pd.DataFrame,
) -> dict[str, float]:
    positions = np.array_split(np.arange(len(challenger)), 3)
    if any(len(values) == 0 for values in positions):
        raise ValueError("Bottleneck scoring requires at least three OOS rows")
    return {
        f"third_{i + 1}": _rmse(baseline.iloc[values]) - _rmse(challenger.iloc[values])
        for i, values in enumerate(positions)
    }


def score_bottleneck_pair(
    challenger: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    primary_block_size: int,
    sensitivity_block_sizes: tuple[int, ...],
    resamples: int,
    confidence: float,
    seed: int,
    minimum_relative_improvement: float = 0.01,
) -> dict[str, Any]:
    if not challenger.index.equals(baseline.index):
        raise ValueError("Bottleneck pair must use identical OOS months")
    challenger_metrics = evaluate_predictions(challenger)
    baseline_metrics = evaluate_predictions(baseline)
    baseline_rmse = float(baseline_metrics["rmse"])
    challenger_rmse = float(challenger_metrics["rmse"])
    if baseline_rmse <= 0.0:
        raise ValueError("Bottleneck baseline RMSE must be positive")
    relative = 1.0 - challenger_rmse / baseline_rmse
    primary = paired_block_bootstrap_rmse(
        challenger,
        baseline,
        block_size=primary_block_size,
        resamples=resamples,
        confidence=confidence,
        seed=seed,
    )
    sensitivities = {
        str(block): paired_block_bootstrap_rmse(
            challenger,
            baseline,
            block_size=block,
            resamples=resamples,
            confidence=confidence,
            seed=seed + block,
        )
        for block in sensitivity_block_sizes
    }
    thirds = _chronological_thirds(challenger, baseline)
    nonnegative_thirds = sum(value >= 0.0 for value in thirds.values())
    survives = bool(
        relative >= minimum_relative_improvement
        and float(primary["ci_lower"]) > 0.0
        and nonnegative_thirds >= 2
    )
    return {
        "challenger": challenger_metrics,
        "baseline": baseline_metrics,
        "relative_rmse_improvement": float(relative),
        "primary": primary,
        "sensitivities": sensitivities,
        "chronological_thirds_rmse_improvement": thirds,
        "nonnegative_chronological_thirds": nonnegative_thirds,
        "minimum_relative_improvement": minimum_relative_improvement,
        "survives_primary_rule": survives,
    }
