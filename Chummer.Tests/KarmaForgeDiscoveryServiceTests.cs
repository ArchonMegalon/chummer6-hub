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
            KarmaForgeDiscoveryService service = new(store, configuration);

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
            Assert.Equal(8, submission.Packet.Source.ExternalStages.Count);
            Assert.Contains(submission.Packet.Source.ExternalStages, stage => stage.StageKey == "structured_prescreen" && stage.Status == "bounded_ready");
            Assert.Contains(submission.Packet.Source.ExternalStages, stage => stage.StageKey == "adaptive_interview" && stage.Status == "bounded_ready");
            Assert.Contains(submission.Packet.Source.ExternalStages, stage => stage.StageKey == "scheduled_followup" && stage.Status == "bounded_ready");
            Assert.Contains(submission.Packet.Source.ExternalStages, stage => stage.StageKey == "review_board" && stage.Status == "bounded_ready");
            Assert.Contains(submission.Packet.Source.ExternalStages, stage => stage.StageKey == "decision" && stage.Status == "bounded_ready");
            Assert.Contains(submission.Packet.Source.ExternalStages, stage => stage.StageKey == "closeout" && stage.Status == "bounded_waiting_decision");
            Assert.Contains(submission.Packet.Source.JourneyProofEventRefs, journey => journey.EventKey == "karma_request_submitted" && journey.JourneyKey == "karma_forge_discovery");
            Assert.Contains(submission.Packet.Source.JourneyProofEventRefs, journey => journey.EventKey == "karma_interview_completed" && journey.JourneyKey == "karma_forge_discovery");
            Assert.Contains(submission.Packet.Source.JourneyProofEventRefs, journey => journey.EventKey == "karma_demand_packet_created" && journey.JourneyKey == "karma_forge_discovery");
            Assert.Contains(submission.Packet.Source.JourneyProofEventRefs, journey => journey.EventKey == "karma_candidate_reviewed" && journey.JourneyKey == "karma_forge_discovery");
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
            KarmaForgeDiscoveryService service = new(store, configuration);

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
            KarmaForgeDiscoveryService reloadedService = new(reloadedStore, configuration);
            KarmaForgeSubmissionProjection? persisted = reloadedService.FindById(created.SubmissionId);
            KarmaForgeDashboardSummary summary = reloadedService.GetDashboardSummary();

            KarmaForgeSubmissionProjection restored = Assert.IsType<KarmaForgeSubmissionProjection>(persisted);
            Assert.Equal("legacy_import_candidate", restored.Candidate.CandidateDecision);
            Assert.Equal("queued_for_product_governor", restored.QueueStatus);
            Assert.Equal(1, summary.TotalPackets);
            Assert.Equal(1, summary.GovernorQueueCount);
            Assert.Contains(restored.Packet.Source.ExternalStages, stage => stage.StageKey == "adaptive_interview" && stage.Status == "bounded_pending_consent");
            Assert.Contains(restored.Packet.Source.ExternalStages, stage => stage.StageKey == "quant_validation" && stage.Status == "bounded_pending_consent");
            Assert.Contains(restored.Packet.Source.ExternalStages, stage => stage.StageKey == "review_board" && stage.Status == "bounded_ready");
            Assert.Contains(restored.Packet.Source.ExternalStages, stage => stage.StageKey == "decision" && stage.Status == "bounded_ready");
            Assert.Contains(restored.Packet.Source.ExternalStages, stage => stage.StageKey == "closeout" && stage.Status == "bounded_waiting_decision");
            Assert.Contains(restored.Packet.Source.JourneyProofEventRefs, journey => journey.EventKey == "karma_demand_packet_created");
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
                ["CHUMMER_KARMA_FORGE_STORE_PATH"] = Path.Combine(tempRoot, "karma-forge-store.json"),
                ["CHUMMER_KARMA_FORGE_DEFTFORM_BASE_URL"] = "https://forms.example.invalid/deftform",
                ["CHUMMER_KARMA_FORGE_ICANPRENEUR_BASE_URL"] = "https://discover.example.invalid/icanpreneur",
                ["CHUMMER_KARMA_FORGE_METASURVEY_BASE_URL"] = "https://surveys.example.invalid/metasurvey",
                ["CHUMMER_KARMA_FORGE_LUNACAL_BASE_URL"] = "https://schedule.example.invalid/lunacal"
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
