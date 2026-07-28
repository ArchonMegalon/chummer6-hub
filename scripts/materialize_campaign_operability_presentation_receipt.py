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
from typing import Any, Sequence


SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
SAFE_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
EVIDENCE_IDS = {
    "desktop_visual",
    "desktop_workflow",
    "desktop_executable",
}
BINDING_FIELDS = {
    "authority_snapshot_sha256",
    "contract_name",
    "contract_version",
    "manifest_sha256",
    "platform",
    "primary_head",
    "registry_commit",
    "release_decision_sha256",
    "release_scope_decision_sha256",
    "release_version",
    "required_heads",
    "rid",
}
SCOPE_FIELDS = {
    "approvedAtUtc",
    "approvedBy",
    "channel",
    "contractName",
    "contractVersion",
    "decisionId",
    "platforms",
    "releaseTarget",
    "releaseVersion",
    "status",
    "supportOwner",
}
SCOPE_PLATFORM_FIELDS = {
    "artifactAccessClass",
    "fallbackHeads",
    "platform",
    "primaryHead",
    "rid",
    "signingRequirement",
}
HANDOFF_FIELDS = {
    "arch",
    "artifactAccessClass",
    "artifactId",
    "channel",
    "contractName",
    "downloadUrl",
    "head",
    "platform",
    "publicInstallRoute",
    "releaseScopeDecisionSha256",
    "releaseVersion",
    "rid",
    "sha256",
    "signingRequirement",
    "sizeBytes",
    "sourcePublicationState",
    "status",
}
ARTIFACT_IDENTITY_FIELDS = (
    "artifactId",
    "head",
    "platform",
    "rid",
    "arch",
    "downloadUrl",
    "sha256",
    "sizeBytes",
    "publicInstallRoute",
)


