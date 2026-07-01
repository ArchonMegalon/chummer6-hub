from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_main_public_routes_use_minimal_surface_contract() -> None:
    landing = read("Chummer.Run.Api/Views/PublicLanding/Landing.cshtml")
    downloads = read("Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml")
    dispatch = read("Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml")
    status = read("Chummer.Run.Api/Views/PublicLanding/Status.cshtml")
    horizons = read("Chummer.Run.Api/Views/PublicLanding/Horizons.cshtml")
    product_story = read("Chummer.Run.Api/Views/PublicLanding/ProductStory.cshtml")
    faq = read("Chummer.Run.Api/Views/PublicLanding/Faq.cshtml")
    shelf = read("Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml")
    trust_page = read("Chummer.Run.Api/Views/PublicLanding/TrustPage.cshtml")

    for source in (landing, downloads, dispatch, status, horizons, product_story, faq, shelf):
        assert 'surface-minimal' in source

    assert 'surface-help surface-minimal' in trust_page
    assert 'minimal-help-grid' in trust_page
    assert 'minimal-help-card' in trust_page
    assert '@PublicText(Model.Intro)' in trust_page
    assert 'Pick the next step.' in trust_page
    assert 'Start with the closest match.' not in trust_page
    assert 'if (helpPage || contactPage)' in trust_page
    assert 'return "/downloads";' in trust_page
    assert 'route-choice-grid--compact' in trust_page
    assert '<h2>Discord</h2>' in trust_page
    assert 'Normal questions and feedback belong in the Chummer5 server.' in trust_page
    assert 'Public ideas go to Participate. Private problems stay here.' not in trust_page
    assert 'Send support request' not in trust_page
    assert 'other routes below' not in trust_page
    assert 'minimal-help-card__list' not in trust_page
    assert 'aria-label="Quick notes"' not in trust_page
    assert 'route-choice-card__details' not in trust_page


def test_help_and_contact_pages_clean_dynamic_copy_before_rendering() -> None:
    trust_page = read("Chummer.Run.Api/Views/PublicLanding/TrustPage.cshtml")
    controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")
    install_setup = read("Chummer.Run.Api/Services/DesktopInstallRail.cs")
    public_trust_content = read(".codex-design/product/PUBLIC_TRUST_CONTENT.yaml")

    for expected in (
        'ViewData["Title"] = UndetectableHumanizerCopyAdapter.Humanize(Model.Heading);',
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
        ">@Model.SupportIntake.AccountSupportLabel</a>",
        ">@Model.SupportIntake.InstallAccessLabel</a>",
        "<p class=\"muted-copy\">@Model.SupportIntake.ResponseExpectation</p>",
        ">@Model.SupportIntake.InstallRailLabel</a>",
        "installer or app does the real work",
        "Return to the guided installer after support",
        "Open the right support case",
        "Pick the path",
        "Use Participate for ideas and safe public bugs",
        "Keep one issue per case",
        "Submit support case",
        "Case type",
        "One-line summary",
        "Need to go back to setup?",
        "Pick the problem",
        "Open support intake",
        "Support cases stay separate from public feedback.",
        "Create an account only when you want tracked support or recovery.",
    ):
        assert forbidden not in trust_page
        assert forbidden not in public_trust_content

    combined = "\n".join((trust_page, controller, install_setup, public_trust_content))
    for forbidden in (
        "Fixer Board",
        "Return to installer",
        "Go back to the installer",
        "only use a recovery code if Chummer entered recovery mode",
        "use this claim code only if Chummer says the device entered recovery mode",
    ):
        assert forbidden not in combined

    for expected in (
        "use this claim code only if Chummer asks for it on that device",
        "Contact",
        "Use the Chummer5 Discord server.",
        "Use Contact to reach the Chummer5 Discord server.",
        "Chummer5 Discord",
    ):
        assert expected in combined


def test_faq_page_cleans_dynamic_public_copy_before_rendering() -> None:
    faq = read("Chummer.Run.Api/Views/PublicLanding/Faq.cshtml")

    for expected in (
        "@PublicText(Model.Eyebrow)",
        "@PublicText(Model.Heading)",
        "@PublicText(Model.Intro)",
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
        "static string PublicDownloadText(string? value) => UndetectableHumanizerCopyAdapter.Humanize(value);",
        "@PublicDownloadText(Model.Manifest.Message)",
        "stableAndNightlyMatch",
        "No newer Nightly right now.",
        "static string PublicStatusText(string? value) => UndetectableHumanizerCopyAdapter.Humanize(value);",
        "var statusLine = Model.ReleaseExperience.Recommended is null",
        ": publicPlatformSummary;",
        "@PublicStatusText(statusLine)",
    ):
        assert expected in combined

    for forbidden in (
        "<p>@Model.Manifest.Message</p>",
        "<p>@package.Summary</p>",
        "<p>@platform.Summary</p>",
        "<p>@Model.ReleaseSummary</p>",
        "var releaseSummaryText = PublicStatusText(Model.ReleaseSummary);",
        "var availabilityText = $\"{releaseAvailabilityLabel}. {compactReleaseSummary}\";",
        "@PublicStatusText(availabilityText)",
    ):
        assert forbidden not in combined


def test_download_dispatch_cleans_dynamic_public_copy_before_rendering() -> None:
    dispatch = read("Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml")

    for expected in (
        "static string PublicDispatchText(string? value) => UndetectableHumanizerCopyAdapter.Humanize(value);",
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


def test_homepage_has_minimal_promo_entry_surface() -> None:
    landing = read("Chummer.Run.Api/Views/PublicLanding/Landing.cshtml")

    assert "A Shadowrun character manager for clean sheets and faster tables." in landing
    assert "Download Chummer" in landing
    assert 'href="/downloads"' in landing
    assert 'href="/downloads#stable"' not in landing
    assert 'href="/downloads#nightly"' not in landing
    assert 'data-analytics-event="homepage_open_downloads"' in landing
    assert 'data-analytics-event="homepage_open_promo_video"' in landing
    assert 'homepage_open_stable' not in landing
    assert 'homepage_open_nightly' not in landing
    assert 'class="minimal-hero__visual minimal-hero__visual--screenshot"' in landing
    assert 'href="/media/promo/every-wonder-horizon-promo.mp4"' in landing
    assert "/media/product/chummer-desktop-runner.png" in landing
    assert "/media/promo/every-wonder-horizon-promo.mp4" in landing
    assert 'data-homepage-section="runner-roster"' not in landing
    assert landing.count("data-homepage-section=") == 1
    assert "minimal-runner-rail" in landing
    assert "Kestrel" in landing
    assert "Brick" in landing
    assert "Whisper" in landing
    assert '/account/open/example/decker' in landing
    assert '/account/open/example/street-samurai' in landing
    assert '/account/open/example/face' in landing
    assert 'href="/login?next=%2Fhome%2Faccess"' not in landing
    assert "/media/promo/every-wonder-horizon-promo.webm" not in landing
    assert "/media/promo/every-wonder-horizon-promo.vtt" not in landing
    assert 'data-homepage-section="downloads"' not in landing


def test_pwa_install_assets_do_not_use_internal_release_language() -> None:
    asset_paths = (
        "Chummer.Run.Api/wwwroot/manifest.webmanifest",
        "Chummer.Run.Api/wwwroot/site.webmanifest",
        "Chummer.Run.Api/wwwroot/manifest.json",
        "Chummer.Run.Api/wwwroot/pwa-screenshot-wide.svg",
        "Chummer.Run.Api/wwwroot/pwa-screenshot-mobile.svg",
        "Chummer.Run.Api/wwwroot/favicon.svg",
        "Chummer.Run.Api/wwwroot/pwa-icon.svg",
    )
    forbidden_terms = (
        "posture",
        "bounded",
        "rail",
        "lane",
        "handoff",
        "proof",
        "receipt",
        "artifact",
        "provider",
        "generated",
    )

    for path in asset_paths:
        source = read(path).lower()
        for term in forbidden_terms:
            assert term not in source, f"{path} should not expose internal term {term!r}"


def test_static_receipts_and_proofs_are_never_indexable() -> None:
    program = read("Chummer.Run.Api/Program.cs")
    indexable_function = program.split("static bool IsIndexablePublicPath(PathString path)", 1)[1].split("static bool IsLegacyMacReleaseBootstrapArtifactPath", 1)[0]
    wwwroot = REPO_ROOT / "Chummer.Run.Api" / "wwwroot"
    internal_static_assets = sorted(
        path
        for path in wwwroot.rglob("*")
        if path.is_file()
        and (
            path.name.endswith(".receipt.json")
            or path.name.endswith(".generated.json")
            or "/proofs/" in path.as_posix()
            or (
                path.name.endswith("manifest.json")
                and "/media/" in path.as_posix()
            )
        )
    )

    assert "app.UseStaticFiles(new StaticFileOptions" in program
    assert "OnPrepareResponse = fileContext =>" in program
    assert 'fileContext.Context.Response.Headers["X-Robots-Tag"] = ResolveRobotsPolicy' in program
    assert 'const string NoIndexRobotsPolicy = "noindex, nofollow, noarchive, nosnippet, noimageindex";' in program
    assert internal_static_assets

    for path in internal_static_assets:
        public_path = "/" + path.relative_to(wwwroot).as_posix()
        assert f'path.Equals("{public_path}"' not in indexable_function

    assert 'path.StartsWithSegments("/media"' not in indexable_function
    assert 'path.StartsWithSegments("/proofs"' not in indexable_function

    for path in (
        "/",
        "/downloads",
        "/status",
        "/help",
        "/privacy",
        "/ledger",
    ):
        assert f'path.Equals("{path}", StringComparison.OrdinalIgnoreCase)' in program


def test_public_mobile_and_changelog_hide_implementation_terms() -> None:
    landing = read("Chummer.Run.Api/Views/PublicLanding/Landing.cshtml")
    mobile = read("Chummer.Run.Api/Views/PublicLanding/MobileProjection.cshtml")
    changelog = read("Chummer.Run.Api/Views/PublicLanding/Changelog.cshtml")
    ledger_workspace = read("Chummer.Run.Api/Views/PublicLanding/LedgerFactionWorkspace.cshtml")
    site_css = read("Chummer.Run.Api/wwwroot/css/site.css")

    combined = "\n".join((mobile, changelog, ledger_workspace))

    for forbidden in (
        ">Open manifest<",
        ">Open service worker<",
        ">Open PWA JSON<",
        ">Open mobile setup file<",
        "service worker",
        "PWA JSON",
        "internal notes",
        "internal details",
        "hands off",
    ):
        assert forbidden not in combined

    assert "Open mobile view" in mobile
    assert "Open setup help" in mobile
    assert "campaign-only details" in ledger_workspace
    assert "Get the app" not in landing
    assert "minimal-inline-links" in landing
    assert 'data-homepage-section="help"' not in landing
    assert '@if (Model.Chrome.Authenticated)' in landing
    assert 'href="/participate"' in landing
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
    ]

    assert not (REPO_ROOT / "Chummer.Run.Api/Views/PublicLanding/Feedback.cshtml").exists()
    assert not (REPO_ROOT / "Chummer.Run.Api/Views/PublicLanding/Participate.cshtml").exists()
    assert (REPO_ROOT / "Chummer.Run.Api/Views/PublicLanding/Partizipate.cshtml").exists()

    for view_path in public_views:
        source = read(view_path)
        assert "workflow-card__proof" not in source
        assert "workflow-card__note" in source


