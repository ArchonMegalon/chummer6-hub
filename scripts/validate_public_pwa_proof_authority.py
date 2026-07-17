#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any


CONTRACT_NAME = "chummer.public-pwa-proof-authority.v1"
RECEIPT_CONTRACT_NAME = "chummer.public-pwa-proof-authority-receipt.v1"
RECEIPT_CONTRACT_VERSION = 1
POLICY_ID = "chummer.public-play-pwa-mirror.v1"
MIRROR_CONTRACT = "play-install-mirror-v5"
INVENTORY_CONTRACT = "play-install-mirror-required-inventory-v2"
GENERATOR_CONTRACT = "play-root-worker-projection-generator-v1"
PROJECTION_CONTRACT = "play-root-worker-public-edge-projection-v2"
EXPECTED_ASSET_COUNT = 12
EXPECTED_DEPENDENCY_COUNT = 4
EXPECTED_PATHS = {
    "verifier": "scripts/verify_public_pwa_static_assets.py",
    "generator": "scripts/generate_public_play_worker_projection.py",
    "inventory": "Chummer.Run.Api/play-pwa-required-inventory.json",
}
MAX_AUTHORITY_BYTES = 64 * 1024
MAX_IDENTITY_BYTES = 2 * 1024 * 1024
MAX_CONTRACT_BYTES = 2 * 1024 * 1024
MAX_PROJECTED_ASSET_BYTES = 16 * 1024 * 1024
EXPECTED_ASSET_POLICY = (
    ("src/Chummer.Play.Web/wwwroot/mobile-install-shell.js", "wwwroot/mobile-install-shell.js", "exact", "install_shell", "application/javascript", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/mobile.css", "wwwroot/mobile.css", "exact", "install_styles", "text/css", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/manifest.webmanifest", "wwwroot/manifest.play.webmanifest", "exact", "base_manifest", "application/manifest+json", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/manifest.player.webmanifest", "wwwroot/manifest.player.webmanifest", "exact", "player_manifest", "application/manifest+json", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/manifest.gm.webmanifest", "wwwroot/manifest.gm.webmanifest", "exact", "gm_manifest", "application/manifest+json", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/manifest.observer.webmanifest", "wwwroot/manifest.observer.webmanifest", "exact", "observer_manifest", "application/manifest+json", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/icons/icon-192.png", "wwwroot/icons/icon-192.png", "exact", "icon_192_png", "image/png", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/icons/icon-512.png", "wwwroot/icons/icon-512.png", "exact", "icon_512_png", "image/png", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/icons/icon-192.svg", "wwwroot/icons/icon-192.svg", "exact", "icon_192_svg", "image/svg+xml", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/icons/icon-512.svg", "wwwroot/icons/icon-512.svg", "exact", "icon_512_svg", "image/svg+xml", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/mobile/service-worker.js", "wwwroot/mobile/service-worker.js", "exact", "scoped_worker", "application/javascript", "no-cache, no-store, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/service-worker.js", "wwwroot/service-worker.js", "transform", "root_worker", "application/javascript", "no-cache, no-store, must-revalidate"),
)
EXPECTED_DEPENDENCY_POLICY = (
    ("scripts/generate_public_play_worker_projection.py", "python", "generator_script", "text/x-python"),
    ("Chummer.Run.Api/play-worker-projection.json", "json", "projection_config", "application/json"),
    ("Chummer.Run.Api/service-worker.public-edge.template.js", "template", "projection_template", "application/javascript"),
    ("Chummer.Run.Api/play-pwa-required-inventory.json", "json", "required_inventory", "application/json"),
)
EXPECTED_PROJECTION_BINDINGS = {
    "source": "../chummer-play/src/Chummer.Play.Web/wwwroot/service-worker.js",
    "template": "Chummer.Run.Api/service-worker.public-edge.template.js",
    "requiredInventory": "Chummer.Run.Api/play-pwa-required-inventory.json",
    "projection": "Chummer.Run.Api/wwwroot/service-worker.js",
    "mirrorContract": "Chummer.Run.Api/play-pwa-mirrors.json",
}
EXPECTED_SOURCE_MARKERS = (
    'const CACHE_VERSION = "v21";',
    'const CACHE_CONTRACT = "play-source-v2";',
    '"/mobile-install-shell.js"',
    '"/manifest.webmanifest"',
    '"/manifest.observer.webmanifest"',
    "event.waitUntil(precacheCriticalShell());",
)
EXPECTED_FORBIDDEN_SOURCE_MARKERS = (
    "self.skipWaiting()",
    "self.clients.claim()",
)
EXPECTED_PROJECTION_MARKERS = (
    "Deterministic public-edge projection template",
    'const CACHE_VERSION = "v19";',
    'const CACHE_CONTRACT = "run-api-projection-v2";',
    "const CRITICAL_SHELL_ASSETS = [",
    '"/manifest.play.webmanifest"',
    "play_public_route_network_unavailable",
    "event.waitUntil(precacheCriticalShell());",
)
EXPECTED_FORBIDDEN_PROJECTION_MARKERS = (
    "self.skipWaiting()",
    "self.clients.claim()",
    '"/mobile-turn-companion.js"',
    'const CACHE_CONTRACT = "play-source-v2";',
    '"/manifest.webmanifest"',
)


