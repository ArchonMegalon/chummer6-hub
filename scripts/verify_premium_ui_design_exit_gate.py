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
DESIGN_CONTRACT_PATH = ROOT / ".codex-design/product/PREMIUM_UI_DESIGN_EXIT_GATE.md"
OUTPUT = PUBLISHED_ROOT / "PREMIUM_UI_DESIGN_EXIT_GATE.generated.json"
REPORT = PUBLISHED_ROOT / "PREMIUM_UI_DESIGN_EXIT_GATE.md"
LAYOUT_VIEW = ROOT / "Chummer.Run.Api/Views/Shared/_Layout.cshtml"
SCREENSHOT_QA_PATH_NAME = "SCREENSHOT_QA.generated.json"
REQUIRED_SCREENSHOT_HOME_VIEWPORTS = {"390x844", "412x915", "768x1024", "1366x768", "1440x900", "1920x1080"}
REQUIRED_SCREENSHOT_SURFACES = {"downloads", "status", "ledger-map", "help", "contact"}
REQUIRED_SCREENSHOT_SURFACE_VIEWPORTS = {"390x844", "1366x768"}
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
DESIGN_CONTRACT_MARKERS = [
    "Apple Human Interface Guidelines",
    "Material Design 3",
    "Microsoft Fluent 2",
    "IBM Carbon Design System",
    "Atlassian Design System",
    "Shopify Polaris",
    "GOV.UK Service Manual",
    "WCAG 2.2",
    "Nielsen Norman Group usability heuristics",
    "five-second verdict",
    "one-route-one-job",
    "premium visual scorecard",
    "zero-internal-language rule",
    "mobile playtime standard",
    "dark-mode form controls",
    "44px action floor",
    "route visual anatomy",
    "public endpoint language ban",
    "visual evidence receipt",
    "state and recovery language",
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
    {
        "id": "state_and_recovery_design",
        "standard": "Nielsen status visibility plus Polaris empty/loading/error state clarity",
        "exit_rule": "Loading, empty, unavailable, and recovery states must explain what is happening and what the user can do next.",
    },
]
ROUTE_JOURNEY_REQUIREMENTS = {
    "Landing.cshtml": {
        "job": "Explain Chummer and make the first install/open action obvious.",
        "required_markers": [
            "minimal-hero",
            "<h1",
            "Download Chummer",
            "href=\"/downloads\"",
            "button-like--primary",
            "site-open-chummer-menu",
            "aria-label=\"Open Chummer options\"",
            "href=\"/build\"",
            "href=\"/mobile/player\"",
            "minimal-hero__visual",
        ],
    },
    "Downloads.cshtml": {
        "job": "Get the user onto the right build without crowding the decision.",
        "required_markers": [
            "downloads-choice-list",
            "downloads-choice-card",
            "<h1",
            "Stable",
            "Nightly",
            "data-release-lane=\"stable\"",
            "data-release-lane=\"nightly\"",
            "Sign in later only if you want to attach this installed copy",
            "href=\"/help\"",
        ],
    },
    "Status.cshtml": {
        "job": "Tell users whether they should install, wait, or ask for help.",
        "required_markers": [
            "minimal-status-pill",
            "<h1",
            "Current caution",
            "aria-label=\"Status next actions\"",
            "href=\"/downloads\"",
            "href=\"/help\"",
        ],
    },
    "Partizipate.cshtml": {
        "job": "Show the participation board as the product surface without extra wrapper noise.",
        "required_markers": [
            "participate-hosted__frame-shell",
            "participate-hosted__frame",
            "<iframe",
            "Model.EmbeddedBoardHref",
            "loading=\"eager\"",
            "referrerpolicy=\"strict-origin-when-cross-origin\"",
            "allow=\"clipboard-write; fullscreen\"",
            "allowfullscreen",
            "data-chummer-participate-frame",
            "participate-board-fallback",
        ],
    },
    "MobileProjection.cshtml": {
        "job": "Expose the PWA playtime lane with install, live ledger, continuity, and help actions.",
        "required_markers": [
            "pwa-ledger-stream",
            "data-install-prompt-button",
            "data-pwa-install-state",
            "data-pwa-ledger-status",
            "data-pwa-ledger-heat-meter",
            "data-pwa-ledger-follow-button",
            "data-pwa-continuity-summary",
            "Open continuity",
            "href=\"/help\"",
        ],
    },
}
STATE_AND_RECOVERY_REQUIREMENTS = {
    "Downloads.cshtml": {
        "job": "When a build is missing or under review, the user gets a useful next step.",
        "required_markers": [
            "minimal-empty",
            "No build is available right now",
            "href=\"/help\"",
            "Current note",
        ],
    },
    "Status.cshtml": {
        "job": "Status gives a decision and recovery split instead of passive status text.",
        "required_markers": [
            "Current caution",
            "aria-label=\"Status next actions\"",
            "href=\"/downloads\"",
            "href=\"/help\"",
        ],
    },
    "Partizipate.cshtml": {
        "job": "Iframe failure has a polite live fallback and recovery actions.",
        "required_markers": [
            "participate-board-fallback",
            "role=\"status\"",
            "aria-live=\"polite\"",
            "Retry",
            "Contact",
        ],
    },
    "MobileProjection.cshtml": {
        "job": "PWA/live-play failure states keep install, stream, follow, and continuity recovery readable.",
        "required_markers": [
            "data-pwa-ledger-summary",
            "data-pwa-ledger-follow-state",
            "data-pwa-ledger-follow-hint",
            "renderLedgerUnavailable(",
            "Continuity snapshot",
            "Enable updates",
            "Open setup help",
        ],
    },
}
NAVIGATION_REQUIREMENTS = {
    "open_chummer_dropdown": "site-open-chummer-menu",
    "accessible_options_label": "aria-label=\"Open Chummer options\"",
    "build_button": "href=\"/build\"",
    "play_button": "href=\"/mobile/player\"",
    "button_class": "site-open-chummer-menu__button",
}
COMPONENT_ANATOMY_REQUIREMENTS = {
    "primary_action": ".button-like--primary",
    "secondary_action": ".button-like--secondary",
    "ghost_action": ".button-like--ghost",
    "sticky_shell_chrome": ".site-header__inner",
    "open_chummer_menu": ".site-open-chummer-menu",
    "hero_composition": ".minimal-hero",
    "page_hero": ".minimal-page-hero",
    "download_card": ".downloads-choice-card",
    "status_pill": ".minimal-status-pill",
    "mobile_fact_cards": ".minimal-facts article",
    "participate_frame": ".participate-hosted__frame",
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
    "debug",
    "endpoint",
    "internal",
    "manifest",
    "mock",
    "pipeline",
    "runtime",
    "stub",
    "webhook",
]
VISIBLE_INTERNAL_COPY_PATTERNS = {
    "raw_json_endpoint": re.compile(r"/[A-Za-z0-9][A-Za-z0-9/_-]*\.json\b", flags=re.IGNORECASE),
    "raw_api_endpoint": re.compile(r"/api/v\d+(?:/[A-Za-z0-9_.~-]+)+", flags=re.IGNORECASE),
    "raw_route_label": re.compile(r"\bRoute\s*:", flags=re.IGNORECASE),
    "internal_status_label": re.compile(r"\b(review_required|readiness_review_required|not_required)\b", flags=re.IGNORECASE),
}
ACTIONABLE_ENDPOINT_ATTR_RE = re.compile(
    r"\b(?P<attribute>href|action|formaction)\s*=\s*(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
    flags=re.IGNORECASE | re.DOTALL,
)
ACTIONABLE_ENDPOINT_VALUE_PATTERNS = {
    "json_action": re.compile(r"/[A-Za-z0-9][A-Za-z0-9/_~.-]*\.json(?:[?#][^\"'\s<>]*)?$", flags=re.IGNORECASE),
    "api_action": re.compile(r"^/api/v\d+(?:/[A-Za-z0-9_.~-]+)+", flags=re.IGNORECASE),
}
ACTIONABLE_ENDPOINT_JS_PATTERNS = {
    "json_set_action_link": re.compile(r"setActionLink\([^;]*\.json(?:[?#][^\"'\s<>]*)?[^;]*\)", flags=re.IGNORECASE | re.DOTALL),
    "api_set_action_link": re.compile(r"setActionLink\([^;]*/api/v\d+(?:/[A-Za-z0-9_.~-]+)+[^;]*\)", flags=re.IGNORECASE | re.DOTALL),
}
PREMIUM_SURFACE_REQUIREMENTS = {
    "primary_action_touch_floor": {
        "selector": ".surface-minimal .button-like",
        "standard": "Apple HIG touch comfort translated into a 44px minimum action floor",
        "required": {"min_height_at_least": 44},
    },
    "open_chummer_touch_floor": {
        "selector": ".surface-minimal .site-open-chummer-menu .site-account-menu__summary",
        "standard": "Open Chummer must remain touch-safe and visually equivalent to sibling actions",
        "required": {"min_height_at_least": 44},
    },
    "account_menu_item_touch_floor": {
        "selector": ".site-account-menu__link",
        "standard": "Menu rows must be finger-readable, not desktop-only micro rows",
        "required": {"min_height_at_least": 44},
    },
    "landing_hero_depth": {
        "selector": ".minimal-hero",
        "standard": "Landing hero needs a composed premium surface, not a flat text block",
        "required": {
            "background": True,
            "non_flat_background": True,
            "depth": True,
            "radius": True,
            "padding": True,
        },
    },
    "page_hero_depth": {
        "selector": ".minimal-page-hero",
        "standard": "Secondary route heroes need a consistent premium panel treatment",
        "required": {
            "background": True,
            "non_flat_background": True,
            "depth": True,
            "radius": True,
            "padding": True,
        },
    },
    "download_card_depth": {
        "selector": ".downloads-choice-card",
        "standard": "Download decisions must read as deliberate cards, not table rows",
        "required": {
            "background": True,
            "non_flat_background": True,
            "depth": True,
            "radius": True,
            "padding": True,
        },
    },
    "status_panel_depth": {
        "selector": ".minimal-status-pill",
        "standard": "Current status must feel like a high-signal decision panel",
        "required": {
            "background": True,
            "non_flat_background": True,
            "depth": True,
            "radius": True,
            "padding": True,
        },
    },
    "mobile_fact_card_depth": {
        "selector": ".minimal-facts article",
        "standard": "Mobile playtime cards need visible separation under table pressure",
        "required": {
            "background": True,
            "non_flat_background": True,
            "depth": True,
            "radius": True,
            "padding": True,
        },
    },
    "participate_iframe_deference": {
        "selector": ".participate-hosted__frame-shell",
        "standard": "Participate must honor the iframe-only product decision while keeping safe containment",
        "required": {
            "background": True,
            "overflow": True,
            "height": True,
            "no_border": True,
        },
    },
}


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


