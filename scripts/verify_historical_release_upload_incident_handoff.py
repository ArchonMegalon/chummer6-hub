#!/usr/bin/env python3
"""Independently verify the committed macOS incident-ticket handoff.

This verifier intentionally does not decrypt the CMS envelope.  It validates
the complete six-file, hash-bound transport transaction and every independently
pinned producer authority before the existing Linux materializer performs the
cryptographic decrypt/signature check.  Static bytes prove transaction
completeness, not historical file-creation order.

The independently reviewed launcher/checkout is the root of trust for the
verifier bytes that Python initially executes; a running Python file cannot
self-attest its own pre-execution loader.  After that boundary, this command
proves its reviewed on-disk blob and compiles the seal/transaction helper only
from the separately pinned, held blob in the same reviewed commit.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import resource
import stat
import subprocess
import sys
import types
from typing import Any, Mapping, Sequence


seal: Any = None


CONTRACT_NAME = (
    "chummer.release-upload-incident-ticket-handoff-verification/v2"
)
COMMIT_CONTRACT_NAME = (
    "chummer.release-upload-incident-ticket-handoff-verification-commit/v1"
)
HANDOFF_CONTRACT_NAME = "chummer.release-upload-incident-ticket-handoff/v2"
HANDOFF_CONTEXT_CONTRACT_NAME = (
    "chummer.release-upload-incident-ticket-handoff-publication-context/v1"
)
HANDOFF_COMMIT_CONTRACT_NAME = (
    "chummer.release-upload-incident-ticket-handoff-commit/v1"
)
CONFIRMATION = "VERIFY_HISTORICAL_RELEASE_UPLOAD_INCIDENT_HANDOFF"

CMS_NAME = "CHUMMER_RELEASE_UPLOAD_INCIDENT_TICKET.cms"
SEAL_RECEIPT_NAME = (
    "CHUMMER_RELEASE_UPLOAD_INCIDENT_TICKET_SEAL.receipt.json"
)
SEAL_COMMIT_NAME = (
    "CHUMMER_RELEASE_UPLOAD_INCIDENT_TICKET_SEAL.commit.json"
)
SIGNER_CERT_NAME = (
    "CHUMMER_RELEASE_UPLOAD_INCIDENT_TICKET_SIGNER.cert.pem"
)
HANDOFF_RESPONSE_NAME = (
    "CHUMMER_RELEASE_UPLOAD_INCIDENT_TICKET_HANDOFF.response.json"
)
HANDOFF_COMMIT_NAME = (
    "CHUMMER_RELEASE_UPLOAD_INCIDENT_TICKET_HANDOFF.commit.json"
)
INPUT_NAMES = (
    CMS_NAME,
    SEAL_RECEIPT_NAME,
    SEAL_COMMIT_NAME,
    SIGNER_CERT_NAME,
    HANDOFF_RESPONSE_NAME,
    HANDOFF_COMMIT_NAME,
)
HANDOFF_CONTEXT_INPUT_NAMES = (
    CMS_NAME,
    SEAL_RECEIPT_NAME,
    SEAL_COMMIT_NAME,
    SIGNER_CERT_NAME,
)
HANDOFF_COMMIT_INPUT_NAMES = (
    *HANDOFF_CONTEXT_INPUT_NAMES,
    HANDOFF_RESPONSE_NAME,
)
MAXIMUM_BYTES = {
    CMS_NAME: 16 * 1024 + 256 * 1024,
    SEAL_RECEIPT_NAME: 64 * 1024,
    SEAL_COMMIT_NAME: 64 * 1024,
    SIGNER_CERT_NAME: 256 * 1024,
    HANDOFF_RESPONSE_NAME: 64 * 1024,
    HANDOFF_COMMIT_NAME: 64 * 1024,
}
EXPECTED_CANDIDATE_COUNT = 14
VERIFIER_SOURCE_RELATIVE_PATH = (
    "scripts/verify_historical_release_upload_incident_handoff.py"
)
SEAL_HELPER_RELATIVE_PATH = (
    "scripts/seal_historical_release_upload_incident_ticket.py"
)
PINNED_GIT_PATH = "/usr/bin/git"
MAX_EXECUTABLE_BYTES = 128 * 1024 * 1024
GIT_COMMAND_TIMEOUT_SECONDS = 30
GIT_FSCK_TIMEOUT_SECONDS = 5 * 60
PYTHON_IDENTITY_SOURCE = "proc-self-exe"
SEAL_HELPER_LOAD_MODE = "held-commit-blob"
SHA256_HEX = re.compile(r"\A[0-9a-f]{64}\Z")
GIT_COMMIT = re.compile(r"\A[0-9a-f]{40}\Z")
TRANSACTION_ID = re.compile(r"\A[0-9a-f]{32}\Z")

ARTIFACT_FIELDS = {"sha256", "sizeBytes"}
TRANSACTION_FIELDS = {
    "contractName",
    "status",
    "transactionId",
    "contextSha256",
    "artifacts",
}
SEAL_RECEIPT_FIELDS = {
    "contractName",
    "generatedAtUtc",
    "status",
    "transactionId",
    "contextSha256",
    "candidateCount",
    "distinctIncidentBearerCount",
    "inventoryCommitmentSha256",
    "cmsComposition",
    "digestAlgorithm",
    "contentEncryptionAlgorithm",
    "recipientCertificateSha256",
    "signerCertificateSha256",
    "opensslExecutableSha256",
    "envelopeSha256",
    "envelopeSizeBytes",
    "plaintextPersistedOutsidePrivateSourceCandidates",
    "plaintextEmitted",
    "quarantineStatus",
    "revocationStatus",
    "exactOldTicketRevocationProofRequired",
}
HANDOFF_RESPONSE_FIELDS = {
    "bootstrapSha256",
    "candidateCount",
    "containsSecretValues",
    "contractName",
    "envelopeSha256",
    "envelopeSizeBytes",
    "handoffContextSha256",
    "handoffTransactionId",
    "hubCommit",
    "inventoryCommitmentSha256",
    "opensslPath",
    "opensslSha256",
    "publishersStopped",
    "pythonPath",
    "pythonSha256",
    "recipientCertSha256",
    "sealCommitMarkerSha256",
    "sealCommitMarkerSizeBytes",
    "sealContextSha256",
    "sealReceiptSha256",
    "sealReceiptSizeBytes",
    "sealScriptSha256",
    "sealTransactionId",
    "signerCertSha256",
    "signerCertificatePinAcknowledgementSha256",
    "sourceCandidatesLeftUntouched",
    "status",
    "telegramSignerCertificatePinSent",
}
VERIFICATION_RECEIPT_FIELDS = {
    "contractName",
    "generatedAtUtc",
    "status",
    "transactionId",
    "contextSha256",
    "handoffContextSha256",
    "handoffTransactionId",
    "sealContextSha256",
    "sealTransactionId",
    "candidateCount",
    "inventoryCommitmentSha256",
    "hubCommit",
    "bootstrapSha256",
    "sealScriptSha256",
    "recipientCertificateSha256",
    "signerCertificateSha256",
    "producerOpensslPath",
    "producerOpensslSha256",
    "producerPythonPath",
    "producerPythonSha256",
    "verifierSourceCommit",
    "verifierRepositoryPath",
    "verifierGitPath",
    "verifierGitSha256",
    "verifierScriptPath",
    "verifierScriptSha256",
    "sealHelperPath",
    "sealHelperSha256",
    "verifierScriptGitBlobOid",
    "sealHelperGitBlobOid",
    "verifierPythonIdentitySource",
    "sealHelperLoadMode",
    "verifierPythonPath",
    "verifierPythonSha256",
    "inputArtifacts",
    "transportReadbackPassed",
    "producerReportedSourceCandidatesLeftUntouched",
    "producerReportedPublishersStopped",
    "producerReportedContainsSecretValues",
    "verifierOutputContainsSecretValues",
    "cmsCryptographicVerificationStatus",
}


class VerificationError(RuntimeError):
    """The handoff cannot be trusted for materialization."""


def _disable_core_dumps() -> None:
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (OSError, ValueError) as error:
        raise VerificationError("unable to disable core dumps") from error


def _minimal_environment() -> dict[str, str]:
    return {
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "TMPDIR": "/tmp",
    }


def _identity(item: os.stat_result) -> tuple[int, ...]:
    return (
        item.st_dev,
        item.st_ino,
        item.st_uid,
        item.st_gid,
        item.st_mode,
        item.st_nlink,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )


def _directory_identity(item: os.stat_result) -> tuple[int, ...]:
    return (
        item.st_dev,
        item.st_ino,
        item.st_uid,
        item.st_gid,
        item.st_mode,
    )


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _file_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _directory_metadata_is_safe(metadata: os.stat_result) -> bool:
    mode = stat.S_IMODE(metadata.st_mode)
    writable_by_others = bool(mode & 0o022)
    root_sticky_boundary = (
        metadata.st_uid == 0
        and bool(mode & stat.S_ISVTX)
    )
    return (
        stat.S_ISDIR(metadata.st_mode)
        and metadata.st_uid in {0, os.geteuid()}
        and (not writable_by_others or root_sticky_boundary)
    )


def _read_bounded(
    descriptor: int,
    *,
    maximum_bytes: int,
    label: str,
) -> bytes:
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    except OSError as error:
        raise VerificationError(f"{label} could not be read safely") from error
    content = b"".join(chunks)
    if not content or len(content) > maximum_bytes:
        raise VerificationError(f"{label} has an invalid size")
    return content


@dataclass
class HeldBinary:
    path: Path
    descriptor: int
    metadata: os.stat_result
    content: bytes
    sha256: str

    @property
    def descriptor_path(self) -> str:
        return f"/dev/fd/{self.descriptor}"

    def close(self) -> None:
        os.close(self.descriptor)


def _open_pinned_binary(
    path: Path,
    expected_sha256: str,
    *,
    running_executable: bool = False,
) -> HeldBinary:
    if running_executable:
        descriptor = os.open(
            "/proc/self/exe",
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0),
        )
        display_path = Path(os.readlink("/proc/self/exe")).resolve()
    else:
        if (
            not path.is_absolute()
            or path.name in {"", ".", ".."}
            or any(part in {"", ".", ".."} for part in path.parts[1:])
        ):
            raise VerificationError("pinned executable path is not canonical")
        before = os.stat(path, follow_symlinks=False)
        descriptor = os.open(path, _file_flags())
        display_path = path
    try:
        metadata = os.fstat(descriptor)
        if (
            display_path != path
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.geteuid()}
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or not metadata.st_mode & 0o111
            or not 1 <= metadata.st_size <= MAX_EXECUTABLE_BYTES
            or (
                not running_executable
                and _identity(before) != _identity(metadata)
            )
        ):
            raise VerificationError("pinned executable identity is unsafe")
        content = _read_bounded(
            descriptor,
            maximum_bytes=MAX_EXECUTABLE_BYTES,
            label="pinned executable",
        )
        final = os.fstat(descriptor)
        sha256 = hashlib.sha256(content).hexdigest()
        if (
            _identity(final) != _identity(metadata)
            or not hmac.compare_digest(sha256, expected_sha256)
        ):
            raise VerificationError("pinned executable differs from authority")
        return HeldBinary(
            path=display_path,
            descriptor=descriptor,
            metadata=final,
            content=content,
            sha256=sha256,
        )
    except BaseException:
        os.close(descriptor)
        raise


@dataclass
class HeldInput:
    path: Path
    descriptor: int
    initial: os.stat_result
    content: bytes
    directory_fds: list[int]
    directory_bindings: list[tuple[int, str, int, tuple[int, ...]]]
    root_identity: tuple[int, ...]

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    @property
    def size(self) -> int:
        return len(self.content)

    def artifact(self) -> dict[str, Any]:
        return {"sha256": self.sha256, "sizeBytes": self.size}

    def assert_bound(self) -> None:
        try:
            linked_root = os.stat(os.sep, follow_symlinks=False)
            opened_root = os.fstat(self.directory_fds[0])
            if (
                _directory_identity(linked_root) != self.root_identity
                or _directory_identity(opened_root) != self.root_identity
                or not _directory_metadata_is_safe(linked_root)
                or linked_root.st_uid != 0
            ):
                raise VerificationError("handoff root changed during verification")
            for parent_fd, name, child_fd, expected in self.directory_bindings:
                linked = os.stat(
                    name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
                opened = os.fstat(child_fd)
                if (
                    _directory_identity(linked) != expected
                    or _directory_identity(opened) != expected
                    or not _directory_metadata_is_safe(linked)
                    or not _directory_metadata_is_safe(opened)
                ):
                    raise VerificationError(
                        "handoff directory changed during verification"
                    )
            parent_fd = self.directory_fds[-1]
            linked_file = os.stat(
                self.path.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            opened_file = os.fstat(self.descriptor)
        except OSError as error:
            raise VerificationError(
                "handoff input changed during verification"
            ) from error
        if (
            _identity(linked_file) != _identity(self.initial)
            or _identity(opened_file) != _identity(self.initial)
        ):
            raise VerificationError("handoff input changed during verification")

    def readback(self, *, maximum_bytes: int) -> None:
        before = os.fstat(self.descriptor)
        content = _read_bounded(
            self.descriptor,
            maximum_bytes=maximum_bytes,
            label=self.path.name,
        )
        after = os.fstat(self.descriptor)
        self.assert_bound()
        if (
            _identity(before) != _identity(self.initial)
            or _identity(after) != _identity(self.initial)
            or not hmac.compare_digest(content, self.content)
        ):
            raise VerificationError("handoff input changed during readback")

    def close(self) -> None:
        try:
            os.close(self.descriptor)
        finally:
            for descriptor in reversed(self.directory_fds):
                os.close(descriptor)


def _open_held_input(path: Path, *, maximum_bytes: int) -> HeldInput:
    if (
        not path.is_absolute()
        or path.name in {"", ".", ".."}
        or any(part in {"", ".", ".."} for part in path.parts[1:])
    ):
        raise VerificationError("handoff input path is not canonical")
    directory_fds: list[int] = []
    bindings: list[tuple[int, str, int, tuple[int, ...]]] = []
    descriptor: int | None = None
    try:
        root_fd = os.open(os.sep, _directory_flags())
        directory_fds.append(root_fd)
        root_metadata = os.fstat(root_fd)
        if (
            not _directory_metadata_is_safe(root_metadata)
            or root_metadata.st_uid != 0
        ):
            raise VerificationError("handoff root permissions are unsafe")
        parent_fd = root_fd
        for component in path.parent.parts[1:]:
            linked = os.stat(
                component,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            if not _directory_metadata_is_safe(linked):
                raise VerificationError("handoff directory permissions are unsafe")
            child_fd = os.open(component, _directory_flags(), dir_fd=parent_fd)
            opened = os.fstat(child_fd)
            if _directory_identity(linked) != _directory_identity(opened):
                os.close(child_fd)
                raise VerificationError("handoff directory changed while opening")
            directory_fds.append(child_fd)
            bindings.append(
                (
                    parent_fd,
                    component,
                    child_fd,
                    _directory_identity(opened),
                )
            )
            parent_fd = child_fd
        linked_file = os.stat(
            path.name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        descriptor = os.open(path.name, _file_flags(), dir_fd=parent_fd)
        opened_file = os.fstat(descriptor)
        if _identity(linked_file) != _identity(opened_file):
            raise VerificationError("handoff input changed while opening")
        if (
            not stat.S_ISREG(opened_file.st_mode)
            or opened_file.st_nlink != 1
            or opened_file.st_uid != os.geteuid()
            or stat.S_IMODE(opened_file.st_mode) & 0o022
            or not 1 <= opened_file.st_size <= maximum_bytes
        ):
            raise VerificationError("handoff input permissions are unsafe")
        content = _read_bounded(
            descriptor,
            maximum_bytes=maximum_bytes,
            label=path.name,
        )
        after = os.fstat(descriptor)
        if _identity(after) != _identity(opened_file):
            raise VerificationError("handoff input changed during stable read")
        held = HeldInput(
            path=path,
            descriptor=descriptor,
            initial=after,
            content=content,
            directory_fds=directory_fds,
            directory_bindings=bindings,
            root_identity=_directory_identity(root_metadata),
        )
        held.assert_bound()
        descriptor = None
        return held
    except OSError as error:
        raise VerificationError("handoff input could not be opened safely") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if descriptor is not None or sys.exc_info()[0] is not None:
            for directory_fd in reversed(directory_fds):
                try:
                    os.close(directory_fd)
                except OSError:
                    pass


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value).rstrip(b"\n")).hexdigest()


def _strict_json(raw: bytes, *, label: str) -> dict[str, Any]:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        folded: set[str] = set()
        for key, value in pairs:
            if not isinstance(key, str) or key.casefold() in folded:
                raise VerificationError(f"{label} contains duplicate fields")
            folded.add(key.casefold())
            result[key] = value
        return result

    def reject_constant(_value: str) -> None:
        raise VerificationError(f"{label} contains a non-finite number")

    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=object_pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"{label} is malformed") from error
    if (
        not isinstance(parsed, dict)
        or _canonical_json_bytes(parsed) != raw
    ):
        raise VerificationError(f"{label} is not exact canonical JSON")
    return parsed


def _sha256(value: Any, *, label: str) -> str:
    if type(value) is not str or SHA256_HEX.fullmatch(value) is None:
        raise VerificationError(f"{label} is not canonical SHA-256")
    return value


def _transaction_id(value: Any, *, label: str) -> str:
    if type(value) is not str or TRANSACTION_ID.fullmatch(value) is None:
        raise VerificationError(f"{label} is not a canonical transaction id")
    return value


def _exact_absolute_path(value: Any, *, expected: str, label: str) -> None:
    if (
        type(value) is not str
        or value != expected
        or not Path(value).is_absolute()
        or str(Path(value)) != value
        or any(
            part in {"", ".", ".."}
            for part in Path(value).parts[1:]
        )
    ):
        raise VerificationError(f"{label} differs from independent authority")


def _timestamp(value: Any, *, now: dt.datetime | None = None) -> None:
    if (
        type(value) is not str
        or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
            r"[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
            value,
        )
        is None
    ):
        raise VerificationError("seal receipt timestamp is not canonical")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise VerificationError("seal receipt timestamp is invalid") from error
    reference = now or dt.datetime.now(dt.timezone.utc)
    if parsed.tzinfo != dt.timezone.utc or parsed > reference + dt.timedelta(minutes=5):
        raise VerificationError("seal receipt timestamp is in the future")


def _artifact_record(
    value: Any,
    *,
    expected: Mapping[str, Any],
    label: str,
) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != ARTIFACT_FIELDS
        or type(value.get("sha256")) is not str
        or SHA256_HEX.fullmatch(value["sha256"]) is None
        or type(value.get("sizeBytes")) is not int
        or value["sizeBytes"] < 1
        or value != expected
    ):
        raise VerificationError(f"{label} artifact binding is invalid")


def _validate_transaction(
    payload: Mapping[str, Any],
    *,
    contract_name: str,
    transaction_id: str,
    context_sha256: str,
    expected_artifacts: Mapping[str, Mapping[str, Any]],
    label: str,
) -> None:
    if (
        set(payload) != TRANSACTION_FIELDS
        or payload.get("contractName") != contract_name
        or payload.get("status") != "committed"
        or payload.get("transactionId") != transaction_id
        or payload.get("contextSha256") != context_sha256
        or not isinstance(payload.get("artifacts"), dict)
        or set(payload["artifacts"]) != set(expected_artifacts)
    ):
        raise VerificationError(f"{label} transaction binding is invalid")
    for name, expected in expected_artifacts.items():
        _artifact_record(
            payload["artifacts"].get(name),
            expected=expected,
            label=f"{label} {name}",
        )


@dataclass(frozen=True)
class IndependentAuthority:
    hub_commit: str
    bootstrap_sha256: str
    seal_script_sha256: str
    seal_context_sha256: str
    inventory_commitment_sha256: str
    recipient_certificate_sha256: str
    signer_certificate_sha256: str
    openssl_path: str
    openssl_sha256: str
    python_path: str
    python_sha256: str
    verifier_source_commit: str
    verifier_repository_path: str
    verifier_git_path: str
    verifier_git_sha256: str
    verifier_script_path: str
    verifier_script_sha256: str
    seal_helper_path: str
    seal_helper_sha256: str
    verifier_script_git_blob_oid: str
    seal_helper_git_blob_oid: str
    verifier_python_identity_source: str
    seal_helper_load_mode: str
    verifier_python_path: str
    verifier_python_sha256: str


@dataclass(frozen=True)
class ValidatedHandoff:
    seal_receipt: Mapping[str, Any]
    response: Mapping[str, Any]
    artifacts: Mapping[str, Mapping[str, Any]]


def _validate_handoff(
    inputs: Mapping[str, HeldInput],
    authority: IndependentAuthority,
) -> ValidatedHandoff:
    seal_receipt = _strict_json(
        inputs[SEAL_RECEIPT_NAME].content,
        label="seal receipt",
    )
    seal_commit = _strict_json(
        inputs[SEAL_COMMIT_NAME].content,
        label="seal commit",
    )
    response = _strict_json(
        inputs[HANDOFF_RESPONSE_NAME].content,
        label="handoff response",
    )
    handoff_commit = _strict_json(
        inputs[HANDOFF_COMMIT_NAME].content,
        label="handoff commit",
    )
    artifacts = {name: inputs[name].artifact() for name in INPUT_NAMES}

    if set(seal_receipt) != SEAL_RECEIPT_FIELDS:
        raise VerificationError("seal receipt fields are not exact")
    _timestamp(seal_receipt.get("generatedAtUtc"))
    seal_context = _sha256(
        seal_receipt.get("contextSha256"),
        label="seal context",
    )
    seal_transaction = _transaction_id(
        seal_receipt.get("transactionId"),
        label="seal transaction",
    )
    sha_fields = (
        "inventoryCommitmentSha256",
        "recipientCertificateSha256",
        "signerCertificateSha256",
        "opensslExecutableSha256",
        "envelopeSha256",
    )
    for field in sha_fields:
        _sha256(seal_receipt.get(field), label=f"seal receipt {field}")
    if (
        seal_receipt.get("contractName") != seal.CONTRACT_NAME
        or seal_receipt.get("status")
        != "sealed_pending_quarantine_and_revocation"
        or seal_transaction != seal_context[:32]
        or seal_context != authority.seal_context_sha256
        or seal_receipt.get("candidateCount") != EXPECTED_CANDIDATE_COUNT
        or type(seal_receipt.get("candidateCount")) is not int
        or seal_receipt.get("distinctIncidentBearerCount") != 1
        or type(seal_receipt.get("distinctIncidentBearerCount")) is not int
        or seal_receipt.get("inventoryCommitmentSha256")
        != authority.inventory_commitment_sha256
        or seal_receipt.get("cmsComposition")
        != "authenticated-signedData-inside-envelopedData"
        or seal_receipt.get("digestAlgorithm") != "sha256"
        or seal_receipt.get("contentEncryptionAlgorithm") != seal.CMS_CIPHER
        or seal_receipt.get("recipientCertificateSha256")
        != authority.recipient_certificate_sha256
        or seal_receipt.get("signerCertificateSha256")
        != authority.signer_certificate_sha256
        or seal_receipt.get("opensslExecutableSha256")
        != authority.openssl_sha256
        or seal_receipt.get("envelopeSha256")
        != artifacts[CMS_NAME]["sha256"]
        or seal_receipt.get("envelopeSizeBytes")
        != artifacts[CMS_NAME]["sizeBytes"]
        or type(seal_receipt.get("envelopeSizeBytes")) is not int
        or seal_receipt.get("plaintextPersistedOutsidePrivateSourceCandidates")
        is not False
        or seal_receipt.get("plaintextEmitted") is not False
        or seal_receipt.get("quarantineStatus") != "pending"
        or seal_receipt.get("revocationStatus") != "pending"
        or seal_receipt.get("exactOldTicketRevocationProofRequired") is not True
    ):
        raise VerificationError("seal receipt authority binding is invalid")

    _validate_transaction(
        seal_commit,
        contract_name=seal.COMMIT_CONTRACT_NAME,
        transaction_id=seal_transaction,
        context_sha256=seal_context,
        expected_artifacts={
            CMS_NAME: artifacts[CMS_NAME],
            SEAL_RECEIPT_NAME: artifacts[SEAL_RECEIPT_NAME],
        },
        label="seal commit",
    )

    if set(response) != HANDOFF_RESPONSE_FIELDS:
        raise VerificationError("handoff response fields are not exact")
    for field in (
        "bootstrapSha256",
        "envelopeSha256",
        "handoffContextSha256",
        "inventoryCommitmentSha256",
        "opensslSha256",
        "pythonSha256",
        "recipientCertSha256",
        "sealCommitMarkerSha256",
        "sealContextSha256",
        "sealReceiptSha256",
        "sealScriptSha256",
        "signerCertSha256",
        "signerCertificatePinAcknowledgementSha256",
    ):
        _sha256(response.get(field), label=f"handoff response {field}")
    handoff_transaction = _transaction_id(
        response.get("handoffTransactionId"),
        label="handoff transaction",
    )
    _transaction_id(
        response.get("sealTransactionId"),
        label="handoff seal transaction",
    )
    _exact_absolute_path(
        response.get("opensslPath"),
        expected=authority.openssl_path,
        label="producer OpenSSL path",
    )
    _exact_absolute_path(
        response.get("pythonPath"),
        expected=authority.python_path,
        label="producer Python path",
    )
    acknowledgement = hashlib.sha256(
        (
            "CHUMMER_TICKET_SIGNER_CERT_SHA256="
            f"{authority.signer_certificate_sha256}\n"
        ).encode("ascii")
    ).hexdigest()
    if (
        response.get("contractName") != HANDOFF_CONTRACT_NAME
        or response.get("status") != "sealed_pending_linux_materialization"
        or response.get("candidateCount") != EXPECTED_CANDIDATE_COUNT
        or type(response.get("candidateCount")) is not int
        or response.get("containsSecretValues") is not False
        or response.get("publishersStopped") is not True
        or response.get("sourceCandidatesLeftUntouched") is not True
        or response.get("telegramSignerCertificatePinSent") is not True
        or response.get("hubCommit") != authority.hub_commit
        or response.get("bootstrapSha256") != authority.bootstrap_sha256
        or response.get("sealScriptSha256") != authority.seal_script_sha256
        or response.get("sealContextSha256") != seal_context
        or response.get("sealTransactionId") != seal_transaction
        or response.get("inventoryCommitmentSha256")
        != authority.inventory_commitment_sha256
        or response.get("recipientCertSha256")
        != authority.recipient_certificate_sha256
        or response.get("signerCertSha256")
        != authority.signer_certificate_sha256
        or response.get("opensslSha256") != authority.openssl_sha256
        or response.get("pythonSha256") != authority.python_sha256
        or response.get("envelopeSha256") != artifacts[CMS_NAME]["sha256"]
        or response.get("envelopeSizeBytes") != artifacts[CMS_NAME]["sizeBytes"]
        or type(response.get("envelopeSizeBytes")) is not int
        or response.get("sealReceiptSha256")
        != artifacts[SEAL_RECEIPT_NAME]["sha256"]
        or response.get("sealReceiptSizeBytes")
        != artifacts[SEAL_RECEIPT_NAME]["sizeBytes"]
        or type(response.get("sealReceiptSizeBytes")) is not int
        or response.get("sealCommitMarkerSha256")
        != artifacts[SEAL_COMMIT_NAME]["sha256"]
        or response.get("sealCommitMarkerSizeBytes")
        != artifacts[SEAL_COMMIT_NAME]["sizeBytes"]
        or type(response.get("sealCommitMarkerSizeBytes")) is not int
        or response.get("signerCertificatePinAcknowledgementSha256")
        != acknowledgement
        or artifacts[SIGNER_CERT_NAME]["sha256"]
        != authority.signer_certificate_sha256
    ):
        raise VerificationError("handoff response authority binding is invalid")

    certificate = inputs[SIGNER_CERT_NAME].content
    if (
        certificate.count(b"-----BEGIN CERTIFICATE-----") != 1
        or certificate.count(b"-----END CERTIFICATE-----") != 1
        or b"PRIVATE KEY" in certificate
    ):
        raise VerificationError("signer certificate transport is invalid")

    handoff_context = _canonical_json_sha256(
        {
            "contractName": HANDOFF_CONTEXT_CONTRACT_NAME,
            "hubCommit": authority.hub_commit,
            "sealContextSha256": seal_context,
            "sealTransactionId": seal_transaction,
            "artifacts": {
                name: artifacts[name]
                for name in HANDOFF_CONTEXT_INPUT_NAMES
            },
        }
    )
    if (
        response.get("handoffContextSha256") != handoff_context
        or handoff_transaction != handoff_context[:32]
    ):
        raise VerificationError("handoff publication context is invalid")

    _validate_transaction(
        handoff_commit,
        contract_name=HANDOFF_COMMIT_CONTRACT_NAME,
        transaction_id=handoff_transaction,
        context_sha256=handoff_context,
        expected_artifacts={
            name: artifacts[name]
            for name in HANDOFF_COMMIT_INPUT_NAMES
        },
        label="handoff commit",
    )
    return ValidatedHandoff(
        seal_receipt=seal_receipt,
        response=response,
        artifacts=artifacts,
    )


def _runtime_source_paths() -> tuple[Path, Path]:
    verifier_path = Path(__file__).resolve()
    return verifier_path, verifier_path.with_name(
        Path(SEAL_HELPER_RELATIVE_PATH).name
    )


def _execute_pinned_git(
    executable: HeldBinary,
    repository_descriptor: int,
    arguments: Sequence[str],
    *,
    maximum_output_bytes: int = 2 * 1024 * 1024,
    timeout_seconds: int = GIT_COMMAND_TIMEOUT_SECONDS,
) -> bytes:
    maximum_timeout = (
        GIT_FSCK_TIMEOUT_SECONDS
        if arguments and arguments[0] == "fsck"
        else GIT_COMMAND_TIMEOUT_SECONDS
    )
    if (
        type(timeout_seconds) is not int
        or not 1 <= timeout_seconds <= maximum_timeout
    ):
        raise VerificationError("pinned Git timeout is invalid")
    executable_path = executable.descriptor_path
    repository_path = f"/proc/self/fd/{repository_descriptor}"
    environment = _minimal_environment()
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
        }
    )
    try:
        completed = subprocess.run(
            (
                executable_path,
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "diff.external=",
                "-c",
                "filter.lfs.process=",
                "-c",
                "filter.lfs.smudge=",
                "-c",
                "filter.lfs.clean=",
                "-C",
                repository_path,
                *arguments,
            ),
            executable=executable_path,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            pass_fds=(executable.descriptor, repository_descriptor),
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise VerificationError("pinned Git operation failed") from error
    if (
        completed.returncode != 0
        or len(completed.stdout) > maximum_output_bytes
    ):
        raise VerificationError("pinned Git operation failed")
    return completed.stdout


def _read_committed_source_blob(
    *,
    executable: HeldBinary,
    repository_descriptor: int,
    commit: str,
    relative_path: str,
    maximum_bytes: int,
) -> tuple[bytes, str]:
    tree_entry = _execute_pinned_git(
        executable,
        repository_descriptor,
        (
            "ls-tree",
            "-z",
            "--full-tree",
            commit,
            "--",
            relative_path,
        ),
        maximum_output_bytes=512,
    )
    expected_suffix = f"\t{relative_path}\0".encode("utf-8")
    if (
        tree_entry.count(b"\0") != 1
        or not tree_entry.endswith(expected_suffix)
    ):
        raise VerificationError("reviewed source tree entry is invalid")
    metadata = tree_entry[: -len(expected_suffix)]
    parts = metadata.split(b" ")
    if (
        len(parts) != 3
        or parts[0] not in {b"100644", b"100755"}
        or parts[1] != b"blob"
    ):
        raise VerificationError("reviewed source tree mode is invalid")
    object_id = parts[2].decode("ascii", errors="strict")
    if GIT_COMMIT.fullmatch(object_id) is None:
        raise VerificationError("reviewed source blob identity is invalid")
    object_type = _execute_pinned_git(
        executable,
        repository_descriptor,
        ("cat-file", "-t", object_id),
        maximum_output_bytes=64,
    )
    if object_type != b"blob\n":
        raise VerificationError("reviewed source object is not a blob")
    size_text = _execute_pinned_git(
        executable,
        repository_descriptor,
        ("cat-file", "-s", object_id),
        maximum_output_bytes=64,
    ).decode("ascii", errors="strict").strip()
    if (
        not size_text.isascii()
        or not size_text.isdigit()
        or not 1 <= int(size_text) <= maximum_bytes
    ):
        raise VerificationError("reviewed source blob size is invalid")
    content = _execute_pinned_git(
        executable,
        repository_descriptor,
        ("cat-file", "blob", object_id),
        maximum_output_bytes=maximum_bytes,
    )
    if len(content) != int(size_text):
        raise VerificationError("reviewed source blob size changed")
    git_object = f"blob {len(content)}\0".encode("ascii") + content
    observed_object_id = hashlib.sha1(
        git_object,
        usedforsecurity=False,
    ).hexdigest()
    if not hmac.compare_digest(observed_object_id, object_id):
        raise VerificationError("reviewed source blob identity is invalid")
    return content, object_id


@dataclass(frozen=True)
class SourceProvenance:
    verifier_blob_oid: str
    helper_blob_oid: str
    helper_module: types.ModuleType


def _load_held_helper(
    *,
    content: bytes,
    source_path: Path,
    sha256: str,
) -> types.ModuleType:
    module_name = f"_chummer_attested_ticket_seal_{sha256[:16]}"
    module = types.ModuleType(module_name)
    module.__file__ = str(source_path)
    module.__package__ = ""
    module.__loader__ = None
    sys.modules.pop(module_name, None)
    sys.modules[module_name] = module
    try:
        code = compile(
            content,
            str(source_path),
            "exec",
            dont_inherit=True,
            optimize=0,
        )
        exec(code, module.__dict__)
    except BaseException as error:
        sys.modules.pop(module_name, None)
        raise VerificationError("reviewed seal helper could not be loaded") from error
    required = (
        "CONTRACT_NAME",
        "COMMIT_CONTRACT_NAME",
        "CMS_CIPHER",
        "MAX_CMS_BYTES",
        "MAX_TRANSACTION_FILE_BYTES",
        "_canonical_json_bytes",
        "_ensure_same_private_parent",
        "_publish_transaction",
        "_recover_fully_linked_transaction",
    )
    if any(not hasattr(module, name) for name in required):
        sys.modules.pop(module_name, None)
        raise VerificationError("reviewed seal helper contract is incomplete")
    return module


def _verify_source_provenance(
    *,
    repository_path: Path,
    source_commit: str,
    git_path: Path,
    git_sha256: str,
    verifier_script_path: Path,
    verifier_script_sha256: str,
    seal_helper_path: Path,
    seal_helper_sha256: str,
) -> SourceProvenance:
    runtime_verifier, runtime_helper = _runtime_source_paths()
    if (
        runtime_verifier != verifier_script_path
        or runtime_helper != seal_helper_path
        or verifier_script_path
        != repository_path / VERIFIER_SOURCE_RELATIVE_PATH
        or seal_helper_path != repository_path / SEAL_HELPER_RELATIVE_PATH
        or str(git_path) != PINNED_GIT_PATH
    ):
        raise VerificationError("local verifier source layout differs from authority")
    verifier_input: HeldInput | None = None
    helper_input: HeldInput | None = None
    git_executable: HeldBinary | None = None
    repository_descriptor: int | None = None
    try:
        verifier_input = _open_held_input(
            verifier_script_path,
            maximum_bytes=2 * 1024 * 1024,
        )
        helper_input = _open_held_input(
            seal_helper_path,
            maximum_bytes=2 * 1024 * 1024,
        )
        if (
            verifier_input.sha256 != verifier_script_sha256
            or helper_input.sha256 != seal_helper_sha256
        ):
            raise VerificationError("local verifier source pin mismatch")
        git_executable = _open_pinned_binary(
            git_path,
            git_sha256,
        )
        before = os.stat(repository_path, follow_symlinks=False)
        repository_descriptor = os.open(
            repository_path,
            _directory_flags(),
        )
        opened = os.fstat(repository_descriptor)
        if (
            _directory_identity(before) != _directory_identity(opened)
            or not _directory_metadata_is_safe(opened)
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) & 0o022
        ):
            raise VerificationError("verifier source repository is unsafe")
        if (
            _execute_pinned_git(
                git_executable,
                repository_descriptor,
                ("rev-parse", "--show-object-format"),
                maximum_output_bytes=64,
            )
            != b"sha1\n"
        ):
            raise VerificationError("verifier source repository format is invalid")
        if (
            _execute_pinned_git(
                git_executable,
                repository_descriptor,
                ("cat-file", "-t", source_commit),
                maximum_output_bytes=64,
            )
            != b"commit\n"
        ):
            raise VerificationError("verifier source commit is invalid")
        commit_content = _execute_pinned_git(
            git_executable,
            repository_descriptor,
            ("cat-file", "commit", source_commit),
            maximum_output_bytes=2 * 1024 * 1024,
        )
        observed_commit = hashlib.sha1(
            (
                f"commit {len(commit_content)}\0".encode("ascii")
                + commit_content
            ),
            usedforsecurity=False,
        ).hexdigest()
        if not hmac.compare_digest(observed_commit, source_commit):
            raise VerificationError("verifier source commit identity is invalid")
        _execute_pinned_git(
            git_executable,
            repository_descriptor,
            (
                "fsck",
                "--strict",
                "--no-dangling",
                "--no-reflogs",
                "--no-progress",
                source_commit,
            ),
            maximum_output_bytes=64 * 1024,
            timeout_seconds=GIT_FSCK_TIMEOUT_SECONDS,
        )
        committed_verifier, verifier_blob_oid = _read_committed_source_blob(
            executable=git_executable,
            repository_descriptor=repository_descriptor,
            commit=source_commit,
            relative_path=VERIFIER_SOURCE_RELATIVE_PATH,
            maximum_bytes=2 * 1024 * 1024,
        )
        committed_helper, helper_blob_oid = _read_committed_source_blob(
            executable=git_executable,
            repository_descriptor=repository_descriptor,
            commit=source_commit,
            relative_path=SEAL_HELPER_RELATIVE_PATH,
            maximum_bytes=2 * 1024 * 1024,
        )
        if (
            not hmac.compare_digest(
                committed_verifier,
                verifier_input.content,
            )
            or not hmac.compare_digest(
                committed_helper,
                helper_input.content,
            )
        ):
            raise VerificationError(
                "local verifier source differs from reviewed commit"
            )
        verifier_input.readback(maximum_bytes=2 * 1024 * 1024)
        helper_input.readback(maximum_bytes=2 * 1024 * 1024)
        current_repository = os.stat(
            repository_path,
            follow_symlinks=False,
        )
        if (
            _directory_identity(current_repository)
            != _directory_identity(opened)
            or _directory_identity(os.fstat(repository_descriptor))
            != _directory_identity(opened)
        ):
            raise VerificationError(
                "verifier source repository changed during verification"
            )
        helper_module = _load_held_helper(
            content=helper_input.content,
            source_path=seal_helper_path,
            sha256=seal_helper_sha256,
        )
        return SourceProvenance(
            verifier_blob_oid=verifier_blob_oid,
            helper_blob_oid=helper_blob_oid,
            helper_module=helper_module,
        )
    except UnicodeError as error:
        raise VerificationError("pinned Git output is not canonical ASCII") from error
    finally:
        if repository_descriptor is not None:
            os.close(repository_descriptor)
        if git_executable is not None:
            git_executable.close()
        if helper_input is not None:
            helper_input.close()
        if verifier_input is not None:
            verifier_input.close()


def _authority(options: argparse.Namespace) -> IndependentAuthority:
    global seal
    if (
        type(options.expected_hub_commit) is not str
        or GIT_COMMIT.fullmatch(options.expected_hub_commit) is None
    ):
        raise VerificationError("expected Hub commit is not canonical")
    for field in (
        "expected_bootstrap_sha256",
        "expected_seal_script_sha256",
        "expected_seal_context_sha256",
        "expected_inventory_commitment_sha256",
        "expected_recipient_cert_sha256",
        "expected_signer_cert_sha256",
        "expected_openssl_sha256",
        "expected_python_sha256",
        "expected_verifier_git_sha256",
        "expected_verifier_script_sha256",
        "expected_seal_helper_sha256",
        "expected_verifier_python_sha256",
    ):
        _sha256(getattr(options, field), label=field.replace("_", " "))
    for field in (
        "expected_openssl_path",
        "expected_python_path",
        "expected_verifier_repository_path",
        "expected_verifier_git_path",
        "expected_verifier_script_path",
        "expected_seal_helper_path",
        "expected_verifier_python_path",
    ):
        value = getattr(options, field)
        _exact_absolute_path(
            value,
            expected=value,
            label=field.replace("_", " "),
        )
    if (
        type(options.expected_verifier_source_commit) is not str
        or GIT_COMMIT.fullmatch(options.expected_verifier_source_commit)
        is None
    ):
        raise VerificationError("expected verifier source commit is not canonical")
    verifier_python = Path(os.readlink("/proc/self/exe")).resolve()
    if (
        verifier_python != Path(sys.executable).resolve()
        or str(verifier_python) != options.expected_verifier_python_path
    ):
        raise VerificationError("local verifier Python differs from authority")
    provenance: SourceProvenance | None = None
    python_pin: HeldBinary | None = None
    try:
        provenance = _verify_source_provenance(
            repository_path=Path(options.expected_verifier_repository_path),
            source_commit=options.expected_verifier_source_commit,
            git_path=Path(options.expected_verifier_git_path),
            git_sha256=options.expected_verifier_git_sha256,
            verifier_script_path=Path(
                options.expected_verifier_script_path
            ),
            verifier_script_sha256=(
                options.expected_verifier_script_sha256
            ),
            seal_helper_path=Path(options.expected_seal_helper_path),
            seal_helper_sha256=options.expected_seal_helper_sha256,
        )
        seal = provenance.helper_module
        python_pin = _open_pinned_binary(
            verifier_python,
            options.expected_verifier_python_sha256,
            running_executable=True,
        )
    finally:
        if python_pin is not None:
            python_pin.close()
    if provenance is None:
        raise VerificationError("verifier source provenance was not established")
    return IndependentAuthority(
        hub_commit=options.expected_hub_commit,
        bootstrap_sha256=options.expected_bootstrap_sha256,
        seal_script_sha256=options.expected_seal_script_sha256,
        seal_context_sha256=options.expected_seal_context_sha256,
        inventory_commitment_sha256=(
            options.expected_inventory_commitment_sha256
        ),
        recipient_certificate_sha256=options.expected_recipient_cert_sha256,
        signer_certificate_sha256=options.expected_signer_cert_sha256,
        openssl_path=options.expected_openssl_path,
        openssl_sha256=options.expected_openssl_sha256,
        python_path=options.expected_python_path,
        python_sha256=options.expected_python_sha256,
        verifier_source_commit=options.expected_verifier_source_commit,
        verifier_repository_path=(
            options.expected_verifier_repository_path
        ),
        verifier_git_path=options.expected_verifier_git_path,
        verifier_git_sha256=options.expected_verifier_git_sha256,
        verifier_script_path=options.expected_verifier_script_path,
        verifier_script_sha256=options.expected_verifier_script_sha256,
        seal_helper_path=options.expected_seal_helper_path,
        seal_helper_sha256=options.expected_seal_helper_sha256,
        verifier_script_git_blob_oid=provenance.verifier_blob_oid,
        seal_helper_git_blob_oid=provenance.helper_blob_oid,
        verifier_python_identity_source=PYTHON_IDENTITY_SOURCE,
        seal_helper_load_mode=SEAL_HELPER_LOAD_MODE,
        verifier_python_path=options.expected_verifier_python_path,
        verifier_python_sha256=options.expected_verifier_python_sha256,
    )


def _verification_context(
    *,
    output: Path,
    commit_marker: Path,
    authority: IndependentAuthority,
    handoff_context_sha256: str,
) -> str:
    return _canonical_json_sha256(
        {
            "contractName": CONTRACT_NAME,
            "outputPathSha256": hashlib.sha256(
                str(output).encode("utf-8")
            ).hexdigest(),
            "commitMarkerPathSha256": hashlib.sha256(
                str(commit_marker).encode("utf-8")
            ).hexdigest(),
            "handoffContextSha256": handoff_context_sha256,
            "hubCommit": authority.hub_commit,
            "bootstrapSha256": authority.bootstrap_sha256,
            "sealScriptSha256": authority.seal_script_sha256,
            "sealContextSha256": authority.seal_context_sha256,
            "inventoryCommitmentSha256": (
                authority.inventory_commitment_sha256
            ),
            "recipientCertificateSha256": (
                authority.recipient_certificate_sha256
            ),
            "signerCertificateSha256": (
                authority.signer_certificate_sha256
            ),
            "producerOpensslPath": authority.openssl_path,
            "producerOpensslSha256": authority.openssl_sha256,
            "producerPythonPath": authority.python_path,
            "producerPythonSha256": authority.python_sha256,
            "verifierSourceCommit": authority.verifier_source_commit,
            "verifierRepositoryPath": authority.verifier_repository_path,
            "verifierGitPath": authority.verifier_git_path,
            "verifierGitSha256": authority.verifier_git_sha256,
            "verifierScriptPath": authority.verifier_script_path,
            "verifierScriptSha256": authority.verifier_script_sha256,
            "sealHelperPath": authority.seal_helper_path,
            "sealHelperSha256": authority.seal_helper_sha256,
            "verifierScriptGitBlobOid": (
                authority.verifier_script_git_blob_oid
            ),
            "sealHelperGitBlobOid": authority.seal_helper_git_blob_oid,
            "verifierPythonIdentitySource": (
                authority.verifier_python_identity_source
            ),
            "sealHelperLoadMode": authority.seal_helper_load_mode,
            "verifierPythonPath": authority.verifier_python_path,
            "verifierPythonSha256": authority.verifier_python_sha256,
        }
    )


def _validate_existing_receipt(
    receipt: Mapping[str, Any],
    *,
    expected: Mapping[str, Any],
) -> None:
    if (
        set(receipt) != VERIFICATION_RECEIPT_FIELDS
        or any(
            receipt.get(field) != value
            for field, value in expected.items()
            if field != "generatedAtUtc"
        )
    ):
        raise VerificationError("existing verification receipt is invalid")
    _timestamp(receipt.get("generatedAtUtc"))


def _load_existing_verification(
    *,
    output: Path,
    commit_marker: Path,
    transaction_id: str,
    context_sha256: str,
) -> dict[str, Any] | None:
    _parent, parent_fd = seal._ensure_same_private_parent(
        (output, commit_marker)
    )
    try:
        existence: list[bool] = []
        for path in (output, commit_marker):
            try:
                os.stat(
                    path.name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
                existence.append(True)
            except FileNotFoundError:
                existence.append(False)
        if not any(existence):
            return None
        if not all(existence):
            raise VerificationError(
                "verification transaction is only partially published"
            )
        receipt_bytes, _receipt_metadata = seal._read_private_file_at(
            parent_fd,
            output.name,
            maximum_bytes=seal.MAX_TRANSACTION_FILE_BYTES,
        )
        marker_bytes, _marker_metadata = seal._read_private_file_at(
            parent_fd,
            commit_marker.name,
            maximum_bytes=seal.MAX_TRANSACTION_FILE_BYTES,
        )
    finally:
        os.close(parent_fd)
    receipt = _strict_json(
        receipt_bytes,
        label="existing verification receipt",
    )
    marker = _strict_json(
        marker_bytes,
        label="existing verification commit",
    )
    _validate_transaction(
        marker,
        contract_name=COMMIT_CONTRACT_NAME,
        transaction_id=transaction_id,
        context_sha256=context_sha256,
        expected_artifacts={output.name: artifact_record(receipt_bytes)},
        label="existing verification commit",
    )
    return receipt


def artifact_record(content: bytes) -> dict[str, Any]:
    return {
        "sha256": hashlib.sha256(content).hexdigest(),
        "sizeBytes": len(content),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-directory", type=Path, required=True)
    parser.add_argument("--expected-hub-commit", required=True)
    parser.add_argument("--expected-bootstrap-sha256", required=True)
    parser.add_argument("--expected-seal-script-sha256", required=True)
    parser.add_argument("--expected-seal-context-sha256", required=True)
    parser.add_argument(
        "--expected-inventory-commitment-sha256",
        required=True,
    )
    parser.add_argument("--expected-recipient-cert-sha256", required=True)
    parser.add_argument("--expected-signer-cert-sha256", required=True)
    parser.add_argument("--expected-openssl-path", required=True)
    parser.add_argument("--expected-openssl-sha256", required=True)
    parser.add_argument("--expected-python-path", required=True)
    parser.add_argument("--expected-python-sha256", required=True)
    parser.add_argument("--expected-verifier-source-commit", required=True)
    parser.add_argument("--expected-verifier-repository-path", required=True)
    parser.add_argument("--expected-verifier-git-path", required=True)
    parser.add_argument("--expected-verifier-git-sha256", required=True)
    parser.add_argument("--expected-verifier-script-path", required=True)
    parser.add_argument("--expected-verifier-script-sha256", required=True)
    parser.add_argument("--expected-seal-helper-path", required=True)
    parser.add_argument("--expected-seal-helper-sha256", required=True)
    parser.add_argument("--expected-verifier-python-path", required=True)
    parser.add_argument("--expected-verifier-python-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit-marker", type=Path, required=True)
    parser.add_argument("--confirm", required=True)
    return parser


def verify(options: argparse.Namespace) -> Mapping[str, Any]:
    _disable_core_dumps()
    if not sys.platform.startswith("linux"):
        raise VerificationError("handoff verification is Linux-only")
    if options.confirm != CONFIRMATION:
        raise VerificationError(f"--confirm requires {CONFIRMATION}")
    authority = _authority(options)
    if (
        not options.handoff_directory.is_absolute()
        or options.output.name in {"", ".", ".."}
        or options.commit_marker.name in {"", ".", ".."}
        or options.output.parent != options.commit_marker.parent
        or not options.output.is_absolute()
        or not options.commit_marker.is_absolute()
    ):
        raise VerificationError("verification paths are not canonical")
    held: dict[str, HeldInput] = {}
    try:
        for name in INPUT_NAMES:
            held[name] = _open_held_input(
                options.handoff_directory / name,
                maximum_bytes=MAXIMUM_BYTES[name],
            )
        validated = _validate_handoff(held, authority)
        for name, item in held.items():
            item.readback(maximum_bytes=MAXIMUM_BYTES[name])

        response = validated.response
        handoff_context = response["handoffContextSha256"]
        context_sha256 = _verification_context(
            output=options.output,
            commit_marker=options.commit_marker,
            authority=authority,
            handoff_context_sha256=handoff_context,
        )
        transaction_id = context_sha256[:32]
        receipt: dict[str, Any] = {
            "contractName": CONTRACT_NAME,
            "generatedAtUtc": seal._utc_now(),
            "status": "verified_pending_cryptographic_materialization",
            "transactionId": transaction_id,
            "contextSha256": context_sha256,
            "handoffContextSha256": handoff_context,
            "handoffTransactionId": response["handoffTransactionId"],
            "sealContextSha256": authority.seal_context_sha256,
            "sealTransactionId": validated.seal_receipt["transactionId"],
            "candidateCount": EXPECTED_CANDIDATE_COUNT,
            "inventoryCommitmentSha256": (
                authority.inventory_commitment_sha256
            ),
            "hubCommit": authority.hub_commit,
            "bootstrapSha256": authority.bootstrap_sha256,
            "sealScriptSha256": authority.seal_script_sha256,
            "recipientCertificateSha256": (
                authority.recipient_certificate_sha256
            ),
            "signerCertificateSha256": (
                authority.signer_certificate_sha256
            ),
            "producerOpensslPath": authority.openssl_path,
            "producerOpensslSha256": authority.openssl_sha256,
            "producerPythonPath": authority.python_path,
            "producerPythonSha256": authority.python_sha256,
            "verifierSourceCommit": authority.verifier_source_commit,
            "verifierRepositoryPath": authority.verifier_repository_path,
            "verifierGitPath": authority.verifier_git_path,
            "verifierGitSha256": authority.verifier_git_sha256,
            "verifierScriptPath": authority.verifier_script_path,
            "verifierScriptSha256": authority.verifier_script_sha256,
            "sealHelperPath": authority.seal_helper_path,
            "sealHelperSha256": authority.seal_helper_sha256,
            "verifierScriptGitBlobOid": (
                authority.verifier_script_git_blob_oid
            ),
            "sealHelperGitBlobOid": authority.seal_helper_git_blob_oid,
            "verifierPythonIdentitySource": (
                authority.verifier_python_identity_source
            ),
            "sealHelperLoadMode": authority.seal_helper_load_mode,
            "verifierPythonPath": authority.verifier_python_path,
            "verifierPythonSha256": authority.verifier_python_sha256,
            "inputArtifacts": dict(validated.artifacts),
            "transportReadbackPassed": True,
            "producerReportedSourceCandidatesLeftUntouched": True,
            "producerReportedPublishersStopped": True,
            "producerReportedContainsSecretValues": False,
            "verifierOutputContainsSecretValues": False,
            "cmsCryptographicVerificationStatus": (
                "pending_linux_materialization"
            ),
        }
        if set(receipt) != VERIFICATION_RECEIPT_FIELDS:
            raise VerificationError("verification receipt fields changed")

        seal._recover_fully_linked_transaction(
            final_paths=(options.output, options.commit_marker),
            transaction_id=transaction_id,
            context_sha256=context_sha256,
        )
        existing = _load_existing_verification(
            output=options.output,
            commit_marker=options.commit_marker,
            transaction_id=transaction_id,
            context_sha256=context_sha256,
        )
        if existing is not None:
            _validate_existing_receipt(existing, expected=receipt)
        else:
            seal._publish_transaction(
                outputs={options.output: _canonical_json_bytes(receipt)},
                commit_marker_path=options.commit_marker,
                transaction_id=transaction_id,
                context_sha256=context_sha256,
                commit_contract_name=COMMIT_CONTRACT_NAME,
            )
            existing = _load_existing_verification(
                output=options.output,
                commit_marker=options.commit_marker,
                transaction_id=transaction_id,
                context_sha256=context_sha256,
            )
            if existing is None:
                raise VerificationError(
                    "verification transaction was not committed"
                )
            _validate_existing_receipt(existing, expected=receipt)
        return {
            "contractName": CONTRACT_NAME,
            "status": "verified_pending_cryptographic_materialization",
            "transactionId": transaction_id,
            "handoffTransactionId": response["handoffTransactionId"],
            "containsSecretValues": False,
        }
    finally:
        for item in reversed(tuple(held.values())):
            item.close()


def run(arguments: Sequence[str] | None = None) -> int:
    try:
        options = build_parser().parse_args(arguments)
        result = verify(options)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (
        VerificationError,
        RuntimeError,
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ):
        print(
            json.dumps(
                {
                    "contractName": CONTRACT_NAME,
                    "status": "error",
                    "error": "secure incident-ticket handoff verification failed",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
