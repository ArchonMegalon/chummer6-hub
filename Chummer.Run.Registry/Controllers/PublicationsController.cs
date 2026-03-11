using Chummer.Run.Registry.Services;
using Chummer.Run.Contracts.Publication;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Net.Http.Headers;

namespace Chummer.Run.Registry.Controllers;

[ApiController]
[Route("api/v1/publications")]
public sealed class PublicationsController : ControllerBase
{
    private readonly IPublicationWorkflowService _workflow;

    public PublicationsController(IPublicationWorkflowService workflow)
    {
        _workflow = workflow;
    }

    [HttpPost]
    [ProducesResponseType<PublicationRecordResponse>(StatusCodes.Status201Created)]
    [ProducesResponseType<ValidationProblemDetails>(StatusCodes.Status400BadRequest)]
    public ActionResult<PublicationRecordResponse> Submit([FromBody] PublicationSubmissionRequest request)
    {
        var created = _workflow.Submit(request);
        SetConcurrencyHeaders(created);
        return CreatedAtAction(nameof(Get), new { publicationId = created.PublicationId }, created);
    }

    [HttpGet]
    [ProducesResponseType<IReadOnlyList<PublicationRecordResponse>>(StatusCodes.Status200OK)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status400BadRequest)]
    public ActionResult<IReadOnlyList<PublicationRecordResponse>> List([FromQuery] string? state = null)
    {
        if (!TryParseState(state, out var parsedState, out var error))
        {
            return Problem(
                detail: error,
                title: "Invalid publication state filter.",
                type: "https://chummer.run/problems/invalid-publication-state",
                statusCode: StatusCodes.Status400BadRequest);
        }

        return Ok(_workflow.List(parsedState));
    }

    [HttpGet("{publicationId}")]
    [ProducesResponseType<PublicationRecordResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status400BadRequest)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status404NotFound)]
    public ActionResult<PublicationRecordResponse> Get([FromRoute] string publicationId)
    {
        if (string.IsNullOrWhiteSpace(publicationId))
        {
            return Problem(
                detail: "publicationId is required.",
                title: "Missing publication id.",
                type: "https://chummer.run/problems/missing-publication-id",
                statusCode: StatusCodes.Status400BadRequest);
        }

        var publication = _workflow.Get(publicationId);
        if (publication is null)
        {
            return Problem(
                detail: $"Publication '{publicationId}' was not found.",
                title: "Publication not found.",
                type: "https://chummer.run/problems/publication-not-found",
                statusCode: StatusCodes.Status404NotFound);
        }

        SetConcurrencyHeaders(publication);
        return Ok(publication);
    }

    [HttpPost("{publicationId}/review")]
    [ProducesResponseType<PublicationRecordResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType<ValidationProblemDetails>(StatusCodes.Status400BadRequest)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status404NotFound)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status409Conflict)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status412PreconditionFailed)]
    public ActionResult<PublicationRecordResponse> Review(
        [FromRoute] string publicationId,
        [FromBody] PublicationReviewRequest request,
        [FromHeader(Name = "If-Match")] string? ifMatch)
    {
        if (string.IsNullOrWhiteSpace(publicationId))
        {
            return Problem(
                detail: "publicationId is required.",
                title: "Missing publication id.",
                type: "https://chummer.run/problems/missing-publication-id",
                statusCode: StatusCodes.Status400BadRequest);
        }

        return FromMutationResult(_workflow.Review(publicationId, request, ifMatch), publicationId);
    }

    [HttpPost("{publicationId}/publish")]
    [ProducesResponseType<PublicationRecordResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType<ValidationProblemDetails>(StatusCodes.Status400BadRequest)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status404NotFound)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status409Conflict)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status412PreconditionFailed)]
    public ActionResult<PublicationRecordResponse> Publish(
        [FromRoute] string publicationId,
        [FromBody] PublicationPublishRequest request,
        [FromHeader(Name = "If-Match")] string? ifMatch)
    {
        if (string.IsNullOrWhiteSpace(publicationId))
        {
            return Problem(
                detail: "publicationId is required.",
                title: "Missing publication id.",
                type: "https://chummer.run/problems/missing-publication-id",
                statusCode: StatusCodes.Status400BadRequest);
        }

        return FromMutationResult(_workflow.Publish(publicationId, request, ifMatch), publicationId);
    }

    [HttpPost("{publicationId}/moderate")]
    [ProducesResponseType<PublicationRecordResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType<ValidationProblemDetails>(StatusCodes.Status400BadRequest)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status404NotFound)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status409Conflict)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status412PreconditionFailed)]
    public ActionResult<PublicationRecordResponse> Moderate(
        [FromRoute] string publicationId,
        [FromBody] PublicationModerationRequest request,
        [FromHeader(Name = "If-Match")] string? ifMatch)
    {
        if (string.IsNullOrWhiteSpace(publicationId))
        {
            return Problem(
                detail: "publicationId is required.",
                title: "Missing publication id.",
                type: "https://chummer.run/problems/missing-publication-id",
                statusCode: StatusCodes.Status400BadRequest);
        }

        return FromMutationResult(_workflow.Moderate(publicationId, request, ifMatch), publicationId);
    }

    private static bool TryParseState(
        string? value,
        out PublicationState? state,
        out string? error)
    {
        error = null;
        state = null;

        if (string.IsNullOrWhiteSpace(value))
        {
            return true;
        }

        if (Enum.TryParse<PublicationState>(value, true, out var parsed))
        {
            state = parsed;
            return true;
        }

        error = "state must be one of Draft, PendingReview, Approved, Rejected, Published, Delisted, Deprecated, or Superseded.";
        return false;
    }

    private ActionResult<PublicationRecordResponse> FromMutationResult(PublicationMutationResult result, string publicationId)
    {
        if (!string.IsNullOrWhiteSpace(result.CurrentConcurrencyToken))
        {
            Response.Headers[HeaderNames.ETag] = result.CurrentConcurrencyToken;
        }

        return result.Status switch
        {
            PublicationMutationStatus.Success when result.Publication is not null => Ok(WriteConcurrencyHeaders(result.Publication)),
            PublicationMutationStatus.NotFound => Problem(
                detail: $"Publication '{publicationId}' was not found.",
                title: "Publication not found.",
                type: "https://chummer.run/problems/publication-not-found",
                statusCode: StatusCodes.Status404NotFound),
            PublicationMutationStatus.PreconditionFailed => Problem(
                detail: result.Message,
                title: "Concurrency token mismatch.",
                type: "https://chummer.run/problems/concurrency-mismatch",
                statusCode: StatusCodes.Status412PreconditionFailed),
            PublicationMutationStatus.Conflict => Problem(
                detail: result.Message,
                title: "Publication state conflict.",
                type: "https://chummer.run/problems/publication-state-conflict",
                statusCode: StatusCodes.Status409Conflict),
            _ => Problem(
                detail: "The publication request could not be completed.",
                title: "Publication workflow failure.",
                type: "https://chummer.run/problems/publication-workflow-failure",
                statusCode: StatusCodes.Status500InternalServerError)
        };
    }

    private PublicationRecordResponse WriteConcurrencyHeaders(PublicationRecordResponse publication)
    {
        SetConcurrencyHeaders(publication);
        return publication;
    }

    private void SetConcurrencyHeaders(PublicationRecordResponse publication)
    {
        Response.Headers[HeaderNames.ETag] = publication.ConcurrencyToken;
        Response.Headers[HeaderNames.LastModified] = publication.UpdatedAtUtc.ToString("R");
    }
}
