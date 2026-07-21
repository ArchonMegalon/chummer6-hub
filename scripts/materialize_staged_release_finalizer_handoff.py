#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Optional, Sequence
from urllib.parse import urlsplit, urlunsplit


SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SESSION_ID = re.compile(r"^[0-9a-f]{32}$")
MAX_INPUT_BYTES = 8 * 1024 * 1024


class HandoffError(ValueError):
    pass


def _args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize a secret-redacted handoff from a sealed Hub generation to "
            "the non-public owner finalizer. This command never activates CURRENT."
        )
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--stage-response", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--release-scope-decision", type=Path, required=True)
    parser.add_argument("--release-scope-verifier", type=Path, required=True)
    parser.add_argument("--release-scope-verification", type=Path, required=True)
    parser.add_argument("--promotion-evidence", type=Path, required=True)
    parser.add_argument("--release-scope-authority", required=True)
    parser.add_argument("--predecessor-current", type=Path, required=True)
    parser.add_argument("--predecessor-snapshot", type=Path, required=True)
    parser.add_argument("--predecessor-decision", type=Path, required=True)
    parser.add_argument("--staged-convergence", type=Path, required=True)
    parser.add_argument("--executed-bootstrap", type=Path, required=True)
    parser.add_argument("--owner-finalizer", type=Path, required=True)
    parser.add_argument("--scorecard-materializer", type=Path, required=True)
    parser.add_argument("--authority-advance-materializer", type=Path, required=True)
    parser.add_argument("--authority-advance-verifier", type=Path, required=True)
    parser.add_argument("--registry-current-inspector", type=Path, required=True)
    parser.add_argument("--live-convergence-verifier", type=Path, required=True)
    parser.add_argument("--registry-authority-materializer", type=Path, required=True)
    parser.add_argument("--registry-authority-verifier", type=Path, required=True)
    parser.add_argument("--registry-publish-materializer", type=Path, required=True)
    parser.add_argument("--registry-publish-verifier", type=Path, required=True)
    parser.add_argument("--registry-authority-library", type=Path, required=True)
    parser.add_argument("--sessions-url", required=True)
    parser.add_argument("--live-base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        folded: set[str] = set()
        for key, value in pairs:
            normalized = key.casefold()
            if normalized in folded:
                raise HandoffError(f"{label} contains duplicate or case-shadowed field {key}")
            folded.add(normalized)
            result[key] = value
        return result

    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HandoffError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise HandoffError(f"{label} must be a JSON object")
    return payload


def _workspace(path: Path) -> Path:
    if not path.is_absolute():
        raise HandoffError("finalizer workspace must be absolute")
    try:
        root = path.resolve(strict=True)
        metadata = root.stat()
    except OSError as error:
        raise HandoffError("finalizer workspace is unavailable") from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        raise HandoffError(
            "finalizer workspace must be caller-owned and not group- or world-writable"
        )
    return root


def _stable_file(path: Path, root: Path, label: str) -> tuple[Path, bytes]:
    if not path.is_absolute():
        raise HandoffError(f"{label} must be absolute")
    try:
        parent = path.parent.resolve(strict=True)
        parent.relative_to(root)
        resolved = parent / path.name
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise HandoffError(f"{label} must remain beneath the finalizer workspace") from error
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError as error:
        raise HandoffError(f"{label} could not be opened without following symlinks") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_mode & 0o022
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_INPUT_BYTES
        ):
            raise HandoffError(
                f"{label} must be a caller-owned single-link regular file not writable by other users"
            )
        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
        item.st_mode,
        item.st_nlink,
    )
    try:
        final = os.lstat(resolved)
    except OSError as error:
        raise HandoffError(f"{label} changed while it was read") from error
    if (
        identity(before) != identity(after)
        or len(raw) != before.st_size
        or stat.S_ISLNK(final.st_mode)
        or (final.st_dev, final.st_ino) != (after.st_dev, after.st_ino)
    ):
        raise HandoffError(f"{label} changed while it was read")
    return resolved, raw


