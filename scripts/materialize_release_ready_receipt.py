#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path("/docker/chummercomplete")
RUN_SERVICES_ROOT = ROOT / "chummer.run-services"
OUTPUT_PATH = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "RELEASE_READY.generated.json"
VERIFY_SCRIPT = ROOT / "scripts" / "release" / "verify_chummer6_release_ready.sh"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    env = os.environ.copy()
    env.setdefault("CHUMMER_ALLOW_UNSIGNED_PUBLIC_RELEASE", "1")
    env.setdefault("CHUMMER_PUBLIC_BASE_URL", "https://chummer.run")
    completed = subprocess.run(
        ["bash", str(VERIFY_SCRIPT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    failure_lines = [
        line.strip()
        for line in stdout.splitlines()
        if line.strip().startswith("FAIL ") or line.strip().startswith("verify_")
    ]
    payload = {
        "contract_name": "chummer.release_ready",
        "generated_at_utc": now_iso(),
        "status": "pass" if completed.returncode == 0 else "fail",
        "verdict": "RELEASE_READY" if completed.returncode == 0 else "NOT_RELEASE_READY",
        "command": f"CHUMMER_ALLOW_UNSIGNED_PUBLIC_RELEASE=1 bash {VERIFY_SCRIPT}",
        "returncode": completed.returncode,
        "failures": failure_lines,
        "stdout_tail": stdout.splitlines()[-80:],
        "stderr_tail": stderr.splitlines()[-80:],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"release_ready_receipt:{payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
