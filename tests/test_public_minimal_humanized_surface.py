from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_main_public_routes_use_minimal_surface_contract() -> None:
    landing = read("Chummer.Run.Api/Views/PublicLanding/Landing.cshtml")
    downloads = read("Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml")
    status = read("Chummer.Run.Api/Views/PublicLanding/Status.cshtml")
    horizons = read("Chummer.Run.Api/Views/PublicLanding/Horizons.cshtml")
    product_story = read("Chummer.Run.Api/Views/PublicLanding/ProductStory.cshtml")
    faq = read("Chummer.Run.Api/Views/PublicLanding/Faq.cshtml")
    trust_page = read("Chummer.Run.Api/Views/PublicLanding/TrustPage.cshtml")

    for source in (landing, downloads, status, horizons, product_story, faq):
        assert 'surface-minimal' in source

    assert 'surface-help surface-minimal' in trust_page
    assert 'minimal-help-grid' in trust_page
    assert 'minimal-help-card' in trust_page
    assert 'Pick one path' in trust_page
    assert 'other options below' in trust_page
    assert 'other routes below' not in trust_page


def test_help_and_contact_pages_clean_dynamic_copy_before_rendering() -> None:
    trust_page = read("Chummer.Run.Api/Views/PublicLanding/TrustPage.cshtml")

    for expected in (
        'ViewData["Title"] = PublicFacingCopyHumanizer.Clean(Model.Heading);',
        "@PublicText(Model.Eyebrow)",
        "@PublicText(Model.Heading)",
        "@PublicText(Model.Intro)",
        "@PublicText(action.Label)",
        "@PublicText(point)",
        "@PublicText(fact.Tag)",
        "@PublicText(fact.Heading)",
        "@PublicText(fact.Summary)",
        "@PublicText(choice.Badge)",
        "@PublicText(choice.Label)",
        "@PublicText(pageSection.Eyebrow)",
        "@PublicText(pageSection.Body)",
        "@PublicText(Model.SupportIntake.Heading)",
        "@PublicText(Model.SupportIntake.Intro)",
        "@PublicText(Model.SupportIntake.SubmissionNotice)",
        "@PublicText(option.Label)",
        "@PublicText(option.Description)",
        "@PublicText(Model.SupportIntake.AccountSupportLabel)",
        "@PublicText(Model.SupportIntake.InstallAccessLabel)",
        "@PublicText(Model.SupportIntake.ResponseExpectation)",
        "@PublicText(Model.SupportIntake.InstallRailSummary)",
        "@PublicText(Model.SupportIntake.InstallRailLabel)",
    ):
        assert expected in trust_page

    for forbidden in (
        'ViewData["Title"] = Model.Heading;',
        ">@Model.Eyebrow</p>",
        ">@Model.Heading</h1>",
        ">@Model.Intro</p>",
        ">@action.Label</a>",
        "<span>@point</span>",
        "<span>@fact.Tag</span>",
        "<strong>@fact.Heading</strong>",
        "<p>@fact.Summary</p>",
        "<span>@choice.Badge</span>",
        ">@choice.Label</a>",
        "<p class=\"eyebrow\">@pageSection.Eyebrow</p>",
        "<p>@pageSection.Body</p>",
        "<h2>@Model.SupportIntake.Heading</h2>",
        "<p>@Model.SupportIntake.Intro</p>",
        "@Model.SupportIntake.SubmissionNotice</p>",
        "<h3>@option.Label</h3>",
        "<p>@option.Description</p>",
        ">@Model.SupportIntake.AccountSupportLabel</a>",
        ">@Model.SupportIntake.InstallAccessLabel</a>",
        "<p class=\"muted-copy\">@Model.SupportIntake.ResponseExpectation</p>",
        "<p>@Model.SupportIntake.InstallRailSummary</p>",
        ">@Model.SupportIntake.InstallRailLabel</a>",
    ):
        assert forbidden not in trust_page


def test_faq_page_cleans_dynamic_public_copy_before_rendering() -> None:
    faq = read("Chummer.Run.Api/Views/PublicLanding/Faq.cshtml")

    for expected in (
        "@PublicText(Model.Eyebrow)",
        "@PublicText(Model.Heading)",
        "@PublicText(Model.Intro)",
        "@PublicText(action.Label)",
        "@PublicText(choice.Badge)",
        "@PublicText(choice.Title)",
        "@PublicText(choice.Summary)",
        "@PublicText(choice.Label)",
        "@PublicText(faqSection.Title)",
        "@PublicText(entry.Question)",
        "@PublicText(entry.Answer)",
    ):
        assert expected in faq

    for forbidden in (
        ">@Model.Eyebrow</p>",
        ">@Model.Heading</h1>",
        ">@Model.Intro</p>",
        ">@action.Label</a>",
        "<span class=\"tag\">@choice.Badge</span>",
        "<h3>@choice.Title</h3>",
        "<p>@choice.Summary</p>",
        ">@choice.Label</a>",
        "<summary>@entry.Question</summary>",
        "<p>@entry.Answer</p>",
    ):
        assert forbidden not in faq


def test_downloads_and_status_clean_dynamic_release_copy_before_rendering() -> None:
    downloads = read("Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml")
    status = read("Chummer.Run.Api/Views/PublicLanding/Status.cshtml")
    combined = "\n".join((downloads, status))

    for expected in (
        "static string PublicDownloadText(string? value) => PublicFacingCopyHumanizer.Clean(value);",
        "@PublicDownloadText(Model.Manifest.Message)",
        "@PublicDownloadText(package.Summary)",
        "@PublicDownloadText(platform.Summary)",
        "static string PublicStatusText(string? value) => PublicFacingCopyHumanizer.Clean(value);",
        "@PublicStatusText(Model.ReleaseSummary)",
        "@PublicStatusText(platform.Summary)",
    ):
        assert expected in combined

    for forbidden in (
        "<p>@Model.Manifest.Message</p>",
        "<p>@package.Summary</p>",
        "<p>@platform.Summary</p>",
        "<p>@Model.ReleaseSummary</p>",
    ):
        assert forbidden not in combined


def test_download_dispatch_cleans_dynamic_public_copy_before_rendering() -> None:
    dispatch = read("Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml")

    for expected in (
        "static string PublicDispatchText(string? value) => PublicFacingCopyHumanizer.Clean(value);",
        "static string PublicDispatchTextOr(string? value, string fallback)",
        "@PublicDispatchText(Model.Eyebrow)",
        "@PublicDispatchText(Model.Heading)",
        "@PublicDispatchText(Model.Summary)",
        "@PublicDispatchText(Model.DispatchNote)",
        "@PublicDispatchText(Model.BootstrapCommandNote)",
        "@PublicDispatchText(Model.CurrentReleaseSummary)",
        "@PublicDispatchText(choice.Badge)",
        "@PublicDispatchText(choice.Title)",
        "@PublicDispatchText(choice.Summary)",
        "@PublicDispatchText(item)",
        "@PublicDispatchText(choice.Label)",
        "@PublicDispatchText(Model.SecondaryDownloadLabel)",
        "@PublicDispatchText(Model.CopyCommandLabel)",
        "@PublicDispatchText(Model.DownloadLabel)",
        "@PublicDispatchText(Model.AccountLabel)",
        "@PublicDispatchText(Model.SupportLabel)",
        "@PublicDispatchText(Model.HelpLabel)",
        "@PublicDispatchText(Model.ArtifactSupportLine)",
    ):
        assert expected in dispatch

    for forbidden in (
        "<p class=\"eyebrow\">@Model.Eyebrow</p>",
        "<h1 class=\"page-title\">@Model.Heading</h1>",
        "@Model.CurrentReleaseSummary.</p>",
        "<span class=\"tag\">@choice.Badge</span>",
        "<h3>@choice.Title</h3>",
        "<p>@choice.Summary</p>",
        "<span>@item</span>",
        ">@choice.Label</a>",
        ">@Model.SecondaryDownloadLabel</a>",
        ">@Model.CopyCommandLabel</button>",
        ">@Model.DownloadLabel</a>",
        ">@Model.AccountLabel</a>",
        ">@Model.SupportLabel</a>",
        ">@Model.HelpLabel</a>",
    ):
        assert forbidden not in dispatch


def test_public_front_door_hides_unready_campaign_and_ai_language() -> None:
    landing = read("Chummer.Run.Api/Views/PublicLanding/Landing.cshtml")
    horizons = read("Chummer.Run.Api/Views/PublicLanding/Horizons.cshtml")
    product_story = read("Chummer.Run.Api/Views/PublicLanding/ProductStory.cshtml")

    for source in (landing, horizons, product_story):
        assert "Black Ledger" not in source
        assert "generated by AI" not in source
        assert "AI-generated" not in source
        assert "proof receipt" not in source
        assert "artifact-gallery" not in source

    assert "Not the front door" in horizons
    assert "Downloads first" in horizons


def test_homepage_has_minimal_product_video_surface() -> None:
    landing = read("Chummer.Run.Api/Views/PublicLanding/Landing.cshtml")
    site_css = read("Chummer.Run.Api/wwwroot/css/site.css")

    assert 'class="minimal-video"' in landing
    assert 'aria-label="Product video"' in landing
    assert "/media/promo/chummer6-flagship-promo.mp4" in landing
    assert "/media/promo/chummer6-flagship-promo.webm" in landing
    assert "/media/promo/chummer6-flagship-promo.vtt" in landing
    assert ".minimal-video" in site_css
    assert "aspect-ratio: 16 / 9;" in site_css

    for forbidden in (
        "proof",
        "receipt",
        "artifact",
        "generated by AI",
        "AI-generated",
    ):
        assert forbidden not in landing


def test_public_views_use_neutral_note_markup_instead_of_proof_markup() -> None:
    public_views = [
        "Chummer.Run.Api/Views/PublicLanding/Changelog.cshtml",
        "Chummer.Run.Api/Views/PublicLanding/Feedback.cshtml",
        "Chummer.Run.Api/Views/PublicLanding/Participate.cshtml",
    ]

    for view_path in public_views:
        source = read(view_path)
        assert "workflow-card__proof" not in source
        assert "workflow-card__note" in source


def test_participation_surface_uses_plain_character_helper_copy() -> None:
    participate = read("Chummer.Run.Api/Views/PublicLanding/Participate.cshtml")

    assert "Character help preview" in participate
    assert "Open character helper" in participate
    assert "@PublicText(card.Card.Summary)" in participate
    assert "@PublicText(milestone.CasualSummary)" in participate

    for forbidden in (
        "ALICE build ghosts",
        "Build Ghost concierge",
        "Open Build Ghost",
        "generated by AI",
        "AI-generated",
    ):
        assert forbidden not in participate


def test_character_helper_page_uses_account_helper_language() -> None:
    helper = read("Chummer.Run.Api/Views/PublicLanding/BuildGhostConcierge.cshtml")

    assert "Account helper" in helper
    assert "The account helper keeps tradeoffs" in helper

    for forbidden in (
        "Signed-in helper",
        "The signed-in helper keeps tradeoffs",
    ):
        assert forbidden not in helper


def test_participation_surface_uses_plain_decision_and_account_language() -> None:
    participate = read("Chummer.Run.Api/Views/PublicLanding/Participate.cshtml")

    for expected in (
        "Account-only programs stay below the fold",
        "account options visible",
        "Keep the public loop simple and keep final decisions in Chummer.",
        "Chummer makes the final call",
        "Account participation",
        "Use the account path when public signal is not enough",
        "optional account paths",
    ):
        assert expected in participate

    for forbidden in (
        "signed-in programs stay below the fold",
        "signed-in options visible",
        "Keep the public loop visible, but keep authority inside Chummer.",
        "Chummer keeps the authority",
        "Signed-in participation",
        "Use the signed-in path when public signal is not enough",
        "optional signed-in paths",
    ):
        assert forbidden not in participate


def test_signal_packet_source_uses_plain_public_copy_labels() -> None:
    packet = read("Chummer.Run.Api/Views/Shared/_PublicSignalProjectionPacket.cshtml")

    assert "Open the Chummer page" in packet
    assert "How this works" in packet
    assert "Limits" in packet
    assert "Public feedback can move into review" in packet
    assert "guided review path" in packet

    for forbidden in (
        "Open first-party fallback",
        "Boundary conditions",
        "sourceReceipts",
        "canonicalSources",
        "journeyProofEvents",
        "guided synthesis lane",
        "guided review lane",
    ):
        assert forbidden not in packet


