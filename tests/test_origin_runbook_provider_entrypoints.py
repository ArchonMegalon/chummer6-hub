from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module(name: str):
    script_path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runbook_packet_and_subscribr_receipt_roundtrip_passes(tmp_path: Path) -> None:
    build_packet = load_module("build_chummer_content_source_packet.py")
    materialize_receipt = load_module("materialize_subscribr_script_receipt.py")
    verify_receipt = load_module("verify_subscribr_script_against_packet.py")

    source_doc = tmp_path / "restore-guide.md"
    source_doc.write_text("Restore truth source.\n", encoding="utf-8")
    export_doc = tmp_path / "script.md"
    export_doc.write_text(
        "\n".join(
            [
                "Chummer validates rule-pack availability before trusting restore results.",
                "The restored workspace must show missing package warnings when required packages are absent.",
                "This walkthrough stays inside the approved receipt trail.",
            ]
        ),
        encoding="utf-8",
    )

    packet = build_packet.build_packet(
        argparse.Namespace(
            packet_id="runbook-restore-runner-2026-06-26",
            mode="RUNBOOK_STRICT",
            target_provider="subscribr",
            subscribr_channel_key="chummer-runbook",
            title="Restore a Runner After Reinstall",
            audience="returning Chummer users",
            language="en-US",
            target_output="video_script",
            target_words=1800,
            source_head=["chummer_core=sha-core", "chummer_ui=sha-ui"],
            source=[f"{source_doc}|desktop-update-truth|public"],
            allowed_claim=[
                "Chummer validates rule-pack availability before trusting restore results.",
                "The restored workspace must show missing package warnings when required packages are absent.",
            ],
            forbidden_claim=[
                "Chummer can restore every runner without source packs.",
                "The recovered result is always safe.",
            ],
            contains_private_runner=False,
            contains_gm_secret=False,
            contains_sourcebook_prose=False,
            human_review_required=True,
            gm_approval_required=False,
            player_approval_required=False,
            publication_allowed=False,
            expires_at="2026-07-03T00:00:00Z",
            out=None,
        )
    )
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")

    receipt = materialize_receipt.build_receipt(
        argparse.Namespace(
            packet=str(packet_path),
            markdown_export=str(export_doc),
            provider_channel_id="chan_123",
            provider_idea_id="idea_123",
            provider_script_id="script_123",
            out=None,
        )
    )
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    verified, passed = verify_receipt.verify_receipt(
        argparse.Namespace(receipt=str(receipt_path), out=None)
    )

    assert passed is True
    assert verified["status"] == "review_required"
    assert verified["validation"]["source_binding"] == "pass"
    assert verified["validation"]["required_claims"] == "pass"
    assert verified["validation"]["forbidden_claims"] == "pass"


def test_origin_packet_hashes_canon_and_mechanics_snapshot(tmp_path: Path) -> None:
    build_packet = load_module("build_origin_dossier_source_packet.py")

    source_doc = tmp_path / "origin-brief.md"
    source_doc.write_text("Origin source.\n", encoding="utf-8")
    canon_doc = tmp_path / "origin-canon.md"
    canon_doc.write_text("Approved origin canon.\n", encoding="utf-8")
    mechanics_doc = tmp_path / "mechanics.json"
    mechanics_doc.write_text('{"karma": 0}\n', encoding="utf-8")

    packet = build_packet.build_packet(
        argparse.Namespace(
            packet_id="origin-dossier-runner-kira-v1",
            mode="ORIGIN_DOSSIER_NARRATIVE",
            target_provider="subscribr",
            subscribr_channel_key="runner-origin-dossiers",
            title="Kira Origin Dossier",
            audience="player and GM",
            language="en-US",
            target_output="narration_script",
            target_words=None,
            runner_ref="runner:kira",
            campaign_ref="campaign:redmond",
            origin_canon_path=str(canon_doc),
            mechanics_snapshot_path=str(mechanics_doc),
            public_projection="player_safe",
            gm_secret_included=False,
            accepted_story_link=[
                "story-link:runner-switchback|runner:switchback|Switchback|They survived the same botched clinic extraction and owe the same fixer.|origin-story-link-consent:runner-switchback"
            ],
            shared_history_gm_review_required=True,
            source_head=["chummer_core=sha-core"],
            source=[f"{source_doc}|origin-canon|public"],
            allowed_claim=[
                "This is approved origin canon.",
                "This narration does not change mechanical legality.",
            ],
            forbidden_claim=[
                "This origin grants extra gear.",
                "This narration overrides the runner build.",
            ],
            contains_private_runner=False,
            contains_gm_secret=False,
            contains_sourcebook_prose=False,
            human_review_required=True,
            gm_approval_required=True,
            player_approval_required=True,
            publication_allowed=False,
            expires_at="2026-07-03T00:00:00Z",
            out=None,
        )
    )

    assert packet["origin_dossier"]["runner_ref"] == "runner:kira"
    assert packet["origin_dossier"]["campaign_ref"] == "campaign:redmond"
    assert len(packet["origin_dossier"]["origin_canon_sha256"]) == 64
    assert len(packet["origin_dossier"]["mechanics_snapshot_sha256"]) == 64
    assert packet["origin_dossier"]["accepted_runner_story_link_ids"] == ["story-link:runner-switchback"]
    assert packet["origin_dossier"]["shared_history_policy"] == {
        "requires_player_consent": True,
        "requires_gm_review": True,
        "provider_may_access_linked_runner_artifacts": False,
        "integration_scope": "origin_story_context_only",
    }
    story_link = packet["origin_dossier"]["shared_history_links"][0]
    assert story_link["linked_runner_ref"] == "runner:switchback"
    assert story_link["linked_runner_alias"] == "Switchback"
    assert story_link["consent_receipt_ref"] == "origin-story-link-consent:runner-switchback"


