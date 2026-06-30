import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_participate_snapshot_timeout_is_not_logged_as_exception() -> None:
    source = (ROOT / "Chummer.Run.Api/Services/PublicParticipateSnapshotService.cs").read_text(encoding="utf-8")

    assert 'LogWarning(ex, "Participate snapshot refresh timed out.' not in source
    assert 'catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested)' in source
    assert 'LogInformation("Participate snapshot refresh timed out; keeping cached Participate snapshot.")' in source


def test_participate_snapshot_logs_do_not_name_the_hosted_board_provider() -> None:
    source = (ROOT / "Chummer.Run.Api/Services/PublicParticipateSnapshotService.cs").read_text(encoding="utf-8")

    assert "could not reach ProductLift" not in source
    assert "invalid ProductLift JSON" not in source
    assert "could not reach the hosted board" in source
    assert "invalid hosted-board JSON" in source


def test_http_client_dependency_urls_are_not_info_logged_by_default() -> None:
    for relative_path in (
        "Chummer.Run.Api/appsettings.json",
        "Chummer.Run.Api/appsettings.Development.json",
    ):
        config = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
        levels = config["Logging"]["LogLevel"]

        assert levels["System.Net.Http.HttpClient"] == "Warning"


def test_feedback_operations_runtime_messages_do_not_name_provider() -> None:
    controller = (ROOT / "Chummer.Run.Api/Controllers/PublicLandingController.cs").read_text(encoding="utf-8")
    service = (ROOT / "Chummer.Run.Api/Services/PublicSignalOperationsService.cs").read_text(encoding="utf-8")

    assert "productlift operations replay is not configured" not in controller
    assert "productlift operations recovery is not configured" not in controller
    assert "productlift operations secret mismatch" not in controller
    assert "feedback operations replay is not configured" in controller
    assert "feedback operations recovery is not configured" in controller
    assert "feedback operations secret mismatch" in controller
    assert "delivery outcome secret mismatch" in controller
    assert "stored ProductLift webhook receipts" not in service
    assert "bounded ProductLift webhook receipts" not in service
    assert "stored feedback webhook receipts" in service
    assert "bounded feedback webhook receipts" in service
