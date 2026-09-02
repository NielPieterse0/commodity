import pytest

from commodity.providers.canonical import ProviderLoadError, load_canonical_provider


def test_provider_loader_resolves_adapter_by_convention(monkeypatch) -> None:
    sentinel = object()
    imported = []

    class Module:
        @staticmethod
        def create_provider():
            return sentinel

    def fake_import(name: str):
        imported.append(name)
        return Module()

    monkeypatch.setattr("commodity.providers.canonical.importlib.import_module", fake_import)
    assert load_canonical_provider("example_futures") is sentinel
    assert imported == ["commodity.providers.example_futures"]


def test_provider_loader_rejects_non_identifier_provider_id() -> None:
    with pytest.raises(ProviderLoadError, match="Invalid canonical provider id"):
        load_canonical_provider("../example")


def test_provider_loader_fails_closed_when_adapter_has_no_factory(monkeypatch) -> None:
    monkeypatch.setattr(
        "commodity.providers.canonical.importlib.import_module", lambda _: object()
    )
    with pytest.raises(ProviderLoadError, match="create_provider"):
        load_canonical_provider("example_futures")


def test_provider_loader_does_not_mask_adapter_dependency_errors(monkeypatch) -> None:
    missing = ModuleNotFoundError("No module named 'broken_dependency'", name="broken_dependency")

    def fake_import(_: str):
        raise missing

    monkeypatch.setattr("commodity.providers.canonical.importlib.import_module", fake_import)
    with pytest.raises(ModuleNotFoundError, match="broken_dependency"):
        load_canonical_provider("example_futures")

