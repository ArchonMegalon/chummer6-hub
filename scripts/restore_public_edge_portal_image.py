#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_NAME = "chummer6-hub"
DEFAULT_PORTAL_SERVICE = "chummer-portal"
DEFAULT_PORTAL_CONTAINER = "chummer6-hub-chummer-portal-1"
DEFAULT_PORTAL_IMAGE_TAG = "chummer-run-api:local"
DEFAULT_BASE_URL = "https://chummer.run"


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    skipped: bool = False


def normalize_image_id(value: str) -> str:
    normalized = str(value or "").strip()
    if re.fullmatch(r"[0-9a-fA-F]{64}", normalized):
        return f"sha256:{normalized.lower()}"
    if normalized.startswith("sha256:"):
        prefix, digest = normalized.split(":", 1)
        return f"{prefix}:{digest.lower()}"
    return normalized


def require_sha256_image_id(value: str) -> str:
    normalized = normalize_image_id(value)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", normalized):
        raise ValueError(f"expected a sha256:<64 hex> image id, got {value!r}")
    return normalized


def run_command(command: list[str], cwd: Path = ROOT, dry_run: bool = False) -> CommandResult:
    if dry_run:
        return CommandResult(command=command, returncode=0, stdout="", stderr="", skipped=True)
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    return CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def run_checked(command: list[str], cwd: Path = ROOT, dry_run: bool = False) -> CommandResult:
    result = run_command(command, cwd=cwd, dry_run=dry_run)
    if result.returncode != 0:
        rendered = " ".join(command)
        detail = result.stderr or result.stdout or f"exit {result.returncode}"
        raise RuntimeError(f"{rendered}: {detail}")
    return result


def inspect_image_id(image_ref: str, dry_run: bool = False) -> str:
    result = run_checked(["docker", "image", "inspect", "--format", "{{.Id}}", image_ref], dry_run=dry_run)
    return normalize_image_id(result.stdout)


def inspect_container_image_id(container: str, dry_run: bool = False) -> tuple[str, str]:
    result = run_checked(["docker", "inspect", "--format", "{{.Image}} {{.Config.Image}}", container], dry_run=dry_run)
    parts = result.stdout.split(maxsplit=1)
    image_id = normalize_image_id(parts[0]) if parts else ""
    image_ref = parts[1].strip() if len(parts) > 1 else ""
    return image_id, image_ref


def compose_command(
    compose_file: Path,
    env_file: Path | None,
    project_name: str,
    service: str,
) -> list[str]:
    command = ["docker", "compose"]
    if env_file is not None:
        command.extend(["--env-file", str(env_file)])
    command.extend(
        [
            "-p",
            project_name,
            "-f",
            str(compose_file),
            "up",
            "-d",
            "--no-build",
            "--no-deps",
            "--force-recreate",
            service,
        ]
    )
    return command


def resolve_env_file(value: str, repo_root: Path) -> Path | None:
    if not value:
        candidate = repo_root / ".env"
        return candidate if candidate.is_file() else None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    if not candidate.is_file():
        raise FileNotFoundError(f"compose env file not found: {candidate}")
    return candidate


def restore_portal_image(
    expected_image_id: str,
    image_tags: list[str],
    compose_file: Path,
    env_file: Path | None,
    project_name: str,
    service: str,
    portal_container: str,
    force_recreate: bool,
    dry_run: bool,
) -> dict[str, Any]:
    expected = require_sha256_image_id(expected_image_id)
    unique_tags = list(dict.fromkeys(tag for tag in image_tags if tag.strip()))
    if not unique_tags:
        unique_tags = [DEFAULT_PORTAL_IMAGE_TAG]

    source_image_id = inspect_image_id(expected, dry_run=dry_run)
    if source_image_id and source_image_id != expected:
        raise RuntimeError(f"approved source image resolved to {source_image_id}, expected {expected}")

    tag_states: list[dict[str, Any]] = []
    tag_commands: list[list[str]] = []
    for tag in unique_tags:
        try:
            current_tag_id = inspect_image_id(tag, dry_run=dry_run)
        except RuntimeError:
            current_tag_id = ""
        needs_retag = current_tag_id != expected
        if needs_retag:
            command = ["docker", "tag", expected, tag]
            run_checked(command, dry_run=dry_run)
            tag_commands.append(command)
        tag_states.append(
            {
                "tag": tag,
                "imageIdBefore": current_tag_id,
                "retagged": needs_retag,
            }
        )

    try:
        container_image_id, container_image_ref = inspect_container_image_id(portal_container, dry_run=dry_run)
    except RuntimeError:
        container_image_id, container_image_ref = "", ""

    should_recreate = force_recreate or container_image_id != expected
    compose_run: list[str] = []
    if should_recreate:
        compose_run = compose_command(compose_file, env_file, project_name, service)
        run_checked(compose_run, dry_run=dry_run)

    return {
        "expectedImageId": expected,
        "sourceImageId": source_image_id or expected,
        "portalContainer": portal_container,
        "containerImageIdBefore": container_image_id,
        "containerImageRefBefore": container_image_ref,
        "containerRecreated": should_recreate,
        "imageTags": tag_states,
        "retagCommands": tag_commands,
        "composeCommand": compose_run,
        "dryRun": dry_run,
    }


