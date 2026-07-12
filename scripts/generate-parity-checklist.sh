#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_PATH="${PARITY_CHECKLIST_OUTPUT:-$REPO_ROOT/docs/PARITY_CHECKLIST.md}"

python3 - "$REPO_ROOT" "$OUTPUT_PATH" <<'PY'
from __future__ import annotations

import pathlib
import re
import sys
import json
import os
from typing import Sequence


repo_root = pathlib.Path(sys.argv[1])
output_path = pathlib.Path(sys.argv[2])
sys.path.insert(0, str(repo_root))

from scripts.parity_source_parser import extract_switch_expression_body as extract_csharp_switch_expression_body

parity_oracle_path = repo_root / "docs" / "PARITY_ORACLE.json"

default_core_engine_root = repo_root.parent / "chummer-core-engine"
core_engine_root = pathlib.Path(os.environ.get("CHUMMER_CORE_ENGINE_ROOT", str(default_core_engine_root)))
default_presentation_root = repo_root.parent / "chummer-presentation"
presentation_root = pathlib.Path(os.environ.get("CHUMMER_PRESENTATION_ROOT", str(default_presentation_root)))
navigation_catalog_path = pathlib.Path(
    os.environ.get(
        "CHUMMER_PARITY_NAVIGATION_TAB_CATALOG_PATH",
        str(core_engine_root / "Chummer.Rulesets.Hosting" / "Presentation" / "NavigationTabCatalog.cs"),
    )
)
action_catalog_path = pathlib.Path(
    os.environ.get(
        "CHUMMER_PARITY_WORKSPACE_ACTION_CATALOG_PATH",
        str(core_engine_root / "Chummer.Rulesets.Hosting" / "Presentation" / "WorkspaceSurfaceActionCatalog.cs"),
    )
)
desktop_dialog_factory_path = pathlib.Path(
    os.environ.get(
        "CHUMMER_PARITY_DESKTOP_DIALOG_FACTORY_PATH",
        str(presentation_root / "Chummer.Presentation" / "Overview" / "DesktopDialogFactory.cs"),
    )
)
overview_command_policy_path = pathlib.Path(
    os.environ.get(
        "CHUMMER_PARITY_OVERVIEW_COMMAND_POLICY_PATH",
        str(presentation_root / "Chummer.Presentation" / "Overview" / "OverviewCommandPolicy.cs"),
    )
)


def read_text(path: pathlib.Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"required source file is missing: {path}")
    return path.read_text(encoding="utf-8")

def display_path(path: pathlib.Path) -> str:
    try:
        return os.path.relpath(path, repo_root)
    except ValueError:
        return str(path)


def normalize_required_token(raw_value: object, *, source: str) -> str:
    if not isinstance(raw_value, str):
        raise ValueError(f"{source} must contain only string token values")
    token = raw_value.strip()
    if not token:
        raise ValueError(f"{source} must not contain blank token values")
    if token != raw_value:
        raise ValueError(f"{source} contains whitespace-padded token '{raw_value}'")
    canonical_token = token.lower()
    if token != canonical_token:
        raise ValueError(
            f"{source} contains non-canonical token '{raw_value}' "
            f"(expected '{canonical_token}')"
        )
    return token


def parse_required_token_list(oracle: dict[str, object], key: str, *, source: str) -> list[str]:
    raw_values = oracle.get(key)
    if not isinstance(raw_values, list):
        raise ValueError(f"{source}.{key} must be a JSON array")

    normalized_tokens: dict[str, str] = {}
    tokens: list[str] = []
    for index, raw_value in enumerate(raw_values):
        token = normalize_required_token(raw_value, source=f"{source}.{key}[{index}]")
        normalized_key = token.casefold()
        if normalized_key in normalized_tokens:
            raise ValueError(
                f"{source}.{key} contains duplicate normalized token '{token}' "
                f"(existing '{normalized_tokens[normalized_key]}')"
            )
        normalized_tokens[normalized_key] = token
        tokens.append(token)
    canonical_order = sorted(tokens)
    if tokens != canonical_order:
        raise ValueError(
            f"{source}.{key} must preserve canonical token ordering "
            f"(actual={tokens}, expected={canonical_order})"
        )
    return canonical_order


