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


def contact_hash(seed: str = "sponsor@example.test") -> str:
    return policy.sha256_text(seed)


def test_engagement_batch_keeps_replies_review_only_and_no_commitments() -> None:
    receipt = policy.build_engagement_batch(
        campaign_id="sendr-campaign-001",
        campaign_type="SPONSOR_OUTREACH",
        event_batch_id="reply-batch-001",
        dry_run=True,
        events=[
            {
                "event_type": "reply_received",
                "contact_hash": contact_hash(),
                "occurred_at": "2026-06-30T12:00:00Z",
                "preview": "Interested, please send details.",
                "human_review_required": True,
                "raw_body_stored": False,
            }
        ],
    )

    assert receipt["contract_name"] == policy.ENGAGEMENT_CONTRACT_NAME
    assert receipt["status"] == "review_required"
    assert receipt["campaign_type"] == "SPONSOR_OUTREACH"
    assert receipt["provider_lane"]["lane_key"] == "sendr_black_ledger_outreach"
    assert receipt["provider_lane"]["integration_lane"] == "governed_outbound_growth"
    assert receipt["validation"]["status"] == "pass"
    assert receipt["events"][0]["raw_body_stored"] is False
    assert receipt["events"][0]["human_review_required"] is True
    assert receipt["ea_actions"]["draft_reply_candidates"] == 1
    assert receipt["ea_actions"]["sponsor_lead_candidates"] == 1
    assert receipt["ea_actions"]["commitment_candidates_created"] == 0
    assert {item["candidate_type"] for item in receipt["ea_actions"]["review_candidates"]} >= {
        "SponsorLeadCandidate",
        "DraftReplyCandidate",
        "Evidence",
    }
    assert receipt["ea_actions"]["automatic_commitments_allowed"] is False
    assert receipt["ea_actions"]["auto_reply_allowed"] is False
    assert receipt["ea_actions"]["suppression_updates"] == 0


def test_meeting_booked_becomes_candidate_not_commitment() -> None:
    receipt = policy.build_engagement_batch(
        campaign_id="sendr-campaign-001",
        campaign_type="GUEST_INVITE",
        event_batch_id="meeting-batch-001",
        dry_run=True,
        events=[
            {
                "event_type": "meeting_booked",
                "contact_hash": contact_hash("guest@example.test"),
                "occurred_at": "2026-06-30T12:00:00Z",
                "human_review_required": True,
                "raw_body_stored": False,
            }
        ],
    )

    assert receipt["ea_actions"]["guest_lead_candidates"] == 1
    assert receipt["ea_actions"]["commitment_candidates"] == 1
    assert receipt["ea_actions"]["commitment_candidates_created"] == 0
    assert receipt["ea_actions"]["automatic_commitments_allowed"] is False
    assert {item["candidate_type"] for item in receipt["ea_actions"]["review_candidates"]} >= {
        "GuestLeadCandidate",
        "CommitmentCandidate",
        "Evidence",
    }


def test_suppression_sync_generates_updates_for_required_events() -> None:
    receipt = policy.build_engagement_batch(
        campaign_id="sendr-campaign-001",
        event_batch_id="suppression-batch-001",
        dry_run=True,
        events=[
            {
                "event_type": "unsubscribe",
                "contact_hash": contact_hash("unsub@example.test"),
                "occurred_at": "2026-06-30T12:01:00Z",
            },
            {
                "event_type": "bounce",
                "contact_hash": contact_hash("bounce@example.test"),
                "occurred_at": "2026-06-30T12:02:00Z",
            },
            {
                "event_type": "negative_reply",
                "contact_hash": contact_hash("negative@example.test"),
                "occurred_at": "2026-06-30T12:03:00Z",
                "preview": "Not relevant.",
            },
        ],
    )

    validation = policy.validate_suppression_sync(receipt)
    scopes = {item["reason"]: item["scope"] for item in receipt["ea_actions"]["suppression_events"]}

    assert receipt["ea_actions"]["suppression_updates"] == 3
    assert scopes["unsubscribe"] == "global_black_ledger"
    assert scopes["bounce"] == "address"
    assert scopes["negative_reply_review"] == "campaign_or_global_review"
    assert validation["status"] == "pass"
    assert validation["suppression_required_events"] == 3


