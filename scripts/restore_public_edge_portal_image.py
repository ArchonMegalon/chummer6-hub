#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import json
import os
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
PUBLIC_EDGE_MUTATION_LOCK = Path("/docker/chummercomplete/.state/public-edge-mutation.lock")


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    skipped: bool = False


def acquire_public_edge_mutation_lock(*, dry_run: bool) -> Path | None:
    if dry_run:
        return None
    lock_root = PUBLIC_EDGE_MUTATION_LOCK.parent
    lock_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    if lock_root.is_symlink() or not lock_root.is_dir():
        raise RuntimeError("public-edge mutation lock root is not a real directory")
    if lock_root.stat().st_uid != os.getuid():
        raise RuntimeError("public-edge mutation lock root is not owned by the caller")
    os.chmod(lock_root, 0o700)
    try:
        PUBLIC_EDGE_MUTATION_LOCK.mkdir(mode=0o700)
    except FileExistsError as error:
        raise RuntimeError(
            "another public-edge mutation owns the shared deployment authority"
        ) from error
    return PUBLIC_EDGE_MUTATION_LOCK


def release_public_edge_mutation_lock(lock_path: Path | None) -> None:
    if lock_path is not None:
        lock_path.rmdir()


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


def inspect_image_details(image_ref: str, dry_run: bool = False) -> dict[str, Any]:
    if not image_ref:
        return {}
    if dry_run:
        return {"imageId": normalize_image_id(image_ref), "dryRun": True}
    result = run_checked(["docker", "image", "inspect", image_ref], dry_run=False)
    payload = json.loads(result.stdout)
    image = payload[0] if isinstance(payload, list) and payload else {}
    config = image.get("Config") if isinstance(image.get("Config"), dict) else {}
    return {
        "imageId": normalize_image_id(str(image.get("Id") or image_ref)),
        "created": image.get("Created") or "",
        "repoTags": image.get("RepoTags") or [],
        "repoDigests": image.get("RepoDigests") or [],
        "labels": config.get("Labels") or {},
    }


def try_inspect_image_details(image_ref: str, dry_run: bool = False) -> dict[str, Any]:
    if not image_ref:
        return {}
    try:
        return inspect_image_details(image_ref, dry_run=dry_run)
    except Exception as error:
        return {"imageId": normalize_image_id(image_ref), "inspectError": str(error)}


def inspect_container_image_id(container: str, dry_run: bool = False) -> tuple[str, str]:
    result = run_checked(["docker", "inspect", "--format", "{{.Image}} {{.Config.Image}}", container], dry_run=dry_run)
    parts = result.stdout.split(maxsplit=1)
    image_id = normalize_image_id(parts[0]) if parts else ""
    image_ref = parts[1].strip() if len(parts) > 1 else ""
    return image_id, image_ref