def test_karma_forge_surfaces_use_plain_review_language() -> None:
    controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")
    karma_forge = read("Chummer.Run.Api/Views/PublicLanding/KarmaForge.cshtml")
    karma_submitted = read("Chummer.Run.Api/Views/PublicLanding/KarmaForgeSubmitted.cshtml")
    combined = "\n".join((controller, karma_forge, karma_submitted))

    assert "guided review path" in combined
    assert "review path" in combined
    assert "id=\"review-next-steps\"" in karma_submitted
    assert "Request intake" in controller
    assert "Turn one table pain into a clear Chummer request" in controller
    assert "KARMA FORGE request saved" in controller
    assert "The request is saved. Chummer can now show the likely review route and the next questions." in controller
    assert "Consent must be accepted before Chummer can save the request." in controller
    assert "Account history keeps recent requests and next steps together." in karma_forge
    assert "Account submissions stay visible here with current queue status." in karma_forge
    assert "No account KARMA FORGE requests are visible on this account yet." in karma_forge
    assert "new PublicNavigationLink(\"Saved details\", \"#saved-details\")" in karma_submitted
    assert "id=\"saved-details\"" in karma_submitted
    assert 'journeyRef.EventKey.Replace("_", " ", StringComparison.OrdinalIgnoreCase)' in karma_submitted

    for forbidden in (
        "Signed-in history keeps recent requests and next steps together.",
        "<p class=\"eyebrow\">Signed-in history</p>",
        "Signed-in submissions stay visible here with current queue status.",
        "No signed-in KARMA FORGE requests are visible on this account yet.",
        "guided synthesis lane",
        "guided review lane",
        "bounded-followthrough",
        "new PublicNavigationLink(\"Next steps\", \"#bounded-followthrough\")",
        "Chummer-owned intake for house-rule, campaign, and trust-friction discovery packets.",
        "Governed discovery intake",
        "Turn one table pain into named Chummer-owned packets",
        "KARMA FORGE packet receipt",
        "The normalized packet, decision path",
        "KARMA FORGE intake receipt",
        "The intake is now visible as a Chummer packet",
        "Consent must be accepted before the intake can become a Chummer packet.",
        "Sample campaign amendment packet",
        "Sample seeded receipt proving",
        "first-party packet payload",
        "governed campaign package lane",
        "Keep the public receipt bounded",
        "demand packet before Product Governor",
        "governed review rail",
        "new PublicNavigationLink(\"Saved details\", \"#packet-json\")",
        "id=\"packet-json\"",
        "<h3>@SanitizePublicText(journeyRef.EventKey)</h3>",
    ):
        assert forbidden not in combined


def test_public_intake_pages_clean_dynamic_route_and_stage_copy() -> None:
    karma_forge = read("Chummer.Run.Api/Views/PublicLanding/KarmaForge.cshtml")
    feedback = read("Chummer.Run.Api/Views/PublicLanding/Feedback.cshtml")

    for expected in (
        'ViewData["Title"] = PublicFacingCopyHumanizer.Clean(Model.Heading);',
        "@SanitizePublicText(Model.Eyebrow)",
        "@SanitizePublicText(Model.Heading)",
        "@SanitizePublicText(choice.Badge)",
        "@SanitizePublicText(choice.Title)",
        "@SanitizePublicText(choice.Summary)",
        "@SanitizePublicText(item)",
        "@SanitizePublicText(choice.Label)",
        "@SanitizePublicText(stage.Status.Replace",
        "@SanitizePublicText(stage.ActionLabel)",
        "@SanitizePublicText(option.Label)",
        "@SanitizePublicText(Model.SelectedTrack.Family)",
    ):
        assert expected in karma_forge

    for expected in (
        "static string PublicFeedbackText(string? value) => PublicFacingCopyHumanizer.Clean(value);",
        "@PublicFeedbackText(choice.Badge)",
        "@PublicFeedbackText(choice.Title)",
        "@PublicFeedbackText(choice.Summary)",
        "@PublicFeedbackText(item)",
        "@PublicFeedbackText(choice.Label)",
        "@PublicFeedbackText(stage.Badge)",
        "@PublicFeedbackText(stage.Title)",
        "@PublicFeedbackText(stage.Summary)",
        "@PublicFeedbackText(stage.Note)",
        "@PublicFeedbackText(stage.Label)",
        "@PublicFeedbackText(card.Badge)",
        "@PublicFeedbackText(card.Title)",
        "@PublicFeedbackText(card.Summary)",
        "@PublicFeedbackText(card.Label)",
    ):
        assert expected in feedback

    for source in (karma_forge, feedback):
        for forbidden in (
            "<span class=\"tag\">@choice.Badge</span>",
            "<h3>@choice.Title</h3>",
            "<p>@choice.Summary</p>",
            "<span>@item</span>",
            ">@choice.Label</a>",
        ):
            assert forbidden not in source

    for forbidden in (
        "<p class=\"eyebrow\">@Model.Eyebrow</p>",
        "<h1 class=\"page-title\">@Model.Heading</h1>",
        "<h3>@stage.Status.Replace",
        ">@stage.ActionLabel</a>",
        ">@option.Label</option>",
        "@Model.SelectedTrack.Family prompts",
    ):
        assert forbidden not in karma_forge

    for forbidden in (
        "<span class=\"tag\">@stage.Badge</span>",
        "<h3>@stage.Title</h3>",
        "<p>@stage.Summary</p>",
        "<p class=\"workflow-card__note\">@stage.Note</p>",
        ">@stage.Label</a>",
        "PublicFacingCopyHumanizer.Clean(card.Badge)",
        "PublicFacingCopyHumanizer.Clean(card.Title)",
        "PublicFacingCopyHumanizer.Clean(card.Summary)",
        "PublicFacingCopyHumanizer.Clean(card.Label)",
    ):
        assert forbidden not in feedback


def test_connected_table_pulse_sources_do_not_keep_legacy_marker_comments() -> None:
    sources = [
        read("Chummer.Run.Api/Views/Accounts/Account.cshtml"),
        read("Chummer.Run.Api/Views/PublicLanding/Landing.cshtml"),
        read("Chummer.Run.Api/Views/PublicLanding/Home.cshtml"),
        read("Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml"),
        read("Chummer.Run.Api/Views/PublicLanding/MediaArtifactHorizon.cshtml"),
    ]
    combined = "\n".join(sources)

    for forbidden in (
        "legacy source marker",
        "command-to-fallout lane",
        "Aftermath return lane",
        "Open aftermath rail",
        "governed workspace",
        "Connected lane",
        "Release proof",
        "Open starter lane on Home",
        "Starter lane",
        "Campaign-ready lane",
    ):
        assert forbidden not in combined


def test_public_humanizer_cleans_plural_internal_terms() -> None:
    humanizer = read("Chummer.Run.Api/Services/PublicFacingCopyHumanizer.cs")

    for phrase in (
        '("receipts", "records")',
        '("artifacts", "files")',
        '("proofs", "status details")',
        '("operators", "maintainers")',
        '("assistants", "help")',
    ):
        assert phrase in humanizer


def test_login_surface_uses_plain_account_and_claim_copy_language() -> None:
    entry = read("Chummer.Run.Api/Views/Auth/Entry.cshtml")

    assert "Claim your copy" in entry
    assert "Claim with email" in entry
    assert "Claim with your account" in entry

    for forbidden in (
        "Campaign OS",
        "roadmap follows",
        "preview interest",
        "optional participation state",
        "claim tickets",
    ):
        assert forbidden not in entry


def test_downloads_surface_hides_account_handoff_noise() -> None:
    downloads = read("Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml")

    assert "Stable" in downloads
    assert "Nightly" in downloads
    assert "Windows" in downloads
    assert "Linux" in downloads
    assert "stableAndNightlyMatch" in downloads
    assert "Nightly currently matches Stable" in downloads
    assert "There is no newer Nightly available" in downloads

    for forbidden in (
        "Signed-in download",
        "recommended download",
        "manual activation",
        "install ticket",
        "short-lived install ticket",
        "Claim code",
        "claim code",
        "portable",
        "proof",
        "receipt",
        "Checked",
    ):
        assert forbidden not in downloads

    assert "Updated" in downloads


def test_minimal_palette_stays_neutral_and_readable() -> None:
    site_css = read("Chummer.Run.Api/wwwroot/css/site.css")

    assert "--minimal-page: #f7f8fa;" in site_css
    assert "--minimal-surface: #ffffff;" in site_css
    assert "rgba(255, 255, 255, 0.92)" in site_css
    assert "--minimal-page: #f7f6f2;" not in site_css
    assert "--minimal-surface: #fffefa;" not in site_css
    assert "--minimal-soft: #ece8df;" not in site_css
    assert ".surface-minimal .field input" in site_css
    assert ".surface-minimal .field select option" in site_css


def test_public_form_controls_have_os_dark_safe_defaults() -> None:
    site_css = read("Chummer.Run.Api/wwwroot/css/site.css")

    assert 'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"])' in site_css
    assert "select option,\nselect optgroup" in site_css
    assert "color-scheme: light;" in site_css
    assert "caret-color: var(--ink-strong);" in site_css
    assert "background: #ffffff;" in site_css
    assert "color: var(--ink-strong);" in site_css
    assert "::placeholder" in site_css
    assert "opacity: 1;" in site_css


def test_public_copy_uses_maintenance_language_instead_of_horizon_metaphor() -> None:
    sources = [
        read("Chummer.Run.Api/Views/PublicLanding/Horizons.cshtml"),
        read("Chummer.Run.Api/Views/PublicLanding/FeatureDetail.cshtml"),
        read("Chummer.Run.Api/Views/PublicLanding/_FeatureDetailRoadmap.cshtml"),
        read("Chummer.Run.Api/Views/PublicLanding/Participate.cshtml"),
    ]
    combined = "\n".join(sources)

    for forbidden in (
        "Why this horizon matters now",
        "What following this horizon means",
        "This page names the horizon",
        "Move to Horizons",
        "current horizon",
        "named horizons",
        "Horizons already carrying public movement",
    ):
        assert forbidden not in combined

    assert "Maintenance" in combined
    assert "planned work" in combined


def test_roadmap_pages_clean_dynamic_copy_before_rendering() -> None:
    roadmap = read("Chummer.Run.Api/Views/PublicLanding/Roadmap.cshtml")
    roadmap_detail = read("Chummer.Run.Api/Views/PublicLanding/_FeatureDetailRoadmap.cshtml")
    live_detail = read("Chummer.Run.Api/Views/PublicLanding/_FeatureDetailLiveProof.cshtml")
    preview_detail = read("Chummer.Run.Api/Views/PublicLanding/_FeatureDetailPreviewConcept.cshtml")

    for required in (
        "@CalmRoadmapText(milestone.StatusLabel)",
        "@CalmRoadmapText(dependency.StatusLabel)",
        "@CalmRoadmapText(signalLoop.FollowSettingsLabel)",
    ):
        assert required in roadmap

    for required in (
        "static string RoadmapText(string? value)",
        "@RoadmapText(Model.Pain)",
        "@RoadmapText(Model.Payoff)",
        "@RoadmapText(Model.PrimaryAction.Label)",
    ):
        assert required in roadmap_detail

    for forbidden in (
        "@milestone.StatusLabel",
        "@dependency.StatusLabel",
        "@signalLoop.FollowSettingsLabel",
    ):
        assert forbidden not in roadmap

    for forbidden in (
        "@Model.Pain",
        "@Model.Payoff",
        "@Model.PrimaryAction.Label",
    ):
        assert forbidden not in roadmap_detail

    for source in (live_detail, preview_detail):
        for required in (
            "PublicFacingCopyHumanizer.Clean(Model.Pain)",
            "PublicFacingCopyHumanizer.Clean(Model.Payoff)",
            "PublicFacingCopyHumanizer.Clean(Model.PrimaryAction.Label)",
        ):
            assert required in source

        for forbidden in (
            "<p>@Model.Pain</p>",
            "<p>@Model.Payoff</p>",
            ">@Model.PrimaryAction.Label</a>",
        ):
            assert forbidden not in source


