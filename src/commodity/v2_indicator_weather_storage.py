from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from commodity.availability import resolve_wngsr_release
from commodity.v2_indicator_contract import (
    IndicatorContractError,
    PinnedSourcePolicy,
    _accepted_source_ids,
    _eligible_before,
    _finite,
    _require_accepted_source,
    _require_columns,
    _require_fresh_current_state,
    _source_settings,
)


def _weather_source_settings(
    policy: PinnedSourcePolicy,
) -> tuple[list[str], int, int, float, int]:
    weather = policy.payload.get("sources", {}).get("weather")
    if not isinstance(weather, Mapping):
        raise IndicatorContractError("pinned source policy is missing sources.weather")
    try:
        anchors = [str(anchor["id"]) for anchor in weather["v1_anchors"]]
        lead_start, lead_end = [
            int(value) for value in weather["v1_feature_lead_hours"]
        ]
        degree_day_base = float(weather["v1_degree_day_base_c"])
        cycle_hour = int(weather["v1_run_cycle_utc_hour"])
    except (KeyError, TypeError, ValueError) as exc:
        raise IndicatorContractError(
            "pinned weather source settings are incomplete"
        ) from exc
    if len(anchors) != 4 or len(set(anchors)) != 4:
        raise IndicatorContractError(
            "#83 weather requires the existing four fixed anchors"
        )
    if lead_end <= lead_start:
        raise IndicatorContractError("weather lead window is invalid")
    return anchors, lead_start, lead_end, degree_day_base, cycle_hour


def build_weather_revision(
    hourly: pd.DataFrame,
    prediction_time: Any,
    source_policy: PinnedSourcePolicy,
) -> dict[str, float]:
    required = (
        "run_id",
        "issued_at",
        "available_at",
        "anchor_id",
        "forecast_valid_at",
        "temperature_2m",
        "source_id",
    )
    _require_columns(hourly, required, label="weather hourly input")
    eligible, cutoff = _eligible_before(
        hourly, prediction_time, label="weather hourly input"
    )
    _require_accepted_source(
        eligible, source_policy, "weather", label="weather hourly input"
    )
    if eligible.empty:
        raise IndicatorContractError(
            "no weather run is eligible at the prediction cutoff"
        )
    eligible["issued_at"] = pd.to_datetime(
        eligible["issued_at"], utc=True, errors="coerce"
    )
    eligible["forecast_valid_at"] = pd.to_datetime(
        eligible["forecast_valid_at"], utc=True, errors="coerce"
    )
    if eligible[["issued_at", "forecast_valid_at"]].isna().any().any():
        raise IndicatorContractError("weather timestamps must be known")
    eligible = eligible.loc[eligible["issued_at"] <= cutoff].copy()

    anchors, lead_start, lead_end, base_c, cycle_hour = _weather_source_settings(
        source_policy
    )
    run_meta = eligible[["run_id", "issued_at", "available_at"]].drop_duplicates()
    counts = run_meta.groupby("run_id", dropna=False).size()
    if (counts != 1).any():
        raise IndicatorContractError(
            "weather run identity has inconsistent timestamps"
        )
    if run_meta["issued_at"].duplicated(keep=False).any():
        raise IndicatorContractError(
            "duplicate/tied eligible weather issued_at identities"
        )
    run_meta = run_meta.sort_values("issued_at")
    run_meta = run_meta.loc[run_meta["issued_at"].dt.hour == cycle_hour]
    if len(run_meta) < 2:
        raise IndicatorContractError(
            "weather revision requires current and predecessor runs"
        )
    current = run_meta.iloc[-1]
    prior = run_meta.iloc[-2]
    _require_fresh_current_state(
        current["available_at"],
        cutoff,
        source_policy,
        "weather",
        label="weather current run",
    )

    start = current["issued_at"] + pd.Timedelta(hours=lead_start)
    end = current["issued_at"] + pd.Timedelta(hours=lead_end)
    valid_times = pd.date_range(start, end, freq="h", inclusive="left")
    expected_rows = len(valid_times)

    aggregates: dict[str, tuple[float, float]] = {}
    for name, meta in (("current", current), ("prior", prior)):
        run = eligible.loc[eligible["run_id"] == meta["run_id"]].copy()
        run = run.loc[
            (run["forecast_valid_at"] >= start) & (run["forecast_valid_at"] < end)
        ]
        if set(run["anchor_id"].astype(str)) != set(anchors):
            raise IndicatorContractError(
                f"{name} weather run is missing a configured anchor"
            )
        hdd_values: list[float] = []
        cdd_values: list[float] = []
        for anchor in anchors:
            rows = run.loc[run["anchor_id"].astype(str) == anchor].copy()
            if rows["forecast_valid_at"].duplicated().any():
                raise IndicatorContractError(
                    f"{name} weather run has duplicate hourly identities"
                )
            rows = rows.set_index("forecast_valid_at").reindex(valid_times)
            if len(rows) != expected_rows or rows["temperature_2m"].isna().any():
                raise IndicatorContractError(
                    f"{name} weather run lacks the exact current valid-time window"
                )
            temperature = pd.to_numeric(rows["temperature_2m"], errors="coerce")
            if temperature.isna().any() or not np.isfinite(
                temperature.to_numpy()
            ).all():
                raise IndicatorContractError(
                    f"{name} weather temperature is non-finite"
                )
            hdd_values.append(
                float((base_c - temperature).clip(lower=0).sum() / 24.0)
            )
            cdd_values.append(
                float((temperature - base_c).clip(lower=0).sum() / 24.0)
            )
        aggregates[name] = (
            float(np.mean(hdd_values)),
            float(np.mean(cdd_values)),
        )

    return {
        "weather_hdd65_revision_1run": (
            aggregates["current"][0] - aggregates["prior"][0]
        ),
        "weather_cdd65_revision_1run": (
            aggregates["current"][1] - aggregates["prior"][1]
        ),
    }


