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
[AutoValidateAntiforgeryToken]
[Route("api/v1/participation/codex")]
public sealed class CodexParticipationController : Controller
{
    private const string DefaultProjectId = "hub";
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly LeaderboardService _leaderboards;
    private readonly BoostSessionService _sessions;
    private readonly IdentityLinkService _links;
    private readonly UserExperienceService _experience;
    private readonly ParticipationOperatorNotificationService _participationNotifications;
    private readonly HubPageChromeService _chrome;
    private readonly IConfiguration _configuration;
    private readonly ILogger<CodexParticipationController> _logger;

    public CodexParticipationController(
        AccountService accounts,
        HubIdentityClient identity,
        LeaderboardService leaderboards,
        BoostSessionService sessions,
        IdentityLinkService links,
        UserExperienceService experience,
        ParticipationOperatorNotificationService participationNotifications,
        HubPageChromeService chrome,
        IConfiguration configuration,
        ILogger<CodexParticipationController> logger)
    {
        _accounts = accounts;
        _identity = identity;
        _leaderboards = leaderboards;
        _sessions = sessions;
        _links = links;
        _experience = experience;
        _participationNotifications = participationNotifications;
        _chrome = chrome;
        _configuration = configuration;
        _logger = logger;
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
                Chrome: _chrome.BuildAuthenticatedChrome("Participate", "Start contributing from one signed-in surface, authorize with your OpenAI account in ChatGPT, then leave with a clean status and account trail.", "/participate/codex", user.DisplayName, user.Email),
                User: user,
                Links: _links.GetSummary(subject.SubjectId),
                Experience: _experience.GetOrCreate(subject.SubjectId));
            return View("~/Views/CodexParticipation/Console.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect("/auth/google/start?next=%2Fparticipate%2Fcodex");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Participation page could not confirm the signed-in identity.");
            return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
                Chrome: _chrome.BuildPublicChrome("Participation unavailable", "Hub could not confirm the signed-in participation surface right now.", "/participate/codex"),
                Heading: "Participation is unavailable right now",
                SupportLine: "Chummer could not open the signed-in participation surface right now. Try again from Home or Account in a moment.",
                Notice: null,
                PrimaryLabel: "Return home",
                PrimaryHref: "/home",
                SecondaryLabel: "Open account",
                SecondaryHref: "/account"));
        }
    }

    [HttpGet("contributions/current")]
    [HttpGet("/api/v1/participation/contributions/current")]
    public async Task<ActionResult<object>> GetCurrentContribution(CancellationToken cancellationToken)
    {
        SponsorSessionStatusDto? session = null;
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            session = _sessions.FindMostRelevantForUser(subject.SubjectId);
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
        catch (ParticipationUnavailableException)
        {
            return BuildContributionUnavailableResult(session);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
    }

    [HttpPost("contributions/start")]
    [HttpPost("/api/v1/participation/contributions/start")]
    [ValidateAntiForgeryToken]
    public async Task<ActionResult<object>> StartContribution(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = null;
        SponsorSessionStatusDto? session = null;
        try
        {
            subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var started = await _sessions.StartContributionAsync(
                new CreateSponsorSessionRequest(
                    SubjectId: subject.SubjectId,
                    ProjectId: _configuration["CHUMMER_PARTICIPATION_DEFAULT_PROJECT_ID"] ?? DefaultProjectId,
                    SubjectLabel: subject.DisplayName,
                    ParticipantCodexCode: Request.HasJsonContentType() ? ExtractStartCodexCode() : null,
                    GroupId: null,
                    Visibility: "group",
                    RequestedLaneType: "participant_burst",
                    RequestedLaneRole: "coding",
                    AuthorizationTier: null,
                    TierSource: null),
                cancellationToken);
            session = started.Session;
            string authProviderFamily = ParticipationOperatorNotificationService.InferAuthProviderFamily(_links.GetSummary(subject.SubjectId));
            await _participationNotifications.NotifyFirstActionIfNeededAsync(
                _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email),
                subject.Email,
                intentKind: "guided_contribution",
                entryRoute: "/participate/codex",
                authProviderFamily,
                cancellationToken);
            return Ok(BuildContributionEnvelope(
                started.Session,
                started.Fleet,
                _sessions.ListBadgesForSessionUser(started.Session.SponsorSessionId)));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (ParticipationUnavailableException)
        {
            session ??= subject is null ? null : _sessions.FindMostRelevantForUser(subject.SubjectId);
            return BuildContributionUnavailableResult(session);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpGet("contributions/{contributionId}")]
    [HttpGet("/api/v1/participation/contributions/{contributionId}")]
    public async Task<ActionResult<object>> GetContribution([FromRoute] string contributionId, CancellationToken cancellationToken)
    {
        SponsorSessionStatusDto? session = null;
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            session = TryGetOwnedSession(contributionId, subject.SubjectId, out var denied);
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
        catch (ParticipationUnavailableException)
        {
            return BuildContributionUnavailableResult(session);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
    }

    [HttpPost("contributions/{contributionId}/stop")]
    [HttpPost("/api/v1/participation/contributions/{contributionId}/stop")]
    [ValidateAntiForgeryToken]
    public async Task<ActionResult<object>> StopContribution([FromRoute] string contributionId, CancellationToken cancellationToken)
    {
        SponsorSessionStatusDto? session = null;
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            session = TryGetOwnedSession(contributionId, subject.SubjectId, out var denied);
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
        catch (ParticipationUnavailableException)
        {
            return BuildContributionUnavailableResult(session);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpPost("contributions/{contributionId}/revoke")]
    [HttpPost("/api/v1/participation/contributions/{contributionId}/revoke")]
    [ValidateAntiForgeryToken]
    public async Task<ActionResult<object>> RevokeContribution([FromRoute] string contributionId, CancellationToken cancellationToken)
    {
        SponsorSessionStatusDto? session = null;
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            session = TryGetOwnedSession(contributionId, subject.SubjectId, out var denied);
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
        catch (ParticipationUnavailableException)
        {
            return BuildContributionUnavailableResult(session);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
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
                ParticipantCodexCode: request.ParticipantCodexCode,
                BoostCode: request.BoostCode,
                CampaignId: request.CampaignId,
                Visibility: request.Visibility ?? "group",
                RequestedLaneType: request.RequestedLaneType ?? "participant_burst",
                RequestedLaneRole: request.RequestedLaneRole ?? "coding",
                AuthorizationTier: request.AuthorizationTier,
                TierSource: request.TierSource));
            return Ok(BuildIntentEnvelope(session, receipts: _sessions.ListReceipts(session.SponsorSessionId), badges: _sessions.ListBadgesForSessionUser(session.SponsorSessionId), recognition: _leaderboards.UserRecognitionSummary(session.UserId)));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
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
        catch (ParticipationUnavailableException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
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
        catch (ParticipationUnavailableException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (Exception ex) when (ex is InvalidOperationException or ArgumentException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
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
            return CommunityApiProblemMapper.FromException(this, ex);
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
        catch (ParticipationUnavailableException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
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
                fleet = FleetProjectionSanitizer.Build(refreshed.Fleet),
                receipts = _sessions.ListReceipts(intentId),
                badges = _sessions.ListBadgesForSessionUser(intentId)
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (ParticipationUnavailableException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
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
        catch (ParticipationUnavailableException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (Exception ex) when (ex is InvalidOperationException or ArgumentException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
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
        catch (ParticipationUnavailableException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (Exception ex) when (ex is InvalidOperationException or ArgumentException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
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
                participantCodexCode = session.ParticipantCodexCode,
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
            fleet = FleetProjectionSanitizer.Build(fleet),
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
                support = "Authorize a temporary Codex contribution lane with your OpenAI account in ChatGPT. Chummer uses it only for bounded project work, and final landing still goes through review.",
                statusLine = "You can stop or revoke this later from your account.",
                auth = new
                {
                    verificationUri = (string?)null,
                    userCode = (string?)null,
                    pollAfterMs = 3000
                },
                badge = (object?)null,
                details = (object?)null,
                lifecycle = BuildContributionLifecycle(null),
                breadcrumbs = Array.Empty<object>(),
                failureGuidance = BuildContributionFailureGuidance(null, unavailable: false),
                actions = BuildContributionActions()
            };
        }

        var phase = ResolveContributionPhase(session);
        var activeBadge = badges?
            .FirstOrDefault(badge =>
                string.Equals(badge.Key, "contributor-ready", StringComparison.OrdinalIgnoreCase)
                && string.Equals(badge.Status, "active", StringComparison.OrdinalIgnoreCase));

        return new
        {
            contribution = BuildContributionSummary(session, phase),
            status = session.Status,
            phase,
            heading = ResolveContributionHeading(session, phase),
            support = ResolveContributionSupport(session, phase),
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
            details = BuildContributionDetails(session),
            lifecycle = BuildContributionLifecycle(session),
            breadcrumbs = BuildContributionBreadcrumbs(session),
            failureGuidance = BuildContributionFailureGuidance(session, unavailable: false),
            actions = BuildContributionActions(),
            fleet = FleetProjectionSanitizer.Build(fleet)
        };
    }

    private ActionResult<object> BuildContributionUnavailableResult(SponsorSessionStatusDto? session)
        => StatusCode(StatusCodes.Status503ServiceUnavailable, BuildContributionUnavailableEnvelope(session));

    private static object BuildContributionUnavailableEnvelope(SponsorSessionStatusDto? session)
        => new
        {
            contribution = BuildContributionSummary(session, "unavailable"),
            unavailable = true,
            status = session?.Status ?? "unavailable",
            phase = "unavailable",
            heading = "Participation is unavailable right now",
            support = "This host can't open or refresh contribution lanes at the moment.",
            statusLine = session is null
                ? "Try again later. Your account is still signed in and nothing was lost."
                : "Try again later. Your saved contribution record is still intact.",
            auth = new
            {
                verificationUri = session?.DeviceAuthVerificationUri,
                userCode = session?.DeviceAuthUserCode,
                pollAfterMs = 3000
            },
            badge = (object?)null,
            details = BuildContributionDetails(session),
            lifecycle = BuildContributionLifecycle(session),
            breadcrumbs = BuildContributionBreadcrumbs(session),
            failureGuidance = BuildContributionFailureGuidance(session, unavailable: true),
            actions = BuildContributionActions()
        };

    private static object? BuildContributionSummary(SponsorSessionStatusDto? session, string phase)
        => session is null
            ? null
            : new
            {
                contributionId = session.SponsorSessionId,
                sponsorSessionId = session.SponsorSessionId,
                phase,
                status = session.Status,
                authReady = session.AuthorizedAtUtc is not null,
                createdAtUtc = session.CreatedAtUtc,
                updatedAtUtc = session.UpdatedAtUtc
            };

    private static object? BuildContributionDetails(SponsorSessionStatusDto? session)
        => session is null
            ? null
            : new
            {
                contributionId = session.SponsorSessionId,
                fleetLaneId = session.FleetLaneId,
                authStatus = session.Status,
                authReadyAtUtc = session.AuthorizedAtUtc,
                authorizationTier = session.AuthorizationTier,
                requestedLaneRole = session.RequestedLaneRole,
                participantCodexCode = session.ParticipantCodexCode,
                projectId = session.ProjectId
            };

    private static object BuildContributionActions()
        => new
        {
            explainHref = "/participate",
            homeHref = "/home",
            accountHref = "/account"
        };

    private static object BuildContributionLifecycle(SponsorSessionStatusDto? session)
    {
        if (session is null)
        {
            return new
            {
                currentState = "Ready to start",
                currentCode = "ready_to_start",
                steps = new[]
                {
                    new { key = "intent", label = "Intent", state = "pending", happenedAtUtc = (DateTimeOffset?)null, summary = "Waiting for you to open a lane." },
                    new { key = "consent", label = "Consent", state = "pending", happenedAtUtc = (DateTimeOffset?)null, summary = "Consent is recorded only after you explicitly continue." },
                    new { key = "authorize", label = "Authorize", state = "pending", happenedAtUtc = (DateTimeOffset?)null, summary = "A one-time code appears only after lane start." },
                    new { key = "activation", label = "Activation", state = "pending", happenedAtUtc = (DateTimeOffset?)null, summary = "Fleet lane activation stays pending until authorization succeeds." }
                }
            };
        }

        string normalizedStatus = (session.Status ?? string.Empty).Trim().ToLowerInvariant();
        bool intentDone = session.CreatedAtUtc != default;
        bool consentDone = session.Consented || session.ConsentedAtUtc is not null;
        bool authDone = session.AuthorizedAtUtc is not null;
        bool laneReady = string.Equals(normalizedStatus, "active", StringComparison.OrdinalIgnoreCase);
        bool terminalStop = string.Equals(normalizedStatus, "stopped", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedStatus, "revoked", StringComparison.OrdinalIgnoreCase);
        DateTimeOffset? activationAtUtc = session.ActivatedAtUtc
            ?? session.Events
                .Where(static evt => string.Equals(evt.Kind, "lane_activated", StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static evt => evt.CreatedAtUtc)
                .Select(static evt => (DateTimeOffset?)evt.CreatedAtUtc)
                .FirstOrDefault();

        string activationState = laneReady ? "complete" : terminalStop ? "stopped" : authDone ? "in_progress" : "pending";
        string activationSummary = laneReady
            ? "Lane is active and ready for bounded contribution work."
            : terminalStop
                ? "This lane is no longer active. Start a fresh lane when you want to contribute again."
                : authDone
                    ? "Authorization is complete; activation is waiting on slot and host readiness."
                    : "Activation starts after consent and authorization complete.";

        return new
        {
            currentState = ResolveContributionLifecycleState(session),
            currentCode = string.IsNullOrWhiteSpace(normalizedStatus) ? "tracked" : normalizedStatus,
            steps = new[]
            {
                new { key = "intent", label = "Intent", state = intentDone ? "complete" : "pending", happenedAtUtc = intentDone ? session.CreatedAtUtc : (DateTimeOffset?)null, summary = "Contribution intent is tracked on your account rail." },
                new { key = "consent", label = "Consent", state = consentDone ? "complete" : "pending", happenedAtUtc = session.ConsentedAtUtc, summary = consentDone ? "Consent recorded and attached to this sponsor session." : "Consent is still required before device authorization starts." },
                new { key = "authorize", label = "Authorize", state = authDone ? "complete" : "pending", happenedAtUtc = session.AuthorizedAtUtc, summary = authDone ? "OpenAI/ChatGPT authorization succeeded for this lane." : "Waiting for one-time device-auth verification." },
                new { key = "activation", label = "Activation", state = activationState, happenedAtUtc = activationAtUtc, summary = activationSummary }
            }
        };
    }

    private static object[] BuildContributionBreadcrumbs(SponsorSessionStatusDto? session)
    {
        if (session?.Events is null || session.Events.Count == 0)
        {
            return Array.Empty<object>();
        }

        return session.Events
            .OrderByDescending(static evt => evt.CreatedAtUtc)
            .Take(6)
            .Select(evt => (object)new
            {
                id = evt.EventId,
                kind = evt.Kind,
                label = ResolveContributionEventLabel(evt.Kind),
                message = evt.Message,
                createdAtUtc = evt.CreatedAtUtc
            })
            .ToArray();
    }

    private static object BuildContributionFailureGuidance(SponsorSessionStatusDto? session, bool unavailable)
    {
        if (unavailable)
        {
            return new
            {
                level = "warning",
                title = "Host reachability issue",
                summary = "The host could not refresh lane status. Keep your account flow on the same rail and retry from this screen.",
                nextSafeAction = "Retry from Participate. If this continues, open Account > Support and mention the current contribution id."
            };
        }

        if (session is null)
        {
            return new
            {
                level = "info",
                title = "No active failure",
                summary = "Start only when you want a fresh lane and one-time code.",
                nextSafeAction = "Choose 'I want to participate' to generate a new authorization code."
            };
        }

        return (session.Status ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "waiting_for_slot" => new
            {
                level = "warning",
                title = "Capacity wait",
                summary = "Authorization can still be valid while lane capacity is temporarily full.",
                nextSafeAction = "Keep this page open for automatic polling, or request a fresh code if the current authorization expires."
            },
            "stopped" => new
            {
                level = "info",
                title = "Lane stopped",
                summary = "This lane was stopped intentionally and will not process new work.",
                nextSafeAction = "Start a new contribution lane when you are ready to continue."
            },
            "revoked" => new
            {
                level = "warning",
                title = "Lane revoked",
                summary = "This lane was revoked and cannot be resumed.",
                nextSafeAction = "Start a fresh lane and complete consent + authorization again."
            },
            _ => new
            {
                level = "info",
                title = "Recovery ready",
                summary = "If the one-time code expires or the verification page fails, this flow can issue a replacement code without losing account history.",
                nextSafeAction = "Use 'Get a fresh code' and continue from the updated authorization step."
            }
        };
    }

    private static string ResolveContributionLifecycleState(SponsorSessionStatusDto session)
        => (session.Status ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "intent_created" => "Intent recorded",
            "consented" => "Consent recorded",
            "pending_auth" => "Waiting for authorization",
            "fleet_lane_created" => "Fleet lane created",
            "auth_ready" => "Authorization ready",
            "lane_pending" => "Activation in progress",
            "waiting_for_slot" => session.AuthorizedAtUtc is null ? "Queued before authorization" : "Queued after authorization",
            "active" => "Lane active",
            "stopped" => "Lane stopped",
            "revoked" => "Lane revoked",
            _ => System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase((session.Status ?? "tracked").Replace('_', ' '))
        };

    private static string ResolveContributionEventLabel(string? kind)
        => (kind ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "intent_created" => "Intent created",
            "consent_recorded" => "Consent recorded",
            "device_auth_started" => "Authorization started",
            "device_auth_ready" => "Authorization ready",
            "lane_created" => "Lane created",
            "lane_activated" => "Lane activated",
            "lane_stopped" => "Lane stopped",
            "lane_revoked" => "Lane revoked",
            _ => string.IsNullOrWhiteSpace(kind)
                ? "Decision event"
                : System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(kind.Replace('_', ' '))
        };

    private static string ResolveContributionPhase(SponsorSessionStatusDto session)
        => session.Status switch
        {
            "active" => "complete",
            "stopped" => "start",
            "revoked" => "start",
            _ => "authorize"
        };

    private static string ResolveContributionHeading(SponsorSessionStatusDto session, string phase)
    {
        if (string.Equals(session.Status, "waiting_for_slot", StringComparison.OrdinalIgnoreCase))
        {
            return session.AuthorizedAtUtc is null
                ? "Waiting for an available slot"
                : "Finishing contribution setup";
        }

        return phase switch
        {
            "complete" => "Thanks, you're set",
            "authorize" => "Authorize with OpenAI",
            _ => "Start contributing"
        };
    }

    private static string ResolveContributionSupport(SponsorSessionStatusDto session, string phase)
    {
        if (string.Equals(session.Status, "waiting_for_slot", StringComparison.OrdinalIgnoreCase))
        {
            return session.AuthorizedAtUtc is null
                ? "All contribution slots are busy right now. Chummer saved your request, and you can ask for a fresh code again as soon as a slot opens."
                : "Your authorization is already complete. Chummer is waiting for the next available contribution slot to finish setup.";
        }

        return phase switch
        {
            "complete" => "Your contribution lane is linked. Chummer will only count receipt-backed work after validation and review.",
            "authorize" => "Open the authorization page, sign in to ChatGPT with your OpenAI account, enter the one-time code, and keep this page open while Chummer watches for confirmation. If the code expires, ask for a fresh one here.",
            _ => "Authorize a temporary Codex contribution lane with your OpenAI account in ChatGPT. Chummer uses it only for bounded project work, and final landing still goes through review."
        };
    }

    private static string ResolveContributionStatusLine(SponsorSessionStatusDto session)
        => session.Status switch
        {
            "lane_pending" => "Authorization is confirmed. Chummer is finishing lane setup.",
            "active" => "You can leave this page now. Stop or revoke later from your account settings.",
            "waiting_for_slot" => session.AuthorizedAtUtc is null
                ? "All contribution slots are currently busy. Chummer saved your request and will move you forward when a slot opens."
                : "Authorization is complete. Chummer is waiting for the next available contribution slot.",
            "stopped" => "This contribution lane has been stopped. You can start again whenever you want.",
            "revoked" => "This contribution lane has been revoked. Start a new one if you want to contribute again.",
            _ => "Waiting for confirmation from your OpenAI account in ChatGPT..."
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

    private string? ExtractStartCodexCode()
    {
        try
        {
            Request.EnableBuffering();
            if (Request.Body.CanSeek)
            {
                Request.Body.Position = 0;
            }

            using var document = System.Text.Json.JsonDocument.Parse(Request.Body);
            if (Request.Body.CanSeek)
            {
                Request.Body.Position = 0;
            }

            return document.RootElement.ValueKind == System.Text.Json.JsonValueKind.Object
                && document.RootElement.TryGetProperty("codexCode", out var codexCode)
                ? codexCode.GetString()
                : null;
        }
        catch
        {
            if (Request.Body.CanSeek)
            {
                Request.Body.Position = 0;
            }

            return null;
        }
    }
}

public sealed record CreateCodexParticipationIntentRequest(
    string? SubjectId,
    string? SubjectLabel,
    string ProjectId,
    string? ParticipantCodexCode = null,
    string? GroupId = null,
    string? BoostCode = null,
    string? CampaignId = null,
    string? Visibility = null,
    string? RequestedLaneType = null,
    string? RequestedLaneRole = null,
    string? AuthorizationTier = null,
    string? TierSource = null);
