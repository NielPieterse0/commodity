from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from commodity.config import REPO_ROOT, model_config


class KronosArtifactError(RuntimeError):
    """Raised when a pinned Kronos artifact cannot be resolved exactly."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_kronos_source_checkout(path: Path, expected_revision: str) -> str:
    source = path.resolve()
    if not source.is_dir():
        raise KronosArtifactError(f"Kronos source checkout is missing: {source}")
    try:
        top_level = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if Path(top_level).resolve() != source:
            raise KronosArtifactError("Kronos source checkout is not initialized as its own Git worktree")
        head = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip().lower()
        status = subprocess.run(
            ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise KronosArtifactError("Unable to verify the vendored Kronos source checkout") from exc
    if head != str(expected_revision).lower():
        raise KronosArtifactError(
            f"Kronos source revision mismatch: expected {expected_revision}, observed {head}"
        )
    if status.strip():
        raise KronosArtifactError("Kronos source checkout must be clean before inference")
    return head


def _resolve_pinned_snapshot(cfg: dict[str, Any], role: str) -> dict[str, str]:
    if cfg.get("local_files_only") is not True:
        raise KronosArtifactError("Kronos checkpoint loading must remain local-files-only")
    cache_env = cfg.get("checkpoint_cache_env")
    if not isinstance(cache_env, str) or not cache_env:
        raise KronosArtifactError("Kronos checkpoint cache environment variable is not configured")
    cache_value = os.environ.get(cache_env)
    if not cache_value:
        raise KronosArtifactError(
            f"Set {cache_env} to the preflighted local Kronos checkpoint cache before use"
        )
    cache_dir = Path(cache_value).expanduser().resolve()
    if not cache_dir.is_dir():
        raise KronosArtifactError(f"Kronos checkpoint cache does not exist: {cache_dir}")

    if role == "model":
        repo_id = cfg["model_id"]
        revision = cfg["model_revision"]
    elif role == "tokenizer":
        repo_id = cfg["tokenizer_id"]
        revision = cfg["tokenizer_revision"]
    else:
        raise KronosArtifactError(f"Unsupported Kronos artifact role: {role}")

    artifact_cfg = cfg.get("checkpoint_artifacts", {}).get(role)
    if not isinstance(artifact_cfg, dict):
        raise KronosArtifactError(f"Missing pinned Kronos {role} artifact identity")
    filename = artifact_cfg.get("filename")
    expected_sha256 = artifact_cfg.get("sha256")
    if not isinstance(filename, str) or not filename:
        raise KronosArtifactError(f"Missing pinned Kronos {role} artifact filename")
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise KronosArtifactError(f"Missing pinned Kronos {role} artifact SHA-256")

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise KronosArtifactError(
            "Install the 'kronos' extra before resolving pinned Kronos checkpoints"
        ) from exc

    try:
        snapshot = Path(
            snapshot_download(
                repo_id=repo_id,
                revision=revision,
                cache_dir=str(cache_dir),
                local_files_only=True,
                allow_patterns=["config.json", filename],
            )
        ).resolve()
    except Exception as exc:
        raise KronosArtifactError(
            f"Pinned Kronos {role} revision is not present in the configured local cache"
        ) from exc

    artifact_path = snapshot / filename
    if not artifact_path.is_file():
        raise KronosArtifactError(f"Pinned Kronos {role} artifact is missing: {artifact_path}")
    observed_sha256 = _sha256_file(artifact_path)
    if observed_sha256 != expected_sha256:
        raise KronosArtifactError(
            f"Pinned Kronos {role} artifact hash mismatch: expected {expected_sha256}, "
            f"observed {observed_sha256}"
        )
    return {
        "repo_id": repo_id,
        "revision": revision,
        "snapshot_path": str(snapshot),
        "artifact_path": str(artifact_path),
        "artifact_sha256": observed_sha256,
    }


def resolve_kronos_artifacts(cfg: dict[str, Any] | None = None) -> dict[str, dict[str, str]]:
    """Resolve and hash the exact pinned model/tokenizer snapshots without inference."""
    resolved_cfg = cfg if cfg is not None else model_config()["models"]["kronos_mini"]
    return {
        "model": _resolve_pinned_snapshot(resolved_cfg, "model"),
        "tokenizer": _resolve_pinned_snapshot(resolved_cfg, "tokenizer"),
    }


class KronosMiniAdapter:
    def __init__(self) -> None:
        cfg = model_config()["models"]["kronos_mini"]
        local_path = REPO_ROOT / cfg["local_path"]
        if not local_path.exists():
            raise RuntimeError("Kronos source is not installed under vendor/Kronos")
        source_revision = cfg.get("source_revision")
        if not isinstance(source_revision, str):
            raise KronosArtifactError("Kronos source revision is not configured")
        verify_kronos_source_checkout(local_path, source_revision)
        import_path = str(local_path)
        if import_path not in sys.path:
            sys.path.insert(0, import_path)
        try:
            from model import Kronos, KronosPredictor, KronosTokenizer
        except ImportError as exc:
            raise RuntimeError("Install the 'kronos' extra before using Kronos") from exc

        artifacts = resolve_kronos_artifacts(cfg)
        tokenizer = KronosTokenizer.from_pretrained(artifacts["tokenizer"]["snapshot_path"])
        model = Kronos.from_pretrained(artifacts["model"]["snapshot_path"])
        self.predictor = KronosPredictor(
            model, tokenizer, device=cfg["device"], max_context=cfg["max_context"]
        )
        self.artifact_manifest = artifacts
        self.inference = dict(cfg["inference"])

    def forecast(self, ohlcv: pd.DataFrame, future_index: pd.DatetimeIndex) -> pd.DataFrame:
        x = ohlcv[["open", "high", "low", "close", "volume"]].copy()
        return self.predictor.predict(
            df=x,
            x_timestamp=pd.Series(x.index),
            y_timestamp=pd.Series(future_index),
            pred_len=len(future_index),
            T=float(self.inference["T"]),
            top_p=float(self.inference["top_p"]),
            sample_count=int(self.inference["sample_count"]),
            verbose=bool(self.inference["verbose"]),
        )


class KronosCheckpointAdapter:
    """Load one explicitly named pinned checkpoint for the #180 successor run."""

    ALLOWED_MODEL_KEYS = frozenset({"kronos_mini", "kronos_small", "kronos_base"})

    def __init__(self, model_key: str, inference: Mapping[str, Any]) -> None:
        if model_key not in self.ALLOWED_MODEL_KEYS:
            raise KronosArtifactError(f"unsupported Kronos checkpoint: {model_key}")
        cfg = model_config()["models"][model_key]
        expected_inference = {"T", "top_p", "sample_count", "verbose"}
        if set(inference) != expected_inference:
            raise KronosArtifactError("Kronos confirmation inference profile is incomplete")
        self.inference = dict(inference)
        local_path = REPO_ROOT / cfg["local_path"]
        source_revision = cfg.get("source_revision")
        if not isinstance(source_revision, str):
            raise KronosArtifactError("Kronos source revision is not configured")
        verify_kronos_source_checkout(local_path, source_revision)
        import_path = str(local_path)
        if import_path not in sys.path:
            sys.path.insert(0, import_path)
        try:
            from model import Kronos, KronosPredictor, KronosTokenizer
        except ImportError as exc:
            raise RuntimeError("Install the 'kronos' extra before using Kronos") from exc
        artifacts = resolve_kronos_artifacts(cfg)
        tokenizer = KronosTokenizer.from_pretrained(artifacts["tokenizer"]["snapshot_path"])
        model = Kronos.from_pretrained(artifacts["model"]["snapshot_path"])
        self.predictor = KronosPredictor(
            model, tokenizer, device=cfg["device"], max_context=cfg["max_context"]
        )
        self.model_key = model_key
        self.artifact_manifest = artifacts

    def forecast(self, ohlcv: pd.DataFrame, future_index: pd.DatetimeIndex) -> pd.DataFrame:
        x = ohlcv[["open", "high", "low", "close", "volume"]].copy()
        return self.predictor.predict(
            df=x,
            x_timestamp=pd.Series(x.index),
            y_timestamp=pd.Series(future_index),
            pred_len=len(future_index),
            T=float(self.inference["T"]),
            top_p=float(self.inference["top_p"]),
            sample_count=int(self.inference["sample_count"]),
            verbose=bool(self.inference["verbose"]),
        )
