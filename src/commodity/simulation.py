from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def positions_from_forecasts(pred: pd.DataFrame, policy: dict[str, Any]) -> pd.Series:
    if not policy.get("enabled", False):
        raise RuntimeError("signal policy is disabled")
    if policy.get("type") != "prediction_sign":
        raise ValueError(f"unsupported signal policy type: {policy.get('type')}")
    scale = float(policy.get("position_scale", 1.0))
    return np.sign(pred["prediction"]).astype(float) * scale


def simulate_forecasts(
    pred: pd.DataFrame,
    policy: dict[str, Any],
    simulation: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, float]]:
    if not simulation.get("enabled", False):
        raise RuntimeError("simulation configuration is disabled")
    cost_model = simulation.get("cost_model", {})
    if cost_model.get("type") != "turnover_bps":
        raise ValueError(f"unsupported cost model type: {cost_model.get('type')}")

    position = positions_from_forecasts(pred, policy)
    turnover = position.diff().abs()
    if len(turnover):
        turnover.iloc[0] = abs(position.iloc[0])
    gross = position * pred["actual"]
    cost = turnover * float(cost_model["turnover_bps"]) / 10_000.0
    net = gross - cost
    path = pd.DataFrame({
        "prediction": pred["prediction"],
        "actual": pred["actual"],
        "position": position,
        "turnover": turnover,
        "gross_log_return": gross,
        "cost_log_return": cost,
        "net_log_return": net,
    }, index=pred.index)
    metrics = {
        "n": float(len(path)),
        "gross_log_return": float(gross.sum()),
        "net_log_return": float(net.sum()),
        "mean_turnover": float(turnover.mean()) if len(turnover) else 0.0,
        "total_cost_log_return": float(cost.sum()),
    }
    return path, metrics
