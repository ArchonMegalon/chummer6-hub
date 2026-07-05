#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_flagship_product_readiness_gate import current_release_truth_launch_blockers


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
ROOT = RUN_SERVICES_ROOT.parent
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
REGISTRY_ROOT = ROOT / "chummer-hub-registry" / ".codex-studio" / "published"
SHARED_WORKSPACE_ROOT = Path(os.environ.get("CHUMMER_SHARED_WORKSPACE_ROOT") or "/docker/chummercomplete")
SHARED_REGISTRY_ROOT = SHARED_WORKSPACE_ROOT / "chummer-hub-registry" / ".codex-studio" / "published"
SHARED_RUN_SERVICES_ROOT = Path(
    os.environ.get("CHUMMER_SHARED_RUN_SERVICES_ROOT") or "/docker/chummercomplete/chummer.run-services"
)
OUTPUT_JSON = PUBLISHED_ROOT / "OPERATOR_RELEASE_DASHBOARD.generated.json"
OUTPUT_MD = PUBLISHED_ROOT / "OPERATOR_RELEASE_DASHBOARD.md"


def resolve_completion_root() -> Path:
    explicit = os.environ.get("CHUMMER_OPERATOR_COMPLETION_ROOT") or os.environ.get("CHUMMER_UI_COMPLETION_ROOT")
    if explicit:
        return Path(explicit).expanduser()
    candidates = [
        ROOT / "_completion" / "chummer_run_redesign_closure",
        Path("/docker/chummercomplete/_completion/chummer_run_redesign_closure"),
    ]
    for candidate in candidates:
        if (candidate / "UI_FRAME_INTEGRITY.generated.json").is_file():
            return candidate
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


