from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from commodity.availability import resolve_wngsr_release
from commodity.v2_indicator_contract import (
    IndicatorContractError,
    PinnedSourcePolicy,
    _accepted_source_ids,
    _date_identity_series,
    _eligible_before,
    _finite,
    _require_accepted_source,
    _require_columns,
    _require_fresh_current_state,
    _source_settings,
    _utc_timestamp,
    canonical_sha256,
)

FROZEN_WEATHER_ARCHIVE_MANIFEST_SHA256 = (
    "44e2ed4c7206ecde8dad442d6dfc70b4e14387c97621a4b516846a0266329096"
)
FROZEN_WEATHER_ARCHIVE_RUNS = 723


def _weather_archive_manifest_records(
    archive_root: Path,
    source_policy: PinnedSourcePolicy,
) -> list[dict[str, Any]]:
    root = Path(archive_root)
    if not root.is_dir():
        raise IndicatorContractError("frozen weather archive root is missing")
    manifests = sorted(root.glob("*/manifest.json"))
    if len(manifests) != FROZEN_WEATHER_ARCHIVE_RUNS:
        raise IndicatorContractError(
            "frozen weather archive run-manifest count differs from the #83 pin"
        )

    digest_entries: list[dict[str, str]] = []
    records: list[dict[str, Any]] = []
    accepted_sources = _accepted_source_ids(source_policy, "weather")
    weather_cfg = _source_settings(source_policy, "weather")
    model = str(weather_cfg.get("model"))
    anchors, _, _, _, _ = _weather_source_settings(source_policy)
    expected_anchor_artifacts = {f"raw/{anchor}.json" for anchor in anchors}

    for manifest_path in manifests:
        try:
            raw = manifest_path.read_bytes()
        except OSError as exc:
            raise IndicatorContractError("unable to read frozen weather run manifest") from exc
        normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        digest_entries.append(
            {
                "path": manifest_path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(normalized).hexdigest(),
            }
        )
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IndicatorContractError("weather run manifest must be valid JSON") from exc
        if not isinstance(payload, Mapping):
            raise IndicatorContractError("weather run manifest must be an object")
        record = dict(payload)
        snapshot_id = str(record.get("snapshot_id"))
        if snapshot_id != manifest_path.parent.name:
            raise IndicatorContractError("weather snapshot identity differs from archive path")
        if str(record.get("source_id")) not in accepted_sources:
            raise IndicatorContractError("weather run manifest source identity is not pinned")
        if record.get("revision_status") != "issued_run_immutable":
            raise IndicatorContractError("weather archive contains a non-immutable run manifest")
        if str(record.get("model")) != model:
            raise IndicatorContractError("weather run manifest model differs from source policy")
        issued_at = _utc_timestamp(
            record.get("issued_at"), label="weather manifest issued_at"
        )
        available_at = _utc_timestamp(
            record.get("available_at"), label="weather manifest available_at"
        )
        if available_at < issued_at:
            raise IndicatorContractError("weather run availability precedes issuance")
        artifacts = record.get("artifacts")
        if not isinstance(artifacts, list):
            raise IndicatorContractError("weather run manifest artifacts are missing")
        artifact_map: dict[str, str] = {}
        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                raise IndicatorContractError("weather run manifest artifact is invalid")
            path = str(artifact.get("path"))
            digest = str(artifact.get("sha256"))
            if path in artifact_map:
                raise IndicatorContractError("weather run manifest has duplicate artifact paths")
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise IndicatorContractError("weather run manifest artifact SHA-256 is invalid")
            artifact_map[path] = digest
        if not expected_anchor_artifacts.issubset(artifact_map):
            raise IndicatorContractError("weather run manifest lacks a pinned anchor artifact")
        record["_manifest_path"] = manifest_path
        record["_issued_at"] = issued_at
        record["_available_at"] = available_at
        record["_artifact_map"] = artifact_map
        records.append(record)

    archive_digest = canonical_sha256(
        {"schema_version": 1, "manifests": digest_entries}
    )
    if archive_digest != FROZEN_WEATHER_ARCHIVE_MANIFEST_SHA256:
        raise IndicatorContractError(
            "weather archive manifests differ from the frozen pre-results #83 archive"
        )
    if len({str(record["snapshot_id"]) for record in records}) != len(records):
        raise IndicatorContractError("weather archive snapshot identities are not unique")
    return records


