from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_participate_iframe_shell.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_participate_iframe_shell", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_source_contract_passes_for_iframe_only_participate_shell() -> None:
    module = load_module()

    result = module.verify_source()

    assert result["status"] == "pass"
    assert result["required"]["view_has_real_iframe"] is True
    assert result["required"]["view_uses_existing_embed_href"] is True
    assert result["required"]["view_removes_visible_header"] is True
    assert result["required"]["public_builder_summary_is_minimal"] is True
    assert result["required"]["legacy_builder_summary_is_minimal"] is True


def test_live_route_accepts_iframe_shell(monkeypatch) -> None:
    module = load_module()

    def fake_fetch(base_url: str, path: str, timeout_seconds: float):
        return (
            200,
            {"content-type": "text/html; charset=utf-8"},
            """
            <main>
              <h1 id="partizipate-title" class="sr-only">Participate</h1>
              <iframe src="/participate/board?embed=1" data-chummer-participate-frame></iframe>
            </main>
            """,
            "https://chummer.run/participate",
        )

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_live_route("https://chummer.run", "/participate", 1)

    assert result["status"] == "pass"
    assert result["has_iframe"] is True
    assert result["has_offline_fallback"] is False


def test_live_route_accepts_existing_offline_fallback(monkeypatch) -> None:
    module = load_module()

    def fake_fetch(base_url: str, path: str, timeout_seconds: float):
        return (
            200,
            {"content-type": "text/html; charset=utf-8"},
            """
            <main>
              <h1 id="partizipate-title" class="sr-only">Participate</h1>
              <article class="participate-board-fallback">Board offline right now</article>
            </main>
            """,
            "https://chummer.run/participate",
        )

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_live_route("https://chummer.run", "/partizipate", 1)

    assert result["status"] == "pass"
    assert result["has_iframe"] is False
    assert result["has_offline_fallback"] is True


def test_live_route_rejects_removed_visible_wrapper(monkeypatch) -> None:
    module = load_module()

    def fake_fetch(base_url: str, path: str, timeout_seconds: float):
        return (
            200,
            {"content-type": "text/html; charset=utf-8"},
            """
            <main>
              <div class="participate-hosted__header">
                <p class="eyebrow">Board</p>
                <h1>Participate</h1>
                <p>Public requests, clear bugs, useful ideas.</p>
              </div>
              <iframe src="/participate/board?embed=1" data-chummer-participate-frame></iframe>
            </main>
            """,
            "https://chummer.run/participate",
        )

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_live_route("https://chummer.run", "/participate", 1)

    assert result["status"] == "fail"
    assert "/participate still renders removed summary" in result["failures"]
    assert "/participate still renders Board eyebrow" in result["failures"]
    assert "/participate still renders participate-hosted header" in result["failures"]


def test_combined_receipt_fails_when_any_live_route_fails(monkeypatch) -> None:
    module = load_module()

    def fake_fetch(base_url: str, path: str, timeout_seconds: float):
        body = '<h1>Participate</h1><iframe data-chummer-participate-frame></iframe>'
        final_url = "https://chummer.run/participate"
        if path == "/partizipate":
            body = '<h1>Participate</h1><p>Public requests, clear bugs, useful ideas.</p>'
        return (200, {"content-type": "text/html; charset=utf-8"}, body, final_url)

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify("https://chummer.run", 1)

    assert result["status"] == "fail"
    assert result["route_count"] == 2
    assert any("still renders removed summary" in failure for failure in result["failures"])
