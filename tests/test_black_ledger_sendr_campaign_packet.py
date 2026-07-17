from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import black_ledger_sendr_policy as policy


def build_ready_packet() -> dict:
    packet = policy.build_packet(
        packet_id="black-ledger-sponsor-pilot-001",
        campaign_type="SPONSOR_OUTREACH",
        source_paths=[],
        source_notes=["Approved public pilot media-kit note for packet tests."],
        root=ROOT,
    )
    packet["recipient_records"] = [
        {
            "recipient_basis": "public_business_contact",
            "source_url_or_source_note": "https://example.test/sponsors",
            "jurisdiction": "US",
            "allowed_channel": "email",
            "suppression_status": "clear",
            "last_verified_at": "2026-06-30T00:00:00Z",
        }
    ]
    packet["recipient_count"] = 1
    return packet


def test_default_packet_is_fail_closed_and_review_required() -> None:
    packet = policy.build_packet(
        packet_id="black-ledger-sponsor-pilot-001",
        campaign_type="SPONSOR_OUTREACH",
        source_paths=[],
        source_notes=[],
        root=ROOT,
    )

    assert packet["human_review_required"] is True
    assert packet["direct_send_allowed"] is False
    assert packet["publication_allowed"] is False
    assert packet["auto_reply_allowed"] is False
    assert packet["limited_send_allowed"] is False
    assert packet["channels"]["whatsapp"] is False
    assert packet["sendr_features_allowed"]["whatsapp"] is False
    assert "BLACK_LEDGER_SENDR_DIRECT_SEND_ENABLED" in packet["feature_flags_required_disabled"]
    assert packet["approval_state"] == "CAMPAIGN_PACKET_DRAFT"
    assert "APPROVED_FOR_LIMITED_SEND" in packet["approval_state_machine"]["states"]
    assert "COMPLIANCE_BLOCKED" in packet["approval_state_machine"]["failure_states"]
    assert packet["provider_lane"]["lane_key"] == "sendr_black_ledger_outreach"
    assert packet["provider_lane"]["integration_lane"] == "governed_outbound_growth"
    assert packet["provider_lane"]["off_switch_env"] == [
        "BLACK_LEDGER_SENDR_ENABLED",
        "BLACK_LEDGER_SENDR_API_ENABLED",
    ]

    validation = policy.validate_packet(packet)
    assert validation["status"] == "pass"
    assert validation["readiness_status"] == "review_required"
    assert validation["ready_for_sendr_setup"] is False
    assert validation["checks"]["source_material"]["missing_required_sources"]
    assert validation["checks"]["recipient_policy"]["missing_records"] is True


def test_ready_packet_still_has_no_direct_send_permission() -> None:
    packet = build_ready_packet()

    validation = policy.validate_packet(packet)

    assert validation["status"] == "pass"
    assert validation["ready_for_sendr_setup"] is True
    assert packet["direct_send_allowed"] is False
    assert packet["auto_reply_allowed"] is False
    assert packet["limited_send_allowed"] is False


def test_provider_governance_lane_matches_sendr_black_ledger_contract() -> None:
    packet = build_ready_packet()
    lane = packet["provider_lane"]
    required_checks = {item["check_key"] for item in lane["required_checks"]}

    assert lane["providers"] == ["Sendr"]
    assert lane["verified_state"] == "verified_draft_operator_lane"
    assert "Black Ledger editorial packets" in lane["source_of_truth"]
    assert sum(lane["recommended_monthly_allocation_percent"].values()) == 100
    assert lane["first_pilot_campaigns"][0]["campaign_type"] == "SPONSOR_OUTREACH"
    assert lane["first_pilot_campaigns"][0]["channels"]["whatsapp"] is False
    assert "approved_media_kit" in lane["allowed_inputs"]
    assert "approved_public_chummer_tutorial" in lane["allowed_inputs"]
    assert "sourcebook_pdf" in lane["forbidden_inputs"]
    assert "private_campaign_data" in lane["forbidden_inputs"]
    assert "direct_publish" in lane["forbidden_inputs"]
    assert "auto_reply" in lane["forbidden_inputs"]
    assert "recipient_basis" in lane["normalized_signal_schema"]
    assert "reply_event_hash" in lane["normalized_signal_schema"]
    assert required_checks == set(policy.PROVIDER_LANE_REQUIRED_CHECKS)

    validation = policy.validate_packet(packet)
    assert validation["status"] == "pass"