def css_rule_bodies(css: str, selector_fragment: str) -> list[str]:
    bodies: list[str] = []
    for match in re.finditer(r"(?s)([^{}]+)\{([^{}]*)\}", css):
        selector = match.group(1).strip()
        if selector_fragment in selector:
            bodies.append(match.group(2))
    return bodies


def combined_rule_body(css: str, selector_fragment: str) -> str:
    return "\n".join(css_rule_bodies(css, selector_fragment))


def has_declaration(body: str, property_name: str) -> bool:
    return re.search(rf"\b{re.escape(property_name)}\s*:", body, flags=re.IGNORECASE) is not None


def declaration_values(body: str, property_name: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(rf"\b{re.escape(property_name)}\s*:\s*([^;]+);", body, flags=re.IGNORECASE)
    ]


def max_px_for_declaration(body: str, property_name: str) -> float:
    values = declaration_values(body, property_name)
    numbers: list[float] = []
    for value in values:
        numbers.extend(parse_px_numbers(value))
    return max(numbers) if numbers else 0


def has_non_flat_background(body: str) -> bool:
    values = declaration_values(body, "background") + declaration_values(body, "background-color")
    if not values:
        return False
    for value in values:
        normalized = value.strip().lower()
        if normalized in {"transparent", "none"}:
            continue
        if "transparent" in normalized and not any(token in normalized for token in ("gradient(", "color-mix(", "rgba(", "var(", "#")):
            continue
        return True
    return False


