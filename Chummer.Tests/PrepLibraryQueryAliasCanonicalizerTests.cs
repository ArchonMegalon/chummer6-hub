using Chummer.Run.Contracts.Search;
using Xunit;

namespace Chummer.Tests;

public sealed class PrepLibraryQueryAliasCanonicalizerTests
{
    [Fact]
    public void RewriteAliases_CollapsesOffLineAndSafeHouseTravelContinuityShorthand()
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase)
        {
            "off",
            "line",
            "safe",
            "house",
            "readiness",
            "cache"
        };

        PrepLibraryQueryAliasCanonicalizer.RewriteAliases(tokens);

        Assert.Contains("offline", tokens);
        Assert.Contains("safehouse", tokens);
        Assert.DoesNotContain("off", tokens);
        Assert.DoesNotContain("line", tokens);
        Assert.DoesNotContain("safe", tokens);
        Assert.DoesNotContain("house", tokens);
        Assert.DoesNotContain("readiness", tokens);
        Assert.DoesNotContain("cache", tokens);
    }

    [Fact]
    public void RewriteAliases_CollapsesMobileSafeHouseAndOffLineContinuityShorthand()
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase)
        {
            "mobile",
            "off",
            "line",
            "safe",
            "house",
            "cache"
        };

        PrepLibraryQueryAliasCanonicalizer.RewriteAliases(tokens);

        Assert.DoesNotContain("mobile", tokens);
        Assert.Contains("offline", tokens);
        Assert.Contains("safehouse", tokens);
        Assert.DoesNotContain("off", tokens);
        Assert.DoesNotContain("line", tokens);
        Assert.DoesNotContain("safe", tokens);
        Assert.DoesNotContain("house", tokens);
        Assert.DoesNotContain("cache", tokens);
    }

    [Fact]
    public void RewriteAliases_CollapsesPluralTravelOfflineSafehouseAndMobileCompactForms()
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase)
        {
            "safehouses",
            "travels",
            "offlines",
            "mobileofflines",
            "mobiletravelcaches",
            "mobilesafehousereadinesses"
        };

        PrepLibraryQueryAliasCanonicalizer.RewriteAliases(tokens);

        Assert.Contains("safehouse", tokens);
        Assert.Contains("travel", tokens);
        Assert.Contains("offline", tokens);
        Assert.DoesNotContain("safehouses", tokens);
        Assert.DoesNotContain("travels", tokens);
        Assert.DoesNotContain("offlines", tokens);
        Assert.DoesNotContain("mobileofflines", tokens);
        Assert.DoesNotContain("mobiletravelcaches", tokens);
        Assert.DoesNotContain("mobilesafehousereadinesses", tokens);
        Assert.DoesNotContain("mobile", tokens);
        Assert.DoesNotContain("cache", tokens);
        Assert.DoesNotContain("readiness", tokens);
    }

    [Fact]
    public void RewriteAliases_CollapsesPluralConnectionAndRelationshipMutationCompactForms()
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase)
        {
            "connectionsupdate",
            "connectionschange",
            "relationshipsupdate",
            "relationshipschange"
        };

        PrepLibraryQueryAliasCanonicalizer.RewriteAliases(tokens);

        Assert.Contains("connection", tokens);
        Assert.Contains("relationship", tokens);
        Assert.DoesNotContain("connectionsupdate", tokens);
        Assert.DoesNotContain("connectionschange", tokens);
        Assert.DoesNotContain("relationshipsupdate", tokens);
        Assert.DoesNotContain("relationshipschange", tokens);
    }

    [Fact]
    public void RewriteAliases_CollapsesMobileCompanionFormsIntoTravelOfflineSafehouseContinuityTokens()
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase)
        {
            "campaignmobilecompanions"
        };

        PrepLibraryQueryAliasCanonicalizer.RewriteAliases(tokens);

        Assert.Contains("campaign", tokens);
        Assert.Contains("offline", tokens);
        Assert.Contains("travel", tokens);
        Assert.Contains("safehouse", tokens);
        Assert.DoesNotContain("campaignmobilecompanions", tokens);
        Assert.DoesNotContain("mobile", tokens);
        Assert.DoesNotContain("companion", tokens);
        Assert.DoesNotContain("companions", tokens);
    }

    [Fact]
    public void RewriteAliases_CollapsesCompactMobileCompanionReturnLoopFormsIntoContinuityTokens()
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase)
        {
            "campaignmobilecompanionreturnloops"
        };

        PrepLibraryQueryAliasCanonicalizer.RewriteAliases(tokens);

        Assert.Contains("campaign", tokens);
        Assert.Contains("offline", tokens);
        Assert.Contains("travel", tokens);
        Assert.Contains("safehouse", tokens);
        Assert.Contains("return", tokens);
        Assert.Contains("loop", tokens);
        Assert.DoesNotContain("campaignmobilecompanionreturnloops", tokens);
        Assert.DoesNotContain("mobile", tokens);
        Assert.DoesNotContain("companion", tokens);
        Assert.DoesNotContain("companions", tokens);
        Assert.DoesNotContain("loops", tokens);
    }

    [Fact]
    public void RewriteAliases_CollapsesCompactGovernedPacketFormsIntoPrepOpsTokens()
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase)
        {
            "preplibrarypacket",
            "oppositionpackets",
            "rostermovementpacket",
            "eventcontrolpackets"
        };

        PrepLibraryQueryAliasCanonicalizer.RewriteAliases(tokens);

        Assert.Contains("prep", tokens);
        Assert.Contains("library", tokens);
        Assert.Contains("opposition", tokens);
        Assert.Contains("roster", tokens);
        Assert.Contains("move", tokens);
        Assert.Contains("eventcontrol", tokens);
        Assert.Contains("packet", tokens);
        Assert.DoesNotContain("preplibrarypacket", tokens);
        Assert.DoesNotContain("oppositionpackets", tokens);
        Assert.DoesNotContain("rostermovementpacket", tokens);
        Assert.DoesNotContain("eventcontrolpackets", tokens);
    }
}
