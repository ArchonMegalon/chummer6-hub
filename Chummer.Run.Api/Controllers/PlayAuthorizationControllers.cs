using System.ComponentModel.DataAnnotations;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

public sealed record CreatePlaySessionRequest(
    [param: Required, StringLength(128, MinimumLength = 1)] string SessionId,
    [param: Required, StringLength(128, MinimumLength = 1)] string CampaignId,
    [param: Required, StringLength(128, MinimumLength = 1)] string RunId,
    [param: Required, StringLength(128, MinimumLength = 1)] string GroupId);

public sealed record AddPlayParticipantRequest(
    [param: Required, StringLength(128, MinimumLength = 1)] string TargetUserId,
    [param: Required, StringLength(32, MinimumLength = 1)] string Role);

public sealed record IssuePlayInviteRequest(
    [param: Required, StringLength(128, MinimumLength = 1)] string TargetUserId,
    [param: Required, StringLength(32, MinimumLength = 1)] string Role,
    [param: Range(60, 900)] int? LifetimeSeconds = null);

public sealed record RedeemPlayInviteRequest(
    [param: Required, StringLength(128, MinimumLength = 1)] string SessionId,
    [param: Required, StringLength(128, MinimumLength = 40)] string Secret,
    [param: Required, StringLength(32, MinimumLength = 1)] string Role,
    [param: Required, StringLength(64, MinimumLength = 64)] string DeviceThumbprint,
    [param: Range(10, 120)] int? ExchangeLifetimeSeconds = null);

public sealed record ConsumePlayExchangeRequest(
    [param: Required, StringLength(128, MinimumLength = 1)] string SessionId,
    [param: Required, StringLength(128, MinimumLength = 1)] string UserId,
    [param: Required, StringLength(32, MinimumLength = 1)] string Role,
    [param: Required, StringLength(128, MinimumLength = 40)] string Secret,
    [param: Required, StringLength(64, MinimumLength = 64)] string DeviceThumbprint,
    [param: Range(30, 600)] int? GrantLifetimeSeconds = null,
    [param: Range(30, 43200)] int? RefreshWindowSeconds = null);

public sealed record IntrospectPlayGrantRequest(
    [param: Required, StringLength(128, MinimumLength = 1)] string SessionId,
    [param: Required, StringLength(128, MinimumLength = 1)] string UserId,
    [param: Required, StringLength(32, MinimumLength = 1)] string Role,
    [param: Required, StringLength(128, MinimumLength = 40)] string Secret,
    [param: Required, StringLength(64, MinimumLength = 64)] string DeviceThumbprint);

public sealed record RefreshPlayGrantRequest(
    [param: Required, StringLength(128, MinimumLength = 1)] string SessionId,
    [param: Required, StringLength(128, MinimumLength = 1)] string UserId,
    [param: Required, StringLength(32, MinimumLength = 1)] string Role,
    [param: Required, StringLength(128, MinimumLength = 40)] string Secret,
    [param: Required, StringLength(64, MinimumLength = 64)] string DeviceThumbprint,
    [param: Range(30, 600)] int? LifetimeSeconds = null);

public sealed record PlaySessionResponse(
    string SessionId,
    string CampaignId,
    string RunId,
    string GroupId,
    string Status,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? ClosedAtUtc);

public sealed record PlayParticipantResponse(
    string ParticipantId,
    string SessionId,
    string UserId,
    string Role,
    string Status,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? RevokedAtUtc);

public sealed record PlaySessionCreatedResponse(
    PlaySessionResponse Session,
    PlayParticipantResponse GameMasterParticipant);

public sealed record PlayInviteIssuedResponse(
    string InviteId,
    string SessionId,
    string? TargetUserId,
    string RequestedRole,
    string Status,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    string Secret);

public sealed record PlayExchangeIssuedResponse(
    string ExchangeId,
    string SessionId,
    string UserId,
    string Role,
    string Status,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    string Secret);

