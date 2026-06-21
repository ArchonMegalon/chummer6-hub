#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = ROOT / ".env"
DEFAULT_PORTAL_SERVICE = "chummer-portal"
DEFAULT_COMPOSE_FILE = ROOT / "docker-compose.public-edge.yml"

ACCESS_TOKEN_ENV_NAMES = (
    "CHUMMER_HEYY_SCAM_CHAT_META_ACCESS_TOKEN",
    "META_WHATSAPP_ACCESS_TOKEN",
    "EA_WHATSAPP_DEFAULT_AUTH_TOKEN",
    "EA_WHATSAPP_API_TOKEN",
)
PHONE_NUMBER_ID_ENV_NAMES = (
    "CHUMMER_HEYY_SCAM_CHAT_META_PHONE_NUMBER_ID",
    "META_WHATSAPP_PHONE_NUMBER_ID",
    "EA_WHATSAPP_DEFAULT_PHONE_NUMBER_ID",
    "EA_HEYY_PHONE_NUMBER_ID",
)


def first_env(names: Iterable[str]) -> tuple[str | None, str | None]:
    for name in names:
        value = str(os.environ.get(name) or "").strip()
        if value:
            return name, value
    return None, None


def load_env_lines(path: Path) -> list[str]:
    return path.read_text(errors="ignore").splitlines() if path.exists() else []


def upsert_env(lines: list[str], updates: dict[str, str]) -> list[str]:
    remaining = dict(updates)
    result: list[str] = []
    for line in lines:
        if "=" not in line or line.strip().startswith("#"):
            result.append(line)
            continue
        key, _value = line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key in remaining:
            result.append(f"{normalized_key}={remaining.pop(normalized_key)}")
        else:
            result.append(line)

    if remaining:
        if result and result[-1].strip():
            result.append("")
        for key in sorted(remaining):
            result.append(f"{key}={remaining[key]}")
    return result


def mask_value(value: str) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 8:
        return "<present>"
    return f"<present:len={len(value)}>"


def phone_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_ea_db_seed_sql(access_token: str, phone_number_id: str, binding_id: str) -> str:
    metadata_patch = {
        "access_token": access_token,
        "phone_number_id": phone_number_id,
        "credential_status": "meta_configured",
        "provider": "meta",
        "status": "business_number_stored",
    }
    channel_metadata_patch = {"send_config_status": "meta_configured"}
    metadata_json = sql_literal(json.dumps(metadata_patch, separators=(",", ":")))
    channel_metadata_json = sql_literal(json.dumps(channel_metadata_patch, separators=(",", ":")))
    binding_literal = sql_literal(binding_id)
    return f"""
update connector_bindings
set auth_metadata_json = coalesce(auth_metadata_json, '{{}}'::jsonb) || {metadata_json}::jsonb,
    updated_at = now()
where binding_id = {binding_literal};

update channel_accounts
set metadata_json = coalesce(metadata_json, '{{}}'::jsonb) || {channel_metadata_json}::jsonb,
    status = 'enabled',
    updated_at = now()
where external_ref in (
    select external_account_ref from connector_bindings where binding_id = {binding_literal}
)
and channel = 'whatsapp';
"""


def read_ea_db_phone_number_id(binding_id: str) -> str:
    sql = (
        "select coalesce(auth_metadata_json ->> 'phone_number_id', '') "
        "from connector_bindings "
        f"where binding_id = {sql_literal(binding_id)} "
        "limit 1;"
    )
    try:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "ea-db",
                "psql",
                "-U",
                "postgres",
                "-d",
                "ea",
                "-t",
                "-A",
                "-c",
                sql,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception:
        return ""

    if proc.returncode != 0:
        return ""
    return proc.stdout.strip().splitlines()[0].strip() if proc.stdout.strip() else ""


def run_ea_db_seed(access_token: str, phone_number_id: str, binding_id: str, dry_run: bool) -> dict[str, object]:
    sql = build_ea_db_seed_sql(access_token, phone_number_id, binding_id)
    if dry_run:
        return {"status": "dry_run", "binding_id": binding_id}

    proc = subprocess.run(
        ["docker", "exec", "-i", "ea-db", "psql", "-U", "postgres", "-d", "ea", "-v", "ON_ERROR_STOP=1"],
        input=sql,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "status": "updated" if proc.returncode == 0 else "failed",
        "binding_id": binding_id,
        "returncode": proc.returncode,
        "stderr_tail": proc.stderr[-500:],
    }


def validate_meta_credentials(access_token: str, phone_number_id: str, graph_version: str) -> dict[str, object]:
    query = urllib.parse.urlencode({"fields": "id,display_phone_number,verified_name"})
    url = f"https://graph.facebook.com/{graph_version.strip() or 'v21.0'}/{urllib.parse.quote(phone_number_id)}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        _ = exc.read()
        return {
            "status": "failed",
            "http_status": exc.code,
            "reason": "meta_validation_http_error",
        }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": exc.__class__.__name__,
        }

    return {
        "status": "passed" if str(payload.get("id") or "") == phone_number_id else "failed",
        "phone_number_id_matched": str(payload.get("id") or "") == phone_number_id,
        "display_phone_number_present": bool(str(payload.get("display_phone_number") or "").strip()),
        "verified_name_present": bool(str(payload.get("verified_name") or "").strip()),
    }


def restart_portal(compose_file: Path, service: str, dry_run: bool) -> dict[str, object]:
    cmd = ["docker", "compose", "-f", str(compose_file), "up", "-d", "--force-recreate", service]
    if dry_run:
        return {"status": "dry_run", "command": cmd}
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    return {
        "status": "restarted" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "stderr_tail": proc.stderr[-500:],
    }


