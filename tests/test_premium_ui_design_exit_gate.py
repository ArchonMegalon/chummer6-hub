from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_premium_ui_design_exit_gate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_premium_ui_design_exit_gate", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_supporting_artifacts(completion: Path, published: Path) -> None:
    completion.mkdir(parents=True, exist_ok=True)
    published.mkdir(parents=True, exist_ok=True)
    (completion / "UI_FRAME_INTEGRITY.generated.json").write_text(
        json.dumps({"status": "pass", "summary": {"failure_count": 0}}),
        encoding="utf-8",
    )
    (completion / "CONTRAST_AUDIT.generated.json").write_text(json.dumps({"status": "pass"}), encoding="utf-8")
    (completion / "MINIMAL_EXPERIENCE_GATE.generated.json").write_text(
        json.dumps({"status": "pass", "failures": []}),
        encoding="utf-8",
    )
    (completion / "NOISE_BUDGET_REPORT.md").write_text("- Status: pass\n", encoding="utf-8")
    (published / "PUBLIC_COPY_LEAK_GATE.generated.json").write_text(
        json.dumps({"status": "pass", "failures": []}),
        encoding="utf-8",
    )
    (completion / "SCREENSHOT_QA.generated.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "base_url": "http://127.0.0.1:8091",
                "homepage_results": [
                    {
                        "viewport": viewport,
                        "overflow_px": 0,
                        "hero_visible": True,
                        "cta_visible": True,
                        "hero_first_viewport_fit": True,
                        "status": "pass",
                    }
                    for viewport in ["390x844", "412x915", "768x1024", "1366x768", "1440x900", "1920x1080"]
                ],
                "surface_results": [
                    {
                        "surface": surface,
                        "viewport": viewport,
                        "overflow_px": 0,
                        "status": "pass",
                    }
                    for surface in ["downloads", "status", "ledger-map", "help", "contact"]
                    for viewport in ["390x844", "1366x768"]
                ],
            }
        ),
        encoding="utf-8",
    )


def write_design_contract(path: Path) -> None:
    path.write_text(
        """
# Premium UI Design Exit Gate

Apple Human Interface Guidelines
Material Design 3
Microsoft Fluent 2
IBM Carbon Design System
Atlassian Design System
Shopify Polaris
GOV.UK Service Manual
WCAG 2.2
Nielsen Norman Group usability heuristics
five-second verdict
one-route-one-job
premium visual scorecard
zero-internal-language rule
mobile playtime standard
dark-mode form controls
44px action floor
route visual anatomy
public endpoint language ban
visual evidence receipt
state and recovery language
""",
        encoding="utf-8",
    )


def write_layout(path: Path) -> None:
    path.write_text(
        """
<details class="site-account-menu site-open-chummer-menu">
  <summary class="site-account-menu__summary">
    <span class="site-account-menu__label">Open Chummer</span>
  </summary>
  <div class="site-account-menu__panel" aria-label="Open Chummer options">
    <a class="site-account-menu__link site-open-chummer-menu__button" href="/build">Build</a>
    <a class="site-account-menu__link site-open-chummer-menu__button" href="/play">Play</a>
  </div>
</details>
""",
        encoding="utf-8",
    )


