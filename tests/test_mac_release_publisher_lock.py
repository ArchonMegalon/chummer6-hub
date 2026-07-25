from __future__ import annotations

import fcntl
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = (
    ROOT
    / "Chummer.Run.Api"
    / "wwwroot"
    / "artifacts"
    / "mac-codex-release-pipeline"
    / "bootstrap.sh"
)
LOCK_NAME = ".chummer-release-publisher.lock"
LOCK_CONTRACT = b"chummer.mac-release-root-publisher-lock/v1\n"


def bootstrap_environment(work_root: Path) -> dict[str, str]:
    return {
        "CHUMMER_MAC_RELEASE_WORK_ROOT": str(work_root),
        "CHUMMER_RELEASE_PYTHON": sys.executable,
        "HOME": str(work_root.parent.parent / "home"),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
    }


def test_bootstrap_initializes_canonical_root_lock_before_preflight(
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "release"
    work_root = release_root / "run-lock-initialization"
    completed = subprocess.run(
        ("/bin/bash", str(BOOTSTRAP)),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=bootstrap_environment(work_root),
        timeout=15,
    )
    assert completed.returncode != 0
    lock_path = release_root / LOCK_NAME
    assert lock_path.read_bytes() == LOCK_CONTRACT
    metadata = lock_path.stat()
    assert stat.S_IMODE(metadata.st_mode) == 0o600
    assert metadata.st_uid == os.geteuid()
    assert metadata.st_nlink == 1
    assert not work_root.exists()


def test_bootstrap_publisher_waits_while_sealer_holds_exclusive_lock(
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "release"
    release_root.mkdir(mode=0o700)
    lock_path = release_root / LOCK_NAME
    lock_path.write_bytes(LOCK_CONTRACT)
    lock_path.chmod(0o600)
    descriptor = os.open(lock_path, os.O_RDWR)
    process: subprocess.Popen[bytes] | None = None
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        process = subprocess.Popen(
            ("/bin/bash", str(BOOTSTRAP)),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=bootstrap_environment(
                release_root / "run-lock-contention"
            ),
        )
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=0.5)
        assert not (release_root / "run-lock-contention").exists()
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode != 0
        assert b"CHUMMER_RELEASE_SCOPE_DECISION_PATH is required" in stderr
        assert b"incident-release-upload" not in stdout + stderr
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_bootstrap_lock_held_flag_without_inherited_fd_fails_closed(
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "release"
    work_root = release_root / "run-legacy-lock-flag"
    environment = bootstrap_environment(work_root)
    environment["CHUMMER_RELEASE_PUBLISHER_LOCK_HELD"] = "1"
    completed = subprocess.run(
        ("/bin/bash", str(BOOTSTRAP)),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        timeout=15,
    )
    assert completed.returncode != 0
    assert (
        b"CHUMMER_RELEASE_PUBLISHER_LOCK_HELD is not publisher-lock authority"
        in completed.stderr
    )
    assert not (release_root / LOCK_NAME).exists()
    assert not work_root.exists()


def test_bootstrap_child_inherits_and_validates_publisher_lock_fd(
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "release"
    release_root.mkdir(mode=0o700)
    lock_path = release_root / LOCK_NAME
    lock_path.write_bytes(LOCK_CONTRACT)
    lock_path.chmod(0o600)
    descriptor = os.open(lock_path, os.O_RDWR)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        environment = bootstrap_environment(
            release_root / "run-inherited-lock-fd"
        )
        environment["CHUMMER_RELEASE_PUBLISHER_LOCK_FD"] = str(descriptor)
        completed = subprocess.run(
            ("/bin/bash", str(BOOTSTRAP)),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            pass_fds=(descriptor,),
            timeout=15,
        )
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    assert completed.returncode != 0
    assert b"CHUMMER_RELEASE_SCOPE_DECISION_PATH is required" in completed.stderr
    assert b"inherited release-root publisher lock validation failed" not in (
        completed.stderr
    )
    assert b"incident-release-upload" not in completed.stdout + completed.stderr