def parse_catalog_token_matches(matches: Sequence[str], *, source: str, allow_duplicate_ids: bool) -> list[str]:
    normalized_tokens: dict[str, str] = {}
    for index, raw_value in enumerate(matches):
        token = normalize_required_token(raw_value, source=f"{source}[{index}]")
        normalized_key = token.casefold()
        if normalized_key in normalized_tokens:
            if allow_duplicate_ids:
                continue
            raise ValueError(
                f"{source} contains duplicate normalized token '{token}' "
                f"(existing '{normalized_tokens[normalized_key]}')"
            )
        normalized_tokens[normalized_key] = token
    return sorted(normalized_tokens.values())


def parse_catalog_ids(text: str) -> list[str]:
    return parse_catalog_token_matches(
        re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\(\s*"([^"]+)"\s*,', text),
        source=f"{display_path(navigation_catalog_path)} tab IDs",
        allow_duplicate_ids=True,
    )


def parse_workspace_action_target_ids(text: str) -> list[str]:
    return parse_catalog_token_matches(
        re.findall(
            r'\b[A-Za-z_][A-Za-z0-9_]*\(\s*"[^"]+"\s*,\s*"[^"]+"\s*,\s*"[^"]+"\s*,\s*[^,]+,\s*"([^"]+)"',
            text,
        ),
        source=f"{display_path(action_catalog_path)} workspace action target IDs",
        allow_duplicate_ids=True,
    )


def parse_static_string_hash_set_ids(text: str, *, set_name: str, source: str) -> list[str]:
    match = re.search(
        rf'{re.escape(set_name)}\s*=\s*new\(StringComparer\.Ordinal\)\s*\{{(?P<body>.*?)\n\s*\}};',
        text,
        re.DOTALL,
    )
    if match is None:
        raise ValueError(f"{source} is missing string hash set {set_name}")
    return parse_catalog_token_matches(
        re.findall(r'"([A-Za-z0-9_]+)"', match.group("body")),
        source=f"{source} {set_name}",
        allow_duplicate_ids=False,
    )


def extract_switch_expression_body(text: str, *, variable_name: str) -> str:
    return extract_csharp_switch_expression_body(
        text,
        variable_name=variable_name,
        source=display_path(desktop_dialog_factory_path),
    )


def parse_switch_case_ids(text: str, *, variable_name: str) -> list[str]:
    switch_body = extract_switch_expression_body(text, variable_name=variable_name)
    return parse_catalog_token_matches(
        re.findall(r'"([A-Za-z0-9_]+)"\s*=>', switch_body),
        source=f"{display_path(desktop_dialog_factory_path)} {variable_name} switch IDs",
        allow_duplicate_ids=False,
    )


def parse_desktop_dialog_control_ids(text: str, *, ignored_command_ids: Sequence[str]) -> list[str]:
    ignored_command_id_set = set(ignored_command_ids)
    command_ids = [
        command_id
        for command_id in parse_switch_case_ids(text, variable_name="commandId")
        if command_id not in ignored_command_id_set
    ]
    return parse_catalog_token_matches(
        command_ids + parse_switch_case_ids(text, variable_name="controlId"),
        source=f"{display_path(desktop_dialog_factory_path)} desktop dialog control IDs",
        allow_duplicate_ids=False,
    )


def partition_coverage(legacy_ids: Sequence[str], catalog_ids: Sequence[str]) -> tuple[list[str], list[str], list[str]]:
    legacy_set = set(legacy_ids)
    catalog_set = set(catalog_ids)
    covered = sorted(legacy_set & catalog_set)
    missing = sorted(legacy_set - catalog_set)
    catalog_only = sorted(catalog_set - legacy_set)
    return covered, missing, catalog_only


