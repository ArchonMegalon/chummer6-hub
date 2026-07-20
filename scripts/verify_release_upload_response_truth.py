#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


CONTRACT_NAME = "chummer.release_upload_response_truth"
SCHEMA_VERSION = "chummer.release-upload-response-truth/v2"
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
SAFE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SAFE_ARTIFACT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}\Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-manifest", required=True)
    parser.add_argument("--local-canonical-manifest", required=True)
    parser.add_argument("--upload-response", required=True)
    parser.add_argument("--output")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError("JSON input contains duplicate object keys")
        payload[key] = value
    return payload


def load_json(path: Path) -> tuple[dict[str, Any], str]:
    content = path.read_bytes()
    payload = json.loads(content.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(payload, dict):
        raise ValueError("JSON input did not contain an object")
    return payload, sha256_bytes(content)


def _required_canonical_text(
    payload: dict[str, Any],
    key: str,
    source: str,
    *,
    failures: list[str],
    pattern: re.Pattern[str] = SAFE_ID_PATTERN,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not pattern.fullmatch(value) or ".." in value:
        failures.append(f"{source} {key} is missing or noncanonical")
        return ""
    return value


def _required_timestamp(
    payload: dict[str, Any],
    key: str,
    source: str,
    *,
    failures: list[str],
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or value != value.strip():
        failures.append(f"{source} {key} is missing or noncanonical")
        return ""
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        failures.append(f"{source} {key} is not a valid ISO-8601 timestamp")
        return ""
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        failures.append(f"{source} {key} must include a UTC offset")
        return ""
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def manifest_view(
    payload: dict[str, Any],
    *,
    source: str,
    channel_key: str,
    failures: list[str],
) -> dict[str, str]:
    return {
        "version": _required_canonical_text(payload, "version", source, failures=failures),
        "channel": _required_canonical_text(payload, channel_key, source, failures=failures),
        "publishedAt": _required_timestamp(payload, "publishedAt", source, failures=failures),
        "status": _required_canonical_text(payload, "status", source, failures=failures),
    }


def upload_response_view(payload: dict[str, Any], *, failures: list[str]) -> dict[str, str]:
    source = "upload response"
    return {
        "version": _required_canonical_text(payload, "version", source, failures=failures),
        "channel": _required_canonical_text(payload, "channel", source, failures=failures),
        "publishedAt": _required_timestamp(payload, "publishedAt", source, failures=failures),
    }


def _artifact_id_from_row(
    row: dict[str, Any],
    *,
    source: str,
    index: int,
    primary_key: str,
    alias_key: Optional[str],
    failures: list[str],
) -> str:
    value = row.get(primary_key)
    if not isinstance(value, str) or not SAFE_ARTIFACT_ID_PATTERN.fullmatch(value) or ".." in value:
        failures.append(f"{source} artifact row {index} has a missing or noncanonical {primary_key}")
        return ""
    if alias_key is not None and alias_key in row:
        alias = row.get(alias_key)
        if not isinstance(alias, str) or alias != value:
            failures.append(f"{source} artifact row {index} has conflicting artifact ID aliases")
            return ""
    return value


def manifest_artifact_ids(
    payload: dict[str, Any],
    *,
    source: str,
    collection_key: str,
    primary_key: str,
    alias_key: Optional[str],
    failures: list[str],
) -> list[str]:
    rows = payload.get(collection_key)
    if not isinstance(rows, list) or not rows:
        failures.append(f"{source} {collection_key} must be a non-empty array")
        return []

    artifact_ids: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            failures.append(f"{source} artifact row {index} is not an object")
            continue
        artifact_id = _artifact_id_from_row(
            row,
            source=source,
            index=index,
            primary_key=primary_key,
            alias_key=alias_key,
            failures=failures,
        )
        if not artifact_id:
            continue
        folded = artifact_id.casefold()
        if folded in seen:
            failures.append(f"{source} contains duplicate or case-ambiguous artifact IDs")
            continue
        seen.add(folded)
        artifact_ids.append(artifact_id)
    return artifact_ids


def promoted_artifact_ids(payload: dict[str, Any], *, failures: list[str]) -> list[str]:
    rows = payload.get("promotedArtifactIds")
    if not isinstance(rows, list) or not rows:
        failures.append("upload response promotedArtifactIds must be a non-empty array")
        return []

    artifact_ids: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(rows):
        if not isinstance(value, str) or not SAFE_ARTIFACT_ID_PATTERN.fullmatch(value) or ".." in value:
            failures.append(f"upload response promotedArtifactIds row {index} is noncanonical")
            continue
        folded = value.casefold()
        if folded in seen:
            failures.append("upload response promotedArtifactIds contains duplicate or case-ambiguous IDs")
            continue
        seen.add(folded)
        artifact_ids.append(value)
    return artifact_ids


def response_generation_id(payload: dict[str, Any], *, failures: list[str]) -> str:
    value = _required_canonical_text(payload, "generationId", "upload response", failures=failures)
    if value in {".", ".."}:
        failures.append("upload response generationId is not a traversal-safe opaque token")
        return ""
    return value


def response_manifest_digest(payload: dict[str, Any], key: str, *, failures: list[str]) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        failures.append(f"upload response {key} is missing or noncanonical")
        return ""
    return value


def compare_views(
    left_name: str,
    left: dict[str, str],
    right_name: str,
    right: dict[str, str],
    *,
    failures: list[str],
) -> None:
    for key in sorted(set(left) | set(right)):
        if left.get(key) != right.get(key):
            failures.append(f"{left_name} and {right_name} differ for {key}")


def binding_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return sha256_bytes(encoded)


def evaluate(
    *,
    local_manifest_path: Path,
    local_canonical_manifest_path: Path,
    upload_response_path: Path,
) -> dict[str, Any]:
    local_manifest_payload, local_manifest_sha256 = load_json(local_manifest_path)
    local_canonical_payload, local_canonical_sha256 = load_json(local_canonical_manifest_path)
    upload_response_payload, upload_response_sha256 = load_json(upload_response_path)

    failures: list[str] = []
    local_manifest = manifest_view(
        local_manifest_payload,
        source="local releases.json",
        channel_key="channel",
        failures=failures,
    )
    local_canonical = manifest_view(
        local_canonical_payload,
        source="local RELEASE_CHANNEL.generated.json",
        channel_key="channelId",
        failures=failures,
    )
    upload_response = upload_response_view(upload_response_payload, failures=failures)

    compare_views(
        "local releases.json",
        local_manifest,
        "local RELEASE_CHANNEL.generated.json",
        local_canonical,
        failures=failures,
    )
    compare_views(
        "upload response",
        upload_response,
        "local RELEASE_CHANNEL.generated.json",
        {
            "version": local_canonical["version"],
            "channel": local_canonical["channel"],
            "publishedAt": local_canonical["publishedAt"],
        },
        failures=failures,
    )

    local_compatibility_artifact_ids = manifest_artifact_ids(
        local_manifest_payload,
        source="local releases.json",
        collection_key="downloads",
        primary_key="id",
        alias_key="artifactId",
        failures=failures,
    )
    local_canonical_artifact_ids = manifest_artifact_ids(
        local_canonical_payload,
        source="local RELEASE_CHANNEL.generated.json",
        collection_key="artifacts",
        primary_key="artifactId",
        alias_key=None,
        failures=failures,
    )
    response_artifact_ids = promoted_artifact_ids(upload_response_payload, failures=failures)

    if set(local_compatibility_artifact_ids) != set(local_canonical_artifact_ids):
        failures.append("local release manifests disagree on the exact artifact ID inventory")
    if response_artifact_ids != local_compatibility_artifact_ids:
        failures.append("upload response promotedArtifactIds do not exactly match the candidate artifact ID inventory")

    local_compatibility_generation_id = _required_canonical_text(
        local_manifest_payload,
        "generationId",
        "local releases.json",
        failures=failures,
    )
    local_canonical_generation_id = _required_canonical_text(
        local_canonical_payload,
        "generationId",
        "local RELEASE_CHANNEL.generated.json",
        failures=failures,
    )
    generation_id = response_generation_id(upload_response_payload, failures=failures)
    if local_compatibility_generation_id != local_canonical_generation_id:
        failures.append("local release manifests disagree for generationId")
    if generation_id != local_canonical_generation_id:
        failures.append("upload response generationId does not match the exact candidate generationId")

    canonical_manifest_sha256 = response_manifest_digest(
        upload_response_payload,
        "canonicalManifestSha256",
        failures=failures,
    )
    compatibility_manifest_sha256 = response_manifest_digest(
        upload_response_payload,
        "compatibilityManifestSha256",
        failures=failures,
    )
    if (
        canonical_manifest_sha256
        and compatibility_manifest_sha256
        and canonical_manifest_sha256 == compatibility_manifest_sha256
    ):
        failures.append("upload response canonical and compatibility manifest digests must identify distinct bytes")
    if canonical_manifest_sha256 != local_canonical_sha256:
        failures.append(
            "upload response canonicalManifestSha256 does not match exact local canonical manifest bytes"
        )
    if compatibility_manifest_sha256 != local_manifest_sha256:
        failures.append(
            "upload response compatibilityManifestSha256 does not match exact local compatibility manifest bytes"
        )

    candidate_binding = {
        "generationId": local_canonical_generation_id,
        "version": local_canonical["version"],
        "channel": local_canonical["channel"],
        "publishedAt": local_canonical["publishedAt"],
        "artifactIds": local_canonical_artifact_ids,
        "canonicalInputSha256": local_canonical_sha256,
        "compatibilityInputSha256": local_manifest_sha256,
    }

    publication_binding: Optional[dict[str, Any]] = None
    if not failures:
        publication_binding = {
            "generationId": generation_id,
            "releaseVersion": upload_response["version"],
            "channel": upload_response["channel"],
            "publishedAt": upload_response["publishedAt"],
            "artifactIds": response_artifact_ids,
            "canonicalManifestSha256": canonical_manifest_sha256,
            "compatibilityManifestSha256": compatibility_manifest_sha256,
            "sanitizedUploadResponseSha256": upload_response_sha256,
            "candidateBindingSha256": binding_sha256(candidate_binding),
        }
        publication_binding["bindingSha256"] = binding_sha256(
            {
                "schemaVersion": SCHEMA_VERSION,
                "candidate": candidate_binding,
                "publication": publication_binding,
            }
        )

    return {
        "generated_at_utc": now_iso(),
        "contract_name": CONTRACT_NAME,
        "schemaVersion": SCHEMA_VERSION,
        "status": "fail" if failures else "pass",
        "failures": failures,
        "candidateBinding": candidate_binding,
        "publicationBinding": publication_binding,
    }


def main() -> None:
    args = parse_args()
    receipt = evaluate(
        local_manifest_path=Path(args.local_manifest),
        local_canonical_manifest_path=Path(args.local_canonical_manifest),
        upload_response_path=Path(args.upload_response),
    )
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    if receipt["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
