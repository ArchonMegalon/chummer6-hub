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

        Assert.Equal("Preview channel", experience.Display.ChannelLabel);
        Assert.Equal("Need install help?", experience.InstallHelpLabel);
        Assert.NotNull(experience.Recommended);
        Assert.Equal("Avalonia Desktop Linux X64 Installer", experience.Recommended!.Artifact.Platform);
        Assert.True(experience.RequestedPlatformHasPublicDownload);
        Assert.Contains(experience.PlatformAvailability, item => item.PlatformId == "linux" && item.PubliclyAvailable);
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
        Assert.Contains("does not publish a Windows artifact yet", windows.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BuildExperienceNormalizesPreviewMacDmgIntoAccountGatedSetupScriptPreview()
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
            ProofStatus: "passed",
            ProofRoutes:
            [
                "/downloads/install/avalonia-osx-arm64-installer"
            ]);

        var experience = service.BuildExperience(manifest, userAgent: "Mozilla/5.0 (X11; Linux x86_64)", authenticated: false);

        Assert.Contains(experience.OtherPlatforms, item => item.Artifact.Id == "avalonia-osx-arm64-installer");
        var mac = Assert.Single(experience.PlatformAvailability, item => item.PlatformId == "macos");
        Assert.True(mac.PubliclyAvailable);
    }

    [Fact]
    public void BuildExperienceUsesMacSetupScriptForAuthenticatedMacUsers()
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

        var recommended = Assert.IsType<ReleaseOptionViewModel>(experience.Recommended);
        Assert.Equal("Install on Mac", recommended.ActionLabel);
        Assert.Equal("/downloads/install/avalonia-osx-arm64-installer", recommended.DispatchHref);
        Assert.Equal("macOS (Apple Silicon)", recommended.PlatformLabel);
        Assert.Contains("one Terminal command", recommended.SupportLine, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("verifies the published DMG digest", recommended.SupportLine, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(experience.PlatformAvailability, item => item.PlatformId == "macos" && item.PubliclyAvailable);
        Assert.True(service.UsesMacBootstrapScript(recommended.Artifact));
    }

    [Fact]
    public void BuildExperienceUsesWindowsSetupScriptForAuthenticatedWindowsUsers()
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
        Assert.Equal("Install on Windows", recommended.ActionLabel);
        Assert.Equal("/downloads/install/avalonia-win-x64-installer", recommended.DispatchHref);
        Assert.Contains("short-lived PowerShell command", recommended.SupportLine, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Auto select", recommended.SupportLine, StringComparison.OrdinalIgnoreCase);
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
        Assert.Equal("Install on Linux", recommended.ActionLabel);
        Assert.Equal("/downloads/install/avalonia-linux-x64-installer", recommended.DispatchHref);
        Assert.Contains("short-lived shell command", recommended.SupportLine, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Auto select", recommended.SupportLine, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BuildExperiencePromptsGuestMacUsersToSignInForSetupScript()
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

        var recommended = Assert.IsType<ReleaseOptionViewModel>(experience.Recommended);
        Assert.Equal("Create account to install on Mac", recommended.ActionLabel);
        Assert.Equal("macOS (Apple Silicon)", recommended.PlatformLabel);
        Assert.StartsWith("/signup?next=", recommended.DispatchHref, StringComparison.Ordinal);
        Assert.Contains("%2Fdownloads%2Finstall%2Favalonia-osx-arm64-installer", recommended.DispatchHref, StringComparison.Ordinal);
        Assert.Equal("Continue with Google", experience.GuestGateSecondaryLabel);
        Assert.Equal("/auth/google/start?next=%2Fdownloads%2Finstall%2Favalonia-osx-arm64-installer", experience.GuestGateSecondaryHref);
        Assert.Contains(experience.PlatformAvailability, item => item.PlatformId == "macos" && item.PubliclyAvailable);
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
    public void BuildExperiencePrefersArchitectureMatchWithinDetectedPlatform()
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

        var recommended = Assert.IsType<ReleaseOptionViewModel>(experience.Recommended);
        Assert.Equal("avalonia-osx-arm64-installer", recommended.Artifact.Id);
        Assert.Equal("macOS (Apple Silicon)", recommended.PlatformLabel);
    }
}
