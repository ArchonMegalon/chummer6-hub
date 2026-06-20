using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services.Community;

public sealed record BlackLedgerWorldTickNewsEvent(
    string WorldId,
    string WorldName,
    int FromTurn,
    int ToTurn,
    string TickReceiptId,
    string NewsId,
    string PublicHeadline,
    string PublicSummary,
    IReadOnlyList<string> PublicHighlights,
    string LedgerUrl,
    string DispatchUrl,
    string TickReceiptUrl,
    DateTimeOffset OccurredAtUtc);

public sealed record BlackLedgerNewsRecipientCandidate(
    string RecipientKey,
    string RecipientUserId,
    string DisplayName,
    string Email,
    bool SubscriptionBacked,
    string Source);

public sealed record BlackLedgerNewsRecipientResolution(
    string Policy,
    string Status,
    string? FailureReason,
    IReadOnlyList<BlackLedgerNewsRecipientCandidate> Recipients);

public sealed record BlackLedgerNewsDeliveryReceipt(
    string ReceiptId,
    string EventType,
    string EventKey,
    string WorldId,
    int FromTurn,
    int ToTurn,
    string TickReceiptId,
    string NewsId,
    string RecipientUserId,
    string EmailMasked,
    string EmailHash,
    string Status,
    string? DeliveryRef,
    string? FailureReason,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset AttemptedAtUtc);

public sealed record BlackLedgerInboxEntry(
    string EntryId,
    string RecipientUserId,
    string WorldId,
    int Turn,
    string Kind,
    string Eyebrow,
    string Heading,
    string Summary,
    string Href,
    string CtaLabel,
    string StatusLabel,
    string SourceReceiptId,
    DateTimeOffset CreatedAtUtc);

public sealed record BlackLedgerTickNewsNotificationBatchReceipt(
    string BatchId,
    string Policy,
    string Status,
    string WorldId,
    int FromTurn,
    int ToTurn,
    string TickReceiptId,
    string NewsId,
    bool DryRun,
    bool Duplicate,
    int RecipientCount,
    string? FailureReason,
    IReadOnlyList<BlackLedgerNewsDeliveryReceipt> Receipts);

public sealed class BlackLedgerNewsRecipientResolver
{
    public const string DisabledPolicy = "disabled";
    public const string SubscribedOnlyPolicy = "subscribed_only";
    public const string SubscribedOrOnlyUserPreviewFallbackPolicy = "subscribed_or_only_user_preview_fallback";
    public const string OperatorOnlyPolicy = "operator_only";

    private const string PolicyConfigKey = "CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY";
    private readonly CommunityStore _store;
    private readonly IConfiguration _configuration;

    public BlackLedgerNewsRecipientResolver(CommunityStore store, IConfiguration configuration)
    {
        _store = store;
        _configuration = configuration;
    }

    public BlackLedgerNewsRecipientResolution Resolve(string worldId, string? policyOverride = null)
    {
        string policy = NormalizePolicy(policyOverride ?? _configuration[PolicyConfigKey]);
        if (string.Equals(policy, DisabledPolicy, StringComparison.Ordinal))
        {
            return new BlackLedgerNewsRecipientResolution(policy, "suppressed_disabled", "notifications_disabled", Array.Empty<BlackLedgerNewsRecipientCandidate>());
        }

        List<BlackLedgerNewsRecipientCandidate> subscribed = ResolveSubscribedUsers(worldId);
        if (subscribed.Count > 0)
        {
            return new BlackLedgerNewsRecipientResolution(policy, "resolved", null, subscribed);
        }

        if (string.Equals(policy, OperatorOnlyPolicy, StringComparison.Ordinal))
        {
            string? operatorEmail = NormalizeEmail(
                _configuration["CHUMMER_BLACK_LEDGER_NEWS_OPERATOR_TO"]
                ?? _configuration["CHUMMER_OPERATOR_PARTICIPATION_NOTIFY_TO"]);
            if (string.IsNullOrWhiteSpace(operatorEmail))
            {
                return new BlackLedgerNewsRecipientResolution(policy, "suppressed_no_recipients", "recipient_missing", Array.Empty<BlackLedgerNewsRecipientCandidate>());
            }

            BlackLedgerNewsRecipientCandidate? mappedOperator = ResolveUserByEmail(operatorEmail, "operator_account_fallback");
            if (mappedOperator is not null)
            {
                return new BlackLedgerNewsRecipientResolution(policy, "resolved", null, [mappedOperator]);
            }

            return new BlackLedgerNewsRecipientResolution(
                policy,
                "resolved",
                null,
                [
                    new BlackLedgerNewsRecipientCandidate(
                        RecipientKey: "operator",
                        RecipientUserId: "operator",
                        DisplayName: "Operator",
                        Email: operatorEmail,
                        SubscriptionBacked: true,
                        Source: "operator_fallback")
                ]);
        }

        if (!string.Equals(policy, SubscribedOrOnlyUserPreviewFallbackPolicy, StringComparison.Ordinal))
        {
            return new BlackLedgerNewsRecipientResolution(policy, "suppressed_no_recipients", "no_subscribers", Array.Empty<BlackLedgerNewsRecipientCandidate>());
        }

        List<BlackLedgerNewsRecipientCandidate> eligible = ResolveEligibleUsers();
        if (eligible.Count == 1)
        {
            BlackLedgerNewsRecipientCandidate only = eligible[0] with
            {
                RecipientKey = $"user:{eligible[0].RecipientUserId}",
                Source = "only_user_preview_fallback",
            };
            return new BlackLedgerNewsRecipientResolution(policy, "resolved", null, [only]);
        }

        return eligible.Count > 1
            ? new BlackLedgerNewsRecipientResolution(policy, "suppressed_multiple_users_no_subscription", "multiple_users_no_subscription", Array.Empty<BlackLedgerNewsRecipientCandidate>())
            : new BlackLedgerNewsRecipientResolution(policy, "suppressed_no_recipients", "no_eligible_users", Array.Empty<BlackLedgerNewsRecipientCandidate>());
    }

