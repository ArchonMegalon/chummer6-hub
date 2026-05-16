from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_participant_notification_runtime_wires_account_open_and_first_action_hooks() -> None:
    service = read("Chummer.Run.Api/Services/Community/ParticipationOperatorNotificationService.cs")
    auth_controller = read("Chummer.Run.Api/Controllers/AuthController.cs")
    public_landing_controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")
    codex_controller = read("Chummer.Run.Api/Controllers/CodexParticipationController.cs")
    accounts_controller = read("Chummer.Run.Api/Controllers/AccountsController.cs")

    assert "participant_account_opened" in service
    assert "participant_first_action" in service
    assert "CHUMMER_OPERATOR_PARTICIPATION_NOTIFY_TO" in service
    assert "suppressed_recipient_missing" in service
    assert "failed_delivery" in service
    assert "NotifyAccountOpenedIfNeededAsync" in auth_controller
    assert "NotifyFirstActionIfNeededAsync" in public_landing_controller
    assert "NotifyFirstActionIfNeededAsync" in codex_controller
    assert "NotifyFirstActionIfNeededAsync" in accounts_controller


def test_participant_notification_canon_and_dashboard_route_exist() -> None:
    manifest = read(".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml")
    feature_registry = read(".codex-design/product/PUBLIC_FEATURE_REGISTRY.yaml")
    surface_doc = read("docs/PUBLIC_LANDING_SURFACE.md")
    dashboard_plan = read("../_completion/chummer6_absolute_completion/SIGNED_IN_PARTICIPATION_DASHBOARD_PLAN.md")

    assert "/account/participation" in manifest
    assert "purpose: signed_in_participation" in manifest
    assert "href: /account/participation" in feature_registry
    assert "registered_href: /account/participation" in feature_registry
    assert "/account/participation" in surface_doc
    assert "/account/participation" in dashboard_plan
