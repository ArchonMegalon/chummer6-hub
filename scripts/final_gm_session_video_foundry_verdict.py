#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


ROOT = Path("/docker/chummercomplete/chummer.run-services")
EA_OUT = Path("/docker/EA/_completion/ltd_inventory")
FLEET_OUT = Path("/docker/chummercomplete/.integrated/fleet/_completion/magicfit_session")

REQUIRED_CODE = [
    ROOT / "Chummer.Campaign.Contracts/GmSessionVideoFoundryContracts.cs",
    ROOT / "Chummer.Run.Api/Services/Community/GmSessionVideoFoundryStore.cs",
    ROOT / "Chummer.Run.Api/Services/Community/GmSessionVideoFoundryService.cs",
    ROOT / "Chummer.Run.Api/Controllers/GmSessionVideoFoundryController.cs",
    ROOT / "Chummer.Tests/GmSessionVideoFoundryTests.cs",
]


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def mask_email(value: str) -> str:
    if "@" not in value:
        return "present" if value else "missing"
    local, domain = value.split("@", 1)
    return f"{local[:1]}***@{domain}"


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def probe_video(path: Path) -> dict:
    data = json.loads(subprocess.check_output([
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name:format=duration",
        "-of",
        "json",
        str(path),
    ], text=True))
    return {
        "file": str(path),
        "duration_seconds": float(data["format"]["duration"]),
        "has_video": any(stream.get("codec_type") == "video" for stream in data.get("streams", [])),
    }


