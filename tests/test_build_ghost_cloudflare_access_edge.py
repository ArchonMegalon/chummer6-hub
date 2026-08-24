import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.build-ghost-private-nonprod.yml"
COMPOSE = COMPOSE_PATH.read_text(encoding="utf-8")
EDGE_ROOT = ROOT / "ops/build-ghost-private-nonprod/cloudflare-access-edge"
PROXY = (EDGE_ROOT / "BuildGhostAccessProxy.cs").read_text(encoding="utf-8")
JWT = (EDGE_ROOT / "CloudflareAccessJwtValidator.cs").read_text(encoding="utf-8")
PROGRAM = (EDGE_ROOT / "Program.cs").read_text(encoding="utf-8")
DOCKERFILE = (
    ROOT / "ops/build-ghost-private-nonprod/Dockerfile.cloudflare-access-edge"
).read_text(encoding="utf-8")
HANDOFF = (
    ROOT / "ops/build-ghost-private-nonprod/CLOUDFLARE_ACCESS_INGRESS_HANDOFF.md"
).read_text(encoding="utf-8")


def compose_environment(*, configured_access: bool) -> dict[str, str]:
    environment = os.environ.copy()
    for index, name in enumerate(
        (
            "CHUMMER_RUN_SERVICES_REVISION",
            "CHUMMER_PRESENTATION_REVISION",
            "CHUMMER_CORE_ENGINE_REVISION",
            "CHUMMER_HUB_REGISTRY_REVISION",
            "CHUMMER_UI_KIT_REVISION",
            "CHUMMER_MEDIA_FACTORY_REVISION",
        ),
        start=1,
    ):
        environment[name] = str(index) * 40
    for name in (
        "CHUMMER_RUN_SERVICES_SOURCE",
        "CHUMMER_PRESENTATION_SOURCE",
        "CHUMMER_CORE_ENGINE_SOURCE",
        "CHUMMER_HUB_REGISTRY_SOURCE",
        "CHUMMER_UI_KIT_SOURCE",
        "CHUMMER_MEDIA_FACTORY_SOURCE",
    ):
        environment[name] = str(ROOT)
    environment["CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN"] = (
        "test-tool-token-" + "a" * 32
    )
    environment["CHUMMER_AI_INTERNAL_API_TOKEN"] = "test-ai-token-" + "b" * 32
    for name in (
        "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_HOST",
        "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_TEAM_DOMAIN",
        "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_AUDIENCE",
        "CHUMMER_BUILD_GHOST_CLOUDFLARE_INGRESS_NETWORK",
    ):
        environment.pop(name, None)
    if configured_access:
        environment.update(
            {
                "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_HOST": "ghost.chummer.run",
                "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_TEAM_DOMAIN": (
                    "example-team.cloudflareaccess.com"
                ),
                "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_AUDIENCE": "a" * 64,
                "CHUMMER_BUILD_GHOST_CLOUDFLARE_INGRESS_NETWORK": (
                    "test-build-ghost-cloudflare-ingress"
                ),
            }
        )
    return environment


def render_compose(*, profile: bool, configured_access: bool) -> dict:
    command = [
        "docker",
        "compose",
        "--project-directory",
        str(ROOT),
    ]
    if profile:
        command.extend(["--profile", "cloudflare-access-ingress"])
    command.extend(["--file", str(COMPOSE_PATH), "config", "--format", "json"])
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=compose_environment(configured_access=configured_access),
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_default_compose_does_not_start_or_attach_access_edge():
    rendered = render_compose(profile=False, configured_access=False)
    assert "build-ghost-cloudflare-access-edge" not in rendered["services"]
    assert "build-ghost-cloudflare-ingress" not in rendered.get("networks", {})
    assert set(rendered["services"]) == {
        "chummer-build-ghost-presentation",
        "chummer-build-ghost-ai",
        "build-ghost-private-edge",
        "build-ghost-private-trust-export",
    }


def test_profiled_edge_has_no_host_port_and_only_two_bounded_networks():
    rendered = render_compose(profile=True, configured_access=True)
    edge = rendered["services"]["build-ghost-cloudflare-access-edge"]
    assert edge["profiles"] == ["cloudflare-access-ingress"]
    assert "ports" not in edge
    assert "network_mode" not in edge
    assert set(edge["networks"]) == {
        "build-ghost-private",
        "build-ghost-cloudflare-ingress",
    }
    assert edge["read_only"] is True
    assert edge["restart"] == "on-failure:5"
    assert edge["cap_drop"] == ["ALL"]
    assert edge["security_opt"] == ["no-new-privileges:true"]
    ingress = rendered["networks"]["build-ghost-cloudflare-ingress"]
    assert ingress["external"] is True
    assert ingress["name"] == "test-build-ghost-cloudflare-ingress"