def write_public_views(root: Path, *, leaked: bool = False) -> list[Path]:
    views = []
    templates = {
        "Landing.cshtml": """
<section class="minimal-hero">
  <h1>Chummer</h1>
  <a class="button-like button-like--primary" href="/downloads">Download Chummer</a>
  <details class="site-account-menu site-open-chummer-menu">
    <summary class="site-account-menu__summary">
      <span class="site-account-menu__label">Open Chummer</span>
    </summary>
    <div class="site-account-menu__panel" aria-label="Open Chummer options">
      <a class="site-account-menu__link site-open-chummer-menu__button" href="/build">Build</a>
      <a class="site-account-menu__link site-open-chummer-menu__button" href="/play">Play</a>
    </div>
  </details>
  <a class="minimal-hero__visual minimal-hero__visual--screenshot" href="/media/promo/every-wonder-horizon-promo.mp4">Watch</a>
</section>
""",
        "Downloads.cshtml": """
<section>
  <h1>Downloads</h1>
  <p>Current note: Use Help if setup blocks your table.</p>
  <p>Sign in later only if you want to attach this installed copy</p>
  <section class="minimal-empty"><h2>No build is available right now</h2><a href="/help">Help</a></section>
  <div class="downloads-choice-list">
    <article class="downloads-choice-card"><h2>Stable</h2><a href="/help" data-release-lane="stable">Help</a></article>
    <article class="downloads-choice-card"><h2>Nightly</h2><a href="/nightly" data-release-lane="nightly">Nightly</a></article>
  </div>
</section>
""",
        "Status.cshtml": """
<section class="minimal-status-pill">
  <h1>Updated</h1>
  <p>Current caution</p>
  <div aria-label="Status next actions">
    <a href="/downloads">Downloads</a>
    <a href="/help">Help</a>
  </div>
</section>
""",
        "Partizipate.cshtml": """
<section>
  <h1 class="sr-only">Participate</h1>
  <div class="participate-hosted__frame-shell">
    <iframe class="participate-hosted__frame" src="@Model.EmbeddedBoardHref" title="Chummer participation board" loading="lazy" referrerpolicy="same-origin" data-chummer-participate-frame></iframe>
  </div>
  <article class="participate-board-fallback" role="status" aria-live="polite">Board offline right now. <a href="/participate">Retry</a> <a href="/contact">Contact</a></article>
</section>
""",
        "MobileProjection.cshtml": """
<section id="pwa-ledger-stream">
  <h1>Mobile</h1>
  <button data-install-prompt-button>Install this app</button>
  <p data-pwa-install-state>Installable app shell live</p>
  <p data-pwa-ledger-status>Checking</p>
  <p data-pwa-ledger-summary>Waiting for live board stream data.</p>
  <meter data-pwa-ledger-heat-meter></meter>
  <button data-pwa-ledger-follow-button></button>
  <p data-pwa-ledger-follow-state>Sign in to opt in and follow a living world.</p>
  <p data-pwa-ledger-follow-hint></p>
  <p data-pwa-continuity-summary>No continuity snapshot loaded yet.</p>
  <p>Continuity snapshot is not available in this lane.</p>
  <a href="/account">Enable updates</a>
  <a href="/help">Open setup help</a>
  <a href="/play/continuity">Open continuity</a>
  <a href="/help">Help</a>
  <script>function renderLedgerUnavailable() {}</script>
</section>
""",
    }
    for name, template in templates.items():
        path = root / name
        path.write_text(
            template
            + ("<p>operator proof provider</p>" if leaked else ""),
            encoding="utf-8",
        )
        views.append(path)
    return views


