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


def write_public_views(root: Path, *, leaked: bool = False) -> list[Path]:
    views = []
    for name in ["Landing.cshtml", "Downloads.cshtml", "Status.cshtml", "Partizipate.cshtml", "MobileProjection.cshtml"]:
        path = root / name
        path.write_text(
            "<section><h1>Chummer</h1><a>Downloads</a></section>"
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
.minimal-hero__visual {{ display: grid; background: linear-gradient(#000, #111); }}
.landing-film {{ display: grid; background: radial-gradient(circle, #111, #000); min-height: 100svh; }}
.editorial-strip {{ display: grid; }}
.downloads-quicknav {{ display: flex; }}
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
        views = write_public_views(root)
        write_supporting_artifacts(completion, published)
        css.write_text(premium_css(), encoding="utf-8")

        payload = module.build_payload(
            css_path=css,
            completion_root=completion,
            published_root=published,
            critical_public_views=views,
        )

    assert payload["status"] == "pass", payload["failures"]
    assert payload["verdict"] == "PREMIUM_UI_READY"
    assert len(payload["reference_systems"]) >= 6
    assert payload["checks"]["premium_typography"]["pass"]
    assert payload["checks"]["premium_elevation"]["pass"]
    assert payload["checks"]["spatial_system"]["pass"]
    assert payload["checks"]["premium_palette"]["pass"]
    assert payload["checks"]["interaction_affordance"]["pass"]
    assert payload["checks"]["responsive_layout"]["pass"]
    assert payload["checks"]["form_control_legibility"]["pass"]
    assert payload["checks"]["composition_hierarchy"]["pass"]


def test_premium_gate_rejects_generic_flat_theme_and_internal_copy() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="premium-ui-gate-fail-") as temp_dir:
        root = Path(temp_dir)
        completion = root / "completion"
        published = root / "published"
        css = root / "site.css"
        views = write_public_views(root, leaked=True)
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
            completion_root=completion,
            published_root=published,
            critical_public_views=views,
        )

    assert payload["status"] == "fail"
    assert "premium typography is not distinctive; display/body stacks are generic or identical" in payload["failures"]
    assert "premium elevation is missing; shadow tokens must create distinct soft and hero depth" in payload["failures"]
    assert "premium public copy is not quiet enough; internal or provider-facing terms remain visible" in payload["failures"]
    assert "premium palette is under-specified; require named semantic colors, dark scheme discipline, and enough tonal range" in payload["failures"]
    assert "interaction affordance is too weak; premium UI needs visible focus, hover states, and touch-safe targets" in payload["failures"]
    assert "responsive system is not flagship-grade; require mobile breakpoints, fluid type/spacing, minmax grids, and svh handling" in payload["failures"]
    assert "form controls are not fully dark-mode readable; textboxes, selects, placeholders, options, and focus states must be styled" in payload["failures"]
    assert "composition still reads like a template; require premium chrome, hero/media, editorial, navigation, and dense layout systems" in payload["failures"]
