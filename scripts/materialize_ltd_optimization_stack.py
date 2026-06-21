#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
DESIGN_ROOT = Path("/docker/chummercomplete/chummer-design/products/chummer")
COMPLETION_ROOT = Path("/docker/chummercomplete/_completion")
OUTPUT_PATH = PUBLISHED_ROOT / "LTD_OPTIMIZATION_STACK.generated.json"
LAYOUT_PATH = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "Shared" / "_Layout.cshtml"
SITE_JS_PATH = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "wwwroot" / "js" / "site.js"
LANDING_PATH = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Landing.cshtml"
DOWNLOADS_PATH = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Downloads.cshtml"
STATUS_PATH = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Status.cshtml"
LEDGER_PATH = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Ledger.cshtml"
PROGRAM_PATH = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Program.cs"
ENV_EXAMPLE_PATH = RUN_SERVICES_ROOT / ".env.example"
COMPOSE_PATH = RUN_SERVICES_ROOT / "docker-compose.public-edge.yml"
DESKTOP_APP_PATH = Path("/docker/chummercomplete/chummer-presentation/Chummer.Avalonia/App.axaml.cs")
DESKTOP_MAIN_WINDOW_PATH = Path("/docker/chummercomplete/chummer-presentation/Chummer.Avalonia/MainWindow.EventHandlers.cs")
DESKTOP_ANALYTICS_CLIENT_PATH = Path("/docker/chummercomplete/chummer-presentation/Chummer.Avalonia/DesktopAnalyticsClient.cs")
DESKTOP_PREFERENCE_PATH = Path("/docker/chummercomplete/chummer-presentation/Chummer.Presentation/Overview/DesktopPreferenceState.cs")
PROVIDER_DISCOVERABILITY_PATH = PUBLISHED_ROOT / "PROVIDER_PROOF_DISCOVERABILITY.generated.json"
ICANPRENEUR_RECEIPT_PATH = PUBLISHED_ROOT / "provider-proof-discoverability" / "icanpreneur" / "ICANPRENEUR_TRACKED_PROVIDER_RECEIPT.generated.json"
ICANPRENEUR_LANE_PATH = PUBLISHED_ROOT / "ICANPRENEUR_DISCOVERY_LANE.generated.json"
RYBBIT_RECEIPT_PATH = PUBLISHED_ROOT / "provider-proof-discoverability" / "rybbit" / "RYBBIT_TRACKED_PROVIDER_RECEIPT.generated.json"
NEURONWRITER_RECEIPT_PATH = PUBLISHED_ROOT / "provider-proof-discoverability" / "neuronwriter" / "NEURONWRITER_TRACKED_PROVIDER_RECEIPT.generated.json"
SUBSCRIBR_RECEIPT_PATH = PUBLISHED_ROOT / "provider-proof-discoverability" / "subscribr" / "SUBSCRIBR_TRACKED_PROVIDER_RECEIPT.generated.json"
PUBLIC_GROWTH_DOC_PATH = DESIGN_ROOT / "PUBLIC_GROWTH_AND_VISIBILITY_STACK.md"
LTD_REGISTRY_PATH = DESIGN_ROOT / "LTD_RUNTIME_AND_PROJECTION_REGISTRY.yaml"
LTD_MAP_PATH = DESIGN_ROOT / "LTD_CAPABILITY_MAP.md"
RAFTER_PIXEFY_BOUNDARY_PATH = DESIGN_ROOT / "RAFTER_PIXEFY_RELEASE_QA_BOUNDARY.md"
RAFTER_GATE_PATH = COMPLETION_ROOT / "rafter" / "RAFTER_SECURITY_GOLD_GATE.generated.json"
PIXEFY_GATE_PATH = COMPLETION_ROOT / "pixefy" / "PIXEFY_RESPONSIVE_VISUAL_QA.generated.json"
RAFTER_PIXEFY_VERDICT_MD = COMPLETION_ROOT / "rafter_pixefy" / "FINAL_RAFTER_PIXEFY_QA_STACK_VERDICT.md"
RAFTER_PIXEFY_REASONS_JSON = COMPLETION_ROOT / "rafter_pixefy" / "FINAL_RAFTER_PIXEFY_QA_STACK_REASONS.generated.json"
READY_VERDICT = "RAFTER_PIXEFY_QA_STACK_READY"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def status_pass(payload: dict[str, Any]) -> bool:
    return str(payload.get("status") or "").strip().lower() in {"pass", "passed", "ready", "tracked"}


