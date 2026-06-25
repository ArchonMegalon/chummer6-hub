from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_CSS = REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / "css" / "auth-compact.css"


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
