using System.Reflection;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingDownloadsChromeTests
{
    [Fact]
    public void AuthorizedPreviewUsesItsManifestBoundImmutableFileHref()
    {
        var (page, option) = BuildReviewRequiredPreview();

        Assert.True(page.ReleaseTruthProjection!.ReviewRequiredPublicByteHandoffsAllowed);
        Assert.Equal(option.Artifact.Url, page.ReviewRequiredPublicByteHandoffHref(option));
    }

    [Theory]
    [InlineData("no_projection")]
    [InlineData("ordinary_release")]
    [InlineData("unbound_authority")]
    [InlineData("account_required")]
    [InlineData("account_recommended")]
    [InlineData("no_guest")]
    [InlineData("requires_account")]
    public void PreviewLinkOverrideDoesNotReplaceOrdinaryOrAccountGatedLinks(string variant)
    {
        var (page, option) = BuildReviewRequiredPreview();
        switch (variant)
        {
            case "no_projection":
                page = page with { ReleaseTruthProjection = null };
                break;
            case "ordinary_release":
                page = page with { ReleaseTruthProjection = page.ReleaseTruthProjection! with
                {
                    ReleaseDecisionStatus = "preview_ready",
                    RolloutState = "promoted_preview",
                    SupportabilityState = "preview_supported"
                } };
                break;
            case "unbound_authority":
                page = page with { ReleaseTruthProjection = page.ReleaseTruthProjection! with
                {
                    ReleaseScopeDecisionSha256 = "missing"
                } };
                break;
            case "account_required":
            case "account_recommended":
                option = option with { InstallAccessClass = variant };
                break;
            case "no_guest":
                option = option with { GuestDownloadAllowed = false };
                break;
            case "requires_account":
                option = option with { RequiresAccount = true };
                break;
        }

        var previewHref = page.ReviewRequiredPublicByteHandoffHref(option);
        Assert.Null(previewHref);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(".")]
    [InlineData("..")]
    [InlineData("../other")]
    [InlineData("other/generation")]
    [InlineData("other\\generation")]
    [InlineData("other%2fgeneration")]
    [InlineData("other..generation")]
    [InlineData(" other-generation")]
    [InlineData("other-generation\n")]
    public void PreviewLinkRejectsMissingOrUnsafeGeneration(string? generationId)
    {
        var (page, option) = BuildReviewRequiredPreview();
        page = page with { Manifest = page.Manifest with { GenerationId = generationId } };

        Assert.Null(page.ReviewRequiredPublicByteHandoffHref(option));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(".")]
    [InlineData("..")]
    [InlineData("../installer.exe")]
    [InlineData("nested/installer.exe")]
    [InlineData("nested\\installer.exe")]
    [InlineData("%2e%2e")]
    [InlineData("installer.exe?claimCode=secret")]
    [InlineData("installer.exe#fragment")]
    [InlineData("installer .exe")]
    [InlineData("installer\n.exe")]
    public void PreviewLinkRejectsMissingOrUnsafeFileName(string? fileName)
    {
        var (page, option) = BuildReviewRequiredPreview();
        option = option with { Artifact = option.Artifact with { FileName = fileName } };
        page = page with { Manifest = page.Manifest with { Downloads = [option.Artifact] } };

        Assert.Null(page.ReviewRequiredPublicByteHandoffHref(option));
    }

    [Theory]
    [InlineData("generation")]
    [InlineData("file")]
    [InlineData("url")]
    [InlineData("id")]
    [InlineData("sha")]
    [InlineData("size")]
    [InlineData("version")]
    [InlineData("channel")]
    [InlineData("artifact_access")]
    [InlineData("absent_artifact")]
    [InlineData("changed_option")]
    public void PreviewLinkRejectsMetadataNotBoundToManifestAndApprovedHandoff(string variant)
    {
        var (page, option) = BuildReviewRequiredPreview();
        var artifact = option.Artifact;
        artifact = variant switch
        {
            "file" => artifact with { FileName = "another-installer.exe" },
            "url" => artifact with { Url = "/downloads/file/test-installer" },
            "id" => artifact with { Id = "another-installer" },
            "sha" => artifact with { Sha256 = new string('f', 64) },
            "size" => artifact with { SizeBytes = artifact.SizeBytes + 1 },
            "artifact_access" => artifact with { InstallAccessClass = "account_required" },
            _ => artifact
        };
        option = option with { Artifact = artifact };
        var manifest = page.Manifest with { Downloads = [artifact] };
        manifest = variant switch
        {
            "generation" => manifest with { GenerationId = "another-generation" },
            "version" => manifest with { Version = "another-version" },
            "channel" => manifest with { Channel = "stable" },
            "absent_artifact" => manifest with { Downloads = [] },
            _ => manifest
        };
        if (variant == "changed_option")
        {
            option = option with { Artifact = artifact with { Kind = "another-kind" } };
        }
        page = page with { Manifest = manifest };

        Assert.Null(page.ReviewRequiredPublicByteHandoffHref(option));
    }

    [Fact]
    public void PreviewLinkEscapesActualFileNameAndRejectsOversizedGeneration()
    {
        var (page, option) = BuildReviewRequiredPreview("installer+é&test.exe");
        Assert.True(page.ReleaseTruthProjection!.ReviewRequiredPublicByteHandoffsAllowed);
        Assert.Equal("/downloads/g/test-preview-generation/files/installer%2B%C3%A9%26test.exe",
            page.ReviewRequiredPublicByteHandoffHref(option));

        page = page with { Manifest = page.Manifest with { GenerationId = new string('a', 129) } };
        Assert.Null(page.ReviewRequiredPublicByteHandoffHref(option));
    }

    [Fact]
    public void AllDownloadsButtonLanesUseTheSamePreviewHrefForEveryClickTarget()
    {
        var view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml"));
        foreach (var optionName in new[] { "stable", "nightly", "option" })
        {
            Assert.Contains($"var previewHref = Model.ReviewRequiredPublicByteHandoffHref({optionName});", view, StringComparison.Ordinal);
            Assert.Contains($"href=\"@(previewHref ?? {optionName}.DispatchHref)\"", view, StringComparison.Ordinal);
            Assert.Contains($"data-download-raw-url=\"@(previewHref ?? {optionName}.DirectFileHref)\"", view, StringComparison.Ordinal);
            Assert.Contains("data-download-install-route=\"@(previewHref ?? $\"/downloads/install/{Uri.EscapeDataString("
                + optionName + ".Artifact.Id)}\")\"", view, StringComparison.Ordinal);
        }
        Assert.Equal(3, view.Split("data-download-link-mode=\"raw-url\"", StringSplitOptions.None).Length - 1);
    }

    private static (DownloadsPageViewModel Page, ReleaseOptionViewModel Option) BuildReviewRequiredPreview(
        string fileName = "test-installer.exe")
    {
        var href = $"/downloads/g/test-preview-generation/files/{Uri.EscapeDataString(fileName)}";
        var artifact = new PublicReleaseArtifactDto(
            Id: "test-installer", Platform: "windows", Url: href, Sha256: new string('a', 64),
            SizeBytes: 42, Head: "avalonia", PlatformId: "win-x64", Rid: "win-x64", Arch: "x64",
            Kind: "installer", FileName: fileName, InstallAccessClass: "open_public");
        var manifest = new PublicReleaseManifestDto(
            Version: "test-preview-version", Channel: "preview", PublishedAt: DateTimeOffset.UnixEpoch,
            Downloads: [artifact]) { GenerationId = "test-preview-generation" };
        var handoff = new PublicPreviewByteHandoffDto(
            ContractName: "chummer.public-preview-byte-handoff/v1", Status: "approved_public_preview_bytes",
            SourcePublicationState: "preview", ReleaseScopeDecisionSha256: new string('d', 64),
            ReleaseVersion: manifest.Version, Channel: "preview", ArtifactId: artifact.Id,
            Head: "avalonia", Platform: "windows", Rid: "win-x64", Arch: "x64",
            Sha256: artifact.Sha256, SizeBytes: 42, ArtifactAccessClass: "open_public",
            SigningRequirement: "preview_unsigned_allowed", DownloadUrl: href,
            PublicInstallRoute: "/downloads/install/test-installer");
        var projection = new PublicReleaseTruthProjectionDto(
            ContractName: PublicReleaseTruthProjectionDto.Schema, ReleaseVersion: manifest.Version,
            Channel: "preview", ReleaseStatus: "published", RolloutState: "public_release_review_required",
            SupportabilityState: "review_required", AvailablePlatforms: ["windows"],
            PrimaryHeadByPlatform: new Dictionary<string, string> { ["windows"] = "avalonia" },
            ArtifactCount: 1, DownloadAccessPosture: "open_public", KnownIssueSummary: "Review required.",
            ManifestSha256: new string('a', 64), RegistryCommit: new string('b', 40),
            ReleaseDecisionStatus: "review_required", ReleaseDecisionSha256: new string('c', 64))
        {
            ReleaseScopeDecisionSha256 = handoff.ReleaseScopeDecisionSha256,
            ArtifactHandoff = handoff
        };
        var option = new ReleaseOptionViewModel(
            Artifact: artifact, Title: "Test installer", DispatchHref: "/downloads/get/test-installer",
            DirectFileHref: "/downloads/file/test-installer", PlatformLabel: "Windows", HeadLabel: "Avalonia",
            SizeLabel: "42 bytes", SupportLine: "Review required", ActionLabel: "Download", ShaPreview: null,
            Installer: true, InstallAccessClass: "open_public", RequiresAccount: false, GuestDownloadAllowed: true);
        var page = new DownloadsPageViewModel(
            Chrome: null!, Surface: null!, Assets: null!, Manifest: manifest, ReleaseTruth: null!,
            ReleaseExperience: null!, FlagshipCoverage: null!, ReleaseTruthProjection: projection);
        return (page, option);
    }

    private static ReleaseExperienceViewModel BuildGuestMacReleaseExperience()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var releaseSelection = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260409-headers",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-09T07:58:00Z"),
            Downloads:
            [
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
                    InstallAccessClass: "account_required"),
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-installer",
                    Platform: "Avalonia Desktop Windows x64 Installer",
                    Url: "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    Sha256: "win-b2",
                    SizeBytes: 202,
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
                "/downloads/install/avalonia-win-x64-installer"
            ]);

        return releaseSelection.BuildExperience(
            manifest,
            userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4)",
            authenticated: false);
    }

    private static ReleaseExperienceViewModel BuildGuestWindowsDirectInstallExperience()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var releaseSelection = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260416-direct-install",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-16T08:00:00Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-installer",
                    Platform: "Avalonia Desktop Windows x64 Installer",
                    Url: "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    Sha256: "win-direct",
                    SizeBytes: 202,
                    Head: "avalonia",
                    PlatformId: "win-x64",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-win-x64-installer.exe",
                    InstallAccessClass: "open_public")
            ],
            ProofStatus: "passed",
            ProofRoutes:
            [
                "/downloads/get/avalonia-win-x64-installer"
            ]);

        return releaseSelection.BuildExperience(
            manifest,
            userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            authenticated: false);
    }

    private static ReleaseExperienceViewModel BuildGuestWindowsExperienceFromLinuxOnlyShelf()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var releaseSelection = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "0.0.0.1",
            Channel: "public_stable",
            PublishedAt: DateTimeOffset.Parse("2026-06-26T08:00:00Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-linux-x64-installer",
                    Platform: "Avalonia Desktop Linux x64 Installer",
                    Url: "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    Sha256: "linux-direct",
                    SizeBytes: 303,
                    Head: "avalonia",
                    PlatformId: "linux-x64",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    InstallAccessClass: "open_public")
            ],
            ProofStatus: "passed",
            ProofRoutes:
            [
                "/downloads/get/avalonia-linux-x64-installer"
            ]);

        return releaseSelection.BuildExperience(
            manifest,
            userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            authenticated: false);
    }

    [Fact]
    public void RebindDownloadsHeaderActionsUsesDownloadsShelfWhenAnyGuestInstallerIsAvailable()
    {
        var releaseExperience = BuildGuestMacReleaseExperience();
        var chrome = new SiteChromeViewModel(
            Title: "Downloads",
            Description: "Install the current release build.",
            CurrentPath: "/downloads",
            PrimaryNavigation: [],
            SecondaryNavigation: [],
            UtilityNavigation: [],
            HeaderActions:
            [
                new SiteChromeActionViewModel("Open Chummer", "/auth/google/start?next=%2Fdownloads", "link"),
                new SiteChromeActionViewModel("Open account-assisted install", "/signup?next=%2Fdownloads%2Finstall%2Favalonia-win-x64-installer", "primary")
            ],
            PublicPrimaryCta: new SiteChromeActionViewModel("Open account-assisted install", "/signup?next=%2Fdownloads%2Finstall%2Favalonia-win-x64-installer", "primary"),
            Authenticated: false,
            SignedInLabel: null,
            FooterCanonicalSource: "fixture",
            FooterGeneratedNote: "fixture");

        var method = typeof(PublicLandingController).GetMethod(
            "RebindDownloadsHeaderActions",
            BindingFlags.NonPublic | BindingFlags.Static);

        Assert.NotNull(method);

        var rebound = Assert.IsType<SiteChromeViewModel>(method!.Invoke(null, [chrome, releaseExperience]));
        var signIn = Assert.Single(rebound.HeaderActions, action => action.Label == "Open Chummer");
        var primary = Assert.Single(rebound.HeaderActions, action => string.Equals(action.Tone, "primary", StringComparison.OrdinalIgnoreCase));

        Assert.Equal("/auth/google/start?next=%2Fdownloads", signIn.Href);
        Assert.NotNull(releaseExperience.Recommended);
        Assert.Equal(releaseExperience.Recommended!.DispatchHref, primary.Href);
        Assert.NotNull(rebound.PublicPrimaryCta);
        Assert.Equal(releaseExperience.Recommended.DispatchHref, rebound.PublicPrimaryCta!.Href);
    }

    [Fact]
    public void RebindGuestGateChromeActionsKeepsContextualSignInButRepointsPrimaryCtasOnOtherPages()
    {
        var releaseExperience = BuildGuestMacReleaseExperience();
        var chrome = new SiteChromeViewModel(
            Title: "Status",
            Description: "Weekly pulse.",
            CurrentPath: "/status",
            PrimaryNavigation: [],
            SecondaryNavigation: [],
            UtilityNavigation: [],
            HeaderActions:
            [
                new SiteChromeActionViewModel("Open Chummer", "/login?next=%2Fstatus", "link"),
                new SiteChromeActionViewModel("Open account-assisted install", "/signup?next=%2Fdownloads%2Finstall%2Favalonia-win-x64-installer", "primary")
            ],
            PublicPrimaryCta: new SiteChromeActionViewModel("Open account-assisted install", "/signup?next=%2Fdownloads%2Finstall%2Favalonia-win-x64-installer", "primary"),
            Authenticated: false,
            SignedInLabel: null,
            FooterCanonicalSource: "fixture",
            FooterGeneratedNote: "fixture");

        var method = typeof(PublicLandingController).GetMethod(
            "RebindGuestGateChromeActions",
            BindingFlags.NonPublic | BindingFlags.Static);

        Assert.NotNull(method);

        var rebound = Assert.IsType<SiteChromeViewModel>(method!.Invoke(null, [chrome, releaseExperience, false]));
        var signIn = Assert.Single(rebound.HeaderActions, action => action.Label == "Open Chummer");
        var primary = Assert.Single(rebound.HeaderActions, action => string.Equals(action.Tone, "primary", StringComparison.OrdinalIgnoreCase));

        Assert.Equal("/login?next=%2Fstatus", signIn.Href);
        Assert.NotNull(releaseExperience.Recommended);
        Assert.Equal(releaseExperience.Recommended!.DispatchHref, primary.Href);
        Assert.NotNull(rebound.PublicPrimaryCta);
        Assert.Equal(releaseExperience.Recommended.DispatchHref, rebound.PublicPrimaryCta!.Href);
    }

    [Fact]
    public void RebindGuestGateChromeActionsUsesDirectInstallRouteWhenGuestInstallIsAllowed()
    {
        var releaseExperience = BuildGuestWindowsDirectInstallExperience();
        var chrome = new SiteChromeViewModel(
            Title: "FAQ",
            Description: "Install answers.",
            CurrentPath: "/faq",
            PrimaryNavigation: [],
            SecondaryNavigation: [],
            UtilityNavigation: [],
            HeaderActions:
            [
                new SiteChromeActionViewModel("Open Chummer", "/login?next=%2Ffaq", "link"),
                new SiteChromeActionViewModel("Install Chummer", "/downloads", "primary")
            ],
            PublicPrimaryCta: new SiteChromeActionViewModel("Install Chummer", "/downloads", "primary"),
            Authenticated: false,
            SignedInLabel: null,
            FooterCanonicalSource: "fixture",
            FooterGeneratedNote: "fixture");

        var method = typeof(PublicLandingController).GetMethod(
            "RebindGuestGateChromeActions",
            BindingFlags.NonPublic | BindingFlags.Static);

        Assert.NotNull(method);

        var rebound = Assert.IsType<SiteChromeViewModel>(method!.Invoke(null, [chrome, releaseExperience, false]));
        var signIn = Assert.Single(rebound.HeaderActions, action => action.Label == "Open Chummer");
        var primary = Assert.Single(rebound.HeaderActions, action => string.Equals(action.Tone, "primary", StringComparison.OrdinalIgnoreCase));

        Assert.Equal("/login?next=%2Ffaq", signIn.Href);
        Assert.Equal(releaseExperience.Recommended!.ActionLabel, primary.Label);
        Assert.Equal(releaseExperience.Recommended.DispatchHref, primary.Href);
        Assert.NotNull(rebound.PublicPrimaryCta);
        Assert.Equal(releaseExperience.Recommended.ActionLabel, rebound.PublicPrimaryCta!.Label);
        Assert.Equal(releaseExperience.Recommended.DispatchHref, rebound.PublicPrimaryCta!.Href);
    }

    [Fact]
    public void WindowsBrowserAgainstLinuxOnlyShelfKeepsRequestedPlatformUnavailable()
    {
        var releaseExperience = BuildGuestWindowsExperienceFromLinuxOnlyShelf();

        Assert.False(releaseExperience.RequestedPlatformHasPublicDownload);
        Assert.Equal("Windows", releaseExperience.RequestedPlatformLabel);
        Assert.NotNull(releaseExperience.Recommended);
        Assert.Equal("avalonia-linux-x64-installer", releaseExperience.Recommended!.Artifact.Id);
        Assert.Equal("Linux", releaseExperience.Recommended.PlatformLabel);
    }
}