def inspect_container_runtime(container: str, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return {
            "containerId": container,
            "imageId": "",
            "imageRef": "",
            "status": "running",
            "running": True,
            "exitCode": 0,
            "startedAt": "",
            "finishedAt": "",
        }
    result = run_checked(["docker", "inspect", container], dry_run=False)
    payload = json.loads(result.stdout)
    container_payload = payload[0] if isinstance(payload, list) and payload else {}
    state = container_payload.get("State") if isinstance(container_payload.get("State"), dict) else {}
    config = container_payload.get("Config") if isinstance(container_payload.get("Config"), dict) else {}
    return {
        "containerId": str(container_payload.get("Id") or "").strip(),
        "imageId": normalize_image_id(str(container_payload.get("Image") or "")),
        "imageRef": str(config.get("Image") or "").strip(),
        "status": str(state.get("Status") or "").strip(),
        "running": bool(state.get("Running")),
        "exitCode": state.get("ExitCode"),
        "startedAt": str(state.get("StartedAt") or ""),
        "finishedAt": str(state.get("FinishedAt") or ""),
    }


def list_local_image_tags(dry_run: bool = False) -> list[str]:
    if dry_run:
        return []
    result = run_checked(["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"], dry_run=False)
    tags: list[str] = []
    for line in result.stdout.splitlines():
        tag = line.strip()
        if not tag or "<none>" in tag:
            continue
        tags.append(tag)
    return tags


def repository_prefix_for_tag(tag: str) -> str:
    candidate = str(tag or "").strip()
    if ":" not in candidate:
        return ""
    return candidate.rsplit(":", 1)[0] + ":"


def discover_runtime_alias_tags(
    image_tags: list[str],
    container_image_id: str,
    dry_run: bool = False,
) -> list[str]:
    normalized_container_image_id = normalize_image_id(container_image_id)
    if not normalized_container_image_id:
        return []

    repository_prefix = ""
    for tag in image_tags:
        repository_prefix = repository_prefix_for_tag(tag)
        if repository_prefix:
            break

    details = try_inspect_image_details(normalized_container_image_id, dry_run=dry_run)
    repo_tags = details.get("repoTags") if isinstance(details.get("repoTags"), list) else []
    discovered: list[str] = []
    for raw_tag in repo_tags:
        tag = str(raw_tag or "").strip()
        if not tag or "<none>" in tag:
            continue
        if repository_prefix and not tag.startswith(repository_prefix):
            continue
        discovered.append(tag)
    return list(dict.fromkeys(discovered))


def resolve_image_tags(
    image_tags: list[str],
    include_patterns: list[str],
    container_image_id: str = "",
    dry_run: bool = False,
) -> list[str]:
    resolved = list(dict.fromkeys(tag.strip() for tag in image_tags if tag.strip()))
    if not resolved:
        resolved = [DEFAULT_PORTAL_IMAGE_TAG]

    resolved.extend(discover_runtime_alias_tags(resolved, container_image_id, dry_run=dry_run))
    compiled_patterns = [re.compile(pattern) for pattern in include_patterns if pattern.strip()]
    if compiled_patterns:
        for tag in list_local_image_tags(dry_run=dry_run):
            if any(pattern.search(tag) for pattern in compiled_patterns):
                resolved.append(tag)

    return list(dict.fromkeys(resolved))


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


def compose_volume_initializer_command(
    compose_file: Path,
    env_file: Path | None,
    project_name: str,
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
            "run",
            "--rm",
            "--no-deps",
            "chummer-portal-volume-init",
        ]
    )
    return command


def compose_stop_command(
    compose_file: Path,
    env_file: Path | None,
    project_name: str,
    service: str,
) -> list[str]:
    command = ["docker", "compose"]
    if env_file is not None:
        command.extend(["--env-file", str(env_file)])
    command.extend(["-p", project_name, "-f", str(compose_file), "stop", service])
    return command


