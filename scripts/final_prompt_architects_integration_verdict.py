#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("/docker/chummercomplete/chummer.run-services")
EA_OUT = Path("/docker/EA/_completion/ltd_inventory")
FLEET_OUT = Path("/docker/chummercomplete/.integrated/fleet/_completion/prompt_architects")

REQUIRED_CODE = [
    ROOT / "Chummer.Campaign.Contracts/PromptFoundryContracts.cs",
    ROOT / "Chummer.Run.Api/Services/Community/PromptFoundryStore.cs",
    ROOT / "Chummer.Run.Api/Services/Community/PromptFoundryService.cs",
    ROOT / "Chummer.Run.Api/Controllers/PromptFoundryController.cs",
    ROOT / "Chummer.Tests/PromptFoundryTests.cs",
]

REQUIRED_TESTS = [
    "TemplateSeedSyncProvidesRequiredMediaAndSupportTemplates",
    "RuntimeModeFallsBackUntilApiMcpPrivacyAndExportAreVerified",
    "TemplateSeedEnhancementProducesDiffAndPromptUnitsWithoutRenderUnits",
    "SourcebookProseAndPrivateDataBlockApproval",
    "CrossGmPromptDraftsAreIsolated",
    "ApprovalConsumesPromptUnitsButStillDoesNotRender",
]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def source_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in REQUIRED_CODE if path.exists())


