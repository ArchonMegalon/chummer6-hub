#!/usr/bin/env python3
"""Materialize one complete, secret-safe Tough Tongue read-only runtime config.

This tool performs local validation only. It never contacts Tough Tongue,
enables a provider gate, creates a provider resource, or claims live readback.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Mapping


CONFIG_SCHEMA = "chummer.build_ghost.tough_tongue.runtime_config.v1"
RECEIPT_SCHEMA = "chummer.build_ghost.tough_tongue.runtime_config_receipt.v1"
CONTRACT_SCHEMA = "ea.tough_tongue.read_only_binding_contract.v1"
STATUS = "ready-for-read-only-probe"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
PROVIDER_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+~-]{0,511}$")
CREDENTIAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~+/@:=-]{15,511}$")
SAFE_ABSOLUTE_PATH = re.compile(r"^/(?:[A-Za-z0-9._@:+~-]+/?)+$")
SAFE_SELECTOR = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*$")
SAFE_LOWER_VALUE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SAFE_ROUTE_PATH = re.compile(r"^[A-Za-z0-9._~/-]*(?:\{resource_ref\})?[A-Za-z0-9._~/-]*$")
VERIFIED_AT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
MAX_CONFIG_BYTES = 256 * 1024
MAX_ENVIRONMENT_BYTES = 256 * 1024
MAX_CONTRACT_BYTES = 512 * 1024
CANDIDATE_KINDS = ("agent", "voice", "function", "scenario", "live_avatar")
ROUTE_NAMES = ("account", "agent", "voice", "function", "scenario")
RESOURCE_SELECTORS = {"resource_ref", "account_ref", "organization_ref"}
ACCOUNT_SELECTORS = {
    "account_ref", "organization_ref", "plan_name", "live_avatar_entitled",
}
SCENARIO_SELECTORS = RESOURCE_SELECTORS | {
    "live_avatar_ref", "live_avatar_provider", "voice_ref", "function_refs",
}
ENVIRONMENT_NAMES = {
    "agent": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID",
    "voice": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID",
    "function": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_FUNCTION_ID",
    "scenario": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_SCENARIO_ID",
    "live_avatar": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_LIVE_AVATAR_ID",
}


class ConfigError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _digest(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_nlink,
    )


def _validated_absolute_path(path: Path, label: str) -> tuple[str, ...]:
    if (
        not path.is_absolute()
        or Path(os.path.normpath(path)) != path
        or SAFE_ABSOLUTE_PATH.fullmatch(str(path)) is None
    ):
        raise ConfigError(f"{label}-path-invalid")
    parts = path.parts[1:]
    if not parts:
        raise ConfigError(f"{label}-path-invalid")
    return parts


def _open_directory_chain(path: Path, label: str) -> int:
    """Open an absolute directory without following any path-component link."""

    parts = () if path == Path("/") else _validated_absolute_path(path, label)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open("/", flags)
    except OSError as error:
        raise ConfigError(f"{label}-unavailable") from error
    try:
        for part in parts:
            try:
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
            except OSError as error:
                raise ConfigError(f"{label}-authority-invalid") from error
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_owned_file(path: Path, label: str, maximum: int) -> tuple[int, os.stat_result]:
    parts = _validated_absolute_path(path, label)
    parent = Path("/").joinpath(*parts[:-1]) if len(parts) > 1 else Path("/")
    parent_fd = _open_directory_chain(parent, label)
    try:
        try:
            linked = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(linked.st_mode):
                raise ConfigError(f"{label}-authority-invalid")
            descriptor = os.open(
                parts[-1],
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
        except ConfigError:
            raise
        except OSError as error:
            raise ConfigError(f"{label}-unavailable") from error
        try:
            opened = os.fstat(descriptor)
            if (
                _identity(opened) != _identity(linked)
                or stat.S_ISLNK(opened.st_mode)
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or opened.st_nlink != 1
                or stat.S_IMODE(opened.st_mode) not in {0o400, 0o600}
                or not 1 <= opened.st_size <= maximum
            ):
                raise ConfigError(f"{label}-authority-invalid")
            return descriptor, opened
        except BaseException:
            os.close(descriptor)
            raise
    finally:
        os.close(parent_fd)


def _capture_owned_file(path: Path, label: str, maximum: int) -> bytes:
    descriptor, before = _open_owned_file(path, label, maximum)
    try:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise ConfigError(f"{label}-too-large")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if _identity(before) != _identity(after):
        raise ConfigError(f"{label}-changed")
    return b"".join(chunks)


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ConfigError(f"{label}-duplicate-key")
            result[key] = value
        return result

    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigError(f"{label}-json-invalid") from error
    if not isinstance(payload, dict):
        raise ConfigError(f"{label}-not-object")
    return payload


def _candidate_digest(value: str) -> str:
    return _digest(value.encode("utf-8"))


def _validated_contract(payload: dict[str, Any], expected_digest: str) -> None:
    required = {
        "schema", "provider_key", "base_url", "source_type", "verified_at",
        "authority", "premium_plan_values", "live_avatar_providers", "routes",
    }
    if set(payload) != required:
        raise ConfigError("read-only-contract-schema-invalid")
    if (
        payload.get("schema") != CONTRACT_SCHEMA
        or payload.get("provider_key") != "tough_tongue"
        or payload.get("base_url") != "https://api.toughtongueai.com/api/public"
        or payload.get("source_type")
        not in {"provider_documentation", "captured_read_only_api"}
    ):
        raise ConfigError("read-only-contract-schema-invalid")
    verified_at = payload.get("verified_at")
    if not isinstance(verified_at, str) or VERIFIED_AT.fullmatch(verified_at) is None:
        raise ConfigError("read-only-contract-authority-invalid")
    try:
        dt.datetime.strptime(verified_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ConfigError("read-only-contract-authority-invalid") from error

    authority = payload.get("authority")
    if (
        not isinstance(authority, dict)
        or set(authority) != {"operator_verified", "source_ref_sha256"}
        or authority.get("operator_verified") is not True
        or not isinstance(authority.get("source_ref_sha256"), str)
        or SHA256.fullmatch(authority["source_ref_sha256"]) is None
    ):
        raise ConfigError("read-only-contract-authority-invalid")

    for field in ("premium_plan_values", "live_avatar_providers"):
        values = payload.get(field)
        if (
            not isinstance(values, list)
            or not values
            or any(
                not isinstance(value, str)
                or SAFE_LOWER_VALUE.fullmatch(value) is None
                for value in values
            )
            or len(set(values)) != len(values)
        ):
            raise ConfigError("read-only-contract-entitlements-invalid")

    routes = payload.get("routes")
    if not isinstance(routes, dict) or set(routes) != set(ROUTE_NAMES):
        raise ConfigError("read-only-contract-routes-invalid")
    expected_selectors = {
        "account": ACCOUNT_SELECTORS,
        "agent": RESOURCE_SELECTORS,
        "voice": RESOURCE_SELECTORS,
        "function": RESOURCE_SELECTORS,
        "scenario": SCENARIO_SELECTORS,
    }
    for name in ROUTE_NAMES:
        route = routes.get(name)
        if not isinstance(route, dict) or set(route) != {"method", "path", "selectors"}:
            raise ConfigError(f"read-only-contract-route-{name}-invalid")
        path = route.get("path")
        if (
            route.get("method") != "GET"
            or not isinstance(path, str)
            or SAFE_ROUTE_PATH.fullmatch(path) is None
            or path.startswith("/")
            or ".." in path.split("/")
            or path.count("{resource_ref}") != (0 if name == "account" else 1)
            or (name == "account" and ("{" in path or "}" in path))
            or (
                name != "account"
                and ("{" in path.replace("{resource_ref}", "") or "}" in path.replace("{resource_ref}", ""))
            )
        ):
            raise ConfigError(f"read-only-contract-route-{name}-invalid")
        selectors = route.get("selectors")
        if (
            not isinstance(selectors, dict)
            or set(selectors) != expected_selectors[name]
            or any(
                not isinstance(value, str)
                or SAFE_SELECTOR.fullmatch(value) is None
                for value in selectors.values()
            )
        ):
            raise ConfigError(f"read-only-contract-route-{name}-invalid")

    if _digest(_canonical(payload)) != expected_digest:
        raise ConfigError("read-only-contract-digest-mismatch")


def _validated_config(
    config_path: Path, contract_snapshot_path: Path
) -> tuple[dict[str, str], dict[str, Any], bytes]:
    payload = _json_object(
        _capture_owned_file(config_path, "operator-config", MAX_CONFIG_BYTES),
        "operator-config",
    )
    if set(payload) != {
        "schema", "account_slots", "preferred_account_ref", "candidate_refs",
        "read_only_contract",
    } or payload.get("schema") != CONFIG_SCHEMA:
        raise ConfigError("operator-config-schema-invalid")

    slots = payload.get("account_slots")
    if not isinstance(slots, list) or not 3 <= len(slots) <= 32:
        raise ConfigError("account-slots-invalid")
    account_refs: list[str] = []
    credentials: list[str] = []
    for slot in slots:
        if not isinstance(slot, dict) or set(slot) != {"account_ref", "api_key"}:
            raise ConfigError("account-slot-schema-invalid")
        account_ref = slot.get("account_ref")
        api_key = slot.get("api_key")
        if not isinstance(account_ref, str) or SHA256.fullmatch(account_ref) is None:
            raise ConfigError("account-ref-invalid")
        if not isinstance(api_key, str) or CREDENTIAL.fullmatch(api_key) is None:
            raise ConfigError("account-credential-invalid")
        account_refs.append(account_ref)
        credentials.append(api_key)
    if len(set(account_refs)) != len(account_refs):
        raise ConfigError("account-refs-not-distinct")
    if len(set(credentials)) != len(credentials):
        raise ConfigError("account-credentials-not-distinct")

    preferred = payload.get("preferred_account_ref")
    if not isinstance(preferred, str) or SHA256.fullmatch(preferred) is None:
        raise ConfigError("preferred-account-ref-invalid")
    if account_refs.count(preferred) != 1:
        raise ConfigError("preferred-account-ref-not-exactly-one")

    candidates = payload.get("candidate_refs")
    if not isinstance(candidates, dict) or set(candidates) != set(CANDIDATE_KINDS):
        raise ConfigError("candidate-refs-schema-invalid")
    candidate_digests: dict[str, str] = {}
    for kind in CANDIDATE_KINDS:
        value = candidates.get(kind)
        if (
            not isinstance(value, str)
            or value != value.strip()
            or PROVIDER_REF.fullmatch(value) is None
            or SHA256.fullmatch(value.lower()) is not None
        ):
            raise ConfigError(f"candidate-{kind.replace('_', '-')}-ref-invalid")
        candidate_digests[kind] = _candidate_digest(value)

    contract = payload.get("read_only_contract")
    if not isinstance(contract, dict) or set(contract) != {"path", "digest"}:
        raise ConfigError("read-only-contract-config-invalid")
    path_value = contract.get("path")
    contract_digest = contract.get("digest")
    if (
        not isinstance(path_value, str)
        or SAFE_ABSOLUTE_PATH.fullmatch(path_value) is None
    ):
        raise ConfigError("read-only-contract-path-invalid")
    contract_path = Path(path_value)
    if not isinstance(contract_digest, str) or SHA256.fullmatch(contract_digest) is None:
        raise ConfigError("read-only-contract-digest-invalid")
    contract_payload = _json_object(
        _capture_owned_file(contract_path, "read-only-contract", MAX_CONTRACT_BYTES),
        "read-only-contract",
    )
    _validated_contract(contract_payload, contract_digest)

    environment = {
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS": ";".join(credentials),
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS": ";".join(account_refs),
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF": preferred,
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_FILE": str(
            contract_snapshot_path
        ),
        "EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST": contract_digest,
    }
    environment.update(
        {ENVIRONMENT_NAMES[kind]: candidates[kind] for kind in CANDIDATE_KINDS}
    )
    expectation_digest = _digest(
        _canonical(
            {
                "preferred_account_ref": preferred,
                "candidate_refs": dict(sorted(candidate_digests.items())),
            }
        )
    )
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "generatedAt": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "status": STATUS,
        "providerKey": "tough_tongue",
        "accountRefCount": len(account_refs),
        "accountRefsDigest": _digest(
            _canonical({"account_refs": sorted(account_refs)})
        ),
        "preferredAccountRef": preferred,
        "candidateRefDigests": dict(sorted(candidate_digests.items())),
        "expectationDigest": expectation_digest,
        "readOnlyContractDigest": contract_digest,
        "providerReadbackVerified": False,
        "providerActivationAuthorized": False,
        "providerMutationPerformed": False,
        "rawCredentialsInReceipt": False,
        "rawCandidateRefsInReceipt": False,
        "environmentContainsCredentials": True,
        "environmentMode": "0600",
        "nextAction": "run-fresh-ea-live-ops-read-only-binding-probe",
        "evidenceDigestContract": "sha256-canonical-json-without-evidenceDigest",
    }
    receipt["evidenceDigest"] = _digest(_canonical(receipt))
    return environment, receipt, _canonical(contract_payload) + b"\n"


def _open_private_output_parent(path: Path) -> int:
    _validated_absolute_path(path, "output")
    try:
        descriptor = _open_directory_chain(path.parent, "output-parent")
    except ConfigError as error:
        if str(error) == "output-parent-path-invalid":
            raise ConfigError("output-path-invalid") from error
        raise
    parent = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.geteuid()
        or stat.S_IMODE(parent.st_mode) & 0o077
    ):
        os.close(descriptor)
        raise ConfigError("output-parent-authority-invalid")
    return descriptor


def _assert_output_parent_binding(path: Path, expected_fd: int) -> None:
    rebound_fd = _open_private_output_parent(path)
    try:
        expected = os.fstat(expected_fd)
        rebound = os.fstat(rebound_fd)
        if (expected.st_dev, expected.st_ino) != (rebound.st_dev, rebound.st_ino):
            raise ConfigError("output-parent-changed")
    finally:
        os.close(rebound_fd)


def _publish_new(parent_fd: int, name: str, raw: bytes, mode: int) -> None:
    if not name or "/" in name or name in {".", ".."}:
        raise ConfigError("output-name-invalid")
    temporary_flag = getattr(os, "O_TMPFILE", 0)
    if not temporary_flag:
        raise ConfigError("output-atomic-publication-unavailable")
    try:
        descriptor = os.open(
            ".",
            os.O_WRONLY
            | temporary_flag
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=parent_fd,
        )
    except OSError as error:
        raise ConfigError("output-atomic-publication-unavailable") from error
    try:
        os.fchmod(descriptor, mode)
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise ConfigError("output-short-write")
            offset += written
        os.fsync(descriptor)
        _link_staged_file(parent_fd, descriptor, name)
        os.fsync(parent_fd)
    finally:
        os.close(descriptor)


def _link_staged_file(parent_fd: int, descriptor: int, name: str) -> None:
    """Atomically give an unnamed staged inode one non-replacing output name."""

    os.link(
        f"/proc/self/fd/{descriptor}",
        name,
        dst_dir_fd=parent_fd,
        follow_symlinks=True,
    )


def destroy_environment(
    path: Path,
    *,
    expected_parent_device: int,
    expected_parent_inode: int,
    expected_environment_digest: str | None = None,
) -> bool:
    """Zero and unlink one owned runtime env without following path links."""

    if (
        expected_parent_device < 0
        or expected_parent_inode <= 0
    ):
        raise ConfigError("environment-destroy-binding-invalid")
    if (
        expected_environment_digest is not None
        and (
            not isinstance(expected_environment_digest, str)
            or SHA256.fullmatch(expected_environment_digest) is None
        )
    ):
        raise ConfigError("environment-destroy-binding-invalid")

    parts = _validated_absolute_path(path, "environment-destroy")
    parent = Path("/").joinpath(*parts[:-1]) if len(parts) > 1 else Path("/")
    parent_fd = _open_directory_chain(parent, "environment-destroy-parent")
    descriptor = -1
    try:
        parent_metadata = os.fstat(parent_fd)
        if (
            parent_metadata.st_dev != expected_parent_device
            or parent_metadata.st_ino != expected_parent_inode
        ):
            raise ConfigError("environment-destroy-parent-changed")
        try:
            linked = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(linked.st_mode):
            raise ConfigError("environment-destroy-authority-invalid")
        try:
            descriptor = os.open(
                parts[-1],
                os.O_RDWR
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
        except OSError as error:
            raise ConfigError("environment-destroy-unavailable") from error
        opened = os.fstat(descriptor)
        if (
            _identity(opened) != _identity(linked)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != 0o600
            or not 0 <= opened.st_size <= MAX_ENVIRONMENT_BYTES
        ):
            raise ConfigError("environment-destroy-authority-invalid")
        if expected_environment_digest is not None:
            hasher = hashlib.sha256()
            os.lseek(descriptor, 0, os.SEEK_SET)
            while True:
                chunk = os.read(descriptor, 64 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
            if f"sha256:{hasher.hexdigest()}" != expected_environment_digest:
                raise ConfigError("environment-destroy-digest-mismatch")
        remaining = opened.st_size
        os.lseek(descriptor, 0, os.SEEK_SET)
        zeroes = b"\0" * min(64 * 1024, max(1, remaining))
        while remaining:
            written = os.write(descriptor, zeroes[: min(len(zeroes), remaining)])
            if written <= 0:
                raise ConfigError("environment-destroy-short-write")
            remaining -= written
        os.fsync(descriptor)
        os.ftruncate(descriptor, 0)
        os.fsync(descriptor)
        rebound = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (rebound.st_dev, rebound.st_ino):
            raise ConfigError("environment-destroy-changed")
        os.unlink(parts[-1], dir_fd=parent_fd)
        os.fsync(parent_fd)
        return True
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_fd)


def materialize(
    config_path: Path,
    environment_path: Path,
    contract_snapshot_path: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    output_paths = (environment_path, contract_snapshot_path, receipt_path)
    if len(set(output_paths)) != len(output_paths):
        raise ConfigError("output-paths-not-distinct")
    if len({path.parent for path in output_paths}) != 1:
        raise ConfigError("output-paths-not-same-private-directory")
    environment, receipt, contract_raw = _validated_config(
        config_path, contract_snapshot_path
    )
    environment_raw = (
        "".join(f"{name}={value}\n" for name, value in sorted(environment.items()))
    ).encode("utf-8")
    receipt["environmentFileDigest"] = _digest(environment_raw)
    receipt["readOnlyContractFileDigest"] = _digest(contract_raw)
    receipt["contractSnapshotMode"] = "0400"
    receipt["publicationOrder"] = ["contract-snapshot", "receipt", "environment"]
    parent_fd = _open_private_output_parent(environment_path)
    try:
        parent_metadata = os.fstat(parent_fd)
        receipt["outputDirectoryDevice"] = parent_metadata.st_dev
        receipt["outputDirectoryInode"] = parent_metadata.st_ino
        receipt["evidenceDigest"] = _digest(_canonical({
            key: value for key, value in receipt.items() if key != "evidenceDigest"
        }))
        receipt_raw = json.dumps(
            receipt, indent=2, ensure_ascii=True, sort_keys=True
        ).encode("utf-8") + b"\n"
        _assert_output_parent_binding(contract_snapshot_path, parent_fd)
        _publish_new(parent_fd, contract_snapshot_path.name, contract_raw, 0o400)
        _assert_output_parent_binding(receipt_path, parent_fd)
        _publish_new(parent_fd, receipt_path.name, receipt_raw, 0o600)
        # The credential-bearing file is the commit marker and is published last.
        # A killed process can leave harmless contract/receipt evidence, but never a
        # usable env file without the already-durable matching receipt.
        _assert_output_parent_binding(environment_path, parent_fd)
        _publish_new(parent_fd, environment_path.name, environment_raw, 0o600)
        _assert_output_parent_binding(environment_path, parent_fd)
    finally:
        os.close(parent_fd)
    return receipt


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize a complete read-only Tough Tongue runtime config.",
        allow_abbrev=False,
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-env", type=Path)
    parser.add_argument("--output-contract", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--destroy-environment", type=Path)
    parser.add_argument("--expected-parent-device", type=int)
    parser.add_argument("--expected-parent-inode", type=int)
    parser.add_argument("--expected-environment-digest")
    args = parser.parse_args()
    materialize_values = (
        args.config, args.output_env, args.output_contract, args.receipt
    )
    if args.destroy_environment is not None:
        if any(value is not None for value in materialize_values):
            parser.error("--destroy-environment cannot be combined with materialization")
        if args.expected_parent_device is None or args.expected_parent_inode is None:
            parser.error(
                "--destroy-environment requires --expected-parent-device "
                "and --expected-parent-inode"
            )
    elif any(value is None for value in materialize_values):
        parser.error(
            "--config, --output-env, --output-contract, and --receipt are required"
        )
    elif any(
        value is not None
        for value in (
            args.expected_parent_device,
            args.expected_parent_inode,
            args.expected_environment_digest,
        )
    ):
        parser.error("expected cleanup bindings require --destroy-environment")
    return args


def main() -> int:
    args = _arguments()
    try:
        if args.destroy_environment is not None:
            removed = destroy_environment(
                args.destroy_environment,
                expected_parent_device=args.expected_parent_device,
                expected_parent_inode=args.expected_parent_inode,
                expected_environment_digest=args.expected_environment_digest,
            )
            print(f"tough_tongue_runtime_environment_destroyed={str(removed).lower()}")
            return 0
        receipt = materialize(
            args.config, args.output_env, args.output_contract, args.receipt
        )
    except (OSError, ConfigError) as error:
        stage = str(error) if isinstance(error, ConfigError) else "io-failed"
        print(f"tough_tongue_runtime_config=failed stage={stage}", file=sys.stderr)
        return 1
    print(
        "tough_tongue_runtime_config=materialized "
        f"status={receipt['status']} evidence_digest={receipt['evidenceDigest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
