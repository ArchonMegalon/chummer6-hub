#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


WORKSPACE = Path("/docker/chummercomplete")
EA_ROOT = Path("/docker/EA")
RUN_SERVICES = WORKSPACE / "chummer.run-services"
OUT = WORKSPACE / "_completion" / "telegram_promo_delivery"


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a Chummer promo video through EA Telegram delivery.")
    parser.add_argument("video", help="Local video file to send.")
    parser.add_argument("--caption", default="", help="Telegram caption.")
    parser.add_argument("--principal-id", default="", help="Principal id to bind for delivery.")
    parser.add_argument("--chat-id", default="", help="Telegram chat id. Defaults to EA_TELEGRAM_CHAT_ID or the local owner chat.")
    parser.add_argument("--receipt-name", default="", help="Receipt filename under _completion/telegram_promo_delivery.")
    args = parser.parse_args()

    load_env(EA_ROOT / ".env")
    sys.path.insert(0, str(EA_ROOT / "ea"))

    from app.repositories.connector_bindings import InMemoryConnectorBindingRepository
    from app.repositories.tool_registry import InMemoryToolRegistryRepository
    from app.services.telegram_delivery import send_telegram_video_for_principal
    from app.services.tool_runtime import ToolRuntimeService

    video = Path(args.video).resolve()
    if not video.is_file():
        raise SystemExit(f"missing video: {video}")

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
        scope_json={"assistant_surfaces": ["dm"], "delivery": ["video"]},
        status="enabled",
    )
    receipt = send_telegram_video_for_principal(
        runtime,
        principal_id=principal_id,
        video_ref=str(video),
        caption=args.caption,
    )

    OUT.mkdir(parents=True, exist_ok=True)
    receipt_name = str(args.receipt_name or f"{video.stem}.telegram.receipt.json").strip()
    payload = {
        "generated_at_utc": utc_now(),
        "status": "sent",
        "transport": "ea.telegram_delivery.send_telegram_video_for_principal",
        "principal_id": receipt.principal_id,
        "chat_id": receipt.chat_id,
        "bot_key": receipt.bot_key,
        "bot_handle": receipt.bot_handle,
        "message_ids": list(receipt.message_ids),
        "video": str(video),
        "caption": args.caption,
    }
    receipt_path = OUT / receipt_name
    receipt_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(receipt_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
