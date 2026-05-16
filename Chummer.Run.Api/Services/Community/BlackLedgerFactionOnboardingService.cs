using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class BlackLedgerFactionOnboardingService
{
    private const string WorldId = "emerald-sprawl-prelude";
    private readonly object _gate = new();
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };
    private readonly BlackLedgerPublicStatsService _stats;
    private BlackLedgerFactionOnboardingState _state = new();

    public BlackLedgerFactionOnboardingService(IConfiguration configuration, BlackLedgerPublicStatsService stats)
    {
        _stats = stats;
        _storagePath = configuration["CHUMMER_BLACK_LEDGER_FACTION_STORAGE"]
            ?? Path.Combine(AppContext.BaseDirectory, "App_Data", "black-ledger-faction-onboarding.json");
        Load();
    }

    public bool HasActiveAllegiance(string userId)
        => GetAllegianceByUserId(userId) is not null;

    public BlackLedgerAccountFactionAllegianceDto? GetAllegiance(HubUserDto user)
        => GetAllegianceByUserId(user.UserId);

    public BlackLedgerFactionOnboardingViewModel BuildOnboardingModel(HubUserDto user)
    {
        var world = _stats.LoadWorldPreview() ?? throw new InvalidOperationException("Black Ledger world preview is unavailable.");
        var allegiance = GetAllegiance(user);
        var createdFactions = ListCreatedFactionSummaries();
        var factionOptions = world.Factions
            .Concat(createdFactions)
            .OrderBy(static faction => faction.PublicName, StringComparer.OrdinalIgnoreCase)
            .Select(faction => new BlackLedgerFactionJoinOptionViewModel(
                faction.Id.Replace('_', '-'),
                faction.PublicName,
                faction.Type,
                string.Join(" · ", faction.PublicSignals.Take(3)),
                $"/ledger/factions/{faction.Id.Replace('_', '-')}"))
            .ToArray();
        var majorAvailability = BuildMajorSlotAvailability();

        return new BlackLedgerFactionOnboardingViewModel(
            Heading: "Choose your flag.",
            Intro: "Black Ledger is a living campaign layer. Your account joins one faction, and all of your current and future runners carry that allegiance.",
            HasActiveAllegiance: allegiance is not null,
            CurrentAllegiance: allegiance,
            ExistingFactionSummary: "Join a house that already has pressure, history, and enemies.",
            MajorFounderSummary: "Found a Major Faction. Major Charter Slots are limited. You start stronger, with more points and a claim to the map.",
            ChallengerFounderSummary: "Found a Challenger Faction. You start weaker, with fewer points and more risk. You can still challenge larger factions and force your way onto the map.",
            MajorSlotsWarning: majorAvailability.MajorSlotsAvailable > 0
                ? null
                : "All Major Charter Slots are taken. You can still found a Challenger Faction. It starts weaker, but it can challenge larger factions through play.",
            MajorSlotsAvailable: majorAvailability.MajorSlotsAvailable,
            ExistingFactions: factionOptions);
    }

    public BlackLedgerFactionHomeViewModel BuildFactionHome(HubUserDto user)
    {
        var allegiance = GetAllegiance(user) ?? throw new InvalidOperationException("No active faction allegiance.");
        var detail = GetFactionDetail(allegiance.ActiveFactionId) ?? throw new InvalidOperationException("Faction detail missing.");
        var welcomeKit = new[]
        {
            $"{detail.PublicName} welcome kit",
            $"{detail.PublicName} badge unlocked",
            "Runner Passport stamp queued",
            "First task: Gather receipts"
        };

        return new BlackLedgerFactionHomeViewModel(
            Heading: "Your runners carry this banner.",
            Intro: "Your account allegiance applies to all current and future runners. Weekly dispatch hooks, badge posture, and the first task all start from this one route.",
            Allegiance: allegiance,
            Faction: detail,
            WelcomeKit: welcomeKit,
            RecentActionReceipts: GetActionReceipts(detail.FactionId).Take(5).ToArray());
    }

    public BlackLedgerFactionCreatePageViewModel BuildCreatePage(HubUserDto user)
    {
        _ = user;
        var majorAvailability = BuildMajorSlotAvailability();
        return new BlackLedgerFactionCreatePageViewModel(
            Heading: "Build a faction charter.",
            Intro: "Choose a charter type, spend the exact point budget, take the required flaws, and start from a bounded MVP rule set.",
            MajorSlotsAvailable: majorAvailability.MajorSlotsAvailable,
            MajorRules: BuildCharterRules("major"),
            ChallengerRules: BuildCharterRules("challenger"),
            Archetypes: Archetypes,
            Perks: Perks,
            Flaws: Flaws);
    }

    public BlackLedgerFactionJoinReceiptDto JoinFaction(HubUserDto user, string factionId)
    {
        string normalizedFactionId = NormalizeFactionId(factionId);
        if (GetFactionDetail(normalizedFactionId) is null)
        {
            throw new InvalidOperationException("Unknown faction.");
        }

        var now = DateTimeOffset.UtcNow;
        var receipt = new BlackLedgerFactionJoinReceiptDto(
            ReceiptId: NewId("fmem"),
            AccountIdHash: Hash(user.UserId),
            FactionId: normalizedFactionId,
            MembershipType: "joined_existing",
            AppliesToAllRunners: true,
            RunnerCount: 2,
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
            CurrentRunnerIdsSnapshot: new[] { $"{user.Handle}-runner-alpha", $"{user.Handle}-runner-beta" },
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

        if (selectedFlaws.Length < rules.RequiredFlaws)
        {
            throw new InvalidOperationException("Selected flaws do not meet the required minimum.");
        }

        if (selectedPerks.Length > rules.MaxPerks)
        {
            throw new InvalidOperationException("Selected perks exceed the charter cap.");
        }

        int spent = selectedPerks.Sum(static item => item.Cost) + selectedFlaws.Sum(static item => item.Cost);
        if (spent > rules.CharterPoints)
        {
            throw new InvalidOperationException("Selected perks and flaws exceed the available charter points.");
        }

        string publicName = NormalizePublicName(request.PublicName);
        string factionId = BuildFactionId(publicName);
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
            Status: "active",
            PublicName: publicName,
            Summary: charterType == "major"
                ? "Major charter starts stronger, holds a map claim, and gets 3 AP per tick."
                : "Challenger starts weaker, has fewer points, more flaws, and must challenge larger factions to grow.");
        var receipt = new BlackLedgerFactionJoinReceiptDto(
            ReceiptId: NewId("fmem"),
            AccountIdHash: Hash(user.UserId),
            FactionId: factionId,
            MembershipType: charterType == "major" ? "founder_major" : "founder_challenger",
            AppliesToAllRunners: true,
            RunnerCount: 2,
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
            CurrentRunnerIdsSnapshot: new[] { $"{user.Handle}-runner-alpha", $"{user.Handle}-runner-beta" },
            ReceiptId: receipt.ReceiptId,
            PublicProjectionAllowed: false,
            NotificationPreferences: new BlackLedgerFactionNotificationPreferencesDto(true, true, true));

        lock (_gate)
        {
            _state.CreatedFactions[factionId] = faction;
            _state.Charters[factionId] = charter;
            _state.Allegiances[user.UserId] = allegiance;
            _state.MembershipReceipts.Add(receipt);
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
        var receipt = new BlackLedgerFactionActionReceiptDto(
            ReceiptId: NewId("fact"),
            FactionId: normalizedFactionId,
            ActionId: action.ActionId,
            ActionLabel: action.Label,
            Cost: action.Cost,
            Stake: request.Stake ?? "pressure",
            TargetDistrictId: NormalizeToken(request.TargetDistrictId),
            TargetFactionId: NormalizeToken(request.TargetFactionId),
            ResultSummary: BuildActionResultSummary(action, request),
            CreatedAtUtc: DateTimeOffset.UtcNow,
            PublicProjectionAllowed: false,
            Href: $"/account/ledger/factions/{normalizedFactionId.Replace('_', '-')}/manage");

        lock (_gate)
        {
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
            return _state.CreatedFactions.Values.OrderBy(static item => item.PublicName, StringComparer.OrdinalIgnoreCase).ToArray();
        }
    }

    private BlackLedgerFactionDetailDto BuildDetail(BlackLedgerFactionViewModel faction, BlackLedgerFactionCharterDto? charter)
        => new(
            faction.Id,
            faction.PublicName,
            faction.Type,
            $"Public-safe faction intel. This page shows pressure, dispatches, package lanes, and AI steward posture. It does not show private campaign data.",
            faction.PublicSignals,
            faction.FactionLeader,
            faction.FieldGm,
            faction.IntelProvider,
            faction.ColorPrimary,
            faction.ColorSecondary,
            faction.Icon,
            charter?.Summary ?? "Seeded faction with route-backed public-safe pressure signals.",
            $"/ledger/factions/{faction.Id.Replace('_', '-')}",
            $"/ledger/factions/{faction.Id.Replace('_', '-')}/dispatches",
            $"/ledger/factions/{faction.Id.Replace('_', '-')}/packages",
            charter);

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

    private static string BuildActionResultSummary(BlackLedgerFactionActionDefinitionDto action, BlackLedgerFactionActionRequest request)
        => action.ActionId switch
        {
            "scout" => $"Scout run raised confidence in {request.TargetDistrictId ?? "the chosen district"}.",
            "recruit" => "Recruit action improved cohesion and faction reach.",
            "secure-district" => $"Secure District hardened pressure around {request.TargetDistrictId ?? "the current front"}.",
            "sponsor-package" => "Sponsor Package added bounded pressure to a package candidate.",
            "publish-dispatch" => "Publish Dispatch queued a clean receipt-backed summary for the faction feed.",
            "reduce-heat" => "Reduce Heat cooled public pressure at the cost of momentum.",
            "challenge-faction" => $"Challenge Faction targeted {request.TargetFactionId ?? "a larger rival"} for visible underdog pressure.",
            "fortify-safehouse" => "Fortify Safehouse reduced attrition risk before the next tick.",
            "gather-receipts" => "Gather Receipts improved proof-trail strength for the next closeout.",
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
            if (!File.Exists(_storagePath))
            {
                _state = new BlackLedgerFactionOnboardingState();
                return;
            }

            _state = JsonSerializer.Deserialize<BlackLedgerFactionOnboardingState>(File.ReadAllText(_storagePath), _jsonOptions)
                ?? new BlackLedgerFactionOnboardingState();
        }
    }

    private void PersistLocked()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        File.WriteAllText(_storagePath, JsonSerializer.Serialize(_state, _jsonOptions));
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
    string Href);

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
    BlackLedgerFactionCharterDto? Charter);

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
    string? RivalFactionId);

public sealed record BlackLedgerFactionActionRequest(
    string? ActionId,
    string? TargetDistrictId,
    string? TargetFactionId,
    string? Stake);

internal sealed class BlackLedgerFactionOnboardingState
{
    public Dictionary<string, BlackLedgerAccountFactionAllegianceDto> Allegiances { get; init; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, BlackLedgerFactionViewModel> CreatedFactions { get; init; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, BlackLedgerFactionCharterDto> Charters { get; init; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, List<BlackLedgerFactionActionReceiptDto>> ActionReceiptsByFactionId { get; init; } = new(StringComparer.OrdinalIgnoreCase);
    public List<BlackLedgerFactionJoinReceiptDto> MembershipReceipts { get; init; } = new();
}
