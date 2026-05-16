using System;
using System.Collections.Generic;
using System.IO;
using Chummer.Run.Api.Services.Community;
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

    internal static BlackLedgerFactionOnboardingService CreateService()
    {
        string path = Path.Combine(Path.GetTempPath(), $"bl-faction-tests-{Guid.NewGuid():N}.json");
        IConfiguration config = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_FACTION_STORAGE"] = path
            })
            .Build();
        return new BlackLedgerFactionOnboardingService(config, new BlackLedgerPublicStatsService());
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
            "ashline_circle"));

        Assert.Equal("challenger", charter.CharterType);
        Assert.Equal(65, charter.CharterPointsTotal);
        Assert.True(charter.Flaws.Count >= 3);
        Assert.Contains("Underdog Momentum", charter.Perks, StringComparer.Ordinal);
    }
}
