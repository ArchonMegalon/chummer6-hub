from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_black_ledger_tick_news_delivery_contract_exists() -> None:
    service = read("Chummer.Run.Api/Services/Community/BlackLedgerTickNewsNotificationService.cs")
    controller = read("Chummer.Run.Api/Controllers/LedgerController.cs")
    store = read("Chummer.Run.Api/Services/Community/CommunityStore.cs")

    assert "public sealed class BlackLedgerTickNewsNotificationService" in service
    assert "public sealed class BlackLedgerNewsRecipientResolver" in service
    assert 'CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY' in service
    assert 'CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED' in service
    assert 'ConnectorDispatchTool = "connector.dispatch"' in service
    assert 'DeliverySendAction = "delivery.send"' in service
    assert "[HttpPost(\"worlds/{worldId}/tick-news/send\")]" in controller
    assert "BlackLedgerNewsDeliveryReceipts" in store


def test_black_ledger_tick_news_catchup_script_exists_and_targets_internal_route() -> None:
    script = read("scripts/black_ledger_send_tick_news.py")

    assert "/api/v1/ledger/worlds/" in script
    assert "tick-news/send" in script
    assert "--dry-run" in script
    assert "--send" in script
    assert "subscribed_or_only_user_preview_fallback" in script
    assert "CHUMMER_BLACK_LEDGER_INTERNAL_API_TOKEN" in script
    assert "FLEET_INTERNAL_API_TOKEN" in script
    assert "missing internal API token for remote tick-news send" in script


def test_black_ledger_tick_news_payload_parity_and_config_check_exist() -> None:
    service = read("Chummer.Run.Api/Services/Community/BlackLedgerTickNewsNotificationService.cs")
    config_check = read("scripts/black_ledger_tick_news_config_check.py")

    assert "tool_name = ConnectorDispatchTool" in service
    assert "action_kind = DeliverySendAction" in service
    assert "payload_json = new" in service
    assert 'TryGetProperty("target_ref"' in service
    assert 'TryGetProperty("output_json"' in service
    assert 'TryGetProperty("delivery_id"' in service
    assert "connector_dispatch_missing_delivery_id" in service

    assert "CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED" in config_check
    assert "CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN" in config_check
    assert "CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID" in config_check
    assert "CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID" in config_check