def test_participation_surface_renders_first_party_without_character_helper_copy() -> None:
    controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")
    participate = read("Chummer.Run.Api/Views/PublicLanding/Partizipate.cshtml")

    assert (REPO_ROOT / "Chummer.Run.Api/Views/PublicLanding/Partizipate.cshtml").exists()
    assert not (REPO_ROOT / "Chummer.Run.Api/Views/PublicLanding/Participate.cshtml").exists()
    assert "DefaultProductLiftFeedbackUrl" not in controller
    assert "https://chummer6.productlift.dev" not in controller
    assert "public async Task<IActionResult> ParticipatePage" in controller
    assert "BuildFirstPartyParticipateBoardAsync" in controller
    assert 'return await ParticipateBoardFallbackAsync(cancellationToken, "/participate")' in controller
    assert '[HttpGet("/participate/board")]' in controller
    assert "ParticipateBoardProxy" in controller
    assert 'public async Task<IActionResult> ParticipateAliasPage(CancellationToken cancellationToken)' in controller
    assert 'BuildParticipateSignInHref(string targetPath = "/participate")' in controller
    assert '? _chrome.BuildPublicChrome(' in controller
    assert ': _chrome.BuildAuthenticatedChrome(' in controller
    assert 'HostedBoardHref: boardShellHref,' in controller
    assert 'canonicalHref: "/participate",' in controller
    assert 'DirectBoardHref: boardShellHref,' in controller
    assert "ResolveParticipateSupporterHref()" in controller
    assert 'BrilliantDirectoriesBillingService? billing = HttpContext?.RequestServices.GetService<BrilliantDirectoriesBillingService>();' in controller
    assert "hostedHeadingReplacement: null," in controller
    assert "hostedSummaryReplacement: null," in controller
    assert 'Heading: "Participate"' in controller
    assert 'Summary: "Participate"' in controller
    assert "Public requests, clear bugs, useful ideas." not in controller
    assert 'public IActionResult ParticipateBoardFrame(string? boardPath)' in controller
    assert ".text-primary," in controller
    assert ".dropdown-menu," in controller
    assert "var(--chummer-board-text)" in controller
    assert "Current requests" not in participate
    assert "participate-preview-card" not in participate
    assert "data-chummer-participate-frame" in participate
    assert "participate-hosted__frame" in participate
    assert 'title="Chummer participation board"' in participate
    assert "Model.SupporterHref" not in participate
    assert "@PublicParticipateText(" not in participate
    assert "@Model.Summary" not in participate
    assert "Board offline right now" in participate
    assert "Use Contact for the Chummer5 Discord server." in participate
    assert "Private support" not in participate
    assert "Supporter" not in participate
    assert "Support Chummer" not in participate
    assert "participate-preview-list" not in participate
    assert "participate-preview-card" not in participate
    assert "BuildParticipatePageModel(" not in controller
    assert "ExternalBoardUrl" not in controller
    assert "ExternalBoardUrl" not in read("Chummer.Run.Api/ViewModels/SiteViewModels.cs")

    for forbidden in (
        "ALICE build ghosts",
        "Build Ghost concierge",
        "Open Build Ghost",
    ):
        assert forbidden not in controller
        assert forbidden not in participate


def test_character_helper_page_uses_account_helper_language() -> None:
    helper = read("Chummer.Run.Api/Views/PublicLanding/BuildGhostConcierge.cshtml")

    assert "Account view" in helper
    assert "The account page keeps tradeoffs" in helper

    for forbidden in (
        "Signed-in helper",
        "The signed-in helper keeps tradeoffs",
    ):
        assert forbidden not in helper


def test_character_helper_chartbrick_insights_are_optional_and_chartbrick_scoped() -> None:
    service = read("Chummer.Run.Api/Services/KarmaForge/BuildGhostConciergeService.cs")
    helper = read("Chummer.Run.Api/Views/PublicLanding/BuildGhostConcierge.cshtml")
    controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")

    assert "CHUMMER_ALICE_CHARTBRICK_EXPLAIN_EMBED_URL" in service
    assert "CHUMMER_ALICE_CHARTBRICK_RUNNER_STATS_EMBED_URL" in service
    assert 'host.EndsWith("chartbrick.com"' in service
    assert 'string.Equals(uri.Scheme, Uri.UriSchemeHttps' in service
    assert "projection.Insights.Count > 0" in helper
    assert 'title="@SanitizePublicCopy(insight.Title)"' in helper
    assert 'src="@insight.EmbedHref"' in helper
    assert 'target="_blank" rel="noreferrer"' in helper
    assert "projection.Insights," in controller


def test_signed_in_alice_handoff_uses_chartbrick_runner_insights() -> None:
    service = read("Chummer.Run.Api/Services/KarmaForge/BuildGhostConciergeService.cs")
    controller = read("Chummer.Run.Api/Controllers/AccountsController.cs")
    account_view = read("Chummer.Run.Api/Views/Accounts/Account.cshtml")
    viewmodels = read("Chummer.Run.Api/ViewModels/SiteViewModels.cs")
    identity = read("Chummer.Run.Api/Services/HubIdentityClient.cs")

    assert "BuildChartBrickInsightsForHandoff" in service
    assert 'builder.Replace("{handoffId}"' in service
    assert 'builder.Replace("{runnerLabel}"' in service
    assert "_buildGhostConcierge.BuildChartBrickInsightsForHandoff(selectedBuildLabHandoff.HandoffId, selectedBuildLabHandoff.Title)" in controller
    assert "SelectedBuildLabInsights" in viewmodels
    assert "ALICE boards" in account_view
    assert "selectedBuildLabInsights.Length > 0" in account_view
    assert 'src="@insight.EmbedHref"' in account_view
    assert 'target="_blank" rel="noreferrer"' in account_view
    assert 'TryResolveLocalSeededSubject(request, accessToken, out AuthenticatedHubSubject? localSubject)' in identity
    assert '(_configuration["CHUMMER_LOCAL_E2E_ACCESS_TOKEN"] ?? string.Empty).Trim()' in identity
    assert '(_configuration["CHUMMER_LOCAL_E2E_SUBJECT_ID"] ?? "subject.demo").Trim()' in identity
    assert 'IPAddress.IsLoopback(remoteIp)' in identity


