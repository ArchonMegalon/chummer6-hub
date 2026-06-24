#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
COMPLETION_ROOT = Path(os.environ.get("CHUMMER_COMPLETION_DIR", "/docker/chummercomplete/_completion/chummer_run_redesign_closure"))
PRESENTATION_PUBLISHED_ROOT = Path(os.environ.get("CHUMMER_PRESENTATION_PUBLISHED_ROOT", "/docker/chummercomplete/chummer-presentation/.codex-studio/published"))
OUTPUT = PUBLISHED_ROOT / "DESIGN_QUALITY_GATE.generated.json"
LIVE_RECRAWL_PATH = PUBLISHED_ROOT / "LIVE_PUBLIC_WEB_RECRAWL.generated.json"
PUBLIC_ROUTE_PROOF_PATH = PUBLISHED_ROOT / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"
LIVE_SURFACE_PARITY_PATH = PUBLISHED_ROOT / "LIVE_SURFACE_PARITY.generated.json"
LTD_OPTIMIZATION_STACK_PATH = PUBLISHED_ROOT / "LTD_OPTIMIZATION_STACK.generated.json"
REQUIRED_VIEWPORTS = {"390x844", "412x915", "768x1024", "1366x768", "1440x900", "1920x1080"}
SUPPORTING_SURFACE_VIEWPORTS = {"390x844", "1366x768"}
REQUIRED_SUPPORTING_SURFACES = {"downloads", "status", "ledger-map"}
MINIMAL_EXPERIENCE_GATE_PATH = COMPLETION_ROOT / "MINIMAL_EXPERIENCE_GATE.generated.json"
DESIGN_REVIEW_PATH = Path("/docker/chummercomplete/chummer-design/products/chummer/FINAL_PRODUCT_DESIGN_REVIEW.md")
DESIGN_REVIEW_REQUIRED_SECTIONS = [
    "## Surface Hierarchy",
    "## Installation and First-Run",
    "## Status and Support",
    "## Desktop",
    "## Black Ledger",
    "## Human Acceptance",
    "## Media Acceptance",
    "## Product Modes",
]
DESIGN_REVIEW_REQUIRED_CHECKS = [
    "first impression communicates Chummer in under five seconds",
    "Black Ledger has a large command-map centerpiece",
    "public copy is free of proof-dashboard language",
    "downloads keep account setup optional",
    "desktop surfaces do not present inert actions as ready",
    "provider and proof lanes stay out of the primary user journey",
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


def parse_report_status(path: Path) -> str:
    if not path.is_file():
        return "missing"
    match = re.search(r"^- Status:\s*`?([A-Za-z0-9_-]+)`?", path.read_text(encoding="utf-8"), flags=re.MULTILINE)
    return match.group(1).lower() if match else "unknown"


def check_final_product_design_review(path: Path) -> tuple[bool, list[str], list[str]]:
    if not path.is_file():
        return False, [], []

    text = path.read_text(encoding="utf-8")
    lower_text = text.lower()
    missing_sections = [
        section
        for section in DESIGN_REVIEW_REQUIRED_SECTIONS
        if section.lower() not in lower_text
    ]
    missing_checks: list[str] = []

    for item in ("[x]", "[X]"):
        if item in text:
            break
    else:
        missing_checks.append("review appears to lack checked outcome rows")

    for required_check in DESIGN_REVIEW_REQUIRED_CHECKS:
        if required_check.lower() not in lower_text:
            missing_checks.append(f"missing required checked design assertion: {required_check}")

    if "Verdict: `DESIGN_READY`" not in text:
        missing_checks.append("final product design review is not currently design-ready")

    return len(missing_sections) == 0 and len(missing_checks) == 0, missing_sections, missing_checks


def status_pass(payload: dict[str, Any]) -> bool:
    return str(payload.get("status") or "").strip().lower() in {"pass", "passed", "ready"}


def normalize_base_url(value: object) -> str:
    return str(value or "").strip().rstrip("/")


def is_public_base_url(base_url: str) -> bool:
    return base_url == "https://chummer.run"


def is_loopback_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost"}


def visual_proof_base_url_passes(base_url: str, *, live_public_ready: bool) -> bool:
    if is_public_base_url(base_url):
        return True
    return live_public_ready and is_loopback_base_url(base_url)


def build_payload() -> dict[str, Any]:
    failures: list[str] = []
    checks: dict[str, Any] = {}

    live_recrawl = load_json(LIVE_RECRAWL_PATH)
    live_recrawl_pass = status_pass(live_recrawl) and int(len(live_recrawl.get("results") or [])) >= 6
    if not live_recrawl_pass:
        failures.append("live public recrawl is missing or failing")
    checks["live_public_web_recrawl"] = {
        "path": str(LIVE_RECRAWL_PATH),
        "status": live_recrawl.get("status", "missing"),
        "result_count": len(live_recrawl.get("results") or []),
        "pass": live_recrawl_pass,
    }

    public_route_proof = load_json(PUBLIC_ROUTE_PROOF_PATH)
    public_route_summary = public_route_proof.get("summary") if isinstance(public_route_proof.get("summary"), dict) else {}
    public_route_pass = (
        int(public_route_summary.get("route_count") or 0) > 0
        and int(public_route_summary.get("failed_count") or 0) == 0
        and int(public_route_summary.get("negative_path_failed_count") or 0) == 0
    )
    if not public_route_pass:
        failures.append("public route proof is missing or failing")
    checks["public_route_proof"] = {
        "path": str(PUBLIC_ROUTE_PROOF_PATH),
        "status": public_route_proof.get("status", "pass" if public_route_pass else "fail"),
        "route_count": public_route_summary.get("route_count"),
        "failed_count": public_route_summary.get("failed_count"),
        "pass": public_route_pass,
    }

    live_surface_parity = load_json(LIVE_SURFACE_PARITY_PATH)
    live_surface_parity_pass = status_pass(live_surface_parity) and not live_surface_parity.get("failures")
    if not live_surface_parity_pass:
        failures.append("live surface parity is missing or failing")
    checks["live_surface_parity"] = {
        "path": str(LIVE_SURFACE_PARITY_PATH),
        "status": live_surface_parity.get("status", "missing"),
        "failure_count": len(live_surface_parity.get("failures") or []),
        "pass": live_surface_parity_pass,
    }

    ltd_optimization_stack = load_json(LTD_OPTIMIZATION_STACK_PATH)
    ltd_optimization_stack_pass = status_pass(ltd_optimization_stack) and not ltd_optimization_stack.get("failures")
    ltd_checks = ltd_optimization_stack.get("checks") if isinstance(ltd_optimization_stack.get("checks"), dict) else {}
    icanpreneur_check = ltd_checks.get("icanpreneur_discovery_interview") if isinstance(ltd_checks.get("icanpreneur_discovery_interview"), dict) else {}
    icanpreneur_design_lane_pass = (
        ltd_optimization_stack_pass
        and bool(icanpreneur_check.get("pass"))
        and str(icanpreneur_check.get("status") or "").strip().lower() == "tracked"
        and str(icanpreneur_check.get("lane_status") or "").strip().lower() == "pass"
        and icanpreneur_check.get("license_tier") == "Tier 3"
        and icanpreneur_check.get("runtime_ready") is False
    )
    if not ltd_optimization_stack_pass:
        failures.append("LTD optimization stack is missing or failing")
    if not icanpreneur_design_lane_pass:
        failures.append("Icanpreneur discovery lane is missing from the design-quality LTD stack")
    checks["ltd_optimization_stack"] = {
        "path": str(LTD_OPTIMIZATION_STACK_PATH),
        "status": ltd_optimization_stack.get("status", "missing"),
        "verdict": ltd_optimization_stack.get("verdict"),
        "failure_count": len(ltd_optimization_stack.get("failures") or []),
        "pass": ltd_optimization_stack_pass,
    }
    checks["icanpreneur_design_lane"] = {
        "path": str(LTD_OPTIMIZATION_STACK_PATH),
        "status": icanpreneur_check.get("status", "missing"),
        "lane_status": icanpreneur_check.get("lane_status", "missing"),
        "license_tier": icanpreneur_check.get("license_tier"),
        "runtime_ready": icanpreneur_check.get("runtime_ready"),
        "pass": icanpreneur_design_lane_pass,
    }

    ui_frame_path = COMPLETION_ROOT / "UI_FRAME_INTEGRITY.generated.json"
    ui_frame = load_json(ui_frame_path)
    frame_summary = ui_frame.get("summary") if isinstance(ui_frame.get("summary"), dict) else {}
    frame_failure_count = frame_summary.get("failure_count")
    live_public_ready = live_recrawl_pass and public_route_pass and live_surface_parity_pass
    frame_base_url = normalize_base_url(ui_frame.get("base_url"))
    frame_pass = (
        status_pass(ui_frame)
        and int(frame_summary.get("checked_pages") or 0) >= 60
        and int(frame_failure_count if frame_failure_count is not None else -1) == 0
        and visual_proof_base_url_passes(frame_base_url, live_public_ready=live_public_ready)
    )
    if not frame_pass:
        failures.append("ui frame integrity gate is missing, too narrow, failing, or not recorded against the live site")
    checks["ui_frame_integrity"] = {
        "path": str(ui_frame_path),
        "status": ui_frame.get("status", "missing"),
        "base_url": ui_frame.get("base_url"),
        "checked_pages": frame_summary.get("checked_pages"),
        "failure_count": frame_summary.get("failure_count"),
        "pass": frame_pass,
    }

    screenshot_path = COMPLETION_ROOT / "SCREENSHOT_QA.generated.json"
    screenshot = load_json(screenshot_path)
    screenshot_results = screenshot.get("homepage_results") if isinstance(screenshot.get("homepage_results"), list) else []
    supporting_surface_results = screenshot.get("surface_results") if isinstance(screenshot.get("surface_results"), list) else []
    screenshot_viewports = {str(item.get("viewport")) for item in screenshot_results if isinstance(item, dict)}
    screenshot_failures = [
        str(item.get("viewport"))
        for item in screenshot_results
        if isinstance(item, dict) and str(item.get("status") or "").lower() != "pass"
    ]
    supporting_surface_failures = [
        f"{item.get('surface')}:{item.get('viewport')}"
        for item in supporting_surface_results
        if isinstance(item, dict) and str(item.get("status") or "").lower() != "pass"
    ]
    supporting_surface_coverage = {
        str(item.get("surface")): {
            str(entry.get("viewport"))
            for entry in supporting_surface_results
            if isinstance(entry, dict) and str(entry.get("surface")) == str(item.get("surface"))
        }
        for item in supporting_surface_results
        if isinstance(item, dict)
    }
    missing_supporting_surfaces = sorted(REQUIRED_SUPPORTING_SURFACES - set(supporting_surface_coverage))
    incomplete_supporting_viewports = {
        surface: sorted(SUPPORTING_SURFACE_VIEWPORTS - set(viewports))
        for surface, viewports in supporting_surface_coverage.items()
        if SUPPORTING_SURFACE_VIEWPORTS - set(viewports)
    }
    screenshot_base_url = normalize_base_url(screenshot.get("base_url"))
    missing_viewports = sorted(REQUIRED_VIEWPORTS - screenshot_viewports)
    screenshot_pass = (
        status_pass(screenshot)
        and not screenshot_failures
        and not supporting_surface_failures
        and not missing_viewports
        and not missing_supporting_surfaces
        and not incomplete_supporting_viewports
        and visual_proof_base_url_passes(screenshot_base_url, live_public_ready=live_public_ready)
    )
    if not screenshot_pass:
        failures.append("live screenshot QA is missing required flagship surface coverage or has failures")
    checks["screenshot_qa"] = {
        "path": str(screenshot_path),
        "status": screenshot.get("status", "missing"),
        "base_url": screenshot.get("base_url"),
        "homepage_viewports": sorted(screenshot_viewports),
        "missing_homepage_viewports": missing_viewports,
        "failed_homepage_viewports": screenshot_failures,
        "supporting_surface_viewports": {surface: sorted(viewports) for surface, viewports in supporting_surface_coverage.items()},
        "missing_supporting_surfaces": missing_supporting_surfaces,
        "incomplete_supporting_viewports": incomplete_supporting_viewports,
        "failed_supporting_surface_viewports": supporting_surface_failures,
        "pass": screenshot_pass,
    }

    cta_path = COMPLETION_ROOT / "CTA_HIERARCHY.generated.json"
    cta = load_json(cta_path)
    cta_pass = status_pass(cta) and not cta.get("failures")
    if not cta_pass:
        failures.append("CTA hierarchy proof is missing or failing")
    checks["cta_hierarchy"] = {
        "path": str(cta_path),
        "status": cta.get("status", "missing"),
        "failure_count": len(cta.get("failures") or []),
        "pass": cta_pass,
    }

    minimal_experience = load_json(MINIMAL_EXPERIENCE_GATE_PATH)
    minimal_experience_base_url = normalize_base_url(minimal_experience.get("base_url"))
    minimal_experience_pass = (
        status_pass(minimal_experience)
        and not minimal_experience.get("failures")
        and visual_proof_base_url_passes(minimal_experience_base_url, live_public_ready=live_public_ready)
    )
    if not minimal_experience_pass:
        failures.append("minimal experience gate is missing or failing")
    checks["minimal_experience_gate"] = {
        "path": str(MINIMAL_EXPERIENCE_GATE_PATH),
        "status": minimal_experience.get("status", "missing"),
        "base_url": minimal_experience.get("base_url"),
        "failure_count": len(minimal_experience.get("failures") or []),
        "pass": minimal_experience_pass,
    }

    asset_path = COMPLETION_ROOT / "PUBLIC_ASSET_QUALITY_GATE.generated.json"
    asset = load_json(asset_path)
    asset_pass = status_pass(asset) and int(asset.get("raster_image_count") or 0) > 0 and int(asset.get("failure_count") or 0) == 0
    if not asset_pass:
        failures.append("public asset quality proof is missing, imageless, or failing")
    checks["public_asset_quality"] = {
        "path": str(asset_path),
        "status": asset.get("status", "missing"),
        "raster_image_count": asset.get("raster_image_count"),
        "failure_count": asset.get("failure_count"),
        "pass": asset_pass,
    }

    contrast_path = COMPLETION_ROOT / "CONTRAST_AUDIT.generated.json"
    contrast = load_json(contrast_path)
    contrast_pass = status_pass(contrast)
    if not contrast_pass:
        failures.append("contrast audit is missing or failing")
    checks["contrast_audit"] = {
        "path": str(contrast_path),
        "status": contrast.get("status", "missing"),
        "pass": contrast_pass,
    }

    noise_path = COMPLETION_ROOT / "NOISE_BUDGET_REPORT.md"
    noise_status = parse_report_status(noise_path)
    noise_pass = noise_status == "pass"
    if not noise_pass:
        failures.append("noise budget report is missing or failing")
    checks["noise_budget"] = {
        "path": str(noise_path),
        "status": noise_status,
        "pass": noise_pass,
    }

    ux_verdict_path = COMPLETION_ROOT / "FINAL_CHUMMER_RUN_UX_VERDICT.md"
    ux_verdict_text = ux_verdict_path.read_text(encoding="utf-8") if ux_verdict_path.is_file() else ""
    ux_verdict_pass = "Verdict: `FLAGSHIP_FRONT_READY`" in ux_verdict_text
    if not ux_verdict_pass:
        failures.append("final UX verdict is missing or not flagship-front-ready")
    checks["final_ux_verdict"] = {
        "path": str(ux_verdict_path),
        "status": "pass" if ux_verdict_pass else "missing_or_not_ready",
        "pass": ux_verdict_pass,
    }

    ui_gold_path = PRESENTATION_PUBLISHED_ROOT / "UI_GOLD_PROOF_DEPTH_GATE.generated.json"
    ui_gold = load_json(ui_gold_path)
    ui_gold_pass = status_pass(ui_gold)
    if not ui_gold_pass:
        failures.append("UI gold proof-depth gate is missing or failing")
    checks["ui_gold_proof_depth"] = {
        "path": str(ui_gold_path),
        "status": ui_gold.get("status", "missing"),
        "verdict": ui_gold.get("verdict"),
        "pass": ui_gold_pass,
    }

    review_pass, review_missing_sections, review_missing_checks = check_final_product_design_review(DESIGN_REVIEW_PATH)
    if not review_pass:
        failures.append("final product design review is missing or incomplete")
    checks["final_product_design_review"] = {
        "path": str(DESIGN_REVIEW_PATH),
        "exists": DESIGN_REVIEW_PATH.is_file(),
        "pass": review_pass,
        "missing_sections": review_missing_sections,
        "missing_checks": review_missing_checks,
    }

    return {
        "contract_name": "chummer.design_quality_gate",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "verdict": "DESIGN_READY" if not failures else "DESIGN_NOT_READY",
        "completion_root": str(COMPLETION_ROOT),
        "checks": checks,
        "failures": failures,
    }


def main() -> int:
    payload = build_payload()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"design_quality_gate:{payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
