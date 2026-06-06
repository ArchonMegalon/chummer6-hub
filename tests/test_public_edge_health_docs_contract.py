from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROGRAM = REPO_ROOT / "Chummer.Run.Api" / "Program.cs"


def test_public_edge_serves_health_and_self_hosted_docs_without_external_assets() -> None:
    source = PROGRAM.read_text(encoding="utf-8")

    assert 'app.MapGet("/api/health"' in source
    assert 'app.MapGet("/openapi/", GetSelfHostedDocs);' in source
    assert "Self-hosted OpenAPI explorer" in source
    assert "jsdelivr" not in source.lower()
