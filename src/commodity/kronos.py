from __future__ import annotations

import hashlib
import os
import sys
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
