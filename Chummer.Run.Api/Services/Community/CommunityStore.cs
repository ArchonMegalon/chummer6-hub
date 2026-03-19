using System.Text.Json;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Entitlements;
using Chummer.Run.Contracts.Ledger;
using Chummer.Run.Contracts.Leaderboards;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

namespace Chummer.Run.Api.Services.Community;

public sealed class CommunityStore
{
    private readonly ILogger<CommunityStore> _logger;
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public CommunityStore(IConfiguration configuration, ILogger<CommunityStore> logger)
    {
        _logger = logger;
        _storagePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();
    public string StoragePath => _storagePath;
    public Dictionary<string, HubUserDto> UsersById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> UserIdBySubjectId { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, GroupDto> GroupsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, JoinCodeDto> JoinCodesByValue { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, BoostCampaignDto> CampaignsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, BoostCodeDto> BoostCodesByValue { get; } = new(StringComparer.OrdinalIgnoreCase);
    internal Dictionary<string, SponsorSessionState> SponsorSessionsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public List<ContributionReceiptDto> Receipts { get; } = new();
    public List<LedgerEntryDto> LedgerEntries { get; } = new();
    public List<RewardJournalEntryDto> RewardEntries { get; } = new();
    public List<EntitlementGrantDto> EntitlementEntries { get; } = new();
    public List<BadgeDto> Badges { get; } = new();

    public void PersistLocked()
    {
        var snapshot = new CommunityStoreSnapshot(
            Users: UsersById.Values.OrderBy(static user => user.UserId, StringComparer.OrdinalIgnoreCase).ToArray(),
            Groups: GroupsById.Values.OrderBy(static group => group.GroupId, StringComparer.OrdinalIgnoreCase).ToArray(),
            JoinCodes: JoinCodesByValue.Values.OrderBy(static code => code.Code, StringComparer.OrdinalIgnoreCase).ToArray(),
            Campaigns: CampaignsById.Values.OrderBy(static campaign => campaign.CampaignId, StringComparer.OrdinalIgnoreCase).ToArray(),
            BoostCodes: BoostCodesByValue.Values.OrderBy(static code => code.Code, StringComparer.OrdinalIgnoreCase).ToArray(),
            SponsorSessions: SponsorSessionsById.Values
                .OrderBy(static session => session.SponsorSessionId, StringComparer.OrdinalIgnoreCase)
                .Select(SponsorSessionStateSnapshot.FromState)
                .ToArray(),
            Receipts: Receipts.ToArray(),
            LedgerEntries: LedgerEntries.ToArray(),
            RewardEntries: RewardEntries.ToArray(),
            EntitlementEntries: EntitlementEntries.ToArray(),
            Badges: Badges.ToArray());

        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        var tempPath = $"{_storagePath}.tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions));
        File.Move(tempPath, _storagePath, true);
    }

    private void Load()
    {
        lock (Gate)
        {
            if (!File.Exists(_storagePath))
            {
                _logger.LogInformation("CommunityStore starting with an empty durable state at {StoragePath}.", _storagePath);
                return;
            }

            var snapshotJson = File.ReadAllText(_storagePath);
            var snapshot = JsonSerializer.Deserialize<CommunityStoreSnapshot>(snapshotJson, _jsonOptions)
                ?? throw new InvalidOperationException($"Unable to deserialize community store snapshot: {_storagePath}");
            ApplySnapshotLocked(snapshot);
            _logger.LogInformation(
                "CommunityStore loaded {UserCount} users, {GroupCount} groups, and {SessionCount} sponsor sessions from {StoragePath}.",
                UsersById.Count,
                GroupsById.Count,
                SponsorSessionsById.Count,
                _storagePath);
        }
    }

    private void ApplySnapshotLocked(CommunityStoreSnapshot snapshot)
    {
        UsersById.Clear();
        UserIdBySubjectId.Clear();
        GroupsById.Clear();
        JoinCodesByValue.Clear();
        CampaignsById.Clear();
        BoostCodesByValue.Clear();
        SponsorSessionsById.Clear();
        Receipts.Clear();
        LedgerEntries.Clear();
        RewardEntries.Clear();
        EntitlementEntries.Clear();
        Badges.Clear();

        foreach (var user in snapshot.Users ?? Array.Empty<HubUserDto>())
        {
            UsersById[user.UserId] = user;
            foreach (var subject in new[] { user.SubjectId }.Concat(user.LinkedPrincipals ?? Array.Empty<string>()))
            {
                var normalized = AccountService.NormalizeOptional(subject);
                if (normalized is not null)
                {
                    UserIdBySubjectId[normalized] = user.UserId;
                }
            }
        }

        foreach (var group in snapshot.Groups ?? Array.Empty<GroupDto>())
        {
            GroupsById[group.GroupId] = group;
        }

        foreach (var joinCode in snapshot.JoinCodes ?? Array.Empty<JoinCodeDto>())
        {
            JoinCodesByValue[joinCode.Code] = joinCode;
        }

        foreach (var campaign in snapshot.Campaigns ?? Array.Empty<BoostCampaignDto>())
        {
            CampaignsById[campaign.CampaignId] = campaign;
        }

        foreach (var boostCode in snapshot.BoostCodes ?? Array.Empty<BoostCodeDto>())
        {
            BoostCodesByValue[boostCode.Code] = boostCode;
        }

        foreach (var session in snapshot.SponsorSessions ?? Array.Empty<SponsorSessionStateSnapshot>())
        {
            var state = session.ToState();
            SponsorSessionsById[state.SponsorSessionId] = state;
        }

        Receipts.AddRange(snapshot.Receipts ?? Array.Empty<ContributionReceiptDto>());
        LedgerEntries.AddRange(snapshot.LedgerEntries ?? Array.Empty<LedgerEntryDto>());
        RewardEntries.AddRange(snapshot.RewardEntries ?? Array.Empty<RewardJournalEntryDto>());
        EntitlementEntries.AddRange(snapshot.EntitlementEntries ?? Array.Empty<EntitlementGrantDto>());
        Badges.AddRange(snapshot.Badges ?? Array.Empty<BadgeDto>());
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        var configured = configuration["CHUMMER_COMMUNITY_STORE_PATH"] ?? configuration["Community:StorePath"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(Path.GetTempPath(), "chummer6-hub", "community-store.json");
    }
}

internal sealed class SponsorSessionState
{
    public string SponsorSessionId { get; init; } = "";
    public string UserId { get; set; } = "";
    public string GroupId { get; set; } = "";
    public string ProjectId { get; set; } = "";
    public string RequestedLaneType { get; set; } = "participant_burst";
    public string Visibility { get; set; } = "group";
    public string Status { get; set; } = "intent_created";
    public bool Consented { get; set; }
    public string? FleetLaneId { get; set; }
    public string? BoostCampaignId { get; set; }
    public string? BoostCodeId { get; set; }
    public string? DeviceAuthVerificationUri { get; set; }
    public string? DeviceAuthUserCode { get; set; }
    public DateTimeOffset CreatedAtUtc { get; init; } = DateTimeOffset.UtcNow;
    public DateTimeOffset UpdatedAtUtc { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? ConsentedAtUtc { get; set; }
    public DateTimeOffset? ActivatedAtUtc { get; set; }
    public DateTimeOffset? StoppedAtUtc { get; set; }
    public List<SponsorSessionEventDto> Events { get; } = new();

    public SponsorSessionStatusDto Snapshot()
        => new(
            SponsorSessionId,
            UserId,
            GroupId,
            ProjectId,
            RequestedLaneType,
            Visibility,
            Status,
            Consented,
            FleetLaneId,
            BoostCampaignId,
            BoostCodeId,
            DeviceAuthVerificationUri,
            DeviceAuthUserCode,
            CreatedAtUtc,
            UpdatedAtUtc,
            ConsentedAtUtc,
            ActivatedAtUtc,
            StoppedAtUtc,
            Events.ToArray());
}

internal sealed record CommunityStoreSnapshot(
    IReadOnlyList<HubUserDto> Users,
    IReadOnlyList<GroupDto> Groups,
    IReadOnlyList<JoinCodeDto> JoinCodes,
    IReadOnlyList<BoostCampaignDto> Campaigns,
    IReadOnlyList<BoostCodeDto> BoostCodes,
    IReadOnlyList<SponsorSessionStateSnapshot> SponsorSessions,
    IReadOnlyList<ContributionReceiptDto> Receipts,
    IReadOnlyList<LedgerEntryDto> LedgerEntries,
    IReadOnlyList<RewardJournalEntryDto> RewardEntries,
    IReadOnlyList<EntitlementGrantDto> EntitlementEntries,
    IReadOnlyList<BadgeDto> Badges);

internal sealed record SponsorSessionStateSnapshot(
    string SponsorSessionId,
    string UserId,
    string GroupId,
    string ProjectId,
    string RequestedLaneType,
    string Visibility,
    string Status,
    bool Consented,
    string? FleetLaneId,
    string? BoostCampaignId,
    string? BoostCodeId,
    string? DeviceAuthVerificationUri,
    string? DeviceAuthUserCode,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? ConsentedAtUtc,
    DateTimeOffset? ActivatedAtUtc,
    DateTimeOffset? StoppedAtUtc,
    IReadOnlyList<SponsorSessionEventDto> Events)
{
    public static SponsorSessionStateSnapshot FromState(SponsorSessionState state)
        => new(
            state.SponsorSessionId,
            state.UserId,
            state.GroupId,
            state.ProjectId,
            state.RequestedLaneType,
            state.Visibility,
            state.Status,
            state.Consented,
            state.FleetLaneId,
            state.BoostCampaignId,
            state.BoostCodeId,
            state.DeviceAuthVerificationUri,
            state.DeviceAuthUserCode,
            state.CreatedAtUtc,
            state.UpdatedAtUtc,
            state.ConsentedAtUtc,
            state.ActivatedAtUtc,
            state.StoppedAtUtc,
            state.Events.ToArray());

    public SponsorSessionState ToState()
    {
        var state = new SponsorSessionState
        {
            SponsorSessionId = SponsorSessionId,
            UserId = UserId,
            GroupId = GroupId,
            ProjectId = ProjectId,
            RequestedLaneType = RequestedLaneType,
            Visibility = Visibility,
            Status = Status,
            Consented = Consented,
            FleetLaneId = FleetLaneId,
            BoostCampaignId = BoostCampaignId,
            BoostCodeId = BoostCodeId,
            DeviceAuthVerificationUri = DeviceAuthVerificationUri,
            DeviceAuthUserCode = DeviceAuthUserCode,
            CreatedAtUtc = CreatedAtUtc,
            UpdatedAtUtc = UpdatedAtUtc,
            ConsentedAtUtc = ConsentedAtUtc,
            ActivatedAtUtc = ActivatedAtUtc,
            StoppedAtUtc = StoppedAtUtc,
        };
        if (Events is not null)
        {
            state.Events.AddRange(Events);
        }

        return state;
    }
}
