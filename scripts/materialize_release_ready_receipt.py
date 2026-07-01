#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import subprocess
from datetime import UTC, datetime
from pathlib import Path


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
ROOT = RUN_SERVICES_ROOT.parent
LEGACY_RUN_SERVICES_ROOT = ROOT / "chummer.run-services"
OUTPUT_PATH = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "RELEASE_READY.generated.json"
VERIFY_SCRIPT = RUN_SERVICES_ROOT / "scripts" / "verify_chummer6_release_ready.sh"
TIMEOUT_SECONDS = int(os.environ.get("CHUMMER_RELEASE_READY_TIMEOUT_SECONDS", "900"))
TERMINATION_GRACE_SECONDS = int(os.environ.get("CHUMMER_RELEASE_READY_TERMINATION_GRACE_SECONDS", "10"))


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def terminate_process_group(process: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    try:
        stdout, stderr = process.communicate(timeout=TERMINATION_GRACE_SECONDS)
        return coerce_output(stdout), coerce_output(stderr)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = process.communicate()
        return coerce_output(stdout), coerce_output(stderr)


def run_release_verifier(env: dict[str, str]) -> tuple[int, bool, str, str]:
    process = subprocess.Popen(
        ["bash", str(VERIFY_SCRIPT)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    try:
        stdout, stderr = process.communicate(timeout=TIMEOUT_SECONDS)
        return process.returncode or 0, False, coerce_output(stdout).strip(), coerce_output(stderr).strip()
    except subprocess.TimeoutExpired as exc:
        timeout_stdout = coerce_output(exc.stdout).strip()
        timeout_stderr = coerce_output(exc.stderr).strip()
        terminated_stdout, terminated_stderr = terminate_process_group(process)
        stdout = terminated_stdout.strip() or timeout_stdout
        stderr = terminated_stderr.strip() or timeout_stderr
        return 124, True, stdout, stderr


def source_binding_failures() -> list[str]:
    if not VERIFY_SCRIPT.is_file():
        return [f"release verifier script is missing: {VERIFY_SCRIPT}"]

    try:
        verifier_text = VERIFY_SCRIPT.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"release verifier script is unreadable: {exc}"]

    current_root = RUN_SERVICES_ROOT.resolve()
    legacy_root = LEGACY_RUN_SERVICES_ROOT.resolve()
    verifier_uses_legacy_root = "$root/chummer.run-services" in verifier_text or str(legacy_root) in verifier_text
    verifier_accepts_current_root = "CHUMMER_RUN_SERVICES_ROOT" in verifier_text
    if current_root != legacy_root and verifier_uses_legacy_root and not verifier_accepts_current_root:
        return [
            (
                "release verifier is bound to the legacy run-services checkout "
                f"{legacy_root}, not the current repo {current_root}"
            )
        ]

    return []


def progress_lines(stdout: str, stderr: str) -> list[str]:
    return [
        line.strip()
        for line in [*stdout.splitlines(), *stderr.splitlines()]
        if line.strip().startswith("RUN ")
    ]


def main() -> int:
    env = os.environ.copy()
    env.setdefault("CHUMMER_ALLOW_UNSIGNED_PUBLIC_RELEASE", "1")
    env.setdefault("CHUMMER_PUBLIC_BASE_URL", "https://chummer.run")
    env.setdefault("CHUMMER_RUN_SERVICES_ROOT", str(RUN_SERVICES_ROOT))
    env.setdefault("CHUMMER_WORKSPACE_ROOT", str(ROOT))
    binding_failures = source_binding_failures()
    if binding_failures:
        returncode, timed_out, stdout, stderr = 78, False, "", ""
    else:
        returncode, timed_out, stdout, stderr = run_release_verifier(env)

    failure_lines = [
        line.strip()
        for line in [*stdout.splitlines(), *stderr.splitlines()]
        if line.strip().startswith("FAIL ") or line.strip().startswith("verify_")
    ]
    verifier_progress = progress_lines(stdout, stderr)
    failure_lines.extend(binding_failures)
    if timed_out:
        failure_lines.append(f"verify_release_ready timed out after {TIMEOUT_SECONDS}s")
        if verifier_progress:
            failure_lines.append(f"last release-ready gate before timeout: {verifier_progress[-1][4:]}")
    payload = {
        "contract_name": "chummer.release_ready",
        "generated_at_utc": now_iso(),
        "status": "pass" if returncode == 0 else "fail",
        "verdict": "RELEASE_READY" if returncode == 0 else "NOT_RELEASE_READY",
        "command": f"CHUMMER_ALLOW_UNSIGNED_PUBLIC_RELEASE=1 CHUMMER_RUN_SERVICES_ROOT={RUN_SERVICES_ROOT} bash {VERIFY_SCRIPT}",
        "returncode": returncode,
        "timed_out": timed_out,
        "timeout_seconds": TIMEOUT_SECONDS,
        "failures": failure_lines,
        "source_binding": {
            "current_repo": str(RUN_SERVICES_ROOT),
            "legacy_run_services_root": str(LEGACY_RUN_SERVICES_ROOT),
            "verify_script": str(VERIFY_SCRIPT),
            "pass": not binding_failures,
            "failures": binding_failures,
            "verifier_accepts_current_root": True,
        },
        "progress": verifier_progress,
        "stdout_tail": stdout.splitlines()[-80:],
        "stderr_tail": stderr.splitlines()[-80:],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"release_ready_receipt:{payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
