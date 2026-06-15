from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
LAYOUT_PATH = REPO_ROOT / "Chummer.Run.Api" / "Views" / "Shared" / "_Layout.cshtml"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
PUBLIC_EDGE_COMPOSE_PATH = REPO_ROOT / "docker-compose.public-edge.yml"
PROGRAM_PATH = REPO_ROOT / "Chummer.Run.Api" / "Program.cs"


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
        self.assertIn('data-analytics-event="homepage_open_ledger"', landing)
        self.assertIn('data-analytics-event="downloads_primary_install"', downloads)
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

    def test_desktop_analytics_bridge_requires_dedicated_desktop_site_id_and_restricts_http_to_local_hosts(self) -> None:
        source = (REPO_ROOT / "Chummer.Run.Api" / "Services" / "DesktopAnalyticsBridgeService.cs").read_text(encoding="utf-8")
        self.assertIn('(_configuration["RYBBIT_CHUMMER_DESKTOP_SITE_ID"] ?? string.Empty).Trim()', source)
        self.assertNotIn('ResolveConfiguredValue("RYBBIT_CHUMMER_DESKTOP_SITE_ID", "RYBBIT_CHUMMER_RUN_SITE_ID")', source)
        self.assertIn('AllowedLocalOrigins', source)
        self.assertIn('trackUri.Scheme == Uri.UriSchemeHttps', source)
        self.assertIn('trackUri.Scheme == Uri.UriSchemeHttp', source)
        self.assertIn('AllowedLocalOrigins.Contains(trackUri.Host)', source)
        self.assertIn('if (!string.IsNullOrWhiteSpace(apiKey))', source)
        self.assertIn('Status: string.IsNullOrWhiteSpace(apiKey) ? "forwarded_public" : "forwarded"', source)


if __name__ == "__main__":
    unittest.main()
