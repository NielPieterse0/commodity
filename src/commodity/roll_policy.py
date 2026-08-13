from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VolumeCrossoverPolicy:
    confirmation_sessions: int
    forced_roll_days_before_expiry: int
    volume_evidence: str
    crossover: str
    tie_behavior: str
    missing_volume_behavior: str
    holiday_behavior: str
    contract_unavailable_behavior: str
    no_later_contract_behavior: str


_REQUIRED = (
    "method",
    "confirmation_sessions",
    "forced_roll_days_before_expiry",
    "volume_evidence",
    "crossover",
    "tie_behavior",
    "missing_volume_behavior",
    "holiday_behavior",
    "contract_unavailable_behavior",
    "no_later_contract_behavior",
)

_SUPPORTED = {
    "method": "volume_crossover_dte_v1",
    "volume_evidence": "prior_observed_session",
    "crossover": "strict_greater_than",
    "tie_behavior": "reset_confirmation_and_hold",
    "missing_volume_behavior": "reset_confirmation_and_hold",
    "holiday_behavior": "count_observed_sessions_only",
    "contract_unavailable_behavior": "nearest_later_eligible",
    "no_later_contract_behavior": "fail_closed",
}


def parse_volume_crossover_policy(policy: dict[str, Any]) -> VolumeCrossoverPolicy:
    missing = [field for field in _REQUIRED if field not in policy]
    if missing:
        raise ValueError(f"Roll policy missing explicit fields: {missing}")
    for field, supported in _SUPPORTED.items():
        if policy[field] != supported:
            raise ValueError(
                f"Unsupported roll-policy {field}: {policy[field]!r}; supported={supported!r}"
            )
    confirmation = int(policy["confirmation_sessions"])
    forced_days = int(policy["forced_roll_days_before_expiry"])
    if confirmation < 1:
        raise ValueError("Roll policy confirmation_sessions must be at least 1")
    if forced_days < 0:
        raise ValueError("Roll policy forced_roll_days_before_expiry must be non-negative")
    return VolumeCrossoverPolicy(
        confirmation_sessions=confirmation,
        forced_roll_days_before_expiry=forced_days,
        volume_evidence=str(policy["volume_evidence"]),
        crossover=str(policy["crossover"]),
        tie_behavior=str(policy["tie_behavior"]),
        missing_volume_behavior=str(policy["missing_volume_behavior"]),
        holiday_behavior=str(policy["holiday_behavior"]),
        contract_unavailable_behavior=str(policy["contract_unavailable_behavior"]),
        no_later_contract_behavior=str(policy["no_later_contract_behavior"]),
    )