public sealed record PlayGrantIssuedResponse(
    string GrantId,
    string SessionId,
    string UserId,
    string Role,
    string Status,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    DateTimeOffset RefreshUntilUtc,
    string Secret);

public sealed record PlayGrantResponse(
    string GrantId,
    string SessionId,
    string UserId,
    string Role,
    string Status,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    DateTimeOffset RefreshUntilUtc,
    DateTimeOffset? RevokedAtUtc);

[ApiController]
[AutoValidateAntiforgeryToken]
[Route("api/v1/accounts/me/play")]
[RequestSizeLimit(MaxRequestBodyBytes)]
public sealed class PlayAuthorizationAccountController : ControllerBase
{
    private const int MaxRequestBodyBytes = 16 * 1024;
    private const string IdempotencyKeyHeader = "Idempotency-Key";

    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly PlaySessionAuthorizationService _authorization;
    private readonly PlayAuthorizationIdempotencyCoordinator _idempotency;
    private readonly ILogger<PlayAuthorizationAccountController> _logger;

    public PlayAuthorizationAccountController(
        HubIdentityClient identity,
        AccountService accounts,
        PlaySessionAuthorizationService authorization,
        PlayAuthorizationIdempotencyCoordinator idempotency,
        ILogger<PlayAuthorizationAccountController> logger)
    {
        _identity = identity;
        _accounts = accounts;
        _authorization = authorization;
        _idempotency = idempotency;
        _logger = logger;
    }

    [HttpPost("sessions")]
    [ProducesResponseType<PlaySessionCreatedResponse>(StatusCodes.Status201Created)]
    public async Task<IActionResult> CreateSession(
        [FromBody] CreatePlaySessionRequest request,
        CancellationToken cancellationToken)
    {
        (string? actorUserId, IActionResult? failure) = await ResolveActorAsync(cancellationToken);
        if (failure is not null)
        {
            return failure;
        }

        return await ExecuteMutationAsync(
            actorUserId!,
            "create_session",
            PlayAuthorizationIdempotencyCoordinator.Fingerprint(
                request.SessionId,
                request.CampaignId,
                request.RunId,
                request.GroupId),
            () => Complete(
                "create_session",
                _authorization.CreateSessionBinding(
                    request.SessionId,
                    request.CampaignId,
                    request.RunId,
                    request.GroupId,
                    actorUserId!),
                value => new PlaySessionCreatedResponse(
                    Project(value.Session),
                    Project(value.GameMasterParticipant)),
                StatusCodes.Status201Created));
    }

    [HttpPost("sessions/{sessionId}/participants")]
    [ProducesResponseType<PlayParticipantResponse>(StatusCodes.Status201Created)]
    public async Task<IActionResult> AddParticipant(
        [FromRoute] string sessionId,
        [FromBody] AddPlayParticipantRequest request,
        CancellationToken cancellationToken)
    {
        (string? actorUserId, IActionResult? failure) = await ResolveActorAsync(cancellationToken);
        if (failure is not null)
        {
            return failure;
        }

        return await ExecuteMutationAsync(
            actorUserId!,
            "add_participant",
            PlayAuthorizationIdempotencyCoordinator.Fingerprint(
                sessionId,
                request.TargetUserId,
                request.Role),
            () => Complete(
                "add_participant",
                _authorization.AddParticipant(sessionId, actorUserId!, request.TargetUserId, request.Role),
                Project,
                StatusCodes.Status201Created));
    }