def _entry(path: Path, raw: bytes, root: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise HandoffError(f"{label} must be canonical SHA-256")
    return value


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None or ".." in value:
        raise HandoffError(f"{label} is not a safe canonical identifier")
    return value


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HandoffError(f"{label} must be a canonical UTC timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as error:
        raise HandoffError(f"{label} must be a canonical UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise HandoffError(f"{label} must be a canonical UTC timestamp")
    return parsed.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _origin(value: str, label: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise HandoffError(f"{label} must be a canonical HTTPS origin")
    return urlunsplit(("https", parsed.netloc, "", "", ""))


def _sessions_url(value: str, live_origin: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/api/internal/releases/upload-sessions"
    ):
        raise HandoffError("upload sessions URL is not canonical HTTPS")
    result = urlunsplit(("https", parsed.netloc, parsed.path.rstrip("/"), "", ""))
    if urlsplit(result).netloc.lower() != urlsplit(live_origin).netloc.lower():
        raise HandoffError("upload sessions URL must share the live release origin")
    return result


def _write_new(path: Path, root: Path, payload: dict[str, Any]) -> None:
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(root)
        resolved.parent.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as error:
        raise HandoffError("finalizer handoff output must remain beneath the workspace") from error
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    try:
        with resolved.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise HandoffError("finalizer handoff output already exists") from error


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _args(argv)
    try:
        root = _workspace(args.workspace)
        session_id = args.session_id.strip()
        if SESSION_ID.fullmatch(session_id) is None:
            raise HandoffError("upload sessionId must be canonical lowercase 32-hex")
        paths: dict[str, Path] = {}
        raws: dict[str, bytes] = {}
        for name, source in {
            "stageResponse": args.stage_response,
            "manifest": args.manifest,
            "releaseScopeDecision": args.release_scope_decision,
            "releaseScopeVerifier": args.release_scope_verifier,
            "releaseScopeVerification": args.release_scope_verification,
            "promotionEvidence": args.promotion_evidence,
            "predecessorCurrent": args.predecessor_current,
            "predecessorSnapshot": args.predecessor_snapshot,
            "predecessorDecision": args.predecessor_decision,
            "stagedConvergence": args.staged_convergence,
            "executedBootstrap": args.executed_bootstrap,
            "ownerFinalizer": args.owner_finalizer,
            "scorecardMaterializer": args.scorecard_materializer,
            "authorityAdvanceMaterializer": args.authority_advance_materializer,
            "authorityAdvanceVerifier": args.authority_advance_verifier,
            "registryCurrentInspector": args.registry_current_inspector,
            "liveConvergenceVerifier": args.live_convergence_verifier,
            "registryAuthorityMaterializer": args.registry_authority_materializer,
            "registryAuthorityVerifier": args.registry_authority_verifier,
            "registryPublishMaterializer": args.registry_publish_materializer,
            "registryPublishVerifier": args.registry_publish_verifier,
            "registryAuthorityLibrary": args.registry_authority_library,
        }.items():
            paths[name], raws[name] = _stable_file(source, root, name)

        stage = _strict_json(raws["stageResponse"], "sanitized stage response")
        manifest = _strict_json(raws["manifest"], "canonical release manifest")
        scope_decision = _strict_json(
            raws["releaseScopeDecision"], "approved release scope decision"
        )
        scope_verification = _strict_json(
            raws["releaseScopeVerification"], "release scope verification"
        )
        predecessor_current = _strict_json(
            raws["predecessorCurrent"], "predecessor CURRENT.json"
        )
        predecessor_snapshot = _strict_json(
            raws["predecessorSnapshot"], "predecessor SNAPSHOT.json"
        )
        predecessor_decision = _strict_json(
            raws["predecessorDecision"], "predecessor RELEASE_DECISION.json"
        )
        convergence = _strict_json(
            raws["stagedConvergence"], "staged convergence receipt"
        )
        if stage.get("responseSanitized") is not True or "probeToken" in stage:
            raise HandoffError("stage response is not a secret-redacted sanitizer output")
        release_version = _safe_id(stage.get("version"), "staged release version")
        generation_id = _safe_id(stage.get("generationId"), "staged generationId")
        stage_receipt_id = _safe_id(stage.get("stageReceiptId"), "stageReceiptId")
        inventory_digest = stage.get("inventoryDigest")
        if (
            not isinstance(inventory_digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", inventory_digest) is None
        ):
            raise HandoffError("staged inventoryDigest is invalid")
        if stage.get("channel") != "preview":
            raise HandoffError("owner finalization is limited to a staged preview")
        previous_generation_id = stage.get("previousGenerationId")
        previous_pointer_sha256 = stage.get("previousPointerSha256")
        if (previous_generation_id is None) != (previous_pointer_sha256 is None):
            raise HandoffError("staged predecessor generation and pointer must be paired")
        if previous_generation_id is not None:
            _safe_id(previous_generation_id, "staged predecessor generationId")
            if (
                not isinstance(previous_pointer_sha256, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", previous_pointer_sha256)
                is None
            ):
                raise HandoffError("staged predecessor pointer digest is invalid")
        manifest_sha256 = _sha(raws["manifest"])
        if (
            manifest.get("version") != release_version
            or _require_sha(
                stage.get("canonicalManifestSha256"),
                "staged canonical manifest digest",
            )
            != manifest_sha256
        ):
            raise HandoffError("stage response does not bind the exact canonical manifest")
        scope_sha256 = _sha(raws["releaseScopeDecision"])
        scope_verification_sha256 = _sha(raws["releaseScopeVerification"])
        promotion_sha256 = _sha(raws["promotionEvidence"])
        scope_authority = args.release_scope_authority.strip()
        expected_scope_authority = (
            "design://release-scope/"
            f"{scope_decision.get('decisionId')}/sha256/{scope_sha256}"
        )
        if (
            scope_authority != expected_scope_authority
            or any(character.isspace() for character in scope_authority)
        ):
            raise HandoffError(
                "release scope authority must exactly bind decisionId and decision digest"
            )
        scope_rows = scope_verification.get("platforms")
        candidate_ids = stage.get("candidateArtifactIds")
        if (
            scope_decision.get("contractName") != "chummer.release-scope-decision/v1"
            or scope_decision.get("contractVersion") != 1
            or scope_decision.get("status") != "approved"
            or scope_verification.get("contractName")
            != "chummer.release-scope-verification/v1"
            or scope_verification.get("contractVersion") != 1
            or scope_verification.get("status") != "pass"
            or scope_verification.get("verificationPhase") != "candidate_inventory"
            or scope_verification.get("decisionSha256") != scope_sha256
            or scope_verification.get("decisionAuthority") != scope_authority
            or scope_verification.get("releaseVersion") != release_version
            or scope_verification.get("channel") != stage.get("channel")
            or scope_verification.get("manifestSha256") != manifest_sha256
            or scope_verification.get("promotionEvidenceSha256") != promotion_sha256
            or not isinstance(scope_rows, list)
            or not scope_rows
            or not isinstance(candidate_ids, list)
            or sorted(candidate_ids) != scope_verification.get("artifactIds")
            or stage.get("exactIncomingDesktopScope")
            != scope_verification.get("exactIncomingDesktopScope")
        ):
            raise HandoffError(
                "staged candidate does not bind the exact approved release scope and inventory"
            )
        snapshot_sha256 = _sha(raws["predecessorSnapshot"])
        decision_sha256 = _sha(raws["predecessorDecision"])
        if (
            predecessor_current.get("releaseVersion") != release_version
            or predecessor_current.get("status") != "review_required"
            or predecessor_current.get("snapshotSha256") != snapshot_sha256
            or predecessor_current.get("decisionSha256") != decision_sha256
            or predecessor_snapshot.get("releaseVersion") != release_version
            or predecessor_snapshot.get("releaseDecisionStatus") != "review_required"
            or predecessor_snapshot.get("releaseDecisionSha256") != decision_sha256
            or predecessor_decision.get("releaseVersion") != release_version
            or predecessor_decision.get("status") != "review_required"
            or predecessor_decision.get("releaseDecisionStatus") != "review_required"
        ):
            raise HandoffError("review-required predecessor authority envelope is inconsistent")
        truth = convergence.get("releaseTruth")
        if (
            convergence.get("contractName") != "chummer.live-release-convergence/v1"
            or convergence.get("contractVersion") != 1
            or convergence.get("verificationMode") != "staged_private"
            or convergence.get("status") != "pass"
            or convergence.get("mismatchCount") != 0
            or convergence.get("failureCount") != 0
            or convergence.get("releaseVersion") != release_version
            or convergence.get("manifestSha256") != manifest_sha256
            or convergence.get("authoritySnapshotSha256") != snapshot_sha256
            or convergence.get("releaseDecisionSha256") != decision_sha256
            or not isinstance(truth, dict)
            or truth.get("releaseVersion") != release_version
            or truth.get("manifestSha256") != manifest_sha256
            or truth.get("releaseDecisionSha256") != decision_sha256
        ):
            raise HandoffError("staged convergence does not bind the exact review candidate")
        probe_expires_at = _timestamp(
            stage.get("probeTokenExpiresAtUtc"), "probe grant expiry"
        )
        live_origin = _origin(args.live_base_url, "live release base URL")
        sessions_url = _sessions_url(args.sessions_url, live_origin)
        files = {
            name: _entry(paths[name], raws[name], root)
            for name in sorted(paths)
        }
        payload = {
            "contractName": "chummer.staged-release-finalizer-handoff/v1",
            "contractVersion": 1,
            "status": "review_required",
            "state": "awaiting_owner_finalization",
            "secretRedacted": True,
            "publicCurrentMutated": False,
            "sessionId": session_id,
            "stageReceiptId": stage_receipt_id,
            "generationId": generation_id,
            "releaseVersion": release_version,
            "channel": stage.get("channel"),
            "stageResponseSha256": _sha(raws["stageResponse"]),
            "targetPointerSha256": _require_sha(
                stage.get("targetPointerSha256"), "staged target pointer digest"
            ),
            "previousGenerationId": previous_generation_id,
            "previousPointerSha256": previous_pointer_sha256,
            "inventoryDigest": inventory_digest,
            "manifestSha256": manifest_sha256,
            "releaseScopeDecisionSha256": scope_sha256,
            "releaseScopeVerificationSha256": scope_verification_sha256,
            "releaseScopeAuthority": scope_authority,
            "exactIncomingDesktopScope": scope_verification.get(
                "exactIncomingDesktopScope"
            ),
            "supportOwner": scope_verification.get("supportOwner"),
            "releaseScopePlatforms": scope_rows,
            "predecessorSnapshotSha256": snapshot_sha256,
            "predecessorDecisionSha256": decision_sha256,
            "stagedConvergenceSha256": _sha(raws["stagedConvergence"]),
            "probeGrantExpiresAtUtc": probe_expires_at,
            "executedBootstrapSha256": _sha(raws["executedBootstrap"]),
            "stagedAuthorityUrl": (
                f"{live_origin}/api/internal/releases/stages/"
                f"{stage_receipt_id}/authority-advances"
            ),
            "activationUrl": (
                f"{sessions_url}/{session_id}/activate-staged"
            ),
            "liveBaseUrl": live_origin,
            "files": files,
        }
        rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if "probeToken" in rendered or "Authorization" in rendered:
            raise HandoffError("finalizer handoff unexpectedly contains credential material")
        _write_new(args.output, root, payload)
    except (HandoffError, OSError) as error:
        print(f"staged release finalizer handoff failed: {error}", file=sys.stderr)
        return 1
    print("staged_release_finalizer_handoff:review_required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
