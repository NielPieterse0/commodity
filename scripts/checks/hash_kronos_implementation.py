from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

CANDIDATE_ID = "kronos-runtime"
SOURCE_PATHS = (
    "config/models.json",
    "src/commodity/kronos.py",
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
    root = Path(__file__).resolve().parents[2]
    files = {relative: sha256_file(root / relative) for relative in SOURCE_PATHS}
    source = (root / "vendor" / "Kronos").resolve()
    top_level = Path(
        subprocess.run(
            ["git", "-C", str(source), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    ).resolve()
    if top_level != source:
        raise SystemExit("Kronos source checkout is not initialized as its own Git worktree")
    source_revision = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()
    expected_revision = json.loads(
        (root / "config" / "models.json").read_text(encoding="utf-8")
    )["models"]["kronos_mini"]["source_revision"].lower()
    if source_revision != expected_revision:
        raise SystemExit(
            f"Kronos source revision mismatch: expected {expected_revision}, observed {source_revision}"
        )
    status = subprocess.run(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise SystemExit("Kronos source checkout must be clean before implementation hashing")
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
