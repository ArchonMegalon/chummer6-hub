#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
import re
import struct
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


APPENDED_PAYLOAD_MAGIC = b"CHUMMER6PAYLOAD1"
FOOTER_LENGTH = len(APPENDED_PAYLOAD_MAGIC) + 8
WINDOWS_EXE_MAGIC = b"MZ"
WINDOWS_PE_MAGIC = b"PE\0\0"
ZIP_LOCAL_FILE_MAGIC = b"PK\x03\x04"
MAX_BOOTSTRAP_INSTALLER_BYTES = 15 * 1024 * 1024

DEFAULT_LAUNCH_EXECUTABLES = {
    "avalonia": "Chummer.Avalonia.exe",
    "blazor-desktop": "Chummer.Blazor.Desktop.exe",
}


@dataclass(frozen=True)
class ManifestRow:
    artifact_id: str
    file_name: str
    download_url: str
    sha256: str
    size_bytes: int | None
    payload_file_name: str
    payload_download_url: str
    payload_sha256: str
    payload_size_bytes: int | None
    installer_mode: str
    authoritative_identity: str
    release_proof_base_urls: tuple[str, ...]
    manifest_errors: tuple[str, ...]


@dataclass(frozen=True)
class PayloadCandidate:
    mode: str
    source: str
    data: bytes


@dataclass(frozen=True)
class CanonicalOrigin:
    hostname: str
    port: int


@dataclass(frozen=True)
class CanonicalHttpsUrl:
    value: str
    origin: CanonicalOrigin
    path: str


@dataclass(frozen=True)
class ManifestUrlAuthority:
    trusted_origin: CanonicalOrigin | None
    payload_path: str | None
    payload_url: CanonicalHttpsUrl | None
    failures: tuple[str, ...]


@dataclass(frozen=True)
class ManifestDocument:
    path: Path
    rows: tuple[ManifestRow, ...]
    release_proof_base_urls: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class ManifestReadResult:
    rows: dict[str, ManifestRow]
    documents: tuple[ManifestDocument, ...]


@dataclass(frozen=True)
class EmbeddedMetadataScan:
    occurrence_count: int
    values: tuple[str, ...]
    failures: tuple[str, ...]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


def normalize_zip_name(value: str) -> str:
    return value.replace("\\", "/").lstrip("/")


def is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())


def exact_string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def url_file_name(value: str) -> str:
    try:
        return Path(urlsplit(value).path).name
    except ValueError:
        return ""


def has_forbidden_url_syntax(value: str) -> bool:
    return (
        not value
        or any(ord(character) <= 32 or ord(character) == 127 for character in value)
        or any(character in value for character in ("%", "\\", ";", "?", "#"))
    )


def canonical_site_download_path(value: str) -> str | None:
    if has_forbidden_url_syntax(value) or not value.startswith("/downloads/"):
        return None
    parts = value.split("/")
    if parts[0] or any(part in {"", ".", ".."} for part in parts[1:]):
        return None
    return value


DNS_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def canonical_hostname(value: str) -> str | None:
    if (
        not value
        or not value.isascii()
        or value != value.lower()
        or value in {"-", "."}
        or value.endswith(".")
    ):
        return None
    try:
        parsed_ip = ipaddress.ip_address(value)
    except ValueError:
        if (
            ":" in value
            or value.startswith("0x")
            or re.fullmatch(r"[0-9.]+", value) is not None
        ):
            return None
    else:
        canonical_ip = parsed_ip.compressed.lower()
        return canonical_ip if value == canonical_ip else None

    if len(value) > 253:
        return None
    labels = value.split(".")
    if any(
        not label
        or label.startswith("xn--")
        or DNS_LABEL_RE.fullmatch(label) is None
        for label in labels
    ):
        return None
    return value


def parse_canonical_https_url(
    value: str,
    *,
    require_download_path: bool,
    require_origin_only: bool = False,
) -> CanonicalHttpsUrl | None:
    if has_forbidden_url_syntax(value) or not value.startswith("https://"):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.geturl() != value
        or port not in (None, 443)
    ):
        return None
    hostname = parsed.hostname
    if hostname is None:
        return None
    hostname = canonical_hostname(hostname)
    if hostname is None:
        return None
    serialized_host = f"[{hostname}]" if ":" in hostname else hostname
    serialized_netloc = serialized_host + (":443" if port is not None else "")
    if parsed.netloc != serialized_netloc:
        return None
    if require_origin_only:
        if parsed.path:
            return None
    elif require_download_path:
        if canonical_site_download_path(parsed.path) is None:
            return None
    elif not parsed.path.startswith("/"):
        return None
    return CanonicalHttpsUrl(
        value=value,
        origin=CanonicalOrigin(hostname=hostname, port=443),
        path=parsed.path,
    )


