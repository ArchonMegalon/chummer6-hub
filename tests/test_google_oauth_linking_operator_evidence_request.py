from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_google_oauth_linking_operator_evidence_request.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_google_oauth_linking_operator_evidence_request", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_materialize_writes_request_and_template(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    draft_root = tmp_path / "_completion" / "google_oauth_linking"
    incoming_root = tmp_path / ".state" / "incoming_google_oauth_linking_operator_evidence"
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_DRAFT_ROOT", draft_root)
    monkeypatch.setattr(module, "DEFAULT_TEMPLATE_PATH", tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json")
    monkeypatch.setattr(module, "DEFAULT_SCREENSHOT_ROOT", tmp_path / "screens")
    monkeypatch.setattr(module, "DEFAULT_INCOMING_EVIDENCE_ROOT", incoming_root)
    monkeypatch.setattr(module, "RUN_SERVICES_ROOT", tmp_path)
    monkeypatch.setattr(module, "ROOT", tmp_path.parent)
    release_channel_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_channel_path.write_text(
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

    output_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    evidence_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"

    payload = module.materialize(
        output_path,
        evidence_path=evidence_path,
        template_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
        screenshot_root=tmp_path / "screens",
        release_channel_path=release_channel_path,
    )

    assert payload["status"] == "operator_action_required"
    assert payload["required_output_path"] == str(evidence_path)
    assert payload["required_receipt_path"] == str(evidence_path)
    assert payload["required_operator_evidence_path"] == str(evidence_path)
    assert payload["request_receipt_path"] == str(output_path)
    assert payload["required_steps"] == list(module.REQUIRED_OPERATOR_STEPS)
    assert payload["operator_ask_text_path"] == str(draft_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt")
    assert payload["operator_ask_metadata_path"] == str(draft_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json")
    assert payload["operator_evidence_template_path"] == str(tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json")
    assert payload["receipt_name"] == "google-oauth-linking-operator-ask.receipt.json"
    assert payload["send_command"] == (
        "python3 scripts/send_telegram_message_via_ea.py "
        f"--text-file {draft_root / 'CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt'} "
        "--receipt-name google-oauth-linking-operator-ask.receipt.json"
    )
    assert payload["operator_ask_receipt_name"] == payload["receipt_name"]
    assert payload["operator_ask_send_command"] == payload["send_command"]
    assert payload["release_channel_receipt_path"] == str(release_channel_path)
    assert payload["release_version"] == "run-20260704-170602"
    assert payload["release_channel"] == "preview"
    assert payload["release_supportability_state"] == "preview_supported"
    assert payload["release_rollout_state"] == "promoted_preview"
    assert payload["release_published_at"] == "2026-07-04T17:48:20Z"
    telegram_draft = payload["operator_telegram_draft"]
    assert telegram_draft["status"] == "prepared_not_sent"
    assert telegram_draft["current_message_path"] == str(draft_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt")
    assert telegram_draft["current_metadata_path"] == str(draft_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json")
    assert telegram_draft["receipt_name"] == "google-oauth-linking-operator-ask.receipt.json"
    assert telegram_draft["send_command"] == payload["send_command"]
    assert telegram_draft["preferred_drop_path"] == payload["preferred_drop_path"]
    assert telegram_draft["preferred_zip_name"] == payload["preferred_zip_name"]
    materialized_draft = payload["operator_telegram_draft_materialized"]
    assert materialized_draft["status"] == "prepared_not_sent"
    assert materialized_draft["operator_ask_text_path"] == str(draft_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt")
    assert materialized_draft["operator_ask_metadata_path"] == str(draft_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json")
    assert materialized_draft["receipt_name"] == "google-oauth-linking-operator-ask.receipt.json"
    assert materialized_draft["send_command"] == payload["send_command"]
    assert materialized_draft["operator_ask_receipt_name"] == payload["operator_ask_receipt_name"]
    assert materialized_draft["operator_ask_send_command"] == payload["operator_ask_send_command"]
    assert payload["secrets_redacted"] is True
    assert payload["direct_telegram_sent"] is False
    assert payload["intake"] == payload["artifact_intake"]
    assert payload["preferredDropPath"] == payload["preferred_drop_path"]
    assert payload["current_operator_evidence"]["pass"] is False
    assert payload["post_import_gates"] == list(module.POST_IMPORT_COMMANDS)
    assert payload["post_import_gates"].index(
        "python3 scripts/verify_google_oauth_linking_proof.py --require-pass"
    ) < payload["post_import_gates"].index(
        "python3 scripts/verify_flagship_product_readiness_gate.py --summary-output .codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
    )
    assert payload["post_import_gates"][-1] == "python3 scripts/final_gold_janitor.py --skip-materializers"
    assert all("http://127.0.0.1" not in command and "http://localhost" not in command for command in payload["post_import_gates"])
    assert payload["artifact_intake"]["dedicated_drop_root"] == str(incoming_root)
    assert payload["artifact_intake"]["dedicated_drop_root_gitignored"] is True
    assert payload["artifact_intake"]["auto_import_roots"][0] == str(incoming_root)
    assert payload["artifact_intake"]["auto_import_roots"][1:] == ["~/Downloads", "~/pCloud Drive/EA"]
    assert payload["drop_roots_checked"] == [str(incoming_root)]
    assert "~/Downloads" in payload["artifact_intake"]["discover_command"]
    assert "~/pCloud Drive/EA" in payload["artifact_intake"]["discover_command"]
    assert "--refresh-intake-request" in payload["artifact_intake"]["auto_import_watch_command"]
    assert output_path.is_file()
    assert incoming_root.is_dir()

    template = json.loads((tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json").read_text())
    assert template["contract_name"] == module.OPERATOR_EVIDENCE_CONTRACT_NAME
    assert template["status"] == "pass"
    assert template["verified_steps"] == list(module.REQUIRED_OPERATOR_STEPS)

    ask_text = (draft_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt").read_text()
    assert "google_sign_in_completed_to_signed_in_state" in ask_text
    assert str(evidence_path) in ask_text
    assert "run-20260704-170602" in ask_text
    assert "channel=preview" in ask_text
    assert str(tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json") in ask_text
    assert str(incoming_root / "google-oauth-linking-operator-evidence-run-20260704-170602.zip") in ask_text
    assert "import_google_oauth_linking_operator_evidence_artifact.py" in ask_text
    assert "auto_import_google_oauth_linking_operator_evidence.py" in ask_text
    assert "--refresh-intake-request" in ask_text

    ask_metadata = json.loads((draft_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json").read_text())
    assert ask_metadata["required_receipt_path"] == str(evidence_path)
    assert ask_metadata["required_operator_evidence_path"] == str(evidence_path)
    assert ask_metadata["request_receipt_path"] == str(output_path)
    assert ask_metadata["operator_ask_text_path"] == str(draft_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt")
    assert ask_metadata["operator_ask_metadata_path"] == str(draft_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json")
    assert ask_metadata["receipt_name"] == "google-oauth-linking-operator-ask.receipt.json"
    assert ask_metadata["send_command"] == payload["send_command"]
    assert ask_metadata["operator_ask_receipt_name"] == payload["operator_ask_receipt_name"]
    assert ask_metadata["operator_ask_send_command"] == payload["operator_ask_send_command"]
    assert ask_metadata["status"] == "prepared_not_sent"
    assert ask_metadata["secrets_redacted"] is True
    assert ask_metadata["release_channel_receipt_path"] == str(release_channel_path)
    assert ask_metadata["release_version"] == "run-20260704-170602"
    assert ask_metadata["release_channel"] == "preview"
    assert "auto_import_google_oauth_linking_operator_evidence.py" in ask_metadata["auto_import_watch_command"]
    assert "--refresh-intake-request" in ask_metadata["auto_import_watch_command"]
    assert payload["operator_message_sha256"] == ask_metadata["message_sha256"]


def test_build_request_rebinds_operator_ask_paths_to_patched_draft_root(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    draft_root = tmp_path / "_completion" / "google_oauth_linking"
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_DRAFT_ROOT", draft_root)

    request = module.build_request(
        tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json",
        "https://chummer.run",
        tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json",
        tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
        [tmp_path / "google-signed-in-state.png", tmp_path / "google-provider-linked.png"],
        {
            "path": str(tmp_path / "RELEASE_CHANNEL.generated.json"),
            "version": "run-20260704-170602",
            "channel": "preview",
            "supportability_state": "preview_supported",
            "rollout_state": "promoted_preview",
            "published_at": "2026-07-04T17:48:20Z",
        },
        request_status="operator_action_required",
    )

    assert request["operator_ask_text_path"].startswith(str(draft_root))
    assert request["operator_ask_metadata_path"].startswith(str(draft_root))
    assert request["operator_ask_text_path"].endswith("CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt")
    assert request["operator_ask_metadata_path"].endswith("CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json")


def test_read_release_context_falls_back_to_shared_portal_release_channel_when_registry_checkout_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    module = load_module()
    run_services_root = tmp_path / "clean-run-services"
    shared_root = tmp_path / "workspace"
    shared_release_channel = shared_root / "chummer.run-services" / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json"
    shared_release_channel.parent.mkdir(parents=True, exist_ok=True)
    shared_release_channel.write_text(
        json.dumps(
            {
                "version": "run-20260705-040324",
                "channelId": "preview",
                "supportabilityState": "preview_supported",
                "rolloutState": "promoted_preview",
                "publishedAt": "2026-07-05T04:05:30Z",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "RUN_SERVICES_ROOT", run_services_root)
    monkeypatch.setattr(module, "ROOT", shared_root)
    monkeypatch.setattr(
        module,
        "DEFAULT_PORTAL_RELEASE_CHANNEL_PATH",
        run_services_root / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json",
    )
    monkeypatch.setattr(
        module,
        "DEFAULT_PUBLISHED_PORTAL_RELEASE_CHANNEL_PATH",
        run_services_root / ".codex-studio" / "published" / "portal" / "RELEASE_CHANNEL.generated.json",
    )
    monkeypatch.setattr(
        module,
        "DEFAULT_RELEASE_CHANNEL_PATH",
        shared_root / "chummer-hub-registry" / ".codex-studio" / "published" / "RELEASE_CHANNEL.generated.json",
    )

    context = module.read_release_context(module.DEFAULT_RELEASE_CHANNEL_PATH)

    assert context["path"] == str(shared_release_channel)
    assert context["version"] == "run-20260705-040324"
    assert context["channel"] == "preview"
    assert context["supportability_state"] == "preview_supported"
    assert context["rollout_state"] == "promoted_preview"
    assert context["published_at"] == "2026-07-05T04:05:30Z"


def test_materialize_suppresses_request_when_valid_operator_evidence_exists(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    draft_root = tmp_path / "_completion" / "google_oauth_linking"
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_DRAFT_ROOT", draft_root)
    monkeypatch.setattr(module, "DEFAULT_TEMPLATE_PATH", tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json")
    monkeypatch.setattr(module, "DEFAULT_SCREENSHOT_ROOT", tmp_path / "screens")
    release_channel_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_channel_path.write_text(
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
                "contract_name": module.OPERATOR_EVIDENCE_CONTRACT_NAME,
                "status": "pass",
                "base_url": module.DEFAULT_BASE_URL,
                "observed_at_utc": "2026-07-04T22:16:09Z",
                "verified_steps": list(module.REQUIRED_OPERATOR_STEPS),
                "screenshot_paths": [str(path) for path in screenshot_paths],
                "notes": "",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = module.materialize(
        tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json",
        evidence_path=evidence_path,
        template_path=tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
        screenshot_root=screenshot_root,
        release_channel_path=release_channel_path,
    )

    assert payload["status"] == "not_required"
    assert payload["current_operator_evidence"]["pass"] is True
    assert payload["operator_telegram_draft"]["status"] == "not_required"
    assert payload["operator_telegram_draft_materialized"]["status"] == "not_required"
    assert "no operator action required" in payload["summary"].lower()

    ask_text = (draft_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt").read_text(encoding="utf-8")
    ask_metadata = json.loads((draft_root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json").read_text(encoding="utf-8"))
    assert "No operator action is currently required." in ask_text
    assert ask_metadata["status"] == "not_required"


def test_artifact_discovery_roots_include_common_operator_sync_locations(tmp_path: Path) -> None:
    module = load_module()
    home = tmp_path / "home"
    incoming_root = tmp_path / ".state" / "incoming_google_oauth_linking_operator_evidence"

    with mock.patch("pathlib.Path.home", return_value=home):
        roots = module.artifact_discovery_roots(incoming_root)

    assert roots == [
        incoming_root,
        home / "Downloads",
        home / "pCloud Drive" / "EA",
    ]
