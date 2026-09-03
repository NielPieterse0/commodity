from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from commodity.config import data_config
from commodity.data_assurance import canonical_json_sha256, canonical_records_sha256
from commodity.market_data import (
    DataContractViolation,
    build_contract_rank_windows,
    validate_contract_history,
    validate_contract_metadata,
)
from commodity.providers import MissingCredential
from commodity.snapshots import SnapshotIntegrityError, SnapshotWriter, verify_snapshot

_SOURCE_COMPONENT_HASH_ALGORITHM = "canonical-records-column-order-invariant-v1"


class MassiveRateLimitError(RuntimeError):
    pass


@dataclass
class MassiveFuturesClient:
    session: requests.Session | None = None
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    minimum_interval_seconds: float = 0.0
    max_retries: int = 4
    base_backoff_seconds: float = 1.0
    _last_request_at: float | None = field(default=None, init=False, repr=False)

    def _pace_request(self) -> None:
        if self.minimum_interval_seconds <= 0 or self._last_request_at is None:
            return
        remaining = self.minimum_interval_seconds - (self.monotonic() - self._last_request_at)
        if remaining > 0:
            self.sleep(remaining)

    def _request_page(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = data_config()["providers"]["massive_futures"]
        api_key = os.getenv(cfg["env_key"])
        if not api_key:
            raise MissingCredential(f"Missing environment variable: {cfg['env_key']}")
        headers = {"Authorization": f"Bearer {api_key}"}
        query = dict(params or {})
        for attempt in range(self.max_retries + 1):
            self._pace_request()
            response = (self.session or requests.Session()).get(
                url, params=query, headers=headers, timeout=30
            )
            self._last_request_at = self.monotonic()
            status = int(getattr(response, "status_code", 200))
            if status == 429:
                if attempt >= self.max_retries:
                    raise MassiveRateLimitError(
                        f"Massive rate limit remained active after {self.max_retries} retries"
                    )
                raw_retry = getattr(response, "headers", {}).get("Retry-After")
                try:
                    delay = float(raw_retry) if raw_retry is not None else None
                except (TypeError, ValueError):
                    delay = None
                self.sleep(delay if delay is not None and delay >= 0 else self.base_backoff_seconds * (2**attempt))
                continue
            if status in {408, 425, 500, 502, 503, 504}:
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        f"Massive transient HTTP {status} remained after {self.max_retries} retries"
                    )
                self.sleep(self.base_backoff_seconds * (2**attempt))
                continue
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") not in (None, "OK"):
                raise RuntimeError(f"Massive request failed with status: {payload.get('status')}")
            return payload
        raise AssertionError("unreachable Massive retry state")

    def _paged_results(
        self, url: str, params: dict[str, Any], max_pages: int
    ) -> list[dict[str, Any]]:
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        rows: list[dict[str, Any]] = []
        current_params: dict[str, Any] | None = params
        for _ in range(max_pages):
            payload = self._request_page(url, current_params)
            rows.extend(payload.get("results", []))
            next_url = payload.get("next_url")
            if not next_url:
                return rows
            url = str(next_url)
            current_params = {}
        raise RuntimeError("Massive pagination limit reached before response completion")

    def list_outright_contracts(
        self,
        product_code: str,
        max_pages: int = 100,
        start_trade_date: str | None = None,
        end_trade_date: str | None = None,
    ) -> list[dict[str, Any]]:
        cfg = data_config()["providers"]["massive_futures"]
        url = f"{cfg['api_base'].rstrip('/')}/futures/v1/contracts"
        base = {
            "product_code": product_code,
            "ticker.gte": f"{product_code}F0",
            "ticker.lt": f"{product_code}~",
            "limit": 1000,
            "sort": "ticker.asc",
        }
        pattern = re.compile(rf"^{re.escape(product_code)}[FGHJKMNQUVXZ]\d{{1,2}}$")
        by_ticker: dict[str, dict[str, Any]] = {}
        boundary_dates = list(
            dict.fromkeys(value for value in (start_trade_date, end_trade_date) if value)
        )
        if boundary_dates:
            for point_in_time in boundary_dates:
                for row in self._paged_results(url, {**base, "date": point_in_time}, max_pages):
                    ticker = str(row.get("ticker", ""))
                    if pattern.fullmatch(ticker):
                        by_ticker[ticker] = row
        else:
            for row in self._paged_results(url, {**base, "sort": "ticker.asc,date.asc"}, max_pages):
                ticker = str(row.get("ticker", ""))
                if pattern.fullmatch(ticker):
                    by_ticker[ticker] = row
        return [by_ticker[ticker] for ticker in sorted(by_ticker)]

    def fetch_session_aggregates(
        self,
        ticker: str,
        start_trade_date: str,
        end_trade_date: str,
        max_pages: int = 100,
    ) -> pd.DataFrame:
        cfg = data_config()["providers"]["massive_futures"]
        url = f"{cfg['api_base'].rstrip('/')}/futures/v1/aggs/{ticker}"
        params = {
            "resolution": "1session",
            "window_start.gte": (pd.Timestamp(start_trade_date) - pd.Timedelta(days=1)).date().isoformat(),
            "window_start.lte": (pd.Timestamp(end_trade_date) - pd.Timedelta(days=1)).date().isoformat(),
            "limit": 50000,
            "sort": "window_start.asc",
        }
        frame = pd.DataFrame(self._paged_results(url, params, max_pages))
        if "session_end_date" in frame.columns:
            dates = pd.to_datetime(frame["session_end_date"], errors="coerce")
            frame = frame[
                (dates >= pd.Timestamp(start_trade_date))
                & (dates <= pd.Timestamp(end_trade_date))
            ].reset_index(drop=True)
        return frame

    def fetch_schedules(
        self,
        product_code: str,
        start_trade_date: str,
        end_trade_date: str,
        max_pages: int = 100,
        chunk_days: int = 90,
    ) -> list[dict[str, Any]]:
        if chunk_days < 1:
            raise ValueError("chunk_days must be positive")
        start = pd.Timestamp(start_trade_date)
        end = pd.Timestamp(end_trade_date)
        if end < start:
            raise ValueError("end_trade_date must be on or after start_trade_date")
        cfg = data_config()["providers"]["massive_futures"]
        url = f"{cfg['api_base'].rstrip('/')}/futures/v1/schedules"
        rows: list[dict[str, Any]] = []
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(chunk_start + pd.Timedelta(days=chunk_days - 1), end)
            rows.extend(
                self._paged_results(
                    url,
                    {
                        "product_code": product_code,
                        "session_end_date.gte": chunk_start.date().isoformat(),
                        "session_end_date.lte": chunk_end.date().isoformat(),
                        "limit": 1000,
                    },
                    max_pages,
                )
            )
            chunk_start = chunk_end + pd.Timedelta(days=1)
        unique: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in rows:
            key = (
                row.get("product_code"),
                row.get("session_end_date"),
                row.get("event"),
                row.get("timestamp"),
                row.get("trading_venue"),
            )
            unique[key] = row
        return sorted(
            unique.values(),
            key=lambda row: (
                str(row.get("session_end_date", "")),
                str(row.get("timestamp", "")),
                str(row.get("event", "")),
            ),
        )


