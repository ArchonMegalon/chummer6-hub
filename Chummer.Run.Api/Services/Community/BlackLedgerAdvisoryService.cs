using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed record BlackLedgerAdvisoryBallotDefinition(
    string BallotId,
    string FactionId,
    string Audience,
    string Heading,
    string Summary,
    string AdvisoryPosture,
    string ResultDestination,
    string DeliveryPosture,
    IReadOnlyList<BlackLedgerAdvisoryBallotOptionDefinition> Options);

public sealed record BlackLedgerAdvisoryBallotOptionDefinition(
    string OptionId,
    string Label,
    string Summary);

public sealed record BlackLedgerAdvisoryVoteReceipt(
    string ReceiptId,
    string BallotId,
    string FactionId,
    string Audience,
    string UserId,
    string OptionId,
    DateTimeOffset VotedAtUtc);

public sealed record BlackLedgerAdvisoryMailReceipt(
    string ReceiptId,
    string MailKind,
    string RecipientUserId,
    string FactionId,
    string Audience,
    string EmailMasked,
    string Status,
    string? DeliveryRef,
    DateTimeOffset CreatedAtUtc,
    string? FailureReason);

internal sealed record BlackLedgerAdvisoryRoleResolution(
    string? FactionId,
    bool IsPlayer,
    bool IsGameMaster,
    bool IsFactionLeader);

public sealed class BlackLedgerAdvisoryService
{
    private const string DefaultEaBaseUrl = "http://127.0.0.1:8090";
    private const string EmailChannel = "email";
    private const string ConnectorDispatchTool = "connector.dispatch";
    private const string DeliverySendAction = "delivery.send";
    private static readonly string[] GameMasterRoles = ["owner", "organizer", "manager", "admin", "gm"];
    private readonly HttpClient _httpClient;
    private readonly CommunityStore _store;
    private readonly IConfiguration _configuration;
    private readonly BlackLedgerFactionOnboardingService _factions;
    private readonly ILogger<BlackLedgerAdvisoryService> _logger;

    public BlackLedgerAdvisoryService(
        HttpClient httpClient,
        CommunityStore store,
        IConfiguration configuration,
        BlackLedgerFactionOnboardingService factions,
        ILogger<BlackLedgerAdvisoryService> logger)
    {
        _httpClient = httpClient;
        _store = store;
        _configuration = configuration;
        _factions = factions;
        _logger = logger;
    }

    public BlackLedgerAdvisorySummaryViewModel BuildSummary(HubUserDto user)
    {
        BlackLedgerAdvisoryRoleResolution role = ResolveRole(user);
        IReadOnlyList<BlackLedgerAdvisoryBallotDefinition> ballots = ListBallots(role.FactionId);
        IReadOnlyList<BlackLedgerAdvisoryBallotViewModel> playerBallots = role.IsPlayer
            ? ballots.Where(static item => string.Equals(item.Audience, "player", StringComparison.OrdinalIgnoreCase))
                .Select(item => BuildBallotViewModel(item, user.UserId, role.IsPlayer))
                .ToArray()
            : Array.Empty<BlackLedgerAdvisoryBallotViewModel>();
        IReadOnlyList<BlackLedgerAdvisoryBallotViewModel> gmBallots = role.IsGameMaster
            ? ballots.Where(static item => string.Equals(item.Audience, "gm", StringComparison.OrdinalIgnoreCase))
                .Select(item => BuildBallotViewModel(item, user.UserId, role.IsGameMaster))
                .ToArray()
            : Array.Empty<BlackLedgerAdvisoryBallotViewModel>();
        IReadOnlyList<BlackLedgerAdvisoryExecutiveSummaryViewModel> executiveSummaries = BuildExecutiveSummaries(role);
        string factionSlug = role.FactionId ?? "emerald-sprawl-prelude";

        return new BlackLedgerAdvisorySummaryViewModel(
            Heading: "Advisory voting lane",
            Intro: "Players can pressure the agenda. Game Masters can recommend strategy. Both loops feed upward, but neither becomes sovereign authority.",
            NoDemocracyNote: "Black Ledger treats this as advisory signal, not binding democracy. Players inform GMs. GMs inform the faction leader. The leader may ratify, reshape, or override the result.",
            OpenMailHref: $"/account/ledger/advisory?faction={factionSlug}",
            PlayerBallots: playerBallots,
            GmBallots: gmBallots,
            ExecutiveSummaries: executiveSummaries);
    }

