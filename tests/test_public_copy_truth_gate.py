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
    feedback = read("Chummer.Run.Api/Views/PublicLanding/Participate.cshtml")
    operations = read("Chummer.Run.Api/Views/Shared/_PublicSignalOperationsPacket.cshtml")
    projection = read("Chummer.Run.Api/Views/Shared/_PublicSignalProjectionPacket.cshtml")
    spec = importlib.util.spec_from_file_location("public_copy_truth_gate", GATE_SCRIPT)
    assert spec is not None and spec.loader is not None
    gate_module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(GATE_SCRIPT.parent))
    spec.loader.exec_module(gate_module)

    assert "Tell us what slows the table down." in feedback
    assert "Use this page for public requests and safe bug reports. Use Help for anything private, account-linked, or install-specific." in feedback
    assert "Use the right place" in feedback
    assert "Start with the shortest path." in feedback
    assert "Public Feedback And Content Registry" not in feedback
    assert "Open the Alice compare bench" not in feedback
    assert "BLACK LEDGER" not in feedback
    assert "release-backed closeout" not in feedback
    assert "Chummer follow-up is not visible here yet." in operations
    assert "account follow-up waits until the shipped path is available on this host" in operations
    assert "Public feedback stays easy to sort." in operations
    assert "Context" in projection
    assert "Decision sources" not in projection
    assert "Open details" in projection
    assert "Open first-party fallback" not in projection
    assert "Boundary conditions" not in projection
    assert "Before it ships" in projection
    assert "The /feedback public copy stays clear, public-safe, and honest about what has shipped." in GATE_SCRIPT.read_text(encoding="utf-8")
    assert "webhook verification" not in feedback
    assert "delivery candidates" not in feedback
    assert "release-backed closeout" not in gate_module.REQUIRED_HTML_PHRASES
    assert "release-backed closeout" not in gate_module.REQUIRED_SOURCE_PHRASES
    assert "proof-bound" not in gate_module.REQUIRED_HTML_PHRASES
    assert "proof-bound" not in gate_module.REQUIRED_SOURCE_PHRASES
    assert "release-backed closeout" in gate_module.FORBIDDEN_HTML_PHRASES
    assert "proof-bound" in gate_module.FORBIDDEN_HTML_PHRASES


def test_auth_entry_uses_account_language_in_public_copy() -> None:
    auth_entry = read("Chummer.Run.Api/Views/Auth/Entry.cshtml")

    assert "the account area" in auth_entry
    assert 'ViewData["SurfaceClass"] = "surface-auth surface-minimal";' in auth_entry
    assert "Use email or Google if you want Chummer to remember you. The download does not need an account." in auth_entry
    assert "No account is needed to download Chummer. Claiming only helps with linked installs, recovery, and private pages." in auth_entry
    assert "the signed-in product" not in auth_entry
    assert "Your signed-in home and account pages for return, recovery, and the next step." not in auth_entry
