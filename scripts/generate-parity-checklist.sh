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
from typing import Sequence


repo_root = pathlib.Path(sys.argv[1])
output_path = pathlib.Path(sys.argv[2])

parity_oracle_path = repo_root / "docs" / "PARITY_ORACLE.json"
navigation_catalog_path = repo_root / "Chummer.Rulesets.Hosting" / "Presentation" / "NavigationTabCatalog.cs"
action_catalog_path = repo_root / "Chummer.Rulesets.Hosting" / "Presentation" / "WorkspaceSurfaceActionCatalog.cs"


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_oracle_ids(oracle: dict[str, list[str]], key: str) -> list[str]:
    return sorted(set(oracle[key]))


def parse_catalog_ids(text: str) -> list[str]:
    return sorted(set(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\(\s*"([^"]+)"\s*,', text)))


def parse_workspace_action_target_ids(text: str) -> list[str]:
    return sorted(
        set(
            re.findall(
                r'\b[A-Za-z_][A-Za-z0-9_]*\(\s*"[^"]+"\s*,\s*"[^"]+"\s*,\s*"[^"]+"\s*,\s*[^,]+,\s*"([^"]+)"',
                text,
            )
        )
    )


def partition_coverage(legacy_ids: Sequence[str], catalog_ids: Sequence[str]) -> tuple[list[str], list[str], list[str]]:
    legacy_set = set(legacy_ids)
    catalog_set = set(catalog_ids)
    covered = sorted(legacy_set & catalog_set)
    missing = sorted(legacy_set - catalog_set)
    catalog_only = sorted(catalog_set - legacy_set)
    return covered, missing, catalog_only


def write_summary_row(kind: str, legacy_ids: Sequence[str], covered: Sequence[str], missing: Sequence[str], catalog_only: Sequence[str]) -> str:
    return f"| {kind} | {len(legacy_ids)} | {len(covered)} | {len(missing)} | {len(catalog_only)} |"


def write_coverage_table(title: str, covered: Sequence[str], missing: Sequence[str], catalog_only: Sequence[str]) -> list[str]:
    lines: list[str] = [f"## {title}", "", "| ID | Status |", "| --- | --- |"]
    for value in covered:
        lines.append(f"| `{value}` | covered |")
    for value in missing:
        lines.append(f"| `{value}` | missing_in_catalog |")
    for value in catalog_only:
        lines.append(f"| `{value}` | catalog_only |")
    if not (covered or missing or catalog_only):
        lines.append("| _(none)_ | _(none)_ |")
    lines.append("")
    return lines


parity_oracle = json.loads(read_text(parity_oracle_path))
navigation_catalog_text = read_text(navigation_catalog_path)
action_catalog_text = read_text(action_catalog_path)

legacy_tabs = parse_oracle_ids(parity_oracle, "tabs")
legacy_actions = parse_oracle_ids(parity_oracle, "workspaceActions")
catalog_tabs = parse_catalog_ids(navigation_catalog_text)
catalog_actions = parse_workspace_action_target_ids(action_catalog_text)

covered_tabs, missing_tabs, catalog_only_tabs = partition_coverage(legacy_tabs, catalog_tabs)
covered_actions, missing_actions, catalog_only_actions = partition_coverage(legacy_actions, catalog_actions)

output_lines: list[str] = [
    "# UI Parity Checklist",
    "",
    "Generated automatically from the parity oracle and current contracts catalogs.",
    "",
    "- Regenerate command: `RUNBOOK_MODE=parity-checklist bash scripts/runbook.sh`",
    f"- Parity oracle source: `{parity_oracle_path.relative_to(repo_root)}`",
    f"- Tab catalog source: `{navigation_catalog_path.relative_to(repo_root)}`",
    f"- Action catalog source: `{action_catalog_path.relative_to(repo_root)}`",
    "- Workspace Actions coverage compares parity-oracle action IDs to action `TargetId` values.",
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
