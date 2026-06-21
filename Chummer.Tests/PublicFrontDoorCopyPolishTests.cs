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
        Assert.DoesNotContain("primary route", firstImpression, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("lab routes", firstImpression, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("horizon_summary", manifest, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("public horizon set", manifest, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Download Chummer", firstImpression, StringComparison.Ordinal);
        Assert.Contains("downloads stay the simplest way to try Chummer", firstImpression, StringComparison.Ordinal);
        Assert.Contains("Experimental surfaces stay off the main path", firstImpression, StringComparison.Ordinal);
    }

    [Fact]
    public void Public_feature_registry_start_and_release_cards_use_plain_copy()
    {
        string[] registryPaths =
        [
            RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_FEATURE_REGISTRY.yaml"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "PUBLIC_FEATURE_REGISTRY.yaml")
        ];

        foreach (string registryPath in registryPaths)
        {
            string registry = File.ReadAllText(registryPath);

            foreach (string forbidden in new[]
            {
                "A current build exists now, not just a story about one.",
                "Receipt-backed continuity",
                "provenance rules",
                "compatibility, and receipts",
                "cannot route, close, and explain",
                "Deterministic rules truth",
                "Clean audit trail",
                "Records and provenance",
                "Visible evidence",
                "integrity trail",
                "hard to verify",
                "desktop artifact",
                "live verification",
                "truthful bootstrap",
                "public-release lane",
                "verify the release",
                "Explanation receipt trail",
                "The proof view",
                "Inspect the receipt trail",
                "Proof: NEXUS-PAN",
                "continuity route",
                "Compare grounded tradeoffs with receipts",
                "Proof: Origin Dossier",
                "receipt-backed",
                "citations and receipts",
                "Inspect the live explanation",
                "Open the briefing receipt",
                "fictional truth",
                "packet rails",
                "Open the prep receipt",
                "Open the control receipt",
                "Open the public route",
                "ops lane",
                "Chummer-owned truth",
                "Inspect the starter receipt",
                "first safe route into Chummer",
                "Inspect the ruleset-head receipt",
                "first-party lane",
                "primer packet",
                "Open the Anarchy lane",
                "Inspect the runtime receipt",
                "Receipt-backed export",
                "after-action truth",
                "Inspect the replay receipt",
                "After-action packet",
                "optional-acceleration lane",
                "Open the acceleration receipt",
                "capability and policy packet rails",
                "source traces and modifier trails",
                "artifact bundles with provenance",
                "mobile and PWA projection lane",
                "desktop rules truth",
                "package routes",
                "losing Chummer provenance",
                "approved origin canon into contacts, debts, scars, secrets, media packets",
                "one noisy lane",
                "Open the governed rules lane",
                "public route instead of only research wording",
                "severing provenance",
                "mission packets",
                "first-party rail",
                "first-class artifacts",
                "signed-in return rails",
                "trusted lanes",
                "Hidden lab route",
                "event trail",
                "truthful channel label",
                "Inspect the runsite pack",
                "credible mission packet",
                "Inspect the dossier brief",
                "Inspect the campaign primer",
                "Inspect the primer-video lane",
                "approved run packets",
                "Inspect the mission-brief lane",
                "Inspect the after-action preview",
                "Projection only",
                "Public roadmap projection",
                "artifact proof",
                "Closeout proof",
                "governed discovery packets",
                "product review routing",
                "fuzzy assistants",
                "ALICE context",
                "assistant folklore",
                "non-authoritative",
                "first-party continuity",
                "first-party trust records",
                "first-party open-run",
                "first-party rules-light",
                "first-party support",
                "first-party aggregate",
                "first-party download",
                "typed GM-control APIs",
                "Typed GM-control APIs",
                "typed starter/recovery APIs",
                "Typed starter/recovery APIs",
                "typed edition-head APIs",
                "Typed edition-head APIs",
                "typed jump-target APIs",
                "Typed jump APIs",
                "typed capability/policy APIs",
                "operator ritual",
                "first-party prompts"
            })
            {
                Assert.DoesNotContain(forbidden, registry, StringComparison.Ordinal);
            }

            Assert.Contains("Current builds are published and ready to download.", registry, StringComparison.Ordinal);
            Assert.Contains("Recorded continuity keeps the table moving", registry, StringComparison.Ordinal);
            Assert.Contains("Repeatable rules math", registry, StringComparison.Ordinal);
            Assert.Contains("Readable records", registry, StringComparison.Ordinal);
            Assert.Contains("download details are live right now", registry, StringComparison.Ordinal);
            Assert.Contains("See the explanation trail", registry, StringComparison.Ordinal);
            Assert.Contains("NEXUS-PAN now has a Chummer continuity page", registry, StringComparison.Ordinal);
            Assert.Contains("vague suggestions", registry, StringComparison.Ordinal);
            Assert.Contains("later build-help context", registry, StringComparison.Ordinal);
            Assert.Contains("Derived projections", registry, StringComparison.Ordinal);
            Assert.Contains("Compare grounded tradeoffs with readable history", registry, StringComparison.Ordinal);
            Assert.Contains("Open the briefing", registry, StringComparison.Ordinal);
            Assert.Contains("Open the prep page", registry, StringComparison.Ordinal);
            Assert.Contains("Open the public page", registry, StringComparison.Ordinal);
            Assert.Contains("working GM-control support", registry, StringComparison.Ordinal);
            Assert.Contains("working starter/recovery support", registry, StringComparison.Ordinal);
            Assert.Contains("working edition support", registry, StringComparison.Ordinal);
            Assert.Contains("Chummer open-run support", registry, StringComparison.Ordinal);
            Assert.Contains("Open Anarchy", registry, StringComparison.Ordinal);
            Assert.Contains("Reviewable export", registry, StringComparison.Ordinal);
            Assert.Contains("Replay and after-action history", registry, StringComparison.Ordinal);
            Assert.Contains("Open the replay page", registry, StringComparison.Ordinal);
            Assert.Contains("working capability controls", registry, StringComparison.Ordinal);
            Assert.Contains("Open the acceleration details", registry, StringComparison.Ordinal);
            Assert.Contains("Publish primers, briefing reels, and bundles without losing context.", registry, StringComparison.Ordinal);
            Assert.Contains("Open the continuity page", registry, StringComparison.Ordinal);
            Assert.Contains("Open the rules page", registry, StringComparison.Ordinal);
            Assert.Contains("Open the runsite pack", registry, StringComparison.Ordinal);
            Assert.Contains("Open the primer video", registry, StringComparison.Ordinal);
            Assert.Contains("Open the mission brief", registry, StringComparison.Ordinal);
            Assert.Contains("Public roadmap", registry, StringComparison.Ordinal);
            Assert.Contains("Roadmap cards are planning signals", registry, StringComparison.Ordinal);
            Assert.Contains("Chummer checks the update before voter notifications are sent.", registry, StringComparison.Ordinal);
            Assert.Contains("focused discovery with Chummer prompts", registry, StringComparison.Ordinal);
        }
    }

    [Fact]
    public void Public_landing_asset_registry_uses_plain_alt_and_caption_copy()
    {
        string[] registryPaths =
        [
            RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_LANDING_ASSET_REGISTRY.yaml"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "PUBLIC_LANDING_ASSET_REGISTRY.yaml")
        ];

        foreach (string registryPath in registryPaths)
        {
            string registry = File.ReadAllText(registryPath);

            foreach (string forbidden in new[]
            {
                "operator relationship",
                "blue proof light",
                "verification image",
                "evidence markers",
                "Future lanes image",
                "solo operator",
                "Creator proof image",
                "Player lane image",
                "GM lane image",
                "Creator lane image",
                "Secure contribution lane",
                "verification pressure cues",
                "Participation lane image"
            })
            {
                Assert.DoesNotContain(forbidden, registry, StringComparison.OrdinalIgnoreCase);
            }

            Assert.Contains("support relationship", registry, StringComparison.Ordinal);
            Assert.Contains("blue desk light", registry, StringComparison.Ordinal);
            Assert.Contains("Rules review image", registry, StringComparison.Ordinal);
            Assert.Contains("Future areas image", registry, StringComparison.Ordinal);
            Assert.Contains("one maintainer", registry, StringComparison.Ordinal);
            Assert.Contains("Creator review image", registry, StringComparison.Ordinal);
            Assert.Contains("Player path image", registry, StringComparison.Ordinal);
            Assert.Contains("GM path image", registry, StringComparison.Ordinal);
            Assert.Contains("Creator path image", registry, StringComparison.Ordinal);
            Assert.Contains("Participation image", registry, StringComparison.Ordinal);
        }
    }

    [Fact]
    public void Public_help_and_faq_source_copy_uses_plain_user_language()
    {
        string publicFaq = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_FAQ_REGISTRY.yaml"));
        string publicHelp = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_HELP_COPY.md"));
        string canonicalPublicHelp = File.ReadAllText(RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "PUBLIC_HELP_COPY.md"));
        string combined = string.Join(Environment.NewLine, publicFaq, publicHelp, canonicalPublicHelp);

        Assert.Contains("schedule and session details", publicFaq, StringComparison.Ordinal);
        Assert.Contains("## Public feedback", publicHelp, StringComparison.Ordinal);
        Assert.Contains("## Private crash reports", publicHelp, StringComparison.Ordinal);
        Assert.Contains("which outside tool helped", publicHelp, StringComparison.Ordinal);

        foreach (string forbidden in new[]
        {
            "handoff details",
            "Public feedback lane",
            "future product lane",
            "Chummer-owned truth",
            "which provider, model, or support adapter",
            "Private crash lane",
            "fixed truth",
            "fallback routes",
            "normal routes stay visible",
            "source packets",
            "public-guide source registries",
            "generated guide output",
            "Katteb-assisted",
            "campaign/world truth",
            "When those lanes"
        })
        {
            Assert.DoesNotContain(forbidden, combined, StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public void Public_guide_policy_and_export_manifest_use_plain_source_copy()
    {
        string[] sources =
        [
            RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_GUIDE_POLICY.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "PUBLIC_GUIDE_POLICY.md"),
            RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_GUIDE_EXPORT_MANIFEST.yaml"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "PUBLIC_GUIDE_EXPORT_MANIFEST.yaml")
        ];

        string combined = string.Join(Environment.NewLine, sources.Select(File.ReadAllText));

        foreach (string forbidden in new[]
        {
            "proof shelf",
            "preview-proof",
            "first-party proofs",
            "source of truth",
            "help/support lane",
            "support lane",
            "operator jargon",
            "public intake lanes",
            "approved source packets",
            "source-registry changes",
            "generated guide output",
            "Clear proof links",
            "repo truth",
            "public guide truth",
            "AI-search",
            "core_product` lanes",
            "expansion_bet` lanes",
            "folded_into_product` lanes",
            "route through an explicit public-guide verdict",
            "omission receipt",
            "proof artifact",
            "provider lane",
            "runtime surface",
            "media lanes",
            "source overrides",
            "public projections only",
            "roadmap truth",
            "first useful routes",
            "operator state-machine terms",
            "guided contribution lane",
            "Chummer-owned source truth",
            "release or availability proof",
            "release matrix artifact",
            "honest artifact format",
            "bounded fallback and recovery routes",
            "implementation-truth trailheads",
            "future lanes"
        })
        {
            Assert.DoesNotContain(forbidden, combined, StringComparison.OrdinalIgnoreCase);
        }

        Assert.Contains("product homepage and invitation surface", combined, StringComparison.Ordinal);
        Assert.Contains("preview cards or first-party pages", combined, StringComparison.Ordinal);
        Assert.Contains("approved Chummer copy, screenshots, and release notes", combined, StringComparison.Ordinal);
        Assert.Contains("Clear deeper links", combined, StringComparison.Ordinal);
        Assert.Contains("generation report", combined, StringComparison.Ordinal);
        Assert.Contains("public planning views", combined, StringComparison.Ordinal);
        Assert.Contains("first useful pages", combined, StringComparison.Ordinal);
        Assert.Contains("release or availability status", combined, StringComparison.Ordinal);
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

        Assert.Equal("An update is ready for the campaign city.", cleaned);
        Assert.DoesNotContain("Alice", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("AI", cleaned, StringComparison.Ordinal);
        Assert.DoesNotContain("assistant", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("proof", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("receipt", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("workspace path", cleaned, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Public_copy_humanizer_removes_assistant_branding_without_doubled_help_copy()
    {
        string cleaned = PublicFacingCopyHumanizer.Clean("An AI assistant can explain this generated provider artifact.");

        Assert.Equal("Help can explain this prepared service file.", cleaned);
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

        Assert.Equal("Read the maintenance note before opening the private details.", cleaned);
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
    public void Public_copy_humanizer_replaces_handoff_language_with_plain_next_steps()
    {
        string cleaned = PublicFacingCopyHumanizer.Clean("The signed-in handoff code keeps follow-up handoffs attached.");

        Assert.Equal("The signed-in access code keeps follow-up next steps attached.", cleaned);
        Assert.DoesNotContain("handoff", cleaned, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Public_copy_humanizer_removes_review_and_validation_jargon()
    {
        string cleaned = PublicFacingCopyHumanizer.Clean("An audit verdict says verified validation checks passed on the return rail.");

        Assert.Equal("The return path is ready.", cleaned);
        Assert.DoesNotContain("audit", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("verdict", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("verified", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("validation", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("checks", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("rail", cleaned, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Public_copy_humanizer_removes_packet_and_posture_jargon()
    {
        string cleaned = PublicFacingCopyHumanizer.Clean("Open the JSON packet when roadmap readiness posture and command posture matter.");

        Assert.Equal("Open the details when roadmap readiness and command state matter.", cleaned);
        Assert.DoesNotContain("JSON packet", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("posture", cleaned, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Public_copy_humanizer_removes_plural_proof_receipt_and_check_language()
    {
        string cleaned = PublicFacingCopyHumanizer.Clean("Proof receipts and public proofs show provider validation checks passed.");

        Assert.Equal("Status details and public status details show service review ready.", cleaned);
        Assert.DoesNotContain("proof", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("receipt", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("provider", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("validation", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("checks", cleaned, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Public_copy_humanizer_cleans_black_ledger_command_jargon()
    {
        string cleaned = PublicFacingCopyHumanizer.Clean("Signal Deck command rail keeps governed consequence posture, receipts, and bounded aftermath on first-party rails.");

        Assert.Equal("Signal Deck command path keeps reviewed consequence status, records, and limited aftermath on Chummer paths.", cleaned);
        Assert.DoesNotContain("rail", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("governed", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("posture", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("receipt", cleaned, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("bounded", cleaned, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Ready_for_tonight_copy_uses_plain_session_language()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string service = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Services", "ReadyForTonightService.cs"));
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "ReadyForTonight.cshtml"));
        string combined = string.Join(Environment.NewLine, controller, service);

        Assert.Contains("role status, starter loadouts, session files, and mobile setup", combined, StringComparison.Ordinal);
        Assert.Contains("table role", combined, StringComparison.Ordinal);
        Assert.Contains("export path", combined, StringComparison.Ordinal);
        Assert.Contains("Download starter file", view, StringComparison.Ordinal);
        Assert.Contains("downloadable setup", view, StringComparison.Ordinal);

        foreach (string forbidden in new[]
        {
            "session-start rail",
            "table lane",
            "mobile handoff",
            "export handoff",
            "export rail",
            "support rails",
            "bounded legal-baseline",
            "bounded prep packet",
            "Bounded combat-ready",
            "Bounded awakened",
            "Join/run rail",
            "public-run handoff",
            "moderation posture"
        })
        {
            Assert.DoesNotContain(forbidden, combined, StringComparison.OrdinalIgnoreCase);
        }

        foreach (string forbiddenViewDetail in new[]
        {
            "verdict.ProofReceipts",
            "verdict.NextBestScreen",
            "Status: @verdict.Status",
            "Download starter loadout JSON",
            "machine-readable copy"
        })
        {
            Assert.DoesNotContain(forbiddenViewDetail, view, StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public void Black_ledger_connected_lane_copy_avoids_internal_process_words()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string connectedLaneSource = string.Join(
            '\n',
            new[]
            {
                SliceSource(controller, "private static BlackLedgerFollowThroughPacketViewModel BuildLedgerFollowThroughPacket"),
                SliceSource(controller, "private static BlackLedgerConnectedLanePacketViewModel BuildRunnerPassportConnectedLanePacket"),
                SliceSource(controller, "private static BlackLedgerConnectedLanePacketViewModel BuildSignalDeckConnectedLanePacket"),
                SliceSource(controller, "private static BlackLedgerConnectedLanePacketViewModel BuildLivingWorldConnectedLanePacket"),
                SliceSource(controller, "private static BlackLedgerConnectedLanePacketViewModel BuildLedgerWorkspaceConnectedLanePacket"),
                SliceSource(controller, "private static BlackLedgerTablePulsePacketViewModel BuildLedgerTablePulsePacket"),
                SliceSource(controller, "private static BlackLedgerGmCockpitPacketViewModel BuildLedgerGmCockpitPacket")
            });

        foreach (string phrase in new[]
                 {
                     "command rail",
                     "continuity rail",
                     "aftermath rail",
                     "Trust rail",
                     "signed-in account lane",
                     "first-party rails",
                     "recipient lane",
                     "promo rail",
                     "advisory lane",
                     "GM bounded",
                     "private return lane",
                     "world authority",
                     "detached minigame truth",
                     "governed consequence posture",
                     "governed return-loop rail",
                     "governed aftermath rail",
                     "participation receipt(s)"
                 })
        {
            Assert.DoesNotContain(phrase, connectedLaneSource, StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public void Public_maintenance_feature_page_copy_avoids_internal_process_words()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string[] publicFeatureMethodMarkers =
        [
            "public async Task<IActionResult> MobileProjectionPage",
            "public async Task<IActionResult> ParticipatePage",
            "public async Task<IActionResult> AlicePage",
            "public async Task<IActionResult> TablePulsePage",
            "private async Task<KnowledgeFabricPageViewModel> BuildKnowledgeFabricPageModel",
            "private async Task<MobileProjectionPageViewModel> BuildMobileProjectionPageModel",
            "private async Task<NexusPanContinuityPageViewModel> BuildNexusPanContinuityPageModel",
            "private async Task<MediaArtifactHorizonPageViewModel> BuildJackpointPageModel",
            "private async Task<MediaArtifactHorizonPageViewModel> BuildRunsitePageModel",
            "private async Task<MediaArtifactHorizonPageViewModel> BuildRunControlPageModel",
            "private async Task<MediaArtifactHorizonPageViewModel> BuildOnrampPageModel",
            "private async Task<MediaArtifactHorizonPageViewModel> BuildEditionStudioPageModel",
            "private async Task<MediaArtifactHorizonPageViewModel> BuildLocalCoProcessorPageModel",
            "private async Task<MediaArtifactHorizonPageViewModel> BuildRunbookPageModel",
            "private async Task<MediaArtifactHorizonPageViewModel> BuildCommunityHubPageModel",
            "private async Task<MediaArtifactHorizonPageViewModel> BuildCreatorOsPageModel",
            "private async Task<MediaArtifactHorizonPageViewModel> BuildQuicksilverPageModel",
            "private async Task<MediaArtifactHorizonPageViewModel> BuildRunnerPassportPageModel",
            "private async Task<MediaArtifactHorizonPageViewModel> BuildSignalDeckPageModel",
            "private async Task<MediaArtifactHorizonPageViewModel> BuildLivingWorldPageModel",
            "private async Task<MediaArtifactHorizonPageViewModel> BuildGhostwirePageModel"
        ];

        foreach (string methodMarker in publicFeatureMethodMarkers)
        {
            string methodSource = SliceSource(controller, methodMarker);
            foreach (Match match in CSharpStringLiteralRegex().Matches(methodSource))
            {
                string value = match.Groups[1].Value;
                if (LooksLikeRouteOrIdentifier(value))
                {
                    continue;
                }

                foreach (Regex forbidden in InternalProcessWordRegexes)
                {
                    Assert.DoesNotMatch(forbidden, value);
                }
            }
        }
    }

    [Fact]
    public void Secondary_public_workflow_views_do_not_reintroduce_maintenance_language()
    {
        foreach (string viewName in new[]
                 {
                     "ReadyForTonight.cshtml",
                     "JoinPrimer.cshtml",
                     "DownloadDispatch.cshtml",
                     "Ledger.cshtml",
                     "Changelog.cshtml",
                     "MobileProjection.cshtml",
                     "KarmaForgeSubmitted.cshtml",
                     "FeedbackOperationsDetail.cshtml",
                     "GmSessionVenue.cshtml",
                     "PublicCreatorPublication.cshtml",
                     "KnowledgeFabric.cshtml",
                     "NexusPanContinuity.cshtml"
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
                         "without losing provenance",
                         "This rail",
                         "privacy-sensitive lane",
                         "governed stages",
                         "These lanes",
                         "update posture",
                         "venue posture",
                         "provider payload",
                         "Provider link",
                         "Provider create available",
                         "video service",
                         "video-service payloads",
                         "service setup",
                         "service sync",
                         "Black Ledger continuity",
                         "Open detail artifact",
                         "Open aggregate artifact",
                         "Open source artifact",
                         "Open thread artifact",
                         "bounded drilldown",
                         "Saved pivot",
                         "Queue posture",
                         "Hub outbox",
                         "Journey writeback",
                         "raw delivery payloads",
                         "provider setup",
                         "operating posture",
                         "send posture",
                         "release-facing trail",
                         "Download handoff",
                         "Page handoff",
                         "Build handoff",
                         "Open lead build handoff",
                         "handoff JSON",
                         "packet data",
                         "Packet detail",
                         "packet stays high-signal",
                         "canonical prompts",
                         "Named bounded roles",
                         "Still bounded",
                         "creator concierge",
                         "testimonial wrapper",
                         "lineage, provenance",
                         "Governed product decision",
                         "HouseRuleDemandPacket",
                         "KarmaForgeCandidate",
                         "Linked update",
                         "required detail"
                     })
            {
                Assert.DoesNotContain(marker, visibleText, StringComparison.OrdinalIgnoreCase);
            }
        }
    }

    [Fact]
    public void Helper_page_receipt_bindings_clean_dynamic_public_copy()
    {
        string knowledgeFabric = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "KnowledgeFabric.cshtml"));
        string nexusPan = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "NexusPanContinuity.cshtml"));

        foreach (string cleanedBinding in new[]
                 {
                     "PublicFacingCopyHumanizer.Clean(receipt.Status)",
                     "PublicFacingCopyHumanizer.Clean(receipt.Topic)",
                     "PublicFacingCopyHumanizer.Clean(receipt.Summary)",
                     "PublicFacingCopyHumanizer.Clean(receipt.Provenance)"
                 })
        {
            Assert.Contains(cleanedBinding, knowledgeFabric, StringComparison.Ordinal);
        }

        foreach (string cleanedBinding in new[]
                 {
                     "PublicFacingCopyHumanizer.Clean(receipt.Status)",
                     "PublicFacingCopyHumanizer.Clean(receipt.Topic)",
                     "PublicFacingCopyHumanizer.Clean(receipt.Summary)",
                     "PublicFacingCopyHumanizer.Clean(receipt.Route)"
                 })
        {
            Assert.Contains(cleanedBinding, nexusPan, StringComparison.Ordinal);
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
            "without losing provenance",
            "This rail",
            "privacy-sensitive lane",
            "governed stages",
            "These lanes",
            "update posture",
            "venue posture",
            "provider payload",
            "provider setup",
            "operating posture",
            "send posture",
            "release-facing trail",
            "Package operator summary",
            "Private summary of package classes, compatibility posture",
            "main recommended shelf",
            "same install rail",
            "Artifacts never become the system of record for rules or account truth",
            "Proposal posture must stay honest",
            "bounded consult handoff",
            "Search bounded receipt and thread drilldowns",
            "Recent bounded receipt and thread drilldowns",
            "Recent bounded drilldown",
            "Composite bounded receipt match",
            "full feedback rail",
            "source receipt id, dispatch receipt id",
            "detail trail",
            "dead external handoff"
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
        Assert.Contains("Claiming only connects this copy to your account.", visibleText, StringComparison.Ordinal);
        Assert.Contains("Keep this copy attached to your account.", visibleText, StringComparison.Ordinal);
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

    private static readonly Regex[] InternalProcessWordRegexes =
    [
        new(@"\bproof\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant),
        new(@"\breceipts?\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant),
        new(@"\baudits?\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant),
        new(@"\bverdict\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant),
        new(@"\bverification\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant),
        new(@"\bvalidated?\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant),
        new(@"\bgoverned\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant),
        new(@"\bprovider\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant),
        new(@"\bposture\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant),
        new(@"\bhorizons?\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant),
        new(@"\brails?\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant),
        new(@"\blanes?\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)
    ];

    private static string SliceSource(string source, string startMarker)
    {
        int start = source.IndexOf(startMarker, StringComparison.Ordinal);
        Assert.True(start >= 0, $"Could not find public feature method marker '{startMarker}'.");

        int end = source.Length;
        foreach (string nextMarker in new[] { "\n    [Http", "\n    private " })
        {
            int candidate = source.IndexOf(nextMarker, start + startMarker.Length, StringComparison.Ordinal);
            if (candidate >= 0)
            {
                end = Math.Min(end, candidate);
            }
        }

        return source[start..end];
    }

    private static bool LooksLikeRouteOrIdentifier(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return true;
        }

        return value.Contains('/', StringComparison.Ordinal)
            || value.Contains('_', StringComparison.Ordinal)
            || value.Contains('%', StringComparison.Ordinal)
            || value.EndsWith(".json", StringComparison.OrdinalIgnoreCase)
            || value.EndsWith(".md", StringComparison.OrdinalIgnoreCase)
            || value.EndsWith(".cshtml", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("api", StringComparison.OrdinalIgnoreCase);
    }

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

    [GeneratedRegex("\"((?:\\\\.|[^\"])*)\"", RegexOptions.CultureInvariant)]
    private static partial Regex CSharpStringLiteralRegex();
}
