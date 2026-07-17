#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CONTRACT_NAME = "black_ledger.sendr_campaign_packet.v1"
RECEIPT_CONTRACT_NAME = "black_ledger.sendr_campaign_receipt.v1"
ENGAGEMENT_CONTRACT_NAME = "black_ledger.sendr_engagement_batch.v1"
SUPPRESSION_VALIDATION_CONTRACT_NAME = "black_ledger.sendr_suppression_sync_validation.v1"

ALLOWED_CAMPAIGN_TYPES = {
    "SPONSOR_OUTREACH": {
        "purpose": "book sponsor conversations",
        "max_contacts_without_extended_review": 50,
        "required_sources": (
            "approved_media_kit",
            "episode_or_pilot_brief",
            "audience_claim_receipt_or_pilot_wording",
            "cta",
        ),
        "allowed_recipient_basis": (
            "public_business_contact",
            "prior_conversation",
            "event_context",
            "opt_in",
            "manual_partner_shortlist",
            "inbound_inquiry",
            "explicit_introduction",
        ),
    },
    "GUEST_INVITE": {
        "purpose": "invite guest or interview participant",
        "max_contacts_without_extended_review": 25,
        "required_sources": (
            "episode_concept",
            "why_this_person",
            "release_recording_consent_language",
            "calendar_cta",
        ),
        "allowed_recipient_basis": (
            "public_creator_contact",
            "prior_conversation",
            "event_context",
            "opt_in",
            "explicit_introduction",
            "inbound_inquiry",
        ),
    },
    "CREATOR_COLLAB": {
        "purpose": "creator or community collaboration",
        "max_contacts_without_extended_review": 50,
        "required_sources": ("collab_proposal", "public_profile_source", "mutual_benefit", "clear_ask"),
        "allowed_recipient_basis": (
            "public_creator_contact",
            "public_business_contact",
            "prior_conversation",
            "event_context",
            "opt_in",
            "manual_partner_shortlist",
            "inbound_inquiry",
            "explicit_introduction",
        ),
    },
    "EPISODE_LAUNCH": {
        "purpose": "approved episode or newsletter link to lawful contacts",
        "max_contacts_without_extended_review": 50,
        "required_sources": ("approved_episode_link", "lawful_contact_basis", "suppression_receipt"),
        "allowed_recipient_basis": ("prior_conversation", "opt_in", "partner_list", "press_list_with_lawful_basis"),
    },
    "CHUMMER_ACADEMY_OUTREACH": {
        "purpose": "source-bound tutorial, guide, runbook, or explainer outreach",
        "max_contacts_without_extended_review": 50,
        "required_sources": ("source_bound_tutorial_packet", "no_sourcebook_replacement_wording", "chummer_truth_packet"),
        "allowed_recipient_basis": (
            "public_creator_contact",
            "public_business_contact",
            "prior_conversation",
            "event_context",
            "opt_in",
            "manual_partner_shortlist",
            "inbound_inquiry",
            "explicit_introduction",
        ),
    },
}

RECOMMENDED_MONTHLY_ALLOCATION = {
    "black_ledger_sponsor_partner_outreach": 40,
    "guest_interview_outreach": 25,
    "chummer_creator_community_outreach": 15,
    "episode_launch_newsletter_campaigns": 10,
    "testing_enrichment_bad_data_failed_campaigns": 10,
}

FIRST_THREE_CAMPAIGNS = (
    {
        "campaign_type": "SPONSOR_OUTREACH",
        "packet_id": "black-ledger-sponsor-pilot-001",
        "audience": "50 TTRPG-adjacent tool, accessory, software, or event sponsor contacts",
        "goal": "3-5 sponsor conversations",
        "channels": {"email": True, "linkedin": "manual_verified_only", "whatsapp": False},
        "asset": "personalized page with 30-45 second video, approved media-kit link, and short episode concept",
        "cta": "Worth a 15-minute sponsor fit call?",
        "required_proof": (
            "recipient_basis",
            "media_kit_hash",
            "pilot_audience_wording",
            "no_fake_audience_numbers",
            "suppression_list_checked",
        ),
    },
    {
        "campaign_type": "GUEST_INVITE",
        "packet_id": "black-ledger-guest-pilot-001",
        "audience": "25 creators, tool builders, GMs, designers, or community operators",
        "goal": "book 3 interviews",
        "channels": {"email": True, "linkedin": "manual_verified_only", "whatsapp": False},
        "asset": "personalized page with proposed episode angle",
        "cta": "Would you be open to a 30-minute recorded conversation?",
        "required_proof": (
            "appearance_consent_language",
            "recording_publication_consent",
            "guest_topic_approved",
            "no_implied_endorsement",
        ),
    },
    {
        "campaign_type": "CHUMMER_ACADEMY_OUTREACH",
        "packet_id": "black-ledger-chummer-academy-pilot-001",
        "audience": "50 community admins, tutorial creators, and newsletter authors",
        "goal": "get feedback or partners for Chummer tutorial content",
        "channels": {"email": True, "linkedin": "manual_verified_only", "whatsapp": False},
        "asset": "source-bound tutorial preview and why-this-helps-players summary",
        "cta": "Can I send you the draft guide for feedback?",
        "required_proof": (
            "no_sourcebook_replacement_wording",
            "no_copied_sourcebook_text",
            "chummer_truth_packet_attached",
        ),
    },
)

FORBIDDEN_RECIPIENT_BASIS = {
    "scraped_private_profile",
    "private_discord_member_export",
    "raw_email_inbox",
    "raw_ea_inbox",
    "purchased_personal_list_without_lawful_basis",
    "minor_contact",
}

FORBIDDEN_INPUT_MARKERS = {
    "sourcebook_pdf",
    "copied_rulebook_prose",
    "private_campaign_data",
    "raw_ea_inbox",
    "private_discord_member_export",
    "memorial_private_data",
    "sponsor_contract_truth",
    "direct_publish",
    "auto_reply",
    "unreviewed_claims",
}

FORBIDDEN_CLAIM_MARKERS = {
    "official shadowrun",
    "guarantee sponsor conversions",
    "guaranteed roi",
    "confirmed audience size",
    "official sourcebook",
    "publisher channel",
    "selected you",
    "reply today",
}

