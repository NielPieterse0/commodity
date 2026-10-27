"""Typed source declaration; never sufficient to authorize dataset admission."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import MarketTruthError


@dataclass(frozen=True, slots=True)
class SourceBuildAttestation:
    """Caller-provided build metadata, not cryptographic/source-owner proof."""

    dataset_scope: str
    protected_confirmation_accessed: bool
    source_manifest_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.dataset_scope, str)
            or not self.dataset_scope.strip()
            or type(self.protected_confirmation_accessed) is not bool
            or not isinstance(self.source_manifest_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.source_manifest_sha256) is None
        ):
            raise MarketTruthError("invalid source governance attestation structure")
