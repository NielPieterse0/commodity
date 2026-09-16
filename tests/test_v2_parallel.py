from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

from commodity import v2_parallel
from commodity.v2_parallel import (
    OptimizationIdentity,
    ShardLease,
    V2ParallelError,
    bounded_worker_count,
    deterministic_shards,
    inspect_shard_state,
    load_manifest,
    merge_shard_results,
    read_shard_result,
    recover_stale_claim,
    run_parallel_shards,
    shard_manifest,
    write_manifest,
    write_shard_result,
)


def _identity(**overrides: object) -> OptimizationIdentity:
    values = {
        "programme_issue": 393,
        "issue": 426,
        "evidence_class": "development",
        "code_id": "code-a",
        "dataset_id": "data-a",
        "search_plan_id": "plan-a",
    }
    values.update(overrides)
    return OptimizationIdentity(**values)


def _records(*item_ids: str) -> list[dict[str, object]]:
    return [
        {
            "item_id": item_id,
            "trial_id": f"trial-{item_id}",
            "status": "complete",
            "score": i,
        }
        for i, item_id in enumerate(item_ids)
    ]


def _manifest(tmp_path: Path, identity: OptimizationIdentity, shards) -> Path:
    path = tmp_path / "manifest.json"
    write_manifest(path, identity, shards)
    return path


def _persist(tmp_path: Path, shard, records):
    lease = ShardLease(tmp_path, shard, owner_id=f"test:{shard.shard_id}")
    lease.acquire()
    try:
        return write_shard_result(tmp_path, shard, lease=lease, records=records)
    finally:
        lease.release(completed_items=len(shard.item_ids))


@pytest.mark.skipif(os.name != "nt", reason="Windows durability helper")
def test_windows_durable_move_supports_replace_and_exclusive_publish(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("new", encoding="utf-8")
    destination.write_text("old", encoding="utf-8")

    v2_parallel._windows_move_file(source, destination, replace_existing=True)
    assert source.exists() is False
    assert destination.read_text(encoding="utf-8") == "new"

    contender = tmp_path / "contender.txt"
    contender.write_text("contender", encoding="utf-8")
    with pytest.raises(FileExistsError):
        v2_parallel._windows_move_file(contender, destination, replace_existing=False)
    assert contender.read_text(encoding="utf-8") == "contender"
    assert destination.read_text(encoding="utf-8") == "new"


def test_windows_move_file_uses_write_through_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, int]] = []

    class FakeMoveFile:
        argtypes = None
        restype = None

        def __call__(self, source: str, destination: str, flags: int) -> int:
            calls.append((source, destination, flags))
            return 1

    class FakeKernel32:
        MoveFileExW = FakeMoveFile()

    monkeypatch.setattr(
        v2_parallel.ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: FakeKernel32(),
        raising=False,
    )
    v2_parallel._windows_move_file(Path("source-a"), Path("dest-a"), replace_existing=True)
    v2_parallel._windows_move_file(Path("source-b"), Path("dest-b"), replace_existing=False)

    assert calls == [
        ("source-a", "dest-a", 0x00000009),
        ("source-b", "dest-b", 0x00000008),
    ]


def test_windows_move_file_propagates_api_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingMoveFile:
        argtypes = None
        restype = None

        def __call__(self, *_args) -> int:
            return 0

    class FakeKernel32:
        MoveFileExW = FailingMoveFile()

    monkeypatch.setattr(
        v2_parallel.ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: FakeKernel32(),
        raising=False,
    )
    monkeypatch.setattr(v2_parallel.ctypes, "get_last_error", lambda: 5, raising=False)
    with pytest.raises(OSError, match="failed durable move"):
        v2_parallel._windows_move_file(Path("source"), Path("dest"), replace_existing=True)


def test_deterministic_shards_are_stable_and_cover_all_items() -> None:
    identity = _identity()
    items = [f"trial-{i:03d}" for i in range(20)]
    first = deterministic_shards(items, shard_count=4, identity=identity)
    second = deterministic_shards(list(reversed(items)), shard_count=4, identity=identity)
    assert first == second
    assert sorted(item for shard in first for item in shard.item_ids) == sorted(items)
    assert all(shard.identity_fingerprint == identity.fingerprint for shard in first)


def test_sharding_rejects_duplicate_item_ids() -> None:
    with pytest.raises(V2ParallelError, match="unique"):
        deterministic_shards(["a", "a"], shard_count=2, identity=_identity())


def test_manifest_is_frozen_to_identity_and_membership(tmp_path: Path) -> None:
    identity = _identity()
    shards = deterministic_shards(["a", "b", "c"], shard_count=2, identity=identity)
    path = tmp_path / "manifest.json"
    write_manifest(path, identity, shards)
    write_manifest(path, identity, shards)
    assert json.loads(path.read_text(encoding="utf-8")) == shard_manifest(identity, shards)
    changed = _identity(search_plan_id="plan-b")
    changed_shards = deterministic_shards(["a", "b", "c"], shard_count=2, identity=changed)
    with pytest.raises(V2ParallelError, match="conflicts"):
        write_manifest(path, changed, changed_shards)


