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
    assert "productlift webhook adapter is not configured" not in controller
    assert "productlift webhook secret mismatch" not in controller
    assert "feedback operations replay is not configured" in controller
    assert "feedback operations recovery is not configured" in controller
    assert "feedback operations secret mismatch" in controller
    assert "feedback webhook adapter is not configured" in controller
    assert "feedback webhook secret mismatch" in controller
    assert "delivery outcome secret mismatch" in controller
    assert "productlift webhook payload must be a JSON object" not in service
    assert "productlift webhook event id" not in service
    assert "productlift webhook event type" not in service
    assert "productlift webhook board label" not in service
    assert "productlift webhook category label" not in service
    assert "productlift webhook item reference" not in service
    assert "productlift webhook status label" not in service
    assert "productlift webhook action label" not in service
    assert "Unable to deserialize ProductLift webhook receipt snapshot" not in service
    assert "feedback webhook payload must be a JSON object" in service
    assert "feedback webhook event id" in service
    assert "feedback webhook event type" in service
    assert "feedback webhook board label" in service
    assert "feedback webhook category label" in service
    assert "feedback webhook item reference" in service
    assert "feedback webhook status label" in service
    assert "feedback webhook action label" in service
    assert "Unable to deserialize feedback webhook receipt snapshot" in service
    assert "stored ProductLift webhook receipts" not in service
    assert "bounded ProductLift webhook receipts" not in service
    assert "ProductLift closeout" not in service
    assert "ProductLift source" not in service
    assert "bounded ProductLift closeout" not in service
    assert "bounded ProductLift journey" not in service
    assert "bounded ProductLift replay" not in service
    assert "stored feedback webhook receipts" in service
    assert "bounded feedback webhook receipts" in service
    assert "bounded feedback closeout" in service
    assert "bounded feedback journey" in service
    assert "bounded feedback replay" in service
    assert "ready feedback source" in service
    assert "feedback source receipt" in service
    assert "feedback closeout" in service