def manifest_url_authority(manifest_row: ManifestRow) -> ManifestUrlAuthority:
    failures = list(manifest_row.manifest_errors)
    installer_url: CanonicalHttpsUrl | None = None
    installer_path: str | None = None
    if manifest_row.download_url:
        installer_path = canonical_site_download_path(manifest_row.download_url)
        if installer_path is None:
            installer_url = parse_canonical_https_url(
                manifest_row.download_url,
                require_download_path=True,
            )
            if installer_url is None:
                failures.append(
                    "manifest Windows installer downloadUrl must be a lossless canonical "
                    "absolute HTTPS URL or /downloads/... site path"
                )
            else:
                installer_path = installer_url.path
        if (
            installer_path is not None
            and installer_path.rsplit("/", 1)[-1] != manifest_row.file_name
        ):
            failures.append(
                "manifest Windows installer downloadUrl basename must match fileName exactly"
            )

    base_urls: list[CanonicalHttpsUrl] = []
    for base_url in manifest_row.release_proof_base_urls:
        parsed_base = parse_canonical_https_url(
            base_url,
            require_download_path=False,
            require_origin_only=True,
        )
        if parsed_base is None:
            failures.append(
                "manifest releaseProof.baseUrl must be one lossless canonical HTTPS origin"
            )
        else:
            base_urls.append(parsed_base)

    candidate_origins = [
        *(item.origin for item in base_urls),
        *((installer_url.origin,) if installer_url is not None else ()),
    ]
    unique_origins = set(candidate_origins)
    trusted_origin: CanonicalOrigin | None
    if len(unique_origins) > 1:
        failures.append(
            "manifest installer downloadUrl and releaseProof.baseUrl origins must all agree"
        )
        trusted_origin = None
    elif unique_origins:
        trusted_origin = next(iter(unique_origins))
    else:
        failures.append(
            "manifest bootstrap URL authority is missing; require an absolute HTTPS "
            "installer downloadUrl or releaseProof.baseUrl"
        )
        trusted_origin = None

    payload_path: str | None = None
    payload_url: CanonicalHttpsUrl | None = None
    if manifest_row.payload_download_url:
        payload_path = canonical_site_download_path(manifest_row.payload_download_url)
        if payload_path is None:
            payload_url = parse_canonical_https_url(
                manifest_row.payload_download_url,
                require_download_path=True,
            )
            if payload_url is None:
                failures.append(
                    "manifest installerMode=bootstrap payloadDownloadUrl must be a "
                    "lossless canonical absolute HTTPS URL or /downloads/... site path"
                )
            else:
                payload_path = payload_url.path
                if (
                    trusted_origin is not None
                    and payload_url.origin != trusted_origin
                ):
                    failures.append(
                        "manifest payloadDownloadUrl must use the trusted manifest origin"
                    )

    return ManifestUrlAuthority(
        trusted_origin=trusted_origin,
        payload_path=payload_path,
        payload_url=payload_url,
        failures=tuple(failures),
    )


def sidecar_url_matches_manifest(
    sidecar_url: CanonicalHttpsUrl,
    manifest_row: ManifestRow,
    authority: ManifestUrlAuthority,
) -> bool:
    if (
        authority.trusted_origin is None
        or authority.payload_path is None
        or sidecar_url.origin != authority.trusted_origin
        or sidecar_url.path != authority.payload_path
    ):
        return False
    if authority.payload_url is not None:
        return sidecar_url.value == manifest_row.payload_download_url
    return True


