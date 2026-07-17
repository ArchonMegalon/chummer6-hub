from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_teable_http_timeout_is_documented_in_env_example() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "CHUMMER_TEABLE_HTTP_TIMEOUT_SECONDS=15" in env_example
    assert "CHUMMER_TEABLE_IMPORTANT_WORK_SYNC_DEADLINE_SECONDS=90" in env_example


def test_teable_services_apply_bounded_request_timeouts() -> None:
    service_paths = [
        ROOT / "Chummer.Run.Api/Services/Community/TeableUserProjectionService.cs",
        ROOT / "Chummer.Run.Api/Services/Community/TeableHeyyScamChatService.cs",
        ROOT / "Chummer.Run.Api/Services/Community/TeableExecutiveAssistantChannelService.cs",
        ROOT / "Chummer.Run.Api/Services/Community/TeableBlackLedgerWorldTickService.cs",
        ROOT / "Chummer.Run.Api/Services/KarmaForge/TeableKarmaForgeReviewBoardService.cs",
    ]

    for path in service_paths:
        text = path.read_text(encoding="utf-8")
        assert 'HttpTimeoutSecondsConfigKey = "CHUMMER_TEABLE_HTTP_TIMEOUT_SECONDS"' in text
        assert "DefaultHttpTimeout = TimeSpan.FromSeconds(15)" in text
        assert "CancellationTokenSource.CreateLinkedTokenSource(cancellationToken)" in text
        assert "timeoutCts.CancelAfter(ResolveHttpTimeout())" in text
        assert "SendAsync(request, timeoutCts.Token)" in text


def test_important_work_sync_script_uses_bounded_teable_timeouts() -> None:
    text = (ROOT / "scripts" / "sync_important_work_to_teable.py").read_text(encoding="utf-8")

    assert 'configured_value("CHUMMER_TEABLE_HTTP_TIMEOUT_SECONDS")' in text
    assert 'configured_value("CHUMMER_TEABLE_IMPORTANT_WORK_SYNC_DEADLINE_SECONDS")' in text
    assert "bounded_timeout_seconds(" in text
    assert 'label="teable_sync"' in text
    assert '"deadline_exceeded": deadline_exceeded' in text
