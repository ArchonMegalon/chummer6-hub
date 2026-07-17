#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from magicai_pool_registry import env_assignments as shared_env_assignments
from magicai_pool_registry import magicai_platform_audit as shared_magicai_platform_audit
from magicai_pool_registry import magicai_pool_counts as shared_magicai_pool_counts

PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
DEFAULT_OUTPUT = PUBLISHED_ROOT / "TEABLE_IMPORTANT_WORK.generated.json"
DEFAULT_CSV_OUTPUT = PUBLISHED_ROOT / "TEABLE_IMPORTANT_WORK.csv"
DEFAULT_MAGICAI_PLATFORM_AUDIT = PUBLISHED_ROOT / "MAGICAI_PLATFORM_ACCESS.generated.json"
DEFAULT_ORIGIN_GOLD_PROOF_CHAIN = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold/ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json")
DEFAULT_TEABLE_ORIGIN = "https://app.teable.ai"
DEFAULT_API_BASE_URL = "https://app.teable.ai/api"
DEFAULT_HUB_BASE_URL = "https://chummer.run"
DEFAULT_TABLE_NAME = "Chummer Important Work"
DEFAULT_DB_TABLE_NAME = "chummer_important_work"
DEFAULT_HTTP_TIMEOUT_SECONDS = 15.0
DEFAULT_SYNC_DEADLINE_SECONDS = 180.0
DEFAULT_BATCH_SIZE = 10
DEFAULT_TRANSIENT_RETRY_LIMIT = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.5
WINDOWS_VISUAL_AUDIT_RECEIPT = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"


@dataclass(frozen=True)
class ImportantWorkItem:
    item_id: str
    title: str
    area: str
    priority: str
    status: str
    cadence: str
    source: str
    why_it_matters: str
    next_action: str
    acceptance_gate: str


REQUIRED_FIELDS: tuple[dict[str, Any], ...] = (
    {"name": "Item Id", "type": "singleLineText", "unique": True, "notNull": True, "description": "Stable workstream key."},
    {"name": "Title", "type": "singleLineText", "notNull": True, "description": "Human-readable workstream title."},
    {"name": "Area", "type": "singleLineText", "description": "Product area."},
    {"name": "Priority", "type": "singleLineText", "description": "Current priority."},
    {"name": "Status", "type": "singleLineText", "description": "Current state."},
    {"name": "Cadence", "type": "singleLineText", "description": "How often this needs attention."},
    {"name": "Source", "type": "singleLineText", "description": "Where the item came from."},
    {"name": "Why It Matters", "type": "longText", "description": "Short business or user reason."},
    {"name": "Next Action", "type": "longText", "description": "Next concrete step."},
    {"name": "Acceptance Gate", "type": "longText", "description": "Observable completion condition."},
    {"name": "Last Synced At UTC", "type": "singleLineText", "description": "Most recent projection timestamp."},
)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def env_assignments(path: Path) -> dict[str, str]:
    return shared_env_assignments(path)


@lru_cache(maxsize=1)
def local_env_assignments() -> dict[str, str]:
    return env_assignments(RUN_SERVICES_ROOT / ".env")


def configured_value(*keys: str) -> str | None:
    for key in keys:
        value = normalize(os.environ.get(key))
        if value is not None:
            return value
    assignments = local_env_assignments()
    for key in keys:
        value = normalize(assignments.get(key))
        if value is not None:
            return value
    return None


def read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def file_contains(path: Path, needles: tuple[str, ...]) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return all(needle in text for needle in needles)


def count_phrase(count: int, singular: str, plural: str | None = None) -> str:
    label = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {label}"


def magicai_pool_readiness(repo_root: Path = RUN_SERVICES_ROOT) -> dict[str, int]:
    return shared_magicai_pool_counts(env_assignments(repo_root / ".env"))


def magicai_platform_audit(repo_root: Path = RUN_SERVICES_ROOT) -> dict[str, Any]:
    return shared_magicai_platform_audit(repo_root)


def render_lane_readiness(repo_root: Path = RUN_SERVICES_ROOT) -> dict[str, bool]:
    return {
        "governed_render_contract": file_contains(
            repo_root / "Chummer.Run.Api/Services/Community/HorizonGovernedRenderRequestComposerService.cs",
            (
                'public const string OrchestrationLane = "ea_governed_render";',
                'public const string ContractName = "chummer6-hub.horizon_governed_render_request.v1";',
            ),
        ),
        "runsite_bridge": file_contains(
            repo_root / "Chummer.Run.Api/Services/RunsiteOrientationArtifactRequestBridgeService.cs",
            (
                'private const string DefaultPreferredProvider = "magicai";',
                'ArtifactKindOrCapabilityId: "runsite-scene-render"',
                "GovernedRenderRequest: new HorizonGovernedRenderRequestCreateRequest(",
            ),
        ),
        "propertyquarry_bridge": file_contains(
            repo_root / "Chummer.Run.Api/Services/PropertyquarryApartmentVideoArtifactRequestBridgeService.cs",
            (
                'private const string DefaultPreferredProvider = "magicai";',
                'ArtifactKindOrCapabilityId: "propertyquarry-apartment-video"',
                "GovernedRenderRequest: new HorizonGovernedRenderRequestCreateRequest(",
                "propertyquarry:property-packet",
                "propertyquarry:property-continuity",
            ),
        ),
        "propertyquarry_internal_controller": file_contains(
            repo_root / "Chummer.Run.Api/Controllers/InternalPropertyquarryApartmentVideoController.cs",
            (
                '[HttpPost("/api/internal/propertyquarry/apartment-videos/requests")]',
                '[HttpPost("/api/internal/propertyquarry/apartment-videos/artifact-requests")]',
                "PropertyquarryApartmentVideoArtifactRequestBridgeResult",
            ),
        ),
        "propertyquarry_signed_in_route": file_contains(
            repo_root / "Chummer.Run.Api/Controllers/CampaignSpineController.cs",
            (
                '[HttpPost("me/property-workspaces/{propertyId}/apartment-video")]',
                "PropertyquarryApartmentVideoRequest",
                "BuildPropertyquarryApartmentVideoLane(property)",
                "apartmentVideoRequestApiHrefTemplate",
            ),
        ),
    }


def origin_gold_proof_status(repo_root: Path = RUN_SERVICES_ROOT) -> dict[str, Any]:
    local_path = repo_root / ".tmp/origin-dossier-fresh-gold/ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json"
    payload = read_json_object(local_path)
    if payload is None and repo_root.resolve() == RUN_SERVICES_ROOT.resolve():
        payload = read_json_object(DEFAULT_ORIGIN_GOLD_PROOF_CHAIN)
    payload = payload or {}
    ready = (
        payload.get("status") == "pass"
        and payload.get("finalVerdict") == "ORIGIN_EDITION_GOLD_READY"
        and payload.get("goalCompletionClaimAllowed") is True
    )
    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    return {
        "ready": ready,
        "status": str(payload.get("status") or "").strip(),
        "finalVerdict": str(payload.get("finalVerdict") or "").strip(),
        "passedStages": progress.get("passedStages"),
        "totalStages": progress.get("totalStages"),
    }


