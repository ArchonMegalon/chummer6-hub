using System.Text.Json.Nodes;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed class BoostSessionService
{
    private readonly CommunityStore _store;
    private readonly AccountService _accounts;
    private readonly GroupService _groups;
    private readonly FleetBridgeService _fleetBridge;

    public BoostSessionService(
        CommunityStore store,
        AccountService accounts,
        GroupService groups,
        FleetBridgeService fleetBridge)
    {
        _store = store;
        _accounts = accounts;
        _groups = groups;
        _fleetBridge = fleetBridge;
    }

    public SponsorSessionStatusDto Create(CreateSponsorSessionRequest request)
    {
        var user = _accounts.EnsureUser(request.SubjectId, request.SubjectLabel ?? request.SubjectId);
        var group = ResolveGroupForSession(user, request);
        var boostCodeId = default(string);
        var campaignId = AccountService.NormalizeOptional(request.CampaignId);
        if (!string.IsNullOrWhiteSpace(request.BoostCode))
        {
            var redeemed = _groups.RedeemBoostCode(new RedeemBoostCodeRequest(request.SubjectId, request.BoostCode!));
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
                cancellationToken);
            var laneId = created["lane"]?["lane_id"]?.GetValue<string>() ?? "";
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
            state.DeviceAuthVerificationUri = AccountService.NormalizeOptional(verificationUri);
            state.DeviceAuthUserCode = AccountService.NormalizeOptional(userCode);
            state.Status = "pending_auth";
            state.UpdatedAtUtc = DateTimeOffset.UtcNow;
            state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), "device_auth_started", "Device auth started on Fleet.", DateTimeOffset.UtcNow));
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
            state.ActivatedAtUtc ??= DateTimeOffset.UtcNow;
            state.UpdatedAtUtc = DateTimeOffset.UtcNow;
            state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), "lane_activated", "Participant lane activated on Fleet.", DateTimeOffset.UtcNow));
            _store.PersistLocked();
            return (state.Snapshot(), fleet);
        }
    }

    public async Task<(SponsorSessionStatusDto Session, JsonObject Fleet)> StopAsync(string sponsorSessionId, bool revoke, CancellationToken cancellationToken)
    {
        var state = Require(sponsorSessionId);
        if (string.IsNullOrWhiteSpace(state.FleetLaneId))
        {
            throw new InvalidOperationException("no Fleet lane exists for this sponsor session.");
        }

        var fleet = revoke
            ? await _fleetBridge.DeleteParticipantLaneAsync(state.FleetLaneId!, cancellationToken)
            : await _fleetBridge.StopParticipantLaneAsync(state.FleetLaneId!, cancellationToken);
        lock (_store.Gate)
        {
            state.Status = revoke ? "revoked" : "stopped";
            state.StoppedAtUtc ??= DateTimeOffset.UtcNow;
            state.UpdatedAtUtc = DateTimeOffset.UtcNow;
            state.Events.Add(new SponsorSessionEventDto(AccountService.NewId("evt"), revoke ? "revoked" : "stopped", revoke ? "Participant lane revoked." : "Participant lane stopped.", DateTimeOffset.UtcNow));
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

    private sealed record HubUserSubject(string SubjectId, string DisplayName);
}