def premium_css() -> str:
    spacing = "\n".join(f"  --space-{index}: {index * 4}px;" for index in range(1, 7))
    return f"""
:root {{
  --color-background-canvas: #081018;
  --color-background-panel: #111b27;
  --color-border-subtle: #273545;
  --color-text-primary: #f7f3eb;
  --color-text-muted: #aeb8c4;
  --color-accent-primary: #f3d28a;
  --color-accent-secondary: #68d2ff;
  --color-accent-danger: #d14b38;
  --bg-canvas: var(--color-background-canvas);
  --bg-surface: var(--color-background-panel);
  --surface-quiet: #172232;
  --surface-muted: #243247;
  --surface-strong: #f7f3eb;
  --ink-strong: var(--color-text-primary);
  --ink-muted: var(--color-text-muted);
  --line-subtle: var(--color-border-subtle);
  --accent-cyan: var(--color-accent-secondary);
  --accent-amber: var(--color-accent-primary);
  --link-strong: #ffffff;
  --font-family-display: "Array Serif", "Fraunces", serif;
  --font-family-base: "Satoshi", "Aptos", sans-serif;
  --shadow-soft: 0 18px 42px rgba(0, 0, 0, 0.18);
  --shadow-hero: 0 36px 86px rgba(0, 0, 0, 0.32);
  --radius-sm: 8px;
  --radius-md: 16px;
  --radius-lg: 28px;
{spacing}
  --site-max: 1240px;
  color-scheme: dark;
}}
.site-header__inner {{ display: grid; grid-template-columns: minmax(9rem, auto) minmax(0, 1fr) auto; backdrop-filter: blur(12px); }}
.button-like,
.surface-minimal .button-like,
.site-account-menu__summary,
.site-account-menu__link,
.editorial-strip__action {{ min-height: 44px; }}
.button-like--primary {{ display: inline-flex; }}
.button-like--secondary {{ display: inline-flex; }}
.button-like--ghost {{ display: inline-flex; }}
.site-open-chummer-menu {{ display: inline-grid; }}
.surface-minimal .site-open-chummer-menu .site-account-menu__summary {{ min-height: 44px; }}
.minimal-hero {{ display: grid; padding: 24px; border-radius: 24px; background: linear-gradient(#111, #000); box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28); }}
.minimal-hero__visual {{ display: grid; background: linear-gradient(#000, #111); }}
.minimal-page-hero {{ display: grid; padding: 24px; border-radius: 20px; background: linear-gradient(#111, #000); box-shadow: 0 22px 52px rgba(0, 0, 0, 0.24); }}
.landing-film {{ display: grid; background: radial-gradient(circle, #111, #000); min-height: 100svh; }}
.editorial-strip {{ display: grid; }}
.downloads-quicknav {{ display: flex; }}
.downloads-choice-card {{ display: grid; padding: 20px; border-radius: 18px; background: linear-gradient(#111, #000); box-shadow: 0 20px 50px rgba(0, 0, 0, 0.22); }}
.minimal-status-pill {{ display: grid; padding: 18px; border-radius: 18px; background: linear-gradient(#111, #000); box-shadow: 0 18px 44px rgba(0, 0, 0, 0.2); }}
.minimal-facts article {{ display: grid; padding: 18px; border-radius: 18px; background: linear-gradient(#111, #000); box-shadow: 0 18px 44px rgba(0, 0, 0, 0.2); }}
.participate-hosted__frame-shell {{ height: 80svh; overflow: hidden; border: 0; background: var(--bg-canvas); }}
.participate-hosted__frame {{ display: block; }}
.black-ledger-geoscape {{ display: grid; }}
.grid-a {{ display: grid; }}
.grid-b {{ display: grid; }}
.grid-c {{ display: grid; }}
.grid-d {{ display: grid; }}
.grid-e {{ display: grid; }}
.grid-f {{ display: grid; }}
.grid-g {{ display: grid; }}
.grid-h {{ display: grid; }}
.grid-i {{ display: grid; }}
.grid-j {{ display: grid; }}
.grid-k {{ display: grid; }}
.grid-l {{ display: grid; }}
.grid-m {{ display: grid; }}
.grid-n {{ display: grid; }}
.grid-o {{ display: grid; }}
.grid-p {{ display: grid; }}
.grid-q {{ display: grid; }}
.grid-r {{ display: grid; }}
.grid-s {{ display: grid; }}
.grid-t {{ display: grid; }}
.flex-a {{ display: flex; }}
.flex-b {{ display: flex; }}
.flex-c {{ display: flex; }}
.flex-d {{ display: flex; }}
.flex-e {{ display: flex; }}
.flex-f {{ display: flex; }}
.flex-g {{ display: flex; }}
.flex-h {{ display: flex; }}
.flex-i {{ display: flex; }}
.flex-j {{ display: flex; }}
input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]),
select,
textarea {{ background: var(--bg-surface); color: var(--ink-strong); color-scheme: dark; caret-color: var(--ink-strong); accent-color: var(--accent-cyan); }}
input::placeholder,
textarea::placeholder {{ color: var(--ink-muted); }}
select option,
select optgroup {{ background: var(--bg-surface); color: var(--ink-strong); }}
select option:checked {{ background: var(--ink-strong); color: var(--bg-canvas); }}
.field input:focus,
.field select:focus,
.field textarea:focus {{ outline: 2px solid rgba(104, 210, 255, 0.36); outline-offset: 2px; }}
@keyframes premium-rise {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
@media (prefers-reduced-motion: reduce) {{ * {{ animation: none; transition: none; }} }}
@media (max-width: 1200px) {{ .site-header__inner {{ grid-template-columns: minmax(0, 1fr); }} }}
@media (max-width: 1024px) {{ .minimal-hero__visual {{ min-height: clamp(24rem, 72svh, 42rem); }} }}
@media (max-width: 980px) {{ .landing-film {{ min-height: 82svh; }} }}
@media (max-width: 860px) {{ .downloads-quicknav {{ flex-wrap: wrap; }} }}
@media (max-width: 720px) {{ .site-header__inner {{ grid-template-columns: minmax(0, 1fr); }} }}
@media (max-width: 520px) {{ .minimal-hero__visual {{ min-height: 48px; }} }}
.hero {{ transition: transform 180ms ease; }}
.touch-a {{ min-height: 44px; }}
.touch-b {{ min-height: 48px; }}
.touch-c {{ min-height: 52px; }}
.touch-d {{ min-height: 60px; }}
{chr(10).join(f".hover{index}:hover {{ transform: translateY(-1px); }}" for index in range(20))}
{chr(10).join(f".focus{index}:focus-visible {{ outline: 2px solid rgba(104, 210, 255, 0.36); }}" for index in range(18))}
{chr(10).join(f".g{index} {{ background: linear-gradient(#000, #111); }}" for index in range(20))}
"""


