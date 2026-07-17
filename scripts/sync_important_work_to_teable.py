#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import fcntl
import ipaddress
import json
import math
import os
import stat
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from magicai_pool_registry import env_assignments as shared_env_assignments
from magicai_pool_registry import magicai_platform_audit as shared_magicai_platform_audit
from magicai_pool_registry import magicai_pool_counts as shared_magicai_pool_counts

PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
SYNC_LOCK_FILENAME = "teable-important-work-sync.lock"
SYNC_LOCK_DIRECTORY_NAME = f"chummer-teable-important-work-sync-{os.geteuid()}"
DEFAULT_SYNC_LOCK_PATH = Path("/tmp") / SYNC_LOCK_DIRECTORY_NAME / SYNC_LOCK_FILENAME
SYNC_LOCK_SIGNATURE = b"chummer.teable-important-work-sync.lock.v1\n"
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
MAX_HTTP_TIMEOUT_SECONDS = 15.0
MAX_SYNC_DEADLINE_SECONDS = 180.0
MAX_TRANSIENT_RETRY_LIMIT = 3
MAX_RETRY_BACKOFF_SECONDS = 5.0
SYNC_LOCK_SCOPE = "host_local_only; cross_host_writers_require_provider_uniqueness_or_distributed_coordination"
SYNC_LOCK_STATE = threading.local()


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
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    assignments: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "a").isalnum() or key[0].isdigit():
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        assignments[key] = value
    return assignments


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


def important_work_items() -> list[ImportantWorkItem]:
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
            status="promoted-gold-proof-passed",
            cadence="after every Windows promotion",
            source="Promoted/native Windows installer gold proof, 2026-07-12",
            why_it_matters="The installer is the first desktop impression; the current promoted build passed native gold proof with compact progress and completion text.",
            next_action="Maintain the premium installer and rerun native gold proof after each future Windows promotion.",
            acceptance_gate="Every promoted Windows installer, including SHA-256 80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91, has fresh native screenshots at 100 percent and 150 percent DPI with no clipping.",
        ),
        ImportantWorkItem(
            item_id="windows-installer-current-shelf-proof",
            title="Current Windows shelf installer proof",
            area="Release",
            priority="P0",
            status="promoted-gold-proof-passed",
            cadence="after every Windows promotion",
            source="Promoted/native Windows installer gold proof, 2026-07-12",
            why_it_matters="The live shelf installer is the exact promoted artifact that passed native Windows gold proof.",
            next_action="Rerun native gold proof after each future Windows promotion and keep the promoted digest aligned with the proof receipt.",
            acceptance_gate="The current promoted Windows installer SHA-256 is 80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91 and every future promoted digest must pass the same native gold-proof gate.",
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
            "started_at_utc": None,
            "finished_at_utc": None,
            "api_base_url": None,
            "sync_lock_path": str(DEFAULT_SYNC_LOCK_PATH),
            "sync_lock_scope": SYNC_LOCK_SCOPE,
            "base_id": None,
            "table_id": None,
            "table_name": DEFAULT_TABLE_NAME,
            "request_timeout_seconds": DEFAULT_HTTP_TIMEOUT_SECONDS,
            "sync_deadline_seconds": DEFAULT_SYNC_DEADLINE_SECONDS,
            "timeout_semantics": "urllib request timeout allocation capped by remaining monotonic sync budget",
            "batch_size": DEFAULT_BATCH_SIZE,
            "batch_count": 0,
            "attempted_batch_count": 0,
            "completed_batch_count": 0,
            "transient_retry_limit": DEFAULT_TRANSIENT_RETRY_LIMIT,
            "retry_backoff_seconds": DEFAULT_RETRY_BACKOFF_SECONDS,
            "retry_count": 0,
            "deadline_exceeded": False,
            "last_item_id": None,
            "total_count": len(rows),
            "row_attempted_count": 0,
            "synced_count": 0,
            "created_count": 0,
            "updated_count": 0,
            "failed_count": 0,
            "unattempted_count": len(rows),
            "ambiguous_create_count": 0,
            "reconciled_create_count": 0,
            "item_outcomes": [
                {
                    "item_id": row["item_id"],
                    "action": None,
                    "outcome": "unattempted",
                    "ambiguous": False,
                    "reconciled": False,
                    "error": None,
                }
                for row in rows
            ],
            "counter_invariants": {
                "total_partition": True,
                "attempted_partition": True,
                "synced_partition": True,
                "action_outcome_alignment": True,
                "all_pass": True,
            },
            "errors": [],
        },
    }


