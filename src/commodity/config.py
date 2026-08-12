from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"


def load_json(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def model_config() -> dict[str, Any]:
    return load_json("models.json")


def data_config() -> dict[str, Any]:
    return load_json("data_sources.json")


def policy_config() -> dict[str, Any]:
    return load_json("policy.json")


def experiment_config() -> dict[str, Any]:
    return load_json("experiment.json")


def signal_policy_config() -> dict[str, Any]:
    return load_json("signal_policy.json")


def simulation_config() -> dict[str, Any]:
    return load_json("simulation.json")
