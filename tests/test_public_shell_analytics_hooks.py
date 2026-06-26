from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
LAYOUT_PATH = REPO_ROOT / "Chummer.Run.Api" / "Views" / "Shared" / "_Layout.cshtml"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
PUBLIC_EDGE_COMPOSE_PATH = REPO_ROOT / "docker-compose.public-edge.yml"
PROGRAM_PATH = REPO_ROOT / "Chummer.Run.Api" / "Program.cs"
PUBLIC_LANDING_CONTROLLER_PATH = REPO_ROOT / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"
KNOWLEDGE_FABRIC_SERVICE_PATH = REPO_ROOT / "Chummer.Run.Api" / "Services" / "KnowledgeFabricService.cs"
NEXUS_PAN_SERVICE_PATH = REPO_ROOT / "Chummer.Run.Api" / "Services" / "NexusPanContinuityService.cs"
PUBLIC_LANDING_MANIFEST_PATH = REPO_ROOT / ".codex-design" / "product" / "PUBLIC_LANDING_MANIFEST.yaml"
PUBLIC_FEATURE_REGISTRY_PATH = REPO_ROOT / ".codex-design" / "product" / "PUBLIC_FEATURE_REGISTRY.yaml"


class PublicShellAnalyticsHooksTests(unittest.TestCase):
    def test_layout_wires_rybbit_as_env_gated_public_only_hook(self) -> None:
        source = LAYOUT_PATH.read_text(encoding="utf-8")
        self.assertIn("CLICKRANK_AI_CHUMMER_RUN_SITE_ID", source)
        self.assertIn("RYBBIT_CHUMMER_RUN_SITE_ID", source)
        self.assertIn("RYBBIT_CHUMMER_RUN_SCRIPT_URL", source)
        self.assertIn("RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN", source)
        self.assertIn("RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY", source)
        self.assertIn("requestHost is \"chummer.run\" or \"www.chummer.run\"", source)
        self.assertIn("navigator.globalPrivacyControl === true", source)
        self.assertIn("document.querySelector(\"script[data-rybbit='analytics']\")", source)
        self.assertIn("document.querySelector(\"script[data-clickrank='seo']\")", source)
        self.assertNotIn("data-clickrank-ai", source)
        self.assertNotIn("clickRankAi", source)
        self.assertNotIn("public-copy-humanizer.js", source)
        self.assertIn('rybbit.src = "@rybbitScriptUrl";', source)
        self.assertIn('rybbit.dataset.siteId = "@rybbitSiteId";', source)
        self.assertIn('rybbit.dataset.skipPatterns =', source)
        self.assertIn('rybbit.dataset.tag = "hub_public_shell";', source)

    def test_public_views_and_site_js_expose_first_party_cta_telemetry(self) -> None:
        site_js = (REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / "js" / "site.js").read_text(encoding="utf-8")
        landing = (REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Landing.cshtml").read_text(encoding="utf-8")
        downloads = (REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Downloads.cshtml").read_text(encoding="utf-8")
        status = (REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Status.cshtml").read_text(encoding="utf-8")
        ledger = (REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Ledger.cshtml").read_text(encoding="utf-8")
        self.assertIn("window.ChummerAnalyticsQueue", site_js)
        self.assertIn("ChummerUi.trackPublicEvent", site_js)
        self.assertIn('data-analytics-event="homepage_open_downloads"', landing)
        self.assertNotIn('data-analytics-event="homepage_open_stable"', landing)
        self.assertNotIn('data-analytics-event="homepage_open_nightly"', landing)
        self.assertIn('data-analytics-event="downloads_stable_install"', downloads)
        self.assertIn('data-analytics-event="downloads_nightly_install"', downloads)
        self.assertIn('data-analytics-event="status_next_action"', status)
        self.assertIn('data-analytics-event="ledger_primary_action"', ledger)

    def test_local_env_and_public_edge_compose_expose_rybbit_configuration(self) -> None:
        env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
        compose = PUBLIC_EDGE_COMPOSE_PATH.read_text(encoding="utf-8")
        self.assertIn("CLICKRANK_AI_CHUMMER_RUN_SITE_ID=", env_example)
        self.assertIn("CLICKRANK_AI_CHUMMER_RUN_SITE_ID: ${CLICKRANK_AI_CHUMMER_RUN_SITE_ID:-}", compose)
        self.assertIn("RYBBIT_CHUMMER_RUN_SITE_ID=", env_example)
        self.assertIn("RYBBIT_CHUMMER_RUN_SCRIPT_URL=", env_example)
        self.assertIn("RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN=https://app.rybbit.io", env_example)
        self.assertIn("RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY=false", env_example)
        self.assertIn("RYBBIT_CHUMMER_RUN_SITE_ID: ${RYBBIT_CHUMMER_RUN_SITE_ID:-}", compose)
        self.assertIn("RYBBIT_CHUMMER_RUN_SCRIPT_URL: ${RYBBIT_CHUMMER_RUN_SCRIPT_URL:-}", compose)
        self.assertIn("RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN: ${RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN:-https://app.rybbit.io}", compose)
        self.assertIn("RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY: ${RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY:-false}", compose)
        self.assertIn("RYBBIT_CHUMMER_DESKTOP_SITE_ID=", env_example)
        self.assertIn("RYBBIT_CHUMMER_DESKTOP_API_KEY=", env_example)
        self.assertIn("RYBBIT_CHUMMER_DESKTOP_API_ORIGIN=https://app.rybbit.io", env_example)
        self.assertIn("RYBBIT_CHUMMER_DESKTOP_SITE_ID: ${RYBBIT_CHUMMER_DESKTOP_SITE_ID:-}", compose)
        self.assertIn("RYBBIT_CHUMMER_DESKTOP_API_KEY: ${RYBBIT_CHUMMER_DESKTOP_API_KEY:-}", compose)
        self.assertIn("RYBBIT_CHUMMER_DESKTOP_API_ORIGIN: ${RYBBIT_CHUMMER_DESKTOP_API_ORIGIN:-https://app.rybbit.io}", compose)

    def test_program_maps_bounded_desktop_analytics_ingest(self) -> None:
        source = PROGRAM_PATH.read_text(encoding="utf-8")
        self.assertIn('MapPost("/api/desktop-analytics/track"', source)
        self.assertIn("DesktopAnalyticsBridgeService", source)
        self.assertIn("Desktop analytics validation failed.", source)

    def test_rybbit_proxy_uses_request_and_response_header_allowlists(self) -> None:
        source = PROGRAM_PATH.read_text(encoding="utf-8")
        policy_source = (REPO_ROOT / "Chummer.Run.Api" / "Services" / "RybbitProxyPolicy.cs").read_text(encoding="utf-8")
        self.assertIn("RybbitProxyPolicy.ShouldForwardRequestHeader(key)", source)
        self.assertIn("RybbitProxyPolicy.ShouldForwardResponseHeader(header.Key)", source)
        self.assertIn("RybbitProxyPolicy.NormalizeProxyPath(proxyPath)", source)
        self.assertIn('HashSet<string> AllowedRequestHeaders', policy_source)
        self.assertIn('HashSet<string> AllowedResponseHeaders', policy_source)
        self.assertIn('"Cookie"', policy_source)
        self.assertIn('"Authorization"', policy_source)
        self.assertIn('"Set-Cookie"', policy_source)
        self.assertIn('builder.Services.AddHttpClient("RybbitProxy"', source)
        self.assertIn('CreateClient("RybbitProxy")', source)
        self.assertNotIn("using var client = new HttpClient();", source)

        allowed_request_headers = self._read_csharp_string_set(policy_source, "AllowedRequestHeaders")
        blocked_request_headers = self._read_csharp_string_set(policy_source, "BlockedRequestHeaders")
        allowed_response_headers = self._read_csharp_string_set(policy_source, "AllowedResponseHeaders")
        blocked_response_headers = self._read_csharp_string_set(policy_source, "BlockedResponseHeaders")

        self.assertNotIn("Cookie", allowed_request_headers)
        self.assertNotIn("Authorization", allowed_request_headers)
        self.assertNotIn("Proxy-Authorization", allowed_request_headers)
        self.assertNotIn("Host", allowed_request_headers)
        self.assertNotIn("Connection", allowed_request_headers)
        self.assertNotIn("Transfer-Encoding", allowed_request_headers)
        self.assertNotIn("X-Forwarded-For", allowed_request_headers)
        self.assertNotIn("X-Forwarded-Host", allowed_request_headers)
        self.assertNotIn("X-Forwarded-Proto", allowed_request_headers)
        self.assertNotIn("Forwarded", allowed_request_headers)
        self.assertIn("Cookie", blocked_request_headers)
        self.assertIn("Authorization", blocked_request_headers)
        self.assertIn("Proxy-Authorization", blocked_request_headers)
        self.assertIn("Host", blocked_request_headers)
        self.assertIn("Connection", blocked_request_headers)
        self.assertIn("Transfer-Encoding", blocked_request_headers)
        self.assertIn("X-Forwarded-For", blocked_request_headers)
        self.assertIn("X-Forwarded-Host", blocked_request_headers)
        self.assertIn("X-Forwarded-Proto", blocked_request_headers)
        self.assertIn("Forwarded", blocked_request_headers)

        self.assertNotIn("Set-Cookie", allowed_response_headers)
        self.assertNotIn("Proxy-Authenticate", allowed_response_headers)
        self.assertNotIn("Proxy-Authorization", allowed_response_headers)
        self.assertNotIn("Connection", allowed_response_headers)
        self.assertNotIn("Transfer-Encoding", allowed_response_headers)
        self.assertIn("Set-Cookie", blocked_response_headers)
        self.assertIn("Proxy-Authenticate", blocked_response_headers)
        self.assertIn("Proxy-Authorization", blocked_response_headers)
        self.assertIn("Connection", blocked_response_headers)
        self.assertIn("Transfer-Encoding", blocked_response_headers)
        self.assertIn("return AllowedRequestHeaders.Contains(headerName);", policy_source)
        self.assertIn("return AllowedResponseHeaders.Contains(headerName);", policy_source)
        self.assertIn("catch (UriFormatException)", policy_source)
        self.assertIn("escapedSegments.Add(Uri.EscapeDataString(unescapedSegment));", policy_source)
        self.assertIn('normalized.Contains("://", StringComparison.Ordinal)', policy_source)
        self.assertIn('segment.Equals("..", StringComparison.Ordinal)', policy_source)

    def test_public_horizon_actions_use_clean_detail_aliases(self) -> None:
        controller = PUBLIC_LANDING_CONTROLLER_PATH.read_text(encoding="utf-8")
        knowledge = KNOWLEDGE_FABRIC_SERVICE_PATH.read_text(encoding="utf-8")
        nexus = NEXUS_PAN_SERVICE_PATH.read_text(encoding="utf-8")
        manifest = PUBLIC_LANDING_MANIFEST_PATH.read_text(encoding="utf-8")
        registry = PUBLIC_FEATURE_REGISTRY_PATH.read_text(encoding="utf-8")

        for alias in [
            '[HttpGet("/rules/explanations")]',
            '[HttpGet("/rules/explanations/{receiptId}.json")]',
            '[HttpGet("/play/continuity/history")]',
            '[HttpGet("/play/continuity/history/{receiptId}.json")]',
            '[HttpGet("/runsites/prep-network")]',
            '[HttpGet("/run-control/control-network")]',
            '[HttpGet("/passport/identity-network")]',
            '[HttpGet("/passport/{receiptId}.md")]',
            '[HttpGet("/signal-deck/{receiptId}.md")]',
            '[HttpGet("/living-world/{receiptId}.md")]',
        ]:
            self.assertIn(alias, controller)

        for legacy_route in [
            '[HttpGet("/rules/receipts")]',
            '[HttpGet("/play/continuity/receipts")]',
            '[HttpGet("/runsites/receipts/prep-network.json")]',
            '[HttpGet("/run-control/receipts/control-network.json")]',
            '[HttpGet("/passport/receipts/identity-network.json")]',
            '[HttpGet("/signal-deck/receipts/{receiptId}.md")]',
            '[HttpGet("/living-world/receipts/{receiptId}.md")]',
        ]:
            self.assertIn(legacy_route, controller)

        visible_controller_lines = [
            line for line in controller.splitlines()
            if "new TrustPageActionViewModel(" in line
            or "Href:" in line
            or "ExplainReceiptHref =" in line
            or "MarkdownHref =" in line
            or "JsonHref =" in line
        ]
        visible_text = "\n".join(visible_controller_lines)
        service_visible_text = "\n".join(
            line for line in (knowledge + "\n" + nexus).splitlines()
            if "Route:" in line or "receipt_index_route" in line
        )

        for old_path in [
            "/rules/receipts",
            "/play/continuity/receipts",
            "/jackpoint/receipts/briefing-network.json",
            "/runsites/receipts/prep-network.json",
            "/onramp/receipts/guided-starter.json",
            "/edition-studio/receipts/ruleset-heads.json",
            "/local-co-processor/receipts/optional-acceleration.json",
            "/run-control/receipts/control-network.json",
            "/quicksilver/receipts/command-network.json",
            "/community/receipts/open-run-network.json",
            "/creator/receipts/publication-network.json",
            "/passport/receipts/runner_return_posture",
            "/signal-deck/receipts/pressure_posture",
            "/living-world/receipts/watch_package_posture",
        ]:
            self.assertNotIn(old_path, visible_text)
            self.assertNotIn(old_path, service_visible_text)

        for clean_path in [
            "/rules/explanations",
            "/play/continuity/history",
            "/jackpoint/briefing-network",
            "/runsites/prep-network",
            "/run-control/control-network",
            "/passport/runner_return_posture.md",
            "/signal-deck/pressure_posture.md",
            "/living-world/watch_package_posture.md",
        ]:
            self.assertIn(clean_path, controller + "\n" + knowledge + "\n" + nexus)

        self.assertIn("detail_route: /rules/explanations", registry)
        self.assertNotIn("/artifacts/explanation-path", registry)

        for public_route in [
            "/rules/explanations",
            "/jackpoint/briefing-network",
            "/runsites/prep-network",
            "/run-control/control-network",
            "/onramp/guided-starter",
            "/edition-studio/ruleset-heads",
            "/passport/identity-network",
            "/quicksilver/command-network",
            "/ghostwire/replay-network",
            "/anarchy/runtime",
            "/local-co-processor/optional-acceleration",
        ]:
            self.assertIn(f"- path: {public_route}", manifest)

        for stale_manifest_route in [
            "/jackpoint/receipts/briefing-network.json",
            "/runsites/receipts/prep-network.json",
            "/run-control/receipts/control-network.json",
            "/passport/receipts/identity-network.json",
            "/anarchy/receipts/runtime.json",
            "/local-co-processor/receipts/optional-acceleration.json",
        ]:
            self.assertNotIn(f"- path: {stale_manifest_route}", manifest)

    @staticmethod
    def _read_csharp_string_set(source: str, set_name: str) -> set[str]:
        match = re.search(
            rf"HashSet<string>\s+{re.escape(set_name)}\s*=\s*new\([^)]*\)\s*\{{(?P<body>.*?)\}};",
            source,
            flags=re.DOTALL,
        )
        if not match:
            raise AssertionError(f"missing C# string set: {set_name}")
        return set(re.findall(r'"([^"]+)"', match.group("body")))

    def test_desktop_analytics_bridge_requires_dedicated_desktop_site_id_and_restricts_http_to_local_hosts(self) -> None:
        source = (REPO_ROOT / "Chummer.Run.Api" / "Services" / "DesktopAnalyticsBridgeService.cs").read_text(encoding="utf-8")
        self.assertIn('(_configuration["RYBBIT_CHUMMER_DESKTOP_SITE_ID"] ?? string.Empty).Trim()', source)
        self.assertNotIn('ResolveConfiguredValue("RYBBIT_CHUMMER_DESKTOP_SITE_ID", "RYBBIT_CHUMMER_RUN_SITE_ID")', source)
        self.assertIn('AllowedLocalOrigins', source)
        self.assertIn('trackUri.Scheme == Uri.UriSchemeHttps', source)
        self.assertIn('trackUri.Scheme == Uri.UriSchemeHttp', source)
        self.assertIn('AllowedLocalOrigins.Contains(trackUri.Host)', source)
        self.assertIn('if (!string.IsNullOrWhiteSpace(apiKey))', source)
        self.assertIn('Accepted: false, Forwarded: false, Status: $"provider_http_{(int)response.StatusCode}"', source)
        self.assertIn('Accepted: false, Forwarded: false, Status: "provider_error"', source)
        self.assertIn('Status: string.IsNullOrWhiteSpace(apiKey) ? "forwarded_public" : "forwarded"', source)

    def test_desktop_analytics_bridge_accepts_every_avalonia_shell_event(self) -> None:
        bridge_source = (REPO_ROOT / "Chummer.Run.Api" / "Services" / "DesktopAnalyticsBridgeService.cs").read_text(encoding="utf-8")
        event_handler_source = (REPO_ROOT.parent / "chummer6-ui" / "Chummer.Avalonia" / "MainWindow.EventHandlers.cs").read_text(encoding="utf-8")

        allowed_events = self._read_csharp_string_set(bridge_source, "AllowedEvents")
        emitted_events = set(re.findall(r'TrackDesktopShellEventAsync\("([^"]+)"', event_handler_source))

        self.assertGreater(len(emitted_events), 0)
        self.assertLessEqual(emitted_events, allowed_events)


if __name__ == "__main__":
    unittest.main()
