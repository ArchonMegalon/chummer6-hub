#!/usr/bin/env python3
"""Consume one immutable Core main runtime artifact and retain only its verdict."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


AUTHORITY_CONTRACT = "chummer-hub.core-main-runtime-artifact-consumer-authority/v1"
VERDICT_CONTRACT = "chummer-hub.core-main-runtime-artifact-verdict/v1"
VALIDATION_V3 = "chummer-hub.core-runtime-package-artifact-validation/v3"
BYTE_SNAPSHOT_CONTRACT = "chummer-hub.core-runtime-package-byte-snapshot/v1"
SELECTOR_CONTRACT = "github-actions.immutable-artifact-selector/v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
EXPECTED_PACKAGE_IDS = (
    "Chummer.Engine.Contracts",
    "Chummer.Application",
    "Chummer.Rulesets.Hosting",
    "Chummer.Rulesets.Sr5",
    "Chummer.Rulesets.Sr6",
    "Chummer.Infrastructure",
    "Chummer.Rulesets.Sr4",
    "Chummer.Engine.GmCharacterEdits",
)

ENVELOPE_KEYS = {"contract", "producer", "archive", "validator_authority"}
PRODUCER_KEYS = {
    "repository",
    "repository_id",
    "workflow_id",
    "workflow_name",
    "workflow_path",
    "run_id",
    "run_attempt",
    "event",
    "branch",
    "head_commit",
    "recipe_tree",
    "artifact_id",
    "artifact_name",
    "artifact_sha256",
    "artifact_size_bytes",
}
ARCHIVE_KEYS = {
    "member_count",
    "uncompressed_size_bytes",
    "file_mode",
    "directory_mode",
    "zip_create_system",
    "zip_create_version",
    "zip_extract_version",
    "zip_flag_bits",
    "zip_compression_method",
    "validator_byte_snapshot_sha256",
    "members",
}
MEMBER_KEYS = {"path", "sha256", "size_bytes"}
WORKSPACE_FILES = {
    "run.json",
    "artifact.json",
    "artifact.zip",
    "validator-authority.json",
    "validation.json",
}


class ConsumerError(RuntimeError):
    """An immutable consumer precondition failed."""


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConsumerError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ConsumerError(f"non-finite JSON constant: {value}")


def _read_json(path: Path, *, label: str, maximum: int = MAX_JSON_BYTES) -> Any:
    try:
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size <= 0
            or metadata.st_size > maximum
        ):
            raise ConsumerError(f"{label} must be one bounded single-link regular file")
        payload = path.read_bytes()
    except OSError as exc:
        raise ConsumerError(f"unable to read {label}") from exc
    if len(payload) != metadata.st_size:
        raise ConsumerError(f"{label} changed while it was read")
    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConsumerError(f"invalid {label} JSON") from exc


def _exact_object(value: Any, keys: set[str], *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ConsumerError(f"{label} fields differ from the exact contract")
    return value


def _string(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or unicodedata.normalize("NFC", value) != value
    ):
        raise ConsumerError(f"{label} must be one canonical string")
    return value


def _positive_integer(value: Any, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConsumerError(f"{label} must be one positive integer")
    return value


def _sha40(value: Any, *, label: str) -> str:
    rendered = _string(value, label=label)
    if SHA40.fullmatch(rendered) is None:
        raise ConsumerError(f"{label} must be one lowercase commit SHA")
    return rendered


def _sha256(value: Any, *, label: str) -> str:
    rendered = _string(value, label=label)
    if SHA256.fullmatch(rendered) is None:
        raise ConsumerError(f"{label} must be one lowercase SHA-256")
    return rendered


def _safe_member_path(value: Any) -> str:
    rendered = _string(value, label="archive member path")
    path = PurePosixPath(rendered)
    if (
        path.is_absolute()
        or "\\" in rendered
        or path.as_posix() != rendered
        or any(part in {"", ".", ".."} for part in path.parts)
        or (len(path.parts) == 2 and path.parts[0] != "packages")
        or len(path.parts) > 2
    ):
        raise ConsumerError(f"unsafe archive member path: {rendered!r}")
    return rendered


def load_authority(path: Path) -> dict[str, Any]:
    authority = _exact_object(
        _read_json(path, label="Core main artifact authority"),
        ENVELOPE_KEYS,
        label="Core main artifact authority",
    )
    if authority["contract"] != AUTHORITY_CONTRACT:
        raise ConsumerError(f"authority contract must be {AUTHORITY_CONTRACT}")
    producer = _exact_object(authority["producer"], PRODUCER_KEYS, label="producer")
    archive = _exact_object(authority["archive"], ARCHIVE_KEYS, label="archive")
    for key in ("repository", "workflow_name", "workflow_path", "event", "branch", "artifact_name"):
        _string(producer[key], label=f"producer.{key}")
    for key in (
        "repository_id",
        "workflow_id",
        "run_id",
        "run_attempt",
        "artifact_id",
        "artifact_size_bytes",
    ):
        _positive_integer(producer[key], label=f"producer.{key}")
    _sha40(producer["head_commit"], label="producer.head_commit")
    _sha40(producer["recipe_tree"], label="producer.recipe_tree")
    _sha256(producer["artifact_sha256"], label="producer.artifact_sha256")
    if producer["event"] != "push" or producer["branch"] != "main":
        raise ConsumerError("producer must be one push run on main")

    if (
        archive["member_count"] != 11
        or archive["file_mode"] != 0o644
        or archive["directory_mode"] != 0o755
        or archive["zip_create_system"] != 3
        or archive["zip_create_version"] != 45
        or archive["zip_extract_version"] != 20
        or archive["zip_flag_bits"] != 8
        or archive["zip_compression_method"] != zipfile.ZIP_STORED
    ):
        raise ConsumerError("archive count, mode, or ZIP metadata authority differs")
    _positive_integer(archive["uncompressed_size_bytes"], label="archive size")
    _sha256(
        archive["validator_byte_snapshot_sha256"],
        label="archive.validator_byte_snapshot_sha256",
    )
    member_values = archive["members"]
    if not isinstance(member_values, list) or len(member_values) != 11:
        raise ConsumerError("archive must contain exactly eleven member rows")
    paths: list[str] = []
    total_size = 0
    for index, value in enumerate(member_values):
        row = _exact_object(value, MEMBER_KEYS, label=f"archive.members[{index}]")
        paths.append(_safe_member_path(row["path"]))
        _sha256(row["sha256"], label=f"archive.members[{index}].sha256")
        total_size += _positive_integer(
            row["size_bytes"], label=f"archive.members[{index}].size_bytes"
        )
    if len(paths) != len(set(paths)) or len(paths) != len(set(path.casefold() for path in paths)):
        raise ConsumerError("archive member paths must be exactly unique")
    if total_size != archive["uncompressed_size_bytes"]:
        raise ConsumerError("archive uncompressed byte authority differs")
    if len([path for path in paths if path.startswith("packages/")]) != 8:
        raise ConsumerError("archive must contain exactly eight package members")

    validator = authority["validator_authority"]
    if not isinstance(validator, dict) or validator.get("contract") != (
        "chummer-hub.core-runtime-package-artifact-authority/v2"
    ):
        raise ConsumerError("embedded validator authority contract differs")
    selector = validator.get("artifact_selector")
    expected_selector = {
        "repository": f"https://github.com/{producer['repository']}.git",
        "workflow_run_id": producer["run_id"],
        "artifact_id": producer["artifact_id"],
        "name": producer["artifact_name"],
        "sha256": producer["artifact_sha256"],
    }
    if selector != expected_selector:
        raise ConsumerError("embedded validator selector differs from producer")
    if validator.get("package_recipe_commit") != producer["head_commit"]:
        raise ConsumerError("validator recipe commit differs from producer")
    expected_package_paths = {
        f"packages/{package_id}.{validator.get('runtime_package_version')}.nupkg"
        for package_id in EXPECTED_PACKAGE_IDS
    }
    if {path for path in paths if path.startswith("packages/")} != expected_package_paths:
        raise ConsumerError("archive package paths differ from exact runtime authority")
    member_by_path = {row["path"]: row for row in member_values}
    for binding, path_key in (
        (validator.get("runtime_package_plane_lock"), "runtime-package-plane.lock.json"),
        (validator.get("inventory"), "chummer-core-runtime-packages.inventory.json"),
        (validator.get("receipt"), "no-siblings.v3.receipt.json"),
    ):
        if not isinstance(binding, dict) or binding.get("sha256") != member_by_path[path_key]["sha256"]:
            raise ConsumerError(f"validator byte binding differs for {path_key}")
    return authority


def validate_api_metadata(
    authority: Mapping[str, Any], run: Any, artifact: Any
) -> None:
    producer = authority["producer"]
    if not isinstance(run, dict) or {
        "id": run.get("id"),
        "run_attempt": run.get("run_attempt"),
        "event": run.get("event"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "head_branch": run.get("head_branch"),
        "head_sha": run.get("head_sha"),
        "name": run.get("name"),
        "path": run.get("path"),
        "workflow_id": run.get("workflow_id"),
        "repository": (run.get("repository") or {}).get("full_name"),
        "head_repository": (run.get("head_repository") or {}).get("full_name"),
        "pull_requests": run.get("pull_requests"),
        "head_commit_id": (run.get("head_commit") or {}).get("id"),
        "head_tree_id": (run.get("head_commit") or {}).get("tree_id"),
    } != {
        "id": producer["run_id"],
        "run_attempt": producer["run_attempt"],
        "event": producer["event"],
        "status": "completed",
        "conclusion": "success",
        "head_branch": producer["branch"],
        "head_sha": producer["head_commit"],
        "name": producer["workflow_name"],
        "path": producer["workflow_path"],
        "workflow_id": producer["workflow_id"],
        "repository": producer["repository"],
        "head_repository": producer["repository"],
        "pull_requests": [],
        "head_commit_id": producer["head_commit"],
        "head_tree_id": producer["recipe_tree"],
    }:
        raise ConsumerError("workflow run metadata differs from immutable authority")

    workflow_run = artifact.get("workflow_run") if isinstance(artifact, dict) else None
    observed_artifact = {
        "id": artifact.get("id") if isinstance(artifact, dict) else None,
        "name": artifact.get("name") if isinstance(artifact, dict) else None,
        "size_in_bytes": artifact.get("size_in_bytes") if isinstance(artifact, dict) else None,
        "digest": artifact.get("digest") if isinstance(artifact, dict) else None,
        "expired": artifact.get("expired") if isinstance(artifact, dict) else None,
        "archive_download_url": (
            artifact.get("archive_download_url") if isinstance(artifact, dict) else None
        ),
        "workflow_run_id": (
            workflow_run.get("id") if isinstance(workflow_run, dict) else None
        ),
        "workflow_head_branch": (
            workflow_run.get("head_branch") if isinstance(workflow_run, dict) else None
        ),
        "workflow_head_sha": (
            workflow_run.get("head_sha") if isinstance(workflow_run, dict) else None
        ),
        "workflow_repository_id": (
            workflow_run.get("repository_id") if isinstance(workflow_run, dict) else None
        ),
        "workflow_head_repository_id": (
            workflow_run.get("head_repository_id")
            if isinstance(workflow_run, dict)
            else None
        ),
    }
    expected_artifact = {
        "id": producer["artifact_id"],
        "name": producer["artifact_name"],
        "size_in_bytes": producer["artifact_size_bytes"],
        "digest": f"sha256:{producer['artifact_sha256']}",
        "expired": False,
        "archive_download_url": (
            f"https://api.github.com/repos/{producer['repository']}/actions/"
            f"artifacts/{producer['artifact_id']}/zip"
        ),
        "workflow_run_id": producer["run_id"],
        "workflow_head_branch": producer["branch"],
        "workflow_head_sha": producer["head_commit"],
        "workflow_repository_id": producer["repository_id"],
        "workflow_head_repository_id": producer["repository_id"],
    }
    if observed_artifact != expected_artifact:
        raise ConsumerError("artifact API metadata differs from immutable authority")


def _require_private_workspace(runner_temp: Path, workspace: Path) -> None:
    if not runner_temp.is_absolute() or not workspace.is_absolute():
        raise ConsumerError("runner temp and workspace must be absolute")
    if workspace.parent != runner_temp or not workspace.name.startswith("core-main-runtime."):
        raise ConsumerError("workspace is outside the fixed runner-temp namespace")
    try:
        metadata = workspace.lstat()
    except OSError as exc:
        raise ConsumerError("workspace is unavailable") from exc
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ConsumerError("workspace must be one real directory")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise ConsumerError("workspace mode must be 0700")


def _hash_file(path: Path, *, expected_size: int) -> str:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        path_before = path.lstat()
        descriptor = os.open(path, flags)
        opened_before = os.fstat(descriptor)

        def identity(value: os.stat_result) -> tuple[int, ...]:
            return (
                value.st_dev,
                value.st_ino,
                value.st_mode,
                value.st_nlink,
                value.st_size,
                value.st_mtime_ns,
                value.st_ctime_ns,
            )

        if (
            not stat.S_ISREG(path_before.st_mode)
            or not stat.S_ISREG(opened_before.st_mode)
            or path_before.st_nlink != 1
            or opened_before.st_nlink != 1
            or opened_before.st_size != expected_size
            or opened_before.st_size > MAX_ARCHIVE_BYTES
            or stat.S_IMODE(opened_before.st_mode) != 0o600
            or identity(path_before) != identity(opened_before)
        ):
            raise ConsumerError("downloaded archive identity, size, or mode differs")
        digest = hashlib.sha256()
        size = 0
        while size <= expected_size:
            chunk = os.read(descriptor, min(1024 * 1024, expected_size + 1 - size))
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        opened_after = os.fstat(descriptor)
        path_after = path.lstat()
    except ConsumerError:
        raise
    except OSError as exc:
        raise ConsumerError("unable to read downloaded archive stably") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if (
        size != expected_size
        or identity(opened_before) != identity(opened_after)
        or identity(opened_before) != identity(path_after)
    ):
        raise ConsumerError("downloaded archive changed while it was read")
    return digest.hexdigest()


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise ConsumerError("short write while extracting immutable ZIP member")
        view = view[written:]


def _write_json_exclusive(path: Path, payload: Any, *, mode: int) -> None:
    rendered = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, mode)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def prepare(
    authority_path: Path,
    run_metadata_path: Path,
    artifact_metadata_path: Path,
    archive_path: Path,
    runner_temp: Path,
    workspace: Path,
    export_root: Path,
    validator_authority_path: Path,
) -> None:
    authority = load_authority(authority_path)
    _require_private_workspace(runner_temp, workspace)
    if export_root.parent != workspace or validator_authority_path.parent != workspace:
        raise ConsumerError("consumer outputs must remain inside the private workspace")
    if export_root.exists() or validator_authority_path.exists():
        raise ConsumerError("consumer outputs must not already exist")
    run = _read_json(run_metadata_path, label="workflow run metadata")
    artifact = _read_json(artifact_metadata_path, label="artifact metadata")
    validate_api_metadata(authority, run, artifact)
    producer = authority["producer"]
    archive_authority = authority["archive"]
    if _hash_file(
        archive_path, expected_size=producer["artifact_size_bytes"]
    ) != producer["artifact_sha256"]:
        raise ConsumerError("downloaded archive SHA-256 differs from authority")

    rows = archive_authority["members"]
    expected_paths = [row["path"] for row in rows]
    expected_by_path = {row["path"]: row for row in rows}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            observed_paths = [info.filename for info in infos]
            if (
                archive.comment != b""
                or archive.start_dir <= 0
                or archive.start_dir >= producer["artifact_size_bytes"]
            ):
                raise ConsumerError("ZIP central-directory envelope differs")
            if observed_paths != expected_paths:
                raise ConsumerError("ZIP members or order differ from exact authority")
            if len(observed_paths) != len(set(observed_paths)) or len(observed_paths) != len(
                set(path.casefold() for path in observed_paths)
            ):
                raise ConsumerError("ZIP contains duplicate or case-colliding members")
            header_offsets: list[int] = []
            observed_uncompressed_size = 0
            for info in infos:
                path = _safe_member_path(info.filename)
                row = expected_by_path[path]
                unix_mode = info.external_attr >> 16
                header_offsets.append(info.header_offset)
                observed_uncompressed_size += info.file_size
                if (
                    info.is_dir()
                    or info.create_system != archive_authority["zip_create_system"]
                    or info.create_version != archive_authority["zip_create_version"]
                    or info.extract_version != archive_authority["zip_extract_version"]
                    or stat.S_IFMT(unix_mode) != stat.S_IFREG
                    or stat.S_IMODE(unix_mode) != archive_authority["file_mode"]
                    or info.compress_type != archive_authority["zip_compression_method"]
                    or info.flag_bits != archive_authority["zip_flag_bits"]
                    or info.extra != b""
                    or info.comment != b""
                    or info.internal_attr != 0
                    or info.volume != 0
                    or info.header_offset < 0
                    or info.header_offset >= archive.start_dir
                    or info.file_size != row["size_bytes"]
                    or info.compress_size != row["size_bytes"]
                ):
                    raise ConsumerError(f"ZIP member metadata differs for {path}")
            if (
                header_offsets != sorted(set(header_offsets))
                or observed_uncompressed_size != archive_authority["uncompressed_size_bytes"]
            ):
                raise ConsumerError("ZIP central-directory offsets or aggregate bytes differ")

            os.mkdir(export_root, mode=0o700)
            os.chmod(export_root, 0o700)
            packages_root = export_root / "packages"
            os.mkdir(packages_root, mode=archive_authority["directory_mode"])
            os.chmod(packages_root, archive_authority["directory_mode"])
            for info in infos:
                row = expected_by_path[info.filename]
                relative = PurePosixPath(info.filename)
                destination = export_root / Path(*relative.parts)
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(destination, flags, archive_authority["file_mode"])
                digest = hashlib.sha256()
                size = 0
                try:
                    os.fchmod(descriptor, archive_authority["file_mode"])
                    with archive.open(info, "r") as source:
                        while size <= row["size_bytes"]:
                            chunk = source.read(
                                min(1024 * 1024, row["size_bytes"] + 1 - size)
                            )
                            if not chunk:
                                break
                            _write_all(descriptor, chunk)
                            digest.update(chunk)
                            size += len(chunk)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                metadata = destination.lstat()
                if (
                    size != row["size_bytes"]
                    or digest.hexdigest() != row["sha256"]
                    or not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_nlink != 1
                    or metadata.st_size != row["size_bytes"]
                    or stat.S_IMODE(metadata.st_mode) != archive_authority["file_mode"]
                ):
                    raise ConsumerError(f"extracted member bytes differ for {info.filename}")
            if archive.testzip() is not None:
                raise ConsumerError("ZIP CRC verification failed")
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ConsumerError("unable to validate or extract exact ZIP") from exc
    if stat.S_IMODE(export_root.lstat().st_mode) != 0o700:
        raise ConsumerError("private extraction root mode differs")
    if stat.S_IMODE((export_root / "packages").lstat().st_mode) != (
        archive_authority["directory_mode"]
    ):
        raise ConsumerError("packages directory mode differs")
    _write_json_exclusive(
        validator_authority_path,
        authority["validator_authority"],
        mode=0o600,
    )


def validation_summary(authority: Mapping[str, Any], result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ConsumerError("validator result must be one object")
    producer = authority["producer"]
    validator_authority = authority["validator_authority"]
    contract = result.get("contract")
    if contract != VALIDATION_V3:
        raise ConsumerError("validator result must use the immutable-snapshot v3 contract")
    expected_common = {
        "status": "pass",
        "outer_artifact_selector": validator_authority["artifact_selector"],
        "member_count": 11,
        "package_count": 8,
        "package_recipe_commit": producer["head_commit"],
        "runtime_source_commit": validator_authority["runtime_source_commit"],
    }
    for key, value in expected_common.items():
        if result.get(key) != value:
            raise ConsumerError(f"validator result differs for {key}")
    if result.get("runtime_package_plane_lock") != {
        "contract": "chummer-core.runtime-package-plane-lock/v1",
        "sha256": validator_authority["runtime_package_plane_lock"]["sha256"],
    }:
        raise ConsumerError("validator lock verdict differs")
    if (result.get("inventory") or {}).get("sha256") != validator_authority["inventory"][
        "sha256"
    ]:
        raise ConsumerError("validator inventory verdict differs")
    if (result.get("receipt") or {}).get("sha256") != validator_authority["receipt"][
        "sha256"
    ]:
        raise ConsumerError("validator receipt verdict differs")
    ordered_ids = result.get("ordered_package_ids")
    if ordered_ids != list(EXPECTED_PACKAGE_IDS):
        raise ConsumerError("validator ordered package verdict differs")
    checks = result.get("checks")
    if not isinstance(checks, dict) or not checks or set(checks.values()) != {"pass"}:
        raise ConsumerError("validator checks are not uniformly pass")

    consumption = {
        "contract": SELECTOR_CONTRACT,
        "artifact_id": producer["artifact_id"],
        "sha256": producer["artifact_sha256"],
    }
    summary: dict[str, Any] = {
        "contract": contract,
        "member_count": 11,
        "package_count": 8,
        "ordered_package_ids": ordered_ids,
        "post_validation_consumption_authority": consumption,
    }
    if result.get("post_validation_consumption_authority") != consumption:
        raise ConsumerError("v3 post-validation consumption authority differs")
    snapshot = result.get("artifact_byte_snapshot")
    expected_snapshot = {
        "contract": BYTE_SNAPSHOT_CONTRACT,
        "sha256": authority["archive"]["validator_byte_snapshot_sha256"],
        "member_count": 11,
        "source_path_posture": "not_attested_after_snapshot_capture",
    }
    if not isinstance(snapshot, dict) or snapshot != expected_snapshot:
        raise ConsumerError("v3 immutable artifact byte snapshot differs")
    summary["artifact_byte_snapshot"] = snapshot
    return summary


def _delete_extraction(authority: Mapping[str, Any], export_root: Path) -> None:
    if not os.path.lexists(export_root):
        return
    metadata = export_root.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ConsumerError("refusing to clean a replaced extraction root")
    expected_root = {
        "packages",
        "chummer-core-runtime-packages.inventory.json",
        "no-siblings.v3.receipt.json",
        "runtime-package-plane.lock.json",
    }
    observed_root = {entry.name for entry in os.scandir(export_root)}
    if not observed_root.issubset(expected_root):
        raise ConsumerError("refusing to clean extraction with foreign root members")
    packages_root = export_root / "packages"
    package_names = {
        PurePosixPath(row["path"]).name
        for row in authority["archive"]["members"]
        if row["path"].startswith("packages/")
    }
    if os.path.lexists(packages_root):
        package_metadata = packages_root.lstat()
        if not stat.S_ISDIR(package_metadata.st_mode) or stat.S_ISLNK(package_metadata.st_mode):
            raise ConsumerError("refusing to clean a replaced packages directory")
        observed_packages = {entry.name for entry in os.scandir(packages_root)}
        if not observed_packages.issubset(package_names):
            raise ConsumerError("refusing to clean extraction with foreign packages")
        for name in sorted(observed_packages):
            path = packages_root / name
            if stat.S_ISDIR(path.lstat().st_mode):
                raise ConsumerError("refusing to clean a package directory")
            path.unlink()
        packages_root.rmdir()
    for name in sorted(observed_root - {"packages"}):
        path = export_root / name
        if stat.S_ISDIR(path.lstat().st_mode):
            raise ConsumerError("refusing to clean an unexpected root directory")
        path.unlink()
    export_root.rmdir()


def cleanup(authority_path: Path, runner_temp: Path, workspace: Path) -> None:
    authority = load_authority(authority_path)
    if not os.path.lexists(workspace):
        return
    _require_private_workspace(runner_temp, workspace)
    observed = {entry.name for entry in os.scandir(workspace)}
    if not observed.issubset(WORKSPACE_FILES | {"artifact-root"}):
        raise ConsumerError("refusing to clean a workspace with foreign members")
    _delete_extraction(authority, workspace / "artifact-root")
    for name in sorted(observed - {"artifact-root"}):
        path = workspace / name
        if stat.S_ISDIR(path.lstat().st_mode):
            raise ConsumerError("refusing to clean an unexpected workspace directory")
        path.unlink()
    workspace.rmdir()


def finalize(
    authority_path: Path,
    validation_path: Path,
    runner_temp: Path,
    workspace: Path,
    verdict_path: Path,
) -> None:
    authority = load_authority(authority_path)
    _require_private_workspace(runner_temp, workspace)
    if validation_path.parent != workspace:
        raise ConsumerError("validation result must remain inside the private workspace")
    if verdict_path.parent != runner_temp or verdict_path.exists():
        raise ConsumerError("verdict path must be one fresh runner-temp file")
    result = _read_json(validation_path, label="validator result")
    summary = validation_summary(authority, result)
    producer = authority["producer"]
    verdict = {
        "contract": VERDICT_CONTRACT,
        "status": "pass",
        "producer": {
            key: producer[key]
            for key in (
                "repository",
                "run_id",
                "run_attempt",
                "head_commit",
                "recipe_tree",
                "artifact_id",
                "artifact_name",
                "artifact_sha256",
                "artifact_size_bytes",
            )
        },
        "archive": {
            "member_count": authority["archive"]["member_count"],
            "uncompressed_size_bytes": authority["archive"]["uncompressed_size_bytes"],
        },
        "validation": summary,
    }
    cleanup(authority_path, runner_temp, workspace)
    if os.path.lexists(workspace):
        raise ConsumerError("private artifact workspace survived finalization")
    _write_json_exclusive(verdict_path, verdict, mode=0o600)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--authority", type=Path, required=True)
    prepare_parser.add_argument("--run-metadata", type=Path, required=True)
    prepare_parser.add_argument("--artifact-metadata", type=Path, required=True)
    prepare_parser.add_argument("--archive", type=Path, required=True)
    prepare_parser.add_argument("--runner-temp", type=Path, required=True)
    prepare_parser.add_argument("--workspace", type=Path, required=True)
    prepare_parser.add_argument("--export-root", type=Path, required=True)
    prepare_parser.add_argument("--validator-authority", type=Path, required=True)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--authority", type=Path, required=True)
    finalize_parser.add_argument("--validation", type=Path, required=True)
    finalize_parser.add_argument("--runner-temp", type=Path, required=True)
    finalize_parser.add_argument("--workspace", type=Path, required=True)
    finalize_parser.add_argument("--verdict", type=Path, required=True)
    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--authority", type=Path, required=True)
    cleanup_parser.add_argument("--runner-temp", type=Path, required=True)
    cleanup_parser.add_argument("--workspace", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "prepare":
            prepare(
                args.authority,
                args.run_metadata,
                args.artifact_metadata,
                args.archive,
                args.runner_temp,
                args.workspace,
                args.export_root,
                args.validator_authority,
            )
        elif args.command == "finalize":
            finalize(
                args.authority,
                args.validation,
                args.runner_temp,
                args.workspace,
                args.verdict,
            )
        else:
            cleanup(args.authority, args.runner_temp, args.workspace)
        return 0
    except ConsumerError as exc:
        print(f"core-main-runtime-consumer: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
