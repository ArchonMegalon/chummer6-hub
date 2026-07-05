from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REQUEST_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_google_oauth_linking_operator_evidence_request.py"
VERIFY_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_google_oauth_linking_operator_evidence_request.py"
PROOF_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_google_oauth_linking_proof.py"


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


def load_proof_module():
    spec = importlib.util.spec_from_file_location("materialize_google_oauth_linking_proof", PROOF_SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_release_channel(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": "run-20260704-170602",
                "channelId": "preview",
                "supportabilityState": "preview_supported",
                "rolloutState": "promoted_preview",
                "publishedAt": "2026-07-04T17:48:20Z",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_verify_google_request_passes_when_operator_action_is_still_required(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    draft_root = tmp_path / "_completion" / "google_oauth_linking"
    monkeypatch.setattr(request_module, "DEFAULT_OPERATOR_DRAFT_ROOT", draft_root)
    monkeypatch.setattr(request_module, "DEFAULT_TEMPLATE_PATH", tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json")
    monkeypatch.setattr(request_module, "DEFAULT_SCREENSHOT_ROOT", tmp_path / "screens")

    release_channel_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    write_release_channel(release_channel_path)
    receipt_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    evidence_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"

    request_module.materialize(
        receipt_path,
        evidence_path=evidence_path,
        template_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
        screenshot_root=tmp_path / "screens",
        release_channel_path=release_channel_path,
    )

    ok, result = verify_module.verify(receipt_path, require_pass=False)

    assert ok is True
    assert result["status"] == "pass"
    assert result["request_status"] == "operator_action_required"
    assert result["operator_action_still_required"] is True
    assert result["recovery_pack_pass"] is True
    assert result["issues"] == []


def test_verify_google_request_passes_when_valid_operator_evidence_already_exists(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    draft_root = tmp_path / "_completion" / "google_oauth_linking"
    monkeypatch.setattr(request_module, "DEFAULT_OPERATOR_DRAFT_ROOT", draft_root)
    monkeypatch.setattr(request_module, "DEFAULT_TEMPLATE_PATH", tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json")
    monkeypatch.setattr(request_module, "DEFAULT_SCREENSHOT_ROOT", tmp_path / "screens")

    release_channel_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    write_release_channel(release_channel_path)
    screenshot_root = tmp_path / "screens"
    screenshot_root.mkdir(parents=True, exist_ok=True)
    screenshot_paths = [
        screenshot_root / "google-signed-in-state.png",
        screenshot_root / "google-provider-linked.png",
    ]
    for path in screenshot_paths:
        path.write_bytes(b"ok")

    evidence_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
    evidence_path.write_text(
        json.dumps(
            {
                "contract_name": request_module.OPERATOR_EVIDENCE_CONTRACT_NAME,
                "status": "pass",
                "base_url": request_module.DEFAULT_BASE_URL,
                "observed_at_utc": "2026-07-04T22:16:09Z",
                "verified_steps": list(request_module.REQUIRED_OPERATOR_STEPS),
                "screenshot_paths": [str(path) for path in screenshot_paths],
                "notes": "",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    receipt_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    request_module.materialize(
        receipt_path,
        evidence_path=evidence_path,
        template_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
        screenshot_root=screenshot_root,
        release_channel_path=release_channel_path,
    )

    ok, result = verify_module.verify(receipt_path, require_pass=False)

    assert ok is True
    assert result["status"] == "pass"
    assert result["request_status"] == "not_required"
    assert result["operator_action_still_required"] is False
    assert result["operator_evidence_pass"] is True
    assert result["issues"] == []


def test_verify_google_request_require_pass_rejects_pending_operator_action(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    draft_root = tmp_path / "_completion" / "google_oauth_linking"
    monkeypatch.setattr(request_module, "DEFAULT_OPERATOR_DRAFT_ROOT", draft_root)
    monkeypatch.setattr(request_module, "DEFAULT_TEMPLATE_PATH", tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json")
    monkeypatch.setattr(request_module, "DEFAULT_SCREENSHOT_ROOT", tmp_path / "screens")

    release_channel_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    write_release_channel(release_channel_path)
    receipt_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"

    request_module.materialize(
        receipt_path,
        evidence_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json",
        template_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
        screenshot_root=tmp_path / "screens",
        release_channel_path=release_channel_path,
    )

    ok, result = verify_module.verify(receipt_path, require_pass=True)

    assert ok is False
    assert result["status"] == "fail"
    assert "operator_action_still_required" in result["issues"]


def test_verify_google_request_rejects_loopback_url_in_published_commands(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    draft_root = tmp_path / "_completion" / "google_oauth_linking"
    monkeypatch.setattr(request_module, "DEFAULT_OPERATOR_DRAFT_ROOT", draft_root)
    monkeypatch.setattr(request_module, "DEFAULT_TEMPLATE_PATH", tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json")
    monkeypatch.setattr(request_module, "DEFAULT_SCREENSHOT_ROOT", tmp_path / "screens")

    release_channel_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    write_release_channel(release_channel_path)
    receipt_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"

    payload = request_module.materialize(
        receipt_path,
        evidence_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json",
        template_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
        screenshot_root=tmp_path / "screens",
        release_channel_path=release_channel_path,
    )
    payload["post_import_gates"][0] = "python3 scripts/tool.py --base-url http://127.0.0.1:8091"
    receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    ok, result = verify_module.verify(receipt_path, require_pass=False)

    assert ok is False
    assert result["status"] == "fail"
    assert "published_commands_contain_loopback_url" in result["issues"]


def test_verify_google_request_rejects_missing_flagship_refresh_gate(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    draft_root = tmp_path / "_completion" / "google_oauth_linking"
    monkeypatch.setattr(request_module, "DEFAULT_OPERATOR_DRAFT_ROOT", draft_root)
    monkeypatch.setattr(request_module, "DEFAULT_TEMPLATE_PATH", tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json")
    monkeypatch.setattr(request_module, "DEFAULT_SCREENSHOT_ROOT", tmp_path / "screens")

    release_channel_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    write_release_channel(release_channel_path)
    receipt_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"

    payload = request_module.materialize(
        receipt_path,
        evidence_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json",
        template_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
        screenshot_root=tmp_path / "screens",
        release_channel_path=release_channel_path,
    )
    payload["post_import_gates"] = [
        command
        for command in payload["post_import_gates"]
        if "verify_flagship_product_readiness_gate.py" not in command
    ]
    receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    ok, result = verify_module.verify(receipt_path, require_pass=False)

    assert ok is False
    assert result["status"] == "fail"
    assert "post_import_gates_missing_required_command" in result["issues"]


def test_verify_google_request_accepts_relative_receipt_path_from_repo_cwd(tmp_path: Path, monkeypatch) -> None:
    request_module = load_request_module()
    verify_module = load_verify_module()
    proof_module = load_proof_module()
    draft_root = tmp_path / "_completion" / "google_oauth_linking"
    monkeypatch.setattr(request_module, "DEFAULT_OPERATOR_DRAFT_ROOT", draft_root)
    monkeypatch.setattr(request_module, "DEFAULT_TEMPLATE_PATH", tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json")
    monkeypatch.setattr(request_module, "DEFAULT_SCREENSHOT_ROOT", tmp_path / "screens")
    monkeypatch.setattr(proof_module, "RUN_SERVICES_ROOT", tmp_path)
    monkeypatch.setattr(verify_module, "load_proof_module", lambda: proof_module)
    monkeypatch.chdir(tmp_path)

    release_channel_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    write_release_channel(release_channel_path)
    receipt_path = Path("GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json")

    request_module.materialize(
        receipt_path,
        evidence_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json",
        template_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
        screenshot_root=tmp_path / "screens",
        release_channel_path=release_channel_path,
    )

    ok, result = verify_module.verify(receipt_path, require_pass=False)

    assert ok is True
    assert result["status"] == "pass"
    assert result["issues"] == []