def is_windows_installer_name(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith("chummer-") and lowered.endswith("-win-x64-installer.exe") or (
        lowered.startswith("chummer-") and "-win-" in lowered and lowered.endswith("-installer.exe")
    )


def expected_payload_name(installer_name: str) -> str:
    lowered = installer_name.lower()
    if not lowered.endswith("-installer.exe"):
        return ""
    return installer_name[: -len("-installer.exe")] + "-payload.zip"


def infer_head_id(installer_name: str) -> str:
    lowered = installer_name.lower()
    if lowered.startswith("chummer-blazor-desktop-"):
        return "blazor-desktop"
    if lowered.startswith("chummer-avalonia-"):
        return "avalonia"
    return ""


def infer_launch_executables(installer_name: str) -> list[str]:
    head_id = infer_head_id(installer_name)
    if head_id in DEFAULT_LAUNCH_EXECUTABLES:
        return [DEFAULT_LAUNCH_EXECUTABLES[head_id]]
    return []


def alias_string(
    value: dict[str, Any],
    aliases: tuple[str, ...],
    label: str,
    failures: list[str],
) -> str:
    observed: list[tuple[str, str]] = []
    for alias in aliases:
        if alias not in value:
            continue
        raw = value.get(alias)
        if not isinstance(raw, str):
            failures.append(f"{label} alias {alias} must be a string")
            continue
        observed.append((alias, raw))
    if len({item for _alias, item in observed}) > 1:
        failures.append(f"{label} aliases {'/'.join(aliases)} must agree exactly")
    return observed[0][1] if observed else ""


def normalized_identity_value(
    value: dict[str, Any],
    key: str,
    *,
    normalize: str = "",
) -> dict[str, Any]:
    if key not in value:
        return {"present": False}
    raw = value.get(key)
    if isinstance(raw, str):
        if normalize == "lower":
            raw = raw.strip().lower()
        elif normalize == "strip":
            raw = raw.strip()
    elif normalize == "integer":
        parsed = try_int(raw)
        raw = parsed if parsed is not None else raw
    return {"present": True, "value": raw}


def manifest_row_authoritative_identity(
    item: dict[str, Any],
    *,
    artifact_id: str,
    file_name: str,
    download_url: str,
    payload_file_name: str,
    payload_download_url: str,
    effective_version: str,
    effective_channel: str,
) -> str:
    # The canonical artifacts collection and compatibility downloads collection
    # intentionally use different alias keys and carry different presentation
    # metadata. Canonical-only artifactByteVisibility/generatedAt/generated_at
    # and compatibility-only flavor/format/platformId are therefore excluded;
    # normalize aliases, then compare every publication/security field shared by
    # both schemas.
    identity = {
        "artifactId": artifact_id,
        "fileName": file_name,
        "downloadUrl": download_url,
        "sha256": normalized_identity_value(item, "sha256", normalize="lower"),
        "sizeBytes": normalized_identity_value(item, "sizeBytes", normalize="integer"),
        "installAccessClass": normalized_identity_value(
            item,
            "installAccessClass",
            normalize="strip",
        ),
        "previewPolicy": normalized_identity_value(
            item,
            "previewPolicy",
            normalize="strip",
        ),
        "signature": normalized_identity_value(item, "signature"),
        "payloadFileName": payload_file_name,
        "payloadDownloadUrl": payload_download_url,
        "payloadSha256": normalized_identity_value(
            item,
            "payloadSha256",
            normalize="lower",
        ),
        "payloadSizeBytes": normalized_identity_value(
            item,
            "payloadSizeBytes",
            normalize="integer",
        ),
        "payloadAcquisitionMode": normalized_identity_value(
            item,
            "payloadAcquisitionMode",
            normalize="lower",
        ),
        "installerMode": normalized_identity_value(
            item,
            "installerMode",
            normalize="lower",
        ),
        "version": effective_version,
        "channel": effective_channel,
        "kind": normalized_identity_value(item, "kind", normalize="lower"),
        "head": normalized_identity_value(item, "head", normalize="lower"),
        "arch": normalized_identity_value(item, "arch", normalize="lower"),
        "rid": normalized_identity_value(item, "rid", normalize="lower"),
        "platform": normalized_identity_value(item, "platform", normalize="lower"),
        "platformLabel": normalized_identity_value(
            item,
            "platformLabel",
            normalize="strip",
        ),
        "platformScope": normalized_identity_value(
            item,
            "platformScope",
            normalize="lower",
        ),
        "compatibilityState": normalized_identity_value(
            item,
            "compatibilityState",
            normalize="lower",
        ),
        "compatibilityReason": normalized_identity_value(
            item,
            "compatibilityReason",
        ),
        "publicationDisposition": normalized_identity_value(
            item,
            "publicationDisposition",
            normalize="lower",
        ),
        "crossRunBitReproducible": normalized_identity_value(
            item,
            "crossRunBitReproducible",
        ),
        "sourceManifestRowSha256": normalized_identity_value(
            item,
            "sourceManifestRowSha256",
            normalize="lower",
        ),
    }
    return json.dumps(
        identity,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def read_manifest_rows(manifest_paths: list[Path]) -> ManifestReadResult:
    rows: dict[str, ManifestRow] = {}
    documents: list[ManifestDocument] = []
    for manifest_path in manifest_paths:
        if not manifest_path.is_file():
            documents.append(
                ManifestDocument(
                    path=manifest_path,
                    rows=(),
                    release_proof_base_urls=(),
                    errors=("supplied release manifest is missing",),
                )
            )
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            documents.append(
                ManifestDocument(
                    path=manifest_path,
                    rows=(),
                    release_proof_base_urls=(),
                    errors=(f"supplied release manifest is unreadable or invalid JSON: {exc}",),
                )
            )
            continue
        if not isinstance(payload, dict):
            documents.append(
                ManifestDocument(
                    path=manifest_path,
                    rows=(),
                    release_proof_base_urls=(),
                    errors=("supplied release manifest must be a JSON object",),
                )
            )
            continue
        release_proof = payload.get("releaseProof")
        root_errors: list[str] = []
        root_version = alias_string(
            payload,
            ("version", "releaseVersion"),
            "manifest release version",
            root_errors,
        )
        root_channel = alias_string(
            payload,
            ("channel", "channelId"),
            "manifest release channel",
            root_errors,
        )
        release_proof_base_urls: tuple[str, ...] = ()
        if release_proof is not None and not isinstance(release_proof, dict):
            root_errors.append("manifest releaseProof must be a JSON object")
        elif isinstance(release_proof, dict) and "baseUrl" in release_proof:
            base_url = release_proof.get("baseUrl")
            if isinstance(base_url, str):
                release_proof_base_urls = (base_url,)
            else:
                root_errors.append("manifest releaseProof.baseUrl must be a string")
        document_rows: list[ManifestRow] = []
        for collection_name in ("artifacts", "downloads"):
            collection = payload.get(collection_name)
            if not isinstance(collection, list):
                continue
            for item in collection:
                if not isinstance(item, dict):
                    continue
                row_errors = list(root_errors)
                file_name = alias_string(
                    item,
                    ("fileName", "name"),
                    "manifest Windows installer file name",
                    row_errors,
                )
                download_value = alias_string(
                    item,
                    ("downloadUrl", "url"),
                    "manifest Windows installer URL",
                    row_errors,
                )
                if not file_name and download_value:
                    file_name = url_file_name(download_value)
                if not file_name or not is_windows_installer_name(file_name):
                    continue
                payload_download_value = item.get("payloadDownloadUrl")
                if (
                    payload_download_value is not None
                    and not isinstance(payload_download_value, str)
                ):
                    row_errors.append(
                        "manifest payloadDownloadUrl must be a string"
                    )
                artifact_id = alias_string(
                    item,
                    ("artifactId", "id"),
                    "manifest Windows installer artifact identity",
                    row_errors,
                )
                payload_file_name = alias_string(
                    item,
                    ("payloadFileName", "payloadName"),
                    "manifest Windows payload file name",
                    row_errors,
                )
                row_version = alias_string(
                    item,
                    ("version", "releaseVersion"),
                    "manifest Windows installer release version",
                    row_errors,
                )
                row_channel = alias_string(
                    item,
                    ("channel", "channelId"),
                    "manifest Windows installer release channel",
                    row_errors,
                )
                if row_version and root_version and row_version != root_version:
                    row_errors.append(
                        "manifest Windows installer release version must agree with "
                        "the manifest root"
                    )
                if row_channel and root_channel and row_channel != root_channel:
                    row_errors.append(
                        "manifest Windows installer release channel must agree with "
                        "the manifest root"
                    )
                effective_version = row_version or root_version
                effective_channel = row_channel or root_channel
                row = ManifestRow(
                    artifact_id=artifact_id,
                    file_name=file_name,
                    download_url=download_value,
                    sha256=str(item.get("sha256") or "").strip().lower(),
                    size_bytes=try_int(item.get("sizeBytes")),
                    payload_file_name=payload_file_name,
                    payload_download_url=exact_string(payload_download_value),
                    payload_sha256=str(item.get("payloadSha256") or "").strip().lower(),
                    payload_size_bytes=try_int(item.get("payloadSizeBytes")),
                    installer_mode=str(item.get("installerMode") or "").strip().lower(),
                    authoritative_identity=manifest_row_authoritative_identity(
                        item,
                        artifact_id=artifact_id,
                        file_name=file_name,
                        download_url=download_value,
                        payload_file_name=payload_file_name,
                        payload_download_url=exact_string(payload_download_value),
                        effective_version=effective_version,
                        effective_channel=effective_channel,
                    ),
                    release_proof_base_urls=release_proof_base_urls,
                    manifest_errors=tuple(row_errors),
                )
                document_rows.append(row)
                existing = rows.get(file_name)
                if existing is None:
                    rows[file_name] = row
                    continue
                combined_base_urls = tuple(
                    dict.fromkeys(
                        (*existing.release_proof_base_urls, *row.release_proof_base_urls)
                    )
                )
                existing_identity = replace(
                    existing,
                    release_proof_base_urls=(),
                    manifest_errors=(),
                )
                row_identity = replace(
                    row,
                    release_proof_base_urls=(),
                    manifest_errors=(),
                )
                combined_errors = [
                    *existing.manifest_errors,
                    *row.manifest_errors,
                ]
                if existing_identity != row_identity:
                    combined_errors.append(
                        "supplied release manifests disagree on the Windows installer row"
                    )
                rows[file_name] = replace(
                    existing,
                    release_proof_base_urls=combined_base_urls,
                    manifest_errors=tuple(dict.fromkeys(combined_errors)),
                )
        documents.append(
            ManifestDocument(
                path=manifest_path,
                rows=tuple(document_rows),
                release_proof_base_urls=release_proof_base_urls,
                errors=tuple(root_errors),
            )
        )
    return ManifestReadResult(rows=rows, documents=tuple(documents))


def validate_strict_manifest_documents(
    documents: tuple[ManifestDocument, ...],
    installer_names: list[str],
) -> list[str]:
    failures: list[str] = []
    expected_rows = Counter(installer_names)
    all_origins: set[CanonicalOrigin] = set()
    authoritative_rows: dict[str, tuple[Path, str]] = {}
    if not documents:
        return ["strict publisher mode requires at least one supplied release manifest"]

    for document in documents:
        prefix = f"manifest {document.path.name}: "
        failures.extend(prefix + failure for failure in document.errors)
        document_origins: set[CanonicalOrigin] = set()
        for base_url in document.release_proof_base_urls:
            parsed_base = parse_canonical_https_url(
                base_url,
                require_download_path=False,
                require_origin_only=True,
            )
            if parsed_base is None:
                failures.append(
                    prefix
                    + "releaseProof.baseUrl must be one lossless canonical HTTPS origin"
                )
            else:
                document_origins.add(parsed_base.origin)

        observed_rows = Counter(row.file_name for row in document.rows)
        if observed_rows != expected_rows:
            failures.append(
                prefix
                + "must contain exactly one row for every checked Windows installer "
                "and no duplicate or unexpected Windows installer rows"
            )

        for row in document.rows:
            failures.extend(prefix + failure for failure in row.manifest_errors)
            if not row.download_url:
                failures.append(
                    prefix
                    + "Windows installer row requires a nonempty canonical "
                    "downloadUrl/url"
                )
            existing_identity = authoritative_rows.get(row.file_name)
            if existing_identity is None:
                authoritative_rows[row.file_name] = (
                    document.path,
                    row.authoritative_identity,
                )
            elif existing_identity[1] != row.authoritative_identity:
                failures.append(
                    prefix
                    + "normalized Windows installer row disagrees with "
                    + f"manifest {existing_identity[0].name}"
                )
            authority = manifest_url_authority(row)
            failures.extend(prefix + failure for failure in authority.failures)
            if authority.trusted_origin is not None:
                document_origins.add(authority.trusted_origin)
        if len(document_origins) > 1:
            failures.append(prefix + "URL authority origins must all agree")
        all_origins.update(document_origins)

    if len(all_origins) > 1:
        failures.append("supplied release manifest URL authority origins must all agree")
    return list(dict.fromkeys(failures))


def try_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def find_installers(files_dir: Path | None, explicit_installers: list[Path]) -> list[Path]:
    installers: list[Path] = [path.resolve() for path in explicit_installers]
    if files_dir is not None and files_dir.is_dir():
        installers.extend(
            sorted(path.resolve() for path in files_dir.glob("chummer-*-win-*-installer.exe"))
        )
    seen: set[Path] = set()
    unique: list[Path] = []
    for installer in installers:
        if installer in seen:
            continue
        seen.add(installer)
        unique.append(installer)
    return unique


def split_tokens(value: str | None) -> set[str]:
    tokens: set[str] = set()
    for raw in str(value or "").replace(";", ",").replace("\n", ",").split(","):
        for token in raw.split():
            token = token.strip().lower()
            if token:
                tokens.add(token)
    return tokens


def is_disabled_installer(installer_path: Path, manifest_row: ManifestRow | None, disabled_tokens: set[str]) -> bool:
    if not disabled_tokens:
        return False

    candidates = {installer_path.name.lower()}
    if manifest_row is not None:
        for value in (manifest_row.artifact_id, manifest_row.file_name, manifest_row.download_url):
            value = str(value or "").strip().lower()
            if value:
                candidates.add(value)
    return any(token in candidates for token in disabled_tokens)


def read_appended_payload(installer_path: Path) -> PayloadCandidate | None:
    file_size = installer_path.stat().st_size
    if file_size < FOOTER_LENGTH:
        return None

    with installer_path.open("rb") as handle:
        handle.seek(file_size - FOOTER_LENGTH)
        footer = handle.read(FOOTER_LENGTH)
        payload_length = struct.unpack("<q", footer[:8])[0]
        magic = footer[8:]
        if magic != APPENDED_PAYLOAD_MAGIC:
            return None
        payload_offset = file_size - FOOTER_LENGTH - payload_length
        if payload_length <= 0 or payload_offset < 0:
            raise ValueError(f"{installer_path.name}: appended payload footer is invalid")
        handle.seek(payload_offset)
        data = handle.read(payload_length)
        if len(data) != payload_length:
            raise ValueError(f"{installer_path.name}: appended payload is truncated")
    return PayloadCandidate("bundled", "appended-footer", data)


def read_sidecar_payload(
    installer_path: Path,
    files_dir: Path | None,
    explicit_payload: Path | None,
    manifest_row: ManifestRow | None,
) -> PayloadCandidate | None:
    candidates: list[Path] = []
    if explicit_payload is not None:
        candidates.append(explicit_payload)
    if manifest_row is not None and manifest_row.payload_file_name:
        if files_dir is not None:
            candidates.append(files_dir / manifest_row.payload_file_name)
        candidates.append(installer_path.parent / manifest_row.payload_file_name)
    payload_name = expected_payload_name(installer_path.name)
    if payload_name:
        if files_dir is not None:
            candidates.append(files_dir / payload_name)
        candidates.append(installer_path.parent / payload_name)

    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return PayloadCandidate("bootstrap", str(candidate), candidate.read_bytes())
    return None


def validate_manifest_payload_metadata(candidate: PayloadCandidate, manifest_row: ManifestRow | None) -> list[str]:
    if manifest_row is None:
        return []
    failures: list[str] = []
    if manifest_row.installer_mode == "bootstrap" and candidate.mode != "bootstrap":
        failures.append("manifest says installerMode=bootstrap but the payload was not a sidecar payload")
    if manifest_row.installer_mode == "bootstrap":
        authority = manifest_url_authority(manifest_row)
        failures.extend(authority.failures)
        if not manifest_row.payload_file_name:
            failures.append("manifest installerMode=bootstrap is missing payloadFileName")
        if not manifest_row.payload_download_url:
            failures.append("manifest installerMode=bootstrap is missing payloadDownloadUrl")
        if not manifest_row.payload_sha256:
            failures.append("manifest installerMode=bootstrap is missing payloadSha256")
        elif not is_sha256_hex(manifest_row.payload_sha256):
            failures.append("manifest installerMode=bootstrap payloadSha256 is not a 64-character hex digest")
        if manifest_row.payload_size_bytes is None or manifest_row.payload_size_bytes <= 0:
            failures.append("manifest installerMode=bootstrap is missing payloadSizeBytes")
        if manifest_row.payload_file_name and manifest_row.payload_download_url:
            download_file_name = url_file_name(manifest_row.payload_download_url)
            if download_file_name != manifest_row.payload_file_name:
                failures.append(
                    f"manifest payloadDownloadUrl file name {download_file_name or '<empty>'} does not match payloadFileName {manifest_row.payload_file_name}"
                )
    if manifest_row.installer_mode == "bundled" and candidate.mode != "bundled":
        failures.append("manifest says installerMode=bundled but the payload was not appended")
    if candidate.mode == "bootstrap":
        source_name = Path(candidate.source).name
        if manifest_row.payload_file_name and manifest_row.payload_file_name != source_name:
            failures.append(
                f"manifest payloadFileName {manifest_row.payload_file_name} does not match sidecar {source_name}"
            )
        if manifest_row.payload_sha256 and manifest_row.payload_sha256 != sha256_bytes(candidate.data):
            failures.append("manifest payloadSha256 does not match sidecar bytes")
        if manifest_row.payload_size_bytes is not None and manifest_row.payload_size_bytes != len(candidate.data):
            failures.append(
                f"manifest payloadSizeBytes {manifest_row.payload_size_bytes} does not match sidecar size {len(candidate.data)}"
            )
    return failures


def validate_manifest_installer_metadata(installer_path: Path, manifest_row: ManifestRow | None) -> list[str]:
    if manifest_row is None:
        return []

    failures: list[str] = []
    if not manifest_row.sha256:
        failures.append("manifest Windows installer row is missing sha256")
    elif not is_sha256_hex(manifest_row.sha256):
        failures.append("manifest Windows installer row sha256 is not a 64-character hex digest")
    else:
        observed_sha256 = sha256_bytes(installer_path.read_bytes())
        if manifest_row.sha256 != observed_sha256:
            failures.append("manifest Windows installer row sha256 does not match installer bytes")

    observed_size = installer_path.stat().st_size
    if manifest_row.size_bytes is None or manifest_row.size_bytes <= 0:
        failures.append("manifest Windows installer row is missing sizeBytes")
    elif manifest_row.size_bytes != observed_size:
        failures.append(
            f"manifest Windows installer row sizeBytes {manifest_row.size_bytes} does not match installer size {observed_size}"
        )

    return failures


def validate_bootstrap_installer_size(installer_path: Path, manifest_row: ManifestRow | None) -> list[str]:
    if manifest_row is None or manifest_row.installer_mode != "bootstrap":
        return []

    observed_size = installer_path.stat().st_size
    failures: list[str] = []
    if observed_size > MAX_BOOTSTRAP_INSTALLER_BYTES:
        failures.append(
            f"manifest installerMode=bootstrap but installer is {observed_size} bytes; "
            f"bootstrap launchers must be <= {MAX_BOOTSTRAP_INSTALLER_BYTES} bytes"
        )
    if manifest_row.payload_size_bytes is not None and observed_size >= manifest_row.payload_size_bytes:
        failures.append(
            f"manifest installerMode=bootstrap but installer size {observed_size} is not smaller than payloadSizeBytes {manifest_row.payload_size_bytes}"
        )
    return failures


def scan_embedded_bootstrap_metadata(
    installer_bytes: bytes,
    label: str,
) -> EmbeddedMetadataScan:
    marker = f"{label}=".encode("ascii")
    values: list[str] = []
    failures: list[str] = []
    occurrence_count = 0
    offset = 0
    while True:
        marker_offset = installer_bytes.find(marker, offset)
        if marker_offset < 0:
            return EmbeddedMetadataScan(
                occurrence_count=occurrence_count,
                values=tuple(values),
                failures=tuple(failures),
            )
        occurrence_count += 1
        offset = marker_offset + len(marker)
        if marker_offset > 0 and installer_bytes[marker_offset - 1] not in b"\r\n\0":
            failures.append("occurrence is not framed at a line or NUL boundary")
            continue
        terminators = [
            position
            for delimiter in (b"\r", b"\n", b"\0")
            if (position := installer_bytes.find(delimiter, offset)) >= 0
        ]
        if not terminators:
            failures.append("occurrence reaches EOF without a CR, LF, or NUL terminator")
            continue
        raw_value = installer_bytes[offset:min(terminators)]
        if not raw_value:
            failures.append("occurrence has an empty value")
            continue
        try:
            value = raw_value.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            failures.append("occurrence is not canonical UTF-8")
            continue
        values.append(value)


def validate_bootstrap_installer_metadata(
    installer_path: Path,
    candidate: PayloadCandidate,
    manifest_row: ManifestRow | None,
) -> list[str]:
    if candidate.mode != "bootstrap":
        return []

    payload_download_url = ""
    payload_sha256 = manifest_row.payload_sha256 if manifest_row is not None else ""
    payload_size_bytes = manifest_row.payload_size_bytes if manifest_row is not None else None

    sidecar_path = Path(candidate.source + ".json")
    if sidecar_path.is_file():
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            sidecar = {}
        if isinstance(sidecar, dict):
            sidecar_download_url = exact_string(sidecar.get("downloadUrl"))
            parsed_sidecar_url = parse_canonical_https_url(
                sidecar_download_url,
                require_download_path=True,
            )
            if (
                parsed_sidecar_url is not None
                and manifest_row is not None
                and sidecar_url_matches_manifest(
                    parsed_sidecar_url,
                    manifest_row,
                    manifest_url_authority(manifest_row),
                )
            ):
                payload_download_url = sidecar_download_url
            payload_sha256 = payload_sha256 or str(sidecar.get("sha256") or "").strip().lower()
            payload_size_bytes = (
                payload_size_bytes
                if payload_size_bytes is not None
                else try_int(sidecar.get("sizeBytes"))
            )

    failures: list[str] = []
    if not payload_download_url:
        failures.append(
            "bootstrap installer has no validated absolute sidecar payloadDownloadUrl metadata"
        )
    if not payload_download_url or not payload_sha256 or payload_size_bytes is None:
        return failures

    installer_bytes = installer_path.read_bytes()
    required_values = {
        "payloadDownloadUrl": payload_download_url,
        "payloadSha256": payload_sha256,
        "payloadSizeBytes": str(payload_size_bytes),
    }
    for label, value in required_values.items():
        scan = scan_embedded_bootstrap_metadata(installer_bytes, label)
        if scan.occurrence_count == 0:
            failures.append(f"bootstrap installer does not contain embedded {label} metadata")
            continue
        if scan.occurrence_count != 1:
            failures.append(
                f"bootstrap installer must contain exactly one embedded {label} metadata occurrence"
            )
        failures.extend(
            f"bootstrap installer embedded {label} metadata is malformed: {failure}"
            for failure in scan.failures
        )
        if not scan.failures and scan.values != (value,):
            failures.append(
                f"bootstrap installer embedded {label} metadata does not equal validated metadata"
            )
    return failures


def validate_bootstrap_sidecar_metadata(
    installer_path: Path,
    candidate: PayloadCandidate,
    manifest_row: ManifestRow | None,
) -> list[str]:
    if candidate.mode != "bootstrap":
        return []

    sidecar_path = Path(candidate.source + ".json")
    if not sidecar_path.is_file():
        return [f"bootstrap payload sidecar metadata is missing: {sidecar_path.name}"]

    try:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return [f"bootstrap payload sidecar metadata is invalid JSON: {sidecar_path.name}: {exc}"]

    if not isinstance(payload, dict):
        return [f"bootstrap payload sidecar metadata is not a JSON object: {sidecar_path.name}"]

    failures: list[str] = []
    expected_file_name = Path(candidate.source).name
    if str(payload.get("contractName") or "").strip() != "chummer6-ui.windows_bootstrap_payload":
        failures.append("bootstrap payload sidecar metadata has unexpected contractName")
    if str(payload.get("fileName") or "").strip() != expected_file_name:
        failures.append(
            f"bootstrap payload sidecar metadata fileName does not match payload: expected {expected_file_name}"
        )
    if str(payload.get("installerFileName") or "").strip() != installer_path.name:
        failures.append(
            f"bootstrap payload sidecar metadata installerFileName does not match installer: expected {installer_path.name}"
        )

    observed_sha256 = sha256_bytes(candidate.data)
    if str(payload.get("sha256") or "").strip().lower() != observed_sha256:
        failures.append("bootstrap payload sidecar metadata sha256 does not match payload bytes")

    observed_size = len(candidate.data)
    try:
        metadata_size = int(payload.get("sizeBytes"))
    except (TypeError, ValueError):
        metadata_size = None
    if metadata_size != observed_size:
        failures.append(
            f"bootstrap payload sidecar metadata sizeBytes does not match payload size {observed_size}"
        )

    sidecar_download_url = exact_string(payload.get("downloadUrl"))
    parsed_sidecar_url = parse_canonical_https_url(
        sidecar_download_url,
        require_download_path=True,
    )
    if parsed_sidecar_url is None:
        failures.append(
            "bootstrap payload sidecar metadata downloadUrl must be a lossless "
            "canonical absolute HTTPS URL"
        )

    if manifest_row is not None:
        if manifest_row.payload_file_name and manifest_row.payload_file_name != str(payload.get("fileName") or "").strip():
            failures.append("bootstrap payload sidecar metadata fileName does not match manifest payloadFileName")
        if (
            parsed_sidecar_url is not None
            and not sidecar_url_matches_manifest(
                parsed_sidecar_url,
                manifest_row,
                manifest_url_authority(manifest_row),
            )
        ):
            failures.append("bootstrap payload sidecar metadata downloadUrl does not match manifest payloadDownloadUrl")
        if manifest_row.payload_sha256 and manifest_row.payload_sha256 != str(payload.get("sha256") or "").strip().lower():
            failures.append("bootstrap payload sidecar metadata sha256 does not match manifest payloadSha256")
        if manifest_row.payload_size_bytes is not None and manifest_row.payload_size_bytes != metadata_size:
            failures.append("bootstrap payload sidecar metadata sizeBytes does not match manifest payloadSizeBytes")
    elif parsed_sidecar_url is not None:
        failures.append(
            "bootstrap payload sidecar metadata has no trusted manifest URL authority"
        )

    return failures


def parse_heads_json_base64(value: str) -> list[str]:
    if not value.strip():
        return []
    decoded = base64.b64decode(value)
    payload = json.loads(decoded.decode("utf-8"))
    if not isinstance(payload, list):
        return []
    entries: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        launch = str(item.get("launchExecutable") or "").strip()
        root = str(item.get("relativeRoot") or "").strip().strip("/\\")
        if not launch:
            continue
        entries.append(normalize_zip_name(f"{root}/{launch}" if root else launch))
    return entries


def validate_zip_payload(
    installer_name: str,
    candidate: PayloadCandidate,
    expected_launches: list[str],
    expected_entries: list[str],
    require_sample: bool,
) -> list[str]:
    failures: list[str] = []
    if not candidate.data.startswith(ZIP_LOCAL_FILE_MAGIC):
        failures.append("payload does not start with ZIP local-file header magic")
    try:
        with zipfile.ZipFile(BytesIO(candidate.data), "r") as archive:
            names = [normalize_zip_name(info.filename) for info in archive.infolist() if not info.is_dir()]
            if not names:
                return ["payload zip contains no files"]
            for name in names:
                parts = [part for part in name.split("/") if part]
                if name.startswith("/") or any(part == ".." for part in parts):
                    failures.append(f"payload zip contains unsafe entry: {name}")
            name_set = set(names)
            basename_set = {Path(name).name.lower() for name in names}
            for expected_entry in expected_entries:
                normalized = normalize_zip_name(expected_entry)
                if normalized not in name_set:
                    failures.append(f"payload zip is missing expected entry: {normalized}")
            launches = expected_launches or infer_launch_executables(installer_name)
            for launch in launches:
                if Path(launch).name.lower() not in basename_set:
                    failures.append(f"payload zip is missing launch executable: {Path(launch).name}")
            if require_sample and "soma-career.chum5" not in basename_set:
                failures.append("payload zip is missing bundled sample character: Soma-Career.chum5")
    except zipfile.BadZipFile as exc:
        failures.append(f"payload is not a readable zip: {exc}")
    return failures


def validate_windows_executable_structure(installer_path: Path) -> list[str]:
    data = installer_path.read_bytes()
    failures: list[str] = []
    if not data.startswith(WINDOWS_EXE_MAGIC):
        return ["installer does not start with Windows MZ executable magic"]
    if len(data) < 0x40:
        return ["installer is too small to contain a Windows PE header"]

    pe_offset = int.from_bytes(data[0x3C:0x40], "little", signed=False)
    if pe_offset <= 0 or pe_offset + len(WINDOWS_PE_MAGIC) > len(data):
        failures.append("installer has an invalid Windows PE header offset")
    elif data[pe_offset:pe_offset + len(WINDOWS_PE_MAGIC)] != WINDOWS_PE_MAGIC:
        failures.append("installer is missing the Windows PE header signature")

    if b"installer-stub" in data[:4096]:
        failures.append("installer still contains placeholder installer-stub bytes")

    return failures


def verify_installer(
    installer_path: Path,
    files_dir: Path | None,
    explicit_payload: Path | None,
    manifest_row: ManifestRow | None,
    expected_launches: list[str],
    expected_entries: list[str],
    require_sample: bool,
    require_embedded_bootstrap_metadata: bool,
    require_manifest_row: bool,
) -> list[str]:
    failures: list[str] = []
    if not installer_path.is_file():
        return [f"installer does not exist: {installer_path}"]
    if manifest_row is not None:
        failures.extend(manifest_row.manifest_errors)
    if installer_path.stat().st_size <= FOOTER_LENGTH:
        failures.append(
            f"installer is too small to contain a payload-aware executable: {installer_path}"
        )
        return [f"{installer_path.name}: {failure}" for failure in failures]
    if require_manifest_row and manifest_row is None:
        return [f"{installer_path.name}: Windows installer is missing from the supplied release manifest"]
    failures.extend(validate_windows_executable_structure(installer_path))

    candidate = read_appended_payload(installer_path)
    if candidate is None:
        candidate = read_sidecar_payload(installer_path, files_dir, explicit_payload, manifest_row)

    if candidate is None:
        payload_name = expected_payload_name(installer_path.name) or "<unknown>"
        failures.append(
            f"no appended payload and no bootstrap sidecar '{payload_name}' was found"
        )
        return [f"{installer_path.name}: {failure}" for failure in failures]

    failures.extend(validate_manifest_installer_metadata(installer_path, manifest_row))
    failures.extend(validate_manifest_payload_metadata(candidate, manifest_row))
    failures.extend(validate_bootstrap_installer_size(installer_path, manifest_row))
    failures.extend(validate_bootstrap_sidecar_metadata(installer_path, candidate, manifest_row))
    if require_embedded_bootstrap_metadata:
        failures.extend(validate_bootstrap_installer_metadata(installer_path, candidate, manifest_row))
    failures.extend(
        validate_zip_payload(
            installer_path.name,
            candidate,
            expected_launches,
            expected_entries,
            require_sample,
        )
    )
    return [f"{installer_path.name}: {failure}" for failure in failures]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail if a Windows Chummer installer cannot reach its bundled/bootstrap payload."
    )
    parser.add_argument("--files-dir", type=Path, help="Bundle files directory containing installers and payload sidecars.")
    parser.add_argument("--manifest", type=Path, action="append", default=[], help="Release manifest to cross-check payload metadata.")
    parser.add_argument("--installer", type=Path, action="append", default=[], help="Specific installer .exe to check.")
    parser.add_argument("--payload", type=Path, help="Specific payload zip to use for an explicit installer check.")
    parser.add_argument("--expected-launch", action="append", default=[], help="Launch executable basename expected in the payload zip.")
    parser.add_argument("--expected-entry", action="append", default=[], help="Exact zip entry expected in the payload zip.")
    parser.add_argument("--heads-json-base64", default="", help="Installer heads JSON metadata used to derive exact payload entries.")
    parser.add_argument("--require-sample", action="store_true", help="Require the legacy Soma sample character in the payload.")
    parser.add_argument(
        "--require-embedded-bootstrap-metadata",
        action="store_true",
        help="Require bootstrap installers to contain the manifest payload URL, SHA-256, and size metadata.",
    )
    parser.add_argument(
        "--require-manifest-row",
        action="store_true",
        help=(
            "Require every checked Windows installer to have one canonical, "
            "identity-consistent row in every supplied release manifest."
        ),
    )
    parser.add_argument(
        "--disabled-artifact-id",
        action="append",
        default=[],
        help="Skip a quarantined Windows installer artifact id, file name, or URL.",
    )
    parser.add_argument("--allow-empty", action="store_true", help="Pass when no Windows installers are present.")
    args = parser.parse_args()

    files_dir = args.files_dir.resolve() if args.files_dir else None
    manifest_result = read_manifest_rows([path.resolve() for path in args.manifest])
    manifest_rows = manifest_result.rows
    disabled_tokens: set[str] = set()
    for value in args.disabled_artifact_id:
        disabled_tokens.update(split_tokens(value))
    disabled_tokens.update(split_tokens(os.environ.get("CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS")))
    disabled_tokens.update(split_tokens(os.environ.get("CHUMMER_RELEASE_DISABLED_ARTIFACT_IDS")))
    all_installers = find_installers(files_dir, args.installer)
    installers = [
        installer
        for installer in all_installers
        if not is_disabled_installer(installer, manifest_rows.get(installer.name), disabled_tokens)
    ]
    strict_manifest_failures = (
        validate_strict_manifest_documents(
            manifest_result.documents,
            [installer.name for installer in all_installers],
        )
        if args.require_manifest_row
        else []
    )
    if not installers:
        if strict_manifest_failures:
            print("windows_installer_payload_gate:fail", file=sys.stderr)
            for failure in strict_manifest_failures:
                print(f" - {failure}", file=sys.stderr)
            return 1
        if args.allow_empty:
            print("windows_installer_payload_gate:ok no_windows_installers")
            return 0
        print("windows_installer_payload_gate:fail no Windows installers found", file=sys.stderr)
        return 1

    expected_entries = [normalize_zip_name(entry) for entry in args.expected_entry]
    expected_entries.extend(parse_heads_json_base64(args.heads_json_base64))
    require_sample = args.require_sample or is_truthy(os.environ.get("CHUMMER_WINDOWS_INSTALLER_REQUIRE_SAMPLE_PAYLOAD"))
    require_embedded_bootstrap_metadata = (
        args.require_embedded_bootstrap_metadata
        or is_truthy(os.environ.get("CHUMMER_WINDOWS_INSTALLER_REQUIRE_EMBEDDED_BOOTSTRAP_METADATA"))
    )
    failures: list[str] = list(strict_manifest_failures)
    for installer_path in installers:
        manifest_row = manifest_rows.get(installer_path.name)
        failures.extend(
            verify_installer(
                installer_path,
                files_dir,
                args.payload.resolve() if args.payload else None,
                manifest_row,
                [str(item).strip() for item in args.expected_launch if str(item).strip()],
                expected_entries,
                require_sample,
                require_embedded_bootstrap_metadata,
                args.require_manifest_row,
            )
        )

    if failures:
        print("windows_installer_payload_gate:fail", file=sys.stderr)
        for failure in dict.fromkeys(failures):
            print(f" - {failure}", file=sys.stderr)
        return 1

    print(f"windows_installer_payload_gate:ok checked={len(installers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