def test_premium_gate_passes_for_tokenized_premium_shell() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="premium-ui-gate-") as temp_dir:
        root = Path(temp_dir)
        completion = root / "completion"
        published = root / "published"
        css = root / "site.css"
        design_contract = root / "PREMIUM_UI_DESIGN_EXIT_GATE.md"
        layout = root / "_Layout.cshtml"
        views = write_public_views(root)
        write_design_contract(design_contract)
        write_layout(layout)
        write_supporting_artifacts(completion, published)
        css.write_text(premium_css(), encoding="utf-8")

        payload = module.build_payload(
            css_path=css,
            design_contract_path=design_contract,
            completion_root=completion,
            published_root=published,
            critical_public_views=views,
            layout_view=layout,
        )

    assert payload["status"] == "pass", payload["failures"]
    assert payload["verdict"] == "PREMIUM_UI_READY"
    assert len(payload["reference_systems"]) >= 8
    assert len(payload["design_principles"]) >= 6
    assert payload["design_principles"][0]["id"] == "five_second_first_impression"
    assert payload["checks"]["premium_typography"]["pass"]
    assert payload["checks"]["premium_elevation"]["pass"]
    assert payload["checks"]["spatial_system"]["pass"]
    assert payload["checks"]["premium_palette"]["pass"]
    assert payload["checks"]["interaction_affordance"]["pass"]
    assert payload["checks"]["responsive_layout"]["pass"]
    assert payload["checks"]["form_control_legibility"]["pass"]
    assert payload["checks"]["composition_hierarchy"]["pass"]
    assert payload["checks"]["source_design_contract"]["pass"]
    assert payload["checks"]["component_anatomy"]["pass"]
    assert payload["checks"]["premium_surface_anatomy"]["pass"]
    assert payload["checks"]["open_chummer_navigation"]["pass"]
    assert payload["checks"]["route_journey_contracts"]["pass"]
    assert payload["checks"]["state_and_recovery_language"]["pass"]
    assert payload["checks"]["visual_evidence_receipt"]["pass"]


def test_premium_gate_rejects_generic_flat_theme_and_internal_copy() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="premium-ui-gate-fail-") as temp_dir:
        root = Path(temp_dir)
        completion = root / "completion"
        published = root / "published"
        css = root / "site.css"
        design_contract = root / "PREMIUM_UI_DESIGN_EXIT_GATE.md"
        layout = root / "_Layout.cshtml"
        views = write_public_views(root, leaked=True)
        write_design_contract(design_contract)
        write_layout(layout)
        write_supporting_artifacts(completion, published)
        css.write_text(
            """
:root {
  --font-family-display: "Inter", -apple-system, "Segoe UI", sans-serif;
  --font-family-base: "Inter", -apple-system, "Segoe UI", sans-serif;
  --shadow-soft: none;
  --shadow-hero: none;
  --radius-sm: 12px;
  --radius-md: 12px;
  --radius-lg: 16px;
}
.hero { transition: transform 180ms ease; }
@media (prefers-reduced-motion: reduce) { * { transition: none; } }
""",
            encoding="utf-8",
        )

        payload = module.build_payload(
            css_path=css,
            design_contract_path=design_contract,
            completion_root=completion,
            published_root=published,
            critical_public_views=views,
            layout_view=layout,
        )

    assert payload["status"] == "fail"
    assert "premium typography is not distinctive; display/body stacks are generic or identical" in payload["failures"]
    assert "premium elevation is missing; shadow tokens must create distinct soft and hero depth" in payload["failures"]
    assert "premium public copy is not quiet enough; internal terms, raw endpoints, or provider-facing language remain visible" in payload["failures"]
    assert "premium palette is under-specified; require named semantic colors, dark scheme discipline, and enough tonal range" in payload["failures"]
    assert "interaction affordance is too weak; premium UI needs visible focus, hover states, and touch-safe targets" in payload["failures"]
    assert "responsive system is not flagship-grade; require mobile breakpoints, fluid type/spacing, minmax grids, and svh handling" in payload["failures"]
    assert "form controls are not fully dark-mode readable; textboxes, selects, placeholders, options, and focus states must be styled" in payload["failures"]
    assert "composition still reads like a template; require premium chrome, hero/media, editorial, navigation, and dense layout systems" in payload["failures"]
    assert "premium surface anatomy is not strong enough; touch targets, hero depth, route cards, status panels, mobile cards, and iframe containment must all meet the exit bar" in payload["failures"]