def test_campaign_city_pages_do_not_render_maintenance_console_words() -> None:
    ledger_account = read("Chummer.Run.Api/Views/PublicLanding/LedgerAccountHome.cshtml")
    ledger_advisory = read("Chummer.Run.Api/Views/PublicLanding/LedgerAdvisory.cshtml")
    ledger_onboarding = read("Chummer.Run.Api/Views/PublicLanding/LedgerOnboarding.cshtml")
    ledger = read("Chummer.Run.Api/Views/PublicLanding/Ledger.cshtml")
    ledger_create = read("Chummer.Run.Api/Views/PublicLanding/LedgerFactionCreate.cshtml")
    ledger_promo = read("Chummer.Run.Api/Views/PublicLanding/LedgerFactionPromo.cshtml")
    ledger_workspace = read("Chummer.Run.Api/Views/PublicLanding/LedgerFactionWorkspace.cshtml")
    ledger_leader = read("Chummer.Run.Api/Views/PublicLanding/LedgerLeaderBriefing.cshtml")
    ledger_notifications = read("Chummer.Run.Api/Views/PublicLanding/LedgerNotifications.cshtml")
    ledger_validation = read("Chummer.Run.Api/Views/PublicLanding/LedgerWorldTickValidation.cshtml")
    sources = [
        ledger,
        ledger_account,
        ledger_advisory,
        ledger_onboarding,
        ledger_promo,
        ledger_workspace,
        ledger_notifications,
        ledger_leader,
        ledger_validation,
    ]
    combined = "\n".join(sources)

    for forbidden in (
        "Posture:",
        "Executive posture",
        "Current page posture",
        "Table posture",
        "Broadcast posture",
        "Quality checklist",
        "Your browser does not support HTML5 video playback for this route.",
        "platform posture",
        "Trust posture is not available",
        "aggregate install posture",
        "faction posture",
        "management posture",
        "Cross-district posture",
        "Verdict:",
        "Connected command lane",
        "Connected command path",
        "Faction workspace lanes",
        "Onboarding command lanes",
        "Fallback mode:",
        "faction-storyboard-frame__proof",
    ):
        assert forbidden not in combined

    assert "PublicFacingCopyHumanizer.Clean(Model.Promo.ProviderStatus)" in combined
    assert "PublicFacingCopyHumanizer.Clean(Model.PromoArtifact.ProviderStatus)" in combined
    assert "Your browser cannot play this video here." in combined

    for required in (
        "PublicFacingCopyHumanizer.Clean(Model.Eyebrow)",
        "PublicFacingCopyHumanizer.Clean(Model.Heading)",
        "PublicFacingCopyHumanizer.Clean(Model.Intro)",
        "PublicFacingCopyHumanizer.Clean(Model.PrimaryAction.Label)",
        "PublicFacingCopyHumanizer.Clean(Model.SecondaryAction.Label)",
        "PublicFacingCopyHumanizer.Clean(Model.World.PublicName)",
        "PublicFacingCopyHumanizer.Clean(Model.World.TurnHeadline)",
        "PublicFacingCopyHumanizer.Clean(Model.World.MapNote)",
        "PublicFacingCopyHumanizer.Clean(dispatch.Type)",
        "PublicFacingCopyHumanizer.Clean(dispatch.Title)",
        "PublicFacingCopyHumanizer.Clean(dispatch.Summary)",
        "PublicFacingCopyHumanizer.Clean(Model.NewsreelStatus.StatusLabel)",
        "PublicFacingCopyHumanizer.Clean(Model.NewsreelStatus.Summary)",
        "PublicFacingCopyHumanizer.Clean(Model.NewsreelStatus.ScopeLabel)",
        "PublicFacingCopyHumanizer.Clean(faction.Type)",
        "PublicFacingCopyHumanizer.Clean(faction.PublicName)",
        "PublicFacingCopyHumanizer.Clean(ledger.Label)",
        "PublicFacingCopyHumanizer.Clean(selectedFaction.PublicName)",
        "PublicFacingCopyHumanizer.Clean(accountCtaLabel)",
        "PublicFacingCopyHumanizer.Clean(selectedFaction.FactionLeader)",
        "PublicFacingCopyHumanizer.Clean(selectedFaction.FieldGm)",
        "PublicFacingCopyHumanizer.Clean(selectedFaction.IntelProvider)",
    ):
        assert required in ledger

    for forbidden in (
        '<p class="eyebrow">@Model.Eyebrow</p>',
        '<h1 class="page-title">@Model.Heading</h1>',
        '<p class="page-copy">@Model.Intro</p>',
        'data-primary-label="@Model.PrimaryAction.Label"',
        'data-secondary-label="@Model.SecondaryAction.Label"',
        'data-analytics-label="@Model.PrimaryAction.Label"',
        'data-analytics-label="@Model.SecondaryAction.Label"',
        ">@Model.PrimaryAction.Label</a>",
        ">@Model.SecondaryAction.Label</a>",
        '<h2 class="editorial-title">@Model.World.PublicName</h2>',
        '<p class="editorial-copy">@Model.World.TurnHeadline</p>',
        '<p class="muted-copy">@Model.World.MapNote</p>',
        '<span class="tag">@dispatch.Type</span>',
        "<h3>@dispatch.Title</h3>",
        "<p>@dispatch.Summary</p>",
        '<h2 class="editorial-title">@Model.NewsreelStatus.StatusLabel</h2>',
        '<p class="editorial-copy">@Model.NewsreelStatus.Summary</p>',
        "<span>Scope: @Model.NewsreelStatus.ScopeLabel</span>",
        '<span class="tag">@faction.Type</span>',
        "<h3>@faction.PublicName</h3>",
        '<span class="score-ledger__label">@ledger.Label</span>',
        '<h2 class="editorial-title">@selectedFaction.PublicName</h2>',
        ">@accountCtaLabel</a>",
    ):
        assert forbidden not in ledger

    for required in (
        'ViewData["Title"] = PublicFacingCopyHumanizer.Clean(Model.Heading);',
        "PublicFacingCopyHumanizer.Clean(Model.Faction.PublicName)",
        "PublicFacingCopyHumanizer.Clean(action.Label)",
        "PublicFacingCopyHumanizer.Clean(action.Effect)",
        "PublicFacingCopyHumanizer.Clean(dispatch.Type)",
        "PublicFacingCopyHumanizer.Clean(dispatch.Title)",
        "PublicFacingCopyHumanizer.Clean(dispatch.Summary)",
    ):
        assert required in ledger_workspace

    for forbidden in (
        "<span>Faction: @Model.Faction.PublicName</span>",
        '<h2 class="editorial-title">@Model.Faction.PublicName</h2>',
        "<h3>@action.Label</h3>",
        "<p>@action.Effect</p>",
        '<span class="tag">@dispatch.Type</span>',
        "<h3>@dispatch.Title</h3>",
        "<p>@dispatch.Summary</p>",
    ):
        assert forbidden not in ledger_workspace

    for required in (
        "PublicFacingCopyHumanizer.Clean(Model.Faction.PublicName)",
        "PublicFacingCopyHumanizer.Clean(Model.WorldTurnBriefing.TransitionLabel)",
        "PublicFacingCopyHumanizer.Clean(Model.WorldTurnBriefing.InboxHeadline)",
        "PublicFacingCopyHumanizer.Clean(item)",
    ):
        assert required in ledger_account

    for required in (
        "PublicFacingCopyHumanizer.Clean(Model.Heading)",
        "PublicFacingCopyHumanizer.Clean(Model.Summary.Heading)",
        "PublicFacingCopyHumanizer.Clean(Model.Summary.Intro)",
        "PublicFacingCopyHumanizer.Clean(ballot.AudienceLabel)",
        "PublicFacingCopyHumanizer.Clean(ballot.Heading)",
        "PublicFacingCopyHumanizer.Clean(option.Label)",
        "PublicFacingCopyHumanizer.Clean(summary.Heading)",
        "PublicFacingCopyHumanizer.Clean(item)",
    ):
        assert required in ledger_advisory

    for source in (ledger_account, ledger_advisory):
        for forbidden in (
            "<span>Faction: @Model.Faction.PublicName</span>",
            "<p class=\"eyebrow\">@Model.WorldTurnBriefing.TransitionLabel</p>",
            "<h2 class=\"editorial-title\">@Model.WorldTurnBriefing.InboxHeadline</h2>",
            "<h1 class=\"page-title\">@Model.Heading</h1>",
            "<h2 class=\"editorial-title\">@Model.Summary.Heading</h2>",
            "<p class=\"editorial-copy\">@Model.Summary.Intro</p>",
            "<span class=\"tag\">@ballot.AudienceLabel</span>",
            "<h3>@ballot.Heading</h3>",
            "@option.Label · @option.VoteShareLabel",
            "<span>@option.Label: @option.VoteCount vote(s)</span>",
            "<h3>@summary.Heading</h3>",
            "<span>@item</span>",
        ):
            assert forbidden not in source

    for required in (
        "PublicFacingCopyHumanizer.Clean(Model.Heading)",
        "PublicFacingCopyHumanizer.Clean(Model.Intro)",
        "PublicFacingCopyHumanizer.Clean(step.Label)",
        "PublicFacingCopyHumanizer.Clean(Model.ExistingFactionSummary)",
        "PublicFacingCopyHumanizer.Clean(faction.Type)",
        "PublicFacingCopyHumanizer.Clean(faction.PublicName)",
        "PublicFacingCopyHumanizer.Clean(faction.Summary)",
        "PublicFacingCopyHumanizer.Clean(Model.MajorFounderSummary)",
        "PublicFacingCopyHumanizer.Clean(Model.ChallengerFounderSummary)",
        "PublicFacingCopyHumanizer.Clean(Model.MajorSlotsWarning)",
    ):
        assert required in ledger_onboarding

    for required in (
        "PublicFacingCopyHumanizer.Clean(Model.Heading)",
        "PublicFacingCopyHumanizer.Clean(Model.Intro)",
        "PublicFacingCopyHumanizer.Clean(archetype.Name)",
        "PublicFacingCopyHumanizer.Clean(rival.PublicName)",
        "PublicFacingCopyHumanizer.Clean(perk.Name)",
        "PublicFacingCopyHumanizer.Clean(flaw.Name)",
    ):
        assert required in ledger_create

    for required in (
        "PublicFacingCopyHumanizer.Clean(Model.Heading)",
        "PublicFacingCopyHumanizer.Clean(Model.Intro)",
        "PublicFacingCopyHumanizer.Clean(Model.Promo.StaticCardLabel)",
        "PublicFacingCopyHumanizer.Clean(Model.Promo.CampaignHook)",
        "PublicFacingCopyHumanizer.Clean(Model.Promo.StorylineSummary)",
        "PublicFacingCopyHumanizer.Clean(Model.Promo.PlaybackLabel)",
        "PublicFacingCopyHumanizer.Clean(Model.Promo.PublicName)",
        "PublicFacingCopyHumanizer.Clean(frame.Label)",
        "PublicFacingCopyHumanizer.Clean(frame.VisualHook)",
        "PublicFacingCopyHumanizer.Clean(frame.ActionBeat)",
        "PublicFacingCopyHumanizer.Clean(Model.Promo.CaptionLines[index])",
        "PublicFacingCopyHumanizer.Clean(Model.Promo.AudiencePromise)",
        "PublicFacingCopyHumanizer.Clean(scene.Label)",
        "PublicFacingCopyHumanizer.Clean(scene.Purpose)",
        "PublicFacingCopyHumanizer.Clean(scene.VisualDirection)",
        "PublicFacingCopyHumanizer.Clean(scene.NarratorLine)",
        "PublicFacingCopyHumanizer.Clean(format)",
    ):
        assert required in ledger_promo

    assert 'ViewData["Title"] = PublicFacingCopyHumanizer.Clean(Model.Heading);' in ledger_leader
    assert "PublicFacingCopyHumanizer.Clean(Model.Digest.PublicName)" in ledger_leader

    for source in (ledger_onboarding, ledger_create, ledger_promo, ledger_leader):
        for forbidden in (
            "<h1 class=\"page-title\">@Model.Heading</h1>",
            "<h1 class=\"editorial-title\">@Model.Heading</h1>",
            "<p class=\"page-copy\">@Model.Intro</p>",
            "<p class=\"editorial-copy\">@Model.Intro</p>",
            "<p class=\"editorial-copy\">@Model.ExistingFactionSummary</p>",
            "<span class=\"tag\">@faction.Type</span>",
            "<h3>@faction.PublicName</h3>",
            "<p class=\"muted-copy\">@faction.Summary</p>",
            "<p>@Model.MajorFounderSummary</p>",
            "<p>@Model.ChallengerFounderSummary</p>",
            ">@archetype.Name</option>",
            ">@rival.PublicName</option>",
            "@perk.Name (@perk.Cost)",
            "@flaw.Name (@(-flaw.Cost))",
            "<span>Faction: @Model.Digest.PublicName</span>",
            "<h2 class=\"editorial-title\">@Model.Digest.PublicName right now</h2>",
            "<h2 class=\"editorial-title\">@Model.Promo.StaticCardLabel</h2>",
            "<p class=\"editorial-copy\">@Model.Promo.StorylineSummary</p>",
            "<span>Mode: @Model.Promo.PlaybackLabel</span>",
            "<span class=\"tag\">@frame.Label</span>",
            "<h3>@Model.Promo.PublicName</h3>",
            "<p class=\"faction-storyboard-frame__visual\">@frame.VisualHook</p>",
            "<p class=\"faction-storyboard-frame__action\">@frame.ActionBeat</p>",
            "@Model.Promo.CaptionLines[index]",
            "<p class=\"editorial-copy\">@Model.Promo.AudiencePromise</p>",
            "<p>@scene.Purpose</p>",
            "<p>@scene.VisualDirection</p>",
            "<p>@scene.NarratorLine</p>",
            "<p>@format</p>",
        ):
            assert forbidden not in source

    for required in (
        "PublicFacingCopyHumanizer.Clean(option.Kind)",
        "PublicFacingCopyHumanizer.Clean(option.Label)",
        "PublicFacingCopyHumanizer.Clean(option.Summary)",
        "PublicFacingCopyHumanizer.Clean(option.ActionLabel)",
        "PublicFacingCopyHumanizer.Clean(Model.WorldTurnBriefing.TransitionLabel)",
        "PublicFacingCopyHumanizer.Clean(Model.WorldTurnBriefing.InboxHeadline)",
        "PublicFacingCopyHumanizer.Clean(Model.WorldTurnBriefing.NewsreelLead)",
        "PublicFacingCopyHumanizer.Clean(beat)",
        "PublicFacingCopyHumanizer.Clean(Model.WorldTurnBriefing.Broadcast.PackageLabel)",
        "PublicFacingCopyHumanizer.Clean(Model.WorldTurnBriefing.Broadcast.AnchorName)",
        "PublicFacingCopyHumanizer.Clean(Model.WorldTurnBriefing.Broadcast.DeskLabel)",
        "PublicFacingCopyHumanizer.Clean(beat.ActorKind)",
        "PublicFacingCopyHumanizer.Clean(beat.BeatLabel)",
        "PublicFacingCopyHumanizer.Clean(beat.ActorLabel)",
        "PublicFacingCopyHumanizer.Clean(message.Eyebrow)",
        "PublicFacingCopyHumanizer.Clean(message.Heading)",
        "PublicFacingCopyHumanizer.Clean(message.Summary)",
        "PublicFacingCopyHumanizer.Clean(message.StatusLabel)",
        "PublicFacingCopyHumanizer.Clean(message.CtaLabel)",
        "PublicFacingCopyHumanizer.Clean(Model.Status.StatusLabel)",
    ):
        assert required in ledger_notifications

    for required in (
        'ViewData["Title"] = PublicFacingCopyHumanizer.Clean(Model.Heading);',
        "PublicFacingCopyHumanizer.Clean(Model.Heading)",
        "PublicFacingCopyHumanizer.Clean(Model.Intro)",
        "PublicFacingCopyHumanizer.Clean(Model.Packet.WorldName)",
        "PublicFacingCopyHumanizer.Clean(Model.WorldTurnBriefing.TransitionLabel)",
        "PublicFacingCopyHumanizer.Clean(Model.WorldTurnBriefing.InboxHeadline)",
        "PublicFacingCopyHumanizer.Clean(Model.WorldTurnBriefing.NewsreelLead)",
        "PublicFacingCopyHumanizer.Clean(Model.LeaderDigest.PublicName)",
        "PublicFacingCopyHumanizer.Clean(item)",
    ):
        assert required in ledger_validation

    for source in (ledger_notifications, ledger_validation):
        for forbidden in (
            "<h3>@option.Label</h3>",
            "<p>@option.Summary</p>",
            ">@option.ActionLabel</button>",
            "<p class=\"eyebrow\">@Model.WorldTurnBriefing.TransitionLabel</p>",
            "<h2 class=\"editorial-title\">@Model.WorldTurnBriefing.InboxHeadline</h2>",
            "<p class=\"editorial-copy\">@Model.WorldTurnBriefing.NewsreelLead</p>",
            "<p>@beat</p>",
            "<h2 class=\"editorial-title\">@Model.WorldTurnBriefing.Broadcast.PackageLabel</h2>",
            "<span>Anchor: @Model.WorldTurnBriefing.Broadcast.AnchorName</span>",
            "<span>Desk: @Model.WorldTurnBriefing.Broadcast.DeskLabel</span>",
            "<span class=\"tag\">@beat.ActorKind</span>",
            "<h4>@beat.BeatLabel</h4>",
            "<p class=\"ledger-newsreel-broadcast__action-actor\">@beat.ActorLabel</p>",
            "<span class=\"tag\">@message.Eyebrow</span>",
            "<h3>@message.Heading</h3>",
            "<p>@message.Summary</p>",
            "<span>Status: @message.StatusLabel</span>",
            ">@message.CtaLabel</a>",
            "<h2 class=\"editorial-title\">@Model.Status.StatusLabel</h2>",
            "<h1 class=\"page-title\">@Model.Heading</h1>",
            "<p class=\"page-copy\">@Model.Intro</p>",
            "<span>World: @Model.Packet.WorldName</span>",
            "<h2 class=\"editorial-title\">@Model.LeaderDigest.PublicName leader digest</h2>",
        ):
            assert forbidden not in source


