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
            "stalecache",
            "stalecaches",
            "staleofflinecache",
            "staleofflinecaches",
            "mobileofflines",
            "mobiletravelreadinesses",
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
        Assert.DoesNotContain("stalecache", tokens);
        Assert.DoesNotContain("stalecaches", tokens);
        Assert.DoesNotContain("staleofflinecache", tokens);
        Assert.DoesNotContain("staleofflinecaches", tokens);
        Assert.DoesNotContain("mobileofflines", tokens);
        Assert.DoesNotContain("mobiletravelreadinesses", tokens);
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
            "mobilecompanionreturnlanes",
            "mobilecompanionsreturnloop",
            "mobilecompanionsreturnloops",
            "mobilecompanionreturnpacket",
            "mobilecompanionsreturnpackets",
            "mobilecompanionreturnpkt",
            "mobilecompanionsreturnpkts",
            "mobilecompanionreturnbrief",
            "mobilecompanionsreturnbriefs",
            "mobilecompanionreturnbrf",
            "mobilecompanionsreturnbrfs",
            "campaignmobilecompanionreturnlane",
            "campaignmobilecompanionreturnlanes",
            "campaignmobilecompanionsreturnloop",
            "campaignmobilecompanionsreturnloops",
            "campaignmobilecompanionreturnpacket",
            "campaignmobilecompanionsreturnpackets",
            "campaignmobilecompanionreturnpkt",
            "campaignmobilecompanionsreturnpkts",
            "campaignmobilecompanionreturnbrief",
            "campaignmobilecompanionsreturnbriefs",
            "campaignmobilecompanionreturnbrf",
            "campaignmobilecompanionsreturnbrfs"
        };

        PrepLibraryQueryAliasCanonicalizer.RewriteAliases(tokens);

        Assert.Contains("campaign", tokens);
        Assert.Contains("offline", tokens);
        Assert.Contains("travel", tokens);
        Assert.Contains("safehouse", tokens);
        Assert.Contains("return", tokens);
        Assert.Contains("loop", tokens);
        Assert.Contains("packet", tokens);
        Assert.DoesNotContain("mobilecompanionreturnlanes", tokens);
        Assert.DoesNotContain("mobilecompanionsreturnloop", tokens);
        Assert.DoesNotContain("mobilecompanionsreturnloops", tokens);
        Assert.DoesNotContain("mobilecompanionreturnpacket", tokens);
        Assert.DoesNotContain("mobilecompanionsreturnpackets", tokens);
        Assert.DoesNotContain("mobilecompanionreturnpkt", tokens);
        Assert.DoesNotContain("mobilecompanionsreturnpkts", tokens);
        Assert.DoesNotContain("mobilecompanionreturnbrief", tokens);
        Assert.DoesNotContain("mobilecompanionsreturnbriefs", tokens);
        Assert.DoesNotContain("mobilecompanionreturnbrf", tokens);
        Assert.DoesNotContain("mobilecompanionsreturnbrfs", tokens);
        Assert.DoesNotContain("campaignmobilecompanionreturnlane", tokens);
        Assert.DoesNotContain("campaignmobilecompanionreturnlanes", tokens);
        Assert.DoesNotContain("campaignmobilecompanionsreturnloop", tokens);
        Assert.DoesNotContain("campaignmobilecompanionsreturnloops", tokens);
        Assert.DoesNotContain("campaignmobilecompanionreturnpacket", tokens);
        Assert.DoesNotContain("campaignmobilecompanionsreturnpackets", tokens);
        Assert.DoesNotContain("campaignmobilecompanionreturnpkt", tokens);
        Assert.DoesNotContain("campaignmobilecompanionsreturnpkts", tokens);
        Assert.DoesNotContain("campaignmobilecompanionreturnbrief", tokens);
        Assert.DoesNotContain("campaignmobilecompanionsreturnbriefs", tokens);
        Assert.DoesNotContain("campaignmobilecompanionreturnbrf", tokens);
        Assert.DoesNotContain("campaignmobilecompanionsreturnbrfs", tokens);
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
            "preplaunch",
            "preplaunches",
            "preplibrarypacket",
            "preplibrarypkt",
            "preplibrarypkts",
            "preplibrarybrief",
            "preplibrarybriefs",
            "preplibrarybrf",
            "preplibrarybrfs",
            "travelprefetch",
            "travelprefetches",
            "oppositionpacket",
            "oppositionpackets",
            "oppositionpkt",
            "oppositionpkts",
            "oppositionbrief",
            "oppositionbriefs",
            "oppositionbrf",
            "oppositionbrfs",
            "rostermovepacket",
            "rostermovepackets",
            "rostermovepkt",
            "rostermovepkts",
            "rostermovementpacket",
            "rostermovementpkt",
            "rostermovementpkts",
            "rostermovebrief",
            "rostermovementbriefs",
            "rostermovebrf",
            "rostermovebrfs",
            "rostermovementbrf",
            "rostermovementbrfs",
            "eventcontrolpacket",
            "eventcontrolpackets",
            "eventcontrolpkt",
            "eventcontrolpkts",
            "eventcontrolbrief",
            "eventcontrolbriefs",
            "eventcontrolbrf",
            "eventcontrolbrfs"
        };

        PrepLibraryQueryAliasCanonicalizer.RewriteAliases(tokens);

        Assert.Contains("prep", tokens);
        Assert.Contains("launch", tokens);
        Assert.Contains("library", tokens);
        Assert.Contains("travel", tokens);
        Assert.Contains("prefetch", tokens);
        Assert.Contains("opposition", tokens);
        Assert.Contains("roster", tokens);
        Assert.Contains("move", tokens);
        Assert.Contains("eventcontrol", tokens);
        Assert.Contains("packet", tokens);
        Assert.DoesNotContain("preplaunch", tokens);
        Assert.DoesNotContain("preplaunches", tokens);
        Assert.DoesNotContain("preplibrarypacket", tokens);
        Assert.DoesNotContain("preplibrarypkt", tokens);
        Assert.DoesNotContain("preplibrarypkts", tokens);
        Assert.DoesNotContain("preplibrarybrief", tokens);
        Assert.DoesNotContain("preplibrarybriefs", tokens);
        Assert.DoesNotContain("preplibrarybrf", tokens);
        Assert.DoesNotContain("preplibrarybrfs", tokens);
        Assert.DoesNotContain("travelprefetch", tokens);
        Assert.DoesNotContain("travelprefetches", tokens);
        Assert.DoesNotContain("oppositionpacket", tokens);
        Assert.DoesNotContain("oppositionpackets", tokens);
        Assert.DoesNotContain("oppositionpkt", tokens);
        Assert.DoesNotContain("oppositionpkts", tokens);
        Assert.DoesNotContain("oppositionbrief", tokens);
        Assert.DoesNotContain("oppositionbriefs", tokens);
        Assert.DoesNotContain("oppositionbrf", tokens);
        Assert.DoesNotContain("oppositionbrfs", tokens);
        Assert.DoesNotContain("rostermovepacket", tokens);
        Assert.DoesNotContain("rostermovepackets", tokens);
        Assert.DoesNotContain("rostermovepkt", tokens);
        Assert.DoesNotContain("rostermovepkts", tokens);
        Assert.DoesNotContain("rostermovementpacket", tokens);
        Assert.DoesNotContain("rostermovementpkt", tokens);
        Assert.DoesNotContain("rostermovementpkts", tokens);
        Assert.DoesNotContain("rostermovebrief", tokens);
        Assert.DoesNotContain("rostermovementbriefs", tokens);
        Assert.DoesNotContain("rostermovebrf", tokens);
        Assert.DoesNotContain("rostermovebrfs", tokens);
        Assert.DoesNotContain("rostermovementbrf", tokens);
        Assert.DoesNotContain("rostermovementbrfs", tokens);
        Assert.DoesNotContain("eventcontrolpacket", tokens);
        Assert.DoesNotContain("eventcontrolpackets", tokens);
        Assert.DoesNotContain("eventcontrolpkt", tokens);
        Assert.DoesNotContain("eventcontrolpkts", tokens);
        Assert.DoesNotContain("eventcontrolbrief", tokens);
        Assert.DoesNotContain("eventcontrolbriefs", tokens);
        Assert.DoesNotContain("eventcontrolbrf", tokens);
        Assert.DoesNotContain("eventcontrolbrfs", tokens);
    }

    [Fact]
    public void RewriteAliases_CollapsesCompactContinuityAndGmPacketFormsIntoUnifiedWorkspaceTokens()
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase)
        {
            "campaignreturnpacket",
            "campaignreturnbriefs",
            "campaignsreturnloop",
            "campaignsreturnpacket",
            "campaignsreturnbriefs",
            "aftermathreturnpacket",
            "aftermathreturnbrief",
            "aftermathreturnlane",
            "aftermathreturnlanes",
            "aftermathsreturnpacket",
            "aftermathsreturnbriefs",
            "downtimesreturnloop",
            "downtimereturnpackets",
            "downtimereturnbriefs",
            "downtimereturnlane",
            "downtimereturnlanes",
            "downtimesreturnpacket",
            "downtimesreturnbriefs",
            "diariesreturnloop",
            "diaryreturnloop",
            "diaryreturnlane",
            "diariesreturnpacket",
            "diariesreturnbriefs",
            "diaryreturnpacket",
            "diaryreturnbriefs",
            "contactsreturnloop",
            "contactreturnloop",
            "contactreturnlane",
            "contactsreturnpacket",
            "contactsreturnbriefs",
            "contactreturnpacket",
            "contactreturnbriefs",
            "heatsreturnloop",
            "heatreturnloop",
            "heatreturnlane",
            "heatsreturnpacket",
            "heatsreturnbriefs",
            "heatreturnpacket",
            "heatreturnbriefs",
            "diarycontactheatpacket",
            "diarycontactsheatpackets",
            "aftermathdowntimepacket",
            "aftermathsdowntimepackets",
            "travelofflinepacket",
            "travelofflinepackets",
            "travelofflinepkt",
            "travelofflinepkts",
            "travelofflinebrief",
            "travelofflinebriefs",
            "travelofflinebrf",
            "travelofflinebrfs",
            "mobileofflinepacket",
            "mobileofflinepackets",
            "mobileofflinepkt",
            "mobileofflinepkts",
            "mobileofflinebrief",
            "mobileofflinebriefs",
            "mobileofflinebrf",
            "mobileofflinebrfs",
            "safehousetravelpacket",
            "safehousetravelpackets",
            "safehousetravelpkt",
            "safehousetravelpkts",
            "safehousetravelbrief",
            "safehousetravelbriefs",
            "safehousetravelbrf",
            "safehousetravelbrfs",
            "safehouseofflinepacket",
            "safehouseofflinepackets",
            "safehouseofflinepkt",
            "safehouseofflinepkts",
            "safehouseofflinebrief",
            "safehouseofflinebriefs",
            "safehouseofflinebrf",
            "safehouseofflinebrfs",
            "mobilesafehouseofflinepacket",
            "mobilesafehouseofflinepackets",
            "mobilesafehouseofflinepkt",
            "mobilesafehouseofflinepkts",
            "mobilesafehouseofflinebrief",
            "mobilesafehouseofflinebriefs",
            "mobilesafehouseofflinebrf",
            "mobilesafehouseofflinebrfs",
            "gmopspacket",
            "gmoperationpackets",
            "gmcontrolpacket",
            "gmopsbriefs",
            "gmoperationbrief",
            "gmcontrolbriefs",
            "gamemasteropspacket",
            "gamemasteroperationpackets",
            "gamemastercontrolpacket",
            "gamemasteropsbriefs",
            "gamemasteroperationbrief",
            "gamemastercontrolbriefs",
            "rostertransfer",
            "rostertransfers",
            "rosterhandoff",
            "rosterhandoffs",
            "gamemasterctls",
            "gamemasterctrls"
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
        Assert.DoesNotContain("campaignsreturnloop", tokens);
        Assert.DoesNotContain("campaignsreturnpacket", tokens);
        Assert.DoesNotContain("campaignsreturnbriefs", tokens);
        Assert.DoesNotContain("aftermathreturnpacket", tokens);
        Assert.DoesNotContain("aftermathreturnbrief", tokens);
        Assert.DoesNotContain("aftermathreturnlane", tokens);
        Assert.DoesNotContain("aftermathreturnlanes", tokens);
        Assert.DoesNotContain("aftermathsreturnpacket", tokens);
        Assert.DoesNotContain("aftermathsreturnbriefs", tokens);
        Assert.DoesNotContain("downtimesreturnloop", tokens);
        Assert.DoesNotContain("downtimereturnpackets", tokens);
        Assert.DoesNotContain("downtimereturnbriefs", tokens);
        Assert.DoesNotContain("downtimereturnlane", tokens);
        Assert.DoesNotContain("downtimereturnlanes", tokens);
        Assert.DoesNotContain("downtimesreturnpacket", tokens);
        Assert.DoesNotContain("downtimesreturnbriefs", tokens);
        Assert.DoesNotContain("diariesreturnloop", tokens);
        Assert.DoesNotContain("diaryreturnloop", tokens);
        Assert.DoesNotContain("diaryreturnlane", tokens);
        Assert.DoesNotContain("diariesreturnpacket", tokens);
        Assert.DoesNotContain("diariesreturnbriefs", tokens);
        Assert.DoesNotContain("diaryreturnpacket", tokens);
        Assert.DoesNotContain("diaryreturnbriefs", tokens);
        Assert.DoesNotContain("contactsreturnloop", tokens);
        Assert.DoesNotContain("contactreturnloop", tokens);
        Assert.DoesNotContain("contactreturnlane", tokens);
        Assert.DoesNotContain("contactsreturnpacket", tokens);
        Assert.DoesNotContain("contactsreturnbriefs", tokens);
        Assert.DoesNotContain("contactreturnpacket", tokens);
        Assert.DoesNotContain("contactreturnbriefs", tokens);
        Assert.DoesNotContain("heatsreturnloop", tokens);
        Assert.DoesNotContain("heatreturnloop", tokens);
        Assert.DoesNotContain("heatreturnlane", tokens);
        Assert.DoesNotContain("heatsreturnpacket", tokens);
        Assert.DoesNotContain("heatsreturnbriefs", tokens);
        Assert.DoesNotContain("heatreturnpacket", tokens);
        Assert.DoesNotContain("heatreturnbriefs", tokens);
        Assert.DoesNotContain("diarycontactheatpacket", tokens);
        Assert.DoesNotContain("diarycontactsheatpackets", tokens);
        Assert.DoesNotContain("aftermathdowntimepacket", tokens);
        Assert.DoesNotContain("aftermathsdowntimepackets", tokens);
        Assert.DoesNotContain("travelofflinepacket", tokens);
        Assert.DoesNotContain("travelofflinepackets", tokens);
        Assert.DoesNotContain("travelofflinepkt", tokens);
        Assert.DoesNotContain("travelofflinepkts", tokens);
        Assert.DoesNotContain("travelofflinebrief", tokens);
        Assert.DoesNotContain("travelofflinebriefs", tokens);
        Assert.DoesNotContain("travelofflinebrf", tokens);
        Assert.DoesNotContain("travelofflinebrfs", tokens);
        Assert.DoesNotContain("mobileofflinepacket", tokens);
        Assert.DoesNotContain("mobileofflinepackets", tokens);
        Assert.DoesNotContain("mobileofflinepkt", tokens);
        Assert.DoesNotContain("mobileofflinepkts", tokens);
        Assert.DoesNotContain("mobileofflinebrief", tokens);
        Assert.DoesNotContain("mobileofflinebriefs", tokens);
        Assert.DoesNotContain("mobileofflinebrf", tokens);
        Assert.DoesNotContain("mobileofflinebrfs", tokens);
        Assert.DoesNotContain("safehousetravelpacket", tokens);
        Assert.DoesNotContain("safehousetravelpackets", tokens);
        Assert.DoesNotContain("safehousetravelpkt", tokens);
        Assert.DoesNotContain("safehousetravelpkts", tokens);
        Assert.DoesNotContain("safehousetravelbrief", tokens);
        Assert.DoesNotContain("safehousetravelbriefs", tokens);
        Assert.DoesNotContain("safehousetravelbrf", tokens);
        Assert.DoesNotContain("safehousetravelbrfs", tokens);
        Assert.DoesNotContain("safehouseofflinepacket", tokens);
        Assert.DoesNotContain("safehouseofflinepackets", tokens);
        Assert.DoesNotContain("safehouseofflinepkt", tokens);
        Assert.DoesNotContain("safehouseofflinepkts", tokens);
        Assert.DoesNotContain("safehouseofflinebrief", tokens);
        Assert.DoesNotContain("safehouseofflinebriefs", tokens);
        Assert.DoesNotContain("safehouseofflinebrf", tokens);
        Assert.DoesNotContain("safehouseofflinebrfs", tokens);
        Assert.DoesNotContain("mobilesafehouseofflinepacket", tokens);
        Assert.DoesNotContain("mobilesafehouseofflinepackets", tokens);
        Assert.DoesNotContain("mobilesafehouseofflinepkt", tokens);
        Assert.DoesNotContain("mobilesafehouseofflinepkts", tokens);
        Assert.DoesNotContain("mobilesafehouseofflinebrief", tokens);
        Assert.DoesNotContain("mobilesafehouseofflinebriefs", tokens);
        Assert.DoesNotContain("mobilesafehouseofflinebrf", tokens);
        Assert.DoesNotContain("mobilesafehouseofflinebrfs", tokens);
        Assert.DoesNotContain("gmopspacket", tokens);
        Assert.DoesNotContain("gmoperationpackets", tokens);
        Assert.DoesNotContain("gmcontrolpacket", tokens);
        Assert.DoesNotContain("gmopsbriefs", tokens);
        Assert.DoesNotContain("gmoperationbrief", tokens);
        Assert.DoesNotContain("gmcontrolbriefs", tokens);
        Assert.DoesNotContain("gamemasteropspacket", tokens);
        Assert.DoesNotContain("gamemasteroperationpackets", tokens);
        Assert.DoesNotContain("gamemastercontrolpacket", tokens);
        Assert.DoesNotContain("gamemasteropsbriefs", tokens);
        Assert.DoesNotContain("gamemasteroperationbrief", tokens);
        Assert.DoesNotContain("gamemastercontrolbriefs", tokens);
        Assert.DoesNotContain("rostertransfer", tokens);
        Assert.DoesNotContain("rostertransfers", tokens);
        Assert.DoesNotContain("rosterhandoff", tokens);
        Assert.DoesNotContain("rosterhandoffs", tokens);
        Assert.DoesNotContain("gamemasterctls", tokens);
        Assert.DoesNotContain("gamemasterctrls", tokens);
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

    [Fact]
    public void RewriteAliases_CollapsesCompactNextSessionsReturnFormsIntoNextSessionReturnLoopTokens()
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase)
        {
            "nextsessionsreturn",
            "nextsessionsreturns",
            "nextsessionsreturnloop",
            "nextsessionsreturnloops",
            "nextsessionsreturnlane",
            "nextsessionsreturnlanes"
        };

        PrepLibraryQueryAliasCanonicalizer.RewriteAliases(tokens);

        Assert.Contains("next", tokens);
        Assert.Contains("session", tokens);
        Assert.Contains("return", tokens);
        Assert.Contains("loop", tokens);
        Assert.DoesNotContain("nextsessionsreturn", tokens);
        Assert.DoesNotContain("nextsessionsreturns", tokens);
        Assert.DoesNotContain("nextsessionsreturnloop", tokens);
        Assert.DoesNotContain("nextsessionsreturnloops", tokens);
        Assert.DoesNotContain("nextsessionsreturnlane", tokens);
        Assert.DoesNotContain("nextsessionsreturnlanes", tokens);
    }

    [Fact]
    public void RewriteAliases_CollapsesOpForShorthandIntoOppositionTokens()
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase)
        {
            "opfor",
            "opforce",
            "opforces",
            "opfors"
        };

        PrepLibraryQueryAliasCanonicalizer.RewriteAliases(tokens);

        Assert.Contains("opposition", tokens);
        Assert.DoesNotContain("opfor", tokens);
        Assert.DoesNotContain("opforce", tokens);
        Assert.DoesNotContain("opforces", tokens);
        Assert.DoesNotContain("opfors", tokens);
    }
}
