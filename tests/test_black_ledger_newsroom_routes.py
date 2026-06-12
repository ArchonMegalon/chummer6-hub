from __future__ import annotations

import json
import unittest
from urllib.parse import urlparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = REPO_ROOT / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"
VIEW = REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Ledger.cshtml"
BRIEFINGS = REPO_ROOT / "Chummer.Run.Api" / "Services" / "Community" / "BlackLedgerWorldTickBriefingService.cs"
MODELS = REPO_ROOT / "Chummer.Run.Api" / "ViewModels" / "SiteViewModels.cs"
TOUR_EXPORTS_MANIFEST = REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / "media" / "ledger" / "tours" / "black-ledger-tour-exports.manifest.json"


class BlackLedgerNewsroomRouteTests(unittest.TestCase):
    def test_public_newsroom_routes_exist(self) -> None:
        controller = CONTROLLER.read_text(encoding="utf-8")
        self.assertIn('[HttpGet("/ledger/newsroom")]', controller)
        self.assertIn('[HttpGet("/ledger/newsroom/{episodeId}")]', controller)
        self.assertIn('[HttpGet("/ledger/newsroom/{episodeId}/transcript")]', controller)
        self.assertIn('[HttpGet("/ledger/newsroom/{episodeId}/receipts")]', controller)
        self.assertIn("TryParseNewsroomEpisodeTurn", controller)

    def test_watch_surface_exposes_required_newsroom_sections(self) -> None:
        ledger_view = VIEW.read_text(encoding="utf-8")
        self.assertIn("Black Ledger Newsroom", ledger_view)
        self.assertIn("Open watch route", ledger_view)
        self.assertIn("Transcript", ledger_view)
        self.assertIn("Source receipts", ledger_view)
        self.assertIn("Feedback", ledger_view)
        self.assertIn("Published:", ledger_view)

    def test_broadcast_model_carries_newsroom_contract_fields(self) -> None:
        models = MODELS.read_text(encoding="utf-8")
        for marker in (
            "TranscriptHref",
            "ReceiptsHref",
            "PublishedLabel",
            "EpisodeTypeLabel",
            "PublicSafetyNote",
            "ReconstructionNote",
            "FeedbackHref",
        ):
            self.assertIn(marker, models)

    def test_briefing_service_builds_newsroom_links_and_safety_copy(self) -> None:
        briefing_service = BRIEFINGS.read_text(encoding="utf-8")
        self.assertIn('string watchHref = $"{ledgerBasePath.TrimEnd(\'/\')}/newsroom/{slug}";', briefing_service)
        self.assertIn("Public-safe bulletin built from aggregate Black Ledger world receipts.", briefing_service)
        self.assertIn("Some footage is reconstructed from public-safe receipts.", briefing_service)

    def test_ledger_map_exposes_real_provider_tour_exports_from_manifest(self) -> None:
        ledger_view = VIEW.read_text(encoding="utf-8")
        manifest = json.loads(TOUR_EXPORTS_MANIFEST.read_text(encoding="utf-8"))
        exports = {item["provider"]: item for item in manifest["exports"]}

        self.assertIn("data-ledger-tour-exports=\"/media/ledger/tours/black-ledger-tour-exports.manifest.json\"", ledger_view)
        self.assertEqual({"Matterport", "3DVista"}, set(exports))
        self.assertIn("not Chummer-authored runsite scans", manifest["claimBoundary"])
        self.assertEqual("/media/ledger/tours/black-ledger-3dvista-flythrough.mp4", manifest["flythrough"]["videoUrl"])
        self.assertIn("/media/ledger/tours/black-ledger-3dvista-flythrough.mp4", ledger_view)

        for provider, item in exports.items():
            viewer_url = item["viewerUrl"]
            parsed = urlparse(viewer_url)
            self.assertEqual("https", parsed.scheme, provider)
            self.assertNotIn("placeholder", viewer_url.lower(), provider)
            self.assertNotIn("localhost", parsed.netloc.lower(), provider)
            self.assertNotIn("chummer-api", parsed.netloc.lower(), provider)
            self.assertIn(viewer_url, ledger_view, provider)
            self.assertEqual("real_external_viewer_link", item["integrationStatus"], provider)


if __name__ == "__main__":
    unittest.main()
