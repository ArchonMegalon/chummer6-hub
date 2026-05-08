#!/usr/bin/env python3
from __future__ import annotations

import html
import os
import sys
from urllib.parse import unquote
from pathlib import Path


PACKAGE_ID = "next90-m105-hub-workspace-continuity"
TITLE = "Emit provenance and conflict receipts for workspace restore and continuity"
TASK = "Make roaming workspace, entitlement replication, stale state, and conflict posture explicit and recoverable."
FRONTIER_ID = "4623636482"
MILESTONE_ID = "105"
COMPLETION_ACTION = "verify_closed_package_only"
DO_NOT_REOPEN_REASON = (
    "M105 chummer6-hub workspace continuity is complete; future shards must verify the workspace "
    "restore receipt, registry row, queue row, and design-queue row instead of reopening the "
    "workspace restore and entitlement conflict receipt package."
)
ALLOWED_PATHS = [
    "Chummer.Run.Api",
    "scripts",
    "tests",
]
OWNED_SURFACES = [
    "workspace_restore:provenance",
    "entitlement_sync:conflict_receipts",
]
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "TASK_LOCAL_TELEMETRY.generated.json",
    "ACTIVE_RUN_HANDOFF",
    "ACTIVE_RUN_HANDOFF.generated.md",
    "task-local telemetry",
    "shard runtime handoff",
    "Shard Runtime Handoff",
    "Recent stderr tail",
    "Prompt path:",
    "Selected account:",
    "Selected model:",
    "Open milestone ids:",
    "active_runs_count",
    "successor-wave telemetry",
    "eta_human",
    "eta: 4.8d-1.7w",
    "eta 4.8d-1.7w",
    "frontier_briefs",
    "queue_item",
    "slice_summary",
    "scope_label",
    "successor frontier detail",
    "successor frontier ids",
    "assigned successor queue package",
    "current steering focus",
    "profile focus",
    "owner focus",
    "text focus",
    "focus_profiles",
    "focus_owners",
    "focus_texts",
    "eta: 5.6d-2w",
    "eta 5.6d-2w",
    "execution rules inside this run",
    "required order",
    "first_commands",
    "polling_disabled",
    "polling disabled",
    "runtime_handoff_path",
    "status_query_supported",
    "status query",
    "remaining_in_progress_milestones",
    "remaining_not_started_milestones",
    "remaining_open_milestones",
    "successor_queue_path",
    "successor_registry_path",
    "remaining milestones",
    "remaining queue items",
    "critical path",
    "active-run helper",
    "active-run helper command",
    "active-run helper commands",
    "operator telemetry",
    "operator/OODA loop owns telemetry",
    "operator/OODA",
    "operator OODA",
    "supervisor status",
    "supervisor eta",
    "status helper",
    "eta helper",
    "design_supervisor_ooda",
    "ooda_design_supervisor.py",
    "run_ooda_design_supervisor_until_quiet",
    "/var/lib/codex-fleet",
]


QUEUE_PATHS = [
    Path(
        os.environ.get(
            "CHUMMER_WORKSPACE_RESTORE_QUEUE_IDENTITY_FLEET_QUEUE",
            "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
        )
    ),
    Path(
        os.environ.get(
            "CHUMMER_WORKSPACE_RESTORE_QUEUE_IDENTITY_DESIGN_QUEUE",
            "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
        )
    ),
]


def read_text(path: Path, missing: list[str]) -> str:
    if not path.is_file():
        missing.append(f"missing queue staging file: {path}")
        return ""
    return path.read_text(encoding="utf-8")


def extract_item_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    block_start: int | None = None

    for index, line in enumerate(lines):
        if not line.lstrip().startswith("- title:"):
            continue
        if block_start is not None:
            blocks.append("\n".join(lines[block_start:index]))
        block_start = index

    if block_start is not None:
        blocks.append("\n".join(lines[block_start:]))

    return blocks


