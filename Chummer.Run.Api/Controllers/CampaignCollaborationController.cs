using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
[Route("api/v1/campaigns")]
public sealed class CampaignCollaborationController : ControllerBase
{
    private const int MaxRequestBodyBytes = 64 * 1024;

    private readonly CampaignCollaborationService _campaigns;
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;

    public CampaignCollaborationController(
        CampaignCollaborationService campaigns,
        AccountService accounts,
        HubIdentityClient identity)
    {
        _campaigns = campaigns;
        _accounts = accounts;
        _identity = identity;
    }

    [HttpGet]
    [ProducesResponseType(typeof(IReadOnlyList<CampaignCollaborationProjection>), StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<CampaignCollaborationProjection>>> List(CancellationToken cancellationToken)
    {
        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            return Ok(_campaigns.ListCampaigns(user));
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpGet("{campaignId}")]
    [ProducesResponseType(typeof(CampaignCollaborationProjection), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignCollaborationProjection>> Get(
        [FromRoute] string campaignId,
        CancellationToken cancellationToken)
    {
        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            CampaignCollaborationProjection? campaign = _campaigns.GetCampaign(user, campaignId);
            return campaign is null ? NotFound() : Ok(campaign);
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpGet("eligible-characters")]
    [ProducesResponseType(typeof(IReadOnlyList<CampaignEligibleCharacterProjection>), StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<CampaignEligibleCharacterProjection>>> ListEligibleCharacters(
        CancellationToken cancellationToken)
    {
        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            return Ok(_campaigns.ListEligibleCharacters(user));
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpPost]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType(typeof(CampaignCollaborationProjection), StatusCodes.Status201Created)]
    public async Task<ActionResult<CampaignCollaborationProjection>> Create(
        [FromBody] CreateCampaignCollaborationRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("campaign payload is required.");
        }

        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            CampaignCollaborationProjection campaign = _campaigns.CreateCampaign(user, request);
            return CreatedAtAction(nameof(Get), new { campaignId = campaign.CampaignId }, campaign);
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpGet("{campaignId}/roster")]
    [ProducesResponseType(typeof(IReadOnlyList<CampaignRosterEntryProjection>), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<IReadOnlyList<CampaignRosterEntryProjection>>> GetRoster(
        [FromRoute] string campaignId,
        CancellationToken cancellationToken)
    {
        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            return Ok(_campaigns.GetRoster(user, campaignId));
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpPost("{campaignId}/invites")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType(typeof(CampaignInviteSecretProjection), StatusCodes.Status201Created)]
    public async Task<ActionResult<CampaignInviteSecretProjection>> CreateInvite(
        [FromRoute] string campaignId,
        [FromBody] CreateCampaignInviteRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("invite payload is required.");
        }

        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            CampaignInviteSecretProjection invite = _campaigns.CreateInvite(user, campaignId, request);
            ApplySecretResponseHeaders();
            return StatusCode(StatusCodes.Status201Created, invite);
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpDelete("{campaignId}/invites/{inviteId}")]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    public async Task<IActionResult> RevokeInvite(
        [FromRoute] string campaignId,
        [FromRoute] string inviteId,
        CancellationToken cancellationToken)
    {
        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            _campaigns.RevokeInvite(user, campaignId, inviteId);
            return NoContent();
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpPost("invites/{inviteId}/redeem")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType(typeof(CampaignInviteRedemptionProjection), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignInviteRedemptionProjection>> RedeemInvite(
        [FromRoute] string inviteId,
        [FromBody] RedeemCampaignInviteRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("invite redemption payload is required.");
        }

        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            ApplySecretResponseHeaders();
            return Ok(_campaigns.RedeemInvite(user, inviteId, request));
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpPost("join-code/redeem")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType(typeof(CampaignInviteRedemptionProjection), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignInviteRedemptionProjection>> RedeemJoinCode(
        [FromBody] RedeemCampaignJoinCodeRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("join-code redemption payload is required.");
        }

        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            ApplySecretResponseHeaders();
            return Ok(_campaigns.RedeemJoinCode(user, request));
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpGet("{campaignId}/sheets/{dossierId}")]
    [ProducesResponseType(typeof(CampaignPlayerSafeSheetProjection), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignPlayerSafeSheetProjection>> GetSharedSheet(
        [FromRoute] string campaignId,
        [FromRoute] string dossierId,
        CancellationToken cancellationToken)
    {
        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            return Ok(_campaigns.GetSharedSheet(user, campaignId, dossierId));
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpPut("{campaignId}/sheets/{dossierId}")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType(typeof(CampaignSharedSheetEditReceipt), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public async Task<ActionResult<CampaignSharedSheetEditReceipt>> UpdateSharedSheet(
        [FromRoute] string campaignId,
        [FromRoute] string dossierId,
        [FromBody] CampaignSharedSheetUpdateRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("shared-sheet payload is required.");
        }

        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            return Ok(_campaigns.UpdateSharedSheet(user, campaignId, dossierId, request));
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpPut("{campaignId}/sheets/{dossierId}/gm-authority")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType(typeof(CampaignGmAuthorityUpdateReceipt), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<ActionResult<CampaignGmAuthorityUpdateReceipt>> UpdateGmAuthority(
        [FromRoute] string campaignId,
        [FromRoute] string dossierId,
        [FromBody] CampaignGmAuthorityUpdateRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("GM authority payload is required.");
        }

        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            return Ok(_campaigns.UpdateGmAuthority(user, campaignId, dossierId, request));
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpGet("{campaignId}/runs/{runId}/runsite/draft")]
    [ProducesResponseType(typeof(CampaignRunsiteDraftProjection), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignRunsiteDraftProjection>> GetRunsiteDraft(
        [FromRoute] string campaignId,
        [FromRoute] string runId,
        CancellationToken cancellationToken)
    {
        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            CampaignRunsiteDraftProjection? draft = _campaigns.GetRunsiteDraft(user, campaignId, runId);
            return draft is null ? NotFound() : Ok(draft);
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpPut("{campaignId}/runs/{runId}/runsite/draft")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType(typeof(CampaignRunsiteDraftProjection), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<ActionResult<CampaignRunsiteDraftProjection>> UpsertRunsiteDraft(
        [FromRoute] string campaignId,
        [FromRoute] string runId,
        [FromBody] CampaignRunsiteDraftUpdateRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("runsite draft payload is required.");
        }

        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            return Ok(_campaigns.UpsertRunsiteDraft(user, campaignId, runId, request));
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpPost("{campaignId}/runs/{runId}/runsite/publish")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType(typeof(CampaignRunsitePlayerProjection), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<ActionResult<CampaignRunsitePlayerProjection>> PublishRunsite(
        [FromRoute] string campaignId,
        [FromRoute] string runId,
        [FromBody] PublishCampaignRunsiteRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("runsite publication payload is required.");
        }

        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            return Ok(_campaigns.PublishRunsite(user, campaignId, runId, request));
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    [HttpGet("{campaignId}/runs/{runId}/runsite")]
    [ProducesResponseType(typeof(CampaignRunsitePlayerProjection), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignRunsitePlayerProjection>> GetPublishedRunsite(
        [FromRoute] string campaignId,
        [FromRoute] string runId,
        CancellationToken cancellationToken)
    {
        try
        {
            HubUserDto user = await RequireUserAsync(cancellationToken);
            CampaignRunsitePlayerProjection? published = _campaigns.GetPublishedRunsite(user, campaignId, runId);
            return published is null ? NotFound() : Ok(published);
        }
        catch (Exception ex) when (IsMapped(ex))
        {
            return MapException(ex);
        }
    }

    private async Task<HubUserDto> RequireUserAsync(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
        return _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
    }

    private void ApplySecretResponseHeaders()
    {
        Response.Headers.CacheControl = "private, no-store, no-cache, max-age=0";
        Response.Headers.Pragma = "no-cache";
        Response.Headers["Referrer-Policy"] = "no-referrer";
    }

    private static bool IsMapped(Exception exception)
        => exception is HubRequestAuthException
            or CampaignCollaborationAccessDeniedException
            or CampaignInviteRejectedException
            or CampaignInviteThrottledException
            or CampaignIdempotencyConflictException
            or CampaignInviteReplayUnavailableException
            or CampaignBindingRevisionConflictException
            or CampaignRevisionConflictException
            or CampaignCanonicalEditConflictException
            or CampaignCanonicalEditUnavailableException
            or KeyNotFoundException
            or ArgumentException
            or InvalidOperationException;

    private ActionResult MapException(Exception exception)
        => exception switch
        {
            HubRequestAuthException auth => Problem(statusCode: auth.StatusCode, detail: auth.Message),
            CampaignCollaborationAccessDeniedException denied => Problem(
                statusCode: StatusCodes.Status403Forbidden,
                detail: denied.Message),
            CampaignInviteRejectedException rejected => Problem(
                statusCode: StatusCodes.Status404NotFound,
                detail: rejected.Message),
            CampaignInviteThrottledException throttled => MapThrottle(throttled),
            CampaignIdempotencyConflictException conflict => Problem(
                statusCode: StatusCodes.Status409Conflict,
                detail: conflict.Message),
            CampaignInviteReplayUnavailableException unavailable => Problem(
                statusCode: StatusCodes.Status503ServiceUnavailable,
                detail: unavailable.Message),
            CampaignBindingRevisionConflictException conflict => Problem(
                statusCode: StatusCodes.Status409Conflict,
                detail: conflict.Message),
            CampaignRevisionConflictException conflict => Problem(
                statusCode: StatusCodes.Status409Conflict,
                detail: conflict.Message),
            CampaignCanonicalEditConflictException conflict => Problem(
                statusCode: StatusCodes.Status409Conflict,
                detail: conflict.Message),
            CampaignCanonicalEditUnavailableException unavailable => Problem(
                statusCode: StatusCodes.Status503ServiceUnavailable,
                detail: unavailable.Message),
            KeyNotFoundException => NotFound(),
            ArgumentException invalid => Problem(
                statusCode: StatusCodes.Status400BadRequest,
                detail: invalid.Message),
            InvalidOperationException invalid => Problem(
                statusCode: StatusCodes.Status409Conflict,
                detail: invalid.Message),
            _ => Problem(statusCode: StatusCodes.Status500InternalServerError)
        };

    private ActionResult MapThrottle(CampaignInviteThrottledException throttled)
    {
        long retryAfterSeconds = Math.Max(
            1,
            (long)Math.Ceiling((throttled.RetryAtUtc - DateTimeOffset.UtcNow).TotalSeconds));
        Response.Headers.RetryAfter = retryAfterSeconds.ToString(System.Globalization.CultureInfo.InvariantCulture);
        return Problem(statusCode: StatusCodes.Status429TooManyRequests, detail: throttled.Message);
    }
}
