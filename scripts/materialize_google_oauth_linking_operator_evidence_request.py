#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from materialize_google_oauth_linking_proof import (
    DEFAULT_BASE_URL,
    DEFAULT_OPERATOR_EVIDENCE_PATH,
    OPERATOR_EVIDENCE_CONTRACT_NAME,
    OPERATOR_EVIDENCE_REQUEST_CONTRACT_NAME,
    REQUIRED_OPERATOR_STEPS,
    MINIMUM_OPERATOR_SCREENSHOT_COUNT,
    inspect_operator_evidence,
    sha256_text,
)
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
DEFAULT_PORTAL_RELEASE_CHANNEL_PATH = RUN_SERVICES_ROOT / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json"
DEFAULT_PUBLISHED_PORTAL_RELEASE_CHANNEL_PATH = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "portal" / "RELEASE_CHANNEL.generated.json"
DEFAULT_RELEASE_CHANNEL_PATH = ROOT / "chummer-hub-registry" / ".codex-studio" / "published" / "RELEASE_CHANNEL.generated.json"
DEFAULT_SHARED_RUN_SERVICES_ROOT = Path(
    os.environ.get("CHUMMER_SHARED_RUN_SERVICES_ROOT") or "/docker/chummercomplete/chummer.run-services"
)
DEFAULT_SHARED_PORTAL_RELEASE_CHANNEL_PATH = (
    DEFAULT_SHARED_RUN_SERVICES_ROOT / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json"
)
DEFAULT_SHARED_PUBLISHED_PORTAL_RELEASE_CHANNEL_PATH = (
    DEFAULT_SHARED_RUN_SERVICES_ROOT / ".codex-studio" / "published" / "portal" / "RELEASE_CHANNEL.generated.json"
)
DEFAULT_BUNDLE_PATTERN = "*google-oauth-linking-operator-evidence*.zip"
DISCOVERY_MAX_DEPTH = 6
POST_IMPORT_COMMANDS = [
    "python3 scripts/materialize_google_oauth_linking_operator_evidence_request.py --base-url https://chummer.run",
    "python3 scripts/verify_google_oauth_linking_operator_evidence_request.py",
    "python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run",
    "python3 scripts/verify_google_oauth_linking_proof.py --require-pass",
    "python3 scripts/verify_flagship_product_readiness_gate.py --summary-output .codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json",
    "python3 scripts/materialize_release_ready_receipt.py",
    "python3 scripts/materialize_operator_release_dashboard.py --release-ready-self-check",
    "python3 scripts/final_gold_janitor.py --skip-materializers",
]


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


def artifact_discovery_roots(dedicated_drop_root: Path) -> list[Path]:
    home = Path.home()
    roots = [
        dedicated_drop_root,
        home / "Downloads",
        home / "pCloud Drive" / "EA",
    ]
    return unique_paths(roots)


def build_auto_import_command(
    request_path: Path,
    *,
    wait_seconds: float | None = None,
    poll_seconds: float | None = None,
    refresh_intake_request: bool = False,
) -> str:
    command = (
        "python3 scripts/auto_import_google_oauth_linking_operator_evidence.py "
        f"--intake-request {request_path}"
    )
    if wait_seconds is not None:
        command += f" --wait-seconds {int(wait_seconds)}"
    if poll_seconds is not None:
        command += f" --poll-seconds {int(poll_seconds)}"
    if refresh_intake_request:
        command += " --refresh-intake-request"
    return command


def release_context_candidate_paths(release_channel_path: Path) -> list[Path]:
    candidates = [
        release_channel_path,
        DEFAULT_PORTAL_RELEASE_CHANNEL_PATH,
        DEFAULT_PUBLISHED_PORTAL_RELEASE_CHANNEL_PATH,
        ROOT / "chummer.run-services" / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json",
        ROOT / "chummer.run-services" / ".codex-studio" / "published" / "portal" / "RELEASE_CHANNEL.generated.json",
        DEFAULT_SHARED_PORTAL_RELEASE_CHANNEL_PATH,
        DEFAULT_SHARED_PUBLISHED_PORTAL_RELEASE_CHANNEL_PATH,
        DEFAULT_RELEASE_CHANNEL_PATH,
    ]
    return unique_paths(candidates)


