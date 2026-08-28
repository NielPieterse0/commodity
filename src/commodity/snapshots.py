from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SnapshotIntegrityError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_SECRET_VALUE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"^Bearer\s+\S{16,}$",
        r"^github_pat_[A-Za-z0-9_]{20,}$",
        r"^gh[pousr]_[A-Za-z0-9_]{20,}$",
        r"^sk-[A-Za-z0-9_-]{20,}$",
        r"^AKIA[A-Z0-9]{16}$",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    )
)


def _assert_secret_free(value: Any, path: str = "metadata") -> None:
    forbidden = ("api_key", "apikey", "authorization", "access_token", "secret", "password")
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(term in normalized for term in forbidden):
                raise SnapshotIntegrityError(f"Secret-bearing snapshot metadata key rejected: {path}.{key}")
            _assert_secret_free(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_secret_free(child, f"{path}[{index}]")
    elif isinstance(value, str) and any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS):
        raise SnapshotIntegrityError(f"Secret-like snapshot metadata value rejected: {path}")


@dataclass
class SnapshotWriter:
    root: Path
    provider: str
    snapshot_id: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def snapshot_dir(self) -> Path:
        return self.root / self.provider / self.snapshot_id

    def write_bytes(self, relative_path: str, content: bytes) -> Path:
        target = self.snapshot_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            expected = hashlib.sha256(content).hexdigest()
            if _sha256(target) != expected:
                raise SnapshotIntegrityError(f"Immutable snapshot artifact differs: {target}")
            self._record(target, relative_path)
            return target
        fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        self._record(target, relative_path)
        return target

    def _record(self, path: Path, relative_path: str) -> None:
        item = {
            "path": relative_path.replace("\\", "/"),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        self.artifacts = [x for x in self.artifacts if x["path"] != item["path"]]
        self.artifacts.append(item)

    def finalize(self, metadata: dict[str, Any]) -> Path:
        manifest = self.snapshot_dir / "manifest.json"
        if manifest.exists():
            raise FileExistsError(f"Immutable snapshot already finalized: {manifest}")
        _assert_secret_free(metadata)
        payload = {
            "schema_version": 1,
            "provider": self.provider,
            "snapshot_id": self.snapshot_id,
            **metadata,
            "artifacts": sorted(self.artifacts, key=lambda item: item["path"]),
        }
        content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        return self.write_bytes("manifest.json", content)


def verify_snapshot(manifest_path: Path) -> dict[str, Any]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    for artifact in payload.get("artifacts", []):
        path = root / artifact["path"]
        if not path.is_file():
            raise SnapshotIntegrityError(f"Snapshot artifact missing: {path}")
        if path.stat().st_size != artifact["bytes"] or _sha256(path) != artifact["sha256"]:
            raise SnapshotIntegrityError(f"Snapshot artifact failed integrity check: {path}")
    return {
        "provider": payload["provider"],
        "snapshot_id": payload["snapshot_id"],
        "artifact_count": len(payload.get("artifacts", [])),
    }
