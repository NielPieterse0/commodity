from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from filelock import FileLock, Timeout


class V2ParallelError(RuntimeError):
    """Raised when parallel optimization integrity would be compromised."""


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _payload_hash(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(Path(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_namespace_change(*paths: Path) -> None:
    parents = {Path(path).parent for path in paths}
    for parent in sorted(parents, key=str):
        _fsync_directory(parent)


def _windows_move_file(source: Path, destination: Path, *, replace_existing: bool) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    move_file = kernel32.MoveFileExW
    move_file.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    move_file.restype = ctypes.c_int
    flags = 0x00000008 | (0x00000001 if replace_existing else 0)
    if move_file(str(source), str(destination), flags):
        return
    error = ctypes.get_last_error()
    if not replace_existing and error in {80, 183}:
        raise FileExistsError(error, f"destination already exists: {destination}", str(destination))
    raise OSError(error, f"failed durable move {source} -> {destination}")


def _durable_replace(source: Path, destination: Path) -> None:
    source = Path(source)
    destination = Path(destination)
    if os.name == "nt":
        _windows_move_file(source, destination, replace_existing=True)
        return
    os.replace(source, destination)
    _fsync_namespace_change(source, destination)


def _durable_move_exclusive(source: Path, destination: Path) -> None:
    source = Path(source)
    destination = Path(destination)
    if os.name == "nt":
        _windows_move_file(source, destination, replace_existing=False)
        return
    os.link(source, destination)
    _fsync_namespace_change(destination)
    os.unlink(source)
    _fsync_namespace_change(source)


def _durable_unlink(path: Path) -> None:
    path = Path(path)
    if os.name != "nt":
        path.unlink()
        _fsync_namespace_change(path)
        return
    tombstone = path.with_name(f".{path.name}.deleted.{uuid.uuid4().hex}")
    _windows_move_file(path, tombstone, replace_existing=False)
    try:
        tombstone.unlink()
    except OSError:
        pass


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _durable_replace(Path(tmp_name), path)
    finally:
        if os.path.exists(tmp_name):
            _durable_unlink(Path(tmp_name))


def _read_json_object(path: Path, *, label: str) -> dict[str, object]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise V2ParallelError(f"{label} is unreadable or malformed: {path}") from exc
    if not isinstance(payload, dict):
        raise V2ParallelError(f"{label} must contain a JSON object: {path}")
    return payload


def _publish_exclusive_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.publish.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _durable_move_exclusive(Path(tmp_name), path)
    finally:
        if os.path.exists(tmp_name):
            _durable_unlink(Path(tmp_name))


def _publish_exclusive_json(path: Path, payload: Mapping[str, object]) -> None:
    _publish_exclusive_text(path, _canonical_json(dict(payload)) + "\n")


@dataclass(frozen=True)
class OptimizationIdentity:
    programme_issue: int
    issue: int
    evidence_class: str
    code_id: str
    dataset_id: str
    search_plan_id: str

    def as_dict(self) -> dict[str, object]:
        return {
            "programme_issue": self.programme_issue,
            "issue": self.issue,
            "evidence_class": self.evidence_class,
            "code_id": self.code_id,
            "dataset_id": self.dataset_id,
            "search_plan_id": self.search_plan_id,
        }

    @property
    def fingerprint(self) -> str:
        return _payload_hash(self.as_dict())


@dataclass(frozen=True)
class ShardSpec:
    shard_id: str
    ordinal: int
    item_ids: tuple[str, ...]
    identity_fingerprint: str


_SHARD_ID_RE = re.compile(r"^shard-[0-9a-f]{12}-[0-9]{3}-[0-9a-f]{12}$")
_LEASE_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def _expected_shard_id(
    *, ordinal: int, item_ids: Sequence[str], identity_fingerprint: str
) -> str:
    return (
        f"shard-{identity_fingerprint[:12]}-{ordinal:03d}-"
        f"{_payload_hash(list(item_ids))[:12]}"
    )


def deterministic_shards(
    item_ids: Sequence[str], *, shard_count: int, identity: OptimizationIdentity
) -> list[ShardSpec]:
    if shard_count < 1:
        raise V2ParallelError("shard_count must be positive")
    unique = sorted({str(item) for item in item_ids})
    if len(unique) != len(item_ids):
        raise V2ParallelError("parallel search item IDs must be unique")
    buckets: list[list[str]] = [[] for _ in range(min(shard_count, max(1, len(unique))))]
    ordered = sorted(unique, key=lambda item: (hashlib.sha256(item.encode("utf-8")).hexdigest(), item))
    for index, item_id in enumerate(ordered):
        buckets[index % len(buckets)].append(item_id)
    specs: list[ShardSpec] = []
    for ordinal, bucket in enumerate(buckets):
        if not bucket:
            continue
        shard_id = _expected_shard_id(
            ordinal=ordinal,
            item_ids=bucket,
            identity_fingerprint=identity.fingerprint,
        )
        specs.append(
            ShardSpec(
                shard_id=shard_id,
                ordinal=ordinal,
                item_ids=tuple(bucket),
                identity_fingerprint=identity.fingerprint,
            )
        )
    return specs


def shard_manifest(identity: OptimizationIdentity, shards: Sequence[ShardSpec]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "identity": identity.as_dict(),
        "identity_fingerprint": identity.fingerprint,
        "shards": [
            {
                "shard_id": shard.shard_id,
                "ordinal": shard.ordinal,
                "item_ids": list(shard.item_ids),
                "identity_fingerprint": shard.identity_fingerprint,
            }
            for shard in sorted(shards, key=lambda item: item.ordinal)
        ],
    }


def write_manifest(path: Path, identity: OptimizationIdentity, shards: Sequence[ShardSpec]) -> None:
    payload = shard_manifest(identity, shards)
    if path.exists():
        current = _read_json_object(path, label="shard manifest")
        if current != payload:
            raise V2ParallelError("existing shard manifest conflicts with frozen optimization identity")
        return
    try:
        _publish_exclusive_json(path, payload)
    except FileExistsError:
        current = _read_json_object(path, label="shard manifest")
        if current != payload:
            raise V2ParallelError("existing shard manifest conflicts with frozen optimization identity")


def load_manifest(path: Path) -> tuple[OptimizationIdentity, list[ShardSpec]]:
    payload = _read_json_object(path, label="shard manifest")
    if payload.get("schema_version") != 1:
        raise V2ParallelError("unsupported shard manifest schema")
    raw_identity = payload.get("identity")
    raw_shards = payload.get("shards")
    if not isinstance(raw_identity, Mapping) or not isinstance(raw_shards, list):
        raise V2ParallelError("shard manifest is incomplete")
    try:
        identity = OptimizationIdentity(
            programme_issue=int(raw_identity["programme_issue"]),
            issue=int(raw_identity["issue"]),
            evidence_class=str(raw_identity["evidence_class"]),
            code_id=str(raw_identity["code_id"]),
            dataset_id=str(raw_identity["dataset_id"]),
            search_plan_id=str(raw_identity["search_plan_id"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V2ParallelError("shard manifest identity is invalid") from exc
    if payload.get("identity_fingerprint") != identity.fingerprint:
        raise V2ParallelError("shard manifest identity fingerprint is invalid")
    shards: list[ShardSpec] = []
    seen_shards: set[str] = set()
    seen_ordinals: set[int] = set()
    seen_items: set[str] = set()
    for raw in raw_shards:
        if not isinstance(raw, Mapping):
            raise V2ParallelError("shard manifest entry is invalid")
        raw_item_ids = raw.get("item_ids")
        if not isinstance(raw_item_ids, list) or not raw_item_ids:
            raise V2ParallelError("shard manifest entry item_ids must be a non-empty array")
        try:
            ordinal = int(raw.get("ordinal", -1))
        except (TypeError, ValueError) as exc:
            raise V2ParallelError("shard manifest entry ordinal is invalid") from exc
        shard = ShardSpec(
            shard_id=str(raw.get("shard_id", "")),
            ordinal=ordinal,
            item_ids=tuple(str(item) for item in raw_item_ids),
            identity_fingerprint=str(raw.get("identity_fingerprint", "")),
        )
        if not shard.shard_id or shard.ordinal < 0 or not shard.item_ids:
            raise V2ParallelError("shard manifest entry is incomplete")
        if any(not item_id for item_id in shard.item_ids):
            raise V2ParallelError("shard manifest entry contains an empty item ID")
        if shard.identity_fingerprint != identity.fingerprint:
            raise V2ParallelError(f"shard {shard.shard_id} has stale identity")
        if not _SHARD_ID_RE.fullmatch(shard.shard_id):
            raise V2ParallelError("shard manifest entry has an invalid shard ID")
        expected_shard_id = _expected_shard_id(
            ordinal=shard.ordinal,
            item_ids=shard.item_ids,
            identity_fingerprint=identity.fingerprint,
        )
        if shard.shard_id != expected_shard_id:
            raise V2ParallelError("shard manifest entry shard ID does not match its identity/membership")
        if (
            shard.shard_id in seen_shards
            or shard.ordinal in seen_ordinals
            or seen_items.intersection(shard.item_ids)
        ):
            raise V2ParallelError("shard manifest has duplicate shard, ordinal, or item membership")
        seen_shards.add(shard.shard_id)
        seen_ordinals.add(shard.ordinal)
        seen_items.update(shard.item_ids)
        shards.append(shard)
    if not shards:
        raise V2ParallelError("shard manifest has no shards")
    return identity, sorted(shards, key=lambda item: item.ordinal)


def _shard_lock_path(root: Path, shard: ShardSpec) -> Path:
    return Path(root) / "locks" / f"{shard.shard_id}.lock"


def _validate_shard_state_identity(
    payload: Mapping[str, object], shard: ShardSpec, *, label: str
) -> None:
    if payload.get("shard_id") != shard.shard_id:
        raise V2ParallelError(f"{label} identity mismatch for {shard.shard_id}")
    if payload.get("identity_fingerprint") != shard.identity_fingerprint:
        raise V2ParallelError(f"stale {label} fingerprint for {shard.shard_id}")


def _recovery_transaction_path(root: Path, shard: ShardSpec) -> Path:
    return Path(root) / "recovery-transactions" / f"{shard.shard_id}.json"


def _is_sha256_hex(value: object) -> bool:
    text = str(value)
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _validated_recovery_transaction(path: Path, shard: ShardSpec) -> dict[str, object]:
    transaction = _read_json_object(path, label="stale recovery transaction")
    if transaction.get("schema_version") != 1:
        raise V2ParallelError(f"unsupported stale recovery transaction for {shard.shard_id}")
    if transaction.get("shard_id") != shard.shard_id:
        raise V2ParallelError(f"stale recovery transaction shard mismatch for {shard.shard_id}")
    if transaction.get("identity_fingerprint") != shard.identity_fingerprint:
        raise V2ParallelError(f"stale recovery transaction fingerprint for {shard.shard_id}")
    token = str(transaction.get("recovered_lease_token", ""))
    if not _LEASE_TOKEN_RE.fullmatch(token):
        raise V2ParallelError(f"invalid stale recovery token for {shard.shard_id}")
    try:
        stamp = int(transaction["archive_stamp_ns"])
    except (KeyError, TypeError, ValueError) as exc:
        raise V2ParallelError(f"invalid stale recovery archive stamp for {shard.shard_id}") from exc
    if stamp < 1:
        raise V2ParallelError(f"invalid stale recovery archive stamp for {shard.shard_id}")
    if not _is_sha256_hex(transaction.get("claim_payload_hash")):
        raise V2ParallelError(f"invalid claim_payload_hash for {shard.shard_id}")
    heartbeat_present = transaction.get("heartbeat_present")
    if not isinstance(heartbeat_present, bool):
        raise V2ParallelError(f"invalid heartbeat_present for {shard.shard_id}")
    heartbeat_matches_claim = transaction.get("heartbeat_matches_claim")
    if not isinstance(heartbeat_matches_claim, bool):
        raise V2ParallelError(f"invalid heartbeat_matches_claim for {shard.shard_id}")
    heartbeat_hash = transaction.get("heartbeat_payload_hash")
    if heartbeat_present and not _is_sha256_hex(heartbeat_hash):
        raise V2ParallelError(f"invalid heartbeat_payload_hash for {shard.shard_id}")
    if not heartbeat_present and heartbeat_hash is not None:
        raise V2ParallelError(f"unexpected heartbeat_payload_hash for {shard.shard_id}")
    return transaction


def _validate_archived_recovery_component(
    archive: Path, *, expected_hash: str, label: str
) -> None:
    if not archive.exists():
        raise V2ParallelError(f"missing archived {label} during stale recovery")
    archived = _read_json_object(archive, label=f"archived {label}")
    if _payload_hash(archived) != expected_hash:
        raise V2ParallelError(f"archived {label} conflicts with stale recovery transaction")


def _archive_recovery_component(
    source: Path,
    archive: Path,
    *,
    expected_hash: str,
    label: str,
) -> None:
    if source.exists():
        payload = _read_json_object(source, label=label)
        if _payload_hash(payload) != expected_hash:
            raise V2ParallelError(f"{label} changed after stale recovery was prepared")
        if archive.exists():
            archived = _read_json_object(archive, label=f"archived {label}")
            if _payload_hash(archived) != expected_hash:
                raise V2ParallelError(f"archived {label} conflicts with stale recovery transaction")
            raise V2ParallelError(f"both live and archived {label} exist during stale recovery")
        _durable_move_exclusive(source, archive)
        return
    _validate_archived_recovery_component(
        archive, expected_hash=expected_hash, label=label
    )


def _recovery_artifact_paths(
    root: Path, shard: ShardSpec, transaction: Mapping[str, object]
) -> tuple[Path, Path | None, Path, Path]:
    token = str(transaction["recovered_lease_token"])
    stamp = int(transaction["archive_stamp_ns"])
    prefix = f"{shard.shard_id}.{token[:16]}.{stamp}"
    reclaimed = Path(root) / "reclaimed"
    claim_archive = reclaimed / f"{prefix}.claim.json"
    heartbeat_archive = (
        reclaimed / f"{prefix}.heartbeat.json"
        if bool(transaction["heartbeat_present"])
        else None
    )
    receipt = reclaimed / f"{prefix}.recovery.json"
    transaction_archive = reclaimed / f"{prefix}.transaction.json"
    return claim_archive, heartbeat_archive, receipt, transaction_archive


def _recovery_receipt_payload(
    shard: ShardSpec, transaction: Mapping[str, object]
) -> dict[str, object]:
    claim_archive, heartbeat_archive, _, transaction_archive = _recovery_artifact_paths(
        Path("."), shard, transaction
    )
    return {
        "schema_version": 1,
        "shard_id": shard.shard_id,
        "identity_fingerprint": shard.identity_fingerprint,
        "recovered_lease_token": transaction.get("recovered_lease_token"),
        "previous_owner_id": transaction.get("previous_owner_id"),
        "recovery_owner_id": transaction.get("recovery_owner_id"),
        "stale_age_seconds": transaction.get("stale_age_seconds"),
        "recovered_unix": transaction.get("recovered_unix"),
        "archive_stamp_ns": transaction.get("archive_stamp_ns"),
        "claim_archive": claim_archive.name,
        "claim_payload_hash": transaction.get("claim_payload_hash"),
        "heartbeat_present": transaction.get("heartbeat_present"),
        "heartbeat_matches_claim": transaction.get("heartbeat_matches_claim"),
        "heartbeat_archive": None if heartbeat_archive is None else heartbeat_archive.name,
        "heartbeat_payload_hash": transaction.get("heartbeat_payload_hash"),
        "transaction_archive": transaction_archive.name,
    }


def _validate_completed_recovery(
    root: Path, shard: ShardSpec, transaction_archive: Path
) -> Path:
    transaction = _validated_recovery_transaction(transaction_archive, shard)
    claim_archive, heartbeat_archive, receipt, expected_transaction_archive = _recovery_artifact_paths(
        root, shard, transaction
    )
    if transaction_archive != expected_transaction_archive:
        raise V2ParallelError(f"stale recovery transaction archive name mismatch for {shard.shard_id}")
    _validate_archived_recovery_component(
        claim_archive,
        expected_hash=str(transaction["claim_payload_hash"]),
        label="shard claim",
    )
    heartbeat_present = bool(transaction["heartbeat_present"])
    if heartbeat_present:
        if heartbeat_archive is None:
            raise V2ParallelError(f"missing heartbeat archive path for {shard.shard_id}")
        _validate_archived_recovery_component(
            heartbeat_archive,
            expected_hash=str(transaction["heartbeat_payload_hash"]),
            label="shard heartbeat",
        )
    elif heartbeat_archive is not None:
        raise V2ParallelError(f"unexpected heartbeat archive path for {shard.shard_id}")
    expected_receipt = _recovery_receipt_payload(shard, transaction)
    if _read_json_object(receipt, label="stale recovery receipt") != expected_receipt:
        raise V2ParallelError(f"stale recovery receipt conflicts for {shard.shard_id}")
    return receipt


def _unique_completed_recovery_receipt(root: Path, shard: ShardSpec) -> Path | None:
    reclaimed = Path(root) / "reclaimed"
    if not reclaimed.exists():
        return None
    receipts = [
        _validate_completed_recovery(root, shard, transaction_archive)
        for transaction_archive in sorted(
            reclaimed.glob(f"{shard.shard_id}.*.transaction.json")
        )
    ]
    if len(receipts) > 1:
        raise V2ParallelError(
            f"shard {shard.shard_id} has ambiguous completed stale recoveries"
        )
    return receipts[0] if receipts else None


def _validate_completed_recoveries(root: Path, shard: ShardSpec) -> None:
    reclaimed = Path(root) / "reclaimed"
    if not reclaimed.exists():
        return
    for transaction_archive in sorted(
        reclaimed.glob(f"{shard.shard_id}.*.transaction.json")
    ):
        _validate_completed_recovery(root, shard, transaction_archive)


def recover_stale_claim(
    root: Path,
    shard: ShardSpec,
    *,
    stale_after_seconds: float,
    recovery_owner_id: str,
    now: float | None = None,
) -> Path:
    """Fence one stale orphaned claim with a crash-resumable recovery transaction."""
    if stale_after_seconds <= 0:
        raise V2ParallelError("stale_after_seconds must be positive")
    root = Path(root)
    claim_path = root / "claims" / f"{shard.shard_id}.json"
    heartbeat_path = root / "heartbeats" / f"{shard.shard_id}.json"
    transaction_path = _recovery_transaction_path(root, shard)
    lock = FileLock(str(_shard_lock_path(root, shard)))
    try:
        lock.acquire(timeout=0)
    except Timeout as exc:
        raise V2ParallelError(f"shard {shard.shard_id} still has an active OS lock") from exc
    try:
        if transaction_path.exists():
            transaction = _validated_recovery_transaction(transaction_path, shard)
        else:
            if not claim_path.exists():
                completed_receipt = _unique_completed_recovery_receipt(root, shard)
                if completed_receipt is not None:
                    return completed_receipt
                raise V2ParallelError(f"shard {shard.shard_id} has no orphaned claim to recover")
            claim = _read_json_object(claim_path, label="shard claim")
            _validate_shard_state_identity(claim, shard, label="shard claim")
            token = str(claim.get("lease_token", ""))
            if not _LEASE_TOKEN_RE.fullmatch(token):
                raise V2ParallelError(f"invalid lease token for {shard.shard_id}")
            try:
                claim_acquired_unix = float(claim["acquired_unix"])
            except (KeyError, TypeError, ValueError) as exc:
                raise V2ParallelError(f"invalid claim timestamp for {shard.shard_id}") from exc

            heartbeat = None
            heartbeat_present = heartbeat_path.exists()
            heartbeat_matches_claim = False
            freshness_unix = claim_acquired_unix
            if heartbeat_present:
                heartbeat = _read_json_object(heartbeat_path, label="shard heartbeat")
                _validate_shard_state_identity(heartbeat, shard, label="shard heartbeat")
                heartbeat_matches_claim = (
                    heartbeat.get("lease_token") == token
                    and heartbeat.get("owner_id") == claim.get("owner_id")
                )
                if heartbeat_matches_claim:
                    try:
                        freshness_unix = float(heartbeat["updated_unix"])
                    except (KeyError, TypeError, ValueError) as exc:
                        raise V2ParallelError(
                            f"invalid heartbeat timestamp for {shard.shard_id}"
                        ) from exc

            current = time.time() if now is None else float(now)
            age = max(0.0, current - freshness_unix)
            if age <= stale_after_seconds:
                raise V2ParallelError(f"shard {shard.shard_id} orphaned claim is not stale")

            transaction_path.parent.mkdir(parents=True, exist_ok=True)
            stamp = int(time.time_ns())
            transaction = {
                "schema_version": 1,
                "shard_id": shard.shard_id,
                "identity_fingerprint": shard.identity_fingerprint,
                "recovered_lease_token": token,
                "previous_owner_id": claim.get("owner_id"),
                "recovery_owner_id": str(recovery_owner_id),
                "stale_age_seconds": age,
                "recovered_unix": current,
                "archive_stamp_ns": stamp,
                "claim_payload_hash": _payload_hash(claim),
                "heartbeat_present": heartbeat_present,
                "heartbeat_matches_claim": heartbeat_matches_claim,
                "heartbeat_payload_hash": None if heartbeat is None else _payload_hash(heartbeat),
            }
            try:
                _publish_exclusive_json(transaction_path, transaction)
            except FileExistsError:
                transaction = _validated_recovery_transaction(transaction_path, shard)

        transaction = _validated_recovery_transaction(transaction_path, shard)
        reclaimed = root / "reclaimed"
        reclaimed.mkdir(parents=True, exist_ok=True)
        claim_archive, heartbeat_archive, receipt, transaction_archive = _recovery_artifact_paths(
            root, shard, transaction
        )
        _archive_recovery_component(
            claim_path,
            claim_archive,
            expected_hash=str(transaction["claim_payload_hash"]),
            label="shard claim",
        )
        if bool(transaction["heartbeat_present"]):
            if heartbeat_archive is None:
                raise V2ParallelError(f"missing heartbeat archive path for {shard.shard_id}")
            _archive_recovery_component(
                heartbeat_path,
                heartbeat_archive,
                expected_hash=str(transaction["heartbeat_payload_hash"]),
                label="shard heartbeat",
            )
        elif heartbeat_path.exists():
            raise V2ParallelError(
                f"unexpected heartbeat appeared during stale recovery for {shard.shard_id}"
            )

        receipt_payload = _recovery_receipt_payload(shard, transaction)
        try:
            _publish_exclusive_json(receipt, receipt_payload)
        except FileExistsError:
            if _read_json_object(receipt, label="stale recovery receipt") != receipt_payload:
                raise V2ParallelError(f"stale recovery receipt conflicts for {shard.shard_id}")

        if transaction_archive.exists():
            if _read_json_object(
                transaction_archive, label="completed stale recovery transaction"
            ) != transaction:
                raise V2ParallelError(
                    f"completed stale recovery transaction conflicts for {shard.shard_id}"
                )
            _durable_unlink(transaction_path)
        else:
            _durable_move_exclusive(transaction_path, transaction_archive)
        _validate_completed_recovery(root, shard, transaction_archive)
        return receipt
    finally:
        lock.release()


class ShardLease:
    def __init__(self, root: Path, shard: ShardSpec, *, owner_id: str) -> None:
        self.root = Path(root)
        self.shard = shard
        self.owner_id = str(owner_id)
        self.token = uuid.uuid4().hex
        self.claim_path = self.root / "claims" / f"{shard.shard_id}.json"
        self.heartbeat_path = self.root / "heartbeats" / f"{shard.shard_id}.json"
        self.lock_path = _shard_lock_path(self.root, shard)
        self._lock = FileLock(str(self.lock_path))
        self._acquired = False

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._lock.acquire(timeout=0)
        except Timeout as exc:
            owner = "unknown"
            if self.claim_path.exists():
                owner = str(_read_json_object(self.claim_path, label="shard claim").get("owner_id", "unknown"))
            raise V2ParallelError(
                f"shard {self.shard.shard_id} already claimed by {owner}"
            ) from exc
        self._acquired = True
        try:
            recovery_transaction = _recovery_transaction_path(self.root, self.shard)
            if recovery_transaction.exists():
                _validated_recovery_transaction(recovery_transaction, self.shard)
                raise V2ParallelError(
                    f"shard {self.shard.shard_id} has an incomplete stale recovery transaction"
                )
            _validate_completed_recoveries(self.root, self.shard)
            if self.claim_path.exists():
                existing = _read_json_object(self.claim_path, label="shard claim")
                _validate_shard_state_identity(existing, self.shard, label="shard claim")
                owner = str(existing.get("owner_id", "unknown"))
                raise V2ParallelError(
                    f"shard {self.shard.shard_id} has an orphaned claim from {owner}; explicit stale recovery required"
                )
            payload = {
                "shard_id": self.shard.shard_id,
                "owner_id": self.owner_id,
                "lease_token": self.token,
                "pid": os.getpid(),
                "identity_fingerprint": self.shard.identity_fingerprint,
                "acquired_unix": time.time(),
            }
            atomic_write_text(self.claim_path, _canonical_json(payload) + "\n")
            self.heartbeat(status="running")
        except Exception:
            self._lock.release()
            self._acquired = False
            raise

    def assert_current(self) -> None:
        if not self._acquired or not self._lock.is_locked:
            raise V2ParallelError(f"shard {self.shard.shard_id} lease is not held")
        current = _read_json_object(self.claim_path, label="shard claim")
        _validate_shard_state_identity(current, self.shard, label="shard claim")
        if current.get("lease_token") != self.token or current.get("owner_id") != self.owner_id:
            raise V2ParallelError(f"shard {self.shard.shard_id} lease token is no longer current")

    def heartbeat(self, *, status: str = "running", completed_items: int = 0) -> None:
        self.assert_current()
        payload = {
            "shard_id": self.shard.shard_id,
            "owner_id": self.owner_id,
            "lease_token": self.token,
            "identity_fingerprint": self.shard.identity_fingerprint,
            "status": status,
            "completed_items": int(completed_items),
            "updated_unix": time.time(),
        }
        atomic_write_text(self.heartbeat_path, _canonical_json(payload) + "\n")

    def release(self, *, status: str = "complete", completed_items: int = 0) -> None:
        if not self._acquired:
            return
        try:
            self.heartbeat(status=status, completed_items=completed_items)
            self.assert_current()
            _durable_unlink(self.claim_path)
        finally:
            self._lock.release()
            self._acquired = False


def shard_result_path(root: Path, shard: ShardSpec) -> Path:
    return Path(root) / "results" / f"{shard.shard_id}.json"


def write_shard_result(
    root: Path,
    shard: ShardSpec,
    *,
    lease: ShardLease,
    records: Sequence[Mapping[str, object]],
) -> Path:
    lease.assert_current()
    if lease.shard != shard:
        raise V2ParallelError("shard result lease does not match shard")
    seen_trials: dict[str, dict[str, object]] = {}
    seen_items: dict[str, dict[str, object]] = {}
    for raw in records:
        record = dict(raw)
        trial_id = str(record.get("trial_id", ""))
        item_id = str(record.get("item_id", ""))
        if not trial_id or not item_id:
            raise V2ParallelError("shard result record requires trial_id and item_id")
        if item_id not in shard.item_ids:
            raise V2ParallelError(f"foreign item {item_id} in {shard.shard_id}")
        if item_id in seen_items:
            raise V2ParallelError(f"duplicate item result {item_id} in {shard.shard_id}")
        if trial_id in seen_trials and seen_trials[trial_id] != record:
            raise V2ParallelError(f"conflicting duplicate trial {trial_id} inside shard")
        seen_items[item_id] = record
        seen_trials[trial_id] = record
    missing = sorted(set(shard.item_ids) - set(seen_items))
    if missing:
        raise V2ParallelError(f"incomplete shard coverage for {shard.shard_id}: {missing}")
    payload = {
        "schema_version": 1,
        "shard_id": shard.shard_id,
        "identity_fingerprint": shard.identity_fingerprint,
        "item_ids": list(shard.item_ids),
        "status": "complete",
        "records": [seen_items[key] for key in sorted(seen_items)],
    }
    lease.assert_current()
    path = shard_result_path(root, shard)
    try:
        _publish_exclusive_json(path, payload)
    except FileExistsError:
        existing = _read_json_object(path, label="shard result")
        _validate_shard_payload(existing, shard)
        if existing != payload:
            raise V2ParallelError(f"conflicting persisted result for {shard.shard_id}")
    return path


def _validate_shard_payload(payload: Mapping[str, object], shard: ShardSpec) -> None:
    if payload.get("schema_version") != 1:
        raise V2ParallelError(f"unsupported shard result schema for {shard.shard_id}")
    if payload.get("shard_id") != shard.shard_id:
        raise V2ParallelError(f"shard result identity mismatch for {shard.shard_id}")
    if payload.get("status") != "complete":
        raise V2ParallelError(f"shard {shard.shard_id} is not complete")
    if payload.get("identity_fingerprint") != shard.identity_fingerprint:
        raise V2ParallelError(f"stale result fingerprint for {shard.shard_id}")
    if payload.get("item_ids") != list(shard.item_ids):
        raise V2ParallelError(f"shard membership drift for {shard.shard_id}")
    records = payload.get("records")
    if not isinstance(records, list):
        raise V2ParallelError(f"invalid records for {shard.shard_id}")
    seen_items: set[str] = set()
    seen_trials: dict[str, dict[str, object]] = {}
    for raw in records:
        if not isinstance(raw, Mapping):
            raise V2ParallelError(f"invalid trial record for {shard.shard_id}")
        record = dict(raw)
        item_id = str(record.get("item_id", ""))
        trial_id = str(record.get("trial_id", ""))
        if not item_id or not trial_id:
            raise V2ParallelError(
                f"shard result record requires trial_id and item_id for {shard.shard_id}"
            )
        if item_id not in shard.item_ids:
            raise V2ParallelError(f"foreign item {item_id} in {shard.shard_id}")
        if item_id in seen_items:
            raise V2ParallelError(f"duplicate item result {item_id} in {shard.shard_id}")
        if trial_id in seen_trials and seen_trials[trial_id] != record:
            raise V2ParallelError(f"conflicting duplicate trial {trial_id} inside shard")
        seen_items.add(item_id)
        seen_trials[trial_id] = record
    if seen_items != set(shard.item_ids):
        raise V2ParallelError(f"incomplete shard coverage for {shard.shard_id}")


def read_shard_result(root: Path, shard: ShardSpec) -> dict[str, object]:
    path = shard_result_path(root, shard)
    if not path.exists():
        raise V2ParallelError(f"missing completed result for {shard.shard_id}")
    payload = _read_json_object(path, label="shard result")
    _validate_shard_payload(payload, shard)
    return payload


def merge_shard_results(
    root: Path,
    *,
    manifest_path: Path,
    output_path: Path,
) -> list[dict[str, object]]:
    _, shards = load_manifest(manifest_path)
    merged: dict[str, dict[str, object]] = {}
    for shard in shards:
        payload = read_shard_result(root, shard)
        records = payload.get("records")
        if not isinstance(records, list):
            raise V2ParallelError(f"invalid records for {shard.shard_id}")
        for raw in records:
            if not isinstance(raw, Mapping):
                raise V2ParallelError(f"invalid trial record for {shard.shard_id}")
            record = dict(raw)
            trial_id = str(record.get("trial_id", ""))
            if not trial_id:
                raise V2ParallelError("merged trial record requires trial_id")
            existing = merged.get(trial_id)
            if existing is not None and existing != record:
                raise V2ParallelError(f"conflicting duplicate trial across shards: {trial_id}")
            merged[trial_id] = record
    ordered = [merged[key] for key in sorted(merged)]
    lines = "".join(_canonical_json(record) + "\n" for record in ordered)
    if output_path.exists():
        if output_path.read_text(encoding="utf-8") != lines:
            raise V2ParallelError("merged output conflicts with frozen manifest results")
    else:
        try:
            _publish_exclusive_text(output_path, lines)
        except FileExistsError:
            if output_path.read_text(encoding="utf-8") != lines:
                raise V2ParallelError("merged output conflicts with frozen manifest results")
    return ordered

def bounded_worker_count(requested: int, *, reserve_cpus: int = 1) -> int:
    if requested < 1:
        raise V2ParallelError("requested worker count must be positive")
    if reserve_cpus < 0:
        raise V2ParallelError("reserve_cpus cannot be negative")
    cpus = max(1, int(os.cpu_count() or 1))
    usable = max(1, cpus - reserve_cpus)
    return min(int(requested), usable)


def inspect_shard_state(
    root: Path, shard: ShardSpec, *, stale_after_seconds: float, now: float | None = None
) -> dict[str, object]:
    if stale_after_seconds <= 0:
        raise V2ParallelError("stale_after_seconds must be positive")
    root = Path(root)
    claim = root / "claims" / f"{shard.shard_id}.json"
    heartbeat = root / "heartbeats" / f"{shard.shard_id}.json"
    recovery_transaction = _recovery_transaction_path(root, shard)
    recovery_incomplete = recovery_transaction.exists()
    if recovery_incomplete:
        _validated_recovery_transaction(recovery_transaction, shard)
    _validate_completed_recoveries(root, shard)
    current = time.time() if now is None else float(now)
    claim_payload = None
    heartbeat_payload = None
    age = None
    if claim.exists():
        claim_payload = _read_json_object(claim, label="shard claim")
        _validate_shard_state_identity(claim_payload, shard, label="shard claim")
        try:
            age = max(0.0, current - float(claim_payload["acquired_unix"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise V2ParallelError(f"invalid claim timestamp for {shard.shard_id}") from exc
    if heartbeat.exists():
        heartbeat_payload = _read_json_object(heartbeat, label="shard heartbeat")
        _validate_shard_state_identity(heartbeat_payload, shard, label="shard heartbeat")
        heartbeat_matches_claim = claim_payload is None or (
            heartbeat_payload.get("lease_token") == claim_payload.get("lease_token")
            and heartbeat_payload.get("owner_id") == claim_payload.get("owner_id")
        )
        if heartbeat_matches_claim:
            try:
                age = max(0.0, current - float(heartbeat_payload["updated_unix"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise V2ParallelError(f"invalid heartbeat timestamp for {shard.shard_id}") from exc
    probe = FileLock(str(_shard_lock_path(root, shard)))
    lock_active = True
    try:
        probe.acquire(timeout=0)
        lock_active = False
    except Timeout:
        lock_active = True
    finally:
        if probe.is_locked:
            probe.release()
    result_state = "missing"
    result_error = None
    if shard_result_path(root, shard).exists():
        try:
            read_shard_result(root, shard)
            result_state = "complete"
        except V2ParallelError as exc:
            result_state = "invalid"
            result_error = str(exc)
    return {
        "shard_id": shard.shard_id,
        "claimed": claim.exists(),
        "claim_owner_id": None if claim_payload is None else claim_payload.get("owner_id"),
        "lock_active": lock_active,
        "result_complete": result_state == "complete",
        "result_state": result_state,
        "result_error": result_error,
        "heartbeat_age_seconds": age,
        "heartbeat_status": None if heartbeat_payload is None else heartbeat_payload.get("status"),
        "stale_claim": bool(claim.exists() and not lock_active and age is not None and age > stale_after_seconds),
        "recovery_incomplete": recovery_incomplete,
    }


def run_parallel_shards(
    root: Path,
    *,
    manifest_path: Path,
    worker: Callable[[ShardSpec, ShardLease], Sequence[Mapping[str, object]]],
    requested_workers: int,
    owner_id: str,
    reserve_cpus: int = 1,
) -> list[dict[str, object]]:
    """Run every shard in a frozen manifest with one OS-backed lease per shard."""
    _, shards = load_manifest(manifest_path)
    max_workers = bounded_worker_count(requested_workers, reserve_cpus=reserve_cpus)
    root = Path(root)

    def run_one(shard: ShardSpec) -> dict[str, object]:
        if shard_result_path(root, shard).exists():
            payload = read_shard_result(root, shard)
            return {"shard_id": shard.shard_id, "status": "resumed", "records": len(payload["records"])}
        lease = ShardLease(root, shard, owner_id=f"{owner_id}:{shard.shard_id}")
        lease.acquire()
        try:
            if shard_result_path(root, shard).exists():
                payload = read_shard_result(root, shard)
                lease.release(status="resumed", completed_items=len(shard.item_ids))
                return {
                    "shard_id": shard.shard_id,
                    "status": "resumed",
                    "records": len(payload["records"]),
                }
            records = list(worker(shard, lease))
            write_shard_result(root, shard, lease=lease, records=records)
            lease.release(status="complete", completed_items=len(shard.item_ids))
            return {"shard_id": shard.shard_id, "status": "complete", "records": len(records)}
        except Exception:
            lease.release(status="failed", completed_items=0)
            raise

    outcomes: dict[str, dict[str, object]] = {}
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="v2-shard") as pool:
        futures = {pool.submit(run_one, shard): shard for shard in shards}
        for future in as_completed(futures):
            shard = futures[future]
            outcomes[shard.shard_id] = future.result()
    return [outcomes[shard.shard_id] for shard in shards]
