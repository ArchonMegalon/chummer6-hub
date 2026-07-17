using System.Text.Json;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public static class PlaySessionRoles
{
    public const string GameMaster = "game_master";
    public const string Player = "player";
    public const string Observer = "observer";
}

public static class PlaySessionStatuses
{
    public const string Active = "active";
    public const string Closed = "closed";
    public const string Revoked = "revoked";
    public const string Pending = "pending";
    public const string Consumed = "consumed";
    public const string Expired = "expired";
}

public static class PlaySessionParticipantSources
{
    public const string GroupOperator = "group_operator";
    public const string CrewAssignment = "crew_assignment";
    public const string AcceptedOpenRunRoster = "accepted_open_run_roster";
    public const string ExplicitParticipant = "explicit_participant";
}

public sealed record PlaySessionBinding(
    string SessionId,
    string CampaignId,
    string RunId,
    string GroupId,
    string Status,
    long AuthorizationVersion,
    string CreatedByUserId,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? ClosedAtUtc = null,
    DateTimeOffset? RevokedAtUtc = null);

public sealed record PlaySessionParticipant(
    string ParticipantId,
    string SessionId,
    string UserId,
    string Role,
    string SourceKind,
    string SourceId,
    string Status,
    long AuthorizationVersion,
    string AddedByUserId,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? RevokedAtUtc = null);

public sealed record PlaySessionInvite(
    string InviteId,
    string SessionId,
    string RequestedRole,
    string? TargetUserId,
    string SecretHashSha256,
    string Status,
    long SessionAuthorizationVersion,
    string CreatedByUserId,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    string? ConsumedByUserId = null,
    DateTimeOffset? ConsumedAtUtc = null,
    DateTimeOffset? RevokedAtUtc = null,
    string? ParticipantId = null,
    long ParticipantAuthorizationVersion = 0);

public sealed record PlaySessionExchange(
    string ExchangeId,
    string InviteId,
    string? GrantId,
    string SecretHashSha256,
    string Status,
    long SessionAuthorizationVersion,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    DateTimeOffset? ConsumedAtUtc = null,
    DateTimeOffset? RevokedAtUtc = null,
    string? SessionId = null,
    string? ParticipantId = null,
    string? UserId = null,
    string? Role = null,
    string? DeviceThumbprint = null,
    long ParticipantAuthorizationVersion = 0);

public sealed record PlaySessionGrant(
    string GrantId,
    string SessionId,
    string ParticipantId,
    string UserId,
    string Role,
    string SecretHashSha256,
    string Status,
    long SessionAuthorizationVersion,
    long ParticipantAuthorizationVersion,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    DateTimeOffset RefreshUntilUtc,
    DateTimeOffset? RevokedAtUtc = null,
    string? DeviceThumbprint = null);

public sealed record PlaySessionAuthorizationFacts(
    PlaySessionBinding? Session,
    string UserId,
    string RequestedRole,
    GroupDto? Group,
    CampaignProjection? Campaign,
    RunProjection? Run,
    IReadOnlyList<CrewProjection> Crews,
    IReadOnlyList<OpenRunListingProjection> OpenRuns,
    IReadOnlyList<OpenRunRosterEntryProjection> OpenRunRoster,
    IReadOnlyList<PlaySessionParticipant> Participants);

public sealed record PlaySessionRoleResolution(
    bool Authorized,
    string? Role,
    string? SourceKind,
    string? SourceId,
    string Reason)
{
    public static PlaySessionRoleResolution Allow(string role, string sourceKind, string sourceId)
        => new(true, role, sourceKind, sourceId, "authorized");

    public static PlaySessionRoleResolution Deny(string reason)
        => new(false, null, null, null, reason);
}

public static class PlaySessionRoleResolver
{
    private static readonly HashSet<string> OperatorRoles = new(StringComparer.OrdinalIgnoreCase)
    {
        "owner",
        "admin",
        "manager",
        "gm"
    };

    private const string LiveCampaignStatus = "active";
    private const string LiveRunStatus = "active";
    private const string LiveCrewAvailability = "available";
    private const string LiveOpenRunStatus = "listed";
    private const string AcceptedSeatStatus = "accepted";

