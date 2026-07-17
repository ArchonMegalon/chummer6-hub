using System.Security.Cryptography;
using System.Text;
using System.Diagnostics.CodeAnalysis;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public static class PlaySessionAuthorizationReasons
{
    public const string SessionCreated = "session_created";
    public const string ParticipantCreated = "participant_created";
    public const string InviteIssued = "invite_issued";
    public const string InviteRedeemed = "invite_redeemed";
    public const string ExchangeConsumed = "exchange_consumed";
    public const string GrantActive = "grant_active";
    public const string GrantRefreshed = "grant_refreshed";
    public const string GrantRevoked = "grant_revoked";
    public const string SessionVersionBumped = "session_version_bumped";
    public const string ParticipantVersionBumped = "participant_version_bumped";
    public const string ParticipantRevoked = "participant_revoked";
    public const string SessionClosed = "session_closed";
    public const string InvalidRequest = "invalid_request";
    public const string AlreadyExists = "already_exists";
    public const string NotFound = "not_found";
    public const string NotAuthorized = "not_authorized";
    public const string RoleNotAuthorized = "role_not_authorized";
    public const string BindingMismatch = "binding_mismatch";
    public const string InviteInvalid = "invite_invalid";
    public const string InviteExpired = "invite_expired";
    public const string InviteReplayed = "invite_replayed";
    public const string ExchangeInvalid = "exchange_invalid";
    public const string ExchangeExpired = "exchange_expired";
    public const string ExchangeReplayed = "exchange_replayed";
    public const string GrantInvalid = "grant_invalid";
    public const string GrantExpired = "grant_expired";
    public const string VersionDrift = "version_drift";
    public const string MembershipDrift = "membership_drift";
    public const string PersistenceFailed = "persistence_failed";
}

public sealed record PlaySessionAuthorizationResult<T>(bool Succeeded, string Reason, T? Value)
    where T : class;

public sealed record PlaySessionBindingCreated(
    PlaySessionBinding Session,
    PlaySessionParticipant GameMasterParticipant);

public sealed record IssuedPlaySessionInvite(PlaySessionInvite Invite, string Secret);

public sealed record IssuedPlaySessionExchange(PlaySessionExchange Exchange, string Secret);

public sealed record IssuedPlaySessionGrant(PlaySessionGrant Grant, string Secret);

public sealed record PlaySessionGrantContext(
    PlaySessionGrant Grant,
    PlaySessionBinding Session,
    PlaySessionParticipant Participant);

public interface IPlaySessionAuthorizationPersistence
{
    void PersistLocked(CommunityStore store);
}

public sealed class CommunityStorePlaySessionAuthorizationPersistence : IPlaySessionAuthorizationPersistence
{
    public void PersistLocked(CommunityStore store)
    {
        ArgumentNullException.ThrowIfNull(store);
        store.PersistLocked();
    }
}

/// <summary>
/// Dormant server-side Play authority. Runtime registration and transport surfaces intentionally
/// remain absent until later phases provide the browser proof and service-credential boundaries.
/// </summary>
public sealed class PlaySessionAuthorizationService
{
    public static readonly TimeSpan DefaultInviteLifetime = TimeSpan.FromMinutes(10);
    public static readonly TimeSpan MaximumInviteLifetime = TimeSpan.FromMinutes(15);
    public static readonly TimeSpan DefaultExchangeLifetime = TimeSpan.FromSeconds(90);
    public static readonly TimeSpan MaximumExchangeLifetime = TimeSpan.FromMinutes(2);
    public static readonly TimeSpan DefaultGrantLifetime = TimeSpan.FromMinutes(5);
    public static readonly TimeSpan MaximumGrantLifetime = TimeSpan.FromMinutes(10);
    public static readonly TimeSpan DefaultRefreshWindow = TimeSpan.FromHours(8);
    public static readonly TimeSpan MaximumRefreshWindow = TimeSpan.FromHours(12);

    private static readonly TimeSpan MinimumInviteLifetime = TimeSpan.FromMinutes(1);
    private static readonly TimeSpan MinimumExchangeLifetime = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan MinimumGrantLifetime = TimeSpan.FromSeconds(30);

    private readonly CommunityStore _store;
    private readonly TimeProvider _timeProvider;
    private readonly IPlaySessionAuthorizationPersistence _persistence;
    private readonly DateTimeOffset _monotonicAnchorUtc;
    private readonly long _monotonicAnchorTimestamp;

    public PlaySessionAuthorizationService(
        CommunityStore store,
        TimeProvider timeProvider,
        IPlaySessionAuthorizationPersistence? persistence = null)
    {
        _store = store ?? throw new ArgumentNullException(nameof(store));
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
        _persistence = persistence ?? new CommunityStorePlaySessionAuthorizationPersistence();
        lock (_store.Gate)
        {
            DateTimeOffset observed = _timeProvider.GetUtcNow().ToUniversalTime();
            _monotonicAnchorUtc = observed > _store.PlayAuthorizationTimeHighWaterUtc
                ? observed
                : _store.PlayAuthorizationTimeHighWaterUtc;
            _monotonicAnchorTimestamp = _timeProvider.GetTimestamp();
        }
    }

    public PlaySessionAuthorizationResult<PlaySessionBindingCreated> CreateSessionBinding(
        string sessionId,
        string campaignId,
        string runId,
        string groupId,
        string actorUserId)
    {
        if (!ValidIdentifier(sessionId)
            || !ValidIdentifier(campaignId)
            || !ValidIdentifier(runId)
            || !ValidIdentifier(groupId)
            || !ValidIdentifier(actorUserId))
        {
            return Failure<PlaySessionBindingCreated>(PlaySessionAuthorizationReasons.InvalidRequest);
        }

        return Mutate(() =>
        {
            if (_store.PlaySessionsById.ContainsKey(sessionId))
            {
                return Fail<PlaySessionBindingCreated>(PlaySessionAuthorizationReasons.AlreadyExists);
            }

            DateTimeOffset now = UtcNow();
            PlaySessionBinding session = new(
                SessionId: sessionId,
                CampaignId: campaignId,
                RunId: runId,
                GroupId: groupId,
                Status: PlaySessionStatuses.Active,
                AuthorizationVersion: 1,
                CreatedByUserId: actorUserId,
                CreatedAtUtc: now,
                UpdatedAtUtc: now);
            if (!ResolveLocked(
                    session,
                    actorUserId,
                    PlaySessionRoles.GameMaster,
                    Array.Empty<PlaySessionParticipant>()).Authorized)
            {
                return Fail<PlaySessionBindingCreated>(PlaySessionAuthorizationReasons.NotAuthorized);
            }

            PlaySessionParticipant participant = new(
                ParticipantId: NewId("participant"),
                SessionId: sessionId,
                UserId: actorUserId,
                Role: PlaySessionRoles.GameMaster,
                SourceKind: PlaySessionParticipantSources.GroupOperator,
                SourceId: groupId,
                Status: PlaySessionStatuses.Active,
                AuthorizationVersion: 1,
                AddedByUserId: actorUserId,
                CreatedAtUtc: now,
                UpdatedAtUtc: now);
            _store.PlaySessionsById.Add(session.SessionId, session);
            _store.PlayParticipantsById.Add(participant.ParticipantId, participant);
            return Success(
                PlaySessionAuthorizationReasons.SessionCreated,
                new PlaySessionBindingCreated(session, participant));
        });
    }

