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
            "oppositionpacket",
            "oppositionpackets",
            "rostermovementpacket",
            "eventcontrolpacket",
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
        Assert.DoesNotContain("oppositionpacket", tokens);
        Assert.DoesNotContain("oppositionpackets", tokens);
        Assert.DoesNotContain("rostermovementpacket", tokens);
        Assert.DoesNotContain("eventcontrolpacket", tokens);
        Assert.DoesNotContain("eventcontrolpackets", tokens);
    }

    [Fact]
    public void RewriteAliases_CollapsesCompactContinuityAndGmPacketFormsIntoUnifiedWorkspaceTokens()
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase)
        {
            "campaignreturnpacket",
            "campaignreturnbriefs",
            "aftermathreturnpacket",
            "aftermathreturnbrief",
            "downtimereturnpackets",
            "downtimereturnbriefs",
            "diarycontactheatpacket",
            "diarycontactsheatpackets",
            "aftermathdowntimepacket",
            "travelofflinepacket",
            "travelofflinepackets",
            "mobileofflinepacket",
            "mobileofflinepackets",
            "safehousetravelpacket",
            "safehousetravelpackets",
            "gmopspacket",
            "gmoperationpackets",
            "gmcontrolpacket"
        };

        PrepLibraryQueryAliasCanonicalizer.RewriteAliases(tokens);

        Assert.Contains("campaign", tokens);
        Assert.Contains("return", tokens);
        Assert.Contains("aftermath", tokens);
        Assert.Contains("downtime", tokens);
        Assert.Contains("diary", tokens);
        Assert.Contains("connection", tokens);
        Assert.Contains("heat", tokens);
        Assert.Contains("travel", tokens);
        Assert.Contains("offline", tokens);
        Assert.Contains("safehouse", tokens);
        Assert.Contains("eventcontrol", tokens);
        Assert.Contains("season", tokens);
        Assert.Contains("operation", tokens);
        Assert.Contains("packet", tokens);
        Assert.DoesNotContain("campaignreturnpacket", tokens);
        Assert.DoesNotContain("campaignreturnbriefs", tokens);
        Assert.DoesNotContain("aftermathreturnpacket", tokens);
        Assert.DoesNotContain("aftermathreturnbrief", tokens);
        Assert.DoesNotContain("downtimereturnpackets", tokens);
        Assert.DoesNotContain("downtimereturnbriefs", tokens);
        Assert.DoesNotContain("diarycontactheatpacket", tokens);
        Assert.DoesNotContain("diarycontactsheatpackets", tokens);
        Assert.DoesNotContain("aftermathdowntimepacket", tokens);
        Assert.DoesNotContain("travelofflinepacket", tokens);
        Assert.DoesNotContain("travelofflinepackets", tokens);
        Assert.DoesNotContain("mobileofflinepacket", tokens);
        Assert.DoesNotContain("mobileofflinepackets", tokens);
        Assert.DoesNotContain("safehousetravelpacket", tokens);
        Assert.DoesNotContain("safehousetravelpackets", tokens);
        Assert.DoesNotContain("gmopspacket", tokens);
        Assert.DoesNotContain("gmoperationpackets", tokens);
        Assert.DoesNotContain("gmcontrolpacket", tokens);
    }

    [Fact]
    public void RewriteAliases_CollapsesWorkspaceV4CompactFormsIntoCampaignReturnPacketTokens()
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase)
        {
            "workspacev4",
            "campaignworkspacev4",
            "workspacev4packets",
            "workspacev4briefs",
            "campaignworkspacev4brief",
            "campaignworkspacev4briefs"
        };

        PrepLibraryQueryAliasCanonicalizer.RewriteAliases(tokens);

        Assert.Contains("campaign", tokens);
        Assert.Contains("return", tokens);
        Assert.Contains("packet", tokens);
        Assert.DoesNotContain("workspacev4", tokens);
        Assert.DoesNotContain("campaignworkspacev4", tokens);
        Assert.DoesNotContain("workspacev4packets", tokens);
        Assert.DoesNotContain("workspacev4briefs", tokens);
        Assert.DoesNotContain("campaignworkspacev4brief", tokens);
        Assert.DoesNotContain("campaignworkspacev4briefs", tokens);
        Assert.DoesNotContain("workspace", tokens);
        Assert.DoesNotContain("v4", tokens);
        Assert.DoesNotContain("brief", tokens);
        Assert.DoesNotContain("briefs", tokens);
    }
}
