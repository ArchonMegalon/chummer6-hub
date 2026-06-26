from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_CSS = REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / "css" / "auth-compact.css"
AUTH_ENTRY = REPO_ROOT / "Chummer.Run.Api" / "Views" / "Auth" / "Entry.cshtml"
AUTH_CONTROLLER = REPO_ROOT / "Chummer.Run.Api" / "Controllers" / "AuthController.cs"


def test_compact_auth_buttons_stay_quiet_and_readable() -> None:
    css = AUTH_CSS.read_text(encoding="utf-8")

    primary_block = ".route-login.surface-auth.surface-minimal .button-like--primary"
    assert primary_block in css
    assert "background: #d6b763;" in css
    assert "box-shadow: none;" in css
    assert "transform: none;" in css

    assert "linear-gradient" not in css
    assert "0 14px 34px" not in css
    assert "text-transform: uppercase;" in css
    assert "border-top-color: rgba(243, 234, 219, 0.16);" in css


def test_login_entry_stays_compact_and_single_purpose() -> None:
    css = AUTH_CSS.read_text(encoding="utf-8")
    view = AUTH_ENTRY.read_text(encoding="utf-8")
    controller = AUTH_CONTROLLER.read_text(encoding="utf-8")

    assert "width: min(17.5rem, 100%);" in css
    assert "font-size: 1.12rem;" in css
    assert "min-height: 2.05rem;" in css
    assert "padding: 0.68rem;" in css
    assert "box-shadow: none;" in css

    assert "auth-entry__story" not in view
    assert "hero-brand" not in view
    assert "<img" not in view

    assert "Open your account. Keep installs and support together." in controller
    assert "Use the same copy. Add recovery and support history." in controller
    assert "Keep this copy attached to your account." not in controller
    assert "Claiming only connects this copy to your account." not in controller
