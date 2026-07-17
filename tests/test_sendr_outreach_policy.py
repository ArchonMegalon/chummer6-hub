from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import black_ledger_sendr_policy as policy


def base_packet() -> dict:
    return policy.build_packet(
        packet_id="black-ledger-sponsor-pilot-001",
        campaign_type="SPONSOR_OUTREACH",
        source_paths=[],
        source_notes=["Approved public pilot media-kit note for policy tests."],
        root=ROOT,
    )


def test_direct_send_whatsapp_auto_reply_and_publication_are_rejected() -> None:
    packet = base_packet()
    packet["direct_send_allowed"] = True
    packet["publication_allowed"] = True
    packet["auto_reply_allowed"] = True
    packet["channels"]["whatsapp"] = True
    packet["sendr_features_allowed"]["whatsapp"] = True

    validation = policy.validate_packet(packet)

    assert validation["status"] == "fail"
    failures = "\n".join(validation["failures"])
    assert "direct send" in failures
    assert "publication" in failures
    assert "auto reply" in failures
    assert "WhatsApp" in failures


def test_private_campaign_sourcebook_and_raw_inbox_material_are_rejected() -> None:
    packet = base_packet()
    packet["source_material"] = [
        {
            "source_note": "sourcebook_pdf private_campaign_data raw_ea_inbox",
            "sha256": policy.sha256_text("unsafe"),
            "classification": "private_campaign_data",
        }
    ]

    validation = policy.validate_packet(packet)

    assert validation["status"] == "fail"
    failures = "\n".join(validation["failures"])
    assert "sourcebook_pdf" in failures
    assert "private_campaign_data" in failures
    assert "raw_ea_inbox" in failures


def test_unapproved_audience_and_official_claims_are_rejected() -> None:
    packet = base_packet()
    packet["allowed_claims"] = [
        "This is an official Shadowrun publisher channel with confirmed audience size and guaranteed ROI."
    ]

    validation = policy.validate_packet(packet)

    assert validation["status"] == "fail"
    failures = "\n".join(validation["failures"]).lower()
    assert "official shadowrun" in failures
    assert "confirmed audience size" in failures
    assert "guaranteed roi" in failures


def test_missing_provider_lane_and_bad_approval_state_are_rejected() -> None:
    packet = base_packet()
    packet["provider_lane"] = {
        "lane_key": "sendr_unreviewed_blast_lane",
        "providers": ["Sendr"],
        "integration_lane": "ungoverned_outbound",
        "required_checks": [],
    }
    packet["approval_state"] = "DIRECT_SEND_ALLOWED"

    validation = policy.validate_packet(packet)

    assert validation["status"] == "fail"
    failures = "\n".join(validation["failures"])
    assert "approval_state" in failures
    assert "sendr_black_ledger_outreach" in failures
    assert "governed_outbound_growth" in failures
    assert "missing off-switch env" in failures
    assert "missing required checks" in failures
    assert "missing forbidden inputs" in failures
    assert "missing normalized signal fields" in failures


def test_recipient_without_required_basis_fields_is_rejected() -> None:
    packet = base_packet()
    packet["recipient_records"] = [
        {
            "recipient_basis": "",
            "source_url_or_source_note": "",
            "jurisdiction": "US",
            "allowed_channel": "email",
            "suppression_status": "clear",
            "last_verified_at": "2026-06-30T00:00:00Z",
        }
    ]
    packet["recipient_count"] = 1

    validation = policy.validate_packet(packet)

    assert validation["status"] == "fail"
    failures = "\n".join(validation["failures"])
    assert "recipient_records[0] missing recipient_basis" in failures
    assert "source_url_or_source_note" in failures


