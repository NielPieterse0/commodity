from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

MONTH_CODES = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6, "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}
OUTRIGHT = re.compile(r"^NG([FGHJKMNQUVXZ])(\d{1,2})$")
SOURCE_BOUNDARY = pd.Timestamp("2017-05-21", tz="UTC")


def infer_delivery(symbol: str, trade_date: pd.Timestamp) -> pd.Timestamp | None:
    match = OUTRIGHT.fullmatch(str(symbol))
    if not match:
        return None
    month = MONTH_CODES[match.group(1)]
    year_code = match.group(2)
    candidate_years = [2000 + int(year_code)] if len(year_code) == 2 else [trade_date.year, trade_date.year + 1]
    for year in candidate_years:
        if len(year_code) == 1 and year % 10 != int(year_code):
            continue
        delivery = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
        months_ahead = (year - trade_date.year) * 12 + month - trade_date.month
        if 0 <= months_ahead <= 12:
            return delivery
    return None

def load_ohlcv(source_dir: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(source_dir.glob("*.ohlcv-1d.dbn.zst")):
        frame = db.DBNStore.from_file(path).to_df().reset_index()
        frame = frame.loc[frame["symbol"].astype(str).str.fullmatch(OUTRIGHT)].copy()
        frames.append(frame[["ts_event", "instrument_id", "symbol", "close", "volume"]])
    if not frames:
        raise RuntimeError(f"No OHLCV DBN files found under {source_dir}")
    bars = pd.concat(frames, ignore_index=True)
    bars["ts_event"] = pd.to_datetime(bars["ts_event"], utc=True)
    bars["delivery"] = [infer_delivery(s, d) for s, d in zip(bars["symbol"], bars["ts_event"])]
    bars = bars.dropna(subset=["delivery"]).copy()
    bars["contract"] = bars["delivery"].dt.strftime("NG-%Y-%m")
    bars = bars.sort_values(["contract", "ts_event"]).drop_duplicates(["contract", "ts_event"], keep="last")
    return bars


def attach_contract_returns_and_rank(bars: pd.DataFrame) -> pd.DataFrame:
    bars = bars.copy()
    bars["log_close"] = np.log(bars["close"].where(bars["close"] > 0))
    bars["log_return"] = bars.groupby("contract", sort=False)["log_close"].diff()
    bars["rank"] = bars.groupby("ts_event")["delivery"].rank(method="dense").astype(int)
    bars = bars.loc[bars["rank"] <= 12].copy()
    bars["source_era"] = np.where(bars["ts_event"] < SOURCE_BOUNDARY, "pre_boundary", "post_boundary")
    bars["delivery_month"] = bars["delivery"].dt.month.astype(int)
    return bars


def samuelson_summary(curve: pd.DataFrame) -> dict:
    returns = curve.dropna(subset=["log_return"])
    by_rank = returns.groupby("rank")["log_return"].agg(["count", "std"])
    by_rank["annualized_volatility"] = by_rank["std"] * math.sqrt(252)
    rank_vol = {str(int(i)): float(v) for i, v in by_rank["annualized_volatility"].dropna().items()}
    selected = {str(key): rank_vol.get(str(key)) for key in (1, 6, 12)}
    slope = float(np.polyfit(by_rank.index.astype(float), by_rank["annualized_volatility"], 1)[0])
    return {"by_rank": rank_vol, "observation_count_by_rank": {str(int(i)): int(v) for i, v in by_rank["count"].items()}, "selected": selected, "linear_slope_per_rank": slope}

def seasonal_curve_summary(curve: pd.DataFrame) -> dict:
    usable = curve.loc[curve["close"] > 0].copy()
    usable["log_close"] = np.log(usable["close"])
    usable["date_curve_mean"] = usable.groupby("ts_event")["log_close"].transform("mean")
    usable["relative_log_price"] = usable["log_close"] - usable["date_curve_mean"]
    monthly = usable.groupby("delivery_month")["relative_log_price"].agg(["count", "mean", "std"])
    winter = usable.loc[usable["delivery_month"].isin([12, 1, 2]), "relative_log_price"]
    injection = usable.loc[usable["delivery_month"].isin([5, 6, 7, 8, 9]), "relative_log_price"]
    return {
        "by_delivery_month": {
            str(int(i)): {"count": int(row["count"]), "mean_relative_log_price": float(row["mean"]), "std": float(row["std"])}
            for i, row in monthly.iterrows()
        },
        "winter_mean_relative_log_price": float(winter.mean()),
        "injection_mean_relative_log_price": float(injection.mean()),
        "winter_minus_injection": float(winter.mean() - injection.mean()),
    }


def build_result(curve: pd.DataFrame, source_dir: Path) -> dict:
    full = samuelson_summary(curve)
    eras = {era: samuelson_summary(part) for era, part in curve.groupby("source_era")}
    seasonal = seasonal_curve_summary(curve)
    selected = full["selected"]
    samuelson_pass = all(selected[str(k)] is not None for k in (1, 6, 12)) and selected["1"] > selected["6"] > selected["12"]
    era_pass = all(v["selected"]["1"] is not None and v["selected"]["12"] is not None and v["selected"]["1"] > v["selected"]["12"] for v in eras.values())
    seasonal_pass = seasonal["winter_minus_injection"] > 0
    return {
        "issue": 285,
        "authority": "exploratory_development_only",
        "data_semantics": "Databento GLBX.MDP3 ohlcv-1d UTC daily close; not official settlement",
        "source_dir": str(source_dir),
        "date_start": curve["ts_event"].min().isoformat(),
        "date_end": curve["ts_event"].max().isoformat(),
        "unique_dates": int(curve["ts_event"].nunique()),
        "unique_contracts": int(curve["contract"].nunique()),
        "attempts": [{"id": "primary_v1", "definition": "Outright NG contracts; infer next-12-month delivery from exchange symbol; contract-level close-to-close returns before same-date expiry ranking; M1-M12 retained.", "status": "executed"}],
        "samuelson_effect": {"full_sample": full, "source_eras": eras, "expected_direction_pass": samuelson_pass, "cross_era_direction_pass": era_pass},
        "seasonal_term_structure": {**seasonal, "expected_direction_pass": seasonal_pass},
    }

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    curve = attach_contract_returns_and_rank(load_ohlcv(args.source_dir))
    result = build_result(curve, args.source_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "unique_dates": result["unique_dates"],
        "samuelson_expected_direction_pass": result["samuelson_effect"]["expected_direction_pass"],
        "samuelson_cross_era_direction_pass": result["samuelson_effect"]["cross_era_direction_pass"],
        "seasonal_expected_direction_pass": result["seasonal_term_structure"]["expected_direction_pass"],
        "m1_m6_m12": result["samuelson_effect"]["full_sample"]["selected"],
        "winter_minus_injection": result["seasonal_term_structure"]["winter_minus_injection"],
    }, indent=2))


if __name__ == "__main__":
    main()