    public static PlaySessionRoleResolution Resolve(PlaySessionAuthorizationFacts facts)
    {
        ArgumentNullException.ThrowIfNull(facts);

        string userId = facts.UserId?.Trim() ?? string.Empty;
        if (userId.Length == 0 || !IsRole(facts.RequestedRole))
        {
            return PlaySessionRoleResolution.Deny("invalid_request");
        }

        PlaySessionBinding? session = facts.Session;
        if (session is null)
        {
            return PlaySessionRoleResolution.Deny("session_not_found");
        }

        if (session.AuthorizationVersion < 1
            || string.IsNullOrWhiteSpace(session.SessionId)
            || string.IsNullOrWhiteSpace(session.GroupId)
            || string.IsNullOrWhiteSpace(session.CampaignId)
            || string.IsNullOrWhiteSpace(session.RunId))
        {
            return PlaySessionRoleResolution.Deny("session_invalid");
        }

        if (!string.Equals(session.Status, PlaySessionStatuses.Active, StringComparison.Ordinal))
        {
            return PlaySessionRoleResolution.Deny("session_inactive");
        }

        if (facts.Group is null
            || !Same(facts.Group.GroupId, session.GroupId))
        {
            return PlaySessionRoleResolution.Deny("group_mismatch");
        }

        if (facts.Campaign is null
            || !Same(facts.Campaign.CampaignId, session.CampaignId)
            || !Same(facts.Campaign.GroupId, session.GroupId))
        {
            return PlaySessionRoleResolution.Deny("campaign_mismatch");
        }

        if (!string.Equals(facts.Campaign.Status, LiveCampaignStatus, StringComparison.OrdinalIgnoreCase))
        {
            return PlaySessionRoleResolution.Deny("campaign_inactive");
        }

        if (facts.Run is null
            || !Same(facts.Run.RunId, session.RunId)
            || !Same(facts.Run.CampaignId, session.CampaignId)
            || !(facts.Campaign.RunIds ?? Array.Empty<string>()).Any(runId => Same(runId, session.RunId)))
        {
            return PlaySessionRoleResolution.Deny("run_mismatch");
        }

        if (!string.Equals(facts.Run.Status, LiveRunStatus, StringComparison.OrdinalIgnoreCase))
        {
            return PlaySessionRoleResolution.Deny("run_inactive");
        }

        PlaySessionParticipant? boundParticipant = (facts.Participants ?? Array.Empty<PlaySessionParticipant>())
            .Where(participant =>
                Same(participant.SessionId, session.SessionId)
                && Same(participant.UserId, userId)
                && string.Equals(participant.Role, facts.RequestedRole, StringComparison.Ordinal))
            .OrderByDescending(static participant => participant.AuthorizationVersion)
            .ThenByDescending(static participant => participant.UpdatedAtUtc)
            .ThenBy(static participant => participant.ParticipantId, StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault();

        if (boundParticipant is not null
            && string.Equals(boundParticipant.Status, PlaySessionStatuses.Revoked, StringComparison.Ordinal))
        {
            return PlaySessionRoleResolution.Deny("participant_revoked");
        }

        if (string.Equals(facts.RequestedRole, PlaySessionRoles.GameMaster, StringComparison.Ordinal))
        {
            bool groupOwner = Same(facts.Group.OwnerUserId, userId);
            GroupMembershipDto? operatorMembership = (facts.Group.Memberships ?? Array.Empty<GroupMembershipDto>())
                .Where(membership => Same(membership.GroupId, session.GroupId)
                    && Same(membership.UserId, userId)
                    && OperatorRoles.Contains(membership.Role))
                .OrderBy(static membership => membership.MembershipId, StringComparer.OrdinalIgnoreCase)
                .FirstOrDefault();
            if (groupOwner)
            {
                return PlaySessionRoleResolution.Allow(
                    PlaySessionRoles.GameMaster,
                    PlaySessionParticipantSources.GroupOperator,
                    facts.Group.GroupId);
            }

            return operatorMembership is not null
                ? PlaySessionRoleResolution.Allow(
                    PlaySessionRoles.GameMaster,
                    PlaySessionParticipantSources.GroupOperator,
                    operatorMembership.MembershipId)
                : PlaySessionRoleResolution.Deny("role_not_authorized");
        }

        if (boundParticipant is not null
            && string.Equals(boundParticipant.Status, PlaySessionStatuses.Active, StringComparison.Ordinal)
            && string.Equals(
                boundParticipant.SourceKind,
                PlaySessionParticipantSources.ExplicitParticipant,
                StringComparison.Ordinal))
        {
            return PlaySessionRoleResolution.Allow(
                facts.RequestedRole,
                PlaySessionParticipantSources.ExplicitParticipant,
                boundParticipant.ParticipantId);
        }

        if (string.Equals(facts.RequestedRole, PlaySessionRoles.Observer, StringComparison.Ordinal))
        {
            return PlaySessionRoleResolution.Deny("role_not_authorized");
        }

        CrewProjection? crew = (facts.Crews ?? Array.Empty<CrewProjection>())
            .Where(candidate =>
                Same(candidate.GroupId, session.GroupId)
                && Same(candidate.CampaignId, session.CampaignId)
                && (facts.Campaign.CrewIds ?? Array.Empty<string>()).Any(crewId => Same(crewId, candidate.CrewId))
                && (candidate.Members ?? Array.Empty<CrewAssignmentProjection>()).Any(member =>
                    Same(member.UserId, userId)
                    && string.Equals(member.Availability, LiveCrewAvailability, StringComparison.OrdinalIgnoreCase)))
            .OrderBy(static candidate => candidate.CrewId, StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault();
        if (crew is not null)
        {
            return PlaySessionRoleResolution.Allow(
                PlaySessionRoles.Player,
                PlaySessionParticipantSources.CrewAssignment,
                crew.CrewId);
        }

        IReadOnlyList<OpenRunRosterEntryProjection> roster = facts.OpenRunRoster ?? Array.Empty<OpenRunRosterEntryProjection>();
        var openRunAuthority = (facts.OpenRuns ?? Array.Empty<OpenRunListingProjection>())
            .Where(listing => Same(listing.CampaignId, session.CampaignId)
                && Same(listing.RunId, session.RunId)
                && string.Equals(listing.Status, LiveOpenRunStatus, StringComparison.OrdinalIgnoreCase))
            .SelectMany(listing => roster
                .Where(entry => Same(entry.OpenRunId, listing.OpenRunId)
                    && Same(entry.UserId, userId)
                    && string.Equals(entry.SeatStatus, AcceptedSeatStatus, StringComparison.OrdinalIgnoreCase))
                .Select(entry => new { Listing = listing, Entry = entry }))
            .OrderBy(static authority => authority.Listing.OpenRunId, StringComparer.OrdinalIgnoreCase)
            .ThenBy(static authority => authority.Entry.EntryId, StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault();
        return openRunAuthority is not null
            ? PlaySessionRoleResolution.Allow(
                PlaySessionRoles.Player,
                PlaySessionParticipantSources.AcceptedOpenRunRoster,
                openRunAuthority.Entry.EntryId)
            : PlaySessionRoleResolution.Deny("role_not_authorized");
    }

    private static bool Same(string? left, string? right)
        => !string.IsNullOrWhiteSpace(left)
            && !string.IsNullOrWhiteSpace(right)
            && string.Equals(left, right, StringComparison.OrdinalIgnoreCase);

    private static bool IsRole(string? role)
        => string.Equals(role, PlaySessionRoles.GameMaster, StringComparison.Ordinal)
            || string.Equals(role, PlaySessionRoles.Player, StringComparison.Ordinal)
            || string.Equals(role, PlaySessionRoles.Observer, StringComparison.Ordinal);

}

public static class PlaySessionAuthorizationValidator
{
    private const int MaxIdentifierLength = 128;

    private static readonly HashSet<string> Roles = new(StringComparer.Ordinal)
    {
        PlaySessionRoles.GameMaster,
        PlaySessionRoles.Player,
        PlaySessionRoles.Observer
    };

    private static readonly HashSet<string> ParticipantSources = new(StringComparer.Ordinal)
    {
        PlaySessionParticipantSources.GroupOperator,
        PlaySessionParticipantSources.CrewAssignment,
        PlaySessionParticipantSources.AcceptedOpenRunRoster,
        PlaySessionParticipantSources.ExplicitParticipant
    };

    public static void ValidateTimeHighWater(DateTimeOffset? value)
    {
        if (value is not null)
        {
            RequireUtc(value.Value, "play authorization time high-water mark");
        }
    }

    public static void ValidateSnapshot(
        IEnumerable<PlaySessionBinding> sessions,
        IEnumerable<PlaySessionParticipant> participants,
        IEnumerable<PlaySessionInvite> invites,
        IEnumerable<PlaySessionExchange> exchanges,
        IEnumerable<PlaySessionGrant> grants)
    {
        PlaySessionBinding[] sessionItems = Materialize(sessions, nameof(sessions));
        PlaySessionParticipant[] participantItems = Materialize(participants, nameof(participants));
        PlaySessionInvite[] inviteItems = Materialize(invites, nameof(invites));
        PlaySessionExchange[] exchangeItems = Materialize(exchanges, nameof(exchanges));
        PlaySessionGrant[] grantItems = Materialize(grants, nameof(grants));

        Dictionary<string, PlaySessionBinding> sessionsById = UniqueBy(
            sessionItems,
            static item => item.SessionId,
            "play session");
        Dictionary<string, PlaySessionParticipant> participantsById = UniqueBy(
            participantItems,
            static item => item.ParticipantId,
            "play participant");
        Dictionary<string, PlaySessionInvite> invitesById = UniqueBy(
            inviteItems,
            static item => item.InviteId,
            "play invite");
        Dictionary<string, PlaySessionGrant> grantsById = UniqueBy(
            grantItems,
            static item => item.GrantId,
            "play grant");
        _ = UniqueBy(exchangeItems, static item => item.ExchangeId, "play exchange");

        HashSet<string> participantBindings = new(StringComparer.OrdinalIgnoreCase);
        HashSet<string> secretHashes = new(StringComparer.Ordinal);
        HashSet<string> exchangeInviteBindings = new(StringComparer.OrdinalIgnoreCase);
        HashSet<string> exchangeGrantBindings = new(StringComparer.OrdinalIgnoreCase);

        foreach (PlaySessionBinding session in sessionItems)
        {
            ValidateSession(session);
        }

        foreach (PlaySessionParticipant participant in participantItems)
        {
            ValidateParticipant(participant);
            _ = RequireReference(sessionsById, participant.SessionId, "participant session");
            string bindingKey = $"{participant.SessionId}\u001f{participant.UserId}\u001f{participant.Role}";
            if (!participantBindings.Add(bindingKey))
            {
                throw Invalid($"Duplicate play participant binding: {participant.SessionId}/{participant.UserId}/{participant.Role}.");
            }
        }

        foreach (PlaySessionInvite invite in inviteItems)
        {
            ValidateInvite(invite);
            RegisterSecretHash(secretHashes, invite.SecretHashSha256, $"invite {invite.InviteId}");
            PlaySessionBinding session = RequireReference(sessionsById, invite.SessionId, "invite session");
            RequireVersionNotAhead(invite.SessionAuthorizationVersion, session.AuthorizationVersion, "invite session authorization version");
            if (invite.ParticipantId is null)
            {
                if (invite.ParticipantAuthorizationVersion != 0)
                {
                    throw Invalid($"Invite {invite.InviteId} has a participant version without a participant binding.");
                }
            }
            else
            {
                PlaySessionParticipant participant = RequireReference(
                    participantsById,
                    invite.ParticipantId,
                    "invite participant");
                if (!Same(participant.SessionId, invite.SessionId)
                    || !Same(participant.UserId, invite.TargetUserId)
                    || !string.Equals(participant.Role, invite.RequestedRole, StringComparison.Ordinal)
                    || invite.ParticipantAuthorizationVersion < 1)
                {
                    throw Invalid($"Invite {invite.InviteId} does not match its participant authority binding.");
                }

                RequireVersionNotAhead(
                    invite.ParticipantAuthorizationVersion,
                    participant.AuthorizationVersion,
                    "invite participant authorization version");
            }
        }

        foreach (PlaySessionGrant grant in grantItems)
        {
            ValidateGrant(grant);
            RegisterSecretHash(secretHashes, grant.SecretHashSha256, $"grant {grant.GrantId}");
            PlaySessionBinding session = RequireReference(sessionsById, grant.SessionId, "grant session");
            PlaySessionParticipant participant = RequireReference(participantsById, grant.ParticipantId, "grant participant");
            if (!Same(participant.SessionId, grant.SessionId)
                || !Same(participant.UserId, grant.UserId)
                || !string.Equals(participant.Role, grant.Role, StringComparison.Ordinal))
            {
                throw Invalid($"Grant {grant.GrantId} does not match its participant authority binding.");
            }

            RequireVersionNotAhead(grant.SessionAuthorizationVersion, session.AuthorizationVersion, "grant session authorization version");
            RequireVersionNotAhead(grant.ParticipantAuthorizationVersion, participant.AuthorizationVersion, "grant participant authorization version");
        }

        foreach (PlaySessionExchange exchange in exchangeItems)
        {
            ValidateExchange(exchange);
            RegisterSecretHash(secretHashes, exchange.SecretHashSha256, $"exchange {exchange.ExchangeId}");
            if (!exchangeInviteBindings.Add(exchange.InviteId))
            {
                throw Invalid($"Invite {exchange.InviteId} is bound to more than one exchange.");
            }

            PlaySessionInvite invite = RequireReference(invitesById, exchange.InviteId, "exchange invite");
            PlaySessionBinding session = RequireReference(sessionsById, invite.SessionId, "exchange session");
            RequireVersionNotAhead(exchange.SessionAuthorizationVersion, session.AuthorizationVersion, "exchange session authorization version");

            if (!string.Equals(invite.Status, PlaySessionStatuses.Consumed, StringComparison.Ordinal)
                || invite.ConsumedAtUtc != exchange.CreatedAtUtc
                || !Same(invite.ConsumedByUserId, exchange.UserId))
            {
                throw Invalid($"Exchange {exchange.ExchangeId} is not backed by one coherent consumed invite transition.");
            }

            if (exchange.SessionAuthorizationVersion != invite.SessionAuthorizationVersion)
            {
                throw Invalid($"Exchange {exchange.ExchangeId} does not preserve its role-bound authorization version.");
            }

            if (!Same(invite.SessionId, exchange.SessionId))
            {
                throw Invalid($"Exchange {exchange.ExchangeId} crosses play sessions.");
            }

            if (!string.Equals(invite.RequestedRole, exchange.Role, StringComparison.Ordinal))
            {
                throw Invalid($"Exchange {exchange.ExchangeId} does not preserve its role-bound authorization version.");
            }

            if (invite.ParticipantId is not null
                && (!Same(invite.ParticipantId, exchange.ParticipantId)
                    || invite.ParticipantAuthorizationVersion != exchange.ParticipantAuthorizationVersion))
            {
                throw Invalid($"Exchange {exchange.ExchangeId} does not preserve its invite participant authorization version.");
            }

            PlaySessionParticipant participant = RequireReference(
                participantsById,
                exchange.ParticipantId!,
                "exchange participant");
            if (!Same(participant.SessionId, invite.SessionId)
                || !Same(participant.UserId, exchange.UserId)
                || !string.Equals(participant.Role, exchange.Role, StringComparison.Ordinal))
            {
                throw Invalid($"Exchange {exchange.ExchangeId} does not match its participant authority binding.");
            }

            RequireVersionNotAhead(
                exchange.ParticipantAuthorizationVersion,
                participant.AuthorizationVersion,
                "exchange participant authorization version");

            if (exchange.GrantId is null)
            {
                if (string.Equals(exchange.Status, PlaySessionStatuses.Consumed, StringComparison.Ordinal))
                {
                    throw Invalid($"Consumed exchange {exchange.ExchangeId} must reference its grant.");
                }

                continue;
            }

            if (!string.Equals(exchange.Status, PlaySessionStatuses.Consumed, StringComparison.Ordinal)
                || !exchangeGrantBindings.Add(exchange.GrantId))
            {
                throw Invalid($"Exchange {exchange.ExchangeId} does not have one unique consumed grant transition.");
            }

            PlaySessionGrant grant = RequireReference(grantsById, exchange.GrantId, "exchange grant");
            if (!Same(invite.SessionId, grant.SessionId)
                || !Same(exchange.SessionId, grant.SessionId))
            {
                throw Invalid($"Exchange {exchange.ExchangeId} crosses play sessions.");
            }

            if (!Same(exchange.ParticipantId, grant.ParticipantId)
                || !Same(exchange.UserId, grant.UserId)
                || !string.Equals(invite.RequestedRole, grant.Role, StringComparison.Ordinal)
                || !string.Equals(exchange.Role, grant.Role, StringComparison.Ordinal)
                || !string.Equals(exchange.DeviceThumbprint, grant.DeviceThumbprint, StringComparison.Ordinal)
                || exchange.SessionAuthorizationVersion != invite.SessionAuthorizationVersion
                || exchange.SessionAuthorizationVersion != grant.SessionAuthorizationVersion
                || exchange.ParticipantAuthorizationVersion != grant.ParticipantAuthorizationVersion
                || exchange.ConsumedAtUtc != grant.IssuedAtUtc
                || grant.IssuedAtUtc >= exchange.ExpiresAtUtc)
            {
                throw Invalid($"Exchange {exchange.ExchangeId} does not preserve its role-bound authorization version.");
            }
        }

        foreach (PlaySessionInvite consumedInvite in inviteItems.Where(static invite =>
                     string.Equals(invite.Status, PlaySessionStatuses.Consumed, StringComparison.Ordinal)))
        {
            if (!exchangeInviteBindings.Contains(consumedInvite.InviteId))
            {
                throw Invalid($"Consumed invite {consumedInvite.InviteId} must reference exactly one exchange.");
            }
        }

        foreach (PlaySessionGrant grant in grantItems)
        {
            if (!exchangeGrantBindings.Contains(grant.GrantId))
            {
                throw Invalid($"Grant {grant.GrantId} must be issued by exactly one consumed exchange.");
            }
        }
    }

    private static void ValidateSession(PlaySessionBinding item)
    {
        RequireIdentifier(item.SessionId, nameof(item.SessionId));
        RequireIdentifier(item.CampaignId, nameof(item.CampaignId));
        RequireIdentifier(item.RunId, nameof(item.RunId));
        RequireIdentifier(item.GroupId, nameof(item.GroupId));
        RequireIdentifier(item.CreatedByUserId, nameof(item.CreatedByUserId));
        RequirePositiveVersion(item.AuthorizationVersion, nameof(item.AuthorizationVersion));
        ValidateCreatedUpdated(item.CreatedAtUtc, item.UpdatedAtUtc, "play session");
        ValidateTerminalLifecycle(item.Status, item.ClosedAtUtc, item.RevokedAtUtc, item.CreatedAtUtc, item.UpdatedAtUtc, "play session");
    }

    private static void ValidateParticipant(PlaySessionParticipant item)
    {
        RequireIdentifier(item.ParticipantId, nameof(item.ParticipantId));
        RequireIdentifier(item.SessionId, nameof(item.SessionId));
        RequireIdentifier(item.UserId, nameof(item.UserId));
        RequireCanonical(item.Role, Roles, nameof(item.Role));
        RequireCanonical(item.SourceKind, ParticipantSources, nameof(item.SourceKind));
        RequireIdentifier(item.SourceId, nameof(item.SourceId));
        RequireIdentifier(item.AddedByUserId, nameof(item.AddedByUserId));
        RequirePositiveVersion(item.AuthorizationVersion, nameof(item.AuthorizationVersion));
        ValidateCreatedUpdated(item.CreatedAtUtc, item.UpdatedAtUtc, "play participant");
        if (string.Equals(item.Status, PlaySessionStatuses.Active, StringComparison.Ordinal))
        {
            RequireNull(item.RevokedAtUtc, "active participant revokedAtUtc");
        }
        else if (string.Equals(item.Status, PlaySessionStatuses.Revoked, StringComparison.Ordinal))
        {
            RequireLifecycleTimestamp(item.RevokedAtUtc, item.CreatedAtUtc, item.UpdatedAtUtc, "revoked participant revokedAtUtc");
        }
        else
        {
            throw Invalid($"Unsupported play participant status: {item.Status}.");
        }
    }

    private static void ValidateInvite(PlaySessionInvite item)
    {
        RequireIdentifier(item.InviteId, nameof(item.InviteId));
        RequireIdentifier(item.SessionId, nameof(item.SessionId));
        RequireCanonical(item.RequestedRole, Roles, nameof(item.RequestedRole));
        RequireOptionalIdentifier(item.TargetUserId, nameof(item.TargetUserId));
        RequireSha256(item.SecretHashSha256, nameof(item.SecretHashSha256));
        RequireIdentifier(item.CreatedByUserId, nameof(item.CreatedByUserId));
        RequirePositiveVersion(item.SessionAuthorizationVersion, nameof(item.SessionAuthorizationVersion));
        RequireOptionalIdentifier(item.ParticipantId, nameof(item.ParticipantId));
        if (item.ParticipantAuthorizationVersion < 0)
        {
            throw Invalid("Invite ParticipantAuthorizationVersion cannot be negative.");
        }

        ValidateCreatedUpdated(item.CreatedAtUtc, item.UpdatedAtUtc, "play invite");
        RequireExpiry(item.CreatedAtUtc, item.ExpiresAtUtc, "play invite");
        ValidateConsumableLifecycle(
            item.Status,
            item.ConsumedAtUtc,
            item.RevokedAtUtc,
            item.CreatedAtUtc,
            item.UpdatedAtUtc,
            item.ExpiresAtUtc,
            "play invite");
        if (string.Equals(item.Status, PlaySessionStatuses.Consumed, StringComparison.Ordinal))
        {
            RequireIdentifier(item.ConsumedByUserId, nameof(item.ConsumedByUserId));
        }
        else if (item.ConsumedByUserId is not null)
        {
            throw Invalid("Only consumed play invites may name a consuming user.");
        }
    }

    private static void ValidateExchange(PlaySessionExchange item)
    {
        RequireIdentifier(item.ExchangeId, nameof(item.ExchangeId));
        RequireIdentifier(item.InviteId, nameof(item.InviteId));
        RequireOptionalIdentifier(item.GrantId, nameof(item.GrantId));
        RequireSha256(item.SecretHashSha256, nameof(item.SecretHashSha256));
        RequirePositiveVersion(item.SessionAuthorizationVersion, nameof(item.SessionAuthorizationVersion));
        RequireIdentifier(item.SessionId, nameof(item.SessionId));
        RequireIdentifier(item.ParticipantId, nameof(item.ParticipantId));
        RequireIdentifier(item.UserId, nameof(item.UserId));
        RequireCanonical(item.Role, Roles, nameof(item.Role));
        RequireSha256(item.DeviceThumbprint, nameof(item.DeviceThumbprint));
        RequirePositiveVersion(item.ParticipantAuthorizationVersion, nameof(item.ParticipantAuthorizationVersion));

        ValidateCreatedUpdated(item.CreatedAtUtc, item.UpdatedAtUtc, "play exchange");
        RequireExpiry(item.CreatedAtUtc, item.ExpiresAtUtc, "play exchange");
        ValidateConsumableLifecycle(
            item.Status,
            item.ConsumedAtUtc,
            item.RevokedAtUtc,
            item.CreatedAtUtc,
            item.UpdatedAtUtc,
            item.ExpiresAtUtc,
            "play exchange");
    }

    private static void ValidateGrant(PlaySessionGrant item)
    {
        RequireIdentifier(item.GrantId, nameof(item.GrantId));
        RequireIdentifier(item.SessionId, nameof(item.SessionId));
        RequireIdentifier(item.ParticipantId, nameof(item.ParticipantId));
        RequireIdentifier(item.UserId, nameof(item.UserId));
        RequireCanonical(item.Role, Roles, nameof(item.Role));
        RequireSha256(item.SecretHashSha256, nameof(item.SecretHashSha256));
        RequireOptionalSha256(item.DeviceThumbprint, nameof(item.DeviceThumbprint));
        RequirePositiveVersion(item.SessionAuthorizationVersion, nameof(item.SessionAuthorizationVersion));
        RequirePositiveVersion(item.ParticipantAuthorizationVersion, nameof(item.ParticipantAuthorizationVersion));
        ValidateCreatedUpdated(item.IssuedAtUtc, item.UpdatedAtUtc, "play grant");
        RequireExpiry(item.IssuedAtUtc, item.ExpiresAtUtc, "play grant");
        RequireUtc(item.RefreshUntilUtc, nameof(item.RefreshUntilUtc));
        if (item.RefreshUntilUtc < item.ExpiresAtUtc)
        {
            throw Invalid("Play grant refreshUntilUtc cannot precede expiresAtUtc.");
        }

        if (string.Equals(item.Status, PlaySessionStatuses.Active, StringComparison.Ordinal))
        {
            RequireNull(item.RevokedAtUtc, "active grant revokedAtUtc");
        }
        else if (string.Equals(item.Status, PlaySessionStatuses.Revoked, StringComparison.Ordinal))
        {
            RequireLifecycleTimestamp(item.RevokedAtUtc, item.IssuedAtUtc, item.UpdatedAtUtc, "revoked grant revokedAtUtc");
        }
        else if (string.Equals(item.Status, PlaySessionStatuses.Expired, StringComparison.Ordinal))
        {
            RequireNull(item.RevokedAtUtc, "expired grant revokedAtUtc");
            if (item.UpdatedAtUtc < item.ExpiresAtUtc)
            {
                throw Invalid("Expired play grant updatedAtUtc must not precede expiresAtUtc.");
            }
        }
        else
        {
            throw Invalid($"Unsupported play grant status: {item.Status}.");
        }
    }

    private static void ValidateTerminalLifecycle(
        string status,
        DateTimeOffset? closedAtUtc,
        DateTimeOffset? revokedAtUtc,
        DateTimeOffset createdAtUtc,
        DateTimeOffset updatedAtUtc,
        string label)
    {
        if (string.Equals(status, PlaySessionStatuses.Active, StringComparison.Ordinal))
        {
            RequireNull(closedAtUtc, $"active {label} closedAtUtc");
            RequireNull(revokedAtUtc, $"active {label} revokedAtUtc");
        }
        else if (string.Equals(status, PlaySessionStatuses.Closed, StringComparison.Ordinal))
        {
            RequireLifecycleTimestamp(closedAtUtc, createdAtUtc, updatedAtUtc, $"closed {label} closedAtUtc");
            RequireNull(revokedAtUtc, $"closed {label} revokedAtUtc");
        }
        else if (string.Equals(status, PlaySessionStatuses.Revoked, StringComparison.Ordinal))
        {
            RequireNull(closedAtUtc, $"revoked {label} closedAtUtc");
            RequireLifecycleTimestamp(revokedAtUtc, createdAtUtc, updatedAtUtc, $"revoked {label} revokedAtUtc");
        }
        else
        {
            throw Invalid($"Unsupported {label} status: {status}.");
        }
    }

    private static void ValidateConsumableLifecycle(
        string status,
        DateTimeOffset? consumedAtUtc,
        DateTimeOffset? revokedAtUtc,
        DateTimeOffset createdAtUtc,
        DateTimeOffset updatedAtUtc,
        DateTimeOffset expiresAtUtc,
        string label)
    {
        if (string.Equals(status, PlaySessionStatuses.Active, StringComparison.Ordinal)
            || string.Equals(status, PlaySessionStatuses.Pending, StringComparison.Ordinal))
        {
            RequireNull(consumedAtUtc, $"pending {label} consumedAtUtc");
            RequireNull(revokedAtUtc, $"pending {label} revokedAtUtc");
        }
        else if (string.Equals(status, PlaySessionStatuses.Consumed, StringComparison.Ordinal))
        {
            RequireLifecycleTimestamp(consumedAtUtc, createdAtUtc, updatedAtUtc, $"consumed {label} consumedAtUtc");
            RequireNull(revokedAtUtc, $"consumed {label} revokedAtUtc");
            if (consumedAtUtc >= expiresAtUtc)
            {
                throw Invalid($"Consumed {label} must be consumed before expiresAtUtc.");
            }
        }
        else if (string.Equals(status, PlaySessionStatuses.Revoked, StringComparison.Ordinal))
        {
            RequireNull(consumedAtUtc, $"revoked {label} consumedAtUtc");
            RequireLifecycleTimestamp(revokedAtUtc, createdAtUtc, updatedAtUtc, $"revoked {label} revokedAtUtc");
        }
        else if (string.Equals(status, PlaySessionStatuses.Expired, StringComparison.Ordinal))
        {
            RequireNull(consumedAtUtc, $"expired {label} consumedAtUtc");
            RequireNull(revokedAtUtc, $"expired {label} revokedAtUtc");
            if (updatedAtUtc < expiresAtUtc)
            {
                throw Invalid($"Expired {label} updatedAtUtc must not precede expiresAtUtc.");
            }
        }
        else
        {
            throw Invalid($"Unsupported {label} status: {status}.");
        }
    }

    private static T[] Materialize<T>(IEnumerable<T>? items, string label)
        where T : class
    {
        if (items is null)
        {
            throw Invalid($"{label} collection is required.");
        }

        T[] materialized = items.ToArray();
        if (materialized.Any(static item => item is null))
        {
            throw Invalid($"{label} collection cannot contain null records.");
        }

        return materialized;
    }

    private static Dictionary<string, T> UniqueBy<T>(
        IEnumerable<T> items,
        Func<T, string> keySelector,
        string label)
    {
        Dictionary<string, T> values = new(StringComparer.OrdinalIgnoreCase);
        foreach (T item in items)
        {
            string key = keySelector(item);
            RequireIdentifier(key, $"{label} identifier");
            if (!values.TryAdd(key, item))
            {
                throw Invalid($"Duplicate {label} identifier: {key}.");
            }
        }

        return values;
    }

    private static T RequireReference<T>(IReadOnlyDictionary<string, T> values, string key, string label)
    {
        if (!values.TryGetValue(key, out T? value))
        {
            throw Invalid($"Unknown {label}: {key}.");
        }

        return value;
    }

    private static void RegisterSecretHash(HashSet<string> hashes, string hash, string label)
    {
        if (!hashes.Add(hash))
        {
            throw Invalid($"Duplicate play authorization secret hash on {label}.");
        }
    }

    private static void RequireIdentifier(string? value, string label)
    {
        if (string.IsNullOrWhiteSpace(value)
            || value.Length > MaxIdentifierLength
            || !string.Equals(value, value.Trim(), StringComparison.Ordinal))
        {
            throw Invalid($"{label} must be a non-blank canonical identifier of at most {MaxIdentifierLength} characters.");
        }
    }

    private static void RequireOptionalIdentifier(string? value, string label)
    {
        if (value is not null)
        {
            RequireIdentifier(value, label);
        }
    }

    private static void RequireCanonical(string? value, IReadOnlySet<string> allowed, string label)
    {
        if (value is null || !allowed.Contains(value))
        {
            throw Invalid($"Unsupported {label}: {value}.");
        }
    }

    private static void RequirePositiveVersion(long version, string label)
    {
        if (version < 1)
        {
            throw Invalid($"{label} must be positive.");
        }
    }

    private static void RequireVersionNotAhead(long value, long authority, string label)
    {
        if (value > authority)
        {
            throw Invalid($"{label} cannot exceed its current authority version.");
        }
    }

    private static void RequireSha256(string? value, string label)
    {
        if (value is null
            || value.Length != 64
            || value.Any(static character => !(character is >= '0' and <= '9' or >= 'a' and <= 'f')))
        {
            throw Invalid($"{label} must contain a canonical lowercase SHA-256 digest, never a raw secret.");
        }
    }

    private static void RequireOptionalSha256(string? value, string label)
    {
        if (value is not null)
        {
            RequireSha256(value, label);
        }
    }

    private static void ValidateCreatedUpdated(DateTimeOffset createdAtUtc, DateTimeOffset updatedAtUtc, string label)
    {
        RequireUtc(createdAtUtc, $"{label} createdAtUtc");
        RequireUtc(updatedAtUtc, $"{label} updatedAtUtc");
        if (updatedAtUtc < createdAtUtc)
        {
            throw Invalid($"{label} updatedAtUtc cannot precede createdAtUtc.");
        }
    }

    private static void RequireExpiry(DateTimeOffset createdAtUtc, DateTimeOffset expiresAtUtc, string label)
    {
        RequireUtc(expiresAtUtc, $"{label} expiresAtUtc");
        if (expiresAtUtc <= createdAtUtc)
        {
            throw Invalid($"{label} expiresAtUtc must follow creation or issuance.");
        }
    }

    private static void RequireLifecycleTimestamp(
        DateTimeOffset? value,
        DateTimeOffset createdAtUtc,
        DateTimeOffset updatedAtUtc,
        string label)
    {
        if (value is null)
        {
            throw Invalid($"{label} is required.");
        }

        RequireUtc(value.Value, label);
        if (value.Value < createdAtUtc || value.Value > updatedAtUtc)
        {
            throw Invalid($"{label} must fall between creation and last update.");
        }
    }

    private static void RequireUtc(DateTimeOffset value, string label)
    {
        if (value.Offset != TimeSpan.Zero || value < DateTimeOffset.UnixEpoch)
        {
            throw Invalid($"{label} must be a non-default UTC timestamp.");
        }
    }

    private static void RequireNull(DateTimeOffset? value, string label)
    {
        if (value is not null)
        {
            throw Invalid($"{label} must be null.");
        }
    }

    private static bool Same(string? left, string? right)
        => !string.IsNullOrWhiteSpace(left)
            && !string.IsNullOrWhiteSpace(right)
            && string.Equals(left, right, StringComparison.OrdinalIgnoreCase);

    private static JsonException Invalid(string message)
        => new($"Invalid persisted Play authorization record: {message}");
}