    [HttpPost("sessions/{sessionId}/invites")]
    [ProducesResponseType<PlayInviteIssuedResponse>(StatusCodes.Status201Created)]
    public async Task<IActionResult> IssueInvite(
        [FromRoute] string sessionId,
        [FromBody] IssuePlayInviteRequest request,
        CancellationToken cancellationToken)
    {
        (string? actorUserId, IActionResult? failure) = await ResolveActorAsync(cancellationToken);
        if (failure is not null)
        {
            return failure;
        }

        return await ExecuteMutationAsync(
            actorUserId!,
            "issue_invite",
            PlayAuthorizationIdempotencyCoordinator.Fingerprint(
                sessionId,
                request.TargetUserId,
                request.Role,
                request.LifetimeSeconds?.ToString()),
            () => Complete(
                "issue_invite",
                _authorization.IssueInvite(
                    sessionId,
                    actorUserId!,
                    request.TargetUserId,
                    request.Role,
                    Seconds(request.LifetimeSeconds)),
                value => new PlayInviteIssuedResponse(
                    value.Invite.InviteId,
                    value.Invite.SessionId,
                    value.Invite.TargetUserId,
                    value.Invite.RequestedRole,
                    value.Invite.Status,
                    value.Invite.CreatedAtUtc,
                    value.Invite.ExpiresAtUtc,
                    value.Secret),
                StatusCodes.Status201Created));
    }

    [HttpPost("invites/{inviteId}/redeem")]
    [ProducesResponseType<PlayExchangeIssuedResponse>(StatusCodes.Status201Created)]
    public async Task<IActionResult> RedeemInvite(
        [FromRoute] string inviteId,
        [FromBody] RedeemPlayInviteRequest request,
        CancellationToken cancellationToken)
    {
        (string? actorUserId, IActionResult? failure) = await ResolveActorAsync(cancellationToken);
        if (failure is not null)
        {
            return failure;
        }

        return await ExecuteMutationAsync(
            actorUserId!,
            "redeem_invite",
            PlayAuthorizationIdempotencyCoordinator.Fingerprint(
                inviteId,
                request.SessionId,
                request.Secret,
                request.Role,
                request.DeviceThumbprint,
                request.ExchangeLifetimeSeconds?.ToString()),
            () => Complete(
                "redeem_invite",
                _authorization.RedeemInvite(
                    inviteId,
                    request.Secret,
                    request.SessionId,
                    actorUserId!,
                    request.Role,
                    request.DeviceThumbprint,
                    Seconds(request.ExchangeLifetimeSeconds)),
                value => new PlayExchangeIssuedResponse(
                    value.Exchange.ExchangeId,
                    value.Exchange.SessionId!,
                    value.Exchange.UserId!,
                    value.Exchange.Role!,
                    value.Exchange.Status,
                    value.Exchange.CreatedAtUtc,
                    value.Exchange.ExpiresAtUtc,
                    value.Secret),
                StatusCodes.Status201Created));
    }

    [HttpDelete("sessions/{sessionId}/grants/{grantId}")]
    [ProducesResponseType<PlayGrantResponse>(StatusCodes.Status200OK)]
    public async Task<IActionResult> RevokeGrant(
        [FromRoute] string sessionId,
        [FromRoute] string grantId,
        CancellationToken cancellationToken)
    {
        (string? actorUserId, IActionResult? failure) = await ResolveActorAsync(cancellationToken);
        if (failure is not null)
        {
            return failure;
        }

        return await ExecuteMutationAsync(
            actorUserId!,
            "revoke_grant",
            PlayAuthorizationIdempotencyCoordinator.Fingerprint(sessionId, grantId),
            () => Complete(
                "revoke_grant",
                _authorization.RevokeGrant(grantId, sessionId, actorUserId!),
                Project,
                StatusCodes.Status200OK));
    }

    [HttpDelete("participants/{participantId}")]
    [ProducesResponseType<PlayParticipantResponse>(StatusCodes.Status200OK)]
    public async Task<IActionResult> RevokeParticipant(
        [FromRoute] string participantId,
        CancellationToken cancellationToken)
    {
        (string? actorUserId, IActionResult? failure) = await ResolveActorAsync(cancellationToken);
        if (failure is not null)
        {
            return failure;
        }

        return await ExecuteMutationAsync(
            actorUserId!,
            "revoke_participant",
            PlayAuthorizationIdempotencyCoordinator.Fingerprint(participantId),
            () => Complete(
                "revoke_participant",
                _authorization.RevokeParticipant(participantId, actorUserId!),
                Project,
                StatusCodes.Status200OK));
    }