def test_shard_ids_are_scoped_to_frozen_optimization_identity() -> None:
    first = _identity(search_plan_id="plan-a")
    second = _identity(search_plan_id="plan-b")
    first_shards = deterministic_shards(["a", "b", "c"], shard_count=2, identity=first)
    second_shards = deterministic_shards(["a", "b", "c"], shard_count=2, identity=second)
    first_ids = {shard.shard_id for shard in first_shards}
    second_ids = {shard.shard_id for shard in second_shards}
    assert first_ids.isdisjoint(second_ids)
    assert all(shard_id.startswith(f"shard-{first.fingerprint[:12]}-") for shard_id in first_ids)
    assert all(shard_id.startswith(f"shard-{second.fingerprint[:12]}-") for shard_id in second_ids)


def test_manifest_rejects_path_escaping_or_unreconstructable_shard_ids(tmp_path: Path) -> None:
    identity = _identity()
    shards = deterministic_shards(["a", "b"], shard_count=2, identity=identity)
    payload = shard_manifest(identity, shards)
    path = tmp_path / "manifest.json"

    payload["shards"][0]["shard_id"] = "../../escape"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(V2ParallelError, match="invalid shard ID"):
        load_manifest(path)

    payload = shard_manifest(identity, shards)
    payload["shards"][0]["shard_id"] = f"shard-{identity.fingerprint[:12]}-000-000000000000"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(V2ParallelError, match="does not match"):
        load_manifest(path)


def test_manifest_normalizes_malformed_ordinal_to_integrity_error(tmp_path: Path) -> None:
    identity = _identity()
    shards = deterministic_shards(["a"], shard_count=1, identity=identity)
    payload = shard_manifest(identity, shards)
    payload["shards"][0]["ordinal"] = "not-an-integer"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(V2ParallelError, match="ordinal is invalid"):
        load_manifest(path)


def test_shard_lease_is_exclusive_even_with_old_heartbeat(tmp_path: Path) -> None:
    shard = deterministic_shards(["a"], shard_count=1, identity=_identity())[0]
    first = ShardLease(tmp_path, shard, owner_id="worker-a")
    first.acquire()
    heartbeat = json.loads(first.heartbeat_path.read_text(encoding="utf-8"))
    heartbeat["updated_unix"] = 10.0
    first.heartbeat_path.write_text(json.dumps(heartbeat), encoding="utf-8")
    with pytest.raises(V2ParallelError, match="already claimed"):
        ShardLease(tmp_path, shard, owner_id="worker-b").acquire()
    state = inspect_shard_state(tmp_path, shard, stale_after_seconds=5.0, now=20.0)
    assert state["claimed"] is True
    assert state["lock_active"] is True
    assert state["stale_claim"] is False
    first.release(completed_items=1)


def test_orphaned_claim_requires_explicit_stale_recovery_after_worker_death(tmp_path: Path) -> None:
    shard = deterministic_shards(["a"], shard_count=1, identity=_identity())[0]
    dead = ShardLease(tmp_path, shard, owner_id="dead-worker")
    dead.acquire()
    old_token = dead.token
    heartbeat = json.loads(dead.heartbeat_path.read_text(encoding="utf-8"))
    heartbeat["updated_unix"] = 10.0
    dead.heartbeat_path.write_text(json.dumps(heartbeat), encoding="utf-8")
    dead._lock.release()
    dead._acquired = False
    state = inspect_shard_state(tmp_path, shard, stale_after_seconds=5.0, now=20.0)
    assert state["stale_claim"] is True

    with pytest.raises(V2ParallelError, match="explicit stale recovery required"):
        ShardLease(tmp_path, shard, owner_id="replacement").acquire()
    with pytest.raises(V2ParallelError, match="not stale"):
        recover_stale_claim(
            tmp_path,
            shard,
            stale_after_seconds=20.0,
            recovery_owner_id="coordinator",
            now=20.0,
        )

    receipt = recover_stale_claim(
        tmp_path,
        shard,
        stale_after_seconds=5.0,
        recovery_owner_id="coordinator",
        now=20.0,
    )
    recovery = json.loads(receipt.read_text(encoding="utf-8"))
    assert recovery["recovered_lease_token"] == old_token
    assert recovery["previous_owner_id"] == "dead-worker"
    assert recovery["recovery_owner_id"] == "coordinator"
    assert recovery["heartbeat_matches_claim"] is True
    transaction_archive = tmp_path / "reclaimed" / str(recovery["transaction_archive"])
    transaction = json.loads(transaction_archive.read_text(encoding="utf-8"))
    assert transaction["heartbeat_matches_claim"] is True
    assert list((tmp_path / "reclaimed").glob(f"{shard.shard_id}.{old_token[:16]}.*.claim.json"))
    assert list((tmp_path / "reclaimed").glob(f"{shard.shard_id}.{old_token[:16]}.*.heartbeat.json"))

    replacement = ShardLease(tmp_path, shard, owner_id="replacement")
    replacement.acquire()
    assert replacement.token != old_token
    with pytest.raises(V2ParallelError, match="lease is not held"):
        write_shard_result(tmp_path, shard, lease=dead, records=_records("a"))
    replacement.release(status="failed")


