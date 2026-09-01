from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Populate and hash the exact pinned Kronos snapshots without inference."
    )
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--model-key",
        default="kronos_mini",
        help="Exact config.models key to preflight (default: kronos_mini).",
    )
    args = parser.parse_args()

    from huggingface_hub import snapshot_download

    root = Path(__file__).resolve().parents[1]
    source_root = str(root / "src")
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    from commodity.kronos_runtime import runtime_lock_authority

    runtime_lock = runtime_lock_authority(root)
    config = json.loads((root / "config" / "models.json").read_text(encoding="utf-8"))
    try:
        cfg = config["models"][args.model_key]
    except KeyError as exc:
        raise SystemExit(f"unknown model key: {args.model_key}") from exc
    if cfg.get("family") != "foundation_model":
        raise SystemExit(f"model key is not a foundation model: {args.model_key}")
    if not cfg.get("enabled", False) and not cfg.get("checkpoint_preflight_enabled", False):
        raise SystemExit(f"checkpoint preflight is not enabled for model key: {args.model_key}")
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, object] = {
        "schema_version": 1,
        "record": "kronos_checkpoint_preflight",
        "model_key": args.model_key,
        "empirical_execution": False,
        "model_inference": False,
        "cache_semantics": "preflight_only; measured execution must use local_files_only",
        "runtime_lock": {
            "path": runtime_lock["path"],
            "sha256": runtime_lock["sha256"],
            "python": runtime_lock["python"],
            "platform": runtime_lock["platform"],
            "torch": runtime_lock["torch"],
        },
        "artifacts": {},
    }
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, dict)

    for role, id_key, revision_key in (
        ("model", "model_id", "model_revision"),
        ("tokenizer", "tokenizer_id", "tokenizer_revision"),
    ):
        identity = cfg["checkpoint_artifacts"][role]
        filename = identity["filename"]
        snapshot = Path(
            snapshot_download(
                repo_id=cfg[id_key],
                revision=cfg[revision_key],
                cache_dir=str(args.cache_dir),
                allow_patterns=["config.json", filename],
            )
        ).resolve()
        artifact_path = snapshot / filename
        observed = sha256_file(artifact_path)
        expected = identity["sha256"]
        if observed != expected:
            raise SystemExit(
                f"{role} SHA-256 mismatch: expected {expected}, observed {observed}"
            )
        artifacts[role] = {
            "repo_id": cfg[id_key],
            "revision": cfg[revision_key],
            "filename": filename,
            "expected_sha256": expected,
            "observed_sha256": observed,
            "bytes": artifact_path.stat().st_size,
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(args.output.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