    public PlaySessionAuthorizationResult<PlaySessionParticipant> AddParticipant(
        string sessionId,
        string actorUserId,
        string targetUserId,
        string role)
    {
        if (!ValidIdentifier(sessionId)
            || !ValidIdentifier(actorUserId)
            || !ValidIdentifier(targetUserId)
            || !ValidRole(role))
        {
            return Failure<PlaySessionParticipant>(PlaySessionAuthorizationReasons.InvalidRequest);
        }

        return Mutate(() =>
        {
            if (!TryGetActiveSessionLocked(sessionId, out PlaySessionBinding? session))
            {
                return Fail<PlaySessionParticipant>(PlaySessionAuthorizationReasons.NotFound);
            }

            if (!AuthorizeGameMasterLocked(session, actorUserId))
            {
                return Fail<PlaySessionParticipant>(PlaySessionAuthorizationReasons.NotAuthorized);
            }

            PlaySessionParticipant? existing = FindParticipantLocked(sessionId, targetUserId, role);
            if (existing is not null
                && string.Equals(existing.Status, PlaySessionStatuses.Active, StringComparison.Ordinal))
            {
                return Fail<PlaySessionParticipant>(PlaySessionAuthorizationReasons.AlreadyExists);
            }

            PlaySessionParticipant[] authorityParticipants = _store.PlayParticipantsById.Values
                .Where(candidate => existing is null || !Same(candidate.ParticipantId, existing.ParticipantId))
                .ToArray();
            PlaySessionRoleResolution source = ResolveLocked(
                session,
                targetUserId,
                role,
                authorityParticipants);
            if (string.Equals(role, PlaySessionRoles.GameMaster, StringComparison.Ordinal)
                && !source.Authorized)
            {
                return Fail<PlaySessionParticipant>(PlaySessionAuthorizationReasons.RoleNotAuthorized);
            }

            string sourceKind = source.Authorized
                ? source.SourceKind!
                : PlaySessionParticipantSources.ExplicitParticipant;
            string sourceId = source.Authorized && ValidIdentifier(source.SourceId)
                ? source.SourceId!
                : session.SessionId;
            DateTimeOffset now = UtcNow();
            PlaySessionParticipant participant = existing is null
                ? new PlaySessionParticipant(
                    ParticipantId: NewId("participant"),
                    SessionId: sessionId,
                    UserId: targetUserId,
                    Role: role,
                    SourceKind: sourceKind,
                    SourceId: sourceId,
                    Status: PlaySessionStatuses.Active,
                    AuthorizationVersion: 1,
                    AddedByUserId: actorUserId,
                    CreatedAtUtc: now,
                    UpdatedAtUtc: now)
                : existing with
                {
                    SourceKind = sourceKind,
                    SourceId = sourceId,
                    Status = PlaySessionStatuses.Active,
                    AuthorizationVersion = checked(existing.AuthorizationVersion + 1),
                    AddedByUserId = actorUserId,
                    UpdatedAtUtc = now,
                    RevokedAtUtc = null
                };
            _store.PlayParticipantsById[participant.ParticipantId] = participant;
            return Success(PlaySessionAuthorizationReasons.ParticipantCreated, participant);
        });
    }

    public PlaySessionAuthorizationResult<IssuedPlaySessionInvite> IssueInvite(
        string sessionId,
        string actorUserId,
        string targetUserId,
        string role,
        TimeSpan? lifetime = null)
    {
        if (!ValidIdentifier(sessionId)
            || !ValidIdentifier(actorUserId)
            || !ValidIdentifier(targetUserId)
            || !ValidRole(role)
            || !TryLifetime(
                lifetime,
                DefaultInviteLifetime,
                MinimumInviteLifetime,
                MaximumInviteLifetime,
                out TimeSpan ttl))
        {
            return Failure<IssuedPlaySessionInvite>(PlaySessionAuthorizationReasons.InvalidRequest);
        }

        return Mutate(() =>
        {
            if (!TryGetActiveSessionLocked(sessionId, out PlaySessionBinding? session))
            {
                return Fail<IssuedPlaySessionInvite>(PlaySessionAuthorizationReasons.NotFound);
            }

            if (!AuthorizeGameMasterLocked(session, actorUserId))
            {
                return Fail<IssuedPlaySessionInvite>(PlaySessionAuthorizationReasons.NotAuthorized);
            }

            PlaySessionParticipant? participant = FindActiveParticipantLocked(sessionId, targetUserId, role);
            if (participant is null || !ResolveLocked(session, targetUserId, role).Authorized)
            {
                return Fail<IssuedPlaySessionInvite>(PlaySessionAuthorizationReasons.RoleNotAuthorized);
            }

            DateTimeOffset now = UtcNow();
            SecretMaterial secret = GenerateUniqueSecretLocked();
            PlaySessionInvite invite = new(
                InviteId: NewId("invite"),
                SessionId: sessionId,
                RequestedRole: role,
                TargetUserId: targetUserId,
                SecretHashSha256: secret.Hash,
                Status: PlaySessionStatuses.Active,
                SessionAuthorizationVersion: session.AuthorizationVersion,
                CreatedByUserId: actorUserId,
                CreatedAtUtc: now,
                UpdatedAtUtc: now,
                ExpiresAtUtc: now.Add(ttl),
                ParticipantId: participant.ParticipantId,
                ParticipantAuthorizationVersion: participant.AuthorizationVersion);
            _store.PlayInvitesById.Add(invite.InviteId, invite);
            return Success(
                PlaySessionAuthorizationReasons.InviteIssued,
                new IssuedPlaySessionInvite(invite, secret.Raw));
        });
    }

