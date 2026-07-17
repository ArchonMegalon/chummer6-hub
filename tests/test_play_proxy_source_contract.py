from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "Chummer.Run.Api"
PLAY_ROOT = ROOT.parent / "chummer-play" / "src" / "Chummer.Play.Web" / "wwwroot"


def test_program_has_no_public_projection_transport_and_private_routes_are_denied_first() -> None:
    source = (API / "Program.cs").read_text(encoding="utf-8")

    assert "PublicPlaySessionAccessPolicy.RequiresSessionGrant" in source
    assert "IPublicPlayPrivateRouteDelegator" in source
    assert "gateway.TryHandleAsync" not in source
    assert "PublicPlayProjectionGateway" not in source
    assert "ShouldProxyPlayPwaRequest" not in source
    assert "TryProxyPlayPwaRequestAsync" not in source
    assert "BuildPlayPwaProxyTarget" not in source
    assert "CHUMMER_PUBLIC_PLAY_PROXY_API_KEY" not in source


def test_controllers_cannot_construct_a_second_play_upstream() -> None:
    legacy = (API / "Controllers" / "LegacySurfaceRedirectController.cs").read_text(encoding="utf-8")
    landing = (API / "Controllers" / "PublicLandingController.cs").read_text(encoding="utf-8")

    assert "_playUpstream" not in legacy
    assert "PlayIcons" not in legacy
    assert "TryProxyPublicPlayPwaAsync" not in landing
    assert "ResolvePublicPlayProxyUri" not in landing
    assert "_privatePlayRoutes.DenyAsync" in legacy
    assert "PublicPlayProxyGateway" not in legacy
    assert "mobile-turn-companion.js" not in legacy
    assert 'Route("/mobile.css")' not in legacy


def test_gateway_is_readiness_only_and_has_zero_remote_content_routes() -> None:
    source = (API / "Services" / "PublicPlayProxyGateway.cs").read_text(encoding="utf-8")

    assert "Array.Empty<string>()" in source
    assert "PublicPlayProxyDisposition.NotMatched" in source
    assert "IHttpClientFactory" not in source
    assert "HttpRequestMessage" not in source
    assert "HandleRequiredAsync" not in source
    assert "projection_retired_local_mirror_only" in source
    network_policy = (API / "Services" / "PublicPlayUpstreamNetworkPolicy.cs").read_text(encoding="utf-8")
    assert "Uri.UriSchemeHttps" in network_policy
    assert "AllowedOriginsConfigurationKey" in network_policy
    assert "DormantPublicPlayProjectionConfigurationPolicy" in network_policy
    assert "TryResolveDormantOriginForReadiness" in network_policy
    assert "HasSameOrigin(candidate, publicCanonicalOrigin)" in network_policy


def test_public_edge_defaults_to_local_shell_and_private_play_is_profile_only() -> None:
    compose = (ROOT / "docker-compose.public-edge.yml").read_text(encoding="utf-8")

    assert 'profiles: ["play-private"]' in compose
    assert 'CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "false"' in compose
    assert 'CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED: "false"' in compose
    assert "${CHUMMER_PUBLIC_PLAY_PROXY_ENABLED" not in compose
    assert "${CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED" not in compose
    assert "CHUMMER_PUBLIC_PLAY_PROXY_URL" not in compose
    assert "CHUMMER_PUBLIC_PLAY_PROXY_API_KEY" not in compose
    portal_dependencies = compose.split("  chummer-portal:", 1)[1].split("    environment:", 1)[0]
    assert "chummer-play-web:" not in portal_dependencies


def test_local_role_shell_uses_dedicated_no_inline_layout_and_restrictive_csp() -> None:
    view = (API / "Views" / "PublicLanding" / "MobileProjection.cshtml").read_text(encoding="utf-8")
    layout = (API / "Views" / "Shared" / "_MobileInstallLayout.cshtml").read_text(encoding="utf-8")
    controller = (API / "Controllers" / "PublicLandingController.cs").read_text(encoding="utf-8")
    model = (API / "ViewModels" / "SiteViewModels.cs").read_text(encoding="utf-8")
    program = (API / "Program.cs").read_text(encoding="utf-8")

    for role in ("player", "gm", "observer"):
        assert f'"/mobile/{role}"' in controller
        assert f'"/manifest.{role}.webmanifest"' in controller
    for field in ("DocumentTitle", "ManifestHref", "AppleAppTitle"):
        assert field in model
        assert f"Model.{field}" in view
    assert "MobileInstallRoleProfileViewModel" in model
    assert "Model.RoleProfile" in view
    for field in ("PurposeHeading", "PrivacyHeading", "AuthorityHeading", "InstallTargetPath", "Capabilities"):
        assert f"roleProfile.{field}" in view
    assert '"/manifest.play.webmanifest"' in controller
    assert "ApplyPrivateMobileDocumentHeaders();" in controller
    assert "connect-src 'none'" in controller
    assert 'src="/mobile-install-shell.js"' in layout
    assert "<script>" not in layout
    assert "script-src 'self'" in program
    assert "frame-ancestors 'none'" in program


