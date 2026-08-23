#!/usr/bin/env python3
"""Generate a fail-closed receipt for the private Build Ghost nonprod lane.

The attester is deliberately observational.  It may execute the existing
synthetic local canary and the AI container's deterministic fallback endpoint,
but it never enables a provider, creates provider resources, grants external
access, deploys an image, or publishes a route.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence


SCHEMA = "chummer.build_ghost.private_nonprod_deployment_attestation.v1"
PROJECT = "chummer-build-ghost-private-nonprod"
DEPLOYED_STATUS = "deployed-private-nonprod"
BLOCKED_STATUS = "blocked"
FALLBACK_TEXT = "Deterministic private Rook deployment attestation."
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")
SAFE_REASON = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,159}$")
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_COMMAND_BYTES = 2 * 1024 * 1024
MAX_RECEIPT_BYTES = 512 * 1024

SERVICES = {
    "presentation": "chummer-build-ghost-presentation",
    "ai": "chummer-build-ghost-ai",
    "edge": "build-ghost-private-edge",
}
PROVIDER_GATES = (
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED",
)
PRESENTATION_SOURCE_LABELS = {
    "hub": "run.chummer.build-ghost.hub-revision",
    "presentation": "org.opencontainers.image.revision",
    "core": "run.chummer.build-ghost.core-revision",
    "hubRegistry": "run.chummer.build-ghost.hub-registry-revision",
    "uiKit": "run.chummer.build-ghost.ui-kit-revision",
    "mediaFactory": "run.chummer.build-ghost.media-factory-revision",
}
AI_SOURCE_LABELS = {
    "hub": "org.opencontainers.image.revision",
    "core": "run.chummer.build-ghost.core-revision",
    "hubRegistry": "run.chummer.build-ghost.hub-registry-revision",
    "mediaFactory": "run.chummer.build-ghost.media-factory-revision",
}


class AttestationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes


class CommandRunner:
    def run(
        self,
        args: Sequence[str],
        *,
        timeout: int,
        input_bytes: bytes | None = None,
    ) -> CommandResult:
        try:
            result = subprocess.run(
                list(args),
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise AttestationError("bounded command execution failed") from error
        if len(result.stdout) > MAX_COMMAND_BYTES or len(result.stderr) > MAX_COMMAND_BYTES:
            raise AttestationError("bounded command output exceeded the attester limit")
        return CommandResult(result.returncode, result.stdout, result.stderr)


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise AttestationError(f"{label} contains duplicate JSON keys")
            value[key] = item
        return value

    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AttestationError(f"{label} is not canonical UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise AttestationError(f"{label} is not a JSON object")
    return payload


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _digest(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_nlink,
    )


def _source_binding(path: Path, label: str) -> dict[str, Any]:
    if not path.is_absolute() or Path(os.path.normpath(path)) != path:
        raise AttestationError(f"{label} path is not absolute and normalized")
    linked = os.stat(path, follow_symlinks=False)
    if (
        stat.S_ISLNK(linked.st_mode)
        or not stat.S_ISREG(linked.st_mode)
        or linked.st_uid != os.geteuid()
        or linked.st_nlink != 1
        or linked.st_mode & 0o022
        or not 1 <= linked.st_size <= MAX_SOURCE_BYTES
    ):
        raise AttestationError(f"{label} is not a stable caller-owned source")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        before = os.fstat(descriptor)
        if _identity(before) != _identity(linked):
            raise AttestationError(f"{label} changed while opened")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, MAX_SOURCE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_SOURCE_BYTES:
                raise AttestationError(f"{label} exceeded the source size limit")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    rebound = os.stat(path, follow_symlinks=False)
    if _identity(before) != _identity(after) or _identity(after) != _identity(rebound):
        raise AttestationError(f"{label} changed while read")
    raw = b"".join(chunks)
    return {
        "sha256": _digest(raw),
        "sizeBytes": len(raw),
        "mode": f"{stat.S_IMODE(after.st_mode):04o}",
    }


def _add(blockers: list[str], reason: str) -> None:
    normalized = reason.strip().lower().replace(" ", "-")
    if SAFE_REASON.fullmatch(normalized) is None:
        normalized = f"unsafe-reason-{hashlib.sha256(reason.encode('utf-8')).hexdigest()[:16]}"
    if normalized not in blockers:
        blockers.append(normalized)


def _run_text(
    runner: CommandRunner,
    args: Sequence[str],
    *,
    timeout: int,
    label: str,
    input_bytes: bytes | None = None,
) -> str:
    result = runner.run(args, timeout=timeout, input_bytes=input_bytes)
    if result.returncode != 0:
        raise AttestationError(f"{label} command failed")
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AttestationError(f"{label} output was not UTF-8") from error


def _collect_git_source(
    repo_root: Path,
    runner: CommandRunner,
    blockers: list[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {"clean": False, "head": "", "tree": ""}
    try:
        top = _run_text(
            runner,
            ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
            timeout=10,
            label="git top-level",
        ).strip()
        head = _run_text(
            runner,
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            timeout=10,
            label="git HEAD",
        ).strip()
        tree = _run_text(
            runner,
            ["git", "-C", str(repo_root), "rev-parse", "HEAD^{tree}"],
            timeout=10,
            label="git tree",
        ).strip()
        dirty = _run_text(
            runner,
            [
                "git",
                "-C",
                str(repo_root),
                "status",
                "--porcelain=v1",
                "--untracked-files=normal",
            ],
            timeout=15,
            label="git status",
        )
        if Path(top) != repo_root:
            _add(blockers, "attester-repository-root-mismatch")
        if GIT_SHA.fullmatch(head) is None:
            _add(blockers, "attester-source-head-invalid")
        if GIT_SHA.fullmatch(tree) is None:
            _add(blockers, "attester-source-tree-invalid")
        if dirty:
            _add(blockers, "attester-source-not-clean")
        result = {
            "clean": not dirty,
            "head": head if GIT_SHA.fullmatch(head) else "",
            "tree": tree if GIT_SHA.fullmatch(tree) else "",
            "dirtyStateSha256": _digest(dirty.encode("utf-8")),
        }
    except AttestationError:
        _add(blockers, "attester-source-unverifiable")
    return result


def _environment_values(inspect: Mapping[str, Any], name: str) -> list[str]:
    config = inspect.get("Config")
    rows = config.get("Env") if isinstance(config, dict) else None
    if not isinstance(rows, list):
        return []
    prefix = f"{name}="
    return [row[len(prefix) :] for row in rows if isinstance(row, str) and row.startswith(prefix)]


def _docker_object(
    runner: CommandRunner,
    args: Sequence[str],
    label: str,
) -> dict[str, Any]:
    raw = _run_text(runner, args, timeout=30, label=label).encode("utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise AttestationError(f"{label} returned malformed JSON") from error
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise AttestationError(f"{label} returned an ambiguous object set")
    return payload[0]


def _safe_image_projection(
    image: Mapping[str, Any],
    expected_id: str,
    blockers: list[str],
    role: str,
) -> dict[str, Any]:
    image_id = image.get("Id")
    if image_id != expected_id or not isinstance(image_id, str) or SHA256.fullmatch(image_id) is None:
        _add(blockers, f"{role}-image-identity-invalid")
    repo_digests = image.get("RepoDigests")
    if repo_digests is None:
        repo_digests = []
    if not isinstance(repo_digests, list) or not all(isinstance(value, str) for value in repo_digests):
        _add(blockers, f"{role}-image-repo-digests-invalid")
        repo_digests = []
    rootfs = image.get("RootFS")
    layers = rootfs.get("Layers") if isinstance(rootfs, dict) else None
    if not isinstance(layers, list) or not layers or not all(
        isinstance(value, str) and SHA256.fullmatch(value) for value in layers
    ):
        _add(blockers, f"{role}-image-layer-digests-invalid")
        layers = []
    projection = {
        "imageId": image_id if isinstance(image_id, str) else "",
        "repoDigests": sorted(repo_digests),
        "rootFsLayerDigests": layers,
    }
    projection["bindingDigest"] = _digest(_canonical(projection))
    return projection


def _source_labels(
    container: Mapping[str, Any],
    image: Mapping[str, Any],
    mapping: Mapping[str, str],
    blockers: list[str],
    role: str,
) -> dict[str, str]:
    container_config = container.get("Config")
    image_config = image.get("Config")
    container_labels = container_config.get("Labels") if isinstance(container_config, dict) else None
    image_labels = image_config.get("Labels") if isinstance(image_config, dict) else None
    container_labels = container_labels if isinstance(container_labels, dict) else {}
    image_labels = image_labels if isinstance(image_labels, dict) else {}
    result: dict[str, str] = {}
    for public_name, label in mapping.items():
        value = image_labels.get(label)
        if not isinstance(value, str) or GIT_SHA.fullmatch(value) is None:
            _add(blockers, f"{role}-source-label-{public_name.lower()}-invalid")
            value = ""
        if container_labels.get(label) != value:
            _add(blockers, f"{role}-source-label-{public_name.lower()}-drift")
        result[public_name] = value
    return result


def _read_runtime_config_binding(
    path_text: Any,
    label: str,
    blockers: list[str],
) -> dict[str, Any]:
    if not isinstance(path_text, str) or not path_text.startswith("/"):
        _add(blockers, f"{label}-path-invalid")
        return {"pathSha256": "", "sha256": "", "sizeBytes": 0}
    path = Path(os.path.normpath(path_text))
    try:
        binding = _source_binding(path, label)
    except (OSError, AttestationError):
        _add(blockers, f"{label}-unreadable")
        return {"pathSha256": _digest(path_text.encode("utf-8")), "sha256": "", "sizeBytes": 0}
    return {
        "pathSha256": _digest(path_text.encode("utf-8")),
        "sha256": binding["sha256"],
        "sizeBytes": binding["sizeBytes"],
    }


def _collect_runtime(
    runner: CommandRunner,
    blockers: list[str],
    expected_compose_sha: str,
    expected_caddy_sha: str,
    project: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    runtime: dict[str, Any] = {"project": project, "containers": {}, "confinement": {}}
    raw_inspects: dict[str, dict[str, Any]] = {}
    ids: dict[str, str] = {}
    try:
        rows = _run_text(
            runner,
            [
                "docker",
                "ps",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={project}",
                "--format",
                '{{.ID}}\t{{.Label "com.docker.compose.service"}}',
            ],
            timeout=30,
            label="Docker project inventory",
        ).splitlines()
        inventory: dict[str, list[str]] = {}
        for row in rows:
            fields = row.split("\t")
            if len(fields) != 2 or CONTAINER_ID.fullmatch(fields[0]) is None:
                _add(blockers, "runtime-project-inventory-invalid")
                continue
            inventory.setdefault(fields[1], []).append(fields[0])
        if set(inventory) != set(SERVICES.values()):
            _add(blockers, "runtime-project-service-set-invalid")
        for role, service in SERVICES.items():
            candidates = inventory.get(service, [])
            if len(candidates) != 1:
                _add(blockers, f"{role}-running-container-count-invalid")
            else:
                ids[role] = candidates[0]
    except AttestationError:
        _add(blockers, "runtime-project-inventory-unavailable")

    for role, container_id in ids.items():
        try:
            container = _docker_object(
                runner,
                ["docker", "inspect", "--type", "container", container_id],
                f"{role} container inspection",
            )
            raw_inspects[role] = container
            image_id = container.get("Image")
            if not isinstance(image_id, str) or SHA256.fullmatch(image_id) is None:
                _add(blockers, f"{role}-container-image-id-invalid")
                image_id = ""
            image = _docker_object(
                runner,
                ["docker", "image", "inspect", image_id],
                f"{role} image inspection",
            )
            state = container.get("State")
            state = state if isinstance(state, dict) else {}
            if state.get("Running") is not True or state.get("Paused") is True or state.get("Restarting") is True:
                _add(blockers, f"{role}-container-not-stably-running")
            health = state.get("Health")
            health_status = health.get("Status") if isinstance(health, dict) else "none"
            if role in {"presentation", "ai"} and health_status != "healthy":
                _add(blockers, f"{role}-container-not-healthy")
            config = container.get("Config")
            labels = config.get("Labels") if isinstance(config, dict) else None
            labels = labels if isinstance(labels, dict) else {}
            if labels.get("com.docker.compose.project") != project or labels.get(
                "com.docker.compose.service"
            ) != SERVICES[role]:
                _add(blockers, f"{role}-compose-identity-invalid")
            compose_binding = _read_runtime_config_binding(
                labels.get("com.docker.compose.project.config_files"),
                f"{role}-runtime-compose-source",
                blockers,
            )
            compose_binding["matchesAttesterSource"] = compose_binding["sha256"] == expected_compose_sha
            projection: dict[str, Any] = {
                "containerId": f"sha256:{container_id}",
                "image": _safe_image_projection(image, image_id, blockers, role),
                "health": health_status,
                "startedAt": state.get("StartedAt") if isinstance(state.get("StartedAt"), str) else "",
                "composeConfigHash": labels.get("com.docker.compose.config-hash", ""),
                "composeSource": compose_binding,
            }
            if role == "presentation":
                projection["sourceRevisions"] = _source_labels(
                    container, image, PRESENTATION_SOURCE_LABELS, blockers, role
                )
                image_labels = image.get("Config", {}).get("Labels", {})
                if image_labels.get("run.chummer.build-ghost.profile") != "private-nonprod":
                    _add(blockers, "presentation-profile-label-invalid")
                if image_labels.get("run.chummer.build-ghost.packet-store-schema") != "v2":
                    _add(blockers, "presentation-packet-store-schema-label-invalid")
            elif role == "ai":
                projection["sourceRevisions"] = _source_labels(
                    container, image, AI_SOURCE_LABELS, blockers, role
                )
                image_labels = image.get("Config", {}).get("Labels", {})
                if image_labels.get("run.chummer.build-ghost.profile") != "private-nonprod":
                    _add(blockers, "ai-profile-label-invalid")
            runtime["containers"][role] = projection
        except (AttestationError, OSError):
            _add(blockers, f"{role}-runtime-inspection-failed")

    presentation_sources = runtime.get("containers", {}).get("presentation", {}).get("sourceRevisions")
    ai_sources = runtime.get("containers", {}).get("ai", {}).get("sourceRevisions")
    if isinstance(presentation_sources, dict) and isinstance(ai_sources, dict):
        for key in ("hub", "core", "hubRegistry", "mediaFactory"):
            if presentation_sources.get(key) != ai_sources.get(key):
                _add(blockers, f"cross-image-source-{key.lower()}-drift")

    private_network = f"{project}_build-ghost-private"
    loopback_network = f"{project}_build-ghost-loopback"
    confinement: dict[str, Any] = {
        "privateNetwork": private_network,
        "loopbackNetwork": loopback_network,
        "edgePublishedBindings": [],
        "loopbackOnly": False,
    }
    runtime["confinement"] = confinement
    if set(ids) == set(SERVICES):
        try:
            private = _docker_object(
                runner,
                ["docker", "network", "inspect", private_network],
                "private Docker network inspection",
            )
            loopback = _docker_object(
                runner,
                ["docker", "network", "inspect", loopback_network],
                "loopback Docker network inspection",
            )
            private_members = set((private.get("Containers") or {}).keys())
            loopback_members = set((loopback.get("Containers") or {}).keys())
            if private.get("Internal") is not True:
                _add(blockers, "private-network-not-internal")
            if private_members != set(ids.values()):
                _add(blockers, "private-network-member-set-invalid")
            if loopback_members != {ids["edge"]}:
                _add(blockers, "loopback-network-member-set-invalid")
            for role in ("presentation", "ai"):
                inspect = raw_inspects.get(role, {})
                networks = inspect.get("NetworkSettings", {}).get("Networks", {})
                if set(networks) != {private_network}:
                    _add(blockers, f"{role}-network-confinement-invalid")
                bindings = inspect.get("HostConfig", {}).get("PortBindings")
                if bindings not in ({}, None):
                    _add(blockers, f"{role}-published-port-present")
            edge = raw_inspects.get("edge", {})
            edge_networks = edge.get("NetworkSettings", {}).get("Networks", {})
            if set(edge_networks) != {private_network, loopback_network}:
                _add(blockers, "edge-network-confinement-invalid")
            bindings = edge.get("HostConfig", {}).get("PortBindings")
            valid_bindings = False
            if isinstance(bindings, dict) and set(bindings) == {"443/tcp"}:
                rows = bindings.get("443/tcp")
                valid_bindings = (
                    isinstance(rows, list)
                    and len(rows) == 1
                    and isinstance(rows[0], dict)
                    and rows[0].get("HostIp") == "127.0.0.1"
                    and isinstance(rows[0].get("HostPort"), str)
                    and rows[0]["HostPort"].isdigit()
                    and 1 <= int(rows[0]["HostPort"]) <= 65535
                )
                if valid_bindings:
                    confinement["edgePublishedBindings"] = [
                        {
                            "containerPort": "443/tcp",
                            "hostIp": "127.0.0.1",
                            "hostPort": int(rows[0]["HostPort"]),
                        }
                    ]
            if not valid_bindings:
                _add(blockers, "edge-published-binding-not-loopback-only")
            mounts = edge.get("Mounts")
            caddy_mounts = [
                row
                for row in mounts if isinstance(row, dict) and row.get("Destination") == "/etc/caddy/Caddyfile"
            ] if isinstance(mounts, list) else []
            if (
                len(caddy_mounts) != 1
                or caddy_mounts[0].get("RW") is not False
                or caddy_mounts[0].get("Type") != "bind"
            ):
                _add(blockers, "edge-caddy-source-mount-invalid")
                caddy_binding = {"pathSha256": "", "sha256": "", "sizeBytes": 0}
            else:
                caddy_binding = _read_runtime_config_binding(
                    caddy_mounts[0].get("Source"), "edge-runtime-caddy-source", blockers
                )
            caddy_binding["matchesAttesterSource"] = caddy_binding["sha256"] == expected_caddy_sha
            confinement["caddySource"] = caddy_binding
            if not caddy_binding["matchesAttesterSource"]:
                _add(blockers, "edge-runtime-caddy-source-drift")
            confinement["privateNetworkInternal"] = private.get("Internal") is True
            confinement["privateNetworkId"] = private.get("Id", "")
            confinement["loopbackNetworkId"] = loopback.get("Id", "")
            confinement["loopbackOnly"] = valid_bindings
        except (AttestationError, OSError):
            _add(blockers, "runtime-network-inspection-failed")

    ai_inspect = raw_inspects.get("ai")
    gates: dict[str, bool | None] = {}
    if ai_inspect is None:
        for gate in PROVIDER_GATES:
            gates[gate] = None
            _add(blockers, f"provider-gate-{gate.lower()}-unverifiable")
    else:
        for gate in PROVIDER_GATES:
            values = _environment_values(ai_inspect, gate)
            literal_false = values == ["false"]
            gates[gate] = False if literal_false else None
            if not literal_false:
                _add(blockers, f"provider-gate-{gate.lower()}-not-literal-false")
        required_ai = {
            "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_TRANSPORT_MODE": "provider-body-key-v2",
            "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_ENDPOINT": "https://canary.chummer.run/api/v2/ai/build-ghost/tool",
            "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_AUTHORITY_ENDPOINT": "https://presentation.canary.chummer.run/api/internal/build-ghost/tool/resolve",
        }
        for name, expected in required_ai.items():
            if _environment_values(ai_inspect, name) != [expected]:
                _add(blockers, f"ai-runtime-contract-{name.lower()}-invalid")
    presentation_inspect = raw_inspects.get("presentation")
    if presentation_inspect is not None:
        if _environment_values(
            presentation_inspect, "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_DEPLOYMENT_ENABLED"
        ) != ["true"]:
            _add(blockers, "presentation-private-tool-deployment-not-literal-true")
        if _environment_values(
            presentation_inspect, "CHUMMER_BUILD_GHOST_PACKET_ACCESS_STORE_ROOT"
        ) != ["/app/state/build-ghost-packet-access"]:
            _add(blockers, "presentation-packet-store-root-invalid")
    runtime["providerGates"] = {
        "allLiteralFalse": all(value is False for value in gates.values()),
        "values": gates,
    }
    runtime["bindingDigest"] = _digest(_canonical(runtime))
    return runtime, raw_inspects


PACKET_STORE_COMMAND = r'''set -eu
root=/app/state/build-ghost-packet-access
test -d "$root"
test ! -L "$root"
for name in pending claims audit revocations; do
  test -d "$root/$name"
  test ! -L "$root/$name"
done
test -f "$root/state-authority.v2.json"
test ! -L "$root/state-authority.v2.json"
grep -Eq '"schema"[[:space:]]*:[[:space:]]*"chummer\.build_ghost\.packet_access_store_authority\.v2"' "$root/state-authority.v2.json"
pending=$(find "$root/pending" -mindepth 1 -maxdepth 1 -print | wc -l | tr -d ' ')
claims=$(find "$root/claims" -mindepth 1 -maxdepth 1 -print | wc -l | tr -d ' ')
audit=$(find "$root/audit" -mindepth 1 -maxdepth 1 -type f -name '*.json' | wc -l | tr -d ' ')
revocations=$(find "$root/revocations" -mindepth 1 -maxdepth 1 -type f -name '*.json' | wc -l | tr -d ' ')
printf '{"authority":"v2","pending":%s,"claims":%s,"audit":%s,"revocations":%s}\n' "$pending" "$claims" "$audit" "$revocations"
'''


def _packet_store_state(
    runner: CommandRunner,
    presentation_id: str,
    blockers: list[str],
    phase: str,
) -> dict[str, Any]:
    fallback = {"authority": "unverified", "pending": -1, "claims": -1, "audit": -1, "revocations": -1}
    try:
        result = runner.run(
            ["docker", "exec", presentation_id, "sh", "-c", PACKET_STORE_COMMAND],
            timeout=30,
        )
        if result.returncode != 0 or result.stderr:
            raise AttestationError("packet store inspection failed")
        payload = _json_object(result.stdout, f"{phase} packet store state")
        if set(payload) != {"authority", "pending", "claims", "audit", "revocations"}:
            raise AttestationError("packet store state fields changed")
        if payload.get("authority") != "v2" or any(
            not isinstance(payload.get(name), int) or payload[name] < 0
            for name in ("pending", "claims", "audit", "revocations")
        ):
            raise AttestationError("packet store state values are invalid")
        if payload["pending"] != 0:
            _add(blockers, f"packet-store-{phase}-pending-not-zero")
        if payload["claims"] != 0:
            _add(blockers, f"packet-store-{phase}-claims-not-zero")
        return payload
    except AttestationError:
        _add(blockers, f"packet-store-{phase}-unverifiable")
        return fallback


CANARY_EXPECTED = {
    "positive_canary": "passed",
    "legacy_unknown_key": "410",
    "legacy_wrong_contract": "401",
    "legacy_unknown_field": "400",
    "provider_unknown_key": "410",
    "provider_wrong_contract": "401",
    "provider_ambiguous_auth": "401",
    "provider_unknown_field": "400",
    "provider_noncanonical_key": "400",
    "neighbor": "404",
    "presentation_neighbor": "404",
    "import": "200",
    "cross_owner": "503",
    "grant": "200",
    "grant_cache": "no-store",
    "tool": "200",
    "replay": "410",
    "revoked": "410",
    "terminal_equivalent": "true",
    "auth": "packet-access-key-body-v2",
    "schema": "chummer.build_ghost_analysis.v1",
    "locale": "en-US",
    "cache": "no-store",
    "pending_grants": "0",
    "active_claims": "0",
    "gates": "false",
    "cleanup": "404",
}


def _run_packet_canary(
    runner: CommandRunner,
    path: Path,
    timeout: int,
    blockers: list[str],
) -> dict[str, Any]:
    try:
        result = runner.run(["bash", str(path)], timeout=timeout)
    except AttestationError:
        _add(blockers, "packet-canary-command-unavailable")
        return {"passed": False, "exitCode": None}
    projection: dict[str, Any] = {
        "passed": False,
        "stdoutSha256": _digest(result.stdout),
        "stderrSha256": _digest(result.stderr),
        "exitCode": result.returncode,
    }
    if result.returncode != 0:
        text = result.stdout.decode("utf-8", errors="replace")
        stage_match = re.search(r"(?:^|\s)stage=([a-z0-9-]+)(?:\s|$)", text)
        stage = stage_match.group(1) if stage_match else "unknown"
        _add(blockers, f"packet-canary-failed:{stage}")
        return projection
    if result.stderr:
        _add(blockers, "packet-canary-unexpected-stderr")
        return projection
    try:
        lines = [line for line in result.stdout.decode("utf-8").splitlines() if line]
        if len(lines) != 1:
            raise AttestationError("packet canary output line count changed")
        tokens: dict[str, str] = {}
        for token in shlex.split(lines[0]):
            key, separator, value = token.partition("=")
            if not separator or key in tokens:
                raise AttestationError("packet canary output was ambiguous")
            tokens[key] = value
        if any(tokens.get(key) != value for key, value in CANARY_EXPECTED.items()):
            raise AttestationError("packet canary semantic contract failed")
        characters = int(tokens.get("characters", "-1"))
        ttl = int(tokens.get("ttl_seconds", "-1"))
        audit = int(tokens.get("audit_records", "-1"))
        revocations = int(tokens.get("revocation_markers", "-1"))
        if not 1 <= characters <= 15000 or not 1 <= ttl <= 300 or audit < 4 or revocations < 1:
            raise AttestationError("packet canary bounded values failed")
        projection.update(
            {
                "passed": True,
                "transport": tokens["auth"],
                "analysisSchema": tokens["schema"],
                "terminalReplayAndRevocationEquivalent": True,
                "providerGatesLiteralFalse": True,
                "pendingGrants": 0,
                "activeClaims": 0,
                "auditRecordCount": audit,
                "revocationMarkerCount": revocations,
            }
        )
    except (AttestationError, UnicodeDecodeError, ValueError):
        _add(blockers, "packet-canary-output-invalid")
    return projection


def _fallback_request(now: dt.datetime) -> tuple[dict[str, Any], str, str]:
    timestamp = now.astimezone(dt.timezone.utc).replace(microsecond=0)
    nonce = hashlib.sha256(timestamp.isoformat().encode("utf-8")).hexdigest()[:20]
    request_id = f"attest-{timestamp.strftime('%Y%m%dt%H%M%Sz')}-{nonce}"
    packet: dict[str, Any] = {
        "schema": "chummer.build_ghost_analysis.v1",
        "personaId": "build-ghost-rook-v1",
        "avatarId": "build-ghost-rook-avatar-v1",
        "voiceId": "build-ghost-rook-voice-v1",
        "packetDigest": "",
        "locale": "en-US",
        "supportedLocales": ["en-US"],
        "localeFallbackChain": ["en-US"],
        "workspaceId": "synthetic-deployment-attestation",
        "workspaceRevision": 1,
        "runner": {"facts": []},
        "optimizationStrategies": [],
        "ruleExplanations": [],
        "variants": [],
        "groupCapabilityPosture": {"visibilityPosture": "hidden", "visibleMembers": []},
        "sourceAnchors": [],
        "allowedSuggestedActions": [],
    }
    packet_digest = _digest(_canonical(packet))
    packet["packetDigest"] = packet_digest
    packet_json = _canonical(packet).decode("utf-8")
    request = {
        "schema": "chummer.tough_tongue.build_ghost_request.v1",
        "requestId": request_id,
        "ownerScopeHash": _digest(f"{PROJECT}:{request_id}".encode("utf-8")),
        "packetDigest": packet_digest,
        "locale": "en-US",
        "analysisPacketJson": packet_json,
        "deterministicFallbackText": FALLBACK_TEXT,
        "idempotencyKey": f"attest:{request_id}:1",
        "requestedAtUtc": timestamp.isoformat().replace("+00:00", "Z"),
    }
    return request, request_id, packet_digest


def _run_fallback_canary(
    runner: CommandRunner,
    ai_inspect: Mapping[str, Any],
    now: dt.datetime,
    blockers: list[str],
) -> dict[str, Any]:
    projection: dict[str, Any] = {
        "passed": False,
        "usedDeterministicFallback": False,
        "remoteExecutionEnabled": None,
        "remoteAttempted": None,
    }
    container_id = ai_inspect.get("Id")
    if not isinstance(container_id, str) or CONTAINER_ID.fullmatch(container_id) is None:
        _add(blockers, "fallback-canary-ai-container-id-invalid")
        return projection
    tokens = _environment_values(ai_inspect, "CHUMMER_AI_INTERNAL_API_TOKEN")
    if len(tokens) != 1 or len(tokens[0].encode("utf-8")) < 32:
        _add(blockers, "fallback-canary-internal-auth-unavailable")
        return projection
    request, request_id, packet_digest = _fallback_request(now)
    body = _canonical(request)
    args = [
        "docker",
        "exec",
        "-i",
        container_id,
        "curl",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "5",
        "--max-time",
        "20",
        "--output",
        "-",
        "--write-out",
        "\n%{http_code}",
        "--header",
        "@-",
        "--header",
        "Content-Type: application/json",
        "--data-binary",
        body.decode("utf-8"),
        "http://127.0.0.1:8080/api/v1/ai/build-ghost/explain",
    ]
    header_input = f"Authorization: Bearer {tokens[0]}\n".encode("utf-8")
    try:
        result = runner.run(args, timeout=30, input_bytes=header_input)
    except AttestationError:
        _add(blockers, "fallback-canary-request-failed")
        return projection
    finally:
        tokens[0] = ""
        header_input = b""
    projection["responseSha256"] = _digest(result.stdout)
    if result.returncode != 0 or result.stderr:
        _add(blockers, "fallback-canary-request-failed")
        return projection
    response_raw, separator, status_raw = result.stdout.rpartition(b"\n")
    if not separator or status_raw != b"200":
        _add(blockers, "fallback-canary-status-invalid")
        return projection
    try:
        response = _json_object(response_raw, "fallback canary response")
        receipt = response.get("receipt")
        if not isinstance(receipt, dict):
            raise AttestationError("fallback canary receipt missing")
        valid = (
            response.get("usedDeterministicFallback") is True
            and response.get("safeText") == FALLBACK_TEXT
            and response.get("providerAnswer") is None
            and receipt.get("requestId") == request_id
            and receipt.get("packetDigest") == packet_digest
            and receipt.get("remoteExecutionEnabled") is False
            and receipt.get("remoteAttempted") is False
            and receipt.get("fallbackReason") == "remote-disabled"
            and isinstance(receipt.get("validationReasons"), list)
            and "remote-execution-disabled-by-default" in receipt["validationReasons"]
        )
        if not valid:
            raise AttestationError("fallback canary semantics changed")
        projection.update(
            {
                "passed": True,
                "requestDigest": _digest(body),
                "packetDigest": packet_digest,
                "usedDeterministicFallback": True,
                "safeTextDigest": _digest(FALLBACK_TEXT.encode("utf-8")),
                "remoteExecutionEnabled": False,
                "remoteAttempted": False,
                "fallbackReason": "remote-disabled",
            }
        )
    except AttestationError:
        _add(blockers, "fallback-canary-response-invalid")
    return projection


def _parse_timestamp(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _probe_team_truth(
    runner: CommandRunner,
    live_ops: Path,
    timeout: int,
    max_age_seconds: int,
    clock: Callable[[], dt.datetime],
    blockers: list[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema": "",
        "fresh": False,
        "redacted": False,
        "ready": False,
        "status": BLOCKED_STATUS,
        "blockers": [],
    }
    with tempfile.TemporaryDirectory(prefix="chummer-build-ghost-team-truth-") as directory:
        receipt_path = Path(directory) / "tough-tongue-binding-receipt.json"
        try:
            result = runner.run(
                [
                    sys.executable,
                    str(live_ops),
                    "probe-tough-tongue-bindings",
                    "--format",
                    "json",
                    "--receipt-path",
                    str(receipt_path),
                    "--timeout-seconds",
                    str(timeout),
                ],
                timeout=timeout + 15,
            )
        except AttestationError:
            _add(blockers, "tough-tongue-live-ops-probe-unavailable")
            return summary
        if result.returncode != 0:
            _add(blockers, "tough-tongue-live-ops-probe-failed")
        try:
            receipt_raw = receipt_path.read_bytes()
            if not 1 <= len(receipt_raw) <= MAX_RECEIPT_BYTES:
                raise AttestationError("Tough Tongue receipt size invalid")
            metadata = os.stat(receipt_path, follow_symlinks=False)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
            ):
                raise AttestationError("Tough Tongue receipt is not owner-only")
            payload = _json_object(receipt_raw, "Tough Tongue live-ops receipt")
            stdout_payload = _json_object(result.stdout, "Tough Tongue live-ops stdout")
            if _canonical(payload) != _canonical(stdout_payload):
                raise AttestationError("Tough Tongue receipt and stdout disagree")
        except (OSError, AttestationError):
            _add(blockers, "tough-tongue-redacted-receipt-unverifiable")
            return summary

        activation = payload.get("provider_activation")
        requests = payload.get("requests")
        raw_safe = all(
            payload.get(name) is False
            for name in (
                "raw_account_identifiers_exposed",
                "raw_candidate_identifiers_exposed",
                "raw_credentials_exposed",
            )
        )
        activation_safe = isinstance(activation, dict) and activation and all(
            value is False for value in activation.values()
        )
        request_safe = (
            isinstance(requests, dict)
            and requests.get("mutation_request_count") == 0
            and requests.get("response_bodies_persisted") is False
            and isinstance(requests.get("methods"), list)
            and all(method == "GET" for method in requests["methods"])
        )
        if not raw_safe:
            _add(blockers, "tough-tongue-live-ops-receipt-not-redacted")
        if not activation_safe:
            _add(blockers, "tough-tongue-live-ops-provider-activation-observed")
        if not request_safe or payload.get("probe_mode") != "strict_read_only_get":
            _add(blockers, "tough-tongue-live-ops-probe-not-read-only")
        generated = _parse_timestamp(payload.get("generated_at"))
        observed_at = clock().astimezone(dt.timezone.utc)
        age = (observed_at - generated).total_seconds() if generated else None
        fresh = age is not None and -5 <= age <= max_age_seconds
        if not fresh:
            _add(blockers, "tough-tongue-live-ops-receipt-not-fresh")

        upstream = payload.get("blockers")
        upstream = upstream if isinstance(upstream, list) else []
        safe_upstream: list[str] = []
        for reason in upstream:
            if isinstance(reason, str) and SAFE_REASON.fullmatch(reason):
                safe_upstream.append(reason)
                _add(blockers, f"tough-tongue:{reason}")
            else:
                _add(blockers, "tough-tongue:unsafe-upstream-blocker")
        accounts = payload.get("accounts") if isinstance(payload.get("accounts"), dict) else {}
        bindings = payload.get("bindings") if isinstance(payload.get("bindings"), dict) else {}
        entitlements = payload.get("entitlements") if isinstance(payload.get("entitlements"), dict) else {}
        ownership = payload.get("ownership") if isinstance(payload.get("ownership"), dict) else {}
        contract = payload.get("contract") if isinstance(payload.get("contract"), dict) else {}
        account_count = accounts.get("configured_count")
        distinct_count = accounts.get("distinct_count")
        ready = (
            payload.get("schema") == "ea.tough_tongue.read_only_binding_receipt.v1"
            and payload.get("provider_key") == "tough_tongue"
            and payload.get("probe_ok") is True
            and payload.get("ready") is True
            and payload.get("status") in {"ready", "pass", "passed"}
            and not safe_upstream
            and isinstance(account_count, int)
            and 3 <= account_count <= 32
            and distinct_count == account_count
            and accounts.get("preferred_account_ref_valid") is True
            and accounts.get("preferred_match_count") == 1
            and accounts.get("preferred_ownership_verified") is True
            and entitlements.get("premium_verified") is True
            and entitlements.get("live_avatar_verified") is True
            and ownership.get("account_verified") is True
            and ownership.get("organization_verified") is True
            and ownership.get("all_candidate_resources_verified") is True
            and contract.get("configured") is True
            and contract.get("verified") is True
            and contract.get("methods") == ["GET"]
            and requests.get("attempted_count", 0) > 0
            and requests.get("methods") == ["GET"]
            and isinstance(bindings, dict)
            and set(bindings) == {"agent", "voice", "function", "scenario"}
            and all(
                isinstance(value, dict)
                and value.get("configured") is True
                and value.get("readback") is True
                and value.get("reference_match") is True
                and value.get("account_owner_match") is True
                and value.get("organization_owner_match") is True
                for value in bindings.values()
            )
        )
        if not ready:
            _add(blockers, "tough-tongue-team-account-truth-not-ready")
        summary = {
            "schema": payload.get("schema", ""),
            "fresh": fresh,
            "generatedAt": payload.get("generated_at", ""),
            "ageSeconds": int(age) if age is not None else None,
            "redacted": raw_safe,
            "strictReadOnlyGet": request_safe and payload.get("probe_mode") == "strict_read_only_get",
            "providerMutationObserved": not activation_safe,
            "ready": ready,
            "status": payload.get("status", BLOCKED_STATUS),
            "source": payload.get("source", ""),
            "configuredAccountCount": accounts.get("configured_count"),
            "distinctAccountCount": accounts.get("distinct_count"),
            "preferredAccountConfigured": accounts.get("preferred_account_ref_configured"),
            "preferredAccountOwnershipVerified": accounts.get("preferred_ownership_verified"),
            "premiumVerified": entitlements.get("premium_verified"),
            "liveAvatarVerified": entitlements.get("live_avatar_verified"),
            "organizationOwnershipVerified": ownership.get("organization_verified"),
            "candidateResourcesOwnershipVerified": ownership.get("all_candidate_resources_verified"),
            "probeRequestCount": requests.get("attempted_count") if isinstance(requests, dict) else None,
            "probeMutationRequestCount": requests.get("mutation_request_count") if isinstance(requests, dict) else None,
            "upstreamEvidenceDigest": payload.get("evidence_digest", ""),
            "upstreamReceiptDigest": payload.get("receipt_digest", ""),
            "receiptFileSha256": _digest(receipt_raw),
            "blockers": sorted(set(safe_upstream)),
        }
        return summary


def _write_new_receipt(path: Path, payload: Mapping[str, Any]) -> None:
    if not path.is_absolute() or Path(os.path.normpath(path)) != path:
        raise AttestationError("output path must be absolute and normalized")
    parent = os.stat(path.parent, follow_symlinks=False)
    if (
        not stat.S_ISDIR(parent.st_mode)
        or stat.S_ISLNK(parent.st_mode)
        or parent.st_uid != os.geteuid()
        or stat.S_IMODE(parent.st_mode) & 0o077
    ):
        raise AttestationError("output parent must be caller-owned and mode 0700")
    raw = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise AttestationError("attestation receipt exceeded its size limit")
    parent_fd = os.open(
        path.parent,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        descriptor = os.open(
            path.name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        try:
            os.fchmod(descriptor, 0o600)
            offset = 0
            while offset < len(raw):
                written = os.write(descriptor, raw[offset:])
                if written <= 0:
                    raise AttestationError("short write while publishing attestation")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def attest(
    *,
    repo_root: Path,
    output: Path,
    canary: Path,
    live_ops: Path,
    project: str = PROJECT,
    canary_timeout: int = 900,
    live_ops_timeout: int = 30,
    team_truth_max_age: int = 120,
    runner: CommandRunner | None = None,
    clock: Callable[[], dt.datetime] | None = None,
) -> dict[str, Any]:
    runner = runner or CommandRunner()
    clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
    blockers: list[str] = []

    source_paths = {
        "attester": Path(__file__).resolve(),
        "packetCanary": canary,
        "compose": repo_root / "docker-compose.build-ghost-private-nonprod.yml",
        "caddy": repo_root / "ops" / "build-ghost-private-nonprod" / "Caddyfile",
        "eaLiveOps": live_ops,
    }
    sources: dict[str, Any] = {}
    for name, path in source_paths.items():
        try:
            sources[name] = _source_binding(path, name)
        except (OSError, AttestationError):
            sources[name] = {"sha256": "", "sizeBytes": 0, "mode": ""}
            _add(blockers, f"source-{name.lower()}-unverifiable")
    sources["git"] = _collect_git_source(repo_root, runner, blockers)

    team_truth = _probe_team_truth(
        runner,
        live_ops,
        live_ops_timeout,
        team_truth_max_age,
        clock,
        blockers,
    )

    runtime_blockers_before = len(blockers)
    runtime_before, raw_before = _collect_runtime(
        runner,
        blockers,
        sources["compose"]["sha256"],
        sources["caddy"]["sha256"],
        project,
    )
    runtime_added_blockers = blockers[runtime_blockers_before:]
    presentation_id = raw_before.get("presentation", {}).get("Id", "")
    packet_before = _packet_store_state(runner, presentation_id, blockers, "before") \
        if presentation_id else {"authority": "unverified", "pending": -1, "claims": -1, "audit": -1, "revocations": -1}
    if not presentation_id:
        _add(blockers, "packet-store-before-unverifiable")

    safe_for_canary = (
        not runtime_added_blockers
        and packet_before.get("pending") == 0
        and packet_before.get("claims") == 0
        and packet_before.get("authority") == "v2"
    )
    if safe_for_canary:
        packet_canary = _run_packet_canary(runner, canary, canary_timeout, blockers)
        fallback_canary = _run_fallback_canary(
            runner, raw_before["ai"], clock().astimezone(dt.timezone.utc), blockers
        )
    else:
        _add(blockers, "canaries-skipped-unsafe-runtime")
        packet_canary = {"passed": False, "skipped": True}
        fallback_canary = {
            "passed": False,
            "skipped": True,
            "usedDeterministicFallback": False,
            "remoteExecutionEnabled": None,
            "remoteAttempted": None,
        }

    packet_after = _packet_store_state(runner, presentation_id, blockers, "after") \
        if presentation_id else {"authority": "unverified", "pending": -1, "claims": -1, "audit": -1, "revocations": -1}
    runtime_after, _ = _collect_runtime(
        runner,
        blockers,
        sources["compose"]["sha256"],
        sources["caddy"]["sha256"],
        project,
    )
    if _canonical(runtime_before) != _canonical(runtime_after):
        _add(blockers, "runtime-identity-drift-during-attestation")

    for name, path in source_paths.items():
        try:
            rebound = _source_binding(path, name)
            if rebound != sources[name]:
                _add(blockers, f"source-{name.lower()}-drift-during-attestation")
        except (OSError, AttestationError):
            _add(blockers, f"source-{name.lower()}-drift-during-attestation")

    blockers = sorted(set(blockers))
    status = DEPLOYED_STATUS if not blockers else BLOCKED_STATUS
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "generatedAt": clock()
        .astimezone(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "status": status,
        "claim": DEPLOYED_STATUS if status == DEPLOYED_STATUS else None,
        "project": project,
        "providerActivationAuthorized": False,
        "externalMutationPerformed": False,
        "sources": sources,
        "runtime": runtime_after,
        "runtimeStableDuringAttestation": _canonical(runtime_before) == _canonical(runtime_after),
        "packetStore": {"before": packet_before, "after": packet_after},
        "canaries": {
            "packetAccessAndGrounding": packet_canary,
            "deterministicNoProviderFallback": fallback_canary,
        },
        "toughTongueTeamAccountTruth": team_truth,
        "blockers": blockers,
        "evidenceDigestContract": "sha256-canonical-json-without-evidenceDigest",
    }
    payload["evidenceDigest"] = _digest(_canonical(payload))
    _write_new_receipt(output, payload)
    return payload


def _arguments() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Generate a fail-closed Build Ghost private nonprod deployment attestation."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--canary",
        type=Path,
        default=repo_root / "ops" / "build-ghost-private-nonprod" / "run-local-canary.sh",
    )
    parser.add_argument(
        "--ea-live-ops",
        type=Path,
        default=Path("/docker/EA/scripts/ea_live_ops.py"),
    )
    parser.add_argument("--project", default=PROJECT)
    parser.add_argument("--canary-timeout-seconds", type=int, default=900)
    parser.add_argument("--live-ops-timeout-seconds", type=int, default=30)
    parser.add_argument("--team-truth-max-age-seconds", type=int, default=120)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if (
        not 30 <= args.canary_timeout_seconds <= 900
        or not 5 <= args.live_ops_timeout_seconds <= 120
        or not 30 <= args.team_truth_max_age_seconds <= 300
        or not SAFE_REASON.fullmatch(args.project)
    ):
        print("build_ghost_private_nonprod_attestation=failed stage=arguments", file=sys.stderr)
        return 2
    try:
        payload = attest(
            repo_root=args.repo_root.resolve(),
            output=args.output,
            canary=args.canary.resolve(),
            live_ops=args.ea_live_ops.resolve(),
            project=args.project,
            canary_timeout=args.canary_timeout_seconds,
            live_ops_timeout=args.live_ops_timeout_seconds,
            team_truth_max_age=args.team_truth_max_age_seconds,
        )
    except (OSError, AttestationError) as error:
        print(
            "build_ghost_private_nonprod_attestation=failed stage=receipt-materialization",
            file=sys.stderr,
        )
        return 2
    print(
        "build_ghost_private_nonprod_attestation="
        f"{payload['status']} evidence_digest={payload['evidenceDigest']} "
        f"blockers={len(payload['blockers'])}"
    )
    return 0 if payload["status"] == DEPLOYED_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