def test_participation_redirect_avoids_public_decision_and_account_explanation_page() -> None:
    controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")
    participate = read("Chummer.Run.Api/Views/PublicLanding/Partizipate.cshtml")
    layout = read("Chummer.Run.Api/Views/Shared/_Layout.cshtml")

    assert not (REPO_ROOT / "Chummer.Run.Api/Views/PublicLanding/Participate.cshtml").exists()
    assert (REPO_ROOT / "Chummer.Run.Api/Views/PublicLanding/Partizipate.cshtml").exists()
    assert "public async Task<IActionResult> ParticipatePage" in controller
    assert "ResolveProductLiftFeedbackUrl()" not in controller
    assert "productlift.dev" not in participate.lower()
    assert '"/participate/board"' in controller
    assert '"/participate"' in controller
    assert "suppressHeaderActionsForPublicParticipate" in layout
    assert "var suppressHeaderActionsForPublicParticipate = false;" in layout
    assert "@PublicParticipateText(" not in participate
    assert "@Model.Summary" not in participate
    assert "Current requests" not in participate
    assert "participate-preview-card" not in participate
    assert "data-chummer-participate-frame" in participate
    assert 'title="Chummer participation board"' in participate

    for forbidden in (
        "Account-only programs stay below the fold",
        "account options visible",
        "Keep the public loop simple and keep final decisions in Chummer.",
        "Chummer makes the final call",
        "Account participation",
        "Use the account path when public signal is not enough",
        "optional account paths",
        "signed-in programs stay below the fold",
        "signed-in options visible",
        "Keep the public loop visible, but keep authority inside Chummer.",
        "Chummer keeps the authority",
        "Signed-in participation",
        "Use the signed-in path when public signal is not enough",
        "optional signed-in paths",
    ):
        assert forbidden not in controller
        assert forbidden not in participate


def test_public_header_open_chummer_stays_email_first() -> None:
    chrome = read("Chummer.Run.Api/Services/HubPageChromeService.cs")
    sign_in_helper = chrome.split("private static string BuildContextualSignInHref", 1)[1].split("public SiteChromeViewModel BuildAuthenticatedChrome", 1)[0]

    assert 'return $"/login?next={Uri.EscapeDataString(normalizedCurrentPath)}";' in sign_in_helper
    forbidden_direct_google_routes = (
        'normalizedCurrentPath.StartsWith("/downloads", StringComparison.OrdinalIgnoreCase)',
        'normalizedCurrentPath.StartsWith("/participate", StringComparison.OrdinalIgnoreCase)',
        'normalizedCurrentPath.StartsWith("/partizipate", StringComparison.OrdinalIgnoreCase)',
    )
    for forbidden in forbidden_direct_google_routes:
        assert forbidden not in sign_in_helper


def test_billing_surface_uses_real_view_and_honest_supporter_copy() -> None:
    controller = read("Chummer.Run.Api/Controllers/BrilliantDirectoriesBillingController.cs")
    billing_view = read("Chummer.Run.Api/Views/Billing/Membership.cshtml")

    assert "ControllerBase" not in controller
    assert '"~/Views/Billing/Membership.cshtml"' in controller
    assert 'return Redirect($"/login?next={Uri.EscapeDataString("/account/billing")}")' in controller
    assert "<!doctype html>" not in controller
    assert '/auth/google/start?next={Uri.EscapeDataString("/account/billing")}' not in controller
    assert "1 book/month on Free. 2/month on Supporter." in billing_view
    assert "No extra app features today." in billing_view
    assert "@Model.Summary" in billing_view
    assert "Continue with email" in billing_view
    assert "used this month" in billing_view
    assert '__RequestVerificationToken' in billing_view
    assert "Manage supporter" in billing_view
    assert "Checkout stays attached to this account." in billing_view
    assert "Email first. Supporter attaches after that step." in billing_view
    assert "Back to account" in billing_view
    assert "Back to downloads" in billing_view
    assert "Free · 1 book/month" in billing_view
    assert "Supporter · 2 books/month" in billing_view
    assert "story-example" not in billing_view
    assert "Account attached: @Model.UserId" not in billing_view
    assert "temporarily unavailable" not in billing_view
    assert "Billing is unavailable" not in billing_view
    assert "Premium" not in billing_view
    assert "Upgrade" not in billing_view


def test_signal_packet_source_uses_plain_public_copy_labels() -> None:
    packet = read("Chummer.Run.Api/Views/Shared/_PublicSignalProjectionPacket.cshtml")

    assert "Open details" in packet
    assert "How this works" in packet
    assert "Limits" in packet
    assert "Public feedback can move into planning, but it does not replace help, roadmap, or release updates." in packet
    assert "guided planning path" in packet

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

    assert "guided request path" in combined
    assert "review route" in combined
    assert "id=\"review-next-steps\"" in karma_submitted
    assert "Request intake" in controller
    assert "Turn one table pain into a clear Chummer request" in controller
    assert "KARMA FORGE request saved" in controller
    assert "The request is saved. Chummer can now show the likely review route and the next questions." in controller
    assert "Consent must be accepted before Chummer can save the request." in controller
    assert "Your saved requests and next steps stay together." in karma_forge
    assert "Your requests stay visible here with current status." in karma_forge
    assert "No saved requests are visible yet." in karma_forge
    assert "new PublicNavigationLink(\"Saved notes\", \"#saved-details\")" in karma_submitted
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
    operations_detail = read("Chummer.Run.Api/Views/PublicLanding/FeedbackOperationsDetail.cshtml")

    for expected in (
        'ViewData["Title"] = UndetectableHumanizerCopyAdapter.Humanize(Model.Heading);',
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

    assert not (REPO_ROOT / "Chummer.Run.Api/Views/PublicLanding/Feedback.cshtml").exists()

    for source in (karma_forge, operations_detail):
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
        assert forbidden not in operations_detail


def test_public_header_uses_inline_neutral_navigation_instead_of_drawer_menu() -> None:
    layout = read("Chummer.Run.Api/Views/Shared/_Layout.cshtml")
    script = read("Chummer.Run.Api/wwwroot/js/site.js")
    site_css = read("Chummer.Run.Api/wwwroot/css/site.css")

    for forbidden in (
        "data-nav-toggle",
        "data-nav-panel",
        "site-nav-panel",
        "site-sidebar",
        "nav-panel-open",
        "nav-sheet-open",
    ):
        assert forbidden not in layout
        assert forbidden not in script

    nav_start = site_css.index(".site-nav {")
    nav_end = site_css.index(".action-form", nav_start)
    nav_css = site_css[nav_start:nav_end]
    minimal_start = site_css.index(".surface-minimal .site-nav a,")
    minimal_end = site_css.index(".surface-minimal .site-main", minimal_start)
    minimal_nav_css = site_css[minimal_start:minimal_end]
    menu_css = "\n".join((nav_css, minimal_nav_css))

    for forbidden in (
        "#0f4fcc",
        "#dfeaff",
        "#e7f0ff",
        "#f5f9ff",
        "#10243f",
        "#0d2242",
        "#081f40",
        "rgba(15, 79, 204",
    ):
        assert forbidden not in menu_css

    for expected in (
        "display: flex;",
        "flex-wrap: wrap;",
        "color: var(--ink-muted);",
        "text-decoration: underline;",
        "color: var(--minimal-muted);",
        "color: var(--minimal-ink);",
    ):
        assert expected in menu_css


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
        '("proofs", "details")',
        '("operators", "maintainers")',
        '("assistants", "help")',
        '("proof-bound", "status-based")',
        '("receipt-bound", "record-based")',
        '("release-backed", "release-based")',
        '("registry-backed", "record-based")',
        '("Product Governor", "product decision")',
        '("package truth", "package status")',
        '("governor", "guide")',
    ):
        assert phrase in humanizer


def test_account_home_does_not_replace_proof_language_with_check_language() -> None:
    home = read("Chummer.Run.Api/Views/PublicLanding/Home.cshtml")
    adapter = read("Chummer.Run.Api/Services/UndetectableHumanizerCopyAdapter.cs")

    assert '.Replace("proof", "check"' not in home
    assert "UndetectableHumanizerCopyAdapter.HumanizeHome(value)" in home
    assert '("proof", "status")' in adapter


def test_public_copy_cleanup_is_centralized_for_planning_and_package_pages() -> None:
    for view_path in (
        "Chummer.Run.Api/Views/PublicLanding/Roadmap.cshtml",
        "Chummer.Run.Api/Views/PublicLanding/_FeatureDetailRoadmap.cshtml",
        "Chummer.Run.Api/Views/PublicLanding/Changelog.cshtml",
        "Chummer.Run.Api/Views/PublicLanding/Packages.cshtml",
        "Chummer.Run.Api/Views/PublicLanding/PackageDetail.cshtml",
        "Chummer.Run.Api/Views/PublicLanding/PackageReceipt.cshtml",
    ):
        source = read(view_path)
        if view_path == "Chummer.Run.Api/Views/PublicLanding/Roadmap.cshtml":
            assert "Planned work and current requests." in source
            assert "In progress." not in source
            assert "Requests stay in Participate." not in source
            assert "Planned work lives here. Shipped work moves to Changelog." not in source
            assert "Work opens below." not in source
            assert 'href="/participate"' in source
            assert 'href="/changelog"' in source
        else:
            assert "PublicFacingCopyHumanizer.Clean" in source or "UndetectableHumanizerCopyAdapter.Humanize" in source
        for duplicated_rule in (
            '.Replace("proof',
            '.Replace("receipts"',
            '.Replace("receipt"',
            '.Replace("provider"',
            '.Replace("horizons"',
            '.Replace("horizon"',
            '.Replace("ALICE"',
            '.Replace("Alice"',
            '.Replace("Black Ledger"',
        ):
            assert duplicated_rule not in source


