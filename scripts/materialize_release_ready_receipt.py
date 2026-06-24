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
TIMEOUT_SECONDS = int(os.environ.get("CHUMMER_RELEASE_READY_TIMEOUT_SECONDS", "900"))


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    env = os.environ.copy()
    env.setdefault("CHUMMER_ALLOW_UNSIGNED_PUBLIC_RELEASE", "1")
    env.setdefault("CHUMMER_PUBLIC_BASE_URL", "https://chummer.run")
    timed_out = False
    returncode = 0
    stdout = ""
    stderr = ""

    try:
        completed = subprocess.run(
            ["bash", str(VERIFY_SCRIPT)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        returncode = completed.returncode
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = 124
        stdout = (exc.stdout or "").strip()
        stderr = (exc.stderr or "").strip()

    failure_lines = [
        line.strip()
        for line in [*stdout.splitlines(), *stderr.splitlines()]
        if line.strip().startswith("FAIL ") or line.strip().startswith("verify_")
    ]
    if timed_out:
        failure_lines.append(f"verify_release_ready timed out after {TIMEOUT_SECONDS}s")
    payload = {
        "contract_name": "chummer.release_ready",
        "generated_at_utc": now_iso(),
        "status": "pass" if returncode == 0 else "fail",
        "verdict": "RELEASE_READY" if returncode == 0 else "NOT_RELEASE_READY",
        "command": f"CHUMMER_ALLOW_UNSIGNED_PUBLIC_RELEASE=1 bash {VERIFY_SCRIPT}",
        "returncode": returncode,
        "timed_out": timed_out,
        "timeout_seconds": TIMEOUT_SECONDS,
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