def test_signed_in_account_copy_uses_files_status_and_plain_download_language() -> None:
    account = read("Chummer.Run.Api/Views/Accounts/Account.cshtml")

    for forbidden in (
        "The artifact stays the same for everyone",
        "Artifact shelf posture",
        "Current release posture",
        "Known help and trust posture",
        "Quiet support posture",
        "Recovery posture",
        "Trust posture",
        "artifacts ·",
        "Restore posture",
        "Recent return artifact",
        "Move governed roster state",
        "Transfer governed roster state",
        "Staleness posture",
        "Conflict posture",
        "Recoverability posture",
        "Continue posture",
        "Governed prep",
        "governed prep",
        "Governed packet",
        "governed packet",
        "GM operations posture",
        "Search posture",
        "Binding posture",
        "Artifact publication",
        "governed operator view",
        "governed view",
        "Issue governed",
        "No governed",
        "Recent governed",
        "governed public discovery",
        "workspace lanes",
        "Grounded rule answer",
        "Package posture",
        "Recap and artifact shelf",
        "waiting for governed",
        "Record:",
        "Evidence:",
        "Lead:",
        "Authority:",
        "Surface:",
        "Route:",
        "Recovery path:",
        "Recovery link:",
        "Lead recovery hint:",
        "Latest record observed:",
        "Entitlement conflict records",
        "Safe-to-continue history",
        "Refresh-before-continue items",
        "Record consent to continue this access request.",
        "Not resumable from this record.",
        "Source summary",
        "Stale source history",
        "Legacy migration records",
        "record(s)",
        "File record",
        "carry-forward record",
        " Source: @output.ProvenanceSummary",
        " Source: @PublicText(item.ProvenanceSummary)",
        " Source: @HumanizeStatus(consequence.Receipts[0].SourceKind",
        " Source: @answer.ProvenanceLabel",
        " Source: @publication.ProvenanceSummary",
        "Target operator groups",
        "Source campaign",
        "Operator note",
        "Source-linked hints",
        "Source hint:",
        "Operator groups",
        "You are not currently the operator",
        "Operator watchouts",
        "No reviewed season or event records are attached yet.",
        "The internal continuity bridge recorded a participation event.",
    ):
        assert forbidden not in account

    assert "The download stays the same for everyone" in account
    assert "Access conflicts" in account
    assert "Ready history" in account
    assert "Needs refresh" in account
    assert "Account update" in account
    assert "Restore update" in account
    assert "Details:" in account
    assert "Recap files" in account
    assert "Restore status" in account
    assert "Move roster state" in account
    assert "Prep packet" in account
    assert "GM operations status" in account
    assert "Binding status" in account
    assert "Package status" in account
    assert "Current release status" in account
    assert "Help and privacy" in account
    assert "Recovery status" in account
    assert "PublicText(" in account
    assert "Save consent to continue this access request." in account
    assert "Not resumable from this action." in account
    assert "Stale history" in account
    assert "Legacy migration history" in account
    assert "File detail" in account
    assert "Details: @PublicText(output.ProvenanceSummary)" in account
    assert "Details: @PublicText(item.ProvenanceSummary)" in account
    assert "Details: @PublicText(answer.ProvenanceLabel)" in account
    assert "Details: @PublicText(publication.ProvenanceSummary)" in account
    assert "Target groups" in account
    assert "Original campaign" in account
    assert "Move note" in account
    assert "Travel note" in account
    assert "Prep note" in account
    assert "Package note" in account
    assert "Hint: @sourceHintLine" in account
    assert "You do not currently manage a campaign" in account
    assert "No reviewed season or event activity is attached yet." in account
    assert "A participation event was saved." in account


def test_specialist_public_surfaces_hide_raw_record_identifiers() -> None:
    sources = {
        "package_receipt": read("Chummer.Run.Api/Views/PublicLanding/PackageReceipt.cshtml"),
        "knowledge_fabric": read("Chummer.Run.Api/Views/PublicLanding/KnowledgeFabric.cshtml"),
        "nexus_pan": read("Chummer.Run.Api/Views/PublicLanding/NexusPanContinuity.cshtml"),
        "anarchy": read("Chummer.Run.Api/Views/PublicLanding/Anarchy.cshtml"),
        "ledger_account": read("Chummer.Run.Api/Views/PublicLanding/LedgerAccountHome.cshtml"),
        "ledger_faction_workspace": read("Chummer.Run.Api/Views/PublicLanding/LedgerFactionWorkspace.cshtml"),
        "ledger_notifications": read("Chummer.Run.Api/Views/PublicLanding/LedgerNotifications.cshtml"),
    }
    combined = "\n".join(sources.values())

    for forbidden in (
        "@PublicPackageText(Model.Receipt.ReceiptId)",
        "<span>@receipt.ReceiptId</span>",
        "<span>@receipt.Provenance</span>",
        "<span>@receipt.Route</span>",
        "<h3>@receipt.ReceiptId</h3>",
        "<h3>@Model.ExplainReceipt.ReceiptId</h3>",
        "Source: @dispatch.SourceReceiptId",
        "Source: @Model.ExplainReceipt.SourceReceiptId",
        "Delivery: @receipt.DeliveryRef",
        "View record",
        "Record summary",
        "without losing the record",
        "The record keeps",
        "Package records should not become a support workaround",
        "Stored records",
        "Decision sources",
    ):
        assert forbidden not in combined

    assert "Saved action" in sources["package_receipt"]
    assert "without losing the saved action" in sources["package_receipt"]
    assert "Package activity should not become a support workaround" in sources["package_receipt"]
    assert "Portable runner explanation" in sources["anarchy"]
    assert "Recent decision" in sources["ledger_account"]
    assert "Recent decision" in sources["ledger_faction_workspace"]
    assert "Delivery attempt" in sources["ledger_notifications"]
    assert "Saved updates" in sources["ledger_notifications"]
    assert "PublicFacingCopyHumanizer.Clean(receipt.Provenance)" in sources["knowledge_fabric"]
    assert "PublicFacingCopyHumanizer.Clean(receipt.Route)" in sources["nexus_pan"]


def test_feedback_operations_detail_hides_provider_and_record_ids_from_cards() -> None:
    feedback_operations = read("Chummer.Run.Api/Views/PublicLanding/FeedbackOperationsDetail.cshtml")
    signal_operations = read("Chummer.Run.Api/Views/Shared/_PublicSignalOperationsPacket.cshtml")

    for forbidden in (
        "<span>@sourceReceipt.ReceiptId</span>",
        "<span>@sourceReceipt.ProviderEventId</span>",
        "<span>@receipt.ReceiptId</span>",
        "<span>@receipt.DeliveryId</span>",
        "<span>@receipt.RecipientRef</span>",
        "<span>@receipt.AddressHash</span>",
        "<span>@receipt.TemplateVersion</span>",
        "<span>@receipt.ConsentSourceRef</span>",
        "<span>@receipt.SuppressionCheck</span>",
        "<span>@receipt.GovernorDecisionRef</span>",
        "<span>@receipt.ProviderMessageId</span>",
        "<span>@receipt.DispatchReceiptId</span>",
        "<span>@thread.AddressHash</span>",
        "<span>@thread.DispatchReceiptId</span>",
        "<h3>@thread.RecipientRef</h3>",
        "<h3>@receipt.TemplateId",
        "<h3>@receipt.EventKey</h3>",
        "message record",
        "follow-up record",
        "routing record",
        "source record",
        "release record",
        "<p class=\"eyebrow\">Source item</p>",
        "The originating source item",
        "Open source details",
        "ReleaseProofReceiptId",
        "ReleaseProofRoute",
        "Download related data",
        "Download thread data",
        "Download item data",
    ):
        assert forbidden not in feedback_operations

    for forbidden in (
        "follow-up record",
        "posted follow-up record",
        "private-support crossover",
        "private-support item",
        "Category routing",
        "Public feedback stays easy to route.",
        "Public signal routing stays transparent",
    ):
        assert forbidden not in signal_operations

    assert "Original item" in feedback_operations
    assert "Open related details" in feedback_operations
    assert "Download related details" in feedback_operations
    assert "Download message details" in feedback_operations
    assert "Download item details" in feedback_operations
    assert "posted follow-up update" in signal_operations
    assert "message update" in feedback_operations
    assert "follow-up update" in feedback_operations
    assert "routing update" in feedback_operations
    assert "Recipient thread" in feedback_operations
    assert "Message updates" in feedback_operations
    assert "Message attempt" in feedback_operations
    assert "Follow-up sent" in feedback_operations
    assert "likely private support follow-up" in signal_operations
    assert "Feedback sorting" in signal_operations
    assert "Public feedback stays easy to sort." in signal_operations
    assert "Public feedback stays visible; private follow-up goes through Help." in signal_operations


