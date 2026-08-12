import pytest

from commodity.providers import (
    EiaApiV2Client,
    MissingCredential,
    require_point_in_time_ready,
)


def test_eia_requires_configured_environment_key(monkeypatch) -> None:
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    with pytest.raises(MissingCredential):
        EiaApiV2Client().fetch("natural-gas/stor/wkly")


def test_point_in_time_gate_rejects_observation_date_only() -> None:
    import pandas as pd

    frame = pd.DataFrame({"report_date": ["2026-01-01"], "value": [1.0]})
    with pytest.raises(ValueError, match="available_at"):
        require_point_in_time_ready(frame)


def test_cftc_snapshot_uses_configured_contract_code() -> None:
    from commodity.providers import CftcCotSnapshotClient

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self):
            return [{"report_date_as_yyyy_mm_dd": "2026-01-06T00:00:00.000"}]

    class Session:
        def __init__(self) -> None:
            self.params = None

        def get(self, url, params, timeout):
            self.params = params
            return Response()

    session = Session()
    frame = CftcCotSnapshotClient(session=session).fetch(limit=2)
    assert session.params["cftc_contract_market_code"] == "023651"
    assert len(frame) == 1


def test_point_in_time_gate_rejects_impossible_availability_order() -> None:
    import pandas as pd

    frame = pd.DataFrame({
        "observed_at": ["2026-01-02T12:00:00Z"],
        "available_at": ["2026-01-02T11:59:00Z"],
    })
    with pytest.raises(ValueError, match="earlier than"):
        require_point_in_time_ready(frame, observation_col="observed_at")


def test_eia_source_uses_authoritative_route_and_provider_config(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            pass
        def json(self):
            return {"response": {"data": [{"period": "2024-04-05", "value": "1.0"}]}}
    class Session:
        def __init__(self) -> None:
            self.url = None
        def get(self, url, params, timeout):
            self.url = url
            return Response()
    monkeypatch.setenv("EIA_API_KEY", "test-key")
    session = Session()
    frame = EiaApiV2Client(session=session).fetch_source("eia_nymex_prompt_history")
    assert session.url.endswith("/natural-gas/pri/fut/data/")
    assert len(frame) == 1
