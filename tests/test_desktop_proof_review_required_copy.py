from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNED_IN_STATUS_SERVICE = REPO_ROOT / "Chummer.Run.Api" / "Services" / "SignedInTrustStatusService.cs"
SHELF_VIEW = REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Shelf.cshtml"
PUBLICATION_VIEW = REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "PublicCreatorPublication.cshtml"
PUBLIC_LANDING_CONTROLLER = REPO_ROOT / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"


class DesktopProofReviewRequiredCopyTests(unittest.TestCase):
    def test_signed_in_status_summary_switches_to_review_required_language(self) -> None:
        source = SIGNED_IN_STATUS_SERVICE.read_text(encoding="utf-8")

        self.assertIn("bool reviewRequired = (pulse?.ParityClaimsReviewRequired ?? false)", source)
        self.assertIn("parity-sensitive follow-through remains review-required until current desktop proof receipts are green", source)
        self.assertIn("Downloads, support, and recovery stay on the same claimed install rail", source)

    def test_publication_detail_view_switches_headline_when_route_is_review_required(self) -> None:
        source = PUBLICATION_VIEW.read_text(encoding="utf-8")

        self.assertIn("Model.TrustPulse?.ParityClaimsReviewRequired == true", source)
        self.assertIn("publicationRouteReviewRequired", source)
        self.assertIn("Why this publication stays review-required", source)
        self.assertIn("public parity claims on the review-required lane", source)

    def test_publication_shelf_view_switches_discovery_copy_when_route_is_review_required(self) -> None:
        source = SHELF_VIEW.read_text(encoding="utf-8")

        self.assertIn("Model.TrustPulse?.ParityClaimsReviewRequired == true", source)
        self.assertIn("Shared publications with limited public claims", source)
        self.assertIn("These publications are visible now, but some public comparison language still needs one more review pass.", source)
        self.assertIn("public parity claims remain review-required until current direct parity proof receipts are green", source)

    def test_support_response_expectation_inherits_review_required_route_guard(self) -> None:
        source = PUBLIC_LANDING_CONTROLLER.read_text(encoding="utf-8")

        self.assertIn("BuildSupportResponseExpectation(", source)
        self.assertIn("Public parity claims stay review-required until the current desktop proof receipts are green again.", source)
        self.assertIn("Tracked cases stay visible in Account.", source)
        self.assertIn("Guest cases should include a reply email.", source)

    def test_route_state_fields_follow_guarded_claim_state(self) -> None:
        source = PUBLIC_LANDING_CONTROLLER.read_text(encoding="utf-8")

        self.assertIn("status = routeClaim.State", source)
        self.assertIn("routeState = routeClaim.State", source)
        self.assertIn("state = routeClaim.State", source)
        self.assertIn("Current direct route receipt is attached, but parity claims stay review-required because", source)


if __name__ == "__main__":
    unittest.main()
