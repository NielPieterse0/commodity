from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from commodity.config import data_config
from commodity.providers import EiaApiV2Client
from commodity.snapshots import SnapshotWriter


@dataclass
class EiaBulkClient:
    session: requests.Session | None = None

    def fetch(self, dataset_id: str) -> tuple[bytes, str]:
        cfg = data_config()["providers"]["eia_bulk"]
        url = cfg["dataset_url_template"].format(dataset_id=dataset_id)
        response = (self.session or requests.Session()).get(url, timeout=60)
        try:
            response.raise_for_status()
        except requests.RequestException:
            status = getattr(response, "status_code", "unknown")
            raise RuntimeError(f"EIA bulk request failed with HTTP {status}") from None
        return response.content, url


def capture_eia_bulk_dataset(
    client: EiaBulkClient,
    dataset_id: str,
    snapshot_root: Path,
    snapshot_id: str,
    retrieved_at: str,
) -> Path:
    content, source_url = client.fetch(dataset_id)
    writer = SnapshotWriter(Path(snapshot_root), "eia", snapshot_id)
    writer.write_bytes(f"{dataset_id}.zip", content)
    return writer.finalize(
        {
            "source_id": "eia_open_data_bulk",
            "dataset_id": dataset_id,
            "source_url": source_url,
            "retrieved_at": retrieved_at,
            "point_in_time_backtest_ready": False,
            "note": "Current-state historical snapshot; release/revision vintages require separate reconstruction.",
        }
    )


def capture_eia_api_dataset(
    client: EiaApiV2Client,
    route: str,
    params: dict[str, Any],
    snapshot_root: Path,
    snapshot_id: str,
    retrieved_at: str,
) -> Path:
    frame = client.fetch_all(route, params)
    writer = SnapshotWriter(Path(snapshot_root), "eia_api", snapshot_id)
    writer.write_bytes("data.csv", frame.to_csv(index=False).encode("utf-8"))
    safe_query = json.loads(json.dumps(params, default=str))
    return writer.finalize(
        {
            "source_id": "eia_api_v2",
            "route": route,
            "query": safe_query,
            "retrieved_at": retrieved_at,
            "rows": len(frame),
            "point_in_time_backtest_ready": False,
            "note": "Snapshot preserves retrieval state; historical revision/availability reconstruction is separate.",
        }
    )
