using System.Net;
using System.Net.Http.Headers;
using Chummer.Campaign.Contracts;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Contracts.Billing;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Xunit;

namespace Chummer.Tests;

public sealed class AccountHubRouteTests
{
    [Fact]
    public async Task AccountRootShowsMinimalHubForSignedInUser()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage(null, null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Hub.cshtml", view.ViewName);
        AccountHubPageViewModel model = Assert.IsType<AccountHubPageViewModel>(view.Model);
        Assert.Equal("Account", model.Chrome.Title);
        Assert.Equal("Account", model.Heading);
        Assert.Equal("Installs, runners, help, and membership live here.", model.Summary);
        Assert.Equal("Free", model.MembershipLabel);
        Assert.Equal("1 book each month. Same app.", model.MembershipSummary);
        Assert.Equal("1 of 1 Origin Book left this month.", model.BookQuotaSummary);
        Assert.Equal(4, model.Cards.Count);
        Assert.Equal("Installs", model.Cards[0].Title);
        Assert.Equal("Runners", model.Cards[1].Title);
        Assert.Equal("/account/roster", model.Cards[1].PrimaryHref);
        Assert.Equal("Help", model.Cards[2].Title);
        Assert.Equal("Membership", model.Cards[3].Title);
        Assert.Equal("Become supporter", model.Cards[3].PrimaryLabel);
        Assert.Equal("/account/billing", model.Cards[3].PrimaryHref);
        Assert.Equal("Details", model.Cards[3].SecondaryLabel);
        Assert.Equal("/account/billing", model.Cards[3].SecondaryHref);
    }

