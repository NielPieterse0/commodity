import json
from pathlib import Path

import pandas as pd

from commodity.weather import OpenMeteoSingleRunClient, capture_weather_run, normalize_single_run


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
    OpenMeteoSingleRunClient(session=session).fetch(41.8, -87.6, "2024-08-13T00:00", "ecmwf_ifs", ("temperature_2m",), 1)
    assert "single-runs-api.open-meteo.com" in session.url
    assert session.params["run"] == "2024-08-13T00:00"


def test_weather_snapshot_declares_availability_unresolved(tmp_path: Path) -> None:
    class Client:
        def fetch(self, *args, **kwargs):
            return {"hourly": {"time": ["2024-08-13T01:00"], "temperature_2m": [25.0]}}
    manifest = capture_weather_run(Client(), 41.8, -87.6, "2024-08-13T00:00", "ecmwf_ifs", ("temperature_2m",), 1, tmp_path, "snap", "2026-08-13T08:00:00Z")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["available_at"] is None
    assert payload["point_in_time_backtest_ready"] is False