def _verified_weather_run_rows(
    record: Mapping[str, Any],
    anchors: list[str],
) -> pd.DataFrame:
    manifest_path = Path(record["_manifest_path"])
    artifact_map = record["_artifact_map"]
    rows: list[dict[str, Any]] = []
    for anchor in anchors:
        relative = f"raw/{anchor}.json"
        artifact_path = manifest_path.parent / relative
        try:
            raw = artifact_path.read_bytes()
        except OSError as exc:
            raise IndicatorContractError("weather anchor artifact is missing") from exc
        if hashlib.sha256(raw).hexdigest() != artifact_map[relative]:
            raise IndicatorContractError("weather anchor artifact differs from its run manifest")
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IndicatorContractError("weather anchor artifact must be valid JSON") from exc
        if not isinstance(payload, Mapping):
            raise IndicatorContractError("weather anchor artifact must be an object")
        if payload.get("utc_offset_seconds") != 0 or str(payload.get("timezone")) not in {
            "GMT",
            "UTC",
        }:
            raise IndicatorContractError("weather anchor artifact is not explicit UTC/GMT")
        hourly = payload.get("hourly")
        if not isinstance(hourly, Mapping):
            raise IndicatorContractError("weather anchor artifact lacks hourly data")
        times = hourly.get("time")
        temperatures = hourly.get("temperature_2m")
        if not isinstance(times, list) or not isinstance(temperatures, list):
            raise IndicatorContractError("weather anchor artifact hourly vectors are invalid")
        if not times or len(times) != len(temperatures):
            raise IndicatorContractError("weather anchor artifact hourly vectors are misaligned")
        valid_times = pd.to_datetime(times, utc=True, errors="coerce")
        temperature_values = pd.to_numeric(temperatures, errors="coerce")
        if valid_times.isna().any() or np.isnan(temperature_values).any():
            raise IndicatorContractError("weather anchor artifact contains invalid hourly values")
        if pd.Index(valid_times).duplicated().any():
            raise IndicatorContractError("weather anchor artifact has duplicate hourly identities")
        for valid_at, temperature in zip(valid_times, temperature_values, strict=True):
            rows.append(
                {
                    "run_id": str(record["snapshot_id"]),
                    "issued_at": record["_issued_at"],
                    "available_at": record["_available_at"],
                    "anchor_id": anchor,
                    "forecast_valid_at": valid_at,
                    "temperature_2m": float(temperature),
                    "revision_status": "issued_run_immutable",
                    "source_id": str(record["source_id"]),
                }
            )
    return pd.DataFrame(rows)


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
    availability = weather.get("availability_policy")
    if not isinstance(availability, Mapping):
        raise IndicatorContractError("pinned weather availability policy is missing")
    if (
        availability.get("issued_run_revision_status") != "issued_run_immutable"
        or availability.get("research_pit_allowed_with_immutable_issued_runs") is not True
    ):
        raise IndicatorContractError(
            "pinned weather policy no longer requires immutable issued runs"
        )
    return anchors, lead_start, lead_end, degree_day_base, cycle_hour


def build_weather_revision(
    weather_archive: Path | pd.DataFrame,
    prediction_time: Any,
    source_policy: PinnedSourcePolicy,
) -> dict[str, float]:
    """Build weather revisions from the exact frozen issued-run archive only."""
    if isinstance(weather_archive, pd.DataFrame):
        raise IndicatorContractError(
            "caller-provided weather rows are not release-authoritative; pass the frozen "
            "Open-Meteo issued-run archive Path"
        )
    records = _weather_archive_manifest_records(Path(weather_archive), source_policy)
    cutoff = _utc_timestamp(prediction_time, label="prediction_time")
    anchors, _, _, _, cycle_hour = _weather_source_settings(source_policy)
    eligible = [
        record
        for record in records
        if record["_available_at"] <= cutoff
        and record["_issued_at"] <= cutoff
        and record["_issued_at"].hour == cycle_hour
    ]
    if len({record["_issued_at"] for record in eligible}) != len(eligible):
        raise IndicatorContractError("duplicate/tied eligible weather issued_at identities")
    eligible.sort(key=lambda record: record["_issued_at"])
    if len(eligible) < 2:
        raise IndicatorContractError("weather revision requires current and predecessor runs")
    current, prior = eligible[-1], eligible[-2]
    _require_fresh_current_state(
        current["_available_at"],
        cutoff,
        source_policy,
        "weather",
        label="weather current run",
    )
    hourly = pd.concat(
        [
            _verified_weather_run_rows(prior, anchors),
            _verified_weather_run_rows(current, anchors),
        ],
        ignore_index=True,
    )
    return _build_weather_revision_from_verified_rows(
        hourly,
        prediction_time,
        source_policy,
    )


