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

    def fetch(self, route: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        cfg = data_config()["providers"]["eia_api_v2"]
        api_key = os.getenv(cfg["env_key"])
        if not api_key:
            raise MissingCredential(f"Missing environment variable: {cfg['env_key']}")
        session = self.session or requests.Session()
        query = dict(params or {})
        query["api_key"] = api_key
        url = f"{cfg['api_base'].rstrip('/')}/{route.strip('/')}/data/"
        response = session.get(url, params=query, timeout=30)
        response.raise_for_status()
        payload = response.json()
        return pd.DataFrame(payload["response"]["data"])

    def fetch_source(
        self,
        source_name: str,
        params: dict[str, Any] | None = None,
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


def require_point_in_time_ready(
    frame: pd.DataFrame,
    observation_col: str | None = None,
) -> None:
    if "available_at" not in frame.columns:
        raise ValueError("Dataset is not backtest-ready: missing actual available_at timestamps")
    available = pd.to_datetime(frame["available_at"], utc=True, errors="coerce")
    if available.isna().any():
        raise ValueError("Dataset is not backtest-ready: invalid available_at timestamps")
    if observation_col is not None:
        if observation_col not in frame.columns:
            raise ValueError(f"Dataset is missing observation timestamp column: {observation_col}")
        observed = pd.to_datetime(frame[observation_col], utc=True, errors="coerce")
        if observed.isna().any():
            raise ValueError(f"Dataset has invalid {observation_col} timestamps")
        if (available < observed).any():
            raise ValueError("Dataset has available_at earlier than its observation timestamp")