def test_public_submission_and_home_pages_hide_raw_ids_and_source_labels() -> None:
    support_submitted = read("Chummer.Run.Api/Views/PublicLanding/SupportSubmitted.cshtml")
    karma_submitted = read("Chummer.Run.Api/Views/PublicLanding/KarmaForgeSubmitted.cshtml")
    home = read("Chummer.Run.Api/Views/PublicLanding/Home.cshtml")
    combined = "\n".join((support_submitted, karma_submitted, home))

    for forbidden in (
        "<span>@Model.CaseId</span>",
        "Keep the case id nearby",
        "one stable id",
        "same case id",
        "<span>@Model.SubmissionId</span>",
        "<span>@stage.ReceiptId</span>",
        "Source: @leadAftermathShelfEntry.ProvenanceSummary",
        "Output source: @output.ProvenanceSummary",
        "Source: @answer.ProvenanceLabel",
        "Source: @publication.ProvenanceSummary",
        "Source-linked hints",
        "Source hint:",
    ):
        assert forbidden not in combined

    assert "Report saved" in support_submitted
    assert "Submission saved" in karma_submitted
    assert "Step saved" in karma_submitted
    assert "Details: @PublicFacingCopyHumanizer.Clean(leadAftermathShelfEntry.ProvenanceSummary)" in home
    assert "Output details: @PublicFacingCopyHumanizer.Clean(output.ProvenanceSummary)" in home
    assert "Details: @PublicFacingCopyHumanizer.Clean(answer.ProvenanceLabel)" in home
    assert "Details: @PublicFacingCopyHumanizer.Clean(publication.ProvenanceSummary)" in home
    assert "Hint: @PublicText(sourceHintLine)" in home


def test_submitted_pages_clean_dynamic_public_copy_before_rendering() -> None:
    support_submitted = read("Chummer.Run.Api/Views/PublicLanding/SupportSubmitted.cshtml")
    karma_submitted = read("Chummer.Run.Api/Views/PublicLanding/KarmaForgeSubmitted.cshtml")

    for expected in (
        "static string PublicSupportSubmittedText(string? value) => PublicFacingCopyHumanizer.Clean(value);",
        "@PublicSupportSubmittedText(Model.Eyebrow)",
        "@PublicSupportSubmittedText(Model.Heading)",
        "@PublicSupportSubmittedText(Model.Intro)",
        "@PublicSupportSubmittedText(Model.StatusLabel.Replace('_', ' '))",
        "@PublicSupportSubmittedText(action.Label)",
        "@PublicSupportSubmittedText(Model.ResponseExpectation)",
        "@PublicSupportSubmittedText(item)",
        "@PublicSupportSubmittedText(route.Badge)",
        "@PublicSupportSubmittedText(route.Title)",
        "@PublicSupportSubmittedText(route.Summary)",
        "@PublicSupportSubmittedText(detail)",
        "@PublicSupportSubmittedText(route.Label)",
        "@PublicSupportSubmittedText(fact.Heading)",
        "@PublicSupportSubmittedText(fact.Summary)",
        "@PublicSupportSubmittedText(eventItem.Label)",
        "@PublicSupportSubmittedText(eventItem.Summary)",
    ):
        assert expected in support_submitted

    for expected in (
        'ViewData["Title"] = PublicFacingCopyHumanizer.Clean(Model.Heading);',
        "@SanitizePublicText(Model.Eyebrow)",
        "@SanitizePublicText(Model.Heading)",
        "@SanitizePublicText(Model.Intro)",
        "@SanitizePublicText(action.Label)",
        "@SanitizePublicText(stage.Status.Replace",
        "@SanitizePublicText(stage.ActionLabel)",
        "@SanitizePublicText(journeyRef.EventKey.Replace",
    ):
        assert expected in karma_submitted

    for source in (support_submitted, karma_submitted):
        for forbidden in (
            'ViewData["Title"] = Model.Heading;',
            "<p class=\"eyebrow\">@Model.Eyebrow</p>",
            "<h1 class=\"page-title\">@Model.Heading</h1>",
            "<p class=\"page-copy\">@Model.Intro</p>",
            ">@action.Label</a>",
        ):
            assert forbidden not in source

    for forbidden in (
        "<span>@Model.StatusLabel.Replace('_', ' ')</span>",
        "<strong>@item</strong>",
        "<span class=\"tag\">@route.Badge</span>",
        "<h3>@route.Title</h3>",
        "<p>@route.Summary</p>",
        "<span>@detail</span>",
        ">@route.Label</a>",
        "<h3>@fact.Heading</h3>",
        "@eventItem.Label</span>",
        "<strong>@eventItem.Summary</strong>",
        "later signed-in return path",
    ):
        assert forbidden not in support_submitted

    assert "later account return path" in support_submitted

    for forbidden in (
        "<h3>@stage.Status.Replace",
        ">@stage.ActionLabel</a>",
        "<h3>@journeyRef.EventKey</h3>",
    ):
        assert forbidden not in karma_submitted


def test_home_page_cleans_primary_and_coverage_dynamic_copy() -> None:
    home = read("Chummer.Run.Api/Views/PublicLanding/Home.cshtml")

    for expected in (
        "@PublicText(Model.PrimaryAction.Eyebrow)",
        "@PublicText(Model.PrimaryAction.Title)",
        "@PublicText(Model.PrimaryAction.Summary)",
        "@PublicText(Model.PrimaryAction.Label)",
        "@PublicText(Model.FlagshipCoverage.Eyebrow)",
        "@PublicText(card.Label)",
        "@PublicText(card.CurrentTitle)",
        "@PublicText(card.CurrentBody)",
        "@PublicText(card.TargetBody)",
        "@PublicText(card.ActionLabel)",
    ):
        assert expected in home

    for forbidden in (
        ">@Model.PrimaryAction.Label</button>",
        ">@Model.PrimaryAction.Label</a>",
        "<span class=\"tag\">@Model.PrimaryAction.Eyebrow</span>",
        "<h2 id=\"setupCardTitle\">@Model.PrimaryAction.Title</h2>",
        "<p id=\"setupCardCopy\">@Model.PrimaryAction.Summary</p>",
        "<p class=\"eyebrow\">@Model.FlagshipCoverage.Eyebrow</p>",
        "<span class=\"tag\">@card.Label</span>",
        "<h3>@card.CurrentTitle</h3>",
        "<p>@card.CurrentBody</p>",
        "<strong>Target:</strong> @card.TargetBody",
        ">@card.ActionLabel</a>",
    ):
        assert forbidden not in home


def test_home_page_uses_account_language_for_return_surface_copy() -> None:
    home = read("Chummer.Run.Api/Views/PublicLanding/Home.cshtml")

    for expected in (
        "Keep account access and work sections in the shared side panel.",
        "Account continuity cockpit",
        "The account cockpit answers this first",
        "Account flagship coverage",
        "account home view",
        "account reaction fallout",
    ):
        assert expected in home

    for forbidden in (
        "Keep signed-in access and work sections in the shared side panel.",
        "Signed-in continuity cockpit",
        "The signed-in cockpit answers",
        "Signed-in flagship coverage",
        "signed-in home view",
        "signed-in reaction fallout",
    ):
        assert forbidden not in home


def test_public_lookup_and_leaderboards_use_plain_history_language() -> None:
    lookup = read("Chummer.Run.Api/Views/PublicLanding/FeedbackOperationsLookup.cshtml")
    leaderboards = read("Chummer.Run.Api/Views/Leaderboards/Index.cshtml")
    combined = "\n".join((lookup, leaderboards))

    for forbidden in (
        "Search by source id",
        "Sources and threads",
        "Source records only",
        "Chummer records",
        "stored state",
        "source records",
        "No record or thread matched this query",
        "Open lookup artifact",
        "Open detail artifact",
        "<th scope=\"col\">Records</th>",
    ):
        assert forbidden not in combined

    assert "Search by item id" in lookup
    assert "Items and threads" in lookup
    assert "Items only" in lookup
    assert "Chummer history" in lookup
    assert "saved state" in lookup
    assert "saved items" in lookup
    assert "No item or thread matched this query" in lookup
    assert "Open lookup data" in lookup
    assert "Open detail data" in lookup
    assert "<th scope=\"col\">Entries</th>" in leaderboards


def test_specialized_public_pages_avoid_operator_artifact_record_copy() -> None:
    codex = read("Chummer.Run.Api/Views/CodexParticipation/Console.cshtml")
    release_upload = read("Chummer.Run.Api/Views/PublicLanding/ReleaseUpload.cshtml")
    gm_session = read("Chummer.Run.Api/Views/PublicLanding/GmSessionVenue.cshtml")
    ledger = read("Chummer.Run.Api/Views/PublicLanding/Ledger.cshtml")
    roadmap_detail = read("Chummer.Run.Api/Views/PublicLanding/_FeatureDetailRoadmap.cshtml")
    combined = "\n".join((codex, release_upload, gm_session, ledger, roadmap_detail))

    for forbidden in (
        "participation record",
        "keeps the record",
        "desktop artifact",
        "packaging artifacts",
        "validates the bundle",
        "platform artifact",
        "promoted artifact",
        "campaign record",
        "Source details",
        "publication record",
    ):
        assert forbidden not in combined

    assert "static string PublicReleaseUploadText(string? value) => PublicFacingCopyHumanizer.Clean(value);" in release_upload
    assert "@PublicReleaseUploadText(Model.Heading)" in release_upload
    assert "@PublicReleaseUploadText(Model.Summary)" in release_upload
    assert "@PublicReleaseUploadText(Model.WindowsUploadNote)" in release_upload

    for forbidden in (
        "<h1 class=\"page-title\">@Model.Heading</h1>",
        "<p class=\"page-copy\">@Model.Summary</p>",
        "<p>@Model.WindowsUploadNote</p>",
    ):
        assert forbidden not in release_upload

    assert "static string PublicGmVenueText(string? value) => PublicFacingCopyHumanizer.Clean(value);" in gm_session
    assert "@PublicGmVenueText(Model.FallbackMessage)" in gm_session
    assert "@PublicGmVenueText(Model.VenueStatus)" in gm_session
    assert "@PublicGmVenueText(Model.ScheduledTimeSummary)" in gm_session
    assert "@PublicGmVenueText(Model.PrivacyStatus)" in gm_session
    assert "@PublicGmVenueText(Model.ConsentStatus)" in gm_session
    assert "@PublicGmVenueText(Model.AttendeeSyncStatus)" in gm_session
    assert "@PublicGmVenueText(Model.ProviderCreateDisabledReason)" in gm_session
    assert "<h1 class=\"page-title\">@Model.SessionTitle</h1>" in gm_session
    assert "<h3>@Model.CampaignName</h3>" in gm_session

    for forbidden in (
        "<p class=\"muted-copy\">@Model.FallbackMessage</p>",
        "<h2>@Model.VenueStatus</h2>",
        "<h2>@Model.ScheduledTimeSummary</h2>",
        "<h2>@Model.PrivacyStatus / @Model.ConsentStatus</h2>",
        "Attendance sync: @Model.AttendeeSyncStatus",
        "<p>@PublicFacingCopyHumanizer.Clean(Model.ProviderCreateDisabledReason)</p>",
        "<h3>@Model.AttendeeSyncStatus</h3>",
    ):
        assert forbidden not in gm_session

    assert "participation history" in codex
    assert "keeps the history" in codex
    assert "desktop app" in release_upload
    assert "packaging files" in release_upload
    assert "accepts the bundle" in release_upload
    assert "platform file" in release_upload
    assert "promoted file" in release_upload
    assert "campaign history" in gm_session
    assert "Details</a>" in ledger
    assert "publication history" in roadmap_detail