def build_storage_public_value_events(
    history: pd.DataFrame,
    revisions: pd.DataFrame,
    source_policy: PinnedSourcePolicy,
) -> pd.DataFrame:
    """Reconstruct WNGSR public values as release/revision events by storage week."""
    _require_columns(
        history, ("observed_for", "storage_lower48_bcf"), label="storage history"
    )
    _require_columns(
        revisions,
        (
            "observed_for",
            "original_storage_lower48_bcf",
            "revised_storage_lower48_bcf",
            "revision_date",
        ),
        label="storage revisions",
    )
    cfg = _source_settings(source_policy, "eia_storage")
    accepted = sorted(_accepted_source_ids(source_policy, "eia_storage"))
    if len(accepted) != 1:
        raise IndicatorContractError(
            "#83 storage reconstruction requires one pinned WNGSR source identity"
        )
    source_id = accepted[0]

    hist = history.copy()
    hist["observed_for"] = pd.to_datetime(
        hist["observed_for"], utc=True, errors="coerce"
    )
    if hist["observed_for"].isna().any() or hist["observed_for"].duplicated().any():
        raise IndicatorContractError(
            "storage history requires unique known observed_for weeks"
        )
    hist["storage_lower48_bcf"] = pd.to_numeric(
        hist["storage_lower48_bcf"], errors="coerce"
    )
    if hist["storage_lower48_bcf"].isna().any() or not np.isfinite(
        hist["storage_lower48_bcf"].to_numpy()
    ).all():
        raise IndicatorContractError("storage history values must be finite")
    finals = {
        pd.Timestamp(row.observed_for): float(row.storage_lower48_bcf)
        for row in hist.itertuples(index=False)
    }

    rev = revisions.copy()
    rev["observed_for"] = pd.to_datetime(
        rev["observed_for"], utc=True, errors="coerce"
    )
    rev["revision_date"] = pd.to_datetime(
        rev["revision_date"], utc=True, errors="coerce"
    )
    if rev[["observed_for", "revision_date"]].isna().any().any():
        raise IndicatorContractError("storage revision identities must be known")
    if not set(rev["observed_for"]).issubset(finals):
        raise IndicatorContractError("storage revision targets an unknown history week")
    rev["original_storage_lower48_bcf"] = pd.to_numeric(
        rev["original_storage_lower48_bcf"], errors="coerce"
    )
    rev["revised_storage_lower48_bcf"] = pd.to_numeric(
        rev["revised_storage_lower48_bcf"], errors="coerce"
    )
    if rev["original_storage_lower48_bcf"].isna().any():
        raise IndicatorContractError("storage revision original values must be finite")

    effective: dict[int, float] = {}
    baseline = dict(finals)
    for observed, group in rev.groupby("observed_for", sort=False):
        ordered = group.sort_values("revision_date", kind="mergesort")
        if ordered["revision_date"].duplicated().any():
            raise IndicatorContractError(
                "storage has duplicate/ambiguous revisions for one week"
            )
        indices = list(ordered.index)
        baseline[pd.Timestamp(observed)] = _finite(
            ordered.iloc[0]["original_storage_lower48_bcf"],
            label="storage original release",
        )
        for position, index in enumerate(indices):
            explicit = rev.at[index, "revised_storage_lower48_bcf"]
            inferred = (
                _finite(
                    rev.at[indices[position + 1], "original_storage_lower48_bcf"],
                    label="next storage revision original",
                )
                if position + 1 < len(indices)
                else finals[pd.Timestamp(observed)]
            )
            if pd.notna(explicit):
                explicit_value = _finite(explicit, label="storage revised value")
                if abs(explicit_value - inferred) > 1e-9:
                    raise IndicatorContractError(
                        "storage explicit revised value conflicts with revision chain"
                    )
            effective[index] = inferred

    rows: list[dict[str, Any]] = []
    for observed in sorted(baseline):
        available_at, status, _ = resolve_wngsr_release(observed, dict(cfg))
        if status == "unresolved" or pd.isna(available_at):
            raise IndicatorContractError(
                f"storage release availability unresolved for {observed.date()}"
            )
        rows.append(
            {
                "observed_for": observed,
                "available_at": pd.Timestamp(available_at).tz_convert("UTC"),
                "storage_lower48_bcf": float(baseline[observed]),
                "revision_status": "point_in_time",
                "source_id": source_id,
            }
        )

    policy = cfg.get("availability_policy")
    if not isinstance(policy, Mapping):
        raise IndicatorContractError("storage availability policy is missing")
    zone = ZoneInfo(str(policy.get("timezone", "")))
    sample_weeks = {
        str(value) for value in policy.get("sample_reselection_weeks", ())
    }
    special_events = policy.get("special_revision_events", {})
    if not isinstance(special_events, Mapping):
        raise IndicatorContractError(
            "storage special revision events must be an object"
        )
    for index, row in rev.iterrows():
        observed = pd.Timestamp(row["observed_for"])
        revision_day = pd.Timestamp(row["revision_date"]).date()
        available_at: pd.Timestamp | None = None
        if observed.date().isoformat() in sample_weeks:
            for value in special_events.values():
                event = pd.Timestamp(value)
                if event.tzinfo is None:
                    raise IndicatorContractError(
                        "storage special revision event must be timezone-aware"
                    )
                if revision_day == event.date():
                    available_at = event.tz_convert("UTC")
                    break
        if available_at is None:
            local = dt.datetime.combine(
                revision_day,
                dt.time(23, 59),
                tzinfo=zone,
            )
            available_at = pd.Timestamp(local).tz_convert("UTC")
        release_at = next(
            item["available_at"]
            for item in rows
            if item["observed_for"] == observed
            and item["storage_lower48_bcf"] == baseline[observed]
        )
        if available_at <= release_at:
            raise IndicatorContractError(
                "storage revision availability must follow the original release"
            )
        rows.append(
            {
                "observed_for": observed,
                "available_at": available_at,
                "storage_lower48_bcf": float(effective[index]),
                "revision_status": "point_in_time",
                "source_id": source_id,
            }
        )

    result = (
        pd.DataFrame(rows)
        .sort_values(["available_at", "observed_for"], kind="mergesort")
        .reset_index(drop=True)
    )
    if result.duplicated(["observed_for", "available_at"]).any():
        raise IndicatorContractError(
            "storage public-value event identity is duplicate/ambiguous"
        )
    return result


