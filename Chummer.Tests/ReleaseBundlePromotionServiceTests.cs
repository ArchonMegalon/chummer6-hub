using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseBundlePromotionServiceTests
{
    private static readonly JsonSerializerOptions TestJsonOptions = new(JsonSerializerDefaults.Web);

    [Fact]
    public async Task PromoteAsyncReplacesShelfWithIncomingBundleArtifacts()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        fixture.WriteLiveArtifact(
            artifactId: "avalonia-linux-x64-installer",
            fileName: "chummer-avalonia-linux-x64-installer.deb",
            platform: "linux",
            arch: "x64",
            kind: "installer",
            bytes: "linux-live");

        string macFileName = "chummer-avalonia-osx-arm64-installer.dmg";
        byte[] macBytes = "mac-live"u8.ToArray();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260401-215500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-dmg",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: macFileName,
                    Bytes: macBytes,
                    RequiresSigning: true,
                    RequiresNotarization: true)
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Equal("run-20260401-215500", result.Version);
        Assert.Contains("avalonia-osx-arm64-dmg", result.PromotedArtifactIds);
        Assert.Contains("https://chummer.run/downloads/install/avalonia-osx-arm64-dmg", result.InstallDispatchUrls);

        JsonDocument compatibility = fixture.ReadCompatibilityManifest();
        string[] downloadIds = compatibility.RootElement.GetProperty("downloads")
            .EnumerateArray()
            .Select(item => item.GetProperty("id").GetString()!)
            .OrderBy(static value => value, StringComparer.OrdinalIgnoreCase)
            .ToArray();
        Assert.Equal(["avalonia-osx-arm64-dmg"], downloadIds);

        JsonDocument canonical = fixture.ReadCanonicalManifest();
        string[] canonicalIds = canonical.RootElement.GetProperty("artifacts")
            .EnumerateArray()
            .Select(item => item.GetProperty("artifactId").GetString()!)
            .OrderBy(static value => value, StringComparer.OrdinalIgnoreCase)
            .ToArray();
        Assert.Equal(["avalonia-osx-arm64-dmg"], canonicalIds);

        Assert.Equal(1, canonical.RootElement.GetProperty("registryBoundaryCoverage").GetProperty("persistence").GetProperty("artifactCount").GetInt32());
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", macFileName)));
    }

    [Fact]
    public async Task PromoteAsyncKeepsPublishedArtifactCountsAlignedWithRegistryBoundaryCoverage()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        fixture.WriteLiveArtifact(
            artifactId: "avalonia-linux-x64-installer",
            fileName: "chummer-avalonia-linux-x64-installer.deb",
            platform: "linux",
            arch: "x64",
            kind: "installer",
            bytes: "linux-live");
        fixture.AppendLiveArtifact(
            artifactId: "avalonia-win-x64-installer",
            fileName: "chummer-avalonia-win-x64-installer.exe",
            platform: "windows",
            arch: "x64",
            kind: "installer",
            bytes: "windows-live");

        string bundlePath = fixture.CreateBundle(
            version: "run-20260525-204932",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-installer"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview"),
                new BundleArtifact(
                    ArtifactId: "blazor-desktop-osx-arm64-installer",
                    Head: "blazor-desktop",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-blazor-desktop-osx-arm64-installer.dmg",
                    Bytes: "mac-installer-blazor"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview"),
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-archive",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "archive",
                    FileName: "chummer-avalonia-osx-arm64.zip",
                    Bytes: "mac-archive"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false),
                new BundleArtifact(
                    ArtifactId: "blazor-desktop-osx-arm64-archive",
                    Head: "blazor-desktop",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "archive",
                    FileName: "chummer-blazor-desktop-osx-arm64.zip",
                    Bytes: "mac-archive-blazor"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false)
            ],
            publishedAt: "2026-05-25T20:51:10Z",
            proofGeneratedAt: "2026-05-25T20:49:32Z");

        await fixture.PromoteAsync(bundlePath);

        using JsonDocument compatibility = fixture.ReadCompatibilityManifest();
        using JsonDocument canonical = fixture.ReadCanonicalManifest();

        Assert.Equal(4, canonical.RootElement.GetProperty("artifacts").GetArrayLength());
        Assert.Equal(4, compatibility.RootElement.GetProperty("downloads").GetArrayLength());
        Assert.Equal(4, canonical.RootElement.GetProperty("registryBoundaryCoverage").GetProperty("persistence").GetProperty("artifactCount").GetInt32());
        Assert.Equal(4, canonical.RootElement.GetProperty("registryBoundaryCoverage").GetProperty("compatibility").GetProperty("compatibleArtifactCount").GetInt32());
    }

    [Fact]
    public async Task PromoteAsyncRejectsMacArtifactWithoutPromotionEvidence()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260401-220500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-dmg",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-live"u8.ToArray(),
                    RequiresSigning: true,
                    RequiresNotarization: true)
            ],
            includePromotionEvidence: false);

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() => fixture.PromoteAsync(bundlePath));
        Assert.Contains("public-promotion.json", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task PromoteAsyncAllowsUnsignedMacPreviewArtifactWhenEvidenceMarksSkippedPreview()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260401-221500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-dmg",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Equal("run-20260401-221500", result.Version);
        Assert.Contains("avalonia-osx-arm64-dmg", result.PromotedArtifactIds);
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", "chummer-avalonia-osx-arm64-installer.dmg")));
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "startup-smoke", "startup-smoke-avalonia-macos-arm64.receipt.json")));
    }

    [Fact]
    public async Task PromoteAsyncAllowsArtifactSha256ReceiptFieldAndPlatformAlias()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260401-223000",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-dmg",
                    Head: "avalonia",
                    Platform: "osx",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview",
                    UseArtifactSha256ReceiptField: true,
                    ReceiptPlatformOverride: "darwin")
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Equal("run-20260401-223000", result.Version);
        Assert.Contains("avalonia-osx-arm64-dmg", result.PromotedArtifactIds);
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", "chummer-avalonia-osx-arm64-installer.dmg")));
    }

    [Fact]
    public async Task PromoteAsyncAllowsRidStylePlatformTokens()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260401-224000",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-dmg",
                    Head: "avalonia",
                    Platform: "osx-arm64",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview",
                    ReceiptPlatformOverride: "osx-arm64")
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Equal("run-20260401-224000", result.Version);
        Assert.Contains("avalonia-osx-arm64-dmg", result.PromotedArtifactIds);
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", "chummer-avalonia-osx-arm64-installer.dmg")));
    }

    [Fact]
    public async Task PromoteAsyncAllowsUnsignedWindowsPreviewArtifactWhenEvidenceMarksSkippedPreview()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260401-222500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ]);

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Equal("run-20260401-222500", result.Version);
        Assert.Contains("avalonia-win-x64-installer", result.PromotedArtifactIds);
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", "chummer-avalonia-win-x64-installer.exe")));
    }

    [Fact]
    public async Task PromoteAsyncAllowsExplicitUnsignedWindowsReleaseArtifactWhenEvidenceMarksUnsignedPublicRelease()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260618-142358",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows-stable"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "unsigned_public_release",
                    StartupSmokeStatusOverride: "skipped_incompatible_host")
            ],
            channel: "stable");

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Equal("run-20260618-142358", result.Version);
        Assert.Contains("avalonia-win-x64-installer", result.PromotedArtifactIds);
        Assert.Contains("https://chummer.run/downloads/files/chummer-avalonia-win-x64-installer.exe", result.DirectFileUrls);
        Assert.DoesNotContain(result.DirectFileUrls, static url => url.Contains("https://chummer.run/https://", StringComparison.OrdinalIgnoreCase));
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "files", "chummer-avalonia-win-x64-installer.exe")));
    }

    [Fact]
    public async Task PromoteAsyncCopiesWindowsProofPayloadWhenBundleProvidesIt()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260412-192500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ],
            proofArtifacts:
            [
                new ProofArtifact(
                    RelativePath: "windows/chummer-avalonia-win-x64-installer.exe",
                    Bytes: "win-proof"u8.ToArray()),
                new ProofArtifact(
                    RelativePath: "windows/chummer-blazor-desktop-win-x64-installer.exe",
                    Bytes: "win-proof-blazor"u8.ToArray())
            ]);

        await fixture.PromoteAsync(bundlePath);

        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "proof", "windows", "chummer-avalonia-win-x64-installer.exe")));
        Assert.True(File.Exists(Path.Combine(fixture.DownloadsRoot, "proof", "windows", "chummer-blazor-desktop-win-x64-installer.exe")));
    }

    [Fact]
    public async Task PromoteAsyncMakesPromotedMacPreviewVisibleOnDownloadsAsInstallCommand()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260409-061506",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview"),
                new BundleArtifact(
                    ArtifactId: "blazor-desktop-osx-arm64-installer",
                    Head: "blazor-desktop",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-blazor-desktop-osx-arm64-installer.dmg",
                    Bytes: "mac-preview-alt"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        await fixture.PromoteAsync(bundlePath);

        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = fixture.DownloadsRoot,
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        PublicReleaseManifestDto manifest = new PublicReleaseManifestService(configuration).LoadManifest();
        ReleaseSelectionService selection = new(new PublicCanonFileLoader(configuration));

        ReleaseExperienceViewModel experience = selection.BuildExperience(
            manifest,
            userAgent: "Mozilla/5.0 (Macintosh; Apple Silicon Mac OS X 14_4) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15 arm64",
            authenticated: true);

        Assert.Null(experience.Recommended);
        Assert.False(experience.RequestedPlatformHasPublicDownload);
        Assert.NotNull(experience.PlatformShelfNoticeTitle);
        Assert.Contains(experience.PlatformAvailability, item => item.PlatformId == "macos" && !item.PubliclyAvailable);
        Assert.DoesNotContain(experience.Alternatives, item => item.Artifact.Id == "blazor-desktop-osx-arm64-installer");
    }

    [Fact]
    public async Task PromoteAsyncReplacesDesktopTupleCoverageWithIncomingBundleShelf()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string initialBundle = fixture.CreateBundle(
            version: "run-20260419-190000",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-linux-x64-installer",
                    Head: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    Bytes: "linux"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false),
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);
        await fixture.PromoteAsync(initialBundle);

        string macBundle = fixture.CreateBundle(
            version: "run-20260419-201110",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        await fixture.PromoteAsync(macBundle);

        using JsonDocument compatibility = fixture.ReadCompatibilityManifest();
        JsonElement coverage = compatibility.RootElement.GetProperty("desktopTupleCoverage");
        Assert.True(coverage.GetProperty("complete").GetBoolean());
        string[] promotedTupleIds = coverage.GetProperty("promotedInstallerTuples")
            .EnumerateArray()
            .Select(item => item.GetProperty("tupleId").GetString()!)
            .OrderBy(static value => value, StringComparer.Ordinal)
            .ToArray();
        Assert.Equal(["avalonia:macos:osx-arm64"], promotedTupleIds);
        Assert.Equal(
            ["macos"],
            coverage.GetProperty("requiredDesktopPlatforms")
                .EnumerateArray()
                .Select(item => item.GetString()!)
                .ToArray());
        Assert.Equal("promoted_preview", compatibility.RootElement.GetProperty("rolloutState").GetString());
        Assert.Equal("preview_supported", compatibility.RootElement.GetProperty("supportabilityState").GetString());
    }

    [Fact]
    public async Task PromoteAsyncFiltersExternalProofRequestsAgainstIncomingShelfCoverage()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string initialBundle = fixture.CreateBundle(
            version: "run-20260419-180000",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-linux-x64-installer",
                    Head: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    Bytes: "linux"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false)
            ]);
        await fixture.PromoteAsync(initialBundle);

        string macBundle = fixture.CreateBundle(
            version: "run-20260419-201110",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        await fixture.PromoteAsync(macBundle);

        using JsonDocument compatibility = fixture.ReadCompatibilityManifest();
        JsonElement coverage = compatibility.RootElement.GetProperty("desktopTupleCoverage");
        string[] promotedTupleIds = coverage.GetProperty("promotedInstallerTuples")
            .EnumerateArray()
            .Select(item => item.GetProperty("tupleId").GetString()!)
            .ToArray();
        Assert.Equal(["avalonia:macos:osx-arm64"], promotedTupleIds);
        Assert.Empty(coverage.GetProperty("externalProofRequests")
            .EnumerateArray()
            .ToArray());
    }

    [Fact]
    public async Task PromoteAsyncPublishesCanonicalRouteTruthWithRevokeSource()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260502-214500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-route-truth"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        await fixture.PromoteAsync(bundlePath);

        using JsonDocument canonical = fixture.ReadCanonicalManifest();
        JsonElement[] rows = canonical.RootElement
            .GetProperty("desktopTupleCoverage")
            .GetProperty("desktopRouteTruth")
            .EnumerateArray()
            .ToArray();

        Assert.NotEmpty(rows);
        foreach (JsonElement row in rows)
        {
            Assert.True(row.TryGetProperty("revokeSource", out JsonElement revokeSource));
            Assert.Equal("none", revokeSource.GetString());

            if (row.GetProperty("promotionState").GetString() == "promoted")
            {
                string artifactId = row.GetProperty("artifactId").GetString()!;
                Assert.Contains(artifactId, row.GetProperty("installPostureReason").GetString());
            }
        }
    }

    [Fact]
    public async Task PromoteAsyncMarksPromotedPrimaryInstallerAsReinstallRecoveryWhenFallbackIsMissing()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260618-142358",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-linux-x64-installer",
                    Head: "avalonia",
                    Platform: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    Bytes: "linux-stable"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false)
            ],
            channel: "stable");

        await fixture.PromoteAsync(bundlePath);

        using JsonDocument canonical = fixture.ReadCanonicalManifest();
        JsonElement primary = canonical.RootElement
            .GetProperty("desktopTupleCoverage")
            .GetProperty("desktopRouteTruth")
            .EnumerateArray()
            .Single(row => row.GetProperty("tupleId").GetString() == "avalonia:linux:linux-x64");

        Assert.Equal("promoted", primary.GetProperty("promotionState").GetString());
        Assert.Equal("primary_reinstall_available", primary.GetProperty("rollbackState").GetString());
        Assert.Equal("primary_installer_reinstall_available", primary.GetProperty("rollbackReasonCode").GetString());
        Assert.Contains("avalonia-linux-x64-installer", primary.GetProperty("rollbackReason").GetString());

        JsonElement releaseChannel = canonical.RootElement
            .GetProperty("publicTrustMetrics")
            .GetProperty("releaseChannel");
        Assert.Equal("live", releaseChannel.GetProperty("posture").GetString());
        Assert.Equal("public_stable", releaseChannel.GetProperty("rolloutState").GetString());
        Assert.Equal("gold_supported", releaseChannel.GetProperty("supportabilityState").GetString());
        Assert.Equal(1, releaseChannel.GetProperty("recommendedRouteCount").GetInt32());

        JsonElement boundaryReleaseChannel = canonical.RootElement
            .GetProperty("registryBoundaryCoverage")
            .GetProperty("releaseChannel");
        Assert.Equal("published", boundaryReleaseChannel.GetProperty("publicationStatus").GetString());
        Assert.Equal("public_stable", boundaryReleaseChannel.GetProperty("rolloutState").GetString());
        Assert.Equal("gold_supported", boundaryReleaseChannel.GetProperty("supportabilityState").GetString());
        Assert.True(boundaryReleaseChannel.GetProperty("desktopTupleComplete").GetBoolean());
        Assert.Equal(1, boundaryReleaseChannel.GetProperty("promotedInstallerTupleCount").GetInt32());
        Assert.Equal("live", boundaryReleaseChannel.GetProperty("publicTrustPosture").GetString());
    }

    [Fact]
    public async Task PromoteAsyncRebuildsInstallAwareRegistryFromNormalizedRouteTruth()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260522-201500",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-install-aware"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        await fixture.PromoteAsync(bundlePath);

        using JsonDocument canonical = fixture.ReadCanonicalManifest();
        JsonElement[] rows = canonical.RootElement
            .GetProperty("installAwareArtifactRegistry")
            .EnumerateArray()
            .ToArray();

        JsonElement primary = Assert.Single(
            rows,
            row => row.GetProperty("artifactId").GetString() == "avalonia-osx-arm64-installer");
        Assert.True(primary.GetProperty("currentForInstalledBuild").GetBoolean());
        Assert.Contains(
            "primary-route avalonia:macos:osx-arm64 current",
            primary.GetProperty("channelRationale").GetString(),
            StringComparison.Ordinal);

        JsonElement fallback = Assert.Single(
            rows,
            row => row.GetProperty("artifactId").GetString() == "blazor-desktop-osx-arm64-installer");
        Assert.False(fallback.GetProperty("currentForInstalledBuild").GetBoolean());
    }

    [Fact]
    public async Task PromoteAsyncDowngradesPassedReleaseProofWhenItPredatesCurrentPublicationWindow()
    {
        using var fixture = new ReleaseBundlePromotionFixture();

        string bundlePath = fixture.CreateBundle(
            version: "run-20260501-040136",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ],
            publishedAt: "2026-05-01T04:01:36Z",
            proofGeneratedAt: "2026-04-25T22:43:00Z");

        await fixture.PromoteAsync(bundlePath);

        using JsonDocument compatibility = fixture.ReadCompatibilityManifest();
        using JsonDocument canonical = fixture.ReadCanonicalManifest();

        Assert.Equal("review_required", compatibility.RootElement.GetProperty("releaseProof").GetProperty("status").GetString());
        Assert.Equal("review_required", canonical.RootElement.GetProperty("releaseProof").GetProperty("status").GetString());
        Assert.Equal("review_required", compatibility.RootElement.GetProperty("supportabilityState").GetString());
    }

    [Fact]
    public async Task PromoteAsyncNormalizesExistingCanonicalArtifactsToIncomingChannelAndVersion()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        fixture.WriteLiveArtifact(
            artifactId: "avalonia-linux-x64-installer",
            fileName: "chummer-avalonia-linux-x64-installer.deb",
            platform: "linux",
            arch: "x64",
            kind: "installer",
            bytes: "linux-live");
        fixture.SetCanonicalMetadata(
            channelId: "public_stable",
            version: "run-20260401-200000");

        string bundlePath = fixture.CreateBundle(
            version: "run-20260420-090000",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-preview"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        await fixture.PromoteAsync(bundlePath);
        using JsonDocument canonical = fixture.ReadCanonicalManifest();

        foreach (JsonElement artifact in canonical.RootElement.GetProperty("artifacts").EnumerateArray())
        {
            Assert.Equal("preview", artifact.GetProperty("channel").GetString());
            Assert.Equal("preview", artifact.GetProperty("channelId").GetString());
            Assert.Equal("run-20260420-090000", artifact.GetProperty("version").GetString());
            Assert.Equal("run-20260420-090000", artifact.GetProperty("releaseVersion").GetString());
        }
    }

    private sealed class ReleaseBundlePromotionFixture : IDisposable
    {
        private readonly string _root;
        private readonly string _downloadsRoot;

        public ReleaseBundlePromotionFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "release-bundle-promotion-tests", Guid.NewGuid().ToString("N"));
            _downloadsRoot = Path.Combine(_root, "downloads");
            Directory.CreateDirectory(Path.Combine(_downloadsRoot, "files"));
        }

        public string DownloadsRoot => _downloadsRoot;

        public async Task<ReleaseBundlePromotionResult> PromoteAsync(string bundlePath)
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = _downloadsRoot,
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://chummer.run/auth/google/callback"
                })
                .Build();

            var service = new ReleaseBundlePromotionService(
                configuration,
                NullLogger<ReleaseBundlePromotionService>.Instance);

            await using FileStream stream = File.OpenRead(bundlePath);
            return await service.PromoteAsync(Path.GetFileName(bundlePath), stream, CancellationToken.None);
        }

        public void WriteLiveArtifact(
            string artifactId,
            string fileName,
            string platform,
            string arch,
            string kind,
            string bytes)
        {
            string path = Path.Combine(_downloadsRoot, "files", fileName);
            File.WriteAllText(path, bytes);
            string sha = Sha256For(path);
            long size = new FileInfo(path).Length;

            WriteCompatibilityManifest(
                Path.Combine(_downloadsRoot, "releases.json"),
                version: "run-20260401-200000",
                downloads:
                [
                    new CompatibilityArtifact(
                        Id: artifactId,
                        Platform: $"Avalonia Desktop {platform} {arch}",
                        Url: $"/downloads/files/{fileName}",
                        Sha256: sha,
                        SizeBytes: size,
                        Head: "avalonia",
                        PlatformId: $"{platform}-{arch}",
                        Arch: arch,
                        Kind: kind,
                        FileName: fileName,
                        InstallAccessClass: "account_required")
                ]);

            WriteCanonicalManifest(
                Path.Combine(_downloadsRoot, "RELEASE_CHANNEL.generated.json"),
                version: "run-20260401-200000",
                artifacts:
                [
                    new CanonicalArtifact(
                        ArtifactId: artifactId,
                        Head: "avalonia",
                        Platform: platform,
                        Arch: arch,
                        Kind: kind,
                        FileName: fileName,
                        DownloadUrl: $"/downloads/files/{fileName}",
                        Sha256: sha,
                        SizeBytes: size,
                        PlatformLabel: $"Avalonia Desktop {platform} {arch}")
                ]);
        }

        public void AppendLiveArtifact(
            string artifactId,
            string fileName,
            string platform,
            string arch,
            string kind,
            string bytes,
            string head = "avalonia")
        {
            string path = Path.Combine(_downloadsRoot, "files", fileName);
            File.WriteAllText(path, bytes);
            string sha = Sha256For(path);
            long size = new FileInfo(path).Length;

            string compatibilityPath = Path.Combine(_downloadsRoot, "releases.json");
            JsonObject compatibility = JsonNode.Parse(File.ReadAllText(compatibilityPath))!.AsObject();
            JsonArray downloads = compatibility["downloads"]!.AsArray();
            downloads.Add(JsonSerializer.SerializeToNode(new CompatibilityArtifact(
                Id: artifactId,
                Platform: $"Avalonia Desktop {platform} {arch}",
                Url: $"/downloads/files/{fileName}",
                Sha256: sha,
                SizeBytes: size,
                Head: head,
                PlatformId: $"{platform}-{arch}",
                Arch: arch,
                Kind: kind,
                FileName: fileName,
                InstallAccessClass: "account_required"), TestJsonOptions));
            File.WriteAllText(compatibilityPath, compatibility.ToJsonString(TestJsonOptions));

            string canonicalPath = Path.Combine(_downloadsRoot, "RELEASE_CHANNEL.generated.json");
            JsonObject canonical = JsonNode.Parse(File.ReadAllText(canonicalPath))!.AsObject();
            JsonArray artifacts = canonical["artifacts"]!.AsArray();
            artifacts.Add(JsonSerializer.SerializeToNode(new CanonicalArtifact(
                ArtifactId: artifactId,
                Head: head,
                Platform: platform,
                Arch: arch,
                Kind: kind,
                FileName: fileName,
                DownloadUrl: $"/downloads/files/{fileName}",
                Sha256: sha,
                SizeBytes: size,
                PlatformLabel: $"Avalonia Desktop {platform} {arch}"), TestJsonOptions));
            File.WriteAllText(canonicalPath, canonical.ToJsonString(TestJsonOptions));
        }

        public string CreateBundle(
            string version,
            IReadOnlyList<BundleArtifact> artifacts,
            bool includePromotionEvidence = true,
            IReadOnlyList<ProofArtifact>? proofArtifacts = null,
            string publishedAt = "2026-04-01T20:00:00Z",
            string proofGeneratedAt = "2026-04-01T20:00:00Z",
            string channel = "preview")
        {
            string bundleRoot = Path.Combine(_root, "bundle-" + Guid.NewGuid().ToString("N"));
            string filesRoot = Path.Combine(bundleRoot, "files");
            string smokeRoot = Path.Combine(bundleRoot, "startup-smoke");
            string evidenceRoot = Path.Combine(bundleRoot, "release-evidence");
            Directory.CreateDirectory(filesRoot);
            Directory.CreateDirectory(smokeRoot);
            Directory.CreateDirectory(evidenceRoot);

            List<CompatibilityArtifact> compatibilityArtifacts = new(artifacts.Count);
            List<CanonicalArtifact> canonicalArtifacts = new(artifacts.Count);
            List<PromotionEvidenceArtifact> evidenceArtifacts = new(artifacts.Count);

            foreach (BundleArtifact artifact in artifacts)
            {
                string filePath = Path.Combine(filesRoot, artifact.FileName);
                File.WriteAllBytes(filePath, artifact.Bytes);
                string sha = Sha256For(filePath);
                long size = new FileInfo(filePath).Length;
                string downloadUrl = $"/downloads/files/{artifact.FileName}";

                compatibilityArtifacts.Add(new CompatibilityArtifact(
                    Id: artifact.ArtifactId,
                    Platform: $"Avalonia Desktop {artifact.Platform} {artifact.Arch}",
                    Url: downloadUrl,
                    Sha256: sha,
                    SizeBytes: size,
                    Head: artifact.Head,
                    PlatformId: $"{artifact.Platform}-{artifact.Arch}",
                    Arch: artifact.Arch,
                    Kind: artifact.Kind,
                    FileName: artifact.FileName,
                    InstallAccessClass: "account_required"));

                canonicalArtifacts.Add(new CanonicalArtifact(
                    ArtifactId: artifact.ArtifactId,
                    Head: artifact.Head,
                    Platform: artifact.Platform,
                    Arch: artifact.Arch,
                    Kind: artifact.Kind,
                    FileName: artifact.FileName,
                    DownloadUrl: downloadUrl,
                    Sha256: sha,
                    SizeBytes: size,
                    PlatformLabel: $"Avalonia Desktop {artifact.Platform} {artifact.Arch}"));

                if (artifact.Kind is "installer" or "dmg" or "pkg" or "msix")
                {
                    File.WriteAllText(
                        Path.Combine(smokeRoot, $"startup-smoke-{artifact.Head}-{artifact.Platform}-{artifact.Arch}.receipt.json"),
                        JsonSerializer.Serialize(new
                        {
                            headId = artifact.Head,
                            platform = artifact.ReceiptPlatformOverride ?? artifact.Platform,
                            arch = artifact.Arch,
                            artifactDigest = artifact.UseArtifactSha256ReceiptField ? null : $"sha256:{sha}",
                            artifactSha256 = artifact.UseArtifactSha256ReceiptField ? sha : null
                        }, TestJsonOptions));
                }

                evidenceArtifacts.Add(new PromotionEvidenceArtifact(
                    ArtifactId: artifact.ArtifactId,
                    FileName: artifact.FileName,
                    Platform: artifact.Platform,
                    PromotionStatus: "pass",
                    StartupSmokeStatus: artifact.StartupSmokeStatusOverride ?? "pass",
                    SigningStatus: artifact.SigningStatusOverride ?? (artifact.RequiresSigning ? "pass" : null),
                    NotarizationStatus: artifact.NotarizationStatusOverride ?? (artifact.RequiresNotarization ? "pass" : null)));
            }

            WriteCompatibilityManifest(
                Path.Combine(bundleRoot, "releases.json"),
                version,
                compatibilityArtifacts,
                publishedAt,
                proofGeneratedAt,
                channel);
            WriteCanonicalManifest(
                Path.Combine(bundleRoot, "RELEASE_CHANNEL.generated.json"),
                version,
                canonicalArtifacts,
                publishedAt,
                proofGeneratedAt,
                channel);

            if (includePromotionEvidence)
            {
                File.WriteAllText(
                    Path.Combine(evidenceRoot, "public-promotion.json"),
                    JsonSerializer.Serialize(new
                    {
                        contractName = "chummer.run.desktop_release_publication",
                        generatedAt = "2026-04-01T21:55:00Z",
                        artifacts = evidenceArtifacts
                    }, TestJsonOptions));
            }

            if (proofArtifacts is { Count: > 0 })
            {
                string proofRoot = Path.Combine(bundleRoot, "proof");
                foreach (ProofArtifact proofArtifact in proofArtifacts)
                {
                    string targetPath = Path.Combine(proofRoot, proofArtifact.RelativePath.Replace('/', Path.DirectorySeparatorChar));
                    string? targetDirectory = Path.GetDirectoryName(targetPath);
                    if (!string.IsNullOrWhiteSpace(targetDirectory))
                    {
                        Directory.CreateDirectory(targetDirectory);
                    }

                    File.WriteAllBytes(targetPath, proofArtifact.Bytes);
                }
            }

            string zipPath = Path.Combine(_root, $"{Path.GetFileName(bundleRoot)}.zip");
            ZipFile.CreateFromDirectory(bundleRoot, zipPath);
            return zipPath;
        }

        public JsonDocument ReadCompatibilityManifest()
            => JsonDocument.Parse(File.ReadAllText(Path.Combine(_downloadsRoot, "releases.json")));

        public JsonDocument ReadCanonicalManifest()
            => JsonDocument.Parse(File.ReadAllText(Path.Combine(_downloadsRoot, "RELEASE_CHANNEL.generated.json")));

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }

        public void SetCanonicalMetadata(string channelId, string version)
        {
            string path = Path.Combine(_downloadsRoot, "RELEASE_CHANNEL.generated.json");
            JsonNode? root = JsonNode.Parse(File.ReadAllText(path));
            if (root is not JsonObject canonical)
            {
                return;
            }

            canonical["channel"] = channelId;
            canonical["channelId"] = channelId;
            canonical["version"] = version;

            if (canonical["artifacts"] is JsonArray artifacts)
            {
                foreach (JsonObject artifact in artifacts.OfType<JsonObject>())
                {
                    artifact["channel"] = channelId;
                    artifact["channelId"] = channelId;
                    artifact["version"] = version;
                    artifact["releaseVersion"] = version;
                }
            }

            File.WriteAllText(path, canonical.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
        }

        private static void WriteCompatibilityManifest(
            string path,
            string version,
            IReadOnlyList<CompatibilityArtifact> downloads,
            string publishedAt = "2026-04-01T20:00:00Z",
            string proofGeneratedAt = "2026-04-01T20:00:00Z",
            string channel = "preview")
        {
            File.WriteAllText(
                path,
                JsonSerializer.Serialize(new
                {
                    version,
                    channel,
                    publishedAt,
                    releaseProof = new
                    {
                        status = "passed",
                        generatedAt = proofGeneratedAt,
                        baseUrl = "https://chummer.run",
                        journeysPassed = new[] { "build_explain_publish" },
                        proofRoutes = downloads.Select(static download => $"/downloads/install/{download.Id}").ToArray()
                    },
                    downloads
                }, TestJsonOptions));
        }

        private static void WriteCanonicalManifest(
            string path,
            string version,
            IReadOnlyList<CanonicalArtifact> artifacts,
            string publishedAt = "2026-04-01T20:00:00Z",
            string proofGeneratedAt = "2026-04-01T20:00:00Z",
            string channel = "preview")
        {
            string[] proofRoutes = artifacts
                .Select(static artifact => $"/downloads/install/{artifact.ArtifactId}")
                .ToArray();

            File.WriteAllText(
                path,
                JsonSerializer.Serialize(new
                {
                    schemaVersion = 1,
                    product = "chummer",
                    channelId = channel,
                    version,
                    publishedAt,
                    status = "published",
                    releaseProof = new
                    {
                        status = "passed",
                        generatedAt = proofGeneratedAt,
                        baseUrl = "https://chummer.run",
                        journeysPassed = new[] { "build_explain_publish" },
                        proofRoutes
                    },
                    artifacts,
                    registryBoundaryCoverage = new
                    {
                        persistence = new
                        {
                            artifactCount = artifacts.Count
                        },
                        compatibility = new
                        {
                            compatibleArtifactCount = artifacts.Count
                        }
                    }
                }, TestJsonOptions));
        }

        private static string Sha256For(string path)
        {
            using var sha = SHA256.Create();
            using FileStream stream = File.OpenRead(path);
            return Convert.ToHexString(sha.ComputeHash(stream)).ToLowerInvariant();
        }
    }

    private sealed record BundleArtifact(
        string ArtifactId,
        string Head,
        string Platform,
        string Arch,
        string Kind,
        string FileName,
        byte[] Bytes,
        bool RequiresSigning,
        bool RequiresNotarization,
        string? SigningStatusOverride = null,
        string? NotarizationStatusOverride = null,
        string? StartupSmokeStatusOverride = null,
        bool UseArtifactSha256ReceiptField = false,
        string? ReceiptPlatformOverride = null);

    private sealed record CompatibilityArtifact(
        string Id,
        string Platform,
        string Url,
        string Sha256,
        long SizeBytes,
        string Head,
        string PlatformId,
        string Arch,
        string Kind,
        string FileName,
        string InstallAccessClass);

    private sealed record CanonicalArtifact(
        string ArtifactId,
        string Head,
        string Platform,
        string Arch,
        string Kind,
        string FileName,
        string DownloadUrl,
        string Sha256,
        long SizeBytes,
        string PlatformLabel);

    private sealed record PromotionEvidenceArtifact(
        string ArtifactId,
        string FileName,
        string Platform,
        string PromotionStatus,
        string StartupSmokeStatus,
        string? SigningStatus,
        string? NotarizationStatus);

    private sealed record ProofArtifact(
        string RelativePath,
        byte[] Bytes);
}