    public PlaySessionAuthorizationResult<IssuedPlaySessionExchange> RedeemInvite(
        string inviteId,
        string inviteSecret,
        string sessionId,
        string targetUserId,
        string role,
        string deviceThumbprint,
        TimeSpan? exchangeLifetime = null)
    {
        if (!ValidIdentifier(inviteId)
            || !ValidSecret(inviteSecret)
            || !ValidIdentifier(sessionId)
            || !ValidIdentifier(targetUserId)
            || !ValidRole(role)
            || !ValidSha256(deviceThumbprint)
            || !TryLifetime(
                exchangeLifetime,
                DefaultExchangeLifetime,
                MinimumExchangeLifetime,
                MaximumExchangeLifetime,
                out TimeSpan ttl))
        {
            return Failure<IssuedPlaySessionExchange>(PlaySessionAuthorizationReasons.InvalidRequest);
        }

        return Mutate(() =>
        {
            _store.PlayInvitesById.TryGetValue(inviteId, out PlaySessionInvite? invite);
            if (!FixedTimeSecretMatches(invite?.SecretHashSha256, inviteSecret))
            {
                return Fail<IssuedPlaySessionExchange>(PlaySessionAuthorizationReasons.InviteInvalid);
            }

            DateTimeOffset now = UtcNow();
            if (invite is null)
            {
                return Fail<IssuedPlaySessionExchange>(PlaySessionAuthorizationReasons.InviteInvalid);
            }

            if (string.Equals(invite.Status, PlaySessionStatuses.Consumed, StringComparison.Ordinal))
            {
                return Fail<IssuedPlaySessionExchange>(PlaySessionAuthorizationReasons.InviteReplayed);
            }

            if (string.Equals(invite.Status, PlaySessionStatuses.Expired, StringComparison.Ordinal)
                || now >= invite.ExpiresAtUtc)
            {
                if (!string.Equals(invite.Status, PlaySessionStatuses.Expired, StringComparison.Ordinal))
                {
                    _store.PlayInvitesById[invite.InviteId] = invite with
                    {
                        Status = PlaySessionStatuses.Expired,
                        UpdatedAtUtc = now
                    };
                    return Fail<IssuedPlaySessionExchange>(
                        PlaySessionAuthorizationReasons.InviteExpired,
                        persist: true);
                }

                return Fail<IssuedPlaySessionExchange>(PlaySessionAuthorizationReasons.InviteExpired);
            }

            if (!string.Equals(invite.Status, PlaySessionStatuses.Active, StringComparison.Ordinal))
            {
                return Fail<IssuedPlaySessionExchange>(PlaySessionAuthorizationReasons.InviteInvalid);
            }

            if (!Same(invite.SessionId, sessionId)
                || !Same(invite.TargetUserId, targetUserId)
                || !string.Equals(invite.RequestedRole, role, StringComparison.Ordinal))
            {
                return Fail<IssuedPlaySessionExchange>(PlaySessionAuthorizationReasons.BindingMismatch);
            }

            if (!TryGetActiveSessionLocked(sessionId, out PlaySessionBinding? session))
            {
                return RevokeInvite<IssuedPlaySessionExchange>(
                    invite,
                    now,
                    PlaySessionAuthorizationReasons.MembershipDrift);
            }

            if (session.AuthorizationVersion != invite.SessionAuthorizationVersion)
            {
                return RevokeInvite<IssuedPlaySessionExchange>(
                    invite,
                    now,
                    PlaySessionAuthorizationReasons.VersionDrift);
            }

            if (!ValidIdentifier(invite.ParticipantId)
                || invite.ParticipantAuthorizationVersion < 1)
            {
                return RevokeInvite<IssuedPlaySessionExchange>(
                    invite,
                    now,
                    PlaySessionAuthorizationReasons.BindingMismatch);
            }

            if (!_store.PlayParticipantsById.TryGetValue(
                    invite.ParticipantId!,
                    out PlaySessionParticipant? participant)
                || !string.Equals(participant.Status, PlaySessionStatuses.Active, StringComparison.Ordinal)
                || !Same(participant.SessionId, sessionId)
                || !Same(participant.UserId, targetUserId)
                || !string.Equals(participant.Role, role, StringComparison.Ordinal))
            {
                return RevokeInvite<IssuedPlaySessionExchange>(
                    invite,
                    now,
                    PlaySessionAuthorizationReasons.MembershipDrift);
            }

            if (invite.ParticipantAuthorizationVersion != participant.AuthorizationVersion)
            {
                return RevokeInvite<IssuedPlaySessionExchange>(
                    invite,
                    now,
                    PlaySessionAuthorizationReasons.VersionDrift);
            }

            if (!ResolveLocked(session, targetUserId, role).Authorized)
            {
                return RevokeInvite<IssuedPlaySessionExchange>(
                    invite,
                    now,
                    PlaySessionAuthorizationReasons.MembershipDrift);
            }

            SecretMaterial secret = GenerateUniqueSecretLocked();
            PlaySessionExchange exchange = new(
                ExchangeId: NewId("exchange"),
                InviteId: invite.InviteId,
                GrantId: null,
                SecretHashSha256: secret.Hash,
                Status: PlaySessionStatuses.Pending,
                SessionAuthorizationVersion: session.AuthorizationVersion,
                CreatedAtUtc: now,
                UpdatedAtUtc: now,
                ExpiresAtUtc: now.Add(ttl),
                SessionId: session.SessionId,
                ParticipantId: participant.ParticipantId,
                UserId: participant.UserId,
                Role: participant.Role,
                DeviceThumbprint: deviceThumbprint,
                ParticipantAuthorizationVersion: participant.AuthorizationVersion);
            _store.PlayInvitesById[invite.InviteId] = invite with
            {
                Status = PlaySessionStatuses.Consumed,
                ConsumedByUserId = targetUserId,
                ConsumedAtUtc = now,
                UpdatedAtUtc = now
            };
            _store.PlayExchangesById.Add(exchange.ExchangeId, exchange);
            return Success(
                PlaySessionAuthorizationReasons.InviteRedeemed,
                new IssuedPlaySessionExchange(exchange, secret.Raw));
        });
    }

