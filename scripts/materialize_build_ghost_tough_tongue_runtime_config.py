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
import secrets
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


def _capture_owned_file(path: Path, label: str, maximum: int) -> bytes:
    if (
        not path.is_absolute()
        or Path(os.path.normpath(path)) != path
        or SAFE_ABSOLUTE_PATH.fullmatch(str(path)) is None
    ):
        raise ConfigError(f"{label}-path-invalid")
    try:
        linked = os.stat(path, follow_symlinks=False)
    except OSError as error:
        raise ConfigError(f"{label}-unavailable") from error
    if (
        stat.S_ISLNK(linked.st_mode)
        or not stat.S_ISREG(linked.st_mode)
        or linked.st_uid != os.geteuid()
        or linked.st_nlink != 1
        or stat.S_IMODE(linked.st_mode) not in {0o400, 0o600}
        or not 1 <= linked.st_size <= maximum
    ):
        raise ConfigError(f"{label}-authority-invalid")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise ConfigError(f"{label}-unavailable") from error
    try:
        before = os.fstat(descriptor)
        if _identity(before) != _identity(linked):
            raise ConfigError(f"{label}-changed")
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
    try:
        rebound = os.stat(path, follow_symlinks=False)
    except OSError as error:
        raise ConfigError(f"{label}-changed") from error
    if _identity(before) != _identity(after) or _identity(after) != _identity(rebound):
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


def _private_output_parent(path: Path) -> os.stat_result:
    if (
        not path.is_absolute()
        or Path(os.path.normpath(path)) != path
        or SAFE_ABSOLUTE_PATH.fullmatch(str(path)) is None
    ):
        raise ConfigError("output-path-invalid")
    try:
        parent = os.stat(path.parent, follow_symlinks=False)
    except OSError as error:
        raise ConfigError("output-parent-unavailable") from error
    if (
        stat.S_ISLNK(parent.st_mode)
        or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.geteuid()
        or stat.S_IMODE(parent.st_mode) & 0o077
    ):
        raise ConfigError("output-parent-authority-invalid")
    return parent


def _publish_new(path: Path, raw: bytes, mode: int) -> None:
    _private_output_parent(path)
    parent_fd = os.open(
        path.parent,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    temporary_name = f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    linked = False
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=parent_fd,
        )
        try:
            os.fchmod(descriptor, mode)
            offset = 0
            while offset < len(raw):
                written = os.write(descriptor, raw[offset:])
                if written <= 0:
                    raise ConfigError("output-short-write")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.link(
            temporary_name,
            path.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
        linked = True
        os.fsync(parent_fd)
        os.unlink(temporary_name, dir_fd=parent_fd)
        linked = False
        os.fsync(parent_fd)
    finally:
        if not linked:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except OSError:
                pass
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
    for path in output_paths:
        _private_output_parent(path)
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
    receipt["evidenceDigest"] = _digest(_canonical({
        key: value for key, value in receipt.items() if key != "evidenceDigest"
    }))
    receipt_raw = json.dumps(
        receipt, indent=2, ensure_ascii=True, sort_keys=True
    ).encode("utf-8") + b"\n"
    _publish_new(contract_snapshot_path, contract_raw, 0o400)
    _publish_new(receipt_path, receipt_raw, 0o600)
    # The credential-bearing file is the commit marker and is published last.
    # A killed process can leave harmless contract/receipt evidence, but never a
    # usable env file without the already-durable matching receipt.
    _publish_new(environment_path, environment_raw, 0o600)
    return receipt


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize a complete read-only Tough Tongue runtime config.",
        allow_abbrev=False,
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-env", type=Path, required=True)
    parser.add_argument("--output-contract", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
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