    [Fact]
    public async Task AccountRootReflectsSupporterOriginAllowanceFromSharedQuota()
    {
        using var fixture = AccountHubRouteFixture.Create();
        fixture.Billing.SyncMember(
            new BrilliantDirectoriesMemberSyncRequest(
                UserId: "subject.account-hub-route",
                MemberId: "supporter-membership",
                Email: "account.runner@example.invalid",
                PlanKey: "supporter",
                PlanName: "Supporter",
                MembershipStatus: "active",
                SupporterActive: true,
                ObservedAtUtc: new DateTimeOffset(2026, 6, 26, 12, 0, 0, TimeSpan.Zero)),
            "sync-secret");
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage(null, null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        AccountHubPageViewModel model = Assert.IsType<AccountHubPageViewModel>(view.Model);
        Assert.Equal("Supporter", model.MembershipLabel);
        Assert.Equal("2 books each month. Same app.", model.MembershipSummary);
        Assert.Equal("2 of 2 Origin Books left this month.", model.BookQuotaSummary);
        Assert.Equal("Membership", model.Cards[3].Title);
        Assert.Equal("Manage supporter", model.Cards[3].PrimaryLabel);
        Assert.Equal("/account/billing", model.Cards[3].PrimaryHref);
        Assert.Equal("Details", model.Cards[3].SecondaryLabel);
        Assert.Equal("/account/billing", model.Cards[3].SecondaryHref);
    }

    [Fact]
    public async Task AccountRootAddsMacOsBuildCardForAllowedAccount()
    {
        string? originalAllowedEmails = Environment.GetEnvironmentVariable("CHUMMER_RELEASE_UPLOAD_ALLOWED_EMAILS");
        try
        {
            Environment.SetEnvironmentVariable("CHUMMER_RELEASE_UPLOAD_ALLOWED_EMAILS", "account.runner@example.invalid");

            using var fixture = AccountHubRouteFixture.Create();
            AccountsController controller = fixture.CreateController();

            IActionResult result = await controller.AccountPage(null, null, CancellationToken.None);

            ViewResult view = Assert.IsType<ViewResult>(result);
            AccountHubPageViewModel model = Assert.IsType<AccountHubPageViewModel>(view.Model);
            AccountHubCardViewModel macOsCard = Assert.Single(model.Cards, card => string.Equals(card.Title, "Build macOS", StringComparison.Ordinal));
            Assert.Equal("/downloads/release-upload/bootstrap.command", macOsCard.PrimaryHref);
            Assert.Equal("/downloads/release-upload", macOsCard.SecondaryHref);
        }
        finally
        {
            Environment.SetEnvironmentVariable("CHUMMER_RELEASE_UPLOAD_ALLOWED_EMAILS", originalAllowedEmails);
        }
    }

    [Fact]
    public async Task AccountProfileRouteRedirectsToAccountHub()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("profile", null, CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/account", redirect.Url);
    }

    [Fact]
    public async Task AccountAccessRouteShowsMinimalSectionPage()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("access", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Section.cshtml", view.ViewName);
        AccountSectionPageViewModel model = Assert.IsType<AccountSectionPageViewModel>(view.Model);
        Assert.Equal("Installs", model.Eyebrow);
        Assert.Equal("Installs", model.Heading);
        Assert.Equal(3, model.Cards.Count);
        Assert.Equal("Downloads", model.Cards[0].Title);
        Assert.Equal("Linked copies", model.Cards[1].Title);
        Assert.Equal("Recovery", model.Cards[2].Title);
    }

    [Fact]
    public async Task AccountAccessRouteShowsLinkedCopiesThatCanBeUnlinked()
    {
        using var fixture = AccountHubRouteFixture.Create();
        fixture.SeedClaimedInstall("ins-account-access", "Desk rig");
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("access", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        AccountSectionPageViewModel model = Assert.IsType<AccountSectionPageViewModel>(view.Model);
        AccountAccessInstallationViewModel installation = Assert.Single(model.AccessInstallations!);
        Assert.Equal("Desk rig", installation.Title);
        Assert.Contains("windows x64", installation.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.True(installation.CanUnlink);
    }

    [Fact]
    public async Task AccountAccessUnlinkRevokesLinkedCopyAndRedirectsBackToAccess()
    {
        using var fixture = AccountHubRouteFixture.Create();
        fixture.SeedClaimedInstall("ins-account-unlink", "Travel laptop");
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.UnlinkInstall("ins-account-unlink", CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/account/access?accessNotice=unlinked", redirect.Url);
        InstallLinkingSummaryDto summary = fixture.InstallLinking.GetSummary("subject.account-hub-route", "subject.account-hub-route", 32);
        Assert.Contains(summary.ClaimedInstallations ?? Array.Empty<ClaimedInstallationDto>(),
            item => string.Equals(item.InstallationId, "ins-account-unlink", StringComparison.Ordinal)
                    && string.Equals(item.Status, ClaimedInstallationStates.Revoked, StringComparison.Ordinal));
        Assert.Empty(summary.ActiveGrants ?? Array.Empty<InstallationGrantDto>());
    }

    [Fact]
    public void AccountSectionViewRendersInlineUnlinkFormForAccessInstallations()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Section.cshtml"));

        Assert.Contains("action=\"/account/access/unlink\"", view, StringComparison.Ordinal);
        Assert.Contains(">Unlink</button>", view, StringComparison.Ordinal);
        Assert.Contains("Manage attached installs", view, StringComparison.Ordinal);
    }

    [Fact]
    public async Task AccountWorkRouteShowsMinimalSectionPage()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("work", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Section.cshtml", view.ViewName);
        AccountSectionPageViewModel model = Assert.IsType<AccountSectionPageViewModel>(view.Model);
        Assert.Equal("Roster", model.Eyebrow);
        Assert.Equal("Roster", model.Heading);
        Assert.Equal("Open runners, groups, and campaigns.", model.Summary);
        Assert.Equal(3, model.Cards.Count);
        Assert.StartsWith("/account/campaigns/", model.Cards[1].SecondaryHref, StringComparison.Ordinal);
    }

    [Fact]
    public async Task AccountRosterRouteIsThePublicRosterAlias()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("roster", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Section.cshtml", view.ViewName);
        AccountSectionPageViewModel model = Assert.IsType<AccountSectionPageViewModel>(view.Model);
        Assert.Equal("Roster", model.Heading);
        Assert.StartsWith("/account/campaigns/", model.Cards[1].SecondaryHref, StringComparison.Ordinal);
    }

    [Fact]
    public async Task AccountParticipationRouteShowsMinimalSectionPage()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("participation", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Section.cshtml", view.ViewName);
        AccountSectionPageViewModel model = Assert.IsType<AccountSectionPageViewModel>(view.Model);
        Assert.Equal("Participate", model.Eyebrow);
        Assert.Equal("Participate", model.Heading);
        Assert.Equal(3, model.Cards.Count);
        Assert.Equal("Participate", model.Cards[0].Title);
        Assert.Equal("Membership", model.Cards[1].Title);
        Assert.Equal("Private help", model.Cards[2].Title);
        Assert.Equal("Become supporter", model.Cards[1].PrimaryLabel);
        Assert.Equal("/account/billing", model.Cards[1].PrimaryHref);
        Assert.Equal("Details", model.Cards[1].SecondaryLabel);
        Assert.Equal("/account/billing", model.Cards[1].SecondaryHref);
    }

    [Fact]
    public async Task AccountParticipationRouteShowsManageSupporterForSupporterAccounts()
    {
        using var fixture = AccountHubRouteFixture.Create();
        fixture.Billing.SyncMember(
            new BrilliantDirectoriesMemberSyncRequest(
                UserId: "subject.account-hub-route",
                MemberId: "supporter-membership",
                Email: "account.runner@example.invalid",
                PlanKey: "supporter",
                PlanName: "Supporter",
                MembershipStatus: "active",
                SupporterActive: true,
                ObservedAtUtc: new DateTimeOffset(2026, 6, 26, 12, 0, 0, TimeSpan.Zero)),
            "sync-secret");
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("participation", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        AccountSectionPageViewModel model = Assert.IsType<AccountSectionPageViewModel>(view.Model);
        Assert.Equal("Manage supporter", model.Cards[1].PrimaryLabel);
        Assert.Equal("/account/billing", model.Cards[1].PrimaryHref);
        Assert.Equal("Details", model.Cards[1].SecondaryLabel);
        Assert.Equal("/account/billing", model.Cards[1].SecondaryHref);
    }

    [Fact]
    public async Task AccountSettingsRouteShowsDedicatedSettingsSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("settings", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Settings.cshtml", view.ViewName);
        AccountPageViewModel model = Assert.IsType<AccountPageViewModel>(view.Model);
        Assert.Equal("Account · Settings", model.Chrome.Title);
    }

    [Fact]
    public async Task AccountAdvancedRouteRedirectsToPreferences()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("advanced", null, CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/account/settings", redirect.Url);
    }

    [Fact]
    public async Task AccountSupportRouteShowsMinimalSupportSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("support", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Support.cshtml", view.ViewName);
        Assert.IsType<AccountPageViewModel>(view.Model);
    }

    [Fact]
    public async Task AccountCampaignDetailRouteShowsMinimalCampaignSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();
        string workspaceId = fixture.GetFirstWorkspaceId();

        IActionResult result = await controller.AccountPage("work", null, CancellationToken.None, workspaceId: workspaceId, runId: null, handoffId: null, entryId: null, publicationId: null, prepQuery: null);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Workspace.cshtml", view.ViewName);
        AccountPageViewModel model = Assert.IsType<AccountPageViewModel>(view.Model);
        Assert.Equal(workspaceId, model.SelectedWorkspace?.WorkspaceId);
    }

    [Fact]
    public async Task AccountRunDetailRouteShowsMinimalRunSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();
        string runId = fixture.GetFirstRunId();

        IActionResult result = await controller.AccountPage("work", null, CancellationToken.None, workspaceId: null, runId: runId, handoffId: null, entryId: null, publicationId: null, prepQuery: null);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Run.cshtml", view.ViewName);
        AccountPageViewModel model = Assert.IsType<AccountPageViewModel>(view.Model);
        Assert.Equal(runId, model.SelectedRun?.RunId);
    }

    [Fact]
    public async Task AccountBuildHandoffDetailRouteShowsMinimalBuildHandoffSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();
        string handoffId = fixture.GetFirstBuildLabHandoffId();

        IActionResult result = await controller.AccountPage("work", null, CancellationToken.None, workspaceId: null, runId: null, handoffId: handoffId, entryId: null, publicationId: null, prepQuery: null);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/BuildHandoff.cshtml", view.ViewName);
        AccountPageViewModel model = Assert.IsType<AccountPageViewModel>(view.Model);
        Assert.Equal(handoffId, model.SelectedBuildLabHandoff?.HandoffId);
    }

    [Fact]
    public async Task AccountRulesAnswerDetailRouteShowsMinimalRulesAnswerSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();
        string entryId = fixture.GetFirstRulesNavigatorEntryId();

        IActionResult result = await controller.AccountPage("work", null, CancellationToken.None, workspaceId: null, runId: null, handoffId: null, entryId: entryId, publicationId: null, prepQuery: null);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/RulesAnswer.cshtml", view.ViewName);
        AccountPageViewModel model = Assert.IsType<AccountPageViewModel>(view.Model);
        Assert.Equal(entryId, model.SelectedRulesNavigatorAnswer?.EntryId);
    }

