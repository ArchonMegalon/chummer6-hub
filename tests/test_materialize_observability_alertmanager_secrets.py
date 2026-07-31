from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_observability_alertmanager_secrets.py"


def load_module():
    spec = importlib.util.spec_from_file_location("observability_alertmanager_secrets", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_materializes_owner_only_secret_files_without_copying_receipt(tmp_path: Path) -> None:
    module = load_module()
    environment = tmp_path / "ea.env"
    receipt = tmp_path / "delivery.json"
    output = tmp_path / "secrets"
    environment.write_text("EA_TELEGRAM_BOT_TOKEN=123456:test-token\n", encoding="utf-8")
    receipt.write_text(
        json.dumps(
            {
                "status": "sent",
                "chat_id": "-123456",
                "message_ids": ["message-1"],
            }
        ),
        encoding="utf-8",
    )

    module.materialize(ea_env=environment, delivery_receipt=receipt, output_dir=output)

    assert (output / "telegram-bot-token").read_text(encoding="utf-8") == "123456:test-token\n"
    assert (output / "telegram-chat-id").read_text(encoding="utf-8") == "-123456\n"
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE((output / "telegram-bot-token").stat().st_mode) == 0o600
    assert stat.S_IMODE((output / "telegram-chat-id").stat().st_mode) == 0o600
    assert not (output / receipt.name).exists()


def test_rejects_receipt_without_delivered_message_reference(tmp_path: Path) -> None:
    module = load_module()
    environment = tmp_path / "ea.env"
    receipt = tmp_path / "delivery.json"
    environment.write_text("EA_TELEGRAM_BOT_TOKEN=123456:test-token\n", encoding="utf-8")
    receipt.write_text(
        json.dumps({"status": "sent", "chat_id": "-123456", "message_ids": []}),
        encoding="utf-8",
    )

    try:
        module.materialize(
            ea_env=environment,
            delivery_receipt=receipt,
            output_dir=tmp_path / "secrets",
        )
    except RuntimeError as exc:
        assert "no delivered message reference" in str(exc)
    else:
        raise AssertionError("receipt without delivered message reference was accepted")
