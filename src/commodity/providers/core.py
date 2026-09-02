from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests

from commodity.config import data_config


class MissingCredential(RuntimeError):
    pass


@dataclass
class EiaApiV2Client:
    session: requests.Session | None = None

    def _request_payload(
        self, route: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        cfg = data_config()["providers"]["eia_api_v2"]
        api_key = os.getenv(cfg["env_key"])
        if not api_key:
            raise MissingCredential(f"Missing environment variable: {cfg['env_key']}")
        query = dict(params or {})
        query["api_key"] = api_key
        url = f"{cfg['api_base'].rstrip('/')}/{route.strip('/')}/data/"
        response = (self.session or requests.Session()).get(url, params=query, timeout=30)
        try:
            response.raise_for_status()
        except requests.RequestException:
            status = getattr(response, "status_code", "unknown")
            raise RuntimeError(f"EIA API request failed with HTTP {status}") from None
        payload = response.json()
        if "response" not in payload or "data" not in payload["response"]:
            raise RuntimeError("EIA API response is missing response.data")
        return payload

    def fetch(self, route: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        return pd.DataFrame(self._request_payload(route, params)["response"]["data"])

    def fetch_all(
        self,
        route: str,
        params: dict[str, Any] | None = None,
        page_size: int = 5000,
        max_pages: int = 1000,
    ) -> pd.DataFrame:
        if page_size < 1 or max_pages < 1:
            raise ValueError("page_size and max_pages must be positive")
        rows: list[dict[str, Any]] = []
        base = dict(params or {})
        for page in range(max_pages):
            payload = self._request_payload(
                route, {**base, "offset": page * page_size, "length": page_size}
            )
            response = payload["response"]
            batch = response["data"]
            rows.extend(batch)
            raw_total = response.get("total")
            total = int(raw_total) if raw_total not in (None, "") else None
            if (total is not None and len(rows) >= total) or len(batch) < page_size:
                return pd.DataFrame(rows)
        raise RuntimeError("EIA pagination limit reached before response completion")

    def fetch_source(
        self, source_name: str, params: dict[str, Any] | None = None
    ) -> pd.DataFrame:
        source = data_config()["sources"][source_name]
        if source["provider"] != "eia_api_v2" or "route" not in source:
            raise ValueError(f"Source is not an EIA API v2 route: {source_name}")
        return self.fetch(source["route"], params=params)


@dataclass
class CftcCotSnapshotClient:
    session: requests.Session | None = None

    def fetch(self, limit: int = 5000) -> pd.DataFrame:
        data = data_config()
        cfg = data["sources"]["cftc_cot"]
        provider = data["providers"][cfg["provider"]]
        session = self.session or requests.Session()
        url = f"{provider['api_base'].rstrip('/')}/{cfg['dataset']}.json"
        params = {
            "$limit": limit,
            "$order": "report_date_as_yyyy_mm_dd ASC",
            "cftc_contract_market_code": cfg["contract_market_code"],
        }
        response = session.get(url, params=params, timeout=30)
        response.raise_for_status()
        frame = pd.DataFrame(response.json())
        if "report_date_as_yyyy_mm_dd" in frame.columns:
            frame["report_date_as_yyyy_mm_dd"] = pd.to_datetime(
                frame["report_date_as_yyyy_mm_dd"], utc=True
            )
        return frame