def has_depth(body: str) -> bool:
    values = declaration_values(body, "box-shadow")
    return any(value.strip().lower() != "none" for value in values)


def strip_razor_code_blocks(text: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(text):
        start = text.find("@{", index)
        if start < 0:
            output.append(text[index:])
            break

        output.append(text[index:start])
        cursor = start + 1
        depth = 0
        while cursor < len(text):
            char = text[cursor]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    cursor += 1
                    break
            cursor += 1
        index = cursor
    return "".join(output)


def strip_balanced_inline(text: str, marker: str, open_char: str, close_char: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(text):
        start = text.find(marker, index)
        if start < 0:
            output.append(text[index:])
            break

        output.append(text[index:start])
        cursor = start + len(marker)
        depth = 1
        while cursor < len(text):
            char = text[cursor]
            if char == open_char:
                depth += 1
            elif char == close_char:
                depth -= 1
                if depth == 0:
                    cursor += 1
                    break
            cursor += 1
        index = cursor
    return "".join(output)


def strip_razor_surface_noise(text: str) -> str:
    without_blocks = strip_razor_code_blocks(text)
    without_directives = re.sub(
        r"(?im)^\s*@(model|inject|using|namespace|addTagHelper|removeTagHelper|inherits)\b[^\n]*",
        " ",
        without_blocks,
    )
    without_control = re.sub(
        r"(?im)^\s*@(if|else|foreach|for|while|switch|case|default|try|catch|finally|functions|section)\b[^\n{]*(?:\{)?\s*$",
        " ",
        without_directives,
    )
    without_inline_groups = strip_balanced_inline(without_control, "@(", "(", ")")
    without_inline_calls = re.sub(r"@[A-Za-z_][A-Za-z0-9_.]*\([^)]*\)", " ", without_inline_groups)
    without_inline_names = re.sub(r"@[A-Za-z_][A-Za-z0-9_.]*(?:\[[^\]]+\])?", " ", without_inline_calls)
    return re.sub(r"(?m)^\s*[{}]\s*$", " ", without_inline_names)


def visible_copy(text: str) -> str:
    without_razor = strip_razor_surface_noise(text)
    without_scripts = re.sub(r"(?is)<script\b.*?</script>", " ", without_razor)
    without_styles = re.sub(r"(?is)<style\b.*?</style>", " ", without_scripts)
    without_tags = re.sub(r"(?is)<[^>]+>", " ", without_styles)
    return re.sub(r"\s+", " ", without_tags).strip()


def line_number_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def actionable_endpoint_findings(path: Path) -> list[dict[str, Any]]:
    text = read_text(path)
    findings: list[dict[str, Any]] = []

    for match in ACTIONABLE_ENDPOINT_ATTR_RE.finditer(text):
        value = match.group("value").strip()
        for pattern_name, pattern in ACTIONABLE_ENDPOINT_VALUE_PATTERNS.items():
            if pattern.search(value):
                findings.append(
                    {
                        "route": path.name,
                        "kind": pattern_name,
                        "attribute": match.group("attribute").lower(),
                        "value": value,
                        "line": line_number_for_offset(text, match.start()),
                    }
                )

    for pattern_name, pattern in ACTIONABLE_ENDPOINT_JS_PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append(
                {
                    "route": path.name,
                    "kind": pattern_name,
                    "attribute": "setActionLink",
                    "value": re.sub(r"\s+", " ", match.group(0)).strip(),
                    "line": line_number_for_offset(text, match.start()),
                }
            )

    return findings


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


def state_recovery_result(path: Path) -> dict[str, Any]:
    requirement = STATE_AND_RECOVERY_REQUIREMENTS.get(path.name)
    if requirement is None:
        return {
            "route": path.name,
            "job": "No state/recovery contract is required for this route.",
            "required_markers": [],
            "missing_markers": [],
            "pass": True,
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


def screenshot_qa_result(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    homepage_results = payload.get("homepage_results") if isinstance(payload.get("homepage_results"), list) else []
    surface_results = payload.get("surface_results") if isinstance(payload.get("surface_results"), list) else []

    homepage_by_viewport = {
        str(item.get("viewport")): item
        for item in homepage_results
        if isinstance(item, dict)
    }
    missing_home_viewports = sorted(REQUIRED_SCREENSHOT_HOME_VIEWPORTS - set(homepage_by_viewport))
    homepage_failures = [
        str(item.get("viewport") or "unknown")
        for item in homepage_results
        if isinstance(item, dict)
        and (
            str(item.get("status") or "").lower() != "pass"
            or int(item.get("overflow_px") or 0) != 0
            or item.get("hero_visible") is not True
            or item.get("cta_visible") is not True
            or item.get("hero_first_viewport_fit") is not True
        )
    ]

    surface_coverage: dict[str, set[str]] = {}
    surface_failures: list[str] = []
    for item in surface_results:
        if not isinstance(item, dict):
            continue
        surface = str(item.get("surface") or "")
        viewport = str(item.get("viewport") or "")
        if surface:
            surface_coverage.setdefault(surface, set()).add(viewport)
        if (
            surface in REQUIRED_SCREENSHOT_SURFACES
            and (
                str(item.get("status") or "").lower() != "pass"
                or int(item.get("overflow_px") or 0) != 0
            )
        ):
            surface_failures.append(f"{surface}:{viewport or 'unknown'}")

    missing_surfaces = sorted(REQUIRED_SCREENSHOT_SURFACES - set(surface_coverage))
    incomplete_surface_viewports = {
        surface: sorted(REQUIRED_SCREENSHOT_SURFACE_VIEWPORTS - viewports)
        for surface, viewports in sorted(surface_coverage.items())
        if surface in REQUIRED_SCREENSHOT_SURFACES
        and REQUIRED_SCREENSHOT_SURFACE_VIEWPORTS - viewports
    }
    passes = (
        status_pass(payload)
        and not missing_home_viewports
        and not homepage_failures
        and not missing_surfaces
        and not incomplete_surface_viewports
        and not surface_failures
    )

    return {
        "path": str(path),
        "status": payload.get("status", "missing"),
        "base_url": payload.get("base_url"),
        "required_home_viewports": sorted(REQUIRED_SCREENSHOT_HOME_VIEWPORTS),
        "missing_home_viewports": missing_home_viewports,
        "homepage_failures": homepage_failures,
        "required_surface_viewports": sorted(REQUIRED_SCREENSHOT_SURFACE_VIEWPORTS),
        "required_surfaces": sorted(REQUIRED_SCREENSHOT_SURFACES),
        "missing_surfaces": missing_surfaces,
        "incomplete_surface_viewports": incomplete_surface_viewports,
        "surface_failures": surface_failures,
        "pass": passes,
    }


def marker_presence(markers: list[str], text: str) -> dict[str, bool]:
    normalized = text.lower()
    return {marker: marker.lower() in normalized for marker in markers}


def premium_surface_result(css: str, name: str, config: dict[str, Any]) -> dict[str, Any]:
    selector = str(config["selector"])
    body = combined_rule_body(css, selector)
    required = config.get("required") if isinstance(config.get("required"), dict) else {}
    checks: dict[str, bool] = {}

    if required.get("min_height_at_least") is not None:
        minimum = float(required["min_height_at_least"])
        checks[f"min_height_at_least_{int(minimum)}"] = max_px_for_declaration(body, "min-height") >= minimum
    if required.get("background"):
        checks["has_background"] = has_declaration(body, "background") or has_declaration(body, "background-color")
    if required.get("non_flat_background"):
        checks["has_non_flat_background"] = has_non_flat_background(body)
    if required.get("depth"):
        checks["has_depth"] = has_depth(body)
    if required.get("radius"):
        checks["has_radius"] = has_declaration(body, "border-radius")
    if required.get("padding"):
        checks["has_padding"] = has_declaration(body, "padding")
    if required.get("overflow"):
        checks["has_overflow"] = has_declaration(body, "overflow")
    if required.get("height"):
        checks["has_height"] = has_declaration(body, "height") or has_declaration(body, "min-height")
    if required.get("no_border"):
        checks["has_no_border"] = any(value.strip().lower() == "0" for value in declaration_values(body, "border"))

    return {
        "selector": selector,
        "standard": config["standard"],
        "checks": checks,
        "pass": bool(body.strip()) and all(checks.values()),
    }


def build_payload(
    *,
    css_path: Path = CSS_PATH,
    design_contract_path: Path = DESIGN_CONTRACT_PATH,
    completion_root: Path = COMPLETION_ROOT,
    published_root: Path = PUBLISHED_ROOT,
    critical_public_views: list[Path] = CRITICAL_PUBLIC_VIEWS,
    layout_view: Path = LAYOUT_VIEW,
) -> dict[str, Any]:
    failures: list[str] = []
    checks: dict[str, Any] = {}
    css = read_text(css_path)
    tokens = extract_css_tokens(css)

    design_contract = read_text(design_contract_path)
    design_contract_markers = marker_presence(DESIGN_CONTRACT_MARKERS, design_contract)
    design_contract_pass = bool(design_contract.strip()) and all(design_contract_markers.values())
    if not design_contract_pass:
        failures.append("premium design contract is incomplete; source-standard calibration, scorecard, mobile, forms, and language rules must be written")
    checks["source_design_contract"] = {
        "standard": "written exit gate calibrated against named public design systems",
        "path": str(design_contract_path),
        "markers": design_contract_markers,
        "pass": design_contract_pass,
    }

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

    component_markers = {
        name: marker in css
        for name, marker in COMPONENT_ANATOMY_REQUIREMENTS.items()
    }
    component_pass = all(component_markers.values())
    if not component_pass:
        failures.append("premium component anatomy is incomplete; shared actions, chrome, hero, cards, mobile facts, and iframe surfaces must all be styled")
    checks["component_anatomy"] = {
        "standard": "Fluent/Carbon component consistency + HIG direct manipulation",
        "markers": component_markers,
        "pass": component_pass,
    }

    premium_surface_results = {
        name: premium_surface_result(css, name, config)
        for name, config in PREMIUM_SURFACE_REQUIREMENTS.items()
    }
    premium_surface_pass = all(result["pass"] for result in premium_surface_results.values())
    if not premium_surface_pass:
        failures.append("premium surface anatomy is not strong enough; touch targets, hero depth, route cards, status panels, mobile cards, and iframe containment must all meet the exit bar")
    checks["premium_surface_anatomy"] = {
        "standard": "HIG touch comfort + Fluent depth + Material/Carbon component structure, verified on actual shared selectors",
        "surfaces": premium_surface_results,
        "pass": premium_surface_pass,
    }

    navigation_text = read_text(layout_view) + "\n" + read_text(ROOT / "Chummer.Run.Api/Views/PublicLanding/Landing.cshtml")
    navigation_markers = {
        name: marker in navigation_text
        for name, marker in NAVIGATION_REQUIREMENTS.items()
    }
    navigation_pass = all(navigation_markers.values())
    if not navigation_pass:
        failures.append("premium navigation contract is broken; Open Chummer must be an accessible Build and Play dropdown")
    checks["open_chummer_navigation"] = {
        "standard": "Nielsen recognition over recall + GOV.UK explicit next action",
        "layout_view": str(layout_view),
        "markers": navigation_markers,
        "pass": navigation_pass,
    }

    raw_view_text = "\n".join(read_text(path) for path in critical_public_views)
    view_text = visible_copy(raw_view_text)
    leaked_terms = sorted({needle for needle in INTERNAL_LANGUAGE_NEEDLES if re.search(rf"\b{re.escape(needle)}\b", view_text, flags=re.IGNORECASE)})
    leaked_terms.extend(
        sorted(
            name
            for name, pattern in VISIBLE_INTERNAL_COPY_PATTERNS.items()
            if pattern.search(view_text)
        )
    )
    public_copy_gate = load_json(published_root / "PUBLIC_COPY_LEAK_GATE.generated.json")
    copy_pass = not leaked_terms and status_pass(public_copy_gate)
    if not copy_pass:
        failures.append("premium public copy is not quiet enough; internal terms, raw endpoints, or provider-facing language remain visible")
    checks["public_copy_quiet"] = {
        "standard": "HIG clarity and Carbon production copy consistency",
        "view_count": len(critical_public_views),
        "leaked_terms": leaked_terms,
        "public_copy_leak_gate_status": public_copy_gate.get("status", "missing"),
        "pass": copy_pass,
    }

    actionable_endpoint_results = [
        finding
        for path in critical_public_views
        for finding in actionable_endpoint_findings(path)
    ]
    actionable_endpoint_pass = not actionable_endpoint_results
    if not actionable_endpoint_pass:
        failures.append("premium public actions expose raw endpoints; links and forms must route to product pages, not JSON or API URLs")
    checks["public_action_endpoint_language"] = {
        "standard": "GOV.UK plain service journeys + HIG clarity: public actions point at product pages, not data endpoints",
        "view_count": len(critical_public_views),
        "findings": actionable_endpoint_results,
        "pass": actionable_endpoint_pass,
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

    state_results = [state_recovery_result(path) for path in critical_public_views]
    state_recovery_pass = all(result["pass"] for result in state_results)
    if not state_recovery_pass:
        failures.append("state and recovery language is incomplete; loading, empty, unavailable, and fallback states must tell users what happens next")
    checks["state_and_recovery_language"] = {
        "standard": "Nielsen status visibility + Polaris empty/loading/error state clarity + GOV.UK recovery action clarity",
        "route_count": len(state_results),
        "routes": state_results,
        "pass": state_recovery_pass,
    }

    screenshot_qa = screenshot_qa_result(completion_root / SCREENSHOT_QA_PATH_NAME)
    if not screenshot_qa["pass"]:
        failures.append("premium visual evidence is missing or failing; screenshot QA must cover home and supporting surfaces across mobile and desktop")
    checks["visual_evidence_receipt"] = {
        "standard": "visual claims require viewport evidence, not just source heuristics",
        **screenshot_qa,
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
        "design_contract_path": str(design_contract_path),
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
        "## Source Design Contract",
        "",
        f"- Path: `{payload['design_contract_path']}`",
        f"- Status: `{'pass' if payload['checks']['source_design_contract'].get('pass') else 'fail'}`",
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
