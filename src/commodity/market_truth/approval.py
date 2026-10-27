"""Verify owner-signed dataset admission; dataset authors cannot mint approval.

The allowlist is intentionally empty until an independent source owner registers a
public verification key through reviewed deployment code. Private keys never enter
the repository, builder, catalog, or research process.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

from .errors import MarketTruthError

# Source-owner keys are trusted deployment authority, not dataset metadata.
# Empty until separately governed owner commissioning; DO NOT add fixture keys.
TRUSTED_SIGNERS: dict[str, tuple[bytes, str]] = {}
OPENSSL_BINARY = (
    Path("C:/Program Files/Git/usr/bin/openssl.exe")
    if sys.platform == "win32" else Path("/usr/bin/openssl")
)
SIGNED_CONTEXT = b"commodity.market_truth.owner_admission.v1\n"


def signed_catalog_payload(catalog: dict) -> bytes:
    """Domain-separated canonical bytes covering every admission record."""
    covered = {
        name: catalog[name]
        for name in ("schema_version", "authority", "datasets", "signer_key_id")
        if name in catalog
    }
    return SIGNED_CONTEXT + json.dumps(
        covered, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def verify_catalog_signature(
    catalog: dict, *, catalog_sha256: str,
    trusted_signers: Mapping[str, tuple[bytes, str]],
) -> None:
    """Require Ed25519 authorization whenever any dataset is admitted."""
    if not catalog["datasets"]:
        if set(catalog) != {"schema_version", "authority", "datasets"}:
            raise MarketTruthError("empty source approval catalog has extra claims")
        return
    if set(catalog) != {
        "schema_version", "authority", "datasets", "signer_key_id",
        "signature_ed25519",
    }:
        raise MarketTruthError("signed source-owner approval required")
    signer = catalog["signer_key_id"]
    if not isinstance(signer, str) or signer not in trusted_signers:
        raise MarketTruthError("untrusted source-owner signing key")
    raw_sig = catalog["signature_ed25519"]
    if not isinstance(raw_sig, str) or re.fullmatch(r"[0-9a-f]{128}", raw_sig) is None:
        raise MarketTruthError("invalid source-owner signature format")
    trust = trusted_signers[signer]
    if not isinstance(trust, tuple) or len(trust) != 2:
        raise MarketTruthError("invalid source-owner trust record")
    public_key, pinned_digest = trust
    if not isinstance(public_key, bytes) or len(public_key) > 4096:
        raise MarketTruthError("invalid trusted source-owner public key")
    try:
        with tempfile.TemporaryDirectory(prefix="commodity-owner-verify-") as dirname:
            stage = Path(dirname)
            (stage / "owner.pub").write_bytes(public_key)
            (stage / "approval.msg").write_bytes(signed_catalog_payload(catalog))
            (stage / "approval.sig").write_bytes(bytes.fromhex(raw_sig))
            # Fully-qualified, deployment-owned executable: never PATH lookup.
            # No shell, credentials, ambient OpenSSL configuration or network.
            env = {"SystemRoot": os.environ.get("SystemRoot", r"C:\Windows")} if os.name == "nt" else {}
            command = [
                str(OPENSSL_BINARY), "pkeyutl", "-verify", "-pubin",
                "-inkey", str(stage / "owner.pub"), "-rawin",
                "-in", str(stage / "approval.msg"),
                "-sigfile", str(stage / "approval.sig"),
            ]
            # Windows 0xC0000142 is process/DLL initialization failure, not
            # signature verification. Bounded retries never retry invalid signatures.
            for _ in range(3):
                completed = subprocess.run(
                    command, env=env, capture_output=True, check=False, timeout=10,
                )
                if completed.returncode & 0xFFFFFFFF != 0xC0000142:
                    break
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired) as exc:
        raise MarketTruthError("source-owner signature verifier unavailable") from exc
    if completed.returncode & 0xFFFFFFFF == 0xC0000142:
        raise MarketTruthError("source-owner signature verifier unavailable")
    if completed.returncode != 0:
        raise MarketTruthError("source-owner approval signature invalid")
    # A correct signature for an older release is not current authorization.
    # Only a separately deployed content pin may advance or revoke a release.
    if (
        not isinstance(pinned_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", pinned_digest) is None
        or pinned_digest != catalog_sha256
    ):
        raise MarketTruthError("untrusted source-owner catalog release")
