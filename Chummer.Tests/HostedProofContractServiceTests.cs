using System.Text.Json;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class HostedProofContractServiceTests
{
    [Fact]
    public void HostedProofContractsCoverOpenRunsShadowcastersPublicSignalCommunityAndAccountAwareHorizonConversion()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hosted-proof-contracts", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            File.WriteAllText(
                Path.Combine(tempRoot, "releases.json"),
                JsonSerializer.Serialize(new PublicReleaseManifestDto(
                    Version: "0.8.4",
                    Channel: "preview",
                    PublishedAt: DateTimeOffset.UtcNow,
                    Downloads:
                    [
                        new PublicReleaseArtifactDto(
                            Id: "avalonia-linux-x64-installer",
                            Platform: "linux",
                            Url: "https://example.invalid/downloads/avalonia-linux-x64-installer.exe",
                            Sha256: new string('c', 64),
                            SizeBytes: 1024,
                            Head: "avalonia",
                            PlatformId: "linux",
                            Arch: "x64",
                            Kind: "installer",
                            FileName: "avalonia-linux-x64-installer.exe",
                            InstallAccessClass: "claimed")
                    ],
                    SupportabilityState: "watch",
                    SupportabilitySummary: "Preview downloads keep the live comparison honest while the signed-in return paths stay first-party."),
                new JsonSerializerOptions(JsonSerializerDefaults.Web)),
                encoding: System.Text.Encoding.UTF8);

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = tempRoot
                })
                .Build();

            DateTimeOffset now = DateTimeOffset.UtcNow;
            PublicReleaseManifestService releases = new(configuration);
            PublicSignalToCanonPacketService publicSignals = new(releases);
            HostedProofContractService service = new(releases);

            SignalToCanonPacketBundle signalBundle = publicSignals.Build(new SupportCaseProjection(
                CaseId: "case-public-002",
                ClusterKey: "public-cluster-002",
                Kind: "feedback",
                Status: "new",
                Title: "Public signal review",
                Summary: "Need a reviewed signal packet path.",
                Detail: "Public roadmap and support paths should stay coordinated.",
                CandidateOwnerRepo: "chummer6-hub",
                DesignImpactSuspected: true,
                CreatedAtUtc: now.AddDays(-2),
                UpdatedAtUtc: now,
                Source: "public_web"));

            OpenRunOrchestrationProjection openRun = new(
                Listing: new OpenRunListingProjection(
                    OpenRunId: "open-run-demo-001",
                    WorkspaceId: "workspace-demo-001",
                    CampaignId: "campaign-demo-001",
                    RunId: "run-demo-001",
                    RunTitle: "Tacoma docks extraction",
                    ListingTitle: "Tacoma docks night extraction",
                    Visibility: "community",
                    Status: "closed",
                    Summary: "A reviewed community open run for one night of extraction fallout.",
                    TableContractSummary: "Beginner-friendly table with explicit safety tool acknowledgement and spoiler-safe closeout.",
                    JoinPolicy: new OpenRunJoinPolicyProjection(
                        AdmissionMode: "request_to_join",
                        SeatsTotal: 4,
                        ReservedSeatRoles:
                        [
                            "decker",
                            "face"
                        ],
                        RequireRunnerDossier: true,
                        AllowQuickstartRunner: true,
                        RuleEnvironmentFingerprint: "sr6-preview",
                        SchedulingMode: "lunacal_slots",
                        ExpectedDurationMinutes: 240,
                        CommunicationPlatform: "discord",
                        VoiceRequired: true,
                        ObserverMode: "manual_markers",
                        Summary: "Reviewed request-to-join open run on the same community page."),
                    SchedulingPosture: "scheduled",
                    QuickstartAllowed: true,
                    EvidenceLines:
                    [
                        "Community visibility keeps the listing discoverable on the reviewed open-run page."
                    ],
                    CreatedByUserId: "gm-demo",
                    CreatedAtUtc: now.AddDays(-3),
                    UpdatedAtUtc: now.AddDays(-1)),
                JoinRequests: [],
                Roster: [],
                Schedule: new OpenRunScheduleReceiptProjection(
                    ReceiptId: "schedule-demo-001",
                    OpenRunId: "open-run-demo-001",
                    SchedulingMode: "lunacal_slots",
                    StartsAtUtc: now.AddDays(2),
                    ExpectedDurationMinutes: 240,
                    Platform: "discord",
                    Timezone: "Europe/Vienna",
                    Summary: "Open run is scheduled on the reviewed Discord handoff page.",
                    EvidenceLines:
                    [
                        "Scheduling record stays in the same reviewed campaign workspace."
                    ],
                    ScheduledByUserId: "gm-demo",
                    ScheduledAtUtc: now.AddDays(-1)),
                MeetingHandoff: new OpenRunMeetingHandoffProjection(
                    HandoffId: "handoff-demo-001",
                    OpenRunId: "open-run-demo-001",
                    ProviderKind: "discord_event",
                    ProviderLabel: "Shadowcasters Tacoma Table",
                    AccessPolicy: "accepted_players_only",
                    ExpiresAtUtc: now.AddDays(2).AddHours(8),
                    AcceptedUserIds:
                    [
                        "runner-demo"
                    ],
                    Summary: "Meeting handoff stays a projection path and never replaces the reviewed open-run records.",
                    EvidenceLines:
                    [
                        "Accepted players still route back through the reviewed hub page."
                    ],
                    CreatedByUserId: "gm-demo",
                    CreatedAtUtc: now.AddHours(-12)),
                Closeout: new OpenRunCloseoutProjection(
                    CloseoutId: "closeout-demo-001",
                    OpenRunId: "open-run-demo-001",
                    ResolutionApprovalId: "resolution-demo-001",
                    WorldTickId: "worldtick-demo-001",
                    PlayerSafeNewsId: "news-demo-001",
                    Summary: "Open-run closeout files ResolutionReport, WorldTick, and player-safe news on the reviewed hub page.",
                    EvidenceLines:
                    [
                        "World memory and player-safe preview stay distinct."
                    ],
                    ClosedByUserId: "gm-demo",
                    ClosedAtUtc: now.AddHours(-1)));

            InstallLinkingSummaryDto installLinking = new(
                RecentReceipts:
                [
                    new DownloadReceiptDto(
                        ReceiptId: "receipt-install-002",
                        ArtifactId: "avalonia-linux-x64-installer",
                        ArtifactLabel: "Avalonia Linux x64",
                        FileName: "avalonia-linux-x64-installer.exe",
                        DownloadUrl: "https://example.invalid/downloads/avalonia-linux-x64-installer.exe",
                        Channel: "preview",
                        Version: "0.8.4",
                        Head: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        Kind: "installer",
                        InstallAccessClass: "claimed",
                        IssuedAtUtc: now.AddHours(-2),
                        UserId: "user-demo",
                        SubjectId: "subject-demo")
                ],
                PendingClaimTickets: [],
                ClaimedInstallations:
                [
                    new ClaimedInstallationDto(
                        InstallationId: "install-demo-002",
                        ArtifactId: "avalonia-linux-x64-installer",
                        Channel: "preview",
                        Version: "0.8.4",
                        InstallAccessClass: "claimed",
                        Status: "active",
                        CreatedAtUtc: now.AddDays(-1),
                        UpdatedAtUtc: now,
                        UserId: "user-demo",
                        SubjectId: "subject-demo",
                        HeadId: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        HostLabel: "demo-linux",
                        GrantId: "grant-demo-002")
                ]);

            HostedProofContractBundle bundle = service.Build(new HostedProofContractContext(
                OpenRun: openRun,
                PublicSignals: signalBundle,
                InstallLinking: installLinking,
                CommunityHubRoute: "/account/roster#community-ops",
                CommunityWorkspaceRoute: "/account/campaigns/workspace-demo-001",
                Locale: "en-US"));

            Assert.Contains(bundle.Contracts, item => string.Equals(item.SurfaceId, "open_runs", StringComparison.Ordinal) && string.Equals(item.Route, "/api/v1/campaign-spine/me/open-runs/open-run-demo-001", StringComparison.Ordinal));
            Assert.Contains(bundle.Contracts, item => string.Equals(item.SurfaceId, "shadowcasters", StringComparison.Ordinal) && string.Equals(item.ComparisonRoute, "/roadmap/black-ledger", StringComparison.Ordinal));
            Assert.Contains(bundle.Contracts, item => string.Equals(item.SurfaceId, "public_signal", StringComparison.Ordinal) && string.Equals(item.Route, "/participate", StringComparison.Ordinal));
            Assert.Contains(bundle.Contracts, item => string.Equals(item.SurfaceId, "community_hub", StringComparison.Ordinal) && string.Equals(item.Route, "/account/roster#community-ops", StringComparison.Ordinal));
            Assert.Contains(bundle.Contracts, item => string.Equals(item.SurfaceId, "account_aware_horizon_conversion", StringComparison.Ordinal) && string.Equals(item.ComparisonRoute, "/account/access", StringComparison.Ordinal));
            string contractText = string.Join(
                "\n",
                bundle.Contracts.SelectMany(item => new[]
                    {
                        item.CloseoutPosture,
                        item.Summary
                    }
                    .Concat(item.EvidenceLines)
                    .Concat(item.Actions.Select(action => action.Summary))));
            Assert.DoesNotContain(" rail", contractText, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("governed", contractText, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(" truth", contractText, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(" proof", contractText, StringComparison.OrdinalIgnoreCase);
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