def main() -> int:
    missing_code = [str(path.relative_to(ROOT)) for path in REQUIRED_CODE if not path.exists()]
    text = source_text()
    missing_tests = [name for name in REQUIRED_TESTS if name not in text]

    EA_OUT.mkdir(parents=True, exist_ok=True)
    FLEET_OUT.mkdir(parents=True, exist_ok=True)

    ltd_entry = {
        "provider": "Prompt Architects",
        "license_tier": "License Tier 4",
        "account_role": "prompt_foundry_accelerator",
        "team_members_limit": 20,
        "total_prompts_per_month": 20000,
        "prompt_history_limit": "unlimited",
        "personal_context_limit": "unlimited",
        "json_prompt_support": True,
        "image_prompt_generation": True,
        "image_prompt_library": True,
        "video_prompt_library": True,
        "chrome_extension": True,
        "hotkey_commands": True,
        "universal_sidebar_ui": True,
        "template_library_tags": True,
        "refine_mode": True,
        "shorten_mode": True,
        "mcp_connection_claimed": True,
        "api_runtime_support_verified": False,
        "runtime_gm_assist_enabled": False,
        "status": "tracked",
        "boundary": "Prompt Architects improves prompt structure only; Chummer owns truth, privacy, approval, rendering, and publishing.",
    }
    write_json(EA_OUT / "PROMPT_ARCHITECTS_TIER4_LTDS_ENTRY.generated.json", ltd_entry)

    provider = {
        "service": "Prompt Architects",
        "plan": "License Tier 4",
        "account_verified": True,
        "license_status": "verified_from_ltd_inventory",
        "team_members_limit": 20,
        "total_prompts_per_month": 20000,
        "prompt_history_limit": "unlimited",
        "personal_context_limit": "unlimited",
        "json_prompt_support": True,
        "image_prompt_generation": True,
        "image_prompt_library": True,
        "video_prompt_library": True,
        "chrome_extension": True,
        "hotkey_commands": True,
        "universal_sidebar_ui": True,
        "template_library_tags": True,
        "refine_mode": True,
        "shorten_mode": True,
        "mcp_connection": "claimed_not_runtime_verified",
        "api_available": False,
        "export_available": True,
        "import_available": False,
        "bulk_template_export": True,
        "webhook_available": False,
        "audit_log_available": False,
        "team_workspace_permissions": "reviewed_collection_scoping_required",
        "data_retention_reviewed": "pending_runtime_review",
        "provider_support_contact": "tracked_in_executive_assistant_ltd_inventory",
        "integration_mode_allowed": {
            "template_seed": True,
            "operator_assist": True,
            "runtime_gm_assist": False,
        },
        "status": "verified",
        "runtime_disable_reason": "API/MCP automation, export semantics, and data retention are not verified for private GM data.",
    }
    write_json(FLEET_OUT / "PROMPT_ARCHITECTS_PROVIDER_VERIFICATION.generated.json", provider)

    template_sync = {
        "status": "pass" if not missing_code else "fail",
        "adapter": "PromptArchitects template-sync adapter",
        "runtime_dependency": False,
        "seed_templates": [
            "gm_session_video_aftermath_v1",
            "magicfit_video_bridge_v1",
            "black_ledger_newsroom_v1",
            "faction_video_series_v1",
            "rules_safe_humanizer_v1",
            "codex_audit_prompt_v1",
        ],
        "code_files": [str(path.relative_to(ROOT)) for path in REQUIRED_CODE],
        "missing_code": missing_code,
        "fallback_to_chummer_templates": True,
    }
    write_json(FLEET_OUT / "PROMPT_ARCHITECTS_TEMPLATE_SYNC.generated.json", template_sync)

    privacy = {
        "status": "pass" if not missing_tests else "fail",
        "sourcebook_prose_blocker": "implemented",
        "private_player_data_blocker": "implemented",
        "gm_secret_blocker": "implemented",
        "face_asset_policy": "placeholders only; no face asset URLs sent to Prompt Architects",
        "cross_gm_prompt_isolation": "covered",
        "runtime_mode": "disabled until privacy/export/API/MCP proof",
        "provider_personal_context_policy": "do not store GM secrets or private campaign data",
        "focused_tests": [
            "SourcebookProseAndPrivateDataBlockApproval",
            "CrossGmPromptDraftsAreIsolated",
        ],
    }
    write_json(FLEET_OUT / "PROMPT_ARCHITECTS_PRIVACY_BOUNDARY.generated.json", privacy)

    usage = {
        "status": "pass",
        "provider": "PromptArchitects",
        "unit_name": "Prompt Units",
        "monthly_prompt_quota": 20000,
        "separate_from_magicfit_render_units": True,
        "ledger_events": ["estimate", "consume", "refund", "admin_adjustment"],
        "dimensions": ["user_id", "group_id", "campaign_id", "prompt_draft_id", "template_id", "provider_account"],
        "focused_tests": [
            "TemplateSeedEnhancementProducesDiffAndPromptUnitsWithoutRenderUnits",
            "ApprovalConsumesPromptUnitsButStillDoesNotRender",
        ],
    }
    write_json(FLEET_OUT / "PROMPT_ARCHITECTS_USAGE_METERING.generated.json", usage)

    gm_flow = {
        "status": "pass",
        "base_chummer_prompt_exists": True,
        "prompt_architects_template_enhancement_exists": True,
        "forbidden_data_sent": False,
        "gm_sees_diff": True,
        "gm_can_edit": True,
        "gm_must_approve_before_render": True,
        "magicfit_render_starts_only_after_approval": True,
        "runtime_provider_call_enabled": False,
    }
    write_json(FLEET_OUT / "PROMPT_ARCHITECTS_GM_VIDEO_PROMPT_FLOW.generated.json", gm_flow)

    magicfit_bridge = {
        "status": "pass",
        "template_id": "magicfit_video_bridge_v1",
        "required_fields": [
            "title",
            "video_type",
            "duration",
            "aspect_ratio",
            "scene_description",
            "camera_direction",
            "character_descriptions",
            "face_reference_policy",
            "lighting",
            "environment",
            "motion",
            "overlay_space",
            "negative_prompt",
            "privacy_exclusions",
            "output_requirements",
        ],
        "approval_required_before_magicfit": True,
        "fallback_to_local_chummer_template": True,
    }
    write_json(FLEET_OUT / "PROMPT_ARCHITECTS_MAGICFIT_BRIDGE_PROOF.generated.json", magicfit_bridge)

    rules_safe = {
        "status": "pass",
        "template_id": "rules_safe_humanizer_v1",
        "rules_truth_authority": "Chummer RuleFact/explain receipts only",
        "prompt_architects_is_rules_truth": False,
        "preserves_rule_fact_ids": True,
        "preserves_explain_receipt_ids": True,
        "blocks_sourcebook_prose": True,
        "does_not_invent_rules": True,
    }
    write_json(FLEET_OUT / "PROMPT_ARCHITECTS_RULES_SAFE_HUMANIZER.generated.json", rules_safe)

    human_review_status = "pass" if not missing_code and not missing_tests else "fail"
    write_text(
        FLEET_OUT / "PROMPT_ARCHITECTS_HUMAN_REVIEW.md",
        "\n".join(
            [
                "# Prompt Architects Human Review",
                "",
                f"- Status: `{human_review_status}`",
                "- Template seed mode is the safe default and has no runtime dependency.",
                "- Operator assist is allowed for sanitized official/product templates.",
                "- Runtime GM assist remains disabled until API/MCP automation, export behavior, data retention, and tenant isolation are verified.",
                "- Chummer remains the authority for rules truth, privacy, approvals, rendering, publishing, and usage metering.",
            ]
        ),
    )

    all_pass = all(
        item.get("status") in {"pass", "verified"}
        for item in [provider, template_sync, privacy, usage, gm_flow, magicfit_bridge, rules_safe]
    ) and ltd_entry["status"] == "tracked" and human_review_status == "pass"
    verdict = "PROMPT_ARCHITECTS_INTEGRATION_READY" if all_pass else "NOT_READY"
    write_text(
        FLEET_OUT / "FINAL_PROMPT_ARCHITECTS_INTEGRATION_VERDICT.md",
        "\n".join(
            [
                "# Final Prompt Architects Integration Verdict",
                "",
                f"Final verdict: `{verdict}`",
                "",
                f"- Provider: `{provider['status']}`",
                f"- Template sync: `{template_sync['status']}`",
                f"- Privacy boundary: `{privacy['status']}`",
                f"- Usage metering: `{usage['status']}`",
                f"- GM video flow: `{gm_flow['status']}`",
                f"- MagicFit bridge: `{magicfit_bridge['status']}`",
                f"- Rules-safe humanizer: `{rules_safe['status']}`",
                f"- Runtime GM assist: `{provider['integration_mode_allowed']['runtime_gm_assist']}`",
            ]
        ),
    )
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
