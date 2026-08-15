from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PIT_EVIDENCE_MODES = frozenset({"research_pit", "evaluation_pit", "canonical"})
AVAILABILITY_MODE_RULES = {
    "canonical": {
        "availability_statuses": frozenset({"verified"}),
        "revision_statuses": frozenset({"point_in_time", "issued_run_immutable"}),
    },
    "research_pit": {
        "availability_statuses": frozenset({"verified", "reconstructed_conservative"}),
        "revision_statuses": frozenset({"point_in_time", "issued_run_immutable"}),
    },
    "evaluation_pit": {
        "availability_statuses": frozenset({"verified", "reconstructed_conservative"}),
        "revision_statuses": frozenset({"point_in_time", "issued_run_immutable"}),
    },
    "screening": {
        "availability_statuses": frozenset({"verified", "reconstructed_conservative"}),
        "revision_statuses": frozenset({
            "point_in_time", "issued_run_immutable", "current_snapshot_revised_history"
        }),
    },
}


def evaluation_authority_is_valid(manifest: Mapping[str, Any]) -> bool:
    """Return whether an evaluation-only manifest is explicitly non-promotable."""
    return (
        manifest.get("evidence_mode") == "evaluation_pit"
        and manifest.get("market_evaluation_evidence") is True
        and manifest.get("canonical_market_evidence") is False
        and manifest.get("research_evaluation_eligible") is True
        and manifest.get("research_promotion_eligible") is False
    )
