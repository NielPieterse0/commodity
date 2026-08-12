import pytest

from commodity import models


def test_baseline_factory_uses_configured_implementation() -> None:
    cfg = {
        "alias": {
            "enabled": True,
            "baseline_implementation": "zero_return",
        }
    }
    factory = models.baseline_factory("alias", cfg)
    assert isinstance(factory(), models.ZeroReturnModel)


def test_baseline_factory_rejects_unknown_implementation() -> None:
    cfg = {
        "alias": {
            "enabled": True,
            "baseline_implementation": "unknown",
        }
    }
    with pytest.raises(ValueError, match="Unsupported baseline implementation"):
        models.baseline_factory("alias", cfg)
