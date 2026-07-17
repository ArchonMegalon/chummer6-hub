from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REQUEST_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_google_oauth_linking_operator_evidence_request.py"
VERIFY_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_google_oauth_linking_operator_evidence_request.py"


def load_request_module():
    spec = importlib.util.spec_from_file_location("materialize_google_oauth_linking_operator_evidence_request", REQUEST_SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_verify_module():
    spec = importlib.util.spec_from_file_location("verify_google_oauth_linking_operator_evidence_request", VERIFY_SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_release_channel(path: Path) -> None:
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


def configure_temp_roots(request_module, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        request_module,
        "DEFAULT_OPERATOR_DRAFT_ROOT",
        tmp_path / "_completion" / "google_oauth_linking",
    )
    monkeypatch.setattr(
        request_module,
        "DEFAULT_INCOMING_EVIDENCE_ROOT",
        tmp_path / ".state" / "incoming_google_oauth_linking_operator_evidence",
    )


def materialize_current_request(
    request_module,
    monkeypatch,
    tmp_path: Path,
    *,
    receipt_path: Path | None = None,
    evidence_path: Path | None = None,
) -> tuple[dict, Path, Path, Path, Path]:
    configure_temp_roots(request_module, monkeypatch, tmp_path)
    portal = tmp_path / "portal-release.json"
    hub = tmp_path / "hub-release.json"
    live = tmp_path / "live-release.json"
    for path in (portal, hub, live):
        write_release_channel(path)
    receipt = receipt_path or tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    evidence = evidence_path or tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
    payload = request_module.materialize(
        receipt,
        evidence_path=evidence,
        template_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
        screenshot_root=tmp_path / "screens",
        release_channel_path=portal,
        hub_release_channel_path=hub,
        live_release_manifest_path=live,
    )
    return payload, receipt, evidence, portal, hub


def verify_current_request(verify_module, receipt: Path, portal: Path, hub: Path, *, require_pass: bool = False):
    return verify_module.verify(
        receipt,
        require_pass=require_pass,
        portal_release_manifest_path=portal,
        hub_release_manifest_path=hub,
    )


def test_verify_google_request_passes_when_current_operator_action_is_required(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    payload, receipt, _evidence, portal, hub = materialize_current_request(
        request_module, monkeypatch, tmp_path
    )

    ok, result = verify_current_request(verify_module, receipt, portal, hub)

    assert payload["contract_name"] == request_module.OPERATOR_EVIDENCE_REQUEST_CONTRACT_NAME
    assert payload["contract_name"].endswith("request.v2")
    assert ok is True
    assert result["status"] == "pass"
    assert result["request_status"] == "operator_action_required"
    assert result["operator_action_still_required"] is True
    assert result["release_authority_ready"] is True
    assert result["program_bindings"]
    assert result["issues"] == []


def test_materialize_rejects_non_production_base_url(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    configure_temp_roots(request_module, monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="must be https://chummer.run"):
        request_module.materialize(
            tmp_path / "request.json",
            base_url="https://ops.example.test",
            evidence_path=tmp_path / "evidence.json",
            template_path=tmp_path / "template.json",
            screenshot_root=tmp_path / "screens",
            release_channel_path=tmp_path / "portal.json",
        )


def test_unverified_legacy_evidence_does_not_suppress_operator_request(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    evidence = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
    write_json(
        evidence,
        {
            "contract_name": request_module.OPERATOR_EVIDENCE_CONTRACT_NAME,
            "status": "pass",
            "base_url": request_module.DEFAULT_BASE_URL,
            "verified_steps": list(request_module.REQUIRED_OPERATOR_STEPS),
            "screenshot_paths": ["one.png", "two.png"],
        },
    )
    payload, receipt, _evidence, portal, hub = materialize_current_request(
        request_module,
        monkeypatch,
        tmp_path,
        evidence_path=evidence,
    )

    ok, result = verify_current_request(verify_module, receipt, portal, hub)

    assert ok is True
    assert payload["status"] == "operator_action_required"
    assert result["operator_action_still_required"] is True


def test_verify_rejects_tampered_not_required_status(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    payload, receipt, _evidence, portal, hub = materialize_current_request(
        request_module, monkeypatch, tmp_path
    )
    payload["status"] = "not_required"
    write_json(receipt, payload)

    ok, result = verify_current_request(verify_module, receipt, portal, hub)

    assert ok is False
    assert result["status"] == "fail"
    assert result["request_status"] == "not_required"
    assert result["operator_action_still_required"] is False
    assert "status must be operator_action_required for the current release authority state" in result["issues"]


def test_verify_require_pass_accepts_current_actionable_request(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    _payload, receipt, _evidence, portal, hub = materialize_current_request(
        request_module, monkeypatch, tmp_path
    )

    ok, result = verify_current_request(
        verify_module, receipt, portal, hub, require_pass=True
    )

    assert ok is True
    assert result["status"] == "pass"
    assert result["request_status"] == "operator_action_required"
    assert result["operator_action_still_required"] is True
    assert result["issues"] == []


def test_verify_rejects_retired_shell_command_authority(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    payload, receipt, _evidence, portal, hub = materialize_current_request(
        request_module, monkeypatch, tmp_path
    )
    payload["post_import_gates"] = [
        "python3 scripts/tool.py --base-url http://127.0.0.1:8091"
    ]
    write_json(receipt, payload)

    ok, result = verify_current_request(verify_module, receipt, portal, hub)

    assert ok is False
    assert result["status"] == "fail"
    assert "post_import_gates is forbidden; shell commands are not intake authority" in result["issues"]


def test_verify_malformed_receipt_fails_closed_without_crashing(tmp_path: Path) -> None:
    verify_module = load_verify_module()
    receipt = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    receipt.write_text("{\n", encoding="utf-8")

    ok, result = verify_module.verify(receipt, require_pass=False)

    assert ok is False
    assert result["status"] == "fail"
    assert result["request_status"] == "missing"
    assert result["operator_action_still_required"] is False
    assert result["issues"] == [f"invalid JSON object: {receipt}"]


def test_verify_rejects_tampered_code_owned_argv_plan(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    payload, receipt, _evidence, portal, hub = materialize_current_request(
        request_module, monkeypatch, tmp_path
    )
    payload["artifact_intake"]["post_import_argv_plan"][0].append("--injected")
    write_json(receipt, payload)

    ok, result = verify_current_request(verify_module, receipt, portal, hub)

    assert ok is False
    assert result["status"] == "fail"
    assert (
        "post_import_argv_plan does not match the release-authority-scoped code-owned plan"
        in result["issues"]
    )


def test_retired_operator_ask_metadata_is_not_request_verifier_authority(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    payload, receipt, _evidence, portal, hub = materialize_current_request(
        request_module, monkeypatch, tmp_path
    )
    Path(payload["operator_ask_metadata_path"]).write_text("{\n", encoding="utf-8")

    ok, result = verify_current_request(verify_module, receipt, portal, hub)

    assert ok is True
    assert result["status"] == "pass"
    assert result["issues"] == []


def test_verify_rejects_appended_release_wrapper_argv(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    payload, receipt, _evidence, portal, hub = materialize_current_request(
        request_module, monkeypatch, tmp_path
    )
    payload["artifact_intake"]["post_import_argv_plan"].append(
        ["python3", "scripts/materialize_operator_release_dashboard.py"]
    )
    write_json(receipt, payload)

    ok, result = verify_current_request(verify_module, receipt, portal, hub)

    assert ok is False
    assert result["status"] == "fail"
    assert (
        "post_import_argv_plan does not match the release-authority-scoped code-owned plan"
        in result["issues"]
    )


def test_verify_accepts_relative_receipt_path_from_repo_cwd(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    configure_temp_roots(request_module, monkeypatch, tmp_path)
    portal = tmp_path / "portal-release.json"
    hub = tmp_path / "hub-release.json"
    live = tmp_path / "live-release.json"
    for path in (portal, hub, live):
        write_release_channel(path)
    monkeypatch.chdir(tmp_path)
    receipt = Path("GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json")
    request_module.materialize(
        receipt,
        evidence_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json",
        template_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
        screenshot_root=tmp_path / "screens",
        release_channel_path=portal,
        hub_release_channel_path=hub,
        live_release_manifest_path=live,
    )

    ok, result = verify_current_request(verify_module, receipt, portal, hub)

    assert ok is True
    assert result["status"] == "pass"
    assert result["issues"] == []


def test_blocked_request_is_current_but_has_no_executable_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    configure_temp_roots(request_module, monkeypatch, tmp_path)
    portal = tmp_path / "portal-release.json"
    hub = tmp_path / "hub-release.json"
    write_json(
        portal,
        {
            "version": "run-20260713-123603",
            "channelId": "preview",
            "supportabilityState": "preview_supported",
            "rolloutState": "promoted_preview",
            "publishedAt": "2026-07-13T12:38:14Z",
        },
    )
    write_json(
        hub,
        {
            "version": "run-20260712-174412",
            "channelId": "preview",
            "supportabilityState": "preview_supported",
            "rolloutState": "promoted_preview",
            "publishedAt": "2026-07-12T18:46:26Z",
        },
    )
    receipt = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    payload = request_module.materialize(
        receipt,
        release_channel_path=portal,
        hub_release_channel_path=hub,
    )

    ok, result = verify_current_request(verify_module, receipt, portal, hub)

    assert ok is False
    assert result["request_status"] == "blocked_release_authority"
    assert result["issues"] == [
        "release_authority: portal_and_hub_release_identity_disagree",
        "release_authority: live_release_manifest_not_captured",
    ]
    assert payload["artifact_intake"]["discover_command"] == ""
    assert payload["artifact_intake"]["import_argv"] == []
    assert payload["artifact_intake"]["auto_import_argv"] == []
    assert payload["artifact_intake"]["auto_import_watch_argv"] == []
    assert payload["artifact_intake"]["post_import_argv_plan"] == []
    assert payload["operator_telegram_draft"]["send_command"] == ""
    assert payload["operator_telegram_draft_materialized"]["send_command"] == ""
    assert payload["recovery"]["execution_authority_present"] is False


@pytest.mark.parametrize(
    ("surface", "unexpected"),
    [
        ("draft_send", "unexpected-send-authority"),
        ("auto_import", ["unexpected-auto-import-authority"]),
        ("post_import", [["unexpected-post-import-authority"]]),
    ],
)
def test_verify_rejects_executable_authority_in_blocked_request(
    tmp_path: Path,
    monkeypatch,
    surface: str,
    unexpected: object,
) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    configure_temp_roots(request_module, monkeypatch, tmp_path)
    portal = tmp_path / "portal-release.json"
    hub = tmp_path / "hub-release.json"
    write_json(
        portal,
        {
            "version": "run-new",
            "channelId": "preview",
            "supportabilityState": "preview_supported",
            "rolloutState": "promoted_preview",
            "publishedAt": "2026-07-13T12:38:14Z",
        },
    )
    write_json(
        hub,
        {
            "version": "run-old",
            "channelId": "preview",
            "supportabilityState": "preview_supported",
            "rolloutState": "promoted_preview",
            "publishedAt": "2026-07-12T18:46:26Z",
        },
    )
    receipt = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    payload = request_module.materialize(
        receipt,
        release_channel_path=portal,
        hub_release_channel_path=hub,
    )
    if surface == "draft_send":
        payload["operator_telegram_draft"]["send_command"] = unexpected
    elif surface == "auto_import":
        payload["artifact_intake"]["auto_import_argv"] = unexpected
        payload["intake"] = payload["artifact_intake"]
    else:
        payload["artifact_intake"]["post_import_argv_plan"] = unexpected
        payload["intake"] = payload["artifact_intake"]
    write_json(receipt, payload)

    ok, result = verify_current_request(verify_module, receipt, portal, hub)

    assert ok is False
    assert any("must be empty while release authority is blocked" in issue for issue in result["issues"])


def test_verify_rejects_canonical_proof_target_from_staged_request(
    tmp_path: Path,
    monkeypatch,
) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    payload, receipt, _evidence, portal, hub = materialize_current_request(
        request_module,
        monkeypatch,
        tmp_path,
    )
    canonical_proof = request_module.evidence_v2.DEFAULT_PROOF_PATH.resolve()
    payload["required_proof_path"] = str(canonical_proof)
    payload["materialization_scope"]["proof_output_path"] = str(canonical_proof)
    payload["artifact_intake"]["post_import_argv_plan"] = request_module.post_import_argv_plan(
        request_module.DEFAULT_BASE_URL,
        request_path=receipt.resolve(),
        evidence_path=Path(payload["required_operator_evidence_path"]),
        proof_path=canonical_proof,
    )
    payload["intake"] = payload["artifact_intake"]
    write_json(receipt, payload)

    ok, result = verify_current_request(verify_module, receipt, portal, hub)

    assert ok is False
    assert "noncanonical request must not target the canonical proof output" in result["issues"]
    assert "required_proof_path escapes the noncanonical request stage root" in result["issues"]
