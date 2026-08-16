from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

CANDIDATE_ID = "v2-82-kronos-only"
SOURCE_PATHS = (
    "config/models.json",
    "src/commodity/kronos.py",
    "src/commodity/v2_kronos.py",
)


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    files = {relative: sha256_file(root / relative) for relative in SOURCE_PATHS}
    source_revision = subprocess.run(
        ["git", "-C", str(root / "vendor" / "Kronos"), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()
    manifest: dict[str, object] = {
        "schema_version": 1,
        "candidate_id": CANDIDATE_ID,
        "files": files,
        "kronos_source_revision": source_revision,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