def test_subscribr_verifier_blocks_forbidden_claim(tmp_path: Path) -> None:
    build_packet = load_module("build_chummer_content_source_packet.py")
    materialize_receipt = load_module("materialize_subscribr_script_receipt.py")
    verify_receipt = load_module("verify_subscribr_script_against_packet.py")

    source_doc = tmp_path / "source.md"
    source_doc.write_text("Truth source.\n", encoding="utf-8")
    export_doc = tmp_path / "script.md"
    export_doc.write_text(
        "Chummer can restore every runner without source packs.\n",
        encoding="utf-8",
    )

    packet = build_packet.build_packet(
        argparse.Namespace(
            packet_id="runbook-fail",
            mode="RUNBOOK_VIDEO",
            target_provider="subscribr",
            subscribr_channel_key="chummer-runbook",
            title="Bad script",
            audience="test",
            language="en-US",
            target_output="video_script",
            target_words=None,
            source_head=["chummer_core=sha-core"],
            source=[f"{source_doc}|runbook-truth|public"],
            allowed_claim=["Only approved facts are allowed."],
            forbidden_claim=["Chummer can restore every runner without source packs."],
            contains_private_runner=False,
            contains_gm_secret=False,
            contains_sourcebook_prose=False,
            human_review_required=True,
            gm_approval_required=False,
            player_approval_required=False,
            publication_allowed=False,
            expires_at="2026-07-03T00:00:00Z",
            out=None,
        )
    )
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    receipt = materialize_receipt.build_receipt(
        argparse.Namespace(
            packet=str(packet_path),
            markdown_export=str(export_doc),
            provider_channel_id="chan",
            provider_idea_id="idea",
            provider_script_id="script",
            out=None,
        )
    )
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    verified, passed = verify_receipt.verify_receipt(
        argparse.Namespace(receipt=str(receipt_path), out=None)
    )

    assert passed is False
    assert verified["status"] == "validation_blocked"
    assert verified["validation"]["forbidden_claims"] == "blocked"


def test_firstbook_packet_and_receipt_verifier_passes(tmp_path: Path) -> None:
    build_packet = load_module("build_firstbook_premium_packet.py")
    materialize_receipt = load_module("materialize_firstbook_premium_receipt.py")
    verify_receipt = load_module("verify_firstbook_premium_receipt.py")

    outline = tmp_path / "outline.md"
    outline.write_text("# Outline\n", encoding="utf-8")
    chapter_one = tmp_path / "chapter-1.md"
    chapter_one.write_text("# Getting Started\n", encoding="utf-8")
    chapter_two = tmp_path / "chapter-2.md"
    chapter_two.write_text("# Recovery\n", encoding="utf-8")
    export_md = tmp_path / "manual.md"
    export_md.write_text("# Manual\n", encoding="utf-8")
    export_pdf = tmp_path / "manual.pdf"
    export_pdf.write_bytes(b"%PDF-1.7\nmanual\n")

    packet = build_packet.build_packet(
        argparse.Namespace(
            packet_id="chummer-beginner-manual-v1",
            source_packet_ref=["runbook-install-current", "runbook-restore-workspace"],
            book_title="Chummer Beginner's Manual",
            audience="new Shadowrun players using Chummer",
            style_profile="clear, practical, source-bound",
            chapter_count=2,
            forbidden_material=[
                "sourcebook copied prose",
                "private runner data",
                "GM-only campaign secrets",
                "unproven release claims",
            ],
            human_review_required_per_chapter=True,
            publication_allowed=False,
            out=None,
        )
    )
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")

    receipt = materialize_receipt.build_receipt(
        argparse.Namespace(
            packet=str(packet_path),
            outline=str(outline),
            chapter=[
                f"1|Getting Started|{chapter_one}|approved",
                f"2|Recovery|{chapter_two}|approved",
            ],
            export=[f"markdown|{export_md}", f"pdf|{export_pdf}"],
            out=None,
        )
    )
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    verified, passed = verify_receipt.verify_receipt(
        argparse.Namespace(receipt=str(receipt_path), out=None)
    )

    assert passed is True
    assert verified["status"] == "review_complete"
    assert verified["validation"]["source_binding"] == "pass"
    assert verified["validation"]["chapter_hashes"] == "pass"
    assert verified["validation"]["export_hashes"] == "pass"
