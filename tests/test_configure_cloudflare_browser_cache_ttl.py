from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "configure_cloudflare_browser_cache_ttl.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "configure_cloudflare_browser_cache_ttl",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def set_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_EMAIL", "operator@example.test")
    monkeypatch.setenv("CLOUDFLARE_GLOBAL_API_KEY", "secret-key")


def response_for_call(method: str, url: str, setting_value: int) -> tuple[int, dict[str, Any]]:
    if method == "GET" and "/zones?" in url:
        return 200, {
            "success": True,
            "result": [{"id": "a" * 32, "name": "chummer.run", "status": "active"}],
        }
    return 200, {
        "success": True,
        "result": {"id": "browser_cache_ttl", "value": setting_value},
    }


def test_audit_reports_current_four_hour_floor_without_mutating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    set_credentials(monkeypatch)
    calls: list[tuple[str, str, bytes | None]] = []

    def transport(method: str, url: str, headers: dict[str, str], body: bytes | None):
        calls.append((method, url, body))
        assert headers["X-Auth-Key"] == "secret-key"
        return response_for_call(method, url, 14400)

    receipt = module.execute(
        zone_name="chummer.run",
        execute_change=False,
        confirmation="",
        expected_current_value=None,
        receipt_path=None,
        transport=transport,
    )

    assert receipt["status"] == "audit_passed"
    assert receipt["beforeValueSeconds"] == 14400
    assert receipt["postconditionMatched"] is False
    assert receipt["mutationIssued"] is False
    assert [call[0] for call in calls] == ["GET", "GET"]


def test_execute_changes_only_exact_reviewed_value_to_respect_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    set_credentials(monkeypatch)
    calls: list[tuple[str, str, bytes | None]] = []
    reads = iter((14400, 0))

    def transport(method: str, url: str, headers: dict[str, str], body: bytes | None):
        calls.append((method, url, body))
        if method == "GET" and "/zones?" in url:
            return response_for_call(method, url, 0)
        if method == "PATCH":
            return 200, {
                "success": True,
                "result": {"id": "browser_cache_ttl", "value": 0},
            }
        return response_for_call(method, url, next(reads))

    receipt = module.execute(
        zone_name="chummer.run",
        execute_change=True,
        confirmation=module.CONFIRMATION,
        expected_current_value=14400,
        receipt_path=None,
        transport=transport,
    )

    assert receipt["status"] == "updated"
    assert receipt["beforeValueSeconds"] == 14400
    assert receipt["afterValueSeconds"] == 0
    assert receipt["postconditionMatched"] is True
    assert receipt["mutationIssued"] is True
    assert [call[0] for call in calls] == ["GET", "GET", "PATCH", "GET"]
    assert calls[2][2] == b'{"value":0}'


def test_execute_is_idempotent_when_setting_already_respects_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    set_credentials(monkeypatch)
    calls: list[str] = []

    def transport(method: str, url: str, _headers: dict[str, str], _body: bytes | None):
        calls.append(method)
        return response_for_call(method, url, 0)

    receipt = module.execute(
        zone_name="chummer.run",
        execute_change=True,
        confirmation=module.CONFIRMATION,
        expected_current_value=0,
        receipt_path=None,
        transport=transport,
    )

    assert receipt["status"] == "already_compliant"
    assert receipt["mutationIssued"] is False
    assert calls == ["GET", "GET", "GET"]


def test_execute_rejects_value_drift_before_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    set_credentials(monkeypatch)
    calls: list[str] = []

    def transport(method: str, url: str, _headers: dict[str, str], _body: bytes | None):
        calls.append(method)
        return response_for_call(method, url, 7200)

    with pytest.raises(module.BrowserCacheTtlError, match="browser_cache_ttl_precondition_failed"):
        module.execute(
            zone_name="chummer.run",
            execute_change=True,
            confirmation=module.CONFIRMATION,
            expected_current_value=14400,
            receipt_path=None,
            transport=transport,
        )

    assert calls == ["GET", "GET"]


def test_accepted_mutation_leaves_durable_do_not_retry_handoff_when_recheck_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_module()
    set_credentials(monkeypatch)
    receipt_path = tmp_path / "receipt.json"
    setting_reads = 0

    def transport(method: str, url: str, _headers: dict[str, str], _body: bytes | None):
        nonlocal setting_reads
        if method == "GET" and "/zones?" in url:
            return response_for_call(method, url, 0)
        if method == "PATCH":
            return 200, {
                "success": True,
                "result": {"id": "browser_cache_ttl", "value": 0},
            }
        setting_reads += 1
        if setting_reads == 1:
            return response_for_call(method, url, 14400)
        raise module.BrowserCacheTtlError("cloudflare_transport_failed")

    with pytest.raises(module.BrowserCacheTtlError, match="cloudflare_transport_failed"):
        module.execute(
            zone_name="chummer.run",
            execute_change=True,
            confirmation=module.CONFIRMATION,
            expected_current_value=14400,
            receipt_path=receipt_path,
            transport=transport,
        )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "mutation_accepted_verification_pending"
    assert receipt["mutationIssued"] is True
    assert receipt["verificationComplete"] is False
    assert receipt["doNotRetryMutation"] is True
    assert receipt_path.stat().st_mode & 0o777 == 0o600


def test_execute_requires_exact_confirmation_and_precondition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    set_credentials(monkeypatch)

    with pytest.raises(module.BrowserCacheTtlError, match="exact_confirmation_required"):
        module.execute(
            zone_name="chummer.run",
            execute_change=True,
            confirmation="wrong",
            expected_current_value=14400,
            receipt_path=None,
            transport=lambda *_args: pytest.fail("transport must not run"),
        )
    with pytest.raises(module.BrowserCacheTtlError, match="expected_current_value_required"):
        module.execute(
            zone_name="chummer.run",
            execute_change=True,
            confirmation=module.CONFIRMATION,
            expected_current_value=None,
            receipt_path=None,
            transport=lambda *_args: pytest.fail("transport must not run"),
        )


def test_receipt_is_private_and_never_contains_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_module()
    set_credentials(monkeypatch)
    receipt_path = tmp_path / "receipt.json"

    def transport(method: str, url: str, _headers: dict[str, str], _body: bytes | None):
        return response_for_call(method, url, 14400)

    module.execute(
        zone_name="chummer.run",
        execute_change=False,
        confirmation="",
        expected_current_value=None,
        receipt_path=receipt_path,
        transport=transport,
    )

    content = receipt_path.read_text(encoding="utf-8")
    assert "operator@example.test" not in content
    assert "secret-key" not in content
    assert receipt_path.stat().st_mode & 0o777 == 0o600
