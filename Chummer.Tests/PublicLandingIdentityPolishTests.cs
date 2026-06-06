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
}
