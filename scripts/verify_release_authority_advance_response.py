#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
from typing import Any, Optional, Sequence


SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVISION_ID = re.compile(r"^auth-[0-9a-f]{64}$")
RECEIPT_ID = re.compile(r"^authority-[0-9a-f]{32}$")
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 64 * 1024 * 1024
MAX_PROOF_BYTES = 8 * 1024 * 1024
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
RESPONSE_FIELDS = {
    "generationId",
    "releaseVersion",
    "revisionId",
    "previousDecisionStatus",
    "decisionStatus",
    "snapshotSha256",
    "decisionSha256",
    "scorecardSha256",
    "convergenceSha256",
    "journalReceiptId",
    "committedAtUtc",
    "recovered",
}


class VerificationError(ValueError):
    pass


def _args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify one exact Hub same-generation release-authority advance response."
    )
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--generation-id", required=True)
    parser.add_argument("--release-version", required=True)
    parser.add_argument("--predecessor-current", type=Path, required=True)
    parser.add_argument("--predecessor-snapshot", type=Path, required=True)
    parser.add_argument("--predecessor-decision", type=Path, required=True)
    parser.add_argument("--successor-current", type=Path, required=True)
    parser.add_argument("--successor-snapshot", type=Path, required=True)
    parser.add_argument("--successor-decision", type=Path, required=True)
    parser.add_argument("--scorecard", type=Path, required=True)
    parser.add_argument("--convergence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise VerificationError(f"{label} contains duplicate JSON field {key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise VerificationError(f"{label} must be a JSON object")
    return value


def _read(path: Path, label: str, maximum_bytes: int = MAX_PROOF_BYTES) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise VerificationError(f"{label} could not be read") from error
    if not raw or len(raw) > maximum_bytes:
        raise VerificationError(f"{label} has an invalid byte length")
    return raw, _strict_json(raw, label)


def _decode(value: Any, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise VerificationError(f"{label} must be canonical base64")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise VerificationError(f"{label} must be canonical base64") from error
    if base64.b64encode(decoded).decode("ascii") != value:
        raise VerificationError(f"{label} must be canonical base64")
    return decoded


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _append_hash_part(digest: Any, label: str, raw: bytes) -> None:
    label_raw = label.encode("utf-8")
    digest.update(struct.pack(">II", len(label_raw), len(raw)))
    digest.update(label_raw)
    digest.update(raw)


def _expected_revision(request: dict[str, Any], decoded: dict[str, bytes]) -> str:
    pointer = request.get("expectedShelfPointerSha256")
    inventory = request.get("expectedShelfInventoryDigest")
    if not isinstance(pointer, str) or SHA256.fullmatch(pointer) is None:
        raise VerificationError("request expectedShelfPointerSha256 is invalid")
    if (
        not isinstance(inventory, str)
        or not inventory.startswith("sha256:")
        or SHA256.fullmatch(inventory[7:]) is None
    ):
        raise VerificationError("request expectedShelfInventoryDigest is invalid")
    digest = hashlib.sha256()
    _append_hash_part(digest, "generation", str(request["generationId"]).encode("utf-8"))
    _append_hash_part(digest, "shelf-pointer", pointer.encode("ascii"))
    _append_hash_part(digest, "shelf-inventory", inventory[7:].encode("ascii"))
    for label, field in (
        ("predecessor-current", "predecessorCurrentBytes"),
        ("predecessor-snapshot", "predecessorSnapshotBytes"),
        ("predecessor-decision", "predecessorDecisionBytes"),
        ("successor-current", "successorCurrentBytes"),
        ("successor-snapshot", "successorSnapshotBytes"),
        ("successor-decision", "successorDecisionBytes"),
        ("scorecard", "scorecardBytes"),
        ("convergence", "convergenceBytes"),
    ):
        _append_hash_part(digest, label, decoded[field])
    return "auth-" + digest.hexdigest()


def _timestamp(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise VerificationError("committedAtUtc is not a canonical UTC timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as error:
        raise VerificationError("committedAtUtc is not a canonical UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise VerificationError("committedAtUtc is not a canonical UTC timestamp")
    return parsed.astimezone(dt.timezone.utc)


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(
                (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
                    "utf-8"
                )
            )
    except FileExistsError as error:
        raise VerificationError("authority advance verification output already exists") from error


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _args(argv)
    try:
        response_raw, response = _read(
            args.response, "authority advance response", MAX_RESPONSE_BYTES
        )
        request_raw, request = _read(
            args.request, "authority advance request", MAX_REQUEST_BYTES
        )
        del request_raw
        if set(response) != RESPONSE_FIELDS:
            raise VerificationError("authority advance response has an unexpected field set")
        if set(request) != REQUEST_FIELDS:
            raise VerificationError("authority advance request has an unexpected field set")

        expected_files: dict[str, tuple[bytes, dict[str, Any]]] = {}
        for name, path in (
            ("predecessorCurrentBytes", args.predecessor_current),
            ("predecessorSnapshotBytes", args.predecessor_snapshot),
            ("predecessorDecisionBytes", args.predecessor_decision),
            ("successorCurrentBytes", args.successor_current),
            ("successorSnapshotBytes", args.successor_snapshot),
            ("successorDecisionBytes", args.successor_decision),
            ("scorecardBytes", args.scorecard),
            ("convergenceBytes", args.convergence),
        ):
            expected_files[name] = _read(path, name)
        decoded = {name: _decode(request[name], name) for name in expected_files}
        for name, (expected_raw, _) in expected_files.items():
            if decoded[name] != expected_raw:
                raise VerificationError(f"authority advance request {name} differs from exact input bytes")

        generation_id = args.generation_id.strip()
        release_version = args.release_version.strip()
        predecessor_decision = expected_files["predecessorDecisionBytes"][1]
        successor_current = expected_files["successorCurrentBytes"][1]
        successor_snapshot = expected_files["successorSnapshotBytes"][1]
        successor_decision = expected_files["successorDecisionBytes"][1]
        if request.get("generationId") != generation_id:
            raise VerificationError("authority advance request generationId drifted")
        if (
            predecessor_decision.get("releaseDecisionStatus") != "review_required"
            or successor_current.get("status") != "preview_ready"
            or successor_snapshot.get("releaseDecisionStatus") != "preview_ready"
            or successor_decision.get("releaseDecisionStatus") != "preview_ready"
            or successor_decision.get("status") != "preview_ready"
            or successor_current.get("releaseVersion") != release_version
            or successor_snapshot.get("releaseVersion") != release_version
            or successor_decision.get("releaseVersion") != release_version
        ):
            raise VerificationError("authority advance input envelopes have inconsistent release identity")

        expected_revision = _expected_revision(request, decoded)
        expected_snapshot_sha256 = _sha(decoded["successorSnapshotBytes"])
        expected_decision_sha256 = _sha(decoded["successorDecisionBytes"])
        expected_scorecard_sha256 = _sha(decoded["scorecardBytes"])
        expected_convergence_sha256 = _sha(decoded["convergenceBytes"])
        if (
            response.get("generationId") != generation_id
            or response.get("releaseVersion") != release_version
            or response.get("revisionId") != expected_revision
            or response.get("previousDecisionStatus") != "review_required"
            or response.get("decisionStatus") != "preview_ready"
            or response.get("snapshotSha256") != expected_snapshot_sha256
            or response.get("decisionSha256") != expected_decision_sha256
            or response.get("scorecardSha256") != expected_scorecard_sha256
            or response.get("convergenceSha256") != expected_convergence_sha256
        ):
            raise VerificationError("authority advance response does not bind the exact successor request")
        if REVISION_ID.fullmatch(str(response.get("revisionId") or "")) is None:
            raise VerificationError("authority advance response revisionId is invalid")
        if RECEIPT_ID.fullmatch(str(response.get("journalReceiptId") or "")) is None:
            raise VerificationError("authority advance response journalReceiptId is invalid")
        if not isinstance(response.get("recovered"), bool):
            raise VerificationError("authority advance response recovered must be boolean")
        committed_at = _timestamp(response.get("committedAtUtc"))
        now = dt.datetime.now(dt.timezone.utc)
        if committed_at > now + dt.timedelta(minutes=5):
            raise VerificationError("authority advance response committedAtUtc is unreasonably in the future")

        _write_new(
            args.output,
            {
                "contractName": "chummer.release-authority-advance-response/v1",
                "status": "pass",
                "generationId": generation_id,
                "releaseVersion": release_version,
                "revisionId": expected_revision,
                "snapshotSha256": expected_snapshot_sha256,
                "decisionSha256": expected_decision_sha256,
                "scorecardSha256": expected_scorecard_sha256,
                "convergenceSha256": expected_convergence_sha256,
                "journalReceiptId": response["journalReceiptId"],
                "committedAtUtc": response["committedAtUtc"],
                "recovered": response["recovered"],
                "responseSha256": _sha(response_raw),
            },
        )
    except (VerificationError, OSError) as error:
        print(f"release authority advance response verification failed: {error}", file=sys.stderr)
        return 1
    print("release_authority_advance_response:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
