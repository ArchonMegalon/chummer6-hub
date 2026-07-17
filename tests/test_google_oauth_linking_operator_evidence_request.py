from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from unittest import mock

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_google_oauth_linking_operator_evidence_request.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "materialize_google_oauth_linking_operator_evidence_request",
        SCRIPT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_release(path: Path, *, version: str, published_at: str) -> None:
    path.write_text(
        json.dumps(
            {
                "version": version,
                "channelId": "preview",
                "supportabilityState": "preview_supported",
                "rolloutState": "promoted_preview",
                "publishedAt": published_at,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def configure_temp_roots(module, monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    draft_root = tmp_path / "completion" / "google_oauth_linking"
    incoming_root = tmp_path / "state" / "incoming_google_oauth_linking_operator_evidence"
    template = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json"
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_DRAFT_ROOT", draft_root)
    monkeypatch.setattr(module, "DEFAULT_INCOMING_EVIDENCE_ROOT", incoming_root)
    return draft_root, incoming_root, template


def test_materialize_blocks_disagreeing_release_authorities_without_actionable_commands(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    draft_root, incoming_root, template = configure_temp_roots(module, monkeypatch, tmp_path)
    portal = tmp_path / "portal-release.json"
    hub = tmp_path / "hub-release.json"
    write_release(portal, version="run-20260713-123603", published_at="2026-07-13T12:38:14Z")
    write_release(hub, version="run-20260712-174412", published_at="2026-07-12T18:46:26Z")
    output = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    evidence = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"

    payload = module.materialize(
        output,
        evidence_path=evidence,
        template_path=template,
        screenshot_root=tmp_path / "screens",
        release_channel_path=portal,
        hub_release_channel_path=hub,
    )

    assert payload["contract_name"].endswith("request.v2")
    assert payload["status"] == "blocked_release_authority"
    assert payload["release"]["ready"] is False
    assert "portal_and_hub_release_identity_disagree" in payload["release"]["blockers"]
    assert "live_release_manifest_not_captured" in payload["release"]["blockers"]
    assert len(payload["request_nonce"]) == 64
    assert payload["send_command"] == ""
    assert payload["import_argv"] == []
    assert payload["artifact_intake"]["import_argv"] == []
    assert payload["artifact_intake"]["discover_command"] == ""
    assert payload["artifact_intake"]["auto_import_argv"] == []
    assert payload["artifact_intake"]["auto_import_watch_argv"] == []
    assert payload["artifact_intake"]["post_import_argv_plan"] == []
    assert "post_import_commands" not in payload["artifact_intake"]
    assert "post_import_gates" not in payload
    assert payload["operator_telegram_draft"]["status"] == "blocked_not_sendable"
    assert payload["operator_telegram_draft"]["send_command"] == ""
    assert payload["operator_telegram_draft_materialized"]["send_command"] == ""
    assert payload["recovery"]["execution_authority_present"] is False
    assert payload["recovery"]["release_authority_blockers"] == payload["release"]["blockers"]
    assert payload["recovery"]["required_conditions"]
    assert payload["materialization_scope"]["mode"] == "staged"
    assert payload["materialization_scope"]["self_contained"] is True
    assert Path(payload["required_proof_path"]).is_relative_to(tmp_path)
    assert "Do not capture, package, import, or send" in payload["operator_telegram_draft"]["message_text"]
    assert output.is_file()
    assert incoming_root.is_dir()
    assert (draft_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt").is_file()
    template_payload = json.loads(template.read_text(encoding="utf-8"))
    assert template_payload["contract_name"].endswith("evidence.v2")
    assert template_payload["request_nonce"] == payload["request_nonce"]
    assert template_payload["screenshots"]


def test_request_nonce_and_raw_bytes_are_stable_only_for_exact_release_and_program_bindings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    _draft_root, _incoming_root, template = configure_temp_roots(module, monkeypatch, tmp_path)
    portal = tmp_path / "portal-release.json"
    hub = tmp_path / "hub-release.json"
    live = tmp_path / "live-release.json"
    for path in (portal, hub, live):
        write_release(path, version="run-20260713-123603", published_at="2026-07-13T12:38:14Z")
    output = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    evidence = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
    real_bindings = module.evidence_v2.program_bindings()
    monkeypatch.setattr(module.evidence_v2, "program_bindings", lambda: real_bindings)

    first = module.materialize(
        output,
        evidence_path=evidence,
        template_path=template,
        screenshot_root=tmp_path / "screens",
        release_channel_path=portal,
        hub_release_channel_path=hub,
        live_release_manifest_path=live,
    )
    first_raw_sha = hashlib.sha256(output.read_bytes()).hexdigest()
    second = module.materialize(
        output,
        evidence_path=evidence,
        template_path=template,
        screenshot_root=tmp_path / "screens",
        release_channel_path=portal,
        hub_release_channel_path=hub,
    )
    assert first["status"] == "operator_action_required"
    assert first["request_nonce"] == second["request_nonce"]
    assert first["generated_at_utc"] == second["generated_at_utc"]
    assert hashlib.sha256(output.read_bytes()).hexdigest() == first_raw_sha

    drifted = json.loads(json.dumps(real_bindings))
    drifted["proof_verifier"]["sha256"] = "f" * 64
    monkeypatch.setattr(module.evidence_v2, "program_bindings", lambda: drifted)
    third = module.materialize(
        output,
        evidence_path=evidence,
        template_path=template,
        screenshot_root=tmp_path / "screens",
        release_channel_path=portal,
        hub_release_channel_path=hub,
        live_release_manifest_path=live,
    )
    assert third["request_nonce"] != second["request_nonce"]
    assert third["request_binding_sha256"] != second["request_binding_sha256"]


def test_build_request_rebinds_operator_ask_paths_to_patched_draft_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    draft_root = tmp_path / "completion" / "google_oauth_linking"
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_DRAFT_ROOT", draft_root)
    release = {
        "ready": False,
        "blockers": ["live_release_manifest_not_captured"],
        "portal": {},
        "hub_registry": {},
        "live": {"status": "not_captured"},
    }
    request = module.build_request(
        tmp_path / "request.json",
        module.DEFAULT_BASE_URL,
        tmp_path / "evidence.json",
        tmp_path / "template.json",
        [tmp_path / "one.png", tmp_path / "two.png"],
        {
            "path": str(tmp_path / "portal.json"),
            "version": "run-test",
            "channel": "preview",
            "supportability_state": "review_required",
            "rollout_state": "promoted_preview",
            "published_at": "2026-07-13T12:38:14Z",
            "authority": release,
        },
        proof_path=tmp_path / "proof.json",
        operator_draft_root=draft_root,
        materialization_scope={
            "mode": "staged",
            "root": str(tmp_path),
            "self_contained": True,
            "proof_output_path": str(tmp_path / "proof.json"),
        },
        request_status="blocked_release_authority",
        program_bindings=module.evidence_v2.program_bindings(),
    )
    assert request["operator_ask_text_path"].startswith(str(draft_root))
    assert request["operator_ask_metadata_path"].startswith(str(draft_root))


def test_artifact_discovery_roots_include_common_operator_sync_locations(tmp_path: Path) -> None:
    module = load_module()
    home = tmp_path / "home"
    incoming_root = tmp_path / "incoming"
    with mock.patch("pathlib.Path.home", return_value=home), mock.patch(
        "tempfile.gettempdir", return_value="/tmp"
    ):
        roots = module.artifact_discovery_roots(incoming_root)
    assert roots == [incoming_root, Path("/tmp"), home / "Downloads", home / "pCloud Drive" / "EA"]


def test_noncanonical_output_cli_defaults_are_self_contained_and_non_executable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    stage_root = tmp_path / "stage"
    output = stage_root / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    forbidden_root = tmp_path / "must-not-write"
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_EVIDENCE_PATH", forbidden_root / "evidence.json")
    monkeypatch.setattr(module, "DEFAULT_TEMPLATE_PATH", forbidden_root / "template.json")
    monkeypatch.setattr(module, "DEFAULT_SCREENSHOT_ROOT", forbidden_root / "screens")
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_DRAFT_ROOT", forbidden_root / "draft")
    monkeypatch.setattr(module, "DEFAULT_INCOMING_EVIDENCE_ROOT", forbidden_root / "incoming")
    monkeypatch.setattr(module, "DEFAULT_PROOF_PATH", forbidden_root / "proof.json")
    portal = tmp_path / "portal-release.json"
    hub = tmp_path / "hub-release.json"
    write_release(portal, version="run-20260713-123603", published_at="2026-07-13T12:38:14Z")
    write_release(hub, version="run-20260712-174412", published_at="2026-07-12T18:46:26Z")
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            str(SCRIPT_PATH),
            "--output",
            str(output),
            "--release-channel-path",
            str(portal),
            "--hub-release-channel-path",
            str(hub),
        ],
    )

    assert module.main() == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert forbidden_root.exists() is False
    assert payload["status"] == "blocked_release_authority"
    assert payload["materialization_scope"] == {
        "mode": "staged",
        "root": str(stage_root.resolve()),
        "self_contained": True,
        "proof_output_path": str((stage_root / "proof.json").resolve()),
    }
    staged_paths = [
        payload["request_receipt_path"],
        payload["required_operator_evidence_path"],
        payload["required_proof_path"],
        payload["template_path"],
        payload["operator_ask_text_path"],
        payload["operator_ask_metadata_path"],
        payload["preferred_drop_folder"],
        payload["artifact_intake"]["dedicated_drop_root"],
        *payload["recommended_screenshot_paths"],
        *payload["artifact_intake"]["auto_import_roots"],
    ]
    assert all(Path(value).is_relative_to(stage_root.resolve()) for value in staged_paths)
    assert payload["artifact_intake"]["post_import_argv_plan"] == []
    assert payload["operator_telegram_draft"]["send_command"] == ""


def test_noncanonical_output_rejects_explicit_companion_escape(tmp_path: Path) -> None:
    module = load_module()
    output = tmp_path / "stage" / "request.json"

    with pytest.raises(ValueError, match="companion escapes stage root"):
        module.materialize(
            output,
            evidence_path=tmp_path / "outside" / "evidence.json",
        )
