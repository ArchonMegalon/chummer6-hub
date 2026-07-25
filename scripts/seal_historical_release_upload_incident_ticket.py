#!/usr/bin/env python3
"""Authenticate and encrypt the one historical release-upload incident ticket.

The command must run while every current macOS release publisher honors the
shared root lock.  Publishers hold the lock shared; this command holds it
exclusive while it performs two descriptor-based inventories, signs the exact
ticket, encrypts the signed CMS object, validates the resulting CMS structure,
and transactionally publishes the envelope and redacted receipt.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import stat
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence


CONTRACT_NAME = "chummer.release-upload-incident-ticket-seal/v2"
COMMIT_CONTRACT_NAME = (
    "chummer.release-upload-incident-ticket-seal-commit/v1"
)
TRANSACTION_CONTRACT_NAME = (
    "chummer.release-upload-incident-ticket-transaction/v1"
)
TRANSACTION_ARTIFACT_FIELDS = {
    "stageFile",
    "sha256",
    "sizeBytes",
    "device",
    "inode",
}
PUBLISHER_LOCK_CONTRACT = "chummer.mac-release-root-publisher-lock/v1\n"
PUBLISHER_LOCK_NAME = ".chummer-release-publisher.lock"
CONFIRMATION = "SEAL_HISTORICAL_RELEASE_UPLOAD_INCIDENT_TICKET"
TARGET_FILE_NAME = "upload-auth.curl"
MAX_TICKET_BYTES = 16 * 1024
MAX_CONFIG_BYTES = 1024 * 1024
MAX_CMS_BYTES = MAX_TICKET_BYTES + 256 * 1024
MAX_EXECUTABLE_BYTES = 128 * 1024 * 1024
MAX_TRANSACTION_FILE_BYTES = 2 * 1024 * 1024
CMS_CIPHER = "aes-256-cbc"
SHA256_HEX = re.compile(r"\A[0-9a-f]{64}\Z")
TRANSACTION_ID = re.compile(r"\A[0-9a-f]{32}\Z")
TOKEN_BYTES = rb"[A-Za-z0-9._~+/=-]+"
HEADER_LINE = re.compile(
    rb'\A[ \t]*header[ \t]*=[ \t]*"Authorization:[ \t]+'
    rb"Bearer[ \t]+(" + TOKEN_BYTES + rb')"[ \t]*\Z'
)
OAUTH2_LINE = re.compile(
    rb'\A[ \t]*oauth2-bearer[ \t]*=[ \t]*"('
    + TOKEN_BYTES
    + rb')"[ \t]*\Z'
)
CREDENTIAL_LIKE = re.compile(
    rb"(?i)(authorization|bearer|oauth2-bearer|[ \t]*header[ \t]*=)"
)
PRINTABLE_ASCII_TOKEN = re.compile(rb"\A[\x21-\x7e]+\Z")
CMS_SIGNED_TYPE = "contentType: pkcs7-signedData"
CMS_ENVELOPED_TYPE = "contentType: pkcs7-envelopedData"
CMS_SHA256_ALGORITHM = "algorithm: sha256"
CMS_AES256_ALGORITHM = "algorithm: aes-256-cbc"
CMS_RSA_KEY_ALGORITHM = "algorithm: rsaEncryption"
CMS_ALLOWED_SIGNATURE_ALGORITHMS = (
    "algorithm: rsaEncryption",
    "algorithm: rsassaPss",
    "algorithm: ecdsa-with-SHA256",
)


class SealError(RuntimeError):
    """The incident ticket could not be sealed safely."""


@dataclass
class PinnedFile:
    path: Path
    descriptor: int
    metadata: os.stat_result
    content: bytes
    sha256: str

    @property
    def descriptor_path(self) -> str:
        return f"/dev/fd/{self.descriptor}"

    def close(self) -> None:
        os.close(self.descriptor)


@dataclass
class Candidate:
    relative_path: str
    parent_descriptor: int
    descriptor: int
    metadata: os.stat_result
    content: bytes
    content_sha256: str

    def close(self) -> None:
        os.close(self.descriptor)
        os.close(self.parent_descriptor)

    def canonical_record(self) -> dict[str, Any]:
        return {
            "relativePath": self.relative_path,
            "contentSha256": self.content_sha256,
            "device": self.metadata.st_dev,
            "inode": self.metadata.st_ino,
            "uid": self.metadata.st_uid,
            "mode": stat.S_IMODE(self.metadata.st_mode),
            "linkCount": self.metadata.st_nlink,
            "sizeBytes": self.metadata.st_size,
            "modifiedTimeNs": self.metadata.st_mtime_ns,
        }


@dataclass
class Inventory:
    candidates: list[Candidate]

    def close(self) -> None:
        for candidate in self.candidates:
            candidate.close()

    def records(self) -> list[dict[str, Any]]:
        return [
            candidate.canonical_record()
            for candidate in sorted(
                self.candidates,
                key=lambda item: item.relative_path,
            )
        ]

    def commitment(self) -> str:
        return _canonical_json_sha256(
            {
                "contractName": (
                    "chummer.release-upload-credential-inventory/v1"
                ),
                "targetFileName": TARGET_FILE_NAME,
                "candidates": self.records(),
            }
        )


@dataclass
class PublisherLease:
    release_root: Path
    root_descriptor: int
    lock_descriptor: int
    lock_metadata: os.stat_result

    def close(self) -> None:
        try:
            fcntl.flock(self.lock_descriptor, fcntl.LOCK_UN)
        finally:
            os.close(self.lock_descriptor)
            os.close(self.root_descriptor)


def _disable_core_dumps() -> None:
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (OSError, ValueError) as exc:
        raise SealError("unable to disable core dumps") from exc


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value).rstrip(b"\n")).hexdigest()


def _validate_sha256(value: str, label: str) -> str:
    if SHA256_HEX.fullmatch(value) is None:
        raise SealError(f"{label} must be canonical lowercase SHA-256")
    return value


def _minimal_environment() -> dict[str, str]:
    return {
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "TMPDIR": "/tmp",
    }


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _file_open_flags(*, writable: bool = False) -> int:
    return (
        (os.O_RDWR if writable else os.O_RDONLY)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _assert_no_extended_acl(descriptor: int, label: str) -> None:
    if sys.platform != "darwin":
        return
    completed = subprocess.run(
        (
            "/bin/ls",
            "-L",
            "-l",
            "-d",
            "-e",
            f"/dev/fd/{descriptor}",
        ),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_minimal_environment(),
        pass_fds=(descriptor,),
        timeout=10,
    )
    if completed.returncode != 0:
        raise SealError(f"unable to verify macOS ACL confinement: {label}")
    if len(completed.stdout.splitlines()) != 1:
        raise SealError(f"extended ACL prevents confinement: {label}")


def _open_absolute_directory(
    path: Path,
    *,
    owner_only: bool,
    allow_root_owner: bool = False,
) -> int:
    if not path.is_absolute():
        raise SealError("directory path must be absolute")
    descriptor = os.open(os.sep, _directory_open_flags())
    try:
        for component in path.parts[1:]:
            if component in ("", ".", ".."):
                raise SealError("directory path is not canonical")
            next_descriptor = os.open(
                component,
                _directory_open_flags(),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise SealError("directory path is not a directory")
        permitted_owners = (
            {0, os.geteuid()} if allow_root_owner else {os.geteuid()}
        )
        if metadata.st_uid not in permitted_owners:
            raise SealError("directory is not owned by the current user")
        disallowed = 0o077 if owner_only else 0o022
        if stat.S_IMODE(metadata.st_mode) & disallowed:
            raise SealError("directory permissions are not confined")
        _assert_no_extended_acl(descriptor, str(path))
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_relative_directory(
    parent_descriptor: int,
    name: str,
    *,
    label: str,
) -> int:
    if name in ("", ".", "..") or os.sep in name:
        raise SealError("unsafe directory entry")
    try:
        descriptor = os.open(
            name,
            _directory_open_flags(),
            dir_fd=parent_descriptor,
        )
    except OSError as exc:
        raise SealError(f"unable to open release directory: {label}") from exc
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        os.close(descriptor)
        raise SealError(f"unsafe release directory: {label}")
    _assert_no_extended_acl(descriptor, label)
    return descriptor


def _read_descriptor(
    descriptor: int,
    *,
    maximum_bytes: int,
    label: str,
) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = maximum_bytes + 1
    while remaining:
        chunk = os.read(descriptor, min(65536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    content = b"".join(chunks)
    if len(content) > maximum_bytes:
        raise SealError(f"{label} exceeds the safe size limit")
    return content


def _open_regular_at(
    parent_descriptor: int,
    name: str,
    *,
    display_path: Path,
    maximum_bytes: int,
    owner_only: bool,
    allow_root_owner: bool = False,
    maximum_links: int = 1,
    retain_content: bool = True,
) -> PinnedFile:
    if name in ("", ".", "..") or os.sep in name:
        raise SealError("unsafe regular-file name")
    initial = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    if (
        not stat.S_ISREG(initial.st_mode)
        or stat.S_ISLNK(initial.st_mode)
        or initial.st_nlink < 1
        or initial.st_nlink > maximum_links
    ):
        raise SealError(f"unsafe regular file: {display_path}")
    descriptor = os.open(
        name,
        _file_open_flags(),
        dir_fd=parent_descriptor,
    )
    try:
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != initial.st_dev
            or opened.st_ino != initial.st_ino
            or opened.st_mode != initial.st_mode
            or opened.st_size != initial.st_size
            or opened.st_nlink < 1
            or opened.st_nlink > maximum_links
        ):
            raise SealError(f"regular file changed while opening: {display_path}")
        permitted_owners = (
            {0, os.geteuid()} if allow_root_owner else {os.geteuid()}
        )
        if opened.st_uid not in permitted_owners:
            raise SealError(f"regular file is not owner-owned: {display_path}")
        disallowed = 0o077 if owner_only else 0o022
        if stat.S_IMODE(opened.st_mode) & disallowed:
            raise SealError(f"regular file permissions are unsafe: {display_path}")
        _assert_no_extended_acl(descriptor, str(display_path))
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        digest = hashlib.sha256()
        total_size = 0
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            digest.update(chunk)
            if retain_content:
                chunks.append(chunk)
            total_size += len(chunk)
            remaining -= len(chunk)
        if total_size > maximum_bytes:
            raise SealError(f"{display_path} exceeds the safe size limit")
        content = b"".join(chunks) if retain_content else b""
        final = os.fstat(descriptor)
        if (
            final.st_dev != opened.st_dev
            or final.st_ino != opened.st_ino
            or final.st_mode != opened.st_mode
            or final.st_size != opened.st_size
            or final.st_mtime_ns != opened.st_mtime_ns
            or final.st_nlink < 1
            or final.st_nlink > maximum_links
            or total_size != opened.st_size
        ):
            raise SealError(f"regular file changed while reading: {display_path}")
        return PinnedFile(
            path=display_path,
            descriptor=descriptor,
            metadata=final,
            content=content,
            sha256=digest.hexdigest(),
        )
    except BaseException:
        os.close(descriptor)
        raise


def _open_pinned_file(
    path: Path,
    expected_sha256: str,
    *,
    label: str,
    maximum_bytes: int,
    owner_only: bool,
    allow_root_owner: bool = False,
    retain_content: bool = True,
) -> PinnedFile:
    if not path.is_absolute() or path.name in ("", ".", ".."):
        raise SealError(f"{label} path must be an absolute file path")
    parent_descriptor = _open_absolute_directory(
        path.parent,
        owner_only=False,
        allow_root_owner=allow_root_owner,
    )
    try:
        pinned = _open_regular_at(
            parent_descriptor,
            path.name,
            display_path=path,
            maximum_bytes=maximum_bytes,
            owner_only=owner_only,
            allow_root_owner=allow_root_owner,
            retain_content=retain_content,
        )
    finally:
        os.close(parent_descriptor)
    if pinned.sha256 != expected_sha256:
        pinned.close()
        raise SealError(f"{label} SHA-256 does not match")
    return pinned


def _open_pinned_executable(
    path: Path,
    expected_sha256: str,
) -> PinnedFile:
    pinned = _open_pinned_file(
        path,
        expected_sha256,
        label="OpenSSL executable",
        maximum_bytes=MAX_EXECUTABLE_BYTES,
        owner_only=False,
        allow_root_owner=True,
    )
    if not stat.S_ISREG(pinned.metadata.st_mode):
        pinned.close()
        raise SealError("OpenSSL executable is not a regular file")
    if pinned.metadata.st_uid not in (0, os.geteuid()):
        pinned.close()
        raise SealError("OpenSSL executable owner is not trusted")
    if not (pinned.metadata.st_mode & 0o111):
        pinned.close()
        raise SealError("OpenSSL executable is not executable")
    return pinned


def _execute_pinned_openssl(
    executable: PinnedFile,
    arguments: Sequence[str],
    *,
    input_bytes: bytes | bytearray = b"",
    inherited_descriptors: Iterable[int] = (),
    maximum_output_bytes: int = MAX_CMS_BYTES,
) -> bytes:
    executable_path = f"/dev/fd/{executable.descriptor}"
    pass_descriptors = tuple(
        sorted(
            {
                executable.descriptor,
                *inherited_descriptors,
            }
        )
    )
    completed = subprocess.run(
        (executable_path, *arguments),
        executable=executable_path,
        input=input_bytes,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_minimal_environment(),
        pass_fds=pass_descriptors,
        timeout=30,
    )
    if completed.returncode != 0:
        raise SealError("pinned OpenSSL operation failed")
    if len(completed.stdout) > maximum_output_bytes:
        raise SealError("pinned OpenSSL output exceeds the safe size limit")
    return completed.stdout


def _certificate_serial(
    executable: PinnedFile,
    certificate: PinnedFile,
) -> str:
    output = _execute_pinned_openssl(
        executable,
        (
            "x509",
            "-in",
            certificate.descriptor_path,
            "-noout",
            "-serial",
        ),
        inherited_descriptors=(certificate.descriptor,),
        maximum_output_bytes=1024,
    )
    try:
        rendered = output.decode("ascii", errors="strict").strip()
    except UnicodeError as exc:
        raise SealError("certificate serial is not canonical ASCII") from exc
    match = re.fullmatch(r"serial=([0-9A-F]+)", rendered)
    if match is None:
        raise SealError("certificate serial output is malformed")
    return match.group(1).lstrip("0") or "0"


def _cms_print(
    executable: PinnedFile,
    content: bytes,
) -> str:
    output = _execute_pinned_openssl(
        executable,
        ("cms", "-cmsout", "-inform", "DER", "-print"),
        input_bytes=content,
        maximum_output_bytes=MAX_CMS_BYTES * 4,
    )
    try:
        return output.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise SealError("OpenSSL CMS structure output is not UTF-8") from exc


def _cms_contains_serial(rendered: str, expected_serial_hex: str) -> bool:
    expected = int(expected_serial_hex, 16)
    for value in re.findall(r"serialNumber:[ \t]*([0-9]+)", rendered):
        if int(value, 10) == expected:
            return True
    for value in re.findall(r"serialNumber:[ \t]*0x([0-9A-Fa-f]+)", rendered):
        if int(value, 16) == expected:
            return True
    return False


def _cms_named_section(rendered: str, heading: str) -> str:
    lines = rendered.splitlines()
    start: int | None = None
    indentation = 0
    for index, line in enumerate(lines):
        if line.strip() == heading:
            start = index
            indentation = len(line) - len(line.lstrip(" "))
            break
    if start is None:
        raise SealError(f"CMS structure is missing {heading}")
    selected = [lines[start]]
    for line in lines[start + 1 :]:
        if line.strip():
            current_indentation = len(line) - len(line.lstrip(" "))
            if (
                current_indentation == indentation
                and re.match(r"\A[A-Za-z][A-Za-z0-9.]*:", line.strip())
            ):
                break
        selected.append(line)
    return "\n".join(selected)


def _cms_section_has_one_serial(
    rendered: str,
    expected_serial_hex: str,
) -> bool:
    serials = re.findall(
        r"serialNumber:[ \t]*(?:0x[0-9A-Fa-f]+|[0-9]+)",
        rendered,
    )
    return len(serials) == 1 and _cms_contains_serial(
        rendered,
        expected_serial_hex,
    )


def _sign_ticket(
    ticket: bytearray,
    *,
    executable: PinnedFile,
    signer_certificate: PinnedFile,
    signer_key: PinnedFile,
) -> bytes:
    signed = _execute_pinned_openssl(
        executable,
        (
            "cms",
            "-sign",
            "-binary",
            "-nodetach",
            "-md",
            "sha256",
            "-signer",
            signer_certificate.descriptor_path,
            "-inkey",
            signer_key.descriptor_path,
            "-outform",
            "DER",
        ),
        input_bytes=ticket,
        inherited_descriptors=(
            signer_certificate.descriptor,
            signer_key.descriptor,
        ),
    )
    if not signed:
        raise SealError("OpenSSL produced an empty signed CMS object")
    rendered = _cms_print(executable, signed)
    signer_serial = _certificate_serial(executable, signer_certificate)
    signer_infos = _cms_named_section(rendered, "signerInfos:")
    if (
        CMS_SIGNED_TYPE not in rendered
        or CMS_SHA256_ALGORITHM not in signer_infos
        or not _cms_section_has_one_serial(signer_infos, signer_serial)
        or not any(
            algorithm in signer_infos
            for algorithm in CMS_ALLOWED_SIGNATURE_ALGORITHMS
        )
    ):
        raise SealError("signed CMS structure does not match pinned authority")
    verified = _execute_pinned_openssl(
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
        maximum_output_bytes=MAX_TICKET_BYTES,
    )
    if not hashlib.sha256(verified).digest() == hashlib.sha256(ticket).digest():
        raise SealError("signed CMS verification changed the ticket")
    if verified != bytes(ticket):
        raise SealError("signed CMS verification changed the ticket")
    return signed


def _encrypt_signed_cms(
    signed: bytes,
    *,
    executable: PinnedFile,
    recipient_certificate: PinnedFile,
) -> bytes:
    envelope = _execute_pinned_openssl(
        executable,
        (
            "cms",
            "-encrypt",
            "-binary",
            "-inform",
            "DER",
            "-outform",
            "DER",
            f"-{CMS_CIPHER}",
            recipient_certificate.descriptor_path,
        ),
        input_bytes=signed,
        inherited_descriptors=(recipient_certificate.descriptor,),
    )
    if not envelope:
        raise SealError("OpenSSL produced an empty CMS envelope")
    rendered = _cms_print(executable, envelope)
    recipient_serial = _certificate_serial(
        executable,
        recipient_certificate,
    )
    recipient_infos = _cms_named_section(rendered, "recipientInfos:")
    if (
        CMS_ENVELOPED_TYPE not in rendered
        or CMS_AES256_ALGORITHM not in rendered
        or not _cms_section_has_one_serial(
            recipient_infos,
            recipient_serial,
        )
        or CMS_RSA_KEY_ALGORITHM not in recipient_infos
    ):
        raise SealError("CMS envelope structure does not match pinned authority")
    return envelope


def _validate_ticket(value: bytes) -> bytes:
    if not value or len(value) > MAX_TICKET_BYTES:
        raise SealError("historical bearer has an invalid byte length")
    if PRINTABLE_ASCII_TOKEN.fullmatch(value) is None:
        raise SealError("historical bearer is not canonical printable ASCII")
    if re.fullmatch(TOKEN_BYTES, value) is None:
        raise SealError("historical bearer contains unsupported bytes")
    return value


def _extract_canonical_ticket(content: bytes) -> bytes:
    if b"\x00" in content or b"\r" in content:
        raise SealError("curl config contains non-canonical control bytes")
    values: list[bytes] = []
    for line in content.split(b"\n"):
        if len(line) > 64 * 1024:
            raise SealError("curl config line exceeds the safe size limit")
        stripped = line.lstrip(b" \t")
        if not stripped or stripped.startswith(b"#"):
            continue
        match = HEADER_LINE.fullmatch(line)
        if match is None:
            match = OAUTH2_LINE.fullmatch(line)
        if match is not None:
            values.append(_validate_ticket(match.group(1)))
        elif CREDENTIAL_LIKE.search(line):
            raise SealError("curl config has malformed credential material")
    if len(values) != 1:
        raise SealError(
            "each curl config must contain exactly one canonical credential line"
        )
    return values[0]


def _scan_run_directory(
    descriptor: int,
    *,
    release_root: Path,
    relative_parts: tuple[str, ...],
    candidates: list[Candidate],
) -> None:
    try:
        names = sorted(os.listdir(descriptor))
    except OSError as exc:
        raise SealError("unable to inventory release directory") from exc
    for name in names:
        if name in ("", ".", "..") or os.sep in name:
            raise SealError("release directory contains an unsafe entry")
        relative = PurePosixPath(*relative_parts, name).as_posix()
        display_path = release_root / Path(*relative_parts) / name
        try:
            metadata = os.stat(
                name,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise SealError("release inventory changed during traversal") from exc
        if name == TARGET_FILE_NAME:
            if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(
                metadata.st_mode
            ):
                raise SealError("credential candidate is not a regular file")
            pinned = _open_regular_at(
                descriptor,
                name,
                display_path=display_path,
                maximum_bytes=MAX_CONFIG_BYTES,
                owner_only=True,
            )
            candidates.append(
                Candidate(
                    relative_path=relative,
                    parent_descriptor=os.dup(descriptor),
                    descriptor=pinned.descriptor,
                    metadata=pinned.metadata,
                    content=pinned.content,
                    content_sha256=pinned.sha256,
                )
            )
            continue
        if stat.S_ISDIR(metadata.st_mode):
            child = _open_relative_directory(
                descriptor,
                name,
                label=str(display_path),
            )
            try:
                _scan_run_directory(
                    child,
                    release_root=release_root,
                    relative_parts=(*relative_parts, name),
                    candidates=candidates,
                )
            finally:
                os.close(child)


def _scan_inventory(lease: PublisherLease) -> Inventory:
    candidates: list[Candidate] = []
    try:
        for name in sorted(os.listdir(lease.root_descriptor)):
            if not name.startswith("run-"):
                continue
            metadata = os.stat(
                name,
                dir_fd=lease.root_descriptor,
                follow_symlinks=False,
            )
            if not stat.S_ISDIR(metadata.st_mode):
                continue
            run_descriptor = _open_relative_directory(
                lease.root_descriptor,
                name,
                label=str(lease.release_root / name),
            )
            try:
                _scan_run_directory(
                    run_descriptor,
                    release_root=lease.release_root,
                    relative_parts=(name,),
                    candidates=candidates,
                )
            finally:
                os.close(run_descriptor)
        return Inventory(candidates)
    except BaseException:
        for candidate in candidates:
            candidate.close()
        raise


def _revalidate_inventory(inventory: Inventory) -> None:
    for candidate in inventory.candidates:
        current = os.fstat(candidate.descriptor)
        linked = os.stat(
            TARGET_FILE_NAME,
            dir_fd=candidate.parent_descriptor,
            follow_symlinks=False,
        )
        if (
            current.st_dev != candidate.metadata.st_dev
            or current.st_ino != candidate.metadata.st_ino
            or current.st_mode != candidate.metadata.st_mode
            or current.st_size != candidate.metadata.st_size
            or current.st_mtime_ns != candidate.metadata.st_mtime_ns
            or current.st_nlink != 1
            or linked.st_dev != candidate.metadata.st_dev
            or linked.st_ino != candidate.metadata.st_ino
            or linked.st_nlink != 1
        ):
            raise SealError("credential inventory changed while sealing")
        content = _read_descriptor(
            candidate.descriptor,
            maximum_bytes=MAX_CONFIG_BYTES,
            label="credential candidate",
        )
        if hashlib.sha256(content).hexdigest() != candidate.content_sha256:
            raise SealError("credential candidate changed while sealing")


def _acquire_publisher_lease(
    release_root: Path,
    publisher_lock: Path,
) -> PublisherLease:
    if not release_root.is_absolute():
        raise SealError("release root must be absolute")
    expected_lock = release_root / PUBLISHER_LOCK_NAME
    if publisher_lock != expected_lock:
        raise SealError("publisher lock must be the canonical release-root lock")
    root_descriptor = _open_absolute_directory(release_root, owner_only=False)
    lock_descriptor: int | None = None
    try:
        lock_descriptor = os.open(
            PUBLISHER_LOCK_NAME,
            _file_open_flags(writable=True),
            dir_fd=root_descriptor,
        )
        metadata = os.fstat(lock_descriptor)
        linked = os.stat(
            PUBLISHER_LOCK_NAME,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or linked.st_dev != metadata.st_dev
            or linked.st_ino != metadata.st_ino
        ):
            raise SealError("publisher lock is not a safe owner-only file")
        _assert_no_extended_acl(lock_descriptor, str(publisher_lock))
        content = _read_descriptor(
            lock_descriptor,
            maximum_bytes=256,
            label="publisher lock",
        )
        if content != PUBLISHER_LOCK_CONTRACT.encode("ascii"):
            raise SealError("publisher lock contract is not initialized")
        try:
            fcntl.flock(
                lock_descriptor,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as exc:
            raise SealError("a release publisher still holds the root lock") from exc
        linked_after = os.stat(
            PUBLISHER_LOCK_NAME,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if (
            linked_after.st_dev != metadata.st_dev
            or linked_after.st_ino != metadata.st_ino
            or linked_after.st_nlink != 1
        ):
            raise SealError("publisher lock identity changed")
        return PublisherLease(
            release_root=release_root,
            root_descriptor=root_descriptor,
            lock_descriptor=lock_descriptor,
            lock_metadata=metadata,
        )
    except BaseException:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        os.close(root_descriptor)
        raise


def _validate_targets(
    inventory: Inventory,
    targets: Sequence[str],
) -> None:
    expected: list[str] = []
    for target in targets:
        pure = PurePosixPath(target)
        if (
            not target
            or pure.is_absolute()
            or pure.as_posix() != target
            or len(pure.parts) < 2
            or not pure.parts[0].startswith("run-")
            or pure.parts[-1] != TARGET_FILE_NAME
            or any(part in ("", ".", "..") for part in pure.parts)
        ):
            raise SealError("target is outside the historical credential scope")
        expected.append(target)
    if len(expected) != len(set(expected)):
        raise SealError("targets contain duplicates")
    actual = sorted(candidate.relative_path for candidate in inventory.candidates)
    if sorted(expected) != actual or not actual:
        raise SealError("targets do not match the full locked inventory")


def _one_incident_ticket(inventory: Inventory) -> bytearray:
    values = {
        _extract_canonical_ticket(candidate.content)
        for candidate in inventory.candidates
    }
    if len(values) != 1:
        raise SealError("historical candidates do not contain one exact ticket")
    return bytearray(next(iter(values)))


def _ensure_same_private_parent(paths: Sequence[Path]) -> tuple[Path, int]:
    if not paths:
        raise SealError("transaction has no output paths")
    if any(
        not path.is_absolute() or path.name in ("", ".", "..")
        for path in paths
    ):
        raise SealError("transaction output paths must be absolute files")
    parent = paths[0].parent
    if any(path.parent != parent for path in paths):
        raise SealError("transaction outputs must share one private directory")
    if len({path.name for path in paths}) != len(paths):
        raise SealError("transaction output paths must be distinct")
    return parent, _open_absolute_directory(parent, owner_only=True)


def _create_private_file_at(
    parent_descriptor: int,
    name: str,
    content: bytes,
) -> tuple[int, os.stat_result]:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(name, flags, 0o600, dir_fd=parent_descriptor)
    try:
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise SealError("private transaction write did not progress")
            offset += written
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or metadata.st_size != len(content)
        ):
            raise SealError("private transaction file is unsafe")
        _assert_no_extended_acl(descriptor, name)
        return descriptor, metadata
    except BaseException:
        try:
            created = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        try:
            current = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                current.st_dev == created.st_dev
                and current.st_ino == created.st_ino
            ):
                os.unlink(name, dir_fd=parent_descriptor)
                os.fsync(parent_descriptor)
        except OSError:
            pass
        raise


def _read_private_file_at(
    parent_descriptor: int,
    name: str,
    *,
    maximum_bytes: int,
    maximum_links: int = 1,
) -> tuple[bytes, os.stat_result]:
    pinned = _open_regular_at(
        parent_descriptor,
        name,
        display_path=Path(name),
        maximum_bytes=maximum_bytes,
        owner_only=True,
        maximum_links=maximum_links,
    )
    try:
        return pinned.content, pinned.metadata
    finally:
        pinned.close()


def _safe_unlink_identity(
    parent_descriptor: int,
    name: str,
    expected: os.stat_result,
) -> None:
    current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    if current.st_dev != expected.st_dev or current.st_ino != expected.st_ino:
        raise SealError("transaction cleanup identity changed")
    os.unlink(name, dir_fd=parent_descriptor)


def _safe_rmdir_identity(
    *,
    parent_descriptor: int,
    stage_descriptor: int,
    stage_name: str,
    expected: os.stat_result,
) -> None:
    opened = os.fstat(stage_descriptor)
    linked = os.stat(
        stage_name,
        dir_fd=parent_descriptor,
        follow_symlinks=False,
    )
    if (
        not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or stat.S_IMODE(opened.st_mode) != 0o700
        or opened.st_dev != expected.st_dev
        or opened.st_ino != expected.st_ino
        or linked.st_dev != expected.st_dev
        or linked.st_ino != expected.st_ino
    ):
        raise SealError("transaction stage directory identity changed")
    os.rmdir(stage_name, dir_fd=parent_descriptor)
    os.fsync(parent_descriptor)


def _read_transaction_manifest(
    *,
    stage_descriptor: int,
    transaction_id: str,
    context_sha256: str,
    expected_names: set[str],
) -> tuple[dict[str, dict[str, Any]], os.stat_result]:
    manifest_bytes, manifest_metadata = _read_private_file_at(
        stage_descriptor,
        "transaction.json",
        maximum_bytes=MAX_TRANSACTION_FILE_BYTES,
    )
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SealError("transaction manifest is malformed") from exc
    if (
        not isinstance(manifest, dict)
        or set(manifest)
        != {
            "contractName",
            "transactionId",
            "contextSha256",
            "artifacts",
        }
        or manifest.get("contractName") != TRANSACTION_CONTRACT_NAME
        or manifest.get("transactionId") != transaction_id
        or manifest.get("contextSha256") != context_sha256
        or _canonical_json_bytes(manifest) != manifest_bytes
    ):
        raise SealError("transaction manifest binding is invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != expected_names:
        raise SealError("transaction manifest output set changed")

    stage_files: set[str] = set()
    typed_artifacts: dict[str, dict[str, Any]] = {}
    for final_name, record in artifacts.items():
        if (
            not isinstance(final_name, str)
            or not isinstance(record, dict)
            or set(record) != TRANSACTION_ARTIFACT_FIELDS
            or type(record.get("stageFile")) is not str
            or re.fullmatch(r"artifact-[0-9]+", record["stageFile"]) is None
            or type(record.get("sha256")) is not str
            or SHA256_HEX.fullmatch(record["sha256"]) is None
            or type(record.get("sizeBytes")) is not int
            or record["sizeBytes"] < 0
            or type(record.get("device")) is not int
            or record["device"] < 0
            or type(record.get("inode")) is not int
            or record["inode"] < 1
            or record["stageFile"] in stage_files
        ):
            raise SealError("transaction artifact record is malformed")
        stage_files.add(record["stageFile"])
        typed_artifacts[final_name] = record

    entries = set(os.listdir(stage_descriptor))
    if (
        "transaction.json" not in entries
        or not entries.issubset(stage_files | {"transaction.json"})
    ):
        raise SealError("transaction stage has unknown entries")
    return typed_artifacts, manifest_metadata


def _read_transaction_artifact(
    parent_descriptor: int,
    name: str,
    record: Mapping[str, Any],
) -> tuple[bytes, os.stat_result] | None:
    try:
        content, metadata = _read_private_file_at(
            parent_descriptor,
            name,
            maximum_bytes=MAX_TRANSACTION_FILE_BYTES,
            maximum_links=2,
        )
    except FileNotFoundError:
        return None
    if (
        len(content) != record["sizeBytes"]
        or hashlib.sha256(content).hexdigest() != record["sha256"]
        or metadata.st_dev != record["device"]
        or metadata.st_ino != record["inode"]
    ):
        raise SealError("transaction artifact identity or content changed")
    return content, metadata


def _ordered_transaction_records(
    artifacts: Mapping[str, Mapping[str, Any]],
) -> list[tuple[str, Mapping[str, Any]]]:
    return sorted(
        artifacts.items(),
        key=lambda item: int(item[1]["stageFile"].removeprefix("artifact-")),
    )


def _finish_transaction_stage(
    *,
    parent_descriptor: int,
    stage_descriptor: int,
    stage_name: str,
    stage_metadata: os.stat_result,
    artifacts: Mapping[str, Mapping[str, Any]],
    manifest_metadata: os.stat_result,
    allow_linking_missing_finals: bool,
) -> bool:
    ordered = _ordered_transaction_records(artifacts)
    seen_retained_stage = False
    for final_name, record in ordered:
        stage_file = record["stageFile"]
        try:
            os.stat(
                stage_file,
                dir_fd=stage_descriptor,
                follow_symlinks=False,
            )
            seen_retained_stage = True
        except FileNotFoundError:
            if seen_retained_stage:
                raise SealError(
                    "transaction stage cleanup order is inconsistent"
                )

        staged = _read_transaction_artifact(
            stage_descriptor,
            stage_file,
            record,
        )
        final = _read_transaction_artifact(
            parent_descriptor,
            final_name,
            record,
        )
        if final is None:
            if not allow_linking_missing_finals:
                return False
            if staged is None or staged[1].st_nlink != 1:
                raise SealError("staged transaction artifact is incomplete")
            try:
                os.link(
                    stage_file,
                    final_name,
                    src_dir_fd=stage_descriptor,
                    dst_dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise SealError(
                    "transaction output appeared during commit"
                ) from exc
            os.fsync(parent_descriptor)
            staged = _read_transaction_artifact(
                stage_descriptor,
                stage_file,
                record,
            )
            final = _read_transaction_artifact(
                parent_descriptor,
                final_name,
                record,
            )
        if final is None:
            raise SealError("transaction output was not published")
        if staged is None:
            if final[1].st_nlink != 1:
                raise SealError(
                    "cleaned transaction output link count is invalid"
                )
            continue
        if (
            staged[1].st_nlink != 2
            or final[1].st_nlink != 2
            or staged[1].st_dev != final[1].st_dev
            or staged[1].st_ino != final[1].st_ino
        ):
            raise SealError(
                "published transaction output is not the exact staged inode"
            )

    for final_name, record in ordered:
        stage_file = record["stageFile"]
        staged = _read_transaction_artifact(
            stage_descriptor,
            stage_file,
            record,
        )
        final = _read_transaction_artifact(
            parent_descriptor,
            final_name,
            record,
        )
        if final is None:
            raise SealError("transaction output disappeared during cleanup")
        if staged is None:
            if final[1].st_nlink != 1:
                raise SealError(
                    "cleaned transaction output link count is invalid"
                )
            continue
        if (
            staged[1].st_nlink != 2
            or final[1].st_nlink != 2
            or staged[1].st_dev != final[1].st_dev
            or staged[1].st_ino != final[1].st_ino
        ):
            raise SealError(
                "transaction cleanup identity changed before unlink"
            )
        _safe_unlink_identity(
            stage_descriptor,
            stage_file,
            staged[1],
        )
        os.fsync(stage_descriptor)
        cleaned = _read_transaction_artifact(
            parent_descriptor,
            final_name,
            record,
        )
        if (
            cleaned is None
            or cleaned[1].st_dev != final[1].st_dev
            or cleaned[1].st_ino != final[1].st_ino
            or cleaned[1].st_nlink != 1
        ):
            raise SealError(
                "transaction output did not become a single durable link"
            )

    _safe_unlink_identity(
        stage_descriptor,
        "transaction.json",
        manifest_metadata,
    )
    os.fsync(stage_descriptor)
    _safe_rmdir_identity(
        parent_descriptor=parent_descriptor,
        stage_descriptor=stage_descriptor,
        stage_name=stage_name,
        expected=stage_metadata,
    )
    return True


def _recover_fully_linked_transaction(
    *,
    final_paths: Sequence[Path],
    transaction_id: str,
    context_sha256: str,
) -> bool:
    parent, parent_descriptor = _ensure_same_private_parent(final_paths)
    stage_name = f".chummer-ticket-intake-{transaction_id}.stage"
    stage_descriptor: int | None = None
    try:
        try:
            stage_descriptor = os.open(
                stage_name,
                _directory_open_flags(),
                dir_fd=parent_descriptor,
            )
        except FileNotFoundError:
            return False
        stage_metadata = os.fstat(stage_descriptor)
        linked_stage = os.stat(
            stage_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(stage_metadata.st_mode)
            or stage_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(stage_metadata.st_mode) != 0o700
            or linked_stage.st_dev != stage_metadata.st_dev
            or linked_stage.st_ino != stage_metadata.st_ino
        ):
            raise SealError("transaction stage directory is unsafe")
        _assert_no_extended_acl(
            stage_descriptor,
            str(parent / stage_name),
        )
        expected_names = {path.name for path in final_paths}
        try:
            artifacts, manifest_metadata = _read_transaction_manifest(
                stage_descriptor=stage_descriptor,
                transaction_id=transaction_id,
                context_sha256=context_sha256,
                expected_names=expected_names,
            )
        except FileNotFoundError:
            final_existence: list[bool] = []
            for path in final_paths:
                try:
                    os.stat(
                        path.name,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                    final_existence.append(True)
                except FileNotFoundError:
                    final_existence.append(False)
            if not any(final_existence):
                return False
            if os.listdir(stage_descriptor) or not all(final_existence):
                raise SealError(
                    "transaction stage lost its retained manifest"
                )
            _safe_rmdir_identity(
                parent_descriptor=parent_descriptor,
                stage_descriptor=stage_descriptor,
                stage_name=stage_name,
                expected=stage_metadata,
            )
            return True
        return _finish_transaction_stage(
            parent_descriptor=parent_descriptor,
            stage_descriptor=stage_descriptor,
            stage_name=stage_name,
            stage_metadata=stage_metadata,
            artifacts=artifacts,
            manifest_metadata=manifest_metadata,
            allow_linking_missing_finals=False,
        )
    finally:
        if stage_descriptor is not None:
            os.close(stage_descriptor)
        os.close(parent_descriptor)


def _cleanup_uncommitted_stage(
    *,
    parent_descriptor: int,
    stage_descriptor: int,
    stage_name: str,
    final_names: set[str],
) -> None:
    for final_name in final_names:
        try:
            os.stat(
                final_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            continue
        raise SealError(
            "uncommitted transaction has an already-published output"
        )
    for entry in sorted(os.listdir(stage_descriptor)):
        if entry != "transaction.json" and re.fullmatch(
            r"artifact-[0-9]+",
            entry,
        ) is None:
            raise SealError("uncommitted transaction stage has unknown entries")
        content, metadata = _read_private_file_at(
            stage_descriptor,
            entry,
            maximum_bytes=MAX_TRANSACTION_FILE_BYTES,
        )
        del content
        _safe_unlink_identity(stage_descriptor, entry, metadata)
    os.fsync(stage_descriptor)


def _publish_transaction(
    *,
    outputs: Mapping[Path, bytes],
    commit_marker_path: Path,
    transaction_id: str,
    context_sha256: str,
    commit_contract_name: str = COMMIT_CONTRACT_NAME,
) -> None:
    if TRANSACTION_ID.fullmatch(transaction_id) is None:
        raise SealError("transaction identifier is invalid")
    all_paths = [*outputs, commit_marker_path]
    parent, parent_descriptor = _ensure_same_private_parent(all_paths)
    stage_name = f".chummer-ticket-intake-{transaction_id}.stage"
    stage_descriptor: int | None = None
    stage_was_created = False
    try:
        try:
            os.mkdir(stage_name, 0o700, dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
            stage_was_created = True
            stage_descriptor = os.open(
                stage_name,
                _directory_open_flags(),
                dir_fd=parent_descriptor,
            )
            artifacts: dict[str, dict[str, Any]] = {}
            for index, (path, content) in enumerate(outputs.items()):
                stage_file = f"artifact-{index}"
                descriptor, metadata = _create_private_file_at(
                    stage_descriptor,
                    stage_file,
                    content,
                )
                os.close(descriptor)
                artifacts[path.name] = {
                    "stageFile": stage_file,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "sizeBytes": len(content),
                    "device": metadata.st_dev,
                    "inode": metadata.st_ino,
                }
            marker_payload = {
                "contractName": commit_contract_name,
                "status": "committed",
                "transactionId": transaction_id,
                "contextSha256": context_sha256,
                "artifacts": {
                    name: {
                        "sha256": value["sha256"],
                        "sizeBytes": value["sizeBytes"],
                    }
                    for name, value in sorted(artifacts.items())
                },
            }
            marker_bytes = _canonical_json_bytes(marker_payload)
            marker_stage = f"artifact-{len(outputs)}"
            marker_descriptor, marker_metadata = _create_private_file_at(
                stage_descriptor,
                marker_stage,
                marker_bytes,
            )
            os.close(marker_descriptor)
            artifacts[commit_marker_path.name] = {
                "stageFile": marker_stage,
                "sha256": hashlib.sha256(marker_bytes).hexdigest(),
                "sizeBytes": len(marker_bytes),
                "device": marker_metadata.st_dev,
                "inode": marker_metadata.st_ino,
            }
            manifest = {
                "contractName": TRANSACTION_CONTRACT_NAME,
                "transactionId": transaction_id,
                "contextSha256": context_sha256,
                "artifacts": artifacts,
            }
            manifest_bytes = _canonical_json_bytes(manifest)
            manifest_descriptor, _manifest_metadata = _create_private_file_at(
                stage_descriptor,
                "transaction.json",
                manifest_bytes,
            )
            os.close(manifest_descriptor)
            os.fsync(stage_descriptor)
        except FileExistsError:
            stage_descriptor = os.open(
                stage_name,
                _directory_open_flags(),
                dir_fd=parent_descriptor,
            )

        assert stage_descriptor is not None
        stage_metadata = os.fstat(stage_descriptor)
        linked_stage = os.stat(
            stage_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(stage_metadata.st_mode)
            or stage_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(stage_metadata.st_mode) != 0o700
            or linked_stage.st_dev != stage_metadata.st_dev
            or linked_stage.st_ino != stage_metadata.st_ino
        ):
            raise SealError("transaction stage directory is unsafe")
        _assert_no_extended_acl(
            stage_descriptor,
            str(parent / stage_name),
        )
        try:
            artifacts, manifest_metadata = _read_transaction_manifest(
                stage_descriptor=stage_descriptor,
                transaction_id=transaction_id,
                context_sha256=context_sha256,
                expected_names={path.name for path in all_paths},
            )
        except FileNotFoundError:
            if stage_was_created:
                raise
            _cleanup_uncommitted_stage(
                parent_descriptor=parent_descriptor,
                stage_descriptor=stage_descriptor,
                stage_name=stage_name,
                final_names={path.name for path in all_paths},
            )
            _safe_rmdir_identity(
                parent_descriptor=parent_descriptor,
                stage_descriptor=stage_descriptor,
                stage_name=stage_name,
                expected=stage_metadata,
            )
            os.close(stage_descriptor)
            stage_descriptor = None
            return _publish_transaction(
                outputs=outputs,
                commit_marker_path=commit_marker_path,
                transaction_id=transaction_id,
                context_sha256=context_sha256,
                commit_contract_name=commit_contract_name,
            )
        _finish_transaction_stage(
            parent_descriptor=parent_descriptor,
            stage_descriptor=stage_descriptor,
            stage_name=stage_name,
            stage_metadata=stage_metadata,
            artifacts=artifacts,
            manifest_metadata=manifest_metadata,
            allow_linking_missing_finals=True,
        )
    finally:
        if stage_descriptor is not None:
            os.close(stage_descriptor)
        os.close(parent_descriptor)


def _load_existing_committed_receipt(
    *,
    output_path: Path,
    receipt_path: Path,
    commit_marker_path: Path,
    transaction_id: str,
    context_sha256: str,
    commit_contract_name: str = COMMIT_CONTRACT_NAME,
) -> dict[str, Any] | None:
    existence = (
        output_path.exists(),
        receipt_path.exists(),
        commit_marker_path.exists(),
    )
    if not any(existence):
        return None
    if not all(existence):
        # A retained transaction stage is the only authority allowed to
        # complete a partially published set.
        return None
    parent, parent_descriptor = _ensure_same_private_parent(
        (output_path, receipt_path, commit_marker_path)
    )
    del parent
    try:
        receipt_bytes, _ = _read_private_file_at(
            parent_descriptor,
            receipt_path.name,
            maximum_bytes=MAX_TRANSACTION_FILE_BYTES,
        )
        marker_bytes, _ = _read_private_file_at(
            parent_descriptor,
            commit_marker_path.name,
            maximum_bytes=MAX_TRANSACTION_FILE_BYTES,
        )
        output_bytes, _ = _read_private_file_at(
            parent_descriptor,
            output_path.name,
            maximum_bytes=MAX_TRANSACTION_FILE_BYTES,
        )
    finally:
        os.close(parent_descriptor)
    try:
        receipt = json.loads(receipt_bytes)
        marker = json.loads(marker_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SealError("existing transaction metadata is malformed") from exc
    if (
        not isinstance(receipt, dict)
        or not isinstance(marker, dict)
        or _canonical_json_bytes(receipt) != receipt_bytes
        or _canonical_json_bytes(marker) != marker_bytes
        or marker.get("contractName") != commit_contract_name
        or marker.get("transactionId") != transaction_id
        or marker.get("contextSha256") != context_sha256
        or receipt.get("transactionId") != transaction_id
        or receipt.get("contextSha256") != context_sha256
    ):
        raise SealError("existing transaction does not match this request")
    artifacts = marker.get("artifacts")
    if (
        not isinstance(artifacts, dict)
        or set(artifacts) != {output_path.name, receipt_path.name}
        or artifacts[output_path.name]
        != {
            "sha256": hashlib.sha256(output_bytes).hexdigest(),
            "sizeBytes": len(output_bytes),
        }
        or artifacts[receipt_path.name]
        != {
            "sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "sizeBytes": len(receipt_bytes),
        }
    ):
        raise SealError("existing transaction artifact binding is invalid")
    return receipt


def _receipt(
    *,
    candidate_count: int,
    inventory_commitment: str,
    recipient_certificate_sha256: str,
    signer_certificate_sha256: str,
    openssl_executable_sha256: str,
    envelope: bytes,
    transaction_id: str,
    context_sha256: str,
) -> dict[str, Any]:
    return {
        "contractName": CONTRACT_NAME,
        "generatedAtUtc": _utc_now(),
        "status": "sealed_pending_quarantine_and_revocation",
        "transactionId": transaction_id,
        "contextSha256": context_sha256,
        "candidateCount": candidate_count,
        "distinctIncidentBearerCount": 1,
        "inventoryCommitmentSha256": inventory_commitment,
        "cmsComposition": "authenticated-signedData-inside-envelopedData",
        "digestAlgorithm": "sha256",
        "contentEncryptionAlgorithm": CMS_CIPHER,
        "recipientCertificateSha256": recipient_certificate_sha256,
        "signerCertificateSha256": signer_certificate_sha256,
        "opensslExecutableSha256": openssl_executable_sha256,
        "envelopeSha256": hashlib.sha256(envelope).hexdigest(),
        "envelopeSizeBytes": len(envelope),
        "plaintextPersistedOutsidePrivateSourceCandidates": False,
        "plaintextEmitted": False,
        "quarantineStatus": "pending",
        "revocationStatus": "pending",
        "exactOldTicketRevocationProofRequired": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--publisher-lock", type=Path, required=True)
    parser.add_argument("--openssl-path", type=Path, required=True)
    parser.add_argument("--openssl-sha256", required=True)
    parser.add_argument("--recipient-cert", type=Path, required=True)
    parser.add_argument("--recipient-cert-sha256", required=True)
    parser.add_argument("--signer-cert", type=Path, required=True)
    parser.add_argument("--signer-cert-sha256", required=True)
    parser.add_argument("--signer-key", type=Path, required=True)
    parser.add_argument("--signer-key-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--commit-marker", type=Path, required=True)
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        metavar="RUN_RELATIVE_PATH",
    )
    parser.add_argument("--confirm", required=True)
    return parser


def seal(options: argparse.Namespace) -> Mapping[str, Any]:
    _disable_core_dumps()
    if options.confirm != CONFIRMATION:
        raise SealError(f"--confirm requires {CONFIRMATION}")
    if not options.target:
        raise SealError("--target is required for every locked candidate")
    openssl_sha256 = _validate_sha256(
        options.openssl_sha256,
        "OpenSSL executable SHA-256",
    )
    recipient_sha256 = _validate_sha256(
        options.recipient_cert_sha256,
        "recipient certificate SHA-256",
    )
    signer_sha256 = _validate_sha256(
        options.signer_cert_sha256,
        "signer certificate SHA-256",
    )
    signer_key_sha256 = _validate_sha256(
        options.signer_key_sha256,
        "signer key SHA-256",
    )
    _parent, validation_parent = _ensure_same_private_parent(
        (options.output, options.receipt, options.commit_marker)
    )
    os.close(validation_parent)

    lease = _acquire_publisher_lease(
        options.release_root,
        options.publisher_lock,
    )
    first_inventory: Inventory | None = None
    second_inventory: Inventory | None = None
    executable: PinnedFile | None = None
    recipient_certificate: PinnedFile | None = None
    signer_certificate: PinnedFile | None = None
    signer_key: PinnedFile | None = None
    ticket = bytearray()
    try:
        first_inventory = _scan_inventory(lease)
        _validate_targets(first_inventory, options.target)
        inventory_commitment = first_inventory.commitment()
        context_sha256 = _canonical_json_sha256(
            {
                "contractName": CONTRACT_NAME,
                "inventoryCommitmentSha256": inventory_commitment,
                "recipientCertificateSha256": recipient_sha256,
                "signerCertificateSha256": signer_sha256,
                "signerKeySha256": signer_key_sha256,
                "opensslExecutableSha256": openssl_sha256,
                "outputPathSha256": hashlib.sha256(
                    str(options.output).encode("utf-8")
                ).hexdigest(),
                "receiptPathSha256": hashlib.sha256(
                    str(options.receipt).encode("utf-8")
                ).hexdigest(),
                "commitMarkerPathSha256": hashlib.sha256(
                    str(options.commit_marker).encode("utf-8")
                ).hexdigest(),
            }
        )
        transaction_id = context_sha256[:32]
        _recover_fully_linked_transaction(
            final_paths=(
                options.output,
                options.receipt,
                options.commit_marker,
            ),
            transaction_id=transaction_id,
            context_sha256=context_sha256,
        )
        existing = _load_existing_committed_receipt(
            output_path=options.output,
            receipt_path=options.receipt,
            commit_marker_path=options.commit_marker,
            transaction_id=transaction_id,
            context_sha256=context_sha256,
        )
        if existing is not None:
            return existing

        ticket = _one_incident_ticket(first_inventory)
        executable = _open_pinned_executable(
            options.openssl_path,
            openssl_sha256,
        )
        recipient_certificate = _open_pinned_file(
            options.recipient_cert,
            recipient_sha256,
            label="recipient certificate",
            maximum_bytes=256 * 1024,
            owner_only=False,
        )
        signer_certificate = _open_pinned_file(
            options.signer_cert,
            signer_sha256,
            label="signer certificate",
            maximum_bytes=256 * 1024,
            owner_only=False,
        )
        signer_key = _open_pinned_file(
            options.signer_key,
            signer_key_sha256,
            label="signer private key",
            maximum_bytes=256 * 1024,
            owner_only=True,
            retain_content=False,
        )
        signed = _sign_ticket(
            ticket,
            executable=executable,
            signer_certificate=signer_certificate,
            signer_key=signer_key,
        )
        envelope = _encrypt_signed_cms(
            signed,
            executable=executable,
            recipient_certificate=recipient_certificate,
        )
        _revalidate_inventory(first_inventory)
        second_inventory = _scan_inventory(lease)
        if (
            second_inventory.records() != first_inventory.records()
            or second_inventory.commitment() != inventory_commitment
        ):
            raise SealError("credential inventory changed before publication")
        result = _receipt(
            candidate_count=len(first_inventory.candidates),
            inventory_commitment=inventory_commitment,
            recipient_certificate_sha256=recipient_sha256,
            signer_certificate_sha256=signer_sha256,
            openssl_executable_sha256=openssl_sha256,
            envelope=envelope,
            transaction_id=transaction_id,
            context_sha256=context_sha256,
        )
        _publish_transaction(
            outputs={
                options.output: envelope,
                options.receipt: _canonical_json_bytes(result),
            },
            commit_marker_path=options.commit_marker,
            transaction_id=transaction_id,
            context_sha256=context_sha256,
        )
        committed = _load_existing_committed_receipt(
            output_path=options.output,
            receipt_path=options.receipt,
            commit_marker_path=options.commit_marker,
            transaction_id=transaction_id,
            context_sha256=context_sha256,
        )
        if committed is None:
            raise SealError("sealed transaction was not committed")
        return committed
    finally:
        for index in range(len(ticket)):
            ticket[index] = 0
        if signer_key is not None:
            signer_key.close()
        if signer_certificate is not None:
            signer_certificate.close()
        if recipient_certificate is not None:
            recipient_certificate.close()
        if executable is not None:
            executable.close()
        if second_inventory is not None:
            second_inventory.close()
        if first_inventory is not None:
            first_inventory.close()
        lease.close()


def run(arguments: Sequence[str] | None = None) -> int:
    try:
        _disable_core_dumps()
        options = build_parser().parse_args(arguments)
        result = seal(options)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (
        SealError,
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
                    "error": "secure incident-ticket sealing failed",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