def test_login_surface_uses_plain_account_and_claim_copy_language() -> None:
    entry = read("Chummer.Run.Api/Views/Auth/Entry.cshtml")
    controller = read("Chummer.Run.Api/Controllers/AuthController.cs")
    combined = "\n".join((entry, controller))

    assert "@Model.Heading" in entry
    assert "@Model.SupportLine" in entry
    assert "@Model.ReturnLine" in entry
    assert "Email first. Google if you prefer." in combined
    assert "Claim this copy when you want installs, support, and recovery together." in combined
    assert "After this step, Chummer returns to" in combined
    assert "Continue with email" in entry
    assert "Continue with Google" in entry

    for forbidden in (
        "Create account",
        "Send magic link",
        "Campaign OS",
        "roadmap follows",
        "preview interest",
        "optional participation state",
        "claim tickets",
        "one calmer place",
        "faster return path",
        "A calmer return path",
        "The binary stays the same for everyone.",
        "Keep Chummer open while the browser finishes connecting this copy.",
        "Use email or Google. The download stays open.",
        "Account optional. Useful for linked installs, recovery, and private pages.",
        "Claim your copy",
        "Email me a link",
        "Use your email to sign in.",
        "Open your account. Keep installs and support together.",
        "Use the same copy. Add recovery and support history.",
    ):
        assert forbidden not in entry


def test_account_access_surface_prioritizes_installs_over_internal_sync_noise() -> None:
    account = read("Chummer.Run.Api/Views/Accounts/Account.cshtml")

    assert '"access" => "Installs"' in account
    assert "See linked copies, setup codes, downloads, and install help." in account
    assert "<summary>Connection details</summary>" in account
    assert "Recovery codes are only for the already-downloaded app when it asks for one." in account
    assert "<summary>Recent downloads</summary>" in account
    assert "<summary>Access grants</summary>" in account
    assert "<summary>Recovery backup</summary>" in account
    assert "Pending setup codes" in account

    for forbidden in (
        "<h2>Devices &amp; access</h2>",
        "Devices &amp; access",
        "Devices and access",
        "<summary>Account sync history</summary>",
        "<span>Account access status</span>",
        "<span>Account recovery path</span>",
        "<span>Blocking sync conflicts</span>",
        "Technical claim details stay available, but they do not need to be the first thing you read.",
        "Do not redeem claim codes in a browser tab.",
        "Linked copies, pending setup, and install help stay in one place. Technical details are still available, but they do not lead the page.",
        "Recovery codes stay below as a reserve option. They are not the normal way to set up Chummer.",
        "<span>Access updates</span>",
        "<span>Stale items</span>",
        "<span>Ready items</span>",
        "hub_entitlement_ledger",
        "No connection history is attached right now.",
        "No connection problems are active right now.",
        "without the internal machinery",
        "access right",
    ):
        assert forbidden not in account


def test_downloads_surface_hides_account_handoff_noise() -> None:
    downloads = read("Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml")

    assert "Stable" in downloads
    assert "Nightly" in downloads
    assert "Linux" in downloads
    assert "Build from source" in downloads
    assert "Download Chummer from the current release page." in downloads
    assert "Chummer selects the best installer when it can. Other downloads stay below." in downloads
    assert "attach this installed copy to your account" in downloads
    assert "Stable release." in downloads
    assert "<summary>Other downloads</summary>" in downloads
    assert "showLinuxSourcePrimary" in downloads
    assert "No sudo. Updates default to notify." in downloads
    assert "/downloads/build-chummer6-linux.sh" in downloads
    assert "stableAndNightlyMatch" in downloads
    assert "release.Alternatives.Concat(release.OtherPlatforms)" not in downloads
    assert "FirstOrDefault(IsNightly)" in downloads
    assert "static bool IsNightly(ReleaseOptionViewModel option)" in downloads
    assert 'value.Contains("nightly", StringComparison.OrdinalIgnoreCase)' in downloads
    assert "No newer Nightly right now." in downloads
    assert "Pick one." not in downloads
    assert "Chummer picks the right installer for this browser." not in downloads
    assert "Nightly currently matches Stable" not in downloads
    assert "There is no newer Nightly available" not in downloads
    assert "The newest promoted build available from this page." not in downloads

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
        "public shelf",
    ):
        assert forbidden not in downloads

    assert "@ButtonText(stable)" in downloads
    assert "@ButtonText(nightly)" in downloads
    assert "Download script" in downloads
    assert "Release freshness" not in downloads


def test_status_surface_uses_single_update_label() -> None:
    status = read("Chummer.Run.Api/Views/PublicLanding/Status.cshtml")

    assert 'ViewData["Title"] = "Status";' in status
    assert "<h1>Current release</h1>" in status
    assert "<h1>Updated</h1>" not in status
    assert 'ViewData["Title"] = "Updated";' not in status


def test_minimal_palette_stays_neutral_and_readable() -> None:
    site_css = read("Chummer.Run.Api/wwwroot/css/site.css")

    assert "--minimal-page: #111210;" in site_css
    assert "--minimal-surface: #181916;" in site_css
    assert "--minimal-ink: #f7f0df;" in site_css
    assert "--minimal-muted: #b8b09f;" in site_css
    assert "--minimal-line: rgba(247, 240, 223, 0.13);" in site_css
    assert "--minimal-soft: rgba(247, 240, 223, 0.045);" in site_css
    assert "--minimal-page: #fcfdfc;" not in site_css
    assert "--minimal-surface: #ffffff;" not in site_css
    assert "--minimal-ink: #0d0d0d;" not in site_css
    assert "--minimal-page: #f7f6f2;" not in site_css
    assert "--minimal-surface: #fffefa;" not in site_css
    assert "--minimal-soft: #ece8df;" not in site_css
    assert ".surface-minimal .field input" in site_css
    assert ".surface-minimal .field select option" in site_css


def test_public_form_controls_have_os_dark_safe_defaults() -> None:
    site_css = read("Chummer.Run.Api/wwwroot/css/site.css")

    assert 'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"])' in site_css
    assert "select option,\nselect optgroup" in site_css
    assert "color-scheme: dark;" in site_css
    assert "caret-color: var(--ink-strong);" in site_css
    assert "background: var(--bg-surface);" in site_css
    assert "color: var(--ink-strong);" in site_css
    assert "::placeholder" in site_css
    assert "opacity: 1;" in site_css


