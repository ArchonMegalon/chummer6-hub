#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from materialize_google_oauth_linking_proof import (
    DEFAULT_BASE_URL,
    DEFAULT_OPERATOR_EVIDENCE_PATH,
    inspect_operator_evidence,
    sha256_text,
)
import google_oauth_linking_evidence_v2 as evidence_v2
from published_path_hygiene import portable_command_text, portable_path_text


RUN_SERVICES_ROOT = SCRIPT_DIR.parents[0]
ROOT = RUN_SERVICES_ROOT.parent
DEFAULT_OUTPUT = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
DEFAULT_OPERATOR_DRAFT_ROOT = RUN_SERVICES_ROOT / "_completion" / "google_oauth_linking"
CURRENT_OPERATOR_ASK_TEXT_NAME = "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt"
CURRENT_OPERATOR_ASK_METADATA_NAME = "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json"
DEFAULT_OPERATOR_ASK_RECEIPT_NAME = "google-oauth-linking-operator-ask.receipt.json"
DEFAULT_TEMPLATE_PATH = DEFAULT_OPERATOR_DRAFT_ROOT / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json"
DEFAULT_SCREENSHOT_ROOT = RUN_SERVICES_ROOT / ".state" / "google_oauth_linking_operator_evidence"
DEFAULT_INCOMING_EVIDENCE_ROOT = RUN_SERVICES_ROOT / ".state" / "incoming_google_oauth_linking_operator_evidence"
DEFAULT_RELEASE_CHANNEL_PATH = evidence_v2.DEFAULT_PORTAL_RELEASE_MANIFEST_PATH
DEFAULT_HUB_RELEASE_CHANNEL_PATH = evidence_v2.DEFAULT_HUB_RELEASE_MANIFEST_PATH
DEFAULT_PROOF_PATH = evidence_v2.DEFAULT_PROOF_PATH
DEFAULT_BUNDLE_PATTERN = "*google-oauth-linking-operator-evidence*.zip"
DISCOVERY_MAX_DEPTH = 6
POST_IMPORT_VERIFY_NOTE = (
    "The --verify import runs only the fixed code-owned argv plan. Commands or "
    "shell text in the intake JSON are never execution authority."
)
OPERATOR_EVIDENCE_CONTRACT_NAME = evidence_v2.EVIDENCE_CONTRACT_NAME
OPERATOR_EVIDENCE_REQUEST_CONTRACT_NAME = evidence_v2.REQUEST_CONTRACT_NAME
REQUIRED_OPERATOR_STEPS = evidence_v2.REQUIRED_OPERATOR_STEPS
MINIMUM_OPERATOR_SCREENSHOT_COUNT = evidence_v2.MINIMUM_SCREENSHOT_COUNT


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def text_preview(value: str, limit: int = 220) -> str:
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def unique_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(path)
    return result


def is_gitignored_runtime_root(path: Path) -> bool:
    normalized = path.expanduser()
    roots = [
        RUN_SERVICES_ROOT / ".state",
        ROOT / ".state",
    ]
    for root in roots:
        try:
            if normalized.is_relative_to(root):
                return True
        except ValueError:
            continue
    return False


def resolved_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_within_root(path: Path, root: Path) -> bool:
    try:
        resolved_path(path).relative_to(resolved_path(root))
        return True
    except ValueError:
        return False


def resolve_materialization_paths(
    output_path: Path,
    *,
    evidence_path: Path | None,
    template_path: Path | None,
    screenshot_root: Path | None,
    operator_draft_root: Path | None,
    incoming_evidence_root: Path | None,
    proof_path: Path | None,
) -> dict[str, Path | bool]:
    output = resolved_path(output_path)
    canonical = output == resolved_path(DEFAULT_OUTPUT)
    stage_root = output.parent
    staged_assets = stage_root / "google_oauth_linking_request"

    def companion(
        explicit: Path | None,
        canonical_default: Path,
        staged_default: Path,
    ) -> Path:
        if explicit is not None:
            candidate = explicit
        elif canonical:
            candidate = canonical_default
        elif is_within_root(canonical_default, stage_root):
            # Tests and embedding callers may deliberately rebind a default to
            # a stage-local path. Honor it only when it remains self-contained.
            candidate = canonical_default
        else:
            candidate = staged_default
        resolved = resolved_path(candidate)
        if not canonical and not is_within_root(resolved, stage_root):
            raise ValueError(
                f"noncanonical Google OAuth request companion escapes stage root {stage_root}: {resolved}"
            )
        return resolved

    return {
        "canonical": canonical,
        "stage_root": stage_root,
        "output_path": output,
        "evidence_path": companion(
            evidence_path,
            DEFAULT_OPERATOR_EVIDENCE_PATH,
            stage_root / DEFAULT_OPERATOR_EVIDENCE_PATH.name,
        ),
        "template_path": companion(
            template_path,
            DEFAULT_TEMPLATE_PATH,
            staged_assets / DEFAULT_TEMPLATE_PATH.name,
        ),
        "screenshot_root": companion(
            screenshot_root,
            DEFAULT_SCREENSHOT_ROOT,
            staged_assets / "screenshots",
        ),
        "operator_draft_root": companion(
            operator_draft_root,
            DEFAULT_OPERATOR_DRAFT_ROOT,
            staged_assets / "operator_draft",
        ),
        "incoming_evidence_root": companion(
            incoming_evidence_root,
            DEFAULT_INCOMING_EVIDENCE_ROOT,
            staged_assets / "incoming",
        ),
        "proof_path": companion(
            proof_path,
            DEFAULT_PROOF_PATH,
            stage_root / DEFAULT_PROOF_PATH.name,
        ),
    }


