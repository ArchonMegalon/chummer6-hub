#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / ".codex-studio" / "published"
OUT_ROOT = REPO_ROOT / ".codex-studio" / "out" / "absolute-audit-local-proof"
PLAYWRIGHT_ROOT = OUT_ROOT / "playwright-tooling"
PLAYWRIGHT_NODE_MODULES = PLAYWRIGHT_ROOT / "node_modules"
PLAYWRIGHT_BIN = PLAYWRIGHT_NODE_MODULES / ".bin" / "playwright"
PLAYWRIGHT_BROWSERS = OUT_ROOT / "playwright-browsers"


def reserve_base_url() -> str:
    configured = os.environ.get("CHUMMER_LOCAL_AUDIT_BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        host, port = probe.getsockname()
    return f"http://{host}:{port}"


BASE_URL = reserve_base_url()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def wait_for_http(url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "timed out"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                body = response.read(8192).decode("utf-8", errors="ignore")
                if response.status < 500 and ("Open downloads" in body or "Chummer" in body):
                    return
        except urllib.error.URLError as exc:
            last_error = str(exc)
        except Exception as exc:  # pragma: no cover - defensive
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def write_receipt(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def ensure_playwright() -> None:
    install_env = os.environ.copy()
    install_env["PLAYWRIGHT_BROWSERS_PATH"] = str(PLAYWRIGHT_BROWSERS)
    PLAYWRIGHT_ROOT.mkdir(parents=True, exist_ok=True)
    PLAYWRIGHT_BROWSERS.mkdir(parents=True, exist_ok=True)

    if not (PLAYWRIGHT_NODE_MODULES / "playwright").is_dir():
        subprocess.run(
            ["npm", "install", "--prefix", str(PLAYWRIGHT_ROOT), "playwright"],
            cwd=REPO_ROOT,
            env=install_env,
            text=True,
            capture_output=True,
            timeout=900,
            check=True,
        )

    subprocess.run(
        [str(PLAYWRIGHT_BIN), "install", "chromium"],
        cwd=REPO_ROOT,
        env=install_env,
        text=True,
        capture_output=True,
        timeout=900,
        check=True,
    )


def run_command(command: list[str], receipt_name: str, script_path: Path, success_summary: str, fail_summary: str) -> dict[str, object]:
    env = os.environ.copy()
    env["CHUMMER_HUB_PLAYWRIGHT_BASE_URL"] = BASE_URL
    env["NODE_PATH"] = str(PLAYWRIGHT_NODE_MODULES)
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(PLAYWRIGHT_BROWSERS)
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    status = "pass" if completed.returncode == 0 else "fail"
    return {
        "contract_name": receipt_name,
        "status": status,
        "generated_at": now_iso(),
        "base_url": BASE_URL,
        "summary": success_summary if status == "pass" else fail_summary,
        "command": command,
        "script": rel(script_path),
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-8000:],
        "stderr": completed.stderr[-8000:],
    }


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    server_log = OUT_ROOT / "local-hub-server.log"
    try:
        ensure_playwright()
    except Exception as exc:
        failure_payload = {
            "generated_at": now_iso(),
            "base_url": BASE_URL,
            "status": "fail",
            "exit_code": 1,
            "stdout": "",
            "stderr": str(exc),
        }
        write_receipt(
            OUTPUT_ROOT / "PHONE_LAYOUT_PROOF.local.generated.json",
            {
                "contract_name": "chummer.run.phone_layout_proof_local",
                "summary": "Local phone-layout proof could not start because the isolated Playwright toolchain failed to bootstrap.",
                "script": rel(REPO_ROOT / "scripts" / "check-public-mobile-nav.cjs"),
                "command": ["node", "scripts/check-public-mobile-nav.cjs"],
                **failure_payload,
            },
        )
        write_receipt(
            OUTPUT_ROOT / "SUPPORT_CASE_FLOW_PROOF.local.generated.json",
            {
                "contract_name": "chummer.run.support_case_flow_proof_local",
                "summary": "Local support-case flow proof could not start because the isolated Playwright toolchain failed to bootstrap.",
                "script": rel(REPO_ROOT / "scripts" / "check-support-case-flow.py"),
                "command": ["python3", "scripts/check-support-case-flow.py"],
                **failure_payload,
            },
        )
        return 1

    env = os.environ.copy()
    env.setdefault("ASPNETCORE_ENVIRONMENT", "Development")
    env.setdefault("DOTNET_ENVIRONMENT", "Development")
    env["ASPNETCORE_URLS"] = BASE_URL

    server = subprocess.Popen(
        ["dotnet", "run", "--no-launch-profile", "--project", "Chummer.Run.Api/Chummer.Run.Api.csproj"],
        cwd=REPO_ROOT,
        env=env,
        stdout=server_log.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )

    receipts: list[tuple[Path, dict[str, object]]] = []
    exit_code = 0
    try:
        wait_for_http(f"{BASE_URL}/", timeout_seconds=180)

        phone_receipt = run_command(
            ["node", "scripts/check-public-mobile-nav.cjs"],
            "chummer.run.phone_layout_proof_local",
            REPO_ROOT / "scripts" / "check-public-mobile-nav.cjs",
            "Local phone-layout proof passed against the development Hub shell using the compact mobile navigation harness.",
            "Local phone-layout proof failed in the Playwright harness.",
        )
        receipts.append((OUTPUT_ROOT / "PHONE_LAYOUT_PROOF.local.generated.json", phone_receipt))

        support_receipt = run_command(
            ["python3", "scripts/check-support-case-flow.py"],
            "chummer.run.support_case_flow_proof_local",
            REPO_ROOT / "scripts" / "check-support-case-flow.py",
            "Local first-party support-flow proof passed across help, contact, FAQ, and the bounded account/support login gates.",
            "Local support-case flow proof failed in the focused first-party support verifier.",
        )
        receipts.append((OUTPUT_ROOT / "SUPPORT_CASE_FLOW_PROOF.local.generated.json", support_receipt))

        for path, payload in receipts:
            write_receipt(path, payload)
            if payload["status"] != "pass":
                exit_code = 1
    finally:
        try:
            os.killpg(server.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            server.wait(timeout=20)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(server.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            server.wait(timeout=10)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