def test_raw_reply_body_and_raw_email_contact_are_rejected() -> None:
    validation = policy.validate_engagement_events(
        [
            {
                "event_type": "reply_received",
                "contact_hash": "person@example.test",
                "occurred_at": "2026-06-30T12:00:00Z",
                "raw_body": "Full private reply must not be stored.",
            }
        ]
    )

    failures = "\n".join(validation["failures"])
    assert validation["status"] == "fail"
    assert "raw Sendr fields" in failures
    assert "raw contact data" in failures


def test_duplicate_events_are_ignored_idempotently() -> None:
    event = {
        "event_type": "page_view",
        "contact_hash": contact_hash(),
        "occurred_at": "2026-06-30T12:00:00Z",
        "page_id": "page-001",
    }

    validation = policy.validate_engagement_events([event, dict(event)])

    assert validation["status"] == "pass"
    assert validation["duplicate_events_ignored"] == 1
    assert len(validation["events"]) == 1


def test_materialize_engagement_batch_requires_dry_run(tmp_path: Path) -> None:
    events_path = tmp_path / "events.json"
    policy.write_json(
        events_path,
        {
            "events": [
                {
                    "event_type": "page_view",
                    "contact_hash": contact_hash(),
                    "occurred_at": "2026-06-30T12:00:00Z",
                    "page_id": "page-001",
                }
            ]
        },
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "materialize_sendr_engagement_batch_receipt.py"),
            "--campaign-id",
            "sendr-campaign-001",
            "--campaign-type",
            "SPONSOR_OUTREACH",
            "--event-batch",
            "batch-001",
            "--events",
            str(events_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "requires --dry-run" in result.stderr or "requires --dry-run" in result.stdout


def test_cli_materializes_engagement_and_verifies_suppression_sync(tmp_path: Path) -> None:
    events_path = tmp_path / "events.json"
    receipt_path = tmp_path / "engagement.json"
    validation_path = tmp_path / "suppression.json"
    policy.write_json(
        events_path,
        {
            "events": [
                {
                    "event_type": "unsubscribe",
                    "contact_hash": contact_hash("unsub@example.test"),
                    "occurred_at": "2026-06-30T12:00:00Z",
                }
            ]
        },
    )

    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "materialize_sendr_engagement_batch_receipt.py"),
            "--campaign-id",
            "sendr-campaign-001",
            "--campaign-type",
            "SPONSOR_OUTREACH",
            "--event-batch",
            "batch-001",
            "--events",
            str(events_path),
            "--dry-run",
            "--output",
            str(receipt_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "verify_sendr_suppression_sync.py"),
            "--batch",
            str(receipt_path),
            "--output",
            str(validation_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    assert receipt["campaign_type"] == "SPONSOR_OUTREACH"
    assert receipt["ea_actions"]["suppression_updates"] == 1
    assert validation["contract_name"] == policy.SUPPRESSION_VALIDATION_CONTRACT_NAME
    assert validation["status"] == "pass"


def test_reply_receipt_cli_writes_review_required_engagement_batch(tmp_path: Path) -> None:
    receipt_path = tmp_path / "reply.json"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "materialize_sendr_reply_receipt.py"),
            "--campaign-id",
            "sendr-campaign-001",
            "--campaign-type",
            "SPONSOR_OUTREACH",
            "--event-batch",
            "reply-batch-001",
            "--contact-hash",
            contact_hash(),
            "--occurred-at",
            "2026-06-30T12:00:00Z",
            "--preview",
            "Interested, please send details.",
            "--dry-run",
            "--output",
            str(receipt_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["contract_name"] == policy.ENGAGEMENT_CONTRACT_NAME
    assert receipt["status"] == "review_required"
    assert receipt["campaign_type"] == "SPONSOR_OUTREACH"
    assert receipt["ea_actions"]["draft_reply_candidates"] == 1
    assert receipt["ea_actions"]["sponsor_lead_candidates"] == 1
    assert receipt["ea_actions"]["auto_reply_allowed"] is False
