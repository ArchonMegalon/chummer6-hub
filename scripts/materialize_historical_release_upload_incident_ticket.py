#!/usr/bin/env python3
"""Decrypt and securely materialize a sealed historical incident ticket.

This Linux-only command requires the independently pinned six-artifact handoff
verification transaction, validates the pinned EnvelopedData recipient and the
pinned inner SignedData signer from the same held handoff descriptors, then
transactionally publishes one complete owner-only raw ticket, one owner-only
authority file, and a commit marker.  The ticket digest is present only in the
private authority file; the epoch deploy must inherit an already-open
descriptor for that file and must never place the digest in argv or the
environment.  The materializer and verifier must themselves be invoked from
the independently reviewed launcher/checkout; their initial Python loader is
an explicit external trust boundary, not a self-attested claim.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence

import verify_historical_release_upload_incident_handoff as handoff


seal: Any = None


CONTRACT_NAME = (
    "chummer.release-upload-incident-ticket-materialization-authority/v2"
)
COMMIT_CONTRACT_NAME = (
    "chummer.release-upload-incident-ticket-materialization-commit/v1"
)
CONFIRMATION = "MATERIALIZE_HISTORICAL_RELEASE_UPLOAD_INCIDENT_TICKET"
SEAL_RECEIPT_FIELDS = {
    "contractName",
    "generatedAtUtc",
    "status",
    "transactionId",
    "contextSha256",
    "candidateCount",
    "distinctIncidentBearerCount",
    "inventoryCommitmentSha256",
    "cmsComposition",
    "digestAlgorithm",
    "contentEncryptionAlgorithm",
    "recipientCertificateSha256",
    "signerCertificateSha256",
    "opensslExecutableSha256",
    "envelopeSha256",
    "envelopeSizeBytes",
    "plaintextPersistedOutsidePrivateSourceCandidates",
    "plaintextEmitted",
    "quarantineStatus",
    "revocationStatus",
    "exactOldTicketRevocationProofRequired",
}
AUTHORITY_FIELDS = {
    "contractName",
    "generatedAtUtc",
    "status",
    "ticketPathSha256",
    "ticketSha256",
    "ticketSizeBytes",
    "envelopeSha256",
    "inventoryCommitmentSha256",
    "recipientCertificateSha256",
    "signerCertificateSha256",
    "opensslExecutableSha256",
    "materializationOpensslExecutableSha256",
    "handoffContextSha256",
    "handoffTransactionId",
    "handoffVerificationReceiptSha256",
    "handoffVerificationCommitSha256",
    "handoffVerificationTransactionId",
    "handoffVerifierSourceCommit",
    "handoffVerifierScriptSha256",
    "handoffSealHelperSha256",
    "handoffVerifierScriptGitBlobOid",
    "handoffSealHelperGitBlobOid",
    "handoffVerifierPythonIdentitySource",
    "handoffSealHelperLoadMode",
    "handoffInputArtifactsSha256",
    "materializationTransactionId",
    "quarantineStatus",
    "revocationStatus",
}
COMMIT_MARKER_FIELDS = {
    "contractName",
    "status",
    "transactionId",
    "contextSha256",
    "artifacts",
}
COMMIT_ARTIFACT_FIELDS = {"sha256", "sizeBytes"}


class MaterializeError(RuntimeError):
    """The authenticated ticket could not be safely materialized."""


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _is_canonical_utc_timestamp(value: Any) -> bool:
    if (
        type(value) is not str
        or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
            r"[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
            value,
        )
        is None
    ):
        return False
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo == dt.timezone.utc


def _strict_private_json(
    pinned: seal.PinnedFile,
    *,
    label: str,
) -> dict[str, Any]:
    try:
        parsed = json.loads(pinned.content)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MaterializeError(f"{label} is malformed") from exc
    if (
        not isinstance(parsed, dict)
        or seal._canonical_json_bytes(parsed) != pinned.content
    ):
        raise MaterializeError(f"{label} is not canonical JSON")
    return parsed


def _validate_seal_receipt(
    receipt: Mapping[str, Any],
    *,
    envelope: seal.PinnedFile,
    inventory_commitment_sha256: str,
    recipient_certificate_sha256: str,
    signer_certificate_sha256: str,
    sealing_openssl_executable_sha256: str,
) -> None:
    if set(receipt) != SEAL_RECEIPT_FIELDS:
        raise MaterializeError("seal receipt fields are not exact")
    if (
        receipt.get("contractName") != seal.CONTRACT_NAME
        or not _is_canonical_utc_timestamp(receipt.get("generatedAtUtc"))
        or receipt.get("status")
        != "sealed_pending_quarantine_and_revocation"
        or receipt.get("cmsComposition")
        != "authenticated-signedData-inside-envelopedData"
        or receipt.get("digestAlgorithm") != "sha256"
        or receipt.get("contentEncryptionAlgorithm") != seal.CMS_CIPHER
        or receipt.get("envelopeSha256") != envelope.sha256
        or receipt.get("envelopeSizeBytes") != len(envelope.content)
        or receipt.get("inventoryCommitmentSha256")
        != inventory_commitment_sha256
        or receipt.get("recipientCertificateSha256")
        != recipient_certificate_sha256
        or receipt.get("signerCertificateSha256")
        != signer_certificate_sha256
        or receipt.get("opensslExecutableSha256")
        != sealing_openssl_executable_sha256
        or receipt.get("plaintextEmitted") is not False
        or receipt.get("quarantineStatus") != "pending"
        or receipt.get("revocationStatus") != "pending"
        or receipt.get("exactOldTicketRevocationProofRequired") is not True
        or type(receipt.get("candidateCount")) is not int
        or receipt["candidateCount"] < 1
        or receipt.get("distinctIncidentBearerCount") != 1
        or type(receipt.get("transactionId")) is not str
        or seal.TRANSACTION_ID.fullmatch(receipt["transactionId"]) is None
        or any(
            type(receipt.get(field)) is not str
            or seal.SHA256_HEX.fullmatch(receipt[field]) is None
            for field in (
                "contextSha256",
                "inventoryCommitmentSha256",
                "recipientCertificateSha256",
                "signerCertificateSha256",
                "opensslExecutableSha256",
                "envelopeSha256",
            )
        )
        or type(receipt.get("envelopeSizeBytes")) is not int
        or receipt["envelopeSizeBytes"] < 1
    ):
        raise MaterializeError("seal receipt binding is invalid")


def _validate_envelope_structure(
    *,
    executable: seal.PinnedFile,
    envelope: bytes,
    recipient_certificate: seal.PinnedFile,
) -> None:
    rendered = seal._cms_print(executable, envelope)
    serial = seal._certificate_serial(executable, recipient_certificate)
    recipient_infos = seal._cms_named_section(rendered, "recipientInfos:")
    if (
        seal.CMS_ENVELOPED_TYPE not in rendered
        or seal.CMS_AES256_ALGORITHM not in rendered
        or not seal._cms_section_has_one_serial(recipient_infos, serial)
        or seal.CMS_RSA_KEY_ALGORITHM not in recipient_infos
    ):
        raise MaterializeError("envelope recipient or algorithm is invalid")


def _decrypt_signed_cms(
    *,
    executable: seal.PinnedFile,
    envelope: bytes,
    recipient_certificate: seal.PinnedFile,
    recipient_key: seal.PinnedFile,
) -> bytes:
    signed = seal._execute_pinned_openssl(
        executable,
        (
            "cms",
            "-decrypt",
            "-binary",
            "-inform",
            "DER",
            "-recip",
            recipient_certificate.descriptor_path,
            "-inkey",
            recipient_key.descriptor_path,
        ),
        input_bytes=envelope,
        inherited_descriptors=(
            recipient_certificate.descriptor,
            recipient_key.descriptor,
        ),
        maximum_output_bytes=seal.MAX_CMS_BYTES,
    )
    if not signed:
        raise MaterializeError("decrypted SignedData is empty")
    return signed


def _verify_signed_ticket(
    *,
    executable: seal.PinnedFile,
    signed: bytes,
    signer_certificate: seal.PinnedFile,
) -> bytearray:
    rendered = seal._cms_print(executable, signed)
    serial = seal._certificate_serial(executable, signer_certificate)
    signer_infos = seal._cms_named_section(rendered, "signerInfos:")
    if (
        seal.CMS_SIGNED_TYPE not in rendered
        or seal.CMS_SHA256_ALGORITHM not in signer_infos
        or not seal._cms_section_has_one_serial(signer_infos, serial)
        or not any(
            algorithm in signer_infos
            for algorithm in seal.CMS_ALLOWED_SIGNATURE_ALGORITHMS
        )
    ):
        raise MaterializeError("SignedData signer or algorithm is invalid")
    ticket = seal._execute_pinned_openssl(
        executable,
        (
            "cms",
            "-verify",
            "-binary",
            "-inform",
            "DER",
            "-nointern",
            "-certfile",
            signer_certificate.descriptor_path,
            "-noverify",
        ),
        input_bytes=signed,
        inherited_descriptors=(signer_certificate.descriptor,),
        maximum_output_bytes=seal.MAX_TICKET_BYTES,
    )
    try:
        return bytearray(seal._validate_ticket(ticket))
    except seal.SealError as exc:
        raise MaterializeError("verified ticket is not canonical") from exc


def _read_committed_authority(
    authority_path: Path,
    *,
    transaction_id: str,
    context_sha256: str,
) -> dict[str, Any] | None:
    if not authority_path.exists():
        return None
    parent_descriptor = seal._open_absolute_directory(
        authority_path.parent,
        owner_only=True,
    )
    try:
        content, _metadata = seal._read_private_file_at(
            parent_descriptor,
            authority_path.name,
            maximum_bytes=8192,
        )
    finally:
        os.close(parent_descriptor)
    try:
        authority = json.loads(content)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MaterializeError("materialization authority is malformed") from exc
    if (
        not isinstance(authority, dict)
        or set(authority) != AUTHORITY_FIELDS
        or seal._canonical_json_bytes(authority) != content
        or authority.get("contractName") != CONTRACT_NAME
        or not _is_canonical_utc_timestamp(authority.get("generatedAtUtc"))
        or authority.get("materializationTransactionId") != transaction_id
        or authority.get("status") != "materialized_pending_revocation"
        or authority.get("quarantineStatus") != "pending"
        or authority.get("revocationStatus") != "pending"
        or type(authority.get("materializationTransactionId")) is not str
        or seal.TRANSACTION_ID.fullmatch(
            authority["materializationTransactionId"]
        )
        is None
        or type(authority.get("ticketSizeBytes")) is not int
        or not 0 < authority["ticketSizeBytes"] <= seal.MAX_TICKET_BYTES
        or any(
            type(authority.get(field)) is not str
            or seal.SHA256_HEX.fullmatch(authority[field]) is None
            for field in (
                "ticketPathSha256",
                "ticketSha256",
                "envelopeSha256",
                "inventoryCommitmentSha256",
                "recipientCertificateSha256",
                "signerCertificateSha256",
                "opensslExecutableSha256",
                "materializationOpensslExecutableSha256",
                "handoffContextSha256",
                "handoffVerificationReceiptSha256",
                "handoffVerificationCommitSha256",
                "handoffVerifierScriptSha256",
                "handoffSealHelperSha256",
                "handoffInputArtifactsSha256",
            )
        )
        or any(
            type(authority.get(field)) is not str
            or seal.TRANSACTION_ID.fullmatch(authority[field]) is None
            for field in (
                "handoffTransactionId",
                "handoffVerificationTransactionId",
            )
        )
        or type(authority.get("handoffVerifierSourceCommit")) is not str
        or handoff.GIT_COMMIT.fullmatch(
            authority["handoffVerifierSourceCommit"]
        )
        is None
        or any(
            type(authority.get(field)) is not str
            or handoff.GIT_COMMIT.fullmatch(authority[field]) is None
            for field in (
                "handoffVerifierScriptGitBlobOid",
                "handoffSealHelperGitBlobOid",
            )
        )
        or authority.get("handoffVerifierPythonIdentitySource")
        != handoff.PYTHON_IDENTITY_SOURCE
        or authority.get("handoffSealHelperLoadMode")
        != handoff.SEAL_HELPER_LOAD_MODE
    ):
        raise MaterializeError("materialization authority is invalid")
    # The transaction context is intentionally not a field in the epoch
    # authority.  Its deterministic transaction id is the binding.
    if transaction_id != context_sha256[:32]:
        raise MaterializeError("materialization context binding is invalid")
    return authority


def _validate_final_materialization(
    *,
    ticket_path: Path,
    authority_path: Path,
    commit_marker_path: Path,
    authority: Mapping[str, Any],
    expected_ticket: bytes | bytearray,
    transaction_id: str,
    context_sha256: str,
) -> None:
    parent, parent_descriptor = seal._ensure_same_private_parent(
        (ticket_path, authority_path, commit_marker_path)
    )
    del parent
    try:
        ticket, _ = seal._read_private_file_at(
            parent_descriptor,
            ticket_path.name,
            maximum_bytes=seal.MAX_TICKET_BYTES,
        )
        authority_bytes, _ = seal._read_private_file_at(
            parent_descriptor,
            authority_path.name,
            maximum_bytes=8192,
        )
        marker_bytes, _ = seal._read_private_file_at(
            parent_descriptor,
            commit_marker_path.name,
            maximum_bytes=8192,
        )
    finally:
        os.close(parent_descriptor)
    try:
        marker = json.loads(marker_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MaterializeError("materialization marker is malformed") from exc
    expected_artifacts = {
        ticket_path.name: {
            "sha256": hashlib.sha256(ticket).hexdigest(),
            "sizeBytes": len(ticket),
        },
        authority_path.name: {
            "sha256": hashlib.sha256(authority_bytes).hexdigest(),
            "sizeBytes": len(authority_bytes),
        },
    }
    artifacts = marker.get("artifacts") if isinstance(marker, dict) else None
    if (
        seal._canonical_json_bytes(dict(authority)) != authority_bytes
        or not isinstance(marker, dict)
        or set(marker) != COMMIT_MARKER_FIELDS
        or seal._canonical_json_bytes(marker) != marker_bytes
        or marker.get("contractName") != COMMIT_CONTRACT_NAME
        or marker.get("status") != "committed"
        or marker.get("transactionId") != transaction_id
        or marker.get("contextSha256") != context_sha256
        or not isinstance(artifacts, dict)
        or set(artifacts) != set(expected_artifacts)
        or not hmac.compare_digest(ticket, expected_ticket)
        or authority.get("ticketSha256")
        != hashlib.sha256(ticket).hexdigest()
        or authority.get("ticketSizeBytes") != len(ticket)
        or authority.get("ticketPathSha256")
        != hashlib.sha256(str(ticket_path).encode("utf-8")).hexdigest()
    ):
        raise MaterializeError("committed materialization binding is invalid")
    for name, expected in expected_artifacts.items():
        artifact = artifacts[name]
        if (
            not isinstance(artifact, dict)
            or set(artifact) != COMMIT_ARTIFACT_FIELDS
            or type(artifact.get("sha256")) is not str
            or type(artifact.get("sizeBytes")) is not int
            or artifact["sha256"] != expected["sha256"]
            or artifact["sizeBytes"] != expected["sizeBytes"]
        ):
            raise MaterializeError(
                "committed materialization artifact binding is invalid"
            )


def _borrow_held_input(item: handoff.HeldInput) -> seal.PinnedFile:
    descriptor = os.dup(item.descriptor)
    try:
        os.set_inheritable(descriptor, False)
        metadata = os.fstat(descriptor)
        return seal.PinnedFile(
            path=item.path,
            descriptor=descriptor,
            metadata=metadata,
            content=item.content,
            sha256=item.sha256,
        )
    except BaseException:
        os.close(descriptor)
        raise


def _verification_authority(
    receipt: Mapping[str, Any],
) -> handoff.IndependentAuthority:
    return handoff._authority(
        argparse.Namespace(
            expected_hub_commit=receipt.get("hubCommit"),
            expected_bootstrap_sha256=receipt.get("bootstrapSha256"),
            expected_seal_script_sha256=receipt.get("sealScriptSha256"),
            expected_seal_context_sha256=receipt.get("sealContextSha256"),
            expected_inventory_commitment_sha256=receipt.get(
                "inventoryCommitmentSha256"
            ),
            expected_recipient_cert_sha256=receipt.get(
                "recipientCertificateSha256"
            ),
            expected_signer_cert_sha256=receipt.get(
                "signerCertificateSha256"
            ),
            expected_openssl_path=receipt.get("producerOpensslPath"),
            expected_openssl_sha256=receipt.get("producerOpensslSha256"),
            expected_python_path=receipt.get("producerPythonPath"),
            expected_python_sha256=receipt.get("producerPythonSha256"),
            expected_verifier_source_commit=receipt.get(
                "verifierSourceCommit"
            ),
            expected_verifier_repository_path=receipt.get(
                "verifierRepositoryPath"
            ),
            expected_verifier_git_path=receipt.get("verifierGitPath"),
            expected_verifier_git_sha256=receipt.get("verifierGitSha256"),
            expected_verifier_script_path=receipt.get("verifierScriptPath"),
            expected_verifier_script_sha256=receipt.get(
                "verifierScriptSha256"
            ),
            expected_seal_helper_path=receipt.get("sealHelperPath"),
            expected_seal_helper_sha256=receipt.get("sealHelperSha256"),
            expected_verifier_python_path=receipt.get("verifierPythonPath"),
            expected_verifier_python_sha256=receipt.get(
                "verifierPythonSha256"
            ),
        )
    )


def _validate_verification_evidence(
    *,
    verification_receipt: handoff.HeldInput,
    verification_commit: handoff.HeldInput,
    inputs: Mapping[str, handoff.HeldInput],
) -> tuple[
    Mapping[str, Any],
    handoff.IndependentAuthority,
    handoff.ValidatedHandoff,
]:
    receipt = handoff._strict_json(
        verification_receipt.content,
        label="handoff verification receipt",
    )
    commit = handoff._strict_json(
        verification_commit.content,
        label="handoff verification commit",
    )
    if set(receipt) != handoff.VERIFICATION_RECEIPT_FIELDS:
        raise MaterializeError("handoff verification receipt fields are not exact")
    handoff._timestamp(receipt.get("generatedAtUtc"))
    authority = _verification_authority(receipt)
    validated = handoff._validate_handoff(inputs, authority)
    expected_artifacts = {
        name: inputs[name].artifact()
        for name in handoff.INPUT_NAMES
    }
    if (
        not isinstance(receipt.get("inputArtifacts"), dict)
        or set(receipt["inputArtifacts"]) != set(expected_artifacts)
    ):
        raise MaterializeError(
            "handoff verification input artifacts are not exact"
        )
    for name, artifact in expected_artifacts.items():
        handoff._artifact_record(
            receipt["inputArtifacts"].get(name),
            expected=artifact,
            label=f"handoff verification {name}",
        )

    context_sha256 = handoff._sha256(
        receipt.get("contextSha256"),
        label="handoff verification context",
    )
    transaction_id = handoff._transaction_id(
        receipt.get("transactionId"),
        label="handoff verification transaction",
    )
    handoff_context = handoff._sha256(
        receipt.get("handoffContextSha256"),
        label="handoff context",
    )
    handoff_transaction = handoff._transaction_id(
        receipt.get("handoffTransactionId"),
        label="handoff transaction",
    )
    seal_transaction = handoff._transaction_id(
        receipt.get("sealTransactionId"),
        label="seal transaction",
    )
    expected_context = handoff._verification_context(
        output=verification_receipt.path,
        commit_marker=verification_commit.path,
        authority=authority,
        handoff_context_sha256=handoff_context,
    )
    if (
        receipt.get("contractName") != handoff.CONTRACT_NAME
        or receipt.get("status")
        != "verified_pending_cryptographic_materialization"
        or context_sha256 != expected_context
        or transaction_id != context_sha256[:32]
        or handoff_context
        != validated.response.get("handoffContextSha256")
        or handoff_transaction
        != validated.response.get("handoffTransactionId")
        or receipt.get("sealContextSha256")
        != authority.seal_context_sha256
        or seal_transaction
        != validated.seal_receipt.get("transactionId")
        or receipt.get("candidateCount") != handoff.EXPECTED_CANDIDATE_COUNT
        or type(receipt.get("candidateCount")) is not int
        or receipt.get("inventoryCommitmentSha256")
        != authority.inventory_commitment_sha256
        or receipt.get("hubCommit") != authority.hub_commit
        or receipt.get("bootstrapSha256") != authority.bootstrap_sha256
        or receipt.get("sealScriptSha256")
        != authority.seal_script_sha256
        or receipt.get("recipientCertificateSha256")
        != authority.recipient_certificate_sha256
        or receipt.get("signerCertificateSha256")
        != authority.signer_certificate_sha256
        or receipt.get("producerOpensslPath") != authority.openssl_path
        or receipt.get("producerOpensslSha256") != authority.openssl_sha256
        or receipt.get("producerPythonPath") != authority.python_path
        or receipt.get("producerPythonSha256") != authority.python_sha256
        or receipt.get("verifierSourceCommit")
        != authority.verifier_source_commit
        or receipt.get("verifierRepositoryPath")
        != authority.verifier_repository_path
        or receipt.get("verifierGitPath") != authority.verifier_git_path
        or receipt.get("verifierGitSha256")
        != authority.verifier_git_sha256
        or receipt.get("verifierScriptPath")
        != authority.verifier_script_path
        or receipt.get("verifierScriptSha256")
        != authority.verifier_script_sha256
        or receipt.get("sealHelperPath") != authority.seal_helper_path
        or receipt.get("sealHelperSha256")
        != authority.seal_helper_sha256
        or receipt.get("verifierScriptGitBlobOid")
        != authority.verifier_script_git_blob_oid
        or receipt.get("sealHelperGitBlobOid")
        != authority.seal_helper_git_blob_oid
        or receipt.get("verifierPythonIdentitySource")
        != authority.verifier_python_identity_source
        or receipt.get("sealHelperLoadMode")
        != authority.seal_helper_load_mode
        or receipt.get("verifierPythonPath")
        != authority.verifier_python_path
        or receipt.get("verifierPythonSha256")
        != authority.verifier_python_sha256
        or receipt.get("transportReadbackPassed") is not True
        or receipt.get("producerReportedSourceCandidatesLeftUntouched")
        is not True
        or receipt.get("producerReportedPublishersStopped") is not True
        or receipt.get("producerReportedContainsSecretValues") is not False
        or receipt.get("verifierOutputContainsSecretValues") is not False
        or receipt.get("cmsCryptographicVerificationStatus")
        != "pending_linux_materialization"
    ):
        raise MaterializeError("handoff verification authority is invalid")
    handoff._validate_transaction(
        commit,
        contract_name=handoff.COMMIT_CONTRACT_NAME,
        transaction_id=transaction_id,
        context_sha256=context_sha256,
        expected_artifacts={
            verification_receipt.path.name: verification_receipt.artifact()
        },
        label="handoff verification commit",
    )
    return receipt, authority, validated


def _materialization_handoff_binding(
    *,
    verification_receipt: handoff.HeldInput,
    verification_commit: handoff.HeldInput,
    verification: Mapping[str, Any],
    authority: handoff.IndependentAuthority,
    validated: handoff.ValidatedHandoff,
) -> dict[str, str]:
    return {
        "handoffContextSha256": validated.response["handoffContextSha256"],
        "handoffTransactionId": validated.response["handoffTransactionId"],
        "handoffVerificationReceiptSha256": verification_receipt.sha256,
        "handoffVerificationCommitSha256": verification_commit.sha256,
        "handoffVerificationTransactionId": verification["transactionId"],
        "handoffVerifierSourceCommit": authority.verifier_source_commit,
        "handoffVerifierScriptSha256": authority.verifier_script_sha256,
        "handoffSealHelperSha256": authority.seal_helper_sha256,
        "handoffVerifierScriptGitBlobOid": (
            authority.verifier_script_git_blob_oid
        ),
        "handoffSealHelperGitBlobOid": authority.seal_helper_git_blob_oid,
        "handoffVerifierPythonIdentitySource": (
            authority.verifier_python_identity_source
        ),
        "handoffSealHelperLoadMode": authority.seal_helper_load_mode,
        "handoffInputArtifactsSha256": handoff._canonical_json_sha256(
            validated.artifacts
        ),
    }


def _validate_authority_handoff_binding(
    authority: Mapping[str, Any],
    *,
    expected: Mapping[str, str],
) -> None:
    if any(authority.get(field) != value for field, value in expected.items()):
        raise MaterializeError(
            "materialization authority handoff binding is invalid"
        )


def _validate_authority_request_binding(
    authority: Mapping[str, Any],
    *,
    expected: Mapping[str, Any],
) -> None:
    if (
        set(expected) != AUTHORITY_FIELDS - {"generatedAtUtc"}
        or any(authority.get(field) != value for field, value in expected.items())
    ):
        raise MaterializeError(
            "materialization authority request binding is invalid"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-directory", type=Path, required=True)
    parser.add_argument(
        "--handoff-verification-receipt",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--handoff-verification-receipt-sha256",
        required=True,
    )
    parser.add_argument(
        "--handoff-verification-commit",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--handoff-verification-commit-sha256",
        required=True,
    )
    parser.add_argument("--openssl-path", type=Path, required=True)
    parser.add_argument("--openssl-sha256", required=True)
    parser.add_argument("--seal-openssl-sha256", required=True)
    parser.add_argument("--envelope", type=Path, required=True)
    parser.add_argument("--envelope-sha256", required=True)
    parser.add_argument("--seal-receipt", type=Path, required=True)
    parser.add_argument("--seal-receipt-sha256", required=True)
    parser.add_argument("--inventory-commitment-sha256", required=True)
    parser.add_argument("--recipient-cert", type=Path, required=True)
    parser.add_argument("--recipient-cert-sha256", required=True)
    parser.add_argument("--recipient-key", type=Path, required=True)
    parser.add_argument("--recipient-key-sha256", required=True)
    parser.add_argument("--signer-cert", type=Path, required=True)
    parser.add_argument("--signer-cert-sha256", required=True)
    parser.add_argument("--ticket-output", type=Path, required=True)
    parser.add_argument("--authority-output", type=Path, required=True)
    parser.add_argument("--commit-marker", type=Path, required=True)
    parser.add_argument("--confirm", required=True)
    return parser


def materialize(options: argparse.Namespace) -> Mapping[str, Any]:
    global seal
    handoff._disable_core_dumps()
    if not sys.platform.startswith("linux"):
        raise MaterializeError("ticket materialization is Linux-only")
    if options.confirm != CONFIRMATION:
        raise MaterializeError(f"--confirm requires {CONFIRMATION}")
    verification_receipt_sha256 = handoff._sha256(
        options.handoff_verification_receipt_sha256,
        label="handoff verification receipt SHA-256",
    )
    verification_commit_sha256 = handoff._sha256(
        options.handoff_verification_commit_sha256,
        label="handoff verification commit SHA-256",
    )
    openssl_sha256 = handoff._sha256(
        options.openssl_sha256,
        label="materialization OpenSSL executable SHA-256",
    )
    seal_openssl_sha256 = handoff._sha256(
        options.seal_openssl_sha256,
        label="sealing OpenSSL executable SHA-256",
    )
    envelope_sha256 = handoff._sha256(
        options.envelope_sha256,
        label="envelope SHA-256",
    )
    seal_receipt_sha256 = handoff._sha256(
        options.seal_receipt_sha256,
        label="seal receipt SHA-256",
    )
    inventory_commitment = handoff._sha256(
        options.inventory_commitment_sha256,
        label="inventory commitment SHA-256",
    )
    recipient_sha256 = handoff._sha256(
        options.recipient_cert_sha256,
        label="recipient certificate SHA-256",
    )
    recipient_key_sha256 = handoff._sha256(
        options.recipient_key_sha256,
        label="recipient key SHA-256",
    )
    signer_sha256 = handoff._sha256(
        options.signer_cert_sha256,
        label="signer certificate SHA-256",
    )
    expected_handoff_paths = {
        name: options.handoff_directory / name
        for name in handoff.INPUT_NAMES
    }
    if (
        not options.handoff_directory.is_absolute()
        or options.envelope != expected_handoff_paths[handoff.CMS_NAME]
        or options.seal_receipt
        != expected_handoff_paths[handoff.SEAL_RECEIPT_NAME]
        or options.signer_cert
        != expected_handoff_paths[handoff.SIGNER_CERT_NAME]
        or not options.handoff_verification_receipt.is_absolute()
        or not options.handoff_verification_commit.is_absolute()
        or options.handoff_verification_receipt.name in {"", ".", ".."}
        or options.handoff_verification_commit.name in {"", ".", ".."}
    ):
        raise MaterializeError("handoff materialization paths are not exact")
    executable: seal.PinnedFile | None = None
    verification_receipt_input: handoff.HeldInput | None = None
    verification_commit_input: handoff.HeldInput | None = None
    handoff_inputs: dict[str, handoff.HeldInput] = {}
    envelope: seal.PinnedFile | None = None
    seal_receipt: seal.PinnedFile | None = None
    recipient_certificate: seal.PinnedFile | None = None
    recipient_key: seal.PinnedFile | None = None
    signer_certificate: seal.PinnedFile | None = None
    ticket = bytearray()
    try:
        verification_receipt_input = handoff._open_held_input(
            options.handoff_verification_receipt,
            maximum_bytes=2 * 1024 * 1024,
        )
        verification_commit_input = handoff._open_held_input(
            options.handoff_verification_commit,
            maximum_bytes=2 * 1024 * 1024,
        )
        if (
            verification_receipt_input.sha256
            != verification_receipt_sha256
            or verification_commit_input.sha256
            != verification_commit_sha256
        ):
            raise MaterializeError(
                "handoff verification artifact pin mismatch"
            )
        for name in handoff.INPUT_NAMES:
            handoff_inputs[name] = handoff._open_held_input(
                expected_handoff_paths[name],
                maximum_bytes=handoff.MAXIMUM_BYTES[name],
            )
        if (
            handoff_inputs[handoff.CMS_NAME].sha256 != envelope_sha256
            or handoff_inputs[handoff.SEAL_RECEIPT_NAME].sha256
            != seal_receipt_sha256
            or handoff_inputs[handoff.SIGNER_CERT_NAME].sha256
            != signer_sha256
        ):
            raise MaterializeError("handoff input pin mismatch")
        verification, verification_authority, validated_handoff = (
            _validate_verification_evidence(
                verification_receipt=verification_receipt_input,
                verification_commit=verification_commit_input,
                inputs=handoff_inputs,
            )
        )
        seal = handoff.seal
        if seal is None:
            raise MaterializeError("reviewed seal helper was not loaded")
        _parent, validation_descriptor = seal._ensure_same_private_parent(
            (
                options.ticket_output,
                options.authority_output,
                options.commit_marker,
            )
        )
        os.close(validation_descriptor)
        executable = seal._open_pinned_executable(
            options.openssl_path,
            openssl_sha256,
        )
        handoff_binding = _materialization_handoff_binding(
            verification_receipt=verification_receipt_input,
            verification_commit=verification_commit_input,
            verification=verification,
            authority=verification_authority,
            validated=validated_handoff,
        )
        envelope = _borrow_held_input(
            handoff_inputs[handoff.CMS_NAME]
        )
        seal_receipt = _borrow_held_input(
            handoff_inputs[handoff.SEAL_RECEIPT_NAME]
        )
        signer_certificate = _borrow_held_input(
            handoff_inputs[handoff.SIGNER_CERT_NAME]
        )
        receipt = _strict_private_json(
            seal_receipt,
            label="seal receipt",
        )
        _validate_seal_receipt(
            receipt,
            envelope=envelope,
            inventory_commitment_sha256=inventory_commitment,
            recipient_certificate_sha256=recipient_sha256,
            signer_certificate_sha256=signer_sha256,
            sealing_openssl_executable_sha256=seal_openssl_sha256,
        )
        recipient_certificate = seal._open_pinned_file(
            options.recipient_cert,
            recipient_sha256,
            label="recipient certificate",
            maximum_bytes=256 * 1024,
            owner_only=False,
        )
        recipient_key = seal._open_pinned_file(
            options.recipient_key,
            recipient_key_sha256,
            label="recipient private key",
            maximum_bytes=256 * 1024,
            owner_only=True,
            retain_content=False,
        )
        _validate_envelope_structure(
            executable=executable,
            envelope=envelope.content,
            recipient_certificate=recipient_certificate,
        )
        signed = _decrypt_signed_cms(
            executable=executable,
            envelope=envelope.content,
            recipient_certificate=recipient_certificate,
            recipient_key=recipient_key,
        )
        ticket = _verify_signed_ticket(
            executable=executable,
            signed=signed,
            signer_certificate=signer_certificate,
        )
        for name, item in handoff_inputs.items():
            item.readback(maximum_bytes=handoff.MAXIMUM_BYTES[name])
        verification_receipt_input.readback(
            maximum_bytes=seal.MAX_TRANSACTION_FILE_BYTES
        )
        verification_commit_input.readback(
            maximum_bytes=seal.MAX_TRANSACTION_FILE_BYTES
        )
        ticket_path = options.ticket_output
        context_sha256 = seal._canonical_json_sha256(
            {
                "contractName": CONTRACT_NAME,
                "ticketPathSha256": hashlib.sha256(
                    str(ticket_path).encode("utf-8")
                ).hexdigest(),
                "envelopeSha256": envelope_sha256,
                "inventoryCommitmentSha256": inventory_commitment,
                "recipientCertificateSha256": recipient_sha256,
                "signerCertificateSha256": signer_sha256,
                "opensslExecutableSha256": seal_openssl_sha256,
                "materializationOpensslExecutableSha256": openssl_sha256,
                "ticketOutputName": ticket_path.name,
                "authorityOutputName": options.authority_output.name,
                "commitMarkerName": options.commit_marker.name,
                **handoff_binding,
            }
        )
        transaction_id = context_sha256[:32]
        authority_binding = {
            "contractName": CONTRACT_NAME,
            "status": "materialized_pending_revocation",
            "ticketPathSha256": hashlib.sha256(
                str(ticket_path).encode("utf-8")
            ).hexdigest(),
            "ticketSha256": hashlib.sha256(ticket).hexdigest(),
            "ticketSizeBytes": len(ticket),
            "envelopeSha256": envelope_sha256,
            "inventoryCommitmentSha256": inventory_commitment,
            "recipientCertificateSha256": recipient_sha256,
            "signerCertificateSha256": signer_sha256,
            "opensslExecutableSha256": seal_openssl_sha256,
            "materializationOpensslExecutableSha256": openssl_sha256,
            **handoff_binding,
            "materializationTransactionId": transaction_id,
            "quarantineStatus": "pending",
            "revocationStatus": "pending",
        }
        seal._recover_fully_linked_transaction(
            final_paths=(
                ticket_path,
                options.authority_output,
                options.commit_marker,
            ),
            transaction_id=transaction_id,
            context_sha256=context_sha256,
        )
        existing = _read_committed_authority(
            options.authority_output,
            transaction_id=transaction_id,
            context_sha256=context_sha256,
        )
        if existing is not None:
            _validate_authority_handoff_binding(
                existing,
                expected=handoff_binding,
            )
            _validate_authority_request_binding(
                existing,
                expected=authority_binding,
            )
            _validate_final_materialization(
                ticket_path=ticket_path,
                authority_path=options.authority_output,
                commit_marker_path=options.commit_marker,
                authority=existing,
                expected_ticket=ticket,
                transaction_id=transaction_id,
                context_sha256=context_sha256,
            )
            return {
                "contractName": CONTRACT_NAME,
                "status": "materialized_pending_revocation",
                "materializationTransactionId": transaction_id,
                "authorityFileReadyForInheritedFd": True,
                "quarantineStatus": "pending",
                "revocationStatus": "pending",
            }

        authority = {
            "generatedAtUtc": seal._utc_now(),
            **authority_binding,
        }
        if set(authority) != AUTHORITY_FIELDS:
            raise MaterializeError("materialization authority fields changed")
        seal._publish_transaction(
            outputs={
                ticket_path: bytes(ticket),
                options.authority_output: seal._canonical_json_bytes(authority),
            },
            commit_marker_path=options.commit_marker,
            transaction_id=transaction_id,
            context_sha256=context_sha256,
            commit_contract_name=COMMIT_CONTRACT_NAME,
        )
        committed = _read_committed_authority(
            options.authority_output,
            transaction_id=transaction_id,
            context_sha256=context_sha256,
        )
        if committed is None:
            raise MaterializeError("materialization authority was not committed")
        _validate_authority_handoff_binding(
            committed,
            expected=handoff_binding,
        )
        _validate_authority_request_binding(
            committed,
            expected=authority_binding,
        )
        _validate_final_materialization(
            ticket_path=ticket_path,
            authority_path=options.authority_output,
            commit_marker_path=options.commit_marker,
            authority=committed,
            expected_ticket=ticket,
            transaction_id=transaction_id,
            context_sha256=context_sha256,
        )
        return {
            "contractName": CONTRACT_NAME,
            "status": "materialized_pending_revocation",
            "materializationTransactionId": transaction_id,
            "authorityFileReadyForInheritedFd": True,
            "quarantineStatus": "pending",
            "revocationStatus": "pending",
        }
    finally:
        for index in range(len(ticket)):
            ticket[index] = 0
        if signer_certificate is not None:
            signer_certificate.close()
        if recipient_key is not None:
            recipient_key.close()
        if recipient_certificate is not None:
            recipient_certificate.close()
        if seal_receipt is not None:
            seal_receipt.close()
        if envelope is not None:
            envelope.close()
        if executable is not None:
            executable.close()
        for item in reversed(tuple(handoff_inputs.values())):
            item.close()
        if verification_commit_input is not None:
            verification_commit_input.close()
        if verification_receipt_input is not None:
            verification_receipt_input.close()


def run(arguments: Sequence[str] | None = None) -> int:
    try:
        handoff._disable_core_dumps()
        options = build_parser().parse_args(arguments)
        result = materialize(options)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (
        MaterializeError,
        handoff.VerificationError,
        RuntimeError,
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ):
        print(
            json.dumps(
                {
                    "contractName": CONTRACT_NAME,
                    "generatedAtUtc": _utc_now(),
                    "status": "error",
                    "error": "secure incident-ticket materialization failed",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