def normalize_massive_contract_history(
    contract: dict[str, Any], aggregates: pd.DataFrame, retrieved_at: str
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required_contract = ("ticker", "product_code", "last_trade_date", "trading_venue")
    missing_contract = [field for field in required_contract if not contract.get(field)]
    if missing_contract:
        raise DataContractViolation(f"Massive contract metadata missing fields: {missing_contract}")
    required_aggregate = ("session_end_date", "settlement_price")
    missing_aggregate = [field for field in required_aggregate if field not in aggregates.columns]
    if missing_aggregate:
        raise DataContractViolation(f"Massive aggregates missing fields: {missing_aggregate}")
    if aggregates.empty:
        raise DataContractViolation("Massive aggregates are empty")
    out = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(aggregates["session_end_date"], utc=True),
            "contract_id": str(contract["ticker"]),
            "expiration": pd.to_datetime(contract["last_trade_date"], utc=True),
            "settle": pd.to_numeric(aggregates["settlement_price"], errors="coerce"),
        }
    )
    for source in ("open", "high", "low", "close", "volume"):
        if source in aggregates.columns:
            out[source] = aggregates[source].values
    if out["settle"].isna().any():
        raise DataContractViolation("Massive aggregates contain missing settlement prices")
    source_identity = {
        "contract": contract,
        "aggregate_records_sha256": canonical_records_sha256(aggregates),
    }
    metadata = {
        "source_id": "massive_futures_rest_v1",
        "source_sha256": canonical_json_sha256(source_identity),
        "retrieved_at": retrieved_at,
        "exchange": contract["trading_venue"],
        "product_code": contract["product_code"],
        "session_timezone": "America/Chicago",
        "calendar": "CME_NYMEX",
        "price_semantics": "massive_session_settlement_price",
    }
    return out, metadata