def extract_scalar_occurrences(block: str) -> dict[str, list[str]]:
    lines = block.splitlines()
    scalars: dict[str, list[str]] = {}
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if not stripped or stripped.startswith("- ") or ":" not in stripped:
            index += 1
            continue

        key, value = stripped.split(":", 1)
        if not key.replace("_", "").isalnum():
            index += 1
            continue

        value = value.strip()
        parts = [value] if value else []
        next_index = index + 1
        while next_index < len(lines):
            next_line = lines[next_index]
            next_stripped = next_line.lstrip()
            next_indent = len(next_line) - len(next_stripped)
            if not next_stripped:
                next_index += 1
                continue
            if next_indent <= indent or next_stripped.startswith("- "):
                break
            parts.append(next_stripped)
            next_index += 1

        scalars.setdefault(key, []).append(" ".join(part for part in parts if part).strip())
        index = next_index

    return scalars


def block_title(block: str) -> str:
    for line in block.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("- title:"):
            return stripped.removeprefix("- title:").strip()
    return ""


def block_contains_scalar(block: str, key: str, value: str) -> bool:
    return value in extract_scalar_occurrences(block).get(key, [])


def extract_scalar_list(block: str, key: str) -> list[str]:
    lines = block.splitlines()
    section_line_index = next(
        (index for index, line in enumerate(lines) if line.lstrip() == f"{key}:"),
        None,
    )
    if section_line_index is None:
        return []

    anchor_line = lines[section_line_index]
    anchor_indent = len(anchor_line) - len(anchor_line.lstrip())
    values: list[str] = []
    list_indent: int | None = None
    current_value: str | None = None
    for line in lines[section_line_index + 1 :]:
        stripped = line.lstrip()
        if not stripped:
            continue

        indent = len(line) - len(stripped)
        if stripped.startswith("- "):
            if list_indent is None:
                list_indent = indent
            elif indent < list_indent:
                break

            if indent == list_indent:
                current_value = stripped[2:].strip()
                values.append(current_value)
                continue

        if list_indent is None:
            if indent <= anchor_indent:
                break
            continue

        if indent > list_indent and current_value is not None:
            current_value = f"{current_value} {stripped}".strip()
            values[-1] = current_value
            continue

        if indent <= anchor_indent or indent < list_indent:
            break

    return values


def decode_hex_escapes(text: str) -> str:
    def replace_match(match: str) -> str:
        try:
            return chr(int(match[2:], 16))
        except ValueError:
            return match

    decoded: list[str] = []
    index = 0
    while index < len(text):
        if (
            index + 3 < len(text)
            and text[index] == "\\"
            and text[index + 1] in {"x", "X"}
            and all(character in "0123456789abcdefABCDEF" for character in text[index + 2 : index + 4])
        ):
            decoded.append(replace_match(text[index : index + 4]))
            index += 4
            continue
        decoded.append(text[index])
        index += 1
    return "".join(decoded)


def forbidden_scan_texts(block: str) -> list[str]:
    html_decoded = html.unescape(block)
    url_decoded = unquote(block)
    hex_decoded = decode_hex_escapes(block)
    return [block, html_decoded, url_decoded, hex_decoded]


def reject_forbidden_markers(path: Path, block: str, missing: list[str]) -> None:
    normalized_blocks = [text.casefold() for text in forbidden_scan_texts(block)]
    for marker in FORBIDDEN_PROOF_MARKERS:
        marker_text = marker.casefold()
        if any(marker_text in normalized_block for normalized_block in normalized_blocks):
            missing.append(f"{path}: forbidden active-run proof marker: {marker}")