def read_release_context(release_channel_path: Path) -> dict[str, str]:
    for candidate in release_context_candidate_paths(release_channel_path):
        payload = load_json(candidate)
        version = str(payload.get("version") or payload.get("releaseVersion") or "").strip()
        channel = str(payload.get("channelId") or payload.get("channel") or "").strip()
        supportability_state = str(payload.get("supportabilityState") or "").strip()
        rollout_state = str(payload.get("rolloutState") or "").strip()
        published_at = str(payload.get("publishedAt") or payload.get("published_at") or "").strip()
        if version or channel or supportability_state or rollout_state or published_at:
            return {
                "path": str(candidate),
                "version": version,
                "channel": channel,
                "supportability_state": supportability_state,
                "rollout_state": rollout_state,
                "published_at": published_at,
            }

    return {
        "path": str(release_channel_path),
        "version": "",
        "channel": "",
        "supportability_state": "",
        "rollout_state": "",
        "published_at": "",
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
            f"Or watch for the bundle automatically with: {auto_import_watch_command}" if auto_import_watch_command else "",
            "Then complete the operator evidence template and write the finished receipt to the required path.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_template(base_url: str, screenshot_paths: list[Path]) -> dict[str, Any]:
    return {
        "contract_name": OPERATOR_EVIDENCE_CONTRACT_NAME,
        "status": "pass",
        "base_url": base_url,
        "observed_at_utc": "",
        "verified_steps": list(REQUIRED_OPERATOR_STEPS),
        "screenshot_paths": [str(path) for path in screenshot_paths],
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
    request_status: str,
    operator_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    operator_action_required = request_status == "operator_action_required"
    operator_message = build_operator_message(
        base_url,
        evidence_path,
        screenshot_paths,
        release_context,
        operator_action_required=operator_action_required,
        operator_evidence=operator_evidence,
    )
    operator_ask_text_path = current_operator_ask_text_path()
    operator_ask_metadata_path = current_operator_ask_metadata_path()
    operator_message_sha256 = sha256_text(operator_message)
    send_command = operator_ask_send_command(operator_ask_text_path)
    return {
        "contract_name": OPERATOR_EVIDENCE_REQUEST_CONTRACT_NAME,
        "generated_at_utc": now_iso(),
        "status": request_status,
        "base_url": base_url,
        "required_output_path": str(evidence_path),
        "required_receipt_path": str(evidence_path),
        "required_operator_evidence_path": str(evidence_path),
        "request_receipt_path": str(request_path),
        "operator_evidence_contract_name": OPERATOR_EVIDENCE_CONTRACT_NAME,
        "required_steps": list(REQUIRED_OPERATOR_STEPS),
        "minimum_screenshot_count": MINIMUM_OPERATOR_SCREENSHOT_COUNT,
        "recommended_screenshot_paths": [str(path) for path in screenshot_paths],
        "template_path": str(template_path),
        "operator_evidence_template_path": str(template_path),
        "release_channel_receipt_path": release_context.get("path") or str(DEFAULT_RELEASE_CHANNEL_PATH),
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
        "operator_ask_receipt_name": DEFAULT_OPERATOR_ASK_RECEIPT_NAME,
        "operator_ask_send_command": send_command,
    }


def build_operator_telegram_draft(
    *,
    request: dict[str, Any],
    operator_message: str,
) -> dict[str, Any]:
    operator_ask_text_path = current_operator_ask_text_path()
    operator_ask_metadata_path = current_operator_ask_metadata_path()
    artifact_intake = request.get("artifact_intake") if isinstance(request.get("artifact_intake"), dict) else {}
    return {
        "status": "prepared_not_sent" if str(request.get("status") or "").strip() == "operator_action_required" else "not_required",
        "message_path": str(operator_ask_text_path),
        "metadata_path": str(operator_ask_metadata_path),
        "current_message_path": str(operator_ask_text_path),
        "current_metadata_path": str(operator_ask_metadata_path),
        "message_text": operator_message,
        "message_sha256": sha256_text(operator_message),
        "message_preview": text_preview(operator_message),
        "receipt_name": str(request.get("receipt_name") or DEFAULT_OPERATOR_ASK_RECEIPT_NAME),
        "send_command": str(request.get("send_command") or operator_ask_send_command(operator_ask_text_path)),
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
        "generated_at_utc": now_iso(),
        "status": str(draft.get("status") or "prepared_not_sent"),
        "message_path": str(message_path),
        "current_message_path": str(current_message_path),
        "message_sha256": str(draft.get("message_sha256") or ""),
        "message_preview": str(draft.get("message_preview") or ""),
        "receipt_name": str(draft.get("receipt_name") or ""),
        "send_command": str(draft.get("send_command") or ""),
        "operator_ask_receipt_name": str(draft.get("receipt_name") or ""),
        "operator_ask_send_command": str(draft.get("send_command") or ""),
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
    evidence_path: Path = DEFAULT_OPERATOR_EVIDENCE_PATH,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    screenshot_root: Path = DEFAULT_SCREENSHOT_ROOT,
    release_channel_path: Path = DEFAULT_RELEASE_CHANNEL_PATH,
) -> dict[str, Any]:
    screenshot_root.mkdir(parents=True, exist_ok=True)
    DEFAULT_INCOMING_EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)

    screenshot_paths = [
        screenshot_root / "google-signed-in-state.png",
        screenshot_root / "google-provider-linked.png",
        screenshot_root / "google-sign-in-return.png",
    ]
    release_context = read_release_context(release_channel_path)
    operator_evidence = inspect_operator_evidence(base_url, evidence_path)
    request_status = "not_required" if operator_evidence.get("pass") is True else "operator_action_required"
    request = build_request(
        output_path,
        base_url,
        evidence_path,
        template_path,
        screenshot_paths,
        release_context,
        request_status=request_status,
        operator_evidence=operator_evidence,
    )
    release_version = release_context.get("version") or "unknown"
    preferred_zip_name = f"google-oauth-linking-operator-evidence-{release_version}.zip"
    preferred_drop_path = DEFAULT_INCOMING_EVIDENCE_ROOT / preferred_zip_name
    scan_roots = [DEFAULT_INCOMING_EVIDENCE_ROOT]
    discovery_roots = artifact_discovery_roots(DEFAULT_INCOMING_EVIDENCE_ROOT)
    discover_command = (
        "python3 ~/.codex/skills/ea-artifact-intake/scripts/artifact_intake.py discover "
        f"--pattern {json.dumps(DEFAULT_BUNDLE_PATTERN)} "
        + " ".join(f"--root {json.dumps(portable_path_text(path))}" for path in discovery_roots)
    )
    import_command = (
        "python3 scripts/import_google_oauth_linking_operator_evidence_artifact.py "
        f"{preferred_drop_path} --verify"
    )
    post_import_commands = list(POST_IMPORT_COMMANDS)
    request.update(
        {
            "provider": "browser_operator",
            "artifact_kind": "google_oauth_linking_operator_evidence_bundle",
            "preferred_drop_folder": str(DEFAULT_INCOMING_EVIDENCE_ROOT),
            "preferred_zip_name": preferred_zip_name,
            "required_zip_filename": preferred_zip_name,
            "preferred_drop_path": str(preferred_drop_path),
            "artifact_intake": {
                "dedicated_drop_root": str(DEFAULT_INCOMING_EVIDENCE_ROOT),
                "dedicated_drop_root_gitignored": is_gitignored_runtime_root(DEFAULT_INCOMING_EVIDENCE_ROOT),
                "preferred_drop_path": str(preferred_drop_path),
                "expected_patterns": [
                    DEFAULT_BUNDLE_PATTERN,
                    preferred_zip_name,
                    Path(str(evidence_path)).name,
                ],
                "discover_command": portable_command_text(discover_command),
                "import_command": import_command,
                "auto_import_command": build_auto_import_command(output_path),
                "auto_import_watch_command": build_auto_import_command(
                    output_path,
                    wait_seconds=900,
                    poll_seconds=10,
                    refresh_intake_request=True,
                ),
                "auto_import_roots": [portable_path_text(path) for path in discovery_roots],
                "post_import_verify_command": "python3 scripts/verify_google_oauth_linking_proof.py --require-pass",
                "post_import_commands": post_import_commands,
            },
            "expected_artifact_patterns": [
                DEFAULT_BUNDLE_PATTERN,
                preferred_zip_name,
                Path(str(evidence_path)).name,
            ],
            "drop_roots_checked": [portable_path_text(path) for path in scan_roots],
            "import_command": import_command,
            "post_import_gates": post_import_commands,
            "current_operator_evidence": operator_evidence,
            "summary": (
                "Current browser-backed Google linking proof already exists; no operator action required."
                if request_status == "not_required"
                else "Capture real browser-backed Google linking proof for an existing Chummer account."
            ),
            "secrets_redacted": True,
            "direct_telegram_sent": False,
            "direct_telegram_reason": (
                "Operator evidence is already present and valid for the current request."
                if request_status == "not_required"
                else "Not sent without an explicit operator-send instruction in this turn."
            ),
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
        operator_evidence=operator_evidence,
        template_path=template_path,
        preferred_drop_path=preferred_drop_path,
        import_command=import_command,
        auto_import_watch_command=build_auto_import_command(
            output_path,
            wait_seconds=900,
            poll_seconds=10,
            refresh_intake_request=True,
        ),
    )
    request["operator_message_sha256"] = sha256_text(operator_message)
    request["operator_message_preview"] = text_preview(operator_message)
    template = build_template(base_url, screenshot_paths)
    operator_telegram_draft = build_operator_telegram_draft(
        request=request,
        operator_message=operator_message,
    )
    request["operator_telegram_draft"] = operator_telegram_draft
    materialized_draft = materialize_operator_telegram_draft(operator_telegram_draft)
    request["operator_telegram_draft_materialized"] = materialized_draft
    request["operator_ask_send_command"] = str(
        materialized_draft.get("operator_ask_send_command")
        or materialized_draft.get("send_command")
        or request.get("send_command")
        or ""
    )
    request["operator_ask_receipt_name"] = str(
        materialized_draft.get("operator_ask_receipt_name")
        or materialized_draft.get("receipt_name")
        or request.get("receipt_name")
        or ""
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")

    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
    return request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize the operator request for Google OAuth linking evidence.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--evidence-path", type=Path, default=DEFAULT_OPERATOR_EVIDENCE_PATH)
    parser.add_argument("--release-channel-path", type=Path, default=DEFAULT_RELEASE_CHANNEL_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = materialize(
        args.output,
        base_url=args.base_url,
        evidence_path=args.evidence_path,
        release_channel_path=args.release_channel_path,
    )
    print(f"google_oauth_linking_operator_evidence_request:{payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
