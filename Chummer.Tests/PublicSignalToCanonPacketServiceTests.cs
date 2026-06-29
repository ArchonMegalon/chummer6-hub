using System.Text.Json;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicSignalToCanonPacketServiceTests
{
    [Fact]
    public void PublicSignalPacketsCoverFeedbackRoadmapChangelogSupportAndSignalIntake()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "public-signal-packets", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            File.WriteAllText(
                Path.Combine(tempRoot, "releases.json"),
                JsonSerializer.Serialize(new PublicReleaseManifestDto(
                    Version: "0.8.3",
                    Channel: "preview",
                    PublishedAt: DateTimeOffset.UtcNow,
                    Downloads:
                    [
                        new PublicReleaseArtifactDto(
                            Id: "avalonia-linux-x64-installer",
                            Platform: "linux",
                            Url: "https://example.invalid/downloads/avalonia-linux-x64-installer.exe",
                            Sha256: new string('b', 64),
                            SizeBytes: 1024,
                            Head: "avalonia",
                            PlatformId: "linux",
                            Arch: "x64",
                            Kind: "installer",
                            FileName: "avalonia-linux-x64-installer.exe",
                            InstallAccessClass: "claimed")
                    ],
                    SupportabilityState: "watch",
                    SupportabilitySummary: "Public trust and support posture stay visible on the hosted preview shelf."),
                new JsonSerializerOptions(JsonSerializerDefaults.Web)),
                encoding: System.Text.Encoding.UTF8);

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = tempRoot
                })
                .Build();

            PublicSignalToCanonPacketService service = new(new PublicReleaseManifestService(configuration));
            SignalToCanonPacketBundle bundle = service.Build(new SupportCaseProjection(
                CaseId: "case-public-001",
                ClusterKey: "public-cluster",
                Kind: "feedback",
                Status: "new",
                Title: "Public feedback trail",
                Summary: "Need a governed first-party intake trail.",
                Detail: "Public support route should stay first-party.",
                CandidateOwnerRepo: "chummer6-hub",
                DesignImpactSuspected: true,
                CreatedAtUtc: DateTimeOffset.UtcNow.AddDays(-1),
                UpdatedAtUtc: DateTimeOffset.UtcNow,
                Source: "public_web"));

            Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "feedback", StringComparison.Ordinal) && string.Equals(item.DestinationRoute, "/participate", StringComparison.Ordinal));
            Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "roadmap", StringComparison.Ordinal) && string.Equals(item.DestinationRoute, "/horizons?source=roadmap#public-roadmap-projection", StringComparison.Ordinal));
            Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "changelog", StringComparison.Ordinal) && string.Equals(item.DestinationRoute, "/now?source=changelog#public-shipped-closeout", StringComparison.Ordinal));
            Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "support", StringComparison.Ordinal) && string.Equals(item.CaseId, "case-public-001", StringComparison.Ordinal));
            Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "signal_intake", StringComparison.Ordinal) && string.Equals(item.Route, "/participate", StringComparison.Ordinal));
            Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "productlift_signal", StringComparison.Ordinal) && string.Equals(item.SourceClassification, "public_feedback_signal", StringComparison.Ordinal));
            Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "katteb_signal", StringComparison.Ordinal) && string.Equals(item.SourceClassification, "content_improvement", StringComparison.Ordinal));
            Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "clickrank_signal", StringComparison.Ordinal) && string.Equals(item.SourceClassification, "site_visibility_audit", StringComparison.Ordinal));
            Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "metasurvey_signal", StringComparison.Ordinal) && string.Equals(item.SourceClassification, "quant_validation", StringComparison.Ordinal));
            Assert.Contains(bundle.Packets, item => item.UpstreamPatchRequirement.Contains("source", StringComparison.OrdinalIgnoreCase));
            Assert.Contains(bundle.Packets, item => item.NoChangeRationalePolicy.Contains("required", StringComparison.OrdinalIgnoreCase));
            Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "productlift_signal", StringComparison.Ordinal) && item.JourneyProofEventRefs.Any(refItem => string.Equals(refItem.EventKey, "productlift_idea_clustered", StringComparison.Ordinal)));
            Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "changelog", StringComparison.Ordinal) && item.JourneyProofEventRefs.Any(refItem => string.Equals(refItem.EventKey, "voter_notified", StringComparison.Ordinal)));
            Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "metasurvey_signal", StringComparison.Ordinal) && item.JourneyProofEventRefs.Any(refItem => string.Equals(refItem.EventKey, "karma_demand_packet_created", StringComparison.Ordinal)));
            Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "signal_intake", StringComparison.Ordinal) && item.JourneyProofEventRefs.Count >= 2);
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
