from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = REPO_ROOT / "Chummer.Run.Api" / "Controllers" / "CodexParticipationController.cs"
PARTICIPATE_VIEW = REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Participate.cshtml"
FEEDBACK_VIEW = REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Feedback.cshtml"


class ParticipateCodexGuestFallbackTests(unittest.TestCase):
    def test_controller_uses_first_party_login_handoff(self) -> None:
        controller = CONTROLLER.read_text(encoding="utf-8")
        self.assertIn('return Redirect("/login?next=%2Fparticipate%2Fcodex");', controller)
        self.assertNotIn('return Redirect("/auth/google/start?next=%2Fparticipate%2Fcodex");', controller)

    def test_public_views_use_first_party_login_handoff(self) -> None:
        for path in (PARTICIPATE_VIEW, FEEDBACK_VIEW):
            text = path.read_text(encoding="utf-8")
            self.assertIn('"/login?next=%2Fparticipate%2Fcodex"', text, msg=str(path))
            self.assertNotIn('"/auth/google/start?next=%2Fparticipate%2Fcodex"', text, msg=str(path))


if __name__ == "__main__":
    unittest.main()
