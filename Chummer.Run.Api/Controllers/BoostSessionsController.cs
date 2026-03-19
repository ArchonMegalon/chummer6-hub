using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Boosters;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/boost-sessions")]
public sealed class BoostSessionsController : ControllerBase
{
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly LeaderboardService _leaderboards;
    private readonly BoostSessionService _sessions;

    public BoostSessionsController(AccountService accounts, HubIdentityClient identity, LeaderboardService leaderboards, BoostSessionService sessions)
    {
        _accounts = accounts;
        _identity = identity;
        _leaderboards = leaderboards;
        _sessions = sessions;
    }

    [HttpGet("/boost")]
    [Produces("text/html")]
    public IActionResult BoostPage() => Redirect("/participate/codex");

    [HttpPost]
    [ProducesResponseType<SponsorSessionStatusDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<SponsorSessionStatusDto>> Create([FromBody] CreateSponsorSessionRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("boost-session payload is required.");
        }

        try
        {
            var subject = string.IsNullOrWhiteSpace(request.SubjectId)
                ? await _identity.RequireSubjectAsync(Request, cancellationToken)
                : await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_sessions.Create(request with { SubjectId = subject.SubjectId }));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentException)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpGet("{sponsorSessionId}")]
    [ProducesResponseType(typeof(object), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<object>> Get([FromRoute] string sponsorSessionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(sponsorSessionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var refreshed = await _sessions.RefreshAsync(sponsorSessionId, cancellationToken);
            return Ok(BuildSessionEnvelope(refreshed.Session, refreshed.Fleet));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("{sponsorSessionId}/consent")]
    [ProducesResponseType<SponsorSessionStatusDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<SponsorSessionStatusDto>> Consent([FromRoute] string sponsorSessionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(sponsorSessionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            return Ok(_sessions.RecordConsent(sponsorSessionId));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
    }

    [HttpPost("{sponsorSessionId}/device-auth/start")]
    public async Task<ActionResult<object>> StartDeviceAuth([FromRoute] string sponsorSessionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(sponsorSessionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.StartDeviceAuthAsync(sponsorSessionId, cancellationToken);
            return Ok(BuildSessionEnvelope(result.Session, result.Fleet));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (Exception ex) when (ex is InvalidOperationException or ArgumentException)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("{sponsorSessionId}/activate")]
    public async Task<ActionResult<object>> Activate([FromRoute] string sponsorSessionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(sponsorSessionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.ActivateAsync(sponsorSessionId, cancellationToken);
            return Ok(BuildSessionEnvelope(result.Session, result.Fleet));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (Exception ex) when (ex is InvalidOperationException or ArgumentException)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("{sponsorSessionId}/stop")]
    public async Task<ActionResult<object>> Stop([FromRoute] string sponsorSessionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(sponsorSessionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.StopAsync(sponsorSessionId, revoke: false, cancellationToken);
            return Ok(BuildSessionEnvelope(result.Session, result.Fleet));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (Exception ex) when (ex is InvalidOperationException or ArgumentException)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpDelete("{sponsorSessionId}")]
    public async Task<ActionResult<object>> Revoke([FromRoute] string sponsorSessionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(sponsorSessionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.StopAsync(sponsorSessionId, revoke: true, cancellationToken);
            return Ok(BuildSessionEnvelope(result.Session, result.Fleet));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (Exception ex) when (ex is InvalidOperationException or ArgumentException)
        {
            return BadRequest(ex.Message);
        }
    }

    private SponsorSessionStatusDto? TryGetOwnedSession(string sponsorSessionId, string subjectId, out ActionResult? denied)
    {
        denied = null;
        var session = _sessions.Get(sponsorSessionId);
        if (session is null)
        {
            return null;
        }

        var user = _accounts.EnsureUser(subjectId, subjectId);
        if (!string.Equals(session.UserId, user.UserId, StringComparison.OrdinalIgnoreCase))
        {
            denied = Problem(statusCode: StatusCodes.Status403Forbidden, detail: "sponsor session does not belong to the authenticated subject.");
            return null;
        }

        return session;
    }

    private object BuildSessionEnvelope(SponsorSessionStatusDto session, JsonObject? fleet)
        => new
        {
            sponsorSession = session,
            fleet,
            receipts = _sessions.ListReceipts(session.SponsorSessionId),
            badges = _sessions.ListBadgesForSessionUser(session.SponsorSessionId),
            recognition = _leaderboards.UserRecognitionSummary(session.UserId)
        };
}
