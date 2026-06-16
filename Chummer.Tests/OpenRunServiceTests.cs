using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class OpenRunServiceTests
{
    [Fact]
    public void OpenRunLoopPersistsListingJoinScheduleHandoffAndCloseout()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "open-run-service", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS"] = "30"
                })
                .Build();

            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            SupportStore supportStore = new(configuration, NullLogger<SupportStore>.Instance);
            CampaignSpineService campaignSpine = new(
                store,
                new WorkspaceLifecyclePolicyService(configuration),
                new CampaignArtifactRegistryBridge(store),
                supportStore);

            var gm = accounts.EnsureUser("subject.gm", "GM Demo", "gm@example.invalid");
            var applicant = accounts.EnsureUser("subject.applicant", "Applicant Demo", "applicant@example.invalid");
            var gmWorkspace = campaignSpine.GetStarterWorkspace(gm)
                ?? throw new InvalidOperationException("Expected a GM starter workspace.");
            var applicantWorkspace = campaignSpine.GetStarterWorkspace(applicant)
                ?? throw new InvalidOperationException("Expected an applicant starter workspace.");
            var run = gmWorkspace.Runs.First();
            var applicantDossier = applicantWorkspace.Dossiers.First();

            campaignSpine.UpsertRunboardContinuity(gm, gmWorkspace, new RunboardContinuityUpdateRequest(
                RunId: run.RunId,
                ActiveSceneId: run.ActiveSceneId,
                TurnLedgerSummary: "Minor-action handoff stays pinned before the next opposition pass.",
                TurnLedgerEvidenceLines:
                [
                    "Player lane confirmed the last spend on the governed turn ledger.",
                    "Hub persisted the same handoff without replaying engine math."
                ],
                RunboardStateSummary: "Two blockers and the same extraction objective stay pinned on the GM runboard.",
                ObjectiveLines:
                [
                    "Extract the courier without spiking public awareness.",
                    "Keep the matrix relay stable until exfiltration."
                ],
                Blockers:
                [
                    "Suppress the loading-dock mooks before the next pass.",
                    "Resolve overwatch pressure before the courier leaves the van."
                ],
                ResolutionReportStatus: "draft",
                ResolutionReportSummary: "ResolutionReport draft keeps the courier handoff and matrix fallout continuity on one hub lane.",
                ResolutionNotes:
                [
                    "Spoiler-safe notes stay bounded to the same closeout draft.",
                    "No VTT map state or engine math is owned by hub here."
                ],
                NextSafeAction: "Open ResolutionReport and keep the same return lane on /account/work#runboard.",
                Note: "Open-run service proof setup."));

            OpenRunListingProjection listing = campaignSpine.CreateOpenRun(gm, gmWorkspace.WorkspaceId, new OpenRunCreateRequest(
                RunId: run.RunId,
                ListingTitle: "Tacoma docks night extraction",
                Summary: "A governed community open run for one night of extraction fallout.",
                Visibility: "community",
                TableContractSummary: "Beginner-friendly table with explicit safety tool acknowledgement and spoiler-safe closeout.",
                AdmissionMode: "request_to_join",
                SeatsTotal: 4,
                RequireRunnerDossier: true,
                AllowQuickstartRunner: true,
                SchedulingMode: "lunacal_slots",
                ExpectedDurationMinutes: 240,
                Platform: "discord",
                VoiceRequired: true,
                ObserverMode: "manual_markers",
                ReservedSeatRoles:
                [
                    "decker",
                    "face"
                ],
                Note: "Open-run service proof."));
            Assert.Contains(campaignSpine.GetOpenRuns(applicant), item => string.Equals(item.OpenRunId, listing.OpenRunId, StringComparison.OrdinalIgnoreCase));
            Assert.NotNull(campaignSpine.GetOpenRun(applicant, listing.OpenRunId));

            OpenRunJoinRequestProjection joinRequest = campaignSpine.SubmitOpenRunJoinRequest(applicant, listing.OpenRunId, new OpenRunJoinRequestCommand(
                DossierId: applicantDossier.DossierId,
                QuickstartPackId: null,
                TableContractAcknowledged: true,
                VoiceConsentAcknowledged: true,
                PlatformReady: true,
                Note: "Applicant can make the Discord handoff."));
            Assert.Equal("pending_review", joinRequest.Status);

            OpenRunJoinRequestProjection reviewedJoinRequest = campaignSpine.ReviewOpenRunJoinRequest(gm, listing.OpenRunId, joinRequest.RequestId, new OpenRunJoinReviewRequest(
                Decision: "accepted",
                Note: "Runner fits the governed role and rules posture."));
            Assert.Equal("accepted", reviewedJoinRequest.Status);

            OpenRunScheduleReceiptProjection schedule = campaignSpine.ScheduleOpenRun(gm, listing.OpenRunId, new OpenRunScheduleRequest(
                StartsAtUtc: DateTimeOffset.UtcNow.AddDays(2),
                Timezone: "Europe/Vienna",
                Note: "Lock the first Saturday night slot."));
            Assert.Contains("scheduled", schedule.Summary, StringComparison.OrdinalIgnoreCase);
            Assert.NotNull(schedule.Envelope);
            Assert.Equal("open_run_schedule", schedule.Envelope!.ReceiptKind);
            Assert.Equal("community.open_run", schedule.Envelope.OwnerScope);

            OpenRunMeetingHandoffProjection handoff = campaignSpine.CreateOpenRunMeetingHandoff(gm, listing.OpenRunId, new OpenRunMeetingHandoffRequest(
                ProviderKind: "discord_event",
                ProviderLabel: "Shadowcasters Tacoma Table",
                AccessPolicy: "accepted_players_only",
                ExpiresAtUtc: DateTimeOffset.UtcNow.AddDays(2).AddHours(8),
                Note: "Discord event is only a projection lane."));
            Assert.Contains(applicant.UserId, handoff.AcceptedUserIds);

            OpenRunCloseoutProjection closeout = campaignSpine.CloseOutOpenRun(gm, listing.OpenRunId, new OpenRunCloseoutRequest(
                Summary: "Open-run closeout files ResolutionReport and keeps world-memory grounded on the governed hub lane.",
                WorldTickSummary: "Tacoma docks fallout becomes a governed WorldTick after the open run closes.",
                ConsequenceSummary: "Heat escalates across Tacoma after the community open run closes out.",
                NewsTitle: "Tacoma docks rumor points to an extraction crew",
                NewsSummary: "Player-safe reports mention a dockside extraction crew, but the preview stays separate from world truth.",
                NewsSource: "Tacoma Shadowfeed",
                NewsUrl: "https://example.invalid/open-run/tacoma-docks",
                NextSafeAction: "Review the governed WorldTick and player-safe preview before the next open-run listing ships.",
                Note: "Open-run service proof."));
            Assert.False(string.IsNullOrWhiteSpace(closeout.WorldTickId));
            Assert.False(string.IsNullOrWhiteSpace(closeout.PlayerSafeNewsId));

            OpenRunOrchestrationProjection detail = campaignSpine.GetOpenRun(gm, listing.OpenRunId)
                ?? throw new InvalidOperationException("Expected open-run detail for the GM.");
            Assert.Equal("closed", detail.Listing.Status);
            Assert.NotNull(detail.Schedule);
            Assert.NotNull(detail.MeetingHandoff);
            Assert.NotNull(detail.Closeout);
            Assert.Contains(detail.Roster, item => string.Equals(item.UserId, applicant.UserId, StringComparison.OrdinalIgnoreCase) && string.Equals(item.SeatStatus, "accepted", StringComparison.OrdinalIgnoreCase));

            CommunityStore reloadedStore = new(configuration, NullLogger<CommunityStore>.Instance);
            SupportStore reloadedSupportStore = new(configuration, NullLogger<SupportStore>.Instance);
            CampaignSpineService reloadedSpine = new(
                reloadedStore,
                new WorkspaceLifecyclePolicyService(configuration),
                new CampaignArtifactRegistryBridge(reloadedStore),
                reloadedSupportStore);

            OpenRunOrchestrationProjection reloadedDetail = reloadedSpine.GetOpenRun(gm, listing.OpenRunId)
                ?? throw new InvalidOperationException("Expected open-run detail after reload.");
            Assert.Equal("closed", reloadedDetail.Listing.Status);
            Assert.NotNull(reloadedDetail.Schedule);
            Assert.NotNull(reloadedDetail.MeetingHandoff);
            Assert.NotNull(reloadedDetail.Closeout);
            Assert.Equal(closeout.WorldTickId, reloadedDetail.Closeout!.WorldTickId);
            CampaignWorkspaceProjection reloadedWorkspace = reloadedSpine.GetWorkspace(gm, gmWorkspace.WorkspaceId)
                ?? throw new InvalidOperationException("Expected workspace after reload.");
            Assert.NotNull(reloadedWorkspace.CampaignAdoptionLoop);
            Assert.NotNull(reloadedWorkspace.CampaignAdoptionLoop!.ResolutionReportApproval);
            Assert.Contains(reloadedWorkspace.CampaignAdoptionLoop.WorldTicks, item => string.Equals(item.WorldTickId, closeout.WorldTickId, StringComparison.OrdinalIgnoreCase));
            Assert.Contains(reloadedWorkspace.CampaignAdoptionLoop.PlayerSafeNews, item => string.Equals(item.NewsId, closeout.PlayerSafeNewsId, StringComparison.OrdinalIgnoreCase));
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }
}