def _build_weather_revision_from_verified_rows(
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
        "revision_status",
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
    if not eligible["revision_status"].astype(str).eq("issued_run_immutable").all():
        raise IndicatorContractError(
            "weather inputs must be immutable actually-issued forecast vintages"
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


def _storage_revision_policy(
    source_policy: PinnedSourcePolicy,
) -> tuple[Mapping[str, Any], ZoneInfo, int, int, str]:
    cfg = _source_settings(source_policy, "eia_storage")
    policy = cfg.get("availability_policy")
    if not isinstance(policy, Mapping):
        raise IndicatorContractError("storage availability policy is missing")
    if (
        cfg.get("point_in_time_required") is not True
        or cfg.get("revision_snapshots_required") is not True
        or cfg.get("availability_reconstruction_status") != "v1_research_ready_conservative"
        or policy.get("research_pit_allowed") is not True
        or policy.get("reconstructed_availability_status")
        != "reconstructed_conservative"
    ):
        raise IndicatorContractError(
            "pinned storage policy no longer permits conservative PIT revision reconstruction"
        )
    try:
        zone = ZoneInfo(str(policy["timezone"]))
        method = str(policy["ordinary_revision_availability_method"])
        hour = int(policy["ordinary_revision_local_hour"])
        minute = int(policy["ordinary_revision_local_minute"])
        basis = str(policy["ordinary_revision_availability_basis"])
    except (KeyError, TypeError, ValueError) as exc:
        raise IndicatorContractError("storage revision availability policy is invalid") from exc
    if (
        method != "revision_date_end_of_day_local_conservative"
        or hour != 23
        or minute != 59
        or basis != "revision_date_2359_local_conservative"
    ):
        raise IndicatorContractError("pinned storage ordinary-revision rule changed")
    return policy, zone, hour, minute, basis


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
    policy, zone, revision_hour, revision_minute, ordinary_revision_basis = (
        _storage_revision_policy(source_policy)
    )
    accepted = sorted(_accepted_source_ids(source_policy, "eia_storage"))
    if len(accepted) != 1:
        raise IndicatorContractError(
            "#83 storage reconstruction requires one pinned WNGSR source identity"
        )
    source_id = accepted[0]

    hist = history.copy()
    hist["observed_for"] = _date_identity_series(
        hist, "observed_for", label="storage history"
    )
    if hist["observed_for"].duplicated().any():
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
    rev["observed_for"] = _date_identity_series(
        rev, "observed_for", label="storage revisions"
    )
    rev["revision_date"] = _date_identity_series(
        rev, "revision_date", label="storage revisions"
    )
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
        available_at, status, availability_basis = resolve_wngsr_release(
            observed, dict(cfg)
        )
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
                "availability_basis": availability_basis,
                "source_id": source_id,
            }
        )

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
        availability_basis: str | None = None
        if observed.date().isoformat() in sample_weeks:
            for value in special_events.values():
                event = pd.Timestamp(value)
                if event.tzinfo is None:
                    raise IndicatorContractError(
                        "storage special revision event must be timezone-aware"
                    )
                if revision_day == event.date():
                    available_at = event.tz_convert("UTC")
                    availability_basis = "special_revision_event"
                    break
        if available_at is None:
            local = dt.datetime.combine(
                revision_day,
                dt.time(revision_hour, revision_minute),
                tzinfo=zone,
            )
            available_at = pd.Timestamp(local).tz_convert("UTC")
            availability_basis = ordinary_revision_basis
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
                "availability_basis": availability_basis,
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
