from __future__ import annotations

from collections.abc import Collection
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import f as f_distribution

_REQUIRED = {"trade_date", "contract_id", "expiration", "settle"}


def _prepare_contracts(contracts: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_REQUIRED - set(contracts.columns))
    if missing:
        raise ValueError(f"contract frame missing required fields: {missing}")
    out = contracts[list(_REQUIRED)].copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], utc=True)
    out["expiration"] = pd.to_datetime(out["expiration"], utc=True)
    out["settle"] = pd.to_numeric(out["settle"], errors="coerce")
    out = out.loc[out["settle"].gt(0.0)].copy()
    if out.duplicated(["trade_date", "contract_id"]).any():
        raise ValueError("contract frame has duplicate contract-day keys")
    return out.sort_values(["trade_date", "expiration", "contract_id"])


def _ranked_same_contract_returns(
    contracts: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.Index]:
    prepared = _prepare_contracts(contracts)
    sessions = pd.Index(sorted(prepared["trade_date"].unique()))
    session_position = pd.Series(np.arange(len(sessions)), index=sessions)
    prepared["session_position"] = prepared["trade_date"].map(session_position)
    prepared = prepared.sort_values(["contract_id", "trade_date"])
    groups = prepared.groupby("contract_id", sort=False)
    prepared["previous_session_position"] = groups["session_position"].shift()
    prepared["previous_settle"] = groups["settle"].shift()
    prepared["return"] = np.log(prepared["settle"] / prepared["previous_settle"])
    prepared["adjacent_return"] = (
        prepared["session_position"] - prepared["previous_session_position"]
    ).eq(1.0)
    prepared = prepared.sort_values(["trade_date", "expiration", "contract_id"])
    prepared["maturity_rank"] = prepared.groupby("trade_date").cumcount() + 1
    prepared = prepared.loc[
        prepared["trade_date"].lt(pd.Timestamp(cutoff)) & prepared["adjacent_return"]
    ].copy()
    return prepared, sessions


