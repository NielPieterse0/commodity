import sys
import types

from commodity import kronos


class _Loader:
    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        return object()


class _Predictor:
    def __init__(self, *args, **kwargs) -> None:
        pass


def test_repeated_adapter_initialization_does_not_duplicate_sys_path(tmp_path, monkeypatch) -> None:
    local_path = tmp_path / "vendor" / "Kronos"
    local_path.mkdir(parents=True)
    fake_model = types.ModuleType("model")
    fake_model.Kronos = _Loader
    fake_model.KronosTokenizer = _Loader
    fake_model.KronosPredictor = _Predictor
    monkeypatch.setitem(sys.modules, "model", fake_model)
    monkeypatch.setattr(kronos, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(kronos, "model_config", lambda: {"models": {"kronos_mini": {
        "local_path": "vendor/Kronos",
        "tokenizer_id": "tokenizer",
        "tokenizer_revision": "tokenizer-rev",
        "model_id": "model",
        "model_revision": "model-rev",
        "device": "cpu",
        "max_context": 512,
    }}})
    path = str(local_path)
    while path in sys.path:
        sys.path.remove(path)

    kronos.KronosMiniAdapter()
    kronos.KronosMiniAdapter()

    assert sys.path.count(path) == 1
    sys.path.remove(path)
