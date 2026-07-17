from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "magicai_pool_registry.py"


def load_module():
    spec = importlib.util.spec_from_file_location("magicai_pool_registry", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_magicai_pool_registry_tracks_declared_ready_and_missing_aliases() -> None:
    module = load_module()

    state = module.magicai_pool_counts(
        {
            "CHUMMER_EA_MAGICAI_EMAIL": "primary@example.test",
            "CHUMMER_EA_MAGICAI_PASSWORD": "pw",
            "MAGICAI_ACCOUNT_2_EMAIL": "two@example.test",
            "MAGICAI_ACCOUNT_2_PASSWORD": "pw",
            "MAGICAI_ACCOUNT_03_API_KEY": "secret-three",
            "MAGICAI_ACCOUNT_10_EMAIL": "ten@example.test",
            "MAGICAI_ACCOUNT_10_PASSWORD": "pw",
            "MAGICAI_ACCOUNT_10_API_KEY": "secret-ten",
        }
    )

    assert module.magicai_declared_aliases(
        {
            "CHUMMER_EA_MAGICAI_EMAIL": "primary@example.test",
            "CHUMMER_EA_MAGICAI_PASSWORD": "pw",
            "MAGICAI_ACCOUNT_2_EMAIL": "two@example.test",
            "MAGICAI_ACCOUNT_2_PASSWORD": "pw",
            "MAGICAI_ACCOUNT_03_API_KEY": "secret-three",
            "MAGICAI_ACCOUNT_10_EMAIL": "ten@example.test",
            "MAGICAI_ACCOUNT_10_PASSWORD": "pw",
            "MAGICAI_ACCOUNT_10_API_KEY": "secret-ten",
        }
    ) == ["02", "03", "10", "primary"]
    assert module.magicai_login_ready_aliases(
        {
            "CHUMMER_EA_MAGICAI_EMAIL": "primary@example.test",
            "CHUMMER_EA_MAGICAI_PASSWORD": "pw",
            "MAGICAI_ACCOUNT_2_EMAIL": "two@example.test",
            "MAGICAI_ACCOUNT_2_PASSWORD": "pw",
            "MAGICAI_ACCOUNT_10_EMAIL": "ten@example.test",
            "MAGICAI_ACCOUNT_10_PASSWORD": "pw",
        }
    ) == ["02", "10", "primary"]
    assert module.magicai_api_ready_aliases(
        {
            "MAGICAI_ACCOUNT_03_API_KEY": "secret-three",
            "MAGICAI_ACCOUNT_10_API_KEY": "secret-ten",
        }
    ) == ["03", "10"]
    assert module.magicai_api_missing_aliases(
        {
            "CHUMMER_EA_MAGICAI_EMAIL": "primary@example.test",
            "CHUMMER_EA_MAGICAI_PASSWORD": "pw",
            "MAGICAI_ACCOUNT_2_EMAIL": "two@example.test",
            "MAGICAI_ACCOUNT_2_PASSWORD": "pw",
            "MAGICAI_ACCOUNT_10_EMAIL": "ten@example.test",
            "MAGICAI_ACCOUNT_10_PASSWORD": "pw",
            "MAGICAI_ACCOUNT_10_API_KEY": "secret-ten",
        }
    ) == ["02", "primary"]
    assert state == {
        "declared_count": 4,
        "login_ready_count": 3,
        "api_key_ready_count": 2,
        "pending_api_key_count": 2,
    }


def test_magicai_platform_audit_tracks_pending_mintable_and_blocked_aliases(tmp_path: Path) -> None:
    module = load_module()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MAGICAI_ACCOUNT_02_EMAIL=two@example.test",
                "MAGICAI_ACCOUNT_02_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_03_EMAIL=three@example.test",
                "MAGICAI_ACCOUNT_03_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_09_EMAIL=nine@example.test",
                "MAGICAI_ACCOUNT_09_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_10_EMAIL=ten@example.test",
                "MAGICAI_ACCOUNT_10_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_10_API_KEY=api-key-ten",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / ".codex-studio/published").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".codex-studio/published/MAGICAI_PLATFORM_ACCESS.generated.json").write_text(
        json.dumps(
            {
                "checked_at_utc": "2026-06-30T18:42:00Z",
                "slots": [
                    {"slot": "02", "keys_status": "forbidden", "logged_in": True},
                    {"slot": "03", "keys_status": "ok", "logged_in": True},
                    {"slot": "09", "keys_status": "login_failed", "logged_in": False},
                    {"slot": "10", "keys_status": "ok", "logged_in": True},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    audit = module.magicai_platform_audit(tmp_path)
    summary = module.magicai_platform_audit_summary(tmp_path)

    assert audit["attempted"] is True
    assert audit["accessible_aliases"] == ["03", "10"]
    assert audit["blocked_aliases"] == ["02"]
    assert audit["login_failed_aliases"] == ["09"]
    assert audit["pending_mintable_aliases"] == ["03"]
    assert audit["pending_blocked_aliases"] == ["02"]
    assert audit["pending_login_failed_aliases"] == ["09"]
    assert audit["pending_unverified_aliases"] == []
    assert summary["accessibleAccounts"] == ["03", "10"]
    assert summary["forbiddenAccounts"] == ["02"]
    assert summary["loginFailedAccounts"] == ["09"]
    serialized = json.dumps({"audit": audit, "summary": summary}, sort_keys=True)
    assert "two@example.test" not in serialized
    assert "api-key-ten" not in serialized
