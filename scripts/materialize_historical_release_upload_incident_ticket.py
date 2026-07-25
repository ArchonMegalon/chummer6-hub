#!/usr/bin/env python3
"""Decrypt and securely materialize a sealed historical incident ticket.

This Linux-only command validates the pinned EnvelopedData recipient and the
pinned inner SignedData signer before it publishes any plaintext.  It
transactionally publishes one complete owner-only raw ticket, one owner-only
authority file, and a commit marker.  The ticket digest is present only in the
private authority file; the epoch deploy must inherit an already-open
descriptor for that file and must never place the digest in argv or the
environment.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence

import seal_historical_release_upload_incident_ticket as seal


CONTRACT_NAME = (
    "chummer.release-upload-incident-ticket-materialization-authority/v1"
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
    "materializationTransactionId",
    "quarantineStatus",
    "revocationStatus",
}


class MaterializeError(RuntimeError):
    """The authenticated ticket could not be safely materialized."""


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
            )
        )
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
    if (
        seal._canonical_json_bytes(dict(authority)) != authority_bytes
        or not isinstance(marker, dict)
        or seal._canonical_json_bytes(marker) != marker_bytes
        or marker.get("contractName") != COMMIT_CONTRACT_NAME
        or marker.get("status") != "committed"
        or marker.get("transactionId") != transaction_id
        or marker.get("contextSha256") != context_sha256
        or authority.get("ticketSha256")
        != hashlib.sha256(ticket).hexdigest()
        or authority.get("ticketSizeBytes") != len(ticket)
        or authority.get("ticketPathSha256")
        != hashlib.sha256(str(ticket_path).encode("utf-8")).hexdigest()
    ):
        raise MaterializeError("committed materialization binding is invalid")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
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
    seal._disable_core_dumps()
    if not sys.platform.startswith("linux"):
        raise MaterializeError("ticket materialization is Linux-only")
    if options.confirm != CONFIRMATION:
        raise MaterializeError(f"--confirm requires {CONFIRMATION}")
    openssl_sha256 = seal._validate_sha256(
        options.openssl_sha256,
        "materialization OpenSSL executable SHA-256",
    )
    seal_openssl_sha256 = seal._validate_sha256(
        options.seal_openssl_sha256,
        "sealing OpenSSL executable SHA-256",
    )
    envelope_sha256 = seal._validate_sha256(
        options.envelope_sha256,
        "envelope SHA-256",
    )
    seal_receipt_sha256 = seal._validate_sha256(
        options.seal_receipt_sha256,
        "seal receipt SHA-256",
    )
    inventory_commitment = seal._validate_sha256(
        options.inventory_commitment_sha256,
        "inventory commitment SHA-256",
    )
    recipient_sha256 = seal._validate_sha256(
        options.recipient_cert_sha256,
        "recipient certificate SHA-256",
    )
    recipient_key_sha256 = seal._validate_sha256(
        options.recipient_key_sha256,
        "recipient key SHA-256",
    )
    signer_sha256 = seal._validate_sha256(
        options.signer_cert_sha256,
        "signer certificate SHA-256",
    )
    _parent, validation_descriptor = seal._ensure_same_private_parent(
        (
            options.ticket_output,
            options.authority_output,
            options.commit_marker,
        )
    )
    os.close(validation_descriptor)

    executable: seal.PinnedFile | None = None
    envelope: seal.PinnedFile | None = None
    seal_receipt: seal.PinnedFile | None = None
    recipient_certificate: seal.PinnedFile | None = None
    recipient_key: seal.PinnedFile | None = None
    signer_certificate: seal.PinnedFile | None = None
    ticket = bytearray()
    try:
        executable = seal._open_pinned_executable(
            options.openssl_path,
            openssl_sha256,
        )
        envelope = seal._open_pinned_file(
            options.envelope,
            envelope_sha256,
            label="CMS envelope",
            maximum_bytes=seal.MAX_CMS_BYTES,
            owner_only=False,
        )
        seal_receipt = seal._open_pinned_file(
            options.seal_receipt,
            seal_receipt_sha256,
            label="seal receipt",
            maximum_bytes=8192,
            owner_only=True,
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
        signer_certificate = seal._open_pinned_file(
            options.signer_cert,
            signer_sha256,
            label="signer certificate",
            maximum_bytes=256 * 1024,
            owner_only=False,
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
            }
        )
        transaction_id = context_sha256[:32]
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
            _validate_final_materialization(
                ticket_path=ticket_path,
                authority_path=options.authority_output,
                commit_marker_path=options.commit_marker,
                authority=existing,
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
            "contractName": CONTRACT_NAME,
            "generatedAtUtc": seal._utc_now(),
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
            "materializationTransactionId": transaction_id,
            "quarantineStatus": "pending",
            "revocationStatus": "pending",
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
        _validate_final_materialization(
            ticket_path=ticket_path,
            authority_path=options.authority_output,
            commit_marker_path=options.commit_marker,
            authority=committed,
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


def run(arguments: Sequence[str] | None = None) -> int:
    try:
        seal._disable_core_dumps()
        options = build_parser().parse_args(arguments)
        result = materialize(options)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (
        MaterializeError,
        seal.SealError,
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ):
        print(
            json.dumps(
                {
                    "contractName": CONTRACT_NAME,
                    "generatedAtUtc": seal._utc_now(),
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
