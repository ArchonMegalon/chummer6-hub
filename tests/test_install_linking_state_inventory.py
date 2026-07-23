from __future__ import annotations

import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "attest_install_linking_state_inventory.py"
OPERATION = "initial-release-shelf-public-download-cutover"
SOURCE_HEAD = "a" * 40
VOLUME = "chummer6-hub_chummer-run-api-state"


def tar_bytes(entries: dict[str, bytes], *, symlink: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, content in entries.items():
            member = tarfile.TarInfo(name)
            member.mode = 0o600
            member.uid = 1654
            member.gid = 1654
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
        if symlink is not None:
            member = tarfile.TarInfo(symlink)
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
            archive.addfile(member)
    return buffer.getvalue()


def run(
    tmp_path: Path,
    command: str,
    tar_payload: bytes,
    *,
    output_name: str,
    before: Path | None = None,
) -> subprocess.CompletedProcess[bytes]:
    arguments = [
        sys.executable,
        str(SCRIPT),
        command,
        "--operation",
        OPERATION,
        "--source-head",
        SOURCE_HEAD,
        "--volume",
        VOLUME,
        "--output",
        str(tmp_path / output_name),
    ]
    if before is not None:
        arguments.extend(["--before", str(before)])
    return subprocess.run(
        arguments,
        cwd=ROOT,
        input=tar_payload,
        check=False,
        capture_output=True,
    )


def test_snapshot_and_compare_exact_install_linking_namespace(
    tmp_path: Path,
) -> None:
    payload = tar_bytes(
        {
            "./install-linking-store.json": b'{"version":1}\n',
            "./data-protection-keys-v2/key.xml": b"unrelated",
        }
    )
    before = tmp_path / "before.json"
    assert run(
        tmp_path,
        "snapshot",
        payload,
        output_name=before.name,
    ).returncode == 0
    assert run(
        tmp_path,
        "compare",
        payload,
        output_name="after.json",
        before=before,
    ).returncode == 0

    receipt = json.loads(before.read_text(encoding="utf-8"))
    assert stat.S_IMODE(before.stat().st_mode) == 0o600
    assert receipt["entryCount"] == 1
    assert receipt["entries"][0]["path"] == "install-linking-store.json"
    after = json.loads((tmp_path / "after.json").read_text(encoding="utf-8"))
    assert after["unchanged"] is True


def test_compare_rejects_byte_change(tmp_path: Path) -> None:
    before = tmp_path / "before.json"
    original = tar_bytes({"install-linking-store.json": b"before"})
    changed = tar_bytes({"install-linking-store.json": b"after"})
    assert run(
        tmp_path,
        "snapshot",
        original,
        output_name=before.name,
    ).returncode == 0
    completed = run(
        tmp_path,
        "compare",
        changed,
        output_name="after.json",
        before=before,
    )
    assert completed.returncode != 0
    assert b"state changed" in completed.stderr
    assert not (tmp_path / "after.json").exists()


def test_unrelated_state_change_is_outside_namespace(tmp_path: Path) -> None:
    before = tmp_path / "before.json"
    original = tar_bytes({"community-store.json": b"before"})
    changed = tar_bytes({"community-store.json": b"after"})
    assert run(
        tmp_path,
        "snapshot",
        original,
        output_name=before.name,
    ).returncode == 0
    assert run(
        tmp_path,
        "compare",
        changed,
        output_name="after.json",
        before=before,
    ).returncode == 0


def test_rejects_symlink_inside_install_linking_namespace(
    tmp_path: Path,
) -> None:
    completed = run(
        tmp_path,
        "snapshot",
        tar_bytes({}, symlink="install-linking-store.json"),
        output_name="before.json",
    )
    assert completed.returncode != 0
    assert b"symlink or special file" in completed.stderr