def origin_visuals_magicai_runtime(repo_root: Path = RUN_SERVICES_ROOT) -> dict[str, str]:
    pool = magicai_pool_readiness(repo_root)
    audit = magicai_platform_audit(repo_root)
    lane = render_lane_readiness(repo_root)
    gold = origin_gold_proof_status(repo_root)
    render_lane_ready = all(lane.values())
    pending = pool["pending_api_key_count"]
    api_ready = pool["api_key_ready_count"]
    declared = pool["declared_count"]
    login_ready = pool["login_ready_count"]
    pending_blocker_count = (
        audit["pending_blocked_count"]
        + audit["pending_login_failed_count"]
        + audit["pending_unverified_count"]
    )

    if render_lane_ready and audit["attempted"] and audit["pending_mintable_count"] > 0:
        status = "live-gold-pass-api-keys-pending"
    elif render_lane_ready and audit["attempted"] and pending > 0 and pending_blocker_count > 0:
        status = "live-gold-pass-api-key-path-blocked"
    elif render_lane_ready and pending > 0:
        status = "live-gold-pass-api-keys-pending"
    elif render_lane_ready and api_ready > 0:
        status = "live-gold-pass-render-lane-ready"
    elif render_lane_ready and declared > 0:
        status = "live-gold-pass-pool-declared"
    elif render_lane_ready:
        status = "live-gold-pass-pool-missing"
    else:
        status = "live-gold-pass-render-lane-pending"
    if gold["ready"]:
        if status == "live-gold-pass-api-key-path-blocked":
            status = "origin-gold-ready-api-key-path-blocked"
        elif status == "live-gold-pass-api-keys-pending":
            status = "origin-gold-ready-api-keys-pending"
        else:
            status = "origin-gold-ready"

    if audit["attempted"]:
        constraints: list[str] = []
        if audit["pending_blocked_count"]:
            constraints.append(f"{count_phrase(audit['pending_blocked_count'], 'slot')} {'is' if audit['pending_blocked_count'] == 1 else 'are'} currently API-forbidden")
        if audit["pending_login_failed_count"]:
            constraints.append(f"{count_phrase(audit['pending_login_failed_count'], 'slot')} currently {'fails' if audit['pending_login_failed_count'] == 1 else 'fail'} platform login")
        if audit["pending_unverified_count"]:
            constraints.append(f"{count_phrase(audit['pending_unverified_count'], 'slot')} still {'needs' if audit['pending_unverified_count'] == 1 else 'need'} a fresh live probe")
        if audit["pending_mintable_count"] > 0:
            action_bits = [f"mint the remaining MagicAI/omagic API keys for {count_phrase(audit['pending_mintable_count'], 'mintable slot')}"]
        elif constraints:
            action_bits = ["clear the remaining MagicAI/omagic API key path blockers"]
        else:
            action_bits = ["keep the MagicAI/omagic API key pool verified"]
        if constraints:
            action_bits.append(", ".join(constraints))
        action_fragment = "; ".join(action_bits)
    else:
        action_fragment = f"mint the remaining MagicAI/omagic API keys for {pending} of {login_ready or declared} declared login-ready pool slots"

    proof_stage_fragment = ""
    if gold["passedStages"] is not None and gold["totalStages"] is not None:
        proof_stage_fragment = f" ({gold['passedStages']}/{gold['totalStages']} proof stages)"
    next_action = (
        f"Origin Dossier Gold is {'ready' if gold['ready'] else 'not yet fully proven'}"
        f"{proof_stage_fragment}; "
        f"keep the deployed owner proof green on chummer.run, keep Magicfit as the preferred visual lane, "
        f"and {action_fragment}; the shared EA render lane is {'ready' if render_lane_ready else 'still being wired'} for Runsite and Propertyquarry via internal EA skills."
    )

    return {
        "status": status,
        "next_action": next_action,
    }


def windows_installer_visual_audit_runtime(repo_root: Path = RUN_SERVICES_ROOT) -> dict[str, str]:
    published_root = repo_root / ".codex-studio" / "published"
    payload = read_json_object(published_root / WINDOWS_VISUAL_AUDIT_RECEIPT.name)
    if payload is None and repo_root.resolve() == RUN_SERVICES_ROOT.resolve():
        payload = read_json_object(WINDOWS_VISUAL_AUDIT_RECEIPT)
    payload = payload or {}

    artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
    startup = payload.get("startupReceipt") if isinstance(payload.get("startupReceipt"), dict) else {}
    visual = payload.get("visualAuditSource") if isinstance(payload.get("visualAuditSource"), dict) else {}
    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    failed_gates = payload.get("failed_gates") if isinstance(payload.get("failed_gates"), list) else []
    raw_status = str(payload.get("status") or "").strip().lower()
    promoted_sha = str(artifact.get("actualSha256") or artifact.get("sha256") or "").strip()
    startup_matches_promoted = startup.get("artifactDigestMatchesPromoted")
    visual_sha = str(visual.get("artifactSha256") or "").strip()
    visual_matches_promoted = visual.get("artifactDigestMatchesPromoted")
    status_is_effective_pass = (
        raw_status in {"pass", "passed", "ready"}
        and not failures
        and not failed_gates
        and payload.get("pass") is not False
        and payload.get("source_digest_matches_promoted") is not False
        and (
            not startup
            or (
                str(startup.get("status") or "").strip().lower() in {"pass", "passed", "ready"}
                and startup_matches_promoted is not False
            )
        )
        and (
            not visual
            or (
                str(visual.get("status") or "").strip().lower() in {"pass", "passed", "ready"}
                and visual_matches_promoted is not False
            )
        )
    )

    if status_is_effective_pass:
        return {
            "status": "current-shelf-visual-proof-pass",
            "cadence": "each promoted Windows artifact",
            "source": "Windows installer visual audit receipt",
            "why_it_matters": "The Windows installer is a launch-critical desktop first impression and its native screenshots now match the promoted shelf artifact.",
            "next_action": "Keep the native Windows visual audit refreshed for every promoted Windows installer digest before release-ready and final-gold claims.",
            "acceptance_gate": "Windows installer visual audit stays pass, the native screenshot source digest matches the promoted installer SHA, and final-gold no longer fails on this lane.",
        }

    if (
        payload.get("source_digest_matches_promoted") is False
        or visual_matches_promoted is False
        or (promoted_sha and visual_sha and promoted_sha != visual_sha)
    ):
        return {
            "status": "native-visual-recapture-needed",
            "cadence": "now; before release-ready",
            "source": "Operator dashboard and Windows installer visual audit receipt",
            "why_it_matters": "The promoted Windows installer is live, but the native visual audit source still belongs to a different installer digest.",
            "next_action": (
                "Run the native Windows visual recapture for promoted installer digest "
                f"{promoted_sha}, import the proof bundle with "
                "scripts/import_windows_installer_gold_proof_artifact.py --intake-request "
                ".codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --verify, "
                "let that --verify import rerun the full post-import gate chain, "
                "then rerun release-ready, the operator dashboard, and final-gold."
            ),
            "acceptance_gate": (
                "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json records artifactSha256 "
                f"{promoted_sha}, required install-progress and completion screenshots pass at default and scaled DPI, "
                "verify_windows_installer_visual_audit.py passes, and final-gold no longer fails on Windows installer visual audit."
            ),
        }

    reason = "; ".join(str(item) for item in failures if str(item).strip()) or "Windows installer visual audit receipt is missing or failing."
    return {
        "status": "visual-proof-blocked",
        "cadence": "now; before release-ready",
        "source": "Operator dashboard and Windows installer visual audit receipt",
        "why_it_matters": "The Windows installer is a launch-critical desktop first impression and must have native visual proof before any flagship claim.",
        "next_action": f"Resolve the Windows installer visual audit blocker: {reason}",
        "acceptance_gate": "verify_windows_installer_visual_audit.py passes for the promoted Windows installer and final-gold no longer fails on this lane.",
    }


