#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path("/docker/chummercomplete")
RUN_SERVICES_ROOT = ROOT / "chummer.run-services"
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
COMPLETION_ROOT = ROOT / "_completion" / "chummer_run_redesign_closure"
REGISTRY_ROOT = ROOT / "chummer-hub-registry" / ".codex-studio" / "published"
OUTPUT_JSON = PUBLISHED_ROOT / "OPERATOR_RELEASE_DASHBOARD.generated.json"
OUTPUT_MD = PUBLISHED_ROOT / "OPERATOR_RELEASE_DASHBOARD.md"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


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
        "generated_at_utc": loaded.get("generated_at_utc") or loaded.get("generatedAt") or loaded.get("generated_at"),
        "pass": path.is_file() and status in accepted,
    }


def build_payload() -> dict[str, Any]:
    release_channel_path = REGISTRY_ROOT / "RELEASE_CHANNEL.generated.json"
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
    release_ready_path = PUBLISHED_ROOT / "RELEASE_READY.generated.json"
    release_ready = load_json(release_ready_path)
    final_gold_path = PUBLISHED_ROOT / "FINAL_GOLD_JANITOR.generated.json"
    final_gold = load_json(final_gold_path)
    oauth_path = PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
    oauth = load_json(oauth_path)

    checks = {
        "release_channel": gate("release_channel", release_channel_path, release_channel, accepted_statuses={"published", "pass", "passed", "ready"}),
        "external_distribution_mirror_proof": gate("external_distribution_mirror_proof", mirror_path, mirror),
        "ruleset_readiness": gate("ruleset_readiness", ruleset_path, ruleset),
        "ui_frame_integrity": gate("ui_frame_integrity", ui_frame_path, ui_frame),
        "design_quality_gate": gate("design_quality_gate", design_path, design),
        "public_copy_leak_gate": gate("public_copy_leak_gate", copy_path, copy_gate),
        "release_ready": gate("release_ready", release_ready_path, release_ready),
        "final_gold_janitor": gate("final_gold_janitor", final_gold_path, final_gold),
        "google_oauth_linking_proof": gate("google_oauth_linking_proof", oauth_path, oauth),
    }

    # OAuth is a durable account-linking proof; it is surfaced as operator context but not required
    # to be fresh for every artifact publish because it exercises a third-party browser handoff.
    checks["google_oauth_linking_proof"]["release_blocking"] = False
    checks["release_ready"]["release_blocking"] = False
    checks["final_gold_janitor"]["release_blocking"] = False
    required_names = [
        name
        for name, data in checks.items()
        if isinstance(data, dict) and data.get("release_blocking", True)
    ]
    failures = [name for name in required_names if not checks[name]["pass"]]

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

    return {
        "contract_name": "chummer.operator_release_dashboard",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "verdict": "OPERABLE_RELEASE_READY" if not failures else "OPERABLE_RELEASE_BLOCKED",
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
        "checks": checks,
        "failures": failures,
    }


def build_markdown(payload: dict[str, Any]) -> str:
    release = payload.get("release") if isinstance(payload.get("release"), dict) else {}
    mirrors = payload.get("mirrors") if isinstance(payload.get("mirrors"), dict) else {}
    rulesets = payload.get("rulesets") if isinstance(payload.get("rulesets"), dict) else {}
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    lines = [
        f"# {payload.get('verdict')}",
        "",
        f"- Generated: {payload.get('generated_at_utc')}",
        f"- Version: `{release.get('version')}`",
        f"- Channel: `{release.get('channel')}`",
        f"- Published: `{release.get('published_at')}`",
        f"- Supportability: `{release.get('supportability_state')}`",
        f"- Mirrors: {', '.join(f'{name}={status}' for name, status in sorted((mirrors.get('providers') or {}).items()))}",
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
    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    if failures:
        lines.extend(["", "## Failures"])
        lines.extend(f"- `{failure}`" for failure in failures)
    return "\n".join(lines) + "\n"


def main() -> int:
    payload = build_payload()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(build_markdown(payload), encoding="utf-8")
    print(f"operator_release_dashboard:{payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