def fail_on_unacknowledged_catalog_only(
    *,
    surface_label: str,
    catalog_only_ids: Sequence[str],
    acknowledged_ids: Sequence[str],
    source: str,
) -> None:
    catalog_only_set = set(catalog_only_ids)
    acknowledged_set = set(acknowledged_ids)
    unacknowledged = sorted(catalog_only_set - acknowledged_set)
    stale = sorted(acknowledged_set - catalog_only_set)
    if unacknowledged:
        raise ValueError(
            f"{source} is missing required acknowledged catalog-only {surface_label} ids "
            f"({', '.join(unacknowledged)})"
        )
    if stale:
        raise ValueError(
            f"{source} acknowledged catalog-only {surface_label} ids that are no longer catalog-only "
            f"({', '.join(stale)})"
        )


def fail_on_missing_required_legacy_ids(
    *,
    surface_label: str,
    missing_ids: Sequence[str],
    source: str,
) -> None:
    if missing_ids:
        raise ValueError(
            f"{source} is missing required legacy {surface_label} ids "
            f"({', '.join(missing_ids)})"
        )


def fail_on_missing_milestone2_baseline_ids(
    *,
    surface_label: str,
    baseline_ids: Sequence[str],
    present_ids: Sequence[str],
    source: str,
) -> None:
    missing = sorted(set(baseline_ids).difference(set(present_ids)))
    if missing:
        raise ValueError(
            f"{source} is missing required milestone-2 baseline {surface_label} ids "
            f"({', '.join(missing)})"
        )


def write_summary_row(kind: str, legacy_ids: Sequence[str], covered: Sequence[str], missing: Sequence[str], catalog_only: Sequence[str]) -> str:
    return f"| {kind} | {len(legacy_ids)} | {len(covered)} | {len(missing)} | {len(catalog_only)} |"


def write_coverage_table(
    title: str,
    covered: Sequence[str],
    missing: Sequence[str],
    catalog_only: Sequence[str],
    *,
    catalog_only_status: str = "catalog_only_acknowledged",
) -> list[str]:
    lines: list[str] = [f"## {title}", "", "| ID | Status |", "| --- | --- |"]
    for value in covered:
        lines.append(f"| `{value}` | covered |")
    for value in missing:
        lines.append(f"| `{value}` | missing_in_catalog |")
    for value in catalog_only:
        lines.append(f"| `{value}` | {catalog_only_status} |")
    if not (covered or missing or catalog_only):
        lines.append("| _(none)_ | _(none)_ |")
    lines.append("")
    return lines


parity_oracle = json.loads(read_text(parity_oracle_path))
if not isinstance(parity_oracle, dict):
    raise ValueError(f"{display_path(parity_oracle_path)} must be a JSON object")
navigation_catalog_text = read_text(navigation_catalog_path)
action_catalog_text = read_text(action_catalog_path)
desktop_dialog_factory_text = read_text(desktop_dialog_factory_path)
overview_command_policy_text = read_text(overview_command_policy_path)

legacy_tabs = parse_required_token_list(
    parity_oracle,
    "tabs",
    source=display_path(parity_oracle_path),
)
legacy_actions = parse_required_token_list(
    parity_oracle,
    "workspaceActions",
    source=display_path(parity_oracle_path),
)
acknowledged_catalog_only_tabs = parse_required_token_list(
    parity_oracle,
    "acknowledgedCatalogOnlyTabs",
    source=display_path(parity_oracle_path),
)
acknowledged_catalog_only_actions = parse_required_token_list(
    parity_oracle,
    "acknowledgedCatalogOnlyWorkspaceActions",
    source=display_path(parity_oracle_path),
)
acknowledged_dialog_factory_only_desktop_controls = parse_required_token_list(
    parity_oracle,
    "acknowledgedDialogFactoryOnlyDesktopControls",
    source=display_path(parity_oracle_path),
)
legacy_desktop_controls = parse_required_token_list(
    parity_oracle,
    "desktopControls",
    source=display_path(parity_oracle_path),
)
import_hint_command_ids = parse_static_string_hash_set_ids(
    overview_command_policy_text,
    set_name="ImportHintCommandIds",
    source=display_path(overview_command_policy_path),
)

