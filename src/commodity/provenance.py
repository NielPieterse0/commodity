from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        check=False,
    )


def git_code_state(repo_root: Path) -> dict[str, Any]:
    head = _git(repo_root, "rev-parse", "HEAD")
    raw_head = head.stdout.decode("utf-8", errors="replace").strip()
    is_sha = len(raw_head) in {40, 64} and all(
        char in "0123456789abcdefABCDEF" for char in raw_head
    )
    commit_sha = raw_head if head.returncode == 0 and is_sha else None
    status = _git(repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    status_bytes = status.stdout if status.returncode == 0 else b""
    dirty = bool(status_bytes)
    if not dirty:
        return {
            "commit_sha": commit_sha,
            "working_tree_dirty": False,
            "working_tree_diff_sha256": None,
        }

    digest = hashlib.sha256()
    for args in (("diff", "--binary"), ("diff", "--binary", "--cached")):
        result = _git(repo_root, *args)
        if result.returncode == 0:
            digest.update(result.stdout)
    digest.update(status_bytes)

    entries = status_bytes.decode("utf-8", errors="replace").split("\0")
    for entry in sorted(item for item in entries if item.startswith("?? ")):
        relative = entry[3:]
        path = repo_root / relative
        if path.is_file():
            digest.update(relative.replace("\\", "/").encode("utf-8"))
            digest.update(bytes.fromhex(sha256_file(path)))

    return {
        "commit_sha": commit_sha,
        "working_tree_dirty": True,
        "working_tree_diff_sha256": digest.hexdigest(),
    }


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
