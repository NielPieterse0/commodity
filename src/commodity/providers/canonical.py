from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any, Protocol

import pandas as pd


class ProviderLoadError(RuntimeError):
    pass


class CanonicalFuturesProvider(Protocol):
    def fetch_contract_history(
        self,
        schema: dict[str, Any],
        product_code: str,
        start_trade_date: str,
        end_trade_date: str,
        retrieved_at: str,
    ) -> tuple[pd.DataFrame, dict[str, Any]]: ...

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
    ) -> Path: ...


def load_canonical_provider(provider_id: str) -> CanonicalFuturesProvider:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", provider_id):
        raise ProviderLoadError(f"Invalid canonical provider id: {provider_id!r}")
    module_name = f"commodity.providers.{provider_id}"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            raise
        raise ProviderLoadError(
            f"Canonical provider adapter is unavailable: {provider_id}"
        ) from exc
    factory = getattr(module, "create_provider", None)
    if not callable(factory):
        raise ProviderLoadError(
            f"Canonical provider adapter {module_name} must expose create_provider()"
        )
    return factory()
