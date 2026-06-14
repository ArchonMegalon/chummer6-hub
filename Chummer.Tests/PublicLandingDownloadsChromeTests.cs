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

    [Fact]
    public void RebindDownloadsHeaderActionsRepointsPrimaryGuestCtaToRecommendedMacInstallRoute()
    {
        var releaseExperience = BuildGuestMacReleaseExperience();
        var chrome = new SiteChromeViewModel(
            Title: "Downloads",
            Description: "Install the current preview.",
            CurrentPath: "/downloads",
            PrimaryNavigation: [],
            SecondaryNavigation: [],
            UtilityNavigation: [],
            HeaderActions:
            [
                new SiteChromeActionViewModel("Sign in", "/auth/google/start?next=%2Fdownloads", "link"),
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
        var signIn = Assert.Single(rebound.HeaderActions, action => action.Label == "Sign in");
        var primary = Assert.Single(rebound.HeaderActions, action => string.Equals(action.Tone, "primary", StringComparison.OrdinalIgnoreCase));

        Assert.Equal(releaseExperience.GuestGateSecondaryHref, signIn.Href);
        Assert.Equal(releaseExperience.GuestGatePrimaryHref, primary.Href);
        Assert.Equal("/signup?next=%2Fdownloads%2Finstall%2Favalonia-osx-arm64-installer", primary.Href);
        Assert.NotNull(rebound.PublicPrimaryCta);
        Assert.Equal(releaseExperience.GuestGatePrimaryHref, rebound.PublicPrimaryCta!.Href);
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
                new SiteChromeActionViewModel("Sign in", "/login?next=%2Fstatus", "link"),
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
        var signIn = Assert.Single(rebound.HeaderActions, action => action.Label == "Sign in");
        var primary = Assert.Single(rebound.HeaderActions, action => string.Equals(action.Tone, "primary", StringComparison.OrdinalIgnoreCase));

        Assert.Equal("/login?next=%2Fstatus", signIn.Href);
        Assert.Equal(releaseExperience.GuestGatePrimaryHref, primary.Href);
        Assert.Equal("/signup?next=%2Fdownloads%2Finstall%2Favalonia-osx-arm64-installer", primary.Href);
        Assert.NotNull(rebound.PublicPrimaryCta);
        Assert.Equal(releaseExperience.GuestGatePrimaryHref, rebound.PublicPrimaryCta!.Href);
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
                new SiteChromeActionViewModel("Sign in", "/login?next=%2Ffaq", "link"),
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
        var signIn = Assert.Single(rebound.HeaderActions, action => action.Label == "Sign in");
        var primary = Assert.Single(rebound.HeaderActions, action => string.Equals(action.Tone, "primary", StringComparison.OrdinalIgnoreCase));

        Assert.Equal("/login?next=%2Ffaq", signIn.Href);
        Assert.Equal(releaseExperience.Recommended!.ActionLabel, primary.Label);
        Assert.Equal(releaseExperience.Recommended.DispatchHref, primary.Href);
        Assert.NotNull(rebound.PublicPrimaryCta);
        Assert.Equal(releaseExperience.Recommended.ActionLabel, rebound.PublicPrimaryCta!.Label);
        Assert.Equal(releaseExperience.Recommended.DispatchHref, rebound.PublicPrimaryCta!.Href);
    }
}
