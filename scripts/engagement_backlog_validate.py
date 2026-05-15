#!/usr/bin/env python3
from __future__ import annotations

from absolute_completion_common import completion_path, now_iso, read_yaml, write_json, write_text


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
REQUIRED_KEYS = {"id", "surface", "owner_repo", "route", "recommendation", "privacy_boundary", "anti_abuse_rule", "verification"}


def main() -> int:
    failures: list[str] = []
    backlog = read_yaml(BACKLOG_PATH)
    items = backlog.get("items", []) if isinstance(backlog, dict) else []
    seen_surfaces = {item.get("surface") for item in items if isinstance(item, dict)}

    for surface in sorted(REQUIRED_SURFACES):
        if surface not in seen_surfaces:
            failures.append(f"missing surface: {surface}")

    for item in items:
        if not isinstance(item, dict):
            failures.append("backlog item is not a mapping")
            continue
        missing_keys = sorted(REQUIRED_KEYS - item.keys())
        if missing_keys:
            failures.append(f"{item.get('id', '<missing-id>')} missing keys: {', '.join(missing_keys)}")
        verification = item.get("verification")
        if not isinstance(verification, list) or not verification:
            failures.append(f"{item.get('id', '<missing-id>')} verification must be a non-empty list")

    payload = {
        "contract_name": "chummer.engagement_backlog_validate",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "path": str(BACKLOG_PATH),
        "item_count": len(items),
        "surface_count": len(seen_surfaces),
        "required_surface_count": len(REQUIRED_SURFACES),
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("ENGAGEMENT_BACKLOG_VALIDATE.generated.json"), payload)

    lines = [
        "# Engagement backlog validation",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Status: `{payload['status']}`",
        f"- Item count: {payload['item_count']}",
        f"- Surface coverage: {payload['surface_count']} / {payload['required_surface_count']}",
        f"- Failure count: {payload['failure_count']}",
    ]
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.extend(["", "The engagement backlog covers every required surface with owner, route, privacy boundary, anti-abuse rule, and verification notes."])

    write_text(completion_path("ENGAGEMENT_BACKLOG_VALIDATE.md"), "\n".join(lines))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
