from __future__ import annotations

from pathlib import Path
import importlib.util
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPT = REPO_ROOT / "scripts" / "public_copy_truth_gate.py"


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_feedback_public_copy_truth_gate_script_exists() -> None:
    assert GATE_SCRIPT.is_file()


def test_feedback_copy_keeps_public_safe_closeout_language() -> None:
    controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")
    participate = read("Chummer.Run.Api/Views/PublicLanding/Partizipate.cshtml")
    operations = read("Chummer.Run.Api/Views/Shared/_PublicSignalOperationsPacket.cshtml")
    projection = read("Chummer.Run.Api/Views/Shared/_PublicSignalProjectionPacket.cshtml")
    spec = importlib.util.spec_from_file_location("public_copy_truth_gate", GATE_SCRIPT)
    assert spec is not None and spec.loader is not None
    gate_module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(GATE_SCRIPT.parent))
    spec.loader.exec_module(gate_module)

    assert 'private static string BuildParticipateFrameHref(' in controller
    assert 'BuildParticipateBoardRouteHref(normalizedBoardPath)' in controller
    assert 'ResolveParticipateSupporterHref()' in controller
    assert "Current requests" in participate
    assert 'participate-preview-card' not in participate
    assert 'data-chummer-participate-frame' in participate
    assert "Requests, votes, and shipped work." not in controller
    assert 'id="participate-board"' not in controller
    assert "Tell us what slows the table down." not in controller
    assert "Use the right place" not in controller
    assert "Public Feedback And Content Registry" not in controller
    assert "Open the Alice compare bench" not in controller
    assert "BLACK LEDGER" not in controller
    assert "release-backed closeout" not in controller
    assert "Chummer follow-up is not visible here yet." in operations
    assert "account follow-up waits until the shipped path is available on this host" in operations
    assert "Public feedback stays easy to sort." in operations
    assert "Context" in projection
    assert "Decision sources" not in projection
    assert "Open details" in projection
    assert "Open first-party fallback" not in projection
    assert "Boundary conditions" not in projection
    assert "Before it ships" in projection
    assert "The public participation copy stays compact, public-safe, and honest about what belongs in Help." in GATE_SCRIPT.read_text(encoding="utf-8")
    assert "webhook verification" not in controller
    assert "delivery candidates" not in controller
    assert "release-backed closeout" not in gate_module.REQUIRED_HTML_PHRASES
    assert "release-backed closeout" not in gate_module.REQUIRED_SOURCE_PHRASES
    assert "proof-bound" not in gate_module.REQUIRED_HTML_PHRASES
    assert "proof-bound" not in gate_module.REQUIRED_SOURCE_PHRASES
    assert "What should Chummer do next?" in gate_module.REQUIRED_HTML_PHRASES
    assert "Public requests, clear bugs, useful ideas." in gate_module.REQUIRED_HTML_PHRASES
    assert "public async Task<IActionResult> ParticipateBoardProxy(string? boardPath, CancellationToken cancellationToken)" in gate_module.REQUIRED_SOURCE_PHRASES
    assert "return Redirect($\"/participate{Request.QueryString}\");" in gate_module.REQUIRED_SOURCE_PHRASES
    assert "Current requests" in gate_module.REQUIRED_SOURCE_PHRASES
    assert "data-chummer-participate-frame" in gate_module.REQUIRED_SOURCE_PHRASES
    assert "data-chummer-board-skin" in gate_module.FORBIDDEN_HTML_PHRASES
    assert "data-chummer-participate-frame" not in gate_module.FORBIDDEN_SOURCE_PHRASES
    assert "release-backed closeout" in gate_module.FORBIDDEN_HTML_PHRASES
    assert "proof-bound" in gate_module.FORBIDDEN_HTML_PHRASES


def test_auth_entry_uses_account_language_in_public_copy() -> None:
    auth_entry = read("Chummer.Run.Api/Views/Auth/Entry.cshtml")

    assert 'ViewData["SurfaceClass"] = Model.CreateAccount ? "surface-auth surface-minimal" : "surface-auth surface-minimal surface-auth-login";' in auth_entry
    assert "@Model.SupportLine" in auth_entry
    assert "Use your email to continue." not in auth_entry
    assert "Use email to create your account." not in auth_entry
    assert "Continue with Google" in auth_entry
    assert "the signed-in product" not in auth_entry
    assert "Your signed-in home and account pages for return, recovery, and the next step." not in auth_entry
