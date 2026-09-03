from __future__ import annotations

import json
import os
import sysconfig
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CONFIG_DIR = REPO_ROOT / "config"
INSTALLED_CONFIG_DIR = (
    Path(sysconfig.get_path("data")) / "share" / "commodity-research" / "config"
)


def _config_dir() -> Path:
    override = os.environ.get("COMMODITY_CONFIG_DIR")
    candidates = [Path(override)] if override else [SOURCE_CONFIG_DIR, INSTALLED_CONFIG_DIR]
    for path in candidates:
        if path.is_dir():
            return path
    raise FileNotFoundError(f"Commodity config directory not found; checked: {candidates}")


def config_path(name: str) -> Path:
    """Resolve the exact config file used by runtime configuration loading."""
    return _config_dir() / name


def load_json(name: str) -> dict[str, Any]:
    path = config_path(name)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def model_config() -> dict[str, Any]:
    return load_json("models.json")


def data_config() -> dict[str, Any]:
    return load_json("data_sources.json")


def policy_config() -> dict[str, Any]:
    return load_json("trading-policy.json")


def research_dataset_config() -> dict[str, Any]:
    return load_json("research_dataset.json")


def assumptions_config() -> dict[str, Any]:
    return load_json("assumptions.json")


def signal_policy_config() -> dict[str, Any]:
    return load_json("signal_policy.json")


def simulation_config() -> dict[str, Any]:
    return load_json("simulation.json")
