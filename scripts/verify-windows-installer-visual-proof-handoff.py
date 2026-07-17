#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlparse


PASSING_STATUSES = {"pass", "passed", "ready"}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
HANDOFF_CONTRACT = "chummer6-ui.windows_installer_visual_proof_handoff"
HANDOFF_SCOPE = "staged_nightly_windows_visual_proof"
WINDOWS_GATE_CONTRACT = "chummer6-ui.windows_desktop_exit_gate"


class DuplicateJsonKey(ValueError):
    pass


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def normalize_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def normalize_id(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_sha256(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw.startswith("sha256:"):
        raw = raw.removeprefix("sha256:")
    return f"sha256:{raw}" if SHA256_PATTERN.fullmatch(raw) else ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise DuplicateJsonKey(f"duplicate JSON key: {key}")
        payload[key] = value
    return payload


def load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        fail(f"{label} must be a non-symlink regular file inside the staged bundle: {path}")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateJsonKey) as exc:
        fail(f"{label} could not be loaded: {exc}")
    if not isinstance(payload, dict):
        fail(f"{label} must be a JSON object")
    return payload


def require_object(payload: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        fail(f"{label}.{key} must be an object")
    return value


def require_exact(payload: dict[str, Any], key: str, expected: Any, label: str) -> None:
    if payload.get(key) != expected:
        fail(f"{label}.{key} must be {expected!r}")


def is_windows_installer_name(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith("chummer-") and "-win-" in lowered and lowered.endswith("-installer.exe")


def item_file_name(item: dict[str, Any]) -> str:
    explicit = str(item.get("fileName") or "").strip()
    if explicit:
        return explicit
    raw_url = str(item.get("downloadUrl") or item.get("url") or "").strip()
    return Path(urlparse(raw_url).path).name if raw_url else ""


def manifest_windows_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for collection_name in ("artifacts", "downloads"):
        collection = payload.get(collection_name)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if isinstance(item, dict) and is_windows_installer_name(item_file_name(item)):
                rows.append(item)
    return rows


def infer_head(file_name: str) -> str:
    lowered = file_name.lower()
    if lowered.startswith("chummer-blazor-desktop-"):
        return "blazor-desktop"
    if lowered.startswith("chummer-avalonia-"):
        return "avalonia"
    return ""


def infer_rid(file_name: str) -> str:
    suffix = "-installer.exe"
    lowered = file_name.lower()
    if not lowered.endswith(suffix):
        return ""
    stem = lowered[: -len(suffix)]
    marker = stem.rfind("-win-")
    return stem[marker + 1 :] if marker >= 0 else ""


def validate_manifest_posture(payload: dict[str, Any], path: Path) -> tuple[str, str, dict[str, Any]]:
    version = str(payload.get("version") or payload.get("releaseVersion") or "").strip()
    if not version:
        fail(f"{path.name} is missing a release version")
    channel = normalize_token(payload.get("channelId") or payload.get("channel"))
    if channel != "preview":
        fail(f"{path.name} proof-only visual handoff is restricted to channel='preview'")
    if normalize_token(payload.get("supportabilityState")) != "review_required":
        fail(f"{path.name} must set supportabilityState='review_required'")

    boundary = require_object(payload, "registryBoundaryCoverage", path.name)
    if normalize_token(boundary.get("channelId")) != "preview":
        fail(f"{path.name} registryBoundaryCoverage.channelId must be 'preview'")
    if str(boundary.get("releaseVersion") or "").strip() != version:
        fail(f"{path.name} registryBoundaryCoverage.releaseVersion must match the release")
    boundary_release = require_object(boundary, "releaseChannel", f"{path.name}.registryBoundaryCoverage")
    if normalize_token(boundary_release.get("supportabilityState")) != "review_required":
        fail(
            f"{path.name} registryBoundaryCoverage.releaseChannel.supportabilityState "
            "must be 'review_required'"
        )
    if normalize_token(boundary_release.get("publicTrustPosture")) != "blocked":
        fail(
            f"{path.name} registryBoundaryCoverage.releaseChannel.publicTrustPosture "
            "must be 'blocked'"
        )

    public_trust = payload.get("publicTrustMetrics")
    if path.name == "RELEASE_CHANNEL.generated.json" or public_trust is not None:
        if not isinstance(public_trust, dict):
            fail(f"{path.name}.publicTrustMetrics must be an object")
        public_release = require_object(public_trust, "releaseChannel", f"{path.name}.publicTrustMetrics")
        if normalize_token(public_release.get("channelId")) != "preview":
            fail(f"{path.name} publicTrustMetrics.releaseChannel.channelId must be 'preview'")
        if normalize_token(public_release.get("supportabilityState")) != "review_required":
            fail(
                f"{path.name} publicTrustMetrics.releaseChannel.supportabilityState "
                "must be 'review_required'"
            )

    rows = manifest_windows_rows(payload)
    if len(rows) != 1:
        fail(f"{path.name} must contain exactly one Windows installer for a proof-only visual handoff")
    return version, channel, rows[0]


def validate_manifest_row(
    item: dict[str, Any],
    *,
    version: str,
    channel: str,
    installer_path: Path,
    actual_digest: str,
    label: str,
) -> tuple[str, str, str, str]:
    artifact_id = str(item.get("artifactId") or item.get("id") or "").strip()
    file_name = item_file_name(item)
    head = normalize_id(item.get("head") or infer_head(file_name))
    rid = normalize_id(item.get("rid") or infer_rid(file_name))
    if not artifact_id:
        fail(f"{label} Windows installer artifactId is missing")
    if file_name != installer_path.name:
        fail(f"{label} Windows installer fileName does not match staged installer bytes")
    if normalize_sha256(item.get("sha256") or item.get("artifactSha256")) != actual_digest:
        fail(f"{label} Windows installer sha256 does not match staged installer bytes")
    if normalize_token(item.get("platform")) != "windows":
        fail(f"{label} Windows installer platform must be 'windows'")
    if not head or not rid:
        fail(f"{label} Windows installer head/rid lineage is incomplete")
    item_version = str(item.get("releaseVersion") or item.get("version") or version).strip()
    if item_version != version:
        fail(f"{label} Windows installer version does not match its manifest")
    item_channel = normalize_token(item.get("channelId") or item.get("channel") or channel)
    if item_channel != channel:
        fail(f"{label} Windows installer channel does not match its manifest")
    return artifact_id, file_name, head, rid


def validate_startup_smoke(
    *,
    bundle_root: Path,
    handoff: dict[str, Any],
    version: str,
    artifact_id: str,
    file_name: str,
    head: str,
    rid: str,
    actual_digest: str,
) -> None:
    receipt_name = f"startup-smoke-{head}-{rid}.receipt.json"
    handoff_path = Path(str(handoff.get("startup_smoke_path") or "").strip())
    if handoff_path.name != receipt_name:
        fail("handoff startup_smoke_path does not name the deterministic stage receipt")
    receipt_path = bundle_root / "startup-smoke" / receipt_name
    receipt = load_object(receipt_path, "stage startup-smoke receipt")
    receipt_digest = sha256_file(receipt_path)

    if normalize_token(receipt.get("status")) not in PASSING_STATUSES:
        fail("stage startup-smoke receipt status is not passing")
    if str(receipt.get("version") or "").strip() != version:
        fail("stage startup-smoke receipt version does not match the release")
    if str(receipt.get("releaseVersion") or "").strip() != version:
        fail("stage startup-smoke receipt releaseVersion does not match the release")
    receipt_channels = [
        normalize_token(receipt.get(key))
        for key in ("channelId", "channel")
        if str(receipt.get(key) or "").strip()
    ]
    if not receipt_channels or any(value != "preview" for value in receipt_channels):
        fail("stage startup-smoke receipt channel does not match preview")
    if normalize_token(receipt.get("platform")) != "windows":
        fail("stage startup-smoke receipt platform is not Windows")
    if normalize_id(receipt.get("headId") or receipt.get("head")) != head:
        fail("stage startup-smoke receipt head does not match the installer")
    if normalize_id(receipt.get("rid")) != rid:
        fail("stage startup-smoke receipt rid does not match the installer")
    if str(receipt.get("artifactId") or "").strip() != artifact_id:
        fail("stage startup-smoke receipt artifactId does not match the installer")
    receipt_file_name = str(
        receipt.get("artifactFileName")
        or receipt.get("fileName")
        or Path(str(receipt.get("artifactPath") or "")).name
        or ""
    ).strip()
    if receipt_file_name != file_name:
        fail("stage startup-smoke receipt artifact file does not match the installer")
    if normalize_sha256(receipt.get("artifactDigest") or receipt.get("artifactSha256")) != actual_digest:
        fail("stage startup-smoke receipt artifact digest does not match staged installer bytes")

    embedded = require_object(handoff, "startup_smoke", "handoff")
    if normalize_token(embedded.get("status")) not in PASSING_STATUSES:
        fail("handoff startup_smoke.status is not passing")
    if str(embedded.get("version") or "").strip() != version:
        fail("handoff startup_smoke.version does not match the release")
    if str(embedded.get("release_version") or "").strip() != version:
        fail("handoff startup_smoke.release_version does not match the release")
    if str(embedded.get("artifact_file_name") or "").strip() != file_name:
        fail("handoff startup_smoke.artifact_file_name does not match the installer")
    if normalize_sha256(embedded.get("artifact_digest")) != actual_digest:
        fail("handoff startup_smoke.artifact_digest does not match staged installer bytes")
    if str(embedded.get("receipt_file_name") or "").strip() != receipt_name:
        fail("handoff startup_smoke.receipt_file_name does not match the deterministic stage receipt")
    if normalize_sha256(embedded.get("receipt_sha256")) != receipt_digest:
        fail("handoff startup_smoke.receipt_sha256 does not match current stage receipt bytes")
    for key in (
        "matches_release_version",
        "matches_artifact_file_name",
        "matches_artifact_digest",
    ):
        require_exact(embedded, key, True, "handoff.startup_smoke")


def visual_only_reason(value: Any) -> bool:
    reason = str(value or "").strip().lower()
    return bool(reason) and reason.startswith("windows installer visual proof ")


def validate_windows_gate(
    *,
    gate_path: Path,
    handoff: dict[str, Any],
    version: str,
    file_name: str,
    head: str,
    rid: str,
    actual_digest: str,
) -> None:
    if Path(str(handoff.get("windows_gate_path") or "").strip()).name != gate_path.name:
        fail("handoff windows_gate_path does not name the deterministic stage gate")
    gate = load_object(gate_path, "stage Windows desktop exit gate")
    contract = str(gate.get("contract_name") or gate.get("contractName") or "").strip()
    if contract != WINDOWS_GATE_CONTRACT:
        fail(f"stage Windows desktop exit gate contract must be {WINDOWS_GATE_CONTRACT}")
    if normalize_token(gate.get("status")) != "failed":
        fail("stage Windows desktop exit gate status must be 'failed'")
    if normalize_token(gate.get("channelId") or gate.get("channel")) != "preview":
        fail("stage Windows desktop exit gate channel must be preview")
    if str(gate.get("releaseVersion") or gate.get("version") or "").strip() != version:
        fail("stage Windows desktop exit gate version does not match the release")

    blocking_modes = [
        normalize_token(gate.get(key))
        for key in ("blockingMode", "blocking_mode")
        if str(gate.get(key) or "").strip()
    ]
    if not blocking_modes or any(value != "external_only" for value in blocking_modes):
        fail("stage Windows desktop exit gate must be blocked in external_only mode")

    reasons = gate.get("reasons")
    if not isinstance(reasons, list) or not reasons or not all(visual_only_reason(item) for item in reasons):
        fail("stage Windows desktop exit gate reasons must be non-empty and visual-proof-only")
    if normalize_token(handoff.get("windows_gate_status")) != "failed":
        fail("handoff windows_gate_status must be 'failed'")
    handoff_reasons = handoff.get("windows_gate_reasons")
    if handoff_reasons != reasons:
        fail("handoff windows_gate_reasons must exactly match the stage Windows exit gate")

    gate_head = require_object(gate, "head", "stage Windows desktop exit gate")
    if normalize_id(gate_head.get("app_key") or gate_head.get("head")) != head:
        fail("stage Windows desktop exit gate head does not match the installer")
    if normalize_token(gate_head.get("platform")) != "windows":
        fail("stage Windows desktop exit gate platform is not Windows")
    if normalize_id(gate_head.get("rid")) != rid:
        fail("stage Windows desktop exit gate rid does not match the installer")

    checks = require_object(gate, "checks", "stage Windows desktop exit gate")
    required_checks: tuple[tuple[str, Any], ...] = (
        ("release_channel_id", "preview"),
        ("release_channel_version", version),
        ("installer_exists", True),
        ("expected_windows_file_name", file_name),
        ("expected_windows_head", head),
        ("expected_windows_rid", rid),
        ("startup_smoke_receipt_found", True),
        ("startup_smoke_status", "pass"),
        ("startup_smoke_digest_matches_expected", True),
        ("startup_smoke_version", version),
        ("startup_smoke_channel", "preview"),
        ("windows_installer_visual_proof_current_capture_pending", True),
    )
    for key, expected in required_checks:
        actual = checks.get(key)
        if isinstance(expected, str):
            if key in {"expected_windows_head", "expected_windows_rid"}:
                actual = normalize_id(actual)
                normalized_expected = normalize_id(expected)
            elif "version" not in key and key != "expected_windows_file_name":
                actual = normalize_token(actual)
                normalized_expected = normalize_token(expected)
            else:
                actual = str(actual or "").strip()
                normalized_expected = expected
            if actual != normalized_expected:
                fail(f"stage Windows desktop exit gate checks.{key} does not match the staged candidate")
        elif actual is not expected:
            fail(f"stage Windows desktop exit gate checks.{key} does not match the staged candidate")
    if normalize_sha256(checks.get("installer_sha256")) != actual_digest:
        fail("stage Windows desktop exit gate installer_sha256 does not match staged bytes")
    if normalize_sha256(checks.get("startup_smoke_artifact_digest")) != actual_digest:
        fail("stage Windows desktop exit gate startup-smoke digest does not match staged bytes")
    if normalize_token(checks.get("windows_visual_proof_external_blocker")) != "missing_windows_visual_proof_capture":
        fail("stage Windows desktop exit gate does not identify missing Windows visual capture as its blocker")


def validate(args: argparse.Namespace) -> tuple[str, str]:
    files_dir = args.files_dir.resolve()
    if not files_dir.is_dir() or files_dir.is_symlink():
        fail(f"files directory must be a non-symlink directory: {files_dir}")
    bundle_root = files_dir.parent
    installers = sorted(
        path for path in files_dir.glob("chummer-*-win-*-installer.exe") if path.is_file() and not path.is_symlink()
    )
    if len(installers) != 1:
        fail("proof-only visual handoff requires exactly one staged Windows installer")
    installer_path = installers[0]
    actual_digest = sha256_file(installer_path)

    manifest_paths = [path.resolve() for path in args.manifest]
    if not manifest_paths:
        fail("at least one release manifest is required")
    canonical_id: tuple[str, str, str, str, str, str] | None = None
    version = artifact_id = file_name = head = rid = ""
    for manifest_path in manifest_paths:
        payload = load_object(manifest_path, manifest_path.name)
        current_version, channel, item = validate_manifest_posture(payload, manifest_path)
        current_artifact_id, current_file_name, current_head, current_rid = validate_manifest_row(
            item,
            version=current_version,
            channel=channel,
            installer_path=installer_path,
            actual_digest=actual_digest,
            label=manifest_path.name,
        )
        current_id = (
            current_version,
            channel,
            current_artifact_id,
            current_file_name,
            current_head,
            current_rid,
        )
        if canonical_id is not None and current_id != canonical_id:
            fail("release manifests disagree on Windows proof-only candidate identity")
        canonical_id = current_id
        version, _, artifact_id, file_name, head, rid = current_id

    handoff = load_object(args.handoff.resolve(), "Windows visual-proof handoff")
    require_exact(handoff, "contract_name", HANDOFF_CONTRACT, "handoff")
    require_exact(handoff, "handoff_only", True, "handoff")
    require_exact(handoff, "handoff_scope", HANDOFF_SCOPE, "handoff")
    require_exact(handoff, "stable_release_unchanged", True, "handoff")
    require_exact(handoff, "requires_separate_publish_lane", True, "handoff")
    require_exact(handoff, "status", "ready_for_windows_host", "handoff")
    require_exact(handoff, "only_blocker_is_visual_proof", True, "handoff")
    require_exact(handoff, "blockers", [], "handoff")

    release = require_object(handoff, "release", "handoff")
    require_exact(release, "channel_id", "preview", "handoff.release")
    require_exact(release, "version", version, "handoff.release")
    require_exact(release, "release_version", version, "handoff.release")
    if Path(str(handoff.get("release_channel_manifest_path") or "").strip()).name != "RELEASE_CHANNEL.generated.json":
        fail("handoff release_channel_manifest_path does not name the canonical stage manifest")

    installer = require_object(handoff, "windows_installer", "handoff")
    require_exact(installer, "artifact_id", artifact_id, "handoff.windows_installer")
    require_exact(installer, "file_name", file_name, "handoff.windows_installer")
    if normalize_sha256(installer.get("sha256")) != actual_digest:
        fail("handoff windows_installer.sha256 does not match staged installer bytes")

    validate_startup_smoke(
        bundle_root=bundle_root,
        handoff=handoff,
        version=version,
        artifact_id=artifact_id,
        file_name=file_name,
        head=head,
        rid=rid,
        actual_digest=actual_digest,
    )
    validate_windows_gate(
        gate_path=args.windows_gate.resolve(),
        handoff=handoff,
        version=version,
        file_name=file_name,
        head=head,
        rid=rid,
        actual_digest=actual_digest,
    )
    return version, actual_digest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the narrow preview-only Windows visual-capture handoff exception. "
            "This never establishes native Windows proof or stable release readiness."
        )
    )
    parser.add_argument("--files-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, action="append", default=[], required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--windows-gate", type=Path, required=True)
    args = parser.parse_args()

    try:
        version, digest = validate(args)
    except ValueError as exc:
        print("windows_installer_visual_proof_handoff_gate:fail", file=sys.stderr)
        print(f" - {exc}", file=sys.stderr)
        return 1

    print(
        "windows_installer_visual_proof_handoff_gate:ok "
        f"version={version} installerDigest={digest} posture=proof_only"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