REQUIRED_RECIPIENT_FIELDS = (
    "recipient_basis",
    "source_url_or_source_note",
    "jurisdiction",
    "allowed_channel",
    "suppression_status",
    "last_verified_at",
)

ALLOWED_RECIPIENT_CHANNELS = {"email", "linkedin", "whatsapp"}
SETUP_READY_SUPPRESSION_STATUS = "clear"
BLOCKING_SUPPRESSION_STATUSES = {"pending_review", "suppressed"}

DISABLED_DEFAULT_ENV = (
    "BLACK_LEDGER_SENDR_ENABLED",
    "BLACK_LEDGER_SENDR_API_ENABLED",
    "BLACK_LEDGER_SENDR_WEBHOOKS_ENABLED",
    "BLACK_LEDGER_SENDR_LEAD_FINDER_ENABLED",
    "BLACK_LEDGER_SENDR_DYNAMIC_VIDEO_ENABLED",
    "BLACK_LEDGER_SENDR_LINKEDIN_ENABLED",
    "BLACK_LEDGER_SENDR_WHATSAPP_ENABLED",
    "BLACK_LEDGER_SENDR_DIRECT_SEND_ENABLED",
    "BLACK_LEDGER_SENDR_AUTO_REPLY_ENABLED",
)

APPROVAL_STATES = (
    "CAMPAIGN_PACKET_DRAFT",
    "CLAIMS_VALIDATED",
    "RECIPIENT_BASIS_VALIDATED",
    "COPY_REVIEW_REQUIRED",
    "SEND_APPROVAL_REQUIRED",
    "APPROVED_FOR_SENDR_SETUP",
    "SENDR_DRAFT_CREATED",
    "SENDR_PREVIEW_REVIEW",
    "APPROVED_FOR_LIMITED_SEND",
    "PILOT_RUNNING",
    "REPLY_REVIEW",
    "FOLLOW_UP_DRAFTED",
    "FOLLOW_UP_APPROVED",
    "CLOSED",
)

FAILURE_STATES = (
    "CLAIM_BLOCKED",
    "RECIPIENT_BASIS_BLOCKED",
    "SOURCE_STALE",
    "COMPLIANCE_BLOCKED",
    "PLATFORM_POLICY_BLOCKED",
    "UNSUBSCRIBE_REQUIRED",
    "BOUNCE_SUPPRESSION_REQUIRED",
    "REPLY_ESCALATION_REQUIRED",
)

PROVIDER_LANE_REQUIRED_CHECKS = (
    "inventory_recorded",
    "provider_verification",
    "recipient_basis",
    "suppression_sync",
    "claim_validation",
    "human_review",
    "reply_ingest",
)

PROVIDER_LANE_OFF_SWITCH_ENV = (
    "BLACK_LEDGER_SENDR_ENABLED",
    "BLACK_LEDGER_SENDR_API_ENABLED",
)

PROVIDER_LANE_ALLOWED_INPUTS = (
    "approved_media_kit",
    "approved_episode_brief",
    "approved_public_chummer_tutorial",
    "public_business_contact",
    "public_creator_contact",
    "prior_relationship_contact",
    "opt_in_contact",
)

SENDR_ALLOWED_STORAGE = (
    "business_contact_name",
    "business_email",
    "public_role_title",
    "company_or_creator_name",
    "public_website_or_profile",
    "campaign_specific_public_notes",
    "approved_personalization_tokens",
    "approved_black_ledger_links",
    "approved_public_video_audio",
)

SENDR_FORBIDDEN_STORAGE = (
    "private_campaign_logs",
    "private_chummer_user_data",
    "raw_ea_messages",
    "raw_telegram_whatsapp_private_chats",
    "sourcebook_pdfs",
    "copied_rulebook_prose",
    "memorial_material",
    "unpublished_sponsor_terms",
    "pricing_negotiations",
    "internal_strategy_notes",
    "unreviewed_claims",
)

EA_RETENTION_FIELDS = (
    "contact_hash",
    "source_note",
    "recipient_basis",
    "campaign_membership",
    "send_approval",
    "reply_event",
    "suppression_status",
)

COPY_POLICY = {
    "use": [
        "I am building a small editorial/newsroom project around Chummer and Shadowrun tooling.",
        "I thought your audience might care because ...",
        "I recorded a short personalized note here.",
        "Would it be worth a 15-minute fit call?",
        "No pressure - if this is not relevant, I will not follow up.",
    ],
    "avoid": [
        "official Shadowrun",
        "guaranteed reach",
        "massive audience",
        "sponsor now before it is too late",
        "we already selected you",
        "you need to reply today",
        "automated personalized surveillance",
    ],
    "sponsor_safe_wording": [
        "We are testing sponsor fit for a pilot run.",
        "Audience and distribution claims are limited to what we can currently prove.",
    ],
    "guest_safe_wording": [
        "This is an invitation, not an assumption that you are participating.",
        "Recording and publication would only happen after explicit approval.",
    ],
}

PROVIDER_LANE_FORBIDDEN_INPUTS = (
    "sourcebook_pdf",
    "copied_rulebook_prose",
    "private_campaign_data",
    "raw_ea_inbox",
    "private_discord_member_export",
    "memorial_private_data",
    "sponsor_contract_truth",
    "direct_publish",
    "auto_reply",
)

PROVIDER_LANE_NORMALIZED_SIGNAL_SCHEMA = (
    "recipient_basis",
    "source_url_or_note",
    "campaign_type",
    "channel",
    "message_copy_hash",
    "suppression_status",
    "reply_event_hash",
    "human_review_status",
)

ALLOWED_ENGAGEMENT_EVENT_TYPES = {
    "reply_received",
    "page_view",
    "video_view",
    "meeting_booked",
    "unsubscribe",
    "bounce",
    "delivery_failure",
    "negative_reply",
    "platform_complaint",
}

REVIEW_REQUIRED_EVENT_TYPES = {
    "reply_received",
    "meeting_booked",
    "negative_reply",
    "platform_complaint",
}

