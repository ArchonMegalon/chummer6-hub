using System.Text.Json;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;
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
    public List<LinkedIdentityDto> LinkedIdentities { get; } = new();
    public List<ChannelLinkDto> ChannelLinks { get; } = new();
    public List<ContributionReceiptDto> Receipts { get; } = new();
    public List<LedgerEntryDto> LedgerEntries { get; } = new();
    public List<RewardJournalEntryDto> RewardEntries { get; } = new();
    public List<EntitlementGrantDto> EntitlementEntries { get; } = new();
    public List<BadgeDto> Badges { get; } = new();
    public Dictionary<string, HubUserExperienceDto> UserExperienceByUserId { get; } = new(StringComparer.OrdinalIgnoreCase);
    public List<ParticipationOperatorNotificationReceipt> ParticipationNotificationReceipts { get; } = new();
    public List<BlackLedgerNewsDeliveryReceipt> BlackLedgerNewsDeliveryReceipts { get; } = new();
    public List<BlackLedgerInboxEntry> BlackLedgerInboxEntries { get; } = new();
    public List<BlackLedgerAdvisoryVoteReceipt> BlackLedgerAdvisoryVoteReceipts { get; } = new();
    public List<BlackLedgerAdvisoryMailReceipt> BlackLedgerAdvisoryMailReceipts { get; } = new();
    public List<BlackLedgerDispatch> BlackLedgerDispatches { get; } = new();
    public List<DispatchDraft> BlackLedgerDispatchDrafts { get; } = new();
    public List<DispatchGateReceipt> BlackLedgerDispatchGateReceipts { get; } = new();
    public List<DispatchApprovalReceipt> BlackLedgerDispatchApprovalReceipts { get; } = new();
    public List<DispatchPublicationReceipt> BlackLedgerDispatchPublicationReceipts { get; } = new();
    public List<HeyyScamChatConversationState> HeyyScamChatConversations { get; } = new();
    public List<HeyyScamChatDigestReceipt> HeyyScamChatDigestReceipts { get; } = new();
    public List<HeyyScamChatApprovalReceipt> HeyyScamChatApprovalReceipts { get; } = new();
    public List<HeyyScamChatOperatorSummaryReceipt> HeyyScamChatOperatorSummaryReceipts { get; } = new();
    public List<ExecutiveAssistantChannelConversationState> ExecutiveAssistantChannelConversations { get; } = new();
    public List<ExecutiveAssistantChannelMessageState> ExecutiveAssistantChannelMessages { get; } = new();
    public List<ImportantWorkItemProjection> ImportantWorkItems { get; } = new();
    public Dictionary<string, RunnerDossierProjection> DossiersById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, CrewProjection> CrewsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, CampaignProjection> CampaignSpinesById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, RunProjection> RunsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public List<RosterTransferProjection> RosterTransfers { get; } = new();
    public List<DossierMovementReceiptProjection> DossierMovements { get; } = new();
    public List<GovernedPrepLaunchProjection> PrepLaunches { get; } = new();
    public List<TravelPrefetchReceiptProjection> TravelPrefetchReceipts { get; } = new();
    public List<AftermathRecapPackageProjection> AftermathPackages { get; } = new();
    public List<CampaignAdoptionProjection> CampaignAdoptions { get; } = new();
    public List<RunnerGoalProjection> RunnerGoals { get; } = new();
    public List<ResolutionReportApprovalProjection> ResolutionReportApprovals { get; } = new();
    public List<WorldTickProjection> WorldTicks { get; } = new();
    public List<PlayerSafeNewsProjection> PlayerSafeNews { get; } = new();
    public List<OpenRunListingProjection> OpenRuns { get; } = new();
    public List<OpenRunJoinRequestProjection> OpenRunJoinRequests { get; } = new();
    public List<OpenRunRosterEntryProjection> OpenRunRoster { get; } = new();
    public List<OpenRunScheduleReceiptProjection> OpenRunSchedules { get; } = new();
    public List<OpenRunMeetingHandoffProjection> OpenRunMeetingHandoffs { get; } = new();
    public List<OpenRunCloseoutProjection> OpenRunCloseouts { get; } = new();
    internal Dictionary<string, CampaignCollaborationInviteState> CampaignCollaborationInvitesById { get; } = new(StringComparer.OrdinalIgnoreCase);
    internal Dictionary<string, string> CampaignInviteIdByCodeLookupSha256 { get; } = new(StringComparer.Ordinal);
    internal List<CampaignCharacterBindingState> CampaignCharacterBindings { get; } = new();
    internal List<CampaignSharedSheetAuditState> CampaignSharedSheetAudit { get; } = new();
    internal Dictionary<string, CampaignRunsiteState> CampaignRunsitesByRunId { get; } = new(StringComparer.OrdinalIgnoreCase);
    internal Dictionary<string, CampaignCreationIdempotencyState> CampaignCreationsByIdempotencyKey { get; } = new(StringComparer.Ordinal);
    internal Dictionary<string, CampaignInviteCreationIdempotencyState> CampaignInviteCreationsByIdempotencyKey { get; } = new(StringComparer.Ordinal);
    internal Dictionary<string, CampaignRunsiteDraftIdempotencyState> CampaignRunsiteDraftCommandsByIdempotencyKey { get; } = new(StringComparer.Ordinal);
    internal Dictionary<string, CampaignRunsitePublishIdempotencyState> CampaignRunsitePublishCommandsByIdempotencyKey { get; } = new(StringComparer.Ordinal);
    internal Dictionary<string, CampaignRedemptionIdempotencyState> CampaignRedemptionsByIdempotencyKey { get; } = new(StringComparer.Ordinal);
    internal Dictionary<string, CampaignSheetEditIdempotencyState> CampaignSheetEditsByIdempotencyKey { get; } = new(StringComparer.Ordinal);
    internal List<CampaignGmAuthorityAuditState> CampaignGmAuthorityAudit { get; } = new();
    internal Dictionary<string, CampaignGmAuthorityIdempotencyState> CampaignGmAuthorityCommandsByIdempotencyKey { get; } = new(StringComparer.Ordinal);
    internal Action? CampaignCollaborationPersistenceFaultInjector { get; set; }
    public Dictionary<string, PlaySessionBinding> PlaySessionsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, PlaySessionParticipant> PlayParticipantsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, PlaySessionInvite> PlayInvitesById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, PlaySessionExchange> PlayExchangesById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, PlaySessionGrant> PlayGrantsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public DateTimeOffset PlayAuthorizationTimeHighWaterUtc { get; internal set; } = DateTimeOffset.UnixEpoch;
    public Dictionary<string, WorkspaceRestoreProjection> RestoreByUserId { get; } = new(StringComparer.OrdinalIgnoreCase);
    public BlackLedgerFactionOnboardingState? BlackLedgerFactionOnboardingState { get; set; }

    internal T ExecuteCampaignCollaborationTransactionLocked<T>(Func<T> mutation)
    {
        ArgumentNullException.ThrowIfNull(mutation);
        if (!System.Threading.Monitor.IsEntered(Gate))
        {
            throw new InvalidOperationException("Campaign collaboration transactions require the community-store lock.");
        }

        CampaignCollaborationTransactionSnapshot before = CaptureCampaignCollaborationTransactionLocked();
        try
        {
            T result = mutation();
            CampaignCollaborationPersistenceFaultInjector?.Invoke();
            PersistLocked();
            return result;
        }
        catch
        {
            RestoreCampaignCollaborationTransactionLocked(before);
            throw;
        }
    }

    private CampaignCollaborationTransactionSnapshot CaptureCampaignCollaborationTransactionLocked()
        => new(
            UsersById.Values.ToArray(),
            GroupsById.Values.ToArray(),
            DossiersById.Values.ToArray(),
            CrewsById.Values.ToArray(),
            CampaignSpinesById.Values.ToArray(),
            RunsById.Values.ToArray(),
            CampaignCollaborationInvitesById.Values.ToArray(),
            CampaignInviteIdByCodeLookupSha256.ToArray(),
            CampaignCharacterBindings.ToArray(),
            CampaignSharedSheetAudit.ToArray(),
            CampaignRunsitesByRunId.ToArray(),
            CampaignCreationsByIdempotencyKey.ToArray(),
            CampaignInviteCreationsByIdempotencyKey.ToArray(),
            CampaignRunsiteDraftCommandsByIdempotencyKey.ToArray(),
            CampaignRunsitePublishCommandsByIdempotencyKey.ToArray(),
            CampaignRedemptionsByIdempotencyKey.ToArray(),
            CampaignSheetEditsByIdempotencyKey.ToArray(),
            CampaignGmAuthorityAudit.ToArray(),
            CampaignGmAuthorityCommandsByIdempotencyKey.ToArray());

    private void RestoreCampaignCollaborationTransactionLocked(CampaignCollaborationTransactionSnapshot snapshot)
    {
        ReplaceDictionary(UsersById, snapshot.Users, static item => item.UserId);
        UserIdBySubjectId.Clear();
        foreach (HubUserDto user in snapshot.Users)
        {
            foreach (string subject in new[] { user.SubjectId }.Concat(user.LinkedPrincipals ?? Array.Empty<string>()))
            {
                string? normalized = AccountService.NormalizeOptional(subject);
                if (normalized is not null)
                {
                    UserIdBySubjectId[normalized] = user.UserId;
                }
            }
        }

        ReplaceDictionary(GroupsById, snapshot.Groups, static item => item.GroupId);
        ReplaceDictionary(DossiersById, snapshot.Dossiers, static item => item.DossierId);
        ReplaceDictionary(CrewsById, snapshot.Crews, static item => item.CrewId);
        ReplaceDictionary(CampaignSpinesById, snapshot.Campaigns, static item => item.CampaignId);
        ReplaceDictionary(RunsById, snapshot.Runs, static item => item.RunId);
        ReplaceDictionary(CampaignCollaborationInvitesById, snapshot.Invites, static item => item.InviteId);
        ReplaceDictionary(CampaignInviteIdByCodeLookupSha256, snapshot.InviteCodeIndex);
        ReplaceList(CampaignCharacterBindings, snapshot.CharacterBindings);
        ReplaceList(CampaignSharedSheetAudit, snapshot.SheetAudit);
        ReplaceDictionary(CampaignRunsitesByRunId, snapshot.Runsites);
        ReplaceDictionary(CampaignCreationsByIdempotencyKey, snapshot.CampaignCreations);
        ReplaceDictionary(CampaignInviteCreationsByIdempotencyKey, snapshot.InviteCreations);
        ReplaceDictionary(CampaignRunsiteDraftCommandsByIdempotencyKey, snapshot.RunsiteDraftCommands);
        ReplaceDictionary(CampaignRunsitePublishCommandsByIdempotencyKey, snapshot.RunsitePublishCommands);
        ReplaceDictionary(CampaignRedemptionsByIdempotencyKey, snapshot.Redemptions);
        ReplaceDictionary(CampaignSheetEditsByIdempotencyKey, snapshot.SheetEdits);
        ReplaceList(CampaignGmAuthorityAudit, snapshot.GmAuthorityAudit);
        ReplaceDictionary(CampaignGmAuthorityCommandsByIdempotencyKey, snapshot.GmAuthorityCommands);
    }

    private static void ReplaceDictionary<TKey, TValue>(
        Dictionary<TKey, TValue> target,
        IEnumerable<TValue> values,
        Func<TValue, TKey> keySelector)
        where TKey : notnull
    {
        target.Clear();
        foreach (TValue value in values)
        {
            target[keySelector(value)] = value;
        }
    }

    private static void ReplaceDictionary<TKey, TValue>(
        Dictionary<TKey, TValue> target,
        IEnumerable<KeyValuePair<TKey, TValue>> values)
        where TKey : notnull
    {
        target.Clear();
        foreach ((TKey key, TValue value) in values)
        {
            target[key] = value;
        }
    }

    private static void ReplaceList<T>(List<T> target, IEnumerable<T> values)
    {
        target.Clear();
        target.AddRange(values);
    }

    public void PersistLocked()
    {
        if (!System.Threading.Monitor.IsEntered(Gate))
        {
            lock (Gate)
            {
                PersistLocked();
            }

            return;
        }

        PlaySessionAuthorizationValidator.ValidateSnapshot(
            PlaySessionsById.Values,
            PlayParticipantsById.Values,
            PlayInvitesById.Values,
            PlayExchangesById.Values,
            PlayGrantsById.Values);
        PlaySessionAuthorizationValidator.ValidateTimeHighWater(PlayAuthorizationTimeHighWaterUtc);

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
            LinkedIdentities: LinkedIdentities.ToArray(),
            ChannelLinks: ChannelLinks.ToArray(),
            Receipts: Receipts.ToArray(),
            LedgerEntries: LedgerEntries.ToArray(),
            RewardEntries: RewardEntries.ToArray(),
            EntitlementEntries: EntitlementEntries.ToArray(),
            Badges: Badges.ToArray(),
            UserExperience: UserExperienceByUserId.Values
                .OrderBy(static item => item.UserId, StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            ParticipationNotificationReceipts: ParticipationNotificationReceipts
                .OrderByDescending(static item => item.OccurredAtUtc)
                .ToArray(),
            BlackLedgerNewsDeliveryReceipts: BlackLedgerNewsDeliveryReceipts
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray(),
            BlackLedgerInboxEntries: BlackLedgerInboxEntries
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray(),
            BlackLedgerAdvisoryVoteReceipts: BlackLedgerAdvisoryVoteReceipts
                .OrderByDescending(static item => item.VotedAtUtc)
                .ToArray(),
            BlackLedgerAdvisoryMailReceipts: BlackLedgerAdvisoryMailReceipts
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray(),
            BlackLedgerDispatches: BlackLedgerDispatches
                .OrderByDescending(static item => item.CreatedAtUtc, StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            BlackLedgerDispatchDrafts: BlackLedgerDispatchDrafts
                .OrderByDescending(static item => item.GeneratedAtUtc, StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            BlackLedgerDispatchGateReceipts: BlackLedgerDispatchGateReceipts
                .OrderByDescending(static item => item.CheckedAtUtc, StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            BlackLedgerDispatchApprovalReceipts: BlackLedgerDispatchApprovalReceipts
                .OrderByDescending(static item => item.ApprovedAtUtc, StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            BlackLedgerDispatchPublicationReceipts: BlackLedgerDispatchPublicationReceipts
                .OrderByDescending(static item => item.PublishedAtUtc, StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            HeyyScamChatConversations: HeyyScamChatConversations
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray(),
            HeyyScamChatDigestReceipts: HeyyScamChatDigestReceipts
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray(),
            HeyyScamChatApprovalReceipts: HeyyScamChatApprovalReceipts
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray(),
            HeyyScamChatOperatorSummaryReceipts: HeyyScamChatOperatorSummaryReceipts
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray(),
            ExecutiveAssistantChannelConversations: ExecutiveAssistantChannelConversations
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray(),
            ExecutiveAssistantChannelMessages: ExecutiveAssistantChannelMessages
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray(),
            ImportantWorkItems: ImportantWorkItems
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray(),
            Dossiers: DossiersById.Values.OrderBy(static item => item.DossierId, StringComparer.OrdinalIgnoreCase).ToArray(),
            Crews: CrewsById.Values.OrderBy(static item => item.CrewId, StringComparer.OrdinalIgnoreCase).ToArray(),
            CampaignSpines: CampaignSpinesById.Values.OrderBy(static item => item.CampaignId, StringComparer.OrdinalIgnoreCase).ToArray(),
            Runs: RunsById.Values.OrderBy(static item => item.RunId, StringComparer.OrdinalIgnoreCase).ToArray(),
            RosterTransfers: RosterTransfers.OrderByDescending(static item => item.TransferredAtUtc).ToArray(),
            DossierMovements: DossierMovements.OrderByDescending(static item => item.MovedAtUtc).ToArray(),
            PrepLaunches: PrepLaunches.OrderByDescending(static item => item.LaunchedAtUtc).ToArray(),
            TravelPrefetchReceipts: TravelPrefetchReceipts.OrderByDescending(static item => item.StagedAtUtc).ToArray(),
            AftermathPackages: AftermathPackages.OrderByDescending(static item => item.GeneratedAtUtc).ToArray(),
            CampaignAdoptions: CampaignAdoptions.OrderByDescending(static item => item.UpdatedAtUtc).ToArray(),
            RunnerGoals: RunnerGoals.OrderByDescending(static item => item.UpdatedAtUtc).ToArray(),
            ResolutionReportApprovals: ResolutionReportApprovals.OrderByDescending(static item => item.UpdatedAtUtc).ToArray(),
            WorldTicks: WorldTicks.OrderByDescending(static item => item.UpdatedAtUtc).ToArray(),
            PlayerSafeNews: PlayerSafeNews.OrderByDescending(static item => item.UpdatedAtUtc).ToArray(),
            OpenRuns: OpenRuns.OrderByDescending(static item => item.UpdatedAtUtc).ToArray(),
            OpenRunJoinRequests: OpenRunJoinRequests.OrderByDescending(static item => item.UpdatedAtUtc).ToArray(),
            OpenRunRoster: OpenRunRoster.OrderByDescending(static item => item.UpdatedAtUtc).ToArray(),
            OpenRunSchedules: OpenRunSchedules.OrderByDescending(static item => item.ScheduledAtUtc).ToArray(),
            OpenRunMeetingHandoffs: OpenRunMeetingHandoffs.OrderByDescending(static item => item.CreatedAtUtc).ToArray(),
            OpenRunCloseouts: OpenRunCloseouts.OrderByDescending(static item => item.ClosedAtUtc).ToArray(),
            RestoreSummaries: RestoreByUserId.Values.OrderBy(static item => item.UserId, StringComparer.OrdinalIgnoreCase).ToArray(),
            BlackLedgerFactionOnboarding: BlackLedgerFactionOnboardingState,
            PlaySessions: PlaySessionsById.Values.OrderBy(static item => item.SessionId, StringComparer.OrdinalIgnoreCase).ToArray(),
            PlayParticipants: PlayParticipantsById.Values.OrderBy(static item => item.ParticipantId, StringComparer.OrdinalIgnoreCase).ToArray(),
            PlayInvites: PlayInvitesById.Values.OrderBy(static item => item.InviteId, StringComparer.OrdinalIgnoreCase).ToArray(),
            PlayExchanges: PlayExchangesById.Values.OrderBy(static item => item.ExchangeId, StringComparer.OrdinalIgnoreCase).ToArray(),
            PlayGrants: PlayGrantsById.Values.OrderBy(static item => item.GrantId, StringComparer.OrdinalIgnoreCase).ToArray(),
            PlayAuthorizationTimeHighWaterUtc: PlayAuthorizationTimeHighWaterUtc,
            CampaignCollaborationInvites: CampaignCollaborationInvitesById.Values
                .OrderBy(static item => item.InviteId, StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            CampaignCharacterBindings: CampaignCharacterBindings
                .OrderBy(static item => item.CampaignId, StringComparer.OrdinalIgnoreCase)
                .ThenBy(static item => item.DossierId, StringComparer.OrdinalIgnoreCase)
                .ThenBy(static item => item.BindingRevision)
                .ToArray(),
            CampaignSharedSheetAudit: CampaignSharedSheetAudit
                .OrderBy(static item => item.EditedAtUtc)
                .ThenBy(static item => item.ReceiptId, StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            CampaignRunsites: CampaignRunsitesByRunId.Values
                .OrderBy(static item => item.CampaignId, StringComparer.OrdinalIgnoreCase)
                .ThenBy(static item => item.RunId, StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            CampaignCreations: CampaignCreationsByIdempotencyKey.Values
                .OrderBy(static item => item.Key, StringComparer.Ordinal)
                .ToArray(),
            CampaignInviteCreations: CampaignInviteCreationsByIdempotencyKey.Values
                .OrderBy(static item => item.Key, StringComparer.Ordinal)
                .ToArray(),
            CampaignRunsiteDraftCommands: CampaignRunsiteDraftCommandsByIdempotencyKey.Values
                .OrderBy(static item => item.Key, StringComparer.Ordinal)
                .ToArray(),
            CampaignRunsitePublishCommands: CampaignRunsitePublishCommandsByIdempotencyKey.Values
                .OrderBy(static item => item.Key, StringComparer.Ordinal)
                .ToArray(),
            CampaignRedemptions: CampaignRedemptionsByIdempotencyKey.Values
                .OrderBy(static item => item.Key, StringComparer.Ordinal)
                .ToArray(),
            CampaignSheetEdits: CampaignSheetEditsByIdempotencyKey.Values
                .OrderBy(static item => item.Key, StringComparer.Ordinal)
                .ToArray(),
            CampaignGmAuthorityAudit: CampaignGmAuthorityAudit
                .OrderBy(static item => item.ChangedAtUtc)
                .ThenBy(static item => item.ReceiptId, StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            CampaignGmAuthorityCommands: CampaignGmAuthorityCommandsByIdempotencyKey.Values
                .OrderBy(static item => item.Key, StringComparer.Ordinal)
                .ToArray());

        CampaignCollaborationStateValidator.ValidateSnapshot(
            snapshot.CampaignCollaborationInvites ?? Array.Empty<CampaignCollaborationInviteState>(),
            snapshot.CampaignCharacterBindings ?? Array.Empty<CampaignCharacterBindingState>(),
            snapshot.CampaignSharedSheetAudit ?? Array.Empty<CampaignSharedSheetAuditState>(),
            snapshot.CampaignRunsites ?? Array.Empty<CampaignRunsiteState>(),
            snapshot.CampaignCreations ?? Array.Empty<CampaignCreationIdempotencyState>(),
            snapshot.CampaignInviteCreations ?? Array.Empty<CampaignInviteCreationIdempotencyState>(),
            snapshot.CampaignRunsiteDraftCommands ?? Array.Empty<CampaignRunsiteDraftIdempotencyState>(),
            snapshot.CampaignRunsitePublishCommands ?? Array.Empty<CampaignRunsitePublishIdempotencyState>(),
            snapshot.CampaignRedemptions ?? Array.Empty<CampaignRedemptionIdempotencyState>(),
            snapshot.CampaignSheetEdits ?? Array.Empty<CampaignSheetEditIdempotencyState>(),
            snapshot.CampaignGmAuthorityAudit ?? Array.Empty<CampaignGmAuthorityAuditState>(),
            snapshot.CampaignGmAuthorityCommands ?? Array.Empty<CampaignGmAuthorityIdempotencyState>(),
            snapshot.Dossiers ?? Array.Empty<RunnerDossierProjection>(),
            snapshot.CampaignSpines ?? Array.Empty<CampaignProjection>());

        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        var tempPath = $"{_storagePath}.tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions), System.Text.Encoding.UTF8);
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

            try
            {
                var snapshotJson = File.ReadAllText(_storagePath, System.Text.Encoding.UTF8);
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
            catch (JsonException ex)
            {
                ApplySnapshotLocked(new CommunityStoreSnapshot(
                    Users: [],
                    Groups: [],
                    JoinCodes: [],
                    Campaigns: [],
                    BoostCodes: [],
                    SponsorSessions: [],
                    LinkedIdentities: [],
                    ChannelLinks: [],
                    Receipts: [],
                    LedgerEntries: [],
                    RewardEntries: [],
                    EntitlementEntries: [],
                    Badges: []));
                QuarantineCorruptStoreFile();
                _logger.LogWarning(ex, "CommunityStore quarantined corrupt durable state at {StoragePath} and restarted empty.", _storagePath);
            }
        }
    }

    private void QuarantineCorruptStoreFile()
    {
        string quarantinePath = $"{_storagePath}.corrupt-{DateTimeOffset.UtcNow:yyyyMMddHHmmssfff}";
        try
        {
            File.Move(_storagePath, quarantinePath);
        }
        catch
        {
            // Starting empty is safer than crashing when a local community store file is unreadable.
        }
    }

    private void ApplySnapshotLocked(CommunityStoreSnapshot snapshot)
    {
        PlaySessionAuthorizationValidator.ValidateSnapshot(
            snapshot.PlaySessions ?? Array.Empty<PlaySessionBinding>(),
            snapshot.PlayParticipants ?? Array.Empty<PlaySessionParticipant>(),
            snapshot.PlayInvites ?? Array.Empty<PlaySessionInvite>(),
            snapshot.PlayExchanges ?? Array.Empty<PlaySessionExchange>(),
            snapshot.PlayGrants ?? Array.Empty<PlaySessionGrant>());
        PlaySessionAuthorizationValidator.ValidateTimeHighWater(snapshot.PlayAuthorizationTimeHighWaterUtc);
        CampaignCollaborationStateValidator.ValidateSnapshot(
            snapshot.CampaignCollaborationInvites ?? Array.Empty<CampaignCollaborationInviteState>(),
            snapshot.CampaignCharacterBindings ?? Array.Empty<CampaignCharacterBindingState>(),
            snapshot.CampaignSharedSheetAudit ?? Array.Empty<CampaignSharedSheetAuditState>(),
            snapshot.CampaignRunsites ?? Array.Empty<CampaignRunsiteState>(),
            snapshot.CampaignCreations ?? Array.Empty<CampaignCreationIdempotencyState>(),
            snapshot.CampaignInviteCreations ?? Array.Empty<CampaignInviteCreationIdempotencyState>(),
            snapshot.CampaignRunsiteDraftCommands ?? Array.Empty<CampaignRunsiteDraftIdempotencyState>(),
            snapshot.CampaignRunsitePublishCommands ?? Array.Empty<CampaignRunsitePublishIdempotencyState>(),
            snapshot.CampaignRedemptions ?? Array.Empty<CampaignRedemptionIdempotencyState>(),
            snapshot.CampaignSheetEdits ?? Array.Empty<CampaignSheetEditIdempotencyState>(),
            snapshot.CampaignGmAuthorityAudit ?? Array.Empty<CampaignGmAuthorityAuditState>(),
            snapshot.CampaignGmAuthorityCommands ?? Array.Empty<CampaignGmAuthorityIdempotencyState>(),
            snapshot.Dossiers ?? Array.Empty<RunnerDossierProjection>(),
            snapshot.CampaignSpines ?? Array.Empty<CampaignProjection>());

        UsersById.Clear();
        UserIdBySubjectId.Clear();
        GroupsById.Clear();
        JoinCodesByValue.Clear();
        CampaignsById.Clear();
        BoostCodesByValue.Clear();
        SponsorSessionsById.Clear();
        LinkedIdentities.Clear();
        ChannelLinks.Clear();
        Receipts.Clear();
        LedgerEntries.Clear();
        RewardEntries.Clear();
        EntitlementEntries.Clear();
        Badges.Clear();
        UserExperienceByUserId.Clear();
        ParticipationNotificationReceipts.Clear();
        BlackLedgerNewsDeliveryReceipts.Clear();
        BlackLedgerInboxEntries.Clear();
        BlackLedgerAdvisoryVoteReceipts.Clear();
        BlackLedgerAdvisoryMailReceipts.Clear();
        BlackLedgerDispatches.Clear();
        BlackLedgerDispatchDrafts.Clear();
        BlackLedgerDispatchGateReceipts.Clear();
        BlackLedgerDispatchApprovalReceipts.Clear();
        BlackLedgerDispatchPublicationReceipts.Clear();
        HeyyScamChatConversations.Clear();
        HeyyScamChatDigestReceipts.Clear();
        HeyyScamChatApprovalReceipts.Clear();
        HeyyScamChatOperatorSummaryReceipts.Clear();
        ExecutiveAssistantChannelConversations.Clear();
        ExecutiveAssistantChannelMessages.Clear();
        ImportantWorkItems.Clear();
        DossiersById.Clear();
        CrewsById.Clear();
        CampaignSpinesById.Clear();
        RunsById.Clear();
        RosterTransfers.Clear();
        DossierMovements.Clear();
        PrepLaunches.Clear();
        TravelPrefetchReceipts.Clear();
        AftermathPackages.Clear();
        CampaignAdoptions.Clear();
        RunnerGoals.Clear();
        ResolutionReportApprovals.Clear();
        WorldTicks.Clear();
        PlayerSafeNews.Clear();
        OpenRuns.Clear();
        OpenRunJoinRequests.Clear();
        OpenRunRoster.Clear();
        OpenRunSchedules.Clear();
        OpenRunMeetingHandoffs.Clear();
        OpenRunCloseouts.Clear();
        CampaignCollaborationInvitesById.Clear();
        CampaignInviteIdByCodeLookupSha256.Clear();
        CampaignCharacterBindings.Clear();
        CampaignSharedSheetAudit.Clear();
        CampaignRunsitesByRunId.Clear();
        CampaignCreationsByIdempotencyKey.Clear();
        CampaignInviteCreationsByIdempotencyKey.Clear();
        CampaignRunsiteDraftCommandsByIdempotencyKey.Clear();
        CampaignRunsitePublishCommandsByIdempotencyKey.Clear();
        CampaignRedemptionsByIdempotencyKey.Clear();
        CampaignSheetEditsByIdempotencyKey.Clear();
        CampaignGmAuthorityAudit.Clear();
        CampaignGmAuthorityCommandsByIdempotencyKey.Clear();
        PlaySessionsById.Clear();
        PlayParticipantsById.Clear();
        PlayInvitesById.Clear();
        PlayExchangesById.Clear();
        PlayGrantsById.Clear();
        PlayAuthorizationTimeHighWaterUtc = snapshot.PlayAuthorizationTimeHighWaterUtc ?? DateTimeOffset.UnixEpoch;
        RestoreByUserId.Clear();
        BlackLedgerFactionOnboardingState = null;

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

        LinkedIdentities.AddRange(snapshot.LinkedIdentities ?? Array.Empty<LinkedIdentityDto>());
        ChannelLinks.AddRange(snapshot.ChannelLinks ?? Array.Empty<ChannelLinkDto>());
        Receipts.AddRange(snapshot.Receipts ?? Array.Empty<ContributionReceiptDto>());
        LedgerEntries.AddRange(snapshot.LedgerEntries ?? Array.Empty<LedgerEntryDto>());
        RewardEntries.AddRange(snapshot.RewardEntries ?? Array.Empty<RewardJournalEntryDto>());
        EntitlementEntries.AddRange(snapshot.EntitlementEntries ?? Array.Empty<EntitlementGrantDto>());
        Badges.AddRange(snapshot.Badges ?? Array.Empty<BadgeDto>());
        foreach (var experience in snapshot.UserExperience ?? Array.Empty<HubUserExperienceDto>())
        {
            UserExperienceByUserId[experience.UserId] = experience;
        }
        ParticipationNotificationReceipts.AddRange(snapshot.ParticipationNotificationReceipts ?? Array.Empty<ParticipationOperatorNotificationReceipt>());
        BlackLedgerNewsDeliveryReceipts.AddRange(snapshot.BlackLedgerNewsDeliveryReceipts ?? Array.Empty<BlackLedgerNewsDeliveryReceipt>());
        BlackLedgerInboxEntries.AddRange(snapshot.BlackLedgerInboxEntries ?? Array.Empty<BlackLedgerInboxEntry>());
        BlackLedgerAdvisoryVoteReceipts.AddRange(snapshot.BlackLedgerAdvisoryVoteReceipts ?? Array.Empty<BlackLedgerAdvisoryVoteReceipt>());
        BlackLedgerAdvisoryMailReceipts.AddRange(snapshot.BlackLedgerAdvisoryMailReceipts ?? Array.Empty<BlackLedgerAdvisoryMailReceipt>());
        BlackLedgerDispatches.AddRange(snapshot.BlackLedgerDispatches ?? Array.Empty<BlackLedgerDispatch>());
        BlackLedgerDispatchDrafts.AddRange(snapshot.BlackLedgerDispatchDrafts ?? Array.Empty<DispatchDraft>());
        BlackLedgerDispatchGateReceipts.AddRange(snapshot.BlackLedgerDispatchGateReceipts ?? Array.Empty<DispatchGateReceipt>());
        BlackLedgerDispatchApprovalReceipts.AddRange(snapshot.BlackLedgerDispatchApprovalReceipts ?? Array.Empty<DispatchApprovalReceipt>());
        BlackLedgerDispatchPublicationReceipts.AddRange(snapshot.BlackLedgerDispatchPublicationReceipts ?? Array.Empty<DispatchPublicationReceipt>());
        HeyyScamChatConversations.AddRange(snapshot.HeyyScamChatConversations ?? Array.Empty<HeyyScamChatConversationState>());
        HeyyScamChatDigestReceipts.AddRange(snapshot.HeyyScamChatDigestReceipts ?? Array.Empty<HeyyScamChatDigestReceipt>());
        HeyyScamChatApprovalReceipts.AddRange(snapshot.HeyyScamChatApprovalReceipts ?? Array.Empty<HeyyScamChatApprovalReceipt>());
        HeyyScamChatOperatorSummaryReceipts.AddRange(snapshot.HeyyScamChatOperatorSummaryReceipts ?? Array.Empty<HeyyScamChatOperatorSummaryReceipt>());
        ExecutiveAssistantChannelConversations.AddRange(snapshot.ExecutiveAssistantChannelConversations ?? Array.Empty<ExecutiveAssistantChannelConversationState>());
        ExecutiveAssistantChannelMessages.AddRange(snapshot.ExecutiveAssistantChannelMessages ?? Array.Empty<ExecutiveAssistantChannelMessageState>());
        ImportantWorkItems.AddRange(snapshot.ImportantWorkItems ?? Array.Empty<ImportantWorkItemProjection>());

        foreach (var dossier in snapshot.Dossiers ?? Array.Empty<RunnerDossierProjection>())
        {
            DossiersById[dossier.DossierId] = dossier;
        }

        foreach (var crew in snapshot.Crews ?? Array.Empty<CrewProjection>())
        {
            CrewsById[crew.CrewId] = crew;
        }

        foreach (var campaign in snapshot.CampaignSpines ?? Array.Empty<CampaignProjection>())
        {
            CampaignSpinesById[campaign.CampaignId] = campaign;
        }

        foreach (var run in snapshot.Runs ?? Array.Empty<RunProjection>())
        {
            RunsById[run.RunId] = run;
        }

        RosterTransfers.AddRange(snapshot.RosterTransfers ?? Array.Empty<RosterTransferProjection>());
        DossierMovements.AddRange(snapshot.DossierMovements ?? Array.Empty<DossierMovementReceiptProjection>());
        PrepLaunches.AddRange(snapshot.PrepLaunches ?? Array.Empty<GovernedPrepLaunchProjection>());
        TravelPrefetchReceipts.AddRange(snapshot.TravelPrefetchReceipts ?? Array.Empty<TravelPrefetchReceiptProjection>());
        AftermathPackages.AddRange(snapshot.AftermathPackages ?? Array.Empty<AftermathRecapPackageProjection>());
        CampaignAdoptions.AddRange(snapshot.CampaignAdoptions ?? Array.Empty<CampaignAdoptionProjection>());
        RunnerGoals.AddRange(snapshot.RunnerGoals ?? Array.Empty<RunnerGoalProjection>());
        ResolutionReportApprovals.AddRange(snapshot.ResolutionReportApprovals ?? Array.Empty<ResolutionReportApprovalProjection>());
        WorldTicks.AddRange(snapshot.WorldTicks ?? Array.Empty<WorldTickProjection>());
        PlayerSafeNews.AddRange(snapshot.PlayerSafeNews ?? Array.Empty<PlayerSafeNewsProjection>());
        OpenRuns.AddRange(snapshot.OpenRuns ?? Array.Empty<OpenRunListingProjection>());
        OpenRunJoinRequests.AddRange(snapshot.OpenRunJoinRequests ?? Array.Empty<OpenRunJoinRequestProjection>());
        OpenRunRoster.AddRange(snapshot.OpenRunRoster ?? Array.Empty<OpenRunRosterEntryProjection>());
        OpenRunSchedules.AddRange(snapshot.OpenRunSchedules ?? Array.Empty<OpenRunScheduleReceiptProjection>());
        OpenRunMeetingHandoffs.AddRange(snapshot.OpenRunMeetingHandoffs ?? Array.Empty<OpenRunMeetingHandoffProjection>());
        OpenRunCloseouts.AddRange(snapshot.OpenRunCloseouts ?? Array.Empty<OpenRunCloseoutProjection>());

        foreach (CampaignCollaborationInviteState invite in snapshot.CampaignCollaborationInvites ?? Array.Empty<CampaignCollaborationInviteState>())
        {
            CampaignCollaborationInvitesById[invite.InviteId] = invite;
            if (!CampaignInviteIdByCodeLookupSha256.TryAdd(invite.ShortCodeLookupSha256, invite.InviteId))
            {
                throw new InvalidDataException("Campaign invite snapshot contains a duplicate code lookup key.");
            }
        }

        CampaignCharacterBindings.AddRange(snapshot.CampaignCharacterBindings ?? Array.Empty<CampaignCharacterBindingState>());
        CampaignSharedSheetAudit.AddRange(snapshot.CampaignSharedSheetAudit ?? Array.Empty<CampaignSharedSheetAuditState>());
        foreach (CampaignRunsiteState runsite in snapshot.CampaignRunsites ?? Array.Empty<CampaignRunsiteState>())
        {
            CampaignRunsitesByRunId[$"{runsite.CampaignId}:{runsite.RunId}"] = runsite;
        }

        foreach (CampaignCreationIdempotencyState campaignCreation in snapshot.CampaignCreations ?? Array.Empty<CampaignCreationIdempotencyState>())
        {
            CampaignCreationsByIdempotencyKey[campaignCreation.Key] = campaignCreation;
        }

        foreach (CampaignInviteCreationIdempotencyState inviteCreation in snapshot.CampaignInviteCreations ?? Array.Empty<CampaignInviteCreationIdempotencyState>())
        {
            CampaignInviteCreationsByIdempotencyKey[inviteCreation.Key] = inviteCreation;
        }

        foreach (CampaignRunsiteDraftIdempotencyState command in snapshot.CampaignRunsiteDraftCommands ?? Array.Empty<CampaignRunsiteDraftIdempotencyState>())
        {
            CampaignRunsiteDraftCommandsByIdempotencyKey[command.Key] = command;
        }

        foreach (CampaignRunsitePublishIdempotencyState command in snapshot.CampaignRunsitePublishCommands ?? Array.Empty<CampaignRunsitePublishIdempotencyState>())
        {
            CampaignRunsitePublishCommandsByIdempotencyKey[command.Key] = command;
        }

        foreach (CampaignRedemptionIdempotencyState redemption in snapshot.CampaignRedemptions ?? Array.Empty<CampaignRedemptionIdempotencyState>())
        {
            CampaignRedemptionsByIdempotencyKey[redemption.Key] = redemption;
        }

        foreach (CampaignSheetEditIdempotencyState edit in snapshot.CampaignSheetEdits ?? Array.Empty<CampaignSheetEditIdempotencyState>())
        {
            CampaignSheetEditsByIdempotencyKey[edit.Key] = edit;
        }

        CampaignGmAuthorityAudit.AddRange(snapshot.CampaignGmAuthorityAudit ?? Array.Empty<CampaignGmAuthorityAuditState>());
        foreach (CampaignGmAuthorityIdempotencyState command in snapshot.CampaignGmAuthorityCommands ?? Array.Empty<CampaignGmAuthorityIdempotencyState>())
        {
            CampaignGmAuthorityCommandsByIdempotencyKey[command.Key] = command;
        }

        foreach (var session in snapshot.PlaySessions ?? Array.Empty<PlaySessionBinding>())
        {
            PlaySessionsById[session.SessionId] = session;
        }

        foreach (var participant in snapshot.PlayParticipants ?? Array.Empty<PlaySessionParticipant>())
        {
            PlayParticipantsById[participant.ParticipantId] = participant;
        }

        foreach (var invite in snapshot.PlayInvites ?? Array.Empty<PlaySessionInvite>())
        {
            PlayInvitesById[invite.InviteId] = invite;
        }

        foreach (var exchange in snapshot.PlayExchanges ?? Array.Empty<PlaySessionExchange>())
        {
            PlayExchangesById[exchange.ExchangeId] = exchange;
        }

        foreach (var grant in snapshot.PlayGrants ?? Array.Empty<PlaySessionGrant>())
        {
            PlayGrantsById[grant.GrantId] = grant;
        }

        foreach (var restore in snapshot.RestoreSummaries ?? Array.Empty<WorkspaceRestoreProjection>())
        {
            RestoreByUserId[restore.UserId] = restore;
        }

        BlackLedgerFactionOnboardingState = snapshot.BlackLedgerFactionOnboarding;
    }

    internal static string ResolveStoragePath(IConfiguration configuration)
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
    public string? ParticipantCodexCode { get; set; }
    public string RequestedLaneType { get; set; } = "participant_burst";
    public string RequestedLaneRole { get; set; } = "coding";
    public string Visibility { get; set; } = "group";
    public string Status { get; set; } = "intent_created";
    public bool Consented { get; set; }
    public string? FleetLaneId { get; set; }
    public string? FleetCredentialHandle { get; set; }
    public string? BoostCampaignId { get; set; }
    public string? BoostCodeId { get; set; }
    public string? DeviceAuthVerificationUri { get; set; }
    public string? DeviceAuthUserCode { get; set; }
    public string AuthorizationTier { get; set; } = "unknown";
    public string TierSource { get; set; } = "unknown";
    public DateTimeOffset CreatedAtUtc { get; init; } = DateTimeOffset.UtcNow;
    public DateTimeOffset UpdatedAtUtc { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? ConsentedAtUtc { get; set; }
    public DateTimeOffset? AuthorizedAtUtc { get; set; }
    public DateTimeOffset? ActivatedAtUtc { get; set; }
    public DateTimeOffset? StoppedAtUtc { get; set; }
    public List<SponsorSessionEventDto> Events { get; } = new();

    public SponsorSessionStatusDto Snapshot()
        => new(
            SponsorSessionId,
            UserId,
            GroupId,
            ProjectId,
            ParticipantCodexCode,
            RequestedLaneType,
            RequestedLaneRole,
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
            Events.ToArray(),
            AuthorizationTier,
            TierSource,
            AuthorizedAtUtc,
            !string.IsNullOrWhiteSpace(FleetCredentialHandle));
}

internal sealed record CommunityStoreSnapshot(
    IReadOnlyList<HubUserDto> Users,
    IReadOnlyList<GroupDto> Groups,
    IReadOnlyList<JoinCodeDto> JoinCodes,
    IReadOnlyList<BoostCampaignDto> Campaigns,
    IReadOnlyList<BoostCodeDto> BoostCodes,
    IReadOnlyList<SponsorSessionStateSnapshot> SponsorSessions,
    IReadOnlyList<LinkedIdentityDto>? LinkedIdentities,
    IReadOnlyList<ChannelLinkDto>? ChannelLinks,
    IReadOnlyList<ContributionReceiptDto> Receipts,
    IReadOnlyList<LedgerEntryDto> LedgerEntries,
    IReadOnlyList<RewardJournalEntryDto> RewardEntries,
    IReadOnlyList<EntitlementGrantDto> EntitlementEntries,
    IReadOnlyList<BadgeDto> Badges,
    IReadOnlyList<HubUserExperienceDto>? UserExperience = null,
    IReadOnlyList<ParticipationOperatorNotificationReceipt>? ParticipationNotificationReceipts = null,
    IReadOnlyList<BlackLedgerNewsDeliveryReceipt>? BlackLedgerNewsDeliveryReceipts = null,
    IReadOnlyList<BlackLedgerInboxEntry>? BlackLedgerInboxEntries = null,
    IReadOnlyList<BlackLedgerAdvisoryVoteReceipt>? BlackLedgerAdvisoryVoteReceipts = null,
    IReadOnlyList<BlackLedgerAdvisoryMailReceipt>? BlackLedgerAdvisoryMailReceipts = null,
    IReadOnlyList<BlackLedgerDispatch>? BlackLedgerDispatches = null,
    IReadOnlyList<DispatchDraft>? BlackLedgerDispatchDrafts = null,
    IReadOnlyList<DispatchGateReceipt>? BlackLedgerDispatchGateReceipts = null,
    IReadOnlyList<DispatchApprovalReceipt>? BlackLedgerDispatchApprovalReceipts = null,
    IReadOnlyList<DispatchPublicationReceipt>? BlackLedgerDispatchPublicationReceipts = null,
    IReadOnlyList<HeyyScamChatConversationState>? HeyyScamChatConversations = null,
    IReadOnlyList<HeyyScamChatDigestReceipt>? HeyyScamChatDigestReceipts = null,
    IReadOnlyList<HeyyScamChatApprovalReceipt>? HeyyScamChatApprovalReceipts = null,
    IReadOnlyList<HeyyScamChatOperatorSummaryReceipt>? HeyyScamChatOperatorSummaryReceipts = null,
    IReadOnlyList<ExecutiveAssistantChannelConversationState>? ExecutiveAssistantChannelConversations = null,
    IReadOnlyList<ExecutiveAssistantChannelMessageState>? ExecutiveAssistantChannelMessages = null,
    IReadOnlyList<ImportantWorkItemProjection>? ImportantWorkItems = null,
    IReadOnlyList<RunnerDossierProjection>? Dossiers = null,
    IReadOnlyList<CrewProjection>? Crews = null,
    IReadOnlyList<CampaignProjection>? CampaignSpines = null,
    IReadOnlyList<RunProjection>? Runs = null,
    IReadOnlyList<RosterTransferProjection>? RosterTransfers = null,
    IReadOnlyList<DossierMovementReceiptProjection>? DossierMovements = null,
    IReadOnlyList<GovernedPrepLaunchProjection>? PrepLaunches = null,
    IReadOnlyList<TravelPrefetchReceiptProjection>? TravelPrefetchReceipts = null,
    IReadOnlyList<AftermathRecapPackageProjection>? AftermathPackages = null,
    IReadOnlyList<CampaignAdoptionProjection>? CampaignAdoptions = null,
    IReadOnlyList<RunnerGoalProjection>? RunnerGoals = null,
    IReadOnlyList<ResolutionReportApprovalProjection>? ResolutionReportApprovals = null,
    IReadOnlyList<WorldTickProjection>? WorldTicks = null,
    IReadOnlyList<PlayerSafeNewsProjection>? PlayerSafeNews = null,
    IReadOnlyList<OpenRunListingProjection>? OpenRuns = null,
    IReadOnlyList<OpenRunJoinRequestProjection>? OpenRunJoinRequests = null,
    IReadOnlyList<OpenRunRosterEntryProjection>? OpenRunRoster = null,
    IReadOnlyList<OpenRunScheduleReceiptProjection>? OpenRunSchedules = null,
    IReadOnlyList<OpenRunMeetingHandoffProjection>? OpenRunMeetingHandoffs = null,
    IReadOnlyList<OpenRunCloseoutProjection>? OpenRunCloseouts = null,
    IReadOnlyList<WorkspaceRestoreProjection>? RestoreSummaries = null,
    BlackLedgerFactionOnboardingState? BlackLedgerFactionOnboarding = null,
    IReadOnlyList<PlaySessionBinding>? PlaySessions = null,
    IReadOnlyList<PlaySessionParticipant>? PlayParticipants = null,
    IReadOnlyList<PlaySessionInvite>? PlayInvites = null,
    IReadOnlyList<PlaySessionExchange>? PlayExchanges = null,
    IReadOnlyList<PlaySessionGrant>? PlayGrants = null,
    DateTimeOffset? PlayAuthorizationTimeHighWaterUtc = null,
    IReadOnlyList<CampaignCollaborationInviteState>? CampaignCollaborationInvites = null,
    IReadOnlyList<CampaignCharacterBindingState>? CampaignCharacterBindings = null,
    IReadOnlyList<CampaignSharedSheetAuditState>? CampaignSharedSheetAudit = null,
    IReadOnlyList<CampaignRunsiteState>? CampaignRunsites = null,
    IReadOnlyList<CampaignCreationIdempotencyState>? CampaignCreations = null,
    IReadOnlyList<CampaignInviteCreationIdempotencyState>? CampaignInviteCreations = null,
    IReadOnlyList<CampaignRunsiteDraftIdempotencyState>? CampaignRunsiteDraftCommands = null,
    IReadOnlyList<CampaignRunsitePublishIdempotencyState>? CampaignRunsitePublishCommands = null,
    IReadOnlyList<CampaignRedemptionIdempotencyState>? CampaignRedemptions = null,
    IReadOnlyList<CampaignSheetEditIdempotencyState>? CampaignSheetEdits = null,
    IReadOnlyList<CampaignGmAuthorityAuditState>? CampaignGmAuthorityAudit = null,
    IReadOnlyList<CampaignGmAuthorityIdempotencyState>? CampaignGmAuthorityCommands = null);

internal sealed record CampaignCollaborationTransactionSnapshot(
    IReadOnlyList<HubUserDto> Users,
    IReadOnlyList<GroupDto> Groups,
    IReadOnlyList<RunnerDossierProjection> Dossiers,
    IReadOnlyList<CrewProjection> Crews,
    IReadOnlyList<CampaignProjection> Campaigns,
    IReadOnlyList<RunProjection> Runs,
    IReadOnlyList<CampaignCollaborationInviteState> Invites,
    IReadOnlyList<KeyValuePair<string, string>> InviteCodeIndex,
    IReadOnlyList<CampaignCharacterBindingState> CharacterBindings,
    IReadOnlyList<CampaignSharedSheetAuditState> SheetAudit,
    IReadOnlyList<KeyValuePair<string, CampaignRunsiteState>> Runsites,
    IReadOnlyList<KeyValuePair<string, CampaignCreationIdempotencyState>> CampaignCreations,
    IReadOnlyList<KeyValuePair<string, CampaignInviteCreationIdempotencyState>> InviteCreations,
    IReadOnlyList<KeyValuePair<string, CampaignRunsiteDraftIdempotencyState>> RunsiteDraftCommands,
    IReadOnlyList<KeyValuePair<string, CampaignRunsitePublishIdempotencyState>> RunsitePublishCommands,
    IReadOnlyList<KeyValuePair<string, CampaignRedemptionIdempotencyState>> Redemptions,
    IReadOnlyList<KeyValuePair<string, CampaignSheetEditIdempotencyState>> SheetEdits,
    IReadOnlyList<CampaignGmAuthorityAuditState> GmAuthorityAudit,
    IReadOnlyList<KeyValuePair<string, CampaignGmAuthorityIdempotencyState>> GmAuthorityCommands);

public sealed record ImportantWorkItemProjection(
    string ItemId,
    string Kind,
    string Scope,
    string Summary,
    string Detail,
    string Status,
    string Priority,
    string? UserId,
    string? SubjectId,
    string? Source,
    string? Link,
    IReadOnlyList<string> Tags,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc);

internal sealed record SponsorSessionStateSnapshot(
    string SponsorSessionId,
    string UserId,
    string GroupId,
    string ProjectId,
    string? ParticipantCodexCode,
    string RequestedLaneType,
    string RequestedLaneRole,
    string Visibility,
    string Status,
    bool Consented,
    string? FleetLaneId,
    string? FleetCredentialHandle,
    string? BoostCampaignId,
    string? BoostCodeId,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? ConsentedAtUtc,
    DateTimeOffset? ActivatedAtUtc,
    DateTimeOffset? StoppedAtUtc,
    IReadOnlyList<SponsorSessionEventDto> Events,
    string AuthorizationTier = "unknown",
    string TierSource = "unknown",
    DateTimeOffset? AuthorizedAtUtc = null)
{
    public static SponsorSessionStateSnapshot FromState(SponsorSessionState state)
        => new(
            state.SponsorSessionId,
            state.UserId,
            state.GroupId,
            state.ProjectId,
            state.ParticipantCodexCode,
            state.RequestedLaneType,
            state.RequestedLaneRole,
            state.Visibility,
            state.Status,
            state.Consented,
            state.FleetLaneId,
            state.FleetCredentialHandle,
            state.BoostCampaignId,
            state.BoostCodeId,
            state.CreatedAtUtc,
            state.UpdatedAtUtc,
            state.ConsentedAtUtc,
            state.ActivatedAtUtc,
            state.StoppedAtUtc,
            state.Events.ToArray(),
            state.AuthorizationTier,
            state.TierSource,
            state.AuthorizedAtUtc);

    public SponsorSessionState ToState()
    {
        var state = new SponsorSessionState
        {
            SponsorSessionId = SponsorSessionId,
            UserId = UserId,
            GroupId = GroupId,
            ProjectId = ProjectId,
            ParticipantCodexCode = AccountService.NormalizeOptional(ParticipantCodexCode),
            RequestedLaneType = RequestedLaneType,
            RequestedLaneRole = RequestedLaneRole,
            Visibility = Visibility,
            Status = Status,
            Consented = Consented,
            FleetLaneId = FleetLaneId,
            FleetCredentialHandle = FleetCredentialHandle,
            BoostCampaignId = BoostCampaignId,
            BoostCodeId = BoostCodeId,
            CreatedAtUtc = CreatedAtUtc,
            UpdatedAtUtc = UpdatedAtUtc,
            ConsentedAtUtc = ConsentedAtUtc,
            AuthorizedAtUtc = AuthorizedAtUtc,
            ActivatedAtUtc = ActivatedAtUtc,
            StoppedAtUtc = StoppedAtUtc,
            AuthorizationTier = SponsorStatusPolicy.NormalizeAuthorizationTier(AuthorizationTier),
            TierSource = SponsorStatusPolicy.NormalizeTierSource(TierSource),
        };
        if (Events is not null)
        {
            state.Events.AddRange(Events);
        }

        return state;
    }
}
