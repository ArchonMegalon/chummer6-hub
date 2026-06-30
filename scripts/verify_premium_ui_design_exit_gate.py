#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = ROOT / ".codex-studio" / "published"
COMPLETION_ROOT = Path("/docker/chummercomplete/_completion/chummer_run_redesign_closure")
CSS_PATH = ROOT / "Chummer.Run.Api/wwwroot/css/site.css"
OUTPUT = PUBLISHED_ROOT / "PREMIUM_UI_DESIGN_EXIT_GATE.generated.json"
REPORT = PUBLISHED_ROOT / "PREMIUM_UI_DESIGN_EXIT_GATE.md"
CRITICAL_PUBLIC_VIEWS = [
    ROOT / "Chummer.Run.Api/Views/PublicLanding/Landing.cshtml",
    ROOT / "Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml",
    ROOT / "Chummer.Run.Api/Views/PublicLanding/Status.cshtml",
    ROOT / "Chummer.Run.Api/Views/PublicLanding/Partizipate.cshtml",
    ROOT / "Chummer.Run.Api/Views/PublicLanding/MobileProjection.cshtml",
]
REFERENCE_SYSTEMS = [
    {
        "name": "Apple Human Interface Guidelines",
        "url": "https://developer.apple.com/design/human-interface-guidelines/",
        "gate_translation": "clarity, deference, depth, touch-safe controls, and direct task hierarchy",
    },
    {
        "name": "Material Design 3 Foundations",
        "url": "https://m3.material.io/foundations",
        "gate_translation": "deliberate color, typography, motion, layout, and component affordance systems",
    },
    {
        "name": "Microsoft Fluent 2",
        "url": "https://fluent2.microsoft.design/",
        "gate_translation": "coherent design tokens, elevation, spacing, and interaction states across platforms",
    },
    {
        "name": "IBM Carbon Design System",
        "url": "https://carbondesignsystem.com/",
        "gate_translation": "2x-grid discipline, accessible structure, purposeful density, and production-ready consistency",
    },
]
BORING_FONT_MARKERS = {
    "arial",
    "blinkmacsystemfont",
    "helvetica",
    "inter",
    "roboto",
    "sans-serif",
    "segoe ui",
    "system-ui",
}
INTERNAL_LANGUAGE_NEEDLES = [
    "proof",
    "receipt",
    "operator",
    "governor",
    "provider",
    "ProductLift",
    "fleet",
]


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def status_pass(payload: dict[str, Any]) -> bool:
    return str(payload.get("status") or "").strip().lower() in {"pass", "passed", "ready"}


def extract_css_tokens(css: str) -> dict[str, str]:
    return {
        match.group(1).strip(): match.group(2).strip()
        for match in re.finditer(r"--([A-Za-z0-9_-]+)\s*:\s*([^;]+);", css)
    }


def font_families(value: str) -> list[str]:
    return [
        family.strip().strip("\"'").lower()
        for family in value.split(",")
        if family.strip()
    ]


def font_stack_is_distinctive(value: str) -> bool:
    families = font_families(value)
    return bool(families) and any(family not in BORING_FONT_MARKERS for family in families)


def parse_px_numbers(value: str) -> list[float]:
    return [float(match.group(1)) for match in re.finditer(r"(-?\d+(?:\.\d+)?)px", value)]