def test_stale_recovery_resumes_after_crash_between_archive_moves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shard = deterministic_shards(["a"], shard_count=1, identity=_identity())[0]
    dead = ShardLease(tmp_path, shard, owner_id="dead-worker")
    dead.acquire()
    heartbeat = json.loads(dead.heartbeat_path.read_text(encoding="utf-8"))
    heartbeat["updated_unix"] = 10.0
    dead.heartbeat_path.write_text(json.dumps(heartbeat), encoding="utf-8")
    dead._lock.release()
    dead._acquired = False

    real_move = v2_parallel._durable_move_exclusive
    archive_moves = 0

    def crash_on_second_archive(source, destination):
        nonlocal archive_moves
        source_path = Path(source)
        if source_path in {dead.claim_path, dead.heartbeat_path}:
            archive_moves += 1
            if archive_moves == 2:
                raise OSError("simulated crash between archive moves")
        return real_move(source, destination)

    monkeypatch.setattr(v2_parallel, "_durable_move_exclusive", crash_on_second_archive)
    with pytest.raises(OSError, match="simulated crash"):
        recover_stale_claim(
            tmp_path,
            shard,
            stale_after_seconds=5.0,
            recovery_owner_id="coordinator",
            now=20.0,
        )

    state = inspect_shard_state(tmp_path, shard, stale_after_seconds=5.0, now=20.0)
    assert state["recovery_incomplete"] is True
    assert dead.claim_path.exists() is False
    assert dead.heartbeat_path.exists() is True
    with pytest.raises(V2ParallelError, match="incomplete stale recovery transaction"):
        ShardLease(tmp_path, shard, owner_id="replacement").acquire()

    monkeypatch.setattr(v2_parallel, "_durable_move_exclusive", real_move)
    receipt = recover_stale_claim(
        tmp_path,
        shard,
        stale_after_seconds=5.0,
        recovery_owner_id="replacement-coordinator",
        now=200.0,
    )
    assert receipt.exists()
    assert dead.heartbeat_path.exists() is False
    assert not list((tmp_path / "recovery-transactions").glob("*.json"))

    replacement = ShardLease(tmp_path, shard, owner_id="replacement")
    replacement.acquire()
    replacement.release(status="failed")


def test_stale_recovery_resumes_after_crash_before_receipt_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shard = deterministic_shards(["a"], shard_count=1, identity=_identity())[0]
    dead = ShardLease(tmp_path, shard, owner_id="dead-worker")
    dead.acquire()
    heartbeat = json.loads(dead.heartbeat_path.read_text(encoding="utf-8"))
    heartbeat["updated_unix"] = 10.0
    dead.heartbeat_path.write_text(json.dumps(heartbeat), encoding="utf-8")
    dead._lock.release()
    dead._acquired = False

    real_publish = v2_parallel._publish_exclusive_json

    def crash_before_receipt(path: Path, payload) -> None:
        if Path(path).parent.name == "reclaimed" and Path(path).name.endswith(".recovery.json"):
            raise OSError("simulated crash before recovery receipt")
        real_publish(path, payload)

    monkeypatch.setattr(v2_parallel, "_publish_exclusive_json", crash_before_receipt)
    with pytest.raises(OSError, match="simulated crash"):
        recover_stale_claim(
            tmp_path,
            shard,
            stale_after_seconds=5.0,
            recovery_owner_id="coordinator",
            now=20.0,
        )

    assert dead.claim_path.exists() is False
    assert dead.heartbeat_path.exists() is False
    state = inspect_shard_state(tmp_path, shard, stale_after_seconds=5.0, now=200.0)
    assert state["recovery_incomplete"] is True
    with pytest.raises(V2ParallelError, match="incomplete stale recovery transaction"):
        ShardLease(tmp_path, shard, owner_id="replacement").acquire()

    monkeypatch.setattr(v2_parallel, "_publish_exclusive_json", real_publish)
    receipt = recover_stale_claim(
        tmp_path,
        shard,
        stale_after_seconds=5.0,
        recovery_owner_id="replacement-coordinator",
        now=200.0,
    )
    recovery = json.loads(receipt.read_text(encoding="utf-8"))
    assert recovery["recovery_owner_id"] == "coordinator"
    assert not list((tmp_path / "recovery-transactions").glob("*.json"))