def run_live_test(recipient: str, include_ea_db: bool, dry_run: bool) -> dict[str, object]:
    cmd = [
        "python3",
        str(ROOT / "scripts" / "send_heyy_whatsapp_live_test.py"),
        "--recipient",
        recipient,
    ]
    if include_ea_db:
        cmd.append("--include-ea-db")
    if dry_run:
        cmd.append("--dry-run")

    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {
            "status": "failed",
            "reason": "send_script_output_invalid",
            "stdout_tail": proc.stdout[-500:],
        }

    payload["returncode"] = proc.returncode
    if proc.stderr:
        payload["stderr_tail"] = proc.stderr[-500:]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Configure local Heyy WhatsApp Meta credentials without printing secret values."
    )
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--graph-version", default="v21.0")
    parser.add_argument("--allowed-recipient", default="")
    parser.add_argument("--blocked-recipient", default="")
    parser.add_argument("--seed-ea-db", action="store_true")
    parser.add_argument("--ea-binding-id", default="heyy-whatsapp-business")
    parser.add_argument("--use-ea-db-phone-number-id-if-missing", action="store_true")
    parser.add_argument("--validate-meta", action="store_true")
    parser.add_argument("--restart-portal", action="store_true")
    parser.add_argument("--compose-file", default=str(DEFAULT_COMPOSE_FILE))
    parser.add_argument("--portal-service", default=DEFAULT_PORTAL_SERVICE)
    parser.add_argument("--send-test-after-configure", action="store_true")
    parser.add_argument("--send-test-dry-run", action="store_true")
    parser.add_argument("--include-ea-db-in-send-check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    access_source, access_token = first_env(ACCESS_TOKEN_ENV_NAMES)
    phone_source, phone_number_id = first_env(PHONE_NUMBER_ID_ENV_NAMES)

    if not phone_number_id and args.use_ea_db_phone_number_id_if_missing:
        ea_phone_number_id = read_ea_db_phone_number_id(args.ea_binding_id)
        if ea_phone_number_id:
            phone_source = f"ea-db:{args.ea_binding_id}"
            phone_number_id = ea_phone_number_id

    blockers: list[str] = []
    if not access_token:
        blockers.append("meta_access_token_env_missing")
    if not phone_number_id:
        blockers.append("meta_phone_number_id_env_missing")
        if args.use_ea_db_phone_number_id_if_missing:
            blockers.append("ea_db_phone_number_id_missing")

    if blockers:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "blockers": blockers,
                    "expected_access_token_envs": list(ACCESS_TOKEN_ENV_NAMES),
                    "expected_phone_number_id_envs": list(PHONE_NUMBER_ID_ENV_NAMES),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    assert access_token is not None
    assert phone_number_id is not None
    validation_result = None
    if args.validate_meta:
        if args.dry_run:
            validation_result = {"status": "dry_run"}
        else:
            validation_result = validate_meta_credentials(access_token, phone_number_id, args.graph_version)
            if validation_result.get("status") != "passed":
                print(
                    json.dumps(
                        {
                            "status": "blocked",
                            "blockers": ["meta_validation_failed"],
                            "meta_validation": validation_result,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 2

    updates = {
        "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED": "true",
        "CHUMMER_HEYY_SCAM_CHAT_META_ACCESS_TOKEN": access_token,
        "CHUMMER_HEYY_SCAM_CHAT_META_PHONE_NUMBER_ID": phone_number_id,
        "CHUMMER_HEYY_SCAM_CHAT_META_GRAPH_VERSION": args.graph_version.strip() or "v21.0",
    }
    if args.allowed_recipient.strip():
        updates["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ALLOWED_RECIPIENTS"] = args.allowed_recipient.strip()
    if args.blocked_recipient.strip():
        updates["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_BLOCKED_RECIPIENTS"] = args.blocked_recipient.strip()

    env_path = Path(args.env_file)
    if not args.dry_run:
        env_path.write_text("\n".join(upsert_env(load_env_lines(env_path), updates)) + "\n")

    ea_result = None
    if args.seed_ea_db:
        ea_result = run_ea_db_seed(access_token, phone_number_id, args.ea_binding_id, args.dry_run)

    restart_result = None
    if args.restart_portal:
        restart_result = restart_portal(Path(args.compose_file), args.portal_service, args.dry_run)

    send_result = None
    if args.send_test_after_configure:
        if not args.allowed_recipient.strip():
            send_result = {"status": "blocked", "blockers": ["allowed_recipient_required_for_send_test"]}
        elif restart_result is not None and restart_result.get("status") == "failed":
            send_result = {"status": "blocked", "blockers": ["portal_restart_failed"]}
        else:
            send_result = run_live_test(
                args.allowed_recipient.strip(),
                include_ea_db=args.include_ea_db_in_send_check,
                dry_run=args.dry_run or args.send_test_dry_run,
            )

    print(
        json.dumps(
            {
                "status": "dry_run" if args.dry_run else "configured",
                "env_file": str(env_path),
                "access_token": mask_value(access_token),
                "access_token_source": access_source,
                "phone_number_id": mask_value(phone_number_id),
                "phone_number_id_source": phone_source,
                "allowed_recipient_digits_present": bool(phone_digits(args.allowed_recipient)),
                "blocked_recipient_digits_present": bool(phone_digits(args.blocked_recipient)),
                "meta_validation": validation_result,
                "ea_db": ea_result,
                "restart": restart_result,
                "send_test": send_result,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
