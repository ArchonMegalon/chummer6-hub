#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


WORKSPACE = Path("/docker/chummercomplete")
EA_ROOT = Path("/docker/EA")
OUT = WORKSPACE / "_completion" / "telegram_text_delivery"


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def text_preview(value: str, limit: int = 220) -> str:
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def resolve_text(*, inline_text: str, text_file: str) -> str:
    if inline_text.strip():
        return inline_text
    file_path = Path(text_file).resolve()
    if not file_path.is_file():
        raise SystemExit(f"missing text file: {file_path}")
    return file_path.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a plain Telegram message through EA delivery.")
    parser.add_argument("--text", default="", help="Message text.")
    parser.add_argument("--text-file", default="", help="Path to a UTF-8 text file to send.")
    parser.add_argument("--principal-id", default="", help="Principal id to bind for delivery.")
    parser.add_argument("--chat-id", default="", help="Telegram chat id. Defaults to EA_TELEGRAM_CHAT_ID or the local owner chat.")
    parser.add_argument("--receipt-name", default="", help="Receipt filename under _completion/telegram_text_delivery.")
    args = parser.parse_args()

    message_text = resolve_text(inline_text=args.text, text_file=args.text_file)
    if not message_text.strip():
        raise SystemExit("telegram_message_text_missing")

    load_env(EA_ROOT / ".env")
    sys.path.insert(0, str(EA_ROOT / "ea"))

    from app.repositories.connector_bindings import InMemoryConnectorBindingRepository
    from app.repositories.tool_registry import InMemoryToolRegistryRepository
    from app.services.telegram_delivery import send_telegram_message_for_principal
    from app.services.tool_runtime import ToolRuntimeService

    principal_id = (
        str(args.principal_id or "").strip()
        or str(os.environ.get("EA_TELEGRAM_DEFAULT_PRINCIPAL_ID") or "").strip()
        or str(os.environ.get("EA_DEFAULT_PRINCIPAL_ID") or "").strip()
        or "local-user"
    )
    chat_id = str(args.chat_id or os.environ.get("EA_TELEGRAM_CHAT_ID") or "1354554303").strip()
    if not chat_id:
        raise SystemExit("telegram_chat_id_missing")

    runtime = ToolRuntimeService(
        tool_registry=InMemoryToolRegistryRepository(),
        connector_bindings=InMemoryConnectorBindingRepository(),
    )
    runtime.upsert_connector_binding(
        principal_id=principal_id,
        connector_name="telegram_identity",
        external_account_ref=chat_id,
        auth_metadata_json={
            "default_chat_ref": chat_id,
            "bot_key": "default",
            "bot_handle": str(os.environ.get("EA_TELEGRAM_BOT_HANDLE") or "").strip(),
        },
        scope_json={"assistant_surfaces": ["dm"], "delivery": ["message"]},
        status="enabled",
    )

    receipt = send_telegram_message_for_principal(
        runtime,
        principal_id=principal_id,
        text=message_text,
    )

    OUT.mkdir(parents=True, exist_ok=True)
    receipt_name = str(args.receipt_name or "telegram-message.receipt.json").strip()
    payload = {
        "generated_at_utc": utc_now(),
        "status": "sent",
        "transport": "ea.telegram_delivery.send_telegram_message_for_principal",
        "principal_id": receipt.principal_id,
        "chat_id": receipt.chat_id,
        "bot_key": receipt.bot_key,
        "bot_handle": receipt.bot_handle,
        "message_ids": list(receipt.message_ids),
        "text_sha256": text_sha256(message_text),
        "text_preview": text_preview(message_text),
    }
    receipt_path = OUT / receipt_name
    receipt_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(receipt_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
