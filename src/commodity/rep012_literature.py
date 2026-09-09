from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.linalg import eig

ENDOGENOUS = ("ln_hh", "ln_wti")
STATIONARY_EXOGENOUS = (
    "hdds",
    "dev_hdds",
    "cdds",
    "dev_cdds",
    "stor_diff",
    "hurr_shutin_bcf",
)
REQUIRED_COLUMNS = ("week_no", "date", *ENDOGENOUS, *STATIONARY_EXOGENOUS)
VAR_LAGS = 5

TRACE_CRITICAL = {0.05: (15.41, 3.76), 0.01: (20.04, 6.65)}
MAX_CRITICAL = {0.05: (14.07, 3.76), 0.01: (18.63, 6.65)}

@dataclass(frozen=True)
class JohansenResult:
    sample: str
    with_exogenous: bool
    input_rows: int
    effective_rows: int
    eigenvalues: tuple[float, float]
    trace_statistics: tuple[float, float]
    max_eigen_statistics: tuple[float, float]
    beta: tuple[float, float]
    beta_se_wti: float
    alpha: tuple[float, float]
    alpha_se: tuple[float, float]
    rank_at_5pct: int
    rank_at_1pct: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class HenryHubEquationResult:
    with_exogenous: bool
    coefficients: dict[str, float]
    standard_errors: dict[str, float]
    z_statistics: dict[str, float]
    residual_standard_error: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_roberts_frame(path: str | Path) -> pd.DataFrame:
    frame = pd.read_stata(Path(path), convert_categoricals=False)
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Roberts dataset missing required columns: {missing}")
    if frame[list(REQUIRED_COLUMNS)].isna().any().any():
        raise ValueError("Roberts dataset contains missing values in required columns")
    frame = frame.copy()
    frame["date_dt"] = pd.to_datetime(frame["date"], format="%m/%d/%Y")
    return frame

def sample_mask(frame: pd.DataFrame, sample: str) -> np.ndarray:
    if sample == "brown_yucel":
        return frame["week_no"].to_numpy() < 523
    if sample == "full":
        return np.ones(len(frame), dtype=bool)
    if sample == "post_2007":
        return frame["week_no"].to_numpy() > 522
    raise ValueError(f"Unknown Roberts sample: {sample}")


def _residualize(values: np.ndarray, controls: np.ndarray) -> np.ndarray:
    coefficients = np.linalg.lstsq(controls, values, rcond=None)[0]
    return values - controls @ coefficients


def _selected_rank(
    trace_statistics: np.ndarray,
    max_statistics: np.ndarray,
    level: float,
) -> int:
    trace_critical = TRACE_CRITICAL[level]
    max_critical = MAX_CRITICAL[level]
    if trace_statistics[0] <= trace_critical[0] or max_statistics[0] <= max_critical[0]:
        return 0
    if trace_statistics[1] <= trace_critical[1] and max_statistics[1] <= max_critical[1]:
        return 1
    return 2

def estimate_roberts_johansen(
    frame: pd.DataFrame,
    sample: str,
    *,
    with_exogenous: bool,
    var_lags: int = VAR_LAGS,
) -> JohansenResult:
    if var_lags < 1:
        raise ValueError("var_lags must be positive")
    y = frame[list(ENDOGENOUS)].to_numpy(dtype=float)
    dy = np.diff(y, axis=0)
    mask = sample_mask(frame, sample)
    selected = np.flatnonzero(mask)
    rows = selected[selected >= var_lags]
    if len(rows) <= 0:
        raise ValueError("Sample has no estimable observations")

    current_difference = dy[rows - 1]
    lagged_level = y[rows - 1]
    controls = np.column_stack(
        [dy[rows - 1 - lag] for lag in range(1, var_lags)]
    )
    if with_exogenous:
        controls = np.column_stack(
            [controls, frame[list(STATIONARY_EXOGENOUS)].to_numpy(dtype=float)[rows]]
        )
    controls = np.column_stack([controls, np.ones(len(rows))])

    r0 = _residualize(current_difference, controls)
    r1 = _residualize(lagged_level, controls)
    effective_rows = len(rows)
    s00 = r0.T @ r0 / effective_rows
    s11 = r1.T @ r1 / effective_rows
    s01 = r0.T @ r1 / effective_rows

    eigenvalues, eigenvectors = eig(s01.T @ np.linalg.inv(s00) @ s01, s11)
    eigenvalues = np.real(eigenvalues)
    eigenvectors = np.real(eigenvectors)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]

    trace_statistics = np.array(
        [-effective_rows * np.log(1.0 - eigenvalues[rank:]).sum() for rank in range(2)]
    )
    max_statistics = -effective_rows * np.log(1.0 - eigenvalues)

    beta = eigenvectors[:, 0] / eigenvectors[0, 0]
    beta_variance_scale = float((beta[None, :] @ s11 @ beta[:, None]).item())
    alpha = (s01 @ beta[:, None] / beta_variance_scale).reshape(-1)

    error_correction = lagged_level @ beta
    vec_controls = np.column_stack([error_correction, controls])
    vec_coefficients = np.linalg.lstsq(vec_controls, current_difference, rcond=None)[0]
    vec_residuals = current_difference - vec_controls @ vec_coefficients
    degrees_of_freedom = effective_rows - vec_controls.shape[1]
    if degrees_of_freedom <= 0:
        raise ValueError("Insufficient residual degrees of freedom")
    vec_covariance = vec_residuals.T @ vec_residuals / degrees_of_freedom
    design_inverse = np.linalg.inv(vec_controls.T @ vec_controls)
    alpha_se = np.sqrt(np.diag(vec_covariance) * design_inverse[0, 0])

    omega = s00 - (
        s01 @ beta[:, None] @ beta[None, :] @ s01.T / beta_variance_scale
    )
    alpha_information = float((alpha[None, :] @ np.linalg.inv(omega) @ alpha[:, None]).item())
    beta_se_wti = float(
        np.sqrt(1.0 / degrees_of_freedom / alpha_information / s11[1, 1])
    )

    return JohansenResult(
        sample=sample,
        with_exogenous=with_exogenous,
        input_rows=int(mask.sum()),
        effective_rows=effective_rows,
        eigenvalues=tuple(float(value) for value in eigenvalues),
        trace_statistics=tuple(float(value) for value in trace_statistics),
        max_eigen_statistics=tuple(float(value) for value in max_statistics),
        beta=tuple(float(value) for value in beta),
        beta_se_wti=beta_se_wti,
        alpha=tuple(float(value) for value in alpha),
        alpha_se=tuple(float(value) for value in alpha_se),
        rank_at_5pct=_selected_rank(trace_statistics, max_statistics, 0.05),
        rank_at_1pct=_selected_rank(trace_statistics, max_statistics, 0.01),
    )


