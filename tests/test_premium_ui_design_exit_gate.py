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
  --font-family-display: "Array Serif", "Fraunces", serif;
  --font-family-base: "Satoshi", "Aptos", sans-serif;
  --shadow-soft: 0 18px 42px rgba(0, 0, 0, 0.18);
  --shadow-hero: 0 36px 86px rgba(0, 0, 0, 0.32);
  --radius-sm: 8px;
  --radius-md: 16px;
  --radius-lg: 28px;
{spacing}
}}
.minimal-hero__visual {{ background: linear-gradient(#000, #111); }}
.landing-film {{ background: radial-gradient(circle, #111, #000); }}
@keyframes premium-rise {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
@media (prefers-reduced-motion: reduce) {{ * {{ animation: none; transition: none; }} }}
.hero {{ transition: transform 180ms ease; }}
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
    assert len(payload["reference_systems"]) == 4
    assert payload["checks"]["premium_typography"]["pass"]
    assert payload["checks"]["premium_elevation"]["pass"]
    assert payload["checks"]["spatial_system"]["pass"]


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