    [HttpPost("sessions/{sessionId}/authorization-version")]
    [ProducesResponseType<PlaySessionResponse>(StatusCodes.Status200OK)]
    public async Task<IActionResult> BumpSessionAuthorizationVersion(
        [FromRoute] string sessionId,
        CancellationToken cancellationToken)
    {
        (string? actorUserId, IActionResult? failure) = await ResolveActorAsync(cancellationToken);
        if (failure is not null)
        {
            return failure;
        }

        return await ExecuteMutationAsync(
            actorUserId!,
            "bump_session_authorization",
            PlayAuthorizationIdempotencyCoordinator.Fingerprint(sessionId),
            () => Complete(
                "bump_session_authorization",
                _authorization.BumpSessionAuthorizationVersion(sessionId, actorUserId!),
                Project,
                StatusCodes.Status200OK));
    }

    [HttpPost("participants/{participantId}/authorization-version")]
    [ProducesResponseType<PlayParticipantResponse>(StatusCodes.Status200OK)]
    public async Task<IActionResult> BumpParticipantAuthorizationVersion(
        [FromRoute] string participantId,
        CancellationToken cancellationToken)
    {
        (string? actorUserId, IActionResult? failure) = await ResolveActorAsync(cancellationToken);
        if (failure is not null)
        {
            return failure;
        }

        return await ExecuteMutationAsync(
            actorUserId!,
            "bump_participant_authorization",
            PlayAuthorizationIdempotencyCoordinator.Fingerprint(participantId),
            () => Complete(
                "bump_participant_authorization",
                _authorization.BumpParticipantAuthorizationVersion(participantId, actorUserId!),
                Project,
                StatusCodes.Status200OK));
    }

    [HttpPost("sessions/{sessionId}/close")]
    [ProducesResponseType<PlaySessionResponse>(StatusCodes.Status200OK)]
    public async Task<IActionResult> CloseSession(
        [FromRoute] string sessionId,
        CancellationToken cancellationToken)
    {
        (string? actorUserId, IActionResult? failure) = await ResolveActorAsync(cancellationToken);
        if (failure is not null)
        {
            return failure;
        }

        return await ExecuteMutationAsync(
            actorUserId!,
            "close_session",
            PlayAuthorizationIdempotencyCoordinator.Fingerprint(sessionId),
            () => Complete(
                "close_session",
                _authorization.CloseSession(sessionId, actorUserId!),
                Project,
                StatusCodes.Status200OK));
    }

