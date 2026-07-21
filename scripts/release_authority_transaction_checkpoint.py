#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Optional, Sequence
from urllib.parse import urlsplit, urlunsplit


SHA256 = re.compile(r"^[0-9a-f]{64}$")
GENERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_CHECKPOINT_BYTES = 256 * 1024
MAX_REQUEST_BYTES = 64 * 1024 * 1024
MAX_INPUT_BYTES = 8 * 1024 * 1024
CHECKPOINT_FIELDS = {
    "contractName",
    "contractVersion",
    "createdAtUtc",
    "state",
    "generationId",
    "releaseVersion",
    "registryCurrentUrl",
    "hubAuthorityAdvanceUrl",
    "liveConvergenceBaseUrl",
    "expectedManifestSha256",
    "expectedRegistrySnapshotSha256",
    "expectedRegistryDecisionSha256",
    "files",
    "evidenceDirectory",
    "convergencePolicy",
}
FILE_FIELDS = {
    "checkpointTool",
    "executedBootstrap",
    "request",
    "predecessorCurrent",
    "predecessorSnapshot",
    "predecessorDecision",
    "successorCurrent",
    "successorSnapshot",
    "successorDecision",
    "scorecard",
    "convergence",
    "responseVerifier",
    "registryInspector",
    "liveConvergenceVerifier",
}
REQUEST_FIELDS = {
    "generationId",
    "expectedShelfPointerSha256",
    "expectedShelfInventoryDigest",
    "predecessorCurrentBytes",
    "predecessorSnapshotBytes",
    "predecessorDecisionBytes",
    "successorCurrentBytes",
    "successorSnapshotBytes",
    "successorDecisionBytes",
    "scorecardBytes",
    "convergenceBytes",
}
REQUEST_FILE_BINDINGS = {
    "predecessorCurrentBytes": "predecessorCurrent",
    "predecessorSnapshotBytes": "predecessorSnapshot",
    "predecessorDecisionBytes": "predecessorDecision",
    "successorCurrentBytes": "successorCurrent",
    "successorSnapshotBytes": "successorSnapshot",
    "successorDecisionBytes": "successorDecision",
    "scorecardBytes": "scorecard",
    "convergenceBytes": "convergence",
}


class CheckpointError(ValueError):
    pass


def _args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or resolve one private Hub authority-transaction recovery checkpoint."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create")
    create.add_argument("--workspace", type=Path, required=True)
    create.add_argument("--executed-bootstrap", type=Path, required=True)
    create.add_argument("--generation-id", required=True)
    create.add_argument("--release-version", required=True)
    create.add_argument("--registry-current-url", required=True)
    create.add_argument("--hub-authority-advance-url", required=True)
    create.add_argument("--live-convergence-base-url", required=True)
    create.add_argument("--expected-manifest-sha256", required=True)
    create.add_argument("--request", type=Path, required=True)
    create.add_argument("--predecessor-current", type=Path, required=True)
    create.add_argument("--predecessor-snapshot", type=Path, required=True)
    create.add_argument("--predecessor-decision", type=Path, required=True)
    create.add_argument("--successor-current", type=Path, required=True)
    create.add_argument("--successor-snapshot", type=Path, required=True)
    create.add_argument("--successor-decision", type=Path, required=True)
    create.add_argument("--scorecard", type=Path, required=True)
    create.add_argument("--convergence", type=Path, required=True)
    create.add_argument("--response-verifier", type=Path, required=True)
    create.add_argument("--registry-inspector", type=Path, required=True)
    create.add_argument("--live-convergence-verifier", type=Path, required=True)
    create.add_argument("--evidence-directory", type=Path, required=True)
    create.add_argument("--convergence-timeout-seconds", type=int, required=True)
    create.add_argument("--convergence-attempts", type=int, required=True)
    create.add_argument("--convergence-retry-seconds", type=int, required=True)
    create.add_argument("--output", type=Path, required=True)

    resolve = commands.add_parser("resolve")
    resolve.add_argument("--workspace", type=Path, required=True)
    resolve.add_argument("--executed-bootstrap", type=Path, required=True)
    resolve.add_argument("--checkpoint", type=Path, required=True)
    resolve.add_argument("--expected-checkpoint-sha256", required=True)
    resolve.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        folded: set[str] = set()
        for key, value in pairs:
            casefolded = key.casefold()
            if casefolded in folded:
                raise CheckpointError(f"{label} contains duplicate or case-shadowed field {key}")
            folded.add(casefolded)
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CheckpointError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise CheckpointError(f"{label} must be a JSON object")
    return value