@pytest.mark.parametrize("heartbeat_mode", ["missing", "mismatched"])
def test_stale_recovery_handles_crash_after_claim_before_current_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, heartbeat_mode: str
) -> None:
    shard = deterministic_shards(["a"], shard_count=1, identity=_identity())[0]
    original_heartbeat = ShardLease.heartbeat

    def crash_before_heartbeat(self: ShardLease, **_: object) -> None:
        if self.owner_id == "dead-worker":
            raise OSError("simulated crash before initial heartbeat")
        original_heartbeat(self)

    monkeypatch.setattr(ShardLease, "heartbeat", crash_before_heartbeat)
    dead = ShardLease(tmp_path, shard, owner_id="dead-worker")
    with pytest.raises(OSError, match="simulated crash"):
        dead.acquire()
    claim = json.loads(dead.claim_path.read_text(encoding="utf-8"))
    claim["acquired_unix"] = 10.0
    dead.claim_path.write_text(json.dumps(claim), encoding="utf-8")
    assert dead.heartbeat_path.exists() is False

    if heartbeat_mode == "mismatched":
        dead.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        dead.heartbeat_path.write_text(
            json.dumps(
                {
                    "shard_id": shard.shard_id,
                    "owner_id": "prior-worker",
                    "lease_token": "0" * 32,
                    "identity_fingerprint": shard.identity_fingerprint,
                    "status": "running",
                    "completed_items": 0,
                    "updated_unix": 19.0,
                }
            ),
            encoding="utf-8",
        )

    receipt = recover_stale_claim(
        tmp_path,
        shard,
        stale_after_seconds=5.0,
        recovery_owner_id="coordinator",
        now=20.0,
    )
    recovery = json.loads(receipt.read_text(encoding="utf-8"))
    assert recovery["heartbeat_present"] is (heartbeat_mode == "mismatched")
    assert recovery["heartbeat_matches_claim"] is False
    assert recovery["recovered_lease_token"] == dead.token
    transaction_archive = tmp_path / "reclaimed" / str(recovery["transaction_archive"])
    transaction = json.loads(transaction_archive.read_text(encoding="utf-8"))
    assert transaction["heartbeat_matches_claim"] is False

    replacement = ShardLease(tmp_path, shard, owner_id="replacement")
    replacement.acquire()
    replacement.release(status="failed")


@pytest.mark.parametrize(
    "artifact", ["claim_archive", "heartbeat_archive", "receipt", "transaction_archive"]
)
def test_completed_stale_recovery_detects_archived_evidence_tampering(
    tmp_path: Path, artifact: str
) -> None:
    shard = deterministic_shards(["a"], shard_count=1, identity=_identity())[0]
    dead = ShardLease(tmp_path, shard, owner_id="dead-worker")
    dead.acquire()
    heartbeat = json.loads(dead.heartbeat_path.read_text(encoding="utf-8"))
    heartbeat["updated_unix"] = 10.0
    dead.heartbeat_path.write_text(json.dumps(heartbeat), encoding="utf-8")
    dead._lock.release()
    dead._acquired = False
    receipt = recover_stale_claim(
        tmp_path,
        shard,
        stale_after_seconds=5.0,
        recovery_owner_id="coordinator",
        now=20.0,
    )
    recovery = json.loads(receipt.read_text(encoding="utf-8"))

    if artifact == "receipt":
        recovery["previous_owner_id"] = "tampered"
        receipt.write_text(json.dumps(recovery), encoding="utf-8")
    else:
        archive = tmp_path / "reclaimed" / str(recovery[artifact])
        payload = json.loads(archive.read_text(encoding="utf-8"))
        if artifact == "transaction_archive":
            payload["heartbeat_matches_claim"] = not payload["heartbeat_matches_claim"]
        else:
            payload["tampered"] = True
        archive.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(V2ParallelError):
        inspect_shard_state(tmp_path, shard, stale_after_seconds=5.0, now=20.0)


@pytest.mark.parametrize("state_file", ["claim", "heartbeat"])
def test_shard_state_rejects_same_identity_payload_misfiled_under_another_shard(
    tmp_path: Path, state_file: str
) -> None:
    shards = deterministic_shards(["a", "b"], shard_count=2, identity=_identity())
    target, foreign = shards
    dead = ShardLease(tmp_path, target, owner_id="dead-worker")
    dead.acquire()
    heartbeat = json.loads(dead.heartbeat_path.read_text(encoding="utf-8"))
    heartbeat["updated_unix"] = 10.0
    dead.heartbeat_path.write_text(json.dumps(heartbeat), encoding="utf-8")
    dead._lock.release()
    dead._acquired = False

    path = dead.claim_path if state_file == "claim" else dead.heartbeat_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["shard_id"] = foreign.shard_id
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(V2ParallelError, match=f"shard {state_file} identity mismatch"):
        inspect_shard_state(tmp_path, target, stale_after_seconds=5.0, now=20.0)
    with pytest.raises(V2ParallelError, match=f"shard {state_file} identity mismatch"):
        recover_stale_claim(
            tmp_path,
            target,
            stale_after_seconds=5.0,
            recovery_owner_id="coordinator",
            now=20.0,
        )


