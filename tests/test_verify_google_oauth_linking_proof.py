from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_google_oauth_linking_proof.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_google_oauth_linking_proof", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT_PATH.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_release(path: Path) -> None:
    write_json(
        path,
        {
            "version": "run-20260713-123603",
            "channelId": "preview",
            "supportabilityState": "review_required",
            "rolloutState": "promoted_preview",
            "publishedAt": "2026-07-13T12:38:14Z",
        },
    )


def current_fail_closed_fixture(module, tmp_path: Path) -> tuple[Path, Path, Path, Path, Path, datetime]:
    evidence = module.evidence_v2
    now = datetime.now(UTC)
    portal = tmp_path / "portal-release.json"
    hub = tmp_path / "hub-release.json"
    live = tmp_path / "live-release.json"
    for path in (portal, hub, live):
        write_release(path)

    release = evidence.release_authority_binding(
        portal_path=portal,
        hub_path=hub,
        live_capture_path=live,
        live_captured_at_utc=evidence.isoformat_utc(now),
    )
    assert release["ready"] is True
    programs = evidence.program_bindings()
    stage_root = tmp_path.resolve()
    request = (stage_root / "operator-request.json").resolve()
    operator_evidence = (stage_root / "operator-evidence.json").resolve()
    receipt = (stage_root / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").resolve()
    template = (stage_root / "operator-template.json").resolve()
    incoming = (stage_root / "incoming").resolve()
    artifact_intake = {
        "dedicated_drop_root": str(incoming),
        "auto_import_roots": [str(incoming)],
        "post_import_argv_plan": evidence.fixed_post_import_argv_plan(
            base_url=evidence.DEFAULT_BASE_URL,
            request_path=request,
            evidence_path=operator_evidence,
            proof_path=receipt,
        ),
    }
    request_payload = {
        "contract_name": evidence.REQUEST_CONTRACT_NAME,
        "generated_at_utc": evidence.isoformat_utc(now),
        "status": "operator_action_required",
        "base_url": evidence.DEFAULT_BASE_URL,
        "request_nonce": "ab" * 32,
        "request_binding_sha256": evidence.request_binding_sha256(
            base_url=evidence.DEFAULT_BASE_URL,
            release=release,
            programs=programs,
        ),
        "release": release,
        "program_bindings": programs,
        "media_policy": evidence.media_policy(),
        "required_steps": list(evidence.REQUIRED_OPERATOR_STEPS),
        "request_receipt_path": str(request),
        "required_output_path": str(operator_evidence),
        "required_receipt_path": str(operator_evidence),
        "required_operator_evidence_path": str(operator_evidence),
        "required_proof_path": str(receipt),
        "template_path": str(template),
        "operator_evidence_template_path": str(template),
        "operator_message_path": str(stage_root / "operator-ask.txt"),
        "operator_ask_text_path": str(stage_root / "operator-ask.txt"),
        "operator_ask_metadata_path": str(stage_root / "operator-ask.json"),
        "preferred_drop_folder": str(incoming),
        "recommended_screenshot_paths": [],
        "materialization_scope": {
            "mode": "staged",
            "root": str(stage_root),
            "self_contained": True,
            "proof_output_path": str(receipt),
        },
        "artifact_intake": artifact_intake,
        "intake": artifact_intake,
    }
    write_json(request, request_payload)

    bindings, binding_failures = evidence.current_proof_bindings(
        request_path=request,
        evidence_path=operator_evidence,
        portal_release_manifest_path=portal,
        hub_release_manifest_path=hub,
        now=now,
    )
    assert not any(item.startswith("request:") for item in binding_failures)
    assert any(item.startswith("evidence:") for item in binding_failures)
    write_json(
        receipt,
        {
            "contract_name": evidence.PROOF_CONTRACT_NAME,
            "proof_contract_version": evidence.PROOF_CONTRACT_VERSION,
            "status": "fail",
            "generated_at_utc": evidence.isoformat_utc(now),
            "base_url": evidence.DEFAULT_BASE_URL,
            "bindings": bindings,
            "quick_handoff_probe": {"pass": True},
            "signed_in_link_handoff": {"status": "operator_required", "pass": False},
            "failures": ["operator evidence is not yet available"],
        },
    )
    return receipt, request, operator_evidence, portal, hub, now


def verify_fixture(module, fixture, *, require_pass: bool = False):
    receipt, request, operator_evidence, portal, hub, now = fixture
    return module.verify(
        receipt,
        require_pass=require_pass,
        request_path=request,
        evidence_path=operator_evidence,
        portal_release_manifest_path=portal,
        hub_release_manifest_path=hub,
        now=now,
    )


def test_verify_v3_receipt_fails_closed_when_operator_evidence_is_missing(tmp_path: Path) -> None:
    module = load_module()
    fixture = current_fail_closed_fixture(module, tmp_path)

    ok, result = verify_fixture(module, fixture)

    assert ok is False
    assert result["status"] == "fail"
    assert result["proof_contract_version"] == module.evidence_v2.PROOF_CONTRACT_VERSION == 3
    assert result["release_authority_ready"] is True
    assert any(item.startswith("evidence: missing regular file:") for item in result["issues"])
    assert "proof bindings do not match current release/request/evidence/program bytes" not in result["issues"]


def test_verify_require_pass_also_rejects_fail_shaped_v3_receipt(tmp_path: Path) -> None:
    module = load_module()
    fixture = current_fail_closed_fixture(module, tmp_path)

    ok, result = verify_fixture(module, fixture, require_pass=True)

    assert ok is False
    assert result["status"] == "fail"
    assert "proof status is not pass" in result["issues"]
    assert "proof receipt contains failures" in result["issues"]
    assert any(item.startswith("evidence: missing regular file:") for item in result["issues"])


def test_verify_rejects_request_argv_authority_tampering(tmp_path: Path) -> None:
    module = load_module()
    fixture = current_fail_closed_fixture(module, tmp_path)
    _receipt, request, _operator_evidence, _portal, _hub, _now = fixture
    payload = module.read_json(request)
    payload["artifact_intake"]["post_import_argv_plan"].append(["sh", "-c", "echo injected"])
    write_json(request, payload)

    ok, result = verify_fixture(module, fixture)

    assert ok is False
    assert result["status"] == "fail"
    assert (
        "request: post_import_argv_plan does not match the release-authority-scoped code-owned plan"
        in result["issues"]
    )
    assert "proof bindings do not match current release/request/evidence/program bytes" in result["issues"]
