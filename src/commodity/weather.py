from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from commodity.availability import annotate_weather_research_availability
from commodity.config import data_config
from commodity.snapshots import SnapshotWriter, verify_snapshot


@dataclass
class OpenMeteoSingleRunClient:
    session: requests.Session | None = None

    def fetch(
        self,
        latitude: float,
        longitude: float,
        run: str,
        model: str,
        hourly: tuple[str, ...],
        forecast_days: int,
    ) -> dict[str, Any]:
        cfg = data_config()["providers"]["open_meteo_historical_forecast"]
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "run": run,
            "models": model,
            "hourly": ",".join(hourly),
            "forecast_days": forecast_days,
            "timezone": "UTC",
        }
        response = (self.session or requests.Session()).get(
            cfg["single_runs_api_base"], params=params, timeout=60
        )
        response.raise_for_status()
        return response.json()

    def fetch_with_raw(
        self,
        latitude: float,
        longitude: float,
        run: str,
        model: str,
        hourly: tuple[str, ...],
        forecast_days: int,
    ) -> tuple[dict[str, Any], bytes]:
        cfg = data_config()["providers"]["open_meteo_historical_forecast"]
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "run": run,
            "models": model,
            "hourly": ",".join(hourly),
            "forecast_days": forecast_days,
            "timezone": "UTC",
        }
        response = (self.session or requests.Session()).get(
            cfg["single_runs_api_base"], params=params, timeout=60
        )
        response.raise_for_status()
        return response.json(), response.content


def normalize_single_run(
    payload: dict[str, Any], run: str, model: str
) -> pd.DataFrame:
    hourly = payload.get("hourly", {})
    if "time" not in hourly:
        raise ValueError("Open-Meteo single-run response is missing hourly.time")
    frame = pd.DataFrame({key: values for key, values in hourly.items()})
    frame.insert(0, "forecast_valid_at", pd.to_datetime(frame.pop("time"), utc=True))
    frame.insert(0, "issued_at", pd.Timestamp(run, tz="UTC"))
    frame.insert(0, "model", model)
    frame["available_at"] = pd.NaT
    return frame


def capture_weather_run(
    client: OpenMeteoSingleRunClient,
    latitude: float,
    longitude: float,
    run: str,
    model: str,
    hourly: tuple[str, ...],
    forecast_days: int,
    snapshot_root: Path,
    snapshot_id: str,
    retrieved_at: str,
) -> Path:
    payload = client.fetch(latitude, longitude, run, model, hourly, forecast_days)
    frame = normalize_single_run(payload, run, model)
    writer = SnapshotWriter(Path(snapshot_root), "open_meteo", snapshot_id)
    writer.write_bytes(
        "raw.json",
        (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8"),
    )
    writer.write_bytes("forecast.csv", frame.to_csv(index=False).encode("utf-8"))
    return writer.finalize(
        {
            "source_id": "open_meteo_single_runs",
            "retrieved_at": retrieved_at,
            "model": model,
            "issued_at": pd.Timestamp(run, tz="UTC").isoformat(),
            "available_at": None,
            "latitude": latitude,
            "longitude": longitude,
            "forecast_days": forecast_days,
            "hourly_variables": list(hourly),
            "point_in_time_backtest_ready": False,
            "note": "Run/model initialization is preserved as issued_at; actual source availability is not fabricated.",
        }
    )



def _utc_timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str) + "\n").encode(
        "utf-8"
    )


def weather_v1_run_schedule(
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
) -> pd.DatetimeIndex:
    cfg = data_config()["sources"]["weather"]
    start_day = _utc_timestamp(start).normalize()
    end_day = _utc_timestamp(end).normalize()
    if end_day < start_day:
        raise ValueError("Weather V1 end date must be on or after start date")
    archive_start = _utc_timestamp(cfg["archive_start"]).normalize()
    if start_day < archive_start:
        raise ValueError(
            f"Weather V1 start precedes configured ECMWF archive start {archive_start.date()}"
        )
    hour = int(cfg["v1_run_cycle_utc_hour"])
    return pd.date_range(start_day, end_day, freq="D") + pd.Timedelta(hours=hour)


