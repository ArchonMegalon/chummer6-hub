namespace Chummer.Run.Contracts.Search;

public static class PrepLibraryQueryAliasCanonicalizer
{
    public static void RewriteAliases(HashSet<string> tokens)
    {
        ArgumentNullException.ThrowIfNull(tokens);

        RewriteCompactContinuityMutationAlias(tokens, "contactupdate", "contact", "update");
        RewriteCompactContinuityMutationAlias(tokens, "contactupdates", "contact", "updates");
        RewriteCompactContinuityMutationAlias(tokens, "contactsupdate", "contacts", "update");
        RewriteCompactContinuityMutationAlias(tokens, "contactsupdates", "contacts", "updates");
        RewriteCompactContinuityMutationAlias(tokens, "contactchange", "contact", "change");
        RewriteCompactContinuityMutationAlias(tokens, "contactchanges", "contact", "changes");
        RewriteCompactContinuityMutationAlias(tokens, "contactchanged", "contact", "changed");
        RewriteCompactContinuityMutationAlias(tokens, "contactschange", "contacts", "change");
        RewriteCompactContinuityMutationAlias(tokens, "contactschanges", "contacts", "changes");
        RewriteCompactContinuityMutationAlias(tokens, "contactschanged", "contacts", "changed");
        RewriteCompactContinuityMutationAlias(tokens, "connectionupdate", "connection", "update");
        RewriteCompactContinuityMutationAlias(tokens, "connectionupdates", "connection", "updates");
        RewriteCompactContinuityMutationAlias(tokens, "connectionupdated", "connection", "updated");
        RewriteCompactContinuityMutationAlias(tokens, "connectionchange", "connection", "change");
        RewriteCompactContinuityMutationAlias(tokens, "connectionchanges", "connection", "changes");
        RewriteCompactContinuityMutationAlias(tokens, "connectionchanged", "connection", "changed");
        RewriteCompactContinuityMutationAlias(tokens, "connectionsupdate", "connections", "update");
        RewriteCompactContinuityMutationAlias(tokens, "connectionsupdates", "connections", "updates");
        RewriteCompactContinuityMutationAlias(tokens, "connectionsupdated", "connections", "updated");
        RewriteCompactContinuityMutationAlias(tokens, "connectionschange", "connections", "change");
        RewriteCompactContinuityMutationAlias(tokens, "connectionschanges", "connections", "changes");
        RewriteCompactContinuityMutationAlias(tokens, "connectionschanged", "connections", "changed");
        RewriteCompactContinuityMutationAlias(tokens, "relationshipupdate", "relationship", "update");
        RewriteCompactContinuityMutationAlias(tokens, "relationshipupdates", "relationship", "updates");
        RewriteCompactContinuityMutationAlias(tokens, "relationshipupdated", "relationship", "updated");
        RewriteCompactContinuityMutationAlias(tokens, "relationshipchange", "relationship", "change");
        RewriteCompactContinuityMutationAlias(tokens, "relationshipchanges", "relationship", "changes");
        RewriteCompactContinuityMutationAlias(tokens, "relationshipchanged", "relationship", "changed");
        RewriteCompactContinuityMutationAlias(tokens, "relationshipsupdate", "relationships", "update");
        RewriteCompactContinuityMutationAlias(tokens, "relationshipsupdates", "relationships", "updates");
        RewriteCompactContinuityMutationAlias(tokens, "relationshipsupdated", "relationships", "updated");
        RewriteCompactContinuityMutationAlias(tokens, "relationshipschange", "relationships", "change");
        RewriteCompactContinuityMutationAlias(tokens, "relationshipschanges", "relationships", "changes");
        RewriteCompactContinuityMutationAlias(tokens, "relationshipschanged", "relationships", "changed");
        RewriteCompactContinuityMutationAlias(tokens, "heatupdate", "heat", "update");
        RewriteCompactContinuityMutationAlias(tokens, "heatupdates", "heat", "updates");
        RewriteCompactContinuityMutationAlias(tokens, "heatupdated", "heat", "updated");
        RewriteCompactContinuityMutationAlias(tokens, "heatchange", "heat", "change");
        RewriteCompactContinuityMutationAlias(tokens, "heatchanges", "heat", "changes");
        RewriteCompactContinuityMutationAlias(tokens, "heatchanged", "heat", "changed");
        RewriteCompactContinuityMutationAlias(tokens, "diaryupdate", "diary", "update");
        RewriteCompactContinuityMutationAlias(tokens, "diaryupdates", "diary", "updates");
        RewriteCompactContinuityMutationAlias(tokens, "diaryupdated", "diary", "updated");
        RewriteCompactContinuityMutationAlias(tokens, "diarychange", "diary", "change");
        RewriteCompactContinuityMutationAlias(tokens, "diarychanges", "diary", "changes");
        RewriteCompactContinuityMutationAlias(tokens, "diarychanged", "diary", "changed");
        RewriteCompactContinuityMutationAlias(tokens, "journalupdate", "journal", "update");
        RewriteCompactContinuityMutationAlias(tokens, "journalupdates", "journal", "updates");
        RewriteCompactContinuityMutationAlias(tokens, "journalupdated", "journal", "updated");
        RewriteCompactContinuityMutationAlias(tokens, "journalchange", "journal", "change");
        RewriteCompactContinuityMutationAlias(tokens, "journalchanges", "journal", "changes");
        RewriteCompactContinuityMutationAlias(tokens, "journalchanged", "journal", "changed");
        RewriteCompactContinuityMutationAlias(tokens, "sessionlogupdate", "session", "log", "update");
        RewriteCompactContinuityMutationAlias(tokens, "sessionlogupdates", "session", "log", "updates");
        RewriteCompactContinuityMutationAlias(tokens, "sessionlogupdated", "session", "log", "updated");
        RewriteCompactContinuityMutationAlias(tokens, "sessionlogchange", "session", "log", "change");
        RewriteCompactContinuityMutationAlias(tokens, "sessionlogchanges", "session", "log", "changes");
        RewriteCompactContinuityMutationAlias(tokens, "sessionlogchanged", "session", "log", "changed");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathreturn", "aftermath", "return");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathreturns", "aftermath", "return");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathreturnloop", "aftermath", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathreturnloops", "aftermath", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsreturn", "aftermath", "return");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsreturns", "aftermath", "return");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsreturnloop", "aftermath", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsreturnloops", "aftermath", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathreturnlane", "aftermath", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathreturnlanes", "aftermath", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsreturnlane", "aftermath", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsreturnlanes", "aftermath", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "downtimereturn", "downtime", "return");
        RewriteCompactContinuityMutationAlias(tokens, "downtimereturns", "downtime", "return");
        RewriteCompactContinuityMutationAlias(tokens, "downtimereturnloop", "downtime", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "downtimereturnloops", "downtime", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "downtimereturnlane", "downtime", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "downtimereturnlanes", "downtime", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "downtimesreturn", "downtime", "return");
        RewriteCompactContinuityMutationAlias(tokens, "downtimesreturns", "downtime", "return");
        RewriteCompactContinuityMutationAlias(tokens, "downtimesreturnloop", "downtime", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "downtimesreturnloops", "downtime", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "downtimesreturnlane", "downtime", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "downtimesreturnlanes", "downtime", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "diariesreturn", "diary", "return");
        RewriteCompactContinuityMutationAlias(tokens, "diariesreturns", "diary", "return");
        RewriteCompactContinuityMutationAlias(tokens, "diaryreturn", "diary", "return");
        RewriteCompactContinuityMutationAlias(tokens, "diaryreturns", "diary", "return");
        RewriteCompactContinuityMutationAlias(tokens, "diaryreturnloop", "diary", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "diaryreturnloops", "diary", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "diaryreturnlane", "diary", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "diaryreturnlanes", "diary", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "diariesreturnloop", "diary", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "diariesreturnloops", "diary", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "diariesreturnlane", "diary", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "diariesreturnlanes", "diary", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "contactreturn", "contact", "return");
        RewriteCompactContinuityMutationAlias(tokens, "contactreturns", "contact", "return");
        RewriteCompactContinuityMutationAlias(tokens, "contactreturnloop", "contact", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "contactreturnloops", "contact", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "contactreturnlane", "contact", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "contactreturnlanes", "contact", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "contactsreturn", "contacts", "return");
        RewriteCompactContinuityMutationAlias(tokens, "contactsreturns", "contacts", "return");
        RewriteCompactContinuityMutationAlias(tokens, "contactsreturnloop", "contacts", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "contactsreturnloops", "contacts", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "contactsreturnlane", "contacts", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "contactsreturnlanes", "contacts", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "heatreturn", "heat", "return");
        RewriteCompactContinuityMutationAlias(tokens, "heatreturns", "heat", "return");
        RewriteCompactContinuityMutationAlias(tokens, "heatreturnloop", "heat", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "heatreturnloops", "heat", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "heatreturnlane", "heat", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "heatreturnlanes", "heat", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "heatsreturn", "heat", "return");
        RewriteCompactContinuityMutationAlias(tokens, "heatsreturns", "heat", "return");
        RewriteCompactContinuityMutationAlias(tokens, "heatsreturnloop", "heat", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "heatsreturnloops", "heat", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "heatsreturnlane", "heat", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "heatsreturnlanes", "heat", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignreturn", "campaign", "return");
        RewriteCompactContinuityMutationAlias(tokens, "campaignreturns", "campaign", "return");
        RewriteCompactContinuityMutationAlias(tokens, "campaignreturnloop", "campaign", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignreturnloops", "campaign", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignreturnlane", "campaign", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignreturnlanes", "campaign", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignsreturn", "campaign", "return");
        RewriteCompactContinuityMutationAlias(tokens, "campaignsreturns", "campaign", "return");
        RewriteCompactContinuityMutationAlias(tokens, "campaignsreturnloop", "campaign", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignsreturnloops", "campaign", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignsreturnlane", "campaign", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignsreturnlanes", "campaign", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "preplibrarypacket", "prep", "library", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "preplibrarypackets", "prep", "library", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "preplibrarypkt", "prep", "library", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "preplibrarypkts", "prep", "library", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "preplibrarybrief", "prep", "library", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "preplibrarybriefs", "prep", "library", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "preplibrarybrf", "prep", "library", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "preplibrarybrfs", "prep", "library", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionpacket", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionpackets", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionpkt", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionpkts", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionbrief", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionbriefs", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionbrf", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionbrfs", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionspacket", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionspackets", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionspkt", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionspkts", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionsbrief", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionsbriefs", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionsbrf", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "oppositionsbrfs", "opposition", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovepacket", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovepackets", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovepkt", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovepkts", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovementpacket", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovementpackets", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovementpkt", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovementpkts", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovebrief", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovebriefs", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovebrf", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovebrfs", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovementbrief", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovementbriefs", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovementbrf", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostermovementbrfs", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovepacket", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovepackets", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovepkt", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovepkts", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovementpacket", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovementpackets", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovementpkt", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovementpkts", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovebrief", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovebriefs", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovebrf", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovebrfs", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovementbrief", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovementbriefs", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovementbrf", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "rostersmovementbrfs", "roster", "movement", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolpacket", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolpackets", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolpkt", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolpkts", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolbrief", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolbriefs", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolbrf", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolbrfs", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolspacket", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolspackets", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolspkt", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolspkts", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolsbrief", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolsbriefs", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolsbrf", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventcontrolsbrfs", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoppacket", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoppackets", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoppkt", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoppkts", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventopbrief", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventopbriefs", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventopbrf", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventopbrfs", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventopspacket", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventopspackets", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventopspkt", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventopspkts", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventopsbrief", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventopsbriefs", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventopsbrf", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventopsbrfs", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationpacket", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationpackets", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationpkt", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationpkts", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationbrief", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationbriefs", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationbrf", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationbrfs", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationspacket", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationspackets", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationspkt", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationspkts", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationsbrief", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationsbriefs", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationsbrf", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "eventoperationsbrfs", "event", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignreturnpacket", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignreturnpackets", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignreturnpkt", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignreturnpkts", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignreturnbrief", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignreturnbriefs", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignreturnbrf", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignreturnbrfs", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignsreturnpacket", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignsreturnpackets", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignsreturnpkt", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignsreturnpkts", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignsreturnbrief", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignsreturnbriefs", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignsreturnbrf", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignsreturnbrfs", "campaign", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathreturnpacket", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathreturnpackets", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathreturnpkt", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathreturnpkts", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathreturnbrief", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathreturnbriefs", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathreturnbrf", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathreturnbrfs", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsreturnpacket", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsreturnpackets", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsreturnpkt", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsreturnpkts", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsreturnbrief", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsreturnbriefs", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsreturnbrf", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsreturnbrfs", "aftermath", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimereturnpacket", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimereturnpackets", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimereturnpkt", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimereturnpkts", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimereturnbrief", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimereturnbriefs", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimereturnbrf", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimereturnbrfs", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimesreturnpacket", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimesreturnpackets", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimesreturnpkt", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimesreturnpkts", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimesreturnbrief", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimesreturnbriefs", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimesreturnbrf", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "downtimesreturnbrfs", "downtime", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diariesreturnpacket", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diariesreturnpackets", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diariesreturnpkt", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diariesreturnpkts", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diariesreturnbrief", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diariesreturnbriefs", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diariesreturnbrf", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diariesreturnbrfs", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diaryreturnpacket", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diaryreturnpackets", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diaryreturnpkt", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diaryreturnpkts", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diaryreturnbrief", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diaryreturnbriefs", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diaryreturnbrf", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diaryreturnbrfs", "diary", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactsreturnpacket", "contacts", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactsreturnpackets", "contacts", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactsreturnpkt", "contacts", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactsreturnpkts", "contacts", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactsreturnbrief", "contacts", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactsreturnbriefs", "contacts", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactsreturnbrf", "contacts", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactsreturnbrfs", "contacts", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactreturnpacket", "contact", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactreturnpackets", "contact", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactreturnpkt", "contact", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactreturnpkts", "contact", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactreturnbrief", "contact", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactreturnbriefs", "contact", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactreturnbrf", "contact", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "contactreturnbrfs", "contact", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatsreturnpacket", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatsreturnpackets", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatsreturnpkt", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatsreturnpkts", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatsreturnbrief", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatsreturnbriefs", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatsreturnbrf", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatsreturnbrfs", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatreturnpacket", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatreturnpackets", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatreturnpkt", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatreturnpkts", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatreturnbrief", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatreturnbriefs", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatreturnbrf", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "heatreturnbrfs", "heat", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diarycontactheatpacket", "diary", "contact", "heat", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diarycontactheatpackets", "diary", "contact", "heat", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diarycontactsheatpacket", "diary", "contacts", "heat", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "diarycontactsheatpackets", "diary", "contacts", "heat", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathdowntimepacket", "aftermath", "downtime", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathdowntimepackets", "aftermath", "downtime", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsdowntimepacket", "aftermath", "downtime", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "aftermathsdowntimepackets", "aftermath", "downtime", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionreturnpacket", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionreturnpackets", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionreturnpkt", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionreturnpkts", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionreturnbrief", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionreturnbriefs", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionreturnbrf", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionreturnbrfs", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionsreturnpacket", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionsreturnpackets", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionsreturnpkt", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionsreturnpkts", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionsreturnbrief", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionsreturnbriefs", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionsreturnbrf", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "nextsessionsreturnbrfs", "next", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "sessionreturnpacket", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "sessionreturnpackets", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "sessionreturnpkt", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "sessionreturnpkts", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "sessionreturnbrief", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "sessionreturnbriefs", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "sessionreturnbrf", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "sessionreturnbrfs", "session", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "preplaunch", "prep", "launch");
        RewriteCompactContinuityMutationAlias(tokens, "preplaunches", "prep", "launch");
        RewriteCompactContinuityMutationAlias(tokens, "travelprefetch", "travel", "prefetch");
        RewriteCompactContinuityMutationAlias(tokens, "travelprefetches", "travel", "prefetch");
        RewriteCompactContinuityMutationAlias(tokens, "travelofflinepacket", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelofflinepackets", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelofflinepkt", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelofflinepkts", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelofflinebrief", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelofflinebriefs", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelofflinebrf", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelofflinebrfs", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelsofflinepacket", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelsofflinepackets", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelsofflinepkt", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelsofflinepkts", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelsofflinebrief", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelsofflinebriefs", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelsofflinebrf", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "travelsofflinebrfs", "travel", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobileofflinepacket", "mobile", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobileofflinepackets", "mobile", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobileofflinepkt", "mobile", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobileofflinepkts", "mobile", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobileofflinebrief", "mobile", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobileofflinebriefs", "mobile", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobileofflinebrf", "mobile", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobileofflinebrfs", "mobile", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousetravelpacket", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousetravelpackets", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousetravelpkt", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousetravelpkts", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousetravelbrief", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousetravelbriefs", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousetravelbrf", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousetravelbrfs", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousestravelpacket", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousestravelpackets", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousestravelpkt", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousestravelpkts", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousestravelbrief", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousestravelbriefs", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousestravelbrf", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousestravelbrfs", "safehouse", "travel", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehouseofflinepacket", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehouseofflinepackets", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehouseofflinepkt", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehouseofflinepkts", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehouseofflinebrief", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehouseofflinebriefs", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehouseofflinebrf", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehouseofflinebrfs", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousesofflinepacket", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousesofflinepackets", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousesofflinepkt", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousesofflinepkts", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousesofflinebrief", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousesofflinebriefs", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousesofflinebrf", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "safehousesofflinebrfs", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehouseofflinepacket", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehouseofflinepackets", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehouseofflinepkt", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehouseofflinepkts", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehouseofflinebrief", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehouseofflinebriefs", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehouseofflinebrf", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehouseofflinebrfs", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehousesofflinepacket", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehousesofflinepackets", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehousesofflinepkt", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehousesofflinepkts", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehousesofflinebrief", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehousesofflinebriefs", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehousesofflinebrf", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehousesofflinebrfs", "mobile", "safehouse", "offline", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmopspacket", "gm", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmopspackets", "gm", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmopspkt", "gm", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmopspkts", "gm", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmopsbrief", "gm", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmopsbriefs", "gm", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmopsbrf", "gm", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmopsbrfs", "gm", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationpacket", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationpackets", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationpkt", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationpkts", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationbrief", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationbriefs", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationbrf", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationbrfs", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationspacket", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationspackets", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationspkt", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationspkts", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationsbrief", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationsbriefs", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationsbrf", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmoperationsbrfs", "gm", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolpacket", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolpackets", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolpkt", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolpkts", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolbrief", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolbriefs", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolbrf", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolbrfs", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolspacket", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolspackets", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolspkt", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolspkts", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolsbrief", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolsbriefs", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolsbrf", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gmcontrolsbrfs", "gm", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteropspacket", "game", "master", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteropspackets", "game", "master", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteropspkt", "game", "master", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteropspkts", "game", "master", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteropsbrief", "game", "master", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteropsbriefs", "game", "master", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteropsbrf", "game", "master", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteropsbrfs", "game", "master", "ops", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationpacket", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationpackets", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationpkt", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationpkts", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationbrief", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationbriefs", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationbrf", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationbrfs", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationspacket", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationspackets", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationspkt", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationspkts", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationsbrief", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationsbriefs", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationsbrf", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperationsbrfs", "game", "master", "operation", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolpacket", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolpackets", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolpkt", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolpkts", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolbrief", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolbriefs", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolbrf", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolbrfs", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolspacket", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolspackets", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolspkt", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolspkts", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolsbrief", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolsbriefs", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolsbrf", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrolsbrfs", "game", "master", "control", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "workspacev4", "workspace", "v4");
        RewriteCompactContinuityMutationAlias(tokens, "workspacev4packet", "workspace", "v4", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "workspacev4packets", "workspace", "v4", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "workspacev4brief", "workspace", "v4", "brief");
        RewriteCompactContinuityMutationAlias(tokens, "workspacev4briefs", "workspace", "v4", "briefs");
        RewriteCompactContinuityMutationAlias(tokens, "campaignworkspacev4", "campaign", "workspace", "v4");
        RewriteCompactContinuityMutationAlias(tokens, "campaignworkspacev4packet", "campaign", "workspace", "v4", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignworkspacev4packets", "campaign", "workspace", "v4", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignworkspacev4brief", "campaign", "workspace", "v4", "brief");
        RewriteCompactContinuityMutationAlias(tokens, "campaignworkspacev4briefs", "campaign", "workspace", "v4", "briefs");
        RewriteCompactContinuityMutationAlias(tokens, "offlinereadiness", "offline", "readiness");
        RewriteCompactContinuityMutationAlias(tokens, "offlinereadinesses", "offline", "readiness");
        RewriteCompactContinuityMutationAlias(tokens, "travelreadiness", "travel", "readiness");
        RewriteCompactContinuityMutationAlias(tokens, "travelreadinesses", "travel", "readiness");
        RewriteCompactContinuityMutationAlias(tokens, "safehousereadiness", "safehouse", "readiness");
        RewriteCompactContinuityMutationAlias(tokens, "safehousereadinesses", "safehouse", "readiness");
        RewriteCompactContinuityMutationAlias(tokens, "offlinecache", "offline", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "offlinecaches", "offline", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "travelcache", "travel", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "travelcaches", "travel", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "safehousecache", "safehouse", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "safehousecaches", "safehouse", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "stalecache", "stale", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "stalecaches", "stale", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "staleofflinecache", "stale", "offline", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "staleofflinecaches", "stale", "offline", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "mobileofflinereadiness", "mobile", "offline", "readiness");
        RewriteCompactContinuityMutationAlias(tokens, "mobileofflinereadinesses", "mobile", "offline", "readiness");
        RewriteCompactContinuityMutationAlias(tokens, "mobiletravelreadiness", "mobile", "travel", "readiness");
        RewriteCompactContinuityMutationAlias(tokens, "mobiletravelreadinesses", "mobile", "travel", "readiness");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehousereadiness", "mobile", "safehouse", "readiness");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehousereadinesses", "mobile", "safehouse", "readiness");
        RewriteCompactContinuityMutationAlias(tokens, "mobileofflinecache", "mobile", "offline", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "mobileofflinecaches", "mobile", "offline", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "mobiletravelcache", "mobile", "travel", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "mobiletravelcaches", "mobile", "travel", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehousecache", "mobile", "safehouse", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehousecaches", "mobile", "safehouse", "cache");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehouse", "mobile", "safehouse");
        RewriteCompactContinuityMutationAlias(tokens, "mobilesafehouses", "mobile", "safehouse");
        RewriteCompactContinuityMutationAlias(tokens, "mobiletravel", "mobile", "travel");
        RewriteCompactContinuityMutationAlias(tokens, "mobiletravels", "mobile", "travel");
        RewriteCompactContinuityMutationAlias(tokens, "mobileoffline", "mobile", "offline");
        RewriteCompactContinuityMutationAlias(tokens, "mobileofflines", "mobile", "offline");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanion", "mobile", "companion");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanions", "mobile", "companion");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionreturnloop", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionreturnloops", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionsreturnloop", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionsreturnloops", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionreturnlane", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionreturnlanes", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionsreturnlane", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionsreturnlanes", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanion", "campaign", "mobile", "companion");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanions", "campaign", "mobile", "companion");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionreturnloop", "campaign", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionreturnloops", "campaign", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionsreturnloop", "campaign", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionsreturnloops", "campaign", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionreturnlane", "campaign", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionreturnlanes", "campaign", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionsreturnlane", "campaign", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionsreturnlanes", "campaign", "mobile", "companion", "return", "loop");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionreturnpacket", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionreturnpackets", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionreturnpkt", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionreturnpkts", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionsreturnpacket", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionsreturnpackets", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionsreturnpkt", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionsreturnpkts", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionreturnbrief", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionreturnbriefs", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionreturnbrf", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionreturnbrfs", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionsreturnbrief", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionsreturnbriefs", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionsreturnbrf", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "mobilecompanionsreturnbrfs", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionreturnpacket", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionreturnpackets", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionreturnpkt", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionreturnpkts", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionsreturnpacket", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionsreturnpackets", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionsreturnpkt", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionsreturnpkts", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionreturnbrief", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionreturnbriefs", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionreturnbrf", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionreturnbrfs", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionsreturnbrief", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionsreturnbriefs", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionsreturnbrf", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "campaignmobilecompanionsreturnbrfs", "campaign", "mobile", "companion", "return", "packet");
        RewriteCompactContinuityMutationAlias(tokens, "gamemaster", "game", "master");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasters", "game", "master");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasterop", "game", "master", "op");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasterops", "game", "master", "ops");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperation", "game", "master", "operation");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasteroperations", "game", "master", "operations");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrol", "game", "master", "control");
        RewriteCompactContinuityMutationAlias(tokens, "gamemastercontrols", "game", "master", "controls");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasterctrl", "game", "master", "ctrl");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasterctl", "game", "master", "ctl");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasterctrls", "game", "master", "ctrls");
        RewriteCompactContinuityMutationAlias(tokens, "gamemasterctls", "game", "master", "ctls");

        if ((tokens.Contains("mobile") || tokens.Contains("campaign"))
            && (tokens.Contains("companion") || tokens.Contains("companions")))
        {
            tokens.Remove("companion");
            tokens.Remove("companions");
            tokens.Add("mobile");
            tokens.Add("offline");
            tokens.Add("travel");
            tokens.Add("safehouse");
        }

        if ((tokens.Contains("gm") && tokens.Contains("ops"))
            || (tokens.Contains("gm") && tokens.Contains("op"))
            || (tokens.Contains("gm") && tokens.Contains("operation"))
            || (tokens.Contains("gm") && tokens.Contains("operations")))
        {
            tokens.Remove("gm");
            tokens.Remove("ops");
            tokens.Remove("op");
            tokens.Remove("operation");
            tokens.Remove("operations");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if ((tokens.Contains("game") && tokens.Contains("master"))
            && (tokens.Contains("ops")
                || tokens.Contains("op")
                || tokens.Contains("operation")
                || tokens.Contains("operations")
                || tokens.Contains("control")
                || tokens.Contains("controls")
                || tokens.Contains("ctrl")
                || tokens.Contains("ctl")
                || tokens.Contains("ctls")
                || tokens.Contains("ctrls")))
        {
            tokens.Remove("game");
            tokens.Remove("master");
            tokens.Remove("ops");
            tokens.Remove("op");
            tokens.Remove("operation");
            tokens.Remove("operations");
            tokens.Remove("control");
            tokens.Remove("controls");
            tokens.Remove("ctrl");
            tokens.Remove("ctl");
            tokens.Remove("ctls");
            tokens.Remove("ctrls");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if ((tokens.Contains("event") && tokens.Contains("ops")) || (tokens.Contains("event") && tokens.Contains("op")))
        {
            tokens.Remove("ops");
            tokens.Remove("op");
            tokens.Add("eventcontrol");
            tokens.Add("operation");
        }

        if ((tokens.Contains("season") && tokens.Contains("ops")) || (tokens.Contains("season") && tokens.Contains("op")))
        {
            tokens.Remove("ops");
            tokens.Remove("op");
            tokens.Add("operation");
        }

        if ((tokens.Contains("league") && tokens.Contains("ops")) || (tokens.Contains("league") && tokens.Contains("op")))
        {
            tokens.Remove("league");
            tokens.Remove("ops");
            tokens.Remove("op");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if ((tokens.Contains("league") && tokens.Contains("operations")) || (tokens.Contains("league") && tokens.Contains("operation")))
        {
            tokens.Remove("league");
            tokens.Remove("operations");
            tokens.Remove("operation");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if ((tokens.Contains("community") && tokens.Contains("operations")) || (tokens.Contains("community") && tokens.Contains("operation")))
        {
            tokens.Remove("community");
            tokens.Remove("operations");
            tokens.Remove("operation");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if ((tokens.Contains("community") && tokens.Contains("ops")) || (tokens.Contains("community") && tokens.Contains("op")))
        {
            tokens.Remove("community");
            tokens.Remove("ops");
            tokens.Remove("op");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if ((tokens.Contains("league") && tokens.Contains("ctrl"))
            || (tokens.Contains("league") && tokens.Contains("ctl"))
            || (tokens.Contains("league") && tokens.Contains("control"))
            || (tokens.Contains("league") && tokens.Contains("controls"))
            || (tokens.Contains("league") && tokens.Contains("ctls"))
            || (tokens.Contains("league") && tokens.Contains("ctrls")))
        {
            tokens.Remove("league");
            tokens.Remove("ctrl");
            tokens.Remove("ctl");
            tokens.Remove("control");
            tokens.Remove("controls");
            tokens.Remove("ctls");
            tokens.Remove("ctrls");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if ((tokens.Contains("community") && tokens.Contains("ctrl"))
            || (tokens.Contains("community") && tokens.Contains("ctl"))
            || (tokens.Contains("community") && tokens.Contains("control"))
            || (tokens.Contains("community") && tokens.Contains("controls"))
            || (tokens.Contains("community") && tokens.Contains("ctls"))
            || (tokens.Contains("community") && tokens.Contains("ctrls")))
        {
            tokens.Remove("community");
            tokens.Remove("ctrl");
            tokens.Remove("ctl");
            tokens.Remove("control");
            tokens.Remove("controls");
            tokens.Remove("ctls");
            tokens.Remove("ctrls");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("event")
            && (tokens.Contains("ctrl")
                || tokens.Contains("ctl")
                || tokens.Contains("ctls")
                || tokens.Contains("ctrls")))
        {
            tokens.Remove("ctrl");
            tokens.Remove("ctl");
            tokens.Remove("ctls");
            tokens.Remove("ctrls");
            tokens.Add("eventcontrol");
        }

        if (tokens.Contains("event") && (tokens.Contains("control") || tokens.Contains("controls")))
        {
            tokens.Remove("control");
            tokens.Remove("controls");
            tokens.Add("eventcontrol");
            tokens.Add("operation");
        }

        if (tokens.Contains("season")
            && (tokens.Contains("ctrl")
                || tokens.Contains("ctl")
                || tokens.Contains("ctls")
                || tokens.Contains("ctrls")))
        {
            tokens.Remove("ctrl");
            tokens.Remove("ctl");
            tokens.Remove("ctls");
            tokens.Remove("ctrls");
            tokens.Add("seasoncontrol");
        }

        if (tokens.Contains("season") && tokens.Contains("control"))
        {
            tokens.Remove("control");
            tokens.Add("eventcontrol");
            tokens.Add("operation");
        }

        if (tokens.Contains("eventctrl"))
        {
            tokens.Remove("eventctrl");
            tokens.Add("eventcontrol");
        }

        if (tokens.Contains("eventctl"))
        {
            tokens.Remove("eventctl");
            tokens.Add("eventcontrol");
        }

        if (tokens.Contains("eventctls"))
        {
            tokens.Remove("eventctls");
            tokens.Add("eventcontrol");
        }

        if (tokens.Contains("eventctrls"))
        {
            tokens.Remove("eventctrls");
            tokens.Add("eventcontrol");
        }

        if (tokens.Contains("eventcontrols"))
        {
            tokens.Remove("eventcontrols");
            tokens.Add("eventcontrol");
        }

        if (tokens.Contains("seasonctrl"))
        {
            tokens.Remove("seasonctrl");
            tokens.Add("seasoncontrol");
        }

        if (tokens.Contains("seasonctl"))
        {
            tokens.Remove("seasonctl");
            tokens.Add("seasoncontrol");
        }

        if (tokens.Contains("seasonctls"))
        {
            tokens.Remove("seasonctls");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("seasonctrls"))
        {
            tokens.Remove("seasonctrls");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("gmops"))
        {
            tokens.Remove("gmops");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("gmop"))
        {
            tokens.Remove("gmop");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("gmoperation"))
        {
            tokens.Remove("gmoperation");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("gmoperations"))
        {
            tokens.Remove("gmoperations");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("gmcontrol"))
        {
            tokens.Remove("gmcontrol");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("gmcontrols"))
        {
            tokens.Remove("gmcontrols");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("gmctrl"))
        {
            tokens.Remove("gmctrl");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("gmctl"))
        {
            tokens.Remove("gmctl");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("gmctls"))
        {
            tokens.Remove("gmctls");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("gmctrls"))
        {
            tokens.Remove("gmctrls");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("gm")
            && (tokens.Contains("control")
                || tokens.Contains("controls")
                || tokens.Contains("ctrl")
                || tokens.Contains("ctl")
                || tokens.Contains("ctls")
                || tokens.Contains("ctrls")))
        {
            tokens.Remove("gm");
            tokens.Remove("control");
            tokens.Remove("controls");
            tokens.Remove("ctrl");
            tokens.Remove("ctl");
            tokens.Remove("ctls");
            tokens.Remove("ctrls");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("eventops"))
        {
            tokens.Remove("eventops");
            tokens.Add("eventcontrol");
            tokens.Add("event");
            tokens.Add("operation");
        }

        if (tokens.Contains("eventop"))
        {
            tokens.Remove("eventop");
            tokens.Add("eventcontrol");
            tokens.Add("event");
            tokens.Add("operation");
        }

        if (tokens.Contains("eventoperation"))
        {
            tokens.Remove("eventoperation");
            tokens.Add("eventcontrol");
            tokens.Add("event");
            tokens.Add("operation");
        }

        if (tokens.Contains("eventoperations"))
        {
            tokens.Remove("eventoperations");
            tokens.Add("eventcontrol");
            tokens.Add("event");
            tokens.Add("operation");
        }

        if (tokens.Contains("crewtransfer"))
        {
            tokens.Remove("crewtransfer");
            tokens.Add("crewhandoff");
        }

        if (tokens.Contains("crewtransfers"))
        {
            tokens.Remove("crewtransfers");
            tokens.Add("crewhandoff");
        }

        if (tokens.Contains("crew") && (tokens.Contains("transfer") || tokens.Contains("transfers")))
        {
            tokens.Remove("transfer");
            tokens.Remove("transfers");
            tokens.Add("handoff");
        }

        if (tokens.Contains("crew") && tokens.Contains("handoffs"))
        {
            tokens.Remove("handoffs");
            tokens.Add("handoff");
        }

        if (tokens.Contains("crewmove"))
        {
            tokens.Remove("crewmove");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("crewshift"))
        {
            tokens.Remove("crewshift");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("crewswap"))
        {
            tokens.Remove("crewswap");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("crewmovement"))
        {
            tokens.Remove("crewmovement");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("crewmoves"))
        {
            tokens.Remove("crewmoves");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("crewshifts"))
        {
            tokens.Remove("crewshifts");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("crewswaps"))
        {
            tokens.Remove("crewswaps");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("crewmovements"))
        {
            tokens.Remove("crewmovements");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("rostermoves"))
        {
            tokens.Remove("rostermoves");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("rosterswap"))
        {
            tokens.Remove("rosterswap");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("rostershift"))
        {
            tokens.Remove("rostershift");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("rosterswaps"))
        {
            tokens.Remove("rosterswaps");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("rostershifts"))
        {
            tokens.Remove("rostershifts");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("rostermovement"))
        {
            tokens.Remove("rostermovement");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("rostermovements"))
        {
            tokens.Remove("rostermovements");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("crew") && tokens.Contains("moves"))
        {
            tokens.Remove("moves");
            tokens.Add("move");
        }

        if (tokens.Contains("crew") && (tokens.Contains("shift") || tokens.Contains("shifts")))
        {
            tokens.Remove("shift");
            tokens.Remove("shifts");
            tokens.Add("move");
        }

        if (tokens.Contains("crew") && (tokens.Contains("swap") || tokens.Contains("swaps")))
        {
            tokens.Remove("swap");
            tokens.Remove("swaps");
            tokens.Add("move");
        }

        if (tokens.Contains("crew") && (tokens.Contains("movement") || tokens.Contains("movements")))
        {
            tokens.Remove("movement");
            tokens.Remove("movements");
            tokens.Add("move");
        }

        if (tokens.Contains("rostertransfer"))
        {
            tokens.Remove("rostertransfer");
            tokens.Add("roster");
            tokens.Add("move");
        }

        if (tokens.Contains("rostertransfers"))
        {
            tokens.Remove("rostertransfers");
            tokens.Add("roster");
            tokens.Add("move");
        }

        if (tokens.Contains("rosterhandoff"))
        {
            tokens.Remove("rosterhandoff");
            tokens.Add("roster");
            tokens.Add("handoff");
        }

        if (tokens.Contains("roster") && (tokens.Contains("transfer") || tokens.Contains("transfers")))
        {
            tokens.Remove("transfer");
            tokens.Remove("transfers");
            tokens.Add("move");
        }

        if (tokens.Contains("rosterhandoffs"))
        {
            tokens.Remove("rosterhandoffs");
            tokens.Add("roster");
            tokens.Add("handoff");
        }

        if (tokens.Contains("rosterhandover"))
        {
            tokens.Remove("rosterhandover");
            tokens.Add("roster");
            tokens.Add("handoff");
        }

        if (tokens.Contains("rosterhandovers"))
        {
            tokens.Remove("rosterhandovers");
            tokens.Add("roster");
            tokens.Add("handoff");
        }

        if (tokens.Contains("roster") && tokens.Contains("handoffs"))
        {
            tokens.Remove("handoffs");
            tokens.Add("handoff");
        }

        if (tokens.Contains("crewhandoffs"))
        {
            tokens.Remove("crewhandoffs");
            tokens.Add("crewhandoff");
        }

        if (tokens.Contains("crewhandover"))
        {
            tokens.Remove("crewhandover");
            tokens.Add("crewhandoff");
        }

        if (tokens.Contains("crewhandovers"))
        {
            tokens.Remove("crewhandovers");
            tokens.Add("crewhandoff");
        }

        if (tokens.Contains("roster") && tokens.Contains("moves"))
        {
            tokens.Remove("moves");
            tokens.Add("move");
        }

        if (tokens.Contains("crew") && (tokens.Contains("handover") || tokens.Contains("handovers")))
        {
            tokens.Remove("handover");
            tokens.Remove("handovers");
            tokens.Add("handoff");
        }

        if (tokens.Contains("roster") && (tokens.Contains("handover") || tokens.Contains("handovers")))
        {
            tokens.Remove("handover");
            tokens.Remove("handovers");
            tokens.Add("handoff");
        }

        if (tokens.Contains("roster") && (tokens.Contains("shift") || tokens.Contains("shifts")))
        {
            tokens.Remove("shift");
            tokens.Remove("shifts");
            tokens.Add("move");
        }

        if (tokens.Contains("roster") && (tokens.Contains("swap") || tokens.Contains("swaps")))
        {
            tokens.Remove("swap");
            tokens.Remove("swaps");
            tokens.Add("move");
        }

        if (tokens.Contains("roster") && (tokens.Contains("movement") || tokens.Contains("movements")))
        {
            tokens.Remove("movement");
            tokens.Remove("movements");
            tokens.Add("move");
        }

        if (tokens.Contains("seasonops"))
        {
            tokens.Remove("seasonops");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("seasonop"))
        {
            tokens.Remove("seasonop");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("seasonoperation"))
        {
            tokens.Remove("seasonoperation");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("seasonoperations"))
        {
            tokens.Remove("seasonoperations");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("seasoncontrol"))
        {
            tokens.Remove("seasoncontrol");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("seasoncontrols"))
        {
            tokens.Remove("seasoncontrols");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leagueops"))
        {
            tokens.Remove("leagueops");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leagueop"))
        {
            tokens.Remove("leagueop");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leagueoperation"))
        {
            tokens.Remove("leagueoperation");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leagueoperations"))
        {
            tokens.Remove("leagueoperations");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communityops"))
        {
            tokens.Remove("communityops");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communityop"))
        {
            tokens.Remove("communityop");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communityoperation"))
        {
            tokens.Remove("communityoperation");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communityoperations"))
        {
            tokens.Remove("communityoperations");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leaguectrl"))
        {
            tokens.Remove("leaguectrl");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leaguectl"))
        {
            tokens.Remove("leaguectl");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leaguectls"))
        {
            tokens.Remove("leaguectls");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leaguectrls"))
        {
            tokens.Remove("leaguectrls");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leaguecontrol"))
        {
            tokens.Remove("leaguecontrol");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leaguecontrols"))
        {
            tokens.Remove("leaguecontrols");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communityctrl"))
        {
            tokens.Remove("communityctrl");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communityctl"))
        {
            tokens.Remove("communityctl");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communityctls"))
        {
            tokens.Remove("communityctls");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communityctrls"))
        {
            tokens.Remove("communityctrls");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communitycontrol"))
        {
            tokens.Remove("communitycontrol");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communitycontrols"))
        {
            tokens.Remove("communitycontrols");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("nextsessionreturn") || tokens.Contains("nextsessionreturns"))
        {
            tokens.Remove("nextsessionreturn");
            tokens.Remove("nextsessionreturns");
            tokens.Add("next");
            tokens.Add("session");
            tokens.Add("return");
        }

        if (tokens.Contains("nextsessionsreturn") || tokens.Contains("nextsessionsreturns"))
        {
            tokens.Remove("nextsessionsreturn");
            tokens.Remove("nextsessionsreturns");
            tokens.Add("next");
            tokens.Add("session");
            tokens.Add("return");
        }

        if (tokens.Contains("nextsessionreturnloop") || tokens.Contains("nextsessionreturnloops"))
        {
            tokens.Remove("nextsessionreturnloop");
            tokens.Remove("nextsessionreturnloops");
            tokens.Add("next");
            tokens.Add("session");
            tokens.Add("return");
            tokens.Add("loop");
        }

        if (tokens.Contains("nextsessionsreturnloop") || tokens.Contains("nextsessionsreturnloops"))
        {
            tokens.Remove("nextsessionsreturnloop");
            tokens.Remove("nextsessionsreturnloops");
            tokens.Add("next");
            tokens.Add("session");
            tokens.Add("return");
            tokens.Add("loop");
        }

        if (tokens.Contains("nextsessionreturnlane") || tokens.Contains("nextsessionreturnlanes"))
        {
            tokens.Remove("nextsessionreturnlane");
            tokens.Remove("nextsessionreturnlanes");
            tokens.Add("next");
            tokens.Add("session");
            tokens.Add("return");
            tokens.Add("loop");
        }

        if (tokens.Contains("nextsessionsreturnlane") || tokens.Contains("nextsessionsreturnlanes"))
        {
            tokens.Remove("nextsessionsreturnlane");
            tokens.Remove("nextsessionsreturnlanes");
            tokens.Add("next");
            tokens.Add("session");
            tokens.Add("return");
            tokens.Add("loop");
        }

        if (tokens.Contains("nextsessionloop") || tokens.Contains("nextsessionloops"))
        {
            tokens.Remove("nextsessionloop");
            tokens.Remove("nextsessionloops");
            tokens.Add("next");
            tokens.Add("session");
            tokens.Add("return");
            tokens.Add("loop");
        }

        if (tokens.Contains("sessionreturn") || tokens.Contains("sessionreturns"))
        {
            tokens.Remove("sessionreturn");
            tokens.Remove("sessionreturns");
            tokens.Add("session");
            tokens.Add("return");
        }

        if (tokens.Contains("sessionreturnloop") || tokens.Contains("sessionreturnloops"))
        {
            tokens.Remove("sessionreturnloop");
            tokens.Remove("sessionreturnloops");
            tokens.Add("session");
            tokens.Add("return");
            tokens.Add("loop");
        }

        if (tokens.Contains("sessionreturnlane") || tokens.Contains("sessionreturnlanes"))
        {
            tokens.Remove("sessionreturnlane");
            tokens.Remove("sessionreturnlanes");
            tokens.Add("session");
            tokens.Add("return");
            tokens.Add("loop");
        }

        if (tokens.Contains("nextsession") || tokens.Contains("nextsessions"))
        {
            tokens.Remove("nextsession");
            tokens.Remove("nextsessions");
            tokens.Add("next");
            tokens.Add("session");
            tokens.Add("return");
        }

        if (tokens.Contains("returnloop") || tokens.Contains("returnloops"))
        {
            tokens.Remove("returnloop");
            tokens.Remove("returnloops");
            tokens.Add("return");
            tokens.Add("loop");
            tokens.Add("session");
        }

        if (tokens.Contains("returnlane") || tokens.Contains("returnlanes"))
        {
            tokens.Remove("returnlane");
            tokens.Remove("returnlanes");
            tokens.Add("return");
            tokens.Add("loop");
            tokens.Add("session");
        }

        if ((tokens.Contains("return") || tokens.Contains("session")) && tokens.Contains("lane"))
        {
            tokens.Remove("lane");
            tokens.Add("loop");
        }

        if ((tokens.Contains("return") || tokens.Contains("session")) && tokens.Contains("lanes"))
        {
            tokens.Remove("lanes");
            tokens.Add("loop");
        }

        if ((tokens.Contains("return") || tokens.Contains("session")) && tokens.Contains("loops"))
        {
            tokens.Remove("loops");
            tokens.Add("loop");
        }

        if ((tokens.Contains("workspace") || tokens.Contains("workspaces"))
            && (tokens.Contains("v4") || tokens.Contains("4")))
        {
            tokens.Remove("workspace");
            tokens.Remove("workspaces");
            tokens.Remove("v4");
            tokens.Remove("4");
            tokens.Remove("brief");
            tokens.Remove("briefs");
            tokens.Add("campaign");
            tokens.Add("return");
            tokens.Add("packet");
        }

        if (tokens.Contains("sessions")
            && (tokens.Contains("next")
                || tokens.Contains("return")
                || tokens.Contains("loop")
                || tokens.Contains("loops")))
        {
            tokens.Remove("sessions");
            tokens.Add("session");
        }

        if ((tokens.Contains("op") && tokens.Contains("for"))
            || (tokens.Contains("op") && tokens.Contains("fors"))
            || (tokens.Contains("op") && tokens.Contains("force"))
            || (tokens.Contains("op") && tokens.Contains("forces")))
        {
            tokens.Remove("op");
            tokens.Remove("for");
            tokens.Remove("fors");
            tokens.Remove("force");
            tokens.Remove("forces");
            tokens.Add("opfor");
        }

        if (tokens.Contains("opforce"))
        {
            tokens.Remove("opforce");
            tokens.Add("opfor");
        }

        if (tokens.Contains("opforces"))
        {
            tokens.Remove("opforces");
            tokens.Add("opfor");
        }

        if (tokens.Contains("opfors"))
        {
            tokens.Remove("opfors");
            tokens.Add("opfor");
        }

        if (tokens.Contains("opfor"))
        {
            tokens.Remove("opfor");
            tokens.Add("opposition");
        }

        if (tokens.Contains("oppositionwindow") || tokens.Contains("oppositionwindows"))
        {
            tokens.Remove("oppositionwindow");
            tokens.Remove("oppositionwindows");
            tokens.Add("opposition");
        }

        if (tokens.Contains("oppositioncontrol") || tokens.Contains("oppositioncontrols"))
        {
            tokens.Remove("oppositioncontrol");
            tokens.Remove("oppositioncontrols");
            tokens.Add("opposition");
        }

        if (tokens.Contains("sessionlogs"))
        {
            tokens.Remove("sessionlogs");
            tokens.Add("session");
            tokens.Add("log");
        }

        if (tokens.Contains("session") && tokens.Contains("logs"))
        {
            tokens.Remove("logs");
            tokens.Add("log");
        }

        if (tokens.Contains("sessionlog")
            || tokens.Contains("sessionlogs")
            || (tokens.Contains("session") && tokens.Contains("log"))
            || (tokens.Contains("session") && tokens.Contains("logs")))
        {
            tokens.Remove("sessionlog");
            tokens.Remove("sessionlogs");
            tokens.Remove("log");
            tokens.Remove("logs");
            tokens.Add("session");
            tokens.Add("diary");
        }

        if (tokens.Contains("diaries"))
        {
            tokens.Remove("diaries");
            tokens.Add("diary");
        }

        if (tokens.Contains("journals"))
        {
            tokens.Remove("journals");
            tokens.Add("journal");
            tokens.Add("diary");
        }

        if (tokens.Contains("off") && (tokens.Contains("line") || tokens.Contains("lines")))
        {
            tokens.Remove("off");
            tokens.Remove("line");
            tokens.Remove("lines");
            tokens.Add("offline");
        }

        if (tokens.Contains("safe") && (tokens.Contains("house") || tokens.Contains("houses")))
        {
            tokens.Remove("safe");
            tokens.Remove("house");
            tokens.Remove("houses");
            tokens.Add("safehouse");
        }

        bool hasCampaignRelationshipOrDiaryScope =
            tokens.Contains("contact")
            || tokens.Contains("contacts")
            || tokens.Contains("connection")
            || tokens.Contains("connections")
            || tokens.Contains("relationship")
            || tokens.Contains("relationships")
            || tokens.Contains("faction")
            || tokens.Contains("factions")
            || tokens.Contains("heat")
            || tokens.Contains("heats")
            || tokens.Contains("diary")
            || tokens.Contains("diaries")
            || tokens.Contains("journal")
            || tokens.Contains("journals")
            || tokens.Contains("sessionlog")
            || tokens.Contains("sessionlogs")
            || (tokens.Contains("session") && tokens.Contains("log"))
            || (tokens.Contains("session") && tokens.Contains("logs"));
        if (hasCampaignRelationshipOrDiaryScope)
        {
            tokens.Remove("update");
            tokens.Remove("updates");
            tokens.Remove("updated");
            tokens.Remove("updating");
            tokens.Remove("change");
            tokens.Remove("changes");
            tokens.Remove("changed");
            tokens.Remove("changing");
            tokens.Remove("delta");
            tokens.Remove("deltas");
            tokens.Remove("shift");
            tokens.Remove("shifts");
            tokens.Remove("shifted");
            tokens.Remove("shifting");
            tokens.Remove("mutation");
            tokens.Remove("mutations");
        }

        if (tokens.Contains("safehouses"))
        {
            tokens.Remove("safehouses");
            tokens.Add("safehouse");
        }

        if (tokens.Contains("travels"))
        {
            tokens.Remove("travels");
            tokens.Add("travel");
        }

        if (tokens.Contains("offlines"))
        {
            tokens.Remove("offlines");
            tokens.Add("offline");
        }

        bool hasTravelOfflineScope =
            tokens.Contains("travel")
            || tokens.Contains("safehouse")
            || tokens.Contains("offline")
            || tokens.Contains("prefetch")
            || tokens.Contains("travelprefetch")
            || tokens.Contains("travelcache")
            || tokens.Contains("offlinecache")
            || tokens.Contains("safehousecache");
        if (tokens.Contains("mobile")
            && (tokens.Contains("travel")
                || tokens.Contains("safehouse")
                || tokens.Contains("offline")
                || tokens.Contains("prefetch")
                || tokens.Contains("travelprefetch")))
        {
            tokens.Remove("mobile");
            hasTravelOfflineScope = true;
        }

        if (hasTravelOfflineScope)
        {
            tokens.Remove("readiness");
            tokens.Remove("readinesses");
            tokens.Remove("ready");
            tokens.Remove("stale");
            tokens.Remove("staleness");
            tokens.Remove("cache");
            tokens.Remove("caches");
            tokens.Remove("cached");
            tokens.Remove("caching");
        }

        if (tokens.Contains("downtimes"))
        {
            tokens.Remove("downtimes");
            tokens.Add("downtime");
        }

        if (tokens.Contains("aftermaths"))
        {
            tokens.Remove("aftermaths");
            tokens.Add("aftermath");
        }

        if (tokens.Contains("debrief"))
        {
            tokens.Remove("debrief");
            tokens.Add("recap");
        }

        if (tokens.Contains("debriefs"))
        {
            tokens.Remove("debriefs");
            tokens.Add("recap");
        }

        if (tokens.Contains("debriefing"))
        {
            tokens.Remove("debriefing");
            tokens.Add("recap");
        }

        if (tokens.Contains("debriefings"))
        {
            tokens.Remove("debriefings");
            tokens.Add("recap");
        }

        if (tokens.Contains("debriefed"))
        {
            tokens.Remove("debriefed");
            tokens.Add("recap");
        }

        if (tokens.Contains("de")
            && (tokens.Contains("brief")
                || tokens.Contains("briefs")
                || tokens.Contains("briefed")
                || tokens.Contains("briefing")
                || tokens.Contains("briefings")))
        {
            tokens.Remove("de");
            tokens.Remove("brief");
            tokens.Remove("briefs");
            tokens.Remove("briefed");
            tokens.Remove("briefing");
            tokens.Remove("briefings");
            tokens.Add("recap");
        }

        if (tokens.Contains("outbrief"))
        {
            tokens.Remove("outbrief");
            tokens.Add("recap");
        }

        if (tokens.Contains("outbriefs"))
        {
            tokens.Remove("outbriefs");
            tokens.Add("recap");
        }

        if (tokens.Contains("outbriefed"))
        {
            tokens.Remove("outbriefed");
            tokens.Add("recap");
        }

        if (tokens.Contains("outbriefing"))
        {
            tokens.Remove("outbriefing");
            tokens.Add("recap");
        }

        if (tokens.Contains("outbriefings"))
        {
            tokens.Remove("outbriefings");
            tokens.Add("recap");
        }

        if (tokens.Contains("postmortem"))
        {
            tokens.Remove("postmortem");
            tokens.Add("recap");
        }

        if (tokens.Contains("postmortems"))
        {
            tokens.Remove("postmortems");
            tokens.Add("recap");
        }

        if (tokens.Contains("postsession"))
        {
            tokens.Remove("postsession");
            tokens.Add("recap");
        }

        if (tokens.Contains("postsessions"))
        {
            tokens.Remove("postsessions");
            tokens.Add("recap");
        }

        if (tokens.Contains("post") && (tokens.Contains("session") || tokens.Contains("sessions")))
        {
            tokens.Remove("post");
            tokens.Remove("session");
            tokens.Remove("sessions");
            tokens.Add("recap");
        }

        if (tokens.Contains("postrun"))
        {
            tokens.Remove("postrun");
            tokens.Add("recap");
        }

        if (tokens.Contains("postruns"))
        {
            tokens.Remove("postruns");
            tokens.Add("recap");
        }

        if (tokens.Contains("post") && (tokens.Contains("run") || tokens.Contains("runs")))
        {
            tokens.Remove("post");
            tokens.Remove("run");
            tokens.Remove("runs");
            tokens.Add("recap");
        }

        if (tokens.Contains("postgame"))
        {
            tokens.Remove("postgame");
            tokens.Add("recap");
        }

        if (tokens.Contains("postgames"))
        {
            tokens.Remove("postgames");
            tokens.Add("recap");
        }

        if (tokens.Contains("post") && (tokens.Contains("game") || tokens.Contains("games")))
        {
            tokens.Remove("post");
            tokens.Remove("game");
            tokens.Remove("games");
            tokens.Add("recap");
        }

        if (tokens.Contains("post") && (tokens.Contains("mortem") || tokens.Contains("mortems")))
        {
            tokens.Remove("post");
            tokens.Remove("mortem");
            tokens.Remove("mortems");
            tokens.Add("recap");
        }

        if (tokens.Contains("afteraction"))
        {
            tokens.Remove("afteraction");
            tokens.Add("recap");
        }

        if (tokens.Contains("afteractions"))
        {
            tokens.Remove("afteractions");
            tokens.Add("recap");
        }

        if (tokens.Contains("afteractionreport"))
        {
            tokens.Remove("afteractionreport");
            tokens.Add("recap");
        }

        if (tokens.Contains("afteractionreports"))
        {
            tokens.Remove("afteractionreports");
            tokens.Add("recap");
        }

        if (tokens.Contains("afteractionreview"))
        {
            tokens.Remove("afteractionreview");
            tokens.Add("recap");
        }

        if (tokens.Contains("afteractionreviews"))
        {
            tokens.Remove("afteractionreviews");
            tokens.Add("recap");
        }

        if (tokens.Contains("after") && (tokens.Contains("action") || tokens.Contains("actions")))
        {
            tokens.Remove("after");
            tokens.Remove("action");
            tokens.Remove("actions");
            tokens.Remove("report");
            tokens.Remove("reports");
            tokens.Remove("review");
            tokens.Remove("reviews");
            tokens.Add("recap");
        }

        if (tokens.Contains("recaps"))
        {
            tokens.Remove("recaps");
            tokens.Add("recap");
        }

        if (tokens.Contains("aar"))
        {
            tokens.Remove("aar");
            tokens.Add("recap");
        }

        if (tokens.Contains("aars"))
        {
            tokens.Remove("aars");
            tokens.Add("recap");
        }

        if (tokens.Contains("retro"))
        {
            tokens.Remove("retro");
            tokens.Add("recap");
        }

        if (tokens.Contains("retros"))
        {
            tokens.Remove("retros");
            tokens.Add("recap");
        }

        if (tokens.Contains("retrospective"))
        {
            tokens.Remove("retrospective");
            tokens.Add("recap");
        }

        if (tokens.Contains("retrospectives"))
        {
            tokens.Remove("retrospectives");
            tokens.Add("recap");
        }

        if (tokens.Contains("hotwash"))
        {
            tokens.Remove("hotwash");
            tokens.Add("recap");
        }

        if (tokens.Contains("hotwashes"))
        {
            tokens.Remove("hotwashes");
            tokens.Add("recap");
        }

        if (tokens.Contains("lessonlearned"))
        {
            tokens.Remove("lessonlearned");
            tokens.Add("recap");
        }

        if (tokens.Contains("lessonslearned"))
        {
            tokens.Remove("lessonslearned");
            tokens.Add("recap");
        }

        if (tokens.Contains("lessonlearnt"))
        {
            tokens.Remove("lessonlearnt");
            tokens.Add("recap");
        }

        if (tokens.Contains("lessonslearnt"))
        {
            tokens.Remove("lessonslearnt");
            tokens.Add("recap");
        }

        if (tokens.Contains("hot") && (tokens.Contains("wash") || tokens.Contains("washes")))
        {
            tokens.Remove("hot");
            tokens.Remove("wash");
            tokens.Remove("washes");
            tokens.Add("recap");
        }

        if (tokens.Contains("out") && (tokens.Contains("brief") || tokens.Contains("briefs") || tokens.Contains("briefed") || tokens.Contains("briefing") || tokens.Contains("briefings")))
        {
            tokens.Remove("out");
            tokens.Remove("brief");
            tokens.Remove("briefs");
            tokens.Remove("briefed");
            tokens.Remove("briefing");
            tokens.Remove("briefings");
            tokens.Add("recap");
        }

        if ((tokens.Contains("lesson") || tokens.Contains("lessons")) && tokens.Contains("learned"))
        {
            tokens.Remove("lesson");
            tokens.Remove("lessons");
            tokens.Remove("learned");
            tokens.Add("recap");
        }

        if ((tokens.Contains("lesson") || tokens.Contains("lessons")) && tokens.Contains("learnt"))
        {
            tokens.Remove("lesson");
            tokens.Remove("lessons");
            tokens.Remove("learnt");
            tokens.Add("recap");
        }

        if (tokens.Contains("returns"))
        {
            tokens.Remove("returns");
            tokens.Add("return");
        }

        if (tokens.Contains("memories"))
        {
            tokens.Remove("memories");
            tokens.Add("memory");
        }

        if (tokens.Contains("archives"))
        {
            tokens.Remove("archives");
            tokens.Add("archive");
        }

        if (tokens.Contains("histories"))
        {
            tokens.Remove("histories");
            tokens.Add("history");
        }

        if (tokens.Contains("lifestyles"))
        {
            tokens.Remove("lifestyles");
            tokens.Add("lifestyle");
        }

        if (tokens.Contains("licenses"))
        {
            tokens.Remove("licenses");
            tokens.Add("license");
        }

        if (tokens.Contains("licences"))
        {
            tokens.Remove("licences");
            tokens.Add("license");
        }

        if (tokens.Contains("sins"))
        {
            tokens.Remove("sins");
            tokens.Add("sin");
        }

        if (tokens.Contains("timelines"))
        {
            tokens.Remove("timelines");
            tokens.Add("timeline");
        }

        if (tokens.Contains("ledgers"))
        {
            tokens.Remove("ledgers");
            tokens.Add("ledger");
        }

        if (tokens.Contains("connections"))
        {
            tokens.Remove("connections");
            tokens.Add("connection");
        }

        if (tokens.Contains("packets"))
        {
            tokens.Remove("packets");
            tokens.Add("packet");
        }

        if (tokens.Contains("oppositions"))
        {
            tokens.Remove("oppositions");
            tokens.Add("opposition");
        }

        if (tokens.Contains("contacts"))
        {
            tokens.Remove("contacts");
            tokens.Add("connection");
        }

        if (tokens.Contains("contact"))
        {
            tokens.Remove("contact");
            tokens.Add("connection");
        }

        if (tokens.Contains("relationships"))
        {
            tokens.Remove("relationships");
            tokens.Add("relationship");
        }

        if (tokens.Contains("factions"))
        {
            tokens.Remove("factions");
            tokens.Add("faction");
        }

        if (tokens.Contains("heats"))
        {
            tokens.Remove("heats");
            tokens.Add("heat");
        }
    }

    private static void RewriteCompactContinuityMutationAlias(
        HashSet<string> tokens,
        string compactToken,
        params string[] expandedTokens)
    {
        if (!tokens.Contains(compactToken))
        {
            return;
        }

        tokens.Remove(compactToken);
        foreach (string token in expandedTokens)
        {
            tokens.Add(token);
        }
    }
}