def test_premium_gate_rejects_visible_raw_endpoint_copy() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="premium-ui-gate-endpoint-fail-") as temp_dir:
        root = Path(temp_dir)
        completion = root / "completion"
        published = root / "published"
        css = root / "site.css"
        design_contract = root / "PREMIUM_UI_DESIGN_EXIT_GATE.md"
        layout = root / "_Layout.cshtml"
        views = write_public_views(root)
        mobile = root / "MobileProjection.cshtml"
        mobile.write_text(
            mobile.read_text(encoding="utf-8")
            + '<p><span>Route:</span><span>/mobile/pwa/ledger.json</span></p>',
            encoding="utf-8",
        )
        write_design_contract(design_contract)
        write_layout(layout)
        write_supporting_artifacts(completion, published)
        css.write_text(premium_css(), encoding="utf-8")

        payload = module.build_payload(
            css_path=css,
            design_contract_path=design_contract,
            completion_root=completion,
            published_root=published,
            critical_public_views=views,
            layout_view=layout,
        )

    assert payload["status"] == "fail"
    assert "premium public copy is not quiet enough; internal terms, raw endpoints, or provider-facing language remain visible" in payload["failures"]
    assert "raw_json_endpoint" in payload["checks"]["public_copy_quiet"]["leaked_terms"]
    assert "raw_route_label" in payload["checks"]["public_copy_quiet"]["leaked_terms"]


def test_premium_gate_rejects_missing_visual_evidence() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="premium-ui-gate-screenshot-fail-") as temp_dir:
        root = Path(temp_dir)
        completion = root / "completion"
        published = root / "published"
        css = root / "site.css"
        design_contract = root / "PREMIUM_UI_DESIGN_EXIT_GATE.md"
        layout = root / "_Layout.cshtml"
        views = write_public_views(root)
        write_design_contract(design_contract)
        write_layout(layout)
        write_supporting_artifacts(completion, published)
        (completion / "SCREENSHOT_QA.generated.json").write_text(
            json.dumps(
                {
                    "status": "pass",
                    "homepage_results": [
                        {
                            "viewport": "390x844",
                            "overflow_px": 0,
                            "hero_visible": True,
                            "cta_visible": True,
                            "hero_first_viewport_fit": True,
                            "status": "pass",
                        }
                    ],
                    "surface_results": [],
                }
            ),
            encoding="utf-8",
        )
        css.write_text(premium_css(), encoding="utf-8")

        payload = module.build_payload(
            css_path=css,
            design_contract_path=design_contract,
            completion_root=completion,
            published_root=published,
            critical_public_views=views,
            layout_view=layout,
        )

    assert payload["status"] == "fail"
    assert "premium visual evidence is missing or failing; screenshot QA must cover home and supporting surfaces across mobile and desktop" in payload["failures"]
    assert payload["checks"]["visual_evidence_receipt"]["missing_home_viewports"]
    assert payload["checks"]["visual_evidence_receipt"]["missing_surfaces"]


