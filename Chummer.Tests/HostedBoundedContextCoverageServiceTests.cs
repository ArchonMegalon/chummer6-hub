using System.Text.Json;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class HostedBoundedContextCoverageServiceTests
{
    [Fact]
    public void HostedBoundedContextCoverageKeepsPublicAccountCommunityCampaignSupportAndOrchestrationSeparate()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hosted-bounded-context-coverage", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            File.WriteAllText(
                Path.Combine(tempRoot, "releases.json"),
                JsonSerializer.Serialize(new PublicReleaseManifestDto(
                    Version: "0.8.9",
                    Channel: "preview",
                    PublishedAt: DateTimeOffset.UtcNow,
                    Downloads:
                    [
                        new PublicReleaseArtifactDto(
                            Id: "avalonia-linux-x64-installer",
                            Platform: "linux",
                            Url: "https://example.invalid/downloads/avalonia-linux-x64-installer.exe",
                            Sha256: new string('f', 64),
                            SizeBytes: 1024,
                            Head: "avalonia",
                            PlatformId: "linux",
                            Arch: "x64",
                            Kind: "installer",
                            FileName: "avalonia-linux-x64-installer.exe",
                            InstallAccessClass: "claimed")
                    ],
                    Source: "registry",
                    ProofStatus: "passed",
                    SupportabilityState: "local_docker_proven",
                    FixAvailabilitySummary: "The current preview keeps public and signed-in followthrough aligned."),
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
            HostedBoundedContextCoverageService service = new(releases);

            HubUserDto user = new(
                UserId: "user-demo-135",
                SubjectId: "subject-demo-135",
                DisplayName: "Archon Demo",
                Handle: "archondemo",
                Visibility: "private",
                Timezone: "Europe/Vienna",
                CountryCode: "AT",
                LinkedPrincipals:
                [
                    "email:demo@example.invalid",
                    "discord:archon-demo"
                ],
                GroupIds:
                [
                    "group-demo-135"
                ],
                CreatedAtUtc: now.AddDays(-30),
                UpdatedAtUtc: now)
            {
                Email = "demo@example.invalid"
            };

            GroupDto group = new(
                GroupId: "group-demo-135",
                GroupType: "community",
                Name: "Tacoma Night Tables",
                Visibility: "private",
                OwnerUserId: "user-demo-135",
                Capabilities:
                [
                    "open_runs",
                    "campaigns"
                ],
                Memberships:
                [
                    new GroupMembershipDto(
                        MembershipId: "membership-demo-135",
                        GroupId: "group-demo-135",
                        UserId: "user-demo-135",
                        Role: "organizer",
                        JoinedAtUtc: now.AddDays(-14))
                ],
                CreatedAtUtc: now.AddDays(-20),
                UpdatedAtUtc: now.AddHours(-1));

            SupportCaseProjection supportCase = new(
                CaseId: "case-demo-135",
                ClusterKey: "case-cluster-demo-135",
                Kind: "feedback",
                Status: "user_notified",
                Title: "Hosted boundary coverage",
                Summary: "Need first-party routed followthrough for hosted context coverage.",
                Detail: "Release shelf, support, campaign, and account posture must stay separated.",
                CandidateOwnerRepo: "chummer6-hub",
                DesignImpactSuspected: false,
                CreatedAtUtc: now.AddDays(-2),
                UpdatedAtUtc: now.AddMinutes(-20),
                Source: "manual",
                ReporterEmail: "demo@example.invalid",
                ReporterUserId: "user-demo-135",
                ReporterSubjectId: "subject-demo-135",
                InstallationId: "install-demo-135",
                ApplicationVersion: "0.8.9",
                ReleaseChannel: "preview",
                HeadId: "avalonia",
                Platform: "linux",
                Arch: "x64");

            SignalToCanonPacketBundle signalBundle = publicSignals.Build(supportCase, "en-US");

            OpenRunOrchestrationProjection openRun = new(
                Listing: new OpenRunListingProjection(
                    OpenRunId: "open-run-demo-135",
                    WorkspaceId: "workspace-demo-135",
                    CampaignId: "campaign-demo-135",
                    RunId: "run-demo-135",
                    RunTitle: "Tacoma bridge extraction",
                    ListingTitle: "Tacoma bridge extraction",
                    Visibility: "community",
                    Status: "scheduled",
                    Summary: "Community open run that stays on the governed campaign spine.",
                    TableContractSummary: "Table contract stays on the signed-in rail with spoiler-safe closeout.",
                    JoinPolicy: new OpenRunJoinPolicyProjection(
                        AdmissionMode: "request_to_join",
                        SeatsTotal: 4,
                        ReservedSeatRoles:
                        [
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
                        Summary: "Community open-run policy stays on the governed hub rail."),
                    SchedulingPosture: "scheduled",
                    QuickstartAllowed: true,
                    EvidenceLines:
                    [
                        "Open-run listing remains attached to the signed-in community and campaign rails."
                    ],
                    CreatedByUserId: "user-demo-135",
                    CreatedAtUtc: now.AddDays(-5),
                    UpdatedAtUtc: now.AddDays(-1)),
                JoinRequests: [],
                Roster: [],
                Schedule: new OpenRunScheduleReceiptProjection(
                    ReceiptId: "schedule-demo-135",
                    OpenRunId: "open-run-demo-135",
                    SchedulingMode: "lunacal_slots",
                    StartsAtUtc: now.AddDays(2),
                    ExpectedDurationMinutes: 240,
                    Platform: "discord",
                    Timezone: "Europe/Vienna",
                    Summary: "Schedule receipt stays on the campaign spine.",
                    EvidenceLines:
                    [
                        "Scheduling remains a campaign-owned receipt."
                    ],
                    ScheduledByUserId: "user-demo-135",
                    ScheduledAtUtc: now.AddHours(-12)),
                MeetingHandoff: null,
                Closeout: new OpenRunCloseoutProjection(
                    CloseoutId: "closeout-demo-135",
                    OpenRunId: "open-run-demo-135",
                    ResolutionApprovalId: "resolution-demo-135",
                    WorldTickId: "worldtick-demo-135",
                    PlayerSafeNewsId: "news-demo-135",
                    Summary: "Closeout proof stays on the campaign spine and never escapes to public or support routes.",
                    EvidenceLines:
                    [
                        "Closeout and player-safe preview remain campaign-owned."
                    ],
                    ClosedByUserId: "user-demo-135",
                    ClosedAtUtc: now.AddHours(-1)));

            InstallLinkingSummaryDto installLinking = new(
                RecentReceipts:
                [
                    new DownloadReceiptDto(
                        ReceiptId: "receipt-demo-135",
                        ArtifactId: "avalonia-linux-x64-installer",
                        ArtifactLabel: "Avalonia Linux x64",
                        FileName: "avalonia-linux-x64-installer.exe",
                        DownloadUrl: "https://example.invalid/downloads/avalonia-linux-x64-installer.exe",
                        Channel: "preview",
                        Version: "0.8.9",
                        Head: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        Kind: "installer",
                        InstallAccessClass: "claimed",
                        IssuedAtUtc: now.AddHours(-3),
                        UserId: "user-demo-135",
                        SubjectId: "subject-demo-135")
                ],
                PendingClaimTickets: [],
                ClaimedInstallations:
                [
                    new ClaimedInstallationDto(
                        InstallationId: "install-demo-135",
                        ArtifactId: "avalonia-linux-x64-installer",
                        Channel: "preview",
                        Version: "0.8.9",
                        InstallAccessClass: "claimed",
                        Status: "active",
                        CreatedAtUtc: now.AddDays(-3),
                        UpdatedAtUtc: now,
                        UserId: "user-demo-135",
                        SubjectId: "subject-demo-135",
                        HeadId: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        HostLabel: "demo-linux",
                        GrantId: "grant-demo-135")
                ]);

            HostedBoundedContextCoverageBundle bundle = service.Build(new HostedBoundedContextCoverageContext(
                User: user,
                Groups:
                [
                    group
                ],
                OpenRun: openRun,
                SupportCase: supportCase,
                PublicSignals: signalBundle,
                InstallLinking: installLinking,
                Locale: "en-US",
                CommunityHubRoute: "/account/work#community-ops"));

            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "public_context", StringComparison.Ordinal) && string.Equals(item.Route, "/", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "account_context", StringComparison.Ordinal) && string.Equals(item.Route, "/account", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "community_context", StringComparison.Ordinal) && string.Equals(item.Route, "/account/work#community-ops", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "campaign_context", StringComparison.Ordinal) && string.Equals(item.Route, "/account/work/workspaces/workspace-demo-135", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "support_context", StringComparison.Ordinal) && item.Route.Contains("/account/support/", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "orchestration_boundary", StringComparison.Ordinal) && string.Equals(item.Route, "/downloads/install", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "bounded_context_closure", StringComparison.Ordinal) && string.Equals(item.Route, "/progress", StringComparison.Ordinal));
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
