#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any


CONTRACT_NAME = "chummer.origin_provider_account_registry.verification.v1"
REQUIRED_ROLES = ("manuscript", "audio", "visual", "packaging", "audiobookshelf", "telegram")
DISABLED_STATUSES = {"disabled", "revoked", "unavailable", "blocked", "retired"}
FORBIDDEN_VALUE_MARKERS = (
    "Bearer ",
    "Cookie:",
    "secret-token",
    "owner-session-token",
    "secret-session",
    "secret-bearer-session",
    "super-secret",
    "rangersofB5",
    "api:",
    "api.telegram.org/bot",
    "TELEGRAM_BOT_TOKEN=",
    "EA_TELEGRAM_BOT_TOKEN=",
    "UNMIXR_API_KEY=",
    "audiobookshelf_api_token=",
    "telegram_bot_token=",
    "password",
    "apiKey",
    "api_key",
    "token",
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def clean(value: object) -> str:
    return str(value or "").strip()


def values_contain_forbidden_markers(value: object) -> list[str]:
    serialized = json.dumps(value, sort_keys=True)
    return [marker for marker in FORBIDDEN_VALUE_MARKERS if marker in serialized]


def account_alias(account: dict[str, Any]) -> str:
    for key in ("accountAlias", "account_alias", "alias", "id"):
        value = clean(account.get(key))
        if value:
            return value
    return ""


def account_roles(account: dict[str, Any]) -> set[str]:
    roles: set[str] = set()
    for key in ("role", "accountRole", "workspaceRole", "lane"):
        value = clean(account.get(key))
        if value:
            roles.add(value.lower())
    for key in ("roles", "capabilities", "projectAffinity", "project_affinity"):
        values = account.get(key)
        if isinstance(values, list):
            roles.update(clean(item).lower() for item in values if clean(item))
    return roles


def role_matches(account_role_tokens: set[str], required_role: str) -> bool:
    if required_role == "manuscript":
        return bool(account_role_tokens & {"manuscript", "authoring", "premium_authoring", "premium_guided_authoring", "scale_drafting", "drafting", "finishing", "narrative_editions", "runner_memoir"})
    if required_role == "audio":
        return bool(account_role_tokens & {"audio", "audiobook", "narration", "premium_narration", "finishing"})
    if required_role == "audiobookshelf":
        return bool(account_role_tokens & {"audiobookshelf", "ebook_shelf", "audiobook_shelf", "book_share", "share_host"})
    if required_role == "visual":
        return bool(account_role_tokens & {"visual", "scene_render", "scene-render", "video_render", "video-render", "visuals", "magicfit", "origin_visual", "origin_visuals"})
    if required_role == "packaging":
        return bool(account_role_tokens & {"packaging", "package", "book_artifact", "book-artifact", "book_export", "book-export", "ebook", "epub", "pdf", "fliplink", "runbook_press", "runbook-press", "origin_packaging", "origin_package"})
    if required_role == "telegram":
        return bool(account_role_tokens & {"telegram", "telegram_delivery", "telegram_official_bot", "origin_delivery"})
    return required_role in account_role_tokens


def normalize_host(value: object) -> str:
    text = clean(value)
    if not text:
        return ""
    if "://" in text:
        from urllib.parse import urlparse

        parsed = urlparse(text)
        return parsed.hostname or ""
    return text.rstrip("/").rstrip(".").lower()


def account_hosts(account: dict[str, Any]) -> list[str]:
    hosts: list[str] = []
    for key in ("host", "shareHost", "share_host", "baseUrl", "base_url", "url"):
        host = normalize_host(account.get(key))
        if host:
            hosts.append(host)
    for key in ("hosts", "trustedHosts", "trusted_hosts"):
        values = account.get(key)
        if isinstance(values, list):
            hosts.extend(host for host in (normalize_host(item) for item in values) if host)
    return sorted(set(hosts))


def verify(path: Path, *, require_all_roles: bool = False) -> tuple[bool, dict[str, Any]]:
    issues: list[str] = []
    accounts: list[dict[str, Any]] = []
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return False, {
            "contractName": CONTRACT_NAME,
            "status": "blocked",
            "issues": [f"invalid_registry:{exc.__class__.__name__}"],
            "generatedAtUtc": now_iso(),
        }

    raw_accounts = payload.get("accounts") or payload.get("providerAccounts") or payload.get("bookAccounts") or payload.get("originProviderAccounts")
    if not isinstance(raw_accounts, list):
        issues.append("accounts_array_missing")
        raw_accounts = []

    forbidden_markers = values_contain_forbidden_markers(payload)
    for marker in forbidden_markers:
        issues.append(f"forbidden_secret_marker:{marker}")

    role_counts = {role: 0 for role in REQUIRED_ROLES}
    for index, item in enumerate(raw_accounts):
        if not isinstance(item, dict):
            issues.append(f"account_not_object:{index}")
            continue
        alias = account_alias(item)
        roles = account_roles(item)
        status = clean(item.get("status")).lower() or "available"
        enabled = status not in DISABLED_STATUSES
        if not alias:
            issues.append(f"account_alias_missing:{index}")
        if not roles:
            issues.append(f"account_roles_missing:{alias or index}")
        if "audiobookshelf" in roles and enabled and not account_hosts(item):
            issues.append(f"audiobookshelf_host_missing:{alias or index}")
        for role in REQUIRED_ROLES:
            if enabled and role_matches(roles, role):
                role_counts[role] += 1
        accounts.append(
            {
                "alias": alias or f"__missing_alias_{index}__",
                "enabled": enabled,
                "status": status,
                "roles": sorted(roles),
                "hosts": account_hosts(item),
            }
        )

    if require_all_roles:
        for role, count in role_counts.items():
            if count == 0:
                issues.append(f"required_role_missing:{role}")

    receipt = {
        "contractName": CONTRACT_NAME,
        "status": "pass" if not issues else "blocked",
        "generatedAtUtc": now_iso(),
        "registryPath": path.as_posix(),
        "rawSecretValuesStored": False,
        "accountCount": len(accounts),
        "enabledRoleCounts": role_counts,
        "accounts": accounts,
        "issues": issues,
    }
    return not issues, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a redacted Origin provider account registry.")
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-all-roles", action="store_true")
    args = parser.parse_args()
    ok, receipt = verify(args.registry, require_all_roles=args.require_all_roles)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
