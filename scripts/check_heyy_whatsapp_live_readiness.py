#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = ROOT / ".env"
DEFAULT_CONTAINER = "chummer6-hub-chummer-portal-1"

HEYY_KEYS = (
    "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED",
    "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ALLOWED_RECIPIENTS",
    "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_BLOCKED_RECIPIENTS",
    "CHUMMER_HEYY_SCAM_CHAT_META_ACCESS_TOKEN",
    "CHUMMER_HEYY_SCAM_CHAT_META_PHONE_NUMBER_ID",
    "CHUMMER_HEYY_SCAM_CHAT_META_GRAPH_VERSION",
    "CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL",
    "CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN",
    "CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID",
    "CHUMMER_HEYY_SCAM_CHAT_EA_BINDING_ID",
    "CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID",
)


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_container_env(container: str) -> dict[str, str]:
    try:
        raw = subprocess.check_output(
            ["docker", "inspect", container, "--format", "{{json .Config.Env}}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return {}

    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return {}

    values: dict[str, str] = {}
    for item in items:
        if isinstance(item, str) and "=" in item:
            key, value = item.split("=", 1)
            values[key] = value
    return values


def present(values: dict[str, str], key: str) -> bool:
    return bool(str(values.get(key) or "").strip())


def enabled(values: dict[str, str], key: str) -> bool:
    return str(values.get(key) or "").strip().lower() == "true"


def normalize_phone(value: str | None) -> str | None:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits if len(digits) >= 7 else None


def split_phones(value: str | None) -> set[str]:
    result: set[str] = set()
    for part in str(value or "").replace(";", ",").split(","):
        normalized = normalize_phone(part)
        if normalized:
            result.add(normalized)
    return result


def base_url_is_real(values: dict[str, str]) -> bool:
    base_url = str(values.get("CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL") or "").strip().lower()
    if not base_url:
        return False
    return not any(marker in base_url for marker in ("support-progress-mock", "127.0.0.1", "localhost"))


def inspect_ea_db_binding() -> dict[str, Any]:
    query = (
        "select binding_id, principal_id, connector_name, status, "
        "length(coalesce(nullif(auth_metadata_json ->> 'access_token', ''), '')) > 0 as access_token_present, "
        "length(coalesce(nullif(auth_metadata_json ->> 'phone_number_id', ''), '')) > 0 as phone_number_id_present, "
        "coalesce(auth_metadata_json ->> 'credential_status', '') as credential_status "
        "from connector_bindings "
        "where connector_name ilike '%whatsapp%' or binding_id ilike '%whatsapp%' "
        "order by updated_at desc limit 5;"
    )
    try:
        raw = subprocess.check_output(
            [
                "docker",
                "exec",
                "ea-db",
                "psql",
                "-U",
                "postgres",
                "-d",
                "ea",
                "-t",
                "-A",
                "-F",
                "\t",
                "-c",
                query,
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return {"available": False, "error": exc.__class__.__name__, "bindings": []}

    bindings: list[dict[str, Any]] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) != 7:
            continue
        bindings.append(
            {
                "binding_id": parts[0],
                "principal_id": parts[1],
                "connector_name": parts[2],
                "status": parts[3],
                "access_token_present": parts[4].lower() == "t",
                "phone_number_id_present": parts[5].lower() == "t",
                "credential_status": parts[6],
            }
        )
    return {"available": True, "bindings": bindings}


def build_report(values: dict[str, str], recipient: str | None) -> dict[str, Any]:
    allowed = split_phones(values.get("CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ALLOWED_RECIPIENTS"))
    blocked = split_phones(values.get("CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_BLOCKED_RECIPIENTS"))
    recipient_digits = normalize_phone(recipient)
    meta_ready = (
        enabled(values, "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED")
        and present(values, "CHUMMER_HEYY_SCAM_CHAT_META_ACCESS_TOKEN")
        and present(values, "CHUMMER_HEYY_SCAM_CHAT_META_PHONE_NUMBER_ID")
    )
    ea_ready = (
        enabled(values, "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED")
        and present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN")
        and present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID")
        and (
            present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID")
            or present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_BINDING_ID")
        )
        and base_url_is_real(values)
    )
    recipient_allowed = recipient_digits in allowed if recipient_digits else False
    recipient_blocked = recipient_digits in blocked if recipient_digits else False

    blockers: list[str] = []
    if not enabled(values, "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED"):
        blockers.append("whatsapp_disabled")
    if recipient_digits and not recipient_allowed:
        blockers.append("recipient_not_allowlisted")
    if recipient_digits and recipient_blocked:
        blockers.append("recipient_blocked")
    if not meta_ready and not ea_ready:
        blockers.append("live_provider_unconfigured")
    if not blocked:
        blockers.append("blocked_recipient_list_empty")

    return {
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
        "recipient": {
            "provided": bool(recipient),
            "digits_present": bool(recipient_digits),
            "allowlisted": recipient_allowed,
            "blocked": recipient_blocked,
        },
        "config": {
            "whatsapp_enabled": enabled(values, "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED"),
            "allowed_recipient_count": len(allowed),
            "blocked_recipient_count": len(blocked),
            "meta_access_token_present": present(values, "CHUMMER_HEYY_SCAM_CHAT_META_ACCESS_TOKEN"),
            "meta_phone_number_id_present": present(values, "CHUMMER_HEYY_SCAM_CHAT_META_PHONE_NUMBER_ID"),
            "ea_base_url_real": base_url_is_real(values),
            "ea_api_token_present": present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN"),
            "ea_principal_id_present": present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID"),
            "ea_whatsapp_binding_present": present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID"),
            "ea_generic_binding_present": present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_BINDING_ID"),
        },
        "providers": {
            "meta_ready": meta_ready,
            "ea_ready": ea_ready,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Heyy WhatsApp live-send readiness without printing secrets.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--recipient", default="")
    parser.add_argument("--skip-container", action="store_true")
    parser.add_argument("--include-ea-db", action="store_true")
    args = parser.parse_args()

    env_values = load_env_file(Path(args.env_file))
    container_values = {} if args.skip_container else load_container_env(args.container)
    effective = {**env_values, **{key: value for key, value in container_values.items() if key in HEYY_KEYS}}
    report = build_report(effective, args.recipient)
    report["sources"] = {
        "env_file": str(Path(args.env_file)),
        "env_file_present": Path(args.env_file).exists(),
        "container": None if args.skip_container else args.container,
        "container_env_present": bool(container_values),
    }
    if args.include_ea_db:
        report["ea_db"] = inspect_ea_db_binding()

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