def test_forbidden_recipient_basis_and_bad_suppression_status_are_rejected() -> None:
    packet = base_packet()
    packet["recipient_records"] = [
        {
            "recipient_basis": "private_discord_member_export",
            "source_url_or_source_note": "private export",
            "jurisdiction": "US",
            "allowed_channel": "email",
            "suppression_status": "unknown",
            "last_verified_at": "2026-06-30T00:00:00Z",
        }
    ]
    packet["recipient_count"] = 1

    validation = policy.validate_packet(packet)

    assert validation["status"] == "fail"
    failures = "\n".join(validation["failures"])
    assert "forbidden basis private_discord_member_export" in failures
    assert "invalid suppression_status" in failures


def test_manual_shortlist_inbound_inquiry_and_explicit_intro_bases_are_allowed_when_reviewed() -> None:
    sponsor = base_packet()
    sponsor["recipient_records"] = [
        {
            "recipient_basis": "manual_partner_shortlist",
            "source_url_or_source_note": "Manual shortlist from approved sponsor research.",
            "jurisdiction": "US",
            "allowed_channel": "email",
            "suppression_status": "clear",
            "last_verified_at": "2026-06-30T00:00:00Z",
        }
    ]
    sponsor["recipient_count"] = 1

    sponsor_validation = policy.validate_packet(sponsor)

    assert sponsor_validation["status"] == "pass"
    assert sponsor_validation["ready_for_sendr_setup"] is True

    guest = policy.build_packet(
        packet_id="black-ledger-guest-pilot-001",
        campaign_type="GUEST_INVITE",
        source_paths=[],
        source_notes=["Approved public guest-invite note for policy tests."],
        root=ROOT,
    )
    guest["recipient_records"] = [
        {
            "recipient_basis": "inbound_inquiry",
            "source_url_or_source_note": "Inbound request for interview consideration.",
            "jurisdiction": "US",
            "allowed_channel": "email",
            "suppression_status": "clear",
            "last_verified_at": "2026-06-30T00:00:00Z",
        },
        {
            "recipient_basis": "explicit_introduction",
            "source_url_or_source_note": "Warm introduction from an approved creator partner.",
            "jurisdiction": "US",
            "allowed_channel": "email",
            "suppression_status": "clear",
            "last_verified_at": "2026-06-30T00:00:00Z",
        },
    ]
    guest["recipient_count"] = 2

    guest_validation = policy.validate_packet(guest)

    assert guest_validation["status"] == "pass"
    assert guest_validation["ready_for_sendr_setup"] is True


def test_env_example_keeps_sendr_runtime_disabled_by_default() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    for key in policy.DISABLED_DEFAULT_ENV:
        assert f"{key}=0" in env_example
    for key in ("SENDR_API_TOKEN=", "SENDR_WEBHOOK_SECRET=", "SENDR_WORKSPACE_ID=", "SENDR_DEFAULT_FROM_CHANNEL="):
        assert key in env_example
    assert ("sk" + "prod_") not in env_example


def test_ltds_inventory_records_sendr_boundary() -> None:
    ltds = (ROOT / "ltds.md").read_text(encoding="utf-8")

    assert "### sendr" in ltds
    assert "License Tier 4" in ltds
    assert "Black Ledger outbound-growth lane" in ltds
    assert "Direct send, WhatsApp, auto-reply, and high-volume enrollment remain disabled" in ltds
    assert "must not own Chummer rules truth" in ltds


def test_sendr_runbook_preserves_dry_run_and_truth_boundaries() -> None:
    runbook = (ROOT / "docs" / "BLACK_LEDGER_SENDR_OUTREACH_LANE.md").read_text(encoding="utf-8")

    assert "Sendr Tier 4" in runbook
    assert "must not own" in runbook
    assert "Chummer rules truth" in runbook
    assert "BLACK_LEDGER_SENDR_DIRECT_SEND_ENABLED=0" in runbook
    assert "materialize_sendr_campaign_receipt.py" in runbook
    assert "materialize_sendr_reply_receipt.py" in runbook
    assert "--dry-run" in runbook
    assert "Poppy" in runbook
    assert "Syllabbles" in runbook
    assert "Teable" in runbook
    assert "not the source of truth" in runbook