def check_queue(path: Path, missing: list[str]) -> None:
    text = read_text(path, missing)
    if not text:
        return

    blocks = extract_item_blocks(text)
    package_blocks = [block for block in blocks if block_contains_scalar(block, "package_id", PACKAGE_ID)]
    title_blocks = [block for block in blocks if block_title(block) == TITLE]
    frontier_blocks = [block for block in blocks if block_contains_scalar(block, "frontier_id", FRONTIER_ID)]
    owned_surface_blocks = [
        block
        for block in blocks
        if all(surface in extract_scalar_list(block, "owned_surfaces") for surface in OWNED_SURFACES)
    ]

    if len(package_blocks) != 1:
        missing.append(f"{path}: expected exactly one package_id {PACKAGE_ID}; found {len(package_blocks)}")
    if len(title_blocks) != 1:
        missing.append(f"{path}: expected exactly one title {TITLE!r}; found {len(title_blocks)}")
    if len(frontier_blocks) != 1:
        missing.append(f"{path}: expected exactly one frontier_id {FRONTIER_ID}; found {len(frontier_blocks)}")
    if len(owned_surface_blocks) != 1:
        missing.append(f"{path}: expected exactly one row owning surfaces {OWNED_SURFACES!r}; found {len(owned_surface_blocks)}")

    if not package_blocks:
        return

    package_block = package_blocks[0]
    reject_forbidden_markers(path, package_block, missing)
    if title_blocks and title_blocks[0] != package_block:
        missing.append(f"{path}: title row for {TITLE!r} must be the {PACKAGE_ID} package row")
    if frontier_blocks and frontier_blocks[0] != package_block:
        missing.append(f"{path}: frontier_id {FRONTIER_ID} must be pinned to the {PACKAGE_ID} package row")
    if owned_surface_blocks and owned_surface_blocks[0] != package_block:
        missing.append(f"{path}: owned surfaces {OWNED_SURFACES!r} must be pinned to the {PACKAGE_ID} package row")

    required_scalars = {
        "task": TASK,
        "frontier_id": FRONTIER_ID,
        "milestone_id": MILESTONE_ID,
        "wave": "W8",
        "repo": "chummer6-hub",
        "status": "complete",
        "completion_action": COMPLETION_ACTION,
        "do_not_reopen_reason": DO_NOT_REOPEN_REASON,
        "landed_commit": "4d4b3856",
    }
    for key, value in required_scalars.items():
        if not block_contains_scalar(package_block, key, value):
            missing.append(f"{path}: {PACKAGE_ID}.{key} must be {value!r}")

    allowed_paths = extract_scalar_list(package_block, "allowed_paths")
    if allowed_paths != ALLOWED_PATHS:
        missing.append(f"{path}: {PACKAGE_ID}.allowed_paths must be exactly {ALLOWED_PATHS!r}")

    owned_surfaces = extract_scalar_list(package_block, "owned_surfaces")
    if owned_surfaces != OWNED_SURFACES:
        missing.append(f"{path}: {PACKAGE_ID}.owned_surfaces must be exactly {OWNED_SURFACES!r}")


def main() -> int:
    missing: list[str] = []
    for path in QUEUE_PATHS:
        check_queue(path, missing)

    if len(QUEUE_PATHS) == 2:
        fleet_text = read_text(QUEUE_PATHS[0], missing)
        design_text = read_text(QUEUE_PATHS[1], missing)
        if fleet_text and design_text:
            fleet_block = next(
                (
                    block
                    for block in extract_item_blocks(fleet_text)
                    if block_contains_scalar(block, "package_id", PACKAGE_ID)
                ),
                "",
            )
            design_block = next(
                (
                    block
                    for block in extract_item_blocks(design_text)
                    if block_contains_scalar(block, "package_id", PACKAGE_ID)
                ),
                "",
            )
            if fleet_block and design_block and fleet_block != design_block:
                missing.append(f"{QUEUE_PATHS[0]}:{PACKAGE_ID} must match {QUEUE_PATHS[1]}:{PACKAGE_ID}")

    if missing:
        for item in missing:
            print(f"workspace_restore_queue_identity_missing: {item}", file=sys.stderr)
        return 1

    print("workspace restore queue identity proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
