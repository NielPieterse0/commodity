from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from commodity.policy import assert_execution_mode


class ExecutionAdapter(Protocol):
    def submit(self, order: dict[str, object], mode: str) -> str: ...


@dataclass
class DisabledExecutionAdapter:
    reason: str = "No broker approved"

    def submit(self, order: dict[str, object], mode: str) -> str:
        assert_execution_mode(mode)
        raise RuntimeError(f"Order submission disabled: {self.reason}")


@dataclass
class SaxoSimCandidate:
    approved: bool = False

    def submit(self, order: dict[str, object], mode: str) -> str:
        assert_execution_mode(mode)
        raise RuntimeError("Saxo adapter is unverified and intentionally non-operational")