    public PlaySessionAuthorizationResult<IssuedPlaySessionGrant> ConsumeExchange(
        string exchangeId,
        string exchangeSecret,
        string sessionId,
        string userId,
        string role,
        string deviceThumbprint,
        TimeSpan? grantLifetime = null,
        TimeSpan? refreshWindow = null)
    {
        if (!ValidIdentifier(exchangeId)
            || !ValidSecret(exchangeSecret)
            || !ValidIdentifier(sessionId)
            || !ValidIdentifier(userId)
            || !ValidRole(role)
            || !ValidSha256(deviceThumbprint)
            || !TryLifetime(
                grantLifetime,
                DefaultGrantLifetime,
                MinimumGrantLifetime,
                MaximumGrantLifetime,
                out TimeSpan grantTtl)
            || !TryLifetime(
                refreshWindow,
                DefaultRefreshWindow,
                grantTtl,
                MaximumRefreshWindow,
                out TimeSpan refreshTtl))
        {
            return Failure<IssuedPlaySessionGrant>(PlaySessionAuthorizationReasons.InvalidRequest);
        }

        return Mutate(() =>
        {
            _store.PlayExchangesById.TryGetValue(exchangeId, out PlaySessionExchange? exchange);
            if (!FixedTimeSecretMatches(exchange?.SecretHashSha256, exchangeSecret))
            {
                return Fail<IssuedPlaySessionGrant>(PlaySessionAuthorizationReasons.ExchangeInvalid);
            }

            DateTimeOffset now = UtcNow();
            if (exchange is null)
            {
                return Fail<IssuedPlaySessionGrant>(PlaySessionAuthorizationReasons.ExchangeInvalid);
            }

            if (string.Equals(exchange.Status, PlaySessionStatuses.Consumed, StringComparison.Ordinal))
            {
                return Fail<IssuedPlaySessionGrant>(PlaySessionAuthorizationReasons.ExchangeReplayed);
            }

            if (string.Equals(exchange.Status, PlaySessionStatuses.Expired, StringComparison.Ordinal)
                || now >= exchange.ExpiresAtUtc)
            {
                if (!string.Equals(exchange.Status, PlaySessionStatuses.Expired, StringComparison.Ordinal))
                {
                    _store.PlayExchangesById[exchange.ExchangeId] = exchange with
                    {
                        Status = PlaySessionStatuses.Expired,
                        UpdatedAtUtc = now
                    };
                    return Fail<IssuedPlaySessionGrant>(
                        PlaySessionAuthorizationReasons.ExchangeExpired,
                        persist: true);
                }

                return Fail<IssuedPlaySessionGrant>(PlaySessionAuthorizationReasons.ExchangeExpired);
            }

            if (!string.Equals(exchange.Status, PlaySessionStatuses.Pending, StringComparison.Ordinal))
            {
                return Fail<IssuedPlaySessionGrant>(PlaySessionAuthorizationReasons.ExchangeInvalid);
            }

            if (!Same(exchange.SessionId, sessionId)
                || !Same(exchange.UserId, userId)
                || !string.Equals(exchange.Role, role, StringComparison.Ordinal)
                || !string.Equals(exchange.DeviceThumbprint, deviceThumbprint, StringComparison.Ordinal)
                || !ValidIdentifier(exchange.ParticipantId)
                || exchange.ParticipantAuthorizationVersion < 1)
            {
                return RevokeExchange<IssuedPlaySessionGrant>(
                    exchange,
                    now,
                    PlaySessionAuthorizationReasons.BindingMismatch);
            }

            if (!TryGetActiveSessionLocked(sessionId, out PlaySessionBinding? session)
                || !_store.PlayParticipantsById.TryGetValue(exchange.ParticipantId!, out PlaySessionParticipant? participant)
                || !string.Equals(participant.Status, PlaySessionStatuses.Active, StringComparison.Ordinal)
                || !Same(participant.SessionId, sessionId)
                || !Same(participant.UserId, userId)
                || !string.Equals(participant.Role, role, StringComparison.Ordinal))
            {
                return RevokeExchange<IssuedPlaySessionGrant>(
                    exchange,
                    now,
                    PlaySessionAuthorizationReasons.MembershipDrift);
            }

            if (exchange.SessionAuthorizationVersion != session.AuthorizationVersion
                || exchange.ParticipantAuthorizationVersion != participant.AuthorizationVersion)
            {
                return RevokeExchange<IssuedPlaySessionGrant>(
                    exchange,
                    now,
                    PlaySessionAuthorizationReasons.VersionDrift);
            }

            if (!ResolveLocked(session, userId, role).Authorized)
            {
                return RevokeExchange<IssuedPlaySessionGrant>(
                    exchange,
                    now,
                    PlaySessionAuthorizationReasons.MembershipDrift);
            }

            SecretMaterial secret = GenerateUniqueSecretLocked();
            PlaySessionGrant grant = new(
                GrantId: NewId("grant"),
                SessionId: sessionId,
                ParticipantId: participant.ParticipantId,
                UserId: userId,
                Role: role,
                SecretHashSha256: secret.Hash,
                Status: PlaySessionStatuses.Active,
                SessionAuthorizationVersion: session.AuthorizationVersion,
                ParticipantAuthorizationVersion: participant.AuthorizationVersion,
                IssuedAtUtc: now,
                UpdatedAtUtc: now,
                ExpiresAtUtc: now.Add(grantTtl),
                RefreshUntilUtc: now.Add(refreshTtl),
                DeviceThumbprint: deviceThumbprint);
            _store.PlayGrantsById.Add(grant.GrantId, grant);
            _store.PlayExchangesById[exchange.ExchangeId] = exchange with
            {
                GrantId = grant.GrantId,
                Status = PlaySessionStatuses.Consumed,
                ConsumedAtUtc = now,
                UpdatedAtUtc = now
            };
            return Success(
                PlaySessionAuthorizationReasons.ExchangeConsumed,
                new IssuedPlaySessionGrant(grant, secret.Raw));
        });
    }

    public PlaySessionAuthorizationResult<PlaySessionGrantContext> IntrospectGrant(
        string grantId,
        string grantSecret,
        string sessionId,
        string userId,
        string role,
        string deviceThumbprint)
    {
        if (!ValidGrantRequest(grantId, grantSecret, sessionId, userId, role, deviceThumbprint))
        {
            return Failure<PlaySessionGrantContext>(PlaySessionAuthorizationReasons.InvalidRequest);
        }

        return Mutate(() => ValidateGrantLocked(
            grantId,
            grantSecret,
            sessionId,
            userId,
            role,
            deviceThumbprint));
    }

    public PlaySessionAuthorizationResult<IssuedPlaySessionGrant> RefreshGrant(
        string grantId,
        string grantSecret,
        string sessionId,
        string userId,
        string role,
        string deviceThumbprint,
        TimeSpan? lifetime = null)
    {
        if (!ValidGrantRequest(grantId, grantSecret, sessionId, userId, role, deviceThumbprint)
            || !TryLifetime(
                lifetime,
                DefaultGrantLifetime,
                MinimumGrantLifetime,
                MaximumGrantLifetime,
                out TimeSpan ttl))
        {
            return Failure<IssuedPlaySessionGrant>(PlaySessionAuthorizationReasons.InvalidRequest);
        }

        return Mutate(() =>
        {
            Mutation<PlaySessionGrantContext> validation = ValidateGrantLocked(
                grantId,
                grantSecret,
                sessionId,
                userId,
                role,
                deviceThumbprint);
            if (!validation.Result.Succeeded)
            {
                return Fail<IssuedPlaySessionGrant>(validation.Result.Reason, validation.ShouldPersist);
            }

            PlaySessionGrant grant = validation.Result.Value!.Grant;
            DateTimeOffset now = UtcNow();
            if (now >= grant.RefreshUntilUtc)
            {
                _store.PlayGrantsById[grant.GrantId] = grant with
                {
                    Status = PlaySessionStatuses.Expired,
                    UpdatedAtUtc = now
                };
                return Fail<IssuedPlaySessionGrant>(
                    PlaySessionAuthorizationReasons.GrantExpired,
                    persist: true);
            }

            DateTimeOffset expiresAt = now.Add(ttl);
            if (expiresAt > grant.RefreshUntilUtc)
            {
                expiresAt = grant.RefreshUntilUtc;
            }

            if (expiresAt <= now)
            {
                return Fail<IssuedPlaySessionGrant>(PlaySessionAuthorizationReasons.GrantExpired);
            }

            SecretMaterial secret = GenerateUniqueSecretLocked(grant.GrantId);
            PlaySessionGrant refreshed = grant with
            {
                SecretHashSha256 = secret.Hash,
                UpdatedAtUtc = now,
                ExpiresAtUtc = expiresAt
            };
            _store.PlayGrantsById[grant.GrantId] = refreshed;
            return Success(
                PlaySessionAuthorizationReasons.GrantRefreshed,
                new IssuedPlaySessionGrant(refreshed, secret.Raw));
        });
    }

