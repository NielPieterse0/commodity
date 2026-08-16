from __future__ import annotations

import argparse
import hashlib
import json
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
    args = parser.parse_args()

    from huggingface_hub import snapshot_download

    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "config" / "models.json").read_text(encoding="utf-8"))
    cfg = config["models"]["kronos_mini"]
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, object] = {
        "schema_version": 1,
        "record": "kronos_checkpoint_preflight",
        "empirical_execution": False,
        "model_inference": False,
        "cache_semantics": "preflight_only; measured execution must use local_files_only",
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
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(args.output.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
