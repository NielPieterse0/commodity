from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PHYSICAL_FEATURES = (
    "feature_fund_log_production",
    "feature_fund_log_storage",
    "feature_fund_log_consumption",
)


class Phase3FundamentalsError(ValueError):
    """Raised when the frozen Phase-3 fundamentals contract cannot be satisfied."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _month_end_2359(periods: pd.PeriodIndex) -> pd.DatetimeIndex:
    return periods.to_timestamp(how="end").tz_localize("UTC").normalize() + pd.Timedelta(
        hours=23, minutes=59
    )

def _read_physical_member(source_package: Path, member_path: str) -> bytes:
    package = Path(source_package)
    if package.is_dir():
        path = package / Path(member_path)
        if not path.is_file():
            raise Phase3FundamentalsError(f"physical source member is missing: {member_path}")
        return path.read_bytes()
    if not package.is_file():
        raise Phase3FundamentalsError("BHLR physical source package is unavailable")
    with zipfile.ZipFile(package) as archive:
        try:
            return archive.read(member_path)
        except KeyError as exc:
            raise Phase3FundamentalsError(
                f"physical source member is missing: {member_path}"
            ) from exc


def load_bhlr_physical_vintages(
    source_package: Path, cfg: dict[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    source = cfg["source"]
    member_cfg = source["members"]
    matrices: dict[str, np.ndarray] = {}
    hashes: dict[str, str] = {}
    for key in ("production", "storage", "consumption"):
        item = member_cfg[key]
        raw = _read_physical_member(Path(source_package), str(item["path"]))
        digest = _sha256(raw)
        if digest != str(item["sha256"]):
            raise Phase3FundamentalsError(f"{key} source member hash mismatch")
        matrices[key] = np.loadtxt(io.BytesIO(raw))
        hashes[key] = digest
    shapes = {value.shape for value in matrices.values()}
    if len(shapes) != 1:
        raise Phase3FundamentalsError("physical vintage matrices must have identical shapes")

    first = pd.Period(str(source["first_vintage_month"]), freq="M")
    cutoff = pd.Period(str(cfg["evidence_boundary"]["last_allowed_trade_date"])[:7], freq="M")
    periods = pd.period_range(first, cutoff, freq="M")
    start_row = int(source["first_origin_row"])
    start_col = int(source["first_origin_column"])
    rows = np.arange(start_row, start_row + len(periods))
    cols = np.arange(start_col, start_col + len(periods))
    row_count, col_count = next(iter(shapes))
    if not len(periods) or rows[-1] >= row_count or cols[-1] >= col_count:
        raise Phase3FundamentalsError("physical vintage range exceeds matrix coverage")

    values: dict[str, np.ndarray] = {}
    for key, matrix in matrices.items():
        diagonal = matrix[rows, cols].astype(float)
        if (~np.isfinite(diagonal)).any() or (diagonal <= 0.0).any():
            raise Phase3FundamentalsError(f"{key} contains invalid frozen PIT values")
        values[key] = np.log(diagonal)

    frame = pd.DataFrame(
        {
            "origin_month": periods.astype(str),
            "available_at": _month_end_2359(periods),
            "feature_fund_log_production": values["production"],
            "feature_fund_log_storage": values["storage"],
            "feature_fund_log_consumption": values["consumption"],
        }
    )
    provenance = {
        "source_role": "predictor_only_bhlr_realtime_nowcasts",
        "member_sha256": hashes,
        "rows": len(frame),
        "first_origin_month": str(periods[0]),
        "last_origin_month": str(periods[-1]),
        "availability_rule": "origin_month_end_2359_utc",
    }
    return frame, provenance

def augment_market_features_with_physical(
    market: pd.DataFrame,
    physical: pd.DataFrame,
    *,
    cutoff: str = "2022-12-31",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required_market = {"trade_date", "available_at"}
    required_physical = {"origin_month", "available_at", *PHYSICAL_FEATURES}
    if not required_market.issubset(market.columns):
        raise Phase3FundamentalsError("market feature frame is missing PIT columns")
    if not required_physical.issubset(physical.columns):
        raise Phase3FundamentalsError("physical feature frame is incomplete")
    left = market.copy()
    left["trade_date"] = pd.to_datetime(left["trade_date"], utc=True)
    left["available_at"] = pd.to_datetime(left["available_at"], utc=True)
    cutoff_ts = pd.Timestamp(cutoff, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    if left["trade_date"].max() > cutoff_ts:
        raise Phase3FundamentalsError("market feature frame crossed protected cutoff")
    right = physical.copy().rename(columns={"available_at": "physical_available_at", "origin_month": "physical_origin_month"})
    right["physical_available_at"] = pd.to_datetime(right["physical_available_at"], utc=True)
    joined = pd.merge_asof(
        left.sort_values("available_at"),
        right.sort_values("physical_available_at"),
        left_on="available_at",
        right_on="physical_available_at",
        direction="backward",
        allow_exact_matches=False,
    ).sort_values("trade_date").reset_index(drop=True)
    missing = joined[list(PHYSICAL_FEATURES)].isna().any(axis=1)
    if (~missing & (joined["physical_available_at"] >= joined["available_at"])).any():
        raise Phase3FundamentalsError("physical PIT join crossed its strict availability boundary")
    age_days = (
        joined.loc[~missing, "available_at"]
        - joined.loc[~missing, "physical_available_at"]
    ).dt.total_seconds() / 86400.0
    diagnostics = {
        "rows": len(joined),
        "missing_rows": int(missing.sum()),
        "coverage_fraction": float((~missing).mean()) if len(joined) else 0.0,
        "age_days_min": None if age_days.empty else float(age_days.min()),
        "age_days_max": None if age_days.empty else float(age_days.max()),
        "age_days_median": None if age_days.empty else float(age_days.median()),
    }
    return joined, diagnostics


def decide_phase3_survival(
    *,
    baseline_pnl: float,
    baseline_drawdown: float,
    challenger_pnl: float,
    challenger_drawdown: float,
    block_deltas: list[float],
) -> dict[str, Any]:
    repeatable = sum(float(value) >= 0.0 for value in block_deltas) >= 2
    economic = float(challenger_pnl) > float(baseline_pnl) and repeatable
    risk = (
        float(challenger_pnl) >= 0.95 * float(baseline_pnl)
        and float(challenger_drawdown) <= 0.80 * float(baseline_drawdown)
        and repeatable
    )
    route = "economic" if economic else "risk" if risk else "rejected"
    return {
        "retained": bool(economic or risk),
        "route": route,
        "economic_survive": bool(economic),
        "risk_survive": bool(risk),
        "nonnegative_incremental_outer_blocks": int(
            sum(float(value) >= 0.0 for value in block_deltas)
        ),
    }