def run_roberts_reproduction(path: str | Path) -> dict[str, object]:
    frame = load_roberts_frame(path)
    results: dict[str, dict[str, object]] = {}
    for sample in ("brown_yucel", "full", "post_2007"):
        results[sample] = {}
        for with_exogenous in (False, True):
            key = "with_exogenous" if with_exogenous else "without_exogenous"
            result = estimate_roberts_johansen(
                frame,
                sample,
                with_exogenous=with_exogenous,
            )
            results[sample][key] = result.to_dict()
    return {
        "dataset_rows": len(frame),
        "date_start": frame["date_dt"].min().date().isoformat(),
        "date_end": frame["date_dt"].max().date().isoformat(),
        "var_lags": VAR_LAGS,
        "vec_lagged_differences": VAR_LAGS - 1,
        "results": results,
        "henry_hub_equations": {
            "without_exogenous": estimate_roberts_henry_hub_equation(
                frame, with_exogenous=False
            ).to_dict(),
            "with_exogenous": estimate_roberts_henry_hub_equation(
                frame, with_exogenous=True
            ).to_dict(),
        },
    }


def estimate_roberts_henry_hub_equation(
    frame: pd.DataFrame,
    *,
    with_exogenous: bool,
    var_lags: int = VAR_LAGS,
) -> HenryHubEquationResult:
    johansen = estimate_roberts_johansen(
        frame,
        "brown_yucel",
        with_exogenous=with_exogenous,
        var_lags=var_lags,
    )
    y = frame[list(ENDOGENOUS)].to_numpy(dtype=float)
    dy = np.diff(y, axis=0)
    rows = np.flatnonzero(sample_mask(frame, "brown_yucel"))
    rows = rows[rows >= var_lags]
    current_difference = dy[rows - 1]
    lagged_level = y[rows - 1]

    lagged_blocks = [dy[rows - 1 - lag] for lag in range(1, var_lags)]
    controls = np.column_stack(lagged_blocks)
    control_names = [
        name
        for lag in range(1, var_lags)
        for name in (f"dln_hh_l{lag}", f"dln_wti_l{lag}")
    ]
    if with_exogenous:
        controls = np.column_stack(
            [controls, frame[list(STATIONARY_EXOGENOUS)].to_numpy(dtype=float)[rows]]
        )
        control_names.extend(STATIONARY_EXOGENOUS)
    controls = np.column_stack([controls, np.ones(len(rows))])
    control_names.append("constant")

    error_correction = lagged_level @ np.asarray(johansen.beta)
    design = np.column_stack([error_correction, controls])
    names = ["error_correction", *control_names]
    coefficients = np.linalg.lstsq(design, current_difference, rcond=None)[0]
    residuals = current_difference - design @ coefficients
    degrees_of_freedom = len(rows) - design.shape[1]
    variance = float(residuals[:, 0] @ residuals[:, 0] / degrees_of_freedom)
    standard_errors = np.sqrt(variance * np.diag(np.linalg.inv(design.T @ design)))
    hh_coefficients = coefficients[:, 0]
    z_statistics = hh_coefficients / standard_errors

    return HenryHubEquationResult(
        with_exogenous=with_exogenous,
        coefficients=dict(zip(names, map(float, hh_coefficients), strict=True)),
        standard_errors=dict(zip(names, map(float, standard_errors), strict=True)),
        z_statistics=dict(zip(names, map(float, z_statistics), strict=True)),
        residual_standard_error=float(np.sqrt(variance)),
    )
