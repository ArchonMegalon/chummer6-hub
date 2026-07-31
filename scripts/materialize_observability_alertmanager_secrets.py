#!/usr/bin/env python3
"""Materialize owner-only Alertmanager Telegram files without logging identifiers."""

from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from pathlib import Path


DEFAULT_EA_ENV = Path("/docker/EA/.env")
DEFAULT_OUTPUT_DIR = Path(
    "/docker/fleet/state/chummer-secrets/chummer-observability-alertmanager"
)
MAX_INPUT_BYTES = 1024 * 1024


def read_regular_file(path: Path) -> bytes:
    resolved = path.expanduser().resolve()
    if path.is_symlink():
        raise RuntimeError(f"input is a symlink: {path}")
    with resolved.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_INPUT_BYTES:
            raise RuntimeError(f"input is not a bounded regular file: {path}")
        payload = handle.read(MAX_INPUT_BYTES + 1)
        after = os.fstat(handle.fileno())
    identity = lambda value: (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
    )
    if len(payload) > MAX_INPUT_BYTES or identity(before) != identity(after):
        raise RuntimeError(f"input changed or exceeded its size limit: {path}")
    return payload


def parse_env(raw: bytes) -> dict[str, str]:
    values: dict[str, str] = {}
    for source_line in raw.decode("utf-8").splitlines():
        line = source_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_chat_id(receipt: dict[str, object]) -> str:
    if receipt.get("status") != "sent":
        raise RuntimeError("Telegram source receipt is not sent")
    message_ids = receipt.get("message_ids")
    if not isinstance(message_ids, list) or not message_ids:
        raise RuntimeError("Telegram source receipt has no delivered message reference")
    chat_id = str(receipt.get("chat_id") or "").strip()
    if not chat_id or not chat_id.lstrip("-").isdigit():
        raise RuntimeError("Telegram source receipt has no valid chat binding")
    return chat_id


def atomic_write_secret(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write((value + "\n").encode("utf-8"))
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def materialize(*, ea_env: Path, delivery_receipt: Path, output_dir: Path) -> None:
    environment = parse_env(read_regular_file(ea_env))
    bot_token = str(
        environment.get("EA_TELEGRAM_BOT_TOKEN")
        or environment.get("TELEGRAM_BOT_TOKEN")
        or ""
    ).strip()
    if not bot_token or ":" not in bot_token:
        raise RuntimeError("EA Telegram bot token is unavailable")

    try:
        receipt = json.loads(read_regular_file(delivery_receipt))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Telegram source receipt is invalid JSON") from exc
    if not isinstance(receipt, dict):
        raise RuntimeError("Telegram source receipt must be an object")
    chat_id = resolve_chat_id(receipt)

    atomic_write_secret(output_dir / "telegram-bot-token", bot_token)
    atomic_write_secret(output_dir / "telegram-chat-id", chat_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ea-env", type=Path, default=DEFAULT_EA_ENV)
    parser.add_argument("--delivery-receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    materialize(
        ea_env=args.ea_env,
        delivery_receipt=args.delivery_receipt,
        output_dir=args.output_dir,
    )
    print("observability_alertmanager_secrets:pass")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as exc:
        print(f"observability_alertmanager_secrets:fail reason={exc}", file=os.sys.stderr)
        raise SystemExit(1)
