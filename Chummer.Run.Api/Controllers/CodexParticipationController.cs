using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Ledger;
using Chummer.Run.Contracts.Leaderboards;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/participation/codex")]
public sealed class CodexParticipationController : Controller
{
    private const string DefaultProjectId = "fleet";
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly LeaderboardService _leaderboards;
    private readonly BoostSessionService _sessions;
    private readonly IdentityLinkService _links;
    private readonly UserExperienceService _experience;
    private readonly HubPageChromeService _chrome;
    private readonly IConfiguration _configuration;

    public CodexParticipationController(
        AccountService accounts,
        HubIdentityClient identity,
        LeaderboardService leaderboards,
        BoostSessionService sessions,
        IdentityLinkService links,
        UserExperienceService experience,
        HubPageChromeService chrome,
        IConfiguration configuration)
    {
        _accounts = accounts;
        _identity = identity;
        _leaderboards = leaderboards;
        _sessions = sessions;
        _links = links;
        _experience = experience;
        _chrome = chrome;
        _configuration = configuration;
    }

    [HttpGet("/participate/codex")]
    [Produces("text/html")]
    public async Task<IActionResult> ParticipationPage(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var model = new ParticipationConsolePageViewModel(
                Chrome: _chrome.BuildAuthenticatedChrome("Participate", "Start contributing from one signed-in surface, authorize in ChatGPT, then leave with a clean status and account trail.", "/participate/codex", user.DisplayName),
                User: user,
                Links: _links.GetSummary(subject.SubjectId),
                Experience: _experience.GetOrCreate(subject.SubjectId));
            return View("~/Views/CodexParticipation/Console.cshtml", model);
        }
        catch (HubRequestAuthException)
        {
            return Redirect("/login?next=/participate/codex");
        }
    }

    [HttpGet("contributions/current")]
    [HttpGet("/api/v1/participation/contributions/current")]
    public async Task<ActionResult<object>> GetCurrentContribution(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = _sessions.FindMostRelevantForUser(subject.SubjectId);
            if (session is null)
            {
                return Ok(BuildContributionEnvelope(null));
            }

            var refreshed = await _sessions.RefreshAsync(session.SponsorSessionId, cancellationToken);
            return Ok(BuildContributionEnvelope(
                refreshed.Session,
                refreshed.Fleet,
                _sessions.ListBadgesForSessionUser(refreshed.Session.SponsorSessionId)));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
    }

    [HttpPost("contributions/start")]
    [HttpPost("/api/v1/participation/contributions/start")]
    public async Task<ActionResult<object>> StartContribution(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var started = await _sessions.StartContributionAsync(
                new CreateSponsorSessionRequest(
                    SubjectId: subject.SubjectId,
                    ProjectId: _configuration["CHUMMER_PARTICIPATION_DEFAULT_PROJECT_ID"] ?? DefaultProjectId,
                    SubjectLabel: subject.DisplayName,
                    GroupId: null,
                    Visibility: "group",
                    RequestedLaneType: "participant_burst",
                    RequestedLaneRole: "coding",
                    AuthorizationTier: null,
                    TierSource: null),
                cancellationToken);
            return Ok(BuildContributionEnvelope(
                started.Session,
                started.Fleet,
                _sessions.ListBadgesForSessionUser(started.Session.SponsorSessionId)));
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

    [HttpGet("contributions/{contributionId}")]
    [HttpGet("/api/v1/participation/contributions/{contributionId}")]
    public async Task<ActionResult<object>> GetContribution([FromRoute] string contributionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(contributionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var refreshed = await _sessions.RefreshAsync(contributionId, cancellationToken);
            return Ok(BuildContributionEnvelope(
                refreshed.Session,
                refreshed.Fleet,
                _sessions.ListBadgesForSessionUser(refreshed.Session.SponsorSessionId)));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
    }

    [HttpPost("contributions/{contributionId}/stop")]
    [HttpPost("/api/v1/participation/contributions/{contributionId}/stop")]
    public async Task<ActionResult<object>> StopContribution([FromRoute] string contributionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(contributionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var stopped = await _sessions.StopAsync(contributionId, revoke: false, cancellationToken);
            return Ok(BuildContributionEnvelope(
                stopped.Session,
                stopped.Fleet,
                _sessions.ListBadgesForSessionUser(stopped.Session.SponsorSessionId)));
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

    [HttpPost("contributions/{contributionId}/revoke")]
    [HttpPost("/api/v1/participation/contributions/{contributionId}/revoke")]
    public async Task<ActionResult<object>> RevokeContribution([FromRoute] string contributionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(contributionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var revoked = await _sessions.StopAsync(contributionId, revoke: true, cancellationToken);
            return Ok(BuildContributionEnvelope(
                revoked.Session,
                revoked.Fleet,
                _sessions.ListBadgesForSessionUser(revoked.Session.SponsorSessionId)));
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

    [HttpPost("intents")]
    [HttpPost("/api/v1/participation/intents")]
    public async Task<ActionResult<object>> CreateIntent([FromBody] CreateCodexParticipationIntentRequest? request, CancellationToken cancellationToken)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.ProjectId))
        {
            return BadRequest("projectId is required.");
        }

        try
        {
            var subject = string.IsNullOrWhiteSpace(request.SubjectId)
                ? await _identity.RequireSubjectAsync(Request, cancellationToken)
                : await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            var session = _sessions.Create(new CreateSponsorSessionRequest(
                SubjectId: subject.SubjectId,
                ProjectId: request.ProjectId,
                GroupId: request.GroupId,
                SubjectLabel: request.SubjectLabel,
                BoostCode: request.BoostCode,
                CampaignId: request.CampaignId,
                Visibility: request.Visibility ?? "group",
                RequestedLaneType: request.RequestedLaneType ?? "participant_burst",
                RequestedLaneRole: request.RequestedLaneRole ?? "coding",
                AuthorizationTier: request.AuthorizationTier,
                TierSource: request.TierSource));
            return Ok(BuildIntentEnvelope(session, receipts: _sessions.ListReceipts(session.SponsorSessionId), badges: _sessions.ListBadgesForSessionUser(session.SponsorSessionId), recognition: _leaderboards.UserRecognitionSummary(session.UserId)));
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

    [HttpPost("intents/{intentId}/consent")]
    [HttpPost("/api/v1/participation/intents/{intentId}/consent")]
    public async Task<ActionResult<object>> RecordConsent([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var ownedSession = TryGetOwnedSession(intentId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (ownedSession is null)
            {
                return NotFound();
            }

            var session = _sessions.RecordConsent(intentId);
            return Ok(BuildIntentEnvelope(session, receipts: _sessions.ListReceipts(session.SponsorSessionId), badges: _sessions.ListBadgesForSessionUser(session.SponsorSessionId), recognition: _leaderboards.UserRecognitionSummary(session.UserId)));
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

    [HttpPost("intents/{intentId}/device-auth/start")]
    [HttpPost("/api/v1/participation/intents/{intentId}/device-auth/start")]
    public async Task<ActionResult<object>> StartDeviceAuth([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(intentId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.StartDeviceAuthAsync(intentId, cancellationToken);
            return Ok(BuildIntentEnvelope(result.Session, result.Fleet, _sessions.ListReceipts(result.Session.SponsorSessionId), _sessions.ListBadgesForSessionUser(result.Session.SponsorSessionId), _leaderboards.UserRecognitionSummary(result.Session.UserId)));
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

    [HttpPost("intents/{intentId}/activate")]
    [HttpPost("/api/v1/participation/intents/{intentId}/activate")]
    public async Task<ActionResult<object>> ActivateLane([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(intentId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.ActivateAsync(intentId, cancellationToken);
            return Ok(BuildIntentEnvelope(result.Session, result.Fleet, _sessions.ListReceipts(result.Session.SponsorSessionId), _sessions.ListBadgesForSessionUser(result.Session.SponsorSessionId), _leaderboards.UserRecognitionSummary(result.Session.UserId)));
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

    [HttpGet("intents/{intentId}")]
    [HttpGet("/api/v1/participation/intents/{intentId}")]
    public async Task<ActionResult<object>> GetIntent([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(intentId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var refreshed = await _sessions.RefreshAsync(intentId, cancellationToken);
            return Ok(BuildIntentEnvelope(refreshed.Session, refreshed.Fleet, _sessions.ListReceipts(intentId), _sessions.ListBadgesForSessionUser(intentId), _leaderboards.UserRecognitionSummary(refreshed.Session.UserId)));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
    }

    [HttpGet("intents/{intentId}/events")]
    [HttpGet("/api/v1/participation/intents/{intentId}/events")]
    public async Task<ActionResult<object>> GetEvents([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(intentId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var refreshed = await _sessions.RefreshAsync(intentId, cancellationToken);
            return Ok(new
            {
                intentId = refreshed.Session.SponsorSessionId,
                sponsorSessionId = refreshed.Session.SponsorSessionId,
                events = refreshed.Session.Events,
                fleet = refreshed.Fleet,
                receipts = _sessions.ListReceipts(intentId),
                badges = _sessions.ListBadgesForSessionUser(intentId)
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
    }

    [HttpPost("intents/{intentId}/stop")]
    [HttpPost("/api/v1/participation/intents/{intentId}/stop")]
    public async Task<ActionResult<object>> StopIntent([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(intentId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.StopAsync(intentId, revoke: false, cancellationToken);
            return Ok(BuildIntentEnvelope(result.Session, result.Fleet, _sessions.ListReceipts(result.Session.SponsorSessionId), _sessions.ListBadgesForSessionUser(result.Session.SponsorSessionId), _leaderboards.UserRecognitionSummary(result.Session.UserId)));
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

    [HttpDelete("intents/{intentId}")]
    [HttpDelete("/api/v1/participation/intents/{intentId}")]
    public async Task<ActionResult<object>> DeleteIntent([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(intentId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.StopAsync(intentId, revoke: true, cancellationToken);
            return Ok(BuildIntentEnvelope(result.Session, result.Fleet, _sessions.ListReceipts(result.Session.SponsorSessionId), _sessions.ListBadgesForSessionUser(result.Session.SponsorSessionId), _leaderboards.UserRecognitionSummary(result.Session.UserId)));
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

    // Keep the public participation surface on the canonical sponsor-session/community-ledger path.
    private static object BuildIntentEnvelope(
        SponsorSessionStatusDto session,
        JsonObject? fleet = null,
        IReadOnlyList<ContributionReceiptDto>? receipts = null,
        IReadOnlyList<BadgeDto>? badges = null,
        UserRecognitionSummaryDto? recognition = null)
        => new
        {
            intent = new
            {
                intentId = session.SponsorSessionId,
                sponsorSessionId = session.SponsorSessionId,
                userId = session.UserId,
                groupId = session.GroupId,
                projectId = session.ProjectId,
                requestedLaneType = session.RequestedLaneType,
                requestedLaneRole = session.RequestedLaneRole,
                visibility = session.Visibility,
                status = session.Status,
                consented = session.Consented,
                fleetLaneId = session.FleetLaneId,
                boostCampaignId = session.BoostCampaignId,
                boostCodeId = session.BoostCodeId,
                authorizationTier = session.AuthorizationTier,
                tierSource = session.TierSource,
                deviceAuthVerificationUri = session.DeviceAuthVerificationUri,
                deviceAuthUserCode = session.DeviceAuthUserCode,
                createdAtUtc = session.CreatedAtUtc,
                updatedAtUtc = session.UpdatedAtUtc,
                consentedAtUtc = session.ConsentedAtUtc,
                authorizedAtUtc = session.AuthorizedAtUtc,
                stoppedAtUtc = session.StoppedAtUtc,
                events = session.Events
            },
            sponsorSession = session,
            fleet,
            receipts = receipts ?? Array.Empty<ContributionReceiptDto>(),
            badges = badges ?? Array.Empty<BadgeDto>(),
            recognition
        };

    private static object BuildContributionEnvelope(
        SponsorSessionStatusDto? session,
        JsonObject? fleet = null,
        IReadOnlyList<BadgeDto>? badges = null)
    {
        if (session is null)
        {
            return new
            {
                contribution = (object?)null,
                status = "ready_to_start",
                phase = "start",
                heading = "Start contributing",
                support = "Authorize a temporary Codex contribution lane in ChatGPT. Chummer uses it only for bounded project work, and final landing still goes through review.",
                statusLine = "You can stop or revoke this later from your account.",
                auth = new
                {
                    verificationUri = (string?)null,
                    userCode = (string?)null,
                    pollAfterMs = 3000
                },
                badge = (object?)null,
                details = (object?)null,
                actions = new
                {
                    explainHref = "/participate",
                    homeHref = "/home",
                    accountHref = "/account"
                }
            };
        }

        var phase = ResolveContributionPhase(session);
        var activeBadge = badges?
            .FirstOrDefault(badge =>
                string.Equals(badge.Key, "contributor-ready", StringComparison.OrdinalIgnoreCase)
                && string.Equals(badge.Status, "active", StringComparison.OrdinalIgnoreCase));

        return new
        {
            contribution = new
            {
                contributionId = session.SponsorSessionId,
                sponsorSessionId = session.SponsorSessionId,
                phase,
                status = session.Status,
                authReady = session.AuthorizedAtUtc is not null,
                createdAtUtc = session.CreatedAtUtc,
                updatedAtUtc = session.UpdatedAtUtc
            },
            status = session.Status,
            phase,
            heading = ResolveContributionHeading(phase),
            support = ResolveContributionSupport(phase),
            statusLine = ResolveContributionStatusLine(session),
            auth = new
            {
                verificationUri = session.DeviceAuthVerificationUri,
                userCode = session.DeviceAuthUserCode,
                pollAfterMs = 3000
            },
            badge = activeBadge is null
                ? null
                : new
                {
                    key = activeBadge.Key,
                    label = activeBadge.Label,
                    note = "This is a thank-you marker only. Contribution credit appears later after validated work."
                },
            details = new
            {
                contributionId = session.SponsorSessionId,
                fleetLaneId = session.FleetLaneId,
                authStatus = session.Status,
                authReadyAtUtc = session.AuthorizedAtUtc,
                authorizationTier = session.AuthorizationTier,
                requestedLaneRole = session.RequestedLaneRole,
                projectId = session.ProjectId
            },
            actions = new
            {
                explainHref = "/participate",
                homeHref = "/home",
                accountHref = "/account"
            },
            fleet
        };
    }

    private static string ResolveContributionPhase(SponsorSessionStatusDto session)
        => session.Status switch
        {
            "active" => "complete",
            "stopped" => "start",
            "revoked" => "start",
            _ => "authorize"
        };

    private static string ResolveContributionHeading(string phase)
        => phase switch
        {
            "complete" => "Thanks, you're set",
            "authorize" => "Authorize in ChatGPT",
            _ => "Start contributing"
        };

    private static string ResolveContributionSupport(string phase)
        => phase switch
        {
            "complete" => "Your contribution lane is linked. Chummer will only count receipt-backed work after validation and review.",
            "authorize" => "Open the authorization page, enter the one-time code, and keep this page open while Chummer watches for confirmation.",
            _ => "Authorize a temporary Codex contribution lane in ChatGPT. Chummer uses it only for bounded project work, and final landing still goes through review."
        };

    private static string ResolveContributionStatusLine(SponsorSessionStatusDto session)
        => session.Status switch
        {
            "lane_pending" => "Authorization is confirmed. Chummer is finishing lane setup.",
            "active" => "You can leave this page now. Stop or revoke later from your account or technical details.",
            "waiting_for_slot" => "Authorization is complete. Fleet is waiting for the next available contribution slot.",
            "stopped" => "This contribution lane has been stopped. You can start again whenever you want.",
            "revoked" => "This contribution lane has been revoked. Start a new one if you want to contribute again.",
            _ => "Waiting for confirmation from ChatGPT..."
        };

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
}

public sealed record CreateCodexParticipationIntentRequest(
    string? SubjectId,
    string? SubjectLabel,
    string ProjectId,
    string? GroupId = null,
    string? BoostCode = null,
    string? CampaignId = null,
    string? Visibility = null,
    string? RequestedLaneType = null,
    string? RequestedLaneRole = null,
    string? AuthorizationTier = null,
    string? TierSource = null);