required_milestone2_tabs = {
    "tab-adept",
    "tab-armor",
    "tab-attributes",
    "tab-combat",
    "tab-info",
    "tab-skills",
    "tab-qualities",
    "tab-improvements",
    "tab-lifestyle",
    "tab-magician",
    "tab-technomancer",
    "tab-gear",
    "tab-cyberware",
    "tab-vehicles",
    "tab-contacts",
    "tab-notes",
    "tab-calendar",
}
required_milestone2_actions = {
    "aiprograms",
    "armorlocations",
    "armormods",
    "armors",
    "arts",
    "attributedetails",
    "build",
    "progress",
    "summary",
    "metadata",
    "profile",
    "attributes",
    "skills",
    "qualities",
    "improvements",
    "awakening",
    "critterpowers",
    "spells",
    "complexforms",
    "drugs",
    "foci",
    "gear",
    "gearlocations",
    "inventory",
    "limitmodifiers",
    "lifestyles",
    "martialarts",
    "mentorspirits",
    "metamagics",
    "initiationgrades",
    "powers",
    "cyberwares",
    "customdatadirectorynames",
    "movement",
    "vehicles",
    "vehiclelocations",
    "vehiclemods",
    "weapons",
    "weaponlocations",
    "weaponaccessories",
    "spirits",
    "contacts",
    "calendar",
    "expenses",
    "sources",
    "rules",
    "validate",
}
required_milestone2_desktop_controls = {
    "combat_add_armor",
    "combat_add_weapon",
    "combat_damage_track",
    "combat_reload",
    "contact_add",
    "contact_connection",
    "contact_edit",
    "contact_remove",
    "create_entry",
    "edit_entry",
    "delete_entry",
    "gear_add",
    "gear_delete",
    "gear_edit",
    "gear_mount",
    "gear_source",
    "magic_add",
    "magic_bind",
    "magic_delete",
    "magic_source",
    "move_down",
    "move_up",
    "show_source",
    "skill_add",
    "skill_group",
    "skill_remove",
    "skill_specialize",
    "toggle_free_paid",
    "open_notes",
}
required_milestone2_dialog_factory_controls = {
    "adept_power_add",
    "complex_form_add",
    "critter_power_add",
    "cyberware_add",
    "cyberware_delete",
    "cyberware_edit",
    "drug_add",
    "drug_delete",
    "initiation_add",
    "matrix_program_add",
    "quality_add",
    "quality_delete",
    "spell_add",
    "spirit_add",
    "vehicle_add",
    "vehicle_delete",
    "vehicle_edit",
    "vehicle_mod_add",
}
fail_on_missing_milestone2_baseline_ids(
    surface_label="tab",
    baseline_ids=required_milestone2_tabs,
    present_ids=legacy_tabs,
    source=display_path(parity_oracle_path),
)
fail_on_missing_milestone2_baseline_ids(
    surface_label="workspace action",
    baseline_ids=required_milestone2_actions,
    present_ids=legacy_actions,
    source=display_path(parity_oracle_path),
)
fail_on_missing_milestone2_baseline_ids(
    surface_label="desktop control",
    baseline_ids=required_milestone2_desktop_controls,
    present_ids=legacy_desktop_controls,
    source=display_path(parity_oracle_path),
)
fail_on_missing_milestone2_baseline_ids(
    surface_label="dialog-factory-only desktop control",
    baseline_ids=required_milestone2_dialog_factory_controls,
    present_ids=acknowledged_dialog_factory_only_desktop_controls,
    source=display_path(parity_oracle_path),
)

catalog_tabs = parse_catalog_ids(navigation_catalog_text)
catalog_actions = parse_workspace_action_target_ids(action_catalog_text)
catalog_desktop_controls = parse_desktop_dialog_control_ids(
    desktop_dialog_factory_text,
    ignored_command_ids=import_hint_command_ids,
)

