#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from absolute_completion_common import RUN_SERVICES_ROOT, WORKSPACE_ROOT, completion_path, now_iso, write_text


DESIGN_ROOT = WORKSPACE_ROOT / "chummer-design" / "products" / "chummer"
COMPLETION_ROOT = WORKSPACE_ROOT / "_completion" / "chummer6_absolute_completion"
REQUIRED_DOCS = [
    "ABSOLUTE_PRODUCT_COMPLETION_PLAN.md",
    "USER_WISHES_AND_MISSED_POTENTIAL.md",
    "FEEDBACK_TO_IMPLEMENTATION_LOOP.md",
    "KARMA_FORGE_PRODUCT_AND_IMPLEMENTATION_LOOP.md",
    "PACKAGE_MANAGEMENT_AND_PUBLIC_PACKAGE_BROWSER.md",
    "MOBILE_PWA_PRODUCT_SPEC.md",
    "LTD_INTEGRATION_OPERATING_MODEL.md",
    "JANITOR_AND_TECH_DEBT_RELEASE_GATE.md",
    "PARTICIPATION_NOTIFICATION_IMPLEMENTATION_PLAN.md",
    "PARTICIPATION_GAMIFICATION_PRODUCT_SPEC.md",
    "ENGAGEMENT_DRIVERS_AUDIT.md",
    "ENGAGEMENT_BACKLOG.yaml",
    "OPERATOR_NOTIFICATION_PRIVACY_REVIEW.md",
    "PUBLIC_PARTICIPATION_COPY_CHANGE_GUIDE.md",
    "SIGNED_IN_PARTICIPATION_DASHBOARD_PLAN.md",
]
REQUIRED_BLOCKER_PATHS = [
    RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_LAUNCH_BLOCKERS.yaml",
    DESIGN_ROOT / "PUBLIC_LAUNCH_BLOCKERS.yaml",
]


def existing_locations(filename: str) -> list[Path]:
    locations = []
    for root in (DESIGN_ROOT, COMPLETION_ROOT):
        path = root / filename
        if path.is_file():
            locations.append(path)
    return locations


def main() -> int:
    failures = []
    lines = [
        "# Completion design docs report",
        "",
        f"- Generated: {now_iso()}",
        "",
        "## Required docs",
        "",
    ]

    for filename in REQUIRED_DOCS:
        locations = existing_locations(filename)
        if not locations:
            failures.append(filename)
            lines.append(f"- `{filename}`: `missing`")
            continue

        formatted = ", ".join(f"`{path}`" for path in locations)
        lines.append(f"- `{filename}`: `present` in {formatted}")

    lines.extend(["", "## Blocker specs", ""])
    for path in REQUIRED_BLOCKER_PATHS:
        if not path.is_file():
            failures.append(str(path))
            lines.append(f"- `{path}`: `missing`")
            continue

        lines.append(f"- `{path}`: `present`")

    lines.insert(3, f"- Status: `{'pass' if not failures else 'fail'}`")
    write_text(completion_path("COMPLETION_DESIGN_DOCS_REPORT.md"), "\n".join(lines))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
