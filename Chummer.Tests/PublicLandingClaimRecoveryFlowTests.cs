using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingClaimRecoveryFlowTests
{
    [Fact]
    public void SignedInDispatchAndAccountAccessKeepRecoveryInInstallerOrAppFlow()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string releaseSelectionPath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "ReleaseSelectionService.cs");
        string dispatchViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml");
        string accountViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");

        string controller = File.ReadAllText(controllerPath);
        string releaseSelection = File.ReadAllText(releaseSelectionPath);
        string dispatchView = File.ReadAllText(dispatchViewPath);
        string accountView = File.ReadAllText(accountViewPath);
        string presenter = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Services", "Support", "SupportCasePresentationService.cs"));

        Assert.Contains("AccountLabel: \"Open Devices and access\"", controller, StringComparison.Ordinal);
        Assert.Contains("SupportLabel: \"Open tracked support\"", controller, StringComparison.Ordinal);
        Assert.Contains("DesktopInstallRail.BuildSupportHref(", controller, StringComparison.Ordinal);
        Assert.Contains("/continue.json", controller, StringComparison.Ordinal);
        Assert.Contains("ResolveSupportIntakeRailFromQuery()", controller, StringComparison.Ordinal);
        Assert.Contains("BuildSupportRailQuery(installRail)", controller, StringComparison.Ordinal);
        Assert.Contains(
            "Open the Windows install handoff, download the published setup .exe, and finish account linking in your default browser after setup starts the browser callback.",
            releaseSelection,
            StringComparison.Ordinal);
        Assert.Contains(
            "Automatic account linking is the default path. Use claim-code fallback only when Chummer explicitly says it is in recovery mode.",
            dispatchView,
            StringComparison.Ordinal);
        Assert.Contains(
            "Support follow-through stays on the same install rail, so the support form opens with this installer context instead of splitting recovery into a separate browser ritual.",
            dispatchView,
            StringComparison.Ordinal);
        Assert.Contains("@Model.SupportIntake.InstallAccessHref", File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml")), StringComparison.Ordinal);
        Assert.Contains("Recovery stays on this install rail", File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml")), StringComparison.Ordinal);
        Assert.Contains(
            "Enter each code in Chummer if it opens in recovery mode on the already-downloaded device. Do not redeem claim codes in a browser tab.",
            accountView,
            StringComparison.Ordinal);
        Assert.Contains("Current install rail", accountView, StringComparison.Ordinal);
        Assert.Contains("Recovery codes stay below as a fallback, not the first instruction.", accountView, StringComparison.Ordinal);
        Assert.Contains("Open Devices and access", presenter, StringComparison.Ordinal);
        Assert.Contains(
            "Follow-up stays attached to the affected claimed install. Use Account > Support for tracked history and Devices & access only when you need to relink or reclaim that copy.",
            presenter,
            StringComparison.Ordinal);
    }
}
