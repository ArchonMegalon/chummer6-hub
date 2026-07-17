#!/usr/bin/env python3
"""Normalize and attest public-edge release payload permissions.

The public payload is mounted into a container that runs as an unprivileged
user.  Source and atomic-write umasks must therefore not determine whether the
runtime can read the payload.  The reserved state directory is a separate,
private boundary: only its root mode is managed and its contents are never
enumerated or changed by this module.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


PAYLOAD_MODE_CONTRACT_NAME = "chummer.public_edge_payload_modes.v1"
PAYLOAD_MODE_ALGORITHM = "exact-posix-mode-policy-v1"
PAYLOAD_MODE_RECEIPT_BINDING_CONTRACT_NAME = (
    "chummer.public_edge_payload_mode_receipt_binding.v1"
)
PAYLOAD_MODE_ENTRY_BINDING_ALGORITHM = (
    "sha256-canonical-json-sorted-relative-path-kind-mode-v1"
)
PAYLOAD_MODE_EXECUTABLE_POLICY_ALGORITHM = "exact-relative-path-allowlist-v1"
PAYLOAD_DIRECTORY_MODE = 0o755
PAYLOAD_FILE_MODE = 0o644
PAYLOAD_EXECUTABLE_FILE_MODE = 0o755
STATE_ROOT_MODE = 0o700
SPECIAL_PERMISSION_BITS = stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX
PAYLOAD_MODE_RECEIPT_FIELD_ORDER = (
    "contractName",
    "algorithm",
    "status",
    "checks",
    "entryBinding",
    "executablePolicy",
    "stateBoundary",
    "counts",
    "entries",
    "failures",
)
PAYLOAD_MODE_RECEIPT_KEYS = frozenset(PAYLOAD_MODE_RECEIPT_FIELD_ORDER)
PAYLOAD_MODE_NORMALIZATION_KEYS = frozenset({"applied", "changedEntryCount"})


class PayloadModePolicyError(RuntimeError):
    """Raised when a payload tree cannot safely be inspected or normalized."""


@dataclass(frozen=True)
class _PlannedEntry:
    path: Path
    relative_path: str
    kind: str
    actual_mode: int
    expected_mode: int
    device: int
    inode: int
    link_count: int
    state_root: bool = False


def _mode_text(mode: int) -> str:
    return f"{mode:04o}"


def _state_directory_name(value: str) -> str:
    name = str(value or "").strip()
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or Path(name).name != name
    ):
        raise ValueError("state_directory_name must be one safe path component")
    return name


def _executable_relative_paths(
    values: Iterable[str],
    *,
    state_directory_name: str,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("executable_relative_paths must be an iterable of paths")
    normalized: list[str] = []
    for raw_value in values:
        if not isinstance(raw_value, str):
            raise ValueError("executable_relative_paths must contain only strings")
        value = raw_value.strip()
        candidate = PurePosixPath(value)
        if (
            not value
            or value != raw_value
            or value in {".", ".."}
            or value.startswith("/")
            or "\\" in value
            or candidate.as_posix() != value
            or any(part in {"", ".", ".."} for part in candidate.parts)
            or value == state_directory_name
            or value.startswith(f"{state_directory_name}/")
        ):
            raise ValueError(
                "executable_relative_paths must contain safe normalized payload paths"
            )
        normalized.append(value)
    if len(normalized) != len(set(normalized)):
        raise ValueError("executable_relative_paths must not contain duplicates")
    return tuple(sorted(normalized))


def _entry_plan(
    path: Path,
    *,
    relative_path: str,
    state_root: bool = False,
    executable_file: bool = False,
) -> _PlannedEntry:
    try:
        identity = path.lstat()
    except OSError as exc:
        raise PayloadModePolicyError(
            f"unable to inspect public-edge payload entry {relative_path}: {exc}"
        ) from exc

    if stat.S_ISLNK(identity.st_mode):
        raise PayloadModePolicyError(
            f"public-edge payload contains a symlink at {relative_path}"
        )

    actual_mode = stat.S_IMODE(identity.st_mode)
    if stat.S_ISDIR(identity.st_mode):
        kind = "state_directory" if state_root else "directory"
        expected_mode = STATE_ROOT_MODE if state_root else PAYLOAD_DIRECTORY_MODE
    elif stat.S_ISREG(identity.st_mode) and not state_root:
        if identity.st_nlink != 1:
            raise PayloadModePolicyError(
                "public-edge payload contains a hardlinked file at "
                f"{relative_path} (link count {identity.st_nlink})"
            )
        kind = "executable_file" if executable_file else "file"
        expected_mode = (
            PAYLOAD_EXECUTABLE_FILE_MODE
            if executable_file
            else PAYLOAD_FILE_MODE
        )
    else:
        expected = "a directory" if state_root else "a regular file or directory"
        raise PayloadModePolicyError(
            f"public-edge payload entry {relative_path} is non-regular and must be {expected}"
        )

    return _PlannedEntry(
        path=path,
        relative_path=relative_path,
        kind=kind,
        actual_mode=actual_mode,
        expected_mode=expected_mode,
        device=identity.st_dev,
        inode=identity.st_ino,
        link_count=identity.st_nlink,
        state_root=state_root,
    )


def _payload_plan(
    root: Path,
    *,
    state_directory_name: str,
    executable_relative_paths: tuple[str, ...],
) -> list[_PlannedEntry]:
    root = Path(root)
    state_name = _state_directory_name(state_directory_name)
    root_entry = _entry_plan(root, relative_path=".")
    if root_entry.kind != "directory":
        raise PayloadModePolicyError("public-edge payload root must be a directory")

    plan = [root_entry]
    def fail_walk(error: OSError) -> None:
        relative = "."
        if error.filename:
            try:
                relative = Path(error.filename).relative_to(root).as_posix()
            except (TypeError, ValueError):
                relative = "<outside-payload>"
        raise PayloadModePolicyError(
            f"unable to enumerate public-edge payload directory {relative}: {error.strerror or error}"
        ) from error

    for directory_path, directory_names, file_names in os.walk(
        root,
        followlinks=False,
        onerror=fail_walk,
    ):
        directory = Path(directory_path)
        relative_directory = directory.relative_to(root)
        directory_names.sort()
        file_names.sort()

        retained_directories: list[str] = []
        for name in directory_names:
            candidate = directory / name
            relative = (relative_directory / name).as_posix()
            is_state_root = relative_directory == Path(".") and name == state_name
            planned = _entry_plan(
                candidate,
                relative_path=relative,
                state_root=is_state_root,
                executable_file=relative in executable_relative_paths,
            )
            plan.append(planned)
            if not is_state_root:
                retained_directories.append(name)
        directory_names[:] = retained_directories

        for name in file_names:
            candidate = directory / name
            relative = (relative_directory / name).as_posix()
            if relative_directory == Path(".") and name == state_name:
                _entry_plan(candidate, relative_path=relative, state_root=True)
            plan.append(
                _entry_plan(
                    candidate,
                    relative_path=relative,
                    executable_file=relative in executable_relative_paths,
                )
            )

    result = sorted(plan, key=lambda entry: entry.relative_path)
    planned_executables = {
        entry.relative_path for entry in result if entry.kind == "executable_file"
    }
    if planned_executables != set(executable_relative_paths):
        missing_or_nonregular = sorted(set(executable_relative_paths) - planned_executables)
        raise PayloadModePolicyError(
            "executable payload allowlist entries are missing or not regular files: "
            + ", ".join(missing_or_nonregular)
        )
    return result


def _binding_rows_from_plan(plan: list[_PlannedEntry]) -> list[dict[str, str]]:
    return [
        {
            "relativePath": entry.relative_path,
            "kind": entry.kind,
            "mode": _mode_text(entry.actual_mode),
        }
        for entry in plan
    ]


def _binding_sha256(rows: list[dict[str, str]]) -> str:
    payload = json.dumps(
        rows,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_exact_keys(
    value: object,
    expected_keys: frozenset[str],
    *,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PayloadModePolicyError(f"{label} must be an object")
    actual_keys = frozenset(value)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        unknown = sorted(actual_keys - expected_keys)
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unknown:
            details.append("unknown=" + ",".join(unknown))
        raise PayloadModePolicyError(
            f"{label} fields are invalid" + (f" ({'; '.join(details)})" if details else "")
        )
    return value


def _safe_receipt_relative_path(value: str) -> bool:
    if value == ".":
        return True
    candidate = PurePosixPath(value)
    return bool(
        value
        and not value.startswith("/")
        and "\\" not in value
        and candidate.as_posix() == value
        and all(part not in {"", ".", ".."} for part in candidate.parts)
    )


def _receipt(
    plan: list[_PlannedEntry],
    *,
    state_directory_name: str,
    executable_relative_paths: tuple[str, ...],
) -> dict[str, Any]:
    rows = [
        {
            "relativePath": entry.relative_path,
            "kind": entry.kind,
            "modeActual": _mode_text(entry.actual_mode),
            "modeExpected": _mode_text(entry.expected_mode),
            "matches": entry.actual_mode == entry.expected_mode,
            "specialPermissionBitsClear": not bool(
                entry.actual_mode & SPECIAL_PERMISSION_BITS
            ),
        }
        for entry in plan
    ]
    failures = [
        {
            "relativePath": row["relativePath"],
            "kind": row["kind"],
            "modeActual": row["modeActual"],
            "modeExpected": row["modeExpected"],
        }
        for row in rows
        if not row["matches"]
    ]
    state_rows = [entry for entry in plan if entry.state_root]
    if len(state_rows) != 1:
        failures.append(
            {
                "relativePath": state_directory_name,
                "kind": "state_directory",
                "modeActual": None,
                "modeExpected": _mode_text(STATE_ROOT_MODE),
            }
        )
    file_rows = [entry for entry in plan if entry.kind in {"file", "executable_file"}]
    directory_rows = [
        entry for entry in plan if entry.kind in {"directory", "state_directory"}
    ]
    binding_rows = _binding_rows_from_plan(plan)
    special_permission_bits_clear = all(
        not entry.actual_mode & SPECIAL_PERMISSION_BITS for entry in plan
    )
    return {
        "contractName": PAYLOAD_MODE_CONTRACT_NAME,
        "algorithm": PAYLOAD_MODE_ALGORITHM,
        "status": "pass" if not failures else "fail",
        "checks": {
            "exactModes": not failures,
            "specialPermissionBitsClear": special_permission_bits_clear,
        },
        "entryBinding": {
            "algorithm": PAYLOAD_MODE_ENTRY_BINDING_ALGORITHM,
            "rowCount": len(binding_rows),
            "sha256": _binding_sha256(binding_rows),
        },
        "executablePolicy": {
            "algorithm": PAYLOAD_MODE_EXECUTABLE_POLICY_ALGORITHM,
            "relativePaths": list(executable_relative_paths),
        },
        "stateBoundary": {
            "relativePath": state_directory_name,
            "stateRootPresent": bool(state_rows),
            "stateRootModeActual": (
                _mode_text(state_rows[0].actual_mode) if state_rows else None
            ),
            "stateRootModeExpected": _mode_text(STATE_ROOT_MODE),
            "stateRootModeMatches": (
                state_rows[0].actual_mode == STATE_ROOT_MODE if state_rows else False
            ),
            "stateContentsInspected": False,
        },
        "counts": {
            "entryCount": len(plan),
            "directoryCount": len(directory_rows),
            "fileCount": len(file_rows),
            "executableFileCount": sum(
                entry.kind == "executable_file" for entry in file_rows
            ),
            "modeFailureCount": len(failures),
        },
        "entries": rows,
        "failures": failures,
    }


def validate_payload_modes(
    root: Path,
    *,
    state_directory_name: str = "state",
    executable_relative_paths: Iterable[str] = (),
) -> dict[str, Any]:
    """Return a deterministic permission receipt without changing the payload.

    Permission drift is represented by a ``fail`` receipt.  Unsafe tree shapes
    raise ``PayloadModePolicyError`` so callers cannot mistake them for ordinary
    mode drift.  A durable payload must include exactly one top-level private
    state directory; an absent state boundary is represented by a fail receipt.
    """

    state_name = _state_directory_name(state_directory_name)
    executable_paths = _executable_relative_paths(
        executable_relative_paths,
        state_directory_name=state_name,
    )
    return _receipt(
        _payload_plan(
            Path(root),
            state_directory_name=state_name,
            executable_relative_paths=executable_paths,
        ),
        state_directory_name=state_name,
        executable_relative_paths=executable_paths,
    )


def _validated_expected_binding_rows(
    expected_receipt: dict[str, Any],
    *,
    state_directory_name: str,
) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    expected_receipt = _require_exact_keys(
        expected_receipt,
        PAYLOAD_MODE_RECEIPT_KEYS,
        label="expected payload-mode receipt",
    )
    if expected_receipt.get("contractName") != PAYLOAD_MODE_CONTRACT_NAME:
        raise PayloadModePolicyError("expected payload-mode receipt contract is invalid")
    if expected_receipt.get("algorithm") != PAYLOAD_MODE_ALGORITHM:
        raise PayloadModePolicyError("expected payload-mode receipt algorithm is invalid")
    if expected_receipt.get("status") != "pass":
        raise PayloadModePolicyError("expected payload-mode receipt must have pass status")
    checks = _require_exact_keys(
        expected_receipt.get("checks"),
        frozenset({"exactModes", "specialPermissionBitsClear"}),
        label="expected payload-mode receipt checks",
    )
    if (
        checks.get("exactModes") is not True
        or checks.get("specialPermissionBitsClear") is not True
    ):
        raise PayloadModePolicyError("expected payload-mode receipt checks are invalid")

    entries = expected_receipt.get("entries")
    if not isinstance(entries, list) or not entries:
        raise PayloadModePolicyError("expected payload-mode receipt entries are invalid")
    allowed_kind_modes = {
        "directory": "0755",
        "state_directory": "0700",
        "file": "0644",
        "executable_file": "0755",
    }
    rows: list[dict[str, str]] = []
    for entry in entries:
        entry = _require_exact_keys(
            entry,
            frozenset(
                {
                    "relativePath",
                    "kind",
                    "modeActual",
                    "modeExpected",
                    "matches",
                    "specialPermissionBitsClear",
                }
            ),
            label="expected payload-mode receipt entry",
        )
        relative_path = entry.get("relativePath")
        kind = entry.get("kind")
        mode_actual = entry.get("modeActual")
        mode_expected = entry.get("modeExpected")
        if not all(isinstance(value, str) for value in (relative_path, kind, mode_actual, mode_expected)):
            raise PayloadModePolicyError("expected payload-mode receipt entry fields are invalid")
        if not _safe_receipt_relative_path(relative_path):
            raise PayloadModePolicyError(
                "expected payload-mode receipt contains an unsafe relative path"
            )
        if kind not in allowed_kind_modes or mode_expected != allowed_kind_modes[kind]:
            raise PayloadModePolicyError("expected payload-mode receipt contains an invalid kind/mode")
        if (
            mode_actual != mode_expected
            or entry.get("matches") is not True
            or entry.get("specialPermissionBitsClear") is not True
        ):
            raise PayloadModePolicyError("expected payload-mode receipt contains mode drift")
        if relative_path == ".":
            if kind != "directory":
                raise PayloadModePolicyError("expected payload-mode receipt root entry is invalid")
        elif kind == "state_directory":
            if relative_path != state_directory_name:
                raise PayloadModePolicyError("expected payload-mode state boundary is invalid")
        rows.append(
            {
                "relativePath": relative_path,
                "kind": kind,
                "mode": mode_actual,
            }
        )

    relative_paths = [row["relativePath"] for row in rows]
    if relative_paths != sorted(relative_paths) or len(relative_paths) != len(set(relative_paths)):
        raise PayloadModePolicyError(
            "expected payload-mode receipt entries must be uniquely sorted"
        )
    if relative_paths[0] != ".":
        raise PayloadModePolicyError("expected payload-mode receipt must bind the payload root")

    expected_binding = _require_exact_keys(
        expected_receipt.get("entryBinding"),
        frozenset({"algorithm", "rowCount", "sha256"}),
        label="expected payload-mode entry binding",
    )
    if (
        expected_binding.get("algorithm") != PAYLOAD_MODE_ENTRY_BINDING_ALGORITHM
        or type(expected_binding.get("rowCount")) is not int
        or expected_binding.get("rowCount") != len(rows)
        or not isinstance(expected_binding.get("sha256"), str)
        or expected_binding.get("sha256") != _binding_sha256(rows)
    ):
        raise PayloadModePolicyError("expected payload-mode entry binding is invalid")

    counts = _require_exact_keys(
        expected_receipt.get("counts"),
        frozenset(
            {
                "entryCount",
                "directoryCount",
                "fileCount",
                "executableFileCount",
                "modeFailureCount",
            }
        ),
        label="expected payload-mode receipt counts",
    )
    expected_counts = {
        "entryCount": len(rows),
        "directoryCount": sum(
            row["kind"] in {"directory", "state_directory"} for row in rows
        ),
        "fileCount": sum(
            row["kind"] in {"file", "executable_file"} for row in rows
        ),
        "executableFileCount": sum(
            row["kind"] == "executable_file" for row in rows
        ),
        "modeFailureCount": 0,
    }
    if any(type(value) is not int for value in counts.values()) or counts != expected_counts:
        raise PayloadModePolicyError("expected payload-mode receipt counts are invalid")
    executable_policy = _require_exact_keys(
        expected_receipt.get("executablePolicy"),
        frozenset({"algorithm", "relativePaths"}),
        label="expected payload-mode executable policy",
    )
    if (
        executable_policy.get("algorithm")
        != PAYLOAD_MODE_EXECUTABLE_POLICY_ALGORITHM
    ):
        raise PayloadModePolicyError("expected payload-mode executable policy is invalid")
    raw_executable_paths = executable_policy.get("relativePaths")
    if not isinstance(raw_executable_paths, list):
        raise PayloadModePolicyError("expected payload-mode executable allowlist is invalid")
    executable_paths = _executable_relative_paths(
        raw_executable_paths,
        state_directory_name=state_directory_name,
    )
    row_executable_paths = tuple(
        row["relativePath"] for row in rows if row["kind"] == "executable_file"
    )
    if executable_paths != row_executable_paths:
        raise PayloadModePolicyError(
            "expected payload-mode executable allowlist does not match its rows"
        )

    state_rows = [row for row in rows if row["kind"] == "state_directory"]
    if len(state_rows) != 1:
        raise PayloadModePolicyError(
            "expected payload-mode receipt must bind exactly one private state root"
        )
    state_boundary = _require_exact_keys(
        expected_receipt.get("stateBoundary"),
        frozenset(
            {
                "relativePath",
                "stateRootPresent",
                "stateRootModeActual",
                "stateRootModeExpected",
                "stateRootModeMatches",
                "stateContentsInspected",
            }
        ),
        label="expected payload-mode state boundary",
    )
    expected_state_boundary = {
        "relativePath": state_directory_name,
        "stateRootPresent": True,
        "stateRootModeActual": "0700",
        "stateRootModeExpected": "0700",
        "stateRootModeMatches": True,
        "stateContentsInspected": False,
    }
    if (
        type(state_boundary.get("stateRootPresent")) is not bool
        or type(state_boundary.get("stateRootModeMatches")) is not bool
        or type(state_boundary.get("stateContentsInspected")) is not bool
        or state_boundary != expected_state_boundary
    ):
        raise PayloadModePolicyError("expected payload-mode state boundary is invalid")

    failures = expected_receipt.get("failures")
    if not isinstance(failures, list) or failures:
        raise PayloadModePolicyError("expected payload-mode receipt failures must be empty")
    return rows, executable_paths


def canonicalize_payload_mode_receipt(
    receipt: dict[str, Any],
    *,
    state_directory_name: str = "state",
) -> dict[str, Any]:
    """Return the exact authoritative receipt, stripping action-only metadata.

    ``normalize_payload_modes`` adds a ``normalization`` summary for its caller.
    Build-info and other durable authorities must store this canonical form so
    unknown fields cannot be smuggled into the trusted envelope.
    """

    if not isinstance(receipt, dict):
        raise PayloadModePolicyError("payload-mode receipt must be an object")
    allowed_keys = PAYLOAD_MODE_RECEIPT_KEYS | {"normalization"}
    actual_keys = frozenset(receipt)
    if actual_keys not in {PAYLOAD_MODE_RECEIPT_KEYS, allowed_keys}:
        _require_exact_keys(
            receipt,
            allowed_keys if "normalization" in receipt else PAYLOAD_MODE_RECEIPT_KEYS,
            label="payload-mode receipt before canonicalization",
        )
    if "normalization" in receipt:
        normalization = _require_exact_keys(
            receipt.get("normalization"),
            PAYLOAD_MODE_NORMALIZATION_KEYS,
            label="payload-mode normalization metadata",
        )
        if normalization.get("applied") is not True or (
            type(normalization.get("changedEntryCount")) is not int
            or normalization["changedEntryCount"] < 0
        ):
            raise PayloadModePolicyError("payload-mode normalization metadata is invalid")

    canonical = copy.deepcopy(
        {key: receipt[key] for key in PAYLOAD_MODE_RECEIPT_FIELD_ORDER}
    )
    state_name = _state_directory_name(state_directory_name)
    _validated_expected_binding_rows(
        canonical,
        state_directory_name=state_name,
    )
    return canonical


def validate_payload_modes_against_receipt(
    root: Path,
    expected_receipt: dict[str, Any],
    *,
    state_directory_name: str = "state",
) -> dict[str, Any]:
    """Bind the current payload to an earlier passing, exact mode receipt.

    The comparison catches path additions/removals, kind changes, mode changes,
    and lost executable intent.  State children remain outside both receipts.
    """

    state_name = _state_directory_name(state_directory_name)
    expected_rows, executable_paths = _validated_expected_binding_rows(
        expected_receipt,
        state_directory_name=state_name,
    )
    actual_receipt = validate_payload_modes(
        Path(root),
        state_directory_name=state_name,
        executable_relative_paths=executable_paths,
    )
    actual_entries = actual_receipt["entries"]
    actual_rows = [
        {
            "relativePath": entry["relativePath"],
            "kind": entry["kind"],
            "mode": entry["modeActual"],
        }
        for entry in actual_entries
    ]
    expected_sha256 = _binding_sha256(expected_rows)
    actual_sha256 = _binding_sha256(actual_rows)
    exact_rows_match = actual_rows == expected_rows
    current_policy_passes = actual_receipt["status"] == "pass"
    failures: list[str] = []
    if not current_policy_passes:
        failures.append("current_payload_mode_policy_failed")
    if not exact_rows_match:
        failures.append("exact_payload_mode_rows_changed")
    return {
        "contractName": PAYLOAD_MODE_RECEIPT_BINDING_CONTRACT_NAME,
        "algorithm": PAYLOAD_MODE_ENTRY_BINDING_ALGORITHM,
        "status": "pass" if not failures else "fail",
        "checks": {
            "currentPayloadModePolicyPasses": current_policy_passes,
            "exactSortedRelativePathKindModeRowsMatch": exact_rows_match,
            "entryBindingSha256Matches": actual_sha256 == expected_sha256,
        },
        "expected": {
            "entryCount": len(expected_rows),
            "entryBindingSha256": expected_sha256,
        },
        "actual": {
            "entryCount": len(actual_rows),
            "entryBindingSha256": actual_sha256,
        },
        "stateContentsInspected": False,
        "failures": failures,
    }


def _normalize_entry(entry: _PlannedEntry) -> bool:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    if entry.kind in {"directory", "state_directory"}:
        flags |= getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(entry.path, flags)
    except OSError as exc:
        raise PayloadModePolicyError(
            f"unable to open public-edge payload entry {entry.relative_path}: {exc}"
        ) from exc

    try:
        before = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (entry.device, entry.inode):
            raise PayloadModePolicyError(
                f"public-edge payload entry changed during normalization: {entry.relative_path}"
            )
        if entry.kind in {"file", "executable_file"}:
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise PayloadModePolicyError(
                    f"public-edge payload file changed during normalization: {entry.relative_path}"
                )
        elif not stat.S_ISDIR(before.st_mode):
            raise PayloadModePolicyError(
                f"public-edge payload directory changed during normalization: {entry.relative_path}"
            )

        changed = stat.S_IMODE(before.st_mode) != entry.expected_mode
        if changed:
            os.fchmod(descriptor, entry.expected_mode)
        after = os.fstat(descriptor)
        if (
            (after.st_dev, after.st_ino) != (entry.device, entry.inode)
            or stat.S_IMODE(after.st_mode) != entry.expected_mode
        ):
            raise PayloadModePolicyError(
                f"public-edge payload mode normalization did not persist: {entry.relative_path}"
            )
        if entry.kind in {"file", "executable_file"} and after.st_nlink != 1:
            raise PayloadModePolicyError(
                f"public-edge payload file gained a hardlink during normalization: {entry.relative_path}"
            )
        return changed
    finally:
        os.close(descriptor)


def normalize_payload_modes(
    root: Path,
    *,
    state_directory_name: str = "state",
    executable_relative_paths: Iterable[str] = (),
) -> dict[str, Any]:
    """Apply the deterministic payload policy and return its passing receipt.

    The caller must create the single top-level state directory first so this
    normalizer never guesses where durable private state should live.
    """

    state_name = _state_directory_name(state_directory_name)
    executable_paths = _executable_relative_paths(
        executable_relative_paths,
        state_directory_name=state_name,
    )
    plan = _payload_plan(
        Path(root),
        state_directory_name=state_name,
        executable_relative_paths=executable_paths,
    )
    if sum(entry.state_root for entry in plan) != 1:
        raise PayloadModePolicyError(
            "public-edge payload must contain exactly one private state directory"
        )
    changed_count = sum(_normalize_entry(entry) for entry in plan)
    receipt = validate_payload_modes(
        Path(root),
        state_directory_name=state_name,
        executable_relative_paths=executable_paths,
    )
    if receipt["status"] != "pass":
        raise PayloadModePolicyError(
            "public-edge payload permission drift remained after normalization"
        )
    return {
        **receipt,
        "normalization": {
            "applied": True,
            "changedEntryCount": changed_count,
        },
    }
