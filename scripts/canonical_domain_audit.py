#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from absolute_completion_common import RUN_SERVICES_ROOT, completion_path, now_iso, write_json, write_text


CHECKS = [
    ("domain_canonicalization", [sys.executable, "scripts/verify_domain_canonicalization.py"]),
    (
        "public_origin_reachability",
        [sys.executable, "scripts/verify_public_origin_reachability.py", "--base-url", "https://chummer.run/"],
    ),
]


def run_check(command: list[str]) -> dict:
    result = subprocess.run(command, cwd=RUN_SERVICES_ROOT, capture_output=True, text=True)
    return {
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "status": "pass" if result.returncode == 0 else "fail",
    }


def main() -> int:
    results = [{"name": name, **run_check(command)} for name, command in CHECKS]
    failed = [result for result in results if result["returncode"] != 0]
    payload = {
        "contract_name": "chummer.canonical_domain_audit",
        "status": "pass" if not failed else "fail",
        "generated_at_utc": now_iso(),
        "canonical_public_domain": "chummer.run",
        "results": results,
    }
    write_json(completion_path("CANONICAL_DOMAIN_AUDIT.generated.json"), payload)

    lines = [
        "# Canonical domain audit",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        "- Canonical public domain: `chummer.run`",
        f"- Status: `{payload['status']}`",
        "",
        "## Checks",
        "",
    ]
    for result in results:
        lines.append(f"- `{result['name']}`: `{result['status']}` - `{result['command']}`")
        if result["stderr"]:
            lines.append(f"  - stderr: `{result['stderr']}`")
    write_text(completion_path("CANONICAL_DOMAIN_AUDIT.md"), "\n".join(lines))

    if failed:
        print(json.dumps(payload, ensure_ascii=True), file=sys.stderr)
        return 1
    print("canonical_domain_audit:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
