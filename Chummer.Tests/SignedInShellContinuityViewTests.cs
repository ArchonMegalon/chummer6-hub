using Xunit;

namespace Chummer.Tests;

public sealed class SignedInShellContinuityViewTests
{
    [Fact]
    public void HomeViewPublishesContinuityCockpitAndWhatChangedPacket()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("@if (!showAccessSection)", view, StringComparison.Ordinal);
        Assert.Contains("home-cockpit-strip", view, StringComparison.Ordinal);
        Assert.Contains("Home summary", view, StringComparison.Ordinal);
        Assert.Contains("Recent change", view, StringComparison.Ordinal);
        Assert.Contains("Use as guest or link this copy later.", view, StringComparison.Ordinal);
        Assert.Contains("Everything you need in one place.", view, StringComparison.Ordinal);
        Assert.Contains("<span class=\"tag\">Campaign</span>", view, StringComparison.Ordinal);
        Assert.Contains(">Open campaign</a>", view, StringComparison.Ordinal);
        Assert.DoesNotContain("<span class=\"tag\">Workspace</span>", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Open campaign workspace", view, StringComparison.Ordinal);
        Assert.Contains("Build, explain, and next step", view, StringComparison.Ordinal);
    }

    [Fact]
    public void HomeViewFailsClosedOnRawWorkspaceDecisionNoticeNoise()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("BuildCalmHomeDecisionNoticeSummary", view, StringComparison.Ordinal);
        Assert.Contains("WorkspaceNoticeSafety.LooksLikeInternalWorkspaceLeak", view, StringComparison.Ordinal);
        Assert.Contains("leadPortableExchangeSummary", view, StringComparison.Ordinal);
        Assert.Contains("A previous campaign needs attention before you continue. Open the campaign page for the safe next step.", view, StringComparison.Ordinal);
        Assert.Contains("Campaign note: @PublicText(leadWorkspaceDecisionNoticeSummary)", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Notice: @leadWorkspaceServerPlane.DecisionNotices[0].Summary", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Portable exchange: @leadPortableExchangeNotice.Summary", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountViewPublishesCalmAccountRailAndRecoveryFallbackCopy()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("account-rail-snapshot", view, StringComparison.Ordinal);
        Assert.Contains("Build next step", view, StringComparison.Ordinal);
        Assert.Contains("Contribution credit follows useful closeout and continuity.", view, StringComparison.Ordinal);
        Assert.Contains("Recovery codes stay in reserve.", view, StringComparison.Ordinal);
        Assert.Contains("Recovery codes stay below as a fallback, not the first instruction.", view, StringComparison.Ordinal);
        Assert.Contains("keep browser pages as backup help instead of the normal path", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountViewFailsClosedOnRawWorkspaceDecisionNoticeNoise()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("WorkspaceNoticeSafety.LooksLikeInternalWorkspaceLeak", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceDecisionNotices", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspacePortableExchangeSummary", view, StringComparison.Ordinal);
        Assert.Contains("A previous campaign needs attention before you continue. Open the campaign sections below for the next safe step.", view, StringComparison.Ordinal);
        Assert.DoesNotContain("foreach (var notice in selectedWorkspaceServerPlane.DecisionNotices)", view, StringComparison.Ordinal);
        Assert.DoesNotContain("@selectedWorkspacePortableExchangeNotice.Summary", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountViewPublishesCharacterAndGroupLauncherWithOnboardingFallback()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Open in Chummer", view, StringComparison.Ordinal);
        Assert.Contains("Recent characters", view, StringComparison.Ordinal);
        Assert.Contains("Groups and campaigns", view, StringComparison.Ordinal);
        Assert.Contains("Example characters", view, StringComparison.Ordinal);
        Assert.Contains("This account does not have a linked desktop copy yet, so clicks should take you into install and claim first.", view, StringComparison.Ordinal);
        Assert.Contains("/account/open/character/", view, StringComparison.Ordinal);
        Assert.Contains("/account/open/campaign/", view, StringComparison.Ordinal);
        Assert.Contains("/account/open/group/", view, StringComparison.Ordinal);
        Assert.Contains("/account/open/example/", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Recent workspaces", view, StringComparison.Ordinal);
        Assert.DoesNotContain(">Workspace<", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountViewPublishesOriginDossierGoldLibraryBehindVerifiedArtifactGates()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("id=\"origin-dossier-library\"", view, StringComparison.Ordinal);
        Assert.Contains("Origin Dossier library", view, StringComparison.Ordinal);
        Assert.Contains("Finished dossiers appear here.", view, StringComparison.Ordinal);
        Assert.Contains("data-story-scene-cover-uses-selected-character-face", view, StringComparison.Ordinal);
        Assert.Contains("data-audiobookshelf-playback-verified", view, StringComparison.Ordinal);
        Assert.Contains("data-undetectable-humanizer-applied", view, StringComparison.Ordinal);
        Assert.Contains("data-telegram-share-delivered", view, StringComparison.Ordinal);
        Assert.Contains("Story draft", view, StringComparison.Ordinal);
        Assert.Contains("Story polish", view, StringComparison.Ordinal);
        Assert.Contains("Book", view, StringComparison.Ordinal);
        Assert.Contains("Video", view, StringComparison.Ordinal);
        Assert.Contains("Share", view, StringComparison.Ordinal);
        Assert.Contains("Listen in Audiobookshelf", view, StringComparison.Ordinal);
        Assert.Contains("Audiobookshelf share locked", view, StringComparison.Ordinal);
        Assert.Contains("/account/work/origin-dossiers/@Uri.EscapeDataString(publication.ProjectId)", view, StringComparison.Ordinal);
        Assert.Contains("Open edition", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountControllerAndViewPublishAuthenticatedOriginDossierDetailSurface()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string detailViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "OriginDossier.cshtml");

        string controller = File.ReadAllText(controllerPath);
        string viewModels = File.ReadAllText(viewModelPath);
        string detailView = File.ReadAllText(detailViewPath);

        Assert.Contains("[HttpGet(\"/account/work/origin-dossiers/{originDossierProjectId}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"me/origin-dossiers/publications\")]", controller, StringComparison.Ordinal);
        Assert.Contains("_originDossierPublications.GetForAccount", controller, StringComparison.Ordinal);
        Assert.Contains("_originDossierPublications.UpsertForAccount", controller, StringComparison.Ordinal);
        Assert.Contains("OriginDossierPublicationImportRequest", controller, StringComparison.Ordinal);
        Assert.Contains("OriginDossierPublicationDetailPageViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("data-origin-dossier-detail", detailView, StringComparison.Ordinal);
        Assert.Contains("data-story-scene-cover-uses-selected-character-face", detailView, StringComparison.Ordinal);
        Assert.Contains("data-audiobookshelf-playback-verified", detailView, StringComparison.Ordinal);
        Assert.Contains("data-book-artifact-verified", detailView, StringComparison.Ordinal);
        Assert.Contains("data-dossier-video-verified", detailView, StringComparison.Ordinal);
        Assert.Contains("data-telegram-share-delivered", detailView, StringComparison.Ordinal);
        Assert.Contains("data-origin-edition-tabs", detailView, StringComparison.Ordinal);
        Assert.Contains("Readiness", detailView, StringComparison.Ordinal);
        Assert.Contains("Story draft", detailView, StringComparison.Ordinal);
        Assert.Contains("Story polish", detailView, StringComparison.Ordinal);
        Assert.Contains("Read in Audiobookshelf", detailView, StringComparison.Ordinal);
        Assert.Contains("Listen in Audiobookshelf", detailView, StringComparison.Ordinal);
        Assert.Contains("Watch scene movie", detailView, StringComparison.Ordinal);
        Assert.Contains("Canon Audit", detailView, StringComparison.Ordinal);
        Assert.Contains("Access notes", detailView, StringComparison.Ordinal);
        Assert.Contains("Dossier ebook share locked", detailView, StringComparison.Ordinal);
        Assert.Contains("Archived book locked", detailView, StringComparison.Ordinal);
        Assert.Contains("Dossier film locked", detailView, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountControllerPublishesFirstPartyDesktopLaunchBridge()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string launchViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "OpenInChummer.cshtml");
        string servicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "AccountDesktopLaunchTicketService.cs");

        string controller = File.ReadAllText(controllerPath);
        string viewModels = File.ReadAllText(viewModelPath);
        string launchView = File.ReadAllText(launchViewPath);
        string service = File.ReadAllText(servicePath);

        Assert.Contains("[HttpGet(\"/account/open/character/{dossierId}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/open/campaign/{campaignId}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/open/group/{groupId}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/open/example/{exampleId}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("_desktopLaunchTickets.Issue", controller, StringComparison.Ordinal);
        Assert.Contains("return Redirect(\"/downloads\");", controller, StringComparison.Ordinal);
        Assert.Contains("chummer://open?ticket=", controller, StringComparison.Ordinal);
        Assert.Contains("public sealed record AccountDesktopLaunchPageViewModel(", viewModels, StringComparison.Ordinal);
        Assert.Contains("id=\"launch-in-chummer\"", launchView, StringComparison.Ordinal);
        Assert.Contains("@Model.PrimaryLabel", launchView, StringComparison.Ordinal);
        Assert.Contains("window.location.href = launchHref;", launchView, StringComparison.Ordinal);
        Assert.Contains("public sealed class AccountDesktopLaunchTicketService", service, StringComparison.Ordinal);
        Assert.Contains("account_desktop_launch", service, StringComparison.Ordinal);
    }
}
