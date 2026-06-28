using Chummer.Run.Contracts.AI.Newspaper;
using Chummer.Run.AI.Services.Newspaper;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.AI.Controllers;

[ApiController]
[Route("api/v1/ai/newspaper")]
public sealed class NewspaperController : ControllerBase
{
    private const int MaxRequestBodyBytes = 16 * 1024;

    private readonly INewspaperCompositionService _compositionService;
    private readonly INewspaperHtmlRenderer _htmlRenderer;
    private readonly INewspaperRenderService _renderService;

    public NewspaperController(
        INewspaperCompositionService compositionService,
        INewspaperHtmlRenderer htmlRenderer,
        INewspaperRenderService renderService)
    {
        _compositionService = compositionService;
        _htmlRenderer = htmlRenderer;
        _renderService = renderService;
    }

    [HttpPost("issue/compose")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<ComposeIssueResponse>(StatusCodes.Status200OK)]
    public ActionResult<ComposeIssueResponse> ComposeIssue([FromBody] ComposeIssueRequest? request)
    {
        if (request is null)
        {
            return BadRequest("Compose request is required.");
        }

        var response = _compositionService.Compose(request);
        return Ok(response);
    }

    [HttpPost("issue/render-html")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<RenderIssueHtmlResponse>(StatusCodes.Status200OK)]
    public ActionResult<RenderIssueHtmlResponse> RenderIssueHtml([FromBody] RenderIssueHtmlRequest? request)
    {
        if (request is null)
        {
            return BadRequest("Render request is required.");
        }

        var response = _htmlRenderer.Render(request.Issue);
        return Ok(response);
    }

    [HttpPost("issue/render-pdf")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [Produces("application/pdf")]
    public async Task<IActionResult> RenderIssuePdf([FromBody] RenderIssueHtmlRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("Render request is required.");
        }

        var response = await _renderService.RenderPdfAsync(request, cancellationToken);
        if (!response.Success || response.Content is null)
        {
            return StatusCode(StatusCodes.Status502BadGateway, response.Error ?? "PDF provider route failed.");
        }

        return File(response.Content, response.ContentType, response.FileName);
    }
}
