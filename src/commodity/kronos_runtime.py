from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path
from typing import Any


class KronosRuntimeError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


RUNTIME_LOCK_PATH = "requirements.kronos-cpu.lock.txt"


def _lock_metadata(lock_path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for raw in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("# ") or ": " not in line:
            continue
        key, value = line[2:].split(": ", 1)
        if key in {"python", "platform", "torch"}:
            metadata[key] = value
    required = {"python", "platform", "torch"}
    if set(metadata) != required:
        raise KronosRuntimeError("Kronos runtime lock metadata is incomplete")
    return metadata


def _locked_packages(lock_path: Path) -> dict[str, str]:
    packages: dict[str, str] = {}
    for raw in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "--")):
            continue
        if "==" not in line:
            raise KronosRuntimeError(f"Kronos runtime lock contains an unpinned requirement: {line}")
        name, version = line.split("==", 1)
        packages[name.strip()] = version.strip()
    return packages


def runtime_lock_authority(repo_root: Path) -> dict[str, Any]:
    lock_path = repo_root / RUNTIME_LOCK_PATH
    if not lock_path.is_file():
        raise KronosRuntimeError(f"Kronos runtime lock is missing: {lock_path}")
    metadata = _lock_metadata(lock_path)
    packages = _locked_packages(lock_path)
    if packages.get("torch") != metadata["torch"]:
        raise KronosRuntimeError("Kronos runtime lock Torch metadata does not match its pinned package")
    return {
        "path": RUNTIME_LOCK_PATH,
        "sha256": _sha256_file(lock_path),
        "python": metadata["python"],
        "platform": metadata["platform"],
        "torch": metadata["torch"],
        "packages": packages,
    }


def validate_installed_runtime(repo_root: Path) -> dict[str, Any]:
    authority = runtime_lock_authority(repo_root)
    observed_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    if observed_python != authority["python"]:
        raise KronosRuntimeError(
            f"Kronos runtime Python mismatch: expected {authority['python']}, observed {observed_python}"
        )
    observed_platform = "windows_x86_64" if sys.platform == "win32" and platform.machine().lower() in {"amd64", "x86_64"} else f"{sys.platform}_{platform.machine().lower()}"
    if observed_platform != authority["platform"]:
        raise KronosRuntimeError(
            f"Kronos runtime platform mismatch: expected {authority['platform']}, observed {observed_platform}"
        )
    installed: dict[str, str] = {}
    for package, expected in authority["packages"].items():
        try:
            observed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            raise KronosRuntimeError(f"Kronos runtime package is missing: {package}") from exc
        if observed != expected:
            raise KronosRuntimeError(
                f"Kronos runtime package mismatch for {package}: expected {expected}, observed {observed}"
            )
        installed[package] = observed
    return {**authority, "installed_packages": installed}


def synthetic_cpu_replay(repo_root: Path) -> dict[str, Any]:
    runtime = validate_installed_runtime(repo_root)
    import torch

    if torch.cuda.is_available():
        raise KronosRuntimeError("Kronos governed runtime must remain CPU-only")

    def sample() -> list[int]:
        torch.manual_seed(0)
        probabilities = torch.tensor([0.05, 0.15, 0.30, 0.50], dtype=torch.float32)
        return torch.multinomial(probabilities, num_samples=32, replacement=True).tolist()

    primary = sample()
    replay = sample()
    if primary != replay:
        raise KronosRuntimeError("Kronos synthetic CPU replay is not deterministic")
    replay_sha256 = hashlib.sha256(
        json.dumps(primary, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "runtime_lock_sha256": runtime["sha256"],
        "python": runtime["python"],
        "platform": runtime["platform"],
        "torch": runtime["torch"],
        "synthetic_replay_sha256": replay_sha256,
        "synthetic_replay_count": len(primary),
        "device": "cpu",
    }
