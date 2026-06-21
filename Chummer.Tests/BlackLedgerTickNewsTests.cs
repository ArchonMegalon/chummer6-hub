using System.Net;
using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class BlackLedgerTickNewsTests
{
    [Fact]
    public void BlackLedgerTickNews_routes_and_views_exist()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string accountView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "LedgerAccountHome.cshtml"));
        string notificationsView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "LedgerNotifications.cshtml"));
        string ledgerView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Ledger.cshtml"));

        Assert.Contains("[HttpGet(\"/account/ledger/notifications\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/ledger/advisory\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/ledger/advisory.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/account/ledger/advisory/vote\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/ledger/worldtick/validation\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/ledger/factions/{factionId}/leader-briefing\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ledger/turns/{turn}/newsreel.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("Open advisory voting", accountView, StringComparison.Ordinal);
        Assert.Contains("Open advisory", notificationsView, StringComparison.Ordinal);
        Assert.Contains("LedgerAdvisory.cshtml", controller, StringComparison.Ordinal);
        string turnReviewView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "LedgerWorldTickValidation.cshtml"));
        Assert.Contains("World turn", turnReviewView, StringComparison.Ordinal);
        Assert.Contains("Download details", turnReviewView, StringComparison.Ordinal);
        Assert.Contains("What changed this turn", turnReviewView, StringComparison.Ordinal);
        Assert.DoesNotContain("Open data", turnReviewView, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("What this packet says", turnReviewView, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Faction leader briefing", File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "LedgerLeaderBriefing.cshtml")), StringComparison.Ordinal);
        Assert.Contains("Controlled signal", File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "LedgerAdvisory.cshtml")), StringComparison.Ordinal);
        Assert.Contains("Open notifications", accountView, StringComparison.Ordinal);
        Assert.Contains("Account notifications", notificationsView, StringComparison.Ordinal);
        Assert.Contains("Open notification history", accountView, StringComparison.Ordinal);
        Assert.Contains("Open turn review", accountView, StringComparison.Ordinal);
        Assert.Contains("Open turn review", notificationsView, StringComparison.Ordinal);
        Assert.Contains("Current turn details", accountView, StringComparison.Ordinal);
        Assert.DoesNotContain("Current world-turn packet", accountView, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Inbox queue", notificationsView, StringComparison.Ordinal);
        Assert.Contains("Actual messages, not just status", notificationsView, StringComparison.Ordinal);
        Assert.Contains("pressure, not people", ledgerView, StringComparison.Ordinal);
    }

    [Fact]
    public void BlackLedgerNewsRecipientResolver_only_user_preview_fallback_resolves_exactly_one_user()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.SubscribedOrOnlyUserPreviewFallbackPolicy,
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            HubUserDto user = accounts.EnsureUserWithStatus("subject.ledger.one", "Ledger One", "ledger-one@example.com").User;
            BlackLedgerNewsRecipientResolver resolver = new(store, configuration);

            BlackLedgerNewsRecipientResolution resolution = resolver.Resolve("emerald-sprawl-prelude");

            Assert.Equal("resolved", resolution.Status);
            Assert.Single(resolution.Recipients);
            Assert.Equal(user.UserId, resolution.Recipients[0].RecipientUserId);
            Assert.Equal("only_user_preview_fallback", resolution.Recipients[0].Source);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void BlackLedgerNewsRecipientResolver_suppresses_when_multiple_users_without_subscription()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.SubscribedOrOnlyUserPreviewFallbackPolicy,
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            _ = accounts.EnsureUserWithStatus("subject.ledger.one", "Ledger One", "ledger-one@example.com").User;
            _ = accounts.EnsureUserWithStatus("subject.ledger.two", "Ledger Two", "ledger-two@example.com").User;
            BlackLedgerNewsRecipientResolver resolver = new(store, configuration);

            BlackLedgerNewsRecipientResolution resolution = resolver.Resolve("emerald-sprawl-prelude");

            Assert.Equal("suppressed_multiple_users_no_subscription", resolution.Status);
            Assert.Empty(resolution.Recipients);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void BlackLedgerNewsRecipientResolver_operator_only_maps_to_real_user_when_email_matches_account()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.OperatorOnlyPolicy,
                ["CHUMMER_BLACK_LEDGER_NEWS_OPERATOR_TO"] = "the.girscheles@gmail.com",
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            HubUserDto user = accounts.EnsureUserWithStatus("subject.operator.live", "Tibor", "the.girscheles@gmail.com").User;
            BlackLedgerNewsRecipientResolver resolver = new(store, configuration);

            BlackLedgerNewsRecipientResolution resolution = resolver.Resolve("emerald-sprawl-prelude");

            Assert.Equal("resolved", resolution.Status);
            Assert.Single(resolution.Recipients);
            Assert.Equal(user.UserId, resolution.Recipients[0].RecipientUserId);
            Assert.Equal($"user:{user.UserId}", resolution.Recipients[0].RecipientKey);
            Assert.Equal("operator_account_fallback", resolution.Recipients[0].Source);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task BlackLedgerTickNews_sends_to_subscribed_users()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            var requests = new List<CapturedRequest>();
            using var http = new HttpClient(new CapturingHandler(requests, HttpStatusCode.OK, """{"target_ref":"ea-delivery-2"}"""));
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"] = "true",
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.SubscribedOnlyPolicy,
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN"] = "ea-token",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID"] = "principal-1",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID"] = "binding-1",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_BASE_URL"] = "https://ea.test",
                ["CHUMMER_BLACK_LEDGER_NEWS_HASH_SALT"] = "salt-1",
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            HubUserDto subscribed = accounts.EnsureUserWithStatus("subject.ledger.subscribed", "Ledger One", "ledger-one@example.com").User;
            HubUserDto other = accounts.EnsureUserWithStatus("subject.ledger.other", "Ledger Two", "ledger-two@example.com").User;
            store.UserExperienceByUserId[subscribed.UserId] = new HubUserExperienceDto(
                subscribed.UserId,
                LaneInterests: Array.Empty<string>(),
                FollowHorizons: false,
                BetaInterest: false,
                OnboardingCompleted: true,
                OnboardingCompletedAtUtc: DateTimeOffset.UtcNow,
                UpdatedAtUtc: DateTimeOffset.UtcNow,
                BlackLedgerNewsEmail: true,
                BlackLedgerWorldsFollowed: ["emerald-sprawl-prelude"]);
            store.UserExperienceByUserId[other.UserId] = new HubUserExperienceDto(
                other.UserId,
                LaneInterests: Array.Empty<string>(),
                FollowHorizons: false,
                BetaInterest: false,
                OnboardingCompleted: true,
                OnboardingCompletedAtUtc: DateTimeOffset.UtcNow,
                UpdatedAtUtc: DateTimeOffset.UtcNow);

            BlackLedgerTickNewsNotificationService service = new(
                http,
                store,
                configuration,
                new BlackLedgerNewsRecipientResolver(store, configuration),
                CreateBriefingService(),
                BlackLedgerFactionAllegianceTests.CreateService(),
                NullLogger<BlackLedgerTickNewsNotificationService>.Instance);

            BlackLedgerTickNewsNotificationBatchReceipt batch = await service.NotifyTickNewsAsync(
                CreateTickEvent(),
                dryRun: false,
                policyOverride: null,
                CancellationToken.None);

            Assert.Equal("sent", batch.Status);
            Assert.Single(batch.Receipts);
            Assert.Equal("sent", batch.Receipts[0].Status);
            Assert.Equal(subscribed.UserId, batch.Receipts[0].RecipientUserId);
            CapturedRequest request = Assert.Single(requests);
            using JsonDocument payload = JsonDocument.Parse(request.Body);
            Assert.Equal("connector.dispatch", payload.RootElement.GetProperty("tool_name").GetString());
            Assert.Equal("delivery.send", payload.RootElement.GetProperty("action_kind").GetString());
            JsonElement payloadJson = payload.RootElement.GetProperty("payload_json");
            Assert.Equal("ledger-one@example.com", payloadJson.GetProperty("recipient").GetString());
            Assert.Equal("binding-1", payloadJson.GetProperty("binding_id").GetString());
            Assert.Contains("0→1", payloadJson.GetProperty("subject").GetString(), StringComparison.Ordinal);
            string content = payloadJson.GetProperty("content").GetString() ?? string.Empty;
            Assert.Contains("/ledger/factions/ashline-circle/promo", content, StringComparison.Ordinal);
            Assert.Contains("/account/ledger/factions/ashline-circle/leader-briefing", content, StringComparison.Ordinal);
            Assert.True(payloadJson.TryGetProperty("idempotency_key", out _));
            Assert.False(request.Body.Contains("ledger-two@example.com", StringComparison.Ordinal));
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task BlackLedgerTickNews_suppresses_when_email_delivery_disabled()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            using var http = new HttpClient(new CapturingHandler(new List<CapturedRequest>(), HttpStatusCode.OK, """{"target_ref":"ea-delivery-2"}"""));
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.SubscribedOrOnlyUserPreviewFallbackPolicy,
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            _ = accounts.EnsureUserWithStatus("subject.ledger.one", "Ledger One", "ledger-one@example.com").User;

            BlackLedgerTickNewsNotificationService service = new(
                http,
                store,
                configuration,
                new BlackLedgerNewsRecipientResolver(store, configuration),
                CreateBriefingService(),
                BlackLedgerFactionAllegianceTests.CreateService(),
                NullLogger<BlackLedgerTickNewsNotificationService>.Instance);

            BlackLedgerTickNewsNotificationBatchReceipt batch = await service.NotifyTickNewsAsync(
                CreateTickEvent(),
                dryRun: false,
                policyOverride: null,
                CancellationToken.None);

            Assert.Equal("suppressed_disabled", batch.Status);
            Assert.Single(batch.Receipts);
            Assert.Equal("suppressed_disabled", batch.Receipts[0].Status);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void BlackLedgerAdvisory_votes_route_players_to_gms_and_gms_to_leaders()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>());
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            GroupService groups = new(store, accounts);
            HubUserDto gm = accounts.EnsureUserWithStatus("subject.gm", "GM", "gm@example.com").User;
            HubUserDto player = accounts.EnsureUserWithStatus("subject.player", "Player", "player@example.com").User;
            GroupDto group = groups.CreateGroup(new CreateGroupRequest(gm.SubjectId, "Ledger Ops", GroupType: "community", Visibility: "private", Capabilities: ["campaigns", "can_issue_join_codes"]));
            JoinCodeDto joinCode = groups.CreateJoinCode(group.GroupId, new CreateJoinCodeRequest(gm.SubjectId, Role: "member"));
            _ = groups.JoinGroup(new JoinGroupByCodeRequest(player.SubjectId, joinCode.Code));

            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignArtifactRegistryBridge artifactBridge = new(store);
            CampaignSpineService campaignSpine = new(store, lifecycle, artifactBridge);
            BlackLedgerFactionOnboardingService factions = new(configuration, new BlackLedgerPublicStatsService(), campaignSpine, store);
            _ = factions.CreateFaction(gm, new BlackLedgerCreateFactionRequest("Signal House", "major", "corporate_compact", ["dispatch_desk"], ["debt_chain", "bad_paperwork"], "downtown-core", "ashline-circle", WarningAccepted: true));
            _ = factions.JoinFaction(player, "signal-house");
            BlackLedgerAdvisoryService service = new(
                new HttpClient(new CapturingHandler(new List<CapturedRequest>(), HttpStatusCode.OK, """{"target_ref":"ea-delivery"}""")),
                store,
                configuration,
                factions,
                NullLogger<BlackLedgerAdvisoryService>.Instance);

            service.SubmitVote(player, "player-run-signal-house", "hardware-recovery");
            service.SubmitVote(gm, "gm-strategy-signal-house", "expand");

            JsonElement payload = JsonSerializer.SerializeToElement(service.BuildSummaryJson(gm));

            Assert.True(payload.GetProperty("is_game_master").GetBoolean());
            Assert.True(payload.GetProperty("is_faction_leader").GetBoolean());
            Assert.Contains("not binding democracy", payload.GetProperty("no_democracy_note").GetString(), StringComparison.OrdinalIgnoreCase);
            Assert.Equal(1, payload.GetProperty("player_ballots")[0].GetProperty("Options")[2].GetProperty("VoteCount").GetInt32());
            Assert.Equal("expand", payload.GetProperty("gm_ballots")[0].GetProperty("SelectedOptionId").GetString());
            Assert.True(payload.GetProperty("executive_summaries")[0].GetProperty("Highlights")[0].GetString()!.Contains("Expand under pressure", StringComparison.OrdinalIgnoreCase));
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task BlackLedgerTickNews_privacy_gate_blocks_private_data()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            using var http = new HttpClient(new CapturingHandler(new List<CapturedRequest>(), HttpStatusCode.OK, """{"target_ref":"ea-delivery-2"}"""));
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"] = "true",
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.SubscribedOrOnlyUserPreviewFallbackPolicy,
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            _ = accounts.EnsureUserWithStatus("subject.ledger.one", "Ledger One", "ledger-one@example.com").User;
            BlackLedgerTickNewsNotificationService service = new(
                http,
                store,
                configuration,
                new BlackLedgerNewsRecipientResolver(store, configuration),
                CreateBriefingService(),
                BlackLedgerFactionAllegianceTests.CreateService(),
                NullLogger<BlackLedgerTickNewsNotificationService>.Instance);

            BlackLedgerTickNewsNotificationBatchReceipt batch = await service.NotifyTickNewsAsync(
                CreateTickEvent(publicSummary: "private_campaign pressure leaked"),
                dryRun: false,
                policyOverride: null,
                CancellationToken.None);

            Assert.Equal("suppressed_privacy_failed", batch.Status);
            Assert.Single(batch.Receipts);
            Assert.Equal("suppressed_privacy_failed", batch.Receipts[0].Status);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task BlackLedgerTickNews_idempotency_prevents_duplicate_send_and_preseeded_turn_one_can_build_catchup_email()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            var requests = new List<CapturedRequest>();
            using var http = new HttpClient(new CapturingHandler(requests, HttpStatusCode.OK, """{"target_ref":"ea-delivery-2"}"""));
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"] = "true",
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.SubscribedOrOnlyUserPreviewFallbackPolicy,
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN"] = "ea-token",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID"] = "principal-1",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID"] = "binding-1",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_BASE_URL"] = "https://ea.test",
                ["CHUMMER_BLACK_LEDGER_NEWS_HASH_SALT"] = "salt-1",
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            _ = accounts.EnsureUserWithStatus("subject.ledger.one", "Ledger One", "ledger-one@example.com").User;

            BlackLedgerTickNewsNotificationService service = new(
                http,
                store,
                configuration,
                new BlackLedgerNewsRecipientResolver(store, configuration),
                CreateBriefingService(),
                BlackLedgerFactionAllegianceTests.CreateService(),
                NullLogger<BlackLedgerTickNewsNotificationService>.Instance);

            BlackLedgerWorldTickNewsEvent seeded = service.BuildSeededWorldEvent("emerald-sprawl-prelude", 1, "https://chummer.run")
                ?? throw new InvalidOperationException("expected preseeded turn-one event");
            Assert.Equal(1, seeded.ToTurn);
            Assert.Equal(0, seeded.FromTurn);
            Assert.Equal("ledger_tick_0001_preseeded", seeded.TickReceiptId);
            Assert.Contains("Turn 0", seeded.PublicSummary, StringComparison.Ordinal);

            BlackLedgerTickNewsNotificationBatchReceipt first = await service.NotifyTickNewsAsync(seeded, false, null, CancellationToken.None);
            BlackLedgerTickNewsNotificationBatchReceipt second = await service.NotifyTickNewsAsync(seeded, false, null, CancellationToken.None);

            Assert.Equal("sent", first.Status);
            Assert.True(second.Duplicate);
            Assert.Equal("duplicate", second.Status);
            Assert.Single(requests);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task BlackLedgerTickNews_accepts_delivery_id_from_output_json()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            var requests = new List<CapturedRequest>();
            using var http = new HttpClient(new CapturingHandler(requests, HttpStatusCode.OK, """{"output_json":{"delivery_id":"ea-delivery-output-json"}}"""));
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"] = "true",
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.SubscribedOrOnlyUserPreviewFallbackPolicy,
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN"] = "ea-token",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID"] = "principal-1",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID"] = "binding-1",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_BASE_URL"] = "https://ea.test",
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            _ = accounts.EnsureUserWithStatus("subject.ledger.one", "Ledger One", "ledger-one@example.com").User;

            BlackLedgerTickNewsNotificationService service = new(
                http,
                store,
                configuration,
                new BlackLedgerNewsRecipientResolver(store, configuration),
                CreateBriefingService(),
                BlackLedgerFactionAllegianceTests.CreateService(),
                NullLogger<BlackLedgerTickNewsNotificationService>.Instance);

            BlackLedgerTickNewsNotificationBatchReceipt batch = await service.NotifyTickNewsAsync(CreateTickEvent(), false, null, CancellationToken.None);

            Assert.Equal("sent", batch.Status);
            Assert.Single(batch.Receipts);
            Assert.Equal("ea-delivery-output-json", batch.Receipts[0].DeliveryRef);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void BlackLedgerTickNews_status_view_model_explains_operator_preview_to_non_recipient()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            using var http = new HttpClient(new CapturingHandler(new List<CapturedRequest>(), HttpStatusCode.OK, """{"target_ref":"ea-delivery-2"}"""));
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"] = "true",
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.OperatorOnlyPolicy,
                ["CHUMMER_BLACK_LEDGER_NEWS_OPERATOR_TO"] = "operator@chummer.run",
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            BlackLedgerTickNewsNotificationService service = new(
                http,
                store,
                configuration,
                new BlackLedgerNewsRecipientResolver(store, configuration),
                CreateBriefingService(),
                BlackLedgerFactionAllegianceTests.CreateService(),
                NullLogger<BlackLedgerTickNewsNotificationService>.Instance);

            store.BlackLedgerNewsDeliveryReceipts.Add(new BlackLedgerNewsDeliveryReceipt(
                "blnews_demo",
                "black_ledger_tick_news_generated",
                "black-ledger-news|emerald-sprawl-prelude|1|ledger_tick_0001_preseeded|operator",
                "emerald-sprawl-prelude",
                0,
                1,
                "ledger_tick_0001_preseeded",
                "news_emerald_turn_1",
                "operator",
                "o***@chummer.run",
                "hash",
                "sent",
                "ea-delivery-1",
                null,
                DateTimeOffset.UtcNow,
                DateTimeOffset.UtcNow));

            BlackLedgerNewsStatusViewModel status = service.BuildStatusViewModel(
                "emerald-sprawl-prelude",
                1,
                "Account lane",
                "/account/ledger/notifications",
                "/ledger/turns/1",
                "/ledger/turns/1/dispatches",
                recipientUserId: "usr_regular");

            Assert.Equal("suppressed_not_current_recipient", status.Status);
            Assert.Contains("not an email recipient on this runtime", status.Summary, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void BlackLedgerTickNews_can_backfill_durable_inbox_entries_from_existing_sent_receipt()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            using var http = new HttpClient(new CapturingHandler(new List<CapturedRequest>(), HttpStatusCode.OK, """{"target_ref":"ea-delivery-2"}"""));
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"] = "true",
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.OperatorOnlyPolicy,
                ["CHUMMER_BLACK_LEDGER_NEWS_OPERATOR_TO"] = "the.girscheles@gmail.com",
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            BlackLedgerTickNewsNotificationService service = new(
                http,
                store,
                configuration,
                new BlackLedgerNewsRecipientResolver(store, configuration),
                CreateBriefingService(),
                BlackLedgerFactionAllegianceTests.CreateService(),
                NullLogger<BlackLedgerTickNewsNotificationService>.Instance);

            store.BlackLedgerNewsDeliveryReceipts.Add(new BlackLedgerNewsDeliveryReceipt(
                "blnews_seeded",
                "black_ledger_tick_news_generated",
                "black-ledger-news|emerald-sprawl-prelude|1|ledger_tick_0001_preseeded|user:usr-ea8af6d123c0",
                "emerald-sprawl-prelude",
                0,
                1,
                "ledger_tick_0001_preseeded",
                "news_emerald_turn_1",
                "usr-ea8af6d123c0",
                "t***@gmail.com",
                "hash",
                "sent",
                "ea-delivery-1",
                null,
                DateTimeOffset.UtcNow,
                DateTimeOffset.UtcNow));

            int rebuilt = service.BackfillInboxEntries("usr-ea8af6d123c0");

            Assert.Equal(1, rebuilt);
            Assert.NotEmpty(store.BlackLedgerInboxEntries);
            Assert.Contains(store.BlackLedgerInboxEntries, item =>
                string.Equals(item.RecipientUserId, "usr-ea8af6d123c0", StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.Kind, "newsreel", StringComparison.OrdinalIgnoreCase));
            Assert.Contains(store.BlackLedgerInboxEntries, item =>
                string.Equals(item.RecipientUserId, "usr-ea8af6d123c0", StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.Kind, "leader_digest", StringComparison.OrdinalIgnoreCase));
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task BlackLedgerTickNewsDispatchWorker_catches_up_seeded_turn_one_when_store_has_no_worldtick_rows()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            var requests = new List<CapturedRequest>();
            using var http = new HttpClient(new CapturingHandler(requests, HttpStatusCode.OK, """{"target_ref":"ea-delivery-catchup"}"""));
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run",
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"] = "true",
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.OperatorOnlyPolicy,
                ["CHUMMER_BLACK_LEDGER_NEWS_OPERATOR_TO"] = "the.girscheles@gmail.com",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN"] = "ea-token",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID"] = "principal-1",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID"] = "binding-1",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_BASE_URL"] = "https://ea.test",
                ["CHUMMER_BLACK_LEDGER_NEWS_HASH_SALT"] = "salt-1",
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            HubUserDto user = accounts.EnsureUserWithStatus("subject.operator.live", "Tibor", "the.girscheles@gmail.com").User;
            BlackLedgerTickNewsNotificationService notifications = new(
                http,
                store,
                configuration,
                new BlackLedgerNewsRecipientResolver(store, configuration),
                CreateBriefingService(),
                BlackLedgerFactionAllegianceTests.CreateService(),
                NullLogger<BlackLedgerTickNewsNotificationService>.Instance);
            BlackLedgerTickNewsDispatchWorker worker = new(
                store,
                notifications,
                configuration,
                NullLogger<BlackLedgerTickNewsDispatchWorker>.Instance);

            var method = typeof(BlackLedgerTickNewsDispatchWorker).GetMethod("DispatchPendingAsync", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)
                ?? throw new InvalidOperationException("DispatchPendingAsync not found.");
            await (Task)(method.Invoke(worker, [CancellationToken.None]) ?? throw new InvalidOperationException("worker invocation returned null"));

            Assert.Single(requests);
            BlackLedgerNewsDeliveryReceipt receipt = Assert.Single(store.BlackLedgerNewsDeliveryReceipts);
            Assert.Equal("sent", receipt.Status);
            Assert.Equal(user.UserId, receipt.RecipientUserId);
            Assert.Equal("ledger_tick_0001_preseeded", receipt.TickReceiptId);
            Assert.NotEmpty(store.BlackLedgerInboxEntries);
            Assert.Contains(store.BlackLedgerInboxEntries, item =>
                string.Equals(item.RecipientUserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.Kind, "newsreel", StringComparison.OrdinalIgnoreCase));

            CommunityStore reloaded = new(configuration, NullLogger<CommunityStore>.Instance);
            Assert.NotEmpty(reloaded.BlackLedgerInboxEntries);
            Assert.Contains(reloaded.BlackLedgerInboxEntries, item =>
                string.Equals(item.RecipientUserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.Kind, "validation", StringComparison.OrdinalIgnoreCase));
            Assert.NotEmpty(notifications.ListInboxEntries(user.UserId));
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    private static BlackLedgerWorldTickNewsEvent CreateTickEvent(string publicSummary = "Debt heat moved, but the lane stayed public-safe.")
        => new(
            WorldId: "emerald-sprawl-prelude",
            WorldName: "Emerald Sprawl: First Pressure",
            FromTurn: 0,
            ToTurn: 1,
            TickReceiptId: "ledger_tick_0001_preseeded",
            NewsId: "news_0001",
            PublicHeadline: "Black Ledger turn 1: The city is moving",
            PublicSummary: publicSummary,
            PublicHighlights: ["Rust Bazaar pressure rose."],
            LedgerUrl: "https://chummer.run/ledger?turn=1",
            DispatchUrl: "https://chummer.run/ledger/dispatches/dispatch_turn_0001_main",
            TickReceiptUrl: "https://chummer.run/ledger/closeouts",
            OccurredAtUtc: DateTimeOffset.UtcNow);

    private static IConfiguration BuildConfiguration(string tempRoot, IReadOnlyDictionary<string, string?> extra)
    {
        Dictionary<string, string?> values = new(extra, StringComparer.OrdinalIgnoreCase)
        {
            ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json")
        };
        return new ConfigurationBuilder()
            .AddInMemoryCollection(values)
            .Build();
    }

    private static string CreateTempRoot()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "black-ledger-tick-news-tests", Guid.NewGuid().ToString("N"));
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

    private static BlackLedgerWorldTickBriefingService CreateBriefingService()
    {
        BlackLedgerPublicStatsService stats = new();
        BlackLedgerFactionOnboardingService factions = BlackLedgerFactionAllegianceTests.CreateService();
        return new BlackLedgerWorldTickBriefingService(stats, factions);
    }

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
