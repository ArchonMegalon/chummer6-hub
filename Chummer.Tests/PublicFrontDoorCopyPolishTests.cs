using System.Text.RegularExpressions;
using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed partial class PublicFrontDoorCopyPolishTests
{
    [Theory]
    [InlineData("Landing.cshtml")]
    [InlineData("Downloads.cshtml")]
    [InlineData("Faq.cshtml")]
    [InlineData("Horizons.cshtml")]
    [InlineData("Now.cshtml")]
    [InlineData("Roadmap.cshtml")]
    [InlineData("Status.cshtml")]
    [InlineData("ProductStory.cshtml")]
    [InlineData("TrustPage.cshtml")]
    [InlineData("SupportSubmitted.cshtml")]
    [InlineData("Packages.cshtml")]
    [InlineData("PackageDetail.cshtml")]
    [InlineData("PackageReceipt.cshtml")]
    public void Public_front_door_views_avoid_internal_ai_and_proof_language(string viewName)
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", viewName));
        string visibleText = ExtractVisibleText(view);

        Assert.DoesNotMatch(StandaloneAiRegex(), visibleText);
        foreach (string marker in ForbiddenVisibleMarkers)
        {
            Assert.DoesNotContain(marker, visibleText, StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public void Public_landing_manifest_keeps_black_ledger_out_of_first_impression_copy()
    {
        string manifest = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_LANDING_MANIFEST.yaml"));
        string firstImpression = string.Join(Environment.NewLine, manifest.Split('\n').Take(80));

        Assert.DoesNotContain("Black Ledger", firstImpression, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Real product proof", firstImpression, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Projection compiled", firstImpression, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("horizon_summary", manifest, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("public horizon set", manifest, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Download Chummer", firstImpression, StringComparison.Ordinal);
    }

    [Fact]
    public void Shared_layout_does_not_depend_on_client_side_copy_rewrites()
    {
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));

        Assert.DoesNotContain("public-copy-polish.js", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("public-copy-humanizer.js", layout, StringComparison.Ordinal);
    }

    [Fact]
    public void Minimal_public_tier_avoids_black_ledger_and_proof_card_language()
    {
        string[] minimalRouteViews =
        [
            "Landing.cshtml",
            "Downloads.cshtml",
            "Faq.cshtml",
            "Status.cshtml"
        ];

        foreach (string viewName in minimalRouteViews)
        {
            string source = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", viewName));
            string visibleText = ExtractVisibleText(source);

            Assert.DoesNotContain("Black Ledger", visibleText, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("route-choice-card__proof", source, StringComparison.Ordinal);
            Assert.DoesNotContain("Proof = new", source, StringComparison.Ordinal);
            Assert.DoesNotContain("choice.Proof", source, StringComparison.Ordinal);
        }
    }

    [Fact]
    public void Minimal_public_navigation_avoids_maintenance_signal_and_internal_routes()
    {
        string navigation = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_NAVIGATION.yaml"));
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));

        string[] firstVisitNavigation =
        [
            "primary_nav:",
            navigation.Split("public_signal_nav:", StringSplitOptions.None)[0],
            "secondary_nav:",
            navigation.Split("secondary_nav:", StringSplitOptions.None)[1].Split("utility_nav:", StringSplitOptions.None)[0]
        ];
        string firstVisitSource = string.Join(Environment.NewLine, firstVisitNavigation);

        Assert.Contains("new PublicNavigationLink(\"Home\", \"/\")", layout, StringComparison.Ordinal);
        Assert.Contains("new PublicNavigationLink(\"Get Chummer\", \"/downloads\")", layout, StringComparison.Ordinal);
        Assert.Contains("new PublicNavigationLink(\"Help\", \"/help\")", layout, StringComparison.Ordinal);
        Assert.Contains("@foreach (var link in primaryDrawerLinks)", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("@foreach (var link in compactDrawerLinks)", layout, StringComparison.Ordinal);

        foreach (string hiddenRoute in new[]
        {
            "Black Ledger",
            "/ledger",
            "horizons",
            "/horizons",
            "roadmap",
            "/roadmap",
            "changelog",
            "/changelog",
            "feedback",
            "/feedback",
            "proof",
            "receipt",
            "provider"
        })
        {
            Assert.DoesNotContain(hiddenRoute, firstVisitSource, StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public void Public_front_door_does_not_claim_macos_as_a_normal_public_download_lane()
    {
        string publicFrontDoorCopy = string.Join(
            Environment.NewLine,
            File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs")),
            File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml")),
            File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Services", "PublicPackageCatalogService.cs")));

        Assert.DoesNotContain("Windows, macOS, and Linux", publicFrontDoorCopy, StringComparison.Ordinal);
        Assert.Contains(
            "Windows and Linux are public now. macOS is guided support only for now.",
            publicFrontDoorCopy,
            StringComparison.Ordinal);
        Assert.Contains("Windows and Linux public, macOS guided support only", publicFrontDoorCopy, StringComparison.Ordinal);
    }

    [Fact]
    public void Public_copy_humanizer_removes_internal_release_vocabulary()
    {
        string cleaned = PublicFacingCopyHumanizer.Clean("ALICE generated an AI proof receipt for the Black Ledger operator lane.");

        Assert.Equal("character help created a status for the campaign city user path.", cleaned);
        Assert.DoesNotContain("Alice", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("AI", cleaned, StringComparison.Ordinal);
        Assert.DoesNotContain("assistant", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("proof", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("receipt", cleaned, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Public_copy_humanizer_removes_assistant_branding_without_doubled_help_copy()
    {
        string cleaned = PublicFacingCopyHumanizer.Clean("An AI assistant can explain this generated provider artifact.");

        Assert.Equal("help can explain this created service file.", cleaned);
        Assert.DoesNotContain("AI", cleaned, StringComparison.Ordinal);
        Assert.DoesNotContain("assistant", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("help help", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("provider", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("artifact", cleaned, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Public_copy_humanizer_replaces_horizon_maintenance_vocabulary()
    {
        string cleaned = PublicFacingCopyHumanizer.Clean("Read the horizon brief before opening the horizon-only proof trail.");

        Assert.Equal("Read the roadmap note before opening the roadmap-only details.", cleaned);
        Assert.DoesNotContain("horizon", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("proof", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("checks", cleaned, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Public_copy_humanizer_does_not_replace_short_terms_inside_words()
    {
        string cleaned = PublicFacingCopyHumanizer.Clean("The plane view mentions an install rail and a lane without proof.");

        Assert.Equal("The plane view mentions a linked copy and a path without status.", cleaned);
        Assert.DoesNotContain("ppath", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("install rail", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(" lane ", cleaned, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Public_copy_humanizer_removes_review_and_validation_jargon()
    {
        string cleaned = PublicFacingCopyHumanizer.Clean("An audit verdict says verified validation checks passed on the return rail.");

        Assert.Equal("a review status says confirmed review details passed on the return path.", cleaned);
        Assert.DoesNotContain("audit", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("verdict", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("verified", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("validation", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("checks", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("rail", cleaned, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Secondary_public_workflow_views_do_not_reintroduce_maintenance_language()
    {
        foreach (string viewName in new[]
                 {
                     "ReadyForTonight.cshtml",
                     "JoinPrimer.cshtml",
                     "DownloadDispatch.cshtml",
                     "Ledger.cshtml"
                 })
        {
            string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", viewName));
            string visibleText = ExtractVisibleText(view);

            foreach (string marker in new[]
                     {
                         "Session-start verdict",
                         "Guided setup assistant",
                         "proof trail",
                         "proof receipt",
                         "install rail",
                         "continuity rail",
                         "first-party email rail",
                         "Faction rail",
                         "governed joining",
                         "without losing provenance"
                     })
            {
                Assert.DoesNotContain(marker, visibleText, StringComparison.OrdinalIgnoreCase);
            }
        }
    }

    [Fact]
    public void Public_api_sources_do_not_reintroduce_old_human_copy_markers()
    {
        string apiRoot = RepoPaths.FromRoot("Chummer.Run.Api");
        string[] sourceFiles = Directory.EnumerateFiles(apiRoot, "*.*", SearchOption.AllDirectories)
            .Where(static path => path.EndsWith(".cs", StringComparison.OrdinalIgnoreCase)
                || path.EndsWith(".cshtml", StringComparison.OrdinalIgnoreCase))
            .Where(static path => !path.EndsWith($"{Path.DirectorySeparatorChar}PublicFacingCopyHumanizer.cs", StringComparison.OrdinalIgnoreCase))
            .ToArray();

        string[] forbiddenPhrases =
        [
            "No current local release-proof receipt",
            "receipt-backed work after validation",
            "Output audit",
            "Check your email",
            "Verification sent",
            "Release proof",
            "release proof",
            "public proof shelf",
            "proof shelf ref",
            "stable public proof shelf",
            "Evidence first",
            "Availability check",
            "Release check pending",
            "Windows proof-installer",
            "Last verified",
            "Last checked",
            "Open checks",
            "World turn check",
            "Turn checks",
            "Check the current release posture",
            "published rules checks",
            "Desktop flagship checks",
            "direct checks are green",
            "setup checks the install-link receipt",
            "Finish verified and linked",
            "Proof receipts",
            "receipt-backed",
            "release-truth substitution",
            "Session-start verdict",
            "Guided setup assistant",
            "first-party email rail",
            "Faction rail",
            "without losing provenance"
        ];

        foreach (string file in sourceFiles)
        {
            string searchable = string.Join(
                '\n',
                File.ReadLines(file)
                    .Where(static line => !line.Contains(".Replace(", StringComparison.Ordinal))
                    .Where(static line => !line.Contains("route-choice-card__proof", StringComparison.Ordinal))
                    .Where(static line => !line.Contains("trust-claim__microproof", StringComparison.Ordinal))
                    .Where(static line => !line.Contains("mono-receipt", StringComparison.Ordinal)));

            foreach (string phrase in forbiddenPhrases)
            {
                Assert.DoesNotContain(phrase, searchable, StringComparison.Ordinal);
            }
        }
    }

    [Fact]
    public void Auth_entry_avoids_internal_install_link_language()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Auth", "Entry.cshtml"));
        string visibleText = ExtractVisibleText(view);

        Assert.DoesNotContain("handoff", visibleText, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("callback", visibleText, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("manual open", visibleText, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("claim this copy", visibleText, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Keep this install attached to your account.", visibleText, StringComparison.Ordinal);
    }

    private static readonly string[] ForbiddenVisibleMarkers =
    [
        "generated by AI",
        "AI-generated",
        "assistant",
        "proof",
        "receipt",
        "validation",
        "verification",
        "verdict",
        "audit",
        "artifact",
        "rail",
        "operator",
        "grounded",
        "governed",
        "source packet",
        "Black Ledger",
        "Starter lane",
        "world lanes",
        "account-assisted install",
        "Open horizons",
        "Home or Horizons",
        "product thread",
        "product threads"
    ];

    private static string ExtractVisibleText(string view)
    {
        string withoutCode = RazorTopCodeBlockRegex().Replace(view, " ");
        withoutCode = RazorFunctionsBlockRegex().Replace(withoutCode, " ");
        var textNodes = HtmlTextNodeRegex()
            .Matches(withoutCode)
            .Select(static match => RazorExpressionRegex().Replace(match.Groups[1].Value, " "))
            .Where(static text => !string.IsNullOrWhiteSpace(text))
            .Where(static text => !text.Contains('{', StringComparison.Ordinal)
                && !text.Contains('}', StringComparison.Ordinal)
                && !text.Contains(';', StringComparison.Ordinal)
                && !text.Contains(" var ", StringComparison.Ordinal));
        return WhitespaceRegex().Replace(string.Join(" ", textNodes), " ").Trim();
    }

    [GeneratedRegex(@"@\{[\s\S]*?\n\}\s*(?=<)", RegexOptions.CultureInvariant)]
    private static partial Regex RazorTopCodeBlockRegex();

    [GeneratedRegex(@"^@functions\s*\{[\s\S]*?^\}\s*(?=<)", RegexOptions.Multiline | RegexOptions.CultureInvariant)]
    private static partial Regex RazorFunctionsBlockRegex();

    [GeneratedRegex(@">([^<]+)<", RegexOptions.CultureInvariant)]
    private static partial Regex HtmlTextNodeRegex();

    [GeneratedRegex(@"@\(?[A-Za-z0-9_\.]+[^ \t\r\n<]*\)?", RegexOptions.CultureInvariant)]
    private static partial Regex RazorExpressionRegex();

    [GeneratedRegex(@"\bAI\b", RegexOptions.CultureInvariant)]
    private static partial Regex StandaloneAiRegex();

    [GeneratedRegex(@"\s+", RegexOptions.CultureInvariant)]
    private static partial Regex WhitespaceRegex();
}
