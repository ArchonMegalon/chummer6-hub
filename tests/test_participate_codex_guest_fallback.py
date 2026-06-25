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

    def test_participate_view_stays_first_party_and_supporter_ready(self) -> None:
        text = PARTICIPATE_VIEW.read_text(encoding="utf-8")
        self.assertIn('href="@Model.RoadmapHref"', text)
        self.assertIn('href="/contact#support-intake"', text)
        self.assertIn("Support Chummer", text)
        self.assertIn('@if (!string.IsNullOrWhiteSpace(Model.SupporterHref))', text)
        self.assertIn('src="@(string.IsNullOrWhiteSpace(Model.HostedBoardHref) ? "/participate/board" : Model.HostedBoardHref)"', text)
        self.assertIn('id="participate-board"', text)
        self.assertNotIn('"/auth/google/start?next=%2Fparticipate%2Fcodex"', text)
        self.assertNotIn('"/login?next=%2Fparticipate%2Fcodex"', text)
        self.assertNotIn("ProductLift", text)
        self.assertIn("Requests, votes, and shipped work.", text)
        self.assertNotIn("Use the right place", text)
        self.assertNotIn("Use the right lane", text)
        self.assertNotIn("first-party route", text)
        self.assertNotIn("Open in a tab", text)

    def test_feedback_public_view_stays_on_participation_surface(self) -> None:
        self.assertFalse(FEEDBACK_VIEW.exists())
        text = PARTICIPATE_VIEW.read_text(encoding="utf-8")
        self.assertIn("participate-shell", text)
        self.assertNotIn("participate-lane", text)
        self.assertNotIn("participate-quick-form", text)
        self.assertNotIn('"/login?next=%2Fparticipate%2Fcodex"', text)

    def test_public_participate_controller_targets_board_proxy_instead_of_recursive_wrapper(self) -> None:
        controller = (REPO_ROOT / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs").read_text(encoding="utf-8")
        self.assertIn('=> ResolveProductLiftHostedBoardUri() is null ? null : "/participate/board";', controller)
        self.assertNotIn('=> ResolveProductLiftHostedBoardUri() is null ? null : "/participate";', controller)

    def test_authenticated_participate_e2e_spec_rejects_sign_in_chrome(self) -> None:
        spec = (REPO_ROOT / "tests" / "public" / "participate-billing-auth.spec.ts").read_text(encoding="utf-8")
        self.assertIn("not.toContainText('Sign in')", spec)
        self.assertIn("not.toContain('Sign in')", spec)


if __name__ == "__main__":
    unittest.main()
