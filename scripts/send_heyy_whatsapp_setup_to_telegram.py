#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EA_ENV = Path("/docker/EA/.env")
DEFAULT_OWNER_PRINCIPAL = ""
DEFAULT_FALLBACK_PRINCIPAL = ""


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


def mask_ref(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    if len(digits) <= 4:
        return "***"
    return f"{digits[:2]}***{digits[-2:]}"


def telegram_bot_token(values: dict[str, str]) -> str:
    token = str(values.get("EA_TELEGRAM_BOT_TOKEN") or "").strip()
    if token:
        return token

    default_key = (
        str(values.get("EA_TELEGRAM_DEFAULT_BOT_KEY") or "").strip()
        or str(values.get("EA_TELEGRAM_DEFAULT_BOT_HANDLE") or "").strip()
    )
    registry_raw = str(values.get("EA_TELEGRAM_BOT_REGISTRY_JSON") or "").strip()
    if not default_key or not registry_raw:
        return ""

    try:
        registry = json.loads(registry_raw)
    except json.JSONDecodeError:
        return ""

    if not isinstance(registry, dict):
        return ""

    candidates = [default_key, default_key.lstrip("@")]
    for candidate in candidates:
        entry = registry.get(candidate)
        if isinstance(entry, dict):
            token = str(entry.get("token") or "").strip()
            if token:
                return token
    return ""


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def query_chat_binding(principal_ids: list[str]) -> tuple[str, str] | None:
    quoted = ", ".join(sql_literal(item) for item in principal_ids if item.strip())
    if not quoted:
        return None

    cases = " ".join(
        f"when principal_id = {sql_literal(principal_id)} then {index}"
        for index, principal_id in enumerate(principal_ids)
        if principal_id.strip()
    )
    sql = f"""
select principal_id, external_account_ref
from connector_bindings
where connector_name = 'telegram_identity'
  and status = 'enabled'
  and external_account_ref is not null
  and principal_id in ({quoted})
order by case {cases} else 99 end,
         updated_at desc nulls last,
         created_at desc nulls last
limit 1;
"""
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
                "-F",
                "\t",
                "-c",
                sql,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception:
        return None

    if proc.returncode != 0:
        return None

    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return parts[0].strip(), parts[1].strip()
    return None


def build_message(allowed_recipient: str, blocked_recipient: str) -> str:
    return f"""WA live-send setup needed:

Deep links:
- Meta Apps: https://developers.facebook.com/apps
- WhatsApp Get Started/API Setup docs: https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started
- Access Tokens docs: https://developers.facebook.com/documentation/business-messaging/whatsapp/access-tokens/
- Business System Users: https://business.facebook.com/settings/system-users

1. In Meta WhatsApp Cloud API, get a valid access token for the WhatsApp Business app.
2. Get the phone_number_id for the sending WhatsApp Business number.
3. On the host, run:

cd {ROOT}
export META_WHATSAPP_ACCESS_TOKEN='PASTE_TOKEN_HERE'
export META_WHATSAPP_PHONE_NUMBER_ID='PASTE_PHONE_NUMBER_ID_HERE'
python3 scripts/configure_heyy_whatsapp_meta.py --allowed-recipient '{allowed_recipient}' --blocked-recipient '{blocked_recipient}' --use-ea-db-phone-number-id-if-missing --validate-meta --seed-ea-db --restart-portal --send-test-after-configure

Do not paste the token into Codex/chat. The script validates Meta first, keeps the blocked number blocked, and then sends one live WA test to the allowlisted *{allowed_recipient[-4:]} number."""


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> dict[str, object]:
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"status": "failed", "reason": "telegram_http_error", "http_status": exc.code}
    except Exception as exc:
        return {"status": "failed", "reason": exc.__class__.__name__}

    result = body.get("result") if isinstance(body, dict) else None
    return {
        "status": "sent" if body.get("ok") else "failed",
        "telegram_ok": bool(body.get("ok")),
        "message_id_present": isinstance(result, dict) and result.get("message_id") is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send the Heyy WhatsApp Meta setup command to the configured owner Telegram chat."
    )
    parser.add_argument("--ea-env", default=str(DEFAULT_EA_ENV))
    parser.add_argument("--principal-id", default=DEFAULT_OWNER_PRINCIPAL)
    parser.add_argument("--fallback-principal-id", default=DEFAULT_FALLBACK_PRINCIPAL)
    parser.add_argument("--chat-id", default="")
    parser.add_argument("--allowed-recipient", default="")
    parser.add_argument("--blocked-recipient", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    env_values = load_env_file(Path(args.ea_env))
    token = telegram_bot_token(env_values)
    blockers: list[str] = []
    if not token:
        blockers.append("telegram_bot_token_missing")

    principal_id = str(args.principal_id or "").strip()
    allowed_recipient = str(args.allowed_recipient or "").strip()
    blocked_recipient = str(args.blocked_recipient or "").strip()
    if not allowed_recipient:
        blockers.append("allowed_recipient_missing")
    if not blocked_recipient:
        blockers.append("blocked_recipient_missing")

    chat_id = str(args.chat_id or "").strip()
    if not chat_id:
        binding = query_chat_binding(
            [
                item
                for item in [
                    principal_id,
                    str(args.fallback_principal_id or "").strip(),
                ]
                if item
            ]
        )
        if binding:
            principal_id, chat_id = binding
        else:
            blockers.append("telegram_binding_missing")

    message = "" if blockers else build_message(allowed_recipient, blocked_recipient)
    if blockers:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "blockers": blockers,
                    "principal": principal_id or None,
                    "chat": mask_ref(chat_id),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "principal": principal_id,
                    "chat": mask_ref(chat_id),
                    "message_length": len(message),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    result = send_telegram_message(token, chat_id, message)
    result.update({"principal": principal_id, "chat": mask_ref(chat_id)})
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "sent" else 2


if __name__ == "__main__":
    raise SystemExit(main())
