namespace Chummer.Run.Contracts.Search;

public static class PrepLibraryQueryAliasCanonicalizer
{
    public static void RewriteAliases(HashSet<string> tokens)
    {
        ArgumentNullException.ThrowIfNull(tokens);

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

        if (tokens.Contains("rosterswaps"))
        {
            tokens.Remove("rosterswaps");
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

        if (tokens.Contains("rostertransfers"))
        {
            tokens.Remove("rostertransfers");
            tokens.Add("rostertransfer");
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
            tokens.Add("rosterhandoff");
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

        if (tokens.Contains("roster") && tokens.Contains("moves"))
        {
            tokens.Remove("moves");
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

        if (tokens.Contains("sessionreturn") || tokens.Contains("sessionreturns"))
        {
            tokens.Remove("sessionreturn");
            tokens.Remove("sessionreturns");
            tokens.Add("session");
            tokens.Add("return");
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

        if (tokens.Contains("hot") && (tokens.Contains("wash") || tokens.Contains("washes")))
        {
            tokens.Remove("hot");
            tokens.Remove("wash");
            tokens.Remove("washes");
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
}