def fetch_massive_canonical_history(
    client: Any,
    schema: dict[str, Any],
    product_code: str,
    start_trade_date: str,
    end_trade_date: str,
    retrieved_at: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    start = pd.Timestamp(start_trade_date, tz="UTC")
    end = pd.Timestamp(end_trade_date, tz="UTC")
    if end < start:
        raise ValueError("end_trade_date must be on or after start_trade_date")
    contracts = client.list_outright_contracts(
        product_code,
        start_trade_date=start_trade_date,
        end_trade_date=end_trade_date,
    )
    frames: list[pd.DataFrame] = []
    components: list[dict[str, Any]] = []
    exchanges: set[str] = set()
    for contract in contracts:
        first = pd.to_datetime(contract.get("first_trade_date"), utc=True, errors="coerce")
        last = pd.to_datetime(contract.get("last_trade_date"), utc=True, errors="coerce")
        if pd.isna(last):
            raise DataContractViolation(
                f"Massive contract {contract.get('ticker', '<unknown>')} is missing a valid last_trade_date"
            )
        if last < start or (not pd.isna(first) and first > end):
            continue
        fetch_start = max(start, first) if not pd.isna(first) else start
        fetch_end = min(end, last)
        aggregates = client.fetch_session_aggregates(
            str(contract["ticker"]), fetch_start.date().isoformat(), fetch_end.date().isoformat()
        )
        if aggregates.empty:
            continue
        normalized, metadata = normalize_massive_contract_history(contract, aggregates, retrieved_at)
        validate_contract_metadata(metadata, schema)
        frames.append(normalized)
        exchanges.add(str(metadata["exchange"]))
        components.append(
            {"contract_id": str(contract["ticker"]), "source_sha256": metadata["source_sha256"]}
        )
    if not frames:
        raise DataContractViolation("Massive returned no canonical contract history for range")
    if len(exchanges) != 1:
        raise DataContractViolation(
            f"Massive canonical history spans multiple trading venues: {sorted(exchanges)}"
        )
    combined = validate_contract_history(pd.concat(frames, ignore_index=True), schema)
    metadata = {
        "source_id": "massive_futures_rest_v1",
        "source_sha256": hashlib.sha256(
            json.dumps(components, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "retrieved_at": retrieved_at,
        "exchange": next(iter(exchanges)),
        "product_code": product_code,
        "session_timezone": "America/Chicago",
        "calendar": "CME_NYMEX",
        "price_semantics": "massive_session_settlement_price",
        "source_contract_count": len(components),
        "source_contracts": components,
    }
    validate_contract_metadata(metadata, schema)
    return combined, metadata


def _artifact_map(writer: SnapshotWriter) -> dict[str, dict[str, Any]]:
    return {str(item["path"]): item for item in writer.artifacts}


def _load_checkpoint(
    writer: SnapshotWriter, request: dict[str, Any], retrieved_at: str
) -> str:
    path = writer.snapshot_dir / ".checkpoint.json"
    if not path.exists():
        return retrieved_at
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("request") != request:
        raise SnapshotIntegrityError("Massive checkpoint request does not match requested capture")
    writer.artifacts = list(payload.get("artifacts", []))
    for artifact in writer.artifacts:
        file_path = writer.snapshot_dir / artifact["path"]
        if not file_path.is_file():
            raise SnapshotIntegrityError(f"Massive checkpoint artifact missing: {file_path}")
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if file_path.stat().st_size != artifact["bytes"] or digest != artifact["sha256"]:
            raise SnapshotIntegrityError(f"Massive checkpoint artifact changed: {file_path}")
    return str(payload["retrieved_at"])


def _save_checkpoint(
    writer: SnapshotWriter, request: dict[str, Any], retrieved_at: str
) -> None:
    writer.snapshot_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "request": request,
        "retrieved_at": retrieved_at,
        "artifacts": sorted(writer.artifacts, key=lambda item: item["path"]),
    }
    temp = writer.snapshot_dir / ".checkpoint.json.tmp"
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(temp, writer.snapshot_dir / ".checkpoint.json")


def reconstruct_massive_archive(
    manifest_path: Path,
    schema: dict[str, Any],
) -> pd.DataFrame:
    """Rebuild a completed Massive archive from retained raw artifacts and verify exact canonical equality."""
    manifest_path = Path(manifest_path)
    verify_snapshot(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("source_id") != "massive_futures_rest_v1":
        raise DataContractViolation("Massive archive has unexpected source identity")

    root = manifest_path.parent
    contracts = json.loads((root / "contracts.json").read_text(encoding="utf-8"))
    contracts_by_ticker = {str(contract.get("ticker")): contract for contract in contracts}
    components = list(payload.get("source_contracts", []))
    if not components:
        raise DataContractViolation("Massive archive lacks retained source components")

    frames: list[pd.DataFrame] = []
    exchanges: set[str] = set()
    retrieved_at = str(payload.get("retrieved_at", ""))
    component_hash_algorithm = payload.get("source_component_hash_algorithm")
    if component_hash_algorithm not in {None, _SOURCE_COMPONENT_HASH_ALGORITHM}:
        raise DataContractViolation(
            f"Massive archive uses unsupported source component hash algorithm: {component_hash_algorithm}"
        )
    for component in components:
        ticker = str(component.get("contract_id", ""))
        contract = contracts_by_ticker.get(ticker)
        if contract is None:
            raise DataContractViolation(f"Massive archive contract metadata missing for {ticker}")
        raw_path = root / "aggregates" / f"{ticker}.json"
        aggregates = pd.DataFrame(json.loads(raw_path.read_text(encoding="utf-8")))
        normalized, metadata = normalize_massive_contract_history(contract, aggregates, retrieved_at)
        validate_contract_metadata(metadata, schema)
        if component_hash_algorithm == _SOURCE_COMPONENT_HASH_ALGORITHM:
            recorded_source_sha256 = str(component.get("source_sha256", ""))
            if recorded_source_sha256 != str(metadata["source_sha256"]):
                raise DataContractViolation(f"Massive archive source identity differs for {ticker}")
        if len(normalized) != int(component.get("rows", -1)):
            raise DataContractViolation(f"Massive archive row count differs for {ticker}")
        frames.append(normalized)
        exchanges.add(str(metadata["exchange"]))

    if len(exchanges) != 1:
        raise DataContractViolation(f"Massive archive spans multiple venues: {sorted(exchanges)}")
    reconstructed = validate_contract_history(pd.concat(frames, ignore_index=True), schema)
    stored = validate_contract_history(pd.read_csv(root / "canonical.csv"), schema)
    try:
        pd.testing.assert_frame_equal(reconstructed, stored, check_exact=True)
    except AssertionError as exc:
        raise DataContractViolation("Massive canonical reconstruction differs from retained canonical.csv") from exc
    return reconstructed


def capture_massive_archive(
    client: Any,
    schema: dict[str, Any],
    product_code: str,
    start_trade_date: str,
    end_trade_date: str,
    retrieved_at: str,
    snapshot_root: Path,
    snapshot_id: str,
    max_contracts: int = 12,
) -> Path:
    if max_contracts < 1:
        raise ValueError("max_contracts must be positive")
    writer = SnapshotWriter(Path(snapshot_root), "massive", snapshot_id)
    final_manifest = writer.snapshot_dir / "manifest.json"
    if final_manifest.exists():
        raise FileExistsError(f"Immutable Massive snapshot already completed: {final_manifest}")
    request: dict[str, Any] = {
        "product_code": product_code,
        "start_trade_date": start_trade_date,
        "end_trade_date": end_trade_date,
        "max_contracts": max_contracts,
    }
    archive_retrieved_at = _load_checkpoint(writer, request, retrieved_at)
    artifacts = _artifact_map(writer)

    if "contracts.json" in artifacts:
        contracts = json.loads((writer.snapshot_dir / "contracts.json").read_text(encoding="utf-8"))
    else:
        contracts = client.list_outright_contracts(
            product_code,
            start_trade_date=start_trade_date,
            end_trade_date=end_trade_date,
        )
        writer.write_bytes(
            "contracts.json",
            (json.dumps(contracts, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8"),
        )
        _save_checkpoint(writer, request, archive_retrieved_at)
        artifacts = _artifact_map(writer)

    if "schedules.json" not in artifacts:
        schedules = client.fetch_schedules(product_code, start_trade_date, end_trade_date)
        writer.write_bytes(
            "schedules.json",
            (json.dumps(schedules, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8"),
        )
        _save_checkpoint(writer, request, archive_retrieved_at)
        artifacts = _artifact_map(writer)

    windows = build_contract_rank_windows(
        contracts, start_trade_date, end_trade_date, max_contracts
    )
    frames: list[pd.DataFrame] = []
    components: list[dict[str, Any]] = []
    exchanges: set[str] = set()
    for contract, fetch_start, fetch_end in windows:
        ticker = str(contract["ticker"])
        raw_name = f"aggregates/{ticker}.json"
        if raw_name in artifacts:
            aggregates = pd.DataFrame(
                json.loads((writer.snapshot_dir / raw_name).read_text(encoding="utf-8"))
            )
        else:
            aggregates = client.fetch_session_aggregates(ticker, fetch_start, fetch_end)
            writer.write_bytes(
                raw_name,
                (
                    json.dumps(
                        aggregates.to_dict(orient="records"),
                        indent=2,
                        sort_keys=True,
                        default=str,
                    )
                    + "\n"
                ).encode("utf-8"),
            )
            _save_checkpoint(writer, request, archive_retrieved_at)
            artifacts = _artifact_map(writer)
        if aggregates.empty:
            continue
        normalized, metadata = normalize_massive_contract_history(
            contract, aggregates, archive_retrieved_at
        )
        validate_contract_metadata(metadata, schema)
        frames.append(normalized)
        exchanges.add(str(metadata["exchange"]))
        components.append(
            {
                "contract_id": ticker,
                "source_sha256": metadata["source_sha256"],
                "rows": len(normalized),
            }
        )
    if not frames:
        raise DataContractViolation("Massive archive contained no canonical rows for selected range")
    if len(exchanges) != 1:
        raise DataContractViolation(f"Massive archive spans multiple venues: {sorted(exchanges)}")
    canonical = validate_contract_history(pd.concat(frames, ignore_index=True), schema)
    writer.write_bytes("canonical.csv", canonical.to_csv(index=False).encode("utf-8"))
    manifest = writer.finalize(
        {
            "source_id": "massive_futures_rest_v1",
            "retrieved_at": archive_retrieved_at,
            "request": request,
            "curve_selection": "expiration_rank_per_trade_date",
            "exchange": next(iter(exchanges)),
            "source_contract_count": len(components),
            "source_contracts": components,
            "source_component_hash_algorithm": _SOURCE_COMPONENT_HASH_ALGORITHM,
            "canonical_rows": len(canonical),
            "redistribution_allowed": False,
            "non_display_backtesting_rights_verified": False,
            "canonical_backtest_evidence_allowed": False,
        }
    )
    checkpoint = writer.snapshot_dir / ".checkpoint.json"
    if checkpoint.exists():
        checkpoint.unlink()
    return manifest


@dataclass
class MassiveCanonicalFuturesProvider:
    client: MassiveFuturesClient | None = None

    def fetch_contract_history(
        self,
        schema: dict[str, Any],
        product_code: str,
        start_trade_date: str,
        end_trade_date: str,
        retrieved_at: str,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        return fetch_massive_canonical_history(
            self.client or MassiveFuturesClient(),
            schema,
            product_code,
            start_trade_date,
            end_trade_date,
            retrieved_at,
        )

    def capture_archive(
        self,
        schema: dict[str, Any],
        product_code: str,
        start_trade_date: str,
        end_trade_date: str,
        retrieved_at: str,
        snapshot_root: Path,
        snapshot_id: str,
        max_contracts: int,
    ) -> Path:
        cfg = data_config()["providers"]["massive_futures"]
        client = self.client or MassiveFuturesClient(
            minimum_interval_seconds=float(cfg["minimum_request_interval_seconds"])
        )
        return capture_massive_archive(
            client,
            schema,
            product_code,
            start_trade_date,
            end_trade_date,
            retrieved_at,
            snapshot_root,
            snapshot_id,
            max_contracts=max_contracts,
        )


def create_provider() -> MassiveCanonicalFuturesProvider:
    cfg = data_config()["providers"]["massive_futures"]
    client = MassiveFuturesClient(
        minimum_interval_seconds=float(cfg["minimum_request_interval_seconds"])
    )
    return MassiveCanonicalFuturesProvider(client=client)
