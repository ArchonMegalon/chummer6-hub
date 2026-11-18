from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROJECT = (
    ROOT
    / "scripts"
    / "Chummer.DataProtectionBundleMaterializer"
    / "Chummer.DataProtectionBundleMaterializer.csproj"
)


@pytest.fixture(scope="session")
def materializer_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("openssl") is None or shutil.which("dotnet") is None:
        pytest.skip("OpenSSL and the .NET SDK are required")
    if os.geteuid() != 1000:
        pytest.skip("custody materializer execution requires the production UID 1000")
    build_cwd = tmp_path_factory.mktemp("bundle-materializer-build")
    completed = subprocess.run(
        [
            "/usr/bin/dotnet",
            "build",
            str(PROJECT),
            "--configuration",
            "Release",
            "--disable-build-servers",
            "--maxcpucount:1",
            "-p:UseSharedCompilation=false",
            "--nologo",
        ],
        cwd=build_cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return PROJECT.parent / "bin/Release/net10.0/Chummer.DataProtectionBundleMaterializer.dll"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_password(root: Path, value: bytes = b"synthetic-test-password\n") -> Path:
    path = root / "password"
    path.write_bytes(value)
    path.chmod(0o400)
    return path


def make_pfx(
    root: Path,
    name: str,
    password: Path,
    *,
    days: int,
    key_type: str = "rsa:2048",
    key_usage: str = "keyEncipherment,dataEncipherment",
) -> Path:
    key = root / f"{name}.key.pem"
    certificate = root / f"{name}.certificate.pem"
    pfx = root / f"{name}.pfx"
    request = subprocess.run(
        [
            "/usr/bin/openssl",
            "req",
            "-x509",
            "-newkey",
            key_type,
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-days",
            str(days),
            "-nodes",
            "-subj",
            f"/CN={name}",
            "-addext",
            f"keyUsage=critical,{key_usage}",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert request.returncode == 0, request.stderr
    export = subprocess.run(
        [
            "/usr/bin/openssl",
            "pkcs12",
            "-export",
            "-out",
            str(pfx),
            "-inkey",
            str(key),
            "-in",
            str(certificate),
            "-passout",
            f"file:{password}",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert export.returncode == 0, export.stderr
    pfx.chmod(0o400)
    return pfx


def run_materializer(
    dll: Path,
    incumbent: Path,
    fresh: Path,
    password: Path,
    output: Path,
    *,
    incumbent_pin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "/usr/bin/dotnet",
            str(dll),
            "--incumbent-pfx",
            str(incumbent),
            "--incumbent-pfx-sha256",
            incumbent_pin or sha256(incumbent),
            "--fresh-pfx",
            str(fresh),
            "--fresh-pfx-sha256",
            sha256(fresh),
            "--password-file",
            str(password),
            "--password-file-sha256",
            sha256(password),
            "--output",
            str(output),
        ],
        cwd=output.parent,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": "/nonexistent",
            "LANG": "C",
            "LC_ALL": "C",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def fixture_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    custody = tmp_path / "custody"
    custody.mkdir(mode=0o700)
    output_root = tmp_path / "output"
    output_root.mkdir(mode=0o700)
    password = write_password(custody)
    incumbent = make_pfx(custody, "incumbent", password, days=30)
    fresh = make_pfx(custody, "fresh", password, days=365)
    return incumbent, fresh, password, output_root / "rotation-bundle.pfx"


def test_materializer_exports_reopens_and_installs_two_private_keys_no_clobber(
    materializer_dll: Path,
    tmp_path: Path,
) -> None:
    incumbent, fresh, password, output = fixture_inputs(tmp_path)

    completed = run_materializer(materializer_dll, incumbent, fresh, password, output)

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(completed.stdout)
    metadata = output.lstat()
    assert receipt["contractName"] == (
        "chummer.data-protection.certificate-bundle-materialization/v1"
    )
    assert receipt["status"] == "pass"
    assert receipt["privateKeyCertificateCount"] == 2
    assert [item["role"] for item in receipt["certificates"]].count("primary") == 1
    assert [item["role"] for item in receipt["certificates"]].count("decrypt-only") == 1
    assert all(item["rsaKeySizeBits"] >= 2048 for item in receipt["certificates"])
    assert receipt["output"] == {
        "sha256": sha256(output),
        "sizeBytes": output.stat().st_size,
        "mode": "0400",
        "userId": 1000,
        "linkCount": 1,
    }
    assert stat.S_IMODE(metadata.st_mode) == 0o400
    assert metadata.st_uid == 1000
    assert metadata.st_nlink == 1
    assert "password" not in completed.stdout.lower()
    assert str(incumbent) not in completed.stdout
    original = output.read_bytes()

    refused = run_materializer(materializer_dll, incumbent, fresh, password, output)

    assert refused.returncode == 70
    assert output.read_bytes() == original
    assert "already exists" in refused.stderr


def test_materializer_refuses_symlink_destination_no_clobber(
    materializer_dll: Path,
    tmp_path: Path,
) -> None:
    incumbent, fresh, password, output = fixture_inputs(tmp_path)
    target = output.parent / "unrelated.pfx"
    target.write_bytes(b"do-not-touch\n")
    output.symlink_to(target)

    completed = run_materializer(materializer_dll, incumbent, fresh, password, output)

    assert completed.returncode == 70
    assert output.is_symlink()
    assert target.read_bytes() == b"do-not-touch\n"


def test_materializer_rejects_wrong_external_pin_without_output(
    materializer_dll: Path,
    tmp_path: Path,
) -> None:
    incumbent, fresh, password, output = fixture_inputs(tmp_path)

    completed = run_materializer(
        materializer_dll,
        incumbent,
        fresh,
        password,
        output,
        incumbent_pin="0" * 64,
    )

    assert completed.returncode == 70
    assert not output.exists()
    assert "external SHA-256 pin" in completed.stderr


def test_materializer_rejects_hardlinked_or_group_readable_secret(
    materializer_dll: Path,
    tmp_path: Path,
) -> None:
    incumbent, fresh, password, output = fixture_inputs(tmp_path)
    alias = incumbent.with_suffix(".alias")
    os.link(incumbent, alias)

    hardlink = run_materializer(materializer_dll, incumbent, fresh, password, output)

    assert hardlink.returncode == 70
    assert not output.exists()
    alias.unlink()
    incumbent.chmod(0o440)

    readable = run_materializer(materializer_dll, incumbent, fresh, password, output)

    assert readable.returncode == 70
    assert not output.exists()


def test_materializer_rejects_non_encryption_key_and_nonfresh_primary(
    materializer_dll: Path,
    tmp_path: Path,
) -> None:
    custody = tmp_path / "custody"
    custody.mkdir(mode=0o700)
    output_root = tmp_path / "output"
    output_root.mkdir(mode=0o700)
    password = write_password(custody)
    incumbent = make_pfx(custody, "incumbent", password, days=365)
    signing_only = make_pfx(
        custody,
        "fresh-signing",
        password,
        days=730,
        key_usage="digitalSignature",
    )
    output = output_root / "signing-only.pfx"

    invalid_usage = run_materializer(
        materializer_dll,
        incumbent,
        signing_only,
        password,
        output,
    )

    assert invalid_usage.returncode == 70
    assert not output.exists()
    fresh_but_older = make_pfx(custody, "fresh-older", password, days=30)
    output = output_root / "older.pfx"

    wrong_primary = run_materializer(
        materializer_dll,
        incumbent,
        fresh_but_older,
        password,
        output,
    )

    assert wrong_primary.returncode == 70
    assert "unique latest-expiry primary must come from the fresh" in wrong_primary.stderr
    assert not output.exists()
