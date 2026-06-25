from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_auxiliary_teable_lanes_are_opt_in_by_default() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    public_edge_compose = (ROOT / "docker-compose.public-edge.yml").read_text(encoding="utf-8")

    assert "CHUMMER_TEABLE_HEYY_SCAM_CHAT_ENABLED=false" in env_example
    assert "CHUMMER_TEABLE_HEYY_SCAM_CHAT_RECONCILE_ENABLED=false" in env_example
    assert "CHUMMER_TEABLE_KARMA_FORGE_ENABLED=false" in env_example
    assert "CHUMMER_TEABLE_KARMA_FORGE_RECONCILE_ENABLED=false" in env_example
    assert "CHUMMER_TEABLE_BLACK_LEDGER_ENABLED=false" in env_example
    assert "CHUMMER_TEABLE_BLACK_LEDGER_RECONCILE_ENABLED=false" in env_example

    for snippet in (
        "CHUMMER_TEABLE_USERS_ENABLED: ${CHUMMER_TEABLE_USERS_ENABLED:-false}",
        "CHUMMER_TEABLE_USERS_RECONCILE_ENABLED: ${CHUMMER_TEABLE_USERS_RECONCILE_ENABLED:-false}",
        "CHUMMER_TEABLE_HEYY_SCAM_CHAT_ENABLED: ${CHUMMER_TEABLE_HEYY_SCAM_CHAT_ENABLED:-false}",
        "CHUMMER_TEABLE_HEYY_SCAM_CHAT_RECONCILE_ENABLED: ${CHUMMER_TEABLE_HEYY_SCAM_CHAT_RECONCILE_ENABLED:-false}",
        "CHUMMER_TEABLE_KARMA_FORGE_ENABLED: ${CHUMMER_TEABLE_KARMA_FORGE_ENABLED:-false}",
        "CHUMMER_TEABLE_KARMA_FORGE_RECONCILE_ENABLED: ${CHUMMER_TEABLE_KARMA_FORGE_RECONCILE_ENABLED:-false}",
        "CHUMMER_TEABLE_BLACK_LEDGER_ENABLED: ${CHUMMER_TEABLE_BLACK_LEDGER_ENABLED:-false}",
        "CHUMMER_TEABLE_BLACK_LEDGER_RECONCILE_ENABLED: ${CHUMMER_TEABLE_BLACK_LEDGER_RECONCILE_ENABLED:-false}",
    ):
        assert snippet in public_edge_compose


def test_auxiliary_teable_services_default_disabled_in_source() -> None:
    checks = {
        ROOT / "Chummer.Run.Api/Services/Community/TeableHeyyScamChatService.cs": [
            'CHUMMER_TEABLE_HEYY_SCAM_CHAT_ENABLED"], defaultValue: false',
            'CHUMMER_TEABLE_HEYY_SCAM_CHAT_RECONCILE_ENABLED"], defaultValue: false',
        ],
        ROOT / "Chummer.Run.Api/Services/Community/TeableExecutiveAssistantChannelService.cs": [
            'CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_ENABLED"], defaultValue: false',
        ],
        ROOT / "Chummer.Run.Api/Services/Community/TeableBlackLedgerWorldTickService.cs": [
            'CHUMMER_TEABLE_BLACK_LEDGER_ENABLED"], defaultValue: false',
        ],
        ROOT / "Chummer.Run.Api/Services/Community/TeableBlackLedgerWorldTickSyncWorker.cs": [
            'CHUMMER_TEABLE_BLACK_LEDGER_RECONCILE_ENABLED"], defaultValue: false',
        ],
        ROOT / "Chummer.Run.Api/Services/KarmaForge/TeableKarmaForgeReviewBoardService.cs": [
            'CHUMMER_TEABLE_KARMA_FORGE_ENABLED"], defaultValue: false',
        ],
        ROOT / "Chummer.Run.Api/Services/KarmaForge/TeableKarmaForgeReviewBoardSyncWorker.cs": [
            'CHUMMER_TEABLE_KARMA_FORGE_RECONCILE_ENABLED"], defaultValue: false',
        ],
    }

    for path, snippets in checks.items():
        text = path.read_text(encoding="utf-8")
        for snippet in snippets:
            assert snippet in text, f"missing opt-in default guard in {path}"
