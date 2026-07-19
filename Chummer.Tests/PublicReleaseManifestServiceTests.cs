using System.Diagnostics;
using System.Net;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicReleaseManifestServiceTests
{
    [Fact]
    public void ConfiguredInvalidCurrentProjectionPreservesReleaseFreeze()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: true);
        fixture.WriteFlagshipReadiness(status: "pass");
        string missingSnapshotRoot = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));

        PublicReleaseManifestDto manifest = fixture.CreateService(
            additionalSettings: new Dictionary<string, string?>
            {
                [PublicProjectionSnapshotService.SnapshotRootConfigurationKey] = missingSnapshotRoot,
                [PublicProjectionSnapshotService.SnapshotRequiredConfigurationKey] = "true"
            }).LoadManifest();

        Assert.Equal("review_required", manifest.ProofStatus);
        Assert.Equal("review_required", manifest.SupportabilityState);
        Assert.DoesNotContain(
            manifest.RolloutState ?? string.Empty,
            new[] { "public_stable", "stable", "promoted_preview", "live" });
        Assert.Contains("public projection", manifest.SupportabilitySummary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CachedManifestReauthenticatesCurrentProjectionBeforeReuse()
    {
        using var fixture = new PublicReleaseManifestFixture();
        using var projection =
            new PublicProjectionSnapshotServiceTests.PublicProjectionFixture();
        fixture.WriteRegistryManifest(includeProof: true);
        fixture.WriteFlagshipReadiness(status: "pass");
        projection.PublishValidSnapshot();
        PublicReleaseManifestService service = fixture.CreateService(
            additionalSettings: new Dictionary<string, string?>
            {
                [PublicProjectionSnapshotService.SnapshotRootConfigurationKey] =
                    projection.SnapshotRoot,
                [PublicProjectionSnapshotService.SnapshotRequiredConfigurationKey] = "true"
            });

        PublicReleaseManifestDto authenticated = service.LoadManifest();
        File.AppendAllText(projection.CurrentLocalProofPath, "tamper");
        PublicReleaseManifestDto blocked = service.LoadManifest();

        Assert.DoesNotContain(
            "public projection",
            authenticated.SupportabilitySummary ?? string.Empty,
            StringComparison.OrdinalIgnoreCase);
        Assert.Equal("review_required", blocked.ProofStatus);
        Assert.Contains(
            "public projection",
            blocked.SupportabilitySummary,
            StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LoadManifestUsesLocalHubProofWhenRegistryProofIsAbsent()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: false);
        fixture.WriteLocalProof("passed", "http://127.0.0.1:8091");

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("passed", manifest.ProofStatus);
        Assert.Equal("http://127.0.0.1:8091", manifest.ProofBaseUrl);
        Assert.NotNull(manifest.ProofGeneratedAt);
        Assert.Equal(["install_claim_restore_continue", "build_explain_publish"], manifest.ProofJourneys);
        Assert.Equal(["/downloads/install/avalonia-linux-x64-installer", "/account/support"], manifest.ProofRoutes);
    }

    [Fact]
    public void LoadManifestPreservesWindowsBootstrapPayloadMetadata()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(
            version: "run-bootstrap",
            downloads:
            [
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-win-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "windows",
                    ["rid"] = "win-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Windows X64 Installer",
                    ["fileName"] = "chummer-avalonia-win-x64-installer.exe",
                    ["downloadUrl"] = "https://chummer.run/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    ["sha256"] = new string('a', 64),
                    ["sizeBytes"] = 51856809L,
                    ["installAccessClass"] = "open_public",
                    ["installerMode"] = "bootstrap",
                    ["payloadFileName"] = "chummer-avalonia-win-x64-payload.zip",
                    ["payloadDownloadUrl"] = "https://chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip",
                    ["payloadSha256"] = new string('b', 64),
                    ["payloadSizeBytes"] = 47152146L
                }
            ]);

        var manifest = fixture.CreateService().LoadManifest();
        var windows = Assert.Single(manifest.Downloads);

        Assert.Equal("bootstrap", windows.InstallerMode);
        Assert.Equal("chummer-avalonia-win-x64-payload.zip", windows.PayloadFileName);
        Assert.Equal("https://chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip", windows.PayloadDownloadUrl);
        Assert.Equal(new string('b', 64), windows.PayloadSha256);
        Assert.Equal(47152146L, windows.PayloadSizeBytes);
    }

    [Fact]
    public void LoadManifestUsesPublicVersionAsTheHumanFacingDisplayVersion()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-20260623-102621",
            ["publicVersion"] = "0.0.0.1",
            ["publishedAt"] = "2026-06-23T10:26:21Z",
            ["status"] = "published",
            ["rolloutState"] = "public_stable",
            ["supportabilityState"] = "gold_supported",
            ["publicTrustMetrics"] = BuildFreshProofTrustMetrics("2026-06-23T10:26:21Z"),
            ["releaseProof"] = BuildFreshReleaseProof("2026-06-23T10:26:21Z"),
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = new string('a', 64),
                    ["sizeBytes"] = 1234L,
                    ["installAccessClass"] = "open_public"
                }
            }
        });
        fixture.WriteFlagshipReadiness(status: "pass");

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("run-20260623-102621", manifest.Version);
        Assert.Equal("0.0.0.1", manifest.PublicVersion);
        Assert.Equal("0.0.0.1", manifest.DisplayVersion);
        Assert.Equal("Current public build", manifest.DisplayBuildLabel);
    }

    [Fact]
    public void LoadManifestProjectsCanonicalChannelWhenChannelIdIsAbsent()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channel"] = "preview",
            ["version"] = "run-channel-only",
            ["publishedAt"] = "2026-07-15T12:00:00Z",
            ["status"] = "published",
            ["artifacts"] = Array.Empty<object>()
        });

        PublicReleaseManifestDto manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("preview", manifest.Channel);
        Assert.Equal("run-channel-only", manifest.Version);
    }

    [Fact]
    public void PublicReleaseManifestDisplayLabelsDoNotClaimStableReleaseWhenSupportabilityIsNotGold()
    {
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260704-170602",
            Channel: "public_stable",
            PublishedAt: new DateTimeOffset(2026, 7, 4, 17, 6, 2, TimeSpan.Zero),
            Downloads: [],
            Status: "published",
            RolloutState: "public_stable",
            SupportabilityState: "preview_supported");

        Assert.Equal("run-20260704-170602", manifest.DisplayVersion);
        Assert.Equal("Build run-20260704-170602", manifest.DisplayBuildLabel);
        Assert.Equal("Current release build", manifest.DisplayChannelLabel);
    }

    [Fact]
    public void PublicReleaseManifestDisplayVersionIgnoresPublicVersionWhenSupportabilityIsNotGold()
    {
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260704-170602",
            Channel: "public_stable",
            PublishedAt: new DateTimeOffset(2026, 7, 4, 17, 6, 2, TimeSpan.Zero),
            Downloads: [],
            Status: "published",
            RolloutState: "public_stable",
            SupportabilityState: "preview_supported",
            PublicVersion: "0.0.0.1");

        Assert.Equal("run-20260704-170602", manifest.DisplayVersion);
    }

    [Fact]
    public void PublicReleaseManifestDisplayLabelsDoNotClaimStableReleaseWhenStatusIsNotPublished()
    {
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260704-170602",
            Channel: "stable",
            PublishedAt: new DateTimeOffset(2026, 7, 4, 17, 6, 2, TimeSpan.Zero),
            Downloads: [],
            Status: "draft",
            RolloutState: "public_stable",
            SupportabilityState: "gold_supported");

        Assert.Equal("run-20260704-170602", manifest.DisplayVersion);
        Assert.Equal("Build run-20260704-170602", manifest.DisplayBuildLabel);
        Assert.Equal("Current release build", manifest.DisplayChannelLabel);
    }

    [Fact]
    public void PublicReleaseManifestDisplayVersionIgnoresPublicVersionWhenStatusIsNotPublished()
    {
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260704-170602",
            Channel: "stable",
            PublishedAt: new DateTimeOffset(2026, 7, 4, 17, 6, 2, TimeSpan.Zero),
            Downloads: [],
            Status: "draft",
            RolloutState: "public_stable",
            SupportabilityState: "gold_supported",
            PublicVersion: "0.0.0.1");

        Assert.Equal("run-20260704-170602", manifest.DisplayVersion);
    }

    [Fact]
    public void LoadManifestUsesRepoLocalPortalDownloadsWhenNoDownloadsRootIsConfigured()
    {
        string root = Path.Combine(Path.GetTempPath(), "public-release-default-root-tests", Guid.NewGuid().ToString("N"));
        try
        {
            string downloadsRoot = Path.Combine(root, "Chummer.Portal", "downloads");
            Directory.CreateDirectory(downloadsRoot);
            File.WriteAllText(
                Path.Combine(downloadsRoot, "releases.json"),
                JsonSerializer.Serialize(
                    new PublicReleaseManifestDto(
                        Version: "repo-local-preview",
                        Channel: "preview",
                        PublishedAt: new DateTimeOffset(2026, 6, 2, 12, 0, 0, TimeSpan.Zero),
                        Downloads:
                        [
                            new PublicReleaseArtifactDto(
                                Id: "repo-local-avalonia-osx-arm64",
                                Platform: "osx-arm64",
                                Url: "/downloads/files/chummer-avalonia-osx-arm64.tar.gz",
                                Sha256: new string('a', 64),
                                SizeBytes: 1234)
                        ],
                        Source: "repo-local",
                        Status: "published",
                        Message: "Repo-local portal bundle is available.",
                        HasFallbackSource: false),
                    new JsonSerializerOptions(JsonSerializerDefaults.Web)));

            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = root
                })
                .Build();

            var manifest = new PublicReleaseManifestService(configuration).LoadManifest();

            Assert.Equal("repo-local-preview", manifest.Version);
            Assert.Contains(manifest.Downloads, item => string.Equals(item.Id, "repo-local-avalonia-osx-arm64", StringComparison.Ordinal));
        }
        finally
        {
            if (Directory.Exists(root))
            {
                Directory.Delete(root, recursive: true);
            }
        }
    }

    [Fact]
    public void LoadManifestCachesRuntimeRegistryFetchAcrossRepeatedCalls()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: false);
        string runtimePayload = JsonSerializer.Serialize(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-runtime-cache",
            ["publishedAt"] = "2026-06-28T00:00:00Z",
            ["status"] = "published",
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = new string('a', 64),
                    ["sizeBytes"] = 1234L,
                    ["installAccessClass"] = "open_public"
                }
            }
        });

        var handler = new CountingStaticJsonHandler(runtimePayload);
        var service = fixture.CreateService(
            httpClient: new HttpClient(handler),
            includeRuntimeUrl: true);

        PublicReleaseManifestDto first = service.LoadManifest();
        PublicReleaseManifestDto second = service.LoadManifest();

        Assert.Equal("run-runtime-cache", first.Version);
        Assert.Equal("run-runtime-cache", second.Version);
        Assert.Equal(1, handler.CallCount);
    }

    [Fact]
    public void LoadManifestFailsFastWhenRuntimeRegistryUrlStallsAndFallsBackToLocalManifest()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-local-fallback",
            ["publishedAt"] = "2026-06-28T00:00:00Z",
            ["status"] = "published",
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = new string('a', 64),
                    ["sizeBytes"] = 1234L,
                    ["installAccessClass"] = "open_public"
                }
            }
        });

        var service = fixture.CreateService(
            httpClient: new HttpClient(new SlowJsonHandler(TimeSpan.FromSeconds(5))),
            includeRuntimeUrl: true);
        var stopwatch = Stopwatch.StartNew();

        PublicReleaseManifestDto manifest = service.LoadManifest();

        stopwatch.Stop();
        Assert.Equal("run-local-fallback", manifest.Version);
        Assert.True(stopwatch.Elapsed < TimeSpan.FromSeconds(2), $"runtime registry fallback should fail fast, but took {stopwatch.Elapsed}.");
    }

    [Fact]
    public void LoadManifestPrefersLocalRegistryManifestInDevelopmentWithoutCallingRuntimeUrl()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-local-development",
            ["publishedAt"] = "2026-06-28T00:00:00Z",
            ["status"] = "published",
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = new string('a', 64),
                    ["sizeBytes"] = 1234L,
                    ["installAccessClass"] = "open_public"
                }
            }
        });

        var handler = new CountingStaticJsonHandler("{}");
        var service = fixture.CreateService(
            httpClient: new HttpClient(handler),
            includeRuntimeUrl: true,
            additionalSettings: new Dictionary<string, string?>
            {
                ["ASPNETCORE_ENVIRONMENT"] = "Development"
            });

        PublicReleaseManifestDto manifest = service.LoadManifest();

        Assert.Equal("run-local-development", manifest.Version);
        Assert.Equal(0, handler.CallCount);
    }

    [Fact]
    public void LoadManifestPreservesRegistryBoundaryCoverageFromRegistryManifest()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "preview",
            ["version"] = "run-boundary-smoke",
            ["publishedAt"] = "2026-06-02T12:00:00Z",
            ["status"] = "published",
            ["registryBoundaryCoverage"] = new Dictionary<string, object?>
            {
                ["compatibility"] = new Dictionary<string, object?>
                {
                    ["compatibleArtifactCount"] = 4,
                    ["unknownArtifactCount"] = 0
                }
            },
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-osx-arm64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "macos",
                    ["rid"] = "osx-arm64",
                    ["arch"] = "arm64",
                    ["kind"] = "dmg",
                    ["fileName"] = "chummer-avalonia-osx-arm64-installer.dmg",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    ["sha256"] = new string('b', 64),
                    ["sizeBytes"] = 1234L
                }
            }
        });

        var manifest = fixture.CreateService().LoadManifest();

        JsonElement coverage = Assert.IsType<JsonElement>(manifest.RegistryBoundaryCoverage);
        JsonElement compatibility = coverage.GetProperty("compatibility");
        Assert.Equal(4, compatibility.GetProperty("compatibleArtifactCount").GetInt32());
        Assert.Equal(0, compatibility.GetProperty("unknownArtifactCount").GetInt32());
    }

    [Fact]
    public void LoadManifestFailsClosedWhenDesktopClientCoverageIsMissing()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: false);
        fixture.WriteLocalProof("passed", "http://127.0.0.1:8091");
        fixture.WriteFlagshipReadiness(status: "fail", missingCoverageKeys: ["desktop_client"]);

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("review_required", manifest.SupportabilityState);
        Assert.Equal("desktop_polish_needed", manifest.RolloutState);
        Assert.Contains("desktop_client", manifest.SupportabilitySummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("parity-sensitive routes", manifest.KnownIssueSummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Chummer support", manifest.FixAvailabilitySummary, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("passed", manifest.ProofStatus);
    }

    [Fact]
    public void LoadManifestFailsClosedWhenDesktopClientCoverageIsOnlyWarningScoped()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: false);
        fixture.WriteLocalProof("passed", "http://127.0.0.1:8091");
        fixture.WriteFlagshipReadiness(status: "fail", warningCoverageKeys: ["desktop_client"]);

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("review_required", manifest.SupportabilityState);
        Assert.Equal("desktop_polish_needed", manifest.RolloutState);
        Assert.Contains("desktop_client", manifest.SupportabilitySummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Desktop polish is not current yet", manifest.KnownIssueSummary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LoadManifestFailsClosedWhenPassingReadinessStillCarriesBlockedJourneyEvidence()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: false);
        fixture.WriteLocalProof("passed", "http://127.0.0.1:8091");
        fixture.WriteFlagshipReadiness(status: "pass", includeBlockedJourneyEvidence: true);

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("review_required", manifest.SupportabilityState);
        Assert.Equal("readiness_review_required", manifest.RolloutState);
        Assert.Contains("flagship journey blockers", manifest.SupportabilitySummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("broad ready claims", manifest.RolloutReason, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("broad ready claims", manifest.KnownIssueSummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("blocked flagship journeys", manifest.FixAvailabilitySummary, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("passed", manifest.ProofStatus);
    }

    [Fact]
    public void LoadManifestDoesNotOverrideRegistryProof()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: true);
        fixture.WriteLocalProof("passed", "http://127.0.0.1:8091");

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("registry-passed", manifest.ProofStatus);
        Assert.Equal("https://registry.chummer.run", manifest.ProofBaseUrl);
        Assert.Equal(["registry_journey"], manifest.ProofJourneys);
        Assert.Equal(["/downloads"], manifest.ProofRoutes);
    }

    [Fact]
    public void LoadManifestPreservesGoldSupportedCanonicalShelfWhenFlagshipReadinessIsCurrent()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-20260601-070650",
            ["publishedAt"] = "2026-06-05T05:05:03Z",
            ["status"] = "published",
            ["supportabilityState"] = "gold_supported",
            ["supportabilitySummary"] = "Current shelf is gold-supported.",
            ["knownIssueSummary"] = "Current release status is green.",
            ["publicTrustMetrics"] = BuildFreshProofTrustMetrics("2026-06-05T05:05:03Z"),
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-win-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "windows",
                    ["rid"] = "win-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Windows X64 Installer",
                    ["fileName"] = "chummer-avalonia-win-x64-installer.exe",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    ["sha256"] = "abc123",
                    ["sizeBytes"] = 123456789L,
                    ["installAccessClass"] = "account_required"
                }
            },
            ["releaseProof"] = BuildFreshReleaseProof("2026-06-05T05:05:03Z")
        });
        fixture.WriteFlagshipReadiness(status: "pass");

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("gold_supported", manifest.SupportabilityState);
        Assert.DoesNotContain("review-required", manifest.SupportabilitySummary ?? string.Empty, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("review-required", manifest.KnownIssueSummary ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LoadManifestDowngradesGoldSupportabilityWhenFinalGoldIsNotGreen()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-20260601-070650",
            ["publishedAt"] = "2026-06-05T05:05:03Z",
            ["status"] = "published",
            ["rolloutState"] = "public_stable",
            ["supportabilityState"] = "gold_supported",
            ["supportabilitySummary"] = "Current shelf is gold-supported.",
            ["knownIssueSummary"] = "Current release status is green.",
            ["publicTrustMetrics"] = BuildFreshProofTrustMetrics("2026-06-05T05:05:03Z"),
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = "linux123",
                    ["sizeBytes"] = 123456789L,
                    ["installAccessClass"] = "account_required"
                },
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-win-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "windows",
                    ["rid"] = "win-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Windows X64 Installer",
                    ["fileName"] = "chummer-avalonia-win-x64-installer.exe",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    ["sha256"] = "abc123",
                    ["sizeBytes"] = 123456789L,
                    ["installAccessClass"] = "account_required"
                },
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-osx-arm64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "macos",
                    ["rid"] = "osx-arm64",
                    ["arch"] = "arm64",
                    ["kind"] = "dmg",
                    ["platformLabel"] = "Avalonia Desktop macOS ARM64 Installer",
                    ["fileName"] = "chummer-avalonia-osx-arm64-installer.dmg",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    ["sha256"] = "mac123",
                    ["sizeBytes"] = 123456789L,
                    ["installAccessClass"] = "account_required"
                }
            },
            ["releaseProof"] = BuildFreshReleaseProof("2026-06-05T05:05:03Z")
        });
        fixture.WriteFlagshipReadiness(status: "pass");
        fixture.WriteFinalGoldReadiness(
            status: "fail",
            verdict: "NOT_GOLD",
            failures: ["windows_installer_visual_audit failed", "release_ready failed"]);

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("release_review_required", manifest.RolloutState);
        Assert.Equal("review_required", manifest.SupportabilityState);
        Assert.Contains("flagship readiness claims stay blocked", manifest.RolloutReason, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("native Windows installer proof", manifest.SupportabilitySummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("release readiness checks", manifest.SupportabilitySummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Final release checks are not current yet", manifest.KnownIssueSummary, StringComparison.Ordinal);
        Assert.DoesNotContain("gold-supported", manifest.SupportabilitySummary ?? string.Empty, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("green", manifest.KnownIssueSummary ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LoadManifestPreservesExistingCoverageIncompleteRolloutWhenFinalGoldIsNotGreen()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-20260704-170602",
            ["publishedAt"] = "2026-07-04T17:06:02Z",
            ["status"] = "published",
            ["rolloutState"] = "coverage_incomplete",
            ["rolloutReason"] = "The current release is published, but a few desktop combinations are still catching up: avalonia windows win-x64.",
            ["supportabilityState"] = "review_required",
            ["supportabilitySummary"] = "This release is live. Some desktop combinations are still catching up: avalonia windows win-x64.",
            ["knownIssueSummary"] = "A few desktop downloads stay hidden until those combinations are current again.",
            ["fixAvailabilitySummary"] = "Check the live download page again after the updated build lands.",
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = "linux123",
                    ["sizeBytes"] = 123456789L,
                    ["installAccessClass"] = "account_required"
                }
            }
        });
        fixture.WriteFlagshipReadiness(status: "pass");
        fixture.WriteFinalGoldReadiness(
            status: "fail",
            verdict: "NOT_GOLD",
            failures: ["windows_installer_visual_audit failed", "release_ready failed"]);

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("coverage_incomplete", manifest.RolloutState);
        Assert.Contains("desktop combinations are still catching up", manifest.RolloutReason, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("flagship readiness claims stay blocked", manifest.RolloutReason, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("native Windows installer proof", manifest.SupportabilitySummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("release readiness checks", manifest.SupportabilitySummary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LoadManifestPreservesExistingPublicReleaseReviewRequiredRolloutWhenFinalGoldIsNotGreen()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-20260704-170602",
            ["publishedAt"] = "2026-07-04T17:06:02Z",
            ["status"] = "published",
            ["rolloutState"] = "public_release_review_required",
            ["rolloutReason"] = "Current shelf is published, but release posture stays review-required because flagship launch blockers remain.",
            ["supportabilityState"] = "review_required",
            ["supportabilitySummary"] = "Treat the current release as review-required because flagship launch blockers remain.",
            ["knownIssueSummary"] = "Known issue: review-required release posture is active until launch blockers clear.",
            ["fixAvailabilitySummary"] = "Only send fixed notices after launch blockers clear.",
            ["publicTrustMetrics"] = BuildFreshProofTrustMetrics("2026-07-04T17:06:02Z"),
            ["releaseProof"] = BuildFreshReleaseProof("2026-07-04T17:06:02Z"),
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = "linux123",
                    ["sizeBytes"] = 123456789L,
                    ["installAccessClass"] = "account_required"
                }
            }
        });
        fixture.WriteFlagshipReadiness(status: "pass");
        fixture.WriteFinalGoldReadiness(
            status: "fail",
            verdict: "NOT_GOLD",
            failures: ["windows_installer_visual_audit failed", "release_ready failed"]);

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("public_release_review_required", manifest.RolloutState);
        Assert.Equal("review_required", manifest.SupportabilityState);
        Assert.Contains("flagship readiness claims stay blocked", manifest.RolloutReason, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("native Windows installer proof", manifest.SupportabilitySummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("release readiness checks", manifest.SupportabilitySummary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LoadManifestPreservesGoldSupportedCanonicalShelfWhenCanonicalProofIsPassed()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-20260601-070650",
            ["publishedAt"] = "2026-06-05T05:05:03Z",
            ["status"] = "published",
            ["supportabilityState"] = "gold_supported",
            ["supportabilitySummary"] = "Current shelf is gold-supported.",
            ["knownIssueSummary"] = "Current release status is green.",
            ["publicTrustMetrics"] = BuildFreshProofTrustMetrics("2026-06-05T05:05:03Z"),
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-win-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "windows",
                    ["rid"] = "win-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Windows X64 Installer",
                    ["fileName"] = "chummer-avalonia-win-x64-installer.exe",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    ["sha256"] = "abc123",
                    ["sizeBytes"] = 123456789L,
                    ["installAccessClass"] = "account_required"
                }
            },
            ["releaseProof"] = BuildFreshReleaseProof("2026-06-05T05:05:03Z")
        });

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("gold_supported", manifest.SupportabilityState);
        Assert.DoesNotContain("review-required", manifest.SupportabilitySummary ?? string.Empty, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("review-required", manifest.KnownIssueSummary ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LoadManifestPreservesPromotedGoldSupportabilityWhenOnlyClosureReceiptsAreStillConverging()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-20260704-170602",
            ["publishedAt"] = "2026-07-04T17:06:02Z",
            ["status"] = "published",
            ["rolloutState"] = "public_stable",
            ["supportabilityState"] = "gold_supported",
            ["supportabilitySummary"] = "Current shelf is gold-supported.",
            ["knownIssueSummary"] = "Current release status is green.",
            ["publicTrustMetrics"] = BuildFreshProofTrustMetrics("2026-07-04T17:06:02Z"),
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-win-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "windows",
                    ["rid"] = "win-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Windows X64 Installer",
                    ["fileName"] = "chummer-avalonia-win-x64-installer.exe",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    ["sha256"] = "abc123",
                    ["sizeBytes"] = 123456789L,
                    ["installAccessClass"] = "account_required"
                }
            },
            ["releaseProof"] = BuildFreshReleaseProof("2026-07-04T17:06:02Z")
        });
        fixture.WriteFlagshipReadinessRaw(new Dictionary<string, object?>
        {
            ["contract_name"] = "fleet.flagship_product_readiness",
            ["status"] = "fail",
            ["completion_audit"] = new Dictionary<string, object?>
            {
                ["reason"] = "Launch-critical nested blockers remain."
            },
            ["flagship_readiness_audit"] = new Dictionary<string, object?>
            {
                ["reason"] = "Launch blockers: final gold janitor state is 'fail', final gold janitor verdict is 'NOT_GOLD'.",
                ["warning_coverage_keys"] = Array.Empty<string>(),
                ["scoped_warning_coverage_keys"] = Array.Empty<string>(),
                ["missing_coverage_keys"] = Array.Empty<string>(),
                ["scoped_missing_coverage_keys"] = Array.Empty<string>()
            },
            ["gate_status_override"] = new Dictionary<string, object?>
            {
                ["reason"] = "Launch-critical nested blockers remain.",
                ["effective_reason"] = "Launch blockers: final gold janitor state is 'fail', final gold janitor verdict is 'NOT_GOLD'.",
                ["launch_critical_nested_blockers"] = new[]
                {
                    "final gold janitor state is 'fail'",
                    "final gold janitor verdict is 'NOT_GOLD'"
                },
                ["coverage_gap_keys"] = Array.Empty<string>(),
                ["scoped_coverage_gap_keys"] = Array.Empty<string>()
            }
        });
        fixture.WriteFinalGoldReadiness(
            status: "fail",
            verdict: "NOT_GOLD",
            failures:
            [
                "public_edge_postdeploy_gate semantic proof failed",
                "operator_release_dashboard failed",
                "operator_release_dashboard has failing required checks",
                "release_ready failed"
            ]);

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("gold_supported", manifest.SupportabilityState);
        Assert.Equal("public_stable", manifest.RolloutState);
        Assert.DoesNotContain("review-required", manifest.SupportabilitySummary ?? string.Empty, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("flagship readiness claims stay blocked", manifest.RolloutReason ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LoadManifestPreservesRegistryPublicTrustMetricsFlagshipReadinessFields()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-20260516-210955",
            ["publishedAt"] = "2026-05-16T21:09:55Z",
            ["generatedAt"] = "2026-05-16T21:11:00Z",
            ["status"] = "published",
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = "abc123",
                    ["sizeBytes"] = 123456789L
                }
            },
            ["publicTrustMetrics"] = new Dictionary<string, object?>
            {
                ["proofFreshness"] = new Dictionary<string, object?>
                {
                    ["status"] = "stale",
                    ["flagshipReadinessGeneratedAt"] = "2026-05-11T13:48:30Z",
                    ["flagshipReadinessAgeSeconds"] = 86400,
                    ["flagshipReadinessMaxAgeSeconds"] = 604800,
                    ["flagshipReadinessStatus"] = "pass",
                    ["flagshipReadinessCoverageGapKeys"] = new[] { "desktop_client" },
                    ["flagshipDesktopClientReady"] = false,
                    ["flagshipReadinessReason"] = "desktop client coverage is still missing from the current flagship readiness proof"
                }
            }
        });

        var manifest = fixture.CreateService().LoadManifest();

        Assert.True(manifest.PublicTrustMetrics.HasValue);
        JsonElement proofFreshness = manifest.PublicTrustMetrics!.Value.GetProperty("proofFreshness");
        Assert.Equal("2026-05-11T13:48:30Z", proofFreshness.GetProperty("flagshipReadinessGeneratedAt").GetString());
        Assert.Equal(86400, proofFreshness.GetProperty("flagshipReadinessAgeSeconds").GetInt32());
        Assert.Equal(604800, proofFreshness.GetProperty("flagshipReadinessMaxAgeSeconds").GetInt32());
        Assert.Equal("pass", proofFreshness.GetProperty("flagshipReadinessStatus").GetString());
        Assert.False(proofFreshness.GetProperty("flagshipDesktopClientReady").GetBoolean());
        Assert.Equal(
            "desktop client coverage is still missing from the current flagship readiness proof",
            proofFreshness.GetProperty("flagshipReadinessReason").GetString());
        Assert.Equal("desktop_client", proofFreshness.GetProperty("flagshipReadinessCoverageGapKeys")[0].GetString());
    }

    [Theory]
    [InlineData("stale")]
    [InlineData("missing")]
    [InlineData("")]
    [InlineData("future_status")]
    public void ServedManifestFloorMakesEveryNonFreshProofReviewRequiredWithoutMutatingSource(string proofFreshnessStatus)
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(BuildOptimisticProofFreshnessManifest(proofFreshnessStatus));
        byte[] sourceBytes = fixture.ReadRegistryManifestBytes();
        var service = fixture.CreateService();

        string canonicalJson = service.LoadCanonicalManifestJson()!;
        using JsonDocument canonical = JsonDocument.Parse(canonicalJson);
        JsonElement root = canonical.RootElement;

        Assert.Equal("run-20260713-123603", root.GetProperty("version").GetString());
        Assert.Equal("2026-07-13T12:38:14Z", root.GetProperty("publishedAt").GetString());
        JsonElement artifact = Assert.Single(root.GetProperty("artifacts").EnumerateArray());
        Assert.Equal("avalonia-osx-arm64-installer", artifact.GetProperty("artifactId").GetString());
        Assert.Equal("artifact-sha", artifact.GetProperty("sha256").GetString());
        Assert.Equal("public_release_review_required", root.GetProperty("rolloutState").GetString());
        Assert.Contains("stale or incomplete proof receipts", root.GetProperty("rolloutReason").GetString(), StringComparison.Ordinal);
        Assert.Equal("review_required", root.GetProperty("supportabilityState").GetString());
        Assert.Contains("review-required", root.GetProperty("supportabilitySummary").GetString(), StringComparison.Ordinal);

        JsonElement publicTrustMetrics = root.GetProperty("publicTrustMetrics");
        Assert.Equal(
            string.IsNullOrWhiteSpace(proofFreshnessStatus)
            || string.Equals(proofFreshnessStatus, "missing", StringComparison.OrdinalIgnoreCase)
                ? "missing"
                : "stale",
            publicTrustMetrics.GetProperty("proofFreshness").GetProperty("status").GetString());
        JsonElement publicReleaseChannel = publicTrustMetrics.GetProperty("releaseChannel");
        Assert.Equal("public_release_review_required", publicReleaseChannel.GetProperty("rolloutState").GetString());
        Assert.Equal("review_required", publicReleaseChannel.GetProperty("supportabilityState").GetString());
        Assert.Equal("blocked", publicReleaseChannel.GetProperty("posture").GetString());
        Assert.Contains("review-required", publicReleaseChannel.GetProperty("summary").GetString(), StringComparison.Ordinal);

        JsonElement registryReleaseChannel = root
            .GetProperty("registryBoundaryCoverage")
            .GetProperty("releaseChannel");
        Assert.Equal("public_release_review_required", registryReleaseChannel.GetProperty("rolloutState").GetString());
        Assert.Equal("review_required", registryReleaseChannel.GetProperty("supportabilityState").GetString());
        Assert.Equal("blocked", registryReleaseChannel.GetProperty("publicTrustPosture").GetString());
        Assert.Contains("review-required", registryReleaseChannel.GetProperty("summary").GetString(), StringComparison.Ordinal);

        PublicReleaseManifestDto pageManifest = service.LoadManifest();
        Assert.Equal("run-20260713-123603", pageManifest.Version);
        Assert.Equal(DateTimeOffset.Parse("2026-07-13T12:38:14Z"), pageManifest.PublishedAt);
        Assert.Single(pageManifest.Downloads);
        Assert.Equal("public_release_review_required", pageManifest.RolloutState);
        Assert.Equal("review_required", pageManifest.SupportabilityState);
        Assert.True(pageManifest.PublicTrustMetrics.HasValue);
        Assert.Equal(
            "review_required",
            pageManifest.PublicTrustMetrics.Value
                .GetProperty("releaseChannel")
                .GetProperty("supportabilityState")
                .GetString());
        Assert.Equal(
            "blocked",
            pageManifest.PublicTrustMetrics.Value
                .GetProperty("releaseChannel")
                .GetProperty("posture")
                .GetString());
        Assert.True(pageManifest.RegistryBoundaryCoverage.HasValue);
        Assert.Equal(
            "review_required",
            pageManifest.RegistryBoundaryCoverage.Value
                .GetProperty("releaseChannel")
                .GetProperty("supportabilityState")
                .GetString());
        Assert.Equal(
            "blocked",
            pageManifest.RegistryBoundaryCoverage.Value
                .GetProperty("releaseChannel")
                .GetProperty("publicTrustPosture")
                .GetString());
        Assert.Equal(sourceBytes, fixture.ReadRegistryManifestBytes());
    }

    [Fact]
    public void ServedManifestFloorTreatsAbsentProofFreshnessAsMissingWithoutMutatingSource()
    {
        using var fixture = new PublicReleaseManifestFixture();
        Dictionary<string, object?> payload = BuildOptimisticProofFreshnessManifest("fresh");
        var publicTrustMetrics = Assert.IsType<Dictionary<string, object?>>(payload["publicTrustMetrics"]);
        publicTrustMetrics.Remove("proofFreshness");
        fixture.WriteRegistryManifestRaw(payload);
        byte[] sourceBytes = fixture.ReadRegistryManifestBytes();

        using JsonDocument canonical = JsonDocument.Parse(fixture.CreateService().LoadCanonicalManifestJson()!);
        JsonElement root = canonical.RootElement;

        Assert.Equal("public_release_review_required", root.GetProperty("rolloutState").GetString());
        Assert.Equal("review_required", root.GetProperty("supportabilityState").GetString());
        Assert.Equal(
            "missing",
            root.GetProperty("publicTrustMetrics").GetProperty("proofFreshness").GetProperty("status").GetString());
        Assert.Equal(
            "review_required",
            root.GetProperty("publicTrustMetrics").GetProperty("releaseChannel").GetProperty("supportabilityState").GetString());
        Assert.Equal(
            "review_required",
            root.GetProperty("registryBoundaryCoverage").GetProperty("releaseChannel").GetProperty("supportabilityState").GetString());
        Assert.Equal(sourceBytes, fixture.ReadRegistryManifestBytes());
    }

    [Theory]
    [InlineData("missing_release_proof")]
    [InlineData("missing_localization_gate")]
    [InlineData("invalid_route_contract")]
    [InlineData("mutated_readiness_digest")]
    public void ServedManifestFloorRejectsUnboundOrRegistryInvalidFreshnessEvidence(string scenario)
    {
        using var fixture = new PublicReleaseManifestFixture();
        Dictionary<string, object?> payload = BuildOptimisticProofFreshnessManifest("fresh");
        if (scenario == "missing_release_proof")
        {
            payload.Remove("releaseProof");
        }
        else
        {
            var releaseProof = Assert.IsType<JsonObject>(payload["releaseProof"]);
            switch (scenario)
            {
                case "missing_localization_gate":
                    releaseProof.Remove("uiLocalizationReleaseGate");
                    break;
                case "invalid_route_contract":
                    releaseProof["proofRoutes"]!.AsArray().Add("/account/roster");
                    break;
                case "mutated_readiness_digest":
                    releaseProof["flagshipReadiness"]!["reason"] = "Evidence changed after hashing.";
                    break;
                default:
                    throw new InvalidOperationException($"Unknown scenario {scenario}.");
            }
        }

        fixture.WriteRegistryManifestRaw(payload);
        byte[] sourceBytes = fixture.ReadRegistryManifestBytes();

        using JsonDocument canonical = JsonDocument.Parse(fixture.CreateService().LoadCanonicalManifestJson()!);
        JsonElement root = canonical.RootElement;
        Assert.Equal("missing", root.GetProperty("publicTrustMetrics").GetProperty("proofFreshness").GetProperty("status").GetString());
        Assert.Equal("public_release_review_required", root.GetProperty("rolloutState").GetString());
        Assert.Equal("review_required", root.GetProperty("supportabilityState").GetString());
        Assert.Equal("blocked", root.GetProperty("publicTrustMetrics").GetProperty("releaseChannel").GetProperty("posture").GetString());
        Assert.Equal("blocked", root.GetProperty("registryBoundaryCoverage").GetProperty("releaseChannel").GetProperty("publicTrustPosture").GetString());
        Assert.Equal(sourceBytes, fixture.ReadRegistryManifestBytes());
    }

    [Theory]
    [InlineData("fresh", false)]
    [InlineData("stale", true)]
    public void ServedManifestFloorBlocksOptimisticCanonicalAndReleasesProjectionsWhilePrivacyLaunchGateIsReviewRequired(
        string proofFreshnessStatus,
        bool proofIsStale)
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(BuildOptimisticProofFreshnessManifest(proofFreshnessStatus));
        byte[] sourceBytes = fixture.ReadRegistryManifestBytes();
        PublicReleaseManifestService service = fixture.CreateService(
            privacyLaunchGate: PrivacyLaunchGate.Current);

        Assert.True(service.RequiresCanonicalManifestRewrite());
        using JsonDocument canonical = JsonDocument.Parse(service.LoadCanonicalManifestJson()!);
        JsonElement root = canonical.RootElement;

        Assert.Equal(proofFreshnessStatus, root.GetProperty("publicTrustMetrics").GetProperty("proofFreshness").GetProperty("status").GetString());
        Assert.Equal("public_release_review_required", root.GetProperty("rolloutState").GetString());
        Assert.Equal("review_required", root.GetProperty("supportabilityState").GetString());
        Assert.Contains("Hosted Build privacy", root.GetProperty("rolloutReason").GetString(), StringComparison.Ordinal);
        if (proofIsStale)
        {
            Assert.Contains("stale or incomplete proof receipts", root.GetProperty("rolloutReason").GetString(), StringComparison.Ordinal);
        }

        JsonElement privacy = root.GetProperty("publicTrustMetrics").GetProperty("privacyReadiness");
        Assert.Equal(PrivacyLaunchGate.ContractName, privacy.GetProperty("contractName").GetString());
        Assert.True(privacy.GetProperty("reviewRequired").GetBoolean());
        JsonElement publicReleaseChannel = root.GetProperty("publicTrustMetrics").GetProperty("releaseChannel");
        Assert.Equal("public_release_review_required", publicReleaseChannel.GetProperty("rolloutState").GetString());
        Assert.Equal("review_required", publicReleaseChannel.GetProperty("supportabilityState").GetString());
        Assert.Equal("blocked", publicReleaseChannel.GetProperty("posture").GetString());
        JsonElement registryReleaseChannel = root.GetProperty("registryBoundaryCoverage").GetProperty("releaseChannel");
        Assert.Equal("public_release_review_required", registryReleaseChannel.GetProperty("rolloutState").GetString());
        Assert.Equal("review_required", registryReleaseChannel.GetProperty("supportabilityState").GetString());
        Assert.Equal("blocked", registryReleaseChannel.GetProperty("publicTrustPosture").GetString());

        PublicReleaseManifestDto releasesManifest = service.LoadManifest();
        Assert.Equal("review_required", releasesManifest.SupportabilityState);
        Assert.Equal("public_release_review_required", releasesManifest.RolloutState);
        Assert.True(releasesManifest.PublicTrustMetrics.HasValue);
        Assert.Equal(
            proofFreshnessStatus,
            releasesManifest.PublicTrustMetrics.Value
                .GetProperty("proofFreshness")
                .GetProperty("status")
                .GetString());
        JsonElement releasesPublicChannel = releasesManifest.PublicTrustMetrics.Value.GetProperty("releaseChannel");
        Assert.Equal("public_release_review_required", releasesPublicChannel.GetProperty("rolloutState").GetString());
        Assert.Equal("review_required", releasesPublicChannel.GetProperty("supportabilityState").GetString());
        Assert.Equal("blocked", releasesPublicChannel.GetProperty("posture").GetString());
        Assert.True(releasesManifest.RegistryBoundaryCoverage.HasValue);
        JsonElement releasesRegistryChannel = releasesManifest.RegistryBoundaryCoverage.Value.GetProperty("releaseChannel");
        Assert.Equal("public_release_review_required", releasesRegistryChannel.GetProperty("rolloutState").GetString());
        Assert.Equal("review_required", releasesRegistryChannel.GetProperty("supportabilityState").GetString());
        Assert.Equal("blocked", releasesRegistryChannel.GetProperty("publicTrustPosture").GetString());
        Assert.Equal(sourceBytes, fixture.ReadRegistryManifestBytes());
    }

    [Fact]
    public void ServedManifestFloorPreservesStrongerRolloutBlockerContext()
    {
        using var fixture = new PublicReleaseManifestFixture();
        Dictionary<string, object?> payload = BuildOptimisticProofFreshnessManifest("stale");
        payload["rolloutState"] = "coverage_incomplete";
        payload["rolloutReason"] = "Required desktop coverage is incomplete.";
        payload["supportabilitySummary"] = "The Windows installer is still missing.";
        payload["knownIssueSummary"] = "Windows remains unavailable.";
        payload["fixAvailabilitySummary"] = "Wait for the Windows candidate.";
        var publicTrustMetrics = Assert.IsType<Dictionary<string, object?>>(payload["publicTrustMetrics"]);
        var publicReleaseChannel = Assert.IsType<Dictionary<string, object?>>(publicTrustMetrics["releaseChannel"]);
        publicReleaseChannel["rolloutState"] = "coverage_incomplete";
        publicReleaseChannel["summary"] = "Public channel coverage is incomplete.";
        var registryBoundaryCoverage = Assert.IsType<Dictionary<string, object?>>(payload["registryBoundaryCoverage"]);
        var registryReleaseChannel = Assert.IsType<Dictionary<string, object?>>(registryBoundaryCoverage["releaseChannel"]);
        registryReleaseChannel["rolloutState"] = "coverage_incomplete";
        registryReleaseChannel["summary"] = "Registry coverage is incomplete.";
        fixture.WriteRegistryManifestRaw(payload);

        using JsonDocument canonical = JsonDocument.Parse(fixture.CreateService().LoadCanonicalManifestJson()!);
        JsonElement root = canonical.RootElement;

        Assert.Equal("coverage_incomplete", root.GetProperty("rolloutState").GetString());
        Assert.Equal("Required desktop coverage is incomplete.", root.GetProperty("rolloutReason").GetString());
        Assert.Equal("review_required", root.GetProperty("supportabilityState").GetString());
        Assert.Equal("The Windows installer is still missing.", root.GetProperty("supportabilitySummary").GetString());
        Assert.Equal("Windows remains unavailable.", root.GetProperty("knownIssueSummary").GetString());
        Assert.Equal("Wait for the Windows candidate.", root.GetProperty("fixAvailabilitySummary").GetString());
        Assert.Equal("Public channel coverage is incomplete.", root.GetProperty("publicTrustMetrics").GetProperty("releaseChannel").GetProperty("summary").GetString());
        Assert.Equal("Registry coverage is incomplete.", root.GetProperty("registryBoundaryCoverage").GetProperty("releaseChannel").GetProperty("summary").GetString());
    }

    [Fact]
    public void ServedManifestFreshnessExpiresAtTheDeclaredBoundaryAndRewriteDetectionAgrees()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(BuildOptimisticProofFreshnessManifest("fresh"));
        DateTimeOffset publishedAt = DateTimeOffset.Parse("2026-07-13T12:38:14Z");

        PublicReleaseManifestService boundaryService = fixture.CreateService(
            evaluationInstant: publishedAt.AddSeconds(604800));
        Assert.False(boundaryService.RequiresCanonicalManifestRewrite());
        using (JsonDocument boundary = JsonDocument.Parse(boundaryService.LoadCanonicalManifestJson()!))
        {
            Assert.Equal("fresh", boundary.RootElement.GetProperty("publicTrustMetrics").GetProperty("proofFreshness").GetProperty("status").GetString());
            Assert.Equal("preview_supported", boundary.RootElement.GetProperty("supportabilityState").GetString());
            Assert.Equal("preview", boundary.RootElement.GetProperty("publicTrustMetrics").GetProperty("releaseChannel").GetProperty("posture").GetString());
            Assert.Equal("preview", boundary.RootElement.GetProperty("registryBoundaryCoverage").GetProperty("releaseChannel").GetProperty("publicTrustPosture").GetString());
        }

        PublicReleaseManifestService expiredService = fixture.CreateService(
            evaluationInstant: publishedAt.AddSeconds(604801));
        Assert.True(expiredService.RequiresCanonicalManifestRewrite());
        using JsonDocument expired = JsonDocument.Parse(expiredService.LoadCanonicalManifestJson()!);
        Assert.Equal("stale", expired.RootElement.GetProperty("publicTrustMetrics").GetProperty("proofFreshness").GetProperty("status").GetString());
        Assert.Equal("public_release_review_required", expired.RootElement.GetProperty("rolloutState").GetString());
        Assert.Equal("review_required", expired.RootElement.GetProperty("supportabilityState").GetString());
        Assert.Equal("blocked", expired.RootElement.GetProperty("publicTrustMetrics").GetProperty("releaseChannel").GetProperty("posture").GetString());
        Assert.Equal("blocked", expired.RootElement.GetProperty("registryBoundaryCoverage").GetProperty("releaseChannel").GetProperty("publicTrustPosture").GetString());
    }

    [Theory]
    [InlineData("revoked", "promoted_preview", "revoked")]
    [InlineData("unpublished", "promoted_preview", "unpublished")]
    [InlineData("disabled", "promoted_preview", "disabled")]
    [InlineData("blocked", "promoted_preview", "blocked")]
    [InlineData("published", "quarantined", "quarantined")]
    [InlineData("published", "security-hold", "security_hold")]
    [InlineData("published", "legal_hold_v2", "legal_hold_v2")]
    public void ServedManifestFloorPreservesTerminalAndUnknownNonOptimisticStates(
        string publicationStatus,
        string rolloutState,
        string expectedState)
    {
        using var fixture = new PublicReleaseManifestFixture();
        Dictionary<string, object?> payload = BuildOptimisticProofFreshnessManifest("stale");
        payload["status"] = publicationStatus;
        payload["rolloutState"] = rolloutState;
        payload["supportabilityState"] = "preview_supported";
        payload["rolloutReason"] = "Current release shelf passed the local release run before publication.";
        payload["supportabilitySummary"] = "Current preview release is supported on the promoted routes.";
        payload["knownIssueSummary"] = "The published preview is available now.";
        var metrics = Assert.IsType<Dictionary<string, object?>>(payload["publicTrustMetrics"]);
        var publicChannel = Assert.IsType<Dictionary<string, object?>>(metrics["releaseChannel"]);
        publicChannel["rolloutState"] = rolloutState;
        publicChannel["supportabilityState"] = "preview_supported";
        publicChannel["summary"] = "The current preview is supported.";
        var boundary = Assert.IsType<Dictionary<string, object?>>(payload["registryBoundaryCoverage"]);
        var registryChannel = Assert.IsType<Dictionary<string, object?>>(boundary["releaseChannel"]);
        registryChannel["rolloutState"] = rolloutState;
        registryChannel["supportabilityState"] = "preview_supported";
        registryChannel["summary"] = "Registry truth reports a supported preview.";
        fixture.WriteRegistryManifestRaw(payload);

        using JsonDocument canonical = JsonDocument.Parse(fixture.CreateService().LoadCanonicalManifestJson()!);
        JsonElement root = canonical.RootElement;
        Assert.Equal(expectedState, root.GetProperty("rolloutState").GetString());
        Assert.Equal(expectedState, root.GetProperty("supportabilityState").GetString());
        Assert.Contains("stale or incomplete proof receipts", root.GetProperty("rolloutReason").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("supported", root.GetProperty("supportabilitySummary").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.Equal(expectedState, root.GetProperty("publicTrustMetrics").GetProperty("releaseChannel").GetProperty("supportabilityState").GetString());
        Assert.Equal(expectedState, root.GetProperty("registryBoundaryCoverage").GetProperty("releaseChannel").GetProperty("supportabilityState").GetString());
        string expectedPublicTrustPosture = string.Equals(expectedState, "revoked", StringComparison.Ordinal)
            ? "revoked"
            : "blocked";
        Assert.Equal(expectedPublicTrustPosture, root.GetProperty("publicTrustMetrics").GetProperty("releaseChannel").GetProperty("posture").GetString());
        Assert.Equal(expectedPublicTrustPosture, root.GetProperty("registryBoundaryCoverage").GetProperty("releaseChannel").GetProperty("publicTrustPosture").GetString());
        Assert.DoesNotContain("supported", root.GetProperty("publicTrustMetrics").GetProperty("releaseChannel").GetProperty("summary").GetString(), StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData("pass")]
    [InlineData("ready")]
    public void LoadManifestNormalizesRegistryProofAliasesToPassed(string proofStatus)
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestWithProofStatus(proofStatus);

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("passed", manifest.ProofStatus);
    }

    [Theory]
    [InlineData("pass")]
    [InlineData("ready")]
    public void LoadManifestNormalizesLocalProofAliasesToPassed(string proofStatus)
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: false);
        fixture.WriteLocalProof(proofStatus, "http://127.0.0.1:8091");

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("passed", manifest.ProofStatus);
    }

    [Fact]
    public void LoadCanonicalManifestJsonRewritesDesktopSurfaceRefsWhenDownloadsAreForceGated()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-20260513-221500",
            ["publishedAt"] = "2026-05-13T00:36:30Z",
            ["status"] = "published",
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = "abc123",
                    ["sizeBytes"] = 123456789L,
                    ["installAccessClass"] = "open_public"
                }
            },
            ["desktopSurfaceRefs"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["registryId"] = "desktop-surface:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["channelId"] = "public_stable",
                    ["releaseVersion"] = "run-20260513-221500",
                    ["tupleId"] = "avalonia:linux:linux-x64",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["installAccessClass"] = "open_public",
                    ["desktopChannelRef"] = "desktop-channel:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["installGuidanceRef"] = "install-guidance:public_stable:run-20260513-221500:avalonia-linux-x64-installer",
                    ["participationReceiptRef"] = "participation-receipt:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["rewardPublicationRef"] = "reward-publication:binding:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["publicationBindingId"] = "binding:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["publicInstallRoute"] = "/downloads/install/avalonia-linux-x64-installer",
                    ["rationale"] = "public_stable keeps avalonia:linux:linux-x64 guest-readable so desktop channel, install guidance, participation, and reward refs stay governed without exposing provider internals."
                }
            },
            ["desktopTupleCoverage"] = new Dictionary<string, object?>
            {
                ["complete"] = true,
                ["desktopRouteTruth"] = new object[]
                {
                    new Dictionary<string, object?>
                    {
                        ["tupleId"] = "avalonia:linux:linux-x64",
                        ["head"] = "avalonia",
                        ["platform"] = "linux",
                        ["rid"] = "linux-x64",
                        ["arch"] = "x64",
                        ["artifactId"] = "avalonia-linux-x64-installer",
                        ["installPosture"] = "installer_first",
                        ["publicInstallRoute"] = "/downloads/install/avalonia-linux-x64-installer"
                    }
                }
            }
        });

        string json = fixture.CreateService(additionalSettings: new Dictionary<string, string?>
        {
            ["CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS"] = "true"
        }).LoadCanonicalManifestJson()!;

        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement artifact = document.RootElement.GetProperty("artifacts")[0];
        JsonElement surface = document.RootElement.GetProperty("desktopSurfaceRefs")[0];

        Assert.Equal("account_required", artifact.GetProperty("installAccessClass").GetString());
        Assert.Equal("account_required", surface.GetProperty("installAccessClass").GetString());
        Assert.Contains("entitlement-backed", surface.GetProperty("rationale").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("guest-readable", surface.GetProperty("rationale").GetString(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LoadCanonicalManifestJsonKeepsFallbackDesktopSurfaceOpenWhenNoArtifactExists()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-20260513-221500",
            ["publishedAt"] = "2026-05-13T00:36:30Z",
            ["status"] = "published",
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = "abc123",
                    ["sizeBytes"] = 123456789L,
                    ["installAccessClass"] = "open_public"
                }
            },
            ["desktopSurfaceRefs"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["registryId"] = "desktop-surface:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["channelId"] = "public_stable",
                    ["releaseVersion"] = "run-20260513-221500",
                    ["tupleId"] = "avalonia:linux:linux-x64",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["installAccessClass"] = "open_public",
                    ["desktopChannelRef"] = "desktop-channel:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["installGuidanceRef"] = "install-guidance:public_stable:run-20260513-221500:avalonia-linux-x64-installer",
                    ["participationReceiptRef"] = "participation-receipt:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["rewardPublicationRef"] = "reward-publication:binding:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["publicationBindingId"] = "binding:public_stable:run-20260513-221500:avalonia:linux:linux-x64",
                    ["publicInstallRoute"] = "/downloads/install/avalonia-linux-x64-installer",
                    ["rationale"] = "public_stable keeps avalonia:linux:linux-x64 guest-readable so desktop channel, install guidance, participation, and reward refs stay governed without exposing provider internals."
                },
                new Dictionary<string, object?>
                {
                    ["registryId"] = "desktop-surface:public_stable:run-20260513-221500:blazor-desktop:linux:linux-x64",
                    ["artifactId"] = "blazor-desktop-linux-x64-installer",
                    ["channelId"] = "public_stable",
                    ["releaseVersion"] = "run-20260513-221500",
                    ["tupleId"] = "blazor-desktop:linux:linux-x64",
                    ["head"] = "blazor-desktop",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["installAccessClass"] = "open_public",
                    ["desktopChannelRef"] = "desktop-channel:public_stable:run-20260513-221500:blazor-desktop:linux:linux-x64",
                    ["installGuidanceRef"] = "install-guidance:public_stable:run-20260513-221500:blazor-desktop-linux-x64-installer",
                    ["participationReceiptRef"] = "participation-receipt:public_stable:run-20260513-221500:blazor-desktop:linux:linux-x64",
                    ["rewardPublicationRef"] = "reward-publication:binding:public_stable:run-20260513-221500:blazor-desktop:linux:linux-x64",
                    ["publicationBindingId"] = "binding:public_stable:run-20260513-221500:blazor-desktop:linux:linux-x64",
                    ["publicInstallRoute"] = "/downloads/install/blazor-desktop-linux-x64-installer",
                    ["rationale"] = "public_stable keeps fallback tuple blazor-desktop:linux:linux-x64 retained with guest-readable install guidance so recovery participation and reward refs stay governed."
                }
            }
        });

        string json = fixture.CreateService(additionalSettings: new Dictionary<string, string?>
        {
            ["CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS"] = "true"
        }).LoadCanonicalManifestJson()!;

        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement surfaces = document.RootElement.GetProperty("desktopSurfaceRefs");

        Assert.Equal("account_required", surfaces[0].GetProperty("installAccessClass").GetString());
        Assert.Equal("open_public", surfaces[1].GetProperty("installAccessClass").GetString());
        Assert.Contains("entitlement-backed", surfaces[0].GetProperty("rationale").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.Contains("guest-readable", surfaces[1].GetProperty("rationale").GetString(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LoadCanonicalManifestJsonKeepsWindowsInstallerOpenWhenArtifactTruthIsGuestReadable()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "preview",
            ["version"] = "run-20260617-061500",
            ["publishedAt"] = "2026-06-17T06:15:00Z",
            ["status"] = "published",
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-win-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "windows",
                    ["rid"] = "win-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Windows X64 Installer",
                    ["fileName"] = "chummer-avalonia-win-x64-installer.exe",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    ["sha256"] = "abc123",
                    ["sizeBytes"] = 123456789L,
                    ["installAccessClass"] = "open_public"
                }
            },
            ["desktopSurfaceRefs"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["registryId"] = "desktop-surface:preview:run-20260617-061500:avalonia:windows:win-x64",
                    ["artifactId"] = "avalonia-win-x64-installer",
                    ["channelId"] = "preview",
                    ["releaseVersion"] = "run-20260617-061500",
                    ["tupleId"] = "avalonia:windows:win-x64",
                    ["head"] = "avalonia",
                    ["platform"] = "windows",
                    ["rid"] = "win-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["installAccessClass"] = "open_public",
                    ["desktopChannelRef"] = "desktop-channel:preview:run-20260617-061500:avalonia:windows:win-x64",
                    ["installGuidanceRef"] = "install-guidance:preview:run-20260617-061500:avalonia-win-x64-installer",
                    ["participationReceiptRef"] = "participation-receipt:preview:run-20260617-061500:avalonia:windows:win-x64",
                    ["rewardPublicationRef"] = "reward-publication:binding:preview:run-20260617-061500:avalonia:windows:win-x64",
                    ["publicationBindingId"] = "binding:preview:run-20260617-061500:avalonia:windows:win-x64",
                    ["publicInstallRoute"] = "/downloads/install/avalonia-win-x64-installer",
                    ["rationale"] = "preview keeps preview tuple avalonia:windows:win-x64 on guest-readable install guidance so desktop can explain claim, participation, and reward posture before wider publication."
                }
            }
        });

        string json = fixture.CreateService().LoadCanonicalManifestJson()!;

        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement artifact = document.RootElement.GetProperty("artifacts")[0];
        JsonElement surface = document.RootElement.GetProperty("desktopSurfaceRefs")[0];

        Assert.Equal("open_public", artifact.GetProperty("installAccessClass").GetString());
        Assert.Equal("open_public", surface.GetProperty("installAccessClass").GetString());
        Assert.Contains("guest-readable", surface.GetProperty("rationale").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("entitlement-backed", surface.GetProperty("rationale").GetString(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RequiresCanonicalManifestRewriteWhenInstallAwareRegistryDriftsFromCoverageTruth()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "preview",
            ["version"] = "run-20260522-203456",
            ["publishedAt"] = "2026-05-22T20:36:30Z",
            ["status"] = "published",
            ["desktopTupleCoverage"] = new Dictionary<string, object?>
            {
                ["desktopRouteTruth"] = new object[]
                {
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:linux:linux-x64", ["head"] = "avalonia", ["platform"] = "linux", ["rid"] = "linux-x64", ["arch"] = "x64", ["artifactId"] = "avalonia-linux-x64-installer", ["routeRole"] = "primary", ["promotionState"] = "promoted", ["revokeState"] = "not_revoked", ["publicInstallRoute"] = "/downloads/install/avalonia-linux-x64-installer" },
                    new Dictionary<string, object?> { ["tupleId"] = "blazor-desktop:linux:linux-x64", ["head"] = "blazor-desktop", ["platform"] = "linux", ["rid"] = "linux-x64", ["arch"] = "x64", ["artifactId"] = "blazor-desktop-linux-x64-installer", ["routeRole"] = "primary", ["promotionState"] = "proof_required", ["revokeState"] = "not_revoked", ["publicInstallRoute"] = "/downloads/install/blazor-desktop-linux-x64-installer" },
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:windows:win-x64", ["head"] = "avalonia", ["platform"] = "windows", ["rid"] = "win-x64", ["arch"] = "x64", ["artifactId"] = "avalonia-win-x64-installer", ["routeRole"] = "primary", ["promotionState"] = "promoted", ["revokeState"] = "not_revoked", ["publicInstallRoute"] = "/downloads/install/avalonia-win-x64-installer" },
                    new Dictionary<string, object?> { ["tupleId"] = "blazor-desktop:windows:win-x64", ["head"] = "blazor-desktop", ["platform"] = "windows", ["rid"] = "win-x64", ["arch"] = "x64", ["artifactId"] = "blazor-desktop-win-x64-installer", ["routeRole"] = "primary", ["promotionState"] = "proof_required", ["revokeState"] = "not_revoked", ["publicInstallRoute"] = "/downloads/install/blazor-desktop-win-x64-installer" }
                }
            },
            ["installAwareArtifactRegistry"] = new object[]
            {
                new Dictionary<string, object?> { ["tupleId"] = "avalonia:linux:linux-x64", ["artifactId"] = "avalonia-linux-x64-installer", ["currentForInstalledBuild"] = false },
                new Dictionary<string, object?> { ["tupleId"] = "blazor-desktop:linux:linux-x64", ["artifactId"] = "blazor-desktop-linux-x64-installer", ["currentForInstalledBuild"] = false },
                new Dictionary<string, object?> { ["tupleId"] = "avalonia:windows:win-x64", ["artifactId"] = "avalonia-win-x64-installer", ["currentForInstalledBuild"] = false },
                new Dictionary<string, object?> { ["tupleId"] = "blazor-desktop:windows:win-x64", ["artifactId"] = "blazor-desktop-win-x64-installer", ["currentForInstalledBuild"] = false }
            },
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?> { ["artifactId"] = "avalonia-linux-x64-installer", ["head"] = "avalonia", ["platform"] = "linux", ["rid"] = "linux-x64", ["arch"] = "x64", ["kind"] = "installer", ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb", ["fileName"] = "chummer-avalonia-linux-x64-installer.deb", ["sha256"] = "linuxa", ["sizeBytes"] = 1L },
                new Dictionary<string, object?> { ["artifactId"] = "blazor-desktop-linux-x64-installer", ["head"] = "blazor-desktop", ["platform"] = "linux", ["rid"] = "linux-x64", ["arch"] = "x64", ["kind"] = "installer", ["downloadUrl"] = "/downloads/files/chummer-blazor-desktop-linux-x64-installer.deb", ["fileName"] = "chummer-blazor-desktop-linux-x64-installer.deb", ["sha256"] = "linuxb", ["sizeBytes"] = 2L },
                new Dictionary<string, object?> { ["artifactId"] = "avalonia-win-x64-installer", ["head"] = "avalonia", ["platform"] = "windows", ["rid"] = "win-x64", ["arch"] = "x64", ["kind"] = "installer", ["downloadUrl"] = "/downloads/files/chummer-avalonia-win-x64-installer.exe", ["fileName"] = "chummer-avalonia-win-x64-installer.exe", ["sha256"] = "wina", ["sizeBytes"] = 3L },
                new Dictionary<string, object?> { ["artifactId"] = "blazor-desktop-win-x64-installer", ["head"] = "blazor-desktop", ["platform"] = "windows", ["rid"] = "win-x64", ["arch"] = "x64", ["kind"] = "installer", ["downloadUrl"] = "/downloads/files/chummer-blazor-desktop-win-x64-installer.exe", ["fileName"] = "chummer-blazor-desktop-win-x64-installer.exe", ["sha256"] = "winb", ["sizeBytes"] = 4L }
            }
        });

        var service = fixture.CreateService();

        Assert.True(service.RequiresCanonicalManifestRewrite());

        string json = service.LoadCanonicalManifestJson()!;
        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement registry = document.RootElement.GetProperty("installAwareArtifactRegistry");
        Assert.True(registry.EnumerateArray().Single(row => row.GetProperty("tupleId").GetString() == "avalonia:linux:linux-x64").GetProperty("currentForInstalledBuild").GetBoolean());
        Assert.False(registry.EnumerateArray().Single(row => row.GetProperty("tupleId").GetString() == "blazor-desktop:linux:linux-x64").GetProperty("currentForInstalledBuild").GetBoolean());
        Assert.True(registry.EnumerateArray().Single(row => row.GetProperty("tupleId").GetString() == "avalonia:windows:win-x64").GetProperty("currentForInstalledBuild").GetBoolean());
        Assert.False(registry.EnumerateArray().Single(row => row.GetProperty("tupleId").GetString() == "blazor-desktop:windows:win-x64").GetProperty("currentForInstalledBuild").GetBoolean());
    }

    [Fact]
    public void LoadCanonicalManifestJsonAlwaysNormalizesInstallAwareRegistryFromCoverageTruth()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "preview",
            ["version"] = "run-20260522-205120",
            ["publishedAt"] = "2026-05-22T20:53:11Z",
            ["status"] = "published",
            ["desktopTupleCoverage"] = new Dictionary<string, object?>
            {
                ["desktopRouteTruth"] = new object[]
                {
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:linux:linux-x64", ["head"] = "avalonia", ["platform"] = "linux", ["rid"] = "linux-x64", ["arch"] = "x64", ["artifactId"] = "avalonia-linux-x64-installer", ["routeRole"] = "primary", ["promotionState"] = "promoted", ["revokeState"] = "not_revoked", ["publicInstallRoute"] = "/downloads/install/avalonia-linux-x64-installer" },
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:windows:win-x64", ["head"] = "avalonia", ["platform"] = "windows", ["rid"] = "win-x64", ["arch"] = "x64", ["artifactId"] = "avalonia-win-x64-installer", ["routeRole"] = "primary", ["promotionState"] = "promoted", ["revokeState"] = "not_revoked", ["publicInstallRoute"] = "/downloads/install/avalonia-win-x64-installer" }
                }
            },
            ["installAwareArtifactRegistry"] = new object[]
            {
                new Dictionary<string, object?> { ["tupleId"] = "avalonia:linux:linux-x64", ["artifactId"] = "avalonia-linux-x64-installer", ["currentForInstalledBuild"] = false },
                new Dictionary<string, object?> { ["tupleId"] = "avalonia:windows:win-x64", ["artifactId"] = "avalonia-win-x64-installer", ["currentForInstalledBuild"] = false }
            },
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?> { ["artifactId"] = "avalonia-linux-x64-installer", ["head"] = "avalonia", ["platform"] = "linux", ["rid"] = "linux-x64", ["arch"] = "x64", ["kind"] = "installer", ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb", ["fileName"] = "chummer-avalonia-linux-x64-installer.deb", ["sha256"] = "linuxa", ["sizeBytes"] = 1L },
                new Dictionary<string, object?> { ["artifactId"] = "avalonia-win-x64-installer", ["head"] = "avalonia", ["platform"] = "windows", ["rid"] = "win-x64", ["arch"] = "x64", ["kind"] = "installer", ["downloadUrl"] = "/downloads/files/chummer-avalonia-win-x64-installer.exe", ["fileName"] = "chummer-avalonia-win-x64-installer.exe", ["sha256"] = "wina", ["sizeBytes"] = 3L }
            }
        });

        string json = fixture.CreateService().LoadCanonicalManifestJson()!;

        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement registry = document.RootElement.GetProperty("installAwareArtifactRegistry");
        Assert.All(registry.EnumerateArray(), row => Assert.True(row.GetProperty("currentForInstalledBuild").GetBoolean()));
    }

    [Fact]
    public void LoadCanonicalManifestJsonDropsCoverageRowsWithoutPublishedArtifacts()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "public_stable",
            ["version"] = "run-20260612-121055",
            ["publishedAt"] = "2026-06-13T18:35:17Z",
            ["status"] = "published",
            ["desktopTupleCoverage"] = new Dictionary<string, object?>
            {
                ["desktopRouteTruth"] = new object[]
                {
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:linux:linux-x64", ["head"] = "avalonia", ["platform"] = "linux", ["rid"] = "linux-x64", ["arch"] = "x64", ["artifactId"] = "avalonia-linux-x64-installer", ["routeRole"] = "primary", ["promotionState"] = "promoted", ["revokeState"] = "not_revoked", ["publicInstallRoute"] = "/downloads/install/avalonia-linux-x64-installer" },
                    new Dictionary<string, object?> { ["tupleId"] = "blazor-desktop:linux:linux-x64", ["head"] = "blazor-desktop", ["platform"] = "linux", ["rid"] = "linux-x64", ["arch"] = "x64", ["artifactId"] = "blazor-desktop-linux-x64-installer", ["routeRole"] = "fallback", ["promotionState"] = "proof_required", ["revokeState"] = "not_revoked", ["publicInstallRoute"] = "/downloads/install/blazor-desktop-linux-x64-installer" },
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:windows:win-x64", ["head"] = "avalonia", ["platform"] = "windows", ["rid"] = "win-x64", ["arch"] = "x64", ["artifactId"] = "avalonia-win-x64-installer", ["routeRole"] = "primary", ["promotionState"] = "promoted", ["revokeState"] = "not_revoked", ["publicInstallRoute"] = "/downloads/install/avalonia-win-x64-installer" }
                }
            },
            ["installAwareArtifactRegistry"] = new object[]
            {
                new Dictionary<string, object?> { ["tupleId"] = "avalonia:linux:linux-x64", ["artifactId"] = "avalonia-linux-x64-installer", ["currentForInstalledBuild"] = true },
                new Dictionary<string, object?> { ["tupleId"] = "blazor-desktop:linux:linux-x64", ["artifactId"] = "blazor-desktop-linux-x64-installer", ["currentForInstalledBuild"] = false },
                new Dictionary<string, object?> { ["tupleId"] = "avalonia:windows:win-x64", ["artifactId"] = "avalonia-win-x64-installer", ["currentForInstalledBuild"] = true }
            },
            ["desktopSurfaceRefs"] = new object[]
            {
                new Dictionary<string, object?> { ["tupleId"] = "avalonia:linux:linux-x64", ["artifactId"] = "avalonia-linux-x64-installer", ["publicInstallRoute"] = "/downloads/install/avalonia-linux-x64-installer" },
                new Dictionary<string, object?> { ["tupleId"] = "blazor-desktop:linux:linux-x64", ["artifactId"] = "blazor-desktop-linux-x64-installer", ["publicInstallRoute"] = "/downloads/install/blazor-desktop-linux-x64-installer" },
                new Dictionary<string, object?> { ["tupleId"] = "avalonia:windows:win-x64", ["artifactId"] = "avalonia-win-x64-installer", ["publicInstallRoute"] = "/downloads/install/avalonia-win-x64-installer" }
            },
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?> { ["artifactId"] = "avalonia-linux-x64-installer", ["head"] = "avalonia", ["platform"] = "linux", ["rid"] = "linux-x64", ["arch"] = "x64", ["kind"] = "installer", ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb", ["fileName"] = "chummer-avalonia-linux-x64-installer.deb", ["sha256"] = "linuxa", ["sizeBytes"] = 1L },
                new Dictionary<string, object?> { ["artifactId"] = "avalonia-win-x64-installer", ["head"] = "avalonia", ["platform"] = "windows", ["rid"] = "win-x64", ["arch"] = "x64", ["kind"] = "installer", ["downloadUrl"] = "/downloads/files/chummer-avalonia-win-x64-installer.exe", ["fileName"] = "chummer-avalonia-win-x64-installer.exe", ["sha256"] = "wina", ["sizeBytes"] = 3L }
            }
        });

        string json = fixture.CreateService().LoadCanonicalManifestJson()!;

        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement registry = document.RootElement.GetProperty("installAwareArtifactRegistry");
        JsonElement surfaces = document.RootElement.GetProperty("desktopSurfaceRefs");

        Assert.DoesNotContain(
            registry.EnumerateArray().Select(row => row.GetProperty("artifactId").GetString()),
            artifactId => string.Equals(artifactId, "blazor-desktop-linux-x64-installer", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain(
            surfaces.EnumerateArray().Select(row => row.GetProperty("artifactId").GetString()),
            artifactId => string.Equals(artifactId, "blazor-desktop-linux-x64-installer", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ManifestSerializationKeepsLegacyReleaseProofObject()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: false);
        fixture.WriteLocalProof("passed", "https://chummer.run");

        var manifest = fixture.CreateService().LoadManifest();
        var json = JsonSerializer.Serialize(manifest, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        using var document = JsonDocument.Parse(json);

        JsonElement releaseProof = document.RootElement.GetProperty("releaseProof");
        Assert.Equal("passed", releaseProof.GetProperty("status").GetString());
        Assert.Equal("https://chummer.run", releaseProof.GetProperty("baseUrl").GetString());
        Assert.Equal("install_claim_restore_continue", releaseProof.GetProperty("journeysPassed")[0].GetString());
        Assert.Equal("/downloads/install/avalonia-linux-x64-installer", releaseProof.GetProperty("proofRoutes")[0].GetString());
    }

    [Fact]
    public void LoadManifestPrefersCanonicalFileWhenRuntimeEndpointIsStale()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(
            version: "run-20260402-203858",
            downloads:
            [
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-osx-arm64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "macos",
                    ["arch"] = "arm64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop macOS ARM64 Installer",
                    ["fileName"] = "chummer-avalonia-osx-arm64-installer.dmg",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    ["sha256"] = "mac123",
                    ["sizeBytes"] = 987654321L,
                    ["installAccessClass"] = "account_required"
                }
            ]);

        using var httpClient = new HttpClient(new StaticJsonHandler(
            """
            {
              "product": "chummer",
              "channelId": "preview",
              "version": "run-older",
              "publishedAt": "2026-04-02T19:00:00Z",
              "status": "published",
              "artifacts": [
                {
                  "artifactId": "avalonia-win-x64-installer",
                  "head": "avalonia",
                  "platform": "windows",
                  "arch": "x64",
                  "kind": "installer",
                  "platformLabel": "Avalonia Desktop Windows X64 Installer",
                  "fileName": "chummer-avalonia-win-x64-installer.exe",
                  "downloadUrl": "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                  "sha256": "win123",
                  "sizeBytes": 123456789,
                  "installAccessClass": "open_public"
                }
              ]
            }
            """));

        var manifest = fixture.CreateService(httpClient, includeRuntimeUrl: true).LoadManifest();

        Assert.Equal("run-20260402-203858", manifest.Version);
        Assert.Contains(manifest.Downloads, item => string.Equals(item.Id, "avalonia-osx-arm64-installer", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain(manifest.Downloads, item => string.Equals(item.Id, "avalonia-win-x64-installer", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void LoadManifestPrefersCanonicalFileWhenRuntimeEndpointMatchesTimestampButDropsCanonicalArtifacts()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["product"] = "chummer",
            ["channelId"] = "preview",
            ["version"] = "run-20260423-201931",
            ["publishedAt"] = "2026-04-23T20:22:05Z",
            ["status"] = "published",
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-osx-arm64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "macos",
                    ["arch"] = "arm64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop macOS ARM64 Installer",
                    ["fileName"] = "chummer-avalonia-osx-arm64-installer.dmg",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    ["sha256"] = "mac123",
                    ["sizeBytes"] = 1L,
                    ["installAccessClass"] = "account_required"
                },
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "blazor-desktop-osx-arm64-installer",
                    ["head"] = "blazor-desktop",
                    ["platform"] = "macos",
                    ["arch"] = "arm64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Blazor Desktop macOS ARM64 Installer",
                    ["fileName"] = "chummer-blazor-desktop-osx-arm64-installer.dmg",
                    ["downloadUrl"] = "/downloads/files/chummer-blazor-desktop-osx-arm64-installer.dmg",
                    ["sha256"] = "mac456",
                    ["sizeBytes"] = 2L,
                    ["installAccessClass"] = "account_required"
                }
            }
        });

        using var httpClient = new HttpClient(new StaticJsonHandler(
            """
            {
              "product": "chummer",
              "channelId": "preview",
              "version": "run-20260423-201931",
              "publishedAt": "2026-04-23T20:22:05Z",
              "status": "published",
              "artifacts": [
                {
                  "artifactId": "avalonia-osx-arm64-installer",
                  "head": "avalonia",
                  "platform": "macos",
                  "arch": "arm64",
                  "kind": "installer",
                  "platformLabel": "Avalonia Desktop macOS ARM64 Installer",
                  "fileName": "chummer-avalonia-osx-arm64-installer.dmg",
                  "downloadUrl": "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                  "sha256": "mac123",
                  "sizeBytes": 1,
                  "installAccessClass": "account_required"
                }
              ]
            }
            """));

        var manifest = fixture.CreateService(httpClient, includeRuntimeUrl: true).LoadManifest();

        Assert.Equal("run-20260423-201931", manifest.Version);
        Assert.Contains(manifest.Downloads, item => string.Equals(item.Id, "avalonia-osx-arm64-installer", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(manifest.Downloads, item => string.Equals(item.Id, "blazor-desktop-osx-arm64-installer", StringComparison.OrdinalIgnoreCase));
    }
    [Fact]
    public void LoadManifestPreservesTopLevelGeneratedTimestampFromCanonicalRegistryManifest()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["contractName"] = "Chummer.Hub.Registry.Contracts",
            ["contract_name"] = "Chummer.Hub.Registry.Contracts",
            ["product"] = "chummer",
            ["channelId"] = "preview",
            ["version"] = "run-20260416-212019",
            ["generatedAt"] = "2026-04-16T21:23:00Z",
            ["publishedAt"] = "2026-04-16T21:21:44Z",
            ["status"] = "published",
            ["artifacts"] = new[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-osx-arm64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "macos",
                    ["arch"] = "arm64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop macOS ARM64 Installer",
                    ["fileName"] = "chummer-avalonia-osx-arm64-installer.dmg",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    ["sha256"] = "mac123",
                    ["sizeBytes"] = 987654321L,
                    ["installAccessClass"] = "account_required"
                }
            }
        });

        var manifest = fixture.CreateService().LoadManifest();
        Assert.Equal(DateTimeOffset.Parse("2026-04-16T21:23:00Z"), manifest.GeneratedAt);

        string json = JsonSerializer.Serialize(manifest, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        using JsonDocument document = JsonDocument.Parse(json);
        Assert.Equal("Chummer.Hub.Registry.Contracts", document.RootElement.GetProperty("contractName").GetString());
        Assert.Equal("Chummer.Hub.Registry.Contracts", document.RootElement.GetProperty("contract_name").GetString());
        Assert.Equal("2026-04-16T21:23:00+00:00", document.RootElement.GetProperty("generatedAt").GetString());
        Assert.Equal("2026-04-16T21:23:00+00:00", document.RootElement.GetProperty("generated_at").GetString());
    }

    [Fact]
    public void LoadManifestPreservesDesktopTupleCoverageFromCanonicalRegistryManifest()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["contractName"] = "Chummer.Hub.Registry.Contracts",
            ["contract_name"] = "Chummer.Hub.Registry.Contracts",
            ["product"] = "chummer",
            ["channelId"] = "preview",
            ["version"] = "run-20260419-201110",
            ["generatedAt"] = "2026-04-19T20:14:00Z",
            ["publishedAt"] = "2026-04-19T20:14:00Z",
            ["status"] = "published",
            ["desktopTupleCoverage"] = new Dictionary<string, object?>
            {
                ["requiredPlatformIds"] = new[] { "linux", "windows" },
                ["missingPlatformIds"] = Array.Empty<string>(),
                ["missingHeadPlatformPairs"] = Array.Empty<string>(),
                ["missingRidPlatformTuples"] = Array.Empty<string>()
            },
            ["artifacts"] = new[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-osx-arm64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "macos",
                    ["arch"] = "arm64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop macOS ARM64 Installer",
                    ["fileName"] = "chummer-avalonia-osx-arm64-installer.dmg",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    ["sha256"] = "mac123",
                    ["sizeBytes"] = 987654321L,
                    ["installAccessClass"] = "account_required"
                }
            }
        });

        var manifest = fixture.CreateService().LoadManifest();
        JsonElement coverage = Assert.IsType<JsonElement>(manifest.DesktopTupleCoverage);
        Assert.Equal(JsonValueKind.Object, coverage.ValueKind);
        Assert.Equal("linux", coverage.GetProperty("requiredPlatformIds")[0].GetString());
        Assert.Equal("windows", coverage.GetProperty("requiredPlatformIds")[1].GetString());

        string json = JsonSerializer.Serialize(manifest, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement serializedCoverage = document.RootElement.GetProperty("desktopTupleCoverage");
        Assert.Equal("linux", serializedCoverage.GetProperty("requiredPlatformIds")[0].GetString());
        Assert.Equal("windows", serializedCoverage.GetProperty("requiredPlatformIds")[1].GetString());
    }

    [Fact]
    public void LoadManifestPreservesCanonicalRidAsCompatibilityPlatformId()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["contractName"] = "Chummer.Hub.Registry.Contracts",
            ["contract_name"] = "Chummer.Hub.Registry.Contracts",
            ["product"] = "chummer",
            ["channelId"] = "preview",
            ["version"] = "run-20260421-000001",
            ["generatedAt"] = "2026-04-21T00:00:01Z",
            ["publishedAt"] = "2026-04-21T00:00:01Z",
            ["status"] = "published",
            ["desktopTupleCoverage"] = new Dictionary<string, object?>
            {
                ["requiredDesktopPlatforms"] = new[] { "linux", "windows", "macos" },
                ["requiredDesktopHeads"] = new[] { "avalonia" },
                ["requiredDesktopPlatformHeadRidTuples"] = new[] { "avalonia:linux-x64:linux", "avalonia:win-x64:windows", "avalonia:osx-arm64:macos" },
                ["promotedInstallerTuples"] = new object[]
                {
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:linux:linux-x64", ["head"] = "avalonia", ["platform"] = "linux", ["rid"] = "linux-x64", ["arch"] = "x64", ["kind"] = "installer", ["artifactId"] = "avalonia-linux-x64-installer" },
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:macos:osx-arm64", ["head"] = "avalonia", ["platform"] = "macos", ["rid"] = "osx-arm64", ["arch"] = "arm64", ["kind"] = "installer", ["artifactId"] = "avalonia-osx-arm64-installer" }
                },
                ["promotedPlatformHeads"] = new Dictionary<string, object?> { ["linux"] = new[] { "avalonia" }, ["windows"] = Array.Empty<string>(), ["macos"] = new[] { "avalonia" } },
                ["promotedPlatformHeadRidTuples"] = new[] { "avalonia:linux-x64:linux", "avalonia:osx-arm64:macos" },
                ["missingRequiredPlatforms"] = new[] { "windows" },
                ["missingRequiredHeads"] = Array.Empty<string>(),
                ["missingRequiredPlatformHeadPairs"] = new[] { "avalonia:windows" },
                ["missingRequiredPlatformHeadRidTuples"] = new[] { "avalonia:win-x64:windows" },
                ["externalProofRequests"] = Array.Empty<object>(),
                ["desktopRouteTruth"] = Array.Empty<object>(),
                ["complete"] = false
            },
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = "linux123",
                    ["sizeBytes"] = 1L,
                    ["installAccessClass"] = "account_required"
                },
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-osx-arm64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "macos",
                    ["rid"] = "osx-arm64",
                    ["arch"] = "arm64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop macOS ARM64 Installer",
                    ["fileName"] = "chummer-avalonia-osx-arm64-installer.dmg",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    ["sha256"] = "mac123",
                    ["sizeBytes"] = 2L,
                    ["installAccessClass"] = "account_required"
                }
            }
        });

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Contains(manifest.Downloads, item => item.Id == "avalonia-linux-x64-installer" && item.PlatformId == "linux" && item.Rid == "linux-x64");
        Assert.Contains(manifest.Downloads, item => item.Id == "avalonia-osx-arm64-installer" && item.PlatformId == "macos" && item.Rid == "osx-arm64");
        Assert.Contains(manifest.Downloads, item => item.Id == "avalonia-linux-x64-installer" && item.Platform == "Avalonia Desktop Linux X64 Installer" && item.PlatformLabel == "Avalonia Desktop Linux X64 Installer");
        Assert.Contains(manifest.Downloads, item => item.Id == "avalonia-osx-arm64-installer" && item.Platform == "Avalonia Desktop macOS ARM64 Installer" && item.PlatformLabel == "Avalonia Desktop macOS ARM64 Installer");
    }

    [Fact]
    public void LoadManifestDefaultsContractNameWhenSourceManifestOmitsIt()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifest(includeProof: false);

        var manifest = fixture.CreateService().LoadManifest();

        Assert.Equal("Chummer.Hub.Registry.Contracts", manifest.ContractName);

        string json = JsonSerializer.Serialize(manifest, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        using JsonDocument document = JsonDocument.Parse(json);
        Assert.Equal("Chummer.Hub.Registry.Contracts", document.RootElement.GetProperty("contractName").GetString());
        Assert.Equal("Chummer.Hub.Registry.Contracts", document.RootElement.GetProperty("contract_name").GetString());
    }

    [Fact]
    public void LoadManifestSuppressesDisabledArtifactsAndRebuildsCoverage()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(new Dictionary<string, object?>
        {
            ["contractName"] = "Chummer.Hub.Registry.Contracts",
            ["contract_name"] = "Chummer.Hub.Registry.Contracts",
            ["product"] = "chummer",
            ["channelId"] = "preview",
            ["version"] = "run-20260420-010101",
            ["publishedAt"] = "2026-04-20T01:01:01Z",
            ["status"] = "published",
            ["releaseProof"] = new Dictionary<string, object?>
            {
                ["status"] = "passed",
                ["proofRoutes"] = new[]
                {
                    "/downloads/install/avalonia-linux-x64-installer",
                    "/downloads/install/avalonia-win-x64-installer"
                }
            },
            ["desktopTupleCoverage"] = new Dictionary<string, object?>
            {
                ["requiredDesktopPlatforms"] = new[] { "macos" },
                ["requiredDesktopHeads"] = new[] { "blazor-desktop" },
                ["requiredDesktopPlatformHeadRidTuples"] = new[]
                {
                    "avalonia:osx-x64:macos",
                    "avalonia:win-arm64:macos",
                    "avalonia:future-x64:linux"
                },
                ["missingRequiredPlatforms"] = Array.Empty<string>(),
                ["missingRequiredHeads"] = Array.Empty<string>(),
                ["missingRequiredPlatformHeadPairs"] = Array.Empty<string>(),
                ["missingRequiredPlatformHeadRidTuples"] = Array.Empty<string>(),
                ["promotedInstallerTuples"] = new object[]
                {
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:linux:linux-x64", ["head"] = "avalonia", ["platform"] = "linux", ["rid"] = "linux-x64", ["arch"] = "x64", ["kind"] = "installer", ["artifactId"] = "avalonia-linux-x64-installer" },
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:windows:win-x64", ["head"] = "avalonia", ["platform"] = "windows", ["rid"] = "win-x64", ["arch"] = "x64", ["kind"] = "installer", ["artifactId"] = "avalonia-win-x64-installer" },
                    new Dictionary<string, object?> { ["tupleId"] = "avalonia:macos:osx-arm64", ["head"] = "avalonia", ["platform"] = "macos", ["rid"] = "osx-arm64", ["arch"] = "arm64", ["kind"] = "installer", ["artifactId"] = "avalonia-osx-arm64-installer" }
                },
                ["promotedPlatformHeads"] = new Dictionary<string, object?> { ["linux"] = new[] { "avalonia" }, ["windows"] = new[] { "avalonia" }, ["macos"] = new[] { "avalonia" } },
                ["promotedPlatformHeadRidTuples"] = new[] { "avalonia:linux-x64:linux", "avalonia:win-x64:windows", "avalonia:osx-arm64:macos" },
                ["externalProofRequests"] = Array.Empty<object>(),
                ["desktopRouteTruth"] = new object[]
                {
                    new Dictionary<string, object?> { ["artifactId"] = "avalonia-linux-x64-installer" },
                    new Dictionary<string, object?> { ["artifactId"] = "avalonia-win-x64-installer" }
                },
                ["complete"] = true
            },
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-linux-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "linux",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                    ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    ["sha256"] = "linux123",
                    ["sizeBytes"] = 1L,
                    ["installAccessClass"] = "account_required"
                },
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-win-x64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "windows",
                    ["arch"] = "x64",
                    ["kind"] = "installer",
                    ["platformLabel"] = "Avalonia Desktop Windows X64 Installer",
                    ["fileName"] = "chummer-avalonia-win-x64-installer.exe",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    ["sha256"] = "win123",
                    ["sizeBytes"] = 2L,
                    ["installAccessClass"] = "account_required"
                },
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-osx-arm64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "macos",
                    ["arch"] = "arm64",
                    ["kind"] = "dmg",
                    ["platformLabel"] = "Avalonia Desktop macOS ARM64 Installer",
                    ["fileName"] = "chummer-avalonia-osx-arm64-installer.dmg",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    ["sha256"] = "mac123",
                    ["sizeBytes"] = 3L,
                    ["installAccessClass"] = "account_required"
                }
            }
        });

        var manifest = fixture.CreateService(additionalSettings: new Dictionary<string, string?>
        {
            ["CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS"] = "avalonia-win-x64-installer"
        }).LoadManifest();

        Assert.DoesNotContain(manifest.Downloads, item => string.Equals(item.Id, "avalonia-win-x64-installer", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain(manifest.ProofRoutes ?? [], route => route.Contains("avalonia-win-x64-installer", StringComparison.OrdinalIgnoreCase));

        JsonElement coverage = Assert.IsType<JsonElement>(manifest.DesktopTupleCoverage);
        Assert.False(coverage.GetProperty("complete").GetBoolean());
        Assert.Equal(
            ["linux", "windows", "macos"],
            coverage.GetProperty("requiredDesktopPlatforms")
                .EnumerateArray()
                .Select(static value => value.GetString()!)
                .ToArray());
        Assert.Equal(
            ["avalonia"],
            coverage.GetProperty("requiredDesktopHeads")
                .EnumerateArray()
                .Select(static value => value.GetString()!)
                .ToArray());
        Assert.Equal(
            ["avalonia:linux-x64:linux", "avalonia:osx-arm64:macos", "avalonia:osx-x64:macos", "avalonia:win-x64:windows"],
            coverage.GetProperty("requiredDesktopPlatformHeadRidTuples")
                .EnumerateArray()
                .Select(static value => value.GetString()!)
                .ToArray());
        Assert.Equal(
            ["windows"],
            coverage.GetProperty("missingRequiredPlatforms")
                .EnumerateArray()
                .Select(static value => value.GetString()!)
                .ToArray());
        Assert.Contains(
            "avalonia:win-x64:windows",
            coverage.GetProperty("missingRequiredPlatformHeadRidTuples")
                .EnumerateArray()
                .Select(static value => value.GetString()));
        Assert.Contains(
            "avalonia:osx-x64:macos",
            coverage.GetProperty("missingRequiredPlatformHeadRidTuples")
                .EnumerateArray()
                .Select(static value => value.GetString()));
        Assert.DoesNotContain(
            coverage.GetProperty("promotedPlatformHeadRidTuples")
                .EnumerateArray()
                .Select(static value => value.GetString()),
            tupleId => tupleId is not null && tupleId.Contains("win-x64", StringComparison.OrdinalIgnoreCase));
        Assert.Equal("coverage_incomplete", manifest.RolloutState);
        Assert.Equal("review_required", manifest.SupportabilityState);
    }

    [Fact]
    public void LoadManifestReevaluatesCachedFreshProofWhenItExpiresInsideTheCacheTtl()
    {
        using var fixture = new PublicReleaseManifestFixture();
        fixture.WriteRegistryManifestRaw(BuildOptimisticProofFreshnessManifest("fresh"));
        DateTimeOffset publishedAt = DateTimeOffset.Parse("2026-07-13T12:38:14Z");
        var timeProvider = new MutableTimeProvider(publishedAt.AddSeconds(604790));
        PublicReleaseManifestService service = fixture.CreateService(timeProvider: timeProvider);

        PublicReleaseManifestDto fresh = service.LoadManifest();

        Assert.Equal("fresh", fresh.PublicTrustMetrics!.Value
            .GetProperty("proofFreshness")
            .GetProperty("status")
            .GetString());
        Assert.Equal("review_required", fresh.SupportabilityState);

        timeProvider.Advance(TimeSpan.FromSeconds(11));
        PublicReleaseManifestDto expired = service.LoadManifest();

        Assert.Equal("stale", expired.PublicTrustMetrics!.Value
            .GetProperty("proofFreshness")
            .GetProperty("status")
            .GetString());
        Assert.Equal("public_release_review_required", expired.RolloutState);
        Assert.Equal("review_required", expired.SupportabilityState);
    }

    [Fact]
    public void ServedManifestFloorReplacesUnrecognizedOptimisticNarrativesWhenProofIsABlocker()
    {
        using var fixture = new PublicReleaseManifestFixture();
        Dictionary<string, object?> payload = BuildOptimisticProofFreshnessManifest("stale");
        payload["rolloutReason"] = "The shelf sparkles without caveat.";
        payload["supportabilitySummary"] = "Every runner can trust this shelf.";
        payload["knownIssueSummary"] = "Nothing here needs attention.";
        payload["fixAvailabilitySummary"] = "Keep moving; no follow-up is necessary.";
        var metrics = Assert.IsType<Dictionary<string, object?>>(payload["publicTrustMetrics"]);
        var publicChannel = Assert.IsType<Dictionary<string, object?>>(metrics["releaseChannel"]);
        publicChannel["summary"] = "This channel is completely delightful.";
        var boundary = Assert.IsType<Dictionary<string, object?>>(payload["registryBoundaryCoverage"]);
        var registryChannel = Assert.IsType<Dictionary<string, object?>>(boundary["releaseChannel"]);
        registryChannel["summary"] = "Registry reports a flawless turquoise horizon.";
        fixture.WriteRegistryManifestRaw(payload);
        fixture.WriteFlagshipReadiness(status: "pass");
        fixture.WriteFinalGoldReadiness(status: "pass", verdict: "GOLD", failures: []);

        using JsonDocument canonical = JsonDocument.Parse(fixture.CreateService().LoadCanonicalManifestJson()!);
        JsonElement root = canonical.RootElement;

        Assert.Equal("public_release_review_required", root.GetProperty("rolloutState").GetString());
        Assert.Contains("stale or incomplete proof receipts", root.GetProperty("rolloutReason").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.Contains("stale or incomplete proof receipts", root.GetProperty("supportabilitySummary").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.Contains("stale or incomplete proof receipts", root.GetProperty("knownIssueSummary").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Only send fixed notices after", root.GetProperty("fixAvailabilitySummary").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("no follow-up", root.GetProperty("fixAvailabilitySummary").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.Contains(
            "stale or incomplete proof receipts",
            root.GetProperty("publicTrustMetrics").GetProperty("releaseChannel").GetProperty("summary").GetString(),
            StringComparison.OrdinalIgnoreCase);
        Assert.Contains(
            "stale or incomplete proof receipts",
            root.GetProperty("registryBoundaryCoverage").GetProperty("releaseChannel").GetProperty("summary").GetString(),
            StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("sparkles", root.GetProperty("rolloutReason").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("delightful", root.GetProperty("publicTrustMetrics").GetProperty("releaseChannel").GetProperty("summary").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("turquoise", root.GetProperty("registryBoundaryCoverage").GetProperty("releaseChannel").GetProperty("summary").GetString(), StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData("version")]
    [InlineData("channel")]
    [InlineData("status")]
    [InlineData("rolloutState")]
    [InlineData("rolloutReason")]
    [InlineData("supportabilityState")]
    [InlineData("supportabilitySummary")]
    [InlineData("proofStatus")]
    [InlineData("proofFlagshipReadiness")]
    public void LoadManifestPrefersCanonicalWhenEqualTimestampRuntimeScalarsDrift(string driftField)
    {
        using var fixture = new PublicReleaseManifestFixture();
        Dictionary<string, object?> canonicalPayload = BuildScalarDriftManifest();
        Dictionary<string, object?> runtimePayload = BuildScalarDriftManifest();
        ApplyRuntimeScalarDrift(runtimePayload, driftField);
        fixture.WriteRegistryManifestRaw(canonicalPayload);
        var handler = new CountingStaticJsonHandler(JsonSerializer.Serialize(runtimePayload));

        PublicReleaseManifestDto manifest = fixture.CreateService(
            httpClient: new HttpClient(handler),
            includeRuntimeUrl: true).LoadManifest();

        Assert.Equal(1, handler.CallCount);
        Assert.Equal("run-canonical-scalar", manifest.Version);
        Assert.Equal("preview", manifest.Channel);
        Assert.Equal("published", manifest.Status);
        Assert.Equal("promoted_preview", manifest.RolloutState);
        Assert.Equal("Canonical rollout narrative.", manifest.RolloutReason);
        Assert.Equal("review_required", manifest.SupportabilityState);
        Assert.Contains("Canonical supportability narrative", manifest.SupportabilitySummary, StringComparison.Ordinal);
        Assert.Equal("passed", manifest.ProofStatus);
        Assert.Contains(manifest.Downloads, artifact => artifact.Id == "avalonia-osx-arm64-installer" && artifact.Sha256 == "canonical-sha");
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void LoadManifestPreservesExplicitTerminalStatusWithArtifactsForCanonicalAndCompatibilityManifests(
        bool canonicalManifest)
    {
        using var fixture = new PublicReleaseManifestFixture();
        if (canonicalManifest)
        {
            Dictionary<string, object?> payload = BuildScalarDriftManifest();
            payload["status"] = "revoked";
            fixture.WriteRegistryManifestRaw(payload);
        }
        else
        {
            fixture.WriteCompatibilityManifestJson(JsonSerializer.Serialize(new Dictionary<string, object?>
            {
                ["version"] = "run-compatibility-terminal",
                ["channel"] = "preview",
                ["publishedAt"] = "2026-07-13T12:38:14Z",
                ["status"] = "revoked",
                ["downloads"] = new object[]
                {
                    new PublicReleaseArtifactDto(
                        Id: "avalonia-osx-arm64-installer",
                        Platform: "macOS ARM64",
                        Url: "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                        Sha256: "compatibility-sha",
                        SizeBytes: 42)
                }
            }));
        }

        PublicReleaseManifestDto manifest = fixture.CreateService(
            evaluationInstant: DateTimeOffset.Parse("2026-07-13T12:38:14Z")).LoadManifest();

        Assert.Equal("revoked", manifest.Status);
        Assert.Single(manifest.Downloads);
        Assert.Equal("avalonia-osx-arm64-installer", manifest.Downloads[0].Id);
    }

    [Theory]
    [InlineData(true, true)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(false, false)]
    public void LoadManifestUsesInjectedTimeProviderForParseAndMissingPublishedAtFallbacks(
        bool canonicalManifest,
        bool parseFallback)
    {
        using var fixture = new PublicReleaseManifestFixture();
        DateTimeOffset evaluationInstant = DateTimeOffset.Parse("2026-07-13T12:38:14Z");
        if (parseFallback)
        {
            if (canonicalManifest)
            {
                fixture.WriteRegistryManifestJson("null");
            }
            else
            {
                fixture.WriteCompatibilityManifestJson("null");
            }
        }
        else if (canonicalManifest)
        {
            Dictionary<string, object?> payload = BuildScalarDriftManifest();
            payload.Remove("publishedAt");
            fixture.WriteRegistryManifestRaw(payload);
        }
        else
        {
            fixture.WriteCompatibilityManifestJson(JsonSerializer.Serialize(new Dictionary<string, object?>
            {
                ["version"] = "run-compatibility-missing-published-at",
                ["channel"] = "preview",
                ["status"] = "published",
                ["downloads"] = new object[]
                {
                    new PublicReleaseArtifactDto(
                        Id: "avalonia-osx-arm64-installer",
                        Platform: "macOS ARM64",
                        Url: "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                        Sha256: "compatibility-sha",
                        SizeBytes: 42)
                }
            }));
        }

        PublicReleaseManifestDto manifest = fixture.CreateService(
            evaluationInstant: evaluationInstant).LoadManifest();

        Assert.Equal(evaluationInstant, manifest.PublishedAt);
        if (parseFallback)
        {
            Assert.Equal("manifest-error", manifest.Status);
            Assert.Equal(evaluationInstant, manifest.GeneratedAt);
        }
        else
        {
            Assert.Equal("published", manifest.Status);
            Assert.Single(manifest.Downloads);
        }
    }

    private static Dictionary<string, object?> BuildFreshProofTrustMetrics(string publishedAt)
    {
        DateTimeOffset generatedAt = DateTimeOffset.Parse(publishedAt);
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(generatedAt);
        return new()
        {
            ["proofFreshness"] = ReleaseProofEvidenceTestData.CreateFreshnessFacts(releaseProof, generatedAt)
        };
    }

    private static JsonObject BuildFreshReleaseProof(string generatedAt)
        => ReleaseProofEvidenceTestData.CreateReleaseProof(DateTimeOffset.Parse(generatedAt));

    private static Dictionary<string, object?> BuildOptimisticProofFreshnessManifest(string proofFreshnessStatus)
        => new()
        {
            ["product"] = "chummer",
            ["channel"] = "preview",
            ["channelId"] = "preview",
            ["version"] = "run-20260713-123603",
            ["publishedAt"] = "2026-07-13T12:38:14Z",
            ["status"] = "published",
            ["rolloutState"] = "promoted_preview",
            ["rolloutReason"] = "Current release shelf passed the local release run before publication.",
            ["supportabilityState"] = "preview_supported",
            ["supportabilitySummary"] = "Current preview release is supported on the promoted routes.",
            ["knownIssueSummary"] = "Preview caveats still apply.",
            ["fixAvailabilitySummary"] = "The published preview is available now.",
            ["releaseProof"] = BuildFreshReleaseProof("2026-07-13T12:38:14Z"),
            ["publicTrustMetrics"] = new Dictionary<string, object?>
            {
                ["proofFreshness"] = BuildProofFreshnessFacts(proofFreshnessStatus),
                ["privacyReadiness"] = PrivacyLaunchGate.ClearForTests.ToJsonObject(),
                ["releaseChannel"] = new Dictionary<string, object?>
                {
                    ["channelId"] = "preview",
                    ["posture"] = "preview",
                    ["publicationStatus"] = "published",
                    ["rolloutState"] = "promoted_preview",
                    ["supportabilityState"] = "preview_supported",
                    ["summary"] = "The current preview is supported."
                }
            },
            ["registryBoundaryCoverage"] = new Dictionary<string, object?>
            {
                ["releaseChannel"] = new Dictionary<string, object?>
                {
                    ["publicationStatus"] = "published",
                    ["publicTrustPosture"] = "preview",
                    ["rolloutState"] = "promoted_preview",
                    ["supportabilityState"] = "preview_supported",
                    ["summary"] = "Registry truth reports a supported preview."
                }
            },
            ["artifacts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["artifactId"] = "avalonia-osx-arm64-installer",
                    ["head"] = "avalonia",
                    ["platform"] = "macos",
                    ["rid"] = "osx-arm64",
                    ["arch"] = "arm64",
                    ["kind"] = "dmg",
                    ["platformLabel"] = "Avalonia Desktop macOS ARM64 Installer",
                    ["fileName"] = "chummer-avalonia-osx-arm64-installer.dmg",
                    ["downloadUrl"] = "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    ["sha256"] = "artifact-sha",
                    ["sizeBytes"] = 42L,
                    ["installAccessClass"] = "account_required"
                }
            }
        };

    private static JsonObject BuildProofFreshnessFacts(string status)
    {
        const string GeneratedAt = "2026-07-13T12:38:14Z";
        JsonObject facts = ReleaseProofEvidenceTestData.CreateFreshnessFacts(
            BuildFreshReleaseProof(GeneratedAt),
            DateTimeOffset.Parse(GeneratedAt));
        facts["status"] = status;
        return facts;
    }

    private static Dictionary<string, object?> BuildScalarDriftManifest()
    {
        Dictionary<string, object?> payload = BuildOptimisticProofFreshnessManifest("fresh");
        payload["version"] = "run-canonical-scalar";
        payload["rolloutReason"] = "Canonical rollout narrative.";
        payload["supportabilitySummary"] = "Canonical supportability narrative.";
        var artifacts = Assert.IsType<object[]>(payload["artifacts"]);
        var artifact = Assert.IsType<Dictionary<string, object?>>(Assert.Single(artifacts));
        artifact["sha256"] = "canonical-sha";
        return payload;
    }

    private static void ApplyRuntimeScalarDrift(Dictionary<string, object?> payload, string driftField)
    {
        switch (driftField)
        {
            case "version":
                payload["version"] = "run-runtime-scalar";
                break;
            case "channel":
                payload["channel"] = "public_stable";
                payload["channelId"] = "public_stable";
                break;
            case "status":
                payload["status"] = "revoked";
                break;
            case "rolloutState":
                payload["rolloutState"] = "live";
                break;
            case "rolloutReason":
                payload["rolloutReason"] = "Runtime rollout narrative.";
                break;
            case "supportabilityState":
                payload["supportabilityState"] = "gold_supported";
                break;
            case "supportabilitySummary":
                payload["supportabilitySummary"] = "Runtime supportability narrative.";
                break;
            case "proofStatus":
                var releaseProof = Assert.IsType<JsonObject>(payload["releaseProof"]);
                releaseProof["status"] = "failed";
                break;
            case "proofFlagshipReadiness":
                var proofWithReadiness = Assert.IsType<JsonObject>(payload["releaseProof"]);
                var readiness = Assert.IsType<JsonObject>(proofWithReadiness["flagshipReadiness"]);
                readiness["reason"] = "Runtime supplied a different readiness snapshot.";
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(driftField), driftField, "Unknown runtime scalar drift field.");
        }
    }

    private sealed class MutableTimeProvider(DateTimeOffset utcNow) : TimeProvider
    {
        private DateTimeOffset _utcNow = utcNow;

        public override DateTimeOffset GetUtcNow() => _utcNow;

        public void Advance(TimeSpan delta) => _utcNow = _utcNow.Add(delta);
    }

    private sealed class PublicReleaseManifestFixture : IDisposable
    {
        private readonly string _root;
        private readonly string _downloadsRoot;
        private readonly string _canonRoot;

        public PublicReleaseManifestFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "public-release-manifest-tests", Guid.NewGuid().ToString("N"));
            _downloadsRoot = Path.Combine(_root, "downloads");
            _canonRoot = Path.Combine(_root, "repo");
            Directory.CreateDirectory(_downloadsRoot);
            Directory.CreateDirectory(_canonRoot);
        }

        public PublicReleaseManifestService CreateService(
            HttpClient? httpClient = null,
            bool includeRuntimeUrl = false,
            IReadOnlyDictionary<string, string?>? additionalSettings = null,
            DateTimeOffset? evaluationInstant = null,
            TimeProvider? timeProvider = null,
            PrivacyLaunchGateSnapshot? privacyLaunchGate = null)
        {
            string localProofPath = Path.Combine(
                _canonRoot,
                ".codex-studio",
                "published",
                "HUB_LOCAL_RELEASE_PROOF.generated.json");
            Dictionary<string, string?> settings = new()
            {
                ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = _downloadsRoot,
                ["CHUMMER_PUBLIC_CANON_ROOT"] = _canonRoot,
                ["CHUMMER_PUBLIC_FLAGSHIP_READINESS_FILE"] = Path.Combine(_root, "fleet", ".codex-studio", "published", "FLAGSHIP_PRODUCT_READINESS.generated.json"),
                ["CHUMMER_PUBLIC_FINAL_GOLD_JANITOR_FILE"] = Path.Combine(_root, ".codex-studio", "published", "FINAL_GOLD_JANITOR.generated.json"),
                ["CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE"] = localProofPath,
                ["CHUMMER_RELEASE_REGISTRY_CURRENT_URL"] = string.Empty,
                ["CHUMMER_HUB_REGISTRY_BASE_URL"] = string.Empty,
                ["CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS"] = string.Empty,
                ["CHUMMER_RELEASE_DISABLED_ARTIFACT_IDS"] = string.Empty,
                ["CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS"] = "0"
            };
            if (includeRuntimeUrl)
            {
                settings["CHUMMER_RELEASE_REGISTRY_CURRENT_URL"] = "https://registry.local/api/v1/registry/release-channel/current";
            }

            if (additionalSettings is not null)
            {
                foreach ((string key, string? value) in additionalSettings)
                {
                    settings[key] = value;
                }
            }

            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(settings)
                .Build();

            return new PublicReleaseManifestService(
                configuration,
                httpClient,
                timeProvider ?? new FixedTimeProvider(evaluationInstant ?? ReadRegistryPublishedAtOrDefault()),
                privacyLaunchGate ?? PrivacyLaunchGate.ClearForTests);
        }

        private DateTimeOffset ReadRegistryPublishedAtOrDefault()
        {
            string path = Path.Combine(_downloadsRoot, "RELEASE_CHANNEL.generated.json");
            if (File.Exists(path))
            {
                using JsonDocument manifest = JsonDocument.Parse(File.ReadAllText(path));
                if (manifest.RootElement.TryGetProperty("publishedAt", out JsonElement publishedAt)
                    && publishedAt.TryGetDateTimeOffset(out DateTimeOffset value))
                {
                    return value;
                }
            }

            return new DateTimeOffset(2026, 7, 14, 0, 0, 0, TimeSpan.Zero);
        }

        private sealed class FixedTimeProvider(DateTimeOffset utcNow) : TimeProvider
        {
            public override DateTimeOffset GetUtcNow() => utcNow;
        }

        public void WriteRegistryManifest(bool includeProof)
        {
            var payload = new Dictionary<string, object?>
            {
                ["product"] = "chummer",
                ["channelId"] = "docker",
                ["version"] = "1.0.0-preview",
                ["publishedAt"] = "2026-03-25T15:23:09Z",
                ["status"] = "published",
                ["artifacts"] = new[]
                {
                    new Dictionary<string, object?>
                    {
                        ["artifactId"] = "avalonia-linux-x64-installer",
                        ["head"] = "avalonia",
                        ["platform"] = "linux",
                        ["arch"] = "x64",
                        ["kind"] = "installer",
                        ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                        ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                        ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                        ["sha256"] = "abc123",
                        ["sizeBytes"] = 123456789L,
                        ["installAccessClass"] = "account_required"
                    }
                }
            };

            if (includeProof)
            {
                payload["releaseProof"] = BuildRegistryProof("registry-passed");
            }

            WriteRegistryManifestRaw(payload);
        }

        public void WriteRegistryManifestWithProofStatus(string proofStatus)
        {
            var payload = new Dictionary<string, object?>
            {
                ["product"] = "chummer",
                ["channelId"] = "docker",
                ["version"] = "1.0.0-preview",
                ["publishedAt"] = "2026-03-25T15:23:09Z",
                ["status"] = "published",
                ["artifacts"] = new[]
                {
                    new Dictionary<string, object?>
                    {
                        ["artifactId"] = "avalonia-linux-x64-installer",
                        ["head"] = "avalonia",
                        ["platform"] = "linux",
                        ["arch"] = "x64",
                        ["kind"] = "installer",
                        ["platformLabel"] = "Avalonia Desktop Linux X64 Installer",
                        ["fileName"] = "chummer-avalonia-linux-x64-installer.deb",
                        ["downloadUrl"] = "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                        ["sha256"] = "abc123",
                        ["sizeBytes"] = 123456789L,
                        ["installAccessClass"] = "account_required"
                    }
                },
                ["releaseProof"] = BuildRegistryProof(proofStatus)
            };

            WriteRegistryManifestRaw(payload);
        }

        public void WriteRegistryManifestRaw(string version, IReadOnlyList<Dictionary<string, object?>> downloads)
        {
            Dictionary<string, object?> payload = new()
            {
                ["product"] = "chummer",
                ["channelId"] = "preview",
                ["version"] = version,
                ["publishedAt"] = "2026-04-02T20:38:58Z",
                ["status"] = "published",
                ["artifacts"] = downloads
            };
            WriteRegistryManifestRaw(payload);
        }

        public void WriteRegistryManifestRaw(Dictionary<string, object?> payload)
        {
            var manifestPath = Path.Combine(_downloadsRoot, "RELEASE_CHANNEL.generated.json");
            File.WriteAllText(manifestPath, JsonSerializer.Serialize(payload));
        }

        public void WriteRegistryManifestJson(string json)
            => File.WriteAllText(Path.Combine(_downloadsRoot, "RELEASE_CHANNEL.generated.json"), json);

        public void WriteCompatibilityManifestJson(string json)
            => File.WriteAllText(Path.Combine(_downloadsRoot, "releases.json"), json);

        public byte[] ReadRegistryManifestBytes()
            => File.ReadAllBytes(Path.Combine(_downloadsRoot, "RELEASE_CHANNEL.generated.json"));

        public void WriteLocalProof(string status, string baseUrl)
        {
            var proofDir = Path.Combine(_canonRoot, ".codex-studio", "published");
            Directory.CreateDirectory(proofDir);
            File.WriteAllText(
                Path.Combine(proofDir, "HUB_LOCAL_RELEASE_PROOF.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "chummer6-hub.local_release_proof",
                    ["status"] = status,
                    ["base_url"] = baseUrl,
                    ["generated_at"] = "2026-03-28T21:03:08Z",
                    ["journeys_passed"] = new[] { "install_claim_restore_continue", "build_explain_publish" },
                    ["proof_routes"] = new[] { "/downloads/install/avalonia-linux-x64-installer", "/account/support" }
                }));
        }

        public void WriteFlagshipReadiness(
            string status,
            IReadOnlyList<string>? missingCoverageKeys = null,
            IReadOnlyList<string>? warningCoverageKeys = null,
            bool includeBlockedJourneyEvidence = false)
        {
            string readinessDir = Path.Combine(_root, "fleet", ".codex-studio", "published");
            Directory.CreateDirectory(readinessDir);
            missingCoverageKeys ??= Array.Empty<string>();
            warningCoverageKeys ??= Array.Empty<string>();
            var payload = new Dictionary<string, object?>
            {
                ["contract_name"] = "fleet.flagship_product_readiness",
                ["status"] = status,
                ["completion_audit"] = new Dictionary<string, object?>
                {
                    ["reason"] = "Flagship product readiness planes are not green."
                },
                ["flagship_readiness_audit"] = new Dictionary<string, object?>
                {
                    ["reason"] = "flagship product readiness proof is not green: missing coverage: desktop_client",
                    ["warning_coverage_keys"] = warningCoverageKeys,
                    ["scoped_warning_coverage_keys"] = warningCoverageKeys,
                    ["missing_coverage_keys"] = missingCoverageKeys,
                    ["scoped_missing_coverage_keys"] = missingCoverageKeys
                }
            };
            if (includeBlockedJourneyEvidence)
            {
                payload["autofix_routing"] = new Dictionary<string, object?>
                {
                    ["routes"] = new[]
                    {
                        new Dictionary<string, object?>
                        {
                            ["journey_id"] = "build_explain_publish",
                            ["journey_state"] = "blocked",
                            ["reason"] = "media publication proof is missing"
                        }
                    }
                };
                payload["coverage_details"] = new Dictionary<string, object?>
                {
                    ["desktop_client"] = new Dictionary<string, object?>
                    {
                        ["evidence"] = new Dictionary<string, object?>
                        {
                            ["install_claim_restore_continue"] = "blocked"
                        }
                    }
                };
            }

            File.WriteAllText(
                Path.Combine(readinessDir, "FLAGSHIP_PRODUCT_READINESS.generated.json"),
                JsonSerializer.Serialize(payload));
        }

        public void WriteFlagshipReadinessRaw(Dictionary<string, object?> payload)
        {
            string readinessDir = Path.Combine(_root, "fleet", ".codex-studio", "published");
            Directory.CreateDirectory(readinessDir);
            File.WriteAllText(
                Path.Combine(readinessDir, "FLAGSHIP_PRODUCT_READINESS.generated.json"),
                JsonSerializer.Serialize(payload));
        }

        public void WriteFinalGoldReadiness(
            string status,
            string verdict,
            IReadOnlyList<string>? failures = null)
        {
            string readinessDir = Path.Combine(_root, ".codex-studio", "published");
            Directory.CreateDirectory(readinessDir);
            File.WriteAllText(
                Path.Combine(readinessDir, "FINAL_GOLD_JANITOR.generated.json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "chummer.final_gold_janitor",
                    ["status"] = status,
                    ["verdict"] = verdict,
                    ["generated_at_utc"] = "2026-06-30T09:10:00Z",
                    ["failures"] = failures ?? Array.Empty<string>()
                }));
        }

        private static Dictionary<string, object?> BuildRegistryProof(string status)
            => new()
            {
                ["status"] = status,
                ["generatedAt"] = "2026-03-28T21:00:00Z",
                ["baseUrl"] = "https://registry.chummer.run",
                ["journeysPassed"] = new[] { "registry_journey" },
                ["proofRoutes"] = new[] { "/downloads" }
            };

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed class StaticJsonHandler : HttpMessageHandler
    {
        private readonly string _payload;

        public StaticJsonHandler(string payload)
        {
            _payload = payload;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.OK)
            {
                Content = new StringContent(_payload)
            });
    }

    private sealed class CountingStaticJsonHandler : HttpMessageHandler
    {
        private readonly string _payload;

        public CountingStaticJsonHandler(string payload)
        {
            _payload = payload;
        }

        public int CallCount { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            CallCount += 1;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(_payload)
            });
        }
    }

    private sealed class SlowJsonHandler : HttpMessageHandler
    {
        private readonly TimeSpan _delay;

        public SlowJsonHandler(TimeSpan delay)
        {
            _delay = delay;
        }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            await Task.Delay(_delay, cancellationToken);
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("{}")
            };
        }
    }
}