def test_public_copy_uses_maintenance_language_instead_of_horizon_metaphor() -> None:
    sources = [
        read("Chummer.Run.Api/Views/PublicLanding/Horizons.cshtml"),
        read("Chummer.Run.Api/Views/PublicLanding/FeatureDetail.cshtml"),
        read("Chummer.Run.Api/Views/PublicLanding/_FeatureDetailRoadmap.cshtml"),
    ]
    assert (REPO_ROOT / "Chummer.Run.Api/Views/PublicLanding/Partizipate.cshtml").exists()
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
        "Roadmap",
        "Planned work and current requests.",
    ):
        assert required in roadmap

    for required in (
        'href="/changelog"',
        'href="/participate"',
    ):
        assert required in roadmap

    assert "Use the right place" not in roadmap
    assert "Model.Milestones" not in roadmap
    assert 'id="roadmap-board"' not in roadmap
    assert "Top requests" not in roadmap

    controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")
    assert 'public async Task<IActionResult> RoadmapPage(CancellationToken cancellationToken)' in controller
    assert 'canonicalHref: "/roadmap"' in controller
    assert 'assetProxyBasePath: "/roadmap/provider-assets"' in controller
    assert 'pageTitle: "Roadmap - Chummer.run"' in controller
    assert '=> await RoadmapBoardFallbackAsync(cancellationToken, "/roadmap").ConfigureAwait(false);' in controller
    for forbidden in (
        "Milestone-backed public direction",
        "current readiness",
        "next honest routes",
        "Loaded through Chummer so the page stays first-party.",
        "Open live board",
    ):
        assert forbidden not in controller
        assert forbidden not in roadmap

    for required in (
        "static string RoadmapText(string? value)",
        "@RoadmapText(Model.Pain)",
        "@RoadmapText(Model.Payoff)",
        "@RoadmapText(Model.PrimaryAction.Label)",
    ):
        assert required in roadmap_detail

    for forbidden in (
        "@RoadmapText(item.Card.Title)",
        "@RoadmapText(item.Card.Summary)",
        "@RoadmapText(item.Action.Label)",
        "PublicSurfaceStatus.DisplayLabel(item.Card.Badge)",
        "These are the items that are moving right now.",
        "Already moving",
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
            "UndetectableHumanizerCopyAdapter.Humanize(Model.Pain)",
            "UndetectableHumanizerCopyAdapter.Humanize(Model.Payoff)",
            "UndetectableHumanizerCopyAdapter.Humanize(Model.PrimaryAction.Label)",
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

    assert "UndetectableHumanizerCopyAdapter.Humanize(Model.Promo.ProviderStatus)" in combined
    assert "UndetectableHumanizerCopyAdapter.Humanize(Model.PromoArtifact.ProviderStatus)" in combined
    assert "Your browser cannot play this video here." in combined

    for required in (
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Eyebrow)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Heading)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Intro)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.PrimaryAction.Label)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.SecondaryAction.Label)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.World.PublicName)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.World.TurnHeadline)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.World.MapNote)",
        "UndetectableHumanizerCopyAdapter.Humanize(dispatch.Type)",
        "UndetectableHumanizerCopyAdapter.Humanize(dispatch.Title)",
        "UndetectableHumanizerCopyAdapter.Humanize(dispatch.Summary)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.NewsreelStatus.StatusLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.NewsreelStatus.Summary)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.NewsreelStatus.ScopeLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(faction.Type)",
        "UndetectableHumanizerCopyAdapter.Humanize(faction.PublicName)",
        "UndetectableHumanizerCopyAdapter.Humanize(ledger.Label)",
        "UndetectableHumanizerCopyAdapter.Humanize(selectedFaction.PublicName)",
        "UndetectableHumanizerCopyAdapter.Humanize(accountCtaLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(selectedFaction.FactionLeader)",
        "UndetectableHumanizerCopyAdapter.Humanize(selectedFaction.FieldGm)",
        "UndetectableHumanizerCopyAdapter.Humanize(selectedFaction.IntelProvider)",
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
        'ViewData["Title"] = UndetectableHumanizerCopyAdapter.Humanize(Model.Heading);',
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Faction.PublicName)",
        "UndetectableHumanizerCopyAdapter.Humanize(action.Label)",
        "UndetectableHumanizerCopyAdapter.Humanize(action.Effect)",
        "UndetectableHumanizerCopyAdapter.Humanize(dispatch.Type)",
        "UndetectableHumanizerCopyAdapter.Humanize(dispatch.Title)",
        "UndetectableHumanizerCopyAdapter.Humanize(dispatch.Summary)",
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
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Faction.PublicName)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.WorldTurnBriefing.TransitionLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.WorldTurnBriefing.InboxHeadline)",
        "UndetectableHumanizerCopyAdapter.Humanize(item)",
    ):
        assert required in ledger_account

    for required in (
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Heading)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Summary.Heading)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Summary.Intro)",
        "UndetectableHumanizerCopyAdapter.Humanize(ballot.AudienceLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(ballot.Heading)",
        "UndetectableHumanizerCopyAdapter.Humanize(option.Label)",
        "UndetectableHumanizerCopyAdapter.Humanize(summary.Heading)",
        "UndetectableHumanizerCopyAdapter.Humanize(item)",
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
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Heading)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Intro)",
        "UndetectableHumanizerCopyAdapter.Humanize(step.Label)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.ExistingFactionSummary)",
        "UndetectableHumanizerCopyAdapter.Humanize(faction.Type)",
        "UndetectableHumanizerCopyAdapter.Humanize(faction.PublicName)",
        "UndetectableHumanizerCopyAdapter.Humanize(faction.Summary)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.MajorFounderSummary)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.ChallengerFounderSummary)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.MajorSlotsWarning)",
    ):
        assert required in ledger_onboarding

    for required in (
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Heading)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Intro)",
        "UndetectableHumanizerCopyAdapter.Humanize(archetype.Name)",
        "UndetectableHumanizerCopyAdapter.Humanize(rival.PublicName)",
        "UndetectableHumanizerCopyAdapter.Humanize(perk.Name)",
        "UndetectableHumanizerCopyAdapter.Humanize(flaw.Name)",
    ):
        assert required in ledger_create

    for required in (
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Heading)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Intro)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Promo.StaticCardLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Promo.CampaignHook)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Promo.StorylineSummary)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Promo.PlaybackLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Promo.PublicName)",
        "UndetectableHumanizerCopyAdapter.Humanize(frame.Label)",
        "UndetectableHumanizerCopyAdapter.Humanize(frame.VisualHook)",
        "UndetectableHumanizerCopyAdapter.Humanize(frame.ActionBeat)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Promo.CaptionLines[index])",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Promo.AudiencePromise)",
        "UndetectableHumanizerCopyAdapter.Humanize(scene.Label)",
        "UndetectableHumanizerCopyAdapter.Humanize(scene.Purpose)",
        "UndetectableHumanizerCopyAdapter.Humanize(scene.VisualDirection)",
        "UndetectableHumanizerCopyAdapter.Humanize(scene.NarratorLine)",
        "UndetectableHumanizerCopyAdapter.Humanize(format)",
    ):
        assert required in ledger_promo

    assert 'ViewData["Title"] = UndetectableHumanizerCopyAdapter.Humanize(Model.Heading);' in ledger_leader
    assert "UndetectableHumanizerCopyAdapter.Humanize(Model.Digest.PublicName)" in ledger_leader

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
        "UndetectableHumanizerCopyAdapter.Humanize(option.Kind)",
        "UndetectableHumanizerCopyAdapter.Humanize(option.Label)",
        "UndetectableHumanizerCopyAdapter.Humanize(option.Summary)",
        "UndetectableHumanizerCopyAdapter.Humanize(option.ActionLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.WorldTurnBriefing.TransitionLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.WorldTurnBriefing.InboxHeadline)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.WorldTurnBriefing.NewsreelLead)",
        "UndetectableHumanizerCopyAdapter.Humanize(beat)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.WorldTurnBriefing.Broadcast.PackageLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.WorldTurnBriefing.Broadcast.AnchorName)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.WorldTurnBriefing.Broadcast.DeskLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(beat.ActorKind)",
        "UndetectableHumanizerCopyAdapter.Humanize(beat.BeatLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(beat.ActorLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(message.Eyebrow)",
        "UndetectableHumanizerCopyAdapter.Humanize(message.Heading)",
        "UndetectableHumanizerCopyAdapter.Humanize(message.Summary)",
        "UndetectableHumanizerCopyAdapter.Humanize(message.StatusLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(message.CtaLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Status.StatusLabel)",
    ):
        assert required in ledger_notifications

    for required in (
        'ViewData["Title"] = UndetectableHumanizerCopyAdapter.Humanize(Model.Heading);',
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Heading)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Intro)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.Packet.WorldName)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.WorldTurnBriefing.TransitionLabel)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.WorldTurnBriefing.InboxHeadline)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.WorldTurnBriefing.NewsreelLead)",
        "UndetectableHumanizerCopyAdapter.Humanize(Model.LeaderDigest.PublicName)",
        "UndetectableHumanizerCopyAdapter.Humanize(item)",
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

    assert "Installs, campaigns, support, billing, and participation." in account
    assert "Private cases and the next step." in account
    assert "Characters, groups, and campaigns." in account
    assert "Membership and billing." in account
    assert "Start here" in account
    assert "Finish setup on that device" in account
    assert "Use the linked app first" in account
    assert "Table Pulse is ready for the next reaction on this campaign." in account
    assert "Ready for the next Table Pulse reaction." in account
    assert '? "Installs"' in account
    assert "See linked copies, setup codes, downloads, and install help. The app or installer still does the actual linking." in account
    assert "setup, recovery, and support stay with this account" in account
    assert "Add an email recovery path if you want an easier way back later." in account

    for forbidden in (
        "Move between installs, support, billing, participation, and campaigns.",
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
        "one calmer account page",
        "one calmer place",
        "one calmer product settings surface",
        "one calmer account view",
        "calmer return path",
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
        "Release and access status",
        "Download history",
        "Files and reconnect history",
        "Restore conflicts",
        "Ready history",
        "Needs refresh",
        "Participation update",
        "Restore note",
        "Details:",
        "Recap files",
        "Restore status",
        "Move roster state",
        "Prep set",
        "GM operations status",
        "Binding status",
        "Package status",
        "Current release status",
        "Help and privacy",
        "Recovery status",
        "Restore history",
        "Access history",
        "Legacy migration history",
        "Published file",
        "Target groups",
        "Original campaign",
        "Move note",
        "Travel note",
        "Prep note",
        "Package note",
        "Hint:",
        "Workspace restore conflicts",
        "Publication status",
        "Decision history",
        "Draft status",
        "Review status",
        "Case status",
        "Trust status",
    ):
        assert forbidden not in account

    assert "The download stays the same for everyone" in account
    assert "the account only keeps linked copies and support in reach" in account
    assert "Account state" in account
    assert "Recent downloads" in account
    assert "Files and reconnect" in account
    assert "Reconnect problems" in account
    assert "Ready updates" in account
    assert "Needs update" in account
    assert "Participation" in account
    assert "Reconnect note" in account
    assert "Notes:" in account
    assert "Recaps" in account
    assert "Reconnect" in account
    assert "Move roster" in account
    assert "Prep kits" in account
    assert "GM tools" in account
    assert "Linked prep" in account
    assert "Package" in account
    assert "Current app" in account
    assert "Help" in account
    assert "Recovery" in account
    assert "PublicText(" in account
    assert "Save consent to continue this access request." in account
    assert "Not resumable from this action." in account
    assert "Recent reconnects" in account
    assert "Linked-copy updates" in account
    assert "Imported Chummer5 files" in account
    assert "Public file" in account
    assert "Notes: @PublicText(output.ProvenanceSummary)" in account
    assert "Notes: @PublicText(item.ProvenanceSummary)" in account
    assert "Notes: @PublicText(answer.ProvenanceLabel)" in account
    assert "Notes: @PublicText(publication.ProvenanceSummary)" in account
    assert "Move to" in account
    assert "Move from" in account
    assert "Move reason" in account
    assert "Travel reason" in account
    assert "Prep reason" in account
    assert "Package reason" in account
    assert "Note: @sourceHintLine" in account
    assert "You do not currently manage a campaign" in account
    assert "No season or event activity is attached yet." in account
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
    assert "Delivery update" in sources["ledger_notifications"]
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

    assert "Original update" in feedback_operations
    assert "Open related details" in feedback_operations
    assert "Open details" in feedback_operations
    assert "Download summary" in feedback_operations
    assert "Download details" in feedback_operations
    assert "posted follow-up update" in signal_operations
    assert "message update" in feedback_operations
    assert "follow-up update" in feedback_operations
    assert "routing update" in feedback_operations
    assert "Recipient conversation" in feedback_operations
    assert "Message updates" in feedback_operations
    assert "delivery update" in feedback_operations
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
    assert "Request saved" in karma_submitted
    assert "Step saved" in karma_submitted
    assert "Background: @HomeText(leadAftermathShelfEntry.ProvenanceSummary)" in home
    assert "Output background: @HomeText(output.ProvenanceSummary)" in home
    assert "Background: @HomeText(answer.ProvenanceLabel)" in home
    assert "Background: @HomeText(publication.ProvenanceSummary)" in home
    assert "Hint: @PublicText(sourceHintLine)" in home


