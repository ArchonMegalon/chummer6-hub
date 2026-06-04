using System;
using System.Collections.Generic;
using System.IO;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class BlackLedgerFactionAllegianceTests
{
    [Fact]
    public void BlackLedgerFactionAllegiance_routes_and_onboarding_wizard_exist()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string ledgerController = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "LedgerController.cs"));
        string onboardingView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "LedgerOnboarding.cshtml"));
        string promoView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "LedgerFactionPromo.cshtml"));

        Assert.Contains("[HttpGet(\"/account/ledger\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/ledger/notifications\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/ledger/worldtick/validation\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/ledger/onboarding\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ledger/factions/{factionId}/promo\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/ledger/factions/{factionId}/leader-briefing\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/account/ledger/onboarding/join\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/api/v1/account/ledger/allegiance\")]", ledgerController, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/api/v1/account/ledger/allegiance/join\")]", ledgerController, StringComparison.Ordinal);
        Assert.Contains("Choose a faction", onboardingView, StringComparison.Ordinal);
        Assert.Contains("Join this faction", onboardingView, StringComparison.Ordinal);
        Assert.Contains("Open faction video", onboardingView, StringComparison.Ordinal);
        Assert.Contains("Found Major Faction", onboardingView, StringComparison.Ordinal);
        Assert.Contains("Found Challenger", onboardingView, StringComparison.Ordinal);
        Assert.Contains("Open watch page", promoView, StringComparison.Ordinal);
        Assert.Contains("First-party motion bulletin", promoView, StringComparison.Ordinal);
        Assert.Contains("<video", promoView, StringComparison.Ordinal);
        Assert.Contains("data-storyboard-player", promoView, StringComparison.Ordinal);
    }

    [Fact]
    public void BlackLedgerFactionAllegiance_join_receipt_applies_to_all_runners()
    {
        var service = CreateService();
        var user = new Chummer.Run.Contracts.Community.HubUserDto(
            "usr_demo",
            "subject.demo",
            "Demo Runner",
            "demo",
            "private",
            "UTC",
            "",
            new[] { "subject.demo" },
            Array.Empty<string>(),
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow);

        BlackLedgerFactionJoinReceiptDto receipt = service.JoinFaction(user, "ashline-circle");
        BlackLedgerAccountFactionAllegianceDto? allegiance = service.GetAllegiance(user);

        Assert.True(receipt.AppliesToAllRunners);
        Assert.True(receipt.FutureRunnersInherit);
        Assert.NotNull(allegiance);
        Assert.True(allegiance!.AppliesToAllCurrentRunners);
        Assert.True(allegiance.AppliesToAllFutureRunners);
    }

    [Fact]
    public void BlackLedgerFactionAllegiance_enforces_defection_cooldown()
    {
        var service = CreateService();
        var user = new Chummer.Run.Contracts.Community.HubUserDto(
            "usr_cooldown",
            "subject.cooldown",
            "Cooldown Runner",
            "cooldown",
            "private",
            "UTC",
            "",
            new[] { "subject.cooldown" },
            Array.Empty<string>(),
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow);

        service.JoinFaction(user, "ashline-circle");
        var ex = Assert.Throws<InvalidOperationException>(() => service.JoinFaction(user, "glass-tower-compact"));
        Assert.Contains("cooldown", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    internal static BlackLedgerFactionOnboardingService CreateService()
    {
        string root = Path.Combine(Path.GetTempPath(), $"bl-faction-tests-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        string path = Path.Combine(root, "black-ledger-factions.json");
        IConfiguration config = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_FACTION_STORAGE"] = path,
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(root, "community-store.json")
            })
            .Build();
        CommunityStore store = new(config, NullLogger<CommunityStore>.Instance);
        WorkspaceLifecyclePolicyService lifecycle = new(config);
        CampaignArtifactRegistryBridge artifactBridge = new(store);
        CampaignSpineService campaignSpine = new(store, lifecycle, artifactBridge);
        return new BlackLedgerFactionOnboardingService(config, new BlackLedgerPublicStatsService(), campaignSpine, store);
    }
}

