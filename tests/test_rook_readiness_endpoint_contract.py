from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "Chummer.Run.AI/Controllers/BuildGhostController.cs"


def test_rook_readiness_is_private_and_fail_closed() -> None:
    source = CONTROLLER.read_text(encoding="utf-8")
    assert '[HttpGet("readiness")]' in source
    assert "BuildGhostPrivateToolDeploymentContract.FromConfiguration" in source
    assert "BuildGhostPrivateToolAuthorityClient.AuthorityEndpointConfigurationKey" in source
    assert "BuildGhostPrivateToolAuthorityClient.ServiceTokenConfigurationKey" in source
    assert "serviceToken.Length < 32" in source
    assert "StatusCodes.Status503ServiceUnavailable" in source
    assert 'Response.Headers.CacheControl = "no-store"' in source
    assert "remoteExecutionEnabled = deployment.Package.RemoteExecutionEnabled" in source
