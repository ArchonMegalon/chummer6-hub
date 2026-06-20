#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
DEFAULT_OUTPUT = PUBLISHED_ROOT / "TEABLE_IMPORTANT_WORK.generated.json"
DEFAULT_CSV_OUTPUT = PUBLISHED_ROOT / "TEABLE_IMPORTANT_WORK.csv"
DEFAULT_TEABLE_ORIGIN = "https://app.teable.ai"
DEFAULT_API_BASE_URL = "https://app.teable.ai/api"
DEFAULT_TABLE_NAME = "Chummer Important Work"
DEFAULT_DB_TABLE_NAME = "chummer_important_work"


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
            next_action="Verify the next installed desktop build starts from race/metatype and archetype, shows the story first, and labels the primary handoff as a book before audio/video.",
            acceptance_gate="A user can start a dossier, read the story first, open the FlipLink-style book, then request audio/video without touching advanced controls.",
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
            status="active",
            cadence="daily until screenshots pass",
            source="User and visual audit",
            why_it_matters="The installer is the first desktop impression and currently has oversized clipped text.",
            next_action="Redesign installer layout, typography, DPI behavior, progress, and completion states.",
            acceptance_gate="Windows installer screenshots at 100 percent and 150 percent DPI show no clipping and feel consistent with Chummer.",
        ),
        ImportantWorkItem(
            item_id="windows-installer-current-shelf-proof",
            title="Current Windows shelf installer proof",
            area="Release",
            priority="P0",
            status="blocked-until-next-publish",
            cadence="next scheduled 08:00 publish",
            source="Windows installer gold proof runs 27872347490 and 27872430827",
            why_it_matters="Fresh installer code now passes visual proof, but the currently published shelf installer is still the older build and cannot complete the proof chain.",
            next_action="At the next scheduled morning publish, promote the Windows build that contains the modeless completion prompt and rerun the native installer gold proof against the promoted shelf artifact.",
            acceptance_gate="The promoted Windows installer artifact SHA matches the proof receipt and has progress plus completion screenshots at 100 percent and 150 percent DPI.",
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
            acceptance_gate="After a build, chummer.run/downloads exposes the newest Windows and Linux installers with no account-first noise.",
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
            why_it_matters="Owned tools such as Dadan, Rybbit, NeuronWriter, Humanizer, VidBoard, and Subscribr need explicit bounded roles.",
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


def send_json(method: str, url: str, api_key: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> Any:
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
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"teable_http_{exc.code}:{body[:240]}") from exc
    if not body.strip():
        return {}
    return json.loads(body)


def discover_base_id(api_base_url: str, api_key: str) -> str | None:
    response = send_json("GET", f"{api_base_url}/base/access/all", api_key)
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


def resolve_or_create_table(api_base_url: str, api_key: str, base_id: str, table_name: str) -> str:
    tables = send_json("GET", f"{api_base_url}/base/{urllib.parse.quote(base_id)}/table", api_key)
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
    created = send_json("POST", f"{api_base_url}/base/{urllib.parse.quote(base_id)}/table/", api_key, payload)
    if not isinstance(created, dict) or not normalize(str(created.get("id") or "")):
        raise RuntimeError("teable_table_create_missing_id")
    return str(created["id"])


def ensure_fields(api_base_url: str, api_key: str, table_id: str) -> None:
    response = send_json("GET", f"{api_base_url}/table/{urllib.parse.quote(table_id)}/field?filterHidden=false", api_key)
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
        send_json("POST", f"{api_base_url}/table/{urllib.parse.quote(table_id)}/field", api_key, teable_field_definition(field))


def find_existing_record(api_base_url: str, api_key: str, table_id: str, item_id: str) -> str | None:
    safe_item_id = item_id.replace("'", "\\'")
    filter_by_tql = urllib.parse.quote(f"{{Item Id}} = '{safe_item_id}'")
    response = send_json(
        "GET",
        f"{api_base_url}/table/{urllib.parse.quote(table_id)}/record?fieldKeyType=name&take=1&filterByTql={filter_by_tql}",
        api_key,
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


def upsert_record(api_base_url: str, api_key: str, table_id: str, item: ImportantWorkItem, synced_at: str) -> str:
    fields = teable_fields_for_row(item, synced_at)
    record_id = find_existing_record(api_base_url, api_key, table_id, item.item_id)
    if record_id:
        send_json(
            "PATCH",
            f"{api_base_url}/table/{urllib.parse.quote(table_id)}/record/{urllib.parse.quote(record_id)}",
            api_key,
            {"fieldKeyType": "name", "typecast": True, "record": {"fields": fields}},
        )
        return "updated"
    send_json(
        "POST",
        f"{api_base_url}/table/{urllib.parse.quote(table_id)}/record",
        api_key,
        {"fieldKeyType": "name", "typecast": True, "records": [{"fields": fields}]},
    )
    return "created"


def sync_to_teable(
    *,
    api_key: str | None,
    api_base_url: str,
    base_id: str | None,
    table_id: str | None,
    table_name: str,
) -> dict[str, Any]:
    started_at = now_iso()
    if not api_key:
        return {
            "state": "blocked",
            "attempted": True,
            "started_at_utc": started_at,
            "synced_count": 0,
            "failed_count": len(important_work_items()),
            "errors": ["teable_api_key_missing"],
        }
    resolved_base_id = base_id
    resolved_table_id = table_id
    try:
        if not resolved_table_id:
            if not resolved_base_id:
                resolved_base_id = discover_base_id(api_base_url, api_key)
            if not resolved_base_id:
                return {
                    "state": "blocked",
                    "attempted": True,
                    "started_at_utc": started_at,
                    "synced_count": 0,
                    "failed_count": len(important_work_items()),
                    "errors": ["teable_base_id_required_when_table_id_is_missing"],
                }
            resolved_table_id = resolve_or_create_table(api_base_url, api_key, resolved_base_id, table_name)
        ensure_fields(api_base_url, api_key, resolved_table_id)
    except Exception as exc:
        return {
            "state": "failed",
            "attempted": True,
            "started_at_utc": started_at,
            "finished_at_utc": now_iso(),
            "api_base_url": api_base_url,
            "base_id": resolved_base_id,
            "table_id": resolved_table_id,
            "table_name": table_name,
            "synced_count": 0,
            "failed_count": len(important_work_items()),
            "errors": [f"teable_setup:{str(exc)[:180]}"],
        }
    synced_at = now_iso()
    created = 0
    updated = 0
    errors: list[str] = []
    for item in important_work_items():
        try:
            result = upsert_record(api_base_url, api_key, resolved_table_id, item, synced_at)
            if result == "created":
                created += 1
            else:
                updated += 1
        except Exception as exc:  # pragma: no cover - exact provider failures are integration-level.
            errors.append(f"{item.item_id}:{str(exc)[:180]}")
    failed = len(errors)
    return {
        "state": "passed" if failed == 0 else "failed",
        "attempted": True,
        "started_at_utc": started_at,
        "finished_at_utc": now_iso(),
        "api_base_url": api_base_url,
        "base_id": resolved_base_id,
        "table_id": resolved_table_id,
        "table_name": table_name,
        "synced_count": created + updated,
        "created_count": created,
        "updated_count": updated,
        "failed_count": failed,
        "errors": errors,
    }


def resolve_api_base_url() -> str:
    explicit_api = normalize(os.environ.get("CHUMMER_TEABLE_IMPORTANT_WORK_API_BASE_URL")) or normalize(os.environ.get("TEABLE_API_BASE_URL"))
    if explicit_api:
        return explicit_api.rstrip("/")
    configured_base = normalize(os.environ.get("TEABLE_BASE_URL")) or normalize(os.environ.get("TEABLE_RUNTIME_BASE_URL"))
    if not configured_base:
        return DEFAULT_API_BASE_URL
    configured_base = configured_base.rstrip("/")
    return configured_base if configured_base.endswith("/api") else f"{configured_base}/api"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project the important Chummer workstreams into Teable.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--csv-output", type=Path, default=None, help="Write a Teable import CSV beside the JSON receipt.")
    parser.add_argument("--sync", action="store_true", help="Upsert rows into Teable. Dry-run artifact only by default.")
    parser.add_argument("--api-base-url", default=resolve_api_base_url())
    parser.add_argument("--api-key", default=normalize(os.environ.get("CHUMMER_TEABLE_IMPORTANT_WORK_API_KEY")) or normalize(os.environ.get("TEABLE_API_KEY")))
    parser.add_argument("--base-id", default=normalize(os.environ.get("CHUMMER_TEABLE_IMPORTANT_WORK_BASE_ID")) or normalize(os.environ.get("EA_ENV_TEABLE_BASE_ID")))
    parser.add_argument("--table-id", default=normalize(os.environ.get("CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_ID")))
    parser.add_argument("--table-name", default=normalize(os.environ.get("CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_NAME")) or DEFAULT_TABLE_NAME)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    projection = build_projection()
    if args.sync:
        projection["sync"] = sync_to_teable(
            api_key=args.api_key,
            api_base_url=str(args.api_base_url).rstrip("/"),
            base_id=args.base_id,
            table_id=args.table_id,
            table_name=args.table_name,
        )
        if projection["sync"]["state"] != "passed":
            projection["status"] = "blocked" if projection["sync"]["state"] == "blocked" else "failed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(projection, indent=2) + "\n", encoding="utf-8")
    csv_output = args.csv_output or (DEFAULT_CSV_OUTPUT if args.output == DEFAULT_OUTPUT else args.output.with_suffix(".csv"))
    write_csv_projection(csv_output, str(projection["generated_at_utc"]))
    print(f"teable_important_work:{projection['status']} rows={projection['row_count']} sync={projection['sync']['state']} csv={csv_output}")
    return 0 if projection["status"] == "ready" or projection["sync"]["state"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
