from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_release_upload_access_can_fall_back_to_claims_email() -> None:
    chrome = read("Chummer.Run.Api/Services/HubPageChromeService.cs")

    assert "_httpContextAccessor.HttpContext?.User" in chrome
    assert "ClaimTypes.Email" in chrome
    assert '"preferred_username"' in chrome
    assert "FindFirstValue" in chrome


def test_account_hub_exposes_macos_build_entry_for_allowed_user() -> None:
    account = read("Chummer.Run.Api/Controllers/AccountsController.cs")

    assert "Build macOS" in account
    assert '"/downloads/release-upload/bootstrap.command"' in account
    assert '"/downloads/release-upload"' in account


def test_billing_controller_keeps_redirect_fallback_when_provider_page_is_unavailable() -> None:
    controller = read("Chummer.Run.Api/Controllers/BrilliantDirectoriesBillingController.cs")

    assert "ResolveUnavailableBillingHandoff" in controller
    assert "BRILLIANT_DIRECTORIES_MEMBER_PORTAL_URL" in controller
    assert "BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL" in controller
    assert "BRILLIANT_DIRECTORIES_CHECKOUT_USER_ID_PARAMETER" in controller
    assert "BRILLIANT_DIRECTORIES_CHECKOUT_EMAIL_PARAMETER" in controller
