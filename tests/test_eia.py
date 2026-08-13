import json
from pathlib import Path

import pandas as pd
import pytest

from commodity.eia import (
    EiaBulkClient,
    capture_eia_api_dataset,
    capture_eia_bulk_dataset,
)
from commodity.providers import EiaApiV2Client, MissingCredential
from commodity.snapshots import verify_snapshot


def test_eia_requires_credential(monkeypatch) -> None:
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    with pytest.raises(MissingCredential, match="EIA_API_KEY"):
        EiaApiV2Client().fetch("natural-gas/prod")


def test_eia_fetch_all_paginates(monkeypatch) -> None:
    class Response:
        status_code = 200

        def __init__(self, params):
            self.params = params

        def raise_for_status(self):
            pass

        def json(self):
            offset = int(self.params["offset"])
            data = [{"period": str(i)} for i in range(offset, min(offset + 2, 3))]
            return {"response": {"total": "3", "data": data}}

    class Session:
        def get(self, url, params, timeout):
            return Response(params)

    monkeypatch.setenv("EIA_API_KEY", "test-key")
    frame = EiaApiV2Client(session=Session()).fetch_all("natural-gas/prod", page_size=2)
    assert list(frame["period"]) == ["0", "1", "2"]


def test_eia_bulk_capture_is_verifiable(tmp_path: Path) -> None:
    class Response:
        status_code = 200
        content = b"fake-zip"

        def raise_for_status(self):
            pass

    class Session:
        def get(self, url, timeout):
            return Response()

    manifest = capture_eia_bulk_dataset(
        EiaBulkClient(session=Session()),
        "NG",
        tmp_path,
        "snap",
        "2026-08-13T08:00:00Z",
    )
    assert verify_snapshot(manifest)["artifact_count"] == 1


def test_eia_api_capture_preserves_query_without_key(tmp_path: Path) -> None:
    class Client:
        def fetch_all(self, route, params):
            return pd.DataFrame([{"period": "2026-08-12T00", "value": 1}])

    manifest = capture_eia_api_dataset(
        Client(),
        "electricity/rto/region-data",
        {"facets[respondent][]": "US48"},
        tmp_path,
        "snap",
        "2026-08-13T08:00:00Z",
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["rows"] == 1
    assert "api_key" not in json.dumps(payload).lower()