def test_lease_assert_current_rejects_foreign_shard_claim(tmp_path: Path) -> None:
    shards = deterministic_shards(["a", "b"], shard_count=2, identity=_identity())
    target, foreign = shards
    lease = ShardLease(tmp_path, target, owner_id="worker")
    lease.acquire()
    try:
        claim = json.loads(lease.claim_path.read_text(encoding="utf-8"))
        claim["shard_id"] = foreign.shard_id
        lease.claim_path.write_text(json.dumps(claim), encoding="utf-8")
        with pytest.raises(V2ParallelError, match="shard claim identity mismatch"):
            lease.assert_current()
    finally:
        lease._lock.release()
        lease._acquired = False


def test_stale_recovery_resumes_after_crash_before_transaction_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shard = deterministic_shards(["a"], shard_count=1, identity=_identity())[0]
    dead = ShardLease(tmp_path, shard, owner_id="dead-worker")
    dead.acquire()
    heartbeat = json.loads(dead.heartbeat_path.read_text(encoding="utf-8"))
    heartbeat["updated_unix"] = 10.0
    dead.heartbeat_path.write_text(json.dumps(heartbeat), encoding="utf-8")
    dead._lock.release()
    dead._acquired = False

    real_move = v2_parallel._durable_move_exclusive

    def crash_before_transaction_archive(source, destination):
        if (
            Path(source).parent.name == "recovery-transactions"
            and Path(destination).name.endswith(".transaction.json")
        ):
            raise OSError("simulated crash before transaction archive")
        return real_move(source, destination)

    monkeypatch.setattr(v2_parallel, "_durable_move_exclusive", crash_before_transaction_archive)
    with pytest.raises(OSError, match="simulated crash"):
        recover_stale_claim(
            tmp_path,
            shard,
            stale_after_seconds=5.0,
            recovery_owner_id="coordinator",
            now=20.0,
        )
    assert list((tmp_path / "reclaimed").glob("*.recovery.json"))
    assert list((tmp_path / "recovery-transactions").glob("*.json"))
    with pytest.raises(V2ParallelError, match="incomplete stale recovery transaction"):
        ShardLease(tmp_path, shard, owner_id="replacement").acquire()

    monkeypatch.setattr(v2_parallel, "_durable_move_exclusive", real_move)
    receipt = recover_stale_claim(
        tmp_path,
        shard,
        stale_after_seconds=5.0,
        recovery_owner_id="replacement-coordinator",
        now=200.0,
    )
    assert receipt.exists()
    assert not list((tmp_path / "recovery-transactions").glob("*.json"))
    assert list((tmp_path / "reclaimed").glob("*.transaction.json"))


def test_completed_recovery_remains_valid_after_crash_post_transaction_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shard = deterministic_shards(["a"], shard_count=1, identity=_identity())[0]
    dead = ShardLease(tmp_path, shard, owner_id="dead-worker")
    dead.acquire()
    heartbeat = json.loads(dead.heartbeat_path.read_text(encoding="utf-8"))
    heartbeat["updated_unix"] = 10.0
    dead.heartbeat_path.write_text(json.dumps(heartbeat), encoding="utf-8")
    dead._lock.release()
    dead._acquired = False

    real_validate = v2_parallel._validate_completed_recovery
    crashed = False

    def crash_after_transaction_archive(root, checked_shard, transaction_archive):
        nonlocal crashed
        if not crashed:
            crashed = True
            raise OSError("simulated crash after transaction archive")
        return real_validate(root, checked_shard, transaction_archive)

    monkeypatch.setattr(v2_parallel, "_validate_completed_recovery", crash_after_transaction_archive)
    with pytest.raises(OSError, match="simulated crash"):
        recover_stale_claim(
            tmp_path,
            shard,
            stale_after_seconds=5.0,
            recovery_owner_id="coordinator",
            now=20.0,
        )
    assert not list((tmp_path / "recovery-transactions").glob("*.json"))
    transaction_archives = list((tmp_path / "reclaimed").glob("*.transaction.json"))
    assert len(transaction_archives) == 1
    reclaimed_before = {
        path.name: path.read_bytes() for path in sorted((tmp_path / "reclaimed").iterdir())
    }
    original_receipts = list((tmp_path / "reclaimed").glob("*.recovery.json"))
    assert len(original_receipts) == 1
    original_receipt = original_receipts[0]

    monkeypatch.setattr(v2_parallel, "_validate_completed_recovery", real_validate)
    receipt = recover_stale_claim(
        tmp_path,
        shard,
        stale_after_seconds=5.0,
        recovery_owner_id="retry-coordinator",
        now=200.0,
    )
    assert receipt == original_receipt
    recovery = json.loads(receipt.read_text(encoding="utf-8"))
    assert recovery["recovery_owner_id"] == "coordinator"
    reclaimed_after = {
        path.name: path.read_bytes() for path in sorted((tmp_path / "reclaimed").iterdir())
    }
    assert reclaimed_after == reclaimed_before

    replacement = ShardLease(tmp_path, shard, owner_id="replacement")
    replacement.acquire()
    replacement.release(status="failed")