def important_work_items(repo_root: Path = RUN_SERVICES_ROOT) -> list[ImportantWorkItem]:
    origin_visuals_runtime = origin_visuals_magicai_runtime(repo_root)
    windows_visual_runtime = windows_installer_visual_audit_runtime(repo_root)
    return [
        ImportantWorkItem(
            item_id="desktop-premium-ui-polish",
            title="Desktop premium UI polish",
            area="Desktop client",
            priority="P0",
            status="active",
            cadence="daily until stable",
            source="Human tester feedback",
            why_it_matters="Unreadable dark-mode controls, clipped text, and awkward dialogs make the app feel unfinished.",
            next_action="Finish the all-surface color, spacing, labels, close-action, and no-scroll-trap pass across Avalonia.",
            acceptance_gate="Every ComboBox, TextBox, NumericUpDown, menu, overlay, dialog, and tab is readable in light and dark mode without hover.",
        ),
        ImportantWorkItem(
            item_id="linux-dark-mode-cachyos",
            title="Linux KDE dark-mode compatibility",
            area="Desktop client",
            priority="P0",
            status="active",
            cadence="daily until fixed",
            source="CachyOS tester feedback",
            why_it_matters="Arch/KDE users saw white-on-white and black-on-black text in basic workflows.",
            next_action="Audit every themed control under KDE dark mode and lock Chummer-owned surfaces to coherent brushes.",
            acceptance_gate="CachyOS/KDE screenshots show readable text and backgrounds across launch, account, builder, help, and report issue windows.",
        ),
        ImportantWorkItem(
            item_id="character-builder-core-usability",
            title="Character builder core usability",
            area="Character creation",
            priority="P0",
            status="active",
            cadence="daily until usable",
            source="Human tester feedback",
            why_it_matters="New users cannot trust the builder if attributes, karma, build method, metatype, and defaults are unclear.",
            next_action="Specialize SR4/SR5/SR6 builder labels, remove duplicate attribute steppers, show remaining budget, and fix Modify/Add overlays.",
            acceptance_gate="Mouse-only SR4 BP troll decker and SR5 karma workflows can be completed without unclear labels or disappearing popups.",
        ),
        ImportantWorkItem(
            item_id="add-workflows-parity",
            title="All Add workflows behave like Chummer5A",
            area="Desktop client",
            priority="P0",
            status="active",
            cadence="daily until covered",
            source="Regression reports",
            why_it_matters="Add Quality already slipped; every Add surface needs the same standard.",
            next_action="Audit Add Quality, Skill, Gear, Ware, Weapon, Armor, Contact, Spell, Critter, and companion workflows with screenshots.",
            acceptance_gate="Every Add dialog has readable colors, interactive navigation, search/filter, commit/cancel, and Chummer5A parity screenshots.",
        ),
        ImportantWorkItem(
            item_id="origin-dossier-first-story",
            title="Origin Dossier starts with the story",
            area="Origin Dossier",
            priority="P0",
            status="book-first-ui-pushed",
            cadence="daily until released",
            source="Product direction",
            why_it_matters="The feature should feel like creating a book, not filling an internal options form.",
            next_action="Verify the next installed desktop build starts from race/metatype and archetype, hands over a real full story ebook with fitting cover art first, then exactly three story-fit portraits, then voice-choice audiobook request, then chapter-scene summaries for one chosen character-visible cinematic render, while preserving authenticated read/listen/watch/canon-audit owner routes.",
            acceptance_gate="A user can start a dossier, receive the real full story ebook with fitting cover art first, choose one of three story-fit portraits, request a voice-choice audiobook, choose one scene from the chapter shortlist for a character-visible render, and access private read/listen/watch/canon-audit routes only as the signed-in owner.",
        ),
        ImportantWorkItem(
            item_id="origin-dossier-alice-seed",
            title="Alice uses Origin Dossier story as build seed",
            area="Alice",
            priority="P0",
            status="active",
            cadence="daily until covered",
            source="Product direction",
            why_it_matters="Alice should reason from the character's story instead of raw combo boxes.",
            next_action="Feed the approved story into Alice suggestions for new builds and support read-only dossier generation for finished characters.",
            acceptance_gate="Origin Dossier E2E proves story generation, Alice follow-up, and established-character dossier creation.",
        ),
        ImportantWorkItem(
            item_id="origin-dossier-humanizer-loop",
            title="Origin Dossier humanizer loop",
            area="Origin Dossier",
            priority="P0",
            status="active",
            cadence="daily until covered",
            source="Product direction",
            why_it_matters="A dossier should read like a deliberate character book, not generated filler or a form summary.",
            next_action="Run the generated story through the Undetectable Humanizer LTD lane before FlipLink/book, audiobook, video, and Alice ingestion; keep advanced steering collapsed by default.",
            acceptance_gate="Origin Dossier E2E proves race/archetype first, story-first review, humanized prose, Subscribr-authored full story, fitting cover art, three story-fit portraits, voice choice, chapter-scene shortlist, one chosen character-visible render, and Alice using the final story.",
        ),
        ImportantWorkItem(
            item_id="alice-build-from-scratch",
            title="Alice can build from scratch",
            area="Alice",
            priority="P0",
            status="active",
            cadence="daily until covered",
            source="User workflow",
            why_it_matters="Opening Alice without a character should produce a complete build, not an error.",
            next_action="Add no-character mode, explicit build button, option explanations, and GM grant constraints.",
            acceptance_gate="Alice creates a complete character from settings and explains options such as legality, ware, qualities, and GM constraints.",
        ),
        ImportantWorkItem(
            item_id="ai-disable-global",
            title="Global AI-off mode hides AI features",
            area="Account and privacy",
            priority="P0",
            status="desktop-option-policy-pushed",
            cadence="daily until covered",
            source="User request",
            why_it_matters="Users who do not want AI should not see AI-labeled buttons, companions, critters, or behavior.",
            next_action="Verify the next installed desktop build with AI disabled hides Alice, Origin Dossier, explain companions, and AI/metasapient character options while keeping normal critter workflows available.",
            acceptance_gate="With AI disabled, public and desktop flows hide AI entry points and tests prove no AI-only choices are offered.",
        ),
        ImportantWorkItem(
            item_id="account-claim-copy-flow",
            title="Claim your copy account flow",
            area="Account linking",
            priority="P0",
            status="active",
            cadence="daily until stable",
            source="User preference",
            why_it_matters="Claim your copy is clearer than login via webpage and should not require manual activation.",
            next_action="Redesign the account linking dialog around claiming the installed copy, with automatic online claim when possible.",
            acceptance_gate="Installed app can claim the downloaded copy online, shows a premium handoff, and falls back cleanly if the browser step fails.",
        ),
        ImportantWorkItem(
            item_id="personalized-claim-copy-video",
            title="Personalized claim-copy uplink video",
            area="Account linking",
            priority="P1",
            status="design-ready",
            cadence="weekly until media lane exists",
            source="Product direction",
            why_it_matters="The login handoff should feel premium while using only consented user data.",
            next_action="Render a short decker host-entry scene that shows available profile data but only extracts the email for linking.",
            acceptance_gate="Help menu can replay the login video on demand and account linking can show the personalized email render safely.",
        ),
        ImportantWorkItem(
            item_id="joggai-consented-avatar-video-lane",
            title="JoggAI consented avatar video lane",
            area="Provider governance",
            priority="P1",
            status="tracked-not-runtime",
            cadence="after core Origin Dossier flow",
            source="Provider inventory and user prompt",
            why_it_matters="JoggAI may be useful for polished character or account-link videos, but only with explicit likeness and data boundaries.",
            next_action="Define JoggAI as an off-by-default candidate render lane for Origin Dossier portraits/scenes and claim-copy login clips; require consent, provider proof, and human review before any output ships.",
            acceptance_gate="JoggAI has a provider verification receipt, consent gate, sample candidate render, privacy review, and no path that can publish or alter character/rules/account truth.",
        ),
        ImportantWorkItem(
            item_id="desktop-updater-install-link",
            title="Updater and install-link reliability",
            area="Updater",
            priority="P0",
            status="active",
            cadence="daily until stable",
            source="Linux audit",
            why_it_matters="Users need visible, reliable updates without stalled gio handoffs or silent failures.",
            next_action="Replace Linux gio package handoff with explicit installer path, show update progress, persist structured failure reasons, and relaunch in place.",
            acceptance_gate="Windows and Linux older builds discover, download, apply, relaunch, and reconcile state without manual package install.",
        ),
        ImportantWorkItem(
            item_id="windows-installer-premium",
            title="Windows installer premium design",
            area="Installer",
            priority="P0",
            status=windows_visual_runtime["status"],
            cadence=windows_visual_runtime["cadence"],
            source=windows_visual_runtime["source"],
            why_it_matters=windows_visual_runtime["why_it_matters"],
            next_action=windows_visual_runtime["next_action"],
            acceptance_gate=windows_visual_runtime["acceptance_gate"],
        ),
        ImportantWorkItem(
            item_id="windows-installer-current-shelf-proof",
            title="Current Windows shelf installer proof",
            area="Release",
            priority="P0",
            status=windows_visual_runtime["status"],
            cadence=windows_visual_runtime["cadence"],
            source=windows_visual_runtime["source"],
            why_it_matters=windows_visual_runtime["why_it_matters"],
            next_action=windows_visual_runtime["next_action"],
            acceptance_gate=windows_visual_runtime["acceptance_gate"],
        ),
        ImportantWorkItem(
            item_id="aur-linux-package",
            title="AUR package for Arch-based Linux",
            area="Packaging",
            priority="P1",
            status="queued",
            cadence="next packaging pass",
            source="CachyOS tester feedback",
            why_it_matters="Arch users should not need to convert Debian packages.",
            next_action="Add PKGBUILD generation and publish-pipeline support for an AUR package lane.",
            acceptance_gate="Arch/CachyOS install path is documented and smoke-tested without converting the .deb manually.",
        ),
        ImportantWorkItem(
            item_id="release-policy-daily-08",
            title="Daily 08:00 release policy",
            area="Release",
            priority="P0",
            status="policy-active",
            cadence="daily",
            source="User policy",
            why_it_matters="Publishing too often burns credits and makes release truth noisy.",
            next_action="Enforce one morning publish per day unless a build is necessary for a focused test, and build only the needed platform.",
            acceptance_gate="Publish pipeline and operator notes default to one 08:00 Europe/Vienna release and per-platform builds only when needed.",
        ),
        ImportantWorkItem(
            item_id="downloads-latest-windows-linux",
            title="Downloads always show latest Windows and Linux",
            area="Website",
            priority="P0",
            status="active",
            cadence="each release",
            source="Release requirement",
            why_it_matters="The website is the user's source of truth for stable and nightly installers.",
            next_action="Keep stable/nightly buttons minimal and ensure each Windows/Linux build updates the download shelf automatically.",
            acceptance_gate="After a build, chummer.run/downloads exposes lane buttons only for promoted installer platforms with no account-first noise.",
        ),
        ImportantWorkItem(
            item_id="public-website-minimal-redesign",
            title="Minimal chummer.run redesign",
            area="Website",
            priority="P0",
            status="active",
            cadence="daily until first human pass",
            source="Human tester feedback",
            why_it_matters="The site must look human-designed, quiet, and respectful of attention.",
            next_action="Publish the pushed minimal-copy pass at the next 08:00 release window, rerun the live leak gate, then do a human visual pass.",
            acceptance_gate="A skeptical visitor can understand Chummer in five seconds and first-visit pages pass minimal copy, nav, attention-budget, and live leak-gate tests.",
        ),
        ImportantWorkItem(
            item_id="public-copy-humanizer",
            title="Humanize public and desktop copy",
            area="Copy",
            priority="P0",
            status="campaign-city-source-pass-pushed",
            cadence="continuous; live after scheduled publish",
            source="Human tester feedback",
            why_it_matters="Generated-sounding copy undermines trust even when the feature works.",
            next_action="Publish the campaign-city copy cleanup at the next 08:00 release window, rerun the live leak gate, then continue the same loop through installer, desktop dialogs, and Origin Dossier output.",
            acceptance_gate="Public and primary desktop surfaces avoid AI, provider, proof, audit, and internal workflow wording unless directly useful.",
        ),
        ImportantWorkItem(
            item_id="public-proof-language-removal",
            title="Remove proof/check wording from user surfaces",
            area="Copy",
            priority="P0",
            status="active",
            cadence="continuous until leak gate is boring",
            source="Human tester feedback",
            why_it_matters="Users need clear product state, not internal proof, checks, receipts, IDs, or validation language.",
            next_action="Continue scanning public views and desktop dialogs for proof, check, receipt, source, record, evidence, audit, validation, provider, and raw-id wording; replace it with user-facing state only when needed.",
            acceptance_gate="Public copy leak gates and source tests pass, and screenshots show no internal proof/check language in normal user journeys.",
        ),
        ImportantWorkItem(
            item_id="public-help-accessibility-polish",
            title="Public help readability and labels",
            area="Support",
            priority="P0",
            status="active",
            cadence="daily until readable",
            source="Human tester feedback",
            why_it_matters="Help is where confused users land; unreadable inputs or missing labels make the product feel careless.",
            next_action="Audit chummer.run help, support, report issue, account, and recovery surfaces for contrast, labels, button names, and minimal copy.",
            acceptance_gate="Help and support pages have readable light/dark contrast, visible labels for every field, clear primary actions, and no internal wording.",
        ),
        ImportantWorkItem(
            item_id="black-ledger-hide-and-polish",
            title="Black Ledger hidden until ready",
            area="Black Ledger",
            priority="P1",
            status="active",
            cadence="weekly until flagship",
            source="Human tester feedback",
            why_it_matters="An unfinished flagship feature should not dominate the public site.",
            next_action="Move Black Ledger behind a quieter route and finish globe, media, replay, faction, and newsroom E2E before promoting it again.",
            acceptance_gate="Black Ledger route has polished visuals, video fallback, route follow-through, screenshots, and is not noisy on the homepage.",
        ),
        ImportantWorkItem(
            item_id="gm-cockpit-design",
            title="GM cockpit redesign",
            area="Campaign tools",
            priority="P1",
            status="design-active",
            cadence="weekly until implemented",
            source="Product direction",
            why_it_matters="The GM surface should feel like a useful table cockpit, not an internal maintenance list.",
            next_action="Design graphics, table state, active scene, players, clocks, pressure, grants, and next actions around the GM's real workflow.",
            acceptance_gate="GM cockpit E2E shows session steering, grants, dossier influence, and table actions without maintenance-language rows.",
        ),
        ImportantWorkItem(
            item_id="desktop-chummer5a-parity",
            title="Hard Chummer5A parity exit gate",
            area="Desktop client",
            priority="P0",
            status="active",
            cadence="daily until covered",
            source="Gold gate",
            why_it_matters="The desktop client is not gold until it behaves like a serious Chummer successor.",
            next_action="Require screenshots for every client surface and side-by-side task parity for veteran workflows.",
            acceptance_gate="Gold gate fails if a primary surface lacks screenshot evidence, task E2E, or acceptable Chummer5A parity.",
        ),
        ImportantWorkItem(
            item_id="reproducible-gold-proof-chain",
            title="Reproducible gold proof chain",
            area="Gold readiness",
            priority="P0",
            status="active",
            cadence="daily until gold",
            source="Gold audit",
            why_it_matters="Gold cannot be claimed while the checked-in verifier, generated artifact, live recrawl, and release truth disagree.",
            next_action="Update the final janitor to the current proof root, regenerate fresh live evidence, and fail closed on stale or mismatched release data.",
            acceptance_gate="A clean checkout can run the checked-in gold verifier and produce a current non-stale verdict that matches the live site and repo docs.",
        ),
        ImportantWorkItem(
            item_id="rules-coverage-authority",
            title="Rules coverage authority",
            area="Rules engine",
            priority="P0",
            status="active",
            cadence="weekly until production depth",
            source="Gold audit",
            why_it_matters="Rules explanations and character legality need current, inspectable coverage.",
            next_action="Materialize current SR4, SR5, SR6 coverage with golden fixtures, explain receipts, and edition separation.",
            acceptance_gate="Rules readiness requires meaningful coverage for SR4/SR5/SR6 and blocks zero-fact or stale authority claims.",
        ),
        ImportantWorkItem(
            item_id="shadowrun-data-files-completeness",
            title="Shadowrun data file completeness",
            area="Rules data",
            priority="P0",
            status="active",
            cadence="weekly until useful",
            source="Human tester feedback",
            why_it_matters="Character creation cannot feel trustworthy when expected skills, qualities, gear, ware, weapons, contacts, and build options are missing or prefilled strangely.",
            next_action="Inventory SR4/SR5/SR6 data gaps, prioritize character creation essentials, and add fixtures that prove clean new characters start with intentional defaults only.",
            acceptance_gate="New SR4/SR5/SR6 characters expose expected core data, remaining budgets, and no surprising preselected skills, weapons, contacts, or qualities.",
        ),
        ImportantWorkItem(
            item_id="whole-product-e2e",
            title="Whole-product E2E coverage",
            area="Testing",
            priority="P0",
            status="active",
            cadence="daily until reliable",
            source="User directive",
            why_it_matters="Broad E2E prevents polish regressions such as unreadable dialogs and broken Add workflows.",
            next_action="Add and harden tests for Origin Dossier, Alice, every horizon/surface, installers, updater, downloads, help, and account linking.",
            acceptance_gate="Focused E2E suite catches UI readability, workflow, and release-truth regressions before a daily publish.",
        ),
        ImportantWorkItem(
            item_id="table-pulse-remote-loop",
            title="Table Pulse remote reaction loop",
            area="Table Pulse",
            priority="P1",
            status="active",
            cadence="weekly until proven",
            source="Gold audit",
            why_it_matters="Table Pulse needs to feel like a useful table tool, not an unproven notification demo.",
            next_action="Build and verify the GM session, opt-in, remote notification, player reaction, adjudication, state update, and receipt loop.",
            acceptance_gate="E2E proof shows the complete GM-to-player-to-GM loop with opt-out, useful copy, state changes, and no notification noise.",
        ),
        ImportantWorkItem(
            item_id="instant-help-vidboard",
            title="Chummer Instant Help with video library",
            area="Support",
            priority="P1",
            status="design-ready",
            cadence="weekly until provider verified",
            source="Support design",
            why_it_matters="Users need instant guidance, optional video, and repair actions instead of booking calls.",
            next_action="Implement intent routing, text answers, pre-rendered VidBoard catalog, diagnostics, escalation, and freshness gates.",
            acceptance_gate="Help flow answers, shows a relevant approved video, runs a repair/check, and escalates with diagnostics if unresolved.",
        ),
        ImportantWorkItem(
            item_id="minimal-seo-optimization",
            title="Minimal SEO optimization",
            area="Website",
            priority="P1",
            status="queued",
            cadence="after minimal redesign",
            source="NeuronWriter and ClickRank direction",
            why_it_matters="Search optimization should improve discoverability without making the site feel generated, keyword-stuffed, or noisy.",
            next_action="Run NeuronWriter and ClickRank only after the minimal human copy is accepted, then keep or reject suggestions by attention cost.",
            acceptance_gate="Optimized public pages remain minimal, human, and clear while search metadata and headings improve without adding visible clutter.",
        ),
        ImportantWorkItem(
            item_id="subscribr-video-script-lane",
            title="Subscribr Tier 7 script lane",
            area="Provider governance",
            priority="P2",
            status="queued",
            cadence="after core polish",
            source="Provider integration guide",
            why_it_matters="Video pre-production can scale tutorials and release explainers without giving providers product truth.",
            next_action="Add source packets, channel map, provider verification, script receipts, and human approval boundaries.",
            acceptance_gate="Subscribr can draft from approved sources only; publication remains disabled until separate human approval.",
        ),
        ImportantWorkItem(
            item_id="sendr-black-ledger-outreach-lane",
            title="Sendr Tier 4 Black Ledger outreach lane",
            area="Provider governance",
            priority="P1",
            status="draft-review-gated",
            cadence="weekly until pilot receipt",
            source="Sendr Tier 4 guide",
            why_it_matters="Black Ledger needs relationship-building distribution without giving Sendr rules, editorial, release, support, sponsor-contract, or private-data truth.",
            next_action="Use the Sendr provider-lane contract, campaign packet verifier, dry-run campaign receipt, reply/engagement batch receipt, and suppression-sync verifier before any sponsor, guest, creator, or launch outreach; keep WhatsApp, direct send, and auto-reply disabled.",
            acceptance_gate="A sponsor-pilot packet with provider-lane metadata, recipient-basis receipt, engagement batch receipt, suppression-sync pass, message-copy hash, platform-policy check, and human approval receipt exist before any limited Sendr send is claimed.",
        ),
        ImportantWorkItem(
            item_id="origin-visuals-magicfit-runsite-magicai",
            title="Magicfit origin visuals and MagicAI runsite pool",
            area="Provider governance",
            priority="P1",
            status=origin_visuals_runtime["status"],
            cadence="daily until stable",
            source="Provider account update",
            why_it_matters="Origin Dossier visual proofs should stay on the preferred Magicfit lane, book/PDF/ebook packaging should have its own governed provider account role, and Runsite scene renders plus Propertyquarry apartment videos should use the multi-account MagicAI/omagic pool through internal EA skills.",
            next_action=origin_visuals_runtime["next_action"],
            acceptance_gate="Deployed Origin Dossier owner proof stays pass on chummer.run, packaging and visual receipt policy remain truthful, no-credit-burn provider readiness audits and free/supporter credit gates stay enforced, Runsite and Propertyquarry share one internal render capability receipt contract, and Teable/env reflect provider account state without exposing raw credentials.",
        ),
        ImportantWorkItem(
            item_id="code-quality-specialization-pass",
            title="Code quality specialization pass",
            area="Engineering quality",
            priority="P1",
            status="active",
            cadence="weekly",
            source="User code-quality request",
            why_it_matters="Over-generic UI/data paths and hardcoded release or provider assumptions both create brittle product behavior.",
            next_action="Identify generic surfaces that should become domain-specific and hardcoded assumptions that should become configuration or registry-backed truth.",
            acceptance_gate="A code-quality pass removes at least one meaningful generic abstraction leak or hardcoded assumption and adds a regression test.",
        ),
        ImportantWorkItem(
            item_id="provider-ltd-inventory",
            title="Owned LTD inventory and proof paths",
            area="Provider governance",
            priority="P1",
            status="active",
            cadence="weekly",
            source="Gold audit",
            why_it_matters="Owned tools such as Dadan, Rybbit, NeuronWriter, Undetectable Humanizer LTD, VidBoard, and Subscribr need explicit bounded roles.",
            next_action="Keep LTDs.md and provider receipts current without surfacing provider names on user-facing pages.",
            acceptance_gate="Inventory lists every owned LTD with role, tier, status, boundaries, and proof path, while public pages stay quiet.",
        ),
        ImportantWorkItem(
            item_id="design-docs-current",
            title="Chummer6 design docs current",
            area="Documentation",
            priority="P0",
            status="active",
            cadence="before doc regeneration",
            source="User request",
            why_it_matters="Human-facing docs should regenerate from current product design, not stale concepts.",
            next_action="Update Chummer6 design with Origin Dossier bundle, GM cockpit, Instant Help, Alice behavior, release policy, and provider boundaries.",
            acceptance_gate="Design source reflects current product decisions before the human-facing docs regeneration runs.",
        ),
        ImportantWorkItem(
            item_id="teable-important-work-sync",
            title="Important work Teable sync",
            area="Operations",
            priority="P0",
            status="active",
            cadence="daily",
            source="User request",
            why_it_matters="The project needs a concise operating board for everything that actually matters.",
            next_action="Refresh this projection after material product-scope changes and keep stale or resolved rows honest.",
            acceptance_gate="Teable contains one current row per critical Chummer workstream and can be refreshed without duplicating records.",
        ),
        ImportantWorkItem(
            item_id="teable-maintenance-not-horizon",
            title="Teable remains maintenance, not a horizon",
            area="Operations",
            priority="P0",
            status="active",
            cadence="continuous",
            source="User correction",
            why_it_matters="Teable is an operator board; presenting it like a product horizon confuses users and adds noise.",
            next_action="Keep Teable integration in maintenance/admin flows and remove any public product framing that makes it look like a user-facing horizon.",
            acceptance_gate="Public navigation and horizon pages do not present Teable as a product feature, while the operator board still syncs important work.",
        ),
    ]


