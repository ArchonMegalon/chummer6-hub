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

public sealed class RegistryTruthBindingServiceTests
{
    [Fact]
    public void RegistryTruthBindingsCoverDownloadsInstallHelpAccountAwareGuidanceSupportRecoveryAndPublicShelf()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "registry-truth-bindings", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            File.WriteAllText(
                Path.Combine(tempRoot, "releases.json"),
                JsonSerializer.Serialize(new PublicReleaseManifestDto(
                    Version: "0.8.5",
                    Channel: "preview",
                    PublishedAt: DateTimeOffset.UtcNow,
                    Downloads:
                    [
                        new PublicReleaseArtifactDto(
                            Id: "avalonia-linux-x64-installer",
                            Platform: "linux",
                            Url: "https://example.invalid/downloads/avalonia-linux-x64-installer.exe",
                            Sha256: new string('d', 64),
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
                    FixAvailabilitySummary: "The affected install can move forward on the current preview without a detached workaround."),
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
            SupportConciergePacketService concierge = new(releases, new SupportCasePresentationService());
            RegistryTruthBindingService service = new(releases, concierge);

            InstallLinkingSummaryDto installLinking = new(
                RecentReceipts:
                [
                    new DownloadReceiptDto(
                        ReceiptId: "receipt-install-003",
                        ArtifactId: "avalonia-linux-x64-installer",
                        ArtifactLabel: "Avalonia Linux x64",
                        FileName: "avalonia-linux-x64-installer.exe",
                        DownloadUrl: "https://example.invalid/downloads/avalonia-linux-x64-installer.exe",
                        Channel: "preview",
                        Version: "0.8.5",
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
                        InstallationId: "install-demo-003",
                        ArtifactId: "avalonia-linux-x64-installer",
                        Channel: "preview",
                        Version: "0.8.5",
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
                        GrantId: "grant-demo-003")
                ]);

            SupportCaseProjection supportCase = new(
                CaseId: "case-demo-003",
                ClusterKey: "case-demo",
                Kind: "installer",
                Status: "fix_ready",
                Title: "Installer recovery trail",
                Summary: "Claimed install needs registry-backed support recovery.",
                Detail: "Installed build receipt: receipt-install-003",
                CandidateOwnerRepo: "chummer6-hub",
                DesignImpactSuspected: false,
                CreatedAtUtc: now.AddDays(-2),
                UpdatedAtUtc: now,
                Source: "manual",
                ReporterEmail: "demo@example.invalid",
                ReporterUserId: "user-demo",
                ReporterSubjectId: "subject-demo",
                InstallationId: "install-demo-003",
                ApplicationVersion: "0.8.5",
                ReleaseChannel: "preview",
                HeadId: "avalonia",
                Platform: "linux",
                Arch: "x64",
                FixedVersion: "0.8.5",
                FixedChannel: "preview",
                ReleasedToReporterChannelAtUtc: now.AddHours(-1),
                UserNotifiedAtUtc: now.AddMinutes(-30),
                ReporterVerificationState: "pending_user_confirmation");

            RegistryTruthBindingBundle bundle = service.Build(new RegistryTruthBindingContext(
                InstallLinking: installLinking,
                SupportCases:
                [
                    supportCase
                ],
                Locale: "en-US"));

            Assert.Contains(bundle.Bindings, item => string.Equals(item.SurfaceId, "downloads", StringComparison.Ordinal) && string.Equals(item.Route, "/downloads", StringComparison.Ordinal));
            Assert.Contains(bundle.Bindings, item => string.Equals(item.SurfaceId, "install_help", StringComparison.Ordinal) && string.Equals(item.ComparisonRoute, "/status", StringComparison.Ordinal));
            Assert.Contains(bundle.Bindings, item => string.Equals(item.SurfaceId, "account_aware_guidance", StringComparison.Ordinal) && string.Equals(item.Route, "/account/access", StringComparison.Ordinal));
            Assert.Contains(bundle.Bindings, item => string.Equals(item.SurfaceId, "support_recovery", StringComparison.Ordinal) && string.Equals(item.Route, "/api/v1/install-linking/continuation/support", StringComparison.Ordinal));
            Assert.Contains(bundle.Bindings, item => string.Equals(item.SurfaceId, "public_release_shelf", StringComparison.Ordinal) && string.Equals(item.Route, "/now", StringComparison.Ordinal));
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
