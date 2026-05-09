#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / ".codex-studio" / "published" / "PUBLIC_CLAIM_SCAN.generated.json"

TARGETS = (
    "Chummer.Run.Api/Views/PublicLanding/*.cshtml",
    "Chummer.Run.Api/Views/Shared/_Layout.cshtml",
    "Chummer.Run.Api/Services/PublicNavigationService.cs",
    "Chummer.Run.Api/Services/DesktopInstallRail.cs",
    "docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md",
)

PATTERNS = (
    ("full_parity", re.compile(r"\bfull parity\b", re.IGNORECASE)),
    ("release_grade_readiness", re.compile(r"\brelease[- ]grade readiness\b", re.IGNORECASE)),
    ("serious_sr4", re.compile(r"\bserious SR4\b", re.IGNORECASE)),
    ("serious_sr6", re.compile(r"\bserious SR6\b", re.IGNORECASE)),
    ("sr4_ready", re.compile(r"\bSR4 (?:ready|complete|fully supported)\b", re.IGNORECASE)),
    ("sr6_ready", re.compile(r"\bSR6 (?:ready|complete|fully supported)\b", re.IGNORECASE)),
    ("github_required", re.compile(r"\bGitHub (?:is required|required for (?:downloads|install))\b", re.IGNORECASE)),
    ("provider_leak", re.compile(r"\b(ProductLift|Deftform|Typeform|Trello|Jira|Clerk)\b", re.IGNORECASE)),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def iter_target_files() -> list[Path]:
    files: list[Path] = []
    for pattern in TARGETS:
        matches = sorted(REPO_ROOT.glob(pattern))
        for path in matches:
            if path.is_file():
                files.append(path)
    return files


def main() -> int:
    hits: list[dict[str, object]] = []
    files = iter_target_files()
    for path in files:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for pattern_id, pattern in PATTERNS:
                if pattern.search(line):
                    hits.append(
                        {
                            "pattern_id": pattern_id,
                            "path": str(path.relative_to(REPO_ROOT)),
                            "line": line_number,
                            "text": line.strip(),
                        }
                    )

    payload = {
        "contract_name": "chummer.run.public_claim_scan",
        "status": "pass" if not hits else "fail",
        "generated_at": now_iso(),
        "scanned_files": [str(path.relative_to(REPO_ROOT)) for path in files],
        "pattern_ids": [pattern_id for pattern_id, _ in PATTERNS],
        "hit_count": len(hits),
        "hits": hits,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0 if not hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
