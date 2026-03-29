using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
[Route("api/v1/campaign-spine")]
public sealed class CampaignSpineController : ControllerBase
{
    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly InstallLinkingService _installLinking;
    private readonly CampaignSpineService _campaignSpine;
    private readonly CampaignWorkspaceServerPlaneService _workspaceServerPlane;

    public CampaignSpineController(
        HubIdentityClient identity,
        AccountService accounts,
        InstallLinkingService installLinking,
        CampaignSpineService campaignSpine,
        CampaignWorkspaceServerPlaneService workspaceServerPlane)
    {
        _identity = identity;
        _accounts = accounts;
        _installLinking = installLinking;
        _campaignSpine = campaignSpine;
        _workspaceServerPlane = workspaceServerPlane;
    }

    [HttpGet("me")]
    [ProducesResponseType<AccountCampaignSummary>(StatusCodes.Status200OK)]
    public async Task<ActionResult<AccountCampaignSummary>> GetMyCampaignSummary(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.GetAccountSummary(user, installLinking));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/restore")]
    [ProducesResponseType<WorkspaceRestoreProjection>(StatusCodes.Status200OK)]
    public async Task<ActionResult<WorkspaceRestoreProjection>> GetMyRestoreProjection(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.GetRestoreProjection(user, installLinking));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}")]
    [ProducesResponseType<CampaignWorkspaceProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignWorkspaceProjection>> GetMyCampaignWorkspace([FromRoute] string workspaceId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var workspace = _campaignSpine.GetWorkspace(user, workspaceId, installLinking);
            return workspace is null ? NotFound() : Ok(workspace);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspace-digests")]
    [ProducesResponseType<IReadOnlyList<CampaignWorkspaceDigestProjection>>(StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<CampaignWorkspaceDigestProjection>>> GetMyCampaignWorkspaceDigests(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.GetWorkspaceDigests(user, installLinking));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/server-plane")]
    [ProducesResponseType<CampaignWorkspaceServerPlaneProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignWorkspaceServerPlaneProjection>> GetMyCampaignWorkspaceServerPlane([FromRoute] string workspaceId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var serverPlane = _workspaceServerPlane.GetWorkspaceServerPlane(user, workspaceId, installLinking);
            return serverPlane is null ? NotFound() : Ok(serverPlane);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/workspaces/{workspaceId}/prep-library")]
    [ProducesResponseType<CampaignPrepLibrarySearchResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignPrepLibrarySearchResponse>> GetMyCampaignWorkspacePrepLibrary(
        [FromRoute] string workspaceId,
        [FromQuery] string? queryText,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var prepLibrary = _workspaceServerPlane.GetWorkspacePrepLibrary(user, workspaceId, installLinking, queryText);
            return prepLibrary is null ? NotFound() : Ok(prepLibrary);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("me/roster-transfers")]
    [ProducesResponseType<RosterTransferProjection>(StatusCodes.Status200OK)]
    public async Task<ActionResult<RosterTransferProjection>> TransferMyRoster([FromBody] RosterTransferRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("roster-transfer payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_campaignSpine.TransferRoster(user, request));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpGet("me/runs/{runId}")]
    [ProducesResponseType<RunProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<RunProjection>> GetMyRun([FromRoute] string runId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var run = _campaignSpine.GetRun(user, runId, installLinking);
            return run is null ? NotFound() : Ok(run);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/build-handoffs/{handoffId}")]
    [ProducesResponseType<BuildLabHandoffProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<BuildLabHandoffProjection>> GetMyBuildLabHandoff([FromRoute] string handoffId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var handoff = _campaignSpine.GetBuildLabHandoff(user, handoffId, installLinking);
            return handoff is null ? NotFound() : Ok(handoff);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/rules/{entryId}")]
    [ProducesResponseType<RulesNavigatorAnswerProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<RulesNavigatorAnswerProjection>> GetMyRulesNavigatorAnswer([FromRoute] string entryId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var answer = _campaignSpine.GetRulesNavigatorAnswer(user, entryId, installLinking);
            return answer is null ? NotFound() : Ok(answer);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/publications/{publicationId}")]
    [ProducesResponseType<CreatorPublicationProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CreatorPublicationProjection>> GetMyCreatorPublication([FromRoute] string publicationId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var publication = _campaignSpine.GetCreatorPublication(user, publicationId, installLinking);
            return publication is null ? NotFound() : Ok(publication);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }
}
