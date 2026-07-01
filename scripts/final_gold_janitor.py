#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
COMPLETION_ROOT = Path("/docker/chummercomplete/_completion")
ARTIFACT_ROOT_NAME = os.environ.get("CHUMMER_FINAL_GOLD_ARTIFACT_ROOT", "full_product_reaudit_v20")
ARTIFACT_ROOT = COMPLETION_ROOT / ARTIFACT_ROOT_NAME
UI_LAYOUT_COMPLETION_ROOT = COMPLETION_ROOT / "chummer_run_redesign_closure"
LEGACY_GOLD_CLOSURE_ROOT = COMPLETION_ROOT / "gold_readiness_closure"
DEFAULT_BASE_URL = os.environ.get("CHUMMER_FINAL_GOLD_BASE_URL", "https://chummer.run")
RECRAWL_MAX_AGE_HOURS = 24
MATERIALIZER_TIMEOUT_SECONDS = int(os.environ.get("CHUMMER_FINAL_GOLD_MATERIALIZER_TIMEOUT_SECONDS", "600"))
FRESHNESS_REQUIRED_GATES = {
    "live_public_web_recrawl",
    "rule_authority_minimum_coverage",
    "ruleset_readiness",
    "public_route_proof",
    "icanpreneur_discovery_lane",
    "provider_proof_discoverability",
    "desktop_native_model_depth",
    "black_ledger_live_media_proof",
    "table_pulse_scenario_replay",
    "live_surface_parity",
    "live_public_windows_installer",
    "blazor_execution_horizon_bridge",
    "ltd_optimization_stack",
    "external_distribution_mirror_proof",
    "public_copy_leak_gate",
    "participate_billing_honesty",
    "account_handoff_runtime_config",
    "premium_ui_design_exit_gate",
    "design_quality_gate",
    "windows_installer_visual_audit",
    "ui_layout_exit_gate",
    "operator_release_dashboard",
    "release_ready",
}
# Accepted boundaries and operator advisories should be surfaced, but they should not
# override passing required gates into a false NOT_GOLD verdict.
FAIL_CLOSED_CAVEAT_IDS: set[str] = set()

REQUIRED_RECEIPTS = {
    "live_public_web_recrawl": PUBLISHED_ROOT / "LIVE_PUBLIC_WEB_RECRAWL.generated.json",
    "rule_authority_minimum_coverage": PUBLISHED_ROOT / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json",
    "ruleset_readiness": PUBLISHED_ROOT / "RULESET_READINESS.generated.json",
    "provider_proof_discoverability": PUBLISHED_ROOT / "PROVIDER_PROOF_DISCOVERABILITY.generated.json",
    "desktop_native_model_depth": PUBLISHED_ROOT / "DESKTOP_NATIVE_MODEL_DEPTH.generated.json",
    "black_ledger_live_media_proof": PUBLISHED_ROOT / "BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json",
    "table_pulse_scenario_replay": PUBLISHED_ROOT / "TABLE_PULSE_SCENARIO_REPLAY.generated.json",
    "public_route_proof": PUBLISHED_ROOT / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json",
    "live_surface_parity": PUBLISHED_ROOT / "LIVE_SURFACE_PARITY.generated.json",
    "live_public_windows_installer": PUBLISHED_ROOT / "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json",
    "blazor_execution_horizon_bridge": PUBLISHED_ROOT / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json",
    "icanpreneur_discovery_lane": PUBLISHED_ROOT / "ICANPRENEUR_DISCOVERY_LANE.generated.json",
    "ltd_optimization_stack": PUBLISHED_ROOT / "LTD_OPTIMIZATION_STACK.generated.json",
    "external_distribution_mirror_proof": PUBLISHED_ROOT / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json",
    "public_copy_leak_gate": PUBLISHED_ROOT / "PUBLIC_COPY_LEAK_GATE.generated.json",
    "participate_billing_honesty": PUBLISHED_ROOT / "PARTICIPATE_BILLING_HONESTY.generated.json",
    "account_handoff_runtime_config": PUBLISHED_ROOT / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json",
    "premium_ui_design_exit_gate": PUBLISHED_ROOT / "PREMIUM_UI_DESIGN_EXIT_GATE.generated.json",
    "design_quality_gate": PUBLISHED_ROOT / "DESIGN_QUALITY_GATE.generated.json",
    "windows_installer_visual_audit": PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
    "ui_layout_exit_gate": UI_LAYOUT_COMPLETION_ROOT / "UI_LAYOUT_EXIT_GATE.generated.json",
    "operator_release_dashboard": PUBLISHED_ROOT / "OPERATOR_RELEASE_DASHBOARD.generated.json",
    "release_ready": PUBLISHED_ROOT / "RELEASE_READY.generated.json",
}
BLAZOR_PUBLIC_ENTRY_CHECK_IDS = (
    "home_open_chummer_dropdown_routes_build_and_play",
    "build_route_opens_character_roster",
    "play_route_opens_pwa_play_shell",
)