def artifact_discovery_roots(dedicated_drop_root: Path) -> list[Path]:
    home = Path.home()
    roots = [
        dedicated_drop_root,
        Path(tempfile.gettempdir()),
        home / "Downloads",
        home / "pCloud Drive" / "EA",
    ]
    return unique_paths(roots)


def shell_quote_path(value: Path | str) -> str:
    return shlex.quote(portable_path_text(value))


def shell_quote_text(value: str) -> str:
    return shlex.quote(str(value))


def build_import_command(bundle_path: Path, request_path: Path) -> str:
    return (
        "python3 scripts/import_google_oauth_linking_operator_evidence_artifact.py "
        f"{shell_quote_path(bundle_path)} "
        f"--intake-request {shell_quote_path(request_path)} "
        "--verify"
    )


def build_auto_import_command(
    request_path: Path,
    base_url: str = DEFAULT_BASE_URL,
    *,
    wait_seconds: float | None = None,
    poll_seconds: float | None = None,
    refresh_intake_request: bool = False,
) -> str:
    command = (
        "python3 scripts/auto_import_google_oauth_linking_operator_evidence.py "
        f"--base-url {shell_quote_text(base_url)} "
        f"--intake-request {request_path}"
    )
    if wait_seconds is not None:
        command += f" --wait-seconds {int(wait_seconds)}"
    if poll_seconds is not None:
        command += f" --poll-seconds {int(poll_seconds)}"
    if refresh_intake_request:
        command += " --refresh-intake-request"
    return command


def post_import_argv_plan(
    base_url: str,
    *,
    request_path: Path = DEFAULT_OUTPUT,
    evidence_path: Path = DEFAULT_OPERATOR_EVIDENCE_PATH,
    proof_path: Path = DEFAULT_PROOF_PATH,
) -> list[list[str]]:
    return evidence_v2.fixed_post_import_argv_plan(
        base_url=base_url or DEFAULT_BASE_URL,
        request_path=request_path,
        evidence_path=evidence_path,
        proof_path=proof_path,
    )


POST_IMPORT_ARGV_PLAN = post_import_argv_plan(DEFAULT_BASE_URL)


def read_release_context(
    release_channel_path: Path,
    *,
    hub_release_channel_path: Path = DEFAULT_HUB_RELEASE_CHANNEL_PATH,
    live_release_manifest_path: Path | None = None,
    live_captured_at_utc: str | None = None,
) -> dict[str, Any]:
    authority = evidence_v2.release_authority_binding(
        portal_path=release_channel_path,
        hub_path=hub_release_channel_path,
        live_capture_path=live_release_manifest_path,
        live_captured_at_utc=live_captured_at_utc,
    )
    portal = authority["portal"]
    return {
        "path": str(release_channel_path.resolve()),
        "version": str(portal.get("version") or ""),
        "channel": str(portal.get("channel") or ""),
        "supportability_state": str(portal.get("supportability_state") or ""),
        "rollout_state": str(portal.get("rollout_state") or ""),
        "published_at": str(portal.get("published_at") or ""),
        "authority": authority,
    }


def current_operator_ask_text_path(operator_draft_root: Path | None = None) -> Path:
    return (operator_draft_root or DEFAULT_OPERATOR_DRAFT_ROOT) / CURRENT_OPERATOR_ASK_TEXT_NAME


def current_operator_ask_metadata_path(operator_draft_root: Path | None = None) -> Path:
    return (operator_draft_root or DEFAULT_OPERATOR_DRAFT_ROOT) / CURRENT_OPERATOR_ASK_METADATA_NAME


