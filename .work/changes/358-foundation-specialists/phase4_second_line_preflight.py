from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS_PATH = REPO_ROOT / "config" / "models.json"
SECOND_LINE_KEYS = ("chronos_2", "kronos_small", "moirai_2_small")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_path(cache: Path, repo_id: str, revision: str, filename: str) -> Path:
    slug = "models--" + repo_id.replace("/", "--")
    return cache / slug / "snapshots" / revision / filename


def _artifact_checks(cfg: dict[str, Any], cache: Path | None) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    identities = [("model", cfg["model_id"], cfg["model_revision"])]
    if "tokenizer" in cfg.get("checkpoint_artifacts", {}):
        identities.append(("tokenizer", cfg["tokenizer_id"], cfg["tokenizer_revision"]))
    for kind, repo_id, revision in identities:
        artifact_cfg = cfg["checkpoint_artifacts"][kind]
        path = None if cache is None else _snapshot_path(
            cache, repo_id, revision, artifact_cfg["filename"]
        )
        present = path is not None and path.is_file()
        observed = _sha256(path) if present else None
        checks.append(
            {
                "kind": kind,
                "repo_id": repo_id,
                "revision": revision,
                "filename": artifact_cfg["filename"],
                "expected_sha256": artifact_cfg["sha256"],
                "path": None if path is None else str(path),
                "present": present,
                "observed_sha256": observed,
                "hash_match": observed == artifact_cfg["sha256"],
            }
        )
    return checks


def _model_status(model_key: str, cfg: dict[str, Any], cache_override: Path | None) -> dict[str, Any]:
    cache_env = cfg["checkpoint_cache_env"]
    cache_value = str(cache_override) if cache_override is not None else os.environ.get(cache_env)
    cache = None if not cache_value else Path(cache_value)
    runtime_module = cfg.get("runtime_module")
    runtime_source = cfg.get("runtime_source")
    source_present = bool(runtime_source and (REPO_ROOT / runtime_source).is_dir())
    runtime_present = source_present or bool(
        runtime_module and importlib.util.find_spec(runtime_module) is not None
    )
    artifacts = _artifact_checks(cfg, cache)
    artifact_ready = bool(artifacts) and all(item["present"] and item["hash_match"] for item in artifacts)
    promotion_eligibility = (
        "research_only_noncommercial_not_deployable"
        if cfg.get("research_only")
        else "deployment_candidate_or_capacity_control"
    )
    return {
        "model_key": model_key,
        "model_id": cfg["model_id"],
        "model_revision": cfg["model_revision"],
        "source_revision": cfg.get("source_revision"),
        "source_release": cfg.get("source_release"),
        "license_status": cfg.get("license_status"),
        "pretraining_exposure": cfg.get("pretraining_exposure"),
        "promotion_eligibility": promotion_eligibility,
        "cache_env": cache_env,
        "cache_bound": cache is not None,
        "cache_path": None if cache is None else str(cache),
        "runtime_module": runtime_module,
        "runtime_package": cfg.get("runtime_package"),
        "runtime_source": cfg.get("runtime_source"),
        "runtime_present": runtime_present,
        "artifacts": artifacts,
        "artifact_ready": artifact_ready,
        "ready": artifact_ready and runtime_present,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-4 second-line model readiness preflight")
    parser.add_argument("--model-key", action="append", choices=SECOND_LINE_KEYS)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    registry = json.loads(MODELS_PATH.read_text(encoding="utf-8"))["models"]
    keys = tuple(args.model_key or SECOND_LINE_KEYS)
    statuses = [_model_status(key, registry[key], args.cache_dir) for key in keys]
    payload = {
        "schema_version": 1,
        "authority": "github-issue-358-comment-5634786235",
        "protected_confirmation_accessed": False,
        "models": statuses,
        "all_ready": all(item["ready"] for item in statuses),
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    print(text, end="")
    return 0 if payload["all_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