def build_payload() -> dict[str, Any]:
    failures: list[str] = []
    checks: dict[str, Any] = {}

    layout_source = read_text(LAYOUT_PATH)
    site_js = read_text(SITE_JS_PATH)
    landing = read_text(LANDING_PATH)
    downloads = read_text(DOWNLOADS_PATH)
    status = read_text(STATUS_PATH)
    ledger = read_text(LEDGER_PATH)
    program_source = read_text(PROGRAM_PATH)
    env_example = read_text(ENV_EXAMPLE_PATH)
    compose_source = read_text(COMPOSE_PATH)
    desktop_app_source = read_text(DESKTOP_APP_PATH)
    desktop_main_window_source = read_text(DESKTOP_MAIN_WINDOW_PATH)
    desktop_analytics_source = read_text(DESKTOP_ANALYTICS_CLIENT_PATH)
    desktop_preference_source = read_text(DESKTOP_PREFERENCE_PATH)
    growth_doc = read_text(PUBLIC_GROWTH_DOC_PATH)
    ltd_registry = read_text(LTD_REGISTRY_PATH)
    ltd_map = read_text(LTD_MAP_PATH)

    icanpreneur_receipt = load_json(ICANPRENEUR_RECEIPT_PATH)
    icanpreneur_lane = load_json(ICANPRENEUR_LANE_PATH)
    icanpreneur_design = read_text(DESIGN_ROOT / "ICANPRENEUR_DISCOVERY_AND_VALIDATION_LANE.md")
    karma_forge_source = read_text(RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Services" / "KarmaForge" / "KarmaForgeDiscoveryService.cs")
    icanpreneur_pass = (
        status_pass(icanpreneur_receipt)
        and icanpreneur_receipt.get("license_tier") == "Tier 3"
        and icanpreneur_receipt.get("runtime_ready") is False
        and status_pass(icanpreneur_lane)
        and icanpreneur_lane.get("runtime_ready") is False
        and "rules truth" in str(icanpreneur_lane.get("claim_boundary") or "")
        and "publication approval" in str(icanpreneur_lane.get("claim_boundary") or "")
        and "`Icanpreneur` - bounded discovery interview and validation lane" in ltd_map
        and "Icanpreneur" in ltd_registry
        and "bounded adaptive discovery-interview and validation lane" in icanpreneur_design
        and "direct backlog ownership" in icanpreneur_design
        and "copyrighted-book-text capture" in icanpreneur_design
        and "CHUMMER_KARMA_FORGE_ICANPRENEUR_BASE_URL" in env_example
        and "CHUMMER_KARMA_FORGE_ICANPRENEUR_BASE_URL" in compose_source
        and 'stageKey: "adaptive_interview"' in karma_forge_source
        and 'boundary: "interview_signal_not_product_truth"' in karma_forge_source
    )
    if not icanpreneur_pass:
        failures.append("icanpreneur discovery interview lane is not discoverable and bounded")
    checks["icanpreneur_discovery_interview"] = {
        "path": str(ICANPRENEUR_RECEIPT_PATH),
        "lane_path": str(ICANPRENEUR_LANE_PATH),
        "status": icanpreneur_receipt.get("status", "missing"),
        "lane_status": icanpreneur_lane.get("status", "missing"),
        "license_tier": icanpreneur_receipt.get("license_tier"),
        "runtime_ready": icanpreneur_receipt.get("runtime_ready"),
        "pass": icanpreneur_pass,
    }

    rybbit_receipt = load_json(RYBBIT_RECEIPT_PATH)
    rybbit_pass = (
        status_pass(rybbit_receipt)
        and bool(rybbit_receipt.get("runtime_ready"))
        and "RYBBIT_CHUMMER_RUN_SITE_ID" in layout_source
        and "ChummerUi.trackPublicEvent" in site_js
        and "window.ChummerAnalyticsQueue" in site_js
        and 'data-analytics-event="homepage_open_stable"' in landing
        and 'data-analytics-event="homepage_open_nightly"' in landing
        and 'data-analytics-event="downloads_stable_install"' in downloads
        and 'data-analytics-event="downloads_nightly_install"' in downloads
        and 'data-analytics-event="status_next_action"' in status
        and 'data-analytics-event="ledger_primary_action"' in ledger
        and 'MapPost("/api/desktop-analytics/track"' in program_source
        and "DesktopAnalyticsBridgeService" in program_source
        and "AddSingleton<DesktopAnalyticsClient>()" in desktop_app_source
        and 'TrackDesktopShellEventAsync("desktop_shell_opened"' in desktop_main_window_source
        and 'TrackDesktopShellEventAsync("desktop_open_settings"' in desktop_main_window_source
        and "DesktopAnalyticsTrackRequest" in desktop_analytics_source
        and "AnalyticsOptIn" in desktop_preference_source
        and "RYBBIT_CHUMMER_DESKTOP_SITE_ID=" in env_example
        and "RYBBIT_CHUMMER_DESKTOP_API_KEY=" in env_example
        and "RYBBIT_CHUMMER_DESKTOP_API_ORIGIN=https://app.rybbit.io" in env_example
        and "RYBBIT_CHUMMER_DESKTOP_SITE_ID: ${RYBBIT_CHUMMER_DESKTOP_SITE_ID:-}" in compose_source
        and "RYBBIT_CHUMMER_DESKTOP_API_KEY: ${RYBBIT_CHUMMER_DESKTOP_API_KEY:-}" in compose_source
        and "RYBBIT_CHUMMER_DESKTOP_API_ORIGIN: ${RYBBIT_CHUMMER_DESKTOP_API_ORIGIN:-https://app.rybbit.io}" in compose_source
    )
    if not rybbit_pass:
        failures.append("rybbit public analytics lane is missing runtime-ready CTA telemetry coverage")
    checks["rybbit_public_analytics"] = {
        "path": str(RYBBIT_RECEIPT_PATH),
        "status": rybbit_receipt.get("status", "missing"),
        "runtime_ready": rybbit_receipt.get("runtime_ready"),
        "pass": rybbit_pass,
    }

    neuronwriter_receipt = load_json(NEURONWRITER_RECEIPT_PATH)
    neuronwriter_pass = (
        status_pass(neuronwriter_receipt)
        and "NeuronWriter may optimize approved source packets." in growth_doc
        and "- NeuronWriter" in ltd_registry
        and "`NeuronWriter`" in ltd_map
    )
    if not neuronwriter_pass:
        failures.append("neuronwriter source-packet SEO workflow is not discoverable")
    checks["neuronwriter_source_packet_workflow"] = {
        "path": str(NEURONWRITER_RECEIPT_PATH),
        "status": neuronwriter_receipt.get("status", "missing"),
        "runtime_ready": neuronwriter_receipt.get("runtime_ready"),
        "pass": neuronwriter_pass,
    }

    subscribr_receipt = load_json(SUBSCRIBR_RECEIPT_PATH)
    subscribr_pass = (
        status_pass(subscribr_receipt)
        and subscribr_receipt.get("license_tier") == "License Tier 7 / Scale 3"
        and subscribr_receipt.get("runtime_ready") is False
        and "Subscribr.ai" in ltd_registry
        and "`Subscribr.ai`" in ltd_map
        and "approved Chummer source packets" in read_text(DESIGN_ROOT / "SUBSCRIBR_SCRIPT_FACTORY_PROVIDER_BOUNDARY.md")
    )
    if not subscribr_pass:
        failures.append("subscribr tier 7 script pre-production lane is not discoverable and bounded")
    checks["subscribr_script_preproduction"] = {
        "path": str(SUBSCRIBR_RECEIPT_PATH),
        "status": subscribr_receipt.get("status", "missing"),
        "license_tier": subscribr_receipt.get("license_tier"),
        "runtime_ready": subscribr_receipt.get("runtime_ready"),
        "pass": subscribr_pass,
    }

    provider_discoverability = load_json(PROVIDER_DISCOVERABILITY_PATH)
    clickrank_pass = (
        status_pass(provider_discoverability)
        and "CLICKRANK_AI_CHUMMER_RUN_SITE_ID" in layout_source
        and "ClickRank audit" in growth_doc
        and "`ClickRank`" in ltd_map
    )
    if not clickrank_pass:
        failures.append("clickrank visibility lane is not discoverable and wired")
    checks["clickrank_visibility_lane"] = {
        "path": str(PROVIDER_DISCOVERABILITY_PATH),
        "status": provider_discoverability.get("status", "missing"),
        "pass": clickrank_pass,
    }

    rafter_gate = load_json(RAFTER_GATE_PATH)
    pixefy_gate = load_json(PIXEFY_GATE_PATH)
    rafter_pass = str(rafter_gate.get("status") or "").strip().lower() == "pass"
    pixefy_pass = str(pixefy_gate.get("status") or "").strip().lower() == "pass"
    if not rafter_pass:
        failures.append("rafter auxiliary release QA gate is missing or failing")
    if not pixefy_pass:
        failures.append("pixefy auxiliary visual QA gate is missing or failing")
    checks["rafter_security_gate"] = {
        "path": str(RAFTER_GATE_PATH),
        "status": rafter_gate.get("status", "missing"),
        "pass": rafter_pass,
    }
    checks["pixefy_visual_gate"] = {
        "path": str(PIXEFY_GATE_PATH),
        "status": pixefy_gate.get("status", "missing"),
        "pass": pixefy_pass,
    }

    combined_ready = False
    combined_source = ""
    if RAFTER_PIXEFY_VERDICT_MD.is_file():
        combined_source = str(RAFTER_PIXEFY_VERDICT_MD)
        combined_ready = READY_VERDICT in read_text(RAFTER_PIXEFY_VERDICT_MD)
    else:
        reasons = load_json(RAFTER_PIXEFY_REASONS_JSON)
        combined_source = str(RAFTER_PIXEFY_REASONS_JSON)
        combined_ready = str(reasons.get("verdict") or "").strip() == READY_VERDICT
    boundary_doc = read_text(RAFTER_PIXEFY_BOUNDARY_PATH)
    combined_pass = combined_ready and READY_VERDICT in boundary_doc
    if not combined_pass:
        failures.append("rafter/pixefy combined auxiliary QA stack is not ready")
    checks["rafter_pixefy_stack"] = {
        "path": combined_source,
        "status": READY_VERDICT if combined_ready else "missing_or_not_ready",
        "pass": combined_pass,
    }

    return {
        "contract_name": "chummer.ltd_optimization_stack",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "verdict": "LTD_OPTIMIZATION_STACK_READY" if not failures else "LTD_OPTIMIZATION_STACK_NOT_READY",
        "checks": checks,
        "failures": failures,
    }


def main() -> int:
    payload = build_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"ltd_optimization_stack:{payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
