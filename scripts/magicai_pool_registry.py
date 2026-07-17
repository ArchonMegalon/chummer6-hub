from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


DEFAULT_MAGICAI_PLATFORM_AUDIT = Path(".codex-studio/published/MAGICAI_PLATFORM_ACCESS.generated.json")


def env_assignments(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    assignments: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key:
            assignments[key] = value.strip()
    return assignments


def read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_alias(alias: str) -> str:
    normalized = str(alias or "").strip().lower()
    return normalized.zfill(2) if normalized.isdigit() else normalized


def _merged_assignments(*assignment_sets: dict[str, str]) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for source in assignment_sets:
        assignments.update(source)
    return assignments


def _account_env_value(assignments: dict[str, str], alias: str, field: str) -> str:
    candidates = [f"MAGICAI_ACCOUNT_{alias.upper()}_{field}"]
    if alias.isdigit():
        candidates.append(f"MAGICAI_ACCOUNT_{int(alias)}_{field}")
    for key in candidates:
        value = assignments.get(key, "").strip()
        if value:
            return value
    return ""


def magicai_declared_aliases(*assignment_sets: dict[str, str]) -> list[str]:
    assignments = _merged_assignments(*assignment_sets)
    declared: list[str] = []
    if any(
        assignments.get(key, "").strip()
        for key in ("CHUMMER_EA_MAGICAI_EMAIL", "CHUMMER_EA_MAGICAI_PASSWORD", "CHUMMER_EA_MAGICAI_API_KEY")
    ):
        declared.append("primary")
    for key, value in assignments.items():
        if not value.strip():
            continue
        match = re.fullmatch(r"MAGICAI_ACCOUNT_(.+)_(EMAIL|PASSWORD|API_KEY)", key)
        if match:
            declared.append(_normalize_alias(match.group(1)))
    return sorted(set(declared))


def magicai_login_ready_aliases(*assignment_sets: dict[str, str]) -> list[str]:
    assignments = _merged_assignments(*assignment_sets)
    ready: list[str] = []
    if assignments.get("CHUMMER_EA_MAGICAI_EMAIL", "").strip() and assignments.get("CHUMMER_EA_MAGICAI_PASSWORD", "").strip():
        ready.append("primary")
    for alias in magicai_declared_aliases(assignments):
        if alias == "primary":
            continue
        if _account_env_value(assignments, alias, "EMAIL") and _account_env_value(assignments, alias, "PASSWORD"):
            ready.append(alias)
    return sorted(set(ready))


def magicai_api_ready_aliases(*assignment_sets: dict[str, str]) -> list[str]:
    assignments = _merged_assignments(*assignment_sets)
    ready: list[str] = []
    if assignments.get("CHUMMER_EA_MAGICAI_API_KEY", "").strip():
        ready.append("primary")
    for key, value in assignments.items():
        if not value.strip():
            continue
        match = re.fullmatch(r"MAGICAI_ACCOUNT_(.+)_API_KEY", key)
        if match:
            ready.append(_normalize_alias(match.group(1)))
    return sorted(set(ready))


def magicai_api_ready_slots(*assignment_sets: dict[str, str]) -> dict[str, str]:
    assignments = _merged_assignments(*assignment_sets)
    ready: dict[str, str] = {}
    primary_api_key = assignments.get("CHUMMER_EA_MAGICAI_API_KEY", "").strip()
    if primary_api_key:
        ready["primary"] = primary_api_key
    for key, value in assignments.items():
        api_key = value.strip()
        if not api_key:
            continue
        match = re.fullmatch(r"MAGICAI_ACCOUNT_(.+)_API_KEY", key)
        if match:
            ready[_normalize_alias(match.group(1))] = api_key
    return dict(sorted(ready.items()))


def magicai_api_missing_aliases(*assignment_sets: dict[str, str]) -> list[str]:
    login_ready = set(magicai_login_ready_aliases(*assignment_sets))
    api_ready = set(magicai_api_ready_aliases(*assignment_sets))
    return sorted(login_ready - api_ready)


def magicai_pool_counts(*assignment_sets: dict[str, str]) -> dict[str, int]:
    declared_aliases = magicai_declared_aliases(*assignment_sets)
    login_ready_aliases = magicai_login_ready_aliases(*assignment_sets)
    api_ready_aliases = magicai_api_ready_aliases(*assignment_sets)
    missing_aliases = magicai_api_missing_aliases(*assignment_sets)
    return {
        "declared_count": len(declared_aliases),
        "login_ready_count": len(login_ready_aliases),
        "api_key_ready_count": len(api_ready_aliases),
        "pending_api_key_count": len(missing_aliases),
    }


def magicai_platform_audit(
    repo_root: Path,
    *,
    assignment_sets: tuple[dict[str, str], ...] | None = None,
    audit_relative_path: Path = DEFAULT_MAGICAI_PLATFORM_AUDIT,
) -> dict[str, Any]:
    audit_path = repo_root / audit_relative_path
    payload = read_json_object(audit_path)
    empty = {
        "attempted": False,
        "present": False,
        "path": audit_path.as_posix(),
        "sha256": "",
        "checked_at_utc": None,
        "accessible_aliases": [],
        "blocked_aliases": [],
        "login_failed_aliases": [],
        "unverified_aliases": [],
        "accessible_count": 0,
        "blocked_count": 0,
        "login_failed_count": 0,
        "unverified_count": 0,
        "pending_mintable_aliases": [],
        "pending_blocked_aliases": [],
        "pending_login_failed_aliases": [],
        "pending_unverified_aliases": [],
        "pending_mintable_count": 0,
        "pending_blocked_count": 0,
        "pending_login_failed_count": 0,
        "pending_unverified_count": 0,
    }
    if payload is None:
        return empty

    assignments = assignment_sets or (env_assignments(repo_root / ".env"),)
    login_ready = set(magicai_login_ready_aliases(*assignments))
    api_ready = set(magicai_api_ready_aliases(*assignments))

    accessible: set[str] = set()
    blocked: set[str] = set()
    login_failed: set[str] = set()
    unverified: set[str] = set()
    for slot_payload in payload.get("slots", []):
        if not isinstance(slot_payload, dict):
            continue
        alias = _normalize_alias(str(slot_payload.get("slot") or slot_payload.get("alias") or ""))
        if not alias:
            continue
        keys_status = str(slot_payload.get("keys_status") or slot_payload.get("keysStatus") or "").strip().lower()
        logged_in = slot_payload.get("logged_in")
        if keys_status == "ok":
            accessible.add(alias)
        elif keys_status == "forbidden":
            blocked.add(alias)
        elif keys_status == "login_failed" or logged_in is False:
            login_failed.add(alias)
        else:
            unverified.add(alias)

    pending_aliases = login_ready - api_ready
    pending_mintable = sorted(pending_aliases & accessible)
    pending_blocked = sorted(pending_aliases & blocked)
    pending_login_failed = sorted(pending_aliases & login_failed)
    pending_unverified = sorted(pending_aliases & unverified)
    return {
        "attempted": True,
        "present": True,
        "path": audit_path.as_posix(),
        "sha256": sha256_file(audit_path),
        "checked_at_utc": payload.get("checked_at_utc") or payload.get("generated_at_utc"),
        "accessible_aliases": sorted(accessible),
        "blocked_aliases": sorted(blocked),
        "login_failed_aliases": sorted(login_failed),
        "unverified_aliases": sorted(unverified),
        "accessible_count": len(accessible),
        "blocked_count": len(blocked),
        "login_failed_count": len(login_failed),
        "unverified_count": len(unverified),
        "pending_mintable_aliases": pending_mintable,
        "pending_blocked_aliases": pending_blocked,
        "pending_login_failed_aliases": pending_login_failed,
        "pending_unverified_aliases": pending_unverified,
        "pending_mintable_count": len(pending_mintable),
        "pending_blocked_count": len(pending_blocked),
        "pending_login_failed_count": len(pending_login_failed),
        "pending_unverified_count": len(pending_unverified),
    }


def magicai_platform_audit_summary(
    repo_root: Path,
    *,
    assignment_sets: tuple[dict[str, str], ...] | None = None,
    audit_relative_path: Path = DEFAULT_MAGICAI_PLATFORM_AUDIT,
) -> dict[str, Any]:
    audit = magicai_platform_audit(
        repo_root,
        assignment_sets=assignment_sets,
        audit_relative_path=audit_relative_path,
    )
    return {
        "present": audit["present"],
        "path": audit["path"],
        "sha256": audit["sha256"],
        "checkedAtUtc": str(audit["checked_at_utc"] or ""),
        "accessibleAccounts": audit["accessible_aliases"],
        "forbiddenAccounts": audit["blocked_aliases"],
        "loginFailedAccounts": audit["login_failed_aliases"],
        "unverifiedAccounts": audit["unverified_aliases"],
    }