def test_ready_for_tonight_cleans_primary_page_copy() -> None:
    ready = read("Chummer.Run.Api/Views/PublicLanding/ReadyForTonight.cshtml")

    assert 'ViewData["Title"] = PublicFacingCopyHumanizer.Clean(Model.Heading);' in ready
    assert "@PublicFacingCopyHumanizer.Clean(Model.Eyebrow)" in ready
    assert "@PublicFacingCopyHumanizer.Clean(Model.Heading)" in ready

    for forbidden in (
        'ViewData["Title"] = Model.Heading;',
        "<p class=\"eyebrow\">@Model.Eyebrow</p>",
        "<h1 class=\"page-title\">@Model.Heading</h1>",
    ):
        assert forbidden not in ready


def test_package_and_publication_pages_use_activity_and_details_language() -> None:
    packages = read("Chummer.Run.Api/Views/PublicLanding/Packages.cshtml")
    package_detail = read("Chummer.Run.Api/Views/PublicLanding/PackageDetail.cshtml")
    package_receipt = read("Chummer.Run.Api/Views/PublicLanding/PackageReceipt.cshtml")
    shelf = read("Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml")
    publication = read("Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml")
    combined = "\n".join((packages, package_detail, package_receipt, shelf, publication))

    for forbidden in (
        "Your recent package records",
        "Recent records",
        "No records yet",
        "Open record",
        "Source:",
        "<span class=\"tag\">Source</span>",
        "source context",
        "shared record",
        "creator-publication record",
        "required item",
    ):
        assert forbidden not in combined

    assert "Your recent package activity" in packages
    assert "Recent activity" in package_detail
    assert "Open activity" in package_detail
    assert "@PublicPackageText(receipt.ActorLabel)" in packages
    assert 'ViewData["Title"] = PublicPackageText(Model.Heading);' in package_receipt
    assert "PublicFacingCopyHumanizer.Clean(value)" in package_receipt
    assert "@PublicPackageText(Model.PrimaryAction.Label)" in package_receipt
    assert "@PublicPackageText(Model.SecondaryAction.Label)" in package_receipt
    assert "@PublicPackageText(Model.Receipt.ActorLabel)" in package_receipt
    assert "@PublicPackageText(Model.Package.Title)" in package_receipt
    assert "@PublicPackageText(Model.PrimaryAction.Label)" in package_detail
    assert "@PublicPackageText(Model.SecondaryAction.Label)" in package_detail
    assert "@PublicPackageText(Model.VoteActionLabel)" in package_detail
    assert "@PublicPackageText(Model.FollowActionLabel)" in package_detail
    assert "@PublicPackageText(receipt.ActorLabel)" in package_detail
    assert "@receipt.ActorLabel" not in packages
    assert "@receipt.ActorLabel" not in package_detail
    assert "@Model.PrimaryAction.Label" not in package_detail
    assert "@Model.SecondaryAction.Label" not in package_detail
    assert "@Model.VoteActionLabel" not in package_detail
    assert "@Model.FollowActionLabel" not in package_detail
    assert "@Model.PrimaryAction.Label" not in package_receipt
    assert "@Model.SecondaryAction.Label" not in package_receipt
    assert "@Model.Receipt.ActorLabel" not in package_receipt
    assert "@Model.Package.Title" not in package_receipt
    assert "Details:</strong> @PublicFacingCopyHumanizer.Clean(publication.ProvenanceSummary)" in shelf
    assert "<span class=\"tag\">Details</span>" in publication
    assert "related detail" in publication


def test_public_pages_use_plain_chummer_labels_instead_of_first_party_jargon() -> None:
    shelf = read("Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml")
    changelog = read("Chummer.Run.Api/Views/PublicLanding/Changelog.cshtml")
    support_submitted = read("Chummer.Run.Api/Views/PublicLanding/SupportSubmitted.cshtml")
    publication = read("Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml")
    nexus_pan = read("Chummer.Run.Api/Views/PublicLanding/NexusPanContinuity.cshtml")
    ledger_notifications = read("Chummer.Run.Api/Views/PublicLanding/LedgerNotifications.cshtml")
    ledger = read("Chummer.Run.Api/Views/PublicLanding/Ledger.cshtml")
    ledger_onboarding = read("Chummer.Run.Api/Views/PublicLanding/LedgerOnboarding.cshtml")
    combined = "\n".join((
        shelf,
        changelog,
        support_submitted,
        publication,
        nexus_pan,
        ledger_notifications,
        ledger,
        ledger_onboarding,
    ))

    for forbidden in (
        "first-party help",
        "First-party help",
        "first-party page",
        "first-party route",
        "first-party storage",
        "first-party email",
        "first-party motion",
        "product claims",
    ):
        assert forbidden not in combined

    assert "Chummer help" in shelf
    assert "Chummer help" in changelog
    assert "Chummer help" in support_submitted
    assert "Use Chummer help" in publication
    assert "tracked by Chummer" in nexus_pan
    assert "one Chummer path" in ledger_notifications
    assert "Delivery: Chummer email" in ledger
    assert "Chummer motion intros" in ledger
    assert "Video: Chummer motion" in ledger
    assert "Video: Chummer motion" in ledger_onboarding
    assert "product improvements" in changelog
    assert "@PublicChangelogText(card.Card.Badge)" in changelog
    assert "<span class=\"tag\">@card.Card.Badge</span>" not in changelog


def test_public_pages_use_plain_promises_and_summaries_instead_of_claim_jargon() -> None:
    anarchy = read("Chummer.Run.Api/Views/PublicLanding/Anarchy.cshtml")
    participate = read("Chummer.Run.Api/Views/PublicLanding/Participate.cshtml")
    feedback_lookup = read("Chummer.Run.Api/Views/PublicLanding/FeedbackOperationsLookup.cshtml")
    combined = "\n".join((anarchy, participate, feedback_lookup))

    for forbidden in (
        "Public claim ceiling",
        "public claim",
        "planned or shipped public claim",
    ):
        assert forbidden not in combined

    assert "What this path covers" in anarchy
    assert "planned or shipped public update" in participate
    assert "no public summary beyond the saved state" in feedback_lookup


def test_public_release_copy_uses_install_notes_instead_of_issue_checking_language() -> None:
    shelf = read("Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml")
    now = read("Chummer.Run.Api/Views/PublicLanding/Now.cshtml")
    faq = read("Chummer.Run.Api/Views/PublicLanding/Faq.cshtml")
    feature_live = read("Chummer.Run.Api/Views/PublicLanding/_FeatureDetailLiveProof.cshtml")
    combined = "\n".join((shelf, now, faq, feature_live))

    for forbidden in (
        "check known issues",
        "Downloads shows the current package, known issues, and setup help",
        "Read download help and known issues",
        "Known issues and install help",
        "easier to trust",
    ):
        assert forbidden not in combined

    assert "see install notes" in shelf
    assert "current package, setup help" in now
    assert "Install notes and help" in now
    assert "current package and setup help" in faq
    assert "easier to use" in feature_live


def test_now_page_cleans_dynamic_public_copy_before_rendering() -> None:
    now = read("Chummer.Run.Api/Views/PublicLanding/Now.cshtml")

    for expected in (
        "static string PublicNowText(string? value) => PublicFacingCopyHumanizer.Clean(value);",
        "@PublicNowText(Model.ReleaseExperience.ReleaseNotesSummary)",
        "@PublicNowText(Model.ReleaseExperience.KnownIssuesLabel)",
        "@PublicNowText(Model.ReleaseExperience.UpdatePostureSummary)",
        "@PublicSurfaceStatus.DisplayLabel(card.Card.Badge)",
        "<h3>@PublicNowText(card.Card.Title)</h3>",
        "<p>@PublicNowText(card.Card.Summary)</p>",
        "@PublicNowText(card.Card.ProofNote)",
        "@PublicNowText(card.Action.Label)",
        "@PublicNowText(overlay.Title)",
    ):
        assert expected in now

    for forbidden in (
        "<p>@Model.ReleaseExperience.ReleaseNotesSummary</p>",
        ">@Model.ReleaseExperience.KnownIssuesLabel</a>",
        "@PublicFacingCopyHumanizer.Clean(Model.ReleaseExperience.UpdatePostureSummary)",
        "<span class=\"tag\">@card.Card.Badge</span>",
        "<h3>@card.Card.Title</h3>",
        "<p>@card.Card.Summary</p>",
        ">@card.Action.Label</a>",
        "<span>@overlay.Title</span>",
    ):
        assert forbidden not in now


def test_shared_public_panels_clean_dynamic_copy_before_rendering() -> None:
    privacy = read("Chummer.Run.Api/Views/Shared/_PrivacyBoundaryPanel.cshtml")
    signed_in = read("Chummer.Run.Api/Views/Shared/_SignedInTrustStatusPanel.cshtml")
    pulse_panel = read("Chummer.Run.Api/Views/Shared/_PublicTrustPulsePanel.cshtml")
    pulse_body = read("Chummer.Run.Api/Views/Shared/_PublicTrustPulseBody.cshtml")
    combined = "\n".join((privacy, signed_in, pulse_panel, pulse_body))

    for expected in (
        "static string PublicPrivacyText(string? value) => PublicFacingCopyHumanizer.Clean(value);",
        "static string PublicSignedInTrustText(string? value) => PublicFacingCopyHumanizer.Clean(value);",
        "static string PublicTrustPulseText(string? value) => PublicFacingCopyHumanizer.Clean(value);",
        "@PublicPrivacyText(Model.Heading)",
        "@PublicPrivacyText(Model.Summary)",
        "@PublicPrivacyText(Model.PrimaryAction.Label)",
        "@PublicPrivacyText(domain.RetentionSummary)",
        "@PublicPrivacyText(rule.BlockedSummary)",
        "@PublicSignedInTrustText(Model.Heading)",
        "@PublicSignedInTrustText(Model.PrimaryAction.Label)",
        "@PublicSignedInTrustText(row.Label)",
        "@PublicTrustPulseText(Model.Heading)",
        "@PublicTrustPulseText(Model.PrimaryAction.Label)",
        "@PublicTrustPulseText(Model.Summary)",
        "@PublicTrustPulseText(row.Label)",
    ):
        assert expected in combined

    for forbidden in (
        "<h2>@Model.Heading</h2>",
        "<p>@Model.Summary</p>",
        ">@Model.PrimaryAction.Label</a>",
        ">@Model.SecondaryAction.Label</a>",
        "<span>@item</span>",
        "<span>@row.Label</span>",
        "<span class=\"tag\">@domain.Owner</span>",
        "<h3>@domain.Label</h3>",
        "@domain.RetentionSummary",
        "@domain.RedactionSummary",
        "@rule.BlockedSummary",
    ):
        assert forbidden not in combined


def test_public_detail_page_uses_limited_detail_instead_of_review_process_copy() -> None:
    shelf = read("Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml")

    for forbidden in (
        "Limited public wording",
        "limited public wording",
        "public comparison language",
        "one more review pass",
        "Public parity claims remain",
        "review-required",
    ):
        assert forbidden not in shelf

    assert "Shared publications with limited detail" in shelf
    assert "shorter public summary" in shelf
    assert "Broader comparisons return when they are useful and current." in shelf


def test_public_detail_page_uses_account_language_instead_of_signed_in_labels() -> None:
    shelf = read("Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml")

    for expected in (
        "Account return view",
        "Account return",
        "one account view",
        "The account view keeps aftermath",
        "account history card(s)",
        "account history, or help",
        "Account history",
    ):
        assert expected in shelf

    for forbidden in (
        "Signed-in account return view",
        "Signed-in account return",
        "one signed-in view",
        "The signed-in view keeps aftermath",
        "signed-in history card(s)",
        "signed-in history, or help",
        "Signed-in history",
        "this signed-in view",
    ):
        assert forbidden not in shelf


def test_public_publication_page_uses_account_return_language() -> None:
    publication = read("Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml")

    for expected in (
        "Open account return view",
        "Create account for account return",
        "Use the account return view",
        "Account return keeps public and private returns together",
        "Choose gallery, downloads, account return, or help on purpose.",
    ):
        assert expected in publication

    for forbidden in (
        "Open signed-in account return view",
        "Create account for signed-in account return",
        "Use the signed-in detail view",
        "Signed-in account return keeps public and private returns together",
        "signed-in account-return view",
        "Choose gallery, downloads, signed-in account return, or help on purpose.",
    ):
        assert forbidden not in publication


def test_feature_detail_partials_use_account_detail_language() -> None:
    live = read("Chummer.Run.Api/Views/PublicLanding/_FeatureDetailLiveProof.cshtml")
    preview = read("Chummer.Run.Api/Views/PublicLanding/_FeatureDetailPreviewConcept.cshtml")
    roadmap = read("Chummer.Run.Api/Views/PublicLanding/_FeatureDetailRoadmap.cshtml")
    combined = "\n".join((live, preview, roadmap))

    for expected in (
        "Use your account detail view",
        "Open the account detail view",
        "Open account detail",
        "Compare against your account detail view",
        "Open account detail view",
    ):
        assert expected in combined

    for forbidden in (
        "Use your signed-in detail view",
        "Open the signed-in detail view",
        "Open signed-in detail",
        "Compare against your signed-in detail view",
        "Open signed-in detail view",
        "signed-in detail view",
    ):
        assert forbidden not in combined