def test_install_only_play_shell_has_no_blazor_boot_or_circuit_script() -> None:
    play_web = ROOT.parent / "chummer-play" / "src" / "Chummer.Play.Web"
    app = (play_web / "Components" / "App.razor").read_text(encoding="utf-8")
    page = (play_web / "Components" / "Pages" / "MobileTurnCompanionPage.razor").read_text(encoding="utf-8")

    assert "blazor.web.js" not in app
    assert "blazor.web.js" not in page
    assert 'src="/mobile-turn-companion.js"' not in page
    assert 'src="/mobile-install-shell.js"' in page


def test_private_play_api_null_remote_ip_fails_closed() -> None:
    play_web = ROOT.parent / "chummer-play" / "src" / "Chummer.Play.Web"
    application = (play_web / "PlayWebApplication.cs").read_text(encoding="utf-8")

    trust_boundary = application.split("public static bool IsTrustedPlayApiRequest", 1)[1].split(
        "private static bool FixedTimeEquals", 1
    )[0]
    assert "IPAddress? remoteAddress = context.Connection.RemoteIpAddress;" in trust_boundary
    assert "if (remoteAddress is null)" in trust_boundary
    assert trust_boundary.index("if (remoteAddress is null)") < trust_boundary.index("IsDevelopment()")
    assert trust_boundary.index("if (remoteAddress is null)") < trust_boundary.index("IPAddress.IsLoopback")
    null_branch = trust_boundary.split("if (remoteAddress is null)", 1)[1].split(
        "if (IPAddress.IsLoopback", 1
    )[0]
    assert "return false;" in null_branch


def test_service_workers_use_exact_mime_checked_atomic_critical_precache() -> None:
    for worker in (API / "wwwroot" / "service-worker.js", PLAY_ROOT / "service-worker.js"):
        source = worker.read_text(encoding="utf-8")
        assert "PUBLIC_CACHEABLE_ASSETS = new Map" in source
        assert "CRITICAL_SHELL_ASSETS" in source
        assert "isExpectedPublicAssetResponse" in source
        assert "await Promise.all(CRITICAL_SHELL_ASSETS.map" in source
        assert "Promise.allSettled" not in source
        assert "PUBLIC_RUNTIME_CACHE_PREFIXES" not in source
        assert "PUBLIC_RUNTIME_CACHE_SUFFIXES" not in source
        assert "/_framework/blazor.web.js" not in source


def test_qr_control_and_display_mode_are_bidirectional() -> None:
    partial = (API / "Views" / "Shared" / "_MobileAppHandoff.cshtml").read_text(encoding="utf-8")
    handoff = (API / "wwwroot" / "js" / "mobile-app-handoff.js").read_text(encoding="utf-8")
    install_source = (API / "wwwroot" / "mobile-install-shell.js").read_text(encoding="utf-8")
    install_projection = (PLAY_ROOT / "mobile-install-shell.js").read_text(encoding="utf-8")

    assert 'aria-expanded="false"' in partial
    qr_card_tag = next(
        line for line in partial.splitlines() if "data-mobile-app-qr-card" in line
    )
    assert " hidden>" in qr_card_tag
    assert "tabindex=" not in qr_card_tag
    assert "setQrExpanded" in handoff
    assert 'showQrButton.setAttribute("aria-expanded"' in handoff
    assert 'showQrButton.focus({ preventScroll: true });' in handoff
    assert "showQrButton.focus();" in handoff
    assert "qrCard.focus" not in handoff
    assert "restoreBrowserInstallState" in install_source
    assert "} else if (window.navigator.standalone !== true) {" in install_source
    assert 'register("/mobile/service-worker.js", { scope: "/mobile/" })' in install_source
    assert 'register("/service-worker.js", { scope: "/" })' not in install_source
    assert install_source == install_projection
