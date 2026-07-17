from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "Chummer.Run.Api"


def test_public_play_projection_is_readiness_only_and_cannot_make_outbound_requests() -> None:
    gateway = (API / "Services" / "PublicPlayProxyGateway.cs").read_text(encoding="utf-8")
    program = (API / "Program.cs").read_text(encoding="utf-8")

    assert "Array.Empty<string>()" in gateway
    assert "Task.FromResult(PublicPlayProxyDisposition.NotMatched)" in gateway
    for transport_symbol in (
        "IHttpClientFactory",
        "HttpClient",
        "HttpRequestMessage",
        "HttpResponseMessage",
        "SendAsync",
        "CopyToAsync",
        "ReadAsStream",
    ):
        assert transport_symbol not in gateway
    assert "playProjectionGateway.TryHandleAsync" not in program
    assert "CHUMMER_PUBLIC_PLAY_PROXY_API_KEY" not in program


def test_invalid_enabled_projection_stays_alive_with_loud_readiness_and_local_fallback() -> None:
    gateway = (API / "Services" / "PublicPlayProxyGateway.cs").read_text(encoding="utf-8")
    program = (API / "Program.cs").read_text(encoding="utf-8")
    landing = (API / "Controllers" / "PublicLandingController.cs").read_text(encoding="utf-8")

    assert "projection_disabled_invalid_configuration" in gateway
    assert "Ready: false" in gateway
    assert "local install mirrors remain available" in gateway
    startup_section = program.split("var app = builder.Build();", 1)[1].split(
        "const string NoIndexRobotsPolicy", 1
    )[0]
    assert "playProjectionGateway.GetReadiness()" in startup_section
    assert "app.Logger.LogError" in startup_section
    assert "throw" not in startup_section
    assert '"/api/ready/play-projection"' in program
    assert "StatusCodes.Status503ServiceUnavailable" in program
    assert "MobileProjection" in landing


def test_default_compose_never_starts_or_injects_credentials_into_private_play() -> None:
    compose = (ROOT / "docker-compose.public-edge.yml").read_text(encoding="utf-8")

    assert 'profiles: ["play-private"]' in compose
    assert 'CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "${CHUMMER_PUBLIC_PLAY_PROXY_ENABLED:-false}"' in compose
    assert "CHUMMER_PUBLIC_PLAY_PROXY_API_KEY" not in compose
    portal_dependencies = compose.split("  chummer-portal:", 1)[1].split("    environment:", 1)[0]
    assert "chummer-play-web:" not in portal_dependencies


def test_dynamic_play_and_blazor_routes_remain_zero_upstream_deny_all() -> None:
    program = (API / "Program.cs").read_text(encoding="utf-8")
    controller = (API / "Controllers" / "LegacySurfaceRedirectController.cs").read_text(encoding="utf-8")
    delegator = (API / "Services" / "PublicPlayPrivateRouteDelegator.cs").read_text(encoding="utf-8")

    assert "PublicPlaySessionAccessPolicy.RequiresSessionGrant" in program
    assert "privateRoutes.DenyAsync" in program
    assert controller.count("_privatePlayRoutes.DenyAsync") == 2
    assert "DenyAllPublicPlayPrivateRouteDelegator" in delegator
    assert "StatusCodes.Status404NotFound" in delegator
