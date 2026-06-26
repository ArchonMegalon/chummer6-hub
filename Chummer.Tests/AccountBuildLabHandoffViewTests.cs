using Xunit;

namespace Chummer.Tests;

public sealed class AccountBuildLabHandoffViewTests
{
    [Fact]
    public void AccountNavigationUsesRealDestinationsInsteadOfFakeSettingsSurfaces()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string controller = File.ReadAllText(controllerPath);
        string view = File.ReadAllText(viewPath);

        Assert.Contains("|| string.Equals(selectedSection, \"advanced\", StringComparison.OrdinalIgnoreCase)", controller, StringComparison.Ordinal);
        Assert.Contains("return Redirect(\"/account/billing\")", controller, StringComparison.Ordinal);
        Assert.Contains("new SectionLinkViewModel(\"access\", \"Installs\"", controller, StringComparison.Ordinal);
        Assert.Contains("new SectionLinkViewModel(\"work\", \"Campaigns\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("new SectionLinkViewModel(\"advanced\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("new SectionLinkViewModel(\"settings\"", controller, StringComparison.Ordinal);

        Assert.Contains("\"settings\" => \"Billing\"", view, StringComparison.Ordinal);
        Assert.Contains("Move between profile, installs, support, billing, participation, and campaigns.", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Move between profile, access, support, and work", view, StringComparison.Ordinal);
        Assert.DoesNotContain("\"work\" => \"Work\"", view, StringComparison.Ordinal);
        Assert.DoesNotContain("\"advanced\" => \"Billing\"", view, StringComparison.Ordinal);
        Assert.DoesNotContain("\"advanced\" => \"Advanced account details\"", view, StringComparison.Ordinal);
        Assert.Contains("Open campaigns on the web", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Open work on the web", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountWorkDetailRendersPerOutputBuildLabFollowThroughCues()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("selectedBuildLabHandoff.Outputs.Take(3)", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.Outputs.Count - 3", view, StringComparison.Ordinal);
        Assert.Contains("@output.NextSafeAction", view, StringComparison.Ordinal);
        Assert.Contains("PublicText(output.ProvenanceSummary)", view, StringComparison.Ordinal);
        Assert.Contains("BuildLabOutputLaneLabel(output.Kind)", view, StringComparison.Ordinal);
        Assert.Contains("@output.PublicationSummary", view, StringComparison.Ordinal);
        Assert.Contains("output.PublicationState", view, StringComparison.Ordinal);
        Assert.Contains("output.TrustBand", view, StringComparison.Ordinal);
        Assert.Contains("PublicFacingCopyHumanizer.Clean(output.AuditSummary)", view, StringComparison.Ordinal);
        Assert.Contains("Output type:", view, StringComparison.Ordinal);
        Assert.Contains("Publication:", view, StringComparison.Ordinal);
        Assert.Contains("Compatibility: @output.CompatibilitySummary", view, StringComparison.Ordinal);
        Assert.Contains("Lineage: @output.LineageSummary", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.ProgressionOutcomes.Take(3)", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.RuleEnvironmentDiff", view, StringComparison.Ordinal);
        Assert.Contains("Rules before", view, StringComparison.Ordinal);
        Assert.Contains("Rules after", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Rule diff before", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Rule diff after", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.CrewFitSummary", view, StringComparison.Ordinal);
        Assert.Contains("Crew fit", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.ConditionalStateSummary", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.ConditionalStateLines.Take(3)", view, StringComparison.Ordinal);
        Assert.Contains("Current conditions", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Conditional state", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.SourceHintSummary", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.SourceHintLines.Take(3)", view, StringComparison.Ordinal);
        Assert.Contains("Helpful notes:", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Linked hints:", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.BuildSurfaceSummary", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.BuildSurfaceLines.Take(4)", view, StringComparison.Ordinal);
        Assert.Contains("Builder view:", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Build surface:", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.ExchangeParitySummary", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.ExchangeParityLines.Take(5)", view, StringComparison.Ordinal);
        Assert.Contains("Import/export fit:", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Exchange parity:", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.PortabilityPillarSummary", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.PortabilityPillarLines.Take(5)", view, StringComparison.Ordinal);
        Assert.Contains("Portability:", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Portability pillar:", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.PlannerCoverageLines.Take(5)", view, StringComparison.Ordinal);
        Assert.Contains("handoff.PlannerCoverageLines.Take(2)", view, StringComparison.Ordinal);
        Assert.Contains("Planner coverage", view, StringComparison.Ordinal);
        Assert.Contains("handoff.SourceHintLines.Take(2)", view, StringComparison.Ordinal);
        Assert.Contains("Note:", view, StringComparison.Ordinal);
        Assert.Contains("handoff.RuleEnvironmentDiff.Summary", view, StringComparison.Ordinal);
        Assert.Contains("More next steps:", view, StringComparison.Ordinal);
        Assert.DoesNotContain("More outputs:", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountWorkspaceTravelModeRendersCacheFreshnessCues()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("selectedWorkspaceServerPlane.GmOperations.Status", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceServerPlane.GmOperations.Summary", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceServerPlane.GmOperations.AccountBackboneSummary", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceServerPlane.GmOperations.LaneCues.Count > 0", view, StringComparison.Ordinal);
        Assert.Contains("gmLane.Lane.Replace('_', ' ')", view, StringComparison.Ordinal);
        Assert.Contains("gmLane.SignalCount", view, StringComparison.Ordinal);
        Assert.Contains("gmLane.Summary", view, StringComparison.Ordinal);
        Assert.Contains("GM operations", view, StringComparison.Ordinal);
        Assert.Contains("Account support", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceServerPlane.TravelMode.CacheFreshnessSummary", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceServerPlane.TravelMode.OfflineActionabilitySummary", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceServerPlane.TravelMode.OfflineLaneCues.Count > 0", view, StringComparison.Ordinal);
        Assert.Contains("laneCue.Lane.Replace('_', ' ')", view, StringComparison.Ordinal);
        Assert.Contains("laneCue.SignalCount", view, StringComparison.Ordinal);
        Assert.Contains("laneCue.Summary", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceServerPlane.TravelMode.FreshCacheDeviceCount", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceServerPlane.TravelMode.StaleCacheDeviceCount", view, StringComparison.Ordinal);
        Assert.Contains("HumanizeStatus(device.Status, \"Status\")", view, StringComparison.Ordinal);
        Assert.Contains("Cache freshness", view, StringComparison.Ordinal);
        Assert.Contains("Offline actionability", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountRecapShelfRendersCompatibilityAndLineageCues()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Compatibility: @PublicText(item.CompatibilitySummary)", view, StringComparison.Ordinal);
        Assert.Contains("Lineage: @PublicText(item.LineageSummary)", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountSettingsRendersNeutralWhatsappSupportControls()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("WhatsApp number", view, StringComparison.Ordinal);
        Assert.DoesNotContain("WhatsApp number for AI support only", view, StringComparison.Ordinal);
        Assert.DoesNotContain("AI support channels", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Ask the grounded support assistant", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Executive Assistant linked to channel", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Ask Rule Ghost", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Rule Ghost summarizes", view, StringComparison.Ordinal);
        Assert.Contains("Rules help", view, StringComparison.Ordinal);
        Assert.Contains("asking what questions you have", view, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("purpose: \"ai_support_only\"", view, StringComparison.Ordinal);
        Assert.DoesNotContain("aiSupportOpeningPrompt", view, StringComparison.Ordinal);
        Assert.Contains("Link WhatsApp", view, StringComparison.Ordinal);
        Assert.Contains("Table Pulse updates", view, StringComparison.Ordinal);
        Assert.Contains("Black Ledger involvement", view, StringComparison.Ordinal);
        Assert.Contains("whatsappNotificationsEnabled", view, StringComparison.Ordinal);
    }
}
