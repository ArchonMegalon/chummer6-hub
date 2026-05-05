using System.Text.Json;
using Chummer.Campaign.Contracts;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class HostedCompanionPacketServiceTests
{
    [Fact]
    public void HostedCompanionPacketsCoverInstallUpdateSupportRestoreCampaignPublicationAndPublicHub()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hosted-companion-packets", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            File.WriteAllText(
                Path.Combine(tempRoot, "releases.json"),
                JsonSerializer.Serialize(new PublicReleaseManifestDto(
                    Version: "0.8.2",
                    Channel: "preview",
                    PublishedAt: DateTimeOffset.UtcNow,
                    Downloads:
                    [
                        new PublicReleaseArtifactDto(
                            Id: "avalonia-linux-x64-installer",
                            Platform: "linux",
                            Url: "https://example.invalid/downloads/avalonia-linux-x64-installer.exe",
                            Sha256: new string('a', 64),
                            SizeBytes: 1024,
                            Head: "avalonia",
                            PlatformId: "linux",
                            Arch: "x64",
                            Kind: "installer",
                            FileName: "avalonia-linux-x64-installer.exe",
                            InstallAccessClass: "claimed")
                    ],
                    SupportabilityState: "watch",
                    SupportabilitySummary: "Preview shelf stays support-directed while claimed-install and update posture remain visible."),
                new JsonSerializerOptions(JsonSerializerDefaults.Web)),
                encoding: System.Text.Encoding.UTF8);

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = tempRoot,
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

            var user = accounts.EnsureUser("subject.demo", "Demo Operator", "demo@example.invalid");
            AccountCampaignSummary summary = campaignSpine.GetAccountSummary(user);
            CampaignWorkspaceProjection workspace = summary.Workspaces.First();

            InstallLinkingSummaryDto installLinking = new(
                RecentReceipts:
                [
                    new DownloadReceiptDto(
                        ReceiptId: "receipt-install-001",
                        ArtifactId: "avalonia-linux-x64-installer",
                        ArtifactLabel: "Avalonia Linux x64",
                        FileName: "avalonia-linux-x64-installer.exe",
                        DownloadUrl: "https://example.invalid/downloads/avalonia-linux-x64-installer.exe",
                        Channel: "preview",
                        Version: "0.8.1",
                        Head: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        Kind: "installer",
                        InstallAccessClass: "claimed",
                        IssuedAtUtc: DateTimeOffset.UtcNow.AddHours(-2),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId)
                ],
                PendingClaimTickets: [],
                ClaimedInstallations:
                [
                    new ClaimedInstallationDto(
                        InstallationId: "install-demo-001",
                        ArtifactId: "avalonia-linux-x64-installer",
                        Channel: "preview",
                        Version: "0.8.1",
                        InstallAccessClass: "claimed",
                        Status: "active",
                        CreatedAtUtc: DateTimeOffset.UtcNow.AddDays(-1),
                        UpdatedAtUtc: DateTimeOffset.UtcNow,
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        HeadId: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        HostLabel: "demo-linux",
                        GrantId: "grant-demo-001")
                ]);

            SupportCaseProjection supportCase = new(
                CaseId: "case-demo-001",
                ClusterKey: "case-demo",
                Kind: "installer",
                Status: "fix_ready",
                Title: "Installer follow-through",
                Summary: "Claimed install needs explicit hosted fix confirmation.",
                Detail: "Installed build receipt: receipt-install-001",
                CandidateOwnerRepo: "chummer6-ui",
                DesignImpactSuspected: false,
                CreatedAtUtc: DateTimeOffset.UtcNow.AddDays(-2),
                UpdatedAtUtc: DateTimeOffset.UtcNow,
                Source: "manual",
                ReporterEmail: "demo@example.invalid",
                ReporterUserId: user.UserId,
                ReporterSubjectId: user.SubjectId,
                InstallationId: "install-demo-001",
                ApplicationVersion: "0.8.1",
                ReleaseChannel: "preview",
                HeadId: "avalonia",
                Platform: "linux",
                Arch: "x64",
                FixedVersion: "0.8.2",
                FixedChannel: "preview",
                ReleasedToReporterChannelAtUtc: DateTimeOffset.UtcNow.AddHours(-1),
                UserNotifiedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-30),
                ReporterVerificationState: "pending_user_confirmation");

            CreatorPublicationProjection publication = new(
                PublicationId: "publication-demo-001",
                Title: "Tacoma primer",
                Kind: "campaign_primer",
                Summary: "A discoverable primer packet is ready for new players.",
                CampaignId: workspace.CampaignId,
                DossierId: workspace.Dossiers.FirstOrDefault()?.DossierId,
                ArtifactId: "artifact-demo-001",
                ProvenanceSummary: "Published from the same governed campaign workspace.",
                DiscoverySummary: "Public discovery is live on the first-party shelf.",
                Visibility: "public",
                PublicationStatus: "published",
                TrustBand: "first_party",
                Discoverable: true,
                UpdatedAtUtc: DateTimeOffset.UtcNow,
                NextSafeAction: "Open the primer packet from the governed publication rail.",
                CampaignReturnSummary: workspace.ReturnSummary,
                SupportClosureSummary: "Support posture stays aligned with the published primer.");

            PublicReleaseManifestService releases = new(configuration);
            SupportCasePresentationService supportPresentation = new();
            SupportConciergePacketService supportConciergePackets = new(releases, supportPresentation);
            HostedCompanionPacketService hostedCompanionPackets = new(releases, supportConciergePackets);

            HostedCompanionPacketBundle packetBundle = hostedCompanionPackets.Build(new HostedCompanionPacketContext(
                Restore: summary.Restore,
                Workspaces: summary.Workspaces,
                Publications:
                [
                    publication
                ],
                SupportCases:
                [
                    supportCase
                ],
                InstallLinking: installLinking,
                Locale: "en-US"));

            Assert.Contains(packetBundle.AccountPackets, item => string.Equals(item.OwningDomain, "install", StringComparison.Ordinal));
            Assert.Contains(packetBundle.AccountPackets, item => string.Equals(item.OwningDomain, "update", StringComparison.Ordinal) && string.Equals(item.TriggerClass, "preview_scout_warning", StringComparison.Ordinal));
            Assert.Contains(packetBundle.AccountPackets, item => string.Equals(item.OwningDomain, "support", StringComparison.Ordinal));
            Assert.Contains(packetBundle.AccountPackets, item => string.Equals(item.OwningDomain, "restore", StringComparison.Ordinal));
            Assert.Contains(packetBundle.AccountPackets, item => string.Equals(item.OwningDomain, "campaign_workspace", StringComparison.Ordinal));
            Assert.Contains(packetBundle.AccountPackets, item => string.Equals(item.OwningDomain, "publication", StringComparison.Ordinal) && item.AllowedActions.Any(action => string.Equals(action.Href, "/artifacts/publications/publication-demo-001", StringComparison.Ordinal)));
            Assert.Contains(packetBundle.PublicHubPackets, item => string.Equals(item.OwningDomain, "public_hub", StringComparison.Ordinal) && item.AllowedActions.Any(action => string.Equals(action.Href, "/downloads", StringComparison.Ordinal)));
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
