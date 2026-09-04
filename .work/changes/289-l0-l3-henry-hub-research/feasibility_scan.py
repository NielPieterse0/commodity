from __future__ import annotations

import json
import zipfile
from collections import Counter
from pathlib import Path

import databento as db
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
WT = ROOT
SNAP = ROOT / "data" / "raw" / "snapshots"
OUT = ROOT / ".work" / "changes" / "289-l0-l3-henry-hub-research" / "feasibility-scan.json"


def date_text(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def ar1_neff(values: pd.Series) -> tuple[float, float]:
    series = values.dropna().astype(float)
    rho = float(series.autocorr(lag=1))
    return rho, float(len(series) * (1.0 - rho) / (1.0 + rho))


def load_weather() -> tuple[pd.DataFrame, dict[str, object]]:
    root = SNAP / "open_meteo_v1"
    files = sorted(root.glob("*/weather_features.csv"))
    frame = pd.concat([pd.read_csv(p).assign(snapshot=p.parent.name) for p in files], ignore_index=True)
    observed = pd.to_datetime(frame["observed_for"]).dt.date
    full = set(pd.date_range(min(observed), max(observed), freq="D").date)
    feature_cols = [c for c in frame if c.startswith("weather_")]
    summary = {
        "rows": len(frame),
        "coverage_start": min(observed).isoformat(),
        "coverage_end": max(observed).isoformat(),
        "missing_dates": sorted(d.isoformat() for d in full - set(observed)),
        "availability_status": frame["availability_status"].value_counts(dropna=False).to_dict(),
        "revision_status": frame["revision_status"].value_counts(dropna=False).to_dict(),
        "feature_missing_cells": int(frame[feature_cols].isna().sum().sum()),
        "rows_with_feature_missingness": int(frame[feature_cols].isna().any(axis=1).sum()),
        "unique_issued_at": int(frame["issued_at"].nunique()),
        "unique_available_at": int(frame["available_at"].nunique()),
    }
    return frame, summary


def load_cftc() -> tuple[pd.DataFrame, dict[str, object]]:
    root = SNAP / "cftc_cot"
    files = sorted(root.glob("*-disaggregated-futures-only/positioning_features.csv"))
    frame = pd.concat([pd.read_csv(p).assign(yearfile=p.parent.name) for p in files], ignore_index=True)
    observed = pd.to_datetime(frame["observed_for"], utc=True)
    frame = frame.assign(_observed_ts=observed).sort_values("_observed_ts")
    level_rho, level_neff = ar1_neff(frame["managed_money_net"])
    managed_money_change = frame["managed_money_net"].astype(float).diff()
    change_rho, change_neff = ar1_neff(managed_money_change)
    summary = {
        "rows": len(frame),
        "coverage_start": date_text(observed.min()),
        "coverage_end": date_text(observed.max()),
        "unique_observed_for": int(observed.nunique()),
        "year_counts": {str(k): int(v) for k, v in observed.dt.year.value_counts().sort_index().items()},
        "availability_status": frame["availability_status"].value_counts(dropna=False).to_dict(),
        "availability_basis": frame["availability_basis"].value_counts(dropna=False).to_dict(),
        "revision_status": frame["revision_status"].value_counts(dropna=False).to_dict(),
        "missing_cells": int(frame.drop(columns=["_observed_ts"]).isna().sum().sum()),
        "managed_money_net_dependence": {
            "level_rows": int(frame["managed_money_net"].notna().sum()),
            "level_ar1": level_rho,
            "level_ar1_effective_n": level_neff,
            "change_rows": int(managed_money_change.notna().sum()),
            "change_ar1": change_rho,
            "change_ar1_effective_n": change_neff,
        },
    }
    return frame.drop(columns=["_observed_ts"]), summary


def load_ng_definition_map() -> tuple[dict[int, tuple[str, pd.Timestamp]], int]:
    root = SNAP / "databento" / "ng-full-history-v1" / "definition" / "GLBX-20260813-4LWDSMFX5T"
    mapping: dict[int, tuple[str, pd.Timestamp]] = {}
    matched_records = 0
    for path in sorted(root.glob("*.definition.dbn.zst")):
        store = db.DBNStore.from_file(path)
        for chunk in store.to_df(map_symbols=False, count=250_000):
            keep = chunk[(chunk["asset"].astype(str) == "NG") & (chunk["instrument_class"].astype(str) == "F")]
            matched_records += len(keep)
            for instrument_id, raw_symbol, expiration in zip(
                keep["instrument_id"], keep["raw_symbol"], keep["expiration"], strict=False
            ):
                mapping[int(instrument_id)] = (str(raw_symbol), pd.Timestamp(expiration))
    return mapping, matched_records


def load_market_identity(mapping: dict[int, tuple[str, pd.Timestamp]]) -> tuple[pd.DataFrame, dict[str, object]]:
    root = SNAP / "databento" / "ng-full-history-v1" / "ohlcv-1d" / "GLBX-20260813-5T4KKKSNG9"
    frames: list[pd.DataFrame] = []
    total_rows = 0
    for path in sorted(root.glob("*.ohlcv-1d.dbn.zst")):
        store = db.DBNStore.from_file(path)
        frame = store.to_df(map_symbols=False).reset_index()
        total_rows += len(frame)
        frame = frame[frame["instrument_id"].astype(int).isin(mapping)].copy()
        frames.append(frame[["ts_event", "instrument_id"]])
    market = pd.concat(frames, ignore_index=True)
    market["trade_date"] = pd.to_datetime(market["ts_event"], utc=True).dt.date
    market["expiration"] = market["instrument_id"].astype(int).map(lambda x: mapping[x][1])
    market["raw_symbol"] = market["instrument_id"].astype(int).map(lambda x: mapping[x][0])
    trade_ts = pd.to_datetime(market["trade_date"].astype(str), utc=True)
    market = market[market["expiration"] >= trade_ts].copy()
    counts = market.groupby("trade_date")["expiration"].nunique().sort_index()
    month_has_13 = (
        counts[counts >= 13]
        .rename_axis("trade_date")
        .reset_index()
        .assign(month=lambda x: pd.to_datetime(x["trade_date"]).dt.to_period("M").astype(str))["month"]
        .nunique()
    )
    summary = {
        "all_ohlcv_rows": total_rows,
        "mapped_outright_rows": len(market),
        "trade_dates": int(counts.size),
        "coverage_start": min(counts.index).isoformat(),
        "coverage_end": max(counts.index).isoformat(),
        "days_ge_6_maturities": int((counts >= 6).sum()),
        "days_ge_12_maturities": int((counts >= 12).sum()),
        "days_ge_13_maturities": int((counts >= 13).sum()),
        "months_with_any_ge_13_day": int(month_has_13),
        "max_simultaneous_maturities": int(counts.max()),
        "unique_instruments_observed": int(market["instrument_id"].nunique()),
        "unique_raw_symbols_observed": int(market["raw_symbol"].nunique()),
    }
    return market, summary


def load_storage_history() -> dict[str, object]:
    path = SNAP / "eia_wngsr" / "2024-08-13_2026-08-12" / "ngshistory.xls"
    frame = pd.read_excel(path, sheet_name="html_report_history", header=6)
    frame = frame.rename(columns={"Week ending": "date", "Total Lower 48": "storage"})
    frame = frame[["date", "storage"]].dropna()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame[frame["date"] >= pd.Timestamp("2010-06-06")].copy()
    frame["week"] = frame["date"].dt.isocalendar().week.astype(int)
    frame["seasonal_norm"] = frame.groupby("week")["storage"].transform("mean")
    frame["storage_anomaly"] = frame["storage"].astype(float) - frame["seasonal_norm"].astype(float)
    rho, neff = ar1_neff(frame["storage_anomaly"])
    winter = frame[frame["date"].dt.month.isin([12, 1, 2])]
    return {
        "rows": len(frame),
        "coverage_start": date_text(frame["date"].min()),
        "coverage_end": date_text(frame["date"].max()),
        "months": int(frame["date"].dt.to_period("M").nunique()),
        "calendar_years": int(frame["date"].dt.year.nunique()),
        "winter_rows": len(winter),
        "winter_below_full_sample_mean_rows": int((winter["storage"] < frame["storage"].mean()).sum()),
        "winter_below_week_of_year_norm_rows": int((winter["storage_anomaly"] < 0).sum()),
        "storage_anomaly_ar1": rho,
        "storage_anomaly_ar1_effective_n": neff,
        "snapshot_semantics": "current_revised_history",
    }


def load_storage_events() -> tuple[pd.DataFrame, dict[str, object]]:
    path = SNAP / "eia_wngsr" / "2024-08-13_2026-08-12" / "storage_feature_events.csv"
    frame = pd.read_csv(path)
    release_col = "available_at" if "available_at" in frame else "release_at"
    release = pd.to_datetime(frame[release_col], utc=True)
    event_counts = frame["source_event_type"].value_counts(dropna=False).to_dict()
    release_mask = frame["source_event_type"].eq("release")
    summary = {
        "rows": len(frame),
        "release_rows": int(release_mask.sum()),
        "revision_rows": int(frame["source_event_type"].eq("revision").sum()),
        "weekly_change_nonmissing": int(frame["storage_weekly_change_bcf"].notna().sum()),
        "event_type_counts": event_counts,
        "release_coverage_start": date_text(release[release_mask].min()),
        "release_coverage_end": date_text(release[release_mask].max()),
        "release_weekdays": dict(Counter(release[release_mask].dt.day_name())),
        "missing_cells": int(frame.isna().sum().sum()),
    }
    return frame, summary


def load_fundamental_metadata() -> dict[str, object]:
    archive = SNAP / "eia" / "20260813-v1-ng-bulk" / "NG.zip"
    categories = ["production", "consumption", "exports", "imports", "lng", "henry hub", "electric power"]
    counts = Counter()
    starts: dict[str, list[str]] = {k: [] for k in categories}
    ends: dict[str, list[str]] = {k: [] for k in categories}
    total = 0
    with zipfile.ZipFile(archive) as zf, zf.open("NG.txt") as handle:
        for raw in handle:
            if b'"data":' not in raw:
                continue
            head = raw.split(b'"data":', 1)[0] + b'"data":[]}'
            meta = json.loads(head)
            total += 1
            text = (str(meta.get("name", "")) + " " + str(meta.get("description", ""))).lower()
            for category in categories:
                if category in text:
                    counts[category] += 1
                    starts[category].append(str(meta.get("start", "")))
                    ends[category].append(str(meta.get("end", "")))
    coverage = {
        category: {
            "series_count": int(counts[category]),
            "earliest_start": min(starts[category]) if starts[category] else None,
            "latest_end": max(ends[category]) if ends[category] else None,
        }
        for category in categories
    }
    return {"total_series": total, "category_coverage": coverage, "snapshot_semantics": "current_revised_history"}


def main() -> int:
    weather, weather_summary = load_weather()
    cftc, cftc_summary = load_cftc()
    mapping, definition_records = load_ng_definition_map()
    market, market_summary = load_market_identity(mapping)
    storage, storage_summary = load_storage_events()
    trade_dates = set(market["trade_date"])
    weather_dates = set(pd.to_datetime(weather["observed_for"]).dt.date)
    cftc_dates = set(pd.to_datetime(cftc["available_at"], utc=True).dt.date)
    storage_release_col = "available_at" if "available_at" in storage else "release_at"
    storage_releases = storage[storage["source_event_type"].eq("release")]
    storage_dates = set(pd.to_datetime(storage_releases[storage_release_col], utc=True).dt.date)
    joins = {
        "weather_exact_market_date": len(weather_dates & trade_dates),
        "weather_source_dates": len(weather_dates),
        "cftc_availability_exact_market_date": len(cftc_dates & trade_dates),
        "cftc_availability_dates": len(cftc_dates),
        "storage_release_exact_market_date": len(storage_dates & trade_dates),
        "storage_release_dates": len(storage_dates),
    }
    payload = {
        "schema_version": 1,
        "programme_id": "002-henry-hub-fresh",
        "scan_class": "non_outcome_source_identity_coverage_missingness_only",
        "outcome_effect_testing_performed": False,
        "protected_evidence_opened": False,
        "databento_definitions": {
            "matched_ng_outright_definition_records": definition_records,
            "unique_ng_outright_instrument_ids": len(mapping),
        },
        "market_identity": market_summary,
        "weather": weather_summary,
        "cftc": cftc_summary,
        "storage_events": storage_summary,
        "storage_history": load_storage_history(),
        "fundamentals": load_fundamental_metadata(),
        "joinability": joins,
        "notes": [
            "Market scan uses instrument identity, timestamps and expiration only; OHLC price fields are not used.",
            "Weather scan uses source timestamps, status fields and missingness only; weather values are not tested against market outcomes.",
            "CFTC dependence uses positioning values only to characterize effective information for power/design feasibility; positioning is not tested against market outcomes.",
            "Storage-history dependence uses storage values only to characterize effective information and scarcity-cell capacity; storage is not tested against market outcomes.",
            "EIA bulk scan reads series metadata only and does not test fundamental values against market outcomes.",
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(OUT),
        "market": market_summary,
        "weather": weather_summary,
        "cftc": cftc_summary,
        "storage": storage_summary,
        "joins": joins,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
