from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def sha256_json_file(path: Path) -> str:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def locked_environment_mismatches(lock_path: Path) -> list[str]:
    from packaging.requirements import Requirement

    mismatches: list[str] = []
    for raw in Path(lock_path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        expected = next(
            (item.version for item in requirement.specifier if item.operator == "=="), None
        )
        if expected is None:
            continue
        try:
            actual = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            mismatches.append(f"{requirement.name}: missing (expected {expected})")
            continue
        if actual != expected:
            mismatches.append(f"{requirement.name}: {actual} != {expected}")
    return mismatches


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
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