    public PlaySessionAuthorizationResult<PlaySessionGrant> RevokeGrant(
        string grantId,
        string sessionId,
        string actorUserId)
    {
        if (!ValidIdentifier(grantId) || !ValidIdentifier(sessionId) || !ValidIdentifier(actorUserId))
        {
            return Failure<PlaySessionGrant>(PlaySessionAuthorizationReasons.InvalidRequest);
        }

        return Mutate(() =>
        {
            if (!_store.PlayGrantsById.TryGetValue(grantId, out PlaySessionGrant? grant)
                || !Same(grant.SessionId, sessionId))
            {
                return Fail<PlaySessionGrant>(PlaySessionAuthorizationReasons.NotFound);
            }

            bool selfRevoke = Same(grant.UserId, actorUserId);
            if (!selfRevoke
                && (!TryGetActiveSessionLocked(sessionId, out PlaySessionBinding? session)
                    || !AuthorizeGameMasterLocked(session, actorUserId)))
            {
                return Fail<PlaySessionGrant>(PlaySessionAuthorizationReasons.NotAuthorized);
            }

            if (string.Equals(grant.Status, PlaySessionStatuses.Revoked, StringComparison.Ordinal))
            {
                return Success(
                    PlaySessionAuthorizationReasons.GrantRevoked,
                    grant,
                    persist: false);
            }

            DateTimeOffset now = UtcNow();
            PlaySessionGrant revoked = grant with
            {
                Status = PlaySessionStatuses.Revoked,
                UpdatedAtUtc = now,
                RevokedAtUtc = now
            };
            _store.PlayGrantsById[grant.GrantId] = revoked;
            return Success(PlaySessionAuthorizationReasons.GrantRevoked, revoked);
        });
    }

    public PlaySessionAuthorizationResult<PlaySessionBinding> BumpSessionAuthorizationVersion(
        string sessionId,
        string actorUserId)
    {
        if (!ValidIdentifier(sessionId) || !ValidIdentifier(actorUserId))
        {
            return Failure<PlaySessionBinding>(PlaySessionAuthorizationReasons.InvalidRequest);
        }

        return Mutate(() =>
        {
            if (!TryGetActiveSessionLocked(sessionId, out PlaySessionBinding? session))
            {
                return Fail<PlaySessionBinding>(PlaySessionAuthorizationReasons.NotFound);
            }

            if (!AuthorizeGameMasterLocked(session, actorUserId))
            {
                return Fail<PlaySessionBinding>(PlaySessionAuthorizationReasons.NotAuthorized);
            }

            PlaySessionBinding bumped = session with
            {
                AuthorizationVersion = checked(session.AuthorizationVersion + 1),
                UpdatedAtUtc = UtcNow()
            };
            _store.PlaySessionsById[session.SessionId] = bumped;
            return Success(PlaySessionAuthorizationReasons.SessionVersionBumped, bumped);
        });
    }

    public PlaySessionAuthorizationResult<PlaySessionParticipant> BumpParticipantAuthorizationVersion(
        string participantId,
        string actorUserId)
    {
        if (!ValidIdentifier(participantId) || !ValidIdentifier(actorUserId))
        {
            return Failure<PlaySessionParticipant>(PlaySessionAuthorizationReasons.InvalidRequest);
        }

        return Mutate(() =>
        {
            if (!_store.PlayParticipantsById.TryGetValue(participantId, out PlaySessionParticipant? participant)
                || !TryGetActiveSessionLocked(participant.SessionId, out PlaySessionBinding? session))
            {
                return Fail<PlaySessionParticipant>(PlaySessionAuthorizationReasons.NotFound);
            }

            if (!AuthorizeGameMasterLocked(session, actorUserId))
            {
                return Fail<PlaySessionParticipant>(PlaySessionAuthorizationReasons.NotAuthorized);
            }

            PlaySessionParticipant bumped = participant with
            {
                AuthorizationVersion = checked(participant.AuthorizationVersion + 1),
                UpdatedAtUtc = UtcNow()
            };
            _store.PlayParticipantsById[participant.ParticipantId] = bumped;
            return Success(PlaySessionAuthorizationReasons.ParticipantVersionBumped, bumped);
        });
    }

    public PlaySessionAuthorizationResult<PlaySessionParticipant> RevokeParticipant(
        string participantId,
        string actorUserId)
    {
        if (!ValidIdentifier(participantId) || !ValidIdentifier(actorUserId))
        {
            return Failure<PlaySessionParticipant>(PlaySessionAuthorizationReasons.InvalidRequest);
        }

        return Mutate(() =>
        {
            if (!_store.PlayParticipantsById.TryGetValue(participantId, out PlaySessionParticipant? participant)
                || !TryGetActiveSessionLocked(participant.SessionId, out PlaySessionBinding? session))
            {
                return Fail<PlaySessionParticipant>(PlaySessionAuthorizationReasons.NotFound);
            }

            if (!AuthorizeGameMasterLocked(session, actorUserId))
            {
                return Fail<PlaySessionParticipant>(PlaySessionAuthorizationReasons.NotAuthorized);
            }

            if (string.Equals(participant.Status, PlaySessionStatuses.Revoked, StringComparison.Ordinal))
            {
                return Success(
                    PlaySessionAuthorizationReasons.ParticipantRevoked,
                    participant,
                    persist: false);
            }

            DateTimeOffset now = UtcNow();
            PlaySessionParticipant revoked = participant with
            {
                Status = PlaySessionStatuses.Revoked,
                AuthorizationVersion = checked(participant.AuthorizationVersion + 1),
                UpdatedAtUtc = now,
                RevokedAtUtc = now
            };
            _store.PlayParticipantsById[participant.ParticipantId] = revoked;
            return Success(PlaySessionAuthorizationReasons.ParticipantRevoked, revoked);
        });
    }

