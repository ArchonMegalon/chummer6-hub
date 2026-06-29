using Xunit;

namespace Chummer.Tests;

public sealed class AccountBuildLabHandoffViewTests
{
    [Fact]
    public void AccountNavigationUsesRealDestinationsInsteadOfFakeSettingsSurfaces()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string hubViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Hub.cshtml");
        string sectionViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Section.cshtml");
        string supportViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Support.cshtml");
        string controller = File.ReadAllText(controllerPath);
        string view = File.ReadAllText(viewPath);
        string hubView = File.ReadAllText(hubViewPath);
        string sectionView = File.ReadAllText(sectionViewPath);
        string supportView = File.ReadAllText(supportViewPath);

        Assert.Contains("string.Equals(selectedSection, \"profile\", StringComparison.OrdinalIgnoreCase)", controller, StringComparison.Ordinal);
        Assert.Contains("return View(", controller, StringComparison.Ordinal);
        Assert.Contains("\"~/Views/Accounts/Hub.cshtml\"", controller, StringComparison.Ordinal);
        Assert.Contains("\"~/Views/Accounts/Section.cshtml\"", controller, StringComparison.Ordinal);
        Assert.Contains("\"~/Views/Accounts/Support.cshtml\"", controller, StringComparison.Ordinal);
        Assert.Contains("ShouldShowMinimalAccountSection", controller, StringComparison.Ordinal);
        Assert.Contains("ShouldShowMinimalSupportSection", controller, StringComparison.Ordinal);
        Assert.Contains("return Redirect(\"/account\")", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("IsBillingSectionAlias", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("section.Trim().ToLowerInvariant() is \"billing\" or \"settings\" or \"advanced\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("return Redirect(\"/account/billing\")", controller, StringComparison.Ordinal);
        Assert.Contains("return Redirect($\"/account/access?localCoProcessor={Uri.EscapeDataString(normalizedProfile)}\")", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("/account/advanced?localCoProcessor=", controller, StringComparison.Ordinal);
        Assert.Contains("new SectionLinkViewModel(\"access\", \"Installs\"", controller, StringComparison.Ordinal);
        Assert.Contains("new SectionLinkViewModel(\"work\", \"Roster\", \"/account/roster\"", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/campaigns/{workspaceId}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("\"roster\" => \"work\"", controller, StringComparison.Ordinal);
        Assert.Contains("\"work\" => \"/account/roster\"", controller, StringComparison.Ordinal);
        Assert.Contains("$\"/account/campaigns/{Uri.EscapeDataString(workspaceId)}\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("new SectionLinkViewModel(\"profile\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("new SectionLinkViewModel(\"advanced\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("new SectionLinkViewModel(\"settings\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("claim ticket", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("group lane", controller, StringComparison.Ordinal);

        Assert.DoesNotContain("\"settings\" => \"Billing\"", view, StringComparison.Ordinal);
        Assert.Contains("Downloads, runners, support, and membership.", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Move between installs, support, billing, participation, and campaigns.", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Move between profile, installs, support, billing, participation, and campaigns.", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Move between profile, access, support, and work", view, StringComparison.Ordinal);
        Assert.DoesNotContain("\"work\" => \"Work\"", view, StringComparison.Ordinal);
        Assert.DoesNotContain("\"settings\" => \"Supporter and billing.\"", view, StringComparison.Ordinal);
        Assert.DoesNotContain("\"advanced\" => \"Billing\"", view, StringComparison.Ordinal);
        Assert.DoesNotContain("\"advanced\" => \"Advanced account details\"", view, StringComparison.Ordinal);
        Assert.Contains("Open campaigns on the web", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Open work on the web", view, StringComparison.Ordinal);
        Assert.DoesNotContain("showSettingsSection", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Help and policy", view, StringComparison.Ordinal);
        Assert.Contains("var showChannelsSection = showProfileSection;", view, StringComparison.Ordinal);
        Assert.Contains("var showParticipationSettings = showParticipationPage;", view, StringComparison.Ordinal);
        Assert.Contains("@Model.Heading", hubView, StringComparison.Ordinal);
        Assert.Contains("@Model.Summary", hubView, StringComparison.Ordinal);
        Assert.Contains("@foreach (var card in Model.Cards)", hubView, StringComparison.Ordinal);
        Assert.Contains("@card.Title", hubView, StringComparison.Ordinal);
        Assert.Contains("@card.PrimaryLabel", hubView, StringComparison.Ordinal);
        Assert.Contains("@Model.Eyebrow", sectionView, StringComparison.Ordinal);
        Assert.Contains("@Model.Heading", sectionView, StringComparison.Ordinal);
        Assert.Contains("@foreach (var card in Model.Cards)", sectionView, StringComparison.Ordinal);
        Assert.Contains("<p class=\"eyebrow\">Support</p>", supportView, StringComparison.Ordinal);
        Assert.Contains("<h1>Support</h1>", supportView, StringComparison.Ordinal);
        Assert.Contains("Discord for normal questions. Private help for installs, crashes, and account issues.", supportView, StringComparison.Ordinal);
        Assert.Contains("Use Discord for normal questions and quick feedback.", supportView, StringComparison.Ordinal);
        Assert.Contains("Private cases stay attached to this account.", supportView, StringComparison.Ordinal);
        Assert.Contains("supportCaseForm", supportView, StringComparison.Ordinal);
        Assert.Contains("<summary>Quick help</summary>", supportView, StringComparison.Ordinal);
        Assert.Contains("supportAssistantForm", supportView, StringComparison.Ordinal);
        Assert.Contains("ruleGhostForm", supportView, StringComparison.Ordinal);
        Assert.DoesNotContain("account-linked follow-up", supportView, StringComparison.Ordinal);
        Assert.DoesNotContain("Account · @Model.Eyebrow", sectionView, StringComparison.Ordinal);
        Assert.DoesNotContain("Account · Support", supportView, StringComparison.Ordinal);
        Assert.DoesNotContain("Signed in as @Model.User.DisplayName", supportView, StringComparison.Ordinal);
        Assert.DoesNotContain("@Model.User.DisplayName", supportView, StringComparison.Ordinal);
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
        Assert.DoesNotContain("<span>Current update</span>", view, StringComparison.Ordinal);
        Assert.DoesNotContain("<span>Current area</span>", view, StringComparison.Ordinal);
        Assert.DoesNotContain("@selectedWorkspaceServerPlane.RestoreReceiptStatus.LeadReceiptId", view, StringComparison.Ordinal);
        Assert.DoesNotContain("@selectedWorkspaceServerPlane.RestoreReceiptStatus.LeadSubjectId", view, StringComparison.Ordinal);
        Assert.DoesNotContain("@surface.Status.LeadReceiptId", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountWorkSurfaceUsesSimplerFollowUpAndRecapCopy()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("<summary>Runboard</summary>", view, StringComparison.Ordinal);
        Assert.Contains("<summary>GM tools and travel</summary>", view, StringComparison.Ordinal);
        Assert.Contains("<summary>Aftermath and recaps</summary>", view, StringComparison.Ordinal);
        Assert.Contains("Open next session note", view, StringComparison.Ordinal);
        Assert.Contains("Open build details for", view, StringComparison.Ordinal);
        Assert.Contains("Create recap or replay", view, StringComparison.Ordinal);
        Assert.Contains("Recaps and replays become available once this campaign has a live run.", view, StringComparison.Ordinal);
        Assert.Contains("Recent aftermath recap packages and replay outputs", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Runboard continuity", view, StringComparison.Ordinal);
        Assert.DoesNotContain("GM prep and travel", view, StringComparison.Ordinal);
        Assert.DoesNotContain("<summary>Aftermath and recap</summary>", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Open carry-forward", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Open build path for", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Generate aftermath or replay package", view, StringComparison.Ordinal);
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

    [Fact]
    public void AccountSettingsRendersBlackLedgerStreamOptIn()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Settings.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("blackLedgerNewsEmail", view, StringComparison.Ordinal);
        Assert.Contains("Black Ledger mobile stream", view, StringComparison.Ordinal);
        Assert.Contains("blackLedgerNewsEmail: document.getElementById(\"blackLedgerNewsEmail\").checked", view, StringComparison.Ordinal);
    }
}