COMPLETION_ROOT = resolve_completion_root()


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def normalized_strings(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = str(value).strip()
        if not candidate:
            continue
        folded = candidate.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        result.append(candidate)
    return result


def safe_current_release_truth_blockers() -> list[str]:
    try:
        blockers = current_release_truth_launch_blockers()
    except Exception as exc:  # pragma: no cover - defensive surface only
        return [f"release truth blocker inspection failed: {exc}"]
    return normalized_strings(blockers)


def resolve_release_channel_path() -> Path:
    explicit = os.environ.get("CHUMMER_OPERATOR_RELEASE_CHANNEL_PATH") or os.environ.get("CHUMMER_RELEASE_CHANNEL_PATH")
    candidates = unique_paths(
        [
            Path(explicit).expanduser() if explicit else REGISTRY_ROOT / "RELEASE_CHANNEL.generated.json",
            REGISTRY_ROOT / "RELEASE_CHANNEL.generated.json",
            SHARED_REGISTRY_ROOT / "RELEASE_CHANNEL.generated.json",
            RUN_SERVICES_ROOT / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json",
            RUN_SERVICES_ROOT / ".codex-studio" / "published" / "portal" / "RELEASE_CHANNEL.generated.json",
            SHARED_RUN_SERVICES_ROOT / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json",
            SHARED_RUN_SERVICES_ROOT / ".codex-studio" / "published" / "portal" / "RELEASE_CHANNEL.generated.json",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def is_pass(payload: dict[str, Any]) -> bool:
    return str(payload.get("status") or "").strip().lower() in {"pass", "passed", "ready"}


def normalize_base_url(value: object) -> str:
    return str(value or "").strip().rstrip("/")


def public_safe_base_url(value: object) -> str | None:
    base_url = normalize_base_url(value)
    parsed = urlparse(base_url)
    if parsed.scheme == "https" and parsed.netloc.lower() == "chummer.run":
        return base_url
    return None


def customer_safe_release_text(value: object) -> str:
    text = str(value or "").strip()
    replacements = (
        ("Current release proof is green", "Current release checks are clear"),
        ("proof is green", "release checks are clear"),
        ("startup-smoke proof", "startup verification"),
        ("startup-smoke", "startup verification"),
        ("executable-gate proof", "executable verification"),
        ("executable-gate", "executable"),
        ("promoted flagship bytes", "promoted release packages"),
        ("proof", "checks"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
        text = text.replace(old.capitalize(), new.capitalize())
    return text


def gate(name: str, path: Path, payload: dict[str, Any] | None = None, *, accepted_statuses: set[str] | None = None) -> dict[str, Any]:
    loaded = payload if payload is not None else load_json(path)
    status = str(loaded.get("status") or "").strip().lower()
    accepted = accepted_statuses or {"pass", "passed", "ready"}
    return {
        "path": str(path),
        "exists": path.is_file(),
        "status": loaded.get("status", "missing"),
        "verdict": loaded.get("verdict"),
        "generated_at_utc": loaded.get("generated_at_utc")
        or loaded.get("generatedAtUtc")
        or loaded.get("generatedAt")
        or loaded.get("generated_at"),
        "pass": path.is_file() and status in accepted,
    }


def build_payload(*, release_ready_self_check: bool = False) -> dict[str, Any]:
    release_channel_path = resolve_release_channel_path()
    release_channel = load_json(release_channel_path)
    mirror_path = PUBLISHED_ROOT / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json"
    mirror = load_json(mirror_path)
    ruleset_path = PUBLISHED_ROOT / "RULESET_READINESS.generated.json"
    ruleset = load_json(ruleset_path)
    public_route_proof_path = PUBLISHED_ROOT / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"
    public_route_proof = load_json(public_route_proof_path)
    ui_frame_path = COMPLETION_ROOT / "UI_FRAME_INTEGRITY.generated.json"
    ui_frame = load_json(ui_frame_path)
    design_path = PUBLISHED_ROOT / "DESIGN_QUALITY_GATE.generated.json"
    design = load_json(design_path)
    copy_path = PUBLISHED_ROOT / "PUBLIC_COPY_LEAK_GATE.generated.json"
    copy_gate = load_json(copy_path)
    participate_billing_honesty_path = PUBLISHED_ROOT / "PARTICIPATE_BILLING_HONESTY.generated.json"
    participate_billing_honesty = load_json(participate_billing_honesty_path)
    account_handoff_runtime_config_path = PUBLISHED_ROOT / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json"
    account_handoff_runtime_config = load_json(account_handoff_runtime_config_path)
    public_edge_postdeploy_path = PUBLISHED_ROOT / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
    public_edge_postdeploy = load_json(public_edge_postdeploy_path)
    release_ready_path = PUBLISHED_ROOT / "RELEASE_READY.generated.json"
    release_ready = load_json(release_ready_path)
    final_gold_path = PUBLISHED_ROOT / "FINAL_GOLD_JANITOR.generated.json"
    final_gold = load_json(final_gold_path)
    oauth_path = PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
    oauth = load_json(oauth_path)
    windows_visual_audit_path = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
    windows_visual_audit = load_json(windows_visual_audit_path)
    windows_visual_intake_path = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
    windows_visual_intake = load_json(windows_visual_intake_path)

    checks = {
        "release_channel": gate("release_channel", release_channel_path, release_channel, accepted_statuses={"published", "pass", "passed", "ready"}),
        "external_distribution_mirror_proof": gate("external_distribution_mirror_proof", mirror_path, mirror),
        "ruleset_readiness": gate("ruleset_readiness", ruleset_path, ruleset),
        "ui_frame_integrity": gate("ui_frame_integrity", ui_frame_path, ui_frame),
        "design_quality_gate": gate("design_quality_gate", design_path, design),
        "public_copy_leak_gate": gate("public_copy_leak_gate", copy_path, copy_gate),
        "participate_billing_honesty": gate("participate_billing_honesty", participate_billing_honesty_path, participate_billing_honesty),
        "account_handoff_runtime_config": gate("account_handoff_runtime_config", account_handoff_runtime_config_path, account_handoff_runtime_config),
        "public_edge_postdeploy_gate": gate("public_edge_postdeploy_gate", public_edge_postdeploy_path, public_edge_postdeploy),
        "release_ready": gate("release_ready", release_ready_path, release_ready),
        "final_gold_janitor": gate("final_gold_janitor", final_gold_path, final_gold),
        "google_oauth_linking_proof": gate("google_oauth_linking_proof", oauth_path, oauth),
        "windows_installer_visual_audit": gate("windows_installer_visual_audit", windows_visual_audit_path, windows_visual_audit),
        "windows_installer_visual_audit_intake_request": gate(
            "windows_installer_visual_audit_intake_request",
            windows_visual_intake_path,
            windows_visual_intake,
            accepted_statuses={"external_artifact_required", "pass", "passed", "ready"},
        ),
    }

    # OAuth is a durable account-linking proof; it is surfaced as operator context but not required
    # to be fresh for every artifact publish because it exercises a third-party browser handoff.
    checks["google_oauth_linking_proof"]["release_blocking"] = False
    checks["release_ready"]["release_blocking"] = False
    checks["final_gold_janitor"]["release_blocking"] = False
    checks["windows_installer_visual_audit"]["release_blocking"] = False
    checks["windows_installer_visual_audit_intake_request"]["release_blocking"] = False
    required_names = [
        name
        for name, data in checks.items()
        if isinstance(data, dict) and data.get("release_blocking", True)
    ]
    failures = [name for name in required_names if not checks[name]["pass"]]
    # Keep the dashboard's full-release signal acyclic: it can depend on
    # prereq release gates, but not on the final gold aggregator that also
    # reads this dashboard.
    full_release_gate_names = [
        "release_ready",
        "windows_installer_visual_audit",
    ]
    full_release_blockers = [name for name in full_release_gate_names if not checks[name]["pass"]]
    full_release_ready = not failures and not full_release_blockers
    verdict = "OPERABLE_RELEASE_BLOCKED"
    if not failures:
        verdict = "OPERABLE_RELEASE_READY" if full_release_ready else "NIGHTLY_HANDOFF_READY"

    providers = {
        provider: data.get("status")
        for provider, data in (mirror.get("providers") or {}).items()
        if isinstance(data, dict)
    }
    frame_base_url = public_safe_base_url(ui_frame.get("base_url")) or public_safe_base_url(public_route_proof.get("base_url"))
    rulesets = {
        ruleset_name: {
            "status": data.get("status"),
            "workflow_parity_status": data.get("workflow_parity_status"),
            "human_side_gold_assumption": data.get("human_side_gold_assumption"),
        }
        for ruleset_name, data in (ruleset.get("rulesets") or {}).items()
        if isinstance(data, dict)
    }
    frame_summary = ui_frame.get("summary") if isinstance(ui_frame.get("summary"), dict) else {}
    visual_artifact = windows_visual_audit.get("artifact") if isinstance(windows_visual_audit.get("artifact"), dict) else {}
    visual_source = windows_visual_audit.get("visualAuditSource") if isinstance(windows_visual_audit.get("visualAuditSource"), dict) else {}
    intake_promoted = windows_visual_intake.get("promoted_installer") if isinstance(windows_visual_intake.get("promoted_installer"), dict) else {}
    intake_discovery = windows_visual_intake.get("last_discovery") if isinstance(windows_visual_intake.get("last_discovery"), dict) else {}
    intake_visual_sources = intake_discovery.get("visual_sources") if isinstance(intake_discovery.get("visual_sources"), dict) else {}
    intake_gold_zip = intake_discovery.get("gold_proof_zip") if isinstance(intake_discovery.get("gold_proof_zip"), dict) else {}
    intake_operator_request = windows_visual_intake.get("operator_request") if isinstance(windows_visual_intake.get("operator_request"), dict) else {}
    oauth_operator_evidence = oauth.get("operator_end_to_end_evidence") if isinstance(oauth.get("operator_end_to_end_evidence"), dict) else {}
    oauth_request_artifacts = oauth.get("operator_request_artifacts") if isinstance(oauth.get("operator_request_artifacts"), dict) else {}
    release_ready_failures = normalized_strings(release_ready.get("failures"))
    release_ready_failed_gates = normalized_strings(release_ready.get("failed_gates"))
    release_ready_truth_blockers = normalized_strings(release_ready.get("release_truth_blockers"))
    if release_ready_self_check and not checks["release_ready"]["pass"]:
        release_ready_truth_blockers = safe_current_release_truth_blockers()
    windows_visual_failures = normalized_strings(windows_visual_audit.get("failures"))
    full_release_blocker_details = normalized_strings(
        (
            release_ready_truth_blockers
            or release_ready_failures
            or (["release_ready"] if not checks["release_ready"]["pass"] else [])
        )
        + (
            windows_visual_failures
            or (["windows_installer_visual_audit"] if not checks["windows_installer_visual_audit"]["pass"] else [])
        )
    )

    return {
        "contract_name": "chummer.operator_release_dashboard",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "verdict": verdict,
        "release_readiness": {
            "full_release_ready": full_release_ready,
            "nightly_handoff_ready": not failures,
            "full_release_blockers": full_release_blockers,
            "full_release_blocker_details": full_release_blocker_details,
            "release_ready_failed_gates": release_ready_failed_gates,
            "release_ready_truth_blockers": release_ready_truth_blockers,
            "release_ready_truth_blocker_count": len(release_ready_truth_blockers),
            "release_ready_self_check": release_ready_self_check,
        },
        "release": {
            "version": release_channel.get("version"),
            "published_at": release_channel.get("publishedAt") or release_channel.get("published_at"),
            "channel": release_channel.get("channel") or release_channel.get("channelId"),
            "rollout_state": release_channel.get("rolloutState"),
            "supportability_state": release_channel.get("supportabilityState"),
            "known_issue_summary": customer_safe_release_text(release_channel.get("knownIssueSummary")),
        },
        "mirrors": {
            "external_required": mirror.get("external_required"),
            "required_providers": mirror.get("required_providers"),
            "providers": providers,
        },
        "rulesets": rulesets,
        "ui": {
            "frame_base_url": frame_base_url,
            "frame_checked_pages": frame_summary.get("checked_pages"),
            "frame_failure_count": frame_summary.get("failure_count"),
            "design_verdict": design.get("verdict"),
        },
        "public_edge": {
            "status": public_edge_postdeploy.get("status"),
            "release_manifest_version": public_edge_postdeploy.get("releaseManifestVersion"),
            "visible_version": public_edge_postdeploy.get("visibleVersion"),
            "navigation_status": public_edge_postdeploy.get("navigationStatus"),
            "pwa_static_status": public_edge_postdeploy.get("pwaStaticStatus"),
            "mobile_ledger_status": public_edge_postdeploy.get("mobileLedgerStatus"),
            "mobile_ledger_payload_status": public_edge_postdeploy.get("mobileLedgerPayloadStatus"),
            "ready_mobile_handoff_status": public_edge_postdeploy.get("readyMobileHandoffStatus"),
            "participate_iframe_shell_status": public_edge_postdeploy.get("participateIframeShellStatus"),
            "flagship_horizons_status": public_edge_postdeploy.get("flagshipHorizonsStatus"),
        },
        "google_oauth_linking": {
            "status": oauth.get("status"),
            "failures": oauth.get("failures") if isinstance(oauth.get("failures"), list) else [],
            "operator_evidence_pass": oauth_operator_evidence.get("pass"),
            "operator_evidence_exists": oauth_operator_evidence.get("exists"),
            "operator_evidence_path": oauth_operator_evidence.get("path"),
            "request_artifacts_pass": oauth_request_artifacts.get("pass"),
            "request_status": oauth_request_artifacts.get("request_status"),
            "request_receipt_path": oauth_request_artifacts.get("request_receipt_path"),
            "operator_ask_text_path": oauth_request_artifacts.get("operator_ask_text_path"),
            "operator_ask_metadata_path": oauth_request_artifacts.get("operator_ask_metadata_path"),
            "operator_ask_receipt_name": oauth_request_artifacts.get("operator_ask_receipt_name"),
            "operator_ask_send_command": oauth_request_artifacts.get("operator_ask_send_command"),
            "operator_ask_resend_command": oauth_request_artifacts.get("operator_ask_resend_command"),
            "operator_ask_delivery_status": oauth_request_artifacts.get("operator_ask_delivery_status"),
            "operator_ask_delivery_generated_at_utc": oauth_request_artifacts.get("operator_ask_delivery_generated_at_utc"),
            "operator_ask_delivery_receipt_path": oauth_request_artifacts.get("operator_ask_delivery_receipt_path"),
            "operator_ask_delivery_matches_current_text": oauth_request_artifacts.get("operator_ask_delivery_matches_current_text"),
            "operator_ask_delivery_needs_resend": oauth_request_artifacts.get("operator_ask_delivery_needs_resend"),
            "preferred_drop_path": oauth_request_artifacts.get("preferred_drop_path"),
            "import_command": oauth_request_artifacts.get("import_command"),
            "auto_import_watch_command": oauth_request_artifacts.get("auto_import_watch_command"),
            "post_import_verify_command": oauth_request_artifacts.get("post_import_verify_command"),
            "operator_evidence_template_path": oauth_request_artifacts.get("operator_evidence_template_path"),
        },
        "windows_installer_visual_audit": {
            "status": windows_visual_audit.get("status"),
            "failures": windows_visual_audit.get("failures") if isinstance(windows_visual_audit.get("failures"), list) else [],
            "artifact_file_name": visual_artifact.get("fileName"),
            "artifact_sha256": visual_artifact.get("sha256") or visual_artifact.get("actualSha256"),
            "visual_source_status": visual_source.get("status"),
            "visual_source_artifact_sha256": visual_source.get("artifactSha256"),
            "visual_source_matches_promoted": (visual_source.get("artifactSha256") == (visual_artifact.get("sha256") or visual_artifact.get("actualSha256"))),
            "intake_status": windows_visual_intake.get("status"),
            "intake_promoted_sha256": intake_promoted.get("sha256") or intake_promoted.get("actual_sha256"),
            "matching_promoted_visual_source_count": intake_visual_sources.get("matching_promoted_count"),
            "gold_proof_zip_status": intake_gold_zip.get("status"),
            "operator_request_summary": intake_operator_request.get("summary"),
            "import_command": windows_visual_intake.get("import_command"),
            "post_import_gates": windows_visual_intake.get("post_import_gates") if isinstance(windows_visual_intake.get("post_import_gates"), list) else [],
        },
        "account_handoffs": {
            "billing_mode": ((account_handoff_runtime_config.get("billing") or {}) if isinstance(account_handoff_runtime_config.get("billing"), dict) else {}).get("mode"),
            "release_upload_mode": ((account_handoff_runtime_config.get("release_upload") or {}) if isinstance(account_handoff_runtime_config.get("release_upload"), dict) else {}).get("mode"),
        },
        "checks": checks,
        "failures": failures,
    }


def build_markdown(payload: dict[str, Any]) -> str:
    release = payload.get("release") if isinstance(payload.get("release"), dict) else {}
    mirrors = payload.get("mirrors") if isinstance(payload.get("mirrors"), dict) else {}
    rulesets = payload.get("rulesets") if isinstance(payload.get("rulesets"), dict) else {}
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    public_edge = payload.get("public_edge") if isinstance(payload.get("public_edge"), dict) else {}
    account_handoffs = payload.get("account_handoffs") if isinstance(payload.get("account_handoffs"), dict) else {}
    google_oauth = payload.get("google_oauth_linking") if isinstance(payload.get("google_oauth_linking"), dict) else {}
    windows_visual = payload.get("windows_installer_visual_audit") if isinstance(payload.get("windows_installer_visual_audit"), dict) else {}
    release_readiness = payload.get("release_readiness") if isinstance(payload.get("release_readiness"), dict) else {}
    lines = [
        f"# {payload.get('verdict')}",
        "",
        f"- Generated: {payload.get('generated_at_utc')}",
        f"- Version: `{release.get('version')}`",
        f"- Channel: `{release.get('channel')}`",
        f"- Published: `{release.get('published_at')}`",
        f"- Supportability: `{release.get('supportability_state')}`",
        f"- Full release ready: `{release_readiness.get('full_release_ready')}`",
        f"- Nightly handoff ready: `{release_readiness.get('nightly_handoff_ready')}`",
        f"- Public edge: `{public_edge.get('status')}` / `{public_edge.get('visible_version')}`",
        f"- Mobile PWA: `{public_edge.get('pwa_static_status')}`, ledger `{public_edge.get('mobile_ledger_payload_status')}`",
        f"- Mirrors: {', '.join(f'{name}={status}' for name, status in sorted((mirrors.get('providers') or {}).items()))}",
        f"- Billing mode: `{account_handoffs.get('billing_mode')}`",
        f"- Release-upload mode: `{account_handoffs.get('release_upload_mode')}`",
        f"- Google OAuth linking: `{google_oauth.get('status')}`; request `{google_oauth.get('request_status')}`; resend `{google_oauth.get('operator_ask_delivery_needs_resend')}`",
        f"- Windows visual audit: `{windows_visual.get('status')}`; intake `{windows_visual.get('intake_status')}`; matching promoted sources `{windows_visual.get('matching_promoted_visual_source_count')}`",
        "",
        "## Rulesets",
    ]
    for name, data in sorted(rulesets.items()):
        if isinstance(data, dict):
            lines.append(f"- `{name}`: status `{data.get('status')}`, workflow parity `{data.get('workflow_parity_status')}`, assumption `{data.get('human_side_gold_assumption')}`")
    lines.extend(["", "## Checks"])
    for name, data in sorted(checks.items()):
        if isinstance(data, dict):
            release_blocking = bool(data.get("release_blocking", True))
            if data.get("pass"):
                mark = "PASS"
            elif release_blocking:
                mark = "FAIL"
            else:
                mark = "INFO"
            suffix = "" if release_blocking else " (operator context, not release-blocking)"
            lines.append(f"- {mark} `{name}`: `{data.get('status')}`{suffix}")
    if google_oauth:
        lines.extend(["", "## Google OAuth Handoff"])
        lines.append(f"- Operator evidence pass: `{google_oauth.get('operator_evidence_pass')}`")
        lines.append(f"- Request artifacts pass: `{google_oauth.get('request_artifacts_pass')}`")
        lines.append(f"- Request receipt: `{google_oauth.get('request_receipt_path')}`")
        lines.append(f"- Operator evidence path: `{google_oauth.get('operator_evidence_path')}`")
        lines.append(f"- Current ask delivery: `{google_oauth.get('operator_ask_delivery_status')}` at `{google_oauth.get('operator_ask_delivery_generated_at_utc')}`")
        lines.append(f"- Current ask text matches delivered text: `{google_oauth.get('operator_ask_delivery_matches_current_text')}`")
        lines.append(f"- Ask resend required: `{google_oauth.get('operator_ask_delivery_needs_resend')}`")
        if google_oauth.get("preferred_drop_path"):
            lines.append(f"- Preferred bundle drop: `{google_oauth.get('preferred_drop_path')}`")
        if google_oauth.get("import_command"):
            lines.append(f"- Import command: `{google_oauth.get('import_command')}`")
        if google_oauth.get("auto_import_watch_command"):
            lines.append(f"- Auto-import watch: `{google_oauth.get('auto_import_watch_command')}`")
        if google_oauth.get("operator_ask_send_command"):
            lines.append(f"- Current ask send command: `{google_oauth.get('operator_ask_send_command')}`")
        if google_oauth.get("operator_ask_resend_command"):
            lines.append(f"- Current ask resend command: `{google_oauth.get('operator_ask_resend_command')}`")
        for failure in google_oauth.get("failures") or []:
            lines.append(f"- Current blocker: {failure}")
    if windows_visual:
        lines.extend(["", "## Windows Visual Audit Handoff"])
        lines.append(f"- Promoted installer: `{windows_visual.get('artifact_file_name')}` / `{windows_visual.get('artifact_sha256')}`")
        lines.append(f"- Current visual source artifact: `{windows_visual.get('visual_source_artifact_sha256')}`")
        lines.append(f"- Matching promoted visual sources discovered: `{windows_visual.get('matching_promoted_visual_source_count')}`")
        lines.append(f"- Gold proof bundle discovery: `{windows_visual.get('gold_proof_zip_status')}`")
        if windows_visual.get("operator_request_summary"):
            lines.append(f"- Operator request: {windows_visual.get('operator_request_summary')}")
        if windows_visual.get("import_command"):
            lines.append(f"- Import command: `{windows_visual.get('import_command')}`")
        for failure in windows_visual.get("failures") or []:
            lines.append(f"- Current blocker: {failure}")
    full_release_blockers = release_readiness.get("full_release_blockers") if isinstance(release_readiness.get("full_release_blockers"), list) else []
    if full_release_blockers:
        lines.extend(["", "## Full Release Blockers"])
        lines.extend(f"- `{blocker}`" for blocker in full_release_blockers)
    full_release_blocker_details = release_readiness.get("full_release_blocker_details") if isinstance(release_readiness.get("full_release_blocker_details"), list) else []
    if full_release_blocker_details:
        lines.extend(["", "## Full Release Blocker Details"])
        lines.extend(f"- {blocker}" for blocker in full_release_blocker_details)
    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    if failures:
        lines.extend(["", "## Failures"])
        lines.extend(f"- `{failure}`" for failure in failures)
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize the operator release dashboard.")
    parser.add_argument(
        "--release-ready-self-check",
        action="store_true",
        help="Refresh release-ready blocker detail from current flagship gate truth when the receipt is stale or incomplete.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_payload(release_ready_self_check=args.release_ready_self_check)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(build_markdown(payload), encoding="utf-8")
    print(f"operator_release_dashboard:{payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
