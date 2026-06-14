from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
LAYOUT_PATH = REPO_ROOT / "Chummer.Run.Api" / "Views" / "Shared" / "_Layout.cshtml"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
PUBLIC_EDGE_COMPOSE_PATH = REPO_ROOT / "docker-compose.public-edge.yml"


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


if __name__ == "__main__":
    unittest.main()
