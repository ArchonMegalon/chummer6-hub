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

    def test_participate_public_view_stays_public_and_first_party(self) -> None:
        text = PARTICIPATE_VIEW.read_text(encoding="utf-8")
        self.assertIn('href="@Model.PrivateHelpHref"', text)
        self.assertIn('href="@Model.RoadmapHref"', text)
        self.assertNotIn('"/auth/google/start?next=%2Fparticipate%2Fcodex"', text)
        self.assertNotIn('"/login?next=%2Fparticipate%2Fcodex"', text)
        self.assertNotIn("ProductLift", text)
        self.assertIn("Public requests, one board.", text)
        self.assertIn("First-party route", text)
        self.assertNotIn("Open in a tab", text)

    def test_feedback_public_view_stays_on_participation_surface(self) -> None:
        self.assertFalse(FEEDBACK_VIEW.exists())
        text = PARTICIPATE_VIEW.read_text(encoding="utf-8")
        self.assertIn("participate-shell", text)
        self.assertIn("participate-quick-form", text)
        self.assertNotIn("participate-lanes", text)
        self.assertNotIn('"/login?next=%2Fparticipate%2Fcodex"', text)


if __name__ == "__main__":
    unittest.main()
