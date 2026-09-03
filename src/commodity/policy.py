from __future__ import annotations

from datetime import datetime

from commodity.config import policy_config


class PolicyViolation(RuntimeError):
    pass


def _assert_human_live_approval(policy: dict) -> None:
    approval = policy.get("human_live_approval", {})
    if approval.get("required") is not True or approval.get("status") != "approved":
        raise PolicyViolation("LIVE trading requires explicit human approval")
    required = ("approved_by", "approved_at_utc", "decision_id")
    if any(not isinstance(approval.get(field), str) or not approval[field] for field in required):
        raise PolicyViolation("LIVE trading human approval record is incomplete")
    try:
        approved_at = datetime.fromisoformat(approval["approved_at_utc"])
    except ValueError as exc:
        raise PolicyViolation("LIVE trading human approval timestamp is invalid") from exc
    if approved_at.tzinfo is None:
        raise PolicyViolation("LIVE trading human approval timestamp must include timezone")


def assert_execution_mode(mode: str) -> None:
    policy = policy_config()["execution"]
    if mode == "live" and not policy.get("live_trading_allowed", False):
        raise PolicyViolation("LIVE trading is prohibited by config/trading-policy.json")
    if mode not in policy["allowed_modes"]:
        raise PolicyViolation(f"Execution mode not approved: {mode}")
    if mode == "live":
        _assert_human_live_approval(policy)


def assert_model_cannot_submit_orders() -> None:
    if policy_config()["execution"]["model_may_submit_orders"]:
        raise PolicyViolation("Model order authority must remain disabled")
