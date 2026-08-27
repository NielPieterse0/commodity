import hashlib
import sys
import types
from pathlib import Path

import pytest

from commodity import kronos_runtime

ROOT = Path(__file__).resolve().parents[1]


def test_kronos_runtime_lock_is_exact_and_separate_from_primary_lock() -> None:
    authority = kronos_runtime.runtime_lock_authority(ROOT)
    lock = ROOT / authority["path"]
    assert authority["path"] == "requirements.kronos-cpu.lock.txt"
    assert lock != ROOT / "requirements.lock.txt"
    assert authority["sha256"] == hashlib.sha256(lock.read_bytes()).hexdigest()
    assert authority["python"] == "3.11"
    assert authority["platform"] == "windows_x86_64"
    assert authority["torch"] == "2.13.0+cpu"
    assert authority["packages"]["torch"] == "2.13.0+cpu"
    assert authority["packages"]["huggingface-hub"] == "0.36.2"


def test_runtime_lock_rejects_incomplete_metadata(tmp_path: Path, monkeypatch) -> None:
    lock = tmp_path / "runtime.lock.txt"
    lock.write_text("# python: 3.11\ntorch==2.13.0+cpu\n", encoding="utf-8")
    monkeypatch.setattr(kronos_runtime, "RUNTIME_LOCK_PATH", lock.name)
    with pytest.raises(kronos_runtime.KronosRuntimeError, match="metadata is incomplete"):
        kronos_runtime.runtime_lock_authority(tmp_path)


def test_runtime_lock_rejects_torch_metadata_drift(tmp_path: Path, monkeypatch) -> None:
    lock = tmp_path / "runtime.lock.txt"
    lock.write_text(
        "# python: 3.11\n# platform: windows_x86_64\n# torch: 2.12.0+cpu\ntorch==2.13.0+cpu\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(kronos_runtime, "RUNTIME_LOCK_PATH", lock.name)
    with pytest.raises(kronos_runtime.KronosRuntimeError, match="Torch metadata"):
        kronos_runtime.runtime_lock_authority(tmp_path)


def test_synthetic_cpu_replay_is_deterministic(monkeypatch) -> None:
    state = {"seed": 0}

    class FakeTensor:
        pass

    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return False

    fake_torch = types.SimpleNamespace(
        float32="float32",
        cuda=FakeCuda(),
        manual_seed=lambda value: state.update(seed=value),
        tensor=lambda values, dtype=None: FakeTensor(),
        multinomial=lambda tensor, num_samples, replacement: types.SimpleNamespace(
            tolist=lambda: [(state["seed"] + index) % 4 for index in range(num_samples)]
        ),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(
        kronos_runtime,
        "validate_installed_runtime",
        lambda _: {
            "sha256": "a" * 64,
            "python": "3.11",
            "platform": "windows_x86_64",
            "torch": "2.13.0+cpu",
        },
    )
    replay = kronos_runtime.synthetic_cpu_replay(ROOT)
    assert replay["device"] == "cpu"
    assert replay["synthetic_replay_count"] == 32
    assert len(replay["synthetic_replay_sha256"]) == 64
