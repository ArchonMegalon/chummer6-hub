using Chummer.Run.Api.Services;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseSelectionServiceTests
{
    [Fact]
    public void LoadPlatformAcceptanceCanonAcceptsGoldReleaseHeadPolicySections()
    {
        string root = Path.Combine(Path.GetTempPath(), "release-selection-canon-tests", Guid.NewGuid().ToString("N"));

        try
        {
            string productRoot = Path.Combine(root, ".codex-design", "product");
            Directory.CreateDirectory(productRoot);
            File.WriteAllText(
                Path.Combine(productRoot, "DESKTOP_PLATFORM_ACCEPTANCE_MATRIX.yaml"),
                """
product: chummer
surface: desktop_delivery
version: 1
flagship_head: Chummer.Avalonia
fallback_head: Chummer.Blazor.Desktop
gold_release_head_policy:
  primary_public_route_must_be_unique: true
  independent_flagship_proof_required_for_all_shipped_heads: true
  secondary_head_must_not_ship_on_thinner_proof: true
  preview_only_fallback_exceptions_do_not_satisfy_gold: true
head_policies:
  - head: Chummer.Avalonia
    role: flagship_primary
    pass_conditions:
      - Avalonia clears the flagship bar.
    fail_conditions:
      - Avalonia silently falls back.
  - head: Chummer.Blazor.Desktop
    role: compatibility_fallback_by_default
    fallback_allowed_when:
      - Avalonia is also promoted as primary.
    must_independently_meet_flagship_when:
      - Blazor is the only visible desktop head.
platforms:
  - id: windows
    public_shelf_status: promoted_preview
    primary_package_kind: installer
    startup_smoke_gate: required
    signing_posture: required_for_promoted_release
    updater_mode: in_app_apply_helper
    supportability: primary
""");

            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = root
                })
                .Build();

            var loader = new PublicCanonFileLoader(configuration);
            var document = loader.LoadRequiredYaml<DesktopPlatformAcceptanceDocument>(".codex-design/product/DESKTOP_PLATFORM_ACCEPTANCE_MATRIX.yaml");

            Assert.Equal("Chummer.Avalonia", document.FlagshipHead);
            Assert.NotNull(document.GoldReleaseHeadPolicy);
            Assert.True(document.GoldReleaseHeadPolicy!.PrimaryPublicRouteMustBeUnique);
            Assert.Equal(2, document.HeadPolicies?.Count);
            Assert.Equal("compatibility_fallback_by_default", document.HeadPolicies?[1].Role);
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
    public void BuildExperienceLoadsCurrentPublicReleaseCanon()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260401-065126",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-01T06:51:26Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-linux-x64-installer",
                    Platform: "Avalonia Desktop Linux X64 Installer",
                    Url: "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    Sha256: "6b0a63c39850a257e66d142c0bad196a7cc4fcbaf027635965f138f534bb13ea",
                    SizeBytes: 34297862,
                    Head: "avalonia",
                    PlatformId: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    InstallAccessClass: "open_public")
            ]);

        var experience = service.BuildExperience(manifest, userAgent: "Mozilla/5.0 (X11; Linux x86_64)", authenticated: false);

        Assert.Equal("Nightly", experience.Display.ChannelLabel);
        Assert.Equal("Need install help?", experience.InstallHelpLabel);
        Assert.NotNull(experience.Recommended);
        Assert.Equal("Avalonia Desktop Linux X64 Installer", experience.Recommended!.Artifact.Platform);
        Assert.True(experience.RequestedPlatformHasPublicDownload);
        Assert.Contains(experience.PlatformAvailability, item => item.PlatformId == "linux" && item.PubliclyAvailable);
    }

    [Fact]
    public void BuildPublicAccessPostureExplainsWhenPreviewIsGuestReadable()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260401-065126",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-01T06:51:26Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-linux-x64-installer",
                    Platform: "Avalonia Desktop Linux X64 Installer",
                    Url: "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    Sha256: "6b0a63c39850a257e66d142c0bad196a7cc4fcbaf027635965f138f534bb13ea",
                    SizeBytes: 34297862,
                    Head: "avalonia",
                    PlatformId: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    InstallAccessClass: "open_public")
            ]);

        var experience = service.BuildExperience(manifest, userAgent: "Mozilla/5.0 (X11; Linux x86_64)", authenticated: false);
        var posture = service.BuildPublicAccessPosture(manifest, experience);

        Assert.True(posture.GuestInstallAvailable);
        Assert.False(posture.AccountRequiredInstallAvailable);
        Assert.Contains("public download", posture.AvailabilitySummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Create an account when you want recovery", posture.DownloadFaqAnswer, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BuildPublicAccessPosturePreservesAccountRequiredArtifactsOnPublicStable()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260422-101500",
            Channel: "public_stable",
            Status: "published",
            RolloutState: "public_stable",
            PublishedAt: DateTimeOffset.Parse("2026-04-22T10:15:00Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-installer",
                    Platform: "Avalonia Desktop Windows X64 Installer",
                    Url: "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    Sha256: "cb3493c1113c23b5e496dfe8a1e6de9afc43c802d7da865adc5255497341e5c4",
                    SizeBytes: 96466473,
                    Head: "avalonia",
                    PlatformId: "win-x64",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    InstallAccessClass: "open_public"),
                new PublicReleaseArtifactDto(
                    Id: "avalonia-osx-arm64-installer",
                    Platform: "Avalonia Desktop macOS ARM64 Installer",
                    Url: "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    Sha256: "mac-a1",
                    SizeBytes: 101,
                    Head: "avalonia",
                    PlatformId: "osx-arm64",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    InstallAccessClass: "account_required")
            ]);

        var experience = service.BuildExperience(manifest, userAgent: "Mozilla/5.0 (Macintosh; Apple Silicon Mac OS X 14_4)", authenticated: false);
        var posture = service.BuildPublicAccessPosture(manifest, experience);

        Assert.Equal("Stable", experience.Display.ChannelLabel);
        var macDownload = Assert.Single(manifest.Downloads, item => item.Id == "avalonia-osx-arm64-installer");
        var macOption = service.BuildOption(manifest, macDownload, authenticated: false, recommended: false);
        Assert.Equal("account_required", macOption.InstallAccessClass);
        Assert.StartsWith("/signup?next=", macOption.DispatchHref, StringComparison.Ordinal);
        Assert.Contains("%2Fdownloads%2Finstall%2Favalonia-osx-arm64-installer", macOption.DispatchHref, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicStableKeepsOpenPublicLinuxInstallerGuestReadable()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260612-121055",
            Channel: "public_stable",
            Status: "published",
            RolloutState: "public_stable",
            PublishedAt: DateTimeOffset.Parse("2026-06-12T13:20:46Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-linux-x64-installer",
                    Platform: "Avalonia Desktop Linux X64 Installer",
                    Url: "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    Sha256: "158294957a9456ddfb561325d5e503f22879ff1ff4036a360f2812099d7fc475",
                    SizeBytes: 42855330,
                    Head: "avalonia",
                    PlatformId: "linux-x64",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    InstallAccessClass: "open_public")
            ]);

        PublicReleaseArtifactDto linuxDownload = Assert.Single(manifest.Downloads);
        ReleaseOptionViewModel linuxOption = service.BuildOption(manifest, linuxDownload, authenticated: false, recommended: true);
        PublicAccessPostureViewModel posture = service.BuildPublicAccessPosture(manifest, userAgent: "Mozilla/5.0 (X11; Linux x86_64)", authenticated: false);

        Assert.Equal("open_public", linuxOption.InstallAccessClass);
        Assert.False(linuxOption.RequiresAccount);
        Assert.Equal("/downloads/get/avalonia-linux-x64-installer", linuxOption.DispatchHref);
        Assert.True(posture.GuestInstallAvailable);
        Assert.False(posture.AccountRequiredInstallAvailable);
    }

    [Fact]
    public void PublicStableKeepsWindowsInstallerGuestReadableEvenWhenRegistryMarksAccountRequired()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260619-080000",
            Channel: "public_stable",
            Status: "published",
            RolloutState: "public_stable",
            PublishedAt: DateTimeOffset.Parse("2026-06-19T08:00:00Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-installer",
                    Platform: "Avalonia Desktop Windows X64 Installer",
                    Url: "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    Sha256: "cb3493c1113c23b5e496dfe8a1e6de9afc43c802d7da865adc5255497341e5c4",
                    SizeBytes: 96466473,
                    Head: "avalonia",
                    PlatformId: "win-x64",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    InstallAccessClass: "account_required")
            ]);

        PublicReleaseArtifactDto windowsDownload = Assert.Single(manifest.Downloads);
        ReleaseOptionViewModel windowsOption = service.BuildOption(manifest, windowsDownload, authenticated: false, recommended: true);
        PublicAccessPostureViewModel posture = service.BuildPublicAccessPosture(manifest, userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", authenticated: false);

        Assert.Equal("open_public", windowsOption.InstallAccessClass);
        Assert.False(windowsOption.RequiresAccount);
        Assert.Equal("/downloads/get/avalonia-win-x64-installer", windowsOption.DispatchHref);
        Assert.True(posture.GuestInstallAvailable);
        Assert.False(posture.AccountRequiredInstallAvailable);
    }

    [Fact]
    public void PublicReleaseExperienceCanonAcceptsCurrentProofBoundaryFields()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var loader = new PublicCanonFileLoader(configuration);
        var document = loader.LoadRequiredYaml<PublicReleaseExperienceDocument>(".codex-design/product/PUBLIC_RELEASE_EXPERIENCE.yaml");

        Assert.Contains("posted", document.ProofScopeSummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Flagship", document.FlagshipClaimSummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("concierge", document.PublicConciergeSummary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BuildExperienceMarksUnsupportedRequestedPlatformAsUnavailableWithoutPretendingItIsRecommended()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260401-065126",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-01T06:51:26Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-linux-x64-installer",
                    Platform: "Avalonia Desktop Linux X64 Installer",
                    Url: "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    Sha256: "6b0a63c39850a257e66d142c0bad196a7cc4fcbaf027635965f138f534bb13ea",
                    SizeBytes: 34297862,
                    Head: "avalonia",
                    PlatformId: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    InstallAccessClass: "open_public")
            ]);

        var experience = service.BuildExperience(manifest, userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", authenticated: false);

        Assert.Equal("Windows", experience.RequestedPlatformLabel);
        Assert.False(experience.RequestedPlatformHasPublicDownload);
        Assert.False(string.IsNullOrWhiteSpace(experience.PlatformShelfNoticeTitle));
        var windows = Assert.Single(experience.PlatformAvailability, item => item.PlatformId == "windows");
        Assert.False(windows.PubliclyAvailable);
        Assert.Contains("not on the public downloads page", windows.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("unavailable", windows.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BuildExperienceUsesWindowsInstallerAsRecommendedDownloadWhenPresentOnTheMainShelf()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260422-101500",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-22T10:15:00Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-linux-x64-installer",
                    Platform: "Avalonia Desktop Linux X64 Installer",
                    Url: "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    Sha256: "6b0a63c39850a257e66d142c0bad196a7cc4fcbaf027635965f138f534bb13ea",
                    SizeBytes: 34297862,
                    Head: "avalonia",
                    PlatformId: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    InstallAccessClass: "account_required"),
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-installer",
                    Platform: "Avalonia Desktop Windows X64 Installer",
                    Url: "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    Sha256: "cb3493c1113c23b5e496dfe8a1e6de9afc43c802d7da865adc5255497341e5c4",
                    SizeBytes: 96466473,
                    Head: "avalonia",
                    PlatformId: "win-x64",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    InstallAccessClass: "account_required")
            ]);

        var experience = service.BuildExperience(manifest, userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", authenticated: false);

        Assert.Equal("Windows", experience.RequestedPlatformLabel);
        Assert.True(experience.RequestedPlatformHasPublicDownload);
        Assert.NotNull(experience.Recommended);
        Assert.Equal("avalonia-win-x64-installer", experience.Recommended!.Artifact.Id);
        Assert.Equal("/downloads/get/avalonia-win-x64-installer", experience.Recommended.DispatchHref);
        var windows = Assert.Single(experience.PlatformAvailability, item => item.PlatformId == "windows");
        Assert.True(windows.PubliclyAvailable);
    }

    [Fact]
    public void BuildOptionTreatsWindowsLauncherAndZipAsSupportOnlyPackages()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260612-121055",
            Channel: "public_stable",
            PublishedAt: DateTimeOffset.Parse("2026-06-12T13:20:46Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-portable",
                    Platform: "Avalonia Desktop Windows X64 Portable Launcher",
                    Url: "/downloads/files/chummer-avalonia-win-x64.exe",
                    Sha256: "portable-launcher",
                    SizeBytes: 433152,
                    Head: "avalonia",
                    PlatformId: "win-x64",
                    Arch: "x64",
                    Kind: "portable_exe",
                    FileName: "chummer-avalonia-win-x64.exe",
                    InstallAccessClass: "open_public"),
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-archive",
                    Platform: "Avalonia Desktop Windows X64 Support Package",
                    Url: "/downloads/files/chummer-avalonia-win-x64.zip",
                    Sha256: "portable-zip",
                    SizeBytes: 49292098,
                    Head: "avalonia",
                    PlatformId: "win-x64",
                    Arch: "x64",
                    Kind: "archive",
                    FileName: "chummer-avalonia-win-x64.zip",
                    InstallAccessClass: "open_public")
            ]);

        var launcher = service.BuildOption(manifest, manifest.Downloads[0], authenticated: false, recommended: false);
        var archive = service.BuildOption(manifest, manifest.Downloads[1], authenticated: false, recommended: false);

        Assert.Equal("Support package for Windows", launcher.Title);
        Assert.Equal("Support-only package for Windows. Use the main installer unless support gives you this link.", launcher.SupportLine);
        Assert.Equal("Download Windows support package", launcher.ActionLabel);

        Assert.Equal("Support package for Windows", archive.Title);
        Assert.Equal("Support-only package for Windows. Use the main installer unless support gives you this link.", archive.SupportLine);
        Assert.Equal("Download Windows support package", archive.ActionLabel);
    }

    [Fact]
    public void BuildOptionTreatsPortableKindAsLauncherAlias()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260612-121055",
            Channel: "public_stable",
            PublishedAt: DateTimeOffset.Parse("2026-06-12T13:20:46Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-portable",
                    Platform: "Avalonia Desktop Windows X64 Portable Launcher",
                    Url: "/downloads/files/chummer-avalonia-win-x64.exe",
                    Sha256: "portable-launcher",
                    SizeBytes: 433152,
                    Head: "avalonia",
                    PlatformId: "win-x64",
                    Arch: "x64",
                    Kind: "portable",
                    FileName: "chummer-avalonia-win-x64.exe",
                    InstallAccessClass: "open_public")
            ]);

        var launcher = service.BuildOption(manifest, manifest.Downloads[0], authenticated: false, recommended: false);

        Assert.Equal("Support package for Windows", launcher.Title);
        Assert.Equal("Support-only package for Windows. Use the main installer unless support gives you this link.", launcher.SupportLine);
        Assert.Equal("Download Windows support package", launcher.ActionLabel);
    }

    [Fact]
    public void ApplyAccessPolicyDropsPortableAndArchiveRowsFromPublicDownloads()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260620-installer-only",
            Channel: "public_stable",
            PublishedAt: DateTimeOffset.Parse("2026-06-20T06:00:00Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-installer",
                    Platform: "Avalonia Desktop Windows X64 Installer",
                    Url: "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    Sha256: "installer",
                    SizeBytes: 98_977_472,
                    Head: "avalonia",
                    PlatformId: "windows",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    InstallAccessClass: "open_public"),
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-portable",
                    Platform: "Avalonia Desktop Windows X64 Portable Launcher",
                    Url: "/downloads/files/chummer-avalonia-win-x64.exe",
                    Sha256: "portable-launcher",
                    SizeBytes: 433_152,
                    Head: "avalonia",
                    PlatformId: "windows",
                    Arch: "x64",
                    Kind: "portable",
                    FileName: "chummer-avalonia-win-x64.exe",
                    InstallAccessClass: "open_public"),
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-archive",
                    Platform: "Avalonia Desktop Windows X64 ZIP",
                    Url: "/downloads/files/chummer-avalonia-win-x64.zip",
                    Sha256: "portable-zip",
                    SizeBytes: 49_292_098,
                    Head: "avalonia",
                    PlatformId: "windows",
                    Arch: "x64",
                    Kind: "archive",
                    FileName: "chummer-avalonia-win-x64.zip",
                    InstallAccessClass: "open_public")
            ]);

        var normalized = service.ApplyAccessPolicy(manifest);
        var experience = service.BuildExperience(manifest, userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", authenticated: false);

        var download = Assert.Single(normalized.Downloads);
        Assert.Equal("avalonia-win-x64-installer", download.Id);
        Assert.Equal("avalonia-win-x64-installer", experience.Recommended?.Artifact.Id);
        Assert.DoesNotContain(experience.Alternatives, item => item.Artifact.Id.Contains("portable", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain(experience.Alternatives, item => item.Artifact.Id.Contains("archive", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void BuildExperienceKeepsMacDmgOffPublicDownloadsEvenWhenProofIsMirrored()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260401-065126",
            Channel: "public_stable",
            PublishedAt: DateTimeOffset.Parse("2026-04-01T06:51:26Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-linux-x64-installer",
                    Platform: "Avalonia Desktop Linux X64 Installer",
                    Url: "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    Sha256: "6b0a63c39850a257e66d142c0bad196a7cc4fcbaf027635965f138f534bb13ea",
                    SizeBytes: 34297862,
                    Head: "avalonia",
                    PlatformId: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    InstallAccessClass: "open_public"),
                new PublicReleaseArtifactDto(
                    Id: "avalonia-osx-arm64-installer",
                    Platform: "Avalonia Desktop macOS ARM64 Installer",
                    Url: "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    Sha256: "7b0a63c39850a257e66d142c0bad196a7cc4fcbaf027635965f138f534bb13ef",
                    SizeBytes: 44297862,
                    Head: "avalonia",
                    PlatformId: "osx-arm64",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    InstallAccessClass: "open_public"),
            ],
            RolloutState: "public_stable",
            ProofStatus: "passed",
            ProofRoutes:
            [
                "/downloads/install/avalonia-osx-arm64-installer"
            ]);

        var experience = service.BuildExperience(manifest, userAgent: "Mozilla/5.0 (X11; Linux x86_64)", authenticated: false);

        Assert.DoesNotContain(experience.OtherPlatforms, item => item.Artifact.Id == "avalonia-osx-arm64-installer");
        var mac = Assert.Single(experience.PlatformAvailability, item => item.PlatformId == "macos");
        Assert.False(mac.PubliclyAvailable);
        Assert.Contains("guided", mac.SupportabilityLabel, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BuildExperienceKeepsMacSetupScriptOffPublicDownloadsForAuthenticatedMacUsers()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260402-161430",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-02T16:14:30Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-osx-arm64-installer",
                    Platform: "Avalonia Desktop macOS ARM64 Installer",
                    Url: "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    Sha256: "7b0a63c39850a257e66d142c0bad196a7cc4fcbaf027635965f138f534bb13ef",
                    SizeBytes: 44297862,
                    Head: "avalonia",
                    PlatformId: "osx-arm64",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    InstallAccessClass: "account_required")
            ],
            ProofStatus: "passed",
            ProofRoutes:
            [
                "/downloads/install/avalonia-osx-arm64-installer"
            ]);

        var experience = service.BuildExperience(manifest, userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4)", authenticated: true);

        Assert.Null(experience.Recommended);
        var mac = Assert.Single(experience.PlatformAvailability, item => item.PlatformId == "macos");
        Assert.False(mac.PubliclyAvailable);
        Assert.Equal("Guided support only", mac.StatusLabel);
        Assert.Contains("guided", mac.SupportabilityLabel, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BuildExperienceUsesWindowsSetupExeForAuthenticatedWindowsUsers()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260403-150000",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-03T15:00:00Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-installer",
                    Platform: "Avalonia Desktop Windows x64 Installer",
                    Url: "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    Sha256: "w1",
                    SizeBytes: 404,
                    Head: "avalonia",
                    PlatformId: "win-x64",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    InstallAccessClass: "account_required")
            ],
            ProofStatus: "passed",
            ProofRoutes:
            [
                "/downloads/install/avalonia-osx-arm64-installer",
                "/downloads/install/avalonia-osx-x64-installer"
            ]);

        var experience = service.BuildExperience(manifest, userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", authenticated: true);

        var recommended = Assert.IsType<ReleaseOptionViewModel>(experience.Recommended);
        Assert.Equal("Install Chummer on Windows", recommended.ActionLabel);
        Assert.Equal("/downloads/get/avalonia-win-x64-installer", recommended.DispatchHref);
        Assert.Contains("default recommended installer", recommended.SupportLine, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("default browser", recommended.SupportLine, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("powershell", recommended.SupportLine, StringComparison.OrdinalIgnoreCase);
        Assert.False(service.UsesGuidedBootstrapScript(recommended.Artifact));
    }

    [Fact]
    public void BuildSignedInOnlyWindowsOptionsSurfacesHiddenWindowsInstallerWhenPublicShelfVisibilitySuppressesIt()
    {
        string root = Path.Combine(Path.GetTempPath(), "release-selection-hidden-windows-tests", Guid.NewGuid().ToString("N"));

        try
        {
            string productRoot = Path.Combine(root, ".codex-design", "product");
            Directory.CreateDirectory(productRoot);
            File.Copy(
                RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_RELEASE_EXPERIENCE.yaml"),
                Path.Combine(productRoot, "PUBLIC_RELEASE_EXPERIENCE.yaml"));
            File.WriteAllText(
                Path.Combine(productRoot, "DESKTOP_PLATFORM_ACCEPTANCE_MATRIX.yaml"),
                """
product: chummer
surface: desktop_delivery
version: 1
flagship_head: Chummer.Avalonia
fallback_head: Chummer.Blazor.Desktop
gold_release_head_policy:
  primary_public_route_must_be_unique: true
  independent_flagship_proof_required_for_all_shipped_heads: true
  secondary_head_must_not_ship_on_thinner_proof: true
  preview_only_fallback_exceptions_do_not_satisfy_gold: true
platforms:
  - id: windows
    public_shelf_status: promoted_preview
    primary_package_kind: installer
    startup_smoke_gate: required
    signing_posture: required_for_promoted_release
    updater_mode: in_app_apply_helper
    supportability: primary
    public_manifest_visibility: visible_after_signed_notarized_promotion
""");

            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = root
                })
                .Build();

            var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
            var manifest = new PublicReleaseManifestDto(
                Version: "run-20260429-170000",
                Channel: "preview",
                PublishedAt: DateTimeOffset.Parse("2026-04-29T17:00:00Z"),
                Downloads:
                [
                    new PublicReleaseArtifactDto(
                        Id: "avalonia-win-x64-installer",
                        Platform: "Avalonia Desktop Windows x64 Installer",
                        Url: "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                        Sha256: "win-hidden",
                        SizeBytes: 404,
                        Head: "avalonia",
                        PlatformId: "win-x64",
                        Arch: "x64",
                        Kind: "installer",
                        FileName: "chummer-avalonia-win-x64-installer.exe",
                        InstallAccessClass: "account_required")
                ],
                ProofStatus: "failed",
                ProofRoutes:
                [
                    "/downloads/install/avalonia-linux-x64-installer"
                ]);

            var guest = service.BuildExperience(
                manifest,
                userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                authenticated: false);

            Assert.False(guest.RequestedPlatformHasPublicDownload);

            var hidden = service.BuildSignedInOnlyWindowsOptions(manifest);

            var option = Assert.Single(hidden);
            Assert.Equal("avalonia-win-x64-installer", option.Artifact.Id);
            Assert.Equal("/downloads/install/avalonia-win-x64-installer", option.DispatchHref);
            Assert.Equal("Install on Windows", option.ActionLabel);
            Assert.Contains("setup .exe", option.SupportLine, StringComparison.OrdinalIgnoreCase);
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
    public void BuildSignedInOnlyWindowsOptionsOmitsWindowsInstallerAlreadyOnPublicShelf()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260429-173000",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-29T17:30:00Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-installer",
                    Platform: "Avalonia Desktop Windows x64 Installer",
                    Url: "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    Sha256: "win-public",
                    SizeBytes: 404,
                    Head: "avalonia",
                    PlatformId: "win-x64",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    InstallAccessClass: "account_required")
            ],
            ProofStatus: "passed",
            ProofRoutes:
            [
                "/downloads/install/avalonia-win-x64-installer"
            ]);

        var hidden = service.BuildSignedInOnlyWindowsOptions(manifest);

        Assert.Empty(hidden);
    }

    [Fact]
    public void BuildExperienceUsesLinuxSetupScriptForAuthenticatedLinuxUsers()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260403-150000",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-03T15:00:00Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-linux-x64-installer",
                    Platform: "Avalonia Desktop Linux x64 Installer",
                    Url: "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    Sha256: "l1",
                    SizeBytes: 505,
                    Head: "avalonia",
                    PlatformId: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    InstallAccessClass: "account_required")
            ],
            ProofStatus: "passed",
            ProofRoutes:
            [
                "/downloads/install/avalonia-osx-arm64-installer",
                "/downloads/install/avalonia-osx-x64-installer"
            ]);

        var experience = service.BuildExperience(manifest, userAgent: "Mozilla/5.0 (X11; Linux x86_64)", authenticated: true);

        var recommended = Assert.IsType<ReleaseOptionViewModel>(experience.Recommended);
        Assert.Equal("Install Chummer on Linux", recommended.ActionLabel);
        Assert.Equal("/downloads/get/avalonia-linux-x64-installer", recommended.DispatchHref);
        Assert.Contains("default recommended installer", recommended.SupportLine, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("short-lived shell command", recommended.SupportLine, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BuildExperienceKeepsGuestMacUsersOnGuidedSupportInsteadOfSignupDownload()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260402-161430",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-02T16:14:30Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-osx-arm64-installer",
                    Platform: "Avalonia Desktop macOS ARM64 Installer",
                    Url: "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    Sha256: "7b0a63c39850a257e66d142c0bad196a7cc4fcbaf027635965f138f534bb13ef",
                    SizeBytes: 44297862,
                    Head: "avalonia",
                    PlatformId: "osx-arm64",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    InstallAccessClass: "account_required")
            ],
            ProofStatus: "passed",
            ProofRoutes:
            [
                "/downloads/install/avalonia-osx-arm64-installer"
            ]);

        var experience = service.BuildExperience(manifest, userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4)", authenticated: false);

        Assert.Null(experience.Recommended);
        var mac = Assert.Single(experience.PlatformAvailability, item => item.PlatformId == "macos");
        Assert.False(mac.PubliclyAvailable);
        Assert.Equal("Guided support only", mac.StatusLabel);
    }

    [Fact]
    public void BuildExperienceWithholdsMacSetupScriptPreviewWithoutExplicitArtifactProof()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260402-203858",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-02T20:38:58Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-osx-arm64-installer",
                    Platform: "Avalonia Desktop macOS ARM64 Installer",
                    Url: "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    Sha256: "arm64",
                    SizeBytes: 44297862,
                    Head: "avalonia",
                    PlatformId: "osx-arm64",
                    Arch: "arm64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    InstallAccessClass: "open_public")
            ],
            Status: "published");

        var experience = service.BuildExperience(
            manifest,
            userAgent: "Mozilla/5.0 (Macintosh; Apple Silicon Mac OS X 14_4)",
            authenticated: false);

        Assert.Null(experience.Recommended);
        Assert.Contains(experience.PlatformAvailability, item => item.PlatformId == "macos" && !item.PubliclyAvailable);
    }

    [Fact]
    public void BuildExperienceKeepsMacArchitectureRowsOffPublicDownloadsUntilMacIsPromoted()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260402-161430",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-02T16:14:30Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-osx-x64-installer",
                    Platform: "Avalonia Desktop macOS X64 Installer",
                    Url: "/downloads/files/chummer-avalonia-osx-x64-installer.dmg",
                    Sha256: "x64",
                    SizeBytes: 44297862,
                    Head: "avalonia",
                    PlatformId: "macOS",
                    Arch: "x64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-x64-installer.dmg",
                    InstallAccessClass: "account_required"),
                new PublicReleaseArtifactDto(
                    Id: "avalonia-osx-arm64-installer",
                    Platform: "Avalonia Desktop macOS ARM64 Installer",
                    Url: "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                    Sha256: "arm64",
                    SizeBytes: 44297862,
                    Head: "avalonia",
                    PlatformId: "macOS",
                    Arch: "arm64",
                    Kind: "dmg",
                    FileName: "chummer-avalonia-osx-arm64-installer.dmg",
                    InstallAccessClass: "account_required")
            ],
            ProofStatus: "passed",
            ProofRoutes:
            [
                "/downloads/install/avalonia-osx-arm64-installer",
                "/downloads/install/avalonia-osx-x64-installer"
            ]);

        var experience = service.BuildExperience(
            manifest,
            userAgent: "Mozilla/5.0 (Macintosh; Apple Silicon Mac OS X 14_4) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15 arm64",
            authenticated: true);

        Assert.Null(experience.Recommended);
        Assert.DoesNotContain(experience.OtherPlatforms, item => item.Artifact.Id.Contains("osx", StringComparison.OrdinalIgnoreCase));
        var mac = Assert.Single(experience.PlatformAvailability, item => item.PlatformId == "macos");
        Assert.False(mac.PubliclyAvailable);
    }
}