def inspect_runtime_state(
    expected_image_id: str,
    image_tags: list[str],
    portal_container: str,
    dry_run: bool,
) -> dict[str, Any]:
    expected = require_sha256_image_id(expected_image_id)
    unique_tags = list(dict.fromkeys(tag for tag in image_tags if tag.strip())) or [DEFAULT_PORTAL_IMAGE_TAG]
    if dry_run:
        return {
            "expectedImageId": expected,
            "portalContainer": portal_container,
            "containerImageId": expected,
            "containerImageRef": "",
            "imageTags": [{"tag": tag, "imageId": expected} for tag in unique_tags],
            "drift": [],
            "dryRun": True,
        }

    drift: list[str] = []
    try:
        container_image_id, container_image_ref = inspect_container_image_id(portal_container, dry_run=False)
    except RuntimeError as error:
        container_image_id, container_image_ref = "", ""
        drift.append(f"portal container inspect failed: {error}")
    if container_image_id and container_image_id != expected:
        drift.append(f"portal container points at {container_image_id}")

    tag_states: list[dict[str, str]] = []
    for tag in unique_tags:
        try:
            tag_image_id = inspect_image_id(tag, dry_run=False)
        except RuntimeError as error:
            tag_image_id = ""
            drift.append(f"portal image tag {tag} inspect failed: {error}")
        if tag_image_id and tag_image_id != expected:
            drift.append(f"portal image tag {tag} points at {tag_image_id}")
        tag_states.append({"tag": tag, "imageId": tag_image_id})

    return {
        "expectedImageId": expected,
        "portalContainer": portal_container,
        "containerImageId": container_image_id,
        "containerImageRef": container_image_ref,
        "imageTags": tag_states,
        "drift": drift,
        "dryRun": False,
    }


def watch_runtime_stability(
    expected_image_id: str,
    image_tags: list[str],
    compose_file: Path,
    env_file: Path | None,
    project_name: str,
    service: str,
    portal_container: str,
    window_seconds: float,
    poll_seconds: float,
    max_restores: int,
    dry_run: bool,
) -> dict[str, Any]:
    expected = require_sha256_image_id(expected_image_id)
    if window_seconds <= 0:
        return {
            "status": "pass",
            "skipped": True,
            "windowSeconds": window_seconds,
            "pollSeconds": poll_seconds,
            "repairCount": 0,
            "driftEvents": [],
        }
    if dry_run:
        return {
            "status": "pass",
            "skipped": True,
            "dryRun": True,
            "windowSeconds": window_seconds,
            "pollSeconds": poll_seconds,
            "repairCount": 0,
            "driftEvents": [],
        }

    stable_started_at = datetime.now(UTC)
    stable_until = time.monotonic() + window_seconds
    repair_count = 0
    drift_events: list[dict[str, Any]] = []
    last_state = inspect_runtime_state(expected, image_tags, portal_container, dry_run=False)

    while time.monotonic() < stable_until:
        time.sleep(max(0.0, poll_seconds))
        last_state = inspect_runtime_state(expected, image_tags, portal_container, dry_run=False)
        drift = last_state.get("drift", [])
        if not drift:
            continue
        if repair_count >= max_restores:
            raise RuntimeError(f"public edge runtime image drift persisted after {repair_count} repairs: {drift}")
        repair = restore_portal_image(
            expected,
            image_tags,
            compose_file,
            env_file,
            project_name,
            service,
            portal_container,
            False,
            False,
        )
        repair_count += 1
        drift_events.append(
            {
                "detectedAtUtc": datetime.now(UTC).isoformat(),
                "drift": drift,
                "state": last_state,
                "repair": repair,
            }
        )
        stable_started_at = datetime.now(UTC)
        stable_until = time.monotonic() + window_seconds

    return {
        "status": "pass",
        "skipped": False,
        "windowSeconds": window_seconds,
        "pollSeconds": poll_seconds,
        "maxRestores": max_restores,
        "repairCount": repair_count,
        "stableStartedAtUtc": stable_started_at.isoformat(),
        "completedAtUtc": datetime.now(UTC).isoformat(),
        "lastState": last_state,
        "driftEvents": drift_events,
    }


