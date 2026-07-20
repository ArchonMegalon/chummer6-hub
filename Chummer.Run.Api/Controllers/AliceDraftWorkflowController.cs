using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.KarmaForge;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
[Route("api/v1/alice/drafts")]
[Produces("application/json")]
public sealed class AliceDraftWorkflowController : ControllerBase
{
    private const int MaxRequestBodyBytes = 16 * 1024;

    private readonly HubIdentityClient _identity;
    private readonly AliceDraftWorkflowService _workflow;

    public AliceDraftWorkflowController(
        HubIdentityClient identity,
        AliceDraftWorkflowService workflow)
    {
        _identity = identity;
        _workflow = workflow;
    }

    [HttpPost]
    [Consumes("application/json")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType(typeof(AliceDraftProjection), StatusCodes.Status201Created)]
    public Task<IActionResult> Create(
        [FromBody] AliceDraftCreateRequest request,
        CancellationToken cancellationToken)
        => ExecuteMutationAsync(
            subject => _workflow.Create(subject.SubjectId, request),
            StatusCodes.Status201Created,
            cancellationToken);

    [HttpGet("{draftId}")]
    [ProducesResponseType(typeof(AliceDraftProjection), StatusCodes.Status200OK)]
    public Task<IActionResult> Get(string draftId, CancellationToken cancellationToken)
        => ExecuteAsync(
            subject => _workflow.Get(subject.SubjectId, draftId),
            StatusCodes.Status200OK,
            requireFreshSubject: false,
            cancellationToken);

    [HttpPost("{draftId}/compare")]
    [Consumes("application/json")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType(typeof(AliceDraftProjection), StatusCodes.Status200OK)]
    public Task<IActionResult> Compare(
        string draftId,
        [FromBody] AliceDraftCompareRequest request,
        CancellationToken cancellationToken)
        => ExecuteMutationAsync(
            subject => _workflow.Compare(subject.SubjectId, draftId, request),
            StatusCodes.Status200OK,
            cancellationToken);

    [HttpPost("{draftId}/apply")]
    [Consumes("application/json")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType(typeof(AliceDraftProjection), StatusCodes.Status200OK)]
    public Task<IActionResult> Apply(
        string draftId,
        [FromBody] AliceDraftApplyRequest request,
        CancellationToken cancellationToken)
        => ExecuteMutationAsync(
            subject => _workflow.Apply(subject.SubjectId, draftId, request),
            StatusCodes.Status200OK,
            cancellationToken);

    [HttpPost("{draftId}/discard")]
    [Consumes("application/json")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType(typeof(AliceDraftProjection), StatusCodes.Status200OK)]
    public Task<IActionResult> Discard(
        string draftId,
        [FromBody] AliceDraftDiscardRequest request,
        CancellationToken cancellationToken)
        => ExecuteMutationAsync(
            subject => _workflow.Discard(subject.SubjectId, draftId, request),
            StatusCodes.Status200OK,
            cancellationToken);

    private Task<IActionResult> ExecuteMutationAsync(
        Func<AuthenticatedHubSubject, AliceDraftProjection> operation,
        int successStatus,
        CancellationToken cancellationToken)
        => ExecuteAsync(operation, successStatus, requireFreshSubject: true, cancellationToken);

    private async Task<IActionResult> ExecuteAsync(
        Func<AuthenticatedHubSubject, AliceDraftProjection> operation,
        int successStatus,
        bool requireFreshSubject,
        CancellationToken cancellationToken)
    {
        try
        {
            AuthenticatedHubSubject subject = requireFreshSubject
                ? await _identity.RequireFreshSubjectAsync(Request, cancellationToken)
                : await _identity.RequireSubjectAsync(Request, cancellationToken);
            AliceDraftProjection projection = operation(subject);
            return StatusCode(successStatus, projection);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(
                statusCode: ex.StatusCode,
                title: "Authenticated ALICE subject required",
                detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return Problem(
                statusCode: StatusCodes.Status404NotFound,
                title: "ALICE draft not found",
                detail: "No ALICE draft is available for this authenticated subject and draft id.");
        }
        catch (AliceDraftConflictException ex)
        {
            return Problem(
                statusCode: StatusCodes.Status409Conflict,
                title: "ALICE draft transition rejected",
                detail: ex.Message);
        }
        catch (ArgumentException ex)
        {
            return Problem(
                statusCode: StatusCodes.Status400BadRequest,
                title: "ALICE draft request is invalid",
                detail: ex.Message);
        }
    }
}