def _workspace(path: Path) -> Path:
    if not path.is_absolute():
        raise CheckpointError("authority recovery workspace must be absolute")
    try:
        root = path.resolve(strict=True)
        metadata = root.stat()
    except OSError as error:
        raise CheckpointError("authority recovery workspace is unavailable") from error
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise CheckpointError("authority recovery workspace must be a caller-owned directory")
    if metadata.st_mode & 0o022:
        raise CheckpointError("authority recovery workspace must not be group- or world-writable")
    return root


def _confined(path: Path, root: Path, label: str, *, must_exist: bool) -> Path:
    if not path.is_absolute():
        raise CheckpointError(f"{label} must be absolute")
    try:
        resolved = path.resolve(strict=must_exist)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise CheckpointError(f"{label} must stay beneath the authority recovery workspace") from error
    return resolved


def _stable_owned_file(
    path: Path,
    root: Path,
    label: str,
    maximum_bytes: int,
    *,
    exact_mode: Optional[int] = None,
) -> tuple[Path, bytes]:
    resolved = _confined(path, root, label, must_exist=True)
    try:
        path_metadata = os.lstat(resolved)
    except OSError as error:
        raise CheckpointError(f"{label} could not be inspected") from error
    if stat.S_ISLNK(path_metadata.st_mode):
        raise CheckpointError(f"{label} must not be a symbolic link")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError as error:
        raise CheckpointError(f"{label} could not be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise CheckpointError(f"{label} must be a single-link regular file")
        if before.st_uid != os.getuid() or before.st_mode & 0o022:
            raise CheckpointError(f"{label} must be caller-owned and not writable by other users")
        if exact_mode is not None and stat.S_IMODE(before.st_mode) != exact_mode:
            raise CheckpointError(f"{label} must have mode {exact_mode:04o}")
        if before.st_size < 1 or before.st_size > maximum_bytes:
            raise CheckpointError(f"{label} has an invalid byte length")
        remaining = before.st_size + 1
        chunks: list[bytes] = []
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
        raise CheckpointError(f"{label} changed during stable read")
    try:
        final_metadata = os.lstat(resolved)
    except OSError as error:
        raise CheckpointError(f"{label} changed during stable read") from error
    if (final_metadata.st_dev, final_metadata.st_ino) != (after.st_dev, after.st_ino):
        raise CheckpointError(f"{label} changed during stable read")
    return resolved, raw


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise CheckpointError(f"{label} must be canonical SHA-256")
    return value


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _from_relative(value: Any, root: Path, label: str, *, must_exist: bool) -> Path:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise CheckpointError(f"{label} must be a portable workspace-relative path")
    candidate = root.joinpath(*value.split("/"))
    return _confined(candidate, root, label, must_exist=must_exist)


def _https_url(value: str, expected_path: Optional[str], label: str) -> str:
    parsed = urlsplit(value.strip())
    try:
        _ = parsed.port
    except ValueError as error:
        raise CheckpointError(f"{label} has an invalid port") from error
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (expected_path is not None and parsed.path != expected_path)
    ):
        raise CheckpointError(f"{label} must be an explicit canonical HTTPS URL")
    return urlunsplit(("https", parsed.netloc, parsed.path, "", ""))


def _live_origin(value: str) -> str:
    canonical = _https_url(value, None, "live convergence base URL")
    parsed = urlsplit(canonical)
    if parsed.path not in {"", "/"}:
        raise CheckpointError("live convergence base URL must be an HTTPS origin")
    return urlunsplit(("https", parsed.netloc, "", "", ""))


