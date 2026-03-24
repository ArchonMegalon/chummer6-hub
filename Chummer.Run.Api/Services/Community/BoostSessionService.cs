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
        var boostCodeId = default(string);
        var campaignId = AccountService.NormalizeOptional(request.CampaignId);
        BoostCodeDto? redeemedBoostCode = null;
        if (!string.IsNullOrWhiteSpace(request.BoostCode))
        {
            redeemedBoostCode = _groups.RedeemBoostCode(new RedeemBoostCodeRequest(subjectId, request.BoostCode!));
            boostCodeId = redeemedBoostCode.BoostCodeId;
            campaignId ??= redeemedBoostCode.CampaignId;
        }
        var group = ResolveGroupForSession(user, request, redeemedBoostCode);
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
            RequestedLaneRole = SponsorLaneRolePolicy.Normalize(request.RequestedLaneRole),
            Visibility = AccountService.NormalizeOptional(request.Visibility) ?? "group",
            Status = "intent_created",
            BoostCampaignId = campaignId,
            BoostCodeId = boostCodeId,
            AuthorizationTier = SponsorStatusPolicy.NormalizeAuthorizationTier(request.AuthorizationTier),
            TierSource = SponsorStatusPolicy.NormalizeTierSource(request.TierSource ?? (string.IsNullOrWhiteSpace(request.AuthorizationTier) ? null : "user_declared")),
            CreatedAtUtc = DateTimeOffset.UtcNow,
            UpdatedAtUtc = DateTimeOffset.UtcNow,
        };
        if (!SponsorLaneRolePolicy.IsEligible(state.RequestedLaneRole, state.AuthorizationTier))
        {
            throw new InvalidOperationException($"{SponsorLaneRolePolicy.Label(state.RequestedLaneRole)} currently requires at least {SponsorLaneRolePolicy.MinimumTier(state.RequestedLaneRole)} tier authorization.");
        }
        state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), "intent_created", $"Created sponsor session for {state.ProjectId}.", DateTimeOffset.UtcNow));
        lock (_store.Gate)
        {
            _store.SponsorSessionsById[state.SponsorSessionId] = state;
            _store.PersistLocked();
        }
        return state.Snapshot();
    }

    public async Task<(SponsorSessionStatusDto Session, JsonObject Fleet)> StartContributionAsync(
        CreateSponsorSessionRequest request,
        CancellationToken cancellationToken)
    {
        var reusable = FindReusableContributionForRequest(request);
        if (reusable is not null)
        {
            if (!reusable.Consented)
            {
                reusable = RecordConsent(reusable.SponsorSessionId);
            }

            if (!string.IsNullOrWhiteSpace(reusable.FleetLaneId))
            {
                var refreshed = await RefreshAsync(reusable.SponsorSessionId, cancellationToken);
                if (!IsTerminalContributionStatus(refreshed.Session.Status))
                {
                    return (refreshed.Session, refreshed.Fleet ?? new JsonObject());
                }
            }
            else
            {
                return await StartDeviceAuthAsync(reusable.SponsorSessionId, cancellationToken);
            }
        }

        var created = Create(request);
        RecordConsent(created.SponsorSessionId);
        return await StartDeviceAuthAsync(created.SponsorSessionId, cancellationToken);
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

    public SponsorSessionStatusDto? FindMostRelevantForUser(string subjectId)
    {
        var normalizedSubjectId = AccountService.NormalizeOptional(subjectId);
        if (normalizedSubjectId is null)
        {
            return null;
        }

        var user = _accounts.EnsureUser(normalizedSubjectId, normalizedSubjectId);
        lock (_store.Gate)
        {
            return _store.SponsorSessionsById.Values
                .Where(session => string.Equals(session.UserId, user.UserId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(SessionPriority)
                .ThenByDescending(session => session.AuthorizedAtUtc ?? session.UpdatedAtUtc)
                .ThenByDescending(session => session.CreatedAtUtc)
                .Select(static session => session.Snapshot())
                .FirstOrDefault();
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
            return await ApplyFleetRefreshAsync(state, fleet, "fleet refresh", cancellationToken);
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
            JsonObject created;
            try
            {
                created = await _fleetBridge.CreateParticipantLaneAsync(
                    subject.SubjectId,
                    subject.DisplayName,
                    state.ProjectId,
                    state.UserId,
                    state.GroupId,
                    state.BoostCampaignId ?? "",
                    state.SponsorSessionId,
                    state.Visibility,
                    state.RequestedLaneRole,
                    state.AuthorizationTier,
                    state.TierSource,
                    cancellationToken);
            }
            catch (InvalidOperationException ex) when (IsInfrastructureLaneFailure(ex))
            {
                throw new ParticipationUnavailableException("Participation is unavailable on this host right now. Try again later.", ex);
            }
            catch (InvalidOperationException ex) when (ex.Message.Contains("(409)", StringComparison.OrdinalIgnoreCase) || ex.Message.Contains("capacity reached", StringComparison.OrdinalIgnoreCase))
            {
                lock (_store.Gate)
                {
                    state.Status = "waiting_for_slot";
                    state.UpdatedAtUtc = DateTimeOffset.UtcNow;
                    state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), "waiting_for_slot", "Fleet is at sponsor-lane capacity. Your sponsor session is queued for the next available slot.", DateTimeOffset.UtcNow));
                    _store.PersistLocked();
                    return (state.Snapshot(), new JsonObject
                    {
                        ["lane"] = new JsonObject
                        {
                            ["status"] = "waiting_for_slot",
                            ["lane_role"] = state.RequestedLaneRole,
                        },
                    });
                }
            }
            var laneId = AccountService.NormalizeOptional(created["lane"]?["lane_id"]?.GetValue<string>());
            if (laneId is null)
            {
                throw new ParticipationUnavailableException("Participation is unavailable on this host right now. Try again later.");
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
            if (!SponsorStatusPolicy.IsCurrentSponsorSession(state.Status, state.AuthorizedAtUtc)
                && !string.Equals(state.Status, "lane_pending", StringComparison.OrdinalIgnoreCase))
            {
                state.Status = "pending_auth";
            }
            state.UpdatedAtUtc = DateTimeOffset.UtcNow;
            state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), "device_auth_started", "Device auth started on Fleet.", DateTimeOffset.UtcNow));
            _store.PersistLocked();
        }

        return await ApplyFleetRefreshAsync(state, fleet, "device auth started", cancellationToken);
    }

    public async Task<(SponsorSessionStatusDto Session, JsonObject Fleet)> ActivateAsync(string sponsorSessionId, CancellationToken cancellationToken)
    {
        var state = Require(sponsorSessionId);
        if (string.IsNullOrWhiteSpace(state.FleetLaneId))
        {
            throw new InvalidOperationException("no Fleet lane exists for this sponsor session.");
        }

        JsonObject fleet;
        try
        {
            fleet = await _fleetBridge.ActivateParticipantLaneAsync(state.FleetLaneId!, cancellationToken);
        }
        catch (InvalidOperationException ex) when (IsInfrastructureLaneFailure(ex))
        {
            throw new ParticipationUnavailableException("Participation is unavailable on this host right now. Try again later.", ex);
        }
        catch (InvalidOperationException ex) when (ex.Message.Contains("(409)", StringComparison.OrdinalIgnoreCase) || ex.Message.Contains("capacity reached", StringComparison.OrdinalIgnoreCase))
        {
            lock (_store.Gate)
            {
                state.Status = "waiting_for_slot";
                state.UpdatedAtUtc = DateTimeOffset.UtcNow;
                state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), "waiting_for_slot", "Fleet could not activate the lane yet because all sponsor slots are busy.", DateTimeOffset.UtcNow));
                _store.PersistLocked();
                return (state.Snapshot(), new JsonObject
                {
                    ["lane"] = new JsonObject
                    {
                        ["lane_id"] = state.FleetLaneId,
                        ["status"] = "waiting_for_slot",
                        ["lane_role"] = state.RequestedLaneRole,
                    },
                });
            }
        }
        lock (_store.Gate)
        {
            state.Status = "active";
            state.AuthorizedAtUtc ??= DateTimeOffset.UtcNow;
            state.ActivatedAtUtc ??= DateTimeOffset.UtcNow;
            ClearDeviceAuthChallengeLocked(state);
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
                ClearDeviceAuthChallengeLocked(state);
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
            ClearDeviceAuthChallengeLocked(state);
            state.StoppedAtUtc ??= DateTimeOffset.UtcNow;
            state.UpdatedAtUtc = DateTimeOffset.UtcNow;
            state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), revoke ? "revoked" : "stopped", revoke ? "Participant lane revoked." : "Participant lane stopped.", DateTimeOffset.UtcNow));
            MaybeAwardChickenedOutBadgeLocked(state);
            SyncRecognitionStateLocked(state, revoke ? "session revoked" : "session stopped");
            _store.PersistLocked();
            return (state.Snapshot(), fleet);
        }
    }

    private GroupDto ResolveGroupForSession(HubUserDto user, CreateSponsorSessionRequest request, BoostCodeDto? redeemedBoostCode)
    {
        var explicitGroupId = AccountService.NormalizeOptional(request.GroupId);
        if (!string.IsNullOrWhiteSpace(explicitGroupId))
        {
            if (redeemedBoostCode is not null
                && !string.Equals(redeemedBoostCode.GroupId, explicitGroupId, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("boost code group does not match the selected group.");
            }

            return _groups.RequireMemberGroup(explicitGroupId!, user.UserId);
        }

        if (redeemedBoostCode is not null)
        {
            return _groups.RequireMemberGroup(redeemedBoostCode.GroupId, user.UserId);
        }

        return _groups.EnsurePersonalBoosterGroup(user);
    }

    private SponsorSessionStatusDto? FindReusableContributionForRequest(CreateSponsorSessionRequest request)
    {
        var subjectId = AccountService.NormalizeRequired(request.SubjectId ?? string.Empty, nameof(request.SubjectId));
        var projectId = AccountService.NormalizeRequired(request.ProjectId, nameof(request.ProjectId));
        var laneRole = SponsorLaneRolePolicy.Normalize(request.RequestedLaneRole);
        var user = _accounts.EnsureUser(subjectId, subjectId);
        lock (_store.Gate)
        {
            return _store.SponsorSessionsById.Values
                .Where(session => string.Equals(session.UserId, user.UserId, StringComparison.OrdinalIgnoreCase))
                .Where(session => !IsTerminalContributionStatus(session.Status))
                .Where(session => string.Equals(session.ProjectId, projectId, StringComparison.OrdinalIgnoreCase))
                .Where(session => string.Equals(session.RequestedLaneRole, laneRole, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(SessionPriority)
                .ThenByDescending(session => session.AuthorizedAtUtc ?? session.UpdatedAtUtc)
                .ThenByDescending(session => session.CreatedAtUtc)
                .Select(static session => session.Snapshot())
                .FirstOrDefault();
        }
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

    private static string MapFleetLaneStatusToSessionStatus(string fleetStatus, bool authReady, bool deviceCodeIssued)
        => fleetStatus switch
        {
            "active" => "active",
            "stopped" => "stopped",
            "revoked" => "revoked",
            "paused" => "paused",
            "pending_auth" when authReady => "lane_pending",
            "pending_auth" when !deviceCodeIssued => "warming",
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
        var credentialHandle = AccountService.NormalizeOptional(lane["credential_handle"]?.GetValue<string>())
            ?? AccountService.NormalizeOptional((lane["telemetry"] as JsonObject)?["credential_handle"]?.GetValue<string>());
        var laneRole = AccountService.NormalizeOptional(lane["lane_role"]?.GetValue<string>())
            ?? AccountService.NormalizeOptional((lane["telemetry"] as JsonObject)?["lane_role"]?.GetValue<string>());
        if (!string.IsNullOrWhiteSpace(credentialHandle))
        {
            state.FleetCredentialHandle = credentialHandle;
        }
        if (!string.IsNullOrWhiteSpace(authorizationTier))
        {
            state.AuthorizationTier = SponsorStatusPolicy.NormalizeAuthorizationTier(authorizationTier);
        }
        if (!string.IsNullOrWhiteSpace(tierSource))
        {
            state.TierSource = SponsorStatusPolicy.NormalizeTierSource(tierSource);
        }
        if (!string.IsNullOrWhiteSpace(laneRole))
        {
            state.RequestedLaneRole = SponsorLaneRolePolicy.Normalize(laneRole);
        }
        var fleetStatus = AccountService.NormalizeOptional(lane["status"]?.GetValue<string>()) ?? state.Status;
        state.Status = MapFleetLaneStatusToSessionStatus(fleetStatus, authReady, verificationUri is not null || userCode is not null);
        if (authReady)
        {
            state.AuthorizedAtUtc ??= DateTimeOffset.UtcNow;
        }
        if (string.Equals(state.Status, "active", StringComparison.OrdinalIgnoreCase))
        {
            state.AuthorizedAtUtc ??= DateTimeOffset.UtcNow;
            state.ActivatedAtUtc ??= DateTimeOffset.UtcNow;
        }
        if (authReady
            || string.Equals(state.Status, "active", StringComparison.OrdinalIgnoreCase)
            || string.Equals(state.Status, "stopped", StringComparison.OrdinalIgnoreCase)
            || string.Equals(state.Status, "revoked", StringComparison.OrdinalIgnoreCase))
        {
            ClearDeviceAuthChallengeLocked(state);
        }
        state.UpdatedAtUtc = DateTimeOffset.UtcNow;
    }

    private async Task<(SponsorSessionStatusDto Session, JsonObject Fleet)> ApplyFleetRefreshAsync(
        SponsorSessionState state,
        JsonObject fleet,
        string reason,
        CancellationToken cancellationToken)
    {
        SponsorSessionStatusDto snapshot;
        var shouldAutoActivate = false;
        lock (_store.Gate)
        {
            ApplyFleetSnapshotLocked(state, fleet);
            SyncRecognitionStateLocked(state, reason);
            shouldAutoActivate = ShouldAutoActivateLocked(state);
            _store.PersistLocked();
            snapshot = state.Snapshot();
        }

        if (!shouldAutoActivate)
        {
            return (snapshot, fleet);
        }

        return await ActivateAsync(snapshot.SponsorSessionId, cancellationToken);
    }

    private static bool ShouldAutoActivateLocked(SponsorSessionState state)
        => state.Consented
            && !string.IsNullOrWhiteSpace(state.FleetLaneId)
            && state.ActivatedAtUtc is null
            && state.StoppedAtUtc is null
            && string.Equals(state.Status, "lane_pending", StringComparison.OrdinalIgnoreCase);

    private static bool IsInfrastructureLaneFailure(InvalidOperationException ex)
        => ex.Message.Contains("Fleet bridge request failed", StringComparison.OrdinalIgnoreCase)
            || ex.Message.Contains("did not return a lane_id", StringComparison.OrdinalIgnoreCase);

    private static void ClearDeviceAuthChallengeLocked(SponsorSessionState state)
    {
        state.DeviceAuthVerificationUri = null;
        state.DeviceAuthUserCode = null;
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
        SyncContributorReadyBadgeLocked(state.UserId, reason);
    }

    private void SyncContributorReadyBadgeLocked(string userId, string reason)
    {
        var hasCurrentAuthorizedSession = _store.SponsorSessionsById.Values.Any(session =>
            string.Equals(session.UserId, userId, StringComparison.OrdinalIgnoreCase)
            && session.AuthorizedAtUtc is not null
            && session.StoppedAtUtc is null
            && !string.Equals(session.Status, "revoked", StringComparison.OrdinalIgnoreCase));

        if (hasCurrentAuthorizedSession)
        {
            _rewards.AwardBadgeIfMissing(
                userId,
                "contributor-ready",
                "Contributor Ready",
                badgeScope: "user",
                badgeKind: "transient");
            return;
        }

        _rewards.RevokeBadgeIfActive(userId, "contributor-ready", reason);
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

    private static int SessionPriority(SponsorSessionState session)
        => session.Status switch
        {
            "active" => 5,
            "lane_pending" => 4,
            "pending_auth" => 4,
            "waiting_for_slot" => 4,
            "fleet_lane_created" => 3,
            "consented" => 3,
            "intent_created" => 2,
            "stopped" => 1,
            "revoked" => 0,
            _ => 1
        };

    private static bool IsTerminalContributionStatus(string? status)
        => string.Equals(status, "stopped", StringComparison.OrdinalIgnoreCase)
            || string.Equals(status, "revoked", StringComparison.OrdinalIgnoreCase);

    private sealed record HubUserSubject(string SubjectId, string DisplayName);
}
