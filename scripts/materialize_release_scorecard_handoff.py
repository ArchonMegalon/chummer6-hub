#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
SAFE_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,127}$")
MAX_SCORECARD_BYTES = 8 * 1024 * 1024
MAX_CONVERGENCE_BYTES = 4 * 1024 * 1024
MAX_BINDING_BYTES = 8 * 1024 * 1024
SCOPE_FIELDS = {
    "approvedAtUtc", "approvedBy", "channel", "contractName", "contractVersion",
    "decisionId", "platforms", "releaseTarget", "releaseVersion", "status",
    "supportOwner",
}
SCOPE_PLATFORM_FIELDS = {
    "artifactAccessClass", "fallbackHeads", "platform", "primaryHead", "rid",
    "signingRequirement",
}
CANDIDATE_EVIDENCE_FIELDS = {
    "authority_snapshot_sha256", "contract_name", "contract_version",
    "manifest_sha256", "registry_commit", "release_decision_sha256",
    "release_scope_decision_sha256", "release_version", "source_receipt_sha256",
}
PRESENTATION_CANDIDATE_BINDING_FIELDS = {
    "authority_snapshot_sha256", "contract_name", "contract_version",
    "manifest_sha256", "platform", "primary_head", "registry_commit",
    "release_decision_sha256", "release_scope_decision_sha256",
    "release_version", "required_heads", "rid",
}


class HandoffError(ValueError):
    pass


