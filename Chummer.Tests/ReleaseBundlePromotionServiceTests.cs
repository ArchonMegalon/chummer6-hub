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

    private static string Sha256For(byte[] bytes)
        => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

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
    public async Task PromoteAsyncPreservesRegistryAuthoredManifestBytesAndBindsDigests()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260717-010203",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "registry-byte-proof"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        byte[] expectedCompatibility = fixture.ReadBundleEntryBytes(bundlePath, "releases.json");
        byte[] expectedCanonical = fixture.ReadBundleEntryBytes(bundlePath, "RELEASE_CHANNEL.generated.json");

        ReleaseBundlePromotionResult result = await fixture.PromoteAsync(bundlePath);

        Assert.Equal(expectedCompatibility, File.ReadAllBytes(Path.Combine(fixture.DownloadsRoot, "releases.json")));
        Assert.Equal(expectedCanonical, File.ReadAllBytes(Path.Combine(fixture.DownloadsRoot, "RELEASE_CHANNEL.generated.json")));
        Assert.Equal($"sha256:{Sha256For(expectedCompatibility)}", result.CompatibilityManifestSha256);
        Assert.Equal($"sha256:{Sha256For(expectedCanonical)}", result.CanonicalManifestSha256);

        using JsonDocument receipt = JsonDocument.Parse(
            File.ReadAllBytes(Path.Combine(fixture.DownloadsRoot, ".release-channel-activation.json")));
        Assert.Equal(result.CompatibilityManifestSha256, receipt.RootElement.GetProperty("compatibilityManifestSha256").GetString());
        Assert.Equal(result.CanonicalManifestSha256, receipt.RootElement.GetProperty("canonicalManifestSha256").GetString());
    }

    [Fact]
    public async Task PromoteAsyncKeepsMacOnlyRegistryShelfIncompleteAndReviewRequired()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260717-020304",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "mac-only"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ]);

        await fixture.PromoteAsync(bundlePath);

        using JsonDocument canonical = fixture.ReadCanonicalManifest();
        JsonElement coverage = canonical.RootElement.GetProperty("desktopTupleCoverage");
        Assert.False(coverage.GetProperty("complete").GetBoolean());
        Assert.Equal(["linux", "windows", "macos"], coverage.GetProperty("requiredDesktopPlatforms").EnumerateArray().Select(static item => item.GetString()!).ToArray());
        Assert.Equal(["linux", "windows"], coverage.GetProperty("missingRequiredPlatforms").EnumerateArray().Select(static item => item.GetString()!).ToArray());
        Assert.Equal("coverage_incomplete", canonical.RootElement.GetProperty("rolloutState").GetString());
        Assert.Equal("review_required", canonical.RootElement.GetProperty("supportabilityState").GetString());
    }

    [Fact]
    public async Task PromoteAsyncRejectsOptimisticMacOnlyRegistryShelf()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260717-030405",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-osx-arm64-installer",
                    Head: "avalonia",
                    Platform: "macos",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    Bytes: "optimistic-mac-only"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview",
                    NotarizationStatusOverride: "skipped_preview")
            ],
            mutateManifestPair: static (compatibility, canonical) =>
            {
                compatibility["rolloutState"] = "promoted_preview";
                compatibility["supportabilityState"] = "preview_supported";
                canonical["rolloutState"] = "promoted_preview";
                canonical["supportabilityState"] = "preview_supported";
                canonical["publicTrustMetrics"]!["releaseChannel"]!["supportabilityState"] = "preview_supported";
                canonical["registryBoundaryCoverage"]!["releaseChannel"]!["supportabilityState"] = "preview_supported";
            });

        InvalidDataException exception = await Assert.ThrowsAsync<InvalidDataException>(() => fixture.PromoteAsync(bundlePath));

        Assert.Contains("coverage_incomplete/review_required", exception.Message, StringComparison.Ordinal);
        Assert.False(File.Exists(Path.Combine(fixture.DownloadsRoot, "RELEASE_CHANNEL.generated.json")));
    }

    [Fact]
    public async Task PromoteAsyncRejectsCanonicalCompatibilityProjectionDrift()
    {
        using var fixture = new ReleaseBundlePromotionFixture();
        string bundlePath = fixture.CreateBundle(
            version: "run-20260717-040506",
            artifacts:
            [
                new BundleArtifact(
                    ArtifactId: "avalonia-win-x64-installer",
                    Head: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    Bytes: "windows-drift"u8.ToArray(),
                    RequiresSigning: false,
                    RequiresNotarization: false,
                    SigningStatusOverride: "skipped_preview")
            ],
            mutateManifestPair: static (compatibility, _) =>
            {
                compatibility["downloads"]![0]!["sha256"] = new string('0', 64);
            });

        InvalidDataException exception = await Assert.ThrowsAsync<InvalidDataException>(() => fixture.PromoteAsync(bundlePath));

        Assert.Contains("artifact avalonia-win-x64-installer sha256", exception.Message, StringComparison.Ordinal);
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
                        Platform: platform,
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
                Platform: platform,
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
            string channel = "preview",
            Action<JsonObject, JsonObject>? mutateManifestPair = null)
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
                    Platform: artifact.Platform,
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

            if (mutateManifestPair is not null)
            {
                string compatibilityPath = Path.Combine(bundleRoot, "releases.json");
                string canonicalPath = Path.Combine(bundleRoot, "RELEASE_CHANNEL.generated.json");
                JsonObject compatibility = JsonNode.Parse(File.ReadAllText(compatibilityPath))!.AsObject();
                JsonObject canonical = JsonNode.Parse(File.ReadAllText(canonicalPath))!.AsObject();
                mutateManifestPair(compatibility, canonical);
                File.WriteAllText(compatibilityPath, compatibility.ToJsonString(TestJsonOptions));
                File.WriteAllText(canonicalPath, canonical.ToJsonString(TestJsonOptions));
            }

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

        public byte[] ReadBundleEntryBytes(string bundlePath, string entryName)
        {
            using ZipArchive archive = ZipFile.OpenRead(bundlePath);
            ZipArchiveEntry entry = archive.GetEntry(entryName)
                ?? throw new InvalidOperationException($"Bundle entry {entryName} is missing.");
            using Stream stream = entry.Open();
            using var bytes = new MemoryStream();
            stream.CopyTo(bytes);
            return bytes.ToArray();
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
            RegistryArtifactProjection[] projections = downloads
                .Select(download => ToRegistryProjection(
                    download.Id,
                    download.Head,
                    download.Platform,
                    download.Arch,
                    download.Kind,
                    download.FileName,
                    download.Url,
                    download.Sha256,
                    download.SizeBytes,
                    download.InstallAccessClass,
                    version,
                    channel))
                .ToArray();
            RegistryPosture posture = BuildRegistryPosture(projections, channel);

            var manifest = new JsonObject
            {
                ["contractName"] = "Chummer.Hub.Registry.Contracts",
                ["contract_name"] = "Chummer.Hub.Registry.Contracts",
                ["source"] = "registry",
                ["schemaVersion"] = 1,
                ["version"] = version,
                ["releaseVersion"] = version,
                ["channel"] = channel,
                ["channelId"] = channel,
                ["publishedAt"] = publishedAt,
                ["status"] = "published",
                ["rolloutState"] = posture.RolloutState,
                ["rolloutReason"] = posture.RolloutReason,
                ["supportabilityState"] = posture.SupportabilityState,
                ["supportabilitySummary"] = posture.SupportabilitySummary,
                ["knownIssueSummary"] = posture.KnownIssueSummary,
                ["fixAvailabilitySummary"] = posture.FixAvailabilitySummary,
                ["releaseProof"] = BuildReleaseProof(projections, proofGeneratedAt),
                ["desktopTupleCoverage"] = BuildDesktopTupleCoverage(projections),
                ["downloads"] = BuildCompatibilityArtifacts(projections)
            };
            File.WriteAllText(path, manifest.ToJsonString(TestJsonOptions));
        }

        private static void WriteCanonicalManifest(
            string path,
            string version,
            IReadOnlyList<CanonicalArtifact> artifacts,
            string publishedAt = "2026-04-01T20:00:00Z",
            string proofGeneratedAt = "2026-04-01T20:00:00Z",
            string channel = "preview")
        {
            RegistryArtifactProjection[] projections = artifacts
                .Select(artifact => ToRegistryProjection(
                    artifact.ArtifactId,
                    artifact.Head,
                    artifact.Platform,
                    artifact.Arch,
                    artifact.Kind,
                    artifact.FileName,
                    artifact.DownloadUrl,
                    artifact.Sha256,
                    artifact.SizeBytes,
                    "account_required",
                    version,
                    channel))
                .ToArray();
            RegistryPosture posture = BuildRegistryPosture(projections, channel);
            bool complete = IsDesktopFloorComplete(projections);

            var manifest = new JsonObject
            {
                ["contractName"] = "Chummer.Hub.Registry.Contracts",
                ["contract_name"] = "Chummer.Hub.Registry.Contracts",
                ["schemaVersion"] = 1,
                ["product"] = "chummer",
                ["version"] = version,
                ["releaseVersion"] = version,
                ["channel"] = channel,
                ["channelId"] = channel,
                ["publishedAt"] = publishedAt,
                ["status"] = "published",
                ["rolloutState"] = posture.RolloutState,
                ["rolloutReason"] = posture.RolloutReason,
                ["supportabilityState"] = posture.SupportabilityState,
                ["supportabilitySummary"] = posture.SupportabilitySummary,
                ["knownIssueSummary"] = posture.KnownIssueSummary,
                ["fixAvailabilitySummary"] = posture.FixAvailabilitySummary,
                ["releaseProof"] = BuildReleaseProof(projections, proofGeneratedAt),
                ["desktopTupleCoverage"] = BuildDesktopTupleCoverage(projections),
                ["artifacts"] = BuildCanonicalArtifacts(projections),
                ["publicTrustMetrics"] = new JsonObject
                {
                    ["releaseChannel"] = new JsonObject
                    {
                        ["posture"] = posture.PublicTrustPosture,
                        ["supportabilityState"] = posture.SupportabilityState
                    },
                    ["proofFreshness"] = new JsonObject
                    {
                        ["status"] = "fresh"
                    }
                },
                ["registryBoundaryCoverage"] = new JsonObject
                {
                    ["owner"] = "chummer6-hub-registry",
                    ["status"] = "closed",
                    ["persistence"] = new JsonObject
                    {
                        ["artifactCount"] = projections.Length
                    },
                    ["compatibility"] = new JsonObject
                    {
                        ["compatibleArtifactCount"] = projections.Length
                    },
                    ["releaseChannel"] = new JsonObject
                    {
                        ["supportabilityState"] = posture.SupportabilityState,
                        ["desktopTupleComplete"] = complete,
                        ["publicTrustPosture"] = posture.PublicTrustPosture
                    }
                }
            };
            File.WriteAllText(path, manifest.ToJsonString(TestJsonOptions));
        }

        private static RegistryArtifactProjection ToRegistryProjection(
            string artifactId,
            string head,
            string platform,
            string arch,
            string kind,
            string fileName,
            string downloadUrl,
            string sha256,
            long sizeBytes,
            string installAccessClass,
            string version,
            string channel)
        {
            string normalizedPlatform = NormalizePlatform(platform);
            return new RegistryArtifactProjection(
                artifactId,
                head,
                normalizedPlatform,
                RidFor(normalizedPlatform, arch),
                arch,
                kind,
                fileName,
                downloadUrl,
                sha256,
                sizeBytes,
                installAccessClass,
                version,
                channel);
        }

        private static JsonObject BuildReleaseProof(
            IReadOnlyList<RegistryArtifactProjection> artifacts,
            string generatedAt)
            => new()
            {
                ["status"] = "passed",
                ["generatedAt"] = generatedAt,
                ["baseUrl"] = "https://chummer.run",
                ["journeysPassed"] = JsonStrings(["build_explain_publish"]),
                ["proofRoutes"] = JsonStrings(
                    artifacts.Select(static artifact => $"/downloads/install/{artifact.ArtifactId}"))
            };

        private static JsonArray BuildCompatibilityArtifacts(
            IReadOnlyList<RegistryArtifactProjection> artifacts)
        {
            var rows = new JsonArray();
            foreach (RegistryArtifactProjection artifact in artifacts)
            {
                rows.Add(new JsonObject
                {
                    ["id"] = artifact.ArtifactId,
                    ["artifactId"] = artifact.ArtifactId,
                    ["head"] = artifact.Head,
                    ["platform"] = artifact.Platform,
                    ["platformId"] = artifact.Platform,
                    ["platformLabel"] = $"Avalonia Desktop {artifact.Platform} {artifact.Arch}",
                    ["rid"] = artifact.Rid,
                    ["arch"] = artifact.Arch,
                    ["kind"] = artifact.Kind,
                    ["fileName"] = artifact.FileName,
                    ["url"] = artifact.DownloadUrl,
                    ["sha256"] = artifact.Sha256,
                    ["sizeBytes"] = artifact.SizeBytes,
                    ["installAccessClass"] = artifact.InstallAccessClass,
                    ["version"] = artifact.Version,
                    ["releaseVersion"] = artifact.Version,
                    ["channel"] = artifact.Channel,
                    ["channelId"] = artifact.Channel,
                    ["status"] = "available"
                });
            }

            return rows;
        }

        private static JsonArray BuildCanonicalArtifacts(
            IReadOnlyList<RegistryArtifactProjection> artifacts)
        {
            var rows = new JsonArray();
            foreach (RegistryArtifactProjection artifact in artifacts)
            {
                rows.Add(new JsonObject
                {
                    ["artifactId"] = artifact.ArtifactId,
                    ["head"] = artifact.Head,
                    ["platform"] = artifact.Platform,
                    ["rid"] = artifact.Rid,
                    ["arch"] = artifact.Arch,
                    ["kind"] = artifact.Kind,
                    ["fileName"] = artifact.FileName,
                    ["downloadUrl"] = artifact.DownloadUrl,
                    ["sha256"] = artifact.Sha256,
                    ["sizeBytes"] = artifact.SizeBytes,
                    ["installAccessClass"] = artifact.InstallAccessClass,
                    ["version"] = artifact.Version,
                    ["releaseVersion"] = artifact.Version,
                    ["channel"] = artifact.Channel,
                    ["channelId"] = artifact.Channel,
                    ["status"] = "available",
                    ["rolloutState"] = "promoted"
                });
            }

            return rows;
        }

        private static JsonObject BuildDesktopTupleCoverage(
            IReadOnlyList<RegistryArtifactProjection> artifacts)
        {
            const string requiredHead = "avalonia";
            string[] requiredPlatforms = ["linux", "windows", "macos"];
            string[] requiredTuples =
            [
                "avalonia:linux-x64:linux",
                "avalonia:osx-arm64:macos",
                "avalonia:win-x64:windows"
            ];
            RegistryArtifactProjection[] installers = artifacts
                .Where(IsPromotedDesktopInstaller)
                .ToArray();
            HashSet<string> promotedPlatforms = installers
                .Select(static artifact => artifact.Platform)
                .ToHashSet(StringComparer.Ordinal);
            HashSet<string> promotedHeads = installers
                .Select(static artifact => artifact.Head)
                .ToHashSet(StringComparer.Ordinal);
            HashSet<string> promotedPairs = installers
                .Select(static artifact => $"{artifact.Head}:{artifact.Platform}")
                .ToHashSet(StringComparer.Ordinal);
            HashSet<string> promotedRequiredTuples = installers
                .Where(static artifact => artifact.Head == requiredHead)
                .Select(static artifact => $"{artifact.Head}:{artifact.Rid}:{artifact.Platform}")
                .ToHashSet(StringComparer.Ordinal);
            string[] missingPlatforms = requiredPlatforms
                .Where(platform => !promotedPlatforms.Contains(platform))
                .ToArray();
            string[] missingHeads = promotedHeads.Contains(requiredHead) ? [] : [requiredHead];
            string[] missingPairs = requiredPlatforms
                .Select(platform => $"{requiredHead}:{platform}")
                .Where(pair => !promotedPairs.Contains(pair))
                .ToArray();
            string[] missingTuples = requiredTuples
                .Where(tuple => !promotedRequiredTuples.Contains(tuple))
                .ToArray();
            var promotedInstallerTuples = new JsonArray();
            foreach (RegistryArtifactProjection artifact in installers.OrderBy(
                         static artifact => $"{artifact.Head}:{artifact.Platform}:{artifact.Rid}",
                         StringComparer.Ordinal))
            {
                promotedInstallerTuples.Add(new JsonObject
                {
                    ["tupleId"] = $"{artifact.Head}:{artifact.Platform}:{artifact.Rid}",
                    ["artifactId"] = artifact.ArtifactId,
                    ["head"] = artifact.Head,
                    ["platform"] = artifact.Platform,
                    ["rid"] = artifact.Rid,
                    ["arch"] = artifact.Arch,
                    ["kind"] = artifact.Kind
                });
            }

            return new JsonObject
            {
                ["requiredDesktopPlatforms"] = JsonStrings(requiredPlatforms),
                ["requiredDesktopHeads"] = JsonStrings([requiredHead]),
                ["requiredDesktopPlatformHeadRidTuples"] = JsonStrings(requiredTuples),
                ["promotedInstallerTuples"] = promotedInstallerTuples,
                ["promotedPlatformHeadRidTuples"] = JsonStrings(
                    installers
                        .Select(static artifact => $"{artifact.Head}:{artifact.Rid}:{artifact.Platform}")
                        .Distinct(StringComparer.Ordinal)
                        .Order(StringComparer.Ordinal)),
                ["missingRequiredPlatforms"] = JsonStrings(missingPlatforms),
                ["missingRequiredHeads"] = JsonStrings(missingHeads),
                ["missingRequiredPlatformHeadPairs"] = JsonStrings(missingPairs),
                ["missingRequiredPlatformHeadRidTuples"] = JsonStrings(missingTuples),
                ["complete"] = missingTuples.Length == 0
            };
        }

        private static RegistryPosture BuildRegistryPosture(
            IReadOnlyList<RegistryArtifactProjection> artifacts,
            string channel)
        {
            if (!IsDesktopFloorComplete(artifacts))
            {
                return new RegistryPosture(
                    "coverage_incomplete",
                    "Registry requires Linux, Windows, and macOS desktop installer coverage.",
                    "review_required",
                    "Registry review is required until the desktop platform floor is complete.",
                    "The desktop platform floor is incomplete.",
                    "Publish the missing Registry-validated desktop installers.",
                    "preview");
            }

            bool stable = string.Equals(channel, "stable", StringComparison.OrdinalIgnoreCase);
            return new RegistryPosture(
                stable ? "public_stable" : "promoted_preview",
                "Registry verified the complete desktop release shelf.",
                stable ? "gold_supported" : "preview_supported",
                "Registry verified the release supportability posture.",
                "No blocking release issue is known.",
                "No corrective publication is required.",
                stable ? "live" : "preview");
        }

        private static bool IsDesktopFloorComplete(IReadOnlyList<RegistryArtifactProjection> artifacts)
        {
            HashSet<string> tuples = artifacts
                .Where(IsPromotedDesktopInstaller)
                .Where(static artifact => artifact.Head == "avalonia")
                .Select(static artifact => $"{artifact.Head}:{artifact.Rid}:{artifact.Platform}")
                .ToHashSet(StringComparer.Ordinal);
            return tuples.Contains("avalonia:linux-x64:linux")
                   && tuples.Contains("avalonia:osx-arm64:macos")
                   && tuples.Contains("avalonia:win-x64:windows");
        }

        private static bool IsPromotedDesktopInstaller(RegistryArtifactProjection artifact)
            => artifact.Platform == "macos"
                ? artifact.Kind is "installer" or "dmg" or "pkg"
                : artifact.Kind == "installer";

        private static string NormalizePlatform(string platform)
        {
            string token = platform.Trim().ToLowerInvariant().Replace('_', '-');
            if (token.StartsWith("mac", StringComparison.Ordinal)
                || token.StartsWith("osx", StringComparison.Ordinal)
                || token.StartsWith("darwin", StringComparison.Ordinal))
            {
                return "macos";
            }

            if (token.StartsWith("win", StringComparison.Ordinal))
            {
                return "windows";
            }

            return token.StartsWith("linux", StringComparison.Ordinal) ? "linux" : token;
        }

        private static string RidFor(string platform, string arch)
            => (platform, arch.ToLowerInvariant()) switch
            {
                ("linux", "arm64") => "linux-arm64",
                ("linux", _) => "linux-x64",
                ("windows", "arm64") => "win-arm64",
                ("windows", _) => "win-x64",
                ("macos", "x64") => "osx-x64",
                ("macos", _) => "osx-arm64",
                _ => string.Empty
            };

        private static JsonArray JsonStrings(IEnumerable<string> values)
        {
            var result = new JsonArray();
            foreach (string value in values)
            {
                result.Add(value);
            }

            return result;
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

    private sealed record RegistryArtifactProjection(
        string ArtifactId,
        string Head,
        string Platform,
        string Rid,
        string Arch,
        string Kind,
        string FileName,
        string DownloadUrl,
        string Sha256,
        long SizeBytes,
        string InstallAccessClass,
        string Version,
        string Channel);

    private sealed record RegistryPosture(
        string RolloutState,
        string RolloutReason,
        string SupportabilityState,
        string SupportabilitySummary,
        string KnownIssueSummary,
        string FixAvailabilitySummary,
        string PublicTrustPosture);

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
