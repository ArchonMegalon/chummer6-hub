using System.Text.Json;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicSurfaceReferenceFilesTests
{
    [Fact]
    public void PublicLandingSurfaceDocTracksTheCurrentPublicRouteFamilies()
    {
        string docPath = RepoPaths.FromRoot("docs", "PUBLIC_LANDING_SURFACE.md");
        string doc = File.ReadAllText(docPath);

        Assert.Contains("/roadmap", doc, StringComparison.Ordinal);
        Assert.Contains("/feedback", doc, StringComparison.Ordinal);
        Assert.Contains("/changelog", doc, StringComparison.Ordinal);
        Assert.Contains("/ledger", doc, StringComparison.Ordinal);
        Assert.Contains("/alice", doc, StringComparison.Ordinal);
        Assert.Contains("/table-pulse", doc, StringComparison.Ordinal);
        Assert.Contains("/quicksilver", doc, StringComparison.Ordinal);
        Assert.Contains("/karma-forge", doc, StringComparison.Ordinal);
        Assert.Contains("/participate/karma-forge", doc, StringComparison.Ordinal);
        Assert.Contains("/feedback/operations", doc, StringComparison.Ordinal);
        Assert.Contains("milestone-backed public direction", doc, StringComparison.Ordinal);
        Assert.Contains("public signal, projected movement, and shipped updates", doc, StringComparison.Ordinal);
    }

    [Fact]
    public void MachineReadableGuideFilesExistForTheCurrentPublicRouteSplit()
    {
        string llmsPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "llms.txt");
        string aiPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "ai.txt");

        string llms = File.ReadAllText(llmsPath);
        string ai = File.ReadAllText(aiPath);

        Assert.Contains("/downloads", llms, StringComparison.Ordinal);
        Assert.Contains("/docs", llms, StringComparison.Ordinal);
        Assert.Contains("/docs/chummer6-quickstart", llms, StringComparison.Ordinal);
        Assert.Contains("/docs/chummer6-quickstart/receipts/publication.json", llms, StringComparison.Ordinal);
        Assert.Contains("/docs/chummer6-quickstart/download.pdf", llms, StringComparison.Ordinal);
        Assert.Contains("/roadmap", llms, StringComparison.Ordinal);
        Assert.Contains("/feedback", llms, StringComparison.Ordinal);
        Assert.Contains("/changelog", llms, StringComparison.Ordinal);
        Assert.Contains("/ledger", llms, StringComparison.Ordinal);
        Assert.Contains("/alice", llms, StringComparison.Ordinal);
        Assert.Contains("/table-pulse", llms, StringComparison.Ordinal);
        Assert.Contains("/quicksilver", llms, StringComparison.Ordinal);
        Assert.Contains("/local-co-processor", llms, StringComparison.Ordinal);
        Assert.Contains("/karma-forge", llms, StringComparison.Ordinal);
        Assert.Contains("/participate/karma-forge", llms, StringComparison.Ordinal);
        Assert.Contains("/llms.txt", ai, StringComparison.Ordinal);
        Assert.Contains("/docs", ai, StringComparison.Ordinal);
        Assert.Contains("/roadmap", ai, StringComparison.Ordinal);
        Assert.Contains("/feedback", ai, StringComparison.Ordinal);
        Assert.Contains("/contact", ai, StringComparison.Ordinal);
    }

    [Fact]
    public void SurfaceDocsTrackCodexFallbackTruthAndTheManifestRouteVerifier()
    {
        string docPath = RepoPaths.FromRoot("docs", "PUBLIC_LANDING_SURFACE.md");
        string runbookPath = RepoPaths.FromRoot("docs", "SELF_HOSTED_DOWNLOADS_RUNBOOK.md");
        string manifestPath = RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_LANDING_MANIFEST.yaml");

        string doc = File.ReadAllText(docPath);
        string manifest = File.ReadAllText(manifestPath);
        string runbook = File.ReadAllText(runbookPath);

        Assert.Contains("/login?next=...", doc, StringComparison.Ordinal);
        Assert.Contains("/auth/google/start?next=%2Fparticipate%2Fcodex", manifest, StringComparison.Ordinal);
        Assert.Contains("/progress", manifest, StringComparison.Ordinal);
        Assert.Contains("/docs", manifest, StringComparison.Ordinal);
        Assert.Contains("/docs/chummer6-quickstart", manifest, StringComparison.Ordinal);
        Assert.Contains("/docs/{slug}/receipts/publication.json", manifest, StringComparison.Ordinal);
        Assert.Contains("/docs/{slug}/download.pdf", manifest, StringComparison.Ordinal);
        Assert.Contains("/docs/embed/{slug}", manifest, StringComparison.Ordinal);
        Assert.Contains("/docs/category/{category}", manifest, StringComparison.Ordinal);
        Assert.Contains("/feedback/operations", manifest, StringComparison.Ordinal);
        Assert.Contains("/feedback/operations/lookup", manifest, StringComparison.Ordinal);
        Assert.Contains("/alice", manifest, StringComparison.Ordinal);
        Assert.Contains("/alice/receipts/build-ghost.json", manifest, StringComparison.Ordinal);
        Assert.Contains("/table-pulse", manifest, StringComparison.Ordinal);
        Assert.Contains("/table-pulse/receipts/live-and-aftermath.json", manifest, StringComparison.Ordinal);
        Assert.Contains("/onramp", manifest, StringComparison.Ordinal);
        Assert.Contains("/onramp/receipts/guided-starter.json", manifest, StringComparison.Ordinal);
        Assert.Contains("/edition-studio", manifest, StringComparison.Ordinal);
        Assert.Contains("/edition-studio/receipts/ruleset-heads.json", manifest, StringComparison.Ordinal);
        Assert.Contains("/quicksilver", manifest, StringComparison.Ordinal);
        Assert.Contains("/quicksilver/receipts/command-network.json", manifest, StringComparison.Ordinal);
        Assert.Contains("/local-co-processor", manifest, StringComparison.Ordinal);
        Assert.Contains("/local-co-processor/receipts/optional-acceleration.json", manifest, StringComparison.Ordinal);
        Assert.Contains("/ledger/factions/{factionId}", manifest, StringComparison.Ordinal);
        Assert.Contains("/ledger/factions/{factionId}/promo", manifest, StringComparison.Ordinal);
        Assert.Contains("/ledger/factions/{factionId}/promo.json", manifest, StringComparison.Ordinal);
        Assert.Contains("/ledger/factions/{factionId}/promo.vtt", manifest, StringComparison.Ordinal);
        Assert.Contains("verification_path: /ledger/factions/ashline-circle/promo.json", manifest, StringComparison.Ordinal);
        Assert.Contains("/contact/submitted/{caseId}", manifest, StringComparison.Ordinal);
        Assert.Contains("/participate/karma-forge/submitted/{submissionId}", manifest, StringComparison.Ordinal);
        Assert.Contains("verification_mode: controller_contract", manifest, StringComparison.Ordinal);
        Assert.Contains("verify_public_routes_from_manifest.py", runbook, StringComparison.Ordinal);
        Assert.Contains(".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml", runbook, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PUBLIC_ROUTE_PROOF.generated.json", runbook, StringComparison.Ordinal);
        Assert.Contains("https://chummer.run", runbook, StringComparison.Ordinal);
        Assert.DoesNotContain("https://chummer6.run", runbook, StringComparison.Ordinal);
        Assert.DoesNotContain("CHUMMER_PUBLIC_ROUTE_PROOF_CHUMMER6_ALIAS.generated.json", runbook, StringComparison.Ordinal);
        Assert.DoesNotContain("stay unpublished", runbook, StringComparison.Ordinal);
    }

    [Fact]
    public void SelectedPublicSurfaceCopyAvoidsProviderAndLtdNames()
    {
        string[] publicFiles =
        {
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Changelog.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Feedback.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "FeedbackOperationsDetail.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_PublicSignalOperationsPacket.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "KarmaForge.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "KarmaForgeSubmitted.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Concierge.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "JoinPrimer.cshtml"),
        };

        string combined = string.Join("\n", publicFiles.Select(static path => File.ReadAllText(path)));

        Assert.DoesNotContain("ProductLift", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("Emailit", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("Blip AI", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("Icanpreneur", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("Lunacal", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("Product Governor", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("OpenAI account in ChatGPT", combined, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicHorizonVideosAreCaptionedAudioBackedAndLinkedFromTheHorizonPage()
    {
        string manifestPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "media", "horizons", "horizon-video-manifest.json");
        string horizonViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Horizons.cshtml");
        string horizonView = File.ReadAllText(horizonViewPath);

        using JsonDocument manifest = JsonDocument.Parse(File.ReadAllText(manifestPath));
        JsonElement root = manifest.RootElement;

        Assert.Equal("chummer.public_horizon_video_manifest", root.GetProperty("contract_name").GetString());
        Assert.True(root.GetProperty("audio_required").GetBoolean());
        Assert.Contains("with_audio", root.GetProperty("publication_posture").GetString() ?? string.Empty, StringComparison.Ordinal);

        int assetCount = 0;
        HashSet<string> horizonIds = new(StringComparer.Ordinal);
        foreach (JsonElement asset in root.GetProperty("assets").EnumerateArray())
        {
            string title = asset.GetProperty("title").GetString() ?? "Untitled horizon video";
            string publicMp4 = asset.GetProperty("public_mp4").GetString() ?? string.Empty;
            string publicCaptions = asset.GetProperty("public_captions").GetString() ?? string.Empty;

            Assert.StartsWith("/media/horizons/", publicMp4, StringComparison.Ordinal);
            Assert.EndsWith(".mp4", publicMp4, StringComparison.Ordinal);
            Assert.StartsWith("/media/horizons/", publicCaptions, StringComparison.Ordinal);
            Assert.EndsWith(".vtt", publicCaptions, StringComparison.Ordinal);
            Assert.True(asset.GetProperty("has_video").GetBoolean(), $"{title} must retain a video stream.");
            Assert.True(asset.GetProperty("has_audio").GetBoolean(), $"{title} must retain an audio stream.");
            Assert.Equal("h264", asset.GetProperty("video_codec").GetString());
            Assert.Equal("aac", asset.GetProperty("audio_codec").GetString());

            string mp4Path = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", publicMp4.TrimStart('/').Replace('/', Path.DirectorySeparatorChar));
            string captionsPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", publicCaptions.TrimStart('/').Replace('/', Path.DirectorySeparatorChar));
            Assert.True(File.Exists(mp4Path), $"Missing published MP4 for {title}: {publicMp4}");
            Assert.True(File.Exists(captionsPath), $"Missing captions for {title}: {publicCaptions}");
            Assert.StartsWith("WEBVTT", File.ReadAllText(captionsPath), StringComparison.Ordinal);
            Assert.Contains(publicMp4, horizonView, StringComparison.Ordinal);
            Assert.Contains(publicCaptions, horizonView, StringComparison.Ordinal);

            horizonIds.Add(asset.GetProperty("horizon_id").GetString() ?? string.Empty);
            assetCount++;
        }

        Assert.Equal(11, assetCount);
        foreach (string expectedHorizon in new[]
        {
            "nexus-pan",
            "alice",
            "karma-forge",
            "jackpoint",
            "runsite",
            "runbook-press",
            "table-pulse",
            "black-ledger",
            "community-hub",
        })
        {
            Assert.Contains(expectedHorizon, horizonIds);
        }
    }

    [Fact]
    public void HorizonRegistryMatchesTheShippedPortfolioForImplementedHorizons()
    {
        string registryPath = RepoPaths.FromRoot(".codex-design", "product", "HORIZON_REGISTRY.yaml");
        string statusMatrixPath = RepoPaths.FromRoot("..", "_completion", "all_horizons_missed_potential", "HORIZON_STATUS_MATRIX.generated.yaml");

        string registry = File.ReadAllText(registryPath);
        string statusMatrix = File.ReadAllText(statusMatrixPath);

        string[] shippedIds =
        {
            "nexus-pan",
            "alice",
            "karma-forge",
            "knowledge-fabric",
            "jackpoint",
            "black-ledger",
            "community-hub",
            "runsite",
            "runbook-press",
            "onramp",
            "edition-studio",
            "run-control",
            "local-co-processor",
            "ghostwire",
            "table-pulse",
            "quicksilver"
        };

        foreach (string shippedId in shippedIds)
        {
            string marker = $"- id: {shippedId}";
            int start = registry.IndexOf(marker, StringComparison.Ordinal);
            Assert.True(start >= 0, $"Missing registry block for {shippedId}.");
            int next = registry.IndexOf("\n- id: ", start + marker.Length, StringComparison.Ordinal);
            string block = next >= 0 ? registry[start..next] : registry[start..];

            Assert.Contains("status: shipped_mvp", block, StringComparison.Ordinal);
            Assert.Contains("current_state: shipped_mvp", block, StringComparison.Ordinal);
            Assert.Contains($"{shippedId.Replace('-', '_')}", statusMatrix.Replace('-', '_'), StringComparison.OrdinalIgnoreCase);
        }

        Assert.DoesNotContain("Public copy may describe JACKPOINT as a bounded horizon and preview lane only", registry, StringComparison.Ordinal);
        Assert.DoesNotContain("Public copy may show runsite as a preview artifact lane only", registry, StringComparison.Ordinal);
        Assert.DoesNotContain("Public copy may describe Community Hub as a bounded horizon and curated preview only", registry, StringComparison.Ordinal);
        Assert.DoesNotContain("Public copy may describe Ghostwire as a receipt-backed replay and forensics horizon only", registry, StringComparison.Ordinal);
        Assert.DoesNotContain("Public copy may describe Table Pulse as a bounded GM-governed live heat and private aftermath horizon only", registry, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicGuideShippedHorizonsDoNotPresentAsFutureConcepts()
    {
        string[] shippedGuideFiles =
        {
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "public-guide", "HORIZONS", "jackpoint.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "public-guide", "HORIZONS", "runsite.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "public-guide", "HORIZONS", "runbook-press.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "public-guide", "HORIZONS", "table-pulse.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "public-guide", "HORIZONS", "community-hub.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "public-guide", "HORIZONS", "onramp.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "public-guide", "HORIZONS", "edition-studio.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "public-guide", "HORIZONS", "run-control.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "public-guide", "HORIZONS", "local-co-processor.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "public-guide", "HORIZONS", "quicksilver.md"),
        };

        string combined = string.Join("\n", shippedGuideFiles.Select(File.ReadAllText));

        Assert.DoesNotContain("Today: Future concept.", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("Next: Research and prototypes.", combined, StringComparison.Ordinal);
    }

    [Fact]
    public void CanonicalShippedHorizonDocsDoNotPresentAsNotReady()
    {
        string[] shippedHorizonDocs =
        {
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "horizons", "nexus-pan.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "horizons", "knowledge-fabric.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "horizons", "runbook-press.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "horizons", "table-pulse.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "horizons", "onramp.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "horizons", "edition-studio.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "horizons", "run-control.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "horizons", "local-co-processor.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "horizons", "jackpoint.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "horizons", "runsite.md"),
            RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "horizons", "quicksilver.md"),
        };

        string combined = string.Join("\n", shippedHorizonDocs.Select(File.ReadAllText));

        Assert.DoesNotContain("## Why it is not ready yet", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("is still a horizon", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("remains a horizon rather than a product promise", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("signed-in command lane is live", combined, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicFeatureRegistryMarksImplementedHorizonsAsShipped()
    {
        string registryPath = RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "PUBLIC_FEATURE_REGISTRY.yaml");
        string registry = File.ReadAllText(registryPath);
        (string id, string href, string badge)[] shippedCards =
        {
            ("lane_creator", "/creator", "Shipped MVP"),
            ("real_mobile_projection", "/mobile", "Live now"),
            ("horizon_nexus_pan", "/play/continuity", "Shipped MVP"),
            ("horizon_knowledge_fabric", "/rules", "Shipped MVP"),
            ("horizon_karma_forge", "/participate/karma-forge", "Shipped MVP"),
            ("horizon_onramp", "/onramp", "Shipped MVP"),
            ("horizon_edition_studio", "/edition-studio", "Shipped MVP"),
            ("horizon_run_control", "/run-control", "Shipped MVP"),
            ("horizon_local_co_processor", "/local-co-processor", "Shipped MVP"),
            ("horizon_runbook_press", "/runbook", "Shipped MVP"),
            ("horizon_quicksilver", "/quicksilver", "Shipped MVP"),
        };

        foreach ((string id, string href, string badge) in shippedCards)
        {
            string marker = $"- id: {id}";
            int start = registry.IndexOf(marker, StringComparison.Ordinal);
            Assert.True(start >= 0, $"Missing public feature card for {id}.");
            int next = registry.IndexOf("\n  - id: ", start + marker.Length, StringComparison.Ordinal);
            string block = next >= 0 ? registry[start..next] : registry[start..];

            Assert.Contains($"href: {href}", block, StringComparison.Ordinal);
            Assert.Contains($"badge: {badge}", block, StringComparison.Ordinal);
            Assert.DoesNotContain("badge: Preparing", block, StringComparison.Ordinal);
            Assert.DoesNotContain("badge: Research", block, StringComparison.Ordinal);
            Assert.DoesNotContain("badge: Preview lane", block, StringComparison.Ordinal);
        }

        int blackLedgerStart = registry.IndexOf("- id: horizon_black_ledger", StringComparison.Ordinal);
        Assert.True(blackLedgerStart >= 0, "Missing public feature card for horizon_black_ledger.");
        int blackLedgerNext = registry.IndexOf("\n  - id: ", blackLedgerStart + "- id: horizon_black_ledger".Length, StringComparison.Ordinal);
        string blackLedgerBlock = blackLedgerNext >= 0 ? registry[blackLedgerStart..blackLedgerNext] : registry[blackLedgerStart..];
        Assert.Contains("href: /ledger", blackLedgerBlock, StringComparison.Ordinal);
        Assert.Contains("badge: Lab preview", blackLedgerBlock, StringComparison.Ordinal);
    }
}