def test_premium_gate_rejects_missing_state_recovery_language() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="premium-ui-gate-state-fail-") as temp_dir:
        root = Path(temp_dir)
        completion = root / "completion"
        published = root / "published"
        css = root / "site.css"
        design_contract = root / "PREMIUM_UI_DESIGN_EXIT_GATE.md"
        layout = root / "_Layout.cshtml"
        views = write_public_views(root)
        partizipate = root / "Partizipate.cshtml"
        partizipate.write_text(
            """
<section>
  <h1 class="sr-only">Participate</h1>
  <div class="participate-hosted__frame-shell">
    <iframe class="participate-hosted__frame" src="@Model.EmbeddedBoardHref" title="Chummer participation board" loading="lazy" referrerpolicy="same-origin" data-chummer-participate-frame></iframe>
  </div>
  <article class="participate-board-fallback">Board offline right now.</article>
</section>
""",
            encoding="utf-8",
        )
        write_design_contract(design_contract)
        write_layout(layout)
        write_supporting_artifacts(completion, published)
        css.write_text(premium_css(), encoding="utf-8")

        payload = module.build_payload(
            css_path=css,
            design_contract_path=design_contract,
            completion_root=completion,
            published_root=published,
            critical_public_views=views,
            layout_view=layout,
        )

    assert payload["status"] == "fail"
    assert "state and recovery language is incomplete; loading, empty, unavailable, and fallback states must tell users what happens next" in payload["failures"]
    partizipate_result = next(
        route for route in payload["checks"]["state_and_recovery_language"]["routes"]
        if route["route"] == "Partizipate.cshtml"
    )
    assert "role=\"status\"" in partizipate_result["missing_markers"]
    assert "aria-live=\"polite\"" in partizipate_result["missing_markers"]


def test_visible_copy_ignores_razor_setup_code_but_keeps_rendered_text() -> None:
    module = load_module()
    source = """
@{
    var releaseNeedsReview = string.Equals(Model.Manifest.RolloutState, "readiness_review_required", StringComparison.OrdinalIgnoreCase);
    var nested = new { Label = "review_required" };
}
<section>
  <p>Current caution</p>
  <p>Route: /mobile/pwa/ledger.json</p>
</section>
"""

    visible = module.visible_copy(source)

    assert "readiness_review_required" not in visible
    assert "review_required" not in visible
    assert "Current caution" in visible
    assert "Route: /mobile/pwa/ledger.json" in visible


def test_visible_copy_strips_razor_model_noise_before_internal_language_scan() -> None:
    module = load_module()
    source = """
@model DownloadsPageViewModel
@{
    var manifest = Model.Manifest;
}
<section>
  <p>Downloads are available.</p>
</section>
"""

    visible = module.visible_copy(source)

    assert "Model.Manifest" not in visible
    assert "manifest" not in visible.lower()
    assert "Downloads are available." in visible


def test_premium_gate_rejects_missing_written_design_contract() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="premium-ui-gate-contract-fail-") as temp_dir:
        root = Path(temp_dir)
        completion = root / "completion"
        published = root / "published"
        css = root / "site.css"
        layout = root / "_Layout.cshtml"
        views = write_public_views(root)
        write_layout(layout)
        write_supporting_artifacts(completion, published)
        css.write_text(premium_css(), encoding="utf-8")

        payload = module.build_payload(
            css_path=css,
            design_contract_path=root / "missing.md",
            completion_root=completion,
            published_root=published,
            critical_public_views=views,
            layout_view=layout,
        )

    assert payload["status"] == "fail"
    assert "premium design contract is incomplete; source-standard calibration, scorecard, mobile, forms, and language rules must be written" in payload["failures"]


def test_design_package_names_the_premium_exit_gate_and_sources() -> None:
    doc = (SCRIPT_PATH.parents[1] / "docs" / "CHUMMER_RUN_FLAGSHIP_REDESIGN_PACKAGE.md").read_text(encoding="utf-8")

    assert "## 5A. Premium UI Design Exit Gate" in doc
    assert "Apple Human Interface Guidelines" in doc
    assert "Material Design 3" in doc
    assert "IBM Carbon Design System" in doc
    assert "WCAG 2.2" in doc
    assert "one visible job, one primary next action" in doc
    assert "not a proof harness, provider adapter, internal roadmap, or operator console" in doc
    assert "premium visual scorecard" in doc
    assert "zero-internal-language" in doc
    assert "44px action floor" in doc
    assert "route visual anatomy" in doc
    assert "visual evidence receipt" in doc
    assert "state and recovery language" in doc