def normalize(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def response_text(value: Any) -> str | None:
    return normalize(value) if isinstance(value, str) else None


def is_loopback_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    lowered = hostname.rstrip(".").lower()
    if lowered == "localhost":
        return True
    try:
        return ipaddress.ip_address(lowered).is_loopback
    except ValueError:
        return False


def validated_api_base_url(value: object) -> str:
    api_base_url = response_text(value)
    if not api_base_url:
        raise RuntimeError("teable_config_api_base_url_invalid")
    try:
        parsed = urllib.parse.urlsplit(api_base_url)
        parsed.port
    except ValueError as exc:
        raise RuntimeError("teable_config_api_base_url_invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("teable_config_api_base_url_invalid")
    if parsed.scheme != "https" and not is_loopback_hostname(parsed.hostname):
        raise RuntimeError("teable_config_api_base_url_invalid")
    return api_base_url.rstrip("/")


def sanitized_api_base_url_for_receipt(value: object) -> str | None:
    api_base_url = response_text(value)
    if not api_base_url:
        return None
    try:
        parsed = urllib.parse.urlsplit(api_base_url)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    hostname = parsed.hostname.rstrip(".").lower()
    rendered_host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = f"{rendered_host}:{port}" if port is not None else rendered_host
    safe_path = urllib.parse.quote(urllib.parse.unquote(parsed.path), safe="/-._~")
    return urllib.parse.urlunsplit((parsed.scheme.lower(), netloc, safe_path.rstrip("/"), "", ""))


def url_origin(url: str) -> tuple[str, str, int] | None:
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None
    return parsed.scheme.lower(), parsed.hostname.rstrip(".").lower(), port


class TeableRequestPhaseError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        request_method: str,
        request_io_started: bool,
        response_received: bool,
    ):
        super().__init__(code)
        self.request_method = request_method.strip().upper()
        self.request_io_started = request_io_started
        self.response_received = response_received


def close_redirect_response(response: Any) -> None:
    if response is None:
        return
    try:
        response.close()
    except Exception:
        pass


class SafeTeableRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        resolved_url = urllib.parse.urljoin(req.full_url, newurl)
        request_method = req.get_method().strip().upper()
        if request_method not in {"GET", "HEAD"}:
            close_redirect_response(fp)
            raise TeableRequestPhaseError(
                "teable_mutation_redirect_blocked",
                request_method=request_method,
                request_io_started=True,
                response_received=True,
            )
        if request_method == "HEAD":
            close_redirect_response(fp)
            raise urllib.error.HTTPError(
                resolved_url,
                470,
                "unsafe_teable_redirect",
                headers,
                None,
            )
        current_origin = url_origin(req.full_url)
        redirect_origin = url_origin(resolved_url)
        if current_origin is None or redirect_origin is None or redirect_origin != current_origin:
            close_redirect_response(fp)
            raise urllib.error.HTTPError(
                resolved_url,
                470,
                "unsafe_teable_redirect",
                headers,
                None,
            )
        return super().redirect_request(req, fp, code, msg, headers, resolved_url)


def open_teable_url(request: urllib.request.Request, timeout: float):
    return urllib.request.build_opener(SafeTeableRedirectHandler()).open(request, timeout=timeout)


def finite_number_for_receipt(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def validated_duration_seconds(value: object, *, code: str, maximum: float) -> float:
    seconds = finite_number_for_receipt(value)
    if seconds is None or seconds <= 0 or seconds > maximum:
        raise RuntimeError(code)
    return seconds


def validated_retry_limit(value: object) -> int:
    try:
        limit = int(value)
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        raise RuntimeError("teable_config_retry_limit_invalid") from None
    if not math.isfinite(numeric) or numeric != limit or limit < 0 or limit > MAX_TRANSIENT_RETRY_LIMIT:
        raise RuntimeError("teable_config_retry_limit_invalid")
    return limit


def validated_retry_backoff_seconds(value: object) -> float:
    backoff = finite_number_for_receipt(value)
    if backoff is None or backoff < 0 or backoff > MAX_RETRY_BACKOFF_SECONDS:
        raise RuntimeError("teable_config_retry_backoff_invalid")
    return backoff


def validated_batch_size(value: object) -> int:
    try:
        batch_size = int(value)
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        raise RuntimeError("teable_config_batch_size_invalid") from None
    if not math.isfinite(numeric) or numeric != batch_size or batch_size < 1:
        raise RuntimeError("teable_config_batch_size_invalid")
    return min(DEFAULT_BATCH_SIZE, batch_size)


def validated_provider_id(value: object, *, kind: str) -> str:
    provider_id = response_text(value)
    if (
        not provider_id
        or len(provider_id) > 128
        or not provider_id.isascii()
        or any(not (character.isalnum() or character in "_-") for character in provider_id)
    ):
        raise RuntimeError(f"teable_{kind}_id_invalid")
    return provider_id


def quoted_provider_id(value: object, *, kind: str) -> str:
    return urllib.parse.quote(validated_provider_id(value, kind=kind), safe="")


def validated_sync_lock_path(value: object) -> Path:
    if isinstance(value, Path):
        path = value.expanduser()
    elif isinstance(value, str) and value.strip():
        path = Path(value.strip()).expanduser()
    else:
        raise RuntimeError("teable_config_sync_lock_path_invalid")
    if (
        not path.is_absolute()
        or ".." in path.parts
        or path.name != SYNC_LOCK_FILENAME
        or path.parent.name != SYNC_LOCK_DIRECTORY_NAME
    ):
        raise RuntimeError("teable_config_sync_lock_path_invalid")
    return path


class TeableSyncLock:
    def __init__(self, path: Path):
        self.path = path
        self.fd: int | None = None

    def acquire(self) -> None:
        fd: int | None = None
        try:
            container_stat = self.path.parent.parent.lstat()
            container_mode = stat.S_IMODE(container_stat.st_mode)
            if (
                not stat.S_ISDIR(container_stat.st_mode)
                or (container_mode & 0o022 and not container_mode & stat.S_ISVTX)
            ):
                raise OSError("lock_container_unrecognized")
            self.path.parent.mkdir(exist_ok=True, mode=0o700)
            parent_stat = self.path.parent.lstat()
            if (
                not stat.S_ISDIR(parent_stat.st_mode)
                or parent_stat.st_uid != os.geteuid()
                or stat.S_IMODE(parent_stat.st_mode) != 0o700
            ):
                raise OSError("lock_parent_unrecognized")
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            try:
                fd = os.open(self.path, flags | os.O_EXCL, 0o600)
                created = True
            except FileExistsError:
                fd = os.open(self.path, flags & ~(os.O_CREAT | os.O_EXCL))
                created = False
            if created:
                os.fchmod(fd, 0o600)
                os.write(fd, SYNC_LOCK_SIGNATURE)
                os.fsync(fd)
            lock_stat = os.fstat(fd)
            if (
                not stat.S_ISREG(lock_stat.st_mode)
                or lock_stat.st_uid != os.geteuid()
                or lock_stat.st_nlink != 1
                or stat.S_IMODE(lock_stat.st_mode) != 0o600
                or lock_stat.st_size != len(SYNC_LOCK_SIGNATURE)
                or os.pread(fd, len(SYNC_LOCK_SIGNATURE) + 1, 0) != SYNC_LOCK_SIGNATURE
            ):
                raise OSError("lock_file_unrecognized")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            if fd is not None:
                os.close(fd)
            raise RuntimeError("teable_sync_busy") from exc
        except OSError as exc:
            if fd is not None:
                os.close(fd)
            code = "teable_sync_lock_unrecognized" if "unrecognized" in str(exc) else "teable_sync_lock_unavailable"
            raise RuntimeError(code) from exc
        assert fd is not None
        self.fd = fd

    def close(self) -> None:
        if self.fd is None:
            return
        fd, self.fd = self.fd, None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

def operation_deadline(start_monotonic: float, deadline_seconds: float | None) -> float | None:
    if deadline_seconds is None:
        raise RuntimeError("teable_config_sync_deadline_invalid")
    return start_monotonic + validated_duration_seconds(
        deadline_seconds,
        code="teable_config_sync_deadline_invalid",
        maximum=MAX_SYNC_DEADLINE_SECONDS,
    )


def bounded_timeout_seconds(
    requested_timeout_seconds: float,
    *,
    deadline_monotonic: float | None,
) -> float:
    timeout_seconds = validated_duration_seconds(
        requested_timeout_seconds,
        code="teable_config_request_timeout_invalid",
        maximum=MAX_HTTP_TIMEOUT_SECONDS,
    )
    if deadline_monotonic is None:
        return timeout_seconds
    remaining = deadline_monotonic - time.monotonic()
    if remaining <= 0:
        raise RuntimeError("teable_sync_deadline_exceeded")
    return min(timeout_seconds, remaining)


def safe_teable_error_code(error: BaseException) -> str:
    text = str(error).strip().lower()
    if "deadline_exceeded" in text:
        return "teable_sync_deadline_exceeded"
    if text.startswith("teable_http_"):
        status = text.removeprefix("teable_http_").split(":", 1)[0]
        return f"teable_http_{status}" if status.isdigit() else "teable_http_error"
    if text.startswith("teable_timeout") or "timed out" in text:
        return "teable_timeout"
    if text.startswith("teable_transport_error"):
        return "teable_transport_error"
    if text.startswith("teable_invalid_json_response"):
        return "teable_invalid_json_response"
    if text.startswith("teable_"):
        # Internal codes are deliberately detail-free.  Never copy provider bodies
        # or transport exception text into a published receipt.
        return text.split(":", 1)[0]
    return f"teable_unexpected_{type(error).__name__.lower()}"


def is_transient_teable_error(error: BaseException) -> bool:
    code = safe_teable_error_code(error)
    return code in {
        "teable_timeout",
        "teable_transport_error",
        "teable_http_408",
        "teable_http_425",
        "teable_http_429",
        "teable_http_500",
        "teable_http_502",
        "teable_http_503",
        "teable_http_504",
        "teable_invalid_json_response",
    } or code.endswith(("_invalid_response", "_count_mismatch", "_id_mismatch", "_fields_mismatch"))


def is_ambiguous_create_error(error: BaseException) -> bool:
    code = safe_teable_error_code(error)
    phase_is_post_io_ambiguous = (
        code in {"teable_sync_deadline_exceeded", "teable_mutation_redirect_blocked"}
        and isinstance(error, TeableRequestPhaseError)
        and error.request_method == "POST"
        and error.request_io_started
        and error.response_received
    )
    return phase_is_post_io_ambiguous or is_transient_teable_error(error) or code.startswith(
        (
            "teable_create_response_",
            "teable_table_create_response_",
            "teable_field_create_response_",
        )
    )


def sleep_before_teable_retry(
    retry_number: int,
    *,
    retry_backoff_seconds: float,
    deadline_monotonic: float | None,
) -> None:
    delay_seconds = validated_retry_backoff_seconds(retry_backoff_seconds) * (2 ** max(0, retry_number - 1))
    if delay_seconds <= 0:
        return
    if deadline_monotonic is not None:
        remaining = deadline_monotonic - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("teable_sync_deadline_exceeded")
        delay_seconds = min(delay_seconds, remaining)
    time.sleep(delay_seconds)


def with_transient_retries(
    operation: Callable[[], Any],
    *,
    transient_retry_limit: int,
    retry_backoff_seconds: float,
    deadline_monotonic: float | None,
    retry_state: dict[str, int] | None,
) -> Any:
    effective_retry_limit = validated_retry_limit(transient_retry_limit)
    effective_retry_backoff = validated_retry_backoff_seconds(retry_backoff_seconds)
    retries = 0
    while True:
        try:
            return operation()
        except Exception as exc:
            if not is_transient_teable_error(exc) or retries >= effective_retry_limit:
                raise
            retries += 1
            if retry_state is not None:
                retry_state["retry_count"] = retry_state.get("retry_count", 0) + 1
            sleep_before_teable_retry(
                retries,
                retry_backoff_seconds=effective_retry_backoff,
                deadline_monotonic=deadline_monotonic,
            )


def send_json(
    method: str,
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    *,
    deadline_monotonic: float | None = None,
) -> Any:
    effective_timeout = bounded_timeout_seconds(
        timeout,
        deadline_monotonic=deadline_monotonic,
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
        with open_teable_url(request, timeout=effective_timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"teable_http_{exc.code}") from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason or "").lower()
        code = "teable_timeout" if "timed out" in reason or "timeout" in reason else "teable_transport_error"
        raise RuntimeError(code) from exc
    except TimeoutError as exc:
        raise RuntimeError("teable_timeout") from exc
    if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
        raise TeableRequestPhaseError(
            "teable_sync_deadline_exceeded",
            request_method=method,
            request_io_started=True,
            response_received=True,
        )
    if not body.strip():
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("teable_invalid_json_response") from exc


def get_json_with_retries(
    url: str,
    api_key: str,
    *,
    request_timeout_seconds: float,
    deadline_monotonic: float | None,
    transient_retry_limit: int,
    retry_backoff_seconds: float,
    retry_state: dict[str, int] | None,
) -> Any:
    return with_transient_retries(
        lambda: send_json(
            "GET",
            url,
            api_key,
            timeout=request_timeout_seconds,
            deadline_monotonic=deadline_monotonic,
        ),
        transient_retry_limit=transient_retry_limit,
        retry_backoff_seconds=retry_backoff_seconds,
        deadline_monotonic=deadline_monotonic,
        retry_state=retry_state,
    )


def discover_base_id(
    api_base_url: str,
    api_key: str,
    *,
    request_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    deadline_monotonic: float | None = None,
    transient_retry_limit: int = DEFAULT_TRANSIENT_RETRY_LIMIT,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    retry_state: dict[str, int] | None = None,
) -> str | None:
    response = get_json_with_retries(
        f"{api_base_url}/base/access/all",
        api_key,
        request_timeout_seconds=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
        transient_retry_limit=transient_retry_limit,
        retry_backoff_seconds=retry_backoff_seconds,
        retry_state=retry_state,
    )
    if not isinstance(response, list):
        raise RuntimeError("teable_base_list_invalid_response")
    ids: list[str] = []
    for entry in response:
        if not isinstance(entry, dict):
            raise RuntimeError("teable_base_list_invalid_response")
        try:
            base_id = validated_provider_id(entry.get("id"), kind="base")
        except RuntimeError as exc:
            raise RuntimeError("teable_base_list_invalid_response") from exc
        ids.append(base_id)
    return ids[0] if len(ids) == 1 else None


def matches_table(entry: dict[str, Any], table_name: str) -> bool:
    names = {
        (response_text(entry.get("name")) or "").lower(),
        (response_text(entry.get("dbTableName")) or "").lower(),
    }
    return table_name.strip().lower() in names or DEFAULT_DB_TABLE_NAME.lower() in names


def read_tables(
    api_base_url: str,
    api_key: str,
    base_id: str,
    *,
    request_timeout_seconds: float,
    deadline_monotonic: float | None,
    transient_retry_limit: int,
    retry_backoff_seconds: float,
    retry_state: dict[str, int] | None,
) -> list[dict[str, Any]]:
    base_path_id = quoted_provider_id(base_id, kind="base")
    tables = get_json_with_retries(
        f"{api_base_url}/base/{base_path_id}/table",
        api_key,
        request_timeout_seconds=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
        transient_retry_limit=transient_retry_limit,
        retry_backoff_seconds=retry_backoff_seconds,
        retry_state=retry_state,
    )
    if not isinstance(tables, list):
        raise RuntimeError("teable_table_list_invalid_response")
    validated: list[dict[str, Any]] = []
    for table in tables:
        if not isinstance(table, dict):
            raise RuntimeError("teable_table_list_invalid_response")
        try:
            validated_provider_id(table.get("id"), kind="table")
        except RuntimeError as exc:
            raise RuntimeError("teable_table_list_invalid_response") from exc
        if not response_text(table.get("name")) and not response_text(table.get("dbTableName")):
            raise RuntimeError("teable_table_list_invalid_response")
        validated.append(table)
    return validated


def matching_table_id(tables: list[dict[str, Any]], table_name: str) -> str | None:
    matches = [validated_provider_id(table["id"], kind="table") for table in tables if matches_table(table, table_name)]
    if len(matches) > 1:
        raise RuntimeError("teable_duplicate_table_match")
    return matches[0] if matches else None


def matching_exact_table_id(tables: list[dict[str, Any]], table_name: str) -> str | None:
    matches = [
        validated_provider_id(table["id"], kind="table")
        for table in tables
        if response_text(table.get("name")) == table_name
        and response_text(table.get("dbTableName")) == DEFAULT_DB_TABLE_NAME
    ]
    if len(matches) > 1:
        raise RuntimeError("teable_duplicate_table_match")
    return matches[0] if matches else None


def resolve_or_create_table(
    api_base_url: str,
    api_key: str,
    base_id: str,
    table_name: str,
    *,
    request_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    deadline_monotonic: float | None = None,
    transient_retry_limit: int = DEFAULT_TRANSIENT_RETRY_LIMIT,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    retry_state: dict[str, int] | None = None,
) -> str:
    base_path_id = quoted_provider_id(base_id, kind="base")
    tables = read_tables(
        api_base_url,
        api_key,
        base_id,
        request_timeout_seconds=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
        transient_retry_limit=transient_retry_limit,
        retry_backoff_seconds=retry_backoff_seconds,
        retry_state=retry_state,
    )
    existing_table_id = matching_table_id(tables, table_name)
    if existing_table_id:
        return existing_table_id
    payload = {
        "name": table_name,
        "dbTableName": DEFAULT_DB_TABLE_NAME,
        "description": "Concise Chummer product operating board. Chummer repositories remain the system of record.",
        "fieldKeyType": "name",
        "fields": [teable_field_definition(field) for field in REQUIRED_FIELDS],
    }
    try:
        created = send_json(
            "POST",
            f"{api_base_url}/base/{base_path_id}/table/",
            api_key,
            payload,
            timeout=request_timeout_seconds,
            deadline_monotonic=deadline_monotonic,
        )
        if not isinstance(created, dict):
            raise RuntimeError("teable_table_create_response_invalid")
        try:
            created_id = validated_provider_id(created.get("id"), kind="table")
        except RuntimeError as id_error:
            raise RuntimeError("teable_table_create_response_invalid") from id_error
        if response_text(created.get("name")) != table_name:
            raise RuntimeError("teable_table_create_response_name_mismatch")
        if response_text(created.get("dbTableName")) != DEFAULT_DB_TABLE_NAME:
            raise RuntimeError("teable_table_create_response_db_name_mismatch")
        return created_id
    except Exception as exc:
        if not is_ambiguous_create_error(exc):
            raise
        refreshed = read_tables(
            api_base_url,
            api_key,
            base_id,
            request_timeout_seconds=request_timeout_seconds,
            deadline_monotonic=deadline_monotonic,
            transient_retry_limit=transient_retry_limit,
            retry_backoff_seconds=retry_backoff_seconds,
            retry_state=retry_state,
        )
        reconciled_table_id = matching_exact_table_id(refreshed, table_name)
        if not reconciled_table_id:
            raise RuntimeError("teable_table_create_ambiguous_unconfirmed") from exc
        return reconciled_table_id


def read_field_names(
    api_base_url: str,
    api_key: str,
    table_id: str,
    *,
    request_timeout_seconds: float,
    deadline_monotonic: float | None,
    transient_retry_limit: int,
    retry_backoff_seconds: float,
    retry_state: dict[str, int] | None,
) -> set[str]:
    table_path_id = quoted_provider_id(table_id, kind="table")
    response = get_json_with_retries(
        f"{api_base_url}/table/{table_path_id}/field?filterHidden=false",
        api_key,
        request_timeout_seconds=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
        transient_retry_limit=transient_retry_limit,
        retry_backoff_seconds=retry_backoff_seconds,
        retry_state=retry_state,
    )
    if not isinstance(response, list):
        raise RuntimeError("teable_field_list_invalid_response")
    existing: set[str] = set()
    lowered_names: set[str] = set()
    for field in response:
        if not isinstance(field, dict):
            raise RuntimeError("teable_field_list_invalid_response")
        name = response_text(field.get("name"))
        if not name:
            raise RuntimeError("teable_field_list_invalid_response")
        lowered = name.lower()
        if lowered in lowered_names:
            raise RuntimeError("teable_field_list_duplicate_name")
        existing.add(name)
        lowered_names.add(lowered)
    return existing


def ensure_fields(
    api_base_url: str,
    api_key: str,
    table_id: str,
    *,
    request_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    deadline_monotonic: float | None = None,
    transient_retry_limit: int = DEFAULT_TRANSIENT_RETRY_LIMIT,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    retry_state: dict[str, int] | None = None,
) -> None:
    table_path_id = quoted_provider_id(table_id, kind="table")
    existing = read_field_names(
        api_base_url,
        api_key,
        table_id,
        request_timeout_seconds=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
        transient_retry_limit=transient_retry_limit,
        retry_backoff_seconds=retry_backoff_seconds,
        retry_state=retry_state,
    )
    for field in REQUIRED_FIELDS:
        expected_name = str(field["name"])
        if expected_name in existing:
            continue
        try:
            created = send_json(
                "POST",
                f"{api_base_url}/table/{table_path_id}/field",
                api_key,
                teable_field_definition(field),
                timeout=request_timeout_seconds,
                deadline_monotonic=deadline_monotonic,
            )
            if not isinstance(created, dict):
                raise RuntimeError("teable_field_create_response_invalid")
            try:
                validated_provider_id(created.get("id"), kind="field")
            except RuntimeError as id_error:
                raise RuntimeError("teable_field_create_response_invalid") from id_error
            returned_name = response_text(created.get("name"))
            if returned_name != expected_name:
                raise RuntimeError("teable_field_create_response_name_mismatch")
            existing.add(expected_name)
        except Exception as exc:
            if not is_ambiguous_create_error(exc):
                raise
            refreshed = read_field_names(
                api_base_url,
                api_key,
                table_id,
                request_timeout_seconds=request_timeout_seconds,
                deadline_monotonic=deadline_monotonic,
                transient_retry_limit=transient_retry_limit,
                retry_backoff_seconds=retry_backoff_seconds,
                retry_state=retry_state,
            )
            if expected_name not in refreshed:
                raise RuntimeError("teable_field_create_ambiguous_unconfirmed") from exc
            existing = refreshed


def validated_item_id(item_id: str) -> str:
    value = normalize(item_id)
    if (
        not value
        or value != item_id
        or len(value) > 128
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise RuntimeError("teable_item_id_invalid")
    return value


def validate_unique_item_ids(items: list[ImportantWorkItem], *, code: str) -> None:
    seen: set[str] = set()
    for item in items:
        item_id = validated_item_id(item.item_id)
        if item_id in seen:
            raise RuntimeError(code)
        seen.add(item_id)


def escaped_tql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def find_existing_record(
    api_base_url: str,
    api_key: str,
    table_id: str,
    item_id: str,
    *,
    request_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    deadline_monotonic: float | None = None,
    transient_retry_limit: int = DEFAULT_TRANSIENT_RETRY_LIMIT,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    retry_state: dict[str, int] | None = None,
    expected_fields: dict[str, str] | None = None,
) -> str | None:
    validated = validated_item_id(item_id)
    table_path_id = quoted_provider_id(table_id, kind="table")
    filter_by_tql = urllib.parse.quote(
        f"{{Item Id}} = '{escaped_tql_string(validated)}'",
        safe="",
    )
    response = get_json_with_retries(
        f"{api_base_url}/table/{table_path_id}/record?fieldKeyType=name&take=2&filterByTql={filter_by_tql}",
        api_key,
        request_timeout_seconds=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
        transient_retry_limit=transient_retry_limit,
        retry_backoff_seconds=retry_backoff_seconds,
        retry_state=retry_state,
    )
    if not isinstance(response, dict) or not isinstance(response.get("records"), list):
        raise RuntimeError("teable_record_lookup_invalid_response")
    records = response["records"]
    if len(records) > 1:
        raise RuntimeError("teable_duplicate_item_id")
    if not records:
        return None
    record = records[0]
    if not isinstance(record, dict):
        raise RuntimeError("teable_record_lookup_invalid_response")
    try:
        record_id = validated_provider_id(record.get("id"), kind="record")
    except RuntimeError as exc:
        raise RuntimeError("teable_record_lookup_invalid_response") from exc
    fields = record.get("fields")
    if not record_id or not isinstance(fields, dict):
        raise RuntimeError("teable_record_lookup_invalid_response")
    returned_item_id = response_text(fields.get("Item Id"))
    if returned_item_id != validated:
        raise RuntimeError("teable_record_lookup_stale")
    if expected_fields is not None:
        for name, expected_value in expected_fields.items():
            actual_value = fields.get(name)
            if not isinstance(actual_value, str) or actual_value != expected_value:
                raise RuntimeError("teable_record_reconciliation_stale")
    return record_id


def chunked(items: list[Any], batch_size: int) -> list[list[Any]]:
    effective_batch_size = min(DEFAULT_BATCH_SIZE, max(1, int(batch_size)))
    return [items[index : index + effective_batch_size] for index in range(0, len(items), effective_batch_size)]


def response_fields_match(fields: object, expected_fields: dict[str, str]) -> bool:
    return isinstance(fields, dict) and all(
        isinstance(fields.get(name), str) and fields[name] == expected_value
        for name, expected_value in expected_fields.items()
    )


def update_record_batch(
    api_base_url: str,
    api_key: str,
    table_id: str,
    items: list[tuple[ImportantWorkItem, str]],
    synced_at: str,
    *,
    request_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    deadline_monotonic: float | None = None,
) -> int:
    if not items:
        return 0
    if len(items) > DEFAULT_BATCH_SIZE:
        raise RuntimeError("teable_update_batch_too_large")
    validate_unique_item_ids([item for item, _ in items], code="teable_update_batch_duplicate_item_id")
    table_path_id = quoted_provider_id(table_id, kind="table")
    validated_items = [
        (item, validated_provider_id(record_id, kind="record"))
        for item, record_id in items
    ]
    response = send_json(
        "PATCH",
        f"{api_base_url}/table/{table_path_id}/record",
        api_key,
        {
            "fieldKeyType": "name",
            "typecast": True,
            "records": [
                {"id": record_id, "fields": teable_fields_for_row(item, synced_at)}
                for item, record_id in validated_items
            ],
        },
        timeout=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
    )
    if not isinstance(response, list) or len(response) != len(items):
        raise RuntimeError("teable_update_response_count_mismatch")
    expected_fields_by_id = {
        record_id: teable_fields_for_row(item, synced_at)
        for item, record_id in validated_items
    }
    expected_ids = set(expected_fields_by_id)
    returned_ids: list[str] = []
    returned_records: dict[str, dict[str, Any]] = {}
    for record in response:
        if not isinstance(record, dict):
            raise RuntimeError("teable_update_response_invalid")
        try:
            returned_id = validated_provider_id(record.get("id"), kind="record")
        except RuntimeError as exc:
            raise RuntimeError("teable_update_response_invalid") from exc
        returned_ids.append(returned_id)
        returned_records[returned_id] = record
    if len(set(returned_ids)) != len(returned_ids) or set(returned_ids) != expected_ids:
        raise RuntimeError("teable_update_response_id_mismatch")
    for returned_id, record in returned_records.items():
        if not response_fields_match(record.get("fields"), expected_fields_by_id[returned_id]):
            raise RuntimeError("teable_update_response_fields_mismatch")
    return len(items)


def create_record_batch(
    api_base_url: str,
    api_key: str,
    table_id: str,
    items: list[ImportantWorkItem],
    synced_at: str,
    *,
    request_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    deadline_monotonic: float | None = None,
) -> int:
    if not items:
        return 0
    if len(items) > DEFAULT_BATCH_SIZE:
        raise RuntimeError("teable_create_batch_too_large")
    validate_unique_item_ids(items, code="teable_create_batch_duplicate_item_id")
    table_path_id = quoted_provider_id(table_id, kind="table")
    response = send_json(
        "POST",
        f"{api_base_url}/table/{table_path_id}/record",
        api_key,
        {
            "fieldKeyType": "name",
            "typecast": True,
            "records": [{"fields": teable_fields_for_row(item, synced_at)} for item in items],
        },
        timeout=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
    )
    records = response.get("records") if isinstance(response, dict) else None
    if not isinstance(records, list) or len(records) != len(items):
        raise RuntimeError("teable_create_response_count_mismatch")
    returned_ids: list[str] = []
    expected_fields_by_item_id = {
        item.item_id: teable_fields_for_row(item, synced_at)
        for item in items
    }
    expected_item_ids = set(expected_fields_by_item_id)
    returned_item_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError("teable_create_response_invalid")
        try:
            returned_ids.append(validated_provider_id(record.get("id"), kind="record"))
        except RuntimeError as exc:
            raise RuntimeError("teable_create_response_invalid") from exc
        fields = record.get("fields")
        if not isinstance(fields, dict):
            raise RuntimeError("teable_create_response_invalid")
        returned_item_id = response_text(fields.get("Item Id"))
        if not returned_item_id or returned_item_id in returned_item_ids:
            raise RuntimeError("teable_create_response_item_id_mismatch")
        expected_fields = expected_fields_by_item_id.get(returned_item_id)
        if expected_fields is None or not response_fields_match(fields, expected_fields):
            raise RuntimeError("teable_create_response_fields_mismatch")
        returned_item_ids.add(returned_item_id)
    if len(set(returned_ids)) != len(returned_ids):
        raise RuntimeError("teable_create_response_id_mismatch")
    if returned_item_ids != expected_item_ids:
        raise RuntimeError("teable_create_response_item_id_mismatch")
    return len(items)


def upsert_record(
    api_base_url: str,
    api_key: str,
    table_id: str,
    item: ImportantWorkItem,
    synced_at: str,
    *,
    request_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    deadline_monotonic: float | None = None,
) -> str:
    record_id = find_existing_record(
        api_base_url,
        api_key,
        table_id,
        item.item_id,
        request_timeout_seconds=request_timeout_seconds,
        deadline_monotonic=deadline_monotonic,
    )
    if record_id:
        update_record_batch(
            api_base_url,
            api_key,
            table_id,
            [(item, record_id)],
            synced_at,
            request_timeout_seconds=request_timeout_seconds,
            deadline_monotonic=deadline_monotonic,
        )
        return "updated"
    try:
        create_record_batch(
            api_base_url,
            api_key,
            table_id,
            [item],
            synced_at,
            request_timeout_seconds=request_timeout_seconds,
            deadline_monotonic=deadline_monotonic,
        )
    except Exception as exc:
        if not is_ambiguous_create_error(exc):
            raise
        reconciled_id = find_existing_record(
            api_base_url,
            api_key,
            table_id,
            item.item_id,
            request_timeout_seconds=request_timeout_seconds,
            deadline_monotonic=deadline_monotonic,
            expected_fields=teable_fields_for_row(item, synced_at),
        )
        if not reconciled_id:
            raise RuntimeError("teable_create_ambiguous_unconfirmed") from exc
    return "created"


def initial_item_outcome_list(rows: list[ImportantWorkItem]) -> list[dict[str, Any]]:
    return [
        {
            "item_id": item.item_id,
            "action": None,
            "outcome": "unattempted",
            "ambiguous": False,
            "reconciled": False,
            "error": None,
        }
        for item in rows
    ]


def initial_item_outcomes(rows: list[ImportantWorkItem]) -> dict[str, dict[str, Any]]:
    return {outcome["item_id"]: outcome for outcome in initial_item_outcome_list(rows)}


def build_sync_result(
    *,
    rows: list[ImportantWorkItem],
    outcomes: dict[str, dict[str, Any]] | list[dict[str, Any]],
    started_at: str,
    api_base_url: str | None,
    sync_lock_path: str | None,
    base_id: str | None,
    table_id: str | None,
    table_name: str,
    request_timeout_seconds: float | None,
    sync_deadline_seconds: float | None,
    batch_size: int | None,
    transient_retry_limit: int | float | None,
    retry_backoff_seconds: float | None,
    retry_state: dict[str, int],
    batch_count: int,
    attempted_batch_count: int,
    completed_batch_count: int,
    last_item_id: str | None,
    deadline_exceeded: bool = False,
    extra_errors: list[str] | None = None,
    forced_state: str | None = None,
) -> dict[str, Any]:
    ordered_outcomes = (
        [outcomes[item.item_id] for item in rows]
        if isinstance(outcomes, dict)
        else list(outcomes)
    )
    created = sum(outcome["outcome"] in {"created", "reconciled_created"} for outcome in ordered_outcomes)
    updated = sum(outcome["outcome"] == "updated" for outcome in ordered_outcomes)
    failed = sum(outcome["outcome"] == "failed" for outcome in ordered_outcomes)
    unattempted = sum(outcome["outcome"] == "unattempted" for outcome in ordered_outcomes)
    row_attempted = sum(
        outcome["action"] in {"update", "create"} and outcome["outcome"] != "unattempted"
        for outcome in ordered_outcomes
    )
    ambiguous = sum(outcome["ambiguous"] is True for outcome in ordered_outcomes)
    reconciled = sum(outcome["reconciled"] is True for outcome in ordered_outcomes)
    errors = list(extra_errors or [])
    errors.extend(
        f"{outcome['item_id']}:{outcome['error']}"
        for outcome in ordered_outcomes
        if outcome["error"]
    )
    effective_deadline_exceeded = deadline_exceeded or any("deadline_exceeded" in error for error in errors)
    state = forced_state or (
        "passed"
        if created + updated == len(rows) and not failed and not unattempted and not effective_deadline_exceeded
        else "failed"
    )
    counter_invariants = {
        "total_partition": len(rows) == created + updated + failed + unattempted,
        "attempted_partition": row_attempted == created + updated + failed,
        "synced_partition": created + updated == sum(
            outcome["outcome"] in {"created", "reconciled_created", "updated"}
            for outcome in ordered_outcomes
        ),
        "action_outcome_alignment": all(
            (outcome["action"] is None) == (outcome["outcome"] == "unattempted")
            for outcome in ordered_outcomes
        ),
    }
    counter_invariants["all_pass"] = all(counter_invariants.values())
    return {
        "state": state,
        "attempted": True,
        "started_at_utc": started_at,
        "finished_at_utc": now_iso(),
        "api_base_url": api_base_url,
        "sync_lock_path": sync_lock_path,
        "sync_lock_scope": SYNC_LOCK_SCOPE,
        "base_id": base_id,
        "table_id": table_id,
        "table_name": table_name,
        "request_timeout_seconds": request_timeout_seconds,
        "sync_deadline_seconds": sync_deadline_seconds,
        "timeout_semantics": "urllib request timeout allocation capped by remaining monotonic sync budget",
        "batch_size": batch_size,
        "batch_count": batch_count,
        "attempted_batch_count": attempted_batch_count,
        "completed_batch_count": completed_batch_count,
        "transient_retry_limit": transient_retry_limit,
        "retry_backoff_seconds": retry_backoff_seconds,
        "retry_count": retry_state.get("retry_count", 0),
        "deadline_exceeded": effective_deadline_exceeded,
        "last_item_id": last_item_id,
        "total_count": len(rows),
        "row_attempted_count": row_attempted,
        "synced_count": created + updated,
        "created_count": created,
        "updated_count": updated,
        "failed_count": failed,
        "unattempted_count": unattempted,
        "ambiguous_create_count": ambiguous,
        "reconciled_create_count": reconciled,
        "item_outcomes": ordered_outcomes,
        "counter_invariants": counter_invariants,
        "errors": errors,
    }


def _sync_to_teable_impl(
    *,
    api_key: str | None,
    api_base_url: str,
    base_id: str | None,
    table_id: str | None,
    table_name: str,
    request_timeout_seconds: object = DEFAULT_HTTP_TIMEOUT_SECONDS,
    sync_deadline_seconds: object = DEFAULT_SYNC_DEADLINE_SECONDS,
    batch_size: object = DEFAULT_BATCH_SIZE,
    transient_retry_limit: object = DEFAULT_TRANSIENT_RETRY_LIMIT,
    retry_backoff_seconds: object = DEFAULT_RETRY_BACKOFF_SECONDS,
    sync_lock_path: object = None,
) -> dict[str, Any]:
    rows = important_work_items()
    started_at = now_iso()
    retry_state = {"retry_count": 0}
    receipt_api_base_url = sanitized_api_base_url_for_receipt(api_base_url)
    effective_lock_input = (
        sync_lock_path
        if sync_lock_path is not None
        else (
            configured_value("CHUMMER_TEABLE_IMPORTANT_WORK_LOCK_PATH")
            or DEFAULT_SYNC_LOCK_PATH
        )
    )

    def validated_or_none(operation: Callable[[], Any]) -> Any:
        try:
            return operation()
        except RuntimeError:
            return None

    receipt_timeout = finite_number_for_receipt(request_timeout_seconds)
    receipt_deadline = finite_number_for_receipt(sync_deadline_seconds)
    receipt_batch_size = validated_or_none(lambda: validated_batch_size(batch_size))
    receipt_retry_limit = validated_or_none(lambda: validated_retry_limit(transient_retry_limit))
    receipt_retry_backoff = finite_number_for_receipt(retry_backoff_seconds)
    receipt_lock_path = validated_or_none(lambda: str(validated_sync_lock_path(effective_lock_input)))
    preliminary_context: dict[str, Any] = {
        "rows": rows,
        "started_at": started_at,
        "api_base_url": receipt_api_base_url,
        "sync_lock_path": receipt_lock_path,
        "base_id": None,
        "table_id": None,
        "table_name": table_name,
        "request_timeout_seconds": receipt_timeout,
        "sync_deadline_seconds": receipt_deadline,
        "batch_size": receipt_batch_size,
        "transient_retry_limit": receipt_retry_limit,
        "retry_backoff_seconds": receipt_retry_backoff,
        "retry_state": retry_state,
        "batch_count": 0,
        "attempted_batch_count": 0,
        "completed_batch_count": 0,
        "last_item_id": None,
        "deadline_exceeded": False,
    }
    try:
        validate_unique_item_ids(rows, code="teable_source_duplicate_item_id")
    except Exception as exc:
        return build_sync_result(
            **preliminary_context,
            outcomes=initial_item_outcome_list(rows),
            extra_errors=[f"teable_source:{safe_teable_error_code(exc)}"],
            forced_state="failed",
        )

    outcomes = initial_item_outcomes(rows)
    try:
        effective_api_base_url = validated_api_base_url(api_base_url)
        effective_timeout = validated_duration_seconds(
            request_timeout_seconds,
            code="teable_config_request_timeout_invalid",
            maximum=MAX_HTTP_TIMEOUT_SECONDS,
        )
        effective_deadline_seconds = validated_duration_seconds(
            sync_deadline_seconds,
            code="teable_config_sync_deadline_invalid",
            maximum=MAX_SYNC_DEADLINE_SECONDS,
        )
        effective_batch_size = validated_batch_size(batch_size)
        effective_retry_limit = validated_retry_limit(transient_retry_limit)
        effective_retry_backoff = validated_retry_backoff_seconds(retry_backoff_seconds)
        effective_lock_path = validated_sync_lock_path(effective_lock_input)
        resolved_base_id = validated_provider_id(base_id, kind="base") if base_id is not None else None
        resolved_table_id = validated_provider_id(table_id, kind="table") if table_id is not None else None
    except Exception as exc:
        return build_sync_result(
            **preliminary_context,
            outcomes=outcomes,
            extra_errors=[f"teable_configuration:{safe_teable_error_code(exc)}"],
            forced_state="failed",
        )

    result_context: dict[str, Any] = {
        "rows": rows,
        "outcomes": outcomes,
        "started_at": started_at,
        "api_base_url": receipt_api_base_url,
        "sync_lock_path": str(effective_lock_path),
        "base_id": resolved_base_id,
        "table_id": resolved_table_id,
        "table_name": table_name,
        "request_timeout_seconds": effective_timeout,
        "sync_deadline_seconds": effective_deadline_seconds,
        "batch_size": effective_batch_size,
        "transient_retry_limit": effective_retry_limit,
        "retry_backoff_seconds": effective_retry_backoff,
        "retry_state": retry_state,
        "batch_count": 0,
        "attempted_batch_count": 0,
        "completed_batch_count": 0,
        "last_item_id": None,
        "deadline_exceeded": False,
    }
    if not api_key:
        return build_sync_result(
            **result_context,
            extra_errors=["teable_api_key_missing"],
            forced_state="blocked",
        )

    sync_lock = TeableSyncLock(effective_lock_path)
    SYNC_LOCK_STATE.lock = sync_lock
    try:
        sync_lock.acquire()
    except Exception as exc:
        return build_sync_result(
            **result_context,
            extra_errors=[f"teable_lock:{safe_teable_error_code(exc)}"],
            forced_state="failed",
        )

    started_monotonic = time.monotonic()
    deadline_monotonic = operation_deadline(started_monotonic, effective_deadline_seconds)

    def finish_locked(result: dict[str, Any]) -> dict[str, Any]:
        sync_lock.close()
        return result

    api_base_url = effective_api_base_url
    retry_backoff_seconds = effective_retry_backoff
    try:
        bounded_timeout_seconds(effective_timeout, deadline_monotonic=deadline_monotonic)
        if not resolved_table_id:
            if not resolved_base_id:
                resolved_base_id = discover_base_id(
                    api_base_url,
                    api_key,
                    request_timeout_seconds=effective_timeout,
                    deadline_monotonic=deadline_monotonic,
                    transient_retry_limit=effective_retry_limit,
                    retry_backoff_seconds=retry_backoff_seconds,
                    retry_state=retry_state,
                )
            if not resolved_base_id:
                result_context["base_id"] = resolved_base_id
                return finish_locked(
                    build_sync_result(
                        **result_context,
                        extra_errors=["teable_base_id_required_when_table_id_is_missing"],
                        forced_state="blocked",
                    )
                )
            resolved_table_id = resolve_or_create_table(
                api_base_url,
                api_key,
                resolved_base_id,
                table_name,
                request_timeout_seconds=effective_timeout,
                deadline_monotonic=deadline_monotonic,
                transient_retry_limit=effective_retry_limit,
                retry_backoff_seconds=retry_backoff_seconds,
                retry_state=retry_state,
            )
        ensure_fields(
            api_base_url,
            api_key,
            resolved_table_id,
            request_timeout_seconds=effective_timeout,
            deadline_monotonic=deadline_monotonic,
            transient_retry_limit=effective_retry_limit,
            retry_backoff_seconds=retry_backoff_seconds,
            retry_state=retry_state,
        )

        # Complete and validate every exact-key lookup before the first record POST.
        # Item Id is not provider-enforced unique, so a duplicate is a hard stop.
        existing_record_ids: dict[str, str] = {}
        for item in rows:
            record_id = find_existing_record(
                api_base_url,
                api_key,
                resolved_table_id,
                item.item_id,
                request_timeout_seconds=effective_timeout,
                deadline_monotonic=deadline_monotonic,
                transient_retry_limit=effective_retry_limit,
                retry_backoff_seconds=retry_backoff_seconds,
                retry_state=retry_state,
            )
            if record_id:
                existing_record_ids[item.item_id] = record_id
    except Exception as exc:
        result_context["base_id"] = resolved_base_id
        result_context["table_id"] = resolved_table_id
        return finish_locked(
            build_sync_result(
                **result_context,
                extra_errors=[f"teable_setup:{safe_teable_error_code(exc)}"],
                forced_state="failed",
            )
        )

    result_context["base_id"] = resolved_base_id
    result_context["table_id"] = resolved_table_id
    synced_at = now_iso()
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
    result_context["batch_count"] = len(batches)
    for action, batch in batches:
        batch_items = [entry[0] for entry in batch] if action == "update" else list(batch)
        for item in batch_items:
            outcomes[item.item_id]["action"] = action
        result_context["attempted_batch_count"] += 1
        result_context["last_item_id"] = batch_items[-1].item_id
        if action == "update":
            try:
                with_transient_retries(
                    lambda: update_record_batch(
                        api_base_url,
                        api_key,
                        resolved_table_id,
                        batch,
                        synced_at,
                        request_timeout_seconds=effective_timeout,
                        deadline_monotonic=deadline_monotonic,
                    ),
                    transient_retry_limit=effective_retry_limit,
                    retry_backoff_seconds=retry_backoff_seconds,
                    deadline_monotonic=deadline_monotonic,
                    retry_state=retry_state,
                )
            except Exception as exc:
                code = safe_teable_error_code(exc)
                for item in batch_items:
                    outcomes[item.item_id]["outcome"] = "failed"
                    outcomes[item.item_id]["error"] = code
                if code == "teable_sync_deadline_exceeded":
                    result_context["deadline_exceeded"] = True
                    break
            else:
                for item in batch_items:
                    outcomes[item.item_id]["outcome"] = "updated"
                result_context["completed_batch_count"] += 1
            continue

        try:
            # Record creation is intentionally single-attempt.  Retrying a POST
            # after an ambiguous transport result can duplicate Item Id rows.
            create_record_batch(
                api_base_url,
                api_key,
                resolved_table_id,
                batch_items,
                synced_at,
                request_timeout_seconds=effective_timeout,
                deadline_monotonic=deadline_monotonic,
            )
        except Exception as exc:
            code = safe_teable_error_code(exc)
            if code == "teable_sync_deadline_exceeded":
                result_context["deadline_exceeded"] = True
            if not is_ambiguous_create_error(exc):
                for item in batch_items:
                    outcomes[item.item_id]["outcome"] = "failed"
                    outcomes[item.item_id]["error"] = code
                if code == "teable_sync_deadline_exceeded":
                    break
                continue

            for item in batch_items:
                outcomes[item.item_id]["ambiguous"] = True
            reconciliation_deadline_hit = False
            for item in batch_items:
                if reconciliation_deadline_hit:
                    outcomes[item.item_id]["outcome"] = "failed"
                    outcomes[item.item_id]["error"] = "teable_sync_deadline_exceeded"
                    continue
                try:
                    reconciled_id = find_existing_record(
                        api_base_url,
                        api_key,
                        resolved_table_id,
                        item.item_id,
                        request_timeout_seconds=effective_timeout,
                        deadline_monotonic=deadline_monotonic,
                        transient_retry_limit=effective_retry_limit,
                        retry_backoff_seconds=retry_backoff_seconds,
                        retry_state=retry_state,
                        expected_fields=teable_fields_for_row(item, synced_at),
                    )
                except Exception as reconciliation_error:
                    reconciliation_code = safe_teable_error_code(reconciliation_error)
                    outcomes[item.item_id]["outcome"] = "failed"
                    outcomes[item.item_id]["error"] = reconciliation_code
                    if reconciliation_code == "teable_sync_deadline_exceeded":
                        result_context["deadline_exceeded"] = True
                        reconciliation_deadline_hit = True
                else:
                    if reconciled_id:
                        outcomes[item.item_id]["outcome"] = "reconciled_created"
                        outcomes[item.item_id]["reconciled"] = True
                    else:
                        outcomes[item.item_id]["outcome"] = "failed"
                        outcomes[item.item_id]["error"] = "teable_create_reconciliation_absent"
            if all(outcomes[item.item_id]["outcome"] == "reconciled_created" for item in batch_items):
                result_context["completed_batch_count"] += 1
            if reconciliation_deadline_hit:
                break
        else:
            for item in batch_items:
                outcomes[item.item_id]["outcome"] = "created"
            result_context["completed_batch_count"] += 1

    return finish_locked(build_sync_result(**result_context))


def sync_to_teable(**kwargs: Any) -> dict[str, Any]:
    previous_lock = getattr(SYNC_LOCK_STATE, "lock", None)
    try:
        return _sync_to_teable_impl(**kwargs)
    finally:
        current_lock = getattr(SYNC_LOCK_STATE, "lock", None)
        if current_lock is not None and current_lock is not previous_lock:
            current_lock.close()
        if previous_lock is None:
            if hasattr(SYNC_LOCK_STATE, "lock"):
                del SYNC_LOCK_STATE.lock
        else:
            SYNC_LOCK_STATE.lock = previous_lock


class RejectHubRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        close_redirect_response(fp)
        raise RuntimeError("hub_redirect_blocked")


def open_hub_url(request: urllib.request.Request, *, timeout: float):
    return urllib.request.build_opener(RejectHubRedirectHandler()).open(
        request,
        timeout=timeout,
    )


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
        with open_hub_url(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"hub_http_{exc.code}") from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason or "").lower()
        code = "hub_timeout" if "timed out" in reason or "timeout" in reason else "hub_transport_error"
        raise RuntimeError(code) from exc
    except TimeoutError as exc:
        raise RuntimeError("hub_timeout") from exc
    if not body.strip():
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("hub_invalid_json_response") from exc


def safe_hub_error_code(error: BaseException) -> str:
    text = str(error).strip().lower()
    if text.startswith("hub_http_"):
        status = text.removeprefix("hub_http_").split(":", 1)[0]
        return f"hub_http_{status}" if status.isdigit() else "hub_http_error"
    if text.startswith("hub_"):
        return text.split(":", 1)[0]
    return f"hub_unexpected_{type(error).__name__.lower()}"


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
            errors.append(f"{item.item_id}:{safe_hub_error_code(exc)}")
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
    explicit_api = configured_value(
        "CHUMMER_TEABLE_IMPORTANT_WORK_API_BASE_URL",
        "TEABLE_API_BASE_URL",
    )
    if explicit_api:
        return explicit_api.rstrip("/")
    configured_base = configured_value("TEABLE_BASE_URL", "TEABLE_RUNTIME_BASE_URL")
    if not configured_base:
        return DEFAULT_API_BASE_URL
    configured_base = configured_base.rstrip("/")
    return configured_base if configured_base.endswith("/api") else f"{configured_base}/api"


def resolve_http_timeout_seconds() -> object:
    return configured_value("CHUMMER_TEABLE_HTTP_TIMEOUT_SECONDS") or DEFAULT_HTTP_TIMEOUT_SECONDS


def resolve_sync_deadline_seconds() -> object:
    return (
        configured_value("CHUMMER_TEABLE_IMPORTANT_WORK_SYNC_DEADLINE_SECONDS")
        or DEFAULT_SYNC_DEADLINE_SECONDS
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project the important Chummer workstreams into Teable.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--csv-output", type=Path, default=None, help="Write a Teable import CSV beside the JSON receipt.")
    parser.add_argument("--seed-hub", action="store_true", help="Record the same work rows into the Chummer Hub internal store before Teable sync.")
    parser.add_argument(
        "--hub-base-url",
        default=configured_value("CHUMMER_PUBLIC_BASE_URL", "CHUMMER_HUB_BASE_URL")
        or DEFAULT_HUB_BASE_URL,
    )
    parser.add_argument(
        "--hub-token",
        default=configured_value("FLEET_INTERNAL_API_TOKEN", "CHUMMER_HUB_INTERNAL_API_TOKEN"),
    )
    parser.add_argument("--sync", action="store_true", help="Upsert rows into Teable. Dry-run artifact only by default.")
    parser.add_argument("--api-base-url", default=resolve_api_base_url())
    parser.add_argument(
        "--api-key",
        default=configured_value("CHUMMER_TEABLE_IMPORTANT_WORK_API_KEY", "TEABLE_API_KEY"),
    )
    parser.add_argument(
        "--base-id",
        default=configured_value("CHUMMER_TEABLE_IMPORTANT_WORK_BASE_ID"),
    )
    parser.add_argument(
        "--table-id",
        default=configured_value("CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_ID"),
    )
    parser.add_argument(
        "--table-name",
        default=configured_value("CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_NAME")
        or DEFAULT_TABLE_NAME,
    )
    parser.add_argument("--request-timeout-seconds", default=resolve_http_timeout_seconds())
    parser.add_argument("--sync-deadline-seconds", default=resolve_sync_deadline_seconds())
    parser.add_argument("--batch-size", default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--transient-retry-limit", default=DEFAULT_TRANSIENT_RETRY_LIMIT)
    parser.add_argument("--retry-backoff-seconds", default=DEFAULT_RETRY_BACKOFF_SECONDS)
    parser.add_argument(
        "--sync-lock-path",
        default=configured_value("CHUMMER_TEABLE_IMPORTANT_WORK_LOCK_PATH")
        or DEFAULT_SYNC_LOCK_PATH,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
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
            request_timeout_seconds=args.request_timeout_seconds,
            sync_deadline_seconds=args.sync_deadline_seconds,
            batch_size=args.batch_size,
            transient_retry_limit=args.transient_retry_limit,
            retry_backoff_seconds=args.retry_backoff_seconds,
            sync_lock_path=args.sync_lock_path,
        )
        if projection["sync"]["state"] != "passed":
            projection["status"] = "blocked" if projection["sync"]["state"] == "blocked" else "failed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(projection, indent=2) + "\n", encoding="utf-8")
    csv_output = args.csv_output or (DEFAULT_CSV_OUTPUT if args.output == DEFAULT_OUTPUT else args.output.with_suffix(".csv"))
    write_csv_projection(csv_output, str(projection["generated_at_utc"]))
    hub_seed_state = projection.get("hub_seed", {}).get("state", "not_requested")
    print(f"teable_important_work:{projection['status']} rows={projection['row_count']} hub_seed={hub_seed_state} sync={projection['sync']['state']} csv={csv_output}")
    requested_lane_states = []
    if args.seed_hub:
        requested_lane_states.append(projection["hub_seed"]["state"])
    if args.sync:
        requested_lane_states.append(projection["sync"]["state"])
    return 0 if projection["status"] == "ready" and all(state == "passed" for state in requested_lane_states) else 2


if __name__ == "__main__":
    raise SystemExit(main())