class ReceiptError(ValueError):
    pass


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize one exact candidate-bound campaign-operability "
            "Presentation receipt without modifying the immutable UI proof."
        )
    )
    parser.add_argument("--evidence-id", choices=sorted(EVIDENCE_IDS), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--allowed-source-root", type=Path, required=True)
    parser.add_argument("--release-scope-decision", type=Path, required=True)
    parser.add_argument("--expected-release-scope-sha256", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at-utc")
    return parser.parse_args(argv)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicate_or_case_shadowed(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        folded: set[str] = set()
        for key, value in pairs:
            normalized = key.casefold()
            if normalized in folded:
                raise ReceiptError(
                    f"{label} contains duplicate or case-shadowed field {key}"
                )
            folded.add(normalized)
            result[key] = value
        return result

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_or_case_shadowed,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReceiptError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ReceiptError(f"{label} must be a JSON object")
    return payload


def _read_file(path: Path, label: str, *, maximum_bytes: int) -> tuple[bytes, dict[str, Any]]:
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise ReceiptError(f"{label} is unavailable") from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size < 2
        or metadata.st_size > maximum_bytes
        or metadata.st_mode & 0o022
    ):
        raise ReceiptError(
            f"{label} must be a bounded single-link non-writable regular file"
        )
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ReceiptError(f"{label} could not be read") from error
    return raw, _strict_json(raw, label)


def _read_source(
    path: Path,
    allowed_root: Path,
    expected_sha256: str,
) -> tuple[bytes, dict[str, Any]]:
    if SHA256.fullmatch(expected_sha256) is None:
        raise ReceiptError("expected source SHA-256 is invalid")
    try:
        root = allowed_root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ReceiptError("source must stay beneath the explicit allowed root") from error
    raw, payload = _read_file(path, "source receipt", maximum_bytes=32 * 1024 * 1024)
    if not hmac.compare_digest(
        hashlib.sha256(raw).hexdigest(),
        expected_sha256,
    ):
        raise ReceiptError("source receipt SHA-256 does not match expected bytes")
    return raw, payload


def _canonical_scope(
    raw: bytes,
    payload: dict[str, Any],
    expected_sha256: str,
) -> tuple[str, list[dict[str, Any]]]:
    if (
        SHA256.fullmatch(expected_sha256) is None
        or hashlib.sha256(raw).hexdigest() != expected_sha256
        or set(payload) != SCOPE_FIELDS
        or payload.get("contractName") != "chummer.release-scope-decision/v1"
        or payload.get("contractVersion") != 1
        or payload.get("status") != "approved"
        or payload.get("channel") != "preview"
        or payload.get("releaseTarget") != "preview"
    ):
        raise ReceiptError("release-scope decision is not the exact approved candidate")
    canonical = (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    if raw != canonical:
        raise ReceiptError("release-scope decision is not canonical compact JSON plus LF")
    release_version = payload.get("releaseVersion")
    rows = payload.get("platforms")
    if (
        not isinstance(release_version, str)
        or SAFE_TOKEN.fullmatch(release_version) is None
        or not isinstance(rows, list)
        or not rows
        or any(not isinstance(row, dict) or set(row) != SCOPE_PLATFORM_FIELDS for row in rows)
    ):
        raise ReceiptError("release-scope decision candidate identity is invalid")
    return release_version, rows


def _timestamp(value: str | None) -> str:
    if value is None:
        return (
            dt.datetime.now(dt.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    if not value.endswith("Z"):
        raise ReceiptError("generated-at UTC must use canonical Z form")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ReceiptError("generated-at UTC is invalid") from error
    if parsed.utcoffset() != dt.timedelta(0):
        raise ReceiptError("generated-at UTC is invalid")
    return value


def _authority(
    *,
    manifest_raw: bytes,
    manifest: dict[str, Any],
    snapshot_raw: bytes,
    snapshot: dict[str, Any],
    snapshot_path: Path,
    decision_raw: bytes,
    decision: dict[str, Any],
    release_version: str,
    release_scope_sha256: str,
    scope_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    snapshot_sha256 = hashlib.sha256(snapshot_raw).hexdigest()
    decision_sha256 = hashlib.sha256(decision_raw).hexdigest()
    if (
        str(manifest.get("releaseVersion") or manifest.get("version") or "")
        != release_version
        or snapshot.get("authorityContract")
        != "chummer.release-authority-snapshot/v2"
        or snapshot.get("releaseVersion") != release_version
        or snapshot.get("manifestSha256") != manifest_sha256
        or snapshot.get("releaseDecisionSha256") != decision_sha256
        or snapshot.get("releaseDecisionStatus") != "review_required"
        or decision.get("contractName") != "chummer.preview-release-decision/v2"
        or decision.get("releaseVersion") != release_version
        or decision.get("releaseDecisionStatus") != "review_required"
        or decision.get("status") != "review_required"
        or decision.get("manifestSha256") != manifest_sha256
        or decision.get("releaseScopeDecisionSha256") != release_scope_sha256
    ):
        raise ReceiptError("Registry candidate authority bytes do not converge exactly")
    expected_tail = (
        "snapshots",
        release_version,
        snapshot_sha256,
        "SNAPSHOT.json",
    )
    if tuple(snapshot_path.resolve().parts[-4:]) != expected_tail:
        raise ReceiptError("Registry snapshot path does not bind its exact digest")
    registry_commit = snapshot.get("registryCommit")
    artifacts = snapshot.get("artifacts")
    handoff = decision.get("artifactHandoff")
    if (
        not isinstance(registry_commit, str)
        or GIT_SHA.fullmatch(registry_commit) is None
        or not isinstance(artifacts, list)
        or not artifacts
        or not isinstance(handoff, dict)
        or set(handoff) != HANDOFF_FIELDS
        or handoff.get("contractName")
        != "chummer.public-preview-byte-handoff/v1"
        or handoff.get("status") != "approved_public_preview_bytes"
        or handoff.get("sourcePublicationState") != "preview"
        or handoff.get("releaseVersion") != release_version
        or handoff.get("releaseScopeDecisionSha256") != release_scope_sha256
    ):
        raise ReceiptError("Registry public-preview byte handoff is invalid")
    scope_row = next(
        (
            row
            for row in scope_rows
            if row.get("platform") == handoff.get("platform")
        ),
        None,
    )
    matching_artifacts = [
        row
        for row in artifacts
        if isinstance(row, dict)
        and all(row.get(field) == handoff.get(field) for field in ARTIFACT_IDENTITY_FIELDS)
        and row.get("installAccessClass") == handoff.get("artifactAccessClass")
    ]
    if (
        scope_row is None
        or len(matching_artifacts) != 1
        or handoff.get("rid") != scope_row.get("rid")
        or handoff.get("head") != scope_row.get("primaryHead")
        or handoff.get("signingRequirement") != scope_row.get("signingRequirement")
        or handoff.get("artifactAccessClass")
        != scope_row.get("artifactAccessClass")
    ):
        raise ReceiptError("Registry public-preview bytes disagree with approved scope")
    return (
        {
            "manifestSha256": manifest_sha256,
            "snapshotSha256": snapshot_sha256,
            "decisionSha256": decision_sha256,
            "registryCommit": registry_commit,
        },
        scope_row,
        handoff,
    )


def _digest(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.removeprefix("sha256:")


def _source_artifact(
    evidence_id: str,
    payload: dict[str, Any],
    release_version: str,
    handoff: dict[str, Any],
) -> dict[str, Any]:
    expected = {
        "releaseVersion": release_version,
        "platform": handoff["platform"],
        "rid": handoff["rid"],
        "head": handoff["head"],
        "sha256": handoff["sha256"],
        "sizeBytes": handoff["sizeBytes"],
    }
    if evidence_id == "desktop_visual":
        valid = (
            payload.get("contractName")
            == "chummer6-ui.unsigned-preview-windows-installer-visual-proof"
            and payload.get("contractVersion") == 1
            and payload.get("status") == "passed"
            and payload.get("releaseVersion") == expected["releaseVersion"]
            and payload.get("platform") == expected["platform"]
            and payload.get("rid") == expected["rid"]
            and payload.get("head") == expected["head"]
            and _digest(payload.get("artifactDigest")) == expected["sha256"]
            and isinstance(payload.get("checks"), dict)
            and payload["checks"].get("accountable_review_confirmed") is True
            and payload["checks"].get("capture_mode") == "hosted_native_windows"
        )
        source_contract = payload.get("contractName")
    elif evidence_id == "desktop_executable":
        native = (
            payload.get("nativeHostEvidence")
            if isinstance(payload.get("nativeHostEvidence"), dict)
            else {}
        )
        valid = (
            payload.get("status") == "pass"
            and payload.get("releaseVersion") == expected["releaseVersion"]
            and payload.get("platform") == expected["platform"]
            and payload.get("rid") == expected["rid"]
            and payload.get("headId") == expected["head"]
            and _digest(payload.get("artifactDigest")) == expected["sha256"]
            and payload.get("artifactSha256") == expected["sha256"]
            and payload.get("artifactId") == handoff["artifactId"]
            and payload.get("executionEnvironment") == "native_windows"
            and native.get("status") == "verified"
            and native.get("isNativeWindows") is True
        )
        source_contract = "chummer6-ui.native-windows-startup-smoke/v1"
    else:
        inventory = (
            payload.get("candidateContentInventory")
            if isinstance(payload.get("candidateContentInventory"), dict)
            else {}
        )
        release = inventory.get("release") if isinstance(inventory.get("release"), dict) else {}
        files = inventory.get("files") if isinstance(inventory.get("files"), list) else []
        matching_files = [
            row
            for row in files
            if isinstance(row, dict)
            and row.get("sha256") == expected["sha256"]
            and row.get("sizeBytes") == expected["sizeBytes"]
            and row.get("path")
            == f"publication/files/{Path(handoff['downloadUrl']).name}"
        ]
        capture = payload.get("captureSource") if isinstance(payload.get("captureSource"), dict) else {}
        finalization = (
            payload.get("finalizationSource")
            if isinstance(payload.get("finalizationSource"), dict)
            else {}
        )
        valid = (
            payload.get("status") == "passed"
            and isinstance(payload.get("reviewer"), str)
            and bool(payload.get("reviewer"))
            and inventory.get("contractName")
            == "chummer6-ui.preview-nightly-unsigned-candidate-content-inventory"
            and inventory.get("contractVersion") == 1
            and inventory.get("platformScope") == f"{expected['platform']}_only"
            and release.get("version") == expected["releaseVersion"]
            and release.get("channel") == "preview"
            and len(matching_files) == 1
            and GIT_SHA.fullmatch(str(inventory.get("sourceSha") or "")) is not None
            and capture.get("sha") == inventory.get("sourceSha")
            and finalization.get("sha") == inventory.get("sourceSha")
        )
        source_contract = (
            "chummer6-ui.unsigned-preview-native-windows-finalized-evidence/v1"
        )
    if not valid:
        raise ReceiptError(
            f"{evidence_id} source does not prove the exact native candidate artifact"
        )
    return {
        **expected,
        "artifactId": handoff["artifactId"],
        "sourceContractName": source_contract,
    }


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def materialize(args: argparse.Namespace) -> dict[str, Any]:
    source_raw, source = _read_source(
        args.source,
        args.allowed_source_root,
        args.expected_source_sha256,
    )
    scope_raw, scope = _read_file(
        args.release_scope_decision,
        "release-scope decision",
        maximum_bytes=256 * 1024,
    )
    manifest_raw, manifest = _read_file(
        args.manifest,
        "release manifest",
        maximum_bytes=8 * 1024 * 1024,
    )
    snapshot_raw, snapshot = _read_file(
        args.snapshot,
        "Registry snapshot",
        maximum_bytes=8 * 1024 * 1024,
    )
    decision_raw, decision = _read_file(
        args.decision,
        "Registry decision",
        maximum_bytes=8 * 1024 * 1024,
    )
    release_version, scope_rows = _canonical_scope(
        scope_raw,
        scope,
        args.expected_release_scope_sha256,
    )
    authority, scope_row, handoff = _authority(
        manifest_raw=manifest_raw,
        manifest=manifest,
        snapshot_raw=snapshot_raw,
        snapshot=snapshot,
        snapshot_path=args.snapshot,
        decision_raw=decision_raw,
        decision=decision,
        release_version=release_version,
        release_scope_sha256=args.expected_release_scope_sha256,
        scope_rows=scope_rows,
    )
    source_artifact = _source_artifact(
        args.evidence_id,
        source,
        release_version,
        handoff,
    )
    binding = {
        "contract_name": "chummer6-ui.campaign_operability_candidate_binding",
        "contract_version": 1,
        "release_version": release_version,
        "release_scope_decision_sha256": args.expected_release_scope_sha256,
        "manifest_sha256": authority["manifestSha256"],
        "authority_snapshot_sha256": authority["snapshotSha256"],
        "release_decision_sha256": authority["decisionSha256"],
        "registry_commit": authority["registryCommit"],
        "platform": scope_row["platform"],
        "rid": scope_row["rid"],
        "primary_head": scope_row["primaryHead"],
        "required_heads": [
            scope_row["primaryHead"],
            *scope_row["fallbackHeads"],
        ],
    }
    if set(binding) != BINDING_FIELDS:
        raise ReceiptError("internal candidate binding field set drifted")
    return {
        "contractName": (
            "chummer6-ui.campaign-operability-presentation-receipt/v1"
        ),
        "contractVersion": 1,
        "generatedAtUtc": _timestamp(args.generated_at_utc),
        "status": "pass",
        "releaseVersion": release_version,
        "evidenceId": args.evidence_id,
        "sourceReceiptSha256": hashlib.sha256(source_raw).hexdigest(),
        "sourceArtifact": source_artifact,
        "campaign_operability_candidate_binding": binding,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _args(argv)
    try:
        payload = materialize(args)
        _write_new(args.output, payload)
    except (OSError, ReceiptError) as error:
        print(
            f"campaign operability Presentation receipt failed: {error}",
            file=sys.stderr,
        )
        return 1
    print(f"campaign_operability_presentation_receipt:{args.evidence_id}:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