def test_stale_recovery_refuses_an_active_os_lock(tmp_path: Path) -> None:
    shard = deterministic_shards(["a"], shard_count=1, identity=_identity())[0]
    active = ShardLease(tmp_path, shard, owner_id="active-worker")
    active.acquire()
    try:
        with pytest.raises(V2ParallelError, match="active OS lock"):
            recover_stale_claim(
                tmp_path,
                shard,
                stale_after_seconds=0.001,
                recovery_owner_id="coordinator",
                now=time.time() + 1.0,
            )
    finally:
        active.release(status="failed")


def test_shard_result_is_atomic_idempotent_and_conflict_safe(tmp_path: Path) -> None:
    shard = deterministic_shards(["a"], shard_count=1, identity=_identity())[0]
    records = _records("a")
    path = _persist(tmp_path, shard, records)
    assert _persist(tmp_path, shard, records) == path
    lease = ShardLease(tmp_path, shard, owner_id="conflict-writer")
    lease.acquire()
    try:
        with pytest.raises(V2ParallelError, match="conflicting persisted"):
            write_shard_result(
                tmp_path,
                shard,
                lease=lease,
                records=[
                    {
                        "item_id": "a",
                        "trial_id": "trial-a",
                        "status": "complete",
                        "score": 99,
                    }
                ],
            )
    finally:
        lease.release(status="failed")


