using Chummer.Run.Api.Services.KarmaForge;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class KarmaForgeDiscoveryServiceTests
{
    [Fact]
    public void Submit_NormalizesCampaignScopedDemandIntoChummerOwnedPackets()
    {
        string tempRoot = CreateTempRoot("karma-forge-normalize");

        try
        {
            IConfiguration configuration = CreateConfiguration(tempRoot);
            KarmaForgeStore store = new(configuration, NullLogger<KarmaForgeStore>.Instance);
            KarmaForgeDiscoveryService service = new(store);

            KarmaForgeSubmissionProjection submission = service.Submit(
                new KarmaForgeSubmissionRequest
                {
                    TrackKey = "gm_house_rule_track",
                    RespondentRole = "GM",
                    Edition = "SR6",
                    TableType = "home_campaign",
                    RuleCategory = "gear_availability",
                    Severity = "blocks_play",
                    FeedbackPrompt = "We need a campaign unlock lane for restricted gear.",
                    UserWordsSummary = "I want to mark gear unavailable until our campaign unlocks it.",
                    CurrentWorkaround = "We track unlocks in Discord and review every sheet manually.",
                    InterpretedNeedSummary = "Campaign-scoped availability overlay with player-visible receipts and build-impact preview.",
                    ImpactNotes = "Players need to see the change before they join and we need rollback if the unlock changes mid-campaign.",
                    ShareabilityNotes = "We would share this as a reusable pack with other tables.",
                    ReplyEmail = "gm@example.invalid",
                    FollowUpAllowed = true,
                    QuoteAllowed = true,
                    ConsentAccepted = true
                },
                subjectId: "subject-kf-1",
                subjectDisplayName: "Switch");

            Assert.Equal("packet_normalized", submission.IntakeStatus);
            Assert.Equal("candidate_for_lunacal_followup", submission.QueueStatus);
            Assert.Equal("campaign_overlay_candidate", submission.Candidate.CandidateDecision);
            Assert.Equal("FacePop -> Deftform -> Icanpreneur", submission.Packet.Source.CanonicalLane);
            Assert.Contains("availability", submission.Packet.AffectedDomains, StringComparer.Ordinal);
            Assert.Contains("CampaignOverlayPackage", submission.Packet.LikelyChummerObjects, StringComparer.Ordinal);
            Assert.True(submission.Packet.TrustRequirements.PlayerVisibleBeforeJoin);
            Assert.True(submission.Packet.PortabilityRequirements.PackageFingerprintRequired);
            Assert.Equal("KARMA_FORGE", submission.Packet.Classification.ProposedRoute);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void Submit_PersistsAndReloadsStoreState()
    {
        string tempRoot = CreateTempRoot("karma-forge-store");

        try
        {
            IConfiguration configuration = CreateConfiguration(tempRoot);
            KarmaForgeStore store = new(configuration, NullLogger<KarmaForgeStore>.Instance);
            KarmaForgeDiscoveryService service = new(store);

            KarmaForgeSubmissionProjection created = service.Submit(
                new KarmaForgeSubmissionRequest
                {
                    TrackKey = "chummer5a_veteran_migration_track",
                    RespondentRole = "Chummer5a veteran",
                    Edition = "SR5 to SR6",
                    TableType = "migration_workbench",
                    RuleCategory = "migration",
                    Severity = "session_friction",
                    FeedbackPrompt = "Our legacy import still drops amend behavior.",
                    UserWordsSummary = "Custom data from Chummer5a does not survive the import.",
                    CurrentWorkaround = "We hand-edit exports after every import.",
                    ShareabilityNotes = "This matters to every migration pass.",
                    ReplyEmail = "veteran@example.invalid",
                    FollowUpAllowed = false,
                    QuoteAllowed = false,
                    ConsentAccepted = true
                },
                subjectId: null,
                subjectDisplayName: null);

            KarmaForgeStore reloadedStore = new(configuration, NullLogger<KarmaForgeStore>.Instance);
            KarmaForgeDiscoveryService reloadedService = new(reloadedStore);
            KarmaForgeSubmissionProjection? persisted = reloadedService.FindById(created.SubmissionId);
            KarmaForgeDashboardSummary summary = reloadedService.GetDashboardSummary();

            KarmaForgeSubmissionProjection restored = Assert.IsType<KarmaForgeSubmissionProjection>(persisted);
            Assert.Equal("legacy_import_candidate", restored.Candidate.CandidateDecision);
            Assert.Equal("queued_for_product_governor", restored.QueueStatus);
            Assert.Equal(1, summary.TotalPackets);
            Assert.Equal(1, summary.GovernorQueueCount);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    private static IConfiguration CreateConfiguration(string tempRoot)
        => new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_KARMA_FORGE_STORE_PATH"] = Path.Combine(tempRoot, "karma-forge-store.json")
            })
            .Build();

    private static string CreateTempRoot(string suffix)
    {
        string path = Path.Combine(Path.GetTempPath(), $"{suffix}-{Guid.NewGuid():N}");
        Directory.CreateDirectory(path);
        return path;
    }

    private static void DeleteTempRoot(string tempRoot)
    {
        if (Directory.Exists(tempRoot))
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }
}