def test_public_detail_route_choices_clean_dynamic_copy_before_rendering() -> None:
    shelf = read("Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml")
    feature = read("Chummer.Run.Api/Views/PublicLanding/FeatureDetail.cshtml")
    publication = read("Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml")

    for expected in (
        'ViewData["Title"] = PublicFacingCopyHumanizer.Clean(Model.Heading);',
        "@PublicText(Model.Eyebrow)",
        "@PublicText(Model.Heading)",
        "@PublicText(choice.Badge)",
        "@PublicText(choice.Title)",
        "@PublicText(choice.Summary)",
        "@PublicText(item)",
        "@PublicText(choice.Label)",
    ):
        assert expected in shelf
        assert expected in feature

    for expected in (
        "@PublicPublicationText(choice.Badge)",
        "@PublicPublicationText(choice.Title)",
        "@PublicPublicationText(choice.Summary)",
        "@PublicPublicationText(item)",
        "@PublicPublicationText(choice.Label)",
    ):
        assert expected in publication

    for source in (shelf, feature, publication):
        for forbidden in (
            'ViewData["Title"] = Model.Heading;',
            "<p class=\"eyebrow\">@Model.Eyebrow</p>",
            "<h1 class=\"page-title\">@Model.Heading</h1>",
            "<span class=\"tag\">@choice.Badge</span>",
            "<h3>@choice.Title</h3>",
            "<p>@choice.Summary</p>",
            "<span>@item</span>",
            ">@choice.Label</a>",
        ):
            assert forbidden not in source


def test_publication_detail_page_uses_plain_labels() -> None:
    publication = read("Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml")

    for forbidden in (
        "Limited public state",
        "Route:",
        "Known issues nearby",
        "No fake build path",
        "No auth wall for discovery",
        "Current desktop coverage still keeps this public wording limited.",
        "Trust</span>",
        "Lineage</span>",
        "supporting detail",
    ):
        assert forbidden not in publication

    assert "Limited detail" in publication
    assert "Page: @routeStateLabel" in publication
    assert "ViewData[\"Title\"] = PublicPublicationText(Model.Publication.Title)" in publication
    assert "@PublicPublicationText(Model.Publication.Title)" in publication
    assert "@PublicPublicationText(Model.Publication.Summary)" in publication
    assert "@PublicPublicationText(Model.TrustPulse.RouteGuardSummary)" in publication
    assert "ViewData[\"Title\"] = Model.Publication.Title" not in publication
    assert "@Model.Publication.Title" not in publication
    assert "@Model.Publication.Summary" not in publication
    assert "@Model.TrustPulse.RouteGuardSummary" not in publication
    assert "Install notes nearby" in publication
    assert "Clear install path" in publication
    assert "Public discovery stays open" in publication
    assert "Some desktop work is still open, so this public summary stays short." in publication
    assert "Status</span>" in publication
    assert "History</span>" in publication
    assert "related detail" in publication


def test_faction_workspace_uses_page_language_instead_of_route_language() -> None:
    workspace = read("Chummer.Run.Api/Views/PublicLanding/LedgerFactionWorkspace.cshtml")

    for forbidden in (
        "Authenticated route",
        "Public route stays separate",
        "Current signed-in workspace.",
        "public Ledger routes",
        "authenticated campaign routes",
        "Public Ledger routes",
        "signed-in faction routes",
        "Signed-in page",
        "signed-in campaign pages",
        "signed-in faction pages",
        "signed-in API",
        "faction overlay route",
        "internal campaign city view",
        "Overlay API",
        "Private lore path exists",
    ):
        assert forbidden not in workspace

    assert "The campaign city view starts with the globe" in workspace
    assert "Account page" in workspace
    assert "Public page stays separate" in workspace
    assert "Current workspace." in workspace
    assert "public Ledger pages" in workspace
    assert "account campaign pages" in workspace
    assert "Public Ledger pages" in workspace
    assert "account faction pages" in workspace
    assert "account workspace" in workspace
    assert "private lore overlay" in workspace
    assert "Private layer" in workspace
    assert "Private lore stays private" in workspace


def test_account_ledger_pages_use_page_and_path_language() -> None:
    account_home = read("Chummer.Run.Api/Views/PublicLanding/LedgerAccountHome.cshtml")
    notifications = read("Chummer.Run.Api/Views/PublicLanding/LedgerNotifications.cshtml")
    ledger = read("Chummer.Run.Api/Views/PublicLanding/Ledger.cshtml")
    advisory = read("Chummer.Run.Api/Views/PublicLanding/LedgerAdvisory.cshtml")
    onboarding = read("Chummer.Run.Api/Views/PublicLanding/LedgerOnboarding.cshtml")
    combined = "\n".join((account_home, notifications, ledger, advisory, onboarding))

    for forbidden in (
        "signed-in route",
        "Open mail-backed route",
        "route-backed world state",
        "one Chummer route",
        "inbox route",
        "public globe route",
        "Open watch route",
        "Major and challenger routes",
        "Current world-turn packet",
        "signed-in page",
        "Signed-in notifications",
        "signed-in inbox",
        "signed-in path",
        "signed-in campaign city view",
    ):
        assert forbidden not in combined

    assert "account page" in account_home
    assert "Open mail-backed page" in account_home
    assert "Account notifications" in notifications
    assert "account inbox" in notifications
    assert "account path" in notifications
    assert "current world state" in notifications
    assert "one Chummer path" in notifications
    assert "Use the inbox as the Table Pulse Live entry point" in notifications
    assert "public globe page" in ledger
    assert "Open watch page" in ledger
    assert "Current turn details" in account_home
    assert "account campaign city view" in account_home
    assert "account page that mail and inbox items return to" in advisory
    assert "Major and challenger paths" in onboarding


def test_faction_builder_and_promo_use_page_language_instead_of_route_language() -> None:
    faction_create = read("Chummer.Run.Api/Views/PublicLanding/LedgerFactionCreate.cshtml")
    faction_promo = read("Chummer.Run.Api/Views/PublicLanding/LedgerFactionPromo.cshtml")
    combined = "\n".join((faction_create, faction_promo))

    for forbidden in (
        "riskier route",
        "route-backed",
        "Every faction video route",
    ):
        assert forbidden not in combined

    assert "riskier start" in faction_create
    assert "Every faction video page includes video files" in faction_promo


def test_package_pages_use_page_language_instead_of_route_language() -> None:
    package_detail = read("Chummer.Run.Api/Views/PublicLanding/PackageDetail.cshtml")
    package_receipt = read("Chummer.Run.Api/Views/PublicLanding/PackageReceipt.cshtml")
    combined = "\n".join((package_detail, package_receipt))

    for forbidden in (
        "Next route",
        "Return to the package route",
        "package route.",
        "signed-in package page",
    ):
        assert forbidden not in combined

    assert "Next step" in package_receipt
    assert "Return to the package page" in package_receipt
    assert "account package page" in package_receipt
    assert "Package history stays attached to this package page." in package_detail


def test_mobile_helper_and_anarchy_pages_use_page_and_export_language() -> None:
    mobile = read("Chummer.Run.Api/Views/PublicLanding/MobileProjection.cshtml")
    knowledge = read("Chummer.Run.Api/Views/PublicLanding/KnowledgeFabric.cshtml")
    nexus = read("Chummer.Run.Api/Views/PublicLanding/NexusPanContinuity.cshtml")
    anarchy = read("Chummer.Run.Api/Views/PublicLanding/Anarchy.cshtml")
    concierge = read("Chummer.Run.Api/Views/PublicLanding/Concierge.cshtml")
    join = read("Chummer.Run.Api/Views/PublicLanding/JoinPrimer.cshtml")
    combined = "\n".join((mobile, knowledge, nexus, anarchy, concierge, join))

    for forbidden in (
        "app route",
        "continuity route",
        "routes converge",
        "This route keeps rule answers",
        "Chummer packet, not book text",
        "This route reads Chummer dispatches",
        "public-safe dispatches",
        "portable packet",
        "Portable runner packet",
        "provenance attached",
        "Chummer-owned JSON",
        "publication authority",
        "<span class=\"tag\">JSON export</span>",
    ):
        assert forbidden not in combined

    assert "app page, manifest, and service worker" in mobile
    assert "continuity page" in mobile
    assert "entry points meet in one shell" in mobile
    assert "This page keeps rule answers short" in knowledge
    assert "Chummer export, not book text" in anarchy
    assert "This page reads Chummer dispatches" in anarchy
    assert "The same Chummer dispatches can power Anarchy play." in anarchy
    assert "Chummer keeps the portable export readable" in anarchy
    assert "The export stays with Chummer" in anarchy
    assert "Portable runner export" in anarchy
    assert "File export" in anarchy

    for expected in (
        "PublicKnowledgeText(Model.Heading)",
        "PublicKnowledgeText(Model.PrimaryAction.Label)",
        "PublicNexusText(Model.Heading)",
        "PublicNexusText(Model.PlatformSummary)",
        "PublicMobileText(Model.Heading)",
        "PublicMobileText(Model.InstallabilitySummary)",
        "PublicMobileText(role.Label)",
        "PublicAnarchyText(Model.Heading)",
        "PublicAnarchyText(Model.ScopeLabel)",
        "PublicAnarchyText(Model.FeaturedProfile.Notes)",
        "PublicAnarchyText(dispatch.Summary)",
        "PublicConciergeText(Model.Heading)",
        "PublicConciergeText(branch.ActionLabel)",
        "PublicJoinText(Model.Heading)",
        "PublicJoinText(panel.PrimaryAction.Label)",
    ):
        assert expected in combined

    for forbidden_binding in (
        "<p class=\"eyebrow\">@Model.Eyebrow</p>",
        "<h1 class=\"page-title\">@Model.Heading</h1>",
        "<p class=\"page-copy\">@Model.Intro</p>",
        ">@Model.PrimaryAction.Label</a>",
        ">@Model.SecondaryAction.Label</a>",
        ">@Model.TertiaryAction.Label</a>",
        "<span>@Model.CurrentRoleLabel</span>",
        "<p class=\"editorial-copy\">@Model.InstallabilitySummary</p>",
        "<p class=\"editorial-copy\">@Model.PlatformSummary</p>",
        "<span>@Model.ScopeLabel</span>",
        "<p>@Model.FeaturedProfile.Notes</p>",
        "<span class=\"tag\">@Model.ExplainReceipt.Status</span>",
        "<a class=\"button-like button-like--@action.Tone\" href=\"@action.Href\">@action.Label</a>",
        "<span class=\"tag\">@branch.DestinationLabel</span>",
        "<a class=\"editorial-strip__action\" href=\"@branch.ActionHref\">@branch.ActionLabel</a>",
        "<a class=\"@ToneClass(action.Tone)\" href=\"@action.Href\">@action.Label</a>",
        "<a class=\"@ToneClass(panel.PrimaryAction.Tone)\" href=\"@panel.PrimaryAction.Href\">@panel.PrimaryAction.Label</a>",
    ):
        assert forbidden_binding not in combined