    private async Task<(string? UserId, IActionResult? Failure)> ResolveActorAsync(
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return (user.UserId, null);
        }
        catch (HubRequestAuthException exception)
        {
            int status = exception.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden
                ? exception.StatusCode
                : StatusCodes.Status401Unauthorized;
            return (null, StatusCode(status, Problem(
                status,
                "Hub authentication is required.",
                "https://chummer.run/problems/play-authentication")));
        }
    }

    private async Task<IActionResult> ExecuteMutationAsync(
        string actorUserId,
        string operation,
        string fingerprint,
        Func<PlayAuthorizationHttpEnvelope> action)
    {
        if (!Request.Headers.TryGetValue(IdempotencyKeyHeader, out var values)
            || values.Count != 1
            || !PlayAuthorizationIdempotencyCoordinator.ValidKey(values[0]))
        {
            return BadRequest(Problem(
                StatusCodes.Status400BadRequest,
                "A valid Idempotency-Key header is required.",
                "https://chummer.run/problems/play-idempotency"));
        }

        PlayAuthorizationIdempotencyOutcome outcome = await _idempotency.ExecuteAsync(
            $"account:{actorUserId}:{operation}",
            values[0]!,
            fingerprint,
            () => Task.FromResult(action()));
        if (outcome.FingerprintConflict)
        {
            return Conflict(Problem(
                StatusCodes.Status409Conflict,
                "The idempotency key was already used for a different request.",
                "https://chummer.run/problems/play-idempotency-conflict"));
        }

        if (outcome.CapacityExceeded)
        {
            return StatusCode(
                StatusCodes.Status503ServiceUnavailable,
                Problem(
                    StatusCodes.Status503ServiceUnavailable,
                    "The Play authorization retry window is temporarily full.",
                    "https://chummer.run/problems/play-idempotency-capacity"));
        }

        return Envelope(outcome.Response!);
    }

    private PlayAuthorizationHttpEnvelope Complete<T>(
        string operation,
        PlaySessionAuthorizationResult<T> result,
        Func<T, object> projector,
        int successStatus)
        where T : class
    {
        _logger.LogInformation(
            "Play authorization operation {Operation} completed with {Reason}; trace {TraceId}.",
            operation,
            result.Reason,
            HttpContext.TraceIdentifier);
        return PlayAuthorizationHttpProjection.Project(result, projector, successStatus);
    }

    private IActionResult Envelope(PlayAuthorizationHttpEnvelope response)
        => response.Body is null
            ? StatusCode(response.StatusCode)
            : StatusCode(response.StatusCode, response.Body);

    private static TimeSpan? Seconds(int? value)
        => value.HasValue ? TimeSpan.FromSeconds(value.Value) : null;

    private static ProblemDetails Problem(int status, string title, string type)
        => new() { Status = status, Title = title, Type = type };

    private static PlaySessionResponse Project(PlaySessionBinding value)
        => PlayAuthorizationHttpProjection.Session(value);

    private static PlayParticipantResponse Project(PlaySessionParticipant value)
        => PlayAuthorizationHttpProjection.Participant(value);

    private static PlayGrantResponse Project(PlaySessionGrant value)
        => PlayAuthorizationHttpProjection.Grant(value);
}

[ApiController]
[IgnoreAntiforgeryToken]
[Route("api/internal/play")]
[RequestSizeLimit(MaxRequestBodyBytes)]
public sealed class PlayAuthorizationInternalController : ControllerBase
{
    private const int MaxRequestBodyBytes = 16 * 1024;
    private const string IdempotencyKeyHeader = "Idempotency-Key";

    private readonly PlayAuthorizationApiPolicy _policy;
    private readonly PlaySessionAuthorizationService _authorization;
    private readonly PlayAuthorizationIdempotencyCoordinator _idempotency;
    private readonly ILogger<PlayAuthorizationInternalController> _logger;

    public PlayAuthorizationInternalController(
        PlayAuthorizationApiPolicy policy,
        PlaySessionAuthorizationService authorization,
        PlayAuthorizationIdempotencyCoordinator idempotency,
        ILogger<PlayAuthorizationInternalController> logger)
    {
        _policy = policy;
        _authorization = authorization;
        _idempotency = idempotency;
        _logger = logger;
    }

    [HttpPost("exchanges/{exchangeId}/consume")]
    [ProducesResponseType<PlayGrantIssuedResponse>(StatusCodes.Status201Created)]
    public Task<IActionResult> ConsumeExchange(
        [FromRoute] string exchangeId,
        [FromBody] ConsumePlayExchangeRequest request)
        => ExecuteMutationAsync(
            "consume_exchange",
            PlayAuthorizationIdempotencyCoordinator.Fingerprint(
                exchangeId,
                request.SessionId,
                request.UserId,
                request.Role,
                request.Secret,
                request.DeviceThumbprint,
                request.GrantLifetimeSeconds?.ToString(),
                request.RefreshWindowSeconds?.ToString()),
            () => Complete(
                "consume_exchange",
                _authorization.ConsumeExchange(
                    exchangeId,
                    request.Secret,
                    request.SessionId,
                    request.UserId,
                    request.Role,
                    request.DeviceThumbprint,
                    Seconds(request.GrantLifetimeSeconds),
                    Seconds(request.RefreshWindowSeconds)),
                value => new PlayGrantIssuedResponse(
                    value.Grant.GrantId,
                    value.Grant.SessionId,
                    value.Grant.UserId,
                    value.Grant.Role,
                    value.Grant.Status,
                    value.Grant.IssuedAtUtc,
                    value.Grant.ExpiresAtUtc,
                    value.Grant.RefreshUntilUtc,
                    value.Secret),
                StatusCodes.Status201Created));

