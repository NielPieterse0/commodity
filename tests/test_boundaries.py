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


def test_model_has_no_order_authority() -> None:
    assert_model_cannot_submit_orders()


def test_execution_adapters_are_non_operational() -> None:
    order = {"instrument": "MNG", "quantity": 1}
    for adapter in (DisabledExecutionAdapter(), SaxoSimCandidate()):
        with pytest.raises(RuntimeError):
            adapter.submit(order, mode="simulation")