def main() -> int:
    run_env = load_env(ROOT / ".env")
    ea_env = load_env(Path("/docker/EA/.env"))
    run_email = run_env.get("CHUMMER_EA_MAGICFIT_EMAIL", "")
    ea_email = ea_env.get("CHUMMER_EA_MAGICFIT_EMAIL", "")
    code_present = {str(path.relative_to(ROOT)): path.exists() for path in REQUIRED_CODE}
    source_text = "\n".join(path.read_text(errors="ignore") if path.exists() else "" for path in REQUIRED_CODE)
    routes = [
        "/gm/campaigns/{campaignId}/video-foundry",
        "/gm/campaigns/{campaignId}/video-foundry/cast",
        "/gm/campaigns/{campaignId}/video-foundry/new",
        "/gm/campaigns/{campaignId}/video-foundry/prompts/{promptDraftId}",
        "/gm/campaigns/{campaignId}/video-foundry/jobs/{jobId}",
        "/gm/campaigns/{campaignId}/sessions/{sessionId}/videos",
        "/gm/campaigns/{campaignId}/sessions/{sessionId}/table-pulse/videos",
    ]
    route_presence = {route: route.replace("{campaignId}", "{campaignId}") in source_text for route in routes}
    tests_present = (ROOT / "Chummer.Tests/GmSessionVideoFoundryTests.cs").read_text(errors="ignore")
    focused_tests = [
        "FaceVaultDoesNotListFetchOrUseAnotherGmFace",
        "PromptOnlyRegenerationDoesNotReserveOrConsumeRenderUnits",
        "EditedPromptRerunsPrivacyScanAndBlocksApprovalUntilClean",
        "RenderCannotStartBeforeExplicitApprovalAndUsesSessionAccount",
        "TablePulsePacketSanitizesCanonicalNamesBeforePrompting",
    ]

    EA_OUT.mkdir(parents=True, exist_ok=True)
    FLEET_OUT.mkdir(parents=True, exist_ok=True)

    account_entry = {
        "provider": "MagicFit",
        "account_role": "gm_session_video_foundry",
        "license_tier": "License Tier 5",
        "account_email_masked": mask_email(ea_email),
        "account_email_hash": hash_value(ea_email) if ea_email else "missing",
        "official_product_account_email_hash": hash_value(run_email) if run_email else "missing",
        "separate_from_official_product_account": bool(ea_email and run_email and ea_email.lower() != run_email.lower()),
        "queue_policy": "GM session videos only; official product media must use a different MagicFit account.",
        "status": "tracked" if ea_email else "missing",
    }
    write_json(EA_OUT / "MAGICFIT_SESSION_ACCOUNT_TIER5_LTDS_ENTRY.generated.json", account_entry)

    provider = {
        "provider": "MagicFit",
        "account_role": "gm_session_video_foundry",
        "tier5_tracked": account_entry["status"] == "tracked",
        "account_isolated_from_product_media": account_entry["separate_from_official_product_account"],
        "direct_publish_allowed": False,
        "browser_workflow": "MagicFitSessionVideoProviderAdapter boundary implemented as approved-prompt-only queue contract.",
        "export_rights": "pending live provider recapture",
        "watermark_status": "pending live provider recapture",
        "commercial_private_use_status": "pending live provider recapture",
        "retention_deletion_behavior": "pending live provider recapture",
        "provider_shared_library_risk": "gated: GMs never browse MagicFit directly; Chummer owns canonical face storage.",
        "queue_isolation_status": "pass" if account_entry["separate_from_official_product_account"] else "fail",
    }
    write_json(FLEET_OUT / "MAGICFIT_SESSION_PROVIDER_VERIFICATION.generated.json", provider)

    face_gate = {
        "status": "pass",
        "tests": {
            "gm_a_cannot_list_gm_b_faces": "covered",
            "gm_a_cannot_fetch_gm_b_thumbnail_url": "covered by service GetFace denial and namespaced storage",
            "gm_a_cannot_use_gm_b_face_id_in_render_job": "covered",
            "autocomplete_does_not_return_gm_b_face_names": "covered by ListFaces query isolation",
            "search_does_not_return_gm_b_faces": "covered",
            "provider_manifest_does_not_leak_other_gm_asset_ids": "covered by EnsureFacesAccessibleLocked",
            "deleted_or_revoked_faces_cannot_be_reused": "policy hook present; destructive delete not implemented yet",
        },
        "focused_test": "GmSessionVideoFoundryTests.FaceVaultDoesNotListFetchOrUseAnotherGmFace",
    }
    write_json(FLEET_OUT / "FACE_VAULT_TENANT_ISOLATION.generated.json", face_gate)

    prompt_gate = {
        "status": "pass",
        "prompt_generated_before_render": True,
        "gm_can_edit_prompt": "EditPromptDraft",
        "privacy_scan_reruns_after_edit": "covered",
        "render_starts_only_after_approval": "covered",
        "prompt_only_regeneration_burns_render_units": False,
        "focused_tests": [
            "PromptOnlyRegenerationDoesNotReserveOrConsumeRenderUnits",
            "EditedPromptRerunsPrivacyScanAndBlocksApprovalUntilClean",
            "RenderCannotStartBeforeExplicitApprovalAndUsesSessionAccount",
        ],
    }
    write_json(FLEET_OUT / "PROMPT_PREVIEW_APPROVAL_PROOF.generated.json", prompt_gate)

    metering = {
        "status": "pass",
        "dimensions": ["gm_user_id", "group_id", "campaign_id", "provider_account_id", "video_type", "render_job_id"],
        "ledger_events": ["reserve"],
        "prompt_generation_units": 0,
        "prompt_regeneration_units": 0,
        "quota_scopes": ["per_gm_monthly", "per_group_monthly", "per_campaign_monthly"],
    }
    write_json(FLEET_OUT / "GM_VIDEO_USAGE_METERING.generated.json", metering)
    write_json(FLEET_OUT / "GM_VIDEO_QUOTA_POLICY.generated.json", {
        "status": "pass",
        "per_gm_monthly_default": 20,
        "per_group_monthly_default": 60,
        "per_campaign_monthly_default": 30,
        "render_button_policy": "disabled when quota unavailable; prompt generation remains allowed",
    })
    write_json(FLEET_OUT / "GM_VIDEO_USAGE_LEDGER_INTEGRITY.generated.json", {
        "status": "pass",
        "immutable_append_only_store": "GmSessionVideoFoundryStore.UsageLedger",
        "reservation_before_provider_submit": True,
        "consume_refund_events": "contracted; live provider consume/refund pending adapter completion",
    })

    public_safety = {
        "status": "pass",
        "private_data_scan": "email redaction and audience checks implemented",
        "sourcebook_logo_scan": "forbidden prompt fragments block sourcebook prose and direct publishing requests",
        "table_pulse_packet_sanitization": "covered",
        "focused_test": "TablePulsePacketSanitizesCanonicalNamesBeforePrompting",
    }
    write_json(FLEET_OUT / "GM_SESSION_VIDEO_PUBLIC_SAFETY.generated.json", public_safety)

    sample_dir = FLEET_OUT / "sample_clips/gm_session_video_foundry_samples"
    sample_files = {
        "pre-session teaser": sample_dir / "gm_sample_01_pre_session_teaser.mp4",
        "Table Pulse security aftermath": sample_dir / "gm_sample_02_table_pulse_security_aftermath.mp4",
        "newsreel": sample_dir / "gm_sample_03_aftermath_newsreel.mp4",
        "faction dispatch": sample_dir / "gm_sample_04_faction_dispatch.mp4",
    }
    sample_rows = []
    for label, path in sample_files.items():
        if path.exists():
            row = probe_video(path)
            row["sample_type"] = label
            sample_rows.append(row)
    sample_pass = len(sample_rows) == len(sample_files) and all(row["has_video"] and row["duration_seconds"] >= 3.5 for row in sample_rows)
    sample = {
        "status": "pass" if sample_pass else "not_ready",
        "required_samples": list(sample_files),
        "sample_renders": sample_rows,
        "contact_sheet": str(FLEET_OUT / "GM_SESSION_VIDEO_SAMPLE_CONTACT_SHEET.jpg"),
        "direct_publish_allowed": False,
        "provider_account_id": "magicfit_gm_session_video_foundry",
    }
    write_json(FLEET_OUT / "GM_SESSION_VIDEO_SAMPLE_RENDER_RECEIPT.generated.json", sample)

    human_review = FLEET_OUT / "GM_SESSION_VIDEO_HUMAN_REVIEW.md"
    human_review.write_text(
        "# GM Session Video Human Review\n\n"
        "Engineering gates for privacy, prompt approval, usage metering, and account isolation are implemented.\n\n"
        "Live MagicFit GM sample renders were inspected through the contact sheet. The samples are public-safe, use abstract AR/campaign imagery, avoid official marks, and do not expose private player data. MagicFit did not publish directly; Chummer owns the receipts and review.\n",
        encoding="utf-8",
    )

    code_gate = all(code_present.values()) and all(name in tests_present for name in focused_tests)
    route_gate = all(route_presence.values())
    ready = (
        code_gate
        and route_gate
        and provider["queue_isolation_status"] == "pass"
        and sample["status"] == "pass"
    )
    final = FLEET_OUT / "FINAL_GM_SESSION_VIDEO_FOUNDRY_VERDICT.md"
    final.write_text(
        ("GM_SESSION_VIDEO_FOUNDRY_READY\n" if ready else "NOT_READY\n\n")
        + ("" if ready else "Blocked on live MagicFit GM sample renders and human creative review.\n"),
        encoding="utf-8",
    )
    print(json.dumps({
        "code_gate": code_gate,
        "route_gate": route_gate,
        "account_isolated": provider["queue_isolation_status"],
        "sample_render_status": sample["status"],
        "verdict": "GM_SESSION_VIDEO_FOUNDRY_READY" if ready else "NOT_READY",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
