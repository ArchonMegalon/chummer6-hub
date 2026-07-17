from __future__ import annotations

import unittest
from pathlib import Path


BLAZOR_GOLD_SCRIPT = Path("/docker/chummercomplete/scripts/release/verify_chummer6_blazor_gold.sh")
RELEASE_READY_SCRIPT = Path("/docker/chummercomplete/scripts/release/verify_chummer6_release_ready.sh")
BLAZOR_FRESHNESS_SCRIPT = Path("/docker/chummercomplete/chummer-presentation/scripts/release/verify_blazor_public_edge_freshness.sh")
BLAZOR_SELF_HOST_FRESHNESS_SCRIPT = Path("/docker/chummercomplete/chummer-presentation/scripts/release/verify_blazor_self_host_workbench_freshness.sh")
BROWSER_SURFACE_PROXY_TIMEOUT_SCRIPT = Path("/docker/chummercomplete/scripts/release/verify_browser_surface_proxy_timeout_posture.sh")


class BlazorGoldReleaseGateTests(unittest.TestCase):
    def test_blazor_gold_script_composes_existing_component_and_public_edge_gates(self) -> None:
        text = BLAZOR_GOLD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("verify_blazor_component_shell", text)
        self.assertIn("cd $root/chummer-presentation && bash scripts/test-blazor-components.sh", text)
        self.assertIn("verify_browser_surface_proxy_timeout_posture", text)
        self.assertIn("bash $root/scripts/release/verify_browser_surface_proxy_timeout_posture.sh", text)
        self.assertIn("verify_blazor_public_edge_workbench_proof", text)
        self.assertIn("blazor-public-edge-workbench-proof-check.sh", text)
        self.assertIn("verify_blazor_public_edge_execution_proof", text)
        self.assertIn("blazor-public-edge-execution-proof-check.sh", text)
        self.assertIn("verify_blazor_play_surface_horizon", text)
        self.assertIn("bash $root/chummer6-ui/scripts/ai/milestones/blazor-play-surface-horizon-check.sh", text)
        self.assertIn("verify_blazor_execution_horizon_bridge", text)
        self.assertIn("cd $root/chummer.run-services && python3 scripts/verify_blazor_execution_horizon_bridge.py", text)
        self.assertIn("verify_blazor_public_edge_freshness", text)
        self.assertIn("verify_blazor_public_edge_freshness.sh", text)
        self.assertIn("CHUMMER_BLAZOR_REQUIRE_LOCAL_E2E", text)
        self.assertIn("cd $root/chummer.run-services && bash scripts/e2e-ui.sh", text)
        self.assertIn("CHUMMER_BLAZOR_REQUIRE_SELF_HOST_E2E", text)
        self.assertIn("cd $root/chummer-presentation && bash scripts/e2e-portal.sh", text)
        self.assertIn("verify_blazor_self_host_workbench_freshness", text)
        self.assertIn("verify_blazor_self_host_workbench_freshness.sh", text)
        self.assertIn('echo "START $name"', text)
        self.assertIn('echo "PASS $name"', text)
        self.assertIn('log_path=/tmp/"$name".blazor-gold.log', text)
        self.assertIn('bash -lc "$cmd" >"$log_path" 2>&1', text)
        self.assertIn("BLAZOR NOT GOLD", text)
        self.assertIn("BLAZOR GOLD", text)

    def test_blazor_public_edge_freshness_script_fail_closes_stale_or_nonpassing_receipts(self) -> None:
        text = BLAZOR_FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("MAX_AGE = 172800", text)
        self.assertIn("BLAZOR_PUBLIC_EDGE_WORKBENCH_PROOF.generated.json", text)
        self.assertIn("BLAZOR_PUBLIC_EDGE_EXECUTION_PROOF.generated.json", text)
        self.assertIn("status is not pass", text)
        self.assertIn("is stale for blazor gold", text)

    def test_blazor_self_host_freshness_script_fail_closes_stale_or_nonpassing_receipt(self) -> None:
        text = BLAZOR_SELF_HOST_FRESHNESS_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("MAX_AGE = 172800", text)
        self.assertIn("BLAZOR_SELF_HOST_WORKBENCH_PROOF.generated.json", text)
        self.assertIn("contract mismatch", text)
        self.assertIn("status is not pass", text)
        self.assertIn("is stale for blazor gold", text)

    def test_browser_surface_proxy_timeout_script_runs_targeted_proxy_and_guardrail_regressions(self) -> None:
        text = BROWSER_SURFACE_PROXY_TIMEOUT_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("dotnet test Chummer.Tests/Chummer.Tests.csproj", text)
        self.assertIn("-c Release", text)
        self.assertIn("-f net10.0", text)
        self.assertIn("-p:RunBrowserSurfaceProxyTimeoutTestsOnly=true", text)
        self.assertIn("FullyQualifiedName~LegacySurfaceRedirectControllerTests", text)
        self.assertIn("FullyQualifiedName~HubApiRequestGuardrailMiddlewareTests", text)
        self.assertIn("FullyQualifiedName~HubApiGuardrailPolicyTests", text)
        self.assertIn("--no-restore", text)

    def test_release_ready_script_always_requires_blazor_gold(self) -> None:
        text = RELEASE_READY_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"verify_chummer6_blazor_gold:bash $root/scripts/release/verify_chummer6_blazor_gold.sh"', text)
        self.assertNotIn('if [[ "${CHUMMER_PUBLIC_REQUIRE_BLAZOR:-0}" =~ ^(1|true|yes|on)$ ]]; then', text)
        self.assertNotIn('gates+=("verify_chummer6_blazor_gold:bash $root/scripts/release/verify_chummer6_blazor_gold.sh")', text)


if __name__ == "__main__":
    unittest.main()
