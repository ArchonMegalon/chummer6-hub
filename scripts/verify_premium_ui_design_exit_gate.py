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
    {
        "name": "Atlassian Design System",
        "url": "https://atlassian.design/",
        "gate_translation": "clear product language, predictable navigation, humane density, and resilient component behavior",
    },
    {
        "name": "Shopify Polaris",
        "url": "https://polaris.shopify.com/",
        "gate_translation": "commerce-grade task clarity, action hierarchy, content discipline, and usable empty/loading/error states",
    },
    {
        "name": "GOV.UK Service Manual",
        "url": "https://www.gov.uk/service-manual",
        "gate_translation": "plain-language service journeys where the next action and user obligation are never ambiguous",
    },
    {
        "name": "WCAG 2.2",
        "url": "https://www.w3.org/TR/WCAG22/",
        "gate_translation": "visible focus, legible contrast, input readability, and touch target discipline",
    },
    {
        "name": "Nielsen Norman Group Usability Heuristics",
        "url": "https://www.nngroup.com/articles/ten-usability-heuristics/",
        "gate_translation": "status visibility, recognition over recall, consistency, and clear task feedback",
    },
]
DESIGN_STANDARD_PRINCIPLES = [
    {
        "id": "five_second_first_impression",
        "standard": "Apple HIG clarity plus Nielsen status visibility",
        "exit_rule": "A new visitor must know what Chummer is, which build to use, and where help lives in one glance.",
    },
    {
        "id": "editorial_identity",
        "standard": "Material/Fluent/Carbon design-token discipline",
        "exit_rule": "Typography, color, depth, spacing, and surface rhythm must be named systems, not incidental page styling.",
    },
    {
        "id": "premium_depth_without_noise",
        "standard": "Apple deference plus Fluent elevation",
        "exit_rule": "Atmosphere may create depth, but it cannot compete with install, play, status, or recovery decisions.",
    },
    {
        "id": "one_route_one_job",
        "standard": "GOV.UK service design plus Shopify action hierarchy",
        "exit_rule": "Each public route needs one visible job, one primary next action, and supporting choices that do not blur the job.",
    },
    {
        "id": "accessibility_as_finish",
        "standard": "WCAG 2.2 plus Carbon production consistency",
        "exit_rule": "Contrast, focus, form controls, touch targets, reduced motion, and mobile layout are release criteria, not cleanup.",
    },
    {
        "id": "quiet_public_language",
        "standard": "Atlassian content discipline plus HIG clarity",
        "exit_rule": "Public pages must read like a product, not like a proof harness, provider adapter, internal roadmap, or operator console.",
    },
]
ROUTE_JOURNEY_REQUIREMENTS = {
    "Landing.cshtml": {
        "job": "Explain Chummer and make the first install/open action obvious.",
        "required_markers": ["minimal-hero", "<h1", "href=\"/downloads\"", "button-like--primary"],
    },
    "Downloads.cshtml": {
        "job": "Get the user onto the right build without crowding the decision.",
        "required_markers": ["downloads-choice-card", "<h1", "Stable", "Nightly", "href=\"/help\""],
    },
    "Status.cshtml": {
        "job": "Tell users whether they should install, wait, or ask for help.",
        "required_markers": ["minimal-status-pill", "<h1", "href=\"/downloads\"", "href=\"/help\""],
    },
    "Partizipate.cshtml": {
        "job": "Show the participation board as the product surface without extra wrapper noise.",
        "required_markers": ["participate-hosted__frame-shell", "<iframe", "Model.EmbeddedBoardHref"],
    },
    "MobileProjection.cshtml": {
        "job": "Expose the PWA playtime lane with install, live ledger, continuity, and help actions.",
        "required_markers": ["pwa-ledger-stream", "data-pwa-install-state", "data-pwa-ledger-status", "href=\"/help\""],
    },
}
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


def count_css(pattern: str, css: str, *, ignore_case: bool = False) -> int:
    flags = re.IGNORECASE if ignore_case else 0
    return len(re.findall(pattern, css, flags=flags))


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


