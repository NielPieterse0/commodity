import pytest

from commodity.execution import DisabledExecutionAdapter, SaxoSimCandidate
from commodity.policy import (
    PolicyViolation,
    assert_execution_mode,
    assert_model_cannot_submit_orders,
)


def test_live_execution_is_prohibited() -> None:
    with pytest.raises(PolicyViolation):
        assert_execution_mode("live")


def test_live_execution_permission_is_owned_by_policy_config(monkeypatch) -> None:
    from commodity import policy as policy_module

    cfg = {
        "execution": {
            "live_trading_allowed": False,
            "allowed_modes": ["live"],
        }
    }
    monkeypatch.setattr(policy_module, "policy_config", lambda: cfg)
    with pytest.raises(PolicyViolation, match="LIVE trading is prohibited"):
        assert_execution_mode("live")

    cfg["execution"]["live_trading_allowed"] = True
    assert_execution_mode("live")


def test_model_has_no_order_authority() -> None:
    assert_model_cannot_submit_orders()


def test_execution_adapters_are_non_operational() -> None:
    order = {"instrument": "MNG", "quantity": 1}
    for adapter in (DisabledExecutionAdapter(), SaxoSimCandidate()):
        with pytest.raises(RuntimeError):
            adapter.submit(order, mode="simulation")