def shadow_has_depth(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized or normalized == "none":
        return False
    numbers = parse_px_numbers(normalized)
    return len(numbers) >= 2 and max(numbers) >= 18


def markdown_status(path: Path) -> str:
    text = read_text(path)
    match = re.search(r"^- Status:\s*`?([A-Za-z0-9_-]+)`?", text, flags=re.MULTILINE)
    return match.group(1).lower() if match else "missing"


def build_payload(
    *,
    css_path: Path = CSS_PATH,
    completion_root: Path = COMPLETION_ROOT,
    published_root: Path = PUBLISHED_ROOT,
    critical_public_views: list[Path] = CRITICAL_PUBLIC_VIEWS,
) -> dict[str, Any]:
    failures: list[str] = []
    checks: dict[str, Any] = {}
    css = read_text(css_path)
    tokens = extract_css_tokens(css)

    display_font = tokens.get("font-family-display", "")
    body_font = tokens.get("font-family-base", "")
    typography_pass = (
        font_stack_is_distinctive(display_font)
        and font_stack_is_distinctive(body_font)
        and font_families(display_font)[:1] != font_families(body_font)[:1]
    )
    if not typography_pass:
        failures.append("premium typography is not distinctive; display/body stacks are generic or identical")
    checks["premium_typography"] = {
        "standard": "HIG clarity + Material/Fluent/Carbon type-system discipline",
        "display_font": display_font,
        "body_font": body_font,
        "pass": typography_pass,
    }

    soft_shadow = tokens.get("shadow-soft", "")
    hero_shadow = tokens.get("shadow-hero", "")
    elevation_pass = shadow_has_depth(soft_shadow) and shadow_has_depth(hero_shadow) and soft_shadow != hero_shadow
    if not elevation_pass:
        failures.append("premium elevation is missing; shadow tokens must create distinct soft and hero depth")
    checks["premium_elevation"] = {
        "standard": "HIG depth + Fluent elevation",
        "shadow_soft": soft_shadow,
        "shadow_hero": hero_shadow,
        "pass": elevation_pass,
    }

    spacing_tokens = sorted(name for name in tokens if name.startswith("space-") or name.startswith("spacing-"))
    radius_tokens = {name: value for name, value in tokens.items() if name.startswith("radius-")}
    distinct_radius_values = {value for value in radius_tokens.values()}
    spacing_pass = len(spacing_tokens) >= 6 and len(distinct_radius_values) >= 3
    if not spacing_pass:
        failures.append("spatial system is under-specified; add 2x/8px spacing tokens and distinct radius tiers")
    checks["spatial_system"] = {
        "standard": "Carbon 2x-grid + Material layout rhythm",
        "spacing_token_count": len(spacing_tokens),
        "radius_tokens": radius_tokens,
        "distinct_radius_count": len(distinct_radius_values),
        "pass": spacing_pass,
    }

    gradient_count = len(re.findall(r"(?:linear|radial)-gradient\(", css))
    art_direction_pass = gradient_count >= 20 and "minimal-hero__visual" in css and "landing-film" in css
    if not art_direction_pass:
        failures.append("art direction is too flat; critical public routes need a deliberate hero/media language")
    checks["art_direction"] = {
        "standard": "HIG deference with purposeful visual depth",
        "gradient_count": gradient_count,
        "has_minimal_hero_visual_css": "minimal-hero__visual" in css,
        "has_landing_film_css": "landing-film" in css,
        "pass": art_direction_pass,
    }

    motion_pass = "@media (prefers-reduced-motion: reduce)" in css and "transition:" in css and "@keyframes" in css
    if not motion_pass:
        failures.append("motion system is incomplete; use restrained motion with reduced-motion fallback")
    checks["motion_governance"] = {
        "standard": "Material motion + accessibility fallback",
        "has_transitions": "transition:" in css,
        "has_keyframes": "@keyframes" in css,
        "has_reduced_motion": "@media (prefers-reduced-motion: reduce)" in css,
        "pass": motion_pass,
    }

    view_text = "\n".join(read_text(path) for path in critical_public_views)
    leaked_terms = sorted({needle for needle in INTERNAL_LANGUAGE_NEEDLES if re.search(rf"\b{re.escape(needle)}\b", view_text, flags=re.IGNORECASE)})
    public_copy_gate = load_json(published_root / "PUBLIC_COPY_LEAK_GATE.generated.json")
    copy_pass = not leaked_terms and status_pass(public_copy_gate)
    if not copy_pass:
        failures.append("premium public copy is not quiet enough; internal or provider-facing terms remain visible")
    checks["public_copy_quiet"] = {
        "standard": "HIG clarity and Carbon production copy consistency",
        "view_count": len(critical_public_views),
        "leaked_terms": leaked_terms,
        "public_copy_leak_gate_status": public_copy_gate.get("status", "missing"),
        "pass": copy_pass,
    }

    ui_frame = load_json(completion_root / "UI_FRAME_INTEGRITY.generated.json")
    frame_summary = ui_frame.get("summary") if isinstance(ui_frame.get("summary"), dict) else {}
    frame_pass = status_pass(ui_frame) and int(frame_summary.get("failure_count") or 0) == 0
    contrast = load_json(completion_root / "CONTRAST_AUDIT.generated.json")
    minimal = load_json(completion_root / "MINIMAL_EXPERIENCE_GATE.generated.json")
    noise_status = markdown_status(completion_root / "NOISE_BUDGET_REPORT.md")
    production_gate_pass = frame_pass and status_pass(contrast) and status_pass(minimal) and noise_status == "pass"
    if not production_gate_pass:
        failures.append("premium production basics are not closed; frame, contrast, minimal, and noise gates must pass together")
    checks["production_basics"] = {
        "standard": "accessible production polish before subjective taste",
        "ui_frame_status": ui_frame.get("status", "missing"),
        "ui_frame_failure_count": frame_summary.get("failure_count"),
        "contrast_status": contrast.get("status", "missing"),
        "minimal_experience_status": minimal.get("status", "missing"),
        "minimal_experience_failure_count": len(minimal.get("failures") or []),
        "noise_budget_status": noise_status,
        "pass": production_gate_pass,
    }

    return {
        "contract_name": "chummer.premium_ui_design_exit_gate",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "verdict": "PREMIUM_UI_READY" if not failures else "PREMIUM_UI_NOT_READY",
        "reference_systems": REFERENCE_SYSTEMS,
        "css_path": str(css_path),
        "completion_root": str(completion_root),
        "published_root": str(published_root),
        "checks": checks,
        "failures": failures,
    }


def write_outputs(payload: dict[str, Any], output: Path, report: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Premium UI Design Exit Gate",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Status: `{payload['status']}`",
        f"- Verdict: `{payload['verdict']}`",
        "",
        "## Reference Standard",
        "",
        *[
            f"- {item['name']}: {item['gate_translation']} ({item['url']})"
            for item in payload["reference_systems"]
        ],
        "",
        "## Failures",
        "",
        *(f"- {failure}" for failure in payload["failures"]),
        "",
        "## Checks",
        "",
        *[
            f"- {name}: `{'pass' if check.get('pass') else 'fail'}`"
            for name, check in payload["checks"].items()
        ],
    ]
    report.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the public UI is premium enough to exit design review.")
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--report", default=str(REPORT))
    parser.add_argument("--completion-dir", default=str(COMPLETION_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    report = Path(args.report)
    payload = build_payload(completion_root=Path(args.completion_dir), published_root=output.parent)
    write_outputs(payload, output, report)
    print(f"premium_ui_design_exit_gate:{payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
