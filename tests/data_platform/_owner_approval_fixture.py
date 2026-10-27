"""Synthetic, ephemeral Ed25519 catalog signer for isolated negative/positive tests.

These test keys must never appear in deployed source-owner trust configuration.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from commodity.market_truth import approval

# One process-local ephemeral signer avoids rotating trust across retained readers.
_TEMP_SIGNER: tempfile.TemporaryDirectory[str] | None = None


def _openssl(*arguments: str) -> None:
    env = {"SystemRoot": os.environ.get("SystemRoot", r"C:\Windows")} if os.name == "nt" else {}
    for _ in range(3):
        completed = subprocess.run(
            [str(approval.OPENSSL_BINARY), *arguments],
            env=env, capture_output=True, check=False, timeout=10,
        )
        if completed.returncode & 0xFFFFFFFF != 0xC0000142:
            break
    if completed.returncode:
        raise AssertionError("synthetic OpenSSL fixture unavailable")


def sign_fixture_catalog(root: Path, catalog: dict) -> tuple[dict, dict[str, tuple[bytes, str]]]:
    """Sign every approved fixture with an ephemeral test-only private key."""
    catalog["schema_version"] = 2
    if not catalog["datasets"]:
        catalog.pop("signer_key_id", None)
        catalog.pop("signature_ed25519", None)
        return catalog, {}
    global _TEMP_SIGNER
    if _TEMP_SIGNER is None:
        _TEMP_SIGNER = tempfile.TemporaryDirectory(prefix="synthetic-market-truth-owner-")
        home = Path(_TEMP_SIGNER.name)
        _openssl("genpkey", "-algorithm", "ED25519", "-out", str(home / "owner.pem"))
        _openssl("pkey", "-in", str(home / "owner.pem"), "-pubout", "-out", str(home / "owner.pub"))
    private = Path(_TEMP_SIGNER.name) / "owner.pem"
    public = Path(_TEMP_SIGNER.name) / "owner.pub"
    public_bytes = public.read_bytes()
    dataset_bytes = json.dumps(catalog["datasets"], sort_keys=True).encode("utf-8")
    signer_id = "synthetic-fixture-" + hashlib.sha256(dataset_bytes).hexdigest()[:24]
    catalog["signer_key_id"] = signer_id
    message = root / "synthetic-approval.msg"
    signature = root / "synthetic-approval.sig"
    message.write_bytes(approval.signed_catalog_payload(catalog))
    _openssl(
        "pkeyutl", "-sign", "-inkey", str(private), "-rawin",
        "-in", str(message), "-out", str(signature),
    )
    catalog["signature_ed25519"] = signature.read_bytes().hex()
    # Test-only trust returned to a scoped patch; no global signer leaks.
    digest = hashlib.sha256(json.dumps(catalog).encode("utf-8")).hexdigest()
    return catalog, {signer_id: (public_bytes, digest)}
