#!/usr/bin/env python3
from __future__ import annotations

from absolute_completion_common import completion_path, now_iso, read_yaml, write_json, write_text


MATRIX_PATH = completion_path("ENGAGEMENT_DRIVERS_AUDIT_MATRIX.yaml")
BACKLOG_PATH = completion_path("ENGAGEMENT_BACKLOG.yaml")
REQUIRED_SURFACES = {
    "homepage",
    "downloads",
    "account",
    "participation",
    "feedback",
    "roadmap",
    "changelog",
    "packages",
    "karma_forge",
    "mobile_pwa",
    "artifacts_media",
    "support",
    "ea_fleet_operator_loop",
}
REQUIRED_KEYS = {"surface", "user_job", "motivation_levers", "owner_repo", "design_owner", "verification"}


def main() -> int:
    failures: list[str] = []
    matrix = read_yaml(MATRIX_PATH)
    backlog = read_yaml(BACKLOG_PATH)
    surfaces = matrix.get("surfaces", []) if isinstance(matrix, dict) else []
    backlog_items = backlog.get("items", []) if isinstance(backlog, dict) else []

    seen_surfaces: set[str] = set()
    backlog_surfaces = {
        str(item.get("surface"))
        for item in backlog_items
        if isinstance(item, dict) and item.get("surface")
    }

    for entry in surfaces:
        if not isinstance(entry, dict):
            failures.append("matrix surface entry is not a mapping")
            continue

        surface = str(entry.get("surface") or "")
        if not surface:
            failures.append("matrix surface entry missing surface id")
            continue

        if surface in seen_surfaces:
            failures.append(f"duplicate surface: {surface}")
        seen_surfaces.add(surface)

        missing_keys = sorted(REQUIRED_KEYS - entry.keys())
        if missing_keys:
            failures.append(f"{surface} missing keys: {', '.join(missing_keys)}")

        motivation_levers = entry.get("motivation_levers")
        if not isinstance(motivation_levers, list) or len(motivation_levers) < 3:
            failures.append(f"{surface} motivation_levers must be a list with at least 3 items")

        verification = entry.get("verification")
        if not isinstance(verification, list) or not verification:
            failures.append(f"{surface} verification must be a non-empty list")

        if surface not in backlog_surfaces:
            failures.append(f"{surface} missing backlog recommendation")

    missing_surfaces = sorted(REQUIRED_SURFACES - seen_surfaces)
    extra_surfaces = sorted(seen_surfaces - REQUIRED_SURFACES)
    failures.extend(f"missing surface: {surface}" for surface in missing_surfaces)
    failures.extend(f"unexpected surface: {surface}" for surface in extra_surfaces)

    payload = {
        "contract_name": "chummer.engagement_drivers_matrix_validate",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "path": str(MATRIX_PATH),
        "backlog_path": str(BACKLOG_PATH),
        "surface_count": len(seen_surfaces),
        "required_surface_count": len(REQUIRED_SURFACES),
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("ENGAGEMENT_DRIVERS_MATRIX_VALIDATE.generated.json"), payload)

    lines = [
        "# Engagement drivers matrix validation",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Status: `{payload['status']}`",
        f"- Surface coverage: {payload['surface_count']} / {payload['required_surface_count']}",
        f"- Failure count: {payload['failure_count']}",
    ]
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.extend(["", "The V5 engagement drivers matrix covers every required surface and each surface has a matching backlog recommendation."])

    write_text(completion_path("ENGAGEMENT_DRIVERS_MATRIX_VALIDATE.md"), "\n".join(lines))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
