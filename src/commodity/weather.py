from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from commodity.config import data_config
from commodity.snapshots import SnapshotWriter


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
