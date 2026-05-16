#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_COMPLETION_DIR = Path("/docker/chummercomplete/_completion/chummer_run_redesign_closure")
REPO_ROOT = Path("/docker/chummercomplete/chummer.run-services")
ROUTE_PROOF_PATH = REPO_ROOT / ".codex-studio" / "published" / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"


def completion_root() -> Path:
    raw = os.environ.get("CHUMMER_COMPLETION_DIR", "").strip()
    return Path(raw) if raw else DEFAULT_COMPLETION_DIR


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_status_line(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lower().startswith("- status:"):
            return line.split(":", 1)[1].strip().strip("`")
    return None


def parse_screenshot_report(path: Path) -> tuple[bool, list[str]]:
    failures: list[str] = []
    required = {
        "390x844",
        "412x915",
        "768x1024",
        "1366x768",
        "1440x900",
        "1920x1080",
    }
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        parts = line[2:].split(":", 1)
        if len(parts) != 2:
            continue
        viewport = parts[0].strip()
        status = parts[1].strip().strip("`")
        if viewport in required:
            seen.add(viewport)
            if status != "pass":
                failures.append(f"screenshot QA failed for {viewport} ({status})")
    missing = sorted(required - seen)
    failures.extend(f"missing screenshot QA row for {viewport}" for viewport in missing)
    return not failures, failures


def copy_route_proof(root: Path) -> Path | None:
    if not ROUTE_PROOF_PATH.is_file():
        return None
    target = root / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"
    target.write_text(ROUTE_PROOF_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def route_proof_passes(payload: dict) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    if status:
        return status == "pass"
    summary = payload.get("summary")
    if isinstance(summary, dict):
        failed_count = summary.get("failed_count")
        positive_proof_count = summary.get("positive_proof_count")
        if failed_count == 0 and isinstance(positive_proof_count, int) and positive_proof_count > 0:
            return True
    return False


def main() -> int:
    root = completion_root()
    failures: list[str] = []
    required_files = {
        "LIVE_LINK_AUDIT.generated.json": root / "LIVE_LINK_AUDIT.generated.json",
        "CONTRAST_AUDIT.generated.json": root / "CONTRAST_AUDIT.generated.json",
        "CTA_HIERARCHY.generated.json": root / "CTA_HIERARCHY.generated.json",
        "NOISE_BUDGET_REPORT.md": root / "NOISE_BUDGET_REPORT.md",
        "SCREENSHOT_QA_REPORT.md": root / "SCREENSHOT_QA_REPORT.md",
        "PUBLIC_ASSET_QUALITY_GATE.generated.json": root / "PUBLIC_ASSET_QUALITY_GATE.generated.json",
        "PUBLIC_FORBIDDEN_STRING_SCAN.generated.json": root / "PUBLIC_FORBIDDEN_STRING_SCAN.generated.json",
        "PUBLIC_OPERATOR_LEAK_SCAN.generated.json": root / "PUBLIC_OPERATOR_LEAK_SCAN.generated.json",
    }
    route_proof_artifact = copy_route_proof(root)

    for label, path in required_files.items():
        if not path.is_file():
            failures.append(f"missing artifact: {label}")
    if route_proof_artifact is None:
        failures.append("missing artifact: CHUMMER_PUBLIC_ROUTE_PROOF.generated.json")

    link_payload = contrast_payload = cta_payload = asset_payload = forbidden_payload = operator_payload = route_payload = None
    if not failures:
        link_payload = read_json(required_files["LIVE_LINK_AUDIT.generated.json"])
        contrast_payload = read_json(required_files["CONTRAST_AUDIT.generated.json"])
        cta_payload = read_json(required_files["CTA_HIERARCHY.generated.json"])
        asset_payload = read_json(required_files["PUBLIC_ASSET_QUALITY_GATE.generated.json"])
        forbidden_payload = read_json(required_files["PUBLIC_FORBIDDEN_STRING_SCAN.generated.json"])
        operator_payload = read_json(required_files["PUBLIC_OPERATOR_LEAK_SCAN.generated.json"])
        route_payload = read_json(route_proof_artifact)

        if link_payload.get("status") != "pass":
            failures.append("visible link audit did not pass")
        if contrast_payload.get("status") != "pass":
            failures.append("contrast audit did not pass")
        if cta_payload.get("status") != "pass":
            failures.append("CTA hierarchy audit did not pass")
        if asset_payload.get("status") != "pass":
            failures.append("asset quality gate did not pass")
        if forbidden_payload.get("status") != "pass":
            failures.append("public forbidden string scan did not pass")
        if operator_payload.get("status") != "pass":
            failures.append("public operator leak scan did not pass")
        if not route_proof_passes(route_payload):
            failures.append("public route proof did not pass")

        noise_status = parse_status_line(required_files["NOISE_BUDGET_REPORT.md"])
        if noise_status != "pass":
            failures.append("noise budget report did not pass")

        screenshots_ok, screenshot_failures = parse_screenshot_report(required_files["SCREENSHOT_QA_REPORT.md"])
        if not screenshots_ok:
            failures.extend(screenshot_failures)

        review_required = contrast_payload.get("review_required", [])
        if review_required and not screenshots_ok:
            failures.append("unsupported contrast backgrounds require screenshot QA coverage")

    verdict = "FLAGSHIP_FRONT_READY" if not failures else "NOT_READY"
    lines = [
        "# Final Chummer.run UX Verdict",
        "",
        f"Verdict: `{verdict}`",
        "",
        f"- Completion dir: `{root}`",
    ]
    if not failures:
        lines.extend(
            [
                "",
                "Why:",
                "- Live link audit passed.",
                "- Contrast audit passed.",
                "- CTA hierarchy and six-section homepage model passed.",
                "- Screenshot QA passed across all required viewports.",
                "- Homepage noise budget passed.",
                "- Asset quality gate passed.",
                "- Public forbidden-string scan passed.",
                "- Public operator-leak scan passed.",
                "- Public route proof passed.",
            ]
        )
    else:
        lines.extend(["", "Failures:"])
        lines.extend(f"- {failure}" for failure in failures)

    output_path = root / "FINAL_CHUMMER_RUN_UX_VERDICT.md"
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output_path.read_text(encoding="utf-8"))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