covered_tabs, missing_tabs, catalog_only_tabs = partition_coverage(legacy_tabs, catalog_tabs)
covered_actions, missing_actions, catalog_only_actions = partition_coverage(legacy_actions, catalog_actions)
covered_desktop_controls, missing_desktop_controls, catalog_only_desktop_controls = partition_coverage(
    legacy_desktop_controls,
    catalog_desktop_controls,
)
fail_on_unacknowledged_catalog_only(
    surface_label="tab",
    catalog_only_ids=catalog_only_tabs,
    acknowledged_ids=acknowledged_catalog_only_tabs,
    source=display_path(parity_oracle_path),
)
fail_on_unacknowledged_catalog_only(
    surface_label="workspace action",
    catalog_only_ids=catalog_only_actions,
    acknowledged_ids=acknowledged_catalog_only_actions,
    source=display_path(parity_oracle_path),
)
fail_on_unacknowledged_catalog_only(
    surface_label="dialog-factory-only desktop control",
    catalog_only_ids=catalog_only_desktop_controls,
    acknowledged_ids=acknowledged_dialog_factory_only_desktop_controls,
    source=display_path(parity_oracle_path),
)
fail_on_missing_required_legacy_ids(
    surface_label="tab",
    missing_ids=missing_tabs,
    source=display_path(parity_oracle_path),
)
fail_on_missing_required_legacy_ids(
    surface_label="workspace action",
    missing_ids=missing_actions,
    source=display_path(parity_oracle_path),
)
if missing_desktop_controls:
    raise ValueError(
        f"{display_path(parity_oracle_path)} is missing required legacy desktop control ids in "
        f"{display_path(desktop_dialog_factory_path)} ({', '.join(missing_desktop_controls)})"
    )

output_lines: list[str] = [
    "# UI Parity Checklist",
    "",
    "Generated automatically from the parity oracle and current contracts catalogs.",
    "",
    "- Regenerate command: `RUNBOOK_MODE=parity-checklist bash scripts/runbook.sh`",
    f"- Parity oracle source: `{display_path(parity_oracle_path)}`",
    f"- Tab catalog source: `{display_path(navigation_catalog_path)}`",
    f"- Action catalog source: `{display_path(action_catalog_path)}`",
    f"- Desktop dialog source: `{display_path(desktop_dialog_factory_path)}`",
    f"- Overview command policy source: `{display_path(overview_command_policy_path)}`",
    "- Workspace Actions coverage compares parity-oracle action IDs to action `TargetId` values.",
    "- Catalog-only IDs must be acknowledged explicitly in `docs/PARITY_ORACLE.json`.",
    "- Desktop Controls coverage compares parity-oracle control IDs to dialog control IDs in `DesktopDialogFactory`, excluding import-hint command routes declared in `OverviewCommandPolicy`.",
    "- Dialog-factory-only desktop controls must be acknowledged explicitly in `docs/PARITY_ORACLE.json`.",
    "",
    "## Summary",
    "",
    "| Surface | Legacy IDs | Covered | Missing In Catalog | Catalog Only |",
    "| --- | ---: | ---: | ---: | ---: |",
    write_summary_row("Tabs", legacy_tabs, covered_tabs, missing_tabs, catalog_only_tabs),
    write_summary_row("Workspace Actions", legacy_actions, covered_actions, missing_actions, catalog_only_actions),
    write_summary_row(
        "Desktop Controls",
        legacy_desktop_controls,
        covered_desktop_controls,
        missing_desktop_controls,
        catalog_only_desktop_controls,
    ),
    "",
]

output_lines.extend(write_coverage_table("Tabs Coverage", covered_tabs, missing_tabs, catalog_only_tabs))
output_lines.extend(write_coverage_table("Workspace Actions Coverage", covered_actions, missing_actions, catalog_only_actions))
output_lines.extend(
    write_coverage_table(
        "Desktop Controls Coverage",
        covered_desktop_controls,
        missing_desktop_controls,
        catalog_only_desktop_controls,
        catalog_only_status="present_in_dialog_factory_acknowledged",
    )
)

output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text("\n".join(output_lines).rstrip() + "\n", encoding="utf-8")

print(f"Wrote parity checklist to {output_path}")
print(
    "Summary: "
    f"tabs covered={len(covered_tabs)}/{len(legacy_tabs)}, "
    f"actions covered={len(covered_actions)}/{len(legacy_actions)}, "
    f"desktop-controls covered={len(covered_desktop_controls)}/{len(legacy_desktop_controls)}"
)
PY
