from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd

AVAILABILITY_MODES = {"canonical", "research_pit", "screening"}

_ALLOWED_AVAILABILITY = {
    "canonical": {"verified"},
    "research_pit": {"verified", "reconstructed_conservative"},
    "screening": {"verified", "reconstructed_conservative"},
}

_ALLOWED_REVISIONS = {
    "canonical": {"point_in_time", "issued_run_immutable"},
    "research_pit": {"point_in_time", "issued_run_immutable"},
    "screening": {
        "point_in_time",
        "issued_run_immutable",
        "current_snapshot_revised_history",
    },
}

_WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _require_columns(frame: pd.DataFrame, columns: set[str]) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def _local_cutoff(
    observed_for: pd.Timestamp,
    timezone: str,
    local_hour: int,
    local_minute: int,
    day_offset: int,
) -> pd.Timestamp:
    zone = ZoneInfo(timezone)
    local_date = observed_for.tz_convert(zone).date() + dt.timedelta(days=day_offset)
    local_dt = dt.datetime.combine(
        local_date,
        dt.time(local_hour, local_minute),
        tzinfo=zone,
    )
    return pd.Timestamp(local_dt).tz_convert("UTC")


def annotate_eia930_region_availability(
    frame: pd.DataFrame, source_cfg: dict
) -> pd.DataFrame:
    _require_columns(frame, {"period", "type"})
    policy = source_cfg["availability_policy"]
    timezone = policy["timezone"]
    out = frame.copy()
    out["observed_for"] = pd.to_datetime(out["period"], utc=True)

    available: list[pd.Timestamp] = []
    for row in out.itertuples(index=False):
        observed_for = pd.Timestamp(row.observed_for)
        data_type = str(row.type)
        if data_type == "D":
            reporting_lag = int(policy["demand"]["period_end_reporting_lag_minutes"])
            available_at = observed_for + dt.timedelta(minutes=reporting_lag)
        elif data_type == "DF":
            forecast = policy["demand_forecast"]
            available_at = _local_cutoff(
                observed_for,
                timezone,
                int(forecast["local_hour"]),
                int(forecast["local_minute"]),
                int(forecast["day_offset"]),
            )
        else:
            raise ValueError(f"Unsupported EIA-930 region-data type: {data_type!r}")
        available.append(available_at)

    out["available_at"] = pd.to_datetime(available, utc=True)
    out["availability_status"] = "reconstructed_conservative"
    out["revision_status"] = "current_snapshot_revised_history"
    out["availability_basis"] = "eia930_publication_schedule"
    return out


def annotate_eia930_generation_availability(
    frame: pd.DataFrame, source_cfg: dict
) -> pd.DataFrame:
    _require_columns(frame, {"period"})
    policy = source_cfg["availability_policy"]
    timezone = policy["timezone"]
    generation = policy["generation"]
    out = frame.copy()
    out["observed_for"] = pd.to_datetime(out["period"], utc=True)
    out["available_at"] = [
        _local_cutoff(
            pd.Timestamp(value),
            timezone,
            int(generation["local_hour"]),
            int(generation["local_minute"]),
            int(generation["day_offset"]),
        )
        for value in out["observed_for"]
    ]
    out["available_at"] = pd.to_datetime(out["available_at"], utc=True)
    out["availability_status"] = "reconstructed_conservative"
    out["revision_status"] = "current_snapshot_revised_history"
    out["availability_basis"] = "eia930_publication_schedule"
    return out


def annotate_wngsr_availability(
    frame: pd.DataFrame,
    source_cfg: dict,
    observed_col: str = "period",
) -> pd.DataFrame:
    _require_columns(frame, {observed_col})
    policy = source_cfg["availability_policy"]
    timezone = policy["timezone"]
    coverage_start = pd.Timestamp(policy["exception_registry_coverage_start"]).date()
    coverage_end = pd.Timestamp(policy["exception_registry_coverage_end"]).date()
    overrides = policy.get("release_date_overrides", {})
    release_hour = int(policy["regular_release_hour"])
    release_minute = int(policy["regular_release_minute"])
    weekday_name = str(policy["regular_release_weekday"]).strip().lower()
    try:
        release_weekday = _WEEKDAY_INDEX[weekday_name]
    except KeyError:
        raise ValueError(f"Unsupported release weekday: {weekday_name!r}") from None
    zone = ZoneInfo(timezone)

    out = frame.copy()
    out["observed_for"] = pd.to_datetime(out[observed_col], utc=True)
    available: list[pd.Timestamp | pd.NaT] = []
    statuses: list[str] = []

    for observed in out["observed_for"]:
        observed_date = pd.Timestamp(observed).date()
        days_to_release = (release_weekday - observed_date.weekday()) % 7
        if days_to_release == 0:
            days_to_release = 7
        regular_date = observed_date + dt.timedelta(days=days_to_release)
        regular_key = regular_date.isoformat()
        override = overrides.get(regular_key)

        outside_coverage = regular_date < coverage_start or regular_date > coverage_end
        if outside_coverage and override is None:
            available.append(pd.NaT)
            statuses.append("unresolved")
            continue

        if override is not None:
            release = pd.Timestamp(override)
            if release.tzinfo is None:
                raise ValueError(f"WNGSR override must include timezone: {override!r}")
            available_at = release.tz_convert("UTC")
        else:
            local_dt = dt.datetime.combine(
                regular_date,
                dt.time(release_hour, release_minute),
                tzinfo=zone,
            )
            available_at = pd.Timestamp(local_dt).tz_convert("UTC")
        available.append(available_at)
        statuses.append("reconstructed_conservative")

    out["available_at"] = pd.to_datetime(available, utc=True)
    out["availability_status"] = statuses
    out["revision_status"] = "current_snapshot_revised_history"
    out["availability_basis"] = "wngsr_release_schedule"
    return out


