import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.build-ghost-private-nonprod.yml"
COMPOSE = COMPOSE_PATH.read_text(encoding="utf-8")
EDGE_ROOT = ROOT / "ops/build-ghost-private-nonprod/cloudflare-access-edge"
PROXY = (EDGE_ROOT / "BuildGhostAccessProxy.cs").read_text(encoding="utf-8")
GRANT_REGISTRY = (EDGE_ROOT / "BuildGhostOwnerBoundGrantRegistry.cs").read_text(
    encoding="utf-8"
)
PROVIDER_CONTRACT = (EDGE_ROOT / "BuildGhostProviderToolRequestContract.cs").read_text(
    encoding="utf-8"
)
JWT = (EDGE_ROOT / "CloudflareAccessJwtValidator.cs").read_text(encoding="utf-8")
PROGRAM = (EDGE_ROOT / "Program.cs").read_text(encoding="utf-8")
TRANSPORT = (EDGE_ROOT / "AccessEdgeHttpTransport.cs").read_text(encoding="utf-8")
MANAGED_TESTS = (
    ROOT / "ops/build-ghost-private-nonprod/cloudflare-access-edge.tests/Program.cs"
).read_text(encoding="utf-8")
VERIFIER = (
    ROOT / "ops/build-ghost-private-nonprod/verify-cloudflare-access-edge.sh"
).read_text(encoding="utf-8")
WORKFLOW = (
    ROOT / ".github/workflows/build-ghost-cloudflare-access-edge.yml"
).read_text(encoding="utf-8")
DOCKERFILE = (
    ROOT / "ops/build-ghost-private-nonprod/Dockerfile.cloudflare-access-edge"
).read_text(encoding="utf-8")
HANDOFF = (
    ROOT / "ops/build-ghost-private-nonprod/CLOUDFLARE_ACCESS_INGRESS_HANDOFF.md"
).read_text(encoding="utf-8")


