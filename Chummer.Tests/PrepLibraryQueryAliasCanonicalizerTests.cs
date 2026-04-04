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
            "eventcontrolbrfs",
            "eventcontrolspacket",
            "eventcontrolspackets",
            "eventcontrolspkt",
            "eventcontrolspkts",
            "eventcontrolsbrief",
            "eventcontrolsbriefs",
            "eventcontrolsbrf",
            "eventcontrolsbrfs",
            "eventoppacket",
            "eventoppackets",
            "eventoppkt",
            "eventoppkts",
            "eventopbrief",
            "eventopbriefs",
            "eventopbrf",
            "eventopbrfs",
            "eventopspacket",
            "eventopspackets",
            "eventopspkt",
            "eventopspkts",
            "eventopsbrief",
            "eventopsbriefs",
            "eventopsbrf",
            "eventopsbrfs",
            "eventoperationpacket",
            "eventoperationpackets",
            "eventoperationpkt",
            "eventoperationpkts",
            "eventoperationbrief",
            "eventoperationbriefs",
            "eventoperationbrf",
            "eventoperationbrfs",
            "eventoperationspacket",
            "eventoperationspackets",
            "eventoperationspkt",
            "eventoperationspkts",
            "eventoperationsbrief",
            "eventoperationsbriefs",
            "eventoperationsbrf",
            "eventoperationsbrfs"
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
        Assert.DoesNotContain("eventcontrolspacket", tokens);
        Assert.DoesNotContain("eventcontrolspackets", tokens);
        Assert.DoesNotContain("eventcontrolspkt", tokens);
        Assert.DoesNotContain("eventcontrolspkts", tokens);
        Assert.DoesNotContain("eventcontrolsbrief", tokens);
        Assert.DoesNotContain("eventcontrolsbriefs", tokens);
        Assert.DoesNotContain("eventcontrolsbrf", tokens);
        Assert.DoesNotContain("eventcontrolsbrfs", tokens);
        Assert.DoesNotContain("eventoppacket", tokens);
        Assert.DoesNotContain("eventoppackets", tokens);
        Assert.DoesNotContain("eventoppkt", tokens);
        Assert.DoesNotContain("eventoppkts", tokens);
        Assert.DoesNotContain("eventopbrief", tokens);
        Assert.DoesNotContain("eventopbriefs", tokens);
        Assert.DoesNotContain("eventopbrf", tokens);
        Assert.DoesNotContain("eventopbrfs", tokens);
        Assert.DoesNotContain("eventopspacket", tokens);
        Assert.DoesNotContain("eventopspackets", tokens);
        Assert.DoesNotContain("eventopspkt", tokens);
        Assert.DoesNotContain("eventopspkts", tokens);
        Assert.DoesNotContain("eventopsbrief", tokens);
        Assert.DoesNotContain("eventopsbriefs", tokens);
        Assert.DoesNotContain("eventopsbrf", tokens);
        Assert.DoesNotContain("eventopsbrfs", tokens);
        Assert.DoesNotContain("eventoperationpacket", tokens);
        Assert.DoesNotContain("eventoperationpackets", tokens);
        Assert.DoesNotContain("eventoperationpkt", tokens);
        Assert.DoesNotContain("eventoperationpkts", tokens);
        Assert.DoesNotContain("eventoperationbrief", tokens);
        Assert.DoesNotContain("eventoperationbriefs", tokens);
        Assert.DoesNotContain("eventoperationbrf", tokens);
        Assert.DoesNotContain("eventoperationbrfs", tokens);
        Assert.DoesNotContain("eventoperationspacket", tokens);
        Assert.DoesNotContain("eventoperationspackets", tokens);
        Assert.DoesNotContain("eventoperationspkt", tokens);
        Assert.DoesNotContain("eventoperationspkts", tokens);
        Assert.DoesNotContain("eventoperationsbrief", tokens);
        Assert.DoesNotContain("eventoperationsbriefs", tokens);
        Assert.DoesNotContain("eventoperationsbrf", tokens);
        Assert.DoesNotContain("eventoperationsbrfs", tokens);
    }

    [Fact]
    public void RewriteAliases_CollapsesCompactContinuityAndGmPacketFormsIntoUnifiedWorkspaceTokens()
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase)
        {
            "campaignreturnpacket",
            "campaignreturnpkt",
            "campaignreturnbriefs",
            "campaignreturnbrfs",
            "campaignsreturnloop",
            "campaignsreturnpacket",
            "campaignsreturnpkts",
            "campaignsreturnbriefs",
            "campaignsreturnbrf",
            "aftermathreturnpacket",
            "aftermathreturnpkt",
            "aftermathreturnbrief",
            "aftermathreturnbrf",
            "aftermathreturnlane",
            "aftermathreturnlanes",
            "aftermathsreturnpacket",
            "aftermathsreturnpkts",
            "aftermathsreturnbriefs",
            "aftermathsreturnbrf",
            "downtimesreturnloop",
            "downtimereturnpackets",
            "downtimereturnpkt",
            "downtimereturnbriefs",
            "downtimereturnbrf",
            "downtimereturnlane",
            "downtimereturnlanes",
            "downtimesreturnpacket",
            "downtimesreturnpkts",
            "downtimesreturnbriefs",
            "downtimesreturnbrf",
            "diariesreturnloop",
            "diaryreturnloop",
            "diaryreturnlane",
            "diariesreturnpacket",
            "diariesreturnpkts",
            "diariesreturnbriefs",
            "diariesreturnbrf",
            "diaryreturnpacket",
            "diaryreturnpkt",
            "diaryreturnbriefs",
            "diaryreturnbrf",
            "contactsreturnloop",
            "contactreturnloop",
            "contactreturnlane",
            "contactsreturnpacket",
            "contactsreturnpkts",
            "contactsreturnbriefs",
            "contactsreturnbrf",
            "contactreturnpacket",
            "contactreturnpkt",
            "contactreturnbriefs",
            "contactreturnbrf",
            "heatsreturnloop",
            "heatreturnloop",
            "heatreturnlane",
            "heatsreturnpacket",
            "heatsreturnpkts",
            "heatsreturnbriefs",
            "heatsreturnbrf",
            "heatreturnpacket",
            "heatreturnpkt",
            "heatreturnbriefs",
            "heatreturnbrf",
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
            "gmoperationspacket",
            "gmcontrolpacket",
            "gmcontrolspacket",
            "gmopspkt",
            "gmoperationpkts",
            "gmoperationspkt",
            "gmcontrolpkt",
            "gmcontrolspkt",
            "gmopsbriefs",
            "gmoperationbrief",
            "gmoperationsbriefs",
            "gmcontrolbriefs",
            "gmcontrolsbrief",
            "gmopsbrf",
            "gmoperationbrfs",
            "gmoperationsbrf",
            "gmcontrolbrf",
            "gmcontrolsbrfs",
            "gamemasteropspacket",
            "gamemasteroperationpackets",
            "gamemasteroperationspacket",
            "gamemastercontrolpacket",
            "gamemastercontrolspacket",
            "gamemasteropspkt",
            "gamemasteroperationpkts",
            "gamemasteroperationspkt",
            "gamemastercontrolpkt",
            "gamemastercontrolspkt",
            "gamemasteropsbriefs",
            "gamemasteroperationbrief",
            "gamemasteroperationsbriefs",
            "gamemastercontrolbriefs",
            "gamemastercontrolsbrief",
            "gamemasteropsbrf",
            "gamemasteroperationbrfs",
            "gamemasteroperationsbrf",
            "gamemastercontrolbrf",
            "gamemastercontrolsbrfs",
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
        Assert.DoesNotContain("campaignreturnpkt", tokens);
        Assert.DoesNotContain("campaignreturnbriefs", tokens);
        Assert.DoesNotContain("campaignreturnbrfs", tokens);
        Assert.DoesNotContain("campaignsreturnloop", tokens);
        Assert.DoesNotContain("campaignsreturnpacket", tokens);
        Assert.DoesNotContain("campaignsreturnpkts", tokens);
        Assert.DoesNotContain("campaignsreturnbriefs", tokens);
        Assert.DoesNotContain("campaignsreturnbrf", tokens);
        Assert.DoesNotContain("aftermathreturnpacket", tokens);
        Assert.DoesNotContain("aftermathreturnpkt", tokens);
        Assert.DoesNotContain("aftermathreturnbrief", tokens);
        Assert.DoesNotContain("aftermathreturnbrf", tokens);
        Assert.DoesNotContain("aftermathreturnlane", tokens);
        Assert.DoesNotContain("aftermathreturnlanes", tokens);
        Assert.DoesNotContain("aftermathsreturnpacket", tokens);
        Assert.DoesNotContain("aftermathsreturnpkts", tokens);
        Assert.DoesNotContain("aftermathsreturnbriefs", tokens);
        Assert.DoesNotContain("aftermathsreturnbrf", tokens);
        Assert.DoesNotContain("downtimesreturnloop", tokens);
        Assert.DoesNotContain("downtimereturnpackets", tokens);
        Assert.DoesNotContain("downtimereturnpkt", tokens);
        Assert.DoesNotContain("downtimereturnbriefs", tokens);
        Assert.DoesNotContain("downtimereturnbrf", tokens);
        Assert.DoesNotContain("downtimereturnlane", tokens);
        Assert.DoesNotContain("downtimereturnlanes", tokens);
        Assert.DoesNotContain("downtimesreturnpacket", tokens);
        Assert.DoesNotContain("downtimesreturnpkts", tokens);
        Assert.DoesNotContain("downtimesreturnbriefs", tokens);
        Assert.DoesNotContain("downtimesreturnbrf", tokens);
        Assert.DoesNotContain("diariesreturnloop", tokens);
        Assert.DoesNotContain("diaryreturnloop", tokens);
        Assert.DoesNotContain("diaryreturnlane", tokens);
        Assert.DoesNotContain("diariesreturnpacket", tokens);
        Assert.DoesNotContain("diariesreturnpkts", tokens);
        Assert.DoesNotContain("diariesreturnbriefs", tokens);
        Assert.DoesNotContain("diariesreturnbrf", tokens);
        Assert.DoesNotContain("diaryreturnpacket", tokens);
        Assert.DoesNotContain("diaryreturnpkt", tokens);
        Assert.DoesNotContain("diaryreturnbriefs", tokens);
        Assert.DoesNotContain("diaryreturnbrf", tokens);
        Assert.DoesNotContain("contactsreturnloop", tokens);
        Assert.DoesNotContain("contactreturnloop", tokens);
        Assert.DoesNotContain("contactreturnlane", tokens);
        Assert.DoesNotContain("contactsreturnpacket", tokens);
        Assert.DoesNotContain("contactsreturnpkts", tokens);
        Assert.DoesNotContain("contactsreturnbriefs", tokens);
        Assert.DoesNotContain("contactsreturnbrf", tokens);
        Assert.DoesNotContain("contactreturnpacket", tokens);
        Assert.DoesNotContain("contactreturnpkt", tokens);
        Assert.DoesNotContain("contactreturnbriefs", tokens);
        Assert.DoesNotContain("contactreturnbrf", tokens);
        Assert.DoesNotContain("heatsreturnloop", tokens);
        Assert.DoesNotContain("heatreturnloop", tokens);
        Assert.DoesNotContain("heatreturnlane", tokens);
        Assert.DoesNotContain("heatsreturnpacket", tokens);
        Assert.DoesNotContain("heatsreturnpkts", tokens);
        Assert.DoesNotContain("heatsreturnbriefs", tokens);
        Assert.DoesNotContain("heatsreturnbrf", tokens);
        Assert.DoesNotContain("heatreturnpacket", tokens);
        Assert.DoesNotContain("heatreturnpkt", tokens);
        Assert.DoesNotContain("heatreturnbriefs", tokens);
        Assert.DoesNotContain("heatreturnbrf", tokens);
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
        Assert.DoesNotContain("gmoperationspacket", tokens);
        Assert.DoesNotContain("gmcontrolpacket", tokens);
        Assert.DoesNotContain("gmcontrolspacket", tokens);
        Assert.DoesNotContain("gmopspkt", tokens);
        Assert.DoesNotContain("gmoperationpkts", tokens);
        Assert.DoesNotContain("gmoperationspkt", tokens);
        Assert.DoesNotContain("gmcontrolpkt", tokens);
        Assert.DoesNotContain("gmcontrolspkt", tokens);
        Assert.DoesNotContain("gmopsbriefs", tokens);
        Assert.DoesNotContain("gmoperationbrief", tokens);
        Assert.DoesNotContain("gmoperationsbriefs", tokens);
        Assert.DoesNotContain("gmcontrolbriefs", tokens);
        Assert.DoesNotContain("gmcontrolsbrief", tokens);
        Assert.DoesNotContain("gmopsbrf", tokens);
        Assert.DoesNotContain("gmoperationbrfs", tokens);
        Assert.DoesNotContain("gmoperationsbrf", tokens);
        Assert.DoesNotContain("gmcontrolbrf", tokens);
        Assert.DoesNotContain("gmcontrolsbrfs", tokens);
        Assert.DoesNotContain("gamemasteropspacket", tokens);
        Assert.DoesNotContain("gamemasteroperationpackets", tokens);
        Assert.DoesNotContain("gamemasteroperationspacket", tokens);
        Assert.DoesNotContain("gamemastercontrolpacket", tokens);
        Assert.DoesNotContain("gamemastercontrolspacket", tokens);
        Assert.DoesNotContain("gamemasteropspkt", tokens);
        Assert.DoesNotContain("gamemasteroperationpkts", tokens);
        Assert.DoesNotContain("gamemasteroperationspkt", tokens);
        Assert.DoesNotContain("gamemastercontrolpkt", tokens);
        Assert.DoesNotContain("gamemastercontrolspkt", tokens);
        Assert.DoesNotContain("gamemasteropsbriefs", tokens);
        Assert.DoesNotContain("gamemasteroperationbrief", tokens);
        Assert.DoesNotContain("gamemasteroperationsbriefs", tokens);
        Assert.DoesNotContain("gamemastercontrolbriefs", tokens);
        Assert.DoesNotContain("gamemastercontrolsbrief", tokens);
        Assert.DoesNotContain("gamemasteropsbrf", tokens);
        Assert.DoesNotContain("gamemasteroperationbrfs", tokens);
        Assert.DoesNotContain("gamemasteroperationsbrf", tokens);
        Assert.DoesNotContain("gamemastercontrolbrf", tokens);
        Assert.DoesNotContain("gamemastercontrolsbrfs", tokens);
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
            "nextsessionsreturnlanes",
            "nextsessionreturnpacket",
            "nextsessionreturnpackets",
            "nextsessionreturnpkt",
            "nextsessionreturnpkts",
            "nextsessionreturnbrief",
            "nextsessionreturnbriefs",
            "nextsessionreturnbrf",
            "nextsessionreturnbrfs",
            "nextsessionsreturnpacket",
            "nextsessionsreturnpackets",
            "nextsessionsreturnpkt",
            "nextsessionsreturnpkts",
            "nextsessionsreturnbrief",
            "nextsessionsreturnbriefs",
            "nextsessionsreturnbrf",
            "nextsessionsreturnbrfs",
            "sessionreturnpacket",
            "sessionreturnpackets",
            "sessionreturnpkt",
            "sessionreturnpkts",
            "sessionreturnbrief",
            "sessionreturnbriefs",
            "sessionreturnbrf",
            "sessionreturnbrfs"
        };

        PrepLibraryQueryAliasCanonicalizer.RewriteAliases(tokens);

        Assert.Contains("next", tokens);
        Assert.Contains("session", tokens);
        Assert.Contains("return", tokens);
        Assert.Contains("loop", tokens);
        Assert.Contains("packet", tokens);
        Assert.DoesNotContain("nextsessionsreturn", tokens);
        Assert.DoesNotContain("nextsessionsreturns", tokens);
        Assert.DoesNotContain("nextsessionsreturnloop", tokens);
        Assert.DoesNotContain("nextsessionsreturnloops", tokens);
        Assert.DoesNotContain("nextsessionsreturnlane", tokens);
        Assert.DoesNotContain("nextsessionsreturnlanes", tokens);
        Assert.DoesNotContain("nextsessionreturnpacket", tokens);
        Assert.DoesNotContain("nextsessionreturnpackets", tokens);
        Assert.DoesNotContain("nextsessionreturnpkt", tokens);
        Assert.DoesNotContain("nextsessionreturnpkts", tokens);
        Assert.DoesNotContain("nextsessionreturnbrief", tokens);
        Assert.DoesNotContain("nextsessionreturnbriefs", tokens);
        Assert.DoesNotContain("nextsessionreturnbrf", tokens);
        Assert.DoesNotContain("nextsessionreturnbrfs", tokens);
        Assert.DoesNotContain("nextsessionsreturnpacket", tokens);
        Assert.DoesNotContain("nextsessionsreturnpackets", tokens);
        Assert.DoesNotContain("nextsessionsreturnpkt", tokens);
        Assert.DoesNotContain("nextsessionsreturnpkts", tokens);
        Assert.DoesNotContain("nextsessionsreturnbrief", tokens);
        Assert.DoesNotContain("nextsessionsreturnbriefs", tokens);
        Assert.DoesNotContain("nextsessionsreturnbrf", tokens);
        Assert.DoesNotContain("nextsessionsreturnbrfs", tokens);
        Assert.DoesNotContain("sessionreturnpacket", tokens);
        Assert.DoesNotContain("sessionreturnpackets", tokens);
        Assert.DoesNotContain("sessionreturnpkt", tokens);
        Assert.DoesNotContain("sessionreturnpkts", tokens);
        Assert.DoesNotContain("sessionreturnbrief", tokens);
        Assert.DoesNotContain("sessionreturnbriefs", tokens);
        Assert.DoesNotContain("sessionreturnbrf", tokens);
        Assert.DoesNotContain("sessionreturnbrfs", tokens);
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
