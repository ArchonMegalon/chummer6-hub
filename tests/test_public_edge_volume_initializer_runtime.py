from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get(
    "CHUMMER_PUBLIC_EDGE_INITIALIZER_TEST_IMAGE",
    "chummer-run-api:local",
)
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


@pytest.fixture
def initializer_script(tmp_path: Path) -> Path:
    isolated_script = tmp_path / "initialize-public-edge-volumes.sh"
    shutil.copyfile(SCRIPT, isolated_script)
    isolated_script.chmod(0o555)
    return isolated_script


def tree_sha256(root: Path) -> str:
    stream = bytearray()
    files = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: f"./{path.relative_to(root).as_posix()}".encode(),
    )
    for path in files:
        relative_path = f"./{path.relative_to(root).as_posix()}"
        stream.extend(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        stream.extend(b"  ")
        stream.extend(relative_path.encode())
        stream.extend(b"\n")
    return hashlib.sha256(stream).hexdigest()


def write_runtime_inputs(root: Path) -> dict[str, str]:
    app = root / "app"
    fleet = root / "fleet"
    shelf = root / "shelf"
    projection = root / "projection"
    for directory in (app, fleet, shelf, projection):
        directory.mkdir(parents=True, mode=0o755)

    (app / "portal.txt").write_text("portal\n", encoding="utf-8")
    (fleet / "fleet.txt").write_text("fleet\n", encoding="utf-8")
    (projection / "projection.json").write_text("{}\n", encoding="utf-8")

    generation = shelf / "generations" / "generation-test"
    generation.mkdir(parents=True, mode=0o755)
    (shelf / ".release-shelf-layout-v1").write_text("v1\n", encoding="utf-8")
    (shelf / ".release-shelf-writer-policy.json").write_text(
        '{"schemaVersion":"chummer.release-shelf.writer-policy/v1",'
        '"mode":"sidecar-readonly-v1"}\n',
        encoding="utf-8",
    )
    (shelf / "current.json").write_text(
        '{"schemaVersion":"chummer.release-shelf.current/v1",'
        '"generationId":"generation-test"}\n',
        encoding="utf-8",
    )
    for path in (
        shelf / "RELEASE_CHANNEL.generated.json",
        shelf / "releases.json",
        generation / "activation-candidate.json",
        generation / "RELEASE_CHANNEL.generated.json",
        generation / "releases.json",
    ):
        path.write_text("{}\n", encoding="utf-8")

    runtime_proof = root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    final_gold = root / "FINAL_GOLD_JANITOR.generated.json"
    certificate = root / "data-protection-key-encryption.pfx"
    password = root / "data-protection-key-encryption.password"
    runtime_proof.write_text('{"status":"pass"}\n', encoding="utf-8")
    final_gold.write_text('{"status":"pass"}\n', encoding="utf-8")
    certificate.write_bytes(b"test-certificate-bytes\n")
    password.write_text("test-password\n", encoding="utf-8")

    for directory in (root, app, fleet, shelf, generation.parent, generation, projection):
        directory.chmod(0o755)
    for path in root.rglob("*"):
        if path.is_file():
            path.chmod(0o644)

    return {
        "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_CERTIFICATE_SHA256": hashlib.sha256(
            certificate.read_bytes()
        ).hexdigest(),
        "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_PASSWORD_SHA256": hashlib.sha256(
            password.read_bytes()
        ).hexdigest(),
        "CHUMMER_PUBLIC_DOWNLOAD_APP_OVERLAY_SHA256": tree_sha256(app),
        "CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256": tree_sha256(fleet),
        "CHUMMER_PUBLIC_DOWNLOAD_SHELF_SHA256": tree_sha256(shelf),
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256": tree_sha256(projection),
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256": hashlib.sha256(
            runtime_proof.read_bytes()
        ).hexdigest(),
        "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256": hashlib.sha256(
            final_gold.read_bytes()
        ).hexdigest(),
    }


def test_public_download_initializer_accepts_valid_digests_and_copies_inputs(
    tmp_path: Path,
    initializer_script: Path,
) -> None:
    require_local_runtime()
    token = uuid.uuid4().hex[:12]
    runtime_inputs = tmp_path / "runtime-inputs"
    runtime_inputs.mkdir(mode=0o755)
    digests = write_runtime_inputs(runtime_inputs)
    volume_targets = (
        "/app/state",
        "/release-upload-sessions",
        "/windows-proof-store",
        "/windows-proof-upload-sessions",
        "/app-staging",
        "/fleet-staging",
        "/downloads-source",
        "/public-projection-staging",
        "/proofs-staging",
        "/run/chummer-secrets",
    )
    volumes = [
        f"chummer-public-download-init-test-{token}-{index}"
        for index in range(len(volume_targets))
    ]

    try:
        for volume in volumes:
            docker("volume", "create", volume)

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
            "CHUMMER_PUBLIC_DOWNLOAD_RUNTIME_INIT=true",
            "-e",
            f"CHUMMER_PORTAL_UID={PORTAL_UID}",
            "-e",
            f"CHUMMER_PORTAL_GID={PORTAL_GID}",
            "-v",
            f"{initializer_script}:/initializer:ro",
            "-v",
            f"{runtime_inputs}:/runtime-inputs:ro",
        ]
        for name, digest in digests.items():
            command.extend(["-e", f"{name}={digest}"])
        for volume, target in zip(volumes, volume_targets, strict=True):
            command.extend(["-v", f"{volume}:{target}"])
        command.extend([IMAGE, "/initializer"])

        result = docker(*command)

        assert (
            f"public-download runtime inputs verified for "
            f"{PORTAL_UID}:{PORTAL_GID}"
        ) in result.stdout
    finally:
        for volume in volumes:
            docker("volume", "rm", "-f", volume, check=False)


def test_initializer_migrates_named_volumes_and_only_probes_downloads_bind(
    tmp_path: Path,
    initializer_script: Path,
) -> None:
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
            f"{initializer_script}:/initializer:ro",
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
