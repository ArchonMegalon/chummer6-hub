#!/usr/bin/env python3
"""Shared fail-closed validation for Windows proof provenance and freshness."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import struct
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


MANIFEST_SCHEMA = "chummer.windows-proof.manifest/v2"
PROVENANCE_CONTRACT = "chummer6.build_provenance.v1"
PROVENANCE_STATE_CONTRACT = "chummer6.build_provenance_invocation_state.v1"
PROVENANCE_BUILDER_ID = "chummer-windows-release-bootstrap"
PROVENANCE_BUILD_TYPE = "windows-desktop-release"
PROVENANCE_TARGET_ID = "desktop-avalonia"
PROVENANCE_ARTIFACT_ID = "avalonia-win-x64-installer"
PROVENANCE_ARTIFACT_KIND = "desktop_download"
PROVENANCE_SOURCE_REPOSITORY = "chummer-presentation"
PROVENANCE_SOURCE_MATERIALS = frozenset(
    {
        "chummer-core-engine",
        "chummer.run-services",
        "chummer-ui-kit",
        "chummer-hub-registry",
        "chummer-media-factory",
        "chummer5a",
    }
)
PROVENANCE_BUILD_INPUT_LABELS = frozenset(
    {
        "windows-bootstrap-recipe",
        "desktop-project",
        "desktop-installer-recipe",
        "dotnet-sdk-selection",
    }
)
SBOM_GENERATOR = "deterministic_project.assets.json_inventory.v1"
PROVENANCE_MAX_AGE = timedelta(hours=24)
MANIFEST_MAX_LIFETIME = timedelta(hours=24)
FUTURE_CLOCK_SKEW = timedelta(minutes=5)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")

# The published proof payload currently contains 242 entries, expands to about
# 116 MiB, and has a maximum per-entry compression ratio below 14:1.  These
# bounds leave deliberate release headroom without allowing an admitted proof
# artifact to become an unbounded archive parser or decompression workload.
BOOTSTRAP_ZIP_MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
BOOTSTRAP_ZIP_MAX_ENTRIES = 2048
BOOTSTRAP_ZIP_MAX_ENTRY_BYTES = 128 * 1024 * 1024
BOOTSTRAP_ZIP_MAX_TOTAL_BYTES = 512 * 1024 * 1024
BOOTSTRAP_ZIP_MAX_COMPRESSION_RATIO = 100
BOOTSTRAP_ZIP_MAX_CENTRAL_DIRECTORY_BYTES = 16 * 1024 * 1024
BOOTSTRAP_ZIP_MAX_INSPECTABLE_TEXT_BYTES = 16 * 1024 * 1024
BOOTSTRAP_ZIP_MAX_PATH_BYTES = 1024
BOOTSTRAP_ZIP_MAX_SEGMENT_BYTES = 255
BOOTSTRAP_ZIP_POLICY_VERSION = "chummer6.windows-bootstrap-zip-admission.v1"

_ZIP_ALLOWED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_ZIP_SENSITIVE_EXTENSIONS = frozenset(
    {
        ".key",
        ".jks",
        ".keystore",
        ".p12",
        ".pfx",
        ".pk8",
        ".pkcs12",
        ".ppk",
        ".snk",
    }
)
_ZIP_WINDOWS_INVALID_SEGMENT_CHARACTERS = frozenset('<>:"\\|?*')
_ZIP_WINDOWS_RESERVED_STEMS = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
    }
)
_ZIP_PRIVATE_KEY_MARKER = re.compile(
    br"-----BEGIN(?:[ \t]+[A-Z0-9]+)*[ \t]+PRIVATE[ \t]+KEY(?:[ \t]+BLOCK)?-----",
    re.IGNORECASE,
)
_ZIP_AUTHORIZATION_BEARER = re.compile(
    br"authorization[\"']?[ \t]*[:=][ \t]*[\"']?bearer[ \t]+[^\x00-\x20\"']",
    re.IGNORECASE,
)
_ZIP_CREDENTIAL_ASSIGNMENT = re.compile(
    br"(?<![A-Za-z0-9])(?:bearer(?:[_-]?token)?|refresh[_-]?token|access[_-]?token|client[_-]?secret|private[_-]?key(?:[_-]?id)?)[\"']?[ \t]*[:=][ \t]*(?:[\"'][ \t]*[^\x00-\x20\"']|[^\x00-\x20\"'])",
    re.IGNORECASE,
)
_ZIP_CONNECTION_ASSIGNMENT = re.compile(
    br"(?<![A-Za-z0-9])(?:connection[_-]?strings?(?:(?:__|:)[A-Za-z0-9_.-]+)?|default[_-]?connection)[\"']?[ \t]*[:=][ \t]*(?:[\"'][ \t]*[^\x00-\x20\"']|[^\x00-\x20\"'])",
    re.IGNORECASE,
)

_ZIP_SENSITIVE_JSON_KEYS = frozenset(
    {
        "authorization",
        "bearer",
        "bearertoken",
        "refreshtoken",
        "accesstoken",
        "clientsecret",
        "privatekey",
        "privatekeyid",
        "connectionstring",
        "connectionstrings",
        "defaultconnection",
    }
)
_ZIP_BINARY_SAFE_CONTENT_RULES = (
    ("content.private_key_marker", _ZIP_PRIVATE_KEY_MARKER),
    ("content.bearer_assignment", _ZIP_AUTHORIZATION_BEARER),
    ("content.credential_assignment", _ZIP_CREDENTIAL_ASSIGNMENT),
    ("content.connection_string_assignment", _ZIP_CONNECTION_ASSIGNMENT),
)
_ZIP_TEXT_ASSIGNMENT_RULES = (
    ("content.bearer_assignment", _ZIP_AUTHORIZATION_BEARER),
    ("content.credential_assignment", _ZIP_CREDENTIAL_ASSIGNMENT),
    ("content.connection_string_assignment", _ZIP_CONNECTION_ASSIGNMENT),
)


class DuplicateJsonKey(ValueError):
    pass


class BootstrapZipPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class GovernedWindowsEvidence:
    invocation_id: str
    provenance_sha256: str
    sbom_sha256: str
    build_started_at: datetime
    generated_at: datetime


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    folded: set[str] = set()
    for key, value in pairs:
        normalized = key.casefold()
        if normalized in folded:
            raise DuplicateJsonKey(f"duplicate or case-colliding JSON key: {key}")
        folded.add(normalized)
        result[key] = value
    return result


def load_unique_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError, DuplicateJsonKey) as exc:
        raise ValueError(f"{label} is not a unique-key UTF-8 JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value, raw


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bootstrap_zip_error(
    label: str,
    rule_id: str,
    *,
    entry_ordinal: int | None = None,
    entry_name: str | None = None,
    entry_name_sha256: str | None = None,
) -> BootstrapZipPolicyError:
    diagnostic = (
        f"{label} violates policy={BOOTSTRAP_ZIP_POLICY_VERSION} rule={rule_id}"
    )
    if entry_ordinal is not None:
        diagnostic += f" entry_ordinal={entry_ordinal}"
    if entry_name is not None:
        encoded = entry_name.encode("utf-8", errors="surrogatepass")
        entry_name_sha256 = hashlib.sha256(encoded).hexdigest()
    if entry_name_sha256 is not None:
        diagnostic += f" entry_name_sha256={entry_name_sha256[:64]}"
    return BootstrapZipPolicyError(diagnostic)


def _normalize_bootstrap_zip_path(
    name: str,
    label: str,
    entry_ordinal: int,
) -> tuple[str, bool]:
    def path_error(rule_id: str) -> BootstrapZipPolicyError:
        return _bootstrap_zip_error(
            label,
            rule_id,
            entry_ordinal=entry_ordinal,
            entry_name=name,
        )

    if not name or "\x00" in name:
        raise path_error("path.non_empty")
    if any(ord(character) < 0x20 or ord(character) > 0x7E for character in name):
        raise path_error("path.ascii_printable")
    if "\\" in name:
        raise path_error("path.forward_slash")
    encoded = name.encode("ascii")
    if len(encoded) > BOOTSTRAP_ZIP_MAX_PATH_BYTES:
        raise path_error("path.length")
    if name.startswith(("/", "//")) or re.match(r"^[A-Za-z]:", name):
        raise path_error("path.relative")

    is_directory = name.endswith("/")
    candidate = name[:-1] if is_directory else name
    segments = candidate.split("/")
    if not candidate or any(segment in ("", ".", "..") for segment in segments):
        raise path_error("path.relative")
    for segment in segments:
        if len(segment) > BOOTSTRAP_ZIP_MAX_SEGMENT_BYTES:
            raise path_error("path.segment_length")
        if (
            any(character in _ZIP_WINDOWS_INVALID_SEGMENT_CHARACTERS for character in segment)
            or segment.endswith((".", " "))
        ):
            raise path_error("path.windows_invalid_segment")
        stem = segment.split(".", 1)[0].casefold()
        if stem in _ZIP_WINDOWS_RESERVED_STEMS:
            raise path_error("path.windows_reserved_device")
    return "/".join(segments), is_directory


def _bootstrap_zip_collision_key(normalized_path: str) -> str:
    # Admission already constrains names to printable ASCII, so this is an
    # intentionally culture- and runtime-independent collision key.
    return normalized_path.lower()


def _has_sensitive_bootstrap_zip_name(normalized_path: str) -> bool:
    for segment in normalized_path.split("/"):
        lowered = segment.casefold()
        suffix = Path(lowered).suffix
        if lowered == ".env" or lowered.startswith(".env."):
            return True
        if suffix in _ZIP_SENSITIVE_EXTENSIONS:
            return True
        collapsed = re.sub(r"[-_. ]+", "", lowered)
        collapsed_stem = re.sub(r"[-_. ]+", "", Path(lowered).stem)
        if "privatekeyid" in collapsed or "serviceaccount" in collapsed:
            return True
        if suffix == ".pem" and "privatekey" in collapsed_stem:
            return True
        if collapsed in {
            "applicationdefaultcredentialsjson",
            "gcpcredentialsjson",
            "googlecredentialsjson",
        }:
            return True
    return False


def _contains_google_service_account(value: Any, depth: int = 0) -> bool:
    if depth > 32:
        return False
    if isinstance(value, dict):
        folded = {str(key).casefold(): child for key, child in value.items()}
        keys = set(folded)
        service_account_type = str(folded.get("type") or "").casefold() == "service_account"
        google_key_set = {"private_key", "private_key_id", "client_email", "token_uri"}
        structural_key_set = {"private_key", "client_email", "token_uri", "project_id"}
        if (service_account_type and google_key_set.issubset(keys)) or structural_key_set.issubset(keys):
            return True
        return any(_contains_google_service_account(child, depth + 1) for child in value.values())
    if isinstance(value, list):
        return any(_contains_google_service_account(child, depth + 1) for child in value)
    return False


def _json_value_is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list)):
        return bool(value)
    return True


def _contains_sensitive_json_value(value: Any, depth: int = 0) -> bool:
    """Find sensitive JSON keys without ever rendering their values."""

    if depth > 32:
        return False
    if isinstance(value, dict):
        for key, child in value.items():
            collapsed_key = re.sub(r"[-_. ]+", "", str(key).casefold())
            if (
                collapsed_key in _ZIP_SENSITIVE_JSON_KEYS
                or collapsed_key.startswith("connectionstrings")
            ) and _json_value_is_non_empty(child):
                return True
            if _contains_sensitive_json_value(child, depth + 1):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_sensitive_json_value(child, depth + 1) for child in value)
    return False


def _has_known_binary_magic(raw: bytes) -> bool:
    return raw.startswith((b"MZ", b"\x7fELF", b"\x89PNG", b"\xff\xd8\xff", b"%PDF"))


def _looks_like_text(raw: bytes) -> bool:
    sample = raw[: 64 * 1024]
    if not sample:
        return True
    if _has_known_binary_magic(sample):
        return False
    try:
        decoded = sample.decode("utf-8-sig")
    except UnicodeError:
        decoded = ""
    if not decoded and len(sample) % 2 == 0:
        for encoding in ("utf-16", "utf-16-le", "utf-16-be"):
            try:
                candidate = sample.decode(encoding)
            except UnicodeError:
                continue
            if candidate:
                decoded = candidate
                break
    if not decoded:
        return False
    acceptable = sum(character.isprintable() or character in "\r\n\t" for character in decoded)
    return acceptable / len(decoded) >= 0.95


def _scan_bootstrap_zip_entry(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    normalized_path: str,
    label: str,
    entry_ordinal: int,
    entry_name: str,
) -> None:
    def entry_error(rule_id: str) -> BootstrapZipPolicyError:
        return _bootstrap_zip_error(
            label,
            rule_id,
            entry_ordinal=entry_ordinal,
            entry_name=entry_name,
        )

    collect_inspectable = info.file_size <= BOOTSTRAP_ZIP_MAX_INSPECTABLE_TEXT_BYTES
    collected = bytearray() if collect_inspectable else None
    prefix = bytearray()
    tail = b""
    observed = 0
    streamed_sensitive_rule: str | None = None
    try:
        with archive.open(info, "r") as stream:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                observed += len(chunk)
                if observed > info.file_size or observed > BOOTSTRAP_ZIP_MAX_ENTRY_BYTES:
                    raise entry_error("entry.decompressed_size")
                if len(prefix) < 4096:
                    prefix.extend(chunk[: 4096 - len(prefix)])
                if collected is not None:
                    collected.extend(chunk)

                scan_window = tail + chunk
                for rule, pattern in _ZIP_BINARY_SAFE_CONTENT_RULES:
                    if pattern.search(scan_window):
                        if rule == "content.private_key_marker":
                            raise entry_error(rule)
                        if streamed_sensitive_rule is None:
                            streamed_sensitive_rule = rule
                tail = (tail + chunk)[-4096:]
    except BootstrapZipPolicyError:
        raise
    except (EOFError, NotImplementedError, OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        raise entry_error("entry.integrity") from exc

    if observed != info.file_size:
        raise entry_error("entry.declared_size")

    prefix_bytes = bytes(prefix)
    if prefix_bytes.startswith(b"\xef\xbb\xbf"):
        prefix_bytes = prefix_bytes[3:]
    looks_like_json = prefix_bytes.lstrip().startswith((b"{", b"["))
    if collected is None:
        if looks_like_json:
            raise entry_error("content.json_inspection_size")
        if streamed_sensitive_rule is not None:
            raise entry_error(streamed_sensitive_rule)
        if _has_known_binary_magic(prefix_bytes):
            return
        # Large entries are admitted only when their binary nature can be
        # established without an incomplete text/JSON decode. Content scanning
        # above still covers every streamed byte before this decision.
        raise entry_error("content.text_inspection_size")

    collected_bytes = bytes(collected)
    if looks_like_json:
        document: Any | None
        try:
            document = json.loads(collected_bytes.decode("utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError):
            document = None
        if document is not None:
            if _contains_google_service_account(document):
                raise entry_error("content.google_service_account_json")
            if _contains_sensitive_json_value(document):
                raise entry_error(
                    streamed_sensitive_rule or "content.sensitive_json_value"
                )
            # Valid JSON is decided structurally so null, empty-string, empty
            # object, and empty-array sensitive values remain genuinely empty.
            return

    if streamed_sensitive_rule is not None:
        raise entry_error(streamed_sensitive_rule)
    if _looks_like_text(collected_bytes):
        text_window = collected_bytes.replace(b"\x00", b"")
        for rule, pattern in _ZIP_TEXT_ASSIGNMENT_RULES:
            if pattern.search(text_window):
                raise entry_error(rule)


def _validate_bootstrap_zip_local_headers(
    archive: zipfile.ZipFile,
    entries: list[zipfile.ZipInfo],
    label: str,
    archive_size: int,
) -> None:
    stream = archive.fp
    central_directory_offset = archive.start_dir
    if (
        stream is None
        or central_directory_offset < 0
        or central_directory_offset > archive_size
    ):
        raise _bootstrap_zip_error(label, "archive.directory_bounds")

    # zipfile exposes the adjusted central-directory start but not its declared
    # size. Parse the canonical EOCD so this bound is identical to the server
    # validator and is checked before any central-directory-derived work.
    tail_size = min(archive_size, 22 + 65535)
    try:
        stream.seek(archive_size - tail_size)
        tail = stream.read(tail_size)
    except (OSError, OverflowError, ValueError) as exc:
        raise _bootstrap_zip_error(label, "archive.directory_bounds") from exc
    eocd_index = -1
    for candidate in range(len(tail) - 22, -1, -1):
        if tail[candidate : candidate + 4] != b"PK\x05\x06":
            continue
        comment_length = struct.unpack_from("<H", tail, candidate + 20)[0]
        if candidate + 22 + comment_length == len(tail):
            eocd_index = candidate
            break
    if eocd_index < 0:
        raise _bootstrap_zip_error(label, "archive.directory_bounds")
    central_directory_size = struct.unpack_from("<I", tail, eocd_index + 12)[0]
    declared_central_directory_offset = struct.unpack_from("<I", tail, eocd_index + 16)[0]
    eocd_offset = archive_size - tail_size + eocd_index
    if central_directory_size > BOOTSTRAP_ZIP_MAX_CENTRAL_DIRECTORY_BYTES:
        raise _bootstrap_zip_error(label, "archive.central_directory_size")
    if (
        declared_central_directory_offset != central_directory_offset
        or central_directory_offset + central_directory_size != eocd_offset
    ):
        raise _bootstrap_zip_error(label, "archive.directory_bounds")

    seen_offsets: set[int] = set()
    for entry_ordinal, info in enumerate(entries, start=1):
        encoding = "utf-8" if info.flag_bits & 0x800 else (archive.metadata_encoding or "cp437")
        try:
            central_name = info.orig_filename.encode(encoding)
        except (LookupError, UnicodeError) as exc:
            raise _bootstrap_zip_error(
                label,
                "entry.name_binding",
                entry_ordinal=entry_ordinal,
                entry_name=info.orig_filename,
            ) from exc
        name_sha256 = hashlib.sha256(central_name).hexdigest()

        def entry_error(rule_id: str) -> BootstrapZipPolicyError:
            return _bootstrap_zip_error(
                label,
                rule_id,
                entry_ordinal=entry_ordinal,
                entry_name_sha256=name_sha256,
            )

        local_offset = info.header_offset
        if (
            local_offset < 0
            or local_offset in seen_offsets
            or local_offset + 30 > central_directory_offset
        ):
            raise entry_error("entry.local_header_bounds")
        seen_offsets.add(local_offset)

        try:
            stream.seek(local_offset)
            header = stream.read(30)
        except (OSError, OverflowError, ValueError) as exc:
            raise entry_error("entry.local_header_bounds") from exc
        if len(header) != 30:
            raise entry_error("entry.local_header_bounds")
        if header[:4] != b"PK\x03\x04":
            raise entry_error("entry.local_header")

        local_flags = struct.unpack_from("<H", header, 6)[0]
        local_method = struct.unpack_from("<H", header, 8)[0]
        local_name_length = struct.unpack_from("<H", header, 26)[0]
        local_extra_length = struct.unpack_from("<H", header, 28)[0]
        data_offset = local_offset + 30 + local_name_length + local_extra_length
        data_end = data_offset + info.compress_size
        if data_offset > central_directory_offset or data_end > central_directory_offset:
            raise entry_error("entry.local_header_bounds")

        try:
            stream.seek(local_offset + 30)
            local_name = stream.read(local_name_length)
        except (OSError, OverflowError, ValueError) as exc:
            raise entry_error("entry.local_header_bounds") from exc
        if len(local_name) != local_name_length:
            raise entry_error("entry.local_header_bounds")
        if (local_flags | info.flag_bits) & 0x41:
            raise entry_error("entry.encrypted")
        if local_flags != info.flag_bits:
            raise entry_error("entry.flags_binding")
        if local_method not in _ZIP_ALLOWED_COMPRESSION:
            raise entry_error("entry.compression_method")
        if local_method != info.compress_type:
            raise entry_error("entry.compression_binding")
        if local_name != central_name:
            raise entry_error("entry.name_binding")


def validate_bootstrap_payload_zip(path: Path, label: str = "Windows bootstrap payload") -> None:
    """Fail closed over the ZIP container and every admitted payload entry.

    Diagnostics intentionally identify only the archive entry and violated rule.
    No content bytes or matched values are ever interpolated into an exception.
    """

    try:
        archive_size = path.stat().st_size
    except OSError as exc:
        raise _bootstrap_zip_error(label, "archive.readable") from exc
    if archive_size <= 0 or archive_size > BOOTSTRAP_ZIP_MAX_ARCHIVE_BYTES:
        raise _bootstrap_zip_error(label, "archive.size")

    try:
        with zipfile.ZipFile(path, "r") as archive:
            entries = archive.infolist()
            if not entries or len(entries) > BOOTSTRAP_ZIP_MAX_ENTRIES:
                raise _bootstrap_zip_error(label, "archive.entry_count")
            _validate_bootstrap_zip_local_headers(
                archive,
                entries,
                label,
                archive_size,
            )

            exact_paths: set[str] = set()
            folded_paths: set[str] = set()
            total_uncompressed = 0
            total_compressed = 0
            for entry_ordinal, info in enumerate(entries, start=1):
                entry_name = info.orig_filename

                def entry_error(rule_id: str) -> BootstrapZipPolicyError:
                    return _bootstrap_zip_error(
                        label,
                        rule_id,
                        entry_ordinal=entry_ordinal,
                        entry_name=entry_name,
                    )

                normalized_path, path_is_directory = _normalize_bootstrap_zip_path(
                    entry_name,
                    label,
                    entry_ordinal,
                )
                collision_key = normalized_path
                portable_collision_key = _bootstrap_zip_collision_key(normalized_path)
                if collision_key in exact_paths:
                    raise entry_error("path.duplicate")
                if portable_collision_key in folded_paths:
                    raise entry_error("path.portable_collision")
                exact_paths.add(collision_key)
                folded_paths.add(portable_collision_key)

                if _has_sensitive_bootstrap_zip_name(normalized_path):
                    raise entry_error("name.sensitive")
                if info.flag_bits & 0x41:
                    raise entry_error("entry.encrypted")
                if info.compress_type not in _ZIP_ALLOWED_COMPRESSION:
                    raise entry_error("entry.compression_method")

                unix_mode = (info.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(unix_mode)
                if file_type == stat.S_IFLNK:
                    raise entry_error("entry.symlink")
                if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise entry_error("entry.regular_type")
                if path_is_directory != info.is_dir():
                    raise entry_error("entry.directory")

                if info.file_size < 0 or info.file_size > BOOTSTRAP_ZIP_MAX_ENTRY_BYTES:
                    raise entry_error("entry.decompressed_size")
                if info.compress_size < 0:
                    raise entry_error("entry.compressed_size")
                if info.file_size > 0 and info.compress_size == 0:
                    raise entry_error("entry.compression_ratio")
                if (
                    info.file_size > 0
                    and info.file_size
                    > info.compress_size * BOOTSTRAP_ZIP_MAX_COMPRESSION_RATIO
                ):
                    raise entry_error("entry.compression_ratio")

                total_uncompressed += info.file_size
                total_compressed += info.compress_size
                if total_uncompressed > BOOTSTRAP_ZIP_MAX_TOTAL_BYTES:
                    raise entry_error("archive.decompressed_size")
                if not path_is_directory:
                    _scan_bootstrap_zip_entry(
                        archive,
                        info,
                        normalized_path,
                        label,
                        entry_ordinal,
                        entry_name,
                    )

            if total_uncompressed <= 0:
                raise _bootstrap_zip_error(label, "archive.non_empty")
            if total_compressed <= 0 or (
                total_uncompressed
                > total_compressed * BOOTSTRAP_ZIP_MAX_COMPRESSION_RATIO
            ):
                raise _bootstrap_zip_error(label, "archive.compression_ratio")
    except BootstrapZipPolicyError:
        raise
    except (EOFError, NotImplementedError, OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        raise _bootstrap_zip_error(label, "archive.format") from exc


def parse_utc_timestamp(value: object, label: str) -> datetime:
    text = str(value or "").strip()
    if not text.endswith("Z"):
        raise ValueError(f"{label} must be a UTC RFC3339 timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{label} must be a valid UTC RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    return parsed.astimezone(UTC)


def validate_manifest_freshness(
    manifest: dict[str, Any],
    *,
    now: datetime | None = None,
    not_before: datetime | None = None,
) -> tuple[datetime, datetime]:
    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    generated_at = parse_utc_timestamp(manifest.get("generatedAt"), "manifest.generatedAt")
    expires_at = parse_utc_timestamp(manifest.get("expiresAt"), "manifest.expiresAt")
    lifetime = expires_at - generated_at
    if lifetime <= timedelta(0) or lifetime > MANIFEST_MAX_LIFETIME:
        raise ValueError("manifest freshness lifetime must be greater than zero and at most 24 hours")
    if generated_at > observed_now + FUTURE_CLOCK_SKEW:
        raise ValueError("manifest.generatedAt is too far in the future")
    if not_before is not None and generated_at < not_before.astimezone(UTC):
        raise ValueError("manifest.generatedAt precedes the governed build invocation")
    if expires_at <= observed_now:
        raise ValueError("Windows proof manifest is expired")
    return generated_at, expires_at


def _require_exact(payload: dict[str, Any], key: str, expected: Any, label: str) -> None:
    if payload.get(key) != expected:
        raise ValueError(f"{label}.{key} must be {expected!r}")


def _require_object(payload: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{label}.{key} must be an object")
    return value


def validate_governed_windows_evidence(
    *,
    version: str,
    installer_path: Path,
    provenance_path: Path,
    sbom_path: Path,
    now: datetime | None = None,
) -> GovernedWindowsEvidence:
    installer_sha256 = sha256_file(installer_path)
    installer_size = installer_path.stat().st_size
    sbom, sbom_bytes = load_unique_json(sbom_path, "Windows proof SBOM")
    sbom_sha256 = hashlib.sha256(sbom_bytes).hexdigest()
    provenance, provenance_bytes = load_unique_json(
        provenance_path,
        "Windows proof build provenance receipt",
    )
    provenance_sha256 = hashlib.sha256(provenance_bytes).hexdigest()
    invocation_id = f"{version}.avalonia.win-x64.installer"

    for key, expected in (
        ("contract_name", PROVENANCE_CONTRACT),
        ("receipt_kind", "invocation"),
        ("status", "pass"),
        ("builder_id", PROVENANCE_BUILDER_ID),
        ("build_type", PROVENANCE_BUILD_TYPE),
        ("invocation_id", invocation_id),
        ("release_version", version),
    ):
        _require_exact(provenance, key, expected, "build provenance")
    if provenance.get("failures") != []:
        raise ValueError("build provenance.failures must be an empty array")
    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    generated_at = parse_utc_timestamp(
        provenance.get("generated_at_utc"),
        "build provenance.generated_at_utc",
    )
    if generated_at > observed_now + FUTURE_CLOCK_SKEW:
        raise ValueError("build provenance.generated_at_utc is too far in the future")
    if observed_now - generated_at > PROVENANCE_MAX_AGE:
        raise ValueError("Windows proof build provenance is stale")
    build_started_at = parse_utc_timestamp(
        provenance.get("build_started_at_utc"),
        "build provenance.build_started_at_utc",
    )
    if generated_at < build_started_at:
        raise ValueError("build provenance was generated before its build invocation began")

    authority_nonce = str(provenance.get("authority_nonce") or "").lower()
    if not SHA256_PATTERN.fullmatch(authority_nonce):
        raise ValueError("build provenance.authority_nonce is invalid")
    invocation = _require_object(provenance, "invocation", "build provenance")
    for key, expected in (
        ("state_contract_name", PROVENANCE_STATE_CONTRACT),
        ("subject_declared_before_build", True),
        ("source_identity_stable", True),
        ("public_projection", "portable_path_references.v1"),
    ):
        _require_exact(invocation, key, expected, "build provenance.invocation")
    state = _require_object(invocation, "state", "build provenance.invocation")
    state_sha256 = hashlib.sha256(
        json.dumps(state, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    _require_exact(invocation, "state_sha256", state_sha256, "build provenance.invocation")
    for key, expected in (
        ("state_contract_name", PROVENANCE_STATE_CONTRACT),
        ("builder_id", PROVENANCE_BUILDER_ID),
        ("build_type", PROVENANCE_BUILD_TYPE),
        ("invocation_id", invocation_id),
        ("release_version", version),
        ("authority_nonce", authority_nonce),
        ("started_at_utc", provenance.get("build_started_at_utc")),
    ):
        _require_exact(state, key, expected, "build provenance invocation state")
    source = _require_object(state, "source", "build provenance invocation state")
    for key, expected in (
        ("repository", PROVENANCE_SOURCE_REPOSITORY),
        ("tracked_worktree_dirty", False),
        ("worktree_dirty", False),
        ("untracked_build_inputs_included", True),
    ):
        _require_exact(source, key, expected, "build provenance invocation source")
    for key in ("commit", "tree"):
        if not REVISION_PATTERN.fullmatch(str(source.get(key) or "")):
            raise ValueError(f"build provenance invocation source.{key} is invalid")
    started_epoch_ns = state.get("started_epoch_ns")
    if isinstance(started_epoch_ns, bool) or not isinstance(started_epoch_ns, int) or started_epoch_ns <= 0:
        raise ValueError("build provenance invocation state.started_epoch_ns is invalid")

    source_materials = state.get("source_materials")
    if not isinstance(source_materials, list):
        raise ValueError("build provenance invocation state.source_materials must be an array")
    material_names: set[str] = set()
    for material in source_materials:
        if not isinstance(material, dict):
            raise ValueError("build provenance source material rows must be objects")
        repository = str(material.get("repository") or "")
        if repository in material_names:
            raise ValueError("build provenance source materials contain a duplicate repository")
        material_names.add(repository)
        for key in ("commit", "tree"):
            if not REVISION_PATTERN.fullmatch(str(material.get(key) or "")):
                raise ValueError(f"build provenance source material {repository}.{key} is invalid")
        for key in ("tracked_worktree_dirty", "worktree_dirty"):
            _require_exact(material, key, False, f"build provenance source material {repository}")
    if material_names != PROVENANCE_SOURCE_MATERIALS:
        raise ValueError("build provenance source materials do not match the exact release repository set")

    build_inputs = state.get("build_inputs")
    if not isinstance(build_inputs, list):
        raise ValueError("build provenance invocation state.build_inputs must be an array")
    input_labels: set[str] = set()
    for build_input in build_inputs:
        if not isinstance(build_input, dict):
            raise ValueError("build provenance build input rows must be objects")
        label = str(build_input.get("label") or "")
        if label in input_labels:
            raise ValueError("build provenance build inputs contain a duplicate label")
        input_labels.add(label)
        if not SHA256_PATTERN.fullmatch(str(build_input.get("sha256") or "")):
            raise ValueError(f"build provenance build input {label}.sha256 is invalid")
    if input_labels != PROVENANCE_BUILD_INPUT_LABELS:
        raise ValueError("build provenance build inputs do not match the exact Windows recipe set")
    build_tools = _require_object(state, "build_tools", "build provenance invocation state")
    for key in ("provenance_generator_sha256", "supply_chain_verifier_sha256"):
        if not SHA256_PATTERN.fullmatch(str(build_tools.get(key) or "")):
            raise ValueError(f"build provenance build_tools.{key} is invalid")
    declaration = _require_object(
        state,
        "subject_declaration",
        "build provenance invocation state",
    )
    for key, expected in (
        ("artifact_id", PROVENANCE_ARTIFACT_ID),
        ("artifact_kind", PROVENANCE_ARTIFACT_KIND),
        ("artifact_name", installer_path.name),
        ("artifact_binding_type", "file"),
        ("target_id", PROVENANCE_TARGET_ID),
    ):
        _require_exact(declaration, key, expected, "build provenance subject declaration")
    _require_exact(
        declaration,
        "artifact_path",
        f"files/{installer_path.name}",
        "build provenance subject declaration",
    )
    prebuild = _require_object(declaration, "prebuild", "build provenance subject declaration")
    _require_exact(prebuild, "exists", False, "build provenance subject declaration.prebuild")
    state_sbom = _require_object(state, "sbom", "build provenance invocation state")
    _require_exact(state_sbom, "sha256", sbom_sha256, "build provenance invocation SBOM")
    _require_exact(state_sbom, "generator", SBOM_GENERATOR, "build provenance invocation SBOM")
    _require_exact(
        state_sbom,
        "path",
        f"proof/build-provenance/v1/sbom/{PROVENANCE_TARGET_ID}.cdx.json",
        "build provenance invocation SBOM",
    )

    subjects = provenance.get("subjects")
    if not isinstance(subjects, list) or len(subjects) != 1 or not isinstance(subjects[0], dict):
        raise ValueError("build provenance must contain exactly one subject")
    subject = subjects[0]
    for key, expected in (
        ("artifact_id", PROVENANCE_ARTIFACT_ID),
        ("artifact_kind", PROVENANCE_ARTIFACT_KIND),
        ("artifact_name", installer_path.name),
        ("artifact_sha256", installer_sha256),
        ("artifact_size_bytes", installer_size),
        ("release_version", version),
        ("target_id", PROVENANCE_TARGET_ID),
        ("source_repository", PROVENANCE_SOURCE_REPOSITORY),
        ("source_tracked_worktree_dirty", False),
        ("source_worktree_dirty", False),
        ("source_untracked_build_inputs_included", True),
        ("sbom_sha256", sbom_sha256),
        ("sbom_generator", SBOM_GENERATOR),
        ("invocation_id", invocation_id),
        ("authority_nonce", authority_nonce),
        ("produced_during_invocation", True),
    ):
        _require_exact(subject, key, expected, "build provenance subject")
    for key in ("source_commit", "source_tree"):
        if not REVISION_PATTERN.fullmatch(str(subject.get(key) or "")):
            raise ValueError(f"build provenance subject.{key} is invalid")
    if subject.get("source_commit") != source.get("commit") or subject.get("source_tree") != source.get("tree"):
        raise ValueError("build provenance subject source identity does not match its invocation state")
    artifact_built_mtime_ns = subject.get("artifact_built_mtime_ns")
    if (
        isinstance(artifact_built_mtime_ns, bool)
        or not isinstance(artifact_built_mtime_ns, int)
        or artifact_built_mtime_ns <= started_epoch_ns
    ):
        raise ValueError("build provenance subject was not produced during the declared invocation")

    for key, expected in (
        ("bomFormat", "CycloneDX"),
        ("specVersion", "1.5"),
        ("version", 1),
    ):
        _require_exact(sbom, key, expected, "SBOM")
    metadata = _require_object(sbom, "metadata", "SBOM")
    component = _require_object(metadata, "component", "SBOM.metadata")
    for key, expected in (
        ("type", "application"),
        ("name", PROVENANCE_TARGET_ID),
        ("version", version),
        ("bom-ref", f"urn:chummer:project:{PROVENANCE_TARGET_ID}"),
    ):
        _require_exact(component, key, expected, "SBOM.metadata.component")
    components = sbom.get("components")
    if not isinstance(components, list):
        raise ValueError("SBOM.components must be an array")
    dependencies = sbom.get("dependencies")
    if not isinstance(dependencies, list) or not any(
        isinstance(row, dict)
        and row.get("ref") == f"urn:chummer:project:{PROVENANCE_TARGET_ID}"
        and isinstance(row.get("dependsOn"), list)
        for row in dependencies
    ):
        raise ValueError("SBOM.dependencies must bind the root application component")

    return GovernedWindowsEvidence(
        invocation_id,
        provenance_sha256,
        sbom_sha256,
        build_started_at,
        generated_at,
    )