def annotate_weather_research_availability(
    frame: pd.DataFrame, source_cfg: dict
) -> pd.DataFrame:
    _require_columns(frame, {"issued_at"})
    policy = source_cfg["availability_policy"]
    delay_minutes = int(policy["research_global_model_delay_minutes"])
    margin_minutes = int(policy["server_consistency_margin_minutes"])
    out = frame.copy()
    out["issued_at"] = pd.to_datetime(out["issued_at"], utc=True)

    if "available_at" in out.columns:
        exact = pd.to_datetime(out["available_at"], utc=True, errors="coerce")
    else:
        exact = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")
    reconstructed = out["issued_at"] + pd.to_timedelta(
        delay_minutes + margin_minutes,
        unit="m",
    )
    out["available_at"] = exact.fillna(reconstructed)
    out["availability_status"] = [
        "verified" if pd.notna(value) else "reconstructed_conservative"
        for value in exact
    ]
    out["revision_status"] = "issued_run_immutable"
    out["availability_basis"] = [
        "source_available_at" if pd.notna(value) else "open_meteo_global_model_delay"
        for value in exact
    ]
    return out


def validate_availability(frame: pd.DataFrame, mode: str) -> pd.DataFrame:
    if mode not in AVAILABILITY_MODES:
        raise ValueError(f"Unknown availability mode: {mode!r}")
    _require_columns(
        frame,
        {"available_at", "availability_status", "revision_status"},
    )
    out = frame.copy()
    out["available_at"] = pd.to_datetime(out["available_at"], utc=True, errors="coerce")
    if "issued_at" in out.columns:
        issued_raw = out["issued_at"]
        issued_at = pd.to_datetime(issued_raw, utc=True, errors="coerce")
        invalid_issue_time = issued_raw.notna() & (
            issued_at.isna() | (out["available_at"] < issued_at)
        )
        if invalid_issue_time.any():
            bad_rows = list(out.index[invalid_issue_time][:10])
            raise ValueError(
                "Availability rows have invalid issued_at ordering: "
                f"row indices {bad_rows}"
            )
        out["issued_at"] = issued_at
    allowed_availability = _ALLOWED_AVAILABILITY[mode]
    allowed_revisions = _ALLOWED_REVISIONS[mode]
    invalid = (
        out["available_at"].isna()
        | ~out["availability_status"].isin(allowed_availability)
        | ~out["revision_status"].isin(allowed_revisions)
    )
    if invalid.any():
        bad_rows = list(out.index[invalid][:10])
        raise ValueError(
            f"Availability rows are not eligible for {mode}: row indices {bad_rows}"
        )
    out["evidence_mode"] = mode
    out["canonical_evidence"] = mode == "canonical"
    out["revision_leakage_risk"] = out["revision_status"].eq(
        "current_snapshot_revised_history"
    )
    return out


def asof_join_point_in_time(
    cutoffs: pd.DataFrame,
    exogenous: pd.DataFrame,
    value_columns: list[str],
    mode: str = "research_pit",
    cutoff_col: str = "prediction_time",
    by: str | list[str] | None = None,
) -> pd.DataFrame:
    _require_columns(cutoffs, {cutoff_col})
    _require_columns(exogenous, {"available_at", *value_columns})
    by_columns = [by] if isinstance(by, str) else list(by or [])
    if by_columns:
        _require_columns(cutoffs, set(by_columns))
        _require_columns(exogenous, set(by_columns))
    else:
        identity_columns = [
            column
            for column in ("series", "series_id", "type")
            if column in exogenous.columns and exogenous[column].nunique(dropna=False) > 1
        ]
        if identity_columns:
            raise ValueError(
                "Point-in-time join requires an explicit group key for multi-series sources: "
                f"{identity_columns}"
            )
    right = validate_availability(exogenous, mode)
    unique_key = [*by_columns, "available_at"]
    if right.duplicated(unique_key).any():
        label = " + ".join(unique_key)
        raise ValueError(
            f"Point-in-time join requires unique {label} rows; aggregate or pivot the source first"
        )
    left = cutoffs.copy()
    left[cutoff_col] = pd.to_datetime(left[cutoff_col], utc=True)
    left["_row_order"] = range(len(left))
    metadata_columns = [
        column
        for column in (
            "availability_status",
            "revision_status",
            "availability_basis",
            "evidence_mode",
            "canonical_evidence",
            "revision_leakage_risk",
        )
        if column in right.columns
    ]
    right_columns = list(
        dict.fromkeys([*by_columns, "available_at", *value_columns, *metadata_columns])
    )
    right = right[right_columns].sort_values(["available_at", *by_columns])
    merged = pd.merge_asof(
        left.sort_values([cutoff_col, *by_columns]),
        right,
        left_on=cutoff_col,
        right_on="available_at",
        by=by_columns or None,
        direction="backward",
    )
    return (
        merged.sort_values("_row_order")
        .drop(columns=["_row_order"])
        .reset_index(drop=True)
    )