def build_storage_increment(
    events: pd.DataFrame,
    prediction_time: Any,
    source_policy: PinnedSourcePolicy,
) -> dict[str, float]:
    required = (
        "observed_for",
        "available_at",
        "storage_lower48_bcf",
        "revision_status",
        "source_id",
    )
    _require_columns(events, required, label="storage input")
    eligible, cutoff = _eligible_before(events, prediction_time, label="storage input")
    _require_accepted_source(
        eligible, source_policy, "eia_storage", label="storage input"
    )
    if eligible.empty:
        raise IndicatorContractError("no storage state is eligible at the cutoff")
    if not eligible["revision_status"].astype(str).eq("point_in_time").all():
        raise IndicatorContractError("storage input contains non-PIT revision state")
    eligible["observed_for"] = pd.to_datetime(
        eligible["observed_for"], utc=True, errors="coerce"
    )
    if eligible["observed_for"].isna().any():
        raise IndicatorContractError("storage observed_for must be known")
    latest_rows: list[pd.Series] = []
    for _, group in eligible.groupby("observed_for", sort=False):
        latest_at = group["available_at"].max()
        latest = group.loc[group["available_at"] == latest_at]
        if len(latest) != 1:
            raise IndicatorContractError(
                "storage has duplicate/ambiguous eligible values for one week"
            )
        latest_rows.append(latest.iloc[0])
    state = pd.DataFrame(latest_rows).sort_values("observed_for")
    if len(state) < 3:
        raise IndicatorContractError(
            "storage acceleration requires three distinct weeks"
        )
    tail = state.iloc[-3:]
    if tail["observed_for"].duplicated().any():
        raise IndicatorContractError("storage predecessor weeks must be distinct")
    values = [
        _finite(value, label="storage_lower48_bcf")
        for value in tail["storage_lower48_bcf"].tolist()
    ]
    w2, w1, w0 = values
    _require_fresh_current_state(
        tail.iloc[-1]["available_at"],
        cutoff,
        source_policy,
        "eia_storage",
        label="storage current state",
    )
    return {"storage_change_accel_bcf": (w0 - w1) - (w1 - w2)}
