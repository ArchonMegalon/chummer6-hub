#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from typing import Any, Callable


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "play-worker-projection.json"
GENERATOR_CONTRACT = "play-root-worker-projection-generator-v1"
MIRROR_CONTRACT = "play-install-mirror-v5"
INVENTORY_CONTRACT = "play-install-mirror-required-inventory-v2"
POLICY_ID = "chummer.public-play-pwa-mirror.v1"
EXPECTED_CONFIG_PATH = "Chummer.Run.Api/play-worker-projection.json"
EXPECTED_CONFIG_BINDINGS = {
    "source": "../chummer-play/src/Chummer.Play.Web/wwwroot/service-worker.js",
    "template": "Chummer.Run.Api/service-worker.public-edge.template.js",
    "requiredInventory": "Chummer.Run.Api/play-pwa-required-inventory.json",
    "projection": "Chummer.Run.Api/wwwroot/service-worker.js",
    "mirrorContract": "Chummer.Run.Api/play-pwa-mirrors.json",
}
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
REQUIRED_DEPENDENCIES = {
    "generator_script": (
        "scripts/generate_public_play_worker_projection.py",
        "python",
        "text/x-python",
    ),
    "projection_config": (
        "Chummer.Run.Api/play-worker-projection.json",
        "json",
        "application/json",
    ),
    "projection_template": (
        "Chummer.Run.Api/service-worker.public-edge.template.js",
        "template",
        "application/javascript",
    ),
    "required_inventory": (
        "Chummer.Run.Api/play-pwa-required-inventory.json",
        "json",
        "application/json",
    ),
}
EXPECTED_DEPENDENCY_POLICY = tuple(
    (path, kind, role, content_type)
    for role, (path, kind, content_type) in REQUIRED_DEPENDENCIES.items()
)
CONTENT_TYPES_BY_SUFFIX = {
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webmanifest": "application/manifest+json",
}
_TRUSTED_INPUT_READER: Callable[[Path, Path, str], bytes | None] | None = None
_TRUSTED_INPUT_ROOTS: tuple[Path, ...] = ()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def strict_json_object(payload: bytes | str, *, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field {key!r}")
            result[key] = value
        return result

    try:
        text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
        parsed = json.loads(text, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"{label} is not strict JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{label} must be a JSON object")
    return parsed


def load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = strict_json_object(
            read_regular_file_no_symlinks(path, root=path.parent, label=label),
            label=label,
        )
    except (OSError, RuntimeError) as exc:
        raise RuntimeError(f"{label} is unreadable: {path}: {exc}") from exc
    return payload


def lexical_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def install_trusted_input_reader(
    reader: Callable[[Path, Path, str], bytes | None],
    *,
    roots: tuple[Path, ...],
) -> None:
    global _TRUSTED_INPUT_READER, _TRUSTED_INPUT_ROOTS
    if _TRUSTED_INPUT_READER is not None:
        raise RuntimeError("trusted input reader is already installed")
    normalized_roots = tuple(lexical_path(root) for root in roots)
    if len(normalized_roots) != 2 or len(set(normalized_roots)) != 2:
        raise RuntimeError("trusted input roots are invalid")
    _TRUSTED_INPUT_READER = reader
    _TRUSTED_INPUT_ROOTS = normalized_roots


def open_directory_no_symlinks(path: Path, *, label: str) -> int:
    absolute = lexical_path(path)
    if not absolute.is_absolute():
        raise RuntimeError(f"{label} must be absolute")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in absolute.parts[1:]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except (OSError, TypeError) as exc:
        os.close(descriptor)
        raise RuntimeError(f"{label} contains a symlink or non-directory component: {absolute}: {exc}") from exc


def require_directory_no_symlinks(path: Path, *, label: str) -> Path:
    absolute = lexical_path(path)
    if _TRUSTED_INPUT_READER is not None:
        for trusted_root in _TRUSTED_INPUT_ROOTS:
            try:
                absolute.relative_to(trusted_root)
            except ValueError:
                continue
            return absolute
    descriptor = open_directory_no_symlinks(absolute, label=label)
    os.close(descriptor)
    return absolute


def read_regular_file_no_symlinks(path: Path, *, root: Path, label: str) -> bytes:
    absolute_root = lexical_path(root)
    absolute_path = lexical_path(path)
    try:
        relative = absolute_path.relative_to(absolute_root)
    except ValueError as exc:
        raise RuntimeError(f"{label} escapes its declared root: {absolute_path}") from exc
    if not relative.parts:
        raise RuntimeError(f"{label} must name a file below its declared root")
    if _TRUSTED_INPUT_READER is not None:
        payload = _TRUSTED_INPUT_READER(absolute_path, absolute_root, label)
        if payload is not None:
            return payload

    absolute_root = require_directory_no_symlinks(absolute_root, label=f"{label} root")

    directory_descriptor = open_directory_no_symlinks(absolute_root, label=f"{label} root")
    try:
        for component in relative.parts[:-1]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_descriptor,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        file_descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=directory_descriptor,
        )
        try:
            metadata = os.fstat(file_descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise RuntimeError(f"{label} is not a regular file: {absolute_path}")
            with os.fdopen(file_descriptor, "rb", closefd=False) as handle:
                return handle.read()
        finally:
            os.close(file_descriptor)
    except (OSError, TypeError) as exc:
        raise RuntimeError(f"{label} contains a symlink or unreadable component: {absolute_path}: {exc}") from exc
    finally:
        os.close(directory_descriptor)


def resolve_declared_path(root: Path, value: object, *, label: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise RuntimeError(f"{label} path is missing")
    path = lexical_path(root / raw)
    workspace = lexical_path(root.parent)
    try:
        path.relative_to(workspace)
    except ValueError as exc:
        raise RuntimeError(f"{label} escapes the workspace: {raw}")
    return path


def normalized_relative_path(value: object, *, label: str) -> str:
    raw = str(value or "").strip()
    normalized = str(PurePosixPath(raw)) if raw else ""
    if (
        not raw
        or raw != normalized
        or raw.startswith("/")
        or "\\" in raw
        or any(part in {"", ".", ".."} for part in PurePosixPath(raw).parts)
    ):
        raise RuntimeError(f"{label} must be a normalized relative POSIX path")
    return raw


def validate_required_inventory(inventory: dict[str, Any]) -> None:
    if inventory.get("contract") != INVENTORY_CONTRACT:
        raise RuntimeError("required mirror inventory contract is unsupported")
    if inventory.get("policyId") != POLICY_ID:
        raise RuntimeError("required mirror inventory policy identity is unsupported")
    if inventory.get("sourceRepository") != "../chummer-play":
        raise RuntimeError("required mirror inventory must bind the sibling chummer-play source")

    assets = inventory.get("assets")
    if not isinstance(assets, list) or not assets:
        raise RuntimeError("required mirror inventory must declare assets")
    seen_sources: set[str] = set()
    seen_projections: set[str] = set()
    seen_roles: set[str] = set()
    transform_count = 0
    actual_asset_policy: list[tuple[str, str, str, str, str, str]] = []
    for item in assets:
        if not isinstance(item, dict):
            raise RuntimeError("required mirror inventory asset rows must be objects")
        source = normalized_relative_path(item.get("source"), label="inventory source")
        projection = normalized_relative_path(item.get("projection"), label="inventory projection")
        role = str(item.get("role") or "").strip()
        kind = str(item.get("kind") or "").strip()
        content_type = str(item.get("contentType") or "").strip()
        cache_control = str(item.get("cacheControl") or "").strip()
        if source in seen_sources or projection in seen_projections or not role or role in seen_roles:
            raise RuntimeError("required mirror inventory contains duplicate source, projection, or role")
        if kind not in {"exact", "transform"}:
            raise RuntimeError(f"required mirror inventory kind is invalid for {projection}")
        if CONTENT_TYPES_BY_SUFFIX.get(PurePosixPath(projection).suffix) != content_type:
            raise RuntimeError(f"required mirror inventory MIME is invalid for {projection}")
        if not cache_control:
            raise RuntimeError(f"required mirror inventory cache policy is missing for {projection}")
        seen_sources.add(source)
        seen_projections.add(projection)
        seen_roles.add(role)
        transform_count += int(kind == "transform")
        actual_asset_policy.append((source, projection, kind, role, content_type, cache_control))
    if transform_count != 1:
        raise RuntimeError("required mirror inventory must declare exactly one transform")
    if tuple(actual_asset_policy) != EXPECTED_ASSET_POLICY:
        raise RuntimeError(
            f"required mirror inventory must exactly match policy {POLICY_ID} "
            f"({len(EXPECTED_ASSET_POLICY)} ordered assets)"
        )

    dependencies = inventory.get("generatorDependencies")
    if not isinstance(dependencies, list) or len(dependencies) != len(REQUIRED_DEPENDENCIES):
        raise RuntimeError("required mirror inventory generator dependency set is incomplete")
    dependency_roles: set[str] = set()
    dependency_paths: set[str] = set()
    actual_dependency_policy: list[tuple[str, str, str, str]] = []
    for item in dependencies:
        if not isinstance(item, dict):
            raise RuntimeError("required mirror inventory dependency rows must be objects")
        role = str(item.get("role") or "").strip()
        path = normalized_relative_path(item.get("path"), label="inventory dependency")
        if role in dependency_roles or path in dependency_paths:
            raise RuntimeError("required mirror inventory contains duplicate dependency rows")
        expected = REQUIRED_DEPENDENCIES.get(role)
        actual = (path, str(item.get("kind") or "").strip(), str(item.get("contentType") or "").strip())
        if expected is None or actual != expected:
            raise RuntimeError(f"required mirror inventory dependency is invalid for role {role or '<missing>'}")
        dependency_roles.add(role)
        dependency_paths.add(path)
        actual_dependency_policy.append((path, actual[1], role, actual[2]))
    if dependency_roles != set(REQUIRED_DEPENDENCIES):
        raise RuntimeError("required mirror inventory generator dependency roles are incomplete")
    if tuple(actual_dependency_policy) != EXPECTED_DEPENDENCY_POLICY:
        raise RuntimeError(
            f"required mirror inventory must exactly match policy {POLICY_ID} "
            f"({len(EXPECTED_DEPENDENCY_POLICY)} ordered dependencies)"
        )


def load_required_inventory(
    root: Path,
    config: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    if config.get("requiredInventory") != EXPECTED_CONFIG_BINDINGS["requiredInventory"]:
        raise RuntimeError("required mirror inventory path drifted from the versioned policy")
    inventory_path = resolve_declared_path(
        root,
        config.get("requiredInventory"),
        label="required mirror inventory",
    )
    inventory_bytes = read_regular_file_no_symlinks(
        inventory_path,
        root=root,
        label="required mirror inventory",
    )
    require_digest(
        inventory_bytes,
        config.get("requiredInventorySha256"),
        label="required mirror inventory",
    )
    inventory = strict_json_object(inventory_bytes, label="required mirror inventory")
    validate_required_inventory(inventory)
    return inventory_path, inventory


def require_digest(payload: bytes, expected: object, *, label: str) -> str:
    actual = sha256(payload)
    normalized_expected = str(expected or "").strip().lower()
    if actual != normalized_expected:
        raise RuntimeError(
            f"{label} digest drifted: expected {normalized_expected or '<missing>'}, got {actual}; "
            "review the semantic change and update the declared projection config"
        )
    return actual


def require_markers(
    text: str,
    required: object,
    forbidden: object,
    *,
    label: str,
) -> None:
    required_values = required if isinstance(required, list) else []
    forbidden_values = forbidden if isinstance(forbidden, list) else []
    missing = [str(marker) for marker in required_values if str(marker) not in text]
    present_forbidden = [str(marker) for marker in forbidden_values if str(marker) in text]
    if missing or present_forbidden:
        detail = []
        if missing:
            detail.append(f"missing markers: {', '.join(missing)}")
        if present_forbidden:
            detail.append(f"forbidden markers: {', '.join(present_forbidden)}")
        raise RuntimeError(f"{label} semantic contract failed ({'; '.join(detail)})")


def render_projection(
    root: Path,
    config_path: Path,
) -> tuple[bytes, dict[str, Any], Path, dict[str, Any]]:
    root = require_directory_no_symlinks(root, label="run-services root")
    config_path = lexical_path(config_path)
    expected_config_path = lexical_path(root / EXPECTED_CONFIG_PATH)
    if config_path != expected_config_path:
        raise RuntimeError("worker projection config path drifted from the versioned policy")
    config_bytes = read_regular_file_no_symlinks(
        config_path,
        root=root,
        label="worker projection config",
    )
    config = strict_json_object(config_bytes, label="worker projection config")
    if config.get("contract") != "play-root-worker-public-edge-projection-v2":
        raise RuntimeError("worker projection config contract is unsupported")
    for field, expected in EXPECTED_CONFIG_BINDINGS.items():
        if config.get(field) != expected:
            raise RuntimeError(f"worker projection config {field} drifted from the versioned policy")

    source_path = resolve_declared_path(root, config.get("source"), label="source worker")
    template_path = resolve_declared_path(root, config.get("template"), label="projection template")
    inventory_path, inventory = load_required_inventory(root, config)
    source_root = require_directory_no_symlinks(root.parent / "chummer-play", label="sibling chummer-play root")
    api_root = require_directory_no_symlinks(root / "Chummer.Run.Api", label="Chummer.Run.Api root")
    source = read_regular_file_no_symlinks(source_path, root=source_root, label="source worker")
    template = read_regular_file_no_symlinks(template_path, root=api_root, label="projection template")
    require_digest(source, config.get("sourceSha256"), label="source worker")
    require_digest(template, config.get("templateSha256"), label="projection template")
    require_markers(
        source.decode("utf-8"),
        config.get("requiredSourceMarkers"),
        config.get("forbiddenSourceMarkers"),
        label="source worker",
    )
    require_markers(
        template.decode("utf-8"),
        config.get("requiredProjectionMarkers"),
        config.get("forbiddenProjectionMarkers"),
        label="projected worker",
    )
    return template, config, inventory_path, inventory


def build_mirror_contract(
    root: Path,
    config_path: Path,
    projection: bytes,
    config: dict[str, Any],
    inventory_path: Path,
    inventory: dict[str, Any],
) -> dict[str, Any]:
    api_root = require_directory_no_symlinks(root / "Chummer.Run.Api", label="Chummer.Run.Api root")
    source_repository = resolve_declared_path(
        root,
        inventory.get("sourceRepository"),
        label="mirror source repository",
    )
    expected_source_repository = lexical_path(root.parent / "chummer-play")
    if source_repository != expected_source_repository:
        raise RuntimeError("mirror source repository drifted from the exact sibling root")
    source_repository = require_directory_no_symlinks(
        source_repository,
        label="mirror source repository",
    )

    assets: list[dict[str, Any]] = []
    transforms: list[dict[str, Any]] = []
    for inventory_item in inventory["assets"]:
        item = dict(inventory_item)
        source_path = resolve_declared_path(source_repository, item["source"], label="mirror source asset")
        projection_path = resolve_declared_path(api_root, item["projection"], label="mirror projection asset")
        source_bytes = read_regular_file_no_symlinks(
            source_path,
            root=source_repository,
            label=f"mirror source asset {item['role']}",
        )
        if item["kind"] == "exact":
            projection_bytes = read_regular_file_no_symlinks(
                projection_path,
                root=api_root,
                label=f"mirror projection asset {item['role']}",
            )
            if source_bytes != projection_bytes:
                raise RuntimeError(f"exact mirror asset drifted: {item['projection']}")
            item["sha256"] = sha256(projection_bytes)
            assets.append(item)
            continue

        expected_source = str(config["source"]).split("../chummer-play/", 1)[-1]
        expected_projection = str(config["projection"]).split("Chummer.Run.Api/", 1)[-1]
        if item["source"] != expected_source or item["projection"] != expected_projection:
            raise RuntimeError("root worker transform does not match the projection config")
        if sha256(source_bytes) != str(config["sourceSha256"]):
            raise RuntimeError("root worker transform source digest does not match the projection config")
        item.update(
            {
                "contract": str(config["contract"]),
                "sourceSha256": str(config["sourceSha256"]),
                "projectionSha256": sha256(projection),
                "transformation": {
                    "cacheContract": "play-source-v2 -> run-api-projection-v2",
                    "baseManifest": "/manifest.webmanifest -> /manifest.play.webmanifest",
                    "privateCompanionScript": "removed from the public-edge runtime allowlist",
                    "activation": "passive; neither worker calls skipWaiting() or clients.claim()",
                },
                "generatorConfig": str(config_path.relative_to(root)),
            }
        )
        transforms.append(item)
    if len(transforms) != 1:
        raise RuntimeError("mirror contract must declare exactly one executable transform")

    script_path = lexical_path(Path(__file__))
    expected_script_path = lexical_path(root / REQUIRED_DEPENDENCIES["generator_script"][0])
    if script_path != expected_script_path:
        raise RuntimeError("generator script path drifted from the versioned policy")
    template_path = resolve_declared_path(root, config.get("template"), label="projection template")
    dependency_rows: list[dict[str, Any]] = []
    dependency_paths = {
        "generator_script": script_path,
        "projection_config": lexical_path(config_path),
        "projection_template": template_path,
        "required_inventory": inventory_path,
    }
    for dependency in inventory["generatorDependencies"]:
        item = dict(dependency)
        path = resolve_declared_path(root, item["path"], label=f"generator dependency {item['role']}")
        if path != dependency_paths[item["role"]]:
            raise RuntimeError(f"generator dependency path drifted for {item['role']}")
        item["sha256"] = sha256(
            read_regular_file_no_symlinks(
                path,
                root=root,
                label=f"generator dependency {item['role']}",
            )
        )
        dependency_rows.append(item)

    dependency_bytes = {
        role: read_regular_file_no_symlinks(path, root=root, label=f"generator dependency {role}")
        for role, path in dependency_paths.items()
    }

    generator = {
        "contract": GENERATOR_CONTRACT,
        "command": "python3 scripts/generate_public_play_worker_projection.py",
        "script": str(script_path.relative_to(root)),
        "scriptSha256": sha256(dependency_bytes["generator_script"]),
        "config": str(config_path.relative_to(root)),
        "configSha256": sha256(dependency_bytes["projection_config"]),
        "template": str(template_path.relative_to(root)),
        "templateSha256": sha256(dependency_bytes["projection_template"]),
        "inventory": str(inventory_path.relative_to(root)),
        "inventorySha256": sha256(dependency_bytes["required_inventory"]),
        "dependencies": dependency_rows,
    }
    return {
        "contract": MIRROR_CONTRACT,
        "inventoryContract": str(inventory["contract"]),
        "policyId": POLICY_ID,
        "assetPolicyCount": len(EXPECTED_ASSET_POLICY),
        "dependencyPolicyCount": len(EXPECTED_DEPENDENCY_POLICY),
        "inventoryPath": str(inventory_path.relative_to(root)),
        "inventorySha256": sha256(dependency_bytes["required_inventory"]),
        "sourceRepository": str(inventory["sourceRepository"]),
        "executableTransforms": transforms,
        "assets": assets,
        "generator": generator,
    }


def render_mirror_bytes(contract: dict[str, Any]) -> bytes:
    return (json.dumps(contract, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    require_directory_no_symlinks(path.parent, label=f"output directory for {path.name}")
    if path.is_symlink():
        raise RuntimeError(f"output path must not be a symlink: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def run(
    *,
    root: Path,
    config_path: Path,
    output_path: Path | None = None,
    mirror_output_path: Path | None = None,
    check: bool = False,
) -> dict[str, Any]:
    root = require_directory_no_symlinks(root, label="run-services root")
    projection, config, inventory_path, inventory = render_projection(root, config_path)
    declared_output = resolve_declared_path(root, config.get("projection"), label="projected worker")
    declared_mirror = resolve_declared_path(root, config.get("mirrorContract"), label="mirror contract")
    output = lexical_path(output_path or declared_output)
    mirror_output = lexical_path(mirror_output_path or declared_mirror)
    mirror_bytes = render_mirror_bytes(
        build_mirror_contract(
            root,
            lexical_path(config_path),
            projection,
            config,
            inventory_path,
            inventory,
        )
    )

    if check:
        failures = []
        try:
            output_bytes = read_regular_file_no_symlinks(output, root=output.parent, label="projected worker output")
        except RuntimeError:
            output_bytes = b""
        try:
            mirror_output_bytes = read_regular_file_no_symlinks(mirror_output, root=mirror_output.parent, label="mirror contract output")
        except RuntimeError:
            mirror_output_bytes = b""
        if output_bytes != projection:
            failures.append(f"projected worker differs from deterministic output: {output}")
        if mirror_output_bytes != mirror_bytes:
            failures.append(f"mirror contract differs from deterministic output: {mirror_output}")
        if failures:
            raise RuntimeError("; ".join(failures))
    else:
        atomic_write(output, projection)
        atomic_write(mirror_output, mirror_bytes)

    return {
        "contract": GENERATOR_CONTRACT,
        "status": "pass",
        "sourceSha256": str(config["sourceSha256"]),
        "projectionSha256": sha256(projection),
        "inventoryContract": str(inventory["contract"]),
        "policyId": POLICY_ID,
        "assetPolicyCount": len(EXPECTED_ASSET_POLICY),
        "dependencyPolicyCount": len(EXPECTED_DEPENDENCY_POLICY),
        "symlinkPolicy": "reject_all_components",
        "inputAuthorityMode": (
            "sealed_trusted_payload_provider"
            if _TRUSTED_INPUT_READER is not None
            else "nofollow_path_reads"
        ),
        "projectionPath": str(output),
        "mirrorPath": str(mirror_output),
        "checkOnly": check,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministically generate the public-edge Play worker and mirror digest contract."
    )
    parser.add_argument("--root", type=Path, default=RUN_SERVICES_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mirror-output", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        receipt = run(
            root=args.root,
            config_path=args.config,
            output_path=args.output,
            mirror_output_path=args.mirror_output,
            check=args.check,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"public_play_worker_projection:error:{exc}")
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
