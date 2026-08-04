from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "purge_cloudflare_zone_urls.py"


def load_module():
    spec = importlib.util.spec_from_file_location("purge_cloudflare_zone_urls", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def set_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_EMAIL", "operator@example.test")
    monkeypatch.setenv("CLOUDFLARE_GLOBAL_API_KEY", "secret-key")


def test_audit_resolves_one_active_zone_without_mutating(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    set_credentials(monkeypatch)
    calls: list[tuple[str, str, bytes | None]] = []

    def transport(method: str, url: str, headers: dict[str, str], body: bytes | None):
        calls.append((method, url, body))
        assert headers["X-Auth-Key"] == "secret-key"
        return 200, {
            "success": True,
            "result": [{"id": "a" * 32, "name": "chummer.run", "status": "active"}],
        }

    receipt = module.execute(
        zone_name="chummer.run",
        urls=["https://chummer.run/mobile.css"],
        execute_purge=False,
        confirmation="",
        receipt_path=None,
        transport=transport,
    )

    assert receipt["status"] == "audit_passed"
    assert receipt["purgeIssued"] is False
    assert len(calls) == 1
    assert calls[0][0] == "GET"


def test_execute_purges_only_exact_validated_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    set_credentials(monkeypatch)
    calls: list[tuple[str, str, bytes | None]] = []

    def transport(method: str, url: str, headers: dict[str, str], body: bytes | None):
        calls.append((method, url, body))
        if method == "GET":
            return 200, {
                "success": True,
                "result": [{"id": "b" * 32, "name": "chummer.run", "status": "active"}],
            }
        return 200, {"success": True, "result": {"id": "b" * 32}}

    urls = [
        "https://chummer.run/mobile.css",
        "https://chummer.run/service-worker.js",
    ]
    receipt = module.execute(
        zone_name="chummer.run",
        urls=urls,
        execute_purge=True,
        confirmation=module.CONFIRMATION,
        receipt_path=None,
        transport=transport,
    )

    assert receipt["status"] == "purged"
    assert receipt["urls"] == urls
    assert [call[0] for call in calls] == ["GET", "POST"]
    assert calls[1][2] == b'{"files":["https://chummer.run/mobile.css","https://chummer.run/service-worker.js"]}'


@pytest.mark.parametrize(
    "url",
    (
        "http://chummer.run/mobile.css",
        "https://www.chummer.run/mobile.css",
        "https://chummer.run/mobile.css?token=private",
        "https://chummer.run/mobile.css#fragment",
        "https://user@chummer.run/mobile.css",
        "https://chummer.run:invalid/mobile.css",
    ),
)
def test_url_validation_rejects_non_exact_or_non_zone_urls(url: str) -> None:
    module = load_module()

    with pytest.raises(module.PurgeError, match="purge_url_invalid"):
        module.normalize_urls([url], "chummer.run")


def test_execute_requires_exact_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    set_credentials(monkeypatch)

    with pytest.raises(module.PurgeError, match="exact_confirmation_required"):
        module.execute(
            zone_name="chummer.run",
            urls=["https://chummer.run/mobile.css"],
            execute_purge=True,
            confirmation="wrong",
            receipt_path=None,
            transport=lambda *_args: pytest.fail("transport must not run"),
        )


def test_receipt_never_contains_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = load_module()
    set_credentials(monkeypatch)
    receipt_path = tmp_path / "receipt.json"

    def transport(method: str, _url: str, _headers: dict[str, str], _body: bytes | None):
        assert method == "GET"
        return 200, {
            "success": True,
            "result": [{"id": "c" * 32, "name": "chummer.run", "status": "active"}],
        }

    module.execute(
        zone_name="chummer.run",
        urls=["https://chummer.run/mobile.css"],
        execute_purge=False,
        confirmation="",
        receipt_path=receipt_path,
        transport=transport,
    )

    content = receipt_path.read_text(encoding="utf-8")
    assert "operator@example.test" not in content
    assert "secret-key" not in content
    assert receipt_path.stat().st_mode & 0o777 == 0o600
