from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_ea_operator_notification_delivery_stays_on_ea_queue_contract() -> None:
    service = read("Chummer.Run.Api/Services/Community/ParticipationOperatorNotificationService.cs")

    assert 'ConnectorDispatchTool = "connector.dispatch"' in service
    assert 'DeliverySendAction = "delivery.send"' in service
    assert 'EmailChannel = "email"' in service
    assert '"email_masked"' in service
    assert '"email_hash"' in service
    assert '"subject_hash"' in service
    assert "recipient" in service
    assert "Emailit" not in service


def test_operator_notification_privacy_review_matches_runtime_constraints() -> None:
    privacy_review = read("../_completion/chummer6_absolute_completion/OPERATOR_NOTIFICATION_PRIVACY_REVIEW.md")
    copy_guide = read("../_completion/chummer6_absolute_completion/PUBLIC_PARTICIPATION_COPY_CHANGE_GUIDE.md")

    assert "unmasked user email" in privacy_review
    assert "recipient address on public routes" in privacy_review
    assert "Votes show demand. Chummer decides what ships." in copy_guide
    assert "Private logs and account issues belong in Help, not public feedback." in copy_guide