SUPPRESSION_EVENT_TYPES = {
    "unsubscribe": ("global_black_ledger", "unsubscribe"),
    "bounce": ("address", "bounce"),
    "delivery_failure": ("address", "delivery_failure"),
    "negative_reply": ("campaign_or_global_review", "negative_reply_review"),
    "platform_complaint": ("global_black_ledger", "platform_complaint"),
}

FORBIDDEN_RAW_EVENT_FIELDS = {
    "body",
    "full_body",
    "html_body",
    "message_body",
    "raw_body",
    "raw_event",
    "raw_payload",
    "raw_reply_body",
    "sendr_payload",
    "transcript",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_expires_iso() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=14)).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_campaign_type(value: str) -> str:
    normalized = value.strip().upper().replace("-", "_")
    if normalized not in ALLOWED_CAMPAIGN_TYPES:
        allowed = ", ".join(sorted(ALLOWED_CAMPAIGN_TYPES))
        raise ValueError(f"unsupported campaign type {value!r}; expected one of {allowed}")
    return normalized


def normalize_campaign_type_optional(value: str | None) -> str:
    if not value or not value.strip():
        return ""
    return normalize_campaign_type(value)


def provider_lane() -> dict[str, Any]:
    return {
        "lane_key": "sendr_black_ledger_outreach",
        "title": "Sendr Black Ledger Outbound Growth Lane",
        "providers": ["Sendr"],
        "integration_lane": "governed_outbound_growth",
        "verified_state": "verified_draft_operator_lane",
        "missing_state": "blocked_pending_proof",
        "off_switch_env": list(PROVIDER_LANE_OFF_SWITCH_ENV),
        "source_of_truth": (
            "Black Ledger editorial packets, Chummer source packets, and human review own claims "
            "and publication truth. Sendr sequences approved outreach only."
        ),
        "allowed_inputs": list(PROVIDER_LANE_ALLOWED_INPUTS),
        "forbidden_inputs": list(PROVIDER_LANE_FORBIDDEN_INPUTS),
        "normalized_signal_schema": list(PROVIDER_LANE_NORMALIZED_SIGNAL_SCHEMA),
        "recommended_monthly_allocation_percent": dict(RECOMMENDED_MONTHLY_ALLOCATION),
        "first_pilot_campaigns": list(FIRST_THREE_CAMPAIGNS),
        "required_checks": [
            {
                "check_key": "inventory_recorded",
                "description": "Sendr Tier 4 is recorded.",
                "evidence": "LTD inventory row.",
            },
            {
                "check_key": "provider_verification",
                "description": "Account and tier are verified.",
                "evidence": "Provider receipt.",
            },
            {
                "check_key": "recipient_basis",
                "description": "Every recipient has lawful/approved basis.",
                "evidence": "Recipient-basis receipt.",
            },
            {
                "check_key": "suppression_sync",
                "description": "Suppression list is fail-closed.",
                "evidence": "Suppression receipt.",
            },
            {
                "check_key": "claim_validation",
                "description": "Campaign claims bind to approved packets.",
                "evidence": "Claim receipt.",
            },
            {
                "check_key": "human_review",
                "description": "Send requires human approval.",
                "evidence": "Approval receipt.",
            },
            {
                "check_key": "reply_ingest",
                "description": "Replies become review candidates, not automatic actions.",
                "evidence": "Reply receipt.",
            },
        ],
    }


def build_source_material(source_paths: list[str], source_notes: list[str], root: Path) -> list[dict[str, Any]]:
    materials: list[dict[str, Any]] = []
    for raw_path in source_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = root / path
        display_path = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        materials.append(
            {
                "path": display_path,
                "sha256": sha256_file(path),
                "classification": "approved_public",
            }
        )

    for note in source_notes:
        clean_note = note.strip()
        if clean_note:
            materials.append(
                {
                    "source_note": clean_note,
                    "sha256": sha256_text(clean_note),
                    "classification": "approved_public",
                }
            )

    return materials


def build_packet(
    *,
    packet_id: str,
    campaign_type: str,
    source_paths: list[str],
    source_notes: list[str],
    root: Path,
    owner: str = "black_ledger_editorial",
    target_audience: str = "TTRPG-adjacent sponsor, guest, creator, or community contacts",
    max_contacts: int | None = None,
) -> dict[str, Any]:
    normalized_type = normalize_campaign_type(campaign_type)
    policy = ALLOWED_CAMPAIGN_TYPES[normalized_type]
    limit = max_contacts if max_contacts is not None else int(policy["max_contacts_without_extended_review"])
    return {
        "contract_name": CONTRACT_NAME,
        "packet_id": packet_id,
        "campaign_type": normalized_type,
        "project": "black_ledger",
        "owner": owner,
        "target_audience": target_audience,
        "jurisdiction_policy": "b2b_outreach_review_required",
        "approval_state": "CAMPAIGN_PACKET_DRAFT",
        "approval_state_machine": {
            "states": list(APPROVAL_STATES),
            "failure_states": list(FAILURE_STATES),
        },
        "provider_lane": provider_lane(),
        "provider_boundaries": {
            "sendr_may_help_with": [
                "sponsor_outreach",
                "guest_interview_outreach",
                "creator_collaboration_outreach",
                "newsletter_episode_launch_outreach",
                "gm_community_partner_outreach",
                "convention_event_outreach",
                "pilot_user_recruitment",
                "warm_reactivation_campaigns",
                "personalized_black_ledger_landing_pages",
                "personalized_video_audio_introductions",
            ],
            "sendr_must_not_own": [
                "chummer_rules_truth",
                "black_ledger_editorial_truth",
                "sourcebook_interpretation",
                "release_truth",
                "support_truth",
                "community_moderation_truth",
                "sponsor_contract_truth",
                "private_campaign_material",
                "memorial_private_material",
                "automatic_publishing",
                "automatic_commitments",
            ],
        },
        "sendr_storage_policy": {
            "allowed": list(SENDR_ALLOWED_STORAGE),
            "forbidden": list(SENDR_FORBIDDEN_STORAGE),
        },
        "data_retention_policy": {
            "ea_black_ledger_store": list(EA_RETENTION_FIELDS),
            "raw_sendr_data_stored": False,
            "raw_reply_bodies_stored": False,
            "suppression_fail_closed": True,
        },
        "copy_policy": COPY_POLICY,
        "recommended_monthly_allocation_percent": dict(RECOMMENDED_MONTHLY_ALLOCATION),
        "first_pilot_campaigns": list(FIRST_THREE_CAMPAIGNS),
        "source_requirements": list(policy["required_sources"]),
        "source_material": build_source_material(source_paths, source_notes, root),
        "allowed_claims": [
            "Black Ledger is a Chummer-adjacent editorial/newsroom project.",
            "The campaign is seeking conversations, not final commitments.",
            "Audience and distribution claims must be receipt-backed or described as pilot/projected.",
        ],
        "forbidden_claims": [
            "We are the official Shadowrun publisher.",
            "We guarantee sponsor conversions.",
            "We have a confirmed audience size unless receipt-backed.",
            "This is an official sourcebook channel.",
        ],
        "recipient_policy": {
            "allowed_recipient_basis": list(policy["allowed_recipient_basis"]),
            "forbidden_recipient_basis": sorted(FORBIDDEN_RECIPIENT_BASIS),
            "required_contact_fields": list(REQUIRED_RECIPIENT_FIELDS),
        },
        "recipient_records": [],
        "recipient_count": 0,
        "channels": {
            "email": True,
            "linkedin": normalized_type != "EPISODE_LAUNCH",
            "whatsapp": False,
        },
        "sendr_features_allowed": {
            "lead_finder": normalized_type in {"SPONSOR_OUTREACH", "GUEST_INVITE", "CREATOR_COLLAB"},
            "data_enrichment": True,
            "personalized_pages": True,
            "dynamic_video": True,
            "sequencer": True,
            "whatsapp": False,
        },
        "feature_flags_required_disabled": list(DISABLED_DEFAULT_ENV),
        "human_review_required": True,
        "direct_send_allowed": False,
        "publication_allowed": False,
        "auto_reply_allowed": False,
        "limited_send_allowed": False,
        "max_contacts": limit,
        "created_at_utc": now_iso(),
        "expires_at": default_expires_iso(),
    }