def attempt_previous_portal_restore(
    *,
    prior_container_id: str,
    prior_image_id: str,
    prior_image_tag: str,
    prior_was_running: bool,
    compose_file: Path,
    env_file: Path | None,
    project_name: str,
    service: str,
    dry_run: bool,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    if not prior_was_running:
        return {"required": False, "status": "not_required", "attempts": attempts}

    if prior_container_id:
        start_command = ["docker", "start", prior_container_id]
        start_result = run_command(start_command, dry_run=dry_run)
        attempts.append({"command": start_command, "returncode": start_result.returncode})
        if start_result.returncode == 0:
            return {"required": True, "status": "prior_container_started", "attempts": attempts}

    if prior_image_id and prior_image_tag:
        tag_command = ["docker", "tag", prior_image_id, prior_image_tag]
        tag_result = run_command(tag_command, dry_run=dry_run)
        attempts.append({"command": tag_command, "returncode": tag_result.returncode})
        if tag_result.returncode == 0:
            recreate_command = compose_command(compose_file, env_file, project_name, service)
            recreate_result = run_command(recreate_command, dry_run=dry_run)
            attempts.append({"command": recreate_command, "returncode": recreate_result.returncode})
            if recreate_result.returncode == 0:
                return {"required": True, "status": "prior_image_recreated", "attempts": attempts}

    return {"required": True, "status": "failed", "attempts": attempts}


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
    source_image_details = try_inspect_image_details(expected, dry_run=dry_run)
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
                "imageDetailsBefore": try_inspect_image_details(current_tag_id, dry_run=dry_run),
                "retagged": needs_retag,
            }
        )

    try:
        container_runtime = inspect_container_runtime(portal_container, dry_run=dry_run)
        container_id = str(container_runtime.get("containerId") or "")
        container_image_id = str(container_runtime.get("imageId") or "")
        container_image_ref = str(container_runtime.get("imageRef") or "")
    except RuntimeError:
        container_runtime = {}
        container_id, container_image_id, container_image_ref = "", "", ""

    container_running = container_runtime.get("running") is True
    should_recreate = force_recreate or container_image_id != expected or not container_running
    portal_quiesce_run: list[str] = []
    compose_run: list[str] = []
    volume_initializer_run: list[str] = []
    if should_recreate:
        portal_quiesce_run = compose_stop_command(compose_file, env_file, project_name, service)
        volume_initializer_run = compose_volume_initializer_command(compose_file, env_file, project_name)
        compose_run = compose_command(compose_file, env_file, project_name, service)
        try:
            run_checked(portal_quiesce_run, dry_run=dry_run)
            run_checked(volume_initializer_run, dry_run=dry_run)
            run_checked(compose_run, dry_run=dry_run)
        except BaseException as error:
            prior_image_tag = (
                container_image_ref
                if container_image_ref and not container_image_ref.startswith("sha256:")
                else unique_tags[0]
            )
            rollback = attempt_previous_portal_restore(
                prior_container_id=container_id,
                prior_image_id=container_image_id,
                prior_image_tag=prior_image_tag,
                prior_was_running=container_running,
                compose_file=compose_file,
                env_file=env_file,
                project_name=project_name,
                service=service,
                dry_run=dry_run,
            )
            if rollback["status"] == "failed":
                raise RuntimeError(f"{error}; prior portal restore also failed: {rollback['attempts']}") from error
            raise

    return {
        "expectedImageId": expected,
        "sourceImageId": source_image_id or expected,
        "sourceImageDetails": source_image_details,
        "portalContainer": portal_container,
        "containerIdBefore": container_id,
        "containerImageIdBefore": container_image_id,
        "containerImageRefBefore": container_image_ref,
        "containerStatusBefore": container_runtime.get("status", ""),
        "containerRunningBefore": container_running,
        "containerImageDetailsBefore": try_inspect_image_details(container_image_id, dry_run=dry_run),
        "containerRecreated": should_recreate,
        "imageTags": tag_states,
        "retagCommands": tag_commands,
        "portalQuiesceCommand": portal_quiesce_run,
        "volumeInitializerCommand": volume_initializer_run,
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
            "containerImageDetails": try_inspect_image_details(expected, dry_run=True),
            "imageTags": [
                {"tag": tag, "imageId": expected, "imageDetails": try_inspect_image_details(expected, dry_run=True)}
                for tag in unique_tags
            ],
            "drift": [],
            "dryRun": True,
        }

    drift: list[str] = []
    try:
        container_runtime = inspect_container_runtime(portal_container, dry_run=False)
        container_image_id = str(container_runtime.get("imageId") or "")
        container_image_ref = str(container_runtime.get("imageRef") or "")
    except RuntimeError as error:
        container_runtime = {}
        container_image_id, container_image_ref = "", ""
        drift.append(f"portal container inspect failed: {error}")
    container_status = str(container_runtime.get("status") or "")
    if container_runtime and container_runtime.get("running") is not True:
        if container_status:
            drift.append(f"portal container is not running (status {container_status})")
        else:
            drift.append("portal container is not running")
    if container_image_id and container_image_id != expected:
        drift.append(f"portal container points at {container_image_id}")

    tag_states: list[dict[str, Any]] = []
    for tag in unique_tags:
        try:
            tag_image_id = inspect_image_id(tag, dry_run=False)
        except RuntimeError as error:
            tag_image_id = ""
            drift.append(f"portal image tag {tag} inspect failed: {error}")
        if tag_image_id and tag_image_id != expected:
            drift.append(f"portal image tag {tag} points at {tag_image_id}")
        tag_states.append({"tag": tag, "imageId": tag_image_id, "imageDetails": try_inspect_image_details(tag_image_id)})

    return {
        "expectedImageId": expected,
        "portalContainer": portal_container,
        "containerImageId": container_image_id,
        "containerImageRef": container_image_ref,
        "containerStatus": container_status,
        "containerRunning": container_runtime.get("running") is True,
        "containerExitCode": container_runtime.get("exitCode"),
        "containerImageDetails": try_inspect_image_details(container_image_id),
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
    expected_release_channel: str,
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
        "--expected-release-channel",
        expected_release_channel,
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
    parser.add_argument(
        "--include-image-tags-matching",
        action="append",
        default=[],
        help="Regex for additional local image tags to repoint at the approved image id, for example '^chummer-run-api:pwa-direct', '^chummer-run-api:current-source', or '^chummer-run-api:fixed-alias'. Repeatable.",
    )
    parser.add_argument("--compose-file", default=str(ROOT / "docker-compose.public-edge.yml"))
    parser.add_argument("--env-file", default="", help="Compose env file. Defaults to .env when it exists; omit when absent.")
    parser.add_argument("--project-name", default=DEFAULT_PROJECT_NAME)
    parser.add_argument("--service", default=DEFAULT_PORTAL_SERVICE)
    parser.add_argument("--portal-container", default=DEFAULT_PORTAL_CONTAINER)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--expected-release-channel",
        default="public_stable",
        choices=["public_stable", "stable", "preview", "nightly"],
        help="Expected downloads release posture. Use preview/nightly for a nightly handoff without promoting stable.",
    )
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

    mutation_lock: Path | None = None
    try:
        mutation_lock = acquire_public_edge_mutation_lock(dry_run=args.dry_run)
        if mutation_lock is not None:
            atexit.register(release_public_edge_mutation_lock, mutation_lock)
        env_file = resolve_env_file(args.env_file, repo_root)
        expected = require_sha256_image_id(args.expected_portal_image_id)
        browser_proofs: list[str] = []
        if args.require_all_browser_proofs or args.require_downloads_status_playwright:
            browser_proofs.append("downloadsStatus")
        if args.require_all_browser_proofs or args.require_mobile_pwa_viewport_playwright:
            browser_proofs.append("mobilePwaViewport")
        if args.require_all_browser_proofs or args.require_frontdoor_navigation_playwright:
            browser_proofs.append("frontdoorNavigation")
        try:
            container_image_id_before_discovery, _container_image_ref_before_discovery = inspect_container_image_id(
                args.portal_container,
                dry_run=args.dry_run,
            )
        except RuntimeError:
            container_image_id_before_discovery = ""
        image_tags = resolve_image_tags(
            args.image_tag or [DEFAULT_PORTAL_IMAGE_TAG],
            args.include_image_tags_matching,
            container_image_id_before_discovery,
            args.dry_run,
        )
        restore_receipt = restore_portal_image(
            expected,
            image_tags,
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
            image_tags,
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
                args.expected_release_channel,
                args.portal_container,
                image_tags[0],
                Path(args.postdeploy_output).expanduser(),
                args.postdeploy_attempts,
                args.postdeploy_retry_delay_seconds,
                browser_proofs,
                args.playwright_timeout_seconds,
                Path(args.playwright_artifact_dir).expanduser() if args.playwright_artifact_dir else None,
                args.dry_run,
            )
    except Exception as error:
        if mutation_lock is not None:
            try:
                release_public_edge_mutation_lock(mutation_lock)
            except OSError as release_error:
                error = RuntimeError(f"{error}; failed to release public-edge mutation lock: {release_error}")
            finally:
                atexit.unregister(release_public_edge_mutation_lock)
        print(str(error), file=sys.stderr)
        return 1

    if mutation_lock is not None:
        try:
            release_public_edge_mutation_lock(mutation_lock)
        except OSError as error:
            print(f"failed to release public-edge mutation lock: {error}", file=sys.stderr)
            return 1
        finally:
            atexit.unregister(release_public_edge_mutation_lock)

    receipt = {
        "contractName": "chummer.public_edge_portal_image_restore.v1",
        "status": "pass",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "restore": restore_receipt,
        "stability": stability_receipt,
        "postdeploy": postdeploy_receipt,
        "browserProofRequirements": browser_proofs,
        "imageTagDiscovery": {
            "containerImageIdBeforeDiscovery": container_image_id_before_discovery,
            "explicitImageTags": args.image_tag or [DEFAULT_PORTAL_IMAGE_TAG],
            "includeImageTagsMatching": args.include_image_tags_matching,
            "runtimeAliasTagsMatchingContainerImage": discover_runtime_alias_tags(
                args.image_tag or [DEFAULT_PORTAL_IMAGE_TAG],
                container_image_id_before_discovery,
                dry_run=args.dry_run,
            ),
            "resolvedImageTags": image_tags,
        },
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