def run_postdeploy_gate(
    expected_image_id: str,
    base_url: str,
    portal_container: str,
    portal_image_tag: str,
    output_path: Path,
    attempts: int,
    retry_delay_seconds: float,
    browser_proofs: list[str],
    playwright_timeout_seconds: float,
    playwright_artifact_dir: Path | None,
    dry_run: bool,
) -> dict[str, Any]:
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "verify_public_edge_postdeploy_gate.py"),
        "--base-url",
        base_url,
        "--skip-preflight",
        "--expected-portal-image-id",
        expected_image_id,
        "--portal-container",
        portal_container,
        "--portal-image-tag",
        portal_image_tag,
        "--output",
        str(output_path),
    ]
    browser_flag_by_name = {
        "downloadsStatus": "--require-downloads-status-playwright",
        "mobilePwaViewport": "--require-mobile-pwa-viewport-playwright",
        "frontdoorNavigation": "--require-frontdoor-navigation-playwright",
    }
    for proof_name in browser_proofs:
        command.append(browser_flag_by_name[proof_name])
    if browser_proofs:
        command.extend(["--playwright-timeout-seconds", str(playwright_timeout_seconds)])
        if playwright_artifact_dir is not None:
            command.extend(["--playwright-artifact-dir", str(playwright_artifact_dir)])
    max_attempts = max(1, attempts)
    run_records: list[dict[str, Any]] = []
    last_result = CommandResult(command, 1, "", "postdeploy gate did not run")
    last_payload: dict[str, Any] = {}

    for attempt_index in range(1, max_attempts + 1):
        last_result = run_command(command, dry_run=dry_run)
        last_payload = {}
        if not dry_run and output_path.is_file():
            loaded = json.loads(output_path.read_text(encoding="utf-8-sig"))
            last_payload = loaded if isinstance(loaded, dict) else {}
        status = last_payload.get("status", "dry_run" if dry_run else "")
        run_records.append(
            {
                "attempt": attempt_index,
                "returncode": last_result.returncode,
                "status": status,
                "portalRuntimeImageStatus": last_payload.get("portalRuntimeImageStatus", ""),
                "browserPlaywrightStatus": last_payload.get("browserPlaywrightStatus", ""),
                "browserPlaywrightRequiredProofs": last_payload.get("browserPlaywrightRequiredProofs", []),
                "releaseManifestVersion": last_payload.get("releaseManifestVersion", ""),
            }
        )
        if last_result.returncode == 0:
            return {
                "command": command,
                "returncode": last_result.returncode,
                "outputPath": str(output_path),
                "status": status,
                "portalRuntimeImageStatus": last_payload.get("portalRuntimeImageStatus", ""),
                "browserPlaywrightStatus": last_payload.get("browserPlaywrightStatus", ""),
                "browserPlaywrightRequiredProofs": last_payload.get("browserPlaywrightRequiredProofs", []),
                "releaseManifestVersion": last_payload.get("releaseManifestVersion", ""),
                "attempts": run_records,
            }
        if attempt_index < max_attempts and not dry_run:
            time.sleep(retry_delay_seconds)

    rendered = " ".join(command)
    detail = last_result.stderr or last_result.stdout or f"exit {last_result.returncode}"
    raise RuntimeError(f"{rendered}: {detail}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restore the public-edge portal container to an approved image id without rebuilding it.")
    parser.add_argument("--expected-portal-image-id", required=True)
    parser.add_argument("--image-tag", action="append", default=[], help="Mutable tag to repoint at the approved image id. Repeatable.")
    parser.add_argument("--compose-file", default=str(ROOT / "docker-compose.public-edge.yml"))
    parser.add_argument("--env-file", default="", help="Compose env file. Defaults to .env when it exists; omit when absent.")
    parser.add_argument("--project-name", default=DEFAULT_PROJECT_NAME)
    parser.add_argument("--service", default=DEFAULT_PORTAL_SERVICE)
    parser.add_argument("--portal-container", default=DEFAULT_PORTAL_CONTAINER)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--postdeploy-output", default=str(ROOT / ".codex-studio" / "published" / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"))
    parser.add_argument("--postdeploy-attempts", type=int, default=3)
    parser.add_argument("--postdeploy-retry-delay-seconds", type=float, default=5.0)
    parser.add_argument("--require-downloads-status-playwright", action="store_true")
    parser.add_argument("--require-mobile-pwa-viewport-playwright", action="store_true")
    parser.add_argument("--require-frontdoor-navigation-playwright", action="store_true")
    parser.add_argument("--require-all-browser-proofs", action="store_true")
    parser.add_argument("--playwright-timeout-seconds", type=float, default=420.0)
    parser.add_argument("--playwright-artifact-dir")
    parser.add_argument("--stability-window-seconds", type=float, default=0.0)
    parser.add_argument("--stability-poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-stability-restores", type=int, default=3)
    parser.add_argument("--skip-postdeploy", action="store_true")
    parser.add_argument("--force-recreate", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", help="Optional JSON receipt path for this restore action.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_root = ROOT
    compose_file = Path(args.compose_file).expanduser()
    if not compose_file.is_absolute():
        compose_file = repo_root / compose_file
    if not compose_file.is_file():
        parser.error(f"compose file not found: {compose_file}")

    try:
        env_file = resolve_env_file(args.env_file, repo_root)
        expected = require_sha256_image_id(args.expected_portal_image_id)
        browser_proofs: list[str] = []
        if args.require_all_browser_proofs or args.require_downloads_status_playwright:
            browser_proofs.append("downloadsStatus")
        if args.require_all_browser_proofs or args.require_mobile_pwa_viewport_playwright:
            browser_proofs.append("mobilePwaViewport")
        if args.require_all_browser_proofs or args.require_frontdoor_navigation_playwright:
            browser_proofs.append("frontdoorNavigation")
        restore_receipt = restore_portal_image(
            expected,
            args.image_tag or [DEFAULT_PORTAL_IMAGE_TAG],
            compose_file,
            env_file,
            args.project_name,
            args.service,
            args.portal_container,
            args.force_recreate,
            args.dry_run,
        )
        stability_receipt = watch_runtime_stability(
            expected,
            args.image_tag or [DEFAULT_PORTAL_IMAGE_TAG],
            compose_file,
            env_file,
            args.project_name,
            args.service,
            args.portal_container,
            args.stability_window_seconds,
            args.stability_poll_seconds,
            args.max_stability_restores,
            args.dry_run,
        )
        postdeploy_receipt = None
        if not args.skip_postdeploy:
            postdeploy_receipt = run_postdeploy_gate(
                expected,
                args.base_url,
                args.portal_container,
                (args.image_tag or [DEFAULT_PORTAL_IMAGE_TAG])[0],
                Path(args.postdeploy_output).expanduser(),
                args.postdeploy_attempts,
                args.postdeploy_retry_delay_seconds,
                browser_proofs,
                args.playwright_timeout_seconds,
                Path(args.playwright_artifact_dir).expanduser() if args.playwright_artifact_dir else None,
                args.dry_run,
            )
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1

    receipt = {
        "contractName": "chummer.public_edge_portal_image_restore.v1",
        "status": "pass",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "restore": restore_receipt,
        "stability": stability_receipt,
        "postdeploy": postdeploy_receipt,
        "browserProofRequirements": browser_proofs,
    }
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