    public BlackLedgerAdvisoryPageViewModel BuildPage(SiteChromeViewModel chrome, HubUserDto user)
        => new(
            Chrome: chrome,
            Heading: "Black Ledger advisory voting",
            Intro: "This is the controlled feedback lane for players, GMs, and faction leadership. The stack is meant to be legible, persuasive, and explicitly non-democratic.",
            Summary: BuildSummary(user));

    public object BuildSummaryJson(HubUserDto user)
    {
        BlackLedgerAdvisoryRoleResolution role = ResolveRole(user);
        BlackLedgerAdvisorySummaryViewModel summary = BuildSummary(user);
        return new
        {
            faction_id = role.FactionId,
            is_player = role.IsPlayer,
            is_game_master = role.IsGameMaster,
            is_faction_leader = role.IsFactionLeader,
            no_democracy_note = summary.NoDemocracyNote,
            player_ballots = summary.PlayerBallots,
            gm_ballots = summary.GmBallots,
            executive_summaries = summary.ExecutiveSummaries
        };
    }

    public void SubmitVote(HubUserDto user, string ballotId, string optionId)
    {
        BlackLedgerAdvisoryRoleResolution role = ResolveRole(user);
        BlackLedgerAdvisoryBallotDefinition ballot = ListBallots(role.FactionId)
            .FirstOrDefault(item => string.Equals(item.BallotId, Normalize(ballotId), StringComparison.OrdinalIgnoreCase))
            ?? throw new InvalidOperationException("Unknown advisory ballot.");
        if (string.Equals(ballot.Audience, "player", StringComparison.OrdinalIgnoreCase) && !role.IsPlayer)
        {
            throw new InvalidOperationException("Player advisory voting requires an active faction allegiance.");
        }

        if (string.Equals(ballot.Audience, "gm", StringComparison.OrdinalIgnoreCase) && !role.IsGameMaster)
        {
            throw new InvalidOperationException("GM strategy voting requires GM posture on the active faction lane.");
        }

        if (!ballot.Options.Any(item => string.Equals(item.OptionId, Normalize(optionId), StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidOperationException("Unknown advisory option.");
        }

        BlackLedgerAdvisoryVoteReceipt receipt = new(
            ReceiptId: AccountService.NewId("blvote"),
            BallotId: ballot.BallotId,
            FactionId: ballot.FactionId,
            Audience: ballot.Audience,
            UserId: user.UserId,
            OptionId: Normalize(optionId),
            VotedAtUtc: DateTimeOffset.UtcNow);

        lock (_store.Gate)
        {
            _store.BlackLedgerAdvisoryVoteReceipts.RemoveAll(item =>
                string.Equals(item.BallotId, receipt.BallotId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.UserId, receipt.UserId, StringComparison.OrdinalIgnoreCase));
            _store.BlackLedgerAdvisoryVoteReceipts.Add(receipt);
            _store.BlackLedgerAdvisoryVoteReceipts.Sort(static (left, right) => right.VotedAtUtc.CompareTo(left.VotedAtUtc));
            if (_store.BlackLedgerAdvisoryVoteReceipts.Count > 2048)
            {
                _store.BlackLedgerAdvisoryVoteReceipts.RemoveRange(2048, _store.BlackLedgerAdvisoryVoteReceipts.Count - 2048);
            }

            _store.PersistLocked();
        }
    }

    public async Task<IReadOnlyList<BlackLedgerAdvisoryMailReceipt>> SendCurrentMailshotsAsync(CancellationToken cancellationToken)
    {
        var receipts = new List<BlackLedgerAdvisoryMailReceipt>();
        foreach (HubUserDto user in ListEligibleUsers())
        {
            BlackLedgerAdvisoryRoleResolution role = ResolveRole(user);
            if (string.IsNullOrWhiteSpace(role.FactionId) || string.IsNullOrWhiteSpace(user.Email))
            {
                continue;
            }

            if (role.IsPlayer)
            {
                receipts.Add(await SendMailAsync(user, role, "player_vote", cancellationToken));
            }

            if (role.IsGameMaster)
            {
                receipts.Add(await SendMailAsync(user, role, "gm_vote", cancellationToken));
            }

            if (role.IsFactionLeader)
            {
                receipts.Add(await SendMailAsync(user, role, "leader_summary", cancellationToken));
            }
        }

        return receipts;
    }

    private IReadOnlyList<HubUserDto> ListEligibleUsers()
    {
        lock (_store.Gate)
        {
            return _store.UsersById.Values
                .Where(user => _factions.GetAllegiance(user) is not null && !string.IsNullOrWhiteSpace(user.Email))
                .OrderBy(static item => item.DisplayName, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }
    }

    private async Task<BlackLedgerAdvisoryMailReceipt> SendMailAsync(
        HubUserDto user,
        BlackLedgerAdvisoryRoleResolution role,
        string mailKind,
        CancellationToken cancellationToken)
    {
        string factionId = role.FactionId ?? throw new InvalidOperationException("Faction context is required.");
        string eventKey = $"{mailKind}|{factionId}|{user.UserId}";
        lock (_store.Gate)
        {
            BlackLedgerAdvisoryMailReceipt? existing = _store.BlackLedgerAdvisoryMailReceipts.FirstOrDefault(item =>
                string.Equals(item.MailKind, mailKind, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.RecipientUserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.FactionId, factionId, StringComparison.OrdinalIgnoreCase));
            if (existing is not null)
            {
                return existing;
            }
        }

        BlackLedgerAdvisoryMailReceipt pending = new(
            ReceiptId: AccountService.NewId("blmail"),
            MailKind: mailKind,
            RecipientUserId: user.UserId,
            FactionId: factionId,
            Audience: mailKind,
            EmailMasked: MaskEmail(user.Email),
            Status: "pending",
            DeliveryRef: null,
            CreatedAtUtc: DateTimeOffset.UtcNow,
            FailureReason: null);
        UpsertMailReceipt(pending);

        try
        {
            if (!NotificationsEnabled() || !EaDispatchConfigured())
            {
                return FinalizeMailReceipt(pending, "suppressed_delivery_unconfigured", null, "ea_dispatch_unconfigured");
            }

            string deliveryRef = await SendToEaAsync(user, role, mailKind, eventKey, cancellationToken).ConfigureAwait(false);
            return FinalizeMailReceipt(pending, "sent", deliveryRef, null);
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or InvalidOperationException or JsonException)
        {
            _logger.LogWarning(ex, "Black Ledger advisory mailshot failed for {UserId} {MailKind}.", user.UserId, mailKind);
            return FinalizeMailReceipt(pending, "failed_delivery", null, ex.Message);
        }
    }

    private async Task<string> SendToEaAsync(
        HubUserDto user,
        BlackLedgerAdvisoryRoleResolution role,
        string mailKind,
        string idempotencyKey,
        CancellationToken cancellationToken)
    {
        string apiToken = RequiredConfig("CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN");
        string principalId = RequiredConfig("CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID");
        string bindingId = RequiredConfig("CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID");
        string baseUrl = (_configuration["CHUMMER_BLACK_LEDGER_NEWS_EA_BASE_URL"] ?? DefaultEaBaseUrl).Trim().TrimEnd('/');

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
                recipient = user.Email.Trim(),
                subject = BuildMailSubject(role, mailKind),
                content = BuildMailBody(user, role, mailKind),
                metadata = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase)
                {
                    ["mail_kind"] = mailKind,
                    ["faction_id"] = role.FactionId ?? string.Empty,
                    ["recipient_user_id"] = user.UserId
                },
                idempotency_key = idempotencyKey
            }
        });

