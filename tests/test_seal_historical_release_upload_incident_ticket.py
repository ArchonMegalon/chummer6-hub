from __future__ import annotations

from dataclasses import dataclass, replace
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIRECTORY = ROOT / "scripts"
SEAL_SCRIPT = (
    SCRIPT_DIRECTORY / "seal_historical_release_upload_incident_ticket.py"
)
MATERIALIZE_SCRIPT = (
    SCRIPT_DIRECTORY
    / "materialize_historical_release_upload_incident_ticket.py"
)
sys.path.insert(0, str(SCRIPT_DIRECTORY))


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


seal = load_script("incident_ticket_seal_test", SEAL_SCRIPT)
materialize = load_script("incident_ticket_materialize_test", MATERIALIZE_SCRIPT)

INCIDENT_TICKET = b"incident-release-upload-bearer-20260725"
CONFIG_BYTES = (
    b"silent\n"
    b'header = "Authorization: Bearer '
    + INCIDENT_TICKET
    + b'"\n'
    b"show-error\n"
)


@dataclass
class CryptoFixture:
    openssl: Path
    openssl_sha256: str
    recipient_key: Path
    recipient_key_sha256: str
    recipient_cert: Path
    recipient_cert_sha256: str
    signer_key: Path
    signer_key_sha256: str
    signer_cert: Path
    signer_cert_sha256: str


