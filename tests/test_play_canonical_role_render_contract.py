from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "Chummer.Run.Api"


def test_play_action_uses_real_query_and_only_emits_query_free_canonical_redirect() -> None:
    controller = (API / "Controllers/PublicLandingController.cs").read_text(encoding="utf-8")
    action = controller.split("public IActionResult PlayProjectionPage()", 1)[1].split(
        '[HttpGet("/player")]', 1
    )[0]

    assert "ResolveCanonicalPlayRoleFromQuery(Request.Query)" in action
    assert 'return Redirect($"/mobile/{canonicalRole}");' in action
    assert "return View" not in action
    assert "Request.QueryString" not in action  # No raw query is copied to Location.
    assert "ApplyPrivateMobileDocumentHeaders();" in action
    assert "values.Count == 1" in controller
    assert 'query["role"]' in controller
    assert "Missing, repeated, or" in controller
    for alias in ("gm", "game-master", "gamemaster", "observer", "spectator", "viewer", "player", "runner", "pc"):
        assert f'"{alias}"' in controller


def test_redirect_tests_execute_real_query_string_into_http_response_history_location() -> None:
    tests = (ROOT / "Chummer.Tests/PublicLandingMobileProjectionFallbackTests.cs").read_text(encoding="utf-8")

    assert "Controller.Request.QueryString = new QueryString(queryString);" in tests
    assert "await redirect.ExecuteResultAsync(Controller.ControllerContext);" in tests
    assert "StatusCodes.Status302Found" in tests
    assert "Assert.False(redirect.Permanent);" in tests
    assert "Assert.False(redirect.PreserveMethod);" in tests
    assert 'Assert.DoesNotContain(\'?\', location);' in tests
    assert "must-not-survive" in tests
    assert '?role=gm&role=observer&secret=must-not-survive' in tests


def test_role_output_is_closed_encoded_and_materially_distinct() -> None:
    controller = (API / "Controllers/PublicLandingController.cs").read_text(encoding="utf-8")
    model = (API / "ViewModels/SiteViewModels.cs").read_text(encoding="utf-8")
    view = (API / "Views/PublicLanding/MobileProjection.cshtml").read_text(encoding="utf-8")

    assert "public sealed record MobileInstallRoleProfileViewModel" in model
    for field in (
        "PurposeHeading",
        "PurposeSummary",
        "PrivacyHeading",
        "PrivacySummary",
        "AuthorityHeading",
        "AuthoritySummary",
        "InstallTargetPath",
        "QrAriaLabel",
        "OpenTargetLabel",
        "Capabilities",
    ):
        assert field in model
        assert f"roleProfile.{field}" in view

    distinct_copy = {
        "player": ("Keep your runner ready at the table.", "Runner readiness", "/mobile/player"),
        "gm": ("Stage the table without exposing Game Master controls.", "Scene pacing", "/mobile/gm"),
        "observer": ("Follow the table without gaining control.", "Read-mostly return", "/mobile/observer"),
    }
    for purpose, capability, target in distinct_copy.values():
        assert purpose in controller
        assert capability in controller
        assert f'InstallTargetPath: "{target}"' in controller
    assert len({purpose for purpose, _, _ in distinct_copy.values()}) == 3
    assert "Html.Raw" not in view
    assert "data-mobile-app-inline-handoff" in view
    assert "data-mobile-app-inline-qr" in view
    assert 'data-role-privacy-warning="@roleProfile.RoleKey"' in view
    assert 'data-role-authority-warning="@roleProfile.RoleKey"' in view


def test_rendered_output_test_executes_razor_view_and_checks_role_exclusivity() -> None:
    tests = (ROOT / "Chummer.Tests/PublicLandingMobileProjectionFallbackTests.cs").read_text(encoding="utf-8")

    assert "MobileRoleProjectionPage_RendersDistinctEncodedRoleOutput" in tests
    assert "await view.ExecuteResultAsync(Controller.ControllerContext);" in tests
    assert "return await reader.ReadToEndAsync();" in tests
    assert 'Assert.Contains($"data-install-role=\\"{role}\\"", html' in tests
    assert "Assert.DoesNotContain(forbiddenOtherRolePurpose, html" in tests
    assert 'Assert.DoesNotContain("mobile-turn-companion.js", html' in tests
