#!/usr/bin/env python3
"""Reusable fail-closed verifier for code-pinned detached Ed25519 attestations."""

from __future__ import annotations

import base64
import binascii
import errno
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping


OPENSSL_BINARY = Path("/usr/bin/openssl")
MAX_PUBLIC_KEY_BYTES = 64 * 1024
MAX_VERIFIER_BINARY_BYTES = 64 * 1024 * 1024
OPENSSL_SUBPROCESS_ENVIRONMENT = (
    ("LANG", "C"),
    ("LC_ALL", "C"),
    ("OPENSSL_CONF", "/dev/null"),
)
COMMON_FIELDS = {
    "contract_name",
    "algorithm",
    "key_id",
    "role",
    "generated_at_utc",
    "signature",
}


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def read_regular_file_bytes(
    path: Path,
    *,
    max_bytes: int = MAX_PUBLIC_KEY_BYTES,
) -> tuple[bytes | None, str | None]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return None, "symlink_rejected"
        return None, "unreadable"
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return None, "not_a_regular_file"
        if before.st_size > max_bytes:
            return None, "too_large"
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                return None, "too_large"
        after = os.fstat(descriptor)
        identity_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, field) != getattr(after, field) for field in identity_fields):
            return None, "changed_during_read"
        return b"".join(chunks), None
    except OSError:
        return None, "unreadable"
    finally:
        os.close(descriptor)


def read_pinned_public_key(
    key_id: str,
    *,
    role: str,
    trusted_identities: Mapping[str, Mapping[str, str]],
    trusted_key_root: Path,
) -> tuple[bytes | None, str | None, str | None]:
    identity = trusted_identities.get(key_id)
    if not isinstance(identity, Mapping):
        return None, None, "attestation key_id is not allowlisted"
    if identity.get("role") != role:
        return None, None, f"attestation key is not allowlisted for {role}"
    relative_path = Path(str(identity.get("public_key_path") or ""))
    expected_sha256 = str(identity.get("public_key_sha256") or "").lower()
    if relative_path.is_absolute() or not expected_sha256 or len(expected_sha256) != 64:
        return None, None, "trusted attester pin is invalid"
    if any(character not in "0123456789abcdef" for character in expected_sha256):
        return None, None, "trusted attester pin is invalid"

    root = trusted_key_root.resolve()
    unresolved_path = root / relative_path
    try:
        if stat.S_ISLNK(os.lstat(unresolved_path).st_mode):
            return None, None, "trusted attester key is symlink_rejected"
    except FileNotFoundError:
        return None, None, "trusted attester key is missing"
    except OSError:
        return None, None, "trusted attester key is unreadable"
    key_path = unresolved_path.resolve()
    try:
        key_path.relative_to(root)
    except ValueError:
        return None, None, "trusted attester key escapes the code-owned key root"
    key_bytes, key_error = read_regular_file_bytes(key_path)
    if key_error is not None or key_bytes is None:
        return None, None, f"trusted attester key is {key_error}"
    actual_sha256 = hashlib.sha256(key_bytes).hexdigest()
    if actual_sha256 != expected_sha256:
        return None, actual_sha256, "trusted attester key digest does not match its code pin"
    return key_bytes, actual_sha256, None


def openssl_binary_identity() -> tuple[dict[str, Any], str | None]:
    """Capture one no-follow, stable snapshot of the absolute verifier binary."""

    summary: dict[str, Any] = {
        "path": str(OPENSSL_BINARY),
        "load_status": "unavailable",
        "sha256": None,
        "size_bytes": 0,
        "environment_contract": dict(OPENSSL_SUBPROCESS_ENVIRONMENT),
        "inherits_process_environment": False,
    }
    if not OPENSSL_BINARY.is_absolute():
        return summary, "pinned OpenSSL verifier path is not absolute"
    raw, error = read_regular_file_bytes(
        OPENSSL_BINARY,
        max_bytes=MAX_VERIFIER_BINARY_BYTES,
    )
    if error is not None or raw is None:
        summary["load_status"] = error or "unreadable"
        return summary, f"pinned OpenSSL verifier is {error or 'unreadable'}"
    summary.update(
        {
            "load_status": "loaded",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }
    )
    return summary, None