def test_submitted_pages_clean_dynamic_public_copy_before_rendering() -> None:
    support_submitted = read("Chummer.Run.Api/Views/PublicLanding/SupportSubmitted.cshtml")
    karma_submitted = read("Chummer.Run.Api/Views/PublicLanding/KarmaForgeSubmitted.cshtml")

    for expected in (
        "static string PublicSupportSubmittedText(string? value) => UndetectableHumanizerCopyAdapter.Humanize(value);",
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
        'ViewData["Title"] = UndetectableHumanizerCopyAdapter.Humanize(Model.Heading);',
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
        "Use the section links to move between installs, roster, and setup.",
        "Home summary",
        "The account cockpit answers this first",
        "Account flagship coverage",
        "Home can point to the next useful page",
        "Aftermath stays with this campaign.",
    ):
        assert expected in home

    for forbidden in (
        "Keep signed-in access and work sections in the shared side panel.",
        "Keep account access and work sections in the shared side panel.",
        "Signed-in continuity cockpit",
        "The signed-in cockpit answers",
        "Signed-in flagship coverage",
        "signed-in home view",
        "signed-in reaction fallout",
        "<span class=\"tag\">Workspace</span>",
        "Open campaign workspace",
        "Workspace note:",
        "Starter workspace",
    ):
        assert forbidden not in home

    assert '<section class="home-cockpit-strip" aria-label="Home summary">' in home
    assert '<section class="editorial-block">' in home


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

    assert "Search by item, message, recipient, delivery, or reference id." in lookup
    assert "Items and threads" in lookup
    assert "Items only" in lookup
    assert "Chummer history" in lookup
    assert "saved state" in lookup
    assert "saved feedback" in lookup
    assert "No item or thread matched" in lookup
    assert "Open result" in lookup
    assert "Open JSON" in lookup
    assert "Open lookup data" not in lookup
    assert "Open detail data" not in lookup
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

    assert "static string PublicReleaseUploadText(string? value) => UndetectableHumanizerCopyAdapter.Humanize(value);" in release_upload
    assert "@PublicReleaseUploadText(Model.Heading)" in release_upload
    assert "@PublicReleaseUploadText(Model.Summary)" in release_upload
    assert "@PublicReleaseUploadText(Model.WindowsUploadNote)" in release_upload

    for forbidden in (
        "<h1 class=\"page-title\">@Model.Heading</h1>",
        "<p class=\"page-copy\">@Model.Summary</p>",
        "<p>@Model.WindowsUploadNote</p>",
    ):
        assert forbidden not in release_upload

    assert "static string PublicGmVenueText(string? value) => UndetectableHumanizerCopyAdapter.Humanize(value);" in gm_session
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

    assert 'ViewData["Title"] = UndetectableHumanizerCopyAdapter.Humanize(Model.Heading);' in ready
    assert "@UndetectableHumanizerCopyAdapter.Humanize(Model.Eyebrow)" in ready
    assert "@UndetectableHumanizerCopyAdapter.Humanize(Model.Heading)" in ready

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
    copy_adapter = read("Chummer.Run.Api/Services/UndetectableHumanizerCopyAdapter.cs")
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
    assert "UndetectableHumanizerCopyAdapter.Humanize(value)" in packages
    assert "UndetectableHumanizerCopyAdapter.Humanize(value)" in package_detail
    assert "Recent activity" in package_detail
    assert "Open activity" in package_detail
    assert "Open package" not in packages
    assert "Use notes:" not in packages
    assert "Package fit" not in package_detail
    assert "Fit notes" not in package_detail
    assert "Community actions" not in package_detail
    assert "@PublicPackageText(receipt.ActorLabel)" in packages
    assert 'ViewData["Title"] = PublicPackageText(Model.Heading);' in package_receipt
    assert "UndetectableHumanizerCopyAdapter.Humanize(value)" in package_receipt
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
    assert "Details:</strong> @PublicText(publication.ProvenanceSummary)" in shelf
    assert "<span class=\"tag\">Origin</span>" in publication
    assert "related page" in publication
    assert "public static class UndetectableHumanizerCopyAdapter" in copy_adapter


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
    feedback_lookup = read("Chummer.Run.Api/Views/PublicLanding/FeedbackOperationsLookup.cshtml")
    combined = "\n".join((anarchy, feedback_lookup))

    for forbidden in (
        "Public claim ceiling",
        "public claim",
        "planned or shipped public claim",
    ):
        assert forbidden not in combined

    assert "What this path covers" in anarchy
    assert (REPO_ROOT / "Chummer.Run.Api/Views/PublicLanding/Partizipate.cshtml").exists()
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
        "static string PublicNowText(string? value) => UndetectableHumanizerCopyAdapter.Humanize(value);",
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
        "static string PublicPrivacyText(string? value) => UndetectableHumanizerCopyAdapter.Humanize(value);",
        "static string PublicSignedInTrustText(string? value) => UndetectableHumanizerCopyAdapter.Humanize(value);",
        "static string PublicTrustPulseText(string? value) => UndetectableHumanizerCopyAdapter.Humanize(value);",
        "@PublicPrivacyText(Model.Heading)",
        "@PublicPrivacyText(Model.Summary)",
        "@PublicPrivacyText(Model.PrimaryAction.Label)",
        "@PublicPrivacyText(domain.PublicProjection)",
        "@PublicPrivacyText(domain.SignedInProjection)",
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
        "Kept for:",
        "Removed from public pages:",
        "Public:",
        "Account:",
        "Never shown:",
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
        "Open saved pages",
        "Account return",
        "one library",
        "your runner and return details visible",
        "Your library keeps aftermath",
        "account history page(s)",
        "account return, or help",
        "Your library",
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
        "Open saved pages",
        "Create account for saved pages",
        "Your library keeps public and private returns together",
        "Choose gallery, downloads, saved pages, or help.",
    ):
        assert expected in publication

    for forbidden in (
        "Open signed-in account return view",
        "Create account for signed-in account return",
        "Use the signed-in detail view",
        "Signed-in account return keeps public and private returns together",
        "signed-in account-return view",
        "Choose gallery, downloads, signed-in account return, or help.",
    ):
        assert forbidden not in publication


