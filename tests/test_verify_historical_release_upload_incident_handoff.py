from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import types
from typing import Any, Callable

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIRECTORY = ROOT / "scripts"
SCRIPT = (
    SCRIPT_DIRECTORY
    / "verify_historical_release_upload_incident_handoff.py"
)
SEAL_HELPER = (
    SCRIPT_DIRECTORY
    / "seal_historical_release_upload_incident_ticket.py"
)
sys.path.insert(0, str(SCRIPT_DIRECTORY))
import seal_historical_release_upload_incident_ticket as fixture_seal


def load_script():
    spec = importlib.util.spec_from_file_location(
        "incident_ticket_handoff_verifier_test",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


verifier = load_script()


@dataclass
class Fixture:
    handoff: Path
    output: Path
    marker: Path
    authority: dict[str, str]


def canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def artifact(content: bytes) -> dict[str, Any]:
    return {"sha256": digest(content), "sizeBytes": len(content)}


def write_private(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    path.chmod(0o600)


def create_source_repository(
    root: Path,
) -> tuple[Path, str, Path, Path, Path]:
    repository = root / "verifier-source"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True, mode=0o700)
    verifier_copy = scripts / SCRIPT.name
    helper_copy = scripts / SEAL_HELPER.name
    write_private(verifier_copy, SCRIPT.read_bytes())
    write_private(helper_copy, SEAL_HELPER.read_bytes())
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
            "user.name=Verifier Fixture",
            "-c",
            "user.email=verifier@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    commit = subprocess.run(
        (str(git), "-C", str(repository), "rev-parse", "HEAD"),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout.strip()
    return repository, commit, git, verifier_copy, helper_copy


def build_fixture(tmp_path: Path) -> Fixture:
    tmp_path.mkdir(parents=True, exist_ok=True)
    handoff = tmp_path / "handoff"
    handoff.mkdir(mode=0o700)
    results = tmp_path / "results"
    results.mkdir(mode=0o700)
    (
        source_repository,
        source_commit,
        git,
        verifier_copy,
        helper_copy,
    ) = create_source_repository(tmp_path)
    verifier._runtime_source_paths = lambda: (
        verifier_copy,
        helper_copy,
    )

    cms = b"\x30\x03\x02\x01\x00"
    signer_certificate = (
        b"-----BEGIN CERTIFICATE-----\n"
        b"ZmFrZS1jZXJ0aWZpY2F0ZQ==\n"
        b"-----END CERTIFICATE-----\n"
    )
    authority = {
        "hub_commit": "1" * 40,
        "bootstrap_sha256": "2" * 64,
        "seal_script_sha256": "3" * 64,
        "seal_context_sha256": "4" * 64,
        "inventory_commitment_sha256": "5" * 64,
        "recipient_certificate_sha256": "6" * 64,
        "signer_certificate_sha256": digest(signer_certificate),
        "openssl_path": "/usr/bin/openssl",
        "openssl_sha256": "7" * 64,
        "python_path": "/usr/bin/python3",
        "python_sha256": "8" * 64,
        "verifier_source_commit": source_commit,
        "verifier_repository_path": str(source_repository),
        "verifier_git_path": str(git),
        "verifier_git_sha256": digest(git.read_bytes()),
        "verifier_script_path": str(verifier_copy),
        "verifier_script_sha256": digest(verifier_copy.read_bytes()),
        "seal_helper_path": str(helper_copy),
        "seal_helper_sha256": digest(helper_copy.read_bytes()),
        "verifier_python_path": str(Path(sys.executable).resolve()),
        "verifier_python_sha256": digest(
            Path(sys.executable).resolve().read_bytes()
        ),
    }
    seal_transaction = authority["seal_context_sha256"][:32]
    seal_receipt = {
        "contractName": fixture_seal.CONTRACT_NAME,
        "generatedAtUtc": "2026-07-26T01:00:00Z",
        "status": "sealed_pending_quarantine_and_revocation",
        "transactionId": seal_transaction,
        "contextSha256": authority["seal_context_sha256"],
        "candidateCount": 14,
        "distinctIncidentBearerCount": 1,
        "inventoryCommitmentSha256": (
            authority["inventory_commitment_sha256"]
        ),
        "cmsComposition": (
            "authenticated-signedData-inside-envelopedData"
        ),
        "digestAlgorithm": "sha256",
        "contentEncryptionAlgorithm": fixture_seal.CMS_CIPHER,
        "recipientCertificateSha256": (
            authority["recipient_certificate_sha256"]
        ),
        "signerCertificateSha256": (
            authority["signer_certificate_sha256"]
        ),
        "opensslExecutableSha256": authority["openssl_sha256"],
        "envelopeSha256": digest(cms),
        "envelopeSizeBytes": len(cms),
        "plaintextPersistedOutsidePrivateSourceCandidates": False,
        "plaintextEmitted": False,
        "quarantineStatus": "pending",
        "revocationStatus": "pending",
        "exactOldTicketRevocationProofRequired": True,
    }
    seal_receipt_bytes = canonical(seal_receipt)
    seal_commit = {
        "contractName": fixture_seal.COMMIT_CONTRACT_NAME,
        "status": "committed",
        "transactionId": seal_transaction,
        "contextSha256": authority["seal_context_sha256"],
        "artifacts": {
            verifier.CMS_NAME: artifact(cms),
            verifier.SEAL_RECEIPT_NAME: artifact(seal_receipt_bytes),
        },
    }
    seal_commit_bytes = canonical(seal_commit)
    context_inputs = {
        verifier.CMS_NAME: artifact(cms),
        verifier.SEAL_RECEIPT_NAME: artifact(seal_receipt_bytes),
        verifier.SEAL_COMMIT_NAME: artifact(seal_commit_bytes),
        verifier.SIGNER_CERT_NAME: artifact(signer_certificate),
    }
    handoff_context = verifier._canonical_json_sha256(
        {
            "contractName": verifier.HANDOFF_CONTEXT_CONTRACT_NAME,
            "hubCommit": authority["hub_commit"],
            "sealContextSha256": authority["seal_context_sha256"],
            "sealTransactionId": seal_transaction,
            "artifacts": context_inputs,
        }
    )
    handoff_transaction = handoff_context[:32]
    acknowledgement = digest(
        (
            "CHUMMER_TICKET_SIGNER_CERT_SHA256="
            f"{authority['signer_certificate_sha256']}\n"
        ).encode("ascii")
    )
    response = {
        "bootstrapSha256": authority["bootstrap_sha256"],
        "candidateCount": 14,
        "containsSecretValues": False,
        "contractName": verifier.HANDOFF_CONTRACT_NAME,
        "envelopeSha256": digest(cms),
        "envelopeSizeBytes": len(cms),
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
        "recipientCertSha256": authority["recipient_certificate_sha256"],
        "sealCommitMarkerSha256": digest(seal_commit_bytes),
        "sealCommitMarkerSizeBytes": len(seal_commit_bytes),
        "sealContextSha256": authority["seal_context_sha256"],
        "sealReceiptSha256": digest(seal_receipt_bytes),
        "sealReceiptSizeBytes": len(seal_receipt_bytes),
        "sealScriptSha256": authority["seal_script_sha256"],
        "sealTransactionId": seal_transaction,
        "signerCertSha256": authority["signer_certificate_sha256"],
        "signerCertificatePinAcknowledgementSha256": acknowledgement,
        "sourceCandidatesLeftUntouched": True,
        "status": "sealed_pending_linux_materialization",
        "telegramSignerCertificatePinSent": True,
    }
    response_bytes = canonical(response)
    handoff_commit = {
        "contractName": verifier.HANDOFF_COMMIT_CONTRACT_NAME,
        "status": "committed",
        "transactionId": handoff_transaction,
        "contextSha256": handoff_context,
        "artifacts": {
            **context_inputs,
            verifier.HANDOFF_RESPONSE_NAME: artifact(response_bytes),
        },
    }
    handoff_commit_bytes = canonical(handoff_commit)
    contents = {
        verifier.CMS_NAME: cms,
        verifier.SEAL_RECEIPT_NAME: seal_receipt_bytes,
        verifier.SEAL_COMMIT_NAME: seal_commit_bytes,
        verifier.SIGNER_CERT_NAME: signer_certificate,
        verifier.HANDOFF_RESPONSE_NAME: response_bytes,
        verifier.HANDOFF_COMMIT_NAME: handoff_commit_bytes,
    }
    for name, content in contents.items():
        write_private(handoff / name, content)
    return Fixture(
        handoff=handoff,
        output=results / "handoff-verification.receipt.json",
        marker=results / "handoff-verification.commit.json",
        authority=authority,
    )


def arguments(fixture: Fixture) -> list[str]:
    authority = fixture.authority
    return [
        "--handoff-directory",
        str(fixture.handoff),
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
        str(fixture.output),
        "--commit-marker",
        str(fixture.marker),
        "--confirm",
        verifier.CONFIRMATION,
    ]


def invoke(fixture: Fixture) -> dict[str, Any]:
    options = verifier.build_parser().parse_args(arguments(fixture))
    return dict(verifier.verify(options))


def rewrite_json(
    path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    payload = json.loads(path.read_bytes())
    mutate(payload)
    write_private(path, canonical(payload))


def test_verifies_exact_six_artifact_commit_last_handoff(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    result = invoke(fixture)
    assert result["status"] == "verified_pending_cryptographic_materialization"
    assert result["containsSecretValues"] is False
    assert stat.S_IMODE(fixture.output.stat().st_mode) == 0o600
    assert stat.S_IMODE(fixture.marker.stat().st_mode) == 0o600
    receipt = json.loads(fixture.output.read_bytes())
    assert set(receipt) == verifier.VERIFICATION_RECEIPT_FIELDS
    assert receipt["transportReadbackPassed"] is True
    assert receipt["producerReportedPublishersStopped"] is True
    assert receipt["verifierOutputContainsSecretValues"] is False
    assert receipt["cmsCryptographicVerificationStatus"] == (
        "pending_linux_materialization"
    )
    assert verifier.GIT_COMMIT.fullmatch(
        receipt["verifierScriptGitBlobOid"]
    )
    assert verifier.GIT_COMMIT.fullmatch(
        receipt["sealHelperGitBlobOid"]
    )
    assert receipt["verifierPythonIdentitySource"] == "proc-self-exe"
    assert receipt["sealHelperLoadMode"] == "held-commit-blob"
    assert verifier.seal is not fixture_seal
    assert verifier.seal.__name__.startswith(
        "_chummer_attested_ticket_seal_"
    )
    assert invoke(fixture) == result


@pytest.mark.parametrize("name", verifier.INPUT_NAMES)
def test_rejects_tamper_in_each_committed_input(
    tmp_path: Path,
    name: str,
) -> None:
    fixture = build_fixture(tmp_path)
    path = fixture.handoff / name
    write_private(path, path.read_bytes() + b"x")
    with pytest.raises(verifier.VerificationError):
        invoke(fixture)
    assert not fixture.output.exists()
    assert not fixture.marker.exists()


def test_rejects_circularly_rehashed_unpinned_signer(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    signer = fixture.handoff / verifier.SIGNER_CERT_NAME
    write_private(
        signer,
        b"-----BEGIN CERTIFICATE-----\nZm9yZ2Vk\n"
        b"-----END CERTIFICATE-----\n",
    )
    with pytest.raises(verifier.VerificationError):
        invoke(fixture)


def test_rejects_independently_unpinned_seal_context(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    fixture.authority["seal_context_sha256"] = "9" * 64
    with pytest.raises(verifier.VerificationError):
        invoke(fixture)


def test_exact_absolute_path_rejects_parent_segments() -> None:
    with pytest.raises(
        verifier.VerificationError,
        match="differs from independent authority",
    ):
        verifier._exact_absolute_path(
            "/reviewed/../substituted",
            expected="/reviewed/../substituted",
            label="reviewed path",
        )


def test_rejects_nonexistent_claimed_verifier_source_commit(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    fixture.authority["verifier_source_commit"] = "9" * 40
    with pytest.raises(verifier.VerificationError):
        invoke(fixture)


def test_rejects_runtime_helper_even_when_attacker_rehashes_its_pin(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    helper = Path(fixture.authority["seal_helper_path"])
    write_private(helper, helper.read_bytes() + b"\n# substituted\n")
    fixture.authority["seal_helper_sha256"] = digest(helper.read_bytes())
    with pytest.raises(
        verifier.VerificationError,
        match="differs from reviewed commit",
    ):
        invoke(fixture)


def test_rejects_non_regular_helper_mode_in_reviewed_tree(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    git = fixture.authority["verifier_git_path"]
    repository = fixture.authority["verifier_repository_path"]
    object_id = subprocess.run(
        (git, "-C", repository, "hash-object", "-w", "--stdin"),
        input=b"forged-helper-target",
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout.decode("ascii").strip()
    subprocess.run(
        (
            git,
            "-C",
            repository,
            "update-index",
            "--add",
            "--cacheinfo",
            f"120000,{object_id},{verifier.SEAL_HELPER_RELATIVE_PATH}",
        ),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        (
            git,
            "-C",
            repository,
            "-c",
            "user.name=Verifier Fixture",
            "-c",
            "user.email=verifier@example.invalid",
            "commit",
            "-q",
            "-m",
            "invalid helper mode",
        ),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    fixture.authority["verifier_source_commit"] = subprocess.run(
        (git, "-C", repository, "rev-parse", "HEAD"),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout.strip()
    with pytest.raises(
        verifier.VerificationError,
        match="tree mode",
    ):
        invoke(fixture)


def test_rejects_unpinned_git_runtime(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    fixture.authority["verifier_git_sha256"] = "0" * 64
    with pytest.raises(verifier.VerificationError):
        invoke(fixture)


def test_rejects_identical_python_copy_that_is_not_running_interpreter(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    copied_python = tmp_path / "copied-python"
    copied_python.write_bytes(Path(sys.executable).resolve().read_bytes())
    copied_python.chmod(0o700)
    fixture.authority["verifier_python_path"] = str(copied_python)
    fixture.authority["verifier_python_sha256"] = digest(
        copied_python.read_bytes()
    )
    with pytest.raises(
        verifier.VerificationError,
        match="Python differs",
    ):
        invoke(fixture)


def test_source_provenance_closes_all_held_descriptors(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    before = set(Path("/proc/self/fd").iterdir())
    invoke(fixture)
    after = set(Path("/proc/self/fd").iterdir())
    assert after == before


def test_source_provenance_uses_bounded_extended_fsck_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    original = verifier._execute_pinned_git
    fsck_timeouts: list[int] = []

    def record_timeout(*args: Any, **kwargs: Any) -> bytes:
        arguments = args[2] if len(args) > 2 else kwargs["arguments"]
        if arguments and arguments[0] == "fsck":
            fsck_timeouts.append(kwargs["timeout_seconds"])
        return original(*args, **kwargs)

    monkeypatch.setattr(verifier, "_execute_pinned_git", record_timeout)
    invoke(fixture)
    assert fsck_timeouts == [verifier.GIT_FSCK_TIMEOUT_SECONDS]
    assert verifier.GIT_FSCK_TIMEOUT_SECONDS == 5 * 60


def test_non_fsck_git_command_rejects_extended_timeout() -> None:
    with pytest.raises(
        verifier.VerificationError,
        match="timeout is invalid",
    ):
        verifier._execute_pinned_git(
            None,
            -1,
            ("cat-file", "-t", "0" * 40),
            timeout_seconds=verifier.GIT_FSCK_TIMEOUT_SECONDS,
        )


def test_preloaded_helper_module_is_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    forged = types.ModuleType(
        "seal_historical_release_upload_incident_ticket"
    )
    forged.CONTRACT_NAME = "forged"
    monkeypatch.setitem(
        sys.modules,
        "seal_historical_release_upload_incident_ticket",
        forged,
    )
    invoke(fixture)
    assert verifier.seal is not forged
    assert verifier.seal.CONTRACT_NAME == fixture_seal.CONTRACT_NAME


def test_helper_path_swap_during_commit_read_fails_before_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    helper = Path(fixture.authority["seal_helper_path"])
    displaced = helper.with_name(f"{helper.name}.displaced")
    original = verifier._read_committed_source_blob
    swapped = False

    def swap_after_helper_blob(*args: Any, **kwargs: Any):
        nonlocal swapped
        result = original(*args, **kwargs)
        if kwargs.get("relative_path") == verifier.SEAL_HELPER_RELATIVE_PATH:
            os.replace(helper, displaced)
            write_private(helper, b"raise RuntimeError('forged helper')\n")
            swapped = True
        return result

    monkeypatch.setattr(
        verifier,
        "_read_committed_source_blob",
        swap_after_helper_blob,
    )
    try:
        with pytest.raises(verifier.VerificationError, match="changed"):
            invoke(fixture)
        assert swapped
        assert not fixture.output.exists()
    finally:
        helper.unlink(missing_ok=True)
        os.replace(displaced, helper)


def test_rejects_noncanonical_duplicate_json_fields(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    response = fixture.handoff / verifier.HANDOFF_RESPONSE_NAME
    raw = response.read_bytes()
    write_private(response, raw[:-2] + b',\"STATUS\":\"forged\"}\n')
    with pytest.raises(verifier.VerificationError, match="duplicate"):
        invoke(fixture)


def test_rejects_boolean_candidate_count(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    rewrite_json(
        fixture.handoff / verifier.SEAL_RECEIPT_NAME,
        lambda payload: payload.__setitem__("candidateCount", True),
    )
    with pytest.raises(verifier.VerificationError):
        invoke(fixture)


def test_rejects_hardlinked_or_writable_input(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    source = fixture.handoff / verifier.CMS_NAME
    os.link(source, fixture.handoff / "cms-hardlink")
    with pytest.raises(verifier.VerificationError, match="permissions"):
        invoke(fixture)
    (fixture.handoff / "cms-hardlink").unlink()
    source.chmod(0o622)
    with pytest.raises(verifier.VerificationError, match="permissions"):
        invoke(fixture)


def test_rejects_input_mutation_before_final_readback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    original = verifier._validate_handoff

    def mutate_after_validation(inputs, authority):
        validated = original(inputs, authority)
        response = fixture.handoff / verifier.HANDOFF_RESPONSE_NAME
        write_private(response, response.read_bytes() + b"x")
        return validated

    monkeypatch.setattr(verifier, "_validate_handoff", mutate_after_validation)
    with pytest.raises(verifier.VerificationError, match="changed"):
        invoke(fixture)
    assert not fixture.output.exists()


def test_accepts_unrelated_parent_directory_content_churn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    original = verifier._validate_handoff

    def churn_after_validation(inputs, authority):
        validated = original(inputs, authority)
        unrelated = tmp_path / "unrelated-entry"
        unrelated.write_bytes(b"unrelated\n")
        unrelated.unlink()
        return validated

    monkeypatch.setattr(verifier, "_validate_handoff", churn_after_validation)
    assert invoke(fixture)["status"] == (
        "verified_pending_cryptographic_materialization"
    )


def test_fifo_substitution_is_opened_nonblocking_and_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    target = fixture.handoff / verifier.CMS_NAME
    real_open = verifier.os.open
    substituted = False
    nonblocking = False

    def substitute_before_open(path, flags, *args, **kwargs):
        nonlocal substituted, nonblocking
        if path == verifier.CMS_NAME and not substituted:
            target.unlink()
            os.mkfifo(target, 0o600)
            substituted = True
            nonblocking = bool(flags & os.O_NONBLOCK)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(verifier.os, "open", substitute_before_open)
    started = time.monotonic()
    with pytest.raises(verifier.VerificationError):
        verifier._open_held_input(
            target,
            maximum_bytes=verifier.MAXIMUM_BYTES[verifier.CMS_NAME],
        )
    assert time.monotonic() - started < 1
    assert substituted
    assert nonblocking


def test_failed_post_open_binding_check_closes_all_descriptors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture(tmp_path)
    target = fixture.handoff / verifier.CMS_NAME
    before = set(Path("/proc/self/fd").iterdir())

    def reject_binding(_self) -> None:
        raise verifier.VerificationError("injected binding failure")

    monkeypatch.setattr(verifier.HeldInput, "assert_bound", reject_binding)
    with pytest.raises(verifier.VerificationError, match="injected"):
        verifier._open_held_input(
            target,
            maximum_bytes=verifier.MAXIMUM_BYTES[verifier.CMS_NAME],
        )
    after = set(Path("/proc/self/fd").iterdir())
    assert after == before


def test_rejects_semantic_forgery_even_with_rehashed_handoff_commit(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    response_path = fixture.handoff / verifier.HANDOFF_RESPONSE_NAME
    response = json.loads(response_path.read_bytes())
    response["publishersStopped"] = False
    response_bytes = canonical(response)
    write_private(response_path, response_bytes)
    commit_path = fixture.handoff / verifier.HANDOFF_COMMIT_NAME
    commit = json.loads(commit_path.read_bytes())
    commit["artifacts"][verifier.HANDOFF_RESPONSE_NAME] = artifact(
        response_bytes
    )
    write_private(commit_path, canonical(commit))
    with pytest.raises(
        verifier.VerificationError,
        match="response authority binding",
    ):
        invoke(fixture)


def test_existing_output_tamper_or_partial_transaction_is_never_overwritten(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    invoke(fixture)
    original_marker = fixture.marker.read_bytes()
    write_private(fixture.output, fixture.output.read_bytes() + b"x")
    with pytest.raises(verifier.VerificationError):
        invoke(fixture)
    assert fixture.marker.read_bytes() == original_marker

    partial = build_fixture(tmp_path / "partial")
    write_private(partial.output, b"preexisting unrelated output\n")
    with pytest.raises(
        verifier.VerificationError,
        match="partially published",
    ):
        invoke(partial)
    assert partial.output.read_bytes() == b"preexisting unrelated output\n"
    assert not partial.marker.exists()


def test_generic_run_error_does_not_disclose_authority(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = build_fixture(tmp_path)
    fixture.authority["signer_certificate_sha256"] = "f" * 64
    assert verifier.run(arguments(fixture)) == 2
    captured = capsys.readouterr()
    assert "secure incident-ticket handoff verification failed" in captured.err
    assert fixture.authority["signer_certificate_sha256"] not in captured.err
    assert captured.out == ""
