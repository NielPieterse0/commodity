"""Private owner signing for Phase 2 review; never self-publish admission."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from . import approval
from .errors import MarketTruthError

ROOT = Path(__file__).resolve().parents[3]
# Private signing identity must outlive disposable governed worktree cleanup.
# The project-local ignored runtime is stable across development worktrees.
OWNER_ROOT = (
    ROOT.parent.parent.parent
    if ROOT.parent.name == "worktrees" and ROOT.parent.parent.name == ".work"
    else ROOT
)
SIGNING_DIR = OWNER_ROOT / ".work/runtime/market_truth_development/owner-signing"
PRIVATE_KEY = SIGNING_DIR / "owner-private.pem"
PUBLIC_KEY = SIGNING_DIR / "owner-public.pem"
SIGNED_DECISIONS = SIGNING_DIR / "signed-decisions"
APPROVAL_CODE_CONFIG = SIGNING_DIR / "mobile-approval-code.json"
ICACLS_BINARY = Path("C:/Windows/System32/icacls.exe")
WHOAMI_BINARY = Path("C:/Windows/System32/whoami.exe")
POWERSHELL_BINARY = Path("C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
_CODE_LOCK = threading.RLock()
_CODE_TTL_SECONDS = 30 * 60


def _run(*args: str) -> None:
    """Invoke fixed trusted utilities; never leak stderr or private material."""
    env = {"SystemRoot": os.environ.get("SystemRoot", r"C:\Windows")} if os.name == "nt" else {}
    try:
        result = subprocess.run(
            list(args), env=env, check=False, capture_output=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MarketTruthError("owner signing utility unavailable") from exc
    if result.returncode != 0:
        raise MarketTruthError("owner signing command failed")


def _owner_sid() -> str:
    """Resolve the authenticated Windows token, never USERNAME environment text."""
    if os.name != "nt" or not WHOAMI_BINARY.is_file():
        raise MarketTruthError("Windows token identity unavailable")
    try:
        result = subprocess.run(
            [str(WHOAMI_BINARY), "/user", "/fo", "csv", "/nh"],
            capture_output=True, check=True, timeout=10,
        )
        import csv
        import io
        row = next(csv.reader(io.StringIO(result.stdout.decode("utf-8-sig"))))
        sid = row[-1].strip()
    except (OSError, subprocess.SubprocessError, ValueError, UnicodeError, StopIteration) as exc:
        raise MarketTruthError("Windows token identity unavailable") from exc
    if not sid.startswith("S-1-5-") or not all(p.isdecimal() for p in sid.split("-")[1:]):
        raise MarketTruthError("invalid Windows owner SID")
    return sid


def _require_unreparsed_owner_path() -> None:
    """Reject junctions/symlinks in the private owner signing directory ancestry."""
    if os.name != "nt":
        return
    for path in (SIGNING_DIR, *SIGNING_DIR.parents):
        if path.is_symlink() or (path.exists() and
                                 path.stat(follow_symlinks=False).st_file_attributes & 0x400):
            raise MarketTruthError("owner signing path reparse point prohibited")


@contextmanager
def _locked_signing_directory():
    """Hold non-delete-sharing Windows handles for signing dir and ancestors."""
    if os.name != "nt":
        raise MarketTruthError("signing directory lock requires Windows")
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    attrs = kernel.GetFileAttributesW
    attrs.argtypes = [wintypes.LPCWSTR]
    attrs.restype = wintypes.DWORD
    invalid = ctypes.c_void_p(-1).value
    paths = [*reversed(SIGNING_DIR.parents), SIGNING_DIR]
    handles = []
    try:
        for path in paths:
            handle = create(str(path), 0x80, 0x3, None, 3, 0x2200000, None)
            if handle in (None, invalid):
                raise MarketTruthError("signing directory handle protection unavailable")
            handles.append(handle)
            flags = attrs(str(path))
            if flags == 0xFFFFFFFF or flags & 0x400:
                raise MarketTruthError("signing directory reparse or identity invalid")
        yield
    finally:
        for handle in reversed(handles):
            close(handle)


def _require_private_acl(path: Path, *, protected: bool = False) -> None:
    """Check Windows ownership and allow ACEs, including pre-existing explicit ACEs."""
    if os.name != "nt":
        return
    if not POWERSHELL_BINARY.is_file():
        raise MarketTruthError("Windows ACL verifier unavailable")
    _require_unreparsed_owner_path()
    if path.is_symlink() or not path.exists():
        raise MarketTruthError("owner ACL path invalid")
    literal = str(path).replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop';"
        "$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;"
        f"$acl=Get-Acl -LiteralPath '{literal}';"
        "$owner=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value;"
        "if($owner -ne $sid){exit 10};"
        + ("if(-not $acl.AreAccessRulesProtected){exit 11};" if protected else "")
        + "$access=@($acl.Access);if($access.Count -eq 0){exit 12};"
        "$seen=$false;"
        "foreach($ace in $access){"
        "$who=$ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value;"
        "if($ace.AccessControlType -ne 'Allow' -or "
        "($who -ne $sid -and $who -ne 'S-1-5-18')){exit 13};"
        "if($who -eq $sid){$seen=$true}"
        "};if(-not $seen){exit 14}"
    )
    _run(str(POWERSHELL_BINARY), "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-Command", script)


def _assert_private_storage() -> None:
    """Fail closed if any signer asset has an unexpected owner or ACL."""
    if os.name != "nt":
        return
    _require_private_acl(SIGNING_DIR, protected=True)
    for path in (PRIVATE_KEY, PUBLIC_KEY):
        _require_private_acl(path)
    if APPROVAL_CODE_CONFIG.exists():
        _require_private_acl(APPROVAL_CODE_CONFIG)


def commission_owner_key() -> dict:
    """Create a new owner-only directory; reject pre-existing hostile ACL state."""
    if os.name != "nt":
        raise MarketTruthError("owner key commissioning requires Windows ACL")
    _require_unreparsed_owner_path()
    if SIGNING_DIR.exists() or PRIVATE_KEY.exists() or PUBLIC_KEY.exists():
        raise MarketTruthError("owner signing directory already exists; review ACL before use")
    sid = _owner_sid()
    if not ICACLS_BINARY.is_file():
        raise MarketTruthError("trusted Windows ACL utility missing")
    SIGNING_DIR.parent.mkdir(parents=True, exist_ok=True)
    SIGNING_DIR.mkdir(exist_ok=False)
    # Keep directory and ancestor identities pinned during ACL setup/key creation.
    with _locked_signing_directory():
        _run(str(ICACLS_BINARY), str(SIGNING_DIR), "/inheritance:r")
        _run(str(ICACLS_BINARY), str(SIGNING_DIR), "/grant:r", f"*{sid}:(OI)(CI)F")
        _require_private_acl(SIGNING_DIR, protected=True)
        _run(str(approval.OPENSSL_BINARY), "genpkey", "-algorithm", "ED25519",
             "-out", str(PRIVATE_KEY))
        _run(str(approval.OPENSSL_BINARY), "pkey", "-in", str(PRIVATE_KEY),
             "-pubout", "-out", str(PUBLIC_KEY))
        for path in (PRIVATE_KEY, PUBLIC_KEY):
            _run(str(ICACLS_BINARY), str(path), "/inheritance:r")
            _run(str(ICACLS_BINARY), str(path), "/grant:r", f"*{sid}:F")
        _assert_private_storage()
        return public_identity()


def public_identity() -> dict:
    if not PRIVATE_KEY.is_file() or not PUBLIC_KEY.is_file():
        raise MarketTruthError("owner signing key not commissioned")
    if PRIVATE_KEY.is_symlink() or PUBLIC_KEY.is_symlink():
        raise MarketTruthError("owner signing key symlink prohibited")
    _assert_private_storage()
    public = PUBLIC_KEY.read_bytes()
    if not public.startswith(b"-----BEGIN PUBLIC KEY-----") or len(public) > 4096:
        raise MarketTruthError("invalid owner public key")
    return {"key_id": "owner-" + hashlib.sha256(public).hexdigest()[:24],
            "public_key_sha256": hashlib.sha256(public).hexdigest()}


def commission_mobile_approval_code(dataset_sha256: str) -> str:
    """Rotate the owner factor; scope it to one dataset and a 30-minute window."""
    if os.name != "nt":
        raise MarketTruthError("mobile approval code commissioning requires Windows")
    if len(dataset_sha256) != 64 or any(c not in "0123456789abcdef" for c in dataset_sha256):
        raise MarketTruthError("invalid approval dataset identity")
    _require_unreparsed_owner_path()
    public_identity()
    code = secrets.token_urlsafe(24)
    salt = secrets.token_bytes(16)
    digest = hmac.new(salt, code.encode("ascii"), hashlib.sha256).hexdigest()
    config = {
        "schema_version": 2, "salt_hex": salt.hex(), "code_sha256": digest,
        "dataset_content_sha256": dataset_sha256,
        "expires_unix": int(time.time()) + _CODE_TTL_SECONDS,
    }
    with _CODE_LOCK:
        if APPROVAL_CODE_CONFIG.is_symlink():
            raise MarketTruthError("approval code symlink prohibited")
        # Preserve the old record as revoked evidence; never reuse its secret.
        if APPROVAL_CODE_CONFIG.exists():
            revoked = APPROVAL_CODE_CONFIG.with_name("revoked-code-" + secrets.token_hex(16) + ".json")
            os.replace(APPROVAL_CODE_CONFIG, revoked)
        with APPROVAL_CODE_CONFIG.open("xb") as stream:
            stream.write(_canonical(config) + b"\n")
        _require_private_acl(APPROVAL_CODE_CONFIG)
    return code


def _code_matches(code: str, dataset_sha256: str) -> bool:
    if not isinstance(code, str) or not 20 <= len(code) <= 128:
        return False
    if not isinstance(dataset_sha256, str) or len(dataset_sha256) != 64:
        return False
    if APPROVAL_CODE_CONFIG.is_symlink():
        return False
    try:
        _require_private_acl(APPROVAL_CODE_CONFIG)
        raw = APPROVAL_CODE_CONFIG.read_bytes()
        if len(raw) > 1024:
            return False
        config = json.loads(raw)
        if (set(config) != {"schema_version", "salt_hex", "code_sha256",
                            "dataset_content_sha256", "expires_unix"}
                or config["schema_version"] != 2
                or config["dataset_content_sha256"] != dataset_sha256
                or type(config["expires_unix"]) is not int
                or not time.time() < config["expires_unix"] <= time.time() + _CODE_TTL_SECONDS):
            return False
        salt = bytes.fromhex(config["salt_hex"])
        expected = config["code_sha256"]
        if len(salt) != 16 or not isinstance(expected, str) or len(expected) != 64:
            return False
        supplied = hmac.new(salt, code.encode("ascii"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, supplied)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, MarketTruthError):
        return False


def approval_code_ready(dataset_sha256: str) -> bool:
    """Report factor readiness without exposing or validating a bearer code."""
    try:
        _require_private_acl(APPROVAL_CODE_CONFIG)
        config = json.loads(APPROVAL_CODE_CONFIG.read_bytes())
        return (
            config.get("schema_version") == 2
            and config.get("dataset_content_sha256") == dataset_sha256
            and type(config.get("expires_unix")) is int
            and time.time() < config["expires_unix"] <= time.time() + _CODE_TTL_SECONDS
        )
    except (OSError, TypeError, ValueError, MarketTruthError):
        return False


def verify_mobile_approval_code(code: str, dataset_sha256: str) -> bool:
    """Non-consuming precheck. Only consumption authorizes an owner signature."""
    with _CODE_LOCK:
        return _code_matches(code, dataset_sha256)


def consume_mobile_approval_code(code: str, dataset_sha256: str) -> bool:
    """Atomically revoke the one-time factor before signing; fail closed on races."""
    with _CODE_LOCK:
        if not _code_matches(code, dataset_sha256):
            return False
        consumed = APPROVAL_CODE_CONFIG.with_name("consumed-code-" + secrets.token_hex(16) + ".json")
        try:
            os.replace(APPROVAL_CODE_CONFIG, consumed)
        except OSError:
            return False
        # Another process might have rotated the file between read and rename.
        # Never authorize a different config's consumption.
        try:
            raw = json.loads(consumed.read_bytes())
            salt = bytes.fromhex(raw["salt_hex"])
            digest = hmac.new(salt, code.encode("ascii"), hashlib.sha256).hexdigest()
            return (raw.get("dataset_content_sha256") == dataset_sha256
                    and hmac.compare_digest(raw["code_sha256"], digest))
        except (OSError, ValueError, TypeError, KeyError):
            return False


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def sign_owner_approval(meta: dict, *, reviewer_login: str,
                        reviewer_label: str, notes: str, verified: bool) -> dict:
    """Sign a catalog candidate bound to exact reviewed source and final bytes."""
    if not verified or not reviewer_login or not reviewer_label:
        raise MarketTruthError("verified owner identity and review evidence required")
    identity = public_identity()
    from .review_site import FINAL_MANIFEST, SOURCE_MANIFEST, digest_file
    final = json.loads(FINAL_MANIFEST.read_bytes())
    if (digest_file(FINAL_MANIFEST) != meta["final_manifest_sha256"]
            or digest_file(SOURCE_MANIFEST) != meta["source_manifest_sha256"]
            or final["content_sha256"] != meta["dataset_content_sha256"]
            or final["source_sha256"]["bars"] != meta["source_sha256"]
            or final["tables"]["bars"]["sha256"] != meta["final_sha256"]
            or set(final["tables"]) != {"bars", "definitions", "statistics"}):
        raise MarketTruthError("source/final manifest changed before signing")
    now = datetime.now(UTC).isoformat()
    review = {
        "decision": "approve", "reviewer_login": reviewer_login,
        "reviewer_label": reviewer_label, "notes": notes,
        "created_at_utc": now, "dataset_content_sha256": meta["dataset_content_sha256"],
    }
    review_id = hashlib.sha256(_canonical(review)).hexdigest()
    entry = {
        "content_sha256": meta["dataset_content_sha256"],
        "source_manifest_sha256": meta["source_manifest_sha256"],
        "source_sha256": final["source_sha256"],
        "tables_sha256": {k: final["tables"][k]["sha256"]
                          for k in sorted(final["tables"])},
        "source_review_id": review_id, "local_evidence_verified": True,
    }
    catalog = {
        "schema_version": 2, "authority": "governed_source_owner_review",
        "datasets": [entry], "signer_key_id": identity["key_id"],
    }
    SIGNED_DECISIONS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sign-", dir=SIGNING_DIR) as temporary:
        stage = Path(temporary)
        (stage / "message").write_bytes(approval.signed_catalog_payload(catalog))
        _run(str(approval.OPENSSL_BINARY), "pkeyutl", "-sign",
             "-inkey", str(PRIVATE_KEY), "-rawin", "-in", str(stage / "message"),
             "-out", str(stage / "signature"))
        signature = (stage / "signature").read_bytes()
    if len(signature) != 64:
        raise MarketTruthError("invalid owner signature length")
    catalog["signature_ed25519"] = signature.hex()
    catalog_bytes = _canonical(catalog) + b"\n"
    approval.verify_catalog_signature(
        catalog, catalog_sha256=hashlib.sha256(catalog_bytes).hexdigest(),
        trusted_signers={identity["key_id"]: (
            PUBLIC_KEY.read_bytes(), hashlib.sha256(catalog_bytes).hexdigest(),
        )},
    )
    # This is evidence pending governed promotion, not an admitted catalog.
    receipt = {
        "schema_version": 1, "evidence_type": "SIGNED_OWNER_APPROVAL_CANDIDATE",
        "source_review_id": review_id, "review": review,
        "catalog": catalog, "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        "signer_public_key_sha256": identity["public_key_sha256"],
        "signed_owner_approval": True, "research_admitted": False,
    }
    verify_signed_receipt(receipt)
    file = SIGNED_DECISIONS / (review_id + ".json")
    with file.open("xb") as stream:
        stream.write(_canonical(receipt) + b"\n")
    return receipt

def verify_signed_receipt(receipt: dict) -> None:
    """Check on-disk owner evidence; never treat this as independent admission."""
    try:
        review, catalog = receipt["review"], receipt["catalog"]
        review_id = hashlib.sha256(_canonical(review)).hexdigest()
        raw = _canonical(catalog) + b"\n"
        digest = hashlib.sha256(raw).hexdigest()
        identity = public_identity()
        if (receipt["source_review_id"] != review_id
                or catalog["datasets"][0]["source_review_id"] != review_id
                or receipt["catalog_sha256"] != digest
                or catalog["signer_key_id"] != identity["key_id"]
                or receipt["signer_public_key_sha256"] != identity["public_key_sha256"]
                or review["decision"] != "approve"
                or receipt["research_admitted"] is not False):
            raise MarketTruthError("signed owner receipt identity mismatch")
        approval.verify_catalog_signature(
            catalog, catalog_sha256=digest,
            trusted_signers={identity["key_id"]: (PUBLIC_KEY.read_bytes(), digest)},
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise MarketTruthError("malformed owner approval receipt") from exc