def verify_ed25519_signature(
    public_key_bytes: bytes,
    signed_bytes: bytes,
    signature: bytes,
    *,
    expected_binary_sha256: str | None = None,
) -> tuple[bool, str | None]:
    before, binary_error = openssl_binary_identity()
    if binary_error is not None:
        return False, binary_error
    observed_binary_sha256 = str(before.get("sha256") or "")
    expected_binary_sha256 = expected_binary_sha256 or observed_binary_sha256
    if observed_binary_sha256 != expected_binary_sha256:
        return False, "pinned OpenSSL verifier digest changed before verification"
    if not os.access(OPENSSL_BINARY, os.X_OK):
        return False, "pinned OpenSSL verifier is not executable"
    with tempfile.TemporaryDirectory(prefix="chummer-ed25519-attestation-") as directory:
        directory_path = Path(directory)
        key_path = directory_path / "public-key.pem"
        signature_path = directory_path / "signature.bin"
        payload_path = directory_path / "signed-payload.json"
        key_path.write_bytes(public_key_bytes)
        signature_path.write_bytes(signature)
        payload_path.write_bytes(signed_bytes)
        os.chmod(key_path, 0o600)
        os.chmod(signature_path, 0o600)
        os.chmod(payload_path, 0o600)
        try:
            completed = subprocess.run(
                [
                    str(OPENSSL_BINARY),
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    str(key_path),
                    "-rawin",
                    "-in",
                    str(payload_path),
                    "-sigfile",
                    str(signature_path),
                ],
                env=dict(OPENSSL_SUBPROCESS_ENVIRONMENT),
                capture_output=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"attestation signature verifier failed ({type(exc).__name__})"
    after, binary_error = openssl_binary_identity()
    if binary_error is not None:
        return False, binary_error
    if str(after.get("sha256") or "") != expected_binary_sha256:
        return False, "pinned OpenSSL verifier digest changed during verification"
    return (
        (True, None)
        if completed.returncode == 0
        else (False, "attestation signature is invalid")
    )


def verify_detached_attestation(
    attestation: Mapping[str, Any],
    *,
    contract_name: str,
    role: str,
    exact_claims: Mapping[str, Any],
    trusted_identities: Mapping[str, Mapping[str, str]],
    trusted_key_root: Path,
    now: datetime,
    max_age: timedelta,
    request_generated_at: datetime | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Verify strict claims and signature against a code-owned identity allowlist."""

    now = now.astimezone(UTC)
    allowed_fields = COMMON_FIELDS | set(exact_claims)
    failures: list[str] = []
    unexpected = sorted(set(attestation) - allowed_fields)
    missing = sorted(allowed_fields - set(attestation))
    if unexpected:
        failures.append(
            f"attestation contains {len(unexpected)} unsupported field(s): {', '.join(unexpected)}"
        )
    if missing:
        failures.append(
            f"attestation is missing {len(missing)} required field(s): {', '.join(missing)}"
        )
    if attestation.get("contract_name") != contract_name:
        failures.append(f"contract_name must be {contract_name}")
    if attestation.get("algorithm") != "ed25519":
        failures.append("algorithm must be ed25519")
    if attestation.get("role") != role:
        failures.append(f"role must be {role}")
    for key, expected in exact_claims.items():
        if attestation.get(key) != expected:
            failures.append(f"{key} does not match the required attestation claim")

    generated_at = parse_time(attestation.get("generated_at_utc"))
    if generated_at is None:
        failures.append("generated_at_utc must be a timezone-aware timestamp")
    else:
        if generated_at > now + timedelta(minutes=5):
            failures.append("attestation timestamp is in the future")
        if now - generated_at > max_age:
            failures.append("attestation is stale")
        if (
            request_generated_at is not None
            and generated_at < request_generated_at - timedelta(minutes=5)
        ):
            failures.append("attestation predates its request or execution challenge")

    key_id = str(attestation.get("key_id") or "")
    key_bytes, key_sha256, key_error = read_pinned_public_key(
        key_id,
        role=role,
        trusted_identities=trusted_identities,
        trusted_key_root=trusted_key_root,
    )
    if key_error is not None or key_bytes is None:
        failures.append(key_error or "trusted attester key is unavailable")

    signature_bytes: bytes | None = None
    signature_text = str(attestation.get("signature") or "")
    try:
        signature_bytes = base64.b64decode(
            signature_text,
            validate=True,
        )
    except (binascii.Error, ValueError):
        failures.append("signature must be canonical base64")
    if signature_bytes is not None and len(signature_bytes) != 64:
        failures.append("signature must be a 64-byte Ed25519 signature")
    elif (
        signature_bytes is not None
        and base64.b64encode(signature_bytes).decode("ascii") != signature_text
    ):
        failures.append("signature must be canonical base64")

    signed_payload = {
        key: value for key, value in attestation.items() if key != "signature"
    }
    verifier_identity, verifier_identity_error = openssl_binary_identity()

    if not failures and key_bytes is not None and signature_bytes is not None:
        if verifier_identity_error is not None:
            failures.append(verifier_identity_error)
        else:
            expected_binary_sha256 = str(verifier_identity.get("sha256") or "")
            signature_valid, signature_error = verify_ed25519_signature(
                key_bytes,
                canonical_json_bytes(signed_payload),
                signature_bytes,
                expected_binary_sha256=expected_binary_sha256,
            )
            if not signature_valid:
                failures.append(signature_error or "attestation signature is invalid")

    summary = {
        "contract_name": attestation.get("contract_name"),
        "status": "fail" if failures else "pass",
        "algorithm": attestation.get("algorithm"),
        "role": attestation.get("role"),
        "key_id": key_id or None,
        "public_key_sha256": key_sha256,
        "generated_at_utc": attestation.get("generated_at_utc"),
        "verification_program": verifier_identity,
        **{key: attestation.get(key) for key in exact_claims},
    }
    return summary, failures
