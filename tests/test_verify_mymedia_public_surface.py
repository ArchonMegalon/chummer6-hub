from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_mymedia_public_surface.py"


def _module():
    spec = importlib.util.spec_from_file_location("verify_mymedia_public_surface", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def passing_receipt() -> dict[str, object]:
    return {
        "contract_name": "chummer.ea_mymedia_public_surface.v1",
        "generated_at_utc": "2026-07-04T20:33:27Z",
        "updated_at": "2026-07-04T20:33:27Z",
        "observed_at": "2026-07-04T20:33:27Z",
        "status": "pass",
        "structural_status": "pass",
        "effective_status": "access_protected",
        "runtime_status": "ready",
        "runtime_ready": True,
        "source": "script:ea_live_ops.py",
        "source_runtime": "ea_live_ops.bridge",
        "probe_payload_present": True,
        "probe_ok": True,
        "secret_leak_detected": False,
        "blocking_count": 0,
        "advisory_count": 0,
        "blocking_findings": [],
        "advisory_findings": [],
        "public_surface_configured": True,
        "public_surface_ready": True,
        "public_surface_status": "access_protected",
        "public_surface_reason": "",
        "public_surface_url": "https://mymedia.girschele.com",
        "public_surface_scope": "public",
        "public_surface_http_status_code": 302,
        "public_surface_access_protected": True,
        "public_surface_cloudflare_blocked": False,
        "public_surface_redirect_host": "girschele.cloudflareaccess.com",
        "next_action": "",
        "mymedia_status": "ready_library_scan_in_progress",
    }


def test_verify_passes_structurally_for_ready_surface(tmp_path: Path) -> None:
    module = _module()
    receipt_path = tmp_path / "MYMEDIA_PUBLIC_SURFACE.generated.json"
    receipt_path.write_text(json.dumps(passing_receipt()), encoding="utf-8")

    passed, result = module.verify(receipt_path)

    assert passed is True
    assert result["status"] == "pass"
    assert result["structural_status"] == "pass"
    assert result["effective_status"] == "access_protected"
    assert result["surface_status"] == "access_protected"


def test_verify_derives_runtime_fields_for_legacy_receipt(tmp_path: Path) -> None:
    module = _module()
    payload = passing_receipt()
    payload.pop("runtime_status", None)
    payload.pop("runtime_ready", None)
    receipt_path = tmp_path / "MYMEDIA_PUBLIC_SURFACE.generated.json"
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    passed, result = module.verify(receipt_path)

    assert passed is True
    assert result["status"] == "pass"
    assert result["runtime_status"] == "ready"
    assert result["runtime_ready"] is True


def test_verify_can_pass_structurally_when_surface_is_not_ready(tmp_path: Path) -> None:
    module = _module()
    payload = passing_receipt()
    payload.update(
        {
            "status": "fail",
            "structural_status": "fail",
            "effective_status": "blocked_by_cloudflare",
            "runtime_status": "blocked",
            "runtime_ready": False,
            "probe_ok": False,
            "blocking_count": 1,
            "advisory_count": 0,
            "blocking_findings": ["mymedia_public_console_blocked_by_cloudflare"],
            "advisory_findings": [],
            "public_surface_ready": False,
            "public_surface_status": "blocked_by_cloudflare",
            "public_surface_reason": "mymedia_public_console_blocked_by_cloudflare",
            "public_surface_access_protected": False,
            "public_surface_http_status_code": 403,
            "public_surface_cloudflare_blocked": True,
            "next_action": "repair_mymedia_public_console_route",
        }
    )
    receipt_path = tmp_path / "MYMEDIA_PUBLIC_SURFACE.generated.json"
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    passed, result = module.verify(receipt_path)

    assert passed is True
    assert result["status"] == "pass"
    assert result["surface_ready"] is False
    assert result["surface_status"] == "blocked_by_cloudflare"


def test_verify_require_pass_fails_when_surface_is_not_ready(tmp_path: Path) -> None:
    module = _module()
    payload = passing_receipt()
    payload.update(
        {
            "status": "fail",
            "structural_status": "fail",
            "effective_status": "blocked_by_cloudflare",
            "runtime_status": "blocked",
            "runtime_ready": False,
            "probe_ok": False,
            "blocking_count": 1,
            "advisory_count": 0,
            "blocking_findings": ["mymedia_public_console_blocked_by_cloudflare"],
            "advisory_findings": [],
            "public_surface_ready": False,
            "public_surface_status": "blocked_by_cloudflare",
            "public_surface_reason": "mymedia_public_console_blocked_by_cloudflare",
            "public_surface_access_protected": False,
            "public_surface_http_status_code": 403,
            "public_surface_cloudflare_blocked": True,
            "next_action": "repair_mymedia_public_console_route",
        }
    )
    receipt_path = tmp_path / "MYMEDIA_PUBLIC_SURFACE.generated.json"
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    passed, result = module.verify(receipt_path, require_pass=True)

    assert passed is False
    assert result["status"] == "fail"
    assert "receipt_status_not_pass" in result["issues"]
    assert "public_surface_not_ready" in result["issues"]
    assert "public_surface_status_not_allowed" in result["issues"]


def test_verify_fails_when_structural_and_effective_status_are_missing(tmp_path: Path) -> None:
    module = _module()
    payload = passing_receipt()
    payload.pop("structural_status", None)
    payload.pop("effective_status", None)
    payload.pop("updated_at", None)
    receipt_path = tmp_path / "MYMEDIA_PUBLIC_SURFACE.generated.json"
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    passed, result = module.verify(receipt_path)

    assert passed is False
    assert result["status"] == "fail"
    assert "updated_at_missing" in result["issues"]
    assert "structural_status_mismatch" in result["issues"]
    assert "effective_status_mismatch" in result["issues"]


def test_verify_fails_when_public_surface_url_is_unsanitized_loopback(tmp_path: Path) -> None:
    module = _module()
    payload = passing_receipt()
    payload["public_surface_url"] = "http://127.0.0.1:52051/index.html#!/tables"
    receipt_path = tmp_path / "MYMEDIA_PUBLIC_SURFACE.generated.json"
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    passed, result = module.verify(receipt_path)

    assert passed is False
    assert result["status"] == "fail"
    assert "public_surface_url_not_sanitized" in result["issues"]


def test_verify_fails_when_source_or_stdout_source_is_unsanitized(tmp_path: Path) -> None:
    module = _module()
    payload = passing_receipt()
    payload["source"] = "/docker/EA/scripts/ea_live_ops.py"
    payload["stdout_tail"] = "returncode=0 observed_at=2026-07-04T20:33:27Z source=/docker/EA/scripts/probe_mymedia_alexa.py"
    receipt_path = tmp_path / "MYMEDIA_PUBLIC_SURFACE.generated.json"
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    passed, result = module.verify(receipt_path)

    assert passed is False
    assert result["status"] == "fail"
    assert "source_mismatch" in result["issues"]
    assert "stdout_tail_source_not_sanitized" in result["issues"]


def test_verify_fails_structurally_when_receipt_is_missing(tmp_path: Path) -> None:
    module = _module()
    receipt_path = tmp_path / "MYMEDIA_PUBLIC_SURFACE.generated.json"

    passed, result = module.verify(receipt_path)

    assert passed is False
    assert result["status"] == "fail"
    assert result["issues"] == ["missing_receipt"]
    assert result["structural_status"] == "missing"
    assert result["effective_status"] == "missing"
