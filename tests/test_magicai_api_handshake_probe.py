from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "materialize_magicai_api_handshake_probe.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_magicai_api_handshake_probe", MODULE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_materialize_blocks_when_no_magicai_api_key_is_configured(tmp_path: Path) -> None:
    module = load_module()
    (tmp_path / ".env").write_text("MAGICAI_ACCOUNT_02_EMAIL=two@example.test\n", encoding="utf-8")
    output = tmp_path / "MAGICAI_API_HANDSHAKE.generated.json"

    payload = module.materialize(repo_root=tmp_path, output=output)

    assert payload["status"] == "blocked"
    assert payload["errors"] == ["magicai_api_key_missing"]
    assert payload["controlledLiveProviderPilot"] is False
    assert "two@example.test" not in output.read_text(encoding="utf-8")


def test_materialize_summarizes_schema_probe_without_exposing_api_key(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    secret = "ak_test_secret_1234567890"
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MAGICAI_ACCOUNT_03_API_KEY=" + secret,
                "",
            ]
        ),
        encoding="utf-8",
    )

    def fake_fetch_probe(request, timeout: int = 60):
        assert request.get_header("X-api-key") == secret
        return {
            "status_code": 200,
            "headers": {
                "Content-Type": "application/json",
                "Allow": "GET, HEAD, OPTIONS",
                "WWW-Authenticate": "X-Api-Key",
            },
            "url": "https://api.omagic.ai/api/schema/public/?format=json",
            "body": json.dumps(
                {
                    "openapi": "3.0.3",
                    "paths": {
                        "/api/templates/": {"get": {}},
                        "/api/jobs/": {"post": {}},
                    },
                    "components": {"securitySchemes": {"ApiKeyAuth": {"type": "apiKey"}}},
                }
            ),
        }

    monkeypatch.setattr(module, "fetch_probe", fake_fetch_probe)
    output = tmp_path / "MAGICAI_API_HANDSHAKE.generated.json"

    payload = module.materialize(repo_root=tmp_path, output=output, requested_slot="03")

    assert payload["status"] == "pass"
    assert payload["slot"] == "03"
    assert payload["controlledLiveProviderPilot"] is True
    assert payload["summary"]["json"] is True
    assert payload["summary"]["path_count"] == 2
    assert payload["summary"]["sample_paths"] == ["/api/jobs/", "/api/templates/"]
    serialized = output.read_text(encoding="utf-8")
    assert secret not in serialized