def build_mu_return_series(
    contracts: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    ranked, _ = _ranked_same_contract_returns(contracts, cutoff=cutoff)
    near = ranked.loc[ranked["maturity_rank"].eq(1)].copy()
    second = ranked.loc[ranked["maturity_rank"].eq(2)].copy()
    near = near[["trade_date", "contract_id", "return"]].rename(
        columns={"contract_id": "near_contract_id", "return": "near_return"}
    )
    second = second[["trade_date", "contract_id", "return"]].rename(
        columns={"contract_id": "second_contract_id", "return": "second_return"}
    )
    paired = near.merge(second, on="trade_date", how="inner", validate="one_to_one")
    last_dates = _prepare_contracts(contracts).groupby("contract_id")["trade_date"].max()
    paired["near_final_trading_day"] = [
        trade_date == last_dates.loc[contract_id]
        for trade_date, contract_id in zip(
            paired["trade_date"], paired["near_contract_id"], strict=True
        )
    ]
    paired["ret1"] = paired["near_return"].where(
        ~paired["near_final_trading_day"], paired["second_return"]
    )
    paired["ret2"] = paired["second_return"]
    paired["ret1_source_rank"] = np.where(paired["near_final_trading_day"], 2, 1)
    paired["ret1_contract_id"] = paired["near_contract_id"].where(
        ~paired["near_final_trading_day"], paired["second_contract_id"]
    )
    paired["ret2_contract_id"] = paired["second_contract_id"]
    return paired[
        [
            "trade_date",
            "ret1",
            "ret2",
            "ret1_source_rank",
            "ret1_contract_id",
            "ret2_contract_id",
            "near_final_trading_day",
        ]
    ].reset_index(drop=True)


def mu_unconditional_test(series: pd.DataFrame) -> dict[str, float | int]:
    ret1 = series["ret1"].to_numpy(dtype=float)
    ret2 = series["ret2"].to_numpy(dtype=float)
    var1 = float(np.var(ret1, ddof=1))
    var2 = float(np.var(ret2, ddof=1))
    ratio = var1 / var2
    return {
        "observations": len(series),
        "ret1_std": float(np.sqrt(var1)),
        "ret2_std": float(np.sqrt(var2)),
        "variance_ratio_ret1_over_ret2": ratio,
        "one_sided_f_pvalue": float(f_distribution.sf(ratio, len(ret1) - 1, len(ret2) - 1)),
    }


def _garch_unwrap(raw: np.ndarray) -> tuple[float, float, float, float]:
    mean = float(raw[0])
    omega = float(np.exp(raw[1]))
    alpha = float(0.999 * expit(raw[2]))
    beta = float((0.999 - alpha) * expit(raw[3]))
    return mean, omega, alpha, beta


def _garch_path(
    returns_percent: np.ndarray,
    raw: np.ndarray,
    initial_variance: float,
) -> tuple[np.ndarray, np.ndarray]:
    mean, omega, alpha, beta = _garch_unwrap(raw)
    residual = returns_percent - mean
    variance = np.empty_like(returns_percent)
    variance[0] = initial_variance
    for index in range(1, len(returns_percent)):
        variance[index] = (
            omega
            + alpha * residual[index - 1] ** 2
            + beta * variance[index - 1]
        )
    return residual, variance


def fit_gaussian_garch(returns: Collection[float]) -> dict[str, Any]:
    values = np.asarray(list(returns), dtype=float) * 100.0
    if len(values) < 50 or not np.isfinite(values).all():
        raise ValueError("GARCH fit requires at least 50 finite returns")
    initial_variance = float(np.var(values, ddof=1))
    def objective(raw: np.ndarray) -> float:
        residual, variance = _garch_path(values, raw, initial_variance)
        if not np.isfinite(variance).all() or np.any(variance <= 1e-10):
            return 1e30
        return float(
            0.5
            * np.sum(
                np.log(2.0 * np.pi)
                + np.log(variance)
                + residual**2 / variance
            )
        )

    fits = []
    for alpha, beta in ((0.05, 0.90), (0.10, 0.80), (0.15, 0.75)):
        alpha_raw = np.log((alpha / 0.999) / (1.0 - alpha / 0.999))
        beta_share = beta / (0.999 - alpha)
        beta_raw = np.log(beta_share / (1.0 - beta_share))
        omega = max(initial_variance * (1.0 - alpha - beta), 1e-8)
        start = np.array([values.mean(), np.log(omega), alpha_raw, beta_raw])
        fits.append(
            minimize(
                objective,
                start,
                method="L-BFGS-B",
                options={"maxiter": 2000, "ftol": 1e-12},
            )
        )
    fit = min(fits, key=lambda candidate: candidate.fun)
    mean, omega, alpha, beta = _garch_unwrap(fit.x)
    _, variance = _garch_path(values, fit.x, initial_variance)
    return {
        "converged": bool(fit.success),
        "optimizer_message": str(fit.message),
        "negative_log_likelihood": float(fit.fun),
        "mean_percent": mean,
        "omega": omega,
        "alpha": alpha,
        "beta": beta,
        "persistence": alpha + beta,
        "conditional_variance": variance,
        "return_scale": "percent",
    }


def mu_garch_test(series: pd.DataFrame) -> dict[str, Any]:
    ret1_fit = fit_gaussian_garch(series["ret1"])
    ret2_fit = fit_gaussian_garch(series["ret2"])
    h1 = np.asarray(ret1_fit.pop("conditional_variance"), dtype=float)
    h2 = np.asarray(ret2_fit.pop("conditional_variance"), dtype=float)
    dominance = h1 > h2
    return {
        "ret1_fit": ret1_fit,
        "ret2_fit": ret2_fit,
        "paired_conditional_variance_dates": len(h1),
        "h1_gt_h2_count": int(dominance.sum()),
        "h1_gt_h2_fraction": float(dominance.mean()),
        "mean_h1_percent_squared": float(h1.mean()),
        "mean_h2_percent_squared": float(h2.mean()),
    }


def build_ergen_maturity_panel(
    contracts: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
    storage_report_dates: Collection[pd.Timestamp] | None = None,
) -> pd.DataFrame:
    ranked, sessions = _ranked_same_contract_returns(contracts, cutoff=cutoff)
    front = ranked.loc[ranked["maturity_rank"].eq(1)].copy()
    expiration_days = front["expiration"].dt.floor("D").to_numpy(dtype="datetime64[ns]")
    session_days = sessions.to_numpy(dtype="datetime64[ns]")
    expiration_positions = np.searchsorted(session_days, expiration_days, side="left")
    front["ttm_business_days"] = expiration_positions - front["session_position"].to_numpy()
    if (front["ttm_business_days"] < 0).any():
        raise ValueError("nearby contract has negative time to maturity")
    front["monday"] = front["trade_date"].dt.weekday.eq(0).astype(float)
    front["winter"] = front["trade_date"].dt.month.isin([12, 1, 2]).astype(float)
    if storage_report_dates is None:
        front["storage_report_day"] = front["trade_date"].dt.weekday.eq(3).astype(float)
    else:
        normalized = {
            pd.Timestamp(value).tz_convert("UTC").floor("D")
            if pd.Timestamp(value).tzinfo is not None
            else pd.Timestamp(value).tz_localize("UTC").floor("D")
            for value in storage_report_dates
        }
        front["storage_report_day"] = front["trade_date"].isin(normalized).astype(float)
    front["ttm_winter"] = front["ttm_business_days"] * front["winter"]
    return front[
        [
            "trade_date",
            "contract_id",
            "expiration",
            "return",
            "storage_report_day",
            "monday",
            "winter",
            "ttm_business_days",
            "ttm_winter",
        ]
    ].reset_index(drop=True)


def _garchx_unwrap(raw: np.ndarray) -> tuple[float, float, float, np.ndarray]:
    omega = float(raw[0])
    alpha = float(0.999 * expit(raw[1]))
    beta = float((0.999 - alpha) * expit(raw[2]))
    return omega, alpha, beta, np.asarray(raw[3:], dtype=float)


def _garchx_path(
    returns_percent: np.ndarray,
    exog: np.ndarray,
    raw: np.ndarray,
    initial_variance: float,
) -> np.ndarray:
    omega, alpha, beta, gamma = _garchx_unwrap(raw)
    variance = np.empty_like(returns_percent)
    variance[0] = initial_variance
    for index in range(1, len(returns_percent)):
        variance[index] = (
            omega
            + alpha * returns_percent[index - 1] ** 2
            + beta * variance[index - 1]
            + float(exog[index] @ gamma)
        )
    return variance


def _scale_garchx_exog(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if matrix.ndim != 2 or matrix.shape[1] == 0:
        raise ValueError("GARCH-X exogenous matrix must be two-dimensional and non-empty")
    scales = np.maximum(np.max(np.abs(matrix), axis=0), 1.0)
    return matrix / scales, scales


def _numerical_hessian(objective: Any, point: np.ndarray) -> np.ndarray:
    size = len(point)
    hessian = np.zeros((size, size), dtype=float)
    steps = 1e-4 * np.maximum(1.0, np.abs(point))
    center = float(objective(point))
    for row in range(size):
        row_step = np.zeros(size)
        row_step[row] = steps[row]
        hessian[row, row] = (
            objective(point + row_step) - 2.0 * center + objective(point - row_step)
        ) / steps[row] ** 2
        for column in range(row + 1, size):
            column_step = np.zeros(size)
            column_step[column] = steps[column]
            value = (
                objective(point + row_step + column_step)
                - objective(point + row_step - column_step)
                - objective(point - row_step + column_step)
                + objective(point - row_step - column_step)
            ) / (4.0 * steps[row] * steps[column])
            hessian[row, column] = value
            hessian[column, row] = value
    return hessian


def fit_zero_mean_garchx(
    returns: Collection[float],
    exog: pd.DataFrame,
) -> dict[str, Any]:
    values = np.asarray(list(returns), dtype=float) * 100.0
    matrix = exog.to_numpy(dtype=float)
    if len(values) < 100 or matrix.shape[0] != len(values):
        raise ValueError("GARCH-X fit requires aligned returns/exogenous rows")
    if not np.isfinite(values).all() or not np.isfinite(matrix).all():
        raise ValueError("GARCH-X inputs must be finite")
    scaled_matrix, exog_scales = _scale_garchx_exog(matrix)
    initial_variance = float(np.var(values, ddof=1))

    def objective(raw: np.ndarray) -> float:
        variance = _garchx_path(values, scaled_matrix, raw, initial_variance)
        safe_variance = np.maximum(variance, 1e-8)
        invalid = np.minimum(variance - 1e-8, 0.0)
        penalty = 1e8 * float(np.dot(invalid, invalid))
        likelihood = 0.5 * np.sum(
            np.log(2.0 * np.pi) + np.log(safe_variance) + values**2 / safe_variance
        )
        return float(likelihood + penalty)

    fits = []
    for alpha, beta in ((0.05, 0.90), (0.10, 0.80), (0.15, 0.75)):
        alpha_raw = np.log((alpha / 0.999) / (1.0 - alpha / 0.999))
        beta_share = beta / (0.999 - alpha)
        beta_raw = np.log(beta_share / (1.0 - beta_share))
        omega = initial_variance * (1.0 - alpha - beta)
        start = np.r_[omega, alpha_raw, beta_raw, np.zeros(matrix.shape[1])]
        bound = 2.0 * max(initial_variance, 1.0)
        bounds = [(1e-8, bound), (-10.0, 10.0), (-10.0, 10.0)]
        bounds.extend(
            [(-bound * scale, bound * scale) for scale in exog_scales]
        )
        fits.append(
            minimize(
                objective,
                start,
                method="L-BFGS-B",
                bounds=bounds,
                options={"maxiter": 4000, "ftol": 1e-12, "gtol": 1e-7},
            )
        )
    converged_fits = [candidate for candidate in fits if candidate.success]
    fit = min(converged_fits or fits, key=lambda candidate: candidate.fun)
    omega, alpha, beta, scaled_gamma = _garchx_unwrap(fit.x)
    gamma = scaled_gamma / exog_scales
    variance = _garchx_path(values, scaled_matrix, fit.x, initial_variance)
    hessian = _numerical_hessian(objective, fit.x)
    scaled_covariance = np.linalg.pinv(hessian)
    transform = np.ones(len(fit.x), dtype=float)
    transform[3:] = 1.0 / exog_scales
    covariance = scaled_covariance * np.outer(transform, transform)
    standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    gamma_se = standard_errors[3:]
    gamma_result = {
        name: {
            "coefficient": float(coefficient),
            "standard_error": float(error),
            "z_stat": float(coefficient / error) if error > 0.0 else None,
        }
        for name, coefficient, error in zip(
            exog.columns, gamma, gamma_se, strict=True
        )
    }
    return {
        "converged": bool(fit.success),
        "optimizer_message": str(fit.message),
        "negative_log_likelihood": float(fit.fun),
        "omega": omega,
        "alpha": alpha,
        "beta": beta,
        "persistence": alpha + beta,
        "gamma": gamma_result,
        "exog_optimizer_scales": {
            name: float(scale) for name, scale in zip(exog.columns, exog_scales, strict=True)
        },
        "raw_covariance": covariance,
        "conditional_variance": variance,
        "minimum_conditional_variance": float(variance.min()),
        "return_scale": "percent",
    }


def fit_ergen_maturity_models(panel: pd.DataFrame) -> dict[str, Any]:
    base_columns = ["storage_report_day", "monday", "winter", "ttm_business_days"]
    interaction_columns = [*base_columns, "ttm_winter"]
    model5 = fit_zero_mean_garchx(panel["return"], panel[base_columns])
    model6 = fit_zero_mean_garchx(panel["return"], panel[interaction_columns])
    covariance6 = np.asarray(model6.pop("raw_covariance"), dtype=float)
    model5.pop("raw_covariance")
    model5.pop("conditional_variance")
    model6.pop("conditional_variance")
    ttm = model6["gamma"]["ttm_business_days"]
    ttm_winter = model6["gamma"]["ttm_winter"]
    ttm_index = 3 + interaction_columns.index("ttm_business_days")
    interaction_index = 3 + interaction_columns.index("ttm_winter")
    combined_coefficient = ttm["coefficient"] + ttm_winter["coefficient"]
    combined_variance = (
        covariance6[ttm_index, ttm_index]
        + covariance6[interaction_index, interaction_index]
        + 2.0 * covariance6[ttm_index, interaction_index]
    )
    combined_se = float(np.sqrt(max(combined_variance, 0.0)))
    combined_z = combined_coefficient / combined_se if combined_se > 0.0 else None
    model5_ttm = model5["gamma"]["ttm_business_days"]
    source_pattern = bool(
        model5["converged"]
        and model6["converged"]
        and model5["minimum_conditional_variance"] > 0.0
        and model6["minimum_conditional_variance"] > 0.0
        and model5_ttm["coefficient"] < 0.0
        and model5_ttm["z_stat"] is not None
        and model5_ttm["z_stat"] < -1.645
        and ttm["z_stat"] is not None
        and abs(ttm["z_stat"]) < 1.96
        and combined_z is not None
        and combined_z < -1.645
    )
    return {
        "model5_without_winter_interaction": model5,
        "model6_with_winter_interaction": model6,
        "winter_ttm_effect": {
            "coefficient": float(combined_coefficient),
            "standard_error": combined_se,
            "z_stat": float(combined_z) if combined_z is not None else None,
        },
        "source_pattern_reproduced": source_pattern,
    }
