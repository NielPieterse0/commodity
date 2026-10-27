"""Causal, contract-grain market-truth foundations; adapters supply market semantics."""

from .core import (
    MarketTruthError,
    build_market_truth,
    curve_asof,
    normalize_bars,
    normalize_definitions,
    normalize_statistics,
    publish_parquet,
    snapshot_asof,
)
from .ng import normalize_ng_databento
from .query import MarketTruthDataset

__all__ = [
    "MarketTruthDataset",
    "MarketTruthError",
    "build_market_truth",
    "curve_asof",
    "normalize_bars",
    "normalize_definitions",
    "normalize_ng_databento",
    "normalize_statistics",
    "publish_parquet",
    "snapshot_asof",
]
