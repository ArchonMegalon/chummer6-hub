from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMAGE = "chummer-run-api:local"
SCRIPT = ROOT / "scripts" / "initialize-public-edge-volumes.sh"
PORTAL_UID = 1000
PORTAL_GID = 1000


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def require_local_runtime() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker is unavailable")
    probe = docker("image", "inspect", IMAGE, check=False)
    if probe.returncode != 0:
        pytest.skip(f"{IMAGE} is unavailable for the isolated runtime regression")


def test_initializer_migrates_named_volumes_and_only_probes_downloads_bind(tmp_path: Path) -> None:
    require_local_runtime()
    token = uuid.uuid4().hex[:12]
    volumes = [f"chummer-volume-init-test-{token}-{index}" for index in range(4)]
    mount_targets = (
        "/app/state",
        "/release-upload-sessions",
        "/windows-proof-store",
        "/windows-proof-upload-sessions",
    )
    downloads = tmp_path / "downloads"
    downloads.mkdir(mode=0o777)
    downloads.chmod(0o777)
    downloads_owner_before = (downloads.stat().st_uid, downloads.stat().st_gid)

    try:
        for index, volume in enumerate(volumes):
            docker("volume", "create", volume)
            legacy_fixture = (
                "mkdir -p /fixture/data-protection-keys; "
                "printf %s legacy-plaintext-key-bytes > "
                "/fixture/data-protection-keys/key-legacy.xml; "
                "chown -R 1000:1000 /fixture/data-protection-keys; "
                if index == 0
                else ""
            )
            docker(
                "run",
                "--rm",
                "--user",
                "0:0",
                "--entrypoint",
                "/bin/sh",
                "-v",
                f"{volume}:/fixture",
                IMAGE,
                "-eu",
                "-c",
                "mkdir -p /fixture/legacy/nested; : > /fixture/legacy/nested/data; "
                "chown -R 1001:1001 /fixture; "
                f"{legacy_fixture}"
                "chmod 700 /fixture /fixture/legacy /fixture/legacy/nested",
            )

        command = [
            "run",
            "--rm",
            "--read-only",
            "--network",
            "none",
            "--user",
            "0:0",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "CHOWN",
            "--cap-add",
            "SETUID",
            "--cap-add",
            "SETGID",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            "32",
            "--entrypoint",
            "/bin/sh",
            "-e",
            f"CHUMMER_PORTAL_UID={PORTAL_UID}",
            "-e",
            f"CHUMMER_PORTAL_GID={PORTAL_GID}",
            "-v",
            f"{SCRIPT}:/initializer:ro",
        ]
        for volume, target in zip(volumes, mount_targets, strict=True):
            command.extend(["-v", f"{volume}:{target}"])
        command.extend(["-v", f"{downloads}:/downloads-source", IMAGE, "/initializer"])

        result = docker(*command)
        assert f"verified for {PORTAL_UID}:{PORTAL_GID}" in result.stdout

        for volume in volumes:
            ownership = docker(
                "run",
                "--rm",
                "--user",
                "0:0",
                "--entrypoint",
                "/bin/sh",
                "-v",
                f"{volume}:/fixture:ro",
                IMAGE,
                "-eu",
                "-c",
                "find -P /fixture -xdev -printf '%U:%G\\n' | sort -u",
            )
            assert ownership.stdout.strip() == f"{PORTAL_UID}:{PORTAL_GID}"

        core_workspace_root = docker(
            "run",
            "--rm",
            "--user",
            "0:0",
            "--entrypoint",
            "/bin/sh",
            "-v",
            f"{volumes[0]}:/fixture:ro",
            IMAGE,
            "-eu",
            "-c",
            "stat -c '%u:%g:%a:%F' /fixture/core-workspaces; "
            "test -z \"$(find /fixture/core-workspaces -mindepth 1 -print -quit)\"",
        )
        assert core_workspace_root.stdout.strip() == (
            f"{PORTAL_UID}:{PORTAL_GID}:700:directory"
        )

        data_protection_roots = docker(
            "run",
            "--rm",
            "--user",
            "0:0",
            "--entrypoint",
            "/bin/sh",
            "-v",
            f"{volumes[0]}:/fixture:ro",
            IMAGE,
            "-eu",
            "-c",
            "stat -c '%u:%g:%a:%F' /fixture/data-protection-keys-v2; "
            "test -z \"$(find /fixture/data-protection-keys-v2 -mindepth 1 -print -quit)\"; "
            "test \"$(cat /fixture/data-protection-keys/key-legacy.xml)\" = "
            "\"legacy-plaintext-key-bytes\"",
        )
        assert data_protection_roots.stdout.strip() == (
            f"{PORTAL_UID}:{PORTAL_GID}:700:directory"
        )

        assert (downloads.stat().st_uid, downloads.stat().st_gid) == downloads_owner_before
        assert downloads.stat().st_mode & 0o777 == 0o777
        assert list(downloads.iterdir()) == []
    finally:
        for volume in volumes:
            docker("volume", "rm", "-f", volume, check=False)
