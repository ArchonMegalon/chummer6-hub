#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Optional, Sequence


SHA256 = re.compile(r"^[0-9a-f]{64}$")
INVENTORY_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
GENERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SCOPE_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,127}$")
MAX_FILE_BYTES = 8 * 1024 * 1024
SCOPE_FIELDS = {
    "approvedAtUtc", "approvedBy", "channel", "contractName", "contractVersion",
    "decisionId", "platforms", "releaseTarget", "releaseVersion", "status",
    "supportOwner",
}
SCOPE_PLATFORM_FIELDS = {
    "artifactAccessClass", "fallbackHeads", "platform", "primaryHead", "rid",
    "signingRequirement",
}


class RequestError(ValueError):
    pass


def _args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize one exact Hub same-generation preview-authority CAS request."
        )
    )
    parser.add_argument("--generation-id", required=True)
    shelf = parser.add_mutually_exclusive_group(required=True)
    shelf.add_argument("--shelf-current", type=Path)
    shelf.add_argument(
        "--staged-handoff",
        type=Path,
        help=(
            "Secret-redacted staged finalizer handoff whose inert target pointer "
            "and inventory bind the authority request before CURRENT activation."
        ),
    )
    parser.add_argument("--predecessor-current", type=Path, required=True)
    parser.add_argument("--predecessor-snapshot", type=Path, required=True)
    parser.add_argument("--predecessor-decision", type=Path, required=True)
    parser.add_argument("--successor-current", type=Path, required=True)
    parser.add_argument("--successor-snapshot", type=Path, required=True)
    parser.add_argument("--successor-decision", type=Path, required=True)
    parser.add_argument("--scorecard", type=Path, required=True)
    parser.add_argument("--convergence", type=Path, required=True)
    parser.add_argument("--release-scope-decision", type=Path, required=True)
    parser.add_argument("--expected-release-scope-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _strict_object(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise RequestError(f"{label} could not be read") from error
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise RequestError(f"{label} has an invalid byte length")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RequestError(f"{label} contains duplicate JSON field {key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RequestError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise RequestError(f"{label} must be a JSON object")
    return raw, value


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise RequestError(f"{label} must be canonical SHA-256")
    return value


def _validate_envelope(
    current_raw: bytes,
    current: dict[str, Any],
    snapshot_raw: bytes,
    snapshot: dict[str, Any],
    decision_raw: bytes,
    decision: dict[str, Any],
    expected_status: str,
) -> None:
    if current.get("status") != expected_status:
        raise RequestError(f"CURRENT.json must be {expected_status}")
    if snapshot.get("releaseDecisionStatus") != expected_status:
        raise RequestError(f"SNAPSHOT.json must be {expected_status}")
    if decision.get("releaseDecisionStatus") != expected_status or decision.get("status") != expected_status:
        raise RequestError(f"RELEASE_DECISION.json must be {expected_status}")
    if _require_digest(current.get("snapshotSha256"), "CURRENT snapshotSha256") != _digest(snapshot_raw):
        raise RequestError("CURRENT.json does not bind exact SNAPSHOT.json bytes")
    decision_digest = _digest(decision_raw)
    if _require_digest(current.get("decisionSha256"), "CURRENT decisionSha256") != decision_digest:
        raise RequestError("CURRENT.json does not bind exact RELEASE_DECISION.json bytes")
    if _require_digest(snapshot.get("releaseDecisionSha256"), "SNAPSHOT releaseDecisionSha256") != decision_digest:
        raise RequestError("SNAPSHOT.json does not bind exact RELEASE_DECISION.json bytes")
    if current.get("releaseVersion") != snapshot.get("releaseVersion") or current.get("releaseVersion") != decision.get("releaseVersion"):
        raise RequestError("release authority envelope version binding disagrees")
    del current_raw


def _encoded(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _validate_release_scope(
    raw: bytes,
    payload: dict[str, Any],
    expected_sha256: str,
    release_version: str,
) -> None:
    if SHA256.fullmatch(expected_sha256) is None:
        raise RequestError("expected release-scope SHA-256 must be canonical lowercase hexadecimal")
    if _digest(raw) != expected_sha256:
        raise RequestError("approved release-scope decision digest does not match exact bytes")
    canonical = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")
    if raw != canonical:
        raise RequestError(
            "approved release-scope decision must be compact sorted UTF-8 JSON plus LF"
        )
    if set(payload) != SCOPE_FIELDS or (
        payload.get("contractName") != "chummer.release-scope-decision/v1"
        or payload.get("contractVersion") != 1
        or payload.get("status") != "approved"
        or payload.get("channel") != "preview"
        or payload.get("releaseTarget") != "preview"
        or payload.get("releaseVersion") != release_version
    ):
        raise RequestError("approved release-scope decision does not bind the exact preview release")
    for name in ("decisionId", "supportOwner"):
        value = payload.get(name)
        if not isinstance(value, str) or SCOPE_TOKEN.fullmatch(value) is None or ".." in value:
            raise RequestError(f"approved release-scope {name} is not a canonical token")
    if not isinstance(payload.get("approvedBy"), str) or not payload["approvedBy"].strip():
        raise RequestError("approved release-scope approving authority is unresolved")
    approved_at = payload.get("approvedAtUtc")
    if not isinstance(approved_at, str) or re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", approved_at
    ) is None:
        raise RequestError("approved release-scope timestamp is not canonical UTC seconds")
    platforms = payload.get("platforms")
    if not isinstance(platforms, list) or not 1 <= len(platforms) <= 16:
        raise RequestError("approved release-scope platform inventory is missing")
    observed: list[str] = []
    for row in platforms:
        if not isinstance(row, dict) or set(row) != SCOPE_PLATFORM_FIELDS:
            raise RequestError("approved release-scope platform row has an unexpected field set")
        platform = row.get("platform")
        rid = row.get("rid")
        if platform not in {"linux", "macos", "windows"} or not isinstance(rid, str):
            raise RequestError("approved release-scope platform/RID is unsupported")
        allowed_rids = {
            "linux": {"linux-x64", "linux-arm64"},
            "macos": {"osx-x64", "osx-arm64"},
            "windows": {"win-x64", "win-arm64"},
        }
        if rid not in allowed_rids[platform]:
            raise RequestError("approved release-scope platform/RID is incompatible")
        primary = row.get("primaryHead")
        fallbacks = row.get("fallbackHeads")
        if (
            primary not in {"avalonia", "blazor-desktop"}
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
            raise RequestError("approved release-scope platform policy is unsupported")
        observed.append(platform)
    if observed != sorted(observed) or len(observed) != len(set(observed)):
        raise RequestError("approved release-scope platforms must be sorted and unique")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _args(argv)
    try:
        generation_id = args.generation_id.strip()
        if GENERATION_ID.fullmatch(generation_id) is None:
            raise RequestError("generationId is not a traversal-safe opaque token")
        if args.shelf_current is not None:
            shelf_raw, shelf = _strict_object(
                args.shelf_current, "release shelf current.json"
            )
            if shelf.get("generationId") != generation_id:
                raise RequestError("release shelf current.json does not bind generationId")
            inventory_digest = shelf.get("inventoryDigest")
            if (
                not isinstance(inventory_digest, str)
                or INVENTORY_DIGEST.fullmatch(inventory_digest) is None
            ):
                raise RequestError("release shelf current.json inventoryDigest is invalid")
            expected_pointer_sha256 = _digest(shelf_raw)
            handoff_release_version = None
        else:
            _, shelf = _strict_object(
                args.staged_handoff, "staged release finalizer handoff"
            )
            if (
                shelf.get("contractName")
                != "chummer.staged-release-finalizer-handoff/v1"
                or shelf.get("contractVersion") != 1
                or shelf.get("status") != "review_required"
                or shelf.get("state") != "awaiting_owner_finalization"
                or shelf.get("secretRedacted") is not True
                or shelf.get("publicCurrentMutated") is not False
                or shelf.get("generationId") != generation_id
            ):
                raise RequestError(
                    "staged release finalizer handoff does not bind an inert exact generation"
                )
            inventory_digest = shelf.get("inventoryDigest")
            if (
                not isinstance(inventory_digest, str)
                or INVENTORY_DIGEST.fullmatch(inventory_digest) is None
            ):
                raise RequestError("staged release finalizer inventoryDigest is invalid")
            expected_pointer_sha256 = _require_digest(
                shelf.get("targetPointerSha256"), "staged target pointer digest"
            )
            handoff_release_version = shelf.get("releaseVersion")

        predecessor_current_raw, predecessor_current = _strict_object(
            args.predecessor_current, "predecessor CURRENT.json"
        )
        predecessor_snapshot_raw, predecessor_snapshot = _strict_object(
            args.predecessor_snapshot, "predecessor SNAPSHOT.json"
        )
        predecessor_decision_raw, predecessor_decision = _strict_object(
            args.predecessor_decision, "predecessor RELEASE_DECISION.json"
        )
        successor_current_raw, successor_current = _strict_object(
            args.successor_current, "successor CURRENT.json"
        )
        successor_snapshot_raw, successor_snapshot = _strict_object(
            args.successor_snapshot, "successor SNAPSHOT.json"
        )
        successor_decision_raw, successor_decision = _strict_object(
            args.successor_decision, "successor RELEASE_DECISION.json"
        )
        scorecard_raw, _ = _strict_object(args.scorecard, "campaign-operability scorecard")
        convergence_raw, _ = _strict_object(args.convergence, "live convergence receipt")
        release_scope_raw, release_scope = _strict_object(
            args.release_scope_decision, "approved release-scope decision"
        )

        _validate_envelope(
            predecessor_current_raw,
            predecessor_current,
            predecessor_snapshot_raw,
            predecessor_snapshot,
            predecessor_decision_raw,
            predecessor_decision,
            "review_required",
        )
        _validate_envelope(
            successor_current_raw,
            successor_current,
            successor_snapshot_raw,
            successor_snapshot,
            successor_decision_raw,
            successor_decision,
            "preview_ready",
        )
        if predecessor_current.get("releaseVersion") != successor_current.get("releaseVersion"):
            raise RequestError("authority advance cannot change releaseVersion")
        expected_release_scope_sha256 = args.expected_release_scope_sha256.strip()
        _validate_release_scope(
            release_scope_raw,
            release_scope,
            expected_release_scope_sha256,
            str(predecessor_current.get("releaseVersion") or ""),
        )
        if (
            handoff_release_version is not None
            and predecessor_current.get("releaseVersion") != handoff_release_version
        ):
            raise RequestError("staged handoff releaseVersion differs from authority envelopes")
        exact_bindings = {
            "authoritySnapshotSha256": _digest(predecessor_snapshot_raw),
            "candidateDecisionStatus": "review_required",
            "candidateDecisionSha256": _digest(predecessor_decision_raw),
            "scorecardSha256": _digest(scorecard_raw),
            "convergenceSha256": _digest(convergence_raw),
        }
        for name, expected in exact_bindings.items():
            if successor_decision.get(name) != expected:
                raise RequestError(f"successor decision {name} does not bind exact input bytes")

        payload = {
            "generationId": generation_id,
            "expectedShelfPointerSha256": expected_pointer_sha256,
            "expectedShelfInventoryDigest": inventory_digest,
            "expectedReleaseScopeDecisionSha256": expected_release_scope_sha256,
            "releaseScopeDecisionBytes": _encoded(release_scope_raw),
            "predecessorCurrentBytes": _encoded(predecessor_current_raw),
            "predecessorSnapshotBytes": _encoded(predecessor_snapshot_raw),
            "predecessorDecisionBytes": _encoded(predecessor_decision_raw),
            "successorCurrentBytes": _encoded(successor_current_raw),
            "successorSnapshotBytes": _encoded(successor_snapshot_raw),
            "successorDecisionBytes": _encoded(successor_decision_raw),
            "scorecardBytes": _encoded(scorecard_raw),
            "convergenceBytes": _encoded(convergence_raw),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with args.output.open("xb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(
                    (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
                )
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as error:
            raise RequestError("authority advance request output already exists") from error
    except (RequestError, OSError) as error:
        print("release authority advance request failed: %s" % error, file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "decisionSha256": _digest(successor_decision_raw),
                "generationId": generation_id,
                "pointerSha256": expected_pointer_sha256,
                "snapshotSha256": _digest(successor_snapshot_raw),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
