using System.Net;
using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class BlackLedgerAdvisoryServiceTests
{
    [Fact]
    public void SubmitVote_replaces_existing_vote_for_same_user_and_ballot()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: false);

            harness.Service.SubmitVote(harness.Player, "player-run-signal-house", "hardware-recovery");
            harness.Service.SubmitVote(harness.Player, "player-run-signal-house", "supply-heist");

            JsonElement payload = JsonSerializer.SerializeToElement(harness.Service.BuildSummaryJson(harness.Player));
            JsonElement ballot = payload.GetProperty("player_ballots")[0];
            JsonElement options = ballot.GetProperty("Options");

            Assert.Equal("supply-heist", ballot.GetProperty("SelectedOptionId").GetString());
            Assert.Equal(1, options[0].GetProperty("VoteCount").GetInt32());
            Assert.Equal(0, options[2].GetProperty("VoteCount").GetInt32());
            Assert.Equal("1 advisory vote(s)", ballot.GetProperty("StatusLabel").GetString());
            Assert.Single(harness.Store.BlackLedgerAdvisoryVoteReceipts);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void SubmitVote_rejects_gm_ballot_for_non_gm_player()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: false);

            InvalidOperationException ex = Assert.Throws<InvalidOperationException>(
                () => harness.Service.SubmitVote(harness.Player, "gm-strategy-signal-house", "expand"));

            Assert.Contains("GM strategy voting requires GM posture", ex.Message, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task SendCurrentMailshotsAsync_sends_player_gm_and_leader_lanes_once()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: true);

            IReadOnlyList<BlackLedgerAdvisoryMailReceipt> first = await harness.Service.SendCurrentMailshotsAsync(CancellationToken.None);
            IReadOnlyList<BlackLedgerAdvisoryMailReceipt> second = await harness.Service.SendCurrentMailshotsAsync(CancellationToken.None);

            Assert.Equal(5, first.Count);
            Assert.All(first, receipt => Assert.Equal("sent", receipt.Status));
            Assert.Equal(5, harness.Requests.Count);
            Assert.Equal(5, second.Count);
            Assert.Equal(5, harness.Requests.Count);
            Assert.Equal(2, first.Count(receipt => string.Equals(receipt.MailKind, "player_vote", StringComparison.OrdinalIgnoreCase)));
            Assert.Equal(2, first.Count(receipt => string.Equals(receipt.MailKind, "gm_vote", StringComparison.OrdinalIgnoreCase)));
            Assert.Single(first, receipt => string.Equals(receipt.MailKind, "leader_summary", StringComparison.OrdinalIgnoreCase));

            string combinedBodies = string.Join("\n\n", harness.Requests.Select(item => item.Body));
            Assert.Contains("[Chummer] Black Ledger player advisory voting is open", combinedBodies, StringComparison.Ordinal);
            Assert.Contains("[Chummer] Black Ledger GM strategy recommendation lane is open", combinedBodies, StringComparison.Ordinal);
            Assert.Contains("[Chummer] Black Ledger GM strategy signal reached executive intake", combinedBodies, StringComparison.Ordinal);
            Assert.Contains("The megacorp is not a democracy.", combinedBodies, StringComparison.Ordinal);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task SendCurrentMailshotsAsync_suppresses_when_dispatch_is_unconfigured()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: false);

            IReadOnlyList<BlackLedgerAdvisoryMailReceipt> receipts = await harness.Service.SendCurrentMailshotsAsync(CancellationToken.None);

            Assert.Equal(5, receipts.Count);
            Assert.All(receipts, receipt => Assert.Equal("suppressed_delivery_unconfigured", receipt.Status));
            Assert.Empty(harness.Requests);
            Assert.Equal(5, harness.Store.BlackLedgerAdvisoryMailReceipts.Count);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void BuildSummaryJson_marks_non_democracy_and_executive_highlight()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: false);

            harness.Service.SubmitVote(harness.Player, "player-run-signal-house", "hardware-recovery");
            harness.Service.SubmitVote(harness.Leader, "gm-strategy-signal-house", "expand");

            JsonElement payload = JsonSerializer.SerializeToElement(harness.Service.BuildSummaryJson(harness.Leader));

            Assert.True(payload.GetProperty("is_game_master").GetBoolean());
            Assert.True(payload.GetProperty("is_faction_leader").GetBoolean());
            Assert.Contains("not binding democracy", payload.GetProperty("no_democracy_note").GetString(), StringComparison.OrdinalIgnoreCase);
            Assert.Equal("expand", payload.GetProperty("gm_ballots")[0].GetProperty("SelectedOptionId").GetString());
            Assert.Contains(
                "Expand under pressure",
                payload.GetProperty("executive_summaries")[0].GetProperty("Highlights")[0].GetString(),
                StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task SendCurrentMailshotsAsync_accepts_delivery_id_from_output_json()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: true, responseBody: """{"output_json":{"delivery_id":"ea-delivery-output-json"}}""");

            IReadOnlyList<BlackLedgerAdvisoryMailReceipt> receipts = await harness.Service.SendCurrentMailshotsAsync(CancellationToken.None);

            Assert.Equal(5, receipts.Count);
            Assert.All(receipts, receipt =>
            {
                Assert.Equal("sent", receipt.Status);
                Assert.Equal("ea-delivery-output-json", receipt.DeliveryRef);
            });
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task SendCurrentMailshotsAsync_marks_failed_delivery_when_dispatch_payload_has_no_delivery_id()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: true, responseBody: """{"output_json":{"status":"accepted"}}""");

            IReadOnlyList<BlackLedgerAdvisoryMailReceipt> receipts = await harness.Service.SendCurrentMailshotsAsync(CancellationToken.None);

            Assert.Equal(5, receipts.Count);
            Assert.All(receipts, receipt => Assert.Equal("failed_delivery", receipt.Status));
            Assert.All(receipts, receipt => Assert.Contains("connector_dispatch_missing_delivery_id", receipt.FailureReason, StringComparison.Ordinal));
            Assert.Equal(5, harness.Requests.Count);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void BuildSummaryJson_without_allegiance_has_no_ballots_or_executive_summaries()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            Directory.CreateDirectory(tempRoot);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run"
                })
                .Build();
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            HubUserDto user = accounts.EnsureUserWithStatus("subject.lonely", "Lonely User", "lonely@example.com").User;
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignArtifactRegistryBridge artifactBridge = new(store);
            CampaignSpineService campaignSpine = new(store, lifecycle, artifactBridge);
            BlackLedgerFactionOnboardingService factions = new(configuration, new BlackLedgerPublicStatsService(), campaignSpine, store);
            BlackLedgerAdvisoryService service = new(
                new HttpClient(new CapturingHandler([], HttpStatusCode.OK, """{"target_ref":"unused"}""")),
                store,
                configuration,
                factions,
                NullLogger<BlackLedgerAdvisoryService>.Instance);

            JsonElement payload = JsonSerializer.SerializeToElement(service.BuildSummaryJson(user));

            Assert.False(payload.GetProperty("is_player").GetBoolean());
            Assert.False(payload.GetProperty("is_game_master").GetBoolean());
            Assert.False(payload.GetProperty("is_faction_leader").GetBoolean());
            Assert.Equal(0, payload.GetProperty("player_ballots").GetArrayLength());
            Assert.Equal(0, payload.GetProperty("gm_ballots").GetArrayLength());
            Assert.Equal(0, payload.GetProperty("executive_summaries").GetArrayLength());
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void SubmitVote_rejects_unknown_ballot_and_unknown_option()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: false);

            InvalidOperationException ballotEx = Assert.Throws<InvalidOperationException>(
                () => harness.Service.SubmitVote(harness.Player, "unknown-ballot", "hardware-recovery"));
            InvalidOperationException optionEx = Assert.Throws<InvalidOperationException>(
                () => harness.Service.SubmitVote(harness.Player, "player-run-signal-house", "unknown-option"));

            Assert.Contains("Unknown advisory ballot", ballotEx.Message, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("Unknown advisory option", optionEx.Message, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task SendCurrentMailshotsAsync_builds_expected_urls_and_posture_copy()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: true);

            _ = await harness.Service.SendCurrentMailshotsAsync(CancellationToken.None);

            string combinedBodies = string.Join("\n\n", harness.Requests.Select(item => item.Body));
            Assert.Contains("https://chummer.run/account/ledger/advisory", combinedBodies, StringComparison.Ordinal);
            Assert.Contains("https://chummer.run/account/ledger/factions/signal-house", combinedBodies, StringComparison.Ordinal);
            Assert.Contains("https://chummer.run/account/ledger/factions/signal-house/leader-briefing", combinedBodies, StringComparison.Ordinal);
            Assert.Contains("The megacorp is not a democracy.", combinedBodies, StringComparison.Ordinal);
            Assert.Contains("advisory command pressure", combinedBodies, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void BuildSummary_marks_founder_as_game_master_even_without_group_role()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: false);

            JsonElement payload = JsonSerializer.SerializeToElement(harness.Service.BuildSummaryJson(harness.Leader));

            Assert.True(payload.GetProperty("is_player").GetBoolean());
            Assert.True(payload.GetProperty("is_game_master").GetBoolean());
            Assert.True(payload.GetProperty("is_faction_leader").GetBoolean());
            Assert.Equal(2, payload.GetProperty("player_ballots").GetArrayLength());
            Assert.Equal(1, payload.GetProperty("gm_ballots").GetArrayLength());
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void BuildPage_exposes_flagship_copy_and_summary_link()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: false);
            SiteChromeViewModel chrome = new(
                Title: "Black Ledger",
                Description: "Advisory lane",
                CurrentPath: "/account/ledger/advisory",
                PrimaryNavigation: Array.Empty<Chummer.Run.Api.Services.PublicNavigationLink>(),
                SecondaryNavigation: Array.Empty<Chummer.Run.Api.Services.PublicNavigationLink>(),
                UtilityNavigation: Array.Empty<Chummer.Run.Api.Services.PublicNavigationLink>(),
                HeaderActions: Array.Empty<SiteChromeActionViewModel>(),
                PublicPrimaryCta: null,
                Authenticated: true,
                SignedInLabel: "Tibor",
                FooterCanonicalSource: "test",
                FooterGeneratedNote: "test");

            BlackLedgerAdvisoryPageViewModel page = harness.Service.BuildPage(chrome, harness.Player);

            Assert.Equal("Black Ledger advisory voting", page.Heading);
            Assert.Contains("explicitly non-democratic", page.Intro, StringComparison.OrdinalIgnoreCase);
            Assert.Equal("/account/ledger/advisory?faction=signal-house", page.Summary.OpenMailHref);
            Assert.Contains("advisory signal, not binding democracy", page.Summary.NoDemocracyNote, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task SendCurrentMailshotsAsync_persists_single_receipt_per_mail_kind_user_and_faction()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: true);

            _ = await harness.Service.SendCurrentMailshotsAsync(CancellationToken.None);
            IReadOnlyList<BlackLedgerAdvisoryMailReceipt> second = await harness.Service.SendCurrentMailshotsAsync(CancellationToken.None);

            Assert.Equal(5, second.Count);
            Assert.Equal(5, harness.Store.BlackLedgerAdvisoryMailReceipts.Count);
            Assert.Equal(
                5,
                harness.Store.BlackLedgerAdvisoryMailReceipts
                    .Select(item => $"{item.MailKind}|{item.RecipientUserId}|{item.FactionId}")
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .Count());
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void BuildSummaryJson_computes_vote_share_labels_from_live_votes()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: false);

            HubUserDto extraPlayer = harness.Accounts.EnsureUserWithStatus("subject.extra.player", "Extra Player", "extra.player@gmail.com").User;
            _ = harness.Factions.JoinFaction(extraPlayer, "signal-house");

            harness.Service.SubmitVote(harness.Player, "player-run-signal-house", "supply-heist");
            harness.Service.SubmitVote(extraPlayer, "player-run-signal-house", "supply-heist");
            harness.Service.SubmitVote(harness.Leader, "player-run-signal-house", "hardware-recovery");

            JsonElement payload = JsonSerializer.SerializeToElement(harness.Service.BuildSummaryJson(harness.Player));
            JsonElement options = payload.GetProperty("player_ballots")[0].GetProperty("Options");

            Assert.Equal(2, options[0].GetProperty("VoteCount").GetInt32());
            Assert.Equal("67%", options[0].GetProperty("VoteShareLabel").GetString());
            Assert.Equal(1, options[2].GetProperty("VoteCount").GetInt32());
            Assert.Equal("33%", options[2].GetProperty("VoteShareLabel").GetString());
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void BuildSummaryJson_without_gm_votes_still_emits_executive_summary_with_zero_highlight()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: false);

            JsonElement payload = JsonSerializer.SerializeToElement(harness.Service.BuildSummaryJson(harness.Leader));
            JsonElement executive = payload.GetProperty("executive_summaries")[0];

            Assert.Contains("advisory pressure", executive.GetProperty("Summary").GetString(), StringComparison.OrdinalIgnoreCase);
            Assert.Contains("0 GM vote", executive.GetProperty("Highlights")[0].GetString(), StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void SubmitVote_replaces_existing_receipt_in_store_without_growing_count()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            TestHarness harness = CreateHarness(tempRoot, configureEa: false);

            harness.Service.SubmitVote(harness.Leader, "gm-strategy-signal-house", "expand");
            string firstReceiptId = Assert.Single(harness.Store.BlackLedgerAdvisoryVoteReceipts).ReceiptId;

            harness.Service.SubmitVote(harness.Leader, "gm-strategy-signal-house", "consolidate");
            BlackLedgerAdvisoryVoteReceipt receipt = Assert.Single(harness.Store.BlackLedgerAdvisoryVoteReceipts);

            Assert.NotEqual(firstReceiptId, receipt.ReceiptId);
            Assert.Equal("consolidate", receipt.OptionId);
            Assert.Equal("gm-strategy-signal-house", receipt.BallotId);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    private static TestHarness CreateHarness(string tempRoot, bool configureEa, string? responseBody = null)
    {
        Directory.CreateDirectory(tempRoot);
        Dictionary<string, string?> values = new()
        {
            ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
            ["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run",
            ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"] = "true"
        };
        if (configureEa)
        {
            values["CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN"] = "ea-token";
            values["CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID"] = "principal-1";
            values["CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID"] = "binding-1";
            values["CHUMMER_BLACK_LEDGER_NEWS_EA_BASE_URL"] = "https://ea.test";
        }

        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(values)
            .Build();
        CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
        AccountService accounts = new(store);
        HubUserDto leader = accounts.EnsureUserWithStatus("subject.gm", "Tibor", "tibor.girschele@gmail.com").User;
        HubUserDto player = accounts.EnsureUserWithStatus("subject.player", "Girschele Family", "the.girscheles@gmail.com").User;
        WorkspaceLifecyclePolicyService lifecycle = new(configuration);
        CampaignArtifactRegistryBridge artifactBridge = new(store);
        CampaignSpineService campaignSpine = new(store, lifecycle, artifactBridge);
        BlackLedgerFactionOnboardingService factions = new(configuration, new BlackLedgerPublicStatsService(), campaignSpine, store);
        _ = factions.CreateFaction(
            leader,
            new BlackLedgerCreateFactionRequest(
                "Signal House",
                "major",
                "corporate_compact",
                ["dispatch_desk"],
                ["debt_chain", "bad_paperwork"],
                "downtown-core",
                "ashline-circle",
                WarningAccepted: true));
        _ = factions.JoinFaction(player, "signal-house");

        List<CapturedRequest> requests = [];
        HttpClient httpClient = configureEa
            ? new(new CapturingHandler(requests, HttpStatusCode.OK, responseBody ?? """{"target_ref":"ea-delivery"}"""))
            : new(new CapturingHandler(requests, HttpStatusCode.OK, """{"target_ref":"unused"}"""));
        BlackLedgerAdvisoryService service = new(
            httpClient,
            store,
            configuration,
            factions,
            NullLogger<BlackLedgerAdvisoryService>.Instance);

        return new TestHarness(store, service, leader, player, requests, accounts, factions);
    }

    private static string CreateTempRoot()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "black-ledger-advisory-service-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        return tempRoot;
    }

    private static void DeleteTempRoot(string tempRoot)
    {
        if (Directory.Exists(tempRoot))
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    private sealed record TestHarness(
        CommunityStore Store,
        BlackLedgerAdvisoryService Service,
        HubUserDto Leader,
        HubUserDto Player,
        List<CapturedRequest> Requests,
        AccountService Accounts,
        BlackLedgerFactionOnboardingService Factions);

    private sealed record CapturedRequest(string Url, string Body);

    private sealed class CapturingHandler(
        List<CapturedRequest> requests,
        HttpStatusCode statusCode,
        string responseBody) : HttpMessageHandler
    {
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            string body = request.Content is null
                ? string.Empty
                : await request.Content.ReadAsStringAsync(cancellationToken);
            requests.Add(new CapturedRequest(request.RequestUri!.ToString(), body));
            return new HttpResponseMessage(statusCode)
            {
                Content = new StringContent(responseBody)
            };
        }
    }
}
