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
    feedback = read("Chummer.Run.Api/Views/PublicLanding/Feedback.cshtml")
    operations = read("Chummer.Run.Api/Views/Shared/_PublicSignalOperationsPacket.cshtml")
    projection = read("Chummer.Run.Api/Views/Shared/_PublicSignalProjectionPacket.cshtml")
    spec = importlib.util.spec_from_file_location("public_copy_truth_gate", GATE_SCRIPT)
    assert spec is not None and spec.loader is not None
    gate_module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(GATE_SCRIPT.parent))
    spec.loader.exec_module(gate_module)

    assert "Votes show demand. Chummer decides what ships." in feedback
    assert "The loop closes only after people can use it" in feedback
    assert "Use the page that matches the job." in feedback
    assert "Public feedback is for ideas and safe bugs." in feedback
    assert "Public Feedback And Content Registry" not in feedback
    assert "Open the Alice compare bench" not in feedback
    assert "BLACK LEDGER" not in feedback
    assert "release-backed closeout" not in feedback
    assert "First-party follow-up is not posted here yet." in operations
    assert "account-backed follow-up waits until the shipped path is available on this host" in operations
    assert "Public feedback stays easy to route." in operations
    assert "Decision context" in projection
    assert "Decision sources" not in projection
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
