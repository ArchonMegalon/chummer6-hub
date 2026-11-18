#!/usr/bin/env python3
"""Consume one exact anonymous Core public release and retain only its verdict."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import sys
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


AUTHORITY_CONTRACT = "chummer-hub.core-main-runtime-public-release-authority/v2"
VERDICT_CONTRACT = "chummer-hub.core-main-runtime-public-release-verdict/v2"
VALIDATION_V3 = "chummer-hub.core-runtime-package-artifact-validation/v3"
BYTE_SNAPSHOT_CONTRACT = "chummer-hub.core-runtime-package-byte-snapshot/v1"
SELECTOR_CONTRACT = "github-actions.immutable-artifact-selector/v1"
HANDOFF_CONTRACT = "chummer-core.runtime-package-public-handoff/v2"
HANDOFF_ZIP_CONTRACT = "chummer-core.runtime-package-public-handoff-zip/v1"
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

ENVELOPE_KEYS = {
    "contract",
    "producer",
    "public_release",
    "archive",
    "validator_authority",
}
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
PUBLIC_RELEASE_KEYS = {
    "release_id",
    "tag_name",
    "target_commit",
    "name",
    "body",
    "draft",
    "prerelease",
    "immutable",
    "created_at_utc",
    "published_at_utc",
    "updated_at_utc",
    "release_api_url",
    "release_html_url",
    "tag_api_url",
    "receipt_asset",
    "bundle_asset",
}
RELEASE_ASSET_KEYS = {
    "id",
    "name",
    "label",
    "content_type",
    "state",
    "size_bytes",
    "sha256",
    "created_at_utc",
    "updated_at_utc",
    "api_url",
    "download_url",
}
HANDOFF_KEYS = {
    "contract",
    "repository",
    "ref",
    "commit",
    "release_tag",
    "receipt_asset_name",
    "source_actions_artifact",
    "bundle",
}
HANDOFF_SOURCE_KEYS = {"id", "name", "sha256", "size_bytes", "workflow_run", "authenticated_metadata"}
HANDOFF_WORKFLOW_KEYS = {
    "id",
    "attempt",
    "event",
    "head_branch",
    "head_sha",
    "head_tree",
    "repository",
    "workflow_id",
    "workflow_ref",
    "workflow_sha",
    "attempt_api_url",
}
HANDOFF_METADATA_KEYS = {
    "api_url",
    "archive_download_url",
    "created_at_utc",
    "expires_at_utc",
    "repository_id",
    "head_repository_id",
}
HANDOFF_BUNDLE_KEYS = {
    "contract",
    "asset_name",
    "sha256",
    "size_bytes",
    "member_count",
    "uncompressed_size_bytes",
    "members",
}
WORKSPACE_FILES = {
    "release.json",
    "tag.json",
    "receipt.json",
    "bundle.zip",
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

    release = _exact_object(
        authority["public_release"], PUBLIC_RELEASE_KEYS, label="public_release"
    )
    _positive_integer(release["release_id"], label="public_release.release_id")
    for key in (
        "tag_name",
        "name",
        "body",
        "created_at_utc",
        "published_at_utc",
        "updated_at_utc",
        "release_api_url",
        "release_html_url",
        "tag_api_url",
    ):
        _string(release[key], label=f"public_release.{key}")
    _sha40(release["target_commit"], label="public_release.target_commit")
    if release["target_commit"] != producer["head_commit"]:
        raise ConsumerError("public release target differs from producer commit")
    if release["draft"] is not False or release["prerelease"] is not False:
        raise ConsumerError("public release must be published and non-prerelease")
    # GitHub currently reports releases as mutable. The consumer never upgrades
    # that into an immutability claim; exact IDs and asset digests fail closed.
    if release["immutable"] is not False:
        raise ConsumerError("reviewed public release mutability posture differs")
    expected_tag = f"core-runtime-package-plane-{producer['head_commit']}"
    if release["tag_name"] != expected_tag:
        raise ConsumerError("public release tag does not bind the producer commit")
    repository = producer["repository"]
    expected_release_urls = {
        "release_api_url": (
            f"https://api.github.com/repos/{repository}/releases/{release['release_id']}"
        ),
        "release_html_url": (
            f"https://github.com/{repository}/releases/tag/{release['tag_name']}"
        ),
        "tag_api_url": (
            f"https://api.github.com/repos/{repository}/git/ref/tags/{release['tag_name']}"
        ),
    }
    for key, expected in expected_release_urls.items():
        if release[key] != expected:
            raise ConsumerError(f"public_release.{key} differs from exact repository authority")
    for asset_key, content_type in (
        ("receipt_asset", "application/json"),
        ("bundle_asset", "application/zip"),
    ):
        asset = _exact_object(
            release[asset_key], RELEASE_ASSET_KEYS, label=f"public_release.{asset_key}"
        )
        _positive_integer(asset["id"], label=f"public_release.{asset_key}.id")
        _positive_integer(
            asset["size_bytes"], label=f"public_release.{asset_key}.size_bytes"
        )
        _sha256(asset["sha256"], label=f"public_release.{asset_key}.sha256")
        for key in (
            "name",
            "label",
            "content_type",
            "state",
            "created_at_utc",
            "updated_at_utc",
            "api_url",
            "download_url",
        ):
            _string(asset[key], label=f"public_release.{asset_key}.{key}")
        if asset["content_type"] != content_type or asset["state"] != "uploaded":
            raise ConsumerError(f"public_release.{asset_key} upload metadata differs")
        if asset["api_url"] != (
            f"https://api.github.com/repos/{repository}/releases/assets/{asset['id']}"
        ):
            raise ConsumerError(f"public_release.{asset_key}.api_url differs")
        expected_prefix = (
            f"https://github.com/{repository}/releases/download/{release['tag_name']}/"
        )
        if asset["download_url"] != expected_prefix + asset["name"]:
            raise ConsumerError(f"public_release.{asset_key}.download_url differs")

    if (
        archive["member_count"] != 11
        or archive["file_mode"] != 0o644
        or archive["directory_mode"] != 0o755
        or archive["zip_create_system"] != 3
        or archive["zip_create_version"] != 20
        or archive["zip_extract_version"] != 20
        or archive["zip_flag_bits"] != 0
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
    bundle_asset = release["bundle_asset"]
    if release["receipt_asset"]["size_bytes"] > MAX_JSON_BYTES:
        raise ConsumerError("public handoff receipt exceeds governed JSON bound")
    if bundle_asset["size_bytes"] > MAX_ARCHIVE_BYTES:
        raise ConsumerError("public bundle exceeds governed download bound")

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


def _github_bot_projection(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {key: value.get(key) for key in ("login", "id", "type", "site_admin")}


def _release_asset_projection(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "id": value.get("id"),
        "name": value.get("name"),
        "label": value.get("label"),
        "content_type": value.get("content_type"),
        "state": value.get("state"),
        "size_bytes": value.get("size"),
        "sha256": value.get("digest"),
        "created_at_utc": value.get("created_at"),
        "updated_at_utc": value.get("updated_at"),
        "api_url": value.get("url"),
        "download_url": value.get("browser_download_url"),
    }


def validate_public_release_metadata(
    authority: Mapping[str, Any], release_metadata: Any, tag_metadata: Any, handoff: Any
) -> None:
    """Bind public transport metadata and the producer-signed byte receipt."""

    producer = authority["producer"]
    release = authority["public_release"]
    if not isinstance(release_metadata, dict):
        raise ConsumerError("public release metadata must be one object")
    observed_release = {
        "release_id": release_metadata.get("id"),
        "tag_name": release_metadata.get("tag_name"),
        "target_commit": release_metadata.get("target_commitish"),
        "name": release_metadata.get("name"),
        "body": release_metadata.get("body"),
        "draft": release_metadata.get("draft"),
        "prerelease": release_metadata.get("prerelease"),
        "immutable": release_metadata.get("immutable"),
        "created_at_utc": release_metadata.get("created_at"),
        "published_at_utc": release_metadata.get("published_at"),
        "updated_at_utc": release_metadata.get("updated_at"),
        "release_api_url": release_metadata.get("url"),
        "release_html_url": release_metadata.get("html_url"),
        "tag_api_url": release["tag_api_url"],
    }
    expected_release = {
        key: release[key]
        for key in observed_release
    }
    if observed_release != expected_release:
        raise ConsumerError("public release metadata differs from exact authority")
    expected_bot = {
        "login": "github-actions[bot]",
        "id": 41898282,
        "type": "Bot",
        "site_admin": False,
    }
    if _github_bot_projection(release_metadata.get("author")) != expected_bot:
        raise ConsumerError("public release author differs from GitHub Actions authority")

    assets = release_metadata.get("assets")
    if not isinstance(assets, list) or len(assets) != 2:
        raise ConsumerError("public release must expose exactly the two governed assets")
    observed_by_id: dict[int, Any] = {}
    for value in assets:
        if not isinstance(value, dict) or not isinstance(value.get("id"), int):
            raise ConsumerError("public release contains malformed asset metadata")
        if value["id"] in observed_by_id:
            raise ConsumerError("public release contains a duplicate asset ID")
        observed_by_id[value["id"]] = value
    expected_ids = {
        release["receipt_asset"]["id"],
        release["bundle_asset"]["id"],
    }
    if set(observed_by_id) != expected_ids:
        raise ConsumerError("public release asset IDs differ from exact authority")
    for key in ("receipt_asset", "bundle_asset"):
        expected_asset = release[key]
        observed_asset = observed_by_id[expected_asset["id"]]
        projection = _release_asset_projection(observed_asset)
        if projection["sha256"] != f"sha256:{expected_asset['sha256']}":
            raise ConsumerError(f"public release {key} digest metadata differs")
        projection["sha256"] = expected_asset["sha256"]
        if projection != expected_asset:
            raise ConsumerError(f"public release {key} metadata differs from exact authority")
        if _github_bot_projection(observed_asset.get("uploader")) != expected_bot:
            raise ConsumerError(f"public release {key} uploader differs")

    expected_tag = {
        "ref": f"refs/tags/{release['tag_name']}",
        "url": release["tag_api_url"].replace("/ref/tags/", "/refs/tags/"),
        "object": {
            "type": "commit",
            "sha": release["target_commit"],
            "url": (
                f"https://api.github.com/repos/{producer['repository']}/git/commits/"
                f"{release['target_commit']}"
            ),
        },
    }
    if not isinstance(tag_metadata, dict) or {
        "ref": tag_metadata.get("ref"),
        "url": tag_metadata.get("url"),
        "object": tag_metadata.get("object"),
    } != expected_tag:
        raise ConsumerError("direct release tag does not resolve to the exact producer commit")

    root = _exact_object(handoff, HANDOFF_KEYS, label="public handoff receipt")
    if root["contract"] != HANDOFF_CONTRACT:
        raise ConsumerError(f"public handoff receipt must use {HANDOFF_CONTRACT}")
    if {
        "repository": root["repository"],
        "ref": root["ref"],
        "commit": root["commit"],
        "release_tag": root["release_tag"],
        "receipt_asset_name": root["receipt_asset_name"],
    } != {
        "repository": producer["repository"],
        "ref": "refs/heads/main",
        "commit": producer["head_commit"],
        "release_tag": release["tag_name"],
        "receipt_asset_name": release["receipt_asset"]["name"],
    }:
        raise ConsumerError("public handoff repository, commit, or release binding differs")

    source = _exact_object(
        root["source_actions_artifact"], HANDOFF_SOURCE_KEYS, label="handoff source artifact"
    )
    if {key: source[key] for key in ("id", "name", "sha256", "size_bytes")} != {
        "id": producer["artifact_id"],
        "name": producer["artifact_name"],
        "sha256": producer["artifact_sha256"],
        "size_bytes": producer["artifact_size_bytes"],
    }:
        raise ConsumerError("public handoff source artifact differs from producer authority")
    workflow = _exact_object(
        source["workflow_run"], HANDOFF_WORKFLOW_KEYS, label="handoff workflow run"
    )
    expected_workflow = {
        "id": producer["run_id"],
        "attempt": producer["run_attempt"],
        "event": producer["event"],
        "head_branch": producer["branch"],
        "head_sha": producer["head_commit"],
        "head_tree": producer["recipe_tree"],
        "repository": producer["repository"],
        "workflow_id": producer["workflow_id"],
        "workflow_ref": (
            f"{producer['repository']}/{producer['workflow_path']}@refs/heads/{producer['branch']}"
        ),
        "workflow_sha": producer["head_commit"],
        "attempt_api_url": (
            f"https://api.github.com/repos/{producer['repository']}/actions/runs/"
            f"{producer['run_id']}/attempts/{producer['run_attempt']}"
        ),
    }
    if workflow != expected_workflow:
        raise ConsumerError("public handoff workflow provenance differs from exact authority")
    metadata = _exact_object(
        source["authenticated_metadata"],
        HANDOFF_METADATA_KEYS,
        label="handoff authenticated artifact metadata",
    )
    if {
        "api_url": metadata["api_url"],
        "archive_download_url": metadata["archive_download_url"],
        "repository_id": metadata["repository_id"],
        "head_repository_id": metadata["head_repository_id"],
    } != {
        "api_url": (
            f"https://api.github.com/repos/{producer['repository']}/actions/artifacts/"
            f"{producer['artifact_id']}"
        ),
        "archive_download_url": (
            f"https://api.github.com/repos/{producer['repository']}/actions/artifacts/"
            f"{producer['artifact_id']}/zip"
        ),
        "repository_id": producer["repository_id"],
        "head_repository_id": producer["repository_id"],
    }:
        raise ConsumerError("public handoff authenticated artifact metadata differs")
    _string(metadata["created_at_utc"], label="handoff artifact created_at_utc")
    _string(metadata["expires_at_utc"], label="handoff artifact expires_at_utc")

    bundle = _exact_object(root["bundle"], HANDOFF_BUNDLE_KEYS, label="handoff bundle")
    bundle_asset = release["bundle_asset"]
    if {
        "contract": bundle["contract"],
        "asset_name": bundle["asset_name"],
        "sha256": bundle["sha256"],
        "size_bytes": bundle["size_bytes"],
        "member_count": bundle["member_count"],
        "uncompressed_size_bytes": bundle["uncompressed_size_bytes"],
        "members": bundle["members"],
    } != {
        "contract": HANDOFF_ZIP_CONTRACT,
        "asset_name": bundle_asset["name"],
        "sha256": bundle_asset["sha256"],
        "size_bytes": bundle_asset["size_bytes"],
        "member_count": authority["archive"]["member_count"],
        "uncompressed_size_bytes": authority["archive"]["uncompressed_size_bytes"],
        "members": authority["archive"]["members"],
    }:
        raise ConsumerError("public handoff bundle member authority differs")


def _require_private_paths(runner_temp: Path, workspace: Path) -> None:
    if not runner_temp.is_absolute() or not workspace.is_absolute():
        raise ConsumerError("runner temp and workspace must be absolute")
    if workspace.parent != runner_temp or not workspace.name.startswith("core-main-runtime."):
        raise ConsumerError("workspace is outside the fixed runner-temp namespace")


def _inode_identity(value: os.stat_result) -> tuple[int, int, int]:
    return (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode))


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )


def _open_directory_path(path: Path, *, label: str) -> tuple[int, os.stat_result]:
    descriptor = -1
    try:
        before = path.lstat()
        descriptor = os.open(path, _directory_flags())
        opened = os.fstat(descriptor)
        after = path.lstat()
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise ConsumerError(f"{label} is unavailable") from exc
    if (
        not stat.S_ISDIR(before.st_mode)
        or not stat.S_ISDIR(opened.st_mode)
        or _inode_identity(before) != _inode_identity(opened)
        or _inode_identity(opened) != _inode_identity(after)
    ):
        os.close(descriptor)
        raise ConsumerError(f"{label} must be one stable real directory")
    return descriptor, opened


def _open_directory_at(
    parent_descriptor: int,
    name: str,
    *,
    label: str,
    required_mode: int | None = None,
) -> tuple[int, os.stat_result]:
    descriptor = -1
    try:
        before = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        descriptor = os.open(name, _directory_flags(), dir_fd=parent_descriptor)
        opened = os.fstat(descriptor)
        after = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise ConsumerError(f"{label} is unavailable") from exc
    if (
        not stat.S_ISDIR(before.st_mode)
        or not stat.S_ISDIR(opened.st_mode)
        or _inode_identity(before) != _inode_identity(opened)
        or _inode_identity(opened) != _inode_identity(after)
        or (
            required_mode is not None
            and stat.S_IMODE(opened.st_mode) != required_mode
        )
    ):
        os.close(descriptor)
        raise ConsumerError(f"{label} must be one stable real directory")
    return descriptor, opened


def _open_runner_anchor(
    runner_temp: Path,
) -> tuple[int, os.stat_result, int, os.stat_result]:
    if not runner_temp.is_absolute() or not runner_temp.name:
        raise ConsumerError("runner temp must be one absolute child directory")
    parent_descriptor, parent_metadata = _open_directory_path(
        runner_temp.parent, label="runner-temp parent"
    )
    try:
        runner_descriptor, runner_metadata = _open_directory_at(
            parent_descriptor,
            runner_temp.name,
            label="runner temp",
        )
    except Exception:
        os.close(parent_descriptor)
        raise
    return parent_descriptor, parent_metadata, runner_descriptor, runner_metadata


def _open_workspace_at(
    runner_descriptor: int, workspace: Path
) -> tuple[int, os.stat_result]:
    return _open_directory_at(
        runner_descriptor,
        workspace.name,
        label="workspace",
        required_mode=0o700,
    )


def _assert_directory_entry(
    parent_descriptor: int,
    name: str,
    opened: os.stat_result,
    *,
    label: str,
) -> None:
    try:
        current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except OSError as exc:
        raise ConsumerError(f"{label} path no longer names the opened directory") from exc
    if (
        not stat.S_ISDIR(current.st_mode)
        or _inode_identity(current) != _inode_identity(opened)
    ):
        raise ConsumerError(f"{label} path no longer names the opened directory")


def _require_missing_at(parent_descriptor: int, name: str, *, label: str) -> None:
    try:
        os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ConsumerError(f"unable to inspect {label}") from exc
    raise ConsumerError(f"{label} must not already exist")


def _read_regular_bytes_at(
    parent_descriptor: int,
    name: str,
    *,
    label: str,
    maximum: int,
    expected_size: int | None = None,
    required_mode: int | None = None,
) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        named_before = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        opened_before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(named_before.st_mode)
            or not stat.S_ISREG(opened_before.st_mode)
            or named_before.st_nlink != 1
            or opened_before.st_nlink != 1
            or opened_before.st_size <= 0
            or opened_before.st_size > maximum
            or (
                expected_size is not None
                and opened_before.st_size != expected_size
            )
            or (
                required_mode is not None
                and stat.S_IMODE(opened_before.st_mode) != required_mode
            )
            or _file_identity(named_before) != _file_identity(opened_before)
        ):
            raise ConsumerError(f"{label} identity, size, or mode differs")
        chunks: list[bytes] = []
        total = 0
        while total <= opened_before.st_size:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, opened_before.st_size + 1 - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        opened_after = os.fstat(descriptor)
        named_after = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except ConsumerError:
        raise
    except OSError as exc:
        raise ConsumerError(f"unable to read {label} stably") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if (
        total != opened_before.st_size
        or _file_identity(opened_before) != _file_identity(opened_after)
        or _file_identity(opened_before) != _file_identity(named_after)
    ):
        raise ConsumerError(f"{label} changed while it was read")
    return b"".join(chunks)


def _read_json_at(
    parent_descriptor: int,
    name: str,
    *,
    label: str,
    maximum: int = MAX_JSON_BYTES,
    required_mode: int | None = None,
) -> Any:
    payload = _read_regular_bytes_at(
        parent_descriptor,
        name,
        label=label,
        maximum=maximum,
        required_mode=required_mode,
    )
    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConsumerError(f"invalid {label} JSON") from exc


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise ConsumerError("short write while extracting immutable ZIP member")
        view = view[written:]


def _write_json_exclusive_at(
    parent_descriptor: int,
    name: str,
    payload: Any,
    *,
    mode: int,
) -> None:
    if not name or "/" in name or name in {".", ".."}:
        raise ConsumerError("output name must be one contained basename")
    rendered = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = -1
    opened: os.stat_result | None = None

    def discard_owned_output() -> None:
        if descriptor < 0:
            return
        try:
            current_opened = os.fstat(descriptor)
            current_named = os.stat(
                name, dir_fd=parent_descriptor, follow_symlinks=False
            )
            if _inode_identity(current_opened) == _inode_identity(current_named):
                os.unlink(name, dir_fd=parent_descriptor)
        except OSError:
            pass

    try:
        descriptor = os.open(name, flags, mode, dir_fd=parent_descriptor)
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        opened = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_size != len(rendered)
            or stat.S_IMODE(opened.st_mode) != mode
            or _file_identity(opened) != _file_identity(named)
        ):
            raise ConsumerError("exclusive JSON output changed while it was written")
        os.fsync(parent_descriptor)
    except ConsumerError:
        discard_owned_output()
        raise
    except OSError as exc:
        discard_owned_output()
        raise ConsumerError("unable to write exclusive JSON output") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def prepare(
    authority_path: Path,
    release_metadata_path: Path,
    tag_metadata_path: Path,
    receipt_path: Path,
    bundle_path: Path,
    runner_temp: Path,
    workspace: Path,
    export_root: Path,
    validator_authority_path: Path,
) -> None:
    authority = load_authority(authority_path)
    _require_private_paths(runner_temp, workspace)
    expected_inputs = {
        release_metadata_path: "release.json",
        tag_metadata_path: "tag.json",
        receipt_path: "receipt.json",
        bundle_path: "bundle.zip",
    }
    if any(path.parent != workspace or path.name != name for path, name in expected_inputs.items()):
        raise ConsumerError("consumer inputs must use their fixed private-workspace names")
    if (
        export_root.parent != workspace
        or export_root.name != "artifact-root"
        or validator_authority_path.parent != workspace
        or validator_authority_path.name != "validator-authority.json"
    ):
        raise ConsumerError("consumer outputs must remain inside the private workspace")
    parent_descriptor = runner_descriptor = workspace_descriptor = -1
    export_descriptor = packages_descriptor = -1
    try:
        (
            parent_descriptor,
            _parent_metadata,
            runner_descriptor,
            runner_metadata,
        ) = _open_runner_anchor(runner_temp)
        workspace_descriptor, workspace_metadata = _open_workspace_at(
            runner_descriptor, workspace
        )
        _require_missing_at(
            workspace_descriptor, export_root.name, label="artifact extraction root"
        )
        _require_missing_at(
            workspace_descriptor,
            validator_authority_path.name,
            label="validator authority output",
        )
        release_metadata = _read_json_at(
            workspace_descriptor,
            release_metadata_path.name,
            label="public release metadata",
            required_mode=0o600,
        )
        tag_metadata = _read_json_at(
            workspace_descriptor,
            tag_metadata_path.name,
            label="direct release tag metadata",
            required_mode=0o600,
        )
        release = authority["public_release"]
        receipt_asset = release["receipt_asset"]
        receipt_bytes = _read_regular_bytes_at(
            workspace_descriptor,
            receipt_path.name,
            label="public handoff receipt",
            maximum=MAX_JSON_BYTES,
            expected_size=receipt_asset["size_bytes"],
            required_mode=0o600,
        )
        if hashlib.sha256(receipt_bytes).hexdigest() != receipt_asset["sha256"]:
            raise ConsumerError("public handoff receipt SHA-256 differs from authority")
        try:
            handoff = json.loads(
                receipt_bytes.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConsumerError("invalid public handoff receipt JSON") from exc
        validate_public_release_metadata(
            authority, release_metadata, tag_metadata, handoff
        )
        archive_authority = authority["archive"]
        bundle_asset = release["bundle_asset"]
        archive_bytes = _read_regular_bytes_at(
            workspace_descriptor,
            bundle_path.name,
            label="downloaded public bundle",
            maximum=MAX_ARCHIVE_BYTES,
            expected_size=bundle_asset["size_bytes"],
            required_mode=0o600,
        )
        if hashlib.sha256(archive_bytes).hexdigest() != bundle_asset["sha256"]:
            raise ConsumerError("downloaded public bundle SHA-256 differs from authority")

        rows = archive_authority["members"]
        expected_paths = [row["path"] for row in rows]
        expected_by_path = {row["path"]: row for row in rows}
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            infos = archive.infolist()
            observed_paths = [info.filename for info in infos]
            if (
                archive.comment != b""
                or archive.start_dir <= 0
                or archive.start_dir >= bundle_asset["size_bytes"]
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

            os.mkdir(export_root.name, mode=0o700, dir_fd=workspace_descriptor)
            export_descriptor, export_metadata = _open_directory_at(
                workspace_descriptor,
                export_root.name,
                label="artifact extraction root",
                required_mode=0o700,
            )
            os.mkdir(
                "packages",
                mode=archive_authority["directory_mode"],
                dir_fd=export_descriptor,
            )
            packages_descriptor, packages_metadata = _open_directory_at(
                export_descriptor,
                "packages",
                label="packages directory",
            )
            os.fchmod(packages_descriptor, archive_authority["directory_mode"])
            packages_metadata = os.fstat(packages_descriptor)
            _assert_directory_entry(
                export_descriptor,
                "packages",
                packages_metadata,
                label="packages directory",
            )
            for info in infos:
                row = expected_by_path[info.filename]
                relative = PurePosixPath(info.filename)
                target_descriptor = (
                    packages_descriptor if len(relative.parts) == 2 else export_descriptor
                )
                target_name = relative.name
                flags = (
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                )
                descriptor = os.open(
                    target_name,
                    flags,
                    archive_authority["file_mode"],
                    dir_fd=target_descriptor,
                )
                digest = hashlib.sha256()
                size = 0
                metadata: os.stat_result | None = None
                named_metadata: os.stat_result | None = None
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
                    metadata = os.fstat(descriptor)
                    named_metadata = os.stat(
                        target_name,
                        dir_fd=target_descriptor,
                        follow_symlinks=False,
                    )
                finally:
                    os.close(descriptor)
                if (
                    size != row["size_bytes"]
                    or digest.hexdigest() != row["sha256"]
                    or metadata is None
                    or named_metadata is None
                    or not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_nlink != 1
                    or metadata.st_size != row["size_bytes"]
                    or stat.S_IMODE(metadata.st_mode) != archive_authority["file_mode"]
                    or _file_identity(metadata) != _file_identity(named_metadata)
                ):
                    raise ConsumerError(f"extracted member bytes differ for {info.filename}")
            if archive.testzip() is not None:
                raise ConsumerError("ZIP CRC verification failed")
        _assert_directory_entry(
            export_descriptor, "packages", packages_metadata, label="packages directory"
        )
        _assert_directory_entry(
            workspace_descriptor,
            export_root.name,
            export_metadata,
            label="artifact extraction root",
        )
        _assert_directory_entry(
            runner_descriptor, workspace.name, workspace_metadata, label="workspace"
        )
        _assert_directory_entry(
            parent_descriptor, runner_temp.name, runner_metadata, label="runner temp"
        )
        _write_json_exclusive_at(
            workspace_descriptor,
            validator_authority_path.name,
            authority["validator_authority"],
            mode=0o600,
        )
    except ConsumerError:
        raise
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ConsumerError("unable to validate or extract exact ZIP") from exc
    finally:
        for descriptor in (
            packages_descriptor,
            export_descriptor,
            workspace_descriptor,
            runner_descriptor,
            parent_descriptor,
        ):
            if descriptor >= 0:
                os.close(descriptor)


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


def _scan_names(descriptor: int, *, label: str) -> set[str]:
    try:
        with os.scandir(descriptor) as entries:
            return {entry.name for entry in entries}
    except OSError as exc:
        raise ConsumerError(f"unable to enumerate {label}") from exc


def _entry_metadata_at(
    parent_descriptor: int, name: str, *, label: str
) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConsumerError(f"unable to inspect {label}") from exc


def _unlink_non_directory_at(
    parent_descriptor: int, name: str, *, label: str
) -> None:
    metadata = _entry_metadata_at(parent_descriptor, name, label=label)
    if metadata is None:
        return
    if stat.S_ISDIR(metadata.st_mode):
        raise ConsumerError(f"refusing to clean unexpected directory at {label}")
    try:
        os.unlink(name, dir_fd=parent_descriptor)
    except OSError as exc:
        raise ConsumerError(f"unable to clean {label}") from exc


def _delete_extraction_at(
    authority: Mapping[str, Any], workspace_descriptor: int
) -> None:
    root_metadata = _entry_metadata_at(
        workspace_descriptor, "artifact-root", label="artifact extraction root"
    )
    if root_metadata is None:
        return
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise ConsumerError("refusing to clean a replaced extraction root")
    export_descriptor = packages_descriptor = -1
    expected_root = {
        "packages",
        "chummer-core-runtime-packages.inventory.json",
        "no-siblings.v3.receipt.json",
        "runtime-package-plane.lock.json",
    }
    package_names = {
        PurePosixPath(row["path"]).name
        for row in authority["archive"]["members"]
        if row["path"].startswith("packages/")
    }
    try:
        export_descriptor, opened_root = _open_directory_at(
            workspace_descriptor,
            "artifact-root",
            label="artifact extraction root",
        )
        observed_root = _scan_names(
            export_descriptor, label="artifact extraction root"
        )
        if not observed_root.issubset(expected_root):
            raise ConsumerError("refusing to clean extraction with foreign root members")
        package_metadata = _entry_metadata_at(
            export_descriptor, "packages", label="packages directory"
        )
        if package_metadata is not None:
            if not stat.S_ISDIR(package_metadata.st_mode):
                raise ConsumerError("refusing to clean a replaced packages directory")
            packages_descriptor, opened_packages = _open_directory_at(
                export_descriptor,
                "packages",
                label="packages directory",
            )
            observed_packages = _scan_names(
                packages_descriptor, label="packages directory"
            )
            if not observed_packages.issubset(package_names):
                raise ConsumerError("refusing to clean extraction with foreign packages")
            for name in sorted(observed_packages):
                _unlink_non_directory_at(
                    packages_descriptor, name, label=f"package member {name}"
                )
            if _scan_names(packages_descriptor, label="packages directory"):
                raise ConsumerError("packages directory changed during cleanup")
            _assert_directory_entry(
                export_descriptor,
                "packages",
                opened_packages,
                label="packages directory",
            )
            os.fsync(packages_descriptor)
            os.rmdir("packages", dir_fd=export_descriptor)
            os.close(packages_descriptor)
            packages_descriptor = -1

        observed_root = _scan_names(
            export_descriptor, label="artifact extraction root"
        )
        if not observed_root.issubset(expected_root - {"packages"}):
            raise ConsumerError("extraction root changed during cleanup")
        for name in sorted(observed_root):
            _unlink_non_directory_at(
                export_descriptor, name, label=f"artifact root member {name}"
            )
        if _scan_names(export_descriptor, label="artifact extraction root"):
            raise ConsumerError("artifact extraction root changed during cleanup")
        _assert_directory_entry(
            workspace_descriptor,
            "artifact-root",
            opened_root,
            label="artifact extraction root",
        )
        os.fsync(export_descriptor)
        os.rmdir("artifact-root", dir_fd=workspace_descriptor)
    except ConsumerError:
        raise
    except OSError as exc:
        raise ConsumerError("unable to clean the anchored artifact extraction") from exc
    finally:
        if packages_descriptor >= 0:
            os.close(packages_descriptor)
        if export_descriptor >= 0:
            os.close(export_descriptor)


def _cleanup_workspace_at(
    authority: Mapping[str, Any],
    runner_descriptor: int,
    workspace_name: str,
    workspace_descriptor: int,
    workspace_metadata: os.stat_result,
) -> None:
    observed = _scan_names(workspace_descriptor, label="private artifact workspace")
    if not observed.issubset(WORKSPACE_FILES | {"artifact-root"}):
        raise ConsumerError("refusing to clean a workspace with foreign members")
    _delete_extraction_at(authority, workspace_descriptor)
    observed = _scan_names(workspace_descriptor, label="private artifact workspace")
    if not observed.issubset(WORKSPACE_FILES):
        raise ConsumerError("workspace changed during cleanup")
    for name in sorted(observed):
        _unlink_non_directory_at(
            workspace_descriptor, name, label=f"workspace member {name}"
        )
    if _scan_names(workspace_descriptor, label="private artifact workspace"):
        raise ConsumerError("private artifact workspace changed during cleanup")
    _assert_directory_entry(
        runner_descriptor,
        workspace_name,
        workspace_metadata,
        label="workspace",
    )
    try:
        os.fsync(workspace_descriptor)
        os.rmdir(workspace_name, dir_fd=runner_descriptor)
    except OSError as exc:
        raise ConsumerError("unable to remove the anchored private workspace") from exc


def cleanup(authority_path: Path, runner_temp: Path, workspace: Path) -> None:
    authority = load_authority(authority_path)
    _require_private_paths(runner_temp, workspace)
    parent_descriptor = runner_descriptor = workspace_descriptor = -1
    try:
        (
            parent_descriptor,
            _parent_metadata,
            runner_descriptor,
            _runner_metadata,
        ) = _open_runner_anchor(runner_temp)
        if _entry_metadata_at(
            runner_descriptor, workspace.name, label="workspace"
        ) is None:
            return
        workspace_descriptor, workspace_metadata = _open_workspace_at(
            runner_descriptor, workspace
        )
        _cleanup_workspace_at(
            authority,
            runner_descriptor,
            workspace.name,
            workspace_descriptor,
            workspace_metadata,
        )
    finally:
        for descriptor in (workspace_descriptor, runner_descriptor, parent_descriptor):
            if descriptor >= 0:
                os.close(descriptor)


def finalize(
    authority_path: Path,
    validation_path: Path,
    runner_temp: Path,
    workspace: Path,
    verdict_path: Path,
) -> None:
    authority = load_authority(authority_path)
    _require_private_paths(runner_temp, workspace)
    if validation_path.parent != workspace or validation_path.name != "validation.json":
        raise ConsumerError("validation result must remain inside the private workspace")
    if (
        verdict_path.parent != runner_temp
        or verdict_path.name != "core-main-runtime-artifact-verdict.json"
    ):
        raise ConsumerError("verdict path must be one fresh runner-temp file")
    parent_descriptor = runner_descriptor = workspace_descriptor = -1
    verdict_written = False
    try:
        (
            parent_descriptor,
            _parent_metadata,
            runner_descriptor,
            runner_metadata,
        ) = _open_runner_anchor(runner_temp)
        workspace_descriptor, workspace_metadata = _open_workspace_at(
            runner_descriptor, workspace
        )
        _require_missing_at(
            runner_descriptor, verdict_path.name, label="verdict output"
        )
        result = _read_json_at(
            workspace_descriptor, validation_path.name, label="validator result"
        )
        summary = validation_summary(authority, result)
        producer = authority["producer"]
        release = authority["public_release"]
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
            "public_release_transport": {
                "release_id": release["release_id"],
                "tag_name": release["tag_name"],
                "target_commit": release["target_commit"],
                "mutable_at_source": not release["immutable"],
                "receipt_asset": {
                    key: release["receipt_asset"][key]
                    for key in ("id", "name", "sha256", "size_bytes")
                },
                "bundle_asset": {
                    key: release["bundle_asset"][key]
                    for key in ("id", "name", "sha256", "size_bytes")
                },
            },
            "archive": {
                "member_count": authority["archive"]["member_count"],
                "uncompressed_size_bytes": authority["archive"]["uncompressed_size_bytes"],
            },
            "validation": summary,
        }
        _cleanup_workspace_at(
            authority,
            runner_descriptor,
            workspace.name,
            workspace_descriptor,
            workspace_metadata,
        )
        _require_missing_at(
            runner_descriptor, workspace.name, label="private artifact workspace"
        )
        _assert_directory_entry(
            parent_descriptor, runner_temp.name, runner_metadata, label="runner temp"
        )
        _write_json_exclusive_at(
            runner_descriptor, verdict_path.name, verdict, mode=0o600
        )
        verdict_written = True
        _assert_directory_entry(
            parent_descriptor, runner_temp.name, runner_metadata, label="runner temp"
        )
    except Exception:
        if verdict_written:
            try:
                _unlink_non_directory_at(
                    runner_descriptor, verdict_path.name, label="failed verdict output"
                )
            except ConsumerError:
                pass
        raise
    finally:
        for descriptor in (workspace_descriptor, runner_descriptor, parent_descriptor):
            if descriptor >= 0:
                os.close(descriptor)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--authority", type=Path, required=True)
    prepare_parser.add_argument("--release-metadata", type=Path, required=True)
    prepare_parser.add_argument("--tag-metadata", type=Path, required=True)
    prepare_parser.add_argument("--receipt", type=Path, required=True)
    prepare_parser.add_argument("--bundle", type=Path, required=True)
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
                args.release_metadata,
                args.tag_metadata,
                args.receipt,
                args.bundle,
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