def _record_failure(failures: list[str], code: str, detail: str) -> None:
    failures.append(f"{code}: {detail}")


def validate_packet(packet: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}

    if packet.get("contract_name") != CONTRACT_NAME:
        _record_failure(failures, "contract_name", f"expected {CONTRACT_NAME}")

    campaign_type = str(packet.get("campaign_type", "")).strip().upper()
    if campaign_type not in ALLOWED_CAMPAIGN_TYPES:
        _record_failure(failures, "campaign_type", f"unsupported campaign type {campaign_type!r}")
        policy = {"required_sources": (), "allowed_recipient_basis": (), "max_contacts_without_extended_review": 0}
    else:
        policy = ALLOWED_CAMPAIGN_TYPES[campaign_type]

    if packet.get("project") != "black_ledger":
        _record_failure(failures, "project", "packet must stay scoped to black_ledger")

    approval_state = str(packet.get("approval_state", "")).strip().upper()
    if approval_state not in set(APPROVAL_STATES).union(FAILURE_STATES):
        _record_failure(failures, "approval_state", "approval_state must be in the Sendr approval state machine")

    state_machine = packet.get("approval_state_machine") if isinstance(packet.get("approval_state_machine"), dict) else {}
    missing_states = [state for state in APPROVAL_STATES if state not in state_machine.get("states", [])]
    missing_failure_states = [state for state in FAILURE_STATES if state not in state_machine.get("failure_states", [])]
    if missing_states or missing_failure_states:
        _record_failure(failures, "approval_state_machine", "packet must include the full approval and failure state machine")

    lane = packet.get("provider_lane") if isinstance(packet.get("provider_lane"), dict) else {}
    lane_providers = lane.get("providers") if isinstance(lane.get("providers"), list) else []
    lane_off_switches = lane.get("off_switch_env") if isinstance(lane.get("off_switch_env"), list) else []
    lane_required_checks = lane.get("required_checks") if isinstance(lane.get("required_checks"), list) else []
    lane_forbidden_inputs = lane.get("forbidden_inputs") if isinstance(lane.get("forbidden_inputs"), list) else []
    lane_signal_schema = lane.get("normalized_signal_schema") if isinstance(lane.get("normalized_signal_schema"), list) else []
    lane_check_keys = {
        str(item.get("check_key"))
        for item in lane_required_checks
        if isinstance(item, dict) and item.get("check_key")
    }
    if lane.get("lane_key") != "sendr_black_ledger_outreach":
        _record_failure(failures, "provider_lane", "provider lane must be sendr_black_ledger_outreach")
    if "Sendr" not in lane_providers:
        _record_failure(failures, "provider_lane", "provider lane must name Sendr")
    if lane.get("integration_lane") != "governed_outbound_growth":
        _record_failure(failures, "provider_lane", "integration lane must be governed_outbound_growth")
    missing_off_switches = [key for key in PROVIDER_LANE_OFF_SWITCH_ENV if key not in lane_off_switches]
    if missing_off_switches:
        _record_failure(failures, "provider_lane", "missing off-switch env: " + ", ".join(missing_off_switches))
    missing_checks = [key for key in PROVIDER_LANE_REQUIRED_CHECKS if key not in lane_check_keys]
    if missing_checks:
        _record_failure(failures, "provider_lane", "missing required checks: " + ", ".join(missing_checks))
    missing_forbidden_inputs = [key for key in PROVIDER_LANE_FORBIDDEN_INPUTS if key not in lane_forbidden_inputs]
    if missing_forbidden_inputs:
        _record_failure(failures, "provider_lane", "missing forbidden inputs: " + ", ".join(missing_forbidden_inputs))
    missing_signal_fields = [key for key in PROVIDER_LANE_NORMALIZED_SIGNAL_SCHEMA if key not in lane_signal_schema]
    if missing_signal_fields:
        _record_failure(failures, "provider_lane", "missing normalized signal fields: " + ", ".join(missing_signal_fields))
    allocation = lane.get("recommended_monthly_allocation_percent") if isinstance(lane.get("recommended_monthly_allocation_percent"), dict) else {}
    if allocation and sum(int(value) for value in allocation.values()) != 100:
        _record_failure(failures, "provider_lane", "recommended monthly allocation must total 100 percent")

    channels = packet.get("channels") if isinstance(packet.get("channels"), dict) else {}
    features = packet.get("sendr_features_allowed") if isinstance(packet.get("sendr_features_allowed"), dict) else {}
    if channels.get("whatsapp") is not False:
        _record_failure(failures, "whatsapp_channel", "WhatsApp must remain disabled by default")
    if features.get("whatsapp") is not False:
        _record_failure(failures, "whatsapp_feature", "Sendr WhatsApp feature must remain disabled by default")
    if packet.get("direct_send_allowed") is not False:
        _record_failure(failures, "direct_send", "direct send must be false")
    if packet.get("publication_allowed") is not False:
        _record_failure(failures, "publication", "publication must be false")
    if packet.get("auto_reply_allowed") is not False:
        _record_failure(failures, "auto_reply", "auto reply must be false")
    if packet.get("human_review_required") is not True:
        _record_failure(failures, "human_review", "human review must be required")

    boundaries = packet.get("provider_boundaries") if isinstance(packet.get("provider_boundaries"), dict) else {}
    forbidden_ownership = boundaries.get("sendr_must_not_own") if isinstance(boundaries.get("sendr_must_not_own"), list) else []
    for required_boundary in ("chummer_rules_truth", "black_ledger_editorial_truth", "automatic_commitments"):
        if required_boundary not in forbidden_ownership:
            _record_failure(failures, "provider_boundaries", f"missing forbidden ownership {required_boundary}")

    storage_policy = packet.get("sendr_storage_policy") if isinstance(packet.get("sendr_storage_policy"), dict) else {}
    storage_forbidden = storage_policy.get("forbidden") if isinstance(storage_policy.get("forbidden"), list) else []
    for required_storage_block in ("private_chummer_user_data", "sourcebook_pdfs", "unreviewed_claims"):
        if required_storage_block not in storage_forbidden:
            _record_failure(failures, "sendr_storage_policy", f"missing forbidden storage {required_storage_block}")

    retention_policy = packet.get("data_retention_policy") if isinstance(packet.get("data_retention_policy"), dict) else {}
    retained_fields = retention_policy.get("ea_black_ledger_store") if isinstance(retention_policy.get("ea_black_ledger_store"), list) else []
    for retained_field in ("contact_hash", "recipient_basis", "suppression_status"):
        if retained_field not in retained_fields:
            _record_failure(failures, "data_retention_policy", f"missing retained field {retained_field}")
    if retention_policy.get("raw_sendr_data_stored") is not False:
        _record_failure(failures, "data_retention_policy", "raw Sendr data storage must be false")
    if retention_policy.get("raw_reply_bodies_stored") is not False:
        _record_failure(failures, "data_retention_policy", "raw reply body storage must be false")
    if retention_policy.get("suppression_fail_closed") is not True:
        _record_failure(failures, "data_retention_policy", "suppression sync must fail closed")

    copy_policy = packet.get("copy_policy") if isinstance(packet.get("copy_policy"), dict) else {}
    copy_avoid = copy_policy.get("avoid") if isinstance(copy_policy.get("avoid"), list) else []
    for required_copy_block in ("official Shadowrun", "guaranteed reach", "automated personalized surveillance"):
        if required_copy_block not in copy_avoid:
            _record_failure(failures, "copy_policy", f"missing avoid wording {required_copy_block}")

    source_material = packet.get("source_material")
    if not isinstance(source_material, list):
        _record_failure(failures, "source_material", "source_material must be a list")
        source_material = []
    approved_sources = 0
    forbidden_source_hits: list[str] = []
    for index, item in enumerate(source_material):
        if not isinstance(item, dict):
            _record_failure(failures, "source_material", f"source material {index} must be an object")
            continue
        classification = str(item.get("classification", "")).strip().lower()
        haystack = " ".join(str(item.get(key, "")) for key in ("path", "source_note", "classification")).lower()
        hits = sorted(marker for marker in FORBIDDEN_INPUT_MARKERS if marker in haystack)
        forbidden_source_hits.extend(hits)
        if classification == "approved_public" and (item.get("path") or item.get("source_note")) and item.get("sha256"):
            approved_sources += 1
        elif classification:
            warnings.append(f"source_material[{index}] is not approved_public")

    if forbidden_source_hits:
        _record_failure(failures, "forbidden_source_material", ", ".join(sorted(set(forbidden_source_hits))))

    missing_sources = list(policy.get("required_sources", ())) if approved_sources == 0 else []
    checks["source_material"] = {
        "approved_public_count": approved_sources,
        "missing_required_sources": missing_sources,
    }

    allowed_claims = packet.get("allowed_claims") if isinstance(packet.get("allowed_claims"), list) else []
    forbidden_claims = packet.get("forbidden_claims") if isinstance(packet.get("forbidden_claims"), list) else []
    claim_haystack = " ".join(str(value).lower() for value in allowed_claims)
    forbidden_claim_hits = sorted(marker for marker in FORBIDDEN_CLAIM_MARKERS if marker in claim_haystack)
    if forbidden_claim_hits:
        _record_failure(failures, "forbidden_allowed_claim", ", ".join(forbidden_claim_hits))
    if not forbidden_claims:
        _record_failure(failures, "forbidden_claims", "forbidden_claims must be explicit")

    recipient_policy = packet.get("recipient_policy") if isinstance(packet.get("recipient_policy"), dict) else {}
    allowed_bases = {str(value) for value in recipient_policy.get("allowed_recipient_basis", [])}
    forbidden_bases = {str(value) for value in recipient_policy.get("forbidden_recipient_basis", [])}
    missing_forbidden = FORBIDDEN_RECIPIENT_BASIS.difference(forbidden_bases)
    if missing_forbidden:
        _record_failure(failures, "recipient_policy", "missing forbidden bases: " + ", ".join(sorted(missing_forbidden)))
    allowed_by_type = set(policy.get("allowed_recipient_basis", ()))
    unexpected_allowed = allowed_bases.difference(allowed_by_type)
    if unexpected_allowed:
        _record_failure(failures, "recipient_policy", "unexpected allowed bases: " + ", ".join(sorted(unexpected_allowed)))

    records = packet.get("recipient_records") if isinstance(packet.get("recipient_records"), list) else []
    recipient_failures: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            recipient_failures.append(f"recipient_records[{index}] must be an object")
            continue
        missing = [field for field in REQUIRED_RECIPIENT_FIELDS if not str(record.get(field, "")).strip()]
        if missing:
            recipient_failures.append(f"recipient_records[{index}] missing {', '.join(missing)}")
        basis = str(record.get("recipient_basis", "")).strip()
        if basis in FORBIDDEN_RECIPIENT_BASIS:
            recipient_failures.append(f"recipient_records[{index}] uses forbidden basis {basis}")
        elif basis and basis not in allowed_bases:
            recipient_failures.append(f"recipient_records[{index}] basis {basis} is not allowed")
        suppression_status = str(record.get("suppression_status", "")).strip().lower()
        if suppression_status not in {"clear", "suppressed", "pending_review"}:
            recipient_failures.append(f"recipient_records[{index}] has invalid suppression_status")
        elif suppression_status != SETUP_READY_SUPPRESSION_STATUS:
            recipient_failures.append(
                f"recipient_records[{index}] suppression_status must be clear before Sendr setup"
            )
        allowed_channel = str(record.get("allowed_channel", "")).strip().lower()
        if allowed_channel and allowed_channel not in ALLOWED_RECIPIENT_CHANNELS:
            recipient_failures.append(f"recipient_records[{index}] has invalid allowed_channel {allowed_channel}")
        elif allowed_channel:
            if allowed_channel == "whatsapp":
                recipient_failures.append(f"recipient_records[{index}] uses WhatsApp while WhatsApp is disabled")
            elif channels.get(allowed_channel) is not True:
                recipient_failures.append(
                    f"recipient_records[{index}] allowed_channel {allowed_channel} is disabled for this campaign"
                )
    if recipient_failures:
        _record_failure(failures, "recipient_records", "; ".join(recipient_failures))

    declared_count = int(packet.get("recipient_count") or len(records) or 0)
    max_contacts = int(packet.get("max_contacts") or policy.get("max_contacts_without_extended_review") or 0)
    if declared_count != len(records):
        warnings.append("recipient_count does not match recipient_records length")
    if declared_count > max_contacts:
        _record_failure(failures, "recipient_limit", f"recipient_count {declared_count} exceeds max_contacts {max_contacts}")

    checks["recipient_policy"] = {
        "record_count": len(records),
        "declared_count": declared_count,
        "missing_records": len(records) == 0,
        "required_fields": list(REQUIRED_RECIPIENT_FIELDS),
    }

    disabled_defaults = packet.get("feature_flags_required_disabled")
    if not isinstance(disabled_defaults, list):
        _record_failure(failures, "feature_flags_required_disabled", "must list fail-closed Sendr feature flags")
    else:
        missing_defaults = [key for key in DISABLED_DEFAULT_ENV if key not in disabled_defaults]
        if missing_defaults:
            _record_failure(failures, "feature_flags_required_disabled", "missing " + ", ".join(missing_defaults))

    ready_for_sendr_setup = not failures and approved_sources > 0 and len(records) > 0
    return {
        "contract_name": "black_ledger.sendr_campaign_packet_validation.v1",
        "status": "fail" if failures else "pass",
        "readiness_status": "ready_for_review" if ready_for_sendr_setup else "review_required",
        "ready_for_sendr_setup": ready_for_sendr_setup,
        "packet_id": packet.get("packet_id", ""),
        "campaign_type": campaign_type,
        "checks": checks,
        "failures": failures,
        "warnings": warnings,
        "generated_at_utc": now_iso(),
    }


