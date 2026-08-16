import sys
import types
from typing import ClassVar

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
    monkeypatch.setattr(kronos, "model_config", lambda: {"models": {"kronos_mini": {
        "local_path": "vendor/Kronos",
        "tokenizer_id": "tokenizer",
        "tokenizer_revision": "tokenizer-rev",
        "model_id": "model",
        "model_revision": "model-rev",
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
