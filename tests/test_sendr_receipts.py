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


def test_dry_run_receipt_never_allows_direct_send_or_auto_reply() -> None:
    packet = policy.build_packet(
        packet_id="black-ledger-sponsor-pilot-001",
        campaign_type="SPONSOR_OUTREACH",
        source_paths=[],
        source_notes=[],
        root=ROOT,
    )
    validation = policy.validate_packet(packet)

    receipt = policy.build_receipt(packet, validation, dry_run=True)

    assert receipt["contract_name"] == policy.RECEIPT_CONTRACT_NAME
    assert receipt["status"] == "draft_review_required"
    assert receipt["provider"] == "sendr"
    assert receipt["license_tier"] == "AppSumo Tier 4"
    assert receipt["provider_lane"]["lane_key"] == "sendr_black_ledger_outreach"
    assert receipt["provider_lane"]["missing_state"] == "blocked_pending_proof"
    assert receipt["recommended_monthly_allocation_percent"]["black_ledger_sponsor_partner_outreach"] == 40
    assert receipt["first_pilot_campaigns"][0]["packet_id"] == "black-ledger-sponsor-pilot-001"
    assert "claim_validation" in {item["check_key"] for item in receipt["provider_lane"]["required_checks"]}
    assert len(receipt["approved_claims_sha256"]) == 64
    assert receipt["message_copy_sha256"] == ""
    assert receipt["personalized_page_template_sha256"] == ""
    assert receipt["video_script_sha256"] == ""
    assert receipt["direct_send_allowed"] is False
    assert receipt["limited_send_allowed"] is False
    assert receipt["auto_reply_allowed"] is False
    assert receipt["validation"]["human_review"] == "review_required"


def test_materialize_receipt_requires_dry_run(tmp_path: Path) -> None:
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
            str(SCRIPTS / "materialize_sendr_campaign_receipt.py"),
            "--packet",
            str(packet_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "requires --dry-run" in result.stderr or "requires --dry-run" in result.stdout


def test_materialize_receipt_dry_run_writes_review_required_receipt(tmp_path: Path) -> None:
    packet_path = tmp_path / "packet.json"
    receipt_path = tmp_path / "receipt.json"
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

    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "materialize_sendr_campaign_receipt.py"),
            "--packet",
            str(packet_path),
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
    assert receipt["status"] == "draft_review_required"
    assert receipt["dry_run"] is True
    assert receipt["direct_send_allowed"] is False
    assert receipt["sendr"]["campaign_id"] == ""
    assert receipt["provider_lane"]["integration_lane"] == "governed_outbound_growth"
