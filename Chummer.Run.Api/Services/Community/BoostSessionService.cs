using System.Text.Json.Nodes;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Ledger;
using Chummer.Run.Contracts.Leaderboards;

namespace Chummer.Run.Api.Services.Community;

public sealed class BoostSessionService
{
    private readonly CommunityStore _store;
    private readonly AccountService _accounts;
    private readonly GroupService _groups;
    private readonly FleetBridgeService _fleetBridge;
    private readonly RewardService _rewards;

    public BoostSessionService(
        CommunityStore store,
        AccountService accounts,
        GroupService groups,
        FleetBridgeService fleetBridge,
        RewardService rewards)
    {
        _store = store;
        _accounts = accounts;
        _groups = groups;
        _fleetBridge = fleetBridge;
        _rewards = rewards;
    }

    public SponsorSessionStatusDto Create(CreateSponsorSessionRequest request)
    {
        var subjectId = AccountService.NormalizeRequired(request.SubjectId ?? string.Empty, nameof(request.SubjectId));
        var user = _accounts.EnsureUser(subjectId, request.SubjectLabel ?? subjectId);
        var group = ResolveGroupForSession(user, request);
        var boostCodeId = default(string);
        var campaignId = AccountService.NormalizeOptional(request.CampaignId);
        if (!string.IsNullOrWhiteSpace(request.BoostCode))
        {
            var redeemed = _groups.RedeemBoostCode(new RedeemBoostCodeRequest(subjectId, request.BoostCode!));
            boostCodeId = redeemed.BoostCodeId;
            campaignId ??= redeemed.CampaignId;
        }
        if (string.IsNullOrWhiteSpace(campaignId))
        {
            campaignId = _groups.GetOrCreateCampaign(group.GroupId, request.ProjectId, $"{group.Name} sponsor campaign").CampaignId;
        }

        var state = new SponsorSessionState
        {
            SponsorSessionId = AccountService.NewId("sps"),
            UserId = user.UserId,
            GroupId = group.GroupId,
            ProjectId = AccountService.NormalizeRequired(request.ProjectId, nameof(request.ProjectId)),
            RequestedLaneType = AccountService.NormalizeOptional(request.RequestedLaneType) ?? "participant_burst",
            Visibility = AccountService.NormalizeOptional(request.Visibility) ?? "group",
            Status = "intent_created",
            BoostCampaignId = campaignId,
            BoostCodeId = boostCodeId,
            AuthorizationTier = SponsorStatusPolicy.NormalizeAuthorizationTier(request.AuthorizationTier),
            TierSource = SponsorStatusPolicy.NormalizeTierSource(request.TierSource ?? (string.IsNullOrWhiteSpace(request.AuthorizationTier) ? null : "user_declared")),
            CreatedAtUtc = DateTimeOffset.UtcNow,
            UpdatedAtUtc = DateTimeOffset.UtcNow,
        };
        state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), "intent_created", $"Created sponsor session for {state.ProjectId}.", DateTimeOffset.UtcNow));
        lock (_store.Gate)
        {
            _store.SponsorSessionsById[state.SponsorSessionId] = state;
            _store.PersistLocked();
        }
        return state.Snapshot();
    }

    public SponsorSessionStatusDto? Get(string sponsorSessionId)
    {
        var normalized = AccountService.NormalizeOptional(sponsorSessionId);
        if (normalized is null)
        {
            return null;
        }

        lock (_store.Gate)
        {
            return _store.SponsorSessionsById.TryGetValue(normalized, out var state) ? state.Snapshot() : null;
        }
    }

    public async Task<(SponsorSessionStatusDto Session, JsonObject? Fleet)> RefreshAsync(string sponsorSessionId, CancellationToken cancellationToken)
    {
        var state = Require(sponsorSessionId);
        var fleetLaneId = default(string);
        lock (_store.Gate)
        {
            fleetLaneId = AccountService.NormalizeOptional(state.FleetLaneId);
        }

        JsonObject? fleet = null;
        if (!string.IsNullOrWhiteSpace(fleetLaneId))
        {
            fleet = await _fleetBridge.GetParticipantLaneAsync(fleetLaneId!, cancellationToken);
            lock (_store.Gate)
            {
                ApplyFleetSnapshotLocked(state, fleet);
                SyncRecognitionStateLocked(state, "fleet refresh");
                _store.PersistLocked();
                return (state.Snapshot(), fleet);
            }
        }

        return (state.Snapshot(), null);
    }

    public IReadOnlyList<ContributionReceiptDto> ListReceipts(string sponsorSessionId)
    {
        var normalized = AccountService.NormalizeRequired(sponsorSessionId, nameof(sponsorSessionId));
        lock (_store.Gate)
        {
            return _store.Receipts
                .Where(receipt => string.Equals(receipt.SponsorSessionId, normalized, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(receipt => receipt.EndedAtUtc ?? receipt.LandedAtUtc ?? receipt.StartedAtUtc ?? DateTimeOffset.MinValue)
                .ToArray();
        }
    }

    public IReadOnlyList<BadgeDto> ListBadgesForSessionUser(string sponsorSessionId)
    {
        var state = Require(sponsorSessionId);
        lock (_store.Gate)
        {
            return _store.Badges
                .Where(badge => string.Equals(badge.UserId, state.UserId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(badge => badge.AwardedAtUtc)
                .ToArray();
        }
    }

    public SponsorSessionStatusDto RecordConsent(string sponsorSessionId)
    {
        var state = Require(sponsorSessionId);
        lock (_store.Gate)
        {
            state.Consented = true;
            state.Status = "consented";
            state.ConsentedAtUtc ??= DateTimeOffset.UtcNow;
            state.UpdatedAtUtc = DateTimeOffset.UtcNow;
            state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), "consent_recorded", "User consent recorded.", DateTimeOffset.UtcNow));
            _store.PersistLocked();
            return state.Snapshot();
        }
    }

    public async Task<(SponsorSessionStatusDto Session, JsonObject Fleet)> StartDeviceAuthAsync(string sponsorSessionId, CancellationToken cancellationToken)
    {
        var state = Require(sponsorSessionId);
        HubUserSubject subject;
        lock (_store.Gate)
        {
            if (!state.Consented)
            {
                throw new InvalidOperationException("consent is required before device auth can start.");
            }

            subject = ResolveSubjectForUserLocked(state.UserId);
        }

        if (string.IsNullOrWhiteSpace(state.FleetLaneId))
        {
            var created = await _fleetBridge.CreateParticipantLaneAsync(
                subject.SubjectId,
                subject.DisplayName,
                state.ProjectId,
                state.UserId,
                state.GroupId,
                state.BoostCampaignId ?? "",
                state.SponsorSessionId,
                state.Visibility,
                state.AuthorizationTier,
                state.TierSource,
                cancellationToken);
            var laneId = AccountService.NormalizeOptional(created["lane"]?["lane_id"]?.GetValue<string>());
            if (laneId is null)
            {
                throw new InvalidOperationException("Fleet lane creation did not return a lane_id.");
            }

            lock (_store.Gate)
            {
                state.FleetLaneId = laneId;
                state.Status = "fleet_lane_created";
                state.UpdatedAtUtc = DateTimeOffset.UtcNow;
                state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), "fleet_lane_created", $"Fleet lane {laneId} created.", DateTimeOffset.UtcNow));
                _store.PersistLocked();
            }
        }

        var fleet = await _fleetBridge.StartDeviceAuthAsync(state.FleetLaneId!, cancellationToken);
        var verificationUri = fleet["lane"]?["device_auth"]?["verification_uri"]?.GetValue<string>();
        var userCode = fleet["lane"]?["device_auth"]?["user_code"]?.GetValue<string>();
        lock (_store.Gate)
        {
            ApplyFleetSnapshotLocked(state, fleet);
            state.DeviceAuthVerificationUri = AccountService.NormalizeOptional(verificationUri) ?? state.DeviceAuthVerificationUri;
            state.DeviceAuthUserCode = AccountService.NormalizeOptional(userCode) ?? state.DeviceAuthUserCode;
            if (!SponsorStatusPolicy.IsCurrentSponsorSession(state.Status, state.AuthorizedAtUtc))
            {
                state.Status = "pending_auth";
            }
            state.UpdatedAtUtc = DateTimeOffset.UtcNow;
            state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), "device_auth_started", "Device auth started on Fleet.", DateTimeOffset.UtcNow));
            SyncRecognitionStateLocked(state, "device auth started");
            _store.PersistLocked();
            return (state.Snapshot(), fleet);
        }
    }

    public async Task<(SponsorSessionStatusDto Session, JsonObject Fleet)> ActivateAsync(string sponsorSessionId, CancellationToken cancellationToken)
    {
        var state = Require(sponsorSessionId);
        if (string.IsNullOrWhiteSpace(state.FleetLaneId))
        {
            throw new InvalidOperationException("no Fleet lane exists for this sponsor session.");
        }

        var fleet = await _fleetBridge.ActivateParticipantLaneAsync(state.FleetLaneId!, cancellationToken);
        lock (_store.Gate)
        {
            state.Status = "active";
            state.AuthorizedAtUtc ??= DateTimeOffset.UtcNow;
            state.ActivatedAtUtc ??= DateTimeOffset.UtcNow;
            state.UpdatedAtUtc = DateTimeOffset.UtcNow;
            state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), "lane_activated", "Participant lane activated on Fleet.", DateTimeOffset.UtcNow));
            SyncRecognitionStateLocked(state, "lane activated");
            _store.PersistLocked();
            return (state.Snapshot(), fleet);
        }
    }

    public async Task<(SponsorSessionStatusDto Session, JsonObject Fleet)> StopAsync(string sponsorSessionId, bool revoke, CancellationToken cancellationToken)
    {
        var state = Require(sponsorSessionId);
        if (string.IsNullOrWhiteSpace(state.FleetLaneId))
        {
            lock (_store.Gate)
            {
                state.Status = revoke ? "revoked" : "stopped";
                state.StoppedAtUtc ??= DateTimeOffset.UtcNow;
                state.UpdatedAtUtc = DateTimeOffset.UtcNow;
                state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), revoke ? "revoked" : "stopped", revoke ? "Sponsor session revoked before Fleet lane creation." : "Sponsor session stopped before Fleet lane creation.", DateTimeOffset.UtcNow));
                MaybeAwardChickenedOutBadgeLocked(state);
                SyncRecognitionStateLocked(state, revoke ? "session revoked" : "session stopped");
                _store.PersistLocked();
                return (state.Snapshot(), new JsonObject());
            }
        }

        var fleet = revoke
            ? await _fleetBridge.DeleteParticipantLaneAsync(state.FleetLaneId!, cancellationToken)
            : await _fleetBridge.StopParticipantLaneAsync(state.FleetLaneId!, cancellationToken);
        lock (_store.Gate)
        {
            ApplyFleetSnapshotLocked(state, fleet);
            state.Status = revoke ? "revoked" : "stopped";
            state.StoppedAtUtc ??= DateTimeOffset.UtcNow;
            state.UpdatedAtUtc = DateTimeOffset.UtcNow;
            state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), revoke ? "revoked" : "stopped", revoke ? "Participant lane revoked." : "Participant lane stopped.", DateTimeOffset.UtcNow));
            MaybeAwardChickenedOutBadgeLocked(state);
            SyncRecognitionStateLocked(state, revoke ? "session revoked" : "session stopped");
            _store.PersistLocked();
            return (state.Snapshot(), fleet);
        }
    }

    private GroupDto ResolveGroupForSession(HubUserDto user, CreateSponsorSessionRequest request)
    {
        var explicitGroupId = AccountService.NormalizeOptional(request.GroupId);
        if (!string.IsNullOrWhiteSpace(explicitGroupId))
        {
            return _groups.GetGroup(explicitGroupId!) ?? throw new KeyNotFoundException($"Unknown group: {explicitGroupId}");
        }

        if (!string.IsNullOrWhiteSpace(request.BoostCode))
        {
            var existing = _groups.GetBoostCode(request.BoostCode)
                ?? throw new KeyNotFoundException($"Unknown boost code: {request.BoostCode}");
            return _groups.GetGroup(existing.GroupId) ?? throw new KeyNotFoundException($"Unknown group: {existing.GroupId}");
        }

        return _groups.EnsurePersonalBoosterGroup(user);
    }

    private HubUserSubject ResolveSubjectForUserLocked(string userId)
    {
        if (!_store.UsersById.TryGetValue(userId, out var user))
        {
            throw new KeyNotFoundException($"Unknown user: {userId}");
        }

        return new HubUserSubject(user.SubjectId, user.DisplayName);
    }

    private SponsorSessionState Require(string sponsorSessionId)
    {
        var normalized = AccountService.NormalizeRequired(sponsorSessionId, nameof(sponsorSessionId));
        lock (_store.Gate)
        {
            if (_store.SponsorSessionsById.TryGetValue(normalized, out var state))
            {
                return state;
            }
        }

        throw new KeyNotFoundException($"Unknown sponsor session: {normalized}");
    }

    private static string MapFleetLaneStatusToSessionStatus(string fleetStatus, bool authReady)
        => fleetStatus switch
        {
            "active" => "active",
            "stopped" => "stopped",
            "revoked" => "revoked",
            "paused" => "paused",
            "pending_auth" when authReady => "lane_pending",
            "pending_auth" => "pending_auth",
            _ => string.IsNullOrWhiteSpace(fleetStatus) ? "intent_created" : fleetStatus,
        };

    private void ApplyFleetSnapshotLocked(SponsorSessionState state, JsonObject fleet)
    {
        var lane = fleet["lane"] as JsonObject;
        if (lane is null)
        {
            return;
        }

        state.FleetLaneId = AccountService.NormalizeOptional(lane["lane_id"]?.GetValue<string>()) ?? state.FleetLaneId;
        var deviceAuth = lane["device_auth"] as JsonObject;
        var verificationUri = AccountService.NormalizeOptional(deviceAuth?["verification_uri"]?.GetValue<string>())
            ?? AccountService.NormalizeOptional((lane["telemetry"] as JsonObject)?["verification_uri"]?.GetValue<string>());
        var userCode = AccountService.NormalizeOptional(deviceAuth?["user_code"]?.GetValue<string>())
            ?? AccountService.NormalizeOptional((lane["telemetry"] as JsonObject)?["user_code"]?.GetValue<string>());
        var authReady = (deviceAuth?["auth_ready"]?.GetValue<bool?>()).GetValueOrDefault()
            || ((lane["telemetry"] as JsonObject)?["auth_ready"]?.GetValue<bool?>()).GetValueOrDefault();
        state.DeviceAuthVerificationUri = verificationUri ?? state.DeviceAuthVerificationUri;
        state.DeviceAuthUserCode = userCode ?? state.DeviceAuthUserCode;
        var authorizationTier = AccountService.NormalizeOptional(lane["authorization_tier"]?.GetValue<string>())
            ?? AccountService.NormalizeOptional((lane["telemetry"] as JsonObject)?["authorization_tier"]?.GetValue<string>());
        var tierSource = AccountService.NormalizeOptional(lane["tier_source"]?.GetValue<string>())
            ?? AccountService.NormalizeOptional((lane["telemetry"] as JsonObject)?["tier_source"]?.GetValue<string>());
        if (!string.IsNullOrWhiteSpace(authorizationTier))
        {
            state.AuthorizationTier = SponsorStatusPolicy.NormalizeAuthorizationTier(authorizationTier);
        }
        if (!string.IsNullOrWhiteSpace(tierSource))
        {
            state.TierSource = SponsorStatusPolicy.NormalizeTierSource(tierSource);
        }
        var fleetStatus = AccountService.NormalizeOptional(lane["status"]?.GetValue<string>()) ?? state.Status;
        state.Status = MapFleetLaneStatusToSessionStatus(fleetStatus, authReady);
        if (authReady)
        {
            state.AuthorizedAtUtc ??= DateTimeOffset.UtcNow;
        }
        if (string.Equals(state.Status, "active", StringComparison.OrdinalIgnoreCase))
        {
            state.AuthorizedAtUtc ??= DateTimeOffset.UtcNow;
            state.ActivatedAtUtc ??= DateTimeOffset.UtcNow;
        }
        state.UpdatedAtUtc = DateTimeOffset.UtcNow;
    }

    private void MaybeAwardChickenedOutBadgeLocked(SponsorSessionState state)
    {
        if (state.ActivatedAtUtc is not null || state.AuthorizedAtUtc is not null || !state.Consented || HasCurrentAuthorizedSponsorLocked(state.UserId))
        {
            return;
        }

        if (_rewards.AwardBadgeIfMissing(
                state.UserId,
                "chickened-out",
                "Chickened Out",
                badgeScope: "user",
                badgeKind: "transient",
                sourceSponsorSessionId: state.SponsorSessionId))
        {
            state.Events.Add(new SponsorSessionEventDto(
                AccountService.NewId("evt"),
                "badge_awarded",
                "Chickened Out badge awarded after stopping before sponsor authorization.",
                DateTimeOffset.UtcNow));
        }
    }

    private void SyncRecognitionStateLocked(SponsorSessionState state, string reason)
    {
        if (state.AuthorizedAtUtc is not null || SponsorStatusPolicy.IsCurrentSponsorSession(state.Status, state.AuthorizedAtUtc))
        {
            _rewards.RevokeBadgeIfActive(state.UserId, "chickened-out", reason);
        }

        SyncUserSponsorTierBadgesLocked(state.UserId, reason);
    }

    private void SyncUserSponsorTierBadgesLocked(string userId, string reason)
    {
        var currentSessions = _store.SponsorSessionsById.Values
            .Where(session =>
                string.Equals(session.UserId, userId, StringComparison.OrdinalIgnoreCase)
                && SponsorStatusPolicy.IsCurrentSponsorSession(session.Status, session.AuthorizedAtUtc))
            .ToArray();
        var bestTier = currentSessions
            .Select(session => session.AuthorizationTier)
            .OrderByDescending(SponsorStatusPolicy.TierPriority)
            .FirstOrDefault();
        var currentBadge = SponsorStatusPolicy.ActiveTierBadge(bestTier);
        var keysToRevoke = SponsorStatusPolicy.ActiveTierBadgeKeys
            .Where(key => !string.Equals(key, currentBadge?.Key, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        _rewards.RevokeBadgesIfActive(userId, keysToRevoke, reason);
        if (currentBadge is not null)
        {
            _rewards.AwardBadgeIfMissing(
                userId,
                currentBadge.Value.Key,
                currentBadge.Value.Label,
                badgeScope: "user",
                badgeKind: "transient");
        }
        else
        {
            _rewards.RevokeBadgesIfActive(userId, SponsorStatusPolicy.ActiveTierBadgeKeys, reason);
        }
    }

    private bool HasCurrentAuthorizedSponsorLocked(string userId)
        => _store.SponsorSessionsById.Values.Any(session =>
            string.Equals(session.UserId, userId, StringComparison.OrdinalIgnoreCase)
            && SponsorStatusPolicy.IsCurrentSponsorSession(session.Status, session.AuthorizedAtUtc));

    private sealed record HubUserSubject(string SubjectId, string DisplayName);
}
