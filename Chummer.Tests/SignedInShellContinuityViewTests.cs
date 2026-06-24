using Xunit;

namespace Chummer.Tests;

public sealed class SignedInShellContinuityViewTests
{
    [Fact]
    public void HomeViewPublishesContinuityCockpitAndWhatChangedPacket()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("home-cockpit-strip", view, StringComparison.Ordinal);
        Assert.Contains("Home summary", view, StringComparison.Ordinal);
        Assert.Contains("Recent change", view, StringComparison.Ordinal);
        Assert.Contains("Use as guest or link this copy later.", view, StringComparison.Ordinal);
        Assert.Contains("Keep the whole product in view, not just the current install.", view, StringComparison.Ordinal);
        Assert.Contains("Workspace", view, StringComparison.Ordinal);
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
        Assert.Contains("A previous campaign workspace needs attention before you continue. Open the campaign workspace for the safe next step.", view, StringComparison.Ordinal);
        Assert.Contains("Workspace note: @PublicText(leadWorkspaceDecisionNoticeSummary)", view, StringComparison.Ordinal);
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
        Assert.Contains("Keep the browser step secondary.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountViewFailsClosedOnRawWorkspaceDecisionNoticeNoise()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("WorkspaceNoticeSafety.LooksLikeInternalWorkspaceLeak", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceDecisionNotices", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspacePortableExchangeSummary", view, StringComparison.Ordinal);
        Assert.Contains("A previous campaign workspace needs attention before you continue. Open the workspace sections below for the next safe step.", view, StringComparison.Ordinal);
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