def operator_ask_send_command(operator_ask_text_path: Path, receipt_name: str = DEFAULT_OPERATOR_ASK_RECEIPT_NAME) -> str:
    return (
        "python3 scripts/send_telegram_message_via_ea.py "
        f"--text-file {operator_ask_text_path} --receipt-name {receipt_name}"
    )


def build_operator_message(
    base_url: str,
    evidence_path: Path,
    screenshot_paths: list[Path],
    release_context: dict[str, str],
    *,
    operator_action_required: bool,
    operator_evidence: dict[str, Any] | None = None,
    template_path: Path | None = None,
    preferred_drop_path: Path | None = None,
    import_command: str = "",
    auto_import_watch_command: str = "",
) -> str:
    release_summary = (
        f"{release_context.get('version') or 'unknown'}"
        f" | channel={release_context.get('channel') or 'unknown'}"
        f" | rollout={release_context.get('rollout_state') or 'unknown'}"
        f" | supportability={release_context.get('supportability_state') or 'unknown'}"
    )
    release_authority = release_context.get("authority") if isinstance(release_context.get("authority"), dict) else {}
    if release_authority.get("ready") is not True:
        blockers = ", ".join(str(item) for item in release_authority.get("blockers") or []) or "release authority is incomplete"
        return (
            "Chummer Google account-linking proof intake is paused internally.\n\n"
            "Do not capture, package, import, or send operator evidence yet.\n"
            f"Release authority blockers: {blockers}\n"
            f"Portal tuple: {release_summary}\n"
            "The portal, hub-registry, and explicitly captured live manifest must agree exactly before a request nonce is actionable.\n"
        )
    if not operator_action_required:
        observed_at = str((operator_evidence or {}).get("observed_at_utc") or "unknown").strip() or "unknown"
        lines = [
            "Chummer Google account-linking operator evidence already satisfies the current request.",
            "",
            f"Base URL: {base_url}",
            f"Current promoted release tuple: {release_summary}",
            f"Verified receipt path: {evidence_path}",
            f"Observed at: {observed_at}",
            "",
            "No operator action is currently required.",
        ]
        return "\n".join(lines).strip() + "\n"

    lines = [
        "Chummer flagship blocker: browser-backed Google account-linking proof is still missing.",
        "",
        f"Base URL: {base_url}",
        f"Current promoted release tuple: {release_summary}",
        f"Required receipt path: {evidence_path}",
        "",
        "Verify these steps in a real browser session against an existing Chummer account:",
    ]
    for index, step in enumerate(REQUIRED_OPERATOR_STEPS, start=1):
        lines.append(f"{index}. {step}")
    lines.extend(
        [
            "",
            "Current live surfaces to read after the handoff:",
            "- /home should stay signed in and keep the Google return path readable.",
            "- /account/settings should keep the primary sign-in and linked sign-in/channel summary readable.",
            "- If a deeper signed-in account surface explicitly shows the Google link state, capture that as the provider-visible proof screenshot.",
            "",
            "Capture at least two screenshots. Recommended paths:",
        ]
    )
    for path in screenshot_paths:
        lines.append(f"- {path}")
    lines.extend(
        [
            "",
            f"Operator evidence template: {template_path}" if template_path else "Complete the operator evidence template.",
            f"Preferred bundle drop path: {preferred_drop_path}" if preferred_drop_path else "",
            f"Import a completed bundle with: {import_command}" if import_command else "",
            POST_IMPORT_VERIFY_NOTE if import_command else "",
            f"Or watch for the bundle automatically with: {auto_import_watch_command}" if auto_import_watch_command else "",
            "Then complete the operator evidence template and write the finished receipt to the required path.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_template(
    base_url: str,
    screenshot_paths: list[Path],
    *,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = request or {}
    release = request.get("release") if isinstance(request.get("release"), dict) else {}
    return {
        "contract_name": OPERATOR_EVIDENCE_CONTRACT_NAME,
        "status": "pass",
        "base_url": base_url,
        "observed_at_utc": "",
        "request_nonce": request.get("request_nonce"),
        "request_sha256": "<sha256-of-the-exact-current-request-json>",
        "release_authority_sha256": evidence_v2.sha256_json(release) if release else "",
        "portal_release_manifest_sha256": (release.get("portal") or {}).get("manifest_sha256"),
        "hub_release_manifest_sha256": (release.get("hub_registry") or {}).get("manifest_sha256"),
        "live_release_manifest_sha256": (release.get("live") or {}).get("manifest_sha256"),
        "verified_steps": list(REQUIRED_OPERATOR_STEPS),
        "screenshots": [
            {
                "logical_name": path.name,
                "path": str(path),
                "sha256": "",
                "size_bytes": 0,
                "width": 0,
                "height": 0,
                "media_type": "",
            }
            for path in screenshot_paths
        ],
        "attestation": {
            "contract_name": evidence_v2.ATTESTATION_CONTRACT_NAME,
            "algorithm": "ed25519",
            "key_id": "<reviewed-code-pinned-operator-key-id>",
            "role": evidence_v2.ATTESTATION_ROLE,
            "generated_at_utc": "",
            "subject_sha256": "",
            "request_nonce": request.get("request_nonce"),
            "request_sha256": "",
            "release_authority_sha256": evidence_v2.sha256_json(release) if release else "",
            "portal_release_manifest_sha256": (release.get("portal") or {}).get("manifest_sha256"),
            "hub_release_manifest_sha256": (release.get("hub_registry") or {}).get("manifest_sha256"),
            "live_release_manifest_sha256": (release.get("live") or {}).get("manifest_sha256"),
            "screenshot_set_sha256": "",
            "signature": "",
        },
        "notes": "",
    }


def build_request(
    request_path: Path,
    base_url: str,
    evidence_path: Path,
    template_path: Path,
    screenshot_paths: list[Path],
    release_context: dict[str, str],
    *,
    proof_path: Path,
    operator_draft_root: Path,
    materialization_scope: dict[str, Any],
    request_status: str,
    operator_evidence: dict[str, Any] | None = None,
    request_nonce: str | None = None,
    generated_at_utc: str | None = None,
    program_bindings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    release = release_context.get("authority") if isinstance(release_context.get("authority"), dict) else {}
    programs = program_bindings or evidence_v2.program_bindings()
    binding_sha256 = evidence_v2.request_binding_sha256(
        base_url=base_url,
        release=release,
        programs=programs,
    )
    request_nonce = request_nonce or evidence_v2.reusable_request_identity(
        None,
        binding_sha256=binding_sha256,
        now=evidence_v2.utc_now(),
    )[0]
    if release.get("ready") is not True:
        request_status = "blocked_release_authority"
    elif request_status != "operator_action_required":
        request_status = "operator_action_required"
    operator_action_required = request_status == "operator_action_required"
    operator_message = build_operator_message(
        base_url,
        evidence_path,
        screenshot_paths,
        release_context,
        operator_action_required=operator_action_required,
        operator_evidence=None,
    )
    operator_ask_text_path = current_operator_ask_text_path(operator_draft_root)
    operator_ask_metadata_path = current_operator_ask_metadata_path(operator_draft_root)
    operator_message_sha256 = sha256_text(operator_message)
    send_command = operator_ask_send_command(operator_ask_text_path) if operator_action_required else ""
    return {
        "contract_name": OPERATOR_EVIDENCE_REQUEST_CONTRACT_NAME,
        "generated_at_utc": generated_at_utc or now_iso(),
        "status": request_status,
        "base_url": base_url,
        "request_nonce": request_nonce,
        "request_binding_sha256": binding_sha256,
        "release": release,
        "program_bindings": programs,
        "media_policy": evidence_v2.media_policy(),
        "attestation_contract_name": evidence_v2.ATTESTATION_CONTRACT_NAME,
        "attestation_role": evidence_v2.ATTESTATION_ROLE,
        "required_output_path": str(evidence_path),
        "required_receipt_path": str(evidence_path),
        "required_operator_evidence_path": str(evidence_path),
        "required_proof_path": str(proof_path),
        "request_receipt_path": str(request_path),
        "materialization_scope": materialization_scope,
        "operator_evidence_contract_name": OPERATOR_EVIDENCE_CONTRACT_NAME,
        "required_steps": list(REQUIRED_OPERATOR_STEPS),
        "minimum_screenshot_count": MINIMUM_OPERATOR_SCREENSHOT_COUNT,
        "recommended_screenshot_paths": [str(path) for path in screenshot_paths],
        "template_path": str(template_path),
        "operator_evidence_template_path": str(template_path),
        "release_channel_receipt_path": release_context.get("path") or str(DEFAULT_RELEASE_CHANNEL_PATH),
        "hub_release_channel_receipt_path": str((release.get("hub_registry") or {}).get("manifest_path") or DEFAULT_HUB_RELEASE_CHANNEL_PATH),
        "release_version": release_context.get("version") or None,
        "release_channel": release_context.get("channel") or None,
        "release_supportability_state": release_context.get("supportability_state") or None,
        "release_rollout_state": release_context.get("rollout_state") or None,
        "release_published_at": release_context.get("published_at") or None,
        "summary": "Capture real browser-backed Google linking proof for an existing Chummer account.",
        "operator_message_path": str(operator_ask_text_path),
        "operator_ask_text_path": str(operator_ask_text_path),
        "operator_ask_metadata_path": str(operator_ask_metadata_path),
        "operator_message_sha256": operator_message_sha256,
        "operator_message_preview": text_preview(operator_message),
        "receipt_name": DEFAULT_OPERATOR_ASK_RECEIPT_NAME,
        "send_command": send_command,
    }


def build_operator_telegram_draft(
    *,
    request: dict[str, Any],
    operator_message: str,
) -> dict[str, Any]:
    operator_ask_text_path = Path(
        str(request.get("operator_ask_text_path") or current_operator_ask_text_path())
    )
    operator_ask_metadata_path = Path(
        str(request.get("operator_ask_metadata_path") or current_operator_ask_metadata_path())
    )
    artifact_intake = request.get("artifact_intake") if isinstance(request.get("artifact_intake"), dict) else {}
    request_status = str(request.get("status") or "").strip()
    return {
        "status": (
            "prepared_not_sent"
            if request_status == "operator_action_required"
            else "blocked_not_sendable"
        ),
        "message_path": str(operator_ask_text_path),
        "metadata_path": str(operator_ask_metadata_path),
        "current_message_path": str(operator_ask_text_path),
        "current_metadata_path": str(operator_ask_metadata_path),
        "message_text": operator_message,
        "message_sha256": sha256_text(operator_message),
        "message_preview": text_preview(operator_message),
        "receipt_name": str(request.get("receipt_name") or DEFAULT_OPERATOR_ASK_RECEIPT_NAME),
        "send_command": (
            str(request.get("send_command") or operator_ask_send_command(operator_ask_text_path))
            if request_status == "operator_action_required"
            else ""
        ),
        "request_receipt_path": str(request.get("request_receipt_path") or ""),
        "required_output_path": str(request.get("required_output_path") or ""),
        "required_receipt_path": str(request.get("required_receipt_path") or ""),
        "required_operator_evidence_path": str(request.get("required_operator_evidence_path") or ""),
        "operator_evidence_template_path": str(request.get("operator_evidence_template_path") or request.get("template_path") or ""),
        "release_channel_receipt_path": str(request.get("release_channel_receipt_path") or ""),
        "release_version": str(request.get("release_version") or ""),
        "release_channel": str(request.get("release_channel") or ""),
        "release_supportability_state": str(request.get("release_supportability_state") or ""),
        "release_rollout_state": str(request.get("release_rollout_state") or ""),
        "release_published_at": str(request.get("release_published_at") or ""),
        "preferred_drop_path": str(request.get("preferred_drop_path") or ""),
        "preferred_zip_name": str(request.get("preferred_zip_name") or ""),
        "discover_command": str(artifact_intake.get("discover_command") or ""),
        "import_command": str(artifact_intake.get("import_command") or ""),
        "auto_import_command": str(artifact_intake.get("auto_import_command") or ""),
        "auto_import_watch_command": str(artifact_intake.get("auto_import_watch_command") or ""),
        "base_url": str(request.get("base_url") or ""),
        "request_generated_at_utc": str(request.get("generated_at_utc") or ""),
        "direct_send_allowed": False,
        "direct_send_reason": str(request.get("direct_telegram_reason") or ""),
        "secrets_redacted": True,
    }


def materialize_operator_telegram_draft(draft: dict[str, Any]) -> dict[str, Any]:
    message_path = Path(str(draft.get("message_path") or "").strip())
    metadata_path = Path(str(draft.get("metadata_path") or "").strip())
    current_message_path = Path(str(draft.get("current_message_path") or "").strip())
    current_metadata_path = Path(str(draft.get("current_metadata_path") or "").strip())
    message_text = str(draft.get("message_text") or "")
    if message_path and message_text:
        message_path.parent.mkdir(parents=True, exist_ok=True)
        message_path.write_text(message_text, encoding="utf-8")
    if current_message_path and message_text:
        current_message_path.parent.mkdir(parents=True, exist_ok=True)
        current_message_path.write_text(message_text, encoding="utf-8")

    metadata_payload = {
        "generated_at_utc": str(draft.get("request_generated_at_utc") or now_iso()),
        "status": str(draft.get("status") or "prepared_not_sent"),
        "message_path": str(message_path),
        "current_message_path": str(current_message_path),
        "message_sha256": str(draft.get("message_sha256") or ""),
        "message_preview": str(draft.get("message_preview") or ""),
        "receipt_name": str(draft.get("receipt_name") or ""),
        "send_command": str(draft.get("send_command") or ""),
        "request_receipt_path": str(draft.get("request_receipt_path") or ""),
        "required_output_path": str(draft.get("required_output_path") or ""),
        "required_receipt_path": str(draft.get("required_receipt_path") or ""),
        "required_operator_evidence_path": str(draft.get("required_operator_evidence_path") or ""),
        "operator_evidence_template_path": str(draft.get("operator_evidence_template_path") or ""),
        "operator_ask_text_path": str(current_message_path),
        "operator_ask_metadata_path": str(current_metadata_path),
        "release_channel_receipt_path": str(draft.get("release_channel_receipt_path") or ""),
        "release_version": str(draft.get("release_version") or ""),
        "release_channel": str(draft.get("release_channel") or ""),
        "release_supportability_state": str(draft.get("release_supportability_state") or ""),
        "release_rollout_state": str(draft.get("release_rollout_state") or ""),
        "release_published_at": str(draft.get("release_published_at") or ""),
        "preferred_drop_path": str(draft.get("preferred_drop_path") or ""),
        "preferred_zip_name": str(draft.get("preferred_zip_name") or ""),
        "discover_command": str(draft.get("discover_command") or ""),
        "import_command": str(draft.get("import_command") or ""),
        "auto_import_command": str(draft.get("auto_import_command") or ""),
        "auto_import_watch_command": str(draft.get("auto_import_watch_command") or ""),
        "base_url": str(draft.get("base_url") or ""),
        "direct_send_allowed": bool(draft.get("direct_send_allowed")),
        "direct_send_reason": str(draft.get("direct_send_reason") or ""),
        "secrets_redacted": bool(draft.get("secrets_redacted", True)),
    }
    if metadata_path:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata_payload, indent=2) + "\n", encoding="utf-8")
    if current_metadata_path:
        current_metadata_path.parent.mkdir(parents=True, exist_ok=True)
        current_metadata_payload = {
            **metadata_payload,
            "message_path": str(current_message_path),
            "current_message_path": str(current_message_path),
            "source_message_path": str(message_path),
            "source_metadata_path": str(metadata_path),
        }
        current_metadata_path.write_text(json.dumps(current_metadata_payload, indent=2) + "\n", encoding="utf-8")
        return current_metadata_payload
    return metadata_payload


def materialize(
    output_path: Path = DEFAULT_OUTPUT,
    *,
    base_url: str = DEFAULT_BASE_URL,
    evidence_path: Path | None = None,
    template_path: Path | None = None,
    screenshot_root: Path | None = None,
    operator_draft_root: Path | None = None,
    incoming_evidence_root: Path | None = None,
    proof_path: Path | None = None,
    release_channel_path: Path = DEFAULT_RELEASE_CHANNEL_PATH,
    hub_release_channel_path: Path = DEFAULT_HUB_RELEASE_CHANNEL_PATH,
    live_release_manifest_path: Path | None = None,
) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    if base_url != DEFAULT_BASE_URL:
        raise ValueError(f"Google OAuth production evidence base_url must be {DEFAULT_BASE_URL}")
    paths = resolve_materialization_paths(
        output_path,
        evidence_path=evidence_path,
        template_path=template_path,
        screenshot_root=screenshot_root,
        operator_draft_root=operator_draft_root,
        incoming_evidence_root=incoming_evidence_root,
        proof_path=proof_path,
    )
    canonical = bool(paths["canonical"])
    stage_root = Path(paths["stage_root"])
    output_path = Path(paths["output_path"])
    evidence_path = Path(paths["evidence_path"])
    template_path = Path(paths["template_path"])
    screenshot_root = Path(paths["screenshot_root"])
    operator_draft_root = Path(paths["operator_draft_root"])
    incoming_evidence_root = Path(paths["incoming_evidence_root"])
    proof_path = Path(paths["proof_path"])
    screenshot_root.mkdir(parents=True, exist_ok=True)
    incoming_evidence_root.mkdir(parents=True, exist_ok=True)

    screenshot_paths = [
        screenshot_root / "google-signed-in-state.png",
        screenshot_root / "google-provider-linked.png",
        screenshot_root / "google-sign-in-return.png",
    ]
    previous = load_json(output_path)
    previous_release = previous.get("release") if isinstance(previous.get("release"), dict) else {}
    previous_live = previous_release.get("live") if isinstance(previous_release.get("live"), dict) else {}
    previous_live_path = str(previous_live.get("capture_path") or "")
    effective_live_release_manifest_path = live_release_manifest_path
    if effective_live_release_manifest_path is None and previous_live_path:
        previous_capture = Path(previous_live_path)
        if previous_capture.is_file():
            effective_live_release_manifest_path = previous_capture
    live_capture_path_text = (
        str(effective_live_release_manifest_path.resolve())
        if effective_live_release_manifest_path
        else ""
    )
    live_captured_at_utc = (
        str(previous_live.get("captured_at_utc") or "")
        if live_capture_path_text and previous_live_path == live_capture_path_text
        else (now_iso() if effective_live_release_manifest_path else "")
    )
    release_context = read_release_context(
        release_channel_path,
        hub_release_channel_path=hub_release_channel_path,
        live_release_manifest_path=effective_live_release_manifest_path,
        live_captured_at_utc=live_captured_at_utc,
    )
    programs = evidence_v2.program_bindings()
    release_authority = release_context["authority"]
    binding_sha256 = evidence_v2.request_binding_sha256(
        base_url=base_url,
        release=release_authority,
        programs=programs,
    )
    request_nonce, generated_at_utc, _reused = evidence_v2.reusable_request_identity(
        previous,
        binding_sha256=binding_sha256,
        now=evidence_v2.utc_now(),
    )
    request_status = (
        "operator_action_required"
        if release_authority.get("ready") is True
        else "blocked_release_authority"
    )
    request = build_request(
        output_path,
        base_url,
        evidence_path,
        template_path,
        screenshot_paths,
        release_context,
        proof_path=proof_path,
        operator_draft_root=operator_draft_root,
        materialization_scope={
            "mode": "canonical" if canonical else "staged",
            "root": str(stage_root),
            "self_contained": not canonical,
            "proof_output_path": str(proof_path),
        },
        request_status=request_status,
        operator_evidence=None,
        request_nonce=request_nonce,
        generated_at_utc=generated_at_utc,
        program_bindings=programs,
    )
    release_version = release_context.get("version") or "unknown"
    actionable = request_status == "operator_action_required"
    preferred_zip_name = (
        f"google-oauth-linking-operator-evidence-{release_version}.zip"
        if actionable
        else ""
    )
    preferred_drop_path = (
        incoming_evidence_root / preferred_zip_name
        if preferred_zip_name
        else None
    )
    scan_roots = [incoming_evidence_root]
    discovery_roots = (
        artifact_discovery_roots(incoming_evidence_root)
        if canonical
        else [incoming_evidence_root]
    )
    discover_command = (
        "python3 ~/.codex/skills/ea-artifact-intake/scripts/artifact_intake.py discover "
        f"--pattern {json.dumps(DEFAULT_BUNDLE_PATTERN)} "
        + " ".join(f"--root {json.dumps(portable_path_text(path))}" for path in discovery_roots)
    )
    import_argv = (
        [
            "python3",
            "scripts/import_google_oauth_linking_operator_evidence_artifact.py",
            str(preferred_drop_path),
            "--intake-request",
            str(output_path),
            "--verify",
        ]
        if preferred_drop_path is not None
        else []
    )
    auto_import_argv = (
        [
            "python3",
            "scripts/auto_import_google_oauth_linking_operator_evidence.py",
            "--base-url",
            base_url,
            "--intake-request",
            str(output_path),
        ]
        if actionable
        else []
    )
    auto_import_watch_argv = (
        [*auto_import_argv, "--wait-seconds", "900", "--poll-seconds", "10", "--refresh-intake-request"]
        if actionable
        else []
    )
    post_import_argv_plan_value = (
        post_import_argv_plan(
            base_url,
            request_path=output_path,
            evidence_path=evidence_path,
            proof_path=proof_path,
        )
        if actionable
        else []
    )
    expected_patterns = (
        [DEFAULT_BUNDLE_PATTERN, preferred_zip_name, Path(str(evidence_path)).name]
        if actionable
        else []
    )
    request.update(
        {
            "provider": "browser_operator",
            "artifact_kind": "google_oauth_linking_operator_evidence_bundle",
            "preferred_drop_folder": str(incoming_evidence_root),
            "preferred_zip_name": preferred_zip_name or None,
            "required_zip_filename": preferred_zip_name or None,
            "preferred_drop_path": str(preferred_drop_path) if preferred_drop_path else "",
            "artifact_intake": {
                "dedicated_drop_root": str(incoming_evidence_root),
                "dedicated_drop_root_gitignored": is_gitignored_runtime_root(incoming_evidence_root),
                "preferred_drop_path": str(preferred_drop_path) if preferred_drop_path else "",
                "expected_patterns": expected_patterns,
                "discover_command": portable_command_text(discover_command) if actionable else "",
                "import_argv": import_argv,
                "auto_import_argv": auto_import_argv,
                "auto_import_watch_argv": auto_import_watch_argv,
                "auto_import_roots": [portable_path_text(path) for path in discovery_roots],
                "post_import_argv_plan": post_import_argv_plan_value,
                "post_import_verify_note": (
                    POST_IMPORT_VERIFY_NOTE
                    if actionable
                    else "Execution remains disabled until a freshly regenerated request has exact release authority."
                ),
            },
            "expected_artifact_patterns": expected_patterns,
            "drop_roots_checked": [portable_path_text(path) for path in scan_roots],
            "import_argv": import_argv,
            "summary": (
                "Capture real browser-backed Google linking proof for an existing Chummer account."
                if actionable
                else "Google operator intake is blocked until portal, hub-registry, and captured live release manifests agree exactly."
            ),
            "secrets_redacted": True,
            "direct_telegram_sent": False,
            "direct_telegram_reason": (
                "Not sent without an explicit operator-send instruction in this turn."
                if actionable
                else "Not sendable while release authority bindings disagree or the live manifest is uncaptured."
            ),
            "recovery": {
                "status": request_status,
                "execution_authority_present": actionable,
                "summary": (
                    "Operator evidence intake is available for the exact current release authority."
                    if actionable
                    else "Operator evidence intake is paused. No message, discovery, import, watch, or post-import action is authorized until release authority agrees."
                ),
                "release_authority_blockers": list(release_authority.get("blockers") or []),
                "required_conditions": (
                    []
                    if actionable
                    else [
                        "Portal and Hub registry release identity and posture must agree exactly.",
                        "An explicit current live release manifest capture must match the agreed release.",
                        "Regenerate and verify a fresh request after those conditions hold.",
                    ]
                ),
            },
        }
    )
    request["intake"] = request["artifact_intake"]
    request["preferredDropPath"] = request["preferred_drop_path"]
    operator_message = build_operator_message(
        base_url,
        evidence_path,
        screenshot_paths,
        release_context,
        operator_action_required=request_status == "operator_action_required",
        operator_evidence=None,
        template_path=template_path,
        preferred_drop_path=preferred_drop_path,
        import_command=shlex.join(import_argv) if import_argv else "",
        auto_import_watch_command=shlex.join(auto_import_watch_argv) if actionable else "",
    )
    request["operator_message_sha256"] = sha256_text(operator_message)
    request["operator_message_preview"] = text_preview(operator_message)
    template = build_template(base_url, screenshot_paths, request=request)
    operator_telegram_draft = build_operator_telegram_draft(
        request=request,
        operator_message=operator_message,
    )
    request["operator_telegram_draft"] = operator_telegram_draft
    request["operator_telegram_draft_materialized"] = materialize_operator_telegram_draft(operator_telegram_draft)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")

    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
    return request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize the operator request for Google OAuth linking evidence.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--evidence-path", type=Path, default=None)
    parser.add_argument("--proof-path", type=Path, default=None)
    parser.add_argument("--template-path", type=Path, default=None)
    parser.add_argument("--screenshot-root", type=Path, default=None)
    parser.add_argument("--operator-draft-root", type=Path, default=None)
    parser.add_argument("--incoming-evidence-root", type=Path, default=None)
    parser.add_argument("--release-channel-path", type=Path, default=DEFAULT_RELEASE_CHANNEL_PATH)
    parser.add_argument("--hub-release-channel-path", type=Path, default=DEFAULT_HUB_RELEASE_CHANNEL_PATH)
    parser.add_argument(
        "--live-release-manifest-path",
        type=Path,
        default=None,
        help="Explicit local capture of the live canonical manifest. This command never fetches it implicitly.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = materialize(
        args.output,
        base_url=args.base_url,
        evidence_path=args.evidence_path,
        proof_path=args.proof_path,
        template_path=args.template_path,
        screenshot_root=args.screenshot_root,
        operator_draft_root=args.operator_draft_root,
        incoming_evidence_root=args.incoming_evidence_root,
        release_channel_path=args.release_channel_path,
        hub_release_channel_path=args.hub_release_channel_path,
        live_release_manifest_path=args.live_release_manifest_path,
    )
    print(f"google_oauth_linking_operator_evidence_request:{payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