def _decode(value: Any, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise CheckpointError(f"{label} must be canonical base64")
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise CheckpointError(f"{label} must be canonical base64") from error
    if base64.b64encode(raw).decode("ascii") != value:
        raise CheckpointError(f"{label} must be canonical base64")
    return raw


def _write_new(path: Path, root: Path, payload: dict[str, Any], label: str) -> None:
    resolved = _confined(path, root, label, must_exist=False)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    _confined(resolved.parent, root, f"{label} parent", must_exist=True)
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        with resolved.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise CheckpointError(f"{label} already exists") from error
    directory_fd = os.open(resolved.parent, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _file_entry(path: Path, root: Path, label: str, maximum: int, *, exact_mode: Optional[int] = None) -> tuple[dict[str, Any], bytes]:
    resolved, raw = _stable_owned_file(path, root, label, maximum, exact_mode=exact_mode)
    return {"path": _relative(resolved, root), "sha256": _sha(raw)}, raw


def _validate_request(
    request_raw: bytes,
    generation_id: str,
    file_raw: dict[str, bytes],
) -> dict[str, Any]:
    request = _strict_json(request_raw, "Hub authority request")
    if set(request) != REQUEST_FIELDS or request.get("generationId") != generation_id:
        raise CheckpointError("Hub authority request schema or generation binding is invalid")
    _require_sha(request.get("expectedShelfPointerSha256"), "request shelf pointer digest")
    inventory = request.get("expectedShelfInventoryDigest")
    if not isinstance(inventory, str) or not inventory.startswith("sha256:"):
        raise CheckpointError("request shelf inventory digest is invalid")
    _require_sha(inventory[7:], "request shelf inventory digest")
    for request_field, checkpoint_field in REQUEST_FILE_BINDINGS.items():
        if not hmac.compare_digest(
            _decode(request.get(request_field), request_field), file_raw[checkpoint_field]
        ):
            raise CheckpointError(f"Hub authority request {request_field} differs from its exact source bytes")
    return request


def _create(args: argparse.Namespace) -> dict[str, Any]:
    root = _workspace(args.workspace)
    generation_id = args.generation_id.strip()
    release_version = args.release_version.strip()
    if GENERATION_ID.fullmatch(generation_id) is None:
        raise CheckpointError("authority checkpoint generationId is invalid")
    if not release_version or len(release_version) > 128 or release_version != release_version.strip():
        raise CheckpointError("authority checkpoint releaseVersion is invalid")
    expected_manifest_sha256 = _require_sha(
        args.expected_manifest_sha256.strip(), "expected manifest digest"
    )
    live_origin = _live_origin(args.live_convergence_base_url)
    registry_url = _https_url(
        args.registry_current_url,
        "/api/v1/registry/release-authority/current",
        "Registry CURRENT URL",
    )
    hub_path = f"/api/internal/releases/generations/{generation_id}/authority-advances"
    hub_url = _https_url(args.hub_authority_advance_url, hub_path, "Hub authority advance URL")
    if urlsplit(hub_url).netloc.lower() != urlsplit(live_origin).netloc.lower():
        raise CheckpointError("Hub authority advance URL must share the live release origin")
    if not 1 <= args.convergence_timeout_seconds <= 120:
        raise CheckpointError("convergence timeout must be between 1 and 120 seconds")
    if not 1 <= args.convergence_attempts <= 12:
        raise CheckpointError("convergence attempts must be between 1 and 12")
    if not 1 <= args.convergence_retry_seconds <= 10:
        raise CheckpointError("convergence retry must be between 1 and 10 seconds")

    paths = {
        "checkpointTool": (Path(__file__), MAX_INPUT_BYTES, None),
        "executedBootstrap": (args.executed_bootstrap, MAX_INPUT_BYTES, None),
        "request": (args.request, MAX_REQUEST_BYTES, 0o600),
        "predecessorCurrent": (args.predecessor_current, MAX_INPUT_BYTES, None),
        "predecessorSnapshot": (args.predecessor_snapshot, MAX_INPUT_BYTES, None),
        "predecessorDecision": (args.predecessor_decision, MAX_INPUT_BYTES, None),
        "successorCurrent": (args.successor_current, MAX_INPUT_BYTES, None),
        "successorSnapshot": (args.successor_snapshot, MAX_INPUT_BYTES, None),
        "successorDecision": (args.successor_decision, MAX_INPUT_BYTES, None),
        "scorecard": (args.scorecard, MAX_INPUT_BYTES, None),
        "convergence": (args.convergence, MAX_INPUT_BYTES, None),
        "responseVerifier": (args.response_verifier, MAX_INPUT_BYTES, None),
        "registryInspector": (args.registry_inspector, MAX_INPUT_BYTES, None),
        "liveConvergenceVerifier": (args.live_convergence_verifier, MAX_INPUT_BYTES, None),
    }
    files: dict[str, dict[str, Any]] = {}
    file_raw: dict[str, bytes] = {}
    for name, (path, maximum, exact_mode) in paths.items():
        files[name], file_raw[name] = _file_entry(
            path, root, name, maximum, exact_mode=exact_mode
        )
    _validate_request(file_raw["request"], generation_id, file_raw)
    successor_current = _strict_json(file_raw["successorCurrent"], "successor CURRENT.json")
    successor_snapshot = _strict_json(file_raw["successorSnapshot"], "successor SNAPSHOT.json")
    successor_decision = _strict_json(file_raw["successorDecision"], "successor RELEASE_DECISION.json")
    if (
        successor_current.get("releaseVersion") != release_version
        or successor_snapshot.get("releaseVersion") != release_version
        or successor_decision.get("releaseVersion") != release_version
        or successor_current.get("status") != "preview_ready"
        or successor_snapshot.get("releaseDecisionStatus") != "preview_ready"
        or successor_decision.get("status") != "preview_ready"
        or successor_decision.get("releaseDecisionStatus") != "preview_ready"
        or successor_snapshot.get("manifestSha256") != expected_manifest_sha256
    ):
        raise CheckpointError("preview successor identity or manifest binding is invalid")
    expected_snapshot_sha256 = _sha(file_raw["successorSnapshot"])
    expected_decision_sha256 = _sha(file_raw["successorDecision"])
    if (
        successor_current.get("snapshotSha256") != expected_snapshot_sha256
        or successor_current.get("decisionSha256") != expected_decision_sha256
        or successor_snapshot.get("releaseDecisionSha256") != expected_decision_sha256
    ):
        raise CheckpointError("preview successor envelope digest binding is invalid")
    evidence_directory = _confined(
        args.evidence_directory, root, "release evidence directory", must_exist=True
    )
    if not evidence_directory.is_dir():
        raise CheckpointError("release evidence directory must be a directory")
    return {
        "contractName": "chummer.release-authority-transaction-checkpoint/v2",
        "contractVersion": 2,
        "createdAtUtc": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "state": "registry_preview_pending_or_published",
        "generationId": generation_id,
        "releaseVersion": release_version,
        "registryCurrentUrl": registry_url,
        "hubAuthorityAdvanceUrl": hub_url,
        "liveConvergenceBaseUrl": live_origin,
        "expectedManifestSha256": expected_manifest_sha256,
        "expectedRegistrySnapshotSha256": expected_snapshot_sha256,
        "expectedRegistryDecisionSha256": expected_decision_sha256,
        "files": files,
        "evidenceDirectory": _relative(evidence_directory, root),
        "convergencePolicy": {
            "timeoutSeconds": args.convergence_timeout_seconds,
            "attempts": args.convergence_attempts,
            "retrySeconds": args.convergence_retry_seconds,
        },
    }


def _resolve(args: argparse.Namespace) -> dict[str, Any]:
    root = _workspace(args.workspace)
    expected_checkpoint_sha256 = _require_sha(
        args.expected_checkpoint_sha256.strip(), "expected checkpoint digest"
    )
    checkpoint_path, checkpoint_raw = _stable_owned_file(
        args.checkpoint,
        root,
        "authority transaction checkpoint",
        MAX_CHECKPOINT_BYTES,
        exact_mode=0o600,
    )
    if not hmac.compare_digest(_sha(checkpoint_raw), expected_checkpoint_sha256):
        raise CheckpointError("authority transaction checkpoint SHA-256 does not match")
    checkpoint = _strict_json(checkpoint_raw, "authority transaction checkpoint")
    if set(checkpoint) != CHECKPOINT_FIELDS:
        raise CheckpointError("authority transaction checkpoint has an unexpected field set")
    generation_id = checkpoint.get("generationId")
    release_version = checkpoint.get("releaseVersion")
    if (
        checkpoint.get("contractName") != "chummer.release-authority-transaction-checkpoint/v2"
        or checkpoint.get("contractVersion") != 2
        or checkpoint.get("state") != "registry_preview_pending_or_published"
        or not isinstance(generation_id, str)
        or GENERATION_ID.fullmatch(generation_id) is None
        or not isinstance(release_version, str)
        or not release_version
        or len(release_version) > 128
    ):
        raise CheckpointError("authority transaction checkpoint identity is invalid")
    expected_manifest_sha256 = _require_sha(
        checkpoint.get("expectedManifestSha256"), "checkpoint manifest digest"
    )
    expected_snapshot_sha256 = _require_sha(
        checkpoint.get("expectedRegistrySnapshotSha256"), "checkpoint Registry snapshot digest"
    )
    expected_decision_sha256 = _require_sha(
        checkpoint.get("expectedRegistryDecisionSha256"), "checkpoint Registry decision digest"
    )
    registry_url = _https_url(
        str(checkpoint.get("registryCurrentUrl") or ""),
        "/api/v1/registry/release-authority/current",
        "checkpoint Registry CURRENT URL",
    )
    live_origin = _live_origin(str(checkpoint.get("liveConvergenceBaseUrl") or ""))
    hub_path = f"/api/internal/releases/generations/{generation_id}/authority-advances"
    hub_url = _https_url(
        str(checkpoint.get("hubAuthorityAdvanceUrl") or ""),
        hub_path,
        "checkpoint Hub authority advance URL",
    )
    if urlsplit(hub_url).netloc.lower() != urlsplit(live_origin).netloc.lower():
        raise CheckpointError("checkpoint Hub authority URL escaped the live release origin")

    file_entries = checkpoint.get("files")
    if not isinstance(file_entries, dict) or set(file_entries) != FILE_FIELDS:
        raise CheckpointError("authority transaction checkpoint file inventory is invalid")
    resolved_files: dict[str, str] = {}
    file_raw: dict[str, bytes] = {}
    for name in sorted(FILE_FIELDS):
        entry = file_entries.get(name)
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise CheckpointError(f"checkpoint {name} file entry is invalid")
        expected = _require_sha(entry.get("sha256"), f"checkpoint {name} digest")
        path = _from_relative(entry.get("path"), root, f"checkpoint {name}", must_exist=True)
        exact_mode = 0o600 if name == "request" else None
        maximum = MAX_REQUEST_BYTES if name == "request" else MAX_INPUT_BYTES
        resolved, raw = _stable_owned_file(
            path, root, f"checkpoint {name}", maximum, exact_mode=exact_mode
        )
        if not hmac.compare_digest(_sha(raw), expected):
            raise CheckpointError(f"checkpoint {name} SHA-256 changed")
        resolved_files[name] = str(resolved)
        file_raw[name] = raw
    own_path = Path(__file__).resolve(strict=True)
    if own_path != Path(resolved_files["checkpointTool"]):
        raise CheckpointError("checkpoint resolver is not the exact pinned checkpoint tool")
    executing_bootstrap, executing_bootstrap_raw = _stable_owned_file(
        args.executed_bootstrap,
        root,
        "executed bootstrap",
        MAX_INPUT_BYTES,
    )
    if (
        executing_bootstrap != Path(resolved_files["executedBootstrap"])
        or not hmac.compare_digest(
            _sha(executing_bootstrap_raw),
            _require_sha(
                file_entries["executedBootstrap"].get("sha256"),
                "checkpoint executed bootstrap digest",
            ),
        )
    ):
        raise CheckpointError("resume is not executing the exact checkpointed bootstrap bytes")
    _validate_request(file_raw["request"], generation_id, file_raw)

    successor_current = _strict_json(file_raw["successorCurrent"], "successor CURRENT.json")
    successor_snapshot = _strict_json(file_raw["successorSnapshot"], "successor SNAPSHOT.json")
    successor_decision = _strict_json(file_raw["successorDecision"], "successor RELEASE_DECISION.json")
    if (
        successor_current.get("releaseVersion") != release_version
        or successor_snapshot.get("releaseVersion") != release_version
        or successor_decision.get("releaseVersion") != release_version
        or successor_current.get("status") != "preview_ready"
        or successor_snapshot.get("releaseDecisionStatus") != "preview_ready"
        or successor_decision.get("releaseDecisionStatus") != "preview_ready"
        or successor_decision.get("status") != "preview_ready"
        or successor_snapshot.get("manifestSha256") != expected_manifest_sha256
        or _sha(file_raw["successorSnapshot"]) != expected_snapshot_sha256
        or _sha(file_raw["successorDecision"]) != expected_decision_sha256
    ):
        raise CheckpointError("checkpoint preview successor bytes no longer match its authority identity")

    policy = checkpoint.get("convergencePolicy")
    if not isinstance(policy, dict) or set(policy) != {
        "timeoutSeconds",
        "attempts",
        "retrySeconds",
    }:
        raise CheckpointError("checkpoint convergence policy is invalid")
    timeout = policy.get("timeoutSeconds")
    attempts = policy.get("attempts")
    retry = policy.get("retrySeconds")
    if (
        not isinstance(timeout, int)
        or isinstance(timeout, bool)
        or not 1 <= timeout <= 120
        or not isinstance(attempts, int)
        or isinstance(attempts, bool)
        or not 1 <= attempts <= 12
        or not isinstance(retry, int)
        or isinstance(retry, bool)
        or not 1 <= retry <= 10
    ):
        raise CheckpointError("checkpoint convergence policy is out of bounds")
    evidence_directory = _from_relative(
        checkpoint.get("evidenceDirectory"),
        root,
        "checkpoint evidence directory",
        must_exist=True,
    )
    if not evidence_directory.is_dir():
        raise CheckpointError("checkpoint evidence directory is not a directory")
    return {
        "contractName": "chummer.release-authority-transaction-resolution/v2",
        "status": "pass",
        "checkpointPath": str(checkpoint_path),
        "checkpointSha256": expected_checkpoint_sha256,
        "generationId": generation_id,
        "releaseVersion": release_version,
        "registryCurrentUrl": registry_url,
        "hubAuthorityAdvanceUrl": hub_url,
        "liveConvergenceBaseUrl": live_origin,
        "expectedManifestSha256": expected_manifest_sha256,
        "expectedRegistrySnapshotSha256": expected_snapshot_sha256,
        "expectedRegistryDecisionSha256": expected_decision_sha256,
        "executedBootstrapSha256": _sha(executing_bootstrap_raw),
        "files": resolved_files,
        "evidenceDirectory": str(evidence_directory),
        "convergencePolicy": policy,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _args(argv)
    try:
        root = _workspace(args.workspace)
        payload = _create(args) if args.command == "create" else _resolve(args)
        _write_new(args.output, root, payload, "authority transaction checkpoint output")
    except (CheckpointError, OSError) as error:
        print(f"release authority transaction checkpoint failed: {error}", file=sys.stderr)
        return 1
    if args.command == "create":
        raw = args.output.read_bytes()
        print(
            json.dumps(
                {
                    "checkpointPath": str(args.output.resolve(strict=True)),
                    "checkpointSha256": _sha(raw),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    else:
        print("release_authority_transaction_resolution:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