def packet_hash(packet: dict[str, Any]) -> str:
    return sha256_text(json.dumps(packet, sort_keys=True, separators=(",", ":")))


def build_receipt(packet: dict[str, Any], validation: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    ready = bool(validation.get("ready_for_sendr_setup"))
    approved_claims_sha256 = sha256_text(json.dumps(packet.get("allowed_claims", []), sort_keys=True, separators=(",", ":")))
    return {
        "contract_name": RECEIPT_CONTRACT_NAME,
        "status": "draft_ready_for_sendr_setup" if ready else "draft_review_required",
        "provider": "sendr",
        "license_tier": "AppSumo Tier 4",
        "provider_lane": provider_lane(),
        "recommended_monthly_allocation_percent": dict(RECOMMENDED_MONTHLY_ALLOCATION),
        "first_pilot_campaigns": list(FIRST_THREE_CAMPAIGNS),
        "packet_id": packet.get("packet_id", ""),
        "campaign_type": packet.get("campaign_type", ""),
        "source_packet_sha256": packet_hash(packet),
        "approved_claims_sha256": approved_claims_sha256,
        "message_copy_sha256": str(packet.get("message_copy_sha256") or ""),
        "personalized_page_template_sha256": str(packet.get("personalized_page_template_sha256") or ""),
        "video_script_sha256": str(packet.get("video_script_sha256") or ""),
        "recipient_policy": {
            "recipient_count": int(packet.get("recipient_count") or 0),
            "recipient_basis": sorted({
                str(record.get("recipient_basis"))
                for record in packet.get("recipient_records", [])
                if isinstance(record, dict) and record.get("recipient_basis")
            }),
            "blocked_recipient_count": 0,
            "suppression_checked": ready,
        },
        "channels": packet.get("channels", {}),
        "sendr": {
            "campaign_id": "",
            "sequence_id": "",
            "page_template_id": "",
            "dynamic_video_id": "",
        },
        "validation": {
            "claims": "pass" if not any("claim" in failure for failure in validation.get("failures", [])) else "fail",
            "recipient_basis": "pass" if not any("recipient" in failure for failure in validation.get("failures", [])) else "fail",
            "platform_policy": "pass" if validation.get("status") == "pass" else "fail",
            "copyright": "pass" if not any("source" in failure for failure in validation.get("failures", [])) else "fail",
            "privacy": "pass" if not any("private" in failure for failure in validation.get("failures", [])) else "fail",
            "suppression": "pass" if ready else "review_required",
            "human_review": "review_required",
        },
        "human_review": {
            "reviewer": "",
            "reviewed_at": "",
            "approval_scope": "",
        },
        "dry_run": dry_run,
        "direct_send_allowed": False,
        "limited_send_allowed": False,
        "max_contacts": int(packet.get("max_contacts") or 0),
        "auto_reply_allowed": False,
        "generated_at_utc": now_iso(),
        "validation_summary": validation,
    }


def _event_hash(event: dict[str, Any]) -> str:
    stable = {
        "event_id": event.get("event_id", ""),
        "event_type": event.get("event_type", ""),
        "contact_hash": event.get("contact_hash", ""),
        "occurred_at": event.get("occurred_at", ""),
        "page_id": event.get("page_id", ""),
        "duration_seconds": event.get("duration_seconds", ""),
        "preview": event.get("preview", ""),
    }
    return sha256_text(json.dumps(stable, sort_keys=True, separators=(",", ":")))


def _short_preview(value: Any) -> str:
    preview = " ".join(str(value or "").split())
    if len(preview) > 240:
        return preview[:237].rstrip() + "..."
    return preview


def validate_engagement_events(events: Any) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    normalized_events: list[dict[str, Any]] = []
    duplicate_count = 0
    seen_hashes: set[str] = set()

    if not isinstance(events, list):
        _record_failure(failures, "events", "events must be a list")
        events = []

    for index, event in enumerate(events):
        if not isinstance(event, dict):
            _record_failure(failures, "events", f"events[{index}] must be an object")
            continue

        raw_hits = sorted(key for key in event if key.lower() in FORBIDDEN_RAW_EVENT_FIELDS)
        if raw_hits:
            _record_failure(
                failures,
                "raw_body_storage",
                f"events[{index}] contains forbidden raw Sendr fields: {', '.join(raw_hits)}",
            )

        event_type = str(event.get("event_type", "")).strip().lower()
        if event_type not in ALLOWED_ENGAGEMENT_EVENT_TYPES:
            _record_failure(failures, "event_type", f"events[{index}] unsupported event_type {event_type!r}")

        contact_hash = str(event.get("contact_hash", "")).strip()
        if not contact_hash:
            _record_failure(failures, "contact_hash", f"events[{index}] missing contact_hash")
        elif "@" in contact_hash or any(character.isspace() for character in contact_hash):
            _record_failure(failures, "contact_hash", f"events[{index}] contact_hash must not contain raw contact data")
        elif len(contact_hash) < 8:
            _record_failure(failures, "contact_hash", f"events[{index}] contact_hash is too short")

        occurred_at = str(event.get("occurred_at", "")).strip()
        if not occurred_at:
            _record_failure(failures, "occurred_at", f"events[{index}] missing occurred_at")

        raw_body_stored = event.get("raw_body_stored", False)
        if raw_body_stored is not False:
            _record_failure(failures, "raw_body_stored", f"events[{index}] must set raw_body_stored=false")

        if event_type in REVIEW_REQUIRED_EVENT_TYPES and event.get("human_review_required") is False:
            _record_failure(failures, "human_review", f"events[{index}] {event_type} must require human review")

        normalized: dict[str, Any] = {
            "event_type": event_type,
            "contact_hash": contact_hash,
            "occurred_at": occurred_at,
            "raw_body_stored": False,
            "human_review_required": event_type in REVIEW_REQUIRED_EVENT_TYPES,
            "suppression_required": event_type in SUPPRESSION_EVENT_TYPES,
        }

        if event.get("event_id"):
            normalized["event_id"] = str(event.get("event_id"))
        if event.get("preview"):
            normalized["preview"] = _short_preview(event.get("preview"))
        if event.get("page_id"):
            normalized["page_id"] = str(event.get("page_id"))
        if "duration_seconds" in event:
            try:
                duration_seconds = int(event.get("duration_seconds") or 0)
            except (TypeError, ValueError):
                duration_seconds = -1
            if duration_seconds < 0:
                _record_failure(failures, "duration_seconds", f"events[{index}] duration_seconds must be non-negative")
            normalized["duration_seconds"] = max(duration_seconds, 0)

        normalized["event_hash"] = _event_hash(normalized)
        if normalized["event_hash"] in seen_hashes:
            duplicate_count += 1
            warnings.append(f"events[{index}] duplicate ignored")
            continue
        seen_hashes.add(normalized["event_hash"])
        normalized_events.append(normalized)

    return {
        "status": "fail" if failures else "pass",
        "failures": failures,
        "warnings": warnings,
        "duplicate_events_ignored": duplicate_count,
        "events": normalized_events,
    }


def _lead_candidate_type_for_campaign(campaign_type: str) -> str:
    if campaign_type == "SPONSOR_OUTREACH":
        return "SponsorLeadCandidate"
    if campaign_type == "GUEST_INVITE":
        return "GuestLeadCandidate"
    if campaign_type in {"CREATOR_COLLAB", "CHUMMER_ACADEMY_OUTREACH"}:
        return "CreatorPartnerCandidate"
    return ""


def build_engagement_batch(
    *,
    campaign_id: str,
    event_batch_id: str,
    events: list[dict[str, Any]],
    dry_run: bool,
    campaign_type: str = "",
) -> dict[str, Any]:
    normalized_campaign_type = normalize_campaign_type_optional(campaign_type)
    validation = validate_engagement_events(events)
    normalized_events = validation["events"]
    reply_candidates = sum(1 for event in normalized_events if event["event_type"] in {"reply_received", "negative_reply"})
    commitment_candidates = sum(1 for event in normalized_events if event["event_type"] == "meeting_booked")
    lead_candidate_type = _lead_candidate_type_for_campaign(normalized_campaign_type)
    review_candidates: list[dict[str, Any]] = []

    for event in normalized_events:
        event_type = event["event_type"]
        if event_type in {"reply_received", "meeting_booked"} and lead_candidate_type:
            review_candidates.append(
                {
                    "candidate_type": lead_candidate_type,
                    "event_hash": event["event_hash"],
                    "contact_hash": event["contact_hash"],
                    "human_review_required": True,
                    "automatic_commitment_created": False,
                    "raw_body_stored": False,
                }
            )
        if event_type in {"reply_received", "negative_reply"}:
            review_candidates.append(
                {
                    "candidate_type": "DraftReplyCandidate",
                    "event_hash": event["event_hash"],
                    "contact_hash": event["contact_hash"],
                    "human_review_required": True,
                    "auto_reply_allowed": False,
                    "raw_body_stored": False,
                }
            )
        if event_type == "meeting_booked":
            review_candidates.append(
                {
                    "candidate_type": "CommitmentCandidate",
                    "event_hash": event["event_hash"],
                    "contact_hash": event["contact_hash"],
                    "human_review_required": True,
                    "automatic_commitment_created": False,
                }
            )
        review_candidates.append(
            {
                "candidate_type": "Evidence",
                "event_hash": event["event_hash"],
                "contact_hash": event["contact_hash"],
                "human_review_required": event_type in REVIEW_REQUIRED_EVENT_TYPES,
                "raw_body_stored": False,
            }
        )

    suppression_events = []
    for event in normalized_events:
        suppression_policy = SUPPRESSION_EVENT_TYPES.get(event["event_type"])
        if not suppression_policy:
            continue
        scope, reason = suppression_policy
        suppression_events.append(
            {
                "contact_hash": event["contact_hash"],
                "event_hash": event["event_hash"],
                "reason": reason,
                "scope": scope,
                "human_review_required": event["event_type"] in {"negative_reply"},
                "raw_body_stored": False,
            }
        )

    return {
        "contract_name": ENGAGEMENT_CONTRACT_NAME,
        "status": "review_required" if validation["status"] == "pass" else "blocked",
        "provider": "sendr",
        "provider_lane": provider_lane(),
        "campaign_id": campaign_id,
        "campaign_type": normalized_campaign_type,
        "event_batch_id": event_batch_id,
        "events": normalized_events,
        "ea_actions": {
            "draft_reply_candidates": reply_candidates,
            "sponsor_lead_candidates": sum(1 for item in review_candidates if item["candidate_type"] == "SponsorLeadCandidate"),
            "guest_lead_candidates": sum(1 for item in review_candidates if item["candidate_type"] == "GuestLeadCandidate"),
            "creator_partner_candidates": sum(1 for item in review_candidates if item["candidate_type"] == "CreatorPartnerCandidate"),
            "commitment_candidates": commitment_candidates,
            "commitment_candidates_created": 0,
            "review_candidates": review_candidates,
            "suppression_updates": len(suppression_events),
            "suppression_events": suppression_events,
            "raw_body_stored": False,
            "auto_reply_allowed": False,
            "automatic_commitments_allowed": False,
            "public_announcement_allowed": False,
        },
        "dry_run": dry_run,
        "validation": validation,
        "generated_at_utc": now_iso(),
    }


def validate_suppression_sync(batch: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []

    if batch.get("contract_name") != ENGAGEMENT_CONTRACT_NAME:
        _record_failure(failures, "contract_name", f"expected {ENGAGEMENT_CONTRACT_NAME}")

    events = batch.get("events") if isinstance(batch.get("events"), list) else []
    ea_actions = batch.get("ea_actions") if isinstance(batch.get("ea_actions"), dict) else {}
    suppression_events = ea_actions.get("suppression_events") if isinstance(ea_actions.get("suppression_events"), list) else []
    if int(ea_actions.get("suppression_updates") or 0) != len(suppression_events):
        _record_failure(failures, "suppression_count", "suppression_updates must match suppression_events length")
    if ea_actions.get("raw_body_stored") is not False:
        _record_failure(failures, "raw_body_stored", "raw reply bodies must not be stored")
    if ea_actions.get("auto_reply_allowed") is not False:
        _record_failure(failures, "auto_reply", "auto reply must remain disabled")
    if ea_actions.get("automatic_commitments_allowed") is not False:
        _record_failure(failures, "automatic_commitments", "engagement must not create automatic commitments")

    suppression_by_hash = {
        str(item.get("event_hash", "")): item
        for item in suppression_events
        if isinstance(item, dict) and item.get("event_hash")
    }
    required_count = 0
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            _record_failure(failures, "events", f"events[{index}] must be an object")
            continue
        if event.get("raw_body_stored") is not False:
            _record_failure(failures, "raw_body_stored", f"events[{index}] raw_body_stored must be false")
        event_type = str(event.get("event_type", "")).strip().lower()
        event_hash = str(event.get("event_hash", "")).strip()
        if event_type in SUPPRESSION_EVENT_TYPES:
            required_count += 1
            expected_scope, expected_reason = SUPPRESSION_EVENT_TYPES[event_type]
            suppression = suppression_by_hash.get(event_hash)
            if not suppression:
                _record_failure(failures, "suppression_missing", f"events[{index}] {event_type} has no suppression event")
                continue
            if suppression.get("contact_hash") != event.get("contact_hash"):
                _record_failure(failures, "suppression_contact", f"events[{index}] suppression contact_hash mismatch")
            if suppression.get("scope") != expected_scope:
                _record_failure(failures, "suppression_scope", f"events[{index}] expected scope {expected_scope}")
            if suppression.get("reason") != expected_reason:
                _record_failure(failures, "suppression_reason", f"events[{index}] expected reason {expected_reason}")

    if len(suppression_events) < required_count:
        _record_failure(failures, "suppression_missing", "not every suppression-required event has a suppression update")
    if len(suppression_events) > required_count:
        warnings.append("suppression_events includes extra review updates")

    return {
        "contract_name": SUPPRESSION_VALIDATION_CONTRACT_NAME,
        "status": "fail" if failures else "pass",
        "campaign_id": batch.get("campaign_id", ""),
        "event_batch_id": batch.get("event_batch_id", ""),
        "suppression_required_events": required_count,
        "suppression_updates": len(suppression_events),
        "failures": failures,
        "warnings": warnings,
        "generated_at_utc": now_iso(),
    }
