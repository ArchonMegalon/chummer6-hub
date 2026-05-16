using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class BlackLedgerFactionOnboardingService
{
    private const string WorldId = "emerald-sprawl-prelude";
    private static readonly string[] ForbiddenFactionNameTerms =
    [
        "ares",
        "aztechnology",
        "renraku",
        "mitsuhama",
        "saeder",
        "shiawase",
        "horizon",
        "neonet",
        "spinrad",
        "evo",
        "shadowrun",
        "sourcebook",
        "fuck",
        "shit",
        "nigger",
        "retard"
    ];
    private readonly object _gate;
    private readonly BlackLedgerPublicStatsService _stats;
    private readonly CampaignSpineService _campaignSpine;
    private readonly CommunityStore _store;
    private BlackLedgerFactionOnboardingState _state = new();

    public BlackLedgerFactionOnboardingService(
        IConfiguration configuration,
        BlackLedgerPublicStatsService stats,
        CampaignSpineService campaignSpine,
        CommunityStore store)
    {
        _ = configuration;
        _stats = stats;
        _campaignSpine = campaignSpine;
        _store = store;
        _gate = store.Gate;
        Load();
    }

    public bool HasActiveAllegiance(string userId)
        => GetAllegianceByUserId(userId) is not null;

    public BlackLedgerAccountFactionAllegianceDto? GetAllegiance(HubUserDto user)
        => GetAllegianceByUserId(user.UserId);

    public BlackLedgerFactionOnboardingViewModel BuildOnboardingModel(SiteChromeViewModel chrome, HubUserDto user, string? currentStep = null)
    {
        var world = _stats.LoadWorldPreview() ?? throw new InvalidOperationException("Black Ledger world preview is unavailable.");
        var allegiance = GetAllegiance(user);
        var summary = _campaignSpine.GetAccountSummary(user);
        var runnerIds = SelectRealRunnerIds(summary.Dossiers);
        var factionOptions = world.Factions
            .OrderBy(static faction => faction.PublicName, StringComparer.OrdinalIgnoreCase)
            .Select(faction => new BlackLedgerFactionJoinOptionViewModel(
                faction.Id.Replace('_', '-'),
                faction.PublicName,
                faction.Type,
                string.Join(" · ", faction.PublicSignals.Take(3)),
                $"/ledger/factions/{faction.Id.Replace('_', '-')}"))
            .ToArray();
        var majorAvailability = BuildMajorSlotAvailability();
        string step = string.IsNullOrWhiteSpace(currentStep) ? "welcome" : NormalizeToken(currentStep).ToLowerInvariant();
        var steps = BuildWizardSteps(step);

        return new BlackLedgerFactionOnboardingViewModel(
            Chrome: chrome,
            Heading: "Choose your flag.",
            Intro: "Black Ledger is a living campaign layer. Your account joins one faction, and all of your current and future runners carry that allegiance.",
            HasActiveAllegiance: allegiance is not null,
            CurrentAllegiance: allegiance,
            CurrentStep: step,
            CurrentRunnerCount: runnerIds.Count,
            Steps: steps,
            ExistingFactionSummary: "Join a house that already has pressure, history, and enemies.",
            MajorFounderSummary: "Found a Major Faction. Major Charter Slots are limited. You start stronger, with more points and a claim to the map.",
            ChallengerFounderSummary: "Found a Challenger Faction. You start weaker, with fewer points and more risk. You can still challenge larger factions and force your way onto the map.",
            MajorSlotsWarning: majorAvailability.MajorSlotsAvailable > 0
                ? null
                : "All Major Charter Slots are taken. You can still found a Challenger Faction. It starts weaker, but it can challenge larger factions through play.",
            MajorSlotsAvailable: majorAvailability.MajorSlotsAvailable,
            ExistingFactions: factionOptions);
    }

    public BlackLedgerFactionHomeViewModel BuildFactionHome(SiteChromeViewModel chrome, HubUserDto user)
    {
        var allegiance = GetAllegiance(user) ?? throw new InvalidOperationException("No active faction allegiance.");
        var detail = GetWorkspaceFactionDetail(allegiance.ActiveFactionId) ?? throw new InvalidOperationException("Faction detail missing.");
        var welcomeKit = new[]
        {
            $"{detail.PublicName} welcome kit",
            $"{detail.PublicName} badge unlocked",
            "Runner Passport stamp queued",
            "First task: Gather receipts"
        };

        return new BlackLedgerFactionHomeViewModel(
            Chrome: chrome,
            Heading: "Your runners carry this banner.",
            Intro: "Your account allegiance applies to all current and future runners. Weekly dispatch hooks, badge posture, and the first task all start from this one route.",
            Allegiance: allegiance,
            Faction: detail,
            WelcomeKit: welcomeKit,
            RecentActionReceipts: GetActionReceipts(detail.FactionId).Take(5).ToArray());
    }

    public BlackLedgerFactionCreatePageViewModel BuildCreatePage(SiteChromeViewModel chrome, HubUserDto user, string? preferredCharterType = null)
    {
        _ = user;
        var majorAvailability = BuildMajorSlotAvailability();
        string charterType = NormalizeCharterType(preferredCharterType);
        var world = _stats.LoadWorldPreview() ?? throw new InvalidOperationException("Black Ledger world preview is unavailable.");
        var rivals = world.Factions
            .OrderBy(static faction => faction.PublicName, StringComparer.OrdinalIgnoreCase)
            .Select(faction => new BlackLedgerFactionJoinOptionViewModel(
                faction.Id.Replace('_', '-'),
                faction.PublicName,
                faction.Type,
                string.Join(" · ", faction.PublicSignals.Take(2)),
                $"/ledger/factions/{faction.Id.Replace('_', '-')}"))
            .ToArray();
        return new BlackLedgerFactionCreatePageViewModel(
            Chrome: chrome,
            Heading: "Build a faction charter.",
            Intro: "Choose a charter type, spend the exact point budget, take the required flaws, and start from a bounded MVP rule set.",
            PreferredCharterType: charterType,
            MajorSlotsAvailable: majorAvailability.MajorSlotsAvailable,
            MajorRules: BuildCharterRules("major"),
            ChallengerRules: BuildCharterRules("challenger"),
            Archetypes: Archetypes,
            Perks: Perks,
            Flaws: Flaws,
            StartingDistrictIds: world.Districts.Select(static district => district.Id).ToArray(),
            RivalFactions: rivals);
    }

    public BlackLedgerFactionJoinReceiptDto JoinFaction(HubUserDto user, string factionId)
    {
        string normalizedFactionId = NormalizeFactionId(factionId);
        if (GetWorkspaceFactionDetail(normalizedFactionId) is null)
        {
            throw new InvalidOperationException("Unknown faction.");
        }

        var now = DateTimeOffset.UtcNow;
        EnsureAllegianceChangeAllowed(user.UserId, normalizedFactionId, now);
        var membership = BuildRunnerMembershipSnapshot(user);
        var receipt = new BlackLedgerFactionJoinReceiptDto(
            ReceiptId: NewId("fmem"),
            AccountIdHash: Hash(user.UserId),
            FactionId: normalizedFactionId,
            MembershipType: "joined_existing",
            AppliesToAllRunners: true,
            RunnerCount: membership.RunnerIds.Count,
            FutureRunnersInherit: true,
            CreatedAtUtc: now,
            PrivacyResult: "passed",
            PublicProjectionAllowed: false);
        var allegiance = new BlackLedgerAccountFactionAllegianceDto(
            AccountId: user.UserId,
            ActiveFactionId: normalizedFactionId,
            MembershipType: "joined_existing",
            AppliesToAllCurrentRunners: true,
            AppliesToAllFutureRunners: true,
            JoinedAtUtc: now,
            LockUntilUtc: now.AddDays(30),
            SwitchCount: GetSwitchCount(user.UserId) + 1,
            CurrentRunnerIdsSnapshot: membership.RunnerIds,
            ReceiptId: receipt.ReceiptId,
            PublicProjectionAllowed: false,
            NotificationPreferences: new BlackLedgerFactionNotificationPreferencesDto(true, true, true));

        lock (_gate)
        {
            _state.Allegiances[user.UserId] = allegiance;
            _state.MembershipReceipts.Add(receipt);
            PersistLocked();
        }

        return receipt;
    }

    public BlackLedgerFactionCharterDto CreateFaction(HubUserDto user, BlackLedgerCreateFactionRequest request)
    {
        var charterType = NormalizeCharterType(request.CharterType);
        var rules = BuildCharterRules(charterType);
        var perkIds = (request.PerkIds ?? Array.Empty<string>()).Select(NormalizeToken).Where(static item => item.Length > 0).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        var flawIds = (request.FlawIds ?? Array.Empty<string>()).Select(NormalizeToken).Where(static item => item.Length > 0).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        bool warningAccepted = request.WarningAccepted ?? false;
        var archetype = Archetypes.FirstOrDefault(item => string.Equals(item.Id, NormalizeToken(request.ArchetypeId), StringComparison.OrdinalIgnoreCase))
            ?? throw new InvalidOperationException("Unknown archetype.");
        var selectedPerks = Perks.Where(item => perkIds.Contains(item.Id, StringComparer.OrdinalIgnoreCase)).ToArray();
        var selectedFlaws = Flaws.Where(item => flawIds.Contains(item.Id, StringComparer.OrdinalIgnoreCase)).ToArray();

        if (selectedPerks.Length != perkIds.Length || selectedFlaws.Length != flawIds.Length)
        {
            throw new InvalidOperationException("Unknown perk or flaw.");
        }

        if (charterType == "major" && BuildMajorSlotAvailability().MajorSlotsAvailable <= 0)
        {
            throw new InvalidOperationException("No major charter slots remain.");
        }

        if (charterType == "challenger" && !warningAccepted)
        {
            throw new InvalidOperationException("Challenger founder warning acknowledgement is required.");
        }

        if (selectedFlaws.Length < rules.RequiredFlaws)
        {
            throw new InvalidOperationException("Selected flaws do not meet the required minimum.");
        }

        if (selectedFlaws.Length > 4)
        {
            throw new InvalidOperationException("Selected flaws exceed the charter cap.");
        }

        if (selectedPerks.Length > rules.MaxPerks)
        {
            throw new InvalidOperationException("Selected perks exceed the charter cap.");
        }

        if (charterType == "major" && selectedPerks.Any(static perk => perk.ChallengerOnly))
        {
            throw new InvalidOperationException("Challenger-only perks are not allowed on a major charter.");
        }

        int spent = selectedPerks.Sum(static item => item.Cost) + selectedFlaws.Sum(static item => item.Cost);
        if (spent > rules.CharterPoints)
        {
            throw new InvalidOperationException("Selected perks and flaws exceed the available charter points.");
        }

        string publicName = NormalizePublicName(request.PublicName);
        string factionId = BuildFactionId(publicName);
        EnsureFactionNameSafe(publicName, factionId);
        EnsureAllegianceChangeAllowed(user.UserId, factionId, DateTimeOffset.UtcNow);
        var membership = BuildRunnerMembershipSnapshot(user);
        var faction = new BlackLedgerFactionViewModel(
            factionId,
            publicName,
            charterType == "major" ? "Major faction" : "Challenger faction",
            $"{user.DisplayName} / founder",
            charterType == "major" ? "Major charter steward" : "Challenger steward",
            charterType == "major" ? "Dispatch Desk" : "Underdog desk",
            BuildSignals(charterType, selectedPerks, selectedFlaws),
            charterType == "major" ? "#d85757" : "#f3a43c",
            charterType == "major" ? "#f8dbc3" : "#fff2d0",
            charterType == "major" ? "major" : "challenger");
        var charter = new BlackLedgerFactionCharterDto(
            FactionId: factionId,
            FounderAccountId: user.UserId,
            CharterType: charterType,
            CharterPointsTotal: rules.CharterPoints,
            CharterPointsSpent: spent,
            Archetype: archetype.Name,
            Attributes: BuildAttributes(archetype, charterType),
            Perks: selectedPerks.Select(static item => item.Name).ToArray(),
            Flaws: selectedFlaws.Select(static item => item.Name).ToArray(),
            StartingDistrictId: charterType == "major" ? NormalizeToken(request.StartingDistrictId) : null,
            RivalFactionId: NormalizeToken(request.RivalFactionId),
            CreatedAtUtc: DateTimeOffset.UtcNow,
            Status: "pending_review",
            PublicName: publicName,
            Summary: charterType == "major"
                ? "Major charter starts stronger, holds a map claim, and gets 3 AP per tick. Public projection waits for moderation review."
                : "Challenger starts weaker, has fewer points, more flaws, and must challenge larger factions to grow. Public projection waits for moderation review.");
        var receipt = new BlackLedgerFactionJoinReceiptDto(
            ReceiptId: NewId("fmem"),
            AccountIdHash: Hash(user.UserId),
            FactionId: factionId,
            MembershipType: charterType == "major" ? "founder_major" : "founder_challenger",
            AppliesToAllRunners: true,
            RunnerCount: membership.RunnerIds.Count,
            FutureRunnersInherit: true,
            CreatedAtUtc: charter.CreatedAtUtc,
            PrivacyResult: "passed",
            PublicProjectionAllowed: false);
        var allegiance = new BlackLedgerAccountFactionAllegianceDto(
            AccountId: user.UserId,
            ActiveFactionId: factionId,
            MembershipType: receipt.MembershipType,
            AppliesToAllCurrentRunners: true,
            AppliesToAllFutureRunners: true,
            JoinedAtUtc: charter.CreatedAtUtc,
            LockUntilUtc: charter.CreatedAtUtc.AddDays(30),
            SwitchCount: GetSwitchCount(user.UserId) + 1,
            CurrentRunnerIdsSnapshot: membership.RunnerIds,
            ReceiptId: receipt.ReceiptId,
            PublicProjectionAllowed: false,
            NotificationPreferences: new BlackLedgerFactionNotificationPreferencesDto(true, true, true));

        lock (_gate)
        {
            _state.CreatedFactions[factionId] = faction;
            _state.Charters[factionId] = charter;
            _state.Allegiances[user.UserId] = allegiance;
            _state.MembershipReceipts.Add(receipt);
            _state.FactionOperationalStates[factionId] = new BlackLedgerFactionOperationalState(
                WorldId,
                1,
                rules.StartingActionPointsPerTick,
                0,
                0,
                0,
                0,
                charter.CreatedAtUtc,
                new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase),
                new List<string>(),
                new List<string>());
            PersistLocked();
        }

        return charter;
    }

    public IReadOnlyList<BlackLedgerFactionSummaryDto> ListFactionSummaries()
    {
        var world = _stats.LoadWorldPreview() ?? throw new InvalidOperationException("Black Ledger world preview is unavailable.");
        return world.Factions
            .Concat(ListCreatedFactionSummaries())
            .GroupBy(static item => item.Id, StringComparer.OrdinalIgnoreCase)
            .Select(static group => group.First())
            .OrderBy(static item => item.PublicName, StringComparer.OrdinalIgnoreCase)
            .Select(item => BuildSummary(item))
            .ToArray();
    }

    public BlackLedgerFactionDetailDto? GetFactionDetail(string factionId)
    {
        string normalized = NormalizeFactionId(factionId);
        var world = _stats.LoadWorldPreview();
        var seededFaction = world?.Factions.FirstOrDefault(item => string.Equals(item.Id, normalized, StringComparison.OrdinalIgnoreCase));
        if (seededFaction is not null)
        {
            return BuildDetail(seededFaction, charter: null);
        }

        lock (_gate)
        {
            if (_state.CreatedFactions.TryGetValue(normalized, out var createdFaction))
            {
                _state.Charters.TryGetValue(normalized, out var charter);
                if (charter is not null
                    && string.Equals(charter.Status, "public_safe_active", StringComparison.OrdinalIgnoreCase))
                {
                    return BuildDetail(createdFaction, charter);
                }
            }
        }

        return null;
    }

    public BlackLedgerFactionDetailDto? GetWorkspaceFactionDetail(string factionId)
    {
        string normalized = NormalizeFactionId(factionId);
        var publicDetail = GetFactionDetail(normalized);
        if (publicDetail is not null)
        {
            return publicDetail;
        }

        lock (_gate)
        {
            if (_state.CreatedFactions.TryGetValue(normalized, out var createdFaction))
            {
                _state.Charters.TryGetValue(normalized, out var charter);
                return BuildDetail(createdFaction, charter);
            }
        }

        return null;
    }

    public IReadOnlyList<BlackLedgerFactionActionDefinitionDto> GetActionDefinitions(string factionId)
    {
        _ = NormalizeFactionId(factionId);
        return ActionDefinitions;
    }

    public BlackLedgerFactionActionReceiptDto ExecuteAction(HubUserDto user, string factionId, BlackLedgerFactionActionRequest request)
    {
        string normalizedFactionId = NormalizeFactionId(factionId);
        var allegiance = GetAllegiance(user) ?? throw new InvalidOperationException("No faction allegiance.");
        if (!string.Equals(allegiance.ActiveFactionId, normalizedFactionId, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("You can only act for your active faction.");
        }

        var action = ActionDefinitions.FirstOrDefault(item => string.Equals(item.ActionId, NormalizeToken(request.ActionId), StringComparison.OrdinalIgnoreCase))
            ?? throw new InvalidOperationException("Unknown faction action.");
        var now = DateTimeOffset.UtcNow;
        BlackLedgerFactionOperationalState actionState;
        lock (_gate)
        {
            actionState = GetOrCreateActionStateLocked(normalizedFactionId, now);
            if (actionState.ActionPointsSpent + action.Cost > actionState.ActionPointsTotal)
            {
                throw new InvalidOperationException("Faction action points are exhausted for the current turn.");
            }

            ReduceActionLocked(actionState, action, request, now);
        }

        var receipt = new BlackLedgerFactionActionReceiptDto(
            ReceiptId: NewId("fact"),
            FactionId: normalizedFactionId,
            ActionId: action.ActionId,
            ActionLabel: action.Label,
            Cost: action.Cost,
            Stake: request.Stake ?? "pressure",
            TargetDistrictId: NormalizeToken(request.TargetDistrictId),
            TargetFactionId: NormalizeToken(request.TargetFactionId),
            ResultSummary: BuildActionResultSummary(action, request, actionState),
            CreatedAtUtc: now,
            PublicProjectionAllowed: false,
            Href: $"/account/ledger/factions/{normalizedFactionId.Replace('_', '-')}/manage",
            Turn: actionState.CurrentTurn,
            RemainingActionPoints: Math.Max(0, actionState.ActionPointsTotal - actionState.ActionPointsSpent),
            Effects: BuildActionEffects(actionState));

        lock (_gate)
        {
            _state.FactionOperationalStates[normalizedFactionId] = actionState;
            if (!_state.ActionReceiptsByFactionId.TryGetValue(normalizedFactionId, out var receipts))
            {
                receipts = new List<BlackLedgerFactionActionReceiptDto>();
                _state.ActionReceiptsByFactionId[normalizedFactionId] = receipts;
            }

            receipts.Insert(0, receipt);
            PersistLocked();
        }

        return receipt;
    }

    public IReadOnlyList<BlackLedgerFactionActionReceiptDto> GetActionReceipts(string factionId)
    {
        string normalizedFactionId = NormalizeFactionId(factionId);
        lock (_gate)
        {
            return _state.ActionReceiptsByFactionId.TryGetValue(normalizedFactionId, out var receipts)
                ? receipts.OrderByDescending(static item => item.CreatedAtUtc).ToArray()
                : Array.Empty<BlackLedgerFactionActionReceiptDto>();
        }
    }

    public BlackLedgerFactionModerationReceiptDto ApproveFactionForPublicProjection(HubUserDto user, string factionId)
    {
        string normalizedFactionId = NormalizeFactionId(factionId);
        var now = DateTimeOffset.UtcNow;

        lock (_gate)
        {
            if (!_state.CreatedFactions.ContainsKey(normalizedFactionId) || !_state.Charters.TryGetValue(normalizedFactionId, out var charter))
            {
                throw new InvalidOperationException("Unknown faction.");
            }

            _state.Charters[normalizedFactionId] = charter with
            {
                Status = "public_safe_active",
                Summary = "Moderation review approved the faction for bounded public projection on the Black Ledger."
            };

            var receipt = new BlackLedgerFactionModerationReceiptDto(
                ReceiptId: NewId("fmod"),
                FactionId: normalizedFactionId,
                ReviewerAccountId: user.UserId,
                Outcome: "approved",
                ResultSummary: "Faction cleared for bounded public projection.",
                CreatedAtUtc: now,
                PublicProjectionAllowed: true);

            _state.ModerationReceipts.Add(receipt);
            PersistLocked();
            return receipt;
        }
    }

    public BlackLedgerFactionModerationReceiptDto SuppressFactionPublicProjection(HubUserDto user, string factionId, string? reason = null)
    {
        string normalizedFactionId = NormalizeFactionId(factionId);
        var now = DateTimeOffset.UtcNow;

        lock (_gate)
        {
            if (!_state.CreatedFactions.ContainsKey(normalizedFactionId) || !_state.Charters.TryGetValue(normalizedFactionId, out var charter))
            {
                throw new InvalidOperationException("Unknown faction.");
            }

            string summary = string.IsNullOrWhiteSpace(reason)
                ? "Faction remains suppressed from public projection pending further review."
                : $"Faction remains suppressed from public projection: {reason.Trim()}";

            _state.Charters[normalizedFactionId] = charter with
            {
                Status = "suppressed",
                Summary = summary
            };

            var receipt = new BlackLedgerFactionModerationReceiptDto(
                ReceiptId: NewId("fmod"),
                FactionId: normalizedFactionId,
                ReviewerAccountId: user.UserId,
                Outcome: "suppressed",
                ResultSummary: summary,
                CreatedAtUtc: now,
                PublicProjectionAllowed: false);

            _state.ModerationReceipts.Add(receipt);
            PersistLocked();
            return receipt;
        }
    }

    public BlackLedgerFactionSlotAvailabilityDto BuildMajorSlotAvailability()
    {
        lock (_gate)
        {
            int createdMajorCount = _state.Charters.Values.Count(item => string.Equals(item.CharterType, "major", StringComparison.OrdinalIgnoreCase));
            const int total = 10;
            const int seededUsed = 6;
            return new BlackLedgerFactionSlotAvailabilityDto(total, seededUsed, Math.Max(0, total - seededUsed - createdMajorCount));
        }
    }

    private IReadOnlyList<BlackLedgerFactionViewModel> ListCreatedFactionSummaries()
    {
        lock (_gate)
        {
            return _state.CreatedFactions.Values
                .Where(item => _state.Charters.TryGetValue(item.Id, out var charter)
                    && string.Equals(charter.Status, "public_safe_active", StringComparison.OrdinalIgnoreCase))
                .OrderBy(static item => item.PublicName, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }
    }

    private BlackLedgerFactionDetailDto BuildDetail(BlackLedgerFactionViewModel faction, BlackLedgerFactionCharterDto? charter)
    {
        BlackLedgerFactionOperationalState? state;
        lock (_gate)
        {
            _state.FactionOperationalStates.TryGetValue(faction.Id, out state);
        }

        var signals = faction.PublicSignals.ToList();
        if (state is not null)
        {
            signals.Add($"AP {Math.Max(0, state.ActionPointsTotal - state.ActionPointsSpent)}/{state.ActionPointsTotal}");
            signals.Add($"Influence {FormatSigned(state.InfluenceDelta)}");
            signals.Add($"Heat {FormatSigned(state.HeatDelta)}");
            signals.Add($"Trust {FormatSigned(state.PublicTrustDelta)}");
        }

        string summary = charter?.Summary ?? "Seeded faction with route-backed public-safe pressure signals.";
        if (state is not null)
        {
            summary += $" Current faction-state reducer: influence {FormatSigned(state.InfluenceDelta)}, heat {FormatSigned(state.HeatDelta)}, trust {FormatSigned(state.PublicTrustDelta)}.";
        }

        return new(
            faction.Id,
            faction.PublicName,
            faction.Type,
            $"Public-safe faction intel. This page shows pressure, dispatches, package lanes, and AI steward posture. It does not show private campaign data.",
            signals.Take(6).ToArray(),
            faction.FactionLeader,
            faction.FieldGm,
            faction.IntelProvider,
            faction.ColorPrimary,
            faction.ColorSecondary,
            faction.Icon,
            summary,
            $"/ledger/factions/{faction.Id.Replace('_', '-')}",
            $"/ledger/factions/{faction.Id.Replace('_', '-')}/dispatches",
            $"/ledger/factions/{faction.Id.Replace('_', '-')}/packages",
            charter,
            state);
    }

    private static BlackLedgerFactionSummaryDto BuildSummary(BlackLedgerFactionViewModel faction)
        => new(
            faction.Id,
            faction.PublicName,
            faction.Type,
            string.Join(" · ", faction.PublicSignals.Take(3)),
            $"/ledger/factions/{faction.Id.Replace('_', '-')}");

    private static Dictionary<string, int> BuildAttributes(BlackLedgerFactionArchetypeDto archetype, string charterType)
    {
        var attributes = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
        {
            ["Influence"] = charterType == "major" ? 2 : 1,
            ["Resources"] = charterType == "major" ? 2 : 1,
            ["Intel"] = 1,
            ["Logistics"] = 1,
            ["Arcana"] = 1,
            ["Muscle"] = 1,
            ["Trust"] = 1,
            ["Secrecy"] = 1,
            ["Cohesion"] = 1
        };

        foreach (var bonus in archetype.Bonus)
        {
            attributes[bonus.Key] = attributes.GetValueOrDefault(bonus.Key) + bonus.Value;
        }

        return attributes;
    }

    private static string[] BuildSignals(string charterType, IReadOnlyList<BlackLedgerFactionPerkDto> perks, IReadOnlyList<BlackLedgerFactionFlawDto> flaws)
    {
        var signals = new List<string>
        {
            charterType == "major" ? "Major charter claim" : "Challenger underdog momentum"
        };
        signals.AddRange(perks.Take(2).Select(static item => item.Name));
        signals.AddRange(flaws.Take(1).Select(static item => item.Name));
        return signals.ToArray();
    }

    private static string BuildActionResultSummary(BlackLedgerFactionActionDefinitionDto action, BlackLedgerFactionActionRequest request, BlackLedgerFactionOperationalState state)
        => action.ActionId switch
        {
            "scout" => $"Scout run raised confidence in {request.TargetDistrictId ?? "the chosen district"}. AP now {Math.Max(0, state.ActionPointsTotal - state.ActionPointsSpent)}/{state.ActionPointsTotal}.",
            "recruit" => $"Recruit action improved cohesion and faction reach. Trust is now {FormatSigned(state.PublicTrustDelta)}.",
            "secure-district" => $"Secure District hardened pressure around {request.TargetDistrictId ?? "the current front"}. Influence is now {FormatSigned(state.InfluenceDelta)}.",
            "sponsor-package" => $"Sponsor Package added bounded pressure to a package candidate. Trust is now {FormatSigned(state.PublicTrustDelta)}.",
            "publish-dispatch" => $"Publish Dispatch queued a clean receipt-backed summary for the faction feed. Trust is now {FormatSigned(state.PublicTrustDelta)}.",
            "reduce-heat" => $"Reduce Heat cooled public pressure at the cost of momentum. Heat is now {FormatSigned(state.HeatDelta)}.",
            "challenge-faction" => $"Challenge Faction targeted {request.TargetFactionId ?? "a larger rival"} for visible underdog pressure. Influence is now {FormatSigned(state.InfluenceDelta)}.",
            "fortify-safehouse" => $"Fortify Safehouse reduced attrition risk before the next tick. Heat is now {FormatSigned(state.HeatDelta)}.",
            "gather-receipts" => $"Gather Receipts improved proof-trail strength for the next closeout. Trust is now {FormatSigned(state.PublicTrustDelta)}.",
            _ => $"{action.Label} resolved."
        };

    private static string BuildFactionId(string publicName)
    {
        var builder = new StringBuilder();
        foreach (char ch in publicName.ToLowerInvariant())
        {
            builder.Append(char.IsLetterOrDigit(ch) ? ch : '_');
        }

        string candidate = builder.ToString().Trim('_');
        while (candidate.Contains("__", StringComparison.Ordinal))
        {
            candidate = candidate.Replace("__", "_", StringComparison.Ordinal);
        }

        return candidate;
    }

    private BlackLedgerAccountFactionAllegianceDto? GetAllegianceByUserId(string userId)
    {
        lock (_gate)
        {
            return _state.Allegiances.TryGetValue(userId, out var allegiance) ? allegiance : null;
        }
    }

    private int GetSwitchCount(string userId)
    {
        lock (_gate)
        {
            return _state.Allegiances.TryGetValue(userId, out var existing) ? existing.SwitchCount : 0;
        }
    }

    private void Load()
    {
        lock (_gate)
        {
            _state = _store.BlackLedgerFactionOnboardingState ?? new BlackLedgerFactionOnboardingState();
        }
    }

    private void PersistLocked()
    {
        _store.BlackLedgerFactionOnboardingState = _state;
        _store.PersistLocked();
    }

    private static string NormalizeFactionId(string factionId)
        => NormalizeToken(factionId).Replace('-', '_');

    private static string NormalizeCharterType(string? charterType)
        => string.Equals(NormalizeToken(charterType), "challenger", StringComparison.OrdinalIgnoreCase) ? "challenger" : "major";

    private static string NormalizePublicName(string? publicName)
    {
        string value = (publicName ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new InvalidOperationException("Faction name is required.");
        }

        if (value.Length < 4 || value.Length > 48)
        {
            throw new InvalidOperationException("Faction name must stay between 4 and 48 characters.");
        }

        return value;
    }

    private static string NormalizeToken(string? value)
        => string.IsNullOrWhiteSpace(value) ? string.Empty : value.Trim();

    private static string NewId(string prefix)
        => $"{prefix}_{Guid.NewGuid():N}";

    private static string Hash(string value)
    {
        byte[] bytes = SHA256.HashData(Encoding.UTF8.GetBytes(value));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }

    private static BlackLedgerFactionCharterRulesDto BuildCharterRules(string charterType)
        => string.Equals(charterType, "challenger", StringComparison.OrdinalIgnoreCase)
            ? new("challenger", 65, 2, 12, 4, 3, 3, false, 22, 48, 35, "This faction starts weaker and must challenge larger factions to grow.")
            : new("major", 100, 3, 18, 5, 2, 5, true, 55, 35, 50, null);

    public BlackLedgerPrivateLoreOverlayDto UpsertPrivateLoreOverlay(HubUserDto user, string campaignId, PrivateLoreOverlayRequest request)
    {
        if (!string.Equals(request.WorldId, WorldId, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("worldId must be emerald-sprawl-prelude.");
        }

        string normalizedFactionId = NormalizeFactionId(request.FactionId);
        var allegiance = GetAllegiance(user) ?? throw new InvalidOperationException("No faction allegiance.");
        if (!string.Equals(allegiance.ActiveFactionId, normalizedFactionId, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("You can only write private lore for your active faction.");
        }

        var overlay = new BlackLedgerPrivateLoreOverlayDto(
            OverlayId: string.IsNullOrWhiteSpace(request.OverlayId) ? NewId("overlay") : NormalizeToken(request.OverlayId),
            CampaignId: campaignId,
            WorldId: WorldId,
            FactionId: normalizedFactionId,
            LabelMap: request.LabelMap,
            Notes: request.Notes ?? Array.Empty<string>(),
            PublicProjectionAllowed: false,
            UpdatedAtUtc: DateTimeOffset.UtcNow);

        lock (_gate)
        {
            _state.PrivateLoreOverlays[$"{campaignId}:{normalizedFactionId}"] = overlay;
            PersistLocked();
        }

        return overlay;
    }

    public BlackLedgerPrivateLoreOverlayDto? GetPrivateLoreOverlay(string campaignId, string factionId)
    {
        lock (_gate)
        {
            return _state.PrivateLoreOverlays.TryGetValue($"{campaignId}:{NormalizeFactionId(factionId)}", out var overlay)
                ? overlay
                : null;
        }
    }

    private RunnerMembershipSnapshot BuildRunnerMembershipSnapshot(HubUserDto user)
    {
        var summary = _campaignSpine.GetAccountSummary(user);
        var runnerIds = SelectRealRunnerIds(summary.Dossiers);

        return new RunnerMembershipSnapshot(runnerIds);
    }

    private static IReadOnlyList<string> SelectRealRunnerIds(IReadOnlyList<Chummer.Campaign.Contracts.RunnerDossierProjection> dossiers)
        => dossiers
            .Where(static dossier => !IsSyntheticPersonalShell(dossier))
            .Select(static dossier => dossier.DossierId)
            .Where(static dossierId => !string.IsNullOrWhiteSpace(dossierId))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

    private static bool IsSyntheticPersonalShell(Chummer.Campaign.Contracts.RunnerDossierProjection dossier)
        => dossier.CampaignId is null
           && dossier.CrewId is null
           && dossier.CurrentRunId is null
           && dossier.Projections.Any(static projection => string.Equals(projection.Label, "Living dossier", StringComparison.OrdinalIgnoreCase));

    private void EnsureAllegianceChangeAllowed(string userId, string factionId, DateTimeOffset now)
    {
        var existing = GetAllegianceByUserId(userId);
        if (existing is null)
        {
            return;
        }

        if (string.Equals(existing.ActiveFactionId, factionId, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Account is already aligned with this faction.");
        }

        if (existing.LockUntilUtc is not null && existing.LockUntilUtc > now)
        {
            throw new InvalidOperationException("Faction defection cooldown is still active.");
        }
    }

    private void EnsureFactionNameSafe(string publicName, string factionId)
    {
        string normalized = publicName.Trim().ToLowerInvariant();
        if (ForbiddenFactionNameTerms.Any(term => normalized.Contains(term, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidOperationException("Faction name failed public-safety moderation.");
        }

        if (GetWorkspaceFactionDetail(factionId) is not null)
        {
            throw new InvalidOperationException("Faction name is already taken.");
        }
    }

    private static IReadOnlyList<BlackLedgerWizardStepViewModel> BuildWizardSteps(string currentStep)
    {
        string[] order = ["welcome", "allegiance", "factions", "choose-path", "confirm", "builder", "welcome-kit"];
        return order
            .Select((step, index) => new BlackLedgerWizardStepViewModel(
                step,
                step switch
                {
                    "welcome" => "Welcome",
                    "allegiance" => "Allegiance",
                    "factions" => "Factions",
                    "choose-path" => "Choose path",
                    "confirm" => "Confirm",
                    "builder" => "Builder",
                    "welcome-kit" => "Welcome kit",
                    _ => step
                },
                $"/account/ledger/onboarding?step={Uri.EscapeDataString(step)}",
                string.Equals(step, currentStep, StringComparison.OrdinalIgnoreCase),
                index < Array.IndexOf(order, currentStep)))
            .ToArray();
    }

    private BlackLedgerFactionOperationalState GetOrCreateActionStateLocked(string factionId, DateTimeOffset now)
    {
        if (!_state.FactionOperationalStates.TryGetValue(factionId, out var state))
        {
            int total = _state.Charters.TryGetValue(factionId, out var charter)
                ? BuildCharterRules(charter.CharterType).StartingActionPointsPerTick
                : 3;
            state = new BlackLedgerFactionOperationalState(
                WorldId,
                1,
                total,
                0,
                0,
                0,
                0,
                now,
                new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase),
                new List<string>(),
                new List<string>());
            _state.FactionOperationalStates[factionId] = state;
        }

        return state;
    }

    private static void ReduceActionLocked(
        BlackLedgerFactionOperationalState state,
        BlackLedgerFactionActionDefinitionDto action,
        BlackLedgerFactionActionRequest request,
        DateTimeOffset now)
    {
        state.ActionPointsSpent += action.Cost;
        state.LastUpdatedAtUtc = now;
        string district = NormalizeToken(request.TargetDistrictId);
        string rival = NormalizeToken(request.TargetFactionId);
        switch (action.ActionId)
        {
            case "scout":
                state.InfluenceDelta += 1;
                if (district.Length > 0)
                {
                    state.DistrictPressure[district] = state.DistrictPressure.GetValueOrDefault(district) + 1;
                }
                break;
            case "recruit":
                state.PublicTrustDelta += 1;
                break;
            case "secure-district":
                state.InfluenceDelta += 2;
                state.HeatDelta -= 1;
                if (district.Length > 0)
                {
                    state.DistrictPressure[district] = state.DistrictPressure.GetValueOrDefault(district) + 2;
                }
                break;
            case "sponsor-package":
                state.PublicTrustDelta += 1;
                break;
            case "publish-dispatch":
                state.PublicTrustDelta += 2;
                break;
            case "reduce-heat":
                state.HeatDelta -= 2;
                state.InfluenceDelta -= 1;
                break;
            case "challenge-faction":
                state.InfluenceDelta += 1;
                state.HeatDelta += 1;
                if (rival.Length > 0 && !state.RivalsChallenged.Contains(rival, StringComparer.OrdinalIgnoreCase))
                {
                    state.RivalsChallenged.Add(rival);
                }
                break;
            case "fortify-safehouse":
                state.HeatDelta -= 1;
                break;
            case "gather-receipts":
                state.PublicTrustDelta += 1;
                break;
        }
    }

    private static IReadOnlyList<string> BuildActionEffects(BlackLedgerFactionOperationalState state)
        =>
        [
            $"influence {FormatSigned(state.InfluenceDelta)}",
            $"heat {FormatSigned(state.HeatDelta)}",
            $"trust {FormatSigned(state.PublicTrustDelta)}",
            $"ap {Math.Max(0, state.ActionPointsTotal - state.ActionPointsSpent)}/{state.ActionPointsTotal}"
        ];

    private static string FormatSigned(int value)
        => value >= 0 ? $"+{value}" : value.ToString();

    public static readonly IReadOnlyList<BlackLedgerFactionActionDefinitionDto> ActionDefinitions =
    [
        new("scout", "Scout", 1, "improves Intel and confidence for a target district"),
        new("recruit", "Recruit", 1, "increases Cohesion or Influence"),
        new("secure-district", "Secure District", 2, "increases influence and reduces volatility"),
        new("sponsor-package", "Sponsor Package", 1, "adds package pressure to a package candidate"),
        new("publish-dispatch", "Publish Dispatch", 1, "improves Public Trust when a dispatch is clean"),
        new("reduce-heat", "Reduce Heat", 1, "lowers Heat and trades away momentum"),
        new("challenge-faction", "Challenge Faction", 2, "contests a district or package lane"),
        new("fortify-safehouse", "Fortify Safehouse", 1, "reduces attrition risk"),
        new("gather-receipts", "Gather Receipts", 1, "improves proof-trail strength")
    ];

    public static readonly IReadOnlyList<BlackLedgerFactionArchetypeDto> Archetypes =
    [
        new("corporate_compact", "Corporate Compact", new Dictionary<string, int> { ["Resources"] = 1, ["Influence"] = 1 }),
        new("street_wardens", "Street Wardens", new Dictionary<string, int> { ["Trust"] = 1, ["Muscle"] = 1 }),
        new("mystic_circle", "Mystic Circle", new Dictionary<string, int> { ["Arcana"] = 2 }),
        new("matrix_cell", "Matrix Cell", new Dictionary<string, int> { ["Intel"] = 1, ["Secrecy"] = 1 }),
        new("logistics_outfit", "Logistics Outfit", new Dictionary<string, int> { ["Logistics"] = 2 }),
        new("black_market_house", "Black-Market House", new Dictionary<string, int> { ["Resources"] = 1, ["Secrecy"] = 1 }),
        new("creator_press", "Creator Press", new Dictionary<string, int> { ["Trust"] = 1, ["Intel"] = 1 }),
        new("mercenary_crew", "Mercenary Crew", new Dictionary<string, int> { ["Muscle"] = 2 })
    ];

    public static readonly IReadOnlyList<BlackLedgerFactionPerkDto> Perks =
    [
        new("safehouse_network", "Safehouse Network", 12, false),
        new("black_market_pipeline", "Black Market Pipeline", 12, false),
        new("trusted_fixers", "Trusted Fixers", 10, false),
        new("street_doctors", "Street Doctors", 10, false),
        new("drone_yard", "Drone Yard", 10, false),
        new("intel_mesh", "Intel Mesh", 14, false),
        new("ritual_circle", "Ritual Circle", 12, false),
        new("clean_paperwork", "Clean Paperwork", 10, false),
        new("public_trust", "Public Trust", 10, false),
        new("ghost_protocol", "Ghost Protocol", 12, false),
        new("runner_academy", "Runner Academy", 8, false),
        new("package_sponsor", "Package Sponsor", 10, false),
        new("emergency_extraction", "Emergency Extraction", 14, false),
        new("dispatch_desk", "Dispatch Desk", 6, false),
        new("underdog_momentum", "Underdog Momentum", 8, true)
    ];

    public static readonly IReadOnlyList<BlackLedgerFactionFlawDto> Flaws =
    [
        new("debt_chain", "Debt Chain", -12),
        new("infighting", "Infighting", -10),
        new("public_heat", "Public Heat", -10),
        new("bad_paperwork", "Bad Paperwork", -8),
        new("thin_resources", "Thin Resources", -10),
        new("unstable_intel", "Unstable Intel", -8),
        new("rival_target", "Rival Target", -8),
        new("haunted_reputation", "Haunted Reputation", -10),
        new("fragile_safehouses", "Fragile Safehouses", -8),
        new("magic_controversy", "Magic Controversy", -8),
        new("supply_dependence", "Supply Dependence", -8),
        new("hardline_doctrine", "Hardline Doctrine", -6),
        new("overexposed", "Overexposed", -10)
    ];
}

public sealed record BlackLedgerFactionNotificationPreferencesDto(
    bool FactionDispatchEmail,
    bool WorldTickDigest,
    bool PackagePressureUpdates);

public sealed record BlackLedgerAccountFactionAllegianceDto(
    string AccountId,
    string ActiveFactionId,
    string MembershipType,
    bool AppliesToAllCurrentRunners,
    bool AppliesToAllFutureRunners,
    DateTimeOffset JoinedAtUtc,
    DateTimeOffset? LockUntilUtc,
    int SwitchCount,
    IReadOnlyList<string> CurrentRunnerIdsSnapshot,
    string ReceiptId,
    bool PublicProjectionAllowed,
    BlackLedgerFactionNotificationPreferencesDto NotificationPreferences);

public sealed record BlackLedgerFactionJoinReceiptDto(
    string ReceiptId,
    string AccountIdHash,
    string FactionId,
    string MembershipType,
    bool AppliesToAllRunners,
    int RunnerCount,
    bool FutureRunnersInherit,
    DateTimeOffset CreatedAtUtc,
    string PrivacyResult,
    bool PublicProjectionAllowed);

public sealed record BlackLedgerFactionCharterDto(
    string FactionId,
    string FounderAccountId,
    string CharterType,
    int CharterPointsTotal,
    int CharterPointsSpent,
    string Archetype,
    IReadOnlyDictionary<string, int> Attributes,
    IReadOnlyList<string> Perks,
    IReadOnlyList<string> Flaws,
    string? StartingDistrictId,
    string? RivalFactionId,
    DateTimeOffset CreatedAtUtc,
    string Status,
    string PublicName,
    string Summary);

public sealed record BlackLedgerFactionActionDefinitionDto(
    string ActionId,
    string Label,
    int Cost,
    string Effect);

public sealed record BlackLedgerFactionActionReceiptDto(
    string ReceiptId,
    string FactionId,
    string ActionId,
    string ActionLabel,
    int Cost,
    string Stake,
    string? TargetDistrictId,
    string? TargetFactionId,
    string ResultSummary,
    DateTimeOffset CreatedAtUtc,
    bool PublicProjectionAllowed,
    string Href,
    int Turn,
    int RemainingActionPoints,
    IReadOnlyList<string> Effects);

public sealed record BlackLedgerFactionModerationReceiptDto(
    string ReceiptId,
    string FactionId,
    string ReviewerAccountId,
    string Outcome,
    string ResultSummary,
    DateTimeOffset CreatedAtUtc,
    bool PublicProjectionAllowed);

public sealed record BlackLedgerFactionSummaryDto(
    string FactionId,
    string PublicName,
    string Type,
    string Summary,
    string Href);

public sealed record BlackLedgerFactionDetailDto(
    string FactionId,
    string PublicName,
    string Type,
    string Intro,
    IReadOnlyList<string> PublicSignals,
    string FactionLeader,
    string FieldGm,
    string IntelProvider,
    string ColorPrimary,
    string ColorSecondary,
    string Icon,
    string Summary,
    string ProfileHref,
    string DispatchesHref,
    string PackagesHref,
    BlackLedgerFactionCharterDto? Charter,
    BlackLedgerFactionOperationalState? OperationalState = null);

public sealed record BlackLedgerFactionSlotAvailabilityDto(
    int MajorSlotsTotal,
    int SeededUsed,
    int MajorSlotsAvailable);

public sealed record BlackLedgerFactionCharterRulesDto(
    string CharterType,
    int CharterPoints,
    int StartingActionPointsPerTick,
    int AttributeRatingPoints,
    int MaxAttributeRating,
    int RequiredFlaws,
    int MaxPerks,
    bool HomeDistrictClaim,
    int StartingInfluence,
    int StartingHeat,
    int StartingPublicTrust,
    string? MandatoryWarning);

public sealed record BlackLedgerFactionArchetypeDto(
    string Id,
    string Name,
    IReadOnlyDictionary<string, int> Bonus);

public sealed record BlackLedgerFactionPerkDto(
    string Id,
    string Name,
    int Cost,
    bool ChallengerOnly);

public sealed record BlackLedgerFactionFlawDto(
    string Id,
    string Name,
    int Cost);

public sealed record BlackLedgerCreateFactionRequest(
    string? PublicName,
    string? CharterType,
    string? ArchetypeId,
    IReadOnlyList<string>? PerkIds,
    IReadOnlyList<string>? FlawIds,
    string? StartingDistrictId,
    string? RivalFactionId,
    bool? WarningAccepted = null);

public sealed record BlackLedgerFactionActionRequest(
    string? ActionId,
    string? TargetDistrictId,
    string? TargetFactionId,
    string? Stake);

public sealed record PrivateLoreOverlayRequest(
    string WorldId,
    string FactionId,
    IReadOnlyDictionary<string, string> LabelMap,
    IReadOnlyList<string>? Notes = null,
    string? OverlayId = null);

public sealed record BlackLedgerPrivateLoreOverlayDto(
    string OverlayId,
    string CampaignId,
    string WorldId,
    string FactionId,
    IReadOnlyDictionary<string, string> LabelMap,
    IReadOnlyList<string> Notes,
    bool PublicProjectionAllowed,
    DateTimeOffset UpdatedAtUtc);

public sealed class BlackLedgerFactionOperationalState
{
    public BlackLedgerFactionOperationalState(
        string worldId,
        int currentTurn,
        int actionPointsTotal,
        int actionPointsSpent,
        int influenceDelta,
        int heatDelta,
        int publicTrustDelta,
        DateTimeOffset lastUpdatedAtUtc,
        Dictionary<string, int> districtPressure,
        List<string> rivalsChallenged,
        List<string> overlayIds)
    {
        WorldId = worldId;
        CurrentTurn = currentTurn;
        ActionPointsTotal = actionPointsTotal;
        ActionPointsSpent = actionPointsSpent;
        InfluenceDelta = influenceDelta;
        HeatDelta = heatDelta;
        PublicTrustDelta = publicTrustDelta;
        LastUpdatedAtUtc = lastUpdatedAtUtc;
        DistrictPressure = districtPressure;
        RivalsChallenged = rivalsChallenged;
        OverlayIds = overlayIds;
    }

    public string WorldId { get; set; }
    public int CurrentTurn { get; set; }
    public int ActionPointsTotal { get; set; }
    public int ActionPointsSpent { get; set; }
    public int InfluenceDelta { get; set; }
    public int HeatDelta { get; set; }
    public int PublicTrustDelta { get; set; }
    public DateTimeOffset LastUpdatedAtUtc { get; set; }
    public Dictionary<string, int> DistrictPressure { get; init; }
    public List<string> RivalsChallenged { get; init; }
    public List<string> OverlayIds { get; init; }
}

internal sealed record RunnerMembershipSnapshot(IReadOnlyList<string> RunnerIds);

public sealed class BlackLedgerFactionOnboardingState
{
    public Dictionary<string, BlackLedgerAccountFactionAllegianceDto> Allegiances { get; init; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, BlackLedgerFactionViewModel> CreatedFactions { get; init; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, BlackLedgerFactionCharterDto> Charters { get; init; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, List<BlackLedgerFactionActionReceiptDto>> ActionReceiptsByFactionId { get; init; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, BlackLedgerFactionOperationalState> FactionOperationalStates { get; init; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, BlackLedgerPrivateLoreOverlayDto> PrivateLoreOverlays { get; init; } = new(StringComparer.OrdinalIgnoreCase);
    public List<BlackLedgerFactionJoinReceiptDto> MembershipReceipts { get; init; } = new();
    public List<BlackLedgerFactionModerationReceiptDto> ModerationReceipts { get; init; } = new();
}