    private List<BlackLedgerNewsRecipientCandidate> ResolveSubscribedUsers(string worldId)
    {
        var recipients = new List<BlackLedgerNewsRecipientCandidate>();
        lock (_store.Gate)
        {
            foreach ((string userId, HubUserExperienceDto experience) in _store.UserExperienceByUserId)
            {
                if (!experience.BlackLedgerNewsEmail)
                {
                    continue;
                }

                IReadOnlyList<string> followed = experience.BlackLedgerWorldsFollowed ?? Array.Empty<string>();
                if (followed.Count > 0 && !followed.Any(item => string.Equals(item?.Trim(), worldId, StringComparison.OrdinalIgnoreCase)))
                {
                    continue;
                }

                if (!_store.UsersById.TryGetValue(userId, out HubUserDto? user))
                {
                    continue;
                }

                string? email = NormalizeEmail(user.Email);
                if (string.IsNullOrWhiteSpace(email))
                {
                    continue;
                }

                recipients.Add(new BlackLedgerNewsRecipientCandidate(
                    RecipientKey: $"user:{user.UserId}",
                    RecipientUserId: user.UserId,
                    DisplayName: string.IsNullOrWhiteSpace(user.DisplayName) ? "Runner" : user.DisplayName,
                    Email: email,
                    SubscriptionBacked: true,
                    Source: followed.Count > 0 ? "world_follow" : "black_ledger_news_email"));
            }
        }

        return recipients
            .GroupBy(static item => item.RecipientKey, StringComparer.OrdinalIgnoreCase)
            .Select(static group => group.First())
            .OrderBy(static item => item.RecipientKey, StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    private List<BlackLedgerNewsRecipientCandidate> ResolveEligibleUsers()
    {
        lock (_store.Gate)
        {
            return _store.UsersById.Values
                .Select(static user => new
                {
                    User = user,
                    Email = NormalizeEmail(user.Email),
                })
                .Where(static item => !string.IsNullOrWhiteSpace(item.Email))
                .Select(static item => new BlackLedgerNewsRecipientCandidate(
                    RecipientKey: $"user:{item.User.UserId}",
                    RecipientUserId: item.User.UserId,
                    DisplayName: string.IsNullOrWhiteSpace(item.User.DisplayName) ? "Runner" : item.User.DisplayName,
                    Email: item.Email!,
                    SubscriptionBacked: false,
                    Source: "eligible_user"))
                .OrderBy(static item => item.RecipientKey, StringComparer.OrdinalIgnoreCase)
                .ToList();
        }
    }

    private BlackLedgerNewsRecipientCandidate? ResolveUserByEmail(string email, string source)
    {
        lock (_store.Gate)
        {
            HubUserDto? user = _store.UsersById.Values
                .FirstOrDefault(candidate => string.Equals(NormalizeEmail(candidate.Email), email, StringComparison.OrdinalIgnoreCase));
            if (user is null)
            {
                return null;
            }

            return new BlackLedgerNewsRecipientCandidate(
                RecipientKey: $"user:{user.UserId}",
                RecipientUserId: user.UserId,
                DisplayName: string.IsNullOrWhiteSpace(user.DisplayName) ? "Operator" : user.DisplayName,
                Email: email,
                SubscriptionBacked: true,
                Source: source);
        }
    }

    public static string NormalizePolicy(string? policy)
    {
        string normalized = (policy ?? string.Empty).Trim().ToLowerInvariant();
        return normalized switch
        {
            SubscribedOnlyPolicy => SubscribedOnlyPolicy,
            SubscribedOrOnlyUserPreviewFallbackPolicy => SubscribedOrOnlyUserPreviewFallbackPolicy,
            OperatorOnlyPolicy => OperatorOnlyPolicy,
            _ => DisabledPolicy,
        };
    }

    private static string? NormalizeEmail(string? email)
        => AccountService.NormalizeOptional(email);
}

public sealed class BlackLedgerTickNewsNotificationService
{
    private const string DefaultEaBaseUrl = "http://127.0.0.1:8090";
    private const string ConnectorDispatchTool = "connector.dispatch";
    private const string DeliverySendAction = "delivery.send";
    private const string EmailChannel = "email";
    private const string ReceiptPrefix = "blnews";
    private const string EventType = "black_ledger_tick_news_generated";
    private const string EnabledConfigKey = "CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED";
    private const string EaApiTokenConfigKey = "CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN";
    private const string EaPrincipalIdConfigKey = "CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID";
    private const string EaBindingIdConfigKey = "CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID";
    private const string EaBaseUrlConfigKey = "CHUMMER_BLACK_LEDGER_NEWS_EA_BASE_URL";
    private const string HashSaltConfigKey = "CHUMMER_BLACK_LEDGER_NEWS_HASH_SALT";
    private static readonly string[] ForbiddenPrivacyTerms =
    [
        "private_campaign",
        "support_case",
        "account_email",
        "operator_secret",
        "sourcebook_text",
        "webhook secret",
        "productlift",
        "emailit",
        "deftform",
    ];

    private readonly HttpClient _httpClient;
    private readonly CommunityStore _store;
    private readonly IConfiguration _configuration;
    private readonly BlackLedgerNewsRecipientResolver _resolver;
    private readonly BlackLedgerWorldTickBriefingService _briefings;
    private readonly BlackLedgerFactionOnboardingService _factions;
    private readonly ILogger<BlackLedgerTickNewsNotificationService> _logger;

    public BlackLedgerTickNewsNotificationService(
        HttpClient httpClient,
        CommunityStore store,
        IConfiguration configuration,
        BlackLedgerNewsRecipientResolver resolver,
        BlackLedgerWorldTickBriefingService briefings,
        BlackLedgerFactionOnboardingService factions,
        ILogger<BlackLedgerTickNewsNotificationService>? logger = null)
    {
        _httpClient = httpClient;
        _store = store;
        _configuration = configuration;
        _resolver = resolver;
        _briefings = briefings;
        _factions = factions;
        _logger = logger ?? NullLogger<BlackLedgerTickNewsNotificationService>.Instance;
    }

    public IReadOnlyList<BlackLedgerNewsDeliveryReceipt> ListReceipts(string worldId, int? turn = null, int take = 24)
    {
        lock (_store.Gate)
        {
            IEnumerable<BlackLedgerNewsDeliveryReceipt> query = _store.BlackLedgerNewsDeliveryReceipts
                .Where(item => string.Equals(item.WorldId, worldId, StringComparison.OrdinalIgnoreCase));
            if (turn.HasValue)
            {
                query = query.Where(item => item.ToTurn == turn.Value);
            }

            return query
                .OrderByDescending(static item => item.CreatedAtUtc)
                .Take(Math.Max(1, take))
                .ToArray();
        }
    }

    public IReadOnlyList<BlackLedgerInboxEntry> ListInboxEntries(string recipientUserId, string worldId = "emerald-sprawl-prelude", int take = 24)
    {
        if (string.IsNullOrWhiteSpace(recipientUserId))
        {
            return Array.Empty<BlackLedgerInboxEntry>();
        }

        lock (_store.Gate)
        {
            return _store.BlackLedgerInboxEntries
                .Where(item =>
                    string.Equals(item.RecipientUserId, recipientUserId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.WorldId, worldId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.CreatedAtUtc)
                .Take(Math.Max(1, take))
                .ToArray();
        }
    }

    public int BackfillInboxEntries(string recipientUserId, string worldId = "emerald-sprawl-prelude")
    {
        if (string.IsNullOrWhiteSpace(recipientUserId))
        {
            return 0;
        }

        BlackLedgerNewsDeliveryReceipt[] receipts;
        lock (_store.Gate)
        {
            bool alreadyHasEntries = _store.BlackLedgerInboxEntries.Any(item =>
                string.Equals(item.RecipientUserId, recipientUserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.WorldId, worldId, StringComparison.OrdinalIgnoreCase));
            if (alreadyHasEntries)
            {
                return 0;
            }

            receipts = _store.BlackLedgerNewsDeliveryReceipts
                .Where(item =>
                    string.Equals(item.RecipientUserId, recipientUserId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.WorldId, worldId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.Status, "sent", StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray();
        }

        foreach (BlackLedgerNewsDeliveryReceipt receipt in receipts)
        {
            UpsertInboxEntries(receipt);
        }

        return receipts.Length;
    }

    public BlackLedgerNewsStatusViewModel BuildStatusViewModel(
        string worldId,
        int turn,
        string scopeLabel,
        string notificationsHref,
        string turnHref,
        string dispatchHref,
        string? recipientUserId = null)
    {
        var allReceipts = ListReceipts(worldId, turn, 24).ToArray();
        var scopedReceipts = string.IsNullOrWhiteSpace(recipientUserId)
            ? allReceipts
            : allReceipts.Where(item => string.Equals(item.RecipientUserId, recipientUserId, StringComparison.OrdinalIgnoreCase)).ToArray();
        BlackLedgerNewsRecipientResolution resolution = _resolver.Resolve(worldId);
        BlackLedgerNewsDeliveryReceipt? latest = scopedReceipts.FirstOrDefault() ?? allReceipts.FirstOrDefault();

        string status;
        string summary;
        string? failureReason;
        if (latest is not null && scopedReceipts.Length > 0)
        {
            status = latest.Status;
            summary = BuildStatusSummary(latest.Status, latest.FailureReason, isRecipientScoped: !string.IsNullOrWhiteSpace(recipientUserId));
            failureReason = latest.FailureReason;
        }
        else if (!string.IsNullOrWhiteSpace(recipientUserId) && latest is not null)
        {
            status = "suppressed_not_current_recipient";
            summary = string.Equals(resolution.Policy, BlackLedgerNewsRecipientResolver.OperatorOnlyPolicy, StringComparison.Ordinal)
                ? "Turn 1 newsreel ran under operator preview policy. This signed-in account is not an email recipient on this runtime."
                : "Turn 1 newsreel exists, but this signed-in account is not one of the current recipients.";
            failureReason = "not_current_recipient";
        }
        else if (latest is not null)
        {
            status = latest.Status;
            summary = BuildStatusSummary(latest.Status, latest.FailureReason, isRecipientScoped: false);
            failureReason = latest.FailureReason;
        }
        else
        {
            status = resolution.Status == "resolved" ? "unconfigured" : resolution.Status;
            summary = resolution.Status == "resolved"
                ? "Recipient resolution is configured, but no stored Turn 1 newsreel receipt exists yet."
                : BuildStatusSummary(resolution.Status, resolution.FailureReason, isRecipientScoped: !string.IsNullOrWhiteSpace(recipientUserId));
            failureReason = resolution.FailureReason;
        }

        return new BlackLedgerNewsStatusViewModel(
            WorldId: worldId,
            Turn: turn,
            Status: status,
            StatusLabel: BuildStatusLabel(status),
            Summary: summary,
            FailureReason: failureReason,
            Policy: resolution.Policy,
            ReceiptCount: scopedReceipts.Length > 0 ? scopedReceipts.Length : allReceipts.Length,
            RecipientCount: allReceipts.Count(item => string.Equals(item.Status, "sent", StringComparison.OrdinalIgnoreCase)),
            ScopeLabel: scopeLabel,
            NotificationsHref: notificationsHref,
            TurnHref: turnHref,
            DispatchHref: dispatchHref,
            Receipts: (scopedReceipts.Length > 0 ? scopedReceipts : allReceipts)
                .Take(6)
                .Select(item => new BlackLedgerNewsReceiptEntryViewModel(
                    ReceiptId: item.ReceiptId,
                    Status: item.Status,
                    Summary: BuildStatusSummary(item.Status, item.FailureReason, isRecipientScoped: !string.IsNullOrWhiteSpace(recipientUserId)),
                    FailureReason: item.FailureReason,
                    RecipientLabel: string.IsNullOrWhiteSpace(item.EmailMasked) ? "system" : item.EmailMasked,
                    DeliveryRef: item.DeliveryRef,
                    AttemptedAtUtc: item.AttemptedAtUtc.ToString("yyyy-MM-dd HH:mm 'UTC'")))
                .ToArray());
    }

    public async Task<BlackLedgerTickNewsNotificationBatchReceipt> NotifyTickNewsAsync(
        BlackLedgerWorldTickNewsEvent tickNews,
        bool dryRun,
        string? policyOverride,
        CancellationToken cancellationToken)
    {
        if (!IsPrivacySafe(tickNews))
        {
            BlackLedgerNewsDeliveryReceipt suppressed = BuildReceipt(
                tickNews,
                recipientUserId: string.Empty,
                recipientEmail: string.Empty,
                status: "suppressed_privacy_failed",
                deliveryRef: null,
                failureReason: "privacy_failed");
            if (!dryRun)
            {
                UpsertReceipt(suppressed);
            }

            return BuildBatchReceipt(
                tickNews,
                BlackLedgerNewsRecipientResolver.NormalizePolicy(policyOverride ?? _configuration["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"]),
                "suppressed_privacy_failed",
                dryRun,
                duplicate: false,
                failureReason: "privacy_failed",
                [suppressed]);
        }

        BlackLedgerNewsRecipientResolution resolution = _resolver.Resolve(tickNews.WorldId, policyOverride);
        if (!string.Equals(resolution.Status, "resolved", StringComparison.Ordinal))
        {
            BlackLedgerNewsDeliveryReceipt suppressed = BuildReceipt(
                tickNews,
                recipientUserId: string.Empty,
                recipientEmail: string.Empty,
                status: resolution.Status,
                deliveryRef: null,
                failureReason: resolution.FailureReason);
            if (!dryRun)
            {
                UpsertReceipt(suppressed);
            }

            return BuildBatchReceipt(tickNews, resolution.Policy, resolution.Status, dryRun, duplicate: false, resolution.FailureReason, [suppressed]);
        }

        var receipts = new List<BlackLedgerNewsDeliveryReceipt>();
        bool duplicate = true;
        foreach (BlackLedgerNewsRecipientCandidate recipient in resolution.Recipients)
        {
            string eventKey = BuildEventKey(tickNews, recipient.RecipientKey);
            BlackLedgerNewsDeliveryReceipt? existing = FindExistingReceipt(eventKey);
            if (existing is not null)
            {
                receipts.Add(existing);
                continue;
            }

            duplicate = false;
            if (dryRun)
            {
                receipts.Add(BuildReceipt(tickNews, recipient.RecipientUserId, recipient.Email, "pending_dry_run", null, null, eventKey));
                continue;
            }

            BlackLedgerNewsDeliveryReceipt pending = BuildReceipt(tickNews, recipient.RecipientUserId, recipient.Email, "pending", null, null, eventKey);
            UpsertReceipt(pending);

            try
            {
                if (!NotificationsEnabled())
                {
                    receipts.Add(FinalizeReceipt(pending, "suppressed_disabled", null, "notifications_disabled"));
                    continue;
                }

                if (!EaDispatchConfigured())
                {
                    receipts.Add(FinalizeReceipt(pending, "suppressed_delivery_unconfigured", null, "ea_dispatch_unconfigured"));
                    continue;
                }

                string deliveryRef = await SendToEaAsync(tickNews, recipient, cancellationToken);
                receipts.Add(FinalizeReceipt(pending, "sent", deliveryRef, null));
            }
            catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or InvalidOperationException or JsonException)
            {
                _logger.LogWarning(ex, "Black Ledger tick-news dispatch failed for {ReceiptId}.", pending.ReceiptId);
                receipts.Add(FinalizeReceipt(pending, "failed_delivery", null, Truncate(ex.Message, 400)));
            }
        }

        string batchStatus = dryRun
            ? "dry_run"
            : duplicate
                ? "duplicate"
                : receipts.All(static item => string.Equals(item.Status, "sent", StringComparison.OrdinalIgnoreCase))
                ? "sent"
                : receipts.Any(static item => string.Equals(item.Status, "sent", StringComparison.OrdinalIgnoreCase))
                    ? "partial"
                    : receipts.FirstOrDefault()?.Status ?? "suppressed_no_recipients";
        string? failureReason = receipts.Select(static item => item.FailureReason).FirstOrDefault(static item => !string.IsNullOrWhiteSpace(item));
        return BuildBatchReceipt(tickNews, resolution.Policy, batchStatus, dryRun, duplicate, failureReason, receipts);
    }

    public BlackLedgerWorldTickNewsEvent? BuildSeededWorldEvent(string worldId, int turn, string ledgerBaseUrl)
    {
        if (!string.Equals(worldId, "emerald-sprawl-prelude", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        BlackLedgerWorldPreviewViewModel? world = new BlackLedgerPublicStatsService(_configuration).LoadWorldPreview(turn);
        if (world?.LastTick is null || world.LastTick.Turn != turn)
        {
            return null;
        }

        return BuildEventFromWorldPreview(world, ledgerBaseUrl);
    }

    public BlackLedgerWorldTickNewsEvent BuildEventFromStoredProjections(WorldTickProjection worldTick, PlayerSafeNewsProjection news, string ledgerBaseUrl)
    {
        string trimmedBase = ledgerBaseUrl.TrimEnd('/');
        return new BlackLedgerWorldTickNewsEvent(
            WorldId: "emerald-sprawl-prelude",
            WorldName: news.Source,
            FromTurn: ExtractPreviousTurn(worldTick),
            ToTurn: ExtractCurrentTurn(worldTick),
            TickReceiptId: AccountService.NormalizeOptional(worldTick.WorldReceiptRef) ?? worldTick.WorldTickId,
            NewsId: news.NewsId,
            PublicHeadline: news.Title,
            PublicSummary: news.Summary,
            PublicHighlights: (news.EvidenceLines ?? Array.Empty<string>()).Take(3).ToArray(),
            LedgerUrl: $"{trimmedBase}/ledger",
            DispatchUrl: $"{trimmedBase}/ledger/dispatches/dispatch_turn_{ExtractCurrentTurn(worldTick):0000}_main",
            TickReceiptUrl: $"{trimmedBase}/ledger/closeouts",
            OccurredAtUtc: worldTick.UpdatedAtUtc);
    }

    private BlackLedgerWorldTickNewsEvent BuildEventFromWorldPreview(BlackLedgerWorldPreviewViewModel world, string ledgerBaseUrl)
    {
        string trimmedBase = ledgerBaseUrl.TrimEnd('/');
        BlackLedgerTickReceiptViewModel tick = world.LastTick ?? throw new InvalidOperationException("World preview is missing the last tick.");
        BlackLedgerWorldTurnBriefingViewModel? briefing = _briefings.BuildWorldTurnBriefing(tick.Turn, $"{trimmedBase}/ledger");
        string publicHeadline = briefing?.InboxHeadline ?? world.TurnHeadline;
        string publicSummary = briefing?.NewsreelLead ?? tick.Summary;
        IReadOnlyList<string> highlights = briefing?.NewsreelBullets ?? tick.Effects.Select(effect => $"{effect.Target}: {effect.PublicReason}").Take(4).ToArray();
        return new BlackLedgerWorldTickNewsEvent(
            WorldId: world.WorldId,
            WorldName: world.PublicName,
            FromTurn: briefing?.FromTurn ?? Math.Max(0, tick.Turn - 1),
            ToTurn: tick.Turn,
            TickReceiptId: tick.ReceiptId,
            NewsId: $"black_ledger_news_{world.WorldId}_{tick.Turn}",
            PublicHeadline: publicHeadline,
            PublicSummary: publicSummary,
            PublicHighlights: highlights,
            LedgerUrl: $"{trimmedBase}/ledger?turn={tick.Turn}",
            DispatchUrl: $"{trimmedBase}/ledger/dispatches/dispatch_turn_{tick.Turn:0000}_main",
            TickReceiptUrl: $"{trimmedBase}/ledger/closeouts",
            OccurredAtUtc: DateTimeOffset.TryParse(tick.CreatedAtUtc, out DateTimeOffset createdAtUtc) ? createdAtUtc : DateTimeOffset.UtcNow);
    }

    private BlackLedgerTickNewsNotificationBatchReceipt BuildBatchReceipt(
        BlackLedgerWorldTickNewsEvent tickNews,
        string policy,
        string status,
        bool dryRun,
        bool duplicate,
        string? failureReason,
        IReadOnlyList<BlackLedgerNewsDeliveryReceipt> receipts)
        => new(
            BatchId: $"blnewsbatch_{Guid.NewGuid():N}"[..21],
            Policy: policy,
            Status: status,
            WorldId: tickNews.WorldId,
            FromTurn: tickNews.FromTurn,
            ToTurn: tickNews.ToTurn,
            TickReceiptId: tickNews.TickReceiptId,
            NewsId: tickNews.NewsId,
            DryRun: dryRun,
            Duplicate: duplicate,
            RecipientCount: receipts.Count(static item => !string.IsNullOrWhiteSpace(item.RecipientUserId)),
            FailureReason: failureReason,
            Receipts: receipts);

    private BlackLedgerNewsDeliveryReceipt BuildReceipt(
        BlackLedgerWorldTickNewsEvent tickNews,
        string recipientUserId,
        string recipientEmail,
        string status,
        string? deliveryRef,
        string? failureReason,
        string? eventKey = null)
        => new(
            ReceiptId: $"{ReceiptPrefix}_{Guid.NewGuid():N}"[..21],
            EventType: EventType,
            EventKey: eventKey ?? BuildEventKey(tickNews, string.IsNullOrWhiteSpace(recipientUserId) ? "none" : $"user:{recipientUserId}"),
            WorldId: tickNews.WorldId,
            FromTurn: tickNews.FromTurn,
            ToTurn: tickNews.ToTurn,
            TickReceiptId: tickNews.TickReceiptId,
            NewsId: tickNews.NewsId,
            RecipientUserId: recipientUserId,
            EmailMasked: MaskEmail(recipientEmail),
            EmailHash: HashPrivate("email", recipientEmail),
            Status: status,
            DeliveryRef: deliveryRef,
            FailureReason: failureReason,
            CreatedAtUtc: DateTimeOffset.UtcNow,
            AttemptedAtUtc: DateTimeOffset.UtcNow);

    private BlackLedgerNewsDeliveryReceipt FinalizeReceipt(
        BlackLedgerNewsDeliveryReceipt receipt,
        string status,
        string? deliveryRef,
        string? failureReason)
    {
        BlackLedgerNewsDeliveryReceipt finalized = receipt with
        {
            Status = status,
            DeliveryRef = deliveryRef,
            FailureReason = failureReason,
            AttemptedAtUtc = DateTimeOffset.UtcNow,
        };
        UpsertReceipt(finalized);
        if (string.Equals(status, "sent", StringComparison.OrdinalIgnoreCase)
            && !string.IsNullOrWhiteSpace(finalized.RecipientUserId))
        {
            UpsertInboxEntries(finalized);
        }
        return finalized;
    }

    private void UpsertReceipt(BlackLedgerNewsDeliveryReceipt receipt)
    {
        lock (_store.Gate)
        {
            int index = _store.BlackLedgerNewsDeliveryReceipts.FindIndex(item => string.Equals(item.EventKey, receipt.EventKey, StringComparison.OrdinalIgnoreCase));
            if (index >= 0)
            {
                _store.BlackLedgerNewsDeliveryReceipts[index] = receipt;
            }
            else
            {
                _store.BlackLedgerNewsDeliveryReceipts.Add(receipt);
            }

            _store.BlackLedgerNewsDeliveryReceipts.Sort(static (left, right) => right.CreatedAtUtc.CompareTo(left.CreatedAtUtc));
            if (_store.BlackLedgerNewsDeliveryReceipts.Count > 256)
            {
                _store.BlackLedgerNewsDeliveryReceipts.RemoveRange(256, _store.BlackLedgerNewsDeliveryReceipts.Count - 256);
            }

            _store.PersistLocked();
        }
    }

    private void UpsertInboxEntries(BlackLedgerNewsDeliveryReceipt receipt)
    {
        BlackLedgerWorldTurnBriefingViewModel? briefing = _briefings.BuildWorldTurnBriefing(receipt.ToTurn);
        List<BlackLedgerInboxEntry> entries =
        [
            new(
                EntryId: $"blinbox_news_{receipt.RecipientUserId}_{receipt.TickReceiptId}",
                RecipientUserId: receipt.RecipientUserId,
                WorldId: receipt.WorldId,
                Turn: receipt.ToTurn,
                Kind: "newsreel",
                Eyebrow: "World turn",
                Heading: briefing?.InboxHeadline ?? $"World Turn {receipt.ToTurn} newsreel",
                Summary: briefing?.NewsreelLead ?? "World-turn newsreel is ready.",
                Href: $"/ledger/turns/{receipt.ToTurn}",
                CtaLabel: "Open newsreel",
                StatusLabel: "Delivered",
                SourceReceiptId: receipt.ReceiptId,
                CreatedAtUtc: receipt.CreatedAtUtc),
            new(
                EntryId: $"blinbox_validation_{receipt.RecipientUserId}_{receipt.TickReceiptId}",
                RecipientUserId: receipt.RecipientUserId,
                WorldId: receipt.WorldId,
                Turn: receipt.ToTurn,
                Kind: "validation",
                Eyebrow: "World state",
                Heading: "World-turn review packet",
                Summary: "Review the inbox-safe turn packet against the same world-turn truth.",
                Href: "/account/ledger/worldtick/validation",
                CtaLabel: "Open turn review",
                StatusLabel: "Ready",
                SourceReceiptId: receipt.ReceiptId,
                CreatedAtUtc: receipt.CreatedAtUtc)
        ];

        foreach (BlackLedgerFactionSummaryDto faction in _factions.ListFactionSummaries().Take(6))
        {
            string factionId = faction.FactionId.Replace('_', '-');
            BlackLedgerFactionPromoArtifactViewModel? promo = _factions.GetPromoArtifact(factionId);
            if (promo is null)
            {
                continue;
            }

            entries.Add(new BlackLedgerInboxEntry(
                EntryId: $"blinbox_promo_{receipt.RecipientUserId}_{receipt.TickReceiptId}_{factionId}",
                RecipientUserId: receipt.RecipientUserId,
                WorldId: receipt.WorldId,
                Turn: receipt.ToTurn,
                Kind: "promo",
                Eyebrow: "Faction promo",
                Heading: $"{promo.PublicName} motion promo rail",
                Summary: $"{promo.CampaignHook} {promo.AudiencePromise}",
                Href: promo.HtmlHref,
                CtaLabel: "Open promo rail",
                StatusLabel: "Public-safe",
                SourceReceiptId: receipt.ReceiptId,
                CreatedAtUtc: receipt.CreatedAtUtc));
            entries.Add(new BlackLedgerInboxEntry(
                EntryId: $"blinbox_leader_{receipt.RecipientUserId}_{receipt.TickReceiptId}_{factionId}",
                RecipientUserId: receipt.RecipientUserId,
                WorldId: receipt.WorldId,
                Turn: receipt.ToTurn,
                Kind: "leader_digest",
                Eyebrow: "Leader brief",
                Heading: $"{promo.PublicName} leader validation",
                Summary: "Personalized faction-leader readout and validation handoff for the current world turn.",
                Href: promo.ValidationHref,
                CtaLabel: "Open leader brief",
                StatusLabel: "Personalized",
                SourceReceiptId: receipt.ReceiptId,
                CreatedAtUtc: receipt.CreatedAtUtc));
        }

        lock (_store.Gate)
        {
            foreach (BlackLedgerInboxEntry entry in entries)
            {
                int index = _store.BlackLedgerInboxEntries.FindIndex(item => string.Equals(item.EntryId, entry.EntryId, StringComparison.OrdinalIgnoreCase));
                if (index >= 0)
                {
                    _store.BlackLedgerInboxEntries[index] = entry;
                }
                else
                {
                    _store.BlackLedgerInboxEntries.Add(entry);
                }
            }

            _store.BlackLedgerInboxEntries.Sort(static (left, right) => right.CreatedAtUtc.CompareTo(left.CreatedAtUtc));
            if (_store.BlackLedgerInboxEntries.Count > 512)
            {
                _store.BlackLedgerInboxEntries.RemoveRange(512, _store.BlackLedgerInboxEntries.Count - 512);
            }

            _store.PersistLocked();
        }
    }

    private BlackLedgerNewsDeliveryReceipt? FindExistingReceipt(string eventKey)
    {
        lock (_store.Gate)
        {
            return _store.BlackLedgerNewsDeliveryReceipts
                .FirstOrDefault(item => string.Equals(item.EventKey, eventKey, StringComparison.OrdinalIgnoreCase));
        }
    }

    private async Task<string> SendToEaAsync(
        BlackLedgerWorldTickNewsEvent tickNews,
        BlackLedgerNewsRecipientCandidate recipient,
        CancellationToken cancellationToken)
    {
        string apiToken = RequiredConfig(EaApiTokenConfigKey);
        string principalId = RequiredConfig(EaPrincipalIdConfigKey);
        string bindingId = RequiredConfig(EaBindingIdConfigKey);
        string baseUrl = (_configuration[EaBaseUrlConfigKey] ?? DefaultEaBaseUrl).Trim().TrimEnd('/');
        string idempotencyKey = BuildEventKey(tickNews, recipient.RecipientKey);
        var metadata = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase)
        {
            ["event_type"] = EventType,
            ["world_id"] = tickNews.WorldId,
            ["world_name"] = tickNews.WorldName,
            ["from_turn"] = tickNews.FromTurn,
            ["to_turn"] = tickNews.ToTurn,
            ["tick_receipt_id"] = tickNews.TickReceiptId,
            ["news_id"] = tickNews.NewsId,
            ["email_masked"] = MaskEmail(recipient.Email),
            ["email_hash"] = HashPrivate("email", recipient.Email),
            ["recipient_user_id"] = recipient.RecipientUserId,
            ["recipient_source"] = recipient.Source,
        };

        using var request = new HttpRequestMessage(HttpMethod.Post, $"{baseUrl}/v1/tools/execute");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiToken);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Headers.Add("x-ea-principal-id", principalId);
        request.Headers.Add("Idempotency-Key", idempotencyKey);
        request.Content = JsonContent.Create(new
        {
            tool_name = ConnectorDispatchTool,
            action_kind = DeliverySendAction,
            payload_json = new
            {
                principal_id = principalId,
                binding_id = bindingId,
                channel = EmailChannel,
                recipient = recipient.Email,
                subject = $"[Chummer] Black Ledger {tickNews.FromTurn}→{tickNews.ToTurn}: {tickNews.PublicHeadline}",
                content = BuildEmailBody(tickNews),
                metadata,
                idempotency_key = idempotencyKey,
            }
        });
        using HttpResponseMessage response = await _httpClient.SendAsync(request, cancellationToken);
        string responseBody = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"{(int)response.StatusCode}:{Truncate(responseBody, 600)}");
        }

        if (string.IsNullOrWhiteSpace(responseBody))
        {
            throw new InvalidOperationException("connector_dispatch_missing_delivery_id");
        }

        using JsonDocument json = JsonDocument.Parse(responseBody);
        if (json.RootElement.TryGetProperty("target_ref", out JsonElement targetRefElement)
            && !string.IsNullOrWhiteSpace(targetRefElement.GetString()))
        {
            return targetRefElement.GetString()!;
        }

        if (json.RootElement.TryGetProperty("output_json", out JsonElement outputJson)
            && outputJson.TryGetProperty("delivery_id", out JsonElement deliveryId)
            && !string.IsNullOrWhiteSpace(deliveryId.GetString()))
        {
            return deliveryId.GetString()!;
        }

        throw new InvalidOperationException("connector_dispatch_missing_delivery_id");
    }

    private bool NotificationsEnabled()
        => bool.TryParse(_configuration[EnabledConfigKey], out bool enabled) && enabled;

    private bool EaDispatchConfigured()
        => !string.IsNullOrWhiteSpace(_configuration[EaApiTokenConfigKey])
           && !string.IsNullOrWhiteSpace(_configuration[EaPrincipalIdConfigKey])
           && !string.IsNullOrWhiteSpace(_configuration[EaBindingIdConfigKey]);

    private bool IsPrivacySafe(BlackLedgerWorldTickNewsEvent tickNews)
    {
        string payload = string.Join(
            "\n",
            new[]
            {
                tickNews.WorldId,
                tickNews.WorldName,
                tickNews.TickReceiptId,
                tickNews.PublicHeadline,
                tickNews.PublicSummary,
                tickNews.LedgerUrl,
                tickNews.DispatchUrl,
                tickNews.TickReceiptUrl,
            }.Concat(tickNews.PublicHighlights ?? Array.Empty<string>()));
        string lowered = payload.ToLowerInvariant();
        return ForbiddenPrivacyTerms.All(term => !lowered.Contains(term, StringComparison.Ordinal));
    }

    private string BuildEmailBody(BlackLedgerWorldTickNewsEvent tickNews)
    {
        StringBuilder builder = new();
        builder.AppendLine($"{tickNews.PublicHeadline}");
        builder.AppendLine();
        builder.AppendLine($"World turn transition: Turn {tickNews.FromTurn} -> Turn {tickNews.ToTurn}.");
        builder.AppendLine();
        builder.AppendLine(tickNews.PublicSummary);
        builder.AppendLine();
        builder.AppendLine("Ledger dispatch:");
        if (tickNews.PublicHighlights.Count > 0)
        {
            foreach (string highlight in tickNews.PublicHighlights)
            {
                builder.Append("- ").AppendLine(highlight);
            }
        }
        else
        {
            builder.AppendLine("- Public-safe world movement posted for this turn.");
        }

        if (tickNews.PublicHighlights.Count > 0)
        {
            builder.AppendLine();
            builder.AppendLine("Read the dispatch and receipt:");
        }
        builder.AppendLine($"Dispatch: {tickNews.DispatchUrl}");
        builder.AppendLine($"Ledger: {tickNews.LedgerUrl}");
        builder.AppendLine($"Tick receipt lane: {tickNews.TickReceiptUrl}");
        builder.AppendLine($"Manage notifications: {tickNews.LedgerUrl}");
        AppendFactionPromoRail(builder);
        builder.AppendLine($"Receipt: {tickNews.TickReceiptId}");
        builder.AppendLine("Privacy note: public-safe aggregate/news only. No private campaign, support, or administrative data is included.");
        return builder.ToString().Trim();
    }

    private void AppendFactionPromoRail(StringBuilder builder)
    {
        IReadOnlyList<BlackLedgerFactionSummaryDto> factions = _factions.ListFactionSummaries();
        if (factions.Count == 0)
        {
            return;
        }

        builder.AppendLine();
        builder.AppendLine("Faction promo and validation lane:");
        foreach (BlackLedgerFactionSummaryDto faction in factions.Take(6))
        {
            string normalizedFactionId = faction.FactionId.Replace('_', '-');
            BlackLedgerFactionPromoArtifactViewModel? promo = _factions.GetPromoArtifact(normalizedFactionId);
            string promoHref = promo?.HtmlHref ?? $"/ledger/factions/{normalizedFactionId}/promo";
            string promoJsonHref = promo?.JsonHref ?? $"/ledger/factions/{normalizedFactionId}/promo.json";
            string validationHref = promo?.ValidationHref ?? $"/account/ledger/factions/{normalizedFactionId}/leader-briefing";
            builder.Append("- ")
                .Append(faction.PublicName)
                .Append(": promo ")
                .AppendLine(ToAbsoluteLedgerUrl(promoHref));
            builder.Append("  JSON: ").AppendLine(ToAbsoluteLedgerUrl(promoJsonHref));
            builder.Append("  Leader validation: ").AppendLine(ToAbsoluteLedgerUrl(validationHref));
        }
    }

    private static string ToAbsoluteLedgerUrl(string href)
    {
        if (string.IsNullOrWhiteSpace(href))
        {
            return "https://chummer.run/ledger";
        }

        if (Uri.TryCreate(href, UriKind.Absolute, out Uri? absolute))
        {
            return absolute.ToString();
        }

        return $"https://chummer.run{(href.StartsWith("/", StringComparison.Ordinal) ? href : $"/{href}")}";
    }

    private static string BuildEventKey(BlackLedgerWorldTickNewsEvent tickNews, string recipientKey)
        => $"black-ledger-news|{tickNews.WorldId}|{tickNews.ToTurn}|{tickNews.TickReceiptId}|{recipientKey}";

    private string HashPrivate(string label, string value)
    {
        string salt = _configuration[HashSaltConfigKey] ?? "black-ledger-news";
        byte[] bytes = SHA256.HashData(Encoding.UTF8.GetBytes($"{label}|{salt}|{value}".Trim()));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }

    private static string MaskEmail(string? email)
    {
        string normalized = AccountService.NormalizeOptional(email) ?? string.Empty;
        if (string.IsNullOrWhiteSpace(normalized) || !normalized.Contains('@', StringComparison.Ordinal))
        {
            return string.Empty;
        }

        string[] parts = normalized.Split('@', 2);
        string local = parts[0];
        string domain = parts[1];
        if (local.Length <= 1)
        {
            return $"*@{domain}";
        }

        return $"{local[0]}***@{domain}";
    }

    private string RequiredConfig(string key)
        => string.IsNullOrWhiteSpace(_configuration[key])
            ? throw new InvalidOperationException($"Missing required configuration: {key}")
            : _configuration[key]!.Trim();

    private static string Truncate(string value, int maxLength)
        => value.Length <= maxLength ? value : value[..maxLength];

    private static string BuildStatusLabel(string status)
        => status switch
        {
            "sent" => "Sent",
            "duplicate" => "Duplicate prevented",
            "pending_dry_run" or "dry_run" => "Dry run",
            "suppressed_disabled" => "Suppressed: disabled",
            "suppressed_no_recipients" => "Suppressed: no recipients",
            "suppressed_multiple_users_no_subscription" => "Suppressed: ambiguous recipients",
            "suppressed_delivery_unconfigured" => "Suppressed: delivery unconfigured",
            "suppressed_privacy_failed" => "Suppressed: privacy gate",
            "suppressed_not_current_recipient" => "Suppressed: not a current recipient",
            "failed_delivery" => "Delivery failed",
            _ => "Unconfigured"
        };

    private static string BuildStatusSummary(string status, string? failureReason, bool isRecipientScoped)
        => status switch
        {
            "sent" => "The current world-turn newsreel email was sent with a delivery receipt.",
            "duplicate" => "This world-turn newsreel was already delivered for the same event key, so a duplicate send was prevented.",
            "pending_dry_run" or "dry_run" => "The current world-turn newsreel was rendered in dry-run mode without sending email.",
            "suppressed_disabled" => "World-turn newsreel email is disabled on this runtime.",
            "suppressed_no_recipients" => "World-turn newsreel email had no eligible recipients on this runtime.",
            "suppressed_multiple_users_no_subscription" => "World-turn preview fallback refused delivery because multiple users exist without an explicit subscription.",
            "suppressed_delivery_unconfigured" => "World-turn newsreel email could not send because EA delivery configuration is missing.",
            "suppressed_privacy_failed" => "World-turn newsreel email was blocked by the privacy gate before delivery.",
            "suppressed_not_current_recipient" when isRecipientScoped => "A world-turn newsreel exists, but this account is not part of the current recipient policy.",
            "failed_delivery" => $"World-turn newsreel email attempted delivery, but the downstream dispatch failed{(string.IsNullOrWhiteSpace(failureReason) ? "." : $": {failureReason}.")}",
            _ => "World-turn newsreel email has not produced a usable receipt yet."
        };

    private static int ExtractCurrentTurn(WorldTickProjection worldTick)
    {
        string turnToken = worldTick.EvidenceLines.FirstOrDefault(line => line.Contains("BLACK LEDGER tick", StringComparison.OrdinalIgnoreCase))
            ?? worldTick.Summary;
        return int.TryParse(new string(turnToken.Where(char.IsDigit).ToArray()), out int parsed) && parsed > 0 ? parsed : 1;
    }

    private static int ExtractPreviousTurn(WorldTickProjection worldTick)
        => Math.Max(0, ExtractCurrentTurn(worldTick) - 1);
}

public sealed class BlackLedgerTickNewsDispatchWorker : BackgroundService
{
    private readonly CommunityStore _store;
    private readonly BlackLedgerTickNewsNotificationService _notifications;
    private readonly IConfiguration _configuration;
    private readonly ILogger<BlackLedgerTickNewsDispatchWorker> _logger;

    public BlackLedgerTickNewsDispatchWorker(
        CommunityStore store,
        BlackLedgerTickNewsNotificationService notifications,
        IConfiguration configuration,
        ILogger<BlackLedgerTickNewsDispatchWorker>? logger = null)
    {
        _store = store;
        _notifications = notifications;
        _configuration = configuration;
        _logger = logger ?? NullLogger<BlackLedgerTickNewsDispatchWorker>.Instance;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMinutes(2));
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await DispatchPendingAsync(stoppingToken);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                _logger.LogWarning(ex, "BLACK LEDGER tick-news dispatch worker encountered a non-blocking failure.");
            }

            if (!await timer.WaitForNextTickAsync(stoppingToken))
            {
                break;
            }
        }
    }

    private async Task DispatchPendingAsync(CancellationToken cancellationToken)
    {
        string baseUrl = (_configuration["CHUMMER_PUBLIC_BASE_URL"] ?? "https://chummer.run").Trim().TrimEnd('/');
        List<(WorldTickProjection WorldTick, PlayerSafeNewsProjection News)> pending;
        lock (_store.Gate)
        {
            pending = (
                from news in _store.PlayerSafeNews
                join tick in _store.WorldTicks on news.WorldTickId equals tick.WorldTickId
                where !_store.BlackLedgerNewsDeliveryReceipts.Any(receipt =>
                    string.Equals(receipt.TickReceiptId, AccountService.NormalizeOptional(tick.WorldReceiptRef) ?? tick.WorldTickId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(receipt.NewsId, news.NewsId, StringComparison.OrdinalIgnoreCase))
                select (tick, news))
                .Take(8)
                .ToList();
        }

        foreach ((WorldTickProjection worldTick, PlayerSafeNewsProjection news) in pending)
        {
            BlackLedgerWorldTickNewsEvent tickNews = _notifications.BuildEventFromStoredProjections(worldTick, news, baseUrl);
            await _notifications.NotifyTickNewsAsync(tickNews, dryRun: false, policyOverride: null, cancellationToken);
        }

        await DispatchSeededTurnOneCatchupAsync(baseUrl, cancellationToken);
    }

    private async Task DispatchSeededTurnOneCatchupAsync(string baseUrl, CancellationToken cancellationToken)
    {
        BlackLedgerWorldTickNewsEvent? seeded = _notifications.BuildSeededWorldEvent("emerald-sprawl-prelude", 1, baseUrl);
        if (seeded is null)
        {
            return;
        }

        bool alreadyExists = _notifications.ListReceipts(seeded.WorldId, seeded.ToTurn, take: 64)
            .Any(receipt =>
                string.Equals(receipt.TickReceiptId, seeded.TickReceiptId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(receipt.NewsId, seeded.NewsId, StringComparison.OrdinalIgnoreCase));
        if (alreadyExists)
        {
            return;
        }

        await _notifications.NotifyTickNewsAsync(seeded, dryRun: false, policyOverride: null, cancellationToken);
    }
}
