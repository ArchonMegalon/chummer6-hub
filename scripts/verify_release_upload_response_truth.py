#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-manifest", required=True)
    parser.add_argument("--local-canonical-manifest", required=True)
    parser.add_argument("--upload-response", required=True)
    parser.add_argument("--output")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_token(value: Any) -> str:
    return normalize_text(value).lower()


def normalize_iso(value: Any) -> str:
    raw = normalize_text(value)
    if not raw:
        return ""
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return normalize_text(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def manifest_view(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "version": normalize_text(payload.get("version")),
        "channel": normalize_text(payload.get("channelId") or payload.get("channel")),
        "publishedAt": normalize_iso(payload.get("publishedAt")),
        "status": normalize_text(payload.get("status")),
    }


def upload_response_view(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "version": normalize_text(payload.get("version") or payload.get("releaseVersion")),
        "channel": normalize_text(payload.get("channelId") or payload.get("channel")),
        "publishedAt": normalize_iso(payload.get("publishedAt")),
    }


def artifact_ids(payload: dict[str, Any]) -> set[str]:
    rows = payload.get("downloads")
    if not isinstance(rows, list):
        rows = payload.get("artifacts")
    if not isinstance(rows, list):
        return set()
    ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        artifact_id = normalize_text(row.get("artifactId") or row.get("id"))
        if artifact_id:
            ids.add(artifact_id)
    return ids


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
            failures.append(f"{left_name} and {right_name} differ for {key}: {left.get(key)!r} != {right.get(key)!r}")


def evaluate(
    *,
    local_manifest_path: Path,
    local_canonical_manifest_path: Path,
    upload_response_path: Path,
) -> dict[str, Any]:
    local_manifest_payload = load_json(local_manifest_path)
    local_canonical_payload = load_json(local_canonical_manifest_path)
    upload_response_payload = load_json(upload_response_path)

    local_manifest = manifest_view(local_manifest_payload)
    local_canonical = manifest_view(local_canonical_payload)
    upload_response = upload_response_view(upload_response_payload)

    failures: list[str] = []
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

    promoted_artifact_ids = [
        normalize_text(item)
        for item in upload_response_payload.get("promotedArtifactIds") or []
        if normalize_text(item)
    ]
    local_known_artifact_ids = artifact_ids(local_manifest_payload) | artifact_ids(local_canonical_payload)
    unknown_promoted_artifact_ids = sorted(set(promoted_artifact_ids) - local_known_artifact_ids)
    if unknown_promoted_artifact_ids:
        failures.append(
            "upload response promotedArtifactIds are missing from local manifests: "
            + ", ".join(unknown_promoted_artifact_ids)
        )

    return {
        "generated_at_utc": now_iso(),
        "contract_name": "chummer.release_upload_response_truth",
        "status": "fail" if failures else "pass",
        "failures": failures,
        "local": {
            "manifest": local_manifest,
            "canonicalManifest": local_canonical,
            "artifactIds": sorted(local_known_artifact_ids),
        },
        "uploadResponse": {
            "view": upload_response,
            "promotedArtifactIds": promoted_artifact_ids,
            "downloadsUrl": normalize_text(upload_response_payload.get("downloadsUrl")),
        },
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