    [Fact]
    public async Task AccountPublicationDetailRouteShowsMinimalPublicationSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();
        string publicationId = fixture.GetFirstCreatorPublicationId();

        IActionResult result = await controller.AccountPage("work", null, CancellationToken.None, workspaceId: null, runId: null, handoffId: null, entryId: null, publicationId: publicationId, prepQuery: null);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Publication.cshtml", view.ViewName);
        AccountPageViewModel model = Assert.IsType<AccountPageViewModel>(view.Model);
        Assert.Equal(publicationId, model.SelectedCreatorPublication?.PublicationId);
    }

    [Fact]
    public async Task AccountCreatorPublicationRouteShowsMinimalPublicationSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();
        string publicationId = fixture.GetFirstCreatorPublicationId();

        IActionResult result = await controller.CreatorPublicationPage(publicationId, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Publication.cshtml", view.ViewName);
        AccountPageViewModel model = Assert.IsType<AccountPageViewModel>(view.Model);
        Assert.Equal(publicationId, model.SelectedCreatorPublication?.PublicationId);
    }

    [Fact]
    public async Task AccountJackpointPublicationRouteShowsMinimalPublicationSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();
        string publicationId = fixture.GetFirstCreatorPublicationId();

        IActionResult result = await controller.JackpointPublicationPage(publicationId, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Publication.cshtml", view.ViewName);
        AccountPageViewModel model = Assert.IsType<AccountPageViewModel>(view.Model);
        Assert.Equal(publicationId, model.SelectedCreatorPublication?.PublicationId);
    }

    [Fact]
    public async Task AccountWorkspacePrepQueryKeepsLegacyDetailedSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();
        string workspaceId = fixture.GetFirstWorkspaceId();

        IActionResult result = await controller.AccountPage("work", null, CancellationToken.None, workspaceId: workspaceId, runId: null, handoffId: null, entryId: null, publicationId: null, prepQuery: "scene");

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Account.cshtml", view.ViewName);
        Assert.IsType<AccountPageViewModel>(view.Model);
    }

    [Fact]
    public async Task AccountSupportDetailRouteShowsMinimalSupportCaseSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        string caseId = fixture.SeedSupportCase();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("support", caseId, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/SupportCase.cshtml", view.ViewName);
        AccountPageViewModel model = Assert.IsType<AccountPageViewModel>(view.Model);
        Assert.Equal(caseId, model.SelectedSupportCase?.CaseId);
        Assert.NotNull(model.SelectedSupportCaseSummary);
    }

    [Fact]
    public void SupportCaseViewRendersMinimalTrackedCaseSurface()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "SupportCase.cshtml"));

        Assert.Contains("Back to support", view, StringComparison.Ordinal);
        Assert.Contains("One case id. One next step.", view, StringComparison.Ordinal);
        Assert.Contains("data-support-verification-outcome", view, StringComparison.Ordinal);
        Assert.Contains("<summary>Timeline</summary>", view, StringComparison.Ordinal);
    }

    [Fact]
    public void RunViewRendersMinimalTrackedRunSurface()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Run.cshtml"));

        Assert.Contains("Current run and the next step.", view, StringComparison.Ordinal);
        Assert.Contains("Open Table Pulse", view, StringComparison.Ordinal);
        Assert.Contains("Signal Deck", view, StringComparison.Ordinal);
        Assert.Contains("Latest visible scenes.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void BuildHandoffViewRendersMinimalTrackedBuildSurface()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "BuildHandoff.cshtml"));

        Assert.Contains("Only the current next steps.", view, StringComparison.Ordinal);
        Assert.Contains("Before and after stay explicit here.", view, StringComparison.Ordinal);
        Assert.Contains("<summary>ALICE boards</summary>", view, StringComparison.Ordinal);
        Assert.Contains("Open rules answer", view, StringComparison.Ordinal);
    }

    [Fact]
    public void RulesAnswerViewRendersMinimalTrackedRulesSurface()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "RulesAnswer.cshtml"));

        Assert.Contains("Current lifecycle and next move.", view, StringComparison.Ordinal);
        Assert.Contains("Only the visible environment changes.", view, StringComparison.Ordinal);
        Assert.Contains("<summary>More context</summary>", view, StringComparison.Ordinal);
        Assert.Contains("Grounding stays visible here", view, StringComparison.Ordinal);
    }

    [Fact]
    public void WorkspaceViewRendersMinimalTrackedWorkspaceSurface()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Workspace.cshtml"));

        Assert.Contains("Read-only overview. Search and launch stay on the full prep screen.", view, StringComparison.Ordinal);
        Assert.Contains("What is moving through this campaign.", view, StringComparison.Ordinal);
        Assert.Contains("<summary>Recent returns</summary>", view, StringComparison.Ordinal);
        Assert.Contains("Open the current run directly.", view, StringComparison.Ordinal);
        Assert.Contains("Session note, memory, and recap stay together here.", view, StringComparison.Ordinal);
        Assert.Contains("Current state and next step.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicationViewRendersMinimalTrackedPublicationSurface()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Publication.cshtml"));

        Assert.Contains("Only the current status and the next useful move.", view, StringComparison.Ordinal);
        Assert.Contains("Move this publication into the next review step.", view, StringComparison.Ordinal);
        Assert.Contains("<summary>More context</summary>", view, StringComparison.Ordinal);
        Assert.Contains("Make it discoverable when it is actually ready.", view, StringComparison.Ordinal);
    }

    [Fact]
    public async Task AccountWorkEditionQueryKeepsLegacyDetailedSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();
        controller.ControllerContext.HttpContext.Request.QueryString = new QueryString("?edition=sr6");

        IActionResult result = await controller.AccountPage("work", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Account.cshtml", view.ViewName);
        Assert.IsType<AccountPageViewModel>(view.Model);
    }

    [Fact]
    public async Task AccountAccessLocalCoProcessorQueryKeepsLegacyDetailedSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();
        controller.ControllerContext.HttpContext.Request.QueryString = new QueryString("?localCoProcessor=paranoid");

        IActionResult result = await controller.AccountPage("access", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Account.cshtml", view.ViewName);
        Assert.IsType<AccountPageViewModel>(view.Model);
    }

    private sealed class AccountHubRouteFixture : IDisposable
    {
        private const string AccessToken = "account-hub-route-token";
        private readonly ServiceProvider _provider;

        private AccountHubRouteFixture(string root, ServiceProvider provider)
        {
            Root = root;
            _provider = provider;
        }

        public string Root { get; }
        public BrilliantDirectoriesBillingService Billing => _provider.GetRequiredService<BrilliantDirectoriesBillingService>();
        public InstallLinkingService InstallLinking => _provider.GetRequiredService<InstallLinkingService>();
        public SupportCaseService SupportCases => _provider.GetRequiredService<SupportCaseService>();
        public CampaignSpineService CampaignSpine => _provider.GetRequiredService<CampaignSpineService>();
        public AccountService Accounts => _provider.GetRequiredService<AccountService>();

        public static AccountHubRouteFixture Create()
        {
            string root = Path.Combine(Path.GetTempPath(), "chummer-account-hub-route-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(root, "community.json"),
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(root, "install-linking.json"),
                    ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(root, "support.json"),
                    ["CHUMMER_PUBLIC_CONCIERGE_STORE_PATH"] = Path.Combine(root, "public-concierge.json"),
                    ["CHUMMER_KARMA_FORGE_STORE_PATH"] = Path.Combine(root, "karma-forge.json"),
                    ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(root, "bd-billing.json"),
                    ["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"] = Path.Combine(root, "myfirstbook-usage.json"),
                    ["CHUMMER_BILLING_SYNC_SECRET"] = "sync-secret",
                    ["BRILLIANT_DIRECTORIES_SYNC_SECRET"] = "sync-secret",
                    ["BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL"] = "https://billing.example.test/supporter",
                    ["CHUMMER_PAYFUNNELS_BILLING_STORE_PATH"] = Path.Combine(root, "payfunnels-billing.json"),
                    ["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run",
                    ["CHUMMER_LOCAL_E2E_ACCESS_TOKEN"] = AccessToken,
                    ["CHUMMER_LOCAL_E2E_SUBJECT_ID"] = "subject.account-hub-route",
                    ["CHUMMER_LOCAL_E2E_DISPLAY_NAME"] = "Account Runner",
                    ["CHUMMER_LOCAL_E2E_EMAIL"] = "account.runner@example.invalid",
                    ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.test"
                })
                .Build();

            ServiceCollection services = new();
            services.AddSingleton(configuration);
            services.AddSingleton<IHostEnvironment>(new TestHostEnvironment(root));
            services.AddLogging();
            services.AddControllersWithViews();
            services.AddDataProtection().PersistKeysToFileSystem(new DirectoryInfo(Path.Combine(root, "data-protection-keys")));
            services
                .AddHubPublicGuideContext()
                .AddHubAccountsAndCommunityContext()
                .AddHubCampaignSpineContext()
                .AddHubControlAndSupportContext()
                .AddHubInstallAndOrchestrationAdapters();
            return new AccountHubRouteFixture(root, services.BuildServiceProvider());
        }

        public AccountsController CreateController(bool authenticated = true)
        {
            AccountsController controller = ActivatorUtilities.CreateInstance<AccountsController>(_provider);
            DefaultHttpContext httpContext = new()
            {
                RequestServices = _provider
            };
            httpContext.Request.Host = new HostString("localhost");
            httpContext.Connection.RemoteIpAddress = IPAddress.Loopback;
            if (authenticated)
            {
                httpContext.Request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", AccessToken).ToString();
            }

            controller.ControllerContext = new ControllerContext
            {
                HttpContext = httpContext
            };
            return controller;
        }

        public void SeedClaimedInstall(string installationId, string hostLabel)
        {
            IssueInstallBrowserCallbackResponseDto issued = InstallLinking.IssueBrowserCallback(
                new IssueInstallBrowserCallbackRequestDto(
                    InstallationId: installationId,
                    ArtifactId: "avalonia-win-x64-installer",
                    ApplicationVersion: "6.0.1-preview",
                    ChannelId: "preview",
                    HeadId: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    CallbackUri: "chummer://install-link",
                    PublicKey: "public-key",
                    HostLabel: hostLabel,
                    InstallAccessClass: InstallAccessClasses.AccountRecommended),
                userId: "subject.account-hub-route",
                subjectId: "subject.account-hub-route");

            InstallLinking.ExchangeBrowserCallback(
                new ExchangeInstallBrowserCallbackRequestDto(
                    CallbackCode: issued.Callback.CallbackCode,
                    InstallationId: installationId,
                    HeadId: "avalonia",
                    ApplicationVersion: "6.0.1-preview",
                    ChannelId: "preview",
                    Platform: "windows",
                    Arch: "x64",
                    PublicKey: "public-key",
                    HostLabel: hostLabel));
        }

        public string SeedSupportCase()
        {
            SupportCaseProjection supportCase = SupportCases.Submit(
                reporterUserId: "subject.account-hub-route",
                reporterSubjectId: "subject.account-hub-route",
                new SupportCaseSubmitRequest(
                    Kind: SupportCaseKinds.BugReport,
                    Title: "Install button was unclear",
                    Summary: "The update path did not explain the next step.",
                    Detail: "The signed-in update flow looked finished before the install actually reopened.",
                    ReporterEmail: "account.runner@example.invalid",
                    InstallationId: "ins-account-support",
                    ApplicationVersion: "6.0.1-preview",
                    ReleaseChannel: "preview",
                    HeadId: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Source: SupportCaseSourceKinds.HubAccount));
            return supportCase.CaseId;
        }

        public string GetFirstRunId()
        {
            HubUserDto user = Accounts.EnsureUser("subject.account-hub-route", "Account Runner", "account.runner@example.invalid");
            InstallLinkingSummaryDto installLinking = InstallLinking.GetSummary("subject.account-hub-route", "subject.account-hub-route");
            AccountCampaignSummary summary = CampaignSpine.GetAccountSummary(user, installLinking);
            Assert.NotEmpty(summary.Runs);
            RunProjection run = summary.Runs
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .First();
            return run.RunId;
        }

        public string GetFirstBuildLabHandoffId()
        {
            HubUserDto user = Accounts.EnsureUser("subject.account-hub-route", "Account Runner", "account.runner@example.invalid");
            InstallLinkingSummaryDto installLinking = InstallLinking.GetSummary("subject.account-hub-route", "subject.account-hub-route");
            AccountCampaignSummary summary = CampaignSpine.GetAccountSummary(user, installLinking);
            Assert.NotEmpty(summary.BuildLabHandoffs);
            BuildLabHandoffProjection handoff = summary.BuildLabHandoffs
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .First();
            return handoff.HandoffId;
        }

        public string GetFirstRulesNavigatorEntryId()
        {
            HubUserDto user = Accounts.EnsureUser("subject.account-hub-route", "Account Runner", "account.runner@example.invalid");
            InstallLinkingSummaryDto installLinking = InstallLinking.GetSummary("subject.account-hub-route", "subject.account-hub-route");
            AccountCampaignSummary summary = CampaignSpine.GetAccountSummary(user, installLinking);
            Assert.NotEmpty(summary.RulesNavigator);
            RulesNavigatorAnswerProjection entry = summary.RulesNavigator
                .OrderBy(static item => item.EntryId, StringComparer.OrdinalIgnoreCase)
                .First();
            return entry.EntryId;
        }

        public string GetFirstCreatorPublicationId()
        {
            HubUserDto user = Accounts.EnsureUser("subject.account-hub-route", "Account Runner", "account.runner@example.invalid");
            InstallLinkingSummaryDto installLinking = InstallLinking.GetSummary("subject.account-hub-route", "subject.account-hub-route");
            AccountCampaignSummary summary = CampaignSpine.GetAccountSummary(user, installLinking);
            Assert.NotEmpty(summary.CreatorPublications);
            CreatorPublicationProjection publication = summary.CreatorPublications
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ThenBy(static item => item.Title, StringComparer.OrdinalIgnoreCase)
                .First();
            return publication.PublicationId;
        }

        public string GetFirstWorkspaceId()
        {
            HubUserDto user = Accounts.EnsureUser("subject.account-hub-route", "Account Runner", "account.runner@example.invalid");
            InstallLinkingSummaryDto installLinking = InstallLinking.GetSummary("subject.account-hub-route", "subject.account-hub-route");
            AccountCampaignSummary summary = CampaignSpine.GetAccountSummary(user, installLinking);
            Assert.NotEmpty(summary.Workspaces);
            CampaignWorkspaceProjection workspace = summary.Workspaces
                .OrderByDescending(static item => item.Runs.Count)
                .ThenBy(static item => item.CampaignName, StringComparer.OrdinalIgnoreCase)
                .First();
            return workspace.WorkspaceId;
        }

        public void Dispose()
        {
            _provider.Dispose();
            if (Directory.Exists(Root))
            {
                Directory.Delete(Root, recursive: true);
            }
        }

        private sealed class TestHostEnvironment(string contentRootPath) : IHostEnvironment
        {
            public string EnvironmentName { get; set; } = Environments.Development;
            public string ApplicationName { get; set; } = "Chummer.Tests";
            public string ContentRootPath { get; set; } = contentRootPath;
            public IFileProvider ContentRootFileProvider { get; set; } = new PhysicalFileProvider(contentRootPath);
        }
    }
}
