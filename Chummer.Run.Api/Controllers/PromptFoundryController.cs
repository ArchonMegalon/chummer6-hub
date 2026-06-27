using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
public sealed class PromptFoundryController : ControllerBase
{
    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly PromptFoundryService _foundry;

    public PromptFoundryController(HubIdentityClient identity, AccountService accounts, PromptFoundryService foundry)
    {
        _identity = identity;
        _accounts = accounts;
        _foundry = foundry;
    }

    [HttpGet("/prompt-foundry")]
    [ProducesResponseType<PromptFoundryHomeProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> Home([FromQuery] string? campaignId, CancellationToken cancellationToken)
        => await WithUser(cancellationToken, userId => Ok(_foundry.GetHome(userId, campaignId)));

    [HttpGet("/prompt-foundry/provider/prompt-architects")]
    [ProducesResponseType<PromptArchitectsProviderVerificationProjection>(StatusCodes.Status200OK)]
    public IActionResult Provider()
        => Ok(_foundry.BuildProviderVerification());

    [HttpPost("/prompt-foundry/templates/sync")]
    [ProducesResponseType<IReadOnlyList<PromptTemplateProjection>>(StatusCodes.Status200OK)]
    public async Task<IActionResult> SyncTemplates(CancellationToken cancellationToken)
        => await WithUser(cancellationToken, userId => Ok(_foundry.SyncSeedTemplates(userId)));

    [HttpPost("/prompt-foundry/drafts")]
    [RequestSizeLimit(PromptFoundryService.MaxDraftRequestBodyBytes)]
    [ProducesResponseType<PromptFoundryDraftProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> CreateDraft([FromBody] PromptFoundryCreateDraftRequest? request, CancellationToken cancellationToken)
        => request is null
            ? BadRequest("prompt foundry draft payload is required.")
            : await WithUser(cancellationToken, userId => Ok(_foundry.CreateDraft(userId, request)));

    [HttpPost("/prompt-foundry/drafts/{promptDraftId}")]
    [RequestSizeLimit(PromptFoundryService.MaxDraftRequestBodyBytes)]
    [ProducesResponseType<PromptFoundryDraftProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> EditDraft(
        [FromRoute] string promptDraftId,
        [FromBody] PromptFoundryEditDraftRequest? request,
        CancellationToken cancellationToken)
        => request is null
            ? BadRequest("prompt foundry edit payload is required.")
            : await WithUser(cancellationToken, userId => Ok(_foundry.EditDraft(userId, promptDraftId, request)));

    [HttpPost("/prompt-foundry/drafts/{promptDraftId}/approve")]
    [RequestSizeLimit(PromptFoundryService.MaxApprovalRequestBodyBytes)]
    [ProducesResponseType<PromptFoundryDraftProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> ApproveDraft(
        [FromRoute] string promptDraftId,
        [FromBody] PromptFoundryApproveDraftRequest? request,
        CancellationToken cancellationToken)
        => request is null
            ? BadRequest("prompt foundry approval payload is required.")
            : await WithUser(cancellationToken, userId => Ok(_foundry.ApproveDraft(userId, promptDraftId, request)));

    private async Task<IActionResult> WithUser(CancellationToken cancellationToken, Func<string, IActionResult> action)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return action(user.UserId);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Conflict(new ProblemDetails { Status = StatusCodes.Status409Conflict, Detail = ex.Message });
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }
}