@pytest.mark.parametrize(
    ("corruption", "match"),
    [
        ("schema", "unsupported shard result schema"),
        ("shard_id", "shard result identity mismatch"),
        ("trial_id", "requires trial_id and item_id"),
    ],
)
def test_read_shard_result_rejects_structural_corruption(
    tmp_path: Path, corruption: str, match: str
) -> None:
    shard = deterministic_shards(["a"], shard_count=1, identity=_identity())[0]
    path = _persist(tmp_path, shard, _records("a"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if corruption == "schema":
        payload["schema_version"] = 2
    elif corruption == "shard_id":
        payload["shard_id"] = "foreign-shard"
    else:
        payload["records"][0].pop("trial_id")
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(V2ParallelError, match=match):
        read_shard_result(tmp_path, shard)


def test_parallel_runner_rejects_corrupt_completed_result_instead_of_resuming(
    tmp_path: Path
) -> None:
    identity = _identity()
    shard = deterministic_shards(["a"], shard_count=1, identity=identity)[0]
    manifest = _manifest(tmp_path, identity, [shard])
    path = _persist(tmp_path, shard, _records("a"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["records"][0].pop("trial_id")
    path.write_text(json.dumps(payload), encoding="utf-8")
    worker_called = False

    def worker(*_):
        nonlocal worker_called
        worker_called = True
        return _records("a")

    with pytest.raises(V2ParallelError, match="requires trial_id and item_id"):
        run_parallel_shards(
            tmp_path,
            manifest_path=manifest,
            worker=worker,
            requested_workers=1,
            owner_id="orchestrator",
            reserve_cpus=0,
        )
    assert worker_called is False


def test_merge_is_deterministic(tmp_path: Path) -> None:
    identity = _identity()
    shards = deterministic_shards(["a", "b", "c"], shard_count=2, identity=identity)
    assert len(shards) == 2
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    left_manifest = _manifest(left, identity, shards)
    right_manifest = _manifest(right, identity, shards)

    for shard in shards:
        _persist(left, shard, _records(*shard.item_ids))
    for shard in reversed(shards):
        records = list(reversed(_records(*shard.item_ids)))
        _persist(right, shard, records)

    left_output = left / "trials.jsonl"
    right_output = right / "trials.jsonl"
    left_merged = merge_shard_results(
        left, manifest_path=left_manifest, output_path=left_output
    )
    right_merged = merge_shard_results(
        right, manifest_path=right_manifest, output_path=right_output
    )
    assert [row["trial_id"] for row in left_merged] == ["trial-a", "trial-b", "trial-c"]
    assert right_merged == left_merged
    assert right_output.read_bytes() == left_output.read_bytes()

    original_bytes = left_output.read_bytes()
    repeated = merge_shard_results(
        left, manifest_path=left_manifest, output_path=left_output
    )
    assert repeated == left_merged
    assert left_output.read_bytes() == original_bytes


def test_merge_rejects_conflicting_duplicate_trials(tmp_path: Path) -> None:
    identity = _identity()
    shards = deterministic_shards(["a", "b"], shard_count=2, identity=identity)
    assert len(shards) == 2
    manifest = _manifest(tmp_path, identity, shards)
    first_item = shards[0].item_ids[0]
    second_item = shards[1].item_ids[0]
    _persist(
        tmp_path,
        shards[0],
        [{"item_id": first_item, "trial_id": "same", "score": 1}],
    )
    _persist(
        tmp_path,
        shards[1],
        [{"item_id": second_item, "trial_id": "same", "score": 2}],
    )
    with pytest.raises(V2ParallelError, match="conflicting duplicate trial across shards"):
        merge_shard_results(
            tmp_path, manifest_path=manifest, output_path=tmp_path / "merged.jsonl"
        )


def test_merge_rejects_stale_identity_fingerprint(tmp_path: Path) -> None:
    identity = _identity()
    shard = deterministic_shards(["a"], shard_count=1, identity=identity)[0]
    manifest = _manifest(tmp_path, identity, [shard])
    path = _persist(tmp_path, shard, _records("a"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["identity_fingerprint"] = "stale"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(V2ParallelError, match="stale result fingerprint"):
        merge_shard_results(
            tmp_path, manifest_path=manifest, output_path=tmp_path / "merged.jsonl"
        )


def test_worker_count_is_host_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("commodity.v2_parallel.os.cpu_count", lambda: 8)
    assert bounded_worker_count(20, reserve_cpus=1) == 7
    assert bounded_worker_count(3, reserve_cpus=1) == 3
    with pytest.raises(V2ParallelError, match="positive"):
        bounded_worker_count(0)
    with pytest.raises(V2ParallelError, match="negative"):
        bounded_worker_count(1, reserve_cpus=-1)


def test_parallel_runner_executes_concurrently_and_resumes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("commodity.v2_parallel.os.cpu_count", lambda: 8)
    identity = _identity()
    shards = deterministic_shards(
        [f"item-{i}" for i in range(4)], shard_count=4, identity=identity
    )
    manifest = _manifest(tmp_path, identity, shards)
    lock = threading.Lock()
    active = 0
    max_active = 0

    def worker(shard, lease):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        lease.heartbeat(completed_items=0)
        time.sleep(0.05)
        with lock:
            active -= 1
        return [
            {"item_id": item_id, "trial_id": f"trial-{item_id}", "status": "complete"}
            for item_id in shard.item_ids
        ]

    first = run_parallel_shards(
        tmp_path,
        manifest_path=manifest,
        worker=worker,
        requested_workers=4,
        owner_id="orchestrator",
    )
    assert max_active > 1
    assert {row["status"] for row in first} == {"complete"}

    second = run_parallel_shards(
        tmp_path,
        manifest_path=manifest,
        worker=lambda *_: pytest.fail("completed shard reran"),
        requested_workers=4,
        owner_id="orchestrator",
    )
    assert {row["status"] for row in second} == {"resumed"}


def test_delayed_contender_rechecks_completed_result_after_lease_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shard = deterministic_shards(["a"], shard_count=1, identity=identity)[0]
    manifest = _manifest(tmp_path, identity, [shard])
    contender_at_acquire = threading.Event()
    allow_contender = threading.Event()
    original_acquire = ShardLease.acquire
    worker_called = threading.Event()
    result: list[dict[str, object]] = []
    failure: list[BaseException] = []

    def controlled_acquire(self: ShardLease) -> None:
        if self.owner_id.startswith("late:"):
            contender_at_acquire.set()
            if not allow_contender.wait(timeout=2.0):
                raise AssertionError("test contender was not released")
        original_acquire(self)

    monkeypatch.setattr(ShardLease, "acquire", controlled_acquire)

    def contender() -> None:
        try:
            result.extend(
                run_parallel_shards(
                    tmp_path,
                    manifest_path=manifest,
                    worker=lambda *_: (worker_called.set(), _records("a"))[1],
                    requested_workers=1,
                    owner_id="late",
                    reserve_cpus=0,
                )
            )
        except Exception as exc:  # noqa: BLE001  # pragma: no cover - diagnostic handoff
            failure.append(exc)

    thread = threading.Thread(target=contender)
    thread.start()
    assert contender_at_acquire.wait(timeout=2.0)
    _persist(tmp_path, shard, _records("a"))
    allow_contender.set()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert not failure
    assert worker_called.is_set() is False
    assert result == [{"shard_id": shard.shard_id, "status": "resumed", "records": 1}]


def test_single_and_dual_worker_modes_produce_identical_results(tmp_path: Path) -> None:
    identity = _identity()
    items = [f"item-{i}" for i in range(6)]
    shards = deterministic_shards(items, shard_count=3, identity=identity)

    def worker(shard, lease):
        time.sleep(0.01 * (len(shards) - shard.ordinal))
        lease.heartbeat(completed_items=0)
        records = []
        for item_id in reversed(shard.item_ids):
            ordinal = int(item_id.rsplit("-", 1)[1])
            records.append(
                {
                    "item_id": item_id,
                    "trial_id": f"trial-{item_id}",
                    "status": "complete",
                    "score": ordinal / 7.0,
                    "metrics": {"monthly_return": ordinal * 123.45, "rank": ordinal},
                }
            )
        return records

    outputs: list[list[dict[str, object]]] = []
    serialized: list[bytes] = []
    for worker_count, name in ((1, "single"), (2, "dual")):
        root = tmp_path / name
        root.mkdir()
        manifest = root / "manifest.json"
        write_manifest(manifest, identity, shards)
        run_parallel_shards(
            root,
            manifest_path=manifest,
            worker=worker,
            requested_workers=worker_count,
            owner_id=f"{name}-orchestrator",
        )
        merged_path = root / "merged.jsonl"
        outputs.append(
            merge_shard_results(
                root,
                manifest_path=manifest,
                output_path=merged_path,
            )
        )
        serialized.append(merged_path.read_bytes())
    assert outputs[0] == outputs[1]
    assert serialized[0] == serialized[1]


def test_shard_completion_requires_exact_item_coverage(tmp_path: Path) -> None:
    shard = deterministic_shards(["a", "b"], shard_count=1, identity=_identity())[0]
    lease = ShardLease(tmp_path, shard, owner_id="coverage-test")
    lease.acquire()
    try:
        with pytest.raises(V2ParallelError, match="incomplete shard coverage"):
            write_shard_result(tmp_path, shard, lease=lease, records=_records("a"))
        with pytest.raises(V2ParallelError, match="foreign item"):
            write_shard_result(
                tmp_path,
                shard,
                lease=lease,
                records=[
                    {"item_id": "a", "trial_id": "trial-a"},
                    {"item_id": "foreign", "trial_id": "trial-foreign"},
                ],
            )
        with pytest.raises(V2ParallelError, match="duplicate item result"):
            write_shard_result(
                tmp_path,
                shard,
                lease=lease,
                records=[
                    {"item_id": "a", "trial_id": "trial-a"},
                    {"item_id": "a", "trial_id": "trial-a-2"},
                ],
            )
    finally:
        lease.release(status="failed")


def test_inspection_marks_corrupt_result_invalid(tmp_path: Path) -> None:
    shard = deterministic_shards(["a"], shard_count=1, identity=_identity())[0]
    path = tmp_path / "results" / f"{shard.shard_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    state = inspect_shard_state(tmp_path, shard, stale_after_seconds=60.0)
    assert state["result_complete"] is False
    assert state["result_state"] == "invalid"
    assert "malformed" in str(state["result_error"])


def test_malformed_existing_claim_fails_with_integrity_error(tmp_path: Path) -> None:
    shard = deterministic_shards(["a"], shard_count=1, identity=_identity())[0]
    claim = tmp_path / "claims" / f"{shard.shard_id}.json"
    claim.parent.mkdir(parents=True, exist_ok=True)
    claim.write_text("", encoding="utf-8")
    with pytest.raises(V2ParallelError, match="shard claim is unreadable or malformed"):
        ShardLease(tmp_path, shard, owner_id="worker-b").acquire()


def test_merge_requires_every_manifest_shard(tmp_path: Path) -> None:
    identity = _identity()
    shards = deterministic_shards(["a", "b"], shard_count=2, identity=identity)
    manifest = _manifest(tmp_path, identity, shards)
    _persist(tmp_path, shards[0], _records(*shards[0].item_ids))
    with pytest.raises(V2ParallelError, match="missing completed result"):
        merge_shard_results(
            tmp_path, manifest_path=manifest, output_path=tmp_path / "merged.jsonl"
        )


def test_concurrent_manifest_writers_cannot_overwrite_identity(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    identities = [_identity(search_plan_id="plan-a"), _identity(search_plan_id="plan-b")]
    outcomes: list[str] = []
    lock = threading.Lock()

    def publish(identity: OptimizationIdentity) -> None:
        shards = deterministic_shards(["a", "b"], shard_count=2, identity=identity)
        try:
            write_manifest(path, identity, shards)
            outcome = "published"
        except V2ParallelError:
            outcome = "conflict"
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=publish, args=(identity,)) for identity in identities]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["conflict", "published"]
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["identity"]["search_plan_id"] in {"plan-a", "plan-b"}
