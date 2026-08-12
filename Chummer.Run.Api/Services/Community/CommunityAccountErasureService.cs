using Chummer.Campaign.Contracts;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed record CommunityAccountErasureResult(
    bool Erased,
    string? UserId,
    int RecordsRemoved,
    int OwnedGroupsRemoved,
    int SharedMembershipsRemoved,
    int PlayAuthorizationRecordsRemoved,
    DateTimeOffset ErasedAtUtc);

/// <summary>
/// Chummer-owned deletion policy for the durable community snapshot. Provider projections
/// are not authoritative and must not be used to decide whether this transaction may run.
/// </summary>
public sealed class CommunityAccountErasureService
{
    private readonly CommunityStore _store;
    private readonly TimeProvider _timeProvider;

    public CommunityAccountErasureService(CommunityStore store, TimeProvider? timeProvider = null)
    {
        _store = store;
        _timeProvider = timeProvider ?? TimeProvider.System;
    }

    public CommunityAccountErasureResult Erase(string subjectId, string? knownUserId = null)
    {
        string normalizedSubject = AccountService.NormalizeRequired(subjectId, nameof(subjectId));
        string? normalizedKnownUserId = AccountService.NormalizeOptional(knownUserId);

        lock (_store.Gate)
        {
            string? userId = ResolveUserId(normalizedSubject, normalizedKnownUserId);
            return _store.ExecuteAccountErasureTransactionLocked(
                () => EraseLocked(normalizedSubject, userId));
        }
    }