    [HttpPost("grants/{grantId}/introspect")]
    [ProducesResponseType<PlayGrantResponse>(StatusCodes.Status200OK)]
    public IActionResult IntrospectGrant(
        [FromRoute] string grantId,
        [FromBody] IntrospectPlayGrantRequest request)
    {
        if (!_policy.IsInternalRequestAuthorized(Request))
        {
            return Unauthorized();
        }

        PlayAuthorizationHttpEnvelope response = Complete(
            "introspect_grant",
            _authorization.IntrospectGrant(
                grantId,
                request.Secret,
                request.SessionId,
                request.UserId,
                request.Role,
                request.DeviceThumbprint),
            value => PlayAuthorizationHttpProjection.Grant(value.Grant),
            StatusCodes.Status200OK);
        return Envelope(response);
    }

    [HttpPost("grants/{grantId}/refresh")]
    [ProducesResponseType<PlayGrantIssuedResponse>(StatusCodes.Status200OK)]
    public Task<IActionResult> RefreshGrant(
        [FromRoute] string grantId,
        [FromBody] RefreshPlayGrantRequest request)
        => ExecuteMutationAsync(
            "refresh_grant",
            PlayAuthorizationIdempotencyCoordinator.Fingerprint(
                grantId,
                request.SessionId,
                request.UserId,
                request.Role,
                request.Secret,
                request.DeviceThumbprint,
                request.LifetimeSeconds?.ToString()),
            () => Complete(
                "refresh_grant",
                _authorization.RefreshGrant(
                    grantId,
                    request.Secret,
                    request.SessionId,
                    request.UserId,
                    request.Role,
                    request.DeviceThumbprint,
                    Seconds(request.LifetimeSeconds)),
                value => new PlayGrantIssuedResponse(
                    value.Grant.GrantId,
                    value.Grant.SessionId,
                    value.Grant.UserId,
                    value.Grant.Role,
                    value.Grant.Status,
                    value.Grant.IssuedAtUtc,
                    value.Grant.ExpiresAtUtc,
                    value.Grant.RefreshUntilUtc,
                    value.Secret),
                StatusCodes.Status200OK));

    private async Task<IActionResult> ExecuteMutationAsync(
        string operation,
        string fingerprint,
        Func<PlayAuthorizationHttpEnvelope> action)
    {
        if (!_policy.IsInternalRequestAuthorized(Request))
        {
            return Unauthorized();
        }

        if (!Request.Headers.TryGetValue(IdempotencyKeyHeader, out var values)
            || values.Count != 1
            || !PlayAuthorizationIdempotencyCoordinator.ValidKey(values[0]))
        {
            return BadRequest(Problem(
                StatusCodes.Status400BadRequest,
                "A valid Idempotency-Key header is required.",
                "https://chummer.run/problems/play-idempotency"));
        }

        PlayAuthorizationIdempotencyOutcome outcome = await _idempotency.ExecuteAsync(
            $"internal:{operation}",
            values[0]!,
            fingerprint,
            () => Task.FromResult(action()));
        if (outcome.FingerprintConflict)
        {
            return Conflict(Problem(
                StatusCodes.Status409Conflict,
                "The idempotency key was already used for a different request.",
                "https://chummer.run/problems/play-idempotency-conflict"));
        }

        if (outcome.CapacityExceeded)
        {
            return StatusCode(
                StatusCodes.Status503ServiceUnavailable,
                Problem(
                    StatusCodes.Status503ServiceUnavailable,
                    "The Play authorization retry window is temporarily full.",
                    "https://chummer.run/problems/play-idempotency-capacity"));
        }

        return Envelope(outcome.Response!);
    }