    public PlaySessionAuthorizationResult<PlaySessionBinding> CloseSession(
        string sessionId,
        string actorUserId)
    {
        if (!ValidIdentifier(sessionId) || !ValidIdentifier(actorUserId))
        {
            return Failure<PlaySessionBinding>(PlaySessionAuthorizationReasons.InvalidRequest);
        }

        return Mutate(() =>
        {
            if (!TryGetActiveSessionLocked(sessionId, out PlaySessionBinding? session))
            {
                return Fail<PlaySessionBinding>(PlaySessionAuthorizationReasons.NotFound);
            }

            if (!AuthorizeGameMasterLocked(session, actorUserId))
            {
                return Fail<PlaySessionBinding>(PlaySessionAuthorizationReasons.NotAuthorized);
            }

            DateTimeOffset now = UtcNow();
            PlaySessionBinding closed = session with
            {
                Status = PlaySessionStatuses.Closed,
                AuthorizationVersion = checked(session.AuthorizationVersion + 1),
                UpdatedAtUtc = now,
                ClosedAtUtc = now
            };
            _store.PlaySessionsById[session.SessionId] = closed;

            foreach (PlaySessionParticipant participant in _store.PlayParticipantsById.Values
                         .Where(candidate => Same(candidate.SessionId, sessionId)
                             && string.Equals(candidate.Status, PlaySessionStatuses.Active, StringComparison.Ordinal))
                         .ToArray())
            {
                _store.PlayParticipantsById[participant.ParticipantId] = participant with
                {
                    Status = PlaySessionStatuses.Revoked,
                    AuthorizationVersion = checked(participant.AuthorizationVersion + 1),
                    UpdatedAtUtc = now,
                    RevokedAtUtc = now
                };
            }

            foreach (PlaySessionInvite invite in _store.PlayInvitesById.Values
                         .Where(candidate => Same(candidate.SessionId, sessionId)
                             && string.Equals(candidate.Status, PlaySessionStatuses.Active, StringComparison.Ordinal))
                         .ToArray())
            {
                _store.PlayInvitesById[invite.InviteId] = invite with
                {
                    Status = PlaySessionStatuses.Revoked,
                    UpdatedAtUtc = now,
                    RevokedAtUtc = now
                };
            }

            foreach (PlaySessionExchange exchange in _store.PlayExchangesById.Values
                         .Where(candidate => Same(candidate.SessionId, sessionId)
                             && (string.Equals(candidate.Status, PlaySessionStatuses.Pending, StringComparison.Ordinal)
                                 || string.Equals(candidate.Status, PlaySessionStatuses.Active, StringComparison.Ordinal)))
                         .ToArray())
            {
                _store.PlayExchangesById[exchange.ExchangeId] = exchange with
                {
                    Status = PlaySessionStatuses.Revoked,
                    UpdatedAtUtc = now,
                    RevokedAtUtc = now
                };
            }

            foreach (PlaySessionGrant grant in _store.PlayGrantsById.Values
                         .Where(candidate => Same(candidate.SessionId, sessionId)
                             && string.Equals(candidate.Status, PlaySessionStatuses.Active, StringComparison.Ordinal))
                         .ToArray())
            {
                _store.PlayGrantsById[grant.GrantId] = grant with
                {
                    Status = PlaySessionStatuses.Revoked,
                    UpdatedAtUtc = now,
                    RevokedAtUtc = now
                };
            }

            return Success(PlaySessionAuthorizationReasons.SessionClosed, closed);
        });
    }

    private Mutation<PlaySessionGrantContext> ValidateGrantLocked(
        string grantId,
        string grantSecret,
        string sessionId,
        string userId,
        string role,
        string deviceThumbprint)
    {
        _store.PlayGrantsById.TryGetValue(grantId, out PlaySessionGrant? grant);
        if (!FixedTimeSecretMatches(grant?.SecretHashSha256, grantSecret))
        {
            return Fail<PlaySessionGrantContext>(PlaySessionAuthorizationReasons.GrantInvalid);
        }

        DateTimeOffset now = UtcNow();
        if (grant is null)
        {
            return Fail<PlaySessionGrantContext>(PlaySessionAuthorizationReasons.GrantInvalid);
        }

        if (string.Equals(grant.Status, PlaySessionStatuses.Revoked, StringComparison.Ordinal))
        {
            return Fail<PlaySessionGrantContext>(PlaySessionAuthorizationReasons.GrantRevoked);
        }

        if (string.Equals(grant.Status, PlaySessionStatuses.Expired, StringComparison.Ordinal)
            || now >= grant.ExpiresAtUtc)
        {
            if (!string.Equals(grant.Status, PlaySessionStatuses.Expired, StringComparison.Ordinal))
            {
                _store.PlayGrantsById[grant.GrantId] = grant with
                {
                    Status = PlaySessionStatuses.Expired,
                    UpdatedAtUtc = now
                };
                return Fail<PlaySessionGrantContext>(
                    PlaySessionAuthorizationReasons.GrantExpired,
                    persist: true);
            }

            return Fail<PlaySessionGrantContext>(PlaySessionAuthorizationReasons.GrantExpired);
        }

        if (!string.Equals(grant.Status, PlaySessionStatuses.Active, StringComparison.Ordinal))
        {
            return Fail<PlaySessionGrantContext>(PlaySessionAuthorizationReasons.GrantInvalid);
        }

        if (!Same(grant.SessionId, sessionId)
            || !Same(grant.UserId, userId)
            || !string.Equals(grant.Role, role, StringComparison.Ordinal)
            || !string.Equals(grant.DeviceThumbprint, deviceThumbprint, StringComparison.Ordinal))
        {
            return RevokeGrantForDrift(grant, now, PlaySessionAuthorizationReasons.BindingMismatch);
        }

        if (!TryGetActiveSessionLocked(sessionId, out PlaySessionBinding? session)
            || !_store.PlayParticipantsById.TryGetValue(grant.ParticipantId, out PlaySessionParticipant? participant)
            || !string.Equals(participant.Status, PlaySessionStatuses.Active, StringComparison.Ordinal)
            || !Same(participant.SessionId, sessionId)
            || !Same(participant.UserId, userId)
            || !string.Equals(participant.Role, role, StringComparison.Ordinal))
        {
            return RevokeGrantForDrift(grant, now, PlaySessionAuthorizationReasons.MembershipDrift);
        }

        if (grant.SessionAuthorizationVersion != session.AuthorizationVersion
            || grant.ParticipantAuthorizationVersion != participant.AuthorizationVersion)
        {
            return RevokeGrantForDrift(grant, now, PlaySessionAuthorizationReasons.VersionDrift);
        }

        if (!ResolveLocked(session, userId, role).Authorized)
        {
            return RevokeGrantForDrift(grant, now, PlaySessionAuthorizationReasons.MembershipDrift);
        }

        return Success(
            PlaySessionAuthorizationReasons.GrantActive,
            new PlaySessionGrantContext(grant, session, participant),
            persist: false);
    }

    private Mutation<T> RevokeInvite<T>(PlaySessionInvite invite, DateTimeOffset now, string reason)
        where T : class
    {
        _store.PlayInvitesById[invite.InviteId] = invite with
        {
            Status = PlaySessionStatuses.Revoked,
            UpdatedAtUtc = now,
            RevokedAtUtc = now
        };
        return Fail<T>(reason, persist: true);
    }

    private Mutation<T> RevokeExchange<T>(PlaySessionExchange exchange, DateTimeOffset now, string reason)
        where T : class
    {
        _store.PlayExchangesById[exchange.ExchangeId] = exchange with
        {
            Status = PlaySessionStatuses.Revoked,
            UpdatedAtUtc = now,
            RevokedAtUtc = now
        };
        return Fail<T>(reason, persist: true);
    }