MATERIALIZERS = [
    ["python3", "scripts/verify_live_public_web_recrawl.py", "--base-url", DEFAULT_BASE_URL],
    [
        "python3",
        "scripts/verify_public_routes_from_manifest.py",
        "--strict-positive",
        "--seed-receipts",
        "--base-url",
        DEFAULT_BASE_URL,
        "--request-timeout-seconds",
        "2",
        "--max-retries",
        "0",
        "--retry-delay-seconds",
        "0.1",
        "--manifest",
        ".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml",
        "--output",
        str(PUBLISHED_ROOT / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"),
    ],
    ["python3", "scripts/verify_live_surface_parity.py", "--base-url", DEFAULT_BASE_URL],
    ["python3", "scripts/verify_live_public_windows_installer.py", "--base-url", DEFAULT_BASE_URL],
    ["python3", "scripts/verify_blazor_execution_horizon_bridge.py"],
    ["python3", "scripts/verify_icanpreneur_discovery_lane.py"],
    ["python3", "scripts/verify_provider_proof_discoverability.py"],
    ["python3", "scripts/materialize_ltd_optimization_stack.py"],
    ["python3", "scripts/verify_rules_authority_minimum_coverage.py"],
    ["python3", "scripts/classify_ruleset_readiness.py", "--output", str(PUBLISHED_ROOT / "RULESET_READINESS.generated.json")],
    ["python3", "scripts/verify_desktop_native_model_depth.py"],
    ["python3", "scripts/verify_black_ledger_live_media_proof.py", "--base-url", DEFAULT_BASE_URL],
    ["python3", "scripts/verify_table_pulse_scenario_replay.py", "--base-url", DEFAULT_BASE_URL],
    ["python3", "scripts/materialize_external_distribution_mirror_proof.py", "--base-url", os.environ.get("CHUMMER_PUBLIC_BASE_URL", "http://127.0.0.1:8091")],
    ["python3", "scripts/verify_public_copy_leak_gate.py", "--base-url", DEFAULT_BASE_URL],
    ["python3", "scripts/materialize_participate_billing_honesty.py", "--completion-dir", str(PUBLISHED_ROOT)],
    ["python3", "scripts/verify_account_handoff_runtime_config.py"],
    ["python3", "scripts/ui_layout_exit_gate.py", "--completion-dir", str(UI_LAYOUT_COMPLETION_ROOT)],
    ["python3", "scripts/verify_minimal_experience_gate.py", "--base-url", DEFAULT_BASE_URL, "--completion-dir", str(UI_LAYOUT_COMPLETION_ROOT)],
    ["python3", "scripts/verify_premium_ui_design_exit_gate.py", "--completion-dir", str(UI_LAYOUT_COMPLETION_ROOT)],
    ["python3", "scripts/materialize_design_quality_gate.py"],
    ["python3", "scripts/verify_windows_installer_visual_audit.py"],
    ["python3", "scripts/materialize_operator_release_dashboard.py"],
    ["python3", "scripts/materialize_release_ready_receipt.py"],
]


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def generated_at_is_fresh(value: str, max_age_hours: int) -> bool:
    if not value:
        return False
    try:
        generated_at = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return False
    return generated_at >= datetime.now(UTC) - timedelta(hours=max_age_hours)


def blazor_bridge_public_entry_summary(payload: dict[str, Any]) -> dict[str, Any]:
    proof = (payload.get("proofs") or {}).get("hub_mobile_pwa_public_projection") or {}
    public_entry = proof.get("public_entry") if isinstance(proof.get("public_entry"), dict) else {}
    checks = public_entry.get("checks") if isinstance(public_entry.get("checks"), dict) else {}
    check_summary = {
        check_id: {
            "present": isinstance(checks.get(check_id), dict),
            "pass": (checks.get(check_id) or {}).get("pass") is True,
        }
        for check_id in BLAZOR_PUBLIC_ENTRY_CHECK_IDS
    }
    holds = (
        proof.get("pass") is True
        and proof.get("base_url") == DEFAULT_BASE_URL
        and public_entry.get("home_open_chummer_dropdown_holds") is True
        and public_entry.get("build_route_holds") is True
        and public_entry.get("play_shell_holds") is True
        and public_entry.get("build_final_route") == "/app?command=character_roster"
        and public_entry.get("play_final_route") == "/play"
        and public_entry.get("checks_pass") is True
        and all(item["pass"] for item in check_summary.values())
    )
    return {
        "pass": holds,
        "base_url": proof.get("base_url"),
        "home_open_chummer_dropdown_holds": public_entry.get("home_open_chummer_dropdown_holds") is True,
        "build_route_holds": public_entry.get("build_route_holds") is True,
        "build_final_route": public_entry.get("build_final_route"),
        "play_shell_holds": public_entry.get("play_shell_holds") is True,
        "play_final_route": public_entry.get("play_final_route"),
        "checks_pass": public_entry.get("checks_pass") is True,
        "checks": check_summary,
    }


def run_materializers() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for command in MATERIALIZERS:
        try:
            completed = subprocess.run(
                command,
                cwd=RUN_SERVICES_ROOT,
                capture_output=True,
                text=True,
                timeout=MATERIALIZER_TIMEOUT_SECONDS,
            )
            results.append(
                {
                    "command": " ".join(command),
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                    "timed_out": False,
                    "timeout_seconds": MATERIALIZER_TIMEOUT_SECONDS,
                }
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            results.append(
                {
                    "command": " ".join(command),
                    "returncode": 124,
                    "stdout": stdout.strip(),
                    "stderr": stderr.strip(),
                    "timed_out": True,
                    "timeout_seconds": MATERIALIZER_TIMEOUT_SECONDS,
                }
            )
    return results


def build_payload(command_results: list[dict[str, Any]]) -> dict[str, Any]:
    required_gates: dict[str, Any] = {}
    failures: list[str] = []
    caveats: list[dict[str, Any]] = []
    for name, path in REQUIRED_RECEIPTS.items():
        payload = load_json(path)
        generated_at = str(payload.get("generated_at_utc") or payload.get("generatedAt") or "")
        is_fresh = generated_at_is_fresh(generated_at, RECRAWL_MAX_AGE_HOURS) if name in FRESHNESS_REQUIRED_GATES else True
        status_value = str(payload.get("status") or "").strip().lower()
        structured_failures = payload.get("failures")
        has_structured_failures = isinstance(structured_failures, list) and len(structured_failures) > 0
        passed = path.is_file() and status_value in {"pass", "passed", "ready"} and is_fresh
        gate_failure_reason: str | None = None
        if name == "public_route_proof" and path.is_file():
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            passed = (
                status_value in {"pass", "passed", "ready"}
                and int(summary.get("route_count") or 0) > 0
                and int(summary.get("failed_count") or 0) == 0
                and int(summary.get("negative_path_failed_count") or 0) == 0
                and is_fresh
            )
            status_value = "pass" if passed else "fail"
        if name == "blazor_execution_horizon_bridge" and path.is_file():
            blazor_public_entry = blazor_bridge_public_entry_summary(payload)
            if not blazor_public_entry["pass"]:
                passed = False
                status_value = "fail"
                gate_failure_reason = "blazor_execution_horizon_bridge missing live Build/Play public-entry proof"
        if passed and has_structured_failures:
            passed = False
        if not passed:
            reason = gate_failure_reason or (f"{name} missing" if not path.is_file() else f"{name} failed")
            if path.is_file() and name in FRESHNESS_REQUIRED_GATES and not is_fresh:
                reason = f"{name} stale"
            elif path.is_file() and status_value in {"pass", "passed", "ready"} and has_structured_failures:
                reason = f"{name} has structured failures"
            failures.append(reason)
        required_gates[name] = {
            "path": str(path),
            "exists": path.is_file(),
            "status": status_value or payload.get("status", "missing"),
            "generated_at_utc": generated_at,
            "fresh_within_hours": RECRAWL_MAX_AGE_HOURS if name in FRESHNESS_REQUIRED_GATES else None,
            "structured_failures_count": len(structured_failures) if isinstance(structured_failures, list) else 0,
            "pass": passed,
        }
        if name == "rule_authority_minimum_coverage" and path.is_file():
            required_gates[name]["rulesets"] = payload.get("rulesets", {})
            required_gates[name]["failures"] = payload.get("failures", [])
        if name == "ruleset_readiness" and path.is_file():
            workflow_assumed_rulesets = [
                ruleset
                for ruleset, ruleset_payload in (payload.get("rulesets") or {}).items()
                if isinstance(ruleset_payload, dict) and ruleset_payload.get("human_side_gold_assumption")
            ]
            authority_approved_rulesets = sorted(
                str(item)
                for item in (
                    ((payload.get("rule_authority_human_approval") or {}).get("rulesets") or [])
                    if isinstance(payload.get("rule_authority_human_approval"), dict)
                    else []
                )
                if str(item).strip()
            )
            if workflow_assumed_rulesets:
                caveats.append(
                    {
                        "id": "ruleset_human_side_gold_assumption",
                        "severity": "accepted_boundary",
                        "summary": "Ruleset readiness still includes an explicitly accepted human-side boundary; authority coverage is approved separately from any workflow-parity assumptions.",
                        "workflow_assumed_rulesets": sorted(workflow_assumed_rulesets),
                        "authority_approved_rulesets": authority_approved_rulesets,
                    }
                )
            required_gates[name]["workflow_assumed_rulesets"] = sorted(workflow_assumed_rulesets)
            required_gates[name]["authority_approved_rulesets"] = authority_approved_rulesets
            required_gates[name]["rulesets"] = payload.get("rulesets", {})
        if name == "public_route_proof" and path.is_file():
            required_gates[name]["summary"] = payload.get("summary", {})
        if name == "blazor_execution_horizon_bridge" and path.is_file():
            required_gates[name]["public_entry"] = blazor_bridge_public_entry_summary(payload)
        if name == "external_distribution_mirror_proof" and path.is_file():
            required_gates[name]["external_required"] = payload.get("external_required")
            required_gates[name]["distribution_resilience_status"] = payload.get("distribution_resilience_status")
            required_gates[name]["advisory_external_failures"] = payload.get("advisory_external_failures", [])
            required_gates[name]["providers"] = {
                provider: data.get("status")
                for provider, data in (payload.get("providers") or {}).items()
                if isinstance(data, dict)
            }
            advisory_failures = payload.get("advisory_external_failures")
            if (
                isinstance(advisory_failures, list)
                and advisory_failures
                and not payload.get("external_required")
            ):
                caveats.append(
                    {
                        "id": "optional_external_mirrors_degraded",
                        "severity": "operational_advisory",
                        "summary": "Local registry and public edge are release-blocking and passing, but optional external mirrors are degraded.",
                        "providers": sorted(str(item) for item in advisory_failures),
                    }
                )
        if name == "release_ready" and path.is_file():
            required_gates[name]["verdict"] = payload.get("verdict")
            required_gates[name]["failures"] = payload.get("failures", [])
        if name == "operator_release_dashboard" and path.is_file():
            required_gates[name]["verdict"] = payload.get("verdict")
            required_gates[name]["failures"] = payload.get("failures", [])
            required_gates[name]["release"] = payload.get("release", {})
        if name == "windows_installer_visual_audit" and path.is_file():
            required_gates[name]["failures"] = payload.get("failures", [])
            required_gates[name]["nextActions"] = payload.get("nextActions", [])
            required_gates[name]["startupReceipt"] = payload.get("startupReceipt", {})
            required_gates[name]["visualAuditSource"] = payload.get("visualAuditSource", {})

    for caveat in caveats:
        if not isinstance(caveat, dict):
            continue
        caveat_id = str(caveat.get("id") or "").strip()
        if caveat_id in FAIL_CLOSED_CAVEAT_IDS:
            failures.append(f"{caveat_id} unresolved")

    for result in command_results:
        if result["returncode"] != 0:
            failures.append(f"materializer failed: {result['command']}")

    return {
        "contract_name": "chummer.final_gold_janitor",
        "generated_at_utc": now_iso(),
        "scope": "full_estate_v20",
        "artifact_root": f"_completion/{ARTIFACT_ROOT_NAME}",
        "durable_artifacts_required": True,
        "live_backed_required": True,
        "live_recrawl_required": True,
        "recrawl_max_age_hours": RECRAWL_MAX_AGE_HOURS,
        "status": "pass" if not failures else "fail",
        "verdict": "GOLD_READY" if not failures else "NOT_GOLD",
        "required_gates": required_gates,
        "materializers": command_results,
        "caveats": caveats,
        "failures": failures,
    }


def build_verdict_markdown(payload: dict[str, Any]) -> str:
    verdict = str(payload.get("verdict") or "NOT_GOLD")
    caveats = payload.get("caveats") if isinstance(payload.get("caveats"), list) else []
    lines = [
        f"# {verdict}",
        "",
        f"Generated: {payload.get('generated_at_utc')}",
        f"Scope: {payload.get('scope')}",
    ]
    if caveats:
        lines.append("Accepted boundaries: yes")
    lines.extend([
        "",
        "## Gate Summary",
    ])
    for name, gate in sorted((payload.get("required_gates") or {}).items()):
        if not isinstance(gate, dict):
            continue
        mark = "PASS" if gate.get("pass") else "FAIL"
        lines.append(f"- {mark} `{name}`: `{gate.get('status')}` at `{gate.get('path')}`")
        if name == "public_route_proof" and isinstance(gate.get("summary"), dict):
            summary = gate["summary"]
            lines.append(
                f"  - routes {summary.get('passed_count')}/{summary.get('route_count')}, failed {summary.get('failed_count')}, negative-path failures {summary.get('negative_path_failed_count')}"
            )
        if name == "external_distribution_mirror_proof" and isinstance(gate.get("providers"), dict):
            provider_summary = ", ".join(f"{provider}={status}" for provider, status in sorted(gate["providers"].items()))
            lines.append(f"  - mirrors: {provider_summary}; external_required={gate.get('external_required')}")
        if name == "ruleset_readiness":
            workflow_assumed = gate.get("workflow_assumed_rulesets") or []
            authority_approved = gate.get("authority_approved_rulesets") or []
            if workflow_assumed:
                lines.append(f"  - workflow assumption: {', '.join(workflow_assumed)}")
            if authority_approved:
                lines.append(f"  - authority approved: {', '.join(authority_approved)}")
        if name == "release_ready" and gate.get("failures"):
            lines.append(f"  - release failures: {', '.join(str(item) for item in gate['failures'])}")
        if name == "operator_release_dashboard" and isinstance(gate.get("release"), dict):
            release = gate["release"]
            lines.append(f"  - release: {release.get('version')} on {release.get('channel')}")
        if name == "operator_release_dashboard" and gate.get("failures"):
            lines.append(f"  - dashboard failures: {', '.join(str(item) for item in gate['failures'])}")
        if name == "windows_installer_visual_audit" and gate.get("failures"):
            lines.append(f"  - visual audit failures: {', '.join(str(item) for item in gate['failures'])}")
            if gate.get("nextActions"):
                lines.append("  - next actions:")
                lines.extend(f"    - {item}" for item in gate["nextActions"])

    if caveats:
        lines.extend(["", "## Accepted Boundaries"])
        for item in caveats:
            if not isinstance(item, dict):
                continue
            lines.append(f"- `{item.get('id')}`: {item.get('summary')}")

    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    if failures:
        lines.extend(["", "## Failures"])
        lines.extend(f"- {failure}" for failure in failures)

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the final gold verdict from committed, fresh, fail-closed receipts.")
    parser.add_argument("--skip-materializers", action="store_true", help="Read receipts without regenerating them.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prior_payload = load_json(PUBLISHED_ROOT / "FINAL_GOLD_JANITOR.generated.json")
    command_results = [] if args.skip_materializers else run_materializers()
    payload = build_payload(command_results)
    if args.skip_materializers and not payload.get("materializers"):
        prior_materializers = prior_payload.get("materializers")
        if isinstance(prior_materializers, list):
            payload["materializers"] = prior_materializers
    legacy_payload = dict(payload)
    legacy_payload["mirrors"] = {
        "authoritative_artifact_root": payload["artifact_root"],
        "legacy_closure_root": str(LEGACY_GOLD_CLOSURE_ROOT),
    }
    write_json(PUBLISHED_ROOT / "FINAL_GOLD_JANITOR.generated.json", payload)
    write_json(ARTIFACT_ROOT / "FINAL_GOLD_JANITOR.generated.json", payload)
    write_json(LEGACY_GOLD_CLOSURE_ROOT / "FINAL_GOLD_JANITOR.generated.json", legacy_payload)
    verdict_markdown = build_verdict_markdown(payload)
    write_text(PUBLISHED_ROOT / "FINAL_GOLD_VERDICT.md", verdict_markdown)
    write_text(ARTIFACT_ROOT / "FINAL_GOLD_VERDICT.md", verdict_markdown)
    write_text(LEGACY_GOLD_CLOSURE_ROOT / "FINAL_GOLD_VERDICT.md", verdict_markdown)
    if payload["status"] != "pass":
        print(json.dumps({
            "status": payload["status"],
            "verdict": payload["verdict"],
            "failures": payload["failures"],
            "required_gates": {
                name: gate
                for name, gate in payload["required_gates"].items()
                if not gate.get("pass")
            },
            "failed_materializers": [
                result for result in payload["materializers"]
                if result.get("returncode") != 0
            ],
        }, indent=2), file=sys.stderr)
        raise SystemExit("final gold janitor failed")
    print("final_gold_janitor:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
