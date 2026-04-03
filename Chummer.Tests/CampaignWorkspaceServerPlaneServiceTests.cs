using Chummer.Campaign.Contracts;
using System.Reflection;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Community;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignWorkspaceServerPlaneServiceTests
{
    [Fact]
    public void PrepLibraryQueryTokensSplitAndNormalizePunctuation()
    {
        IReadOnlyList<string> tokens = InvokeBuildTokens("  Opposition, season-control / audit  ");

        Assert.Contains("opposition", tokens);
        Assert.Contains("season", tokens);
        Assert.Contains("control", tokens);
        Assert.Contains("audit", tokens);
    }

    [Fact]
    public void PrepLibraryQueryMatchingRequiresAllTokensAcrossSearchSurfaces()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "opposition:demo",
            Kind: "opposition_packet",
            Title: "Neon Cradle opposition packet",
            Summary: "Active pressure stays tied to the current season lane.",
            BindingSummary: "Bound to the return lane and audit receipts.",
            Reusable: true,
            SearchTerms: ["opposition", "season", "roster"],
            EvidenceLines: ["GM audit line: roster movement receipt captured."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));

        IReadOnlyList<string> positiveTokens = InvokeBuildTokens("opposition audit");
        IReadOnlyList<string> negativeTokens = InvokeBuildTokens("opposition matrix");

        Assert.True(InvokeMatches(packet, positiveTokens));
        Assert.False(InvokeMatches(packet, negativeTokens));
    }

    [Fact]
    public void PrepLibraryIncludesRosterMovementPacketWhenRosterTransfersExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("roster", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("movement", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void PrepLibraryIncludesAftermathPacketWhenAftermathPackagesExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("aftermath", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("downtime", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void ScenePacketIncludesSceneAndObjectiveLabelsWhenSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSceneSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();
        RunProjection leadRun = Assert.Single(workspace.Runs);

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "scene_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("dockyard checkpoint label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("hostile extraction team label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ScenePacketSummaryFallsBackWhenSceneSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSceneSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();
        RunProjection leadRun = Assert.Single(workspace.Runs);

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "scene_packet", StringComparison.Ordinal));
        Assert.Contains("compiled from the shared campaign return lane", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ScenePacketBindingFallsBackWhenRunAndSceneTitlesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseRunAndSceneTitles();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();
        RunProjection leadRun = Assert.Single(workspace.Runs);

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "scene_packet", StringComparison.Ordinal));
        Assert.Contains("Bound to active run / Active scene on sr6-mainline.", packet.BindingSummary, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("Active scene scene packet", packet.Title);
    }

    [Fact]
    public void AftermathPacketFallsBackToChangeSignalsWhenPackagesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathChangeSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("aftermath", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("change signals", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void AftermathPacketIncludesSignalLabelsWhenSignalSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketFallsBackToSignalLabelsWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketIncludesKindFallbackWhenSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathSignalKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime_brief", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketIncludesRecapKindFallbackWhenRecapSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathRecapKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime_brief", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketFallsBackToRecapLabelWhenRecapKindIsSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathRecapLabelOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime recap label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketKeepsRecapKindFallbackWhenPackageEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathRecapKindsAndVerbosePackage();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime_brief", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketKeepsRecapKindFallbackWhenRecapEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathRecapKindsAndVerboseRecapEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime_brief", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLibraryIncludesEventControlPacketWhenCarryForwardAndChangePacketsExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControls();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("season", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("control", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("return", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void PrepLibraryIncludesCampaignReturnPacketWhenDiaryAndRelationshipSignalsExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnSignals();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("diary", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("contacts", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("heat", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("return", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToAftermathSignalsWhenDiaryAndRelationshipSignalsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("aftermath", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("aftermath", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToRelationshipChangeSignalsWhenConsequenceReceiptsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRelationshipChangeSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("return", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("relationship", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketCountsRelationshipSignalsFromChangePackets()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRelationshipChangeSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToReturnSignalVariantsWhenOtherReceiptsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnVariantSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("return", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("return window", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToDiarySignalVariantsWhenRecapAndConsequencesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignDiaryVariantSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("diary", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("diary", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToRelationshipConsequenceVariantsWhenCoreKindsAreNotUsed()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnRelationshipConsequenceVariantsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("return", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("fixer pressure", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToRelationshipSignalVariantsWithoutExplicitMutationVerbs()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnRelationshipSignalVariantsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("return", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("fixer obligation", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketIncludesRelationshipConsequenceReceiptEvidenceWhenConsequenceSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnRelationshipReceiptEvidenceOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("support case", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToRelationshipConsequenceLabelsWhenConsequenceKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseRelationshipConsequenceKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure consequence label", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain("and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToRelationshipConsequenceLabelsWhenFalloutSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseRelationshipConsequenceFalloutLabelOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact fallout consequence label", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain("and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromRelationshipMentionsWithoutMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseRelationshipMentionOnlyConsequenceEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromBacklogMentionsWithoutRecapIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithBacklogMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketIncludesChangePacketLabelsWhenChangeSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("return window label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("fixer obligation label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToSignalLabelsWhenChangeSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("return window label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact pressure label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains("1 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketCountsRelationshipSignalsWhenRelationshipTokensAreSplitAcrossFields()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnSplitRelationshipSignalTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact lane label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains("relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketIncludesCarryForwardLabelWhenCarryForwardSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnCarryForwardLabelOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("return lane label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("reopen from governed return lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketIncludesKindFallbacksWhenLabelsAndSummariesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("campaign_return_window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat_pressure_lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketKeepsKindFallbackEvidenceWhenCarryForwardIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnKindsAndVerboseCarryForward();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("campaign_return_window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat_pressure_lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketKeepsRelationshipKindFallbackWhenDiaryEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnKindsAndVerboseDiaryEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("campaign_return_window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat_pressure_lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketIncludesRecapKindFallbackWhenRecapSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnRecapKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("session_recap", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToRecapLabelWhenRecapKindIsSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnRecapLabelOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("session diary recap label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLibraryIncludesPrepLaunchPacketWhenGovernedPrepLaunchReceiptsExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("prep", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("launch", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("audit", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void PrepLibraryIncludesTravelPrefetchPacketWhenPrefetchReceiptsExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("travel", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("prefetch", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("device", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void PrepLaunchPacketIncludesFallbackEvidenceWhenLaunchReceiptsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseOpsReceipts();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();
        RunProjection leadRun = Assert.Single(workspace.Runs);

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("scene_packet for run-1 / scene-1", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPrefetchPacketIncludesFallbackEvidenceWhenReceiptSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseOpsReceipts();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel_cache on ios (mobile/preview)", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesOpsFallbackEvidenceWhenReceiptSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseOpsReceipts();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();
        RunProjection leadRun = Assert.Single(workspace.Runs);

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("scene_packet for run-1 / scene-1", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel_cache on ios (mobile/preview)", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPrefetchPacketFallsBackToChangeSignalsWhenReceiptsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchChangeSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("travel", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("prefetch", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("change packets", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void TravelPrefetchPacketIncludesSignalLabelsWhenSignalSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel prefetch label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPrefetchPacketFallsBackToSignalLabelsWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel prefetch label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPrefetchPacketFallsBackToSplitSignalTokensWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchSparseSignalKindsAndSplitTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel staging label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPrefetchPacketIncludesKindFallbackWhenSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel_prefetch", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPrefetchPacketKeepsKindFallbackWhenReceiptEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchKindsAndVerboseReceiptEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel_prefetch", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPacketIncludesFallbackEvidenceWhenRestoreSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        WorkspaceRestoreProjection restore = BuildRestoreWithTravelPacketSparseEvidence();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel_cache on linux (offline/preview)", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("campaign_recap_bundle", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("campaign_approved", StringComparison.OrdinalIgnoreCase));
        Assert.Contains("recap", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketIncludesOpsReceiptsWhenPrepLaunchAndTravelPrefetchExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("operations", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("event-control receipt", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("install-local secrets remain local", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToSignalFamilyVariants()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlSignalVariants();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("prep launch", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel prefetch", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("crew handoff", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToRelationshipChangeSignalsWhenConsequenceReceiptsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlRelationshipSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("relationship", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToRelationshipConsequenceVariantsWhenCoreKindsAreNotUsed()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlRelationshipConsequenceVariantsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("2 event-control receipt(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("faction pressure", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToRelationshipSignalVariantsWithoutExplicitMutationVerbs()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlRelationshipSignalVariantsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("fixer obligation", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesRelationshipConsequenceReceiptEvidenceWhenConsequenceSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlRelationshipReceiptEvidenceOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("support case", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesSignalLabelsWhenSignalSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season operation label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact pressure label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToRelationshipConsequenceLabelsWhenFalloutSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseRelationshipConsequenceFalloutLabelOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact fallout consequence label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromRelationshipMentionsWithoutMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseRelationshipMentionOnlyConsequenceEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketFallsBackToSignalLabelsWhenEventSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season operation label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact pressure label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToSplitRelationshipSignalTokensWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlSplitRelationshipSignalTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season operation label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact lane label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketActivatesFromRelationshipSplitSignalTokensWhenOtherFamiliesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlRelationshipOnlySplitSignalTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact lane label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("status changed after downtime", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesKindFallbackWhenEventSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlSignalKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season_operation_checkpoint", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("event_window_shift", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesCarryForwardLabelWhenCarryForwardSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlCarryForwardLabelOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("event control label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("open season controls before next launch", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromUnrelatedCarryForwardNotesOnly()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithNonEventCarryForwardOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromContinuitySignalsOnly()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlContinuitySignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromAftermathSignalsOnly()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlAftermathSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void RosterMovementPacketDoesNotActivateFromContinuityHandoffSignalsWithoutRosterIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlContinuitySignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void RosterMovementPacketDoesNotActivateFromCrewMentionsWithoutMovementSemantics()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCrewMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromCrewMentionsWithoutMovementSemantics()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCrewMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromCooperationMentionsWithoutEventSemantics()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCooperationMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromContactlessMentionsWithoutRelationshipIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactlessStatusMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromNonThreateningMentionsWithoutOppositionIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithNonThreateningMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void OppositionPacketDoesNotActivateFromNonThreateningMentionsWithoutOppositionIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithNonThreateningMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromCampaignReturnWindowSignalsOnly()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnVariantSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromCarryForwardWindowLanguageOnly()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlCarryForwardWindowOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketActivatesFromRosterCarryForwardSignalsWhenOtherFamiliesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterEventCarryForwardOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("roster return carry-forward", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("resolve roster assignment", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketActivatesFromPrepLaunchCarryForwardSplitTokensWhenOtherFamiliesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchCarryForwardSplitTokensOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("prep lane note", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("launch the queued packet", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketActivatesFromTravelPrefetchCarryForwardSplitTokensWhenOtherFamiliesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchCarryForwardSplitTokensOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel lane note", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("prefetch sealed offline kit", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketSummaryFallsBackToConsequenceKindsWhenConsequenceLabelsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlConsequenceKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("heat_pressure_lane", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("faction_status_window", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketIncludesConsequenceKindFallbackInEvidenceWhenConsequenceSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlConsequenceKindsSparseOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat_pressure_lane", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("faction_status_window", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToRelationshipConsequenceLabelsWhenConsequenceKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseRelationshipConsequenceKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure consequence label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains("consequence signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketKeepsKindFallbackEvidenceWhenCarryForwardIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlKindsAndVerboseCarryForward();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season_operation_checkpoint", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat_pressure_lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketKeepsConsequenceKindFallbackWhenEventEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlKindsAndVerboseEventEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat_pressure_lane", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season board lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToExplicitEventSignalVariantsWhenOtherFamiliesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlExplicitEventSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("season", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("event window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season operation", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToRunPressureSignalsWhenReceiptsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlRunPressureSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("season", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("event window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("event control board", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesRosterTransferReceiptsWhenChangePacketsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlRosterTransfersOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("roster", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season operations roster", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToOppositionSignalVariantsWhenEventFamiliesLag()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlOppositionSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("opposition", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opposition command board", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketFallsBackToOppositionChangeSignalsWhenConsequencesAndRunPressureAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionChangeSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("opposition", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opposition", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("threat", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketIncludesSignalLabelsWhenSignalSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opposition window label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("threat lane label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketFallsBackToSignalLabelsWhenOppositionSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opposition window label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("threat lane label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketSummaryFallsBackToKindsWhenSignalLabelsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("opposition_window", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("threat_window", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void OppositionPacketIncludesConsequenceKindFallbackInEvidenceWhenConsequenceSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionConsequenceKindsSparseOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opposition_window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("threat_window", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketKeepsConsequenceKindFallbackWhenOppositionEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionConsequenceKindsSparseAndVerboseSignals();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("threat_window", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketExcludesNonOppositionConsequencesFromSummaryAndEvidence()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithMixedOppositionAndRelationshipConsequences();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("threat_window", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain("heat_pressure_lane", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(packet.EvidenceLines, line => line.Contains("heat pressure", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketFallsBackToConsequenceLabelWhenConsequenceKindIsSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionConsequenceLabelOnlyAndSparseKind();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opposition window label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketFallsBackToRunPressureWhenConsequencesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRunPressureSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("opposition", packet.PacketId, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("hostile", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("high", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("run pressure", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RosterMovementPacketFallsBackToChangeAndCarryForwardSignalsWhenTransfersAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("roster", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("crew", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("roster-change packets", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RosterMovementPacketIncludesChangeAndCarryForwardLabelsWhenSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("crew assignment label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("roster return label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void RosterMovementPacketFallsBackToSignalLabelsWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("crew assignment label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("roster return label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void RosterMovementPacketIncludesKindFallbackWhenSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterSignalKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("roster_assignment", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void RosterMovementPacketIncludesTransferIdentityFallbackWhenTransferSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterTransfersSparseOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("Ghostline transfer Neon Cradle -> Season Ops", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesRosterTransferIdentityFallbackWhenTransferSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterTransfersSparseOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("Ghostline transfer Neon Cradle -> Season Ops", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToRosterSignalLabelsWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("crew assignment label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void RosterMovementPacketKeepsSignalKindFallbackWhenTransferEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterTransfersSparseAndVerboseOpsEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("roster_assignment", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("Ghostline transfer Neon Cradle -> Season Ops", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketKeepsRosterTransferIdentityWhenOpsEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterTransfersSparseAndVerboseOpsEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("Ghostline transfer Neon Cradle -> Season Ops", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLaunchPacketFallsBackToChangeSignalsWhenLaunchReceiptsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchChangeSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("prep", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("launch", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("change packets", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void PrepLaunchPacketIncludesSignalLabelsWhenLaunchSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("scene prep label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLaunchPacketFallsBackToSignalLabelsWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("scene prep launch label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLaunchPacketFallsBackToSplitSignalTokensWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchSparseSignalKindsAndSplitTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("scene prep label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLaunchPacketIncludesKindFallbackWhenSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("prep_launch", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLaunchPacketKeepsKindFallbackWhenLaunchEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchKindsAndVerboseLaunchEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("prep_launch", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season prep lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketFallsBackToCarryForwardAndContinuityChangeSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuitySignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains("continuity", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("continuity signal", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("carry-forward", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketIncludesSignalLabelsWhenSignalSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuitySignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("continuity carry-forward label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("return handoff label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketFallsBackToSignalLabelsWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuitySparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("continuity carry-forward label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("return handoff label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketIncludesKindFallbackWhenSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuitySignalKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("next_session_carry_forward", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketIncludesRecapKindFallbackWhenRecapSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuityRecapKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("session_recap", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketKeepsRecapKindFallbackWhenCarryForwardIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuityRecapKindsAndVerboseCarryForward();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("session_recap", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketKeepsContinuityKindFallbackWhenRecapEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuityKindsAndVerboseRecapEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("next_session_carry_forward", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("Session recap lane", StringComparison.OrdinalIgnoreCase));
    }

    private static IReadOnlyList<string> InvokeBuildTokens(string? queryText)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildPrepLibraryQueryTokens", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildPrepLibraryQueryTokens was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<string>>(method.Invoke(null, [queryText]));
    }

    private static bool InvokeMatches(GovernedPrepPacketSummary packet, IReadOnlyList<string> queryTokens)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("MatchesPrepLibraryQuery", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("MatchesPrepLibraryQuery was not found.");

        return Assert.IsType<bool>(method.Invoke(null, [packet, queryTokens]));
    }

    private static IReadOnlyList<GovernedPrepPacketSummary> InvokeBuildPrepPackets(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore)
        => InvokeBuildPrepPackets(workspace, restore, null);

    private static IReadOnlyList<GovernedPrepPacketSummary> InvokeBuildPrepPackets(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore,
        RunProjection? leadRun)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildPrepPackets", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildPrepPackets was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<GovernedPrepPacketSummary>>(method.Invoke(null, [workspace, restore, leadRun]));
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterAndAftermath()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        RosterTransferProjection transfer = new(
            TransferId: "transfer-1",
            DossierId: "dossier-1",
            RunnerHandle: "Ghostline",
            PreviousOwnerUserId: "user-a",
            CurrentOwnerUserId: "user-b",
            SourceGroupId: "group-a",
            SourceGroupName: "Night Shift",
            SourceCampaignId: "campaign-a",
            SourceCampaignName: "Neon Cradle",
            SourceCrewId: "crew-a",
            SourceCrewName: "Wardens",
            TargetGroupId: "group-b",
            TargetGroupName: "Aftermath Desk",
            TargetCampaignId: "campaign-b",
            TargetCampaignName: "Season Ops",
            TargetCrewId: "crew-b",
            TargetCrewName: "Organizers",
            InitiatedByUserId: "gm-1",
            Summary: "Moved Ghostline into season operations roster lane.",
            AuditLines: ["Roster movement receipt captured for season operations."],
            Receipts: [],
            TransferredAtUtc: now);

        AftermathRecapPackageProjection aftermath = new(
            PackageId: "package-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            RunId: "run-1",
            RunTitle: "Dockyard pressure test",
            PackageKind: "downtime_brief",
            Title: "Downtime brief",
            Summary: "Downtime consequences and return cues are published for next session.",
            ArtifactId: "artifact-1",
            EvidenceLines: ["Heat posture and contact fallout captured."],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: now);

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            RosterTransfers: [transfer],
            AftermathPackages: [aftermath]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControls()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        var carryForward = new NextSessionCarryForwardProjection(
            CarryForwardId: "carry-1",
            Label: "Next session carry-forward",
            Summary: "Season event controls and return windows are staged for the next run.",
            ReturnSummary: "Return window remains governed from workspace state.",
            NextSafeAction: "Open event controls before launching the next prep lane.",
            EvidenceLines: ["Carry-forward receipt captured from the latest continuity lane."],
            UpdatedAtUtc: now.AddMinutes(5));

        var changePacket = new WorkspaceChangePacketProjection(
            PacketId: "packet-1",
            Kind: "prep_launch",
            Label: "GM prep launch",
            Summary: "Event board packet launched for season operations.",
            UpdatedAtUtc: now.AddMinutes(3));

        var consequence = new CampaignConsequenceProjection(
            ConsequenceId: "consequence-1",
            Kind: "heat",
            Label: "Heat posture",
            State: "elevated",
            Summary: "Event pressure remains elevated until the return loop is confirmed.",
            EvidenceLines: ["Heat review line captured for event control."],
            Receipts:
            [
                new CampaignConsequenceReceipt(
                    ReceiptId: "objective-1",
                    SourceKind: "objective",
                    Summary: "Open pressure objective still active.")
            ],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [changePacket],
            Consequences: [consequence],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnSignals()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "session_recap",
            Label: "After action diary",
            Summary: "Diary recap records downtime outcomes and next-session obligations.");
        WorkspaceChangePacketProjection changePacket = new(
            PacketId: "packet-1",
            Kind: "next_session_carry_forward",
            Label: "Carry-forward packet",
            Summary: "Carry-forward packet keeps diary and contact follow-through on one lane.",
            UpdatedAtUtc: now.AddMinutes(3));
        CampaignConsequenceProjection contactConsequence = new(
            ConsequenceId: "consequence-1",
            Kind: "contact",
            Label: "Fixer pressure",
            State: "active",
            Summary: "Contact obligations remain active in the return loop.",
            EvidenceLines: ["Contact diary update captured from the latest recap."],
            Receipts:
            [
                new CampaignConsequenceReceipt(
                    ReceiptId: "receipt-1",
                    SourceKind: "contact",
                    Summary: "Contact relationship changed after downtime.")
            ],
            UpdatedAtUtc: now.AddMinutes(4));
        CampaignConsequenceProjection heatConsequence = new(
            ConsequenceId: "consequence-2",
            Kind: "heat",
            Label: "Street heat",
            State: "elevated",
            Summary: "Operational heat stays elevated until the next session opens.",
            EvidenceLines: ["Heat trend remains tied to the same return lane."],
            Receipts:
            [
                new CampaignConsequenceReceipt(
                    ReceiptId: "receipt-2",
                    SourceKind: "objective",
                    Summary: "Open objective keeps pressure elevated.")
            ],
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [changePacket],
            Consequences: [contactConsequence, heatConsequence]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        AftermathRecapPackageProjection aftermath = new(
            PackageId: "package-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            RunId: "run-1",
            RunTitle: "Dockyard pressure test",
            PackageKind: "downtime_brief",
            Title: "Aftermath downtime brief",
            Summary: "Aftermath summary captures downtime obligations for return.",
            ArtifactId: "artifact-1",
            EvidenceLines: ["Aftermath heat and contact fallout captured for return."],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: now.AddMinutes(6));

        WorkspaceChangePacketProjection aftermathChange = new(
            PacketId: "packet-1",
            Kind: "aftermath",
            Label: "Aftermath change packet",
            Summary: "Aftermath change remains governed on the return lane.",
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [aftermathChange],
            Consequences: [],
            AftermathPackages: [aftermath]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathChangeSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection aftermathChange = new(
            PacketId: "packet-1",
            Kind: "downtime_brief",
            Label: "Downtime signal",
            Summary: "Downtime change packet keeps aftermath continuity visible before package receipts land.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [aftermathChange],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection aftermathChange = new(
            PacketId: "packet-1",
            Kind: "downtime_brief",
            Label: "Downtime label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [aftermathChange],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathSparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection aftermathChange = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Downtime label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [aftermathChange],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathSignalKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection aftermathChange = new(
            PacketId: "packet-1",
            Kind: "downtime_brief",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [aftermathChange],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathRecapKindsOnly()
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "downtime_brief",
            Label: "",
            Summary: "");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathRecapLabelOnly()
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "",
            Label: "Downtime recap label",
            Summary: "");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathRecapKindsAndVerbosePackage()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "downtime_brief",
            Label: "",
            Summary: "");
        AftermathRecapPackageProjection package = new(
            PackageId: "package-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            RunId: "run-1",
            RunTitle: "Dockyard Pressure Test",
            PackageKind: "aftermath",
            Title: "Verbose aftermath package title line",
            Summary: "Verbose aftermath package summary line",
            ArtifactId: "artifact-1",
            EvidenceLines:
            [
                "Verbose aftermath evidence line one.",
                "Verbose aftermath evidence line two."
            ],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: now);

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            AftermathPackages: [package]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathRecapKindsAndVerboseRecapEvidence()
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recapOne = new(
            ProjectionId: "recap-1",
            Kind: "downtime_brief",
            Label: "",
            Summary: "Verbose downtime recap lane summary line one.");
        PublicationSafeProjection recapTwo = new(
            ProjectionId: "recap-2",
            Kind: "downtime_brief",
            Label: "",
            Summary: "Verbose downtime recap lane summary line two.");
        PublicationSafeProjection recapThree = new(
            ProjectionId: "recap-3",
            Kind: "downtime_brief",
            Label: "",
            Summary: "Verbose downtime recap lane summary line three.");
        PublicationSafeProjection recapFour = new(
            ProjectionId: "recap-4",
            Kind: "downtime_brief",
            Label: "",
            Summary: "Verbose downtime recap lane summary line four.");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recapOne, recapTwo, recapThree, recapFour],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRelationshipChangeSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection relationshipChange = new(
            PacketId: "packet-1",
            Kind: "heat_relationship_shift",
            Label: "Relationship change",
            Summary: "Relationship update keeps contact and heat posture on the return lane before consequence receipts land.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [relationshipChange],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        GovernedPrepLaunchProjection prepLaunch = new(
            LaunchId: "launch-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            PacketId: "scene:workspace-1",
            PacketKind: "scene_packet",
            PacketTitle: "Dockyard scene packet",
            TargetRunId: "run-1",
            TargetRunTitle: "Dockyard pressure test",
            TargetSceneId: "scene-1",
            TargetSceneTitle: "Dockyard checkpoint",
            InitiatedByUserId: "gm-1",
            Summary: "GM launched governed scene packet for the next table run.",
            AuditLines: ["Prep launch receipt captured on the account audit lane."],
            LaunchedAtUtc: now.AddMinutes(6));

        TravelPrefetchReceiptProjection prefetch = new(
            ReceiptId: "prefetch-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            InstallationId: "install-1",
            DeviceRole: "travel_cache",
            Platform: "ios",
            HeadId: "mobile",
            Channel: "preview",
            PrefetchSummary: "Travel prefetch staged for the next session return loop.",
            InventoryLines: ["Staged dossier, campaign, and prep packet inventory for travel mode."],
            Boundaries: ["Install-local secrets remain local and are never synced."],
            InitiatedByUserId: "gm-1",
            StagedAtUtc: now.AddMinutes(7));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            PrepLaunches: [prepLaunch],
            TravelPrefetches: [prefetch]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithSparseOpsReceipts()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Season operation checkpoint",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        GovernedPrepLaunchProjection prepLaunch = new(
            LaunchId: "launch-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            PacketId: "scene:workspace-1",
            PacketKind: "scene_packet",
            PacketTitle: "",
            TargetRunId: "run-1",
            TargetRunTitle: "",
            TargetSceneId: "scene-1",
            TargetSceneTitle: "",
            InitiatedByUserId: "gm-1",
            Summary: "",
            AuditLines: [],
            LaunchedAtUtc: now.AddMinutes(6));

        TravelPrefetchReceiptProjection prefetch = new(
            ReceiptId: "prefetch-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            InstallationId: "install-1",
            DeviceRole: "travel_cache",
            Platform: "ios",
            HeadId: "mobile",
            Channel: "preview",
            PrefetchSummary: "",
            InventoryLines: [],
            Boundaries: [],
            InitiatedByUserId: "gm-1",
            StagedAtUtc: now.AddMinutes(7));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            PrepLaunches: [prepLaunch],
            TravelPrefetches: [prefetch]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnVariantSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection returnVariant = new(
            PacketId: "packet-1",
            Kind: "campaign_return_window",
            Label: "Return window variant",
            Summary: "Return window variant packet keeps next-session reopen cues governed.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [returnVariant],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignDiaryVariantSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection diaryVariant = new(
            PacketId: "packet-1",
            Kind: "journal_diary_update",
            Label: "Diary variant update",
            Summary: "Diary update keeps downtime follow-through visible before recap receipts land.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [diaryVariant],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnRelationshipConsequenceVariantsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure",
            State: "elevated",
            Summary: "Heat pressure remains on the return lane while diary receipts catch up.",
            EvidenceLines: ["Heat pressure stayed governed for return-loop reopen."],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));
        CampaignConsequenceProjection contactVariant = new(
            ConsequenceId: "consequence-2",
            Kind: "contact_obligation_lane",
            Label: "Fixer pressure",
            State: "active",
            Summary: "Contact obligation remains active in the same return continuity lane.",
            EvidenceLines: ["Fixer pressure remains linked to next-session return posture."],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [heatVariant, contactVariant],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnRelationshipSignalVariantsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection heatPressureLane = new(
            PacketId: "packet-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure lane",
            Summary: "Heat pressure remains attached to the campaign return lane before consequence receipts land.",
            UpdatedAtUtc: now.AddMinutes(3));
        WorkspaceChangePacketProjection contactObligationLane = new(
            PacketId: "packet-2",
            Kind: "contact_obligation_lane",
            Label: "Fixer obligation lane",
            Summary: "Fixer obligation remains attached to the same governed return lane.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [heatPressureLane, contactObligationLane],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnRelationshipReceiptEvidenceOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceReceipt receipt = new(
            ReceiptId: "receipt-1",
            SourceKind: "support_case",
            Summary: "Support case receipt confirms heat pressure remains governed for return.");
        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure",
            State: "elevated",
            Summary: "",
            EvidenceLines: [],
            Receipts: [receipt],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [heatVariant],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithSparseRelationshipConsequenceKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceProjection consequence = new(
            ConsequenceId: "consequence-1",
            Kind: "",
            Label: "Heat pressure consequence label",
            State: "elevated",
            Summary: "Status shifted during downtime follow-through.",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [consequence],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithSparseRelationshipConsequenceFalloutLabelOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceProjection consequence = new(
            ConsequenceId: "consequence-1",
            Kind: "",
            Label: "Contact fallout consequence label",
            State: "elevated",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [consequence],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithSparseRelationshipMentionOnlyConsequenceEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceProjection consequence = new(
            ConsequenceId: "consequence-1",
            Kind: "",
            Label: "",
            State: "steady",
            Summary: "",
            EvidenceLines: ["Contact directory note captured for table reference."],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [consequence],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithBacklogMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection backlogSignal = new(
            PacketId: "packet-backlog-1",
            Kind: "status_note",
            Label: "Campaign backlog review",
            Summary: "Backlog status remains stable while triage work is scheduled.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-backlog-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [backlogSignal],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection returnWindow = new(
            PacketId: "packet-1",
            Kind: "campaign_return_window",
            Label: "Return window label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection contactPressure = new(
            PacketId: "packet-2",
            Kind: "contact_obligation_lane",
            Label: "Fixer obligation label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [returnWindow, contactPressure],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnCarryForwardLabelOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Return lane label",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "Reopen from governed return lane.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnSparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection returnWindow = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Return window label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection contactPressure = new(
            PacketId: "packet-2",
            Kind: "",
            Label: "Contact pressure label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [returnWindow, contactPressure],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnSplitRelationshipSignalTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection returnWindow = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Return window label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection splitRelationship = new(
            PacketId: "packet-2",
            Kind: "",
            Label: "Contact lane label",
            Summary: "Status changed after downtime reconciliation.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [returnWindow, splitRelationship],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection returnWindow = new(
            PacketId: "packet-1",
            Kind: "campaign_return_window",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(1));
        CampaignConsequenceProjection heatLane = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "",
            State: "",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [returnWindow],
            Consequences: [heatLane],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnKindsAndVerboseCarryForward()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection returnWindow = new(
            PacketId: "packet-1",
            Kind: "campaign_return_window",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(1));
        CampaignConsequenceProjection heatLane = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "",
            State: "elevated",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Return lane priority",
            Summary: "Carry-forward summary keeps reopen actions staged.",
            ReturnSummary: "Return summary keeps the session handoff governed.",
            NextSafeAction: "Reopen the campaign from the governed return lane.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [returnWindow],
            Consequences: [heatLane],
            NextSessionCarryForward: carryForward,
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnKindsAndVerboseDiaryEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection returnWindow = new(
            PacketId: "packet-1",
            Kind: "campaign_return_window",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(1));
        CampaignConsequenceProjection heatLane = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "",
            State: "",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));
        PublicationSafeProjection recapA = new(
            ProjectionId: "recap-1",
            Kind: "session_recap",
            Label: "Session recap lane A",
            Summary: "Session recap evidence line A remains verbose while return packets hydrate.");
        PublicationSafeProjection recapB = new(
            ProjectionId: "recap-2",
            Kind: "session_recap",
            Label: "Session recap lane B",
            Summary: "Session recap evidence line B remains verbose while return packets hydrate.");
        PublicationSafeProjection recapC = new(
            ProjectionId: "recap-3",
            Kind: "session_recap",
            Label: "Session recap lane C",
            Summary: "Session recap evidence line C remains verbose while return packets hydrate.");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recapA, recapB, recapC],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [returnWindow],
            Consequences: [heatLane],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnRecapKindsOnly()
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "session_recap",
            Label: "",
            Summary: "");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnRecapLabelOnly()
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "",
            Label: "Session diary recap label",
            Summary: "");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchChangeSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection prefetchChange = new(
            PacketId: "packet-1",
            Kind: "travel_prefetch",
            Label: "Travel prefetch signal",
            Summary: "Travel prefetch change packet staged bounded offline inventory for the next return loop.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [prefetchChange],
            Consequences: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection prefetchChange = new(
            PacketId: "packet-1",
            Kind: "travel_prefetch",
            Label: "Travel prefetch label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prefetchChange],
            Consequences: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection prefetchChange = new(
            PacketId: "packet-1",
            Kind: "travel_prefetch",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prefetchChange],
            Consequences: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchSparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection prefetchChange = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Travel prefetch label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prefetchChange],
            Consequences: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchSparseSignalKindsAndSplitTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection prefetchChange = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Travel staging label",
            Summary: "Prefetch ready for travel cache.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prefetchChange],
            Consequences: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchKindsAndVerboseReceiptEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection prefetchChange = new(
            PacketId: "packet-1",
            Kind: "travel_prefetch",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(8));

        TravelPrefetchReceiptProjection receiptOne = new(
            ReceiptId: "prefetch-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            InstallationId: "install-1",
            DeviceRole: "travel_cache",
            Platform: "ios",
            HeadId: "mobile",
            Channel: "preview",
            PrefetchSummary: "Verbose prefetch summary line one.",
            InventoryLines: [],
            Boundaries: [],
            InitiatedByUserId: "gm-1",
            StagedAtUtc: now.AddMinutes(4));
        TravelPrefetchReceiptProjection receiptTwo = new(
            ReceiptId: "prefetch-2",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            InstallationId: "install-2",
            DeviceRole: "travel_cache",
            Platform: "android",
            HeadId: "mobile",
            Channel: "preview",
            PrefetchSummary: "Verbose prefetch summary line two.",
            InventoryLines: [],
            Boundaries: [],
            InitiatedByUserId: "gm-1",
            StagedAtUtc: now.AddMinutes(5));
        TravelPrefetchReceiptProjection receiptThree = new(
            ReceiptId: "prefetch-3",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            InstallationId: "install-3",
            DeviceRole: "travel_cache",
            Platform: "windows",
            HeadId: "desktop",
            Channel: "stable",
            PrefetchSummary: "Verbose prefetch summary line three.",
            InventoryLines: [],
            Boundaries: [],
            InitiatedByUserId: "gm-1",
            StagedAtUtc: now.AddMinutes(6));
        TravelPrefetchReceiptProjection receiptFour = new(
            ReceiptId: "prefetch-4",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            InstallationId: "install-4",
            DeviceRole: "travel_cache",
            Platform: "linux",
            HeadId: "desktop",
            Channel: "stable",
            PrefetchSummary: "Verbose prefetch summary line four.",
            InventoryLines: [],
            Boundaries: [],
            InitiatedByUserId: "gm-1",
            StagedAtUtc: now.AddMinutes(7));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prefetchChange],
            Consequences: [],
            TravelPrefetches: [receiptOne, receiptTwo, receiptThree, receiptFour]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRunPressureSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Hostile extraction team",
            Status: "open",
            Pressure: "high",
            Summary: "An extraction team remains active and pushes immediate opposition risk.",
            UpdatedAtUtc: now.AddMinutes(2));

        SceneProjection scene = new(
            SceneId: "scene-1",
            RunId: "run-1",
            Title: "Dockyard checkpoint",
            Revision: "r3",
            Status: "active",
            Summary: "Opposition remains active around the dockyard perimeter.",
            UpdatedAtUtc: now.AddMinutes(3));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains under hostile pressure.",
            ActiveSceneId: "scene-1",
            Objectives: [objective],
            Scenes: [scene],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithSceneSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Hostile extraction team label",
            Status: "open",
            Pressure: "high",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        SceneProjection scene = new(
            SceneId: "scene-1",
            RunId: "run-1",
            Title: "Dockyard checkpoint label",
            Revision: "r3",
            Status: "active",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "",
            ActiveSceneId: "scene-1",
            Objectives: [objective],
            Scenes: [scene],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithSparseRunAndSceneTitles()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        SceneProjection scene = new(
            SceneId: "scene-1",
            RunId: "run-1",
            Title: "",
            Revision: "r3",
            Status: "active",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "",
            Status: "active",
            Summary: "",
            ActiveSceneId: "scene-1",
            Objectives: [],
            Scenes: [scene],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlSignalVariants()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection prepLaunchVariant = new(
            PacketId: "packet-1",
            Kind: "prep_packet_launch",
            Label: "Prep launch variant",
            Summary: "Prep launch variant packet remains attached to event controls.",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection travelPrefetchVariant = new(
            PacketId: "packet-2",
            Kind: "travel_prefetch_request",
            Label: "Travel prefetch variant",
            Summary: "Travel prefetch variant packet remains attached to event controls.",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection rosterVariant = new(
            PacketId: "packet-3",
            Kind: "crew_handoff",
            Label: "Roster movement variant",
            Summary: "Crew handoff variant packet remains attached to season operations.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [prepLaunchVariant, travelPrefetchVariant, rosterVariant],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlRelationshipSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection relationshipChange = new(
            PacketId: "packet-1",
            Kind: "heat_update",
            Label: "Heat relationship update",
            Summary: "Relationship update keeps heat posture attached to event controls before consequence receipts land.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [relationshipChange],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlRelationshipConsequenceVariantsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure",
            State: "elevated",
            Summary: "Heat pressure remains attached to event-control governance.",
            EvidenceLines: ["Heat pressure review captured for season controls."],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));
        CampaignConsequenceProjection factionVariant = new(
            ConsequenceId: "consequence-2",
            Kind: "faction_pressure_lane",
            Label: "Faction pressure",
            State: "contested",
            Summary: "Faction pressure remains attached to event-control governance.",
            EvidenceLines: ["Faction pressure review captured for season controls."],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [heatVariant, factionVariant],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlRelationshipSignalVariantsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection heatPressureLane = new(
            PacketId: "packet-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure lane",
            Summary: "Heat pressure remains attached to event controls while consequence receipts catch up.",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection contactObligationLane = new(
            PacketId: "packet-2",
            Kind: "contact_obligation_lane",
            Label: "Fixer obligation lane",
            Summary: "Fixer obligation remains attached to event controls on the same governed lane.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [heatPressureLane, contactObligationLane],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlRelationshipReceiptEvidenceOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceReceipt receipt = new(
            ReceiptId: "receipt-1",
            SourceKind: "support_case",
            Summary: "Support case receipt confirms heat pressure remains attached to event control.");
        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure",
            State: "elevated",
            Summary: "",
            EvidenceLines: [],
            Receipts: [receipt],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [heatVariant],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection seasonOperation = new(
            PacketId: "packet-1",
            Kind: "season_operation_checkpoint",
            Label: "Season operation label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection relationshipPressure = new(
            PacketId: "packet-2",
            Kind: "contact_pressure_lane",
            Label: "Contact pressure label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [seasonOperation, relationshipPressure],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlSignalKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection seasonOperation = new(
            PacketId: "packet-1",
            Kind: "season_operation_checkpoint",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection eventWindowShift = new(
            PacketId: "packet-2",
            Kind: "event_window_shift",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [seasonOperation, eventWindowShift],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlSparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection seasonOperation = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Season operation label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection relationshipPressure = new(
            PacketId: "packet-2",
            Kind: "",
            Label: "Contact pressure label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [seasonOperation, relationshipPressure],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlSplitRelationshipSignalTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection seasonOperation = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Season operation label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection splitRelationship = new(
            PacketId: "packet-2",
            Kind: "",
            Label: "Contact lane label",
            Summary: "Status changed after organizer checkpoint reconciliation.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [seasonOperation, splitRelationship],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlRelationshipOnlySplitSignalTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection splitRelationship = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Contact lane label",
            Summary: "Status changed after downtime.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [splitRelationship],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlCarryForwardLabelOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Event control label",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "Open season controls before next launch.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlConsequenceKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "",
            State: "elevated",
            Summary: "Heat pressure stays attached to event controls.",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));
        CampaignConsequenceProjection factionVariant = new(
            ConsequenceId: "consequence-2",
            Kind: "faction_status_window",
            Label: "",
            State: "active",
            Summary: "Faction pressure stays attached to event controls.",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [heatVariant, factionVariant],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithNonEventCarryForwardOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Budget review note",
            Summary: "Audit receipt reconciliation is pending for publication notes.",
            ReturnSummary: "Document refresh queue remains open for operator follow-through.",
            NextSafeAction: "Review publication checklist before posting the update.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlCarryForwardWindowOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Return window note",
            Summary: "Window remains open for continuity review.",
            ReturnSummary: "Shared return window stays visible to the table.",
            NextSafeAction: "Review the return lane window before reopening play.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlContinuitySignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection continuitySignal = new(
            PacketId: "packet-1",
            Kind: "next_session_carry_forward",
            Label: "Continuity carry-forward signal",
            Summary: "Continuity handoff remains attached to the return lane.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [continuitySignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlAftermathSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection aftermathSignal = new(
            PacketId: "packet-1",
            Kind: "downtime_brief",
            Label: "Downtime brief signal",
            Summary: "Aftermath remains visible for return-loop continuity.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [aftermathSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCrewMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection crewMentionSignal = new(
            PacketId: "packet-crew-1",
            Kind: "continuity_update",
            Label: "Crew morale pulse",
            Summary: "Crew morale remains stable after downtime review.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-crew-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [crewMentionSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCooperationMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection cooperationSignal = new(
            PacketId: "packet-cooperation-1",
            Kind: "continuity_update",
            Label: "Community cooperation pulse",
            Summary: "Cooperation remains stable for continuity follow-through.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-cooperation-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [cooperationSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContactlessStatusMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection contactlessSignal = new(
            PacketId: "packet-contactless-1",
            Kind: "continuity_update",
            Label: "Contactless kiosk status",
            Summary: "Contactless queue status remains stable during recap.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-contactless-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [contactlessSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithNonThreateningMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection nonThreateningSignal = new(
            PacketId: "packet-nonthreatening-1",
            Kind: "continuity_update",
            Label: "Nonthreatening continuity pulse",
            Summary: "Table posture remains nonthreatening during continuity review.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-nonthreatening-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [nonThreateningSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterEventCarryForwardOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Roster return carry-forward",
            Summary: "",
            ReturnSummary: "Crew assignment posture stays attached to one governed lane.",
            NextSafeAction: "Resolve roster assignment before next event launch.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchCarryForwardSplitTokensOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Prep lane note",
            Summary: "Operator follow-through remains on campaign truth.",
            ReturnSummary: "",
            NextSafeAction: "Launch the queued packet before table return.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchCarryForwardSplitTokensOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Travel lane note",
            Summary: "Device handoff stays governed for the same campaign lane.",
            ReturnSummary: "",
            NextSafeAction: "Prefetch sealed offline kit before departure.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlConsequenceKindsSparseOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "",
            State: "elevated",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));
        CampaignConsequenceProjection factionVariant = new(
            ConsequenceId: "consequence-2",
            Kind: "faction_status_window",
            Label: "",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [heatVariant, factionVariant],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlKindsAndVerboseCarryForward()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection seasonOperation = new(
            PacketId: "packet-1",
            Kind: "season_operation_checkpoint",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "",
            State: "elevated",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Event control lane",
            Summary: "Carry-forward keeps the event board attached to return.",
            ReturnSummary: "Season controls reopen from one governed lane.",
            NextSafeAction: "Reopen event controls before launch.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [seasonOperation],
            Consequences: [heatVariant],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlKindsAndVerboseEventEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection eventSignalA = new(
            PacketId: "event-1",
            Kind: "season_operation_checkpoint",
            Label: "Season board lane A",
            Summary: "Season operation control timeline is saturated with verbose lane details for packet A.",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection eventSignalB = new(
            PacketId: "event-2",
            Kind: "event_window_shift",
            Label: "Season board lane B",
            Summary: "Event window control timeline is saturated with verbose lane details for packet B.",
            UpdatedAtUtc: now.AddMinutes(3));
        WorkspaceChangePacketProjection eventSignalC = new(
            PacketId: "event-3",
            Kind: "operation_checkpoint",
            Label: "Season board lane C",
            Summary: "Operation checkpoint control timeline is saturated with verbose lane details for packet C.",
            UpdatedAtUtc: now.AddMinutes(4));
        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [eventSignalA, eventSignalB, eventSignalC],
            Consequences: [heatVariant],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlExplicitEventSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection eventWindowShift = new(
            PacketId: "packet-1",
            Kind: "event_window_shift",
            Label: "Event window shift",
            Summary: "Event window shift keeps timeline governance visible while derivative receipt families catch up.",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection seasonOpsCheckpoint = new(
            PacketId: "packet-2",
            Kind: "season_operation_checkpoint",
            Label: "Season operation checkpoint",
            Summary: "Season operation checkpoint preserves operator timeline control on the same governed lane.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [eventWindowShift, seasonOpsCheckpoint],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Roster handoff review",
            Status: "open",
            Pressure: "medium",
            Summary: "Crew assignment handoff still needs organizer approval before session launch.",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection rosterChange = new(
            PacketId: "packet-1",
            Kind: "roster_assignment",
            Label: "Crew assignment update",
            Summary: "Roster assignment moved a runner into season operations coverage.",
            UpdatedAtUtc: now.AddMinutes(4));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Roster return carry-forward",
            Summary: "Roster handoff decisions stay governed before the next session opens.",
            ReturnSummary: "Crew assignment posture remains attached to the return lane.",
            NextSafeAction: "Resolve roster assignment before launching event prep.",
            EvidenceLines: ["Carry-forward receipt captured for roster return."],
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [rosterChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Roster handoff label",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection rosterChange = new(
            PacketId: "packet-1",
            Kind: "roster_assignment",
            Label: "Crew assignment label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Roster return label",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [rosterChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterSignalKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Roster handoff label",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection rosterChange = new(
            PacketId: "packet-1",
            Kind: "roster_assignment",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [rosterChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterSparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Roster handoff label",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection rosterChange = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Crew assignment label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Roster return label",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [rosterChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterTransfersSparseOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        RosterTransferProjection transfer = new(
            TransferId: "transfer-1",
            DossierId: "dossier-1",
            RunnerHandle: "Ghostline",
            PreviousOwnerUserId: "user-a",
            CurrentOwnerUserId: "user-b",
            SourceGroupId: "group-a",
            SourceGroupName: "Night Shift",
            SourceCampaignId: "campaign-a",
            SourceCampaignName: "Neon Cradle",
            SourceCrewId: "crew-a",
            SourceCrewName: "Wardens",
            TargetGroupId: "group-b",
            TargetGroupName: "Aftermath Desk",
            TargetCampaignId: "campaign-b",
            TargetCampaignName: "Season Ops",
            TargetCrewId: "crew-b",
            TargetCrewName: "Season Operations Roster",
            InitiatedByUserId: "gm-1",
            Summary: "",
            AuditLines: [],
            Receipts: [],
            TransferredAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            RosterTransfers: [transfer],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterTransfersSparseAndVerboseOpsEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        RosterTransferProjection transfer = new(
            TransferId: "transfer-1",
            DossierId: "dossier-1",
            RunnerHandle: "Ghostline",
            PreviousOwnerUserId: "user-a",
            CurrentOwnerUserId: "user-b",
            SourceGroupId: "group-a",
            SourceGroupName: "Night Shift",
            SourceCampaignId: "campaign-a",
            SourceCampaignName: "Neon Cradle",
            SourceCrewId: "crew-a",
            SourceCrewName: "Wardens",
            TargetGroupId: "group-b",
            TargetGroupName: "Aftermath Desk",
            TargetCampaignId: "campaign-b",
            TargetCampaignName: "Season Ops",
            TargetCrewId: "crew-b",
            TargetCrewName: "Season Operations Roster",
            InitiatedByUserId: "gm-1",
            Summary: "",
            AuditLines:
            [
                "Transfer receipt line A includes verbose season-operation context for launch prep and roster pressure.",
                "Transfer receipt line B includes verbose staffing context for event windows and checkpoint planning.",
                "Transfer receipt line C includes verbose accountability context for operator lane governance."
            ],
            Receipts: [],
            TransferredAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection rosterSignal = new(
            PacketId: "packet-roster",
            Kind: "roster_assignment",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));
        WorkspaceChangePacketProjection eventSignalA = new(
            PacketId: "packet-event-a",
            Kind: "season_operation_checkpoint",
            Label: "Season board lane A",
            Summary: "Season operation control timeline is saturated with verbose lane details for packet A.",
            UpdatedAtUtc: now.AddMinutes(5));
        WorkspaceChangePacketProjection eventSignalB = new(
            PacketId: "packet-event-b",
            Kind: "event_window_shift",
            Label: "Season board lane B",
            Summary: "Event window control timeline is saturated with verbose lane details for packet B.",
            UpdatedAtUtc: now.AddMinutes(6));
        WorkspaceChangePacketProjection eventSignalC = new(
            PacketId: "packet-event-c",
            Kind: "operation_checkpoint",
            Label: "Season board lane C",
            Summary: "Operation checkpoint control timeline is saturated with verbose lane details for packet C.",
            UpdatedAtUtc: now.AddMinutes(7));

        CampaignConsequenceProjection consequence = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure lane",
            State: "active",
            Summary: "Heat pressure remains attached to event-control governance.",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(8));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [rosterSignal, eventSignalA, eventSignalB, eventSignalC],
            Consequences: [consequence],
            RosterTransfers: [transfer],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlRunPressureSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Season event window lock",
            Status: "open",
            Pressure: "high",
            Summary: "Event window remains open until organizer controls are reconciled.",
            UpdatedAtUtc: now.AddMinutes(2));

        SceneProjection scene = new(
            SceneId: "scene-1",
            RunId: "run-1",
            Title: "Season-control checkpoint",
            Revision: "r4",
            Status: "active",
            Summary: "Event control board stays active while the return lane is validated.",
            UpdatedAtUtc: now.AddMinutes(3));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active under season-control pressure.",
            ActiveSceneId: "scene-1",
            Objectives: [objective],
            Scenes: [scene],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlRosterTransfersOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        RosterTransferProjection transfer = new(
            TransferId: "transfer-1",
            DossierId: "dossier-1",
            RunnerHandle: "Ghostline",
            PreviousOwnerUserId: "user-a",
            CurrentOwnerUserId: "user-b",
            SourceGroupId: "group-a",
            SourceGroupName: "Night Shift",
            SourceCampaignId: "campaign-a",
            SourceCampaignName: "Neon Cradle",
            SourceCrewId: "crew-a",
            SourceCrewName: "Wardens",
            TargetGroupId: "group-b",
            TargetGroupName: "Aftermath Desk",
            TargetCampaignId: "campaign-b",
            TargetCampaignName: "Season Ops",
            TargetCrewId: "crew-b",
            TargetCrewName: "Season Operations Roster",
            InitiatedByUserId: "gm-1",
            Summary: "Moved Ghostline into season operations roster lane.",
            AuditLines: ["Roster movement receipt captured for season operations."],
            Receipts: [],
            TransferredAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [],
            RosterTransfers: [transfer],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlOppositionSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection oppositionVariant = new(
            PacketId: "packet-1",
            Kind: "opposition_window_shift",
            Label: "Opposition window shift",
            Summary: "Opposition command board remains active while event-control receipts catch up.",
            UpdatedAtUtc: now.AddMinutes(2));

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Hostile response window",
            Status: "open",
            Pressure: "high",
            Summary: "Hostile pressure remains active until the organizer event board is reopened.",
            UpdatedAtUtc: now.AddMinutes(3));

        SceneProjection scene = new(
            SceneId: "scene-1",
            RunId: "run-1",
            Title: "Dockyard opposition board",
            Revision: "r6",
            Status: "active",
            Summary: "Opposition command board remains active for the next season-control checkpoint.",
            UpdatedAtUtc: now.AddMinutes(4));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active under hostile pressure.",
            ActiveSceneId: "scene-1",
            Objectives: [objective],
            Scenes: [scene],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [oppositionVariant],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionChangeSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection oppositionWindow = new(
            PacketId: "packet-1",
            Kind: "opposition_window_shift",
            Label: "Opposition window shift",
            Summary: "Opposition window shift keeps threat posture visible before consequence or run-pressure summaries arrive.",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection threatLane = new(
            PacketId: "packet-2",
            Kind: "threat_control_delta",
            Label: "Threat control delta",
            Summary: "Threat control delta remains attached to the governed opposition lane.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [oppositionWindow, threatLane],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection oppositionWindow = new(
            PacketId: "packet-1",
            Kind: "opposition_window_shift",
            Label: "Opposition window label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection threatLane = new(
            PacketId: "packet-2",
            Kind: "threat_control_delta",
            Label: "Threat lane label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [oppositionWindow, threatLane],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection oppositionWindow = new(
            PacketId: "packet-1",
            Kind: "opposition_window",
            Label: "",
            Summary: "Opposition window remains active.",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection threatWindow = new(
            PacketId: "packet-2",
            Kind: "threat_window",
            Label: "",
            Summary: "Threat window remains active.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [oppositionWindow, threatWindow],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionSparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection oppositionWindow = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Opposition window label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection threatLane = new(
            PacketId: "packet-2",
            Kind: "",
            Label: "Threat lane label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [oppositionWindow, threatLane],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionConsequenceKindsSparseOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        CampaignConsequenceProjection oppositionWindow = new(
            ConsequenceId: "consequence-1",
            Kind: "opposition_window",
            Label: "",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(1));
        CampaignConsequenceProjection threatWindow = new(
            ConsequenceId: "consequence-2",
            Kind: "threat_window",
            Label: "",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [oppositionWindow, threatWindow]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionConsequenceKindsSparseAndVerboseSignals()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection oppositionWindowSignal = new(
            PacketId: "packet-1",
            Kind: "opposition_window_shift",
            Label: "Opposition window label",
            Summary: "Opposition window summary line remains verbose in evidence.",
            UpdatedAtUtc: now.AddMinutes(3));
        WorkspaceChangePacketProjection threatWindowSignal = new(
            PacketId: "packet-2",
            Kind: "threat_window_shift",
            Label: "Threat window label",
            Summary: "Threat window summary line remains verbose in evidence.",
            UpdatedAtUtc: now.AddMinutes(4));

        CampaignConsequenceProjection sparseConsequence = new(
            ConsequenceId: "consequence-1",
            Kind: "threat_window",
            Label: "",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [oppositionWindowSignal, threatWindowSignal],
            Consequences: [sparseConsequence]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithMixedOppositionAndRelationshipConsequences()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        CampaignConsequenceProjection opposition = new(
            ConsequenceId: "consequence-1",
            Kind: "threat_window",
            Label: "",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));
        CampaignConsequenceProjection relationship = new(
            ConsequenceId: "consequence-2",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure lane",
            State: "active",
            Summary: "Heat pressure remains attached to event-control governance.",
            EvidenceLines: ["Heat pressure receipt line"],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [opposition, relationship]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionConsequenceLabelOnlyAndSparseKind()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        CampaignConsequenceProjection sparseConsequence = new(
            ConsequenceId: "consequence-1",
            Kind: "",
            Label: "Opposition window label",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [sparseConsequence]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchChangeSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Prep launch validation",
            Status: "open",
            Pressure: "medium",
            Summary: "Prep launch evidence is pending final receipt ingestion.",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection prepLaunchChange = new(
            PacketId: "packet-1",
            Kind: "prep_launch",
            Label: "Scene prep launch",
            Summary: "Prep launch packet was staged on the governed campaign lane.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [prepLaunchChange],
            Consequences: [],
            PrepLaunches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Prep launch validation",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection prepLaunchChange = new(
            PacketId: "packet-1",
            Kind: "prep_launch",
            Label: "Scene prep label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prepLaunchChange],
            Consequences: [],
            PrepLaunches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Prep launch validation",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection prepLaunchChange = new(
            PacketId: "packet-1",
            Kind: "prep_launch",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prepLaunchChange],
            Consequences: [],
            PrepLaunches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchSparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Prep launch validation",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection prepLaunchChange = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Scene prep launch label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prepLaunchChange],
            Consequences: [],
            PrepLaunches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchSparseSignalKindsAndSplitTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Prep launch validation",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection prepLaunchChange = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Scene prep label",
            Summary: "Launch window pending final check.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prepLaunchChange],
            Consequences: [],
            PrepLaunches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchKindsAndVerboseLaunchEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Prep launch validation",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection prepLaunchChange = new(
            PacketId: "packet-1",
            Kind: "prep_launch",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        GovernedPrepLaunchProjection launchA = new(
            LaunchId: "launch-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            PacketId: "scene:workspace-1",
            PacketKind: "scene_packet",
            PacketTitle: "Season prep lane A",
            TargetRunId: "run-1",
            TargetRunTitle: "Dockyard pressure test",
            TargetSceneId: "scene-a",
            TargetSceneTitle: "Pier ingress",
            InitiatedByUserId: "gm-1",
            Summary: "Season prep lane A remains richly documented for launch audit detail.",
            AuditLines: ["Launch lane A audit details are fully populated."],
            LaunchedAtUtc: now.AddMinutes(8));
        GovernedPrepLaunchProjection launchB = new(
            LaunchId: "launch-2",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            PacketId: "scene:workspace-2",
            PacketKind: "scene_packet",
            PacketTitle: "Season prep lane B",
            TargetRunId: "run-1",
            TargetRunTitle: "Dockyard pressure test",
            TargetSceneId: "scene-b",
            TargetSceneTitle: "Signal tunnel",
            InitiatedByUserId: "gm-1",
            Summary: "Season prep lane B remains richly documented for launch audit detail.",
            AuditLines: ["Launch lane B audit details are fully populated."],
            LaunchedAtUtc: now.AddMinutes(7));
        GovernedPrepLaunchProjection launchC = new(
            LaunchId: "launch-3",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            PacketId: "scene:workspace-3",
            PacketKind: "scene_packet",
            PacketTitle: "Season prep lane C",
            TargetRunId: "run-1",
            TargetRunTitle: "Dockyard pressure test",
            TargetSceneId: "scene-c",
            TargetSceneTitle: "Grid relay",
            InitiatedByUserId: "gm-1",
            Summary: "Season prep lane C remains richly documented for launch audit detail.",
            AuditLines: ["Launch lane C audit details are fully populated."],
            LaunchedAtUtc: now.AddMinutes(6));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prepLaunchChange],
            Consequences: [],
            PrepLaunches: [launchA, launchB, launchC]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuitySignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection continuityChange = new(
            PacketId: "packet-1",
            Kind: "next_session_carry_forward",
            Label: "Continuity carry-forward packet",
            Summary: "Continuity carry-forward remains governed on the shared campaign lane.",
            UpdatedAtUtc: now.AddMinutes(3));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Continuity return lane",
            Summary: "Carry-forward continuity signal remains active for the next session.",
            ReturnSummary: "Return lane continuity is ready for shared reopen.",
            NextSafeAction: "Review carry-forward continuity before starting play.",
            EvidenceLines: ["Carry-forward continuity receipt captured."],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [continuityChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuitySignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection continuityChange = new(
            PacketId: "packet-1",
            Kind: "next_session_carry_forward",
            Label: "Continuity carry-forward label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Return handoff label",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [continuityChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuitySignalKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection continuityChange = new(
            PacketId: "packet-1",
            Kind: "next_session_carry_forward",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [continuityChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuitySparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection continuityChange = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Continuity carry-forward label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Return handoff label",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [continuityChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuityRecapKindsOnly()
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "session_recap",
            Label: "",
            Summary: "");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: null);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuityRecapKindsAndVerboseCarryForward()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "session_recap",
            Label: "",
            Summary: "");
        WorkspaceChangePacketProjection continuityChange = new(
            PacketId: "packet-1",
            Kind: "next_session_carry_forward",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Continuity return lane",
            Summary: "Carry-forward continuity remains active for next session.",
            ReturnSummary: "Continuity handoff remains attached to governed return.",
            NextSafeAction: "Review continuity handoff before table start.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [continuityChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuityKindsAndVerboseRecapEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        PublicationSafeProjection recapA = new(
            ProjectionId: "recap-a",
            Kind: "session_recap",
            Label: "Session recap lane A",
            Summary: "Session recap evidence line A remains verbose while continuity projections hydrate.");
        PublicationSafeProjection recapB = new(
            ProjectionId: "recap-b",
            Kind: "session_recap",
            Label: "Session recap lane B",
            Summary: "Session recap evidence line B remains verbose while continuity projections hydrate.");
        PublicationSafeProjection recapC = new(
            ProjectionId: "recap-c",
            Kind: "session_recap",
            Label: "Session recap lane C",
            Summary: "Session recap evidence line C remains verbose while continuity projections hydrate.");
        WorkspaceChangePacketProjection continuityChange = new(
            PacketId: "packet-1",
            Kind: "next_session_carry_forward",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recapA, recapB, recapC],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [continuityChange],
            Consequences: [],
            NextSessionCarryForward: null);
    }

    private static WorkspaceRestoreProjection BuildRestoreWithTravelPacketSparseEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef sparseRuleEnvironment = new(
            EnvironmentId: "env-restore-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "",
            ApprovalState: "campaign_approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ClaimedDeviceRestoreProjection device = new(
            InstallationId: "install-1",
            DeviceRole: "travel_cache",
            Platform: "linux",
            HeadId: "offline",
            Channel: "preview",
            HostLabel: null,
            RestoreSummary: "");

        RestoreArtifactProjection artifact = new(
            ArtifactId: "artifact-1",
            Label: "",
            Kind: "campaign_recap_bundle",
            Summary: "");

        return new WorkspaceRestoreProjection(
            RestoreId: "restore-sparse-travel-1",
            UserId: "user-1",
            RecentDossiers: [],
            RecentCampaigns: [],
            RecentRuleEnvironments: [sparseRuleEnvironment],
            RecentArtifacts: [artifact],
            Entitlements: [],
            ClaimedDevices: [device],
            ConflictSummaries: [],
            LocalOnlyNotes: [],
            GeneratedAtUtc: now);
    }

    private static WorkspaceRestoreProjection BuildEmptyRestore()
        => new(
            RestoreId: "restore-1",
            UserId: "user-1",
            RecentDossiers: [],
            RecentCampaigns: [],
            RecentRuleEnvironments: [],
            RecentArtifacts: [],
            Entitlements: [],
            ClaimedDevices: [],
            ConflictSummaries: [],
            LocalOnlyNotes: [],
            GeneratedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));
}
