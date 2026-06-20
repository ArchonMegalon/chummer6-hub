from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_feedback_public_copy_truth_gate_script_exists() -> None:
    assert (REPO_ROOT / "scripts" / "public_copy_truth_gate.py").is_file()


def test_feedback_copy_keeps_public_safe_closeout_language() -> None:
    feedback = read("Chummer.Run.Api/Views/PublicLanding/Feedback.cshtml")
    operations = read("Chummer.Run.Api/Views/Shared/_PublicSignalOperationsPacket.cshtml")

    assert "Votes show demand. Chummer decides what ships." in feedback
    assert "The loop closes only after people can use it" in feedback
    assert "release-backed closeout" not in feedback
    assert "First-party follow-up is not posted here yet." in operations
    assert "account-backed follow-up waits until the shipped path is available on this host" in operations
    assert "webhook verification" not in feedback
    assert "delivery candidates" not in feedback