        using HttpResponseMessage response = await _httpClient.SendAsync(request, cancellationToken).ConfigureAwait(false);
        string responseBody = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"{(int)response.StatusCode}:{responseBody}");
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

    private BlackLedgerAdvisoryMailReceipt FinalizeMailReceipt(BlackLedgerAdvisoryMailReceipt receipt, string status, string? deliveryRef, string? failureReason)
    {
        BlackLedgerAdvisoryMailReceipt finalized = receipt with
        {
            Status = status,
            DeliveryRef = deliveryRef,
            FailureReason = failureReason
        };
        UpsertMailReceipt(finalized);
        return finalized;
    }

    private void UpsertMailReceipt(BlackLedgerAdvisoryMailReceipt receipt)
    {
        lock (_store.Gate)
        {
            int index = _store.BlackLedgerAdvisoryMailReceipts.FindIndex(item =>
                string.Equals(item.MailKind, receipt.MailKind, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.RecipientUserId, receipt.RecipientUserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.FactionId, receipt.FactionId, StringComparison.OrdinalIgnoreCase));
            if (index >= 0)
            {
                _store.BlackLedgerAdvisoryMailReceipts[index] = receipt;
            }
            else
            {
                _store.BlackLedgerAdvisoryMailReceipts.Add(receipt);
            }

            _store.BlackLedgerAdvisoryMailReceipts.Sort(static (left, right) => right.CreatedAtUtc.CompareTo(left.CreatedAtUtc));
            _store.PersistLocked();
        }
    }

    private BlackLedgerAdvisoryBallotViewModel BuildBallotViewModel(BlackLedgerAdvisoryBallotDefinition ballot, string userId, bool mayVote)
    {
        IReadOnlyList<BlackLedgerAdvisoryVoteReceipt> votes = ListVotes(ballot.BallotId);
        int totalVotes = votes.Count;
        BlackLedgerAdvisoryVoteReceipt? selected = votes.FirstOrDefault(item => string.Equals(item.UserId, userId, StringComparison.OrdinalIgnoreCase));
        return new BlackLedgerAdvisoryBallotViewModel(
            BallotId: ballot.BallotId,
            Audience: ballot.Audience,
            AudienceLabel: string.Equals(ballot.Audience, "gm", StringComparison.OrdinalIgnoreCase) ? "Game Master vote" : "Player vote",
            Heading: ballot.Heading,
            Summary: ballot.Summary,
            AdvisoryPosture: ballot.AdvisoryPosture,
            ResultDestination: ballot.ResultDestination,
            DeliveryPosture: ballot.DeliveryPosture,
            StatusLabel: totalVotes > 0 ? $"{totalVotes} advisory vote(s)" : "Open",
            UserMayVote: mayVote,
            SelectedOptionId: selected?.OptionId,
            Options: ballot.Options.Select(option =>
            {
                int optionVotes = votes.Count(item => string.Equals(item.OptionId, option.OptionId, StringComparison.OrdinalIgnoreCase));
                string share = totalVotes <= 0 ? "0%" : $"{Math.Round(optionVotes * 100d / totalVotes, MidpointRounding.AwayFromZero):0}%";
                return new BlackLedgerAdvisoryOptionViewModel(
                    OptionId: option.OptionId,
                    Label: option.Label,
                    Summary: option.Summary,
                    VoteCount: optionVotes,
                    VoteShareLabel: share,
                    Selected: string.Equals(selected?.OptionId, option.OptionId, StringComparison.OrdinalIgnoreCase));
            }).ToArray());
    }

    private IReadOnlyList<BlackLedgerAdvisoryExecutiveSummaryViewModel> BuildExecutiveSummaries(BlackLedgerAdvisoryRoleResolution role)
    {
        if (string.IsNullOrWhiteSpace(role.FactionId))
        {
            return Array.Empty<BlackLedgerAdvisoryExecutiveSummaryViewModel>();
        }

        BlackLedgerFactionDetailDto? detail = _factions.GetWorkspaceFactionDetail(role.FactionId);
        if (detail is null)
        {
            return Array.Empty<BlackLedgerAdvisoryExecutiveSummaryViewModel>();
        }

        List<BlackLedgerAdvisoryBallotDefinition> gmBallots = ListBallots(role.FactionId)
            .Where(static item => string.Equals(item.Audience, "gm", StringComparison.OrdinalIgnoreCase))
            .ToList();
        if (gmBallots.Count == 0)
        {
            return Array.Empty<BlackLedgerAdvisoryExecutiveSummaryViewModel>();
        }

        List<string> highlights = new();
        foreach (BlackLedgerAdvisoryBallotDefinition ballot in gmBallots)
        {
            IReadOnlyList<BlackLedgerAdvisoryVoteReceipt> votes = ListVotes(ballot.BallotId);
            BlackLedgerAdvisoryBallotOptionDefinition? top = ballot.Options
                .OrderByDescending(option => votes.Count(item => string.Equals(item.OptionId, option.OptionId, StringComparison.OrdinalIgnoreCase)))
                .ThenBy(option => option.Label, StringComparer.OrdinalIgnoreCase)
                .FirstOrDefault();
            if (top is null)
            {
                continue;
            }

            int count = votes.Count(item => string.Equals(item.OptionId, top.OptionId, StringComparison.OrdinalIgnoreCase));
            highlights.Add($"{ballot.Heading}: {top.Label} is leading with {count} GM vote(s).");
        }

        return
        [
            new BlackLedgerAdvisoryExecutiveSummaryViewModel(
                FactionId: role.FactionId,
                Heading: $"{detail.PublicName} executive intake",
                Summary: "Faction leadership receives the GM recommendation stack as advisory pressure, not as binding command. The leader may take it, reshape it, or discard it.",
                ExecutivePosture: "Megacorp executive doctrine: signal is welcome; sovereignty stays at the top of the chain.",
                Highlights: highlights)
        ];
    }

    private IReadOnlyList<BlackLedgerAdvisoryVoteReceipt> ListVotes(string ballotId)
    {
        lock (_store.Gate)
        {
            return _store.BlackLedgerAdvisoryVoteReceipts
                .Where(item => string.Equals(item.BallotId, ballotId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.VotedAtUtc)
                .ToArray();
        }
    }

    private IReadOnlyList<BlackLedgerAdvisoryBallotDefinition> ListBallots(string? factionId)
    {
        string normalizedFactionId = Normalize(string.IsNullOrWhiteSpace(factionId) ? "ashline-circle" : factionId);
        BlackLedgerFactionDetailDto? detail = _factions.GetWorkspaceFactionDetail(normalizedFactionId) ?? _factions.GetFactionDetail(normalizedFactionId);
        string name = detail?.PublicName ?? "Faction";
        return
        [
            new(
                BallotId: $"player-run-{normalizedFactionId}",
                FactionId: normalizedFactionId,
                Audience: "player",
                Heading: "Which run pressure should your GMs build around next?",
                Summary: $"Players can signal the run appetite for {name}. GMs receive the topline and can use it as a creative constraint, a prompt, or a rejection point.",
                AdvisoryPosture: "Player votes are advisory. They pressure the agenda; they do not command the table.",
                ResultDestination: "Topline goes to the GMs for this faction.",
                DeliveryPosture: "Use this to show real demand for run arcs, not to elect content by plebiscite.",
                Options:
                [
                    new("supply-heist", "Supply heist escalation", "A high-visibility smash-and-grab against rival logistics or protected stock."),
                    new("research-extraction", "Research extraction", "A stealth or hybrid operation to steal talent, prototypes, or results before competitors lock them down."),
                    new("hardware-recovery", "Hardware recovery", "A field run focused on recovering bleeding-edge gear for the faction pool.")
                ]),
            new(
                BallotId: $"player-research-{normalizedFactionId}",
                FactionId: normalizedFactionId,
                Audience: "player",
                Heading: "What research track feels most worth faction effort?",
                Summary: $"Players can tell the GMs which research and progression fantasy feels hottest inside {name} right now.",
                AdvisoryPosture: "This is signal for pacing and rewards, not a direct order to the world state.",
                ResultDestination: "Topline goes to the GMs for reward and scenario shaping.",
                DeliveryPosture: "Research demand can be honored directly, translated into another artifact, or deliberately denied for tension.",
                Options:
                [
                    new("matrix-protocols", "Matrix protocols", "Signal appetite for intel nets, decker toys, and breach-forward progression."),
                    new("ritual-shielding", "Ritual shielding", "Signal appetite for occult protection, warding, and magical posture."),
                    new("drone-autonomy", "Drone autonomy", "Signal appetite for drones, rigging, and hard-tech escalation.")
                ]),
            new(
                BallotId: $"gm-strategy-{normalizedFactionId}",
                FactionId: normalizedFactionId,
                Audience: "gm",
                Heading: "What strategic line should the faction leader see from the GM desk?",
                Summary: $"GMs can align on the strategic recommendation they want to carry upward for {name}. The leader sees the signal and may ratify, reshape, or override it.",
                AdvisoryPosture: "GM votes are advisory to the leader. They are operational recommendations, not constitutional law.",
                ResultDestination: "Topline goes to the faction leader.",
                DeliveryPosture: "A megacorp can listen closely and still say no.",
                Options:
                [
                    new("consolidate", "Consolidate and lower heat", "Stabilize holdings, harden routes, and trade tempo for resilience."),
                    new("expand", "Expand under pressure", "Push territory and package presence even at higher operational risk."),
                    new("covert", "Stay covert and shape the board indirectly", "Prioritize proxies, deniability, and low-signature leverage.")
                ])
        ];
    }

    private BlackLedgerAdvisoryRoleResolution ResolveRole(HubUserDto user)
    {
        BlackLedgerAccountFactionAllegianceDto? allegiance = _factions.GetAllegiance(user);
        string? factionId = allegiance?.ActiveFactionId.Replace('_', '-');
        bool isPlayer = allegiance is not null;
        bool isGameMaster = false;
        bool isFactionLeader = false;

        lock (_store.Gate)
        {
            foreach (string groupId in user.GroupIds ?? Array.Empty<string>())
            {
                if (!_store.GroupsById.TryGetValue(groupId, out GroupDto? group))
                {
                    continue;
                }

                GroupMembershipDto? membership = group.Memberships.FirstOrDefault(item => string.Equals(item.UserId, user.UserId, StringComparison.OrdinalIgnoreCase));
                if (membership is not null && GameMasterRoles.Contains(Normalize(membership.Role), StringComparer.OrdinalIgnoreCase))
                {
                    isGameMaster = true;
                    break;
                }
            }
        }

        if (!isGameMaster && allegiance is not null && allegiance.MembershipType.StartsWith("founder_", StringComparison.OrdinalIgnoreCase))
        {
            isGameMaster = true;
        }

        if (!string.IsNullOrWhiteSpace(factionId))
        {
            BlackLedgerFactionCharterDto? charter = _factions.GetCharter(factionId);
            isFactionLeader = charter is not null
                && string.Equals(charter.FounderAccountId, user.UserId, StringComparison.OrdinalIgnoreCase);
        }

        return new BlackLedgerAdvisoryRoleResolution(factionId, isPlayer, isGameMaster, isFactionLeader);
    }

    private static string BuildMailSubject(BlackLedgerAdvisoryRoleResolution role, string mailKind)
        => mailKind switch
        {
            "player_vote" => "[Chummer] Black Ledger player advisory voting is open",
            "gm_vote" => "[Chummer] Black Ledger GM strategy recommendation lane is open",
            "leader_summary" => "[Chummer] Black Ledger GM strategy signal reached executive intake",
            _ => $"[Chummer] Black Ledger advisory update for {role.FactionId}"
        };

    private string BuildMailBody(HubUserDto user, BlackLedgerAdvisoryRoleResolution role, string mailKind)
    {
        string factionId = role.FactionId ?? "ashline-circle";
        string advisoryHref = $"{LedgerBaseUrl().TrimEnd('/')}/account/ledger/advisory";
        return mailKind switch
        {
            "player_vote" => $"""
                Black Ledger advisory voting is open.

                You can now tell the Game Masters which runs, research, or hardware feel worth pushing next.
                That signal goes to the GM desk. It does not bind the world. The megacorp is not a democracy.

                Open the advisory lane:
                {advisoryHref}

                Faction lane:
                {LedgerBaseUrl().TrimEnd('/')}/account/ledger/factions/{factionId}
                """,
            "gm_vote" => $"""
                Black Ledger GM strategy voting is open.

                Player demand is ready for review, and the GM desk can now send a strategic recommendation upward.
                The faction leader receives that recommendation and may ratify, reshape, or override it. The megacorp is not a democracy.

                Open the advisory lane:
                {advisoryHref}

                Leader intake:
                {LedgerBaseUrl().TrimEnd('/')}/account/ledger/factions/{factionId}/leader-briefing
                """,
            _ => $"""
                Black Ledger executive intake has fresh GM strategy signal.

                This is advisory command pressure from the GM desk, not a binding vote.
                Review it, use it, or overrule it. The megacorp is not a democracy.

                Open the advisory lane:
                {advisoryHref}
                """
        };
    }

    private string LedgerBaseUrl()
        => (_configuration["CHUMMER_PUBLIC_BASE_URL"] ?? "https://chummer.run").Trim().TrimEnd('/');

    private bool NotificationsEnabled()
        => bool.TryParse(_configuration["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"], out bool enabled) && enabled;

    private bool EaDispatchConfigured()
        => !string.IsNullOrWhiteSpace(_configuration["CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN"])
           && !string.IsNullOrWhiteSpace(_configuration["CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID"])
           && !string.IsNullOrWhiteSpace(_configuration["CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID"]);

    private string RequiredConfig(string key)
        => _configuration[key]?.Trim() ?? throw new InvalidOperationException($"{key} missing");

    private static string Normalize(string? value)
        => string.IsNullOrWhiteSpace(value) ? string.Empty : value.Trim().Replace('_', '-').ToLowerInvariant();

    private static string MaskEmail(string? email)
    {
        if (string.IsNullOrWhiteSpace(email))
        {
            return "unknown";
        }

        int atIndex = email.IndexOf('@', StringComparison.Ordinal);
        if (atIndex <= 1)
        {
            return "***";
        }

        return $"{email[0]}***{email[(atIndex - 1)..]}";
    }
}
