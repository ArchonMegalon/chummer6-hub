#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Optional, Sequence


SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
RESPONSE_FIELDS = {
    "current",
    "snapshot",
    "snapshotBytes",
    "manifestBytes",
    "releaseDecisionBytes",
}
CURRENT_FIELDS = {"releaseVersion", "snapshotSha256", "decisionSha256", "status"}


class InspectionError(ValueError):
    pass


def _args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect one exact Registry CURRENT authority response for CAS."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--response", type=Path)
    source.add_argument("--absent", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise InspectionError(f"{label} contains duplicate JSON field {key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InspectionError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise InspectionError(f"{label} must be a JSON object")
    return value


def _decode(value: Any, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise InspectionError(f"{label} must be non-empty canonical base64")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise InspectionError(f"{label} must be non-empty canonical base64") from error
    if base64.b64encode(decoded).decode("ascii") != value:
        raise InspectionError(f"{label} must be non-empty canonical base64")
    return decoded


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise InspectionError(f"{label} must be canonical SHA-256")
    return value


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
        raise InspectionError("Registry current inspection output already exists") from error


def _inspect(response_path: Path) -> dict[str, Any]:
    try:
        raw = response_path.read_bytes()
    except OSError as error:
        raise InspectionError("Registry current response could not be read") from error
    if not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise InspectionError("Registry current response has an invalid byte length")
    response = _strict_json(raw, "Registry current response")
    if set(response) != RESPONSE_FIELDS:
        raise InspectionError("Registry current response has an unexpected field set")

    current = response.get("current")
    snapshot = response.get("snapshot")
    if not isinstance(current, dict) or set(current) != CURRENT_FIELDS:
        raise InspectionError("Registry current pointer has an unexpected field set")
    if not isinstance(snapshot, dict):
        raise InspectionError("Registry current snapshot must be an object")

    snapshot_raw = _decode(response["snapshotBytes"], "snapshotBytes")
    manifest_raw = _decode(response["manifestBytes"], "manifestBytes")
    decision_raw = _decode(response["releaseDecisionBytes"], "releaseDecisionBytes")
    decoded_snapshot = _strict_json(snapshot_raw, "decoded Registry snapshot")
    manifest = _strict_json(manifest_raw, "decoded Registry manifest")
    decision = _strict_json(decision_raw, "decoded Registry decision")
    if decoded_snapshot != snapshot:
        raise InspectionError("Registry parsed snapshot differs from exact snapshotBytes")

    release_version = current.get("releaseVersion")
    status = current.get("status")
    if (
        not isinstance(release_version, str)
        or not release_version
        or len(release_version) > 128
        or status not in {"review_required", "preview_ready", "stable_ready"}
        or snapshot.get("releaseVersion") != release_version
        or snapshot.get("releaseDecisionStatus") != status
        or decision.get("releaseVersion") != release_version
        or decision.get("releaseDecisionStatus") != status
        or decision.get("status") != status
    ):
        raise InspectionError("Registry current envelope identity or status is inconsistent")

    snapshot_sha256 = hashlib.sha256(snapshot_raw).hexdigest()
    decision_sha256 = hashlib.sha256(decision_raw).hexdigest()
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    if (
        _digest(current.get("snapshotSha256"), "current snapshotSha256")
        != snapshot_sha256
        or _digest(current.get("decisionSha256"), "current decisionSha256")
        != decision_sha256
        or _digest(snapshot.get("releaseDecisionSha256"), "snapshot releaseDecisionSha256")
        != decision_sha256
        or _digest(snapshot.get("manifestSha256"), "snapshot manifestSha256")
        != manifest_sha256
    ):
        raise InspectionError("Registry current envelope digest binding is inconsistent")
    manifest_version = manifest.get("releaseVersion") or manifest.get("version")
    if manifest_version != release_version:
        raise InspectionError("Registry current manifest release version is inconsistent")

    return {
        "contractName": "chummer.registry-release-authority-current-cas/v1",
        "status": "pass",
        "authorityState": "present",
        "releaseVersion": release_version,
        "releaseDecisionStatus": status,
        "snapshotSha256": snapshot_sha256,
        "decisionSha256": decision_sha256,
        "manifestSha256": manifest_sha256,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _args(argv)
    try:
        payload = (
            {
                "contractName": "chummer.registry-release-authority-current-cas/v1",
                "status": "pass",
                "authorityState": "absent",
                "releaseVersion": "",
                "releaseDecisionStatus": "",
                "snapshotSha256": "none",
                "decisionSha256": "",
                "manifestSha256": "",
            }
            if args.absent
            else _inspect(args.response)
        )
        _write_new(args.output, payload)
    except (InspectionError, OSError) as error:
        print(f"Registry current authority inspection failed: {error}", file=sys.stderr)
        return 1
    print("registry_release_authority_current:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
