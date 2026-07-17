from __future__ import annotations

from pathlib import Path


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = RUN_SERVICES_ROOT.parent
RUN_API = RUN_SERVICES_ROOT / "Chummer.Run.Api"
PLAY_WEB = WORKSPACE_ROOT / "chummer-play" / "src" / "Chummer.Play.Web"


RESTRICTIVE_CSP = (
    "default-src 'none'; base-uri 'none'; connect-src 'none'; form-action 'self'; "
    "frame-ancestors 'none'; img-src 'self' data:; manifest-src 'self'; "
    "script-src 'self'; style-src 'self'; worker-src 'self'"
)


def test_mobile_documents_are_private_no_store_and_use_the_same_restrictive_csp() -> None:
    edge = (RUN_API / "Program.cs").read_text(encoding="utf-8")
    play = (PLAY_WEB / "PlayWebApplication.cs").read_text(encoding="utf-8")

    for source in (edge, play):
        assert RESTRICTIVE_CSP in source
        assert '"Referrer-Policy"] = "no-referrer"' in source
        assert '"X-Content-Type-Options"] = "nosniff"' in source
        assert '"X-Frame-Options"] = "DENY"' in source
        assert "private, no-store" in source


def test_edge_mobile_shell_is_local_install_only_and_contains_no_inline_script() -> None:
    view = (RUN_API / "Views" / "PublicLanding" / "MobileProjection.cshtml").read_text(encoding="utf-8")
    layout = (RUN_API / "Views" / "Shared" / "_MobileInstallLayout.cshtml").read_text(encoding="utf-8")

    assert 'data-play-surface="install-only"' in view
    assert 'data-live-session="unavailable"' in view
    assert 'data-authority="none"' in view
    assert 'src="/mobile-install-shell.js"' in layout
    assert 'href="/mobile.css"' in layout
    assert "<script>" not in view
    assert "<script>" not in layout
    assert "http://" not in view and "https://" not in view
    assert "http://" not in layout and "https://" not in layout


def test_service_workers_have_explicit_mime_nosniff_and_no_cache_headers() -> None:
    edge = (RUN_API / "Program.cs").read_text(encoding="utf-8")
    play = (PLAY_WEB / "PlayWebApplication.cs").read_text(encoding="utf-8")

    assert 'path.Equals("/mobile/service-worker.js"' in edge
    assert '"application/javascript; charset=utf-8"' in edge
    assert '"no-cache, no-store, must-revalidate"' in edge
    assert '"X-Content-Type-Options"] = "nosniff"' in edge
    assert 'context.Request.Path.Equals("/mobile/service-worker.js"' in play
    assert '"application/javascript; charset=utf-8"' in play
    assert '"no-cache, no-store, must-revalidate"' in play
    assert '"X-Content-Type-Options"] = "nosniff"' in play


def test_edge_public_handoff_scripts_share_an_exact_nosniff_javascript_contract() -> None:
    edge = (RUN_API / "Program.cs").read_text(encoding="utf-8")

    assert 'value.Equals("/js/mobile-app-handoff.js", StringComparison.OrdinalIgnoreCase)' in edge
    assert 'value.Equals("/mobile-install-shell.js", StringComparison.OrdinalIgnoreCase)' in edge
    assert 'requestPath.Value?.EndsWith(".js", StringComparison.OrdinalIgnoreCase)' in edge
    assert '"application/javascript; charset=utf-8"' in edge
    assert '"X-Content-Type-Options"] = "nosniff"' in edge


def test_api_ready_is_private_no_store_at_origin_and_cdn_boundaries() -> None:
    edge = (RUN_API / "Program.cs").read_text(encoding="utf-8")
    headers = (RUN_API / "PrivateResponseCacheHeaders.cs").read_text(encoding="utf-8")
    ready_block = edge.split('app.MapMethods("/api/ready"', 1)[1].split(
        'app.MapMethods("/api/ready/play-projection"', 1
    )[0]

    assert "PrivateResponseCacheHeaders.Apply(context.Response.Headers);" in ready_block
    assert 'context.Response.Headers["X-Content-Type-Options"] = "nosniff";' in ready_block
    assert 'headers["Cache-Control"] = "private, no-store, max-age=0";' in headers
    assert 'headers["CDN-Cache-Control"] = "no-store, max-age=0";' in headers
    assert 'headers["Cloudflare-CDN-Cache-Control"] = "no-store, max-age=0";' in headers
    assert 'headers["Surrogate-Control"] = "no-store";' in headers


def test_no_same_origin_remote_active_content_projection_remains() -> None:
    gateway = (RUN_API / "Services" / "PublicPlayProxyGateway.cs").read_text(encoding="utf-8")
    controller = (RUN_API / "Controllers" / "LegacySurfaceRedirectController.cs").read_text(encoding="utf-8")

    assert "Array.Empty<string>()" in gateway
    assert "IHttpClientFactory" not in gateway
    assert "HttpRequestMessage" not in gateway
    assert 'Route("/mobile.css")' not in controller
    assert "mobile-turn-companion.js" not in controller
