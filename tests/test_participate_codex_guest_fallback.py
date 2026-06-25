from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = REPO_ROOT / "Chummer.Run.Api" / "Controllers" / "CodexParticipationController.cs"
PUBLIC_CONTROLLER = REPO_ROOT / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"
PARTICIPATE_VIEW = REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Partizipate.cshtml"
FEEDBACK_VIEW = REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Feedback.cshtml"


class ParticipateCodexGuestFallbackTests(unittest.TestCase):
    def test_controller_uses_first_party_login_handoff(self) -> None:
        controller = CONTROLLER.read_text(encoding="utf-8")
        self.assertIn('return Redirect("/login?next=%2Fparticipate%2Fcodex");', controller)
        self.assertNotIn('return Redirect("/auth/google/start?next=%2Fparticipate%2Fcodex");', controller)

    def test_participate_route_uses_whitelabeled_board_proxy_and_supporter_guard(self) -> None:
        controller = PUBLIC_CONTROLLER.read_text(encoding="utf-8")
        self.assertIn('localOrigin: "/participate"', controller)
        self.assertIn('localBaseHref: "/participate/"', controller)
        self.assertIn('ResolveParticipateSupporterHref()', controller)
        self.assertIn('return "/account/billing/supporter/start";', controller)
        self.assertIn('return View("~/Views/PublicLanding/Partizipate.cshtml", model);', controller)
        self.assertNotIn('"/auth/google/start?next=%2Fparticipate%2Fcodex"', controller)
        self.assertNotIn('"/login?next=%2Fparticipate%2Fcodex"', controller)
        self.assertNotIn("Requests, votes, and shipped work.", controller)

    def test_feedback_public_view_stays_on_participation_surface(self) -> None:
        self.assertFalse(FEEDBACK_VIEW.exists())
        controller = PUBLIC_CONTROLLER.read_text(encoding="utf-8")
        self.assertIn("ParticipateBoardProxyCore", controller)
        self.assertNotIn("participate-lane", controller)
        self.assertNotIn("participate-quick-form", controller)
        self.assertNotIn("participate-fallback", controller)
        self.assertNotIn('"/login?next=%2Fparticipate%2Fcodex"', controller)

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