def test_profile_defaults_are_blocked_public_sentinels_and_never_credentials():
    rendered = render_compose(profile=True, configured_access=False)
    environment = rendered["services"]["build-ghost-cloudflare-access-edge"][
        "environment"
    ]
    assert environment == {
        "ASPNETCORE_URLS": "http://+:8080",
        "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_AUDIENCE": "",
        "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_HOST": "unconfigured.invalid",
        "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_TEAM_DOMAIN": (
            "unconfigured.cloudflareaccess.com"
        ),
    }
    edge_block = COMPOSE.split(
        "\n  build-ghost-cloudflare-access-edge:\n", 1
    )[1].split("\nvolumes:\n", 1)[0]
    assert "TOKEN" not in edge_block
    assert "SECRET" not in edge_block
    assert "TOUGH_TONGUE" not in edge_block
    assert "REMOTE_EXECUTION_ENABLED" not in edge_block


def test_existing_local_operator_edge_remains_loopback_and_unprofiled():
    local_edge = COMPOSE.split("\n  build-ghost-private-edge:\n", 1)[1].split(
        "\n  build-ghost-private-trust-export:\n", 1
    )[0]
    assert '127.0.0.1:${CHUMMER_BUILD_GHOST_PRIVATE_HTTPS_PORT:-8443}:443' in local_edge
    assert "profiles:" not in local_edge
    assert "build-ghost-cloudflare-ingress" not in local_edge
    assert "ops/build-ghost-private-nonprod/Caddyfile" in local_edge


def test_edge_allowlists_only_workspace_import_lifecycle_and_ephemeral_grant():
    assert '"/api/workspaces/import"' in PROXY
    assert "WorkspaceLifecyclePath" in PROXY
    assert "ToolAccessPath" in PROXY
    assert '"POST"' in PROXY
    assert '"GET"' in PROXY
    assert '"DELETE"' in PROXY
    for forbidden_route in (
        "/api/internal/build-ghost/tool/resolve",
        "/api/v1/ai/build-ghost/tool",
        "/api/v2/ai/build-ghost/tool",
        "/api/v1/ai/build-ghost/explain",
    ):
        assert forbidden_route not in PROXY
    assert "PresentationOrigin" in PROXY
    assert "chummer-build-ghost-ai" not in PROXY


def test_edge_validates_both_access_headers_and_cryptographic_identity_binding():
    assert '"Cf-Access-Authenticated-User-Email"' in PROXY
    assert '"Cf-Access-Jwt-Assertion"' in PROXY
    assert "values.Count != 1" in PROXY
    assert "rawEmail.ToLowerInvariant()" in PROXY
    assert "RSA.Create()" in JWT
    assert '"RS256"' in JWT
    assert 'TryReadExactString(payload, "iss"' in JWT
    assert "HasExactAudience(payload, _configuration.Audience)" in JWT
    assert 'TryReadExactString(payload, "email"' in JWT
    assert "rsa.VerifyData" in JWT
    assert "AllowAutoRedirect = false" in PROGRAM
    assert "UseCookies = false" in PROGRAM
    assert "UseProxy = false" in PROGRAM


def test_upstream_is_reconstructed_and_access_assertion_is_not_logged_or_forwarded():
    assert "builder.Logging.ClearProviders()" in PROGRAM
    assert "CreateUpstreamRequest" in PROXY
    assert "outgoing.Headers.TryAddWithoutValidation(OwnerHeader, authenticatedEmail)" in PROXY
    assert "CopySingleSafeHeader" in PROXY
    assert "request.Headers" not in PROXY.split(
        "public static HttpRequestMessage CreateUpstreamRequest", 1
    )[1].split("public static bool IsForbiddenUpstreamHeader", 1)[0].replace(
        "request.Headers, outgoing.Headers", ""
    )
    assert "CacheControl = new CacheControlHeaderValue { NoStore = true }" in PROXY
    assert 'response.Headers.CacheControl = "no-store"' in PROXY
    assert "Set-Cookie" not in PROXY


def test_edge_image_is_digest_pinned_nonroot_and_has_no_tunnel_or_provider_binary():
    assert "dotnet/sdk:10.0.103@sha256:" in DOCKERFILE
    assert "dotnet/aspnet:10.0@sha256:" in DOCKERFILE
    assert "USER $APP_UID:$APP_UID" in DOCKERFILE
    assert "cloudflared" not in DOCKERFILE
    assert "caddy" not in DOCKERFILE.lower()
    assert "TOUGH_TONGUE" not in DOCKERFILE


def test_operator_handoff_stops_before_live_mutation_and_preserves_provider_gates():
    assert "No live action was performed" in HANDOFF
    assert "independent security review" in HANDOFF
    assert "do not attach" in HANDOFF.lower()
    assert "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_AUDIENCE" in HANDOFF
    assert "httpHostHeader" in HANDOFF
    assert "never authorizes provider execution" in HANDOFF
    assert "false" in HANDOFF
