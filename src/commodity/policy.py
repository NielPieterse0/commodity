from __future__ import annotations

from commodity.config import policy_config


class PolicyViolation(RuntimeError):
    pass


def assert_execution_mode(mode: str) -> None:
    policy = policy_config()["execution"]
    if mode == "live":
        raise PolicyViolation("LIVE trading is prohibited by config/policy.json")
    if mode not in policy["allowed_modes"]:
        raise PolicyViolation(f"Execution mode not approved: {mode}")


def assert_model_cannot_submit_orders() -> None:
    if policy_config()["execution"]["model_may_submit_orders"]:
        raise PolicyViolation("Model order authority must remain disabled")