public sealed class FactionCharterBuilderTests
{
    [Fact]
    public void FactionCharterBuilder_routes_and_challenger_warning_exist()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string ledgerController = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "LedgerController.cs"));
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "LedgerFactionCreate.cshtml"));

        Assert.Contains("[HttpGet(\"/account/ledger/factions/create\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/account/ledger/factions/create\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/api/v1/account/ledger/factions\")]", ledgerController, StringComparison.Ordinal);
        Assert.Contains("Found a Challenger Faction", view, StringComparison.Ordinal);
        Assert.Contains("starts weaker", view, StringComparison.Ordinal);
    }

    [Fact]
    public void FactionCharterBuilder_creates_challenger_with_required_flaws_and_lower_budget()
    {
        var service = BlackLedgerFactionAllegianceTests.CreateService();
        var user = new Chummer.Run.Contracts.Community.HubUserDto(
            "usr_builder",
            "subject.builder",
            "Builder",
            "builder",
            "private",
            "UTC",
            "",
            new[] { "subject.builder" },
            Array.Empty<string>(),
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow);

        var charter = service.CreateFaction(user, new BlackLedgerCreateFactionRequest(
            "Undertow Signal Cell",
            "challenger",
            "matrix_cell",
            new[] { "underdog_momentum", "dispatch_desk" },
            new[] { "overexposed", "thin_resources", "rival_target" },
            null,
            "ashline_circle",
            true));

        Assert.Equal("challenger", charter.CharterType);
        Assert.Equal(65, charter.CharterPointsTotal);
        Assert.True(charter.Flaws.Count >= 3);
        Assert.Contains("Underdog Momentum", charter.Perks, StringComparer.Ordinal);
    }

    [Fact]
    public void FactionCharterBuilder_requires_challenger_warning_acknowledgement()
    {
        var service = BlackLedgerFactionAllegianceTests.CreateService();
        var user = new Chummer.Run.Contracts.Community.HubUserDto(
            "usr_warning",
            "subject.warning",
            "Warning",
            "warning",
            "private",
            "UTC",
            "",
            new[] { "subject.warning" },
            Array.Empty<string>(),
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow);

        var ex = Assert.Throws<InvalidOperationException>(() => service.CreateFaction(user, new BlackLedgerCreateFactionRequest(
            "Quiet Undertow",
            "challenger",
            "matrix_cell",
            new[] { "underdog_momentum", "dispatch_desk" },
            new[] { "overexposed", "thin_resources", "rival_target" },
            null,
            "ashline_circle",
            false)));

        Assert.Contains("warning", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void FactionCharterBuilder_rejects_unsafe_public_names()
    {
        var service = BlackLedgerFactionAllegianceTests.CreateService();
        var user = new Chummer.Run.Contracts.Community.HubUserDto(
            "usr_name",
            "subject.name",
            "Name",
            "name",
            "private",
            "UTC",
            "",
            new[] { "subject.name" },
            Array.Empty<string>(),
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow);

        var ex = Assert.Throws<InvalidOperationException>(() => service.CreateFaction(user, new BlackLedgerCreateFactionRequest(
            "Ares Mirror Cell",
            "major",
            "creator_press",
            new[] { "dispatch_desk", "public_trust" },
            new[] { "overexposed", "thin_resources" },
            "emerald-core",
            null,
            false)));

        Assert.Contains("public-safety moderation", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void FactionCharterBuilder_rejects_challenger_only_perk_on_major()
    {
        var service = BlackLedgerFactionAllegianceTests.CreateService();
        var user = new Chummer.Run.Contracts.Community.HubUserDto(
            "usr_major",
            "subject.major",
            "Major",
            "major",
            "private",
            "UTC",
            "",
            new[] { "subject.major" },
            Array.Empty<string>(),
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow);

        var ex = Assert.Throws<InvalidOperationException>(() => service.CreateFaction(user, new BlackLedgerCreateFactionRequest(
            "Harbor Signal Board",
            "major",
            "creator_press",
            new[] { "dispatch_desk", "underdog_momentum" },
            new[] { "overexposed", "thin_resources" },
            "emerald-core",
            null,
            false)));

        Assert.Contains("Challenger-only", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void FactionActionReducer_enforces_action_points_and_persists_receipts()
    {
        var service = BlackLedgerFactionAllegianceTests.CreateService();
        var user = new Chummer.Run.Contracts.Community.HubUserDto(
            "usr_actions",
            "subject.actions",
            "Actions",
            "actions",
            "private",
            "UTC",
            "",
            new[] { "subject.actions" },
            Array.Empty<string>(),
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow);

        var charter = service.CreateFaction(user, new BlackLedgerCreateFactionRequest(
            "Undertow Relay Cell",
            "challenger",
            "matrix_cell",
            new[] { "underdog_momentum", "dispatch_desk" },
            new[] { "overexposed", "thin_resources", "rival_target" },
            null,
            "ashline_circle",
            true));

        BlackLedgerFactionActionReceiptDto first = service.ExecuteAction(user, charter.FactionId, new BlackLedgerFactionActionRequest("challenge-faction", "emerald-core", "ashline_circle", "pressure"));
        Assert.Equal(0, first.RemainingActionPoints);
        Assert.Contains(first.Effects, effect => effect.Contains("ap 0/2", StringComparison.OrdinalIgnoreCase));

        var ex = Assert.Throws<InvalidOperationException>(() => service.ExecuteAction(user, charter.FactionId, new BlackLedgerFactionActionRequest("recruit", "emerald-core", null, "trust")));
        Assert.Contains("action points are exhausted", ex.Message, StringComparison.OrdinalIgnoreCase);

        var detail = service.GetWorkspaceFactionDetail(charter.FactionId);
        Assert.NotNull(detail?.OperationalState);
        Assert.Equal(2, detail!.OperationalState!.ActionPointsSpent);
        Assert.Contains("ashline_circle", detail.OperationalState.RivalsChallenged, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void FactionRunnerInheritance_zero_runners_stay_zero()
    {
        var service = BlackLedgerFactionAllegianceTests.CreateService();
        var user = new Chummer.Run.Contracts.Community.HubUserDto(
            "usr_zero",
            "subject.zero",
            "Zero",
            "zero",
            "private",
            "UTC",
            "",
            new[] { "subject.zero" },
            Array.Empty<string>(),
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow);

        var receipt = service.JoinFaction(user, "ashline-circle");
        Assert.Equal(0, receipt.RunnerCount);
        Assert.Empty(service.GetAllegiance(user)!.CurrentRunnerIdsSnapshot);
    }

    [Fact]
    public void FactionStorage_persists_to_community_store()
    {
        string root = Path.Combine(Path.GetTempPath(), $"bl-faction-storage-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        IConfiguration config = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(root, "community-store.json")
            })
            .Build();
        CommunityStore store = new(config, NullLogger<CommunityStore>.Instance);
        WorkspaceLifecyclePolicyService lifecycle = new(config);
        CampaignArtifactRegistryBridge artifactBridge = new(store);
        CampaignSpineService campaignSpine = new(store, lifecycle, artifactBridge);
        var service = new BlackLedgerFactionOnboardingService(config, new BlackLedgerPublicStatsService(), campaignSpine, store);
        var user = new Chummer.Run.Contracts.Community.HubUserDto(
            "usr_store",
            "subject.store",
            "Store",
            "store",
            "private",
            "UTC",
            "",
            new[] { "subject.store" },
            Array.Empty<string>(),
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow);

        service.CreateFaction(user, new BlackLedgerCreateFactionRequest(
            "Signal Storage Board",
            "major",
            "creator_press",
            new[] { "dispatch_desk", "public_trust" },
            new[] { "overexposed", "thin_resources" },
            "emerald-core",
            null,
            false));

        CommunityStore restoredStore = new(config, NullLogger<CommunityStore>.Instance);
        CampaignSpineService restoredSpine = new(restoredStore, lifecycle, new CampaignArtifactRegistryBridge(restoredStore));
        var restoredService = new BlackLedgerFactionOnboardingService(config, new BlackLedgerPublicStatsService(), restoredSpine, restoredStore);
        var allegiance = restoredService.GetAllegiance(user);

        Assert.NotNull(restoredStore.BlackLedgerFactionOnboardingState);
        Assert.NotNull(allegiance);
        Assert.Equal("signal_storage_board", allegiance!.ActiveFactionId);
    }

    [Fact]
    public void FactionModerationLifecycle_blocks_public_projection_until_safe()
    {
        var service = BlackLedgerFactionAllegianceTests.CreateService();
        var user = new Chummer.Run.Contracts.Community.HubUserDto(
            "usr_mod",
            "subject.mod",
            "Moderation",
            "moderation",
            "private",
            "UTC",
            "",
            new[] { "subject.mod" },
            Array.Empty<string>(),
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow);

        var charter = service.CreateFaction(user, new BlackLedgerCreateFactionRequest(
            "Review Gate Board",
            "major",
            "creator_press",
            new[] { "dispatch_desk", "public_trust" },
            new[] { "overexposed", "thin_resources" },
            "emerald-core",
            null,
            false));

        Assert.Equal("pending_review", charter.Status);
        Assert.DoesNotContain(service.ListFactionSummaries(), item => string.Equals(item.FactionId, charter.FactionId, StringComparison.OrdinalIgnoreCase));
        Assert.Null(service.GetFactionDetail(charter.FactionId));
        Assert.NotNull(service.GetWorkspaceFactionDetail(charter.FactionId));
    }

    [Fact]
    public void FactionModerationLifecycle_can_approve_and_suppress_public_projection()
    {
        var service = BlackLedgerFactionAllegianceTests.CreateService();
        var user = new Chummer.Run.Contracts.Community.HubUserDto(
            "usr_mod2",
            "subject.mod2",
            "Moderation Two",
            "moderation2",
            "private",
            "UTC",
            "",
            new[] { "subject.mod2" },
            Array.Empty<string>(),
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow);

        var charter = service.CreateFaction(user, new BlackLedgerCreateFactionRequest(
            "Projection Gate Board",
            "major",
            "creator_press",
            new[] { "dispatch_desk", "public_trust" },
            new[] { "overexposed", "thin_resources" },
            "emerald-core",
            null,
            false));

        var approved = service.ApproveFactionForPublicProjection(user, charter.FactionId);
        Assert.Equal("approved", approved.Outcome);
        Assert.True(approved.PublicProjectionAllowed);
        Assert.NotNull(service.GetFactionDetail(charter.FactionId));
        Assert.Contains(service.ListFactionSummaries(), item => string.Equals(item.FactionId, charter.FactionId, StringComparison.OrdinalIgnoreCase));

        var suppressed = service.SuppressFactionPublicProjection(user, charter.FactionId, "needs another pass");
        Assert.Equal("suppressed", suppressed.Outcome);
        Assert.False(suppressed.PublicProjectionAllowed);
        Assert.Null(service.GetFactionDetail(charter.FactionId));
        Assert.DoesNotContain(service.ListFactionSummaries(), item => string.Equals(item.FactionId, charter.FactionId, StringComparison.OrdinalIgnoreCase));
        Assert.NotNull(service.GetWorkspaceFactionDetail(charter.FactionId));
    }

    [Fact]
    public void PrivateLoreOverlay_persists_without_public_projection()
    {
        var service = BlackLedgerFactionAllegianceTests.CreateService();
        var user = new Chummer.Run.Contracts.Community.HubUserDto(
            "usr_overlay",
            "subject.overlay",
            "Overlay",
            "overlay",
            "private",
            "UTC",
            "",
            new[] { "subject.overlay" },
            Array.Empty<string>(),
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow);

        var charter = service.CreateFaction(user, new BlackLedgerCreateFactionRequest(
            "Relay Choir",
            "major",
            "creator_press",
            new[] { "dispatch_desk", "public_trust" },
            new[] { "overexposed", "thin_resources" },
            "emerald-core",
            null,
            false));

        var overlay = service.UpsertPrivateLoreOverlay(user, "cmp_demo", new PrivateLoreOverlayRequest(
            "emerald-sprawl-prelude",
            charter.FactionId,
            new Dictionary<string, string>
            {
                ["safehouse_alpha"] = "Choir Annex",
                ["district_beta"] = "Glassline"
            },
            new[] { "Private lore stays non-projecting." }));

        Assert.False(overlay.PublicProjectionAllowed);
        Assert.Equal("cmp_demo", overlay.CampaignId);
        Assert.Equal("Choir Annex", overlay.LabelMap["safehouse_alpha"]);

        var restored = service.GetPrivateLoreOverlay("cmp_demo", charter.FactionId);
        Assert.NotNull(restored);
        Assert.Equal("Glassline", restored!.LabelMap["district_beta"]);
    }

    [Fact]
    public void FactionPromoArtifact_prefers_magicfit_receipt_backed_cinematic_package()
    {
        var service = BlackLedgerFactionAllegianceTests.CreateService();

        BlackLedgerFactionPromoArtifactViewModel? promo = service.GetPromoArtifact("ashline-circle");

        Assert.NotNull(promo);
        Assert.Equal("VERIFIED_PROVIDER", promo!.ProviderStatus);
        Assert.Equal("magicfit_cinematic_faction_promo_with_narration", promo.RenderMode);
        Assert.Equal("first_party_storyboard", promo.FallbackRenderMode);
        Assert.Contains("/ledger/factions/ashline-circle/promo", promo.HtmlHref, StringComparison.Ordinal);
        Assert.Equal("Scene-driven faction mobilization bulletin", promo.StaticCardLabel);
        Assert.Equal("Playable MagicFit-rendered faction reel", promo.PlaybackLabel);
        Assert.Contains(".mp4", promo.VideoMp4Href, StringComparison.Ordinal);
        Assert.Contains(".webm", promo.VideoWebmHref, StringComparison.Ordinal);
        Assert.Contains("MagicFit-rendered 16:9 MP4", promo.FormatLabels, StringComparer.Ordinal);
        Assert.Contains("Captions required", promo.FormatLabels, StringComparer.Ordinal);
        Assert.Contains("world tick", promo.AudiencePromise, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("/account/ledger/factions/ashline-circle/leader-briefing", promo.ValidationHref, StringComparison.Ordinal);
        Assert.Equal(3, promo.StoryboardShots.Count);
        Assert.Equal(3, promo.StoryboardFrames.Count);
        Assert.Equal("Anchor Open", promo.StoryboardFrames[0].Label);
        Assert.Contains("pressure", promo.StoryboardFrames[0].VisualHook, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("world tick", promo.StoryboardFrames[0].ProofPayoff, StringComparison.OrdinalIgnoreCase);
        Assert.NotEmpty(promo.ScreenplayScenes);
        Assert.Contains(promo.ScreenplayScenes, scene => scene.Label.Contains("Turn 1", StringComparison.OrdinalIgnoreCase)
            || scene.Label.Contains("scene", StringComparison.OrdinalIgnoreCase)
            || scene.NarratorLine.Contains("keep the faction problem visible", StringComparison.OrdinalIgnoreCase));
    }
}