def test_feature_detail_partials_use_account_detail_language() -> None:
    live = read("Chummer.Run.Api/Views/PublicLanding/_FeatureDetailLiveProof.cshtml")
    preview = read("Chummer.Run.Api/Views/PublicLanding/_FeatureDetailPreviewConcept.cshtml")
    roadmap = read("Chummer.Run.Api/Views/PublicLanding/_FeatureDetailRoadmap.cshtml")
    combined = "\n".join((live, preview, roadmap))

    for expected in (
        "Use your account details",
        "Open account details",
        "Open account detail",
        "Compare against your account details",
        "Open account details",
        "@RoadmapText(Model.ProofNote)",
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
        'ViewData["Title"] = UndetectableHumanizerCopyAdapter.Humanize(Model.Heading);',
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


def test_feature_detail_normalizes_release_detail_language_before_rendering() -> None:
    feature = read("Chummer.Run.Api/Views/PublicLanding/FeatureDetail.cshtml")

    assert 'const string ReleaseDetailFamily = "release-detail";' in feature
    assert 'displayFamily = string.Equals(Model.Family, "live-release", StringComparison.OrdinalIgnoreCase)' in feature
    assert feature.count('"live-release"') == 1
    assert 'case "live-release":' not in feature
    assert '"live-release" =>' not in feature
    assert 'Model.Family switch' not in feature


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

    assert "Short summary" in publication
    assert "Status: @routeStateLabel" in publication
    assert "ViewData[\"SurfaceClass\"] = \"surface-artifacts surface-minimal\";" in publication
    assert "ViewData[\"Title\"] = PublicPublicationText(Model.Publication.Title)" in publication
    assert "@PublicPublicationText(Model.Publication.Title)" in publication
    assert "@PublicPublicationText(Model.Publication.Summary)" in publication
    assert "@PublicPublicationText(Model.TrustPulse.RouteGuardSummary)" in publication
    assert "ViewData[\"Title\"] = Model.Publication.Title" not in publication
    assert "@Model.Publication.Title" not in publication
    assert "@Model.Publication.Summary" not in publication
    assert "@Model.TrustPulse.RouteGuardSummary" not in publication
    assert "Updated" in publication
    assert "Setup help nearby" in publication
    assert "Public discovery stays open" in publication
    assert "Some desktop work is still open, so this page stays short." in publication
    assert "Status</span>" in publication
    assert "History</span>" in publication
    assert "related page" in publication


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
    assert "Current section." in workspace
    assert "public Ledger pages" in workspace
    assert "account campaign pages" in workspace
    assert "Public Ledger pages" in workspace
    assert "account faction pages" in workspace
    assert "this account page" in workspace
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
    assert "Current turn summary" in account_home
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
    assert "Activity stays attached to this package page." in package_detail


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

    assert "offline return path" in mobile
    assert "continuity page" not in mobile
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
        "UndetectableHumanizerCopyAdapter.Humanize(receipt.Status)",
        "UndetectableHumanizerCopyAdapter.Humanize(receipt.Topic)",
        "UndetectableHumanizerCopyAdapter.Humanize(receipt.Summary)",
        "UndetectableHumanizerCopyAdapter.Humanize(receipt.Route)",
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
        "limited handoff path",
        "Use export as a handoff",
        "Foundry-style export is a handoff.",
        "what Chummer can hand off",
        "public-safe trust posture",
        "meeting handoff",
        "first-party account rails",
        "The packet is still local",
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
        '"Open runsites"',
        '"Open publication list"',
        '"Open command overview"',
        '"Open jump guide"',
        '"Open identity overview"',
        '"Open return details"',
        '"Open pressure summary"',
        '"Open pressure data"',
        '"Open bulletin summary"',
        '"Open bulletin data"',
        '"Open replay data"',
        '"Open mobile"',
        '"Download player notes"',
        '"Open first runsite"',
        "Read the session board before using Run Control at the table.",
        "Read the reconnect and recovery notes that keep live GM work attached to the same campaign.",
        "Read the starter guide before using ONRAMP for the first session.",
        "Read the restore and continuity notes that keep guided setup tied to the account.",
        "Read the hosted-first capability matrix before enabling local compute.",
        "Read the privacy and fallback notes that keep local acceleration optional.",
        "Read the quick-jump guide before using Quicksilver as your jump view.",
        "Read the targets and focus pages that keep expert speed inside Chummer.",
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
        "Read the account routes and control notes before using RUN CONTROL as the table hub.",
        "Read the account routes and recovery notes before treating ONRAMP like a simple tutorial overlay.",
        "The public guide shows the session board and continuity limits without pretending GM control is only a private surface.",
        "The public guide shows starter and recovery limits without pretending the product is an auto-build wizard.",
        "The public guides show the SR4, SR5, and SR6 differences without pretending visual styling is rules.",
        "The public guide shows which workloads may accelerate locally while keeping hosted mode available.",
        "limited export path",
        "Use export when it helps",
        "Foundry-style export creates files for another tool.",
        "what Chummer can export",
        "Runner Passport keeps account identity connected",
        "meeting links",
        "Chummer account pages",
        "This submission stays on this form",
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
        "Runner Passport keeps account identity connected to the Table Pulse inbox",
        "The account inbox is ready so the next remote reaction can enter the same between-session loop.",
        "The account inbox is already carrying",
        "Open the account inbox",
        "Open the account inbox",
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

    for forbidden in (
        "Foundry export remains a limited handoff path, not a separate flagship feature.",
        "This route explains what Chummer can hand off toward Foundry-style targets without making export support look like a separate product.",
        "Foundry-style export is a handoff.",
    ):
        assert forbidden not in controller

    for expected in (
        "Foundry export remains a limited export path, not a separate flagship feature.",
        "Export support",
        "This route explains what Chummer can export toward Foundry-style targets without making export support look like a separate product.",
        "Export path",
        "No separate public Foundry feature",
        "Chummer keeps the campaign state",
        "Foundry-style export creates files for another tool.",
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
    community_creator = read("Chummer.Run.Api/Services/CommunityCreatorHorizonsService.cs")
    hosted_contract = read("Chummer.Run.Api/Services/Support/HostedProofContractService.cs")
    hosted_context = read("Chummer.Run.Api/Services/Support/HostedBoundedContextCoverageService.cs")
    campaign_spine = read("Chummer.Run.Api/Services/Community/CampaignSpineService.cs")
    combined = "\n".join((controller, venue, community_creator, hosted_contract, hosted_context, campaign_spine))

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
        "How scheduling, handoff, and closeout stay clear",
        "Meeting handoff",
        "Scheduling, handoff, and closeout status stay in Chummer",
        "schedule, handoff, and closeout status agree",
        "schedule, meeting handoff, and closeout status",
        "meeting handoff can close the loop",
        "Meeting handoff is still pending",
        "schedule, handoff, and closeout records",
        "Fleet handoff",
        "Voice-required handoff",
        "meeting handoff can stay green",
        "Meeting handoff requires",
    ):
        assert forbidden not in combined

    for expected in (
        "Public venue status for an open run without leaking private room details.",
        "Public venue",
        "Public session title or run label.",
        "ready for account participants",
        "Public venue status only",
        "Account Community Hub keeps open-run listing, join review, scheduling, meeting links, and closeout together on Chummer pages.",
        "RulesOwner = \"Chummer\"",
        "WorldOwner = \"Chummer\"",
        "Public board status is readable without an account",
        "Private roster details, meeting access, and case handling stay in your Chummer account pages.",
        "Account board",
        "Public board",
        "Read the account and public pages without turning Community Hub into just another forum or meeting tool.",
        "account Community Hub page",
        "Chummer keeps the run, roster, scheduling, and closeout records together.",
        "Lead open run",
        "Use the open-run list when you want current table status before a public listing becomes a real table.",
        "Venue and meeting link",
        "meeting-service automation stays optional",
        "Chummer still keeps accepted roster and run status.",
        "does not hand run, roster, or closeout records to chat tools, meeting tools, or public boards.",
        "Room available to account participants",
        "How scheduling, meeting details, and closeout stay clear without exposing private table details.",
        "Meeting details",
        "Scheduling, meeting details, and closeout status stay in Chummer",
        "schedule, meeting details, and closeout status agree",
        "keeps listing, schedule, meeting details, and closeout status",
        "meeting details can close the loop",
        "Meeting details are still pending",
        "schedule, meeting details, and closeout records",
        "Fleet release steps",
        "Voice participation still needs explicit acknowledgement",
        "meeting details can stay green",
        "Meeting details require",
    ):
        assert expected in combined


def test_support_and_download_copy_uses_setup_and_release_language() -> None:
    support = read("Chummer.Run.Api/Services/Support/SupportCasePresentationService.cs")
    release = read("Chummer.Run.Api/Services/ReleaseSelectionService.cs")
    public_signal = read("Chummer.Run.Api/Services/PublicSignalOperationsService.cs")
    trust = read("Chummer.Run.Api/Services/SignedInTrustStatusService.cs")
    controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")
    combined = "\n".join((support, release, public_signal, trust, controller))

    for forbidden in (
        "release handoff may still be moving",
        "release handoff is still moving",
        "Windows install handoff",
        "Linux install handoff",
        "raw DMG handoff",
        "Moderation and help handoff",
        "First-party help handoff",
        "No release handoff is published yet.",
        "first-party Fixer Board",
    ):
        assert forbidden not in combined

    for expected in (
        "release step may still be moving",
        "release step is still moving",
        "Windows setup path",
        "Linux setup path",
        "raw DMG download",
        "Moderation and help review",
        "First-party help review",
        "No release download is published yet.",
        "Participate",
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
        "account area",
    ):
        assert expected in sources


def test_account_view_hides_internal_status_language_from_signed_in_users() -> None:
    account = read("Chummer.Run.Api/Views/Accounts/Account.cshtml")

    for forbidden in (
        "bounded trust continuity",
        "Assign bounded contribution work",
        "entitlement-sync history",
        "entitlement-sync conflicts",
        "The staged packet stays bounded",
        "Still bounded",
        "next bounded response",
    ):
        assert forbidden not in account

    for expected in (
        "Runner Passport is ready to update",
        "Assign contribution work and track progress.",
        "Open in Chummer",
        "Recent characters",
        "Groups and campaigns",
        "Example characters",
        "This account does not have a linked desktop copy yet, so clicks should take you into install and claim first.",
        "/account/open/character/",
        "/account/open/campaign/",
        "/account/open/group/",
        "/account/open/example/",
        "Install Chummer first",
        "Prepare offline travel files",
        "secrets and local caches stay on this device",
        "Not shared yet",
        "trigger or open the next response",
    ):
        assert expected in account

    for forbidden in (
        "Recent workspaces",
        "Example workspaces",
    ):
        assert forbidden not in account


def test_feedback_and_account_views_trim_remaining_operator_noise() -> None:
    account = read("Chummer.Run.Api/Views/Accounts/Account.cshtml")
    feedback = read("Chummer.Run.Api/Views/PublicLanding/FeedbackOperationsDetail.cshtml")
    humanizer = read("Chummer.Run.Api/Services/PublicFacingCopyHumanizer.cs")

    assert "Reconnect note:" in account
    assert "Social specialist focused on negotiation, cover, and team access." in account
    assert "Social operator focused on negotiation, cover, and team access." not in account
    assert "Restore update:" not in account
    assert "Notes: @PublicFacingCopyHumanizer.Clean(receipt.Proof)" in account
    assert "Observed: @receipt.ObservedAtUtc" not in account
    assert "State: @HumanizeStatus(receipt.StalenessPosture" not in account
    assert "Status: @HumanizeStatus(receipt.ConflictPosture" not in account
    assert "Conflict status:" not in account
    assert "Continue is blocked until this issue is resolved." not in account
    assert '@HumanizeStatus(action.Authority, "Chummer")' in account
    assert "Finish this item before you continue." in account

    assert "Open summary data" not in feedback
    assert "Open related details" in feedback
    assert "Outcome ·" not in feedback
    assert "Delivery ·" in feedback

    for expected in (
        '("summary data", "details")',
        '("conversation data", "conversation details")',
        '("recent action receipts", "recent activity")',
        '("provenance receipts", "history")',
        '("authority", "source")',
    ):
        assert expected in humanizer


def test_public_views_avoid_visible_receipt_and_verification_labels() -> None:
    ledger = read("Chummer.Run.Api/Views/PublicLanding/Ledger.cshtml")
    leaderboards = read("Chummer.Run.Api/Views/Leaderboards/Index.cshtml")

    assert "Viewer details" in ledger
    assert "Viewer receipt" not in ledger
    assert '<th scope="col">Confirmed</th>' in leaderboards
    assert '<th scope="col">Verified</th>' not in leaderboards


def test_email_preview_fallback_does_not_expose_live_ticket_by_default() -> None:
    auth_controller = read("Chummer.Run.Api/Controllers/AuthController.cs")
    account_links_controller = read("Chummer.Run.Api/Controllers/AccountLinksController.cs")
    browser_auth = read("Chummer.Run.Api/Services/HubBrowserAuthService.cs")
    identity_access = read("Chummer.Run.Identity/Services/IdentityAccessService.cs")
    email_delivery = read("Chummer.Run.Identity/Services/IdentityEmailDeliveryService.cs")

    assert "ShouldExposeInlinePreviewLink(Request)" in auth_controller
    assert "!string.IsNullOrWhiteSpace(started.TicketId)" in auth_controller
    assert "Email delivery is not available on this host right now." in auth_controller
    assert "ShouldExposeInlinePreviewLink(Request)" in account_links_controller
    assert "!string.IsNullOrWhiteSpace(started.TicketId)" in account_links_controller
    assert "public static bool ShouldExposeInlinePreviewLink(HttpRequest request)" in browser_auth
    assert "IDENTITY_UNSAFE_ALLOW_INLINE_EMAIL_PREVIEW_LINKS" in email_delivery
    assert 'DeliveryMode: "email_delivery_unavailable"' in email_delivery
    assert "IsInlinePreviewDelivery(delivery.DeliveryMode) && delivery.ExposeInlinePreviewTicket ? ticketId : string.Empty" in identity_access
    assert "AccessTokenHash" in identity_access
    assert "RefreshTokenHash" in identity_access
    assert "TicketHash" in identity_access
    assert "IDENTITY_EMAILIT_WEBHOOK_SECRET" in read("Chummer.Run.Identity/Controllers/IdentityController.cs")
    assert "IDENTITY_UNSAFE_ALLOW_UNSIGNED_EMAILIT_WEBHOOKS" in read("Chummer.Run.Identity/Controllers/IdentityController.cs")
    assert "StatusCodes.Status503ServiceUnavailable" in read("Chummer.Run.Identity/Controllers/IdentityController.cs")


def test_login_view_is_minimal_auth_surface() -> None:
    auth_entry = read("Chummer.Run.Api/Views/Auth/Entry.cshtml")
    auth_message = read("Chummer.Run.Api/Views/Auth/Message.cshtml")
    google_merge = read("Chummer.Run.Api/Views/Auth/GoogleMerge.cshtml")
    layout = read("Chummer.Run.Api/Views/Shared/_Layout.cshtml")
    auth_compact = read("Chummer.Run.Api/wwwroot/css/auth-compact.css")

    for expected in (
        'ViewData["SurfaceClass"] = Model.CreateAccount ? "surface-auth surface-minimal" : "surface-auth surface-minimal surface-auth-login";',
        'ViewData["HideAuthChrome"] = true;',
        "auth-entry--lean",
        "auth-panel__eyebrow",
        'class="button-like button-like--secondary auth-panel__primary"',
        "Continue with Google",
        "@Model.SupportLine",
        "@Model.ReturnLine",
    ):
        assert expected in auth_entry

    for expected in (
        'var hideAuthChrome = (ViewData["HideAuthChrome"] as bool?) == true;',
        "if (!hideAuthChrome)",
        'authSurface && minimalSurface',
        'href="~/css/auth-compact.css"',
    ):
        assert expected in layout

    for expected in (
        ".route-login.surface-auth.surface-minimal",
        "width: min(316px, calc(100vw - 24px));",
        "font-size: 1.38rem;",
        "min-height: 38px;",
        "padding: 14px;",
        ".surface-auth.surface-minimal.surface-auth-message",
    ):
        assert expected in auth_compact

    for compact_auth_view in (auth_message, google_merge):
        assert 'ViewData["SurfaceClass"] = "surface-auth surface-minimal surface-auth-message";' in compact_auth_view
        assert 'ViewData["HideAuthChrome"] = true;' in compact_auth_view
        assert "auth-entry--lean" in compact_auth_view
        assert "auth-shell__story" not in compact_auth_view
        assert "hero-brand" not in compact_auth_view
        assert "hero-headline" not in compact_auth_view

    for forbidden in (
        "clamp(1.75rem",
        "width: min(420px",
        "0 14px 34px",
        "linear-gradient",
    ):
        assert forbidden not in auth_compact


def test_minimal_landing_does_not_build_signed_in_or_campaign_surfaces_for_guests() -> None:
    controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")
    start = controller.index('public async Task<IActionResult> LandingPage(CancellationToken cancellationToken)')
    end = controller.index('[HttpGet("/what-is-chummer")]', start)
    action = controller[start:end]

    assert "hasAuthCookie" in action
    assert 'Request.Cookies.ContainsKey(HubBrowserAuthConstants.AccessTokenCookieName)' in action
    assert "hasAuthCookie && await TryIsAuthenticatedAsync(cancellationToken)" in action
    assert "TrustPulse: null" in action
    assert "SignedInStatus: null" in action
    assert "CampaignSpine: null" in action
    assert "OpenRail: null" in action

    for forbidden in (
        "BuildLandingCampaignSpineAsync",
        "BuildSignedInTrustStatusPanelAsync",
        "BuildPublicTrustPulsePanel",
        "_blackLedgerStats.ListHomepageStats",
        "_blackLedgerStats.LoadWorldPreview",
        "_blackLedgerDispatches.ListPublishedDispatches",
        "BuildLandingOpenRailAsync",
    ):
        assert forbidden not in action


def test_account_page_does_not_expose_fake_advanced_settings_surface() -> None:
    account_view = read("Chummer.Run.Api/Views/Accounts/Account.cshtml")
    controller = read("Chummer.Run.Api/Controllers/AccountsController.cs")
    billing_controller = read("Chummer.Run.Api/Controllers/BrilliantDirectoriesBillingController.cs")
    settings_view = read("Chummer.Run.Api/Views/Accounts/Settings.cshtml")

    assert '"settings" => "Billing"' not in account_view
    assert 'return Redirect("/account/settings");' in controller
    assert '[HttpGet("/account/settings")]' not in billing_controller
    assert '[HttpGet("/account/advanced")]' not in billing_controller
    assert 'AccountSettingsAlias' not in billing_controller
    assert 'Settings' in settings_view
    assert 'Open membership' in settings_view
    assert 'Save settings' in settings_view
    assert 'Follow new updates' in settings_view
    assert '"settings" => ("Account · Settings", "Update choices, sign-in, and privacy.")' in controller
    assert '"advanced" => ("Account · Advanced account details", "Linked identities, channels, and recovery metadata.")' not in controller
    assert not (REPO_ROOT / "Chummer.Run.Api/Views/Accounts/Advanced.cshtml").exists()
    assert "Open campaigns on the web" in account_view
    assert "<h2>Campaigns</h2>" in account_view
    assert "Starter campaign is not ready yet. Open Home > Campaigns to continue." in account_view
    assert "Open Home > Campaigns to continue." in account_view

    for forbidden in (
        "showAdvancedSection",
        '"advanced" => "Account · Billing"',
        '"advanced" => "Billing"',
        "SectionLinkViewModel(\"advanced\"",
        "Open work on the web",
        "<h2>Work</h2>",
        "deeper work continuity",
        "Open Home > Work to continue.",
        "Hub account id",
        "Provider-backed help",
        "Help and policy",
    ):
        assert forbidden not in account_view
        assert forbidden not in controller
        assert forbidden not in settings_view
