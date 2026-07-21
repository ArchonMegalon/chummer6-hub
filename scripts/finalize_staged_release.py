#!/usr/bin/env python3
"""Owner-only completion of one inert, privately-probed release generation.

The downloaded bootstrap deliberately cannot execute this program: it rejects
owner credentials and stops with a secret-redacted handoff.  This finalizer
pins every input and helper before its first mutation, prepares the Hub
authority overlay while the generation is still inert, advances Registry by
CAS, and only then activates the exact precomputed CURRENT pointer.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from collections.abc import Callable, Mapping, Sequence
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import sys
import time
from typing import Any, Optional
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlsplit, urlunsplit


SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
REVISION_ID = re.compile(r"^auth-[0-9a-f]{64}$")
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_SECRET_BYTES = 8192
HANDOFF_CONTRACT = "chummer.staged-release-finalizer-handoff/v1"
CHECKPOINT_CONTRACT = "chummer.staged-release-owner-finalizer-checkpoint/v1"
FINAL_RECEIPT_CONTRACT = "chummer.staged-release-owner-finalization/v1"
OWNER_ENVIRONMENT_NAMES = {
    "FLEET_INTERNAL_API_TOKEN",
    "CHUMMER_RELEASE_UPLOAD_TOKEN",
    "CHUMMER_RELEASE_UPLOAD_TICKET",
    "CHUMMER_REGISTRY_CONTROL_API_KEY",
    "REGISTRY_CONTROL_API_KEY",
}
REQUIRED_PINNED_TOOLS = {
    "ownerFinalizer",
    "scorecardMaterializer",
    "authorityAdvanceMaterializer",
    "authorityAdvanceVerifier",
    "registryCurrentInspector",
    "liveConvergenceVerifier",
    "registryAuthorityMaterializer",
    "registryAuthorityVerifier",
    "registryPublishMaterializer",
    "registryPublishVerifier",
    "registryAuthorityLibrary",
    "releaseScopeVerifier",
}
REQUIRED_PINNED_FILES = REQUIRED_PINNED_TOOLS | {
    "manifest",
    "promotionEvidence",
    "releaseScopeDecision",
    "releaseScopeVerification",
    "predecessorCurrent",
    "predecessorSnapshot",
    "predecessorDecision",
    "stagedConvergence",
}


class FinalizerError(RuntimeError):
    pass


class MutationOutcomeUnknown(FinalizerError):
    pass


class ReviewRequired(FinalizerError):
    """A bounded compensation succeeded and the release remains inert."""


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urlerror.HTTPError(req.full_url, code, msg, headers, fp)


def _args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Finalize one immutable staged generation using owner-only credentials. "
            "Credentials are accepted only from mode-0600 files outside the run workspace."
        )
    )
    parser.add_argument("--workspace", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--handoff", type=Path)
    source.add_argument("--resume-checkpoint", type=Path)
    parser.add_argument("--expected-handoff-sha256")
    parser.add_argument("--expected-checkpoint-sha256")
    parser.add_argument("--scorecard", type=Path)
    parser.add_argument("--expected-scorecard-sha256")
    parser.add_argument("--hub-owner-token-file", type=Path, required=True)
    parser.add_argument("--registry-control-key-file", type=Path, required=True)
    parser.add_argument("--registry-current-url")
    parser.add_argument("--registry-publish-url")
    parser.add_argument("--support-owner", default="Chummer release operations")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--convergence-attempts", type=int, default=6)
    parser.add_argument("--convergence-retry-seconds", type=int, default=5)
    return parser.parse_args(argv)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise FinalizerError(f"{label} must be canonical SHA-256")
    return value


def _safe_id(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or SAFE_ID.fullmatch(value) is None
        or ".." in value
    ):
        raise FinalizerError(f"{label} must be a traversal-safe identifier")
    return value


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        folded: set[str] = set()
        for key, value in pairs:
            normalized = key.casefold()
            if normalized in folded:
                raise FinalizerError(
                    f"{label} contains duplicate or case-shadowed field {key}"
                )
            folded.add(normalized)
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalizerError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise FinalizerError(f"{label} must be a JSON object")
    return value


def _workspace(path: Path) -> Path:
    if not path.is_absolute():
        raise FinalizerError("owner finalizer workspace must be absolute")
    try:
        root = path.resolve(strict=True)
        metadata = root.stat()
    except OSError as error:
        raise FinalizerError("owner finalizer workspace is unavailable") from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        raise FinalizerError(
            "owner finalizer workspace must be caller-owned and not writable by other users"
        )
    return root


def _confined(path: Path, root: Path, label: str, *, must_exist: bool = True) -> Path:
    if not path.is_absolute():
        raise FinalizerError(f"{label} must be absolute")
    try:
        resolved = path.resolve(strict=must_exist)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise FinalizerError(f"{label} must remain beneath the owner workspace") from error
    return resolved


def _stable_file(
    path: Path,
    label: str,
    maximum: int = MAX_JSON_BYTES,
    *,
    root: Optional[Path] = None,
    exact_mode: Optional[int] = None,
) -> tuple[Path, bytes]:
    resolved = _confined(path, root, label) if root is not None else path.resolve(strict=True)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError as error:
        raise FinalizerError(f"{label} could not be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or before.st_mode & 0o022
            or not 1 <= before.st_size <= maximum
        ):
            raise FinalizerError(
                f"{label} must be a caller-owned single-link regular file not writable by other users"
            )
        if exact_mode is not None and stat.S_IMODE(before.st_mode) != exact_mode:
            raise FinalizerError(f"{label} must have mode {exact_mode:04o}")
        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
        item.st_mode,
        item.st_nlink,
    )
    raw = b"".join(chunks)
    if identity(before) != identity(after) or len(raw) != before.st_size:
        raise FinalizerError(f"{label} changed during stable read")
    try:
        final = os.lstat(resolved)
    except OSError as error:
        raise FinalizerError(f"{label} changed during stable read") from error
    if (final.st_dev, final.st_ino) != (after.st_dev, after.st_ino):
        raise FinalizerError(f"{label} changed during stable read")
    return resolved, raw


def _read_secret(path: Path, workspace: Path, label: str) -> str:
    resolved, raw = _stable_file(
        path,
        label,
        MAX_SECRET_BYTES,
        exact_mode=0o600,
    )
    try:
        resolved.relative_to(workspace)
    except ValueError:
        pass
    else:
        raise FinalizerError(
            f"{label} must come from an owner-only source outside the persisted run workspace"
        )
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if raw.endswith(b"\r"):
        raw = raw[:-1]
    if not raw or b"\n" in raw or b"\r" in raw or b"\x00" in raw:
        raise FinalizerError(f"{label} must contain one bounded credential value")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FinalizerError(f"{label} is not UTF-8") from error


def _https_url(value: str, expected_path: str, label: str) -> str:
    parsed = urlsplit(value.strip())
    try:
        _ = parsed.port
    except ValueError as error:
        raise FinalizerError(f"{label} has an invalid port") from error
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != expected_path
    ):
        raise FinalizerError(f"{label} must be an explicit canonical HTTPS URL")
    return urlunsplit(("https", parsed.netloc, parsed.path, "", ""))


def _write_new(path: Path, root: Path, raw: bytes, label: str) -> Path:
    resolved = _confined(path, root, label, must_exist=False)
    resolved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _confined(resolved.parent, root, f"{label} parent")
    try:
        descriptor = os.open(
            resolved,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
    except FileExistsError as error:
        raise FinalizerError(f"{label} already exists") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    directory = os.open(resolved.parent, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return resolved


def _atomic_checkpoint(path: Path, root: Path, payload: dict[str, Any]) -> str:
    resolved = _confined(path, root, "owner finalizer checkpoint", must_exist=False)
    resolved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    temporary = resolved.with_name(f".{resolved.name}.{os.getpid()}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, resolved)
        directory = os.open(resolved.parent, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return _sha(raw)


def _file_entry(path: Path, raw: bytes, root: Path) -> dict[str, str]:
    return {"path": path.relative_to(root).as_posix(), "sha256": _sha(raw)}


def _resolve_entry(
    entry: Any, root: Path, label: str, maximum: int = MAX_JSON_BYTES
) -> tuple[Path, bytes]:
    if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
        raise FinalizerError(f"{label} file binding is invalid")
    relative = entry.get("path")
    expected = _require_sha(entry.get("sha256"), f"{label} digest")
    if (
        not isinstance(relative, str)
        or not relative
        or relative.startswith("/")
        or "\\" in relative
    ):
        raise FinalizerError(f"{label} path is not workspace-relative")
    path, raw = _stable_file(root.joinpath(*relative.split("/")), label, maximum, root=root)
    if not hmac.compare_digest(_sha(raw), expected):
        raise FinalizerError(f"{label} SHA-256 changed")
    return path, raw


def _load_handoff(
    path: Path, root: Path, expected_sha256: str
) -> tuple[dict[str, Any], dict[str, Path], bytes]:
    expected = _require_sha(expected_sha256.strip(), "expected handoff digest")
    resolved, raw = _stable_file(path, "staged finalizer handoff", root=root, exact_mode=0o600)
    if not hmac.compare_digest(_sha(raw), expected):
        raise FinalizerError("staged finalizer handoff SHA-256 does not match")
    payload = _strict_json(raw, "staged finalizer handoff")
    if (
        payload.get("contractName") != HANDOFF_CONTRACT
        or payload.get("contractVersion") != 1
        or payload.get("status") != "review_required"
        or payload.get("state") != "awaiting_owner_finalization"
        or payload.get("secretRedacted") is not True
        or payload.get("publicCurrentMutated") is not False
    ):
        raise FinalizerError("staged finalizer handoff identity is invalid")
    files = payload.get("files")
    if not isinstance(files, dict) or not REQUIRED_PINNED_FILES.issubset(files):
        raise FinalizerError("staged finalizer handoff omits required pinned tools or scope evidence")
    resolved_files: dict[str, Path] = {}
    for name, entry in files.items():
        file_path, _ = _resolve_entry(entry, root, f"handoff {name}")
        resolved_files[name] = file_path
    own = Path(__file__).resolve(strict=True)
    if own != resolved_files["ownerFinalizer"]:
        raise FinalizerError("this process is not the exact handoff-pinned owner finalizer")
    _safe_id(payload.get("generationId"), "handoff generationId")
    _safe_id(payload.get("stageReceiptId"), "handoff stageReceiptId")
    _require_sha(payload.get("targetPointerSha256"), "handoff target pointer digest")
    _require_sha(payload.get("manifestSha256"), "handoff manifest digest")
    scope_sha = _require_sha(
        payload.get("releaseScopeDecisionSha256"),
        "handoff release-scope decision digest",
    )
    scope_verification_sha = _require_sha(
        payload.get("releaseScopeVerificationSha256"),
        "handoff release-scope verification digest",
    )
    _require_sha(payload.get("predecessorSnapshotSha256"), "handoff predecessor snapshot digest")
    _require_sha(payload.get("predecessorDecisionSha256"), "handoff predecessor decision digest")
    _, scope_raw = _stable_file(
        resolved_files["releaseScopeDecision"], "handoff release scope decision", root=root
    )
    _, scope_verification_raw = _stable_file(
        resolved_files["releaseScopeVerification"],
        "handoff release scope verification",
        root=root,
    )
    scope_verification = _strict_json(
        scope_verification_raw, "handoff release scope verification"
    )
    if (
        not hmac.compare_digest(_sha(scope_raw), scope_sha)
        or not hmac.compare_digest(_sha(scope_verification_raw), scope_verification_sha)
        or scope_verification.get("decisionSha256") != scope_sha
        or scope_verification.get("manifestSha256") != payload.get("manifestSha256")
        or scope_verification.get("exactIncomingDesktopScope")
        != payload.get("exactIncomingDesktopScope")
        or scope_verification.get("supportOwner") != payload.get("supportOwner")
        or scope_verification.get("platforms") != payload.get("releaseScopePlatforms")
    ):
        raise FinalizerError("staged finalizer handoff release-scope binding is inconsistent")
    return payload, resolved_files, raw


def _run_tool(
    tool: Path,
    arguments: Sequence[str],
    *,
    stdout_path: Optional[Path] = None,
    root: Optional[Path] = None,
) -> str:
    completed = subprocess.run(
        [sys.executable, str(tool), *arguments],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            key: value
            for key, value in os.environ.items()
            if key not in OWNER_ENVIRONMENT_NAMES
        },
    )
    if completed.returncode != 0:
        diagnostic = completed.stderr.strip().replace("\r", " ").replace("\n", " ")
        raise FinalizerError(
            f"pinned helper {tool.name} failed: {diagnostic[:1000] or 'no diagnostic'}"
        )
    if stdout_path is not None:
        if root is None:
            raise FinalizerError("internal finalizer error: stdout root is required")
        _write_new(stdout_path, root, completed.stdout.encode(), f"{tool.name} receipt")
    return completed.stdout


class HttpsTransport:
    def __init__(self, timeout: int):
        self.timeout = timeout
        self._opener = urlrequest.build_opener(
            urlrequest.HTTPSHandler(context=ssl.create_default_context()),
            _NoRedirect(),
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        body: Optional[bytes] = None,
        credential_header: Optional[tuple[str, str]] = None,
        maximum: int = 16 * 1024 * 1024,
    ) -> tuple[int, bytes]:
        headers = {"Accept": "application/json", "Cache-Control": "no-cache"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if credential_header is not None:
            headers[credential_header[0]] = credential_header[1]
        request = urlrequest.Request(url, data=body, headers=headers, method=method)
        try:
            response = self._opener.open(request, timeout=self.timeout)
        except urlerror.HTTPError as error:
            raw = error.read(maximum + 1)
            if len(raw) > maximum:
                raise FinalizerError("HTTPS error response exceeded its size limit") from error
            return error.code, raw
        except (urlerror.URLError, TimeoutError, OSError) as error:
            raise MutationOutcomeUnknown(f"HTTPS {method} outcome is unknown") from error
        with response:
            raw = response.read(maximum + 1)
            if len(raw) > maximum:
                raise FinalizerError("HTTPS response exceeded its size limit")
            return response.status, raw


def classify_activation_pointer(
    observed_pointer_bytes: bytes,
    target_pointer_sha256: str,
    predecessor_pointer_sha256: Optional[str],
) -> str:
    """Classify public CURRENT without trusting parsed mutable fields."""
    observed = _sha(observed_pointer_bytes)
    target = _require_sha(target_pointer_sha256, "target pointer digest")
    predecessor = predecessor_pointer_sha256
    if predecessor is not None and predecessor.startswith("sha256:"):
        predecessor = predecessor[7:]
    if predecessor is not None:
        predecessor = _require_sha(predecessor, "predecessor pointer digest")
    if hmac.compare_digest(observed, target):
        return "target"
    if predecessor is not None and hmac.compare_digest(observed, predecessor):
        return "predecessor"
    return "unknown"


def reconcile_activation_failure(
    *,
    observed_pointer_bytes: bytes,
    target_pointer_sha256: str,
    predecessor_pointer_sha256: Optional[str],
    retry_activation: Callable[[], bool],
    compensate_registry: Callable[[], bool],
) -> str:
    """Resolve only the two byte-exact, safe post-CAS activation states."""
    classification = classify_activation_pointer(
        observed_pointer_bytes,
        target_pointer_sha256,
        predecessor_pointer_sha256,
    )
    if classification == "target":
        if not retry_activation():
            raise MutationOutcomeUnknown(
                "target CURRENT is visible but idempotent activation acknowledgement failed"
            )
        return "activated"
    if classification == "predecessor":
        if not compensate_registry():
            raise MutationOutcomeUnknown(
                "predecessor CURRENT remained visible but Registry compensation was not confirmed"
            )
        return "compensated_review_required"
    raise MutationOutcomeUnknown(
        "public CURRENT matches neither the staged target nor its exact predecessor"
    )


def _registry_publish_payload_from_envelope(
    manifest_raw: bytes,
    snapshot_raw: bytes,
    decision_raw: bytes,
    expected_current_snapshot_sha256: str,
) -> bytes:
    """Build only the server's narrow CAS wire shape from already verified bytes."""
    snapshot = _strict_json(snapshot_raw, "Registry compensation snapshot")
    metadata_fields = (
        "releaseVersion",
        "channel",
        "status",
        "rolloutState",
        "supportabilityState",
        "availablePlatforms",
        "primaryHeadByPlatform",
        "artifactCount",
        "downloadAccessPosture",
        "knownIssueSummary",
        "registryRepository",
        "registryCommit",
        "supportOwner",
        "nextActions",
        "artifacts",
    )
    try:
        metadata = {name: snapshot[name] for name in metadata_fields}
    except KeyError as error:
        raise FinalizerError(
            "Registry compensation snapshot omits required metadata"
        ) from error
    expected = _require_sha(
        expected_current_snapshot_sha256,
        "Registry compensation expected-current digest",
    )
    payload = {
        "metadata": metadata,
        "manifestBytes": base64.b64encode(manifest_raw).decode("ascii"),
        "releaseDecisionBytes": base64.b64encode(decision_raw).decode("ascii"),
        "expectedCurrentSnapshotSha256": expected,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _decode_registry_response(raw: bytes) -> dict[str, bytes | dict[str, Any]]:
    response = _strict_json(raw, "Registry CURRENT response")
    if set(response) != {
        "current",
        "snapshot",
        "snapshotBytes",
        "manifestBytes",
        "releaseDecisionBytes",
    }:
        raise FinalizerError("Registry CURRENT response has an unexpected field set")
    decoded: dict[str, bytes | dict[str, Any]] = {
        "current": response["current"],
        "snapshot": response["snapshot"],
    }
    for field in ("snapshotBytes", "manifestBytes", "releaseDecisionBytes"):
        value = response[field]
        try:
            body = base64.b64decode(value, validate=True)
        except (TypeError, ValueError, binascii.Error) as error:
            raise FinalizerError(f"Registry CURRENT {field} is not canonical base64") from error
        if base64.b64encode(body).decode("ascii") != value:
            raise FinalizerError(f"Registry CURRENT {field} is not canonical base64")
        decoded[field] = body
    return decoded


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _checkpoint_add_file(
    checkpoint: dict[str, Any], name: str, path: Path, root: Path
) -> None:
    _, raw = _stable_file(path, name, root=root)
    checkpoint.setdefault("files", {})[name] = _file_entry(path, raw, root)


def _save_checkpoint(
    checkpoint: dict[str, Any], path: Path, root: Path, state: str
) -> str:
    checkpoint["state"] = state
    checkpoint["updatedAtUtc"] = _utc_now()
    digest = _atomic_checkpoint(path, root, checkpoint)
    print(f"checkpoint_state={state}")
    print(f"checkpoint_sha256={digest}")
    return digest


def _load_checkpoint(
    path: Path, root: Path, expected_sha256: str
) -> tuple[dict[str, Any], dict[str, Path], bytes]:
    expected = _require_sha(expected_sha256.strip(), "expected checkpoint digest")
    resolved, raw = _stable_file(
        path,
        "owner finalizer checkpoint",
        root=root,
        exact_mode=0o600,
    )
    if not hmac.compare_digest(_sha(raw), expected):
        raise FinalizerError("owner finalizer checkpoint SHA-256 does not match")
    payload = _strict_json(raw, "owner finalizer checkpoint")
    if (
        payload.get("contractName") != CHECKPOINT_CONTRACT
        or payload.get("contractVersion") != 1
        or payload.get("state")
        not in {
            "prepared",
            "registry_review_published",
            "hub_authority_staged",
            "registry_preview_published",
            "hub_activation_confirmed",
            "compensated_review_required",
            "complete",
        }
    ):
        raise FinalizerError("owner finalizer checkpoint identity is invalid")
    files = payload.get("files")
    if not isinstance(files, dict) or "ownerFinalizer" not in files:
        raise FinalizerError("owner finalizer checkpoint file inventory is invalid")
    resolved_files: dict[str, Path] = {}
    for name, entry in files.items():
        resolved_files[name], _ = _resolve_entry(entry, root, f"checkpoint {name}")
    if Path(__file__).resolve(strict=True) != resolved_files["ownerFinalizer"]:
        raise FinalizerError("resume is not executing the checkpoint-pinned owner finalizer")
    _require_sha(
        payload.get("releaseScopeDecisionSha256"),
        "checkpoint release-scope decision digest",
    )
    expected = payload.get("expected")
    if not isinstance(expected, dict):
        raise FinalizerError("owner finalizer checkpoint expected bindings are missing")
    _require_sha(
        expected.get("releaseScopeVerificationSha256"),
        "checkpoint release-scope verification digest",
    )
    if not isinstance(payload.get("exactIncomingDesktopScope"), str) or not payload[
        "exactIncomingDesktopScope"
    ]:
        raise FinalizerError("owner finalizer checkpoint exact release scope is missing")
    return payload, resolved_files, raw


def _json_file(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    _, raw = _stable_file(path, label)
    return raw, _strict_json(raw, label)


def _post_json(
    transport: HttpsTransport,
    url: str,
    body: bytes,
    header: tuple[str, str],
    label: str,
) -> bytes:
    status, raw = transport.request(
        "POST", url, body=body, credential_header=header
    )
    if status != 200:
        raise FinalizerError(f"{label} returned HTTP {status}")
    return raw


def _verify_registry_current(
    transport: HttpsTransport,
    url: str,
    expected_snapshot_sha256: str,
) -> bytes:
    status, raw = transport.request("GET", url)
    if status != 200:
        raise FinalizerError(f"Registry CURRENT returned HTTP {status}")
    decoded = _decode_registry_response(raw)
    snapshot_raw = decoded["snapshotBytes"]
    assert isinstance(snapshot_raw, bytes)
    if not hmac.compare_digest(_sha(snapshot_raw), expected_snapshot_sha256):
        raise FinalizerError("Registry CURRENT does not match the expected exact snapshot")
    return raw


def _run_convergence(
    checkpoint: dict[str, Any], files: Mapping[str, Path], root: Path
) -> None:
    expected = checkpoint["expected"]
    policy = checkpoint["convergencePolicy"]
    evidence = root / checkpoint["evidenceDirectory"]
    verifier = files["liveConvergenceVerifier"]
    for name, generation in (
        ("publicGenerationConvergence", checkpoint["generationId"]),
        ("publicCurrentConvergence", None),
    ):
        output = evidence / f"{name}.generated.json"
        arguments = [
            "--base-url",
            checkpoint["liveBaseUrl"],
            "--expected-release-version",
            checkpoint["releaseVersion"],
            "--expected-manifest-sha256",
            expected["manifestSha256"],
            "--expected-release-decision-sha256",
            expected["previewDecisionSha256"],
            "--timeout",
            str(policy["timeoutSeconds"]),
        ]
        if generation is not None:
            arguments[2:2] = ["--generation-id", generation]
        last_error: Optional[FinalizerError] = None
        for attempt in range(policy["attempts"]):
            try:
                _run_tool(verifier, arguments, stdout_path=output, root=root)
                _checkpoint_add_file(checkpoint, name, output, root)
                break
            except FinalizerError as error:
                last_error = error
                if output.exists():
                    output.unlink()
                if attempt + 1 < policy["attempts"]:
                    time.sleep(policy["retrySeconds"])
        else:
            raise FinalizerError(f"{name} failed: {last_error}")


def _prepare_transaction(args: argparse.Namespace, root: Path) -> tuple[dict[str, Any], dict[str, Path], Path]:
    if args.expected_handoff_sha256 is None:
        raise FinalizerError("--expected-handoff-sha256 is required for a new finalization")
    if args.scorecard is None or args.expected_scorecard_sha256 is None:
        raise FinalizerError("a digest-pinned scorecard is required for a new finalization")
    if args.checkpoint is None:
        raise FinalizerError("--checkpoint is required before a new finalization can mutate authority")
    if args.registry_current_url is None or args.registry_publish_url is None:
        raise FinalizerError("explicit Registry current and publish URLs are required")
    handoff, files, handoff_raw = _load_handoff(
        args.handoff, root, args.expected_handoff_sha256
    )
    live_origin = handoff["liveBaseUrl"]
    registry_current_url = _https_url(
        args.registry_current_url,
        "/api/v1/registry/release-authority/current",
        "Registry CURRENT URL",
    )
    registry_publish_url = _https_url(
        args.registry_publish_url,
        "/api/v1/registry/release-authority/publish",
        "Registry publish URL",
    )
    if urlsplit(registry_current_url).netloc.lower() != urlsplit(registry_publish_url).netloc.lower():
        raise FinalizerError("Registry endpoints must share one origin")
    evidence = args.handoff.resolve(strict=True).parent / "owner-finalization"
    evidence.mkdir(mode=0o700)
    if evidence.stat().st_mode & 0o022:
        raise FinalizerError("owner finalization evidence directory is writable by other users")

    manifest = files["manifest"]
    if args.support_owner != handoff.get("supportOwner"):
        raise FinalizerError(
            "owner finalizer support owner disagrees with the approved release scope"
        )
    scope_platforms = handoff.get("releaseScopePlatforms")
    if not isinstance(scope_platforms, list) or len(scope_platforms) != 1:
        raise FinalizerError("mac owner finalizer requires one exact approved platform scope")
    scope_platform = scope_platforms[0]
    if not isinstance(scope_platform, dict):
        raise FinalizerError("approved release platform scope is malformed")
    scope_heads = [scope_platform.get("primaryHead"), *(scope_platform.get("fallbackHeads") or [])]
    if any(not isinstance(head, str) or not head for head in scope_heads):
        raise FinalizerError("approved release head scope is malformed")
    scope_reverification = evidence / "RELEASE_SCOPE_REVERIFICATION.generated.json"
    _run_tool(
        files["releaseScopeVerifier"],
        [
            "--decision", str(files["releaseScopeDecision"]),
            "--expected-sha256", handoff["releaseScopeDecisionSha256"],
            "--authority", handoff["releaseScopeAuthority"],
            "--manifest", str(manifest),
            "--promotion-evidence", str(files["promotionEvidence"]),
            "--expected-release-version", handoff["releaseVersion"],
            "--expected-channel", handoff["channel"],
            "--expected-platform", str(scope_platform.get("platform") or ""),
            "--expected-rid", str(scope_platform.get("rid") or ""),
            "--expected-heads", ",".join(scope_heads),
            "--output", str(scope_reverification),
        ],
    )
    _, scope_reverification_raw = _stable_file(
        scope_reverification, "owner release scope reverification", root=root
    )
    _, staged_scope_verification_raw = _stable_file(
        files["releaseScopeVerification"],
        "staged release scope verification",
        root=root,
    )
    if not hmac.compare_digest(scope_reverification_raw, staged_scope_verification_raw):
        raise FinalizerError(
            "owner release-scope reverification disagrees with staged candidate evidence"
        )
    predecessor_current = files["predecessorCurrent"]
    predecessor_snapshot = files["predecessorSnapshot"]
    predecessor_decision = files["predecessorDecision"]
    convergence = files["stagedConvergence"]
    scorecard_output = evidence / "CAMPAIGN_OPERABILITY_SCORECARD.generated.json"
    scorecard_receipt = evidence / "CAMPAIGN_OPERABILITY_SCORECARD_HANDOFF.generated.json"
    _run_tool(
        files["scorecardMaterializer"],
        [
            "--source", str(args.scorecard),
            "--expected-sha256", args.expected_scorecard_sha256,
            "--allowed-root", str(root),
            "--manifest", str(manifest),
            "--predecessor-snapshot", str(predecessor_snapshot),
            "--predecessor-decision", str(predecessor_decision),
            "--convergence", str(convergence),
            "--expected-release-version", handoff["releaseVersion"],
            "--output", str(scorecard_output),
            "--receipt", str(scorecard_receipt),
        ],
    )

    predecessor_snapshot_raw, predecessor_snapshot_json = _json_file(
        predecessor_snapshot, "predecessor snapshot"
    )
    registry_commit = predecessor_snapshot_json.get("registryCommit")
    if not isinstance(registry_commit, str) or re.fullmatch(r"[0-9a-f]{40}", registry_commit) is None:
        raise FinalizerError("predecessor snapshot lacks a canonical Registry commit")
    preview_dir = evidence / "preview-authority"
    _run_tool(
        files["registryAuthorityMaterializer"],
        [
            "--manifest", str(manifest),
            "--output-dir", str(preview_dir),
            "--registry-commit", registry_commit,
            "--decision-status", "preview_ready",
            "--support-owner", args.support_owner,
            "--generated-at", _utc_now(),
            "--next-action", "Close retained flagship gaps before any stable or gold claim.",
            "--scorecard", str(scorecard_output),
            "--convergence", str(convergence),
            "--predecessor-current", str(predecessor_current),
            "--predecessor-snapshot", str(predecessor_snapshot),
            "--predecessor-decision", str(predecessor_decision),
        ],
        stdout_path=evidence / "PREVIEW_AUTHORITY_MATERIALIZATION.generated.json",
        root=root,
    )
    preview_current = preview_dir / "CURRENT.json"
    preview_snapshot = preview_dir / "SNAPSHOT.json"
    preview_decision = preview_dir / "RELEASE_DECISION.json"
    _run_tool(
        files["registryAuthorityVerifier"],
        [
            "--manifest", str(manifest),
            "--current", str(preview_current),
            "--snapshot", str(preview_snapshot),
            "--decision", str(preview_decision),
            "--scorecard", str(scorecard_output),
            "--convergence", str(convergence),
            "--predecessor-current", str(predecessor_current),
            "--predecessor-snapshot", str(predecessor_snapshot),
            "--predecessor-decision", str(predecessor_decision),
        ],
        stdout_path=evidence / "PREVIEW_AUTHORITY_VERIFICATION.generated.json",
        root=root,
    )

    authority_request = evidence / ".hub-staged-authority-request.json"
    _run_tool(
        files["authorityAdvanceMaterializer"],
        [
            "--generation-id", handoff["generationId"],
            "--staged-handoff", str(args.handoff),
            "--predecessor-current", str(predecessor_current),
            "--predecessor-snapshot", str(predecessor_snapshot),
            "--predecessor-decision", str(predecessor_decision),
            "--successor-current", str(preview_current),
            "--successor-snapshot", str(preview_snapshot),
            "--successor-decision", str(preview_decision),
            "--scorecard", str(scorecard_output),
            "--convergence", str(convergence),
            "--output", str(authority_request),
        ],
        stdout_path=evidence / "HUB_STAGED_AUTHORITY_REQUEST.generated.json",
        root=root,
    )

    predecessor_current_raw, _ = _json_file(predecessor_current, "predecessor CURRENT")
    predecessor_decision_raw, _ = _json_file(predecessor_decision, "predecessor decision")
    preview_snapshot_raw, _ = _json_file(preview_snapshot, "preview snapshot")
    preview_decision_raw, _ = _json_file(preview_decision, "preview decision")
    manifest_raw, _ = _json_file(manifest, "canonical manifest")
    review_request = evidence / ".registry-review-request.json"
    preview_request = evidence / ".registry-preview-request.json"
    compensation_request = evidence / ".registry-compensation-request.json"
    # The review request expected-current binding is filled after one read-only
    # Registry inspection and is therefore created immediately before checkpoint.
    transport = HttpsTransport(args.timeout)
    status, registry_before_raw = transport.request("GET", registry_current_url)
    if status not in {200, 404}:
        raise FinalizerError(f"Registry CURRENT returned HTTP {status}")
    registry_before_snapshot = "none"
    if status == 200:
        decoded = _decode_registry_response(registry_before_raw)
        body = decoded["snapshotBytes"]
        assert isinstance(body, bytes)
        registry_before_snapshot = _sha(body)
    _run_tool(
        files["registryPublishMaterializer"],
        [
            "--manifest", str(manifest),
            "--current", str(predecessor_current),
            "--snapshot", str(predecessor_snapshot),
            "--decision", str(predecessor_decision),
            "--expected-current-snapshot-sha256", registry_before_snapshot,
            "--output", str(review_request),
        ],
        stdout_path=evidence / "REGISTRY_REVIEW_REQUEST.generated.json",
        root=root,
    )
    _run_tool(
        files["registryPublishMaterializer"],
        [
            "--manifest", str(manifest),
            "--current", str(preview_current),
            "--snapshot", str(preview_snapshot),
            "--decision", str(preview_decision),
            "--scorecard", str(scorecard_output),
            "--convergence", str(convergence),
            "--predecessor-current", str(predecessor_current),
            "--predecessor-snapshot", str(predecessor_snapshot),
            "--predecessor-decision", str(predecessor_decision),
            "--expected-current-snapshot-sha256", _sha(predecessor_snapshot_raw),
            "--output", str(preview_request),
        ],
        stdout_path=evidence / "REGISTRY_PREVIEW_REQUEST.generated.json",
        root=root,
    )
    compensation_raw = _registry_publish_payload_from_envelope(
        manifest_raw,
        predecessor_snapshot_raw,
        predecessor_decision_raw,
        _sha(preview_snapshot_raw),
    )
    _write_new(
        compensation_request,
        root,
        compensation_raw,
        "Registry compensation request",
    )

    tracked = {
        **files,
        "handoff": args.handoff.resolve(strict=True),
        "scorecard": scorecard_output,
        "scorecardReceipt": scorecard_receipt,
        "previewCurrent": preview_current,
        "previewSnapshot": preview_snapshot,
        "previewDecision": preview_decision,
        "authorityRequest": authority_request,
        "reviewRequest": review_request,
        "previewRequest": preview_request,
        "compensationRequest": compensation_request,
        "scopeReverification": scope_reverification,
    }
    checkpoint_files: dict[str, dict[str, str]] = {}
    for name, path in tracked.items():
        resolved, raw = _stable_file(path, name, root=root)
        checkpoint_files[name] = _file_entry(resolved, raw, root)
    checkpoint = {
        "contractName": CHECKPOINT_CONTRACT,
        "contractVersion": 1,
        "createdAtUtc": _utc_now(),
        "updatedAtUtc": _utc_now(),
        "state": "prepared",
        "releaseVersion": handoff["releaseVersion"],
        "generationId": handoff["generationId"],
        "stageReceiptId": handoff["stageReceiptId"],
        "handoffSha256": _sha(handoff_raw),
        "targetPointerSha256": handoff["targetPointerSha256"],
        "releaseScopeDecisionSha256": handoff["releaseScopeDecisionSha256"],
        "exactIncomingDesktopScope": handoff["exactIncomingDesktopScope"],
        "predecessorPointerSha256": handoff.get("previousPointerSha256"),
        "stagedAuthorityUrl": handoff["stagedAuthorityUrl"],
        "activationUrl": handoff["activationUrl"],
        "liveBaseUrl": live_origin,
        "registryCurrentUrl": registry_current_url,
        "registryPublishUrl": registry_publish_url,
        "registryInitialSnapshotSha256": registry_before_snapshot,
        "evidenceDirectory": evidence.relative_to(root).as_posix(),
        "files": checkpoint_files,
        "expected": {
            "manifestSha256": handoff["manifestSha256"],
            "releaseScopeVerificationSha256": handoff[
                "releaseScopeVerificationSha256"
            ],
            "predecessorSnapshotSha256": _sha(predecessor_snapshot_raw),
            "predecessorDecisionSha256": _sha(predecessor_decision_raw),
            "previewSnapshotSha256": _sha(preview_snapshot_raw),
            "previewDecisionSha256": _sha(preview_decision_raw),
            "authorityRevisionId": None,
        },
        "convergencePolicy": {
            "timeoutSeconds": args.timeout,
            "attempts": args.convergence_attempts,
            "retrySeconds": args.convergence_retry_seconds,
        },
    }
    checkpoint_path = _confined(args.checkpoint, root, "owner checkpoint", must_exist=False)
    if checkpoint_path.exists():
        raise FinalizerError("owner finalizer checkpoint already exists")
    _save_checkpoint(checkpoint, checkpoint_path, root, "prepared")
    return checkpoint, tracked, checkpoint_path


def _execute_transaction(
    checkpoint: dict[str, Any],
    files: dict[str, Path],
    checkpoint_path: Path,
    root: Path,
    hub_token: str,
    registry_key: str,
) -> None:
    transport = HttpsTransport(checkpoint["convergencePolicy"]["timeoutSeconds"])
    expected = checkpoint["expected"]
    evidence = root / checkpoint["evidenceDirectory"]
    registry_header = ("X-Chummer-Registry-Key", registry_key)
    hub_header = ("Authorization", f"Bearer {hub_token}")

    state = checkpoint["state"]
    if state == "complete":
        return
    if state == "compensated_review_required":
        raise ReviewRequired(
            "Registry was compensated to review_required; CURRENT was not activated"
        )

    # Establish the exact review seed in Registry. This CAS is fail-closed and
    # may already have committed if a previous request lost its response.
    if state == "prepared":
        status, raw = transport.request("GET", checkpoint["registryCurrentUrl"])
        observed = "none"
        if status == 200:
            decoded = _decode_registry_response(raw)
            snapshot_body = decoded["snapshotBytes"]
            assert isinstance(snapshot_body, bytes)
            observed = _sha(snapshot_body)
        elif status != 404:
            raise FinalizerError(f"Registry CURRENT returned HTTP {status}")
        if observed != expected["predecessorSnapshotSha256"]:
            if observed != checkpoint["registryInitialSnapshotSha256"]:
                raise FinalizerError(
                    "Registry CURRENT changed after checkpoint creation; review-seed CAS not attempted"
                )
            review_response = _post_json(
                transport,
                checkpoint["registryPublishUrl"],
                files["reviewRequest"].read_bytes(),
                registry_header,
                "Registry review-seed CAS",
            )
            response_path = evidence / "REGISTRY_REVIEW_RESPONSE.json"
            _write_new(response_path, root, review_response, "Registry review response")
            _run_tool(
                files["registryPublishVerifier"],
                [
                    "--manifest", str(files["manifest"]),
                    "--current", str(files["predecessorCurrent"]),
                    "--snapshot", str(files["predecessorSnapshot"]),
                    "--decision", str(files["predecessorDecision"]),
                    "--response", str(response_path),
                    "--output", str(evidence / "REGISTRY_REVIEW_RESPONSE.generated.json"),
                ],
            )
            _checkpoint_add_file(checkpoint, "registryReviewResponse", response_path, root)
        _verify_registry_current(
            transport,
            checkpoint["registryCurrentUrl"],
            expected["predecessorSnapshotSha256"],
        )
        _save_checkpoint(checkpoint, checkpoint_path, root, "registry_review_published")
        state = "registry_review_published"

    if state == "registry_review_published":
        authority_response = _post_json(
            transport,
            checkpoint["stagedAuthorityUrl"],
            files["authorityRequest"].read_bytes(),
            hub_header,
            "Hub staged authority preparation",
        )
        response_path = evidence / "HUB_STAGED_AUTHORITY_RESPONSE.json"
        if not response_path.exists():
            _write_new(response_path, root, authority_response, "Hub authority response")
        elif response_path.read_bytes() != authority_response:
            raise FinalizerError("idempotent Hub authority response bytes changed")
        receipt_path = evidence / "HUB_STAGED_AUTHORITY_RESPONSE.generated.json"
        if not receipt_path.exists():
            _run_tool(
                files["authorityAdvanceVerifier"],
                [
                    "--response", str(response_path),
                    "--request", str(files["authorityRequest"]),
                    "--generation-id", checkpoint["generationId"],
                    "--release-version", checkpoint["releaseVersion"],
                    "--predecessor-current", str(files["predecessorCurrent"]),
                    "--predecessor-snapshot", str(files["predecessorSnapshot"]),
                    "--predecessor-decision", str(files["predecessorDecision"]),
                    "--successor-current", str(files["previewCurrent"]),
                    "--successor-snapshot", str(files["previewSnapshot"]),
                    "--successor-decision", str(files["previewDecision"]),
                    "--scorecard", str(files["scorecard"]),
                    "--convergence", str(files["stagedConvergence"]),
                    "--output", str(receipt_path),
                ],
            )
        _, receipt = _json_file(receipt_path, "Hub authority receipt")
        revision_id = receipt.get("revisionId")
        if not isinstance(revision_id, str) or REVISION_ID.fullmatch(revision_id) is None:
            raise FinalizerError("Hub authority receipt lacks a canonical revisionId")
        checkpoint["expected"]["authorityRevisionId"] = revision_id
        for name, path in (
            ("hubAuthorityResponse", response_path),
            ("hubAuthorityReceipt", receipt_path),
        ):
            _checkpoint_add_file(checkpoint, name, path, root)
            files[name] = path
        _save_checkpoint(checkpoint, checkpoint_path, root, "hub_authority_staged")
        state = "hub_authority_staged"

    if state == "hub_authority_staged":
        try:
            preview_response = _post_json(
                transport,
                checkpoint["registryPublishUrl"],
                files["previewRequest"].read_bytes(),
                registry_header,
                "Registry preview CAS",
            )
        except MutationOutcomeUnknown:
            _verify_registry_current(
                transport,
                checkpoint["registryCurrentUrl"],
                expected["previewSnapshotSha256"],
            )
            preview_response = b""
        if preview_response:
            response_path = evidence / "REGISTRY_PREVIEW_RESPONSE.json"
            _write_new(response_path, root, preview_response, "Registry preview response")
            receipt_path = evidence / "REGISTRY_PREVIEW_RESPONSE.generated.json"
            _run_tool(
                files["registryPublishVerifier"],
                [
                    "--manifest", str(files["manifest"]),
                    "--current", str(files["previewCurrent"]),
                    "--snapshot", str(files["previewSnapshot"]),
                    "--decision", str(files["previewDecision"]),
                    "--scorecard", str(files["scorecard"]),
                    "--convergence", str(files["stagedConvergence"]),
                    "--predecessor-current", str(files["predecessorCurrent"]),
                    "--predecessor-snapshot", str(files["predecessorSnapshot"]),
                    "--predecessor-decision", str(files["predecessorDecision"]),
                    "--response", str(response_path),
                    "--output", str(receipt_path),
                ],
            )
            for name, path in (
                ("registryPreviewResponse", response_path),
                ("registryPreviewReceipt", receipt_path),
            ):
                _checkpoint_add_file(checkpoint, name, path, root)
                files[name] = path
        _verify_registry_current(
            transport,
            checkpoint["registryCurrentUrl"],
            expected["previewSnapshotSha256"],
        )
        _save_checkpoint(checkpoint, checkpoint_path, root, "registry_preview_published")
        state = "registry_preview_published"

    def activation_body() -> bytes:
        revision = checkpoint["expected"].get("authorityRevisionId")
        if not isinstance(revision, str) or REVISION_ID.fullmatch(revision) is None:
            raise FinalizerError("checkpoint lacks exact Hub authority revision")
        return (
            json.dumps(
                {
                    "stageReceiptId": checkpoint["stageReceiptId"],
                    "expectedAuthorityRevisionId": revision,
                    "expectedSnapshotSha256": expected["previewSnapshotSha256"],
                    "expectedDecisionSha256": expected["previewDecisionSha256"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()

    def activate() -> bool:
        try:
            response = _post_json(
                transport,
                checkpoint["activationUrl"],
                activation_body(),
                hub_header,
                "Hub staged activation",
            )
        except (FinalizerError, MutationOutcomeUnknown):
            return False
        payload = _strict_json(response, "Hub staged activation response")
        if (
            payload.get("generationId") != checkpoint["generationId"]
            or payload.get("version") != checkpoint["releaseVersion"]
        ):
            return False
        response_path = evidence / "HUB_STAGED_ACTIVATION_RESPONSE.json"
        if not response_path.exists():
            _write_new(response_path, root, response, "Hub activation response")
        elif response_path.read_bytes() != response:
            return False
        _checkpoint_add_file(checkpoint, "hubActivationResponse", response_path, root)
        files["hubActivationResponse"] = response_path
        return True

    def compensate() -> bool:
        try:
            _post_json(
                transport,
                checkpoint["registryPublishUrl"],
                files["compensationRequest"].read_bytes(),
                registry_header,
                "Registry preview compensation CAS",
            )
        except MutationOutcomeUnknown:
            # A lost response is not a failed CAS.  Resolve it from exact
            # Registry CURRENT bytes before deciding whether compensation won.
            pass
        except FinalizerError:
            return False
        try:
            _verify_registry_current(
                transport,
                checkpoint["registryCurrentUrl"],
                expected["predecessorSnapshotSha256"],
            )
        except (FinalizerError, MutationOutcomeUnknown):
            return False
        return True

    if state == "registry_preview_published":
        if not activate():
            pointer_url = f"{checkpoint['liveBaseUrl']}/downloads/current.json"
            pointer_status, pointer_raw = transport.request("GET", pointer_url, maximum=131072)
            if pointer_status != 200:
                raise MutationOutcomeUnknown(
                    f"activation failed and public CURRENT returned HTTP {pointer_status}"
                )
            recovery = reconcile_activation_failure(
                observed_pointer_bytes=pointer_raw,
                target_pointer_sha256=checkpoint["targetPointerSha256"],
                predecessor_pointer_sha256=checkpoint.get("predecessorPointerSha256"),
                retry_activation=activate,
                compensate_registry=compensate,
            )
            if recovery == "compensated_review_required":
                _save_checkpoint(
                    checkpoint, checkpoint_path, root, "compensated_review_required"
                )
                raise ReviewRequired(
                    "activation was not visible; Registry was compensated to review_required"
                )
        _save_checkpoint(checkpoint, checkpoint_path, root, "hub_activation_confirmed")
        state = "hub_activation_confirmed"

    if state == "hub_activation_confirmed":
        _run_convergence(checkpoint, files, root)
        receipt = {
            "contractName": FINAL_RECEIPT_CONTRACT,
            "contractVersion": 1,
            "status": "preview_ready",
            "releaseVersion": checkpoint["releaseVersion"],
            "generationId": checkpoint["generationId"],
            "stageReceiptId": checkpoint["stageReceiptId"],
            "manifestSha256": expected["manifestSha256"],
            "releaseScopeDecisionSha256": checkpoint[
                "releaseScopeDecisionSha256"
            ],
            "releaseScopeVerificationSha256": expected[
                "releaseScopeVerificationSha256"
            ],
            "exactIncomingDesktopScope": checkpoint[
                "exactIncomingDesktopScope"
            ],
            "snapshotSha256": expected["previewSnapshotSha256"],
            "decisionSha256": expected["previewDecisionSha256"],
            "authorityRevisionId": expected["authorityRevisionId"],
            "targetPointerSha256": checkpoint["targetPointerSha256"],
            "completedAtUtc": _utc_now(),
        }
        receipt_path = evidence / "STAGED_RELEASE_OWNER_FINALIZATION.generated.json"
        _write_new(
            receipt_path,
            root,
            (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode(),
            "owner finalization receipt",
        )
        _checkpoint_add_file(checkpoint, "finalReceipt", receipt_path, root)
        files["finalReceipt"] = receipt_path
        _save_checkpoint(checkpoint, checkpoint_path, root, "complete")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _args(argv)
    try:
        for name in OWNER_ENVIRONMENT_NAMES:
            if os.environ.get(name):
                raise FinalizerError(
                    f"owner finalizer rejects ambient {name}; use the dedicated mode-0600 credential files"
                )
        if not 1 <= args.timeout <= 120:
            raise FinalizerError("timeout must be between 1 and 120 seconds")
        if not 1 <= args.convergence_attempts <= 12:
            raise FinalizerError("convergence attempts must be between 1 and 12")
        if not 1 <= args.convergence_retry_seconds <= 10:
            raise FinalizerError("convergence retry must be between 1 and 10 seconds")
        root = _workspace(args.workspace)
        if args.resume_checkpoint is not None:
            if args.expected_checkpoint_sha256 is None:
                raise FinalizerError("--expected-checkpoint-sha256 is required for resume")
            checkpoint, files, _ = _load_checkpoint(
                args.resume_checkpoint, root, args.expected_checkpoint_sha256
            )
            checkpoint_path = args.resume_checkpoint.resolve(strict=True)
        else:
            checkpoint, files, checkpoint_path = _prepare_transaction(args, root)
        # Credential files are read only after every helper and transaction byte
        # has been pinned durably. Their values never enter argv, env, logs, or files.
        hub_token = _read_secret(args.hub_owner_token_file, root, "Hub owner token")
        registry_key = _read_secret(
            args.registry_control_key_file, root, "Registry control key"
        )
        try:
            _execute_transaction(
                checkpoint,
                files,
                checkpoint_path,
                root,
                hub_token,
                registry_key,
            )
        finally:
            hub_token = ""
            registry_key = ""
    except ReviewRequired as error:
        print(f"staged release remains review_required: {error}", file=sys.stderr)
        return 2
    except (FinalizerError, OSError, KeyError, TypeError, ValueError) as error:
        print(f"staged release owner finalization failed: {error}", file=sys.stderr)
        return 1
    print("staged_release_owner_finalization:preview_ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