@dataclass
class SealFixture:
    release_root: Path
    lock_path: Path
    targets: list[str]
    output: Path
    receipt: Path
    marker: Path
    crypto: CryptoFixture


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_identity(openssl: Path, root: Path, name: str) -> tuple[Path, Path]:
    key = root / f"{name}.key.pem"
    cert = root / f"{name}.cert.pem"
    subprocess.run(
        (
            str(openssl),
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-nodes",
            "-days",
            "1",
            "-subj",
            f"/CN={name}",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
    )
    key.chmod(0o600)
    cert.chmod(0o600)
    return key, cert


def crypto_fixture(root: Path) -> CryptoFixture:
    selected = shutil.which("openssl")
    if selected is None:
        pytest.skip("OpenSSL is required")
    openssl = Path(selected).resolve()
    crypto_root = root / "crypto"
    crypto_root.mkdir(mode=0o700)
    recipient_key, recipient_cert = generate_identity(
        openssl,
        crypto_root,
        "recipient",
    )
    signer_key, signer_cert = generate_identity(
        openssl,
        crypto_root,
        "signer",
    )
    return CryptoFixture(
        openssl=openssl,
        openssl_sha256=digest(openssl),
        recipient_key=recipient_key,
        recipient_key_sha256=digest(recipient_key),
        recipient_cert=recipient_cert,
        recipient_cert_sha256=digest(recipient_cert),
        signer_key=signer_key,
        signer_key_sha256=digest(signer_key),
        signer_cert=signer_cert,
        signer_cert_sha256=digest(signer_cert),
    )


def write_candidate(
    root: Path,
    run_id: str,
    content: bytes = CONFIG_BYTES,
) -> str:
    relative = f"{run_id}/nested/upload-auth.curl"
    path = root / relative
    path.parent.mkdir(parents=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_bytes(content)
    path.chmod(0o600)
    return relative


def build_fixture(tmp_path: Path) -> SealFixture:
    release_root = tmp_path / "release"
    release_root.mkdir(mode=0o700)
    lock_path = release_root / seal.PUBLISHER_LOCK_NAME
    lock_path.write_text(seal.PUBLISHER_LOCK_CONTRACT, encoding="ascii")
    lock_path.chmod(0o600)
    targets = [
        write_candidate(release_root, "run-20260724-130312"),
        write_candidate(release_root, "run-20260724-193632"),
    ]
    drop = tmp_path / "drop"
    drop.mkdir(mode=0o700)
    return SealFixture(
        release_root=release_root,
        lock_path=lock_path,
        targets=targets,
        output=drop / "incident-ticket.cms",
        receipt=drop / "incident-ticket.receipt.json",
        marker=drop / "incident-ticket.commit.json",
        crypto=crypto_fixture(tmp_path),
    )


def seal_args(fixture: SealFixture) -> list[str]:
    crypto = fixture.crypto
    result = [
        "--release-root",
        str(fixture.release_root),
        "--publisher-lock",
        str(fixture.lock_path),
        "--openssl-path",
        str(crypto.openssl),
        "--openssl-sha256",
        crypto.openssl_sha256,
        "--recipient-cert",
        str(crypto.recipient_cert),
        "--recipient-cert-sha256",
        crypto.recipient_cert_sha256,
        "--signer-cert",
        str(crypto.signer_cert),
        "--signer-cert-sha256",
        crypto.signer_cert_sha256,
        "--signer-key",
        str(crypto.signer_key),
        "--signer-key-sha256",
        crypto.signer_key_sha256,
        "--output",
        str(fixture.output),
        "--receipt",
        str(fixture.receipt),
        "--commit-marker",
        str(fixture.marker),
        "--confirm",
        seal.CONFIRMATION,
    ]
    for target in fixture.targets:
        result.extend(("--target", target))
    return result


def materialize_args(
    fixture: SealFixture,
    *,
    ticket: Path,
    authority: Path,
    marker: Path,
) -> list[str]:
    crypto = fixture.crypto
    receipt = json.loads(fixture.receipt.read_text(encoding="utf-8"))
    return [
        "--openssl-path",
        str(crypto.openssl),
        "--openssl-sha256",
        crypto.openssl_sha256,
        "--envelope",
        str(fixture.output),
        "--envelope-sha256",
        digest(fixture.output),
        "--seal-receipt",
        str(fixture.receipt),
        "--seal-receipt-sha256",
        digest(fixture.receipt),
        "--inventory-commitment-sha256",
        receipt["inventoryCommitmentSha256"],
        "--recipient-cert",
        str(crypto.recipient_cert),
        "--recipient-cert-sha256",
        crypto.recipient_cert_sha256,
        "--recipient-key",
        str(crypto.recipient_key),
        "--recipient-key-sha256",
        crypto.recipient_key_sha256,
        "--signer-cert",
        str(crypto.signer_cert),
        "--signer-cert-sha256",
        crypto.signer_cert_sha256,
        "--ticket-output",
        str(ticket),
        "--authority-output",
        str(authority),
        "--commit-marker",
        str(marker),
        "--confirm",
        materialize.CONFIRMATION,
    ]


def assert_no_plaintext_in_public_results(
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured = capsys.readouterr()
    assert INCIDENT_TICKET.decode() not in captured.out
    assert INCIDENT_TICKET.decode() not in captured.err
    assert hashlib.sha256(INCIDENT_TICKET).hexdigest() not in captured.out
    assert hashlib.sha256(INCIDENT_TICKET).hexdigest() not in captured.err


def test_authenticated_seal_and_linux_materialization_handoff(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    assert seal.run(seal_args(fixture)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "sealed_pending_quarantine_and_revocation"
    assert result["cmsComposition"] == (
        "authenticated-signedData-inside-envelopedData"
    )
    assert result["quarantineStatus"] == "pending"
    assert result["revocationStatus"] == "pending"
    assert stat.S_IMODE(fixture.output.stat().st_mode) == 0o600
    assert stat.S_IMODE(fixture.receipt.stat().st_mode) == 0o600
    assert stat.S_IMODE(fixture.marker.stat().st_mode) == 0o600
    assert INCIDENT_TICKET not in fixture.output.read_bytes()
    assert INCIDENT_TICKET.decode() not in fixture.receipt.read_text()

    materialized = tmp_path / "materialized"
    materialized.mkdir(mode=0o700)
    ticket = materialized / "old-ticket.raw"
    authority = materialized / "old-ticket.authority.json"
    marker = materialized / "old-ticket.commit.json"
    assert (
        materialize.run(
            materialize_args(
                fixture,
                ticket=ticket,
                authority=authority,
                marker=marker,
            )
        )
        == 0
    )
    public_result = json.loads(capsys.readouterr().out)
    assert public_result == {
        "authorityFileReadyForInheritedFd": True,
        "contractName": materialize.CONTRACT_NAME,
        "materializationTransactionId": public_result[
            "materializationTransactionId"
        ],
        "quarantineStatus": "pending",
        "revocationStatus": "pending",
        "status": "materialized_pending_revocation",
    }
    assert ticket.read_bytes() == INCIDENT_TICKET
    assert stat.S_IMODE(ticket.stat().st_mode) == 0o600
    assert stat.S_IMODE(authority.stat().st_mode) == 0o600
    authority_payload = json.loads(authority.read_text(encoding="utf-8"))
    assert set(authority_payload) == materialize.AUTHORITY_FIELDS
    assert authority_payload["ticketSha256"] == hashlib.sha256(
        INCIDENT_TICKET
    ).hexdigest()
    assert authority_payload["ticketPathSha256"] == hashlib.sha256(
        str(ticket).encode("utf-8")
    ).hexdigest()
    assert authority.read_bytes() == seal._canonical_json_bytes(
        authority_payload
    )
    assert_no_plaintext_in_public_results(capsys)


@pytest.mark.parametrize(
    "content",
    [
        b'header = "Authorization: Bearer token" trailing\n',
        b"header = 'Authorization: Bearer token'\n",
        b'header = "X-Note: Authorization: Bearer token"\n',
        b'--oauth2-bearer = "token"\n',
        b'oauth2-bearer = "token"\nheader = "Authorization: Bearer token"\n',
        b"header = Authorization: Bearer token\n",
        b'header = "Authorization: Bearer token"\r\n',
        b'silent\nurl = "https://example.invalid/Bearer/token"\n',
    ],
)
def test_parser_rejects_malformed_or_ambiguous_credential_lines(
    content: bytes,
) -> None:
    with pytest.raises(seal.SealError):
        seal._extract_canonical_ticket(content)


def test_oauth2_bearer_full_line_is_supported() -> None:
    assert (
        seal._extract_canonical_ticket(
            b'silent\noauth2-bearer = "canonical-token"\n'
        )
        == b"canonical-token"
    )


def test_shared_publisher_lock_blocks_sealing_before_inventory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    descriptor = os.open(fixture.lock_path, os.O_RDWR)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        assert seal.run(seal_args(fixture)) == 2
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    assert not fixture.output.exists()
    error = json.loads(capsys.readouterr().err)
    assert error["error"] == "secure incident-ticket sealing failed"


def test_full_inventory_target_set_is_required(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    fixture.targets.pop()
    assert seal.run(seal_args(fixture)) == 2
    assert not fixture.output.exists()
    assert_no_plaintext_in_public_results(capsys)


def test_new_candidate_between_inventories_fails_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    original = seal._encrypt_signed_cms

    def add_candidate(*args: Any, **kwargs: Any) -> bytes:
        envelope = original(*args, **kwargs)
        write_candidate(
            fixture.release_root,
            "run-20260725-000000",
        )
        return envelope

    monkeypatch.setattr(seal, "_encrypt_signed_cms", add_candidate)
    assert seal.run(seal_args(fixture)) == 2
    assert not fixture.output.exists()
    assert_no_plaintext_in_public_results(capsys)


def test_candidate_inode_swap_between_inventories_fails_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    candidate = fixture.release_root / fixture.targets[0]
    original = seal._encrypt_signed_cms

    def swap_candidate(*args: Any, **kwargs: Any) -> bytes:
        envelope = original(*args, **kwargs)
        replacement = candidate.with_suffix(".replacement")
        replacement.write_bytes(CONFIG_BYTES)
        replacement.chmod(0o600)
        os.replace(replacement, candidate)
        return envelope

    monkeypatch.setattr(seal, "_encrypt_signed_cms", swap_candidate)
    assert seal.run(seal_args(fixture)) == 2
    assert not fixture.output.exists()
    assert_no_plaintext_in_public_results(capsys)


def test_transaction_recovers_after_link_crash_without_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    original_link = seal.os.link
    calls = 0

    def fail_second_link(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated crash boundary")
        original_link(*args, **kwargs)

    monkeypatch.setattr(seal.os, "link", fail_second_link)
    assert seal.run(seal_args(fixture)) == 2
    assert fixture.output.exists()
    assert not fixture.marker.exists()
    capsys.readouterr()

    monkeypatch.setattr(seal.os, "link", original_link)
    assert seal.run(seal_args(fixture)) == 0
    receipt = json.loads(fixture.receipt.read_text(encoding="utf-8"))
    assert receipt["envelopeSha256"] == digest(fixture.output)
    assert fixture.marker.exists()
    assert not list(fixture.output.parent.glob(".chummer-ticket-intake-*.stage"))
    assert_no_plaintext_in_public_results(capsys)


def test_transaction_recovers_abandoned_pre_manifest_stage(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    original_create = seal._create_private_file_at

    def fail_manifest(
        parent_descriptor: int,
        name: str,
        content: bytes,
    ):
        if name == "transaction.json":
            raise OSError("simulated crash before manifest commit")
        return original_create(parent_descriptor, name, content)

    monkeypatch.setattr(seal, "_create_private_file_at", fail_manifest)
    assert seal.run(seal_args(fixture)) == 2
    assert not fixture.output.exists()
    assert not fixture.receipt.exists()
    assert not fixture.marker.exists()
    assert len(
        list(fixture.output.parent.glob(".chummer-ticket-intake-*.stage"))
    ) == 1
    capsys.readouterr()

    monkeypatch.setattr(seal, "_create_private_file_at", original_create)
    assert seal.run(seal_args(fixture)) == 0
    assert fixture.output.exists()
    assert fixture.receipt.exists()
    assert fixture.marker.exists()
    assert not list(fixture.output.parent.glob(".chummer-ticket-intake-*.stage"))
    assert_no_plaintext_in_public_results(capsys)


def test_existing_unrelated_output_is_never_overwritten(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    fixture.output.write_bytes(b"keep")
    fixture.output.chmod(0o600)
    assert seal.run(seal_args(fixture)) == 2
    assert fixture.output.read_bytes() == b"keep"
    assert not fixture.receipt.exists()
    assert_no_plaintext_in_public_results(capsys)


def test_tampered_cms_or_wrong_signer_fails_before_plaintext(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    assert seal.run(seal_args(fixture)) == 0
    capsys.readouterr()
    envelope = bytearray(fixture.output.read_bytes())
    envelope[len(envelope) // 2] ^= 0x01
    fixture.output.write_bytes(envelope)
    fixture.output.chmod(0o600)
    receipt = json.loads(fixture.receipt.read_text(encoding="utf-8"))
    receipt["envelopeSha256"] = digest(fixture.output)
    receipt["envelopeSizeBytes"] = len(envelope)
    fixture.receipt.write_bytes(seal._canonical_json_bytes(receipt))
    fixture.receipt.chmod(0o600)
    materialized = tmp_path / "materialized"
    materialized.mkdir(mode=0o700)
    assert (
        materialize.run(
            materialize_args(
                fixture,
                ticket=materialized / "ticket",
                authority=materialized / "authority.json",
                marker=materialized / "commit.json",
            )
        )
        == 2
    )
    assert not (materialized / "ticket").exists()
    assert_no_plaintext_in_public_results(capsys)


def test_pinned_signer_cannot_be_substituted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    assert seal.run(seal_args(fixture)) == 0
    capsys.readouterr()
    wrong_root = tmp_path / "wrong-signer"
    wrong_root.mkdir(mode=0o700)
    wrong_key, wrong_cert = generate_identity(
        fixture.crypto.openssl,
        wrong_root,
        "wrong-signer",
    )
    fixture.crypto = replace(
        fixture.crypto,
        signer_key=wrong_key,
        signer_key_sha256=digest(wrong_key),
        signer_cert=wrong_cert,
        signer_cert_sha256=digest(wrong_cert),
    )
    receipt = json.loads(fixture.receipt.read_text(encoding="utf-8"))
    receipt["signerCertificateSha256"] = fixture.crypto.signer_cert_sha256
    fixture.receipt.write_bytes(seal._canonical_json_bytes(receipt))
    fixture.receipt.chmod(0o600)
    destination = tmp_path / "wrong-signer-materialized"
    destination.mkdir(mode=0o700)
    assert (
        materialize.run(
            materialize_args(
                fixture,
                ticket=destination / "ticket",
                authority=destination / "authority.json",
                marker=destination / "commit.json",
            )
        )
        == 2
    )
    assert not (destination / "ticket").exists()
    assert_no_plaintext_in_public_results(capsys)


def test_materialization_crash_never_publishes_partial_ticket_and_recovers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    assert seal.run(seal_args(fixture)) == 0
    capsys.readouterr()
    destination = tmp_path / "crash-materialized"
    destination.mkdir(mode=0o700)
    ticket = destination / "ticket"
    authority = destination / "authority.json"
    marker = destination / "commit.json"
    arguments = materialize_args(
        fixture,
        ticket=ticket,
        authority=authority,
        marker=marker,
    )
    original_link = seal.os.link
    calls = 0

    def fail_second_link(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated materialization crash")
        original_link(*args, **kwargs)

    monkeypatch.setattr(seal.os, "link", fail_second_link)
    assert materialize.run(arguments) == 2
    assert ticket.read_bytes() == INCIDENT_TICKET
    assert stat.S_IMODE(ticket.stat().st_mode) == 0o600
    assert not authority.exists()
    assert not marker.exists()
    capsys.readouterr()

    monkeypatch.setattr(seal.os, "link", original_link)
    assert materialize.run(arguments) == 0
    assert ticket.read_bytes() == INCIDENT_TICKET
    assert authority.exists()
    assert marker.exists()
    assert not list(destination.glob(".chummer-ticket-intake-*.stage"))
    assert_no_plaintext_in_public_results(capsys)


def test_mac_acl_check_uses_minimal_environment_and_rejects_acl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "private"
    target.write_bytes(b"x")
    target.chmod(0o600)
    descriptor = os.open(target, os.O_RDONLY)
    observed: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any):
        observed.update(kwargs)
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=b"file\n 0: user:someone read\n",
            stderr=b"",
        )

    monkeypatch.setattr(seal.sys, "platform", "darwin")
    monkeypatch.setattr(seal.subprocess, "run", fake_run)
    try:
        with pytest.raises(seal.SealError):
            seal._assert_no_extended_acl(descriptor, str(target))
    finally:
        os.close(descriptor)
    assert observed["env"] == seal._minimal_environment()
    assert "GIT_CONFIG" not in observed["env"]


def test_core_dump_failure_is_fail_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)

    def fail_core_limit(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("not permitted")

    monkeypatch.setattr(seal.resource, "setrlimit", fail_core_limit)
    assert seal.run(seal_args(fixture)) == 2
    assert not fixture.output.exists()
    assert_no_plaintext_in_public_results(capsys)


def test_openssl_pin_is_mandatory_and_generic_error_is_secret_free(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    arguments = seal_args(fixture)
    index = arguments.index("--openssl-sha256") + 1
    arguments[index] = "0" * 64
    assert seal.run(arguments) == 2
    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert error == {
        "contractName": seal.CONTRACT_NAME,
        "error": "secure incident-ticket sealing failed",
        "generatedAtUtc": error["generatedAtUtc"],
        "status": "error",
    }
    assert INCIDENT_TICKET.decode() not in captured.err
    assert str(fixture.crypto.signer_key) not in captured.err


def test_explicit_pinned_non_system_openssl_path_is_supported(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    portable_root = tmp_path / "opt" / "homebrew" / "bin"
    portable_root.mkdir(parents=True, mode=0o700)
    portable_openssl = portable_root / "openssl"
    shutil.copy2(fixture.crypto.openssl, portable_openssl)
    portable_openssl.chmod(0o700)
    fixture.crypto = replace(
        fixture.crypto,
        openssl=portable_openssl,
        openssl_sha256=digest(portable_openssl),
    )
    monkeypatch.setenv("PATH", str(tmp_path / "untrusted-path"))
    assert seal.run(seal_args(fixture)) == 0
    assert fixture.output.exists()
    assert_no_plaintext_in_public_results(capsys)