def test_packet_preserves_sendr_storage_and_truth_boundaries() -> None:
    packet = build_ready_packet()

    assert "chummer_rules_truth" in packet["provider_boundaries"]["sendr_must_not_own"]
    assert "black_ledger_editorial_truth" in packet["provider_boundaries"]["sendr_must_not_own"]
    assert "automatic_commitments" in packet["provider_boundaries"]["sendr_must_not_own"]
    assert "business_email" in packet["sendr_storage_policy"]["allowed"]
    assert "private_chummer_user_data" in packet["sendr_storage_policy"]["forbidden"]
    assert "sourcebook_pdfs" in packet["sendr_storage_policy"]["forbidden"]
    assert packet["data_retention_policy"]["raw_sendr_data_stored"] is False
    assert packet["data_retention_policy"]["raw_reply_bodies_stored"] is False
    assert packet["data_retention_policy"]["suppression_fail_closed"] is True
    assert "contact_hash" in packet["data_retention_policy"]["ea_black_ledger_store"]
    assert "official Shadowrun" in packet["copy_policy"]["avoid"]
    assert "guaranteed reach" in packet["copy_policy"]["avoid"]

    validation = policy.validate_packet(packet)
    assert validation["status"] == "pass"


def test_blocked_suppression_status_prevents_sendr_setup() -> None:
    packet = build_ready_packet()
    packet["recipient_records"][0]["suppression_status"] = "pending_review"

    validation = policy.validate_packet(packet)

    assert validation["status"] == "fail"
    assert validation["ready_for_sendr_setup"] is False
    assert "suppression_status must be clear before Sendr setup" in "\n".join(validation["failures"])


def test_disabled_recipient_channels_are_rejected() -> None:
    packet = build_ready_packet()
    packet["recipient_records"][0]["allowed_channel"] = "whatsapp"

    validation = policy.validate_packet(packet)

    assert validation["status"] == "fail"
    assert "WhatsApp while WhatsApp is disabled" in "\n".join(validation["failures"])

    episode_packet = build_ready_packet()
    episode_packet["campaign_type"] = "EPISODE_LAUNCH"
    episode_packet["channels"]["linkedin"] = False
    episode_packet["recipient_policy"]["allowed_recipient_basis"] = ["prior_conversation", "opt_in", "partner_list", "press_list_with_lawful_basis"]
    episode_packet["recipient_records"][0]["recipient_basis"] = "opt_in"
    episode_packet["recipient_records"][0]["allowed_channel"] = "linkedin"

    episode_validation = policy.validate_packet(episode_packet)

    assert episode_validation["status"] == "fail"
    assert "allowed_channel linkedin is disabled" in "\n".join(episode_validation["failures"])


def test_cli_build_and_verify_safe_draft(tmp_path: Path) -> None:
    packet_path = tmp_path / "packet.json"
    validation_path = tmp_path / "validation.json"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "build_black_ledger_sendr_campaign_packet.py"),
            "--type",
            "SPONSOR_OUTREACH",
            "--packet",
            "black-ledger-sponsor-pilot-001",
            "--output",
            str(packet_path),
        ],
        cwd=ROOT,
        check=True,
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "verify_black_ledger_sendr_campaign_packet.py"),
            "--packet",
            str(packet_path),
            "--output",
            str(validation_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    assert packet["contract_name"] == policy.CONTRACT_NAME
    assert validation["status"] == "pass"
    assert validation["ready_for_sendr_setup"] is False
    assert "review_required" in result.stdout


def test_cli_require_ready_fails_for_source_less_draft(tmp_path: Path) -> None:
    packet_path = tmp_path / "packet.json"
    policy.write_json(
        packet_path,
        policy.build_packet(
            packet_id="black-ledger-sponsor-pilot-001",
            campaign_type="SPONSOR_OUTREACH",
            source_paths=[],
            source_notes=[],
            root=ROOT,
        ),
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "verify_black_ledger_sendr_campaign_packet.py"),
            "--packet",
            str(packet_path),
            "--require-ready",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "review_required" in result.stdout
