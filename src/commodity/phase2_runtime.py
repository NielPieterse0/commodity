from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from filelock import FileLock, Timeout


class Phase2RuntimeError(RuntimeError):
    """Raised when Phase-2 runtime safety or checkpoint integrity fails."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_sha256(payload: object) -> str:
    data = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class Phase2Telemetry:
    """Emit durable local progress events plus periodic liveness heartbeats."""

    def __init__(
        self,
        path: Path | None,
        *,
        heartbeat_seconds: float = 30.0,
        echo: bool = True,
    ) -> None:
        self.path = None if path is None else Path(path)
        self.heartbeat_seconds = max(float(heartbeat_seconds), 1.0)
        self.echo = bool(echo)
        self.started = time.monotonic()
        self._lock = threading.Lock()
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, event: str, **fields: object) -> None:
        record = {
            "timestamp_utc": _utc_now(),
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
            "event": str(event),
            **fields,
        }
        encoded = json.dumps(record, sort_keys=True, default=str, allow_nan=False)
        with self._lock:
            if self.path is not None:
                with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(encoded + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            if self.echo:
                stage = f" stage={fields['stage']}" if "stage" in fields else ""
                detail = f" detail={fields['detail']}" if "detail" in fields else ""
                print(
                    f"phase2 event={event}{stage}{detail} elapsed_s={record['elapsed_seconds']}",
                    file=sys.stderr,
                    flush=True,
                )

    @contextmanager
    def stage(self, stage: str, **fields: object) -> Iterator[None]:
        started = time.monotonic()
        stop = threading.Event()
        self.event("stage_started", stage=stage, **fields)

        def heartbeat() -> None:
            while not stop.wait(self.heartbeat_seconds):
                self.event(
                    "heartbeat",
                    stage=stage,
                    stage_elapsed_seconds=round(time.monotonic() - started, 3),
                )

        thread = threading.Thread(
            target=heartbeat,
            name=f"phase2-heartbeat-{stage}",
            daemon=True,
        )
        thread.start()
        try:
            yield
        except Exception as exc:
            self.event(
                "stage_failed",
                stage=stage,
                stage_elapsed_seconds=round(time.monotonic() - started, 3),
                error_type=type(exc).__name__,
                detail=str(exc),
            )
            raise
        else:
            self.event(
                "stage_completed",
                stage=stage,
                stage_elapsed_seconds=round(time.monotonic() - started, 3),
            )
        finally:
            stop.set()
            thread.join(timeout=min(self.heartbeat_seconds, 1.0))


class Phase2CheckpointView:
    """Apply a code-bound identity context to one reusable checkpoint stage."""

    def __init__(
        self,
        store: Phase2CheckpointStore,
        identity_context: dict[str, Any],
        *,
        allow_legacy_identity: bool = False,
    ) -> None:
        self.store = store
        self.telemetry = store.telemetry
        self.identity_context = dict(identity_context)
        self.allow_legacy_identity = bool(allow_legacy_identity)

    def _identity(self, identity: dict[str, Any]) -> dict[str, Any]:
        overlap = set(identity) & set(self.identity_context)
        if overlap:
            raise Phase2RuntimeError(
                f"checkpoint identity context collision: {sorted(overlap)}"
            )
        return {**identity, **self.identity_context}

    def load_json(self, name: str, identity: dict[str, Any]) -> dict[str, Any] | None:
        scoped = self._identity(identity)
        payload = self.store.load_json(name, scoped)
        if payload is not None or not self.allow_legacy_identity:
            return payload
        payload = self.store.load_json(name, identity)
        if payload is not None:
            self.store.save_json(name, payload, scoped)
            self.telemetry.event("checkpoint_identity_upgraded", checkpoint=name)
        return payload

    def save_json(self, name: str, payload: dict[str, Any], identity: dict[str, Any]) -> None:
        self.store.save_json(name, payload, self._identity(identity))

    def load_frame(self, name: str, identity: dict[str, Any]) -> pd.DataFrame | None:
        scoped = self._identity(identity)
        frame = self.store.load_frame(name, scoped)
        if frame is not None or not self.allow_legacy_identity:
            return frame
        frame = self.store.load_frame(name, identity)
        if frame is not None:
            self.store.save_frame(name, frame, scoped)
            self.telemetry.event("checkpoint_identity_upgraded", checkpoint=name)
        return frame

    def save_frame(self, name: str, frame: pd.DataFrame, identity: dict[str, Any]) -> None:
        self.store.save_frame(name, frame, self._identity(identity))


class Phase2CheckpointStore:
    """Integrity-check local disposable checkpoints without making them authority."""

    def __init__(self, root: Path, telemetry: Phase2Telemetry) -> None:
        self.root = Path(root)
        self.telemetry = telemetry
        self.root.mkdir(parents=True, exist_ok=True)

    def scoped_identity(
        self,
        identity_context: dict[str, Any],
        *,
        allow_legacy_identity: bool = False,
    ) -> Phase2CheckpointView:
        return Phase2CheckpointView(
            self,
            identity_context,
            allow_legacy_identity=allow_legacy_identity,
        )

    @contextmanager
    def run_lock(self) -> Iterator[None]:
        lock = FileLock(str(self.root / "run.lock"), timeout=0)
        try:
            lock.acquire()
        except Timeout as exc:
            raise Phase2RuntimeError(
                "another Phase-2 process already owns this checkpoint directory"
            ) from exc
        try:
            self.telemetry.event("run_lock_acquired", checkpoint_root=str(self.root))
            yield
        finally:
            lock.release()
            self.telemetry.event("run_lock_released", checkpoint_root=str(self.root))

    def _atomic_bytes(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            with temp.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink(missing_ok=True)

    def save_json(self, name: str, payload: dict[str, Any], identity: dict[str, Any]) -> None:
        content = {
            "schema_version": 1,
            "identity": identity,
            "payload": payload,
        }
        encoded = (
            json.dumps(content, indent=2, sort_keys=True, default=str, allow_nan=False) + "\n"
        ).encode("utf-8")
        self._atomic_bytes(self.root / f"{name}.json", encoded)
        self.telemetry.event("checkpoint_saved", checkpoint=name, kind="json")

    def load_json(self, name: str, identity: dict[str, Any]) -> dict[str, Any] | None:
        path = self.root / f"{name}.json"
        if not path.is_file():
            return None
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.telemetry.event("checkpoint_rejected", checkpoint=name, detail="invalid_json")
            return None
        if content.get("identity") != identity or not isinstance(content.get("payload"), dict):
            self.telemetry.event("checkpoint_rejected", checkpoint=name, detail="identity_mismatch")
            return None
        self.telemetry.event("checkpoint_reused", checkpoint=name, kind="json")
        return dict(content["payload"])

    def save_frame(self, name: str, frame: pd.DataFrame, identity: dict[str, Any]) -> None:
        data_path = self.root / f"{name}.parquet"
        data_path.parent.mkdir(parents=True, exist_ok=True)
        temp = data_path.with_name(f".{data_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            frame.to_parquet(temp, index=False)
            with temp.open("rb+") as handle:
                handle.flush()
                os.fsync(handle.fileno())
            data_sha256 = sha256_file(temp)
            os.replace(temp, data_path)
        finally:
            if temp.exists():
                temp.unlink(missing_ok=True)
        manifest = {
            "schema_version": 1,
            "identity": identity,
            "data_file": data_path.name,
            "data_sha256": data_sha256,
            "rows": len(frame),
            "columns": list(frame.columns),
        }
        encoded = (
            json.dumps(manifest, indent=2, sort_keys=True, default=str, allow_nan=False) + "\n"
        ).encode("utf-8")
        self._atomic_bytes(self.root / f"{name}.manifest.json", encoded)
        self.telemetry.event(
            "checkpoint_saved",
            checkpoint=name,
            kind="frame",
            rows=len(frame),
        )

    def load_frame(self, name: str, identity: dict[str, Any]) -> pd.DataFrame | None:
        manifest_path = self.root / f"{name}.manifest.json"
        data_path = self.root / f"{name}.parquet"
        if not manifest_path.is_file() or not data_path.is_file():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.telemetry.event("checkpoint_rejected", checkpoint=name, detail="invalid_manifest")
            return None
        if manifest.get("identity") != identity:
            self.telemetry.event("checkpoint_rejected", checkpoint=name, detail="identity_mismatch")
            return None
        observed_sha256 = sha256_file(data_path)
        if observed_sha256 != manifest.get("data_sha256"):
            self.telemetry.event("checkpoint_rejected", checkpoint=name, detail="data_hash_mismatch")
            return None
        try:
            frame = pd.read_parquet(data_path)
        except (OSError, TypeError, ValueError) as exc:
            self.telemetry.event(
                "checkpoint_rejected",
                checkpoint=name,
                detail=f"parquet_read_failed:{type(exc).__name__}",
            )
            return None
        if int(manifest.get("rows", -1)) != len(frame) or list(manifest.get("columns", [])) != list(frame.columns):
            self.telemetry.event("checkpoint_rejected", checkpoint=name, detail="shape_mismatch")
            return None
        self.telemetry.event(
            "checkpoint_reused",
            checkpoint=name,
            kind="frame",
            rows=len(frame),
        )
        return frame