def bounded_read_with_identity(
    path: Path,
    *,
    limit: int,
    label: str,
) -> tuple[bytes, dict[str, int]]:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"{label} is not a regular file")
        if before.st_size > limit:
            raise RuntimeError(f"{label} exceeds its size limit")
        chunks: list[bytes] = []
        byte_count = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - byte_count))
            if not chunk:
                break
            chunks.append(chunk)
            byte_count += len(chunk)
            if byte_count > limit:
                raise RuntimeError(f"{label} exceeds its size limit")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_before != identity_after or byte_count != before.st_size:
        raise RuntimeError(f"{label} changed while it was read")
    return b"".join(chunks), {
        "device": after.st_dev,
        "inode": after.st_ino,
        "size": after.st_size,
        "modifiedTimeNanoseconds": after.st_mtime_ns,
        "changedTimeNanoseconds": after.st_ctime_ns,
    }


def bounded_read(path: Path, *, limit: int, label: str) -> bytes:
    payload, _ = bounded_read_with_identity(path, limit=limit, label=label)
    return payload


def strict_json_object(payload: bytes, *, label: str = "authority") -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field {key!r}")
            result[key] = value
        return result

    try:
        parsed = json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{label} must be a JSON object")
    canonical = (json.dumps(parsed, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if canonical != payload:
        raise RuntimeError(f"{label} is not canonical UTF-8 JSON")
    return parsed


def require_exact_fields(
    value: dict[str, Any],
    expected: set[str],
    *,
    label: str,
) -> None:
    if set(value) != expected:
        raise RuntimeError(f"{label} fields drifted from the closed contract")


def require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise RuntimeError(f"{label} is not a lowercase SHA-256 digest")
    return value


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_inventory_contract(inventory: dict[str, Any]) -> None:
    require_exact_fields(
        inventory,
        {"contract", "policyId", "sourceRepository", "assets", "generatorDependencies"},
        label="required inventory",
    )
    fixed = {
        "contract": INVENTORY_CONTRACT,
        "policyId": POLICY_ID,
        "sourceRepository": "../chummer-play",
    }
    for field, expected in fixed.items():
        if inventory.get(field) != expected:
            raise RuntimeError(f"required inventory {field} drifted")

    assets = inventory.get("assets")
    if not isinstance(assets, list) or len(assets) != EXPECTED_ASSET_COUNT:
        raise RuntimeError("required inventory must declare exactly 12 ordered assets")
    asset_fields = {"source", "projection", "kind", "role", "contentType", "cacheControl"}
    actual_assets: list[tuple[str, str, str, str, str, str]] = []
    sources: set[str] = set()
    projections: set[str] = set()
    roles: set[str] = set()
    for index, row in enumerate(assets):
        if not isinstance(row, dict):
            raise RuntimeError(f"required inventory asset row {index} must be an object")
        require_exact_fields(row, asset_fields, label=f"required inventory asset row {index}")
        actual = tuple(row[field] for field in (
            "source", "projection", "kind", "role", "contentType", "cacheControl"
        ))
        if not all(isinstance(value, str) for value in actual):
            raise RuntimeError(f"required inventory asset row {index} must contain strings")
        source, projection, _, role, _, _ = actual
        if source in sources or projection in projections or role in roles:
            raise RuntimeError("required inventory contains duplicate asset identity")
        sources.add(source)
        projections.add(projection)
        roles.add(role)
        actual_assets.append(actual)  # type: ignore[arg-type]
    if tuple(actual_assets) != EXPECTED_ASSET_POLICY:
        raise RuntimeError("required inventory ordered asset policy drifted")

    dependencies = inventory.get("generatorDependencies")
    if not isinstance(dependencies, list) or len(dependencies) != EXPECTED_DEPENDENCY_COUNT:
        raise RuntimeError("required inventory must declare exactly four ordered dependencies")
    dependency_fields = {"path", "kind", "role", "contentType"}
    actual_dependencies: list[tuple[str, str, str, str]] = []
    paths: set[str] = set()
    dependency_roles: set[str] = set()
    for index, row in enumerate(dependencies):
        if not isinstance(row, dict):
            raise RuntimeError(f"required inventory dependency row {index} must be an object")
        require_exact_fields(
            row,
            dependency_fields,
            label=f"required inventory dependency row {index}",
        )
        actual = tuple(row[field] for field in ("path", "kind", "role", "contentType"))
        if not all(isinstance(value, str) for value in actual):
            raise RuntimeError(f"required inventory dependency row {index} must contain strings")
        path, _, role, _ = actual
        if path in paths or role in dependency_roles:
            raise RuntimeError("required inventory contains duplicate dependency identity")
        paths.add(path)
        dependency_roles.add(role)
        actual_dependencies.append(actual)  # type: ignore[arg-type]
    if tuple(actual_dependencies) != EXPECTED_DEPENDENCY_POLICY:
        raise RuntimeError("required inventory ordered dependency policy drifted")


def validate_projection_contract(
    projection: dict[str, Any],
    *,
    inventory_sha256: str,
    template_sha256: str,
) -> None:
    require_exact_fields(
        projection,
        {
            "contract",
            "source",
            "sourceSha256",
            "template",
            "templateSha256",
            "requiredInventory",
            "requiredInventorySha256",
            "projection",
            "mirrorContract",
            "requiredSourceMarkers",
            "forbiddenSourceMarkers",
            "requiredProjectionMarkers",
            "forbiddenProjectionMarkers",
        },
        label="worker projection",
    )
    if projection.get("contract") != PROJECTION_CONTRACT:
        raise RuntimeError("worker projection contract drifted")
    for field, expected in EXPECTED_PROJECTION_BINDINGS.items():
        if projection.get(field) != expected:
            raise RuntimeError(f"worker projection {field} drifted")
    require_sha256(projection.get("sourceSha256"), label="worker projection sourceSha256")
    if require_sha256(
        projection.get("templateSha256"),
        label="worker projection templateSha256",
    ) != template_sha256:
        raise RuntimeError("worker projection template digest binding drifted")
    if require_sha256(
        projection.get("requiredInventorySha256"),
        label="worker projection requiredInventorySha256",
    ) != inventory_sha256:
        raise RuntimeError("worker projection inventory digest binding drifted")
    marker_contracts = {
        "requiredSourceMarkers": EXPECTED_SOURCE_MARKERS,
        "forbiddenSourceMarkers": EXPECTED_FORBIDDEN_SOURCE_MARKERS,
        "requiredProjectionMarkers": EXPECTED_PROJECTION_MARKERS,
        "forbiddenProjectionMarkers": EXPECTED_FORBIDDEN_PROJECTION_MARKERS,
    }
    for field, expected in marker_contracts.items():
        value = projection.get(field)
        if not isinstance(value, list) or tuple(value) != expected:
            raise RuntimeError(f"worker projection {field} drifted from the ordered contract")


def validate_mirror_contract(
    mirror: dict[str, Any],
    *,
    mirror_path: Path,
    inventory: dict[str, Any],
    inventory_sha256: str,
    projection: dict[str, Any],
    projection_sha256: str,
    template_sha256: str,
    generator_sha256: str,
) -> None:
    require_exact_fields(
        mirror,
        {
            "contract",
            "inventoryContract",
            "policyId",
            "assetPolicyCount",
            "dependencyPolicyCount",
            "inventoryPath",
            "inventorySha256",
            "sourceRepository",
            "executableTransforms",
            "assets",
            "generator",
        },
        label="mirror contract",
    )
    fixed = {
        "contract": MIRROR_CONTRACT,
        "inventoryContract": INVENTORY_CONTRACT,
        "policyId": POLICY_ID,
        "inventoryPath": EXPECTED_PATHS["inventory"],
        "sourceRepository": "../chummer-play",
    }
    for field, expected in fixed.items():
        if mirror.get(field) != expected:
            raise RuntimeError(f"mirror contract {field} drifted")
    if type(mirror.get("assetPolicyCount")) is not int or mirror["assetPolicyCount"] != EXPECTED_ASSET_COUNT:
        raise RuntimeError("mirror contract assetPolicyCount drifted")
    if type(mirror.get("dependencyPolicyCount")) is not int or mirror["dependencyPolicyCount"] != EXPECTED_DEPENDENCY_COUNT:
        raise RuntimeError("mirror contract dependencyPolicyCount drifted")
    if require_sha256(mirror.get("inventorySha256"), label="mirror inventorySha256") != inventory_sha256:
        raise RuntimeError("mirror inventory digest binding drifted")

    inventory_assets = inventory["assets"]
    exact_inventory_assets = [row for row in inventory_assets if row["kind"] == "exact"]
    transform_inventory_assets = [row for row in inventory_assets if row["kind"] == "transform"]
    assets = mirror.get("assets")
    if not isinstance(assets, list) or len(assets) != len(exact_inventory_assets):
        raise RuntimeError("mirror exact asset set is not closed")
    asset_fields = {
        "source", "projection", "kind", "role", "contentType", "cacheControl", "sha256"
    }
    for index, (row, required) in enumerate(zip(assets, exact_inventory_assets, strict=True)):
        if not isinstance(row, dict):
            raise RuntimeError(f"mirror asset row {index} must be an object")
        require_exact_fields(row, asset_fields, label=f"mirror asset row {index}")
        for field in ("source", "projection", "kind", "role", "contentType", "cacheControl"):
            if row.get(field) != required.get(field):
                raise RuntimeError(f"mirror asset row {index} {field} drifted")
        declared = require_sha256(row.get("sha256"), label=f"mirror asset row {index} sha256")
        actual = sha256(
            bounded_read(
                mirror_path.parent / str(row["projection"]),
                limit=MAX_PROJECTED_ASSET_BYTES,
                label=f"projected mirror asset {index}",
            )
        )
        if declared != actual:
            raise RuntimeError(f"mirror asset row {index} digest drifted from its projection")

    transforms = mirror.get("executableTransforms")
    if not isinstance(transforms, list) or len(transforms) != 1 or len(transform_inventory_assets) != 1:
        raise RuntimeError("mirror transform set is not closed")
    transform = transforms[0]
    if not isinstance(transform, dict):
        raise RuntimeError("mirror transform must be an object")
    require_exact_fields(
        transform,
        {
            "source", "projection", "kind", "role", "contentType", "cacheControl",
            "contract", "sourceSha256", "projectionSha256", "transformation", "generatorConfig",
        },
        label="mirror transform",
    )
    required_transform = transform_inventory_assets[0]
    for field in ("source", "projection", "kind", "role", "contentType", "cacheControl"):
        if transform.get(field) != required_transform.get(field):
            raise RuntimeError(f"mirror transform {field} drifted")
    if transform.get("contract") != PROJECTION_CONTRACT:
        raise RuntimeError("mirror transform contract drifted")
    if require_sha256(transform.get("sourceSha256"), label="mirror transform sourceSha256") != projection["sourceSha256"]:
        raise RuntimeError("mirror transform source digest drifted from projection config")
    if require_sha256(transform.get("projectionSha256"), label="mirror transform projectionSha256") != template_sha256:
        raise RuntimeError("mirror transform projection digest drifted")
    projected_worker_sha256 = sha256(
        bounded_read(
            mirror_path.parent / str(transform["projection"]),
            limit=MAX_PROJECTED_ASSET_BYTES,
            label="projected root worker",
        )
    )
    if projected_worker_sha256 != template_sha256:
        raise RuntimeError("projected root worker differs from its reviewed template")
    if transform.get("generatorConfig") != "Chummer.Run.Api/play-worker-projection.json":
        raise RuntimeError("mirror transform generatorConfig drifted")
    expected_transformation = {
        "cacheContract": "play-source-v2 -> run-api-projection-v2",
        "baseManifest": "/manifest.webmanifest -> /manifest.play.webmanifest",
        "privateCompanionScript": "removed from the public-edge runtime allowlist",
        "activation": "passive; neither worker calls skipWaiting() or clients.claim()",
    }
    transformation = transform.get("transformation")
    if not isinstance(transformation, dict) or transformation != expected_transformation:
        raise RuntimeError("mirror transform description drifted from the closed contract")

    generator = mirror.get("generator")
    if not isinstance(generator, dict):
        raise RuntimeError("mirror generator must be an object")
    require_exact_fields(
        generator,
        {
            "contract", "command", "script", "scriptSha256", "config", "configSha256",
            "template", "templateSha256", "inventory", "inventorySha256", "dependencies",
        },
        label="mirror generator",
    )
    expected_generator_values = {
        "contract": GENERATOR_CONTRACT,
        "command": "python3 scripts/generate_public_play_worker_projection.py",
        "script": EXPECTED_PATHS["generator"],
        "config": "Chummer.Run.Api/play-worker-projection.json",
        "template": "Chummer.Run.Api/service-worker.public-edge.template.js",
        "inventory": EXPECTED_PATHS["inventory"],
    }
    for field, expected in expected_generator_values.items():
        if generator.get(field) != expected:
            raise RuntimeError(f"mirror generator {field} drifted")
    digest_bindings = {
        "scriptSha256": generator_sha256,
        "configSha256": projection_sha256,
        "templateSha256": template_sha256,
        "inventorySha256": inventory_sha256,
    }
    for field, expected in digest_bindings.items():
        if require_sha256(generator.get(field), label=f"mirror generator {field}") != expected:
            raise RuntimeError(f"mirror generator {field} binding drifted")

    dependencies = generator.get("dependencies")
    inventory_dependencies = inventory["generatorDependencies"]
    if not isinstance(dependencies, list) or len(dependencies) != EXPECTED_DEPENDENCY_COUNT:
        raise RuntimeError("mirror generator dependency set is not closed")
    dependency_fields = {"path", "kind", "role", "contentType", "sha256"}
    dependency_digests = (
        generator_sha256,
        projection_sha256,
        template_sha256,
        inventory_sha256,
    )
    for index, (row, required, expected_digest) in enumerate(
        zip(dependencies, inventory_dependencies, dependency_digests, strict=True)
    ):
        if not isinstance(row, dict):
            raise RuntimeError(f"mirror generator dependency row {index} must be an object")
        require_exact_fields(
            row,
            dependency_fields,
            label=f"mirror generator dependency row {index}",
        )
        for field in ("path", "kind", "role", "contentType"):
            if row.get(field) != required.get(field):
                raise RuntimeError(f"mirror generator dependency row {index} {field} drifted")
        if require_sha256(
            row.get("sha256"),
            label=f"mirror generator dependency row {index} sha256",
        ) != expected_digest:
            raise RuntimeError(f"mirror generator dependency row {index} digest drifted")


def validate(
    authority_path: Path,
    verifier: Path,
    generator: Path,
    inventory: Path,
    mirror: Path,
    projection: Path,
    template: Path,
) -> dict[str, Any]:
    input_specs = (
        ("authority", authority_path, MAX_AUTHORITY_BYTES, "authority"),
        ("verifier", verifier, MAX_IDENTITY_BYTES, "verifierSha256"),
        ("generator", generator, MAX_IDENTITY_BYTES, "generatorSha256"),
        ("inventory", inventory, MAX_CONTRACT_BYTES, "required inventory"),
        ("mirror", mirror, MAX_CONTRACT_BYTES, "mirror contract"),
        ("projection", projection, MAX_CONTRACT_BYTES, "worker projection"),
        ("template", template, MAX_IDENTITY_BYTES, "projection template"),
    )
    input_payloads: dict[str, bytes] = {}
    receipt_inputs: dict[str, dict[str, Any]] = {}
    for role, path, limit, label in input_specs:
        payload, identity = bounded_read_with_identity(path, limit=limit, label=label)
        input_payloads[role] = payload
        receipt_inputs[role] = {
            "path": os.fspath(path),
            "sha256": sha256(payload),
            "identity": identity,
        }

    authority = strict_json_object(input_payloads["authority"], label="authority")
    expected_fields = {
        "contractName",
        "policyId",
        "assetPolicyCount",
        "dependencyPolicyCount",
        "verifierPath",
        "verifierSha256",
        "generatorPath",
        "generatorSha256",
        "inventoryPath",
        "inventorySha256",
    }
    if set(authority) != expected_fields:
        raise RuntimeError("authority fields drifted from the closed contract")
    fixed_values = {
        "contractName": CONTRACT_NAME,
        "policyId": POLICY_ID,
        "assetPolicyCount": EXPECTED_ASSET_COUNT,
        "dependencyPolicyCount": EXPECTED_DEPENDENCY_COUNT,
        "verifierPath": EXPECTED_PATHS["verifier"],
        "generatorPath": EXPECTED_PATHS["generator"],
        "inventoryPath": EXPECTED_PATHS["inventory"],
    }
    for field, expected in fixed_values.items():
        if authority.get(field) != expected:
            raise RuntimeError(f"authority {field} drifted")
    if type(authority.get("assetPolicyCount")) is not int:
        raise RuntimeError("authority assetPolicyCount must be an integer")
    if type(authority.get("dependencyPolicyCount")) is not int:
        raise RuntimeError("authority dependencyPolicyCount must be an integer")

    verifier_payload = input_payloads["verifier"]
    generator_payload = input_payloads["generator"]
    inventory_payload = input_payloads["inventory"]
    projection_payload = input_payloads["projection"]
    template_payload = input_payloads["template"]
    inventory_contract = strict_json_object(
        inventory_payload,
        label="required inventory",
    )
    projection_contract = strict_json_object(
        projection_payload,
        label="worker projection",
    )
    mirror_contract = strict_json_object(
        input_payloads["mirror"],
        label="mirror contract",
    )
    identity_payloads = {
        "verifierSha256": verifier_payload,
        "generatorSha256": generator_payload,
        "inventorySha256": inventory_payload,
    }
    for field, payload in identity_payloads.items():
        declared = require_sha256(authority.get(field), label=f"authority {field}")
        if declared != sha256(payload):
            raise RuntimeError(f"authority {field} does not match its exact input")

    inventory_sha256 = sha256(inventory_payload)
    projection_sha256 = sha256(projection_payload)
    template_sha256 = sha256(template_payload)
    generator_sha256 = sha256(generator_payload)
    validate_inventory_contract(inventory_contract)
    validate_projection_contract(
        projection_contract,
        inventory_sha256=inventory_sha256,
        template_sha256=template_sha256,
    )
    validate_mirror_contract(
        mirror_contract,
        mirror_path=mirror,
        inventory=inventory_contract,
        inventory_sha256=inventory_sha256,
        projection=projection_contract,
        projection_sha256=projection_sha256,
        template_sha256=template_sha256,
        generator_sha256=generator_sha256,
    )
    for role, path, limit, label in input_specs:
        payload, identity = bounded_read_with_identity(path, limit=limit, label=label)
        if payload != input_payloads[role] or identity != receipt_inputs[role]["identity"]:
            raise RuntimeError(f"{label} changed during validation")
    return {
        "contractName": RECEIPT_CONTRACT_NAME,
        "contractVersion": RECEIPT_CONTRACT_VERSION,
        "status": "pass",
        "interpreter": {
            "executable": sys.executable,
            "implementation": sys.implementation.name,
            "version": [
                sys.version_info.major,
                sys.version_info.minor,
                sys.version_info.micro,
            ],
            "isolated": bool(sys.flags.isolated),
            "noSite": bool(sys.flags.no_site),
            "ignoreEnvironment": bool(sys.flags.ignore_environment),
            "safePath": bool(sys.flags.safe_path),
        },
        "inputs": receipt_inputs,
        "closedPolicy": {
            "policyId": POLICY_ID,
            "assetPolicyCount": EXPECTED_ASSET_COUNT,
            "dependencyPolicyCount": EXPECTED_DEPENDENCY_COUNT,
        },
    }


def require_isolated_receipt_interpreter() -> None:
    if not (
        sys.flags.isolated == 1
        and sys.flags.no_site == 1
        and sys.flags.ignore_environment == 1
        and bool(sys.flags.safe_path)
    ):
        raise RuntimeError(
            "receipt output requires isolated, no-site, environment-ignoring, safe-path Python"
        )


def write_atomic_canonical_receipt(path: Path, receipt: dict[str, Any]) -> None:
    payload = (json.dumps(receipt, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    parsed = strict_json_object(payload, label="validation receipt")
    require_exact_fields(
        parsed,
        {
            "contractName",
            "contractVersion",
            "status",
            "interpreter",
            "inputs",
            "closedPolicy",
        },
        label="validation receipt",
    )
    if parsed.get("status") != "pass":
        raise RuntimeError("validation receipt must be a pass receipt")

    parent = path.parent
    if not parent.is_dir():
        raise RuntimeError("validation receipt parent directory does not exist")
    descriptor = -1
    temporary_path = ""
    try:
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=parent,
        )
        os.fchmod(descriptor, 0o644)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short write while creating validation receipt")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary_path, path)
        temporary_path = ""
        directory_descriptor = os.open(
            parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--verifier", type=Path, required=True)
    parser.add_argument("--generator", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--mirror", type=Path, required=True)
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    try:
        if args.receipt is not None:
            receipt_target = args.receipt.resolve(strict=False)
            input_targets = {
                value.resolve(strict=False)
                for value in (
                    args.authority,
                    args.verifier,
                    args.generator,
                    args.inventory,
                    args.mirror,
                    args.projection,
                    args.template,
                )
            }
            if receipt_target in input_targets:
                raise RuntimeError("validation receipt must not replace a proof input")
        receipt = validate(
            args.authority,
            args.verifier,
            args.generator,
            args.inventory,
            args.mirror,
            args.projection,
            args.template,
        )
        if args.receipt is not None:
            require_isolated_receipt_interpreter()
            write_atomic_canonical_receipt(args.receipt, receipt)
    except (OSError, RuntimeError) as exc:
        print(f"public_pwa_proof_authority:error:{exc}")
        return 1
    print("public_pwa_proof_authority:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