def weather_v1_declared_gaps(
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
) -> pd.DatetimeIndex:
    cfg = data_config()["sources"]["weather"]
    start_ts = _utc_timestamp(start).normalize()
    end_ts = _utc_timestamp(end).normalize() + pd.Timedelta(days=1)
    values = [
        *cfg.get("declared_issued_run_archive_gaps", []),
        *cfg.get("declared_issued_run_feature_gaps", []),
    ]
    gaps = pd.DatetimeIndex(pd.to_datetime(values, utc=True)).drop_duplicates()
    return gaps[(gaps >= start_ts) & (gaps < end_ts)].sort_values()


def _weather_window(
    payload: dict[str, Any],
    run: pd.Timestamp,
    model: str,
    lead_start: int,
    lead_end: int,
) -> pd.DataFrame:
    frame = normalize_single_run(payload, run.strftime("%Y-%m-%dT%H:%M"), model)
    start = run + pd.Timedelta(hours=lead_start)
    end = run + pd.Timedelta(hours=lead_end)
    window = frame.loc[
        (frame["forecast_valid_at"] >= start) & (frame["forecast_valid_at"] < end)
    ].copy()
    expected_rows = lead_end - lead_start
    if len(window) != expected_rows:
        raise ValueError(
            f"Open-Meteo issued run requires {expected_rows} hourly rows in the V1 feature window; "
            f"found {len(window)}"
        )
    return window


def _numeric(window: pd.DataFrame, column: str) -> pd.Series:
    if column not in window.columns:
        raise ValueError(f"Open-Meteo issued run is missing hourly variable {column!r}")
    values = pd.to_numeric(window[column], errors="coerce")
    if values.isna().any():
        raise ValueError(f"Open-Meteo issued run has missing/non-numeric {column!r} values")
    return values.astype(float)


def _anchor_features(
    window: pd.DataFrame,
    *,
    anchor_id: str,
    degree_day_base_c: float,
) -> dict[str, float]:
    temperature = _numeric(window, "temperature_2m")
    humidity = _numeric(window, "relative_humidity_2m")
    precipitation = _numeric(window, "precipitation")
    wind = _numeric(window, "wind_speed_10m")
    prefix = f"weather_{anchor_id}"
    return {
        f"{prefix}_temp_7d_mean_c": float(temperature.mean()),
        f"{prefix}_hdd65_7d": float((degree_day_base_c - temperature).clip(lower=0).sum() / 24.0),
        f"{prefix}_cdd65_7d": float((temperature - degree_day_base_c).clip(lower=0).sum() / 24.0),
        f"{prefix}_humidity_7d_mean_pct": float(humidity.mean()),
        f"{prefix}_precip_7d_mm": float(precipitation.sum()),
        f"{prefix}_wind_7d_mean_kmh": float(wind.mean()),
    }


def _mean_feature(anchor_features: list[dict[str, float]], suffix: str) -> float:
    values = [value for features in anchor_features for key, value in features.items() if key.endswith(suffix)]
    if not values:
        raise ValueError(f"Weather V1 anchor feature suffix not found: {suffix}")
    return float(pd.Series(values, dtype=float).mean())


