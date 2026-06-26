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
DEFAULT_OUTPUT = Path(
    "/docker/chummercomplete/.tmp/origin-dossier-fresh-gold/"
    "origin.chummer.run/Varga/Mira/Kestrel/portal-publication-index-preflight.receipt.json"
)


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


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def load_container_inspect(container: str, inspect_file: Path | None = None) -> dict[str, Any]:
    if inspect_file is not None:
        parsed = json.loads(inspect_file.read_text(encoding="utf-8"))
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return parsed[0]
        if isinstance(parsed, dict):
            return parsed
        raise ValueError(f"{inspect_file}: expected docker inspect object or one-item list")
    try:
        completed = subprocess.run(
            ["docker", "inspect", container],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError):
        return {}
    parsed = json.loads(completed.stdout)
    return parsed[0] if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict) else {}


def inspect_env(inspect_payload: dict[str, Any]) -> dict[str, str]:
    env_values: dict[str, str] = {}
    config = inspect_payload.get("Config") if isinstance(inspect_payload.get("Config"), dict) else {}
    env = config.get("Env") if isinstance(config.get("Env"), list) else []
    for item in env:
        text = str(item)
        if "=" not in text:
            continue
        key, value = text.split("=", 1)
        if key:
            env_values[key] = value
    return env_values


def inspect_mounts(inspect_payload: dict[str, Any]) -> list[dict[str, str]]:
    mounts: list[dict[str, str]] = []
    raw_mounts = inspect_payload.get("Mounts") if isinstance(inspect_payload.get("Mounts"), list) else []
    for mount in raw_mounts:
        if not isinstance(mount, dict):
            continue
        mounts.append(
            {
                "destination": str(mount.get("Destination") or ""),
                "sourceSha256": sha256_text(mount.get("Source") or ""),
                "type": str(mount.get("Type") or ""),
                "name": str(mount.get("Name") or ""),
            }
        )
    return mounts


def env_file_has_index(path: Path, key: str, expected_index: str) -> dict[str, Any]:
    text = read_text(path)
    present = False
    expected = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        env_key, value = stripped.split("=", 1)
        if env_key.strip() != key:
            continue
        present = True
        expected = value.strip().strip('"').strip("'") == expected_index
    return {
        "pathSha256": sha256_text(path.as_posix()),
        "present": path.is_file(),
        "keyPresent": present,
        "expectedValuePresent": expected,
        "valueStoredInReceipt": False,
    }


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
    inspect_payload = load_container_inspect(container, inspect_file)
    env_values = inspect_env(inspect_payload)
    mounts = inspect_mounts(inspect_payload)
    expected_host_index = host_state_root / Path(expected_index).name
    running_value = env_values.get("CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX", "")
    running_env_present = bool(running_value)
    running_env_expected = running_value == expected_index
    state_mount_present = any(mount["destination"] == "/app/state" for mount in mounts)
    host_index_present = expected_host_index.is_file()
    host_index_nonempty = host_index_present and expected_host_index.stat().st_size > 0
    compose_text = read_text(compose_file)
    compose_configured = "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX" in compose_text and expected_index in compose_text
    env_example_state = env_file_has_index(env_example, "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX", expected_index)
    pass_state = running_env_expected and state_mount_present and host_index_nonempty
    restart_required = host_index_nonempty and state_mount_present and not running_env_expected
    blockers: list[str] = []
    if not inspect_payload:
        blockers.append("portal_container_inspect_unavailable")
    if not running_env_present:
        blockers.append("running_portal_publication_index_env_missing")
    elif not running_env_expected:
        blockers.append("running_portal_publication_index_env_unexpected")
    if not state_mount_present:
        blockers.append("portal_state_mount_missing")
    if not host_index_present:
        blockers.append("host_publication_index_missing")
    elif not host_index_nonempty:
        blockers.append("host_publication_index_empty")
    if not compose_configured:
        blockers.append("compose_publication_index_env_missing")
    if not env_example_state["keyPresent"]:
        blockers.append("env_example_publication_index_missing")

    payload: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "generatedAtUtc": now_iso(),
        "updated_at": now_iso(),
        "status": "pass" if pass_state else "blocked",
        "goalCompletionClaimAllowed": False,
        "deploymentPerformed": False,
        "container": container,
        "expectedContainerPublicationIndex": expected_index,
        "expectedHostPublicationIndex": {
            "pathSha256": sha256_text(expected_host_index.as_posix()),
            "present": host_index_present,
            "nonempty": host_index_nonempty,
            "sha256": sha256_file(expected_host_index) if host_index_nonempty else "",
            "sizeBytes": expected_host_index.stat().st_size if host_index_present else 0,
            "pathStoredInReceipt": False,
        },
        "runningContainer": {
            "inspectAvailable": bool(inspect_payload),
            "publicationIndexEnvPresent": running_env_present,
            "publicationIndexEnvMatchesExpected": running_env_expected,
            "publicationIndexValueSha256": sha256_text(running_value),
            "envValueStoredInReceipt": False,
            "stateMountPresent": state_mount_present,
            "mounts": mounts,
        },
        "configFiles": {
            "compose": {
                "pathSha256": sha256_text(compose_file.as_posix()),
                "present": compose_file.is_file(),
                "publicationIndexConfigured": compose_configured,
            },
            "envExample": env_example_state,
        },
        "restartRequiredForExistingContainer": restart_required,
        "next_action": (
            "Restart/recreate chummer-portal only after explicit deploy approval so "
            "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX=/app/state/origin-dossier-publications.json is active."
            if restart_required
            else "Resolve portal publication-index preflight blockers before claiming deployed Origin Edition Gold."
            if not pass_state
            else "Portal publication index is active in the running container; rerun deployed browser proof."
        ),
        "blocking_reason": "" if pass_state else ",".join(blockers),
        "blockers": blockers,
        "privacy": {
            "rawCredentialExposed": False,
            "rawEnvValueExposed": False,
            "deploymentPerformed": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only preflight for deployed Chummer Origin publication index.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--expected-index", default=DEFAULT_EXPECTED_INDEX)
    parser.add_argument("--host-state-root", type=Path, default=DEFAULT_HOST_STATE_ROOT)
    parser.add_argument("--inspect-file", type=Path)
    parser.add_argument("--compose-file", type=Path, default=Path("docker-compose.public-edge.yml"))
    parser.add_argument("--env-example", type=Path, default=Path(".env.example"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = materialize(
        args.output,
        container=args.container,
        expected_index=args.expected_index,
        host_state_root=args.host_state_root,
        inspect_file=args.inspect_file,
        compose_file=args.compose_file,
        env_example=args.env_example,
    )
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
