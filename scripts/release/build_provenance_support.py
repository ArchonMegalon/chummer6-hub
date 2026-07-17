#!/usr/bin/env python3
"""Portable deterministic support for Chummer build provenance producers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


PROVENANCE_CONTRACT_NAME = "chummer6.build_provenance.v1"
PROVENANCE_STATE_CONTRACT_NAME = "chummer6.build_provenance_invocation_state.v1"
EXPECTED_BUILDER_ID = "chummer-mac-hosted-bootstrap"
EXPECTED_BUILD_TYPE = "macos-desktop-release"
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TARGET_BY_HEAD = {"avalonia": "desktop-avalonia", "blazor-desktop": "desktop-blazor"}
REQUIRED_SOURCE_MATERIALS = {
    "chummer-core-engine",
    "chummer.run-services",
    "chummer-ui-kit",
    "chummer-hub-registry",
    "chummer-media-factory",
    "chummer5a",
}
GENERATED_UNTRACKED_ROOTS = frozenset(
    {".codex-studio/published", ".state", ".tmp", ".vexp", "dist"}
)
GENERATED_UNTRACKED_SEGMENTS = frozenset({"bin", "obj"})


@dataclass(frozen=True)
class ProjectTarget:
    target_id: str
    repository: str
    repo_root: Path
    project_path: Path


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def canonical_json_sha256(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise OSError(f"hash input is not a regular file: {path}")
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(handle.fileno())
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if identity(before) != identity(after):
        raise OSError(f"hash input changed while it was being read: {path}")
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(encoded)
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def generated_untracked_path_allowed(path_text: str) -> bool:
    normalized = path_text.replace("\\", "/").strip().rstrip("/")
    if normalized.startswith('"'):
        return False
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or normalized.startswith("../"):
        return False
    parts = tuple(part for part in normalized.split("/") if part)
    if any(part in GENERATED_UNTRACKED_SEGMENTS for part in parts):
        return True
    return any(
        normalized == root or normalized.startswith(root + "/")
        for root in GENERATED_UNTRACKED_ROOTS
    )


def release_relevant_git_status(status_output: str) -> list[str]:
    relevant: list[str] = []
    for raw_line in status_output.splitlines():
        if not raw_line:
            continue
        state = raw_line[:2]
        path_text = raw_line[3:] if len(raw_line) > 3 else ""
        if state in {"??", "!!"} and generated_untracked_path_allowed(path_text):
            continue
        relevant.append(raw_line)
    return relevant


def git_revision(repo_root: Path) -> tuple[str, str, bool]:
    results: dict[str, subprocess.CompletedProcess[str]] = {}
    commands = {
        "commit": ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        "tree": ["git", "-C", str(repo_root), "rev-parse", "HEAD^{tree}"],
        "dirty": [
            "git",
            "-C",
            str(repo_root),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignored=matching",
        ],
    }
    for name, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"source revision command is unavailable: {type(exc).__name__}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise RuntimeError(
                f"source revision command failed ({name}): "
                f"{detail[-1][:300] if detail else 'non-zero exit'}"
            )
        results[name] = result
    commit = results["commit"].stdout.strip().lower()
    tree = results["tree"].stdout.strip().lower()
    if len(commit) not in range(40, 65) or len(tree) not in range(40, 65):
        raise RuntimeError("source revision command returned an invalid commit or tree id")
    if any(character not in "0123456789abcdef" for character in commit + tree):
        raise RuntimeError("source revision command returned an invalid commit or tree id")
    return commit, tree, bool(release_relevant_git_status(results["dirty"].stdout))


def file_snapshot(path: Path) -> dict[str, object]:
    try:
        handle = path.open("rb")
    except (FileNotFoundError, IsADirectoryError):
        return {"exists": False, "path": str(path)}
    with handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            return {"exists": False, "path": str(path)}
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(handle.fileno())
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if identity(before) != identity(after):
        raise RuntimeError(f"file changed while its identity was captured: {path}")
    return {
        "exists": True,
        "path": str(path),
        "sha256": digest.hexdigest(),
        "size_bytes": after.st_size,
        "mtime_ns": after.st_mtime_ns,
        "device": after.st_dev,
        "inode": after.st_ino,
    }


def load_assets(target: ProjectTarget) -> tuple[dict[str, Any] | None, str | None, Path]:
    assets_path = target.project_path.parent / "obj" / "project.assets.json"
    if not target.project_path.is_file():
        return None, f"project is missing: {target.project_path}", assets_path
    if not assets_path.is_file():
        return None, f"restore assets are unavailable: {assets_path}", assets_path
    try:
        payload = json.loads(assets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"restore assets are malformed: {type(exc).__name__}", assets_path
    if not isinstance(payload, dict) or not isinstance(payload.get("libraries"), dict):
        return None, "restore assets do not expose a NuGet library inventory", assets_path
    inputs = [target.project_path]
    for name in ("Directory.Build.props", "Directory.Build.targets", "Directory.Packages.props", "global.json"):
        candidate = target.repo_root / name
        if candidate.is_file():
            inputs.append(candidate)
    for library in payload["libraries"].values():
        if not isinstance(library, dict) or library.get("type") != "project":
            continue
        relative_project = str(library.get("path") or "").strip()
        if relative_project:
            inputs.append((target.project_path.parent / relative_project).resolve())
    try:
        assets_mtime = assets_path.stat().st_mtime_ns
        stale = [str(path) for path in inputs if path.is_file() and path.stat().st_mtime_ns > assets_mtime]
    except OSError as exc:
        return None, f"restore asset freshness could not be evaluated: {type(exc).__name__}", assets_path
    if stale:
        return None, f"restore assets are stale relative to {len(stale)} dependency input(s)", assets_path
    return payload, None, assets_path


def dependency_inventory_sha256(assets: dict[str, Any]) -> str:
    libraries = {
        str(key): {
            "type": "package",
            "sha512": str(metadata.get("sha512") or ""),
            "path": str(metadata.get("path") or ""),
        }
        for key, metadata in sorted((assets.get("libraries") or {}).items())
        if isinstance(metadata, dict) and metadata.get("type") == "package"
    }
    targets: dict[str, object] = {}
    for framework, framework_libraries in sorted((assets.get("targets") or {}).items()):
        if not isinstance(framework_libraries, dict):
            continue
        targets[str(framework)] = {
            str(key): {
                "type": str(metadata.get("type") or "package"),
                "dependencies": dict(sorted((metadata.get("dependencies") or {}).items())),
            }
            for key, metadata in sorted(framework_libraries.items())
            if isinstance(metadata, dict) and "/" in str(key)
        }
    return canonical_json_sha256(
        {
            "project_version": str(((assets.get("project") or {}).get("version") or "0.0.0-local")),
            "libraries": libraries,
            "targets": targets,
        }
    )


def build_cyclonedx(target: ProjectTarget, assets: dict[str, Any], inventory_sha256: str) -> dict[str, object]:
    components: list[dict[str, object]] = []
    refs_by_name: dict[str, str] = {}
    for library_key, metadata in sorted((assets.get("libraries") or {}).items()):
        if not isinstance(metadata, dict) or metadata.get("type") != "package" or "/" not in library_key:
            continue
        name, version = library_key.rsplit("/", 1)
        bom_ref = f"pkg:nuget/{quote(name, safe='')}@{quote(version, safe='')}"
        component: dict[str, object] = {
            "type": "library",
            "bom-ref": bom_ref,
            "name": name,
            "version": version,
            "purl": bom_ref,
        }
        sha512 = str(metadata.get("sha512") or "").strip()
        if sha512:
            try:
                component["hashes"] = [{"alg": "SHA-512", "content": base64.b64decode(sha512).hex()}]
            except (TypeError, ValueError):
                pass
        components.append(component)
        refs_by_name[name.lower()] = bom_ref
    dependencies: dict[str, set[str]] = {reference: set() for reference in refs_by_name.values()}
    for framework in (assets.get("targets") or {}).values():
        if not isinstance(framework, dict):
            continue
        for library_key, metadata in framework.items():
            if not isinstance(metadata, dict) or "/" not in str(library_key):
                continue
            source_ref = refs_by_name.get(str(library_key).rsplit("/", 1)[0].lower())
            if not source_ref:
                continue
            for dependency_name in (metadata.get("dependencies") or {}):
                dependency_ref = refs_by_name.get(str(dependency_name).lower())
                if dependency_ref:
                    dependencies[source_ref].add(dependency_ref)
    root_ref = f"urn:chummer:project:{target.target_id}"
    project_version = str(((assets.get("project") or {}).get("version") or "0.0.0-local"))
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, target.target_id + ':' + inventory_sha256)}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": target.target_id,
                "version": project_version,
                "properties": [
                    {"name": "chummer:projectPath", "value": str(target.project_path.relative_to(target.repo_root))},
                    {"name": "chummer:dependencyInventorySha256", "value": inventory_sha256},
                    {"name": "chummer:evidenceKind", "value": "restore-assets-inventory"},
                ],
            },
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "chummer-supply-chain-release-gate",
                        "version": "1",
                    }
                ]
            },
        },
        "components": components,
        "dependencies": [
            {"ref": root_ref, "dependsOn": sorted(refs_by_name.values())},
            *[
                {"ref": reference, "dependsOn": sorted(values)}
                for reference, values in sorted(dependencies.items())
            ],
        ],
    }


def _parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _normalized_platform(value: object) -> str:
    token = str(value or "").strip().lower()
    return {"mac": "macos", "osx": "macos", "darwin": "macos"}.get(token, token)


def _governed_files(root: Path, failures: list[str]) -> tuple[list[Path], list[Path]]:
    governed_root = root / "proof" / "build-provenance" / "v1"
    invocation_root = governed_root / "invocations"
    sbom_root = governed_root / "sbom"
    if not governed_root.is_dir() or governed_root.is_symlink():
        failures.append("bundle is missing the governed proof/build-provenance/v1 directory")
        return [], []
    for path in governed_root.rglob("*"):
        if path.is_symlink():
            failures.append(f"governed build provenance cannot contain symlinks: {path.name}")
    allowed_directories = {governed_root, invocation_root, sbom_root}
    for path in governed_root.rglob("*"):
        if path.is_dir() and path not in allowed_directories:
            failures.append(f"governed build provenance contains an unexpected directory: {path.name}")
        elif path.is_file():
            allowed_receipt = path.parent == invocation_root and path.name.endswith(".json")
            allowed_sbom = path.parent == sbom_root and path.name.endswith(".cdx.json")
            if not allowed_receipt and not allowed_sbom:
                failures.append(f"governed build provenance contains an unexpected path: {path.name}")
    invocations = sorted(path for path in invocation_root.glob("*.json") if path.is_file()) if invocation_root.is_dir() else []
    sboms = sorted(path for path in sbom_root.glob("*.cdx.json") if path.is_file()) if sbom_root.is_dir() else []
    if not invocations:
        failures.append("governed build provenance has no invocation receipts")
    if not sboms:
        failures.append("governed build provenance has no SBOM documents")
    return invocations, sboms


def validate_release_bundle_build_provenance(bundle_root: Path) -> list[str]:
    """Validate exact Mac artifact, receipt, and SBOM identity inside a bundle."""

    bundle_root = bundle_root.resolve()
    failures: list[str] = []
    manifest_path = bundle_root / "RELEASE_CHANNEL.generated.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"canonical release manifest is unavailable or malformed: {type(exc).__name__}"]
    artifacts = manifest.get("artifacts") if isinstance(manifest, dict) else None
    if not isinstance(artifacts, list):
        return ["canonical release manifest artifacts must be a list"]
    expected: dict[str, dict[str, object]] = {}
    for row in artifacts:
        if not isinstance(row, dict) or _normalized_platform(row.get("platform")) != "macos":
            continue
        head = str(row.get("head") or "").strip().lower()
        target_id = TARGET_BY_HEAD.get(head)
        artifact_id = str(row.get("artifactId") or "").strip()
        file_name = str(row.get("fileName") or "").strip()
        sha256 = str(row.get("sha256") or "").strip().lower().removeprefix("sha256:")
        size = row.get("sizeBytes")
        if (
            target_id is None
            or not SAFE_ID_RE.fullmatch(artifact_id)
            or Path(file_name).name != file_name
            or not SHA256_RE.fullmatch(sha256)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
        ):
            failures.append(f"Mac artifact row is incomplete for provenance: {artifact_id or file_name or '<unknown>'}")
            continue
        artifact_path = bundle_root / "files" / file_name
        if not artifact_path.is_file() or artifact_path.is_symlink():
            failures.append(f"Mac artifact bytes are unavailable for provenance: {artifact_id}")
            continue
        if artifact_path.stat().st_size != size or sha256_file(artifact_path) != sha256:
            failures.append(f"Mac artifact identity does not match its manifest row: {artifact_id}")
            continue
        expected[artifact_id] = {
            "artifact_id": artifact_id,
            "artifact_name": file_name,
            "artifact_sha256": sha256,
            "artifact_size_bytes": size,
            "target_id": target_id,
        }
    if not expected:
        return failures

    invocation_paths, sbom_paths = _governed_files(bundle_root, failures)
    sbom_by_target: dict[str, tuple[Path, str]] = {}
    for path in sbom_paths:
        target_id = path.name[: -len(".cdx.json")]
        if target_id not in set(TARGET_BY_HEAD.values()) or path.stat().st_size > 16 * 1024 * 1024:
            failures.append(f"governed build provenance contains an unexpected or oversized SBOM: {path.name}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"SBOM is malformed ({path.name}): {type(exc).__name__}")
            continue
        component = ((payload.get("metadata") or {}).get("component") or {}) if isinstance(payload, dict) else {}
        if (
            payload.get("bomFormat") != "CycloneDX"
            or payload.get("specVersion") != "1.5"
            or component.get("name") != target_id
            or component.get("bom-ref") != f"urn:chummer:project:{target_id}"
        ):
            failures.append(f"SBOM contract or target binding is invalid: {path.name}")
            continue
        if target_id in sbom_by_target:
            failures.append(f"governed build provenance contains duplicate SBOM target: {target_id}")
            continue
        sbom_by_target[target_id] = (path, sha256_file(path))

    subjects: dict[str, dict[str, object]] = {}
    now = datetime.now(timezone.utc)
    for path in invocation_paths:
        if path.stat().st_size > 4 * 1024 * 1024:
            failures.append(f"build provenance invocation receipt is oversized: {path.name}")
            continue
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"build provenance invocation is malformed ({path.name}): {type(exc).__name__}")
            continue
        if not isinstance(receipt, dict):
            failures.append(f"build provenance invocation must be an object: {path.name}")
            continue
        invocation_id = str(receipt.get("invocation_id") or "").strip()
        generated_at = _parse_timestamp(receipt.get("generated_at_utc"))
        started_at = _parse_timestamp(receipt.get("build_started_at_utc"))
        if (
            receipt.get("contract_name") != PROVENANCE_CONTRACT_NAME
            or receipt.get("receipt_kind") != "invocation"
            or receipt.get("status") != "pass"
            or receipt.get("builder_id") != EXPECTED_BUILDER_ID
            or receipt.get("build_type") != EXPECTED_BUILD_TYPE
            or receipt.get("failures") not in ([], None)
            or not SAFE_ID_RE.fullmatch(invocation_id)
            or path.name != f"{invocation_id}.json"
        ):
            failures.append(f"build provenance invocation contract is invalid: {path.name}")
            continue
        if (
            generated_at is None
            or started_at is None
            or generated_at < started_at
            or generated_at < now - timedelta(days=7)
            or generated_at > now + timedelta(minutes=5)
        ):
            failures.append(f"build provenance invocation timestamp is invalid or stale: {path.name}")
        invocation = receipt.get("invocation") if isinstance(receipt.get("invocation"), dict) else {}
        state = invocation.get("state") if isinstance(invocation.get("state"), dict) else {}
        state_sha = str(invocation.get("state_sha256") or "").strip().lower()
        if (
            invocation.get("state_contract_name") != PROVENANCE_STATE_CONTRACT_NAME
            or invocation.get("subject_declared_before_build") is not True
            or invocation.get("source_identity_stable") is not True
            or not SHA256_RE.fullmatch(state_sha)
            or canonical_json_sha256(state) != state_sha
        ):
            failures.append(f"build provenance invocation state binding is invalid: {path.name}")
            continue
        if any(state.get(field) != receipt.get(field) for field in ("builder_id", "build_type", "invocation_id")):
            failures.append(f"build provenance invocation state identity mismatch: {path.name}")
        if state.get("started_at_utc") != receipt.get("build_started_at_utc"):
            failures.append(f"build provenance invocation start timestamp mismatch: {path.name}")
        tools = state.get("build_tools") if isinstance(state.get("build_tools"), dict) else {}
        if any(
            SHA256_RE.fullmatch(str(tools.get(field) or "").strip().lower()) is None
            for field in ("provenance_generator_sha256", "supply_chain_verifier_sha256")
        ):
            failures.append(f"build provenance tool binding is invalid: {path.name}")
        expected_inputs = {
            "hosted-bootstrap",
            "desktop-project",
            "desktop-installer-recipe",
            "dotnet-sdk-selection",
        }
        input_rows = [item for item in state.get("build_inputs") or [] if isinstance(item, dict)]
        input_names = {
            str(item.get("label") or "")
            for item in input_rows
            if SHA256_RE.fullmatch(str(item.get("sha256") or "").strip().lower())
        }
        if input_names != expected_inputs or len(input_rows) != len(expected_inputs):
            failures.append(f"build provenance input set is incomplete or invalid: {path.name}")
        source = state.get("source") if isinstance(state.get("source"), dict) else {}
        if (
            source.get("repository") != "chummer-presentation"
            or source.get("tracked_worktree_dirty") is not False
            or not re.fullmatch(r"[0-9a-f]{40,64}", str(source.get("commit") or ""))
            or not re.fullmatch(r"[0-9a-f]{40,64}", str(source.get("tree") or ""))
        ):
            failures.append(f"build provenance source binding is invalid: {path.name}")
        material_rows = [item for item in state.get("source_materials") or [] if isinstance(item, dict)]
        material_names = {
            str(item.get("repository") or "")
            for item in material_rows
            if item.get("tracked_worktree_dirty") is False
            and re.fullmatch(r"[0-9a-f]{40,64}", str(item.get("commit") or ""))
            and re.fullmatch(r"[0-9a-f]{40,64}", str(item.get("tree") or ""))
        }
        if material_names != REQUIRED_SOURCE_MATERIALS or len(material_rows) != len(REQUIRED_SOURCE_MATERIALS):
            failures.append(f"build provenance source-material set is incomplete: {path.name}")
        rows = receipt.get("subjects")
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            failures.append(f"build provenance invocation must contain exactly one subject: {path.name}")
            continue
        subject = rows[0]
        artifact_id = str(subject.get("artifact_id") or "").strip()
        declared = state.get("subject_declaration") if isinstance(state.get("subject_declaration"), dict) else {}
        sbom = state.get("sbom") if isinstance(state.get("sbom"), dict) else {}
        expected_row = expected.get(artifact_id)
        target_id = str(subject.get("target_id") or "")
        sbom_record = sbom_by_target.get(target_id)
        if expected_row is None:
            failures.append(f"build provenance contains an unexpected subject: {artifact_id or '<blank>'}")
            continue
        comparisons = {
            "artifact_kind": (subject.get("artifact_kind"), "desktop_download"),
            "artifact_name": (subject.get("artifact_name"), expected_row["artifact_name"]),
            "artifact_sha256": (subject.get("artifact_sha256"), expected_row["artifact_sha256"]),
            "artifact_size_bytes": (subject.get("artifact_size_bytes"), expected_row["artifact_size_bytes"]),
            "target_id": (subject.get("target_id"), expected_row["target_id"]),
            "source_repository": (subject.get("source_repository"), "chummer-presentation"),
            "source_commit": (subject.get("source_commit"), source.get("commit")),
            "source_tree": (subject.get("source_tree"), source.get("tree")),
            "invocation_id": (subject.get("invocation_id"), invocation_id),
            "declared artifact id": (declared.get("artifact_id"), artifact_id),
            "declared artifact name": (declared.get("artifact_name"), expected_row["artifact_name"]),
            "declared artifact kind": (declared.get("artifact_kind"), "desktop_download"),
            "declared artifact binding": (declared.get("artifact_binding_type"), "file"),
            "declared artifact path": (
                Path(str(declared.get("artifact_path") or "")).name,
                expected_row["artifact_name"],
            ),
            "declared target id": (declared.get("target_id"), expected_row["target_id"]),
        }
        if any(left != right for left, right in comparisons.values()):
            failures.append(f"build provenance subject identity mismatch: {artifact_id}")
        if not isinstance(declared.get("prebuild"), dict):
            failures.append(f"build provenance pre-build artifact snapshot is missing: {artifact_id}")
        if subject.get("produced_during_invocation") is not True or subject.get("source_tracked_worktree_dirty") is not False:
            failures.append(f"build provenance subject lacks clean invocation production proof: {artifact_id}")
        if (
            not isinstance(state.get("started_epoch_ns"), int)
            or isinstance(state.get("started_epoch_ns"), bool)
            or state.get("started_epoch_ns", 0) <= 0
            or not isinstance(subject.get("artifact_built_mtime_ns"), int)
            or isinstance(subject.get("artifact_built_mtime_ns"), bool)
            or subject.get("artifact_built_mtime_ns", 0) <= state.get("started_epoch_ns", 0)
        ):
            failures.append(f"build provenance artifact production time is invalid: {artifact_id}")
        if (
            sbom_record is None
            or subject.get("sbom_sha256") != sbom_record[1]
            or sbom.get("sha256") != sbom_record[1]
            or subject.get("sbom_generator") != "deterministic_project.assets.json_inventory.v1"
            or sbom.get("generator") != "deterministic_project.assets.json_inventory.v1"
        ):
            failures.append(f"build provenance SBOM identity mismatch: {artifact_id}")
        if artifact_id in subjects:
            failures.append(f"build provenance contains duplicate subject: {artifact_id}")
        else:
            subjects[artifact_id] = subject
    missing = sorted(set(expected).difference(subjects))
    if missing:
        failures.append(f"build provenance is missing Mac artifact subjects: {','.join(missing)}")
    expected_targets = {str(row["target_id"]) for row in expected.values()}
    if set(sbom_by_target) != expected_targets:
        failures.append("build provenance SBOM target set does not match the Mac artifact target set")
    return list(dict.fromkeys(failures))