    private CommunityAccountErasureResult EraseLocked(string subjectId, string? userId)
    {
        DateTimeOffset erasedAtUtc = _timeProvider.GetUtcNow();
        if (userId is null)
        {
            int orphanSubjectMappings = RemoveDictionaryWhere(
                _store.UserIdBySubjectId,
                pair => IdEquals(pair.Key, subjectId));
            return new CommunityAccountErasureResult(
                Erased: orphanSubjectMappings > 0,
                UserId: null,
                RecordsRemoved: orphanSubjectMappings,
                OwnedGroupsRemoved: 0,
                SharedMembershipsRemoved: 0,
                PlayAuthorizationRecordsRemoved: 0,
                ErasedAtUtc: erasedAtUtc);
        }

        int removed = 0;
        int sharedMembershipsRemoved = 0;

        HashSet<string> ownedGroupIds = _store.GroupsById.Values
            .Where(group => IdEquals(group.OwnerUserId, userId))
            .Select(static group => group.GroupId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        HashSet<string> affectedCampaignIds = _store.CampaignSpinesById.Values
            .Where(campaign => ownedGroupIds.Contains(campaign.GroupId))
            .Select(static campaign => campaign.CampaignId)
            .Concat(_store.CampaignsById.Values
                .Where(campaign => ownedGroupIds.Contains(campaign.GroupId))
                .Select(static campaign => campaign.CampaignId))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        HashSet<string> affectedRunIds = _store.RunsById.Values
            .Where(run => affectedCampaignIds.Contains(run.CampaignId))
            .Select(static run => run.RunId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        HashSet<string> affectedDossierIds = _store.DossiersById.Values
            .Where(dossier => IdEquals(dossier.OwnerUserId, userId)
                              || (dossier.CampaignId is not null && affectedCampaignIds.Contains(dossier.CampaignId)))
            .Select(static dossier => dossier.DossierId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        HashSet<string> affectedCrewIds = _store.CrewsById.Values
            .Where(crew => ownedGroupIds.Contains(crew.GroupId)
                           || affectedCampaignIds.Contains(crew.CampaignId))
            .Select(static crew => crew.CrewId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        HashSet<string> affectedChronicleProjectIds = _store.ChronicleProjectsById.Values
            .Where(project => IdEquals(project.CreatedByUserId, userId)
                              || ownedGroupIds.Contains(project.GroupId))
            .Select(static project => project.ChronicleProjectId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        HashSet<string> affectedSponsorSessionIds = _store.SponsorSessionsById.Values
            .Where(session => IdEquals(session.UserId, userId)
                              || ownedGroupIds.Contains(session.GroupId)
                              || affectedChronicleProjectIds.Contains(session.ProjectId))
            .Select(static session => session.SponsorSessionId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        HashSet<string> affectedOpenRunIds = _store.OpenRuns
            .Where(run => IdEquals(run.CreatedByUserId, userId)
                          || affectedCampaignIds.Contains(run.CampaignId)
                          || affectedRunIds.Contains(run.RunId))
            .Select(static run => run.OpenRunId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        HashSet<string> affectedPlaySessionIds = _store.PlaySessionsById.Values
            .Where(session => IdEquals(session.CreatedByUserId, userId)
                              || ownedGroupIds.Contains(session.GroupId)
                              || affectedCampaignIds.Contains(session.CampaignId)
                              || affectedRunIds.Contains(session.RunId))
            .Select(static session => session.SessionId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        HashSet<string> affectedParticipantIds = _store.PlayParticipantsById.Values
            .Where(participant => affectedPlaySessionIds.Contains(participant.SessionId)
                                  || IdEquals(participant.UserId, userId)
                                  || IdEquals(participant.AddedByUserId, userId))
            .Select(static participant => participant.ParticipantId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        HashSet<string> affectedInviteIds = _store.PlayInvitesById.Values
            .Where(invite => affectedPlaySessionIds.Contains(invite.SessionId)
                             || IdEquals(invite.CreatedByUserId, userId)
                             || IdEquals(invite.TargetUserId, userId)
                             || IdEquals(invite.ConsumedByUserId, userId)
                             || (invite.ParticipantId is not null && affectedParticipantIds.Contains(invite.ParticipantId)))
            .Select(static invite => invite.InviteId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        HashSet<string> affectedGrantIds = _store.PlayGrantsById.Values
            .Where(grant => affectedPlaySessionIds.Contains(grant.SessionId)
                            || affectedParticipantIds.Contains(grant.ParticipantId)
                            || IdEquals(grant.UserId, userId))
            .Select(static grant => grant.GrantId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        HashSet<string> affectedExchangeIds = _store.PlayExchangesById.Values
            .Where(exchange => affectedInviteIds.Contains(exchange.InviteId)
                               || (exchange.GrantId is not null && affectedGrantIds.Contains(exchange.GrantId))
                               || (exchange.SessionId is not null && affectedPlaySessionIds.Contains(exchange.SessionId))
                               || (exchange.ParticipantId is not null && affectedParticipantIds.Contains(exchange.ParticipantId))
                               || IdEquals(exchange.UserId, userId))
            .Select(static exchange => exchange.ExchangeId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        int playRemoved = 0;
        playRemoved += RemoveDictionaryWhere(_store.PlayGrantsById, pair => affectedGrantIds.Contains(pair.Key));
        playRemoved += RemoveDictionaryWhere(_store.PlayExchangesById, pair => affectedExchangeIds.Contains(pair.Key));
        playRemoved += RemoveDictionaryWhere(_store.PlayInvitesById, pair => affectedInviteIds.Contains(pair.Key));
        playRemoved += RemoveDictionaryWhere(_store.PlayParticipantsById, pair => affectedParticipantIds.Contains(pair.Key));
        playRemoved += RemoveDictionaryWhere(_store.PlaySessionsById, pair => affectedPlaySessionIds.Contains(pair.Key));
        removed += playRemoved;

        foreach ((string groupId, GroupDto group) in _store.GroupsById.ToArray())
        {
            if (ownedGroupIds.Contains(groupId))
            {
                _store.GroupsById.Remove(groupId);
                removed++;
                continue;
            }

            GroupMembershipDto[] memberships = group.Memberships
                .Where(membership => !IdEquals(membership.UserId, userId))
                .ToArray();
            int removedFromGroup = group.Memberships.Count - memberships.Length;
            if (removedFromGroup > 0)
            {
                _store.GroupsById[groupId] = group with
                {
                    Memberships = memberships,
                    UpdatedAtUtc = erasedAtUtc
                };
                sharedMembershipsRemoved += removedFromGroup;
                removed += removedFromGroup;
            }
        }

        foreach ((string otherUserId, HubUserDto otherUser) in _store.UsersById.ToArray())
        {
            if (IdEquals(otherUserId, userId))
            {
                continue;
            }

            string[] retainedGroups = otherUser.GroupIds
                .Where(groupId => !ownedGroupIds.Contains(groupId))
                .ToArray();
            if (retainedGroups.Length != otherUser.GroupIds.Count)
            {
                _store.UsersById[otherUserId] = otherUser with
                {
                    GroupIds = retainedGroups,
                    UpdatedAtUtc = erasedAtUtc
                };
                removed += otherUser.GroupIds.Count - retainedGroups.Length;
            }
        }

        removed += RemoveDictionaryWhere(_store.JoinCodesByValue, pair => ownedGroupIds.Contains(pair.Value.GroupId));
        removed += RemoveDictionaryWhere(
            _store.RunnerTicketsById,
            pair => IdEquals(pair.Value.UserId, userId)
                    || ownedGroupIds.Contains(pair.Value.GroupId));
        removed += RemoveDictionaryWhere(
            _store.ChronicleProjectsById,
            pair => affectedChronicleProjectIds.Contains(pair.Key));
        removed += RemoveDictionaryWhere(_store.CampaignsById, pair => ownedGroupIds.Contains(pair.Value.GroupId));
        removed += RemoveDictionaryWhere(
            _store.BoostCodesByValue,
            pair => ownedGroupIds.Contains(pair.Value.GroupId)
                    || affectedCampaignIds.Contains(pair.Value.CampaignId)
                    || IdEquals(pair.Value.CreatedByUserId, userId)
                    || IdEquals(pair.Value.RedeemedByUserId, userId));
        removed += RemoveDictionaryWhere(
            _store.SponsorSessionsById,
            pair => affectedSponsorSessionIds.Contains(pair.Key));

        removed += _store.LinkedIdentities.RemoveAll(link => IdEquals(link.UserId, userId));
        removed += _store.ChannelLinks.RemoveAll(link => IdEquals(link.UserId, userId));
        removed += _store.Receipts.RemoveAll(receipt => IdEquals(receipt.UserId, userId)
                                                       || (receipt.GroupId is not null && ownedGroupIds.Contains(receipt.GroupId))
                                                       || (receipt.SponsorSessionId is not null && affectedSponsorSessionIds.Contains(receipt.SponsorSessionId)));
        removed += _store.LedgerEntries.RemoveAll(entry => IdEquals(entry.UserId, userId)
                                                          || (entry.GroupId is not null && ownedGroupIds.Contains(entry.GroupId)));
        removed += _store.RewardEntries.RemoveAll(entry => IdEquals(entry.UserId, userId)
                                                          || (entry.GroupId is not null && ownedGroupIds.Contains(entry.GroupId)));
        removed += _store.EntitlementEntries.RemoveAll(entry =>
            (IdEquals(entry.Scope, "user") && IdEquals(entry.ScopeId, userId))
            || (IdEquals(entry.Scope, "group") && ownedGroupIds.Contains(entry.ScopeId)));
        removed += _store.Badges.RemoveAll(badge => IdEquals(badge.UserId, userId));
        removed += RemoveDictionaryWhere(_store.UserExperienceByUserId, pair => IdEquals(pair.Key, userId));
        removed += RemoveDictionaryWhere(_store.RestoreByUserId, pair => IdEquals(pair.Key, userId));

        removed += _store.ParticipationNotificationReceipts.RemoveAll(item => IdEquals(item.UserId, userId));
        removed += _store.BlackLedgerNewsDeliveryReceipts.RemoveAll(item => IdEquals(item.RecipientUserId, userId));
        removed += _store.BlackLedgerInboxEntries.RemoveAll(item => IdEquals(item.RecipientUserId, userId));
        removed += _store.BlackLedgerAdvisoryVoteReceipts.RemoveAll(item => IdEquals(item.UserId, userId));
        removed += _store.BlackLedgerAdvisoryMailReceipts.RemoveAll(item => IdEquals(item.RecipientUserId, userId));

        HashSet<string> eaConversationIds = _store.ExecutiveAssistantChannelConversations
            .Where(conversation => IdEquals(conversation.UserId, userId))
            .Select(static conversation => conversation.ConversationId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        removed += _store.ExecutiveAssistantChannelMessages.RemoveAll(message => eaConversationIds.Contains(message.ConversationId));
        removed += _store.ExecutiveAssistantChannelConversations.RemoveAll(conversation => eaConversationIds.Contains(conversation.ConversationId));
        removed += _store.ImportantWorkItems.RemoveAll(item => IdEquals(item.UserId, userId)
                                                        || IdEquals(item.SubjectId, subjectId));

        removed += RemoveDictionaryWhere(_store.DossiersById, pair => affectedDossierIds.Contains(pair.Key));
        removed += RemoveDictionaryWhere(_store.CrewsById, pair => affectedCrewIds.Contains(pair.Key));
        foreach ((string crewId, CrewProjection crew) in _store.CrewsById.ToArray())
        {
            CrewAssignmentProjection[] retained = crew.Members
                .Where(member => !IdEquals(member.UserId, userId)
                                 && !affectedDossierIds.Contains(member.DossierId))
                .ToArray();
            if (retained.Length != crew.Members.Count)
            {
                _store.CrewsById[crewId] = crew with { Members = retained, UpdatedAtUtc = erasedAtUtc };
                removed += crew.Members.Count - retained.Length;
            }
        }

        removed += RemoveDictionaryWhere(_store.CampaignSpinesById, pair => affectedCampaignIds.Contains(pair.Key));
        foreach ((string campaignId, CampaignProjection campaign) in _store.CampaignSpinesById.ToArray())
        {
            string[] retainedDossiers = campaign.DossierIds.Where(id => !affectedDossierIds.Contains(id)).ToArray();
            string[] retainedCrews = campaign.CrewIds.Where(id => !affectedCrewIds.Contains(id)).ToArray();
            if (retainedDossiers.Length != campaign.DossierIds.Count || retainedCrews.Length != campaign.CrewIds.Count)
            {
                _store.CampaignSpinesById[campaignId] = campaign with
                {
                    DossierIds = retainedDossiers,
                    CrewIds = retainedCrews,
                    UpdatedAtUtc = erasedAtUtc
                };
                removed += (campaign.DossierIds.Count - retainedDossiers.Length)
                           + (campaign.CrewIds.Count - retainedCrews.Length);
            }
        }
        removed += RemoveDictionaryWhere(_store.RunsById, pair => affectedRunIds.Contains(pair.Key));

        removed += _store.RosterTransfers.RemoveAll(item =>
            IdEquals(item.PreviousOwnerUserId, userId)
            || IdEquals(item.CurrentOwnerUserId, userId)
            || IdEquals(item.InitiatedByUserId, userId)
            || affectedDossierIds.Contains(item.DossierId)
            || ownedGroupIds.Contains(item.SourceGroupId)
            || ownedGroupIds.Contains(item.TargetGroupId)
            || affectedCampaignIds.Contains(item.SourceCampaignId)
            || affectedCampaignIds.Contains(item.TargetCampaignId));
        removed += _store.DossierMovements.RemoveAll(item =>
            IdEquals(item.PreviousOwnerUserId, userId)
            || IdEquals(item.CurrentOwnerUserId, userId)
            || IdEquals(item.InitiatedByUserId, userId)
            || affectedDossierIds.Contains(item.DossierId)
            || ownedGroupIds.Contains(item.SourceGroupId)
            || ownedGroupIds.Contains(item.TargetGroupId)
            || affectedCampaignIds.Contains(item.SourceCampaignId)
            || affectedCampaignIds.Contains(item.TargetCampaignId));
        removed += _store.PrepLaunches.RemoveAll(item => IdEquals(item.InitiatedByUserId, userId)
                                                       || affectedCampaignIds.Contains(item.CampaignId));
        removed += _store.TravelPrefetchReceipts.RemoveAll(item => IdEquals(item.InitiatedByUserId, userId)
                                                                  || affectedCampaignIds.Contains(item.CampaignId));
        removed += _store.AftermathPackages.RemoveAll(item => IdEquals(item.InitiatedByUserId, userId)
                                                          || affectedCampaignIds.Contains(item.CampaignId));
        removed += _store.CampaignAdoptions.RemoveAll(item => IdEquals(item.UpdatedByUserId, userId)
                                                             || affectedCampaignIds.Contains(item.CampaignId));
        removed += _store.RunnerGoals.RemoveAll(item => IdEquals(item.UpdatedByUserId, userId)
                                                     || affectedDossierIds.Contains(item.DossierId)
                                                     || affectedCampaignIds.Contains(item.CampaignId));
        removed += _store.ResolutionReportApprovals.RemoveAll(item => IdEquals(item.UpdatedByUserId, userId)
                                                                        || affectedCampaignIds.Contains(item.CampaignId)
                                                                        || affectedRunIds.Contains(item.RunId));
        removed += _store.WorldTicks.RemoveAll(item => IdEquals(item.UpdatedByUserId, userId)
                                                     || affectedCampaignIds.Contains(item.CampaignId)
                                                     || affectedRunIds.Contains(item.RunId));
        removed += _store.PlayerSafeNews.RemoveAll(item => IdEquals(item.UpdatedByUserId, userId)
                                                         || affectedCampaignIds.Contains(item.CampaignId));

        removed += _store.OpenRunCloseouts.RemoveAll(item => affectedOpenRunIds.Contains(item.OpenRunId)
                                                             || IdEquals(item.ClosedByUserId, userId));
        removed += _store.OpenRunMeetingHandoffs.RemoveAll(item => affectedOpenRunIds.Contains(item.OpenRunId)
                                                                   || IdEquals(item.CreatedByUserId, userId)
                                                                   || item.AcceptedUserIds.Any(id => IdEquals(id, userId)));
        removed += _store.OpenRunSchedules.RemoveAll(item => affectedOpenRunIds.Contains(item.OpenRunId)
                                                             || IdEquals(item.ScheduledByUserId, userId));
        removed += _store.OpenRunRoster.RemoveAll(item => affectedOpenRunIds.Contains(item.OpenRunId)
                                                          || IdEquals(item.UserId, userId)
                                                          || (item.DossierId is not null && affectedDossierIds.Contains(item.DossierId)));
        removed += _store.OpenRunJoinRequests.RemoveAll(item => affectedOpenRunIds.Contains(item.OpenRunId)
                                                                || IdEquals(item.ApplicantUserId, userId)
                                                                || (item.DossierId is not null && affectedDossierIds.Contains(item.DossierId)));
        removed += _store.OpenRuns.RemoveAll(item => affectedOpenRunIds.Contains(item.OpenRunId));

        HashSet<string> collaborationInviteIds = _store.CampaignCollaborationInvitesById.Values
            .Where(invite => affectedCampaignIds.Contains(invite.CampaignId)
                             || IdEquals(invite.CreatedByUserId, userId)
                             || IdEquals(invite.RevokedByUserId, userId))
            .Select(static invite => invite.InviteId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        removed += RemoveDictionaryWhere(
            _store.CampaignInviteIdByCodeLookupSha256,
            pair => collaborationInviteIds.Contains(pair.Value));
        removed += RemoveDictionaryWhere(
            _store.CampaignCollaborationInvitesById,
            pair => collaborationInviteIds.Contains(pair.Key));
        removed += _store.CampaignCharacterBindings.RemoveAll(item =>
            affectedCampaignIds.Contains(item.CampaignId)
            || affectedDossierIds.Contains(item.DossierId)
            || IdEquals(item.AuthenticatedOwnerUserId, userId)
            || IdEquals(item.GrantedByUserId, userId));
        removed += _store.CampaignSharedSheetAudit.RemoveAll(item =>
            affectedCampaignIds.Contains(item.CampaignId)
            || affectedDossierIds.Contains(item.DossierId)
            || IdEquals(item.EditedByUserId, userId));
        removed += RemoveDictionaryWhere(
            _store.CampaignRunsitesByRunId,
            pair => affectedCampaignIds.Contains(pair.Value.CampaignId)
                    || affectedRunIds.Contains(pair.Value.RunId)
                    || IdEquals(pair.Value.UpdatedByUserId, userId));
        removed += RemoveDictionaryWhere(
            _store.CampaignCreationsByIdempotencyKey,
            pair => IdEquals(pair.Value.UserId, userId)
                    || affectedCampaignIds.Contains(pair.Value.Response.CampaignId));
        removed += RemoveDictionaryWhere(
            _store.CampaignInviteCreationsByIdempotencyKey,
            pair => IdEquals(pair.Value.UserId, userId)
                    || affectedCampaignIds.Contains(pair.Value.CampaignId));
        removed += RemoveDictionaryWhere(
            _store.CampaignRunsiteDraftCommandsByIdempotencyKey,
            pair => IdEquals(pair.Value.UserId, userId)
                    || affectedCampaignIds.Contains(pair.Value.Response.CampaignId));
        removed += RemoveDictionaryWhere(
            _store.CampaignRunsitePublishCommandsByIdempotencyKey,
            pair => IdEquals(pair.Value.UserId, userId)
                    || affectedCampaignIds.Contains(pair.Value.Response.CampaignId));
        removed += RemoveDictionaryWhere(
            _store.CampaignRedemptionsByIdempotencyKey,
            pair => IdEquals(pair.Value.UserId, userId)
                    || affectedCampaignIds.Contains(pair.Value.Response.CampaignId)
                    || affectedDossierIds.Contains(pair.Value.Response.DossierId));
        removed += RemoveDictionaryWhere(
            _store.CampaignSheetEditsByIdempotencyKey,
            pair => IdEquals(pair.Value.UserId, userId)
                    || affectedCampaignIds.Contains(pair.Value.Response.CampaignId)
                    || affectedDossierIds.Contains(pair.Value.Response.DossierId));
        removed += _store.CampaignGmAuthorityAudit.RemoveAll(item =>
            affectedCampaignIds.Contains(item.CampaignId)
            || affectedDossierIds.Contains(item.DossierId)
            || IdEquals(item.ChangedByOwnerUserId, userId));
        removed += RemoveDictionaryWhere(
            _store.CampaignGmAuthorityCommandsByIdempotencyKey,
            pair => IdEquals(pair.Value.UserId, userId)
                    || affectedCampaignIds.Contains(pair.Value.Response.CampaignId)
                    || affectedDossierIds.Contains(pair.Value.Response.DossierId));
        removed += RemoveDictionaryWhere(
            _store.CampaignTeardownsByIdempotencyKey,
            pair => IdEquals(pair.Value.UserId, userId)
                    || affectedCampaignIds.Contains(pair.Value.Response.CampaignId));

        removed += EraseBlackLedgerAccountState(userId);

        removed += RemoveDictionaryWhere(
            _store.UserIdBySubjectId,
            pair => IdEquals(pair.Value, userId) || IdEquals(pair.Key, subjectId));
        if (_store.UsersById.Remove(userId))
        {
            removed++;
        }

        return new CommunityAccountErasureResult(
            Erased: removed > 0,
            UserId: userId,
            RecordsRemoved: removed,
            OwnedGroupsRemoved: ownedGroupIds.Count,
            SharedMembershipsRemoved: sharedMembershipsRemoved,
            PlayAuthorizationRecordsRemoved: playRemoved,
            ErasedAtUtc: erasedAtUtc);
    }

    private int EraseBlackLedgerAccountState(string userId)
    {
        BlackLedgerFactionOnboardingState? state = _store.BlackLedgerFactionOnboardingState;
        if (state is null)
        {
            return 0;
        }

        int removed = RemoveDictionaryWhere(
            state.Allegiances,
            pair => IdEquals(pair.Key, userId) || IdEquals(pair.Value.AccountId, userId));
        HashSet<string> foundedFactionIds = state.Charters.Values
            .Where(charter => IdEquals(charter.FounderAccountId, userId))
            .Select(static charter => charter.FactionId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        removed += RemoveDictionaryWhere(state.Charters, pair => foundedFactionIds.Contains(pair.Key));
        removed += RemoveDictionaryWhere(state.CreatedFactions, pair => foundedFactionIds.Contains(pair.Key));
        removed += RemoveDictionaryWhere(state.ActionReceiptsByFactionId, pair => foundedFactionIds.Contains(pair.Key));
        removed += RemoveDictionaryWhere(state.FactionOperationalStates, pair => foundedFactionIds.Contains(pair.Key));
        removed += RemoveDictionaryWhere(state.PrivateLoreOverlays, pair => foundedFactionIds.Contains(pair.Value.FactionId));
        removed += state.ModerationReceipts.RemoveAll(receipt => IdEquals(receipt.ReviewerAccountId, userId)
                                                                || foundedFactionIds.Contains(receipt.FactionId));
        return removed;
    }

    private string? ResolveUserId(string subjectId, string? knownUserId)
    {
        if (knownUserId is not null && _store.UsersById.ContainsKey(knownUserId))
        {
            return knownUserId;
        }

        return _store.UserIdBySubjectId.TryGetValue(subjectId, out string? mappedUserId)
            ? mappedUserId
            : knownUserId;
    }

    private static bool IdEquals(string? left, string? right)
        => !string.IsNullOrWhiteSpace(left)
           && !string.IsNullOrWhiteSpace(right)
           && string.Equals(left.Trim(), right.Trim(), StringComparison.OrdinalIgnoreCase);

    private static int RemoveDictionaryWhere<TKey, TValue>(
        Dictionary<TKey, TValue> dictionary,
        Func<KeyValuePair<TKey, TValue>, bool> predicate)
        where TKey : notnull
    {
        TKey[] keys = dictionary.Where(predicate).Select(static pair => pair.Key).ToArray();
        foreach (TKey key in keys)
        {
            dictionary.Remove(key);
        }

        return keys.Length;
    }
}