def build_weather_feature_row(
    payloads: dict[str, dict[str, Any]],
    run: str | pd.Timestamp,
    raw_payloads: dict[str, bytes] | None = None,
) -> pd.DataFrame:
    cfg = data_config()["sources"]["weather"]
    run_ts = _utc_timestamp(run)
    anchors = list(cfg["v1_anchors"])
    expected_ids = [str(anchor["id"]) for anchor in anchors]
    missing = [anchor_id for anchor_id in expected_ids if anchor_id not in payloads]
    if missing:
        raise ValueError(f"Weather V1 run is missing configured anchors: {missing}")
    lead_start, lead_end = [int(value) for value in cfg["v1_feature_lead_hours"]]
    degree_day_base_c = float(cfg["v1_degree_day_base_c"])
    model = str(cfg["model"])
    per_anchor: list[dict[str, float]] = []
    for anchor_id in expected_ids:
        window = _weather_window(
            payloads[anchor_id], run_ts, model, lead_start, lead_end
        )
        per_anchor.append(
            _anchor_features(
                window,
                anchor_id=anchor_id,
                degree_day_base_c=degree_day_base_c,
            )
        )

    availability = annotate_weather_research_availability(
        pd.DataFrame({"issued_at": [run_ts]}), cfg
    ).iloc[0]
    raw_hashes = {
        anchor_id: hashlib.sha256(
            raw_payloads[anchor_id]
            if raw_payloads is not None
            else _canonical_payload_bytes(payloads[anchor_id])
        ).hexdigest()
        for anchor_id in expected_ids
    }
    bundle_text = "\n".join(f"{key}:{raw_hashes[key]}" for key in sorted(raw_hashes))
    row: dict[str, Any] = {
        "observed_for": run_ts,
        "issued_at": run_ts,
        "available_at": availability["available_at"],
        "forecast_valid_at": run_ts + pd.Timedelta(hours=lead_start),
        "forecast_valid_end_at": run_ts + pd.Timedelta(hours=lead_end),
        "availability_status": availability["availability_status"],
        "revision_status": availability["revision_status"],
        "availability_basis": availability["availability_basis"],
        "source_id": "open_meteo_single_runs_v1",
        "model": model,
        "run_cycle_utc_hour": int(cfg["v1_run_cycle_utc_hour"]),
        "anchor_aggregation": cfg["v1_anchor_aggregation"],
        "source_raw_sha256": hashlib.sha256(bundle_text.encode("utf-8")).hexdigest(),
    }
    for features in per_anchor:
        row.update(features)
    row.update(
        {
            "weather_temp_7d_anchor_mean_c": _mean_feature(per_anchor, "_temp_7d_mean_c"),
            "weather_hdd65_7d_anchor_mean": _mean_feature(per_anchor, "_hdd65_7d"),
            "weather_cdd65_7d_anchor_mean": _mean_feature(per_anchor, "_cdd65_7d"),
        }
    )
    row.update(
        {
            "weather_humidity_7d_anchor_mean_pct": _mean_feature(
                per_anchor, "_humidity_7d_mean_pct"
            ),
            "weather_precip_7d_anchor_mean_mm": _mean_feature(
                per_anchor, "_precip_7d_mm"
            ),
            "weather_wind_7d_anchor_mean_kmh": _mean_feature(
                per_anchor, "_wind_7d_mean_kmh"
            ),
        }
    )
    return pd.DataFrame([row])


def _run_request_string(run: pd.Timestamp) -> str:
    return _utc_timestamp(run).strftime("%Y-%m-%dT%H:%M")


def _weather_snapshot_id(run: pd.Timestamp) -> str:
    return _utc_timestamp(run).strftime("%Y%m%dT%H%MZ")


def capture_weather_v1_run(
    client: OpenMeteoSingleRunClient,
    run: str | pd.Timestamp,
    snapshot_root: Path,
    snapshot_id: str,
    retrieved_at: str,
) -> Path:
    cfg = data_config()["sources"]["weather"]
    run_ts = _utc_timestamp(run)
    run_text = _run_request_string(run_ts)
    model = str(cfg["model"])
    hourly = tuple(str(value) for value in cfg["v1_hourly_variables"])
    forecast_days = int(cfg["v1_forecast_days"])
    payloads: dict[str, dict[str, Any]] = {}
    raw_payloads: dict[str, bytes] = {}
    for anchor in cfg["v1_anchors"]:
        anchor_id = str(anchor["id"])
        args = (
            float(anchor["latitude"]), float(anchor["longitude"]), run_text,
            model, hourly, forecast_days,
        )
        if hasattr(client, "fetch_with_raw"):
            payload, raw = client.fetch_with_raw(*args)
        else:
            payload = client.fetch(*args)
            raw = _canonical_payload_bytes(payload)
        payloads[anchor_id] = payload
        raw_payloads[anchor_id] = raw
    frame = build_weather_feature_row(payloads, run_ts, raw_payloads=raw_payloads)
    writer = SnapshotWriter(Path(snapshot_root), "open_meteo_v1", snapshot_id)
    for anchor_id, raw in raw_payloads.items():
        writer.write_bytes(f"raw/{anchor_id}.json", raw)
    writer.write_bytes(
        "weather_features.csv", frame.to_csv(index=False).encode("utf-8")
    )
    first = frame.iloc[0]
    return writer.finalize(
        {
            "source_id": "open_meteo_single_runs_v1",
            "retrieved_at": retrieved_at,
            "model": model,
            "issued_at": run_ts.isoformat(),
            "available_at": pd.Timestamp(first["available_at"]).isoformat(),
            "forecast_valid_at": pd.Timestamp(first["forecast_valid_at"]).isoformat(),
            "forecast_valid_end_at": pd.Timestamp(first["forecast_valid_end_at"]).isoformat(),
            "source_raw_sha256": first["source_raw_sha256"],
            "anchors": list(cfg["v1_anchors"]),
            "hourly_variables": list(hourly),
            "normalized_rows": len(frame),
            "availability_status": first["availability_status"],
            "revision_status": first["revision_status"],
            "point_in_time_backtest_ready": True,
            "canonical_evidence": False,
        }
    )