    private PlayAuthorizationHttpEnvelope Complete<T>(
        string operation,
        PlaySessionAuthorizationResult<T> result,
        Func<T, object> projector,
        int successStatus)
        where T : class
    {
        _logger.LogInformation(
            "Internal Play authorization operation {Operation} completed with {Reason}; trace {TraceId}.",
            operation,
            result.Reason,
            HttpContext.TraceIdentifier);
        return PlayAuthorizationHttpProjection.Project(result, projector, successStatus);
    }

    private IActionResult Envelope(PlayAuthorizationHttpEnvelope response)
        => response.Body is null
            ? StatusCode(response.StatusCode)
            : StatusCode(response.StatusCode, response.Body);

    private static TimeSpan? Seconds(int? value)
        => value.HasValue ? TimeSpan.FromSeconds(value.Value) : null;

    private static ProblemDetails Problem(int status, string title, string type)
        => new() { Status = status, Title = title, Type = type };
}

internal static class PlayAuthorizationHttpProjection
{
    private static readonly HashSet<string> ExpiredReasons = new(StringComparer.Ordinal)
    {
        PlaySessionAuthorizationReasons.InviteExpired,
        PlaySessionAuthorizationReasons.ExchangeExpired,
        PlaySessionAuthorizationReasons.GrantExpired
    };

    private static readonly HashSet<string> ReplayReasons = new(StringComparer.Ordinal)
    {
        PlaySessionAuthorizationReasons.InviteReplayed,
        PlaySessionAuthorizationReasons.ExchangeReplayed
    };

    public static PlayAuthorizationHttpEnvelope Project<T>(
        PlaySessionAuthorizationResult<T> result,
        Func<T, object> projector,
        int successStatus)
        where T : class
    {
        if (result.Succeeded && result.Value is not null)
        {
            return new PlayAuthorizationHttpEnvelope(successStatus, projector(result.Value));
        }

        int status = result.Reason switch
        {
            PlaySessionAuthorizationReasons.InvalidRequest => StatusCodes.Status400BadRequest,
            PlaySessionAuthorizationReasons.PersistenceFailed => StatusCodes.Status503ServiceUnavailable,
            _ when ExpiredReasons.Contains(result.Reason) => StatusCodes.Status410Gone,
            _ when ReplayReasons.Contains(result.Reason) => StatusCodes.Status409Conflict,
            _ => StatusCodes.Status404NotFound
        };
        string title = status switch
        {
            StatusCodes.Status400BadRequest => "The Play authorization request is invalid.",
            StatusCodes.Status409Conflict => "The Play authorization capability cannot be reused.",
            StatusCodes.Status410Gone => "The Play authorization capability has expired.",
            StatusCodes.Status503ServiceUnavailable => "The Play authorization request could not be persisted.",
            _ => "The Play authorization resource is unavailable."
        };
        return new PlayAuthorizationHttpEnvelope(
            status,
            new ProblemDetails
            {
                Status = status,
                Title = title,
                Type = "https://chummer.run/problems/play-authorization"
            });
    }

    public static PlaySessionResponse Session(PlaySessionBinding value)
        => new(
            value.SessionId,
            value.CampaignId,
            value.RunId,
            value.GroupId,
            value.Status,
            value.CreatedAtUtc,
            value.UpdatedAtUtc,
            value.ClosedAtUtc);

    public static PlayParticipantResponse Participant(PlaySessionParticipant value)
        => new(
            value.ParticipantId,
            value.SessionId,
            value.UserId,
            value.Role,
            value.Status,
            value.CreatedAtUtc,
            value.UpdatedAtUtc,
            value.RevokedAtUtc);

    public static PlayGrantResponse Grant(PlaySessionGrant value)
        => new(
            value.GrantId,
            value.SessionId,
            value.UserId,
            value.Role,
            value.Status,
            value.IssuedAtUtc,
            value.ExpiresAtUtc,
            value.RefreshUntilUtc,
            value.RevokedAtUtc);
}
