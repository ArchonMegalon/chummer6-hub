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
    private readonly CampaignFederationOrchestrationService _campaignFederation;

    public CampaignSpineController(
        HubIdentityClient identity,
        AccountService accounts,
        InstallLinkingService installLinking,
        CampaignSpineService campaignSpine,
        CampaignWorkspaceServerPlaneService workspaceServerPlane,
        CampaignFederationOrchestrationService campaignFederation)
    {
        _identity = identity;
        _accounts = accounts;
        _installLinking = installLinking;
        _campaignSpine = campaignSpine;
        _workspaceServerPlane = workspaceServerPlane;
        _campaignFederation = campaignFederation;
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

    [HttpGet("me/organizer-ops")]
    [ProducesResponseType<OrganizerOperationsDashboardProjection>(StatusCodes.Status200OK)]
    public async Task<ActionResult<OrganizerOperationsDashboardProjection>> GetMyOrganizerOperations(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_campaignSpine.GetOrganizerOperations(user, installLinking));
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

    [HttpPost("me/workspaces/starter")]
    [ProducesResponseType<CampaignWorkspaceProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignWorkspaceProjection>> SeedStarterWorkspace(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            CampaignWorkspaceProjection? starter = _campaignSpine.GetStarterWorkspace(user, installLinking);
            return starter is null ? NotFound() : Ok(starter);
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

    [HttpGet("me/workspaces/{workspaceId}/roster-transfer-plan")]
    [ProducesResponseType<RosterTransferPlannerProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<RosterTransferPlannerProjection>> GetMyCampaignWorkspaceRosterTransferPlan(
        [FromRoute] string workspaceId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var rosterTransferPlan = _campaignSpine.GetRosterTransferPlan(user, workspaceId, installLinking);
            return rosterTransferPlan is null ? NotFound() : Ok(rosterTransferPlan);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("me/workspaces/{workspaceId}/prep-library/launches")]
    [ProducesResponseType<GovernedPrepLaunchProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<GovernedPrepLaunchProjection>> LaunchMyCampaignWorkspacePrepPacket(
        [FromRoute] string workspaceId,
        [FromBody] GovernedPrepLaunchRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("governed prep launch payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var launch = _workspaceServerPlane.LaunchWorkspacePrepPacket(user, workspaceId, request, installLinking);
            return launch is null ? NotFound() : Ok(launch);
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

    [HttpPost("me/workspaces/{workspaceId}/travel-prefetches")]
    [ProducesResponseType<TravelPrefetchReceiptProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<TravelPrefetchReceiptProjection>> StageMyCampaignWorkspaceTravelPrefetch(
        [FromRoute] string workspaceId,
        [FromBody] TravelPrefetchStageRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("travel-prefetch payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var receipt = _workspaceServerPlane.StageTravelPrefetch(user, workspaceId, request, installLinking);
            return receipt is null ? NotFound() : Ok(receipt);
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

    [HttpPost("me/workspaces/{workspaceId}/aftermath-recap-packages")]
    [ProducesResponseType<AftermathRecapPackageProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<AftermathRecapPackageProjection>> GenerateMyCampaignWorkspaceAftermathRecapPackage(
        [FromRoute] string workspaceId,
        [FromBody] AftermathRecapPackageRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("aftermath recap payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var package = _workspaceServerPlane.GenerateAftermathRecapPackage(user, workspaceId, request, installLinking);
            return package is null ? NotFound() : Ok(package);
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

    [HttpPost("me/workspaces/{workspaceId}/federation-batches")]
    [ProducesResponseType<CampaignFederationBatchProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CampaignFederationBatchProjection>> LaunchMyCampaignWorkspaceFederationBatch(
        [FromRoute] string workspaceId,
        [FromBody] CampaignFederationBatchRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("campaign federation payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var batch = _campaignFederation.LaunchWorkspaceFederationBatch(user, workspaceId, request, installLinking);
            return batch is null ? NotFound() : Ok(batch);
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
