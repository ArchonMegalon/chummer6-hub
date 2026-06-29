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

public sealed class PrivacyBoundedSupportStatusServiceTests
{
    [Fact]
    public void PrivacyBoundedSupportStatusCoversSupportCrashFeedbackTelemetryRetentionAndFollowthrough()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "privacy-bounded-support-status", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            File.WriteAllText(
                Path.Combine(tempRoot, "releases.json"),
                JsonSerializer.Serialize(new PublicReleaseManifestDto(
                    Version: "0.8.6",
                    Channel: "preview",
                    PublishedAt: DateTimeOffset.UtcNow,
                    Downloads:
                    [
                        new PublicReleaseArtifactDto(
                            Id: "avalonia-linux-x64-installer",
                            Platform: "linux",
                            Url: "https://example.invalid/downloads/avalonia-linux-x64-installer.exe",
                            Sha256: new string('e', 64),
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
            PublicSignalToCanonPacketService publicSignals = new(releases);
            PrivacyBoundedSupportStatusService service = new(releases, concierge);

            SupportCaseProjection supportCase = new(
                CaseId: "case-demo-004",
                ClusterKey: "case-demo",
                Kind: "installer",
                Status: "user_notified",
                Title: "Installer closure trail",
                Summary: "Claimed install needs privacy-bounded followthrough.",
                Detail: "Installed build receipt: receipt-install-004",
                CandidateOwnerRepo: "chummer6-hub",
                DesignImpactSuspected: false,
                CreatedAtUtc: now.AddDays(-2),
                UpdatedAtUtc: now.AddMinutes(-15),
                Source: "manual",
                ReporterEmail: "demo@example.invalid",
                ReporterUserId: "user-demo",
                ReporterSubjectId: "subject-demo",
                InstallationId: "install-demo-004",
                ApplicationVersion: "0.8.6",
                ReleaseChannel: "preview",
                HeadId: "avalonia",
                Platform: "linux",
                Arch: "x64",
                FixedVersion: "0.8.6",
                FixedChannel: "preview",
                ReleasedToReporterChannelAtUtc: now.AddHours(-2),
                UserNotifiedAtUtc: now.AddMinutes(-30),
                ReporterVerificationState: "pending_user_confirmation");

            SignalToCanonPacketBundle signalBundle = publicSignals.Build(supportCase, "en-US");

            InstallLinkingSummaryDto installLinking = new(
                RecentReceipts:
                [
                    new DownloadReceiptDto(
                        ReceiptId: "receipt-install-004",
                        ArtifactId: "avalonia-linux-x64-installer",
                        ArtifactLabel: "Avalonia Linux x64",
                        FileName: "avalonia-linux-x64-installer.exe",
                        DownloadUrl: "https://example.invalid/downloads/avalonia-linux-x64-installer.exe",
                        Channel: "preview",
                        Version: "0.8.6",
                        Head: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        Kind: "installer",
                        InstallAccessClass: "claimed",
                        IssuedAtUtc: now.AddHours(-3),
                        UserId: "user-demo",
                        SubjectId: "subject-demo")
                ],
                PendingClaimTickets: [],
                ClaimedInstallations:
                [
                    new ClaimedInstallationDto(
                        InstallationId: "install-demo-004",
                        ArtifactId: "avalonia-linux-x64-installer",
                        Channel: "preview",
                        Version: "0.8.6",
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
                        GrantId: "grant-demo-004")
                ]);

            CrashWorkItemProjection crashWorkItem = new(
                WorkItemId: "crash-work-demo-001",
                ClusterId: "crash-cluster-demo-001",
                Status: "queued_for_triage",
                Summary: "Bounded crash triage keeps user-safe status without exposing raw diagnostics.",
                CandidateOwnerRepo: "chummer6-ui",
                RegressionSuspected: true,
                OccurrenceCount: 2,
                FirstSeenAtUtc: now.AddDays(-1),
                LastSeenAtUtc: now.AddMinutes(-10),
                RegistryContext: new CrashRegistryContextProjection(
                    ApplicationVersion: "0.8.6",
                    ReleaseChannel: "preview",
                    Platform: "linux",
                    ProcessArchitecture: "x64",
                    DesktopHead: "avalonia",
                    RuntimeHead: "sr6.preview.v1",
                    UpdateAvailable: false,
                    UpdateTargetVersion: null,
                    Source: "smoke"),
                IncidentIds:
                [
                    "crash-inc-demo-001"
                ]);

            PrivacyBoundedSupportStatusBundle bundle = service.Build(new PrivacyBoundedSupportStatusContext(
                SupportCases:
                [
                    supportCase
                ],
                CrashWorkItems:
                [
                    crashWorkItem
                ],
                PublicSignals: signalBundle,
                InstallLinking: installLinking,
                Locale: "en-US"));

            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "support_status", StringComparison.Ordinal) && item.Route.Contains("/account/support/", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "crash_status", StringComparison.Ordinal) && string.Equals(item.Route, "/api/v1/support/crashes/work-items", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "feedback_status", StringComparison.Ordinal) && string.Equals(item.Route, "/participate", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "telemetry_rollup", StringComparison.Ordinal) && string.Equals(item.Route, "/progress", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "retention_clocks", StringComparison.Ordinal) && string.Equals(item.Route, "/privacy", StringComparison.Ordinal));
            Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "case_status_followthrough", StringComparison.Ordinal) && item.Route.Contains("/account/support/", StringComparison.Ordinal));
            string publicProjectionText = JsonSerializer.Serialize(bundle, new JsonSerializerOptions(JsonSerializerDefaults.Web));
            Assert.Contains("account support page", publicProjectionText, StringComparison.Ordinal);
            Assert.Contains("public feedback path", publicProjectionText, StringComparison.Ordinal);
            Assert.DoesNotContain("/contact#support-intake", publicProjectionText, StringComparison.Ordinal);
            Assert.DoesNotContain("Open support intake", publicProjectionText, StringComparison.Ordinal);
            Assert.DoesNotContain("support account rail", publicProjectionText, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("feedback lane", publicProjectionText, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("governed Participate lane", publicProjectionText, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("governed feedback", publicProjectionText, StringComparison.OrdinalIgnoreCase);
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