def compose_environment(
    *,
    configured_access: bool,
    ingress_network: str | None = "test-build-ghost-cloudflare-ingress",
) -> dict[str, str]:
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
    environment["CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY"] = "A" * 43 + "="
    for name in (
        "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_HOST",
        "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_TEAM_DOMAIN",
        "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_AUDIENCE",
        "CHUMMER_BUILD_GHOST_CLOUDFLARE_INGRESS_NETWORK",
    ):
        environment.pop(name, None)
    if ingress_network is not None:
        environment["CHUMMER_BUILD_GHOST_CLOUDFLARE_INGRESS_NETWORK"] = (
            ingress_network
        )
    if configured_access:
        environment.update(
            {
                "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_HOST": "ghost.chummer.run",
                "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_TEAM_DOMAIN": (
                    "example-team.cloudflareaccess.com"
                ),
                "CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_AUDIENCE": "a" * 64,
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
        "build-ghost-live-support-store-init",
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
    assert set(edge["depends_on"]) == {
        "chummer-build-ghost-ai",
        "chummer-build-ghost-presentation",
    }
    ingress = rendered["networks"]["build-ghost-cloudflare-ingress"]
    assert ingress["external"] is True
    assert ingress["name"] == "test-build-ghost-cloudflare-ingress"


def test_external_ingress_network_name_is_strictly_required_and_blank_closed():
    for ingress_network in (None, ""):
        command = [
            "docker",
            "compose",
            "--project-directory",
            str(ROOT),
            "--profile",
            "cloudflare-access-ingress",
            "--file",
            str(COMPOSE_PATH),
            "config",
            "--format",
            "json",
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=compose_environment(
                configured_access=True,
                ingress_network=ingress_network,
            ),
        )
        assert result.returncode != 0
        assert "CHUMMER_BUILD_GHOST_CLOUDFLARE_INGRESS_NETWORK" in result.stderr

    rendered = render_compose(profile=True, configured_access=True)
    assert rendered["networks"]["build-ghost-cloudflare-ingress"]["name"] == (
        "test-build-ghost-cloudflare-ingress"
    )
    assert (
        "${CHUMMER_BUILD_GHOST_CLOUDFLARE_INGRESS_NETWORK:?"
        in COMPOSE
    )


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
        "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_CONTRACT_DIGEST": (
            "sha256:af7b643855bbc2220be40bfadc8cb1e89"
            "ecdc324a787c771a353d74e85f01104"
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


def test_edge_allowlists_only_workspace_and_exact_owner_bound_v2_packet_tool():
    assert '"/api/workspaces/import"' in PROXY
    assert "WorkspaceLifecyclePath" in PROXY
    assert "ToolAccessPath" in PROXY
    assert '"POST"' in PROXY
    assert '"GET"' in PROXY
    assert '"DELETE"' in PROXY
    for forbidden_route in (
        "/api/internal/build-ghost/tool/resolve",
        "/api/v1/ai/build-ghost/tool",
        "/api/v1/ai/build-ghost/explain",
    ):
        assert forbidden_route not in PROXY
        assert forbidden_route not in PROVIDER_CONTRACT
    assert '"/api/v2/ai/build-ghost/tool"' in PROVIDER_CONTRACT
    assert "ProviderToolV2" in PROXY
    assert "PresentationOrigin" in PROXY
    assert "AiOrigin" in PROXY
    assert "chummer-build-ghost-ai" in PROXY
    assert "private_tool_provider_request_invalid" in PROXY
    assert "private-tool-authority-rejected" in PROXY
    assert "MaximumBodyBytes = 16 * 1024" in PROVIDER_CONTRACT
    assert "MaximumResponseBytes = 64 * 1024" in PROVIDER_CONTRACT


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
    assert TRANSPORT.count("ActivityHeadersPropagator = null") == 3
    assert TRANSPORT.count("AllowAutoRedirect = false") == 3
    assert TRANSPORT.count("UseCookies = false") == 3
    assert TRANSPORT.count("UseProxy = false") == 3
    assert "CreateCertificateHandler" in PROGRAM
    assert "CreatePresentationHandler" in PROGRAM
    assert "CreateAiHandler" in PROGRAM
    assert 'TryReadExactString(payload, "type"' in JWT
    assert 'string.Equals(accessTokenType, "app"' in JWT
    assert "MaximumTokenLifetimeSeconds = 24 * 60 * 60" in JWT


def test_upstream_is_reconstructed_and_access_assertion_is_not_logged_or_forwarded():
    assert "builder.Logging.ClearProviders()" in PROGRAM
    assert "CreateUpstreamRequest" in PROXY
    assert "outgoing.Headers.TryAddWithoutValidation(OwnerHeader, authenticatedEmail)" in PROXY
    assert "CopySingleSafeHeader" in PROXY
    assert "request.Headers" not in PROXY.split(
        "public static HttpRequestMessage CreateUpstreamRequest", 1
    )[1].split("public static HttpRequestMessage CreateProviderToolUpstreamRequest", 1)[0].replace(
        "request.Headers, outgoing.Headers", ""
    )
    provider_rebuild = PROXY.split(
        "public static HttpRequestMessage CreateProviderToolUpstreamRequest", 1
    )[1].split("private async Task IssueOwnerBoundGrantAsync", 1)[0]
    assert "OwnerHeader" not in provider_rebuild
    assert "Authorization" not in provider_rebuild
    assert "Cookie" not in provider_rebuild
    assert "ToolContractHeader" in provider_rebuild
    assert "CacheControl = new CacheControlHeaderValue { NoStore = true }" in PROXY
    assert 'response.Headers.CacheControl = "no-store"' in PROXY
    assert "Set-Cookie" not in PROXY


def test_owner_binding_retains_no_raw_key_and_claims_before_single_dispatch():
    assert "SHA256.HashData(material)" in GRANT_REGISTRY
    assert "CryptographicOperations.ZeroMemory(material)" in GRANT_REGISTRY
    assert "Dictionary<string, OwnerBoundGrant>" in GRANT_REGISTRY
    assert "PacketAccessKey" not in GRANT_REGISTRY.split(
        "private sealed record OwnerBoundGrant", 1
    )[1]
    assert "MaximumBindings = 4096" in GRANT_REGISTRY
    assert "MaximumGrantLifetime = TimeSpan.FromMinutes(5)" in GRANT_REGISTRY
    claim = GRANT_REGISTRY.split("public bool TryClaim", 1)[1]
    assert claim.index("_bindings.Remove(keyRef)") < claim.index("return true")
    dispatch = PROXY.split("private async Task DispatchOwnerBoundProviderToolAsync", 1)[1]
    assert dispatch.index("_grantRegistry.TryClaim") < dispatch.index("_aiUpstream.SendAsync")
    assert "CryptographicOperations.ZeroMemory(requestBody)" in dispatch
    assert "builder.Logging.ClearProviders()" in PROGRAM


def test_provider_contract_rejects_unknown_duplicate_and_header_credentials():
    assert "HasExactUniqueProperties" in PROVIDER_CONTRACT
    assert "!seen.Add(property.Name)" in PROVIDER_CONTRACT
    assert "JsonUnmappedMemberHandling.Disallow" in PROVIDER_CONTRACT
    assert "IsCanonicalPacketAccessKey" in PROVIDER_CONTRACT
    assert "IsCanonicalPacketDigest" in PROVIDER_CONTRACT
    dispatch = PROXY.split("private async Task DispatchOwnerBoundProviderToolAsync", 1)[1]
    assert 'ContainsKey("Authorization")' in dispatch
    assert 'ContainsKey("Cookie")' in dispatch
    assert '"no-store"' in dispatch
    assert "FixedEquals(suppliedContract" in dispatch
    for hostile_receipt in (
        "owner-bound v2 broker issues dispatches once",
        "owner-bound v2 broker fails closed across owner replay expiry restart and revocation",
        "owner-bound v2 broker rejects hostile contract and body ambiguity",
    ):
        assert hostile_receipt in MANAGED_TESTS


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
    assert "`Everyone` bypass" in HANDOFF
    assert "service-token" in HANDOFF
    assert "false" in HANDOFF


def test_jwks_refresh_is_generation_coalesced_and_retry_bounded_without_stale_keys():
    assert "RefreshRetrySeconds = 30" in JWT
    assert "current.Generation != observed.Generation" in JWT
    assert "now < current.RefreshNotBefore" in JWT
    assert "static CacheState Failed(" in JWT
    assert "CacheState.AfterFailedRefresh(" in JWT
    assert "DateTimeOffset.MinValue" in JWT
    assert "current.IsFresh(now)" in JWT
    assert "GetConcurrentWaveAsync" in MANAGED_TESTS
    for scenario in (
        "sameUnknown",
        "differentUnknown",
        "failedInitial",
        "failedWarmUnknown",
        "afterRotation",
        "failedRefresh",
        "newKid",
        "concurrent",
    ):
        assert scenario in MANAGED_TESTS
    assert "Enumerable.Range(1, 31)" in MANAGED_TESTS


def test_canonical_verifier_cannot_escape_repo_locked_exact_sdk():
    assert 'expected_sdk="10.0.103"' in VERIFIER
    assert '"$repo_root/global.json"' in VERIFIER
    assert 'locked_roll_forward' in VERIFIER
    assert 'cd -- "$repo_root" && dotnet --version' in VERIFIER
    assert 'cd -- "$verify_root"' not in VERIFIER
    assert '--project "ops/build-ghost-private-nonprod/cloudflare-access-edge.tests/' in VERIFIER
    assert '--artifacts-path "$verify_root/artifacts"' in VERIFIER


def test_cloudflare_edge_pr_ci_is_narrow_hash_pinned_and_exact_sdk():
    assert "pull_request:" in WORKFLOW
    assert "push:" not in WORKFLOW
    assert "workflow_dispatch:" not in WORKFLOW
    assert "ops/build-ghost-private-nonprod/cloudflare-access-edge/**" in WORKFLOW
    assert "tests/test_build_ghost_cloudflare_access_edge.py" in WORKFLOW
    assert "./ops/build-ghost-private-nonprod/verify-cloudflare-access-edge.sh" in WORKFLOW
    assert "--version 10.0.103" in WORKFLOW
    assert 'test "$(dotnet --version)" = "10.0.103"' in WORKFLOW
    action_lines = [line.strip() for line in WORKFLOW.splitlines() if "uses:" in line]
    assert action_lines
    for line in action_lines:
        action = line.split("uses:", 1)[1].split("#", 1)[0].strip()
        assert "@" in action
        assert len(action.rsplit("@", 1)[1]) == 40