def teable_field_definition(field: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": field["name"],
        "type": field["type"],
        "description": field.get("description", ""),
    }


def teable_fields_for_row(item: ImportantWorkItem, synced_at: str) -> dict[str, str]:
    return {
        "Item Id": item.item_id,
        "Title": item.title,
        "Area": item.area,
        "Priority": item.priority,
        "Status": item.status,
        "Cadence": item.cadence,
        "Source": item.source,
        "Why It Matters": item.why_it_matters,
        "Next Action": item.next_action,
        "Acceptance Gate": item.acceptance_gate,
        "Last Synced At UTC": synced_at,
    }


def write_csv_projection(path: Path, generated_at_utc: str) -> None:
    fieldnames = [str(field["name"]) for field in REQUIRED_FIELDS]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for item in important_work_items():
            writer.writerow(teable_fields_for_row(item, generated_at_utc))


def build_projection() -> dict[str, Any]:
    generated_at = now_iso()
    rows = [asdict(item) for item in important_work_items()]
    priority_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    area_counts: dict[str, int] = {}
    for item in rows:
        priority_counts[item["priority"]] = priority_counts.get(item["priority"], 0) + 1
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
        area_counts[item["area"]] = area_counts.get(item["area"], 0) + 1
    return {
        "contract_name": "chummer.teable_important_work.v1",
        "generated_at_utc": generated_at,
        "status": "ready",
        "table_name": DEFAULT_TABLE_NAME,
        "row_count": len(rows),
        "summary": {
            "priority_counts": dict(sorted(priority_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "area_counts": dict(sorted(area_counts.items())),
        },
        "rows": rows,
        "sync": {
            "state": "not_requested",
            "attempted": False,
            "synced_count": 0,
            "failed_count": 0,
            "errors": [],
        },
    }


def normalize(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def resolve_duration_seconds(value: object, default: float) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return default
    return seconds if seconds > 0 else default


def resolve_http_timeout_seconds() -> float:
    return resolve_duration_seconds(
        configured_value("CHUMMER_TEABLE_HTTP_TIMEOUT_SECONDS"),
        DEFAULT_HTTP_TIMEOUT_SECONDS,
    )


def resolve_sync_deadline_seconds() -> float:
    return resolve_duration_seconds(
        configured_value("CHUMMER_TEABLE_IMPORTANT_WORK_SYNC_DEADLINE_SECONDS"),
        DEFAULT_SYNC_DEADLINE_SECONDS,
    )


def operation_deadline(start_monotonic: float, deadline_seconds: float | None) -> float | None:
    if deadline_seconds is None or deadline_seconds <= 0:
        return None
    return start_monotonic + deadline_seconds


def bounded_timeout_seconds(
    requested_timeout_seconds: float,
    *,
    deadline_monotonic: float | None,
    label: str,
) -> float:
    timeout_seconds = max(1.0, float(requested_timeout_seconds))
    if deadline_monotonic is None:
        return timeout_seconds
    remaining = deadline_monotonic - time.monotonic()
    if remaining <= 0:
        raise TimeoutError(f"{label}_deadline_exceeded")
    return max(1.0, min(timeout_seconds, remaining))


def chunked(items: list[Any], batch_size: int) -> list[list[Any]]:
    effective_batch_size = max(1, int(batch_size))
    return [items[index : index + effective_batch_size] for index in range(0, len(items), effective_batch_size)]


def is_transient_teable_error(error: BaseException) -> bool:
    text = str(error).strip().lower()
    if "deadline_exceeded" in text:
        return False
    return any(
        token in text
        for token in (
            "timed out",
            "timeout",
            "teable_transport_error:",
            "teable_http_408:",
            "teable_http_425:",
            "teable_http_429:",
            "teable_http_500:",
            "teable_http_502:",
            "teable_http_503:",
            "teable_http_504:",
            "teable_batch_update_count_mismatch:",
            "teable_batch_create_count_mismatch:",
            "teable_invalid_json_response",
        )
    )


def sleep_before_teable_retry(
    retry_number: int,
    *,
    retry_backoff_seconds: float,
    deadline_monotonic: float | None,
) -> None:
    delay_seconds = max(0.0, float(retry_backoff_seconds)) * (2 ** max(0, retry_number - 1))
    if delay_seconds <= 0:
        return
    if deadline_monotonic is not None:
        remaining = deadline_monotonic - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("teable_sync_deadline_exceeded")
        delay_seconds = min(delay_seconds, remaining)
    time.sleep(delay_seconds)


def send_json(
    method: str,
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    timeout: float | None = None,
    *,
    deadline_monotonic: float | None = None,
) -> Any:
    requested_timeout_seconds = resolve_http_timeout_seconds() if timeout is None else float(timeout)
    effective_timeout_seconds = bounded_timeout_seconds(
        requested_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
        label="teable_request",
    )
    data: bytes | None = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json, text/plain, */*",
        "Origin": DEFAULT_TEABLE_ORIGIN,
        "Referer": f"{DEFAULT_TEABLE_ORIGIN}/",
        "User-Agent": "Mozilla/5.0",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=effective_timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"teable_http_{exc.code}:{body[:240]}") from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason or "").strip()
        if "timed out" in reason.lower():
            raise RuntimeError(f"teable_timeout_after_{effective_timeout_seconds:g}s") from exc
        raise RuntimeError(f"teable_transport_error:{reason[:180]}") from exc
    except TimeoutError as exc:
        detail = str(exc) or f"teable_timeout_after_{effective_timeout_seconds:g}s"
        raise RuntimeError(detail[:180]) from exc
    if not body.strip():
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("teable_invalid_json_response") from exc


def discover_base_id(
    api_base_url: str,
    api_key: str,
    *,
    request_timeout_seconds: float,
    deadline_monotonic: float | None = None,
) -> str | None:
    response = send_json(
        "GET",
        f"{api_base_url}/base/access/all",
        api_key,
        timeout=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
    )
    if not isinstance(response, list):
        return None
    ids = [str(entry.get("id") or "").strip() for entry in response if isinstance(entry, dict) and str(entry.get("id") or "").strip()]
    return ids[0] if len(ids) == 1 else None


def matches_table(entry: dict[str, Any], table_name: str) -> bool:
    names = {
        str(entry.get("name") or "").strip().lower(),
        str(entry.get("dbTableName") or "").strip().lower(),
    }
    return table_name.strip().lower() in names or DEFAULT_DB_TABLE_NAME.lower() in names


def resolve_or_create_table(
    api_base_url: str,
    api_key: str,
    base_id: str,
    table_name: str,
    *,
    request_timeout_seconds: float,
    deadline_monotonic: float | None = None,
) -> str:
    tables = send_json(
        "GET",
        f"{api_base_url}/base/{urllib.parse.quote(base_id)}/table",
        api_key,
        timeout=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
    )
    if isinstance(tables, list):
        for table in tables:
            if isinstance(table, dict) and matches_table(table, table_name):
                table_id = normalize(str(table.get("id") or ""))
                if table_id:
                    return table_id
    payload = {
        "name": table_name,
        "dbTableName": DEFAULT_DB_TABLE_NAME,
        "description": "Concise Chummer product operating board. Chummer repositories remain the system of record.",
        "fieldKeyType": "name",
        "fields": [teable_field_definition(field) for field in REQUIRED_FIELDS],
    }
    created = send_json(
        "POST",
        f"{api_base_url}/base/{urllib.parse.quote(base_id)}/table/",
        api_key,
        payload,
        timeout=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
    )
    if not isinstance(created, dict) or not normalize(str(created.get("id") or "")):
        raise RuntimeError("teable_table_create_missing_id")
    return str(created["id"])


def ensure_fields(
    api_base_url: str,
    api_key: str,
    table_id: str,
    *,
    request_timeout_seconds: float,
    deadline_monotonic: float | None = None,
) -> None:
    response = send_json(
        "GET",
        f"{api_base_url}/table/{urllib.parse.quote(table_id)}/field?filterHidden=false",
        api_key,
        timeout=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
    )
    existing = set()
    if isinstance(response, list):
        for field in response:
            if isinstance(field, dict):
                name = normalize(str(field.get("name") or ""))
                if name:
                    existing.add(name.lower())
    for field in REQUIRED_FIELDS:
        if str(field["name"]).lower() in existing:
            continue
        send_json(
            "POST",
            f"{api_base_url}/table/{urllib.parse.quote(table_id)}/field",
            api_key,
            teable_field_definition(field),
            timeout=request_timeout_seconds,
            deadline_monotonic=deadline_monotonic,
        )


def existing_record_ids_by_item_id(
    api_base_url: str,
    api_key: str,
    table_id: str,
    *,
    request_timeout_seconds: float,
    deadline_monotonic: float | None = None,
) -> dict[str, str]:
    response = send_json(
        "GET",
        f"{api_base_url}/table/{urllib.parse.quote(table_id)}/record?fieldKeyType=name&take=1000",
        api_key,
        timeout=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
    )
    if not isinstance(response, dict) or not isinstance(response.get("records"), list):
        raise RuntimeError("teable_record_list_invalid_response")

    result: dict[str, str] = {}
    for record in response["records"]:
        if not isinstance(record, dict):
            continue
        fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
        item_id = normalize(str(fields.get("Item Id") or ""))
        record_id = normalize(str(record.get("id") or ""))
        if not item_id or not record_id:
            continue
        if item_id in result and result[item_id] != record_id:
            raise RuntimeError(f"teable_duplicate_item_id:{item_id}")
        result[item_id] = record_id
    return result


def update_record_batch(
    api_base_url: str,
    api_key: str,
    table_id: str,
    items: list[tuple[ImportantWorkItem, str]],
    synced_at: str,
    *,
    request_timeout_seconds: float,
    deadline_monotonic: float | None = None,
) -> int:
    if not items:
        return 0
    response = send_json(
        "PATCH",
        f"{api_base_url}/table/{urllib.parse.quote(table_id)}/record",
        api_key,
        {
            "fieldKeyType": "name",
            "typecast": True,
            "records": [
                {"id": record_id, "fields": teable_fields_for_row(item, synced_at)}
                for item, record_id in items
            ],
        },
        timeout=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
    )
    if not isinstance(response, list) or len(response) != len(items):
        raise RuntimeError(f"teable_batch_update_count_mismatch:{len(items)}")
    return len(items)


def create_record_batch(
    api_base_url: str,
    api_key: str,
    table_id: str,
    items: list[ImportantWorkItem],
    synced_at: str,
    *,
    request_timeout_seconds: float,
    deadline_monotonic: float | None = None,
) -> int:
    if not items:
        return 0
    response = send_json(
        "POST",
        f"{api_base_url}/table/{urllib.parse.quote(table_id)}/record",
        api_key,
        {
            "fieldKeyType": "name",
            "typecast": True,
            "records": [
                {"fields": teable_fields_for_row(item, synced_at)}
                for item in items
            ],
        },
        timeout=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
    )
    records = response.get("records") if isinstance(response, dict) else None
    if not isinstance(records, list) or len(records) != len(items):
        raise RuntimeError(f"teable_batch_create_count_mismatch:{len(items)}")
    return len(items)


def find_existing_record(
    api_base_url: str,
    api_key: str,
    table_id: str,
    item_id: str,
    *,
    request_timeout_seconds: float,
    deadline_monotonic: float | None = None,
) -> str | None:
    safe_item_id = item_id.replace("'", "\\'")
    filter_by_tql = urllib.parse.quote(f"{{Item Id}} = '{safe_item_id}'")
    response = send_json(
        "GET",
        f"{api_base_url}/table/{urllib.parse.quote(table_id)}/record?fieldKeyType=name&take=1&filterByTql={filter_by_tql}",
        api_key,
        timeout=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
    )
    if not isinstance(response, dict):
        return None
    records = response.get("records")
    if not isinstance(records, list):
        return None
    for record in records:
        if isinstance(record, dict):
            record_id = normalize(str(record.get("id") or ""))
            if record_id:
                return record_id
    return None


def upsert_record(
    api_base_url: str,
    api_key: str,
    table_id: str,
    item: ImportantWorkItem,
    synced_at: str,
    *,
    request_timeout_seconds: float,
    deadline_monotonic: float | None = None,
) -> str:
    fields = teable_fields_for_row(item, synced_at)
    record_id = find_existing_record(
        api_base_url,
        api_key,
        table_id,
        item.item_id,
        request_timeout_seconds=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
    )
    if record_id:
        send_json(
            "PATCH",
            f"{api_base_url}/table/{urllib.parse.quote(table_id)}/record/{urllib.parse.quote(record_id)}",
            api_key,
            {"fieldKeyType": "name", "typecast": True, "record": {"fields": fields}},
            timeout=request_timeout_seconds,
            deadline_monotonic=deadline_monotonic,
        )
        return "updated"
    send_json(
        "POST",
        f"{api_base_url}/table/{urllib.parse.quote(table_id)}/record",
        api_key,
        {"fieldKeyType": "name", "typecast": True, "records": [{"fields": fields}]},
        timeout=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
    )
    return "created"


def sync_to_teable(
    *,
    api_key: str | None,
    api_base_url: str,
    base_id: str | None,
    table_id: str | None,
    table_name: str,
    request_timeout_seconds: float,
    sync_deadline_seconds: float | None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    transient_retry_limit: int = DEFAULT_TRANSIENT_RETRY_LIMIT,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
) -> dict[str, Any]:
    started_at = now_iso()
    started_monotonic = time.monotonic()
    deadline_monotonic = operation_deadline(started_monotonic, sync_deadline_seconds)
    effective_batch_size = max(1, int(batch_size))
    effective_retry_limit = max(0, int(transient_retry_limit))
    rows = important_work_items()
    if not api_key:
        return {
            "state": "blocked",
            "attempted": True,
            "started_at_utc": started_at,
            "request_timeout_seconds": request_timeout_seconds,
            "sync_deadline_seconds": sync_deadline_seconds,
            "batch_size": effective_batch_size,
            "transient_retry_limit": effective_retry_limit,
            "synced_count": 0,
            "failed_count": len(rows),
            "errors": ["teable_api_key_missing"],
        }
    resolved_base_id = base_id
    resolved_table_id = table_id
    try:
        bounded_timeout_seconds(
            request_timeout_seconds,
            deadline_monotonic=deadline_monotonic,
            label="teable_sync",
        )
        if not resolved_table_id:
            if not resolved_base_id:
                resolved_base_id = discover_base_id(
                    api_base_url,
                    api_key,
                    request_timeout_seconds=request_timeout_seconds,
                    deadline_monotonic=deadline_monotonic,
                )
            if not resolved_base_id:
                return {
                    "state": "blocked",
                    "attempted": True,
                    "started_at_utc": started_at,
                    "request_timeout_seconds": request_timeout_seconds,
                    "sync_deadline_seconds": sync_deadline_seconds,
                    "batch_size": effective_batch_size,
                    "transient_retry_limit": effective_retry_limit,
                    "synced_count": 0,
                    "failed_count": len(rows),
                    "errors": ["teable_base_id_required_when_table_id_is_missing"],
                }
            resolved_table_id = resolve_or_create_table(
                api_base_url,
                api_key,
                resolved_base_id,
                table_name,
                request_timeout_seconds=request_timeout_seconds,
                deadline_monotonic=deadline_monotonic,
            )
        ensure_fields(
            api_base_url,
            api_key,
            resolved_table_id,
            request_timeout_seconds=request_timeout_seconds,
            deadline_monotonic=deadline_monotonic,
        )
        existing_record_ids = existing_record_ids_by_item_id(
            api_base_url,
            api_key,
            resolved_table_id,
            request_timeout_seconds=request_timeout_seconds,
            deadline_monotonic=deadline_monotonic,
        )
    except Exception as exc:
        deadline_exceeded = "deadline_exceeded" in str(exc)
        return {
            "state": "failed",
            "attempted": True,
            "started_at_utc": started_at,
            "finished_at_utc": now_iso(),
            "api_base_url": api_base_url,
            "base_id": resolved_base_id,
            "table_id": resolved_table_id,
            "table_name": table_name,
            "request_timeout_seconds": request_timeout_seconds,
            "sync_deadline_seconds": sync_deadline_seconds,
            "batch_size": effective_batch_size,
            "transient_retry_limit": effective_retry_limit,
            "deadline_exceeded": deadline_exceeded,
            "synced_count": 0,
            "failed_count": len(rows),
            "errors": [f"teable_setup:{str(exc)[:180]}"],
        }
    synced_at = now_iso()
    created = 0
    updated = 0
    errors: list[str] = []
    deadline_exceeded = False
    last_item_id: str | None = None
    retry_count = 0
    reconciled_create_count = 0
    completed_batch_count = 0

    update_items = [
        (item, existing_record_ids[item.item_id])
        for item in rows
        if item.item_id in existing_record_ids
    ]
    create_items = [item for item in rows if item.item_id not in existing_record_ids]
    batches: list[tuple[str, list[Any]]] = [
        *[("update", batch) for batch in chunked(update_items, effective_batch_size)],
        *[("create", batch) for batch in chunked(create_items, effective_batch_size)],
    ]
    for action, batch_items in batches:
        if not batch_items:
            continue
        original_batch_items = list(batch_items)
        pending_batch_items = list(batch_items)
        first_item = original_batch_items[0][0] if action == "update" else original_batch_items[0]
        last_item = original_batch_items[-1][0] if action == "update" else original_batch_items[-1]
        last_item_id = last_item.item_id
        batch_retry_count = 0
        while pending_batch_items:
            try:
                bounded_timeout_seconds(
                    request_timeout_seconds,
                    deadline_monotonic=deadline_monotonic,
                    label="teable_sync",
                )
                if action == "update":
                    updated += update_record_batch(
                        api_base_url,
                        api_key,
                        resolved_table_id,
                        pending_batch_items,
                        synced_at,
                        request_timeout_seconds=request_timeout_seconds,
                        deadline_monotonic=deadline_monotonic,
                    )
                else:
                    created += create_record_batch(
                        api_base_url,
                        api_key,
                        resolved_table_id,
                        pending_batch_items,
                        synced_at,
                        request_timeout_seconds=request_timeout_seconds,
                        deadline_monotonic=deadline_monotonic,
                    )
                pending_batch_items = []
                completed_batch_count += 1
            except Exception as exc:  # pragma: no cover - exact provider failures are integration-level.
                error_text = str(exc)
                if "deadline_exceeded" in error_text:
                    deadline_exceeded = True
                    errors.append(f"{action}:{first_item.item_id}..{last_item.item_id}:{error_text[:180]}")
                    break
                if not is_transient_teable_error(exc) or batch_retry_count >= effective_retry_limit:
                    errors.append(f"{action}:{first_item.item_id}..{last_item.item_id}:{error_text[:180]}")
                    break

                if action == "create":
                    try:
                        refreshed_record_ids = existing_record_ids_by_item_id(
                            api_base_url,
                            api_key,
                            resolved_table_id,
                            request_timeout_seconds=request_timeout_seconds,
                            deadline_monotonic=deadline_monotonic,
                        )
                    except Exception as reconciliation_error:
                        errors.append(
                            f"create:{first_item.item_id}..{last_item.item_id}:"
                            f"ambiguous_create_reconciliation_failed:{str(reconciliation_error)[:128]}"
                        )
                        break
                    confirmed_items = [
                        item for item in pending_batch_items if item.item_id in refreshed_record_ids
                    ]
                    if confirmed_items:
                        confirmed_count = len(confirmed_items)
                        created += confirmed_count
                        reconciled_create_count += confirmed_count
                        pending_batch_items = [
                            item for item in pending_batch_items if item.item_id not in refreshed_record_ids
                        ]
                        if not pending_batch_items:
                            completed_batch_count += 1
                            break

                batch_retry_count += 1
                retry_count += 1
                try:
                    sleep_before_teable_retry(
                        batch_retry_count,
                        retry_backoff_seconds=retry_backoff_seconds,
                        deadline_monotonic=deadline_monotonic,
                    )
                except TimeoutError as retry_deadline_error:
                    deadline_exceeded = True
                    errors.append(
                        f"{action}:{first_item.item_id}..{last_item.item_id}:{str(retry_deadline_error)}"
                    )
                    break
        if deadline_exceeded:
            break
    failed = len(rows) - created - updated
    return {
        "state": "passed" if failed == 0 else "failed",
        "attempted": True,
        "started_at_utc": started_at,
        "finished_at_utc": now_iso(),
        "api_base_url": api_base_url,
        "base_id": resolved_base_id,
        "table_id": resolved_table_id,
        "table_name": table_name,
        "request_timeout_seconds": request_timeout_seconds,
        "sync_deadline_seconds": sync_deadline_seconds,
        "batch_size": effective_batch_size,
        "batch_count": len(batches),
        "completed_batch_count": completed_batch_count,
        "transient_retry_limit": effective_retry_limit,
        "retry_count": retry_count,
        "reconciled_create_count": reconciled_create_count,
        "deadline_exceeded": deadline_exceeded,
        "last_item_id": last_item_id,
        "synced_count": created + updated,
        "created_count": created,
        "updated_count": updated,
        "failed_count": failed,
        "errors": errors,
    }


def send_hub_json(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
    timeout: float | None = None,
    *,
    deadline_monotonic: float | None = None,
) -> Any:
    requested_timeout_seconds = resolve_http_timeout_seconds() if timeout is None else float(timeout)
    effective_timeout_seconds = bounded_timeout_seconds(
        requested_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
        label="hub_request",
    )
    data: bytes | None = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 Chummer-Important-Work-Sync",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=effective_timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"hub_http_{exc.code}:{body[:240]}") from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason or "").strip()
        if "timed out" in reason.lower():
            raise RuntimeError(f"hub_timeout_after_{effective_timeout_seconds:g}s") from exc
        raise RuntimeError(f"hub_transport_error:{reason[:180]}") from exc
    except TimeoutError as exc:
        detail = str(exc) or f"hub_timeout_after_{effective_timeout_seconds:g}s"
        raise RuntimeError(detail[:180]) from exc
    if not body.strip():
        return {}
    return json.loads(body)


def important_work_item_to_hub_request(item: ImportantWorkItem) -> dict[str, Any]:
    return {
        "itemId": item.item_id,
        "kind": "workflow",
        "scope": "chummer.run",
        "summary": item.title,
        "detail": "\n".join(
            [
                f"Area: {item.area}",
                f"Cadence: {item.cadence}",
                f"Why it matters: {item.why_it_matters}",
                f"Next action: {item.next_action}",
                f"Acceptance gate: {item.acceptance_gate}",
            ]
        ),
        "status": item.status,
        "priority": item.priority,
        "source": item.source,
        "tags": [item.area, item.priority, item.status],
    }


def seed_hub_store(
    *,
    hub_base_url: str,
    hub_token: str | None,
    request_timeout_seconds: float,
) -> dict[str, Any]:
    started_at = now_iso()
    rows = important_work_items()
    if not hub_token:
        return {
            "state": "blocked",
            "attempted": True,
            "started_at_utc": started_at,
            "request_timeout_seconds": request_timeout_seconds,
            "recorded_count": 0,
            "failed_count": len(rows),
            "errors": ["hub_internal_token_missing"],
        }
    recorded = 0
    errors: list[str] = []
    endpoint = f"{hub_base_url.rstrip('/')}/api/internal/community/important-work"
    for item in rows:
        try:
            send_hub_json(
                "POST",
                endpoint,
                hub_token,
                important_work_item_to_hub_request(item),
                timeout=request_timeout_seconds,
            )
            recorded += 1
        except Exception as exc:  # pragma: no cover - live edge behavior is integration-level.
            errors.append(f"{item.item_id}:{str(exc)[:180]}")
    return {
        "state": "passed" if not errors else "failed",
        "attempted": True,
        "started_at_utc": started_at,
        "finished_at_utc": now_iso(),
        "hub_base_url": hub_base_url.rstrip("/"),
        "request_timeout_seconds": request_timeout_seconds,
        "recorded_count": recorded,
        "failed_count": len(errors),
        "errors": errors,
    }


def resolve_api_base_url() -> str:
    explicit_api = configured_value("CHUMMER_TEABLE_IMPORTANT_WORK_API_BASE_URL", "TEABLE_API_BASE_URL")
    if explicit_api:
        return explicit_api.rstrip("/")
    configured_base = configured_value("TEABLE_BASE_URL", "TEABLE_RUNTIME_BASE_URL")
    if not configured_base:
        return DEFAULT_API_BASE_URL
    configured_base = configured_base.rstrip("/")
    return configured_base if configured_base.endswith("/api") else f"{configured_base}/api"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project the important Chummer workstreams into Teable.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--csv-output", type=Path, default=None, help="Write a Teable import CSV beside the JSON receipt.")
    parser.add_argument("--seed-hub", action="store_true", help="Record the same work rows into the Chummer Hub internal store before Teable sync.")
    parser.add_argument("--hub-base-url", default=configured_value("CHUMMER_PUBLIC_BASE_URL", "CHUMMER_HUB_BASE_URL") or DEFAULT_HUB_BASE_URL)
    parser.add_argument("--hub-token", default=configured_value("FLEET_INTERNAL_API_TOKEN", "CHUMMER_HUB_INTERNAL_API_TOKEN"))
    parser.add_argument("--sync", action="store_true", help="Upsert rows into Teable. Dry-run artifact only by default.")
    parser.add_argument("--api-base-url", default=resolve_api_base_url())
    parser.add_argument("--api-key", default=configured_value("CHUMMER_TEABLE_IMPORTANT_WORK_API_KEY", "TEABLE_API_KEY"))
    parser.add_argument("--base-id", default=configured_value("CHUMMER_TEABLE_IMPORTANT_WORK_BASE_ID"))
    parser.add_argument("--table-id", default=configured_value("CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_ID"))
    parser.add_argument("--table-name", default=configured_value("CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_NAME") or DEFAULT_TABLE_NAME)
    parser.add_argument("--request-timeout-seconds", type=float, default=resolve_http_timeout_seconds())
    parser.add_argument("--sync-deadline-seconds", type=float, default=resolve_sync_deadline_seconds())
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--transient-retry-limit", type=int, default=DEFAULT_TRANSIENT_RETRY_LIMIT)
    parser.add_argument("--retry-backoff-seconds", type=float, default=DEFAULT_RETRY_BACKOFF_SECONDS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    projection = build_projection()
    if args.seed_hub:
        projection["hub_seed"] = seed_hub_store(
            hub_base_url=str(args.hub_base_url),
            hub_token=args.hub_token,
            request_timeout_seconds=float(args.request_timeout_seconds),
        )
        if projection["hub_seed"]["state"] != "passed":
            projection["status"] = "blocked" if projection["hub_seed"]["state"] == "blocked" else "failed"
    if args.sync:
        projection["sync"] = sync_to_teable(
            api_key=args.api_key,
            api_base_url=str(args.api_base_url).rstrip("/"),
            base_id=args.base_id,
            table_id=args.table_id,
            table_name=args.table_name,
            request_timeout_seconds=float(args.request_timeout_seconds),
            sync_deadline_seconds=float(args.sync_deadline_seconds),
            batch_size=int(args.batch_size),
            transient_retry_limit=int(args.transient_retry_limit),
            retry_backoff_seconds=float(args.retry_backoff_seconds),
        )
        if projection["sync"]["state"] != "passed":
            projection["status"] = "blocked" if projection["sync"]["state"] == "blocked" else "failed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(projection, indent=2) + "\n", encoding="utf-8")
    csv_output = args.csv_output or (DEFAULT_CSV_OUTPUT if args.output == DEFAULT_OUTPUT else args.output.with_suffix(".csv"))
    write_csv_projection(csv_output, str(projection["generated_at_utc"]))
    hub_seed_state = projection.get("hub_seed", {}).get("state", "not_requested")
    print(f"teable_important_work:{projection['status']} rows={projection['row_count']} hub_seed={hub_seed_state} sync={projection['sync']['state']} csv={csv_output}")
    return 0 if projection["status"] == "ready" or projection["sync"]["state"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
