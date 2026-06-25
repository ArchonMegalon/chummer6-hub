#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


CONTRACT_NAME = "chummer.origin_edition.portal_publication_index_preflight.v1"
DEFAULT_CONTAINER = "chummer6-hub-chummer-portal-1"
DEFAULT_EXPECTED_INDEX = "/app/state/origin-dossier-publications.json"
DEFAULT_HOST_STATE_ROOT = Path("/var/lib/docker/volumes/chummer6-hub_chummer-run-api-state/_data")
DEFAULT_OUTPUT = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold/origin.chummer.run/Varga/Mira/Kestrel/portal-publication-index-preflight.receipt.json")


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_text(value: object) -> str:
    text = str(value or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_inspect(container: str, inspect_file: Path | None) -> dict[str, Any]:
    if inspect_file:
        parsed = json.loads(inspect_file.read_text(encoding="utf-8"))
        return parsed[0] if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict) else parsed
    try:
        completed = subprocess.run(["docker", "inspect", container], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError):
        return {}
    parsed = json.loads(completed.stdout)
    return parsed[0] if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict) else {}


def env_map(inspect_payload: dict[str, Any]) -> dict[str, str]:
    config = inspect_payload.get("Config") if isinstance(inspect_payload.get("Config"), dict) else {}
    values: dict[str, str] = {}
    for item in config.get("Env") if isinstance(config.get("Env"), list) else []:
        text = str(item)
        if "=" in text:
            key, value = text.split("=", 1)
            values[key] = value
    return values


def mount_summary(inspect_payload: dict[str, Any]) -> list[dict[str, str]]:
    mounts = inspect_payload.get("Mounts") if isinstance(inspect_payload.get("Mounts"), list) else []
    return [
        {
            "destination": str(mount.get("Destination") or ""),
            "type": str(mount.get("Type") or ""),
            "name": str(mount.get("Name") or ""),
            "sourceSha256": sha256_text(mount.get("Source") or ""),
        }
        for mount in mounts
        if isinstance(mount, dict)
    ]


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def materialize(
    output: Path,
    *,
    container: str = DEFAULT_CONTAINER,
    expected_index: str = DEFAULT_EXPECTED_INDEX,
    host_state_root: Path = DEFAULT_HOST_STATE_ROOT,
    inspect_file: Path | None = None,
    compose_file: Path = Path("docker-compose.public-edge.yml"),
    env_example: Path = Path(".env.example"),
) -> dict[str, Any]:
    inspect_payload = load_inspect(container, inspect_file)
    env = env_map(inspect_payload)
    mounts = mount_summary(inspect_payload)
    running_index = env.get("CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX", "")
    host_index = host_state_root / Path(expected_index).name
    state_mount_present = any(mount["destination"] == "/app/state" for mount in mounts)
    host_index_present = host_index.is_file()
    host_index_nonempty = host_index_present and host_index.stat().st_size > 0
    compose_configured = "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX" in text(compose_file) and expected_index in text(compose_file)
    env_example_configured = "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX" in text(env_example)
    running_matches = running_index == expected_index
    restart_required = host_index_nonempty and state_mount_present and not running_matches
    blockers: list[str] = []
    if not inspect_payload:
        blockers.append("portal_container_inspect_unavailable")
    if not running_index:
        blockers.append("running_portal_publication_index_env_missing")
    elif not running_matches:
        blockers.append("running_portal_publication_index_env_unexpected")
    if not state_mount_present:
        blockers.append("portal_state_mount_missing")
    if not host_index_present:
        blockers.append("host_publication_index_missing")
    elif not host_index_nonempty:
        blockers.append("host_publication_index_empty")
    if not compose_configured:
        blockers.append("compose_publication_index_env_missing")
    if not env_example_configured:
        blockers.append("env_example_publication_index_missing")
    passed = running_matches and state_mount_present and host_index_nonempty
    payload = {
        "contractName": CONTRACT_NAME,
        "generatedAtUtc": now_iso(),
        "updated_at": now_iso(),
        "status": "pass" if passed else "blocked",
        "goalCompletionClaimAllowed": False,
        "deploymentPerformed": False,
        "expectedContainerPublicationIndex": expected_index,
        "restartRequiredForExistingContainer": restart_required,
        "blockers": blockers,
        "blocking_reason": "" if passed else ",".join(blockers),
        "next_action": "Portal publication index is active in the running container; rerun deployed browser proof." if passed else "Restart/recreate chummer-portal only after explicit deploy approval so CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX=/app/state/origin-dossier-publications.json is active." if restart_required else "Resolve portal publication-index preflight blockers before claiming deployed Origin Edition Gold.",
        "runningContainer": {
            "inspectAvailable": bool(inspect_payload),
            "publicationIndexEnvPresent": bool(running_index),
            "publicationIndexEnvMatchesExpected": running_matches,
            "publicationIndexValueSha256": sha256_text(running_index),
            "envValueStoredInReceipt": False,
            "stateMountPresent": state_mount_present,
            "mounts": mounts,
        },
        "expectedHostPublicationIndex": {
            "pathSha256": sha256_text(host_index.as_posix()),
            "present": host_index_present,
            "nonempty": host_index_nonempty,
            "sha256": sha256_file(host_index) if host_index_nonempty else "",
            "pathStoredInReceipt": False,
        },
        "configFiles": {
            "compose": {"present": compose_file.is_file(), "publicationIndexConfigured": compose_configured, "pathSha256": sha256_text(compose_file.as_posix())},
            "envExample": {"present": env_example.is_file(), "keyPresent": env_example_configured, "valueStoredInReceipt": False, "pathSha256": sha256_text(env_example.as_posix())},
        },
        "privacy": {"rawCredentialExposed": False, "rawEnvValueExposed": False, "deploymentPerformed": False},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only preflight for deployed Chummer Origin publication index.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--expected-index", default=DEFAULT_EXPECTED_INDEX)
    parser.add_argument("--host-state-root", type=Path, default=DEFAULT_HOST_STATE_ROOT)
    parser.add_argument("--inspect-file", type=Path)
    parser.add_argument("--compose-file", type=Path, default=Path("docker-compose.public-edge.yml"))
    parser.add_argument("--env-example", type=Path, default=Path(".env.example"))
    args = parser.parse_args()
    payload = materialize(args.output, container=args.container, expected_index=args.expected_index, host_state_root=args.host_state_root, inspect_file=args.inspect_file, compose_file=args.compose_file, env_example=args.env_example)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
