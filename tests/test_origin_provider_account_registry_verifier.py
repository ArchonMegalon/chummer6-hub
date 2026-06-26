from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_origin_provider_account_registry.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_provider_account_registry_verifier", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def valid_registry() -> dict:
    return {
        "accounts": [
            {
                "accountAlias": "INK01_ORIGIN",
                "provider": "Inkfluence",
                "status": "available",
                "roles": ["manuscript", "origin"],
            },
            {
                "accountAlias": "UNMIXR_TIBOR_01",
                "provider": "Unmixr",
                "status": "available",
                "roles": ["audio", "audiobook", "origin"],
            },
            {
                "accountAlias": "MAGICFIT_ORIGIN_VISUAL_01",
                "provider": "Magicfit",
                "status": "available",
                "roles": ["visual", "scene_render", "origin"],
            },
            {
                "accountAlias": "ABS_ORIGIN_01",
                "provider": "Audiobookshelf",
                "status": "available",
                "roles": ["audiobookshelf", "book_share"],
                "shareHost": "audio.chummer.run",
            },
            {
                "accountAlias": "EA_TELEGRAM_ORIGIN",
                "provider": "Telegram",
                "status": "available",
                "roles": ["telegram", "telegram_delivery", "origin_share"],
            },
        ]
    }


def test_verifier_accepts_redacted_complete_registry(tmp_path: Path) -> None:
    module = load_module()
    registry = write_json(tmp_path / "origin-provider-accounts.json", valid_registry())

    ok, receipt = module.verify(registry, require_all_roles=True)

    assert ok is True
    assert receipt["status"] == "pass"
    assert receipt["rawSecretValuesStored"] is False
    assert receipt["enabledRoleCounts"]["manuscript"] >= 1
    assert receipt["enabledRoleCounts"]["audio"] >= 1
    assert receipt["enabledRoleCounts"]["visual"] >= 1
    assert receipt["enabledRoleCounts"]["audiobookshelf"] >= 1
    assert receipt["enabledRoleCounts"]["telegram"] == 1
    assert "rangersofB5" not in json.dumps(receipt)


def test_verifier_rejects_malformed_registry(tmp_path: Path) -> None:
    module = load_module()
    registry = tmp_path / "origin-provider-accounts.json"
    registry.write_text("{ malformed", encoding="utf-8")

    ok, receipt = module.verify(registry, require_all_roles=True)

    assert ok is False
    assert receipt["status"] == "blocked"
    assert "invalid_registry:JSONDecodeError" in receipt["issues"]


def test_verifier_rejects_secret_bearing_registry(tmp_path: Path) -> None:
    module = load_module()
    payload = valid_registry()
    payload["accounts"][1]["api_key"] = "UNMIXR_API_KEY=leaked"
    payload["accounts"][3]["botToken"] = "https://api.telegram.org/bot123"
    registry = write_json(tmp_path / "origin-provider-accounts.json", payload)

    ok, receipt = module.verify(registry, require_all_roles=True)

    assert ok is False
    assert "forbidden_secret_marker:UNMIXR_API_KEY=" in receipt["issues"]
    assert "forbidden_secret_marker:api.telegram.org/bot" in receipt["issues"]


def test_verifier_rejects_missing_required_roles(tmp_path: Path) -> None:
    module = load_module()
    payload = valid_registry()
    payload["accounts"] = payload["accounts"][:2]
    registry = write_json(tmp_path / "origin-provider-accounts.json", payload)

    ok, receipt = module.verify(registry, require_all_roles=True)

    assert ok is False
    assert "required_role_missing:audiobookshelf" in receipt["issues"]
    assert "required_role_missing:telegram" in receipt["issues"]
    assert "required_role_missing:visual" in receipt["issues"]


def test_verifier_rejects_audiobookshelf_account_without_share_host(tmp_path: Path) -> None:
    module = load_module()
    payload = valid_registry()
    payload["accounts"][3].pop("shareHost")
    registry = write_json(tmp_path / "origin-provider-accounts.json", payload)

    ok, receipt = module.verify(registry, require_all_roles=True)

    assert ok is False
    assert "audiobookshelf_host_missing:ABS_ORIGIN_01" in receipt["issues"]


def test_verifier_rejects_origin_share_only_as_required_delivery_roles(tmp_path: Path) -> None:
    module = load_module()
    payload = valid_registry()
    payload["accounts"][3] = {
        "accountAlias": "ABS_ORIGIN_01",
        "provider": "Audiobookshelf",
        "status": "available",
        "roles": ["origin_share"],
        "shareHost": "audio.chummer.run",
    }
    payload["accounts"][4] = {
        "accountAlias": "EA_TELEGRAM_ORIGIN",
        "provider": "Telegram",
        "status": "available",
        "roles": ["origin_share"],
    }
    registry = write_json(tmp_path / "origin-provider-accounts.json", payload)

    ok, receipt = module.verify(registry, require_all_roles=True)

    assert ok is False
    assert receipt["enabledRoleCounts"]["audiobookshelf"] == 0
    assert receipt["enabledRoleCounts"]["telegram"] == 0
    assert "required_role_missing:audiobookshelf" in receipt["issues"]
    assert "required_role_missing:telegram" in receipt["issues"]


def test_verifier_writes_receipt_without_raw_secret_values(tmp_path: Path) -> None:
    module = load_module()
    registry = write_json(tmp_path / "origin-provider-accounts.json", valid_registry())
    output = tmp_path / "origin-provider-accounts.verification.receipt.json"

    ok, receipt = module.verify(registry, require_all_roles=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    parsed = json.loads(output.read_text(encoding="utf-8"))

    assert ok is True
    assert parsed["contractName"] == "chummer.origin_provider_account_registry.verification.v1"
    assert parsed["rawSecretValuesStored"] is False