    private Mutation<PlaySessionGrantContext> RevokeGrantForDrift(
        PlaySessionGrant grant,
        DateTimeOffset now,
        string reason)
    {
        _store.PlayGrantsById[grant.GrantId] = grant with
        {
            Status = PlaySessionStatuses.Revoked,
            UpdatedAtUtc = now,
            RevokedAtUtc = now
        };
        return Fail<PlaySessionGrantContext>(reason, persist: true);
    }

    private PlaySessionAuthorizationResult<T> Mutate<T>(Func<Mutation<T>> operation)
        where T : class
    {
        lock (_store.Gate)
        {
            AuthorizationStateSnapshot snapshot;
            try
            {
                snapshot = AuthorizationStateSnapshot.Capture(_store);
            }
            catch (Exception exception) when (IsRecoverablePersistenceException(exception))
            {
                return Failure<T>(PlaySessionAuthorizationReasons.PersistenceFailed);
            }

            Mutation<T> mutation;
            try
            {
                mutation = operation();
            }
            catch
            {
                snapshot.RestoreMemory(_store);
                throw;
            }

            bool timeHighWaterAdvanced = _store.PlayAuthorizationTimeHighWaterUtc > snapshot.TimeHighWaterUtc;
            if (!mutation.ShouldPersist && !timeHighWaterAdvanced)
            {
                return mutation.Result;
            }

            try
            {
                _persistence.PersistLocked(_store);
                return mutation.Result;
            }
            catch (Exception exception) when (IsRecoverablePersistenceException(exception))
            {
                try
                {
                    snapshot.Restore(_store);
                }
                catch (Exception restoreException) when (IsRecoverablePersistenceException(restoreException))
                {
                    throw new InvalidOperationException(
                        "Play authorization rollback could not restore durable state.",
                        restoreException);
                }

                return Failure<T>(PlaySessionAuthorizationReasons.PersistenceFailed);
            }
        }
    }

    private bool TryGetActiveSessionLocked(
        string sessionId,
        [NotNullWhen(true)] out PlaySessionBinding? session)
    {
        if (_store.PlaySessionsById.TryGetValue(sessionId, out session)
            && string.Equals(session.Status, PlaySessionStatuses.Active, StringComparison.Ordinal))
        {
            return true;
        }

        session = null;
        return false;
    }

    private bool AuthorizeGameMasterLocked(PlaySessionBinding session, string actorUserId)
        => ResolveLocked(session, actorUserId, PlaySessionRoles.GameMaster).Authorized;

    private PlaySessionRoleResolution ResolveLocked(
        PlaySessionBinding session,
        string userId,
        string role,
        IReadOnlyList<PlaySessionParticipant>? participants = null)
    {
        _store.GroupsById.TryGetValue(session.GroupId, out GroupDto? group);
        _store.CampaignSpinesById.TryGetValue(session.CampaignId, out CampaignProjection? campaign);
        _store.RunsById.TryGetValue(session.RunId, out RunProjection? run);
        return PlaySessionRoleResolver.Resolve(new PlaySessionAuthorizationFacts(
            Session: session,
            UserId: userId,
            RequestedRole: role,
            Group: group,
            Campaign: campaign,
            Run: run,
            Crews: _store.CrewsById.Values.ToArray(),
            OpenRuns: _store.OpenRuns.ToArray(),
            OpenRunRoster: _store.OpenRunRoster.ToArray(),
            Participants: participants ?? _store.PlayParticipantsById.Values.ToArray()));
    }

    private PlaySessionParticipant? FindParticipantLocked(string sessionId, string userId, string role)
        => _store.PlayParticipantsById.Values
            .Where(candidate => Same(candidate.SessionId, sessionId)
                && Same(candidate.UserId, userId)
                && string.Equals(candidate.Role, role, StringComparison.Ordinal))
            .OrderByDescending(static candidate => candidate.AuthorizationVersion)
            .ThenByDescending(static candidate => candidate.UpdatedAtUtc)
            .FirstOrDefault();

    private PlaySessionParticipant? FindActiveParticipantLocked(string sessionId, string userId, string role)
    {
        PlaySessionParticipant? participant = FindParticipantLocked(sessionId, userId, role);
        return participant is not null
            && string.Equals(participant.Status, PlaySessionStatuses.Active, StringComparison.Ordinal)
            ? participant
            : null;
    }

    private SecretMaterial GenerateUniqueSecretLocked(string? replacingGrantId = null)
    {
        while (true)
        {
            byte[] bytes = RandomNumberGenerator.GetBytes(32);
            string raw;
            try
            {
                raw = Convert.ToBase64String(bytes)
                    .TrimEnd('=')
                    .Replace('+', '-')
                    .Replace('/', '_');
            }
            finally
            {
                CryptographicOperations.ZeroMemory(bytes);
            }

            string hash = HashSecret(raw);
            bool collision = _store.PlayInvitesById.Values.Any(item =>
                    string.Equals(item.SecretHashSha256, hash, StringComparison.Ordinal))
                || _store.PlayExchangesById.Values.Any(item =>
                    string.Equals(item.SecretHashSha256, hash, StringComparison.Ordinal))
                || _store.PlayGrantsById.Values.Any(item =>
                    !Same(item.GrantId, replacingGrantId)
                    && string.Equals(item.SecretHashSha256, hash, StringComparison.Ordinal));
            if (!collision)
            {
                return new SecretMaterial(raw, hash);
            }
        }
    }

    private static bool FixedTimeSecretMatches(string? expectedHash, string rawSecret)
    {
        byte[] secretBytes = Encoding.UTF8.GetBytes(rawSecret);
        byte[] actual;
        try
        {
            actual = SHA256.HashData(secretBytes);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(secretBytes);
        }

        bool validExpected = ValidSha256(expectedHash);
        byte[] expected = validExpected
            ? Convert.FromHexString(expectedHash!)
            : new byte[32];
        try
        {
            bool equal = CryptographicOperations.FixedTimeEquals(expected, actual);
            return validExpected && equal;
        }
        finally
        {
            CryptographicOperations.ZeroMemory(expected);
            CryptographicOperations.ZeroMemory(actual);
        }
    }

    private static string HashSecret(string raw)
    {
        byte[] input = Encoding.UTF8.GetBytes(raw);
        try
        {
            return Convert.ToHexString(SHA256.HashData(input)).ToLowerInvariant();
        }
        finally
        {
            CryptographicOperations.ZeroMemory(input);
        }
    }

    private static bool ValidGrantRequest(
        string grantId,
        string grantSecret,
        string sessionId,
        string userId,
        string role,
        string deviceThumbprint)
        => ValidIdentifier(grantId)
            && ValidSecret(grantSecret)
            && ValidIdentifier(sessionId)
            && ValidIdentifier(userId)
            && ValidRole(role)
            && ValidSha256(deviceThumbprint);

    private static bool ValidIdentifier(string? value)
        => !string.IsNullOrWhiteSpace(value)
            && value.Length <= 128
            && string.Equals(value, value.Trim(), StringComparison.Ordinal);