def route_requirement_result(path: Path) -> dict[str, Any]:
    requirement = ROUTE_JOURNEY_REQUIREMENTS.get(path.name)
    if requirement is None:
        return {
            "route": path.name,
            "job": "No premium route contract is registered.",
            "missing_markers": ["route contract"],
            "pass": False,
        }

    text = read_text(path)
    missing = [
        marker
        for marker in requirement["required_markers"]
        if marker not in text
    ]
    return {
        "route": path.name,
        "job": requirement["job"],
        "required_markers": requirement["required_markers"],
        "missing_markers": missing,
        "pass": not missing,
    }


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

    color_tokens = sorted(
        name
        for name in tokens
        if name.startswith(("color-", "bg-", "surface-", "ink-", "accent-", "line-", "text-", "link-"))
    )
    hex_palette = sorted({match.group(0).lower() for match in re.finditer(r"#[0-9a-fA-F]{3,8}\b", css)})
    named_palette_requirements = {
        "--color-background-canvas": "--color-background-canvas:" in css,
        "--color-background-panel": "--color-background-panel:" in css,
        "--color-border-subtle": "--color-border-subtle:" in css,
        "--color-text-primary": "--color-text-primary:" in css,
        "--color-text-muted": "--color-text-muted:" in css,
        "--color-accent-primary": "--color-accent-primary:" in css,
        "--color-accent-danger": "--color-accent-danger:" in css,
    }
    palette_pass = (
        len(color_tokens) >= 10
        and len(hex_palette) >= 8
        and all(named_palette_requirements.values())
        and "color-scheme: dark" in css
    )
    if not palette_pass:
        failures.append("premium palette is under-specified; require named semantic colors, dark scheme discipline, and enough tonal range")
    checks["premium_palette"] = {
        "standard": "Material color roles + Fluent/Carbon semantic tokens",
        "color_token_count": len(color_tokens),
        "hex_palette_count": len(hex_palette),
        "required_semantic_tokens": named_palette_requirements,
        "has_dark_color_scheme": "color-scheme: dark" in css,
        "pass": palette_pass,
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

    hover_count = count_css(r":hover\b", css)
    focus_visible_count = count_css(r":focus-visible\b", css)
    touch_target_count = count_css(r"min-height:\s*(?:4[4-9]|[5-9]\d)px", css)
    focus_outline_pass = "::focus-visible" in css or count_css(r"outline(?:-offset)?:", css) >= 4
    interaction_pass = hover_count >= 20 and focus_visible_count >= 18 and touch_target_count >= 4 and focus_outline_pass
    if not interaction_pass:
        failures.append("interaction affordance is too weak; premium UI needs visible focus, hover states, and touch-safe targets")
    checks["interaction_affordance"] = {
        "standard": "HIG touch targets + WCAG focus visible + Fluent interaction states",
        "hover_selector_count": hover_count,
        "focus_visible_selector_count": focus_visible_count,
        "touch_safe_min_height_count": touch_target_count,
        "has_focus_outline": focus_outline_pass,
        "pass": interaction_pass,
    }

    media_query_count = count_css(r"@media\s*\(", css)
    responsive_pass = (
        media_query_count >= 6
        and "@media (max-width: 720px)" in css
        and ("@media (max-width: 980px)" in css or "@media (max-width: 1024px)" in css)
        and "clamp(" in css
        and "minmax(" in css
        and "svh" in css
    )
    if not responsive_pass:
        failures.append("responsive system is not flagship-grade; require mobile breakpoints, fluid type/spacing, minmax grids, and svh handling")
    checks["responsive_layout"] = {
        "standard": "HIG platform adaptation + Material responsive layout",
        "media_query_count": media_query_count,
        "has_mobile_breakpoint_720": "@media (max-width: 720px)" in css,
        "has_tablet_breakpoint": "@media (max-width: 980px)" in css or "@media (max-width: 1024px)" in css,
        "has_clamp": "clamp(" in css,
        "has_minmax": "minmax(" in css,
        "has_svh": "svh" in css,
        "pass": responsive_pass,
    }

    form_control_markers = {
        "input_select_textarea_base": "input:not([type=\"hidden\"]):not([type=\"checkbox\"]):not([type=\"radio\"])" in css
        and "select," in css
        and "textarea" in css,
        "placeholder_legible": "::placeholder" in css,
        "select_option_dark": "select option" in css and "select optgroup" in css,
        "selected_option_state": "select option:checked" in css,
        "caret_and_accent": "caret-color:" in css and "accent-color:" in css,
        "field_focus_state": ".field input:focus" in css and ".field select:focus" in css and ".field textarea:focus" in css,
    }
    form_control_pass = all(form_control_markers.values())
    if not form_control_pass:
        failures.append("form controls are not fully dark-mode readable; textboxes, selects, placeholders, options, and focus states must be styled")
    checks["form_control_legibility"] = {
        "standard": "WCAG legibility + HIG direct manipulation for input surfaces",
        "markers": form_control_markers,
        "pass": form_control_pass,
    }

    layout_markers = {
        "site_header_chrome": ".site-header__inner" in css,
        "hero_visual": ".minimal-hero__visual" in css,
        "cinematic_landing": ".landing-film" in css,
        "editorial_strip": ".editorial-strip" in css,
        "downloads_quicknav": ".downloads-quicknav" in css,
        "ledger_geoscape": ".black-ledger-geoscape" in css,
        "site_max_token": "--site-max:" in css,
    }
    composition_pass = (
        all(layout_markers.values())
        and count_css(r"display:\s*grid", css) >= 20
        and count_css(r"display:\s*flex", css) >= 10
        and "backdrop-filter:" in css
    )
    if not composition_pass:
        failures.append("composition still reads like a template; require premium chrome, hero/media, editorial, navigation, and dense layout systems")
    checks["composition_hierarchy"] = {
        "standard": "Nielsen consistency + Carbon structure + Fluent depth",
        "markers": layout_markers,
        "grid_layout_count": count_css(r"display:\s*grid", css),
        "flex_layout_count": count_css(r"display:\s*flex", css),
        "has_glass_chrome": "backdrop-filter:" in css,
        "pass": composition_pass,
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

    route_results = [route_requirement_result(path) for path in critical_public_views]
    route_contract_pass = all(result["pass"] for result in route_results)
    if not route_contract_pass:
        failures.append("premium route contracts are incomplete; each critical route needs a visible job, primary action, and route-specific premium component")
    checks["route_journey_contracts"] = {
        "standard": "GOV.UK service journey clarity + Shopify action hierarchy + Nielsen recognition over recall",
        "route_count": len(route_results),
        "routes": route_results,
        "pass": route_contract_pass,
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
        "design_principles": DESIGN_STANDARD_PRINCIPLES,
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
        "## Exit Principles",
        "",
        *[
            f"- `{item['id']}`: {item['exit_rule']} Source posture: {item['standard']}."
            for item in payload["design_principles"]
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