def _args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy one caller-owned, digest-pinned campaign-operability scorecard "
            "into release evidence after exact review-candidate convergence."
        )
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--allowed-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predecessor-snapshot", type=Path, required=True)
    parser.add_argument("--predecessor-decision", type=Path, required=True)
    parser.add_argument("--convergence", type=Path, required=True)
    parser.add_argument("--release-scope-decision", type=Path, required=True)
    parser.add_argument("--expected-release-scope-sha256", required=True)
    parser.add_argument("--ui-frame-receipt", type=Path, required=True)
    parser.add_argument("--desktop-visual-receipt", type=Path, required=True)
    parser.add_argument("--desktop-workflow-receipt", type=Path, required=True)
    parser.add_argument("--desktop-executable-receipt", type=Path, required=True)
    parser.add_argument("--expected-release-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser.parse_args(argv)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise HandoffError(f"{label} contains duplicate JSON field {key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HandoffError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise HandoffError(f"{label} must be a JSON object")
    return value


def _timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HandoffError(f"{label} must be a canonical UTC timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as error:
        raise HandoffError(f"{label} must be a canonical UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise HandoffError(f"{label} must be a canonical UTC timestamp")
    return parsed.astimezone(dt.timezone.utc)


def _stable_owned_file(path: Path, allowed_root: Path, maximum_bytes: int) -> bytes:
    try:
        root = allowed_root.resolve(strict=True)
        root_metadata = root.stat()
    except OSError as error:
        raise HandoffError("allowed scorecard root is unavailable") from error
    if not stat.S_ISDIR(root_metadata.st_mode) or root_metadata.st_uid != os.getuid():
        raise HandoffError("allowed scorecard root must be a caller-owned directory")
    if root_metadata.st_mode & 0o022:
        raise HandoffError("allowed scorecard root must not be group- or world-writable")

    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise HandoffError("scorecard source must stay beneath the caller-owned run workspace") from error
    try:
        path_metadata = os.lstat(path)
    except OSError as error:
        raise HandoffError("scorecard source is unavailable") from error
    if stat.S_ISLNK(path_metadata.st_mode):
        raise HandoffError("scorecard source must not be a symbolic link")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise HandoffError("scorecard source could not be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise HandoffError("scorecard source must be a single-link regular file")
        if before.st_uid != os.getuid():
            raise HandoffError("scorecard source must be owned by the current caller")
        if before.st_mode & 0o022:
            raise HandoffError("scorecard source must not be group- or world-writable")
        if before.st_size < 1 or before.st_size > maximum_bytes:
            raise HandoffError("scorecard source has an invalid byte length")
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
        raise HandoffError("scorecard source changed during stable read")
    try:
        final_path_metadata = os.lstat(path)
    except OSError as error:
        raise HandoffError("scorecard source changed during stable read") from error
    if (final_path_metadata.st_dev, final_path_metadata.st_ino) != (
        after.st_dev,
        after.st_ino,
    ):
        raise HandoffError("scorecard source changed during stable read")
    return raw


def _bounded_json_file(path: Path, label: str, maximum_bytes: int) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise HandoffError(f"{label} could not be read") from error
    if not raw or len(raw) > maximum_bytes:
        raise HandoffError(f"{label} has an invalid byte length")
    return raw, _strict_json(raw, label)


def _validate_exact_release_bindings(
    manifest_raw: bytes,
    manifest: dict[str, Any],
    snapshot_raw: bytes,
    snapshot: dict[str, Any],
    decision_raw: bytes,
    decision: dict[str, Any],
    convergence_payload: dict[str, Any],
    release_version: str,
) -> dict[str, Any]:
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    snapshot_sha256 = hashlib.sha256(snapshot_raw).hexdigest()
    decision_sha256 = hashlib.sha256(decision_raw).hexdigest()
    if manifest.get("version") != release_version:
        raise HandoffError("canonical release manifest does not bind the expected release version")
    if (
        snapshot.get("releaseVersion") != release_version
        or snapshot.get("releaseDecisionStatus") != "review_required"
        or snapshot.get("releaseDecisionSha256") != decision_sha256
        or decision.get("releaseVersion") != release_version
        or decision.get("releaseDecisionStatus") != "review_required"
        or decision.get("status") != "review_required"
    ):
        raise HandoffError("predecessor authority is not the exact review-required release seed")
    support_owner = snapshot.get("supportOwner")
    next_actions = snapshot.get("nextActions")
    authority_manifest_sha256 = snapshot.get("manifestSha256")
    registry_commit = snapshot.get("registryCommit")
    if (
        not isinstance(support_owner, str)
        or SAFE_TOKEN.fullmatch(support_owner) is None
        or not isinstance(next_actions, list)
        or not next_actions
        or any(not isinstance(action, str) or not action.strip() for action in next_actions)
        or not isinstance(authority_manifest_sha256, str)
        or SHA256.fullmatch(authority_manifest_sha256) is None
        or authority_manifest_sha256 != manifest_sha256
        or not isinstance(registry_commit, str)
        or GIT_SHA.fullmatch(registry_commit) is None
    ):
        raise HandoffError("predecessor authority lacks candidate evidence owner/action bindings")
    truth = convergence_payload.get("releaseTruth")
    if (
        convergence_payload.get("releaseVersion") != release_version
        or convergence_payload.get("manifestSha256") != manifest_sha256
        or convergence_payload.get("authoritySnapshotSha256") != snapshot_sha256
        or convergence_payload.get("releaseDecisionSha256") != decision_sha256
        or not isinstance(truth, dict)
        or truth.get("releaseVersion") != release_version
        or truth.get("manifestSha256") != manifest_sha256
        or truth.get("releaseDecisionSha256") != decision_sha256
    ):
        raise HandoffError("staged convergence does not bind the exact candidate authority")
    return {
        "manifestSha256": manifest_sha256,
        "predecessorSnapshotSha256": snapshot_sha256,
        "predecessorDecisionSha256": decision_sha256,
        "authorityManifestSha256": authority_manifest_sha256,
        "predecessorSupportOwner": support_owner,
        "predecessorNextActions": next_actions,
        "registryCommit": registry_commit,
    }


def _validate_convergence(payload: dict[str, Any], release_version: str) -> dt.datetime:
    if (
        payload.get("contractName") != "chummer.live-release-convergence/v1"
        or payload.get("contractVersion") != 1
        or payload.get("status") != "pass"
        or payload.get("mismatchCount") != 0
        or payload.get("failureCount") != 0
        or payload.get("mismatches") != []
        or payload.get("failures") != []
        or payload.get("releaseDecisionStatus") != "review_required"
    ):
        raise HandoffError("staged convergence receipt is not an exact zero-failure review candidate")
    truth = payload.get("releaseTruth")
    if (
        not isinstance(truth, dict)
        or truth.get("releaseVersion") != release_version
        or truth.get("releaseDecisionStatus") != "review_required"
        or truth.get("releaseDecisionSha256") != payload.get("releaseDecisionSha256")
    ):
        raise HandoffError("staged convergence receipt does not bind the expected review candidate")
    return _timestamp(payload.get("generatedAtUtc"), "convergence generatedAtUtc")


def _validate_scorecard(
    payload: dict[str, Any],
    convergence_at: dt.datetime,
    release_version: str,
    release_scope_sha256: str,
    exact_bindings: dict[str, Any],
    release_scope: dict[str, Any],
    ui_frame_receipt_sha256: str,
    presentation_receipt_sha256: dict[str, str],
) -> dt.datetime:
    summary = payload.get("summary")
    cells = payload.get("cells")
    if (
        payload.get("contract_name") != "chummer.campaign_operability_scorecard"
        or payload.get("contract_version") != 2
        or payload.get("release_version") != release_version
        or payload.get("release_scope_decision_sha256") != release_scope_sha256
        or payload.get("releaseVersion") != release_version
        or payload.get("releaseScopeDecisionSha256") != release_scope_sha256
        or payload.get("snapshotSha256")
        != exact_bindings["predecessorSnapshotSha256"]
        or payload.get("manifestSha256")
        != exact_bindings["authorityManifestSha256"]
        or payload.get("releaseDecisionSha256")
        != exact_bindings["predecessorDecisionSha256"]
        or payload.get("preview_status") != "pass"
        or payload.get("preview_verdict") != "CAMPAIGN_OPERABILITY_PREVIEW_READY"
        or payload.get("preview_failures") != []
        or not isinstance(summary, dict)
        or summary.get("cell_count") != 36
        or summary.get("at_least_2_count") != 36
        or summary.get("below_2_count") != 0
        or summary.get("minimum_score") not in {2, 3}
        or not isinstance(cells, list)
        or len(cells) != 36
    ):
        raise HandoffError("scorecard is not a generated v2 36-cell preview-ready artifact")
    registry_review_seed_count = 0
    candidate_bound_ui_frame_count = 0
    presentation_counts = {evidence_id: 0 for evidence_id in presentation_receipt_sha256}
    for cell in cells:
        if not isinstance(cell, dict):
            raise HandoffError(
                "scorecard is not a generated v2 36-cell preview-ready artifact"
            )
        evidence_rows = cell.get("evidence")
        if not isinstance(evidence_rows, list) or not evidence_rows:
            raise HandoffError(
                "scorecard preview cells must carry candidate-bound evidence rows"
            )
        for row in evidence_rows:
            if not isinstance(row, dict) or row.get("score") not in {2, 3}:
                raise HandoffError(
                    "scorecard preview cells contain an invalid evidence score"
                )
            row_id = row.get("id")
            source_sha256 = row.get("source_sha256")
            if (
                not isinstance(row_id, str)
                or SAFE_TOKEN.fullmatch(row_id) is None
                or not isinstance(source_sha256, str)
                or SHA256.fullmatch(source_sha256) is None
            ):
                raise HandoffError("scorecard evidence row lacks canonical id/source bindings")
            if row.get("score") == 3:
                candidate_evidence = row.get("candidate_evidence")
                expected_candidate = {
                    "contract_name": "chummer.campaign-operability-candidate-evidence/v1",
                    "contract_version": 1,
                    "release_version": release_version,
                    "release_scope_decision_sha256": release_scope_sha256,
                    "manifest_sha256": exact_bindings["authorityManifestSha256"],
                    "authority_snapshot_sha256": exact_bindings[
                        "predecessorSnapshotSha256"
                    ],
                    "release_decision_sha256": exact_bindings[
                        "predecessorDecisionSha256"
                    ],
                    "registry_commit": exact_bindings["registryCommit"],
                    "source_receipt_sha256": source_sha256,
                }
                if (
                    row.get("source_release_version") != release_version
                    or not isinstance(candidate_evidence, dict)
                    or set(candidate_evidence) != CANDIDATE_EVIDENCE_FIELDS
                    or candidate_evidence != expected_candidate
                ):
                    raise HandoffError(
                        "scorecard score-3 evidence does not bind the exact release candidate"
                    )
                if row_id == "ui_frame":
                    if (
                        row.get("source_status") != "pass"
                        or row.get("source_verdict") != "PASS"
                        or source_sha256 != ui_frame_receipt_sha256
                    ):
                        raise HandoffError(
                            "scorecard UI-frame receipt does not bind the staged UI receipt bytes"
                        )
                    candidate_bound_ui_frame_count += 1
                if row_id in presentation_receipt_sha256:
                    if (
                        row.get("source_status") != "pass"
                        or source_sha256 != presentation_receipt_sha256[row_id]
                    ):
                        raise HandoffError(
                            "scorecard Presentation evidence does not bind the pinned candidate receipt bytes"
                        )
                    presentation_counts[row_id] += 1
                continue
            preview_evidence = row.get("preview_evidence")
            proof = (
                preview_evidence.get("proof")
                if isinstance(preview_evidence, dict)
                else None
            )
            if (
                not isinstance(proof, dict)
                or not isinstance(preview_evidence, dict)
                or preview_evidence.get("source_receipt_sha256") != source_sha256
                or proof.get("release_version") != release_version
                or proof.get("release_scope_decision_sha256")
                != release_scope_sha256
            ):
                raise HandoffError(
                    "scorecard score-2 proof does not bind the exact release candidate"
                )
            if preview_evidence.get("provenance_kind") == "registry_review_seed":
                registry_review_seed_count += 1
                if (
                    row_id != "release_channel"
                    or "source_verdict" not in row
                    or source_sha256
                    != exact_bindings["predecessorSnapshotSha256"]
                    or proof.get("bounded_owner")
                    != exact_bindings["predecessorSupportOwner"]
                    or proof.get("bounded_owner") != release_scope["supportOwner"]
                    or proof.get("next_actions")
                    != exact_bindings["predecessorNextActions"]
                    or row.get("bounded_owner") != proof.get("bounded_owner")
                    or row.get("next_actions") != proof.get("next_actions")
                    or not hmac.compare_digest(
                        str(proof.get("authority_snapshot_sha256") or ""),
                        exact_bindings["predecessorSnapshotSha256"],
                    )
                ):
                    raise HandoffError(
                        "scorecard Registry proof does not bind release_channel predecessor/scope data"
                    )
            elif preview_evidence.get("provenance_kind") == "approved_scope_exclusion":
                if (
                    row_id != "windows_visual"
                    or "source_verdict" not in row
                    or "windows" in release_scope["platforms"]
                    or proof.get("excluded_platform") != "windows"
                    or proof.get("evidence_id") != "windows_visual"
                    or proof.get("bounded_owner") != release_scope["supportOwner"]
                    or row.get("bounded_owner") != proof.get("bounded_owner")
                    or row.get("next_actions") != proof.get("next_actions")
                ):
                    raise HandoffError(
                        "scorecard approved-scope exclusion does not bind windows_visual scope data"
                    )
    if registry_review_seed_count == 0:
        raise HandoffError(
            "scorecard omits the exact candidate Registry review-seed proof"
        )
    if candidate_bound_ui_frame_count == 0:
        raise HandoffError(
            "scorecard omits the exact candidate-bound UI-frame receipt"
        )
    if any(count == 0 for count in presentation_counts.values()):
        raise HandoffError(
            "scorecard omits one or more exact candidate-bound Presentation receipts"
        )
    generated_at = _timestamp(payload.get("generated_at_utc"), "scorecard generated_at_utc")
    if generated_at < convergence_at:
        raise HandoffError("scorecard must be materialized after review-candidate convergence")
    now = dt.datetime.now(dt.timezone.utc)
    if generated_at > now + dt.timedelta(minutes=5):
        raise HandoffError("scorecard generated_at_utc is unreasonably in the future")
    return generated_at


def _validate_ui_frame_receipt(
    raw: bytes,
    payload: dict[str, Any],
    release_version: str,
    release_scope_sha256: str,
    exact_bindings: dict[str, Any],
) -> str:
    candidate = payload.get("candidate_binding")
    if (
        payload.get("contract_name") != "chummer.ui-frame-integrity/v2"
        or payload.get("contract_version") != 2
        or payload.get("status") != "pass"
        or payload.get("verdict") != "READY"
        or payload.get("request_methods") != ["GET"]
        or payload.get("failures") != []
        or payload.get("release_version") != release_version
        or payload.get("manifest_sha256")
        != exact_bindings["authorityManifestSha256"]
        or payload.get("authority_snapshot_sha256")
        != exact_bindings["predecessorSnapshotSha256"]
        or payload.get("release_decision_sha256")
        != exact_bindings["predecessorDecisionSha256"]
        or payload.get("release_scope_decision_sha256") != release_scope_sha256
        or not isinstance(candidate, dict)
        or candidate.get("release_version") != release_version
        or candidate.get("manifest_sha256")
        != exact_bindings["authorityManifestSha256"]
        or candidate.get("authority_snapshot_sha256")
        != exact_bindings["predecessorSnapshotSha256"]
        or candidate.get("release_decision_sha256")
        != exact_bindings["predecessorDecisionSha256"]
        or candidate.get("release_scope_decision_sha256") != release_scope_sha256
        or candidate.get("verification_mode") != "staged_private"
    ):
        raise HandoffError(
            "UI-frame receipt is not the exact successful staged release candidate proof"
        )
    return hashlib.sha256(raw).hexdigest()


def _validate_presentation_receipt(
    raw: bytes,
    payload: dict[str, Any],
    evidence_id: str,
    release_version: str,
    release_scope_sha256: str,
    exact_bindings: dict[str, Any],
    release_scope: dict[str, Any],
) -> str:
    binding = payload.get("campaign_operability_candidate_binding")
    release_aliases = [
        payload[name]
        for name in ("releaseVersion", "release_version")
        if name in payload
    ]
    if (
        payload.get("status") != "pass"
        or not release_aliases
        or any(value != release_version for value in release_aliases)
        or not isinstance(binding, dict)
        or set(binding) != PRESENTATION_CANDIDATE_BINDING_FIELDS
    ):
        raise HandoffError(
            f"{evidence_id} is not an exact passing Presentation candidate receipt"
        )
    platform = binding.get("platform")
    scope_row = next(
        (
            row
            for row in release_scope["platformRows"]
            if row.get("platform") == platform
        ),
        None,
    )
    if scope_row is None:
        raise HandoffError(f"{evidence_id} binds a platform outside approved scope")
    expected = {
        "contract_name": "chummer6-ui.campaign_operability_candidate_binding",
        "contract_version": 1,
        "release_version": release_version,
        "release_scope_decision_sha256": release_scope_sha256,
        "manifest_sha256": exact_bindings["authorityManifestSha256"],
        "authority_snapshot_sha256": exact_bindings["predecessorSnapshotSha256"],
        "release_decision_sha256": exact_bindings["predecessorDecisionSha256"],
        "registry_commit": exact_bindings["registryCommit"],
        "platform": platform,
        "rid": scope_row["rid"],
        "primary_head": scope_row["primaryHead"],
        "required_heads": [scope_row["primaryHead"], *scope_row["fallbackHeads"]],
    }
    if binding != expected:
        raise HandoffError(
            f"{evidence_id} Presentation candidate binding does not match approved bytes"
        )
    return hashlib.sha256(raw).hexdigest()


def _validate_release_scope(
    raw: bytes,
    payload: dict[str, Any],
    expected_sha256: str,
    release_version: str,
) -> dict[str, Any]:
    observed_sha256 = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(observed_sha256, expected_sha256):
        raise HandoffError(
            "release-scope decision SHA-256 does not match the staged handoff"
        )
    canonical = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    if raw != canonical:
        raise HandoffError(
            "release-scope decision bytes are not canonical compact sorted UTF-8 JSON plus LF"
        )
    if set(payload) != SCOPE_FIELDS or (
        payload.get("contractName") != "chummer.release-scope-decision/v1"
        or payload.get("contractVersion") != 1
        or payload.get("status") != "approved"
        or payload.get("channel") != "preview"
        or payload.get("releaseTarget") != "preview"
        or payload.get("releaseVersion") != release_version
    ):
        raise HandoffError(
            "release-scope decision is not the exact approved candidate binding"
        )
    support_owner = payload.get("supportOwner")
    decision_id = payload.get("decisionId")
    if any(
        not isinstance(value, str)
        or SAFE_TOKEN.fullmatch(value) is None
        or ".." in value
        for value in (support_owner, decision_id)
    ):
        raise HandoffError("release-scope decision owner/id is not canonical")
    if not isinstance(payload.get("approvedBy"), str) or not payload["approvedBy"].strip():
        raise HandoffError("release-scope decision approving authority is unresolved")
    approved_at = _timestamp(payload.get("approvedAtUtc"), "release-scope approvedAtUtc")
    if approved_at.isoformat(timespec="seconds").replace("+00:00", "Z") != payload.get(
        "approvedAtUtc"
    ):
        raise HandoffError("release-scope approvedAtUtc must use exact UTC seconds")
    rows = payload.get("platforms")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 16:
        raise HandoffError("release-scope decision platform inventory is missing")
    platforms: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != SCOPE_PLATFORM_FIELDS:
            raise HandoffError("release-scope platform row has an unexpected field set")
        platform = row.get("platform")
        rid = row.get("rid")
        allowed_rids = {
            "linux": {"linux-x64", "linux-arm64"},
            "macos": {"osx-x64", "osx-arm64"},
            "windows": {"win-x64", "win-arm64"},
        }
        primary = row.get("primaryHead")
        fallbacks = row.get("fallbackHeads")
        if (
            platform not in allowed_rids
            or rid not in allowed_rids[platform]
            or primary not in {"avalonia", "blazor-desktop"}
            or not isinstance(fallbacks, list)
            or fallbacks != sorted(fallbacks)
            or len(fallbacks) != len(set(fallbacks))
            or primary in fallbacks
            or any(value not in {"avalonia", "blazor-desktop"} for value in fallbacks)
            or row.get("artifactAccessClass")
            not in {"open_public", "account_required", "support_directed"}
            or row.get("signingRequirement")
            not in {"signed", "preview_unsigned_allowed", "not_applicable"}
        ):
            raise HandoffError("release-scope platform policy is unsupported")
        platforms.append(platform)
    if platforms != sorted(platforms) or len(platforms) != len(set(platforms)):
        raise HandoffError("release-scope platforms must be sorted and unique")
    return {
        "supportOwner": support_owner,
        "platforms": set(platforms),
        "platformRows": rows,
    }


def _write_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise HandoffError(f"output already exists: {path.name}") from error


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _args(argv)
    try:
        expected = args.expected_sha256.strip()
        if SHA256.fullmatch(expected) is None:
            raise HandoffError("expected scorecard SHA-256 must be 64 lowercase hexadecimal characters")
        release_version = args.expected_release_version.strip()
        if not release_version or len(release_version) > 128:
            raise HandoffError("expected release version is invalid")
        release_scope_sha256 = args.expected_release_scope_sha256.strip()
        if SHA256.fullmatch(release_scope_sha256) is None:
            raise HandoffError(
                "expected release-scope SHA-256 must be 64 lowercase hexadecimal characters"
            )

        convergence_raw, convergence = _bounded_json_file(
            args.convergence, "convergence receipt", MAX_CONVERGENCE_BYTES
        )
        convergence_at = _validate_convergence(convergence, release_version)
        manifest_raw, manifest = _bounded_json_file(
            args.manifest, "canonical release manifest", MAX_BINDING_BYTES
        )
        snapshot_raw, snapshot = _bounded_json_file(
            args.predecessor_snapshot, "predecessor authority snapshot", MAX_BINDING_BYTES
        )
        decision_raw, decision = _bounded_json_file(
            args.predecessor_decision, "predecessor authority decision", MAX_BINDING_BYTES
        )
        exact_bindings = _validate_exact_release_bindings(
            manifest_raw,
            manifest,
            snapshot_raw,
            snapshot,
            decision_raw,
            decision,
            convergence,
            release_version,
        )
        release_scope_raw, release_scope = _bounded_json_file(
            args.release_scope_decision,
            "approved release-scope decision",
            MAX_BINDING_BYTES,
        )
        release_scope_binding = _validate_release_scope(
            release_scope_raw,
            release_scope,
            release_scope_sha256,
            release_version,
        )
        ui_frame_raw, ui_frame_payload = _bounded_json_file(
            args.ui_frame_receipt,
            "candidate-bound UI-frame receipt",
            MAX_BINDING_BYTES,
        )
        ui_frame_receipt_sha256 = _validate_ui_frame_receipt(
            ui_frame_raw,
            ui_frame_payload,
            release_version,
            release_scope_sha256,
            exact_bindings,
        )
        presentation_receipt_sha256: dict[str, str] = {}
        for evidence_id, path in {
            "desktop_visual": args.desktop_visual_receipt,
            "desktop_workflow": args.desktop_workflow_receipt,
            "desktop_executable": args.desktop_executable_receipt,
        }.items():
            raw, payload = _bounded_json_file(
                path,
                f"candidate-bound {evidence_id} Presentation receipt",
                MAX_BINDING_BYTES,
            )
            presentation_receipt_sha256[evidence_id] = _validate_presentation_receipt(
                raw,
                payload,
                evidence_id,
                release_version,
                release_scope_sha256,
                exact_bindings,
                release_scope_binding,
            )
        if len(set(presentation_receipt_sha256.values())) != 3:
            raise HandoffError(
                "Presentation visual, workflow, and executable receipts must be distinct raw artifacts"
            )
        scorecard_raw = _stable_owned_file(
            args.source, args.allowed_root, MAX_SCORECARD_BYTES
        )
        observed = hashlib.sha256(scorecard_raw).hexdigest()
        if not hmac.compare_digest(observed, expected):
            raise HandoffError("scorecard SHA-256 does not match the immutable handoff")
        scorecard = _strict_json(scorecard_raw, "scorecard")
        scorecard_at = _validate_scorecard(
            scorecard,
            convergence_at,
            release_version,
            release_scope_sha256,
            exact_bindings,
            release_scope_binding,
            ui_frame_receipt_sha256,
            presentation_receipt_sha256,
        )

        receipt = {
            "contractName": "chummer.release-scorecard-handoff/v3",
            "status": "pass",
            "releaseVersion": release_version,
            "releaseScopeDecisionSha256": release_scope_sha256,
            "manifestSha256": exact_bindings["manifestSha256"],
            "predecessorSnapshotSha256": exact_bindings[
                "predecessorSnapshotSha256"
            ],
            "predecessorDecisionSha256": exact_bindings[
                "predecessorDecisionSha256"
            ],
            "registryCommit": exact_bindings["registryCommit"],
            "uiFrameReceiptSha256": ui_frame_receipt_sha256,
            "desktopVisualReceiptSha256": presentation_receipt_sha256[
                "desktop_visual"
            ],
            "desktopWorkflowReceiptSha256": presentation_receipt_sha256[
                "desktop_workflow"
            ],
            "desktopExecutableReceiptSha256": presentation_receipt_sha256[
                "desktop_executable"
            ],
            "scorecardSha256": observed,
            "stagedConvergenceSha256": hashlib.sha256(convergence_raw).hexdigest(),
            "scorecardGeneratedAtUtc": scorecard_at.isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            ),
            "convergenceGeneratedAtUtc": convergence_at.isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            ),
        }
        receipt_raw = (
            json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        _write_new(args.output, scorecard_raw)
        _write_new(args.receipt, receipt_raw)
    except (HandoffError, OSError) as error:
        print(f"release scorecard handoff failed: {error}", file=sys.stderr)
        return 1
    print("release_scorecard_handoff:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