    private static bool ValidRole(string? role)
        => string.Equals(role, PlaySessionRoles.GameMaster, StringComparison.Ordinal)
            || string.Equals(role, PlaySessionRoles.Player, StringComparison.Ordinal)
            || string.Equals(role, PlaySessionRoles.Observer, StringComparison.Ordinal);

    private static bool ValidSecret(string? secret)
        => secret is not null
            && secret.Length == 43
            && secret.All(static character => character is >= 'A' and <= 'Z'
                or >= 'a' and <= 'z'
                or >= '0' and <= '9'
                or '-'
                or '_');

    private static bool ValidSha256(string? hash)
        => hash is not null
            && hash.Length == 64
            && hash.All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static bool TryLifetime(
        TimeSpan? requested,
        TimeSpan defaultValue,
        TimeSpan minimum,
        TimeSpan maximum,
        out TimeSpan value)
    {
        value = requested ?? defaultValue;
        return value >= minimum && value <= maximum;
    }

    private static bool Same(string? left, string? right)
        => !string.IsNullOrWhiteSpace(left)
            && !string.IsNullOrWhiteSpace(right)
            && string.Equals(left, right, StringComparison.OrdinalIgnoreCase);

    private static string NewId(string prefix)
        => $"{prefix}-{Guid.NewGuid():N}";

    private DateTimeOffset UtcNow()
    {
        if (!Monitor.IsEntered(_store.Gate))
        {
            throw new InvalidOperationException("Play authorization time must be read under the store transaction gate.");
        }

        DateTimeOffset observed = _timeProvider.GetUtcNow().ToUniversalTime();
        long currentTimestamp = _timeProvider.GetTimestamp();
        TimeSpan elapsed = currentTimestamp >= _monotonicAnchorTimestamp
            ? _timeProvider.GetElapsedTime(_monotonicAnchorTimestamp, currentTimestamp)
            : TimeSpan.Zero;
        DateTimeOffset monotonic = _monotonicAnchorUtc.Add(elapsed);
        DateTimeOffset candidate = observed > monotonic ? observed : monotonic;
        if (candidate > _store.PlayAuthorizationTimeHighWaterUtc)
        {
            _store.PlayAuthorizationTimeHighWaterUtc = candidate;
        }

        return _store.PlayAuthorizationTimeHighWaterUtc;
    }

    private static bool IsRecoverablePersistenceException(Exception exception)
        => exception is IOException
            or UnauthorizedAccessException
            or System.Text.Json.JsonException
            or InvalidOperationException;

    private static PlaySessionAuthorizationResult<T> Failure<T>(string reason)
        where T : class
        => new(false, reason, null);

    private static Mutation<T> Success<T>(string reason, T value, bool persist = true)
        where T : class
        => new(new PlaySessionAuthorizationResult<T>(true, reason, value), persist);

    private static Mutation<T> Fail<T>(string reason, bool persist = false)
        where T : class
        => new(new PlaySessionAuthorizationResult<T>(false, reason, null), persist);

    private sealed record SecretMaterial(string Raw, string Hash);

    private sealed record Mutation<T>(PlaySessionAuthorizationResult<T> Result, bool ShouldPersist)
        where T : class;

    private sealed class AuthorizationStateSnapshot
    {
        private readonly PlaySessionBinding[] _sessions;
        private readonly PlaySessionParticipant[] _participants;
        private readonly PlaySessionInvite[] _invites;
        private readonly PlaySessionExchange[] _exchanges;
        private readonly PlaySessionGrant[] _grants;
        private readonly DateTimeOffset _timeHighWaterUtc;
        private readonly bool _fileExisted;
        private readonly byte[]? _fileBytes;

        private AuthorizationStateSnapshot(
            PlaySessionBinding[] sessions,
            PlaySessionParticipant[] participants,
            PlaySessionInvite[] invites,
            PlaySessionExchange[] exchanges,
            PlaySessionGrant[] grants,
            DateTimeOffset timeHighWaterUtc,
            bool fileExisted,
            byte[]? fileBytes)
        {
            _sessions = sessions;
            _participants = participants;
            _invites = invites;
            _exchanges = exchanges;
            _grants = grants;
            _timeHighWaterUtc = timeHighWaterUtc;
            _fileExisted = fileExisted;
            _fileBytes = fileBytes;
        }

        public DateTimeOffset TimeHighWaterUtc => _timeHighWaterUtc;

        public static AuthorizationStateSnapshot Capture(CommunityStore store)
        {
            bool fileExisted = File.Exists(store.StoragePath);
            byte[]? fileBytes = fileExisted ? File.ReadAllBytes(store.StoragePath) : null;
            return new AuthorizationStateSnapshot(
                store.PlaySessionsById.Values.Select(static item => item with { }).ToArray(),
                store.PlayParticipantsById.Values.Select(static item => item with { }).ToArray(),
                store.PlayInvitesById.Values.Select(static item => item with { }).ToArray(),
                store.PlayExchangesById.Values.Select(static item => item with { }).ToArray(),
                store.PlayGrantsById.Values.Select(static item => item with { }).ToArray(),
                store.PlayAuthorizationTimeHighWaterUtc,
                fileExisted,
                fileBytes is null ? null : (byte[])fileBytes.Clone());
        }

        public void Restore(CommunityStore store)
        {
            RestoreMemory(store);
            File.Delete($"{store.StoragePath}.tmp");
            if (_fileExisted)
            {
                string directory = Path.GetDirectoryName(store.StoragePath)
                    ?? throw new InvalidOperationException("Play authorization storage path has no directory.");
                Directory.CreateDirectory(directory);
                string tempPath = $"{store.StoragePath}.rollback-{Guid.NewGuid():N}";
                try
                {
                    File.WriteAllBytes(tempPath, _fileBytes ?? Array.Empty<byte>());
                    File.Move(tempPath, store.StoragePath, overwrite: true);
                }
                finally
                {
                    File.Delete(tempPath);
                }
            }
            else
            {
                File.Delete(store.StoragePath);
            }
        }

        public void RestoreMemory(CommunityStore store)
        {
            RestoreDictionary(store.PlaySessionsById, _sessions, static item => item.SessionId);
            RestoreDictionary(store.PlayParticipantsById, _participants, static item => item.ParticipantId);
            RestoreDictionary(store.PlayInvitesById, _invites, static item => item.InviteId);
            RestoreDictionary(store.PlayExchangesById, _exchanges, static item => item.ExchangeId);
            RestoreDictionary(store.PlayGrantsById, _grants, static item => item.GrantId);
            store.PlayAuthorizationTimeHighWaterUtc = _timeHighWaterUtc;
        }

        private static void RestoreDictionary<T>(
            IDictionary<string, T> target,
            IEnumerable<T> snapshot,
            Func<T, string> keySelector)
        {
            target.Clear();
            foreach (T item in snapshot)
            {
                target.Add(keySelector(item), item);
            }
        }
    }
}
