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

parity_oracle_path = repo_root / "docs" / "PARITY_ORACLE.json"

default_core_engine_root = repo_root.parent / "chummer-core-engine"
core_engine_root = pathlib.Path(os.environ.get("CHUMMER_CORE_ENGINE_ROOT", str(default_core_engine_root)))
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
    return sorted(tokens)


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


def write_summary_row(kind: str, legacy_ids: Sequence[str], covered: Sequence[str], missing: Sequence[str], catalog_only: Sequence[str]) -> str:
    return f"| {kind} | {len(legacy_ids)} | {len(covered)} | {len(missing)} | {len(catalog_only)} |"


def write_coverage_table(title: str, covered: Sequence[str], missing: Sequence[str], catalog_only: Sequence[str]) -> list[str]:
    lines: list[str] = [f"## {title}", "", "| ID | Status |", "| --- | --- |"]
    for value in covered:
        lines.append(f"| `{value}` | covered |")
    for value in missing:
        lines.append(f"| `{value}` | missing_in_catalog |")
    for value in catalog_only:
        lines.append(f"| `{value}` | catalog_only_acknowledged |")
    if not (covered or missing or catalog_only):
        lines.append("| _(none)_ | _(none)_ |")
    lines.append("")
    return lines


parity_oracle = json.loads(read_text(parity_oracle_path))
if not isinstance(parity_oracle, dict):
    raise ValueError(f"{display_path(parity_oracle_path)} must be a JSON object")
navigation_catalog_text = read_text(navigation_catalog_path)
action_catalog_text = read_text(action_catalog_path)

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
catalog_tabs = parse_catalog_ids(navigation_catalog_text)
catalog_actions = parse_workspace_action_target_ids(action_catalog_text)

covered_tabs, missing_tabs, catalog_only_tabs = partition_coverage(legacy_tabs, catalog_tabs)
covered_actions, missing_actions, catalog_only_actions = partition_coverage(legacy_actions, catalog_actions)
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

output_lines: list[str] = [
    "# UI Parity Checklist",
    "",
    "Generated automatically from the parity oracle and current contracts catalogs.",
    "",
    "- Regenerate command: `RUNBOOK_MODE=parity-checklist bash scripts/runbook.sh`",
    f"- Parity oracle source: `{display_path(parity_oracle_path)}`",
    f"- Tab catalog source: `{display_path(navigation_catalog_path)}`",
    f"- Action catalog source: `{display_path(action_catalog_path)}`",
    "- Workspace Actions coverage compares parity-oracle action IDs to action `TargetId` values.",
    "- Catalog-only IDs must be acknowledged explicitly in `docs/PARITY_ORACLE.json`.",
    "- Legacy desktop control parity is enforced by dialog-template compliance tests, not by a shared control catalog.",
    "",
    "## Summary",
    "",
    "| Surface | Legacy IDs | Covered | Missing In Catalog | Catalog Only |",
    "| --- | ---: | ---: | ---: | ---: |",
    write_summary_row("Tabs", legacy_tabs, covered_tabs, missing_tabs, catalog_only_tabs),
    write_summary_row("Workspace Actions", legacy_actions, covered_actions, missing_actions, catalog_only_actions),
    "",
]

output_lines.extend(write_coverage_table("Tabs Coverage", covered_tabs, missing_tabs, catalog_only_tabs))
output_lines.extend(write_coverage_table("Workspace Actions Coverage", covered_actions, missing_actions, catalog_only_actions))

output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text("\n".join(output_lines).rstrip() + "\n", encoding="utf-8")

print(f"Wrote parity checklist to {output_path}")
print(
    "Summary: "
    f"tabs covered={len(covered_tabs)}/{len(legacy_tabs)}, "
    f"actions covered={len(covered_actions)}/{len(legacy_actions)}"
)
PY
