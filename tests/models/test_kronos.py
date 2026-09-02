import subprocess
import sys
import types
from typing import ClassVar

import pandas as pd
import pytest

from commodity import kronos


class _Loader:
    calls: ClassVar[list[tuple[tuple, dict]]] = []

    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        cls.calls.append((args, kwargs))
        return object()


class _Predictor:
    def __init__(self, *args, **kwargs) -> None:
        pass


def test_repeated_adapter_initialization_does_not_duplicate_sys_path(tmp_path, monkeypatch) -> None:
    local_path = tmp_path / "vendor" / "Kronos"
    local_path.mkdir(parents=True)
    model_snapshot = tmp_path / "cache" / "model"
    tokenizer_snapshot = tmp_path / "cache" / "tokenizer"
    model_snapshot.mkdir(parents=True)
    tokenizer_snapshot.mkdir(parents=True)
    fake_model = types.ModuleType("model")
    fake_model.Kronos = _Loader
    fake_model.KronosTokenizer = _Loader
    fake_model.KronosPredictor = _Predictor
    monkeypatch.setitem(sys.modules, "model", fake_model)
    monkeypatch.setattr(kronos, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        kronos,
        "resolve_kronos_artifacts",
        lambda cfg: {
            "model": {"snapshot_path": str(model_snapshot)},
            "tokenizer": {"snapshot_path": str(tokenizer_snapshot)},
        },
    )
    monkeypatch.setattr(
        kronos,
        "verify_kronos_source_checkout",
        lambda path, expected_revision: expected_revision,
        raising=False,
    )
    monkeypatch.setattr(kronos, "model_config", lambda: {"models": {"kronos_mini": {
        "local_path": "vendor/Kronos",
        "tokenizer_id": "tokenizer",
        "tokenizer_revision": "tokenizer-rev",
        "model_id": "model",
        "model_revision": "model-rev",
        "source_revision": "f" * 40,
        "device": "cpu",
        "max_context": 512,
        "inference": {"T": 1.0, "top_p": 0.9, "sample_count": 1, "verbose": False},
    }}})
    path = str(local_path)
    while path in sys.path:
        sys.path.remove(path)

    kronos.KronosMiniAdapter()
    kronos.KronosMiniAdapter()

    assert sys.path.count(path) == 1
    assert _Loader.calls[-2][0] == (str(tokenizer_snapshot),)
    assert _Loader.calls[-1][0] == (str(model_snapshot),)
    sys.path.remove(path)


def test_kronos_source_checkout_requires_exact_clean_revision(tmp_path) -> None:
    source = tmp_path / "Kronos"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    tracked = source / "model.py"
    tracked.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "model.py"], check=True)
    subprocess.run(
        [
            "git", "-C", str(source),
            "-c", "user.name=Test",
            "-c", "user.email=test@example.invalid",
            "commit", "-q", "-m", "fixture",
        ],
        check=True,
    )
    revision = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert kronos.verify_kronos_source_checkout(source, revision) == revision
    tracked.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(kronos.KronosArtifactError, match="must be clean"):
        kronos.verify_kronos_source_checkout(source, revision)

    subprocess.run(["git", "-C", str(source), "reset", "--hard", "-q"], check=True)
    (source / "shadow.py").write_text("VALUE = 9\n", encoding="utf-8")
    with pytest.raises(kronos.KronosArtifactError, match="must be clean"):
        kronos.verify_kronos_source_checkout(source, revision)

    (source / "shadow.py").unlink()
    with pytest.raises(kronos.KronosArtifactError, match="revision mismatch"):
        kronos.verify_kronos_source_checkout(source, "0" * 40)


@pytest.mark.parametrize("adapter_type", [kronos.KronosMiniAdapter, kronos.KronosCheckpointAdapter])
def test_forecast_rejects_non_datetime_history_index(adapter_type) -> None:
    adapter = adapter_type.__new__(adapter_type)
    adapter.predictor = object()
    adapter.inference = {"T": 1.0, "top_p": 0.9, "sample_count": 1, "verbose": False}
    history = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]}
    )
    future = pd.date_range("2026-01-02", periods=1, tz="UTC")

    with pytest.raises(kronos.KronosArtifactError, match="DatetimeIndex"):
        adapter.forecast(history, future)
