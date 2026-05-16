using System;
using System.Collections.Generic;
using System.IO;
using Chummer.Run.Api.Services.Community;
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

        Assert.Contains("[HttpGet(\"/account/ledger\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/ledger/onboarding\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/account/ledger/onboarding/join\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/api/v1/account/ledger/allegiance\")]", ledgerController, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/api/v1/account/ledger/allegiance/join\")]", ledgerController, StringComparison.Ordinal);
        Assert.Contains("Choose your flag.", onboardingView, StringComparison.Ordinal);
        Assert.Contains("Join this faction", onboardingView, StringComparison.Ordinal);
        Assert.Contains("Found Major Faction", onboardingView, StringComparison.Ordinal);
        Assert.Contains("Found Challenger", onboardingView, StringComparison.Ordinal);
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
        return new BlackLedgerFactionOnboardingService(config, new BlackLedgerPublicStatsService(), campaignSpine);
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

        var detail = service.GetFactionDetail(charter.FactionId);
        Assert.NotNull(detail?.OperationalState);
        Assert.Equal(2, detail!.OperationalState!.ActionPointsSpent);
        Assert.Contains("ashline_circle", detail.OperationalState.RivalsChallenged, StringComparer.OrdinalIgnoreCase);
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
}
