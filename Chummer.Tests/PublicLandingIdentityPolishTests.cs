using System.IO;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingIdentityPolishTests
{
    [Fact]
    public void PublicLanding_connected_lane_copy_is_replaced_with_product_surface_identities()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));

        Assert.DoesNotContain(" connected lane", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("First-party package receipt", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("Normalized packet receipt", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("Authenticated faction workspace", controller, StringComparison.Ordinal);

        Assert.Contains("Community Hub operations rail", controller, StringComparison.Ordinal);
        Assert.Contains("Creator OS publication rail", controller, StringComparison.Ordinal);
        Assert.Contains("Quicksilver command rail", controller, StringComparison.Ordinal);
        Assert.Contains("JACKPOINT briefing rail", controller, StringComparison.Ordinal);
        Assert.Contains("RUNSITE prep rail", controller, StringComparison.Ordinal);
        Assert.Contains("RUN CONTROL operations rail", controller, StringComparison.Ordinal);
        Assert.Contains("ONRAMP starter rail", controller, StringComparison.Ordinal);
        Assert.Contains("EDITION STUDIO edition rail", controller, StringComparison.Ordinal);
        Assert.Contains("LOCAL CO-PROCESSOR profile rail", controller, StringComparison.Ordinal);
        Assert.Contains("Runner Passport continuity rail", controller, StringComparison.Ordinal);
        Assert.Contains("Signal Deck command rail", controller, StringComparison.Ordinal);
        Assert.Contains("Living World continuity rail", controller, StringComparison.Ordinal);
        Assert.Contains("Package route receipt", controller, StringComparison.Ordinal);
        Assert.Contains("KARMA FORGE intake receipt", controller, StringComparison.Ordinal);
        Assert.Contains("Faction command workspace", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicLanding_product_surfaces_lead_with_product_names_in_titles_and_headings()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));

        Assert.Contains("title: \"ALICE\"", controller, StringComparison.Ordinal);
        Assert.Contains("heading: \"ALICE\"", controller, StringComparison.Ordinal);
        Assert.Contains("title: \"TABLE PULSE\"", controller, StringComparison.Ordinal);
        Assert.Contains("heading: \"TABLE PULSE\"", controller, StringComparison.Ordinal);
        Assert.Contains("title: \"JACKPOINT\"", controller, StringComparison.Ordinal);
        Assert.Contains("heading: \"JACKPOINT\"", controller, StringComparison.Ordinal);
        Assert.Contains("title: \"RUNSITE\"", controller, StringComparison.Ordinal);
        Assert.Contains("heading: \"RUNSITE\"", controller, StringComparison.Ordinal);
        Assert.Contains("title: \"GHOSTWIRE\"", controller, StringComparison.Ordinal);
        Assert.Contains("heading: \"GHOSTWIRE\"", controller, StringComparison.Ordinal);

        Assert.DoesNotContain("ALICE keeps compare, tradeoffs, and apply truth on first-party rails.", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("TABLE PULSE separates live heat from private aftermath.", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("title: \"JACKPOINT briefings\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("heading: \"JACKPOINT briefings\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("title: \"RUNSITE packets\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("heading: \"RUNSITE packets\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("title: \"GHOSTWIRE after-action\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("heading: \"GHOSTWIRE after-action\"", controller, StringComparison.Ordinal);

        Assert.Contains("Heading: \"Faction command rail\"", controller, StringComparison.Ordinal);
        Assert.Contains("Heading: \"Black Ledger inbox\"", controller, StringComparison.Ordinal);
        Assert.Contains("Heading: \"Table Pulse Live\"", controller, StringComparison.Ordinal);
        Assert.Contains("Heading: \"World-turn validation\"", controller, StringComparison.Ordinal);
    }
}
