#!/usr/bin/env python3
"""Candidate-bound Google OAuth operator-evidence workflow.

The legacy proof scripts remain available for historical v1 receipts. This CLI
owns the v2 request/evidence path required by the current release gate: exact
portal, registry, and live release bytes; code-bound import/verification; real
image evidence; and detached operator attestation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import requests

import google_oauth_linking_evidence_v2 as contract
from materialize_google_oauth_linking_proof import (
    DEFAULT_AUDIT_EMAIL,
    probe_public_google_handoff,
    probe_signed_in_google_link_handoff,
)


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DEFAULT_TEMPLATE_PATH = (
    ROOT
    / "_completion"
    / "google_oauth_linking"
    / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.v2.template.generated.json"
)
DEFAULT_ASK_PATH = (
    ROOT
    / "_completion"
    / "google_oauth_linking"
    / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.v2.txt"
)
DEFAULT_ASK_METADATA_PATH = (
    ROOT
    / "_completion"
    / "google_oauth_linking"
    / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.v2.generated.json"
)
DEFAULT_INCOMING_ROOT = ROOT / ".state" / "incoming_google_oauth_linking_operator_evidence_v2"
DEFAULT_LIVE_CAPTURE_PATH = (
    ROOT / ".state" / "google_oauth_linking_operator_evidence" / "live-release-manifest.json"
)
DEFAULT_LIVE_URL = "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json"
MAX_LIVE_BYTES = 8 * 1024 * 1024
MAX_ZIP_MEMBER_BYTES = 50 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 128 * 1024 * 1024


def now() -> datetime:
    return datetime.now(UTC)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    payload, _raw = contract.read_json_object(path)
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture_live_manifest(url: str, output: Path) -> dict[str, Any]:
    response = requests.get(
        url,
        headers={"Accept": "application/json", "User-Agent": "ChummerOAuthEvidenceV2/1.0"},
        timeout=30,
        allow_redirects=False,
    )
    response.raise_for_status()
    raw = response.content
    if not raw or len(raw) > MAX_LIVE_BYTES:
        raise SystemExit("live release manifest is empty or exceeds the bounded capture size")
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit("live release manifest is not a UTF-8 JSON object") from exc
    if not isinstance(payload, dict):
        raise SystemExit("live release manifest root is not an object")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    captured_at = contract.isoformat_utc(now())
    result = {
        "status": "captured",
        "url": url,
        "path": str(output.resolve()),
        "captured_at_utc": captured_at,
        "sha256": contract.sha256_bytes(raw),
        "size_bytes": len(raw),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


def previous_live_binding(request_path: Path) -> tuple[Path | None, str | None]:
    if not request_path.is_file():
        return None, None
    try:
        payload = read_json(request_path)
    except Exception:
        return None, None
    release = payload.get("release") if isinstance(payload.get("release"), dict) else {}
    live = release.get("live") if isinstance(release.get("live"), dict) else {}
    capture_path = str(live.get("capture_path") or "").strip()
    captured_at = str(live.get("captured_at_utc") or "").strip()
    return (Path(capture_path) if capture_path else None, captured_at or None)


def default_paths_for_request(
    request_path: Path,
    *,
    evidence_path: Path | None,
    proof_path: Path | None,
    template_path: Path | None,
    incoming_root: Path | None,
) -> dict[str, Path]:
    request_path = request_path.resolve()
    canonical = request_path == contract.DEFAULT_REQUEST_PATH.resolve()
    if canonical:
        return {
            "evidence": (evidence_path or contract.DEFAULT_EVIDENCE_PATH).resolve(),
            "proof": (proof_path or contract.DEFAULT_PROOF_PATH).resolve(),
            "template": (template_path or DEFAULT_TEMPLATE_PATH).resolve(),
            "incoming": (incoming_root or DEFAULT_INCOMING_ROOT).resolve(),
            "ask": DEFAULT_ASK_PATH.resolve(),
            "ask_metadata": DEFAULT_ASK_METADATA_PATH.resolve(),
            "scope_root": request_path.parent,
        }
    stage_root = request_path.parent.resolve()
    return {
        "evidence": (evidence_path or stage_root / "imported" / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json").resolve(),
        "proof": (proof_path or stage_root / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").resolve(),
        "template": (template_path or stage_root / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json").resolve(),
        "incoming": (incoming_root or stage_root / "incoming").resolve(),
        "ask": (stage_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt").resolve(),
        "ask_metadata": (stage_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json").resolve(),
        "scope_root": stage_root,
    }


def build_operator_message(request: Mapping[str, Any]) -> str:
    release = request.get("release") if isinstance(request.get("release"), Mapping) else {}
    portal = release.get("portal") if isinstance(release.get("portal"), Mapping) else {}
    intake = request.get("artifact_intake") if isinstance(request.get("artifact_intake"), Mapping) else {}
    lines = [
        "Chummer Google OAuth v2 operator evidence request",
        "",
        f"Status: {request.get('status')}",
        f"Base URL: {request.get('base_url')}",
        f"Release: {portal.get('version') or 'unknown'} / {portal.get('channel') or 'unknown'}",
    ]
    if request.get("status") == "blocked_release_authority":
        lines.extend(
            [
                "",
                "Do not capture or send OAuth evidence yet. Portal, registry, and live release authority must converge first.",
                *[f"- {item}" for item in release.get("blockers") or []],
            ]
        )
        return "\n".join(lines).strip() + "\n"
    lines.extend(
        [
            "",
            "Use a real browser and an existing Chummer account:",
            *[
                f"{index}. {step}"
                for index, step in enumerate(contract.REQUIRED_OPERATOR_STEPS, start=1)
            ],
            "",
            "Capture at least two distinct PNG/JPEG screenshots (minimum 640x360 and 4096 bytes each).",
            "Sign the exact evidence claims with a reviewed Ed25519 operator identity.",
            f"Template: {request.get('template_path')}",
            f"Bundle filename: {Path(str(intake.get('preferred_drop_path') or '')).name}",
            f"Drop folder: {intake.get('dedicated_drop_root')}",
            "The importer will bind the receipt, screenshots, release manifests, and current verifier bytes before proof materialization.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def materialize_request(args: argparse.Namespace) -> int:
    request_path = args.request.resolve()
    paths = default_paths_for_request(
        request_path,
        evidence_path=args.evidence,
        proof_path=args.proof,
        template_path=args.template,
        incoming_root=args.incoming_root,
    )
    captured_at = args.live_captured_at
    live_path = args.live_release_manifest.resolve() if args.live_release_manifest else None
    if live_path is None:
        live_path, previous_captured_at = previous_live_binding(request_path)
        captured_at = captured_at or previous_captured_at

    release = contract.release_authority_binding(
        portal_path=args.portal_release_manifest.resolve(),
        hub_path=args.hub_release_manifest.resolve(),
        live_capture_path=live_path,
        live_captured_at_utc=captured_at,
    )
    programs = contract.program_bindings()
    binding_sha256 = contract.request_binding_sha256(
        base_url=args.base_url,
        release=release,
        programs=programs,
    )
    previous = read_json(request_path) if request_path.is_file() else None
    nonce, generated_at, reused = contract.reusable_request_identity(
        previous,
        binding_sha256=binding_sha256,
        now=now(),
    )
    status = "operator_action_required" if release.get("ready") is True else "blocked_release_authority"
    release_version = str((release.get("portal") or {}).get("version") or "unknown")
    preferred_drop_path = paths["incoming"] / f"google-oauth-linking-operator-evidence-v2-{release_version}.zip"
    screenshot_paths = [
        (paths["scope_root"] / "screenshots" / "google-signed-in.png").resolve(),
        (paths["scope_root"] / "screenshots" / "google-provider-linked.png").resolve(),
    ]
    post_import_plan = (
        contract.fixed_post_import_argv_plan(
            base_url=args.base_url,
            request_path=request_path,
            evidence_path=paths["evidence"],
            proof_path=paths["proof"],
        )
        if release.get("ready") is True
        else []
    )
    artifact_intake: dict[str, Any] = {
        "dedicated_drop_root": str(paths["incoming"]),
        "auto_import_roots": [str(paths["incoming"])],
        "preferred_drop_path": str(preferred_drop_path),
        "post_import_argv_plan": post_import_plan,
    }
    if release.get("ready") is True:
        artifact_intake["import_argv"] = [
            "python3",
            "scripts/google_oauth_linking_evidence_v2_cli.py",
            "import-evidence",
            "--artifact",
            str(preferred_drop_path),
            "--request",
            str(request_path),
            "--evidence",
            str(paths["evidence"]),
        ]

    canonical = request_path == contract.DEFAULT_REQUEST_PATH.resolve()
    request: dict[str, Any] = {
        "contract_name": contract.REQUEST_CONTRACT_NAME,
        "generated_at_utc": generated_at,
        "status": status,
        "base_url": args.base_url,
        "request_nonce": nonce,
        "request_binding_sha256": binding_sha256,
        "release": release,
        "program_bindings": programs,
        "media_policy": contract.media_policy(),
        "required_steps": list(contract.REQUIRED_OPERATOR_STEPS),
        "request_receipt_path": str(request_path),
        "required_output_path": str(paths["evidence"]),
        "required_receipt_path": str(paths["evidence"]),
        "required_operator_evidence_path": str(paths["evidence"]),
        "required_proof_path": str(paths["proof"]),
        "template_path": str(paths["template"]),
        "operator_evidence_template_path": str(paths["template"]),
        "operator_message_path": str(paths["ask"]),
        "operator_ask_text_path": str(paths["ask"]),
        "operator_ask_metadata_path": str(paths["ask_metadata"]),
        "preferred_drop_folder": str(paths["incoming"]),
        "recommended_screenshot_paths": [str(path) for path in screenshot_paths],
        "materialization_scope": {
            "mode": "canonical" if canonical else "staged",
            "root": str(paths["scope_root"]),
            "self_contained": not canonical,
            "proof_output_path": str(paths["proof"]),
        },
        "artifact_intake": artifact_intake,
        "request_identity_reused": reused,
        "trusted_operator_identity_count": len(contract.TRUSTED_OPERATOR_IDENTITIES),
        "trusted_operator_identity_review_required": not bool(contract.TRUSTED_OPERATOR_IDENTITIES),
    }
    request["intake"] = dict(artifact_intake)
    if release.get("ready") is not True:
        request["recovery"] = {
            "status": "blocked_release_authority",
            "execution_authority_present": False,
            "release_authority_blockers": list(release.get("blockers") or []),
            "summary": "OAuth evidence capture is withheld until portal, registry, and live release authority converge.",
            "required_conditions": [
                "Capture fresh live release manifest bytes.",
                "Use exact portal and registry manifests with the same release identity and posture.",
                "Rerun materialize-request after authority convergence.",
            ],
        }

    write_json(request_path, request)
    request_raw = request_path.read_bytes()
    evidence_template = {
        "contract_name": contract.EVIDENCE_CONTRACT_NAME,
        "status": "pass",
        "base_url": args.base_url,
        "observed_at_utc": "",
        "request_nonce": nonce,
        "request_sha256": contract.sha256_bytes(request_raw),
        "release_authority_sha256": contract.sha256_json(release),
        "portal_release_manifest_sha256": (release.get("portal") or {}).get("manifest_sha256"),
        "hub_release_manifest_sha256": (release.get("hub_registry") or {}).get("manifest_sha256"),
        "live_release_manifest_sha256": (release.get("live") or {}).get("manifest_sha256"),
        "verified_steps": list(contract.REQUIRED_OPERATOR_STEPS),
        "screenshots": [
            {
                "logical_name": path.name,
                "path": str(path),
                "sha256": "",
                "size_bytes": 0,
                "width": 0,
                "height": 0,
                "media_type": "image/png",
            }
            for path in screenshot_paths
        ],
        "attestation": {
            "contract_name": contract.ATTESTATION_CONTRACT_NAME,
            "algorithm": "ed25519",
            "key_id": "",
            "role": contract.ATTESTATION_ROLE,
            "generated_at_utc": "",
            "signature": "",
        },
        "notes": "Fill image claims, then sign the exact code-derived attestation claims with a reviewed operator key.",
    }
    write_json(paths["template"], evidence_template)
    operator_message = build_operator_message(request)
    paths["ask"].parent.mkdir(parents=True, exist_ok=True)
    paths["ask"].write_text(operator_message, encoding="utf-8")
    write_json(
        paths["ask_metadata"],
        {
            "status": "prepared_not_sent" if status == "operator_action_required" else "blocked_release_authority",
            "generated_at_utc": contract.isoformat_utc(now()),
            "request_path": str(request_path),
            "message_path": str(paths["ask"]),
            "message_sha256": contract.sha256_bytes(operator_message.encode("utf-8")),
            "secrets_redacted": True,
        },
    )
    _payload, summary, _raw, failures = contract.verify_request_file(
        request_path,
        portal_release_manifest_path=args.portal_release_manifest.resolve(),
        hub_release_manifest_path=args.hub_release_manifest.resolve(),
    )
    result = {**summary, "failures": failures, "template_path": str(paths["template"])}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


def release_paths_from_request(request_path: Path) -> tuple[Path, Path]:
    payload = read_json(request_path)
    release = payload.get("release") if isinstance(payload.get("release"), dict) else {}
    portal = release.get("portal") if isinstance(release.get("portal"), dict) else {}
    hub = release.get("hub_registry") if isinstance(release.get("hub_registry"), dict) else {}
    portal_path = str(portal.get("manifest_path") or "").strip()
    hub_path = str(hub.get("manifest_path") or "").strip()
    if not portal_path or not hub_path:
        raise SystemExit("request does not bind exact portal and registry manifest paths")
    return Path(portal_path), Path(hub_path)


def verify_request(args: argparse.Namespace) -> int:
    portal_path, hub_path = release_paths_from_request(args.request)
    _payload, summary, _raw, failures = contract.verify_request_file(
        args.request,
        portal_release_manifest_path=portal_path,
        hub_release_manifest_path=hub_path,
    )
    print(json.dumps({**summary, "failures": failures}, indent=2, sort_keys=True))
    return 0 if not failures else 1


def safe_zip_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members: list[zipfile.ZipInfo] = []
    total = 0
    for info in archive.infolist():
        path = Path(info.filename)
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"unsafe zip member path: {info.filename}")
        if stat.S_ISLNK(unix_mode):
            raise SystemExit(f"zip symlink is rejected: {info.filename}")
        if info.is_dir():
            continue
        if info.file_size > MAX_ZIP_MEMBER_BYTES:
            raise SystemExit(f"zip member exceeds bounded size: {info.filename}")
        total += info.file_size
        if total > MAX_ZIP_TOTAL_BYTES:
            raise SystemExit("zip expanded size exceeds bounded total")
        members.append(info)
    return members


def import_evidence(args: argparse.Namespace) -> int:
    artifact = args.artifact.resolve()
    if not artifact.is_file() or artifact.suffix.lower() != ".zip":
        raise SystemExit("v2 operator evidence must be supplied as a regular .zip bundle")
    request_path = args.request.resolve()
    portal_path, hub_path = release_paths_from_request(request_path)
    request_payload, request_summary, _request_raw, request_failures = contract.verify_request_file(
        request_path,
        portal_release_manifest_path=portal_path,
        hub_release_manifest_path=hub_path,
    )
    if request_failures:
        raise SystemExit("current v2 request is invalid: " + "; ".join(request_failures))
    if request_payload.get("status") != "operator_action_required":
        raise SystemExit("current v2 request does not authorize evidence import")

    evidence_path = (args.evidence or Path(str(request_payload["required_operator_evidence_path"]))).resolve()
    imported_root = (
        args.imported_root
        or (contract.DEFAULT_IMPORTED_SCREENSHOT_ROOT if request_path == contract.DEFAULT_REQUEST_PATH.resolve() else request_path.parent / "imported" / "screenshots")
    ).resolve()
    token = now().strftime("%Y%m%dT%H%M%SZ")
    destination_root = imported_root / token
    with tempfile.TemporaryDirectory(prefix="google-oauth-v2-import-") as temp_dir:
        temp_root = Path(temp_dir)
        with zipfile.ZipFile(artifact) as archive:
            members = safe_zip_members(archive)
            for info in members:
                destination = temp_root / info.filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(info))
        candidates: list[Path] = []
        for candidate in temp_root.rglob("*.json"):
            try:
                payload = read_json(candidate)
            except Exception:
                continue
            if payload.get("contract_name") == contract.EVIDENCE_CONTRACT_NAME:
                candidates.append(candidate)
        if len(candidates) != 1:
            raise SystemExit(f"expected one v2 evidence receipt, found {len(candidates)}")
        source_receipt = candidates[0]
        payload = read_json(source_receipt)
        screenshots = payload.get("screenshots")
        if not isinstance(screenshots, list) or len(screenshots) < contract.MINIMUM_SCREENSHOT_COUNT:
            raise SystemExit("v2 evidence receipt does not list the required screenshots")
        imported_rows: list[dict[str, Any]] = []
        destination_root.mkdir(parents=True, exist_ok=True)
        for index, raw_row in enumerate(screenshots, start=1):
            if not isinstance(raw_row, dict):
                raise SystemExit("v2 screenshot row is not an object")
            raw_path = Path(str(raw_row.get("path") or raw_row.get("logical_name") or ""))
            matches = [path for path in temp_root.rglob(raw_path.name) if path.is_file()]
            if len(matches) != 1:
                raise SystemExit(f"screenshot {raw_path.name!r} is missing or ambiguous in the bundle")
            source_image = matches[0]
            actual, image_failures = contract.inspect_image(source_image)
            if image_failures:
                raise SystemExit("invalid screenshot: " + "; ".join(image_failures))
            for field in ("sha256", "size_bytes", "width", "height", "media_type"):
                if raw_row.get(field) != actual.get(field):
                    raise SystemExit(f"screenshot {raw_path.name!r} {field} does not match its bytes")
            destination = destination_root / f"{index:02d}-{raw_path.name}"
            shutil.copy2(source_image, destination)
            imported_rows.append({**raw_row, **actual, "path": str(destination)})

        imported = dict(payload)
        imported["screenshots"] = imported_rows
        imported["import_provenance"] = {
            "source_artifact_path": str(artifact),
            "source_artifact_sha256": sha256_file(artifact),
            "source_receipt_sha256": sha256_file(source_receipt),
            "importer_program": "v2_cli",
            "importer_program_sha256": request_summary["program_bindings"]["v2_cli"]["sha256"],
            "imported_at_utc": contract.isoformat_utc(now()),
        }
        write_json(evidence_path, imported)

    _payload, summary, _raw, failures = contract.verify_evidence_file(
        evidence_path,
        request_path=request_path,
        portal_release_manifest_path=portal_path,
        hub_release_manifest_path=hub_path,
        allowed_screenshot_root=imported_root,
    )
    print(json.dumps({**summary, "failures": failures}, indent=2, sort_keys=True))
    return 0 if not failures else 1


def evidence_path_from_args(args: argparse.Namespace, request_payload: Mapping[str, Any]) -> Path:
    raw = args.evidence or Path(str(request_payload.get("required_operator_evidence_path") or contract.DEFAULT_EVIDENCE_PATH))
    return raw.resolve()


def materialize_proof(args: argparse.Namespace) -> int:
    request_path = args.request.resolve()
    request_payload = read_json(request_path)
    portal_path, hub_path = release_paths_from_request(request_path)
    evidence_path = evidence_path_from_args(args, request_payload)
    proof_path = args.proof.resolve()
    quick_probe = probe_public_google_handoff(args.base_url)
    if args.run_signed_in_probe:
        signed_in_probe = probe_signed_in_google_link_handoff(args.base_url, args.audit_email)
    else:
        signed_in_probe = {
            "status": "operator_required",
            "pass": False,
            "failures": [],
            "reason": "signed-in automation remains paused; candidate-bound operator evidence is required",
        }
    bindings, binding_failures = contract.current_proof_bindings(
        request_path=request_path,
        evidence_path=evidence_path,
        portal_release_manifest_path=portal_path,
        hub_release_manifest_path=hub_path,
    )
    failures = [f"quick_handoff_probe: {item}" for item in quick_probe.get("failures", [])]
    if signed_in_probe.get("status") == "fail":
        failures.extend(f"signed_in_link_handoff: {item}" for item in signed_in_probe.get("failures", []))
    failures.extend(binding_failures)
    receipt = {
        "contract_name": contract.PROOF_CONTRACT_NAME,
        "proof_contract_version": contract.PROOF_CONTRACT_VERSION,
        "status": "pass" if not failures else "fail",
        "generated_at_utc": contract.isoformat_utc(now()),
        "base_url": args.base_url,
        "bindings": bindings,
        "quick_handoff_probe": quick_probe,
        "signed_in_link_handoff": signed_in_probe,
        "failures": failures,
    }
    write_json(proof_path, receipt)
    summary, verification_failures = contract.verify_proof_payload(
        receipt,
        request_path=request_path,
        evidence_path=evidence_path,
        portal_release_manifest_path=portal_path,
        hub_release_manifest_path=hub_path,
        require_pass=False,
    )
    print(json.dumps({**summary, "receipt_path": str(proof_path), "failures": verification_failures}, indent=2, sort_keys=True))
    return 0 if not verification_failures else 1


def verify_proof(args: argparse.Namespace) -> int:
    request_path = args.request.resolve()
    request_payload = read_json(request_path)
    portal_path, hub_path = release_paths_from_request(request_path)
    evidence_path = evidence_path_from_args(args, request_payload)
    payload = read_json(args.proof)
    summary, failures = contract.verify_proof_payload(
        payload,
        request_path=request_path,
        evidence_path=evidence_path,
        portal_release_manifest_path=portal_path,
        hub_release_manifest_path=hub_path,
        require_pass=args.require_pass,
    )
    print(json.dumps({**summary, "failures": failures}, indent=2, sort_keys=True))
    return 0 if not failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Candidate-bound Google OAuth v2 evidence workflow.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture-live")
    capture.add_argument("--url", default=DEFAULT_LIVE_URL)
    capture.add_argument("--output", type=Path, default=DEFAULT_LIVE_CAPTURE_PATH)

    request = subparsers.add_parser("materialize-request")
    request.add_argument("--request", type=Path, default=contract.DEFAULT_REQUEST_PATH)
    request.add_argument("--base-url", default=contract.DEFAULT_BASE_URL)
    request.add_argument("--portal-release-manifest", type=Path, default=contract.DEFAULT_PORTAL_RELEASE_MANIFEST_PATH)
    request.add_argument("--hub-release-manifest", type=Path, default=contract.DEFAULT_HUB_RELEASE_MANIFEST_PATH)
    request.add_argument("--live-release-manifest", type=Path)
    request.add_argument("--live-captured-at")
    request.add_argument("--evidence", type=Path)
    request.add_argument("--proof", type=Path)
    request.add_argument("--template", type=Path)
    request.add_argument("--incoming-root", type=Path)

    verify_request_parser = subparsers.add_parser("verify-request")
    verify_request_parser.add_argument("--request", type=Path, default=contract.DEFAULT_REQUEST_PATH)

    import_parser = subparsers.add_parser("import-evidence")
    import_parser.add_argument("--artifact", type=Path, required=True)
    import_parser.add_argument("--request", type=Path, default=contract.DEFAULT_REQUEST_PATH)
    import_parser.add_argument("--evidence", type=Path)
    import_parser.add_argument("--imported-root", type=Path)

    proof = subparsers.add_parser("materialize-proof")
    proof.add_argument("--proof", type=Path, default=contract.DEFAULT_PROOF_PATH)
    proof.add_argument("--request", type=Path, default=contract.DEFAULT_REQUEST_PATH)
    proof.add_argument("--evidence", type=Path)
    proof.add_argument("--base-url", default=contract.DEFAULT_BASE_URL)
    proof.add_argument("--audit-email", default=DEFAULT_AUDIT_EMAIL)
    proof.add_argument("--run-signed-in-probe", action="store_true")

    verify_proof_parser = subparsers.add_parser("verify-proof")
    verify_proof_parser.add_argument("--proof", type=Path, default=contract.DEFAULT_PROOF_PATH)
    verify_proof_parser.add_argument("--request", type=Path, default=contract.DEFAULT_REQUEST_PATH)
    verify_proof_parser.add_argument("--evidence", type=Path)
    verify_proof_parser.add_argument("--require-pass", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "capture-live":
        capture_live_manifest(args.url, args.output.resolve())
        return 0
    if args.command == "materialize-request":
        return materialize_request(args)
    if args.command == "verify-request":
        return verify_request(args)
    if args.command == "import-evidence":
        return import_evidence(args)
    if args.command == "materialize-proof":
        return materialize_proof(args)
    if args.command == "verify-proof":
        return verify_proof(args)
    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
