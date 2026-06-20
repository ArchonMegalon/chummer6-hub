using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using System.Text.RegularExpressions;
using Xunit;

namespace Chummer.Tests;

public sealed class HubPageChromeServiceTests
{
    private static HubPageChromeService CreateService(IConfiguration configuration, string userAgent = "")
    {
        var canon = new PublicCanonFileLoader(configuration);
        var routes = new PublicRouteCatalogService(canon);
        var context = new DefaultHttpContext();
        if (!string.IsNullOrWhiteSpace(userAgent))
        {
            context.Request.Headers.UserAgent = userAgent;
        }

        return new HubPageChromeService(
            new PublicLandingService(canon, new PublicActionResolver()),
            new PublicNavigationService(canon, routes),
            new PublicReleaseManifestService(configuration),
            new ReleaseSelectionService(canon),
            new HttpContextAccessor { HttpContext = context });
    }

    [Fact]
    public void BuildPublicChromeUsesGoogleStartForDownloadsHeaderSignIn()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = CreateService(configuration);

        var chrome = service.BuildPublicChrome("Downloads", "Install the current release build.", "/downloads");

        var signIn = Assert.Single(chrome.HeaderActions, action => action.Label == "Sign in");
        Assert.Equal("/auth/google/start?next=%2Fdownloads", signIn.Href);
        Assert.DoesNotContain(chrome.HeaderActions, action => string.Equals(action.Tone, "primary", StringComparison.OrdinalIgnoreCase));
        Assert.Null(chrome.PublicPrimaryCta);
    }

    [Fact]
    public void BuildPublicChromeUsesGoogleStartForParticipateHeaderSignIn()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = CreateService(configuration);

        var chrome = service.BuildPublicChrome("Participate", "Authorize Codex access.", "/participate");

        var signIn = Assert.Single(chrome.HeaderActions, action => action.Label == "Sign in");
        Assert.Equal("/auth/google/start?next=%2Fparticipate", signIn.Href);
    }

    [Fact]
    public void BuildPublicChromeUsesFlagshipPrimaryNavigationModel()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = CreateService(configuration);

        var chrome = service.BuildPublicChrome("Home", "Flagship shell.", "/");

        Assert.Equal(
            ["Home", "Get Chummer", "Help"],
            chrome.PrimaryNavigation.Select(static link => link.Label).ToArray());
        Assert.Equal("/", chrome.PrimaryNavigation[0].Href);
        Assert.Equal("/downloads", chrome.PrimaryNavigation[1].Href);
        Assert.Equal("/help", chrome.PrimaryNavigation[2].Href);
    }

    [Fact]
    public void BuildPublicChromeCleansPublicTitleAndDescriptionBeforeFirstPaint()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = CreateService(configuration);

        var chrome = service.BuildPublicChrome(
            "Black Ledger proof",
            "ALICE generated an AI proof receipt for the Black Ledger operator lane.",
            "/status");

        Assert.Equal("campaign city check", chrome.Title);
        Assert.Equal("character help created a check for the campaign city user path.", chrome.Description);
        Assert.DoesNotContain("Alice", chrome.Description, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("AI", chrome.Description, StringComparison.Ordinal);
        Assert.DoesNotContain("proof", chrome.Description, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("receipt", chrome.Description, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("operator", chrome.Description, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BlackLedgerRouteExistsButIsNotPrimaryNavigation()
    {
        string navigationPath = RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_NAVIGATION.yaml");
        string manifestPath = RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_LANDING_MANIFEST.yaml");

        string navigation = File.ReadAllText(navigationPath);
        string manifest = File.ReadAllText(manifestPath);

        Assert.DoesNotContain("label: Ledger", navigation, StringComparison.Ordinal);
        Assert.Matches(new Regex(@"(?m)^\s*-\s+path:\s+/ledger\s*$"), manifest);
    }

    [Fact]
    public void BuildPublicChromeKeepsCanonicalSignInOnLoginRoute()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = CreateService(configuration);

        var chrome = service.BuildPublicChrome("Sign in", "Continue into account surfaces.", "/login");

        var signIn = Assert.Single(chrome.HeaderActions, action => action.Label == "Sign in");
        Assert.Equal("/login?next=/home", signIn.Href);
    }

    [Fact]
    public void BuildPublicChromeKeepsCanonicalSignInOnAuthStartRoute()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = CreateService(configuration);

        var chrome = service.BuildPublicChrome("Auth", "Provider handoff.", "/auth/google/start");

        var signIn = Assert.Single(chrome.HeaderActions, action => action.Label == "Sign in");
        Assert.Equal("/login?next=/home", signIn.Href);
    }

    [Fact]
    public void BuildPublicChromeUsesContextualDirectInstallRouteWhenGuestInstallIsAllowed()
    {
        string root = Path.Combine(Path.GetTempPath(), "hub-chrome-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            File.WriteAllText(
                Path.Combine(root, "releases.json"),
                """
                {
                  "version": "run-20260416-chrome",
                  "channel": "preview",
                  "publishedAt": "2026-04-16T09:00:00Z",
                  "downloads": [
                    {
                      "id": "avalonia-win-x64-installer",
                      "platform": "Avalonia Desktop Windows x64 Installer",
                      "url": "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                      "sha256": "win-direct",
                      "sizeBytes": 202,
                      "head": "avalonia",
                      "platformId": "win-x64",
                      "arch": "x64",
                      "kind": "installer",
                      "fileName": "chummer-avalonia-win-x64-installer.exe",
                      "installAccessClass": "open_public"
                    }
                  ],
                  "proofStatus": "passed",
                  "proofRoutes": [
                    "/downloads/get/avalonia-win-x64-installer"
                  ]
                }
                """);

            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root,
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = root
                })
                .Build();

            var service = CreateService(configuration, "Mozilla/5.0 (Windows NT 10.0; Win64; x64)");
            var chrome = service.BuildPublicChrome("FAQ", "Install answers.", "/faq");

            Assert.NotNull(chrome.PublicPrimaryCta);
            Assert.Equal("Install Chummer on Windows", chrome.PublicPrimaryCta!.Label);
            Assert.Equal("/downloads/get/avalonia-win-x64-installer", chrome.PublicPrimaryCta.Href);

            var primary = Assert.Single(chrome.HeaderActions, action => string.Equals(action.Tone, "primary", StringComparison.OrdinalIgnoreCase));
            Assert.Equal("Install Chummer on Windows", primary.Label);
            Assert.Equal("/downloads/get/avalonia-win-x64-installer", primary.Href);
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
    public void BuildAuthenticatedChromeOmitsBuildForNonOwnerEmail()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = CreateService(configuration);

        var chrome = service.BuildAuthenticatedChrome(
            "Home",
            "Signed-in shell.",
            "/home",
            "Other User",
            "someone@example.com");

        Assert.DoesNotContain(
            chrome.HeaderActions,
            action => string.Equals(action.Href, "/downloads/release-upload", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void BuildAuthenticatedChromeIncludesBuildForReleaseUploadOwner()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = CreateService(configuration);

        var chrome = service.BuildAuthenticatedChrome(
            "Home",
            "Signed-in shell.",
            "/home",
            "Tibor",
            ReleaseUploadAccessPolicy.AllowedEmail);

        var buildAction = Assert.Single(
            chrome.HeaderActions,
            action => string.Equals(action.Href, "/downloads/release-upload", StringComparison.OrdinalIgnoreCase));
        Assert.Equal("Build", buildAction.Label);
    }
}