def test_public_feature_action_labels_do_not_expose_packet_receipt_or_json_jargon() -> None:
    controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")

    for forbidden in (
        '"Open briefing details"',
        '"Open prep details"',
        '"Open control details"',
        '"Open session board packet"',
        '"Open starter details"',
        '"Open starter packet"',
        '"Open ruleset details"',
        '"Open SR5 head packet"',
        '"Open acceleration details"',
        '"Open capability packet"',
        '"Open primer JSON"',
        '"Open network details"',
        '"Open publication details"',
        '"Open command details"',
        '"Open command deck packet"',
        '"Open identity details"',
        '"Open runner return details"',
        '"Open command pressure details"',
        '"Open JSON details"',
        '"Open watch package details"',
        '"Open replay JSON"',
        '"Open mobile PWA JSON"',
        '"Download player packet"',
        "Inspect the public-safe session-board contract",
        "Inspect the reconnect and recovery contract",
        "Inspect the public-safe starter contract",
        "Inspect the restore and continuity contract",
        "Inspect the hosted-first capability contract",
        "Inspect the privacy and fail-open boundary",
        "Inspect the bounded quick-jump contract",
        "Inspect the named account route",
        "generic operations console",
        "generic launcher",
        "generic ops dashboard",
        "generic tutorial chrome",
        "Signed-in desk",
        "signed-in desk",
        "Signed-in control desk",
        "Signed-in starter desk",
        "Signed-in edition desk",
        "Signed-in profile desk",
        "Signed-in publication desk",
        "Signed-in JACKPOINT desk",
        "first-party account truth",
        "truth path",
        "hidden product prerequisites",
        "No local truth owner",
        "Fail-open fallback",
        "stale cached views",
        "generic chat suite",
        "Spatial-prep packet only",
        "Ruleset-head surface only",
        "Open first runsite pack",
        "bounded jump contract",
        "typed command APIs",
        "typed control APIs",
        "typed edition-head APIs",
        "starter/recovery APIs",
        "typed capability/policy APIs",
        "truth authority",
        "off-account recovery truth",
        "canonical truth",
        "rules truth",
        "visual flavor as rules truth",
        "off-spine truth",
        "rules authority",
        "core rules authority",
        "background hints into authority",
        "campaign truth",
        "publication truth",
        "spoiler truth",
        "Public command packet",
        "Public ruleset-head packet",
        "Public session packet",
        "Public starter packet",
        "Public capability packet",
        "Public-safe briefing packet",
        "Lead publication contract",
        "Open named desk route",
        "Typed command API",
        "Typed control API",
        "Typed starter API",
        "Typed capability API",
        "publication contract",
        "guided-mastery contract",
        "local-acceleration contract",
    ):
        assert forbidden not in controller

    for expected in (
        '"Open briefing list"',
        '"Open prep overview"',
        '"Open control overview"',
        '"Open session board"',
        '"Open starter overview"',
        '"Open starter guide"',
        '"Open edition overview"',
        '"Open SR5 guide"',
        '"Open acceleration overview"',
        '"Open capability matrix"',
        '"Open primer data"',
        '"Open run list"',
        '"Open publication list"',
        '"Open command overview"',
        '"Open command deck"',
        '"Open identity overview"',
        '"Open runner return"',
        '"Open command pressure"',
        '"Open pressure data"',
        '"Open watch brief"',
        '"Open watch data"',
        '"Open replay data"',
        '"Open mobile app data"',
        '"Download player notes"',
        '"Open first runsite"',
        "Read the public session board before using Run Control at the table.",
        "Read the reconnect and recovery notes that keep live GM work attached to the same campaign.",
        "Read the starter guide before using ONRAMP for the first session.",
        "Read the restore and continuity notes that keep guided setup tied to the account.",
        "Read the hosted-first capability matrix before enabling local compute.",
        "Read the privacy and fallback notes that keep local acceleration optional.",
        "Read the quick-jump guide before using Quicksilver as your command deck.",
        "Read the named targets and focus paths that keep expert speed inside Chummer.",
        "Account workspace",
        "Account control workspace",
        "Account starter workspace",
        "Account edition workspace",
        "Account profile workspace",
        "Account publication workspace",
        "Account JACKPOINT workspace",
        "Account optional profile",
        "Account edition focus",
        "No local rules owner",
        "Fallback available",
        "Privacy notes",
        "Spatial-prep guide only. This page does not promise tactical overlays, live map control, or full VTT integration.",
        "Spatial-prep guide only. This route does not claim a full overlay, VTT, or tactical control stack.",
        "Edition-focused surface only. EDITION STUDIO does not create three disconnected apps, replace core rules with styling, or treat visual flavor as rules.",
        "The public command guide shows where quick jumps are allowed without pretending expert speed is a secret local-only mode.",
        "Read the account route and focus boundaries before using Quicksilver as a command deck.",
        "Read the account routes and control notes before using RUN CONTROL as the table hub.",
        "Read the account routes and recovery notes before treating ONRAMP like a simple tutorial overlay.",
        "The public guide shows the session board and continuity limits without pretending GM control is only a private surface.",
        "The public guide shows starter and recovery limits without pretending the product is an auto-build wizard.",
        "The public guides show the SR4, SR5, and SR6 posture without pretending styling itself is rules.",
        "The public guide shows which workloads may accelerate locally while keeping hosted mode available.",
        "Use the command deck when you want the current jump targets before opening a build, rule, workspace, or publication surface.",
    ):
        assert expected in controller


def test_table_pulse_public_copy_uses_plain_live_and_aftermath_language() -> None:
    controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")

    for forbidden in (
        "Live pressure stays on the signed-in command path.",
        "GM-private aftermath packages stay separate",
        "The live view is the in-world packet and reaction system.",
        "GM-controlled heat packets on the signed-in ledger notifications route.",
        "Bounded remote reaction submissions with explicit GM adjudication.",
        "Aftermath is a separate GM-private recap and carry-forward packet system.",
        "Workspace aftermath recap packages stay attached.",
        "moderation truth",
        "Live heat packets are real now",
        "GM-private aftermath packages are real now",
        "GM-controlled heat packets, bounded reactions, and adjudicated fallout stay on the signed-in command path.",
        "GM-private aftermath recap, downtime carry-forward, and campaign-memory next steps remain separate from the live path.",
        "no_automatic_world_authority",
        "no_public_surveillance_truth",
        "Signed-in account lane",
        "Signed-in Runner Passport keeps public-safe trust posture",
        "Signal Deck is armed, but no reviewed consequence cue has been written yet for this signed-in path.",
        "the signed-in command loop can still carry inbox reactions",
        "signed-in command paths",
        "The signed-in inbox is already carrying",
        "The signed-in inbox is armed",
        "Open the signed-in inbox",
        "Signed-in Black Ledger newsreel delivery status and history.",
        "Signed-in Black Ledger faction home",
        "Reviewed signed-in path",
        "signed-in workspace path",
        "Table Pulse Live turns the signed-in inbox into a command packet",
    ):
        assert forbidden not in controller

    for expected in (
        "Live pressure stays in the account inbox.",
        "Private aftermath stays separate",
        "The live view is the in-world signal and reaction system.",
        "GM-controlled heat updates in the account inbox.",
        "Remote reactions wait for explicit GM adjudication.",
        "Aftermath is a separate private recap and carry-forward system for the GM.",
        "Workspace aftermath recaps stay attached.",
        "not public scoring or moderation.",
        "Live heat updates are real now",
        "Private aftermath recaps are real now",
        "GM-controlled heat updates, remote reactions, and adjudicated fallout stay in the account inbox.",
        "Private aftermath recap, downtime carry-forward, and campaign-memory next steps remain separate from the live path.",
        "no_automatic_world_changes",
        "no_public_surveillance",
        "Account lane",
        "Runner Passport keeps public-safe trust posture connected to the first-party Table Pulse live inbox",
        "Signal Deck is armed, but no reviewed consequence cue has been written yet for this account path.",
        "the account command loop can still carry inbox reactions",
        "account command paths",
        "The account inbox is already carrying",
        "The account inbox is armed",
        "Open the account inbox",
        "Account Black Ledger newsreel delivery status and history.",
        "Account Black Ledger faction home",
        "Reviewed account path",
        "account workspace path",
        "Table Pulse Live turns the account inbox into a command packet",
    ):
        assert expected in controller


def test_foundry_export_copy_uses_limited_handoff_language() -> None:
    controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")

    for forbidden in (
        "Foundry-facing export remains a bounded interoperability surface, not a separate flagship claim.",
        "Boundary surface",
        "This route exists to make the interoperability boundary explicit.",
        "separate parked feature still owns the public product story",
        "Interop boundary",
        "No separate public Foundry feature claim",
        "Export truth stays first-party",
        "Foundry-facing export is an interoperability boundary.",
        "Packet truth, moderation status, and active campaign authority stay first-party",
        "No third-party truth owner",
        "Boundary stays explicit",
    ):
        assert forbidden not in controller

    for expected in (
        "Foundry export remains a limited handoff path, not a separate flagship feature.",
        "Export support",
        "This route explains what Chummer can hand off toward Foundry-style targets without making export support look like a separate product.",
        "Export path",
        "No separate public Foundry feature",
        "Chummer keeps the campaign state",
        "Foundry-style export is a handoff.",
        "Chummer keeps campaign state, moderation status, and active table work in Chummer even when a VTT target exists.",
        "Export only",
        "Chummer keeps the record",
        "No outside owner",
        "Export stays clear",
    ):
        assert expected in controller


def test_community_hub_copy_uses_plain_board_and_venue_language() -> None:
    controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")
    venue = read("Chummer.Run.Api/Views/PublicLanding/GmSessionVenue.cshtml")
    combined = "\n".join((controller, venue))

    for forbidden in (
        "Public-safe venue status for an open run without leaking private room details.",
        "Public-safe venue",
        "Public-safe session title or run label.",
        "ready for signed-in participants",
        "Public-safe venue status only",
        "Signed-in Community Hub keeps open-run listing, join review, scheduling, meeting handoff, and closeout on first-party campaign-spine rails.",
        "RuleTruth = \"Chummer-owned\"",
        "WorldTruth = \"Chummer-owned\"",
        "public board status and safety boundaries stay readable, while signed-in listing",
        "Private roster notes, meeting access, and case handling stay signed-in and Chummer-owned.",
        "Signed-in board",
        "Public board packet",
        "Inspect the named signed-in and API paths before treating Community Hub as just another forum or meeting-tool shell.",
        "the signed-in Community Hub path",
        "Chummer owns run, roster, scheduling, and closeout truth.",
        "Lead open run contract",
        "Use the typed API index when you want the open-run contract before a public packet becomes a real table.",
        "Venue and handoff boundary",
        "meeting-service automation still remains projection-only",
        "Chummer still owns accepted roster and run truth.",
        "run truth, roster truth, or consequence truth",
    ):
        assert forbidden not in combined

    for expected in (
        "Public venue status for an open run without leaking private room details.",
        "Public venue",
        "Public session title or run label.",
        "ready for account participants",
        "Public venue status only",
        "Account Community Hub keeps open-run listing, join review, scheduling, meeting handoff, and closeout on Chummer campaign pages.",
        "RulesOwner = \"Chummer\"",
        "WorldOwner = \"Chummer\"",
        "public board status and safety limits stay readable, while account listing",
        "Private roster notes, meeting access, and case handling stay in Chummer account pages.",
        "Account board",
        "Public board",
        "Read the account and public paths before treating Community Hub as just another forum or meeting-tool shell.",
        "account Community Hub path",
        "Chummer keeps run, roster, scheduling, and closeout records.",
        "Lead open run",
        "Use the open-run list when you want current table status before a public listing becomes a real table.",
        "Venue and meeting link",
        "meeting-service automation stays optional",
        "Chummer still keeps accepted roster and run status.",
        "does not hand run, roster, or closeout records to chat tools, meeting tools, or public boards.",
        "Room available to account participants",
    ):
        assert expected in combined


def test_account_context_services_use_account_language_instead_of_signed_in_rails() -> None:
    sources = "\n".join(
        (
            read("Chummer.Run.Api/Controllers/AccountsController.cs"),
            read("Chummer.Run.Api/Controllers/AuthController.cs"),
            read("Chummer.Run.Api/Controllers/PublicLandingController.cs"),
            read("Chummer.Run.Api/Services/Community/CampaignSpineService.cs"),
            read("Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs"),
            read("Chummer.Run.Api/Services/Community/ReusableAccountFlowService.cs"),
            read("Chummer.Run.Api/Services/NexusPanContinuityService.cs"),
            read("Chummer.Run.Api/Services/PublicPackageCatalogService.cs"),
            read("Chummer.Run.Api/Services/Support/HostedBoundedContextCoverageService.cs"),
            read("Chummer.Run.Api/Services/Support/PrivacyBoundedSupportStatusService.cs"),
        )
    )

    for forbidden in (
        "reusable account-profile truth on the signed-in account rail",
        "Review the signed-in account profile",
        "Return to the signed-in account",
        "This signed-in account",
        "entitlement(s) stay reusable on the signed-in account rail",
        "signed-in account page",
        "Inspect the signed-in account page",
        "same signed-in page",
        "signed-in community operations anchor",
        "signed-in community page",
        "signed-in account settings",
        "signed-in account surface",
        "signed-in account path",
        "signed-in routes carry",
        "signed-in rails",
        "signed-in support and account pages",
        "signed-in publication review",
        "signed-in draft review",
        "signed-in area",
    ):
        assert forbidden not in sources

    for expected in (
        "reusable account-profile truth on the account page",
        "Review the account profile and linked paths",
        "Return to the account page",
        "This account currently owns the group.",
        "entitlement(s) stay reusable on the account page",
        "keeps profile, access, rewards, and entitlements on the account page",
        "Inspect the account page",
        "same account page",
        "account community operations anchor",
        "account community page",
        "account settings",
        "account page right now",
        "account path instead of forking a shadow copy",
        "account routes carry the user-safe slice",
        "account paths",
        "account support and account pages",
        "account publication review",
        "account draft review",
        "account area",
    ):
        assert expected in sources
