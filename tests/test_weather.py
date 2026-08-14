import json
from pathlib import Path

import pandas as pd

from commodity.weather import (
    OpenMeteoSingleRunClient,
    build_weather_feature_row,
    capture_weather_run,
    capture_weather_v1_run,
    capture_weather_v1_window,
    load_weather_v1_window,
    normalize_single_run,
    weather_v1_run_schedule,
)


def test_weather_run_preserves_issue_and_valid_time_without_fabricating_availability() -> None:
    payload = {"hourly": {"time": ["2024-08-13T01:00"], "temperature_2m": [25.0]}}
    frame = normalize_single_run(payload, "2024-08-13T00:00", "ecmwf_ifs")
    assert frame.iloc[0]["issued_at"] == pd.Timestamp("2024-08-13T00:00Z")
    assert frame.iloc[0]["forecast_valid_at"] == pd.Timestamp("2024-08-13T01:00Z")
    assert pd.isna(frame.iloc[0]["available_at"])


def test_weather_client_uses_single_runs_endpoint(monkeypatch) -> None:
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"hourly": {"time": [], "temperature_2m": []}}

    class Session:
        def __init__(self):
            self.url = None
            self.params = None

        def get(self, url, params, timeout):
            self.url = url
            self.params = params
            return Response()

    session = Session()
    OpenMeteoSingleRunClient(session=session).fetch(
        41.8,
        -87.6,
        "2024-08-13T00:00",
        "ecmwf_ifs",
        ("temperature_2m",),
        1,
    )
    assert "single-runs-api.open-meteo.com" in session.url
    assert session.params["run"] == "2024-08-13T00:00"


def test_weather_snapshot_declares_availability_unresolved(tmp_path: Path) -> None:
    class Client:
        def fetch(self, *args, **kwargs):
            return {
                "hourly": {"time": ["2024-08-13T01:00"], "temperature_2m": [25.0]}
            }

    manifest = capture_weather_run(
        Client(),
        41.8,
        -87.6,
        "2024-08-13T00:00",
        "ecmwf_ifs",
        ("temperature_2m",),
        1,
        tmp_path,
        "snap",
        "2026-08-13T08:00:00Z",
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["available_at"] is None
    assert payload["point_in_time_backtest_ready"] is False



def _payload(run: pd.Timestamp, temperature: float) -> dict:
    times = pd.date_range(run, periods=217, freq="h")
    return {
        "hourly": {
            "time": times.strftime("%Y-%m-%dT%H:%M").tolist(),
            "temperature_2m": [temperature] * len(times),
            "relative_humidity_2m": [50.0] * len(times),
            "precipitation": [0.25] * len(times),
            "wind_speed_10m": [10.0] * len(times),
        }
    }


def test_weather_v1_schedule_is_one_predeclared_run_per_day() -> None:
    runs = weather_v1_run_schedule("2024-08-13", "2024-08-15")
    assert list(runs) == list(
        pd.to_datetime(
            ["2024-08-13T00:00Z", "2024-08-14T00:00Z", "2024-08-15T00:00Z"]
        )
    )


def test_weather_v1_features_use_future_window_and_pit_metadata() -> None:
    from commodity.config import data_config

    cfg = data_config()["sources"]["weather"]
    run = pd.Timestamp("2024-08-13T00:00Z")
    payloads = {
        anchor["id"]: _payload(run, 18.0 + index)
        for index, anchor in enumerate(cfg["v1_anchors"])
    }
    row = build_weather_feature_row(payloads, run.isoformat())
    assert row.iloc[0]["issued_at"] == run
    assert row.iloc[0]["available_at"] == pd.Timestamp("2024-08-13T06:10Z")
    assert row.iloc[0]["forecast_valid_at"] == pd.Timestamp("2024-08-14T00:00Z")
    assert row.iloc[0]["forecast_valid_end_at"] == pd.Timestamp("2024-08-21T00:00Z")
    assert row.iloc[0]["availability_status"] == "reconstructed_conservative"
    assert row.iloc[0]["revision_status"] == "issued_run_immutable"
    assert len(row.iloc[0]["source_raw_sha256"]) == 64
    assert row.iloc[0]["weather_precip_7d_anchor_mean_mm"] == 42.0
    assert row.iloc[0]["weather_wind_7d_anchor_mean_kmh"] == 10.0


def test_weather_v1_capture_preserves_raw_anchor_lineage(tmp_path: Path) -> None:
    from commodity.config import data_config

    cfg = data_config()["sources"]["weather"]
    run = pd.Timestamp("2024-08-13T00:00Z")

    class Client:
        def fetch(self, latitude, longitude, run, model, hourly, forecast_days):
            anchor = next(
                item for item in cfg["v1_anchors"]
                if item["latitude"] == latitude and item["longitude"] == longitude
            )
            return _payload(pd.Timestamp(run, tz="UTC"), 18.0 + len(anchor["id"]))

    manifest = capture_weather_v1_run(
        Client(), run, tmp_path, "20240813T0000Z", "2026-08-14T02:00:00Z"
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["source_id"] == "open_meteo_single_runs_v1"
    assert payload["point_in_time_backtest_ready"] is True
    assert payload["normalized_rows"] == 1
    paths = {item["path"] for item in payload["artifacts"]}
    assert "weather_features.csv" in paths
    assert len([path for path in paths if path.startswith("raw/")]) == len(cfg["v1_anchors"])


def test_weather_v1_window_is_bounded_and_resumable(tmp_path: Path) -> None:
    from commodity.config import data_config

    cfg = data_config()["sources"]["weather"]

    class Client:
        def __init__(self):
            self.calls = 0

        def fetch(self, latitude, longitude, run, model, hourly, forecast_days):
            self.calls += 1
            return _payload(pd.Timestamp(run, tz="UTC"), 18.0)

    client = Client()
    first = capture_weather_v1_window(
        client, "2024-08-13", "2024-08-14", tmp_path, "2026-08-14T02:00:00Z"
    )
    expected_calls = 2 * len(cfg["v1_anchors"])
    assert client.calls == expected_calls
    second = capture_weather_v1_window(
        client, "2024-08-13", "2024-08-14", tmp_path, "2026-08-14T03:00:00Z"
    )
    assert client.calls == expected_calls
    assert first == second
    assert len(first) == 2
    loaded = load_weather_v1_window(tmp_path, "2024-08-13", "2024-08-14")
    assert len(loaded) == 2
    assert loaded["source_id"].eq("open_meteo_single_runs_v1").all()
    assert loaded["issued_at"].is_monotonic_increasing



def test_weather_v1_loader_requires_every_scheduled_manifest(tmp_path: Path) -> None:
    run = pd.Timestamp("2024-08-13T00:00Z")

    class Client:
        def fetch(self, latitude, longitude, run, model, hourly, forecast_days):
            return _payload(pd.Timestamp(run, tz="UTC"), 18.0)

    capture_weather_v1_run(
        Client(), run, tmp_path, "20240813T0000Z", "2026-08-14T02:00:00Z"
    )
    try:
        load_weather_v1_window(tmp_path, "2024-08-13", "2024-08-14")
    except ValueError as exc:
        assert "missing scheduled snapshot" in str(exc)
    else:
        raise AssertionError("Weather V1 loader must fail closed on a date gap")