def capture_weather_v1_window(
    client: OpenMeteoSingleRunClient,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    snapshot_root: Path,
    retrieved_at: str,
) -> list[Path]:
    root = Path(snapshot_root)
    manifests: list[Path] = []
    declared_gaps = set(weather_v1_declared_gaps(start, end))
    for run in weather_v1_run_schedule(start, end):
        snapshot_id = _weather_snapshot_id(run)
        manifest = root / "open_meteo_v1" / snapshot_id / "manifest.json"
        if manifest.exists():
            verify_snapshot(manifest)
            manifests.append(manifest)
            continue
        if run in declared_gaps:
            continue
        manifests.append(
            capture_weather_v1_run(
                client,
                run,
                root,
                snapshot_id,
                retrieved_at,
            )
        )
    return manifests



def load_weather_v1_window(
    snapshot_root: Path,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
) -> pd.DataFrame:
    root = Path(snapshot_root)
    rows: list[pd.DataFrame] = []
    expected_runs = weather_v1_run_schedule(start, end)
    declared_gaps = set(weather_v1_declared_gaps(start, end))
    skipped_declared_gaps: set[pd.Timestamp] = set()
    parse_dates = [
        "observed_for",
        "issued_at",
        "available_at",
        "forecast_valid_at",
        "forecast_valid_end_at",
    ]
    for run in expected_runs:
        snapshot_id = _weather_snapshot_id(run)
        manifest = root / "open_meteo_v1" / snapshot_id / "manifest.json"
        if not manifest.is_file():
            if run in declared_gaps:
                skipped_declared_gaps.add(run)
                continue
            raise ValueError(f"Weather V1 missing scheduled snapshot: {snapshot_id}")
        verify_snapshot(manifest)
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        if metadata.get("source_id") != "open_meteo_single_runs_v1":
            raise ValueError(f"Weather V1 snapshot has unexpected source identity: {snapshot_id}")
        if metadata.get("point_in_time_backtest_ready") is not True:
            raise ValueError(f"Weather V1 snapshot is not research-PIT ready: {snapshot_id}")
        feature_path = manifest.parent / "weather_features.csv"
        frame = pd.read_csv(feature_path, parse_dates=parse_dates)
        if len(frame) != 1:
            raise ValueError(f"Weather V1 snapshot must contain exactly one feature row: {snapshot_id}")
        issued_at = _utc_timestamp(frame.iloc[0]["issued_at"])
        if issued_at != run:
            raise ValueError(
                f"Weather V1 snapshot issued_at mismatch for {snapshot_id}: {issued_at.isoformat()}"
            )
        rows.append(frame)
    result = pd.concat(rows, ignore_index=True)
    result = result.sort_values("issued_at", kind="mergesort").reset_index(drop=True)
    observed_runs = pd.DatetimeIndex(pd.to_datetime(result["issued_at"], utc=True))
    expected_loaded_runs = pd.DatetimeIndex(
        [run for run in expected_runs if run not in skipped_declared_gaps]
    )
    if not observed_runs.equals(expected_loaded_runs):
        raise ValueError(
            "Weather V1 loaded run schedule does not match configured daily schedule "
            "after declared archive gaps"
        )
    if not result["source_raw_sha256"].astype(str).str.fullmatch(r"[0-9a-f]{64}").all():
        raise ValueError("Weather V1 loaded features contain invalid raw lineage")
    return result
