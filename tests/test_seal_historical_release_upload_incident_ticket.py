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
handoff = materialize.handoff

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
    handoff_directory: Path
    output: Path
    receipt: Path
    marker: Path
    signer_transport: Path
    verification_receipt: Path
    verification_marker: Path
    verifier_repository: Path
    verifier_source_commit: str
    verifier_git: Path
    verifier_script: Path
    verifier_helper: Path
    crypto: CryptoFixture


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_verifier_source_repository(
    root: Path,
) -> tuple[Path, str, Path, Path, Path]:
    repository = root / "verifier-source"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True, mode=0o700)
    verifier_script = (
        scripts / "verify_historical_release_upload_incident_handoff.py"
    )
    verifier_helper = (
        scripts / "seal_historical_release_upload_incident_ticket.py"
    )
    verifier_script.write_bytes(Path(handoff.__file__).read_bytes())
    verifier_helper.write_bytes(
        (SCRIPT_DIRECTORY / verifier_helper.name).read_bytes()
    )
    verifier_script.chmod(0o600)
    verifier_helper.chmod(0o600)
    git = Path("/usr/bin/git")
    subprocess.run(
        (str(git), "init", "-q", str(repository)),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        (str(git), "-C", str(repository), "add", "--", "scripts"),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        (
            str(git),
            "-C",
            str(repository),
            "-c",
            "user.name=Materializer Fixture",
            "-c",
            "user.email=materializer@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    source_commit = subprocess.run(
        (str(git), "-C", str(repository), "rev-parse", "HEAD"),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout.strip()
    return (
        repository,
        source_commit,
        git,
        verifier_script,
        verifier_helper,
    )


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
        write_candidate(release_root, f"run-20260724-{index:06d}")
        for index in range(handoff.EXPECTED_CANDIDATE_COUNT)
    ]
    drop = tmp_path / "drop"
    drop.mkdir(mode=0o700)
    verification = tmp_path / "verification"
    verification.mkdir(mode=0o700)
    (
        verifier_repository,
        verifier_source_commit,
        verifier_git,
        verifier_script,
        verifier_helper,
    ) = create_verifier_source_repository(tmp_path)
    handoff._runtime_source_paths = lambda: (
        verifier_script,
        verifier_helper,
    )
    return SealFixture(
        release_root=release_root,
        lock_path=lock_path,
        targets=targets,
        handoff_directory=drop,
        output=drop / handoff.CMS_NAME,
        receipt=drop / handoff.SEAL_RECEIPT_NAME,
        marker=drop / handoff.SEAL_COMMIT_NAME,
        signer_transport=drop / handoff.SIGNER_CERT_NAME,
        verification_receipt=(
            verification / "handoff-verification.receipt.json"
        ),
        verification_marker=(
            verification / "handoff-verification.commit.json"
        ),
        verifier_repository=verifier_repository,
        verifier_source_commit=verifier_source_commit,
        verifier_git=verifier_git,
        verifier_script=verifier_script,
        verifier_helper=verifier_helper,
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


def prepare_handoff_verification(fixture: SealFixture) -> None:
    fixture.signer_transport.write_bytes(
        fixture.crypto.signer_cert.read_bytes()
    )
    fixture.signer_transport.chmod(0o600)
    receipt = json.loads(fixture.receipt.read_text(encoding="utf-8"))

    producer_openssl = fixture.crypto.openssl
    if digest(producer_openssl) != receipt["opensslExecutableSha256"]:
        selected = shutil.which("openssl")
        assert selected is not None
        producer_openssl = Path(selected).resolve()
        assert digest(producer_openssl) == receipt["opensslExecutableSha256"]
    producer_python = Path(sys.executable).resolve()
    authority = {
        "hub_commit": "a" * 40,
        "bootstrap_sha256": "b" * 64,
        "seal_script_sha256": digest(SEAL_SCRIPT),
        "seal_context_sha256": receipt["contextSha256"],
        "inventory_commitment_sha256": (
            receipt["inventoryCommitmentSha256"]
        ),
        "recipient_certificate_sha256": (
            receipt["recipientCertificateSha256"]
        ),
        "signer_certificate_sha256": (
            receipt["signerCertificateSha256"]
        ),
        "openssl_path": str(producer_openssl),
        "openssl_sha256": receipt["opensslExecutableSha256"],
        "python_path": str(producer_python),
        "python_sha256": digest(producer_python),
        "verifier_source_commit": fixture.verifier_source_commit,
        "verifier_repository_path": str(fixture.verifier_repository),
        "verifier_git_path": str(fixture.verifier_git),
        "verifier_git_sha256": digest(fixture.verifier_git),
        "verifier_script_path": str(fixture.verifier_script),
        "verifier_script_sha256": digest(fixture.verifier_script),
        "seal_helper_path": str(fixture.verifier_helper),
        "seal_helper_sha256": digest(fixture.verifier_helper),
        "verifier_python_path": str(producer_python),
        "verifier_python_sha256": digest(producer_python),
    }
    context_inputs = {
        name: handoff.artifact_record(
            (fixture.handoff_directory / name).read_bytes()
        )
        for name in handoff.HANDOFF_CONTEXT_INPUT_NAMES
    }
    handoff_context = handoff._canonical_json_sha256(
        {
            "contractName": handoff.HANDOFF_CONTEXT_CONTRACT_NAME,
            "hubCommit": authority["hub_commit"],
            "sealContextSha256": authority["seal_context_sha256"],
            "sealTransactionId": receipt["transactionId"],
            "artifacts": context_inputs,
        }
    )
    handoff_transaction = handoff_context[:32]
    acknowledgement = hashlib.sha256(
        (
            "CHUMMER_TICKET_SIGNER_CERT_SHA256="
            f"{authority['signer_certificate_sha256']}\n"
        ).encode("ascii")
    ).hexdigest()
    response = {
        "bootstrapSha256": authority["bootstrap_sha256"],
        "candidateCount": handoff.EXPECTED_CANDIDATE_COUNT,
        "containsSecretValues": False,
        "contractName": handoff.HANDOFF_CONTRACT_NAME,
        "envelopeSha256": digest(fixture.output),
        "envelopeSizeBytes": fixture.output.stat().st_size,
        "handoffContextSha256": handoff_context,
        "handoffTransactionId": handoff_transaction,
        "hubCommit": authority["hub_commit"],
        "inventoryCommitmentSha256": (
            authority["inventory_commitment_sha256"]
        ),
        "opensslPath": authority["openssl_path"],
        "opensslSha256": authority["openssl_sha256"],
        "publishersStopped": True,
        "pythonPath": authority["python_path"],
        "pythonSha256": authority["python_sha256"],
        "recipientCertSha256": authority[
            "recipient_certificate_sha256"
        ],
        "sealCommitMarkerSha256": digest(fixture.marker),
        "sealCommitMarkerSizeBytes": fixture.marker.stat().st_size,
        "sealContextSha256": authority["seal_context_sha256"],
        "sealReceiptSha256": digest(fixture.receipt),
        "sealReceiptSizeBytes": fixture.receipt.stat().st_size,
        "sealScriptSha256": authority["seal_script_sha256"],
        "sealTransactionId": receipt["transactionId"],
        "signerCertSha256": authority["signer_certificate_sha256"],
        "signerCertificatePinAcknowledgementSha256": acknowledgement,
        "sourceCandidatesLeftUntouched": True,
        "status": "sealed_pending_linux_materialization",
        "telegramSignerCertificatePinSent": True,
    }
    response_path = (
        fixture.handoff_directory / handoff.HANDOFF_RESPONSE_NAME
    )
    response_path.write_bytes(seal._canonical_json_bytes(response))
    response_path.chmod(0o600)
    handoff_commit = {
        "contractName": handoff.HANDOFF_COMMIT_CONTRACT_NAME,
        "status": "committed",
        "transactionId": handoff_transaction,
        "contextSha256": handoff_context,
        "artifacts": {
            **context_inputs,
            handoff.HANDOFF_RESPONSE_NAME: handoff.artifact_record(
                response_path.read_bytes()
            ),
        },
    }
    handoff_marker = (
        fixture.handoff_directory / handoff.HANDOFF_COMMIT_NAME
    )
    handoff_marker.write_bytes(seal._canonical_json_bytes(handoff_commit))
    handoff_marker.chmod(0o600)

    verification_args = [
        "--handoff-directory",
        str(fixture.handoff_directory),
        "--expected-hub-commit",
        authority["hub_commit"],
        "--expected-bootstrap-sha256",
        authority["bootstrap_sha256"],
        "--expected-seal-script-sha256",
        authority["seal_script_sha256"],
        "--expected-seal-context-sha256",
        authority["seal_context_sha256"],
        "--expected-inventory-commitment-sha256",
        authority["inventory_commitment_sha256"],
        "--expected-recipient-cert-sha256",
        authority["recipient_certificate_sha256"],
        "--expected-signer-cert-sha256",
        authority["signer_certificate_sha256"],
        "--expected-openssl-path",
        authority["openssl_path"],
        "--expected-openssl-sha256",
        authority["openssl_sha256"],
        "--expected-python-path",
        authority["python_path"],
        "--expected-python-sha256",
        authority["python_sha256"],
        "--expected-verifier-source-commit",
        authority["verifier_source_commit"],
        "--expected-verifier-repository-path",
        authority["verifier_repository_path"],
        "--expected-verifier-git-path",
        authority["verifier_git_path"],
        "--expected-verifier-git-sha256",
        authority["verifier_git_sha256"],
        "--expected-verifier-script-path",
        authority["verifier_script_path"],
        "--expected-verifier-script-sha256",
        authority["verifier_script_sha256"],
        "--expected-seal-helper-path",
        authority["seal_helper_path"],
        "--expected-seal-helper-sha256",
        authority["seal_helper_sha256"],
        "--expected-verifier-python-path",
        authority["verifier_python_path"],
        "--expected-verifier-python-sha256",
        authority["verifier_python_sha256"],
        "--output",
        str(fixture.verification_receipt),
        "--commit-marker",
        str(fixture.verification_marker),
        "--confirm",
        handoff.CONFIRMATION,
    ]
    verification_options = handoff.build_parser().parse_args(
        verification_args
    )
    assert handoff.verify(verification_options)["status"] == (
        "verified_pending_cryptographic_materialization"
    )
    materialize.seal = handoff.seal


def materialize_args(
    fixture: SealFixture,
    *,
    ticket: Path,
    authority: Path,
    marker: Path,
) -> list[str]:
    prepare_handoff_verification(fixture)
    crypto = fixture.crypto
    receipt = json.loads(fixture.receipt.read_text(encoding="utf-8"))
    return [
        "--handoff-directory",
        str(fixture.handoff_directory),
        "--handoff-verification-receipt",
        str(fixture.verification_receipt),
        "--handoff-verification-receipt-sha256",
        digest(fixture.verification_receipt),
        "--handoff-verification-commit",
        str(fixture.verification_marker),
        "--handoff-verification-commit-sha256",
        digest(fixture.verification_marker),
        "--openssl-path",
        str(crypto.openssl),
        "--openssl-sha256",
        crypto.openssl_sha256,
        "--seal-openssl-sha256",
        receipt["opensslExecutableSha256"],
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
        str(fixture.signer_transport),
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


@pytest.mark.parametrize("rewrite_marker_artifacts", (False, True))
def test_materialization_retry_rejects_forged_ticket_and_authority(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    rewrite_marker_artifacts: bool,
) -> None:
    fixture = build_fixture(tmp_path)
    assert seal.run(seal_args(fixture)) == 0
    capsys.readouterr()
    destination = tmp_path / "forged-materialization-retry"
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
    assert materialize.run(arguments) == 0
    capsys.readouterr()

    forged_ticket = b"attacker-controlled-ticket"
    ticket.write_bytes(forged_ticket)
    authority_payload = json.loads(authority.read_bytes())
    authority_payload["ticketSha256"] = hashlib.sha256(
        forged_ticket
    ).hexdigest()
    authority_payload["ticketSizeBytes"] = len(forged_ticket)
    authority.write_bytes(seal._canonical_json_bytes(authority_payload))
    if rewrite_marker_artifacts:
        marker_payload = json.loads(marker.read_bytes())
        ticket_bytes = ticket.read_bytes()
        authority_bytes = authority.read_bytes()
        marker_payload["artifacts"] = {
            ticket.name: {
                "sha256": hashlib.sha256(ticket_bytes).hexdigest(),
                "sizeBytes": len(ticket_bytes),
            },
            authority.name: {
                "sha256": hashlib.sha256(authority_bytes).hexdigest(),
                "sizeBytes": len(authority_bytes),
            },
        }
        marker.write_bytes(seal._canonical_json_bytes(marker_payload))

    assert materialize.run(arguments) == 2
    assert ticket.read_bytes() == forged_ticket
    assert_no_plaintext_in_public_results(capsys)


def test_materialization_retry_rejects_forged_authority_and_marker(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    assert seal.run(seal_args(fixture)) == 0
    capsys.readouterr()
    destination = tmp_path / "forged-authority-retry"
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
    assert materialize.run(arguments) == 0
    capsys.readouterr()
    original_authority = authority.read_bytes()
    original_marker = marker.read_bytes()

    authority_payload = json.loads(original_authority)
    authority_payload["envelopeSha256"] = "0" * 64
    authority.write_bytes(seal._canonical_json_bytes(authority_payload))
    marker_payload = json.loads(original_marker)
    authority_bytes = authority.read_bytes()
    marker_payload["artifacts"][authority.name] = {
        "sha256": hashlib.sha256(authority_bytes).hexdigest(),
        "sizeBytes": len(authority_bytes),
    }
    marker.write_bytes(seal._canonical_json_bytes(marker_payload))
    assert materialize.run(arguments) == 2
    assert_no_plaintext_in_public_results(capsys)

    authority.write_bytes(original_authority)
    marker_payload = json.loads(original_marker)
    marker_payload["unexpectedField"] = True
    marker.write_bytes(seal._canonical_json_bytes(marker_payload))
    assert materialize.run(arguments) == 2
    assert_no_plaintext_in_public_results(capsys)


def test_materialization_retry_rejects_boolean_one_byte_artifact_size(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    one_byte_config = b'header = "Authorization: Bearer x"\n'
    for relative in fixture.targets:
        candidate = fixture.release_root / relative
        candidate.write_bytes(one_byte_config)
        candidate.chmod(0o600)
    assert seal.run(seal_args(fixture)) == 0
    capsys.readouterr()
    destination = tmp_path / "boolean-artifact-size-retry"
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
    assert materialize.run(arguments) == 0
    assert ticket.read_bytes() == b"x"
    capsys.readouterr()

    marker_payload = json.loads(marker.read_bytes())
    marker_payload["artifacts"][ticket.name]["sizeBytes"] = True
    marker.write_bytes(seal._canonical_json_bytes(marker_payload))
    assert materialize.run(arguments) == 2
    assert_no_plaintext_in_public_results(capsys)


def test_materialization_requires_independently_pinned_verification(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    assert seal.run(seal_args(fixture)) == 0
    capsys.readouterr()
    destination = tmp_path / "verification-required"
    destination.mkdir(mode=0o700)
    arguments = materialize_args(
        fixture,
        ticket=destination / "ticket",
        authority=destination / "authority.json",
        marker=destination / "commit.json",
    )
    pin_index = (
        arguments.index("--handoff-verification-receipt-sha256") + 1
    )
    arguments[pin_index] = "0" * 64
    assert materialize.run(arguments) == 2
    assert not (destination / "ticket").exists()
    assert_no_plaintext_in_public_results(capsys)


def test_materialization_rejects_v1_verification_receipt_downgrade(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    assert seal.run(seal_args(fixture)) == 0
    capsys.readouterr()
    destination = tmp_path / "v1-downgrade"
    destination.mkdir(mode=0o700)
    arguments = materialize_args(
        fixture,
        ticket=destination / "ticket",
        authority=destination / "authority.json",
        marker=destination / "commit.json",
    )
    receipt = json.loads(fixture.verification_receipt.read_bytes())
    receipt["contractName"] = (
        "chummer.release-upload-incident-ticket-handoff-verification/v1"
    )
    fixture.verification_receipt.write_bytes(
        handoff._canonical_json_bytes(receipt)
    )
    fixture.verification_receipt.chmod(0o600)
    marker = json.loads(fixture.verification_marker.read_bytes())
    marker["artifacts"][fixture.verification_receipt.name] = (
        handoff.artifact_record(fixture.verification_receipt.read_bytes())
    )
    fixture.verification_marker.write_bytes(
        handoff._canonical_json_bytes(marker)
    )
    fixture.verification_marker.chmod(0o600)
    arguments[
        arguments.index("--handoff-verification-receipt-sha256") + 1
    ] = digest(fixture.verification_receipt)
    arguments[
        arguments.index("--handoff-verification-commit-sha256") + 1
    ] = digest(fixture.verification_marker)
    assert materialize.run(arguments) == 2
    assert not (destination / "ticket").exists()
    assert_no_plaintext_in_public_results(capsys)


def test_handoff_preparation_reuses_and_never_repairs_producer_seal_commit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    assert seal.run(seal_args(fixture)) == 0
    capsys.readouterr()
    original = fixture.marker.read_bytes()
    original_identity = (
        fixture.marker.stat().st_dev,
        fixture.marker.stat().st_ino,
        fixture.marker.stat().st_mtime_ns,
        fixture.marker.stat().st_ctime_ns,
    )
    destination = tmp_path / "producer-marker-reuse"
    destination.mkdir(mode=0o700)
    materialize_args(
        fixture,
        ticket=destination / "ticket",
        authority=destination / "authority.json",
        marker=destination / "commit.json",
    )
    assert fixture.marker.read_bytes() == original
    assert (
        fixture.marker.stat().st_dev,
        fixture.marker.stat().st_ino,
        fixture.marker.stat().st_mtime_ns,
        fixture.marker.stat().st_ctime_ns,
    ) == original_identity

    fixture.marker.write_bytes(original + b"x")
    fixture.marker.chmod(0o600)
    with pytest.raises(handoff.VerificationError):
        prepare_handoff_verification(fixture)
    assert fixture.marker.read_bytes() == original + b"x"


def test_handoff_path_replacement_after_verification_cannot_publish(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    assert seal.run(seal_args(fixture)) == 0
    capsys.readouterr()
    destination = tmp_path / "post-verification-swap"
    destination.mkdir(mode=0o700)
    arguments = materialize_args(
        fixture,
        ticket=destination / "ticket",
        authority=destination / "authority.json",
        marker=destination / "commit.json",
    )
    original_validate = materialize._validate_verification_evidence
    displaced = fixture.output.with_name(f"{fixture.output.name}.displaced")

    def replace_after_validation(*args: Any, **kwargs: Any):
        validated = original_validate(*args, **kwargs)
        os.replace(fixture.output, displaced)
        fixture.output.write_bytes(b"forged-envelope")
        fixture.output.chmod(0o600)
        return validated

    monkeypatch.setattr(
        materialize,
        "_validate_verification_evidence",
        replace_after_validation,
    )
    try:
        assert materialize.run(arguments) == 2
        assert not (destination / "ticket").exists()
        assert not (destination / "authority.json").exists()
    finally:
        fixture.output.unlink(missing_ok=True)
        os.replace(displaced, fixture.output)
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


@pytest.mark.parametrize("transaction_kind", ("seal", "materialize"))
def test_transaction_recovers_after_commit_marker_link_before_stage_unlink(
    transaction_kind: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    if transaction_kind == "seal":
        arguments = seal_args(fixture)
        execute = seal.run
        final_paths = (fixture.output, fixture.receipt, fixture.marker)
        stage_parent = fixture.output.parent
    else:
        assert seal.run(seal_args(fixture)) == 0
        capsys.readouterr()
        stage_parent = tmp_path / "materialized-after-commit-link"
        stage_parent.mkdir(mode=0o700)
        ticket = stage_parent / "ticket"
        authority = stage_parent / "authority.json"
        marker = stage_parent / "commit.json"
        arguments = materialize_args(
            fixture,
            ticket=ticket,
            authority=authority,
            marker=marker,
        )
        execute = materialize.run
        final_paths = (ticket, authority, marker)

    interrupted = False

    def patch_transaction_module(transaction_module: Any) -> None:
        original_unlink = transaction_module._safe_unlink_identity

        def interrupt_before_first_stage_unlink(
            parent_descriptor: int,
            name: str,
            expected: os.stat_result,
        ) -> None:
            nonlocal interrupted
            if not interrupted and name.startswith("artifact-"):
                interrupted = True
                raise OSError("simulated crash before staged-link cleanup")
            original_unlink(parent_descriptor, name, expected)

        transaction_module._safe_unlink_identity = (
            interrupt_before_first_stage_unlink
        )

    original_loader = handoff._load_held_helper
    if transaction_kind == "seal":
        original_unlink = seal._safe_unlink_identity
        patch_transaction_module(seal)
    else:
        def load_interrupted_helper(*args: Any, **kwargs: Any):
            loaded = original_loader(*args, **kwargs)
            patch_transaction_module(loaded)
            return loaded

        monkeypatch.setattr(
            handoff,
            "_load_held_helper",
            load_interrupted_helper,
        )
    assert execute(arguments) == 2
    assert interrupted is True
    assert all(path.exists() for path in final_paths)
    assert all(path.stat().st_nlink == 2 for path in final_paths)
    stages = list(stage_parent.glob(".chummer-ticket-intake-*.stage"))
    assert len(stages) == 1
    assert (stages[0] / "transaction.json").is_file()
    capsys.readouterr()

    if transaction_kind == "seal":
        monkeypatch.setattr(seal, "_safe_unlink_identity", original_unlink)
    else:
        monkeypatch.setattr(handoff, "_load_held_helper", original_loader)
    assert execute(arguments) == 0
    assert all(path.stat().st_nlink == 1 for path in final_paths)
    assert not list(stage_parent.glob(".chummer-ticket-intake-*.stage"))
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
    materialized = tmp_path / "materialized"
    materialized.mkdir(mode=0o700)
    arguments = materialize_args(
        fixture,
        ticket=materialized / "ticket",
        authority=materialized / "authority.json",
        marker=materialized / "commit.json",
    )
    envelope = bytearray(fixture.output.read_bytes())
    envelope[len(envelope) // 2] ^= 0x01
    fixture.output.write_bytes(envelope)
    fixture.output.chmod(0o600)
    envelope_pin = arguments.index("--envelope-sha256") + 1
    arguments[envelope_pin] = digest(fixture.output)
    assert materialize.run(arguments) == 2
    assert not (materialized / "ticket").exists()
    assert_no_plaintext_in_public_results(capsys)


def test_pinned_signer_cannot_be_substituted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    assert seal.run(seal_args(fixture)) == 0
    capsys.readouterr()
    destination = tmp_path / "wrong-signer-materialized"
    destination.mkdir(mode=0o700)
    arguments = materialize_args(
        fixture,
        ticket=destination / "ticket",
        authority=destination / "authority.json",
        marker=destination / "commit.json",
    )
    wrong_root = tmp_path / "wrong-signer"
    wrong_root.mkdir(mode=0o700)
    _wrong_key, wrong_cert = generate_identity(
        fixture.crypto.openssl,
        wrong_root,
        "wrong-signer",
    )
    fixture.signer_transport.write_bytes(wrong_cert.read_bytes())
    fixture.signer_transport.chmod(0o600)
    signer_pin = arguments.index("--signer-cert-sha256") + 1
    arguments[signer_pin] = digest(wrong_cert)
    assert materialize.run(arguments) == 2
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


def test_mac_seal_linux_materialization_accepts_distinct_pinned_openssl_binaries(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    sealing_openssl_sha256 = fixture.crypto.openssl_sha256
    assert seal.run(seal_args(fixture)) == 0
    capsys.readouterr()

    linux_openssl = tmp_path / "linux-openssl"
    shutil.copy2(fixture.crypto.openssl, linux_openssl)
    with linux_openssl.open("ab") as executable:
        executable.write(b"\n")
    linux_openssl.chmod(0o700)
    fixture.crypto = replace(
        fixture.crypto,
        openssl=linux_openssl,
        openssl_sha256=digest(linux_openssl),
    )
    assert fixture.crypto.openssl_sha256 != sealing_openssl_sha256

    destination = tmp_path / "distinct-openssl-materialized"
    destination.mkdir(mode=0o700)
    ticket = destination / "ticket"
    authority = destination / "authority.json"
    marker = destination / "commit.json"
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
    payload = json.loads(authority.read_text(encoding="utf-8"))
    assert payload["opensslExecutableSha256"] == sealing_openssl_sha256
    assert (
        payload["materializationOpensslExecutableSha256"]
        == fixture.crypto.openssl_sha256
    )
    assert ticket.read_bytes() == INCIDENT_TICKET
    assert_no_plaintext_in_public_results(capsys)
